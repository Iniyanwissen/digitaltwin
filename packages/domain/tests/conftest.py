from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def raw_config() -> dict:
    return yaml.safe_load((REPO_ROOT / "config" / "simulation.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def write_config(tmp_path: Path):
    def _write(data: dict) -> Path:
        (tmp_path / "simulation.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
        return tmp_path

    return _write
