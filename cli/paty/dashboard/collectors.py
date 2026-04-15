"""Rolling buffer of raw metric values for percentile computation."""

from __future__ import annotations

import math
from collections import deque


class RollingCollector:
    """Fixed-size deque per metric name for computing avg/p95/max.

    OTEL histograms only expose min/max/sum/count — no percentiles.
    This collector stores raw values so any frontend can compute
    arbitrary percentiles without depending on OTEL internals.
    """

    def __init__(self, window_size: int = 200):
        self._buffers: dict[str, deque[float]] = {}
        self._window_size = window_size

    def record(self, name: str, value: float) -> None:
        buf = self._buffers.setdefault(name, deque(maxlen=self._window_size))
        buf.append(value)

    def percentile(self, name: str, p: float) -> float | None:
        buf = self._buffers.get(name)
        if not buf:
            return None
        sorted_vals = sorted(buf)
        k = (p / 100.0) * (len(sorted_vals) - 1)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_vals[int(k)]
        return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)

    def avg(self, name: str) -> float | None:
        buf = self._buffers.get(name)
        if not buf:
            return None
        return sum(buf) / len(buf)

    def max_val(self, name: str) -> float | None:
        buf = self._buffers.get(name)
        return max(buf) if buf else None

    def count(self, name: str) -> int:
        return len(self._buffers.get(name, []))
