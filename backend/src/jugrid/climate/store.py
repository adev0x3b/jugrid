"""The Zarr store: the region's daily climate per scenario and year, and the indicators.

Layout::

    daily/<scenario>/<variable>/<year>   one year of one variable, (time, lat, lon)
    indicators                           every indicator, (scenario, lat, lon), as scored
    indicators_raw                       the same from the uncorrected projections

A year is written whole and then marked ``complete``, so an interrupted ingest starts again
from the first year that is not.
"""

from typing import Any

import xarray as xr
import zarr
from zarr.storage import FsspecStore, LocalStore, StoreLike

INDICATORS_GROUP = "indicators"  # what the scores use: bias-corrected when a model applies
RAW_INDICATORS_GROUP = "indicators_raw"  # from the projections as published


def open_store(url: str, storage_options: dict[str, Any] | None = None) -> StoreLike:
    if "://" in url and not url.startswith("file://"):
        return FsspecStore.from_url(url, storage_options=storage_options or {})
    return LocalStore(url.removeprefix("file://"))


class ClimateStore:
    def __init__(self, store: StoreLike) -> None:
        self.store = store

    @staticmethod
    def _daily(scenario: str, variable: str, year: int) -> str:
        return f"daily/{scenario}/{variable}/{year}"

    def has_year(self, scenario: str, variable: str, year: int) -> bool:
        try:
            group = zarr.open_group(
                self.store, path=self._daily(scenario, variable, year), mode="r"
            )
        except FileNotFoundError, zarr.errors.GroupNotFoundError:
            return False
        return bool(group.attrs.get("complete"))

    def write_year(self, scenario: str, variable: str, year: int, data: xr.DataArray) -> None:
        path = self._daily(scenario, variable, year)
        data.to_dataset(name=variable).drop_encoding().to_zarr(
            self.store, group=path, mode="w", consolidated=False, zarr_format=3
        )
        zarr.open_group(self.store, path=path, mode="r+").attrs["complete"] = True

    def read_period(self, scenario: str, variable: str, years: range) -> xr.DataArray:
        parts = [
            xr.open_zarr(
                self.store, group=self._daily(scenario, variable, year), consolidated=False
            )[variable]
            for year in years
        ]
        joined: xr.DataArray = xr.concat(parts, dim="time")
        return joined

    def write_indicators(self, indicators: xr.Dataset, *, raw: bool = False) -> None:
        group = RAW_INDICATORS_GROUP if raw else INDICATORS_GROUP
        indicators.to_zarr(self.store, group=group, mode="w", consolidated=False, zarr_format=3)

    def read_indicators(self, *, raw: bool = False) -> xr.Dataset | None:
        group = RAW_INDICATORS_GROUP if raw else INDICATORS_GROUP
        try:
            loaded: xr.Dataset = xr.open_zarr(self.store, group=group, consolidated=False).load()
            return loaded
        except FileNotFoundError, zarr.errors.GroupNotFoundError, KeyError:
            return None
