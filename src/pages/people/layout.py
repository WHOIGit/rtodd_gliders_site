from pathlib import Path

import yaml
from dash import html
import dash_bootstrap_components as dbc


def _person_block(name: str, role: str, *, bottom_margin: str = "mb-3"):
    return html.P(
        [
            html.Strong(name),
            html.Br(),
            html.Span(role, className="text-muted"),
        ],
        className=f"text-center {bottom_margin}",
    )

def _prev_person_block(name: str, role: str, *, bottom_margin: str = "mb-2"):
    return html.P(
        [
            html.Strong(name),
            ' — ',
            html.Span(role, className="text-muted"),
        ],
        className=f"text-center {bottom_margin}",
    )


def make_layout(yml_path: str | Path = "../config/people.yml"):
    """Return the layout for the People page, built from a YAML template."""
    yml_path = Path(yml_path)

    with yml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    title = data.get("title", "People")
    current_team = data.get("current_team", []) or []
    previously = data.get("previously", []) or []

    current_blocks = [
        _person_block(p.get("name", ""), p.get("role", ""), bottom_margin="mb-3")
        for p in current_team
    ]
    if current_blocks:
        # tighten last item
        current_blocks[-1].className = "text-center mb-0"

    prev_blocks = [
        _prev_person_block(p.get("name", ""), p.get("role", ""), bottom_margin="mb-2")
        for p in previously
    ]
    if prev_blocks:
        prev_blocks[-1].className = "text-center mb-0"

    return dbc.Container(
        [
            dbc.Row(
                dbc.Col(
                    html.H1(title, className="fw-bold mb-5 text-center"),
                    width=12,
                ),
                justify="center",
            ),

            dbc.Row(
                dbc.Col(
                    [
                        html.H5(
                            "Current Team",
                            className="text-uppercase text-muted text-center mb-3",
                        ),
                        html.Div(current_blocks),
                    ],
                    xs=12, md=8, lg=6,
                ),
                justify="center",
            ),

            dbc.Row(
                dbc.Col(
                    [
                        html.H5(
                            "Previously",
                            className="text-uppercase text-muted text-center mt-5 mb-3",
                        ),
                        html.Div(prev_blocks),
                    ],
                    xs=12, md=8, lg=6,
                ),
                justify="center",
            ),
        ],
        fluid=True,
        className="py-4",
    )


# Expose a layout object that main.py imports
layout = make_layout()

