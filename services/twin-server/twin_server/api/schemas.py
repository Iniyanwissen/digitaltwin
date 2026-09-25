"""API response models. Mirrored by frontend/src/api/types.ts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from workplace_domain.enums import ComponentStatus


class ComponentHealthOut(BaseModel):
    status: ComponentStatus
    detail: str
    info: dict[str, Any]


class HealthOut(BaseModel):
    status: ComponentStatus
    checked_at: datetime
    components: dict[str, ComponentHealthOut]


class ConfigSummaryOut(BaseModel):
    content_hash: str
    seed: int
    timezone: str
    scale_preset: str
    organization: str
    employee_count: int
    layout_files: list[str]
    default_speed: int
    allowed_speeds: list[int]
    core_hours: str


class MetaOut(BaseModel):
    name: str
    version: str
    environment: str
    server_time: datetime
    config: ConfigSummaryOut


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


# ------------------------------------------------------------------ spaces


class AccessPointOut(BaseModel):
    access_point_id: str
    building_id: str
    floor_id: str
    name: str
    direction: str
    x: float
    y: float


class FloorSummaryOut(BaseModel):
    floor_id: str
    building_id: str
    floor_number: int
    name: str
    desk_policy: str
    max_occupancy: int
    plan_width: float
    plan_height: float
    is_available: bool
    desks: int
    cabins: int
    rooms: int
    room_seats: int
    common_areas: int
    common_area_capacity: int
    zones: int
    sensors: int
    home_employees: int
    home_teams: int
    workspaces: int
    employees_per_workspace: float


class BuildingOut(BaseModel):
    building_id: str
    org_id: str
    name: str
    timezone: str
    max_occupancy: int
    gross_area_sqm: float
    floors: list[FloorSummaryOut]
    access_points: list[AccessPointOut]


class ZoneOut(BaseModel):
    zone_id: str
    floor_id: str
    name: str
    zone_type: str
    x: float
    y: float
    width: float
    height: float
    max_occupancy: int
    area_sqm: float
    workspaces: int = 0


class WorkspaceOut(BaseModel):
    workspace_id: str
    floor_id: str
    zone_id: str
    workspace_type: str
    x: float
    y: float
    status: str
    has_sensor: bool


class RoomOut(BaseModel):
    room_id: str
    floor_id: str
    zone_id: str
    zone_name: str | None = None
    name: str
    room_type: str
    area_subtype: str | None
    capacity: int
    x: float
    y: float
    width: float
    height: float
    is_bookable: bool
    status: str


class FloorLayoutOut(BaseModel):
    floor_id: str
    building_id: str
    floor_number: int
    name: str
    desk_policy: str
    plan_width: float
    plan_height: float
    zones: list[ZoneOut]
    workspaces: list[WorkspaceOut]
    rooms: list[RoomOut]
    access_points: list[AccessPointOut]


class SensorOut(BaseModel):
    sensor_id: str
    sensor_type: str
    target_type: str
    target_id: str
    floor_id: str
    zone_id: str
    metrics: list[str]
    poll_interval_s: int
    installed_at: date
    is_active: bool


# ------------------------------------------------------------------ people


class DepartmentOut(BaseModel):
    department_id: str
    name: str
    employees: int
    teams: int


class ZoneAllocationOut(BaseModel):
    zone_id: str
    zone_name: str
    share: float


class TeamOut(BaseModel):
    team_id: str
    name: str
    department_id: str
    department_name: str
    home_floor_id: str
    home_floor_name: str
    office_days: list[int]
    size_target: int
    members: int
    zone_allocations: list[ZoneAllocationOut]


class EmployeeOut(BaseModel):
    employee_id: str
    employee_name: str
    email: str
    job_role: str
    team_id: str
    team_name: str
    department_id: str
    department_name: str
    home_floor_id: str
    home_floor_name: str
    preferred_zone_id: str
    manager_id: str | None
    employment_type: str
    work_mode: str
    behavior_profile: str
    hire_date: date
    assigned_workspace_id: str | None


class FacetValueOut(BaseModel):
    value: str
    count: int


class EmployeeFacetsOut(BaseModel):
    work_mode: list[FacetValueOut]
    behavior_profile: list[FacetValueOut]
    employment_type: list[FacetValueOut]
