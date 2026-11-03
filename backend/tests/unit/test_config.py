import pytest

from jugrid.config import Settings


def test_the_database_url_is_built_from_parts_with_the_password_escaped() -> None:
    settings = Settings(db_host="db.internal", db_user="jugrid", db_password="p@ss/word:1")
    assert settings.database_url == (
        "postgresql+psycopg://jugrid:p%40ss%2Fword%3A1@db.internal:5432/jugrid?sslmode=require"
    )


def test_without_a_host_the_url_is_used_as_given() -> None:
    url = "postgresql+psycopg://a:b@127.0.0.1:5432/c"
    assert Settings(database_url=url).database_url == url


@pytest.mark.parametrize("years", [1, 20, 30])
def test_scenarios_keep_their_length_and_centre_on_2050(years: int) -> None:
    baseline, middle, high = Settings(period_years=years).scenarios
    assert baseline.end_year == 2014
    assert baseline.end_year - baseline.start_year + 1 == years
    assert middle.end_year - middle.start_year + 1 == years
    assert middle.start_year <= 2050 <= middle.end_year
    assert (middle.start_year, middle.end_year) == (high.start_year, high.end_year)


def test_s3_stores_get_the_endpoint_and_local_ones_nothing() -> None:
    s3 = Settings(store_url="s3://jugrid/climate.zarr", s3_endpoint_url="http://seaweedfs:8333")
    assert s3.storage_options()["endpoint_url"] == "http://seaweedfs:8333"
    assert Settings(store_url="data/climate.zarr").storage_options() == {}
