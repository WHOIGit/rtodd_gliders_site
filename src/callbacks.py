# callbacks.py
import datetime as dt

from dash import Input, Output, State
from dash import dcc

from names import ControlIds, TabsIds, TextIds, IntervalIds, StoreIds
import data_loader
from utils import range_slider_marks

def _build_tabs(y_columns):
    tabs = [dcc.Tab(label="Info", value=TabsIds.INFO_TAB_VALUE)]
    for col in y_columns:
        tabs.append(dcc.Tab(label=col, value=f"tab-{col}"))
    return tabs


def register_callbacks(app):
    # 1) Refresh datafile list and update glider checklist + status text
    @app.callback(
        Output(ControlIds.GLIDER_CHECKLIST, "options"),
        Output(TextIds.STATUS, "children"),
        Input(IntervalIds.FILE_REFRESH, "n_intervals"),
        State(ControlIds.GLIDER_CHECKLIST, "value"),
        prevent_initial_call=False,
    )
    def refresh_file_list(n, current_selection):
        files = data_loader.list_glider_files()

        if not files:
            return [], [], "No CSV files found in ./data/ (waiting for glider data...)"

        options = [{"label": f, "value": f} for f in files]
        # Default to all files selected
        selection = current_selection or files
        status = f"Found {len(files)} CSV file(s) in ./data/. Selected: {', '.join(selection)}"
        return options, status

    # 2) When glider selection changes, load data, update time slider + tabs, and store data
    @app.callback(
        Output(StoreIds.DATA, "data"),
        Output(ControlIds.TIME_RANGE, "min"),
        Output(ControlIds.TIME_RANGE, "max"),
        Output(ControlIds.TIME_RANGE, "value"),
        Output(ControlIds.TIME_RANGE, "marks"),
        Output(TabsIds.TABS, "children"),
        Output(TabsIds.TABS, "value"),
        Input(ControlIds.GLIDER_CHECKLIST, "value"),
        State(ControlIds.TIME_RANGE, "min"),
        State(ControlIds.TIME_RANGE, "max"),
        State(ControlIds.TIME_RANGE, "value"),
        State(TabsIds.TABS, "value"),
        prevent_initial_call=True,
    )
    def load_data_and_update_layout(selected_files, current_min, current_max, current_range, current_tab):
        # No gliders selected → clear
        if not selected_files:
            empty_tabs = _build_tabs([])
            return (
                None,
                0,
                1,
                [0, 1],
                {0: "0", 1: "1"},
                empty_tabs,
                TabsIds.INFO_TAB_VALUE,
            )

        df = data_loader.load_gliders(selected_files)
        if df.empty:
            empty_tabs = _build_tabs([])
            return (
                None,
                0,
                1,
                [0, 1],
                {0: "0", 1: "1"},
                empty_tabs,
                TabsIds.INFO_TAB_VALUE,
            )

        # Use UNIxtime for slider bounds
        t_min = int(df["unixtime"].min())
        t_max = int(df["unixtime"].max())
        if t_min == t_max:
            t_min, t_max = t_min - 1, t_max + 1

        # Build tick marks from unixtime
        import datetime as dt
        steps = 7
        marks = {}
        delta = (t_max - t_min) / steps
        for i in range(steps + 1):
            tick = int(t_min + i * delta)
            ts = dt.datetime.utcfromtimestamp(tick)
            label = ts.strftime("%Y-%m-%d\n%H:%M")
            marks[tick] = label

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

        # Build tabs from available y-columns
        y_cols = data_loader.get_y_columns(df)
        tabs = _build_tabs(y_cols)

        store_data = {
            "data": df.to_dict("records"),
            "columns": list(df.columns),
            "y_columns": y_cols,
        }

        # Valid tab values: "Info" + one tab per y-column
        valid_tab_values = [TabsIds.INFO_TAB_VALUE] + [f"tab-{col}" for col in y_cols]

        # Use current_tab if it exists and is still valid, otherwise fall back to "Info"
        active_tab = current_tab if current_tab in valid_tab_values else TabsIds.INFO_TAB_VALUE


        return (
            store_data,
            t_min,
            t_max,
            slider_value,
            marks,
            tabs,
            active_tab,
        )

    # 3) Update time range readout text
    @app.callback(
        Output("time-range-readout", "children"),
        Input(ControlIds.TIME_RANGE, "value"),
    )
    def update_time_range_readout(range_vals):
        if not range_vals or len(range_vals) != 2:
            return "No time range selected."
        start, end = range_vals
        start = dt.datetime.fromtimestamp(start).strftime("%Y-%m-%d %H:%M")
        end = dt.datetime.fromtimestamp(end).strftime("%Y-%m-%d %H:%M")
        return f"Time range: {start} – {end}"
