"""Single source of truth for event classification (docs/event-model.md §3-§4).

`identity_class` is always derived from `event_type` through this table and is never set
freely. A new event type must be added here before it can be emitted.
"""

from __future__ import annotations

from dataclasses import dataclass

from workplace_domain.enums import EntityType, EventType, IdentityClass, Source, Stream


@dataclass(frozen=True, slots=True)
class EventTypeSpec:
    identity_class: IdentityClass
    sources: frozenset[Source]
    entity_types: frozenset[EntityType]
    stream: Stream


def _spec(
    identity: IdentityClass,
    sources: set[Source],
    entities: set[EntityType],
    stream: Stream,
) -> EventTypeSpec:
    return EventTypeSpec(identity, frozenset(sources), frozenset(entities), stream)


_PERSON = {EntityType.EMPLOYEE, EntityType.VISITOR}
_SENSORS = {Source.DESK_SENSOR, Source.ROOM_SENSOR, Source.ENV_SENSOR}

EVENT_TYPE_SPECS: dict[EventType, EventTypeSpec] = {
    EventType.ACCESS_IN: _spec(
        IdentityClass.IDENTIFIED, {Source.ACCESS_CONTROL}, _PERSON, Stream.ACCESS
    ),
    EventType.ACCESS_OUT: _spec(
        IdentityClass.IDENTIFIED, {Source.ACCESS_CONTROL}, _PERSON, Stream.ACCESS
    ),
    EventType.WORKSPACE_LOGIN: _spec(
        IdentityClass.IDENTIFIED, {Source.WORKSTATION}, {EntityType.EMPLOYEE}, Stream.WORKSPACE
    ),
    EventType.WORKSPACE_LOGOUT: _spec(
        IdentityClass.IDENTIFIED, {Source.WORKSTATION}, {EntityType.EMPLOYEE}, Stream.WORKSPACE
    ),
    EventType.OCCUPANCY_CHANGED: _spec(
        IdentityClass.ANONYMOUS, {Source.DESK_SENSOR}, {EntityType.WORKSPACE}, Stream.OCCUPANCY
    ),
    EventType.ROOM_OCCUPANCY_CHANGED: _spec(
        IdentityClass.ANONYMOUS, {Source.ROOM_SENSOR}, {EntityType.ROOM}, Stream.OCCUPANCY
    ),
    # Desk/room heartbeats go to ev.occupancy; env sensors do not send separate heartbeats.
    EventType.SENSOR_HEARTBEAT: _spec(
        IdentityClass.ANONYMOUS, _SENSORS, {EntityType.SENSOR}, Stream.OCCUPANCY
    ),
    EventType.ENVIRONMENT_READING: _spec(
        IdentityClass.ANONYMOUS, {Source.ENV_SENSOR}, {EntityType.ZONE}, Stream.ENVIRONMENT
    ),
    EventType.SENSOR_STATUS_CHANGED: _spec(
        IdentityClass.SYSTEM, {Source.SENSOR_GATEWAY}, {EntityType.SENSOR}, Stream.SYSTEM
    ),
    EventType.AUTOMATION_ACTION: _spec(
        IdentityClass.SYSTEM, {Source.BMS}, {EntityType.ZONE}, Stream.SYSTEM
    ),
    EventType.TRUTH_STATE_TRANSITION: _spec(
        IdentityClass.INTERNAL, {Source.SIMULATION}, _PERSON, Stream.TRUTH
    ),
    EventType.TRUTH_DESK_SEARCH_FAILED: _spec(
        IdentityClass.INTERNAL, {Source.SIMULATION}, {EntityType.EMPLOYEE}, Stream.TRUTH
    ),
    EventType.SIMULATION_LIFECYCLE: _spec(
        IdentityClass.SYSTEM, {Source.SIMULATION}, {EntityType.SIMULATION}, Stream.SYSTEM
    ),
}

# Keys that must never appear anywhere in an ANONYMOUS payload.
PERSON_IDENTIFIER_KEYS: frozenset[str] = frozenset(
    {"employee_id", "visitor_id", "person_id", "email", "name", "employee_name", "visitor_name"}
)


def identity_class_for(event_type: EventType) -> IdentityClass:
    return EVENT_TYPE_SPECS[event_type].identity_class


def stream_for(event_type: EventType) -> Stream:
    return EVENT_TYPE_SPECS[event_type].stream
