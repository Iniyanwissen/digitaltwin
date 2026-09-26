"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from twin_server import __version__
from twin_server.api.routes import api_v1_router, system_router
from twin_server.api.routes_live import live_router, live_ws_router
from twin_server.api.routes_master import master_router
from twin_server.api.routes_v2 import v2_router
from twin_server.context import AppContext
from twin_server.db import run_migrations
from twin_server.log_setup import configure_logging
from twin_server.settings import Settings
from workplace_domain.config import load_workplace_config


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings)
    # Fails fast with a readable ConfigError before the server accepts requests.
    config = load_workplace_config(settings.config_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        ctx = AppContext.build(settings, config)
        app.state.ctx = ctx
        log = structlog.get_logger("api")
        if settings.auto_migrate:
            await run_in_threadpool(run_migrations, settings.resolved_database_url)
        if settings.auto_seed:
            try:
                await run_in_threadpool(ctx.master.ensure)
            except Exception:
                # Surfaced through /health (e.g. migrations not applied); keep serving.
                log.exception("master_data_seed_failed")
        if ctx.master.current is not None:
            ctx.attach_live(ctx.master.current)
        try:
            ctx.attach_v2()
        except Exception:
            # v2 is optional and isolated: a v2 config problem never stops v1.
            log.exception("live_v2_unavailable")
        ctx.start()
        log.info("twin_server_started", port=settings.port)
        try:
            yield
        finally:
            await ctx.stop()

    app = FastAPI(title="Smart Workplace Digital Twin", version=__version__, lifespan=lifespan)
    app.include_router(system_router)
    app.include_router(api_v1_router)
    app.include_router(master_router)
    app.include_router(live_router)
    app.include_router(live_ws_router)
    app.include_router(v2_router)
    return app
