from pathlib import Path

import pandas as pd

import dash
from dash import Input, Output, State, no_update
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data_loader import GliderDataLoader
from utils import time_ticks
from .layout import layout
from .names import EngStoreIds, EngControlIds, EngGraphIds

dash.register_page(
    __name__,
    path="/plotting/engineering",
    name="Engineering",
    title="Gliders - Engineering",
)

#   ┌──────────────────┬──────────────────────────────────────────────────────────┐
#   │     Subplot      │                        Data path                         │
#   ├──────────────────┼──────────────────────────────────────────────────────────┤
#   │ Surface Pressure │ d['eng']['psurf'][i]                                     │
#   ├──────────────────┼──────────────────────────────────────────────────────────┤
#   │ Min Pressure     │ derived: min(d['eng']['p'][i])                           │
#   ├──────────────────┼──────────────────────────────────────────────────────────┤
#   │ Max Pressure     │ d['eng']['pmax'][i]                                      │
#   ├──────────────────┼──────────────────────────────────────────────────────────┤
#   │ Dive Duration    │ d['eng']['divetime'][i]                                  │
#   ├──────────────────┼──────────────────────────────────────────────────────────┤
#   │ X-axis (all)     │ d['time'][i][0] — top-level unix timestamp, not from eng │
#   └──────────────────┴──────────────────────────────────────────────────────────┘
#
#   Dive figure (Figure 2) — time series for selected dive:
#
#   ┌──────────────┬────────────────────────────────────────────────────────┐
#   │   Subplot    │                       Data path                        │
#   ├──────────────┼────────────────────────────────────────────────────────┤
#   │ Heading      │ d['eng']['head'][dive_idx]                             │
#   ├──────────────┼────────────────────────────────────────────────────────┤
#   │ Pitch        │ d['eng']['pitch'][dive_idx]                            │
#   ├──────────────┼────────────────────────────────────────────────────────┤
#   │ Roll         │ d['eng']['roll'][dive_idx]                             │
#   ├──────────────┼────────────────────────────────────────────────────────┤
#   │ Pressure     │ d['eng']['p'][dive_idx]                                │
#   ├──────────────┼────────────────────────────────────────────────────────┤
#   │ X-axis (all) │ d['eng']['time'][dive_idx] — seconds within dive cycle │
#   └──────────────┴────────────────────────────────────────────────────────┘


app = dash.get_app()

# Module-level data loader — reloaded by _get_gdl() when data files change.
_gdl: GliderDataLoader | None = None
_gdl_version: str | None = None


def _get_gdl() -> GliderDataLoader:
    """Return the GliderDataLoader, reloading if data files have changed."""
    global _gdl, _gdl_version
    from pages.map.main import source_version
    v = source_version()
    if _gdl is None or v != _gdl_version:
        _gdl = GliderDataLoader(data_dir=Path("./data"), auto_load=True)
        _gdl_version = v
    return _gdl


def _empty_fig(msg="No data"):
    fig = go.Figure()
    fig.add_annotation(
        text=msg,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=18, color="grey"),
    )
    fig.update_layout(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        margin=dict(l=60, r=20, t=30, b=50),
    )
    return fig


# ---------------------------------------------------------------------------
# CB-1: Populate glider dropdown on page load
# ---------------------------------------------------------------------------
@app.callback(
    Output(EngControlIds.GLIDER_SELECT, "options"),
    Output(EngControlIds.GLIDER_SELECT, "value"),
    Input(EngControlIds.GLIDER_SELECT, "id"),
)
def populate_glider_options(_):
    sns = sorted(_get_gdl().glider_sns())
    opts = [{"label": f"Spray {sn:03d}", "value": sn} for sn in sns]
    mtimes = _get_gdl().sn_mtimes()
    most_recent = max(mtimes, key=mtimes.get) if mtimes else (sns[0] if sns else None)
    return opts, most_recent


# ---------------------------------------------------------------------------
# CB-2: Glider select → load data into stores, set dive input bounds
# ---------------------------------------------------------------------------
@app.callback(
    Output(EngStoreIds.GLIDER_DATA_STORE, "data"),
    Output(EngStoreIds.ENG_SUMMARY_STORE, "data"),
    Output(EngControlIds.DIVE_INPUT, "max"),
    Output(EngControlIds.DIVE_INPUT, "value"),
    Output(EngControlIds.DIVE_INPUT, "placeholder"),
    Input(EngControlIds.GLIDER_SELECT, "value"),
    prevent_initial_call=True,
)
def on_glider_select(glider_sn):
    if not glider_sn:
        raise PreventUpdate

    glider_sn = int(glider_sn)
    filename = _get_gdl().sn_to_filename(glider_sn)
    data = _get_gdl().glider_jsons[filename]
    eng = data["eng"]
    tl_time = data["time"]

    rows = []
    for i, ndive in enumerate(eng["ndive"]):
        if ndive is None:
            continue
        t_pair = tl_time[i] if i < len(tl_time) else None
        if not t_pair:
            continue
        dive_time = t_pair[0]
        p_series = eng["p"][i] if i < len(eng["p"]) else []
        rows.append({
            "ndive":    int(ndive),
            "datetime": dive_time,
            "psurf":    eng["psurf"][i],
            "pmax":     eng["pmax"][i],
            "pmin":     min(p_series) if p_series else None,
            "divetime": eng["divetime"][i],
        })

    max_dive = max(r["ndive"] for r in rows) if rows else 1

    store_data = {"sn": glider_sn, "max_dive": max_dive}
    summary_data = {"records": rows}

    return store_data, summary_data, max_dive, max_dive, str(max_dive)


# ---------------------------------------------------------------------------
# CB-3: Prev / next dive buttons
# ---------------------------------------------------------------------------
@app.callback(
    Output(EngControlIds.DIVE_INPUT, "value", allow_duplicate=True),
    Input(EngControlIds.DIVE_PREV, "n_clicks"),
    Input(EngControlIds.DIVE_NEXT, "n_clicks"),
    State(EngControlIds.DIVE_INPUT, "value"),
    State(EngStoreIds.GLIDER_DATA_STORE, "data"),
    prevent_initial_call=True,
)
def step_dive(n_prev, n_next, current, glider_store):
    if not glider_store:
        raise PreventUpdate
    max_dive = glider_store.get("max_dive", 1)
    current = current if current is not None else max_dive
    delta = -1 if dash.ctx.triggered_id == EngControlIds.DIVE_PREV else 1
    return max(1, min(max_dive, int(current) + delta))


# ---------------------------------------------------------------------------
# CB-4: Mission figure — pressures and dive duration over full mission
# ---------------------------------------------------------------------------
@app.callback(
    Output(EngGraphIds.MISSION_FIG, "figure"),
    Input(EngStoreIds.ENG_SUMMARY_STORE, "data"),
    Input(EngControlIds.DIVE_INPUT, "value"),
    prevent_initial_call=True,
)
def update_mission_fig(summary_store, dive_num):
    if not summary_store or not summary_store.get("records"):
        return _empty_fig("Select a glider")

    rows = summary_store["records"]
    # Extract columns, skipping None datetimes
    valid       = [r for r in rows if r["datetime"] is not None]
    xs          = [r["datetime"] for r in valid]
    psurf_y     = [r["psurf"]    for r in valid]
    pmax_y      = [r["pmax"]     for r in valid]
    pmin_y      = [r["pmin"]     for r in valid]
    divetime_y  = [r["divetime"] for r in valid]
    ndives      = [r["ndive"]    for r in valid]
    dt_strs     = [
        pd.Timestamp(r["datetime"], unit="s", tz="UTC").strftime("%Y-%m-%d %H:%M UTC")
        for r in valid
    ]
    cdata = list(zip(ndives, dt_strs))

    if not xs:
        return _empty_fig("No data")

    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=("Surface Pressure (db)", "Min Pressure (db)", "Max Pressure (db)", "Dive Duration (min)"),
    )

    common_scatter = dict(mode="lines+markers", marker=dict(size=4), line=dict(width=1.5), showlegend=False)

    fig.add_trace(go.Scatter(
        x=xs, y=psurf_y, name="p surf",
        **common_scatter,
        customdata=cdata,
        hovertemplate="%{customdata[1]}<br>Dive %{customdata[0]}<br>p surf: %{y:.2f} db<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=xs, y=pmin_y, name="p min",
        **common_scatter,
        customdata=cdata,
        hovertemplate="%{customdata[1]}<br>Dive %{customdata[0]}<br>p min: %{y:.1f} db<extra></extra>",
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=xs, y=pmax_y, name="p max",
        **common_scatter,
        customdata=cdata,
        hovertemplate="%{customdata[1]}<br>Dive %{customdata[0]}<br>p max: %{y:.1f} db<extra></extra>",
    ), row=3, col=1)

    fig.add_trace(go.Scatter(
        x=xs, y=divetime_y, name="duration",
        **common_scatter,
        customdata=cdata,
        hovertemplate="%{customdata[1]}<br>Dive %{customdata[0]}<br>Duration: %{y:.1f} min<extra></extra>",
    ), row=4, col=1)

    # X-axis ticks on shared axis (bottom subplot)
    tv, tt = time_ticks(min(xs), max(xs), fmt="datetime")
    fig.update_xaxes(tickvals=tv, ticktext=tt, row=4, col=1)

    fig.update_yaxes(autorange="reversed", row=1, col=1)
    fig.update_yaxes(autorange="reversed", row=2, col=1)
    fig.update_yaxes(autorange="reversed", row=3, col=1)

    # Vertical line for selected dive
    if dive_num is not None:
        matching = [r["datetime"] for r in rows if r["ndive"] == int(dive_num) and r["datetime"] is not None]
        if matching:
            fig.add_vline(x=matching[0], line_dash="dash", line_color="red", line_width=1.5)

    for ann in fig.layout.annotations:
        ann.update(x=0, xanchor="left")

    fig.update_layout(
        margin=dict(l=60, r=20, t=60, b=50),
        showlegend=False,
    )

    return fig


# ---------------------------------------------------------------------------
# CB-5: Dive figure — heading, pitch, roll, pressure for selected dive
# ---------------------------------------------------------------------------
@app.callback(
    Output(EngGraphIds.DIVE_FIG, "figure"),
    Input(EngControlIds.DIVE_INPUT, "value"),
    State(EngStoreIds.GLIDER_DATA_STORE, "data"),
    prevent_initial_call=True,
)
def update_dive_fig(dive_num, glider_store):
    if dive_num is None or not glider_store:
        raise PreventUpdate

    glider_sn = int(glider_store["sn"])
    filename = _get_gdl().sn_to_filename(glider_sn)
    eng = _get_gdl().glider_jsons[filename]["eng"]

    dive_idx = int(dive_num) - 1
    if dive_idx < 0 or dive_idx >= len(eng["time"]):
        return _empty_fig(f"Dive {dive_num} out of range")

    x = eng["time"][dive_idx]
    if not x:
        return _empty_fig(f"No data for dive {dive_num}")

    p     = eng["p"][dive_idx]
    head  = eng["head"][dive_idx]
    pitch = eng["pitch"][dive_idx]
    roll  = eng["roll"][dive_idx]

    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=("Heading (°)", "Pitch (°)", "Roll (°)", "Pressure (db)"),
    )

    def _fmt_s(s):
        s = int(round(s))
        if s < 3600:
            m, sec = divmod(s, 60)
            return f"{m}m {sec:02d}s"
        h, rem = divmod(s, 3600)
        return f"{h}h {rem // 60:02d}m"

    x_strs = [_fmt_s(v) for v in x]
    scatter_kw = dict(mode="lines", line=dict(width=1.5), showlegend=False)

    fig.add_trace(go.Scatter(x=x, y=head,  name="heading",
        customdata=x_strs,
        hovertemplate="%{customdata}<br>Heading: %{y:.1f}°<extra></extra>",
        **scatter_kw), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=pitch, name="pitch",
        customdata=x_strs,
        hovertemplate="%{customdata}<br>Pitch: %{y:.2f}°<extra></extra>",
        **scatter_kw), row=2, col=1)
    fig.add_trace(go.Scatter(x=x, y=roll,  name="roll",
        customdata=x_strs,
        hovertemplate="%{customdata}<br>Roll: %{y:.2f}°<extra></extra>",
        **scatter_kw), row=3, col=1)
    fig.add_trace(go.Scatter(x=x, y=p,     name="pressure",
        customdata=x_strs,
        hovertemplate="%{customdata}<br>Pressure: %{y:.1f} db<extra></extra>",
        **scatter_kw), row=4, col=1)

    # --- Y-axis defaults ---
    fig.update_yaxes(range=[0, 360], row=1, col=1)  # Heading
    fig.update_yaxes(range=[-25, 25], row=2, col=1)  # Pitch
    fig.update_yaxes(range=[-45, 45], row=3, col=1)  # Roll
    fig.update_yaxes(autorange="reversed", row=4, col=1)  # Pressure

    # X-axis ticks on bottom subplot (shared)
    tv, tt = time_ticks(min(x), max(x), fmt="s")
    fig.update_xaxes(tickvals=tv, ticktext=tt, row=4, col=1)
    fig.update_xaxes(title_text="Time in dive", row=4, col=1)

    for ann in fig.layout.annotations:
        ann.update(x=0, xanchor="left")

    fig.update_layout(
        title=dict(text=f"Dive {dive_num}", font=dict(size=14)),
        margin=dict(l=60, r=20, t=60, b=50),
        showlegend=False,
    )

    return fig
