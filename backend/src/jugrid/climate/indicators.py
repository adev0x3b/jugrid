"""Climate indicators over daily grids.

Each function takes daily data as an ``xarray.DataArray`` with a ``time`` dimension (plus any
spatial ones) and returns the yearly indicator averaged over the period, so the result keeps the
spatial dimensions and drops ``time``. Missing days stay missing: a cell with no data at all comes
out as NaN rather than zero.
"""

import xarray as xr

HOT_DAY_C = 35.0
WET_SNOW_MIN_PR_MM = 10.0
WET_SNOW_TAS_C = (-1.0, 2.0)


def _yearly_mean(per_year: xr.DataArray) -> xr.DataArray:
    return per_year.mean("year", skipna=True)


def _count_per_year(condition: xr.DataArray, valid: xr.DataArray) -> xr.DataArray:
    counted = condition.where(valid).groupby("time.year").sum("time", min_count=1)
    return _yearly_mean(counted)


def hot_days(tasmax_c: xr.DataArray, threshold_c: float = HOT_DAY_C) -> xr.DataArray:
    """Mean number of days a year whose maximum temperature is above ``threshold_c``."""
    return _count_per_year(tasmax_c > threshold_c, tasmax_c.notnull()).rename("hot_days")


def wettest_day(pr_mm: xr.DataArray) -> xr.DataArray:
    """Mean over years of the year's largest one-day rainfall (ETCCDI Rx1day), in mm."""
    yearly = pr_mm.groupby("time.year").max("time", skipna=True)
    return _yearly_mean(yearly).rename("wettest_day")


def windiest_day(wind_ms: xr.DataArray) -> xr.DataArray:
    """Mean over years of the year's highest daily mean wind speed, in m/s."""
    yearly = wind_ms.groupby("time.year").max("time", skipna=True)
    return _yearly_mean(yearly).rename("windiest_day")


def wet_snow_days(
    tas_c: xr.DataArray,
    pr_mm: xr.DataArray,
    min_pr_mm: float = WET_SNOW_MIN_PR_MM,
    tas_range_c: tuple[float, float] = WET_SNOW_TAS_C,
) -> xr.DataArray:
    """Mean number of days a year with heavy precipitation falling near freezing.

    Those are the days wet snow sticks to conductors and builds the sleeves that bring lines
    down: at least ``min_pr_mm`` of precipitation with the daily mean temperature inside
    ``tas_range_c``.
    """
    low, high = tas_range_c
    condition = (pr_mm >= min_pr_mm) & (tas_c >= low) & (tas_c <= high)
    valid = tas_c.notnull() & pr_mm.notnull()
    return _count_per_year(condition, valid).rename("wet_snow_days")
