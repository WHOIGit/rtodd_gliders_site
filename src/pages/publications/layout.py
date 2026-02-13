import dash
from dash import html

app = dash.get_app()


def make_layout(asset: str = "publications.html") -> html.Div:
    src = app.get_asset_url(asset)

    return html.Div(
        [
            html.H1(
                "Publications",
                style={
                    "textAlign": "center",
                    "marginBottom": "40px",
                },
            ),
            html.Div(
                html.Iframe(
                    id="publications-iframe",
                    src=src,
                    style={
                        "height": "1000px",
                        "width": "100%",
                        "maxWidth": "800px",
                        "border": "none",
                    },
                ),
                style={
                    "display": "flex",
                    "justifyContent": "center",
                },
            ),
        ],
        style={
            "padding": "40px 20px",
        },
    )


layout = make_layout()
