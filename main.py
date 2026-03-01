#!/usr/bin/env python3
"""
🥾 Trail History Weather — Deluxe Edition
Interactive weather history viewer for long-distance hiking trails.

Features:
  - Multi-trail support with auto-discovery
  - Weather heatmap overlay on map (temp/rain/wind)
  - Elevation profile from GPX data
  - Wind speed + gusts charts
  - Daylight / sunrise-sunset hours
  - Danger alerts (freezing, extreme heat, storms, high wind)
  - GPX file upload for custom trails
  - Year-over-year comparison
  - Share via URL parameters
  - CSV export

Original concept by Shepherd 🇩🇪 🍺 🥨
Pimped with ❤️ by GitHub Copilot
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import timedelta, date as Date
from streamlit_folium import st_folium

from config import get_available_trails, get_trail_files
from weather_api import fetch_weather, process_weather_responses, detect_danger_alerts
from map_builder import build_trail_map, calculate_range_coords
from charts import (
    build_temperature_chart, build_precipitation_chart, build_wind_chart,
    build_sunrise_sunset_chart, build_weather_summary_chart, build_elevation_profile,
    build_year_comparison_chart,
)
from gpx_upload import process_gpx_upload
from trail_db import save_trail, list_saved_trails, load_trail, delete_trail
from elevation_utils import (
    load_elevation_profile, get_segment_elevation_stats,
    plan_thru_hike, get_thru_hike_summary,
)


# ─── Page Config ───────────────────────────────────────────────────
st.set_page_config(
    page_title="🥾 Trail History Weather",
    page_icon="🥾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS (Dark Mode) ───────────────────────────────────────
st.markdown("""
<style>
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a2332 0%, #0d1117 100%);
    }
    .main .block-container {
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
    }
    [data-testid="stMetric"] {
        background: #1a2332;
        border-radius: 10px;
        padding: 14px;
        border: 1px solid #2d3748;
    }
    .stDataFrame { border-radius: 8px; overflow: hidden; }
    .shepherd-footer {
        text-align: center; padding: 1.5rem 0 0.5rem 0;
        color: #64748b; font-size: 0.85rem;
    }
    .shepherd-footer a { color: #3b82f6 !important; }
    .danger-box {
        background: linear-gradient(135deg, #451a03 0%, #7c2d12 100%);
        border: 1px solid #ea580c;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 0.5rem;
    }
    .danger-box-warn {
        background: linear-gradient(135deg, #422006 0%, #713f12 100%);
        border: 1px solid #ca8a04;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


# ─── Cached Data Loaders ──────────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=3600)
def load_csv(path):
    """Load and cache a CSV file."""
    return pd.read_csv(path)


@st.cache_data(show_spinner=False)
def load_emblem_b64(path):
    """Load and base64-encode an emblem image."""
    import base64
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


@st.cache_data(show_spinner=False)
def simplify_route(route_df, max_points=800):
    """Decimate route to max_points for faster map rendering."""
    if len(route_df) <= max_points:
        return list(zip(route_df["latitude"], route_df["longitude"]))
    step = max(1, len(route_df) // max_points)
    simplified = route_df.iloc[::step]
    return list(zip(simplified["latitude"], simplified["longitude"]))


@st.cache_data(show_spinner=False)
def cached_danger_alerts(_df_hash, df, temp_symbol):
    """Cached version of danger alert detection."""
    return detect_danger_alerts(df, temp_symbol)


def init_session_state():
    """Initialize all session state variables."""
    defaults = {
        "start_date": Date.today() - timedelta(days=30),
        "end_date": Date.today() - timedelta(days=1),
        "last_start_date": None,
        "mm_weather_df": None,
        "mm_range_coords": None,
        "last_temp_unit": None,
        "last_nobo": None,
        "last_trail": None,
        "uploaded_trail": None,
        "comparison_df": None,
        "thru_hike_days": None,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def apply_url_params(available_trails, mm_options):
    """Apply URL query parameters if present (share link support)."""
    params = st.query_params
    if "trail" in params and params["trail"] in available_trails:
        st.session_state.selected_trail = params["trail"]
    if "start" in params:
        try:
            st.session_state.start_date = Date.fromisoformat(params["start"])
        except ValueError:
            pass
    if "end" in params:
        try:
            st.session_state.end_date = Date.fromisoformat(params["end"])
        except ValueError:
            pass


BASE_URL = "https://trail-weather.familiereis.de/"

def generate_share_url(trail, start_date, end_date, start_mm, end_mm):
    """Generate a shareable URL with current settings."""
    return f"{BASE_URL}?trail={trail}&start={start_date}&end={end_date}&mm_start={start_mm}&mm_end={end_mm}"


def main():
    init_session_state()

    available_trails = get_available_trails()

    # ─── Sidebar ──────────────────────────────────────────────────

    # Trail Selector
    use_upload = False
    trail_options = {k: f"{v['emoji']} {v['name']}" for k, v in available_trails.items()}

    if available_trails:
        selected_trail = st.sidebar.selectbox(
            "🗺️ Select Trail",
            options=list(trail_options.keys()),
            format_func=lambda x: trail_options[x],
            key="selected_trail",
            label_visibility="collapsed",
        )
        trail_meta = available_trails[selected_trail]
        trail_files = get_trail_files(selected_trail)

        # Logo in sidebar (non-clickable)
        emblem_path = trail_files["emblem"]
        has_emblem = os.path.isfile(emblem_path)
        if has_emblem:
            b64 = load_emblem_b64(emblem_path)
            st.sidebar.markdown(
                f'<img src="data:image/png;base64,{b64}" width="160" '
                f'style="pointer-events:none; user-select:none; display:block; margin:0 auto 0.5rem auto;">',
                unsafe_allow_html=True,
            )
        st.sidebar.markdown(f"### {trail_meta['emoji']} {trail_meta['name']}")
    else:
        selected_trail = None
        trail_meta = None
        trail_files = None
        has_emblem = False
        emblem_path = None

    # ─── GPX Upload ───────────────────────────────────────────────
    with st.sidebar.expander("📤 Upload Custom Trail (GPX)", expanded=not bool(available_trails)):
        uploaded_gpx = st.file_uploader(
            "Drop your GPX file here",
            type=["gpx"],
            label_visibility="collapsed",
        )
        upload_name = st.text_input("Trail Name", value="MyTrail", max_chars=20)
        upload_interval = st.number_input("Mile Marker Interval", value=10, min_value=1, max_value=50)

        if uploaded_gpx and st.button("🔄 Process & Save GPX", use_container_width=True):
            with st.spinner("Processing GPX file..."):
                result = process_gpx_upload(uploaded_gpx, upload_name, upload_interval)
                if result:
                    # Save to SQLite
                    trail_id = save_trail(
                        upload_name, upload_interval,
                        result["trackpoints_df"],
                        result["mm_nobo_df"],
                        result["mm_sobo_df"],
                    )
                    st.session_state.uploaded_trail = result
                    st.session_state.mm_weather_df = None
                    st.session_state.mm_range_coords = None
                    st.success(f"✅ {upload_name} saved! "
                              f"{len(result['trackpoints_df'])} trackpoints, "
                              f"{len(result['mm_nobo_df'])} mile markers")
                else:
                    st.error("❌ No track data found in GPX file")

    # ─── Saved Custom Trails ──────────────────────────────────────
    saved_trails = list_saved_trails()
    with st.sidebar.expander(f"💾 Saved Trails ({len(saved_trails)})", expanded=len(saved_trails) > 0):
        if saved_trails:
            for t in saved_trails:
                col_load, col_del = st.columns([3, 1])
                with col_load:
                    if st.button(
                        f"📂 {t['name']} ({t['total_miles']:.0f} mi)",
                        key=f"load_{t['id']}",
                        use_container_width=True,
                    ):
                        loaded = load_trail(t["id"])
                        if loaded:
                            st.session_state.uploaded_trail = loaded
                            st.session_state.mm_weather_df = None
                            st.session_state.mm_range_coords = None
                            st.rerun()
                with col_del:
                    if st.button("🗑️", key=f"del_{t['id']}"):
                        delete_trail(t["id"])
                        if (st.session_state.uploaded_trail
                                and st.session_state.uploaded_trail.get("trail_name") == t["name"]):
                            st.session_state.uploaded_trail = None
                            st.session_state.mm_weather_df = None
                            st.session_state.mm_range_coords = None
                        st.rerun()
        else:
            st.caption("Noch keine Trails gespeichert.\nLade eine GPX-Datei hoch ☝️")

    # Determine data source: uploaded trail or built-in
    if st.session_state.uploaded_trail:
        use_upload = True
        upl = st.session_state.uploaded_trail
        trail_name_display = f"📤 {upl['trail_name']}"
        timezone = "UTC"
        if st.sidebar.button("❌ Clear Active Upload"):
            st.session_state.uploaded_trail = None
            st.session_state.mm_weather_df = None
            st.session_state.mm_range_coords = None
            st.rerun()
    elif trail_meta:
        trail_name_display = f"{trail_meta['emoji']} {trail_meta['name']}"
        timezone = trail_meta["timezone"]
    else:
        st.error("❌ No trail data available. Upload a GPX file or add trail CSVs.")
        return

    # Reset weather data when trail changes
    if not use_upload and selected_trail != st.session_state.last_trail:
        st.session_state.mm_weather_df = None
        st.session_state.mm_range_coords = None
        st.session_state.comparison_df = None
        st.session_state.thru_hike_days = None
        st.session_state.reset_mm_range = True
        st.session_state.last_trail = selected_trail

    st.sidebar.markdown("---")

    # ─── Settings ─────────────────────────────────────────────────
    st.sidebar.markdown("### ⚙️ Settings")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        temp_unit_input = st.radio("🌡️ Temp", ["°C", "°F"], horizontal=True)
        temperature_unit = "celsius" if temp_unit_input == "°C" else "fahrenheit"
        temp_symbol = "°C" if temperature_unit == "celsius" else "°F"
    with col2:
        direction = st.radio("🧭 Direction", ["NOBO", "SOBO"], horizontal=True)
        nobo = direction == "NOBO"

    col3, col4 = st.sidebar.columns(2)
    with col3:
        show_mm = st.checkbox("📍 Mile Markers", value=False)
    with col4:
        if not use_upload and trail_files:
            has_poi = os.path.isfile(trail_files["poi"])
        else:
            has_poi = False
        show_poi = st.checkbox("🏕️ POIs", value=False, disabled=not has_poi)

    # Heatmap mode
    heatmap_mode = st.sidebar.selectbox(
        "🗺️ Map Overlay",
        ["Off", "🌡️ Temperature", "🌧️ Precipitation", "💨 Wind"],
        index=0,
    )

    # Reset weather if settings change
    if temperature_unit != st.session_state.last_temp_unit:
        st.session_state.mm_weather_df = None
        st.session_state.comparison_df = None
        st.session_state.last_temp_unit = temperature_unit
    if nobo != st.session_state.last_nobo:
        st.session_state.mm_weather_df = None
        st.session_state.comparison_df = None
        st.session_state.thru_hike_days = None
        st.session_state.last_nobo = nobo

    st.sidebar.markdown("---")

    # ─── Load Trail Data (cached) ────────────────────────────────
    if use_upload:
        upl = st.session_state.uploaded_trail
        route_df = upl["trackpoints_df"]
        mm_df = upl["mm_nobo_df"] if nobo else upl["mm_sobo_df"]
    else:
        route_df = load_csv(trail_files["trackpoints"])
        mm_file = trail_files["mm_nobo"] if nobo else trail_files["mm_sobo"]
        mm_df = load_csv(mm_file)

    mm_options = mm_df["mile_marker"].tolist()

    # Apply URL params
    if not use_upload and available_trails:
        apply_url_params(available_trails, mm_options)

    # ─── Mile Marker Range ────────────────────────────────────────
    st.sidebar.markdown("### 📏 Mile Marker Range")

    # Auto-reset MM range when trail changes
    if st.session_state.get("reset_mm_range", False):
        # Clear stale selectbox keys so they default to first/last
        if "start_mm" in st.session_state:
            del st.session_state["start_mm"]
        if "end_mm" in st.session_state:
            del st.session_state["end_mm"]
        st.session_state.reset_mm_range = False

    start_mm = st.sidebar.selectbox("Start MM", mm_options, index=0, key="start_mm")
    end_mm = st.sidebar.selectbox("End MM", mm_options, index=len(mm_options) - 1, key="end_mm")

    # Force End MM to max if it's not a valid option for this trail
    if end_mm not in mm_options:
        end_mm = mm_options[-1]
        st.session_state.end_mm = end_mm
    if start_mm > end_mm:
        start_mm, end_mm = end_mm, start_mm

    st.sidebar.caption(f"📐 Range: **{start_mm}** → **{end_mm}** ({end_mm - start_mm:.0f} mi)")

    selected_points = mm_df[
        (mm_df["mile_marker"] >= start_mm) & (mm_df["mile_marker"] <= end_mm)
    ]

    # ─── 🥾 Thru-Hike Planner ────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🥾 Thru-Hike Planner")
    thru_col1, thru_col2 = st.sidebar.columns([2, 1])
    with thru_col1:
        thru_pace = st.number_input(
            "📏 mi/day (flat)",
            min_value=5.0, max_value=40.0, value=20.0, step=1.0,
            help="Target miles per day on flat terrain. Elevation gain reduces effective pace.",
        )
    with thru_col2:
        thru_adjust_elev = st.checkbox("🏔️ Elev.", value=True,
                                        help="Naismith's Rule: +1h/600m ascent, +1h/800m descent")

    # Compute thru-hike plan
    if not use_upload and selected_trail:
        seg_stats = get_segment_elevation_stats(selected_trail, direction)
    else:
        seg_stats = None

    thru_mm_df = mm_df[
        (mm_df["mile_marker"] >= start_mm) & (mm_df["mile_marker"] <= end_mm)
    ].reset_index(drop=True)

    hike_start = st.session_state.start_date
    hike_duration_days = None

    if len(thru_mm_df) >= 2:
        thru_days = plan_thru_hike(
            thru_mm_df, seg_stats, hike_start,
            thru_pace, thru_adjust_elev,
        )
        summary = get_thru_hike_summary(thru_days)
        st.session_state.thru_hike_days = thru_days

        if summary:
            hike_duration_days = summary["total_days"]
            end_date_hike = hike_start + timedelta(days=hike_duration_days - 1)
            target_end = min(end_date_hike, Date.today() - timedelta(days=1))

            # Auto-set end date to match hike duration
            st.session_state.end_date = target_end

            st.sidebar.markdown(
                f"📅 **{summary['total_days']} Tage** "
                f"({summary['avg_daily_mi']} mi/Tag)  \n"
                f"🏁 **{hike_start.strftime('%d.%m.%Y')} → "
                f"{end_date_hike.strftime('%d.%m.%Y')}**  \n"
                f"⬆️ {summary['total_gain_ft']:,} ft &nbsp; "
                f"⬇️ {summary['total_loss_ft']:,} ft &nbsp; "
                f"🏔️ {summary['highest_camp_ft']:,} ft"
            )
    else:
        st.session_state.thru_hike_days = None

    # ─── 📅 Date Range ────────────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📅 Date Range")
    start_date = st.sidebar.date_input(
        "Start Date", key="start_date",
        max_value=Date.today() - timedelta(days=1),
    )
    end_date = st.sidebar.date_input(
        "End Date", key="end_date",
        max_value=Date.today(),
    )
    if hike_duration_days:
        st.sidebar.caption(f"📅 Zeitraum: **{(end_date - start_date).days + 1}** Tage "
                          f"(Hike: {hike_duration_days} Tage)")

    st.sidebar.markdown("---")

    # ─── Load Weather ─────────────────────────────────────────────
    if st.sidebar.button("⚡ Load Weather", type="primary", use_container_width=True):
        with st.spinner(f"🌤️ Loading weather for {trail_name_display}..."):
            latitudes = selected_points["latitude"].tolist()
            longitudes = selected_points["longitude"].tolist()
            mile_markers = selected_points["mile_marker"].tolist()

            responses = fetch_weather(
                latitudes, longitudes, start_date, end_date,
                temperature_unit, timezone,
            )
            st.session_state.mm_weather_df = process_weather_responses(
                responses, mile_markers, latitudes, longitudes, temp_symbol, timezone
            )
            st.session_state.mm_range_coords = calculate_range_coords(
                route_df, mm_df, start_mm, end_mm
            )
            st.session_state.comparison_df = None

    # ─── Year Comparison Button ───────────────────────────────────
    if st.session_state.mm_weather_df is not None:
        if st.sidebar.button("📅 Compare with Previous Year", use_container_width=True):
            prev_start = start_date.replace(year=start_date.year - 1)
            prev_end = end_date.replace(year=end_date.year - 1)
            with st.spinner("📅 Loading previous year data..."):
                latitudes = selected_points["latitude"].tolist()
                longitudes = selected_points["longitude"].tolist()
                mile_markers = selected_points["mile_marker"].tolist()

                prev_responses = fetch_weather(
                    latitudes, longitudes, prev_start, prev_end,
                    temperature_unit, timezone,
                )
                st.session_state.comparison_df = process_weather_responses(
                    prev_responses, mile_markers, latitudes, longitudes, temp_symbol, timezone
                )

    # Clear Button
    if st.session_state.mm_range_coords is not None:
        if st.sidebar.button("🗑️ Clear Selection", use_container_width=True):
            st.session_state.mm_range_coords = None
            st.session_state.mm_weather_df = None
            st.session_state.comparison_df = None
            st.session_state.thru_hike_days = None
            st.session_state.reset_mm_range = True
            st.rerun()

    # ─── Share Link ───────────────────────────────────────────────
    if not use_upload and st.session_state.mm_weather_df is not None:
        share_url = generate_share_url(selected_trail, start_date, end_date, start_mm, end_mm)
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 🔗 Share")
        st.sidebar.code(share_url, language=None)

    st.sidebar.markdown("---")
    st.sidebar.caption("Proudly presented by Shepherd 🇩🇪 🍺 🥨")
    st.sidebar.caption("Pimped by GitHub Copilot 🤖✨")

    # ═══════════════════════════════════════════════════════════════
    # MAIN CONTENT
    # ═══════════════════════════════════════════════════════════════

    # ─── Map ──────────────────────────────────────────────────────
    poi_df = None
    if not use_upload and has_poi and show_poi:
        poi_df = load_csv(trail_files["poi"])

    route_coords = simplify_route(route_df)

    m = build_trail_map(
        route_df=route_df,
        mm_range_coords=st.session_state.mm_range_coords,
        mm_df=mm_df,
        show_mm=show_mm,
        direction=direction,
        poi_df=poi_df,
        show_poi=show_poi,
        emblem_image=emblem_path if has_emblem else None,
        weather_df=st.session_state.mm_weather_df,
        heatmap_mode=heatmap_mode,
        temp_symbol=temp_symbol,
        route_coords=route_coords,
    )
    st_folium(m, use_container_width=True, height=650, returned_objects=[])

    # ─── Elevation Profile ────────────────────────────────────────
    if not use_upload and selected_trail:
        elev_df = load_elevation_profile(selected_trail)
        if elev_df is not None:
            thru_days = st.session_state.get("thru_hike_days", None)
            elev_chart = build_elevation_profile(
                elev_df, mm_df, start_mm, end_mm,
                thru_hike_days=thru_days,
            )
            if elev_chart:
                st.plotly_chart(elev_chart, use_container_width=True)

    # ─── Thru-Hike Itinerary Table ────────────────────────────────
    thru_days = st.session_state.get("thru_hike_days", None)
    if thru_days and len(thru_days) > 1:
        with st.expander(f"🥾 Thru-Hike Itinerary ({len(thru_days)} days)", expanded=False):
            itinerary_df = pd.DataFrame(thru_days)
            display_cols = {
                "day": "Day",
                "date": "Date",
                "start_mm": "Start MM",
                "end_mm": "End MM",
                "distance_mi": "Miles",
                "gain_ft": "↑ Gain (ft)",
                "loss_ft": "↓ Loss (ft)",
                "camp_elev_ft": "Camp Elev (ft)",
            }
            show_df = itinerary_df[[c for c in display_cols.keys() if c in itinerary_df.columns]]
            show_df = show_df.rename(columns=display_cols)
            st.dataframe(show_df, use_container_width=True, hide_index=True)

    # ─── Weather Data ─────────────────────────────────────────────
    if st.session_state.mm_weather_df is not None:
        df = st.session_state.mm_weather_df
        temp_max_col = f"Temp Max ({temp_symbol})"
        temp_min_col = f"Temp Min ({temp_symbol})"

        # ─── Danger Alerts (cached) ──────────────────────────────
        df_hash = hash(df.to_json())
        alerts = cached_danger_alerts(df_hash, df, temp_symbol)
        if alerts:
            st.markdown("### ⚠️ Weather Alerts")
            errors = [a for a in alerts if a["severity"] == "error"]
            warnings = [a for a in alerts if a["severity"] == "warning"]

            if errors:
                with st.expander(f"🚨 {len(errors)} Danger Alert(s)", expanded=True):
                    for a in errors[:20]:
                        st.error(f"**{a['type']}** — {a['message']}")
            if warnings:
                with st.expander(f"⚠️ {len(warnings)} Warning(s)", expanded=False):
                    for a in warnings[:20]:
                        st.warning(f"**{a['type']}** — {a['message']}")

        st.markdown("---")

        # ─── Summary Metrics ─────────────────────────────────────
        st.markdown("### 📊 Weather Summary")
        m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
        with m1:
            st.metric("🌡️ Max Temp", f"{df[temp_max_col].max()}{temp_symbol}")
        with m2:
            st.metric("🧊 Min Temp", f"{df[temp_min_col].min()}{temp_symbol}")
        with m3:
            st.metric("🌧️ Total Rain", f"{df['Rain (mm)'].sum()} mm")
        with m4:
            st.metric("❄️ Total Snow", f"{df['Snow (cm)'].sum()} cm")
        with m5:
            wind_col = "💨 Gusts (km/h)"
            max_gust = df[wind_col].max() if wind_col in df.columns else "N/A"
            st.metric("💨 Max Gust", f"{max_gust} km/h")
        with m6:
            if "🌅 Sunrise" in df.columns and "🌇 Sunset" in df.columns:
                # Show earliest sunrise and latest sunset across all points
                first_row = df.iloc[0]
                last_row = df.iloc[-1]
                st.metric("🌅 Sunrise", f"{first_row['🌅 Sunrise']}–{last_row['🌅 Sunrise']}")
            else:
                st.metric("☀️ Daylight", "N/A")
        with m7:
            st.metric("📍 Mile Markers", f"{df['Mile Marker'].nunique()}")

        # ─── Charts ──────────────────────────────────────────────
        st.markdown("---")
        unique_dates = df["Date"].unique()

        if len(unique_dates) > 1:
            selected_chart_date = st.selectbox(
                "📅 Select date for charts", ["All Days"] + list(unique_dates)
            )
            chart_date = None if selected_chart_date == "All Days" else selected_chart_date
        else:
            chart_date = unique_dates[0]

        # Row 1: Temperature + Precipitation
        c1, c2 = st.columns(2)
        with c1:
            fig = build_temperature_chart(df, temp_symbol, chart_date)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = build_precipitation_chart(df, chart_date)
            if fig:
                st.plotly_chart(fig, use_container_width=True)

        # Row 2: Wind + Sunrise/Sunset
        c3, c4 = st.columns(2)
        with c3:
            fig = build_wind_chart(df, chart_date)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        with c4:
            fig = build_sunrise_sunset_chart(df, chart_date)
            if fig:
                st.plotly_chart(fig, use_container_width=True)

        # Row 3: Weather Distribution + Year Comparison
        c5, c6 = st.columns(2)
        with c5:
            if len(df) >= 5:
                fig = build_weather_summary_chart(df)
                st.plotly_chart(fig, use_container_width=True)

        with c6:
            if st.session_state.comparison_df is not None:
                fig = build_year_comparison_chart(
                    df, st.session_state.comparison_df,
                    temp_symbol,
                    start_date.year, start_date.year - 1,
                )
                if fig:
                    st.plotly_chart(fig, use_container_width=True)

        # ─── Data Tables ─────────────────────────────────────────
        st.markdown("---")
        st.markdown("### 📋 Detailed Weather Data")

        display_cols = [
            "Mile Marker", temp_max_col, temp_min_col,
            "Rain (mm)", "Snow (cm)",
            "💨 Wind Max (km/h)", "💨 Gusts (km/h)",
            "🌅 Sunrise", "🌇 Sunset", "Weather",
        ]
        # Only show columns that exist
        display_cols = [c for c in display_cols if c in df.columns]

        for date in unique_dates:
            with st.expander(f"📅 {date}", expanded=len(unique_dates) == 1):
                daily_df = df[df["Date"] == date].copy()
                st.dataframe(
                    daily_df[display_cols].reset_index(drop=True),
                    use_container_width=True,
                    hide_index=True,
                )

        # ─── CSV Download ────────────────────────────────────────
        st.markdown("---")
        export_cols = [c for c in df.columns if not c.startswith("_")]
        csv = df[export_cols].to_csv(index=False).encode("utf-8")
        trail_key = selected_trail if not use_upload else upload_name
        st.download_button(
            label="📥 Download Weather Data as CSV",
            data=csv,
            file_name=f"{trail_key}_weather_{start_date}_{end_date}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # Footer
    st.markdown(
        '<div class="shepherd-footer">'
        'Made with ❤️ for Thru-Hikers everywhere<br>'
        'Weather data by <a href="https://open-meteo.com/" target="_blank">Open-Meteo</a>'
        '</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
