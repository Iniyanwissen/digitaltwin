"""Live Simulation v2 endpoints (/api/v2). Separate from v1 (/api/v1)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from twin_server.api.routes import Ctx
from twin_server.context import AppContext
from twin_server.v2.world import V2World

v2_router = APIRouter(prefix="/api/v2", tags=["live simulation v2"])


def _world(ctx: AppContext) -> V2World:
    if ctx.v2 is None:
        raise HTTPException(503, "live simulation v2 not available (check config/v2)")
    return ctx.v2


@v2_router.get("/layout")
async def layout(ctx: Ctx) -> dict[str, Any]:
    """Floor-plan geometry in metres for the v2 twin (render-only fields included)."""
    return _world(ctx).render


@v2_router.get("/areas")
async def areas(ctx: Ctx) -> list[dict[str, Any]]:
    """Environment areas: every zone and every room/common area (environment-and-esg.md §1)."""
    return _world(ctx).env_areas
