# callbacks.py
import datetime as dt
from collections import defaultdict

from dash import Input, Output, State, dcc

from names import ControlIds, TabsIds, TextIds, IntervalIds, StoreIds, InstrumentsIds, MapIds
import data_loader
from utils import range_slider_marks


def register_callbacks(app):

    @app.callback(
        Output(ControlIds.GLIDER_CHECKLIST, "options"),
        Output(ControlIds.GLIDER_CHECKLIST, "value"),
        Output(TextIds.STATUS, "children"),
        Input(ControlIds.REFRESH_BTN_ID, "n_clicks"),
        #Input(IntervalIds.FILE_REFRESH, "n_intervals"),
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

    # 2) When glider selection changes, load data, update time slider + tabs, and store data
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
            empty_tabs = [dcc.Tab(label="Instruments", value=TabsIds.INSTRUMENTS_TAB_VALUE)]
            return (
                None,
                0,
                1,
                [0, 1],
                {0: "0", 1: "1"},
            )

        gdl = data_loader.GliderDataLoader()
        gdl.set_selected_files(selected_files)

        store_data = dict(latlon_dfs={}, instrument_dfs=defaultdict(dict), dv_fields={})
        inst_names = set()

        # Dependent variable metadata
        for inst_field_tag,field_meta in gdl.dv_fields().items():
            store_data['dv_fields'][inst_field_tag] = field_meta
            inst_name = inst_field_tag.split(':')[0]
            inst_names.add(inst_name)

        # Dataframes per glider and per instrument
        for glider_sn in gdl.glider_sns():
            df_latlon = gdl.build_glider_df(glider_sn)
            store_data['latlon_dfs'][glider_sn] = df_latlon.to_dict('records')

            # per-instrument dfs for plots
            for inst_name in gdl.instruments():
                if gdl.instrument_in_glider(inst_name, glider_sn):
                    df = gdl.build_instrument_df(glider_sn, inst_name)
                    store_data['instrument_dfs'][glider_sn][inst_name] = df.to_dict('records')


        # Use Unixtime for slider bounds
        t_min, t_max = gdl.time_range()

        # Build tick marks from unixtime
        marks = range_slider_marks(t_min, t_max)

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



    @app.callback(
        Output(InstrumentsIds.DV_DROPDOWN, "options"),
        Output(InstrumentsIds.DV_DROPDOWN, "value"),
        Input(StoreIds.DATA, "data"),
    )
    def update_dv_options(store_data):
        if not store_data or "dv_fields" not in store_data:
            return [], []

        options = []
        for key, field_meta in store_data['dv_fields'].items():
            inst_name,field_id = key.split(':',1)
            sns = list(field_meta.keys())
            sn0 = sns[0]
            short_name = field_meta[sn0].get("short_name")
            units = field_meta[sn0].get("units")
            comment = field_meta[sn0].get('comment')
            label = f"{key} ({','.join(sns)})"
            if short_name: label = f'{label} "{short_name}"'
            if units: label = f'{label} [{units}]'
            if comment: label = f'{label} - {comment}'
            options.append(dict(label=label, value=key))

        return options, []
