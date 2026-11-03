from pathlib import Path

import httpx
import numpy as np
import pytest
import respx
import xarray as xr

from jugrid.geo import BBox
from jugrid.sources import nexgddp
from tests.factories import global_file

BASE = "https://nex.example"
PIEMONTE = BBox(6.62, 44.06, 9.22, 46.47)


def listing(keys: list[str], next_token: str | None = None) -> str:
    contents = "".join(f"<Contents><Key>{k}</Key></Contents>" for k in keys)
    truncated = "true" if next_token else "false"
    token = f"<NextContinuationToken>{next_token}</NextContinuationToken>" if next_token else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"<IsTruncated>{truncated}</IsTruncated>{token}{contents}</ListBucketResult>"
    )


def key(year: int, version: str = "") -> str:
    return (
        "NEX-GDDP-CMIP6/EC-Earth3/historical/r1i1p1f1/tas/"
        f"tas_day_EC-Earth3_historical_r1i1p1f1_gr_{year}{version}.nc"
    )


@respx.mock
def test_listing_follows_continuation_tokens() -> None:
    route = respx.get(f"{BASE}/").mock(
        side_effect=[
            httpx.Response(200, text=listing([key(1995)], next_token="abc")),
            httpx.Response(200, text=listing([key(1996)])),
        ]
    )
    with httpx.Client() as client:
        keys = nexgddp.list_keys(client, BASE, "NEX-GDDP-CMIP6/EC-Earth3/historical/")
    assert keys == [key(1995), key(1996)]
    assert route.calls[1].request.url.params["continuation-token"] == "abc"


@respx.mock
def test_a_failed_listing_is_a_source_error() -> None:
    respx.get(f"{BASE}/").mock(return_value=httpx.Response(503))
    with httpx.Client() as client, pytest.raises(nexgddp.ClimateSourceError):
        nexgddp.list_keys(client, BASE, "x/")


def test_the_newest_version_of_each_year_wins() -> None:
    keys = [key(1995), key(1995, "_v2.0"), key(1995, "_v1.1"), key(1996), "README.txt"]
    assert nexgddp.pick_per_year(keys) == {1995: key(1995, "_v2.0"), 1996: key(1996)}


def test_cut_keeps_the_region_converts_units_and_drops_the_noon_stamp() -> None:
    region = nexgddp.cut(global_file("tasmax", 2001, kelvin=303.15), "tasmax", PIEMONTE)
    assert region.attrs["units"] == "degC"
    assert float(region.min()) == pytest.approx(30.0)
    assert float(region.lon.min()) >= PIEMONTE.west - 0.125
    assert float(region.lon.max()) <= PIEMONTE.east + 0.125
    assert str(region.time.values[0]).startswith("2001-01-01T00:00")


def test_cut_turns_rain_flux_into_millimetres_a_day() -> None:
    region = nexgddp.cut(global_file("pr", 2001), "pr", PIEMONTE)
    assert float(region.max()) == pytest.approx(8.64)


def test_cut_west_of_greenwich_uses_negative_longitudes() -> None:
    region = nexgddp.cut(global_file("tas", 2001), "tas", BBox(-1.0, 40.0, 1.0, 42.0))
    assert np.all((region.lon.values > -1.2) & (region.lon.values < 1.2))
    assert region.lon.values.min() < 0


def test_cut_outside_the_grid_is_an_error() -> None:
    with pytest.raises(nexgddp.ClimateSourceError):
        nexgddp.cut(global_file("tas", 2001), "tas", BBox(7.0, -80.0, 8.0, -70.0))


@respx.mock
def test_fetch_year_downloads_cuts_and_cleans_up(tmp_path: Path) -> None:
    source = tmp_path / "global.nc"
    global_file("tas", 2001, kelvin=273.15).to_netcdf(source, engine="h5netcdf")
    respx.get(f"{BASE}/{key(2001)}").mock(
        return_value=httpx.Response(200, content=source.read_bytes())
    )
    workdir = tmp_path / "work"
    workdir.mkdir()
    with httpx.Client() as client:
        region = nexgddp.fetch_year(client, BASE, key(2001), "tas", PIEMONTE, workdir)
    assert float(region.mean()) == pytest.approx(0.0, abs=1e-4)
    assert list(workdir.iterdir()) == []


@respx.mock
def test_fetch_year_starts_over_after_a_dropped_connection(tmp_path: Path) -> None:
    source = tmp_path / "global.nc"
    global_file("tas", 2001, kelvin=283.15).to_netcdf(source, engine="h5netcdf")
    route = respx.get(f"{BASE}/{key(2001)}").mock(
        side_effect=[
            httpx.ReadError("Connection reset by peer"),
            httpx.Response(503),
            httpx.Response(200, content=source.read_bytes()),
        ]
    )
    with httpx.Client() as client:
        region = nexgddp.fetch_year(client, BASE, key(2001), "tas", PIEMONTE, tmp_path, backoff_s=0)
    assert route.call_count == 3
    assert float(region.mean()) == pytest.approx(10.0, abs=1e-4)


@respx.mock
def test_fetch_year_gives_up_after_its_attempts(tmp_path: Path) -> None:
    route = respx.get(f"{BASE}/{key(2001)}").mock(side_effect=httpx.ReadError("reset"))
    with httpx.Client() as client, pytest.raises(nexgddp.ClimateSourceError, match="reset"):
        nexgddp.fetch_year(client, BASE, key(2001), "tas", PIEMONTE, tmp_path, backoff_s=0)
    assert route.call_count == 4


@respx.mock
def test_fetch_year_does_not_retry_a_missing_file(tmp_path: Path) -> None:
    route = respx.get(f"{BASE}/{key(2001)}").mock(return_value=httpx.Response(404))
    with httpx.Client() as client, pytest.raises(nexgddp.ClimateSourceError):
        nexgddp.fetch_year(client, BASE, key(2001), "tas", PIEMONTE, tmp_path, backoff_s=0)
    assert route.call_count == 1


@respx.mock
def test_fetch_year_of_a_broken_file_is_a_source_error(tmp_path: Path) -> None:
    respx.get(f"{BASE}/{key(2001)}").mock(return_value=httpx.Response(200, content=b"nope"))
    with httpx.Client() as client, pytest.raises(nexgddp.ClimateSourceError):
        nexgddp.fetch_year(client, BASE, key(2001), "tas", PIEMONTE, tmp_path)


def test_the_real_file_names_parse() -> None:
    real = (
        "NEX-GDDP-CMIP6/EC-Earth3/ssp245/r1i1p1f1/sfcWind/"
        "sfcWind_day_EC-Earth3_ssp245_r1i1p1f1_gr_2050_v2.0.nc"
    )
    match = nexgddp.KEY.search(real)
    assert match is not None
    assert (match["var"], match["experiment"], match["year"], match["version"]) == (
        "sfcWind",
        "ssp245",
        "2050",
        "2.0",
    )
    assert isinstance(xr.Dataset(), xr.Dataset)
