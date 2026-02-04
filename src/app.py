# app.py
import os

import dash
import dash_bootstrap_components as dbc

from layout import create_layout
from names import *

external_stylesheets = [dbc.themes.BOOTSTRAP]

dash_kwargs = {
    "use_pages": True,
    "external_stylesheets": external_stylesheets,
    "suppress_callback_exceptions": True,
}

TRUTHY = ("true", "1", "yes", "on", "en", "enable", "enabled")
PROD_ENV = os.environ.get("PROD", "False").lower() in TRUTHY

if PROD_ENV:
    dash_kwargs.update(
        {
            "routes_pathname_prefix": "/",
            "requests_pathname_prefix": "/dashapp/",
            "assets_url_path": "/assets",
        }
    )

app = dash.Dash(
    __name__,
    **dash_kwargs,
)
app.title = "Glider Dashboard"

# Use function-based layout (nice for larger apps)
app.layout = create_layout

server = app.server

if __name__ == "__main__":
    debug = os.getenv("DEBUG", "False").lower() in TRUTHY
    app.run(debug=debug)
