from pathlib import Path

import geopandas as gpd
import networkx as nx

from topology.district import load_district, save_district, filter_iris_by_network_coverage
from electrical_network.network import (load_substations, load_lines, clip_substations_to_district, clip_lines_to_district, 
                                        build_endpoint_snapping, classify_lines, save)
from electrical_network.graph import (build_graph_from_snapping, report_graph_topology, keep_main_component, extract_main_component)
from visualization.network_map import plot_network
from buildings.load import load_building_groups, clip_to_district, save_building_groups


_CACHE = {
    "district":    "cache/topology/district.geojson",
    "substations": "cache/electrical_network/substations_district.geojson",
    "lines":       "cache/electrical_network/lines_district.geojson",
    "buildings":   "cache/buildings/buildings_district.geojson"}


# ── Orchestrator ───────────────────────────────────────────────────────────────


def run_topology_check() -> None:

    district, district_boundary = load_or_build_district()
    substations_district = load_or_build_substations(district_boundary)
    hta_lines_district, endpoint_nodes, sub_nodes, junc_nodes, ext_nodes = load_or_build_hta_lines(district_boundary, substations_district)
    G = build_graph(hta_lines_district, endpoint_nodes, sub_nodes, junc_nodes, substations_district, ext_nodes)
    district, district_boundary = filter_district_to_main_component(district, G)
    buildings_district = load_or_build_buildings(district_boundary)
    run_plot(district, district_boundary, G)


# ── Step 1 ─────────────────────────────────────────────────────────────────────


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


# ── Step 2 ─────────────────────────────────────────────────────────────────────


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


# ── Step 3 ─────────────────────────────────────────────────────────────────────


def load_or_build_hta_lines(district_boundary: gpd.GeoDataFrame, 
                            substations_district: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict, set, set, set]:
    if Path(_CACHE["lines"]).exists():
        print("Found existing file for the lines. The snapping data is not cached, rebuilding from cached lines")
        lines_district = gpd.read_file(_CACHE["lines"])
        _, endpoint_nodes, sub_nodes, junc_nodes, ext_nodes = build_endpoint_snapping(lines_district, substations_district, district_boundary)
        return lines_district, endpoint_nodes, sub_nodes, junc_nodes, ext_nodes
    print("No existing file found for the lines, building it from input data")
    return _compute_and_cache_lines(district_boundary, substations_district)


def _compute_and_cache_lines(district_boundary: gpd.GeoDataFrame,
                             substations_district: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict, set, set, set]:
    lines = load_lines("data/electrical_network/enedis_nrj_energie.enedis_reseau.json")
    lines_district = clip_lines_to_district(lines, district_boundary)
    lines_district, endpoint_nodes, sub_nodes, junc_nodes, ext_nodes = build_endpoint_snapping(lines_district, substations_district, district_boundary)
    lines_district = classify_lines(lines_district, endpoint_nodes, district_boundary)
    save(lines_district, _CACHE["lines"])
    return lines_district, endpoint_nodes, sub_nodes, junc_nodes, ext_nodes


# ── Step 4 ─────────────────────────────────────────────────────────────────────


def build_graph(hta_lines_district: gpd.GeoDataFrame,
                endpoint_nodes: dict,
                sub_nodes: set,
                junc_nodes: set,
                substations_district: gpd.GeoDataFrame,
                ext_nodes: set) -> nx.Graph:
    G = build_graph_from_snapping(hta_lines_district, endpoint_nodes, sub_nodes, junc_nodes, substations_district, ext_nodes)
    G = keep_main_component(G)
    report_graph_topology(G)
    return G

# ── Step 5 ─────────────────────────────────────────────────────────────────────


def filter_district_to_main_component(district: gpd.GeoDataFrame, G: nx.Graph) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    print("Filtering district to main network component")
    filtered_district = filter_iris_by_network_coverage(district, set(G.nodes()))
    return filtered_district, filtered_district.dissolve()


# ── Step 6 ─────────────────────────────────────────────────────────────────────


def load_or_build_buildings(district_boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if Path(_CACHE["buildings"]).exists():
        print("Found existing file for buildings.")
        return gpd.read_file(_CACHE["buildings"])
    print("No existing file found for the buildings, building it from scratch")
    return _compute_and_cache_buildings(district_boundary)


def _compute_and_cache_buildings(district_boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    buildings = load_building_groups("data/buildings/bdnb.gpkg")
    buildings_district = clip_to_district(buildings, district_boundary)
    save_building_groups(buildings_district, _CACHE["buildings"])
    return buildings_district


# ── Step 7 ─────────────────────────────────────────────────────────────────────


def run_plot(district: gpd.GeoDataFrame,
             district_boundary: gpd.GeoDataFrame,
             G: nx.Graph) -> None:
    print("Plotting the electrical network")
    plot_network(district, district_boundary, G)


if __name__ == "__main__":
    run_topology_check()