from __future__ import annotations

from datetime import timedelta

import pytest

from swing_trading_ai_assistant.market_data.account_rate_limit import (
    ThreadSafeAccountRateLimiterV1,
)
from swing_trading_ai_assistant.market_data.historical import (
    CancellationRequested,
    CancellationToken,
    RetryWaitBoundExceeded,
)


class _Time:
    def __init__(self) -> None:
        self.value = 100.0

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def test_shared_slots_are_reserved_in_order_with_bounded_wait() -> None:
    time = _Time()
    limiter = ThreadSafeAccountRateLimiterV1(
        timedelta(seconds=1), monotonic=time.monotonic, sleeper=time.sleep
    )
    cancellation = CancellationToken()

    assert limiter.acquire(cancellation, timedelta(seconds=2)) == timedelta(0)
    assert limiter.acquire(cancellation, timedelta(seconds=2)) == timedelta(seconds=1)
    assert limiter.acquire(cancellation, timedelta(seconds=2)) == timedelta(seconds=1)


def test_wait_budget_and_cancellation_fail_before_provider_admission() -> None:
    time = _Time()
    limiter = ThreadSafeAccountRateLimiterV1(
        timedelta(seconds=1), monotonic=time.monotonic, sleeper=time.sleep
    )
    cancellation = CancellationToken()
    limiter.acquire(cancellation, timedelta(seconds=1))

    with pytest.raises(RetryWaitBoundExceeded):
        limiter.acquire(cancellation, timedelta(milliseconds=500))
    cancellation.cancel()
    with pytest.raises(CancellationRequested):
        limiter.acquire(cancellation, timedelta(seconds=2))


def test_retry_after_deferral_is_published_to_following_requests() -> None:
    time = _Time()
    limiter = ThreadSafeAccountRateLimiterV1(
        timedelta(seconds=1), monotonic=time.monotonic, sleeper=time.sleep
    )

    assert limiter.defer_for(timedelta(seconds=3), timedelta(seconds=3)) == timedelta(
        seconds=3
    )
    assert limiter.acquire(CancellationToken(), timedelta(seconds=1)) == timedelta(0)


@pytest.mark.parametrize(
    "interval",
    [timedelta(0), timedelta(seconds=-1), timedelta(seconds=61), "one second"],
)
def test_invalid_rate_limit_interval_is_rejected(interval: object) -> None:
    with pytest.raises(ValueError):
        ThreadSafeAccountRateLimiterV1(interval)  # type: ignore[arg-type]


def test_invalid_wait_and_retry_after_budgets_fail_closed() -> None:
    time = _Time()
    limiter = ThreadSafeAccountRateLimiterV1(
        monotonic=time.monotonic, sleeper=time.sleep
    )

    with pytest.raises(RetryWaitBoundExceeded):
        limiter.acquire(CancellationToken(), timedelta(seconds=-1))
    with pytest.raises(RetryWaitBoundExceeded):
        limiter.defer_for(timedelta(seconds=-1), timedelta(seconds=1))
    with pytest.raises(RetryWaitBoundExceeded):
        limiter.defer_for(timedelta(seconds=2), timedelta(seconds=1))


def test_cancellation_during_wait_and_faulty_dependencies_fail_closed() -> None:
    time = _Time()
    cancellation = CancellationToken()

    def cancelling_sleep(seconds: float) -> None:
        time.value += seconds
        cancellation.cancel()

    limiter = ThreadSafeAccountRateLimiterV1(
        monotonic=time.monotonic, sleeper=cancelling_sleep
    )
    limiter.acquire(CancellationToken(), timedelta(seconds=1))
    with pytest.raises(CancellationRequested):
        limiter.acquire(cancellation, timedelta(seconds=2))

    def broken_sleep(seconds: float) -> None:
        raise RuntimeError

    broken = ThreadSafeAccountRateLimiterV1(
        monotonic=time.monotonic, sleeper=broken_sleep
    )
    broken.acquire(CancellationToken(), timedelta(seconds=1))
    with pytest.raises(RetryWaitBoundExceeded):
        broken.acquire(CancellationToken(), timedelta(seconds=2))

    invalid_clock = ThreadSafeAccountRateLimiterV1(monotonic=lambda: -1.0)
    with pytest.raises(RetryWaitBoundExceeded):
        invalid_clock.acquire(CancellationToken(), timedelta(seconds=1))
