# app.py
import dash
import dash_bootstrap_components as dbc

from layout import create_layout
from callbacks import register_callbacks
from map import register_map_plots
from plots import register_instrument_plots

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
register_instrument_plots(app)
register_map_plots(app)

server = app.server

if __name__ == "__main__":
    app.run(debug=True)
