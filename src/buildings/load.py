import geopandas as gpd
from pathlib import Path

def load_building_groups(path: str) -> gpd.GeoDataFrame:
    buildings = gpd.read_file(path, layer="batiment_groupe_compile")
    return buildings.to_crs("EPSG:2154")


def clip_to_district(buildings: gpd.GeoDataFrame, district_boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    clipped = gpd.sjoin(buildings, district_boundary[["geometry"]], how="inner", predicate="intersects").drop(columns="index_right")
    return clipped


def save_building_groups(buildings: gpd.GeoDataFrame, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    buildings.to_file(output_path, driver="GeoJSON")