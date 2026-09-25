"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from twin_server import __version__
from twin_server.api.routes import api_v1_router, system_router
from twin_server.context import AppContext
from twin_server.log_setup import configure_logging
from twin_server.settings import Settings
from workplace_domain.config import load_simulation_config


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings)
    # Fails fast with a readable ConfigError before the server accepts requests.
    config = load_simulation_config(settings.config_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        ctx = AppContext.build(settings, config)
        app.state.ctx = ctx
        ctx.start()
        structlog.get_logger("api").info("twin_server_started", port=settings.port)
        try:
            yield
        finally:
            await ctx.stop()

    app = FastAPI(title="Smart Workplace Digital Twin", version=__version__, lifespan=lifespan)
    app.include_router(system_router)
    app.include_router(api_v1_router)
    return app
