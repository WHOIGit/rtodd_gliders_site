import os
import dash
from utils import static_layout

HTML_PATH = os.environ.get("DATAPAGE_HTML_PATH", "config/datapage.html")
layout = static_layout(HTML_PATH)

# Register this file as a Dash "page"
dash.register_page(
    __name__,
    path="/datapage",             # URL path
    name="Data",              # Text shown in navbar (via page["name"])
    title="Gliders - Data", # <title> of the browser tab
)
