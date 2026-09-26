"""v2 engine: same people as v1, plus per-area environment, energy and ESG automation.

Subclass of the v1 Engine so behaviour (arrivals, desks, meetings, badges, sensors) is identical;
only the environment tick is replaced (environment-and-esg.md §2-4):
- one environment area per zone and per room/common area, physics from ground-truth crowds
- ENVIRONMENT_READING per area with setpoint, HVAC mode, ventilation boost and light level
- ENERGY_INTERVAL per area every `energy.interval_minutes`
- the prototype rule set (HVAC, lighting, meeting rooms), reading OBSERVED data only:
  sensor reports (desk/room counts, the area's own reported temperature and CO2) and the
  booking system (bookings, panel check-ins). Rules never read ground truth.
"""

from __future__ import annotations

import uuid
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from twin_server.engine.simtime import SimTime
from twin_server.engine.simulation import (
    P_ENV,
    Engine,
    EventSink,
    RoomBooking,
    TruthSink,
)
from twin_server.v2.environment import (
    AreaEnv,
    EnergyAcc,
    accumulate_energy,
    daylight,
    light_lux,
    setpoint,
    step_physics,
)
from twin_server.v2.world import V2World
from workplace_domain.config import SimulationConfig
from workplace_domain.config.v2 import SimulationV2Config
from workplace_domain.enums import EntityType, EventType, RoomType, RunMode, ZoneType
from workplace_domain.events import EventEnvelope

UNSENSED_ZONE_TYPES = {ZoneType.CIRCULATION, ZoneType.ENTRANCE, ZoneType.MEETING}


@dataclass
class Area:
    area_id: str
    area_type: str  # ZONE | ROOM
    floor_id: str
    zone_id: str
    name: str
    area_m2: float
    facade: str | None
    capacity: int
    is_room: bool
    is_bookable: bool
    sensed: bool
    desks: list[str] = field(default_factory=list)  # desk sensors that report this area
    count_rooms: list[str] = field(default_factory=list)  # count sensors that report it
    meeting_rooms: list[str] = field(default_factory=list)  # rooms inside a zone (truth split)
    env: AreaEnv = field(default_factory=lambda: AreaEnv(temp=24.0, co2=450.0))
    energy: EnergyAcc = field(default_factory=EnergyAcc)
    flags: dict[str, float] = field(default_factory=dict)
    over_flagged: bool = False  # one FLAG_OVER_CAPACITY per crowding episode
    oversized_bookings: set[str] = field(default_factory=set)  # one flag per booking


class EngineV2(Engine):
    def __init__(
        self,
        config: SimulationConfig,
        v2: SimulationV2Config,
        world: V2World,
        start_date: date,
        sink: EventSink,
        truth_sink: TruthSink | None = None,
        mode: RunMode = RunMode.BATCH,
        run_id: uuid.UUID | None = None,
    ) -> None:
        self.v2, self.world = v2, world
        super().__init__(config, world.master, start_date, sink, truth_sink, mode, run_id)
        env = v2.environment
        live = mode is RunMode.LIVE
        self.env_interval = float(env.tick_live_s if live else env.tick_batch_s)
        self.released: dict[str, datetime] = {}
        self.checked_in: set[str] = set()
        # Bookings whose room was ever sensor-occupied during the booking (not a no-show).
        self.booking_used: set[str] = set()
        self.bookings_by_room: dict[str, list[RoomBooking]] = defaultdict(list)
        self._build_areas()

    # ------------------------------------------------------------------ areas
    def _build_areas(self) -> None:
        lay = self.master.layout
        env = self.v2.environment
        init = AreaEnv(temp=env.initial["temperature_c"], co2=env.initial["co2_ppm"])
        desks_by_zone: dict[str, list[str]] = defaultdict(list)
        for w in lay.workspaces:
            if w.workspace_id in self.desk_sensor:
                desks_by_zone[w.zone_id].append(w.workspace_id)
        rooms_by_zone: dict[str, list[str]] = defaultdict(list)
        common_by_zone: dict[str, str] = {}
        for r in lay.rooms:
            if r.room_type is RoomType.COMMON_AREA:
                common_by_zone[r.zone_id] = r.room_id
            else:
                rooms_by_zone[r.zone_id].append(r.room_id)
        meta = {a["area_id"]: a for a in self.world.env_areas}
        self.areas: dict[str, Area] = {}
        for z in lay.zones:
            if z.zone_id not in meta:
                continue  # zone filled by a common area: the common-area room is the area
            m = meta[z.zone_id]
            desks = desks_by_zone.get(z.zone_id, [])
            common = [common_by_zone[z.zone_id]] if z.zone_id in common_by_zone else []
            sensed = bool(desks or common) and z.zone_type not in UNSENSED_ZONE_TYPES
            capacity = m.get("capacity") or len(desks) or env.min_area_capacity
            self.areas[z.zone_id] = Area(
                z.zone_id,
                "ZONE",
                z.floor_id,
                z.zone_id,
                z.name,
                m["area_m2"],
                m.get("facade"),
                capacity,
                False,
                False,
                sensed,
                desks,
                common,
                rooms_by_zone.get(z.zone_id, []),
                AreaEnv(temp=init.temp, co2=init.co2),
            )
        for r in lay.rooms:
            m = meta[r.room_id]
            self.areas[r.room_id] = Area(
                r.room_id,
                "ROOM",
                r.floor_id,
                r.zone_id,
                r.name,
                m["area_m2"],
                m.get("facade"),
                r.capacity,
                True,
                r.is_bookable,
                True,
                [],
                [r.room_id],
                [],
                AreaEnv(temp=init.temp, co2=init.co2),
            )

    def _people(self, a: Area) -> int:
        """Ground truth people in an area (physics only)."""
        if a.is_room:
            return max(0, self.room_truth[a.area_id])
        inside_rooms = sum(self.room_truth[r] for r in a.meeting_rooms)
        return max(0, self.zone_truth[a.zone_id] - inside_rooms)

    def _observed_count(self, a: Area) -> int:
        """What the sensors report for the area (the only occupancy the BMS may use)."""
        return sum(self.desk_rep[d] for d in a.desks) + sum(self.room_rep[r] for r in a.count_rooms)

    # ------------------------------------------------------------------ bookings (SaaS)
    def _plan_meetings(self, day: date, t0: float, attendees: list[Any], rng: Any) -> None:
        super()._plan_meetings(day, t0, attendees, rng)
        self.bookings_by_room.clear()
        for b in self.bookings:
            self.bookings_by_room[b.room_id].append(b)
        for items in self.bookings_by_room.values():
            items.sort(key=lambda b: b.start_time)

    def _current_booking(self, room_id: str, now: datetime) -> RoomBooking | None:
        for b in self.bookings_by_room.get(room_id, []):
            if b.start_time <= now < b.end_time and b.booking_id not in self.released:
                return b
        return None

    def _next_booking(self, room_id: str, now: datetime, within_min: float) -> RoomBooking | None:
        items = self.bookings_by_room.get(room_id, [])
        starts = [b.start_time for b in items]
        i = bisect_left(starts, now)
        for b in items[i:]:
            if b.start_time > now + timedelta(minutes=within_min):
                return None
            if b.booking_id not in self.released:
                return b
        return None

    def _deliver(self, env: EventEnvelope) -> None:
        # Panel check-ins are observed booking-system data the room rules may use.
        if env.event_type is EventType.ROOM_CHECK_IN:
            self.checked_in.add(env.payload["booking_id"])
        super()._deliver(env)

    def meeting_start(self, mid: str, end_t: float) -> None:
        m = self.meetings.get(mid)
        if m is None or m.booking_id in self.released:
            return  # booking was auto-released: the meeting does not happen in this room
        super().meeting_start(mid, end_t)

    def truth_summary(self) -> dict[str, int]:
        summary = super().truth_summary()
        for p in self.persons.values():
            if p.inside and p.cur_floor:
                key = f"inside_{p.cur_floor}"
                summary[key] = summary.get(key, 0) + 1
        return summary

    # ------------------------------------------------------------------ environment tick
    def start(self, days: int | None = None) -> None:
        super().start(days)
        step = self.v2.energy.interval_minutes * 60
        self.schedule(step, P_ENV, self.energy_interval)

    def env_tick(self) -> None:
        cfg, energy = self.v2.environment, self.v2.energy
        dt_min = self.env_interval / 60
        hour = SimTime.hour_of(self.t)
        start, end = energy.operating_hours
        operating = start <= hour < end
        rng = self.env_rng
        for a in self.areas.values():
            e = a.env
            if not a.sensed or not self.v2.bms.enabled:
                # Building schedule (not automation): NORMAL + full lights in operating hours.
                e.mode, e.light = ("NORMAL", 100) if operating else ("ECO", 0)
                e.adj, e.boost = 0.0, False
            people = self._people(a)
            step_physics(e, people, a.capacity, a.area_m2, a.facade, hour, dt_min, cfg, rng)
            e.obs_temp = round(e.temp + rng.gauss(0, 0.05), 1)
            e.obs_co2 = round(e.co2 + rng.gauss(0, 5))
            self._reading(a, hour, rng)
            if self.v2.bms.enabled and a.sensed:
                self._rules(a, hour, operating)
            accumulate_energy(a.energy, e, a.area_m2, people, hour, dt_min, energy)
        self.schedule(self.t + self.env_interval, P_ENV, self.env_tick)

    def _reading(self, a: Area, hour: float, rng: Any) -> None:
        e = a.env
        sid = self.env_sensor.get(a.area_id, f"ENV_{a.area_id}")
        lux = light_lux(e, a.facade, hour, self.v2.environment)
        self.emit(
            EventType.ENVIRONMENT_READING,
            self.t,
            EntityType.ROOM if a.is_room else EntityType.ZONE,
            a.area_id,
            sid,
            a.floor_id,
            a.zone_id,
            {
                "sensor_id": sid,
                "readings": [
                    {"metric_type": "TEMPERATURE", "value": e.obs_temp, "unit": "C"},
                    {"metric_type": "CO2", "value": e.obs_co2, "unit": "PPM"},
                    {"metric_type": "LIGHT", "value": round(lux), "unit": "LUX"},
                ],
                "setpoint_c": round(setpoint(e, self.v2.environment), 1),
                "hvac_mode": e.mode,
                "ventilation_boost": e.boost,
                "light_level_pct": e.light,
            },
            rng=rng,
        )

    def energy_interval(self) -> None:
        for a in self.areas.values():
            acc = a.energy
            self.emit(
                EventType.ENERGY_INTERVAL,
                self.t,
                EntityType.ROOM if a.is_room else EntityType.ZONE,
                a.area_id,
                f"BMS_{self.bid}",
                a.floor_id,
                a.zone_id,
                {
                    "area_id": a.area_id,
                    "kwh_hvac": round(acc.kwh_hvac, 4),
                    "kwh_lighting": round(acc.kwh_lighting, 4),
                    "kwh_baseline": round(acc.kwh_baseline, 4),
                    "hvac_mode": a.env.mode,
                    "light_level_pct_avg": round(acc.light_level_sum / max(1, acc.ticks)),
                    "occupied_minutes": round(acc.occupied_minutes, 1),
                    "comfort_ok_minutes": round(acc.comfort_ok_minutes, 1),
                },
                rng=self.env_rng,
            )
            a.energy = EnergyAcc()
        self.schedule(self.t + self.v2.energy.interval_minutes * 60, P_ENV, self.energy_interval)

    # ------------------------------------------------------------------ automation rules
    def _rules(self, a: Area, hour: float, operating: bool) -> None:
        """Prototype rule set in order (environment-and-esg.md §4). OBSERVED inputs only."""
        b, e = self.v2.bms, a.env
        count = self._observed_count(a)
        now = self.st.dt(self.t)
        occupied = count > 0
        e.empty_since = (
            None if occupied else (e.empty_since if e.empty_since is not None else self.t)
        )
        empty_min = 0.0 if e.empty_since is None else (self.t - e.empty_since) / 60
        # At most one HVAC-mode/setpoint, one ventilation and one lighting action per tick.
        done = {"hvac": False, "vent": False, "light": False}
        booking = self._current_booking(a.area_id, now) if a.is_bookable else None

        def act(
            kind: str,
            rule: str,
            action: str,
            params: dict[str, Any],
            reason: str,
            booking_id: str | None = None,
        ) -> bool:
            if done[kind] or self.t - e.last_rule.get(rule, -1e9) < b.cooldown_minutes * 60:
                return False
            done[kind] = True
            e.last_rule[rule] = self.t
            prev = {
                "mode": e.mode,
                "setpoint_c": round(setpoint(e, self.v2.environment), 1),
                "boost": e.boost,
                "light_level_pct": e.light,
            }
            if action == "SET_HVAC_MODE":
                e.mode = params["mode"]
                if e.mode == "ECO":
                    e.adj = 0.0
            elif action == "ADJUST_SETPOINT":
                e.adj += params["delta_c"]
            elif action == "INCREASE_VENTILATION":
                e.boost = params["on"]
            elif action == "SET_LIGHT_LEVEL":
                e.light = params["level_pct"]
            self._action(a, rule, action, params, reason, prev, count, booking_id)
            return True

        # ---- meeting rooms first: releasing a no-show booking changes HVAC and lights together
        if booking and occupied:
            self.booking_used.add(booking.booking_id)
        no_show = booking is not None and booking.booking_id not in self.booking_used
        if booking and no_show and booking.booking_id not in self.checked_in:
            started_min = (now - booking.start_time).total_seconds() / 60
            if started_min >= b.rooms.release_after_minutes:
                self.released[booking.booking_id] = now
                a.flags["released"] = self.t
                e.mode, e.light, e.adj = "ECO", 0, 0.0
                done["hvac"] = done["vent"] = done["light"] = True
                self._action(
                    a,
                    "RELEASE_GHOST_BOOKING",
                    "RELEASE_BOOKING",
                    {
                        "booking_id": booking.booking_id,
                        "status": "RELEASED",
                        "release_reason": "NO_SHOW",
                    },
                    f"{a.name} booking released. No one arrived {b.rooms.release_after_minutes:g} "
                    "min after start.",
                    {"mode": "NORMAL"},
                    count,
                    booking.booking_id,
                )
                booking = None

        # ---- HVAC
        if (
            not occupied
            and empty_min >= b.eco_after_empty_minutes
            and e.mode not in ("ECO", "PRECOOL")
        ):
            act(
                "hvac",
                "HVAC_ECO_WHEN_EMPTY",
                "SET_HVAC_MODE",
                {"mode": "ECO"},
                f"{a.name} set to eco. Empty for {b.eco_after_empty_minutes:g} min.",
            )
        elif occupied and e.mode in ("ECO", "PRECOOL"):
            act(
                "hvac",
                "HVAC_NORMAL_ON_OCCUPANCY",
                "SET_HVAC_MODE",
                {"mode": "NORMAL"},
                f"{a.name} back to normal. People detected.",
            )
        elif occupied and e.obs_temp >= b.warm_threshold_c:
            current = setpoint(e, self.v2.environment)
            if current - 1.0 >= b.min_setpoint_c - 1e-9:
                act(
                    "hvac",
                    "COOL_WHEN_WARM",
                    "ADJUST_SETPOINT",
                    {"delta_c": -1.0},
                    f"Cooling increased in {a.name}. {e.obs_temp:.1f} °C with {count} people.",
                )
        if a.is_bookable and not done["hvac"] and e.mode == "ECO":
            nxt = self._next_booking(a.area_id, now, b.rooms.precool_lead_minutes)
            if (
                nxt
                and len(nxt.attendee_employee_ids)
                >= a.capacity * b.rooms.precool_min_expected_pct / 100
            ):
                act(
                    "hvac",
                    "PRECOOL_FOR_BOOKING",
                    "SET_HVAC_MODE",
                    {"mode": "PRECOOL"},
                    f"{a.name} pre-cooling. Booked for {nxt.start_time:%H:%M}, "
                    f"{len(nxt.attendee_employee_ids)} attendees.",
                    nxt.booking_id,
                )
        if e.obs_co2 > b.co2_boost_on_ppm and not e.boost:
            act(
                "vent",
                "VENT_BOOST_ON_CO2",
                "INCREASE_VENTILATION",
                {"on": True},
                f"{a.name} ventilation boosted. CO₂ {e.obs_co2:,.0f} ppm.",
            )
        elif e.boost and e.obs_co2 < b.co2_boost_off_ppm:
            act(
                "vent",
                "VENT_NORMAL",
                "INCREASE_VENTILATION",
                {"on": False},
                f"{a.name} ventilation back to normal. CO₂ {e.obs_co2:,.0f} ppm.",
            )

        # ---- lighting
        lights = b.lights
        dl = daylight(hour, self.v2.environment)
        if hour >= lights.after_hours_off_h and not occupied and e.light > 0:
            act(
                "light",
                "LIGHTS_OFF_AFTER_HOURS",
                "SET_LIGHT_LEVEL",
                {"level_pct": 0},
                f"{a.name} lights off after hours.",
            )
        elif (
            a.is_room
            and not occupied
            and empty_min >= lights.room_off_after_minutes
            and e.light > 0
        ):
            if not self._next_booking(a.area_id, now, 30):
                act(
                    "light",
                    "LIGHTS_OFF_EMPTY_ROOM",
                    "SET_LIGHT_LEVEL",
                    {"level_pct": 0},
                    f"{a.name} lights off.",
                )
        elif (
            not a.is_room
            and not occupied
            and empty_min >= lights.dim_empty_after_minutes
            and e.light > lights.dim_level_pct
        ):
            act(
                "light",
                "LIGHTS_DIM_WHEN_EMPTY",
                "SET_LIGHT_LEVEL",
                {"level_pct": lights.dim_level_pct},
                f"{a.name} dimmed to {lights.dim_level_pct}%. "
                f"Empty for {lights.dim_empty_after_minutes:g} min.",
            )
        elif (
            occupied
            and a.facade
            and dl >= lights.daylight_min_factor
            and e.light != lights.daylight_level_pct
        ):
            act(
                "light",
                "DAYLIGHT_HARVEST",
                "SET_LIGHT_LEVEL",
                {"level_pct": lights.daylight_level_pct},
                f"{a.name} dimmed to {lights.daylight_level_pct}%. Daylight.",
            )
        elif occupied and e.light < 100 and not (a.facade and dl >= lights.daylight_min_factor):
            act(
                "light",
                "LIGHTS_ON_OCCUPANCY",
                "SET_LIGHT_LEVEL",
                {"level_pct": 100},
                f"{a.name} lights on. People detected.",
            )

        # ---- advisory room flags
        rooms = b.rooms
        if a.is_room:
            if count > a.capacity:
                e.over_since = e.over_since if e.over_since is not None else self.t
                long_enough = (self.t - e.over_since) / 60 >= rooms.over_capacity_after_minutes
                if long_enough and not a.over_flagged:
                    a.over_flagged = True
                    e.boost = True
                    self._action(
                        a,
                        "FLAG_OVER_CAPACITY",
                        "FLAG_OVER_CAPACITY",
                        {"count": count},
                        f"{a.name} over capacity: {count} in {a.capacity} seats.",
                        {"boost": e.boost},
                        count,
                        booking.booking_id if booking else None,
                    )
            else:
                e.over_since = None
                a.over_flagged = False
            small = (
                occupied
                and booking is not None
                and count <= a.capacity * rooms.oversized_max_pct / 100
            )
            if small:
                e.oversize_since = e.oversize_since if e.oversize_since is not None else self.t
                long_enough = (self.t - e.oversize_since) / 60 >= rooms.oversized_after_minutes
                if (
                    long_enough
                    and booking is not None
                    and booking.booking_id not in a.oversized_bookings
                ):
                    a.oversized_bookings.add(booking.booking_id)
                    self._action(
                        a,
                        "FLAG_OVERSIZED_ROOM",
                        "FLAG_ROOM_RIGHTSIZE",
                        {"count": count},
                        f"{a.name} oversized: {count} people in {a.capacity} seats.",
                        {},
                        count,
                        booking.booking_id if booking else None,
                    )
            else:
                e.oversize_since = None

    def _action(
        self,
        a: Area,
        rule: str,
        action: str,
        params: dict[str, Any],
        reason: str,
        prev: dict[str, Any],
        count: int,
        booking_id: str | None,
    ) -> None:
        e = a.env
        self.emit(
            EventType.AUTOMATION_ACTION,
            self.t,
            EntityType.ROOM if a.is_room else EntityType.ZONE,
            a.area_id,
            f"BMS_{self.bid}",
            a.floor_id,
            a.zone_id,
            {
                "rule_id": rule,
                "trigger": {
                    "observed_values": {
                        "observed_count": count,
                        "temperature": e.obs_temp,
                        "co2": e.obs_co2,
                    }
                },
                "action": action,
                "action_params": params,
                "previous_state": prev,
                "hvac_zone_id": a.area_id,
                "area_type": a.area_type,
                "booking_id": booking_id,
                "reason": reason,
            },
            rng=self.env_rng,
        )
