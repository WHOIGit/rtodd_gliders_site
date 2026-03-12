from dash import html, dcc
import dash_bootstrap_components as dbc

from .names import AdvStoreIds, AdvControlIds, AdvGraphIds, AdvContainerIds


def _controls_card():
    return dbc.Card(
        dbc.CardBody([
            html.H5("Advanced Data Explorer", className="mb-3"),

            # Glider selection
            html.Label("Glider", className="fw-semibold mb-1"),
            dcc.Dropdown(
                id=AdvControlIds.GLIDER_SELECT,
                options=[],
                value=None,
                placeholder="Select glider...",
                clearable=True,
            ),

            html.Hr(className="my-3"),

            # Data range mode
            html.Label("Data Range", className="fw-semibold mb-1"),
            dbc.RadioItems(
                id=AdvControlIds.RANGE_MODE,
                options=[
                    {"label": "Section", "value": "section"},
                    {"label": "Dive", "value": "dive"},
                ],
                value="section",
                inline=True,
                className="mb-2",
            ),

            # Section selector (visible by default)
            html.Div(
                [
                    dcc.Dropdown(
                        id=AdvControlIds.SECTION_SELECT,
                        options=[],
                        value=None,
                        placeholder="Select section...",
                        clearable=True,
                    ),
                ],
                id=AdvContainerIds.SECTION_CONTAINER,
            ),

            # Dive number input (hidden by default)
            html.Div(
                [
                    dbc.InputGroup([
                        dcc.Input(
                            id=AdvControlIds.DIVE_INPUT,
                            type="number",
                            min=1,
                            placeholder="Dive #",
                            className="form-control text-center",
                            style={"textAlign": "center"},
                            debounce=True,
                        ),
                        dbc.Button("▲", id=AdvControlIds.DIVE_NEXT, color="secondary", outline=True, size="sm"),
                        dbc.Button("▼", id=AdvControlIds.DIVE_PREV, color="secondary", outline=True, size="sm"),
                    ]),
                ],
                id=AdvContainerIds.DIVE_CONTAINER,
                style={"display": "none"},
            ),

            html.Hr(className="my-3"),

            # Cast filter
            html.Label("Cast Filter", className="fw-semibold mb-1"),
            dbc.RadioItems(
                id=AdvControlIds.CAST_FILTER,
                options=[
                    {"label": "All", "value": "all"},
                    {"label": "Downcast", "value": "downcast"},
                    {"label": "Upcast", "value": "upcast"},
                ],
                value="all",
                inline=True,
                className="mb-2",
            ),

            html.Hr(className="my-3"),

            # Instrument selection
            html.Label("Instrument", className="fw-semibold mb-1"),
            dcc.Dropdown(
                id=AdvControlIds.INSTRUMENT_SELECT,
                options=[],
                value=None,
                placeholder="Select instrument...",
                clearable=True,
            ),

            html.Hr(className="my-3"),

            # Axis selection
            html.Label("X Axis", className="fw-semibold mb-1"),
            dcc.Dropdown(
                id=AdvControlIds.X_AXIS_SELECT,
                options=[],
                value=None,
                placeholder="Select field...",
                clearable=False,
            ),
            html.Label("Y Axis", className="fw-semibold mt-2 mb-1"),
            dcc.Dropdown(
                id=AdvControlIds.Y_AXIS_SELECT,
                options=[],
                value=None,
                placeholder="Select field...",
                clearable=False,
            ),
        ]),
    )


def _plot_area():
    minimap_toggle = dbc.Checklist(
        id=AdvControlIds.MINIMAP_TOGGLE,
        options=[{"label": "Show Map", "value": "show"}],
        value=["show"],
        switch=True,
        className="mb-2",
    )

    minimap = dbc.Collapse(
        dbc.Card(
            dbc.CardBody(
                dcc.Graph(
                    id=AdvGraphIds.MINI_MAP,
                    style={"height": "250px"},
                    config={"displayModeBar": False},
                ),
                className="p-1",
            ),
            className="mb-2",
        ),
        id=AdvContainerIds.MINIMAP_CARD,
        is_open=True,
    )

    data_plot = dcc.Graph(
        id=AdvGraphIds.DATA_PLOT,
        style={"height": "60vh", "minHeight": "400px"},
        config={"displayModeBar": True, "responsive": True},
    )

    return html.Div([minimap_toggle, minimap, data_plot])


def make_layout():
    stores = html.Div([
        dcc.Store(id=AdvStoreIds.GLIDER_DATA_STORE, storage_type="session"),
        dcc.Store(id=AdvStoreIds.INSTRUMENT_DF_STORE, storage_type="memory"),
        dcc.Store(id=AdvStoreIds.SELECTION_STORE, storage_type="memory"),
    ])

    return dbc.Container(
        [
            stores,
            dbc.Row(
                [
                    dbc.Col(
                        _controls_card(),
                        xs=12, lg=3,
                        className="mb-3 mb-lg-0",
                    ),
                    dbc.Col(
                        _plot_area(),
                        xs=12, lg=9,
                    ),
                ],
            ),
        ],
        fluid=True,
        className="p-2 p-md-3",
    )


layout = make_layout()
