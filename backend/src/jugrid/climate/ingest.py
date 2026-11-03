"""Fill the store with the region's daily climate, then compute the indicators."""

import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx
import xarray as xr

from jugrid.climate import indicators
from jugrid.climate.store import ClimateStore
from jugrid.geo import BBox
from jugrid.risk.hazards import Scenario
from jugrid.sources import nexgddp

log = logging.getLogger(__name__)

Fetch = Callable[[str, str, int], xr.DataArray]


def missing_years(
    store: ClimateStore, scenario: Scenario, variables: Sequence[str]
) -> list[tuple[str, int]]:
    return [
        (variable, year)
        for variable in variables
        for year in range(scenario.start_year, scenario.end_year + 1)
        if not store.has_year(scenario.key, variable, year)
    ]


def nexgddp_fetcher(
    client: httpx.Client, base_url: str, model: str, member: str, bbox: BBox, workdir: Path
) -> Fetch:
    """A fetch function that lists each (experiment, variable) once and downloads per year."""
    listings: dict[tuple[str, str], dict[int, str]] = {}

    def fetch(experiment: str, variable: str, year: int) -> xr.DataArray:
        if (experiment, variable) not in listings:
            keys = nexgddp.list_keys(
                client, base_url, nexgddp.prefix(model, experiment, member, variable)
            )
            listings[experiment, variable] = nexgddp.pick_per_year(keys)
        key = listings[experiment, variable].get(year)
        if key is None:
            raise nexgddp.ClimateSourceError(f"{model} {experiment} has no {variable} for {year}")
        return nexgddp.fetch_year(client, base_url, key, variable, bbox, workdir)

    return fetch


def fill(
    store: ClimateStore,
    scenarios: Sequence[Scenario],
    fetch: Fetch,
    workers: int = 1,
    variables: Sequence[str] = nexgddp.VARIABLES,
) -> int:
    """Download every year the store lacks. Returns how many were written."""
    written = 0
    for scenario in scenarios:
        todo = missing_years(store, scenario, variables)
        log.info("%s: %d variable-years to fetch", scenario.key, len(todo))

        def one(item: tuple[str, int], scenario: Scenario = scenario) -> None:
            variable, year = item
            store.write_year(
                scenario.key, variable, year, fetch(scenario.experiment, variable, year)
            )
            log.info("%s %s %d stored", scenario.key, variable, year)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for _ in pool.map(one, todo):
                written += 1
    return written


def compute(store: ClimateStore, scenarios: Sequence[Scenario], model: str) -> xr.Dataset:
    """Every indicator for every scenario, stacked along a ``scenario`` dimension."""
    per_scenario = []
    for scenario in scenarios:
        years = range(scenario.start_year, scenario.end_year + 1)
        tasmax = store.read_period(scenario.key, "tasmax", years)
        tas = store.read_period(scenario.key, "tas", years)
        pr = store.read_period(scenario.key, "pr", years)
        wind = store.read_period(scenario.key, "sfcWind", years)
        per_scenario.append(
            xr.Dataset(
                {
                    "hot_days": indicators.hot_days(tasmax),
                    "wettest_day": indicators.wettest_day(pr),
                    "windiest_day": indicators.windiest_day(wind),
                    "wet_snow_days": indicators.wet_snow_days(tas, pr),
                }
            )
            .compute()
            .expand_dims(scenario=[scenario.key])
        )
    result = xr.concat(per_scenario, dim="scenario").astype("float32")
    result.attrs.update(
        model=model,
        source="NASA NEX-GDDP-CMIP6",
        periods={s.key: [s.start_year, s.end_year] for s in scenarios},
        computed_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    store.write_indicators(result)
    return result
