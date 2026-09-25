import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from workplace_domain.enums import EntityType, EventType, IdentityClass, Source, Stream
from workplace_domain.events import (
    EVENT_TYPE_SPECS,
    EventEnvelope,
    identity_class_for,
    make_event_id,
    stream_for,
)

RUN = uuid.UUID("b1e2c3d4-0000-4000-8000-000000000001")
T0 = datetime(2026, 9, 25, 9, 14, 32, tzinfo=ZoneInfo("Asia/Kolkata"))


def envelope(**overrides) -> dict:
    base = {
        "event_type": EventType.OCCUPANCY_CHANGED,
        "event_time": T0,
        "ingest_time": T0 + timedelta(seconds=1),
        "source": Source.DESK_SENSOR,
        "source_device_id": "SEN_DSK_000021",
        "identity_class": IdentityClass.ANONYMOUS,
        "entity_type": EntityType.WORKSPACE,
        "entity_id": "DESK_BLD01_F02_045",
        "building_id": "BLD01",
        "floor_id": "BLD01_F02",
        "simulation_run_id": RUN,
        "sequence_number": 7,
        "payload": {"sensor_id": "SEN_DSK_000021", "occupancy_status": 1, "previous_status": 0},
    }
    base.update(overrides)
    base.setdefault("event_id", make_event_id(base["simulation_run_id"], base["sequence_number"]))
    return base


def test_every_event_type_is_classified() -> None:
    assert set(EVENT_TYPE_SPECS) == set(EventType)


def test_event_id_is_deterministic() -> None:
    assert make_event_id(RUN, 42) == make_event_id(RUN, 42)
    assert make_event_id(RUN, 42) != make_event_id(RUN, 43)


def test_valid_anonymous_event() -> None:
    event = EventEnvelope.model_validate(envelope())
    assert event.identity_class is identity_class_for(EventType.OCCUPANCY_CHANGED)
    assert stream_for(event.event_type) is Stream.OCCUPANCY


def test_valid_identified_event_with_correlation() -> None:
    EventEnvelope.model_validate(
        envelope(
            event_type=EventType.ACCESS_IN,
            source=Source.ACCESS_CONTROL,
            source_device_id="AP_BLD01_ENT01",
            identity_class=IdentityClass.IDENTIFIED,
            entity_type=EntityType.EMPLOYEE,
            entity_id="EMP000042",
            correlation_id="VISIT-EMP000042-20260925-1",
            payload={"access_point_id": "AP_BLD01_ENT01", "direction": "IN"},
        )
    )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"identity_class": IdentityClass.IDENTIFIED}, "must have identity_class"),
        ({"entity_type": EntityType.EMPLOYEE}, "cannot have entity_type"),
        ({"correlation_id": "VISIT-1"}, "correlation_id"),
        ({"payload": {"sensor_id": "S1", "employee_id": "EMP000042"}}, "person identifier"),
        ({"payload": {"meta": [{"person_id": "EMP1"}]}}, "person identifier"),
        ({"source": Source.ACCESS_CONTROL}, "cannot come from source"),
        ({"ingest_time": T0 - timedelta(seconds=1)}, "ingest_time"),
        ({"event_id": uuid.uuid4()}, "UUIDv5"),
    ],
)
def test_envelope_rejects_rule_violations(overrides, expected) -> None:
    with pytest.raises(ValidationError, match=expected):
        EventEnvelope.model_validate(envelope(**overrides))


def test_naive_timestamps_rejected() -> None:
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(envelope(event_time=T0.replace(tzinfo=None)))
