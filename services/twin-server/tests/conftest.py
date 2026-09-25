from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from twin_server.api import create_app
from twin_server.db import run_migrations
from twin_server.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        config_dir=REPO_ROOT / "config",
        data_dir=tmp_path / "data",
        heartbeat_interval_s=0.05,
    )


@pytest.fixture
def client(settings: Settings):
    run_migrations(settings.resolved_database_url)
    with TestClient(create_app(settings)) as test_client:
        yield test_client
