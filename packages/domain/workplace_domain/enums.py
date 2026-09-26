"""Domain enums shared by all services. Values match docs/event-model.md and docs/data-model.md."""

from enum import StrEnum


class EventType(StrEnum):
    ACCESS_IN = "ACCESS_IN"
    ACCESS_OUT = "ACCESS_OUT"
    AREA_ACCESS = "AREA_ACCESS"
    ACCESS_DENIED = "ACCESS_DENIED"
    ROOM_CHECK_IN = "ROOM_CHECK_IN"
    WORKSPACE_LOGIN = "WORKSPACE_LOGIN"
    WORKSPACE_LOGOUT = "WORKSPACE_LOGOUT"
    OCCUPANCY_CHANGED = "OCCUPANCY_CHANGED"
    ROOM_OCCUPANCY_CHANGED = "ROOM_OCCUPANCY_CHANGED"
    SENSOR_HEARTBEAT = "SENSOR_HEARTBEAT"
    ENVIRONMENT_READING = "ENVIRONMENT_READING"
    SENSOR_STATUS_CHANGED = "SENSOR_STATUS_CHANGED"
    AUTOMATION_ACTION = "AUTOMATION_ACTION"
    ENERGY_INTERVAL = "ENERGY_INTERVAL"  # v2: kWh per environment area per interval
    TRUTH_STATE_TRANSITION = "TRUTH_STATE_TRANSITION"
    TRUTH_DESK_SEARCH_FAILED = "TRUTH_DESK_SEARCH_FAILED"
    SIMULATION_LIFECYCLE = "SIMULATION_LIFECYCLE"


class Source(StrEnum):
    ACCESS_CONTROL = "ACCESS_CONTROL"
    ROOM_PANEL = "ROOM_PANEL"
    WORKSTATION = "WORKSTATION"
    DESK_SENSOR = "DESK_SENSOR"
    ROOM_SENSOR = "ROOM_SENSOR"
    ENV_SENSOR = "ENV_SENSOR"
    SENSOR_GATEWAY = "SENSOR_GATEWAY"
    BMS = "BMS"
    SIMULATION = "SIMULATION"


class IdentityClass(StrEnum):
    IDENTIFIED = "IDENTIFIED"
    ANONYMOUS = "ANONYMOUS"
    SYSTEM = "SYSTEM"
    INTERNAL = "INTERNAL"  # simulation ground truth, never operational


class EntityType(StrEnum):
    EMPLOYEE = "EMPLOYEE"
    VISITOR = "VISITOR"
    WORKSPACE = "WORKSPACE"
    ROOM = "ROOM"
    SENSOR = "SENSOR"
    ZONE = "ZONE"
    SIMULATION = "SIMULATION"


class Stream(StrEnum):
    ACCESS = "ev.access"
    WORKSPACE = "ev.workspace"
    OCCUPANCY = "ev.occupancy"
    ENVIRONMENT = "ev.environment"
    SYSTEM = "ev.system"
    TRUTH = "ev.truth"
    DEADLETTER = "ev.deadletter"


class PersonType(StrEnum):
    EMPLOYEE = "EMPLOYEE"
    VISITOR = "VISITOR"


class PersonState(StrEnum):
    OUTSIDE_OFFICE = "OUTSIDE_OFFICE"
    ENTERING = "ENTERING"
    AT_DESK = "AT_DESK"
    MEETING = "MEETING"
    CAFETERIA = "CAFETERIA"
    BREAK = "BREAK"
    COLLABORATION_AREA = "COLLABORATION_AREA"
    OTHER_AREA = "OTHER_AREA"
    LEAVING = "LEAVING"


class LocationType(StrEnum):
    WORKSPACE = "WORKSPACE"
    ROOM = "ROOM"
    COMMON_AREA = "COMMON_AREA"
    UNSENSED = "UNSENSED"


class ZoneType(StrEnum):
    OPEN_WORKSPACE = "OPEN_WORKSPACE"
    TEAM_NEIGHBORHOOD = "TEAM_NEIGHBORHOOD"
    MEETING = "MEETING"
    CAFETERIA = "CAFETERIA"
    LOUNGE = "LOUNGE"
    COLLABORATION = "COLLABORATION"
    CABIN_BLOCK = "CABIN_BLOCK"
    ENTRANCE = "ENTRANCE"
    CIRCULATION = "CIRCULATION"


class WorkspaceType(StrEnum):
    DESK = "DESK"
    CABIN = "CABIN"


class RoomType(StrEnum):
    SMALL_MEETING = "SMALL_MEETING"
    MEDIUM_MEETING = "MEDIUM_MEETING"
    LARGE_CONFERENCE = "LARGE_CONFERENCE"
    AUDITORIUM = "AUDITORIUM"
    FOCUS_BOOTH = "FOCUS_BOOTH"  # v2 floor plan
    COMMON_AREA = "COMMON_AREA"


class AreaSubtype(StrEnum):
    CAFETERIA = "CAFETERIA"
    LOUNGE = "LOUNGE"
    COLLABORATION = "COLLABORATION"


class DeskPolicy(StrEnum):
    ASSIGNED = "ASSIGNED"
    HOT_DESK = "HOT_DESK"


class WorkMode(StrEnum):
    OFFICE = "OFFICE"
    HYBRID = "HYBRID"
    REMOTE = "REMOTE"


class BehaviorProfile(StrEnum):
    EARLY_BIRD = "EARLY_BIRD"
    STANDARD = "STANDARD"
    LATE_STARTER = "LATE_STARTER"
    MEETING_HEAVY = "MEETING_HEAVY"
    REMOTE_HEAVY = "REMOTE_HEAVY"
    MOBILE_WORKER = "MOBILE_WORKER"


class ScalePreset(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    CUSTOM = "custom"


class RunMode(StrEnum):
    LIVE = "LIVE"
    BATCH = "BATCH"


class RunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SimCommand(StrEnum):
    START = "START"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    STOP = "STOP"
    RESET = "RESET"
    SET_SPEED = "SET_SPEED"
    GENERATE_HISTORY = "GENERATE_HISTORY"


class EmploymentType(StrEnum):
    FULL_TIME = "FULL_TIME"
    CONTRACTOR = "CONTRACTOR"
    INTERN = "INTERN"


class PlannedMode(StrEnum):
    OFFICE = "OFFICE"
    REMOTE = "REMOTE"
    FLEX = "FLEX"


class AccessDirection(StrEnum):
    IN = "IN"
    OUT = "OUT"
    IN_OUT = "IN_OUT"


class ReaderType(StrEnum):
    BUILDING_ENTRANCE = "BUILDING_ENTRANCE"
    FLOOR_LOBBY = "FLOOR_LOBBY"
    SECURE_ZONE = "SECURE_ZONE"
    ROOM_DOOR = "ROOM_DOOR"


class DeviceType(StrEnum):
    DOCKING_STATION = "DOCKING_STATION"
    DESK_PC = "DESK_PC"
    THIN_CLIENT = "THIN_CLIENT"


class SpaceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    UNAVAILABLE = "UNAVAILABLE"


class SensorType(StrEnum):
    DESK_OCCUPANCY = "DESK_OCCUPANCY"
    ROOM_COUNT = "ROOM_COUNT"
    ENVIRONMENT = "ENVIRONMENT"


class SensorTarget(StrEnum):
    WORKSPACE = "WORKSPACE"
    ROOM = "ROOM"
    ZONE = "ZONE"


class MetricType(StrEnum):
    TEMPERATURE = "TEMPERATURE"
    HUMIDITY = "HUMIDITY"
    CO2 = "CO2"
    LIGHT = "LIGHT"
    NOISE = "NOISE"


class ComponentStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"
