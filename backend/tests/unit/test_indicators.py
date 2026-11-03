import numpy as np
import pandas as pd
import pytest
import xarray as xr
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from jugrid.climate import indicators


def daily(values: list[float] | np.ndarray, start: str = "2001-01-01") -> xr.DataArray:
    values = np.asarray(values, dtype="float64")
    time = pd.date_range(start, periods=values.shape[0], freq="D")
    return xr.DataArray(values, dims=("time",), coords={"time": time})


def two_years(first: float, second: float) -> xr.DataArray:
    """365 days at ``first`` then 365 days at ``second`` (2001 and 2002 are not leap years)."""
    return daily([first] * 365 + [second] * 365)


class TestHotDays:
    def test_counts_days_strictly_above_the_threshold_and_averages_years(self) -> None:
        values = np.full(730, 20.0)
        values[:10] = 36.0  # ten hot days in 2001
        values[365:395] = 35.5  # thirty in 2002
        values[400] = 35.0  # exactly 35 is not above it
        assert float(indicators.hot_days(daily(values))) == pytest.approx(20.0)

    def test_keeps_spatial_dimensions(self) -> None:
        cube = xr.concat([two_years(36, 36), two_years(10, 10)], dim="lat").assign_coords(
            lat=[45.0, 45.25]
        )
        result = indicators.hot_days(cube)
        assert result.dims == ("lat",)
        assert result.sel(lat=45.0) == pytest.approx(365)
        assert result.sel(lat=45.25) == pytest.approx(0)

    def test_a_cell_without_data_is_nan_not_zero(self) -> None:
        assert np.isnan(float(indicators.hot_days(daily([np.nan] * 365))))

    @settings(max_examples=50, deadline=None)
    @given(arrays("float64", 365, elements=st.floats(-30, 50)))
    def test_is_between_zero_and_the_days_of_the_year(self, values: np.ndarray) -> None:
        result = float(indicators.hot_days(daily(values)))
        assert 0 <= result <= 365

    @settings(max_examples=50, deadline=None)
    @given(arrays("float64", 365, elements=st.floats(-30, 50)), st.floats(20, 40))
    def test_a_higher_threshold_never_counts_more(self, values: np.ndarray, t: float) -> None:
        cube = daily(values)
        assert float(indicators.hot_days(cube, t + 1)) <= float(indicators.hot_days(cube, t))


class TestWettestDay:
    def test_is_the_mean_of_each_years_maximum(self) -> None:
        values = np.zeros(730)
        values[100] = 80.0
        values[500] = 40.0
        assert float(indicators.wettest_day(daily(values))) == pytest.approx(60.0)

    @settings(max_examples=50, deadline=None)
    @given(arrays("float64", 730, elements=st.floats(0, 300)))
    def test_lies_between_the_smallest_and_largest_day(self, values: np.ndarray) -> None:
        result = float(indicators.wettest_day(daily(values)))
        assert values.min() - 1e-9 <= result <= values.max() + 1e-9


class TestWindiestDay:
    def test_is_the_mean_of_each_years_maximum(self) -> None:
        values = np.full(730, 3.0)
        values[10] = 12.0
        values[700] = 8.0
        assert float(indicators.windiest_day(daily(values))) == pytest.approx(10.0)


class TestWetSnowDays:
    def test_needs_both_heavy_precipitation_and_a_temperature_near_freezing(self) -> None:
        tas = np.full(365, 5.0)
        pr = np.zeros(365)
        tas[0], pr[0] = 0.5, 15.0  # counts
        tas[1], pr[1] = 0.5, 5.0  # too little precipitation
        tas[2], pr[2] = -5.0, 30.0  # too cold: dry snow
        tas[3], pr[3] = 4.0, 30.0  # too warm: rain
        tas[4], pr[4] = -1.0, 10.0  # both bounds included
        assert float(indicators.wet_snow_days(daily(tas), daily(pr))) == pytest.approx(2.0)

    def test_missing_temperature_is_missing_not_zero(self) -> None:
        result = indicators.wet_snow_days(daily([np.nan] * 365), daily([20.0] * 365))
        assert np.isnan(float(result))
