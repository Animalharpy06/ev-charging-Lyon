from __future__ import annotations

import json
from pathlib import Path
import geopandas as gpd
import pandas as pd


_BUILDING_LAYER_CANDIDATES = ["batiment_construction", "batiment_groupe_compile"]

_COLUMNS_TO_AUDIT = [
    "bdtopo_bat_l_usage_1",
    "bdtopo_bat_l_usage_2",
    "bdtopo_bat_l_nature",
    "usage_principal_bdnb_open",
    "ffo_bat_usage_niveau_1_txt",
    "ffo_bat_annee_construction",
    "dpe_mix_arrete_annee_construction_dpe",
    "rnc_l_annee_construction",
    "rpls_l_annee_construction",
    "dpe_mix_arrete_periode_construction_dpe",
    "rnc_periode_construction_max"]


def audit_classification_columns(gpkg_path: str,
                                 output_dir: str = "output/bdnb_audit",
                                 layer_name: str = "batiment_groupe_compile") -> None:

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    layer = gpd.read_file(gpkg_path, layer=layer_name, ignore_geometry=True)

    available = [c for c in _COLUMNS_TO_AUDIT if c in layer.columns]
    missing = sorted(set(_COLUMNS_TO_AUDIT) - set(available))

    if missing:
        print(f"[WARN] Colonne non trovate nel layer: {missing}")

    rows = []
    for column in available:
        unique_values = _extract_unique_values(layer[column])
        for value in unique_values:
            rows.append({"column": column, "value": value})

    output_path = output / f"{layer_name}__unique_classification_values.csv"
    pd.DataFrame(rows).to_csv(output_path, index=False)
    print(f"[OK] Salvati {len(rows)} valori unici in: {output_path}")


def _extract_unique_values(series: pd.Series) -> list[str]:
    non_null = series.dropna()

    try:
        unique_raw = sorted(pd.unique(non_null).tolist(), key=str)
    except TypeError:
        unique_raw = pd.unique(non_null).tolist()

    return [str(v) for v in unique_raw]

def explore_package(
    gpkg_path: str,
    district_path: str | None = None,
    output_dir: str = "output/bdnb_audit") -> None:

    gpkg = Path(gpkg_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    layer_names = list_layer_names(gpkg)
    layer_profiles = [profile_layer(gpkg, layer_name) for layer_name in layer_names]

    save_layer_inventory(layer_profiles, output / "layers_summary.csv")
    save_column_inventory(layer_profiles, output / "columns_summary.csv")

    building_candidates = select_candidate_building_layers(layer_profiles)
    save_building_candidates(building_candidates, output / "building_layer_candidates.csv")

    for layer_name in building_candidates:
        layer = load_layer(gpkg, layer_name)
        save_layer_schema(layer, output / f"{layer_name}__schema.csv")
        save_layer_sample(layer, output / f"{layer_name}__sample.csv")

        if district_path is not None and is_geospatial(layer):
            district = load_district(district_path, layer.crs)
            clipped = clip_layer_to_district(layer, district)
            save_clipped_summary(clipped, output / f"{layer_name}__district_summary.json")
            save_clipped_sample(clipped, output / f"{layer_name}__district_sample.geojson")


def list_layer_names(gpkg_path: Path) -> list[str]:
    layers = gpd.list_layers(gpkg_path)
    return layers["name"].tolist()


def profile_layer(gpkg_path: Path, layer_name: str) -> dict:
    layer = load_layer(gpkg_path, layer_name)
    geometry_types = summarize_geometry_types(layer)
    bounds = summarize_bounds(layer)

    return {
        "layer_name": layer_name,
        "rows": len(layer),
        "columns": len(layer.columns),
        "is_geospatial": is_geospatial(layer),
        "crs": str(layer.crs) if is_geospatial(layer) else "",
        "geometry_column": layer.geometry.name if is_geospatial(layer) else "",
        "geometry_types": json.dumps(geometry_types, ensure_ascii=False),
        "total_bounds": json.dumps(bounds, ensure_ascii=False) if bounds else "",
    }


def load_layer(gpkg_path: Path, layer_name: str) -> gpd.GeoDataFrame:
    return gpd.read_file(gpkg_path, layer=layer_name)


def is_geospatial(frame: pd.DataFrame) -> bool:
    return isinstance(frame, gpd.GeoDataFrame) and "geometry" in frame.columns


def summarize_geometry_types(layer: pd.DataFrame) -> dict[str, int]:
    if not is_geospatial(layer):
        return {}
    counts = layer.geom_type.value_counts(dropna=False).to_dict()
    return {str(key): int(value) for key, value in counts.items()}


def summarize_bounds(layer: pd.DataFrame) -> list[float] | None:
    if not is_geospatial(layer):
        return None
    if layer.empty:
        return None
    bounds = layer.total_bounds.tolist()
    return [float(value) for value in bounds]


def save_layer_inventory(layer_profiles: list[dict], output_path: Path) -> None:
    pd.DataFrame(layer_profiles).to_csv(output_path, index=False)


def save_column_inventory(layer_profiles: list[dict], output_path: Path) -> None:
    rows: list[dict] = []

    for profile in layer_profiles:
        layer_name = profile["layer_name"]
        gpkg_path = Path(profile.get("gpkg_path", "")) if "gpkg_path" in profile else None
        if gpkg_path is None or not gpkg_path.exists():
            continue

        layer = load_layer(gpkg_path, layer_name)
        rows.extend(profile_columns(layer_name, layer))

    pd.DataFrame(rows).to_csv(output_path, index=False)


def profile_columns(layer_name: str, layer: pd.DataFrame) -> list[dict]:
    rows = []

    for column in layer.columns:
        series = layer[column]
        rows.append(
            {
                "layer_name": layer_name,
                "column": column,
                "dtype": str(series.dtype),
                "non_null_count": int(series.notna().sum()),
                "null_count": int(series.isna().sum()),
                "null_share": float(series.isna().mean()),
                "n_unique": safe_nunique(series),
                "sample_values": json.dumps(sample_values(series), ensure_ascii=False),
            }
        )

    return rows


def safe_nunique(series: pd.Series) -> int | None:
    try:
        return int(series.nunique(dropna=True))
    except TypeError:
        return None


def sample_values(series: pd.Series, n: int = 5) -> list[str]:
    non_null = series.dropna()

    if non_null.empty:
        return []

    try:
        unique_values = pd.unique(non_null)
    except TypeError:
        return []

    values = [stringify_value(value) for value in unique_values[:n]]
    return values


def stringify_value(value: object) -> str:
    text = str(value)
    return text[:200]


def select_candidate_building_layers(layer_profiles: list[dict]) -> list[str]:
    layer_names = [profile["layer_name"] for profile in layer_profiles]
    lower_to_original = {name.lower(): name for name in layer_names}

    exact_matches = [lower_to_original[name] for name in _BUILDING_LAYER_CANDIDATES if name in lower_to_original]

    if exact_matches:
        return exact_matches
    
    fallback_matches = [name for name in layer_names if "batiment" in name.lower()]
    return fallback_matches


def save_building_candidates(layer_names: list[str], output_path: Path) -> None:
    pd.DataFrame({"layer_name": layer_names}).to_csv(output_path, index=False)


def save_layer_schema(layer: pd.DataFrame, output_path: Path) -> None:
    schema = pd.DataFrame(profile_columns("current_layer", layer))
    schema = schema.drop(columns="layer_name")
    schema.to_csv(output_path, index=False)


def save_layer_sample(layer: pd.DataFrame, output_path: Path, n: int = 20) -> None:
    sample = layer.head(n).copy()

    if is_geospatial(sample):
        sample = pd.DataFrame(sample.drop(columns="geometry"))

    sample.to_csv(output_path, index=False)


def load_district(district_path: str, target_crs: object) -> gpd.GeoDataFrame:
    district = gpd.read_file(district_path)
    if target_crs is not None and district.crs != target_crs:
        district = district.to_crs(target_crs)
    return district


def clip_layer_to_district(
    layer: gpd.GeoDataFrame,
    district: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    clipped = gpd.sjoin(
        layer,
        district[["geometry"]],
        how="inner",
        predicate="intersects",
    ).drop(columns="index_right")

    return clipped[~clipped.index.duplicated(keep="first")].copy()


def save_clipped_summary(clipped: gpd.GeoDataFrame, output_path: Path) -> None:
    summary = {
        "rows": int(len(clipped)),
        "columns": int(len(clipped.columns)),
        "crs": str(clipped.crs),
        "geometry_types": summarize_geometry_types(clipped),
        "valid_geometries": int(clipped.geometry.is_valid.sum()),
        "invalid_geometries": int((~clipped.geometry.is_valid).sum()),
    }
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def save_clipped_sample(clipped: gpd.GeoDataFrame, output_path: Path, n: int = 2000) -> None:
    clipped.head(n).to_file(output_path, driver="GeoJSON")


if __name__ == "__main__":
    #explore_package("data/buildings/bdnb.gpkg","data/topology/iris_lyon.geojson")
    audit_classification_columns(gpkg_path="data/buildings/bdnb.gpkg", output_dir="output/bdnb_audit")