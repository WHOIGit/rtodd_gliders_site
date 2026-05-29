# app.py
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

import dash
import dash_bootstrap_components as dbc
from flask import send_from_directory, abort

from .layout import create_layout, register_callbacks
from .names import *
from .utils import CONFIG_ASSETS_DIR, CONFIG_ASSETS_URL_PREFIX, PORTRAITS_DIR, PORTRAITS_URL_PREFIX

external_stylesheets = [dbc.themes.BOOTSTRAP,
    "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css",
    ]

dash_kwargs = {
    "use_pages": True,
    "external_stylesheets": external_stylesheets,
    "suppress_callback_exceptions": True,
}

TRUTHY = ("true", "1", "yes", "on", "en", "enable", "enabled")
PROD_ENV = os.environ.get("PROD", "False").lower() in TRUTHY
SUBPATH = os.environ.get("SUBPATH", "/dashapp" if PROD_ENV else "").rstrip("/")

if PROD_ENV:
    dash_kwargs.update(
        {
            "routes_pathname_prefix": "/",
            "requests_pathname_prefix": f"{SUBPATH}/" if SUBPATH else "/",
            "assets_url_path": "/assets",
        }
    )

app = dash.Dash(
    __package__,
    **dash_kwargs,
)
app.title = "Glider Dashboard"

# --- GoatCounter analytics -------------------------------------------------
# When ANALYTICS_ENDPOINT is set, inject the self-hosted GoatCounter tracker.
# `no_onload` disables count.js's automatic pageview; instead the clientside
# callback in layout.py counts every route — including the initial load — so
# Dash's client-side page changes are tracked exactly once each.
ANALYTICS_ENDPOINT = os.environ.get("ANALYTICS_ENDPOINT", "").rstrip("/")
if ANALYTICS_ENDPOINT:
    app.index_string = """<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <script>window.goatcounter = {no_onload: true}</script>
        <script data-goatcounter=\"""" + ANALYTICS_ENDPOINT + """/count"
                async src=\"""" + ANALYTICS_ENDPOINT + """/count.js"></script>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""

# Use function-based layout (nice for larger apps)
app.layout = create_layout

# Register layout-level clientside callbacks exactly once. Must happen here,
# not inside create_layout(), since Dash re-runs a function-based layout on
# every page load.
register_callbacks()

server = app.server


# Optional: only allow typical image extensions
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

@server.get(CONFIG_ASSETS_URL_PREFIX+"<path:filename>")
def config_assets(filename: str):
    p = (CONFIG_ASSETS_DIR / filename).resolve()
    if CONFIG_ASSETS_DIR not in p.parents and p != CONFIG_ASSETS_DIR:
        abort(404)
    if p.suffix.lower() not in ALLOWED_EXTS:
        abort(404)
    if not p.exists() or not p.is_file():
        abort(404)
    return send_from_directory(CONFIG_ASSETS_DIR, filename)

@server.get(PORTRAITS_URL_PREFIX+"<path:filename>")
def people_portraits(filename: str):
    # basic safety checks
    p = (PORTRAITS_DIR / filename).resolve()
    if PORTRAITS_DIR not in p.parents and p != PORTRAITS_DIR:
        abort(404)

    if p.suffix.lower() not in ALLOWED_EXTS:
        abort(404)

    if not p.exists() or not p.is_file():
        abort(404)

    # send file; Flask will set Content-Type
    # (you can also add cache headers if desired)
    return send_from_directory(PORTRAITS_DIR, filename)


if __name__ == "__main__":
    debug = os.getenv("DEBUG", "False").lower() in TRUTHY
    app.run(debug=debug)
