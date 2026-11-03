"""Assets, their risks and the ingest log.

Revision ID: 0001
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "assets",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("osm_type", sa.String(8), nullable=False),
        sa.Column("osm_id", sa.BigInteger, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.Text),
        sa.Column("operator", sa.Text),
        sa.Column("voltage_kv", sa.Float),
        sa.Column("length_km", sa.Float, nullable=False, server_default="0"),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("osm_type", "osm_id"),
        sa.CheckConstraint(
            "kind IN ('line', 'minor_line', 'cable', 'substation', 'plant')", name="assets_kind"
        ),
        sa.CheckConstraint("osm_type IN ('node', 'way', 'relation')", name="assets_osm_type"),
    )
    op.create_index("ix_assets_kind", "assets", ["kind"])
    op.create_index("idx_assets_geom", "assets", ["geom"], postgresql_using="gist")
    op.create_table(
        "asset_risks",
        sa.Column(
            "asset_id",
            sa.BigInteger,
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("scenario", sa.String(32), primary_key=True),
        sa.Column("hazard", sa.String(16), primary_key=True),
        sa.Column("value", sa.Float),
        sa.Column("score", sa.Float),
        sa.Column("flooded_km", sa.Float),
        sa.CheckConstraint(
            "hazard IN ('heat', 'heavy_rain', 'wind', 'wet_snow', 'flood', 'overall')",
            name="asset_risks_hazard",
        ),
        sa.CheckConstraint("score IS NULL OR score BETWEEN 0 AND 1", name="asset_risks_score"),
    )
    op.create_index("asset_risks_ranking", "asset_risks", ["scenario", "hazard", "score"])
    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("step", sa.String(16), nullable=False),
        sa.Column("status", sa.String(8), nullable=False, server_default="running"),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("detail", sa.Text),
        sa.CheckConstraint("status IN ('running', 'done', 'failed')", name="ingest_runs_status"),
    )
    op.create_index("ingest_runs_step_started", "ingest_runs", ["step", "started_at"])


def downgrade() -> None:
    op.drop_table("ingest_runs")
    op.drop_table("asset_risks")
    op.drop_table("assets")
