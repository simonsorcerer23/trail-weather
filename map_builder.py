"""
Trail Weather App – Map Builder Module
Constructs the Folium map with trail routes, mile markers, POIs, and weather heatmap.
"""

import os
import folium
import pandas as pd
import numpy as np


def find_nearest_index(lat, lon, df):
    """Find the index of the nearest point in a DataFrame."""
    distances = np.sqrt(
        (df["latitude"] - lat) ** 2 + (df["longitude"] - lon) ** 2
    )
    return distances.idxmin()


def _temp_to_color(temp, temp_min, temp_max):
    """Map a temperature value to a color from blue (cold) to red (hot)."""
    if temp_max == temp_min:
        return "#fbbf24"
    ratio = max(0, min(1, (temp - temp_min) / (temp_max - temp_min)))
    # Blue → Cyan → Green → Yellow → Orange → Red
    if ratio < 0.2:
        r, g, b = 59, 130, 246   # blue
    elif ratio < 0.4:
        r, g, b = 34, 197, 94    # green
    elif ratio < 0.6:
        r, g, b = 250, 204, 21   # yellow
    elif ratio < 0.8:
        r, g, b = 249, 115, 22   # orange
    else:
        r, g, b = 239, 68, 68    # red
    return f"#{r:02x}{g:02x}{b:02x}"


def _rain_to_color(rain):
    """Map rain amount to a blue intensity."""
    if rain <= 0:
        return None
    if rain < 5:
        return "#93c5fd"
    if rain < 15:
        return "#3b82f6"
    return "#1d4ed8"


def build_trail_map(
    route_df,
    mm_range_coords=None,
    mm_df=None,
    show_mm=False,
    direction="NOBO",
    poi_df=None,
    show_poi=False,
    emblem_image=None,
    weather_df=None,
    heatmap_mode=None,
    temp_symbol="°C",
    route_coords=None,
):
    """Build a Folium map with the trail and optional overlays."""

    mean_lat = route_df["latitude"].mean()
    mean_lon = route_df["longitude"].mean()

    if mm_range_coords:
        m = folium.Map(zoom_start=9, tiles="OpenStreetMap")
    else:
        m = folium.Map(location=[mean_lat, mean_lon], zoom_start=7, tiles="OpenStreetMap")

    # Full trail route (grey) — use pre-simplified coords if provided
    if route_coords is None:
        # Fallback: simplify on the fly
        step = max(1, len(route_df) // 800)
        subset = route_df.iloc[::step]
        route_coords = list(zip(subset["latitude"], subset["longitude"]))
    folium.PolyLine(route_coords, weight=4, color="grey", opacity=0.6).add_to(m)

    # Highlighted range (bold blue)
    if mm_range_coords:
        folium.PolyLine(
            mm_range_coords, weight=10, color="#2563eb", opacity=0.85
        ).add_to(m)
        m.fit_bounds(mm_range_coords)

    # ─── Weather Heatmap Overlay ──────────────────────────────────
    if weather_df is not None and heatmap_mode and heatmap_mode != "Off":
        wx_group = folium.FeatureGroup(name=f"Weather: {heatmap_mode}")

        if heatmap_mode == "🌡️ Temperature":
            temp_col = f"Temp Max ({temp_symbol})"
            if temp_col in weather_df.columns:
                # Average across dates per mile marker
                avg_df = weather_df.groupby(["Mile Marker", "Latitude", "Longitude"]).agg(
                    {temp_col: "mean"}
                ).reset_index()
                t_min = avg_df[temp_col].min()
                t_max = avg_df[temp_col].max()

                for _, row in avg_df.iterrows():
                    temp_val = float(row[temp_col])
                    color = _temp_to_color(temp_val, t_min, t_max)
                    folium.CircleMarker(
                        location=[row["Latitude"], row["Longitude"]],
                        radius=10,
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.8,
                        tooltip=f"Mile {row['Mile Marker']}: {temp_val:.0f}{temp_symbol}",
                    ).add_to(wx_group)

        elif heatmap_mode == "🌧️ Precipitation":
            avg_df = weather_df.groupby(["Mile Marker", "Latitude", "Longitude"]).agg(
                {"Rain (mm)": "sum", "Snow (cm)": "sum"}
            ).reset_index()

            for _, row in avg_df.iterrows():
                rain = float(row["Rain (mm)"])
                snow = float(row["Snow (cm)"])
                total = rain + snow
                if total <= 0:
                    continue
                color = _rain_to_color(rain) or "#93c5fd"
                folium.CircleMarker(
                    location=[row["Latitude"], row["Longitude"]],
                    radius=max(5, min(18, total / 2)),
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.7,
                    tooltip=f"Mile {row['Mile Marker']}: 🌧️{rain:.0f}mm ❄️{snow:.0f}cm",
                ).add_to(wx_group)

        elif heatmap_mode == "💨 Wind":
            wind_col = "💨 Gusts (km/h)"
            if wind_col in weather_df.columns:
                avg_df = weather_df.groupby(["Mile Marker", "Latitude", "Longitude"]).agg(
                    {wind_col: "max"}
                ).reset_index()

                for _, row in avg_df.iterrows():
                    gust = float(row[wind_col])
                    if gust < 20:
                        continue
                    # Color: green < 40, yellow < 60, orange < 80, red >= 80
                    if gust < 40:
                        color = "#22c55e"
                    elif gust < 60:
                        color = "#facc15"
                    elif gust < 80:
                        color = "#f97316"
                    else:
                        color = "#ef4444"
                    folium.CircleMarker(
                        location=[row["Latitude"], row["Longitude"]],
                        radius=max(5, min(15, gust / 8)),
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.7,
                        tooltip=f"Mile {row['Mile Marker']}: 💨 {gust:.0f} km/h gusts",
                    ).add_to(wx_group)

        wx_group.add_to(m)

    # Mile Markers
    if show_mm and mm_df is not None:
        mm_group = folium.FeatureGroup(name="Mile Markers")
        for _, row in mm_df.iterrows():
            folium.CircleMarker(
                location=[row["latitude"], row["longitude"]],
                radius=5,
                color="#ef4444",
                fill=True,
                fill_color="#ef4444",
                fill_opacity=0.8,
                tooltip=f"{direction} Mile {row['mile_marker']}",
            ).add_to(mm_group)
        mm_group.add_to(m)

    # POIs
    if show_poi and poi_df is not None:
        poi_group = folium.FeatureGroup(name="Points of Interest")
        for _, row in poi_df.iterrows():
            if emblem_image and os.path.isfile(emblem_image):
                icon = folium.CustomIcon(
                    emblem_image, icon_size=(22, 22),
                    icon_anchor=(1, 22), popup_anchor=(-3, -76),
                )
            else:
                icon = folium.Icon(color="green", icon="info-sign")

            folium.Marker(
                location=[row["latitude"], row["longitude"]],
                popup=folium.Popup(f"<b>{row['name']}</b>", max_width=300),
                tooltip=row["name"],
                icon=icon,
            ).add_to(poi_group)
        poi_group.add_to(m)

    folium.LayerControl().add_to(m)
    return m


def calculate_range_coords(route_df, mm_df, start_mm, end_mm):
    """Calculate the route section between two mile markers."""
    start_row = mm_df[mm_df["mile_marker"] == start_mm].iloc[0]
    end_row = mm_df[mm_df["mile_marker"] == end_mm].iloc[0]

    start_idx = find_nearest_index(start_row["latitude"], start_row["longitude"], route_df)
    end_idx = find_nearest_index(end_row["latitude"], end_row["longitude"], route_df)

    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx

    selected = route_df.iloc[start_idx : end_idx + 1]
    return list(zip(selected["latitude"], selected["longitude"]))
