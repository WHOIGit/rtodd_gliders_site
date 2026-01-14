# app.py

import datetime as dt
from collections import defaultdict

import dash
from dash import dcc, Input, Output, State, no_update, ctx
import dash_bootstrap_components as dbc

from layout import create_layout
from names import *
import data_loader
from utils import range_slider_marks

external_stylesheets = [dbc.themes.BOOTSTRAP]

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=external_stylesheets,
    suppress_callback_exceptions=True,
)
app.title = "Glider Dashboard"

# Use function-based layout (nice for larger apps)
app.layout = create_layout


@app.callback(
    Output(ControlIds.GLIDER_CHECKLIST, "options"),
    Output(ControlIds.GLIDER_CHECKLIST, "value"),
    Output(TextIds.STATUS, "children"),
    Input(ControlIds.REFRESH_BTN_ID, "n_clicks"),
    State(ControlIds.GLIDER_CHECKLIST, "value"),
    prevent_initial_call=False,
)
def refresh_file_list(n, current_selection):
    gdl = data_loader.GliderDataLoader()
    files = gdl.files_available  # list of filenames

    if not files:
        return [], [], "No .json files found in ./data/"

    # Build options for the checklist
    options = [{"label": f, "value": f} for f in files]

    # Clean up the current selection: only keep files that still exist
    current_selection = current_selection or []
    selection = [f for f in current_selection if f in files]

    # On first load, if nothing is selected, pick the most recently modified file
    if not selection and n == 0:
        latest = max(
            files,
            key=lambda fn: (gdl.data_dir / fn).stat().st_mtime
        )
        selection = [latest]

    status = (
        f"Found {len(files)} .json file(s) in ./data/. "
        f"Selected: {', '.join(selection) if selection else 'None'}"
    )
    return options, selection, status

@app.callback(
    Output(StoreIds.DATA, "data"),
    Output(ControlIds.TIME_RANGE, "min"),
    Output(ControlIds.TIME_RANGE, "max"),
    Output(ControlIds.TIME_RANGE, "value"),
    Output(ControlIds.TIME_RANGE, "marks"),
    Input(ControlIds.GLIDER_CHECKLIST, "value"),
    State(ControlIds.TIME_RANGE, "min"),
    State(ControlIds.TIME_RANGE, "max"),
    State(ControlIds.TIME_RANGE, "value"),
    prevent_initial_call=True,
)
def load_data_and_update_layout(selected_files, current_min, current_max, current_range):
    # No gliders selected → clear
    if not selected_files:
        return (
            None,
            0,
            1,
            [0, 1],
            {0: "0", 1: "1"},
        )

    gdl = data_loader.GliderDataLoader()
    gdl.set_selected_files(selected_files)

    store_data = dict(latlon_records={}, instrument_records=defaultdict(dict), dv_fields={}, uv_records={})
    inst_names = set()

    # Dependent variable metadata
    for inst_field_tag,field_meta in gdl.dv_fields().items():
        store_data['dv_fields'][inst_field_tag] = field_meta
        inst_name = inst_field_tag.split(':')[0]
        inst_names.add(inst_name)

    # Dataframes per glider and per instrument
    for glider_sn in gdl.glider_sns():
        store_data['latlon_records'][glider_sn] = gdl.build_glider_df(glider_sn).to_dict('records')
        store_data['uv_records'][glider_sn] = gdl.build_uv_df(glider_sn).to_dict('records')

        # per-instrument dfs for plots
        for inst_name in gdl.instruments():
            if gdl.instrument_in_glider(inst_name, glider_sn):
                df = gdl.build_instrument_df(glider_sn, inst_name)
                store_data['instrument_records'][glider_sn][inst_name] = df.to_dict('records')


    # Use Unixtime for slider bounds
    t_min, t_max = gdl.time_range()

    # Build tick marks from unixtime
    marks = range_slider_marks(t_min, t_max, target_mark_count=6)

    # Decide what slider value to use
    if (
        current_min is not None
        and current_max is not None
        and current_range is not None
        and current_min == t_min
        and current_max == t_max
    ):
        # Bounds didn't change → keep user’s current selection
        slider_value = current_range
    else:
        # Bounds changed → reset to full extent
        slider_value = [t_min, t_max]

    return (
        store_data,
        t_min,
        t_max,
        slider_value,
        marks,
    )

# 3) Update time range readout text
@app.callback(
    Output(TextIds.TIMERANGE_READOUT, "children"),
    Input(ControlIds.TIME_RANGE, "drag_value"),
)
def update_time_range_readout(range_vals):
    if not range_vals or len(range_vals) != 2:
        return "No time range selected."
    start, end = range_vals
    start = dt.datetime.fromtimestamp(start).strftime("%Y-%m-%d %H:%M")
    end = dt.datetime.fromtimestamp(end).strftime("%Y-%m-%d %H:%M")
    return f"Time range: {start} – {end}"


@app.callback(
    Output(ControlIds.TIME_RANGE, "value", allow_duplicate=True), # lookout for race conditions w/ load_data_and_update_layout
    Input(ControlIds.TIME_BTN_DAY, "n_clicks"),
    Input(ControlIds.TIME_BTN_WEEK, "n_clicks"),
    Input(ControlIds.TIME_BTN_MONTH, "n_clicks"),
    State(ControlIds.TIME_RANGE, "min"),
    State(ControlIds.TIME_RANGE, "max"),
    prevent_initial_call=True,
)
def set_recent_time_block(n_day, n_week, n_month, t_min, t_max):
    trig = ctx.triggered_id
    if trig is None or t_min is None or t_max is None:
        return no_update

    # Use the latest available time as the block end
    end = float(t_max)

    DAY = 24 * 3600
    WEEK = 7 * DAY
    MONTH = 30 * DAY

    if trig == ControlIds.TIME_BTN_DAY:
        start = end - DAY
    elif trig == ControlIds.TIME_BTN_WEEK:
        start = end - WEEK
    elif trig == ControlIds.TIME_BTN_MONTH:
        start = end - MONTH
    else:
        return no_update

    # Clamp to slider bounds
    start = max(float(t_min), start)
    end = min(float(t_max), end)

    return [int(start), int(end)]


@app.callback(
    Output("left-drawer", "is_open"),
    Input("open-drawer", "n_clicks"),
    State("left-drawer", "is_open"),
    prevent_initial_call=True,
)
def toggle_drawer(n_clicks, is_open):
    return not is_open


server = app.server

if __name__ == "__main__":
    app.run(debug=True)
