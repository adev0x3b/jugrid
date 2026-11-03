"""The HTTP API under ``/api``. Read-only: data changes only through ``jugrid ingest``."""

import json
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from typing import Annotated, Any

import numpy as np
import xarray as xr
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from jugrid.api import queries
from jugrid.api.schemas import (
    AssetOut,
    HazardOut,
    KindSummary,
    Meta,
    RankedAsset,
    RunOut,
    ScenarioOut,
    SourceOut,
)
from jugrid.climate.store import ClimateStore, open_store
from jugrid.config import Settings
from jugrid.db import session_factory
from jugrid.pipeline import INDICATOR_OF
from jugrid.risk.hazards import (
    HAZARDS,
    VULNERABILITY,
    AssetKind,
    Hazard,
    RiskView,
    ScenarioKey,
)
from jugrid.risk.scoring import hazard_score, level

SOURCES = [
    SourceOut(
        name="OpenStreetMap contributors (power assets)",
        url="https://www.openstreetmap.org/copyright",
        license="ODbL 1.0",
    ),
    SourceOut(
        name="NASA NEX-GDDP-CMIP6, EC-Earth3 (daily climate projections)",
        url="https://registry.opendata.aws/nex-gddp-cmip6/",
        license="CC BY 4.0",
    ),
    SourceOut(
        name="Copernicus EMS / JRC global river flood hazard maps",
        url="https://data.jrc.ec.europa.eu/collection/id-0054",
        license="ODbL 1.0",
    ),
]

Kinds = Annotated[list[AssetKind] | None, Query(alias="kind")]

# The data only changes when an ingest runs (monthly), so browsers and CloudFront may keep an
# answer for a few minutes; that is also what absorbs a burst of requests.
CACHE_CONTROL = "public, max-age=300"


class IndicatorCache:
    """The indicators read from the Zarr store, kept for a minute between reads."""

    def __init__(self, store: ClimateStore, ttl_s: float = 60.0) -> None:
        self._store, self._ttl = store, ttl_s
        self._value: xr.Dataset | None = None
        self._read_at = -1e9
        self._lock = threading.Lock()

    def get(self) -> xr.Dataset | None:
        with self._lock:
            if time.monotonic() - self._read_at > self._ttl:
                self._value = self._store.read_indicators()
                self._read_at = time.monotonic()
            return self._value


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    # The API only reads: Postgres refuses any write on its connections.
    make_session = session_factory(
        settings.database_url,
        read_only=True,
        iam_region=settings.aws_region if settings.db_iam_auth else None,
    )
    indicators = IndicatorCache(
        ClimateStore(open_store(settings.store_url, settings.storage_options()))
    )
    app = FastAPI(
        title="JuGrid API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(GZipMiddleware, minimum_size=2048)

    @app.middleware("http")
    async def cache_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if "cache-control" not in response.headers:
            cacheable = request.method == "GET" and response.status_code in {200, 404}
            response.headers["Cache-Control"] = CACHE_CONTROL if cacheable else "no-store"
        return response

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET"]
        )

    def session() -> Iterator[Session]:
        with make_session() as s:
            yield s

    Db = Annotated[Session, Depends(session)]  # noqa: N806

    def kinds_or_all(kinds: list[AssetKind] | None) -> list[str]:
        return [k.value for k in (kinds or list(AssetKind))]

    @app.get("/api/health")
    def health(db: Db, response: Response) -> dict[str, str]:
        db.execute(text("SELECT 1"))
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok"}

    @app.get("/api/meta")
    def meta(db: Db) -> Meta:
        bbox = settings.bbox
        return Meta(
            region=settings.region_name,
            bbox=(bbox.west, bbox.south, bbox.east, bbox.north),
            climate_model=settings.climate_model,
            scenarios=[
                ScenarioOut(key=s.key, label=s.label, start_year=s.start_year, end_year=s.end_year)
                for s in settings.scenarios
            ],
            hazards=[
                HazardOut(
                    key=h.hazard.value,
                    label=h.label,
                    indicator=h.indicator,
                    unit=h.unit,
                    low=h.low,
                    high=h.high,
                    projected=h.climate,
                )
                for h in HAZARDS.values()
            ],
            kinds=[k.value for k in AssetKind],
            vulnerability={
                k.value: {h.value: w for h, w in weights.items()}
                for k, weights in VULNERABILITY.items()
            },
            sources=SOURCES,
            runs=[RunOut(**r) for r in queries.last_runs(db)],
        )

    @app.get(
        "/api/assets",
        response_class=Response,
        responses={200: {"content": {"application/geo+json": {}}}},
    )
    def assets(
        db: Db,
        kinds: Kinds = None,
        scenario: ScenarioKey = ScenarioKey.BASELINE,
        view: RiskView = RiskView.OVERALL,
    ) -> Response:
        body = queries.assets_geojson(db, scenario.value, view.value, kinds_or_all(kinds))
        return Response(body, media_type="application/geo+json")

    @app.get("/api/assets/{asset_id}")
    def asset(asset_id: Annotated[int, Path(ge=1, le=2**63 - 1)], db: Db) -> AssetOut:
        found = queries.asset_detail(db, asset_id)
        if found is None:
            raise HTTPException(404, "No asset with that id")
        return AssetOut(
            osm_url=f"https://www.openstreetmap.org/{found['osm_type']}/{found['osm_id']}",
            **found,
        )

    @app.get("/api/summary")
    def summary(db: Db, scenario: ScenarioKey = ScenarioKey.BASELINE) -> list[KindSummary]:
        return [KindSummary(**row) for row in queries.summary(db, scenario.value)]

    @app.get("/api/ranking")
    def ranking(
        db: Db,
        kinds: Kinds = None,
        scenario: ScenarioKey = ScenarioKey.BASELINE,
        view: RiskView = RiskView.OVERALL,
        order: Annotated[str, Query(pattern="^(score|change)$")] = "score",
        limit: Annotated[int, Query(ge=1, le=200)] = 20,
    ) -> list[RankedAsset]:
        rows = queries.ranking(
            db, scenario.value, view.value, kinds_or_all(kinds), order == "change", limit
        )
        return [RankedAsset(**row) for row in rows]

    @app.get(
        "/api/grid/{hazard}",
        response_class=Response,
        responses={200: {"content": {"application/geo+json": {}}}},
    )
    def grid(hazard: Hazard, scenario: ScenarioKey = ScenarioKey.BASELINE) -> Response:
        if hazard not in INDICATOR_OF:
            raise HTTPException(404, "This hazard has no climate grid")
        data = indicators.get()
        if data is None or scenario.value not in data["scenario"].values:
            raise HTTPException(404, "No climate data yet: run the ingest first")
        layer = data[INDICATOR_OF[hazard]].sel(scenario=scenario.value)
        return Response(_cells_geojson(layer, hazard), media_type="application/geo+json")

    @app.get(
        "/api/export.csv", response_class=Response, responses={200: {"content": {"text/csv": {}}}}
    )
    def export(db: Db, scenario: ScenarioKey = ScenarioKey.BASELINE) -> Response:
        return Response(
            queries.export_csv(db, scenario.value),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="jugrid-{scenario.value}.csv"'},
        )

    return app


def _cells_geojson(layer: xr.DataArray, hazard: Hazard) -> str:
    lats, lons = layer["lat"].values, layer["lon"].values
    half_lat = float(np.abs(np.diff(lats)).min()) / 2 if lats.size > 1 else 0.125
    half_lon = float(np.abs(np.diff(lons)).min()) / 2 if lons.size > 1 else 0.125
    values = layer.transpose("lat", "lon").values
    features: list[dict[str, Any]] = []
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            value = float(values[i, j])
            if not np.isfinite(value):
                continue
            w, e = round(lon - half_lon, 4), round(lon + half_lon, 4)
            s, n = round(lat - half_lat, 4), round(lat + half_lat, 4)
            score = hazard_score(hazard, value)
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
                    },
                    "properties": {"value": round(value, 2), "score": score, "level": level(score)},
                }
            )
    return json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":"))


def app_factory() -> FastAPI:
    return create_app()
