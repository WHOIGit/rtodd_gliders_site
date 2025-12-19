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
    pullout_btn = html.Div(
        dbc.Button(
            "Sidebar >>",
            id="open-drawer",
            n_clicks=0,
            color="secondary",
            size="sm",
        ),
    )

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
                pullout_btn,

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


def time_slider_card():
    card = dbc.Card(
        [
            dbc.CardHeader("Time Range"),
            dbc.CardBody(
                [
                    dcc.RangeSlider(
                        id=ControlIds.TIME_RANGE,
                        min=0,
                        max=1,
                        step=1,
                        value=[0, 1],
                        marks={0: "0", 1: "1"},
                        tooltip={"placement": "bottom", "always_visible": False},
                    ),
                    html.Div(
                        id=TextIds.TIMERANGE_READOUT,
                        className="mt-2 text-muted",
                        style={"fontSize": "0.85rem"},
                    ),
                ]
            ),
        ],
        class_name="mb-3",
    )
    return card

def gliders_card():
    card = dbc.Card(
        [
            dbc.CardHeader("Gliders"),
            dbc.CardBody([
                dcc.Checklist(
                    id=ControlIds.GLIDER_CHECKLIST,
                    options=[],
                    value=[],
                ),
                dbc.Button(
                    "Refresh file list",
                    id=ControlIds.REFRESH_BTN_ID,
                    n_clicks=0,
                    size="sm",
                    className="mb-2",
                ),
                dbc.Alert(
                    id=TextIds.STATUS,
                    children="Waiting for data files in ./data/ ...",
                    color="info",
                    class_name="mb-0",
                ),
            ]),
        ],
        class_name="mb-3",
    )
    return card


def left_pullout(content):
    # The pullout panel itself
    pullout_panel = dbc.Offcanvas(
        children=content,
        id=DivIds.LEFT_DRAWER,
        title="Sidebar",
        is_open=False,
        placement="start",  # slide from the left
        backdrop=False,  # don't dim / block the rest of the screen
        scrollable=True,
    )
    return pullout_panel


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
            dcc.Store(id=StoreIds.DATA),
            make_navbar(),
            left_pullout([
                html.H5("Controls"),
                gliders_card(),
                time_slider_card(),
            ]),
            pages_container,

        ],
        fluid=True,
        className="p-0 d-flex flex-column vh-100",
    )
    return layout
