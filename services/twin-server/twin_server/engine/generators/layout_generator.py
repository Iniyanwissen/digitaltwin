"""Generate an explicit, hand-editable layout file from a size preset (config/layout_presets.yaml).

Each floor is two rows of modules separated by a corridor:
  top row:    desk zones ... | meeting zone
  corridor:   corridor ...   | lobby (reception + entrances on floor 1)
  bottom row: desk zones ... | meeting zone | amenity
"""

from __future__ import annotations

import math
import string

from workplace_domain.config.layout import (
    AccessPointSpec,
    BuildingSpec,
    CommonAreaSpec,
    FloorSpec,
    GridBlock,
    LayoutFile,
    LayoutPreset,
    LayoutPresetsFile,
    Rect,
    RoomSpec,
    ZoneSpec,
)
from workplace_domain.enums import (
    AccessDirection,
    AreaSubtype,
    DeskPolicy,
    ReaderType,
    RoomType,
    ZoneType,
)

_ROOM_MARGIN = 0.5
_AREA_MARGIN = 1.0


def _centered_grid(rect: Rect, rows: int, cols: int, pitch_x: float, pitch_y: float) -> GridBlock:
    x = rect.x + (rect.width - (cols - 1) * pitch_x) / 2
    y = rect.y + (rect.height - (rows - 1) * pitch_y) / 2
    return GridBlock(
        x=round(x, 2), y=round(y, 2), rows=rows, cols=cols, pitch_x=pitch_x, pitch_y=pitch_y
    )


def _inset(rect: Rect, margin: float) -> Rect:
    return Rect(
        x=round(rect.x + margin, 2),
        y=round(rect.y + margin, 2),
        width=round(rect.width - 2 * margin, 2),
        height=round(rect.height - 2 * margin, 2),
    )


def _desk_zone(code: str, index: int, rect: Rect, p: LayoutPreset) -> ZoneSpec:
    block = _centered_grid(rect, p.desk_rows, p.desk_cols, p.desk_pitch_x, p.desk_pitch_y)
    zone_type = ZoneType.TEAM_NEIGHBORHOOD if index % 2 else ZoneType.OPEN_WORKSPACE
    return ZoneSpec(
        code=code,
        name=f"Workspace {code}",
        zone_type=zone_type,
        rect=rect,
        max_occupancy=block.count,
        desk_blocks=[block],
    )


def _meeting_zone(
    code: str,
    rect: Rect,
    floor_number: int,
    first_room_no: int,
    p: LayoutPreset,
    presets: LayoutPresetsFile,
    auditorium: bool,
) -> ZoneSpec:
    rooms: list[RoomSpec] = []
    if auditorium:
        rooms.append(
            RoomSpec(
                name="Auditorium",
                room_type=RoomType.AUDITORIUM,
                capacity=presets.room_capacity[RoomType.AUDITORIUM],
                has_badge_reader=RoomType.AUDITORIUM in presets.door_reader_room_types,
                has_panel=RoomType.AUDITORIUM in presets.panel_room_types,
                rect=_inset(rect, _AREA_MARGIN),
            )
        )
    else:
        cols = math.ceil(len(p.room_mix) / 2)
        cell_w, cell_h = rect.width / cols, rect.height / 2
        for i, room_type in enumerate(p.room_mix):
            cell = Rect(
                x=round(rect.x + (i % cols) * cell_w, 2),
                y=round(rect.y + (i // cols) * cell_h, 2),
                width=round(cell_w, 2),
                height=round(cell_h, 2),
            )
            rooms.append(
                RoomSpec(
                    name=f"Room {floor_number}.{first_room_no + i:02d}",
                    room_type=room_type,
                    capacity=presets.room_capacity[room_type],
                    has_badge_reader=room_type in presets.door_reader_room_types,
                    has_panel=room_type in presets.panel_room_types,
                    rect=_inset(cell, _ROOM_MARGIN),
                )
            )
    return ZoneSpec(
        code=code,
        name="Meeting rooms" if not auditorium else "Auditorium",
        zone_type=ZoneType.MEETING,
        rect=rect,
        max_occupancy=sum(r.capacity for r in rooms),
        rooms=rooms,
    )


def _amenity_zone(
    rect: Rect, floor_number: int, assigned: bool, p: LayoutPreset, presets: LayoutPresetsFile
) -> ZoneSpec:
    if assigned:
        cols = math.ceil(p.cabins_per_block / 2)
        block = _centered_grid(rect, 2, cols, rect.width / cols, rect.height / 2)
        return ZoneSpec(
            code="X",
            name="Cabins",
            zone_type=ZoneType.CABIN_BLOCK,
            rect=rect,
            max_occupancy=block.count,
            cabin_blocks=[block],
        )
    if floor_number == 1:
        subtype, zone_type, area_code, name = (
            AreaSubtype.CAFETERIA,
            ZoneType.CAFETERIA,
            "CAF",
            "Cafeteria",
        )
    elif floor_number % 2 == 0:
        subtype, zone_type, area_code, name = (
            AreaSubtype.COLLABORATION,
            ZoneType.COLLABORATION,
            "COL",
            "Collaboration area",
        )
    else:
        subtype, zone_type, area_code, name = (
            AreaSubtype.LOUNGE,
            ZoneType.LOUNGE,
            "LNG",
            "Lounge",
        )
    capacity = presets.amenity_capacity[subtype]
    return ZoneSpec(
        code="X",
        name=name,
        zone_type=zone_type,
        rect=rect,
        max_occupancy=capacity,
        common_areas=[
            CommonAreaSpec(
                code=area_code,
                name=name,
                subtype=subtype,
                capacity=capacity,
                rect=_inset(rect, _AREA_MARGIN),
            )
        ],
    )


def _floor(floor_number: int, p: LayoutPreset, presets: LayoutPresetsFile) -> FloorSpec:
    mw, md, cd, n = p.module_width, p.module_depth, p.corridor_depth, p.modules_per_row
    width, height = n * mw, 2 * md + cd
    assigned = floor_number in p.assigned_floors
    desk_codes = iter(string.ascii_uppercase)
    zones: list[ZoneSpec] = []
    desk_index = 0
    meeting_no = 0
    next_room_no = 1

    rows = (
        (0.0, ["desk"] * (n - 1) + ["meeting"]),
        (md + cd, ["desk"] * (n - 2) + ["meeting", "amenity"]),
    )
    for y0, kinds in rows:
        for i, kind in enumerate(kinds):
            rect = Rect(x=i * mw, y=y0, width=mw, height=md)
            if kind == "desk":
                zones.append(_desk_zone(next(desk_codes), desk_index, rect, p))
                desk_index += 1
            elif kind == "meeting":
                meeting_no += 1
                zone = _meeting_zone(
                    f"M{meeting_no}",
                    rect,
                    floor_number,
                    next_room_no,
                    p,
                    presets,
                    auditorium=floor_number == 1 and meeting_no == 2,
                )
                next_room_no += len(zone.rooms)
                zones.append(zone)
            else:
                zones.append(_amenity_zone(rect, floor_number, assigned, p, presets))

    zones.append(
        ZoneSpec(
            code="R",
            name="Corridor",
            zone_type=ZoneType.CIRCULATION,
            rect=Rect(x=0, y=md, width=width - mw, height=cd),
            max_occupancy=0,
        )
    )
    lobby = Rect(x=width - mw, y=md, width=mw, height=cd)
    zones.append(
        ZoneSpec(
            code="L",
            name="Reception" if floor_number == 1 else "Lift lobby",
            zone_type=ZoneType.ENTRANCE if floor_number == 1 else ZoneType.CIRCULATION,
            rect=lobby,
            max_occupancy=0,
        )
    )
    access_points = (
        [
            AccessPointSpec(
                code=f"ENT{k:02d}",
                name=f"Entrance {k}",
                direction=AccessDirection.IN_OUT,
                x=round(lobby.x + lobby.width * k / (p.entrances + 1), 2),
                y=round(lobby.y + lobby.height / 2, 2),
            )
            for k in range(1, p.entrances + 1)
        ]
        if floor_number == 1
        else [
            AccessPointSpec(
                code="LOBBY",
                name=f"Floor {floor_number} lobby",
                direction=AccessDirection.IN,
                x=round(lobby.x + lobby.width / 2, 2),
                y=round(lobby.y + lobby.height / 2, 2),
                reader_type=ReaderType.FLOOR_LOBBY,
            )
        ]
    )
    workspaces = sum(b.count for z in zones for b in (*z.desk_blocks, *z.cabin_blocks))
    return FloorSpec(
        floor_number=floor_number,
        name=f"Floor {floor_number}",
        desk_policy=DeskPolicy.ASSIGNED if assigned else DeskPolicy.HOT_DESK,
        max_occupancy=math.ceil(workspaces * p.occupancy_factor),
        width=width,
        height=height,
        zones=zones,
        access_points=access_points,
    )


def generate_layout(preset: LayoutPreset, presets: LayoutPresetsFile) -> LayoutFile:
    floors = [_floor(n, preset, presets) for n in range(1, preset.floors + 1)]
    return LayoutFile(
        building=BuildingSpec(
            building_id=preset.building_id,
            name=preset.building_name,
            max_occupancy=sum(f.max_occupancy for f in floors),
            floors=floors,
        )
    )
