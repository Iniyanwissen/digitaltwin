from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from twin_server.api import create_app
from twin_server.db import run_migrations
from twin_server.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]


def make_settings(data_dir: Path) -> Settings:
    return Settings(
        _env_file=None,
        config_dir=REPO_ROOT / "config",
        data_dir=data_dir,
        heartbeat_interval_s=0.05,
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path / "data")


@pytest.fixture(scope="session")
def client(tmp_path_factory: pytest.TempPathFactory):
    """Read-only client over one seeded database, shared across tests."""
    settings = make_settings(tmp_path_factory.mktemp("api") / "data")
    run_migrations(settings.resolved_database_url)
    with TestClient(create_app(settings)) as test_client:
        yield test_client
