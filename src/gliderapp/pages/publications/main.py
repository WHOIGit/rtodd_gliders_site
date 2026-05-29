import os
from pathlib import Path

import dash
from dash import html, dcc

from gliderapp.utils import static_layout

PUBLICATIONS_HTML_PATH = os.environ.get("PUBLICATIONS_HTML_PATH", "config/publications.html")

html_text = (Path.cwd() / PUBLICATIONS_HTML_PATH).read_text(encoding="utf-8")
layout = html.Div([
            html.H1('Publications Related to WHOI Spray Glider Operations',
                    style={"textAlign": "center", "marginBottom": "40px"}),
            dcc.Markdown(html_text, dangerously_allow_html=True)],
            style={"maxWidth": "840px", "margin": "0 auto", "padding": "40px 20px"},
        )

# Register this file as a Dash "page"
dash.register_page(
    __name__,
    path="/publications",             # URL path
    name="Publications",              # Text shown in navbar (via page["name"])
    title="Gliders - Publications", # <title> of the browser tab
)
