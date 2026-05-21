from collections import defaultdict
from itertools import cycle
import datetime as dt
import math
from pathlib import Path

import dash
from dash import Input, Output, State, no_update, html, clientside_callback, ALL
import dash_bootstrap_components as dbc
import dash_leaflet as dl
from dash.exceptions import PreventUpdate
import numpy as np
import pandas as pd

from data_loader import DEFAULT_DATA_DIR, GliderDataLoader, parse_mission_yyyymmm
from utils import latlon_offset, load_map_region_config, load_region_labels, section_chart_specs
from .layout import layout, TILE_URL
from .names import MapIds, StoreIds, ControlIds, ContainerIds, TextIds, IntervalIds


dash.register_page(
    __name__,
    path="/plotting/archived",
    name="Archive Map",
    title="Gliders - Archive Map",
)

app = dash.get_app()

_REGION_LABELS = load_region_labels(Path("config/map_config.yml").resolve())


def _region_display(key: str) -> str:
    return _REGION_LABELS.get(key, key)


def _make_search_text(*parts):
    pieces = []
    for p in parts:
        if not p:
            continue
        s = str(p).lower()
        pieces.append(s)
        if " " in s:
            pieces.append(s.replace(" ", ""))
    return " ".join(pieces)


def _matches_query(search_text, query):
    if not query:
        return True
    return all(tok in search_text for tok in query.lower().split())


def rgb_to_hex(r: int, g: int, b: int, a=None):
    if a is None:
        return "#{:02X}{:02X}{:02X}".format(int(r), int(g), int(b))
    return "#{:02X}{:02X}{:02X}{:02X}".format(int(r), int(g), int(b), int(a * 255))


COLOR_CYCLE = [
    (31, 119, 180),
    (255, 127, 14),
    (44, 160, 44),
    (214, 39, 40),
    (148, 103, 189),
    (140, 86, 75),
]


def _load_region_config():
    gdl = GliderDataLoader(data_dir=DEFAULT_DATA_DIR, auto_load=False)
    archive_regions = {m["region"] for m in gdl.archive_missions.values()}
    _, _, glider_image_url = load_map_region_config(
        Path("config/map_config.yml").resolve(),
        active_regions=archive_regions,
    )
    return glider_image_url


_GLIDER_IMAGE_URL = _load_region_config()

GLIDER_ICON = dict(
    iconUrl=_GLIDER_IMAGE_URL or "SprayGliderTail.png",
    iconSize=[40, 40],
    iconAnchor=[20, 20],
)


def _finite_time_bounds(records):
    vals = [
        float(r["time"])
        for r in records
        if r.get("time") is not None and np.isfinite(r.get("time"))
    ]
    if not vals:
        return None, None
    return min(vals), max(vals)


def _mission_year_from_id(mission_id):
    try:
        return 2000 + int(str(mission_id)[0:2])
    except (TypeError, ValueError):
        return None


def _mission_years(meta):
    if meta.get("start_time") is not None and meta.get("end_time") is not None:
        start_year = dt.datetime.utcfromtimestamp(meta["start_time"]).year
        end_year = dt.datetime.utcfromtimestamp(meta["end_time"]).year
        return start_year, end_year
    year = meta.get("mission_year")
    return year, year


def _overlaps_year_range(meta, year_range):
    if not year_range:
        return True
    start_year, end_year = _mission_years(meta)
    if start_year is None or end_year is None:
        return True
    selected_start, selected_end = [int(y) for y in year_range]
    return start_year <= selected_end and end_year >= selected_start


def _mission_date_label(meta):
    if meta.get("start_time") is None:
        yymm = meta.get("yymm")
        return yymm if yymm and yymm != "?" else ""
    start = dt.datetime.utcfromtimestamp(meta["start_time"]).strftime("%Y-%m-%d")
    end = dt.datetime.utcfromtimestamp(meta["end_time"]).strftime("%Y-%m-%d")
    return start if start == end else f"{start} to {end}"


def _bounds_for_records(records):
    points = [
        (float(r["lat"]), float(r["lon"]))
        for r in records
        if r.get("lat") is not None
        and r.get("lon") is not None
        and np.isfinite(r.get("lat"))
        and np.isfinite(r.get("lon"))
    ]
    if not points:
        return None
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


def _merge_bounds(bounds_list):
    bounds_list = [b for b in bounds_list if b]
    if not bounds_list:
        return None
    return [
        [min(b[0][0] for b in bounds_list), min(b[0][1] for b in bounds_list)],
        [max(b[1][0] for b in bounds_list), max(b[1][1] for b in bounds_list)],
    ]


def _viewport_for_bounds(bounds):
    return {"bounds": bounds, "transition": "fitBounds"}


def _viewport_for_default():
    return {
        "center": [38.5, -73.5],
        "zoom": 5,
        "transition": "flyTo",
    }


def load_mapdata_from_source():
    gdl = GliderDataLoader(data_dir=DEFAULT_DATA_DIR, auto_load=False)
    missions = {}
    data_mtimes = []

    for mission_id in gdl.archive_mission_ids():
        meta = gdl.archive_missions.get(mission_id, {})
        mission_year = _mission_year_from_id(mission_id)
        yymm = parse_mission_yyyymmm(mission_id)
        mission = {
            "mission_id": mission_id,
            "region": meta.get("region", ""),
            "type": meta.get("type", ""),
            "available": gdl.has_json(mission_id),
            "mission_year": mission_year,
            "yymm": yymm,
            "records": [],
            "start_time": None,
            "end_time": None,
        }

        if mission["available"]:
            gdl.load_archived(mission_id)
            df = gdl.build_glider_df(mission_id)
            records = df.to_dict("records")
            start_time, end_time = _finite_time_bounds(records)
            mission.update(
                records=records,
                start_time=start_time,
                end_time=end_time,
            )
            entry = gdl._entry(mission_id)
            if entry and entry.get("source_mtime") is not None:
                data_mtimes.append(entry["source_mtime"])

        missions[mission_id] = mission

    latest = max(data_mtimes) if data_mtimes else 0
    return {
        "missions": missions,
        "data_mtime": dt.datetime.fromtimestamp(latest).isoformat(timespec="seconds"),
    }


def _build_map_children(missions, year_range, uv_scale, uv_data, hidden=None):
    hidden_set = set(hidden or [])
    children = []
    region_items = []
    mission_bounds = {}
    region_bounds_map = defaultdict(list)
    all_bounds = []
    items_by_region = defaultdict(list)

    filtered = [
        mission
        for mission in missions.values()
        if _overlaps_year_range(mission, year_range)
    ]

    filtered.sort(
        key=lambda m: (
            _region_display(m.get("region", "")),
            m.get("start_time") or math.inf,
            m["mission_id"],
        )
    )

    colors_by_region = defaultdict(lambda: cycle(COLOR_CYCLE))
    for mission in filtered:
        mission_id = mission["mission_id"]
        region_key = mission.get("region", "")
        color_hex = rgb_to_hex(*next(colors_by_region[region_key]))
        available = bool(mission.get("available") and mission.get("records"))
        is_hidden = str(mission_id) in hidden_set
        bounds = _bounds_for_records(mission.get("records", [])) if available else None

        if bounds:
            mission_bounds[mission_id] = bounds
            region_bounds_map[region_key].append(bounds)
            all_bounds.append(bounds)

        item = {
            "mission_id": mission_id,
            "region": region_key,
            "region_label": _region_display(region_key),
            "color": color_hex,
            "hidden": is_hidden,
            "available": available,
            "date_label": _mission_date_label(mission),
        }
        items_by_region[region_key].append(item)

        if not available or is_hidden:
            continue

        df = pd.DataFrame(mission["records"]).dropna(subset=["lat", "lon"])
        if df.empty:
            continue

        section_values = sorted({int(s) for s in df["section"].dropna().unique()})
        opacity_by_section = {
            section: float(opacity)
            for section, opacity in zip(
                section_values,
                np.linspace(0.25, 1, len(section_values)) if len(section_values) > 1 else [1.0],
            )
        }

        for section, df_sec in df.groupby("section", sort=False):
            positions = list(zip(df_sec["lat"].tolist(), df_sec["lon"].tolist()))
            if len(positions) < 2:
                continue
            section_int = int(section)
            children.append(
                dl.Polyline(
                    positions=positions,
                    color=color_hex,
                    opacity=opacity_by_section.get(section_int, 1.0),
                    weight=3,
                    id={"type": "archive-track-segment", "index": f"{mission_id}-{section_int}"},
                    children=dl.Tooltip(
                        html.Div(
                            [
                                html.B(f"Mission {mission_id}"),
                                html.Br(),
                                _region_display(region_key),
                                html.Br(),
                                f"Section {section_int}",
                            ]
                        )
                    ),
                )
            )

        # Depth-averaged current vectors for the one selected mission
        # (skipped when no mission is chosen or the scale slider is off).
        if (
            uv_scale
            and uv_data
            and str(uv_data.get("mission_id")) == str(mission_id)
            and uv_data.get("uv_records")
        ):
            uv_lines = []
            for section, df_uv_sec in pd.DataFrame(uv_data["uv_records"]).groupby("section", sort=False):
                opacity = opacity_by_section.get(int(section), 1.0)
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
                children.append(dl.LayerGroup(children=uv_lines, id=f"uv-{mission_id}"))

        end_row = df.iloc[-1]
        end_dt = dt.datetime.utcfromtimestamp(float(end_row["time"])) if np.isfinite(end_row["time"]) else None
        end_date_str = end_dt.strftime("%Y-%m-%d %H:%M:%S") if end_dt else "N/A"
        children.append(
            dl.Marker(
                position=[float(end_row["lat"]), float(end_row["lon"])],
                icon=GLIDER_ICON,
                id={"type": "archive-glider-endpoint", "index": str(mission_id)},
                children=dl.Tooltip(
                    html.Div(
                        [
                            html.B(f"Mission {mission_id}"),
                            html.Br(),
                            _region_display(region_key),
                            html.Br(),
                            f"Lat: {end_row['lat']:.4f}, Lon: {end_row['lon']:.4f}",
                            html.Br(),
                            f"Date: {end_date_str}",
                            html.Br(),
                            f"Section: {end_row.get('section', 'N/A')}, Dive: {end_row.get('ndive', 'N/A')}",
                        ]
                    )
                ),
            )
        )

    for region_key in sorted(items_by_region, key=_region_display):
        region_items.append(
            {
                "region": region_key,
                "region_label": _region_display(region_key),
                "items": items_by_region[region_key],
            }
        )

    gbounds = {
        "all": _merge_bounds(all_bounds),
        "regions": {region: _merge_bounds(bounds) for region, bounds in region_bounds_map.items()},
        "missions": mission_bounds,
        "region_missions": {
            region: [
                item["mission_id"]
                for item in items_by_region[region]
                if item["available"]
            ]
            for region in items_by_region
        },
    }
    return children, _merge_bounds(all_bounds), region_items, gbounds


def _icon_button(icon_class, button_id, title, class_name="map-legend-eye", disabled=False):
    return html.Button(
        html.I(className=f"bi {icon_class}"),
        id=button_id,
        className=class_name,
        n_clicks=0,
        title=title,
        disabled=disabled,
    )


def _legend_id(scope, kind, index=None):
    out = {"type": f"archive-legend-{kind}", "scope": scope}
    if index is not None:
        out["index"] = index
    return out


def _open_key(scope, region):
    return f"{scope}:{region}"


def _legend_children(region_items, scope="desktop", open_regions=None):
    if not region_items:
        return []
    open_set = set(open_regions or [])

    all_available = [
        item
        for region in region_items
        for item in region["items"]
        if item["available"]
    ]
    any_visible = any(not item["hidden"] for item in all_available)
    master_icon = "bi-eye" if any_visible else "bi-eye-slash"

    region_sections = []
    for region in region_items:
        items = region["items"]
        available = [item for item in items if item["available"]]
        region_visible = any(not item["hidden"] for item in available)
        region_icon = "bi-eye" if region_visible else "bi-eye-slash"

        count_label = str(len(items)) if len(available) == len(items) else f"{len(available)}/{len(items)}"
        header = html.Div(
            [
                html.Button(
                    [
                        html.I(className="bi bi-chevron-right archive-map-legend-chevron"),
                        html.Span(region["region_label"], className="map-legend-region-title"),
                        html.Span(count_label, className="map-legend-region-count"),
                    ],
                    id=_legend_id(scope, "region-toggle", region["region"]),
                    className="archive-map-legend-region-toggle",
                    n_clicks=0,
                    title=f"Expand {region['region_label']}",
                ),
                _icon_button(
                    "bi-search",
                    _legend_id(scope, "region-zoom", region["region"]),
                    f"Zoom to {region['region_label']}",
                    class_name="map-legend-eye archive-legend-zoom",
                    disabled=not bool(available),
                ),
                _icon_button(
                    region_icon,
                    _legend_id(scope, "region-eye", region["region"]),
                    "Hide region" if region_visible else "Show region",
                    disabled=not bool(available),
                ),
            ],
            className="archive-map-legend-region-header",
        )

        rows = []
        for item in items:
            hidden = item["hidden"] or not item["available"]
            eye_icon = "bi-eye-slash" if item["hidden"] else "bi-eye"
            row_classes = ["map-legend-row"]
            if not item["available"]:
                row_classes.append("map-legend-row-disabled")
            rows.append(
                html.Div(
                    [
                        html.Button(
                            [
                                html.Span(
                                    className="map-legend-swatch",
                                    style={
                                        "backgroundColor": item["color"],
                                        "opacity": 0.25 if hidden else 1.0,
                                    },
                                ),
                                html.Span(
                                    [
                                        html.Span(
                                            item["mission_id"],
                                            className="map-legend-label"
                                            + (" map-legend-label-hidden" if hidden else ""),
                                        ),
                                        html.Span(item["date_label"], className="archive-legend-date"),
                                    ],
                                    className="archive-legend-label-block",
                                ),
                            ],
                            id=_legend_id(scope, "item", str(item["mission_id"])),
                            className="map-legend-item",
                            n_clicks=0,
                            disabled=not item["available"],
                            title="Zoom to mission" if item["available"] else "No local data available",
                        ),
                        _icon_button(
                            eye_icon,
                            _legend_id(scope, "eye", str(item["mission_id"])),
                            "Hide" if not item["hidden"] else "Show",
                            disabled=not item["available"],
                        ),
                    ],
                    className=" ".join(row_classes),
                )
            )

        region_sections.append(
            html.Div(
                [
                    header,
                    dbc.Collapse(
                        html.Div(rows, className="map-legend-list archive-map-legend-list"),
                        id=_legend_id(scope, "region-collapse", region["region"]),
                        is_open=_open_key(scope, region["region"]) in open_set,
                    ),
                ],
                className="archive-map-legend-region",
            )
        )

    return html.Details(
        [
            html.Summary(
                [
                    html.Span("Archive Missions", className="map-legend-title"),
                    _icon_button(
                        "bi-search",
                        _legend_id(scope, "master-zoom"),
                        "Zoom to all archive tracks",
                        class_name="map-legend-eye map-legend-eye-master archive-legend-zoom",
                        disabled=not bool(all_available),
                    ),
                    _icon_button(
                        master_icon,
                        _legend_id(scope, "master-eye"),
                        "Hide all" if any_visible else "Show all",
                        class_name="map-legend-eye map-legend-eye-master",
                        disabled=not bool(all_available),
                    ),
                ],
                className="map-legend-header archive-map-legend-master-summary",
            ),
            html.Div(
                region_sections,
                id=f"archive-map-legend-accordion-{scope}",
                className="archive-map-legend-accordion",
            ),
        ],
        open=True,
        className="archive-map-legend-master",
    )


@app.callback(
    Output({"type": "archive-legend-region-collapse", "scope": ALL, "index": ALL}, "is_open"),
    Input({"type": "archive-legend-region-toggle", "scope": ALL, "index": ALL}, "n_clicks"),
    State({"type": "archive-legend-region-collapse", "scope": ALL, "index": ALL}, "is_open"),
    prevent_initial_call=True,
)
def toggle_legend_region(_clicks, is_open):
    trig = dash.ctx.triggered_id
    if not trig:
        raise PreventUpdate
    triggered_prop = dash.ctx.triggered[0]
    if not triggered_prop.get("value"):
        raise PreventUpdate
    ids = [entry["id"] for entry in dash.ctx.outputs_list]
    return [
        (not open_state) if out_id["scope"] == trig["scope"] and out_id["index"] == trig["index"] else open_state
        for out_id, open_state in zip(ids, is_open)
    ]


@app.callback(
    Output(StoreIds.LEGEND_OPEN_STORE, "data"),
    Input({"type": "archive-legend-region-toggle", "scope": ALL, "index": ALL}, "n_clicks"),
    State(StoreIds.LEGEND_OPEN_STORE, "data"),
    prevent_initial_call=True,
)
def store_open_legend_regions(_clicks, open_regions):
    trig = dash.ctx.triggered_id
    if not trig:
        raise PreventUpdate
    triggered_prop = dash.ctx.triggered[0]
    if not triggered_prop.get("value"):
        raise PreventUpdate
    open_set = set(open_regions or [])
    key = _open_key(trig["scope"], trig["index"])
    if key in open_set:
        open_set.remove(key)
    else:
        open_set.add(key)
    return sorted(open_set)


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


clientside_callback(
    """
    function(children, currentClass) {
        if (currentClass && currentClass.includes('hidden')) {
            return window.dash_clientside.no_update;
        }
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


@app.callback(
    Output(StoreIds.MAPDATA_STORE, "data"),
    Input("archive-url", "pathname"),
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
    Output(StoreIds.YEARRANGE_STORE, "data"),
    Input(ControlIds.YEAR_RANGE, "value"),
)
def update_yearrange_store(year_range):
    if not year_range:
        raise PreventUpdate
    return [int(year_range[0]), int(year_range[1])]


@app.callback(
    Output(MapIds.MAP, "children"),
    Output(MapIds.MAP, "viewport"),
    Output(ContainerIds.MAP_LEGEND, "children"),
    Output(ContainerIds.MAP_LEGEND_MOBILE, "children"),
    Output(StoreIds.LEGEND_BOUNDS_STORE, "data"),
    Input(StoreIds.MAPDATA_STORE, "data"),
    Input(StoreIds.YEARRANGE_STORE, "data"),
    Input(ControlIds.UV_SCALE, "value"),
    Input(StoreIds.UV_STORE, "data"),
    Input(StoreIds.LEGEND_HIDDEN_STORE, "data"),
    State(StoreIds.LEGEND_OPEN_STORE, "data"),
    prevent_initial_call=False,
)
def update_map(store_data, year_range, uv_scale, uv_data, hidden, open_regions):
    store_data = store_data or {}
    missions = store_data.get("missions", {})
    tile = dl.TileLayer(url=TILE_URL)
    zoom_ctrl = dl.ZoomControl(position="bottomright")

    if not missions:
        return [tile, zoom_ctrl], _viewport_for_default(), [], [], {}

    data_children, bounds, region_items, gbounds = _build_map_children(
        missions, year_range, uv_scale, uv_data, hidden=hidden
    )
    if not data_children:
        data_children = [dl.LayerGroup(id="archive-map-loaded-placeholder")]
    all_children = [tile, zoom_ctrl] + data_children
    desktop_legend = _legend_children(region_items, scope="desktop", open_regions=open_regions)
    mobile_legend = _legend_children(region_items, scope="mobile", open_regions=open_regions)

    # Selecting a UV glider or moving the scale slider only restyles vectors —
    # keep the viewport put (re-zoom only on year-range / data changes).
    if dash.ctx.triggered_id in (
        StoreIds.LEGEND_HIDDEN_STORE,
        StoreIds.UV_STORE,
        ControlIds.UV_SCALE,
    ):
        return all_children, no_update, desktop_legend, mobile_legend, gbounds
    if bounds:
        return all_children, _viewport_for_bounds(bounds), desktop_legend, mobile_legend, gbounds
    return all_children, _viewport_for_default(), desktop_legend, mobile_legend, gbounds


@app.callback(
    Output(StoreIds.LEGEND_HIDDEN_STORE, "data"),
    Input({"type": "archive-legend-eye", "scope": ALL, "index": ALL}, "n_clicks"),
    Input({"type": "archive-legend-region-eye", "scope": ALL, "index": ALL}, "n_clicks"),
    Input({"type": "archive-legend-master-eye", "scope": ALL}, "n_clicks"),
    State(StoreIds.LEGEND_HIDDEN_STORE, "data"),
    State(StoreIds.LEGEND_BOUNDS_STORE, "data"),
    prevent_initial_call=True,
)
def toggle_legend_visibility(_eye_clicks, _region_clicks, _master_clicks, hidden, gbounds):
    trig = dash.ctx.triggered_id
    if not trig:
        raise PreventUpdate
    triggered_prop = dash.ctx.triggered[0]
    if not triggered_prop.get("value"):
        raise PreventUpdate

    hidden_set = set(hidden or [])
    gbounds = gbounds or {}

    if trig["type"] == "archive-legend-master-eye":
        all_missions = set(map(str, (gbounds.get("missions") or {}).keys()))
        any_visible = bool(all_missions - hidden_set)
        return sorted(all_missions) if any_visible else []

    if trig["type"] == "archive-legend-region-eye":
        region = trig["index"]
        region_missions = set(map(str, (gbounds.get("region_missions") or {}).get(region, [])))
        any_visible = bool(region_missions - hidden_set)
        if any_visible:
            hidden_set.update(region_missions)
        else:
            hidden_set.difference_update(region_missions)
        return sorted(hidden_set)

    mission_id = str(trig["index"])
    if mission_id in hidden_set:
        hidden_set.remove(mission_id)
    else:
        hidden_set.add(mission_id)
    return sorted(hidden_set)


@app.callback(
    Output(MapIds.MAP, "viewport", allow_duplicate=True),
    Input({"type": "archive-legend-item", "scope": ALL, "index": ALL}, "n_clicks"),
    Input({"type": "archive-legend-region-zoom", "scope": ALL, "index": ALL}, "n_clicks"),
    Input({"type": "archive-legend-master-zoom", "scope": ALL}, "n_clicks"),
    State(StoreIds.LEGEND_BOUNDS_STORE, "data"),
    prevent_initial_call=True,
)
def zoom_to_legend(_mission_clicks, _region_clicks, _master_clicks, gbounds):
    trig = dash.ctx.triggered_id
    if not trig or not gbounds:
        raise PreventUpdate
    triggered_prop = dash.ctx.triggered[0]
    if not triggered_prop.get("value"):
        raise PreventUpdate

    if trig["type"] == "archive-legend-master-zoom":
        bounds = gbounds.get("all")
    elif trig["type"] == "archive-legend-region-zoom":
        bounds = (gbounds.get("regions") or {}).get(trig["index"])
    else:
        bounds = (gbounds.get("missions") or {}).get(str(trig["index"]))

    if not bounds:
        raise PreventUpdate
    return _viewport_for_bounds(bounds)


def _mission_dropdown_options(store_data, search_value):
    """Build mission-dropdown options (label with region + date, disabled when
    no local data). Shared by the Section Details and current-vector dropdowns.
    """
    store_data = store_data or {}
    missions = store_data.get("missions", {})
    rows = []
    for mission_id, mission in missions.items():
        region_key = mission.get("region", "")
        region_lbl = _region_display(region_key)
        date_label = _mission_date_label(mission)
        disabled = not mission.get("available")
        search_text = _make_search_text(mission_id, region_key, region_lbl, date_label, mission.get("yymm"))
        if not _matches_query(search_text, search_value):
            continue
        rows.append((disabled, mission_id, region_lbl, date_label, search_text))

    rows.sort(key=lambda r: r[1])
    sv = search_value or ""
    gray = {"color": "#999", "marginLeft": "0.5em"}
    disabled_style = {"color": "#aaa"}

    def label(disabled, mission_id, region_lbl, date_label):
        primary = html.Span(mission_id, style=disabled_style) if disabled else mission_id
        suffix = []
        detail = " - ".join(part for part in (region_lbl, date_label) if part)
        if detail:
            suffix.append(html.Span(f" {detail}", style=gray))
        if disabled:
            suffix.append(html.Span(" (no data)", style=gray))
        return html.Span([primary, *suffix])

    return [
        {
            "label": label(disabled, mission_id, region_lbl, date_label),
            "value": mission_id,
            "disabled": disabled,
            "search": f"{search_text} {sv}",
        }
        for disabled, mission_id, region_lbl, date_label, search_text in rows
    ]


@app.callback(
    Output(ControlIds.GLIDER_SELECT, "options"),
    Input(StoreIds.MAPDATA_STORE, "data"),
    Input(ControlIds.GLIDER_SELECT, "search_value"),
)
def set_glider_options(store_data, search_value):
    return _mission_dropdown_options(store_data, search_value)


@app.callback(
    Output(ControlIds.UV_PLOT_BTN, "disabled"),
    Input(ControlIds.GLIDER_SELECT, "value"),
)
def toggle_uv_button(mission_id):
    # The button can only request vectors when a mission is selected.
    return not mission_id


@app.callback(
    Output(StoreIds.UV_STORE, "data"),
    Input(ControlIds.UV_PLOT_BTN, "n_clicks"),
    Input(ControlIds.GLIDER_SELECT, "value"),
    prevent_initial_call=True,
)
def update_uv_store(_n_clicks, mission_id):
    """Plot / clear depth-averaged current vectors for the Section Details mission.

    Clicking the button loads vectors for the currently selected mission.
    Changing the mission selection clears any plotted vectors, so the map never
    shows currents that don't match the selected mission. Only the one selected
    mission's vectors are ever built and shipped to the browser.
    """
    if dash.ctx.triggered_id == ControlIds.GLIDER_SELECT:
        return {}
    if not mission_id:
        return {}
    gdl = GliderDataLoader(data_dir=DEFAULT_DATA_DIR, auto_load=False)
    if not gdl.has_json(mission_id):
        return {}
    gdl.load_archived(mission_id)
    uv_df = gdl.build_uv_df(mission_id).dropna(subset=["lat", "lon", "u", "v"])
    return {"mission_id": str(mission_id), "uv_records": uv_df.to_dict("records")}


@app.callback(
    Output(TextIds.SECTION_DETAILS_TEXT, "children"),
    Input(ControlIds.GLIDER_SELECT, "value"),
    Input(ControlIds.SECTION_SELECT, "value"),
)
def populate_section_details(mission_id, section_num):
    if not mission_id:
        return "Select a mission to see details."

    mission_url = f"https://gliders.whoi.edu/data/archive/{mission_id}.html"
    url_pattern = "https://gliders.whoi.edu/data/figs/archive/{MISSION}/{KEY}_{SECTION}.png"

    # Charts are driven by the mission's variable list in archive.csv/archive2.csv
    # so plots the mission doesn't carry are never rendered (no broken images).
    gdl = GliderDataLoader(data_dir=DEFAULT_DATA_DIR, auto_load=False)
    chart_specs = section_chart_specs(gdl.section_variables(mission_id), gdl.variable_names)

    mission_link = html.Div(
        [
            html.A("All plots for this mission", href=mission_url, target="_blank"),
        ],
        style={"margin-bottom": "30px"},
    )

    if section_num is None:
        return html.Div([mission_link, "Select a section to see plots."])

    def img_block(series, header):
        url = url_pattern.format(MISSION=mission_id, KEY=series, SECTION=section_num)
        return html.Div(
            [
                html.H4(header),
                html.A(
                    html.Img(src=url, style={"width": "100%", "max-width": "300px", "margin-top": "10px"}),
                    href=url,
                    target="_blank",
                ),
            ],
            style={"margin-bottom": "20px"},
        )

    return html.Div(
        [
            mission_link,
            html.H3(f"Section {section_num} Plots"),
            *[img_block(key, header) for key, header in chart_specs],
        ]
    )


def get_sections_for_glider(store_data, mission_id):
    latlon_records = ((store_data or {}).get("missions", {}).get(str(mission_id), {}) or {}).get("records", [])
    secs = sorted({int(r["section"]) for r in latlon_records if "section" in r and r["section"] is not None})
    return secs


@app.callback(
    Output(MapIds.CLICK_STORE, "data"),
    Input({"type": "archive-track-segment", "index": ALL}, "n_clicks"),
    Input({"type": "archive-glider-endpoint", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def on_map_element_click(track_clicks, endpoint_clicks):
    triggered = dash.ctx.triggered_id
    if triggered is None:
        raise PreventUpdate
    triggered_prop = dash.ctx.triggered[0]
    if not triggered_prop.get("value"):
        raise PreventUpdate

    idx = triggered["index"]
    if triggered["type"] == "archive-track-segment":
        parts = idx.rsplit("-", 1)
        mission_id = parts[0]
        section = int(parts[1]) if len(parts) > 1 else None
        return {"glider": mission_id, "section": section}
    if triggered["type"] == "archive-glider-endpoint":
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
        new_active = [ContainerIds.SECTION_DETAILS] if isinstance(active_item, list) else ContainerIds.SECTION_DETAILS
        glider_for_options = clicked_glider
    else:
        if not glider_value:
            return glider_value, [], None, no_update
        glider_for_options = str(glider_value)
        new_glider = glider_for_options

    sections = get_sections_for_glider(store_data, glider_for_options)
    opts = [{"label": str(s), "value": s} for s in sections]

    if trig == MapIds.CLICK_STORE and click_data and click_data.get("section") is not None:
        clicked_section = click_data["section"]
        if clicked_section not in sections:
            opts = [{"label": str(clicked_section), "value": clicked_section}] + opts

    return new_glider, opts, new_section_value, new_active
