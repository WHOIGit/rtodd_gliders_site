# app.py

import datetime as dt
from collections import defaultdict

import dash
from dash import dcc, Input, Output, State, no_update, ctx
import dash_bootstrap_components as dbc

from layout import create_layout
from names import *
import data_loader
from utils import range_slider_marks

external_stylesheets = [dbc.themes.BOOTSTRAP]

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=external_stylesheets,
    suppress_callback_exceptions=True,
)
app.title = "Glider Dashboard"

# Use function-based layout (nice for larger apps)
app.layout = create_layout



# @app.callback(
#     Output("left-drawer", "is_open"),
#     Input("open-drawer", "n_clicks"),
#     State("left-drawer", "is_open"),
#     prevent_initial_call=True,
# )
# def toggle_drawer(n_clicks, is_open):
#     return not is_open


server = app.server

if __name__ == "__main__":
    app.run(debug=True)
