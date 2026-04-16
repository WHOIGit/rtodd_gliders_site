"""data_watcher.py — sidecar service that splits _web.json files into per-concern files.

Scans data/*_web.json on startup, splits each into data/split/, then polls every
POLL_INTERVAL seconds for mtime changes and re-splits only changed files.

Files are written atomically (temp + rename) and manifest.json is written last so
the app never sees a partial split set.
"""
import json
import logging
import os
import time
import tempfile
from pathlib import Path

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


def atomic_write(path: Path, obj: dict) -> None:
    """Write obj as JSON to path atomically via a temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, separators=(",", ":"))
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def split_glider(web_json_path: Path, split_dir: Path) -> dict:
    """Split a _web.json into track + eng + per-instrument files.

    Returns a manifest entry dict for this glider.
    """
    logger.info(f"Splitting {web_json_path.name}")
    with web_json_path.open() as f:
        data = json.load(f)

    sn = str(int(data["mission"]))
    source_mtime = web_json_path.stat().st_mtime

    # --- Track file ---
    track = {k: data[k] for k in TRACK_KEYS if k in data}
    # Add instrument info stubs so metadata queries work without loading full data
    for inst_key in INSTRUMENT_KEYS:
        if inst_key in data and "info" in data[inst_key]:
            track[inst_key] = {"info": data[inst_key]["info"]}

    track_filename = f"{sn}_track.json"
    atomic_write(split_dir / track_filename, track)

    # --- Eng file ---
    eng_filename = None
    if "eng" in data:
        eng_filename = f"{sn}_eng.json"
        atomic_write(split_dir / eng_filename, data["eng"])

    # --- Instrument files ---
    instrument_files = {}
    for inst_key in INSTRUMENT_KEYS:
        if inst_key in data:
            inst_filename = f"{sn}_{inst_key}.json"
            atomic_write(split_dir / inst_filename, data[inst_key])
            instrument_files[inst_key] = inst_filename

    entry = {
        "track": track_filename,
        "source_mtime": source_mtime,
        "instruments": instrument_files,
    }
    if eng_filename:
        entry["eng"] = eng_filename

    logger.info(
        f"  → {track_filename}, {eng_filename or '(no eng)'}, "
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
            entry = split_glider(web_path, SPLIT_DIR)
            gliders[sn] = entry
            known_mtimes[web_path.name] = current_mtime
            updated = True
        except Exception as e:
            logger.error(f"Failed to split {web_path.name}: {e}")

    if updated:
        atomic_write(manifest_path, build_manifest(gliders))
        logger.info(f"Manifest written: {len(gliders)} gliders")

    return known_mtimes


def main():
    logger.info(f"data-watcher starting. DATA_DIR={DATA_DIR} SPLIT_DIR={SPLIT_DIR} POLL_INTERVAL={POLL_INTERVAL}s")
    SPLIT_DIR.mkdir(parents=True, exist_ok=True)

    known_mtimes: dict = {}

    # Initial scan
    known_mtimes = scan_and_split(known_mtimes)

    # Poll loop
    while True:
        time.sleep(POLL_INTERVAL)
        logger.info("Polling for changes...")
        known_mtimes = scan_and_split(known_mtimes)


if __name__ == "__main__":
    main()
