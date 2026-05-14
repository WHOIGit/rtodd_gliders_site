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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data/sync"))
SPLIT_DIR = Path(os.environ.get("SPLIT_DIR", str(DATA_DIR.parent / "splits")))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "300"))

TRACK_KEYS = {"mission", "glider_version", "time", "lat", "lon", "u", "v"}
INSTRUMENT_KEYS = {"ctd", "opt", "dox", "ph"}


def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def atomic_write(path: Path, obj: dict) -> None:
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
    track = entry.get("track")
    if not track or not (SPLIT_DIR / track).exists():
        return False

    eng = entry.get("eng")
    if eng and not (SPLIT_DIR / eng).exists():
        return False

    for fname in entry.get("instruments", {}).values():
        if not (SPLIT_DIR / fname).exists():
            return False

    return True


def load_known_mtimes_from_manifest() -> dict:
    manifest_path = SPLIT_DIR / "manifest.json"
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
            logger.info(f"Manifest entry for {glider_id} incomplete; will re-split")
            continue
        source_file = entry.get("source_file", f"{glider_id}_web.json")
        known_mtimes[source_file] = source_mtime

    logger.info(f"Loaded {len(known_mtimes)} source mtimes from manifest")
    return known_mtimes


def split_glider_streaming(web_json_path: Path, split_dir: Path, glider_id: str) -> dict:
    """Split a _web.json into track + eng + per-instrument files using streaming parse."""
    logger.info(f"Splitting {web_json_path.name}")
    source_mtime = web_json_path.stat().st_mtime

    track = {}
    eng_filename = None
    instrument_files = {}

    with web_json_path.open("rb") as f:
        for key, value in ijson.kvitems(f, "", use_float=True):
            if key in TRACK_KEYS:
                track[key] = value

            elif key == "eng":
                eng_filename = f"{glider_id}_eng.json"
                atomic_write(split_dir / eng_filename, value)

            elif key in INSTRUMENT_KEYS:
                inst_filename = f"{glider_id}_{key}.json"
                atomic_write(split_dir / inst_filename, value)
                instrument_files[key] = inst_filename

                if isinstance(value, dict) and "info" in value:
                    track[key] = {"info": value["info"]}

    track_filename = f"{glider_id}_track.json"
    atomic_write(split_dir / track_filename, track)

    entry = {
        "track": track_filename,
        "source_mtime": source_mtime,
        "source_file": web_json_path.name,
        "instruments": instrument_files,
    }
    if eng_filename:
        entry["eng"] = eng_filename

    logger.info(
        f"  -> {track_filename}, {eng_filename or '(no eng)'}, "
        f"instruments: {list(instrument_files.keys())}"
    )
    return entry


def build_manifest(gliders: dict) -> dict:
    return {
        "version": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "gliders": gliders,
    }


def scan_and_split(known_mtimes: dict) -> dict:
    web_files = sorted(DATA_DIR.glob("*_web.json"))
    if not web_files:
        logger.warning(f"No *_web.json files found in {DATA_DIR}")
        return known_mtimes

    manifest_path = SPLIT_DIR / "manifest.json"
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
            entry = split_glider_streaming(web_path, SPLIT_DIR, glider_id)
            gliders[glider_id] = entry
            known_mtimes[web_path.name] = current_mtime
            updated = True
        except Exception as e:
            logger.error(f"Failed to split {web_path.name}: {e}")

    if updated:
        atomic_write(manifest_path, build_manifest(gliders))
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
        f"SPLIT_DIR={SPLIT_DIR} POLL_INTERVAL={POLL_INTERVAL}s"
    )
    SPLIT_DIR.mkdir(parents=True, exist_ok=True)

    known_mtimes = load_known_mtimes_from_manifest()

    known_mtimes = scan_and_split(known_mtimes)
    gc.collect()
    _trim_heap()

    while True:
        time.sleep(POLL_INTERVAL)
        logger.info("Polling for changes...")
        known_mtimes = scan_and_split(known_mtimes)
        gc.collect()
        _trim_heap()


if __name__ == "__main__":
    main()
