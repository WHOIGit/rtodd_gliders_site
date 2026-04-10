from dash import html, dcc
import dash_bootstrap_components as dbc

from .names import EngStoreIds, EngControlIds, EngGraphIds


def _controls_card():
    return dbc.Card(
        dbc.CardBody([
            html.H5("Engineering", className="mb-3"),

            html.Label("Glider", className="fw-semibold mb-1"),
            dcc.Dropdown(
                id=EngControlIds.GLIDER_SELECT,
                options=[],
                value=None,
                placeholder="Select glider...",
                clearable=True,
            ),

            html.Hr(className="my-3"),

            html.Label("Dive", className="fw-semibold mb-1"),
            dbc.InputGroup([
                dcc.Input(
                    id=EngControlIds.DIVE_INPUT,
                    type="number",
                    min=1,
                    placeholder="Dive #",
                    className="form-control text-center",
                    style={"textAlign": "center", "lineHeight": "normal", "height": "38px"},
                    debounce=True,
                ),
                dbc.Button("▲", id=EngControlIds.DIVE_NEXT, color="secondary", outline=True, size="sm"),
                dbc.Button("▼", id=EngControlIds.DIVE_PREV, color="secondary", outline=True, size="sm"),
            ], className="mb-1"),
        ]),
    )


def _plot_area():
    mission_fig = dcc.Loading(
        type="circle",
        children=dcc.Graph(
            id=EngGraphIds.MISSION_FIG,
            style={"height": "55vh", "minHeight": "400px"},
            config={"displayModeBar": True, "responsive": True},
        ),
    )

    dive_fig = dcc.Loading(
        type="circle",
        children=dcc.Graph(
            id=EngGraphIds.DIVE_FIG,
            style={"height": "55vh", "minHeight": "400px"},
            config={"displayModeBar": True, "responsive": True},
        ),
    )

    return html.Div([mission_fig, dive_fig])


def make_layout():
    stores = html.Div([
        dcc.Store(id=EngStoreIds.GLIDER_DATA_STORE, storage_type="session"),
        dcc.Store(id=EngStoreIds.ENG_SUMMARY_STORE, storage_type="memory"),
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
