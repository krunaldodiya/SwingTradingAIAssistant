"""Thread-safe provider-account request admission with explicit wait bounds."""

from __future__ import annotations

import threading
import time
from datetime import timedelta
from typing import Protocol

from .historical import (
    CancellationRequested,
    CancellationSignal,
    RetryWaitBoundExceeded,
)


class MonotonicClockV1(Protocol):
    def __call__(self) -> float: ...


class DelaySleeperV1(Protocol):
    def __call__(self, seconds: float, /) -> None: ...


class ThreadSafeAccountRateLimiterV1:
    """Reserve one account-wide request slot at a bounded fixed interval.

    The one-second production default stays below Upstox's tightest published
    standard-API rolling limit (2,000 requests per 30 minutes), while callers
    may inject a stricter interval without changing workflow contracts.
    """

    def __init__(
        self,
        minimum_interval: timedelta = timedelta(seconds=1),
        *,
        monotonic: MonotonicClockV1 = time.monotonic,
        sleeper: DelaySleeperV1 = time.sleep,
    ) -> None:
        if (
            type(minimum_interval) is not timedelta
            or minimum_interval <= timedelta(0)
            or minimum_interval > timedelta(seconds=60)
        ):
            raise ValueError("invalid account rate limit interval")
        self._interval = minimum_interval.total_seconds()
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._lock = threading.Lock()
        self._next_request_at = 0.0
        self._deferred_until = 0.0

    def acquire(
        self, cancellation: CancellationSignal, remaining_wait: timedelta
    ) -> timedelta:
        if type(remaining_wait) is not timedelta or remaining_wait < timedelta(0):
            raise RetryWaitBoundExceeded
        if cancellation.is_cancelled():
            raise CancellationRequested
        with self._lock:
            now = self._now()
            target = max(now, self._next_request_at, self._deferred_until)
            delay = max(target - now, 0.0)
            if delay > remaining_wait.total_seconds():
                raise RetryWaitBoundExceeded
            self._next_request_at = target + self._interval
        self._wait(delay, cancellation)
        return timedelta(seconds=delay)

    def defer_for(self, delay: timedelta, remaining_wait: timedelta) -> timedelta:
        if (
            type(delay) is not timedelta
            or delay < timedelta(0)
            or type(remaining_wait) is not timedelta
            or remaining_wait < timedelta(0)
        ):
            raise RetryWaitBoundExceeded
        with self._lock:
            now = self._now()
            self._deferred_until = max(
                self._deferred_until, now + delay.total_seconds()
            )
            effective = max(self._deferred_until - now, 0.0)
            if effective > remaining_wait.total_seconds():
                raise RetryWaitBoundExceeded
        self._wait(effective, None)
        return timedelta(seconds=effective)

    def _wait(self, delay: float, cancellation: CancellationSignal | None) -> None:
        deadline = self._now() + delay
        while True:
            if cancellation is not None and cancellation.is_cancelled():
                raise CancellationRequested
            remaining = deadline - self._now()
            if remaining <= 0:
                return
            try:
                self._sleeper(min(remaining, 0.05))
            except Exception:
                raise RetryWaitBoundExceeded from None

    def _now(self) -> float:
        try:
            value = self._monotonic()
            if type(value) not in (int, float) or value < 0:
                raise ValueError
            return float(value)
        except Exception:
            raise RetryWaitBoundExceeded from None
