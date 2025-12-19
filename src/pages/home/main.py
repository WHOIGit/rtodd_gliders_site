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
    name="Home",          # Text shown in navbar (via page["name"])
    title="GliderApp - Home", # <title> of the browser tab
)

app = dash.get_app()

map_fig_common_layout_kwargs = dict(
    mapbox_style="white-bg",
    map_layers=[
        {
            "below": 'traces',
            "sourcetype": "raster",
            # "sourceattribution": "Esri, Garmin, GEBCO, NOAA NGDC, and other contributors",
            "source": [
                "https://services.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}"
            ]
        },
    ],
    margin=dict(l=0, r=0, t=0, b=0),
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

    color_choice = "red" #color_choice or "red"

    fig = go.Figure()
    maxlat, minlat, maxlon, minlon = 0,0,0,0
    for glider_sn, records in latlon_dfs.items():
        df = pd.DataFrame(records)
        if df.empty or not {"lat", "lon"}.issubset(df.columns):
            continue

        # optional: filter by time range if available
        if time_range and "time" in df.columns:
            start, end = time_range
            df = df[(df["time"] >= start) & (df["time"] <= end)]

        if df.empty:
            continue
        maxlat,minlat = df["lat"].max() , df["lat"].min()
        maxlon,minlon = df["lon"].max(), df["lon"].min()
        fig.add_trace(
            go.Scattermap(
                lat=df["lat"],
                lon=df["lon"],
                mode="lines+markers",
                name=f"SN {glider_sn}",
                marker=dict(size=6, color=color_choice),
                line=dict(width=2, color=color_choice),
            )
        )

    if not fig.data:
        return blank_map()

    # Center/zoom roughly on data
    max_bound = max(abs(maxlon - minlon), abs(maxlat - minlat)) * 111
    zoom = 11.5 - np.log(max_bound)
    center = dict(lat=(maxlat + minlat) / 2, lon=(maxlon + minlon) / 2)
    fig.update_layout(
        map = dict(center=center, zoom=zoom),
        **map_fig_common_layout_kwargs,
    )

    return fig

