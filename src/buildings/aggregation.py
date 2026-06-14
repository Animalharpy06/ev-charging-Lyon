import networkx as nx
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from shapely.strtree import STRtree
from typing import cast

from electrical_network.graph import MV_LV_SUBSTATIONS

_PV_PANEL_DENSITY = 200.0 #W/m2
_ROOFTOP_USABLE_FRACTION   = 0.3   # 30% of the rooftop are

def assign_buildings_to_nodes(buildings: gpd.GeoDataFrame,
                              G: nx.Graph) -> pd.Series:
    
    mv_lv_nodes = _extract_mv_lv_nodes(G)
    node_tree, node_coord = _build_node_tree(mv_lv_nodes)
    building_centroids   = _building_centroids(buildings)

    assignments = {building_id: node_coord[node_tree.nearest(centroid)] for building_id, centroid in building_centroids.items()}

    return pd.Series(assignments, name="node_key")


def aggregate_demand_by_node(demand_profiles: dict[str, pd.DataFrame],
                             building_to_node: pd.Series) -> dict[str, pd.DataFrame]:

    return {demand_type: _sum_profiles_by_node(df, building_to_node) for demand_type, df in demand_profiles.items()}


def aggregate_pv_capacity_by_node(buildings: gpd.GeoDataFrame,
                                  building_to_node: pd.Series) -> pd.Series:
    
    pv_capacity_per_building = _pv_capacity_per_building(buildings)
    return pv_capacity_per_building.groupby(building_to_node).sum()


# ── Node extraction ───────────────────────────────────────────────────────────

def _extract_mv_lv_nodes(G: nx.Graph) -> dict[tuple[float, float], Point]:
    # Only MV/LV substations are valid load nodes — junctions and cabins are topological artefacts with no direct building connection
    return {node: Point(node) for node, data in G.nodes(data=True) if data.get(MV_LV_SUBSTATIONS)}


def _build_node_tree(mv_lv_nodes: dict[tuple[float, float], Point]) -> tuple[STRtree, list[tuple[float, float]]]:

    #Link between points and coordinates, since STRtree doen't remember the original element
    node_coord   = list(mv_lv_nodes.keys())
    node_points = [mv_lv_nodes[k] for k in node_coord]
    return STRtree(node_points), node_coord


# ── Building centroids ────────────────────────────────────────────────────────

def _building_centroids(buildings: gpd.GeoDataFrame) -> dict[str, Point]:
    buildings_projected = buildings.to_crs("EPSG:2154")
    centroids = buildings_projected.geometry.centroid
    return {bid: cast(Point, c) for bid, c in zip(buildings_projected["batiment_groupe_id"].astype(str), centroids)}


# ── Pv per building ───────────────────────────────────────────────────────────────


def _pv_capacity_per_building(buildings: gpd.GeoDataFrame) -> pd.Series:
    capacity = (buildings.set_index("batiment_groupe_id")["s_geom_groupe"].astype(float) * _ROOFTOP_USABLE_FRACTION * _PV_PANEL_DENSITY/ 1000.0)
    capacity.index = capacity.index.astype(str)
    return capacity.rename("pv_capacity_kw")


# ── Aggregation ───────────────────────────────────────────────────────────────

def _sum_profiles_by_node(profiles: pd.DataFrame,
                          building_to_node: pd.Series) -> pd.DataFrame:
    
    return profiles.T.groupby(building_to_node).sum().T


