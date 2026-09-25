"""In-process event bus: bounded streams with the same names as the Redis/Event Hubs design."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Sequence

from workplace_domain.enums import ComponentStatus, Stream
from workplace_domain.events import EventEnvelope, stream_for
from workplace_domain.interfaces import ComponentHealth, ReceivedEvent


class InMemoryEventBus:
    """Implements EventPublisher and EventConsumer for a single consumer (the processor).

    Each stream is a deque capped at `maxlen`. When a stream is full the oldest unconsumed
    event is dropped and counted; the raw archive, not the bus, is the durable history.
    """

    def __init__(self, maxlen: int) -> None:
        self._maxlen = maxlen
        self._streams: dict[Stream, deque[ReceivedEvent]] = {s: deque() for s in Stream}
        self._next_id: dict[Stream, int] = dict.fromkeys(Stream, 0)
        self._published = 0
        self._dropped = 0
        self._available = asyncio.Event()

    async def publish(self, events: Sequence[EventEnvelope]) -> None:
        for envelope in events:
            stream = stream_for(envelope.event_type)
            queue = self._streams[stream]
            if len(queue) >= self._maxlen:
                queue.popleft()
                self._dropped += 1
            self._next_id[stream] += 1
            queue.append(ReceivedEvent(envelope, stream, f"{stream}-{self._next_id[stream]}"))
            self._published += 1
        if events:
            self._available.set()

    async def flush(self) -> None:
        return None

    async def consume(
        self, streams: Sequence[Stream], max_batch: int, timeout_ms: int
    ) -> Sequence[ReceivedEvent]:
        batch = self._drain(streams, max_batch)
        if batch:
            return batch
        self._available.clear()
        try:
            await asyncio.wait_for(self._available.wait(), timeout_ms / 1000)
        except TimeoutError:
            return []
        return self._drain(streams, max_batch)

    async def ack(self, events: Sequence[ReceivedEvent]) -> None:
        # Events are removed from the stream when consumed; nothing to acknowledge in memory.
        return None

    def _drain(self, streams: Sequence[Stream], max_batch: int) -> list[ReceivedEvent]:
        batch: list[ReceivedEvent] = []
        for stream in streams:
            queue = self._streams[stream]
            while queue and len(batch) < max_batch:
                batch.append(queue.popleft())
        return batch

    def backlog(self) -> dict[str, int]:
        return {str(s): len(q) for s, q in self._streams.items()}

    async def health(self) -> ComponentHealth:
        return ComponentHealth(
            ComponentStatus.OK,
            "in-memory event bus",
            {
                "published": self._published,
                "dropped": self._dropped,
                "backlog": sum(self.backlog().values()),
                "stream_maxlen": self._maxlen,
            },
        )
