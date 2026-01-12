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

map_margins = dict(margin=dict(l=0, r=0, t=0, b=0), autosize=True)

def blank_map():
    fig = go.Figure()
    fig.add_trace(go.Scattermap())
    fig.update_layout(**map_margins)
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
    maxlat, minlat, maxlon, minlon = -180,180,-180,180
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

        # set map bounds
        minlat = min(minlat, float(df["lat"].min()))
        maxlat = max(maxlat, float(df["lat"].max()))
        minlon = min(minlon, float(df["lon"].min()))
        maxlon = max(maxlon, float(df["lon"].max()))

        # add trace for this glider
        fig.add_trace(go.Scattergeo(
            lat=df["lat"],
            lon=df["lon"],
            mode="lines+markers",
            name=f"SN {glider_sn}",
            marker=dict(size=6, color=color_choice),
            line=dict(width=2, color=color_choice),
            hovertemplate=(
                "<b>Glider %{customdata[0]}</b><br>"
                "Lat: %{lat}<br>"
                "Lon: %{lon}<extra></extra>"
            ),
            customdata=[[glider_sn]]*len(df),
        ))

        # add u,v vectors if available
        if {"u", "v"}.issubset(df.columns):
            df_uv = df.dropna()
            vlats,ulons = [],[]
            for index, row in df_uv.iterrows():
                lat, lon = row["lat"], row["lon"]
                ulon, vlat = lon+row["u"], lat+row["v"]
                ulons += [lon, ulon, None]
                vlats += [lat, vlat, None]
            fig.add_trace(go.Scattergeo(
                lat=vlats,
                lon=ulons,
                mode="lines",
                name=f"SN {glider_sn} UV",
                line=dict(width=2, color='green'),
                showlegend=False,
                hoverinfo="skip",
            ))
        # image at end of trace
        lat_end = df["lat"].iloc[-1]
        lon_end = df["lon"].iloc[-1]

        fig.add_trace(go.Scattergeo(
            lat=[lat_end],
            lon=[lon_end],
            mode="markers",
            marker=dict(
                size=30,
                symbol="diamond-tall",
            ),
            name=f"SN {glider_sn} Endpoint",
            #showlegend=False,
            hovertemplate=(
                "<b>Glider %{customdata[0]}</b><br>"
                "Lat: %{lat}<br>"
                "Lon: %{lon}<extra></extra>"
            ),
            customdata=[[glider_sn]],
        ))
        print(lat_end,lon_end)
    if not fig.data:
        return blank_map()

    # Legend inside map
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

    fig.update_layout(**map_margins, legend=legend_layout, uirevision="map")
    fig.update_geos(
        domain=dict(x=[0, 1], y=[0, 1]),
        fitbounds="locations",
        visible=True,
        showocean=True,
        oceancolor="#cfe8f3",
        showland=True,
        landcolor="#f5f5f5",
        coastlinecolor="#444",
        showcountries=False,
        projection_type="mercator",
    )

    return fig

