"""Tables and the engine."""

from datetime import datetime
from functools import cache
from typing import Any

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

KINDS = "('line', 'minor_line', 'cable', 'substation', 'plant')"
HAZARD_KEYS = "('heat', 'heavy_rain', 'wind', 'wet_snow', 'flood', 'overall')"


class Base(DeclarativeBase):
    pass


class AssetRow(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("osm_type", "osm_id"),
        CheckConstraint(f"kind IN {KINDS}", name="assets_kind"),
        CheckConstraint("osm_type IN ('node', 'way', 'relation')", name="assets_osm_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    osm_type: Mapped[str] = mapped_column(String(8))
    osm_id: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str | None] = mapped_column(Text)
    operator: Mapped[str | None] = mapped_column(Text)
    voltage_kv: Mapped[float | None] = mapped_column(Float)
    length_km: Mapped[float] = mapped_column(Float, default=0.0)
    geom: Mapped[WKBElement] = mapped_column(Geometry(srid=4326, spatial_index=True))
    tags: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RiskRow(Base):
    __tablename__ = "asset_risks"
    __table_args__ = (
        CheckConstraint(f"hazard IN {HAZARD_KEYS}", name="asset_risks_hazard"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 1", name="asset_risks_score"),
        Index("asset_risks_ranking", "scenario", "hazard", "score"),
    )

    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True
    )
    scenario: Mapped[str] = mapped_column(String(32), primary_key=True)
    hazard: Mapped[str] = mapped_column(String(16), primary_key=True)
    value: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float)
    flooded_km: Mapped[float | None] = mapped_column(Float)


class RunRow(Base):
    __tablename__ = "ingest_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'done', 'failed')", name="ingest_runs_status"),
        Index("ingest_runs_step_started", "step", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    step: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(8), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail: Mapped[str | None] = mapped_column(Text)


def rds_token(host: str, port: int, user: str, region: str) -> str:
    """A 15-minute RDS sign-in token, signed with the task's IAM role. No network call."""
    import botocore.session  # type: ignore[import-untyped]  # noqa: PLC0415 - only on AWS

    client = botocore.session.get_session().create_client("rds", region_name=region)
    token: str = client.generate_db_auth_token(host, port, user)
    return token


@cache
def engine(url: str, *, read_only: bool = False, iam_region: str | None = None) -> Engine:
    """One pool per database. With ``read_only`` Postgres refuses every write on it; with
    ``iam_region`` each new connection signs in with a fresh IAM token."""
    connect_args = {"options": "-c default_transaction_read_only=on"} if read_only else {}
    made = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    if iam_region:

        @event.listens_for(made, "do_connect")
        def _sign_in(_dialect: Any, _record: Any, _args: Any, params: dict[str, Any]) -> None:
            params["password"] = rds_token(
                made.url.host or "", made.url.port or 5432, made.url.username or "", iam_region
            )

    return made


def session_factory(
    url: str, *, read_only: bool = False, iam_region: str | None = None
) -> sessionmaker:  # type: ignore[type-arg]
    return sessionmaker(
        engine(url, read_only=read_only, iam_region=iam_region), expire_on_commit=False
    )
