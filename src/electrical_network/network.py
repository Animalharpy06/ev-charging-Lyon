import geopandas as gpd
from pathlib import Path
from shapely.geometry import Point, Polygon
from shapely.ops import linemerge, unary_union

SNAP_THRESHOLD_M = 10
HTA_LINE_TYPE = "reseau-souterrain-hta"

# ── Loading ───────────────────────────────────────────────────────────────────

def load_substations(path: str) -> gpd.GeoDataFrame:
    return gpd.read_file(path)

def load_hta_lines(path: str) -> gpd.GeoDataFrame:
    lines = gpd.read_file(path)
    return lines[lines["type"] == HTA_LINE_TYPE].copy()

# ── Clipping ──────────────────────────────────────────────────────────────────

def clip_substations_to_district(substations: gpd.GeoDataFrame,
                                  district_boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    # Here we use district_boundary[["geometry"]] becasue we want a GeoDataFrame with only one column
    return (gpd.sjoin(substations, district_boundary[["geometry"]],how="inner", predicate="within").drop(columns="index_right"))

def clip_lines_to_district(lines: gpd.GeoDataFrame,
                            district_boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    # Full geometry preserved — lines are not cut at the boundary,
    # because boundary lines represent real feeders connecting to upstream nodes.

    # Here we use district_boundary.geometry becasue we don't need a GeoDataFrame with only one column, we can have a GeoSeries
    boundary_polygon = district_boundary.geometry.iloc[0]
    has_endpoint_inside = lines.geometry.apply(lambda line: _any_endpoint_inside(line, boundary_polygon))
    
    return lines[has_endpoint_inside].copy()

def _any_endpoint_inside(line_geom, polygon) -> bool:
    start, end = _endpoints(line_geom)
    return polygon.contains(start) or polygon.contains(end)

# ── Merging ───────────────────────────────────────────────────────────────────

def merge_line_segments(lines: gpd.GeoDataFrame,
                        substations: gpd.GeoDataFrame,
                        district_boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:

    # EPSG:2154 is a projected coordinate system (RGF93 / Lambert-93), while this data is stored in EPSG:4326 (WGS84 — latitude/longitude in degrees).
    # Spatial operations like distance, length, and area require coordinates in meters, not degrees.

    lines_proj       = lines.to_crs("EPSG:2154").copy()
    substations_proj = substations.to_crs("EPSG:2154")
    polygon          = district_boundary.to_crs("EPSG:2154").geometry.iloc[0]
    
    
    # Stops when a full pass produces no new merges.
    merged_in_pass = True
    while merged_in_pass:
        lines_proj, merged_in_pass = _merge_pass(lines_proj, substations_proj, polygon)

    return lines_proj.to_crs("EPSG:4326")

def _merge_pass(lines: gpd.GeoDataFrame,
                substations: gpd.GeoDataFrame,
                district_polygon: Polygon) -> tuple[gpd.GeoDataFrame, bool]:
    geometries = list(lines.geometry)
    used       = [False] * len(geometries)
    merged_any = False

    starts = [Point(geom.coords[0]) for geom in geometries]
    ends   = [Point(geom.coords[-1]) for geom in geometries]

    for i in range(len(geometries)):
        if used[i]:
            continue
        for j in range(i + 1, len(geometries)):
            if used[j]:
                continue
            result = _try_merge(geometries[i], geometries[j],
                                starts[i], ends[i],
                                starts[j], ends[j],
                                substations, district_polygon)
            if result is not None:
                # If the merge succeeded, replace line i with the new longer merged line.
                # Line i now represents the combination of the two.
                geometries[i] = result
                starts[i]     = Point(result.coords[0])
                ends[i]       = Point(result.coords[-1])
                used[j]       = True
                merged_any    = True
                # Line i has changed, so we need to restart the inner loop to try merging the new bigger line i with other candidates.
                break

    surviving = [g for g, discarded in zip(geometries, used) if not discarded]
    
    return gpd.GeoDataFrame(geometry=surviving, crs=lines.crs), merged_any

def _try_merge(geom_a, geom_b,
               start_a: Point, end_a: Point,
               start_b: Point, end_b: Point,
               substations: gpd.GeoDataFrame,
               district_polygon: Polygon) -> object:
    endpoint_pairs = [  (end_a,   start_b),
                        (end_a,   end_b),
                        (start_a, start_b),
                        (start_a, end_b),]
    
    for pt_a, pt_b in endpoint_pairs:
        if (pt_a.distance(pt_b) <= SNAP_THRESHOLD_M
                and district_polygon.contains(pt_a)
                and not _near_substation(pt_a, substations)):
            
            merged = linemerge(unary_union([geom_a, geom_b]))

            if merged.geom_type == "LineString":
                return merged
    return None

def _near_substation(point: Point, substations: gpd.GeoDataFrame) -> bool:
    return substations.geometry.distance(point).min() <= SNAP_THRESHOLD_M

def _endpoints(geom) -> tuple[Point, Point]:
    return Point(geom.coords[0]), Point(geom.coords[-1])

# ── Classification ────────────────────────────────────────────────────────────

def classify_lines(lines: gpd.GeoDataFrame,
                   district_boundary: gpd.GeoDataFrame,
                   substations: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    
    lines_proj       = lines.to_crs("EPSG:2154")
    substations_proj = substations.to_crs("EPSG:2154")
    polygon          = district_boundary.to_crs("EPSG:2154").geometry.iloc[0]

    categories = lines_proj.geometry.apply(lambda geom: _line_category(geom, polygon, substations_proj))

    lines = lines.copy()
    lines["category"] = categories.values
    return lines

def _line_category(geom, polygon, substations) -> str:
    start, end = _endpoints(geom)

    start_inside = polygon.contains(start)
    end_inside   = polygon.contains(end)

    if not (start_inside and end_inside):
        return "boundary"

    start_connected = substations.geometry.distance(start).min() <= SNAP_THRESHOLD_M
    end_connected   = substations.geometry.distance(end).min()   <= SNAP_THRESHOLD_M

    if not start_connected or not end_connected:
        return "orphan"
    return "internal"

# ── Validation ────────────────────────────────────────────────────────────────

def check_orphan_endpoints(lines: gpd.GeoDataFrame,
                           substations: gpd.GeoDataFrame,
                           district_boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    lines_proj       = lines.to_crs("EPSG:2154")
    substations_proj = substations.to_crs("EPSG:2154")
    polygon          = district_boundary.to_crs("EPSG:2154").geometry.iloc[0]

    orphan_pts = [
        point
        for geom in lines_proj.geometry
        for point in _endpoints(geom)
        if polygon.contains(point)
        and substations_proj.geometry.distance(point).min() > SNAP_THRESHOLD_M]

    orphans = gpd.GeoDataFrame(geometry=orphan_pts, crs="EPSG:2154").to_crs("EPSG:4326")
    print(f"Orphan endpoints inside district: {len(orphans)} across {len(lines_proj)} lines")

    return orphans

# ── Saving ────────────────────────────────────────────────────────────────────

def save(gdf: gpd.GeoDataFrame, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output_path, driver="GeoJSON")