import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from twin_server.__main__ import main
from twin_server.api import create_app
from twin_server.settings import Settings
from workplace_domain.config import ConfigError

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_health_reports_all_components(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["components"]) == {
        "config",
        "database",
        "event_bus",
        "state_store",
        "simulation_engine",
        "event_processor",
    }
    assert body["components"]["database"]["info"]["schema_revision"] == "0001_baseline"


def test_health_is_down_without_migrations(settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["components"]["database"]["status"] == "down"


def test_meta_summarizes_config(client) -> None:
    body = client.get("/api/v1/meta").json()
    assert body["config"]["timezone"] == "Asia/Kolkata"
    assert body["config"]["default_speed"] in body["config"]["allowed_speeds"]
    assert len(body["config"]["content_hash"]) == 64


def test_invalid_config_fails_fast(tmp_path, monkeypatch, capsys) -> None:
    bad_dir = tmp_path / "config"
    shutil.copytree(REPO_ROOT / "config", bad_dir)
    path = bad_dir / "simulation.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("seed: 12345", "seed: -1"))

    monkeypatch.setenv("CONFIG_DIR", str(bad_dir))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    assert main(["migrate"]) == 2
    err = capsys.readouterr().err
    assert "Configuration error" in err
    assert "seed" in err

    with pytest.raises(ConfigError):
        create_app(Settings(_env_file=None))
