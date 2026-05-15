from pathlib import Path

import dash
from dash import Input, Output, State, no_update, html
from dash.exceptions import PreventUpdate
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from data_loader import GliderDataLoader, parse_mission_yyyymmm, get_gdl as _get_gdl
from utils import time_ticks, load_region_labels
from .layout import layout
from .names import AdvStoreIds, AdvControlIds, AdvGraphIds, AdvContainerIds

_REGION_LABELS = load_region_labels(Path("config/map_config.yml").resolve())


def _region_display(key: str) -> str:
    return _REGION_LABELS.get(key, key)


def _make_search_text(*parts: str) -> str:
    """Build the lowercased search-source for a dropdown option.

    For each part, include both the lowercased text and a no-space variant so
    queries like 'gulf' match 'gulfstream' and 'Gulf Stream' alike.
    """
    pieces = []
    for p in parts:
        if not p:
            continue
        s = str(p).lower()
        pieces.append(s)
        if " " in s:
            pieces.append(s.replace(" ", ""))
    return " ".join(pieces)


def _matches_query(search_text: str, query: str | None) -> bool:
    """Token-AND match: every whitespace-separated token in query must appear."""
    if not query:
        return True
    q = query.lower()
    # Allow queries with embedded spaces by splitting; each token is substring.
    return all(tok in search_text for tok in q.split())

dash.register_page(
    __name__,
    path="/plotting/profiles",
    name="Profiles",
    title="Gliders - Profiles",
)

app = dash.get_app()

MAX_PROFILE_POINTS = 200_000

# ArcGIS ocean basemap config (same as map page)
_map_tile_layer = dict(
    below="traces",
    sourcetype="raster",
    source=[
        "https://services.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}"
    ],
)


def _fmt_hover(series: pd.Series, col: str) -> pd.Series:
    """Format a raw data series for hover display based on column type."""
    if col == "divetime":
        def fmt(v):
            if pd.isna(v):
                return ""
            s = int(round(v))
            if s < 60:
                return f"{s}s"
            elif s < 3600:
                m, rem = divmod(s, 60)
                return f"{m}m {rem:02d}s"
            elif s < 86400:
                h, rem = divmod(s, 3600)
                return f"{h}h {rem // 60:02d}m {rem % 60:02d}s"
            else:
                d, rem = divmod(s, 86400)
                return f"{d}d {rem // 3600:02d}h"
        return series.apply(fmt)
    elif col == "datetime":
        def fmt(v):
            if pd.isna(v):
                return ""
            return pd.Timestamp(v, unit="s", tz="UTC").strftime("%Y-%m-%d %H:%M:%S UTC")
        return series.apply(fmt)
    return series


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

    glider_sn = str(glider_sn)
    gdl = _get_gdl()
    # Archived mission ids are longer than 4 chars; lazy-load if needed.
    if len(glider_sn) > 4 or glider_sn in gdl.archive_missions:
        gdl.load_archived(glider_sn)

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
    inst_default = "CTD" if any(o["value"] == "CTD" for o in inst_opts) else (inst_opts[0]["value"] if inst_opts else None)

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
    Input(AdvControlIds.RANGE_TOGGLE, "value"),
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
        n = n1 if n1 is not None else max_dive
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
    glider_sn = str(glider_sn)
    gdl = _get_gdl()
    if len(glider_sn) > 4 or glider_sn in gdl.archive_missions:
        gdl.load_archived(glider_sn)
    try:
        has_down, has_up = gdl.instrument_phase_presence(
            glider_sn,
            instrument_name,
            ndive_range=ndive_range,
        )
    except (KeyError, ValueError):
        return _all_opts

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
    Output(AdvControlIds.COLOR_SELECT, "options"),
    Output(AdvControlIds.COLOR_SELECT, "value"),
    Output(AdvContainerIds.DECIMATION_ALERT, "children"),
    Output(AdvContainerIds.DECIMATION_ALERT, "is_open"),
    Input(AdvControlIds.INSTRUMENT_SELECT, "value"),
    Input(AdvStoreIds.SELECTION_STORE, "data"),
    State(AdvControlIds.GLIDER_SELECT, "value"),
    State(AdvControlIds.X_AXIS_SELECT, "value"),
    State(AdvControlIds.Y_AXIS_SELECT, "value"),
    State(AdvControlIds.COLOR_SELECT, "value"),
    prevent_initial_call=True,
)
def build_instrument_data(instrument_name, selection, glider_sn, current_x, current_y, current_color):
    if not instrument_name or not selection or not glider_sn:
        raise PreventUpdate

    glider_sn = str(glider_sn)
    cast = selection.get("cast", "all")
    phase_filter = None
    if cast == "downcast":
        phase_filter = "descent"
    elif cast == "upcast":
        phase_filter = "ascent"

    ndive_range = tuple(selection["dive_range"]) if selection.get("dive_range") else None

    gdl = _get_gdl()
    if len(glider_sn) > 4 or glider_sn in gdl.archive_missions:
        gdl.load_archived(glider_sn)

    try:
        df = gdl.build_instrument_df(
            glider_sn, instrument_name,
            ndive_range=ndive_range,
            phase=phase_filter,
            max_points=MAX_PROFILE_POINTS,
        )
    except (KeyError, ValueError):
        raise PreventUpdate

    if df.empty:
        return {
            "records": [],
            "columns": [],
        }, no_update, no_update, no_update, no_update, no_update, no_update, "", False

    # Build axis field options with short_name labels
    exclude_cols = {"ndive", "glider_sn", "instrument", "phase"}
    non_physical = {"divetime", "datetime", "depth", "p"}
    available = [c for c in df.columns if c not in exclude_cols]

    inst_key = gdl.instruments()[instrument_name]['key']
    info = gdl.glider_jsons[gdl.sn_to_filename(glider_sn)][inst_key]['info']
    field_meta = {}
    for c in available:
        meta = dict(info.get(c, {}))
        if "unit" in meta and "units" not in meta:
            meta["units"] = meta["unit"]
        if "name" in meta and "short_name" not in meta:
            meta["short_name"] = meta["name"]
        field_meta[c] = meta

    def field_label(col):
        meta = field_meta[col]
        name = meta.get('name') or meta.get('unit') or ''
        return f"[{col}] {name}" if name else col

    field_opts = [{"label": field_label(c), "value": c} for c in available]

    # Preserve current axis selections if still valid on range change, else use defaults
    is_single_dive = ndive_range and ndive_range[0] == ndive_range[1]
    range_changed = dash.ctx.triggered_id == AdvStoreIds.SELECTION_STORE

    if range_changed and current_x in available:
        x_default = current_x
    else:
        x_default = (
            next((f for f in ("temp",) if f in available), None)
            or next((f for f in available if f not in non_physical), available[0])
        )

    if range_changed and current_y in available:
        y_default = current_y
    else:
        y_default = "depth" if "depth" in available else (available[1] if len(available) > 1 else available[0])

    store = {
        "records": df.to_dict("records"),
        "columns": list(df.columns),
        "field_meta": field_meta,
    }

    color_opts = [{"label": "ndive", "value": "ndive"}] + field_opts
    color_values = {"ndive"} | {c["value"] for c in field_opts}
    color_default = current_color if (range_changed and current_color in color_values) else "ndive"

    raw_points = int(df.attrs.get("raw_points", len(df)))
    shown_points = int(df.attrs.get("shown_points", len(df)))
    if shown_points < raw_points:
        reduction = 100 * (1 - shown_points / raw_points)
        warning = (
            f"Showing {shown_points:,} of {raw_points:,} available data points "
            f"({reduction:.1f}% reduction). To show all datapoints, request a smaller range."
        )
        warning_open = True
    else:
        warning = ""
        warning_open = False

    return store, field_opts, x_default, field_opts, y_default, color_opts, color_default, warning, warning_open


# ---------------------------------------------------------------------------
# Callback 5: Update data plot
# ---------------------------------------------------------------------------
@app.callback(
    Output(AdvGraphIds.DATA_PLOT, "figure"),
    Input(AdvStoreIds.INSTRUMENT_DF_STORE, "data"),
    Input(AdvControlIds.X_AXIS_SELECT, "value"),
    Input(AdvControlIds.Y_AXIS_SELECT, "value"),
    Input(AdvControlIds.COLOR_SELECT, "value"),
    Input(AdvStoreIds.MINIMAP_CLICK_STORE, "data"),
    State(AdvStoreIds.SELECTION_STORE, "data"),
    prevent_initial_call=True,
)
def update_data_plot(inst_store, x_col, y_col, color_col, click_store, selection):
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

    # Convert datetime column to pandas Timestamp for display on axes
    for col in (x_col, y_col):
        if col == "datetime":
            df["datetime_dt"] = pd.to_datetime(df["datetime"], unit="s", utc=True)

    # Insert NaN separator rows between dives so plotly doesn't connect them
    if "ndive" in df.columns and df["ndive"].nunique() > 1:
        sep = pd.DataFrame({
            col: pd.Series([np.nan], dtype=float if pd.api.types.is_integer_dtype(df[col]) else df[col].dtype)
            for col in df.columns
        })
        parts = []
        for i, (_, grp) in enumerate(df.groupby("ndive", sort=False)):
            if i > 0:
                parts.append(sep)
            parts.append(grp)
        df = pd.concat(parts, ignore_index=True)
    x_data = df["datetime_dt"] if x_col == "datetime" and "datetime_dt" in df.columns else df[x_col]
    y_data = df["datetime_dt"] if y_col == "datetime" and "datetime_dt" in df.columns else df[y_col]

    color_field = color_col if (color_col and color_col in df.columns) else "ndive"
    color_data = df[color_field]
    color_label = color_field

    # Build colorbar options with special formatting for ndive, divetime, and datetime.
    # For datetime, convert to milliseconds so plotly uses its native date tick formatting.
    colorbar_opts = dict(title=color_label, thickness=14)
    marker_color_data = pd.to_numeric(color_data, errors="coerce")
    if color_field == "ndive":
        colorbar_opts["tickformat"] = ".0f"
    elif color_field in ("divetime", "datetime"):
        vals = marker_color_data.dropna()
        if not vals.empty:
            tv, tt = time_ticks(vals.min(), vals.max(), fmt=color_field, n_min=3, n_max=6)
            colorbar_opts.update(tickvals=tv, ticktext=tt)

    # Marker symbol: triangle-down for descent (phase==1), triangle-up for ascent
    if "phase" in df.columns:
        symbols = df["phase"].map(lambda p: "triangle-down" if p == 1 else "triangle-up").tolist()
    else:
        symbols = "circle"

    # Build customdata: ndive, formatted x, formatted y, formatted color
    x_hover = _fmt_hover(df[x_col] if x_col in df.columns else pd.to_numeric(x_data, errors="coerce"), x_col)
    y_hover = _fmt_hover(df[y_col] if y_col in df.columns else pd.to_numeric(y_data, errors="coerce"), y_col)
    color_hover = _fmt_hover(color_data, color_field)
    cdata = np.column_stack([df["ndive"].values, x_hover.values, y_hover.values, color_hover.values])

    # Compute selectedpoints if a dive was clicked on the minimap
    sel_points = None
    #print(f"[DEBUG] triggered_id={dash.ctx.triggered_id!r}, expected={AdvStoreIds.MINIMAP_CLICK_STORE!r}, click_store={click_store}")
    if click_store and dash.ctx.triggered_id == AdvStoreIds.MINIMAP_CLICK_STORE:
        clicked_ndive = click_store.get("ndive")
        if clicked_ndive is not None:
            matches = df.index[df["ndive"] == clicked_ndive].tolist()
            #print(f"[DEBUG] clicked_ndive={clicked_ndive!r}, type={type(clicked_ndive)}, ndive_dtype={df['ndive'].dtype}, matches={len(matches)}")
            if matches:
                sel_points = matches

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x_data,
        y=y_data,
        mode="lines+markers",
        line=dict(width=0.5, color="rgba(100,100,100,0.3)"),
        marker=dict(
            size=5,
            symbol=symbols,
            color=marker_color_data,
            colorscale="Viridis",
            colorbar=colorbar_opts,
            showscale=True,
        ),
        selected=dict(marker=dict(opacity=1)),
        unselected=dict(marker=dict(opacity=0.15, size=3)),
        selectedpoints=sel_points,
        customdata=cdata,
        hovertemplate=(
            f"<b>{x_col}</b>: %{{customdata[1]}}<br>"
            f"<b>{y_col}</b>: %{{customdata[2]}}<br>"
            + ("" if "ndive" in (x_col, y_col) else "<b>ndive</b>: %{customdata[0]}<br>")
            + ("" if color_label in (x_col, y_col, "ndive") else f"<b>{color_label}</b>: %{{customdata[3]}}<br>")
            + "<extra></extra>"
        ),
    ))

    def axis_title(col):
        if col == "divetime":
            return "divetime (s)"
        if col == "datetime":
            return "datetime (UTC)"
        meta = inst_store.get("field_meta", {}).get(col, {})
        short = meta.get('short_name', '')
        units = meta.get('units', '')
        name = short or units
        if name and units and short:
            return f"[{col}] {name} ({units})"
        elif name:
            return f"[{col}] {name}"
        return col

    fig.update_layout(
        xaxis_title=axis_title(x_col),
        yaxis_title=axis_title(y_col),
        margin=dict(l=60, r=20, t=30, b=50),
    )

    if x_col == "divetime":
        x_vals = pd.to_numeric(df[x_col], errors="coerce").dropna()
        if not x_vals.empty:
            tv, tt = time_ticks(x_vals.min(), x_vals.max(), fmt="s", n_min=4, n_max=8)
            fig.update_xaxes(tickvals=tv, ticktext=tt)

    if y_col == "divetime":
        y_vals = pd.to_numeric(df[y_col], errors="coerce").dropna()
        if not y_vals.empty:
            tv, tt = time_ticks(y_vals.min(), y_vals.max(), fmt="s", n_min=4, n_max=8)
            fig.update_yaxes(tickvals=tv, ticktext=tt)

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
            # Line trace for the highlighted track
            fig.add_trace(go.Scattermap(
                lat=highlight["lat"],
                lon=highlight["lon"],
                mode="lines",
                line=dict(width=3, color="royalblue"),
                showlegend=False,
                hoverinfo="skip",
            ))
            # Markers-only trace: one point per dive (mean of start/end)
            per_dive = highlight.groupby("ndive", sort=False).agg(
                lat=("lat", "mean"), lon=("lon", "mean"),
            ).reset_index()
            fig.add_trace(go.Scattermap(
                lat=per_dive["lat"],
                lon=per_dive["lon"],
                mode="markers",
                marker=dict(size=8, color="royalblue"),
                showlegend=False,
                customdata=per_dive["ndive"].values,
                hovertemplate=(
                    "Dive: %{customdata}<br>"
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
# Callback 6a: Mini-map click → store clicked ndive
# ---------------------------------------------------------------------------
@app.callback(
    Output(AdvStoreIds.MINIMAP_CLICK_STORE, "data"),
    Input(AdvGraphIds.MINI_MAP, "clickData"),
    State(AdvStoreIds.GLIDER_DATA_STORE, "data"),
    State(AdvStoreIds.SELECTION_STORE, "data"),
    prevent_initial_call=True,
)
def minimap_click(click_data, glider_store, selection):
    if not click_data or not glider_store or not selection:
        raise PreventUpdate

    point = click_data["points"][0]
    # Only handle clicks on the per-dive markers trace (curveNumber 2)
    if point.get("curveNumber") != 2:
        raise PreventUpdate

    point_index = point.get("pointIndex")
    if point_index is None:
        raise PreventUpdate

    # Reconstruct per-dive ndive list (same groupby as callback 6)
    track = pd.DataFrame(glider_store["track_records"])
    start, end = selection["dive_range"]
    highlight = track[track["ndive"].between(start, end)]
    per_dive_ndives = highlight.groupby("ndive", sort=False).first().reset_index()["ndive"]

    if point_index >= len(per_dive_ndives):
        raise PreventUpdate

    clicked_ndive = int(per_dive_ndives.iloc[point_index])
    #print(f"[DEBUG 6a] clicked ndive={clicked_ndive}")
    return {"ndive": clicked_ndive}



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
# Populate glider/mission dropdown based on Archived toggle
# ---------------------------------------------------------------------------
_GRAY = {"color": "#999", "marginLeft": "0.5em"}
_DISABLED_PRIMARY = {"color": "#aaa"}


def _option_label(primary: str, suffix: str, disabled: bool = False):
    primary_node = html.Span(primary, style=_DISABLED_PRIMARY) if disabled else primary
    if not suffix:
        return html.Span([primary_node]) if disabled else primary
    return html.Span([primary_node, html.Span(suffix, style=_GRAY)])


@app.callback(
    Output(AdvControlIds.GLIDER_SELECT, "options"),
    Output(AdvControlIds.GLIDER_SELECT, "value"),
    Output(AdvControlIds.GLIDER_SELECT, "placeholder"),
    Output(AdvControlIds.GLIDER_LABEL, "children"),
    Input(AdvControlIds.ARCHIVED_TOGGLE, "value"),
    Input(AdvControlIds.GLIDER_SELECT, "search_value"),
    State(AdvControlIds.GLIDER_SELECT, "value"),
)
def populate_glider_options(archived_value, search_value, current_value):
    gdl = _get_gdl()
    archived = "on" in (archived_value or [])
    is_search = dash.ctx.triggered_id == AdvControlIds.GLIDER_SELECT

    if archived:
        ids = gdl.archive_mission_ids()
        rows = []
        for mid in ids:
            meta = gdl.archive_missions.get(mid, {})
            region_key = meta.get("region", "")
            region_lbl = _region_display(region_key)
            yymm = parse_mission_yyyymmm(mid)  # e.g. "2025 Dec"
            year = yymm.split(" ")[0] if yymm and yymm != "?" else ""
            month = yymm.split(" ")[1] if yymm and " " in yymm else ""
            suffix = f" {region_lbl} - {yymm}" if region_lbl else f" {yymm}"
            disabled = not gdl.has_json(mid)
            search_text = _make_search_text(mid, region_key, region_lbl, year, month)
            if not _matches_query(search_text, search_value):
                continue
            rows.append((disabled, mid, suffix, search_text))
        rows.sort(key=lambda r: r[1])
        sv = search_value or ""
        opts = [{
            "label": _option_label(mid, suffix, disabled=disabled),
            "value": mid,
            "disabled": disabled,
            "search": f"{search_text} {sv}",
        } for disabled, mid, suffix, search_text in rows]
        new_value = no_update if is_search else None
        return opts, new_value, "Select mission...", "Mission"

    sns = gdl.all_active_sns()
    rows = []
    for sn in sns:
        region_key = gdl.active_meta.get(sn, {}).get("region", "")
        region_lbl = _region_display(region_key)
        suffix = f" {region_lbl}" if region_lbl else ""
        disabled = not gdl.has_json(sn)
        search_text = _make_search_text(sn, f"spray {sn}", region_key, region_lbl)
        if not _matches_query(search_text, search_value):
            continue
        rows.append((disabled, sn, suffix, search_text))
    rows.sort(key=lambda r: r[1])
    sv = search_value or ""
    opts = [{
        "label": _option_label(f"Spray {sn}", suffix, disabled=disabled),
        "value": sn,
        "disabled": disabled,
        "search": f"{search_text} {sv}",
    } for disabled, sn, suffix, search_text in rows]
    if is_search:
        new_value = no_update
    else:
        loaded = [sn for sn in sns if gdl.has_json(sn)]
        mtimes = {sn: t for sn, t in gdl.sn_mtimes().items() if sn in loaded}
        new_value = max(mtimes, key=mtimes.get) if mtimes else (loaded[0] if loaded else None)
    return opts, new_value, "Select glider...", "Glider"
