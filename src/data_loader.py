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

    def __init__(self, data_dir: Path, auto_load: bool = False):
        self.data_dir = data_dir
        self.glider_jsons: Dict[str, Dict[str, Any]] = dict()
        self.selected_files: list[str] = []
        self.section_ranges: Dict[int, list[tuple[int, float]]] = dict()
        self.active_sns: Optional[set[int]] = None
        self._instruments_cache: Optional[Dict[str, dict]] = None
        self.load_active2()
        self.load_secsactive2()
        if auto_load:
            self.load_glider_json()

    def files_available(self) -> list[str]:
        """List available JSON data files, filtered by active gliders."""
        if not self.data_dir.exists():
            return []
        files = []
        for f in sorted(self.data_dir.iterdir()):
            if not (f.is_file() and f.suffix.lower() == ".json"):
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

    def latest_filemodified_timestamp(self) -> str:
        """Return ISO timestamp of the most recently modified data file."""
        latest_mtime = 0
        for filename in self.files_available():
            path = self.data_dir / filename
            mtime = path.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
        latest_mtime = dt.datetime.fromtimestamp(latest_mtime).isoformat(timespec='seconds')
        return latest_mtime

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
        return [gj['sn'] for gj in self.glider_jsons.values()]

    def instruments(self) -> Dict[str, dict]:
        """Return instrument metadata: {inst_name: {'key': str, 'gliders': [int]}}."""
        if self._instruments_cache is not None:
            return self._instruments_cache
        insts = {}
        for filename, glider_json in self.glider_jsons.items():
            sn = glider_json['sn']
            for inst_key, val in glider_json.items():
                if isinstance(val, dict) and 'info' in val and 'time' in val:
                    inst_name = val['info']['tag']
                    if inst_name not in insts:
                        insts[inst_name] = dict(gliders=[sn], key=inst_key)
                    else:
                        assert insts[inst_name]['key'] == inst_key
                        insts[inst_name]['gliders'].append(sn)
        self._instruments_cache = insts
        return insts

    def dv_fields(self) -> Dict[str, Dict[int, dict]]:
        """Return dependent variable fields: {'inst:field': {sn: field_meta}}."""
        fields = {}
        for filename, glider_json in self.glider_jsons.items():
            sn = glider_json['sn']
            for key, val in glider_json.items():
                if isinstance(val, dict) and 'info' in val:
                    inst_name = val['info']['tag']
                    for field_tag, field_name in val['info']['tags'].items():
                        if field_name == 'time': continue
                        field_meta = val['info']['fields'][field_name]
                        inst_field_tag = f"{inst_name}:{field_name}"
                        if inst_field_tag not in fields:
                            fields[inst_field_tag] = {sn: field_meta}
                        else:
                            fields[inst_field_tag][sn] = field_meta
        return fields

    def sn_to_filename(self, glider_sn: int) -> str:
        """Look up filename for a given serial number."""
        for filename, glider_json in self.glider_jsons.items():
            if glider_sn == glider_json['sn']:
                return filename
        raise KeyError(f'glider_sn {glider_sn} not found. Available are: {self.glider_sns()}')

    def filename_to_sn(self, filename: str) -> int:
        """Look up serial number for a given filename."""
        return self.glider_jsons[filename]['sn']

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
            DataFrame with columns: time, ndive, depth, phase, [channels], glider_sn, instrument.
        """
        data = self.glider_jsons[self.sn_to_filename(glider_sn)]
        instrument_key = self.instruments()[instrument_name]['key']
        data = data[instrument_key].copy()
        flat_data = dict(time=[])

        for dive_num, times in zip(data['ndive'], data['time']):
            if dive_num is None: continue
            ndive_t0 = self.glider_ndive_t0(glider_sn, dive_num)
            if ndive_t0 is None:
                unixtimes = [None] * len(times)
            else:
                unixtimes = [t + ndive_t0 if t is not None else None for t in times]
            flat_data['time'].extend(unixtimes)

        nested_keys = [k for k in data.keys() if k not in ['info', 'ndive', 'time']]
        segment_lengths = [len(segment) for segment in data['time']]

        flat_data['ndive'] = list(chain.from_iterable(
            [[dive_num] * seg_len for dive_num, seg_len in zip(data["ndive"], segment_lengths)]
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
            df = df[(df['time'] >= t_start) & (df['time'] <= t_end)]

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
