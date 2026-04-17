# app.py
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

import dash
import dash_bootstrap_components as dbc
from flask import send_from_directory, abort

from layout import create_layout
from names import *
from utils import CONFIG_ASSETS_DIR, CONFIG_ASSETS_URL_PREFIX, PORTRAITS_DIR, PORTRAITS_URL_PREFIX

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

# Pre-warm the map data cache at startup so the first visitor doesn't trigger
# a 20-second blocking load in the single Gunicorn worker.
from pages.map.main import load_mapdata, source_version as _map_source_version
load_mapdata()
logging.info(f'Data Preload Timestamp: {_map_source_version()}')

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
