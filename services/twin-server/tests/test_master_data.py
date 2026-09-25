import dataclasses
import re
from collections import Counter, defaultdict
from pathlib import Path

import pytest
import yaml

from twin_server.db import create_db_engine, run_migrations
from twin_server.engine.generators import generate_master_data
from twin_server.engine.generators.layout_generator import generate_layout
from twin_server.layout_yaml import dump_layout
from twin_server.masterdata.service import MasterDataService
from workplace_domain.config import (
    LayoutFile,
    WorkplaceConfig,
    load_layout_presets,
    load_workplace_config,
)
from workplace_domain.enums import DeskPolicy, SensorType, WorkMode, WorkspaceType
from workplace_domain.models import MasterData

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"
# Employees per preset for the scale tests (roughly 1.25 people per desk).
PRESET_EMPLOYEES = {"small": 180, "medium": 1000, "large": 2700}


def with_changes(
    config: WorkplaceConfig, *, seed: int | None = None, employees: int | None = None,
    layout: LayoutFile | None = None, coverage: float | None = None,
) -> WorkplaceConfig:  # fmt: skip
    sim = config.simulation
    if seed is not None:
        sim = sim.model_copy(update={"seed": seed})
    if employees is not None:
        sim = sim.model_copy(
            update={"employees": sim.employees.model_copy(update={"count": employees})}
        )
    if coverage is not None:
        sim = sim.model_copy(
            update={"sensors": sim.sensors.model_copy(update={"desk_sensor_coverage": coverage})}
        )
    layouts = (layout,) if layout is not None else config.layouts
    return dataclasses.replace(
        config, simulation=sim, layouts=layouts, content_hash=f"{config.content_hash}-test"
    )


@pytest.fixture(scope="module")
def config() -> WorkplaceConfig:
    return load_workplace_config(CONFIG_DIR)


@pytest.fixture(scope="module")
def master(config: WorkplaceConfig) -> MasterData:
    return generate_master_data(config)


# ------------------------------------------------------------------ reproducibility


def test_same_seed_same_master_data(config: WorkplaceConfig, master: MasterData) -> None:
    assert generate_master_data(config).content_hash() == master.content_hash()


def test_different_seed_different_master_data(config: WorkplaceConfig, master: MasterData) -> None:
    other = generate_master_data(with_changes(config, seed=config.simulation.seed + 1))
    assert other.content_hash() != master.content_hash()


# ------------------------------------------------------------------ counts per preset


@pytest.mark.parametrize("preset_name", ["small", "medium", "large"])
def test_counts_match_config(config: WorkplaceConfig, preset_name: str) -> None:
    presets = load_layout_presets(CONFIG_DIR)
    preset = presets.presets[preset_name]
    layout_file = generate_layout(preset, presets)
    cfg = with_changes(config, employees=PRESET_EMPLOYEES[preset_name], layout=layout_file)
    data = generate_master_data(cfg)
    lay = data.layout

    desk_zones = preset.modules_per_row * 2 - 3
    desks = preset.floors * desk_zones * preset.desk_rows * preset.desk_cols
    cabins = len(preset.assigned_floors) * preset.cabins_per_block
    assert len(lay.floors) == preset.floors
    assert sum(w.workspace_type is WorkspaceType.DESK for w in lay.workspaces) == desks
    assert sum(w.workspace_type is WorkspaceType.CABIN for w in lay.workspaces) == cabins
    assert len(lay.zones) == preset.floors * (2 * preset.modules_per_row + 2)
    assert len(data.employees) == PRESET_EMPLOYEES[preset_name]
    assert len(lay.access_points) == preset.entrances
    expected_sensors = sum(w.has_sensor for w in lay.workspaces) + len(lay.rooms) + len(lay.zones)
    assert len(lay.sensors) == expected_sensors


def test_sensor_coverage(master: MasterData) -> None:
    lay = master.layout
    by_type = defaultdict(Counter)
    for s in lay.sensors:
        by_type[s.sensor_type][s.target_id] += 1
    sensed_desks = {w.workspace_id for w in lay.workspaces if w.has_sensor}
    assert set(by_type[SensorType.DESK_OCCUPANCY]) == sensed_desks
    assert set(by_type[SensorType.ROOM_COUNT]) == {r.room_id for r in lay.rooms}
    assert set(by_type[SensorType.ENVIRONMENT]) == {z.zone_id for z in lay.zones}
    assert all(n == 1 for counts in by_type.values() for n in counts.values())


def test_partial_sensor_coverage(config: WorkplaceConfig) -> None:
    data = generate_master_data(with_changes(config, coverage=0.5))
    workspaces = data.layout.workspaces
    assert sum(w.has_sensor for w in workspaces) == round(0.5 * len(workspaces))


# ------------------------------------------------------------------ mixes and teams


def test_work_mode_and_profile_mix_within_two_percent(
    config: WorkplaceConfig, master: MasterData
) -> None:
    n = len(master.employees)
    modes = Counter(e.work_mode for e in master.employees)
    profiles = Counter(e.behavior_profile for e in master.employees)
    for mode, share in config.simulation.employees.work_mode_mix.items():
        assert abs(modes[mode] / n - share) <= 0.02
    for profile, share in config.simulation.employees.profile_mix.items():
        assert abs(profiles[profile] / n - share) <= 0.02


def test_teams_have_home_floor_and_full_zone_allocation(master: MasterData) -> None:
    floors = {f.floor_id for f in master.layout.floors}
    zone_floor = {z.zone_id: z.floor_id for z in master.layout.zones}
    shares: dict[str, float] = defaultdict(float)
    for a in master.team_zone_allocations:
        shares[a.team_id] += a.share
    for team in master.teams:
        assert team.home_floor_id in floors
        assert shares[team.team_id] == pytest.approx(1.0, abs=1e-6)
        assert team.office_days and all(1 <= d <= 5 for d in team.office_days)
    for a in master.team_zone_allocations:
        team = next(t for t in master.teams if t.team_id == a.team_id)
        assert zone_floor[a.zone_id] == team.home_floor_id
    assert sum(t.size_target for t in master.teams) == len(master.employees)


def test_employee_integrity(master: MasterData) -> None:
    ids = {e.employee_id for e in master.employees}
    team_of = {e.employee_id: e.team_id for e in master.employees}
    assert len({e.email for e in master.employees}) == len(master.employees)
    for e in master.employees:
        assert re.fullmatch(r"EMP\d{6}", e.employee_id)
        if e.manager_id is not None:
            assert e.manager_id in ids and team_of[e.manager_id] == e.team_id
    leads = [e for e in master.employees if e.manager_id is None]
    assert len(leads) == len(master.teams)


def test_work_patterns(master: MasterData) -> None:
    assert len(master.work_patterns) == 7 * len(master.employees)
    mode_of = {e.employee_id: e.work_mode for e in master.employees}
    for p in master.work_patterns:
        if p.iso_weekday > 5 or mode_of[p.employee_id] is WorkMode.REMOTE:
            assert p.planned_mode == "REMOTE"
        elif mode_of[p.employee_id] is WorkMode.OFFICE:
            assert p.planned_mode == "OFFICE"


def test_assignments_only_on_assigned_floors(master: MasterData) -> None:
    policy = {f.floor_id: f.desk_policy for f in master.layout.floors}
    ws_floor = {w.workspace_id: w.floor_id for w in master.layout.workspaces}
    emp = {e.employee_id: e for e in master.employees}
    workspaces = [a.workspace_id for a in master.assignments]
    assert len(workspaces) == len(set(workspaces)) > 0
    for a in master.assignments:
        floor_id = ws_floor[a.workspace_id]
        assert policy[floor_id] is DeskPolicy.ASSIGNED
        assert emp[a.employee_id].home_floor_id == floor_id
        assert emp[a.employee_id].work_mode is not WorkMode.REMOTE


def test_id_formats(master: MasterData) -> None:
    lay = master.layout
    assert all(re.fullmatch(r"BLD\d{2}_F\d{2}", f.floor_id) for f in lay.floors)
    assert all(re.fullmatch(r"BLD\d{2}_F\d{2}_Z[A-Z0-9]+", z.zone_id) for z in lay.zones)
    assert all(
        re.fullmatch(r"(DESK_BLD\d{2}_F\d{2}_\d{3}|CABIN_BLD\d{2}_F\d{2}_\d{2})", w.workspace_id)
        for w in lay.workspaces
    )
    assert all(
        re.fullmatch(r"(ROOM_BLD\d{2}_F\d{2}_\d{2}|AREA_BLD\d{2}_F\d{2}_[A-Z]{3})", r.room_id)
        for r in lay.rooms
    )
    assert all(re.fullmatch(r"SEN_(DSK|RM|ENV)_\d{6}", s.sensor_id) for s in lay.sensors)


def test_generated_layout_yaml_round_trips() -> None:
    presets = load_layout_presets(CONFIG_DIR)
    layout = generate_layout(presets.presets["medium"], presets)
    assert LayoutFile.model_validate(yaml.safe_load(dump_layout(layout))) == layout


# ------------------------------------------------------------------ persistence


def test_store_seeds_once_and_detects_config_change(tmp_path, config: WorkplaceConfig) -> None:
    url = f"sqlite:///{(tmp_path / 'w.db').as_posix()}"
    run_migrations(url)
    engine = create_db_engine(url)
    try:
        service = MasterDataService(engine, config)
        first = service.ensure()
        assert first.generated and first.counts["employee"] == config.simulation.employees.count
        assert not service.ensure().generated
        assert service.store.counts()["employee"] == config.simulation.employees.count

        changed = MasterDataService(engine, with_changes(config, seed=7))
        assert not changed.is_current()
        assert changed.health().status == "degraded"
        assert changed.ensure().generated
        assert changed.is_current() and not service.is_current()
    finally:
        engine.dispose()
