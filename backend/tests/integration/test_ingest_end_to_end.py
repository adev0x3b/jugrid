"""``jugrid ingest`` against every source, each answered by a local stand-in."""

import json
import re
from pathlib import Path

import httpx
import numpy as np
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jugrid.cli import run
from jugrid.config import Settings
from jugrid.db import RiskRow, RunRow
from tests.factories import global_file
from tests.integration.conftest import FIXTURES
from tests.unit.test_exposure import write_tile

pytestmark = pytest.mark.integration
NEX = "https://nex.test"
JRC = "https://jrc.test"
OVERPASS = "https://overpass.test/api/interpreter"


@pytest.fixture
def sources(tmp_path: Path) -> respx.MockRouter:
    files: dict[str, bytes] = {}
    for variable in ("tasmax", "tas", "pr", "sfcWind"):
        path = tmp_path / f"{variable}.nc"
        global_file(variable, 2014).to_netcdf(path, engine="h5netcdf")
        files[variable] = path.read_bytes()

    def listing(request: httpx.Request) -> httpx.Response:
        prefix = request.url.params["prefix"]
        _, model, experiment, member, variable, _ = prefix.split("/")
        year = 2014 if experiment == "historical" else 2050
        key = f"{prefix}{variable}_day_{model}_{experiment}_{member}_gr_{year}_v2.0.nc"
        return httpx.Response(
            200,
            text='<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<IsTruncated>false</IsTruncated><Contents><Key>{key}</Key></Contents>"
            "</ListBucketResult>",
        )

    def netcdf(request: httpx.Request) -> httpx.Response:
        variable = request.url.path.split("/")[5]
        return httpx.Response(200, content=files[variable])

    depth = np.full((100, 100), -9999.0)
    depth[94:96, 64:66] = 1.5
    tile = tmp_path / "tile.tif"
    write_tile(tile, depth, 7.0, 46.0, 0.01)
    index = {
        "features": [
            {
                "properties": {"id": 114, "name": "N50_W0"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 40], [10, 40], [10, 50], [0, 50], [0, 40]]],
                },
            }
        ]
    }

    router = respx.mock(assert_all_called=False)
    router.post(OVERPASS).respond(json=json.loads((FIXTURES / "overpass.json").read_text()))
    router.get(f"{NEX}/").mock(side_effect=listing)
    router.get(url__regex=rf"^{re.escape(NEX)}/NEX-GDDP-CMIP6/.+\.nc$").mock(side_effect=netcdf)
    router.get(f"{JRC}/tile_extents.geojson").respond(json=index)
    router.get(f"{JRC}/RP100/ID114_N50_W0_RP100_depth.tif").respond(content=tile.read_bytes())
    return router


def test_ingest_all_fills_the_map_from_the_sources(
    settings: Settings, session: Session, sources: respx.MockRouter
) -> None:
    configured = settings.model_copy(
        update={"overpass_url": OVERPASS, "nexgddp_url": NEX, "flood_url": JRC}
    )
    with sources:
        run(configured, ("assets", "climate", "score"))
        assert [str(r.pattern) for r in sources.routes if not r.called] == []

    runs = {r.step: r for r in session.scalars(select(RunRow))}
    assert {step: r.status for step, r in runs.items()} == {
        "assets": "done",
        "climate": "done",
        "score": "done",
    }
    assert runs["assets"].detail == "6 assets from OpenStreetMap (IT-21)"
    assert runs["climate"].detail is not None
    assert runs["climate"].detail.startswith("12 new variable-years")
    assert session.scalar(select(func.count()).select_from(RiskRow)) == 6 * 3 * 6

    # A second run downloads nothing new: every year is already in the store.
    with sources:
        run(configured, ("climate",))
        assert not any(c.request.url.path.endswith(".nc") for c in sources.calls)
    latest = session.scalars(
        select(RunRow).where(RunRow.step == "climate").order_by(RunRow.id.desc())
    ).first()
    assert latest is not None
    assert latest.detail is not None
    assert latest.detail.startswith("0 new variable-years")


def test_a_failing_source_marks_the_step_failed(settings: Settings, session: Session) -> None:
    configured = settings.model_copy(update={"overpass_url": OVERPASS})
    with respx.mock() as router:
        router.post(OVERPASS).respond(504)
        with pytest.raises(Exception, match="Overpass"):
            run(configured, ("assets",))
    session.expire_all()
    failed = session.scalars(select(RunRow)).one()
    assert failed.status == "failed"
    assert "504" in (failed.detail or "")
