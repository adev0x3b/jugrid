import json
from pathlib import Path
from typing import ClassVar

import httpx
import pytest
import respx
from shapely.geometry import Point

from jugrid.risk.hazards import AssetKind
from jugrid.sources import overpass

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "overpass.json").read_text())
URL = "https://overpass.example/api/interpreter"


def test_query_asks_for_the_region_by_its_iso_code() -> None:
    text = overpass.query("IT-21")
    assert 'area["ISO3166-2"="IT-21"]' in text
    assert "minor_line" in text
    assert "substation" in text


@pytest.mark.parametrize("code", ["it-21", 'IT-21"];out;', "Piemonte"])
def test_query_refuses_anything_that_is_not_a_code(code: str) -> None:
    with pytest.raises(ValueError, match="ISO 3166-2"):
        overpass.query(code)


@pytest.mark.parametrize(
    ("raw", "kv"),
    [
        ("132000", 132),
        ("380000;132000", 380),
        ("15000; 400", 15),
        ("unknown", None),
        (None, None),
        # Values JSON cannot carry or that make no sense are dropped, not stored.
        ("nan", None),
        ("inf;132000", 132),
        ("-1", None),
        ("0", None),
    ],
)
def test_voltage_is_the_highest_one_in_kv(raw: str | None, kv: float | None) -> None:
    assert overpass.parse_voltage_kv(raw) == kv


class TestParse:
    assets: ClassVar = {(a.osm_type, a.osm_id): a for a in overpass.parse(FIXTURE)}

    def test_keeps_sites_lines_and_cables_and_drops_towers(self) -> None:
        kinds = {key: a.kind for key, a in self.assets.items()}
        assert kinds == {
            ("node", 101): AssetKind.SUBSTATION,
            ("way", 201): AssetKind.SUBSTATION,
            ("relation", 301): AssetKind.PLANT,
            ("way", 401): AssetKind.LINE,
            ("way", 402): AssetKind.MINOR_LINE,
            ("way", 403): AssetKind.CABLE,
        }

    def test_sites_become_points_and_lines_stay_lines(self) -> None:
        site = self.assets[("way", 201)].geometry
        assert isinstance(site, Point)
        assert site.geom_type == "Point"
        assert site.x == pytest.approx(7.701)
        assert site.y == pytest.approx(45.101)
        assert self.assets[("relation", 301)].geometry.geom_type == "Point"
        assert self.assets[("way", 401)].geometry.geom_type == "LineString"

    def test_reads_name_operator_and_voltage(self) -> None:
        cabin = self.assets[("node", 101)]
        assert (cabin.name, cabin.operator, cabin.voltage_kv) == (
            "Cabina Lingotto",
            "e-distribuzione",
            132,
        )

    def test_without_elements_is_an_error(self) -> None:
        with pytest.raises(overpass.OverpassError):
            list(overpass.parse({"remark": "nothing"}))


@respx.mock
def test_fetch_posts_the_query_and_parses_the_answer() -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=FIXTURE))
    with httpx.Client() as client:
        assets = overpass.fetch(client, URL, "IT-21")
    assert len(assets) == 6
    assert b"IT-21" in route.calls.last.request.content


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(504, text="Gateway Timeout"),
        httpx.Response(200, text="<html>busy</html>"),
        httpx.Response(200, json={"elements": [], "remark": "runtime error: Query timed out"}),
    ],
)
def test_fetch_failures_are_one_exception_type(response: httpx.Response) -> None:
    respx.post(URL).mock(return_value=response)
    with httpx.Client() as client, pytest.raises(overpass.OverpassError):
        overpass.fetch(client, URL, "IT-21")
