"""Live simulation endpoints: control, layout, snapshot, details, truth and the WebSocket.

Operational data and ground truth are separate: truth (positions, hidden collaboration pairs)
is only returned when explicitly requested and is labelled `truth` in every payload.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from twin_server.api.routes import Ctx
from twin_server.context import AppContext
from twin_server.live.service import LiveService
from workplace_domain.enums import SimCommand

live_router = APIRouter(prefix="/api/v1", tags=["live simulation"])
live_ws_router = APIRouter(tags=["live simulation"])


class CommandIn(BaseModel):
    command: SimCommand
    speed: int | None = None


def _live(ctx: AppContext) -> LiveService:
    if ctx.live is None:
        raise HTTPException(503, "live simulation not ready (master data missing)")
    return ctx.live


@live_router.get("/simulation/status")
async def status(ctx: Ctx) -> dict[str, Any]:
    return _live(ctx).runner.status_info()


@live_router.post("/simulation/commands")
async def command(ctx: Ctx, body: CommandIn) -> dict[str, Any]:
    try:
        return _live(ctx).runner.command(body.command, body.speed)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@live_router.get("/live/layout")
async def layout(ctx: Ctx) -> dict[str, Any]:
    return _live(ctx).layout()


@live_router.get("/live/snapshot")
async def snapshot(ctx: Ctx, truth: bool = False) -> dict[str, Any]:
    return _live(ctx).snapshot(include_truth=truth)


@live_router.get("/live/desks/{desk_id}")
async def desk_detail(ctx: Ctx, desk_id: str) -> dict[str, Any]:
    detail = _live(ctx).desk_detail(desk_id)
    if detail is None:
        raise HTTPException(404, f"desk {desk_id} not found")
    return detail


@live_router.get("/live/rooms/{room_id}")
async def room_detail(ctx: Ctx, room_id: str) -> dict[str, Any]:
    detail = _live(ctx).room_detail(room_id)
    if detail is None:
        raise HTTPException(404, f"room {room_id} not found")
    return detail


@live_router.get("/simulation/truth/collaboration")
async def collaboration_truth(ctx: Ctx) -> dict[str, Any]:
    """Hidden collaboration pairs (simulation ground truth, for validation and debug only)."""
    pairs = _live(ctx).collaboration_truth()
    return {
        "truth": True,
        "pairs": [
            {"team_a": p.team_a, "team_b": p.team_b, "cross_floor": p.cross_floor} for p in pairs
        ],
    }


@live_ws_router.websocket("/ws/live")
async def live_socket(websocket: WebSocket, truth: bool = False) -> None:
    """Snapshot on connect, then delta frames every `processing.live_flush_ms`."""
    ctx: AppContext = websocket.app.state.ctx
    await websocket.accept()
    if ctx.live is None:
        await websocket.close(code=1013, reason="live simulation not ready")
        return
    live = ctx.live
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
