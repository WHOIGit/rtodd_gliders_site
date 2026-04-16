import ctypes
import gc
import json
import logging
import os
import time
import tempfile
from pathlib import Path

import ijson

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
SPLIT_DIR = DATA_DIR / "split"
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "300"))

TRACK_KEYS = {"mission", "glider_version", "time", "lat", "lon", "u", "v"}
INSTRUMENT_KEYS = {"ctd", "opt", "dox", "ph"}


from decimal import Decimal

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


def split_glider_streaming(web_json_path: Path, split_dir: Path, glider_id: str) -> dict:
    """Split a _web.json into track + eng + per-instrument files using streaming parse.

    Returns a manifest entry dict for this glider.
    """
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
                del value

            elif key in INSTRUMENT_KEYS:
                inst_filename = f"{glider_id}_{key}.json"
                atomic_write(split_dir / inst_filename, value)
                instrument_files[key] = inst_filename

                if isinstance(value, dict) and "info" in value:
                    track[key] = {"info": value["info"]}

                del value

    track_filename = f"{glider_id}_track.json"
    atomic_write(split_dir / track_filename, track)

    entry = {
        "track": track_filename,
        "source_mtime": source_mtime,
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
    import datetime as dt
    return {
        "version": dt.datetime.utcnow().isoformat(timespec="seconds"),
        "gliders": gliders,
    }


def scan_and_split(known_mtimes: dict) -> dict:
    """Check all _web.json files; split those that are new or changed.

    known_mtimes: {filename: mtime} from last scan
    Returns updated known_mtimes dict.
    """
    web_files = sorted(DATA_DIR.glob("*_web.json"))
    if not web_files:
        logger.warning(f"No *_web.json files found in {DATA_DIR}")
        return known_mtimes

    # Load existing manifest if present so we can preserve unchanged entries
    manifest_path = SPLIT_DIR / "manifest.json"
    existing_gliders: dict = {}
    if manifest_path.exists():
        try:
            existing_gliders = json.loads(manifest_path.read_text()).get("gliders", {})
        except Exception:
            existing_gliders = {}

    gliders = dict(existing_gliders)
    updated = False

    for web_path in web_files:
        try:
            sn = str(int(web_path.name.split("_")[0]))
        except ValueError:
            continue

        current_mtime = web_path.stat().st_mtime
        prev_mtime = known_mtimes.get(web_path.name)

        if prev_mtime is not None and abs(current_mtime - prev_mtime) < 0.01:
            continue  # unchanged

        try:
            entry = split_glider_streaming(web_path, SPLIT_DIR, sn)
            gliders[sn] = entry
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

    known_mtimes: dict = {}

    # Initial scan
    known_mtimes = scan_and_split(known_mtimes)
    gc.collect()
    _trim_heap()

    # Poll loop
    while True:
        time.sleep(POLL_INTERVAL)
        logger.info("Polling for changes...")
        known_mtimes = scan_and_split(known_mtimes)
        gc.collect()
        _trim_heap()


if __name__ == "__main__":
    main()