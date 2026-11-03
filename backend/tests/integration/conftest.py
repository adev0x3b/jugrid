import json
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from jugrid import pipeline
from jugrid.api.app import create_app
from jugrid.cli import migrate
from jugrid.climate.store import ClimateStore, open_store
from jugrid.config import Settings
from jugrid.db import session_factory
from jugrid.sources import overpass
from jugrid.sources.jrcflood import FloodSampler
from tests.factories import LATS, LONS
from tests.unit.test_exposure import write_tile

FIXTURES = Path(__file__).parents[1] / "fixtures"
pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def migrated(database_url: str) -> str:
    migrate(Settings(database_url=database_url))
    return database_url


@pytest.fixture
def settings(migrated: str, tmp_path: Path) -> Settings:
    return Settings(
        database_url=migrated,
        store_url=str(tmp_path / "climate.zarr"),
        cache_dir=tmp_path / "cache",
        period_years=1,
    )


@pytest.fixture
def session(settings: Settings) -> Iterator[Session]:
    with session_factory(settings.database_url)() as s:
        s.execute(text("TRUNCATE assets, asset_risks, ingest_runs RESTART IDENTITY CASCADE"))
        s.commit()
        yield s


def indicator_grid(settings: Settings) -> xr.Dataset:
    """Turin's 3x3 cells: today mild, 2050 much hotter and windier in the east."""
    keys = [s.key for s in settings.scenarios]
    shape = (len(keys), LATS.size, LONS.size)
    hot = np.zeros(shape)
    hot[0] = 4.0
    hot[1] = 10.0
    hot[2] = 16.0
    wind = np.full(shape, 6.0)
    wind[2, :, 2] = 14.0
    return xr.Dataset(
        {
            "hot_days": (("scenario", "lat", "lon"), hot),
            "wettest_day": (("scenario", "lat", "lon"), np.full(shape, 60.0)),
            "windiest_day": (("scenario", "lat", "lon"), wind),
            "wet_snow_days": (("scenario", "lat", "lon"), np.zeros(shape)),
        },
        coords={"scenario": keys, "lat": LATS, "lon": LONS},
    ).astype("float32")


@pytest.fixture
def flood_tile(tmp_path: Path) -> Path:
    # Water 1.5 m deep around the Lingotto cabin (7.65 E, 45.05 N), dry elsewhere.
    depth = np.full((100, 100), -9999.0)
    depth[94:96, 64:66] = 1.5
    path = tmp_path / "flood.tif"
    write_tile(path, depth, 7.0, 46.0, 0.01)
    return path


@pytest.fixture
def scored(settings: Settings, session: Session, flood_tile: Path) -> Settings:
    """The fixture assets stored and scored against the synthetic grid and flood tile."""
    payload = json.loads((FIXTURES / "overpass.json").read_text())
    pipeline.store_assets(session, list(overpass.parse(payload)))
    grid = indicator_grid(settings)
    ClimateStore(open_store(settings.store_url)).write_indicators(grid)
    with FloodSampler([flood_tile]) as flood:
        pipeline.score_assets(session, grid, settings.scenarios, flood)
    session.commit()
    return settings


@pytest.fixture
def client(scored: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(scored)) as c:
        yield c


def asset_id(session: Session, osm_type: str, osm_id: int) -> int:
    return int(
        session.execute(
            text("SELECT id FROM assets WHERE osm_type = :t AND osm_id = :i"),
            {"t": osm_type, "i": osm_id},
        ).scalar_one()
    )
