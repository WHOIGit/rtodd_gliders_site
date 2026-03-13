import time
from pathlib import Path

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc

from .names import *
from utils import load_map_region_config

_default_region, _region_options, _ = load_map_region_config(
    Path("config/map_regions.yml").resolve()
)

app = dash.get_app()


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
        html.Img(src=app.get_asset_url("sponsors.png"), style={"maxWidth": "350px", "width": "100%"}),
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
                "Tip: leave End blank to use ‘now’",
                className="text-muted small mt-1",
            ),
        ],
        id=ContainerIds.HIDDEN_CUSTOMTIME_CONTAINER,
        style={"display": "none"},  # hidden by default
        className="mt-2",
    )

    uv_scale = html.Div(
        [
            html.Div("UV Drift Scale", className="fw-semibold mb-1"),
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

    region_select = dbc.RadioItems(
        id=ControlIds.REGION_SELECT,
        options=_region_options,
        value=_default_region,
        inline=False,
        className="btn-group-vertical w-100",
        inputClassName="btn-check",
        labelClassName="btn btn-outline-secondary btn-sm",
        labelCheckedClassName="btn btn-secondary btn-sm",
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

    return html.Div(accordion, className="map-overlay",)



def main_layout():
    now = int(time.time())
    daysago = 30
    start = now - daysago * 24 * 60 * 60

    map_div = dcc.Loading(
        id="map-loading",
        type="circle",
        children=dcc.Graph(
            id=MapIds.GRAPH,
            style={"height": "100%", "width": "100%"},
            config={"displayModeBar": True, "responsive": True},
        ),
        parent_className="flex-grow-1 d-flex flex-column",
        parent_style={"minHeight": 0},
    )

    return html.Div(
        [
            # triggers on navigation/page-load
            dcc.Location(id="url", refresh=False),

            # session stores so init runs once per tab session
            dcc.Store(id=StoreIds.MAPDATA_STORE, storage_type="session", data={}),
            dcc.Store(id=StoreIds.MAPDATA_STORE_STATE, storage_type="session",
                      data={"initialized": False, 'version':''}),
            dcc.Store(id=StoreIds.TIMERANGE_STORE, storage_type="session", data=[start, now]),
            dcc.Store(id=StoreIds.TIMEBTN_ACTIVE_STORE, storage_type="session", data=ControlIds.TIME_BTN_MONTH),

            # UI elements
            map_div,
            float_box(),
        ],
        className="flex-grow-1 d-flex",
        style={"minHeight": 0},
    )

layout = main_layout()

