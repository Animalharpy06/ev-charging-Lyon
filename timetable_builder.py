# -*- coding: utf-8 -*-
"""
Created on Mon Feb 23 11:44:19 2026

@author: Admin
"""

import gzip
import xml.etree.ElementTree as ET
import pandas as pd

# ── Configuration ─────────────────────────────────────────────────────────────
DAY_START = 0
DAY_END   = 86400

IGNORED_ACTIVITY_TYPES = {"car interaction","car_passenger interaction", "bike interaction", "pt interaction"}


# ── Plans parser ──────────────────────────────────────────────────────────────
def parse_plans(plans_path: str) -> pd.DataFrame:
    """
    Parse output_plans.xml.gz and return a DataFrame of real activities
    (home / work / leisure / ...) for each person.

    Returns
    -------
    pd.DataFrame with columns:
        person_id, activity_type, link_id, x, y, start_time_s
    """
    records = []

    with gzip.open(plans_path, "rb") as f:
        tree = ET.parse(f)
    root = tree.getroot()                       # is the population element

    for person in root.iter("person"):
        person_id = person.get("id")

        selected_plan = None
        for plan in person.findall("plan"):                 # Each person can have multiple plans (MATSim keeps rejected plans from previous iterations)
            if plan.get("selected") == "yes":
                selected_plan = plan
                break
        if selected_plan is None:                           # If somehow no selected plan exists, we skip that person entirely.
            continue

        for element in selected_plan:                       # Iterates over all direct children of the plan — these alternate between <activity> and <leg> elements
            if element.tag != "activity":                   # We skip everything that is not and <activity>
                continue
            activity_type = element.get("type", "")
            if activity_type in IGNORED_ACTIVITY_TYPES:     # If it is a MATSim internal interaction activity, skip it
                continue

            link_id    = element.get("link")                # Any of these can be None if the attribute is absent in the XML 
            x          = element.get("x")                   # .get() returns None by default rather than raising an error
            y          = element.get("y")
            start_time = element.get("start_time")          # missing for first activity

            records.append({
                "person_id":     person_id,
                "activity_type": activity_type,
                "link_id":       link_id,
                "x":             float(x) if x is not None else None,
                "y":             float(y) if y is not None else None,
                "start_time_s":  _to_seconds(start_time),   # NaN if missing
            })

    df = pd.DataFrame(records)

    # First activity of day has no start_time → _to_seconds() returned NaN for it and now we assign 0
    df["start_time_s"] = df["start_time_s"].fillna(0.0)

    print(f"  → {df['person_id'].nunique():,} persons parsed from plans")
    print(f"  → Activity types found: {sorted(df['activity_type'].unique())}")

    return df


def _to_seconds(time_str: str) -> float:
    """
    Convert HH:MM:SS to seconds from midnight.
    MATSim allows hours > 24 for post-midnight trips.
    Returns NaN if None or unparseable.
    """
    if time_str is None:
        return float("nan")
    try:
        h, m, s = time_str.strip().split(":")
        return float(int(h) * 3600 + int(m) * 60 + int(s))
    except Exception:
        return float("nan")


# ── Timetable builder ─────────────────────────────────────────────────────────
def build_timetable(trips_df, plans_path=None, nodes=None, links=None):
    """
    Build per-vehicle timetable of driving and parked episodes.

    If plans_path, nodes and links are provided, each parked episode is
    enriched with activity_type and (x, y) coordinates by matching against
    the plans file.

    Parameters
    ----------
    trips_df   : pd.DataFrame — output of events_parser
    plans_path : str or None  — path to output_plans.xml.gz
    nodes      : dict or None — node_id -> Node (from network_parser)
    links      : dict or None — link_id -> Link (from network_parser)

    Returns
    -------
    pd.DataFrame with episodes. Parked episodes include activity_type, x, y
    if plans data was provided.
    """
    records = []

    for vehicle_id, group in trips_df.groupby("vehicle_id"):
        group = group.reset_index(drop=True)

        # Parked episode before the first trip
        first_trip = group.iloc[0]
        if first_trip["t_start"] > DAY_START:
            records.append({
                "vehicle_id":   vehicle_id,
                "episode_type": "parked",
                "t_start":      DAY_START,
                "t_end":        first_trip["t_start"],
                "duration_s":   first_trip["t_start"] - DAY_START,
                "link_id":      first_trip["from_link"],
                "distance_m":   None
            })

        for i, row in group.iterrows():

            # Driving episode
            records.append({
                "vehicle_id":   vehicle_id,
                "episode_type": "driving",
                "t_start":      row["t_start"],
                "t_end":        row["t_end"],
                "duration_s":   row["t_end"] - row["t_start"],
                "link_id":      None,
                "distance_m":   row["distance_m"]
            })

            # Parked episode between consecutive trips
            if i + 1 < len(group):
                next_trip = group.iloc[i + 1]
                records.append({
                    "vehicle_id":   vehicle_id,
                    "episode_type": "parked",
                    "t_start":      row["t_end"],
                    "t_end":        next_trip["t_start"],
                    "duration_s":   next_trip["t_start"] - row["t_end"],
                    "link_id":      row["to_link"],
                    "distance_m":   None
                })

        # Parked episode after the last trip
        last_trip = group.iloc[-1]
        if last_trip["t_end"] < DAY_END:
            records.append({
                "vehicle_id":   vehicle_id,
                "episode_type": "parked",
                "t_start":      last_trip["t_end"],
                "t_end":        DAY_END,
                "duration_s":   DAY_END - last_trip["t_end"],
                "link_id":      last_trip["to_link"],
                "distance_m":   None
            })

    timetable = pd.DataFrame(records)
    timetable = timetable.sort_values(["vehicle_id", "t_start"]).reset_index(drop=True)

    # ── Enrich with activity types if plans data is provided ─────────────────
    if plans_path is not None and nodes is not None and links is not None:
        print("  → Enriching parked episodes with activity types...")
        plans_df = parse_plans(plans_path)
        # plans_df.to_parquet("output/plans_debug.parquet")     # If you want to save the plans in outputs
        timetable = _match_activities(timetable, plans_df, nodes, links)

    return timetable


# ── Activity matching ─────────────────────────────────────────────────────────
def _match_activities(timetable_df, plans_df, nodes, links):
    """
    Enrich each parked episode with activity_type and (x, y) from plans.

    Matching key: person_id + link_id + activity start_time_s within (t_start, t_end)
    Fallback for unmatched: activity_type = "unknown", (x,y) from network node.
    """
    
    # Initialises the three new columns for all episodes
    timetable_df = timetable_df.copy()
    timetable_df["activity_type"] = None
    timetable_df["x"]             = float("nan")
    timetable_df["y"]             = float("nan")
    # timetable_df["match_status"]  = "not_checked"

    # Boolean Series that is True only for parked rows
    parked_mask = timetable_df["episode_type"] == "parked"

    # Derive person_id from vehicle_id for parked episodes only
    timetable_df.loc[parked_mask, "person_id"] = (
        timetable_df.loc[parked_mask, "vehicle_id"].str.replace(":car", "", regex=False))


    # Build lookup: (person_id, link_id) -> rows in plans_df so that future lookups are faster
    plans_lookup = plans_df.groupby(["person_id", "link_id"])

    matched   = 0
    unmatched = 0

    # Iterates only over parked episodes. 
    # idx is the original DataFrame index. 
    # row is the full row as a Series.
    
    for idx, row in timetable_df[parked_mask].iterrows():
        person_id = row["person_id"]
        link_id   = str(row["link_id"])

        key = (person_id, link_id)

        if key in plans_lookup.groups:      # Checks if this (person_id, link_id) combination exists in the plans
            candidates = plans_df.loc[plans_lookup.groups[key]]
            # plans_lookup.groups[key] returns the integer indices of the matching rows in plans_df 
            # .loc[...] retrieves them (the matching rows)

            match = candidates
            

            if len(match) >= 1:
                timetable_df.at[idx, "activity_type"] = match.iloc[0]["activity_type"]
                timetable_df.at[idx, "x"]             = match.iloc[0]["x"]
                timetable_df.at[idx, "y"]             = match.iloc[0]["y"]
                
                matched += 1
                continue

        # No match — fallback to network node coordinates
        unmatched += 1
        timetable_df.at[idx, "activity_type"] = "unknown"
        # timetable_df.at[idx, "match_status"]  = "unmatched"
        
        if link_id in links:
            to_node_id = links[link_id].to_node
            if to_node_id in nodes:
                timetable_df.at[idx, "x"] = nodes[to_node_id].x
                timetable_df.at[idx, "y"] = nodes[to_node_id].y

    print(f"  → Matched: {matched:,} | Unmatched (fallback): {unmatched:,}")
    return timetable_df





