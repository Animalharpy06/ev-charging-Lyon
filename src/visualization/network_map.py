import matplotlib.pyplot as plt
from pathlib import Path
import geopandas as gpd
import networkx as nx
from shapely.geometry import Point

from electrical_network.graph import graph_edges_to_geodataframe


def plot_network(
    district: gpd.GeoDataFrame,
    district_boundary: gpd.GeoDataFrame,
    G: nx.Graph
    ) -> None:

    fig, ax = plt.subplots(figsize=(12, 12))

    district.plot(ax=ax, color="lightyellow", edgecolor="gray", linewidth=0.5)
    district_boundary.plot(ax=ax, color="none", edgecolor="black", linewidth=1.5)

    _plot_lines(ax, G)
    _plot_points(ax, G)

    ax.set_title("Quartier 5 — HTA Network", fontsize=14)
    ax.legend()

    _save_figure("output/topology_check/network_map.png")


def _plot_lines(ax, 
                G: nx.Graph) -> None:
    
    internal = graph_edges_to_geodataframe(G, category="internal")
    internal.plot(ax=ax, color="steelblue", linewidth=0.1,label=f"Internal HTA lines ({len(internal)})")



def _plot_points(
    ax,
    G: nx.Graph
) -> None:
    
    substations   = nodes_to_geodataframe(G, filter_key="is_MV-LV_substation")
    hv_mv_cabins  = nodes_to_geodataframe(G, filter_key="is_HV-MV_cabin")
    junction_nodes = nodes_to_geodataframe(G, filter_key="is_junction")

    substations.plot(ax=ax, color="red", markersize=1, label=f"Substations ({len(substations)})")
    hv_mv_cabins.plot(ax=ax, color="orange", markersize=1, marker="*", label=f"HV/MV cabins ({len(hv_mv_cabins)})")
    junction_nodes.plot(ax=ax, color="purple", markersize=1, marker="^",label=f"Junction nodes ({len(junction_nodes)})")



def nodes_to_geodataframe(G: nx.Graph, filter_key: str) -> gpd.GeoDataFrame:
    points = [Point(n) for n, d in G.nodes(data=True) if d.get(filter_key)]
    return gpd.GeoDataFrame(geometry=points, crs="EPSG:2154").to_crs("EPSG:4326")

def _save_figure(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=1000, bbox_inches="tight")
    print(f"Map saved to {path}")
