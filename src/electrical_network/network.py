import pandas as pd
import geopandas as gpd
from pathlib import Path
from shapely.geometry import Point, Polygon, LineString
from shapely.strtree import STRtree

SNAP_THRESHOLD_SUBSTATION_M = 5   
SNAP_THRESHOLD_JUNCTION_M   = 20  
HTA_LINE_TYPE    = "reseau-souterrain-hta"


# ── Loading ───────────────────────────────────────────────────────────────────

def load_substations(path: str) -> gpd.GeoDataFrame:
    return gpd.read_file(path)


def load_hta_lines(path: str) -> gpd.GeoDataFrame:
    lines = gpd.read_file(path)
    return lines[lines["type"] == HTA_LINE_TYPE].copy()


# ── Clipping ──────────────────────────────────────────────────────────────────

def clip_substations_to_district(substations: gpd.GeoDataFrame,
                                  district_boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return (gpd.sjoin(substations, district_boundary[["geometry"]],
                      how="inner", predicate="within")
              .drop(columns="index_right"))


def clip_lines_to_district(lines: gpd.GeoDataFrame,
                            district_boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    # Full geometry preserved — lines are not cut at the boundary,
    # because boundary lines represent real feeders connecting to upstream nodes.
    boundary_polygon = district_boundary.geometry.iloc[0]
    has_endpoint_inside = lines.geometry.apply(
        lambda line: _any_endpoint_inside(line, boundary_polygon)
    )
    return lines[has_endpoint_inside].copy()


def _any_endpoint_inside(line_geom, polygon: Polygon) -> bool:
    start, end = _endpoints(line_geom)
    return polygon.contains(start) or polygon.contains(end)


# ── Endpoint snapping ─────────────────────────────────────────────────────────

def build_endpoint_snapping(
    lines: gpd.GeoDataFrame,
    substations: gpd.GeoDataFrame,
    district_boundary: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, dict, gpd.GeoDataFrame, gpd.GeoDataFrame]:

    lines_proj       = lines.to_crs("EPSG:2154")
    substations_proj = substations.to_crs("EPSG:2154")
    polygon          = district_boundary.to_crs("EPSG:2154").geometry.iloc[0]


    # Phase 1 — identify orphans and split host lines at T-junctions
    inside_endpoints     = _collect_inside_endpoints(lines_proj, polygon)
    _, unsnapped         = _snap_to_substations(inside_endpoints, substations_proj)
    _, orphan_keys_dict  = _cluster_unsnapped(unsnapped, substations_proj)

    orphan_pts  = list(orphan_keys_dict.values())
    orphan_keys = list(orphan_keys_dict.keys())

    _, lines_proj = _snap_to_line_interiors(orphan_pts, orphan_keys, lines_proj)

    # Phase 2 — rebuild endpoint_nodes fresh on updated lines
    lines_proj               = lines_proj.reset_index(drop=True)
    inside_endpoints         = _collect_inside_endpoints(lines_proj, polygon)
    endpoint_nodes, unsnapped = _snap_to_substations(inside_endpoints, substations_proj)
    junction_keys, final_orphans_dict = _cluster_unsnapped(unsnapped, substations_proj)
    endpoint_nodes.update(junction_keys)
    
    junction_nodes = _to_geodataframe([Point(xy) for xy in set(junction_keys.values())], crs="EPSG:2154").to_crs("EPSG:4326")

    orphan_points = _to_geodataframe(list(final_orphans_dict.values()), crs="EPSG:2154").to_crs("EPSG:4326")


    return lines_proj.to_crs("EPSG:4326"), endpoint_nodes, junction_nodes, orphan_points



def _collect_inside_endpoints(
    lines: gpd.GeoDataFrame,
    polygon: Polygon,) -> list[tuple[int, str, Point]]:

    result = []
    for idx, geom in lines.geometry.items():
        start, end = _endpoints(geom)
        if polygon.contains(start):
            result.append((idx, "start", start))
        if polygon.contains(end):
            result.append((idx, "end", end))
    return result


def _snap_to_substations(
    inside_endpoints: list[tuple[int, str, Point]],
    substations_proj: gpd.GeoDataFrame) -> tuple[dict, list[tuple[int, str, Point]]]:

    substation_tree = STRtree(substations_proj.geometry)
    endpoint_nodes  = {}
    unsnapped       = []

    for line_idx, side, point in inside_endpoints:
        nearest_idx = substation_tree.nearest(point)
        nearest_pt  = substations_proj.geometry.iloc[nearest_idx]
        candidate_key = _round_coords(nearest_pt)
        

        if point.distance(nearest_pt) <= SNAP_THRESHOLD_SUBSTATION_M and not _already_snapped_to_same_node(line_idx, side, candidate_key, endpoint_nodes):
            endpoint_nodes[(line_idx, side)] = _round_coords(nearest_pt)
        else:
            unsnapped.append((line_idx, side, point))

    return endpoint_nodes, unsnapped

def _snap_to_line_interiors(
    orphan_pts: list[Point],
    orphan_keys: list[tuple[int, str]],
    lines_proj: gpd.GeoDataFrame,) -> tuple[dict, gpd.GeoDataFrame]:
    """
    For each orphan point, check if it lies within SNAP_THRESHOLD_M of the
    interior of any line. If so, split that line at the nearest point and
    assign the orphan a junction node key at the split location.

    # We only check line interiors here — endpoint-to-endpoint proximity
    # was already handled by _cluster_unsnapped.
    """
    line_tree = STRtree(lines_proj.geometry)
    resolved_keys = {}
    split_records = []
    split_indices = set()

    for key, orphan_pt in zip(orphan_keys, orphan_pts):
        candidate_idxs = line_tree.query(orphan_pt.buffer(SNAP_THRESHOLD_JUNCTION_M))

        for line_pos_idx in candidate_idxs:
            line_idx = lines_proj.index[line_pos_idx]
            line_geom = lines_proj.geometry.iloc[line_pos_idx]

            nearest_pt = line_geom.interpolate(line_geom.project(orphan_pt))

            if orphan_pt.distance(nearest_pt) > SNAP_THRESHOLD_JUNCTION_M:
                continue
            if _is_endpoint(nearest_pt, line_geom):
                continue  # endpoint proximity already handled

            node_key = _round_coords(nearest_pt)
            resolved_keys[key] = node_key

            seg_a, seg_b = _split_line(line_geom, nearest_pt)
            split_records.append(seg_a)
            split_records.append(seg_b)
            split_indices.add(line_idx)
            break

    surviving = lines_proj[~lines_proj.index.isin(split_indices)]
    new_segments = gpd.GeoDataFrame(geometry=split_records, crs=lines_proj.crs)
    updated_lines = gpd.GeoDataFrame(pd.concat([surviving[["geometry"]], new_segments], ignore_index=True),crs=lines_proj.crs)

    return resolved_keys, updated_lines


def _is_endpoint(point: Point, line_geom) -> bool:
    start, end = _endpoints(line_geom)
    return point.distance(start) < 1.0 or point.distance(end) < 1.0


def _split_line(line_geom, split_point: Point) -> tuple:
    distance = line_geom.project(split_point)
    coords = list(line_geom.coords)

    # Find insertion position along the coordinate sequence
    accumulated = 0.0
    insert_pos = len(coords) - 1
    for i in range(len(coords) - 1):
        segment_len = Point(coords[i]).distance(Point(coords[i + 1]))
        if accumulated + segment_len >= distance:
            insert_pos = i + 1
            break
        accumulated += segment_len

    split_coord = (split_point.x, split_point.y)
    seg_a = LineString(coords[:insert_pos] + [split_coord])
    seg_b = LineString([split_coord] + coords[insert_pos:])
    return seg_a, seg_b

def _already_snapped_to_same_node(
    line_idx: int,
    side: str,
    candidate_key: tuple[float, float],
    endpoint_nodes: dict,) -> bool:
    other_side = "end" if side == "start" else "start"
    return endpoint_nodes.get((line_idx, other_side)) == candidate_key

def _cluster_unsnapped(
    unsnapped: list[tuple[int, str, Point]],
    substations_proj: gpd.GeoDataFrame,) -> tuple[dict, dict]:
    substation_tree = STRtree(substations_proj.geometry)
    filtered = [(line_idx, side, pt) for line_idx, side, pt in unsnapped if not _near_substation(pt, substation_tree)]

    keys   = [(line_idx, side) for line_idx, side, _ in filtered]
    points = [pt for _, _, pt in filtered]                           
    n      = len(points)
    parent = list(range(n))

    if n > 0:
        tree = STRtree(points)
        for i, pt in enumerate(points):
            for j in tree.query(pt.buffer(SNAP_THRESHOLD_JUNCTION_M)):
                if i != j:
                    _union(parent, i, j)
    """
    points = [A, B, C, D]   (indices 0, 1, 2, 3)
    parent = [0, 1, 2, 3]   (each point is its own cluster)
    SNAP_THRESHOLD_M = 20

    A is 10m from B   → should cluster
    B is 15m from C   → should cluster  
    D is 100m from all others → isolated
    Walking through the example:

    i=0, pt=A: buffer finds B (10m away) → _union(parent, 0, 1) → parent = [1, 1, 2, 3]

    i=1, pt=B: buffer finds A and C → _union(parent, 1, 0) (no change, already same cluster) → _union(parent, 1, 2) → parent = [1, 2, 2, 3]

    i=2, pt=C: buffer finds B → _union(parent, 2, 1) (no change) → parent = [1, 2, 2, 3]

    i=3, pt=D: buffer finds nothing → no unions

    Final parent = [1, 2, 2, 3]
    """

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(_find(parent,i), []).append(i)

    """
    i=0: _find(parent, 0) → parent[0]=1, parent[1]=2, parent[2]=2 ✓ → root=2 → clusters = {2: [0]}

    i=1: _find(parent, 1) → parent[1]=2, parent[2]=2 ✓ → root=2 → clusters = {2: [0, 1]}

    i=2: _find(parent, 2) → parent[2]=2 ✓ → root=2 → clusters = {2: [0, 1, 2]}

    i=3: _find(parent, 3) → parent[3]=3 ✓ → root=3 → clusters = {2: [0, 1, 2], 3: [3]}
    """

    junction_keys = {}
    orphan_keys_out = {}
    for members in clusters.values():
        if len(members) >= 2:
            centroid = _centroid_of_points([points[i] for i in members])
            node_key = _round_coords(centroid)
            for i in members:
                junction_keys[keys[i]] = node_key
        else:
            i = members[0]
            orphan_keys_out[keys[i]] = points[i]

    return junction_keys, orphan_keys_out


# ── Classification ────────────────────────────────────────────────────────────

def classify_lines(
    lines: gpd.GeoDataFrame,
    endpoint_nodes: dict[tuple[int, str], tuple[float, float]],
    district_boundary: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    
    """
    Classify each line using endpoint_nodes as the single source of truth:
      - boundary : at least one endpoint outside the district
      - internal : both endpoints inside and both resolved to a node
      - orphan   : both endpoints inside but at least one could not be resolved
    """
    lines_proj = lines.to_crs("EPSG:2154")
    polygon    = district_boundary.to_crs("EPSG:2154").geometry.iloc[0]

    categories = [
        _line_category(idx, geom, endpoint_nodes, polygon)
        for idx, geom in lines_proj.geometry.items()
    ]

    lines = lines.copy()
    lines["category"] = categories
    return lines


def _line_category(
    idx: int,
    geom,
    endpoint_nodes: dict,
    polygon: Polygon,
) -> str:
    start, end   = _endpoints(geom)
    start_inside = polygon.contains(start)
    end_inside   = polygon.contains(end)

    if not (start_inside and end_inside):
        return "boundary"
    if (idx, "start") in endpoint_nodes and (idx, "end") in endpoint_nodes:
        return "internal"
    return "orphan"


# ── Validation ────────────────────────────────────────────────────────────────

def check_orphan_endpoints(
    lines: gpd.GeoDataFrame,
    substations: gpd.GeoDataFrame,
    district_boundary: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    _, _, orphan_points = build_endpoint_snapping(lines, substations, district_boundary)
    print(f"Orphan endpoints inside district: {len(orphan_points)}")
    return orphan_points


# ── Saving ────────────────────────────────────────────────────────────────────

def save(gdf: gpd.GeoDataFrame, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output_path, driver="GeoJSON")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _endpoints(geom) -> tuple[Point, Point]:
    return Point(geom.coords[0]), Point(geom.coords[-1])


def _round_coords(point: Point) -> tuple[float, float]:
    return (round(point.x, 0), round(point.y, 0))


def _centroid_of_points(points: list[Point]) -> Point:
    x = sum(p.x for p in points) / len(points)
    y = sum(p.y for p in points) / len(points)
    return Point(x, y)


def _to_geodataframe(points: list[Point], crs: str) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(geometry=points, crs=crs)

def _near_substation(point: Point, substation_tree: STRtree) -> bool:
    nearest_idx = substation_tree.nearest(point)
    nearest_pt  = substation_tree.geometries[nearest_idx]
    return point.distance(nearest_pt) <= SNAP_THRESHOLD_SUBSTATION_M

def _find(parent: list[int], i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i

def _union(parent: list[int], i: int, j: int) -> None:
    parent[_find(parent, i)] = _find(parent, j)
