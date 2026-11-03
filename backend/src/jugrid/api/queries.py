"""Read-only questions the API asks the database. GeoJSON is built by PostGIS."""

import csv
import io
from collections.abc import Sequence
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from jugrid.risk.hazards import LEVEL_BOUNDS, AssetKind, Hazard, Level

LEVEL_SQL = (
    "CASE WHEN {s} IS NULL THEN NULL "
    + " ".join(f"WHEN {{s}} < {bound} THEN '{name.value}'" for bound, name in LEVEL_BOUNDS)
    + f" ELSE '{Level.VERY_HIGH.value}' END"
)


def level_sql(column: str) -> str:
    return LEVEL_SQL.replace("{s}", column)


def assets_geojson(session: Session, scenario: str, view: str, kinds: Sequence[str]) -> str:
    """Every asset of the given kinds as a FeatureCollection, the riskiest drawn last."""
    statement = text(f"""
        SELECT json_build_object(
          'type', 'FeatureCollection',
          'features', coalesce(json_agg(json_build_object(
            'type', 'Feature',
            'id', a.id,
            'geometry', ST_AsGeoJSON(a.geom, 5)::json,
            'properties', json_build_object(
              'id', a.id, 'kind', a.kind, 'name', a.name, 'voltage_kv', a.voltage_kv,
              'score', r.score, 'level', {level_sql("r.score")})
          ) ORDER BY r.score ASC NULLS FIRST), '[]'::json)
        )::text
        FROM assets a
        LEFT JOIN asset_risks r
          ON r.asset_id = a.id AND r.scenario = :scenario AND r.hazard = :view
        WHERE a.kind IN :kinds
    """).bindparams(bindparam("kinds", expanding=True))
    return str(
        session.execute(
            statement, {"scenario": scenario, "view": view, "kinds": list(kinds)}
        ).scalar_one()
    )


def asset_detail(session: Session, asset_id: int) -> dict[str, Any] | None:
    row = (
        session.execute(
            text("""
            SELECT id, osm_type, osm_id, kind, name, operator, voltage_kv, length_km, tags,
                   ST_AsGeoJSON(geom, 5)::json AS geometry,
                   ST_X(ST_PointOnSurface(geom)) AS lon, ST_Y(ST_PointOnSurface(geom)) AS lat
            FROM assets WHERE id = :id
        """),
            {"id": asset_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    risks = (
        session.execute(
            text(f"""
            SELECT scenario, hazard, value, score, flooded_km, {level_sql("score")} AS level
            FROM asset_risks WHERE asset_id = :id ORDER BY scenario, hazard
        """),
            {"id": asset_id},
        )
        .mappings()
        .all()
    )
    return {**row, "risks": [dict(r) for r in risks]}


def summary(session: Session, scenario: str) -> list[dict[str, Any]]:
    """Per kind of asset: how many there are, how long, and how many at each level."""
    rows = (
        session.execute(
            text(f"""
            SELECT a.kind, {level_sql("r.score")} AS level,
                   count(*) AS count, coalesce(sum(a.length_km), 0) AS length_km
            FROM assets a
            LEFT JOIN asset_risks r
              ON r.asset_id = a.id AND r.scenario = :scenario AND r.hazard = 'overall'
            GROUP BY 1, 2
        """),
            {"scenario": scenario},
        )
        .mappings()
        .all()
    )
    by_kind: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = by_kind.setdefault(
            row["kind"],
            {
                "kind": row["kind"],
                "count": 0,
                "length_km": 0.0,
                "levels": {level.value: 0 for level in Level} | {"unknown": 0},
            },
        )
        entry["count"] += row["count"]
        entry["length_km"] = round(entry["length_km"] + row["length_km"], 1)
        entry["levels"][row["level"] or "unknown"] += row["count"]
    order = {kind.value: i for i, kind in enumerate(AssetKind)}
    return sorted(by_kind.values(), key=lambda e: order.get(e["kind"], 99))


def ranking(
    session: Session, scenario: str, view: str, kinds: Sequence[str], by_change: bool, limit: int
) -> list[dict[str, Any]]:
    """The most exposed assets, or those whose risk grows the most from today."""
    order = "change DESC NULLS LAST" if by_change else "r.score DESC NULLS LAST"
    statement = text(f"""
        SELECT a.id, a.kind, a.name, a.operator, a.voltage_kv, a.length_km,
               r.value, r.score, {level_sql("r.score")} AS level,
               b.score AS baseline_score, r.score - b.score AS change
        FROM asset_risks r
        JOIN assets a ON a.id = r.asset_id
        LEFT JOIN asset_risks b
          ON b.asset_id = r.asset_id AND b.scenario = 'baseline' AND b.hazard = r.hazard
        WHERE r.scenario = :scenario AND r.hazard = :view AND r.score IS NOT NULL
          AND a.kind IN :kinds
        ORDER BY {order}, a.voltage_kv DESC NULLS LAST, a.id
        LIMIT :limit
    """).bindparams(bindparam("kinds", expanding=True))
    rows = (
        session.execute(
            statement, {"scenario": scenario, "view": view, "kinds": list(kinds), "limit": limit}
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


def export_csv(session: Session, scenario: str) -> str:
    """Every asset with every hazard's value and score in one scenario, for a spreadsheet."""
    hazards = [h.value for h in Hazard] + ["overall"]
    pivots = ", ".join(
        f"max(r.value) FILTER (WHERE r.hazard = '{h}') AS {h}_value, "
        f"max(r.score) FILTER (WHERE r.hazard = '{h}') AS {h}_score"
        for h in hazards
    )
    rows = session.execute(
        text(f"""
            SELECT a.id, a.osm_type, a.osm_id, a.kind, a.name, a.operator, a.voltage_kv,
                   a.length_km,
                   round(ST_X(ST_PointOnSurface(a.geom))::numeric, 5) AS lon,
                   round(ST_Y(ST_PointOnSurface(a.geom))::numeric, 5) AS lat,
                   {pivots}
            FROM assets a
            LEFT JOIN asset_risks r ON r.asset_id = a.id AND r.scenario = :scenario
            GROUP BY a.id
            ORDER BY max(r.score) FILTER (WHERE r.hazard = 'overall') DESC NULLS LAST, a.id
        """),
        {"scenario": scenario},
    )
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(rows.keys())
    for row in rows:
        writer.writerow(_safe_cell(v) for v in row)
    return out.getvalue()


def _safe_cell(value: object) -> object:
    """Keep spreadsheet apps from running a name that starts like a formula."""
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@", "\t", "\r"}:
        return "'" + value
    return value


def last_runs(session: Session) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            text("""
            SELECT DISTINCT ON (step) step, status, started_at, finished_at, detail
            FROM ingest_runs ORDER BY step, started_at DESC
        """)
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]
