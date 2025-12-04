# layout.py
from dash import html, dcc
import dash_bootstrap_components as dbc

from names import ControlIds, MapIds, TabsIds, TextIds, IntervalIds, StoreIds


def header_row():
    return dbc.Row(
        dbc.Col(
            html.H2("Glider Data Explorer", className="my-2"),
            width=12,
        ),
        class_name="mb-2",
    )


def status_row():
    return dbc.Row(
        dbc.Col(
            dbc.Alert(
                id=TextIds.STATUS,
                children="Waiting for data files in ./data/ ...",
                color="info",
                class_name="mb-2",
            ),
            width=12,
        )
    )


def map_row():
    card = dbc.Card(
        [
            dbc.CardHeader("Map"),
            dbc.CardBody(
                dcc.Graph(
                    id=MapIds.GRAPH,
                    style={"height": "450px"},
                    config={"displayModeBar": True},
                )
            ),
        ],
        class_name="mb-3",
    )
    return dbc.Row(dbc.Col(card, width=12))


def time_slider_row():
    card = dbc.Card(
        [
            dbc.CardHeader("Time Range"),
            dbc.CardBody(
                [
                    dcc.RangeSlider(
                        id=ControlIds.TIME_RANGE,
                        min=0,
                        max=1,
                        step=1,
                        value=[0, 1],
                        marks={0: "0", 1: "1"},
                        tooltip={"placement": "bottom", "always_visible": False},
                    ),
                    html.Div(
                        id="time-range-readout",
                        className="mt-2 text-muted",
                        style={"fontSize": "0.85rem"},
                    ),
                ]
            ),
        ],
        class_name="mb-3",
    )
    return dbc.Row(dbc.Col(card, width=12))


def options_row():
    # Column 1: Gliders (checkboxes)
    gliders_card = dbc.Card(
        [
            dbc.CardHeader("Gliders"),
            dbc.CardBody(
                dcc.Checklist(
                    id=ControlIds.GLIDER_CHECKLIST,
                    options=[],
                    value=[],
                ),
            ),
        ],
        class_name="mb-3",
    )

    # Column 2: Map Color Variable
    color_card = dbc.Card(
        [
            dbc.CardHeader("Map Color Variable"),
            dbc.CardBody(
                dcc.RadioItems(
                    id=ControlIds.MAP_COLOR_RADIO,
                    options=[
                        {"label": "Red", "value": "red"},
                        {"label": "Green", "value": "green"},
                        {"label": "Blue",  "value": "blue"},
                    ],
                    value="red",
                    labelStyle={"display": "block"},
                )
            ),
        ],
        class_name="mb-3",
    )

    # Disabled helper style
    disabled_style = {
        "opacity": "0.4",
        "pointerEvents": "none",
    }

    # Column 3: Layers (placeholder)
    layers_card = dbc.Card(
        [
            dbc.CardHeader("Layers"),
            dbc.CardBody(
                dcc.RadioItems(
                    id=ControlIds.LAYERS_RADIO,
                    options=[
                        {"label": "Mixed Layer Depth Avg", "value": "mld_avg"},
                        {"label": "Surface", "value": "surface"},
                    ],
                    value="mld_avg",
                    labelStyle={"display": "block"},
                ),
                style=disabled_style,
            ),
        ],
        class_name="mb-3",
    )

    # Column 4: Cast Direction (placeholder)
    cast_card = dbc.Card(
        [
            dbc.CardHeader("Cast Direction"),
            dbc.CardBody(
                dcc.RadioItems(
                    id=ControlIds.CAST_DIR_RADIO,
                    options=[
                        {"label": "Up", "value": "up"},
                        {"label": "Down", "value": "down"},
                        {"label": "Both", "value": "both"},
                        {"label": "Unknown", "value": "unknown"},
                    ],
                    value="both",
                    labelStyle={"display": "block"},
                ),
                style=disabled_style,
            ),
        ],
        class_name="mb-3",
    )

    # Column 5: Map Options (placeholder)
    map_opts_card = dbc.Card(
        [
            dbc.CardHeader("Map Options"),
            dbc.CardBody(
                dcc.RadioItems(
                    id=ControlIds.MAP_OPTIONS_RADIO,
                    options=[
                        {"label": "Option 1", "value": "opt1"},
                        {"label": "Option 2", "value": "opt2"},
                    ],
                    value="opt1",
                    labelStyle={"display": "block"},
                ),
                style=disabled_style,
            ),
        ],
        class_name="mb-3",
    )

    return dbc.Row(
        [
            dbc.Col(gliders_card, md=3),
            dbc.Col(color_card, md=2),
            dbc.Col(layers_card, md=3),
            dbc.Col(cast_card, md=2),
            dbc.Col(map_opts_card, md=2),
        ],
        class_name="mb-2",
    )


def tabs_row():
    tabs = dcc.Tabs(
        id=TabsIds.TABS,
        value=TabsIds.INFO_TAB_VALUE,
        children=[
            dcc.Tab(label="Info", value=TabsIds.INFO_TAB_VALUE),
            # Data-driven tabs get added here by callback
        ],
    )

    content = html.Div(id=TabsIds.CONTENT, className="mt-3")

    card = dbc.Card(
        [
            dbc.CardHeader("Plots"),
            dbc.CardBody([tabs, content]),
        ],
        class_name="mb-3",
    )
    return dbc.Row(dbc.Col(card, width=12))


def create_layout():
    return dbc.Container(
        [
            header_row(),
            status_row(),      # updatable text row
            map_row(),         # map row
            time_slider_row(), # time range slider row
            options_row(),     # options row with 5 columns
            tabs_row(),        # tabs row
            # Hidden / utility components
            dcc.Store(id=StoreIds.DATA),
            dcc.Interval(
                id=IntervalIds.FILE_REFRESH,
                interval=10_000,  # 10 seconds
                n_intervals=0,
            ),
        ],
        fluid=True,
    )
