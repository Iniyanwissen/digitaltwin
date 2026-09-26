"""v2 processor state: v1 LiveState plus per-area environment, ESG rollups and automation log.

Built from OBSERVED events only (environment-and-esg.md §5.3):
- ENVIRONMENT_READING -> area [temp, delta_15m, co2, mode, light, setpoint, boost] and a
  one-hour history per area (sparkline); delta_15m from the readings in the trend window
- AUTOMATION_ACTION -> automation log with reasons, room chips (released / over / too big)
- ENERGY_INTERVAL -> today's ESG rollups per floor and building
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any

from twin_server.processor.live_state import LiveState
from workplace_domain.config.schema import ProcessingConfig
from workplace_domain.config.v2 import SimulationV2Config
from workplace_domain.enums import EventType, RoomType
from workplace_domain.events import EventEnvelope
from workplace_domain.models import MasterData

HISTORY_MINUTES = 60
CHIP_MINUTES = 30  # how long an advisory chip stays visible without being re-raised
FLAG_CHIPS = {
    "RELEASE_BOOKING": "released",
    "FLAG_OVER_CAPACITY": "over",
    "FLAG_ROOM_RIGHTSIZE": "too_big",
}


class LiveStateV2(LiveState):
    def __init__(
        self,
        master: MasterData,
        cfg: ProcessingConfig,
        v2: SimulationV2Config,
        env_areas: list[dict[str, Any]],
    ) -> None:
        self.v2 = v2
        self.area_meta = {a["area_id"]: a for a in env_areas}
        self.meeting_room_ids = {
            r.room_id for r in master.layout.rooms if r.room_type is not RoomType.COMMON_AREA
        }
        super().__init__(master, cfg)

    def reset(self, run_id: Any) -> None:
        super().reset(run_id)
        self.areas: dict[str, list[Any]] = {}
        self.history: dict[str, deque[tuple[datetime, float | None, float | None]]] = defaultdict(
            deque
        )
        self.area_log: deque[tuple[int, str, list[Any]]] = deque(maxlen=self.cfg.change_log_max)
        self.chips: dict[str, tuple[str, datetime]] = {}
        self.last_action: dict[str, dict[str, Any]] = {}
        self.actions: deque[tuple[int, dict[str, Any]]] = deque(maxlen=self.cfg.feed_buffer)
        self.esg_floor: dict[str, dict[str, float]] = defaultdict(
            lambda: {"kwh": 0.0, "baseline": 0.0, "occupied": 0.0, "comfort": 0.0}
        )
        self.actions_by_rule: dict[str, int] = defaultdict(int)
        self._esg_day: str | None = None

    # ------------------------------------------------------------------ events
    def apply(self, env: EventEnvelope) -> None:
        if self.run_id is None or env.simulation_run_id != self.run_id:
            return
        if env.event_type is EventType.ENERGY_INTERVAL:
            # Energy intervals feed the ESG rollups only (not the event feed or v1 state).
            if env.event_id not in self.seen:
                self.seen.add(env.event_id)
                self.seen_q.append(env.event_id)
                self._energy(env)
            return
        duplicate = env.event_id in self.seen
        super().apply(env)
        if duplicate:
            return
        if env.event_type is EventType.ENVIRONMENT_READING and "hvac_mode" in env.payload:
            self._reading(env)
        elif env.event_type is EventType.AUTOMATION_ACTION and "reason" in env.payload:
            self._automation(env)

    def _reading(self, env: EventEnvelope) -> None:
        p, area, t = env.payload, env.entity_id, env.event_time
        values = {r["metric_type"]: r["value"] for r in p["readings"]}
        temp, co2 = values.get("TEMPERATURE"), values.get("CO2")
        hist = self.history[area]
        hist.append((t, temp, co2))
        while hist and hist[0][0] < t - timedelta(minutes=HISTORY_MINUTES):
            hist.popleft()
        window = t - timedelta(minutes=self.v2.environment.trend_window_min)
        past = next((h for h in hist if h[0] >= window), None)
        delta = round(temp - past[1], 1) if past and temp is not None else 0.0
        value = [
            temp,
            delta,
            co2,
            p["hvac_mode"],
            p["light_level_pct"],
            p["setpoint_c"],
            p["ventilation_boost"],
        ]
        if self.areas.get(area) != value:
            self.areas[area] = value
            self.version += 1
            self.area_log.append((self.version, area, value))

    def _automation(self, env: EventEnvelope) -> None:
        p, area, t = env.payload, env.entity_id, env.event_time
        meta = self.area_meta.get(area, {})
        item = {
            "t": t.strftime("%H:%M"),
            "area": area,
            "area_name": meta.get("name", area),
            "floor": env.floor_id,
            "rule": p["rule_id"],
            "action": p["action"],
            "tag": _tag(p["action"]),
            "reason": p["reason"],
        }
        self.version += 1
        self.actions.append((self.version, item))
        self.last_action[area] = item
        self.actions_by_rule[p["rule_id"]] += 1
        chip = FLAG_CHIPS.get(p["action"])
        if chip:
            self.chips[area] = (chip, t)

    def _energy(self, env: EventEnvelope) -> None:
        day = env.event_time.strftime("%Y-%m-%d")
        if self._esg_day != day:
            self.esg_floor.clear()
            self.actions_by_rule.clear()
            self._esg_day = day
        p = env.payload
        f = self.esg_floor[env.floor_id or ""]
        f["kwh"] += p["kwh_hvac"] + p["kwh_lighting"]
        f["baseline"] += p["kwh_baseline"]
        f["occupied"] += p["occupied_minutes"]
        f["comfort"] += p["comfort_ok_minutes"]

    # ------------------------------------------------------------------ views
    def esg(self, floor_id: str | None = None) -> dict[str, Any]:
        rows = [self.esg_floor[floor_id]] if floor_id else list(self.esg_floor.values())
        kwh = sum(r["kwh"] for r in rows)
        base = sum(r["baseline"] for r in rows)
        occ = sum(r["occupied"] for r in rows)
        ok = sum(r["comfort"] for r in rows)
        saved = max(0.0, base - kwh)
        e = self.v2.energy
        return {
            "kwh": round(kwh, 1),
            "baseline_kwh": round(base, 1),
            "saved_kwh": round(saved, 1),
            "saved_pct": round(100 * saved / base, 1) if base else 0.0,
            "co2e_kg": round(saved * e.grid_emission_factor_kg_per_kwh, 1),
            "cost_inr": round(saved * e.tariff_inr_per_kwh),
            "comfort_pct": round(100 * ok / occ, 1) if occ else 100.0,
        }

    def warm_areas(self) -> list[str]:
        """Areas observed occupied and at or above the warm threshold (warm-spot markers)."""
        threshold = self.v2.bms.warm_threshold_c
        return sorted(
            area
            for area, value in self.areas.items()
            if value[0] is not None and value[0] >= threshold and self._occupied(area)
        )

    def warm_spots(self) -> dict[str, int]:
        """Warm areas per floor (KPI strip)."""
        counts: dict[str, int] = defaultdict(int)
        for area in self.warm_areas():
            counts[self.area_meta.get(area, {}).get("floor_id", "")] += 1
        return dict(counts)

    def _occupied(self, area: str) -> bool:
        if area in self.rooms:
            return self.room_count.get(area, 0) > 0
        return any(self.desk_sensor.get(d) for d, w in self.desks.items() if w.zone_id == area)

    def floor_kpis(self) -> dict[str, dict[str, Any]]:
        """KPI strip per floor (max 5 cells, floor-twin-design-v2.md §5)."""
        warm = self.warm_spots()
        out: dict[str, dict[str, Any]] = {}
        for f in self.kpis()["floors"]:
            fid = f["floor_id"]
            rooms = [r for r in self.meeting_room_ids if self.rooms[r].floor_id == fid]
            in_use = sum(1 for r in rooms if self.room_count.get(r, 0) > 0)
            out[fid] = {
                "desk_util_pct": f["desk_util_pct"],
                "occupied_desks": f["occupied_desks"],
                "held_desks": f["held_desks"],
                "rooms_in_use": in_use,
                "rooms": len(rooms),
                "est_people": f["est_headcount"],
                "warm_spots": warm.get(fid, 0),
            }
        return out

    def active_chips(self, now: datetime | None) -> dict[str, str]:
        if now is None:
            return {}
        cutoff = now - timedelta(minutes=CHIP_MINUTES)
        return {area: chip for area, (chip, t) in self.chips.items() if t >= cutoff}

    def area_detail(self, area: str) -> dict[str, Any] | None:
        meta = self.area_meta.get(area)
        if meta is None:
            return None
        value = self.areas.get(area)
        return {
            **meta,
            "people": self.room_count.get(area)
            if area in self.rooms
            else sum(
                self.desk_sensor.get(d, 0) for d, w in self.desks.items() if w.zone_id == area
            ),
            "temperature": value[0] if value else None,
            "delta_15m": value[1] if value else None,
            "co2": value[2] if value else None,
            "hvac_mode": value[3] if value else None,
            "light_level_pct": value[4] if value else None,
            "setpoint_c": value[5] if value else None,
            "ventilation_boost": value[6] if value else None,
            "last_action": self.last_action.get(area),
            "history": [
                {"t": t.strftime("%H:%M"), "temp": temp, "co2": co2}
                for t, temp, co2 in self.history.get(area, [])
            ],
        }

    def snapshot(self) -> dict[str, Any]:
        snap = super().snapshot()
        snap.update(
            areas=dict(self.areas),
            esg=self.esg(),
            esg_floors={f: self.esg(f) for f in self.esg_floor},
            floor_kpis=self.floor_kpis(),
            chips=self.active_chips(self.sim_time),
            actions=[a for _, a in self.actions][-self.cfg.feed_per_frame :],
            warm_areas=self.warm_areas(),
        )
        return snap

    def delta(self, since: int) -> dict[str, Any] | None:
        base = super().delta(since)
        if base is None:
            return None
        areas: dict[str, list[Any]] = {}
        for ver, area, value in self.area_log:
            if ver > since:
                areas[area] = value
        base.update(
            areas=areas,
            esg=self.esg(),
            esg_floors={f: self.esg(f) for f in self.esg_floor},
            floor_kpis=self.floor_kpis(),
            chips=self.active_chips(self.sim_time),
            actions=[a for v, a in self.actions if v > since][-self.cfg.feed_per_frame :],
            warm_areas=self.warm_areas(),
        )
        return base


def _tag(action: str) -> str:
    if action in ("SET_LIGHT_LEVEL",):
        return "Lighting"
    if action in ("RELEASE_BOOKING", "FLAG_ROOM_RIGHTSIZE", "FLAG_OVER_CAPACITY"):
        return "Rooms"
    return "HVAC"
