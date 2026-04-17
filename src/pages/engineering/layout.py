from dash import html, dcc
import dash_bootstrap_components as dbc

from .names import EngStoreIds, EngControlIds, EngGraphIds


def make_layout():
    stores = html.Div([
        dcc.Store(id=EngStoreIds.GLIDER_DATA_STORE, storage_type="memory"),
        dcc.Store(id=EngStoreIds.ENG_SUMMARY_STORE, storage_type="memory"),
    ])

    glider_control = html.Div([
        html.Label("Glider", className="fw-semibold mb-1"),
        dcc.Dropdown(
            id=EngControlIds.GLIDER_SELECT,
            options=[],
            value=None,
            placeholder="Select glider...",
            clearable=True,
        ),
    ], className="mb-2")

    dive_control = html.Div([
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
        ]),
    ], className="mb-2")

    mission_fig = dcc.Loading(
        type="circle",
        children=dcc.Graph(
            id=EngGraphIds.MISSION_FIG,
            style={"height": "75vh", "minHeight": "500px"},
            config={"displayModeBar": True, "responsive": True},
        ),
    )

    dive_fig = dcc.Loading(
        type="circle",
        children=dcc.Graph(
            id=EngGraphIds.DIVE_FIG,
            style={"height": "75vh", "minHeight": "500px"},
            config={"displayModeBar": True, "responsive": True},
        ),
    )

    left_col = dbc.Col([glider_control, mission_fig], xs=12, lg=6)
    right_col = dbc.Col([dive_control, dive_fig],     xs=12, lg=6)

    return dbc.Container(
        [stores, dbc.Row([left_col, right_col])],
        fluid=True,
        className="p-2 p-md-3",
    )


layout = make_layout()
