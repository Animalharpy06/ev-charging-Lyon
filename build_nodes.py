# -*- coding: utf-8 -*-
"""
Created on Thu Feb 26 15:11:11 2026

build_nodes.py
--------------
Assigns electrical nodes to parked vehicle episodes and prepares the two
data structures consumed by the multi-node LP in optimize.py:

    nodes.parquet               — one row per unique electrical node
                                  columns: node_id, x, y

    parking_assignments.parquet — one row per parking episode
                                  columns: vehicle_id, node_id,
                                           slot_start, slot_end,
                                           activity_type

Current node definition  : node_id = link_id where the vehicle is parked.
Future spatial upgrade   : replace the single assignment line with a
                           link_to_block mapping built by spatial clustering.
"""

import os
import pandas as pd

# ── Constants ─────────────────────────────────────────────────────────────────
SLOT_DURATION = 900   # seconds per time slot (15 min)
N_SLOTS       = 96    # slots in one day

# ── Main function ─────────────────────────────────────────────────────────────
def build_node_mapping(
    timetable  : pd.DataFrame,
    links      : dict,
    nodes      : dict,
    output_dir : str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Parameters
    ----------
    timetable  : pd.DataFrame
        Output of timetable_builder.build_timetable() — all driving and
        parked episodes for every vehicle.
    links      : dict[str -> Link]
        Returned by network_parser.parse_network().
        Used to look up from_node / to_node so we can derive link coordinates.
    nodes      : dict[str -> Node]
        Returned by network_parser.parse_network().
        Each Node carries .x and .y in the projected CRS.
    output_dir : str
        Folder where output files are written (matches OUTPUT_DIR in config).

    Returns
    -------
    nodes_df       : pd.DataFrame  — node registry (one row per unique node)
    assignments_df : pd.DataFrame  — parking episodes with node and slot info
    """

    # ── 1. Filter to parked episodes only ────────────────────────────────────
    #
    # The timetable contains two episode types:
    #   "parked"  — vehicle is stationary at a link (has a link_id)
    #   "driving" — vehicle is moving         (link_id is None)
    #
    # We only care about parked rows: only parked vehicles consume charging
    # power and therefore only they belong to an electrical node.
    #
    # .copy() creates an independent DataFrame so that the assignments we add
    # below (node_id, slot_start, slot_end) don't accidentally modify the
    # original timetable object that was passed in.
    
    parking = timetable[(timetable["episode_type"] == "parked") &   # keep only parked rows
        (timetable["link_id"].notna())].copy()                      # drop any row missing a link
    

    # ── 2. Assign node_id ─────────────────────────────────────────────────────
    #
    # For now: node_id = link_id (one electrical node per road segment).
    # This is the ONLY line to change when spatial aggregation is added later.
    # At that point you will build a  link_to_block  dict  (link_id -> block_id)
    # from a clustering step and replace the line below with:
    #   parking["node_id"] = parking["link_id"].map(link_to_block)
    
    parking["node_id"] = parking["link_id"]

    # ── 3. Convert episode times to slot indices ──────────────────────────────
    #
    # The LP works in 15-min slots numbered 0 … 95.
    # We need to know: for this parking episode, which slots does it span?
    #
    # slot_start — the slot in which the vehicle ARRIVES (inclusive).
    #   Example: vehicle parks at t=3600s  →  3600/900 = 4.0  →  slot 4
    #
    # slot_end   — the slot AFTER the vehicle LEAVES (exclusive upper bound).
    #   This matches Python's range() convention: range(4, 8) gives [4,5,6,7].
    #   Example: vehicle leaves at t=7200s  →  7200/900 = 8.0  →  slot_end = 8
    #            so the vehicle is present in slots 4, 5, 6, 7  (not 8).
    #
    # int()  floors the division result to the slot index.
    # .clip() ensures we never go below 0 or above the valid range:
    #   slot_start is clipped to [0, N_SLOTS-1]  (first valid slot = 0)
    #   slot_end   is clipped to [0, N_SLOTS]    (N_SLOTS = 96 is a valid
    #              exclusive upper bound for the last slot 95)
    parking["slot_start"] = (parking["t_start"] / SLOT_DURATION).apply(int).clip(0, N_SLOTS - 1)
    parking["slot_end"]   = (parking["t_end"]   / SLOT_DURATION).apply(int).clip(0, N_SLOTS)

    # ── 4. Build parking assignment table ────────────────────────────────────
    #
    # This table has ONE ROW PER PARKING EPISODE (not one row per slot).
    # The LP will later expand each episode into individual slots when building
    # the V_n(t) sets (vehicles at node n in slot t).
    #
    # Storing episodes instead of a dense [V × 96] matrix:
    #   - is more memory-efficient (most vehicles park at ~2-3 locations/day)
    #   - makes the spatial upgrade trivial (just change node_id column)
    #   - keeps the file human-readable for debugging
    #
    # If the timetable was built without plans data, activity_type won't exist.
    # We add it as None so the output schema is always consistent.
    if "activity_type" not in parking.columns:
        parking["activity_type"] = None

    assignments_df = parking[["vehicle_id", "node_id", "slot_start", "slot_end", "activity_type"]].reset_index(drop=True)
    # reset_index(drop=True) resets the row numbers to 0,1,2,… and drop=True
    # discards the old index (which came from the filtered timetable and would
    # have gaps like 0, 3, 7, … making the file confusing to read).

    # ── 5. Build node registry ────────────────────────────────────────────────
    #
    # We want one row per unique node_id with its (x, y) coordinates.
    #
    # The Link dataclass in network_parser.py does NOT carry x/y directly —
    # only Node objects do. Each Link has a from_node and to_node attribute.
    # We take the midpoint of the two endpoint nodes as the link's representative
    # coordinate. This is good enough for visualisation and future clustering.
    #
    # Step A: get the unique (node_id, link_id) pairs from the parking table.
    #   drop_duplicates("node_id") keeps only the first occurrence of each node,
    #   which is all we need since node_id == link_id for now.
    unique_nodes = (parking[["node_id", "link_id"]].drop_duplicates("node_id").copy())

    # Step B: define two helper functions that look up x and y for a link_id.
    #
    # links.get(lid) returns the Link object if lid exists, or None if not.
    # If the Link exists, we get its from_node and to_node IDs.
    # We then look up those IDs in the nodes dict to get the Node objects,
    # and return the average of their x (or y) coordinates.
    # If anything is missing, we return None gracefully.
    def _link_x(lid: str):
        lk = links.get(lid)
        if lk is None:
            return None
        n1 = nodes.get(lk.from_node)   # Node object at the start of the link
        n2 = nodes.get(lk.to_node)     # Node object at the end of the link
        if n1 is None or n2 is None:
            return None
        return (n1.x + n2.x) / 2       # midpoint x coordinate

    def _link_y(lid: str):
        lk = links.get(lid)
        if lk is None:
            return None
        n1 = nodes.get(lk.from_node)
        n2 = nodes.get(lk.to_node)
        if n1 is None or n2 is None:
            return None
        return (n1.y + n2.y) / 2       # midpoint y coordinate

    # Step C: apply the helper functions to each link_id in the unique_nodes table.
    # .map(func) applies func to every value in the column and returns a new Series.
    unique_nodes["x"] = unique_nodes["link_id"].map(_link_x)
    unique_nodes["y"] = unique_nodes["link_id"].map(_link_y)

    # Step D: keep only the three columns we actually need and reset the index.
    nodes_df = unique_nodes[["node_id", "x", "y"]].reset_index(drop=True)

    # ── 6. Write outputs to disk ──────────────────────────────────────────────
    #
    # os.makedirs(..., exist_ok=True) creates the output folder if it doesn't
    # exist yet; if it already exists, it does nothing (no error).
    os.makedirs(output_dir, exist_ok=True)

    nodes_out       = os.path.join(output_dir, "nodes.parquet")
    assignments_out = os.path.join(output_dir, "parking_assignments.parquet")

    nodes_df.to_parquet(nodes_out,       index=False)
    assignments_df.to_parquet(assignments_out, index=False)
    # index=False prevents pandas from writing the row numbers (0,1,2,…) as
    # a separate column in the parquet file — we don't need them.

    # ── 7. Print summary ──────────────────────────────────────────────────────
    print(f"  → {len(nodes_df):,} unique nodes (one per parking link)")
    print(f"  → {len(assignments_df):,} parking episodes assigned")
    print(f"  → {assignments_df['vehicle_id'].nunique():,} vehicles with ≥1 parked episode")
    print(f"  → Activity type breakdown:")
    for atype, cnt in assignments_df["activity_type"].value_counts(dropna=False).items():
        print(f"       {str(atype):20s}: {cnt:,}")

    return nodes_df, assignments_df