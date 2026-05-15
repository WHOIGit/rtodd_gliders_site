import os
import dash
from utils import static_layout

HTML_PATH = os.environ.get("HOME_HTML_PATH", "config/homepage.html")
SUBPATH = os.environ.get("SUBPATH", "/dashapp" if os.environ.get("PROD", "False").lower() in ("true", "1") else "").rstrip("/")

try:
    layout = static_layout(HTML_PATH, subst={"SUBPATH": SUBPATH})

    # Register this file as a Dash "page"
    dash.register_page(
        __name__,
        path="/",             # URL path
        name="Home",              # Text shown in navbar (via page["name"])
        title="Gliders - Home", # <title> of the browser tab
    )
except Exception as e:
    print(type(e),e)
