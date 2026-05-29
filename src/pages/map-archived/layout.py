import datetime as dt

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_leaflet as dl

from data_loader import DEFAULT_DATA_DIR, GliderDataLoader
from .names import ControlIds, StoreIds, MapIds, ContainerIds, TextIds, IntervalIds


_gdl = GliderDataLoader(data_dir=DEFAULT_DATA_DIR, auto_load=False)
_init_center = [38.5, -73.5]
_init_zoom = 5

app = dash.get_app()

TILE_URL = "https://services.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}"


def _archive_year_bounds():
    years = []
    for mission_id in _gdl.archive_mission_ids():
        try:
            years.append(2000 + int(str(mission_id)[0:2]))
        except (TypeError, ValueError):
            continue
    current_year = dt.datetime.now(dt.timezone.utc).year
    min_year = min(years) if years else current_year
    return min_year, current_year


_min_year, _max_year = _archive_year_bounds()


def options_div():
    marks = {
        year: str(year)
        for year in range(_min_year, _max_year + 1)
        if year % 5 == 0
    }
    return html.Div(
        [
            dcc.RangeSlider(
                id=ControlIds.YEAR_RANGE,
                min=_min_year,
                max=_max_year,
                step=1,
                value=[_min_year, _max_year],
                marks=marks,
                tooltip={"placement": "bottom", "always_visible": False},
                allowCross=False,
                className="archive-year-slider",
            ),
        ]
    )


def uv_scale_div():
    return html.Div(
        dcc.Slider(
            id=ControlIds.UV_SCALE,
            min=0,
            max=2,
            step=0.1,
            value=1.0,
            marks={0: "off", 0.5: "long", 1.0: "", 1.5: "short", 2: ""},
            tooltip={"placement": "bottom", "always_visible": False},
        ),
        className="mt-2 mb-2",
    )


def section_details_div():
    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div("Mission", className="fw-semibold mb-1"),
                            dcc.Dropdown(
                                id=ControlIds.GLIDER_SELECT,
                                options=[],
                                value=None,
                                placeholder="Select mission...",
                                clearable=True,
                            ),
                            dbc.Tooltip(
                                "Select a mission",
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
                                options=[],
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
            dbc.Button(
                "Plot Depth-Average Currents",
                id=ControlIds.UV_PLOT_BTN,
                size="sm",
                color="secondary",
                outline=True,
                disabled=True,
                n_clicks=0,
                className="w-100 mt-2",
            ),
            html.Div(
                "Select a mission and section to see details.",
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


def float_box():
    accordion = dbc.Accordion(
        [
            dbc.AccordionItem(options_div(), title="Year Range"),
            dbc.AccordionItem(uv_scale_div(), title="Depth-Average Current Scale"),
            dbc.AccordionItem(section_details_div(), title="Section Details", item_id=ContainerIds.SECTION_DETAILS),
            dbc.AccordionItem(
                html.Div(id=ContainerIds.MAP_LEGEND_MOBILE, className="archive-map-legend archive-map-legend-mobile"),
                title="Legend",
                item_id=ContainerIds.MOBILE_LEGEND,
                className="archive-mobile-legend-item",
            ),
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
    loading_overlay = html.Div(
        [
            html.Div(
                [
                    html.Div(className="map-loading-overlay__spinner"),
                    "Loading archive map...",
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
        wheelPxPerZoomLevel=120,
        style={"height": "100%", "width": "100%"},
    )

    legend_box = html.Div(
        id=ContainerIds.MAP_LEGEND,
        className="map-legend archive-map-legend",
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
            dcc.Location(id="archive-url", refresh=False),
            dcc.Store(id=StoreIds.MAPDATA_STORE, storage_type="memory", data={}),
            dcc.Store(id=StoreIds.YEARRANGE_STORE, storage_type="memory", data=[_min_year, _max_year]),
            dcc.Store(id=StoreIds.UV_STORE, storage_type="memory", data={}),
            dcc.Store(id=StoreIds.LEGEND_BOUNDS_STORE, storage_type="memory", data={}),
            dcc.Store(id=StoreIds.SECTION_BOUNDS_STORE, storage_type="memory", data={}),
            dcc.Store(id=StoreIds.LEGEND_HIDDEN_STORE, storage_type="memory", data=[]),
            dcc.Store(id=StoreIds.LEGEND_OPEN_STORE, storage_type="memory", data=[]),
            dcc.Interval(id=IntervalIds.DATA_REFRESH, interval=30 * 60 * 1000, n_intervals=0),
            dcc.Store(id=MapIds.CLICK_STORE, data=None),
            map_div,
            float_box(),
            overlay_toggle,
        ],
        className="flex-grow-1 d-flex",
        style={"minHeight": 0},
    )


layout = main_layout()
