import networkx as nx
import geopandas as gpd
from shapely.geometry import Point

_SUBSTATION_NODE_TOLERANCE_M = 1.0
_HV_MV_CABIN_DEGREE_THRESHOLD = 10


# ── Building ──────────────────────────────────────────────────────────────────

def build_graph_from_snapping(
    lines: gpd.GeoDataFrame,
    endpoint_nodes: dict[tuple[int, str], tuple[float, float]],
    substations: gpd.GeoDataFrame,
) -> nx.Graph:
    
    lines_proj       = lines.to_crs("EPSG:2154")
    substations_proj = substations.to_crs("EPSG:2154")

    G = nx.Graph()
    for idx, row in lines_proj.iterrows():
        start_key = endpoint_nodes.get((idx, "start"))
        end_key   = endpoint_nodes.get((idx, "end"))

        if start_key is None or end_key is None:
            continue
        if start_key == end_key:
            continue

        category = row.get("category", "unknown")
        G.add_edge(start_key, end_key, geometry=row.geometry, category=category)

    _tag_nodes(G, substations_proj)
    
    G = _drop_unconnected_islands(G)

    return G


def _tag_nodes(G: nx.Graph, substations: gpd.GeoDataFrame) -> None:
    for node in G.nodes:

        pt             = Point(node)
        G.nodes[node]["is_MV-LV_substation"] = substations.geometry.distance(pt).min() <= _SUBSTATION_NODE_TOLERANCE_M
        G.nodes[node]["is_HV-MV_cabin"]      = G.degree(node) >= _HV_MV_CABIN_DEGREE_THRESHOLD
        G.nodes[node]["is_junction"]          = (
            not G.nodes[node]["is_MV-LV_substation"]
            and not G.nodes[node]["is_HV-MV_cabin"]
            and G.degree(node) >= 2)

def _drop_unconnected_islands(G: nx.Graph) -> nx.Graph:
    safe_nodes = {
        node
        for component in nx.connected_components(G)
        if _component_has_hv_mv_cabin(G, component)
        for node in component
    }
    return G.subgraph(safe_nodes).copy()

def _component_has_hv_mv_cabin(G: nx.Graph, component: set) -> bool:
    return any(G.nodes[node]["is_HV-MV_cabin"] for node in component)


# ── Reporting ─────────────────────────────────────────────────────────────────

def report_graph_topology(G: nx.Graph, district_boundary: gpd.GeoDataFrame) -> None:
    components = list(nx.connected_components(G))

    MV_LV_substations = [n for n, d in G.nodes(data=True) if d.get("is_MV-LV_substation")]
    HV_MV_substations = [n for n, d in G.nodes(data=True) if d.get("is_HV-MV_cabin")]

    print(f"Nodes:                {G.number_of_nodes()}")
    print(f"Edges:                {G.number_of_edges()}")
    print(f"Connected components: {len(components)}")
    print(f"MV/LV Substations:     {len(MV_LV_substations)}")
    print(f"HV/MV Substations:     {len(HV_MV_substations)}")


# ── Export ────────────────────────────────────────────────────────────────────

def graph_edges_to_geodataframe(
    G: nx.Graph,
    category: str = None,
) -> gpd.GeoDataFrame:
    edges = [
        data["geometry"]
        for _, _, data in G.edges(data=True)
        if "geometry" in data
        and (category is None or data.get("category") == category)]
    
    return gpd.GeoDataFrame(geometry=edges, crs="EPSG:2154").to_crs("EPSG:4326")
