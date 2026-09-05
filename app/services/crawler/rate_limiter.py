"""Per-source crawler throttling and concurrency controls.

The limiter is intentionally in-process: it protects a worker process from
bursting requests to the same source. Durable retry timing remains owned by
``job_queue.py`` and source scheduling remains database-backed.
"""

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterator


@dataclass(frozen=True)
class RateLimitConfig:
    """Request pacing and concurrent-request limits for one source."""

    requests_per_second: float = 1.0
    max_concurrency: int = 1
    min_interval_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be > 0")
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        if self.min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must be >= 0")

    @property
    def interval_seconds(self) -> float:
        return max(self.min_interval_seconds, 1.0 / self.requests_per_second)


class SourceRateLimiter:
    """Thread-safe pacing/semaphore limiter keyed by source identifier."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._semaphores: Dict[str, threading.BoundedSemaphore] = {}
        self._last_request: Dict[str, float] = {}

    def _semaphore(self, source_key: str, config: RateLimitConfig) -> threading.BoundedSemaphore:
        with self._lock:
            semaphore = self._semaphores.get(source_key)
            if semaphore is None:
                semaphore = threading.BoundedSemaphore(config.max_concurrency)
                self._semaphores[source_key] = semaphore
            return semaphore

    @contextmanager
    def acquire(self, source_key: str, config: RateLimitConfig) -> Iterator[None]:
        """Acquire a source slot and wait until the minimum request interval."""
        semaphore = self._semaphore(source_key, config)
        semaphore.acquire()
        try:
            with self._lock:
                previous = self._last_request.get(source_key)
                if previous is not None:
                    wait = config.interval_seconds - (time.monotonic() - previous)
                    if wait > 0:
                        time.sleep(wait)
                self._last_request[source_key] = time.monotonic()
            yield
        finally:
            semaphore.release()


DEFAULT_SOURCE_RATE_LIMIT = RateLimitConfig(
    requests_per_second=1.0,
    max_concurrency=1,
)


_LIMITER = SourceRateLimiter()


def get_source_rate_limiter() -> SourceRateLimiter:
    """Return the process-wide limiter shared by crawler adapters."""
    return _LIMITER
