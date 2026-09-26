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
from twin_server.v2.live import LiveRunnerV2, LiveServiceV2
from twin_server.v2.live_state import LiveStateV2
from twin_server.v2.world import V2World, build_v2_world
from workplace_domain.config import WorkplaceConfig
from workplace_domain.config.v2 import load_v2_config
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
    # Live Simulation v2 world (separate from v1; None when config/v2 is absent).
    v2: V2World | None = None
    v2_bus: InMemoryEventBus | None = None
    v2_processor: EventProcessorService | None = None
    v2_runner: LiveRunnerV2 | None = None
    v2_live: LiveServiceV2 | None = None

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

    def attach_v2(self) -> None:
        """Build the v2 world from config/v2 (optional; v1 never depends on it)."""
        v2_cfg, plan = load_v2_config(self.settings.config_dir)
        world = build_v2_world(self.config, v2_cfg, plan)
        sim = self.config.simulation
        # Own bus and processor: v2 events never reach the v1 processor (and vice versa).
        bus = InMemoryEventBus(maxlen=sim.processing.stream_maxlen)
        processor = EventProcessorService(bus, self.settings.heartbeat_interval_s)
        processor.name = "event-processor-v2"
        state = LiveStateV2(world.master, sim.processing, v2_cfg, world.env_areas)
        truth = TruthView(world.master, sim.processing)
        runner = LiveRunnerV2(sim, v2_cfg, world, bus, state, truth)
        processor.live_state = state
        self.v2, self.v2_bus, self.v2_processor, self.v2_runner = world, bus, processor, runner
        self.v2_live = LiveServiceV2(world, runner, state, truth)

    def start(self) -> None:
        self.processor.start()
        if self.runner is not None:
            self.runner.start()
        if self.v2_processor is not None and self.v2_runner is not None:
            self.v2_processor.start()
            self.v2_runner.start()

    async def stop(self) -> None:
        if self.v2_runner is not None and self.v2_processor is not None:
            await self.v2_runner.stop()
            await self.v2_processor.stop()
        if self.runner is not None:
            await self.runner.stop()
        await self.processor.stop()
        self.db.dispose()
