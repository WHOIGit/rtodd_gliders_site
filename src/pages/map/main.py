from itertools import cycle
import time
import datetime as dt
from pathlib import Path

import dash
from dash import Input, Output, State, no_update, clientside_callback
import numpy as np

import plotly.graph_objects as go
import pandas as pd

# Dash pages expects a `layout` variable in the module
from dash.exceptions import PreventUpdate

from data_loader import GliderDataLoader
from utils import latlon_offset
from .layout import layout
from names import *
from .names import *

# Register this file as a Dash "page"
dash.register_page(
    __name__,
    path="/",          # URL path
    name="Map",          # Text shown in navbar (via page["name"])
    title="GliderApp - Map", # <title> of the browser tab
)

app = dash.get_app()

map_margins = dict(margin=dict(l=0, r=0, t=0, b=0))
map_fig_common_layout_kwargs = dict(
    #style="white-bg",
    layers=[dict(
        below="traces",
        sourcetype="raster",
        source=[
            "https://services.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}"
        ])],
)


def _date_to_epoch_start(date_str):
    # date_str: "YYYY-MM-DD" -> epoch at 00:00:00 UTC
    d = dt.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp())

def _date_to_epoch_end(date_str):
    # epoch at 23:59:59 UTC
    d = dt.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    d = d + dt.timedelta(days=1) - dt.timedelta(seconds=1)
    return int(d.timestamp())

@app.callback(
    Output(StoreIds.TIMERANGE_STORE, "data"),
    Output(StoreIds.TIMEBTN_ACTIVE_STORE, "data"),
    Input(ControlIds.TIME_BTN_DAY, "n_clicks"),
    Input(ControlIds.TIME_BTN_WEEK, "n_clicks"),
    Input(ControlIds.TIME_BTN_MONTH, "n_clicks"),
    Input(ControlIds.TIME_BTN_ALL, "n_clicks"),
    Input(ControlIds.TIME_BTN_X, "n_clicks"),
    Input(ControlIds.TIME_RANGE_PICKER, "start_date"),
    Input(ControlIds.TIME_RANGE_PICKER, "end_date"),
    prevent_initial_call=True,
)
def update_timerange_store(
    day, week, month, all_, custom_btn,
    start_date, end_date,
):
    trig = dash.ctx.triggered_id
    now = end = int(time.time())
    start = 0

    if trig == ControlIds.TIME_BTN_DAY:
        start = now - 1 * 24 * 3600

    elif trig == ControlIds.TIME_BTN_WEEK:
        start = now - 7 * 24 * 3600

    elif trig == ControlIds.TIME_BTN_MONTH:
        start = now - 30 * 24 * 3600

    elif trig == ControlIds.TIME_BTN_X:
        if not start_date:
            return no_update, ControlIds.TIME_BTN_X
        start = _date_to_epoch_start(start_date)
        end = _date_to_epoch_end(end_date) if end_date else now

    elif trig == ControlIds.TIME_RANGE_PICKER:
        if not start_date:
            return no_update, no_update
        start = _date_to_epoch_start(start_date)
        end = _date_to_epoch_end(end_date) if end_date else now
        return [start, end], ControlIds.TIME_BTN_X

    else: # trig == ControlIds.TIME_BTN_ALL
        return None, trig

    return [start, end], trig



@app.callback(
    Output(ControlIds.TIME_BTN_DAY, "outline"),
    Output(ControlIds.TIME_BTN_WEEK, "outline"),
    Output(ControlIds.TIME_BTN_MONTH, "outline"),
    Output(ControlIds.TIME_BTN_ALL, "outline"),
    Output(ControlIds.TIME_BTN_X, "outline"),
    Input(StoreIds.TIMEBTN_ACTIVE_STORE, "data"),
)
def set_active_time_button(active_btn_id):
    def inactive(btn_id):
        return active_btn_id != btn_id

    return (
        inactive(ControlIds.TIME_BTN_DAY),
        inactive(ControlIds.TIME_BTN_WEEK),
        inactive(ControlIds.TIME_BTN_MONTH),
        inactive(ControlIds.TIME_BTN_ALL),
        inactive(ControlIds.TIME_BTN_X),
    )



def blank_map():
    fig = go.Figure()
    fig.add_trace(go.Scattermap())
    fig.update_layout(map=map_fig_common_layout_kwargs)
    return fig


@app.callback(
    Output(MapIds.GRAPH, "figure"),
    Input(StoreIds.MAPDATA_STORE, "data"),
    Input(StoreIds.TIMERANGE_STORE, "data"),
    prevent_initial_call=False,
)
def update_map(store_data, time_range):
    print("store_data", type(store_data), time_range)

    store_data = store_data or {}
    latlon_records = store_data.get("latlon_records", {})
    uv_records = store_data.get("uv_records", {})

    if not latlon_records:
        return blank_map()

    COLOR_CYCLE = cycle([
        "#1f77b4",  # blue
        "#ff7f0e",  # orange
        "#2ca02c",  # green
        "#d62728",  # red
        "#9467bd",  # purple
        "#8c564b",  # brown
    ])
    opacity = 0.6
    COLOR_CYCLE_RGBA = cycle([
        f"rgba(31, 119, 180, {opacity})",  # blue
        f"rgba(255, 127, 14, {opacity})",  # orange
        f"rgba(44, 160, 44, {opacity})",  # green
        f"rgba(214, 39, 40, {opacity})",  # red
        f"rgba(148, 103, 189, {opacity})",  # purple
        f"rgba(140, 86, 75, {opacity})",  # brown
    ])

    fig = go.Figure()
    maxlat, minlat, maxlon, minlon = -180,180,-180,180
    for glider_sn, records in latlon_records.items():
        color = next(COLOR_CYCLE)
        color_rgba = next(COLOR_CYCLE_RGBA)
        legendgroup = f"SN {glider_sn}"

        df = pd.DataFrame(records)
        if df.empty or not {"lat", "lon"}.issubset(df.columns):
            continue

        # filter by time range if available
        if time_range and "time" in df.columns:
            start, end = time_range
            df = df[(df["time"] >= start) & (df["time"] <= end)]

        if df.empty:
            continue

        # set map bounds
        minlat = min(minlat, float(df["lat"].min()))
        maxlat = max(maxlat, float(df["lat"].max()))
        minlon = min(minlon, float(df["lon"].min()))
        maxlon = max(maxlon, float(df["lon"].max()))

        df['datetimestr'] = pd.to_datetime(df.time, unit='s').dt.strftime('%Y-%m-%d %H:%M:%S')
        customdata = [[glider_sn, datestr.split()[0], datestr.split()[1]] for datestr in df.datetimestr]

        # add trace for this glider
        fig.add_trace(go.Scattermap(
            lat=df["lat"],
            lon=df["lon"],
            mode="markers+lines",
            name=f"SN {glider_sn}",
            legendgroup = legendgroup,
            marker=dict(size=6, color=color),
            line=dict(width=3, color=color),
            hovertemplate=(
                "<b>Glider %{customdata[0]}</b><br>"
                "Lat: %{lat}<br>"
                "Lon: %{lon}<br>"
                "Date: %{customdata[1]}<br>"
                "Time: %{customdata[2]}"
                "<extra></extra>"
            ),
            customdata=customdata,
        ))

        # add u,v vectors if available
        if uv_records and glider_sn in uv_records:
            SCALE_FACTOR = 1
            uv_recs = uv_records[glider_sn]
            df_uv = pd.DataFrame(uv_recs)
            if time_range and "time" in df.columns:
                start, end = time_range
                df_uv = df_uv[(df_uv["time"] >= start) & (df_uv["time"] <= end)]
            vlats, ulons = [], []
            for _, row in df_uv.iterrows():
                lat, lon = row["lat"], row["lon"]
                vlat,ulon = latlon_offset(lat, lon, row["v"], row["u"], SCALE_FACTOR)
                ulons += [lon, ulon, None]
                vlats += [lat, vlat, None]
            fig.add_trace(go.Scattermap(
                lat=vlats,
                lon=ulons,
                name=f"SN {glider_sn} UV",
                legendgroup=legendgroup,
                showlegend=False,
                hoverinfo="skip",
                mode="lines",
                line=dict(width=1, color=color_rgba), # argh, no OPACITY
            ))

        # image at end of trace
        lat_end = df["lat"].iloc[-1]
        lon_end = df["lon"].iloc[-1]
        fig.add_trace(go.Scattermap(
            lat=[lat_end],
            lon=[lon_end],
            name=f"SN {glider_sn} Endpoint",
            mode="markers",
            marker=dict(
                size=30,
                symbol="star",
                color=color,
            ),
            legendgroup = legendgroup,
            showlegend=False,
            hovertemplate=(
                "<b>Glider %{customdata[0]}</b><br>"
                "Lat: %{lat}<br>"
                "Lon: %{lon}<br>"
                "Date: %{customdata[1]}<br>"
                "Time: %{customdata[2]}"
                "<extra></extra>"
            ),
            customdata=[customdata[-1]]
        ))

    if not fig.data:
        return blank_map()

    # Center/zoom roughly on data
    max_bound = max(abs(maxlon - minlon), abs(maxlat - minlat)) * 111
    zoom = 12 - np.log(max_bound)
    center = dict(lat=(maxlat + minlat) / 2, lon=(maxlon + minlon) / 2)

    legend_layout = dict(
        x=0.99,
        y=0.96,
        xanchor="right",
        yanchor="top",
        bgcolor="rgba(255,255,255,0.7)",
        bordercolor="rgba(0,0,0,0.2)",
        borderwidth=1,
        orientation="v",
    )

    fig.update_layout(
        map=dict(
            center=center,
            zoom=zoom,
            **map_fig_common_layout_kwargs,
        ),
        legend = legend_layout,
        uirevision="map",
        **map_margins,
    )

    return fig

def source_version():
    gdl = GliderDataLoader(data_dir=Path("./data"))
    latest_mtime = gdl.latest_filemodified_timestamp()
    #print(latest_mtime, type(latest_mtime))
    return latest_mtime


def load_mapdata_from_source():
    """
    Return a dict shaped like:
    {
      "latlon_records": { "<sn>": [ {"lat":..., "lon":..., "time":...}, ... ], ... },
      "uv_records": { "<sn>": [ {"lat":..., "lon":..., "time":..., "u":..., "v":...}, ... ], ... },
      ...anything else you want...
    }
    """
    gdl = GliderDataLoader(data_dir=Path("./data"))
    gdl.load_glider_json()
    latlon_records, uv_records = {}, {}
    for sn in gdl.glider_sns():
        latlon_records[sn] = gdl.build_glider_df(glider_sn=sn).to_dict('records')

        uv_sn_df = gdl.build_uv_df(glider_sn=sn)
        new_lats, new_lons = latlon_offset(
            uv_sn_df["lat"].values,
            uv_sn_df["lon"].values,
            uv_sn_df["v"].values,
            uv_sn_df["u"].values,
            scale=1
        )
        uv_sn_df['uvlat'] = new_lats
        uv_sn_df['uvlon'] = new_lons
        uv_records[sn] = uv_sn_df.to_dict('records')

    return {
        "latlon_records": latlon_records,
        "uv_records": uv_records,
    }


def default_timerange_seconds(days_back=7):
    now = int(time.time())
    start = now - days_back * 24 * 3600
    return start, now  # match your existing update_map expectation


@app.callback(
    Output(StoreIds.MAPDATA_STORE, "data"),
    Output(StoreIds.MAPDATA_STORE_STATE, "data"),
    Input("url", "pathname"),
    State(StoreIds.MAPDATA_STORE_STATE, "data"),
    prevent_initial_call=False,   # run on first load
)
def init_mapdata_on_session(pathname, init_state):
    # Normalize
    version = source_version()
    #print("MAP PAGE: session init, is initialized?", init_state, version)

    # Already initialized → do nothing
    if init_state['initialized'] and version == init_state['version']:
        raise PreventUpdate

    # Load once
    mapdata = load_mapdata_from_source()

    return mapdata, dict(initialized=True, version=version)


@app.callback(
    Output(ContainerIds.HIDDEN_CUSTOMTIME_CONTAINER, "style"),
    Input(ControlIds.TIME_BTN_X, "n_clicks"),
    Input(ControlIds.TIME_BTN_DAY, "n_clicks"),
    Input(ControlIds.TIME_BTN_WEEK, "n_clicks"),
    Input(ControlIds.TIME_BTN_MONTH, "n_clicks"),
    Input(ControlIds.TIME_BTN_ALL, "n_clicks"),
    prevent_initial_call=True,
)
def toggle_custom_time_picker(
    n_custom, n_day, n_week, n_month, n_all
):
    trigger = dash.ctx.triggered_id

    if trigger == ControlIds.TIME_BTN_X:
        # show date picker
        return {"display": "block"}

    # any other button hides it
    return {"display": "none"}



