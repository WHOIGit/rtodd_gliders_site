# plots.py
from dash import Input, Output, dcc, html
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from names import ControlIds, MapIds, TabsIds, StoreIds, InstrumentsIds

PHASE_UP = 0
PHASE_DOWN = 1

def _get_filtered_dfs_for_dv(instrument_dfs, dv, time_range, phase_filter):
    """
    For a DV like 'CTD:t', return:
      inst_name, field_name, entries
    where entries is a list of dicts:
      { "glider_sn": ..., "df": filtered_df, "depth_col": depth_col or None }

    This applies:
      - time_range filter (if 'time' exists)
      - phase filter (if 'phase' exists)
      - chooses depth_col ('depth' or 'p') when present
      - ensures field_name is in df
    """
    try:
        inst_name, field_name = dv.split(":", 1)
    except ValueError:
        return None, None, []

    entries = []

    for glider_sn, inst_map in instrument_dfs.items():
        records = inst_map.get(inst_name)
        if not records:
            continue

        df = pd.DataFrame(records)
        if df.empty:
            continue

        # Time filter (unixtime) if slider + 'time' column
        if time_range and "time" in df.columns:
            start, end = time_range
            df = df[(df["time"] >= start) & (df["time"] <= end)]
            if df.empty:
                continue

        # Phase filter
        if phase_filter != "all" and "phase" in df.columns:
            if phase_filter == "up":
                df = df[df["phase"] == PHASE_UP]
            elif phase_filter == "down":
                df = df[df["phase"] == PHASE_DOWN]
            if df.empty:
                continue

        # Depth column (only needed for depth plots, but we can discover it here)
        depth_col = None
        if "depth" in df.columns:
            depth_col = "depth"
        elif "p" in df.columns:
            depth_col = "p"

        # Must have the requested field
        if field_name not in df.columns:
            continue

        entries.append(
            {
                "glider_sn": glider_sn,
                "df": df,
                "depth_col": depth_col,
            }
        )

    return inst_name, field_name, entries


def register_instrument_plots(app):
    @app.callback(
        Output(InstrumentsIds.PLOTS, "children"),
        Input(StoreIds.DATA, "data"),
        Input(InstrumentsIds.IV_RADIO, "value"),
        Input(InstrumentsIds.DV_DROPDOWN, "value"),
        Input(InstrumentsIds.PHASE_RADIO, "value"),
        Input(ControlIds.TIME_RANGE, "value"),
    )
    def update_instrument_plots(store_data, iv, dv_values, phase_filter, time_range):
        if not store_data or not dv_values:
            return html.Div("No instrument variables selected.", style={"color": "#666"})

        instrument_dfs = store_data.get("instrument_dfs", {})
        if not instrument_dfs:
            return html.Div("No instrument data available.", style={"color": "#666"})

        plots = []

        # Precompute filtered entries for each DV once
        dv_results = {}  # dv -> (inst_name, field_name, entries)
        for dv in dv_values:
            inst_name, field_name, entries = _get_filtered_dfs_for_dv(
                instrument_dfs, dv, time_range, phase_filter
            )
            dv_results[dv] = (inst_name, field_name, entries)

        # -----------------
        # IV = time: stack plots vertically
        # -----------------
        if iv == "time":
            for dv in dv_values:
                inst_name, field_name, entries = dv_results.get(dv, (None, None, []))
                if not inst_name or not entries:
                    plots.append(
                        dbc.Row(
                            dbc.Col(
                                html.Div(
                                    f"No data for {dv} with current IV/phase selection.",
                                    style={"color": "#666"},
                                ),
                                width=12,
                            ),
                            class_name="mb-3",
                        )
                    )
                    continue

                fig = go.Figure()
                any_trace = False

                for entry in entries:
                    glider_sn = entry["glider_sn"]
                    df = entry["df"]

                    # need 'time' column here
                    if "time" not in df.columns:
                        continue

                    df_sorted = df.sort_values("time")
                    time_dt = pd.to_datetime(df_sorted["time"], unit="s")

                    fig.add_trace(
                        go.Scatter(
                            x=time_dt,
                            y=df_sorted[field_name],
                            mode="lines",
                            name=f"SN {glider_sn}",
                        )
                    )
                    any_trace = True

                if not any_trace:
                    plots.append(
                        dbc.Row(
                            dbc.Col(
                                html.Div(
                                    f"No data for {dv} with current IV/phase selection.",
                                    style={"color": "#666"},
                                ),
                                width=12,
                            ),
                            class_name="mb-3",
                        )
                    )
                else:
                    fig.update_layout(
                        xaxis_title="Time",
                        yaxis_title=field_name,
                        title=f"{inst_name.upper()} – {field_name} vs time",
                    )
                    plots.append(
                        dbc.Row(
                            dbc.Col(
                                dcc.Graph(figure=fig),
                                width=12,
                            ),
                            class_name="mb-3",
                        )
                    )

        # -----------------
        # IV = depth: plots side-by-side, tall & skinny, shared y range
        # -----------------
        elif iv == "depth":
            # First: compute global max depth across all DVs / gliders
            depth_max = None
            for dv in dv_values:
                inst_name, field_name, entries = dv_results.get(dv, (None, None, []))
                if not inst_name or not entries:
                    continue
                for entry in entries:
                    df = entry["df"]
                    depth_col = entry["depth_col"]
                    if not depth_col or depth_col not in df.columns:
                        continue
                    dmax = df[depth_col].max()
                    if depth_max is None or dmax > depth_max:
                        depth_max = dmax

            if depth_max is None:
                depth_max = 1.0

            # Second: build one fig per DV and lay them out horizontally
            row_children = []

            for dv in dv_values:
                inst_name, field_name, entries = dv_results.get(dv, (None, None, []))
                if not inst_name or not entries:
                    row_children.append(
                        dbc.Col(
                            html.Div(
                                f"No data for {dv} with current IV/phase selection.",
                                style={"color": "#666"},
                            ),
                            md=4,
                        )
                    )
                    continue

                fig = go.Figure()
                any_trace = False
                depth_col_used = None

                for entry in entries:
                    glider_sn = entry["glider_sn"]
                    df = entry["df"]
                    depth_col = entry["depth_col"]

                    if not depth_col or depth_col not in df.columns:
                        continue

                    if field_name not in df.columns:
                        continue

                    fig.add_trace(
                        go.Scatter(
                            x=df[field_name],
                            y=df[depth_col],
                            mode="markers",
                            name=f"SN {glider_sn}",
                        )
                    )
                    depth_col_used = depth_col
                    any_trace = True

                if not any_trace:
                    row_children.append(
                        dbc.Col(
                            html.Div(
                                f"No data for {dv} with current IV/phase selection.",
                                style={"color": "#666"},
                            ),
                            md=4,
                        )
                    )
                else:
                    fig.update_layout(
                        xaxis_title=field_name,
                        yaxis_title=depth_col_used or "depth",
                        title=f"{inst_name.upper()} – {field_name} vs {depth_col_used or 'depth'}",
                    )
                    # shared depth axis, depth increases downward
                    fig.update_yaxes(range=[depth_max, 0])

                    row_children.append(
                        dbc.Col(
                            dcc.Graph(figure=fig, style={"height": "800px"}),  # tall & skinny
                            md=2,  # tweak to control how many per row
                        )
                    )

            if not row_children:
                plots.append(
                    dbc.Row(
                        dbc.Col(
                            html.Div("No depth plots available.", style={"color": "#666"}),
                            width=12,
                        ),
                        class_name="mb-3",
                    )
                )
            else:
                plots.append(dbc.Row(row_children, class_name="mb-3"))

        if not plots:
            return html.Div("No plots to display with current settings.", style={"color": "#666"})

        return plots
