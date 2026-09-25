"""Invariant, privacy, calibration and reproducibility tests for the reference simulator.

Run from reference/:  python -m pytest -q
These tests define behaviour the production engine must also satisfy (port them).
"""
import hashlib
import json
from collections import defaultdict
from datetime import date

from refsim.common import load_config
from refsim.engine import Engine
from refsim.layout import generate_layout
from refsim.master import generate_master

MONDAY = date(2026, 9, 28)


class ListSink:
    def __init__(self):
        self.rows = []

    def write(self, env):
        self.rows.append(env)


def run(preset="small", days=1, start=MONDAY, seed=None, mode="BATCH"):
    cfg = load_config(preset=preset)
    if seed is not None:
        cfg["seed"] = seed
    layout = generate_layout(cfg)
    master = generate_master(cfg, layout)
    ev, tr = ListSink(), ListSink()
    eng = Engine(cfg, layout, master, start, ev, tr, mode=mode)
    eng.start(days=days)
    eng.step_until(days * 86400 + 3600)
    return cfg, layout, master, eng, ev.rows, tr.rows


def content_hash(rows):
    h = hashlib.sha256()
    for r in rows:
        r = {k: v for k, v in r.items() if k not in ("event_id", "simulation_run_id")}
        h.update(json.dumps(r, sort_keys=True).encode())
    return h.hexdigest()


def test_master_data_is_deterministic():
    cfg = load_config(preset="medium")
    a = generate_master(cfg, generate_layout(cfg))
    b = generate_master(cfg, generate_layout(cfg))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert len(a["employees"]) == cfg["scale"]["employees"]


def test_truth_sequences_start_and_end_outside():
    *_, truth = run()
    seq = defaultdict(list)
    for t in truth:
        if t["event_type"] == "TRUTH_STATE_TRANSITION":
            seq[t["entity_id"]].append(t["payload"])
    assert seq
    for pid, s in seq.items():
        assert s[0]["from_state"] == "OUTSIDE_OFFICE", pid
        assert s[-1]["to_state"] == "OUTSIDE_OFFICE", pid


def test_anonymous_events_never_carry_identity():
    _, _, master, _, events, _ = run()
    ids = {e["employee_id"] for e in master["employees"]}
    for e in events:
        if e["identity_class"] == "ANONYMOUS":
            assert e["entity_type"] not in ("EMPLOYEE", "VISITOR")
            assert e["correlation_id"] is None
            blob = json.dumps(e["payload"])
            assert not any(i in blob for i in ids), e["event_type"]


def test_ground_truth_counts_never_negative():
    *_, eng, _, _ = run()
    assert min(eng.desk_truth.values(), default=0) >= 0
    assert min(eng.room_truth.values(), default=0) >= 0
    assert eng.truth_summary()["inside"] == 0


def test_logins_only_after_arrival():
    *_, events, truth = run()
    arrived = {}
    for t in truth:
        if t["event_type"] == "TRUTH_STATE_TRANSITION" and t["payload"]["to_state"] == "ENTERING":
            arrived.setdefault(t["entity_id"], t["event_time"])
    for e in events:
        if e["event_type"] == "WORKSPACE_LOGIN":
            assert e["entity_id"] in arrived and e["event_time"] >= arrived[e["entity_id"]]


def test_same_seed_is_reproducible():
    *_, e1, t1 = run()
    *_, e2, t2 = run()
    assert content_hash(e1) == content_hash(e2)
    assert content_hash(t1) == content_hash(t2)


def test_different_seed_differs():
    *_, e1, _ = run()
    *_, e2, _ = run(seed=999)
    assert content_hash(e1) != content_hash(e2)


def test_weekday_attendance_is_calibrated():
    cfg, *_, truth = run(preset="medium")
    arrivals = {t["entity_id"] for t in truth if t["payload"]["to_state"] == "ENTERING"}
    wf = cfg["attendance"]["weekday_factor"]
    expected = cfg["attendance"]["average_daily_percentage"] / 100 * wf[1] / (sum(wf.values()) / len(wf))
    actual = len(arrivals) / cfg["scale"]["employees"]
    assert abs(actual - expected) < 0.06, (actual, expected)


def test_sensor_lags_truth_and_login_persists_during_meetings():
    *_, events, truth = run(preset="medium")
    types = {e["event_type"] for e in events}
    assert {"ACCESS_IN", "WORKSPACE_LOGIN", "OCCUPANCY_CHANGED", "ROOM_OCCUPANCY_CHANGED", "AREA_ACCESS"} <= types
    meetings = [t for t in truth if t["payload"]["to_state"] == "MEETING" and t["payload"]["held_workspace_id"]]
    assert meetings, "people should hold their desk while in meetings (logged in, sensor vacant)"


def test_live_and_batch_produce_the_same_world():
    """Only the clock/sink and env interval differ between modes; people and identity/occupancy events must match."""
    skip = {"ENVIRONMENT_READING", "AUTOMATION_ACTION", "SENSOR_HEARTBEAT", "SIMULATION_LIFECYCLE"}
    *_, eb, tb = run(mode="BATCH")
    *_, el, tl = run(mode="LIVE")
    strip = lambda rows: [{k: v for k, v in r.items() if k not in ("sequence_number",)} for r in rows if r["event_type"] not in skip]
    assert content_hash(tb) == content_hash(tl)
    assert content_hash(strip(eb)) == content_hash(strip(el))
