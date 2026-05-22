# layout.py
import os

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc

from names import *

# Component IDs shared between the layout builders and register_callbacks().
# Kept at module scope so callbacks can be registered exactly once, outside
# the function-based layout (see register_callbacks() for why).
NAVBAR_TOGGLE_ID = "navbar-toggler"
NAVBAR_COLLAPSE_ID = "navbar-collapse"
ANALYTICS_SINK_ID = "analytics-sink"


def make_navbar() -> dbc.Navbar:
    """
    Top navigation bar with manual structure including Plotting dropdown.
    """
    # TODO WHOI image

    prod_env = os.environ.get('PROD', 'False').lower() in ("true", "1")
    subpath = os.environ.get("SUBPATH", "/dashapp" if prod_env else "").rstrip("/")

    def href(path):
        return subpath + path

    nav_links = [
        dbc.NavItem(
            dbc.NavLink("Home", href=href("/"), active="exact")
        ),
        dbc.DropdownMenu([
            dbc.DropdownMenuItem("Map - Realtime", href=href("/plotting/realtime")),
            dbc.DropdownMenuItem("Map - Archived", href=href("/plotting/archived")),
            dbc.DropdownMenuItem("Profiles", href=href("/plotting/profiles")),
            dbc.DropdownMenuItem("Engineering", href=href("/plotting/engineering")),
        ], label="Plotting", nav=True, in_navbar=True),
        dbc.NavItem(
            dbc.NavLink("Data", href=href("/datapage"), active="exact")
        ),
        dbc.NavItem(
            dbc.NavLink("People", href=href("/people"), active="exact")
        ),
        dbc.NavItem(
            dbc.NavLink("Publications", href=href("/publications"), active="exact")
        ),
    ]

    navbar = dbc.Navbar(
        dbc.Container(
            [
                dbc.NavbarBrand("WHOI Spray Glider Operations", href=href("/")),
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
            # GoatCounter SPA tracking: hidden output target for the
            # route-change counter (registered in register_callbacks()).
            html.Div(id=ANALYTICS_SINK_ID, disable_n_clicks=True,
                     style={"display": "none"}),
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


def register_callbacks():
    """
    Register all layout-level clientside callbacks. Call this exactly once,
    after the Dash app has been created.

    These must NOT be registered inside create_layout()/make_navbar():
    create_layout is the function-based ``app.layout``, which Dash re-runs on
    every page load. Registering callbacks there appends a duplicate entry to
    Dash's global callback list on each load, desyncing the callback graph the
    browser downloads (``/_dash-dependencies``) from the one the server
    dispatches against — which raises
    ``CallbackException: Inputs do not match callback definition``.
    """
    # Toggle the navbar collapse on mobile, and dismiss it on nav-link click.
    dash.clientside_callback(
        """
        function(n_clicks, pathname, is_open) {
            var triggered = window.dash_clientside.callback_context.triggered;
            if (!triggered || !triggered.length) return is_open;
            var prop = triggered[0].prop_id;

            // Toggler button: flip open/closed
            if (prop.indexOf('""" + NAVBAR_TOGGLE_ID + """') !== -1) {
                return !is_open;
            }

            // Page navigation: close the menu
            return false;
        }
        """,
        dash.Output(NAVBAR_COLLAPSE_ID, "is_open"),
        dash.Input(NAVBAR_TOGGLE_ID, "n_clicks"),
        dash.Input(dash.dash._ID_LOCATION, "pathname"),
        dash.State(NAVBAR_COLLAPSE_ID, "is_open"),
    )

    # Close the navbar menu on a click outside it.
    dash.clientside_callback(
        """
        function(n) {
            // Attach a one-time listener pattern for outside clicks
            if (!window._navCollapseListener) {
                window._navCollapseListener = true;
                document.addEventListener('click', function(e) {
                    var collapse = document.getElementById('""" + NAVBAR_COLLAPSE_ID + """');
                    var toggler = document.getElementById('""" + NAVBAR_TOGGLE_ID + """');
                    if (!collapse || !toggler) return;
                    var isOpen = collapse.classList.contains('show');
                    if (isOpen && !collapse.contains(e.target) && !toggler.contains(e.target)) {
                        toggler.click();
                    }
                });
            }
            return window.dash_clientside.no_update;
        }
        """,
        dash.Output(NAVBAR_TOGGLE_ID, "className"),
        dash.Input(NAVBAR_TOGGLE_ID, "n_clicks"),
    )

    # Count a GoatCounter pageview on every route change. Dash navigation is
    # client-side, so count.js's onload counter (disabled via no_onload in
    # app.py) would miss everything after the initial load. This fires for the
    # first route too, and retries briefly in case the async count.js hasn't
    # loaded yet. No-op when ANALYTICS_ENDPOINT is unset (window.goatcounter
    # undefined).
    dash.clientside_callback(
        """
        function(pathname) {
            function send(tries) {
                if (window.goatcounter && window.goatcounter.count) {
                    window.goatcounter.count({path: pathname});
                } else if (tries > 0) {
                    setTimeout(function() { send(tries - 1); }, 200);
                }
            }
            if (pathname) { send(20); }
            return window.dash_clientside.no_update;
        }
        """,
        dash.Output(ANALYTICS_SINK_ID, "children"),
        dash.Input(dash.dash._ID_LOCATION, "pathname"),
    )
