from alembic import context

from jugrid.config import Settings
from jugrid.db import Base, engine

config = context.config
url = config.get_main_option("sqlalchemy.url") or Settings().database_url

with engine(url).connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
