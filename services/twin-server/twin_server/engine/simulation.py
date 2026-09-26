"""Discrete-event simulation engine (typed port of reference/refsim/engine.py).

Ground truth (people and where they really are) -> observers (what each device can know) ->
delivery -> sink. The same code runs LIVE (scaled clock, driven by the live runner) and BATCH
(history, as fast as possible); only the environment interval and heartbeats differ.

Hybrid differences from the reference (docs/decision-log.md, 2026-09-26):
- runs on our master data (MasterData records) instead of the reference layout dicts
- hot-desk zones are OPEN_WORKSPACE and TEAM_NEIGHBORHOOD; cabins are assigned only
- common areas are looked up on the nearest floor that has them (not every floor has a lounge)
- meeting participants can come from hidden partner teams (engine.collaboration)
- all timings come from config (no magic numbers); streams are RngFactory.py_stream
"""

from __future__ import annotations

import heapq
import math
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from twin_server.engine.collaboration import CollaborationPair, generate_pairs, partners_by_team
from twin_server.engine.simtime import SECONDS_PER_DAY, SimTime
from workplace_domain.config import SimulationConfig
from workplace_domain.enums import (
    AreaSubtype,
    BehaviorProfile,
    EntityType,
    EventType,
    LocationType,
    PersonState,
    PlannedMode,
    ReaderType,
    RoomType,
    RunMode,
    SensorType,
    Source,
    WorkMode,
    WorkspaceType,
    ZoneType,
)
from workplace_domain.events import EVENT_TYPE_SPECS, EventEnvelope, make_event_id
from workplace_domain.models import MasterData, Room, Workspace, Zone
from workplace_domain.rng import PyRandom, RngFactory, lognormal_from_median_p90, weighted_choice

# Scheduler priorities at equal timestamps (lower runs first).
P_PLAN, P_MEETING, P_PERSON, P_OBSERVER, P_ENV, P_DELIVER = 1, 2, 3, 4, 5, 7

DESK_ZONE_TYPES = (ZoneType.OPEN_WORKSPACE, ZoneType.TEAM_NEIGHBORHOOD)
RUN_NAMESPACE = uuid.UUID("0b8f3c7e-6a51-5f4e-9d2c-7e1a4b3c9f10")

EventSink = Callable[[EventEnvelope], None]


# ------------------------------------------------------------------ truth records


@dataclass(frozen=True, slots=True)
class TruthTransition:
    event_time: datetime
    sim_t: float
    person_id: str
    team_id: str
    department: str
    from_state: PersonState
    to_state: PersonState
    location_type: LocationType | None
    location_id: str | None
    floor_id: str | None
    held_workspace_id: str | None
    reason: str
    meeting_id: str | None


@dataclass(frozen=True, slots=True)
class TruthDeskSearchFailed:
    event_time: datetime
    sim_t: float
    person_id: str
    floor_id: str
    fallback_location_id: str


TruthEvent = TruthTransition | TruthDeskSearchFailed
TruthSink = Callable[[TruthEvent], None]


# ------------------------------------------------------------------ SaaS-side records


@dataclass(frozen=True, slots=True)
class RoomBooking:
    booking_id: str
    room_id: str
    organizer_employee_id: str
    attendee_employee_ids: tuple[str, ...]
    start_time: datetime
    end_time: datetime
    meeting_id: str


@dataclass(frozen=True, slots=True)
class LeaveRecord:
    leave_id: str
    employee_id: str
    leave_date: date
    leave_type: str


@dataclass(frozen=True, slots=True)
class Meeting:
    meeting_id: str
    booking_id: str
    room_id: str
    organizer: str
    participants: tuple[str, ...]
    no_show: frozenset[str]


# ------------------------------------------------------------------ runtime state


class Person:
    __slots__ = (
        "assigned_desk",
        "corr",
        "cur_floor",
        "depart_t",
        "dept",
        "desk",
        "fav_desk",
        "home_floor",
        "id",
        "in_meeting",
        "inside",
        "leaving",
        "loc_id",
        "loc_type",
        "logged_in",
        "login_iso",
        "lunch_taken",
        "no_login",
        "pref_zone",
        "profile",
        "rng",
        "state",
        "team",
        "tok",
        "visit",
        "work_mode",
        "zone",
    )

    def __init__(
        self,
        pid: str,
        team: str,
        dept: str,
        home_floor: str,
        pref_zone: str,
        profile: BehaviorProfile,
        work_mode: WorkMode,
    ) -> None:
        self.id, self.team, self.dept = pid, team, dept
        self.home_floor, self.pref_zone = home_floor, pref_zone
        self.profile, self.work_mode = profile, work_mode
        self.state = PersonState.OUTSIDE_OFFICE
        self.loc_type: LocationType | None = None
        self.loc_id: str | None = None
        self.cur_floor: str | None = None
        self.zone: str | None = None
        self.desk: str | None = None
        self.fav_desk: str | None = None
        self.assigned_desk: str | None = None
        self.inside = False
        self.tok = 0
        self.depart_t = 0.0
        self.leaving = False
        self.in_meeting: str | None = None
        self.lunch_taken = False
        self.logged_in: str | None = None
        self.login_iso: str | None = None
        self.no_login = False
        self.visit = 0
        self.corr: str | None = None
        self.rng: PyRandom = PyRandom(0)  # replaced by the per-person-day stream


@dataclass
class ZoneEnvironment:
    temp: float
    co2: float
    hum: float
    mode: str = "NORMAL"
    adj: float = 0.0
    boost: bool = False
    empty_since: float | None = None
    last: dict[str, float] = field(default_factory=dict)


HeapItem = tuple[float, int, int, Callable[..., None], tuple[Any, ...]]


class Engine:
    def __init__(
        self,
        config: SimulationConfig,
        master: MasterData,
        start_date: date,
        sink: EventSink,
        truth_sink: TruthSink | None = None,
        mode: RunMode = RunMode.BATCH,
        run_id: uuid.UUID | None = None,
    ) -> None:
        self.cfg, self.master, self.mode = config, master, mode
        self.sink, self.truth_sink = sink, truth_sink
        self.run_id = run_id or uuid.uuid5(RUN_NAMESPACE, f"{config.seed}|{start_date}|{mode}")
        self.st = SimTime(start_date, config.timezone)
        self.rngf = RngFactory(config.seed)
        self.obs_rng = self.rngf.py_stream("observers", start_date)
        self.env_rng = self.rngf.py_stream("environment", start_date)
        self.t = 0.0
        self.days: int | None = None
        self._heap: list[HeapItem] = []
        self._hseq = 0
        self.ev_seq = 0
        self.counters: dict[str, int] = defaultdict(int)
        self.meetings: dict[str, Meeting] = {}
        self.bookings: list[RoomBooking] = []
        self.leave_records: list[LeaveRecord] = []
        live = mode is RunMode.LIVE
        self.env_interval = float(
            config.sensors.environment_poll_interval
            if live
            else config.batch.environment_poll_interval
        )
        emit_hb = live or config.batch.emit_heartbeats
        self.heartbeat_interval = float(config.sensors.desk_poll_interval) if emit_hb else 0.0
        self.collaboration: list[CollaborationPair] = generate_pairs(
            master.teams, config.meetings.collaboration, self.rngf
        )
        self._index()

    # ------------------------------------------------------------------ indexes
    def _index(self) -> None:
        lay = self.master.layout
        self.bid = lay.buildings[0].building_id
        self.building_capacity = lay.buildings[0].max_occupancy
        floors = sorted(lay.floors, key=lambda f: f.floor_number)
        self.floor_num = {f.floor_id: f.floor_number for f in floors}
        self.ground = floors[0].floor_id
        self.zones: dict[str, Zone] = {z.zone_id: z for z in lay.zones}
        self.desks: dict[str, Workspace] = {w.workspace_id: w for w in lay.workspaces}
        self.rooms: dict[str, Room] = {r.room_id: r for r in lay.rooms}

        self.lobby: dict[str, str] = {}
        for f in floors:
            hall = [
                z
                for z in lay.zones
                if z.floor_id == f.floor_id
                and z.zone_type in (ZoneType.ENTRANCE, ZoneType.CIRCULATION)
            ]
            entrance = [z for z in hall if z.zone_type is ZoneType.ENTRANCE]
            pick = entrance or sorted(hall, key=lambda z: (z.area_sqm, z.zone_id))
            self.lobby[f.floor_id] = pick[0].zone_id

        self.common: dict[str, dict[AreaSubtype, str]] = defaultdict(dict)
        for r in lay.rooms:
            if r.room_type is RoomType.COMMON_AREA and r.area_subtype is not None:
                self.common[r.floor_id][r.area_subtype] = r.room_id

        self.ap_floor: dict[str, str] = {}
        self.ap_room: dict[str, str] = {}
        self.ap_zone: dict[str, str] = {}
        by_type = {
            ReaderType.FLOOR_LOBBY: self.ap_floor,
            ReaderType.ROOM_DOOR: self.ap_room,
            ReaderType.SECURE_ZONE: self.ap_zone,
        }
        for ap in lay.access_points:
            if ap.reader_type in by_type:
                by_type[ap.reader_type][ap.target_id] = ap.access_point_id
        self.entrance = next(
            ap.access_point_id
            for ap in lay.access_points
            if ap.reader_type is ReaderType.BUILDING_ENTRANCE
        )
        self.desk_sensor: dict[str, str] = {}
        self.room_sensor: dict[str, str] = {}
        self.env_sensor: dict[str, str] = {}
        for s in lay.sensors:
            {
                SensorType.DESK_OCCUPANCY: self.desk_sensor,
                SensorType.ROOM_COUNT: self.room_sensor,
                SensorType.ENVIRONMENT: self.env_sensor,
            }[s.sensor_type][s.target_id] = s.sensor_id

        dept_name = {d.department_id: d.name for d in self.master.departments}
        self.persons: dict[str, Person] = {
            e.employee_id: Person(
                e.employee_id,
                e.team_id,
                dept_name[e.department_id],
                e.home_floor_id,
                e.preferred_zone_id,
                e.behavior_profile,
                e.work_mode,
            )
            for e in self.master.employees
        }
        self.teams = {t.team_id: t for t in self.master.teams}
        self.team_zones: dict[str, list[str]] = defaultdict(list)
        for a in sorted(self.master.team_zone_allocations, key=lambda a: (-a.share, a.zone_id)):
            self.team_zones[a.team_id].append(a.zone_id)
        self.allowed: dict[str, set[str]] = defaultdict(set)
        for rule in self.master.zone_access_rules:
            self.allowed[rule.zone_id].add(rule.team_id)
        self.patterns: dict[tuple[str, int], PlannedMode] = {
            (p.employee_id, p.iso_weekday): p.planned_mode for p in self.master.work_patterns
        }
        assigned = {a.workspace_id: a.employee_id for a in self.master.assignments}
        for wid, eid in assigned.items():
            self.persons[eid].assigned_desk = wid
        # Hot-desk pools per zone: ordered lists for determinism (never iterate sets).
        self.pool: dict[str, list[str]] = defaultdict(list)
        for w in lay.workspaces:
            if (
                w.status == "ACTIVE"
                and w.workspace_type is WorkspaceType.DESK
                and w.workspace_id not in assigned
            ):
                self.pool[w.zone_id].append(w.workspace_id)
        self.desk_zones = [z for z in lay.zones if z.zone_type in DESK_ZONE_TYPES]
        self.claimed: dict[str, str] = {}
        self.partners = partners_by_team(self.collaboration)

        # Ground truth occupancy
        self.desk_truth: dict[str, int] = defaultdict(int)
        self.room_truth: dict[str, int] = defaultdict(int)
        self.zone_truth: dict[str, int] = defaultdict(int)
        # Observer (reported) state
        self.desk_rep: dict[str, int] = defaultdict(int)
        self.desk_tok: dict[str, int] = defaultdict(int)
        self.room_rep: dict[str, int] = defaultdict(int)
        self.room_pending: set[str] = set()
        self.rooms_by_zone: dict[str, list[str]] = defaultdict(list)
        for r in lay.rooms:
            self.rooms_by_zone[r.zone_id].append(r.room_id)
        self.desks_by_zone: dict[str, list[str]] = defaultdict(list)
        for w in lay.workspaces:
            if w.workspace_id in self.desk_sensor:
                self.desks_by_zone[w.zone_id].append(w.workspace_id)
        init = self.cfg.environment.initial
        self.env = {
            zid: ZoneEnvironment(init["temperature_c"], init["co2_ppm"], init["humidity_pct"])
            for zid in self.zones
        }

    # ------------------------------------------------------------------ scheduler
    def schedule(self, t: float, prio: int, fn: Callable[..., None], *args: Any) -> None:
        self._hseq += 1
        heapq.heappush(self._heap, (t, prio, self._hseq, fn, args))

    def peek(self) -> float | None:
        return self._heap[0][0] if self._heap else None

    def step_until(self, t_end: float) -> int:
        n = 0
        while self._heap and self._heap[0][0] <= t_end:
            t, _, _, fn, args = heapq.heappop(self._heap)
            self.t = t
            fn(*args)
            n += 1
        self.t = max(self.t, t_end)
        return n

    def start(self, days: int | None = None) -> None:
        """days=None -> open-ended (LIVE)."""
        self.days = days
        self.schedule(0.0, P_PLAN, self.day_start, 0)
        self.schedule(0.0, P_ENV, self.env_tick)
        if self.heartbeat_interval:
            self.schedule(self.heartbeat_interval, P_OBSERVER, self.heartbeat_sweep)
        self._lifecycle("RUN_STARTED")

    # ------------------------------------------------------------------ emission
    def emit(
        self,
        et: EventType,
        t_event: float,
        entity_type: EntityType,
        entity_id: str,
        device: str,
        floor: str | None = None,
        zone: str | None = None,
        payload: dict[str, Any] | None = None,
        corr: str | None = None,
        rng: PyRandom | None = None,
        source: Source | None = None,
    ) -> None:
        d, a = self.cfg.delivery, self.cfg.anomalies
        spec = EVENT_TYPE_SPECS[et]
        # Environment/heartbeats use their own stream so live (1-min) and batch (15-min)
        # environment intervals don't shift identity/occupancy draws.
        r = rng or self.obs_rng
        if spec.identity_class == "ANONYMOUS" and r.random() < a.missing_event_probability:
            return
        self.ev_seq += 1
        ingest = t_event + max(
            d.min_transport_delay_s, r.gauss(d.transport_delay_s.mean, d.transport_delay_s.sd)
        )
        if r.random() < a.late_event_probability:
            ingest += r.lognormvariate(math.log(d.late_delay_median_s), d.late_delay_sigma)
        identified = spec.identity_class == "IDENTIFIED"
        env = EventEnvelope(
            event_id=make_event_id(self.run_id, self.ev_seq),
            event_type=et,
            event_time=self.st.dt(t_event),
            ingest_time=self.st.dt(ingest),
            source=source or next(iter(spec.sources)),
            source_device_id=device,
            identity_class=spec.identity_class,
            entity_type=entity_type,
            entity_id=entity_id,
            building_id=self.bid,
            floor_id=floor,
            zone_id=zone,
            correlation_id=corr if identified else None,
            simulation_run_id=self.run_id,
            sequence_number=self.ev_seq,
            payload=payload or {},
        )
        self.schedule(ingest, P_DELIVER, self._deliver, env)
        if r.random() < a.duplicate_event_probability:
            self.schedule(
                ingest + r.uniform(0, d.duplicate_delay_max_s), P_DELIVER, self._deliver, env
            )

    def _deliver(self, env: EventEnvelope) -> None:
        self.counters[env.event_type] += 1
        self.sink(env)

    def _truth(self, p: Person, frm: PersonState, reason: str) -> None:
        if self.truth_sink is None:
            return
        self.counters["TRUTH"] += 1
        self.truth_sink(
            TruthTransition(
                event_time=self.st.dt(self.t),
                sim_t=self.t,
                person_id=p.id,
                team_id=p.team,
                department=p.dept,
                from_state=frm,
                to_state=p.state,
                location_type=p.loc_type,
                location_id=p.loc_id,
                floor_id=p.cur_floor,
                held_workspace_id=p.desk,
                reason=reason,
                meeting_id=p.in_meeting,
            )
        )

    def _lifecycle(self, what: str, **extra: Any) -> None:
        self.emit(
            EventType.SIMULATION_LIFECYCLE,
            self.t,
            EntityType.SIMULATION,
            str(self.run_id),
            "ENGINE",
            payload={"lifecycle": what, "mode": str(self.mode), "seed": self.cfg.seed, **extra},
        )

    # ------------------------------------------------------------------ day planning
    def day_start(self, d: int) -> None:
        day = self.st.day_date(d)
        t0 = d * SECONDS_PER_DAY
        cfg, cal, att = self.cfg, self.cfg.calendar, self.cfg.attendance
        rng = self.rngf.py_stream("plan", day)
        self.obs_rng = self.rngf.py_stream("observers", day)
        self.env_rng = self.rngf.py_stream("environment", day)
        self._lifecycle("DAY_STARTED", sim_date=day.isoformat())
        wd = day.isoweekday()
        off_day = wd in cal.weekend_days or day in cal.holidays
        people = list(self.persons.values())
        if off_day:
            attendees = [
                p
                for p in people
                if p.work_mode is WorkMode.OFFICE and rng.random() < cal.weekend_attendance
            ]
        else:
            team_mult = {}
            for tid, team in self.teams.items():
                m = rng.lognormvariate(0, att.team_correlation_sigma)
                team_mult[tid] = m * (att.team_office_day_boost if wd in team.office_days else 1.0)
            probs: list[tuple[Person, float]] = []
            for p in people:
                if rng.random() < att.leave_rate:
                    leave_type = weighted_choice(rng, cal.leave_type_weights)
                    self.leave_records.append(
                        LeaveRecord(f"LV-{day:%Y%m%d}-{p.id}", p.id, day, leave_type)
                    )
                    continue
                planned = self.patterns[(p.id, wd)]
                key = p.work_mode if p.work_mode is not WorkMode.HYBRID else f"HYBRID_{planned}"
                probs.append((p, att.base[key] * att.weekday_factor_iso(wd) * team_mult[p.team]))
            # Calibrate: expected attendance = average % x weekday factor (relative to the mean).
            wf = att.weekday_factor_iso(wd) / att.workday_mean_factor()
            target = att.average_daily_percentage / 100 * len(people) * wf
            cap, scale = att.max_probability, 1.0
            for _ in range(6):  # iterate because of the probability cap
                scale *= target / max(1e-9, sum(min(cap, pr * scale) for _, pr in probs))
            attendees = [p for p, pr in probs if rng.random() < min(cap, pr * scale)]

        s = cfg.simulation
        for p in attendees:
            prof = cfg.profiles[p.profile]
            p.rng = self.rngf.py_stream("person", p.id, day)
            arr = min(
                max(p.rng.gauss(prof.arrival, prof.arrival_sd_min / 60), s.earliest_arrival),
                s.latest_arrival,
            )
            workday = max(s.min_workday_h, p.rng.gauss(prof.workday_h, prof.workday_sd_min / 60))
            dep = min(arr + workday, s.latest_departure)
            p.depart_t, p.leaving, p.in_meeting, p.lunch_taken = t0 + dep * 3600, False, None, False
            p.no_login = p.rng.random() < cfg.workstation.no_login_probability
            p.tok += 1
            self.schedule(t0 + arr * 3600, P_PERSON, self.arrive, p.id, day)
            self.schedule(p.depart_t, P_PERSON, self.depart, p.id)
        self._plan_meetings(day, t0, attendees, rng)
        self.schedule(t0 + s.day_end_hour * 3600, P_PLAN, self.day_end, d)
        if self.days is None or d + 1 < self.days:
            self.schedule(t0 + SECONDS_PER_DAY, P_PLAN, self.day_start, d + 1)

    def _slot_weights(self) -> dict[float, float]:
        mc = self.cfg.meetings
        slots: dict[float, float] = {}
        h = mc.slot_first_hour
        while h <= mc.slot_last_hour + 1e-9:
            if mc.quiet_window.contains(h):
                w = mc.quiet_weight
            else:
                w = 1.0 + sum(mc.peak_boost for win in mc.peak_windows if win.contains(h))
            slots[round(h, 4)] = w
            h += mc.slot_step_h
        return slots

    def _plan_meetings(self, day: date, t0: float, attendees: list[Person], rng: PyRandom) -> None:
        mc = self.cfg.meetings
        if len(attendees) < 2:
            return
        by_team: dict[str, list[Person]] = defaultdict(list)
        by_dept: dict[str, list[Person]] = defaultdict(list)
        for p in attendees:
            by_team[p.team].append(p)
            by_dept[p.dept].append(p)
        left = {
            p.id: max(
                0,
                round(
                    rng.gauss(
                        mc.average_per_employee * self.cfg.profiles[p.profile].meeting_factor,
                        mc.per_employee_sd,
                    )
                ),
            )
            for p in attendees
        }
        slot_w = self._slot_weights()
        room_sched: dict[str, list[tuple[float, float]]] = defaultdict(list)
        bookable = sorted(
            (r for r in self.rooms.values() if r.is_bookable), key=lambda r: (r.capacity, r.room_id)
        )
        mseq, guard = 0, 0
        pool = list(attendees)
        s_team = mc.team_share
        s_partner = s_team + mc.partner_share
        s_dept = s_partner + mc.department_share
        while sum(left.values()) > 1 and guard < 20_000:
            guard += 1
            org = rng.choices(pool, weights=[left[p.id] + 0.01 for p in pool], k=1)[0]
            if left[org.id] <= 0:
                continue
            size = int(weighted_choice(rng, mc.size_weights))
            chosen = [org]
            partner_pool = [q for tid in self.partners.get(org.team, []) for q in by_team[tid]]
            for _ in range(size - 1):
                r = rng.random()
                if r < s_team:
                    src = by_team[org.team]
                elif r < s_partner:
                    src = partner_pool or by_team[org.team]
                elif r < s_dept:
                    src = by_dept[org.dept]
                else:
                    src = pool
                cand = [q for q in src if q not in chosen and left[q.id] > 0] or [
                    q for q in pool if q not in chosen and left[q.id] > 0
                ]
                if not cand:
                    break
                chosen.append(rng.choice(cand))
            dur = int(weighted_choice(rng, mc.duration_weights)) * 60
            start_h = weighted_choice(rng, slot_w)
            s_t, e_t = t0 + start_h * 3600, t0 + start_h * 3600 + dur
            home = self.floor_num[org.home_floor]
            room: Room | None = None
            for cand_room in sorted(
                bookable, key=lambda r: (abs(self.floor_num[r.floor_id] - home), r.capacity)
            ):
                free = all(e_t <= a or s_t >= b for a, b in room_sched[cand_room.room_id])
                if cand_room.capacity >= len(chosen) and free:
                    room = cand_room
                    break
            left[org.id] -= 1
            if room is None:
                continue
            for q in chosen[1:]:
                left[q.id] -= 1
            room_sched[room.room_id].append((s_t, e_t))
            mseq += 1
            mid = f"MTG-{day:%Y%m%d}-{mseq:04d}"
            ghost = rng.random() < mc.ghost_booking_probability
            a_start = s_t + max(0.0, rng.gauss(mc.late_start_s.mean, mc.late_start_s.sd))
            early = rng.random() < mc.early_end_probability
            a_end = e_t - (rng.uniform(mc.early_end_s.min, mc.early_end_s.max) if early else 0.0)
            a_end = max(a_end, a_start + mc.min_duration_s)
            participants = tuple(q.id for q in chosen)
            no_show = frozenset(q.id for q in chosen if rng.random() < mc.no_show_probability)
            booking_id = f"BKG-{day:%Y%m%d}-{mseq:04d}"
            self.meetings[mid] = Meeting(
                mid, booking_id, room.room_id, org.id, participants, no_show
            )
            self.bookings.append(
                RoomBooking(
                    booking_id,
                    room.room_id,
                    org.id,
                    participants,
                    self.st.dt(s_t),
                    self.st.dt(e_t),
                    mid,
                )
            )
            if not ghost:
                self.schedule(a_start, P_MEETING, self.meeting_start, mid, a_end)

    def day_end(self, d: int) -> None:
        for p in self.persons.values():
            if p.inside:
                p.tok += 1
                self.final_leave(p.id, p.tok)
        self.meetings.clear()  # every meeting of the day has ended by day_end_hour
        self._lifecycle("DAY_ENDED", sim_date=self.st.day_date(d).isoformat())

    # ------------------------------------------------------------------ ground truth movement
    def _where(
        self, loc_type: LocationType | None, loc_id: str | None
    ) -> tuple[str | None, str | None]:
        if loc_id is None or loc_type is None:
            return None, None
        if loc_type is LocationType.WORKSPACE:
            w = self.desks[loc_id]
            return w.floor_id, w.zone_id
        if loc_type in (LocationType.ROOM, LocationType.COMMON_AREA):
            r = self.rooms[loc_id]
            return r.floor_id, r.zone_id
        z = self.zones[loc_id]
        return z.floor_id, z.zone_id

    def move(
        self,
        p: Person,
        state: PersonState,
        loc_type: LocationType | None,
        loc_id: str | None,
        reason: str,
    ) -> None:
        frm = p.state
        if p.loc_type is LocationType.WORKSPACE and p.loc_id:
            self._desk_delta(p.loc_id, -1)
        elif p.loc_type in (LocationType.ROOM, LocationType.COMMON_AREA) and p.loc_id:
            self._room_delta(p.loc_id, -1)
        if p.zone:
            self.zone_truth[p.zone] -= 1
        floor, zone = self._where(loc_type, loc_id)
        if loc_type is not None:
            self._area_readers(p, floor, zone, loc_type, loc_id)
        p.state, p.loc_type, p.loc_id, p.cur_floor, p.zone = state, loc_type, loc_id, floor, zone
        if zone:
            self.zone_truth[zone] += 1
        if loc_type is LocationType.WORKSPACE and loc_id:
            self._desk_delta(loc_id, +1)
        elif loc_type in (LocationType.ROOM, LocationType.COMMON_AREA) and loc_id:
            self._room_delta(loc_id, +1)
        self._truth(p, frm, reason)

    def _area(self, subtype: AreaSubtype, floor_id: str) -> str:
        """Common area of `subtype` on this floor, else on the nearest floor that has one."""
        if subtype in self.common.get(floor_id, {}):
            return self.common[floor_id][subtype]
        here = self.floor_num[floor_id]
        options = sorted(
            (abs(self.floor_num[f] - here), f, areas[subtype])
            for f, areas in self.common.items()
            if subtype in areas
        )
        if options:
            return options[0][2]
        nearby = sorted(
            (abs(self.floor_num[f] - here), f, rid)
            for f, areas in self.common.items()
            for rid in areas.values()
        )
        return nearby[0][2]

    # ------------------------------------------------------------------ person handlers
    def arrive(self, pid: str, day: date) -> None:
        p = self.persons[pid]
        ac = self.cfg.access
        p.inside, p.visit = True, p.visit + 1
        p.corr = f"VISIT-{pid}-{day:%Y%m%d}-{p.visit}"
        if self.obs_rng.random() >= ac.tailgate_probability:
            delay = max(
                ac.min_delay_s, self.obs_rng.gauss(ac.entry_delay_s.mean, ac.entry_delay_s.sd)
            )
            self.emit(
                EventType.ACCESS_IN,
                self.t + delay,
                EntityType.EMPLOYEE,
                pid,
                self.entrance,
                self.ground,
                self.lobby[self.ground],
                {
                    "access_point_id": self.entrance,
                    "reader_type": ReaderType.BUILDING_ENTRANCE.value,
                    "credential_type": "EMPLOYEE_BADGE",
                    "direction": "IN",
                    "result": "GRANTED",
                },
                p.corr,
            )
        self.move(
            p, PersonState.ENTERING, LocationType.UNSENSED, self.lobby[self.ground], "ARRIVAL"
        )
        walk = self.cfg.timings.entry_to_desk_s
        self.schedule(
            self.t + p.rng.uniform(walk.min, walk.max), P_PERSON, self.go_desk, pid, p.tok
        )

    def go_desk(self, pid: str, tok: int) -> None:
        p = self.persons[pid]
        if tok != p.tok:
            return
        if p.leaving:
            self.start_leaving(p)
            return
        self.seat(p)

    def seat(self, p: Person) -> None:
        desk = p.desk or self.claim_desk(p)
        if desk is None:
            area = self._area(AreaSubtype.COLLABORATION, p.home_floor)
            if self.truth_sink is not None:
                self.truth_sink(
                    TruthDeskSearchFailed(self.st.dt(self.t), self.t, p.id, p.home_floor, area)
                )
            self.move(
                p, PersonState.COLLABORATION_AREA, LocationType.COMMON_AREA, area, "DESK_SHORTAGE"
            )
        else:
            self.move(p, PersonState.AT_DESK, LocationType.WORKSPACE, desk, "SEATED")
            if p.logged_in != desk and not p.no_login:
                self._login(p, desk)
        a = self.cfg.activities
        rate = (
            a.lunch_leave_rate_factor if a.lunch_window.contains(SimTime.hour_of(self.t)) else 1.0
        )
        block = lognormal_from_median_p90(p.rng, a.desk_block.median, a.desk_block.p90) / rate
        self.schedule(self.t + block * 60, P_PERSON, self.leave_desk, p.id, p.tok)

    def claim_desk(self, p: Person) -> str | None:
        desk: str | None
        if p.assigned_desk and p.assigned_desk not in self.claimed:
            desk = p.assigned_desk
        else:
            zones = [p.pref_zone, *self.team_zones[p.team]]
            zones += [z.zone_id for z in self.desk_zones if z.floor_id == p.home_floor]
            home = self.floor_num[p.home_floor]
            others = sorted(
                (z for z in self.desk_zones if z.floor_id != p.home_floor),
                key=lambda z: (abs(self.floor_num[z.floor_id] - home), z.zone_id),
            )
            zones += [z.zone_id for z in others]
            desk = None
            for zid in dict.fromkeys(zones):
                if self.zones[zid].is_restricted and p.team not in self.allowed[zid]:
                    continue
                pool = self.pool[zid]
                if pool:
                    fav = (
                        p.fav_desk in pool and p.rng.random() < self.cfg.activities.favourite_desk_p
                    )
                    desk = p.fav_desk if fav and p.fav_desk else p.rng.choice(pool)
                    pool.remove(desk)
                    break
            if desk is None:
                return None
        self.claimed[desk] = p.id
        p.desk = p.fav_desk = desk
        return desk

    def release_desk(self, p: Person) -> None:
        if p.desk:
            self.claimed.pop(p.desk, None)
            if p.desk != p.assigned_desk:
                self.pool[self.desks[p.desk].zone_id].append(p.desk)
            p.desk = None

    def leave_desk(self, pid: str, tok: int) -> None:
        p = self.persons[pid]
        a = self.cfg.activities
        if (
            tok != p.tok
            or p.leaving
            or self.t >= p.depart_t - self.cfg.timings.leave_before_departure_s
        ):
            return
        h = SimTime.hour_of(self.t)
        weights = dict(a.weights)
        lunch_time = a.lunch_window.contains(h)
        late_lunch = a.lunch_window.end <= h < a.late_lunch_until
        if not p.lunch_taken and (lunch_time or late_lunch):
            weights["CAFETERIA"] *= a.lunch_boost * (2 if late_lunch else 1)
        act = weighted_choice(p.rng, weights)
        state = PersonState(act)
        loc_type = LocationType.COMMON_AREA
        if act == "CAFETERIA":
            lunch = not p.lunch_taken and (lunch_time or h >= a.lunch_window.end)
            dwell_cfg = a.lunch if lunch else a.coffee
            p.lunch_taken = p.lunch_taken or lunch
            loc = self._area(AreaSubtype.CAFETERIA, self.ground)
            reason = "LUNCH" if lunch else "COFFEE"
        elif act == "BREAK":
            dwell_cfg, reason = a.break_, "BREAK"
            loc = self._area(AreaSubtype.LOUNGE, p.home_floor)
        elif act == "COLLABORATION_AREA":
            dwell_cfg, reason = a.collaboration, "COLLABORATION"
            loc = self._area(AreaSubtype.COLLABORATION, p.home_floor)
        else:
            dwell_cfg, reason, loc_type = a.other, "OTHER", LocationType.UNSENSED
            loc = self.lobby[p.cur_floor or p.home_floor]
        dwell = lognormal_from_median_p90(p.rng, dwell_cfg.median, dwell_cfg.p90)
        self.move(p, state, loc_type, loc, reason)
        self.schedule(self.t + dwell * 60, P_PERSON, self.return_desk, pid, p.tok)

    def return_desk(self, pid: str, tok: int) -> None:
        p = self.persons[pid]
        if tok != p.tok:
            return
        if p.leaving:
            self.start_leaving(p)
            return
        switch_p = self.cfg.profiles[p.profile].desk_switch_p
        if p.desk and p.rng.random() < switch_p:
            self._logout(p, "SWITCH", self.t)
            self.release_desk(p)
        self.seat(p)

    def meeting_start(self, mid: str, end_t: float) -> None:
        m = self.meetings[mid]
        attended = []
        for pid in m.participants:
            p = self.persons[pid]
            skip = pid in m.no_show or not p.inside or p.leaving or p.in_meeting
            if skip or p.state is PersonState.ENTERING:
                continue
            p.tok += 1
            p.in_meeting = mid
            self.move(p, PersonState.MEETING, LocationType.ROOM, m.room_id, "SCHEDULED_MEETING")
            attended.append(pid)
        room = self.rooms[m.room_id]
        mc = self.cfg.meetings
        if (
            m.organizer in attended
            and room.has_panel
            and self.obs_rng.random() < mc.room_check_in_probability
        ):
            o = self.persons[m.organizer]
            delay = self.obs_rng.uniform(mc.check_in_delay_s.min, mc.check_in_delay_s.max)
            self.emit(
                EventType.ROOM_CHECK_IN,
                self.t + delay,
                EntityType.EMPLOYEE,
                o.id,
                f"PANEL_{room.room_id}",
                room.floor_id,
                room.zone_id,
                {"room_id": room.room_id, "booking_id": m.booking_id, "meeting_id": mid},
                o.corr,
            )
        self.schedule(end_t, P_MEETING, self.meeting_end, mid)

    def meeting_end(self, mid: str) -> None:
        walk = self.cfg.timings.meeting_to_desk_s
        for pid in self.meetings[mid].participants:
            p = self.persons[pid]
            if p.in_meeting != mid:
                continue
            p.in_meeting = None
            p.tok += 1
            if p.leaving:
                self.start_leaving(p)
                continue
            lobby = self.lobby[p.cur_floor or p.home_floor]
            self.move(p, PersonState.OTHER_AREA, LocationType.UNSENSED, lobby, "MEETING_ENDED")
            self.schedule(
                self.t + p.rng.uniform(walk.min, walk.max), P_PERSON, self.go_desk, pid, p.tok
            )

    def depart(self, pid: str) -> None:
        p = self.persons[pid]
        if not p.inside:
            return
        p.leaving = True
        if p.in_meeting:
            return
        p.tok += 1
        self.start_leaving(p)

    def start_leaving(self, p: Person) -> None:
        pack = self.cfg.timings.pack_up_s
        if (
            p.state is not PersonState.AT_DESK
            and p.desk
            and p.rng.random() < self.cfg.activities.pack_up_return_p
        ):
            self.move(p, PersonState.AT_DESK, LocationType.WORKSPACE, p.desk, "PACK_UP")
            self.schedule(
                self.t + p.rng.uniform(pack.min, pack.max), P_PERSON, self.final_leave, p.id, p.tok
            )
        else:
            self.final_leave(p.id, p.tok)

    def final_leave(self, pid: str, tok: int) -> None:
        p = self.persons[pid]
        if tok != p.tok or not p.inside:
            return
        ws = self.cfg.workstation
        if p.logged_in:
            r = self.obs_rng
            if r.random() < ws.explicit_logout_probability:
                delay = max(
                    ws.min_logout_delay_s, r.gauss(ws.logout_delay_s.mean, ws.logout_delay_s.sd)
                )
                self._logout(p, "EXPLICIT", self.t + delay)
            else:
                sweep = SimTime.day_start(self.t) + ws.end_of_day_sweep * 3600
                t_to = min(self.t + ws.idle_timeout_minutes * 60, sweep)
                reason = "TIMEOUT" if t_to < sweep else "END_OF_DAY"
                self._logout(p, reason, max(t_to, self.t + 1))
        self.release_desk(p)
        self.move(
            p, PersonState.LEAVING, LocationType.UNSENSED, self.lobby[self.ground], "DEPARTURE"
        )
        walk = self.cfg.timings.exit_walk_s
        self.schedule(self.t + p.rng.uniform(walk.min, walk.max), P_PERSON, self.exit, pid, p.tok)

    def exit(self, pid: str, tok: int) -> None:
        p = self.persons[pid]
        if tok != p.tok:
            return
        self.move(p, PersonState.OUTSIDE_OFFICE, None, None, "EXIT")
        p.inside = False
        ac = self.cfg.access
        if self.obs_rng.random() >= ac.missed_badge_out_probability:
            delay = max(
                ac.min_delay_s, self.obs_rng.gauss(ac.exit_delay_s.mean, ac.exit_delay_s.sd)
            )
            self.emit(
                EventType.ACCESS_OUT,
                self.t + delay,
                EntityType.EMPLOYEE,
                pid,
                self.entrance,
                self.ground,
                self.lobby[self.ground],
                {
                    "access_point_id": self.entrance,
                    "reader_type": ReaderType.BUILDING_ENTRANCE.value,
                    "credential_type": "EMPLOYEE_BADGE",
                    "direction": "OUT",
                    "result": "GRANTED",
                },
                p.corr,
            )

    # ------------------------------------------------------------- observers: identity-aware
    def _area_readers(
        self,
        p: Person,
        floor: str | None,
        zone: str | None,
        loc_type: LocationType,
        loc_id: str | None,
    ) -> None:
        ac = self.cfg.access
        r = self.obs_rng
        hits: list[tuple[str, ReaderType, str, str]] = []
        if floor and floor != p.cur_floor and floor in self.ap_floor:
            hits.append((self.ap_floor[floor], ReaderType.FLOOR_LOBBY, "FLOOR", floor))
        if loc_type is LocationType.ROOM and loc_id in self.ap_room:
            hits.append((self.ap_room[loc_id], ReaderType.ROOM_DOOR, "ROOM", loc_id))
        if zone and zone != p.zone and zone in self.ap_zone:
            hits.append((self.ap_zone[zone], ReaderType.SECURE_ZONE, "ZONE", zone))
        for i, (ap, rtype, area_type, area_id) in enumerate(hits):
            # Secure zones cannot be entered without badging; other readers can be skipped.
            if rtype is not ReaderType.SECURE_ZONE and r.random() >= ac.internal_badge_compliance:
                continue
            t = (
                self.t
                + ac.min_delay_s
                + i * ac.area_reader_spacing_s
                + r.uniform(0, ac.area_reader_jitter_s)
            )
            self.emit(
                EventType.AREA_ACCESS,
                t,
                EntityType.EMPLOYEE,
                p.id,
                ap,
                floor,
                zone,
                {
                    "access_point_id": ap,
                    "reader_type": rtype.value,
                    "area_type": area_type,
                    "area_id": area_id,
                    "direction": "IN",
                    "result": "GRANTED",
                },
                p.corr,
            )

    def _login(self, p: Person, desk: str) -> None:
        ws = self.cfg.workstation
        t = self.t + max(
            ws.min_login_delay_s, self.obs_rng.gauss(ws.login_delay_s.mean, ws.login_delay_s.sd)
        )
        w = self.desks[desk]
        p.logged_in, p.login_iso = desk, self.st.iso(t)
        self.emit(
            EventType.WORKSPACE_LOGIN,
            t,
            EntityType.EMPLOYEE,
            p.id,
            desk,
            w.floor_id,
            w.zone_id,
            {
                "workspace_id": desk,
                "login_method": "BADGE_TAP",
                "device_type": w.device_type.value,
                "assignment_type": "ASSIGNED" if desk == p.assigned_desk else "HOT_DESK",
            },
            p.corr,
        )

    def _logout(self, p: Person, reason: str, t: float) -> None:
        if not p.logged_in:
            return
        w = self.desks[p.logged_in]
        self.emit(
            EventType.WORKSPACE_LOGOUT,
            t,
            EntityType.EMPLOYEE,
            p.id,
            p.logged_in,
            w.floor_id,
            w.zone_id,
            {
                "workspace_id": p.logged_in,
                "logout_reason": reason,
                "session_login_time": p.login_iso,
            },
            p.corr,
        )
        p.logged_in = None

    # ------------------------------------------------------------- observers: anonymous sensors
    def _desk_delta(self, desk: str, delta: int) -> None:
        self.desk_truth[desk] += delta
        if desk not in self.desk_sensor:
            return
        s = self.cfg.sensors
        self.desk_tok[desk] += 1
        if self.desk_truth[desk] > 0:
            det = s.desk_detection_delay_s
            dt, val = max(s.min_detection_delay_s, self.obs_rng.gauss(det.mean, det.sd)), 1
        else:
            dt, val = float(s.desk_vacancy_timeout_s), 0
        self.schedule(self.t + dt, P_OBSERVER, self._desk_report, desk, self.desk_tok[desk], val)

    def _desk_report(self, desk: str, tok: int, val: int) -> None:
        if tok != self.desk_tok[desk] or self.desk_rep[desk] == val:
            return
        prev, self.desk_rep[desk] = self.desk_rep[desk], val
        w = self.desks[desk]
        sid = self.desk_sensor[desk]
        self.emit(
            EventType.OCCUPANCY_CHANGED,
            self.t,
            EntityType.WORKSPACE,
            desk,
            sid,
            w.floor_id,
            w.zone_id,
            {
                "sensor_id": sid,
                "workspace_id": desk,
                "sensor_type": "DESK_OCCUPANCY",
                "occupancy_status": val,
                "previous_status": prev,
            },
        )

    def _room_delta(self, room: str, delta: int) -> None:
        self.room_truth[room] += delta
        if room in self.room_pending:
            return
        self.room_pending.add(room)
        s = self.cfg.sensors
        lag = max(
            s.min_room_lag_s, self.obs_rng.gauss(s.room_report_lag_s.mean, s.room_report_lag_s.sd)
        )
        self.schedule(self.t + lag, P_OBSERVER, self._room_report, room)

    def _room_report(self, room: str) -> None:
        self.room_pending.discard(room)
        s = self.cfg.sensors
        true = self.room_truth[room]
        rep = true
        if true > 0 and self.obs_rng.random() < s.room_count_noise_probability:
            rep = max(0, true + self.obs_rng.choice((-1, 1)))
        if rep == self.room_rep[room]:
            return
        prev, self.room_rep[room] = self.room_rep[room], rep
        r = self.rooms[room]
        sid = self.room_sensor[room]
        self.emit(
            EventType.ROOM_OCCUPANCY_CHANGED,
            self.t,
            EntityType.ROOM,
            room,
            sid,
            r.floor_id,
            r.zone_id,
            {
                "sensor_id": sid,
                "room_id": room,
                "room_type": r.room_type.value,
                "area_subtype": r.area_subtype.value if r.area_subtype else None,
                "capacity": r.capacity,
                "occupied": rep > 0,
                "occupancy_count": rep,
                "previous_count": prev,
                "count_confidence": s.count_confidence,
            },
        )

    def heartbeat_sweep(self) -> None:
        iv = self.heartbeat_interval
        for i, (desk, sid) in enumerate(self.desk_sensor.items()):
            w = self.desks[desk]
            self.emit(
                EventType.SENSOR_HEARTBEAT,
                self.t + (i * 7) % iv,
                EntityType.SENSOR,
                sid,
                sid,
                w.floor_id,
                w.zone_id,
                {
                    "sensor_id": sid,
                    "sensor_type": "DESK_OCCUPANCY",
                    "current_value": self.desk_rep[desk],
                },
                rng=self.env_rng,
                source=Source.DESK_SENSOR,
            )
        for i, (room, sid) in enumerate(self.room_sensor.items()):
            r = self.rooms[room]
            self.emit(
                EventType.SENSOR_HEARTBEAT,
                self.t + (i * 11) % iv,
                EntityType.SENSOR,
                sid,
                sid,
                r.floor_id,
                r.zone_id,
                {
                    "sensor_id": sid,
                    "sensor_type": "ROOM_COUNT",
                    "current_value": self.room_rep[room],
                },
                rng=self.env_rng,
                source=Source.ROOM_SENSOR,
            )
        self.schedule(self.t + iv, P_OBSERVER, self.heartbeat_sweep)

    # ------------------------------------------------------------- environment physics + BMS
    def env_tick(self) -> None:
        ec = self.cfg.environment
        dt_min = self.env_interval / 60
        h = SimTime.hour_of(self.t)
        rng = self.env_rng
        core = self.cfg.simulation.core_hours
        core_start = core.start.hour + core.start.minute / 60
        core_end = core.end.hour + core.end.minute / 60
        for zid, z in self.zones.items():
            e = self.env[zid]
            occ = max(0, self.zone_truth[zid])
            cap = max(ec.min_zone_capacity, z.max_occupancy)
            load = min(ec.max_load, occ / cap)
            out = ec.outdoor_amplitude_c * math.sin(2 * math.pi * (h - ec.outdoor_peak_hour) / 24)
            target = ec.setpoint_c[e.mode] + e.adj + ec.occupancy_heat_c * load + out
            k = math.exp(-ec.mean_reversion_per_min[e.mode] * dt_min)
            noise = rng.gauss(0, ec.temperature_noise_c * math.sqrt(dt_min))
            bounds = ec.temperature_bounds_c
            e.temp = min(bounds.max, max(bounds.min, target + (e.temp - target) * k + noise))
            vent = ec.ventilation_per_min["BOOST" if e.boost else e.mode]
            steady = ec.outdoor_co2_ppm + (ec.co2_per_load * load) / vent
            e.co2 = (
                steady
                + (e.co2 - steady) * math.exp(-vent * dt_min)
                + rng.gauss(0, ec.co2_noise_ppm)
            )
            hs = ec.humidity_base_pct + ec.humidity_per_load * load
            decay = math.exp(-ec.humidity_reversion_per_min * dt_min)
            e.hum = hs + (e.hum - hs) * decay + rng.gauss(0, ec.humidity_noise_pct)
            lit = occ > 0 or core_start <= h < core_end
            light_cfg = ec.light_on_lux if lit else ec.light_off_lux
            light = rng.gauss(light_cfg.mean, light_cfg.sd)
            noise_db = (
                ec.noise_base_dba
                + ec.noise_per_log_occupant * math.log1p(occ)
                + rng.gauss(0, ec.noise_sd_dba)
            )
            sid = self.env_sensor[zid]
            self.emit(
                EventType.ENVIRONMENT_READING,
                self.t,
                EntityType.ZONE,
                zid,
                sid,
                z.floor_id,
                zid,
                {
                    "sensor_id": sid,
                    "readings": [
                        {"metric_type": "TEMPERATURE", "value": round(e.temp, 1), "unit": "C"},
                        {"metric_type": "HUMIDITY", "value": round(e.hum, 1), "unit": "PCT"},
                        {"metric_type": "CO2", "value": round(e.co2), "unit": "PPM"},
                        {"metric_type": "LIGHT", "value": round(max(0.0, light)), "unit": "LUX"},
                        {"metric_type": "NOISE", "value": round(noise_db, 1), "unit": "DBA"},
                    ],
                },
                rng=rng,
            )
            self._bms(zid, z, e, cap)
        self.schedule(self.t + self.env_interval, P_ENV, self.env_tick)

    def _bms(self, zid: str, z: Zone, e: ZoneEnvironment, cap: int) -> None:
        """The BMS sees ONLY observed (reported) sensor values, never ground truth."""
        bc = self.cfg.bms
        obs = sum(self.desk_rep[d] for d in self.desks_by_zone[zid]) + sum(
            self.room_rep[r] for r in self.rooms_by_zone[zid]
        )
        pct = 100 * obs / cap
        cool = bc.cooldown_minutes * 60

        def act(rule: str, action: str, params: dict[str, Any], cond: str) -> None:
            if self.t - e.last.get(rule, -1e9) < cool:
                return
            e.last[rule] = self.t
            prev = {"mode": e.mode, "setpoint_adj": e.adj, "boost": e.boost}
            if action == "SET_HVAC_MODE":
                e.mode = params["mode"]
            elif action == "ADJUST_SETPOINT":
                e.adj = max(-bc.max_setpoint_drop_c, e.adj + params["delta_c"])
            elif action == "INCREASE_VENTILATION":
                e.boost = params["on"]
            self.emit(
                EventType.AUTOMATION_ACTION,
                self.t,
                EntityType.ZONE,
                zid,
                f"BMS_{self.bid}",
                z.floor_id,
                zid,
                {
                    "rule_id": rule,
                    "trigger": {
                        "condition": cond,
                        "observed_values": {
                            "observed_occupancy": obs,
                            "occupancy_pct": round(pct, 1),
                            "temperature": round(e.temp, 1),
                            "co2": round(e.co2),
                        },
                    },
                    "action": action,
                    "action_params": params,
                    "previous_state": prev,
                    "hvac_zone_id": zid,
                },
                rng=self.env_rng,
            )

        if obs == 0:
            e.empty_since = e.empty_since if e.empty_since is not None else self.t
            empty_for = self.t - e.empty_since
            if e.mode != "ECO" and empty_for >= bc.eco_after_empty_minutes * 60:
                act(
                    "HVAC_ECO_WHEN_EMPTY",
                    "SET_HVAC_MODE",
                    {"mode": "ECO"},
                    f"observed occupancy == 0 for {bc.eco_after_empty_minutes:g} min",
                )
                e.adj = 0.0
        else:
            e.empty_since = None
            if pct > bc.high_above_pct and e.mode != "HIGH":
                act(
                    "HVAC_HIGH_WHEN_BUSY",
                    "SET_HVAC_MODE",
                    {"mode": "HIGH"},
                    f"occupancy > {bc.high_above_pct:g}%",
                )
            elif e.mode == "ECO" or (e.mode == "HIGH" and pct < bc.high_exit_below_pct):
                act("HVAC_NORMAL", "SET_HVAC_MODE", {"mode": "NORMAL"}, "occupied, normal load")
            if e.temp > bc.hot_threshold_c and e.adj > -bc.max_setpoint_drop_c:
                act(
                    "COOLING_WHEN_HOT",
                    "ADJUST_SETPOINT",
                    {"delta_c": -bc.setpoint_step_c},
                    f"temperature > {bc.hot_threshold_c:g} and occupied",
                )
        if e.co2 > bc.co2_threshold_ppm and not e.boost:
            act(
                "VENTILATE_ON_CO2",
                "INCREASE_VENTILATION",
                {"on": True},
                f"co2 > {bc.co2_threshold_ppm:g}",
            )
        elif e.boost and e.co2 < bc.co2_threshold_ppm - bc.co2_recovery_margin_ppm:
            act("VENTILATION_NORMAL", "INCREASE_VENTILATION", {"on": False}, "co2 recovered")

    # ------------------------------------------------------------------ status
    def truth_summary(self) -> dict[str, int]:
        inside = [p for p in self.persons.values() if p.inside]
        return {
            "inside": len(inside),
            "at_desk": sum(1 for p in inside if p.state is PersonState.AT_DESK),
            "in_meeting": sum(1 for p in inside if p.state is PersonState.MEETING),
            "occupied_desks_truth": sum(1 for v in self.desk_truth.values() if v > 0),
            "claimed_desks": len(self.claimed),
        }
