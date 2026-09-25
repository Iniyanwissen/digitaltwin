"""Exact integer apportionment (largest remainder), deterministic tie-break by key."""

from __future__ import annotations

import math
from collections.abc import Hashable, Mapping


def apportion[K: Hashable](total: int, weights: Mapping[K, float]) -> dict[K, int]:
    if total < 0:
        raise ValueError("total must be non-negative")
    weight_sum = sum(weights.values())
    if weight_sum <= 0:
        raise ValueError("weights must have a positive sum")
    raw = {k: total * w / weight_sum for k, w in weights.items()}
    result = {k: math.floor(v) for k, v in raw.items()}
    remainder = total - sum(result.values())
    order = sorted(weights, key=lambda k: (-(raw[k] - result[k]), str(k)))
    for key in order[:remainder]:
        result[key] += 1
    return result
