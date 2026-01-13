from itertools import cycle

import dash
from dash import Input, Output, State, dcc
import numpy as np

import plotly.graph_objects as go
import pandas as pd

# Dash pages expects a `layout` variable in the module
from .layout import layout
from names import *
from .names import *

# Register this file as a Dash "page"
dash.register_page(
    __name__,
    path="/",          # URL path
    name="Map",          # Text shown in navbar (via page["name"])
    title="GliderApp - Map2", # <title> of the browser tab
)

app = dash.get_app()

map_margins = dict(margin=dict(l=0, r=0, t=0, b=0))
map_fig_common_layout_kwargs = dict(
    style="white-bg",
    layers=[dict(
        below="traces",
        sourcetype="raster",
        source=[
            "https://services.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}"
        ])],
)

def blank_map():
    fig = go.Figure()
    fig.add_trace(go.Scattermap())
    fig.update_layout(**map_fig_common_layout_kwargs)
    return fig


@app.callback(
    Output(MapIds.GRAPH, "figure"),
    Input(StoreIds.DATA, "data"),
    Input(ControlIds.TIME_RANGE, "value")
)
def update_map(store_data, time_range):
    latlon_dfs = (store_data or {}).get("latlon_dfs", {})
    if not latlon_dfs:
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
    for glider_sn, records in latlon_dfs.items():
        color = next(COLOR_CYCLE)
        color_rgba = next(COLOR_CYCLE_RGBA)
        legendgroup = f"SN {glider_sn}"

        df = pd.DataFrame(records)
        if df.empty or not {"lat", "lon"}.issubset(df.columns):
            continue

        # optional: filter by time range if available
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
        if {"u", "v"}.issubset(df.columns):
            SCALE_FACTOR = 0.4
            df_uv = df.dropna()
            vlats, ulons = [], []
            for index, row in df_uv.iterrows():
                lat, lon = row["lat"], row["lon"]
                ulon, vlat = lon + row["u"]*SCALE_FACTOR, lat + row["v"]*SCALE_FACTOR
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
    zoom = 13 - np.log(max_bound)
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

