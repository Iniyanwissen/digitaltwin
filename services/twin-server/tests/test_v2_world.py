"""Live Simulation v2 world: floor plan + overrides -> master data (v0.3 pack step 3)."""

from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from twin_server.engine.generators import generate_master_data
from twin_server.engine.simulation import TruthTransition
from twin_server.v2.engine import EngineV2
from twin_server.v2.world import build_v2_world
from workplace_domain.config import load_workplace_config
from workplace_domain.config.v2 import load_v2_config
from workplace_domain.enums import DeskPolicy, ReaderType, RoomType, SensorType

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG = REPO_ROOT / "config"


@pytest.fixture(scope="module")
def setup():
    base = load_workplace_config(CONFIG)
    v2, plan = load_v2_config(CONFIG)
    return base, v2, plan, build_v2_world(base, v2, plan)


def test_counts_match_the_floor_plan(setup) -> None:
    _, v2, plan, world = setup
    lay = world.master.layout
    floors = v2.layout.floors
    assert len(lay.floors) == floors
    per_floor = Counter(w.floor_id for w in lay.workspaces)
    assert set(per_floor.values()) == {len(plan.workspaces)}
    rooms = Counter(r.floor_id for r in lay.rooms if r.room_type is not RoomType.COMMON_AREA)
    assert set(rooms.values()) == {len(plan.rooms)}
    assert len(world.render["floors"]) == floors
    assert all(len(f["desks"]) == len(plan.workspaces) for f in world.render["floors"])


def test_floor_overrides(setup) -> None:
    *_, world = setup
    lay = world.master.layout
    f1 = {z.name for z in lay.zones if z.floor_id == "BLD01_F01"}
    assert "Reception" in f1 and "Team hub" not in f1
    entrance = [a for a in lay.access_points if a.reader_type is ReaderType.BUILDING_ENTRANCE]
    assert [a.floor_id for a in entrance] == ["BLD01_F01"]
    caf1 = next(r for r in lay.rooms if r.room_id == "AREA_BLD01_F01_CAF")
    assert caf1.capacity == 60
    restricted = [z.zone_id for z in lay.zones if z.is_restricted]
    assert restricted == ["BLD01_F03_ZD"]
    secure = [a.target_id for a in lay.access_points if a.reader_type is ReaderType.SECURE_ZONE]
    assert secure == ["BLD01_F03_ZD"]
    other_d = {z.name for z in lay.zones if z.zone_id.endswith("_ZD") and not z.is_restricted}
    assert other_d == {"Open workspace D"}
    policy = {f.floor_id: f.desk_policy for f in lay.floors}
    assert policy["BLD01_F04"] is DeskPolicy.ASSIGNED
    ws_floor = {w.workspace_id: w.floor_id for w in lay.workspaces}
    assert world.master.assignments
    assert {ws_floor[a.workspace_id] for a in world.master.assignments} == {"BLD01_F04"}


def test_finance_sits_in_the_secure_zone_only(setup) -> None:
    *_, world = setup
    m = world.master
    dept = {d.department_id: d.name for d in m.departments}
    finance = {t.team_id for t in m.teams if dept[t.department_id] == "Finance"}
    assert finance
    for a in m.team_zone_allocations:
        assert (a.zone_id == "BLD01_F03_ZD") == (a.team_id in finance)
    assert {r.team_id for r in m.zone_access_rules} == finance


def test_environment_areas_cover_zones_and_rooms(setup) -> None:
    *_, world = setup
    lay = world.master.layout
    areas = {a["area_id"] for a in world.env_areas}
    covered = {r.zone_id for r in lay.rooms if r.room_type is RoomType.COMMON_AREA}
    zones = {z.zone_id for z in lay.zones} - covered
    assert areas == zones | {r.room_id for r in lay.rooms}
    env = {s.target_id for s in lay.sensors if s.sensor_type is SensorType.ENVIRONMENT}
    assert env == areas


def test_v2_world_is_deterministic(setup) -> None:
    base, v2, plan, world = setup
    assert build_v2_world(base, v2, plan).master.content_hash() == world.master.content_hash()


def test_v1_master_data_is_unaffected(setup) -> None:
    base, *_ = setup
    v1 = generate_master_data(base)
    assert len(v1.layout.workspaces) == 808
    assert not any(r.room_type is RoomType.FOCUS_BOOTH for r in v1.layout.rooms)


def test_engine_runs_a_day_on_the_v2_building(setup) -> None:
    base, v2, _, world = setup
    truth: list = []
    eng = EngineV2(base.simulation, v2, world, date(2026, 9, 28), lambda e: None, truth.append)
    eng.start(days=1)
    eng.step_until(86400 + 3600)
    arrivals = {
        t.person_id for t in truth if isinstance(t, TruthTransition) and t.to_state == "ENTERING"
    }
    assert len(arrivals) > 0.4 * len(world.master.employees)
    assert eng.truth_summary()["inside"] == 0
    assert not [t for t in truth if not isinstance(t, TruthTransition)], "no desk shortages"


def test_v2_layout_api(client) -> None:
    layout = client.get("/api/v2/layout").json()
    assert [f["floor_number"] for f in layout["floors"]] == [1, 2, 3, 4]
    assert len(layout["floors"][1]["desks"]) == 136 and layout["floors"][1]["cores"]
    areas = client.get("/api/v2/areas").json()
    assert {a["area_type"] for a in areas} == {"ZONE", "ROOM"}
    assert client.get("/api/v1/live/layout").status_code == 200  # v1 untouched
