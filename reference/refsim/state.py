"""Reference event processor: builds CURRENT STATE from observed events only.

Mirrors docs/data-model.md §4 (Redis state) in memory:
- dedupe on event_id, per-key event-time guards (late/out-of-order events never regress state)
- identity views (who is inside, who is logged in where) come ONLY from identified events
- desk/room occupancy comes ONLY from anonymous sensors
- truth positions (for the Simulation View dots) are kept separately and never mixed into observed state
A versioned change log lets the server stream deltas to the UI.
"""
from __future__ import annotations

from collections import deque

from .common import stable_jitter


class LiveState:
    def __init__(self, layout: dict, max_log: int = 200_000):
        self.layout = layout
        self.desks = {w["workspace_id"]: w for w in layout["workspaces"]}
        self.rooms = {r["room_id"]: r for r in layout["rooms"]}
        self.zones = {z["zone_id"]: z for z in layout["zones"]}
        self.building_cap = layout["building"]["max_occupancy"]
        self.seen: set[str] = set()
        self.seen_q: deque = deque()
        self.last_time: dict[str, str] = {}
        # observed state
        self.inside: dict[str, dict] = {}            # employee -> {since, floor}
        self.desk_login: dict[str, str] = {}         # desk -> employee
        self.desk_sensor: dict[str, int] = {}        # desk -> 0/1
        self.desk_changed: dict[str, str] = {}
        self.room_count: dict[str, int] = {}
        self.env: dict[str, dict] = {}
        self.hvac: dict[str, str] = {}
        self.checkins: dict[str, str] = {}           # room -> booking
        self.peak = {"value": 0, "time": None}
        self.event_counts: dict[str, int] = {}
        self.automation_log: deque = deque(maxlen=50)
        # truth (simulation view only)
        self.positions: dict[str, list] = {}
        # streaming
        self.version = 0
        self.log: deque = deque(maxlen=max_log)
        self.feed: deque = deque(maxlen=300)
        self.series: list[dict] = []
        self._last_minute = None
        self.sim_iso = ""

    # ------------------------------------------------------------------ helpers
    def _change(self, kind: str, key: str, value):
        self.version += 1
        self.log.append((self.version, kind, key, value))

    def _fresh(self, key: str, t: str) -> bool:
        if self.last_time.get(key, "") > t:
            return False
        self.last_time[key] = t
        return True

    # ------------------------------------------------------------------ observed events
    def apply(self, env: dict):
        eid = env["event_id"]
        if eid in self.seen:
            return
        self.seen.add(eid)
        self.seen_q.append(eid)
        if len(self.seen_q) > 500_000:
            self.seen.discard(self.seen_q.popleft())
        et, t, p, ent = env["event_type"], env["event_time"], env["payload"], env["entity_id"]
        self.event_counts[et] = self.event_counts.get(et, 0) + 1
        if et == "ACCESS_IN" and self._fresh("person:" + ent, t):
            self.inside[ent] = {"since": t, "floor": env["floor_id"]}
            if len(self.inside) > self.peak["value"]:
                self.peak = {"value": len(self.inside), "time": t}
        elif et == "ACCESS_OUT" and self._fresh("person:" + ent, t):
            self.inside.pop(ent, None)
        elif et == "AREA_ACCESS" and ent in self.inside:
            if p["area_type"] == "FLOOR":
                self.inside[ent]["floor"] = p["area_id"]
        elif et == "WORKSPACE_LOGIN" and self._fresh("login:" + p["workspace_id"], t):
            self.desk_login[p["workspace_id"]] = ent
            self._desk_change(p["workspace_id"])
        elif et == "WORKSPACE_LOGOUT" and self._fresh("login:" + p["workspace_id"], t):
            if self.desk_login.get(p["workspace_id"]) == ent:
                del self.desk_login[p["workspace_id"]]
                self._desk_change(p["workspace_id"])
        elif et == "OCCUPANCY_CHANGED" and self._fresh("sensor:" + ent, t):
            self.desk_sensor[ent] = p["occupancy_status"]
            self.desk_changed[ent] = t
            self._desk_change(ent)
        elif et == "ROOM_OCCUPANCY_CHANGED" and self._fresh("room:" + ent, t):
            self.room_count[ent] = p["occupancy_count"]
            self._change("r", ent, p["occupancy_count"])
        elif et == "ROOM_CHECK_IN":
            self.checkins[p["room_id"]] = p["booking_id"]
        elif et == "ENVIRONMENT_READING":
            self.env[ent] = {r["metric_type"]: r["value"] for r in p["readings"]}
            self._change("z", ent, [self.env[ent].get("TEMPERATURE"), self.env[ent].get("CO2"), self.hvac.get(ent, "NORMAL")])
        elif et == "AUTOMATION_ACTION":
            if p["action"] == "SET_HVAC_MODE":
                self.hvac[ent] = p["action_params"]["mode"]
            self.automation_log.append({"t": t, "zone": ent, "rule": p["rule_id"], "action": p["action"], "params": p["action_params"]})
        if et not in ("ENVIRONMENT_READING", "SENSOR_HEARTBEAT", "SIMULATION_LIFECYCLE"):
            self.feed.append((self.version, self._feed_line(env)))

    def _desk_change(self, desk: str):
        self._change("d", desk, [self.desk_sensor.get(desk, 0), 1 if desk in self.desk_login else 0])

    @staticmethod
    def _feed_line(env: dict) -> dict:
        p = env["payload"]
        detail = {
            "ACCESS_IN": lambda: p["access_point_id"], "ACCESS_OUT": lambda: p["access_point_id"],
            "AREA_ACCESS": lambda: f"{p['area_type']} {p['area_id']}",
            "WORKSPACE_LOGIN": lambda: p["workspace_id"], "WORKSPACE_LOGOUT": lambda: f"{p['workspace_id']} ({p['logout_reason']})",
            "OCCUPANCY_CHANGED": lambda: "OCCUPIED" if p["occupancy_status"] else "VACANT",
            "ROOM_OCCUPANCY_CHANGED": lambda: f"{p['previous_count']}→{p['occupancy_count']}",
            "ROOM_CHECK_IN": lambda: p["booking_id"],
            "AUTOMATION_ACTION": lambda: f"{p['rule_id']} {p['action_params']}",
        }.get(env["event_type"], lambda: "")()
        return {"t": env["event_time"][11:19], "type": env["event_type"], "entity": env["entity_id"],
                "floor": env["floor_id"], "detail": detail, "identity": env["identity_class"]}

    # ------------------------------------------------------------------ truth (simulation view only)
    def apply_truth(self, tev: dict):
        if tev["event_type"] != "TRUTH_STATE_TRANSITION":
            return
        p = tev["payload"]
        pid, lt, lid = p["person_id"], p["location_type"], p["location_id"]
        if lt is None:
            self.positions.pop(pid, None)
            self._change("p", pid, None)
            return
        if lt == "DESK":
            w = self.desks[lid]
            x, y = w["x"], w["y"]
        else:
            box = self.rooms.get(lid) or self.zones[lid]
            jx, jy = stable_jitter(pid + lid, 0.8)
            x = box["x"] + box["width"] * (0.5 + jx)
            y = box["y"] + box["height"] * (0.5 + jy)
        pos = [round(x, 2), round(y, 2), p["floor_id"], p["department"], p["to_state"]]
        self.positions[pid] = pos
        self._change("p", pid, pos)

    # ------------------------------------------------------------------ KPIs
    def kpis(self) -> dict:
        total = len(self.desks)
        occ = sum(1 for v in self.desk_sensor.values() if v)
        held = sum(1 for d in self.desk_login if not self.desk_sensor.get(d))
        meeting_rooms = [r for r in self.rooms.values() if r["room_type"] != "COMMON_AREA"]
        rooms_in_use = sum(1 for r in meeting_rooms if self.room_count.get(r["room_id"], 0) > 0)
        occupants = sum(self.room_count.values())
        floors = []
        for f in self.layout["floors"]:
            fid = f["floor_id"]
            d_occ = sum(1 for d, v in self.desk_sensor.items() if v and self.desks[d]["floor_id"] == fid)
            d_held = sum(1 for d in self.desk_login if self.desks[d]["floor_id"] == fid and not self.desk_sensor.get(d))
            r_occ = sum(c for r, c in self.room_count.items() if self.rooms[r]["floor_id"] == fid)
            est = d_occ + r_occ
            floors.append({"floor_id": fid, "name": f["name"], "occupied_desks": d_occ, "held_desks": d_held,
                           "room_occupants": r_occ, "est_headcount": est, "desks": f["desk_count"],
                           "desk_util_pct": round(100 * d_occ / max(1, f["desk_count"]), 1)})
        return {"employees_inside": len(self.inside), "occupied_desks": occ, "held_desks": held,
                "available_desks": total - occ - held, "total_desks": total,
                "desk_util_pct": round(100 * occ / max(1, total), 1),
                "rooms_in_use": rooms_in_use, "meeting_rooms": len(meeting_rooms),
                "room_util_pct": round(100 * rooms_in_use / max(1, len(meeting_rooms)), 1),
                "room_occupants": occupants,
                "building_util_pct": round(100 * len(self.inside) / max(1, self.building_cap), 1),
                "peak_today": self.peak["value"], "peak_time": (self.peak["time"] or "")[11:16],
                "floors": floors, "hvac_eco_zones": sum(1 for m in self.hvac.values() if m == "ECO")}

    def sample(self, sim_iso: str):
        """Called by the runner every tick; records one point per simulated minute (today's rolling series)."""
        self.sim_iso = sim_iso
        minute = sim_iso[:16]
        if minute == self._last_minute:
            return
        if self._last_minute and minute[:10] != self._last_minute[:10]:
            self.series.clear()
            self.inside.clear()   # inferred exits for missed badge-outs (state only, no fabricated events)
            self.peak = {"value": 0, "time": None}
        self._last_minute = minute
        k = self.kpis()
        self.series.append({"m": minute[11:16], "inside": k["employees_inside"], "desks": k["occupied_desks"],
                            "held": k["held_desks"], "rooms": k["room_occupants"]})
