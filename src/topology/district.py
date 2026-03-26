import geopandas as gpd
from pathlib import Path

DISTRICT_IRIS_CODES = [
    # 7e arrondissement
    693870501, 693870502, 693870503, 693870402, 693870403,
    # 8e arrondissement
    693880101, 693880102, 693880104, 693880105,
    693880202, 693880203, 693880204,
    693880301, 693880302, 693880303, 693880404,
    693880701, 693880702, 693880802, 693880901,
    # 3e arrondissement
    693830302, 693830401, 693830402, 693830403, 693830404, 693830405,
    693830501, 693830502, 693830601, 693830602, 693830603, 693830604,
    693830701, 693830702, 693830703, 693830801, 693830802, 693830901,
    # Villeurbanne
    692661205, 692661301, 692661302, 692661303,
    692661402, 692661501, 692661502, 692661503]


def load_district(path: str) -> gpd.GeoDataFrame:
    iris = gpd.read_file(path)
    return iris[iris["codeiris"].isin(DISTRICT_IRIS_CODES)].copy()


def save_district(district: gpd.GeoDataFrame, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    district.to_file(output_path, driver="GeoJSON")


if __name__ == "__main__":
    district = load_district("data/topology/iris_lyon.geojson")
    save_district(district, "cache/topology/district.geojson")
    print(f"Saved {len(district)} IRIS zones to cache/topology/district.geojson")
