import os
import dash
from utils import static_layout

PUBLICATIONS_HTML_PATH = os.environ.get("PUBLICATIONS_HTML_PATH", "config/publications.html")
layout = static_layout(
    PUBLICATIONS_HTML_PATH,
    title="Publications Related to WHOI Spray Glider Operations",
)

# Register this file as a Dash "page"
dash.register_page(
    __name__,
    path="/publications",             # URL path
    name="Publications",              # Text shown in navbar (via page["name"])
    title="Gliders - Publications", # <title> of the browser tab
)
