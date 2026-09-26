"""Live simulation queries used by the API (layout, details, snapshot/frame building)."""

from __future__ import annotations

from typing import Any

from twin_server.engine.collaboration import CollaborationPair
from twin_server.live.runner import LiveRunner
from twin_server.live.truth_view import TruthView
from twin_server.processor.live_state import LiveState
from workplace_domain.enums import RoomType, WorkspaceType
from workplace_domain.models import MasterData


class LiveService:
    def __init__(
        self, master: MasterData, runner: LiveRunner, state: LiveState, truth: TruthView
    ) -> None:
        self.master, self.runner, self.state, self.truth = master, runner, state, truth
        self._layout = self._build_layout()

    # ------------------------------------------------------------------ layout
    def _build_layout(self) -> dict[str, Any]:
        lay = self.master.layout
        building = lay.buildings[0]
        desk_counts = {
            f.floor_id: sum(
                1
                for w in lay.workspaces
                if w.floor_id == f.floor_id and w.workspace_type is WorkspaceType.DESK
            )
            for f in lay.floors
        }
        return {
            "building": {
                "building_id": building.building_id,
                "name": building.name,
                "max_occupancy": building.max_occupancy,
            },
            "floors": [
                {
                    "floor_id": f.floor_id,
                    "floor_number": f.floor_number,
                    "name": f.name,
                    "desk_policy": f.desk_policy.value,
                    "width": f.plan_width,
                    "height": f.plan_height,
                    "desks": desk_counts[f.floor_id],
                }
                for f in sorted(lay.floors, key=lambda f: f.floor_number)
            ],
            "zones": [
                {
                    "zone_id": z.zone_id,
                    "floor_id": z.floor_id,
                    "name": z.name,
                    "zone_type": z.zone_type.value,
                    "x": z.x,
                    "y": z.y,
                    "width": z.width,
                    "height": z.height,
                    "is_restricted": z.is_restricted,
                }
                for z in lay.zones
            ],
            "workspaces": [
                {
                    "workspace_id": w.workspace_id,
                    "floor_id": w.floor_id,
                    "zone_id": w.zone_id,
                    "workspace_type": w.workspace_type.value,
                    "x": w.x,
                    "y": w.y,
                    "has_sensor": w.has_sensor,
                }
                for w in lay.workspaces
            ],
            "rooms": [
                {
                    "room_id": r.room_id,
                    "floor_id": r.floor_id,
                    "zone_id": r.zone_id,
                    "name": r.name,
                    "room_type": r.room_type.value,
                    "area_subtype": r.area_subtype.value if r.area_subtype else None,
                    "capacity": r.capacity,
                    "x": r.x,
                    "y": r.y,
                    "width": r.width,
                    "height": r.height,
                    "has_badge_reader": r.has_badge_reader,
                    "has_panel": r.has_panel,
                }
                for r in lay.rooms
            ],
            "access_points": [
                {
                    "access_point_id": a.access_point_id,
                    "floor_id": a.floor_id,
                    "name": a.name,
                    "reader_type": a.reader_type.value,
                    "x": a.x,
                    "y": a.y,
                }
                for a in lay.access_points
            ],
            "departments": [d.name for d in self.master.departments],
        }

    def layout(self) -> dict[str, Any]:
        return self._layout

    # ------------------------------------------------------------------ details
    def desk_detail(self, desk_id: str) -> dict[str, Any] | None:
        return self.state.desk_detail(desk_id)

    def room_detail(self, room_id: str) -> dict[str, Any] | None:
        room = next((r for r in self.master.layout.rooms if r.room_id == room_id), None)
        if room is None:
            return None
        now = self.runner.engine.st.dt(self.runner.sim_t)
        booking = next(
            (
                b
                for b in self.runner.engine.bookings
                if b.room_id == room_id and b.start_time <= now < b.end_time
            ),
            None,
        )
        return {
            "room_id": room.room_id,
            "name": room.name,
            "room_type": room.room_type.value,
            "area_subtype": room.area_subtype.value if room.area_subtype else None,
            "capacity": room.capacity,
            "sensor_count": self.state.room_count.get(room_id, 0),
            "has_panel": room.has_panel,
            "has_badge_reader": room.has_badge_reader,
            "bookable": room.room_type is not RoomType.COMMON_AREA,
            # Booking data comes from the booking system (identified, labelled as such).
            "current_booking": {
                "booking_id": booking.booking_id,
                "start": booking.start_time.strftime("%H:%M"),
                "end": booking.end_time.strftime("%H:%M"),
                "expected_attendees": len(booking.attendee_employee_ids),
                "checked_in": self.state.checkins.get(room_id) == booking.booking_id,
            }
            if booking
            else None,
        }

    def collaboration_truth(self) -> list[CollaborationPair]:
        return self.runner.engine.collaboration

    # ------------------------------------------------------------------ streaming
    def snapshot(self, include_truth: bool) -> dict[str, Any]:
        return self.runner.snapshot(include_truth)

    def frame(
        self, obs_since: int, truth_since: int, include_truth: bool
    ) -> tuple[dict[str, Any], int, int]:
        """Next frame for a client at the given cursors; falls back to a snapshot on resync."""
        delta = self.state.delta(obs_since)
        truth_delta = self.truth.delta(truth_since) if include_truth else None
        if delta is None or (include_truth and truth_delta is None):
            snap = self.snapshot(include_truth)
            return snap, self.state.version, self.truth.version
        frame: dict[str, Any] = {"type": "frame", **self.runner.status_info(), **delta}
        if include_truth and truth_delta is not None:
            frame["truth"] = truth_delta
        return frame, self.state.version, self.truth.version
