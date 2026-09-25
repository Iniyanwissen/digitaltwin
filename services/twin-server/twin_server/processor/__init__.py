"""Event processor (docs/architecture.md §4.2). Phase 1: consumes and counts, no state yet."""

from __future__ import annotations

import time

from twin_server.runtime import BackgroundService
from workplace_domain.enums import Stream
from workplace_domain.interfaces import EventConsumer, StateStore

_OPERATIONAL_STREAMS = [s for s in Stream if s is not Stream.DEADLETTER]


class EventProcessorService(BackgroundService):
    name = "event-processor"

    def __init__(
        self, consumer: EventConsumer, state: StateStore, heartbeat_interval_s: float
    ) -> None:
        super().__init__()
        self._consumer = consumer
        self._state = state
        self._heartbeat_interval_s = heartbeat_interval_s
        self._received = 0

    async def _run(self) -> None:
        self.log.info("processor_started", streams=[str(s) for s in _OPERATIONAL_STREAMS])
        last_beat = time.monotonic()
        while True:
            batch = await self._consumer.consume(_OPERATIONAL_STREAMS, 500, timeout_ms=1000)
            self._received += len(batch)
            await self._consumer.ack(batch)
            if time.monotonic() - last_beat >= self._heartbeat_interval_s:
                self.log.info("processor_heartbeat", events_received=self._received)
                last_beat = time.monotonic()

    def _state_info(self) -> dict[str, object]:
        return {"events_received": self._received}
