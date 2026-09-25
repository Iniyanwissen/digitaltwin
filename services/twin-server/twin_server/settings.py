"""Infrastructure settings from environment variables / .env (never business config)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "local"
    host: str = "127.0.0.1"
    port: int = 8000

    config_dir: Path = Path("config")
    data_dir: Path = Path("data")
    database_url: str | None = None

    event_bus: Literal["memory"] = "memory"
    state_store: Literal["memory"] = "memory"

    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"

    # Wall-clock interval for service heartbeat log lines (operational only).
    heartbeat_interval_s: float = 30.0

    # Apply database migrations at startup (also after auto-reload).
    auto_migrate: bool = True

    # Generate master data at startup when missing or when config/ changed.
    auto_seed: bool = True

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'workplace.db').resolve().as_posix()}"
