# data_loader.py
import json
import datetime as dt
import os
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from itertools import chain

import numpy as np
import pandas as pd
from netCDF4 import Dataset
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# The netCDF4 Python package uses the HDF5 C library underneath. In threaded
# Dash dev servers, concurrent reads can crash the interpreter instead of
# raising Python exceptions, so all Dataset open/read/close blocks are serialized.
_NETCDF_LOCK = threading.RLock()


_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def parse_mission_yyyymmm(mid: str) -> str:
    """Parse a mission id into 'YYYY MMM' (e.g. '2025 Dec')."""
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


def _filled(value) -> np.ndarray:
    return np.asarray(np.ma.filled(value, np.nan), dtype="float64")


def _safe_json_attr(obj, attr: str, default):
    raw = getattr(obj, attr, None)
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


class GliderDataLoader:
    """Loads glider deployment data from data/netcdf/*.nc files."""

    INSTRUMENT_KEYS = {'ctd', 'opt', 'dox', 'ph', 'adcp'}
    INSTRUMENT_NAMES = {'ctd': 'CTD', 'opt': 'OPT', 'dox': 'DOX', 'ph': 'PH', 'adcp': 'ADCP'}
    PROFILE_READ_CHUNK_DIVES = 16

    def __init__(
        self,
        data_dir: Path,
        auto_load: bool = False,
        netcdf_dir: Optional[Path] = None,
        split_dir: Optional[Path] = None,
    ):
        self.data_dir = data_dir
        # split_dir remains accepted so older call sites do not break, but it is ignored.
        self.netcdf_dir = netcdf_dir if netcdf_dir is not None else data_dir.parent / "netcdf"
        self.glider_jsons: Dict[str, Dict[str, Any]] = dict()
        self.selected_files: list[str] = []
        self.section_ranges: Dict[str, list[tuple[int, float]]] = dict()
        self.active_sns: set[str] = set()
        self.active_meta: Dict[str, Dict[str, Any]] = dict()
        self.archive_missions: Dict[str, Dict[str, Any]] = dict()
        self.variable_names: Dict[str, str] = dict()
        self._instruments_cache: Optional[Dict[str, dict]] = None
        self._manifest: Dict[str, Any] = {"gliders": {}}

        self.load_active()
        self.load_secsactive()
        self.load_archive()
        self.load_secsarchive()
        self.load_variables()
        self._load_manifest()

        if auto_load:
            self._load_all_tracks()

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
                self.active_meta[sn] = {
                    "region": region,
                    "type": spray_type,
                    "variables": [p.strip() for p in parts[4:] if p.strip()],
                }

    def load_active1(self) -> None:
        self._load_active_csv("active.csv", "spray1")

    def load_active2(self) -> None:
        self._load_active_csv("active2.csv", "spray2")

    def load_active(self) -> None:
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
                logger.debug(f"{k} is in {name} but missing from {label} csv")

    def load_secsactive1(self) -> None:
        sn_set = {sn for sn, m in self.active_meta.items() if m["type"] == "spray1"}
        self._load_secs_csv("secsactive.csv", self.section_ranges, sn_set, label="active1")

    def load_secsactive2(self) -> None:
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
                if spray_type == "spray1" and len(mid) == 7 and mid.isalnum():
                    mid = mid.zfill(8)
                region = parts[1].strip()
                self.archive_missions[mid] = {
                    "region": region,
                    "type": spray_type,
                    "variables": [p.strip() for p in parts[3:] if p.strip()],
                }

    def load_archive1(self) -> None:
        self._load_archive_csv("archive.csv", "spray1")

    def load_archive2(self) -> None:
        self._load_archive_csv("archive2.csv", "spray2")

    def load_archive(self) -> None:
        self.load_archive1()
        self.load_archive2()

    def load_secsarchive1(self) -> None:
        mid_set = {m for m, meta in self.archive_missions.items() if meta["type"] == "spray1"}
        self._load_secs_csv("secsarchive.csv", self.section_ranges, mid_set, label="archive1")

    def load_secsarchive2(self) -> None:
        mid_set = {m for m, meta in self.archive_missions.items() if meta["type"] == "spray2"}
        self._load_secs_csv("secsarchive2.csv", self.section_ranges, mid_set, label="archive2")

    def load_secsarchive(self) -> None:
        self.load_secsarchive1()
        self.load_secsarchive2()

    def load_variables(self) -> None:
        """Load variable display names from variables.csv (key, name, units)."""
        path = self.data_dir / "variables.csv"
        if not path.exists():
            logger.warning("variables.csv not found; variable display names unavailable")
            return
        with path.open() as f:
            for line in f:
                parts = line.split(",")
                if len(parts) < 2:
                    continue
                key = parts[0].strip()
                name = parts[1].strip()
                if key and name:
                    self.variable_names[key] = name

    def section_variables(self, key: str) -> list[str]:
        """Plot variable tokens for a glider SN or archive mission ID.

        Sourced from the active*/archive* CSVs; drives the Section Details charts.
        Returns an empty list when the SN/mission is unknown or lists no variables.
        """
        meta = self.active_meta.get(str(key)) or self.archive_missions.get(str(key))
        return list(meta.get("variables", [])) if meta else []

    # ------------------------------------------------------------------
    # NetCDF manifest and track loading
    # ------------------------------------------------------------------

    def _load_manifest(self) -> None:
        manifest_path = self.netcdf_dir / "manifest.json"
        if not manifest_path.exists():
            self._manifest = {"gliders": {}}
            return
        try:
            self._manifest = json.loads(manifest_path.read_text())
        except Exception as e:
            logger.warning(f"Failed to read NetCDF manifest: {e}")
            self._manifest = {"gliders": {}}

    def _entry(self, glider_id: str) -> Optional[dict]:
        return self._manifest.get("gliders", {}).get(str(glider_id))

    def _store_path(self, glider_id: str) -> Optional[Path]:
        entry = self._entry(glider_id)
        if not entry:
            return None
        store = entry.get("store")
        if not store:
            return None
        return self.netcdf_dir / store

    def _tracks_store_path(self) -> Path:
        return self.netcdf_dir / self._manifest.get("tracks_store", "tracks.nc")

    def _open_dataset(self, glider_id: str) -> Dataset:
        path = self._store_path(glider_id)
        if path is None or not path.exists():
            raise FileNotFoundError(f"No NetCDF store for glider_id {glider_id!r}")
        return Dataset(path, "r")

    def files_available(self) -> list[str]:
        files = []
        for sn in sorted(self.active_sns):
            if self.has_json(sn):
                files.append(f"{sn}_web.json")
        return files

    def archive_mission_ids(self) -> list[str]:
        return sorted(self.archive_missions.keys())

    def all_active_sns(self) -> list[str]:
        return sorted(self.active_sns)

    def has_json(self, glider_id: str) -> bool:
        path = self._store_path(str(glider_id))
        return bool(path and path.exists())

    def set_selected_files(self, filenames: list[str]) -> None:
        self.selected_files = []
        self.glider_jsons = dict()
        self._instruments_cache = None
        for filename in filenames:
            self.load_glider_json(filename)
            self.selected_files.append(filename)

    def sn_mtimes(self) -> Dict[str, float]:
        return {
            sn: entry["source_mtime"]
            for sn, entry in self._manifest.get("gliders", {}).items()
            if sn in self.active_sns and self.has_json(sn) and entry.get("source_mtime") is not None
        }

    def latest_filemodified_timestamp(self) -> str:
        mtimes = self.sn_mtimes()
        latest_mtime = max(mtimes.values()) if mtimes else 0
        return dt.datetime.fromtimestamp(latest_mtime).isoformat(timespec='seconds')

    def load_glider_json(self, filename=None, force: bool = False) -> Optional[Dict[str, Any]]:
        if isinstance(filename, str):
            glider_id = filename[:-9] if filename.endswith("_web.json") else filename
            return self._load_track(glider_id, force=force)
        if isinstance(filename, list):
            for f in filename:
                self.load_glider_json(f, force=force)
        else:
            if not self.selected_files:
                self.selected_files = self.files_available()
            for f in self.selected_files:
                self.load_glider_json(f, force=force)
        return None

    def load_archived(self, mission_id: str) -> Optional[Dict[str, Any]]:
        return self._load_track(str(mission_id))

    def _load_all_tracks(self) -> None:
        self._load_manifest()
        if self._load_all_tracks_from_tracks_store(active_only=True):
            logger.info(f"Loaded {len(self.glider_jsons)} track records from aggregate NetCDF")
            return
        for sn_str in self._manifest.get("gliders", {}):
            if sn_str not in self.active_sns:
                continue
            self._load_track(sn_str)
        logger.info(f"Loaded {len(self.glider_jsons)} track records from NetCDF")

    def _tracks_group_by_id(self, ds: Dataset) -> dict[str, Any]:
        tracks = ds.groups.get("tracks")
        if tracks is None:
            return {}
        return {
            str(getattr(group, "glider_id", name)): group
            for name, group in tracks.groups.items()
        }

    def _track_data_from_group(self, glider_id: str, group) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "mission": str(getattr(group, "mission", glider_id)),
            "glider_version": str(getattr(group, "glider_version", "")),
        }
        for key in ("time", "lat", "lon"):
            data[key] = _filled(group.variables[key][:]).tolist()
        for key in ("u", "v"):
            data[key] = _filled(group.variables[key][:]).tolist()

        inst_parent = group.groups.get("instruments")
        if inst_parent is not None:
            for inst_key, inst_group in inst_parent.groups.items():
                data[inst_key] = {"info": _safe_json_attr(inst_group, "info_json", {})}
        return data

    def _load_all_tracks_from_tracks_store(self, active_only: bool = True) -> bool:
        path = self._tracks_store_path()
        if not path.exists():
            return False
        try:
            with _NETCDF_LOCK, Dataset(path, "r") as ds:
                for glider_id, group in self._tracks_group_by_id(ds).items():
                    if active_only and glider_id not in self.active_sns:
                        continue
                    self.glider_jsons[f"{glider_id}_web.json"] = self._track_data_from_group(glider_id, group)
        except Exception as e:
            logger.warning(f"Failed to load aggregate tracks NetCDF {path}: {e}")
            return False
        self._instruments_cache = None
        return True

    def _load_track_from_tracks_store(self, glider_id: str) -> Optional[Dict[str, Any]]:
        path = self._tracks_store_path()
        if not path.exists():
            return None
        try:
            with _NETCDF_LOCK, Dataset(path, "r") as ds:
                group = self._tracks_group_by_id(ds).get(str(glider_id))
                if group is None:
                    return None
                return self._track_data_from_group(str(glider_id), group)
        except Exception as e:
            logger.warning(f"Failed to load {glider_id} from aggregate tracks NetCDF {path}: {e}")
            return None

    def _load_track(self, glider_id: str, force: bool = False) -> Optional[Dict[str, Any]]:
        filename = f"{glider_id}_web.json"
        if filename in self.glider_jsons and not force:
            return self.glider_jsons[filename]
        if not self.has_json(glider_id):
            logger.debug(f"NetCDF store not found for {glider_id}")
            return None

        data = self._load_track_from_tracks_store(glider_id)
        if data is None:
            with _NETCDF_LOCK, self._open_dataset(glider_id) as ds:
                track_group = ds.groups["track"]
                data = self._track_data_from_group(glider_id, track_group)
                data["mission"] = str(getattr(ds, "mission", glider_id))
                data["glider_version"] = str(getattr(ds, "glider_version", ""))

                inst_parent = ds.groups.get("instruments")
                if inst_parent is not None:
                    for inst_key, inst_group in inst_parent.groups.items():
                        data[inst_key] = {"info": _safe_json_attr(inst_group, "info_json", {})}

        self.glider_jsons[filename] = data
        self._instruments_cache = None
        return data

    def load_eng(self, sn: str) -> None:
        self._load_track(str(sn))

    def load_instrument(self, sn: str, inst_key: str) -> None:
        self._load_track(str(sn))

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def glider_sns(self) -> list[str]:
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
        for glider_json in self.glider_jsons.values():
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
        for glider_json in self.glider_jsons.values():
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
        glider_id = str(glider_id)
        for filename, glider_json in self.glider_jsons.items():
            if glider_id == str(glider_json['mission']):
                return filename
        if self.has_json(glider_id):
            self._load_track(glider_id)
            return f"{glider_id}_web.json"
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
        # Dives outside every CSV range — gaps between sections, or dives after
        # the last section — inherit the previous section's number instead of
        # collapsing onto section 1. Otherwise their points join section 1's
        # polyline and the map draws straight lines across non-adjacent dives.
        # Rows are already in dive order (build_glider_df/build_uv_df), so a
        # row-wise fill is a dive-order fill; bfill covers a leading gap before
        # the first section and fillna(1) is a final safety net.
        section = pd.Series(section).ffill().bfill().fillna(1)
        df["section"] = section.to_numpy().astype(int)
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
                   if np.isfinite(divestart) and np.isfinite(diveend)
                   else None
                   for divestart, diveend in data['lat']]
        midlons = [(divestart + diveend)/2
                   if np.isfinite(divestart) and np.isfinite(diveend)
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
        return data['time'][ndive - 1][0]

    def build_instrument_df(
        self,
        glider_id: str,
        instrument_name: str,
        ndive_range: Optional[tuple[int, int]] = None,
        time_range: Optional[tuple[float, float]] = None,
        phase: Optional[str] = None,
        max_points: Optional[int] = None,
    ) -> pd.DataFrame:
        glider_id = str(glider_id)
        self._load_track(glider_id)
        instrument_key = self.instruments()[instrument_name]['key']

        flat_data: Dict[str, list] = {"divetime": [], "datetime": [], "ndive": []}
        raw_points = 0
        shown_points = 0
        stride = 1

        with _NETCDF_LOCK, self._open_dataset(glider_id) as ds:
            inst_parent = ds.groups.get("instruments")
            if inst_parent is None or instrument_key not in inst_parent.groups:
                raise KeyError(instrument_name)
            inst_group = inst_parent.groups[instrument_key]
            time_var = inst_group.variables.get("time")
            reference_key = self._instrument_reference_key(inst_group.variables)
            if time_var is None and reference_key is None:
                return pd.DataFrame()
            reference_var = time_var if time_var is not None else inst_group.variables[reference_key]
            has_sample_time = time_var is not None

            n_dive = len(ds.dimensions["dive"])
            start_dive, end_dive = ndive_range if ndive_range is not None else (1, n_dive)
            start_idx = max(0, int(start_dive) - 1)
            end_idx = min(n_dive, int(end_dive))
            if start_idx >= end_idx:
                return pd.DataFrame()

            sample_keys = [key for key in inst_group.variables if key != "time"]
            for key in sample_keys:
                flat_data[key] = []
            if not has_sample_time:
                flat_data["sample"] = []

            chunk_slices = [
                slice(i, min(i + self.PROFILE_READ_CHUNK_DIVES, end_idx))
                for i in range(start_idx, end_idx, self.PROFILE_READ_CHUNK_DIVES)
            ]

            for chunk_slice in chunk_slices:
                sample_axis = _filled(reference_var[chunk_slice, :])
                phase_arr = _filled(inst_group.variables["phase"][chunk_slice, :]) \
                    if "phase" in inst_group.variables else None
                raw_points += self._profile_raw_count(sample_axis, phase_arr=phase_arr, phase=phase)

            if max_points and raw_points > max_points:
                stride = max(2, int(np.ceil(raw_points / max_points)))

            for chunk_slice in chunk_slices:
                sample_axis = _filled(reference_var[chunk_slice, :])
                rel_time = _filled(time_var[chunk_slice, :]) if has_sample_time else None
                track_time = _filled(ds.groups["track"].variables["time"][chunk_slice, :])
                phase_arr = _filled(inst_group.variables["phase"][chunk_slice, :]) \
                    if "phase" in inst_group.variables else None
                keep_masks = self._profile_keep_masks_for_stride(
                    sample_axis,
                    phase_arr=phase_arr,
                    phase=phase,
                    stride=stride,
                )

                for row_idx, dive_idx in enumerate(range(chunk_slice.start, chunk_slice.stop)):
                    mask = keep_masks[row_idx]
                    if not mask.any():
                        continue
                    if has_sample_time:
                        times = rel_time[row_idx, mask]
                        flat_data["divetime"].extend(times.tolist())
                        t0 = track_time[row_idx, 0]
                        if np.isfinite(t0):
                            flat_data["datetime"].extend((times + t0).tolist())
                        else:
                            flat_data["datetime"].extend([None] * len(times))
                    else:
                        n_points = int(mask.sum())
                        flat_data["divetime"].extend([None] * n_points)
                        flat_data["datetime"].extend([None] * n_points)
                        flat_data["sample"].extend((np.flatnonzero(mask) + 1).tolist())
                    flat_data["ndive"].extend([dive_idx + 1] * int(mask.sum()))
                    shown_points += int(mask.sum())

                for key in sample_keys:
                    arr = _filled(inst_group.variables[key][chunk_slice, :])
                    for row_idx, mask in enumerate(keep_masks):
                        if mask.any():
                            flat_data[key].extend(arr[row_idx, mask].tolist())

        df = pd.DataFrame(flat_data)
        if df.empty:
            return df
        df['glider_sn'] = glider_id
        df['instrument'] = instrument_name

        df.attrs["raw_points"] = int(raw_points)
        df.attrs["shown_points"] = int(shown_points)
        df.attrs["decimation_stride"] = int(stride)
        df.attrs["decimated"] = bool(shown_points < raw_points)

        if time_range is not None:
            t_start, t_end = time_range
            df = df[(df['datetime'] >= t_start) & (df['datetime'] <= t_end)]

        return df

    @staticmethod
    def _instrument_reference_key(variables) -> Optional[str]:
        for key in ("time", "p", "depth", "t", "s", "theta", "fl", "oxconc", "ph"):
            if key in variables:
                return key
        for key, var in variables.items():
            if len(getattr(var, "dimensions", ())) == 2:
                return key
        return None

    @staticmethod
    def _profile_raw_count(
        rel_time: np.ndarray,
        phase_arr: Optional[np.ndarray] = None,
        phase: Optional[str] = None,
    ) -> int:
        raw_points = 0

        for row_idx in range(rel_time.shape[0]):
            mask = np.isfinite(rel_time[row_idx])
            if phase_arr is not None:
                phase_vals = phase_arr[row_idx]
                if phase == "descent":
                    mask &= phase_vals == 1
                elif phase == "ascent":
                    mask &= np.isfinite(phase_vals) & (phase_vals != 1)
            raw_points += int(mask.sum())
        return raw_points

    @staticmethod
    def _profile_keep_masks_for_stride(
        rel_time: np.ndarray,
        phase_arr: Optional[np.ndarray] = None,
        phase: Optional[str] = None,
        stride: int = 1,
    ) -> list[np.ndarray]:
        keep_masks = []

        for row_idx in range(rel_time.shape[0]):
            base_mask = np.isfinite(rel_time[row_idx])
            if phase_arr is not None:
                phase_vals = phase_arr[row_idx]
                if phase == "descent":
                    base_mask &= phase_vals == 1
                elif phase == "ascent":
                    base_mask &= np.isfinite(phase_vals) & (phase_vals != 1)

            if stride <= 1:
                keep_masks.append(base_mask)
                continue

            keep = np.zeros_like(base_mask, dtype=bool)
            idx = np.flatnonzero(base_mask)
            if phase_arr is not None and phase is None:
                down_idx = idx[phase_arr[row_idx, idx] == 1]
                up_idx = idx[phase_arr[row_idx, idx] != 1]
                groups = [down_idx, up_idx]
            else:
                groups = [idx]

            for group_idx in groups:
                if group_idx.size <= 2:
                    keep[group_idx] = True
                    continue
                keep[group_idx[0]] = True
                keep[group_idx[-1]] = True
                interior = group_idx[1:-1]
                keep[interior[::stride]] = True

            keep_masks.append(keep)

        return keep_masks

    def instrument_phase_presence(
        self,
        glider_id: str,
        instrument_name: str,
        ndive_range: Optional[tuple[int, int]] = None,
    ) -> tuple[bool, bool]:
        glider_id = str(glider_id)
        self._load_track(glider_id)
        instrument_key = self.instruments()[instrument_name]['key']

        with _NETCDF_LOCK, self._open_dataset(glider_id) as ds:
            inst_parent = ds.groups.get("instruments")
            if inst_parent is None or instrument_key not in inst_parent.groups:
                return False, False
            inst_group = inst_parent.groups[instrument_key]
            if "phase" not in inst_group.variables:
                return False, False

            n_dive = len(ds.dimensions["dive"])
            start_dive, end_dive = ndive_range if ndive_range is not None else (1, n_dive)
            start_idx = max(0, int(start_dive) - 1)
            end_idx = min(n_dive, int(end_dive))
            if start_idx >= end_idx:
                return False, False

            phase_arr = _filled(inst_group.variables["phase"][start_idx:end_idx, :])

        finite = np.isfinite(phase_arr)
        has_down = bool(np.any(finite & (phase_arr == 1)))
        has_up = bool(np.any(finite & (phase_arr != 1)))
        return has_down, has_up

    def build_eng_summary_records(self, glider_id: str) -> list[dict]:
        glider_id = str(glider_id)
        self._load_track(glider_id)
        with _NETCDF_LOCK, self._open_dataset(glider_id) as ds:
            if "eng" not in ds.groups:
                return []
            eng = ds.groups["eng"]
            track_time = _filled(ds.groups["track"].variables["time"][:, :])
            n_dive = len(ds.dimensions["dive"])

            def one_d(name: str) -> np.ndarray:
                if name not in eng.variables:
                    return np.full(n_dive, np.nan)
                return _filled(eng.variables[name][:])

            ndive = one_d("ndive")
            psurf = one_d("psurf")
            pmax = one_d("pmax")
            p = _filled(eng.variables["p"][:, :]) if "p" in eng.variables else None

        rows = []
        for i in range(n_dive):
            t_pair = track_time[i]
            if not np.isfinite(t_pair[0]):
                continue
            pmin = None
            if p is not None:
                p_vals = p[i, np.isfinite(p[i])]
                if p_vals.size:
                    pmin = float(np.nanmin(p_vals))
            nd = ndive[i] if np.isfinite(ndive[i]) else i + 1
            rows.append({
                "ndive": int(nd),
                "datetime": float(t_pair[0]),
                "psurf": float(psurf[i]) if np.isfinite(psurf[i]) else None,
                "pmax": float(pmax[i]) if np.isfinite(pmax[i]) else None,
                "pmin": pmin,
                "divetime": float((t_pair[1] - t_pair[0]) / 60.0) if np.isfinite(t_pair[1]) else None,
            })
        return rows

    def build_eng_dive(self, glider_id: str, dive_num: int) -> Optional[dict]:
        glider_id = str(glider_id)
        self._load_track(glider_id)
        dive_idx = int(dive_num) - 1
        with _NETCDF_LOCK, self._open_dataset(glider_id) as ds:
            if "eng" not in ds.groups:
                return None
            n_dive = len(ds.dimensions["dive"])
            if dive_idx < 0 or dive_idx >= n_dive:
                return None
            eng = ds.groups["eng"]
            if "time" not in eng.variables:
                return None
            x = _filled(eng.variables["time"][dive_idx, :])
            mask = np.isfinite(x)
            if not mask.any():
                return None
            track_time = _filled(ds.groups["track"].variables["time"][dive_idx, :])

            def series(name: str) -> list:
                if name not in eng.variables:
                    return [np.nan] * int(mask.sum())
                return _filled(eng.variables[name][dive_idx, :])[mask].tolist()

            return {
                "time": x[mask].tolist(),
                "p": series("p"),
                "head": series("head"),
                "pitch": series("pitch"),
                "roll": series("roll"),
                "t0": float(track_time[0]) if np.isfinite(track_time[0]) else None,
            }

    def time_range(self) -> tuple[float, float]:
        t_min, t_max = dt.datetime.now().timestamp(), 0
        for data in self.glider_jsons.values():
            if data.get('time'):
                t_min = min(data['time'][0][0], t_min)
                t_max = max(data['time'][-1][-1], t_max)
        if t_max <= t_min:
            t_max = t_min
            t_min -= 3600
        return t_min, t_max

    def instrument_in_glider(self, instrument_name: str, glider_id: str) -> bool:
        glider_id = str(glider_id)
        self._load_track(glider_id)
        instrument_key = self.INSTRUMENT_NAMES
        reverse = {v: k for k, v in instrument_key.items()}
        key = reverse.get(instrument_name)
        if key is None:
            return False
        with _NETCDF_LOCK, self._open_dataset(glider_id) as ds:
            inst_parent = ds.groups.get("instruments")
            if inst_parent is None or key not in inst_parent.groups:
                return False
            return self._instrument_reference_key(inst_parent.groups[key].variables) is not None


# ---------------------------------------------------------------------------
# Per-worker singleton with manifest-mtime version check
# ---------------------------------------------------------------------------

DEFAULT_DATA_DIR = Path(os.environ.get("DATA_DIR", "./data/sync"))
DEFAULT_NETCDF_DIR = Path(os.environ.get("NETCDF_DIR", str(DEFAULT_DATA_DIR.parent / "netcdf")))

_gdl: Optional[GliderDataLoader] = None
_gdl_version: float = 0.0


def _source_version(netcdf_dir: Path = DEFAULT_NETCDF_DIR) -> float:
    try:
        return (netcdf_dir / "manifest.json").stat().st_mtime
    except FileNotFoundError:
        return 0.0


def get_gdl(data_dir: Path = DEFAULT_DATA_DIR,
            netcdf_dir: Path = DEFAULT_NETCDF_DIR) -> GliderDataLoader:
    """Return a per-worker singleton GliderDataLoader.

    Rebuilds the loader only when data/netcdf/manifest.json mtime changes.
    """
    global _gdl, _gdl_version
    v = _source_version(netcdf_dir)
    if _gdl is None or v != _gdl_version:
        _gdl = GliderDataLoader(data_dir=data_dir, auto_load=True, netcdf_dir=netcdf_dir)
        _gdl_version = v
    return _gdl
