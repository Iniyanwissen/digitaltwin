"""Identifier formats (docs/data-model.md §1). Deterministic and human-readable."""

from __future__ import annotations

from typing import Literal

SensorKind = Literal["DSK", "RM", "ENV"]


def floor_id(building_id: str, floor_number: int) -> str:
    return f"{building_id}_F{floor_number:02d}"


def zone_id(floor_id_: str, code: str) -> str:
    return f"{floor_id_}_Z{code}"


def desk_id(building_id: str, floor_number: int, n: int) -> str:
    return f"DESK_{building_id}_F{floor_number:02d}_{n:03d}"


def cabin_id(building_id: str, floor_number: int, n: int) -> str:
    return f"CABIN_{building_id}_F{floor_number:02d}_{n:02d}"


def room_id(building_id: str, floor_number: int, n: int) -> str:
    return f"ROOM_{building_id}_F{floor_number:02d}_{n:02d}"


def area_id(building_id: str, floor_number: int, code: str) -> str:
    return f"AREA_{building_id}_F{floor_number:02d}_{code}"


def access_point_id(building_id: str, code: str) -> str:
    return f"AP_{building_id}_{code}"


def sensor_id(kind: SensorKind, n: int) -> str:
    return f"SEN_{kind}_{n:06d}"


def department_id(code: str) -> str:
    return f"DEP_{code}"


def team_id(n: int) -> str:
    return f"TEAM_{n:03d}"


def employee_id(n: int) -> str:
    return f"EMP{n:06d}"
