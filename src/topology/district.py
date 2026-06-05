import geopandas as gpd
from pathlib import Path


def load_district(path: str) -> gpd.GeoDataFrame:
    iris = gpd.read_file(path)
    return iris

#iris[iris["codeiris"].isin(DISTRICT_IRIS_CODES)].copy()

def save_district(district: gpd.GeoDataFrame, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    district.to_file(output_path, driver="GeoJSON")


if __name__ == "__main__":
    district = load_district("data/topology/iris_lyon.geojson")
    save_district(district, "cache/topology/district.geojson")
    print(f"Saved {len(district)} IRIS zones to cache/topology/district.geojson")
