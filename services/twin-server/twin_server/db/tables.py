"""Operational database tables (docs/data-model.md §2).

SQLite has no schemas, so each table is prefixed with its group: master_, config_, sim_, ops_.
Array and jsonb columns are stored as JSON.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    false,
    func,
)

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


def _timestamps() -> list[Column[Any]]:
    return [
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    ]


# ------------------------------------------------------------------------------ master

organization = Table(
    "master_organization",
    metadata,
    Column("org_id", String, primary_key=True),
    Column("name", String, nullable=False),
    *_timestamps(),
)

building = Table(
    "master_building",
    metadata,
    Column("building_id", String, primary_key=True),
    Column("org_id", String, ForeignKey("master_organization.org_id"), nullable=False),
    Column("name", String, nullable=False),
    Column("timezone", String, nullable=False),
    Column("max_occupancy", Integer, nullable=False),
    Column("gross_area_sqm", Float, nullable=False),
    *_timestamps(),
)

floor = Table(
    "master_floor",
    metadata,
    Column("floor_id", String, primary_key=True),
    Column("building_id", String, ForeignKey("master_building.building_id"), nullable=False),
    Column("floor_number", Integer, nullable=False),
    Column("name", String, nullable=False),
    Column("max_occupancy", Integer, nullable=False),
    Column("desk_policy", String, nullable=False),
    Column("plan_width", Float, nullable=False),
    Column("plan_height", Float, nullable=False),
    Column("is_available", Boolean, nullable=False),
    *_timestamps(),
)

zone = Table(
    "master_zone",
    metadata,
    Column("zone_id", String, primary_key=True),
    Column("floor_id", String, ForeignKey("master_floor.floor_id"), nullable=False, index=True),
    Column("name", String, nullable=False),
    Column("zone_type", String, nullable=False),
    Column("x", Float, nullable=False),
    Column("y", Float, nullable=False),
    Column("width", Float, nullable=False),
    Column("height", Float, nullable=False),
    Column("max_occupancy", Integer, nullable=False),
    Column("area_sqm", Float, nullable=False),
    Column("is_hvac_zone", Boolean, nullable=False),
    Column("is_restricted", Boolean, nullable=False, server_default=false()),
    *_timestamps(),
)

workspace = Table(
    "master_workspace",
    metadata,
    Column("workspace_id", String, primary_key=True),
    Column("floor_id", String, ForeignKey("master_floor.floor_id"), nullable=False, index=True),
    Column("zone_id", String, ForeignKey("master_zone.zone_id"), nullable=False, index=True),
    Column("workspace_type", String, nullable=False),
    Column("x", Float, nullable=False),
    Column("y", Float, nullable=False),
    Column("status", String, nullable=False),
    Column("has_sensor", Boolean, nullable=False),
    Column("device_type", String, nullable=False, server_default="DOCKING_STATION"),
    *_timestamps(),
)

room = Table(
    "master_room",
    metadata,
    Column("room_id", String, primary_key=True),
    Column("floor_id", String, ForeignKey("master_floor.floor_id"), nullable=False, index=True),
    Column("zone_id", String, ForeignKey("master_zone.zone_id"), nullable=False),
    Column("name", String, nullable=False),
    Column("room_type", String, nullable=False),
    Column("area_subtype", String),
    Column("capacity", Integer, nullable=False),
    Column("x", Float, nullable=False),
    Column("y", Float, nullable=False),
    Column("width", Float, nullable=False),
    Column("height", Float, nullable=False),
    Column("is_bookable", Boolean, nullable=False),
    Column("status", String, nullable=False),
    Column("has_badge_reader", Boolean, nullable=False, server_default=false()),
    Column("has_panel", Boolean, nullable=False, server_default=false()),
    *_timestamps(),
)

access_point = Table(
    "master_access_point",
    metadata,
    Column("access_point_id", String, primary_key=True),
    Column("building_id", String, ForeignKey("master_building.building_id"), nullable=False),
    Column("floor_id", String, ForeignKey("master_floor.floor_id"), nullable=False),
    Column("name", String, nullable=False),
    Column("direction", String, nullable=False),
    Column("x", Float, nullable=False),
    Column("y", Float, nullable=False),
    Column("reader_type", String, nullable=False, server_default="BUILDING_ENTRANCE"),
    Column("target_id", String, nullable=False, server_default=""),
    *_timestamps(),
)

sensor = Table(
    "master_sensor",
    metadata,
    Column("sensor_id", String, primary_key=True),
    Column("sensor_type", String, nullable=False),
    Column("target_type", String, nullable=False),
    Column("target_id", String, nullable=False, index=True),
    Column("floor_id", String, ForeignKey("master_floor.floor_id"), nullable=False, index=True),
    Column("zone_id", String, ForeignKey("master_zone.zone_id"), nullable=False),
    Column("metrics", JSON, nullable=False),
    Column("poll_interval_s", Integer, nullable=False),
    Column("installed_at", Date, nullable=False),
    Column("is_active", Boolean, nullable=False),
    *_timestamps(),
)

department = Table(
    "master_department",
    metadata,
    Column("department_id", String, primary_key=True),
    Column("name", String, nullable=False),
    *_timestamps(),
)

team = Table(
    "master_team",
    metadata,
    Column("team_id", String, primary_key=True),
    Column("department_id", String, ForeignKey("master_department.department_id"), nullable=False),
    Column("name", String, nullable=False),
    Column("home_floor_id", String, ForeignKey("master_floor.floor_id"), nullable=False),
    Column("office_days", JSON, nullable=False),
    Column("size_target", Integer, nullable=False),
    *_timestamps(),
)

team_zone_allocation = Table(
    "master_team_zone_allocation",
    metadata,
    Column("team_id", String, ForeignKey("master_team.team_id"), primary_key=True),
    Column("zone_id", String, ForeignKey("master_zone.zone_id"), primary_key=True),
    Column("share", Float, nullable=False),
    *_timestamps(),
)

zone_access_rule = Table(
    "master_zone_access_rule",
    metadata,
    Column("zone_id", String, ForeignKey("master_zone.zone_id"), primary_key=True),
    Column("team_id", String, ForeignKey("master_team.team_id"), primary_key=True),
    *_timestamps(),
)

employee = Table(
    "master_employee",
    metadata,
    Column("employee_id", String, primary_key=True),
    Column("employee_name", String, nullable=False),
    Column("email", String, nullable=False, unique=True),
    Column("team_id", String, ForeignKey("master_team.team_id"), nullable=False, index=True),
    Column(
        "department_id",
        String,
        ForeignKey("master_department.department_id"),
        nullable=False,
        index=True,
    ),
    Column("job_role", String, nullable=False),
    Column("manager_id", String, ForeignKey("master_employee.employee_id")),
    Column("home_floor_id", String, ForeignKey("master_floor.floor_id"), nullable=False),
    Column("preferred_zone_id", String, ForeignKey("master_zone.zone_id"), nullable=False),
    Column("employment_type", String, nullable=False),
    Column("work_mode", String, nullable=False),
    Column("behavior_profile", String, nullable=False),
    Column("active_flag", Boolean, nullable=False),
    Column("hire_date", Date, nullable=False),
    *_timestamps(),
)

employee_work_pattern = Table(
    "master_employee_work_pattern",
    metadata,
    Column("employee_id", String, ForeignKey("master_employee.employee_id"), primary_key=True),
    Column("iso_weekday", Integer, primary_key=True),
    Column("planned_mode", String, nullable=False),
    *_timestamps(),
)

workspace_assignment = Table(
    "master_workspace_assignment",
    metadata,
    Column("assignment_id", Integer, primary_key=True, autoincrement=True),
    Column("employee_id", String, ForeignKey("master_employee.employee_id"), nullable=False),
    Column("workspace_id", String, ForeignKey("master_workspace.workspace_id"), nullable=False),
    Column("valid_from", Date, nullable=False),
    Column("valid_to", Date),
    *_timestamps(),
)

# Insert order for a full replace (parents first). Delete in reverse.
MASTER_TABLES: dict[str, Table] = {
    "organization": organization,
    "building": building,
    "floor": floor,
    "zone": zone,
    "workspace": workspace,
    "room": room,
    "access_point": access_point,
    "sensor": sensor,
    "department": department,
    "team": team,
    "team_zone_allocation": team_zone_allocation,
    "zone_access_rule": zone_access_rule,
    "employee": employee,
    "employee_work_pattern": employee_work_pattern,
    "workspace_assignment": workspace_assignment,
}

# ------------------------------------------------------------------------------ config

office_configuration = Table(
    "config_office_configuration",
    metadata,
    Column("config_id", String(36), primary_key=True),
    Column("name", String, nullable=False),
    Column("simulation_yaml", JSON, nullable=False),
    Column("organization_yaml", JSON, nullable=False),
    Column("layout_yaml", JSON, nullable=False),
    Column("content_hash", String, nullable=False, index=True),
    Column("is_active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

master_data_version = Table(
    "config_master_data_version",
    metadata,
    Column("version_id", String(36), primary_key=True),
    Column(
        "config_id",
        String(36),
        ForeignKey("config_office_configuration.config_id"),
        nullable=False,
    ),
    Column("seed", BigInteger, nullable=False),
    Column("generated_at", DateTime(timezone=True), nullable=False),
    Column("employee_count", Integer, nullable=False),
    Column("content_hash", String, nullable=False),
    Column("is_current", Boolean, nullable=False),
)

# ------------------------------------------------------------------------------ sim

simulation_run = Table(
    "sim_simulation_run",
    metadata,
    Column("simulation_run_id", String(36), primary_key=True),
    Column("config_id", String(36), ForeignKey("config_office_configuration.config_id")),
    Column(
        "master_data_version",
        String(36),
        ForeignKey("config_master_data_version.version_id"),
    ),
    Column("config_snapshot", JSON, nullable=False),
    Column("seed", BigInteger, nullable=False),
    Column("mode", String, nullable=False),
    Column("sim_start_date", Date, nullable=False),
    Column("sim_end_date", Date),
    Column("initial_speed", Integer),
    Column("status", String, nullable=False),
    Column("wall_started_at", DateTime(timezone=True)),
    Column("wall_ended_at", DateTime(timezone=True)),
    Column("sim_time_reached", DateTime(timezone=True)),
    Column("events_generated", BigInteger, nullable=False, server_default="0"),
    Column("truth_events", BigInteger, nullable=False, server_default="0"),
    Column("error_message", Text),
    *_timestamps(),
)

run_speed_change = Table(
    "sim_run_speed_change",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "simulation_run_id",
        String(36),
        ForeignKey("sim_simulation_run.simulation_run_id"),
        nullable=False,
    ),
    Column("wall_time", DateTime(timezone=True), nullable=False),
    Column("sim_time", DateTime(timezone=True), nullable=False),
    Column("old_speed", Integer, nullable=False),
    Column("new_speed", Integer, nullable=False),
)

run_metrics_snapshot = Table(
    "sim_run_metrics_snapshot",
    metadata,
    Column(
        "simulation_run_id",
        String(36),
        ForeignKey("sim_simulation_run.simulation_run_id"),
        primary_key=True,
    ),
    Column("sim_time", DateTime(timezone=True), primary_key=True),
    Column("employees_inside", Integer, nullable=False),
    Column("occupied_desks", Integer, nullable=False),
    Column("occupied_rooms", Integer, nullable=False),
    Column("events_generated", BigInteger, nullable=False),
)

floor_snapshot = Table(
    "sim_floor_snapshot",
    metadata,
    Column(
        "simulation_run_id",
        String(36),
        ForeignKey("sim_simulation_run.simulation_run_id"),
        primary_key=True,
    ),
    Column("floor_id", String, primary_key=True),
    Column("sim_minute", DateTime(timezone=True), primary_key=True),
    Column("desks", JSON, nullable=False),  # {"DESK_...": [sensor, logged_in]}, non-default only
    Column("rooms", JSON, nullable=False),  # {"ROOM_...": count}
    Column("zones", JSON, nullable=False),  # {"ZONE_...": [temp, co2, hvac_mode]}
    Column("kpis", JSON, nullable=False),
)

# ------------------------------------------------------------------------------ ops

pipeline_run = Table(
    "ops_pipeline_run",
    metadata,
    Column("pipeline_run_id", String(36), primary_key=True),
    Column("trigger", String, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("ended_at", DateTime(timezone=True)),
    Column("status", String, nullable=False),
    Column("error_message", Text),
)

pipeline_layer_count = Table(
    "ops_pipeline_layer_count",
    metadata,
    Column(
        "pipeline_run_id",
        String(36),
        ForeignKey("ops_pipeline_run.pipeline_run_id"),
        primary_key=True,
    ),
    Column("layer", String, primary_key=True),
    Column("object_name", String, primary_key=True),
    Column("rows_total", BigInteger, nullable=False),
    Column("rows_added", BigInteger, nullable=False),
)

ingestion_watermark = Table(
    "ops_ingestion_watermark",
    metadata,
    Column("source_name", String, primary_key=True),
    Column("watermark_value", String, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

source_status_snapshot = Table(
    "ops_source_status_snapshot",
    metadata,
    Column("source_name", String, primary_key=True),
    Column("snapshot_at", DateTime(timezone=True), primary_key=True),
    Column("status", String, nullable=False),
    Column("events_received", BigInteger, nullable=False),
    Column("last_event_time", DateTime(timezone=True)),
    Column("records_processed", BigInteger, nullable=False),
    Column("processing_failures", BigInteger, nullable=False),
    Column("avg_latency_ms", Float),
)

Index("ix_master_employee_home_floor", employee.c.home_floor_id)
