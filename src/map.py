from dash import Input, Output, State, dcc
from names import *

import numpy as np
def register_map_plots(app):
    @app.callback(
        Output(MapIds.GRAPH, "figure"),
        Input(StoreIds.DATA, "data"),
        Input(ControlIds.TIME_RANGE, "value"),
        Input(ControlIds.MAP_COLOR_RADIO, "value"),
    )
    def update_map(store_data, time_range, color_choice):
        import plotly.graph_objects as go
        import pandas as pd

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

        latlon_dfs = (store_data or {}).get("latlon_dfs", {})
        if not latlon_dfs:
            # blank map
            fig = go.Figure()
            fig.update_layout(**map_fig_common_layout_kwargs,)
            return fig

        color_choice = color_choice or "red"

        fig = go.Figure()
        maxlat, minlan, maxlon, minlon = 0,0,0,0
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
            # still nothing → blank map
            fig = go.Figure()
            fig.update_layout(**map_fig_common_layout_kwargs)
            return fig

        # Center/zoom roughly on data
        max_bound = max(abs(maxlon - minlon), abs(maxlat - minlat)) * 111
        zoom = 11.5 - np.log(max_bound)
        center = dict(lat=(maxlat + minlat) / 2, lon=(maxlon + minlon) / 2)
        fig.update_layout(
            map = dict(center=center, zoom=zoom),
            **map_fig_common_layout_kwargs,
        )

        return fig