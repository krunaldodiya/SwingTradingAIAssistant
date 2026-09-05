"""Upstox V3 historical-candle provider adapter."""

from __future__ import annotations

import json
import re
import time
from calendar import monthrange
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from enum import StrEnum
from inspect import Parameter, signature
from random import SystemRandom
from typing import NoReturn, Protocol, cast
from urllib.parse import quote

from .credentials import AccessToken
from .http import (
    HttpResponse,
    HttpResponseBodyTooLarge,
    HttpResponseHeaders,
    HttpResponseHeadersInvalid,
    HttpTransport,
    HttpTransportError,
    ProviderErrorCategory,
    provider_error_category,
)
from .monthly_request_planner import PlannedInstrumentMonth

UPSTOX_API_BASE_URL = "https://api.upstox.com"

_V3_INTERVAL_LIMITS = {
    "minutes": range(1, 301),
    "hours": range(1, 6),
    "days": range(1, 2),
    "weeks": range(1, 2),
    "months": range(1, 2),
}
_MAX_PROVIDER_JSON_NESTING = 64


class HistoricalPayloadError(ValueError):
    """A provider success response failed historical payload validation."""


def _empty_headers() -> HttpResponseHeaders:
    return HttpResponseHeaders()


@dataclass(frozen=True)
class HistoricalRequest:
    instrument_key: str
    unit: str
    interval: int
    from_date: date
    to_date: date

    def __post_init__(self) -> None:
        if not self.instrument_key.strip():
            raise ValueError("instrument_key must not be empty")
        allowed_intervals = _V3_INTERVAL_LIMITS.get(self.unit)
        if allowed_intervals is None:
            raise ValueError("unit is not supported by Upstox Historical V3")
        if self.interval not in allowed_intervals:
            raise ValueError(
                "interval is not supported for this Upstox Historical V3 unit"
            )
        if self.from_date > self.to_date:
            raise ValueError("from_date must be on or before to_date")
        if (
            self.unit == "minutes"
            and self.interval <= 15
            and (self.from_date.year, self.from_date.month)
            != (self.to_date.year, self.to_date.month)
        ):
            raise ValueError("1-15 minute requests must fit within one calendar month")


@dataclass(frozen=True)
class HistoricalResponse:
    status_code: int
    candles: list[list[object]]
    headers: HttpResponseHeaders = field(default_factory=_empty_headers)
    error_category: ProviderErrorCategory | None = None


class UpstoxV3HistoricalClient:
    """Translate the internal request into the documented Upstox V3 route."""

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def fetch(
        self, request: HistoricalRequest, token: AccessToken
    ) -> HistoricalResponse:
        instrument_key = quote(request.instrument_key, safe="")
        url = (
            f"{UPSTOX_API_BASE_URL}/v3/historical-candle/{instrument_key}/"
            f"{request.unit}/{request.interval}/{request.to_date.isoformat()}/"
            f"{request.from_date.isoformat()}"
        )
        oversized = False
        invalid_headers = False
        response: HttpResponse | None = None
        try:
            response = self._transport.get(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token.reveal()}",
                },
            )
        except HttpResponseBodyTooLarge:
            oversized = True
        except HttpResponseHeadersInvalid:
            invalid_headers = True
        if oversized:
            del instrument_key, request, self, token, url, response
            _raise_body_too_large()
        if invalid_headers:
            del instrument_key, request, self, token, url, response
            _raise_invalid_response_headers()
        response = cast(HttpResponse, response)
        if response.status_code < 200 or response.status_code >= 300:
            return HistoricalResponse(
                status_code=response.status_code,
                candles=[],
                headers=response.headers,
                error_category=response.error_category,
            )
        status_code = response.status_code
        error_category = response.error_category
        decode_status, candles = _decode_success_candles(response.body)
        if decode_status is _SuccessDecodeStatus.MALFORMED_JSON:
            del instrument_key, request, response, self, token, url
            _raise_malformed_historical_json()
        if decode_status is _SuccessDecodeStatus.INVALID_ENVELOPE:
            del instrument_key, request, response, self, token, url
            _raise_invalid_success_envelope()
        if decode_status is _SuccessDecodeStatus.INVALID_CANDLES:
            del instrument_key, request, response, self, token, url
            _raise_invalid_candles_array()
        headers = response.headers
        del instrument_key, request, response, self, token, url
        return HistoricalResponse(
            status_code=status_code,
            candles=candles,
            headers=headers,
            error_category=error_category,
        )


class _SuccessDecodeStatus(StrEnum):
    VALID = "VALID"
    MALFORMED_JSON = "MALFORMED_JSON"
    INVALID_ENVELOPE = "INVALID_ENVELOPE"
    INVALID_CANDLES = "INVALID_CANDLES"


class _RejectedProviderJSON(ValueError):
    pass


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _RejectedProviderJSON
        result[key] = value
    return result


def _reject_nonstandard_json_constant(value: str) -> NoReturn:
    del value
    raise _RejectedProviderJSON


def _decode_success_candles(
    body: bytes,
) -> tuple[_SuccessDecodeStatus, list[list[object]]]:
    if not _json_nesting_within_limit(body):
        return _SuccessDecodeStatus.MALFORMED_JSON, []
    try:
        payload: object = json.loads(
            body,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except (ValueError, RecursionError, MemoryError):
        return _SuccessDecodeStatus.MALFORMED_JSON, []
    if type(payload) is not dict:
        return _SuccessDecodeStatus.INVALID_ENVELOPE, []
    payload_record = cast(dict[str, object], payload)
    data = payload_record.get("data")
    if (
        set(payload_record) != {"status", "data"}
        or payload_record.get("status") != "success"
        or type(data) is not dict
    ):
        return _SuccessDecodeStatus.INVALID_ENVELOPE, []
    data_record = cast(dict[str, object], data)
    if set(data_record) != {"candles"}:
        return _SuccessDecodeStatus.INVALID_ENVELOPE, []
    candles = data_record.get("candles")
    if type(candles) is not list:
        return _SuccessDecodeStatus.INVALID_CANDLES, []
    candle_rows = cast(list[object], candles)
    if any(type(row) is not list for row in candle_rows):
        return _SuccessDecodeStatus.INVALID_CANDLES, []
    return _SuccessDecodeStatus.VALID, cast(list[list[object]], candles)


def _json_nesting_within_limit(value: bytes) -> bool:
    depth = 0
    in_string = False
    escaped = False
    for byte in value:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x5B, 0x7B):
            depth += 1
            if depth > _MAX_PROVIDER_JSON_NESTING:
                return False
        elif byte in (0x5D, 0x7D):
            depth -= 1
    return True


def _raise_malformed_historical_json() -> NoReturn:
    raise HistoricalPayloadError("historical response is not valid JSON") from None


def _raise_invalid_success_envelope() -> NoReturn:
    raise HistoricalPayloadError(
        "historical response is not a valid success envelope"
    ) from None


def _raise_invalid_candles_array() -> NoReturn:
    raise HistoricalPayloadError(
        "historical response does not contain a candles array"
    ) from None


def _raise_body_too_large() -> NoReturn:
    raise HttpResponseBodyTooLarge(
        "market-data provider response exceeded limit"
    ) from None


def _raise_invalid_response_headers() -> NoReturn:
    raise HttpResponseHeadersInvalid from None


class HistoricalFetchCode(StrEnum):
    """Stable outcomes exposed by the bounded request executor."""

    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    PROVIDER_CLIENT = "PROVIDER_CLIENT"
    PROVIDER_CONTRACT = "PROVIDER_CONTRACT"
    PROVIDER_RETRYABLE = "PROVIDER_RETRYABLE"
    ATTEMPT_BUDGET_EXHAUSTED = "ATTEMPT_BUDGET_EXHAUSTED"
    RETRY_WAIT_BOUND_EXCEEDED = "RETRY_WAIT_BOUND_EXCEEDED"
    CANCELLED = "CANCELLED"


_MAX_PUBLIC_TEXT = 128
_MAX_PUBLIC_ATTEMPTS = 1_000_000
_EVENT_STATUS_CLASSES = frozenset({"2xx", "4xx", "5xx", "transport", "other"})
_EVENT_CATEGORIES = frozenset(
    {
        "provider_success",
        "provider_retryable",
        "provider_client",
        "provider_contract",
        "authentication_failed",
        "authorization_failed",
        "retry_after_ambiguous",
        "retry_after_invalid",
        "retry_after_oversized",
    }
)


def _event_status_compatible(category: str, status_class: str | None) -> bool:
    if category == "provider_success":
        return status_class == "2xx"
    if category == "provider_retryable":
        return status_class in {"4xx", "5xx", "transport"}
    if category in {"provider_client", "authentication_failed", "authorization_failed"}:
        return status_class == "4xx" or (
            category == "provider_client" and status_class == "other"
        )
    if category in {
        "retry_after_ambiguous",
        "retry_after_invalid",
        "retry_after_oversized",
    }:
        return status_class in {"4xx", "5xx", "transport"}
    if category == "provider_contract":
        return status_class in {None, "4xx", "5xx", "transport", "other"}
    return False


def _failure_status_compatible(
    code: HistoricalFetchCode, status_class: str | None
) -> bool:
    if status_class == "2xx":
        return False
    if code is HistoricalFetchCode.CANCELLED:
        return status_class is None
    if code in {
        HistoricalFetchCode.AUTHENTICATION_FAILED,
        HistoricalFetchCode.AUTHORIZATION_FAILED,
    }:
        return status_class == "4xx"
    if code is HistoricalFetchCode.PROVIDER_CLIENT:
        return status_class in {"4xx", "other"}
    if code is HistoricalFetchCode.PROVIDER_RETRYABLE:
        return status_class in {"4xx", "5xx", "transport"}
    if code in {
        HistoricalFetchCode.ATTEMPT_BUDGET_EXHAUSTED,
        HistoricalFetchCode.RETRY_WAIT_BOUND_EXCEEDED,
    }:
        return status_class in {None, "4xx", "5xx", "transport", "other"}
    if code is HistoricalFetchCode.PROVIDER_CONTRACT:
        return status_class in {None, "4xx", "5xx", "transport", "other"}
    return False


def _valid_success_response_payload(response: object) -> bool:
    return (
        type(response) is HistoricalResponse
        and type(response.status_code) is int
        and 200 <= response.status_code < 300
        and type(response.candles) is list
        and all(type(row) is list for row in response.candles)
        and type(response.headers) is HttpResponseHeaders
        and response.error_category is None
    )


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Immutable bounds for one invocation's provider retry behavior."""

    max_attempts_per_partition: int = 3
    base_backoff: timedelta = timedelta(seconds=1)
    max_backoff: timedelta = timedelta(seconds=8)
    max_retry_after: timedelta = timedelta(seconds=60)
    max_total_wait: timedelta = timedelta(seconds=120)

    def __post_init__(self) -> None:
        if (
            type(self.max_attempts_per_partition) is not int
            or self.max_attempts_per_partition < 1
            or type(self.base_backoff) is not timedelta
            or self.base_backoff < timedelta(0)
            or type(self.max_backoff) is not timedelta
            or self.max_backoff < timedelta(0)
            or type(self.max_retry_after) is not timedelta
            or self.max_retry_after < timedelta(0)
            or type(self.max_total_wait) is not timedelta
            or self.max_total_wait < timedelta(0)
        ):
            raise ValueError("retry policy contains invalid bounds")


class CancellationToken:
    """Small caller-owned cancellation signal used at blocking boundaries."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled


class CancellationSignal(Protocol):
    def is_cancelled(self) -> bool:
        """Return whether the caller has requested cancellation."""
        ...


class HistoricalProviderSession(Protocol):
    def fetch(self, request: HistoricalRequest) -> HistoricalResponse:
        """Execute one already-authenticated Historical V3 request."""
        ...


class AccountRateLimiter(Protocol):
    def acquire(
        self, cancellation: CancellationSignal, remaining_wait: timedelta
    ) -> timedelta | None:
        """Admit one account request, returning the wait charged to the ledger."""
        ...

    def defer_for(
        self,
        delay: timedelta,
        remaining_wait: timedelta,
        cancellation: CancellationSignal | None = None,
    ) -> timedelta | None:
        """Publish an account-wide provider deferral."""
        ...


class CancellableSleeper(Protocol):
    def sleep(self, delay: timedelta, cancellation: CancellationSignal) -> None:
        """Sleep while allowing the caller to observe cancellation."""
        ...


class UtcClock(Protocol):
    def now(self) -> datetime:
        """Return an aware UTC timestamp."""
        ...


class JitterSource(Protocol):
    def uniform(self, lower: float, upper: float) -> float:
        """Return bounded equal-jitter noise."""
        ...


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    """Sanitized provider-attempt or Retry-After diagnostic event."""

    run_id: str
    attempt_ordinal: int
    category: str
    status_class: str | None
    occurred_at: datetime

    def __post_init__(self) -> None:
        if (
            not _safe_identifier(self.run_id)
            or type(self.attempt_ordinal) is not int
            or not 1 <= self.attempt_ordinal <= _MAX_PUBLIC_ATTEMPTS
            or type(self.category) is not str
            or self.category not in _EVENT_CATEGORIES
            or not _safe_status_class(self.status_class)
            or not _event_status_compatible(self.category, self.status_class)
        ):
            raise ValueError("provider event contains invalid sanitized fields")
        object.__setattr__(self, "occurred_at", _utc_datetime(self.occurred_at))


@dataclass(frozen=True, slots=True)
class HistoricalFetchFailure:
    """Typed failure without provider exception, URL, body, or credential text."""

    code: HistoricalFetchCode
    attempts: int
    status_class: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.code) is not HistoricalFetchCode
            or type(self.attempts) is not int
            or not 0 <= self.attempts <= _MAX_PUBLIC_ATTEMPTS
            or not _safe_status_class(self.status_class)
            or not _failure_status_compatible(self.code, self.status_class)
        ):
            raise ValueError("historical fetch failure contains invalid fields")


@dataclass(frozen=True, slots=True)
class HistoricalFetchResult:
    """One bounded fetch outcome with complete attempt and retrieval evidence."""

    response: HistoricalResponse | None
    attempts: int
    failure: HistoricalFetchFailure | None = None
    wait_consumed: timedelta = timedelta(0)
    retrieved_at: datetime | None = None

    def __post_init__(self) -> None:
        failure = self.failure
        if failure is not None and type(failure) is not HistoricalFetchFailure:
            raise ValueError(
                "historical fetch result contains an invalid failure"
            ) from None
        if (self.response is None) == (failure is None):
            raise ValueError("historical fetch result must contain one outcome")
        if (
            type(self.attempts) is not int
            or not 0 <= self.attempts <= _MAX_PUBLIC_ATTEMPTS
            or (self.response is not None and self.attempts < 1)
        ):
            raise ValueError("historical fetch result contains invalid attempts")
        if failure is not None and failure.attempts != self.attempts:
            raise ValueError(
                "historical fetch result contains invalid failure attempts"
            )
        if self.response is not None and not _valid_success_response_payload(
            self.response
        ):
            raise ValueError("historical fetch result contains an invalid response")
        if self.response is not None:
            try:
                object.__setattr__(
                    self, "retrieved_at", _utc_datetime(self.retrieved_at)
                )
            except Exception:
                raise ValueError(
                    "historical fetch result contains an invalid retrieval timestamp"
                ) from None
        elif self.retrieved_at is not None:
            raise ValueError("failed fetch cannot contain a retrieval timestamp")
        if type(self.wait_consumed) is not timedelta or self.wait_consumed < timedelta(
            0
        ):
            raise ValueError("historical fetch result contains an invalid wait")


class RetryWaitBoundExceeded(RuntimeError):
    """A limiter or retry wait could not fit in the invocation ledger."""


class CancellationRequested(RuntimeError):
    """A cancellable injected port stopped its wait."""


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class _SystemSleeper:
    def sleep(self, delay: timedelta, cancellation: CancellationSignal) -> None:
        deadline = time.monotonic() + delay.total_seconds()
        while True:
            try:
                if cancellation.is_cancelled():
                    raise CancellationRequested
            except CancellationRequested:
                raise
            except Exception:
                raise CancellationRequested from None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 0.01))


class _RandomJitter:
    def uniform(self, lower: float, upper: float) -> float:
        return SystemRandom().uniform(lower, upper)


_RETRY_AFTER_SECONDS = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_RETRY_AFTER_IMF = "%a, %d %b %Y %H:%M:%S GMT"


class HistoricalRequestExecutor:
    """Execute one planned month through a bounded authenticated session."""

    def __init__(
        self,
        *,
        session: HistoricalProviderSession,
        limiter: AccountRateLimiter,
        retry_policy: RetryPolicy | None = None,
        clock: UtcClock | None = None,
        sleeper: CancellableSleeper | None = None,
        jitter: JitterSource | None = None,
        cancellation: CancellationSignal | None = None,
        event_sink: Callable[[ProviderEvent], None] | None = None,
        run_id: str = "run",
    ) -> None:
        self._session = session
        self._limiter = limiter
        self._retry_policy = retry_policy or RetryPolicy()
        self._clock = clock or _SystemClock()
        self._sleeper = sleeper or _SystemSleeper()
        self._jitter = jitter or _RandomJitter()
        self._cancellation = cancellation or CancellationToken()
        self._event_sink = event_sink
        self._run_id = _sanitize_run_id(run_id)
        self._consumed_wait = timedelta(0)

    def fetch(
        self,
        plan: PlannedInstrumentMonth,
        *,
        remaining_attempts: int,
        remaining_wait: timedelta | None = None,
    ) -> HistoricalFetchResult:
        prepared = self._prepare_fetch(plan, remaining_attempts, remaining_wait)
        if isinstance(prepared, HistoricalFetchResult):
            return prepared
        request, attempt_limit, consumed_wait = prepared
        return self._run_attempts(
            request, attempt_limit, remaining_attempts, consumed_wait
        )

    def _prepare_fetch(
        self,
        plan: PlannedInstrumentMonth,
        remaining_attempts: int,
        remaining_wait: timedelta | None,
    ) -> tuple[HistoricalRequest, int, timedelta] | HistoricalFetchResult:
        if type(plan) is not PlannedInstrumentMonth:
            raise ValueError("a planned instrument month is required")
        if not _is_full_calendar_month(plan):
            raise ValueError("plan must cover a full calendar month")
        if type(remaining_attempts) is not int or remaining_attempts < 1:
            return HistoricalFetchResult(
                response=None,
                attempts=0,
                failure=HistoricalFetchFailure(
                    HistoricalFetchCode.ATTEMPT_BUDGET_EXHAUSTED, 0
                ),
            )
        if remaining_wait is None:
            remaining_wait = self._retry_policy.max_total_wait
        if (
            type(remaining_wait) is not timedelta
            or remaining_wait < timedelta(0)
            or remaining_wait > self._retry_policy.max_total_wait
        ):
            raise ValueError("remaining_wait is outside the retry policy")

        request = HistoricalRequest(
            instrument_key=plan.instrument_key,
            unit="minutes",
            interval=1,
            from_date=plan.from_date,
            to_date=plan.to_date,
        )
        attempt_limit = min(
            self._retry_policy.max_attempts_per_partition, remaining_attempts
        )
        consumed_wait = self._retry_policy.max_total_wait - remaining_wait
        self._consumed_wait = consumed_wait
        return request, attempt_limit, consumed_wait

    def _run_attempts(
        self,
        request: HistoricalRequest,
        attempt_limit: int,
        remaining_attempts: int,
        consumed_wait: timedelta,
    ) -> HistoricalFetchResult:
        for attempt in range(1, attempt_limit + 1):
            if self._is_cancelled():
                return self._cancelled(attempt - 1)
            consumed_wait, admission_failure = self._admit(consumed_wait, attempt)
            if admission_failure is not None:
                return admission_failure
            if self._is_cancelled():
                return self._cancelled(attempt - 1)
            response, transport_category, contract_failure = self._send(request)
            retrieved_at = self._clock_now()
            if self._is_cancelled():
                return self._cancelled(attempt)
            response, category, response_failure = self._classify_response(
                response, transport_category, contract_failure, attempt
            )
            attempt_result, category, status_class = self._handle_response(
                response, category, response_failure, attempt, retrieved_at
            )
            if attempt_result is not None:
                return attempt_result
            if category is None:
                return self._failure(HistoricalFetchCode.PROVIDER_CONTRACT, attempt)
            retryable = category in {
                ProviderErrorCategory.TIMEOUT,
                ProviderErrorCategory.NETWORK,
                ProviderErrorCategory.RATE_LIMITED,
                ProviderErrorCategory.SERVER,
            }
            failure_code = _failure_code(category, retryable)
            if not retryable:
                return self._failure(failure_code, attempt, status_class)
            consumed_wait, retry_failure = self._prepare_retry(
                response,
                attempt,
                attempt_limit,
                remaining_attempts,
                status_class,
                consumed_wait,
            )
            if retry_failure is not None:
                return retry_failure

        return self._failure(
            HistoricalFetchCode.ATTEMPT_BUDGET_EXHAUSTED, attempt_limit
        )

    def _prepare_retry(
        self,
        response: HistoricalResponse | None,
        attempt: int,
        attempt_limit: int,
        remaining_attempts: int,
        status_class: str | None,
        consumed_wait: timedelta,
    ) -> tuple[timedelta, HistoricalFetchResult | None]:
        if attempt == attempt_limit:
            code = (
                HistoricalFetchCode.ATTEMPT_BUDGET_EXHAUSTED
                if remaining_attempts <= attempt
                else HistoricalFetchCode.PROVIDER_RETRYABLE
            )
            return consumed_wait, self._failure(code, attempt, status_class)
        return self._wait_before_retry(response, attempt, status_class, consumed_wait)

    def _handle_response(
        self,
        response: HistoricalResponse | None,
        category: ProviderErrorCategory | None,
        response_failure: HistoricalFetchResult | None,
        attempt: int,
        retrieved_at: datetime | None,
    ) -> tuple[
        HistoricalFetchResult | None,
        ProviderErrorCategory | None,
        str | None,
    ]:
        if response_failure is not None:
            return response_failure, None, None
        status_class = _status_class(response)
        if category is None:
            event_failure = self._emit(attempt, "provider_success", status_class)
            if event_failure is not None:
                return event_failure, None, status_class
            if retrieved_at is None:
                return (
                    self._failure(HistoricalFetchCode.PROVIDER_CONTRACT, attempt),
                    None,
                    status_class,
                )
            return (
                HistoricalFetchResult(
                    response=cast(HistoricalResponse, response),
                    attempts=attempt,
                    wait_consumed=self._consumed_wait,
                    retrieved_at=retrieved_at,
                ),
                None,
                status_class,
            )
        failure_code = _failure_code(
            category,
            category
            in {
                ProviderErrorCategory.TIMEOUT,
                ProviderErrorCategory.NETWORK,
                ProviderErrorCategory.RATE_LIMITED,
                ProviderErrorCategory.SERVER,
            },
        )
        event_failure = self._emit(attempt, failure_code.lower(), status_class)
        if event_failure is not None:
            return event_failure, category, status_class
        return None, category, status_class

    def _classify_response(
        self,
        response: object | None,
        transport_category: ProviderErrorCategory | None,
        contract_failure: bool,
        attempt: int,
    ) -> tuple[
        HistoricalResponse | None,
        ProviderErrorCategory | None,
        HistoricalFetchResult | None,
    ]:
        if contract_failure:
            return (
                None,
                None,
                self._attempt_failure(
                    attempt, HistoricalFetchCode.PROVIDER_CONTRACT, None
                ),
            )
        if transport_category is not None:
            return None, transport_category, None
        if not self._valid_response(response):
            return (
                None,
                None,
                self._attempt_failure(
                    attempt, HistoricalFetchCode.PROVIDER_CONTRACT, None
                ),
            )
        typed_response = cast(HistoricalResponse, response)
        category = self._response_category(typed_response)
        if category is None and not self._valid_success_response(typed_response):
            return (
                None,
                None,
                self._attempt_failure(
                    attempt, HistoricalFetchCode.PROVIDER_CONTRACT, None
                ),
            )
        return typed_response, category, None

    def _admit(
        self, consumed_wait: timedelta, attempt: int
    ) -> tuple[timedelta, HistoricalFetchResult | None]:
        try:
            waited = self._limiter.acquire(
                self._cancellation,
                self._remaining(consumed_wait),
            )
            return self._charge(consumed_wait, waited), None
        except CancellationRequested:
            return consumed_wait, self._cancelled(attempt - 1)
        except RetryWaitBoundExceeded:
            return consumed_wait, self._failure(
                HistoricalFetchCode.RETRY_WAIT_BOUND_EXCEEDED, attempt - 1
            )
        except Exception:
            return consumed_wait, self._failure(
                HistoricalFetchCode.PROVIDER_CONTRACT, attempt - 1
            )

    def _send(
        self, request: HistoricalRequest
    ) -> tuple[object | None, ProviderErrorCategory | None, bool]:
        try:
            response = self._session.fetch(request)
        except HttpTransportError as error:
            category = error.category
            del error
            return None, category, False
        except (HttpResponseBodyTooLarge, HttpResponseHeadersInvalid, ValueError):
            return None, None, True
        except Exception:
            return None, None, True
        return response, None, False

    def _wait_before_retry(
        self,
        response: HistoricalResponse | None,
        attempt: int,
        status_class: str | None,
        consumed_wait: timedelta,
    ) -> tuple[timedelta, HistoricalFetchResult | None]:
        retry_after_value, effective_delay, delay_failure = self._retry_delays(
            response, attempt, status_class, consumed_wait
        )
        if delay_failure is not None:
            return consumed_wait, delay_failure
        if self._is_cancelled():
            return consumed_wait, self._cancelled(attempt)
        deferral_wait = timedelta(0)
        if retry_after_value is not None:
            consumed_wait, deferral_wait, deferral_failure = self._publish_deferral(
                retry_after_value, consumed_wait, attempt, status_class
            )
            if deferral_failure is not None:
                return consumed_wait, deferral_failure
            if self._is_cancelled():
                return consumed_wait, self._cancelled(attempt)
        remaining_effective = max(effective_delay - deferral_wait, timedelta(0))
        return self._sleep_retry(
            remaining_effective, consumed_wait, attempt, status_class
        )

    def _retry_delays(
        self,
        response: HistoricalResponse | None,
        attempt: int,
        status_class: str | None,
        consumed_wait: timedelta,
    ) -> tuple[timedelta | None, timedelta, HistoricalFetchResult | None]:
        retry_after, diagnostic = self._retry_after(response, attempt, status_class)
        if diagnostic is not None:
            event_failure = self._emit(attempt, diagnostic, status_class)
            if event_failure is not None:
                return None, timedelta(0), event_failure
        if retry_after is _CLOCK_FAILURE:
            return (
                None,
                timedelta(0),
                self._failure(
                    HistoricalFetchCode.PROVIDER_CONTRACT, attempt, status_class
                ),
            )
        if retry_after is _RETRY_AFTER_TOO_LARGE:
            return (
                None,
                timedelta(0),
                self._failure(
                    HistoricalFetchCode.RETRY_WAIT_BOUND_EXCEEDED, attempt, status_class
                ),
            )
        retry_after_value = (
            None
            if retry_after is _INVALID_RETRY_AFTER
            else cast(timedelta, retry_after)
        )
        try:
            local_delay = self._local_delay(attempt)
        except Exception:
            return (
                None,
                timedelta(0),
                self._failure(
                    HistoricalFetchCode.PROVIDER_CONTRACT, attempt, status_class
                ),
            )
        effective_delay = max(local_delay, retry_after_value or timedelta(0))
        total_wait = consumed_wait + effective_delay
        if total_wait > self._retry_policy.max_total_wait:
            return (
                None,
                timedelta(0),
                self._failure(
                    HistoricalFetchCode.RETRY_WAIT_BOUND_EXCEEDED, attempt, status_class
                ),
            )
        return retry_after_value, effective_delay, None

    def _sleep_retry(
        self,
        effective_delay: timedelta,
        consumed_wait: timedelta,
        attempt: int,
        status_class: str | None,
    ) -> tuple[timedelta, HistoricalFetchResult | None]:
        if effective_delay == timedelta(0):
            return consumed_wait, None
        try:
            consumed_wait = self._charge(consumed_wait, effective_delay)
            self._sleeper.sleep(effective_delay, self._cancellation)
        except RetryWaitBoundExceeded:
            return consumed_wait, self._failure(
                HistoricalFetchCode.RETRY_WAIT_BOUND_EXCEEDED, attempt, status_class
            )
        except CancellationRequested:
            return consumed_wait, self._cancelled(attempt)
        except Exception:
            return consumed_wait, self._failure(
                HistoricalFetchCode.PROVIDER_CONTRACT, attempt, status_class
            )
        if self._is_cancelled():
            return consumed_wait, self._cancelled(attempt)
        return consumed_wait, None

    def _publish_deferral(
        self,
        delay: timedelta,
        consumed_wait: timedelta,
        attempt: int,
        status_class: str | None,
    ) -> tuple[timedelta, timedelta, HistoricalFetchResult | None]:
        try:
            defer = self._limiter.defer_for
            try:
                parameters = signature(defer).parameters.values()
                supports_cancellation = any(
                    parameter.name == "cancellation"
                    or parameter.kind is Parameter.VAR_KEYWORD
                    for parameter in parameters
                )
            except (TypeError, ValueError):
                supports_cancellation = True
            if supports_cancellation:
                waited = self._limiter.defer_for(
                    delay, self._remaining(consumed_wait), self._cancellation
                )
            else:
                # Existing injected test and integration limiters remain valid;
                # production limiters receive the cancellation signal above.
                waited = self._limiter.defer_for(delay, self._remaining(consumed_wait))
            actual = timedelta(0) if waited is None else waited
            return (
                self._charge(consumed_wait, actual),
                actual,
                None,
            )
        except CancellationRequested:
            return consumed_wait, timedelta(0), self._cancelled(attempt)
        except RetryWaitBoundExceeded:
            return (
                consumed_wait,
                timedelta(0),
                self._failure(
                    HistoricalFetchCode.RETRY_WAIT_BOUND_EXCEEDED, attempt, status_class
                ),
            )
        except Exception:
            return (
                consumed_wait,
                timedelta(0),
                self._failure(
                    HistoricalFetchCode.PROVIDER_CONTRACT, attempt, status_class
                ),
            )

    def _retry_after(
        self, response: object, attempt: int, status_class: str | None
    ) -> tuple[object, str | None]:
        if (
            type(response) is not HistoricalResponse
            or type(response.headers) is not HttpResponseHeaders
        ):
            return None, None
        values = response.headers.get_all("Retry-After")
        if not values:
            return None, None
        if len(values) != 1:
            return _INVALID_RETRY_AFTER, "retry_after_ambiguous"
        value = values[0]
        now = self._clock_now()
        if now is None:
            return _CLOCK_FAILURE, None
        delay = _parse_retry_after(value, now)
        if delay is None:
            return _INVALID_RETRY_AFTER, "retry_after_invalid"
        if delay > self._retry_policy.max_retry_after:
            return _RETRY_AFTER_TOO_LARGE, "retry_after_oversized"
        return delay, None

    def _local_delay(self, attempt: int) -> timedelta:
        base = min(
            self._retry_policy.base_backoff * (2 ** (attempt - 1)),
            self._retry_policy.max_backoff,
        )
        half_seconds = base.total_seconds() / 2
        jitter = self._jitter.uniform(0.0, half_seconds)
        if type(jitter) not in (int, float) or jitter < 0 or jitter > half_seconds:
            raise ValueError("jitter source returned an invalid value")
        return timedelta(seconds=half_seconds + float(jitter))

    def _remaining(self, consumed: timedelta) -> timedelta:
        return self._retry_policy.max_total_wait - consumed

    def _charge(self, consumed: timedelta, waited: timedelta | None) -> timedelta:
        actual = timedelta(0) if waited is None else waited
        if type(actual) is not timedelta or actual < timedelta(0):
            raise RetryWaitBoundExceeded
        updated = consumed + actual
        if updated > self._retry_policy.max_total_wait:
            raise RetryWaitBoundExceeded
        self._consumed_wait = updated
        return updated

    def _attempt_failure(
        self, attempt: int, code: HistoricalFetchCode, status_class: str | None
    ) -> HistoricalFetchResult:
        event_failure = self._emit(attempt, code.lower(), status_class)
        if event_failure is not None:
            return event_failure
        return self._failure(code, attempt, status_class)

    def _failure(
        self,
        code: HistoricalFetchCode,
        attempts: int,
        status_class: str | None = None,
    ) -> HistoricalFetchResult:
        return HistoricalFetchResult(
            response=None,
            attempts=attempts,
            failure=HistoricalFetchFailure(code, attempts, status_class),
            wait_consumed=self._consumed_wait,
        )

    def _cancelled(self, attempts: int) -> HistoricalFetchResult:
        return self._failure(HistoricalFetchCode.CANCELLED, attempts)

    def _is_cancelled(self) -> bool:
        try:
            return self._cancellation.is_cancelled()
        except Exception:
            return True

    def _emit(
        self, attempt: int, category: str, status_class: str | None
    ) -> HistoricalFetchResult | None:
        sink = self._event_sink
        if sink is None:
            return None
        try:
            event = ProviderEvent(
                self._run_id,
                attempt,
                category,
                status_class,
                self._clock.now(),
            )
            sink(event)
        except Exception:
            return self._failure(HistoricalFetchCode.PROVIDER_CONTRACT, attempt)
        return None

    def _clock_now(self) -> datetime | None:
        try:
            return _utc_datetime(self._clock.now())
        except Exception:
            return None

    @staticmethod
    def _response_category(response: object) -> ProviderErrorCategory | None:
        if not HistoricalRequestExecutor._valid_response(response):
            return ProviderErrorCategory.CLIENT
        typed_response = cast(HistoricalResponse, response)
        return provider_error_category(typed_response.status_code)

    @staticmethod
    def _valid_response(response: object) -> bool:
        return (
            type(response) is HistoricalResponse
            and type(response.status_code) is int
            and 100 <= response.status_code <= 599
            and type(response.candles) is list
            and all(type(row) is list for row in response.candles)
            and type(response.headers) is HttpResponseHeaders
            and (
                response.error_category is None
                or type(response.error_category) is ProviderErrorCategory
            )
        )

    @staticmethod
    def _valid_success_response(response: object) -> bool:
        return _valid_success_response_payload(response)


_INVALID_RETRY_AFTER = object()
_CLOCK_FAILURE = object()
_RETRY_AFTER_TOO_LARGE = object()


def _parse_retry_after(value: str, now: datetime) -> timedelta | None:
    if _RETRY_AFTER_SECONDS.fullmatch(value):
        try:
            seconds = Decimal(value)
        except InvalidOperation:
            return None
        try:
            return timedelta(seconds=float(seconds))
        except (OverflowError, ValueError):
            return timedelta.max
    if len(value) != 29:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if value != parsed.strftime(_RETRY_AFTER_IMF):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    delay = parsed.astimezone(UTC) - now
    return max(delay, timedelta(0))


def _utc_datetime(value: object) -> datetime:
    if type(value) is not datetime:
        raise ValueError("clock must return an aware UTC datetime")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return an aware UTC datetime")
        return value.astimezone(UTC)
    except (OverflowError, TypeError, ValueError):
        raise ValueError("clock must return an aware UTC datetime") from None


def _safe_identifier(value: object) -> bool:
    return (
        type(value) is str
        and 0 < len(value) <= _MAX_PUBLIC_TEXT
        and value.isascii()
        and all(character.isalnum() or character in "-_.:" for character in value)
    )


def _safe_status_class(value: object) -> bool:
    return value is None or (type(value) is str and value in _EVENT_STATUS_CLASSES)


def _is_full_calendar_month(plan: PlannedInstrumentMonth) -> bool:
    return plan.from_date == date(plan.year, plan.month, 1) and plan.to_date == date(
        plan.year, plan.month, monthrange(plan.year, plan.month)[1]
    )


def _sanitize_run_id(value: object) -> str:
    if _safe_identifier(value):
        return cast(str, value)
    return "run"


def _status_class(response: object) -> str | None:
    if (
        type(response) is not HistoricalResponse
        or type(response.status_code) is not int
    ):
        return "transport"
    if 200 <= response.status_code < 300:
        return "2xx"
    if 400 <= response.status_code < 500:
        return "4xx"
    if 500 <= response.status_code < 600:
        return "5xx"
    return "other"


def _failure_code(
    category: ProviderErrorCategory | None, retryable: bool
) -> HistoricalFetchCode:
    if retryable:
        return HistoricalFetchCode.PROVIDER_RETRYABLE
    if category is ProviderErrorCategory.AUTHENTICATION:
        return HistoricalFetchCode.AUTHENTICATION_FAILED
    if category is ProviderErrorCategory.AUTHORIZATION:
        return HistoricalFetchCode.AUTHORIZATION_FAILED
    return HistoricalFetchCode.PROVIDER_CLIENT
