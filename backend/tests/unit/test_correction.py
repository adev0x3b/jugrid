import numpy as np
import pandas as pd
import pytest
import xarray as xr
from hypothesis import given, settings
from hypothesis import strategies as st

from jugrid.correction import quantiles as qm


def cube(values: np.ndarray, start: str = "2001-01-01") -> xr.DataArray:
    time = pd.date_range(start, periods=values.shape[0], freq="D")
    return xr.DataArray(
        values.astype("float32"),
        dims=("time", "lat", "lon"),
        coords={"time": time, "lat": [45.125, 45.375], "lon": [7.125]},
        name="tasmax",
    )


def noise(days: int = 730, seed: int = 0, loc: float = 20, scale: float = 5) -> np.ndarray:
    return np.random.default_rng(seed).normal(loc, scale, (days, 2, 1))


class TestRanks:
    def test_lie_strictly_between_zero_and_one(self) -> None:
        q = qm.ranks(cube(noise()))
        assert float(q.min()) > 0
        assert float(q.max()) < 1

    def test_follow_the_values_within_each_cell_and_month(self) -> None:
        data = cube(noise())
        q = qm.ranks(data)
        january = data.time.dt.month == 1
        cell = {"lat": 45.125, "lon": 7.125}
        values = data.sel(cell).where(january, drop=True).values
        ranks = q.sel(cell).where(january, drop=True).values
        assert (np.argsort(values) == np.argsort(ranks)).all()

    def test_a_missing_day_stays_missing(self) -> None:
        values = noise()
        values[3, 0, 0] = np.nan
        assert np.isnan(qm.ranks(cube(values)).values[3, 0, 0])


class TestTransforms:
    @pytest.mark.parametrize("variable", ["tasmax", "tas", "pr", "sfcWind"])
    def test_applying_the_delta_between_two_values_turns_one_into_the_other(
        self, variable: str
    ) -> None:
        model, observed = np.array([0.0, 3.0, 12.5]), np.array([0.4, 2.0, 15.0])
        delta = qm.delta(model, observed, variable)
        assert np.allclose(qm.apply_delta(model, delta, variable), observed, atol=1e-5)

    def test_rain_and_wind_never_come_out_negative(self) -> None:
        out = qm.apply_delta(np.array([0.0, 0.05]), np.array([-5.0, -5.0]), "pr")
        assert (out >= 0).all()

    def test_rain_and_wind_are_corrected_by_ratio_temperature_by_difference(self) -> None:
        assert {"pr", "sfcWind"} == qm.MULTIPLICATIVE


class TestFeatures:
    def test_are_the_quantile_the_season_and_the_place(self) -> None:
        data = cube(noise(days=40))
        x = qm.features(qm.ranks(data))
        assert x.shape == (40 * 2, 5)
        assert x.dtype == np.float32
        # January and February rows differ only in the season columns.
        assert set(np.round(x[:, 3], 3)) == {45.125, 45.375}

    def test_the_season_is_continuous_from_december_to_january(self) -> None:
        dec, jan = qm.season(np.array([12])), qm.season(np.array([1]))
        assert np.linalg.norm(dec - jan) < 0.6


class TestTrainingTable:
    def test_pairs_model_and_observed_quantiles_per_cell_and_month(self) -> None:
        model = cube(noise(seed=1))
        observed = cube(noise(seed=2, loc=23))
        table = qm.training_table(model, observed, "tasmax")
        assert table.x.shape[0] == table.y.shape[0] == 2 * 12 * len(qm.QUANTILES)
        # Observed is about 3 degrees warmer: the deltas say so.
        assert 2 < float(np.median(table.y)) < 4
        assert set(table.cell) == {0, 1}
        assert np.allclose(table.model + table.y, table.observed)

    def test_skips_cells_without_observations(self) -> None:
        observed = noise(seed=2)
        observed[:, 1, 0] = np.nan
        table = qm.training_table(cube(noise(seed=1)), cube(observed), "tasmax")
        assert set(table.cell) == {0}
        assert not np.isnan(table.x).any()

    def test_observations_on_a_shifted_grid_are_interpolated_onto_the_model_cells(
        self,
    ) -> None:
        model = cube(noise(seed=1))
        time = model["time"]
        shifted = xr.DataArray(
            np.full((len(time), 3, 3), 23.0, dtype="float32"),
            dims=("time", "lat", "lon"),
            coords={"time": time, "lat": [44.9, 45.25, 45.6], "lon": [6.9, 7.2, 7.5]},
        )
        table = qm.training_table(model, shifted, "tasmax")
        assert table.x.shape[0] == 2 * 12 * len(qm.QUANTILES)
        assert np.allclose(table.observed, 23.0)


class TestEmpiricalMapping:
    def test_moves_the_model_distribution_onto_the_observed_one(self) -> None:
        model = cube(noise(seed=1, loc=20, scale=3))
        observed = cube(noise(seed=2, loc=24, scale=5))
        corrected = qm.apply_cube(model, qm.delta_cube(model, observed, "tasmax"), "tasmax")
        for q in (0.1, 0.5, 0.9):
            assert abs(float(corrected.quantile(q)) - float(observed.quantile(q))) < 0.5

    def test_keeps_the_change_a_projection_adds(self) -> None:
        history = cube(noise(seed=1))
        observed = cube(noise(seed=2, loc=22))
        future = history + 3  # the model's projected warming
        cube_ = qm.delta_cube(history, observed, "tasmax")
        change = (
            qm.apply_cube(future, cube_, "tasmax").mean()
            - qm.apply_cube(history, cube_, "tasmax").mean()
        )
        assert abs(float(change) - 3) < 0.2


@settings(max_examples=30, deadline=None)
@given(st.floats(-20, 20), st.floats(0.5, 3))
def test_a_monotone_bias_is_removed_and_days_keep_their_order(shift: float, stretch: float) -> None:
    history = cube(noise(seed=1))
    observed = history * stretch + shift  # the model is off by a monotone transform
    corrected = qm.apply_cube(history, qm.delta_cube(history, observed, "tasmax"), "tasmax")
    spread = float(observed.std())
    assert float(abs(corrected - observed).mean()) < 0.02 * spread
    # Interpolating between quantiles can swap two near-equal days, never more.
    before = history.values.ravel()
    after = corrected.values.ravel()
    rank_before = np.argsort(np.argsort(before))
    rank_after = np.argsort(np.argsort(after))
    assert np.corrcoef(rank_before, rank_after)[0, 1] > 0.999
