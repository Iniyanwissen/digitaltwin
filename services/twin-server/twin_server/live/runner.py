"""Live runner: drives the engine on a scaled clock (port of reference/refsim/server.py Runner).

sim = anchor_sim + (wall - anchor_wall) x speed. Speed changes and resume re-anchor, so time never
jumps backwards. Night skip: when nobody is truly inside after `night_starts_hour` (or before
`morning_hour`), jump to the next morning. Observed events go to the event bus (the processor
builds LiveState from them); truth events go straight to the TruthView.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from twin_server.engine.simtime import SECONDS_PER_DAY
from twin_server.engine.simulation import Engine
from twin_server.live.truth_view import TruthView
from twin_server.processor.live_state import LiveState
from twin_server.runtime import BackgroundService
from workplace_domain.config import SimulationConfig
from workplace_domain.enums import RunMode, SimCommand
from workplace_domain.events import EventEnvelope
from workplace_domain.interfaces import EventPublisher
from workplace_domain.models import MasterData

LIVE_NAMESPACE = uuid.UUID("5c2e8a41-93d7-5b1f-a6e0-4d9c7b2f8e36")


class LiveRunner(BackgroundService):
    name = "simulation-engine"

    def __init__(
        self,
        config: SimulationConfig,
        master: MasterData,
        publisher: EventPublisher,
        state: LiveState,
        truth: TruthView,
    ) -> None:
        super().__init__()
        self.cfg, self.master, self.publisher = config, master, publisher
        self.state, self.truth = state, truth
        self.speed = config.simulation.speed
        self._runs = 0
        self._outbox: list[EventEnvelope] = []
        self.reset()

    # ------------------------------------------------------------------ lifecycle
    def _start_date(self) -> date:
        """Configured date, else today; weekends and holidays roll forward to a working day."""
        day = (
            self.cfg.simulation.live_start_date or datetime.now(ZoneInfo(self.cfg.timezone)).date()
        )
        cal = self.cfg.calendar
        if self.cfg.simulation.live_start_date is None:
            while day.isoweekday() in cal.weekend_days or day in cal.holidays:
                day += timedelta(days=1)
        return day

    def reset(self) -> None:
        self._runs += 1
        start = self._start_date()
        stamp = datetime.now(UTC).isoformat()
        self.run_id = uuid.uuid5(LIVE_NAMESPACE, f"{self.cfg.seed}|{start}|{self._runs}|{stamp}")
        self._outbox.clear()
        self.state.reset(self.run_id)
        self.truth.reset()
        self.engine = Engine(
            self.cfg,
            self.master,
            start,
            self._outbox.append,
            self.truth.apply,
            mode=RunMode.LIVE,
            run_id=self.run_id,
        )
        self.engine.start(days=None)
        self.status = "STOPPED"
        self.sim_t = 0.0
        self.anchor_wall = time.monotonic()
        self.anchor_sim = 0.0
        self.state.sample(self.engine.st.dt(0))
        self.truth.summary = self.engine.truth_summary()

    def command(self, cmd: SimCommand, speed: int | None = None) -> dict[str, Any]:
        now = time.monotonic()
        if cmd in (SimCommand.START, SimCommand.RESUME) and self.status != "RUNNING":
            self.status, self.anchor_wall, self.anchor_sim = "RUNNING", now, self.sim_t
        elif cmd is SimCommand.PAUSE and self.status == "RUNNING":
            self.status = "PAUSED"
        elif cmd is SimCommand.STOP:
            self.status = "STOPPED"
        elif cmd is SimCommand.RESET:
            self.reset()
        elif cmd is SimCommand.SET_SPEED:
            if speed not in self.cfg.simulation.allowed_speeds:
                raise ValueError(f"speed must be one of {self.cfg.simulation.allowed_speeds}")
            self.anchor_wall, self.anchor_sim, self.speed = now, self.sim_t, speed
        return self.status_info()

    # ------------------------------------------------------------------ loop
    async def _run(self) -> None:
        tick = self.cfg.simulation.tick_ms / 1000
        self.log.info("live_runner_started", speed=self.speed)
        while True:
            await asyncio.sleep(tick)
            if self.status != "RUNNING":
                continue
            self._advance()
            if self._outbox:
                batch, self._outbox[:] = list(self._outbox), []
                await self.publisher.publish(batch)
            self.state.sample(self.engine.st.dt(self.sim_t))
            self.truth.summary = self.engine.truth_summary()

    def _advance(self) -> None:
        s = self.cfg.simulation
        target = self.anchor_sim + (time.monotonic() - self.anchor_wall) * self.speed
        hour = (target % SECONDS_PER_DAY) / 3600
        night = hour >= s.night_starts_hour or hour < s.morning_hour
        if s.skip_night and night and not self.engine.truth_summary()["inside"]:
            day0 = target - (target % SECONDS_PER_DAY)
            morning = s.morning_hour * 3600
            target = day0 + (morning if hour < s.morning_hour else SECONDS_PER_DAY + morning)
            # Process everything up to the jump instantly (environment continuity).
            self.anchor_wall, self.anchor_sim = time.monotonic(), target
        self.engine.step_until(target)
        self.sim_t = target

    # ------------------------------------------------------------------ views
    def status_info(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "status": self.status,
            "speed": self.speed,
            "allowed_speeds": list(self.cfg.simulation.allowed_speeds),
            "sim_time": self.engine.st.dt(self.sim_t).isoformat(timespec="seconds"),
            "events_generated": sum(v for k, v in self.engine.counters.items() if k != "TRUTH"),
        }

    def _state_info(self) -> dict[str, object]:
        return {k: v for k, v in self.status_info().items() if k != "allowed_speeds"}

    def snapshot(self, include_truth: bool) -> dict[str, Any]:
        snap: dict[str, Any] = {"type": "snapshot", **self.status_info(), **self.state.snapshot()}
        if include_truth:
            snap["truth"] = self.truth.snapshot()
        return snap
