from pathlib import Path

import httpx
import pytest
import respx

from jugrid.geo import BBox
from jugrid.sources import http, jrcflood, nexgddp, overpass

PIEMONTE = BBox(6.62, 44.06, 9.22, 46.47)


@respx.mock
def test_a_redirect_to_plain_http_is_refused() -> None:
    respx.post("https://overpass.test/api").mock(
        return_value=httpx.Response(302, headers={"location": "http://evil.test/api"})
    )
    evil = respx.post("http://evil.test/api").mock(return_value=httpx.Response(200, json={}))
    with http.client() as client, pytest.raises(overpass.OverpassError, match="HTTPS"):
        overpass.fetch(client, "https://overpass.test/api", "IT-21")
    assert not evil.called


@respx.mock
def test_a_plain_http_source_is_refused_before_any_request() -> None:
    route = respx.get("http://flood.test/tile_extents.geojson").mock(httpx.Response(200))
    with http.client() as client, pytest.raises(jrcflood.FloodSourceError, match="HTTPS"):
        jrcflood.fetch_tiles(client, "http://flood.test", 100, PIEMONTE, Path("/nonexistent"))
    assert not route.called


@respx.mock
def test_https_redirects_are_followed_and_send_the_user_agent() -> None:
    respx.get("https://a.test/x").mock(
        return_value=httpx.Response(301, headers={"location": "https://b.test/x"})
    )
    final = respx.get("https://b.test/x").mock(return_value=httpx.Response(200, text="ok"))
    with http.client() as client:
        assert client.get("https://a.test/x").text == "ok"
    assert final.calls.last.request.headers["user-agent"] == http.USER_AGENT


@respx.mock
def test_a_climate_file_larger_than_the_limit_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(http, "MAX_DOWNLOAD_BYTES", 10)
    respx.get("https://nasa.test/k.nc").mock(return_value=httpx.Response(200, content=b"x" * 64))
    with httpx.Client() as client, pytest.raises(nexgddp.ClimateSourceError, match="larger"):
        nexgddp.fetch_year(client, "https://nasa.test", "k.nc", "tas", PIEMONTE, tmp_path)


@respx.mock
def test_a_flood_tile_that_says_it_is_too_large_is_refused_and_left_nowhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(http, "MAX_DOWNLOAD_BYTES", 10)
    respx.get("https://jrc.test/t.tif").mock(
        return_value=httpx.Response(200, headers={"content-length": "64"}, content=b"x" * 64)
    )
    dest = tmp_path / "t.tif"
    with httpx.Client() as client, pytest.raises(jrcflood.FloodSourceError, match="larger"):
        jrcflood._download(client, "https://jrc.test/t.tif", dest)
    assert list(tmp_path.iterdir()) == []
