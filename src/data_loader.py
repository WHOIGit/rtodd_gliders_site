# data_loader.py
import json
import datetime as dt
from pathlib import Path
from typing import Dict, Any, Optional
from itertools import chain

import numpy as np
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def parse_mission_yyyymmm(mid: str) -> str:
    """Parse a mission id into 'YYYY MMM' (e.g. '2025 Dec').

    Spray-1: 8 chars 'YYMGGGGX' where M is hex 1-9 / A-C.
    Spray-2: 10 chars 'YYMMGGGGXX'.
    Returns '?' on out-of-range month, after a debug log.
    """
    try:
        year = 2000 + int(mid[0:2])
        if len(mid) == 8:
            m = int(mid[2], 16)
        elif len(mid) == 10:
            m = int(mid[2:4])
        else:
            logger.debug(f"unexpected mission id length: {mid!r}")
            return "?"
        if not 1 <= m <= 12:
            logger.debug(f"out-of-range month in mission id: {mid!r}")
            return "?"
        return f"{year} {_MONTH_NAMES[m-1]}"
    except (ValueError, IndexError):
        logger.debug(f"failed to parse mission id: {mid!r}")
        return "?"


class GliderDataLoader:
    """Loads and manages glider deployment JSON data files."""

    INSTRUMENT_KEYS = {'ctd', 'opt', 'dox', 'ph'}
    INSTRUMENT_NAMES = {'ctd': 'CTD', 'opt': 'OPT', 'dox': 'DOX', 'ph': 'PH'}

    def __init__(self, data_dir: Path, auto_load: bool = False, split_dir: Optional[Path] = None):
        self.data_dir = data_dir
        self.split_dir = split_dir if split_dir is not None else data_dir.parent / "splits"
        self.glider_jsons: Dict[str, Dict[str, Any]] = dict()
        self.selected_files: list[str] = []
        self.section_ranges: Dict[str, list[tuple[int, float]]] = dict()
        self.active_sns: set[str] = set()
        self.active_meta: Dict[str, Dict[str, Any]] = dict()
        self.archive_missions: Dict[str, Dict[str, Any]] = dict()
        self._instruments_cache: Optional[Dict[str, dict]] = None
        self._use_split: bool = (self.split_dir / "manifest.json").is_file()
        self._split_manifest: Optional[Dict[str, Any]] = None
        self._loaded_eng: set[str] = set()
        self._loaded_instruments: set[tuple[str, str]] = set()

        self.load_active()
        self.load_secsactive()
        self.load_archive()
        self.load_secsarchive()

        if auto_load:
            if self._use_split:
                self._load_all_tracks()
            else:
                self.load_glider_json()

    # ------------------------------------------------------------------
    # CSV loaders
    # ------------------------------------------------------------------

    def _load_active_csv(self, name: str, spray_type: str) -> None:
        path = self.data_dir / name
        if not path.exists():
            logger.warning(f"{name} not found; skipping {spray_type} active gliders")
            return
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) < 4:
                    continue
                sn = parts[0].strip()
                region = parts[1].strip()
                try:
                    active = int(parts[3])
                except ValueError:
                    continue
                if active != 1:
                    continue
                self.active_sns.add(sn)
                self.active_meta[sn] = {"region": region, "type": spray_type}

    def load_active1(self) -> None:
        """Load active.csv (Spray-1)."""
        self._load_active_csv("active.csv", "spray1")

    def load_active2(self) -> None:
        """Load active2.csv (Spray-2)."""
        self._load_active_csv("active2.csv", "spray2")

    def load_active(self) -> None:
        """Load both active CSVs."""
        self.load_active1()
        self.load_active2()

    def _load_secs_csv(self, name: str, target: Dict[str, list], expected_keys: Optional[set[str]] = None,
                      label: str = "") -> None:
        path = self.data_dir / name
        if not path.exists():
            logger.warning(f"{name} not found; {label or 'gliders'} will use a single (1, inf) section")
            return
        seen: set[str] = set()
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) < 3:
                    continue
                key = parts[0].strip()
                # Defensive zfill for 7-char spray-1 mission ids
                if label == "archive1" and len(key) == 7 and key.isalnum():
                    key = key.zfill(8)
                try:
                    start = int(parts[1])
                    end_raw = parts[2].strip()
                    end = float('inf') if end_raw.lower() == 'inf' else float(end_raw)
                except ValueError:
                    continue
                target.setdefault(key, []).append((start, end))
                seen.add(key)

        if expected_keys is not None:
            missing_in_sec = expected_keys - seen
            extra_in_sec = seen - expected_keys
            for k in missing_in_sec:
                logger.info(f"{k} is in {label} csv but missing from {name}; assuming single (1, inf) section")
                target.setdefault(k, [(1, float('inf'))])
            for k in extra_in_sec:
                logger.info(f"{k} is in {name} but missing from {label} csv")

    def load_secsactive1(self) -> None:
        """Load secsactive.csv (Spray-1)."""
        sn_set = {sn for sn, m in self.active_meta.items() if m["type"] == "spray1"}
        self._load_secs_csv("secsactive.csv", self.section_ranges, sn_set, label="active1")

    def load_secsactive2(self) -> None:
        """Load secsactive2.csv (Spray-2)."""
        sn_set = {sn for sn, m in self.active_meta.items() if m["type"] == "spray2"}
        self._load_secs_csv("secsactive2.csv", self.section_ranges, sn_set, label="active2")

    def load_secsactive(self) -> None:
        self.load_secsactive1()
        self.load_secsactive2()

    def _load_archive_csv(self, name: str, spray_type: str) -> None:
        path = self.data_dir / name
        if not path.exists():
            logger.warning(f"{name} not found; skipping {spray_type} archive missions")
            return
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) < 2:
                    continue
                mid = parts[0].strip()
                # Spray-1: defensive zfill 7→8 (leading zero stripped by spreadsheet round-trip)
                if spray_type == "spray1" and len(mid) == 7 and mid.isalnum():
                    mid = mid.zfill(8)
                region = parts[1].strip()
                self.archive_missions[mid] = {"region": region, "type": spray_type}

    def load_archive1(self) -> None:
        """Load archive.csv (Spray-1)."""
        self._load_archive_csv("archive.csv", "spray1")

    def load_archive2(self) -> None:
        """Load archive2.csv (Spray-2)."""
        self._load_archive_csv("archive2.csv", "spray2")

    def load_archive(self) -> None:
        self.load_archive1()
        self.load_archive2()

    def load_secsarchive1(self) -> None:
        """Load secsarchive.csv (Spray-1)."""
        mid_set = {m for m, meta in self.archive_missions.items() if meta["type"] == "spray1"}
        self._load_secs_csv("secsarchive.csv", self.section_ranges, mid_set, label="archive1")

    def load_secsarchive2(self) -> None:
        """Load secsarchive2.csv (Spray-2)."""
        mid_set = {m for m, meta in self.archive_missions.items() if meta["type"] == "spray2"}
        self._load_secs_csv("secsarchive2.csv", self.section_ranges, mid_set, label="archive2")

    def load_secsarchive(self) -> None:
        self.load_secsarchive1()
        self.load_secsarchive2()

    # ------------------------------------------------------------------
    # File listing and JSON loading
    # ------------------------------------------------------------------

    def files_available(self) -> list[str]:
        """List available active glider JSON data files."""
        if not self.data_dir.exists():
            return []
        files = []
        for f in sorted(self.data_dir.iterdir()):
            if not (f.is_file() and f.name.endswith("_web.json")):
                continue
            sn = f.name.split('_')[0]
            if sn not in self.active_sns:
                continue
            files.append(f.name)
        return files

    def archive_mission_ids(self) -> list[str]:
        """Return sorted list of archive mission ids."""
        return sorted(self.archive_missions.keys())

    def all_active_sns(self) -> list[str]:
        """Return sorted list of all active SNs from CSV (regardless of JSON availability)."""
        return sorted(self.active_sns)

    def has_json(self, glider_id: str) -> bool:
        """Whether a _web.json (or split track) is available for this id."""
        glider_id = str(glider_id)
        filename = f"{glider_id}_web.json"
        if filename in self.glider_jsons:
            return True
        if self._use_split and self._split_manifest:
            entry = self._split_manifest.get("gliders", {}).get(glider_id)
            if entry is not None and (self.split_dir / entry.get("track", "")).exists():
                return True
        return (self.data_dir / filename).exists()

    def set_selected_files(self, filenames: list[str]) -> None:
        """Set and load specific files, clearing previous data."""
        self.selected_files = []
        self.glider_jsons = dict()
        self._instruments_cache = None
        for filename in filenames:
            self.load_glider_json(filename)
            self.selected_files.append(filename)

    def sn_mtimes(self) -> Dict[str, float]:
        """Return dict of {sn: file mtime} for all loaded gliders."""
        if self._use_split and self._split_manifest:
            return {sn: entry["source_mtime"]
                    for sn, entry in self._split_manifest["gliders"].items()
                    if sn in self.active_sns}
        result = {}
        for filename, glider_json in self.glider_jsons.items():
            sn = str(glider_json['mission'])
            if sn in self.active_sns:
                result[sn] = (self.data_dir / filename).stat().st_mtime
        return result

    def latest_filemodified_timestamp(self) -> str:
        mtimes = self.sn_mtimes()
        latest_mtime = max(mtimes.values()) if mtimes else 0
        return dt.datetime.fromtimestamp(latest_mtime).isoformat(timespec='seconds')

    def load_glider_json(self, filename=None, force: bool = False) -> Optional[Dict[str, Any]]:
        """Load glider JSON file(s) into memory cache."""
        if filename in self.glider_jsons and not force:
            return self.glider_jsons[filename]
        if isinstance(filename, str):
            path = self.data_dir / filename
            if not path.exists():
                logger.debug(f"requested glider json not found on disk: {filename}")
                return None
            with path.open() as f:
                content = json.load(f)
            self.glider_jsons[filename] = content
            self._instruments_cache = None
            return content
        elif isinstance(filename, list):
            for f in filename:
                self.load_glider_json(f, force=force)
        else:
            if not self.selected_files:
                self.selected_files = self.files_available()
            for f in self.selected_files:
                self.load_glider_json(f, force=force)
        return None

    def load_archived(self, mission_id: str) -> Optional[Dict[str, Any]]:
        """Lazy-load a single archived mission's _web.json."""
        filename = f"{mission_id}_web.json"
        if filename in self.glider_jsons:
            return self.glider_jsons[filename]

        if self._use_split and self._split_manifest:
            entry = self._split_manifest.get("gliders", {}).get(mission_id)
            if entry is not None:
                track_path = self.split_dir / entry["track"]
                if track_path.exists():
                    with track_path.open() as f:
                        track_data = json.load(f)
                    self.glider_jsons[filename] = track_data
                    self._instruments_cache = None
                    return track_data

        path = self.data_dir / filename
        if not path.exists():
            logger.debug(f"archive mission {mission_id} listed in csv but no _web.json on disk")
            return None
        with path.open() as f:
            content = json.load(f)
        self.glider_jsons[filename] = content
        self._instruments_cache = None
        return content

    def _load_all_tracks(self) -> None:
        manifest_path = self.split_dir / "manifest.json"
        with manifest_path.open() as f:
            self._split_manifest = json.load(f)
        for sn_str, entry in self._split_manifest["gliders"].items():
            if sn_str not in self.active_sns:
                continue
            track_path = self.split_dir / entry["track"]
            with track_path.open() as f:
                track_data = json.load(f)
            filename = f"{sn_str}_web.json"
            self.glider_jsons[filename] = track_data
            if filename not in self.selected_files:
                self.selected_files.append(filename)
        self._instruments_cache = None
        logger.info(f"Loaded {len(self.glider_jsons)} track files from split dir")

    def load_eng(self, sn: str) -> None:
        if not self._use_split or sn in self._loaded_eng:
            return
        if self._split_manifest is None:
            return
        entry = self._split_manifest["gliders"].get(sn)
        if entry is None or "eng" not in entry:
            return
        eng_path = self.split_dir / entry["eng"]
        with eng_path.open() as f:
            eng_data = json.load(f)
        filename = f"{sn}_web.json"
        if filename in self.glider_jsons:
            self.glider_jsons[filename]["eng"] = eng_data
        self._loaded_eng.add(sn)
        logger.info(f"Lazy-loaded eng for sn={sn}")

    def load_instrument(self, sn: str, inst_key: str) -> None:
        if not self._use_split or (sn, inst_key) in self._loaded_instruments:
            return
        if self._split_manifest is None:
            return
        entry = self._split_manifest["gliders"].get(sn)
        if entry is None:
            return
        inst_files = entry.get("instruments", {})
        if inst_key not in inst_files:
            return
        inst_path = self.split_dir / inst_files[inst_key]
        with inst_path.open() as f:
            inst_data = json.load(f)
        filename = f"{sn}_web.json"
        if filename in self.glider_jsons:
            self.glider_jsons[filename][inst_key] = inst_data
        self._loaded_instruments.add((sn, inst_key))
        logger.info(f"Lazy-loaded {inst_key} for sn={sn}")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def glider_sns(self) -> list[str]:
        """Return ids of currently-loaded active gliders (string sn)."""
        out = []
        for gj in self.glider_jsons.values():
            sn = str(gj['mission'])
            if sn in self.active_sns:
                out.append(sn)
        return out

    def instruments(self) -> Dict[str, dict]:
        if self._instruments_cache is not None:
            return self._instruments_cache
        insts: Dict[str, dict] = {}
        for filename, glider_json in self.glider_jsons.items():
            sn = str(glider_json['mission'])
            for inst_key in self.INSTRUMENT_KEYS:
                if inst_key not in glider_json:
                    continue
                inst_name = self.INSTRUMENT_NAMES[inst_key]
                if inst_name not in insts:
                    insts[inst_name] = dict(gliders=[sn], key=inst_key)
                else:
                    insts[inst_name]['gliders'].append(sn)
        self._instruments_cache = insts
        return insts

    def dv_fields(self) -> Dict[str, Dict[str, dict]]:
        fields: Dict[str, Dict[str, dict]] = {}
        for filename, glider_json in self.glider_jsons.items():
            sn = str(glider_json['mission'])
            for inst_key in self.INSTRUMENT_KEYS:
                if inst_key not in glider_json:
                    continue
                inst_name = self.INSTRUMENT_NAMES[inst_key]
                for field_name, field_meta in glider_json[inst_key]['info'].items():
                    if field_name in ('time', 'phase'):
                        continue
                    inst_field_tag = f"{inst_name}:{field_name}"
                    fields.setdefault(inst_field_tag, {})[sn] = field_meta
        return fields

    def sn_to_filename(self, glider_id: str) -> str:
        """Look up filename for a given id (sn or mission)."""
        glider_id = str(glider_id)
        for filename, glider_json in self.glider_jsons.items():
            if glider_id == str(glider_json['mission']):
                return filename
        # Fallback to constructed filename
        candidate = f"{glider_id}_web.json"
        if (self.data_dir / candidate).exists():
            return candidate
        raise KeyError(f'glider_id {glider_id!r} not found. Loaded: {list(self.glider_jsons.keys())}')

    def filename_to_sn(self, filename: str) -> str:
        return str(self.glider_jsons[filename]['mission'])

    def _assign_sections(self, df: pd.DataFrame, glider_id: str) -> pd.DataFrame:
        df["section"] = 1
        ranges = self.section_ranges.get(glider_id)
        if not ranges:
            return df
        section = np.full(len(df), np.nan)
        nd = df["ndive"].to_numpy()
        for i, (start, end) in enumerate(ranges, start=1):
            if np.isinf(end):
                mask = nd >= start
            else:
                mask = (nd >= start) & (nd <= end)
            section[mask] = i
        df["section"] = np.nan_to_num(section, nan=1).astype(int)
        return df

    def sections_for_glider(self, glider_id: str) -> list[dict]:
        ranges = self.section_ranges.get(str(glider_id), [])
        sections = []
        for i, (start, end) in enumerate(ranges, start=1):
            if np.isinf(end):
                label = f"Section {i} (dives {start}+)"
            else:
                label = f"Section {i} (dives {start}-{int(end)})"
            sections.append({"id": i, "start": start, "end": end, "label": label})
        return sections

    def build_glider_df(self, glider_id: str) -> pd.DataFrame:
        glider_id = str(glider_id)
        data = self.glider_jsons[self.sn_to_filename(glider_id)]
        flat_data = {}
        for key in ['time', 'lat', 'lon']:
            flat_data[key] = list(chain.from_iterable(data[key]))
        df = pd.DataFrame(flat_data)
        df["ndive"] = np.repeat(np.arange(1, len(df) // 2 + 1), 2)
        return self._assign_sections(df, glider_id)

    def build_uv_df(self, glider_id: str) -> pd.DataFrame:
        glider_id = str(glider_id)
        data = self.glider_jsons[self.sn_to_filename(glider_id)]

        midlats = [(divestart + diveend)/2
                   if isinstance(divestart, float) and isinstance(diveend, float)
                   else None
                   for divestart, diveend in data['lat']]
        midlons = [(divestart + diveend)/2
                   if isinstance(divestart, float) and isinstance(diveend, float)
                   else None
                   for divestart, diveend in data['lon']]
        timestamps = [timestart for timestart, timeend in data['time']]
        flat_data = dict(time=timestamps, lat=midlats, lon=midlons, u=data['u'], v=data['v'])

        df = pd.DataFrame(flat_data)
        df['glider_sn'] = glider_id
        df["ndive"] = np.arange(1, len(df) + 1)
        return self._assign_sections(df, glider_id)

    def glider_ndive_t0(self, glider_id: str, ndive: int) -> float:
        data = self.glider_jsons[self.sn_to_filename(str(glider_id))]
        t0 = data['time'][ndive-1][0]
        return t0

    @staticmethod
    def pad_emptys(segment_lengths, inst_data, fill_val=0):
        padded_block = []
        for data_block, expected_len in zip(inst_data, segment_lengths):
            if len(data_block) == expected_len:
                padded_block.append(data_block)
            elif len(data_block) == 0:
                padded_block.append([fill_val]*expected_len)
            else:
                raise ValueError('Will cause flattening error')
        return padded_block

    def build_instrument_df(
        self,
        glider_id: str,
        instrument_name: str,
        ndive_range: Optional[tuple[int, int]] = None,
        time_range: Optional[tuple[float, float]] = None,
        phase: Optional[str] = None,
    ) -> pd.DataFrame:
        glider_id = str(glider_id)
        instrument_key = self.instruments()[instrument_name]['key']
        self.load_instrument(glider_id, instrument_key)
        data = self.glider_jsons[self.sn_to_filename(glider_id)]
        data = data[instrument_key].copy()
        flat_data = dict(divetime=[], datetime=[])

        for dive_num, times in enumerate(data['time'], start=1):
            flat_data['divetime'].extend(times)
            ndive_t0 = self.glider_ndive_t0(glider_id, dive_num)
            if ndive_t0 is None:
                flat_data['datetime'].extend([None] * len(times))
            else:
                flat_data['datetime'].extend([t + ndive_t0 if t is not None else None for t in times])

        nested_keys = [k for k in data.keys() if k not in ['info', 'ndive', 'time']]
        segment_lengths = [len(segment) for segment in data['time']]

        flat_data['ndive'] = list(chain.from_iterable(
            [[dive_num] * seg_len for dive_num, seg_len in enumerate(segment_lengths, start=1)]
        ))

        for key in nested_keys:
            padded = self.pad_emptys(segment_lengths, data[key])
            flat_data[key] = list(chain.from_iterable(padded))

        df = pd.DataFrame(flat_data)
        df['glider_sn'] = glider_id
        df['instrument'] = instrument_name

        if ndive_range is not None:
            start, end = ndive_range
            df = df[df['ndive'].between(start, end)]

        if time_range is not None:
            t_start, t_end = time_range
            df = df[(df['datetime'] >= t_start) & (df['datetime'] <= t_end)]

        if phase is not None and 'phase' in df.columns:
            if phase == 'descent':
                df = df[df['phase'] == 1]
            elif phase == 'ascent':
                df = df[df['phase'] != 1]

        return df

    def time_range(self) -> tuple[float, float]:
        t_min, t_max = dt.datetime.now().timestamp(), 0
        for filename, data in self.glider_jsons.items():
            t_min = min(data['time'][0][0], t_min)
            t_max = max(data['time'][-1][-1], t_max)
        if t_max <= t_min:
            t_max = t_min
            t_min -= 3600
        return t_min, t_max

    def instrument_in_glider(self, instrument_name: str, glider_id: str) -> bool:
        instrument_key = self.instruments()[instrument_name]['key']
        return instrument_key in self.glider_jsons[self.sn_to_filename(str(glider_id))]
