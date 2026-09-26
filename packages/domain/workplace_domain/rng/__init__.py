"""The only source of randomness in the system (docs/simulation-engine.md §5).

Every consumer asks for a named stream, optionally keyed (per day, per person, per sensor...).
Streams are derived from the root seed with a stable hash, so adding a new stream or a new key
never shifts the draws of existing ones.

Two flavours share the same derivation:
- `stream()` returns a numpy Generator (vectorised draws: generators, analytics)
- `py_stream()` returns a stdlib Random (many scalar draws: the simulation engine; faster per call)
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence

import numpy as np
import xxhash

# Re-exported so engine code can type-annotate streams without importing `random` itself.
PyRandom = random.Random


def stable_hash(value: str) -> int:
    """Process-independent 64-bit hash (never Python's salted hash())."""
    return xxhash.xxh64_intdigest(value.encode("utf-8"))


class RngFactory:
    def __init__(self, root_seed: int) -> None:
        if root_seed < 0:
            raise ValueError("root_seed must be non-negative")
        self.root_seed = root_seed

    def _seed_sequence(self, name: str, keys: tuple[object, ...]) -> np.random.SeedSequence:
        entropy = [self.root_seed, stable_hash(name), *(stable_hash(str(k)) for k in keys)]
        return np.random.SeedSequence(entropy)

    def stream(self, name: str, *keys: object) -> np.random.Generator:
        return np.random.Generator(np.random.PCG64(self._seed_sequence(name, keys)))

    def py_stream(self, name: str, *keys: object) -> random.Random:
        state = self._seed_sequence(name, keys).generate_state(2, np.uint64)
        return random.Random(int(state[0]) << 64 | int(state[1]))


def lognormal_from_median_p90(rng: random.Random, median: float, p90: float) -> float:
    """Log-normal draw parameterised by its median and 90th percentile."""
    mu = math.log(median)
    sigma = (math.log(p90) - mu) / 1.2816  # z-score of the 90th percentile
    return rng.lognormvariate(mu, sigma)


def weighted_choice[K](rng: random.Random, weights: Mapping[K, float]) -> K:
    keys: Sequence[K] = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


__all__ = ["PyRandom", "RngFactory", "lognormal_from_median_p90", "stable_hash", "weighted_choice"]
