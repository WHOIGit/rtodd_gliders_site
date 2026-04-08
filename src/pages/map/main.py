from itertools import cycle
import logging
import threading
import time
import datetime as dt
from pathlib import Path

logger = logging.getLogger(__name__)

import dash
from dash import Input, Output, State, no_update, html, clientside_callback, ALL
import numpy as np

import dash_leaflet as dl
import pandas as pd

# Dash pages expects a `layout` variable in the module
from dash.exceptions import PreventUpdate

from data_loader import GliderDataLoader
from utils import latlon_offset, load_map_region_config
from .layout import layout, TILE_URL
from names import *
from .names import *

# Register this file as a Dash "page"
dash.register_page(
    __name__,
    path="/plotting/realtime",          # URL path
    name="Realtime Map",          # Text shown in navbar (via page["name"])
    title="Gliders - Realtime Map", # <title> of the browser tab
)

app = dash.get_app()


# ── Mobile overlay toggle ──

@app.callback(
    Output(ContainerIds.MAP_OVERLAY, "className"),
    Output(ContainerIds.MAP_OVERLAY_TOGGLE, "children"),
    Input(ContainerIds.MAP_OVERLAY_TOGGLE, "n_clicks"),
    State(ContainerIds.MAP_OVERLAY, "className"),
    prevent_initial_call=True,
)
def toggle_map_overlay(n_clicks, current_class):
    current_class = current_class or ""
    if "collapsed" in current_class:
        return "map-overlay", "✕"
    return "map-overlay collapsed", "≡"


# ── Loading overlay: hide when map children has data layers ──

clientside_callback(
    """
    function(children, currentClass) {
        if (currentClass && currentClass.includes('hidden')) {
            return window.dash_clientside.no_update;
        }
        // children[0] is TileLayer, [1] is ZoomControl; data layers come after
        if (!children || children.length <= 2) {
            return 'map-loading-overlay';
        }
        return 'map-loading-overlay hidden';
    }
    """,
    Output(ContainerIds.MAP_LOADING_OVERLAY, "className"),
    Input(MapIds.MAP, "children"),
    State(ContainerIds.MAP_LOADING_OVERLAY, "className"),
)


def _date_to_epoch_start(date_str):
    # date_str: "YYYY-MM-DD" -> epoch at 00:00:00 UTC
    d = dt.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp())

def _date_to_epoch_end(date_str):
    # epoch at 23:59:59 UTC
    d = dt.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    d = d + dt.timedelta(days=1) - dt.timedelta(seconds=1)
    return int(d.timestamp())

@app.callback(
    Output(StoreIds.TIMERANGE_STORE, "data"),
    Output(StoreIds.TIMEBTN_ACTIVE_STORE, "data"),
    Input(ControlIds.TIME_BTN_DAY, "n_clicks"),
    Input(ControlIds.TIME_BTN_WEEK, "n_clicks"),
    Input(ControlIds.TIME_BTN_MONTH, "n_clicks"),
    Input(ControlIds.TIME_BTN_ALL, "n_clicks"),
    Input(ControlIds.TIME_BTN_X, "n_clicks"),
    Input(ControlIds.TIME_RANGE_PICKER, "start_date"),
    Input(ControlIds.TIME_RANGE_PICKER, "end_date"),
    prevent_initial_call=True,
)
def update_timerange_store(
    day, week, month, all_, custom_btn,
    start_date, end_date,
):
    trig = dash.ctx.triggered_id
    now = end = int(time.time())
    start = 0

    if trig == ControlIds.TIME_BTN_DAY:
        start = now - 1 * 24 * 3600

    elif trig == ControlIds.TIME_BTN_WEEK:
        start = now - 7 * 24 * 3600

    elif trig == ControlIds.TIME_BTN_MONTH:
        start = now - 30 * 24 * 3600

    elif trig == ControlIds.TIME_BTN_X:
        if not start_date:
            return no_update, ControlIds.TIME_BTN_X
        start = _date_to_epoch_start(start_date)
        end = _date_to_epoch_end(end_date) if end_date else now

    elif trig == ControlIds.TIME_RANGE_PICKER:
        if not start_date:
            return no_update, no_update
        start = _date_to_epoch_start(start_date)
        end = _date_to_epoch_end(end_date) if end_date else now
        return [start, end], ControlIds.TIME_BTN_X

    else: # trig == ControlIds.TIME_BTN_ALL
        return None, trig

    return [start, end], trig



@app.callback(
    Output(ControlIds.TIME_BTN_DAY, "outline"),
    Output(ControlIds.TIME_BTN_WEEK, "outline"),
    Output(ControlIds.TIME_BTN_MONTH, "outline"),
    Output(ControlIds.TIME_BTN_ALL, "outline"),
    Output(ControlIds.TIME_BTN_X, "outline"),
    Input(StoreIds.TIMEBTN_ACTIVE_STORE, "data"),
)
def set_active_time_button(active_btn_id):
    def inactive(btn_id):
        return active_btn_id != btn_id

    return (
        inactive(ControlIds.TIME_BTN_DAY),
        inactive(ControlIds.TIME_BTN_WEEK),
        inactive(ControlIds.TIME_BTN_MONTH),
        inactive(ControlIds.TIME_BTN_ALL),
        inactive(ControlIds.TIME_BTN_X),
    )


def rgb_to_hex(r:int, g:int, b:int, a=None):
    if a is None:
        return "#{:02X}{:02X}{:02X}".format(
            int(r), int(g), int(b) )
    else:
        return "#{:02X}{:02X}{:02X}{:02X}".format(
            int(r), int(g), int(b), int(a * 255))


_, _, REGION_PRESETS, _GLIDER_IMAGE_URL = load_map_region_config(Path("config/map_config.yml").resolve())

GLIDER_ICON = dict(
    iconUrl=_GLIDER_IMAGE_URL or "SprayGliderTail.png",
    iconSize=[40, 40],
    iconAnchor=[20, 20],
)


def _build_map_children(latlon_records, uv_records, time_range, uv_scale, region_key):
    """Build dash-leaflet children, bounds, and legend for the map.

    Returns (children, bounds, legend_children) where:
      children: list of dl components (Polyline, Marker, LayerGroup)
      bounds: [[south, west], [north, east]] or None
      legend_items: list of (glider_sn, color_hex) for legend
    """
    COLOR_CYCLE = cycle([
        ( 31, 119, 180), # blue
        (255, 127,  14), # orange
        ( 44, 160,  44), # green
        (214,  39,  40), # red
        (148, 103, 189), # purple
        (140,  86,  75), # brown
    ])

    children = []
    legend_items = []
    maxlat, minlat, maxlon, minlon = -180, 180, -180, 180

    for glider_sn, records in latlon_records.items():
        color_rgb = next(COLOR_CYCLE)
        color_hex = rgb_to_hex(*color_rgb)

        df = pd.DataFrame(records)
        df['dt'] = df.time.apply(lambda x: pd.NaT if np.isnan(x) else dt.datetime.utcfromtimestamp(x/1))
        if df.empty or not {"lat", "lon"}.issubset(df.columns):
            continue
        df = df.dropna(subset=["lat", "lon"])

        num_of_sections = len(set(df.section))
        opacities = np.linspace(0.2, 1, num_of_sections) if num_of_sections > 1 else [1.0]

        # filter by time range if available
        if time_range and "time" in df.columns:
            start, end = time_range
            df = df[(df["time"] >= start) & (df["time"] <= end)]

        if df.empty:
            continue

        legend_items.append((glider_sn, color_hex))

        # set map bounds
        minlat = min(minlat, float(df["lat"].min()))
        maxlat = max(maxlat, float(df["lat"].max()))
        minlon = min(minlon, float(df["lon"].min()))
        maxlon = max(maxlon, float(df["lon"].max()))

        for section, df_sec in df.groupby("section", sort=False):
            opacity = float(opacities[section-1])
            positions = list(zip(
                df_sec["lat"].tolist(),
                df_sec["lon"].tolist(),
            ))

            if len(positions) < 2:
                continue

            children.append(
                dl.Polyline(
                    positions=positions,
                    color=color_hex,
                    opacity=opacity,
                    weight=3,
                    id={"type": "track-segment", "index": f"{glider_sn}-{section}"},
                    children=dl.Tooltip(
                        html.Div([
                            html.B(f"Spray {glider_sn}"),
                            html.Br(),
                            f"Section {section}",
                        ]),
                    ),
                )
            )

        # add u,v vectors if available
        if uv_records and glider_sn in uv_records:
            uv_recs = uv_records[glider_sn]
            df_uv = pd.DataFrame(uv_recs)
            df_uv = df_uv.dropna(subset=["lat", "lon", "u", "v"])

            if time_range and "time" in df_uv.columns:
                start, end = time_range
                df_uv = df_uv[(df_uv["time"] >= start) & (df_uv["time"] <= end)]

            uv_lines = []
            for section, df_uv_sec in df_uv.groupby("section", sort=False):
                opacity = float(opacities[section - 1])

                for _, row in df_uv_sec.iterrows():
                    lat, lon = row["lat"], row["lon"]
                    vlat, ulon = latlon_offset(lat, lon, row["v"], row["u"], uv_scale)
                    uv_lines.append(
                        dl.Polyline(
                            positions=[[lat, lon], [vlat, ulon]],
                            color=color_hex,
                            opacity=opacity,
                            weight=1,
                            interactive=False,
                        )
                    )

            if uv_lines:
                children.append(dl.LayerGroup(children=uv_lines))

        # endpoint marker with custom icon
        end_row = df.iloc[-1]
        end_date_str = str(end_row["dt"].date()) if pd.notna(end_row["dt"]) else "N/A"
        end_time_str = str(end_row["dt"].time()) if pd.notna(end_row["dt"]) else "N/A"
        end_section = end_row.get("section", "N/A")
        end_ndive = end_row.get("ndive", "N/A")

        children.append(
            dl.Marker(
                position=[float(end_row["lat"]), float(end_row["lon"])],
                icon=GLIDER_ICON,
                id={"type": "glider-endpoint", "index": str(glider_sn)},
                children=dl.Tooltip(
                    html.Div([
                        html.B(f"Spray {glider_sn}"),
                        html.Br(),
                        f"Lat: {end_row['lat']:.4f}, Lon: {end_row['lon']:.4f}",
                        html.Br(),
                        f"Date: {end_date_str} {end_time_str}",
                        html.Br(),
                        f"Section: {end_section}, Dive: {end_ndive}",
                    ]),
                ),
            )
        )

    if not children:
        return [], None, []

    bounds = [[minlat, minlon], [maxlat, maxlon]]
    return children, bounds, legend_items


def _viewport_for_bounds(bounds):
    """Create a viewport dict that fits the given bounds with padding."""
    return {"bounds": bounds, "transition": "fitBounds"}


def _viewport_for_preset(region_key):
    """Create a viewport dict for a named region preset."""
    preset = REGION_PRESETS.get(region_key, REGION_PRESETS["global"])
    return {
        "center": [preset["center"]["lat"], preset["center"]["lon"]],
        "zoom": preset["zoom"],
        "transition": "flyTo",
    }


@app.callback(
    Output(MapIds.MAP, "children"),
    Output(MapIds.MAP, "viewport"),
    Output(AlertIds.BANNER, "is_open"),
    Output(AlertIds.BANNER, "children"),
    Input(StoreIds.MAPDATA_STORE, "data"),
    Input(StoreIds.TIMERANGE_STORE, "data"),
    Input(ControlIds.UV_SCALE, "value"),
    Input(ControlIds.REGION_SELECT, "value"),
    prevent_initial_call=False,
)
def update_map(store_data, time_range, uv_scale, region_key):
    store_data = store_data or {}
    latlon_records = store_data.get("latlon_records", {})
    uv_records = store_data.get("uv_records", {})

    tile = dl.TileLayer(url=TILE_URL)
    zoom_ctrl = dl.ZoomControl(position="bottomright")

    if not latlon_records:
        vp = _viewport_for_preset(region_key) if region_key != 'auto' else no_update
        return [tile, zoom_ctrl], vp, False, ""

    data_children, bounds, _ = _build_map_children(
        latlon_records, uv_records, time_range, uv_scale, region_key
    )

    if not data_children:
        # No data for this time range — try shifting to last available data
        if time_range:
            start, end = time_range
            window = end - start
            last_ts = max(
                r["time"] for records in latlon_records.values()
                for r in records if r.get("time") is not None and not np.isnan(r["time"])
            )
            shifted_range = [last_ts - window, last_ts]
            data_children, bounds, _ = _build_map_children(
                latlon_records, uv_records, shifted_range, uv_scale, region_key
            )
            if data_children:
                last_dt = dt.datetime.utcfromtimestamp(last_ts).strftime("%Y-%m-%d")
                all_children = [tile, zoom_ctrl] + data_children
                vp = _viewport_for_bounds(bounds) if region_key == 'auto' else _viewport_for_preset(region_key)
                return all_children, vp, True, \
                    f"No data found for the selected time range. Showing the same time window ending at the last available data ({last_dt})."

        vp = _viewport_for_preset(region_key) if region_key != 'auto' else no_update
        return [tile, zoom_ctrl], vp, False, ""

    all_children = [tile, zoom_ctrl] + data_children

    if region_key == 'auto':
        return all_children, _viewport_for_bounds(bounds), False, ""
    else:
        return all_children, _viewport_for_preset(region_key), False, ""


_mapdata_cache: dict = {"version": None, "data": None}

DATA_RELOAD_INTERVAL = 300  # seconds between background version checks
_reload_thread: threading.Thread | None = None
_reload_lock = threading.Lock()


def _background_reload(interval: int):
    """Daemon thread: reload _mapdata_cache when data files change."""
    while True:
        time.sleep(interval)
        try:
            version = source_version()
            if _mapdata_cache["version"] == version:
                continue
            logger.info(f"Data files changed ({_mapdata_cache['version']} → {version}), reloading...")
            data = load_mapdata_from_source()
            _mapdata_cache["data"] = data
            _mapdata_cache["version"] = source_version()
            logger.info("Background data reload complete.")
        except Exception:
            logger.exception("Background data reload failed")


def _ensure_reload_thread():
    """Start the background reload thread if not already running.

    Gunicorn workers do not inherit threads across fork, so this is called
    lazily on the first callback invocation in each worker process.
    """
    global _reload_thread
    if _reload_thread is not None and _reload_thread.is_alive():
        return
    with _reload_lock:
        if _reload_thread is not None and _reload_thread.is_alive():
            return
        _reload_thread = threading.Thread(
            target=_background_reload,
            args=(DATA_RELOAD_INTERVAL,),
            daemon=True,
            name="mapdata-reload",
        )
        _reload_thread.start()
        logger.info(f"Started background data reload thread (interval={DATA_RELOAD_INTERVAL}s)")


def source_version():
    gdl = GliderDataLoader(data_dir=Path("./data"))
    files = gdl.files_available()
    if not files:
        return "0"
    latest = max((gdl.data_dir / f).stat().st_mtime for f in files)
    return dt.datetime.fromtimestamp(latest).isoformat(timespec='seconds')


def load_mapdata(version: str) -> dict:
    """Return mapdata from the module-level cache, recomputing only when version changes."""
    if _mapdata_cache["data"] is not None:
        if _mapdata_cache["version"] != version:
            logger.info(f"Data version changed ({_mapdata_cache['version']} → {version}); serving current cache.")
        return _mapdata_cache["data"]
    data = load_mapdata_from_source()
    # Read version after loading so the stored version reflects file state at completion,
    # not at the start of a potentially long load (avoids mtime race on next check).
    _mapdata_cache["version"] = source_version()
    _mapdata_cache["data"] = data
    return data


def load_mapdata_from_source():
    gdl = GliderDataLoader(data_dir=Path("./data"), auto_load=True)
    latlon_records, uv_records = {}, {}
    for sn in gdl.glider_sns():
        latlon_records[sn] = gdl.build_glider_df(glider_sn=sn).to_dict('records')
        uv_sn_df = gdl.build_uv_df(glider_sn=sn)
        new_lats, new_lons = latlon_offset(
            uv_sn_df["lat"].values,
            uv_sn_df["lon"].values,
            uv_sn_df["v"].values,
            uv_sn_df["u"].values,
            scale=1
        )
        uv_sn_df['uvlat'] = new_lats
        uv_sn_df['uvlon'] = new_lons
        uv_records[sn] = uv_sn_df.to_dict('records')

    return {
        "latlon_records": latlon_records,
        "uv_records": uv_records,
    }


def default_timerange_seconds(days_back=7):
    now = int(time.time())
    start = now - days_back * 24 * 3600
    return start, now


@app.callback(
    Output(StoreIds.MAPDATA_STORE, "data"),
    Output(StoreIds.MAPDATA_STORE_STATE, "data"),
    Input("url", "pathname"),
    State(StoreIds.MAPDATA_STORE_STATE, "data"),
    prevent_initial_call=False,   # run on first load
)
def init_mapdata_on_session(pathname, init_state):
    _ensure_reload_thread()
    version = source_version()

    # Already initialized → do nothing
    if init_state['initialized'] and version == init_state['version']:
        raise PreventUpdate

    mapdata = load_mapdata(version)

    return mapdata, dict(initialized=True, version=version)


@app.callback(
    Output(StoreIds.MAPDATA_STORE, "data", allow_duplicate=True),
    Output(StoreIds.MAPDATA_STORE_STATE, "data", allow_duplicate=True),
    Input(IntervalIds.DATA_REFRESH, "n_intervals"),
    State(StoreIds.MAPDATA_STORE_STATE, "data"),
    prevent_initial_call=True,
)
def refresh_mapdata_on_interval(n_intervals, init_state):
    version = source_version()
    if init_state.get("version") == version:
        raise PreventUpdate
    logger.info(f"Interval refresh: pushing new data version {version} to client.")
    return load_mapdata(version), dict(initialized=True, version=version)


@app.callback(
    Output(ContainerIds.HIDDEN_CUSTOMTIME_CONTAINER, "style"),
    Input(ControlIds.TIME_BTN_X, "n_clicks"),
    Input(ControlIds.TIME_BTN_DAY, "n_clicks"),
    Input(ControlIds.TIME_BTN_WEEK, "n_clicks"),
    Input(ControlIds.TIME_BTN_MONTH, "n_clicks"),
    Input(ControlIds.TIME_BTN_ALL, "n_clicks"),
    prevent_initial_call=True,
)
def toggle_custom_time_picker(
    n_custom, n_day, n_week, n_month, n_all
):
    trigger = dash.ctx.triggered_id

    if trigger == ControlIds.TIME_BTN_X:
        # show date picker
        return {"display": "block"}

    # any other button hides it
    return {"display": "none"}


@app.callback(
    Output(ControlIds.GLIDER_SELECT, "options"),
    Input(StoreIds.MAPDATA_STORE, "data"),
)
def set_glider_options(store_data):
    store_data = store_data or {}
    latlon_records = store_data.get("latlon_records", {})
    sns = sorted(latlon_records.keys())
    return [{"label": f"Spray {sn}", "value": str(sn)} for sn in sns]


@app.callback(
    Output(TextIds.SECTION_DETAILS_TEXT, "children"),
    Input(ControlIds.GLIDER_SELECT, "value"),
    Input(ControlIds.SECTION_SELECT, "value"),
    State(StoreIds.MAPDATA_STORE, "data"),
)
def populate_section_details(glider_sn, section_num, store_data):
    if not glider_sn:
        return "Select a glider to see details."
    store_data = store_data or {}

    url_realtime_pattern = 'https://gliders.whoi.edu/data/realtime/{:04d}.html'
    url_pattern = 'https://gliders.whoi.edu/data/figs/realtime/{SN:04d}/{KEY}_{SECTION}.png'

    static_charts = dict(
        map="Track and Depth-Average Currents",
        TS="Potential Temperature - Salinity",
        theta="Potential Temperature",
        s="Salinity",
        fl="Chlorophyll",
        oxumolkg="Dissolved Oxygen",
        ph="pH",
        c="Sound Speed",
    )

    # Mission link - always shown when glider is selected
    mission_link = html.Div([
        html.A("All plots for this mission", href=url_realtime_pattern.format(int(glider_sn)), target="_blank"),
    ], style={"margin-bottom": "30px"})

    # Section plot images - only shown when section is selected
    if section_num is None:
        details = html.Div([mission_link, "Select a section to see plots."])
        return details

    def img_block(series):
        url = url_pattern.format(SN=int(glider_sn), KEY=series, SECTION=section_num)
        block = html.Div([
            html.H4(static_charts[series]),
            html.A(
                html.Img(src=url, style={"width": "100%", "max-width": "300px", "margin-top": "10px"}),
                href=url,
                target="_blank",
            )
        ], style={"margin-bottom": "20px"})
        return block

    images = [img_block(key) for key in static_charts.keys()]

    details = html.Div([
        mission_link,
        html.H3(f"Section {section_num} Plots"),
        *images
    ])
    return details

def get_sections_for_glider(store_data, glider_sn):
    latlon_records = (store_data or {}).get("latlon_records", {})
    recs = latlon_records.get(glider_sn, [])
    secs = sorted({int(r["section"]) for r in recs if "section" in r and r["section"] is not None})
    return secs


# ── Click handler: relay track/endpoint clicks to a store ──

@app.callback(
    Output(MapIds.CLICK_STORE, "data"),
    Input({"type": "track-segment", "index": ALL}, "n_clicks"),
    Input({"type": "glider-endpoint", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def on_map_element_click(track_clicks, endpoint_clicks):
    triggered = dash.ctx.triggered_id
    if triggered is None:
        raise PreventUpdate

    # When map children are rebuilt, this callback fires with all n_clicks
    # as None. Only proceed if the triggered prop actually has a real click.
    triggered_prop = dash.ctx.triggered[0]
    if not triggered_prop.get("value"):
        raise PreventUpdate

    idx = triggered["index"]
    if triggered["type"] == "track-segment":
        parts = idx.rsplit("-", 1)
        glider_sn = parts[0]
        section = int(parts[1]) if len(parts) > 1 else None
        return {"glider": glider_sn, "section": section}
    elif triggered["type"] == "glider-endpoint":
        return {"glider": idx, "section": None}

    raise PreventUpdate


@app.callback(
    Output(ControlIds.GLIDER_SELECT, "value"),
    Output(ControlIds.SECTION_SELECT, "options"),
    Output(ControlIds.SECTION_SELECT, "value"),
    Output(ContainerIds.MAP_ACCORDION, "active_item"),
    Input(MapIds.CLICK_STORE, "data"),
    Input(ControlIds.GLIDER_SELECT, "value"),
    State(StoreIds.MAPDATA_STORE, "data"),
    State(ContainerIds.MAP_ACCORDION, "active_item"),
    prevent_initial_call=True,
)
def sync_section_ui(click_data, glider_value, store_data, active_item):
    trig = dash.ctx.triggered_id

    # Defaults: don't change unless we decide to
    new_glider = no_update
    new_section_value = no_update
    new_active = no_update

    if trig == MapIds.CLICK_STORE:
        if not click_data:
            raise PreventUpdate

        clicked_glider = str(click_data["glider"])
        clicked_section = click_data.get("section")

        new_glider = clicked_glider
        new_section_value = clicked_section

        # open accordion on map click
        new_active = [ContainerIds.SECTION_DETAILS] if isinstance(active_item, list) else ContainerIds.SECTION_DETAILS

        glider_for_options = clicked_glider

    else:
        # manual glider dropdown change -> just update section options
        if not glider_value:
            return glider_value, [], None, no_update

        glider_for_options = str(glider_value)
        new_glider = glider_for_options
        new_active = no_update
        new_section_value = no_update

    # Build section options for the chosen glider
    sections = get_sections_for_glider(store_data, glider_for_options)
    opts = [{"label": str(s), "value": s} for s in sections]

    # If click provided a section, ensure it's present in options so value sticks
    if trig == MapIds.CLICK_STORE and click_data and click_data.get("section") is not None:
        clicked_section = click_data["section"]
        if clicked_section not in sections:
            opts = [{"label": str(clicked_section), "value": clicked_section}] + opts

    return new_glider, opts, new_section_value, new_active
