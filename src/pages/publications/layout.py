from pathlib import Path

from dash import html, dcc

ASSETS_DIR = Path.cwd() / "assets"

def make_layout(asset: str = "publications.html") -> html.Div:
    html_text = (ASSETS_DIR / asset).read_text(encoding="utf-8")
    return html.Div(
        [
            html.H1("Publications", style={"textAlign": "center", "marginBottom": "40px"}),

            # Centered container, max width 800, responsive
            html.Div(
                dcc.Markdown(html_text, dangerously_allow_html=True),
                style={"maxWidth": "800px", "margin": "0 auto"},
            ),
        ],
        style={"padding": "40px 20px"},
    )

layout = make_layout()
