import logging
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

from data_loader import DEFAULT_DATA_DIR, GliderDataLoader, get_gdl
from utils import (
    active_glider_dropdown_options,
    latlon_offset,
    load_map_region_config,
    load_region_labels,
    region_display,
    section_chart_specs,
    section_opacity_by_section,
    section_plot_details,
)

_REGION_LABELS = load_region_labels(Path("config/map_config.yml").resolve())


def _region_display(key: str) -> str:
    return region_display(_REGION_LABELS, key)


def _finite_number(value):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _latest_record_time(records):
    return max(
        (
            t
            for record in (records or [])
            if isinstance(record, dict)
            for t in (_finite_number(record.get("time")),)
            if t is not None
        ),
        default=0,
    )


def _section_key(section):
    try:
        return str(int(section))
    except (TypeError, ValueError):
        return str(section)


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

def _truncate_to_day_start(epoch: int) -> int:
    d = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(d.timestamp())

@app.callback(
    Output(StoreIds.TIMERANGE_STORE, "data"),
    Output(StoreIds.TIMEBTN_ACTIVE_STORE, "data"),
    Input(ControlIds.TIME_BTN_DAY, "n_clicks"),
    Input(ControlIds.TIME_BTN_WEEK, "n_clicks"),
    Input(ControlIds.TIME_BTN_MONTH, "n_clicks"),
    Input(ControlIds.TIME_BTN_ALL, "n_clicks"),
    Input(ControlIds.TIME_RANGE_PICKER, "start_date"),
    Input(ControlIds.TIME_RANGE_PICKER, "end_date"),
    prevent_initial_call=True,
)
def update_timerange_store(
    day, week, month, all_,
    start_date, end_date,
):
    trig = dash.ctx.triggered_id
    now = int(time.time())
    start = 0

    if trig == ControlIds.TIME_BTN_DAY:
        start = _truncate_to_day_start(now - 1 * 24 * 3600)
        return [start, None], trig

    elif trig == ControlIds.TIME_BTN_WEEK:
        start = _truncate_to_day_start(now - 7 * 24 * 3600)
        return [start, None], trig

    elif trig == ControlIds.TIME_BTN_MONTH:
        start = _truncate_to_day_start(now - 30 * 24 * 3600)
        return [start, None], trig

    elif trig == ControlIds.TIME_RANGE_PICKER:
        if not start_date:
            return no_update, no_update
        start = _date_to_epoch_start(start_date)
        end = _date_to_epoch_end(end_date) if end_date else now
        return [start, end], no_update

    else: # trig == ControlIds.TIME_BTN_ALL
        return None, trig



@app.callback(
    Output(ControlIds.TIME_BTN_DAY, "outline"),
    Output(ControlIds.TIME_BTN_WEEK, "outline"),
    Output(ControlIds.TIME_BTN_MONTH, "outline"),
    Output(ControlIds.TIME_BTN_ALL, "outline"),
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
    )


@app.callback(
    Output(StoreIds.REGION_ACTIVE_STORE, "data"),
    Input({"type": "region-btn", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def update_region_store(all_n_clicks):
    trig = dash.ctx.triggered_id
    if not trig or not any(c for c in all_n_clicks if c):
        return no_update
    return {"region": trig["index"], "n": sum(c or 0 for c in all_n_clicks)}


@app.callback(
    Output({"type": "region-btn", "index": ALL}, "outline"),
    Input(StoreIds.REGION_ACTIVE_STORE, "data"),
)
def set_active_region_button(region_data):
    active = (region_data or {}).get("region", _default_region)
    return [opt["value"] != active for opt in _region_options]


def rgb_to_hex(r:int, g:int, b:int, a=None):
    if a is None:
        return "#{:02X}{:02X}{:02X}".format(
            int(r), int(g), int(b) )
    else:
        return "#{:02X}{:02X}{:02X}{:02X}".format(
            int(r), int(g), int(b), int(a * 255))


def _load_region_config():
    gdl = GliderDataLoader(data_dir=DEFAULT_DATA_DIR, auto_load=False)
    active_regions = {m["region"] for m in gdl.active_meta.values()}
    _, _, glider_image_url = load_map_region_config(
        Path("config/map_config.yml").resolve(),
        active_regions=active_regions,
    )
    region_options = [{"label": "Show All", "value": "all"}] + [
        {"label": _region_display(region), "value": region}
        for region in sorted(active_regions, key=_region_display)
    ]
    return "all", region_options, glider_image_url


_default_region, _region_options, _GLIDER_IMAGE_URL = _load_region_config()

GLIDER_ICON = dict(
    iconUrl=_GLIDER_IMAGE_URL or "SprayGliderTail.png",
    iconSize=[40, 40],
    iconAnchor=[20, 20],
)


def _build_map_children(latlon_records, uv_records, time_range, uv_scale, hidden=None):
    """Build dash-leaflet children, bounds, and legend for the map.

    Returns (children, bounds, legend_items, per_glider_bounds, per_section_bounds) where:
      children: list of dl components (Polyline, Marker, LayerGroup)
      bounds: [[south, west], [north, east]] or None — overall fit bounds
      legend_items: list of (glider_sn, color_hex) in display order
      per_glider_bounds: dict[sn, [[s,w],[n,e]]] for legend click-to-zoom
      per_section_bounds: dict[sn][section], filtered to the rendered records
    """
    COLOR_PALETTE = [
        ( 31, 119, 180), # blue
        (255, 127,  14), # orange
        ( 44, 160,  44), # green
        (214,  39,  40), # red
        (148, 103, 189), # purple
        (140,  86,  75), # brown
    ]

    # Assign each glider a stable color keyed by its serial number. Recency
    # (sorted_gliders, below) still controls draw and legend order, but color
    # must NOT depend on that order: an interval refresh can reorder gliders by
    # most-recent timestamp, and if color followed that order the tracks would
    # recolor while already-rendered vector layers kept their old color — the
    # "mismatched track/vector colors" seen after the map sits idle.
    color_by_sn = {
        sn: rgb_to_hex(*COLOR_PALETTE[i % len(COLOR_PALETTE)])
        for i, sn in enumerate(sorted(latlon_records))
    }

    hidden_set = set(hidden or [])
    children = []
    legend_items = []  # all gliders, with a `hidden` flag
    per_glider_bounds = {}
    per_section_bounds = {}
    maxlat, minlat, maxlon, minlon = -180, 180, -180, 180

    sorted_gliders = sorted(
        latlon_records.items(),
        key=lambda item: _latest_record_time(item[1]),
        reverse=True,
    )

    for glider_sn, records in sorted_gliders:
        color_hex = color_by_sn[glider_sn]

        df = pd.DataFrame(records)
        if df.empty or not {"lat", "lon", "time"}.issubset(df.columns):
            continue
        if "section" not in df.columns:
            df["section"] = 1
        for column in ("lat", "lon", "time"):
            df[column] = pd.to_numeric(df[column], errors="coerce")
        df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True, errors="coerce").dt.tz_convert(None)
        df = df.dropna(subset=["lat", "lon"])

        # filter by time range if available
        if time_range and "time" in df.columns:
            start, end = time_range
            mask = df["time"] >= start
            if end is not None:
                mask = mask & (df["time"] <= end)
            df = df[mask]

        if df.empty:
            continue

        opacity_by_section = section_opacity_by_section(df["section"])
        per_section_bounds[str(glider_sn)] = {
            _section_key(section): _bounds_for_records(df_sec.to_dict("records"))
            for section, df_sec in df.groupby("section", sort=False)
        }

        is_hidden = str(glider_sn) in hidden_set
        legend_items.append((glider_sn, color_hex, is_hidden))

        # per-glider bounds (for legend click-to-zoom) — computed even when hidden
        g_minlat = float(df["lat"].min())
        g_maxlat = float(df["lat"].max())
        g_minlon = float(df["lon"].min())
        g_maxlon = float(df["lon"].max())
        per_glider_bounds[glider_sn] = [[g_minlat, g_minlon], [g_maxlat, g_maxlon]]

        if is_hidden:
            continue

        # set overall map bounds (visible gliders only)
        minlat = min(minlat, g_minlat)
        maxlat = max(maxlat, g_maxlat)
        minlon = min(minlon, g_minlon)
        maxlon = max(maxlon, g_maxlon)

        for section, df_sec in df.groupby("section", sort=False):
            opacity = opacity_by_section.get(section, 1.0)
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

        # add u,v vectors if available (skip entirely when scale is off)
        if uv_scale and uv_records and glider_sn in uv_records:
            uv_recs = uv_records[glider_sn]
            df_uv = pd.DataFrame(uv_recs)
            if df_uv.empty or not {"lat", "lon", "u", "v"}.issubset(df_uv.columns):
                continue
            if "section" not in df_uv.columns:
                df_uv["section"] = 1
            for column in ("lat", "lon", "u", "v", "time"):
                if column in df_uv.columns:
                    df_uv[column] = pd.to_numeric(df_uv[column], errors="coerce")
            df_uv = df_uv.dropna(subset=["lat", "lon", "u", "v"])

            if time_range and "time" in df_uv.columns:
                start, end = time_range
                mask = df_uv["time"] >= start
                if end is not None:
                    mask = mask & (df_uv["time"] <= end)
                df_uv = df_uv[mask]

            uv_lines = []
            for section, df_uv_sec in df_uv.groupby("section", sort=False):
                opacity = opacity_by_section.get(section, 1.0)
                lat = df_uv_sec["lat"].to_numpy()
                lon = df_uv_sec["lon"].to_numpy()
                vlat, ulon = latlon_offset(
                    lat, lon, df_uv_sec["v"].to_numpy(), df_uv_sec["u"].to_numpy(), uv_scale
                )
                # One multi-segment polyline per section: each ray is its own
                # [start, end] segment, so they render disconnected within a
                # single layer instead of one Polyline component per vector.
                segments = [
                    [[la, lo], [vla, ulo]]
                    for la, lo, vla, ulo in zip(
                        lat.tolist(), lon.tolist(), vlat.tolist(), ulon.tolist()
                    )
                ]
                if segments:
                    uv_lines.append(
                        dl.Polyline(
                            positions=segments,
                            color=color_hex,
                            opacity=opacity,
                            weight=1,
                            interactive=False,
                        )
                    )

            if uv_lines:
                children.append(dl.LayerGroup(children=uv_lines, id=f"uv-{glider_sn}"))

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
        # No visible tracks — still surface the legend so users can re-show.
        bounds_or_none = None
        return [], bounds_or_none, legend_items, per_glider_bounds, per_section_bounds

    bounds = [[minlat, minlon], [maxlat, maxlon]]
    return children, bounds, legend_items, per_glider_bounds, per_section_bounds


def _viewport_for_bounds(bounds):
    """Create a viewport dict that fits the given bounds with padding."""
    return {"bounds": bounds, "transition": "fitBounds"}


def _merge_bounds(bounds_list):
    bounds_list = [b for b in bounds_list if b]
    if not bounds_list:
        return None
    return [
        [min(b[0][0] for b in bounds_list), min(b[0][1] for b in bounds_list)],
        [max(b[1][0] for b in bounds_list), max(b[1][1] for b in bounds_list)],
    ]


def _bounds_for_region_selection(region_key, gbounds, region_by_glider, hidden):
    hidden_set = set(hidden or [])
    gbounds = gbounds or {}
    if region_key == "all":
        sns = [sn for sn in gbounds if str(sn) not in hidden_set]
    else:
        sns = [
            sn for sn, region in (region_by_glider or {}).items()
            if region == region_key and sn in gbounds and str(sn) not in hidden_set
        ]
    return _merge_bounds(gbounds.get(sn) for sn in sns)


def _bounds_for_records(records, section_num=None, time_range=None):
    points = []
    for record in records or []:
        if section_num is not None and record.get("section") != section_num:
            try:
                if int(record.get("section")) != int(section_num):
                    continue
            except (TypeError, ValueError):
                continue
        if time_range and record.get("time") is not None:
            try:
                record_time = float(record["time"])
            except (TypeError, ValueError):
                continue
            start, end = time_range
            if record_time < start or (end is not None and record_time > end):
                continue
        lat = _finite_number(record.get("lat"))
        lon = _finite_number(record.get("lon"))
        if lat is None or lon is None:
            continue
        points.append((lat, lon))
    if not points:
        return None
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


@app.callback(
    Output(MapIds.MAP, "children"),
    Output(MapIds.MAP, "viewport"),
    Output(AlertIds.BANNER, "is_open"),
    Output(AlertIds.BANNER, "children"),
    Output(ContainerIds.MAP_LEGEND, "children"),
    Output(StoreIds.LEGEND_BOUNDS_STORE, "data"),
    Output(StoreIds.SECTION_BOUNDS_STORE, "data"),
    Input(StoreIds.MAPDATA_STORE, "data"),
    Input(StoreIds.TIMERANGE_STORE, "data"),
    Input(ControlIds.UV_SCALE, "value"),
    Input(StoreIds.REGION_ACTIVE_STORE, "data"),
    Input(ControlIds.REGION_AUTO_ZOOM, "value"),
    Input(StoreIds.LEGEND_HIDDEN_STORE, "data"),
    State(IntervalIds.DATA_REFRESH, "n_intervals"),
    prevent_initial_call=False,
)
def update_map(store_data, time_range, uv_scale, region_store, auto_zoom, hidden, n_intervals):
    region_key = (region_store or {}).get("region", _default_region)
    trigger = dash.ctx.triggered_id
    is_visibility_toggle = dash.ctx.triggered_id == StoreIds.LEGEND_HIDDEN_STORE
    is_interval_refresh = (
        trigger == ControlIds.UV_SCALE
        or is_visibility_toggle
        or (
            trigger == StoreIds.MAPDATA_STORE
            and n_intervals is not None
            and n_intervals > 0
        )
    )
    should_update_viewport = (
        trigger in (None, StoreIds.REGION_ACTIVE_STORE)
        or (
            bool(auto_zoom)
            and trigger in (StoreIds.MAPDATA_STORE, StoreIds.TIMERANGE_STORE, StoreIds.LEGEND_HIDDEN_STORE)
        )
    )
    store_data = store_data or {}
    latlon_records = store_data.get("latlon_records", {})
    uv_records = store_data.get("uv_records", {})
    region_by_glider = store_data.get("region_by_glider", {})

    tile = dl.TileLayer(url=TILE_URL)
    zoom_ctrl = dl.ZoomControl(position="bottomright")

    if not latlon_records:
        return [tile, zoom_ctrl], no_update, False, "", [], {}, {}

    data_children, bounds, legend_items, gbounds, section_bounds = _build_map_children(
        latlon_records, uv_records, time_range, uv_scale, hidden=hidden
    )

    if not data_children:
        # No visible tracks. Could be: (a) everything hidden via legend toggle,
        # (b) no data in the selected time range. For (b), try shifting.
        all_hidden_via_toggle = bool(legend_items) and all(h for *_, h in legend_items)

        if not all_hidden_via_toggle and time_range:
            start, end = time_range
            window = end - start
            last_ts = max(
                r["time"] for records in latlon_records.values()
                for r in records if r.get("time") is not None and not np.isnan(r["time"])
            )
            shifted_range = [last_ts - window, last_ts]
            data_children, bounds, legend_items, gbounds, section_bounds = _build_map_children(
                latlon_records, uv_records, shifted_range, uv_scale, hidden=hidden
            )
            if data_children:
                last_dt = dt.datetime.utcfromtimestamp(last_ts).strftime("%Y-%m-%d")
                all_children = [tile, zoom_ctrl] + data_children
                selected_bounds = _bounds_for_region_selection(region_key, gbounds, region_by_glider, hidden)
                vp = _viewport_for_bounds(selected_bounds) if selected_bounds else no_update
                if not should_update_viewport:
                    vp = no_update
                return (all_children, vp, True,
                    f"No data found for the selected time range. Showing the same time window ending at the last available data ({last_dt}).",
                    _legend_children(legend_items), gbounds, section_bounds)

        selected_bounds = _bounds_for_region_selection(region_key, gbounds, region_by_glider, hidden)
        vp = no_update if not should_update_viewport or not selected_bounds else _viewport_for_bounds(selected_bounds)
        return [tile, zoom_ctrl], vp, False, "", _legend_children(legend_items), gbounds, section_bounds

    all_children = [tile, zoom_ctrl] + data_children
    legend = _legend_children(legend_items)
    selected_bounds = _bounds_for_region_selection(region_key, gbounds, region_by_glider, hidden)

    if is_visibility_toggle:
        vp = _viewport_for_bounds(selected_bounds) if should_update_viewport and selected_bounds else no_update
        return all_children, vp, False, "", legend, gbounds, section_bounds
    vp = no_update if not should_update_viewport or is_interval_refresh or not selected_bounds else _viewport_for_bounds(selected_bounds)
    return all_children, vp, False, "", legend, gbounds, section_bounds


def _legend_children(legend_items):
    if not legend_items:
        return []
    any_visible = any(not h for _, _, h in legend_items)
    master_icon = "bi-eye" if any_visible else "bi-eye-slash"
    rows = []
    for sn, color_hex, hidden in legend_items:
        eye_icon = "bi-eye-slash" if hidden else "bi-eye"
        rows.append(html.Div([
            html.Button(
                [
                    html.Span(className="map-legend-swatch",
                              style={"backgroundColor": color_hex,
                                     "opacity": 0.3 if hidden else 1.0}),
                    html.Span(f"Spray {sn}",
                              className="map-legend-label"
                                        + (" map-legend-label-hidden" if hidden else "")),
                ],
                id={"type": "legend-item", "index": str(sn)},
                className="map-legend-item",
                n_clicks=0,
            ),
            html.Button(
                html.I(className=f"bi {eye_icon}"),
                id={"type": "legend-eye", "index": str(sn)},
                className="map-legend-eye",
                n_clicks=0,
                title="Hide" if not hidden else "Show",
            ),
        ], className="map-legend-row"))
    return [
        html.Div([
            html.Span("Gliders", className="map-legend-title"),
            html.Button(
                html.I(className=f"bi {master_icon}"),
                id="map-legend-master-eye",
                className="map-legend-eye map-legend-eye-master",
                n_clicks=0,
                title="Hide all" if any_visible else "Show all",
            ),
        ], className="map-legend-header"),
        html.Div(rows, className="map-legend-list"),
    ]




@app.callback(
    Output(StoreIds.LEGEND_HIDDEN_STORE, "data"),
    Input({"type": "legend-eye", "index": ALL}, "n_clicks"),
    Input("map-legend-master-eye", "n_clicks"),
    State(StoreIds.LEGEND_HIDDEN_STORE, "data"),
    State(StoreIds.LEGEND_BOUNDS_STORE, "data"),
    prevent_initial_call=True,
)
def toggle_legend_visibility(_eye_clicks, _master_clicks, hidden, gbounds):
    trig = dash.ctx.triggered_id
    if not trig:
        raise PreventUpdate
    triggered_prop = dash.ctx.triggered[0]
    if not triggered_prop.get("value"):
        raise PreventUpdate

    hidden_set = set(hidden or [])

    if trig == "map-legend-master-eye":
        all_sns = set(map(str, (gbounds or {}).keys()))
        any_visible = bool(all_sns - hidden_set)
        return sorted(all_sns) if any_visible else []

    sn = str(trig["index"])
    if sn in hidden_set:
        hidden_set.remove(sn)
    else:
        hidden_set.add(sn)
    return sorted(hidden_set)


@app.callback(
    Output(MapIds.MAP, "viewport", allow_duplicate=True),
    Input({"type": "legend-item", "index": ALL}, "n_clicks"),
    State(StoreIds.LEGEND_BOUNDS_STORE, "data"),
    prevent_initial_call=True,
)
def zoom_to_legend(_clicks, gbounds):
    trig = dash.ctx.triggered_id
    if not trig or not gbounds:
        raise PreventUpdate
    triggered_prop = dash.ctx.triggered[0]
    if not triggered_prop.get("value"):
        raise PreventUpdate
    sn = trig["index"]
    bounds = gbounds.get(sn)
    if not bounds:
        raise PreventUpdate
    return _viewport_for_bounds(bounds)


@app.callback(
    Output(ControlIds.SECTION_ZOOM_BTN, "disabled"),
    Input(ControlIds.GLIDER_SELECT, "value"),
)
def toggle_section_zoom_button(glider_sn):
    return not glider_sn


@app.callback(
    Output(MapIds.MAP, "viewport", allow_duplicate=True),
    Input(ControlIds.SECTION_ZOOM_BTN, "n_clicks"),
    State(ControlIds.GLIDER_SELECT, "value"),
    State(ControlIds.SECTION_SELECT, "value"),
    State(StoreIds.LEGEND_BOUNDS_STORE, "data"),
    State(StoreIds.SECTION_BOUNDS_STORE, "data"),
    prevent_initial_call=True,
)
def zoom_to_section_details(_n_clicks, glider_sn, section_num, gbounds, section_bounds):
    if not glider_sn:
        raise PreventUpdate

    glider_sn = str(glider_sn)
    if section_num is None:
        bounds = (gbounds or {}).get(glider_sn)
    else:
        bounds = ((section_bounds or {}).get(glider_sn) or {}).get(_section_key(section_num))

    if not bounds:
        raise PreventUpdate
    return _viewport_for_bounds(bounds)


def load_mapdata_from_source():
    gdl = get_gdl()
    latlon_records, uv_records = {}, {}
    for sn in gdl.glider_sns():
        latlon_records[sn] = gdl.build_glider_df(sn).to_dict('records')
        uv_sn_df = gdl.build_uv_df(sn)
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
        "region_by_glider": {
            sn: meta.get("region", "")
            for sn, meta in gdl.active_meta.items()
            if sn in latlon_records
        },
        "data_mtime": gdl.latest_filemodified_timestamp(),
    }


def default_timerange_seconds(days_back=7):
    now = int(time.time())
    start = now - days_back * 24 * 3600
    return start, now


@app.callback(
    Output(StoreIds.MAPDATA_STORE, "data"),
    Input("url", "pathname"),
    prevent_initial_call=False,
)
def init_mapdata_on_session(pathname):
    return load_mapdata_from_source()


@app.callback(
    Output(StoreIds.MAPDATA_STORE, "data", allow_duplicate=True),
    Input(IntervalIds.DATA_REFRESH, "n_intervals"),
    State(StoreIds.MAPDATA_STORE, "data"),
    prevent_initial_call=True,
)
def refresh_mapdata_on_interval(n_intervals, current_store):
    new_data = load_mapdata_from_source()
    if current_store and current_store.get("data_mtime") == new_data.get("data_mtime"):
        return no_update
    return new_data


@app.callback(
    Output(ControlIds.GLIDER_SELECT, "options"),
    Input(StoreIds.MAPDATA_STORE, "data"),
    Input(ControlIds.GLIDER_SELECT, "search_value"),
)
def set_glider_options(store_data, search_value):
    store_data = store_data or {}
    latlon_records = store_data.get("latlon_records", {})
    loaded = set(latlon_records.keys())
    gdl = get_gdl()
    all_sns = sorted(set(gdl.all_active_sns()) | loaded)
    region_by_glider = {
        sn: gdl.active_meta.get(sn, {}).get("region", "")
        for sn in all_sns
    }
    return active_glider_dropdown_options(
        all_sns,
        search_value=search_value,
        region_by_glider=region_by_glider,
        region_labels=_REGION_LABELS,
        is_available=lambda sn: sn in loaded,
        include_no_data_suffix=True,
    )


@app.callback(
    Output(TextIds.SECTION_DETAILS_TEXT, "children"),
    Input(ControlIds.GLIDER_SELECT, "value"),
    Input(ControlIds.SECTION_SELECT, "value"),
)
def populate_section_details(glider_sn, section_num):
    if not glider_sn:
        return "Select a glider to see details."

    # Charts are driven by the glider's variable list in active.csv/active2.csv
    # so plots the glider doesn't carry are never rendered (no broken images).
    gdl = get_gdl()
    chart_specs = section_chart_specs(gdl.section_variables(glider_sn), gdl.variable_names)
    return section_plot_details(
        source="realtime",
        identifier=glider_sn,
        section_num=section_num,
        chart_specs=chart_specs,
    )

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
