from pathlib import Path

import pandas as pd

import dash
from dash import Input, Output, State, no_update, html
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data_loader import GliderDataLoader, parse_mission_yyyymmm, get_gdl as _get_gdl
from utils import time_ticks, load_region_labels
from .layout import layout
from .names import EngStoreIds, EngControlIds, EngGraphIds

_REGION_LABELS = load_region_labels(Path("config/map_config.yml").resolve())


def _region_display(key: str) -> str:
    return _REGION_LABELS.get(key, key)


def _make_search_text(*parts):
    pieces = []
    for p in parts:
        if not p:
            continue
        s = str(p).lower()
        pieces.append(s)
        if " " in s:
            pieces.append(s.replace(" ", ""))
    return " ".join(pieces)


def _matches_query(search_text, query):
    if not query:
        return True
    return all(tok in search_text for tok in query.lower().split())

dash.register_page(
    __name__,
    path="/plotting/engineering",
    name="Engineering",
    title="Gliders - Engineering",
)

#   ┌──────────────────┬──────────────────────────────────────────────────────────┐
#   │     Subplot      │                        Data path                         │
#   ├──────────────────┼──────────────────────────────────────────────────────────┤
#   │ Surface Pressure │ gdl.build_eng_summary_records()[i]["psurf"]              │
#   ├──────────────────┼──────────────────────────────────────────────────────────┤
#   │ Min Pressure     │ derived from the NetCDF eng pressure row                  │
#   ├──────────────────┼──────────────────────────────────────────────────────────┤
#   │ Max Pressure     │ gdl.build_eng_summary_records()[i]["pmax"]               │
#   ├──────────────────┼──────────────────────────────────────────────────────────┤
#   │ Dive Duration    │ derived from top-level track start/end times             │
#   ├──────────────────┼──────────────────────────────────────────────────────────┤
#   │ X-axis (all)     │ top-level unix timestamp from the NetCDF track group     │
#   └──────────────────┴──────────────────────────────────────────────────────────┘
#
#   Dive figure (Figure 2) — time series for selected dive:
#
#   ┌──────────────┬────────────────────────────────────────────────────────┐
#   │   Subplot    │                       Data path                        │
#   ├──────────────┼────────────────────────────────────────────────────────┤
#   │ Heading      │ gdl.build_eng_dive()["head"]                          │
#   ├──────────────┼────────────────────────────────────────────────────────┤
#   │ Pitch        │ gdl.build_eng_dive()["pitch"]                         │
#   ├──────────────┼────────────────────────────────────────────────────────┤
#   │ Roll         │ gdl.build_eng_dive()["roll"]                          │
#   ├──────────────┼────────────────────────────────────────────────────────┤
#   │ Pressure     │ gdl.build_eng_dive()["p"]                             │
#   ├──────────────┼────────────────────────────────────────────────────────┤
#   │ X-axis (all) │ gdl.build_eng_dive()["time"] — seconds within dive     │
#   └──────────────┴────────────────────────────────────────────────────────┘


app = dash.get_app()

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
_GRAY = {"color": "#999", "marginLeft": "0.5em"}
_DISABLED_PRIMARY = {"color": "#aaa"}


def _option_label(primary: str, suffix: str, disabled: bool = False):
    primary_node = html.Span(primary, style=_DISABLED_PRIMARY) if disabled else primary
    if not suffix:
        return html.Span([primary_node]) if disabled else primary
    return html.Span([primary_node, html.Span(suffix, style=_GRAY)])


@app.callback(
    Output(EngControlIds.GLIDER_SELECT, "options"),
    Output(EngControlIds.GLIDER_SELECT, "value"),
    Output(EngControlIds.GLIDER_SELECT, "placeholder"),
    Output(EngControlIds.GLIDER_LABEL, "children"),
    Input(EngControlIds.ARCHIVED_TOGGLE, "value"),
    Input(EngControlIds.GLIDER_SELECT, "search_value"),
    State(EngControlIds.GLIDER_SELECT, "value"),
)
def populate_glider_options(archived_value, search_value, current_value):
    gdl = _get_gdl()
    archived = "on" in (archived_value or [])
    is_search = dash.ctx.triggered_id == EngControlIds.GLIDER_SELECT

    if archived:
        rows = []
        for mid in gdl.archive_mission_ids():
            meta = gdl.archive_missions.get(mid, {})
            region_key = meta.get("region", "")
            region_lbl = _region_display(region_key)
            yymm = parse_mission_yyyymmm(mid)
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

    glider_sn = str(glider_sn)
    gdl = _get_gdl()
    if len(glider_sn) > 4 or glider_sn in gdl.archive_missions:
        gdl.load_archived(glider_sn)
    rows = gdl.build_eng_summary_records(glider_sn)
    if not rows:
        raise PreventUpdate

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
# CB-4: Mission figure click → selected dive
# ---------------------------------------------------------------------------
@app.callback(
    Output(EngControlIds.DIVE_INPUT, "value", allow_duplicate=True),
    Input(EngGraphIds.MISSION_FIG, "clickData"),
    prevent_initial_call=True,
)
def select_dive_from_mission_click(click_data):
    if not click_data or not click_data.get("points"):
        raise PreventUpdate

    pt = click_data["points"][0]
    customdata = pt.get("customdata")
    if not customdata:
        raise PreventUpdate

    dive_num = customdata[0]
    if dive_num is None:
        raise PreventUpdate

    return int(dive_num)


# ---------------------------------------------------------------------------
# CB-5: Mission figure — pressures and dive duration over full mission
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
    fig.update_traces(xaxis="x4", hoverinfo="skip")
    fig.update_layout(xaxis=dict(showspikes=True), clickmode="event")
    fig.update_xaxes(
        showspikes=True,
        spikemode="across",   # line spans all subplots
        spikesnap="cursor",
        showline=True,
    )

    fig.update_yaxes(autorange="reversed", row=1, col=1)
    fig.update_yaxes(autorange="reversed", row=2, col=1)
    fig.update_yaxes(autorange="reversed", row=3, col=1)

    # Vertical line for selected dive (one shape per subplot row to span all)
    if dive_num is not None:
        matching = [r["datetime"] for r in rows if r["ndive"] == int(dive_num) and r["datetime"] is not None]
        if matching:
            for row in range(1, 5):
                yref = "y" if row == 1 else f"y{row}"
                fig.add_shape(
                    type="line",
                    x0=matching[0], x1=matching[0],
                    y0=0, y1=1,
                    xref="x4",
                    yref=f"{yref} domain",
                    line=dict(dash="dash", color="red", width=1.5),
                )

    for ann in fig.layout.annotations:
        ann.update(x=0, xanchor="left")

    fig.update_layout(
        margin=dict(l=60, r=20, t=60, b=50),
        showlegend=False,
    )

    return fig


# ---------------------------------------------------------------------------
# CB-6: Dive figure — heading, pitch, roll, pressure for selected dive
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

    glider_sn = str(glider_store["sn"])
    gdl = _get_gdl()
    if len(glider_sn) > 4 or glider_sn in gdl.archive_missions:
        gdl.load_archived(glider_sn)
    dive = gdl.build_eng_dive(glider_sn, int(dive_num))
    if dive is None:
        return _empty_fig(f"Dive {dive_num} out of range")

    x = dive["time"]
    if not x:
        return _empty_fig(f"No data for dive {dive_num}")

    t0 = dive["t0"]
    p     = dive["p"]
    head  = dive["head"]
    pitch = dive["pitch"]
    roll  = dive["roll"]

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
    dt_strs = [""] * len(x)
    if t0 is not None:
        dt_strs = [
            pd.Timestamp(t0 + v, unit="s", tz="UTC").strftime("%Y-%m-%d %H:%M:%S UTC")
            for v in x
        ]
    customdata = list(zip(x_strs, dt_strs))

    scatter_kw = dict(mode="lines", line=dict(width=1.5), showlegend=False)

    fig.add_trace(go.Scatter(x=x, y=head,  name="heading",
        customdata=customdata,
        hovertemplate="%{customdata[1]}<br>Dive Time: %{customdata[0]}<br>Heading: %{y:.1f}°<extra></extra>",
        **scatter_kw), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=pitch, name="pitch",
        customdata=customdata,
        hovertemplate="%{customdata[1]}<br>Dive Time: %{customdata[0]}<br>Pitch: %{y:.1f}°<extra></extra>",
        **scatter_kw), row=2, col=1)
    fig.add_trace(go.Scatter(x=x, y=roll,  name="roll",
        customdata=customdata,
        hovertemplate="%{customdata[1]}<br>Dive Time: %{customdata[0]}<br>Roll: %{y:.1f}°<extra></extra>",
        **scatter_kw), row=3, col=1)
    fig.add_trace(go.Scatter(x=x, y=p,     name="pressure",
        customdata=customdata,
        hovertemplate="%{customdata[1]}<br>Dive Time: %{customdata[0]}<br>Pressure: %{y:.1f} db<extra></extra>",
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
    fig.update_traces(xaxis="x4", hoverinfo="skip")
    fig.update_layout(xaxis=dict(showspikes=True))
    fig.update_xaxes(
        showspikes=True,
        spikemode="across",   # line spans all subplots
        spikesnap="cursor",
        showline=True,
    )

    for ann in fig.layout.annotations:
        ann.update(x=0, xanchor="left")

    fig.update_layout(
        title=dict(text=f"Dive {dive_num}", font=dict(size=14)),
        margin=dict(l=60, r=20, t=60, b=50),
        showlegend=False,
    )

    return fig
