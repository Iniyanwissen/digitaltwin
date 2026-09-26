"""Live Simulation v2 endpoints (/api/v2, /ws/live-v2). Separate from v1 (/api/v1, /ws/live)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from twin_server.api.routes import Ctx
from twin_server.api.routes_live import CommandIn
from twin_server.context import AppContext
from twin_server.v2.live import LiveServiceV2
from twin_server.v2.world import V2World

v2_router = APIRouter(prefix="/api/v2", tags=["live simulation v2"])
v2_ws_router = APIRouter(tags=["live simulation v2"])


def _world(ctx: AppContext) -> V2World:
    if ctx.v2 is None:
        raise HTTPException(503, "live simulation v2 not available (check config/v2)")
    return ctx.v2


def _live(ctx: AppContext) -> LiveServiceV2:
    if ctx.v2_live is None:
        raise HTTPException(503, "live simulation v2 not available (check config/v2)")
    return ctx.v2_live


@v2_router.get("/layout")
async def layout(ctx: Ctx) -> dict[str, Any]:
    """Floor-plan geometry in metres for the v2 twin (render-only fields included)."""
    return _world(ctx).render


@v2_router.get("/areas")
async def areas(ctx: Ctx) -> list[dict[str, Any]]:
    """Environment areas: every zone and every room/common area (environment-and-esg.md §1)."""
    return _world(ctx).env_areas


@v2_router.get("/simulation/status")
async def status(ctx: Ctx) -> dict[str, Any]:
    return _live(ctx).runner.status_info()


@v2_router.post("/simulation/commands")
async def command(ctx: Ctx, body: CommandIn) -> dict[str, Any]:
    try:
        return _live(ctx).runner.command(body.command, body.speed)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@v2_router.get("/live/snapshot")
async def snapshot(ctx: Ctx, truth: bool = False) -> dict[str, Any]:
    return _live(ctx).snapshot(include_truth=truth)


@v2_router.get("/live/desks/{desk_id}")
async def desk_detail(ctx: Ctx, desk_id: str) -> dict[str, Any]:
    detail = _live(ctx).desk_detail(desk_id)
    if detail is None:
        raise HTTPException(404, f"desk {desk_id} not found")
    return detail


@v2_router.get("/live/areas/{area_id}")
async def area_detail(ctx: Ctx, area_id: str) -> dict[str, Any]:
    """Room/zone: people, temperature + 15-min trend, CO2, HVAC, lighting, last action, history."""
    detail = _live(ctx).area_detail(area_id)
    if detail is None:
        raise HTTPException(404, f"area {area_id} not found")
    return detail


@v2_ws_router.websocket("/ws/live-v2")
async def live_socket_v2(websocket: WebSocket, truth: bool = False) -> None:
    """Snapshot on connect, then delta frames (with areas, esg, chips, actions)."""
    ctx: AppContext = websocket.app.state.ctx
    await websocket.accept()
    if ctx.v2_live is None:
        await websocket.close(code=1013, reason="live simulation v2 not ready")
        return
    live = ctx.v2_live
    flush = ctx.config.simulation.processing.live_flush_ms / 1000
    try:
        await websocket.send_json(live.snapshot(include_truth=truth))
        obs_v, truth_v = live.state.version, live.truth.version
        while True:
            await asyncio.sleep(flush)
            frame, obs_v, truth_v = live.frame(obs_v, truth_v, include_truth=truth)
            await websocket.send_json(frame)
    except WebSocketDisconnect:
        return
