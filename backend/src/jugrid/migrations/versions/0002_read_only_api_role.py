"""A read-only role for the API.

On RDS the API signs in as ``jugrid_api`` with an IAM token (``rds_iam``), so it holds no
password and can only read. Elsewhere the role exists without a way to sign in.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"

API_ROLE = "jugrid_api"


def upgrade() -> None:
    op.execute(f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{API_ROLE}') THEN
            CREATE ROLE {API_ROLE} LOGIN;
          END IF;
          IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'rds_iam') THEN
            GRANT rds_iam TO {API_ROLE};
          END IF;
        END
        $$
    """)
    op.execute(f"GRANT USAGE ON SCHEMA public TO {API_ROLE}")
    op.execute(f"GRANT SELECT ON assets, asset_risks, ingest_runs TO {API_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE ALL ON assets, asset_risks, ingest_runs FROM {API_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {API_ROLE}")
