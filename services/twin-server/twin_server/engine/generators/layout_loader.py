"""Expand layout files into master-data entities (floors, zones, workspaces, rooms, readers,
sensors)."""

from __future__ import annotations

import dataclasses

from twin_server.engine.generators.apportion import apportion
from workplace_domain import ids
from workplace_domain.config import WorkplaceConfig
from workplace_domain.config.layout import BuildingSpec
from workplace_domain.enums import (
    AccessDirection,
    DeviceType,
    MetricType,
    ReaderType,
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
                    is_restricted=False,
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
                            device_type=DeviceType.DOCKING_STATION,  # set by _finalize_workspaces
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
                            device_type=DeviceType.DOCKING_STATION,  # set by _finalize_workspaces
                        )
                    )
            for rs in zs.rooms:
                room_no += 1
                room_id = ids.room_id(b, fn, room_no)
                layout.rooms.append(
                    Room(
                        room_id=room_id,
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
                        has_badge_reader=rs.has_badge_reader,
                        has_panel=rs.has_panel,
                    )
                )
                if rs.has_badge_reader:
                    layout.access_points.append(
                        AccessPoint(
                            access_point_id=ids.door_reader_id(room_id),
                            building_id=b,
                            floor_id=floor_id,
                            name=f"{rs.name} door",
                            direction=AccessDirection.IN,
                            x=round(rs.rect.x + 0.5, 2),
                            y=round(rs.rect.y + rs.rect.height / 2, 2),
                            reader_type=ReaderType.ROOM_DOOR,
                            target_id=room_id,
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
                        has_badge_reader=False,
                        has_panel=False,
                    )
                )
        for ap in fs.access_points:
            lobby = ap.reader_type is ReaderType.FLOOR_LOBBY
            layout.access_points.append(
                AccessPoint(
                    access_point_id=ids.lobby_reader_id(floor_id)
                    if lobby
                    else ids.access_point_id(b, ap.code),
                    building_id=b,
                    floor_id=floor_id,
                    name=ap.name,
                    direction=ap.direction,
                    x=ap.x,
                    y=ap.y,
                    reader_type=ap.reader_type,
                    target_id=floor_id if lobby else b,
                )
            )


def _finalize_workspaces(layout: Layout, config: WorkplaceConfig, rng: RngFactory) -> None:
    """Choose which workspaces have sensors and assign device types (exact mixes, seeded)."""
    n = len(layout.workspaces)
    coverage = config.simulation.sensors.desk_sensor_coverage
    sensed = {
        int(i)
        for i in rng.stream("sensor_coverage").choice(n, size=round(coverage * n), replace=False)
    }
    counts = apportion(n, dict(config.simulation.office.device_type_mix))
    devices = [d for d, c in counts.items() for _ in range(c)]
    order = rng.stream("device_type").permutation(n)
    layout.workspaces[:] = [
        dataclasses.replace(
            w, has_sensor=i in sensed, device_type=DeviceType(devices[int(order[i])])
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
    _finalize_workspaces(layout, config, rng)
    _generate_sensors(layout, config)
    return layout
