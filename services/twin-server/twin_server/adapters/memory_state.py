"""In-process current-state store following the Redis key layout (docs/data-model.md §4)."""

from __future__ import annotations

from collections.abc import Mapping

from workplace_domain.enums import ComponentStatus
from workplace_domain.interfaces import ComponentHealth


class InMemoryStateStore:
    """Implements StateStore. State is lost on restart (acceptable for the POC)."""

    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}
        self._sets: dict[str, set[str]] = {}

    async def get_hash(self, key: str) -> dict[str, str]:
        return dict(self._hashes.get(key, {}))

    async def set_hash_fields(self, key: str, fields: Mapping[str, str]) -> None:
        self._hashes.setdefault(key, {}).update(fields)

    async def add_to_set(self, key: str, *members: str) -> None:
        self._sets.setdefault(key, set()).update(members)

    async def remove_from_set(self, key: str, *members: str) -> None:
        target = self._sets.get(key)
        if target is not None:
            target.difference_update(members)

    async def set_members(self, key: str) -> set[str]:
        return set(self._sets.get(key, set()))

    async def delete_prefix(self, prefix: str) -> int:
        removed = 0
        for store in (self._hashes, self._sets):
            for key in [k for k in store if k.startswith(prefix)]:
                del store[key]
                removed += 1
        return removed

    async def health(self) -> ComponentHealth:
        return ComponentHealth(
            ComponentStatus.OK,
            "in-memory state store",
            {"keys": len(self._hashes) + len(self._sets)},
        )
