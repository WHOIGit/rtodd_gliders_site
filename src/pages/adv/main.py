import datetime as dt
from pathlib import Path

import dash
from dash import Input, Output, State, no_update
from dash.exceptions import PreventUpdate
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from data_loader import GliderDataLoader
from .layout import layout
from .names import AdvStoreIds, AdvControlIds, AdvGraphIds, AdvContainerIds

dash.register_page(
    __name__,
    path="/advanced",
    name="Advanced",
    title="GliderApp - Advanced",
)

app = dash.get_app()

# Module-level data loader — loads all active glider JSONs once
gdl = GliderDataLoader(data_dir=Path("./data"), auto_load=True)

# ArcGIS ocean basemap config (same as map page)
_map_tile_layer = dict(
    below="traces",
    sourcetype="raster",
    source=[
        "https://services.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}"
    ],
)


# ---------------------------------------------------------------------------
# Callback 1: Glider selection → populate stores and dropdowns
# ---------------------------------------------------------------------------
@app.callback(
    Output(AdvStoreIds.GLIDER_DATA_STORE, "data"),
    Output(AdvControlIds.SECTION_SELECT, "options"),
    Output(AdvControlIds.SECTION_SELECT, "value"),
    Output(AdvControlIds.INSTRUMENT_SELECT, "options"),
    Output(AdvControlIds.INSTRUMENT_SELECT, "value"),
    Output(AdvControlIds.DIVE_INPUT, "max"),
    Input(AdvControlIds.GLIDER_SELECT, "value"),
    prevent_initial_call=True,
)
def on_glider_select(glider_sn):
    if not glider_sn:
        raise PreventUpdate

    glider_sn = int(glider_sn)

    # Section options
    sections = gdl.sections_for_glider(glider_sn)
    section_opts = [{"label": s["label"], "value": s["id"]} for s in sections]
    section_default = sections[0]["id"] if sections else None

    # Instrument options
    all_instruments = gdl.instruments()
    inst_opts = [
        {"label": name, "value": name}
        for name in all_instruments
        if gdl.instrument_in_glider(name, glider_sn)
    ]
    inst_default = inst_opts[0]["value"] if inst_opts else None

    # Track records for mini-map
    track_df = gdl.build_glider_df(glider_sn)
    max_dive = int(track_df["ndive"].max()) if not track_df.empty else 1

    store_data = {
        "sn": glider_sn,
        "sections": sections,
        "max_dive": max_dive,
        "track_records": track_df.to_dict("records"),
    }

    return store_data, section_opts, section_default, inst_opts, inst_default, max_dive


# ---------------------------------------------------------------------------
# Callback 2: Range mode toggle
# ---------------------------------------------------------------------------
@app.callback(
    Output(AdvContainerIds.SECTION_CONTAINER, "style"),
    Output(AdvContainerIds.DIVE_CONTAINER, "style"),
    Output(AdvContainerIds.TIMESPAN_CONTAINER, "style"),
    Input(AdvControlIds.RANGE_MODE, "value"),
)
def toggle_range_mode(mode):
    show = {"display": "block"}
    hide = {"display": "none"}
    if mode == "section":
        return show, hide, hide
    elif mode == "dive":
        return hide, show, hide
    else:  # timespan
        return hide, hide, show


# ---------------------------------------------------------------------------
# Callback 3: Build selection store
# ---------------------------------------------------------------------------
@app.callback(
    Output(AdvStoreIds.SELECTION_STORE, "data"),
    Input(AdvControlIds.RANGE_MODE, "value"),
    Input(AdvControlIds.SECTION_SELECT, "value"),
    Input(AdvControlIds.DIVE_INPUT, "value"),
    Input(AdvControlIds.TIME_RANGE_PICKER, "start_date"),
    Input(AdvControlIds.TIME_RANGE_PICKER, "end_date"),
    Input(AdvControlIds.CAST_FILTER, "value"),
    State(AdvStoreIds.GLIDER_DATA_STORE, "data"),
    prevent_initial_call=True,
)
def build_selection(mode, section_id, dive_num, time_start, time_end, cast_filter, glider_store):
    if not glider_store:
        raise PreventUpdate

    selection = {
        "mode": mode,
        "section": section_id,
        "dive": dive_num,
        "time_start": None,
        "time_end": None,
        "cast": cast_filter or "all",
        "dive_range": None,
    }

    if mode == "section" and section_id is not None:
        sections = glider_store.get("sections", [])
        for s in sections:
            if s["id"] == section_id:
                end = s["end"]
                if np.isinf(end):
                    end = glider_store.get("max_dive", 99999)
                selection["dive_range"] = [s["start"], int(end)]
                break

    elif mode == "dive" and dive_num is not None:
        selection["dive_range"] = [int(dive_num), int(dive_num)]

    elif mode == "timespan":
        if time_start:
            ts = dt.datetime.strptime(time_start[:10], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
            selection["time_start"] = ts.timestamp()
        if time_end:
            te = dt.datetime.strptime(time_end[:10], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
            te = te + dt.timedelta(days=1) - dt.timedelta(seconds=1)
            selection["time_end"] = te.timestamp()

    return selection


# ---------------------------------------------------------------------------
# Callback 4: Build instrument DataFrame + axis defaults
# ---------------------------------------------------------------------------
@app.callback(
    Output(AdvStoreIds.INSTRUMENT_DF_STORE, "data"),
    Output(AdvControlIds.X_AXIS_SELECT, "options"),
    Output(AdvControlIds.X_AXIS_SELECT, "value"),
    Output(AdvControlIds.Y_AXIS_SELECT, "options"),
    Output(AdvControlIds.Y_AXIS_SELECT, "value"),
    Input(AdvControlIds.INSTRUMENT_SELECT, "value"),
    Input(AdvStoreIds.SELECTION_STORE, "data"),
    State(AdvControlIds.GLIDER_SELECT, "value"),
    prevent_initial_call=True,
)
def build_instrument_data(instrument_name, selection, glider_sn):
    if not instrument_name or not selection or not glider_sn:
        raise PreventUpdate

    glider_sn = int(glider_sn)
    mode = selection.get("mode", "section")
    cast = selection.get("cast", "all")
    phase_filter = None
    if cast == "downcast":
        phase_filter = "descent"
    elif cast == "upcast":
        phase_filter = "ascent"

    # Determine filters
    ndive_range = None
    time_range = None
    if mode in ("section", "dive") and selection.get("dive_range"):
        ndive_range = tuple(selection["dive_range"])
    elif mode == "timespan":
        t_start = selection.get("time_start")
        t_end = selection.get("time_end")
        if t_start and t_end:
            time_range = (t_start, t_end)

    try:
        df = gdl.build_instrument_df(
            glider_sn, instrument_name,
            ndive_range=ndive_range,
            time_range=time_range,
            phase=phase_filter,
        )
    except (KeyError, ValueError):
        raise PreventUpdate

    if df.empty:
        raise PreventUpdate

    # Build axis field options
    exclude_cols = {"ndive", "glider_sn", "instrument", "phase"}
    available = [c for c in df.columns if c not in exclude_cols]
    field_opts = [{"label": c, "value": c} for c in available]

    # Axis defaults
    if mode == "dive":
        y_default = "depth" if "depth" in available else "time"
        x_default = next(
            (f for f in available if f not in ("time", "depth", "p")),
            available[0],
        )
    else:
        x_default = "time" if "time" in available else available[0]
        y_default = "depth" if "depth" in available else (available[1] if len(available) > 1 else available[0])

    store = {
        "records": df.to_dict("records"),
        "columns": list(df.columns),
    }

    return store, field_opts, x_default, field_opts, y_default


# ---------------------------------------------------------------------------
# Callback 5: Update data plot
# ---------------------------------------------------------------------------
@app.callback(
    Output(AdvGraphIds.DATA_PLOT, "figure"),
    Input(AdvStoreIds.INSTRUMENT_DF_STORE, "data"),
    Input(AdvControlIds.X_AXIS_SELECT, "value"),
    Input(AdvControlIds.Y_AXIS_SELECT, "value"),
    State(AdvStoreIds.SELECTION_STORE, "data"),
    prevent_initial_call=True,
)
def update_data_plot(inst_store, x_col, y_col, selection):
    if not inst_store or not x_col or not y_col:
        raise PreventUpdate

    df = pd.DataFrame(inst_store["records"])
    if df.empty:
        raise PreventUpdate

    mode = selection.get("mode", "section") if selection else "section"

    # Convert time columns to datetime for display
    for col in (x_col, y_col):
        if col == "time":
            df["time_dt"] = pd.to_datetime(df["time"], unit="s", utc=True)

    x_data = df["time_dt"] if x_col == "time" and "time_dt" in df.columns else df[x_col]
    y_data = df["time_dt"] if y_col == "time" and "time_dt" in df.columns else df[y_col]

    # Color by ndive for multi-dive, phase for single dive
    if mode == "dive" and "phase" in df.columns:
        color_col = df["phase"].astype(str)
        color_label = "phase"
    else:
        color_col = df["ndive"]
        color_label = "ndive"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x_data,
        y=y_data,
        mode="markers",
        marker=dict(
            size=4,
            color=color_col,
            colorscale="Viridis",
            colorbar=dict(title=color_label),
            showscale=True,
        ),
        hovertemplate=(
            f"<b>{x_col}</b>: %{{x}}<br>"
            f"<b>{y_col}</b>: %{{y}}<br>"
            "<extra></extra>"
        ),
    ))

    fig.update_layout(
        xaxis_title=x_col,
        yaxis_title=y_col,
        margin=dict(l=60, r=20, t=30, b=50),
    )

    # Reverse Y axis for depth (depth increases downward)
    if y_col == "depth":
        fig.update_yaxes(autorange="reversed")

    return fig


# ---------------------------------------------------------------------------
# Callback 6: Update mini-map
# ---------------------------------------------------------------------------
@app.callback(
    Output(AdvGraphIds.MINI_MAP, "figure"),
    Input(AdvStoreIds.GLIDER_DATA_STORE, "data"),
    Input(AdvStoreIds.SELECTION_STORE, "data"),
    prevent_initial_call=True,
)
def update_minimap(glider_store, selection):
    if not glider_store or not glider_store.get("track_records"):
        raise PreventUpdate

    track = pd.DataFrame(glider_store["track_records"])
    fig = go.Figure()

    # Full track in grey
    fig.add_trace(go.Scattermap(
        lat=track["lat"],
        lon=track["lon"],
        mode="lines",
        line=dict(width=2, color="lightgrey"),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Highlight selected range
    if selection and selection.get("dive_range"):
        start, end = selection["dive_range"]
        highlight = track[track["ndive"].between(start, end)]
        if not highlight.empty:
            fig.add_trace(go.Scattermap(
                lat=highlight["lat"],
                lon=highlight["lon"],
                mode="lines+markers",
                line=dict(width=3, color="royalblue"),
                marker=dict(size=4, color="royalblue"),
                showlegend=False,
                hovertemplate=(
                    "Lat: %{lat:.4f}<br>"
                    "Lon: %{lon:.4f}<br>"
                    "<extra></extra>"
                ),
            ))

            # Center on highlighted segment
            center_lat = (highlight["lat"].min() + highlight["lat"].max()) / 2
            center_lon = (highlight["lon"].min() + highlight["lon"].max()) / 2
            max_bound = max(
                abs(highlight["lat"].max() - highlight["lat"].min()),
                abs(highlight["lon"].max() - highlight["lon"].min()),
            ) * 111
            zoom = max(1, 12 - np.log(max(max_bound, 0.1)))
        else:
            center_lat = track["lat"].mean()
            center_lon = track["lon"].mean()
            zoom = 4
    elif selection and selection.get("mode") == "timespan" and selection.get("time_start"):
        # For timespan mode, highlight by time if no dive_range
        center_lat = track["lat"].mean()
        center_lon = track["lon"].mean()
        zoom = 4
    else:
        center_lat = track["lat"].dropna().mean() if not track["lat"].dropna().empty else 0
        center_lon = track["lon"].dropna().mean() if not track["lon"].dropna().empty else 0
        zoom = 4

    fig.update_layout(
        map=dict(
            center=dict(lat=center_lat, lon=center_lon),
            zoom=zoom,
            layers=[_map_tile_layer],
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )

    return fig


# ---------------------------------------------------------------------------
# Callback 7: Mini-map toggle
# ---------------------------------------------------------------------------
@app.callback(
    Output(AdvContainerIds.MINIMAP_CARD, "is_open"),
    Input(AdvControlIds.MINIMAP_TOGGLE, "value"),
)
def toggle_minimap(value):
    return "show" in (value or [])


# ---------------------------------------------------------------------------
# Populate glider dropdown options on page load
# ---------------------------------------------------------------------------
@app.callback(
    Output(AdvControlIds.GLIDER_SELECT, "options"),
    Input(AdvControlIds.GLIDER_SELECT, "id"),  # fires once on page load
)
def populate_glider_options(_):
    sns = sorted(gdl.glider_sns())
    return [{"label": f"SG{sn:03d}", "value": sn} for sn in sns]
