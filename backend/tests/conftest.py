import os
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """One PostGIS container for the whole run, unless JUGRID_TEST_DATABASE_URL points at one."""
    if url := os.environ.get("JUGRID_TEST_DATABASE_URL"):
        yield url
        return
    from testcontainers.community.postgres import PostgresContainer  # noqa: PLC0415 - only without a URL

    image = os.environ.get("JUGRID_TEST_POSTGIS_IMAGE", "postgis/postgis:18-3.6")
    with PostgresContainer(image, driver="psycopg") as container:
        yield container.get_connection_url()
