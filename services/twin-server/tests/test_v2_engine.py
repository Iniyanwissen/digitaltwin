"""v2 environment, energy and ESG automation (v0.3 pack steps 4-5 acceptance checks)."""

import uuid
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from random import Random

import pytest

from twin_server.engine.simulation import TruthTransition
from twin_server.v2.engine import EngineV2
from twin_server.v2.environment import AreaEnv, step_physics
from twin_server.v2.live_state import LiveStateV2
from twin_server.v2.world import build_v2_world
from workplace_domain.config import load_workplace_config
from workplace_domain.config.v2 import load_v2_config
from workplace_domain.enums import EntityType, EventType, IdentityClass, PersonState, Source
from workplace_domain.events import EventEnvelope, make_event_id

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG = REPO_ROOT / "config"
MONDAY = date(2026, 9, 28)


@pytest.fixture(scope="module")
def setup():
    base = load_workplace_config(CONFIG)
    v2, plan = load_v2_config(CONFIG)
    return base, v2, build_v2_world(base, v2, plan)


def run_day(setup, v2=None, until_h=25.0):
    base, v2_default, world = setup
    events, truth = [], []
    eng = EngineV2(base.simulation, v2 or v2_default, world, MONDAY, events.append, truth.append)
    eng.start(days=1)
    eng.step_until(until_h * 3600)
    return eng, events, truth


@pytest.fixture(scope="module")
def day(setup):
    return run_day(setup)


def energy_totals(events):
    rows = [e.payload for e in events if e.event_type is EventType.ENERGY_INTERVAL]
    kwh = sum(r["kwh_hvac"] + r["kwh_lighting"] for r in rows)
    return rows, kwh, sum(r["kwh_baseline"] for r in rows)


# ------------------------------------------------------------------ physics


def test_crowded_room_heats_up_and_co2_rises(setup) -> None:
    _, v2, _ = setup
    cfg = v2.environment
    e = AreaEnv(temp=cfg.setpoint_c["NORMAL"], co2=450, mode="NORMAL")
    rng = Random(1)
    for _ in range(15):  # 125% load for 15 sim-minutes, automation disabled
        step_physics(e, 5, 4, 20.8, None, 11.0, 1.0, cfg, rng)
    assert e.temp >= cfg.setpoint_c["NORMAL"] + 1.0, e.temp
    assert e.co2 > 1000, e.co2


def test_empty_area_converges_to_setpoint_and_eco_drifts_up(setup) -> None:
    _, v2, _ = setup
    cfg = v2.environment
    e = AreaEnv(temp=cfg.setpoint_c["NORMAL"], co2=450, mode="ECO")
    rng = Random(2)
    temps = []
    for _ in range(240):
        step_physics(e, 0, 10, 50.0, None, 21.0, 1.0, cfg, rng)
        temps.append(e.temp)
    assert abs(temps[-1] - cfg.setpoint_c["ECO"]) < 0.3
    assert min(temps) >= cfg.setpoint_c["NORMAL"] - 0.2


# ------------------------------------------------------------------ energy


def test_energy_without_automation_matches_baseline(setup) -> None:
    _, v2, _ = setup
    off = v2.model_copy(update={"bms": v2.bms.model_copy(update={"enabled": False})})
    _, events, _ = run_day(setup, off)
    rows, kwh, baseline = energy_totals(events)
    assert rows and abs(kwh - baseline) <= 0.02 * baseline
    assert not [e for e in events if e.event_type is EventType.AUTOMATION_ACTION]


def test_energy_accounting_is_consistent(day) -> None:
    _, events, _ = day
    rows, kwh, baseline = energy_totals(events)
    for r in rows:
        assert r["kwh_hvac"] >= 0 and r["kwh_lighting"] >= 0 and r["kwh_baseline"] >= 0
        assert r["comfort_ok_minutes"] <= r["occupied_minutes"] + 1e-9
    saved_pct = 100 * (baseline - kwh) / baseline
    occupied = sum(r["occupied_minutes"] for r in rows)
    comfort = 100 * sum(r["comfort_ok_minutes"] for r in rows) / occupied
    assert 10 <= saved_pct <= 35, saved_pct
    assert comfort >= 90, comfort


# ------------------------------------------------------------------ automation


def test_demo_actions_by_1130_on_floor_2(day) -> None:
    _, events, _ = day
    rules = Counter(
        e.payload["rule_id"]
        for e in events
        if e.event_type is EventType.AUTOMATION_ACTION
        and e.floor_id == "BLD01_F02"
        and (e.event_time.hour, e.event_time.minute) <= (11, 30)
    )
    for rule in (
        "RELEASE_GHOST_BOOKING",
        "PRECOOL_FOR_BOOKING",
        "VENT_BOOST_ON_CO2",
        "DAYLIGHT_HARVEST",
        "HVAC_ECO_WHEN_EMPTY",
    ):
        assert rules[rule] >= 1, (rule, dict(rules))
    reasons = [e.payload["reason"] for e in events if e.event_type is EventType.AUTOMATION_ACTION]
    assert all(isinstance(r, str) and r for r in reasons)


def test_released_bookings_are_not_used(day) -> None:
    eng, _, truth = day
    released = set(eng.released)
    assert released
    meetings = {m.booking_id: m for m in eng.bookings}
    released_meetings = {meetings[b].meeting_id for b in released}
    used = {
        t.meeting_id
        for t in truth
        if isinstance(t, TruthTransition) and t.to_state is PersonState.MEETING
    }
    assert not released_meetings & used


def test_rules_read_sensors_not_ground_truth(setup) -> None:
    """Fake truth contradicting the sensors: rules follow the sensors."""
    base, v2, world = setup
    events = []
    eng = EngineV2(base.simulation, v2, world, MONDAY, events.append)
    room = next(a for a in eng.areas.values() if a.is_bookable and a.capacity == 4)
    room.env.light, room.env.mode = 100, "NORMAL"
    eng.t = 11 * 3600

    # Truth says the room is packed; sensors say empty -> no occupancy-driven action.
    eng.room_truth[room.area_id] = 10
    eng.room_rep[room.area_id] = 0
    for _ in range(20):
        eng.t += 60
        eng._rules(room, 11.0, True)
    eng.step_until(eng.t + 300)
    rules = {e.payload["rule_id"] for e in events if e.event_type is EventType.AUTOMATION_ACTION}
    assert "FLAG_OVER_CAPACITY" not in rules and "HVAC_NORMAL_ON_OCCUPANCY" not in rules

    # Truth says empty; sensors report 6 in 4 seats -> over-capacity flag.
    eng.room_truth[room.area_id] = 0
    eng.room_rep[room.area_id] = 6
    for _ in range(10):
        eng.t += 60
        eng._rules(room, 11.2, True)
    eng.step_until(eng.t + 300)
    rules = {e.payload["rule_id"] for e in events if e.event_type is EventType.AUTOMATION_ACTION}
    assert "FLAG_OVER_CAPACITY" in rules


# ------------------------------------------------------------------ processor state


def test_delta_15m_follows_recent_readings(setup) -> None:
    base, v2, world = setup
    state = LiveStateV2(world.master, base.simulation.processing, v2, world.env_areas)
    run = uuid.UUID("22222222-3333-5444-8555-666666666666")
    state.reset(run)
    area = next(a["area_id"] for a in world.env_areas if a["area_type"] == "ROOM")
    t0 = world.master.layout.buildings[0].timezone and __import__("datetime").datetime(
        2026, 9, 28, 10, 0, tzinfo=__import__("datetime").UTC
    )

    def reading(seq: int, minute: int, temp: float) -> EventEnvelope:
        t = t0 + timedelta(minutes=minute)
        return EventEnvelope(
            event_id=make_event_id(run, seq), event_type=EventType.ENVIRONMENT_READING,
            event_time=t, ingest_time=t, source=Source.ENV_SENSOR, source_device_id="S",
            identity_class=IdentityClass.ANONYMOUS, entity_type=EntityType.ROOM,
            entity_id=area, building_id="BLD01", simulation_run_id=run, sequence_number=seq,
            payload={
                "sensor_id": "S",
                "readings": [{"metric_type": "TEMPERATURE", "value": temp, "unit": "C"},
                             {"metric_type": "CO2", "value": 600, "unit": "PPM"}],
                "setpoint_c": 23.5, "hvac_mode": "NORMAL", "ventilation_boost": False,
                "light_level_pct": 100,
            },
        )  # fmt: skip

    for i in range(16):
        state.apply(reading(i + 1, i, 23.5 + 0.1 * i))
    assert state.areas[area][1] > 0  # rising -> positive delta
    for i in range(16):
        state.apply(reading(100 + i, 16 + i, 25.0 - 0.1 * i))
    assert state.areas[area][1] < 0  # falling -> negative delta


# ------------------------------------------------------------------ API


def test_v2_live_api_and_socket(client) -> None:
    status = client.get("/api/v2/simulation/status").json()
    assert status["status"] == "STOPPED"
    assert (
        client.post("/api/v2/simulation/commands", json={"command": "START"}).json()["status"]
        == "RUNNING"
    )
    client.post("/api/v2/simulation/commands", json={"command": "PAUSE"})
    snap = client.get("/api/v2/live/snapshot").json()
    assert {"areas", "esg", "floor_kpis", "chips", "actions"} <= set(snap)
    assert set(snap["floor_kpis"]) == {"BLD01_F01", "BLD01_F02", "BLD01_F03", "BLD01_F04"}
    detail = client.get("/api/v2/live/areas/ROOM_BLD01_F02_NOY").json()
    assert detail["name"] == "Noyyal" and "history" in detail
    with client.websocket_connect("/ws/live-v2") as ws:
        first = ws.receive_json()
        assert first["type"] == "snapshot" and "esg" in first
    # v1 keeps running independently
    assert client.get("/api/v1/simulation/status").json()["status"] in (
        "STOPPED",
        "RUNNING",
        "PAUSED",
    )
    client.post("/api/v2/simulation/commands", json={"command": "RESET"})
