import geopandas as gpd
from pathlib import Path
from shapely.geometry import Point, Polygon
from shapely.ops import linemerge, unary_union

SNAP_THRESHOLD_M = 20   # metres — endpoints closer than this are treated as touching
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
    # Keep lines with at least one endpoint inside the district.
    # Full geometry is preserved — lines are not cut at the boundary,
    # because boundary lines represent real feeders connecting to upstream nodes.
    boundary_polygon = district_boundary.geometry.iloc[0]
    has_endpoint_inside = lines.geometry.apply(lambda geom: _any_endpoint_inside(geom, boundary_polygon))
    return lines[has_endpoint_inside].copy()


def _any_endpoint_inside(line_geom, polygon) -> bool:
    start = Point(line_geom.coords[0])
    end   = Point(line_geom.coords[-1])
    return polygon.contains(start) or polygon.contains(end)


# ── Merging ───────────────────────────────────────────────────────────────────

def merge_line_segments(lines: gpd.GeoDataFrame,
                         substations: gpd.GeoDataFrame,
                         district_boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Iteratively merge line segments that share an endpoint not anchored to a
    substation. Raw Enedis data splits continuous feeders into many short
    segments — this reassembles them into single LineString objects.

    Stops when a full pass produces no new merges.
    """
    lines_proj        = lines.to_crs("EPSG:2154").copy()
    substations_proj  = substations.to_crs("EPSG:2154")
    polygon = district_boundary.to_crs("EPSG:2154").geometry.iloc[0]

    merged_in_pass = True
    while merged_in_pass:
        lines_proj, merged_in_pass = _merge_pass(lines_proj, substations_proj, polygon)

    return lines_proj.to_crs("EPSG:4326")


def _merge_pass(lines: gpd.GeoDataFrame,
                substations: gpd.GeoDataFrame,
                district_polygon: Polygon) -> tuple[gpd.GeoDataFrame, bool]:
    geometries = list(lines.geometry)
    used = [False] * len(geometries)
    merged_any = False

    # Pre-compute endpoints once, outside the inner loop
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
                geometries[i] = result
                starts[i] = Point(result.coords[0])
                ends[i]   = Point(result.coords[-1])
                used[j] = True
                merged_any = True
                break

    surviving = [g for g, d in zip(geometries, used) if not d]
    return gpd.GeoDataFrame(geometry=surviving, crs=lines.crs), merged_any


def _try_merge(geom_a, geom_b, start_a, end_a, start_b, end_b,
               substations, district_polygon) -> object:
    endpoint_pairs = [
        (end_a,   start_b),
        (end_a,   end_b),
        (start_a, start_b),
        (start_a, end_b),
    ]
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


# ── Classification ────────────────────────────────────────────────────────────

def classify_lines(lines: gpd.GeoDataFrame,
                   district_boundary: gpd.GeoDataFrame,
                   substations: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Labels each line as:
    - 'internal': both endpoints inside the district and connected to a substation
    - 'boundary': one endpoint outside the district (expected, upstream feeders)
    - 'orphan':   both endpoints inside but not connected to any substation
    """
    lines_proj       = lines.to_crs("EPSG:2154")
    substations_proj = substations.to_crs("EPSG:2154")
    polygon          = district_boundary.to_crs("EPSG:2154").geometry.iloc[0]

    categories = lines_proj.geometry.apply(lambda geom: _line_category(geom, polygon, substations_proj))
    lines = lines.copy()
    lines["category"] = categories.values
    return lines


def _line_category(geom, polygon, substations) -> str:
    start = Point(geom.coords[0])
    end   = Point(geom.coords[-1])

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
                           district_boundary: gpd.GeoDataFrame) -> None:
    lines_proj = lines.to_crs("EPSG:2154")
    substations_proj = substations.to_crs("EPSG:2154")
    polygon = district_boundary.to_crs("EPSG:2154").geometry.iloc[0]

    orphan_pts = [
        pt
        for geom in lines_proj.geometry
        for pt in [Point(geom.coords[0]), Point(geom.coords[-1])]
        if polygon.contains(pt)
        and substations_proj.geometry.distance(pt).min() > SNAP_THRESHOLD_M
    ]

    orphans = gpd.GeoDataFrame(geometry=orphan_pts, crs="EPSG:2154").to_crs("EPSG:4326")
    print(f"Orphan endpoints inside district: {len(orphans)} across {len(lines_proj)} lines")
    return orphans

# ── Saving ────────────────────────────────────────────────────────────────────

def save(gdf: gpd.GeoDataFrame, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output_path, driver="GeoJSON")


if __name__ == "__main__":
    from topology.district import load_district

    district          = load_district("data/topology/iris_lyon.geojson")
    district_boundary = district.dissolve()

    substations          = load_substations("data/electrical_network/enedis_nrj_energie.enedis_poste.json")
    substations_district = clip_substations_to_district(substations, district_boundary)
    save(substations_district, "cache/electrical_network/substations_district.geojson")
    print(f"Saved {len(substations_district)} substations")

    hta_lines          = load_hta_lines("data/electrical_network/enedis_nrj_energie.enedis_reseau.json")
    hta_lines_district = clip_lines_to_district(hta_lines, district_boundary)
    save(hta_lines_district, "cache/electrical_network/hta_lines_district.geojson")
    print(f"Saved {len(hta_lines_district)} HTA lines")
