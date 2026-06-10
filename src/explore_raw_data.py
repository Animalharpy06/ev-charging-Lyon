from pathlib import Path
import json

import geopandas as gpd
import pandas as pd


_BUILDING_LAYER_CANDIDATES = [
    "batiment_groupe",
    "batiment_construction",
    "batiment_groupe_geom",
    "batiment_construction_geom"]

_USEFUL_COLUMN_KEYWORDS = [
    "id",
    "rnb",
    "adresse",
    "geo",
    "usage",
    "log",
    "surface",
    "hauteur",
    "chauff",
    "dpe",
    "energie",
    "construction",
    "annee"]

def explore_referentiel_administratif(gpkg_path: str = "data/buildings/referentiel_administratif.gpkg") -> None:
    layers = list_layers(Path(gpkg_path))
    print("\n══ REFERENTIEL ADMINISTRATIF — LAYERS ══")
    for layer in layers:
        gdf = gpd.read_file(gpkg_path, layer=layer)
        print(f"  {layer:<40} rows={len(gdf):<8} cols={len(gdf.columns):<5} crs={gdf.crs}")

def analyze_bdnb_gpkg(gpkg_path: str,
                      district_path: str | None = None,
                      output_dir: str = "output/bdnb_audit") -> None:
    gpkg = Path(gpkg_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    layers = list_layers(gpkg)
    save_layers_summary(layers, out / "layers_summary.csv")

    layer_reports = [analyze_layer(gpkg, layer_name) for layer_name in layers]
    save_layer_reports(layer_reports, out / "layer_details.csv")

    building_layer = choose_building_layer(layers)
    if building_layer is None:
        print("No standard BDNB building layer found.")
        print("Check output/bdnb_audit/layers_summary.csv and choose the correct layer manually.")
        return

    buildings = load_layer(gpkg, building_layer)
    save_building_schema(buildings, out / "building_schema.csv")
    save_useful_columns(buildings, out / "building_useful_columns.csv")

    print_basic_building_stats(buildings, building_layer)

    if district_path is not None:
        district = gpd.read_file(district_path)
        clipped = clip_to_district(buildings, district)
        save_clipped_summary(clipped, out / "district_building_summary.json")
        save_clipped_sample(clipped, out / "district_building_sample.geojson")
        print_district_stats(clipped)


def list_layers(gpkg_path: Path) -> list[str]:
    layers = gpd.list_layers(gpkg_path)
    return layers["name"].tolist()


def save_layers_summary(layers: list[str], output_path: Path) -> None:
    pd.DataFrame({"layer_name": layers}).to_csv(output_path, index=False)


def analyze_layer(gpkg_path: Path, layer_name: str) -> dict:
    layer = gpd.read_file(gpkg_path, layer=layer_name)

    is_geospatial = isinstance(layer, gpd.GeoDataFrame) and "geometry" in layer.columns

    return {
        "layer_name": layer_name,
        "rows": len(layer),
        "columns": len(layer.columns),
        "is_geospatial": is_geospatial,
        "crs": str(layer.crs) if is_geospatial else "",
        "geometry_types": geometry_type_summary(layer) if is_geospatial else "",
    }


def load_layer(gpkg_path: Path, layer_name: str) -> gpd.GeoDataFrame:
    return gpd.read_file(gpkg_path, layer=layer_name)


def geometry_type_summary(layer: pd.DataFrame) -> str:
    if not isinstance(layer, gpd.GeoDataFrame):
        return ""
    if "geometry" not in layer.columns:
        return ""
    return json.dumps(layer.geom_type.value_counts(dropna=False).to_dict(), ensure_ascii=False)


def save_layer_reports(reports: list[dict], output_path: Path) -> None:
    pd.DataFrame(reports).to_csv(output_path, index=False)


def choose_building_layer(layers: list[str]) -> str | None:
    lower_to_original = {layer.lower(): layer for layer in layers}

    for candidate in _BUILDING_LAYER_CANDIDATES:
        if candidate in lower_to_original:
            return lower_to_original[candidate]

    for layer in layers:
        if "batiment" in layer.lower():
            return layer

    return None


def save_building_schema(buildings: gpd.GeoDataFrame, output_path: Path) -> None:
    schema = pd.DataFrame({
        "column": buildings.columns,
        "dtype": [str(buildings[col].dtype) for col in buildings.columns],
        "non_null_count": [int(buildings[col].notna().sum()) for col in buildings.columns],
        "null_count": [int(buildings[col].isna().sum()) for col in buildings.columns],
        "n_unique": [safe_nunique(buildings[col]) for col in buildings.columns],
    })
    schema.to_csv(output_path, index=False)


def safe_nunique(series: pd.Series) -> int | None:
    try:
        return int(series.nunique(dropna=True))
    except TypeError:
        return None


def save_useful_columns(buildings: gpd.GeoDataFrame, output_path: Path) -> None:
    useful = [
        col for col in buildings.columns
        if any(keyword in col.lower() for keyword in _USEFUL_COLUMN_KEYWORDS)
    ]
    pd.DataFrame({"column": useful}).to_csv(output_path, index=False)


def print_basic_building_stats(buildings: gpd.GeoDataFrame, layer_name: str) -> None:
    print(f"Building layer:       {layer_name}")
    print(f"Rows:                 {len(buildings)}")
    print(f"Columns:              {len(buildings.columns)}")
    print(f"CRS:                  {buildings.crs if isinstance(buildings, gpd.GeoDataFrame) else 'N/A'}")

    if isinstance(buildings, gpd.GeoDataFrame) and "geometry" in buildings.columns:
        print(f"Geometry types:       {buildings.geom_type.value_counts(dropna=False).to_dict()}")
        print(f"Valid geometries:     {int(buildings.geometry.is_valid.sum())}")
        print(f"Invalid geometries:   {int((~buildings.geometry.is_valid).sum())}")


def clip_to_district(buildings: gpd.GeoDataFrame,
                     district: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if buildings.crs != district.crs:
        district = district.to_crs(buildings.crs)

    # We use intersects rather than within to avoid dropping buildings that touch
    # the study boundary exactly; boundary cases matter for later building-to-node assignment.
    clipped = gpd.sjoin(buildings, district[["geometry"]], how="inner", predicate="intersects").drop(columns="index_right")

    return clipped[~clipped.index.duplicated(keep="first")].copy()


def save_clipped_summary(clipped: gpd.GeoDataFrame, output_path: Path) -> None:
    summary = {
        "rows": int(len(clipped)),
        "columns": int(len(clipped.columns)),
        "crs": str(clipped.crs),
        "geometry_types": clipped.geom_type.value_counts(dropna=False).to_dict(),
        "valid_geometries": int(clipped.geometry.is_valid.sum()),
        "invalid_geometries": int((~clipped.geometry.is_valid).sum())}
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def save_clipped_sample(clipped: gpd.GeoDataFrame, output_path: Path, n: int = 2000) -> None:
    sample = clipped.head(n).copy()
    sample.to_file(output_path, driver="GeoJSON")


def print_district_stats(clipped: gpd.GeoDataFrame) -> None:
    print("")
    print("District subset")
    print(f"Rows:                 {len(clipped)}")
    print(f"Geometry types:       {clipped.geom_type.value_counts(dropna=False).to_dict()}")
    print(f"Valid geometries:     {int(clipped.geometry.is_valid.sum())}")
    print(f"Invalid geometries:   {int((~clipped.geometry.is_valid).sum())}")

def explore_iris_district(path: str = "data/topology/iris_lyon.geojson") -> None:
    iris = gpd.read_file(path)
    print("\n══ IRIS DISTRICT ══")
    print(f"Rows:    {len(iris)}")
    print(f"CRS:     {iris.crs}")
    print(f"Columns: {iris.columns.tolist()}")
    print(f"\nFirst 5 rows:")
    print(iris.drop(columns="geometry").head())

def explore_bdnb_iris(path: str = "data/buildings/referentiel_administratif.gpkg") -> None:
    iris = gpd.read_file(path, layer="iris")
    print(iris.columns.tolist())
    print(iris.head(3).drop(columns="geometry"))


if __name__ == "__main__":
    #analyze_bdnb_gpkg(gpkg_path="data/buildings/bdnb.gpkg", district_path="cache/topology/district.geojson", output_dir="output/bdnb_audit")
    #explore_referentiel_administratif()
    explore_iris_district()
    explore_bdnb_iris()