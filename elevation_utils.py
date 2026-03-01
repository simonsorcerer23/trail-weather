"""
Trail Weather App – Elevation Utilities
Provides elevation profiles, thru-hike planning with Naismith's Rule,
and elevation-adjusted daily pace calculations.
"""

import os
import pandas as pd
import numpy as np
import streamlit as st
from datetime import timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


# ─── Elevation Profile Loading ──────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=None)
def load_elevation_profile(trail_key: str) -> pd.DataFrame | None:
    """Load pre-computed elevation profile for a trail.
    Returns DataFrame with: distance_miles, latitude, longitude, elevation_m
    """
    path = os.path.join(DATA_DIR, f"{trail_key}_elevation.csv")
    if not os.path.isfile(path):
        return None
    return pd.read_csv(path)


# ─── Elevation Stats Between Mile Markers ───────────────────────────

@st.cache_data(show_spinner=False, ttl=None)
def get_segment_elevation_stats(trail_key: str, direction: str) -> pd.DataFrame | None:
    """Calculate elevation gain/loss between consecutive mile markers.

    Uses the fine-grained elevation profile to sum up/down between MM positions.
    Returns DataFrame with columns:
      start_mm, end_mm, distance_mi, gain_m, loss_m, gain_ft, loss_ft
    """
    elev_profile = load_elevation_profile(trail_key)
    if elev_profile is None:
        return None

    mm_file = os.path.join(DATA_DIR, f"{trail_key}_MM_points_list_{direction}.csv")
    if not os.path.isfile(mm_file):
        return None
    mm_df = pd.read_csv(mm_file)

    if "elevation_m" not in mm_df.columns:
        return None

    # Use the fine-grained elevation profile to compute cumulative gain/loss
    # between mile markers by mapping MM positions to profile distance
    profile_dist = elev_profile["distance_miles"].values
    profile_elev = elev_profile["elevation_m"].values
    max_profile_dist = profile_dist[-1]

    mms = mm_df["mile_marker"].values
    mm_elevs = mm_df["elevation_m"].values

    # For each pair of consecutive MMs, sum the ups and downs from the profile
    segments = []
    for i in range(len(mms) - 1):
        start_mm = mms[i]
        end_mm = mms[i + 1]
        dist = end_mm - start_mm

        # Map MM positions to approximate profile distance
        # MM 0 → profile dist 0, MM max → profile dist max
        total_trail_miles = mms[-1]
        frac_start = start_mm / total_trail_miles
        frac_end = end_mm / total_trail_miles
        d_start = frac_start * max_profile_dist
        d_end = frac_end * max_profile_dist

        # Get profile points in this range
        mask = (profile_dist >= d_start) & (profile_dist <= d_end)
        seg_elevs = profile_elev[mask]

        if len(seg_elevs) < 2:
            # Fallback to MM-level elevation
            gain = max(0, mm_elevs[i + 1] - mm_elevs[i])
            loss = max(0, mm_elevs[i] - mm_elevs[i + 1])
        else:
            diffs = np.diff(seg_elevs)
            gain = float(np.sum(diffs[diffs > 0]))
            loss = float(np.abs(np.sum(diffs[diffs < 0])))

        segments.append({
            "start_mm": start_mm,
            "end_mm": end_mm,
            "distance_mi": dist,
            "gain_m": round(gain),
            "loss_m": round(loss),
            "gain_ft": round(gain * 3.281),
            "loss_ft": round(loss * 3.281),
            "start_elev_m": mm_elevs[i],
            "end_elev_m": mm_elevs[i + 1],
        })

    return pd.DataFrame(segments)


# ─── Thru-Hike Planner ──────────────────────────────────────────────

HIKING_HOURS_PER_DAY = 8


def plan_thru_hike(
    mm_df: pd.DataFrame,
    segment_stats: pd.DataFrame | None,
    start_date,
    daily_pace: float,
    adjust_for_elevation: bool = True,
    hiking_hours: float = HIKING_HOURS_PER_DAY,
    waypoint_interval: float = 5.0,
) -> list[dict]:
    """Plan a thru-hike day by day, optionally adjusting for elevation.

    Creates fine-grained waypoints (every `waypoint_interval` miles) between
    mile markers to allow realistic daily planning. Uses Naismith's Rule:
    base walking time + 1h per 600m ascent + 1h per 800m descent.

    Args:
        mm_df: Mile marker DataFrame (must have mile_marker, latitude, longitude, elevation_m)
        segment_stats: Elevation stats between MMs (from get_segment_elevation_stats)
        start_date: Hike start date
        daily_pace: Target miles per day (flat terrain)
        adjust_for_elevation: Whether to apply Naismith's Rule
        hiking_hours: Available hiking hours per day
        waypoint_interval: Miles between sub-waypoints for planning

    Returns:
        List of day plans with keys:
          day, date, start_mm, end_mm, distance_mi, gain_m, loss_m,
          gain_ft, loss_ft, camp_lat, camp_lon, camp_elev_m
    """
    mms = mm_df["mile_marker"].values
    lats = mm_df["latitude"].values
    lons = mm_df["longitude"].values
    elevs = mm_df["elevation_m"].values if "elevation_m" in mm_df.columns else np.zeros(len(mms))

    flat_speed = daily_pace / hiking_hours  # mph on flat

    # Build fine-grained waypoints between mile markers
    wp_miles = []
    wp_lats = []
    wp_lons = []
    wp_elevs = []

    for i in range(len(mms) - 1):
        seg_start = mms[i]
        seg_end = mms[i + 1]
        seg_dist = seg_end - seg_start

        # Number of sub-segments
        n_sub = max(1, int(np.ceil(seg_dist / waypoint_interval)))

        # Elevation gain/loss from segment stats (fine-grained)
        if segment_stats is not None and i < len(segment_stats):
            total_gain = segment_stats.iloc[i]["gain_m"]
            total_loss = segment_stats.iloc[i]["loss_m"]
        else:
            total_gain = max(0, elevs[i + 1] - elevs[i])
            total_loss = max(0, elevs[i] - elevs[i + 1])

        for j in range(n_sub):
            frac_start = j / n_sub
            frac_end = (j + 1) / n_sub

            sub_mile_start = seg_start + frac_start * seg_dist
            sub_mile_end = seg_start + frac_end * seg_dist
            sub_dist = sub_mile_end - sub_mile_start

            # Interpolated position
            lat = lats[i] + frac_end * (lats[i + 1] - lats[i])
            lon = lons[i] + frac_end * (lons[i + 1] - lons[i])
            elev = elevs[i] + frac_end * (elevs[i + 1] - elevs[i])

            # Proportional gain/loss for this sub-segment
            sub_gain = total_gain / n_sub
            sub_loss = total_loss / n_sub

            wp_miles.append(sub_mile_end)
            wp_lats.append(lat)
            wp_lons.append(lon)
            wp_elevs.append(elev)

    # Insert start point
    wp_miles.insert(0, mms[0])
    wp_lats.insert(0, lats[0])
    wp_lons.insert(0, lons[0])
    wp_elevs.insert(0, elevs[0])

    wp_miles = np.array(wp_miles)
    wp_lats = np.array(wp_lats)
    wp_lons = np.array(wp_lons)
    wp_elevs = np.array(wp_elevs)

    # Pre-compute sub-segment distances and elevation changes
    sub_dists = np.diff(wp_miles)
    sub_gains = np.array([0.0] * len(sub_dists))
    sub_losses = np.array([0.0] * len(sub_dists))

    # Distribute segment gains/losses across sub-segments
    seg_idx = 0
    for i in range(len(sub_dists)):
        wp_mid = (wp_miles[i] + wp_miles[i + 1]) / 2
        # Find which MM segment this sub-segment belongs to
        while seg_idx < len(mms) - 2 and wp_mid > mms[seg_idx + 1]:
            seg_idx += 1

        if segment_stats is not None and seg_idx < len(segment_stats):
            seg_dist = mms[seg_idx + 1] - mms[seg_idx]
            if seg_dist > 0:
                frac = sub_dists[i] / seg_dist
                sub_gains[i] = segment_stats.iloc[seg_idx]["gain_m"] * frac
                sub_losses[i] = segment_stats.iloc[seg_idx]["loss_m"] * frac
        else:
            elev_diff = wp_elevs[i + 1] - wp_elevs[i]
            sub_gains[i] = max(0, elev_diff)
            sub_losses[i] = max(0, -elev_diff)

    # Plan days
    days = []
    current_day = 1
    current_date = start_date
    current_idx = 0  # index into sub-segments

    while current_idx < len(sub_dists):
        day_start_idx = current_idx
        day_start_mile = wp_miles[current_idx]
        hours_used = 0.0
        day_gain = 0.0
        day_loss = 0.0

        while current_idx < len(sub_dists):
            dist = sub_dists[current_idx]
            gain = sub_gains[current_idx]
            loss = sub_losses[current_idx]

            horizontal_time = dist / flat_speed

            if adjust_for_elevation:
                ascent_time = gain / 600.0
                descent_time = loss / 800.0
                segment_time = horizontal_time + ascent_time + descent_time
            else:
                segment_time = horizontal_time

            if hours_used + segment_time > hiking_hours and current_idx > day_start_idx:
                break

            hours_used += segment_time
            day_gain += gain
            day_loss += loss
            current_idx += 1

        # Force at least one sub-segment per day
        if current_idx == day_start_idx:
            day_gain += sub_gains[current_idx]
            day_loss += sub_losses[current_idx]
            current_idx += 1

        end_mile = wp_miles[current_idx]
        days.append({
            "day": current_day,
            "date": current_date.strftime("%b %d"),
            "start_mm": round(day_start_mile, 1),
            "end_mm": round(end_mile, 1),
            "distance_mi": round(end_mile - day_start_mile, 1),
            "gain_m": round(day_gain),
            "loss_m": round(day_loss),
            "gain_ft": round(day_gain * 3.281),
            "loss_ft": round(day_loss * 3.281),
            "camp_lat": wp_lats[current_idx],
            "camp_lon": wp_lons[current_idx],
            "camp_elev_m": round(wp_elevs[current_idx]),
            "camp_elev_ft": round(wp_elevs[current_idx] * 3.281),
        })

        current_day += 1
        current_date += timedelta(days=1)

    return days


def get_thru_hike_summary(days: list[dict]) -> dict:
    """Summarize a thru-hike plan."""
    if not days:
        return {}
    total_distance = sum(d["distance_mi"] for d in days)
    total_gain = sum(d["gain_m"] for d in days)
    total_loss = sum(d["loss_m"] for d in days)
    avg_daily = total_distance / len(days) if days else 0

    return {
        "total_days": len(days),
        "total_distance_mi": round(total_distance, 1),
        "total_gain_m": round(total_gain),
        "total_gain_ft": round(total_gain * 3.281),
        "total_loss_m": round(total_loss),
        "total_loss_ft": round(total_loss * 3.281),
        "avg_daily_mi": round(avg_daily, 1),
        "start_date": days[0]["date"],
        "end_date": days[-1]["date"],
        "highest_camp_m": max(d["camp_elev_m"] for d in days),
        "highest_camp_ft": max(d["camp_elev_ft"] for d in days),
    }
