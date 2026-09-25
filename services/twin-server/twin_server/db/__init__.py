"""SQLite (default) operational database: master, config, sim and ops data."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import Engine, create_engine, event, text

from workplace_domain.enums import ComponentStatus
from workplace_domain.interfaces import ComponentHealth

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def create_db_engine(url: str) -> Engine:
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


def run_migrations(url: str) -> None:
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


def check_database(engine: Engine) -> ComponentHealth:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:
        return ComponentHealth(ComponentStatus.DOWN, f"{type(exc).__name__}: {exc}")
    return ComponentHealth(
        ComponentStatus.OK,
        f"{engine.dialect.name} reachable",
        {"schema_revision": version or "none"},
    )
