# people_page.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

import dash
from dash import html
import dash_bootstrap_components as dbc

# Adjust to your app structure:
# - Put this file wherever your pages live
# - Ensure you have a default image in assets/, e.g. assets/default-person.png


PORTRAITS_DIR = Path("config/people-imgs").resolve()
PORTRAITS_URL_PREFIX = "/people/img/"
DEFAULT_IMAGE = os.environ.get("PORTRAITS_DEFAULT", "default.jpg")


def load_people_yaml(yaml_path: str | Path) -> Dict[str, Any]:
    yaml_path = Path(yaml_path)
    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # Normalize missing keys
    data.setdefault("current_members", [])
    data.setdefault("previous_members", [])
    return data


def _asset_url(filename: str) -> str:
    # Dash assets: /assets/<filename> (respects requests_pathname_prefix)
    app_prefix = dash.get_app().config['requests_pathname_prefix']
    filepath = app_prefix[:-1] + PORTRAITS_URL_PREFIX + filename
    return filepath


def _pick_image(image_field: Optional[str]) -> str:
    """
    image_field: string like "people/jane.png" or "jane.png" relative to assets/.
    If missing/blank/not found on disk, fall back to DEFAULT_IMAGE.
    """
    if not image_field or not str(image_field).strip():
        return _asset_url(DEFAULT_IMAGE)

    # Try to verify existence on disk.
    img_path = str(image_field).lstrip("/")
    if (PORTRAITS_DIR / img_path).exists():
        return _asset_url(img_path)
    return _asset_url(DEFAULT_IMAGE)


def person_card(person: Dict[str, Any], card_bg: str, card_height: int = 170) -> dbc.Card:
    name = (person.get("name") or "").strip()
    role = (person.get("role") or "").strip()
    email = (person.get("email") or "").strip()
    website = (person.get("website") or "").strip()
    desc = (person.get("description") or "").strip()
    image = _pick_image(person.get("image"))

    icon_links = []
    if email:
        icon_links.append(
            html.A(
                html.I(className="bi bi-envelope"),
                href=f"mailto:{email}",
                className="ms-2 text-decoration-none",
                title="Send email",
                style={"fontSize": "1.1rem"},
            )
        )
    if website:
        icon_links.append(
            html.A(
                html.I(className="bi bi-globe"),
                href=website,
                target="_blank",
                rel="noreferrer",
                className="ms-2 text-decoration-none",
                title="Visit website",
                style={"fontSize": "1.1rem"},
            )
        )

    # very light grey background for previous members
    card_bg = card_bg or "white"  # bootstrap-ish "gray-100"

    return dbc.Card(
        dbc.Row(
            [
                dbc.Col(
                    html.Img(
                        src=image,
                        alt=name or "Person photo",
                        style={
                            "width": "140px",
                            "height": f"{card_height}px",
                            "borderRadius": "12px",
                            "objectFit": "cover",
                        },
                    ),
                    xs=12,
                    sm=4,
                    md=3,
                    className="d-flex align-items-center justify-content-center p-3",
                ),
                dbc.Col(
                    [
                        html.Div(
                            [
                                html.H3(
                                    name or "—",
                                    className="mb-0",
                                    style={"fontWeight": 700},
                                ),
                                html.Div(icon_links, className="d-flex align-items-center"),
                            ],
                            className="d-flex align-items-center justify-content-between mb-1",
                        ),
                        html.Div(role, className="mb-2", style={"color": "#6c757d"}) if role else None,
                        html.P(desc, className="mb-0", style={"overflow": "hidden"}) if desc else None,
                    ],
                    xs=12,
                    sm=8,
                    md=9,
                    className="p-3",
                    style={
                        "height": f"{card_height}px",
                        "overflow": "hidden",  # keeps all cards same height
                    },
                ),
            ],
            className="g-0",
            style={"height": f"{card_height}px"},
        ),
        className="mb-3 shadow-sm",
        style={
            "borderRadius": "16px",
            "overflow": "hidden",
            "height": f"{card_height + 16}px",  # small cushion for card chrome
            "backgroundColor": card_bg,
        },
    )


def people_section(title: str, people: List[Dict[str, Any]], bg: str = None, card_heights: int = 170) -> html.Div:
    cards = [person_card(p, card_bg=bg, card_height=card_heights) for p in (people or [])]
    return html.Div(
        [
            html.H2(title, className="mt-4 mb-3"),
            html.Div(cards) if cards else html.Div("None listed.", className="text-muted"),
        ]
    )


def make_people_layout(yaml_path: str | Path) -> dbc.Container:
    data = load_people_yaml(yaml_path)

    current_members = data.get("current_members", []) or []
    previous_members = data.get("previous_members", []) or []

    # If you want previous members to be simpler (e.g., no images), you can
    # keep using the same card renderer; it will just omit missing fields.

    return dbc.Container(
        [
            html.H1("People", className="mt-4"),
            people_section("Team", current_members),
            people_section("Previous Members", previous_members, bg="#f8f9fa", card_heights=100),
            html.Div(className="mb-5"),
        ],
        fluid=False,
        style={"maxWidth": "800px"},
    )


# Example export for Dash Pages:
layout = make_people_layout("config/people.yml")
