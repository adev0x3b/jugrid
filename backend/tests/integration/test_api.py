import csv
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from jugrid import db
from jugrid.config import Settings
from tests.integration.conftest import asset_id

pytestmark = pytest.mark.integration


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_meta_describes_scenarios_hazards_and_sources(client: TestClient) -> None:
    meta = client.get("/api/meta").json()
    assert meta["region"] == "Piemonte"
    assert [s["key"] for s in meta["scenarios"]] == ["baseline", "ssp245_2050", "ssp585_2050"]
    assert {h["key"] for h in meta["hazards"]} == {
        "heat",
        "heavy_rain",
        "wind",
        "wet_snow",
        "flood",
    }
    flood = next(h for h in meta["hazards"] if h["key"] == "flood")
    assert flood["projected"] is False
    assert meta["vulnerability"]["cable"]["wind"] == 0
    assert len(meta["sources"]) == 3


class TestAssets:
    def test_are_geojson_coloured_by_the_chosen_view(self, client: TestClient) -> None:
        response = client.get("/api/assets", params={"scenario": "baseline", "view": "flood"})
        assert response.headers["content-type"].startswith("application/geo+json")
        features = response.json()["features"]
        assert len(features) == 6
        cabin = next(f for f in features if f["properties"]["name"] == "Cabina Lingotto")
        assert cabin["geometry"]["type"] == "Point"
        assert cabin["properties"]["level"] == "very_high"
        # The riskiest are drawn last, on top.
        scores = [f["properties"]["score"] or 0 for f in features]
        assert scores == sorted(scores)

    def test_filter_by_kind(self, client: TestClient) -> None:
        features = client.get(
            "/api/assets", params=[("kind", "line"), ("kind", "minor_line")]
        ).json()["features"]
        assert {f["properties"]["kind"] for f in features} == {"line", "minor_line"}

    @pytest.mark.parametrize(
        "params", [{"scenario": "ssp126_2100"}, {"view": "hail"}, {"kind": "pylon"}]
    )
    def test_unknown_choices_are_422(self, client: TestClient, params: dict[str, str]) -> None:
        assert client.get("/api/assets", params=params).status_code == 422


class TestAssetDetail:
    def test_has_every_scenario_and_a_link_to_osm(
        self, client: TestClient, session: Session
    ) -> None:
        line = asset_id(session, "way", 401)
        body = client.get(f"/api/assets/{line}").json()
        assert body["osm_url"] == "https://www.openstreetmap.org/way/401"
        assert body["operator"] == "Terna"
        assert body["voltage_kv"] == 132
        assert len(body["risks"]) == 18
        wind_2050 = next(
            r for r in body["risks"] if (r["scenario"], r["hazard"]) == ("ssp585_2050", "wind")
        )
        assert wind_2050 == {
            "scenario": "ssp585_2050",
            "hazard": "wind",
            "value": 14.0,
            "score": 1.0,
            "level": "very_high",
            "flooded_km": None,
        }

    def test_an_unknown_id_is_404(self, client: TestClient) -> None:
        assert client.get("/api/assets/999999").status_code == 404

    @pytest.mark.parametrize("asset", ["0", "-1", str(2**63), "1e3"])
    def test_ids_the_database_cannot_hold_are_422_not_500(
        self, client: TestClient, asset: str
    ) -> None:
        assert client.get(f"/api/assets/{asset}").status_code == 422


def test_summary_counts_assets_per_kind_and_level(client: TestClient) -> None:
    rows = {r["kind"]: r for r in client.get("/api/summary").json()}
    assert list(rows) == ["line", "minor_line", "cable", "substation", "plant"]
    assert rows["substation"]["count"] == 2
    assert sum(rows["substation"]["levels"].values()) == 2
    assert rows["line"]["length_km"] > 0


class TestRanking:
    def test_puts_the_most_exposed_first(self, client: TestClient) -> None:
        ranked = client.get("/api/ranking", params={"view": "flood"}).json()
        assert ranked[0]["name"] == "Cabina Lingotto"
        assert ranked[0]["score"] == 1.0

    def test_by_change_puts_the_fastest_growing_risk_first(self, client: TestClient) -> None:
        ranked = client.get(
            "/api/ranking", params={"scenario": "ssp585_2050", "order": "change", "limit": 3}
        ).json()
        assert len(ranked) == 3
        changes = [r["change"] for r in ranked]
        assert changes == sorted(changes, reverse=True)
        assert ranked[0]["kind"] == "line"  # the line reaching the stormy east

    def test_limit_is_bounded(self, client: TestClient) -> None:
        assert client.get("/api/ranking", params={"limit": 1000}).status_code == 422


class TestGrid:
    def test_serves_the_climate_cells_from_the_zarr_store(self, client: TestClient) -> None:
        cells = client.get("/api/grid/heat", params={"scenario": "ssp585_2050"}).json()
        assert len(cells["features"]) == 9
        first = cells["features"][0]
        assert first["properties"] == {"value": 16.0, "score": 0.8, "level": "very_high"}
        ring = first["geometry"]["coordinates"][0]
        assert ring[0] == ring[-1]

    def test_flood_has_no_climate_grid(self, client: TestClient) -> None:
        assert client.get("/api/grid/flood").status_code == 404


class TestExport:
    def test_is_one_csv_row_per_asset_with_every_hazard(
        self, client: TestClient, session: Session
    ) -> None:
        response = client.get("/api/export.csv", params={"scenario": "ssp245_2050"})
        assert response.headers["content-disposition"] == (
            'attachment; filename="jugrid-ssp245_2050.csv"'
        )
        rows = list(csv.DictReader(io.StringIO(response.text)))
        assert len(rows) == 6
        assert {"flood_value", "wind_score", "overall_score", "lon", "lat"} <= set(rows[0])

    def test_names_that_look_like_formulas_are_defused(
        self, client: TestClient, session: Session
    ) -> None:
        session.execute(text("UPDATE assets SET name = '=HYPERLINK(\"x\")' WHERE osm_id = 402"))
        session.commit()
        body = client.get("/api/export.csv").text
        assert "'=HYPERLINK" in body
        assert ",=HYPERLINK" not in body


def test_openapi_is_served_without_a_page_that_loads_scripts_from_a_cdn(
    client: TestClient,
) -> None:
    assert client.get("/api/openapi.json").json()["info"]["title"] == "JuGrid API"
    assert client.get("/api/docs").status_code == 404


def test_a_kind_repeated_many_times_is_one_kind(client: TestClient) -> None:
    once = client.get("/api/ranking", params={"kind": "substation"}).json()
    many = client.get("/api/ranking", params=[("kind", "substation")] * 400).json()
    assert many == once


class TestCaching:
    @pytest.mark.parametrize(
        "path", ["/api/meta", "/api/assets", "/api/summary", "/api/ranking", "/api/grid/heat"]
    )
    def test_data_may_be_kept_for_a_few_minutes(self, client: TestClient, path: str) -> None:
        assert client.get(path).headers["cache-control"] == "public, max-age=300"

    def test_health_and_errors_are_never_kept(self, client: TestClient) -> None:
        assert client.get("/api/health").headers["cache-control"] == "no-store"
        assert client.get("/api/ranking?limit=0").headers["cache-control"] == "no-store"


class TestTheApiOnlyReads:
    def test_its_connections_refuse_writes(self, scored: Settings) -> None:
        engine = db.engine(scored.database_url, read_only=True)
        with engine.connect() as conn, pytest.raises(DBAPIError, match="read-only transaction"):
            conn.execute(text("DELETE FROM assets"))

    def test_on_rds_it_signs_in_with_a_token_as_a_role_that_can_only_read(
        self, scored: Settings, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Stand in for RDS: give the role a password and have the token be that password.
        session.execute(text("ALTER ROLE jugrid_api PASSWORD 'token-123'"))
        session.commit()
        monkeypatch.setattr(db, "rds_token", lambda host, port, user, region: "token-123")
        url = make_url(scored.database_url).set(username="jugrid_api", password=None)
        engine = db.engine(url.render_as_string(hide_password=False), iam_region="eu-south-1")
        try:
            with engine.connect() as conn:
                assert conn.execute(text("SELECT count(*) FROM assets")).scalar_one() == 6
                with pytest.raises(DBAPIError, match="permission denied"):
                    conn.execute(text("DELETE FROM assets"))
        finally:
            engine.dispose()
            session.execute(text("ALTER ROLE jugrid_api PASSWORD NULL"))
            session.commit()


class TestRequestLogs:
    def test_every_answer_carries_a_request_id(self, client: TestClient) -> None:
        response = client.get("/api/meta")
        assert len(response.headers["x-request-id"]) == 32

    def test_a_plain_request_id_from_the_caller_is_kept(self, client: TestClient) -> None:
        response = client.get("/api/meta", headers={"X-Request-Id": "trace-42"})
        assert response.headers["x-request-id"] == "trace-42"

    def test_a_request_is_logged_with_its_status_and_duration(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("INFO", logger="jugrid.api")
        client.get("/api/assets/999999", headers={"X-Request-Id": "trace-43"})
        [record] = [r for r in caplog.records if r.name == "jugrid.api"]
        fields = record.fields  # type: ignore[attr-defined]
        assert fields["method"] == "GET"
        assert fields["path"] == "/api/assets/999999"
        assert fields["status"] == 404
        assert fields["duration_ms"] >= 0
        assert record.request_id == "trace-43"  # type: ignore[attr-defined]

    def test_health_checks_are_not_logged(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("INFO", logger="jugrid.api")
        client.get("/api/health")
        assert not [r for r in caplog.records if r.name == "jugrid.api"]
