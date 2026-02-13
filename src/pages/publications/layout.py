from pathlib import Path

from dash import html, dcc


def make_layout(html_file: str) -> html.Div:
    html_text = (Path.cwd() / html_file).read_text(encoding="utf-8")
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

layout = make_layout("config/publications.html")
