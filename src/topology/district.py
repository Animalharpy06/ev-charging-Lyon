from pathlib import Path
from shapely import Point

import geopandas as gpd


def load_district(path: str) -> gpd.GeoDataFrame:
    return gpd.read_file(path).to_crs("EPSG:2154")


def save_district(district: gpd.GeoDataFrame, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    district.to_file(output_path, driver="GeoJSON")


def filter_iris_by_network_coverage(district: gpd.GeoDataFrame, main_component: set) -> gpd.GeoDataFrame:
    nodes_gdf = _component_nodes_to_geodataframe(main_component)
    covered_iris = gpd.sjoin(district, nodes_gdf[["geometry"]], how="inner", predicate="contains")["codeiris"].unique()
    return district[district["codeiris"].isin(covered_iris)].copy()


def _component_nodes_to_geodataframe(component: set) -> gpd.GeoDataFrame:
    points = [Point(x, y) for x, y in component]
    return gpd.GeoDataFrame(geometry=points, crs="EPSG:2154")