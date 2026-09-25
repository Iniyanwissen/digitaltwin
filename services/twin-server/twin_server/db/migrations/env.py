"""Alembic environment. Configured programmatically by twin_server.db.run_migrations."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

config = context.config
_url = config.get_main_option("sqlalchemy.url")
if not _url:
    raise RuntimeError("sqlalchemy.url is not set")
url: str = _url

target_metadata = None  # models arrive in Phase 2


def run_offline() -> None:
    context.configure(url=url, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    engine = create_engine(url)
    with engine.connect() as connection:
        # render_as_batch lets ALTER TABLE migrations work on SQLite.
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
