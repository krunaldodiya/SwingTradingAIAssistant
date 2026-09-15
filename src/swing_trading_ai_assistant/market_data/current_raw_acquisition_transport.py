"""Strict, status-first transport used only by #188 acquisition.

The older generic transport intentionally returns buffered bodies for legacy
callers.  This narrow transport never reads a non-success body and never follows
redirects, so auth/rate failures cannot be hidden by body parsing or body limits.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


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


def get_strict_current_raw_v1(
    url: object,
    *,
    headers: Mapping[str, str],
    timeout_seconds: float,
    deadline: datetime,
    now: Callable[[], datetime],
    maximum_body_bytes: int = 1_000_000,
) -> StrictCurrentRawResponseV1:
    """Perform one bounded GET; caller owns retry and effect sequencing."""
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("strict current raw URL is invalid")
    if timeout_seconds <= 0 or maximum_body_bytes < 0:
        raise ValueError("strict current raw limits are invalid")
    if now() >= deadline:
        raise CurrentRawDeadlineError("current raw deadline exceeded")
    request = Request(  # noqa: S310 -- exact https scheme is admitted above
        url, headers=dict(headers), method="GET"
    )
    opener = build_opener(_NoRedirect())
    try:
        response = opener.open(request, timeout=timeout_seconds)
    except HTTPError as error:
        _raise_status(error.code)
        raise CurrentRawProviderResponseError(
            "current raw provider refused request"
        ) from None
    except URLError as error:
        raise CurrentRawProviderResponseError(
            "current raw provider unavailable"
        ) from error
    try:
        status = response.getcode()
        final_url = response.geturl()
        if status != 200:
            _raise_status(status)
            raise CurrentRawProviderResponseError(
                "current raw provider refused request"
            )
        if final_url != url:
            raise CurrentRawProviderResponseError("current raw redirect refused")
        header_items = tuple((name, value) for name, value in response.headers.items())
        body = response.read(maximum_body_bytes + 1)
        if len(body) > maximum_body_bytes:
            raise CurrentRawProviderResponseError("current raw response too large")
        if now() > deadline:
            raise CurrentRawDeadlineError("current raw deadline exceeded")
        return StrictCurrentRawResponseV1(status, final_url, header_items, body)
    finally:
        response.close()


def _raise_status(status: int) -> None:
    if status == 401:
        raise CurrentRawAuthenticationError("current raw authentication failed")
    if status == 403:
        raise CurrentRawAuthorizationError("current raw authorization failed")
    if status == 429:
        raise CurrentRawRateLimitedError("current raw rate limited")
