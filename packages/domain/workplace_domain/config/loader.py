"""Load and validate config/simulation.yaml, failing fast with a readable message."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from workplace_domain.config.schema import SimulationConfig

SIMULATION_CONFIG_FILE = "simulation.yaml"


class ConfigError(Exception):
    """Raised when a configuration file is missing, unparseable or invalid."""


def _format_validation_error(path: Path, exc: ValidationError) -> str:
    lines = [f"Invalid configuration in {path} ({exc.error_count()} problem(s)):"]
    for err in exc.errors():
        location = ".".join(str(part) for part in err["loc"]) or "<root>"
        lines.append(f"  - {location}: {err['msg']}")
    return "\n".join(lines)


def load_simulation_config(config_dir: Path) -> SimulationConfig:
    path = config_dir / SIMULATION_CONFIG_FILE
    if not path.is_file():
        raise ConfigError(f"Configuration file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Cannot parse {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a YAML mapping at the top level")
    try:
        return SimulationConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(path, exc)) from exc


def config_content_hash(config: SimulationConfig) -> str:
    """Stable hash of the resolved config, used for run snapshots and cache keys."""
    canonical = json.dumps(config.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
