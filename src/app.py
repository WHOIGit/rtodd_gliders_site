# app.py
import dash
import dash_bootstrap_components as dbc

from layout import create_layout
from callbacks import register_callbacks
from plots import register_plot_callbacks

external_stylesheets = [dbc.themes.BOOTSTRAP]

app = dash.Dash(
    __name__,
    external_stylesheets=external_stylesheets,
    suppress_callback_exceptions=True,
)
app.title = "Glider Dashboard"

# Use function-based layout (nice for larger apps)
app.layout = create_layout

# Register callbacks from separate modules
register_callbacks(app)
register_plot_callbacks(app)

server = app.server

if __name__ == "__main__":
    app.run(debug=True)
