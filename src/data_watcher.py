import ctypes
import gc
import json
import logging
import os
import tempfile
import time
from decimal import Decimal
from pathlib import Path
import datetime as dt

import ijson
import numpy as np
from netCDF4 import Dataset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data/sync"))
NETCDF_DIR = Path(os.environ.get("NETCDF_DIR", str(DATA_DIR.parent / "netcdf")))
TRACKS_NETCDF = os.environ.get("TRACKS_NETCDF", "tracks.nc")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "300"))

TRACK_KEYS = {"mission", "glider_version", "time", "lat", "lon", "u", "v"}
TRACK_PAIR_KEYS = {"time", "lat", "lon"}
INSTRUMENT_KEYS = {"ctd", "opt", "dox", "ph", "adcp"}
COMPRESSION = dict(zlib=True, shuffle=True, complevel=4)
TRACKS_SCHEMA_VERSION = "gliderapp-tracks-v1"


def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _filled(value) -> np.ndarray:
    return np.asarray(np.ma.filled(value, np.nan), dtype="float64")


def atomic_write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, separators=(",", ":"), default=_json_default)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def manifest_entry_complete(entry: dict) -> bool:
    store = entry.get("store")
    return bool(store and (NETCDF_DIR / store).exists())


def tracks_store_complete(gliders: dict) -> bool:
    path = NETCDF_DIR / TRACKS_NETCDF
    if not path.exists():
        return False

    expected = {
        str(glider_id): entry.get("source_mtime")
        for glider_id, entry in gliders.items()
        if manifest_entry_complete(entry)
    }

    try:
        with Dataset(path, "r") as ds:
            if getattr(ds, "schema_version", "") != TRACKS_SCHEMA_VERSION:
                return False
            tracks = ds.groups.get("tracks")
            if tracks is None:
                return False
            found = {}
            for group in tracks.groups.values():
                glider_id = str(getattr(group, "glider_id", ""))
                found[glider_id] = getattr(group, "source_mtime", None)
    except Exception as e:
        logger.warning(f"Failed to inspect tracks NetCDF {path}: {e}")
        return False

    if set(found) != set(expected):
        return False
    for glider_id, source_mtime in expected.items():
        if source_mtime is None:
            continue
        found_mtime = found.get(glider_id)
        if found_mtime is None or abs(float(found_mtime) - float(source_mtime)) >= 0.01:
            return False
    return True


def load_known_mtimes_from_manifest() -> dict:
    manifest_path = NETCDF_DIR / "manifest.json"
    if not manifest_path.exists():
        return {}

    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as e:
        logger.warning(f"Failed to read existing manifest: {e}")
        return {}

    known_mtimes = {}
    for glider_id, entry in manifest.get("gliders", {}).items():
        source_mtime = entry.get("source_mtime")
        if source_mtime is None:
            continue
        if not manifest_entry_complete(entry):
            logger.info(f"Manifest entry for {glider_id} incomplete; will rebuild NetCDF")
            continue
        source_file = entry.get("source_file", f"{glider_id}_web.json")
        known_mtimes[source_file] = source_mtime

    logger.info(f"Loaded {len(known_mtimes)} source mtimes from manifest")
    return known_mtimes


def _as_float_array(values, shape: tuple[int, ...] | None = None) -> np.ndarray:
    arr = np.asarray(values, dtype="float64")
    if shape is not None:
        out = np.full(shape, np.nan, dtype="float64")
        slices = tuple(slice(0, min(a, b)) for a, b in zip(arr.shape, out.shape))
        out[slices] = arr[slices]
        return out
    return arr


def _padded_2d(segments: list, n_dive: int) -> np.ndarray:
    max_len = 1
    for segment in segments:
        if isinstance(segment, list):
            max_len = max(max_len, len(segment))

    arr = np.full((n_dive, max_len), np.nan, dtype="float64")
    for i, segment in enumerate(segments[:n_dive]):
        if not isinstance(segment, list) or not segment:
            continue
        vals = np.asarray(segment, dtype="float64")
        arr[i, :len(vals)] = vals
    return arr


def _chunk_shape(arr: np.ndarray) -> tuple[int, ...]:
    if arr.ndim == 1:
        return (min(max(arr.shape[0], 1), 1024),)
    if arr.ndim == 2:
        return (min(max(arr.shape[0], 1), 16), max(arr.shape[1], 1))
    return arr.shape


def _create_float_var(group, name: str, dimensions: tuple[str, ...], arr: np.ndarray):
    kwargs = dict(fill_value=np.nan)
    if arr.size:
        kwargs.update(COMPRESSION)
        kwargs["chunksizes"] = _chunk_shape(arr)
    var = group.createVariable(name, "f8", dimensions, **kwargs)
    var[:] = arr
    return var


def _apply_info_attrs(var, info: dict | None) -> None:
    if not isinstance(info, dict):
        return
    for attr_key, attr_value in info.items():
        if attr_value is None:
            continue
        safe_key = "units" if attr_key == "unit" else attr_key
        try:
            setattr(var, safe_key, str(attr_value))
        except Exception:
            pass
    if "name" in info and not hasattr(var, "long_name"):
        var.long_name = str(info["name"])
    if "unit" in info and not hasattr(var, "units"):
        var.units = str(info["unit"])


def _write_track(ds: Dataset, track: dict, n_dive: int) -> None:
    group = ds.createGroup("track")
    ds.createDimension("pair", 2)

    for key in ("time", "lat", "lon"):
        arr = _as_float_array(track.get(key, []), shape=(n_dive, 2))
        _create_float_var(group, key, ("dive", "pair"), arr)

    for key in ("u", "v"):
        arr = _as_float_array(track.get(key, []), shape=(n_dive,))
        _create_float_var(group, key, ("dive",), arr)


def _write_instrument(parent, inst_key: str, inst_data: dict, n_dive: int) -> None:
    group = parent.createGroup(inst_key)
    info = inst_data.get("info", {}) if isinstance(inst_data, dict) else {}
    group.info_json = json.dumps(info, separators=(",", ":"), default=_json_default)

    sample_keys = [
        key for key, value in inst_data.items()
        if key not in {"info", "ndive"} and isinstance(value, list)
    ]
    max_len = 1
    for key in sample_keys:
        for segment in inst_data.get(key, []):
            if isinstance(segment, list):
                max_len = max(max_len, len(segment))

    dim_name = f"{inst_key}_sample"
    parent.parent.createDimension(dim_name, max_len)

    for key in sample_keys:
        arr = _padded_2d(inst_data.get(key, []), n_dive)
        if arr.shape[1] != max_len:
            padded = np.full((n_dive, max_len), np.nan, dtype="float64")
            padded[:, :arr.shape[1]] = arr
            arr = padded
        var = _create_float_var(group, key, ("dive", dim_name), arr)
        _apply_info_attrs(var, info.get(key))


def _write_eng(ds: Dataset, eng_data: dict, n_dive: int) -> None:
    group = ds.createGroup("eng")
    info = eng_data.get("info", {}) if isinstance(eng_data, dict) else {}
    group.info_json = json.dumps(info, separators=(",", ":"), default=_json_default)

    summary_keys = []
    sample_keys = []
    for key, value in eng_data.items():
        if key == "info" or not isinstance(value, list):
            continue
        if value and isinstance(value[0], list):
            sample_keys.append(key)
        else:
            summary_keys.append(key)

    for key in summary_keys:
        arr = _as_float_array(eng_data.get(key, []), shape=(n_dive,))
        var = _create_float_var(group, key, ("dive",), arr)
        _apply_info_attrs(var, info.get(key))

    max_len = 1
    for key in sample_keys:
        for segment in eng_data.get(key, []):
            if isinstance(segment, list):
                max_len = max(max_len, len(segment))
    ds.createDimension("eng_sample", max_len)

    for key in sample_keys:
        arr = _padded_2d(eng_data.get(key, []), n_dive)
        if arr.shape[1] != max_len:
            padded = np.full((n_dive, max_len), np.nan, dtype="float64")
            padded[:, :arr.shape[1]] = arr
            arr = padded
        var = _create_float_var(group, key, ("dive", "eng_sample"), arr)
        _apply_info_attrs(var, info.get(key))


def write_glider_netcdf(web_json_path: Path, netcdf_dir: Path, glider_id: str) -> dict:
    """Convert one _web.json file into one compressed NetCDF4 file."""
    logger.info(f"Writing NetCDF for {web_json_path.name}")
    source_mtime = web_json_path.stat().st_mtime
    source_size = web_json_path.stat().st_size

    track: dict = {}
    pending_blocks: list[tuple[str, dict]] = []
    instruments_written: list[str] = []
    has_eng = False
    n_dive: int | None = None
    store_filename = f"{glider_id}.nc"
    netcdf_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=netcdf_dir, suffix=".nc.tmp")
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        with Dataset(tmp_path, "w", format="NETCDF4") as ds:
            ds.schema_version = "gliderapp-netcdf-v1"
            ds.source_file = web_json_path.name
            ds.source_mtime = source_mtime
            ds.source_size = source_size
            ds.created = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            inst_parent = ds.createGroup("instruments")

            def ensure_dive_dimension() -> int:
                nonlocal n_dive
                if n_dive is None:
                    n_dive = len(track.get("time", []))
                    ds.createDimension("dive", n_dive)
                return n_dive

            def write_block(block_key: str, block_value: dict) -> None:
                nonlocal has_eng
                current_n_dive = ensure_dive_dimension()
                if block_key == "eng":
                    _write_eng(ds, block_value, current_n_dive)
                    has_eng = True
                else:
                    _write_instrument(inst_parent, block_key, block_value, current_n_dive)
                    instruments_written.append(block_key)

            with web_json_path.open("rb") as f:
                for key, value in ijson.kvitems(f, "", use_float=True):
                    if key in TRACK_KEYS:
                        track[key] = value
                    elif key == "eng" or key in INSTRUMENT_KEYS:
                        if "time" not in track:
                            pending_blocks.append((key, value))
                        else:
                            write_block(key, value)

            ensure_dive_dimension()
            for key, value in pending_blocks:
                write_block(key, value)
            _write_track(ds, track, n_dive)
            ds.mission = str(track.get("mission", glider_id))
            ds.glider_version = str(track.get("glider_version", ""))

        os.replace(tmp_path, netcdf_dir / store_filename)
    except Exception:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise

    entry = {
        "store": store_filename,
        "store_format": "netcdf4",
        "schema_version": "gliderapp-netcdf-v1",
        "source_mtime": source_mtime,
        "source_file": web_json_path.name,
        "source_size": source_size,
        "ndive": n_dive,
        "instruments": sorted(instruments_written),
        "has_eng": has_eng,
    }
    logger.info(f"  -> {store_filename} ({n_dive} dives, instruments: {entry['instruments']})")
    return entry


def _track_group_name(glider_id: str, used: set[str]) -> str:
    base = "g_" + "".join(c if c.isalnum() else "_" for c in str(glider_id))
    name = base
    i = 2
    while name in used:
        name = f"{base}_{i}"
        i += 1
    used.add(name)
    return name


def _copy_track_var(dst_group, src_var, name: str, dimensions: tuple[str, ...]) -> None:
    var = _create_float_var(dst_group, name, dimensions, _filled(src_var[:]))
    for attr in src_var.ncattrs():
        try:
            setattr(var, attr, getattr(src_var, attr))
        except Exception:
            pass


def write_tracks_netcdf(gliders: dict, netcdf_dir: Path) -> None:
    """Write duplicated track data for all gliders into one map-friendly NetCDF."""
    logger.info(f"Writing tracks NetCDF: {TRACKS_NETCDF}")
    netcdf_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=netcdf_dir, suffix=".tracks.nc.tmp")
    os.close(fd)
    tmp_path = Path(tmp)
    used_group_names: set[str] = set()
    written = 0

    try:
        with Dataset(tmp_path, "w", format="NETCDF4") as ds:
            ds.schema_version = TRACKS_SCHEMA_VERSION
            ds.created = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            ds.createDimension("pair", 2)
            tracks_group = ds.createGroup("tracks")

            for glider_id, entry in sorted(gliders.items()):
                store = entry.get("store")
                if not store:
                    continue
                store_path = netcdf_dir / store
                if not store_path.exists():
                    logger.warning(f"Skipping {glider_id} in tracks NetCDF; missing {store}")
                    continue

                with Dataset(store_path, "r") as src:
                    src_track = src.groups.get("track")
                    if src_track is None:
                        logger.warning(f"Skipping {glider_id} in tracks NetCDF; no track group")
                        continue

                    group_name = _track_group_name(str(glider_id), used_group_names)
                    dst = tracks_group.createGroup(group_name)
                    dst.createDimension("dive", len(src.dimensions["dive"]))
                    dst.glider_id = str(glider_id)
                    dst.mission = str(getattr(src, "mission", glider_id))
                    dst.glider_version = str(getattr(src, "glider_version", ""))
                    dst.source_file = str(entry.get("source_file", f"{glider_id}_web.json"))
                    dst.store = str(store)
                    if entry.get("source_mtime") is not None:
                        dst.source_mtime = float(entry["source_mtime"])
                    if entry.get("source_size") is not None:
                        dst.source_size = int(entry["source_size"])

                    for key in ("time", "lat", "lon"):
                        if key in src_track.variables:
                            _copy_track_var(dst, src_track.variables[key], key, ("dive", "pair"))
                    for key in ("u", "v"):
                        if key in src_track.variables:
                            _copy_track_var(dst, src_track.variables[key], key, ("dive",))

                    src_inst_parent = src.groups.get("instruments")
                    if src_inst_parent is not None:
                        dst_inst_parent = dst.createGroup("instruments")
                        for inst_key, src_inst in src_inst_parent.groups.items():
                            dst_inst = dst_inst_parent.createGroup(inst_key)
                            if "info_json" in src_inst.ncattrs():
                                dst_inst.info_json = getattr(src_inst, "info_json")

                    written += 1

        os.replace(tmp_path, netcdf_dir / TRACKS_NETCDF)
    except Exception:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise

    logger.info(f"  -> {TRACKS_NETCDF} ({written} gliders)")


def build_manifest(gliders: dict) -> dict:
    return {
        "version": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "schema_version": "gliderapp-netcdf-v1",
        "tracks_store": TRACKS_NETCDF,
        "tracks_schema_version": TRACKS_SCHEMA_VERSION,
        "gliders": gliders,
    }


def scan_and_convert(known_mtimes: dict) -> dict:
    web_files = sorted(DATA_DIR.glob("*_web.json"))
    if not web_files:
        logger.warning(f"No *_web.json files found in {DATA_DIR}")
        return known_mtimes

    manifest_path = NETCDF_DIR / "manifest.json"
    existing_gliders: dict = {}
    if manifest_path.exists():
        try:
            existing_gliders = json.loads(manifest_path.read_text()).get("gliders", {})
        except Exception:
            existing_gliders = {}

    gliders = dict(existing_gliders)
    updated = False

    current_ids = {web_path.name[:-9] for web_path in web_files}
    for glider_id in list(gliders):
        if glider_id not in current_ids:
            logger.info(f"Removing missing source from manifest: {glider_id}")
            gliders.pop(glider_id, None)
            updated = True

    for web_path in web_files:
        glider_id = web_path.name[:-9]  # strip "_web.json"
        current_mtime = web_path.stat().st_mtime
        prev_mtime = known_mtimes.get(web_path.name)

        if prev_mtime is not None and abs(current_mtime - prev_mtime) < 0.01:
            continue

        try:
            entry = write_glider_netcdf(web_path, NETCDF_DIR, glider_id)
            gliders[glider_id] = entry
            known_mtimes[web_path.name] = current_mtime
            updated = True
        except Exception as e:
            logger.error(f"Failed to convert {web_path.name}: {e}")

    tracks_updated = updated or not tracks_store_complete(gliders)
    if tracks_updated:
        try:
            write_tracks_netcdf(gliders, NETCDF_DIR)
        except Exception as e:
            logger.error(f"Failed to write tracks NetCDF: {e}")

    if updated or tracks_updated:
        atomic_write_json(manifest_path, build_manifest(gliders))
        logger.info(f"Manifest written: {len(gliders)} gliders")

    return known_mtimes


try:
    _libc = ctypes.CDLL("libc.so.6")

    def _trim_heap() -> None:
        _libc.malloc_trim(0)

except OSError:
    def _trim_heap() -> None:
        pass


def main():
    logger.info(
        f"data-watcher starting. DATA_DIR={DATA_DIR} "
        f"NETCDF_DIR={NETCDF_DIR} TRACKS_NETCDF={TRACKS_NETCDF} "
        f"POLL_INTERVAL={POLL_INTERVAL}s"
    )
    NETCDF_DIR.mkdir(parents=True, exist_ok=True)

    known_mtimes = load_known_mtimes_from_manifest()

    known_mtimes = scan_and_convert(known_mtimes)
    gc.collect()
    _trim_heap()

    while True:
        time.sleep(POLL_INTERVAL)
        logger.info("Polling for changes...")
        known_mtimes = scan_and_convert(known_mtimes)
        gc.collect()
        _trim_heap()


if __name__ == "__main__":
    main()
