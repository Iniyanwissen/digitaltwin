"""Current state built from OBSERVED events only (typed port of reference/refsim/state.py).

- dedupe on event_id; per-key event-time guards (late/out-of-order events never regress state)
- identity views (who is inside, who is logged in where) come ONLY from identified events
- desk/room occupancy comes ONLY from anonymous sensors
- a versioned change log lets the live endpoint stream deltas (docs/live-streaming.md §4)
Truth positions for the Simulation View live in `twin_server.live.truth_view`, never here.
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from twin_server.activity import ActivityDescriber
from workplace_domain.config.schema import ProcessingConfig
from workplace_domain.enums import EventType, RoomType, WorkspaceType
from workplace_domain.events import EventEnvelope
from workplace_domain.models import MasterData

ChangeValue = Any  # desk: [sensor, logged_in] | room: count | zone: [temp, co2, hvac]
_SKIP_FEED = {
    EventType.ENVIRONMENT_READING,
    EventType.SENSOR_HEARTBEAT,
    EventType.SIMULATION_LIFECYCLE,
}


@dataclass
class Visit:
    since: datetime
    floor_id: str | None


class LiveState:
    def __init__(self, master: MasterData, cfg: ProcessingConfig) -> None:
        self.cfg = cfg
        self.describer = ActivityDescriber(master)
        lay = master.layout
        self.desks = {w.workspace_id: w for w in lay.workspaces}
        self.rooms = {r.room_id: r for r in lay.rooms}
        self.floors = sorted(lay.floors, key=lambda f: f.floor_number)
        self.building_capacity = sum(b.max_occupancy for b in lay.buildings)
        self.desk_count = {
            f.floor_id: sum(
                1
                for w in lay.workspaces
                if w.floor_id == f.floor_id and w.workspace_type is WorkspaceType.DESK
            )
            for f in self.floors
        }
        self.meeting_rooms = [r for r in lay.rooms if r.room_type is not RoomType.COMMON_AREA]
        self.version = 0
        self.reset(None)

    # ------------------------------------------------------------------ lifecycle
    def reset(self, run_id: uuid.UUID | None) -> None:
        """Clear all state for a new run; events from other runs are ignored."""
        self.run_id = run_id
        self.seen: set[uuid.UUID] = set()
        self.seen_q: deque[uuid.UUID] = deque()
        self.last_time: dict[str, datetime] = {}
        self.inside: dict[str, Visit] = {}
        self.desk_login: dict[str, str] = {}
        self.desk_sensor: dict[str, int] = {}
        self.desk_changed: dict[str, datetime] = {}
        self.room_count: dict[str, int] = {}
        self.env: dict[str, dict[str, float]] = {}
        self.hvac: dict[str, str] = {}
        self.checkins: dict[str, str] = {}
        self.peak_value = 0
        self.peak_time: datetime | None = None
        self.event_counts: dict[str, int] = {}
        self.automation_log: deque[dict[str, Any]] = deque(maxlen=self.cfg.automation_log)
        self.log: deque[tuple[int, str, str, ChangeValue]] = deque(maxlen=self.cfg.change_log_max)
        self.feed: deque[tuple[int, dict[str, Any]]] = deque(maxlen=self.cfg.feed_buffer)
        self.series: list[dict[str, Any]] = []
        self._last_minute: str | None = None
        # People activity (identified events only) and current status per person.
        self.activity: deque[tuple[int, dict[str, Any]]] = deque(maxlen=self.cfg.feed_buffer)
        self.person_status: dict[str, dict[str, Any]] = {}
        self.login_of: dict[str, str] = {}
        self.sim_time: datetime | None = None
        self.version += 1  # clients holding an older version resync

    # ------------------------------------------------------------------ helpers
    def _change(self, kind: str, key: str, value: ChangeValue) -> None:
        self.version += 1
        self.log.append((self.version, kind, key, value))

    def _fresh(self, key: str, t: datetime) -> bool:
        last = self.last_time.get(key)
        if last is not None and last > t:
            return False
        self.last_time[key] = t
        return True

    def _desk_value(self, desk: str) -> list[int]:
        return [self.desk_sensor.get(desk, 0), 1 if desk in self.desk_login else 0]

    def _desk_change(self, desk: str) -> None:
        self._change("d", desk, self._desk_value(desk))

    # ------------------------------------------------------------------ observed events
    def apply(self, env: EventEnvelope) -> None:
        if self.run_id is None or env.simulation_run_id != self.run_id:
            return
        if env.event_id in self.seen:
            return
        self.seen.add(env.event_id)
        self.seen_q.append(env.event_id)
        if len(self.seen_q) > self.cfg.dedupe_window:
            self.seen.discard(self.seen_q.popleft())
        et, t, p, ent = env.event_type, env.event_time, env.payload, env.entity_id
        self.event_counts[et] = self.event_counts.get(et, 0) + 1
        if et is EventType.ACCESS_IN and self._fresh("person:" + ent, t):
            self.inside[ent] = Visit(t, env.floor_id)
            if len(self.inside) > self.peak_value:
                self.peak_value, self.peak_time = len(self.inside), t
        elif et is EventType.ACCESS_OUT and self._fresh("person:" + ent, t):
            self.inside.pop(ent, None)
        elif et is EventType.AREA_ACCESS and ent in self.inside:
            if p["area_type"] == "FLOOR":
                self.inside[ent].floor_id = p["area_id"]
        elif et is EventType.WORKSPACE_LOGIN and self._fresh("login:" + p["workspace_id"], t):
            self.desk_login[p["workspace_id"]] = ent
            self._desk_change(p["workspace_id"])
        elif et is EventType.WORKSPACE_LOGOUT and self._fresh("login:" + p["workspace_id"], t):
            if self.desk_login.get(p["workspace_id"]) == ent:
                del self.desk_login[p["workspace_id"]]
                self._desk_change(p["workspace_id"])
        elif et is EventType.OCCUPANCY_CHANGED and self._fresh("sensor:" + ent, t):
            self.desk_sensor[ent] = p["occupancy_status"]
            self.desk_changed[ent] = t
            self._desk_change(ent)
        elif et is EventType.ROOM_OCCUPANCY_CHANGED and self._fresh("room:" + ent, t):
            self.room_count[ent] = p["occupancy_count"]
            self._change("r", ent, p["occupancy_count"])
        elif et is EventType.ROOM_CHECK_IN:
            self.checkins[p["room_id"]] = p["booking_id"]
        elif et is EventType.ENVIRONMENT_READING:
            self.env[ent] = {r["metric_type"]: r["value"] for r in p["readings"]}
            self._change("z", ent, self.zone_value(ent))
        elif et is EventType.AUTOMATION_ACTION:
            if p["action"] == "SET_HVAC_MODE":
                self.hvac[ent] = p["action_params"]["mode"]
                self._change("z", ent, self.zone_value(ent))
            self.automation_log.append(
                {
                    "t": t.strftime("%H:%M"),
                    "zone": ent,
                    "rule": p["rule_id"],
                    "action": p["action"],
                    "params": p["action_params"],
                }
            )
        if et not in _SKIP_FEED:
            self.feed.append((self.version, self._feed_line(env)))
        if env.identity_class == "IDENTIFIED":
            self._person_activity(env)

    def _person_activity(self, env: EventEnvelope) -> None:
        ent, p = env.entity_id, env.payload
        if env.event_type is EventType.WORKSPACE_LOGIN:
            self.login_of[ent] = p["workspace_id"]
        elif (
            env.event_type is EventType.WORKSPACE_LOGOUT
            and self.login_of.get(ent) == p["workspace_id"]
        ):
            del self.login_of[ent]
        item = self.describer.observed(env)
        if item is None:
            return
        visit = self.inside.get(ent)
        status = {
            **{k: item[k] for k in ("code", "name", "dept", "t")},
            "text": self.describer.observed_status(
                visit is not None, visit.floor_id if visit else None, self.login_of.get(ent)
            ),
            "inside": visit is not None,
        }
        self.person_status[ent] = status
        self._change("s", ent, status)
        self.activity.append((self.version, item))

    def zone_value(self, zone_id: str) -> list[Any]:
        e = self.env.get(zone_id, {})
        return [e.get("TEMPERATURE"), e.get("CO2"), self.hvac.get(zone_id, "NORMAL")]

    @staticmethod
    def _feed_line(env: EventEnvelope) -> dict[str, Any]:
        p = env.payload
        et = env.event_type
        if et in (EventType.ACCESS_IN, EventType.ACCESS_OUT):
            detail = p["access_point_id"]
        elif et is EventType.AREA_ACCESS:
            detail = f"{p['area_type']} {p['area_id']}"
        elif et is EventType.WORKSPACE_LOGIN:
            detail = p["workspace_id"]
        elif et is EventType.WORKSPACE_LOGOUT:
            detail = f"{p['workspace_id']} ({p['logout_reason']})"
        elif et is EventType.OCCUPANCY_CHANGED:
            detail = "OCCUPIED" if p["occupancy_status"] else "VACANT"
        elif et is EventType.ROOM_OCCUPANCY_CHANGED:
            detail = f"{p['previous_count']}→{p['occupancy_count']}"
        elif et is EventType.ROOM_CHECK_IN:
            detail = p["booking_id"]
        elif et is EventType.AUTOMATION_ACTION:
            detail = f"{p['rule_id']} {p['action_params']}"
        else:
            detail = ""
        return {
            "t": env.event_time.strftime("%H:%M:%S"),
            "type": str(et),
            "entity": env.entity_id,
            "floor": env.floor_id,
            "detail": detail,
            "identity": str(env.identity_class),
        }

    # ------------------------------------------------------------------ KPIs
    def kpis(self) -> dict[str, Any]:
        total = len(self.desks)
        occ = sum(1 for v in self.desk_sensor.values() if v)
        held = sum(1 for d in self.desk_login if not self.desk_sensor.get(d))
        rooms_in_use = sum(1 for r in self.meeting_rooms if self.room_count.get(r.room_id, 0) > 0)
        floors = []
        for f in self.floors:
            fid = f.floor_id
            d_occ = sum(
                1 for d, v in self.desk_sensor.items() if v and self.desks[d].floor_id == fid
            )
            d_held = sum(
                1
                for d in self.desk_login
                if self.desks[d].floor_id == fid and not self.desk_sensor.get(d)
            )
            r_occ = sum(c for r, c in self.room_count.items() if self.rooms[r].floor_id == fid)
            desks = self.desk_count[fid]
            floors.append(
                {
                    "floor_id": fid,
                    "name": f.name,
                    "occupied_desks": d_occ,
                    "held_desks": d_held,
                    "room_occupants": r_occ,
                    "est_headcount": d_occ + r_occ,
                    "desks": desks,
                    "desk_util_pct": round(100 * d_occ / max(1, desks), 1),
                }
            )
        n_rooms = len(self.meeting_rooms)
        return {
            "employees_inside": len(self.inside),
            "occupied_desks": occ,
            "held_desks": held,
            "available_desks": total - occ - held,
            "total_desks": total,
            "desk_util_pct": round(100 * occ / max(1, total), 1),
            "rooms_in_use": rooms_in_use,
            "meeting_rooms": n_rooms,
            "room_util_pct": round(100 * rooms_in_use / max(1, n_rooms), 1),
            "room_occupants": sum(self.room_count.values()),
            "building_util_pct": round(100 * len(self.inside) / max(1, self.building_capacity), 1),
            "peak_today": self.peak_value,
            "peak_time": self.peak_time.strftime("%H:%M") if self.peak_time else "",
            "floors": floors,
            "hvac_eco_zones": sum(1 for m in self.hvac.values() if m == "ECO"),
        }

    def sample(self, sim_time: datetime) -> None:
        """Called by the runner each tick; records one series point per simulated minute."""
        self.sim_time = sim_time
        minute = sim_time.strftime("%Y-%m-%d %H:%M")
        if minute == self._last_minute:
            return
        if self._last_minute and minute[:10] != self._last_minute[:10]:
            self.series.clear()
            self.inside.clear()  # inferred exits for missed badge-outs (state only, no events)
            for pid in list(self.person_status):
                self._change("s", pid, None)
            self.person_status.clear()
            self.peak_value, self.peak_time = 0, None
        self._last_minute = minute
        k = self.kpis()
        self.series.append(
            {
                "m": minute[11:],
                "inside": k["employees_inside"],
                "desks": k["occupied_desks"],
                "held": k["held_desks"],
                "rooms": k["room_occupants"],
            }
        )

    # ------------------------------------------------------------------ streaming
    def snapshot(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "desks": {d: self._desk_value(d) for d in self.desks},
            "rooms": dict(self.room_count),
            "zones": {z: self.zone_value(z) for z in self.env},
            "kpis": self.kpis(),
            "series": list(self.series),
            "events_total": sum(self.event_counts.values()),
            "automation": list(self.automation_log)[-5:],
            "people": dict(self.person_status),
            "activity": [a for _, a in self.activity][-self.cfg.feed_buffer :],
        }

    def delta(self, since: int) -> dict[str, Any] | None:
        """Changes after `since` (last value per key wins). None = client must resync."""
        oldest = self.log[0][0] if self.log else self.version + 1
        if since < oldest - 1 and since != self.version:
            return None
        desks: dict[str, ChangeValue] = {}
        rooms: dict[str, ChangeValue] = {}
        zones: dict[str, ChangeValue] = {}
        people: dict[str, ChangeValue] = {}
        target = {"d": desks, "r": rooms, "z": zones, "s": people}
        for ver, kind, key, val in self.log:
            if ver > since:
                target[kind][key] = val
        feed = [f for v, f in self.feed if v > since][-self.cfg.feed_per_frame :]
        activity = [a for v, a in self.activity if v > since][-self.cfg.feed_per_frame :]
        return {
            "version": self.version,
            "desks": desks,
            "rooms": rooms,
            "zones": zones,
            "feed": feed,
            "people": people,
            "activity": activity,
            "kpis": self.kpis(),
            "point": self.series[-1] if self.series else None,
            "events_total": sum(self.event_counts.values()),
            "automation": list(self.automation_log)[-5:],
        }

    def desk_detail(self, desk: str) -> dict[str, Any] | None:
        w = self.desks.get(desk)
        if w is None:
            return None
        changed = self.desk_changed.get(desk)
        return {
            "workspace_id": desk,
            "zone_id": w.zone_id,
            "floor_id": w.floor_id,
            "device_type": w.device_type.value,
            "has_sensor": w.has_sensor,
            "sensor_status": "OCCUPIED" if self.desk_sensor.get(desk) else "VACANT",
            "last_sensor_change": changed.strftime("%H:%M:%S") if changed else None,
            # Identity ONLY from workstation login, never from the anonymous sensor.
            "logged_in_employee": self.desk_login.get(desk),
        }
