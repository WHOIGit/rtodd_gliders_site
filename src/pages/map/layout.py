from dash import html, dcc

from .names import *

def float_box():
    return html.Div(
        [
            html.H5("Map Info", className="mb-2"),
            html.P(
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
                "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua."
            ),
        ],
        className="map-overlay",
    )


def main_row():
    map_div = dcc.Graph(
        id=MapIds.GRAPH,
        style={"height": "100%", "width": "100%"},
        config={"displayModeBar": True,"responsive": True},
    )

    floatbox_div = float_box()

    return html.Div(
        [
            map_div,
            floatbox_div
        ],
        className="flex-grow-1 d-flex",
        style={"minHeight": 0},
    )



# Expose a layout object that main.py imports
layout = main_row()

