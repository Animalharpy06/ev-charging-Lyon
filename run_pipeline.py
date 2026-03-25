# -*- coding: utf-8 -*-
"""
Created on Fri Feb 20 11:00:42 2026
@author: Admin
"""

import os
import yaml
import pandas as pd
from network_parser import parse_network, build_length_lookup, links_to_dataframe
from events_parser import parse_events
from timetable_builder import build_timetable
from discharge_profile import build_discharge_profile
from prepare_profiles import build_profiles
from optimize import run_optimization
from plot_results import plot_results


# ── Load config ───────────────────────────────────────────────────────────────
with open(os.path.join(os.path.dirname(__file__), "config.yaml")) as f:
    cfg = yaml.safe_load(f)

SIM_OUTPUT        = cfg["eqasim_output"]
OUTPUT_DIR        = cfg["pipeline_output"]
TYPICAL_DAYS_PATH = cfg["typical_days"]

NETWORK_PATH  = os.path.join(SIM_OUTPUT, "output_network.xml.gz")
EVENTS_PATH   = os.path.join(SIM_OUTPUT, "output_events.xml.gz")
PLANS_PATH    = os.path.join(SIM_OUTPUT, "output_plans.xml.gz")
VEHICLES_PATH = os.path.join(SIM_OUTPUT, "output_allVehicles.xml")


os.makedirs(OUTPUT_DIR, exist_ok=True)
print("Saving outputs to:", OUTPUT_DIR)

# ── Step 1: Network ───────────────────────────────────────────────────────
print("[Step 1] Parsing network...")
links, nodes = parse_network(NETWORK_PATH)
link_length  = build_length_lookup(links)
df_links     = links_to_dataframe(links)
df_links.to_parquet(os.path.join(OUTPUT_DIR, "network_links.parquet"))
print(f"  → {len(links):,} links loaded")

# ── Step 2: Events ────────────────────────────────────────────────────────
print("\n[Step 2] Parsing events...")
trips, activities, person_to_vehicle = parse_events(EVENTS_PATH, link_length)
pd.DataFrame(trips).to_parquet(os.path.join(OUTPUT_DIR, "trips_raw.parquet"))
pd.DataFrame(activities).to_parquet(os.path.join(OUTPUT_DIR, "activities_raw.parquet"))

# ── Step 3: Build vehicle timetable ──────────────────────────────────────
print("\n[Step 3] Building vehicle timetable...")
trips_df  = pd.read_parquet(os.path.join(OUTPUT_DIR, "trips_raw.parquet"))
timetable = build_timetable(
    trips_df,
    plans_path = PLANS_PATH,   # already defined at top of run_pipeline.py
    nodes      = nodes,        # returned by parse_network() in Step 1
    links      = links         # returned by parse_network() in Step 1
)
timetable.to_parquet(os.path.join(OUTPUT_DIR, "vehicle_timetable.parquet"))
print(f"  → {len(timetable):,} episodes for {timetable['vehicle_id'].nunique():,} vehicles")

# ── Step 4a: Discharge profile ─────────────────────────────────────────────
print("\n[Step 4] Building discharge profile...")

timetable_df = pd.read_parquet(os.path.join(OUTPUT_DIR, "vehicle_timetable.parquet"))
discharge_df = build_discharge_profile(timetable_df)
discharge_df.to_parquet(os.path.join(OUTPUT_DIR, "discharge_profile.parquet"))

print(f"  → {discharge_df['vehicle_id'].nunique():,} vehicles | "
      f"{discharge_df['energy_consumed_kWh'].sum():.1f} kWh total consumed")

# ── Step 4b: Input profiles (solar + price) ───────────────────────────────
print("\n[Step 4b] Building input profiles...")
profiles_df = build_profiles(TYPICAL_DAYS_PATH)
profiles_df.to_parquet(os.path.join(OUTPUT_DIR, "input_profiles.parquet"))
print(f"  → {len(profiles_df)} slots | "
      f"Peak solar: {profiles_df['SolRad_Wm2'].max():.1f} W/m² | "
      f"Price range: {profiles_df['Price_EURkWh'].min()*1000:.1f}–"
      f"{profiles_df['Price_EURkWh'].max()*1000:.1f} €/MWh")

# ── Step 5: Gurobi optimization ───────────────────────────────────────────
print("\n[Step 5] Running optimization...")
opt_results = run_optimization()

if opt_results is not None:
    print("Results saved to output/optimization_results.parquet")
    print("SOC profiles saved to output/soc_results.parquet")
else:
    print("  ✗ Optimization failed — check Gurobi log above")
    
    
# ── Step 6: Result visualization ─────────────────────────────────────────
print("\n[Step 6] Plotting results...")
plot_results()




