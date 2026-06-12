import pandas as pd
import xarray as xr

_LYON_LAT = 45.75
_LYON_LON = 4.85


def load_temperature_15min(grib_path: str, year: int = 2019) -> pd.Series:
    hourly    = _load_hourly_temperature(grib_path)
    full_year = _select_year(hourly, year)
    return _interpolate_to_15min(full_year, year)


# ── Loading ───────────────────────────────────────────────────────────────────

def _load_hourly_temperature(grib_path: str) -> pd.Series:
    ds = xr.open_dataset(grib_path, engine="cfgrib")
    if "t2m" not in ds:
        raise ValueError(f"Variable 't2m' not found. Available: {list(ds.data_vars)}")
    da = ds["t2m"]
    da = _select_nearest_point(da)
    # ERA5 stores temperature in Kelvin
    return da.to_series().rename("temperature_c") - 273.15


def _select_nearest_point(da: xr.DataArray) -> xr.DataArray:
    kwargs = {}
    if "latitude" in da.dims:
        kwargs["latitude"] = _LYON_LAT
    if "longitude" in da.dims:
        kwargs["longitude"] = _LYON_LON
    if kwargs:
        return da.sel(**kwargs, method="nearest")
    return da


# ── Processing ────────────────────────────────────────────────────────────────

def _select_year(series: pd.Series, year: int) -> pd.Series:
    return series[series.index.year == year]


def _interpolate_to_15min(hourly: pd.Series, year: int) -> pd.Series:
    index_15min = pd.date_range(f"{year}-01-01", f"{year}-12-31 23:45", freq="15min")
    # Linear interpolation is sufficient — ERA5 hourly data is already smoothed
    return (hourly.reindex(hourly.index.union(index_15min)).interpolate(method="time").reindex(index_15min))