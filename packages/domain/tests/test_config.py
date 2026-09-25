import copy
from pathlib import Path

import pytest

from workplace_domain.config import ConfigError, config_content_hash, load_simulation_config

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_repo_config_is_valid() -> None:
    config = load_simulation_config(REPO_ROOT / "config")
    assert config.employees.count > 0
    assert config.simulation.speed in config.simulation.allowed_speeds


def test_hash_is_stable_and_content_sensitive(raw_config, write_config) -> None:
    a = load_simulation_config(write_config(raw_config))
    b = load_simulation_config(write_config(copy.deepcopy(raw_config)))
    assert config_content_hash(a) == config_content_hash(b)

    raw_config["seed"] += 1
    c = load_simulation_config(write_config(raw_config))
    assert config_content_hash(c) != config_content_hash(a)


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda c: c["employees"]["work_mode_mix"].update(OFFICE=0.5), "must sum to 1.0"),
        (lambda c: c.update(timezone="Mars/Olympus"), "unknown timezone"),
        (lambda c: c["simulation"].update(speed=7), "not in allowed_speeds"),
        (lambda c: c["anomalies"].update(late_event_probability=1.5), "anomalies"),
        (lambda c: c["meetings"].update(no_shw_probability=0.1), "Extra inputs"),
        (lambda c: c["attendance"]["weekday_factor"].update(FUNDAY=1.0), "unknown weekday"),
        (lambda c: c["simulation"]["core_hours"].update(start="19:00"), "before core_hours.end"),
        (lambda c: c.pop("seed"), "seed"),
    ],
)
def test_invalid_config_fails_with_readable_error(raw_config, write_config, mutate, expected):
    mutate(raw_config)
    with pytest.raises(ConfigError) as exc_info:
        load_simulation_config(write_config(raw_config))
    message = str(exc_info.value)
    assert "Invalid configuration" in message
    assert expected in message


def test_missing_file(tmp_path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_simulation_config(tmp_path)


def test_unparseable_yaml(tmp_path) -> None:
    (tmp_path / "simulation.yaml").write_text("seed: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="Cannot parse"):
        load_simulation_config(tmp_path)
