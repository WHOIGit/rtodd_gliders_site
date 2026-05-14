import time
from pathlib import Path

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_leaflet as dl

from .names import *
from utils import load_map_region_config
from data_loader import GliderDataLoader

_gdl = GliderDataLoader(data_dir=Path("./data"), auto_load=False)
_active_regions = {m["region"] for m in _gdl.active_meta.values()}
_default_region, _region_options, _region_presets, _ = load_map_region_config(
    Path("config/map_config.yml").resolve(),
    active_regions=_active_regions,
)

# Initial center/zoom from the default region preset
_init_preset = _region_presets.get(_default_region, {"center": {"lat": 35.0, "lon": -65.0}, "zoom": 4})
_init_center = [_init_preset["center"]["lat"], _init_preset["center"]["lon"]]
_init_zoom = _init_preset["zoom"]

app = dash.get_app()

TILE_URL = "https://services.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}"


def intro_div():
    return html.Div([
        html.P(
            "Autonomous underwater gliders are able to fly through the ocean for months at a time, "
            "returning measurement of many key water properties. "
            "Our group at the Woods Hole Oceanographic Institution (WHOI) "
            "operates a fleet of Spray gliders as a contribution to the "
            "Global Ocean Observing System and in support of various oceanographic field campaigns"
        ),
        html.P('Our work is funded by:'),
        html.Img(src=app.get_asset_url("sponsors_800.png"), style={"maxWidth": "350px", "width": "100%"}),
        ])

def options_div():
    btn_grp = dbc.ButtonGroup(
        [
            dbc.Button("Day", id=ControlIds.TIME_BTN_DAY, size="sm", outline=True, color="secondary"),
            dbc.Button("Week", id=ControlIds.TIME_BTN_WEEK, size="sm", outline=True, color="secondary"),
            dbc.Button("Month", id=ControlIds.TIME_BTN_MONTH, size="sm", outline=True, color="secondary"),
            dbc.Button("All", id=ControlIds.TIME_BTN_ALL, size="sm", outline=True, color="secondary"),
            dbc.Button("Custom", id=ControlIds.TIME_BTN_X, size="sm", outline=True, color="secondary"),
        ],
        size="sm",
    )

    custom_picker = html.Div(
        [
            html.Div("Custom range", className="fw-semibold mb-1"),
            dcc.DatePickerRange(
                id=ControlIds.TIME_RANGE_PICKER,
                minimum_nights=0,
                display_format="YYYY-MM-DD",
                start_date_placeholder_text="Start date",
                end_date_placeholder_text="End date",
                clearable=True,
            ),
            html.Div(
                "Tip: leave End blank to use 'now'",
                className="text-muted small mt-1",
            ),
        ],
        id=ContainerIds.HIDDEN_CUSTOMTIME_CONTAINER,
        style={"display": "none"},  # hidden by default
        className="mt-2",
    )

    uv_scale = html.Div(
        [
            html.Div("Depth-Average Current Scale", className="fw-semibold mb-1"),
            dcc.Slider(
                id=ControlIds.UV_SCALE,
                min=0,
                max=2,
                step=0.1,
                value=1.0,
                marks={
                    0: "off",
                    0.5: "long",
                    1.0: "",
                    1.5: "short",
                    2: ""
                },
                tooltip={"placement": "bottom", "always_visible": False},
            ),
        ],
        className="mt-3",
    )

    region_select = html.Div(
        [
            dbc.Button(
                opt["label"],
                id={"type": "region-btn", "index": opt["value"]},
                size="sm",
                color="secondary",
                outline=opt["value"] != _default_region,
                className="w-100 mb-1",
                n_clicks=0,
            )
            for opt in _region_options
        ],
        id="region-btn-group",
    )

    return html.Div(
        [
            html.Div("Time Range", className="fw-semibold mb-1"),
            btn_grp,
            custom_picker,  # hidden

            html.Hr(className="my-3"),
            uv_scale,

            html.Hr(className="my-3"),
            html.Div("Region", className="fw-semibold mb-1"),
            region_select,
        ])


def section_details_div():
    controls = html.Div(
        [
            # Inline row: glider dropdown + section integer dropdown
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div("Glider", className="fw-semibold mb-1"),
                            dcc.Dropdown(
                                id=ControlIds.GLIDER_SELECT,
                                options=[],          # filled by callback
                                value=None,
                                placeholder="Select glider...",
                                clearable=True,
                            ),
                        ],
                        xs=12, sm=7,
                    ),
                    dbc.Col(
                        [
                            html.Div("Section", className="fw-semibold mb-1"),
                            dcc.Dropdown(
                                id=ControlIds.SECTION_SELECT,
                                options=[],          # filled by callback
                                value=None,
                                placeholder="Select #",
                                clearable=True,
                            ),
                        ],
                        xs=12, sm=5,
                    ),
                ],
                className="g-2",
                align="end",
            ),

            # Output text area
            html.Div(
                "Select a glider and section to see details.",
                id=TextIds.SECTION_DETAILS_TEXT,
                className="mt-3 small",
                style={
                    "whiteSpace": "pre-wrap",
                    "maxHeight": "50vh",
                    "overflowY": "auto",
                    "border": "1px solid rgba(0,0,0,0.1)",
                    "borderRadius": "6px",
                    "padding": "8px",
                    "background": "rgba(255,255,255,0.85)",
                },
            ),
        ]
    )

    return controls




def float_box():
    intro = intro_div()
    options = options_div()
    sections_info = section_details_div()

    accordion = dbc.Accordion(
        [
            dbc.AccordionItem(intro, title="Spray Glider Operations at WHOI", item_id="map-info"),
            dbc.AccordionItem(options, title="Map Options"),
            dbc.AccordionItem(sections_info, title="Section Details", item_id=ContainerIds.SECTION_DETAILS),
        ],
        id=ContainerIds.MAP_ACCORDION,
        flush=True,
        always_open=False,
        active_item='map-info',
    )

    return html.Div(
        accordion,
        id=ContainerIds.MAP_OVERLAY,
        className="map-overlay collapsed",
    )



def main_layout():
    import datetime as dt
    daysago = 30
    today = dt.datetime.now(tz=dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = int((today - dt.timedelta(days=daysago)).timestamp())

    loading_overlay = html.Div(
        [
            html.Div(
                [
                    html.Div(className="map-loading-overlay__spinner"),
                    "Loading map\u2026",
                ],
                className="map-loading-overlay__label",
            )
        ],
        id=ContainerIds.MAP_LOADING_OVERLAY,
        className="map-loading-overlay",
    )

    leaflet_map = dl.Map(
        id=MapIds.MAP,
        children=[
            dl.TileLayer(url=TILE_URL),
            dl.ZoomControl(position="bottomright"),
        ],
        center=_init_center,
        zoom=_init_zoom,
        zoomControl=False,
        #wheelDebounceTime=0,
        wheelPxPerZoomLevel=120,
        style={"height": "100%", "width": "100%"},
    )

    map_div = html.Div(
        [leaflet_map, loading_overlay],
        className="flex-grow-1 d-flex flex-column",
        style={"position": "relative", "minHeight": 0},
    )

    overlay_toggle = html.Div(
        "≡",
        id=ContainerIds.MAP_OVERLAY_TOGGLE,
        className="map-overlay-toggle",
        n_clicks=0,
    )

    return html.Div(
        [
            # triggers on navigation/page-load
            dcc.Location(id="url", refresh=False),

            # memory stores: cleared on every page load so hard refresh always fetches fresh data
            dcc.Store(id=StoreIds.MAPDATA_STORE, storage_type="memory", data={}),
            dcc.Store(id=StoreIds.TIMERANGE_STORE, storage_type="memory", data=[start, None]),
            dcc.Store(id=StoreIds.TIMEBTN_ACTIVE_STORE, storage_type="memory", data=ControlIds.TIME_BTN_MONTH),
            dcc.Store(id=StoreIds.REGION_ACTIVE_STORE, storage_type="memory", data={"region": _default_region, "n": 0}),

            # periodic check for updated data files
            dcc.Interval(id=IntervalIds.DATA_REFRESH, interval=5 * 60 * 1000, n_intervals=0),

            # click relay store
            dcc.Store(id=MapIds.CLICK_STORE, data=None),

            # UI elements
            map_div,
            float_box(),
            overlay_toggle,
        ],
        className="flex-grow-1 d-flex",
        style={"minHeight": 0},
    )

layout = main_layout()
