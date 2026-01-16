# layout.py
import dash
from dash import html, dcc
import dash_bootstrap_components as dbc

from names import *

def make_navbar() -> dbc.Navbar:
    """
    Top navigation bar. It iterates over Dash's page registry
    and builds links for each registered page.
    """
    # TODO WHOI image

    nav_items = [dbc.NavbarBrand("GliderApp", href="/")]
    for page in dash.page_registry.values():
        # You can add conditions here to hide certain pages from the navbar
        # e.g., if page.get("name") == "NotShown": continue
        nav_items.append(
            dbc.NavItem(
                dbc.NavLink(
                    page["name"],
                    href=page["path"],
                    active="exact",
                )
            )
        )

    navbar = dbc.Navbar(
        dbc.Container(
            [
                # Left side: Brand
                #pullout_btn,

                # Right side: Links
                dbc.Nav(
                    nav_items,
                    className="ms-auto",  # push nav items to the right
                    navbar=True,
                ),
            ],
            fluid=True,
        ),
        className="mb-0",
    )

    return navbar


def create_layout():
    # instead of dash.page_container, we create our own container with flex-column and w-100
    pages_container = html.Div(
        [
            dcc.Location(id=dash.dash._ID_LOCATION, refresh="callback-nav"),
            html.Div(id=dash.dash._ID_CONTENT, disable_n_clicks=True,
                     className="flex-grow-1 d-flex flex-column w-100",),
            dcc.Store(id=dash.dash._ID_STORE),
            html.Div(id=dash.dash._ID_DUMMY, disable_n_clicks=True),
        ],
        className="flex-grow-1 d-flex flex-column w-100",
        style={"minHeight": 0}
    )

    layout = dbc.Container(
        [
            make_navbar(),
            pages_container,
        ],
        fluid=True,
        className="p-0 d-flex flex-column vh-100",
    )
    return layout
