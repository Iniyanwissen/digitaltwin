"""Engine behaviour tests, ported from reference/tests/test_refsim.py, plus hybrid additions."""

import dataclasses
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path

import pytest

from twin_server.engine.generators import generate_master_data
from twin_server.engine.generators.layout_generator import generate_layout
from twin_server.engine.simulation import Engine, TruthTransition
from workplace_domain.config import WorkplaceConfig, load_layout_presets, load_workplace_config
from workplace_domain.enums import EventType, LocationType, PersonState, RunMode

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"
MONDAY = date(2026, 9, 28)


def small_config(base: WorkplaceConfig, seed: int | None = None) -> WorkplaceConfig:
    presets = load_layout_presets(CONFIG_DIR)
    layout = generate_layout(presets.presets["small"], presets)
    sim = base.simulation.model_copy(
        update={
            "employees": base.simulation.employees.model_copy(update={"count": 180}),
            "seed": base.simulation.seed if seed is None else seed,
            "meetings": base.simulation.meetings.model_copy(
                update={
                    "collaboration": base.simulation.meetings.collaboration.model_copy(
                        update={"pair_count": 3}
                    )
                }
            ),
        }
    )
    return dataclasses.replace(base, simulation=sim, layouts=(layout,))


def run(cfg: WorkplaceConfig, days: int = 1, mode: RunMode = RunMode.BATCH):
    master = generate_master_data(cfg)
    events, truth = [], []
    eng = Engine(cfg.simulation, master, MONDAY, events.append, truth.append, mode=mode)
    eng.start(days=days)
    eng.step_until(days * 86400 + 3600)
    return master, eng, events, truth


def content_hash(rows, exclude=("event_id", "simulation_run_id")) -> str:
    h = hashlib.sha256()
    for r in rows:
        if dataclasses.is_dataclass(r):
            data = {k: str(v) for k, v in dataclasses.asdict(r).items()}
        else:
            data = r.model_dump(mode="json", exclude=set(exclude))
        h.update(json.dumps(data, sort_keys=True).encode())
    return h.hexdigest()


def transitions(truth) -> list[TruthTransition]:
    return [t for t in truth if isinstance(t, TruthTransition)]


@pytest.fixture(scope="module")
def base() -> WorkplaceConfig:
    return load_workplace_config(CONFIG_DIR)


@pytest.fixture(scope="module")
def small_run(base):
    return run(small_config(base))


@pytest.fixture(scope="module")
def medium_run(base):
    return run(base)


# ------------------------------------------------------------------ ported reference tests


def test_truth_sequences_start_and_end_outside(small_run) -> None:
    *_, truth = small_run
    seq = defaultdict(list)
    for t in transitions(truth):
        seq[t.person_id].append(t)
    assert seq
    for pid, s in seq.items():
        assert s[0].from_state is PersonState.OUTSIDE_OFFICE, pid
        assert s[-1].to_state is PersonState.OUTSIDE_OFFICE, pid


def test_anonymous_events_never_carry_identity(small_run) -> None:
    master, _, events, _ = small_run
    ids = {e.employee_id for e in master.employees}
    anonymous = [e for e in events if e.identity_class == "ANONYMOUS"]
    assert anonymous
    for e in anonymous:
        assert e.entity_type not in ("EMPLOYEE", "VISITOR")
        assert e.correlation_id is None
        blob = json.dumps(e.payload)
        assert not any(i in blob for i in ids), e.event_type


def test_ground_truth_counts_never_negative(small_run) -> None:
    _, eng, _, _ = small_run
    assert min(eng.desk_truth.values(), default=0) >= 0
    assert min(eng.room_truth.values(), default=0) >= 0
    assert eng.truth_summary()["inside"] == 0


def test_logins_only_after_arrival(small_run) -> None:
    *_, events, truth = small_run
    arrived = {}
    for t in transitions(truth):
        if t.to_state is PersonState.ENTERING:
            arrived.setdefault(t.person_id, t.event_time)
    logins = [e for e in events if e.event_type is EventType.WORKSPACE_LOGIN]
    assert logins
    for e in logins:
        assert e.entity_id in arrived and e.event_time >= arrived[e.entity_id]


def test_same_seed_is_reproducible(base, small_run) -> None:
    *_, e1, t1 = small_run
    *_, e2, t2 = run(small_config(base))
    assert content_hash(e1) == content_hash(e2)
    assert content_hash(t1) == content_hash(t2)


def test_different_seed_differs(base, small_run) -> None:
    *_, e1, _ = small_run
    *_, e2, _ = run(small_config(base, seed=999))
    assert content_hash(e1) != content_hash(e2)


def test_weekday_attendance_is_calibrated(base, medium_run) -> None:
    *_, truth = medium_run
    arrivals = {t.person_id for t in transitions(truth) if t.to_state is PersonState.ENTERING}
    att = base.simulation.attendance
    expected = (
        att.average_daily_percentage / 100 * att.weekday_factor_iso(1) / att.workday_mean_factor()
    )
    actual = len(arrivals) / base.simulation.employees.count
    assert abs(actual - expected) < 0.06, (actual, expected)


def test_sensor_lags_truth_and_login_persists_during_meetings(medium_run) -> None:
    *_, events, truth = medium_run
    types = {e.event_type for e in events}
    assert {
        EventType.ACCESS_IN,
        EventType.WORKSPACE_LOGIN,
        EventType.OCCUPANCY_CHANGED,
        EventType.ROOM_OCCUPANCY_CHANGED,
        EventType.AREA_ACCESS,
        EventType.ROOM_CHECK_IN,
    } <= types
    held = [
        t for t in transitions(truth) if t.to_state is PersonState.MEETING and t.held_workspace_id
    ]
    assert held, "people should hold their desk while in meetings (logged in, sensor vacant)"


def test_live_and_batch_produce_the_same_world(base) -> None:
    """Only the clock, env interval and heartbeats differ; people and identity/occupancy match."""
    skip = {
        EventType.ENVIRONMENT_READING,
        EventType.AUTOMATION_ACTION,
        EventType.SENSOR_HEARTBEAT,
        EventType.SIMULATION_LIFECYCLE,
    }
    cfg = small_config(base)
    *_, eb, tb = run(cfg, mode=RunMode.BATCH)
    *_, el, tl = run(cfg, mode=RunMode.LIVE)
    strip = ("event_id", "simulation_run_id", "sequence_number")

    def keep(rows):
        return [r for r in rows if r.event_type not in skip]

    assert content_hash(tb) == content_hash(tl)
    assert content_hash(keep(eb), strip) == content_hash(keep(el), strip)


# ------------------------------------------------------------------ hybrid additions


def test_restricted_zones_only_hold_allowed_teams(medium_run) -> None:
    master, _, events, truth = medium_run
    allowed = defaultdict(set)
    for r in master.zone_access_rules:
        allowed[r.zone_id].add(r.team_id)
    team_of = {e.employee_id: e.team_id for e in master.employees}
    desks = {w.workspace_id: w.zone_id for w in master.layout.workspaces}
    for t in transitions(truth):
        if t.location_type is LocationType.WORKSPACE:
            zone = desks[t.location_id]
            if zone in allowed:
                assert team_of[t.person_id] in allowed[zone]
    secure = [
        e
        for e in events
        if e.event_type is EventType.AREA_ACCESS and e.payload["reader_type"] == "SECURE_ZONE"
    ]
    assert secure, "restricted zones should produce secure-reader passes"


def test_collaboration_pairs_meet_more_than_random_pairs(base, medium_run) -> None:
    master, eng, _, _ = medium_run
    pairs = eng.collaboration
    cfg = base.simulation.meetings.collaboration
    assert len(pairs) == cfg.pair_count
    teams_used = [t for p in pairs for t in (p.team_a, p.team_b)]
    assert len(teams_used) == len(set(teams_used)), "pairs are disjoint"
    assert sum(p.cross_floor for p in pairs) == round(cfg.pair_count * cfg.cross_floor_share)

    team_of = {e.employee_id: e.team_id for e in master.employees}
    shared = Counter()
    for b in eng.bookings:
        teams = sorted({team_of[a] for a in b.attendee_employee_ids})
        for x, y in combinations(teams, 2):
            shared[(x, y)] += 1
    hidden = {tuple(sorted((p.team_a, p.team_b))) for p in pairs}
    partner_avg = sum(shared[p] for p in hidden) / len(hidden)
    others = [
        k for k in combinations(sorted({t.team_id for t in master.teams}), 2) if k not in hidden
    ]
    other_avg = sum(shared[k] for k in others) / len(others)
    assert partner_avg > 5 * other_avg, (partner_avg, other_avg)
