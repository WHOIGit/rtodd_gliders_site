import time

from dash import html, dcc
import dash_bootstrap_components as dbc

from .names import *


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
        html.Img(src="/assets/sponsors.png", style={"width": "350px"}),
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

    return html.Div(
        [
            html.P('Select Time Range'),
            btn_grp,
            custom_picker,  # hidden

            html.Hr(className="my-3"),
            html.P('Select UV Glider Drift Scale'),
        ])


def float_box():
    intro = intro_div()

    options = options_div()

    accordion = dbc.Accordion(
        [
            dbc.AccordionItem(intro, title="Spray Glider Operations at WHOI", item_id="map-info"),
            dbc.AccordionItem(options, title="Map Options"),
        ],
        flush=True,            # cleaner edges inside the box
        always_open=False,
        active_item='map-info',
    )

    return html.Div(accordion, className="map-overlay",)



def main_layout():
    now = int(time.time())
    daysago = 30
    start = now - daysago * 24 * 60 * 60

    map_div = dcc.Graph(
        id=MapIds.GRAPH,
        style={"height": "100%", "width": "100%"},
        config={"displayModeBar": True,"responsive": True},
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

