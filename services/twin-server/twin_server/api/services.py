"""Logic behind the system endpoints. Route handlers stay thin and call these."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi.concurrency import run_in_threadpool

from twin_server import __version__
from twin_server.api.schemas import ComponentHealthOut, ConfigSummaryOut, HealthOut, MetaOut
from twin_server.context import AppContext
from twin_server.db import check_database
from workplace_domain.enums import ComponentStatus
from workplace_domain.interfaces import ComponentHealth

_SEVERITY = {ComponentStatus.OK: 0, ComponentStatus.DEGRADED: 1, ComponentStatus.DOWN: 2}


def _out(h: ComponentHealth) -> ComponentHealthOut:
    return ComponentHealthOut(status=h.status, detail=h.detail, info=dict(h.info))


def _master_health(ctx: AppContext) -> ComponentHealth:
    try:
        return ctx.master.health()
    except Exception as exc:
        return ComponentHealth(ComponentStatus.DOWN, f"{type(exc).__name__}: {exc}")


async def get_health(ctx: AppContext) -> HealthOut:
    config = ComponentHealth(
        ComponentStatus.OK, "config valid", {"content_hash": ctx.config.content_hash[:12]}
    )
    database, master, bus, state, engine, processor = await asyncio.gather(
        run_in_threadpool(check_database, ctx.db),
        run_in_threadpool(_master_health, ctx),
        ctx.bus.health(),
        ctx.state.health(),
        ctx.engine.health(),
        ctx.processor.health(),
    )
    components = {
        "config": config,
        "database": database,
        "master_data": master,
        "event_bus": bus,
        "state_store": state,
        "simulation_engine": engine,
        "event_processor": processor,
    }
    overall = max((c.status for c in components.values()), key=_SEVERITY.__getitem__)
    return HealthOut(
        status=overall,
        checked_at=datetime.now(UTC),
        components={name: _out(c) for name, c in components.items()},
    )


def get_meta(ctx: AppContext) -> MetaOut:
    cfg = ctx.config.simulation
    core = cfg.simulation.core_hours
    return MetaOut(
        name="Smart Workplace Digital Twin",
        version=__version__,
        environment=ctx.settings.environment,
        server_time=datetime.now(UTC),
        config=ConfigSummaryOut(
            content_hash=ctx.config.content_hash,
            seed=cfg.seed,
            timezone=cfg.timezone,
            scale_preset=cfg.scale_preset,
            organization=ctx.config.organization.name,
            employee_count=cfg.employees.count,
            layout_files=list(cfg.office.layout_files),
            default_speed=cfg.simulation.speed,
            allowed_speeds=list(cfg.simulation.allowed_speeds),
            core_hours=f"{core.start:%H:%M}-{core.end:%H:%M}",
        ),
    )
