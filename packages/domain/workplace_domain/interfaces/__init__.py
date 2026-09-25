"""Adapter interfaces (docs/architecture.md §6).

Callers depend only on these Protocols. Implementations are chosen by settings: in-memory and
local-file adapters ship first (docs/infrastructure.md); Redis, Event Hubs, ADLS and Snowflake
adapters can be added later without changing callers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from workplace_domain.enums import ComponentStatus, Stream
from workplace_domain.events import EventEnvelope


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    status: ComponentStatus
    detail: str = ""
    info: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class HealthCheckable(Protocol):
    async def health(self) -> ComponentHealth: ...


@dataclass(frozen=True, slots=True)
class ReceivedEvent:
    """An event as delivered by the bus, with its transport position."""

    envelope: EventEnvelope
    stream: Stream
    stream_id: str


class EventPublisher(Protocol):
    async def publish(self, events: Sequence[EventEnvelope]) -> None: ...
    async def flush(self) -> None: ...


class EventConsumer(Protocol):
    async def consume(
        self, streams: Sequence[Stream], max_batch: int, timeout_ms: int
    ) -> Sequence[ReceivedEvent]: ...
    async def ack(self, events: Sequence[ReceivedEvent]) -> None: ...


class StateStore(Protocol):
    """Key/hash/set store modelled on the Redis key layout in docs/data-model.md §4."""

    async def get_hash(self, key: str) -> dict[str, str]: ...
    async def set_hash_fields(self, key: str, fields: Mapping[str, str]) -> None: ...
    async def add_to_set(self, key: str, *members: str) -> None: ...
    async def remove_from_set(self, key: str, *members: str) -> None: ...
    async def set_members(self, key: str) -> set[str]: ...
    async def delete_prefix(self, prefix: str) -> int: ...


class RawArchive(Protocol):
    async def append(self, events: Sequence[ReceivedEvent]) -> None: ...
    async def list_closed_files(self, since: str | None = None) -> Sequence[Path]: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
    async def wait_until(self, t: datetime) -> None: ...


class WarehouseRepository(Protocol):
    def query_mart(self, mart: str, filters: Mapping[str, Any]) -> list[dict[str, Any]]: ...


__all__ = [
    "Clock",
    "ComponentHealth",
    "EventConsumer",
    "EventPublisher",
    "HealthCheckable",
    "RawArchive",
    "ReceivedEvent",
    "StateStore",
    "WarehouseRepository",
]
