"""Schemas for building layouts (config/layouts/*.yaml) and layout presets.

A layout file is explicit and hand-editable: zones are rectangles, desks are grid blocks that the
loader expands into individual workspaces. Presets drive the LayoutGenerator that writes such files.
Units are metres.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workplace_domain.enums import AccessDirection, AreaSubtype, DeskPolicy, RoomType, ZoneType

NonNeg = Annotated[float, Field(ge=0)]
Positive = Annotated[float, Field(gt=0)]
PositiveInt = Annotated[int, Field(gt=0)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Rect(_Strict):
    x: NonNeg
    y: NonNeg
    width: Positive
    height: Positive

    @property
    def area(self) -> float:
        return self.width * self.height

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.x + self.width and self.y <= y <= self.y + self.height


class GridBlock(_Strict):
    """rows x cols workspaces; (x, y) is the centre of the first one."""

    x: NonNeg
    y: NonNeg
    rows: PositiveInt
    cols: PositiveInt
    pitch_x: Positive
    pitch_y: Positive

    @property
    def count(self) -> int:
        return self.rows * self.cols

    def positions(self) -> list[tuple[float, float]]:
        return [
            (round(self.x + c * self.pitch_x, 2), round(self.y + r * self.pitch_y, 2))
            for r in range(self.rows)
            for c in range(self.cols)
        ]


class RoomSpec(_Strict):
    name: str
    room_type: RoomType
    capacity: PositiveInt
    rect: Rect

    @model_validator(mode="after")
    def _not_common_area(self) -> RoomSpec:
        if self.room_type is RoomType.COMMON_AREA:
            raise ValueError("use common_areas for COMMON_AREA spaces")
        return self


class CommonAreaSpec(_Strict):
    code: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    name: str
    subtype: AreaSubtype
    capacity: PositiveInt
    rect: Rect


class ZoneSpec(_Strict):
    code: Annotated[str, Field(pattern=r"^[A-Z0-9]{1,3}$")]
    name: str
    zone_type: ZoneType
    rect: Rect
    max_occupancy: Annotated[int, Field(ge=0)]
    desk_blocks: list[GridBlock] = Field(default_factory=list)
    cabin_blocks: list[GridBlock] = Field(default_factory=list)
    rooms: list[RoomSpec] = Field(default_factory=list)
    common_areas: list[CommonAreaSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _contents_inside_zone(self) -> ZoneSpec:
        for block in (*self.desk_blocks, *self.cabin_blocks):
            for px, py in block.positions():
                if not self.rect.contains(px, py):
                    raise ValueError(f"zone {self.code}: workspace at ({px}, {py}) is outside")
        return self


class AccessPointSpec(_Strict):
    code: Annotated[str, Field(pattern=r"^[A-Z]+\d{2}$")]
    name: str
    direction: AccessDirection
    x: NonNeg
    y: NonNeg


class FloorSpec(_Strict):
    floor_number: PositiveInt
    name: str
    desk_policy: DeskPolicy
    max_occupancy: PositiveInt
    width: Positive
    height: Positive
    zones: list[ZoneSpec] = Field(min_length=1)
    access_points: list[AccessPointSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_codes(self) -> FloorSpec:
        codes = [z.code for z in self.zones]
        if len(set(codes)) != len(codes):
            raise ValueError(f"floor {self.floor_number}: zone codes must be unique")
        areas = [a.code for z in self.zones for a in z.common_areas]
        if len(set(areas)) != len(areas):
            raise ValueError(f"floor {self.floor_number}: common area codes must be unique")
        return self


class BuildingSpec(_Strict):
    building_id: Annotated[str, Field(pattern=r"^BLD\d{2}$")]
    name: str
    max_occupancy: PositiveInt
    floors: list[FloorSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_floors(self) -> BuildingSpec:
        numbers = [f.floor_number for f in self.floors]
        if len(set(numbers)) != len(numbers):
            raise ValueError("floor numbers must be unique")
        if not any(f.access_points for f in self.floors):
            raise ValueError("building needs at least one access point")
        return self


class LayoutFile(_Strict):
    building: BuildingSpec


# ---------------------------------------------------------------- presets


class LayoutPreset(_Strict):
    building_id: Annotated[str, Field(pattern=r"^BLD\d{2}$")]
    building_name: str
    floors: PositiveInt
    modules_per_row: Annotated[int, Field(ge=3)]
    module_width: Positive
    module_depth: Positive
    corridor_depth: Positive
    desk_rows: PositiveInt
    desk_cols: PositiveInt
    desk_pitch_x: Positive
    desk_pitch_y: Positive
    room_mix: list[RoomType] = Field(min_length=1)
    cabins_per_block: PositiveInt
    assigned_floors: list[int]
    entrances: PositiveInt
    occupancy_factor: Annotated[float, Field(ge=1)]


class LayoutPresetsFile(_Strict):
    room_capacity: dict[RoomType, PositiveInt]
    amenity_capacity: dict[AreaSubtype, PositiveInt]
    presets: dict[str, LayoutPreset]

    @model_validator(mode="after")
    def _capacities_cover_mix(self) -> LayoutPresetsFile:
        needed = {t for p in self.presets.values() for t in p.room_mix} | {RoomType.AUDITORIUM}
        missing = needed - set(self.room_capacity)
        if missing:
            raise ValueError(f"room_capacity missing {sorted(missing)}")
        return self
