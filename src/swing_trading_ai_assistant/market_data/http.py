"""Small injectable HTTP boundary used by provider adapters."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from http.client import HTTPMessage
from types import MappingProxyType
from typing import IO, Any, NoReturn, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import SplitResult, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DEFAULT_MAX_HISTORICAL_RESPONSE_BYTES = 1_000_000
DEFAULT_USER_AGENT = "SwingTradingAIAssistant/0.1"


def _empty_headers() -> Mapping[str, str]:
    return {}


class ProviderErrorCategory(StrEnum):
    """Stable categories callers can use for retry and diagnostic policy."""

    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    CLIENT = "client"
    RATE_LIMITED = "rate_limited"
    SERVER = "server"
    TIMEOUT = "timeout"
    NETWORK = "network"


def provider_error_category(status_code: int) -> ProviderErrorCategory | None:
    """Classify an HTTP status without inspecting an untrusted error body."""
    if 200 <= status_code < 300:
        return None
    if status_code == 401:
        return ProviderErrorCategory.AUTHENTICATION
    if status_code == 403:
        return ProviderErrorCategory.AUTHORIZATION
    if status_code == 408:
        return ProviderErrorCategory.TIMEOUT
    if status_code == 429:
        return ProviderErrorCategory.RATE_LIMITED
    if 500 <= status_code < 600:
        return ProviderErrorCategory.SERVER
    return ProviderErrorCategory.CLIENT


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=_empty_headers)
    error_category: ProviderErrorCategory | None = None

    def __post_init__(self) -> None:
        if self.status_code < 100 or self.status_code > 599:
            raise ValueError("status_code must be an HTTP status code")
        # Keep provider headers needed for retry and correlation, while preventing
        # a caller from changing the observed response later.
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))
        if self.error_category is None:
            object.__setattr__(
                self, "error_category", provider_error_category(self.status_code)
            )


class HttpTransport(Protocol):
    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        """Return status, bounded raw body, and response headers for an HTTP GET."""
        ...


class HttpTransportError(RuntimeError):
    """Network transport failed before an HTTP response was received."""

    def __init__(self, category: ProviderErrorCategory) -> None:
        self.category = category
        super().__init__(f"market-data provider transport failed: {category.value}")


class HttpResponseBodyTooLarge(RuntimeError):
    """A provider response exceeded the configured safe in-memory limit."""


_BODY_TOO_LARGE = object()


class SameOriginAuthorizationRedirectHandler(HTTPRedirectHandler):
    """Allow redirects without forwarding bearer credentials to another origin."""

    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> Request | None:
        redirected = super().redirect_request(
            req,
            cast(IO[bytes], fp),
            code,
            msg,
            cast(HTTPMessage, headers),
            newurl,
        )
        if redirected is not None and not _same_origin(req.full_url, newurl):
            for name in ("Authorization", "authorization"):
                redirected.headers.pop(name, None)
                redirected.unredirected_hdrs.pop(name, None)
        return redirected


def _same_origin(source: str, target: str) -> bool:
    source_parts = urlsplit(source)
    target_parts = urlsplit(target)
    return _origin(source_parts) == _origin(target_parts)


def _origin(parts: SplitResult) -> tuple[str, str, int | None]:
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    port = parts.port
    default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return scheme, hostname, port or default_port


# urllib exposes several different response classes. Keep the unsafely typed
# standard-library edge here rather than leaking it into provider adapters.
Opener = Callable[..., Any]


class UrllibHttpTransport:
    """Standard-library transport with bounded duration, bodies, and redirects."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        max_body_bytes: int = DEFAULT_MAX_HISTORICAL_RESPONSE_BYTES,
        opener: Opener | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be positive")
        self._timeout_seconds = timeout_seconds
        self._max_body_bytes = max_body_bytes
        self._opener = (
            opener
            if opener is not None
            else build_opener(SameOriginAuthorizationRedirectHandler()).open
        )

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        # Provider adapters supply fixed HTTPS endpoints; this transport must
        # remain protocol-neutral for deterministic adapter tests.
        request_headers = dict(headers)
        if not any(name.lower() == "user-agent" for name in request_headers):
            request_headers["User-Agent"] = DEFAULT_USER_AGENT
        request = Request(  # noqa: S310
            url=url, headers=request_headers, method="GET"
        )
        outcome = _perform_bounded_get(
            self._opener,
            request,
            self._timeout_seconds,
            self._max_body_bytes,
        )
        if outcome is _BODY_TOO_LARGE:
            del headers, request_headers, request, self
            _raise_body_too_large()
        return cast(HttpResponse, outcome)


def _perform_bounded_get(
    opener: Opener,
    request: Request,
    timeout_seconds: float,
    max_body_bytes: int,
) -> HttpResponse | object:
    """Return a non-raising sentinel for oversized authenticated bodies."""
    try:
        with opener(request, timeout=timeout_seconds) as response:
            body = _read_bounded(response, max_body_bytes)
            if body is None:
                return _BODY_TOO_LARGE
            return HttpResponse(
                status_code=response.status,
                body=body,
                headers=_headers(response.headers),
            )
    except HTTPError as exc:
        body = _read_bounded(exc, max_body_bytes)
        if body is None:
            return _BODY_TOO_LARGE
        return HttpResponse(
            status_code=exc.code,
            body=body,
            headers=_headers(exc.headers),
        )
    except TimeoutError as exc:
        raise HttpTransportError(ProviderErrorCategory.TIMEOUT) from exc
    except URLError as exc:
        category = (
            ProviderErrorCategory.TIMEOUT
            if isinstance(exc.reason, TimeoutError)
            else ProviderErrorCategory.NETWORK
        )
        raise HttpTransportError(category) from exc


def _read_bounded(response: Any, max_body_bytes: int) -> bytes | None:
    body = response.read(max_body_bytes + 1)
    if len(body) > max_body_bytes:
        return None
    return body


def _raise_body_too_large() -> NoReturn:
    raise HttpResponseBodyTooLarge(
        "market-data provider response exceeded limit"
    ) from None


def _headers(headers: Any) -> Mapping[str, str]:
    items = getattr(headers, "items", None)
    if not callable(items):
        return {}
    header_items = cast(Iterable[tuple[object, object]], items())
    return {str(name): str(value) for name, value in header_items}
