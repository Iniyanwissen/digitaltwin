"""Simulation engine (docs/simulation-engine.md). Phase 1: runnable skeleton only."""

from __future__ import annotations

import asyncio

from twin_server.runtime import BackgroundService
from workplace_domain.config import SimulationConfig
from workplace_domain.enums import RunStatus
from workplace_domain.interfaces import EventPublisher


class SimulationEngineService(BackgroundService):
    """Owns the simulated world. Until Phase 3 it only reports that it is alive and idle."""

    name = "simulation-engine"

    def __init__(
        self, config: SimulationConfig, publisher: EventPublisher, heartbeat_interval_s: float
    ) -> None:
        super().__init__()
        self._config = config
        self._publisher = publisher
        self._heartbeat_interval_s = heartbeat_interval_s
        self.run_status: RunStatus | None = None  # no run exists yet

    async def _run(self) -> None:
        self.log.info("engine_started", seed=self._config.seed, timezone=self._config.timezone)
        while True:
            self.log.info("engine_heartbeat", run_status=self.run_status or "NO_RUN")
            await asyncio.sleep(self._heartbeat_interval_s)

    def _state_info(self) -> dict[str, object]:
        return {"run_status": self.run_status or "NO_RUN"}
