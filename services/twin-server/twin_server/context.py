"""Composition root: builds adapters and services from settings and config."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine

from twin_server.adapters.memory_bus import InMemoryEventBus
from twin_server.adapters.memory_state import InMemoryStateStore
from twin_server.db import create_db_engine
from twin_server.engine import SimulationEngineService
from twin_server.processor import EventProcessorService
from twin_server.settings import Settings
from workplace_domain.config import SimulationConfig, config_content_hash


@dataclass
class AppContext:
    settings: Settings
    config: SimulationConfig
    config_hash: str
    db: Engine
    bus: InMemoryEventBus
    state: InMemoryStateStore
    engine: SimulationEngineService
    processor: EventProcessorService

    @classmethod
    def build(cls, settings: Settings, config: SimulationConfig) -> AppContext:
        # Only in-memory adapters exist so far; Settings restricts the choice accordingly.
        bus = InMemoryEventBus(maxlen=config.processing.stream_maxlen)
        state = InMemoryStateStore()
        return cls(
            settings=settings,
            config=config,
            config_hash=config_content_hash(config),
            db=create_db_engine(settings.resolved_database_url),
            bus=bus,
            state=state,
            engine=SimulationEngineService(config, bus, settings.heartbeat_interval_s),
            processor=EventProcessorService(bus, state, settings.heartbeat_interval_s),
        )

    def start(self) -> None:
        self.processor.start()
        self.engine.start()

    async def stop(self) -> None:
        await self.engine.stop()
        await self.processor.stop()
        self.db.dispose()
