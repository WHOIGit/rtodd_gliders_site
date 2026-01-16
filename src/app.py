# app.py

import dash
import dash_bootstrap_components as dbc

from layout import create_layout
from names import *

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

server = app.server

if __name__ == "__main__":
    app.run(debug=True)
