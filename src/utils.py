import datetime as dt
import pandas as pd
import numpy as np


def range_slider_marks(t_min, t_max, target_mark_count=10):
    """
    Generate RangeSlider marks at evenly spaced full-hour intervals,
    aligned to the nearest hour, based on a target number of marks.

    Parameters:
    ----------
    df : pandas.DataFrame
        Must contain 'Datetime' and 'unixTimestamp' columns.
    target_mark_count : int
        Approximate number of marks to generate.

    Returns:
    -------
    dict
        Dictionary of {unixTimestamp: formatted datetime string}
    """
    # Sort and get min/max

    if pd.isna(t_min) or pd.isna(t_max) or t_max <= t_min:
        return {}
    t_min = dt.datetime.fromtimestamp(t_min)
    t_max = dt.datetime.fromtimestamp(t_max)
    # Round t_min up to next full hour
    t_start = (t_min + pd.Timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

    # Total range in seconds
    total_seconds = (t_max - t_start).total_seconds()
    if total_seconds <= 0:
        return {}

    # Compute spacing interval (rounded to nearest hour step)
    interval_seconds = total_seconds // target_mark_count
    interval_hours = max(1, int(round(interval_seconds / 3600)))

    # Generate evenly spaced timestamps
    timestamps = pd.date_range(start=t_start, end=t_max, freq=f'{interval_hours}h')

    # Convert to Unix timestamp and format labels
    # marks = {int(ts.timestamp()): ts.strftime('%m/%d %H:%M') for ts in timestamps}
    marks = {
        int(ts.timestamp()): {
            'label': ts.strftime('%m/%d') + '\n' + ts.strftime('%H:%M'),
            'style': {'fontSize': '12px', 'whiteSpace': 'pre'}
        }
        for ts in timestamps
    }

    return marks


def latlon_offset(lat, lon, v_dy, u_dx, scale=1):
    """
    Calculate new latitude and longitude given offsets in meters.

    Parameters:
    ----------
    lat0 : float Original latitude in degrees.
    lon0 : float Original longitude in degrees.
    dx : float Offset in meters in the east-west direction.
    dy : float Offset in meters in the north-south direction.
    scale : float|str Scaling factor for the offsets. also accepts 'm', 'km', 'miles'.
    """
    if isinstance(scale, str):
        if scale=='m' or scale.startswith('meter'):
            scale = 111139
        elif scale=='km' or scale.startswith('kilometer'):
            scale = 111.139
        elif scale.startswith('mile'):
            scale = 69.0
    else:
        scale = float(scale)

    dlat = v_dy / scale
    dlon = u_dx / (scale * np.cos(np.radians(lat)))

    # New latitude and longitude
    new_lat = lat + dlat
    new_lon = lon + dlon

    return new_lat, new_lon


