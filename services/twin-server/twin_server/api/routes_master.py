"""Master data endpoints (read-only). Handlers delegate to MasterDataReader."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from twin_server.api.routes import Ctx
from twin_server.api.schemas import (
    BuildingOut,
    DepartmentOut,
    EmployeeFacetsOut,
    EmployeeOut,
    FloorLayoutOut,
    FloorSummaryOut,
    Page,
    RoomOut,
    SensorOut,
    TeamOut,
    WorkspaceOut,
    ZoneOut,
)
from twin_server.masterdata.reader import EmployeeFilters

master_router = APIRouter(prefix="/api/v1", tags=["master data"])

PageNo = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=500)]


@master_router.get("/buildings", response_model=list[BuildingOut])
async def buildings(ctx: Ctx) -> list[dict[str, object]]:
    return await run_in_threadpool(ctx.master.reader.buildings)


@master_router.get("/floors", response_model=list[FloorSummaryOut])
async def floors(ctx: Ctx, building_id: str | None = None) -> list[dict[str, object]]:
    return await run_in_threadpool(ctx.master.reader.floors, building_id)


@master_router.get("/floors/{floor_id}/layout", response_model=FloorLayoutOut)
async def floor_layout(ctx: Ctx, floor_id: str) -> dict[str, object]:
    layout = await run_in_threadpool(ctx.master.reader.floor_layout, floor_id)
    if layout is None:
        raise HTTPException(404, f"floor {floor_id} not found")
    return layout


@master_router.get("/zones", response_model=list[ZoneOut])
async def zones(ctx: Ctx, floor_id: str | None = None) -> list[dict[str, object]]:
    return await run_in_threadpool(ctx.master.reader.zones, floor_id)


@master_router.get("/rooms", response_model=list[RoomOut])
async def rooms(
    ctx: Ctx, floor_id: str | None = None, room_type: str | None = None
) -> list[dict[str, object]]:
    return await run_in_threadpool(ctx.master.reader.rooms, floor_id, room_type)


@master_router.get("/workspaces", response_model=Page[WorkspaceOut])
async def workspaces(
    ctx: Ctx,
    floor_id: str | None = None,
    zone_id: str | None = None,
    workspace_type: str | None = None,
    page: PageNo = 1,
    page_size: PageSize = 100,
) -> dict[str, object]:
    items, total = await run_in_threadpool(
        ctx.master.reader.workspaces, floor_id, zone_id, workspace_type, page, page_size
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@master_router.get("/sensors", response_model=Page[SensorOut])
async def sensors(
    ctx: Ctx,
    sensor_type: str | None = None,
    floor_id: str | None = None,
    page: PageNo = 1,
    page_size: PageSize = 100,
) -> dict[str, object]:
    items, total = await run_in_threadpool(
        ctx.master.reader.sensors, sensor_type, floor_id, page, page_size
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@master_router.get("/departments", response_model=list[DepartmentOut])
async def departments(ctx: Ctx) -> list[dict[str, object]]:
    return await run_in_threadpool(ctx.master.reader.departments)


@master_router.get("/teams", response_model=list[TeamOut])
async def teams(
    ctx: Ctx, department_id: str | None = None, floor_id: str | None = None
) -> list[dict[str, object]]:
    return await run_in_threadpool(ctx.master.reader.teams, department_id, floor_id)


@master_router.get("/employees", response_model=Page[EmployeeOut])
async def employees(
    ctx: Ctx,
    search: str | None = None,
    department_id: str | None = None,
    team_id: str | None = None,
    floor_id: str | None = None,
    work_mode: str | None = None,
    behavior_profile: str | None = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> dict[str, object]:
    filters = EmployeeFilters(search, department_id, team_id, floor_id, work_mode, behavior_profile)
    items, total = await run_in_threadpool(ctx.master.reader.employees, filters, page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@master_router.get("/employees/facets", response_model=EmployeeFacetsOut)
async def employee_facets(ctx: Ctx) -> dict[str, list[dict[str, Any]]]:
    return await run_in_threadpool(ctx.master.reader.employee_facets)
