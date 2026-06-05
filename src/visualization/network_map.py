import matplotlib.pyplot as plt
from pathlib import Path
import geopandas as gpd
import networkx as nx
from shapely.geometry import Point

from electrical_network.graph import graph_edges_to_geodataframe, MV_LV_SUBSTATIONS, HV_MV_CABIN, JUNCTION, EXTERNAL_BOUNDARY


def plot_network(district: gpd.GeoDataFrame,
                 district_boundary: gpd.GeoDataFrame,
                 G: nx.Graph) -> None:

    fig, ax = plt.subplots(figsize=(12, 12))
    
    _plot_district(ax, district, district_boundary)
    _plot_lines(ax, G)
    _plot_points(ax, G)

    ax.set_title("Quartier 5 — HTA Network", fontsize=14)
    ax.legend(markerscale=50)

    _save_figure("output/topology_check/network_map.png")

# ── Plotting ──────────────────────────────────────────────────────────────────

def _plot_district(ax,
                   district: gpd.GeoDataFrame,
                   district_boundary: gpd.GeoDataFrame) -> None:
    
    district.plot(ax=ax, color="lightyellow", edgecolor="gray", linewidth=0.1)
    district_boundary.plot(ax=ax, color="none", edgecolor="black", linewidth=0.5)

def _plot_lines(ax, G: nx.Graph) -> None:
    
    internal = graph_edges_to_geodataframe(G, category="internal")
    internal.plot(ax=ax, color="steelblue", linewidth=0.05,label=f"Internal HTA lines ({len(internal)})")
    boundary = graph_edges_to_geodataframe(G, category="boundary")
    boundary.plot(ax=ax, color="orange", linewidth=0.05,label=f"Boundary HTA lines ({len(boundary)})")
    

def _plot_points(ax,G: nx.Graph) -> None:
    
    mv_lv_substations = nodes_to_geodataframe(G, filter_key=MV_LV_SUBSTATIONS)
    hv_mv_cabins = nodes_to_geodataframe(G, filter_key=HV_MV_CABIN)
    junction_nodes = nodes_to_geodataframe(G, filter_key=JUNCTION)
    external_boundary_nodes = nodes_to_geodataframe(G, filter_key=EXTERNAL_BOUNDARY)

    if not mv_lv_substations.empty:
        mv_lv_substations.plot(ax=ax, color="red", markersize=0.1, marker=".", linewidth=0,  label=f"Substations ({len(mv_lv_substations)})")
    if not hv_mv_cabins.empty:
        hv_mv_cabins.plot(ax=ax, color="orange", markersize=0.1, marker="*",linewidth=0, label=f"HV/MV cabins ({len(hv_mv_cabins)})")
    if not junction_nodes.empty:
        junction_nodes.plot(ax=ax, color="purple", markersize=0.1, marker="^",linewidth=0, label=f"Junction nodes ({len(junction_nodes)})")
    if not external_boundary_nodes.empty:
        external_boundary_nodes.plot(ax=ax, color="green", markersize=0.1, marker=".", linewidth=0, label=f"External nodes ({len(external_boundary_nodes)})")


def nodes_to_geodataframe(G: nx.Graph, filter_key: str) -> gpd.GeoDataFrame:
    points = [Point(n) for n, d in G.nodes(data=True) if d.get(filter_key)]
    return gpd.GeoDataFrame(geometry=points, crs="EPSG:2154").to_crs("EPSG:4326")

# ── Saving ──────────────────────────────────────────────────────────────────

def _save_figure(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=4000, bbox_inches="tight")
    print(f"Map saved to {path}")
