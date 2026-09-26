"""Composition root: builds adapters and services from settings and config."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Engine

from twin_server.adapters.memory_bus import InMemoryEventBus
from twin_server.adapters.memory_state import InMemoryStateStore
from twin_server.db import create_db_engine
from twin_server.live.runner import LiveRunner
from twin_server.live.service import LiveService
from twin_server.live.truth_view import TruthView
from twin_server.masterdata.service import MasterDataService
from twin_server.processor import EventProcessorService
from twin_server.processor.live_state import LiveState
from twin_server.settings import Settings
from workplace_domain.config import WorkplaceConfig
from workplace_domain.models import MasterData


@dataclass
class AppContext:
    settings: Settings
    config: WorkplaceConfig
    db: Engine
    bus: InMemoryEventBus
    state: InMemoryStateStore
    master: MasterDataService
    processor: EventProcessorService
    runner: LiveRunner | None = None
    live: LiveService | None = field(default=None)

    @classmethod
    def build(cls, settings: Settings, config: WorkplaceConfig) -> AppContext:
        # Only in-memory adapters exist so far; Settings restricts the choice accordingly.
        sim = config.simulation
        db = create_db_engine(settings.resolved_database_url)
        bus = InMemoryEventBus(maxlen=sim.processing.stream_maxlen)
        return cls(
            settings=settings,
            config=config,
            db=db,
            bus=bus,
            state=InMemoryStateStore(),
            master=MasterDataService(db, config),
            processor=EventProcessorService(bus, settings.heartbeat_interval_s),
        )

    def attach_live(self, master: MasterData) -> None:
        """Wire the live simulation once master data is available."""
        sim = self.config.simulation
        state = LiveState(master, sim.processing)
        truth = TruthView(master, sim.processing)
        self.runner = LiveRunner(sim, master, self.bus, state, truth)
        self.processor.live_state = state
        self.live = LiveService(master, self.runner, state, truth)

    def start(self) -> None:
        self.processor.start()
        if self.runner is not None:
            self.runner.start()

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.stop()
        await self.processor.stop()
        self.db.dispose()
