from pathlib import Path

import geopandas as gpd


def load_district(path: str) -> gpd.GeoDataFrame:
    return gpd.read_file(path).to_crs("EPSG:2154")


def save_district(district: gpd.GeoDataFrame, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    district.to_file(output_path, driver="GeoJSON")