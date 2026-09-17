"""Strict, status-first transport used only by #188 acquisition.

This module deliberately does not reuse the legacy buffered HTTP adapter.  A
non-success status is classified before a body is touched; successful payloads
are accepted only from an exact, preplanned Upstox HTTPS endpoint.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import IncompleteRead
from typing import Literal, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .http import HttpResponse, HttpResponseHeaders
from .instruments import UPSTOX_NSE_INSTRUMENTS_URL

_MAX_HEADERS = 32
_MAX_HEADER_BYTES = 8 * 1024
_MAX_BODY_BYTES = 1_000_000
_MAX_MAPPING_BODY_BYTES = 4_000_000
_MAX_ACTION_BODY_BYTES = 1_048_576
_UPSTOX_HOST = "api.upstox.com"


class CurrentRawTransportError(RuntimeError):
    """Base typed strict-transport failure."""


class CurrentRawAuthenticationError(CurrentRawTransportError):
    pass


class CurrentRawAuthorizationError(CurrentRawTransportError):
    pass


class CurrentRawRateLimitedError(CurrentRawTransportError):
    pass


class CurrentRawProviderResponseError(CurrentRawTransportError):
    pass


class CurrentRawDeadlineError(CurrentRawTransportError):
    pass


@dataclass(frozen=True, slots=True)
class StrictCurrentRawOperationV1:
    """One immutable, bounded endpoint permission for an acquisition slot."""

    kind: Literal["MAPPING", "HISTORICAL", "INTRADAY", "ACTION"]
    expected_url: str
    maximum_body_bytes: int

    def __post_init__(self) -> None:
        if (
            self.kind not in {"MAPPING", "HISTORICAL", "INTRADAY", "ACTION"}
            or not _valid_operation_url(self.kind, self.expected_url)
            or not _valid_body_limit(self.expected_url, self.maximum_body_bytes)
            or (
                self.kind == "MAPPING"
                and (
                    self.expected_url != UPSTOX_NSE_INSTRUMENTS_URL
                    or self.maximum_body_bytes != _MAX_MAPPING_BODY_BYTES
                )
            )
            or (
                self.kind in {"HISTORICAL", "INTRADAY"}
                and self.maximum_body_bytes != _MAX_BODY_BYTES
            )
            or (
                self.kind == "ACTION"
                and self.maximum_body_bytes != _MAX_ACTION_BODY_BYTES
            )
        ):
            raise ValueError("strict current raw operation is invalid")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> Request | None:
        return None


class StrictCurrentRawHttpTransportV1:
    """One-operation adapter from the strict edge to existing provider clients.

    It intentionally holds only deadline/clock policy; provider clients retain
    their own fixed URL and response parsers.  Mapping requests are always
    credential-free, while raw/action clients may carry their already-admitted
    bearer header.
    """

    def __init__(
        self,
        *,
        deadline: datetime,
        now: Callable[[], datetime],
        operation: StrictCurrentRawOperationV1 | None = None,
        before_open: Callable[[], None] | None = None,
        response_completed: Callable[[], None] | None = None,
        terminal_response: Callable[[], None] | None = None,
    ) -> None:
        if (
            type(deadline) is not datetime
            or deadline.tzinfo is not UTC
            or not callable(now)
            or (
                operation is not None
                and type(operation) is not StrictCurrentRawOperationV1
            )
            or (before_open is not None and not callable(before_open))
            or (response_completed is not None and not callable(response_completed))
            or (terminal_response is not None and not callable(terminal_response))
        ):
            raise ValueError("strict current raw transport is invalid")
        self._deadline = deadline
        self._now = now
        self._operation = operation
        self._before_open = before_open
        self._response_completed = response_completed
        self._terminal_response = terminal_response

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        operation = self._operation
        if operation is not None and url != operation.expected_url:
            raise CurrentRawProviderResponseError("current raw operation URL refused")
        response = get_strict_current_raw_v1(
            url,
            headers=headers,
            timeout_seconds=30.0,
            deadline=self._deadline,
            now=self._now,
            maximum_body_bytes=(
                operation.maximum_body_bytes
                if operation is not None
                else (
                    _MAX_MAPPING_BODY_BYTES
                    if url == UPSTOX_NSE_INSTRUMENTS_URL
                    else _MAX_BODY_BYTES
                )
            ),
            before_open=self._before_open,
            response_completed=self._response_completed,
            terminal_response=self._terminal_response,
        )
        return HttpResponse(
            status_code=response.status_code,
            body=response.body,
            headers=HttpResponseHeaders.from_items(response.headers),
            request_url=response.url,
            response_url=response.url,
        )


@dataclass(frozen=True, slots=True)
class StrictCurrentRawResponseV1:
    status_code: int
    url: str
    headers: tuple[tuple[str, str], ...]
    body: bytes


def get_strict_current_raw_v1(  # noqa: C901 -- ordered status-first trust boundary
    url: object,
    *,
    headers: Mapping[str, str],
    timeout_seconds: float,
    deadline: datetime,
    now: Callable[[], datetime],
    maximum_body_bytes: int = _MAX_BODY_BYTES,
    before_open: Callable[[], None] | None = None,
    response_completed: Callable[[], None] | None = None,
    terminal_response: Callable[[], None] | None = None,
) -> StrictCurrentRawResponseV1:
    """Perform one exact, bounded GET with status-first failure handling."""
    if (
        not _planned_upstox_url(url)
        or type(deadline) is not datetime
        or deadline.tzinfo is not UTC
        or not callable(now)
        or type(timeout_seconds) not in (int, float)
        or type(maximum_body_bytes) is not int
        or not _valid_body_limit(url, maximum_body_bytes)
        or not _valid_headers(headers)
        or (before_open is not None and not callable(before_open))
        or (response_completed is not None and not callable(response_completed))
        or (terminal_response is not None and not callable(terminal_response))
    ):
        raise ValueError("strict current raw request is invalid")
    current = now()
    if type(current) is not datetime or current.tzinfo is not UTC:
        raise ValueError("strict current raw clock is invalid")
    remaining = (deadline - current).total_seconds()
    if remaining <= 0:
        raise CurrentRawDeadlineError("current raw deadline exceeded")
    if timeout_seconds <= 0:
        raise ValueError("strict current raw timeout is invalid")
    trusted_url = cast(str, url)
    request = Request(  # noqa: S310 -- exact HTTPS Upstox URL admitted above
        trusted_url,
        headers=dict(headers),
        method="GET",  # type: ignore[arg-type]
    )
    opener = build_opener(_NoRedirect())
    if before_open is not None:
        before_open()
    try:
        response = opener.open(request, timeout=min(float(timeout_seconds), remaining))
    except HTTPError as error:
        try:
            _raise_status(error.code)
            raise CurrentRawProviderResponseError(
                "current raw provider refused request"
            )
        finally:
            # An HTTP error body must never be inspected.  Its close failure is
            # subordinate to the status classification.
            with suppress(BaseException):
                error.close()
    except (URLError, TimeoutError, ConnectionResetError, IncompleteRead) as error:
        raise CurrentRawProviderResponseError(
            "current raw provider unavailable"
        ) from error

    primary: BaseException | None = None
    try:
        status = response.getcode()
        if type(status) is not int:
            raise CurrentRawProviderResponseError("current raw status is invalid")
        if status != 200:
            if terminal_response is not None:
                terminal_response()
            _raise_status(status)
            raise CurrentRawProviderResponseError(
                "current raw provider refused request"
            )
        final_url = response.geturl()
        if final_url != trusted_url:
            raise CurrentRawProviderResponseError("current raw redirect refused")
        header_items = _bounded_response_headers(response.headers.items())
        if not _valid_response_headers(
            header_items, mapping=(trusted_url == UPSTOX_NSE_INSTRUMENTS_URL)
        ):
            raise CurrentRawProviderResponseError(
                "current raw response headers invalid"
            )
        try:
            body = response.read(maximum_body_bytes + 1)
        except (
            URLError,
            TimeoutError,
            ConnectionResetError,
            IncompleteRead,
            OSError,
        ) as error:
            raise CurrentRawProviderResponseError(
                "current raw response body unavailable"
            ) from error
        if type(body) is not bytes or len(body) > maximum_body_bytes:
            raise CurrentRawProviderResponseError("current raw response too large")
        if response_completed is not None:
            response_completed()
        completed = now()
        if type(completed) is not datetime or completed.tzinfo is not UTC:
            raise ValueError("strict current raw clock is invalid")
        if completed > deadline:
            raise CurrentRawDeadlineError("current raw deadline exceeded")
        return StrictCurrentRawResponseV1(
            status, final_url, cast(tuple[tuple[str, str], ...], header_items), body
        )
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            response.close()
        except BaseException:
            if primary is None:
                raise


def _valid_operation_url(kind: str, value: object) -> bool:
    if not _planned_upstox_url(value):
        return False
    if kind == "MAPPING":
        return value == UPSTOX_NSE_INSTRUMENTS_URL
    path = urlsplit(cast(str, value)).path
    if kind == "HISTORICAL":
        return path.startswith("/v3/historical-candle/") and not path.startswith(
            "/v3/historical-candle/intraday/"
        )
    if kind == "INTRADAY":
        return path.startswith("/v3/historical-candle/intraday/")
    return path.startswith("/v2/fundamentals/") and path.endswith("/corporate-actions")


def _planned_upstox_url(value: object) -> bool:
    if type(value) is not str or len(value) > 512:
        return False
    parsed = urlsplit(value)
    if value == UPSTOX_NSE_INSTRUMENTS_URL:
        return True
    return (
        parsed.scheme == "https"
        and parsed.netloc == _UPSTOX_HOST
        and not parsed.query
        and not parsed.fragment
        and (parsed.path.startswith("/v2/") or parsed.path.startswith("/v3/"))
    )


def _valid_body_limit(url: object, maximum_body_bytes: int) -> bool:
    return (
        0
        <= maximum_body_bytes
        <= (
            _MAX_MAPPING_BODY_BYTES
            if url == UPSTOX_NSE_INSTRUMENTS_URL
            else _MAX_ACTION_BODY_BYTES
        )
    )


def _bounded_response_headers(value: object) -> tuple[tuple[object, object], ...]:
    if not isinstance(value, Iterable):
        return ()
    headers: list[tuple[object, object]] = []
    items = cast(Iterable[object], value)
    for item in items:
        if len(headers) >= _MAX_HEADERS or not isinstance(item, (tuple, list)):
            return ()
        pair = cast(tuple[object, ...] | list[object], item)
        if len(pair) != 2:
            return ()
        headers.append((pair[0], pair[1]))
    return tuple(headers)


def _valid_headers(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    headers = cast(Mapping[object, object], value)
    if len(headers) > _MAX_HEADERS:
        return False
    total = 0
    for name, item in headers.items():
        if (
            type(name) is not str
            or type(item) is not str
            or not name
            or not name.isascii()
            or not item.isascii()
            or "\n" in name
            or "\r" in name
            or "\n" in item
            or "\r" in item
        ):
            return False
        total += len(name) + len(item)
    return total <= _MAX_HEADER_BYTES


def _valid_response_headers(
    headers: tuple[tuple[object, object], ...], *, mapping: bool
) -> bool:
    if len(headers) > _MAX_HEADERS:
        return False
    total = 0
    content_type: str | None = None
    content_encoding: str | None = None
    for name, value in headers:
        if type(name) is not str or type(value) is not str or not name:
            return False
        if (
            not name.isascii()
            or not value.isascii()
            or "\n" in name
            or "\r" in name
            or "\n" in value
            or "\r" in value
        ):
            return False
        total += len(name) + len(value)
        if name.casefold() == "content-type":
            if content_type is not None:
                return False
            content_type = value.casefold().replace(" ", "")
        if name.casefold() == "content-encoding":
            if content_encoding is not None:
                return False
            content_encoding = value.casefold().replace(" ", "")
    allowed_content_types = {
        "application/json",
        "application/json;charset=utf-8",
    }
    if mapping:
        allowed_content_types.update({"application/gzip", "application/octet-stream"})
    return (
        total <= _MAX_HEADER_BYTES
        and content_type in allowed_content_types
        and content_encoding in {None, "identity"}
    )


def _raise_status(status: int) -> None:
    if status == 401:
        raise CurrentRawAuthenticationError("current raw authentication failed")
    if status == 403:
        raise CurrentRawAuthorizationError("current raw authorization failed")
    if status == 429:
        raise CurrentRawRateLimitedError("current raw rate limited")
