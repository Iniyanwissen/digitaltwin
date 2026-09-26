"""Schemas for Live Simulation v2 (v0.3 pack): config/v2/simulation-v2.yaml and the floor plan.

v2 is a separate world next to v1: its own layout (real floor plan in metres), environment areas,
energy model and ESG automation. Shared behaviour still comes from config/simulation.yaml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workplace_domain.config.loader import ConfigError, load_model
from workplace_domain.enums import DeskPolicy, ZoneType

PositiveInt = Annotated[int, Field(gt=0)]
PositiveFloat = Annotated[float, Field(gt=0)]
NonNeg = Annotated[float, Field(ge=0)]
Hour = Annotated[float, Field(ge=0, le=24)]
Facade = Literal["N", "S", "E", "W"]
V2_CONFIG_FILE = Path("v2") / "simulation-v2.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ------------------------------------------------------------------ floor plan file (metres)


class PlanFloor(_Strict):
    floor_id: str
    name: str
    width: PositiveFloat
    height: PositiveFloat
    north: str
    glazing: list[Facade]
    desk_policy: DeskPolicy


class PlanZone(_Strict):
    zone_id: str
    code: str
    name: str
    zone_type: ZoneType
    x: NonNeg
    y: NonNeg
    w: PositiveFloat
    h: PositiveFloat
    facade: Facade | None = None
    capacity: PositiveInt | None = None
    is_restricted: bool = False


class PlanCore(_Strict):
    x: NonNeg
    y: NonNeg
    w: PositiveFloat
    h: PositiveFloat
    label: str


class PlanRoom(_Strict):
    room_id: str
    code: str
    name: str
    room_type: Literal[
        "SMALL_MEETING", "MEDIUM_MEETING", "LARGE_CONFERENCE", "AUDITORIUM", "FOCUS_BOOTH"
    ]
    x: NonNeg
    y: NonNeg
    w: PositiveFloat
    h: PositiveFloat
    capacity: PositiveInt
    zone_id: str
    has_badge_reader: bool
    has_panel: bool
    is_bookable: bool


class PlanWorkspace(_Strict):
    workspace_id: str
    zone_code: str
    zone_id: str
    x: NonNeg
    y: NonNeg
    w: PositiveFloat
    h: PositiveFloat
    facing: Facade


class PlanAccessPoint(_Strict):
    access_point_id: str
    reader_type: Literal["BUILDING_ENTRANCE", "FLOOR_LOBBY", "SECURE_ZONE", "ROOM_DOOR"]
    x: NonNeg
    y: NonNeg
    target_id: str


class FloorPlanFile(_Strict):
    version: str
    units: Literal["metres"]
    floor: PlanFloor
    zones: list[PlanZone] = Field(min_length=1)
    cores: list[PlanCore]
    rooms: list[PlanRoom]
    workspaces: list[PlanWorkspace]
    access_points: list[PlanAccessPoint]

    @model_validator(mode="after")
    def _references(self) -> FloorPlanFile:
        zone_ids = {z.zone_id for z in self.zones}
        bad = [w.workspace_id for w in self.workspaces if w.zone_id not in zone_ids]
        bad += [r.room_id for r in self.rooms if r.zone_id not in zone_ids]
        if bad:
            raise ValueError(f"unknown zone ids referenced by {bad[:5]}")
        return self


# ------------------------------------------------------------------ v2 config


class ReplaceZone(_Strict):
    name: str
    zone_type: ZoneType
    entrance_reader: bool = False


class FloorOverride(_Strict):
    replace_zone: dict[str, ReplaceZone] = Field(default_factory=dict)
    capacity_overrides: dict[str, PositiveInt] = Field(default_factory=dict)
    restricted_zones: list[str] = Field(default_factory=list)
    restricted_departments: list[str] = Field(default_factory=list)
    desk_policy: DeskPolicy | None = None


class V2Layout(_Strict):
    floor_plan_file: str
    floors: PositiveInt
    lobby_core: Annotated[int, Field(ge=0)]
    floor_overrides: dict[int, FloorOverride] = Field(default_factory=dict)


class V2Employees(_Strict):
    count: PositiveInt


class Daylight(_Strict):
    start_h: Hour
    end_h: Hour
    peak_h: Hour


class V2Environment(_Strict):
    tick_live_s: PositiveInt
    tick_batch_s: PositiveInt
    setpoint_c: dict[str, float]
    mean_reversion_per_min: dict[str, PositiveFloat]
    occupancy_heat_c: float
    max_load: PositiveFloat
    solar_gain_c: dict[Facade, float]
    daylight: Daylight
    co2_lpm_per_person: PositiveFloat
    ceiling_height_m: PositiveFloat
    ventilation_per_min: dict[str, PositiveFloat]
    outdoor_co2_ppm: PositiveFloat
    lux_full: PositiveFloat
    daylight_lux: NonNeg
    trend_window_min: PositiveInt
    initial: dict[str, float]
    temperature_noise_c: NonNeg
    co2_noise_ppm: NonNeg
    min_area_capacity: PositiveInt

    @model_validator(mode="after")
    def _modes(self) -> V2Environment:
        modes = {"ECO", "NORMAL", "HIGH", "PRECOOL"}
        for name, table in (
            ("setpoint_c", self.setpoint_c),
            ("mean_reversion_per_min", self.mean_reversion_per_min),
        ):
            if set(table) != modes:
                raise ValueError(f"environment.{name} needs exactly {sorted(modes)}")
        if set(self.ventilation_per_min) != modes | {"BOOST"}:
            raise ValueError("environment.ventilation_per_min needs the four modes and BOOST")
        return self


class V2Energy(_Strict):
    hvac_w_per_m2: dict[str, NonNeg]
    boost_w_per_m2: NonNeg
    lighting_w_per_m2: NonNeg
    operating_hours: tuple[Hour, Hour]
    night_baseline_w_per_m2: NonNeg
    grid_emission_factor_kg_per_kwh: NonNeg
    tariff_inr_per_kwh: NonNeg
    comfort_band_c: tuple[float, float]
    comfort_co2_ppm: PositiveFloat
    interval_minutes: PositiveInt


class V2Lights(_Strict):
    dim_empty_after_minutes: PositiveFloat
    dim_level_pct: Annotated[int, Field(ge=0, le=100)]
    room_off_after_minutes: PositiveFloat
    daylight_level_pct: Annotated[int, Field(ge=0, le=100)]
    daylight_min_factor: Annotated[float, Field(ge=0, le=1)]
    after_hours_off_h: Hour


class V2Rooms(_Strict):
    release_after_minutes: PositiveFloat
    precool_lead_minutes: PositiveFloat
    precool_min_expected_pct: Annotated[float, Field(ge=0, le=100)]
    oversized_max_pct: Annotated[float, Field(ge=0, le=100)]
    oversized_after_minutes: PositiveFloat
    over_capacity_after_minutes: PositiveFloat


class V2Bms(_Strict):
    enabled: bool
    cooldown_minutes: PositiveFloat
    eco_after_empty_minutes: PositiveFloat
    warm_threshold_c: float
    min_setpoint_c: float
    co2_boost_on_ppm: PositiveFloat
    co2_boost_off_ppm: PositiveFloat
    lights: V2Lights
    rooms: V2Rooms


class SimulationV2Config(_Strict):
    employees: V2Employees
    layout: V2Layout
    environment: V2Environment
    energy: V2Energy
    bms: V2Bms


def load_v2_config(config_dir: Path) -> tuple[SimulationV2Config, FloorPlanFile]:
    """Load config/v2/simulation-v2.yaml and the floor plan it points to (repo-root relative)."""
    cfg = load_model(config_dir / V2_CONFIG_FILE, SimulationV2Config)
    plan_path = config_dir.parent / cfg.layout.floor_plan_file
    if not plan_path.is_file():
        raise ConfigError(f"v2 floor plan not found: {plan_path}")
    try:
        plan = FloorPlanFile.model_validate_json(plan_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ConfigError(f"Invalid v2 floor plan {plan_path}: {exc}") from exc
    return cfg, plan


__all__ = ["FloorPlanFile", "SimulationV2Config", "load_v2_config"]
