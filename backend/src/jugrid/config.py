"""Settings, read from ``JUGRID_*`` environment variables."""

from functools import cached_property
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from jugrid.geo import BBox
from jugrid.risk.hazards import Scenario


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JUGRID_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://jugrid:jugrid@127.0.0.1:5432/jugrid"
    # On AWS the parts come separately, the password from Secrets Manager.
    db_host: str | None = None
    db_port: int = 5432
    db_name: str = "jugrid"
    db_user: str = "jugrid"
    db_password: SecretStr | None = None
    # Sign in with a short-lived IAM token instead of a password (RDS only).
    db_iam_auth: bool = False

    # Where the Zarr store lives: a local path, or s3://bucket/key.zarr
    store_url: str = "data/climate.zarr"
    s3_endpoint_url: str | None = None  # SeaweedFS in compose; unset on AWS
    aws_region: str = "eu-south-1"
    cache_dir: Path = Path("data/cache")

    # The region: an ISO 3166-2 code for OpenStreetMap and a box for the climate grid.
    region_name: str = "Piemonte"
    region_iso: str = "IT-21"
    region_bbox: str = "6.62,44.06,9.22,46.47"

    overpass_url: str = "https://overpass-api.de/api/interpreter"
    nexgddp_url: str = "https://nex-gddp-cmip6.s3.us-west-2.amazonaws.com"
    climate_model: str = "EC-Earth3"
    climate_member: str = "r1i1p1f1"
    period_years: int = Field(default=20, ge=1, le=30)
    download_workers: int = Field(default=4, ge=1, le=16)
    flood_url: str = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard"
    flood_return_period: int = 100

    cors_origins: list[str] = []

    @model_validator(mode="after")
    def _database_from_parts(self) -> Settings:
        if self.db_host:
            user = quote(self.db_user, safe="")
            if not self.db_iam_auth and self.db_password:
                user += ":" + quote(self.db_password.get_secret_value(), safe="")
            self.database_url = (
                f"postgresql+psycopg://{user}@{self.db_host}:{self.db_port}/{self.db_name}"
                "?sslmode=require"
            )
        return self

    @cached_property
    def bbox(self) -> BBox:
        return BBox.parse(self.region_bbox)

    @cached_property
    def scenarios(self) -> tuple[Scenario, ...]:
        """Today's climate (the model's last 20 historical years) against 2050 under two paths."""
        n = self.period_years
        future_start = 2051 - (n + 1) // 2
        return (
            Scenario("baseline", f"Today ({2015 - n}-2014)", "historical", 2015 - n, 2014),
            Scenario(
                "ssp245_2050",
                f"2050, middle road (SSP2-4.5, {future_start}-{future_start + n - 1})",
                "ssp245",
                future_start,
                future_start + n - 1,
            ),
            Scenario(
                "ssp585_2050",
                f"2050, high emissions (SSP5-8.5, {future_start}-{future_start + n - 1})",
                "ssp585",
                future_start,
                future_start + n - 1,
            ),
        )

    def storage_options(self) -> dict[str, object]:
        if not self.store_url.startswith("s3://"):
            return {}
        options: dict[str, object] = {"client_kwargs": {"region_name": self.aws_region}}
        if self.s3_endpoint_url:
            options["endpoint_url"] = self.s3_endpoint_url
        return options
