"""API response models. Mirrored by frontend/src/api/types.ts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from workplace_domain.enums import ComponentStatus


class ComponentHealthOut(BaseModel):
    status: ComponentStatus
    detail: str
    info: dict[str, Any]


class HealthOut(BaseModel):
    status: ComponentStatus
    checked_at: datetime
    components: dict[str, ComponentHealthOut]


class ConfigSummaryOut(BaseModel):
    content_hash: str
    seed: int
    timezone: str
    scale_preset: str
    employee_count: int
    layout_files: list[str]
    default_speed: int
    allowed_speeds: list[int]
    core_hours: str


class MetaOut(BaseModel):
    name: str
    version: str
    environment: str
    server_time: datetime
    config: ConfigSummaryOut
