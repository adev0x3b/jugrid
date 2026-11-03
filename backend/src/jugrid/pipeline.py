"""The ingest steps: assets, climate, flood, and scoring every asset."""

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import xarray as xr
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry.base import BaseGeometry
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from jugrid.db import AssetRow, RiskRow, RunRow
from jugrid.geo import length_km
from jugrid.risk.exposure import GridSampler
from jugrid.risk.hazards import AssetKind, Hazard, Scenario
from jugrid.risk.scoring import asset_score, overall_score
from jugrid.sources.jrcflood import FloodSampler
from jugrid.sources.overpass import Asset

log = logging.getLogger(__name__)

INDICATOR_OF: dict[Hazard, str] = {
    Hazard.HEAT: "hot_days",
    Hazard.HEAVY_RAIN: "wettest_day",
    Hazard.WIND: "windiest_day",
    Hazard.WET_SNOW: "wet_snow_days",
}
OVERALL = "overall"


@contextmanager
def recorded(session: Session, step: str) -> Iterator[RunRow]:
    """Log a step in ``ingest_runs``, as done with its detail or failed with the error."""
    run = RunRow(step=step, status="running")
    session.add(run)
    session.commit()
    try:
        yield run
    except BaseException as error:
        # The run log is public (/api/meta): it names the kind of failure, the logs say the rest.
        log.exception("ingest step %s failed", step)
        session.rollback()
        run.status, run.detail = "failed", f"{type(error).__name__}; see the ingest logs"
        run.finished_at = datetime.now(UTC)
        session.add(run)
        session.commit()
        raise
    run.status, run.finished_at = "done", datetime.now(UTC)
    session.add(run)
    session.commit()


def store_assets(session: Session, assets: Sequence[Asset]) -> int:
    """Insert or update every asset and drop the ones OpenStreetMap no longer has."""
    if not assets:
        raise ValueError("no assets: refusing to empty the map")
    rows = [
        {
            "osm_type": a.osm_type,
            "osm_id": a.osm_id,
            "kind": a.kind.value,
            "name": a.name,
            "operator": a.operator,
            "voltage_kv": a.voltage_kv,
            "length_km": round(length_km(a.geometry), 3),
            "geom": from_shape(a.geometry, srid=4326),
            "tags": dict(a.tags),
        }
        for a in assets
    ]
    for start in range(0, len(rows), 1000):
        chunk = rows[start : start + 1000]
        statement = insert(AssetRow).values(chunk)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=["osm_type", "osm_id"],
                set_={
                    column: statement.excluded[column]
                    for column in (
                        "kind",
                        "name",
                        "operator",
                        "voltage_kv",
                        "length_km",
                        "geom",
                        "tags",
                    )
                },
            )
        )
    keep = {(a.osm_type, a.osm_id) for a in assets}
    existing = session.execute(select(AssetRow.id, AssetRow.osm_type, AssetRow.osm_id)).all()
    gone = [row.id for row in existing if (row.osm_type, row.osm_id) not in keep]
    if gone:
        session.execute(delete(AssetRow).where(AssetRow.id.in_(gone)))
    session.flush()
    return len(rows)


def risks_for(
    kind: AssetKind,
    geometry: BaseGeometry,
    climate: dict[str, float | None],
    flood: tuple[float | None, float] | None,
) -> list[dict[str, Any]]:
    """One row per hazard plus the overall row, for one asset in one scenario."""
    rows: list[dict[str, Any]] = []
    scores: dict[Hazard, float | None] = {}
    for hazard, indicator in INDICATOR_OF.items():
        value = climate.get(indicator)
        scores[hazard] = asset_score(kind, hazard, value)
        rows.append(
            {"hazard": hazard.value, "value": value, "score": scores[hazard], "flooded_km": None}
        )
    depth, wet_km = flood if flood is not None else (None, 0.0)
    scores[Hazard.FLOOD] = asset_score(kind, Hazard.FLOOD, depth)
    rows.append(
        {
            "hazard": Hazard.FLOOD.value,
            "value": depth,
            "score": scores[Hazard.FLOOD],
            "flooded_km": wet_km if geometry.geom_type != "Point" else None,
        }
    )
    worst = overall_score(scores)
    rows.append({"hazard": OVERALL, "value": worst, "score": worst, "flooded_km": None})
    return rows


def score_assets(
    session: Session,
    indicators: xr.Dataset,
    scenarios: Sequence[Scenario],
    flood: FloodSampler | None,
) -> int:
    """Recompute every asset's risks in every scenario. Returns how many rows were written."""
    samplers = {
        s.key: GridSampler(indicators.sel(scenario=s.key), list(INDICATOR_OF.values()))
        for s in scenarios
        if s.key in indicators["scenario"].values
    }
    assets = session.execute(select(AssetRow.id, AssetRow.kind, AssetRow.geom)).all()
    rows: list[dict[str, Any]] = []
    for asset_id, kind, geom in assets:
        geometry = to_shape(geom)
        flood_exposure = flood.exposure(geometry) if flood is not None else None
        for key, sampler in samplers.items():
            for row in risks_for(
                AssetKind(kind), geometry, sampler.sample(geometry), flood_exposure
            ):
                rows.append({"asset_id": asset_id, "scenario": key, **row})
    session.execute(delete(RiskRow))
    for start in range(0, len(rows), 5000):
        session.execute(insert(RiskRow).values(rows[start : start + 5000]))
    session.flush()
    log.info("scored %d assets in %d scenarios", len(assets), len(samplers))
    return len(rows)
