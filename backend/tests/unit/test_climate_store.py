from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from jugrid.climate import ingest
from jugrid.climate.store import ClimateStore, open_store
from jugrid.risk.hazards import Scenario
from tests.factories import daily_cube

BASELINE = Scenario("baseline", "Today", "historical", 2001, 2002)
FUTURE = Scenario("ssp245_2050", "2050", "ssp245", 2049, 2050)


@pytest.fixture
def store(tmp_path: Path) -> ClimateStore:
    return ClimateStore(open_store(str(tmp_path / "climate.zarr")))


def test_a_year_is_missing_until_written_whole(store: ClimateStore) -> None:
    assert not store.has_year("baseline", "tas", 2001)
    store.write_year("baseline", "tas", 2001, daily_cube(1.0, 2001, "tas"))
    assert store.has_year("baseline", "tas", 2001)
    assert not store.has_year("baseline", "tas", 2002)


def test_read_period_joins_years_in_order(store: ClimateStore) -> None:
    for year in (2001, 2002):
        store.write_year("baseline", "pr", year, daily_cube(float(year), year, "pr"))
    joined = store.read_period("baseline", "pr", range(2001, 2003))
    assert joined.sizes["time"] == 730
    assert float(joined.isel(time=0, lat=0, lon=0)) == 2001
    assert float(joined.isel(time=-1, lat=0, lon=0)) == 2002


def fake_climate(experiment: str, variable: str, year: int) -> xr.DataArray:
    """Hot and calm today, hotter and stormier tomorrow."""
    hot = experiment != "historical"
    value = {
        "tasmax": 36.0 if hot else 30.0,
        "tas": 0.5,
        "pr": 12.0,
        "sfcWind": 10.0 if hot else 5.0,
    }[variable]
    data = np.full((365 + (year % 4 == 0), 3, 3), value, dtype="float32")
    if variable == "tasmax" and not hot:
        data[:10] = 36.0  # ten hot days a year today
    return daily_cube(data, year, variable)


def test_fill_fetches_only_what_is_missing(store: ClimateStore) -> None:
    calls: list[tuple[str, str, int]] = []

    def fetch(experiment: str, variable: str, year: int) -> xr.DataArray:
        calls.append((experiment, variable, year))
        return fake_climate(experiment, variable, year)

    store.write_year("baseline", "tas", 2001, fake_climate("historical", "tas", 2001))
    written = ingest.fill(store, [BASELINE], fetch, workers=2)
    assert written == 7
    assert ("historical", "tas", 2001) not in calls
    assert ingest.fill(store, [BASELINE], fetch) == 0


def test_compute_stacks_every_indicator_by_scenario(store: ClimateStore) -> None:
    ingest.fill(store, [BASELINE, FUTURE], fake_climate)
    result = ingest.compute(store, [BASELINE, FUTURE], "test-model")
    assert result.sizes == {"scenario": 2, "lat": 3, "lon": 3}
    today, tomorrow = result.sel(scenario="baseline"), result.sel(scenario="ssp245_2050")
    assert float(today.hot_days.mean()) == pytest.approx(10)
    assert float(tomorrow.hot_days.mean()) == pytest.approx(365)
    assert float(tomorrow.windiest_day.mean()) == pytest.approx(10)
    assert float(today.wet_snow_days.mean()) == pytest.approx(365)

    stored = store.read_indicators()
    assert stored is not None
    assert stored.attrs["model"] == "test-model"
    xr.testing.assert_allclose(stored.hot_days, result.hot_days)


def test_no_indicators_yet_is_none(store: ClimateStore) -> None:
    assert store.read_indicators() is None
