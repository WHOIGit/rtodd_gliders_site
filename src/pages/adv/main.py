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
    Output(AdvControlIds.DIVE_INPUT, "value"),
    Output(AdvControlIds.DIVE_INPUT, "placeholder"),
    Output(AdvControlIds.DIVE_INPUT2, "max"),
    Output(AdvControlIds.DIVE_INPUT2, "value"),
    Output(AdvControlIds.DIVE_INPUT2, "placeholder"),
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

    # JSON can't represent float('inf') — replace inf ends with max_dive before storing
    sections_serializable = [
        {**s, "end": max_dive if isinstance(s["end"], float) and np.isinf(s["end"]) else s["end"]}
        for s in sections
    ]

    store_data = {
        "sn": glider_sn,
        "sections": sections_serializable,
        "max_dive": max_dive,
        "track_records": track_df.to_dict("records"),
    }

    return (
        store_data,
        section_opts, None,
        inst_opts, inst_default,
        max_dive, max_dive, str(max_dive),
        max_dive, None, str(max_dive),
    )


# ---------------------------------------------------------------------------
# Callback 2: Range toggle → show/hide second dive input
# ---------------------------------------------------------------------------
@app.callback(
    Output(AdvContainerIds.DIVE_INPUT2_CONTAINER, "is_open"),
    Input(AdvControlIds.RANGE_TOGGLE, "value"),
)
def toggle_range(value):
    return "range" in (value or [])


# ---------------------------------------------------------------------------
# Callback 2a: Dive prev/next buttons (input 1 and input 2)
# ---------------------------------------------------------------------------
@app.callback(
    Output(AdvControlIds.DIVE_INPUT, "value", allow_duplicate=True),
    Input(AdvControlIds.DIVE_PREV, "n_clicks"),
    Input(AdvControlIds.DIVE_NEXT, "n_clicks"),
    State(AdvControlIds.DIVE_INPUT, "value"),
    State(AdvStoreIds.GLIDER_DATA_STORE, "data"),
    prevent_initial_call=True,
)
def step_dive1(n_prev, n_next, current, glider_store):
    if not glider_store:
        raise PreventUpdate
    max_dive = glider_store.get("max_dive", 1)
    current = current if current is not None else max_dive
    delta = -1 if dash.ctx.triggered_id == AdvControlIds.DIVE_PREV else 1
    return max(1, min(max_dive, int(current) + delta))


@app.callback(
    Output(AdvControlIds.DIVE_INPUT2, "value", allow_duplicate=True),
    Input(AdvControlIds.DIVE_PREV2, "n_clicks"),
    Input(AdvControlIds.DIVE_NEXT2, "n_clicks"),
    State(AdvControlIds.DIVE_INPUT2, "value"),
    State(AdvStoreIds.GLIDER_DATA_STORE, "data"),
    prevent_initial_call=True,
)
def step_dive2(n_prev, n_next, current, glider_store):
    if not glider_store:
        raise PreventUpdate
    max_dive = glider_store.get("max_dive", 1)
    current = current if current is not None else max_dive
    delta = -1 if dash.ctx.triggered_id == AdvControlIds.DIVE_PREV2 else 1
    return max(1, min(max_dive, int(current) + delta))


# ---------------------------------------------------------------------------
# Callback 2b: Section select → set dive input values + activate range mode
# ---------------------------------------------------------------------------
@app.callback(
    Output(AdvControlIds.DIVE_INPUT, "value", allow_duplicate=True),
    Output(AdvControlIds.DIVE_INPUT2, "value", allow_duplicate=True),
    Output(AdvControlIds.RANGE_TOGGLE, "value"),
    Input(AdvControlIds.SECTION_SELECT, "value"),
    State(AdvStoreIds.GLIDER_DATA_STORE, "data"),
    prevent_initial_call=True,
)
def apply_section(section_id, glider_store):
    if not section_id or not glider_store:
        raise PreventUpdate
    sections = glider_store.get("sections", [])
    for s in sections:
        if s["id"] == section_id:
            start = int(s["start"])
            end = s["end"]
            if end is None or (isinstance(end, float) and np.isinf(end)):
                end = glider_store.get("max_dive", 99999)
            return start, int(end), ["range"]
    raise PreventUpdate


# ---------------------------------------------------------------------------
# Callback 3: Build selection store
# ---------------------------------------------------------------------------
@app.callback(
    Output(AdvStoreIds.SELECTION_STORE, "data"),
    Input(AdvControlIds.DIVE_INPUT, "value"),
    Input(AdvControlIds.DIVE_INPUT2, "value"),
    Input(AdvControlIds.CAST_FILTER, "value"),
    State(AdvControlIds.RANGE_TOGGLE, "value"),
    State(AdvStoreIds.GLIDER_DATA_STORE, "data"),
    prevent_initial_call=True,
)
def build_selection(dive1, dive2, cast_filter, range_toggle, glider_store):
    if not glider_store:
        raise PreventUpdate

    max_dive = glider_store.get("max_dive", 1)
    n1 = int(dive1) if dive1 is not None else None
    n2 = int(dive2) if dive2 is not None else None

    if "range" in (range_toggle or []) and n1 is not None and n2 is not None:
        dive_range = [min(n1, n2), max(n1, n2)]
    else:
        n = n1 if n1 is not None else (n2 if n2 is not None else max_dive)
        dive_range = [n, n]

    return {
        "dive_range": dive_range,
        "cast": cast_filter or "all",
    }


# ---------------------------------------------------------------------------
# Callback 3a: Update cast filter options based on available phases
# ---------------------------------------------------------------------------
@app.callback(
    Output(AdvControlIds.CAST_FILTER, "options"),
    Input(AdvControlIds.INSTRUMENT_SELECT, "value"),
    Input(AdvStoreIds.SELECTION_STORE, "data"),
    State(AdvControlIds.GLIDER_SELECT, "value"),
    prevent_initial_call=True,
)
def update_cast_options(instrument_name, selection, glider_sn):
    _all_opts = [
        {"label": "All", "value": "all"},
        {"label": "Downcast", "value": "downcast"},
        {"label": "Upcast", "value": "upcast"},
    ]
    if not instrument_name or not glider_sn or not selection:
        return _all_opts

    ndive_range = tuple(selection["dive_range"]) if selection.get("dive_range") else None
    try:
        df = gdl.build_instrument_df(int(glider_sn), instrument_name, ndive_range=ndive_range)
    except (KeyError, ValueError):
        return _all_opts

    if df.empty or "phase" not in df.columns:
        return _all_opts

    has_down = (df["phase"] == 1).any()
    has_up = (df["phase"] != 1).any()
    return [
        {"label": "All", "value": "all"},
        {"label": "Downcast", "value": "downcast", "disabled": not has_down},
        {"label": "Upcast", "value": "upcast", "disabled": not has_up},
    ]


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
    State(AdvControlIds.X_AXIS_SELECT, "value"),
    State(AdvControlIds.Y_AXIS_SELECT, "value"),
    prevent_initial_call=True,
)
def build_instrument_data(instrument_name, selection, glider_sn, current_x, current_y):
    if not instrument_name or not selection or not glider_sn:
        raise PreventUpdate

    glider_sn = int(glider_sn)
    cast = selection.get("cast", "all")
    phase_filter = None
    if cast == "downcast":
        phase_filter = "descent"
    elif cast == "upcast":
        phase_filter = "ascent"

    ndive_range = tuple(selection["dive_range"]) if selection.get("dive_range") else None

    try:
        df = gdl.build_instrument_df(
            glider_sn, instrument_name,
            ndive_range=ndive_range,
            phase=phase_filter,
        )
    except (KeyError, ValueError):
        raise PreventUpdate

    if df.empty:
        return {"records": [], "columns": []}, no_update, no_update, no_update, no_update

    # Build axis field options
    exclude_cols = {"ndive", "glider_sn", "instrument", "phase"}
    available = [c for c in df.columns if c not in exclude_cols]
    field_opts = [{"label": c, "value": c} for c in available]

    # Preserve current axis selections if still valid on range change, else use defaults
    is_single_dive = ndive_range and ndive_range[0] == ndive_range[1]
    range_changed = dash.ctx.triggered_id == AdvStoreIds.SELECTION_STORE

    if range_changed and current_x in available:
        x_default = current_x
    elif is_single_dive:
        x_default = next((f for f in available if f not in ("time", "depth", "p")), available[0])
    else:
        x_default = "time" if "time" in available else available[0]

    if range_changed and current_y in available:
        y_default = current_y
    elif is_single_dive:
        y_default = "depth" if "depth" in available else "time"
    else:
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
        fig = go.Figure()
        fig.add_annotation(
            text="No Data",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=24, color="grey"),
        )
        fig.update_layout(
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            margin=dict(l=60, r=20, t=30, b=50),
        )
        return fig

    # Convert time columns to datetime for display
    for col in (x_col, y_col):
        if col == "time":
            df["time_dt"] = pd.to_datetime(df["time"], unit="s", utc=True)

    x_data = df["time_dt"] if x_col == "time" and "time_dt" in df.columns else df[x_col]
    y_data = df["time_dt"] if y_col == "time" and "time_dt" in df.columns else df[y_col]

    # Single-dive: color by phase; multi-dive: color by ndive
    dive_range = selection.get("dive_range") if selection else None
    is_single = dive_range and dive_range[0] == dive_range[1]

    if is_single and "phase" in df.columns:
        color_col = df["phase"]
        color_label = "phase"
    else:
        color_col = df["ndive"]
        color_label = "ndive"

    # Marker symbol: triangle-down for descent (phase==1), triangle-up for ascent
    if "phase" in df.columns:
        symbols = df["phase"].map(lambda p: "triangle-down" if p == 1 else "triangle-up").tolist()
    else:
        symbols = "circle"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x_data,
        y=y_data,
        mode="lines+markers",
        line=dict(width=0.5, color="rgba(100,100,100,0.3)"),
        marker=dict(
            size=5,
            symbol=symbols,
            color=color_col.astype(int),
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

    fig.add_trace(go.Scattermap(
        lat=track["lat"],
        lon=track["lon"],
        mode="lines",
        line=dict(width=2, color="lightgrey"),
        showlegend=False,
        hoverinfo="skip",
    ))

    center_lat = track["lat"].dropna().mean() if not track["lat"].dropna().empty else 0
    center_lon = track["lon"].dropna().mean() if not track["lon"].dropna().empty else 0
    zoom = 4

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
            center_lat = (highlight["lat"].min() + highlight["lat"].max()) / 2
            center_lon = (highlight["lon"].min() + highlight["lon"].max()) / 2
            max_bound = max(
                abs(highlight["lat"].max() - highlight["lat"].min()),
                abs(highlight["lon"].max() - highlight["lon"].min()),
            ) * 111
            zoom = max(1, 12 - np.log(max(max_bound, 0.1)))

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
    Output(AdvControlIds.GLIDER_SELECT, "value"),
    Input(AdvControlIds.GLIDER_SELECT, "id"),  # fires once on page load
)
def populate_glider_options(_):
    sns = sorted(gdl.glider_sns())
    opts = [{"label": f"Spray2 {sn:03d}", "value": sn} for sn in sns]
    mtimes = gdl.sn_mtimes()
    most_recent = max(mtimes, key=mtimes.get) if mtimes else (sns[0] if sns else None)
    return opts, most_recent
