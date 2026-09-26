"""Processor LiveState, TruthView and the live API/WebSocket."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from twin_server.engine.generators import generate_master_data
from twin_server.live.truth_view import TruthView
from twin_server.processor.live_state import LiveState
from workplace_domain.config import load_workplace_config
from workplace_domain.enums import EntityType, EventType, IdentityClass, Source
from workplace_domain.events import EventEnvelope, make_event_id

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN = uuid.UUID("11111111-2222-5333-8444-555555555555")
T0 = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def world():
    cfg = load_workplace_config(REPO_ROOT / "config")
    return cfg, generate_master_data(cfg)


@pytest.fixture
def state(world):
    cfg, master = world
    s = LiveState(master, cfg.simulation.processing)
    s.reset(RUN)
    return s


_seq = iter(range(1, 10_000_000))


def envelope(et, entity_type, entity_id, payload, t, source, identity, run=RUN, seq=None):
    seq = seq if seq is not None else next(_seq)
    return EventEnvelope(
        event_id=make_event_id(run, seq),
        event_type=et,
        event_time=t,
        ingest_time=t,
        source=source,
        source_device_id="dev",
        identity_class=identity,
        entity_type=entity_type,
        entity_id=entity_id,
        building_id="BLD01",
        simulation_run_id=run,
        sequence_number=seq,
        payload=payload,
    )


def login(emp, desk, t, et=EventType.WORKSPACE_LOGIN, **kw):
    payload = {"workspace_id": desk}
    if et is EventType.WORKSPACE_LOGOUT:
        payload["logout_reason"] = "EXPLICIT"
    return envelope(
        et, EntityType.EMPLOYEE, emp, payload, t, Source.WORKSTATION, IdentityClass.IDENTIFIED, **kw
    )


def sensor(desk, value, t, **kw):
    return envelope(
        EventType.OCCUPANCY_CHANGED,
        EntityType.WORKSPACE,
        desk,
        {
            "sensor_id": "S",
            "workspace_id": desk,
            "occupancy_status": value,
            "previous_status": 1 - value,
        },
        t,
        Source.DESK_SENSOR,
        IdentityClass.ANONYMOUS,
        **kw,
    )


def test_desk_identity_only_from_login(state, world) -> None:
    desk = world[1].layout.workspaces[0].workspace_id
    state.apply(sensor(desk, 1, T0))
    assert state.desk_detail(desk)["logged_in_employee"] is None
    assert state.desk_detail(desk)["sensor_status"] == "OCCUPIED"
    state.apply(login("EMP000001", desk, T0))
    assert state.desk_detail(desk)["logged_in_employee"] == "EMP000001"
    k = state.kpis()
    assert k["occupied_desks"] == 1 and k["held_desks"] == 0


def test_late_events_never_regress_state(state, world) -> None:
    desk = world[1].layout.workspaces[1].workspace_id
    state.apply(sensor(desk, 1, T0 + timedelta(minutes=10)))
    state.apply(sensor(desk, 0, T0))  # older event delivered late
    assert state.desk_sensor[desk] == 1


def test_duplicates_and_other_runs_are_ignored(state, world) -> None:
    desk = world[1].layout.workspaces[2].workspace_id
    ev = login("EMP000002", desk, T0, seq=424242)
    state.apply(ev)
    state.apply(ev)
    assert state.event_counts[EventType.WORKSPACE_LOGIN] == 1
    other = uuid.UUID("99999999-2222-5333-8444-555555555555")
    state.apply(login("EMP000003", world[1].layout.workspaces[3].workspace_id, T0, run=other))
    assert state.event_counts[EventType.WORKSPACE_LOGIN] == 1


def test_delta_frames_and_resync(state, world) -> None:
    desks = [w.workspace_id for w in world[1].layout.workspaces[:3]]
    v0 = state.version
    for d in desks:
        state.apply(sensor(d, 1, T0))
    delta = state.delta(v0)
    assert set(delta["desks"]) == set(desks)
    assert state.delta(state.version)["desks"] == {}
    state.reset(RUN)
    assert state.delta(v0) is None  # client older than the log -> resync


def test_truth_view_is_separate(world) -> None:
    from twin_server.engine.simulation import TruthTransition
    from workplace_domain.enums import LocationType, PersonState

    cfg, master = world
    truth = TruthView(master, cfg.simulation.processing)
    desk = master.layout.workspaces[0]
    truth.apply(
        TruthTransition(
            T0, 0.0, "EMP000001", "TEAM_001", "Engineering", PersonState.ENTERING,
            PersonState.AT_DESK, LocationType.WORKSPACE, desk.workspace_id, desk.floor_id,
            desk.workspace_id, "SEATED", None,
        )
    )  # fmt: skip
    assert truth.positions["EMP000001"][:2] == [desk.x, desk.y]
    state = LiveState(master, cfg.simulation.processing)
    assert "positions" not in state.snapshot()


# ------------------------------------------------------------------ API


def test_simulation_commands_and_layout(client) -> None:
    status = client.get("/api/v1/simulation/status").json()
    assert status["status"] == "STOPPED"
    assert (
        client.post("/api/v1/simulation/commands", json={"command": "START"}).json()["status"]
        == "RUNNING"
    )
    assert (
        client.post("/api/v1/simulation/commands", json={"command": "PAUSE"}).json()["status"]
        == "PAUSED"
    )
    bad = client.post("/api/v1/simulation/commands", json={"command": "SET_SPEED", "speed": 7})
    assert bad.status_code == 422
    ok = client.post("/api/v1/simulation/commands", json={"command": "SET_SPEED", "speed": 300})
    assert ok.json()["speed"] == 300
    client.post("/api/v1/simulation/commands", json={"command": "RESET"})

    layout = client.get("/api/v1/live/layout").json()
    assert len(layout["floors"]) == 4 and len(layout["workspaces"]) == 808
    assert layout["departments"]


def test_snapshot_hides_truth_unless_requested(client) -> None:
    assert "truth" not in client.get("/api/v1/live/snapshot").json()
    snap = client.get("/api/v1/live/snapshot", params={"truth": True}).json()
    assert "positions" in snap["truth"]
    pairs = client.get("/api/v1/simulation/truth/collaboration").json()
    assert pairs["truth"] is True and pairs["pairs"]


def test_live_websocket_sends_snapshot_then_frames(client) -> None:
    with client.websocket_connect("/ws/live") as ws:
        first = ws.receive_json()
        assert first["type"] == "snapshot" and "desks" in first and "truth" not in first
        second = ws.receive_json()
        assert second["type"] in ("frame", "snapshot")


def test_people_activity_comes_only_from_identified_events(state, world) -> None:
    desk = world[1].layout.workspaces[5].workspace_id
    v0 = state.version
    access = envelope(
        EventType.ACCESS_IN,
        EntityType.EMPLOYEE,
        "EMP000283",
        {"access_point_id": "AP_BLD01_ENT01", "direction": "IN"},
        T0,
        Source.ACCESS_CONTROL,
        IdentityClass.IDENTIFIED,
    )
    state.apply(access)
    state.apply(login("EMP000283", desk, T0 + timedelta(minutes=2)))
    state.apply(sensor(desk, 1, T0 + timedelta(minutes=3)))  # anonymous: no people activity
    texts = [a["text"] for _, a in state.activity]
    assert texts == [
        "entered the building",
        f"logged in at Desk F{int(desk.split('_')[2][1:])}-{desk.split('_')[3]}",
    ]
    assert all(a["code"] == "E283" for _, a in state.activity)
    status = state.person_status["EMP000283"]
    assert status["inside"] and "logged in at Desk" in status["text"]
    delta = state.delta(v0)
    assert delta is not None and "EMP000283" in delta["people"] and delta["activity"]


def test_truth_activity_is_readable(world) -> None:
    from twin_server.engine.simulation import TruthTransition
    from workplace_domain.enums import LocationType, PersonState

    cfg, master = world
    truth = TruthView(master, cfg.simulation.processing)
    cafe = next(r for r in master.layout.rooms if r.area_subtype == "CAFETERIA")
    truth.apply(
        TruthTransition(
            T0, 0.0, "EMP000007", "TEAM_001", "Engineering", PersonState.AT_DESK,
            PersonState.CAFETERIA, LocationType.COMMON_AREA, cafe.room_id, cafe.floor_id,
            None, "LUNCH", None,
        )
    )  # fmt: skip
    snap = truth.snapshot()
    assert snap["activity"][-1]["text"] == "went to the cafeteria (lunch)"
    assert snap["people"]["EMP000007"]["text"] == "Cafeteria (lunch)"
