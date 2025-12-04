# plots.py
from dash import Input, Output, dcc, html
import pandas as pd
import plotly.express as px

from names import ControlIds, MapIds, TabsIds, StoreIds


def _df_from_store(store_data):
    if not store_data or "data" not in store_data:
        return pd.DataFrame()
    df = pd.DataFrame(store_data["data"])
    if 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'], errors='coerce')
    return df


def register_plot_callbacks(app):
    # Map callback: responds to data, time range, and color selection
    @app.callback(
        Output(MapIds.GRAPH, "figure"),
        Input(StoreIds.DATA, "data"),
        Input(ControlIds.TIME_RANGE, "value"),
        Input(ControlIds.MAP_COLOR_RADIO, "value"),
    )
    def update_map(store_data, time_range, color_choice):
        df = _df_from_store(store_data)

        # Empty or missing columns -> blank map
        if df.empty or "lat" not in df.columns or "lon" not in df.columns:
            blank = px.scatter_mapbox(
                pd.DataFrame({"lat": [0], "lon": [0]}),
                lat="lat",
                lon="lon",
                zoom=1,
            )
            blank.update_traces(marker={"opacity": 0})
            blank.update_layout(
                mapbox_style="open-street-map",
                margin=dict(l=0, r=0, t=0, b=0),
            )
            return blank

        # Filter by time range if possible
        if time_range and "unixtime" in df.columns:
            start,end = time_range
            timerange_mask = (df["unixtime"] >= start) & (df["unixtime"] <= end)
            df = df[timerange_mask]

        if df.empty:
            blank = px.scatter_mapbox(
                pd.DataFrame({"lat": [0], "lon": [0]}),
                lat="lat",
                lon="lon",
                zoom=1,
            )
            blank.update_traces(marker={"opacity": 0})
            blank.update_layout(
                mapbox_style="open-street-map",
                margin=dict(l=0, r=0, t=0, b=0),
            )
            return blank

        fig = px.scatter_mapbox(
            df,
            lat="lat",
            lon="lon",
            hover_data=[c for c in df.columns if c not in {"lat", "lon"}],
            zoom=4,
        )

        # Apply color choice as marker color
        color_choice = color_choice or "red"
        fig.update_traces(marker={"color": color_choice})

        fig.update_layout(
            mapbox_style="open-street-map",
            margin=dict(l=0, r=0, t=0, b=0),
        )
        return fig

    # Tab content callback: render Info tab and y-column tabs
    @app.callback(
        Output(TabsIds.CONTENT, "children"),
        Input(TabsIds.TABS, "value"),
        Input(StoreIds.DATA, "data"),
        Input(ControlIds.TIME_RANGE, "value"),
    )
    def render_tab(active_tab, store_data, time_range):
        df = _df_from_store(store_data)

        # Info tab
        if active_tab == TabsIds.INFO_TAB_VALUE:
            if df.empty:
                return "No data loaded yet."
            n_points = len(df)
            sources = sorted(df["source"].unique()) if "source" in df.columns else []
            return html.Div(
                [
                    html.H5("Deployment Information"),
                    html.P(f"Loaded {n_points} data point(s)."),
                    html.P(f"Sources: {', '.join(sources) if sources else 'Unknown'}."),
                ],
                style={
                    "minHeight": "500px",
                    "padding": "10px",
                },
            )

        # Filter by time for plots
        if not df.empty and time_range and "unixtime" in df.columns:
            start, end = time_range
            timerange_mask = (df["unixtime"] >= start) & (df["unixtime"] <= end)
            df = df[timerange_mask]

        if not active_tab or not active_tab.startswith("tab-"):
            return "No plot available."

        y_col = active_tab.replace("tab-", "", 1)
        if df.empty or y_col not in df.columns:
            return f"No data available for {y_col}."

        # Example: time vs selected variable
        if "time" in df.columns:
            x_col = "time"
        else:
            # Fallback to index
            df = df.reset_index().rename(columns={"index": "index"})
            x_col = "index"

        fig = px.line(
            df.sort_values(x_col),
            x=x_col,
            y=y_col,
            color="source" if "source" in df.columns else None,
            markers=True,
            title=f"{y_col} vs {x_col}",
        )

        return dcc.Graph(figure=fig)
