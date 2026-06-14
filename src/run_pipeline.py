from pathlib import Path
import json
import ast

import geopandas as gpd
import pandas as pd
import networkx as nx

from topology.district import load_district, save_district, filter_iris_by_network_coverage
from electrical_network.network import (load_substations, load_lines, clip_substations_to_district,
                                        clip_lines_to_district, build_endpoint_snapping, classify_lines, save)
from electrical_network.graph import (build_graph_from_snapping, report_graph_topology,
                                      keep_main_component)
from visualization.network_map import plot_network
from buildings.load import load_building_groups, clip_to_district, save_building_groups
from buildings.demand import build_demand_profiles
from weather.era5 import load_temperature_15min
from buildings.aggregation import assign_buildings_to_nodes, aggregate_demand_by_node, aggregate_pv_capacity_by_node


_CACHE = {
    "district":                  "cache/topology/district.geojson",
    "substations":               "cache/electrical_network/substations_district.geojson",
    "lines":                     "cache/electrical_network/lines_district.geojson",
    "endpoint_nodes":            "cache/electrical_network/endpoint_nodes.json",
    "snapping_nodes":            "cache/electrical_network/snapping_nodes.json",
    "buildings":                 "cache/buildings/buildings_district.geojson",
    "demand_electricity":        "cache/buildings/demand_electricity.parquet",
    "demand_heat":               "cache/buildings/demand_heat.parquet",
    "building_to_node":        "cache/buildings/building_to_node.parquet",
    "node_demand_electricity":   "cache/buildings/node_demand_electricity.parquet",
    "node_demand_heat":          "cache/buildings/node_demand_heat.parquet",
    "node_pv_capacity":          "cache/buildings/node_pv_capacity.parquet",
}


# ── Orchestrator ──────────────────────────────────────────────────────────────


def run_topology_check() -> None:

    district, district_boundary = load_or_build_district()
    substations_district = load_or_build_substations(district_boundary)
    hta_lines_district, endpoint_nodes, sub_nodes, junc_nodes, orphan_nodes_coord = load_or_build_hta_lines(district_boundary, substations_district)
    Graph = build_graph(hta_lines_district, endpoint_nodes, sub_nodes, junc_nodes, orphan_nodes_coord)
    district, district_boundary = filter_district_to_main_component(district, Graph)
    buildings_clipped = load_or_build_buildings(district_boundary)
    run_plot(district, district_boundary, Graph)
    demand_profiles = load_or_build_demand_profiles(buildings_clipped)
    building_to_node = load_or_build_building_to_node(buildings_clipped, Graph)
    node_demand      = load_or_build_node_demand(demand_profiles, building_to_node)
    node_pv_capacity = load_or_build_node_pv_capacity(buildings_clipped, building_to_node)



# ── Step 1: District ──────────────────────────────────────────────────────────


def load_or_build_district() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    if Path(_CACHE["district"]).exists():
        print("Found existing file for the district")
        district = gpd.read_file(_CACHE["district"])
    else:
        print("No existing file found for the district, building it from input data")
        district = _compute_and_cache_district()
    return district, district.dissolve()


def _compute_and_cache_district() -> gpd.GeoDataFrame:
    district = load_district("data/topology/iris_lyon.geojson")
    save_district(district, _CACHE["district"])
    return district


# ── Step 2: Substations ───────────────────────────────────────────────────────


def load_or_build_substations(district_boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if Path(_CACHE["substations"]).exists():
        print("Found existing file for the substations")
        return gpd.read_file(_CACHE["substations"])
    print("No existing file found for the substations, building it from input data")
    return _compute_and_cache_substations(district_boundary)


def _compute_and_cache_substations(district_boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    substations = load_substations("data/electrical_network/enedis_nrj_energie.enedis_poste.json")
    substations_district = clip_substations_to_district(substations, district_boundary)
    save(substations_district, _CACHE["substations"])
    return substations_district


# ── Step 3: HTA lines (snapping + classification) ─────────────────────────────


def load_or_build_hta_lines(district_boundary: gpd.GeoDataFrame,
                             substations_district: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict, set, set, set]:

    cache_files = [_CACHE["lines"], _CACHE["endpoint_nodes"], _CACHE["snapping_nodes"]]
    if all(Path(p).exists() for p in cache_files):
        print("Found existing files for HTA lines")
        return _load_lines_cache()
    print("No existing files found for HTA lines, building from scratch")
    return _compute_and_cache_lines(district_boundary, substations_district)


def _load_lines_cache() -> tuple[gpd.GeoDataFrame, dict, set, set, set]:
    lines          = gpd.read_file(_CACHE["lines"])
    endpoint_nodes = _deserialize_endpoint_nodes(_CACHE["endpoint_nodes"])
    sub_nodes, junc_nodes, orphan_nodes = _deserialize_snapping_nodes(_CACHE["snapping_nodes"])
    return lines, endpoint_nodes, sub_nodes, junc_nodes, orphan_nodes


def _compute_and_cache_lines(district_boundary: gpd.GeoDataFrame,
                              substations_district: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict, set, set, set]:
    lines          = load_lines("data/electrical_network/enedis_nrj_energie.enedis_reseau.json")
    lines_district = clip_lines_to_district(lines, district_boundary)
    lines_post_snapping, endpoint_nodes, sub_nodes, junc_nodes, orphan_nodes = \
        build_endpoint_snapping(lines_district, substations_district, district_boundary)
    lines_post_snapping = classify_lines(lines_post_snapping, endpoint_nodes, district_boundary)
    _save_lines_cache(lines_post_snapping, endpoint_nodes, sub_nodes, junc_nodes, orphan_nodes)
    return lines_post_snapping, endpoint_nodes, sub_nodes, junc_nodes, orphan_nodes


def _save_lines_cache(lines: gpd.GeoDataFrame,
                      endpoint_nodes: dict,
                      sub_nodes: set,
                      junc_nodes: set,
                      orphan_nodes: set) -> None:
    Path(_CACHE["lines"]).parent.mkdir(parents=True, exist_ok=True)
    lines.to_file(_CACHE["lines"], driver="GeoJSON")
    _serialize_endpoint_nodes(endpoint_nodes, _CACHE["endpoint_nodes"])
    _serialize_snapping_nodes(sub_nodes, junc_nodes, orphan_nodes, _CACHE["snapping_nodes"])
    print("HTA lines cached successfully")


# ── Step 3 serialization helpers ──────────────────────────────────────────────
#
# endpoint_nodes has tuple keys and tuple values — neither is natively JSON-serialisable.
#
#   key   (int, str)           →  "123__start"
#   value (float, float)       →  [668423.0, 5117832.0]
#
# snapping_nodes are three sets of (float, float) tuples, stored as lists of lists.


def _serialize_endpoint_nodes(endpoint_nodes: dict, path: str) -> None:
    serialisable = {f"{line_idx}__{side}": list(coord) for (line_idx, side), coord in endpoint_nodes.items()}
    Path(path).write_text(json.dumps(serialisable), encoding="utf-8")


def _deserialize_endpoint_nodes(path: str) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {(int(k.split("__")[0]), k.split("__")[1]): tuple(v) for k, v in raw.items()}


def _serialize_snapping_nodes(sub_nodes: set,
                               junc_nodes: set,
                               orphan_nodes: set,
                               path: str) -> None:
    serialisable = {"sub_nodes":    [list(t) for t in sub_nodes],
                    "junc_nodes":   [list(t) for t in junc_nodes],
                    "orphan_nodes": [list(t) for t in orphan_nodes]}
    Path(path).write_text(json.dumps(serialisable), encoding="utf-8")


def _deserialize_snapping_nodes(path: str) -> tuple[set, set, set]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return ({tuple(t) for t in raw["sub_nodes"]},
            {tuple(t) for t in raw["junc_nodes"]},
            {tuple(t) for t in raw["orphan_nodes"]})


# ── Step 4: Graph ─────────────────────────────────────────────────────────────


def build_graph(hta_lines_district: gpd.GeoDataFrame,
                endpoint_nodes: dict,
                sub_nodes: set,
                junc_nodes: set,
                orphan_nodes: set) -> nx.Graph:

    G = build_graph_from_snapping(hta_lines_district, endpoint_nodes, sub_nodes, junc_nodes, orphan_nodes)
    G = keep_main_component(G)
    report_graph_topology(G)
    return G


# ── Step 5: Filter district to main network component ─────────────────────────


def filter_district_to_main_component(district: gpd.GeoDataFrame,
                                       G: nx.Graph) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    print("Filtering district to main network component")
    filtered_district = filter_iris_by_network_coverage(district, set(G.nodes()))
    return filtered_district, filtered_district.dissolve()


# ── Step 6: Buildings ─────────────────────────────────────────────────────────


def load_or_build_buildings(district_boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if Path(_CACHE["buildings"]).exists():
        print("Found existing file for buildings")
        return gpd.read_file(_CACHE["buildings"])
    print("No existing file found for the buildings, building it from scratch")
    return _compute_and_cache_buildings(district_boundary)


def _compute_and_cache_buildings(district_boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    buildings = load_building_groups("data/buildings/bdnb.gpkg")
    buildings_district = clip_to_district(buildings, district_boundary)
    save_building_groups(buildings_district, _CACHE["buildings"])
    return buildings_district


# ── Step 7: Plot ──────────────────────────────────────────────────────────────


def run_plot(district: gpd.GeoDataFrame,
             district_boundary: gpd.GeoDataFrame,
             G: nx.Graph) -> None:
    print("Plotting the electrical network")
    plot_network(district, district_boundary, G)


# ── Step 8: Associate Buildings to nodes ──────────────────────────────────────────────────────────────


def load_or_build_building_to_node(buildings: gpd.GeoDataFrame,
                                   G: nx.Graph) -> pd.Series:
    if Path(_CACHE["building_to_node"]).exists():
        print("Found existing file for building-to-node assignment")
        raw = pd.read_parquet(_CACHE["building_to_node"])["node_key"]
        return raw.map(ast.literal_eval)
    print("No existing file for building-to-node assignment, building from scratch")
    return _compute_and_cache_building_to_node(buildings, G)


def _compute_and_cache_building_to_node(buildings: gpd.GeoDataFrame,
                                        G: nx.Graph) -> pd.Series:
    building_to_node = assign_buildings_to_nodes(buildings, G)
    path = _CACHE["building_to_node"]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    building_to_node.map(str).to_frame("node_key").to_parquet(path)
    return building_to_node

# ── Step 9: Demand profiles ───────────────────────────────────────────────────


def load_or_build_demand_profiles(buildings: gpd.GeoDataFrame) -> dict[str, pd.DataFrame]:
    if Path(_CACHE["demand_electricity"]).exists() and Path(_CACHE["demand_heat"]).exists():
        print("Found existing files for demand profiles")
        return {
            "electricity": pd.read_parquet(_CACHE["demand_electricity"]),
            "heat":        pd.read_parquet(_CACHE["demand_heat"])}
    print("No existing files found for demand profiles, building from scratch")
    return _compute_and_cache_demand_profiles(buildings)


def _compute_and_cache_demand_profiles(buildings: gpd.GeoDataFrame) -> dict[str, pd.DataFrame]:
    temperature_15min = load_temperature_15min("data/weather/era5_lyon.grib", year=2025)
    demand_profiles   = build_demand_profiles(buildings, temperature_15min, year=2025)
    _save_demand_profiles(demand_profiles)
    return demand_profiles


def _save_demand_profiles(demand_profiles: dict[str, pd.DataFrame]) -> None:
    for key, df in demand_profiles.items():
        path = _CACHE[f"demand_{key}"]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path)


# ── Step 10a: Node demand ───────────────────────────────────────────────────────


def load_or_build_node_demand(demand_profiles: dict[str, pd.DataFrame],
                               building_to_node: pd.Series) -> dict[str, pd.DataFrame]:

    if Path(_CACHE["node_demand_electricity"]).exists() and Path(_CACHE["node_demand_heat"]).exists():
        print("Found existing files for node demand")
        return {
            "electricity": _parse_node_columns(pd.read_parquet(_CACHE["node_demand_electricity"])),
            "heat":        _parse_node_columns(pd.read_parquet(_CACHE["node_demand_heat"]))}
    print("No existing files found for node demand, building from scratch")
    return _compute_and_cache_node_demand(demand_profiles, building_to_node)


def _compute_and_cache_node_demand(demand_profiles:dict[str, pd.DataFrame], 
                                   building_to_node: pd.Series)-> dict[str, pd.DataFrame]:
    node_demand = aggregate_demand_by_node(demand_profiles, building_to_node)
    _save_node_demand(node_demand)
    return node_demand


def _parse_node_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Parquet serialises tuple column names as strings — restore them
    df.columns = [ast.literal_eval(c) for c in df.columns]
    return df


def _save_node_demand(node_demand: dict[str, pd.DataFrame]) -> None:
    for key, df in node_demand.items():
        path = _CACHE[f"node_demand_{key}"]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        df.rename(columns=str).to_parquet(path)


# ── Step 10b: Node PV capacity ─────────────────────────────────────────────────


def load_or_build_node_pv_capacity(buildings: gpd.GeoDataFrame,
                                   building_to_node: pd.Series) -> pd.Series:
    if Path(_CACHE["node_pv_capacity"]).exists():
        print("Found existing files for node PV capacity")
        return pd.read_parquet(_CACHE["node_pv_capacity"])["pv_capacity_kw"]
    print("No existing files found for node PV capacity, building from scratch")
    return _compute_and_cache_node_pv_capacity(buildings, building_to_node)


def _compute_and_cache_node_pv_capacity(buildings, building_to_node) :
    node_pv_capacity = aggregate_pv_capacity_by_node(buildings, building_to_node)
    _save_pv_capacity(node_pv_capacity)
    return node_pv_capacity


def _save_pv_capacity(pv_capacity: pd.Series) -> None:
    path = _CACHE["node_pv_capacity"]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pv_capacity.to_frame().to_parquet(path)


if __name__ == "__main__":
    run_topology_check()