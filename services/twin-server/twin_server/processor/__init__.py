"""Event processor (docs/architecture.md §4.2): consumes observed events and maintains LiveState."""

from __future__ import annotations

import time

from twin_server.processor.live_state import LiveState
from twin_server.runtime import BackgroundService
from workplace_domain.enums import Stream
from workplace_domain.interfaces import EventConsumer

# Truth never travels on the operational bus; dead letters are not applied.
_OPERATIONAL_STREAMS = [s for s in Stream if s not in (Stream.DEADLETTER, Stream.TRUTH)]


class EventProcessorService(BackgroundService):
    name = "event-processor"

    def __init__(self, consumer: EventConsumer, heartbeat_interval_s: float) -> None:
        super().__init__()
        self._consumer = consumer
        self._heartbeat_interval_s = heartbeat_interval_s
        self._received = 0
        self.live_state: LiveState | None = None

    async def _run(self) -> None:
        self.log.info("processor_started", streams=[str(s) for s in _OPERATIONAL_STREAMS])
        last_beat = time.monotonic()
        while True:
            batch = await self._consumer.consume(_OPERATIONAL_STREAMS, 2000, timeout_ms=1000)
            self._received += len(batch)
            if self.live_state is not None:
                for received in batch:
                    self.live_state.apply(received.envelope)
            await self._consumer.ack(batch)
            if time.monotonic() - last_beat >= self._heartbeat_interval_s:
                self.log.info("processor_heartbeat", events_received=self._received)
                last_beat = time.monotonic()

    def _state_info(self) -> dict[str, object]:
        return {"events_received": self._received}
