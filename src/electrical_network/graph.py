import networkx as nx
import geopandas as gpd
from shapely.geometry import Point


_HV_MV_CABIN_DEGREE_THRESHOLD = 10
MV_LV_SUBSTATIONS = "MV-LV_substation"
HV_MV_CABIN = "HV-MV_cabin"
JUNCTION = "Junction"
EXTERNAL_BOUNDARY  = "external_boundary_node"



# ── Building ──────────────────────────────────────────────────────────────────

def build_graph_from_snapping(lines: gpd.GeoDataFrame,
                              endpoint_nodes: dict,
                              substation_nodes_keys: set,
                              junction_nodes_keys: set,
                              substations: gpd.GeoDataFrame,
                              external_nodes_coord: set) -> nx.Graph:
    
    lines_proj = lines.to_crs("EPSG:2154")
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

    _tag_nodes(G, substation_nodes_keys, junction_nodes_keys, external_nodes_coord)
    
    return G


def _tag_nodes(G: nx.Graph, 
               substation_nodes_coord: set,
               junction_nodes_coord: set,
               external_nodes_coord:set) -> None:
    
    for node in G.nodes:
        is_sub = node in substation_nodes_coord
        is_junc = node in junction_nodes_coord
        is_hv_mv = is_junc and G.degree(node) >= _HV_MV_CABIN_DEGREE_THRESHOLD
        is_ext = node in external_nodes_coord

        G.nodes[node][MV_LV_SUBSTATIONS] = is_sub and not is_hv_mv
        G.nodes[node][HV_MV_CABIN] = is_hv_mv
        G.nodes[node][JUNCTION] = is_junc
        G.nodes[node][EXTERNAL_BOUNDARY] = is_ext



# ── Reporting ─────────────────────────────────────────────────────────────────

def report_graph_topology(G: nx.Graph) -> None:

    components = list(nx.connected_components(G))

    MV_LV_substations = [n for n, d in G.nodes(data=True) if d.get(MV_LV_SUBSTATIONS)]
    HV_MV_substations = [n for n, d in G.nodes(data=True) if d.get(HV_MV_CABIN)]

    print(f"Nodes:                {G.number_of_nodes()}")
    print(f"Edges:                {G.number_of_edges()}")
    print(f"Connected components: {len(components)}")
    print(f"MV/LV Substations:    {len(MV_LV_substations)}")
    print(f"HV/MV Substations:    {len(HV_MV_substations)}")



# ── Export ────────────────────────────────────────────────────────────────────

def graph_edges_to_geodataframe(G: nx.Graph, category: str) -> gpd.GeoDataFrame:
    
    edges = [data["geometry"] for _, _, data in G.edges(data=True) if "geometry" in data and (category is None or data.get("category") == category)]
    
    return gpd.GeoDataFrame(geometry=edges, crs="EPSG:2154").to_crs("EPSG:4326")
