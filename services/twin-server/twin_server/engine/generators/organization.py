"""Generate departments, teams, employees, work patterns and desk assignments."""

from __future__ import annotations

import dataclasses
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

from twin_server.engine.generators.apportion import apportion
from workplace_domain import ids
from workplace_domain.config import WorkplaceConfig
from workplace_domain.config.organization import WORKDAYS
from workplace_domain.enums import (
    AccessDirection,
    BehaviorProfile,
    DeskPolicy,
    EmploymentType,
    PlannedMode,
    ReaderType,
    WorkMode,
    WorkspaceType,
    ZoneType,
)
from workplace_domain.models import (
    AccessPoint,
    Department,
    Employee,
    EmployeeWorkPattern,
    Floor,
    Layout,
    Team,
    TeamZoneAllocation,
    WorkspaceAssignment,
    ZoneAccessRule,
)
from workplace_domain.rng import RngFactory

DESK_ZONE_TYPES = {ZoneType.OPEN_WORKSPACE, ZoneType.TEAM_NEIGHBORHOOD}


@dataclass(frozen=True)
class OrgData:
    departments: list[Department]
    teams: list[Team]
    team_zone_allocations: list[TeamZoneAllocation]
    zone_access_rules: list[ZoneAccessRule]
    employees: list[Employee]
    work_patterns: list[EmployeeWorkPattern]
    assignments: list[WorkspaceAssignment]


def _team_count(size: int, mean: int, lo: int, hi: int) -> int:
    n = max(1, round(size / mean))
    while n < size and size / n > hi:
        n += 1
    while n > 1 and size / n < lo:
        n -= 1
    return n


def _exact_mix[T](values: dict[T, float], total: int, rng: RngFactory, stream: str) -> list[T]:
    """Exactly apportioned values, shuffled: mixes match config to the nearest person."""
    counts = apportion(total, values)
    ordered = [v for v, c in counts.items() for _ in range(c)]
    order = rng.stream(stream).permutation(total)
    return [ordered[int(i)] for i in order]


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _allocate_teams(
    teams: list[Team], floors: list[Floor], layout: Layout, secure_teams: set[str]
) -> tuple[list[Team], list[TeamZoneAllocation]]:
    """Place teams on floors and desk zones proportionally to desk capacity (deterministic).

    Teams in `secure_teams` (restricted departments) are placed first and packed together on one
    floor; the zones they use are then closed to every other team, forming a compact secure area.
    """
    desk_zones = {z.zone_id: z for z in layout.zones if z.zone_type in DESK_ZONE_TYPES}
    zone_cap: dict[str, int] = defaultdict(int)
    for w in layout.workspaces:
        if w.workspace_type is WorkspaceType.DESK and w.zone_id in desk_zones:
            zone_cap[w.zone_id] += 1
    floor_cap: dict[str, int] = defaultdict(int)
    for zone_id, cap in zone_cap.items():
        floor_cap[desk_zones[zone_id].floor_id] += cap

    people = sum(t.size_target for t in teams)
    total_cap = sum(floor_cap.values())
    floor_left = {f.floor_id: floor_cap[f.floor_id] * people / total_cap for f in floors}
    zone_left = {z: cap * people / total_cap for z, cap in zone_cap.items()}

    placed: dict[str, Team] = {}
    allocations: list[TeamZoneAllocation] = []
    secure_zones: list[str] = []
    secure_floor: str | None = None
    order = sorted(teams, key=lambda t: (t.team_id not in secure_teams, -t.size_target, t.team_id))
    for team in order:
        is_secure = team.team_id in secure_teams
        if is_secure and secure_floor is not None and floor_left[secure_floor] >= team.size_target:
            floor_id = secure_floor
        else:
            floor_id = max(floor_left, key=lambda f: (floor_left[f], f))
        floor_left[floor_id] -= team.size_target
        on_floor = [z for z in zone_left if desk_zones[z].floor_id == floor_id]
        if is_secure:
            secure_floor = floor_id
            # Fill zones already secured before opening a new one.
            zones = sorted(
                on_floor,
                key=lambda z: (z not in secure_zones or zone_left[z] <= 0, -zone_left[z], z),
            )
        else:
            zones = sorted(
                [z for z in on_floor if z not in secure_zones] or on_floor,
                key=lambda z: (-zone_left[z], z),
            )
        first = zones[0]
        size = team.size_target
        if zone_left[first] >= size or len(zones) == 1 or zone_left[first] <= 0:
            shares = {first: 1.0}
        else:
            s1 = round(zone_left[first] / size, 4)
            shares = {first: s1, zones[1]: round(1.0 - s1, 4)}
        for zone_id, share in shares.items():
            zone_left[zone_id] -= share * size
            allocations.append(TeamZoneAllocation(team.team_id, zone_id, share))
            if is_secure and zone_id not in secure_zones:
                secure_zones.append(zone_id)
        placed[team.team_id] = Team(
            team.team_id, team.department_id, team.name, floor_id, team.office_days, size
        )
    ordered = [placed[t.team_id] for t in teams]
    allocations.sort(key=lambda a: (a.team_id, a.zone_id))
    return ordered, allocations


def _restrict_zones(
    teams: list[Team],
    allocations: list[TeamZoneAllocation],
    team_dept: dict[str, str],
    restricted_departments: list[str],
    layout: Layout,
) -> list[ZoneAccessRule]:
    """Secure every zone where restricted-department teams sit (kit: reference/refsim/master.py).

    Those teams are packed together by `_allocate_teams`, so the secure area is compact.
    Every team seated in a restricted zone gets an access rule, so nobody is locked out.
    """
    restricted: list[str] = []
    for a in sorted(allocations, key=lambda a: (a.zone_id, a.team_id)):
        if team_dept[a.team_id] in restricted_departments and a.zone_id not in restricted:
            restricted.append(a.zone_id)
    zones = {z.zone_id: z for z in layout.zones}
    for zone_id in restricted:
        zone = zones[zone_id]
        layout.access_points.append(
            AccessPoint(
                access_point_id=ids.secure_reader_id(zone_id),
                building_id=next(
                    f.building_id for f in layout.floors if f.floor_id == zone.floor_id
                ),
                floor_id=zone.floor_id,
                name=f"{zone.name} secure door",
                direction=AccessDirection.IN,
                x=round(zone.x + 0.5, 2),
                y=round(zone.y + zone.height / 2, 2),
                reader_type=ReaderType.SECURE_ZONE,
                target_id=zone_id,
            )
        )
    layout.zones[:] = [
        dataclasses.replace(z, is_restricted=True) if z.zone_id in restricted else z
        for z in layout.zones
    ]
    return sorted(
        {ZoneAccessRule(a.zone_id, a.team_id) for a in allocations if a.zone_id in restricted},
        key=lambda r: (r.zone_id, r.team_id),
    )


def _assign_desks(
    employees: list[Employee], floors: list[Floor], layout: Layout, leads: set[str]
) -> list[WorkspaceAssignment]:
    assignments: list[WorkspaceAssignment] = []
    for floor in floors:
        if floor.desk_policy is not DeskPolicy.ASSIGNED:
            continue
        free_cabins = [
            w.workspace_id
            for w in layout.workspaces
            if w.floor_id == floor.floor_id and w.workspace_type is WorkspaceType.CABIN
        ]
        free_desks: dict[str, list[str]] = defaultdict(list)
        for w in layout.workspaces:
            if w.floor_id == floor.floor_id and w.workspace_type is WorkspaceType.DESK:
                free_desks[w.zone_id].append(w.workspace_id)
        eligible = [
            e
            for e in employees
            if e.home_floor_id == floor.floor_id and e.work_mode is not WorkMode.REMOTE
        ]
        eligible.sort(key=lambda e: (e.employee_id not in leads, e.employee_id))
        for emp in eligible:
            workspace_id: str | None = None
            if emp.employee_id in leads and free_cabins:
                workspace_id = free_cabins.pop(0)
            elif free_desks.get(emp.preferred_zone_id):
                workspace_id = free_desks[emp.preferred_zone_id].pop(0)
            else:
                zone = next((z for z in sorted(free_desks) if free_desks[z]), None)
                if zone is not None:
                    workspace_id = free_desks[zone].pop(0)
            if workspace_id is not None:
                assignments.append(
                    WorkspaceAssignment(emp.employee_id, workspace_id, emp.hire_date, None)
                )
    return assignments


def generate_organization(config: WorkplaceConfig, layout: Layout, rng: RngFactory) -> OrgData:
    org = config.organization
    total = config.simulation.employees.count
    floors = sorted(layout.floors, key=lambda f: f.floor_id)

    departments = [Department(ids.department_id(d.code), d.name) for d in org.departments]
    dept_sizes = apportion(total, {d.code: d.share for d in org.departments})

    # Teams -------------------------------------------------------------------------------
    name_order = rng.stream("team_names").permutation(len(org.team_names))
    weekday_weights = [org.office_days.weekday_weights[d] for d in WORKDAYS]
    weekday_p = [w / sum(weekday_weights) for w in weekday_weights]
    teams: list[Team] = []
    team_dept: dict[str, str] = {}
    for dept in org.departments:
        size = dept_sizes[dept.code]
        ts = org.team_size
        n_teams = _team_count(size, ts.mean, ts.min, ts.max)
        weights = rng.stream("team_sizes", dept.code).uniform(0.8, 1.2, n_teams)
        sizes = apportion(size, {i: float(w) for i, w in enumerate(weights)})
        for i in range(n_teams):
            number = len(teams) + 1
            tid = ids.team_id(number)
            pool_index = int(name_order[(number - 1) % len(org.team_names)])
            cycle = (number - 1) // len(org.team_names)
            name = org.team_names[pool_index] + (f" {cycle + 1}" if cycle else "")
            trng = rng.stream("team", tid)
            k = int(trng.integers(org.office_days.count_min, org.office_days.count_max + 1))
            days = sorted(int(d) + 1 for d in trng.choice(5, size=k, replace=False, p=weekday_p))
            teams.append(Team(tid, ids.department_id(dept.code), name, "", tuple(days), sizes[i]))
            team_dept[tid] = dept.code
    secure_teams = {t for t, code in team_dept.items() if code in org.restricted_departments}
    teams, allocations = _allocate_teams(teams, floors, layout, secure_teams)
    access_rules = _restrict_zones(
        teams, allocations, team_dept, org.restricted_departments, layout
    )
    team_zones: dict[str, list[TeamZoneAllocation]] = defaultdict(list)
    for a in allocations:
        team_zones[a.team_id].append(a)

    # Employees ---------------------------------------------------------------------------
    emp_cfg = config.simulation.employees
    modes = _exact_mix(dict(emp_cfg.work_mode_mix), total, rng, "work_mode")
    profiles = _exact_mix(dict(emp_cfg.profile_mix), total, rng, "behavior_profile")
    employment = _exact_mix(dict(org.employment_type_mix), total, rng, "employment_type")
    dept_by_code = {d.code: d for d in org.departments}
    hire_span = (org.hire_date_range.end - org.hire_date_range.start).days

    employees: list[Employee] = []
    leads: set[str] = set()
    emails: dict[str, int] = defaultdict(int)
    for team in teams:
        dept = dept_by_code[team_dept[team.team_id]]
        lead_id: str | None = None
        zones = team_zones[team.team_id]
        for member in range(team.size_target):
            idx = len(employees)
            eid = ids.employee_id(idx + 1)
            erng = rng.stream("employee", eid)
            first = org.first_names[int(erng.integers(len(org.first_names)))]
            last = org.last_names[int(erng.integers(len(org.last_names)))]
            local = _ascii(f"{first}.{last}").lower().replace(" ", "")
            emails[local] += 1
            suffix = str(emails[local]) if emails[local] > 1 else ""
            role = (
                dept.lead_role if member == 0 else dept.roles[int(erng.integers(len(dept.roles)))]
            )
            zone_pick = int(erng.choice(len(zones), p=[z.share for z in zones]))
            employees.append(
                Employee(
                    employee_id=eid,
                    employee_name=f"{first} {last}",
                    email=f"{local}{suffix}@{org.email_domain}",
                    team_id=team.team_id,
                    department_id=team.department_id,
                    job_role=role,
                    manager_id=lead_id,
                    home_floor_id=team.home_floor_id,
                    preferred_zone_id=zones[zone_pick].zone_id,
                    employment_type=EmploymentType(employment[idx]),
                    work_mode=WorkMode(modes[idx]),
                    behavior_profile=BehaviorProfile(profiles[idx]),
                    active_flag=True,
                    hire_date=org.hire_date_range.start
                    + timedelta(days=int(erng.integers(hire_span + 1))),
                )
            )
            if member == 0:
                lead_id = eid
                leads.add(eid)

    # Weekly work patterns -----------------------------------------------------------------
    wp = org.work_pattern
    team_days = {t.team_id: set(t.office_days) for t in teams}
    patterns: list[EmployeeWorkPattern] = []
    for emp in employees:
        prng = rng.stream("work_pattern", emp.employee_id)
        draws = prng.random(5)
        for day in range(1, 8):
            if day > 5 or emp.work_mode is WorkMode.REMOTE:
                mode = PlannedMode.REMOTE
            elif emp.work_mode is WorkMode.OFFICE:
                mode = PlannedMode.OFFICE
            elif day in team_days[emp.team_id]:
                office = draws[day - 1] < wp.hybrid_office_on_team_day
                mode = PlannedMode.OFFICE if office else PlannedMode.FLEX
            else:
                remote = draws[day - 1] < wp.hybrid_remote_on_other_day
                mode = PlannedMode.REMOTE if remote else PlannedMode.FLEX
            patterns.append(EmployeeWorkPattern(emp.employee_id, day, mode))

    assignments = _assign_desks(employees, floors, layout, leads)
    return OrgData(departments, teams, allocations, access_rules, employees, patterns, assignments)
