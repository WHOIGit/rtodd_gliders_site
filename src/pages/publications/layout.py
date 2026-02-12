from dash import html
import dash_bootstrap_components as dbc


def make_layout():
    """Return the layout for Page 1."""
    return dbc.Container(
        [
            html.H1("Publications", className="mb-4"),
            html.P("This is a starter layout template for PUBLICATIONS"),
            # Add your components here...
        ],
        fluid=True,
    )


# Expose a layout object that main.py imports
layout = make_layout()

