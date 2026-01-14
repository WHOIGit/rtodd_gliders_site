from dash import html, dcc

from .names import *

def float_box():
    return html.Div(
        [
            html.H5("Spray Glider Operations at WHOI", className="mb-2"),
            html.P(
                "Autonomous underwater gliders are able to fly through the ocean for months at a time, "
                "returning measurement of many key water properties. "
                "Our group at the Woods Hole Oceanographic Institution (WHOI) "
                "operates a fleet of Spray gliders as a contribution to the "
                "Global Ocean Observing System and in support of various oceanographic field campaigns"
            ),
            html.P('Our work is funded by:'),
            html.Img(src="/assets/sponsors.png", style={"width": "250px"}),
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

