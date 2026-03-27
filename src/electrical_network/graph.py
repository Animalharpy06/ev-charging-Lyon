import networkx as nx
import geopandas as gpd
from shapely.geometry import Point

from electrical_network.network import SNAP_THRESHOLD_M

# ── Building ──────────────────────────────────────────────────────────────────

def build_graph(lines: gpd.GeoDataFrame,
                substations: gpd.GeoDataFrame) -> nx.Graph:
    lines_proj = lines.to_crs("EPSG:2154")
    substations_proj = substations.to_crs("EPSG:2154")

    G = _build_edges_from_lines(lines_proj, substations_proj)
    _tag_substation_nodes(G, substations_proj)
    return G


def _build_edges_from_lines(lines_proj: gpd.GeoDataFrame,
                            substations_proj: gpd.GeoDataFrame) -> nx.Graph:
    G = nx.Graph()
    for _, row in lines_proj.iterrows():
        start_point = Point(row.geometry.coords[0])
        end_point   = Point(row.geometry.coords[-1])

        start = _snap_to_node(start_point, substations_proj)
        end   = _snap_to_node(end_point, substations_proj)

        category = row.get("category", "unknown")
        G.add_edge(start, end, geometry=row.geometry, category=category)
    return G

def _snap_to_node(point: Point, substations: gpd.GeoDataFrame) -> tuple:
    # Snap to the nearest substation if within threshold,
    # otherwise use rounded coordinates as the node key.
    distances = substations.geometry.distance(point)
    nearest_idx = distances.idxmin()

    if distances[nearest_idx] <= SNAP_THRESHOLD_M:
        nearest = substations.geometry[nearest_idx]
        return (round(nearest.x, 4), round(nearest.y, 4))
    return (round(point.x, 4), round(point.y, 4))

def _tag_substation_nodes(G: nx.Graph, substations: gpd.GeoDataFrame) -> None:
    for node in G.nodes:
        pt = Point(node)
        is_substation = substations.geometry.distance(pt).min() <= SNAP_THRESHOLD_M
        G.nodes[node]["is_MV-LV_substation"] = is_substation


# ── Pruning ───────────────────────────────────────────────────────────────────

def drop_unconnected_islands(G: nx.Graph) -> nx.Graph:
    # Keep only components that contain at least one substation node.
    # Components with no substation have no slack bus and cannot be modelled.
    safe_nodes = {
        node
        for component in nx.connected_components(G)
        if _component_has_substation(G, component)
        for node in component
    }
    return G.subgraph(safe_nodes).copy()

def _component_has_substation(G: nx.Graph, component: set) -> bool:
    return any(G.nodes[node]["is_MV-LV_substation"] for node in component)

# ── Reporting ─────────────────────────────────────────────────────────────────

def report_graph_topology(G: nx.Graph, district_boundary: gpd.GeoDataFrame) -> None:
    polygon = district_boundary.to_crs("EPSG:2154").geometry.iloc[0]

    components       = list(nx.connected_components(G))
    substation_nodes = [n for n, d in G.nodes(data=True) if d.get("is_MV-LV_substation")]
    orphan_nodes     = [n for n, d in G.nodes(data=True)
                        if not d.get("is_MV-LV_substation")
                        and G.degree(n) == 1
                        and polygon.contains(Point(n))]
    islands          = [c for c in components if not _component_has_substation(G, c)]
    
    print(f"Nodes:              {G.number_of_nodes()}")
    print(f"Edges:              {G.number_of_edges()}")
    print(f"Connected components: {len(components)}")
    print(f"Substation nodes:   {len(substation_nodes)}")
    print(f"Orphan endpoints:   {len(orphan_nodes)}")
    print(f"Islands: {len(islands)} "f"({sum(len(c) for c in islands)} nodes total)")

# ── Export ────────────────────────────────────────────────────────────────────

def graph_edges_to_geodataframe(G: nx.Graph,
                                category: str = None) -> gpd.GeoDataFrame:
    edges = [
        data["geometry"]
        for _, _, data in G.edges(data=True)
        if "geometry" in data
        and (category is None or data.get("category") == category)]
    
    return gpd.GeoDataFrame(geometry=edges, crs="EPSG:2154").to_crs("EPSG:4326")