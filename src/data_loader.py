# data_loader.py
from pathlib import Path
from typing import List

import pandas as pd

DATA_DIR = Path("data")


def list_glider_files() -> List[str]:
    """Return a sorted list of CSV filenames in DATA_DIR."""
    if not DATA_DIR.exists():
        return []
    return sorted(
        f.name for f in DATA_DIR.iterdir()
        if f.is_file() and f.suffix.lower() == ".csv"
    )


def load_single_glider(filename: str) -> pd.DataFrame:
    """Load a single CSV file from DATA_DIR."""
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df["unixtime"] = df["time"].astype("int64") // 10**9  # seconds since epoch
    df["source"] = filename  # track which glider/file this row came from
    return df


def load_gliders(filenames: List[str]) -> pd.DataFrame:
    """Load and concatenate multiple glider files."""
    if not filenames:
        return pd.DataFrame()
    frames = [load_single_glider(name) for name in filenames]
    combined = pd.concat(frames, ignore_index=True)
    return combined


def get_y_columns(df: pd.DataFrame) -> list:
    """
    Return columns suitable for y-axis plots (excluding geo/time/source).
    For your glider data, this will typically be:
    depth, temperature, pressure, salinity, ...
    """
    if df.empty:
        return []
    exclude = {"time", "lat", "lon", "source", "unixtime"}
    numeric_cols = df.select_dtypes(include="number").columns
    return [c for c in numeric_cols if c not in exclude]


def get_time_bounds(df: pd.DataFrame):
    """Return (min, max) for 'time', or (0, 1) if missing/empty."""
    if df.empty or "time" not in df.columns:
        return 0, 1
    return df["unixtime"].min(), df["unixtime"].max()
