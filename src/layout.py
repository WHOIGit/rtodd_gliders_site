# layout.py
import os

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

    NAVBAR_TOGGLE_ID = "navbar-toggler"
    NAVBAR_COLLAPSE_ID = "navbar-collapse"

    nav_links = []
    for page in dash.page_registry.values():
        href = page["path"]
        if os.environ.get('PROD', 'False').lower() in ("true", "1"):
            href = '/dashapp'+page["path"]

        nav_links.append(
            dbc.NavItem(
                dbc.NavLink(
                    page["name"],
                    href=href,
                    active="exact",
                )
            )
        )

    navbar = dbc.Navbar(
        dbc.Container(
            [
                dbc.NavbarBrand("GliderApp", href="/"),
                dbc.NavbarToggler(id=NAVBAR_TOGGLE_ID, n_clicks=0),
                dbc.Collapse(
                    dbc.Nav(
                        nav_links,
                        className="ms-auto",
                        navbar=True,
                    ),
                    id=NAVBAR_COLLAPSE_ID,
                    is_open=False,
                    navbar=True,
                ),
            ],
            fluid=True,
        ),
        className="mb-0",
    )

    # Clientside callback to toggle the collapse on mobile
    dash.clientside_callback(
        """
        function(n_clicks, is_open) {
            if (n_clicks > 0) { return !is_open; }
            return is_open;
        }
        """,
        dash.Output(NAVBAR_COLLAPSE_ID, "is_open"),
        dash.Input(NAVBAR_TOGGLE_ID, "n_clicks"),
        dash.State(NAVBAR_COLLAPSE_ID, "is_open"),
    )

    return navbar


def create_layout():
    alert_banner = dbc.Alert(
        "",
        id=AlertIds.BANNER,
        color="warning",
        dismissable=True,
        is_open=False,
        style={
            "position": "fixed",
            "top": "60px",
            "left": "50%",
            "transform": "translateX(-50%)",
            "zIndex": 1050,
            "maxWidth": "90vw",
        },
    )

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
            alert_banner,
            pages_container,
        ],
        fluid=True,
        className="p-0 d-flex flex-column vh-100",
    )
    return layout
