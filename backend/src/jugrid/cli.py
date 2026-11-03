"""``jugrid``: migrate the database and run the ingest steps."""

import argparse
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from alembic import command
from alembic.config import Config

from jugrid import logs, pipeline
from jugrid.climate import ingest
from jugrid.climate.store import ClimateStore, open_store
from jugrid.config import Settings
from jugrid.db import session_factory
from jugrid.sources import http, jrcflood, overpass

STEPS = ("assets", "climate", "score")


def migrate(settings: Settings) -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")


def ensure_bucket(settings: Settings) -> None:
    """Create the store's bucket on a local S3 (SeaweedFS in compose); on AWS it exists."""
    if not (settings.store_url.startswith("s3://") and settings.s3_endpoint_url):
        return
    import s3fs  # noqa: PLC0415 - only for local S3

    fs = s3fs.S3FileSystem(**settings.storage_options())
    bucket = settings.store_url.removeprefix("s3://").split("/", 1)[0]
    if not fs.exists(bucket):
        fs.mkdir(bucket)


def climate_store(settings: Settings) -> ClimateStore:
    return ClimateStore(open_store(settings.store_url, settings.storage_options()))


def run(settings: Settings, steps: Sequence[str]) -> None:
    make_session = session_factory(settings.database_url)
    store = climate_store(settings)
    with http.client() as client:
        if "assets" in steps:
            with make_session() as session, pipeline.recorded(session, "assets") as record:
                assets = overpass.fetch(client, settings.overpass_url, settings.region_iso)
                count = pipeline.store_assets(session, assets)
                session.commit()
                record.detail = f"{count} assets from OpenStreetMap ({settings.region_iso})"
        if "climate" in steps:
            ensure_bucket(settings)
            with make_session() as session, pipeline.recorded(session, "climate") as record:
                settings.cache_dir.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(dir=settings.cache_dir) as workdir:
                    fetch = ingest.nexgddp_fetcher(
                        client,
                        settings.nexgddp_url,
                        settings.climate_model,
                        settings.climate_member,
                        settings.bbox,
                        Path(workdir),
                    )
                    written = ingest.fill(
                        store, settings.scenarios, fetch, workers=settings.download_workers
                    )
                result = ingest.compute(store, settings.scenarios, settings.climate_model)
                record.detail = (
                    f"{written} new variable-years; indicators on "
                    f"{result.sizes['lat']}x{result.sizes['lon']} cells"
                )
        if "score" in steps:
            with make_session() as session, pipeline.recorded(session, "score") as record:
                indicators = store.read_indicators()
                if indicators is None:
                    raise SystemExit("no climate indicators yet: run `jugrid ingest climate`")
                tiles = jrcflood.fetch_tiles(
                    client,
                    settings.flood_url,
                    settings.flood_return_period,
                    settings.bbox,
                    settings.cache_dir / "flood",
                )
                with jrcflood.FloodSampler(tiles) as flood:
                    rows = pipeline.score_assets(session, indicators, settings.scenarios, flood)
                session.commit()
                record.detail = f"{rows} risk rows"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jugrid", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="bring the database schema up to date")
    ingest_parser = sub.add_parser("ingest", help="fetch sources and score the assets")
    ingest_parser.add_argument(
        "steps",
        nargs="*",
        choices=[*STEPS, "all"],
        default=["all"],
        help="assets (OpenStreetMap), climate (NEX-GDDP-CMIP6), score (with the flood maps)",
    )
    args = parser.parse_args(argv)
    settings = Settings()
    logs.configure(settings.log_format)
    if args.command == "migrate":
        migrate(settings)
    else:
        steps = STEPS if "all" in args.steps else tuple(args.steps)
        migrate(settings)
        run(settings, steps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
