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


def rgb_to_hex(r:int, g:int, b:int, a=None):
    """
    Convert RGBA to HEX.
    r, g, b : int [0–255]
    a       : float [0–1]
    """
    if a is None:
        return "#{:02X}{:02X}{:02X}".format(
            int(r), int(g), int(b) )
    else:
        return "#{:02X}{:02X}{:02X}{:02X}".format(
            int(r), int(g), int(b), int(a * 255))


def blank_map():
    fig = go.Figure()
    fig.add_trace(go.Scattermap())
    fig.update_layout(map=map_fig_common_layout_kwargs)
    return fig

# TODO config file
REGION_PRESETS = {
    "global":      {"center": {"lat": 0, "lon": 0}, "zoom": 1.2},
    "gulfstream": {"center": {"lat": 35.0, "lon": -65.0}, "zoom": 4.2},
}

@app.callback(
    Output(MapIds.GRAPH, "figure"),
    Input(StoreIds.MAPDATA_STORE, "data"),
    Input(StoreIds.TIMERANGE_STORE, "data"),
    Input(ControlIds.UV_SCALE, "value"),
    Input(ControlIds.REGION_SELECT, "value"),
    prevent_initial_call=False,
)
def update_map(store_data, time_range, uv_scale, region_key):

    store_data = store_data or {}
    latlon_records = store_data.get("latlon_records", {})
    uv_records = store_data.get("uv_records", {})

    if not latlon_records:
        return blank_map()

    COLOR_CYCLE = cycle([
        ( 31, 119, 180), # blue
        (255, 127,  14), # orange
        ( 44, 160,  44), # green
        (214,  39,  40), # red
        (148, 103, 189), # purple
        (140,  86,  75), # brown
    ])

    fig = go.Figure()
    maxlat, minlat, maxlon, minlon = -180,180,-180,180
    for glider_sn, records in latlon_records.items():
        color_rgb = next(COLOR_CYCLE)
        color_hex = rgb_to_hex(*color_rgb)
        legendgroup = f"SN {glider_sn}"

        df = pd.DataFrame(records)
        df['dt'] = pd.to_datetime(df.time, unit='s')
        if df.empty or not {"lat", "lon"}.issubset(df.columns):
            continue

        num_of_sections = len(set(df.section))
        opacities = np.linspace(0.2, 1, num_of_sections) if num_of_sections > 1 else [1.0]

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

        for section, df_sec in df.groupby("section", sort=False):
            customdata = list(
                zip(
                    [glider_sn]*len(df_sec),
                    df_sec["section"],  # customdata[1]
                    df_sec["dt"].dt.date.astype(str),  # customdata[2]
                    df_sec["dt"].dt.time.astype(str),  # customdata[3]
                    df_sec["ndive"],  # customdata[4]
                )
            )
            opacity = opacities[section-1]
            color = 'rgba({},{},{},{})'.format(*color_rgb, opacity)
            fig.add_trace(
                go.Scattermap(
                    lat=df_sec["lat"],
                    lon=df_sec["lon"],
                    mode="lines", # markers+lines
                    name=f"SN {glider_sn}",
                    legendgroup=legendgroup,  # or f"{glider_sn}"
                    marker=dict(size=6, color=color),
                    line=dict(width=3, color=color),
                    hovertemplate=(
                        "<b>Glider %{customdata[0]}</b><br>"
                        "Lat: %{lat}<br>"
                        "Lon: %{lon}<br>"
                        "Date: %{customdata[2]}<br>"
                        "Time: %{customdata[3]}<br>"
                        "Section: %{customdata[1]}<br>"
                        "NDive: %{customdata[4]}<br>"
                        "<extra></extra>"
                    ),
                    customdata=customdata,
                    showlegend=bool(opacity == 1),
                )
            )

        # df['datetimestr'] = pd.to_datetime(df.time, unit='s').dt.strftime('%Y-%m-%d %H:%M:%S')
        # customdata = [[glider_sn, int(section), datestr.split()[0], datestr.split()[1]] for datestr, section in zip(df.datetimestr, df.section)]
        #
        # # add trace for this glider
        # fig.add_trace(go.Scattermap(
        #     lat=df["lat"],
        #     lon=df["lon"],
        #     mode="markers+lines",
        #     name=f"SN {glider_sn}",
        #     legendgroup = legendgroup,
        #     marker=dict(size=6, color=color),
        #     line=dict(width=3, color=color),
        #     hovertemplate=(
        #         "<b>Glider %{customdata[0]}</b><br>"
        #         "Lat: %{lat}<br>"
        #         "Lon: %{lon}<br>"
        #         "Date: %{customdata[2]}<br>"
        #         "Time: %{customdata[3]}<br>"
        #         "Section: %{customdata[1]}"
        #         "<extra></extra>"
        #     ),
        #     customdata=customdata,
        # ))

        # add u,v vectors if available
        if uv_records and glider_sn in uv_records:
            uv_recs = uv_records[glider_sn]
            df_uv = pd.DataFrame(uv_recs)

            if time_range and "time" in df_uv.columns:
                start, end = time_range
                df_uv = df_uv[(df_uv["time"] >= start) & (df_uv["time"] <= end)]

            for section, df_uv_sec in df_uv.groupby("section", sort=False):

                opacity = opacities[section - 1]
                color = 'rgba({},{},{},{})'.format(*color_rgb, opacity)

                vlats, ulons = [], []
                for _, row in df_uv_sec.iterrows():
                    lat, lon = row["lat"], row["lon"]
                    vlat,ulon = latlon_offset(lat, lon, row["v"], row["u"], uv_scale)
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
                    line=dict(width=1, color=color), # argh, no OPACITY
                ))

        # image at end of trace
        end = df.iloc[-1]
        fig.add_trace(go.Scattermap(
            lat=[end["lat"]],
            lon=[end["lon"]],
            name=f"SN {glider_sn} Endpoint",
            mode="markers",
            marker=dict(
                size=30,
                symbol=f"star",
            ),
            legendgroup = legendgroup,
            showlegend=False,
            hovertemplate=(
                "<b>Glider %{customdata[0]}</b><br>"
                "Lat: %{lat}<br>"
                "Lon: %{lon}<br>"
                "Date: %{customdata[2]}<br>"
                "Time: %{customdata[3]}<br>"
                "Section: %{customdata[1]}<br>"
                "NDive: %{customdata[4]}<br>"
                "<extra></extra>"
            ),
            customdata=[customdata[-1]]
        ))

    if not fig.data:
        return blank_map()

    # Set Center and Zoom
    if region_key == 'auto':
        max_bound = max(abs(maxlon - minlon), abs(maxlat - minlat)) * 111
        zoom = 12 - np.log(max_bound)
        center = dict(lat=(maxlat + minlat) / 2, lon=(maxlon + minlon) / 2)
    else:
        region_preset = REGION_PRESETS.get(region_key, REGION_PRESETS["global"])
        center = region_preset["center"]
        zoom = region_preset["zoom"]
    #print(region_key, center, zoom)

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
        **map_margins,
    )

    return fig

def source_version():
    gdl = GliderDataLoader(data_dir=Path("../data"))
    latest_mtime = gdl.latest_filemodified_timestamp()
    #print(latest_mtime, type(latest_mtime))
    return latest_mtime


def load_mapdata_from_source():
    """
    Return a dict shaped like:
    {
      "latlon_records": { "<sn>": [ {"lat":..., "lon":..., "time":...}, ... ], ... },
      "uv_records": { "<sn>": [ {"lat":..., "lon":..., "time":..., "u":..., "v":...}, ... ], ... },
    }
    """
    gdl = GliderDataLoader(data_dir=Path("../data"))
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


@app.callback(
    Output(ControlIds.GLIDER_SELECT, "options"),
    Input(StoreIds.MAPDATA_STORE, "data"),
)
def set_glider_options(store_data):
    store_data = store_data or {}
    latlon_records = store_data.get("latlon_records", {})
    sns = sorted(latlon_records.keys())
    return [{"label": f"SN {sn}", "value": str(sn)} for sn in sns]


@app.callback(
    Output(TextIds.SECTION_DETAILS_TEXT, "children"),
    Input(ControlIds.GLIDER_SELECT, "value"),
    Input(ControlIds.SECTION_SELECT, "value"),
    State(StoreIds.MAPDATA_STORE, "data"),
)
def populate_section_details(glider_sn, section_num, store_data):
    if not glider_sn or section_num is None:
        return "Select a glider and section to see details."

    store_data = store_data or {}

    # TEMPLATE: replace with real lookup
    # Example text:
    return (
        f"Glider: SN {glider_sn}\n"
        f"Section: {section_num}\n\n"
        "Details:\n"
        f"- {store_data.keys()}\n"
        "- …\n"
    )

def get_sections_for_glider(store_data, glider_sn):
    # TEMPLATE: replace with your real source.
    latlon_records = (store_data or {}).get("latlon_records", {})
    recs = latlon_records.get(glider_sn, [])
    secs = sorted({int(r["section"]) for r in recs if "section" in r and r["section"] is not None})
    return secs

@app.callback(
    Output(ControlIds.GLIDER_SELECT, "value"),
    Output(ControlIds.SECTION_SELECT, "options"),
    Output(ControlIds.SECTION_SELECT, "value"),
    Output(ContainerIds.MAP_ACCORDION, "active_item"),
    Input(MapIds.GRAPH, "clickData"),
    Input(ControlIds.GLIDER_SELECT, "value"),
    State(StoreIds.MAPDATA_STORE, "data"),
    State(ContainerIds.MAP_ACCORDION, "active_item"),
    prevent_initial_call=True,
)
def sync_section_ui(clickData, glider_value, store_data, active_item):
    trig = dash.ctx.triggered_id

    # Defaults: don't change unless we decide to
    new_glider = no_update
    new_section_value = no_update
    new_active = no_update

    # Determine glider + section from click if that's the trigger
    clicked_glider = None
    clicked_section = None
    if trig == MapIds.GRAPH:
        if not clickData or not clickData.get("points"):
            raise PreventUpdate
        cd = clickData["points"][0].get("customdata")
        if not cd or len(cd) < 2:
            raise PreventUpdate
        clicked_glider = str(cd[0])
        try:
            clicked_section = int(cd[1])
        except Exception:
            clicked_section = None

        new_glider = clicked_glider
        new_section_value = clicked_section

        # open accordion on map click
        new_active = [ContainerIds.SECTION_DETAILS] if isinstance(active_item, list) else ContainerIds.SECTION_DETAILS

        glider_for_options = clicked_glider

    else:
        # manual glider dropdown change -> just update section options
        if not glider_value:
            # no glider -> clear sections
            return glider_value, [], None, no_update

        glider_for_options = str(glider_value)
        new_glider = glider_for_options
        # don't open accordion just because dropdown changed
        new_active = no_update
        # keep section value as-is (Dash may clear it if not in new options)
        new_section_value = no_update

    # Build section options for the chosen glider
    sections = get_sections_for_glider(store_data, glider_for_options)
    opts = [{"label": str(s), "value": s} for s in sections]

    # If click provided a section, ensure it's present in options so value sticks
    if trig == MapIds.GRAPH and clicked_section is not None and clicked_section not in sections:
        opts = [{"label": str(clicked_section), "value": clicked_section}] + opts

    return new_glider, opts, new_section_value, new_active




