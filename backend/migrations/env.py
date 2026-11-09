import os

from alembic import context
from sqlalchemy import create_engine

from app.infrastructure.db import normalise_url
from app.infrastructure.models import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return normalise_url(config.attributes.get("url") or os.getenv("DATABASE_ADMIN_URL")
                         or os.getenv("DATABASE_URL", "sqlite:///./data/vla.db"))


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=_url().startswith("sqlite"))
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=connection.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(_url())
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata,
                          render_as_batch=conn.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
