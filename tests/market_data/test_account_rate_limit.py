from __future__ import annotations

import threading
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
    with limiter._lock:
        limiter._reservations[7] = 101.0
        limiter._next_request_at = 101.0
    before = (
        limiter._deferred_until,
        dict(limiter._reservations),
        limiter._next_request_at,
    )
    with pytest.raises(RetryWaitBoundExceeded):
        limiter.defer_for(timedelta(seconds=2), timedelta(seconds=1))
    assert (
        limiter._deferred_until,
        limiter._reservations,
        limiter._next_request_at,
    ) == before


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


def test_published_deferral_revalidates_an_already_reserved_waiter() -> None:
    time = _Time()
    limiter = ThreadSafeAccountRateLimiterV1(
        timedelta(seconds=1), monotonic=time.monotonic, sleeper=time.sleep
    )
    cancellation = CancellationToken()
    assert limiter.acquire(cancellation, timedelta(seconds=1)) == timedelta(0)

    # Reserve the next slot, then publish a provider-wide Retry-After before it
    # is sent.  The reservation must move past the deferral, not escape at 101.
    with limiter._lock:  # test-only synchronization of the queued reservation
        limiter._next_request_at = 101.0
        limiter._reservations[1] = 101.0
    assert limiter.defer_for(timedelta(seconds=3), timedelta(seconds=3)) == timedelta(
        seconds=3
    )
    assert limiter._reservations[1] == 103.0


def test_queued_worker_cannot_send_before_a_published_deferral() -> None:
    time = _Time()
    entered_wait = threading.Event()
    release_wait = threading.Event()
    sent_at: list[float] = []

    def sleeper(seconds: float) -> None:
        if (
            threading.current_thread().name == "queued-worker"
            and not entered_wait.is_set()
        ):
            entered_wait.set()
            assert release_wait.wait(timeout=1)
        time.value += seconds

    limiter = ThreadSafeAccountRateLimiterV1(
        timedelta(seconds=1), monotonic=time.monotonic, sleeper=sleeper
    )
    assert limiter.acquire(CancellationToken(), timedelta(seconds=1)) == timedelta(0)

    def provider_worker() -> None:
        limiter.acquire(CancellationToken(), timedelta(seconds=5))
        sent_at.append(time.monotonic())

    worker = threading.Thread(target=provider_worker, name="queued-worker")
    worker.start()
    assert entered_wait.wait(timeout=1)
    assert limiter.defer_for(timedelta(seconds=3), timedelta(seconds=3)) == timedelta(
        seconds=3
    )
    release_wait.set()
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert sent_at and sent_at[0] >= 103.0


def test_acquire_rechecks_a_reservation_shifted_after_its_first_wait() -> None:
    time = _Time()
    limiter = ThreadSafeAccountRateLimiterV1(
        timedelta(seconds=1), monotonic=time.monotonic, sleeper=time.sleep
    )
    assert limiter.acquire(CancellationToken(), timedelta(seconds=1)) == timedelta(0)
    waits = 0

    def shifted_wait(delay: float, _cancellation: object) -> None:
        nonlocal waits
        time.sleep(delay)
        waits += 1
        if waits == 1:
            with limiter._lock:
                reservation = next(iter(limiter._reservations))
                limiter._reservations[reservation] += 2.0

    limiter._wait = shifted_wait  # type: ignore[method-assign]

    assert limiter.acquire(CancellationToken(), timedelta(seconds=4)) == timedelta(
        seconds=3
    )
    assert waits == 2


def test_deferral_wait_observes_cancellation() -> None:
    time = _Time()
    cancellation = CancellationToken()

    def cancelling_sleep(seconds: float) -> None:
        time.value += seconds
        cancellation.cancel()

    limiter = ThreadSafeAccountRateLimiterV1(
        monotonic=time.monotonic, sleeper=cancelling_sleep
    )
    with pytest.raises(CancellationRequested):
        limiter.defer_for(timedelta(seconds=1), timedelta(seconds=1), cancellation)
