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

class GliderDataLoader:
    """Loads and manages glider deployment JSON data files."""

    def __init__(self, data_dir: Path, auto_load: bool = False, split_dir: Optional[Path] = None):
        self.data_dir = data_dir
        self.split_dir = split_dir if split_dir is not None else data_dir / "split"
        self.glider_jsons: Dict[str, Dict[str, Any]] = dict()
        self.selected_files: list[str] = []
        self.section_ranges: Dict[int, list[tuple[int, float]]] = dict()
        self.active_sns: Optional[set[int]] = None
        self._instruments_cache: Optional[Dict[str, dict]] = None
        self._use_split: bool = (self.split_dir / "manifest.json").is_file()
        self._split_manifest: Optional[Dict[str, Any]] = None
        self._loaded_eng: set[int] = set()
        self._loaded_instruments: set[tuple] = set()
        self.load_active2()
        self.load_secsactive2()
        if auto_load:
            if self._use_split:
                self._load_all_tracks()
            else:
                self.load_glider_json()

    def files_available(self) -> list[str]:
        """List available JSON data files, filtered by active gliders."""
        if not self.data_dir.exists():
            return []
        files = []
        for f in sorted(self.data_dir.iterdir()):
            if not (f.is_file() and f.name.endswith("_web.json")):
                continue
            if self.active_sns is not None:
                try:
                    sn = int(f.name.split('_')[0])
                except ValueError:
                    continue
                if sn not in self.active_sns:
                    continue
            files.append(f.name)
        return files

    def set_selected_files(self, filenames: list[str]) -> None:
        """Set and load specific files, clearing previous data."""
        self.selected_files = []
        self.glider_jsons = dict()
        self._instruments_cache = None
        for filename in filenames:
            self.load_glider_json(filename)
            self.selected_files.append(filename)

    def sn_mtimes(self) -> Dict[int, float]:
        """Return dict of {sn: file mtime} for all loaded gliders."""
        if self._use_split and self._split_manifest:
            result = {}
            for sn_str, entry in self._split_manifest["gliders"].items():
                result[int(sn_str)] = entry["source_mtime"]
            return result
        result = {}
        for filename, glider_json in self.glider_jsons.items():
            sn = int(glider_json['mission'])
            result[sn] = (self.data_dir / filename).stat().st_mtime
        return result

    def latest_filemodified_timestamp(self) -> str:
        """Return ISO timestamp of the most recently modified data file."""
        mtimes = self.sn_mtimes()
        latest_mtime = max(mtimes.values()) if mtimes else 0
        return dt.datetime.fromtimestamp(latest_mtime).isoformat(timespec='seconds')

    def load_glider_json(self, filename=None, force: bool = False) -> Optional[Dict[str, Any]]:
        """Load glider JSON file(s) into memory cache.

        Args:
            filename: A single filename, list of filenames, or None to load all available.
            force: If True, reload even if already cached.
        """
        if filename in self.glider_jsons and not force:
            return self.glider_jsons[filename]
        if isinstance(filename, str):
            path = self.data_dir / filename
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

    def _load_all_tracks(self) -> None:
        """Load track split files for all active gliders into glider_jsons."""
        manifest_path = self.split_dir / "manifest.json"
        with manifest_path.open() as f:
            self._split_manifest = json.load(f)
        for sn_str, entry in self._split_manifest["gliders"].items():
            sn = int(sn_str)
            if self.active_sns is not None and sn not in self.active_sns:
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

    def _manifest_key(self, sn: int) -> str | None:
        """Return the manifest gliders key whose numeric value equals sn."""
        if self._split_manifest is None:
            return None
        for key in self._split_manifest.get("gliders", {}):
            try:
                if int(key) == sn:
                    return key
            except ValueError:
                pass
        return None

    def load_eng(self, sn: int) -> None:
        """Lazy-load eng data for a glider from split files (no-op if not using split)."""
        if not self._use_split or sn in self._loaded_eng:
            return
        if self._split_manifest is None:
            return
        sn_str = self._manifest_key(sn)
        entry = self._split_manifest["gliders"].get(sn_str) if sn_str else None
        if entry is None or "eng" not in entry:
            return
        eng_path = self.split_dir / entry["eng"]
        with eng_path.open() as f:
            eng_data = json.load(f)
        filename = f"{sn_str}_web.json"
        if filename in self.glider_jsons:
            self.glider_jsons[filename]["eng"] = eng_data
        self._loaded_eng.add(sn)
        logger.info(f"Lazy-loaded eng for sn={sn}")

    def load_instrument(self, sn: int, inst_key: str) -> None:
        """Lazy-load a full instrument block for a glider from split files."""
        if not self._use_split or (sn, inst_key) in self._loaded_instruments:
            return
        if self._split_manifest is None:
            return
        sn_str = self._manifest_key(sn)
        entry = self._split_manifest["gliders"].get(sn_str) if sn_str else None
        if entry is None:
            return
        inst_files = entry.get("instruments", {})
        if inst_key not in inst_files:
            return
        inst_path = self.split_dir / inst_files[inst_key]
        with inst_path.open() as f:
            inst_data = json.load(f)
        filename = f"{sn_str}_web.json"
        if filename in self.glider_jsons:
            self.glider_jsons[filename][inst_key] = inst_data
        self._loaded_instruments.add((sn, inst_key))
        logger.info(f"Lazy-loaded {inst_key} for sn={sn}")

    def load_active2(self) -> None:
        """Load active2.csv to determine which gliders are active."""
        path = self.data_dir / 'active2.csv'
        if not path.exists():
            self.active_sns = None
            return
        df = pd.read_csv(path, header=None, usecols=[0, 3],
                         names=["sn", "active"], dtype={"sn": int, "active": int})
        self.active_sns = set(df.loc[df["active"] == 1, "sn"])

    def load_secsactive2(self) -> None:
        """Load secsactive2.csv to populate section dive ranges per glider."""
        path = self.data_dir / 'secsactive2.csv'
        if not path.exists():
            self.section_ranges = {}
            return
        df = pd.read_csv(path, header=None, names=["sn", "start", "end"],
                         dtype={"sn": int, "start": float, "end": float})

        self.section_ranges = {}
        for sn, g in df.groupby("sn", sort=False):
            if self.active_sns is not None and sn not in self.active_sns:
                continue
            self.section_ranges[sn] = [(int(r.start), float(r.end)) for r in g.itertuples(index=False)]

    def glider_sns(self) -> list[int]:
        """Return serial numbers of all loaded gliders."""
        return [int(gj['mission']) for gj in self.glider_jsons.values()]

    INSTRUMENT_KEYS = {'ctd', 'opt', 'dox', 'ph'}
    INSTRUMENT_NAMES = {'ctd': 'CTD', 'opt': 'OPT', 'dox': 'DOX', 'ph': 'PH'}

    def instruments(self) -> Dict[str, dict]:
        """Return instrument metadata: {inst_name: {'key': str, 'gliders': [int]}}."""
        if self._instruments_cache is not None:
            return self._instruments_cache
        insts = {}
        for filename, glider_json in self.glider_jsons.items():
            sn = int(glider_json['mission'])
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

    def dv_fields(self) -> Dict[str, Dict[int, dict]]:
        """Return dependent variable fields: {'inst:field': {sn: field_meta}}."""
        fields = {}
        for filename, glider_json in self.glider_jsons.items():
            sn = int(glider_json['mission'])
            for inst_key in self.INSTRUMENT_KEYS:
                if inst_key not in glider_json:
                    continue
                inst_name = self.INSTRUMENT_NAMES[inst_key]
                for field_name, field_meta in glider_json[inst_key]['info'].items():
                    if field_name in ('time', 'phase'):
                        continue
                    inst_field_tag = f"{inst_name}:{field_name}"
                    if inst_field_tag not in fields:
                        fields[inst_field_tag] = {sn: field_meta}
                    else:
                        fields[inst_field_tag][sn] = field_meta
        return fields

    def sn_to_filename(self, glider_sn: int) -> str:
        """Look up filename for a given serial number."""
        for filename, glider_json in self.glider_jsons.items():
            if glider_sn == int(glider_json['mission']):
                return filename
        raise KeyError(f'glider_sn {glider_sn} not found. Available are: {self.glider_sns()}')

    def filename_to_sn(self, filename: str) -> int:
        """Look up serial number for a given filename."""
        return int(self.glider_jsons[filename]['mission'])

    def _assign_sections(self, df: pd.DataFrame, glider_sn: int) -> pd.DataFrame:
        """Add section column to DataFrame based on ndive ranges from secsactive2."""
        df["section"] = 1
        if not self.section_ranges:
            return df
        ranges = self.section_ranges.get(glider_sn)
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

    def sections_for_glider(self, glider_sn: int) -> list[dict]:
        """Return section info dicts for a glider's sections.

        Returns list of {'id': int, 'start': int, 'end': float, 'label': str}.
        """
        ranges = self.section_ranges.get(glider_sn, [])
        sections = []
        for i, (start, end) in enumerate(ranges, start=1):
            if np.isinf(end):
                label = f"Section {i} (dives {start}+)"
            else:
                label = f"Section {i} (dives {start}-{int(end)})"
            sections.append({"id": i, "start": start, "end": end, "label": label})
        return sections

    def build_glider_df(self, glider_sn: int) -> pd.DataFrame:
        """Build GPS track DataFrame with 2 rows per dive (start + end)."""
        data = self.glider_jsons[self.sn_to_filename(glider_sn)]
        flat_data = {}
        for key in ['time', 'lat', 'lon']:
            flat_data[key] = list(chain.from_iterable(data[key]))
        df = pd.DataFrame(flat_data)
        df["ndive"] = np.repeat(np.arange(1, len(df) // 2 + 1), 2)
        return self._assign_sections(df, glider_sn)

    def build_uv_df(self, glider_sn: int) -> pd.DataFrame:
        """Build depth-averaged current DataFrame with 1 row per dive."""
        data = self.glider_jsons[self.sn_to_filename(glider_sn)]

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
        df['glider_sn'] = glider_sn
        df["ndive"] = np.arange(1, len(df) + 1)
        return self._assign_sections(df, glider_sn)

    def glider_ndive_t0(self, glider_sn: int, ndive: int) -> float:
        """Return unix timestamp at dive start for a given glider and dive number."""
        data = self.glider_jsons[self.sn_to_filename(glider_sn)]
        t0 = data['time'][ndive-1][0]
        return t0

    @staticmethod
    def pad_emptys(segment_lengths, inst_data, fill_val=0):
        """Pad empty nested lists to match expected segment lengths."""
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
        glider_sn: int,
        instrument_name: str,
        ndive_range: Optional[tuple[int, int]] = None,
        time_range: Optional[tuple[float, float]] = None,
        phase: Optional[str] = None,
    ) -> pd.DataFrame:
        """Build flattened sensor DataFrame for an instrument.

        Args:
            glider_sn: Glider serial number.
            instrument_name: Instrument name (e.g. 'CTD').
            ndive_range: Optional (start, end) inclusive dive range filter.
            time_range: Optional (unix_start, unix_end) time filter.
            phase: Optional 'descent' or 'ascent' cast filter.

        Returns:
            DataFrame with columns: divetime, datetime, ndive, depth, phase, [channels], glider_sn, instrument.
        """
        instrument_key = self.instruments()[instrument_name]['key']
        self.load_instrument(glider_sn, instrument_key)
        data = self.glider_jsons[self.sn_to_filename(glider_sn)]
        data = data[instrument_key].copy()
        flat_data = dict(divetime=[], datetime=[])

        for dive_num, times in enumerate(data['time'], start=1):
            flat_data['divetime'].extend(times)
            ndive_t0 = self.glider_ndive_t0(glider_sn, dive_num)
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
        df['glider_sn'] = glider_sn
        df['instrument'] = instrument_name

        # Apply optional filters
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
        """Return (min, max) unix timestamps across all loaded gliders."""
        t_min, t_max = dt.datetime.now().timestamp(), 0
        for filename, data in self.glider_jsons.items():
            t_min = min(data['time'][0][0], t_min)
            t_max = max(data['time'][-1][-1], t_max)
        if t_max <= t_min:
            t_max = t_min
            t_min -= 3600
        return t_min, t_max

    def instrument_in_glider(self, instrument_name: str, glider_sn: int) -> bool:
        """Check if a glider has a given instrument."""
        instrument_key = self.instruments()[instrument_name]['key']
        return instrument_key in self.glider_jsons[self.sn_to_filename(glider_sn)]
