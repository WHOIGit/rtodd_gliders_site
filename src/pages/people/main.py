import dash

# Dash expects a `layout` variable in the page module
from .layout import layout

# Register this file as a Dash "page"
dash.register_page(
    __name__,
    path="/people",             # URL path
    name="People",              # Text shown in navbar (via page["name"])
    title="GliderApp - People", # <title> of the browser tab
)
