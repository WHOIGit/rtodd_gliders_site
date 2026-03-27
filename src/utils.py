import datetime as dt
import pandas as pd
import numpy as np
from pathlib import Path

import dash
from dash import html, dcc
from dash_extensions import Purify

# Shared path/URL constants for serving config assets
CONFIG_ASSETS_DIR = Path("config/assets").resolve()
CONFIG_ASSETS_URL_PREFIX = "/config-assets/"

PORTRAITS_DIR = Path("config/assets/people-imgs").resolve()
PORTRAITS_URL_PREFIX = "/config-assets/people-img/"


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


def asset_url(filename: str, url_prefix: str = "/assets/") -> str:
    """Build a URL for a served file, respecting the app's requests_pathname_prefix.

    Args:
        filename: The filename (e.g. "image.png").
        url_prefix: The URL prefix where the file is served
                    (e.g. "/assets/", "/people/img/").
    """
    app_prefix = dash.get_app().config['requests_pathname_prefix']
    return app_prefix.rstrip("/") + url_prefix + filename


def load_map_region_config(config_path):
    """
    Load map config from a YAML file (map_config.yml).

    Returns:
        default_region (str): key of the default selected region
        region_options (list[dict]): RadioItems-compatible options (enabled only)
        region_presets (dict): key -> {center, zoom} for non-auto regions
        glider_image_url (str|None): URL to serve the glider marker image
    """
    import yaml
    config_path = Path(config_path)
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    # Resolve glider_image: check src/assets/ first, then config/assets/
    glider_image_url = None
    glider_image = cfg.get("glider_image")
    if glider_image:
        assets_dir = Path(dash.get_app().config.get("assets_folder", "assets")).resolve()
        if (CONFIG_ASSETS_DIR / glider_image).exists():
            glider_image_url = asset_url(glider_image, CONFIG_ASSETS_URL_PREFIX)
        elif (assets_dir / glider_image).exists():
            glider_image_url = asset_url(glider_image, "/assets/")

    default_region = None
    region_options = []
    region_presets = {}

    for key, val in cfg.get("regions", {}).items():
        if not val.get("enabled", True):
            continue
        if val.get("default", False):
            default_region = key
        region_options.append({"label": val["label"], "value": key})
        if key != "auto":
            region_presets[key] = {
                "center": {"lat": val["center"]["lat"], "lon": val["center"]["lon"]},
                "zoom": val["zoom"],
            }

    if default_region is None:
        default_region = "auto"

    return default_region, region_options, region_presets, glider_image_url


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


def static_layout(html_file: str, title: str = None) -> html.Div:
    """
    Generic static HTML layout with optional title.

    Parameters:
    -----------
    html_file : str
        Path to HTML file (relative to current working directory).
    title : str, optional
        Optional title to display above the HTML content.

    Returns:
    --------
    html.Div
        A Dash Div containing the title (if provided) and HTML content.
    """
    html_text = (Path.cwd() / html_file).read_text(encoding="utf-8")
    children = []
    if title:
        children.append(html.H1(title))
    children.append(
        html.Div(
            Purify(html_text),
            style={"maxWidth": "800px", "margin": "0 auto"},
        )
    )
    return html.Div(children, style={"padding": "40px 20px"})
