"""Pydantic schema for config/simulation.yaml.

Every model forbids unknown keys, so a typo in the YAML fails at startup instead of being
silently ignored. Business logic reads these values; nothing is hardcoded elsewhere.
Behaviour sections (profiles, calendar, activities, meetings, access, workstation, sensors,
environment, bms, delivery) are ported from the kit reference config (reference/config).
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
PositiveFloat = Annotated[float, Field(gt=0)]
NonNegFloat = Annotated[float, Field(ge=0)]
Hour = Annotated[float, Field(ge=0, le=24)]

_MIX_TOLERANCE = 1e-6
WEEKDAY_NAMES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
ATTENDANCE_BASE_KEYS = frozenset(
    {"OFFICE", "HYBRID_OFFICE", "HYBRID_REMOTE", "HYBRID_FLEX", "REMOTE"}
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_mix(shares: Iterable[float], label: str) -> None:
    shares = list(shares)
    total = sum(shares)
    if abs(total - 1.0) > _MIX_TOLERANCE:
        raise ValueError(f"{label} shares must sum to 1.0 (got {total:.4f})")
    if any(v < 0 for v in shares):
        raise ValueError(f"{label} shares must be non-negative")


class Dist(_Strict):
    """Normal distribution: mean and standard deviation."""

    mean: float
    sd: NonNegFloat


class Range(_Strict):
    """Uniform range [min, max]."""

    min: NonNegFloat
    max: NonNegFloat

    @model_validator(mode="after")
    def _ordered(self) -> Range:
        if self.min > self.max:
            raise ValueError("range min must be <= max")
        return self


class MedianP90(_Strict):
    """Log-normal dwell given by median and 90th percentile (minutes)."""

    median: PositiveFloat
    p90: PositiveFloat

    @model_validator(mode="after")
    def _ordered(self) -> MedianP90:
        if self.p90 <= self.median:
            raise ValueError("p90 must be greater than median")
        return self


class Window(_Strict):
    """Hour-of-day window [start, end)."""

    start: Hour
    end: Hour

    @model_validator(mode="after")
    def _ordered(self) -> Window:
        if self.start >= self.end:
            raise ValueError("window start must be before end")
        return self

    def contains(self, hour: float) -> bool:
        return self.start <= hour < self.end


# ------------------------------------------------------------------ office and people


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


class ProfileSpec(_Strict):
    arrival: Hour
    arrival_sd_min: NonNegFloat
    workday_h: PositiveFloat
    workday_sd_min: NonNegFloat
    meeting_factor: NonNegFloat
    desk_switch_p: Probability


# ------------------------------------------------------------------ clock and calendar


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
    night_starts_hour: Hour
    morning_hour: Hour
    tick_ms: PositiveInt
    live_start_date: date | None = None
    core_hours: CoreHours
    earliest_arrival: Hour
    latest_arrival: Hour
    latest_departure: Hour
    min_workday_h: PositiveFloat
    day_end_hour: Hour

    @model_validator(mode="after")
    def _valid(self) -> SimulationSection:
        if self.speed not in self.allowed_speeds:
            raise ValueError(f"simulation.speed {self.speed} is not in allowed_speeds")
        if not self.earliest_arrival < self.latest_arrival < self.latest_departure:
            raise ValueError("need earliest_arrival < latest_arrival < latest_departure")
        if self.latest_departure >= self.day_end_hour:
            raise ValueError("latest_departure must be before day_end_hour")
        return self


class CalendarConfig(_Strict):
    all_days_working: bool
    working_pattern_weekday: Annotated[int, Field(ge=1, le=5)]
    weekend_days: list[Annotated[int, Field(ge=1, le=7)]]
    holidays: list[date]
    weekend_attendance: Probability
    leave_type_weights: dict[str, PositiveFloat]

    def is_off_day(self, day: date) -> bool:
        if self.all_days_working:
            return False
        return day.isoweekday() in self.weekend_days or day in self.holidays

    def pattern_weekday(self, day: date) -> int:
        """Weekday whose attendance pattern applies (weekends borrow one if all days work)."""
        wd = day.isoweekday()
        if self.all_days_working and wd in self.weekend_days:
            return self.working_pattern_weekday
        return wd


class AttendanceConfig(_Strict):
    average_daily_percentage: Annotated[float, Field(gt=0, le=100)]
    team_correlation_sigma: NonNegFloat
    team_office_day_boost: PositiveFloat
    base: dict[str, Probability]
    weekday_factor: dict[str, NonNegFloat]
    leave_rate: Probability
    max_probability: Probability

    @field_validator("weekday_factor")
    @classmethod
    def _known_weekdays(cls, v: dict[str, float]) -> dict[str, float]:
        unknown = set(v) - set(WEEKDAY_NAMES)
        if unknown:
            raise ValueError(f"unknown weekday keys {sorted(unknown)}; use {list(WEEKDAY_NAMES)}")
        return v

    @field_validator("base")
    @classmethod
    def _base_keys(cls, v: dict[str, float]) -> dict[str, float]:
        if set(v) != ATTENDANCE_BASE_KEYS:
            raise ValueError(f"attendance.base needs exactly {sorted(ATTENDANCE_BASE_KEYS)}")
        return v

    def weekday_factor_iso(self, iso_weekday: int) -> float:
        return self.weekday_factor.get(WEEKDAY_NAMES[iso_weekday - 1], 0.0)

    def workday_mean_factor(self) -> float:
        values = list(self.weekday_factor.values())
        return sum(values) / len(values)


# ------------------------------------------------------------------ behaviour


class ActivitiesConfig(_Strict):
    desk_block: MedianP90
    lunch: MedianP90
    coffee: MedianP90
    break_: MedianP90 = Field(alias="break")
    collaboration: MedianP90
    other: MedianP90
    weights: dict[str, PositiveFloat]
    lunch_window: Window
    late_lunch_until: Hour
    lunch_boost: PositiveFloat
    lunch_leave_rate_factor: PositiveFloat
    pack_up_return_p: Probability
    favourite_desk_p: Probability

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @field_validator("weights")
    @classmethod
    def _activity_keys(cls, v: dict[str, float]) -> dict[str, float]:
        expected = {"CAFETERIA", "BREAK", "COLLABORATION_AREA", "OTHER_AREA"}
        if set(v) != expected:
            raise ValueError(f"activities.weights needs exactly {sorted(expected)}")
        return v


class CollaborationConfig(_Strict):
    """Hidden cross-team collaboration pairs (ground truth the analytics should rediscover)."""

    pair_count: Annotated[int, Field(ge=0)]
    cross_floor_share: Probability


class MeetingsConfig(_Strict):
    average_per_employee: NonNegFloat
    per_employee_sd: NonNegFloat
    team_share: Probability
    partner_share: Probability
    department_share: Probability
    size_weights: dict[PositiveInt, PositiveFloat]
    duration_weights: dict[PositiveInt, PositiveFloat]
    slot_first_hour: Hour
    slot_last_hour: Hour
    slot_step_h: PositiveFloat
    peak_windows: list[Window]
    peak_boost: NonNegFloat
    quiet_window: Window
    quiet_weight: NonNegFloat
    no_show_probability: Probability
    ghost_booking_probability: Probability
    early_end_probability: Probability
    early_end_s: Range
    late_start_s: Dist
    min_duration_s: PositiveFloat
    room_check_in_probability: Probability
    check_in_delay_s: Range
    walk_in_share: Probability
    collaboration: CollaborationConfig

    @model_validator(mode="after")
    def _shares(self) -> MeetingsConfig:
        if self.team_share + self.partner_share + self.department_share > 1.0 + _MIX_TOLERANCE:
            raise ValueError("team_share + partner_share + department_share must be <= 1")
        if self.slot_first_hour >= self.slot_last_hour:
            raise ValueError("slot_first_hour must be before slot_last_hour")
        return self


class TimingsConfig(_Strict):
    """Walking and dwell times between states (seconds)."""

    entry_to_desk_s: Range
    meeting_to_desk_s: Range
    pack_up_s: Range
    exit_walk_s: Range
    leave_before_departure_s: NonNegFloat


# ------------------------------------------------------------------ observers


class AccessConfig(_Strict):
    tailgate_probability: Probability
    missed_badge_out_probability: Probability
    internal_badge_compliance: Probability
    entry_delay_s: Dist
    exit_delay_s: Dist
    min_delay_s: NonNegFloat
    area_reader_spacing_s: NonNegFloat
    area_reader_jitter_s: NonNegFloat


class WorkstationConfig(_Strict):
    explicit_logout_probability: Probability
    no_login_probability: Probability
    idle_timeout_minutes: PositiveFloat
    end_of_day_sweep: Hour
    login_delay_s: Dist
    min_login_delay_s: NonNegFloat
    logout_delay_s: Dist
    min_logout_delay_s: NonNegFloat


class SensorsConfig(_Strict):
    desk_poll_interval: PositiveInt
    room_poll_interval: PositiveInt
    environment_poll_interval: PositiveInt
    desk_vacancy_timeout_s: PositiveInt
    desk_detection_delay_s: Dist
    min_detection_delay_s: NonNegFloat
    room_report_lag_s: Dist
    min_room_lag_s: NonNegFloat
    room_count_noise_probability: Probability
    count_confidence: Probability
    desk_sensor_coverage: Probability
    installed_at: date


class EnvironmentConfig(_Strict):
    initial: dict[str, float]
    setpoint_c: dict[str, float]
    mean_reversion_per_min: dict[str, PositiveFloat]
    ventilation_per_min: dict[str, PositiveFloat]
    occupancy_heat_c: float
    outdoor_amplitude_c: float
    outdoor_peak_hour: Hour
    min_zone_capacity: PositiveInt
    max_load: PositiveFloat
    temperature_bounds_c: Range
    temperature_noise_c: NonNegFloat
    outdoor_co2_ppm: PositiveFloat
    co2_per_load: PositiveFloat
    co2_noise_ppm: NonNegFloat
    humidity_base_pct: float
    humidity_per_load: float
    humidity_reversion_per_min: PositiveFloat
    humidity_noise_pct: NonNegFloat
    light_on_lux: Dist
    light_off_lux: Dist
    noise_base_dba: float
    noise_per_log_occupant: float
    noise_sd_dba: NonNegFloat


class BmsConfig(_Strict):
    eco_after_empty_minutes: PositiveFloat
    high_above_pct: Annotated[float, Field(ge=0, le=100)]
    high_exit_below_pct: Annotated[float, Field(ge=0, le=100)]
    hot_threshold_c: float
    max_setpoint_drop_c: PositiveFloat
    setpoint_step_c: PositiveFloat
    co2_threshold_ppm: PositiveFloat
    co2_recovery_margin_ppm: PositiveFloat
    cooldown_minutes: PositiveFloat


class BatchConfig(_Strict):
    environment_poll_interval: PositiveInt
    emit_heartbeats: bool
    parallel_workers: PositiveInt


class DeliveryConfig(_Strict):
    transport_delay_s: Dist
    min_transport_delay_s: NonNegFloat
    late_delay_median_s: PositiveFloat
    late_delay_sigma: NonNegFloat
    duplicate_delay_max_s: NonNegFloat


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
    change_log_max: PositiveInt
    feed_buffer: PositiveInt
    feed_per_frame: PositiveInt
    dedupe_window: PositiveInt
    automation_log: PositiveInt


# ------------------------------------------------------------------ root


class SimulationConfig(_Strict):
    seed: Annotated[int, Field(ge=0)]
    timezone: str
    scale_preset: ScalePreset
    office: OfficeConfig
    employees: EmployeesConfig
    profiles: dict[BehaviorProfile, ProfileSpec]
    simulation: SimulationSection
    calendar: CalendarConfig
    attendance: AttendanceConfig
    activities: ActivitiesConfig
    meetings: MeetingsConfig
    timings: TimingsConfig
    access: AccessConfig
    workstation: WorkstationConfig
    sensors: SensorsConfig
    environment: EnvironmentConfig
    bms: BmsConfig
    batch: BatchConfig
    delivery: DeliveryConfig
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

    @model_validator(mode="after")
    def _profiles_cover_mix(self) -> SimulationConfig:
        missing = set(self.employees.profile_mix) - set(self.profiles)
        if missing:
            raise ValueError(f"profiles missing for {sorted(missing)}")
        return self
