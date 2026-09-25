"""Master data entities (docs/data-model.md §2.1) as plain immutable records."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from workplace_domain.enums import (
    AccessDirection,
    AreaSubtype,
    BehaviorProfile,
    DeskPolicy,
    DeviceType,
    EmploymentType,
    MetricType,
    PlannedMode,
    ReaderType,
    RoomType,
    SensorTarget,
    SensorType,
    SpaceStatus,
    WorkMode,
    WorkspaceType,
    ZoneType,
)


@dataclass(frozen=True, slots=True)
class Organization:
    org_id: str
    name: str


@dataclass(frozen=True, slots=True)
class Building:
    building_id: str
    org_id: str
    name: str
    timezone: str
    max_occupancy: int
    gross_area_sqm: float


@dataclass(frozen=True, slots=True)
class Floor:
    floor_id: str
    building_id: str
    floor_number: int
    name: str
    max_occupancy: int
    desk_policy: DeskPolicy
    plan_width: float
    plan_height: float
    is_available: bool


@dataclass(frozen=True, slots=True)
class Zone:
    zone_id: str
    floor_id: str
    name: str
    zone_type: ZoneType
    x: float
    y: float
    width: float
    height: float
    max_occupancy: int
    area_sqm: float
    is_hvac_zone: bool
    is_restricted: bool


@dataclass(frozen=True, slots=True)
class Workspace:
    workspace_id: str
    floor_id: str
    zone_id: str
    workspace_type: WorkspaceType
    x: float
    y: float
    status: SpaceStatus
    has_sensor: bool
    device_type: DeviceType


@dataclass(frozen=True, slots=True)
class Room:
    room_id: str
    floor_id: str
    zone_id: str
    name: str
    room_type: RoomType
    area_subtype: AreaSubtype | None
    capacity: int
    x: float
    y: float
    width: float
    height: float
    is_bookable: bool
    status: SpaceStatus
    has_badge_reader: bool
    has_panel: bool


@dataclass(frozen=True, slots=True)
class AccessPoint:
    access_point_id: str
    building_id: str
    floor_id: str
    name: str
    direction: AccessDirection
    x: float
    y: float
    reader_type: ReaderType
    target_id: str


@dataclass(frozen=True, slots=True)
class Sensor:
    sensor_id: str
    sensor_type: SensorType
    target_type: SensorTarget
    target_id: str
    floor_id: str
    zone_id: str
    metrics: tuple[MetricType, ...]
    poll_interval_s: int
    installed_at: date
    is_active: bool


@dataclass(frozen=True, slots=True)
class Department:
    department_id: str
    name: str


@dataclass(frozen=True, slots=True)
class Team:
    team_id: str
    department_id: str
    name: str
    home_floor_id: str
    office_days: tuple[int, ...]  # ISO weekdays
    size_target: int


@dataclass(frozen=True, slots=True)
class TeamZoneAllocation:
    team_id: str
    zone_id: str
    share: float


@dataclass(frozen=True, slots=True)
class ZoneAccessRule:
    """Teams allowed through a restricted zone's secure reader."""

    zone_id: str
    team_id: str


@dataclass(frozen=True, slots=True)
class Employee:
    employee_id: str
    employee_name: str
    email: str
    team_id: str
    department_id: str
    job_role: str
    manager_id: str | None
    home_floor_id: str
    preferred_zone_id: str
    employment_type: EmploymentType
    work_mode: WorkMode
    behavior_profile: BehaviorProfile
    active_flag: bool
    hire_date: date


@dataclass(frozen=True, slots=True)
class EmployeeWorkPattern:
    employee_id: str
    iso_weekday: int
    planned_mode: PlannedMode


@dataclass(frozen=True, slots=True)
class WorkspaceAssignment:
    employee_id: str
    workspace_id: str
    valid_from: date
    valid_to: date | None


@dataclass(frozen=True)
class Layout:
    """Physical part of master data, produced by the layout loader."""

    organization: Organization
    buildings: list[Building] = field(default_factory=list)
    floors: list[Floor] = field(default_factory=list)
    zones: list[Zone] = field(default_factory=list)
    workspaces: list[Workspace] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)
    access_points: list[AccessPoint] = field(default_factory=list)
    sensors: list[Sensor] = field(default_factory=list)


@dataclass(frozen=True)
class MasterData:
    layout: Layout
    departments: list[Department]
    teams: list[Team]
    team_zone_allocations: list[TeamZoneAllocation]
    zone_access_rules: list[ZoneAccessRule]
    employees: list[Employee]
    work_patterns: list[EmployeeWorkPattern]
    assignments: list[WorkspaceAssignment]

    def tables(self) -> dict[str, list[Any]]:
        """Entity lists keyed by table name, in foreign-key insert order."""
        lay = self.layout
        return {
            "organization": [lay.organization],
            "building": lay.buildings,
            "floor": lay.floors,
            "zone": lay.zones,
            "workspace": lay.workspaces,
            "room": lay.rooms,
            "access_point": lay.access_points,
            "sensor": lay.sensors,
            "department": self.departments,
            "team": self.teams,
            "team_zone_allocation": self.team_zone_allocations,
            "zone_access_rule": self.zone_access_rules,
            "employee": self.employees,
            "employee_work_pattern": self.work_patterns,
            "workspace_assignment": self.assignments,
        }

    def counts(self) -> dict[str, int]:
        return {name: len(rows) for name, rows in self.tables().items()}

    def content_hash(self) -> str:
        payload = {
            name: [dataclasses.asdict(row) for row in rows] for name, rows in self.tables().items()
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
