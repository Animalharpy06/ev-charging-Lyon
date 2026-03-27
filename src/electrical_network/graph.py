import networkx as nx
import geopandas as gpd
from shapely.geometry import Point

_SUBSTATION_NODE_TOLERANCE_M = 1.0


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

    _tag_substation_nodes(G, substations_proj)
    return G


def _tag_substation_nodes(G: nx.Graph, substations: gpd.GeoDataFrame) -> None:
    for node in G.nodes:
        pt             = Point(node)
        is_substation  = substations.geometry.distance(pt).min() <= _SUBSTATION_NODE_TOLERANCE_M
        G.nodes[node]["is_MV-LV_substation"] = is_substation


# ── Reporting ─────────────────────────────────────────────────────────────────

def report_graph_topology(G: nx.Graph, district_boundary: gpd.GeoDataFrame) -> None:
    components = list(nx.connected_components(G))

    substation_nodes = [n for n, d in G.nodes(data=True) if d.get("is_MV-LV_substation")]

    print(f"Nodes:                {G.number_of_nodes()}")
    print(f"Edges:                {G.number_of_edges()}")
    print(f"Connected components: {len(components)}")
    print(f"Substation nodes:     {len(substation_nodes)}")


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
