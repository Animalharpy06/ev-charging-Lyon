from pathlib import Path

import geopandas as gpd
import networkx as nx

from topology.district import load_district, save_district
from electrical_network.network import (load_substations, load_hta_lines, 
                                        clip_substations_to_district, clip_lines_to_district,
                                        build_endpoint_snapping, classify_lines, save)
from electrical_network.graph import build_graph_from_snapping, report_graph_topology
from visualization.network_map import plot_network


# ── Orchestrator ───────────────────────────────────────────────────────────────

def run_topology_check() -> None:
    district, district_boundaries = load_or_build_district()
    substations_district = load_or_build_substations(district_boundaries)
    hta_lines_district, endpoint_nodes, sub_nodes, junc_nodes, ext_nodes = load_or_build_hta_lines(district_boundaries, substations_district)
    G = build_graph(hta_lines_district, endpoint_nodes, sub_nodes, junc_nodes, substations_district, ext_nodes)
    report_graph_topology(G)
    run_plot(district, district_boundaries, G)


# ── Step 1 ─────────────────────────────────────────────────────────────────────

def load_or_build_district() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    if Path(_CACHE["district"]).exists():
        print("Found existing file for the district")
        district = gpd.read_file(_CACHE["district"])
    else:
        district = _compute_and_cache_district()
    return district, district.dissolve()


def _compute_and_cache_district() -> gpd.GeoDataFrame:
    district = load_district("data/topology/iris_lyon.geojson")
    save_district(district, _CACHE["district"])
    return district


# ── Step 2 ─────────────────────────────────────────────────────────────────────

def load_or_build_substations(district_boundaries: gpd.GeoDataFrame) -> gpd.GeoDataFrame:

    if Path(_CACHE["substations"]).exists():
        print("Found existing file for the substations")
        return gpd.read_file(_CACHE["substations"])
    return _compute_and_cache_substations(district_boundaries)


def _compute_and_cache_substations(district_boundaries: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    substations = load_substations("data/electrical_network/enedis_nrj_energie.enedis_poste.json")
    substations_district = clip_substations_to_district(substations, district_boundaries)
    save(substations_district, _CACHE["substations"])
    return substations_district


# ── Step 3 ─────────────────────────────────────────────────────────────────────

def load_or_build_hta_lines(district_boundaries: gpd.GeoDataFrame,
                            substations_district: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict, set, set, set]:
    
    if Path(_CACHE["hta_lines"]).exists():
        print("Found existing file for thehta_lines. The snapping data is not cached, rebuilding from cached lines")
        hta_lines_district = gpd.read_file(_CACHE["hta_lines"])
        _, endpoint_nodes, sub_nodes, junc_nodes, ext_nodes = build_endpoint_snapping(hta_lines_district, substations_district, district_boundaries)
        return hta_lines_district, endpoint_nodes, sub_nodes, junc_nodes, ext_nodes
    return _compute_and_cache_hta_lines(district_boundaries, substations_district)


def _compute_and_cache_hta_lines(district_boundaries: gpd.GeoDataFrame, 
                                 substations_district: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict, set, set, set]:
    
    hta_lines = load_hta_lines("data/electrical_network/enedis_nrj_energie.enedis_reseau.json")
    hta_lines_district = clip_lines_to_district(hta_lines, district_boundaries)

    hta_lines_district, endpoint_nodes, substation_nodes_coord, junction_nodes_coord, external_nodes_coord = build_endpoint_snapping(hta_lines_district, substations_district, district_boundaries)
    hta_lines_district = classify_lines(hta_lines_district, endpoint_nodes, district_boundaries)
    save(hta_lines_district, _CACHE["hta_lines"])
    return hta_lines_district, endpoint_nodes, substation_nodes_coord, junction_nodes_coord, external_nodes_coord


# ── Step 4 ─────────────────────────────────────────────────────────────────────

def build_graph(hta_lines_district: gpd.GeoDataFrame,
                endpoint_nodes: dict,
                sub_nodes: set,
                junc_nodes: set,
                substations_district: gpd.GeoDataFrame,
                ext_nodes: set) -> nx.Graph:

    return build_graph_from_snapping(hta_lines_district, endpoint_nodes, sub_nodes, junc_nodes, substations_district, ext_nodes)


# ── Step 5 ─────────────────────────────────────────────────────────────────────

def run_plot(district: gpd.GeoDataFrame, district_boundaries: gpd.GeoDataFrame, G: nx.Graph) -> None:
    plot_network(district, district_boundaries, G)



_CACHE = {"district":     "cache/topology/district.geojson",
          "substations":  "cache/electrical_network/substations_district.geojson",
          "hta_lines":    "cache/electrical_network/hta_lines_district.geojson"}

if __name__ == "__main__":
    run_topology_check()