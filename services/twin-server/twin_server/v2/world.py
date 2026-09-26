"""Live Simulation v2 world: master data built from the real floor plan (design/floor-plan-v2.json).

Separate from v1: nothing here is stored in the database or used by v1 pages. The shared
generators (organization, sensors, device types) are reused; v2 only supplies a different layout.

Per floor n the plan's ids (BLD01_F02...) are rewritten to BLD01_F0n and the floor overrides are
applied (floor 1 reception + entrance reader, floor 3 Finance restricted zone D, floor 4 assigned).
Café, lounge and team hub are zones with a capacity; each becomes a COMMON_AREA room filling its
zone (floor-twin-design-v2.md §3). The plan has no corridor, so one lift core per floor becomes a
walkable "Lift lobby" zone.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

from twin_server.engine.generators.layout_loader import _finalize_workspaces
from twin_server.engine.generators.organization import generate_organization
from workplace_domain import ids
from workplace_domain.config import WorkplaceConfig
from workplace_domain.config.v2 import FloorPlanFile, PlanZone, SimulationV2Config
from workplace_domain.enums import (
    AccessDirection,
    AreaSubtype,
    DeviceType,
    MetricType,
    ReaderType,
    RoomType,
    SensorTarget,
    SensorType,
    SpaceStatus,
    WorkspaceType,
    ZoneType,
)
from workplace_domain.ids import SensorKind
from workplace_domain.models import (
    AccessPoint,
    Building,
    Floor,
    Layout,
    MasterData,
    Organization,
    Room,
    Sensor,
    Workspace,
    Zone,
)
from workplace_domain.rng import RngFactory

COMMON_AREA_ZONES = {
    ZoneType.COLLABORATION: AreaSubtype.COLLABORATION,
    ZoneType.LOUNGE: AreaSubtype.LOUNGE,
    ZoneType.CAFETERIA: AreaSubtype.CAFETERIA,
}
ENV_METRICS = tuple(MetricType)
LOBBY_CODE = "LOB"


@dataclass
class V2World:
    """Master data for the engine plus render-only geometry for the v2 floor twin."""

    master: MasterData
    render: dict[str, Any]
    #: Environment areas = every zone + every room/common area (environment-and-esg.md §1).
    env_areas: list[dict[str, Any]] = field(default_factory=list)


def _floor_id(building_id: str, n: int) -> str:
    return ids.floor_id(building_id, n)


def build_v2_world(base: WorkplaceConfig, v2: SimulationV2Config, plan: FloorPlanFile) -> V2World:
    template = plan.floor.floor_id  # e.g. BLD01_F02
    building_id = template.split("_")[0]
    rng = RngFactory(base.simulation.seed)
    org = base.organization
    layout = Layout(organization=Organization(org_id=org.org_id, name=org.name))
    render_floors: list[dict[str, Any]] = []
    env_areas: list[dict[str, Any]] = []
    restricted_departments: list[str] = []
    zone_meta: dict[str, dict[str, Any]] = {}

    for n in range(1, v2.layout.floors + 1):
        fid = _floor_id(building_id, n)
        ov = v2.layout.floor_overrides.get(n)

        def rid(value: str, fid: str = fid) -> str:
            return value.replace(template, fid)

        desk_policy = (ov.desk_policy if ov and ov.desk_policy else None) or plan.floor.desk_policy
        if ov:
            names = {d.name: d.code for d in org.departments}
            restricted_departments += [names[d] for d in ov.restricted_departments if d in names]

        # ---- zones (+ common areas)
        zones: list[Zone] = []
        rooms: list[Room] = []
        render_zones: list[dict[str, Any]] = []
        for pz in plan.zones:
            name, ztype = pz.name, pz.zone_type
            replacement = ov.replace_zone.get(pz.code) if ov else None
            if replacement:
                name, ztype = replacement.name, replacement.zone_type
            restricted = bool(ov and pz.code in ov.restricted_zones)
            if pz.is_restricted and not restricted:
                name = f"Open workspace {pz.code}"
            capacity = (ov.capacity_overrides.get(pz.code) if ov else None) or pz.capacity
            zid = rid(pz.zone_id)
            zones.append(_zone(zid, fid, name, ztype, pz, capacity, restricted))
            zone_meta[zid] = {"facade": pz.facade, "capacity": capacity}
            render_zones.append(
                {
                    "zone_id": zid,
                    "code": pz.code,
                    "name": name,
                    "zone_type": ztype.value,
                    "x": pz.x,
                    "y": pz.y,
                    "w": pz.w,
                    "h": pz.h,
                    "facade": pz.facade,
                    "is_restricted": restricted,
                    "capacity": capacity,
                }
            )
            if ztype in COMMON_AREA_ZONES and capacity:
                rooms.append(
                    Room(
                        room_id=ids.area_id(building_id, n, pz.code),
                        floor_id=fid,
                        zone_id=zid,
                        name=name,
                        room_type=RoomType.COMMON_AREA,
                        area_subtype=COMMON_AREA_ZONES[ztype],
                        capacity=capacity,
                        x=pz.x,
                        y=pz.y,
                        width=pz.w,
                        height=pz.h,
                        is_bookable=False,
                        status=SpaceStatus.ACTIVE,
                        has_badge_reader=False,
                        has_panel=False,
                    )
                )
        core = plan.cores[v2.layout.lobby_core]
        lobby_id = ids.zone_id(fid, LOBBY_CODE)
        zones.append(
            Zone(
                zone_id=lobby_id,
                floor_id=fid,
                name="Lift lobby",
                zone_type=ZoneType.CIRCULATION,
                x=core.x,
                y=core.y,
                width=core.w,
                height=core.h,
                max_occupancy=0,
                area_sqm=round(core.w * core.h, 2),
                is_hvac_zone=True,
                is_restricted=False,
            )
        )
        zone_meta[lobby_id] = {"facade": None, "capacity": None}

        # ---- rooms
        for pr in plan.rooms:
            rooms.append(
                Room(
                    room_id=rid(pr.room_id),
                    floor_id=fid,
                    zone_id=rid(pr.zone_id),
                    name=pr.name,
                    room_type=RoomType(pr.room_type),
                    area_subtype=None,
                    capacity=pr.capacity,
                    x=pr.x,
                    y=pr.y,
                    width=pr.w,
                    height=pr.h,
                    is_bookable=pr.is_bookable,
                    status=SpaceStatus.ACTIVE,
                    has_badge_reader=pr.has_badge_reader,
                    has_panel=pr.has_panel,
                )
            )

        # ---- desks (engine positions are desk centres; render keeps the rectangle)
        workspaces = [
            Workspace(
                rid(w.workspace_id),
                fid,
                rid(w.zone_id),
                WorkspaceType.DESK,
                round(w.x + w.w / 2, 2),
                round(w.y + w.h / 2, 2),
                SpaceStatus.ACTIVE,
                has_sensor=False,
                device_type=DeviceType.DOCKING_STATION,  # set below
            )
            for w in plan.workspaces
        ]

        # ---- readers
        readers: list[AccessPoint] = []
        for ap in plan.access_points:
            if ap.reader_type == "SECURE_ZONE" and not any(
                z.is_restricted and z.zone_id == rid(ap.target_id) for z in zones
            ):
                continue  # zone D is only secure on the restricted floor
            readers.append(
                AccessPoint(
                    access_point_id=rid(ap.access_point_id),
                    building_id=building_id,
                    floor_id=fid,
                    name=_reader_name(ap.reader_type, ap.access_point_id),
                    direction=AccessDirection.IN,
                    x=ap.x,
                    y=ap.y,
                    reader_type=ReaderType(ap.reader_type),
                    target_id=rid(ap.target_id),
                )
            )
        if ov:
            for code, replacement in ov.replace_zone.items():
                if replacement.entrance_reader:
                    pz = next(z for z in plan.zones if z.code == code)
                    readers.append(
                        AccessPoint(
                            access_point_id=ids.access_point_id(building_id, "ENT01"),
                            building_id=building_id,
                            floor_id=fid,
                            name="Main entrance",
                            direction=AccessDirection.IN_OUT,
                            x=round(pz.x + pz.w / 2, 2),
                            y=pz.y,
                            reader_type=ReaderType.BUILDING_ENTRANCE,
                            target_id=building_id,
                        )
                    )

        seats = sum(r.capacity for r in rooms)
        layout.floors.append(
            Floor(
                floor_id=fid,
                building_id=building_id,
                floor_number=n,
                name=f"Floor {n}",
                max_occupancy=len(workspaces) + seats,
                desk_policy=desk_policy,
                plan_width=plan.floor.width,
                plan_height=plan.floor.height,
                is_available=True,
            )
        )
        layout.zones.extend(zones)
        layout.rooms.extend(rooms)
        layout.workspaces.extend(workspaces)
        layout.access_points.extend(readers)
        render_floors.append(
            {
                "floor_id": fid,
                "floor_number": n,
                "name": f"Floor {n}",
                "desk_policy": desk_policy.value,
                "width": plan.floor.width,
                "height": plan.floor.height,
                "glazing": list(plan.floor.glazing),
                "cores": [c.model_dump() for c in plan.cores],
                "zones": render_zones,
                "desks": [
                    {
                        "workspace_id": rid(w.workspace_id),
                        "zone_id": rid(w.zone_id),
                        "x": w.x,
                        "y": w.y,
                        "w": w.w,
                        "h": w.h,
                        "facing": w.facing,
                    }
                    for w in plan.workspaces
                ],
                "rooms": [
                    {
                        "room_id": r.room_id,
                        "name": r.name,
                        "room_type": r.room_type.value,
                        "area_subtype": r.area_subtype.value if r.area_subtype else None,
                        "x": r.x,
                        "y": r.y,
                        "w": r.width,
                        "h": r.height,
                        "capacity": r.capacity,
                        "zone_id": r.zone_id,
                        "has_badge_reader": r.has_badge_reader,
                        "has_panel": r.has_panel,
                        "is_bookable": r.is_bookable,
                    }
                    for r in rooms
                ],
                "readers": [
                    {
                        "access_point_id": a.access_point_id,
                        "reader_type": a.reader_type.value,
                        "x": a.x,
                        "y": a.y,
                        "target_id": a.target_id,
                    }
                    for a in readers
                ],
            }
        )

    layout.buildings.append(
        Building(
            building_id=building_id,
            org_id=org.org_id,
            name="Building A",
            timezone=base.simulation.timezone,
            max_occupancy=sum(f.max_occupancy for f in layout.floors),
            gross_area_sqm=round(plan.floor.width * plan.floor.height * v2.layout.floors, 2),
        )
    )

    # Shared generators: sensor coverage + device types, then sensors, then the organisation.
    cfg = _v2_workplace_config(base, v2, restricted_departments)
    _finalize_workspaces(layout, cfg, rng)
    _v2_sensors(layout, cfg)
    org_data = generate_organization(cfg, layout, rng)
    master = MasterData(
        layout=layout,
        departments=org_data.departments,
        teams=org_data.teams,
        team_zone_allocations=org_data.team_zone_allocations,
        zone_access_rules=org_data.zone_access_rules,
        employees=org_data.employees,
        work_patterns=org_data.work_patterns,
        assignments=org_data.assignments,
    )

    # Environment areas: every zone and every room/common area.
    for z in layout.zones:
        meta = zone_meta.get(z.zone_id, {})
        env_areas.append(
            {
                "area_id": z.zone_id,
                "area_type": "ZONE",
                "floor_id": z.floor_id,
                "name": z.name,
                "area_m2": z.area_sqm,
                "facade": meta.get("facade"),
                "capacity": meta.get("capacity"),
            }
        )
    for r in layout.rooms:
        env_areas.append(
            {
                "area_id": r.room_id,
                "area_type": "ROOM",
                "floor_id": r.floor_id,
                "name": r.name,
                "area_m2": round(r.width * r.height, 2),
                "facade": zone_meta.get(r.zone_id, {}).get("facade")
                if r.room_type is RoomType.COMMON_AREA
                else None,
                "capacity": r.capacity,
            }
        )

    render = {
        "building": {"building_id": building_id, "name": "Building A"},
        "floors": render_floors,
        "departments": [d.name for d in master.departments],
    }
    return V2World(master=master, render=render, env_areas=env_areas)


def _zone(
    zid: str,
    fid: str,
    name: str,
    ztype: ZoneType,
    pz: PlanZone,
    capacity: int | None,
    restricted: bool,
) -> Zone:
    return Zone(
        zone_id=zid,
        floor_id=fid,
        name=name,
        zone_type=ztype,
        x=pz.x,
        y=pz.y,
        width=pz.w,
        height=pz.h,
        max_occupancy=capacity or 0,
        area_sqm=round(pz.w * pz.h, 2),
        is_hvac_zone=True,
        is_restricted=restricted,
    )


def _reader_name(reader_type: str, access_point_id: str) -> str:
    return {
        "FLOOR_LOBBY": "Lift lobby reader",
        "ROOM_DOOR": "Boardroom door",
        "SECURE_ZONE": "Finance secure door",
    }.get(reader_type, access_point_id)


def _v2_workplace_config(
    base: WorkplaceConfig, v2: SimulationV2Config, restricted_departments: list[str]
) -> WorkplaceConfig:
    sim = base.simulation
    sim = sim.model_copy(
        update={"employees": sim.employees.model_copy(update={"count": v2.employees.count})}
    )
    org = base.organization.model_copy(
        update={"restricted_departments": sorted(set(restricted_departments))}
    )
    return dataclasses.replace(base, simulation=sim, organization=org, layouts=())


def _v2_sensors(layout: Layout, cfg: WorkplaceConfig) -> None:
    """Desk + room count sensors as in v1; an ENVIRONMENT sensor per zone AND per room."""
    s = cfg.simulation.sensors
    installed = s.installed_at

    def add(
        kind: SensorKind,
        n: int,
        stype: SensorType,
        target: SensorTarget,
        tid: str,
        floor: str,
        zone: str,
        metrics: tuple[MetricType, ...],
        poll: int,
    ) -> None:
        layout.sensors.append(
            Sensor(
                ids.sensor_id(kind, n),
                stype,
                target,
                tid,
                floor,
                zone,
                metrics,
                poll,
                installed,
                is_active=True,
            )
        )

    for n, w in enumerate((w for w in layout.workspaces if w.has_sensor), start=1):
        add(
            "DSK",
            n,
            SensorType.DESK_OCCUPANCY,
            SensorTarget.WORKSPACE,
            w.workspace_id,
            w.floor_id,
            w.zone_id,
            (),
            s.desk_poll_interval,
        )
    for n, r in enumerate(layout.rooms, start=1):
        add(
            "RM",
            n,
            SensorType.ROOM_COUNT,
            SensorTarget.ROOM,
            r.room_id,
            r.floor_id,
            r.zone_id,
            (),
            s.room_poll_interval,
        )
    n = 0
    for z in layout.zones:
        n += 1
        add(
            "ENV",
            n,
            SensorType.ENVIRONMENT,
            SensorTarget.ZONE,
            z.zone_id,
            z.floor_id,
            z.zone_id,
            ENV_METRICS,
            s.environment_poll_interval,
        )
    for r in layout.rooms:
        n += 1
        add(
            "ENV",
            n,
            SensorType.ENVIRONMENT,
            SensorTarget.ROOM,
            r.room_id,
            r.floor_id,
            r.zone_id,
            ENV_METRICS,
            s.environment_poll_interval,
        )
