"""Pydantic schema for config/simulation.yaml.

Every model forbids unknown keys, so a typo in the YAML fails at startup instead of being
silently ignored. Business logic reads these values; nothing is hardcoded elsewhere.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, time
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from workplace_domain.enums import BehaviorProfile, DeviceType, ScalePreset, WorkMode

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
PositiveInt = Annotated[int, Field(gt=0)]

_MIX_TOLERANCE = 1e-6
_WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_mix(shares: Iterable[float], label: str) -> None:
    shares = list(shares)
    total = sum(shares)
    if abs(total - 1.0) > _MIX_TOLERANCE:
        raise ValueError(f"{label} shares must sum to 1.0 (got {total:.4f})")
    if any(v < 0 for v in shares):
        raise ValueError(f"{label} shares must be non-negative")


class OfficeConfig(_Strict):
    layout_files: list[str] = Field(min_length=1)
    device_type_mix: dict[DeviceType, float]

    @field_validator("device_type_mix")
    @classmethod
    def _device_mix_sums_to_one(cls, v: dict[DeviceType, float]) -> dict[DeviceType, float]:
        _check_mix(v.values(), "office.device_type_mix")
        return v


class EmployeesConfig(_Strict):
    count: PositiveInt
    work_mode_mix: dict[WorkMode, float]
    profile_mix: dict[BehaviorProfile, float]

    @field_validator("work_mode_mix")
    @classmethod
    def _work_mode_mix_sums_to_one(cls, v: dict[WorkMode, float]) -> dict[WorkMode, float]:
        _check_mix(v.values(), "employees.work_mode_mix")
        return v

    @field_validator("profile_mix")
    @classmethod
    def _profile_mix_sums_to_one(
        cls, v: dict[BehaviorProfile, float]
    ) -> dict[BehaviorProfile, float]:
        _check_mix(v.values(), "employees.profile_mix")
        return v


class CoreHours(_Strict):
    start: time
    end: time

    @model_validator(mode="after")
    def _start_before_end(self) -> CoreHours:
        if self.start >= self.end:
            raise ValueError("core_hours.start must be before core_hours.end")
        return self


class SimulationSection(_Strict):
    speed: PositiveInt
    allowed_speeds: list[PositiveInt] = Field(min_length=1)
    skip_night: bool
    core_hours: CoreHours

    @model_validator(mode="after")
    def _speed_is_allowed(self) -> SimulationSection:
        if self.speed not in self.allowed_speeds:
            raise ValueError(f"simulation.speed {self.speed} is not in allowed_speeds")
        return self


class AttendanceConfig(_Strict):
    average_daily_percentage: Annotated[float, Field(gt=0, le=100)]
    team_correlation_sigma: Annotated[float, Field(ge=0)]
    weekday_factor: dict[str, Annotated[float, Field(ge=0)]]
    leave_rate: Probability

    @field_validator("weekday_factor")
    @classmethod
    def _known_weekdays(cls, v: dict[str, float]) -> dict[str, float]:
        unknown = set(v) - set(_WEEKDAYS)
        if unknown:
            raise ValueError(f"unknown weekday keys {sorted(unknown)}; use {list(_WEEKDAYS)}")
        return v


class MeetingsConfig(_Strict):
    average_per_employee: Annotated[float, Field(ge=0)]
    no_show_probability: Probability
    ghost_booking_probability: Probability
    walk_in_share: Probability


class SensorsConfig(_Strict):
    desk_poll_interval: PositiveInt
    room_poll_interval: PositiveInt
    environment_poll_interval: PositiveInt
    desk_vacancy_timeout_s: PositiveInt
    desk_sensor_coverage: Probability
    installed_at: date


class BatchConfig(_Strict):
    environment_poll_interval: PositiveInt
    emit_heartbeats: bool
    parallel_workers: PositiveInt


class BmsConfig(_Strict):
    evaluation_interval_s: PositiveInt


class AnomaliesConfig(_Strict):
    duplicate_event_probability: Probability
    late_event_probability: Probability
    out_of_order_probability: Probability
    missing_event_probability: Probability
    sensor_failure_probability: Probability


class ProcessingConfig(_Strict):
    stream_maxlen: PositiveInt
    live_flush_ms: PositiveInt
    late_threshold_seconds: PositiveInt


class SimulationConfig(_Strict):
    seed: Annotated[int, Field(ge=0)]
    timezone: str
    scale_preset: ScalePreset
    office: OfficeConfig
    employees: EmployeesConfig
    simulation: SimulationSection
    attendance: AttendanceConfig
    meetings: MeetingsConfig
    sensors: SensorsConfig
    batch: BatchConfig
    bms: BmsConfig
    anomalies: AnomaliesConfig
    processing: ProcessingConfig

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone {v!r}") from exc
        return v
