"""v2 live runner and service (reuse the v1 runner/service, swap engine, state and layout)."""

from __future__ import annotations

from datetime import date
from typing import Any

from twin_server.engine.simulation import Engine
from twin_server.live.runner import LiveRunner
from twin_server.live.service import LiveService
from twin_server.live.truth_view import TruthView
from twin_server.v2.engine import EngineV2
from twin_server.v2.live_state import LiveStateV2
from twin_server.v2.world import V2World
from workplace_domain.config import SimulationConfig
from workplace_domain.config.v2 import SimulationV2Config
from workplace_domain.enums import RunMode
from workplace_domain.interfaces import EventPublisher


class LiveRunnerV2(LiveRunner):
    name = "simulation-engine-v2"

    def __init__(
        self,
        config: SimulationConfig,
        v2: SimulationV2Config,
        world: V2World,
        publisher: EventPublisher,
        state: LiveStateV2,
        truth: TruthView,
    ) -> None:
        self.v2, self.world = v2, world  # needed by _make_engine during super().__init__
        super().__init__(config, world.master, publisher, state, truth)

    def _make_engine(self, start: date) -> Engine:
        return EngineV2(
            self.cfg,
            self.v2,
            self.world,
            start,
            self._outbox.append,
            self.truth.apply,
            mode=RunMode.LIVE,
            run_id=self.run_id,
        )


class LiveServiceV2(LiveService):
    def __init__(
        self, world: V2World, runner: LiveRunnerV2, state: LiveStateV2, truth: TruthView
    ) -> None:
        self.world = world
        self.state_v2 = state
        super().__init__(world.master, runner, state, truth)

    def layout(self) -> dict[str, Any]:
        return self.world.render

    BOOKED_WINDOW_MIN = 30

    def booked(self) -> dict[str, str]:
        """Rooms empty now with a booking starting within 30 min -> start time (room chip)."""
        engine = self.runner.engine
        if not isinstance(engine, EngineV2):
            return {}
        now = engine.st.dt(self.runner.sim_t)
        out: dict[str, str] = {}
        for room_id in engine.bookings_by_room:
            if self.state.room_count.get(room_id, 0) > 0:
                continue
            nxt = engine._next_booking(room_id, now, self.BOOKED_WINDOW_MIN)
            if nxt is not None:
                out[room_id] = nxt.start_time.strftime("%H:%M")
        return out

    def snapshot(self, include_truth: bool) -> dict[str, Any]:
        snap = super().snapshot(include_truth)
        snap["booked"] = self.booked()
        return snap

    def frame(
        self, obs_since: int, truth_since: int, include_truth: bool
    ) -> tuple[dict[str, Any], int, int]:
        frame, obs_v, truth_v = super().frame(obs_since, truth_since, include_truth)
        frame["booked"] = self.booked()
        return frame, obs_v, truth_v

    def area_detail(self, area_id: str) -> dict[str, Any] | None:
        detail = self.state_v2.area_detail(area_id)
        if detail is None:
            return None
        engine = self.runner.engine
        assert isinstance(engine, EngineV2)
        now = engine.st.dt(self.runner.sim_t)
        bookings = engine.bookings_by_room.get(area_id, [])
        current = next((b for b in bookings if b.start_time <= now < b.end_time), None)
        upcoming = next((b for b in bookings if b.start_time > now), None)

        def booking(b: Any) -> dict[str, Any] | None:
            if b is None:
                return None
            return {
                "booking_id": b.booking_id,
                "start": b.start_time.strftime("%H:%M"),
                "end": b.end_time.strftime("%H:%M"),
                "attendees": len(b.attendee_employee_ids),
                "released": b.booking_id in engine.released,
                "checked_in": b.booking_id in engine.checked_in,
            }

        # Booking data is booking-system (SaaS) information, shown as such.
        detail["current_booking"] = booking(current)
        detail["next_booking"] = booking(upcoming)
        return detail
