from dash import html
import dash_bootstrap_components as dbc
from dash import html, dcc

from .names import *

def map_row():
    return html.Div(
    dcc.Graph(
        id=MapIds.GRAPH,
        style={"height": "100%", "width": "100%"},
        config={"displayModeBar": True},
    ),
    className="flex-grow-1 d-flex",
    style={"minHeight": 0},
)



# Expose a layout object that main.py imports
layout = map_row()