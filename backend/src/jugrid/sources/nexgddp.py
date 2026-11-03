"""Daily CMIP6 projections from NASA's NEX-GDDP-CMIP6, on the AWS Open Data registry.

The dataset is bias-corrected and downscaled to 0.25 degrees, one NetCDF file per model,
experiment, variable and year, each holding the whole globe. A region needs the whole file
(the files are chunked one day per chunk), so a file is downloaded, cut to the region and
thrown away.
"""

import logging
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path
from typing import IO

import httpx
import xarray as xr

from jugrid.geo import BBox
from jugrid.sources.http import check_size

log = logging.getLogger(__name__)

VARIABLES = ("tasmax", "tas", "pr", "sfcWind")
PREFIX = "NEX-GDDP-CMIP6"
_TIMES = xr.coders.CFDatetimeCoder(use_cftime=False)
_S3 = "{http://s3.amazonaws.com/doc/2006-03-01/}"
KEY = re.compile(
    r"(?P<var>[A-Za-z]+)_day_(?P<model>[\w-]+?)_(?P<experiment>\w+?)_(?P<member>r\d+i\d+p\d+f\d+)"
    r"_(?P<grid>g\w+?)_(?P<year>\d{4})(?:_v(?P<version>\d+(?:\.\d+)*))?\.nc$"
)


class ClimateSourceError(RuntimeError):
    """The archive could not be listed or a file could not be fetched or read."""


def prefix(model: str, experiment: str, member: str, variable: str) -> str:
    return f"{PREFIX}/{model}/{experiment}/{member}/{variable}/"


def list_keys(client: httpx.Client, base_url: str, key_prefix: str) -> list[str]:
    """Every object key under a prefix, following the listing's continuation tokens."""
    keys: list[str] = []
    token: str | None = None
    while True:
        params = {"list-type": "2", "prefix": key_prefix}
        if token:
            params["continuation-token"] = token
        try:
            response = client.get(base_url + "/", params=params, timeout=60)
            response.raise_for_status()
            root = ET.fromstring(response.content)  # noqa: S314 - AWS's own listing XML
        except (httpx.HTTPError, ET.ParseError) as error:
            raise ClimateSourceError(f"could not list {key_prefix}: {error}") from error
        keys += [el.text or "" for el in root.iter(f"{_S3}Key")]
        if (root.findtext(f"{_S3}IsTruncated") or "false") != "true":
            return keys
        token = root.findtext(f"{_S3}NextContinuationToken")


def _version(text: str | None) -> tuple[int, ...]:
    return tuple(int(p) for p in text.split(".")) if text else (0,)


def pick_per_year(keys: Iterable[str]) -> dict[int, str]:
    """One key per year: NASA republished some years as ``_v1.1`` and ``_v2.0``; newest wins."""
    best: dict[int, tuple[tuple[int, ...], str]] = {}
    for key in keys:
        match = KEY.search(key)
        if not match:
            continue
        year, version = int(match["year"]), _version(match["version"])
        if year not in best or version > best[year][0]:
            best[year] = (version, key)
    return {year: key for year, (_, key) in sorted(best.items())}


def to_units(data: xr.DataArray, variable: str) -> xr.DataArray:
    """Kelvin to °C and kg m-2 s-1 to mm a day; wind stays in m/s."""
    if variable in {"tasmax", "tas"}:
        out = data - 273.15
        out.attrs["units"] = "degC"
    elif variable == "pr":
        out = data * 86400.0
        out.attrs["units"] = "mm/day"
    else:
        out = data.copy()
        out.attrs["units"] = "m/s"
    return out.astype("float32")


def cut(dataset: xr.Dataset, variable: str, bbox: BBox) -> xr.DataArray:
    """The region's cells of one variable, with longitudes from -180 to 180, south to north."""
    data = dataset[variable]
    lon = ((data["lon"] + 180) % 360) - 180
    data = data.assign_coords(lon=lon).sortby("lon").sortby("lat")
    margin = 0.125  # half a cell, so cells whose centre is just outside still cover the edge
    region = data.sel(
        lat=slice(bbox.south - margin, bbox.north + margin),
        lon=slice(bbox.west - margin, bbox.east + margin),
    )
    if region.sizes["lat"] == 0 or region.sizes["lon"] == 0:
        raise ClimateSourceError(f"no {variable} cells inside {bbox}")
    region = to_units(region.load(), variable)
    region["time"] = region["time"].dt.floor("D")  # NEX-GDDP stamps each day at noon
    return region.drop_vars([c for c in region.coords if c not in {"time", "lat", "lon"}])


def _download(
    client: httpx.Client, url: str, handle: IO[bytes], attempts: int, backoff_s: float
) -> None:
    """Stream a file into ``handle``, starting over after a dropped connection or a 5xx."""
    for attempt in range(1, attempts + 1):
        handle.seek(0)
        handle.truncate()
        try:
            with client.stream("GET", url, timeout=600) as response:
                response.raise_for_status()
                received = 0
                check_size(response, received)
                for chunk in response.iter_bytes(1 << 20):
                    received += len(chunk)
                    check_size(response, received)
                    handle.write(chunk)
            handle.flush()
            return
        except httpx.HTTPStatusError as error:
            if error.response.status_code < 500 or attempt == attempts:
                raise
        except httpx.TransportError:
            if attempt == attempts:
                raise
        log.warning("retrying %s (attempt %d of %d)", url, attempt + 1, attempts)
        time.sleep(backoff_s * 2 ** (attempt - 1))


def fetch_year(
    client: httpx.Client,
    base_url: str,
    key: str,
    variable: str,
    bbox: BBox,
    workdir: Path,
    attempts: int = 4,
    backoff_s: float = 2.0,
) -> xr.DataArray:
    """Download one global file, cut the region out of it and delete the file."""
    with tempfile.NamedTemporaryFile(dir=workdir, suffix=".nc") as handle:
        try:
            _download(client, f"{base_url}/{key}", handle, attempts, backoff_s)
            with xr.open_dataset(handle.name, engine="h5netcdf", decode_times=_TIMES) as dataset:
                return cut(dataset, variable, bbox)
        except (httpx.HTTPError, OSError, KeyError, ValueError) as error:
            raise ClimateSourceError(f"could not read {key}: {error}") from error
