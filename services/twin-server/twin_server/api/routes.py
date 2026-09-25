"""HTTP routes. Thin: resolve the context, delegate to api.services."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from twin_server.api import services
from twin_server.api.schemas import HealthOut, MetaOut
from twin_server.context import AppContext
from workplace_domain.enums import ComponentStatus


def get_ctx(request: Request) -> AppContext:
    ctx: AppContext = request.app.state.ctx
    return ctx


Ctx = Annotated[AppContext, Depends(get_ctx)]

system_router = APIRouter(tags=["system"])
api_v1_router = APIRouter(prefix="/api/v1", tags=["meta"])


@system_router.get("/health", response_model=HealthOut)
async def health(ctx: Ctx, response: Response) -> HealthOut:
    result = await services.get_health(ctx)
    if result.status == ComponentStatus.DOWN:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@api_v1_router.get("/meta", response_model=MetaOut)
async def meta(ctx: Ctx) -> MetaOut:
    return services.get_meta(ctx)
