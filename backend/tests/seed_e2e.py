"""Seed a running stack with the test fixture for the browser tests.

Usage: docker compose exec -T api python - < backend/tests/seed_e2e.py

Loads the six fixture assets around Turin and a synthetic climate grid, then scores them.
No network: the browser tests must not depend on OpenStreetMap or NASA being up.
"""

import sys

import numpy as np
import xarray as xr
from sqlalchemy import text

from jugrid import pipeline
from jugrid.cli import ensure_bucket
from jugrid.climate.store import ClimateStore, open_store
from jugrid.config import Settings
from jugrid.db import session_factory
from jugrid.sources import overpass


def node(osm_id: int, lat: float, lon: float, **tags: str) -> dict[str, object]:
    return {"type": "node", "id": osm_id, "lat": lat, "lon": lon, "tags": tags}


def way(osm_id: int, coords: list[tuple[float, float]], **tags: str) -> dict[str, object]:
    geometry = [{"lat": lat, "lon": lon} for lat, lon in coords]
    return {"type": "way", "id": osm_id, "geometry": geometry, "tags": tags}


FIXTURE = {
    "elements": [
        node(101, 45.05, 7.65, power="substation", name="Cabina Lingotto", voltage="132000"),
        node(102, 45.11, 7.70, power="substation", name="Stazione Torino Nord", voltage="380000"),
        node(103, 44.91, 7.92, power="plant", name="Centrale idroelettrica"),
        way(
            401,
            [(45.05, 7.65), (45.1, 7.7), (45.2, 7.8)],
            power="line",
            voltage="132000",
            operator="Terna",
        ),
        way(402, [(45.0, 7.6), (45.01, 7.61)], power="minor_line", voltage="15000"),
        way(403, [(45.06, 7.66), (45.07, 7.67)], power="cable", location="underground"),
    ]
}

settings = Settings()
lats, lons = np.array([44.875, 45.125, 45.375]), np.array([7.375, 7.625, 7.875])
keys = [s.key for s in settings.scenarios]
shape = (len(keys), lats.size, lons.size)


def per_scenario(*values: float) -> np.ndarray:
    return np.stack([np.full(shape[1:], v) for v in values])


grid = xr.Dataset(
    {
        "hot_days": (
            ("scenario", "lat", "lon"),
            np.stack([np.full(shape[1:], v) for v in (4, 10, 16)]),
        ),
        "wettest_day": (("scenario", "lat", "lon"), np.full(shape, 70.0)),
        "windiest_day": (
            ("scenario", "lat", "lon"),
            np.stack([np.full(shape[1:], v) for v in (7, 9, 12)]),
        ),
        "wet_snow_days": (("scenario", "lat", "lon"), np.full(shape, 1.0)),
    },
    coords={"scenario": keys, "lat": lats, "lon": lons},
).astype("float32")

ensure_bucket(settings)
with session_factory(settings.database_url)() as session:
    session.execute(text("TRUNCATE assets, asset_risks, ingest_runs RESTART IDENTITY CASCADE"))
    pipeline.store_assets(session, list(overpass.parse(FIXTURE)))
    ClimateStore(open_store(settings.store_url, settings.storage_options())).write_indicators(grid)
    pipeline.score_assets(session, grid, settings.scenarios, flood=None)
    session.commit()
print("seeded", file=sys.stderr)
