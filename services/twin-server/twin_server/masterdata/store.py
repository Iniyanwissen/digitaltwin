"""Persist generated master data and track which config/seed version is current."""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import Engine, func, select

from twin_server.db import tables as t
from workplace_domain.config import WorkplaceConfig
from workplace_domain.models import MasterData

_NAMESPACE = uuid.UUID("6f1d1c9e-3b1a-5d0e-8c4f-2a7b9e0d1c33")


def config_id_for(config: WorkplaceConfig) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"config:{config.content_hash}"))


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple | list):
        return [_plain(v) for v in value]
    return value


def _row(entity: Any) -> dict[str, Any]:
    return {k: _plain(v) for k, v in dataclasses.asdict(entity).items()}


class MasterDataStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def current_version(self) -> Mapping[str, Any] | None:
        query = (
            select(
                t.master_data_version, t.office_configuration.c.content_hash.label("config_hash")
            )
            .join(t.office_configuration)
            .where(t.master_data_version.c.is_current.is_(True))
        )
        with self._engine.connect() as conn:
            row = conn.execute(query).first()
        return dict(row._mapping) if row else None

    def counts(self) -> dict[str, int]:
        with self._engine.connect() as conn:
            return {
                name: conn.execute(select(func.count()).select_from(table)).scalar_one()
                for name, table in t.MASTER_TABLES.items()
            }

    def replace(self, master: MasterData, config: WorkplaceConfig) -> str:
        """Replace all master data in one transaction and mark this version current."""
        config_id = config_id_for(config)
        master_hash = master.content_hash()
        version_id = str(
            uuid.uuid5(uuid.UUID(config_id), f"{config.simulation.seed}:{master_hash}")
        )
        cfg = config.as_json()
        with self._engine.begin() as conn:
            for table in reversed(t.MASTER_TABLES.values()):
                conn.execute(table.delete())
            for name, rows in master.tables().items():
                if rows:
                    conn.execute(t.MASTER_TABLES[name].insert(), [_row(r) for r in rows])

            exists = select(t.office_configuration.c.config_id).where(
                t.office_configuration.c.config_id == config_id
            )
            if conn.execute(exists).first() is None:
                conn.execute(
                    t.office_configuration.insert().values(
                        config_id=config_id,
                        name=config.organization.name,
                        simulation_yaml=cfg["simulation"],
                        organization_yaml=cfg["organization"],
                        layout_yaml=cfg["layouts"],
                        content_hash=config.content_hash,
                        is_active=True,
                    )
                )
            conn.execute(
                t.office_configuration.update()
                .where(t.office_configuration.c.config_id != config_id)
                .values(is_active=False)
            )
            conn.execute(t.master_data_version.update().values(is_current=False))
            version = t.master_data_version
            if conn.execute(select(version).where(version.c.version_id == version_id)).first():
                conn.execute(
                    version.update()
                    .where(version.c.version_id == version_id)
                    .values(is_current=True, generated_at=datetime.now(UTC))
                )
            else:
                conn.execute(
                    version.insert().values(
                        version_id=version_id,
                        config_id=config_id,
                        seed=config.simulation.seed,
                        generated_at=datetime.now(UTC),
                        employee_count=len(master.employees),
                        content_hash=master_hash,
                        is_current=True,
                    )
                )
        return version_id
