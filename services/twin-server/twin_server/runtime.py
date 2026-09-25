"""Base class for long-running in-process services (engine, processor)."""

from __future__ import annotations

import asyncio
import contextlib
from abc import ABC, abstractmethod
from datetime import UTC, datetime

import structlog

from workplace_domain.enums import ComponentStatus
from workplace_domain.interfaces import ComponentHealth


class BackgroundService(ABC):
    name: str

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._started_at: datetime | None = None
        self.log = structlog.get_logger(self.name)

    def start(self) -> None:
        if self._task is None:
            self._started_at = datetime.now(UTC)
            self._task = asyncio.create_task(self._run(), name=self.name)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    @abstractmethod
    async def _run(self) -> None: ...

    def _state_info(self) -> dict[str, object]:
        return {}

    async def health(self) -> ComponentHealth:
        info: dict[str, object] = {
            "started_at": self._started_at.isoformat() if self._started_at else None,
            **self._state_info(),
        }
        if self._task is None:
            return ComponentHealth(ComponentStatus.DOWN, "not started", info)
        if self._task.done():
            exc = None if self._task.cancelled() else self._task.exception()
            return ComponentHealth(ComponentStatus.DOWN, f"stopped: {exc!r}", info)
        return ComponentHealth(ComponentStatus.OK, "running", info)
