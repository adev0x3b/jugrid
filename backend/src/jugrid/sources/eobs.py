"""Observed daily weather from E-OBS, the station-based gridded dataset of ECA&D / Copernicus.

E-OBS is on the same 0.25 degree grid as NEX-GDDP-CMIP6, which makes it the reference the bias
correction learns from. KNMI hosts the files in a public S3 bucket; each holds 1950 to the last
release for all of Europe, chunked one day per chunk, so a region is read in place with ranged
requests (about five seconds a year) instead of downloading the whole file.

Licence: free for non-commercial research and education; cite Cornes et al. (2018).
"""

import logging
from typing import Any

import xarray as xr

from jugrid.geo import BBox

log = logging.getLogger(__name__)

BUCKET = "knmi-ecad-assets-prd/ensembles/data/Grid_0.25deg_reg_ensemble"
VERSION = "v32.0e"
# The model's variable and the E-OBS one that measures the same thing, in the same units.
OBSERVED = {"tasmax": "tx", "tas": "tg", "pr": "rr", "sfcWind": "fg"}


class ObservationsError(RuntimeError):
    """E-OBS could not be read, or has no data for the region or year asked."""


def path(variable: str, version: str = VERSION) -> str:
    return f"{BUCKET}/{OBSERVED[variable]}_ens_mean_0.25deg_reg_{version}.nc"


def cut(dataset: xr.Dataset, variable: str, year: int, bbox: BBox) -> xr.DataArray:
    """One year of the region's cells, named and laid out like the model's (time, lat, lon)."""
    data = dataset[OBSERVED[variable]].rename(latitude="lat", longitude="lon")
    # A cell and a half: E-OBS wind sits on a grid shifted 0.1 degrees from the others, and
    # interpolating it onto the model's edge cells needs the cells beyond them.
    margin = 0.375
    region = data.sel(
        time=slice(f"{year}-01-01", f"{year}-12-31"),
        lat=slice(bbox.south - margin, bbox.north + margin),
        lon=slice(bbox.west - margin, bbox.east + margin),
    )
    if region.sizes["time"] == 0:
        raise ObservationsError(f"E-OBS has no {variable} for {year}")
    if region.sizes["lat"] == 0 or region.sizes["lon"] == 0:
        raise ObservationsError(f"E-OBS has no cells inside {bbox}")
    out = region.load().astype("float32").rename(variable)
    out["time"] = out["time"].dt.floor("D")
    return out.drop_vars([c for c in out.coords if c not in {"time", "lat", "lon"}])


class Reader:
    """Reads years of one region from the public bucket, opening each file once."""

    def __init__(self, bbox: BBox, version: str = VERSION) -> None:
        import s3fs  # noqa: PLC0415 - only the training reads observations

        self.bbox, self.version = bbox, version
        self._fs = s3fs.S3FileSystem(anon=True)
        self._open: dict[str, tuple[Any, xr.Dataset]] = {}

    def year(self, variable: str, year: int) -> xr.DataArray:
        if variable not in self._open:
            try:
                handle = self._fs.open(
                    path(variable, self.version), block_size=4 << 20, cache_type="readahead"
                )
                self._open[variable] = (handle, xr.open_dataset(handle, engine="h5netcdf"))
            except OSError as error:
                raise ObservationsError(f"could not open E-OBS {variable}: {error}") from error
        try:
            return cut(self._open[variable][1], variable, year, self.bbox)
        except OSError as error:
            raise ObservationsError(f"could not read E-OBS {variable} {year}: {error}") from error

    def close(self) -> None:
        for handle, dataset in self._open.values():
            dataset.close()
            handle.close()
        self._open.clear()
