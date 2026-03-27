import matplotlib.pyplot as plt
from pathlib import Path
import geopandas as gpd
import networkx as nx

from electrical_network.graph import graph_edges_to_geodataframe


def plot_network(district: gpd.GeoDataFrame,
                 district_boundary: gpd.GeoDataFrame,
                 G: nx.Graph,
                 substations: gpd.GeoDataFrame,
                 orphan_points: gpd.GeoDataFrame) -> None:
    fig, ax = plt.subplots(figsize=(12, 12))

    district.plot(ax=ax, color="lightyellow", edgecolor="gray", linewidth=0.5)
    district_boundary.plot(ax=ax, color="none", edgecolor="black", linewidth=1.5)

    _plot_hta_lines(ax, G)
    _plot_points(ax, substations, orphan_points)

    ax.set_title("Quartier 5 — HTA Network", fontsize=14)
    ax.legend()

    _save_figure("output/topology_check/network_map.png")


def _plot_hta_lines(ax, G: nx.Graph) -> None:
    internal = graph_edges_to_geodataframe(G, category="internal")
    boundary = graph_edges_to_geodataframe(G, category="boundary")
    orphan   = graph_edges_to_geodataframe(G, category="orphan")

    internal.plot(ax=ax, color="steelblue", linewidth=0.5, label=f"Internal HTA lines ({len(internal)})")
    boundary.plot(ax=ax, color="green",     linewidth=0.5, label=f"Boundary HTA lines ({len(boundary)})")

    if not orphan.empty:
        orphan.plot(ax=ax, color="gold", linewidth=0.1, label=f"Orphan lines ({len(orphan)})")


def _plot_points(ax, substations: gpd.GeoDataFrame, orphan_points: gpd.GeoDataFrame) -> None:
    substations.plot(ax=ax, color="red",    markersize=5,  label=f"Substations ({len(substations)})")
    orphan_points.plot(ax=ax, color="orange", marker="x", markersize=10,
                       linewidth=1, zorder=6, label=f"Orphan endpoints ({len(orphan_points)})")


def _save_figure(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=1000, bbox_inches="tight")
    print(f"Map saved to {path}")

