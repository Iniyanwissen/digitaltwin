"""The only source of randomness in the system (docs/simulation-engine.md §5).

Every consumer asks for a named stream, optionally keyed (per day, per person, per sensor...).
Streams are derived from the root seed with a stable hash, so adding a new stream or a new key
never shifts the draws of existing ones.
"""

from __future__ import annotations

import numpy as np
import xxhash


def stable_hash(value: str) -> int:
    """Process-independent 64-bit hash (never Python's salted hash())."""
    return xxhash.xxh64_intdigest(value.encode("utf-8"))


class RngFactory:
    def __init__(self, root_seed: int) -> None:
        if root_seed < 0:
            raise ValueError("root_seed must be non-negative")
        self.root_seed = root_seed

    def stream(self, name: str, *keys: object) -> np.random.Generator:
        entropy = [self.root_seed, stable_hash(name), *(stable_hash(str(k)) for k in keys)]
        return np.random.Generator(np.random.PCG64(np.random.SeedSequence(entropy)))


__all__ = ["RngFactory", "stable_hash"]
