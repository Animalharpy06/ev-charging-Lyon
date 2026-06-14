import matplotlib.pyplot as plt
from pathlib import Path
import geopandas as gpd
import networkx as nx
from shapely.geometry import Point

from electrical_network.graph import (graph_edges_to_geodataframe,
                                      MV_LV_SUBSTATIONS, HV_MV_CABIN, JUNCTION, EXTERNAL_NODE, ORPHAN)


def plot_network(district: gpd.GeoDataFrame,
                 district_boundary: gpd.GeoDataFrame,
                 G: nx.Graph) -> None:

    fig, ax = plt.subplots(figsize=(12, 12))

    _plot_district(ax, district, district_boundary)
    _plot_hta_lines(ax, G)
    _plot_graph_nodes(ax, G)


    ax.set_title("HTA Network", fontsize=14)
    ax.legend(markerscale=50)
    _save_figure("output/topology_check/network_map.png")


# ── District ──────────────────────────────────────────────────────────────────

def _plot_district(ax,
                   district: gpd.GeoDataFrame,
                   district_boundary: gpd.GeoDataFrame) -> None:
    
    district.to_crs("EPSG:4326").plot(ax=ax, color="lightyellow", edgecolor="gray", linewidth=0.1)
    district_boundary.to_crs("EPSG:4326").plot(ax=ax, color="none", edgecolor="black", linewidth=0.5)


# ── HTA lines (from graph) ────────────────────────────────────────────────────

def _plot_hta_lines(ax, G: nx.Graph) -> None:
    _plot_line_category(ax, G, category="internal", color="steelblue", label_prefix="HTA internal")
    _plot_line_category(ax, G, category="boundary", color="steelblue", label_prefix="HTA boundary", dashed=True)


def _plot_line_category(ax,
                        G: nx.Graph,
                        category: str,
                        color: str,
                        label_prefix: str,
                        dashed: bool = False,) -> None:
    
    gdf = graph_edges_to_geodataframe(G, category=category).to_crs("EPSG:4326")
    if gdf.empty:
        return
    gdf.plot(ax=ax, color=color, linewidth=0.01, linestyle="--" if dashed else "-", label=f"{label_prefix} ({len(gdf)})")


# ── Graph nodes ───────────────────────────────────────────────────────────────

def _plot_graph_nodes(ax, G: nx.Graph) -> None:
    _plot_node_type(ax, G, MV_LV_SUBSTATIONS, color="red",    marker=".", label_prefix="MV/LV substations")
    _plot_node_type(ax, G, HV_MV_CABIN,       color="orange", marker="*", label_prefix="HV/MV cabins")
    _plot_node_type(ax, G, JUNCTION,          color="purple", marker="^", label_prefix="Junction nodes", markersize=0.01)
    _plot_node_type(ax, G, EXTERNAL_NODE, color="green",  marker=".", label_prefix="External nodes")
    _plot_node_type(ax, G, ORPHAN, color="cyan",  marker=".", label_prefix="Orphan", markersize=0.05)


def _plot_node_type(ax,
                    G: nx.Graph,
                    filter_key: str,
                    color: str,
                    marker: str,
                    label_prefix: str,
                    markersize=0.1) -> None:
    
    gdf = nodes_to_geodataframe(G, filter_key)
    if gdf.empty:
        return
    gdf.plot(ax=ax, color=color, markersize=markersize, marker=marker, linewidth=0, label=f"{label_prefix} ({len(gdf)})")

# ── Helpers ───────────────────────────────────────────────────────────────────

def nodes_to_geodataframe(G: nx.Graph, filter_key: str) -> gpd.GeoDataFrame:
    points = [Point(n) for n, d in G.nodes(data=True) if d.get(filter_key)]
    return gpd.GeoDataFrame(geometry=points, crs="EPSG:2154").to_crs("EPSG:4326")


# ── Saving ────────────────────────────────────────────────────────────────────

def _save_figure(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=2000, bbox_inches="tight")
    print(f"Map saved to {path}")