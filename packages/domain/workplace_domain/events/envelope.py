"""Common event envelope (docs/event-model.md §2) with the identity rule enforced."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from workplace_domain.enums import EntityType, EventType, IdentityClass, Source
from workplace_domain.events.identity import EVENT_TYPE_SPECS, PERSON_IDENTIFIER_KEYS


def make_event_id(simulation_run_id: uuid.UUID, sequence_number: int) -> uuid.UUID:
    """Deterministic event id: UUIDv5(run id, sequence number). Duplicates keep the same id."""
    return uuid.uuid5(simulation_run_id, str(sequence_number))


def _walk_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, inner in value.items():
            yield str(key)
            yield from _walk_keys(inner)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: uuid.UUID
    event_type: EventType
    event_version: int = Field(default=1, ge=1)
    event_time: AwareDatetime
    ingest_time: AwareDatetime
    source: Source
    source_device_id: str = Field(min_length=1)
    identity_class: IdentityClass
    entity_type: EntityType
    entity_id: str = Field(min_length=1)
    building_id: str = Field(min_length=1)
    floor_id: str | None = None
    zone_id: str | None = None
    correlation_id: str | None = None
    simulation_run_id: uuid.UUID
    sequence_number: int = Field(ge=0)
    payload: dict[str, Any]

    @model_validator(mode="after")
    def _enforce_classification(self) -> EventEnvelope:
        spec = EVENT_TYPE_SPECS[self.event_type]
        if self.identity_class != spec.identity_class:
            raise ValueError(
                f"{self.event_type} must have identity_class {spec.identity_class}, "
                f"got {self.identity_class}"
            )
        if self.source not in spec.sources:
            raise ValueError(f"{self.event_type} cannot come from source {self.source}")
        if self.entity_type not in spec.entity_types:
            raise ValueError(f"{self.event_type} cannot have entity_type {self.entity_type}")
        if self.ingest_time < self.event_time:
            raise ValueError("ingest_time must be >= event_time")
        if self.event_id != make_event_id(self.simulation_run_id, self.sequence_number):
            raise ValueError("event_id must equal UUIDv5(simulation_run_id, sequence_number)")
        if self.identity_class == IdentityClass.ANONYMOUS:
            self._enforce_anonymity()
        return self

    def _enforce_anonymity(self) -> None:
        if self.entity_type in (EntityType.EMPLOYEE, EntityType.VISITOR):
            raise ValueError("ANONYMOUS events cannot be about an employee or visitor")
        if self.correlation_id is not None:
            raise ValueError("ANONYMOUS events cannot carry a correlation_id")
        leaked = PERSON_IDENTIFIER_KEYS.intersection(_walk_keys(self.payload))
        if leaked:
            raise ValueError(f"ANONYMOUS payload contains person identifier keys {sorted(leaked)}")

    @property
    def lateness_seconds(self) -> float:
        return (self.ingest_time - self.event_time).total_seconds()
