"""Tiny process-local TTL cache for read-mostly repository lookups.

Used so a remote database (hosted Postgres) is not hit on every request. Any write through the same repository
clears it; the short TTL bounds staleness when another process (e.g. the pipeline CLI) writes."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

_MISS = object()


class TtlCache:
    def __init__(self, ttl_seconds: float):
        self.ttl = ttl_seconds
        self._data: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Any, load: Callable[[], Any]) -> Any:
        now = time.monotonic()
        with self._lock:
            hit = self._data.get(key, _MISS)
            if hit is not _MISS and now - hit[0] < self.ttl:
                return hit[1]
        value = load()
        with self._lock:
            self._data[key] = (time.monotonic(), value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
