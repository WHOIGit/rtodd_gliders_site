import datetime as dt
import math
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


# Candidate step sizes (in seconds): plotly's base-60/24/7 sets × unit multipliers
_NICE_STEPS_S: list[float] = sorted(
    m * c
    for m, candidates in [
        (1,     [1, 2, 5, 10, 15, 30]),   # sub-minute
        (60,    [1, 2, 5, 10, 15, 30]),   # minutes
        (3600,  [1, 2, 3, 6, 12]),        # hours
        (86400, [1, 2, 3, 7, 14, 30]),    # days
    ]
    for c in candidates
)


def _fmt_duration(seconds: float, step_s: float) -> str:
    """Format a duration (seconds) as a human-readable string, resolution chosen by step_s."""
    s = int(round(seconds))
    if step_s < 60:
        return f"{s}s"
    elif step_s < 3600:
        m, sec = divmod(s, 60)
        return f"{m}m" if sec == 0 else f"{m}m {sec:02d}s"
    elif step_s < 86400:
        h, rem = divmod(s, 3600)
        m = rem // 60
        return f"{h}h" if m == 0 else f"{h}h {m:02d}m"
    else:
        d, rem = divmod(s, 86400)
        h = rem // 3600
        return f"{d}d" if h == 0 else f"{d}d {h:02d}h"


def _fmt_datetime_tick(unix_s: float, step_s: float) -> str:
    """Format a unix timestamp as a human-readable string, resolution chosen by step_s."""
    ts = pd.Timestamp(unix_s, unit="s", tz="UTC")
    if step_s < 86400:
        return ts.strftime("%Y-%m-%d<br>%H:%M")
    else:
        return ts.strftime("%Y-%m-%d")


def time_ticks(
    t_min,
    t_max,
    fmt: str = "s",
    n_min: int = 4,
    n_max: int = 8,
) -> tuple[list, list]:
    """Generate human-readable time tick positions and labels.

    Ticks fall on rounded time boundaries (whole minutes, hours, days, etc.)
    and are formatted to match the scale of the interval.

    Parameters
    ----------
    t_min, t_max : numeric
        Range of the time axis, in units given by ``fmt``.
    fmt : str
        Units of t_min/t_max:
        - ``"s"``        — seconds (relative duration, e.g. divetime)
        - ``"ms"``       — milliseconds (relative duration)
        - ``"min"``      — minutes (relative duration)
        - ``"datetime"`` — unix timestamp in seconds (absolute time, UTC)
    n_min, n_max : int
        Desired range for number of ticks returned.

    Returns
    -------
    tickvals : list
        Tick positions in the same units as t_min/t_max.
    ticktext : list[str]
        Human-readable label for each tick.
    """
    # Convert to seconds internally
    if fmt == "ms":
        scale = 1 / 1000
    elif fmt == "min":
        scale = 60.0
    else:  # "s" or "datetime"
        scale = 1.0

    t_min_s = float(t_min) * scale
    t_max_s = float(t_max) * scale
    span_s = t_max_s - t_min_s

    if span_s <= 0:
        return [], []

    # Pick the coarsest step that still gives >= n_min ticks; fall back to finest if needed
    step_s = _NICE_STEPS_S[0]
    for candidate in _NICE_STEPS_S:
        n = span_s / candidate
        if n < n_min:
            break
        step_s = candidate
        if n <= n_max:
            break

    # Generate ticks aligned to step boundaries (UTC epoch is already midnight-aligned)
    first = math.ceil(t_min_s / step_s) * step_s
    last = math.floor(t_max_s / step_s) * step_s
    ticks_s = np.arange(first, last + step_s * 0.01, step_s)

    if len(ticks_s) == 0:
        return [], []

    # Convert back to input units and format labels
    tickvals = (ticks_s / scale).tolist()
    if fmt == "datetime":
        ticktext = [_fmt_datetime_tick(v, step_s) for v in ticks_s]
    else:
        ticktext = [_fmt_duration(v, step_s) for v in ticks_s]

    return tickvals, ticktext


def asset_url(filename: str, url_prefix: str = "/assets/") -> str:
    """Build a URL for a served file, respecting the app's requests_pathname_prefix.

    Args:
        filename: The filename (e.g. "image.png").
        url_prefix: The URL prefix where the file is served
                    (e.g. "/assets/", "/people/img/").
    """
    app_prefix = dash.get_app().config['requests_pathname_prefix']
    return app_prefix.rstrip("/") + url_prefix + filename


def load_region_labels(config_path) -> dict[str, str]:
    """Map region key -> human label, e.g. 'gulfstream' -> 'Gulf Stream'."""
    import yaml
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    return {k: v.get("label", k) for k, v in cfg.get("regions", {}).items()}


def load_map_region_config(config_path, active_regions=None):
    """
    Load map config from a YAML file (map_config.yml).

    Each region has an `enable` field:
      - true: include
      - false: skip
      - "if-has-gliders": include only if region_key is in active_regions
        (not honored for auto/global — those are always included)

    Args:
        config_path: path to map_config.yml
        active_regions: optional set of region keys with at least one active glider

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

    glider_image_url = None
    glider_image = cfg.get("glider_image")
    if glider_image:
        assets_dir = Path(dash.get_app().config.get("assets_folder", "assets")).resolve()
        if (CONFIG_ASSETS_DIR / glider_image).exists():
            glider_image_url = asset_url(glider_image, CONFIG_ASSETS_URL_PREFIX)
        elif (assets_dir / glider_image).exists():
            glider_image_url = asset_url(glider_image, "/assets/")

    active_regions = set(active_regions or [])
    default_region = None
    region_options = []
    region_presets = {}

    for key, val in cfg.get("regions", {}).items():
        enable = val.get("enable", True)
        if key in ("auto", "global"):
            if enable != True:
                import logging
                logging.getLogger(__name__).warning(
                    f"region {key!r} has enable={enable!r}; forcing enabled"
                )
            include = True
        elif enable is True:
            include = True
        elif enable is False:
            include = False
        elif enable == "if-has-gliders":
            include = key in active_regions
        else:
            import logging
            logging.getLogger(__name__).warning(
                f"region {key!r} has unrecognized enable={enable!r}; treating as false"
            )
            include = False

        if not include:
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


def static_layout(html_file: str, title: str = None, subst: dict[str, str] | None = None) -> html.Div:
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
    if subst:
        for key, value in subst.items():
            html_text = html_text.replace("{" + key + "}", value)
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
