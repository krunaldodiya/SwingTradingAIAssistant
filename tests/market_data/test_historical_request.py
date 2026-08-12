from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from threading import Timer

import pytest

import swing_trading_ai_assistant.market_data.historical as historical_module
from swing_trading_ai_assistant.market_data.historical import (
    CancellationRequested,
    CancellationToken,
    HistoricalFetchCode,
    HistoricalFetchFailure,
    HistoricalFetchResult,
    HistoricalRequestExecutor,
    HistoricalResponse,
    ProviderEvent,
    RetryPolicy,
    RetryWaitBoundExceeded,
)
from swing_trading_ai_assistant.market_data.http import (
    HttpResponseHeaders,
    HttpTransportError,
    ProviderErrorCategory,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)


class FakeClock:
    def __init__(self) -> None:
        self.now_value = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.now_value


class FakeSleeper:
    def __init__(self, cancellation: CancellationToken | None = None) -> None:
        self.delays: list[timedelta] = []
        self.cancellation = cancellation

    def sleep(self, delay: timedelta, cancellation: CancellationToken) -> None:
        self.delays.append(delay)
        if self.cancellation is not None:
            self.cancellation.cancel()


class FakeLimiter:
    def __init__(self) -> None:
        self.acquires: list[timedelta] = []
        self.deferrals: list[tuple[timedelta, timedelta]] = []

    def acquire(
        self, cancellation: CancellationToken, remaining_wait: timedelta
    ) -> timedelta:
        self.acquires.append(remaining_wait)
        return timedelta(0)

    def defer_for(self, delay: timedelta, remaining_wait: timedelta) -> timedelta:
        self.deferrals.append((delay, remaining_wait))
        return delay


class FakeJitter:
    def uniform(self, lower: float, upper: float) -> float:
        return lower


class FakeSession:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.requests: list[object] = []

    def fetch(self, request: object) -> object:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _plan() -> PlannedInstrumentMonth:
    return PlannedInstrumentMonth(
        provider="upstox",
        instrument_key="NSE_EQ|INE002A01018",
        security_id="INE002A01018",
        symbol="RELIANCE",
        exchange="NSE",
        segment="NSE_EQ",
        instrument_type="EQ",
        interval="1m",
        year=2026,
        month=7,
        from_date=date(2026, 7, 1),
        to_date=date(2026, 7, 31),
    )


def _success() -> HistoricalResponse:
    return HistoricalResponse(status_code=200, candles=[])


def _executor(
    session: FakeSession,
    limiter: FakeLimiter,
    *,
    policy: RetryPolicy | None = None,
    cancellation: CancellationToken | None = None,
    sleeper: FakeSleeper | None = None,
    events: list[object] | None = None,
) -> HistoricalRequestExecutor:
    return HistoricalRequestExecutor(
        session=session,
        limiter=limiter,
        retry_policy=policy or RetryPolicy(),
        clock=FakeClock(),
        sleeper=sleeper or FakeSleeper(),
        jitter=FakeJitter(),
        cancellation=cancellation or CancellationToken(),
        event_sink=(events.append if events is not None else None),
        run_id="run-1",
    )


def test_executor_constructs_one_minute_full_month_request_without_credentials() -> (
    None
):
    session = FakeSession([_success()])
    limiter = FakeLimiter()

    result = _executor(session, limiter).fetch(_plan(), remaining_attempts=1)

    assert result.response is not None
    request = session.requests[0]
    assert request.instrument_key == "NSE_EQ|INE002A01018"
    assert request.unit == "minutes"
    assert request.interval == 1
    assert request.from_date == date(2026, 7, 1)
    assert request.to_date == date(2026, 7, 31)
    assert len(session.requests) == 1
    assert len(limiter.acquires) == 1


def test_executor_retries_only_retryable_failures_and_uses_bounded_retry_after() -> (
    None
):
    session = FakeSession(
        [
            HistoricalResponse(
                status_code=503,
                candles=[],
                error_category=ProviderErrorCategory.SERVER,
            ),
            HistoricalResponse(
                status_code=429,
                candles=[],
                headers=HttpResponseHeaders.from_items((("Retry-After", "2"),)),
                error_category=ProviderErrorCategory.RATE_LIMITED,
            ),
            _success(),
        ]
    )
    limiter = FakeLimiter()
    sleeper = FakeSleeper()
    events: list[object] = []

    result = _executor(
        session,
        limiter,
        policy=RetryPolicy(
            max_attempts_per_partition=3,
            base_backoff=timedelta(seconds=2),
            max_backoff=timedelta(seconds=2),
            max_retry_after=timedelta(seconds=5),
            max_total_wait=timedelta(seconds=10),
        ),
        sleeper=sleeper,
        events=events,
    ).fetch(_plan(), remaining_attempts=3)

    assert result.response is not None
    assert result.attempts == 3
    assert result.retrieved_at == FakeClock().now_value
    assert len(session.requests) == 3
    assert sleeper.delays == [timedelta(seconds=1)]
    assert limiter.deferrals == [(timedelta(seconds=2), timedelta(seconds=9))]
    assert [event.category for event in events] == [
        "provider_retryable",
        "provider_retryable",
        "provider_success",
    ]


def test_executor_forwards_cancellation_to_account_deferral() -> None:
    observed: list[CancellationToken | None] = []

    class CancellationAwareLimiter(FakeLimiter):
        def defer_for(
            self,
            delay: timedelta,
            remaining_wait: timedelta,
            cancellation: CancellationToken | None = None,
        ) -> timedelta:
            observed.append(cancellation)
            return super().defer_for(delay, remaining_wait)

    cancellation = CancellationToken()
    result = _executor(
        FakeSession(
            [
                HistoricalResponse(
                    status_code=429,
                    candles=[],
                    headers=HttpResponseHeaders.from_items((("Retry-After", "1"),)),
                    error_category=ProviderErrorCategory.RATE_LIMITED,
                ),
                _success(),
            ]
        ),
        CancellationAwareLimiter(),
        cancellation=cancellation,
    ).fetch(_plan(), remaining_attempts=2)

    assert result.response is not None
    assert observed == [cancellation]


def test_executor_prefers_the_safe_cancellation_signature_when_introspection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[CancellationToken | None] = []

    class OpaqueLimiter(FakeLimiter):
        def defer_for(
            self,
            delay: timedelta,
            remaining_wait: timedelta,
            cancellation: CancellationToken | None = None,
        ) -> timedelta:
            observed.append(cancellation)
            return super().defer_for(delay, remaining_wait)

    monkeypatch.setattr(
        historical_module,
        "signature",
        lambda _method: (_ for _ in ()).throw(ValueError("opaque callable")),
    )
    cancellation = CancellationToken()
    result = _executor(
        FakeSession(
            [
                HistoricalResponse(
                    status_code=429,
                    candles=[],
                    headers=HttpResponseHeaders.from_items((("Retry-After", "1"),)),
                    error_category=ProviderErrorCategory.RATE_LIMITED,
                ),
                _success(),
            ]
        ),
        OpaqueLimiter(),
        cancellation=cancellation,
    ).fetch(_plan(), remaining_attempts=2)

    assert result.response is not None
    assert observed == [cancellation]


def test_success_attempts_are_available_for_the_callers_remaining_budget() -> None:
    session = FakeSession(
        [
            HistoricalResponse(
                status_code=503,
                candles=[],
                error_category=ProviderErrorCategory.SERVER,
            ),
            _success(),
        ]
    )

    result = _executor(
        session,
        FakeLimiter(),
        policy=RetryPolicy(max_attempts_per_partition=3),
    ).fetch(_plan(), remaining_attempts=3)

    assert result.response is not None
    assert result.attempts == 2
    assert 3 - result.attempts == 1


def test_executor_stops_on_non_retryable_provider_status() -> None:
    session = FakeSession(
        [
            HistoricalResponse(
                status_code=401,
                candles=[],
                error_category=ProviderErrorCategory.AUTHENTICATION,
            )
        ]
    )
    sleeper = FakeSleeper()

    result = _executor(session, FakeLimiter(), sleeper=sleeper).fetch(
        _plan(), remaining_attempts=3
    )

    assert result.response is None
    assert result.failure is not None
    assert result.failure.code is HistoricalFetchCode.AUTHENTICATION_FAILED
    assert len(session.requests) == 1
    assert sleeper.delays == []


def test_executor_fails_before_wait_when_retry_after_exceeds_invocation_budget() -> (
    None
):
    session = FakeSession(
        [
            HistoricalResponse(
                status_code=429,
                candles=[],
                headers=HttpResponseHeaders.from_items((("Retry-After", "6"),)),
                error_category=ProviderErrorCategory.RATE_LIMITED,
            )
        ]
    )
    limiter = FakeLimiter()
    sleeper = FakeSleeper()

    result = _executor(
        session,
        limiter,
        policy=RetryPolicy(max_total_wait=timedelta(seconds=5)),
        sleeper=sleeper,
    ).fetch(_plan(), remaining_attempts=3)

    assert result.response is None
    assert result.failure is not None
    assert result.failure.code is HistoricalFetchCode.RETRY_WAIT_BOUND_EXCEEDED
    assert limiter.deferrals == []
    assert sleeper.delays == []
    assert len(session.requests) == 1


def test_executor_cancellation_during_backoff_prevents_later_request() -> None:
    cancellation = CancellationToken()
    sleeper = FakeSleeper(cancellation)
    session = FakeSession(
        [
            HistoricalResponse(
                status_code=503,
                candles=[],
                error_category=ProviderErrorCategory.SERVER,
            ),
            _success(),
        ]
    )

    result = _executor(
        session,
        FakeLimiter(),
        cancellation=cancellation,
        sleeper=sleeper,
    ).fetch(_plan(), remaining_attempts=3)

    assert result.response is None
    assert result.failure is not None
    assert result.failure.code is HistoricalFetchCode.CANCELLED
    assert len(session.requests) == 1


def test_executor_sanitizes_provider_contract_exception_and_emits_stable_event() -> (
    None
):
    events: list[object] = []
    session = FakeSession([RuntimeError("token=secret body=provider-secret")])

    result = _executor(session, FakeLimiter(), events=events).fetch(
        _plan(), remaining_attempts=1
    )

    assert result.response is None
    assert result.failure is not None
    assert result.failure.code is HistoricalFetchCode.PROVIDER_CONTRACT
    assert not hasattr(result.failure, "detail")
    assert [event.category for event in events] == ["provider_contract"]
    assert "secret" not in repr(events)


def test_executor_ignores_ambiguous_or_invalid_retry_after_and_records_stable_code() -> (
    None
):
    session = FakeSession(
        [
            HistoricalResponse(
                status_code=429,
                candles=[],
                headers=HttpResponseHeaders.from_items(
                    (("Retry-After", "1"), ("retry-after", "2"))
                ),
                error_category=ProviderErrorCategory.RATE_LIMITED,
            ),
            HistoricalResponse(
                status_code=429,
                candles=[],
                headers=HttpResponseHeaders.from_items((("Retry-After", "later"),)),
                error_category=ProviderErrorCategory.RATE_LIMITED,
            ),
            _success(),
        ]
    )
    limiter = FakeLimiter()
    sleeper = FakeSleeper()
    events: list[object] = []

    result = _executor(
        session,
        limiter,
        policy=RetryPolicy(
            base_backoff=timedelta(seconds=2),
            max_backoff=timedelta(seconds=2),
        ),
        sleeper=sleeper,
        events=events,
    ).fetch(_plan(), remaining_attempts=3)

    assert result.response is not None
    assert limiter.deferrals == []
    assert sleeper.delays == [timedelta(seconds=1), timedelta(seconds=1)]
    assert [event.category for event in events] == [
        "provider_retryable",
        "retry_after_ambiguous",
        "provider_retryable",
        "retry_after_invalid",
        "provider_success",
    ]


def test_executor_accepts_strict_imf_date_and_treats_past_date_as_zero() -> None:
    session = FakeSession(
        [
            HistoricalResponse(
                status_code=429,
                candles=[],
                headers=HttpResponseHeaders.from_items(
                    (("Retry-After", "Fri, 07 Aug 2026 10:00:01 GMT"),)
                ),
                error_category=ProviderErrorCategory.RATE_LIMITED,
            ),
            _success(),
        ]
    )
    limiter = FakeLimiter()
    sleeper = FakeSleeper()

    result = _executor(
        session,
        limiter,
        policy=RetryPolicy(
            base_backoff=timedelta(seconds=2),
            max_backoff=timedelta(seconds=2),
            max_total_wait=timedelta(seconds=5),
        ),
        sleeper=sleeper,
    ).fetch(_plan(), remaining_attempts=2)

    assert result.response is not None
    assert limiter.deferrals == [(timedelta(seconds=1), timedelta(seconds=5))]
    assert sleeper.delays == []


def test_executor_respects_attempt_and_invocation_wide_remaining_budgets() -> None:
    session = FakeSession(
        [
            HistoricalResponse(
                status_code=503,
                candles=[],
                error_category=ProviderErrorCategory.SERVER,
            )
        ]
    )
    limiter = FakeLimiter()

    result = _executor(
        session,
        limiter,
        policy=RetryPolicy(max_total_wait=timedelta(seconds=2)),
    ).fetch(
        _plan(),
        remaining_attempts=1,
        remaining_wait=timedelta(seconds=1),
    )

    assert result.failure is not None
    assert result.failure.code is HistoricalFetchCode.ATTEMPT_BUDGET_EXHAUSTED
    assert result.wait_consumed == timedelta(seconds=1)
    assert limiter.acquires == [timedelta(seconds=1)]


def test_retry_after_exact_remaining_budget_uses_one_effective_delay() -> None:
    session = FakeSession(
        [
            HistoricalResponse(
                status_code=429,
                candles=[],
                headers=HttpResponseHeaders.from_items((("Retry-After", "2"),)),
                error_category=ProviderErrorCategory.RATE_LIMITED,
            ),
            _success(),
        ]
    )
    limiter = FakeLimiter()
    sleeper = FakeSleeper()

    result = _executor(
        session,
        limiter,
        policy=RetryPolicy(
            base_backoff=timedelta(seconds=2),
            max_backoff=timedelta(seconds=2),
            max_total_wait=timedelta(seconds=2),
        ),
        sleeper=sleeper,
    ).fetch(_plan(), remaining_attempts=2)

    assert result.response is not None
    assert result.wait_consumed == timedelta(seconds=2)
    assert limiter.deferrals == [(timedelta(seconds=2), timedelta(seconds=2))]
    assert sleeper.delays == []
    assert len(session.requests) == 2


def test_nonzero_account_deferral_sleeps_only_the_remaining_effective_interval() -> (
    None
):
    session = FakeSession(
        [
            HistoricalResponse(
                status_code=429,
                candles=[],
                headers=HttpResponseHeaders.from_items((("Retry-After", "1"),)),
                error_category=ProviderErrorCategory.RATE_LIMITED,
            ),
            _success(),
        ]
    )
    limiter = FakeLimiter()
    sleeper = FakeSleeper()

    result = _executor(
        session,
        limiter,
        policy=RetryPolicy(
            base_backoff=timedelta(seconds=4),
            max_backoff=timedelta(seconds=4),
            max_total_wait=timedelta(seconds=3),
        ),
        sleeper=sleeper,
    ).fetch(_plan(), remaining_attempts=2)

    assert result.response is not None
    assert result.wait_consumed == timedelta(seconds=2)
    assert limiter.deferrals == [(timedelta(seconds=1), timedelta(seconds=3))]
    assert sleeper.delays == [timedelta(seconds=1)]


@pytest.mark.parametrize(
    "response",
    [
        _success(),
        HistoricalResponse(
            status_code=503,
            candles=[],
            error_category=ProviderErrorCategory.SERVER,
        ),
        HistoricalResponse(
            status_code=401,
            candles=[],
            error_category=ProviderErrorCategory.AUTHENTICATION,
        ),
    ],
)
def test_cancellation_after_session_return_precedes_events_classification_and_result(
    response: HistoricalResponse,
) -> None:
    cancellation = CancellationToken()

    class CancelOnReturnSession(FakeSession):
        def fetch(self, request: object) -> object:
            value = super().fetch(request)
            cancellation.cancel()
            return value

    events: list[object] = []
    session = CancelOnReturnSession([response])

    result = _executor(
        session,
        FakeLimiter(),
        cancellation=cancellation,
        events=events,
    ).fetch(_plan(), remaining_attempts=2)

    assert result.failure is not None
    assert result.failure.code is HistoricalFetchCode.CANCELLED
    assert events == []
    assert len(session.requests) == 1


def test_default_sleeper_observes_cancellation_during_backoff() -> None:
    cancellation = CancellationToken()
    session = FakeSession(
        [
            HistoricalResponse(
                status_code=503,
                candles=[],
                error_category=ProviderErrorCategory.SERVER,
            ),
            _success(),
        ]
    )
    timer = Timer(0.02, cancellation.cancel)
    timer.start()
    try:
        result = HistoricalRequestExecutor(
            session=session,
            limiter=FakeLimiter(),
            retry_policy=RetryPolicy(
                base_backoff=timedelta(seconds=0.2),
                max_backoff=timedelta(seconds=0.2),
            ),
            clock=FakeClock(),
            jitter=FakeJitter(),
            cancellation=cancellation,
        ).fetch(_plan(), remaining_attempts=2)
    finally:
        timer.cancel()

    assert result.failure is not None
    assert result.failure.code is HistoricalFetchCode.CANCELLED
    assert len(session.requests) == 1


def test_partial_month_plan_is_rejected_before_limiter_or_session() -> None:
    partial = PlannedInstrumentMonth(
        provider="upstox",
        instrument_key="NSE_EQ|INE002A01018",
        security_id="INE002A01018",
        symbol="RELIANCE",
        exchange="NSE",
        segment="NSE_EQ",
        instrument_type="EQ",
        interval="1m",
        year=2026,
        month=7,
        from_date=date(2026, 7, 2),
        to_date=date(2026, 7, 31),
    )
    session = FakeSession([_success()])
    limiter = FakeLimiter()

    with pytest.raises(ValueError, match="full calendar month"):
        _executor(session, limiter).fetch(partial, remaining_attempts=1)

    assert session.requests == []
    assert limiter.acquires == []


@pytest.mark.parametrize("clock", [object()])
def test_invalid_clock_output_maps_to_sanitized_typed_result(clock: object) -> None:
    class InvalidClock:
        def now(self) -> object:
            return clock

    session = FakeSession([_success()])
    events: list[object] = []
    result = HistoricalRequestExecutor(
        session=session,
        limiter=FakeLimiter(),
        clock=InvalidClock(),  # type: ignore[arg-type]
        sleeper=FakeSleeper(),
        jitter=FakeJitter(),
        event_sink=events.append,
        run_id="run-1",
    ).fetch(_plan(), remaining_attempts=1)

    assert result.response is None
    assert result.failure is not None
    assert result.failure.code is HistoricalFetchCode.PROVIDER_CONTRACT
    assert events == []


def test_event_sink_failure_maps_to_typed_result_without_leaking_exception_text() -> (
    None
):
    def hostile_sink(event: ProviderEvent) -> None:
        raise RuntimeError("token=secret body=provider-secret")

    result = HistoricalRequestExecutor(
        session=FakeSession([_success()]),
        limiter=FakeLimiter(),
        clock=FakeClock(),
        sleeper=FakeSleeper(),
        jitter=FakeJitter(),
        event_sink=hostile_sink,
        run_id="run-1",
    ).fetch(_plan(), remaining_attempts=1)

    assert result.response is None
    assert result.failure is not None
    assert result.failure.code is HistoricalFetchCode.PROVIDER_CONTRACT
    assert "secret" not in repr(result)


def test_public_provider_contract_dataclasses_enforce_sanitized_invariants() -> None:
    valid_time = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)
    ProviderEvent("run-1", 1, "provider_success", "2xx", valid_time)
    HistoricalFetchFailure(HistoricalFetchCode.CANCELLED, 0)
    HistoricalFetchResult(
        response=_success(),
        attempts=1,
        retrieved_at=valid_time,
    )
    HistoricalFetchResult(
        response=None,
        failure=HistoricalFetchFailure(HistoricalFetchCode.PROVIDER_CLIENT, 1, "4xx"),
        wait_consumed=timedelta(seconds=1),
        attempts=1,
    )

    invalid_events = [
        ("run value", 1, "provider_success", "2xx", valid_time),
        ("run-1", 0, "provider_success", "2xx", valid_time),
        ("run-1", 1, "provider secret", "2xx", valid_time),
        ("run-1", 1, "provider_success", "secret", valid_time),
        ("run-1", 1, "provider_success", "2xx", datetime(2026, 8, 7, 10, 0)),
    ]
    for fields in invalid_events:
        with pytest.raises(ValueError):
            ProviderEvent(*fields)  # type: ignore[arg-type]

    invalid_failures = [
        ("provider secret", 1, None),
        (HistoricalFetchCode.PROVIDER_CLIENT, -1, None),
        (HistoricalFetchCode.PROVIDER_CLIENT, 1, "secret"),
    ]
    for fields in invalid_failures:
        with pytest.raises(ValueError):
            HistoricalFetchFailure(*fields)  # type: ignore[arg-type]

    invalid_result_builders = [
        lambda: HistoricalFetchResult(response=None, failure=None, attempts=0),
        lambda: HistoricalFetchResult(
            response=_success(),
            failure=HistoricalFetchFailure(HistoricalFetchCode.PROVIDER_CLIENT, 1),
            attempts=1,
            retrieved_at=valid_time,
        ),
        lambda: HistoricalFetchResult(
            response=None,
            failure=HistoricalFetchFailure(HistoricalFetchCode.PROVIDER_CLIENT, 1),
            wait_consumed=timedelta(seconds=-1),
            attempts=1,
        ),
    ]
    for build_result in invalid_result_builders:
        with pytest.raises(ValueError):
            build_result()


def test_public_evidence_rejects_contradictory_status_and_code_values() -> None:
    valid_time = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)
    invalid_builders = [
        lambda: ProviderEvent("run-1", 1, "provider_success", "5xx", valid_time),
        lambda: ProviderEvent("run-1", 1, "provider_retryable", "2xx", valid_time),
        lambda: HistoricalFetchFailure(HistoricalFetchCode.CANCELLED, 1, "2xx"),
        lambda: HistoricalFetchFailure(HistoricalFetchCode.PROVIDER_CLIENT, 1, "2xx"),
        lambda: HistoricalFetchFailure("CANCELLED", 1),  # type: ignore[arg-type]
        lambda: HistoricalFetchResult(
            response=HistoricalResponse(status_code=500, candles=[]),
            attempts=1,
        ),
    ]

    for build in invalid_builders:
        with pytest.raises(ValueError):
            build()


@pytest.mark.parametrize(
    ("attempts", "failure_attempts"),
    [(0, 1), (1, 0), (1, 2)],
)
def test_historical_fetch_result_rejects_mismatched_failure_attempt_counts(
    attempts: int, failure_attempts: int
) -> None:
    with pytest.raises(ValueError):
        HistoricalFetchResult(
            response=None,
            attempts=attempts,
            failure=HistoricalFetchFailure(
                HistoricalFetchCode.PROVIDER_CONTRACT,
                failure_attempts,
                "4xx",
            ),
        )


@pytest.mark.parametrize("hostile", ("object", "subclass"))
def test_historical_fetch_result_rejects_hostile_failure_before_attribute_access(
    hostile: str,
) -> None:
    class HostileFailure:
        def __getattribute__(self, _: str) -> object:
            raise RuntimeError("failure metadata secret")

    class HostileFailureSubclass(HistoricalFetchFailure):
        def __getattribute__(self, _: str) -> object:
            raise RuntimeError("failure subclass secret")

    failure: object
    if hostile == "object":
        failure = HostileFailure()
    else:
        failure = object.__new__(HostileFailureSubclass)

    with pytest.raises(ValueError) as error:
        HistoricalFetchResult(response=None, attempts=1, failure=failure)  # type: ignore[arg-type]

    assert str(error.value) == "historical fetch result contains an invalid failure"
    assert error.value.__cause__ is None
    assert "secret" not in str(error.value)


def test_historical_fetch_result_rejects_zero_attempt_mismatch_without_payload() -> (
    None
):
    with pytest.raises(ValueError):
        HistoricalFetchResult(
            response=HistoricalResponse(status_code=200, candles=[]),
            attempts=0,
            failure=HistoricalFetchFailure(HistoricalFetchCode.PROVIDER_CLIENT, 0),
        )


def test_executor_cancellation_before_admission_makes_no_provider_or_limiter_call() -> (
    None
):
    cancellation = CancellationToken()
    cancellation.cancel()
    session = FakeSession([_success()])
    limiter = FakeLimiter()

    result = _executor(session, limiter, cancellation=cancellation).fetch(
        _plan(), remaining_attempts=1
    )

    assert result.failure is not None
    assert result.failure.code is HistoricalFetchCode.CANCELLED
    assert session.requests == []
    assert limiter.acquires == []


def test_executor_retries_timeout_transport_failure() -> None:
    session = FakeSession(
        [HttpTransportError(ProviderErrorCategory.TIMEOUT), _success()]
    )
    sleeper = FakeSleeper()

    result = _executor(session, FakeLimiter(), sleeper=sleeper).fetch(
        _plan(), remaining_attempts=2
    )

    assert result.response is not None
    assert len(session.requests) == 2
    assert sleeper.delays == [timedelta(seconds=0.5)]


def test_executor_rejects_malformed_success_response_without_retry() -> None:
    session = FakeSession([HistoricalResponse(status_code=200, candles=[("bad",)])])

    result = _executor(session, FakeLimiter()).fetch(_plan(), remaining_attempts=3)

    assert result.failure is not None
    assert result.failure.code is HistoricalFetchCode.PROVIDER_CONTRACT
    assert len(session.requests) == 1


def test_executor_maps_other_client_status_without_retry() -> None:
    session = FakeSession(
        [
            HistoricalResponse(
                status_code=404,
                candles=[],
                error_category=ProviderErrorCategory.CLIENT,
            )
        ]
    )

    result = _executor(session, FakeLimiter()).fetch(_plan(), remaining_attempts=3)

    assert result.failure is not None
    assert result.failure.code is HistoricalFetchCode.PROVIDER_CLIENT
    assert result.failure.status_class == "4xx"


def test_executor_rejects_retry_after_above_policy_without_waiting() -> None:
    session = FakeSession(
        [
            HistoricalResponse(
                status_code=429,
                candles=[],
                headers=HttpResponseHeaders.from_items((("Retry-After", "3"),)),
                error_category=ProviderErrorCategory.RATE_LIMITED,
            )
        ]
    )
    limiter = FakeLimiter()
    sleeper = FakeSleeper()

    result = _executor(
        session,
        limiter,
        policy=RetryPolicy(max_retry_after=timedelta(seconds=2)),
        sleeper=sleeper,
    ).fetch(_plan(), remaining_attempts=2)

    assert result.failure is not None
    assert result.failure.code is HistoricalFetchCode.RETRY_WAIT_BOUND_EXCEEDED
    assert limiter.deferrals == []
    assert sleeper.delays == []


def test_executor_maps_cancellation_and_provider_errors_from_account_deferral() -> None:
    class CancelLimiter(FakeLimiter):
        def defer_for(self, delay: timedelta, remaining_wait: timedelta) -> timedelta:
            raise CancellationRequested

    class ErrorLimiter(FakeLimiter):
        def defer_for(self, delay: timedelta, remaining_wait: timedelta) -> timedelta:
            raise RuntimeError("account secret")

    response = HistoricalResponse(
        status_code=429,
        candles=[],
        headers=HttpResponseHeaders.from_items((("Retry-After", "1"),)),
        error_category=ProviderErrorCategory.RATE_LIMITED,
    )
    cancelled = _executor(FakeSession([response]), CancelLimiter()).fetch(
        _plan(), remaining_attempts=2
    )
    failed = _executor(FakeSession([response]), ErrorLimiter()).fetch(
        _plan(), remaining_attempts=2
    )

    assert cancelled.failure is not None
    assert cancelled.failure.code is HistoricalFetchCode.CANCELLED
    assert failed.failure is not None
    assert failed.failure.code is HistoricalFetchCode.PROVIDER_CONTRACT


def test_executor_handles_sleeper_bound_failure_and_huge_retry_after_safely() -> None:
    class BoundSleeper(FakeSleeper):
        def sleep(self, delay: timedelta, cancellation: CancellationToken) -> None:
            raise RetryWaitBoundExceeded

    huge = "9" * 4_000
    session = FakeSession(
        [
            HistoricalResponse(
                status_code=429,
                candles=[],
                headers=HttpResponseHeaders.from_items((("Retry-After", huge),)),
                error_category=ProviderErrorCategory.RATE_LIMITED,
            )
        ]
    )
    result = _executor(
        session,
        FakeLimiter(),
        policy=RetryPolicy(max_retry_after=timedelta(seconds=1)),
        sleeper=BoundSleeper(),
    ).fetch(_plan(), remaining_attempts=2)

    assert result.failure is not None
    assert result.failure.code is HistoricalFetchCode.RETRY_WAIT_BOUND_EXCEEDED


def test_executor_stops_after_deferral_cancellation_and_sanitizes_sleeper_failure() -> (
    None
):
    class CancelAfterDeferralLimiter(FakeLimiter):
        def defer_for(self, delay: timedelta, remaining_wait: timedelta) -> timedelta:
            cancellation.cancel()
            return delay

    class ErrorSleeper(FakeSleeper):
        def sleep(self, delay: timedelta, cancellation: CancellationToken) -> None:
            raise RuntimeError("sleeper secret")

    response = HistoricalResponse(
        status_code=429,
        candles=[],
        headers=HttpResponseHeaders.from_items((("Retry-After", "1"),)),
        error_category=ProviderErrorCategory.RATE_LIMITED,
    )
    cancellation = CancellationToken()
    cancelled = _executor(
        FakeSession([response]),
        CancelAfterDeferralLimiter(),
        cancellation=cancellation,
    ).fetch(_plan(), remaining_attempts=2)
    failed = _executor(
        FakeSession([response]),
        FakeLimiter(),
        sleeper=ErrorSleeper(),
    ).fetch(_plan(), remaining_attempts=2)

    assert cancelled.failure is not None
    assert cancelled.failure.code is HistoricalFetchCode.CANCELLED
    assert failed.failure is not None
    assert failed.failure.code is HistoricalFetchCode.PROVIDER_CONTRACT


def test_executor_rejects_invalid_bounds_and_sanitizes_event_identity() -> None:
    session = FakeSession([_success()])
    events: list[object] = []
    executor = _executor(session, FakeLimiter(), events=events)

    try:
        executor.fetch(
            _plan(), remaining_attempts=1, remaining_wait=timedelta(seconds=121)
        )
    except ValueError as error:
        assert "remaining_wait" in str(error)
    else:
        raise AssertionError("invalid remaining wait was accepted")

    result = HistoricalRequestExecutor(
        session=session,
        limiter=FakeLimiter(),
        clock=FakeClock(),
        sleeper=FakeSleeper(),
        jitter=FakeJitter(),
        event_sink=events.append,
        run_id="secret value\n",
    ).fetch(_plan(), remaining_attempts=1)

    assert result.response is not None
    assert events[0].run_id == "run"
