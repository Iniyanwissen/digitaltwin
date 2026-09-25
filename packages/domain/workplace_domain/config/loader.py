"""Load and validate the YAML configuration, failing fast with a readable message."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from workplace_domain.config.layout import LayoutFile, LayoutPresetsFile
from workplace_domain.config.organization import OrganizationConfig
from workplace_domain.config.schema import SimulationConfig

SIMULATION_CONFIG_FILE = "simulation.yaml"
ORGANIZATION_CONFIG_FILE = "organization.yaml"
LAYOUT_PRESETS_FILE = "layout_presets.yaml"


class ConfigError(Exception):
    """Raised when a configuration file is missing, unparseable or invalid."""


def _format_validation_error(path: Path, exc: ValidationError) -> str:
    lines = [f"Invalid configuration in {path} ({exc.error_count()} problem(s)):"]
    for err in exc.errors():
        location = ".".join(str(part) for part in err["loc"]) or "<root>"
        lines.append(f"  - {location}: {err['msg']}")
    return "\n".join(lines)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"Configuration file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Cannot parse {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a YAML mapping at the top level")
    return raw


def load_model[M: BaseModel](path: Path, model: type[M]) -> M:
    raw = _read_yaml(path)
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(path, exc)) from exc


def load_simulation_config(config_dir: Path) -> SimulationConfig:
    return load_model(config_dir / SIMULATION_CONFIG_FILE, SimulationConfig)


def load_layout_presets(config_dir: Path) -> LayoutPresetsFile:
    return load_model(config_dir / LAYOUT_PRESETS_FILE, LayoutPresetsFile)


def _hash(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def config_content_hash(config: SimulationConfig) -> str:
    """Stable hash of the simulation config alone."""
    return _hash(config.model_dump(mode="json"))


@dataclass(frozen=True)
class WorkplaceConfig:
    """Everything the system reads from config/: simulation, organization and layouts."""

    simulation: SimulationConfig
    organization: OrganizationConfig
    layouts: tuple[LayoutFile, ...]
    content_hash: str

    def as_json(self) -> dict[str, Any]:
        return {
            "simulation": self.simulation.model_dump(mode="json"),
            "organization": self.organization.model_dump(mode="json"),
            "layouts": [layout.model_dump(mode="json") for layout in self.layouts],
        }


def load_workplace_config(config_dir: Path) -> WorkplaceConfig:
    simulation = load_simulation_config(config_dir)
    organization = load_model(config_dir / ORGANIZATION_CONFIG_FILE, OrganizationConfig)
    layouts = tuple(
        load_model(config_dir / rel, LayoutFile) for rel in simulation.office.layout_files
    )
    ids = [layout.building.building_id for layout in layouts]
    if len(set(ids)) != len(ids):
        raise ConfigError(f"Duplicate building_id across layout files: {ids}")
    payload = {
        "simulation": simulation.model_dump(mode="json"),
        "organization": organization.model_dump(mode="json"),
        "layouts": [layout.model_dump(mode="json") for layout in layouts],
    }
    return WorkplaceConfig(simulation, organization, layouts, _hash(payload))
