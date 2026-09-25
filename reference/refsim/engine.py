"""Reference discrete-event simulation engine.

Ground truth (people and where they really are) → observers (what each device can know) → delivery → sink.
Same code for LIVE (scaled clock, driven by server.py) and BATCH (history, as fast as possible).

This is a reference implementation of docs/simulation-engine.md for porting into services/simulation-engine.
Intentionally dependency-light (stdlib + PyYAML).
"""
from __future__ import annotations

import heapq
import math
import uuid
from collections import defaultdict

from .common import (IDENTITY_CLASS, SOURCE, RngFactory, SimTime, lognormal_from_median_p90,
                     make_event_id, validate_envelope, weighted_choice)

# scheduler priorities at equal timestamps (lower first)
P_PLAN, P_MEETING, P_PERSON, P_OBSERVER, P_ENV, P_DELIVER = 1, 2, 3, 4, 5, 7


class Person:
    __slots__ = ("id", "e", "team", "dept", "home_floor", "pref_zone", "profile", "work_mode", "state",
                 "loc_type", "loc_id", "cur_floor", "zone", "desk", "fav_desk", "assigned_desk", "inside", "tok",
                 "depart_t", "leaving", "in_meeting", "lunch_taken", "logged_in", "login_iso", "no_login",
                 "visit", "corr", "rng")

    def __init__(self, e: dict):
        self.id, self.e = e["employee_id"], e
        self.team, self.dept = e["team_id"], e["department"]
        self.home_floor, self.pref_zone = e["home_floor_id"], e["preferred_zone_id"]
        self.profile, self.work_mode = e["behavior_profile"], e["work_mode"]
        self.state, self.loc_type, self.loc_id = "OUTSIDE_OFFICE", None, None
        self.cur_floor = self.zone = self.desk = self.fav_desk = self.assigned_desk = None
        self.inside, self.tok, self.depart_t, self.leaving = False, 0, 0.0, False
        self.in_meeting, self.lunch_taken, self.logged_in, self.login_iso = None, False, None, None
        self.no_login, self.visit, self.corr, self.rng = False, 0, None, None


class Engine:
    def __init__(self, cfg: dict, layout: dict, master: dict, start_date, sink, truth_sink=None,
                 mode: str = "BATCH", run_id: str | None = None):
        self.cfg, self.layout, self.master = cfg, layout, master
        self.mode = mode
        self.sink, self.truth_sink = sink, truth_sink
        self.run_id = run_id or str(uuid.uuid4())
        self.st = SimTime(start_date, cfg["timezone"])
        self.rngf = RngFactory(cfg["seed"])
        self.obs_rng = self.rngf.stream("observers", start_date)
        self.env_rng = self.rngf.stream("environment", start_date)
        self.t = 0.0
        self.heap: list = []
        self._hseq = 0
        self.ev_seq = 0
        self.counters: dict[str, int] = defaultdict(int)
        self._index()
        self.meetings: dict[str, dict] = {}
        self.saas = {"room_bookings": [], "leave_records": []}
        self.env_interval = cfg["sensors"]["environment_poll_interval_s"] if mode == "LIVE" \
            else cfg["batch"]["environment_poll_interval_s"]
        hb = cfg["sensors"]["heartbeat_interval_s"]
        self.heartbeat_interval = hb if (mode == "LIVE" or cfg["batch"]["emit_heartbeats"]) else 0

    # ------------------------------------------------------------------ indexes
    def _index(self):
        L = self.layout
        self.bid = L["building"]["building_id"]
        self.floors = {f["floor_id"]: f for f in L["floors"]}
        self.ground = L["floors"][0]["floor_id"]
        self.zones = {z["zone_id"]: z for z in L["zones"]}
        self.desks = {w["workspace_id"]: w for w in L["workspaces"]}
        self.rooms = {r["room_id"]: r for r in L["rooms"]}
        self.lobby = {z["floor_id"]: z["zone_id"] for z in L["zones"] if z["zone_type"] in ("CIRCULATION", "ENTRANCE")}
        self.common = defaultdict(dict)
        for r in L["rooms"]:
            if r["room_type"] == "COMMON_AREA":
                self.common[r["floor_id"]][r["area_subtype"]] = r["room_id"]
        self.ap_floor, self.ap_room, self.ap_zone = {}, {}, {}
        for ap in L["access_points"]:
            {"FLOOR_LOBBY": self.ap_floor, "ROOM_DOOR": self.ap_room, "SECURE_ZONE": self.ap_zone}.get(
                ap["reader_type"], {})[ap["target_id"]] = ap["access_point_id"]
        self.entrance = next(ap["access_point_id"] for ap in L["access_points"] if ap["reader_type"] == "BUILDING_ENTRANCE")
        self.desk_sensor = {s["target_id"]: s["sensor_id"] for s in L["sensors"] if s["sensor_type"] == "DESK_OCCUPANCY"}
        self.room_sensor = {s["target_id"]: s["sensor_id"] for s in L["sensors"] if s["sensor_type"] == "ROOM_COUNT"}
        self.env_sensor = {s["target_id"]: s["sensor_id"] for s in L["sensors"] if s["sensor_type"] == "ENVIRONMENT"}
        self.floor_num = {f["floor_id"]: f["floor_number"] for f in L["floors"]}

        self.persons = {e["employee_id"]: Person(e) for e in self.master["employees"]}
        self.teams = {t["team_id"]: t for t in self.master["teams"]}
        self.team_zones = defaultdict(list)
        for a in sorted(self.master["team_zone_allocation"], key=lambda a: -float(a["share"])):
            self.team_zones[a["team_id"]].append(a["zone_id"])
        assigned = {a["workspace_id"]: a["employee_id"] for a in self.master["workspace_assignment"]}
        for wid, eid in assigned.items():
            self.persons[eid].assigned_desk = wid
        # hot-desk pools per zone: ordered lists for determinism (never iterate sets)
        self.pool = defaultdict(list)
        for w in self.layout["workspaces"]:
            if w["status"] == "ACTIVE" and w["workspace_id"] not in assigned:
                self.pool[w["zone_id"]].append(w["workspace_id"])
        self.claimed: dict[str, str] = {}

        # ground truth occupancy
        self.desk_truth = defaultdict(int)
        self.room_truth = defaultdict(int)
        self.zone_truth = defaultdict(int)
        # observer (reported) state
        self.desk_rep = defaultdict(int)
        self.desk_tok = defaultdict(int)
        self.room_rep = defaultdict(int)
        self.room_pending: set = set()
        self.rooms_by_zone = defaultdict(list)
        for r in self.layout["rooms"]:
            self.rooms_by_zone[r["zone_id"]].append(r["room_id"])
        self.desks_by_zone = defaultdict(list)
        for w in self.layout["workspaces"]:
            if w["workspace_id"] in self.desk_sensor:
                self.desks_by_zone[w["zone_id"]].append(w["workspace_id"])
        # environment + BMS state
        self.env = {zid: {"temp": 24.0, "co2": 450.0, "hum": 50.0, "mode": "NORMAL", "adj": 0.0, "boost": False,
                          "empty_since": None, "last": {}} for zid in self.zones}

    # ------------------------------------------------------------------ scheduler
    def schedule(self, t: float, prio: int, fn, *args):
        self._hseq += 1
        heapq.heappush(self.heap, (t, prio, self._hseq, fn, args))

    def peek(self) -> float | None:
        return self.heap[0][0] if self.heap else None

    def step_until(self, t_end: float) -> int:
        n = 0
        while self.heap and self.heap[0][0] <= t_end:
            t, _, _, fn, args = heapq.heappop(self.heap)
            self.t = t
            fn(*args)
            n += 1
        self.t = max(self.t, t_end)
        return n

    def start(self, days: int | None = None):
        """days=None → open-ended (LIVE)."""
        self.days = days
        self.schedule(0.0, P_PLAN, self.day_start, 0)
        self.schedule(0.0, P_ENV, self.env_tick)
        if self.heartbeat_interval:
            self.schedule(self.heartbeat_interval, P_OBSERVER, self.heartbeat_sweep)
        self._lifecycle("RUN_STARTED")

    # ------------------------------------------------------------------ emission
    def emit(self, et: str, t_event: float, entity_type: str, entity_id: str, device: str,
             floor=None, zone=None, payload=None, corr=None, rng=None):
        d = self.cfg["delivery"]
        a = self.cfg["anomalies"]
        r = rng or self.obs_rng  # environment/heartbeats use their own stream so live (1-min) and batch
                                 # (15-min) env intervals don't shift identity/occupancy event draws
        if IDENTITY_CLASS[et] == "ANONYMOUS" and r.random() < a["missing_event_probability"]:
            return
        self.ev_seq += 1
        ingest = t_event + max(0.1, r.gauss(d["transport_delay_s"]["mean"], d["transport_delay_s"]["sd"]))
        if r.random() < a["late_event_probability"]:
            ingest += r.lognormvariate(math.log(600), 0.8)
        env = {
            "event_id": make_event_id(self.run_id, self.ev_seq), "event_type": et, "event_version": 1,
            "event_time": self.st.iso(t_event), "ingest_time": self.st.iso(ingest), "source": SOURCE[et],
            "source_device_id": device, "identity_class": IDENTITY_CLASS[et], "entity_type": entity_type,
            "entity_id": entity_id, "building_id": self.bid, "floor_id": floor, "zone_id": zone,
            "correlation_id": corr if IDENTITY_CLASS[et] == "IDENTIFIED" else None,
            "simulation_run_id": self.run_id, "sequence_number": self.ev_seq, "payload": payload or {},
        }
        validate_envelope(env)
        self.schedule(ingest, P_DELIVER, self._deliver, env)
        if r.random() < a["duplicate_event_probability"]:
            self.schedule(ingest + r.uniform(0, 120), P_DELIVER, self._deliver, env)

    def _deliver(self, env: dict):
        self.counters[env["event_type"]] += 1
        self.sink.write(env)

    def _truth(self, p: Person, frm: str, reason: str):
        if not self.truth_sink:
            return
        self.counters["TRUTH"] += 1
        self.truth_sink.write({
            "event_type": "TRUTH_STATE_TRANSITION", "event_time": self.st.iso(self.t), "sim_t": self.t,
            "simulation_run_id": self.run_id, "entity_id": p.id,
            "payload": {"person_id": p.id, "person_type": "EMPLOYEE", "team_id": p.team, "department": p.dept,
                        "from_state": frm, "to_state": p.state, "location_type": p.loc_type,
                        "location_id": p.loc_id, "floor_id": p.cur_floor, "held_workspace_id": p.desk,
                        "reason": reason, "meeting_id": p.in_meeting}})

    def _lifecycle(self, what: str, **extra):
        self.emit("SIMULATION_LIFECYCLE", self.t, "SYSTEM", self.bid, "ENGINE", payload={
            "lifecycle": what, "mode": self.mode, "seed": self.cfg["seed"], **extra})

    # ------------------------------------------------------------------ day planning
    def day_start(self, d: int):
        date = self.st.day_date(d)
        t0 = d * 86400.0
        cfg, cal, att = self.cfg, self.cfg["calendar"], self.cfg["attendance"]
        rng = self.rngf.stream("plan", date)
        self.obs_rng = self.rngf.stream("observers", date)
        self.env_rng = self.rngf.stream("environment", date)
        self._lifecycle("DAY_STARTED", sim_date=date.isoformat())
        wd = date.isoweekday()
        off_day = wd in cal["weekend_days"] or date.isoformat() in cal["holidays"]
        attendees = []
        people = list(self.persons.values())
        if off_day:
            attendees = [p for p in people if p.work_mode == "OFFICE" and rng.random() < cal["weekend_attendance"]]
        else:
            team_mult = {}
            for tid, t in self.teams.items():
                m = rng.lognormvariate(0, att["team_correlation_sigma"])
                team_mult[tid] = m * (att["team_office_day_boost"] if wd in t["office_days"] else 1.0)
            patterns = self._patterns()
            probs = []
            for p in people:
                if rng.random() < cal["leave_rate"]:
                    self.saas["leave_records"].append({
                        "leave_id": f"LV-{date:%Y%m%d}-{p.id}", "employee_id": p.id, "leave_date": date.isoformat(),
                        "leave_type": weighted_choice(rng, {"ANNUAL": 0.6, "SICK": 0.3, "OTHER": 0.1}),
                        "record_status": "ACTIVE", "updated_at": self.st.iso(t0), "simulation_run_id": self.run_id})
                    continue
                planned = patterns[(p.id, wd)]
                key = p.work_mode if p.work_mode != "HYBRID" else f"HYBRID_{planned}"
                probs.append((p, att["base"][key] * att["weekday_factor"][wd] * team_mult[p.team]))
            # calibrate: expected attendance = average % × weekday factor (relative to the Mon–Fri mean)
            wf = att["weekday_factor"]
            target = att["average_daily_percentage"] / 100 * len(people) * wf[wd] / (sum(wf.values()) / len(wf))
            scale = 1.0
            for _ in range(6):  # iterate because of the 0.98 cap
                scale *= target / max(1e-9, sum(min(0.98, pr * scale) for _, pr in probs))
            attendees = [p for p, pr in probs if rng.random() < min(0.98, pr * scale)]

        s = cfg["simulation"]
        for p in attendees:
            prof = cfg["profiles"][p.profile]
            p.rng = self.rngf.stream("person", p.id, date)
            arr = min(max(p.rng.gauss(prof["arrival"], prof["arrival_sd"] / 60), s["earliest_arrival"]), s["latest_arrival"])
            dep = min(arr + max(3.0, p.rng.gauss(prof["workday"], prof["workday_sd"] / 60)), s["latest_departure"])
            p.depart_t, p.leaving, p.in_meeting, p.lunch_taken = t0 + dep * 3600, False, None, False
            p.no_login = p.rng.random() < cfg["workstation"]["no_login_probability"]
            p.tok += 1
            self.schedule(t0 + arr * 3600, P_PERSON, self.arrive, p.id, date)
            self.schedule(p.depart_t, P_PERSON, self.depart, p.id)
        self._plan_meetings(date, t0, attendees, rng)
        self.schedule(t0 + 23.5 * 3600, P_PLAN, self.day_end, d)
        if self.days is None or d + 1 < self.days:
            self.schedule(t0 + 86400, P_PLAN, self.day_start, d + 1)

    def _patterns(self):
        if not hasattr(self, "_pat"):
            self._pat = {(r["employee_id"], int(r["iso_weekday"])): r["planned_mode"]
                         for r in self.master["employee_work_pattern"]}
        return self._pat

    def _plan_meetings(self, date, t0, attendees, rng):
        mc = self.cfg["meetings"]
        if len(attendees) < 2:
            return
        by_team, by_dept = defaultdict(list), defaultdict(list)
        for p in attendees:
            by_team[p.team].append(p)
            by_dept[p.dept].append(p)
        left = {p.id: max(0, round(rng.gauss(mc["average_per_employee"] * self.cfg["profiles"][p.profile]["meeting_factor"], 1.0)))
                for p in attendees}
        slots = [8.5 + 0.5 * i for i in range(19)]
        slot_w = [0.1 if 12.5 <= h < 13.5 else 1 + (1.5 if 10 <= h < 12 else 0) + (1.5 if 14 <= h < 16 else 0) for h in slots]
        room_sched = defaultdict(list)
        bookable = sorted([r for r in self.layout["rooms"] if r["is_bookable"]], key=lambda r: (r["capacity"], r["room_id"]))
        mseq, guard = 0, 0
        pool = list(attendees)
        while sum(left.values()) > 1 and guard < 20000:
            guard += 1
            org = rng.choices(pool, weights=[left[p.id] + 0.01 for p in pool], k=1)[0]
            if left[org.id] <= 0:
                continue
            size = int(weighted_choice(rng, mc["size_weights"]))
            chosen = [org]
            for _ in range(size - 1):
                r = rng.random()
                src = by_team[org.team] if r < mc["team_share"] else by_dept[org.dept] if r < mc["team_share"] + mc["department_share"] else pool
                cand = [p for p in src if p not in chosen and left[p.id] > 0] or [p for p in pool if p not in chosen and left[p.id] > 0]
                if not cand:
                    break
                chosen.append(rng.choice(cand))
            dur = int(weighted_choice(rng, mc["duration_weights"])) * 60
            start_h = weighted_choice(rng, dict(zip(slots, slot_w)))
            s_t, e_t = t0 + start_h * 3600, t0 + start_h * 3600 + dur
            room = None
            for r in sorted(bookable, key=lambda r: (abs(self.floor_num[r["floor_id"]] - self.floor_num[org.home_floor]), r["capacity"])):
                if r["capacity"] >= len(chosen) and all(e_t <= a or s_t >= b for a, b in room_sched[r["room_id"]]):
                    room = r
                    break
            left[org.id] -= 1
            if not room:
                continue
            for p in chosen[1:]:
                left[p.id] -= 1
            room_sched[room["room_id"]].append((s_t, e_t))
            mseq += 1
            mid = f"MTG-{date:%Y%m%d}-{mseq:04d}"
            ghost = rng.random() < mc["ghost_booking_probability"]
            a_start = s_t + max(0.0, rng.gauss(180, 120))
            a_end = e_t - (rng.uniform(300, 1200) if rng.random() < mc["early_end_probability"] else 0)
            a_end = max(a_end, a_start + 600)
            m = {"meeting_id": mid, "room_id": room["room_id"], "organizer": org.id, "ghost": ghost,
                 "participants": [p.id for p in chosen],
                 "no_show": {p.id for p in chosen if rng.random() < mc["no_show_probability"]},
                 "booking_id": f"BKG-{date:%Y%m%d}-{mseq:04d}"}
            self.meetings[mid] = m
            self.saas["room_bookings"].append({
                "booking_id": m["booking_id"], "room_id": room["room_id"], "organizer_employee_id": org.id,
                "attendee_employee_ids": m["participants"], "title": f"Meeting {mseq}",
                "start_time": self.st.iso(s_t), "end_time": self.st.iso(e_t), "expected_attendees": len(chosen),
                "meeting_id": mid, "status": "CONFIRMED", "record_status": "ACTIVE",
                "updated_at": self.st.iso(t0 + 6 * 3600), "simulation_run_id": self.run_id})
            if not ghost:
                self.schedule(a_start, P_MEETING, self.meeting_start, mid, a_end)

    def day_end(self, d: int):
        for p in self.persons.values():
            if p.inside:
                p.tok += 1
                self.final_leave(p.id, p.tok)
        self.meetings.clear()  # all meetings of the day have ended by 23:30
        self._lifecycle("DAY_ENDED", sim_date=self.st.day_date(d).isoformat())

    # ------------------------------------------------------------------ ground truth movement
    def _where(self, loc_type, loc_id, p):
        if loc_type == "DESK":
            w = self.desks[loc_id]
            return w["floor_id"], w["zone_id"]
        if loc_type in ("ROOM", "AREA"):
            r = self.rooms[loc_id]
            return r["floor_id"], r["zone_id"]
        if loc_type == "UNSENSED":
            z = self.zones[loc_id]
            return z["floor_id"], z["zone_id"]
        return None, None

    def move(self, p: Person, state: str, loc_type, loc_id, reason: str):
        frm = p.state
        if p.loc_type == "DESK":
            self._desk_delta(p.loc_id, -1)
        elif p.loc_type in ("ROOM", "AREA"):
            self._room_delta(p.loc_id, -1)
        if p.zone:
            self.zone_truth[p.zone] -= 1
        floor, zone = self._where(loc_type, loc_id, p)
        if loc_type is not None:
            self._area_readers(p, floor, zone, loc_type, loc_id)
        p.state, p.loc_type, p.loc_id, p.cur_floor, p.zone = state, loc_type, loc_id, floor, zone
        if zone:
            self.zone_truth[zone] += 1
        if loc_type == "DESK":
            self._desk_delta(loc_id, +1)
        elif loc_type in ("ROOM", "AREA"):
            self._room_delta(loc_id, +1)
        self._truth(p, frm, reason)

    # ------------------------------------------------------------------ person handlers
    def arrive(self, pid: str, date):
        p = self.persons[pid]
        p.inside, p.visit = True, p.visit + 1
        p.corr = f"VISIT-{pid}-{date:%Y%m%d}-{p.visit}"
        if self.obs_rng.random() >= self.cfg["access"]["tailgate_probability"]:
            self.emit("ACCESS_IN", self.t + max(2, self.obs_rng.gauss(10, 5)), "EMPLOYEE", pid, self.entrance,
                      self.ground, self.lobby[self.ground], {
                          "access_point_id": self.entrance, "reader_type": "BUILDING_ENTRANCE",
                          "credential_type": "EMPLOYEE_BADGE", "direction": "IN", "result": "GRANTED"}, p.corr)
        self.move(p, "ENTERING", "UNSENSED", self.lobby[self.ground], "ARRIVAL")
        self.schedule(self.t + p.rng.uniform(120, 480), P_PERSON, self.go_desk, pid, p.tok)

    def go_desk(self, pid: str, tok: int):
        p = self.persons[pid]
        if tok != p.tok:
            return
        if p.leaving:
            return self.start_leaving(p)
        self.seat(p)

    def seat(self, p: Person):
        desk = p.desk or self.claim_desk(p)
        if desk is None:
            area = self.common[p.home_floor].get("COLLABORATION") or next(iter(self.common[p.home_floor].values()))
            if self.truth_sink:
                self.truth_sink.write({"event_type": "TRUTH_DESK_SEARCH_FAILED", "event_time": self.st.iso(self.t),
                                       "sim_t": self.t, "simulation_run_id": self.run_id, "entity_id": p.id,
                                       "payload": {"person_id": p.id, "floor_id": p.home_floor,
                                                   "fallback": "OVERFLOW_AREA", "fallback_location_id": area}})
            self.move(p, "COLLABORATION_AREA", "AREA", area, "DESK_SHORTAGE")
        else:
            self.move(p, "AT_DESK", "DESK", desk, "SEATED")
            if p.logged_in != desk and not p.no_login:
                self._login(p, desk)
        a = self.cfg["activities"]
        h = SimTime.hour_of(self.t)
        rate = 1.5 if a["lunch_window"][0] <= h < a["lunch_window"][1] else 1.0
        block = lognormal_from_median_p90(p.rng, a["desk_block"]["median"], a["desk_block"]["p90"]) / rate
        self.schedule(self.t + block * 60, P_PERSON, self.leave_desk, p.id, p.tok)

    def claim_desk(self, p: Person):
        if p.assigned_desk and p.assigned_desk not in self.claimed:
            desk = p.assigned_desk
        else:
            zones = [p.pref_zone] + self.team_zones[p.team]
            zones += [z["zone_id"] for z in self.layout["zones"] if z["floor_id"] == p.home_floor and z["zone_type"] == "OPEN_WORKSPACE"]
            others = sorted((z for z in self.layout["zones"] if z["zone_type"] == "OPEN_WORKSPACE" and z["floor_id"] != p.home_floor),
                            key=lambda z: (abs(self.floor_num[z["floor_id"]] - self.floor_num[p.home_floor]), z["zone_id"]))
            zones += [z["zone_id"] for z in others]
            desk = None
            for zid in dict.fromkeys(zones):
                z = self.zones[zid]
                if z.get("is_restricted") and p.team not in z.get("allowed_team_ids", []):
                    continue
                pool = self.pool[zid]
                if pool:
                    desk = p.fav_desk if (p.fav_desk in pool and p.rng.random() < 0.6) else p.rng.choice(pool)
                    pool.remove(desk)
                    break
            if desk is None:
                return None
        self.claimed[desk] = p.id
        p.desk = p.fav_desk = desk
        return desk

    def release_desk(self, p: Person):
        if p.desk:
            self.claimed.pop(p.desk, None)
            if p.desk != p.assigned_desk:
                self.pool[self.desks[p.desk]["zone_id"]].append(p.desk)
            p.desk = None

    def leave_desk(self, pid: str, tok: int):
        p = self.persons[pid]
        if tok != p.tok or p.leaving or self.t >= p.depart_t - 300:
            return
        a = self.cfg["activities"]
        h = SimTime.hour_of(self.t)
        w = dict(a["weights"])
        lunch_time = a["lunch_window"][0] <= h < a["lunch_window"][1]
        if not p.lunch_taken and (lunch_time or 14 <= h < 15):
            w["CAFETERIA"] *= a["lunch_boost"] * (2 if h >= 14 else 1)
        act = weighted_choice(p.rng, w)
        if act == "CAFETERIA":
            key = "lunch" if (not p.lunch_taken and (lunch_time or h >= 14)) else "coffee"
            p.lunch_taken = p.lunch_taken or key == "lunch"
            loc_type, loc = "AREA", self.common[self.ground]["CAFETERIA"]
        elif act == "BREAK":
            key, loc_type = "break", "AREA"
            loc = self.common[p.home_floor].get("LOUNGE") or self.common[self.ground]["LOUNGE"]
        elif act == "COLLABORATION_AREA":
            key, loc_type = "collaboration", "AREA"
            loc = self.common[p.home_floor].get("COLLABORATION") or next(iter(self.common[p.home_floor].values()))
        else:
            key, loc_type, loc = "other", "UNSENSED", self.lobby[p.cur_floor or p.home_floor]
        dwell = lognormal_from_median_p90(p.rng, a[key]["median"], a[key]["p90"])
        self.move(p, act, loc_type, loc, key.upper())
        self.schedule(self.t + dwell * 60, P_PERSON, self.return_desk, pid, p.tok)

    def return_desk(self, pid: str, tok: int):
        p = self.persons[pid]
        if tok != p.tok:
            return
        if p.leaving:
            return self.start_leaving(p)
        if p.desk and p.rng.random() < self.cfg["profiles"][p.profile]["desk_switch_p"]:
            self._logout(p, "SWITCH", self.t)
            self.release_desk(p)
        self.seat(p)

    def meeting_start(self, mid: str, end_t: float):
        m = self.meetings[mid]
        attended = []
        for pid in m["participants"]:
            p = self.persons[pid]
            if pid in m["no_show"] or not p.inside or p.leaving or p.in_meeting or p.state == "ENTERING":
                continue
            p.tok += 1
            p.in_meeting = mid
            self.move(p, "MEETING", "ROOM", m["room_id"], "SCHEDULED_MEETING")
            attended.append(pid)
        room = self.rooms[m["room_id"]]
        if m["organizer"] in attended and room["has_panel"] and self.obs_rng.random() < self.cfg["meetings"]["room_check_in_probability"]:
            o = self.persons[m["organizer"]]
            self.emit("ROOM_CHECK_IN", self.t + self.obs_rng.uniform(30, 180), "EMPLOYEE", o.id,
                      f"PANEL_{room['room_id']}", room["floor_id"], room["zone_id"],
                      {"room_id": room["room_id"], "booking_id": m["booking_id"], "meeting_id": mid}, o.corr)
        self.schedule(end_t, P_MEETING, self.meeting_end, mid)

    def meeting_end(self, mid: str):
        for pid in self.meetings[mid]["participants"]:
            p = self.persons[pid]
            if p.in_meeting != mid:
                continue
            p.in_meeting = None
            p.tok += 1
            if p.leaving:
                self.start_leaving(p)
                continue
            self.move(p, "OTHER_AREA", "UNSENSED", self.lobby[p.cur_floor], "MEETING_ENDED")
            self.schedule(self.t + p.rng.uniform(60, 180), P_PERSON, self.go_desk, pid, p.tok)

    def depart(self, pid: str):
        p = self.persons[pid]
        if not p.inside:
            return
        p.leaving = True
        if p.in_meeting:
            return
        p.tok += 1
        self.start_leaving(p)

    def start_leaving(self, p: Person):
        if p.state != "AT_DESK" and p.desk and p.rng.random() < self.cfg["activities"]["pack_up_return_p"]:
            self.move(p, "AT_DESK", "DESK", p.desk, "PACK_UP")
            self.schedule(self.t + p.rng.uniform(120, 420), P_PERSON, self.final_leave, p.id, p.tok)
        else:
            self.final_leave(p.id, p.tok)

    def final_leave(self, pid: str, tok: int):
        p = self.persons[pid]
        if tok != p.tok or not p.inside:
            return
        ws = self.cfg["workstation"]
        if p.logged_in:
            r = self.obs_rng
            if r.random() < ws["explicit_logout_probability"]:
                self._logout(p, "EXPLICIT", self.t + max(3, r.gauss(20, 10)))
            else:
                day0 = self.t - (self.t % 86400)
                t_to = min(self.t + ws["idle_timeout_minutes"] * 60, day0 + ws["end_of_day_sweep"] * 3600)
                reason = "TIMEOUT" if t_to < day0 + ws["end_of_day_sweep"] * 3600 else "END_OF_DAY"
                self._logout(p, reason, max(t_to, self.t + 1))
        self.release_desk(p)
        self.move(p, "LEAVING", "UNSENSED", self.lobby[self.ground], "DEPARTURE")
        self.schedule(self.t + p.rng.uniform(60, 240), P_PERSON, self.exit, pid, p.tok)

    def exit(self, pid: str, tok: int):
        p = self.persons[pid]
        if tok != p.tok:
            return
        self.move(p, "OUTSIDE_OFFICE", None, None, "EXIT")
        p.inside = False
        if self.obs_rng.random() >= self.cfg["access"]["missed_badge_out_probability"]:
            self.emit("ACCESS_OUT", self.t + max(2, self.obs_rng.gauss(8, 4)), "EMPLOYEE", pid, self.entrance,
                      self.ground, self.lobby[self.ground], {
                          "access_point_id": self.entrance, "reader_type": "BUILDING_ENTRANCE",
                          "credential_type": "EMPLOYEE_BADGE", "direction": "OUT", "result": "GRANTED"}, p.corr)

    # ------------------------------------------------------------------ observers: identity-aware
    def _area_readers(self, p: Person, floor, zone, loc_type, loc_id):
        comply = self.cfg["access"]["internal_badge_compliance"]
        r = self.obs_rng
        hits = []
        if floor != p.cur_floor and floor in self.ap_floor:
            hits.append((self.ap_floor[floor], "FLOOR_LOBBY", "FLOOR", floor))
        if loc_type == "ROOM" and loc_id in self.ap_room:
            hits.append((self.ap_room[loc_id], "ROOM_DOOR", "ROOM", loc_id))
        if zone != p.zone and zone in self.ap_zone:
            hits.append((self.ap_zone[zone], "SECURE_ZONE", "ZONE", zone))
        for i, (ap, rtype, area_type, area_id) in enumerate(hits):
            if rtype != "SECURE_ZONE" and r.random() >= comply:
                continue
            self.emit("AREA_ACCESS", self.t + 2 + i * 20 + r.uniform(0, 5), "EMPLOYEE", p.id, ap, floor, zone, {
                "access_point_id": ap, "reader_type": rtype, "area_type": area_type, "area_id": area_id,
                "direction": "IN", "result": "GRANTED"}, p.corr)

    def _login(self, p: Person, desk: str):
        t = self.t + max(10, self.obs_rng.gauss(60, 30))
        w = self.desks[desk]
        p.logged_in, p.login_iso = desk, self.st.iso(t)
        self.emit("WORKSPACE_LOGIN", t, "EMPLOYEE", p.id, desk, w["floor_id"], w["zone_id"], {
            "workspace_id": desk, "login_method": "BADGE_TAP", "device_type": w["device_type"],
            "assignment_type": "ASSIGNED" if desk == p.assigned_desk else "HOT_DESK"}, p.corr)

    def _logout(self, p: Person, reason: str, t: float):
        if not p.logged_in:
            return
        w = self.desks[p.logged_in]
        self.emit("WORKSPACE_LOGOUT", t, "EMPLOYEE", p.id, p.logged_in, w["floor_id"], w["zone_id"], {
            "workspace_id": p.logged_in, "logout_reason": reason, "session_login_time": p.login_iso}, p.corr)
        p.logged_in = None

    # ------------------------------------------------------------------ observers: anonymous sensors
    def _desk_delta(self, desk: str, delta: int):
        self.desk_truth[desk] += delta
        if desk not in self.desk_sensor:
            return
        s = self.cfg["sensors"]
        self.desk_tok[desk] += 1
        if self.desk_truth[desk] > 0:
            dt = max(5, self.obs_rng.gauss(s["desk_detection_delay_s"]["mean"], s["desk_detection_delay_s"]["sd"]))
            val = 1
        else:
            dt, val = s["desk_vacancy_timeout_s"], 0
        self.schedule(self.t + dt, P_OBSERVER, self._desk_report, desk, self.desk_tok[desk], val)

    def _desk_report(self, desk: str, tok: int, val: int):
        if tok != self.desk_tok[desk] or self.desk_rep[desk] == val:
            return
        prev, self.desk_rep[desk] = self.desk_rep[desk], val
        w = self.desks[desk]
        self.emit("OCCUPANCY_CHANGED", self.t, "WORKSPACE", desk, self.desk_sensor[desk], w["floor_id"], w["zone_id"], {
            "sensor_id": self.desk_sensor[desk], "workspace_id": desk, "sensor_type": "DESK_OCCUPANCY",
            "occupancy_status": val, "previous_status": prev})

    def _room_delta(self, room: str, delta: int):
        self.room_truth[room] += delta
        if room in self.room_pending:
            return
        self.room_pending.add(room)
        lag = self.cfg["sensors"]["room_report_lag_s"]
        self.schedule(self.t + max(3, self.obs_rng.gauss(lag["mean"], lag["sd"])), P_OBSERVER, self._room_report, room)

    def _room_report(self, room: str):
        self.room_pending.discard(room)
        true = self.room_truth[room]
        rep = true
        if true > 0 and self.obs_rng.random() < self.cfg["sensors"]["room_count_noise_probability"]:
            rep = max(0, true + self.obs_rng.choice((-1, 1)))
        if rep == self.room_rep[room]:
            return
        prev, self.room_rep[room] = self.room_rep[room], rep
        r = self.rooms[room]
        self.emit("ROOM_OCCUPANCY_CHANGED", self.t, "ROOM", room, self.room_sensor[room], r["floor_id"], r["zone_id"], {
            "sensor_id": self.room_sensor[room], "room_id": room, "room_type": r["room_type"],
            "area_subtype": r["area_subtype"], "capacity": r["capacity"], "occupied": rep > 0,
            "occupancy_count": rep, "previous_count": prev, "count_confidence": 0.9})

    def heartbeat_sweep(self):
        iv = self.heartbeat_interval
        for i, (desk, sid) in enumerate(self.desk_sensor.items()):
            w = self.desks[desk]
            self.emit("SENSOR_HEARTBEAT", self.t + (i * 7) % iv, "SENSOR", sid, sid, w["floor_id"], w["zone_id"],
                      {"sensor_id": sid, "sensor_type": "DESK_OCCUPANCY", "current_value": self.desk_rep[desk]}, rng=self.env_rng)
        for i, (room, sid) in enumerate(self.room_sensor.items()):
            r = self.rooms[room]
            self.emit("SENSOR_HEARTBEAT", self.t + (i * 11) % iv, "SENSOR", sid, sid, r["floor_id"], r["zone_id"],
                      {"sensor_id": sid, "sensor_type": "ROOM_COUNT", "current_value": self.room_rep[room]}, rng=self.env_rng)
        self.schedule(self.t + iv, P_OBSERVER, self.heartbeat_sweep)

    # ------------------------------------------------------------------ environment physics + BMS
    def env_tick(self):
        ec, bc = self.cfg["environment"], self.cfg["bms"]
        dt_min = self.env_interval / 60
        h = SimTime.hour_of(self.t)
        rng = self.env_rng
        core = self.cfg["simulation"]["core_hours"]
        for zid, z in self.zones.items():
            e = self.env[zid]
            occ = max(0, self.zone_truth[zid])
            cap = max(10, z["capacity"])
            load = min(1.5, occ / cap)
            out = ec["outdoor_amplitude_c"] * math.sin(2 * math.pi * (h - 9) / 24)
            target = ec["setpoint_c"][e["mode"]] + e["adj"] + ec["occupancy_heat_c"] * load + out
            k = math.exp(-ec["mean_reversion_per_min"][e["mode"]] * dt_min)
            e["temp"] = min(32, max(16, target + (e["temp"] - target) * k + rng.gauss(0, 0.03 * math.sqrt(dt_min))))
            vent = ec["ventilation_per_min"]["BOOST" if e["boost"] else e["mode"]]
            ss = 420 + (24 * load) / vent
            e["co2"] = ss + (e["co2"] - ss) * math.exp(-vent * dt_min) + rng.gauss(0, 3)
            hs = 48 + 4 * load
            e["hum"] = hs + (e["hum"] - hs) * math.exp(-0.05 * dt_min) + rng.gauss(0, 0.2)
            light = rng.gauss(450, 15) if (occ > 0 or core["start"] <= h < core["end"]) else rng.gauss(5, 1)
            noise = 35 + 8 * math.log1p(occ) + rng.gauss(0, 1)
            sid = self.env_sensor[zid]
            self.emit("ENVIRONMENT_READING", self.t, "ZONE", zid, sid, z["floor_id"], zid, {"sensor_id": sid, "readings": [
                {"metric_type": "TEMPERATURE", "value": round(e["temp"], 1), "unit": "C"},
                {"metric_type": "HUMIDITY", "value": round(e["hum"], 1), "unit": "PCT"},
                {"metric_type": "CO2", "value": round(e["co2"]), "unit": "PPM"},
                {"metric_type": "LIGHT", "value": round(max(0, light)), "unit": "LUX"},
                {"metric_type": "NOISE", "value": round(noise, 1), "unit": "DBA"}]}, rng=rng)
            self._bms(zid, z, e, bc, cap)
        self.schedule(self.t + self.env_interval, P_ENV, self.env_tick)

    def _bms(self, zid, z, e, bc, cap):
        """BMS sees ONLY observed (reported) sensor values, never ground truth."""
        obs = sum(self.desk_rep[d] for d in self.desks_by_zone[zid]) + sum(self.room_rep[r] for r in self.rooms_by_zone[zid])
        pct = 100 * obs / cap
        cool = bc["cooldown_minutes"] * 60

        def act(rule, action, params, cond):
            if self.t - e["last"].get(rule, -1e9) < cool:
                return
            e["last"][rule] = self.t
            prev = {"mode": e["mode"], "setpoint_adj": e["adj"], "boost": e["boost"]}
            if action == "SET_HVAC_MODE":
                e["mode"] = params["mode"]
            elif action == "ADJUST_SETPOINT":
                e["adj"] = max(-2.0, e["adj"] + params["delta_c"])
            elif action == "INCREASE_VENTILATION":
                e["boost"] = params["on"]
            self.emit("AUTOMATION_ACTION", self.t, "ZONE", zid, f"BMS_{self.bid}", z["floor_id"], zid, {
                "rule_id": rule, "trigger": {"condition": cond, "observed_values": {
                    "observed_occupancy": obs, "occupancy_pct": round(pct, 1), "temperature": round(e["temp"], 1),
                    "co2": round(e["co2"])}}, "action": action, "action_params": params, "previous_state": prev,
                "hvac_zone_id": zid}, rng=self.env_rng)

        if obs == 0:
            e["empty_since"] = e["empty_since"] if e["empty_since"] is not None else self.t
            if e["mode"] != "ECO" and self.t - e["empty_since"] >= bc["eco_after_empty_minutes"] * 60:
                act("HVAC_ECO_WHEN_EMPTY", "SET_HVAC_MODE", {"mode": "ECO"}, f"observed occupancy == 0 for {bc['eco_after_empty_minutes']} min")
                e["adj"] = 0.0
        else:
            e["empty_since"] = None
            if pct > bc["high_above_pct"] and e["mode"] != "HIGH":
                act("HVAC_HIGH_WHEN_BUSY", "SET_HVAC_MODE", {"mode": "HIGH"}, f"occupancy > {bc['high_above_pct']}%")
            elif e["mode"] == "ECO" or (e["mode"] == "HIGH" and pct < bc["high_exit_below_pct"]):
                act("HVAC_NORMAL", "SET_HVAC_MODE", {"mode": "NORMAL"}, "occupied, normal load")
            if e["temp"] > bc["hot_threshold_c"] and e["adj"] > -2.0:
                act("COOLING_WHEN_HOT", "ADJUST_SETPOINT", {"delta_c": -1.0}, f"temperature > {bc['hot_threshold_c']} and occupied")
        if e["co2"] > bc["co2_threshold_ppm"] and not e["boost"]:
            act("VENTILATE_ON_CO2", "INCREASE_VENTILATION", {"on": True}, f"co2 > {bc['co2_threshold_ppm']}")
        elif e["boost"] and e["co2"] < bc["co2_threshold_ppm"] - 250:
            act("VENTILATION_NORMAL", "INCREASE_VENTILATION", {"on": False}, "co2 recovered")

    # ------------------------------------------------------------------ status
    def truth_summary(self) -> dict:
        inside = [p for p in self.persons.values() if p.inside]
        return {"inside": len(inside), "at_desk": sum(1 for p in inside if p.state == "AT_DESK"),
                "in_meeting": sum(1 for p in inside if p.state == "MEETING"),
                "occupied_desks_truth": sum(1 for v in self.desk_truth.values() if v > 0),
                "claimed_desks": len(self.claimed)}
