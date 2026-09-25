"""Keep master data in sync with the configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import Engine

from twin_server.engine.generators import generate_master_data
from twin_server.masterdata.reader import MasterDataReader
from twin_server.masterdata.store import MasterDataStore, config_id_for
from workplace_domain.config import WorkplaceConfig
from workplace_domain.enums import ComponentStatus
from workplace_domain.interfaces import ComponentHealth

log = structlog.get_logger("master-data")


@dataclass(frozen=True)
class SeedResult:
    generated: bool
    version_id: str | None
    counts: dict[str, int]


class MasterDataService:
    def __init__(self, engine: Engine, config: WorkplaceConfig) -> None:
        self._config = config
        self.store = MasterDataStore(engine)
        self.reader = MasterDataReader(engine)

    def is_current(self) -> bool:
        version = self.store.current_version()
        return version is not None and version["config_id"] == config_id_for(self._config)

    def ensure(self, force: bool = False) -> SeedResult:
        """Regenerate master data if missing, if config or generator output changed, or if forced.

        Generation is cheap and deterministic, so comparing content hashes also catches
        generator code changes that leave the config untouched.
        """
        master = generate_master_data(self._config)
        version = self.store.current_version()
        if (
            not force
            and version is not None
            and version["config_id"] == config_id_for(self._config)
            and version["content_hash"] == master.content_hash()
        ):
            return SeedResult(False, version["version_id"], {})
        version_id = self.store.replace(master, self._config)
        counts = master.counts()
        log.info("master_data_generated", version_id=version_id, **counts)
        return SeedResult(True, version_id, counts)

    def health(self) -> ComponentHealth:
        version = self.store.current_version()
        if version is None:
            return ComponentHealth(ComponentStatus.DOWN, "no master data; run `poe seed`")
        info: dict[str, Any] = {
            "version_id": version["version_id"],
            "seed": version["seed"],
            "employees": version["employee_count"],
        }
        if version["config_id"] != config_id_for(self._config):
            return ComponentHealth(
                ComponentStatus.DEGRADED, "config changed; restart or run `poe seed`", info
            )
        return ComponentHealth(ComponentStatus.OK, f"{version['employee_count']} employees", info)
