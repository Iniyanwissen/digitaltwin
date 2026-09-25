"""Expand layout files into master-data entities (floors, zones, workspaces, rooms, sensors)."""

from __future__ import annotations

from workplace_domain import ids
from workplace_domain.config import WorkplaceConfig
from workplace_domain.config.layout import BuildingSpec
from workplace_domain.enums import (
    MetricType,
    RoomType,
    SensorTarget,
    SensorType,
    SpaceStatus,
    WorkspaceType,
)
from workplace_domain.models import (
    AccessPoint,
    Building,
    Floor,
    Layout,
    Organization,
    Room,
    Sensor,
    Workspace,
    Zone,
)
from workplace_domain.rng import RngFactory

ENV_METRICS = tuple(MetricType)


def _load_building(spec: BuildingSpec, config: WorkplaceConfig, layout: Layout) -> None:
    b = spec.building_id
    layout.buildings.append(
        Building(
            building_id=b,
            org_id=config.organization.org_id,
            name=spec.name,
            timezone=config.simulation.timezone,
            max_occupancy=spec.max_occupancy,
            gross_area_sqm=round(sum(f.width * f.height for f in spec.floors), 2),
        )
    )
    for fs in sorted(spec.floors, key=lambda f: f.floor_number):
        fn = fs.floor_number
        floor_id = ids.floor_id(b, fn)
        layout.floors.append(
            Floor(
                floor_id=floor_id,
                building_id=b,
                floor_number=fn,
                name=fs.name,
                max_occupancy=fs.max_occupancy,
                desk_policy=fs.desk_policy,
                plan_width=fs.width,
                plan_height=fs.height,
                is_available=True,
            )
        )
        desk_no = cabin_no = room_no = 0
        for zs in fs.zones:
            zone_id = ids.zone_id(floor_id, zs.code)
            layout.zones.append(
                Zone(
                    zone_id=zone_id,
                    floor_id=floor_id,
                    name=zs.name,
                    zone_type=zs.zone_type,
                    x=zs.rect.x,
                    y=zs.rect.y,
                    width=zs.rect.width,
                    height=zs.rect.height,
                    max_occupancy=zs.max_occupancy,
                    area_sqm=round(zs.rect.area, 2),
                    is_hvac_zone=True,
                )
            )
            for block in zs.desk_blocks:
                for x, y in block.positions():
                    desk_no += 1
                    layout.workspaces.append(
                        Workspace(
                            ids.desk_id(b, fn, desk_no),
                            floor_id,
                            zone_id,
                            WorkspaceType.DESK,
                            x,
                            y,
                            SpaceStatus.ACTIVE,
                            has_sensor=False,
                        )
                    )
            for block in zs.cabin_blocks:
                for x, y in block.positions():
                    cabin_no += 1
                    layout.workspaces.append(
                        Workspace(
                            ids.cabin_id(b, fn, cabin_no),
                            floor_id,
                            zone_id,
                            WorkspaceType.CABIN,
                            x,
                            y,
                            SpaceStatus.ACTIVE,
                            has_sensor=False,
                        )
                    )
            for rs in zs.rooms:
                room_no += 1
                layout.rooms.append(
                    Room(
                        room_id=ids.room_id(b, fn, room_no),
                        floor_id=floor_id,
                        zone_id=zone_id,
                        name=rs.name,
                        room_type=rs.room_type,
                        area_subtype=None,
                        capacity=rs.capacity,
                        x=rs.rect.x,
                        y=rs.rect.y,
                        width=rs.rect.width,
                        height=rs.rect.height,
                        is_bookable=True,
                        status=SpaceStatus.ACTIVE,
                    )
                )
            for area in zs.common_areas:
                layout.rooms.append(
                    Room(
                        room_id=ids.area_id(b, fn, area.code),
                        floor_id=floor_id,
                        zone_id=zone_id,
                        name=area.name,
                        room_type=RoomType.COMMON_AREA,
                        area_subtype=area.subtype,
                        capacity=area.capacity,
                        x=area.rect.x,
                        y=area.rect.y,
                        width=area.rect.width,
                        height=area.rect.height,
                        is_bookable=False,
                        status=SpaceStatus.ACTIVE,
                    )
                )
        for ap in fs.access_points:
            layout.access_points.append(
                AccessPoint(
                    access_point_id=ids.access_point_id(b, ap.code),
                    building_id=b,
                    floor_id=floor_id,
                    name=ap.name,
                    direction=ap.direction,
                    x=ap.x,
                    y=ap.y,
                )
            )


def _apply_sensor_coverage(layout: Layout, coverage: float, rng: RngFactory) -> None:
    n = len(layout.workspaces)
    k = round(coverage * n)
    chosen = set(int(i) for i in rng.stream("sensor_coverage").choice(n, size=k, replace=False))
    layout.workspaces[:] = [
        Workspace(
            w.workspace_id,
            w.floor_id,
            w.zone_id,
            w.workspace_type,
            w.x,
            w.y,
            w.status,
            has_sensor=i in chosen,
        )
        for i, w in enumerate(layout.workspaces)
    ]


def _generate_sensors(layout: Layout, config: WorkplaceConfig) -> None:
    sensors = config.simulation.sensors
    installed = sensors.installed_at
    for n, w in enumerate((w for w in layout.workspaces if w.has_sensor), start=1):
        layout.sensors.append(
            Sensor(
                ids.sensor_id("DSK", n),
                SensorType.DESK_OCCUPANCY,
                SensorTarget.WORKSPACE,
                w.workspace_id,
                w.floor_id,
                w.zone_id,
                (),
                sensors.desk_poll_interval,
                installed,
                is_active=True,
            )
        )
    for n, r in enumerate(layout.rooms, start=1):
        layout.sensors.append(
            Sensor(
                ids.sensor_id("RM", n),
                SensorType.ROOM_COUNT,
                SensorTarget.ROOM,
                r.room_id,
                r.floor_id,
                r.zone_id,
                (),
                sensors.room_poll_interval,
                installed,
                is_active=True,
            )
        )
    for n, z in enumerate(layout.zones, start=1):
        layout.sensors.append(
            Sensor(
                ids.sensor_id("ENV", n),
                SensorType.ENVIRONMENT,
                SensorTarget.ZONE,
                z.zone_id,
                z.floor_id,
                z.zone_id,
                ENV_METRICS,
                sensors.environment_poll_interval,
                installed,
                is_active=True,
            )
        )


def load_layout(config: WorkplaceConfig, rng: RngFactory) -> Layout:
    org = config.organization
    layout = Layout(organization=Organization(org_id=org.org_id, name=org.name))
    for layout_file in config.layouts:
        _load_building(layout_file.building, config, layout)
    _apply_sensor_coverage(layout, config.simulation.sensors.desk_sensor_coverage, rng)
    _generate_sensors(layout, config)
    return layout
