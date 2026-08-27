"""Small injectable HTTP boundary used by provider adapters."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from http.client import HTTPMessage
from typing import IO, Any, NoReturn, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import SplitResult, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DEFAULT_MAX_HISTORICAL_RESPONSE_BYTES = 1_000_000
DEFAULT_USER_AGENT = "SwingTradingAIAssistant/0.1"
MAX_RESPONSE_HEADER_FIELDS = 128
MAX_RESPONSE_HEADER_NAME_BYTES = 256
MAX_RESPONSE_HEADER_VALUE_BYTES = 4_096

_HTTP_TOKEN_CHARS = frozenset(
    "!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)


class HttpResponseHeadersInvalid(RuntimeError):
    """A response contained an invalid or oversized header structure."""

    def __init__(self) -> None:
        super().__init__("market-data provider response contained invalid headers")


@dataclass(frozen=True, slots=True)
class HttpResponseHeader:
    """One validated response field retained in its observed arrival position."""

    name: str
    value: str

    def __post_init__(self) -> None:
        if not _valid_header_name(self.name) or not _valid_header_value(self.value):
            raise HttpResponseHeadersInvalid


@dataclass(frozen=True, slots=True)
class HttpResponseHeaders:
    """Immutable, bounded, arrival-ordered response header fields."""

    fields: tuple[HttpResponseHeader, ...] = ()

    def __post_init__(self) -> None:
        fields = tuple(self.fields)
        if len(fields) > MAX_RESPONSE_HEADER_FIELDS or any(
            type(field) is not HttpResponseHeader for field in fields
        ):
            raise HttpResponseHeadersInvalid
        object.__setattr__(self, "fields", fields)

    @classmethod
    def from_items(cls, items: Iterable[object]) -> HttpResponseHeaders:
        fields: list[HttpResponseHeader] = []
        for item in items:
            if len(fields) >= MAX_RESPONSE_HEADER_FIELDS:
                raise HttpResponseHeadersInvalid
            if isinstance(item, HttpResponseHeader):
                fields.append(item)
                continue
            if not isinstance(item, (tuple, list)):
                raise HttpResponseHeadersInvalid
            item_values = cast(tuple[object, ...] | list[object], item)
            if (
                len(item_values) != 2
                or not isinstance(item_values[0], str)
                or not isinstance(item_values[1], str)
            ):
                raise HttpResponseHeadersInvalid
            fields.append(HttpResponseHeader(item_values[0], item_values[1]))
        return cls(tuple(fields))

    def __iter__(self) -> Iterator[HttpResponseHeader]:
        return iter(self.fields)

    def __len__(self) -> int:
        return len(self.fields)

    def __getitem__(
        self, index: int | slice
    ) -> HttpResponseHeader | tuple[HttpResponseHeader, ...]:
        return self.fields[index]

    def items(self) -> tuple[tuple[str, str], ...]:
        """Return all fields in arrival order, including duplicates."""
        return tuple((field.name, field.value) for field in self.fields)

    def get_all(self, name: str) -> tuple[str, ...]:
        """Return every value for a field name using case-insensitive matching."""
        folded_name = name.casefold()
        return tuple(
            field.value for field in self.fields if field.name.casefold() == folded_name
        )

    def get_single(self, name: str) -> str | None:
        """Return one value only when the case-insensitive field occurs once."""
        values = self.get_all(name)
        return values[0] if len(values) == 1 else None


def _empty_headers() -> HttpResponseHeaders:
    return HttpResponseHeaders()


def _valid_header_name(name: str) -> bool:
    try:
        name_bytes = name.encode("ascii")
    except UnicodeEncodeError:
        return False
    return (
        bool(name)
        and len(name_bytes) <= MAX_RESPONSE_HEADER_NAME_BYTES
        and all(character in _HTTP_TOKEN_CHARS for character in name)
    )


def _valid_header_value(value: str) -> bool:
    try:
        value_bytes = value.encode("latin-1")
    except UnicodeEncodeError:
        return False
    return len(value_bytes) <= MAX_RESPONSE_HEADER_VALUE_BYTES and all(
        (character == 0x09 or 0x20 <= character <= 0x7E or 0x80 <= character <= 0xFF)
        for character in value_bytes
    )


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
    headers: HttpResponseHeaders = field(default_factory=_empty_headers)
    error_category: ProviderErrorCategory | None = None
    request_url: str | None = None
    response_url: str | None = None

    def __post_init__(self) -> None:
        if self.status_code < 100 or self.status_code > 599:
            raise ValueError("status_code must be an HTTP status code")
        if type(self.headers) is not HttpResponseHeaders:
            raise TypeError("headers must be an HttpResponseHeaders collection")
        if (self.request_url is None) != (self.response_url is None) or any(
            type(value) is not str or not value
            for value in (self.request_url, self.response_url)
            if value is not None
        ):
            raise ValueError("response URL metadata must be complete")
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
_INVALID_RESPONSE_HEADERS = object()


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
        if outcome is _INVALID_RESPONSE_HEADERS:
            del headers, request_headers, request, self, url
            _raise_invalid_response_headers()
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
            headers = _headers(response.headers)
            if headers is _INVALID_RESPONSE_HEADERS:
                return _INVALID_RESPONSE_HEADERS
            raw_response_url: object = getattr(response, "url", request.full_url)
            response_url = (
                raw_response_url if type(raw_response_url) is str else request.full_url
            )
            return HttpResponse(
                status_code=response.status,
                body=body,
                headers=cast(HttpResponseHeaders, headers),
                request_url=request.full_url,
                response_url=response_url,
            )
    except HTTPError as exc:
        body = _read_bounded(exc, max_body_bytes)
        if body is None:
            return _BODY_TOO_LARGE
        headers = _headers(exc.headers)
        if headers is _INVALID_RESPONSE_HEADERS:
            return _INVALID_RESPONSE_HEADERS
        return HttpResponse(
            status_code=exc.code,
            body=body,
            headers=cast(HttpResponseHeaders, headers),
            request_url=request.full_url,
            response_url=exc.url,
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


def _raise_invalid_response_headers() -> NoReturn:
    raise HttpResponseHeadersInvalid from None


def _headers(headers: Any) -> HttpResponseHeaders | object:
    try:
        items = getattr(headers, "items", None)
        if not callable(items):
            return _INVALID_RESPONSE_HEADERS
        return HttpResponseHeaders.from_items(cast(Iterable[object], items()))
    except Exception:
        return _INVALID_RESPONSE_HEADERS
