import time
from pathlib import Path

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_leaflet as dl

from .names import *
from utils import load_region_labels, normalize_region_key
from data_loader import DEFAULT_DATA_DIR, GliderDataLoader

_gdl = GliderDataLoader(data_dir=DEFAULT_DATA_DIR, auto_load=False)
_active_regions = {normalize_region_key(m.get("region", "")) for m in _gdl.active_meta.values()}
_region_labels = load_region_labels(Path("config/map_config.yml").resolve())
_default_region = "all"
_region_options = [{"label": "Show All", "value": _default_region}] + [
    {"label": _region_labels.get(region, region), "value": region}
    for region in sorted(_active_regions, key=lambda r: _region_labels.get(r, r))
]

_init_center = [35.0, -65.0]
_init_zoom = 4

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
            dbc.Button("Day", id=ControlIds.TIME_BTN_DAY, size="sm", outline=True, color="secondary", className="flex-fill"),
            dbc.Button("Week", id=ControlIds.TIME_BTN_WEEK, size="sm", outline=True, color="secondary", className="flex-fill"),
            dbc.Button("Month", id=ControlIds.TIME_BTN_MONTH, size="sm", outline=True, color="secondary", className="flex-fill"),
            dbc.Button("All", id=ControlIds.TIME_BTN_ALL, size="sm", outline=True, color="secondary", className="flex-fill"),
        ],
        size="sm",
        className="w-100 d-flex",
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
        className="mt-3 mb-2",
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
            html.Div(
                [
                    html.Div("Region", className="fw-semibold"),
                    dbc.Switch(
                        id=ControlIds.REGION_AUTO_ZOOM,
                        label="Auto",
                        value=True,
                        className="map-region-auto-switch",
                    ),
                ],
                className="d-flex align-items-center justify-content-between mb-1",
            ),
            region_select,

            html.Hr(className="my-3"),
            uv_scale,
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
                            dbc.Tooltip(
                                "Select a glider",
                                id=TextIds.GLIDER_SELECT_TOOLTIP,
                                target=ControlIds.GLIDER_SELECT,
                                placement="top",
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
            dbc.Button(
                "Zoom To",
                id=ControlIds.SECTION_ZOOM_BTN,
                size="sm",
                color="secondary",
                outline=True,
                disabled=True,
                n_clicks=0,
                className="w-100 mt-2",
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
    options = options_div()
    sections_info = section_details_div()

    accordion = dbc.Accordion(
        [
            dbc.AccordionItem(options, title="Map Options"),
            dbc.AccordionItem(sections_info, title="Section Details", item_id=ContainerIds.SECTION_DETAILS),
        ],
        id=ContainerIds.MAP_ACCORDION,
        flush=True,
        always_open=False,
        active_item=None,
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
        style={"backgroundImage": f"url({app.get_asset_url('spray_cropped_800.jpg')})"},
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

    legend_box = html.Div(
        id=ContainerIds.MAP_LEGEND,
        className="map-legend",
    )

    map_div = html.Div(
        [leaflet_map, loading_overlay, legend_box],
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
            dcc.Store(id=StoreIds.LEGEND_BOUNDS_STORE, storage_type="memory", data={}),
            dcc.Store(id=StoreIds.SECTION_BOUNDS_STORE, storage_type="memory", data={}),
            dcc.Store(id=StoreIds.LEGEND_HIDDEN_STORE, storage_type="memory", data=[]),

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
