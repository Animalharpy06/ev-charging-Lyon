import pandas as pd
from demandlib import bdew

_MARCH_TYPICAL_DAY = 11

_SPECIFIC_DEMAND: dict[tuple[str, str], dict[str, float]] = {
    ("residential", "old"):    {"heating": 12.39, "electricity": 5.08},
    ("residential", "mid"):    {"heating": 14.11, "electricity": 5.93},
    ("residential", "recent"): {"heating":  5.89, "electricity": 5.93},
    ("office",      "old"):    {"heating": 12.36, "electricity": 12.12},
    ("office",      "mid"):    {"heating": 14.61, "electricity": 14.15},
    ("office",      "recent"): {"heating":  6.63, "electricity": 14.15}}

# Internal BDEW values to represent the thermal properties of buildings, they go from 1 to 10
_BDEW_BUILDING_CLASS: dict[str, int] = {"old": 1, "mid": 5, "recent": 9}

_ALL_CLASSES: list[tuple[str, str]] = list(_SPECIFIC_DEMAND.keys())


def build_demand_profiles(buildings, temperature_15min, year=2025, holidays=None):
    index_15min      = _full_year_index(year)
    march_index      = _march_day_index(year)
    unit_elec_curves = _build_unit_electrical_curves(year, holidays)
    unit_heat_curves = _build_unit_thermal_curves(temperature_15min, index_15min)

    elec_columns: dict[str, pd.Series] = {}
    heat_columns: dict[str, pd.Series] = {}

    for row in buildings.itertuples(index=False):
        use       = _building_use(row.bdtopo_bat_l_usage_1)
        age_class = _age_class(row.ffo_bat_annee_construction)
        volume_m3 = float(row.s_geom_groupe) * float(row.bdtopo_bat_hauteur_mean)
        annual    = _annual_demand(volume_m3, use, age_class)
        building_id = str(row.batiment_groupe_id)

        elec_columns[building_id] = unit_elec_curves[(use, age_class)] * annual["electricity"]
        heat_columns[building_id] = unit_heat_curves[(use, age_class)] * annual["heating"]

    return {"electricity": pd.DataFrame(elec_columns, index=march_index),
            "heat":        pd.DataFrame(heat_columns, index=march_index)}


def _march_day_index(year: int) -> pd.DatetimeIndex:
    start = pd.Timestamp(year=year, month=3, day=_MARCH_TYPICAL_DAY)
    return pd.date_range(start, periods=96, freq="15min")


# ── Unit curves (computed once per class, scaled per building) ────────────────

def _build_unit_electrical_curves(year: int, 
                                  holidays) -> dict[tuple[str, str], pd.Series]:
    
    # ElecSlp is stateless across use types — instantiate once per profile name
    residential_curve = _unit_electrical_curve("residential", year, holidays)
    office_curve      = _unit_electrical_curve("office",      year, holidays)

    return {(use, age): residential_curve if use == "residential" else office_curve
            for use, age in _ALL_CLASSES}


def _unit_electrical_curve(use: str, 
                           year: int, 
                           holidays) -> pd.Series:
    
    profile_name = "h0_dyn" if use == "residential" else "g0"
    slp          = bdew.ElecSlp(year=year, holidays=holidays)
    full_year    = slp.get_profiles(profile_name)[profile_name]
    normalised   = full_year / full_year.sum()

    return _march_day(normalised, year)


def _build_unit_thermal_curves(temperature_15min: pd.Series,
                               index_15min: pd.DatetimeIndex) -> dict[tuple[str, str], pd.Series]:
    
    return {(use, age): _unit_thermal_curve(use, age, temperature_15min, index_15min) for use, age in _ALL_CLASSES}


def _unit_thermal_curve(use: str,
                        age_class: str,
                        temperature_15min: pd.Series,
                        index_15min: pd.DatetimeIndex) -> pd.Series:
    
    shlp_type      = "MFH" if use == "residential" else "GHD"
    building_class = _BDEW_BUILDING_CLASS[age_class] if use == "residential" else 0

    builder = bdew.HeatBuilding(df_index=index_15min,
                                temperature=temperature_15min,
                                annual_heat_demand=1.0,   # unit curve — scaled per building by annual_kwh
                                shlp_type=shlp_type,
                                building_class=building_class,
                                wind_class=0,
                                ww_incl=True)
    full_year = pd.Series(builder.get_bdew_profile(), index=index_15min, dtype=float)
    
    return _march_day(full_year, index_15min.year[0])


# ── Building classification ───────────────────────────────────────────────────

def _building_use(raw_usage: object) -> str:
    # Residential only if the string contains "Résidentiel"; everything else is office
    if isinstance(raw_usage, str) and "Résidentiel" in raw_usage:
        return "residential"
    return "office"


def _age_class(raw_year: object) -> str:
    # Only ffo_bat_annee_construction is checked; missing values default to "mid"
    if pd.isna(raw_year):
        return "mid"
    year = int(float(raw_year))
    if year < 1960:
        return "old"
    if year < 2005:
        return "mid"
    return "recent"


def _annual_demand(volume_m3: float, use: str, age_class: str) -> dict[str, float]:
    spec = _SPECIFIC_DEMAND[(use, age_class)]
    return {"heating":     volume_m3 * spec["heating"],
            "electricity": volume_m3 * spec["electricity"]}


# ── Time helpers ──────────────────────────────────────────────────────────────

def _full_year_index(year: int) -> pd.DatetimeIndex:
    return pd.date_range(f"{year}-01-01", f"{year}-12-31 23:45", freq="15min")


def _march_day(series: pd.Series, year: int) -> pd.Series:
    start = pd.Timestamp(year=year, month=3, day=_MARCH_TYPICAL_DAY)
    end   = start + pd.Timedelta(hours=23, minutes=45)
    return series.loc[start:end].reset_index(drop=True)