"""Ground-truth positions for the Simulation View (dots). Never mixed into observed state.

Served only on the explicit truth channel (`truth=1` on the live WebSocket, /api/v1/live/truth).
"""

from __future__ import annotations

import hashlib
from collections import deque
from typing import Any

from twin_server.engine.simulation import TruthEvent, TruthTransition
from workplace_domain.enums import LocationType
from workplace_domain.models import MasterData

Position = list[Any]  # [x, y, floor_id, department, state]


def stable_jitter(key: str, span: float) -> tuple[float, float]:
    """Deterministic offset in [-span/2, span/2] so dots in one room don't overlap (not random)."""
    h = hashlib.blake2b(key.encode("utf-8"), digest_size=4).digest()
    return (h[0] / 255 - 0.5) * span, (h[1] / 255 - 0.5) * span


class TruthView:
    JITTER_SPAN = 0.8

    def __init__(self, master: MasterData, change_log_max: int) -> None:
        lay = master.layout
        self.desks = {w.workspace_id: (w.x, w.y) for w in lay.workspaces}
        self.boxes = {r.room_id: (r.x, r.y, r.width, r.height) for r in lay.rooms}
        self.boxes |= {z.zone_id: (z.x, z.y, z.width, z.height) for z in lay.zones}
        self.change_log_max = change_log_max
        self.version = 0
        self.reset()

    def reset(self) -> None:
        self.positions: dict[str, Position] = {}
        self.log: deque[tuple[int, str, Position | None]] = deque(maxlen=self.change_log_max)
        self.summary: dict[str, int] = {}
        self.version += 1

    def apply(self, event: TruthEvent) -> None:
        if not isinstance(event, TruthTransition):
            return
        pid, loc_type, loc_id = event.person_id, event.location_type, event.location_id
        self.version += 1
        if loc_type is None or loc_id is None:
            self.positions.pop(pid, None)
            self.log.append((self.version, pid, None))
            return
        if loc_type is LocationType.WORKSPACE:
            x, y = self.desks[loc_id]
        else:
            bx, by, bw, bh = self.boxes[loc_id]
            jx, jy = stable_jitter(pid + loc_id, self.JITTER_SPAN)
            x, y = bx + bw * (0.5 + jx), by + bh * (0.5 + jy)
        pos: Position = [round(x, 2), round(y, 2), event.floor_id, event.department, event.to_state]
        self.positions[pid] = pos
        self.log.append((self.version, pid, pos))

    def snapshot(self) -> dict[str, Any]:
        return {"version": self.version, "positions": dict(self.positions), "summary": self.summary}

    def delta(self, since: int) -> dict[str, Any] | None:
        oldest = self.log[0][0] if self.log else self.version + 1
        if since < oldest - 1 and since != self.version:
            return None
        changes: dict[str, Position | None] = {}
        for ver, pid, pos in self.log:
            if ver > since:
                changes[pid] = pos
        return {"version": self.version, "positions": changes, "summary": self.summary}
