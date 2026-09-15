"""Strict, status-first transport used only by #188 acquisition.

This module deliberately does not reuse the legacy buffered HTTP adapter.  A
non-success status is classified before a body is touched; successful payloads
are accepted only from an exact, preplanned Upstox HTTPS endpoint.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

_MAX_HEADERS = 32
_MAX_HEADER_BYTES = 8 * 1024
_MAX_BODY_BYTES = 1_000_000
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


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> Request | None:
        return None


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
) -> StrictCurrentRawResponseV1:
    """Perform one exact, bounded GET with status-first failure handling."""
    if (
        not _planned_upstox_url(url)
        or type(deadline) is not datetime
        or deadline.tzinfo is not UTC
        or not callable(now)
        or type(timeout_seconds) not in (int, float)
        or type(maximum_body_bytes) is not int
        or not 0 <= maximum_body_bytes <= _MAX_BODY_BYTES
        or not _valid_headers(headers)
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
    except URLError as error:
        raise CurrentRawProviderResponseError(
            "current raw provider unavailable"
        ) from error

    primary: BaseException | None = None
    try:
        status = response.getcode()
        if type(status) is not int:
            raise CurrentRawProviderResponseError("current raw status is invalid")
        if status != 200:
            _raise_status(status)
            raise CurrentRawProviderResponseError(
                "current raw provider refused request"
            )
        final_url = response.geturl()
        if final_url != trusted_url:
            raise CurrentRawProviderResponseError("current raw redirect refused")
        header_items = tuple((name, value) for name, value in response.headers.items())
        if not _valid_response_headers(header_items):
            raise CurrentRawProviderResponseError(
                "current raw response headers invalid"
            )
        body = response.read(maximum_body_bytes + 1)
        if type(body) is not bytes or len(body) > maximum_body_bytes:
            raise CurrentRawProviderResponseError("current raw response too large")
        completed = now()
        if type(completed) is not datetime or completed.tzinfo is not UTC:
            raise ValueError("strict current raw clock is invalid")
        if completed > deadline:
            raise CurrentRawDeadlineError("current raw deadline exceeded")
        return StrictCurrentRawResponseV1(status, final_url, header_items, body)
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            response.close()
        except BaseException:
            if primary is None:
                raise


def _planned_upstox_url(value: object) -> bool:
    if type(value) is not str or len(value) > 512:
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.netloc == _UPSTOX_HOST
        and not parsed.query
        and not parsed.fragment
        and parsed.path.startswith("/v2/")
    )


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


def _valid_response_headers(headers: tuple[tuple[object, object], ...]) -> bool:
    if len(headers) > _MAX_HEADERS:
        return False
    total = 0
    content_type: str | None = None
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
    return total <= _MAX_HEADER_BYTES and content_type in {
        "application/json",
        "application/json;charset=utf-8",
    }


def _raise_status(status: int) -> None:
    if status == 401:
        raise CurrentRawAuthenticationError("current raw authentication failed")
    if status == 403:
        raise CurrentRawAuthorizationError("current raw authorization failed")
    if status == 429:
        raise CurrentRawRateLimitedError("current raw rate limited")
