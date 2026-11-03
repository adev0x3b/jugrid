import json
from dataclasses import replace

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from jugrid import pipeline
from jugrid.config import Settings
from jugrid.db import AssetRow, RiskRow, RunRow
from jugrid.sources import overpass
from tests.integration.conftest import FIXTURES, asset_id

pytestmark = pytest.mark.integration


def fixture_assets() -> list[overpass.Asset]:
    return list(overpass.parse(json.loads((FIXTURES / "overpass.json").read_text())))


class TestStoreAssets:
    def test_inserts_then_updates_in_place_and_drops_what_osm_lost(self, session: Session) -> None:
        assets = fixture_assets()
        assert pipeline.store_assets(session, assets) == 6
        line_id = asset_id(session, "way", 401)

        kept = [
            replace(a, name="Linea Torino-Chivasso")
            if (a.osm_type, a.osm_id) == ("way", 401)
            else a
            for a in assets
            if (a.osm_type, a.osm_id) != ("node", 101)
        ]
        pipeline.store_assets(session, kept)
        session.commit()

        assert session.scalar(select(func.count()).select_from(AssetRow)) == 5
        assert asset_id(session, "way", 401) == line_id  # same row, not a new one
        assert session.scalar(select(AssetRow.name).where(AssetRow.id == line_id)) == (
            "Linea Torino-Chivasso"
        )

    def test_lines_get_their_length_as_postgis_measures_it(self, session: Session) -> None:
        pipeline.store_assets(session, fixture_assets())
        ours, postgis = session.execute(
            text(
                "SELECT length_km, ST_Length(geom::geography) / 1000 FROM assets "
                "WHERE osm_type = 'way' AND osm_id = 401"
            )
        ).one()
        assert ours == pytest.approx(postgis, rel=0.005)

    def test_refuses_to_empty_the_map(self, session: Session) -> None:
        with pytest.raises(ValueError, match="no assets"):
            pipeline.store_assets(session, [])


class TestScoring:
    def test_every_asset_gets_every_hazard_and_overall_in_every_scenario(
        self, scored: Settings, session: Session
    ) -> None:
        rows = session.scalar(select(func.count()).select_from(RiskRow))
        assert rows == 6 * 3 * 6

    def test_the_flooded_cabin_scores_on_flood(self, scored: Settings, session: Session) -> None:
        cabin = asset_id(session, "node", 101)
        flood = session.execute(
            select(RiskRow.value, RiskRow.score).where(
                RiskRow.asset_id == cabin, RiskRow.scenario == "baseline", RiskRow.hazard == "flood"
            )
        ).one()
        assert flood.value == pytest.approx(1.5)
        assert flood.score == pytest.approx(1.0)  # substations take flood at full weight

    def test_the_line_into_the_windy_east_is_worst_on_wind_in_2050(
        self, scored: Settings, session: Session
    ) -> None:
        line = asset_id(session, "way", 401)
        risks = dict(
            session.execute(
                select(RiskRow.hazard, RiskRow.score).where(
                    RiskRow.asset_id == line, RiskRow.scenario == "ssp585_2050"
                )
            ).all()
        )
        assert risks["wind"] == pytest.approx(1.0)
        assert risks["overall"] == pytest.approx(1.0)

    def test_underground_cables_ignore_wind(self, scored: Settings, session: Session) -> None:
        cable = asset_id(session, "way", 403)
        wind = session.scalar(
            select(RiskRow.score).where(
                RiskRow.asset_id == cable,
                RiskRow.scenario == "ssp585_2050",
                RiskRow.hazard == "wind",
            )
        )
        assert wind == 0


class TestRecorded:
    def test_a_finished_step_is_done(self, session: Session) -> None:
        with pipeline.recorded(session, "assets") as run:
            run.detail = "6 assets"
        row = session.scalars(select(RunRow)).one()
        assert (row.status, row.detail) == ("done", "6 assets")
        assert row.finished_at is not None

    def test_a_failed_step_names_the_error_but_keeps_its_text_out_of_the_public_log(
        self, session: Session
    ) -> None:
        with pytest.raises(RuntimeError), pipeline.recorded(session, "climate"):
            raise RuntimeError("could not reach db.internal:5432 as jugrid")
        row = session.scalars(select(RunRow)).one()
        assert row.status == "failed"
        assert row.detail == "RuntimeError; see the ingest logs"


def test_the_schema_refuses_unknown_kinds(session: Session) -> None:
    with pytest.raises(Exception, match="assets_kind"):
        session.execute(
            text(
                "INSERT INTO assets (osm_type, osm_id, kind, geom) "
                "VALUES ('node', 1, 'pylon', ST_SetSRID(ST_MakePoint(7, 45), 4326))"
            )
        )
    session.rollback()
