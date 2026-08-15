"""Isolated stdlib-only fixed candidate-artifact probe worker."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import queue
import signal
import socket
import ssl
import sys
import threading
import time
from typing import TypeAlias, cast
from urllib.parse import SplitResult, urlsplit

CANDIDATE_ARTIFACT_URL = (
    "https://www.niftyindices.com/Press_Release/ind_prs21022025.pdf"
)
PROBE_METHOD = "GET"
PROBE_DEADLINE_SECONDS = 30
MAX_TRANSPORT_WAIT_SECONDS = 5
MAX_BODY_BYTES = 1_048_576
MAX_BODY_READ_BYTES = MAX_BODY_BYTES + 1
_NORMALIZED_MEDIA_TYPE = "application/pdf"
_MAX_CONTENT_TYPE_BYTES = 256
_MAX_OUTPUT_BYTES = 4 * 1024
_PDF_PREFIX = b"%PDF-"
_USER_AGENT = "SwingTradingAIAssistant/0.1"
_MARKER = "__capability_probe_worker_v1__"
_SocketAddress: TypeAlias = tuple[str, int] | tuple[str, int, int, int]
_AddressInfo: TypeAlias = tuple[
    socket.AddressFamily,
    socket.SocketKind,
    int,
    str,
    _SocketAddress,
]
_ResolutionResult: TypeAlias = tuple[_AddressInfo, ...] | Exception


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _remaining_wait(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("capability probe deadline exceeded")
    return min(MAX_TRANSPORT_WAIT_SECONDS, remaining)


def _normalize_pdf_media_type(values: tuple[bytes, ...]) -> str | None:
    if len(values) != 1:
        return None
    value = values[0]
    if not 0 < len(value) <= _MAX_CONTENT_TYPE_BYTES:
        return None
    if any(byte != 0x09 and not 0x20 <= byte <= 0x7E for byte in value):
        return None
    essence = value.split(b";", 1)[0].strip(b" \t").lower()
    if essence != b"application/pdf":
        return None
    return _NORMALIZED_MEDIA_TYPE


def _normalize_address_info(raw: tuple[object, ...]) -> _AddressInfo | None:
    if len(raw) != 5:
        return None
    family_value, kind_value, protocol, canonical_name, socket_address = raw
    if (
        not isinstance(family_value, int)
        or isinstance(family_value, bool)
        or not isinstance(kind_value, int)
        or isinstance(kind_value, bool)
        or type(protocol) is not int
        or type(canonical_name) is not str
        or type(socket_address) is not tuple
    ):
        return None
    address_values = cast(tuple[object, ...], socket_address)
    try:
        family = socket.AddressFamily(family_value)
        kind = socket.SocketKind(kind_value)
    except ValueError:
        return None
    if family is socket.AddressFamily.AF_INET:
        if len(address_values) != 2:
            return None
        address_host, address_port = address_values
        if type(address_host) is not str or type(address_port) is not int:
            return None
        address: _SocketAddress = (address_host, address_port)
    elif family is socket.AddressFamily.AF_INET6:
        if len(address_values) != 4:
            return None
        address_host, address_port, flow_info, scope_id = address_values
        if (
            type(address_host) is not str
            or type(address_port) is not int
            or type(flow_info) is not int
            or type(scope_id) is not int
        ):
            return None
        address = (address_host, address_port, flow_info, scope_id)
    else:
        return None
    return family, kind, protocol, canonical_name, address


def _resolve_addresses(
    host: str, port: int, deadline: float
) -> tuple[_AddressInfo, ...]:
    results: queue.Queue[_ResolutionResult] = queue.Queue(maxsize=1)

    def resolve() -> None:
        try:
            addresses: list[_AddressInfo] = []
            for raw in socket.getaddrinfo(
                host,
                port,
                type=socket.SOCK_STREAM,
            ):
                address = _normalize_address_info(cast(tuple[object, ...], raw))
                if address is not None:
                    addresses.append(address)
            result: _ResolutionResult = tuple(addresses)
        except Exception as error:
            result = error
        results.put(result)

    threading.Thread(
        target=resolve,
        name="capability-probe-dns",
        daemon=True,
    ).start()
    try:
        result = results.get(timeout=_remaining_wait(deadline))
    except queue.Empty as error:
        raise TimeoutError("capability probe DNS deadline exceeded") from error
    if isinstance(result, Exception):
        raise result
    if not result:
        raise OSError("capability probe DNS resolution returned no addresses")
    return result


def _open_connection(url: SplitResult, deadline: float) -> http.client.HTTPConnection:
    host = url.hostname
    if host is None:
        raise ValueError("invalid transport URL")
    port = url.port or (443 if url.scheme == "https" else 80)
    if url.scheme not in {"http", "https"}:
        raise ValueError("unsupported transport scheme")
    connect_deadline = min(
        deadline,
        time.monotonic() + MAX_TRANSPORT_WAIT_SECONDS,
    )
    family, socket_type, protocol, _, socket_address = _resolve_addresses(
        host,
        port,
        connect_deadline,
    )[0]
    connected = socket.socket(family, socket_type, protocol)
    try:
        connected.settimeout(_remaining_wait(connect_deadline))
        connected.connect(socket_address)
        if url.scheme == "https":
            connected.settimeout(_remaining_wait(connect_deadline))
            connected = ssl.create_default_context().wrap_socket(
                connected,
                server_hostname=host,
            )
            connection: http.client.HTTPConnection = http.client.HTTPSConnection(
                host,
                port,
                timeout=_remaining_wait(deadline),
            )
        else:
            connection = http.client.HTTPConnection(
                host,
                port,
                timeout=_remaining_wait(deadline),
            )
        connection.sock = connected
        return connection
    except OSError:
        connected.close()
        raise


def _content_type_values(response: http.client.HTTPResponse) -> tuple[bytes, ...]:
    values: list[bytes] = []
    for name, value in response.getheaders():
        if name.lower() == "content-type":
            try:
                values.append(value.encode("latin-1"))
            except UnicodeEncodeError:
                return ()
    return tuple(values)


def _probe(deadline: float) -> dict[str, object]:
    _remaining_wait(deadline)
    url = urlsplit(CANDIDATE_ARTIFACT_URL)
    target = url.path or "/"
    connection = _open_connection(url, deadline)
    try:
        connection.putrequest(PROBE_METHOD, target, skip_accept_encoding=True)
        connection.putheader("Accept", _NORMALIZED_MEDIA_TYPE)
        connection.putheader("User-Agent", _USER_AGENT)
        connection.endheaders()
        if connection.sock is None:
            raise http.client.HTTPException("transport closed")
        connection.sock.settimeout(_remaining_wait(deadline))
        response = connection.getresponse()
        status = response.status
        if not 100 <= status <= 599:
            raise http.client.HTTPException("invalid status")
        if status != 200:
            return {"failure": "HTTP_STATUS_REJECTED", "http_status": status}
        media = _normalize_pdf_media_type(_content_type_values(response))
        if media is None:
            return {"failure": "CONTENT_TYPE_REJECTED", "http_status": 200}
        body = response.read(MAX_BODY_READ_BYTES)
        body_bytes = len(body)
        if body_bytes == 0:
            return {
                "failure": "BODY_EMPTY",
                "http_status": 200,
                "normalized_media_type": media,
                "body_bytes_observed": 0,
                "candidate_prefix_matched": False,
            }
        if body_bytes > MAX_BODY_BYTES:
            return {
                "failure": "BODY_TOO_LARGE",
                "http_status": 200,
                "normalized_media_type": media,
                "body_bytes_observed": MAX_BODY_READ_BYTES,
            }
        if not body.startswith(_PDF_PREFIX):
            return {
                "failure": "CANDIDATE_PREFIX_REJECTED",
                "http_status": 200,
                "normalized_media_type": media,
                "body_bytes_observed": body_bytes,
                "candidate_prefix_matched": False,
            }
        return {
            "failure": None,
            "http_status": 200,
            "normalized_media_type": media,
            "body_bytes_observed": body_bytes,
            "candidate_body_sha256": hashlib.sha256(body).hexdigest(),
            "candidate_prefix_matched": True,
        }
    finally:
        connection.close()


def main(arguments: list[str]) -> int:
    if len(arguments) != 2 or arguments[0] != _MARKER:
        return 2
    deadline: float | None = None
    try:
        deadline = float(arguments[1])
        remaining = deadline - time.monotonic()
        if not 0 < remaining <= PROBE_DEADLINE_SECONDS:
            return 2
        observation = _probe(deadline)
    except TimeoutError:
        if deadline is not None and time.monotonic() >= deadline:
            while True:
                signal.pause()
        observation = {"failure": "TRANSPORT_FAILURE"}
    except Exception:
        observation = {"failure": "TRANSPORT_FAILURE"}
    payload = _canonical(observation)
    if len(payload) > _MAX_OUTPUT_BYTES:
        return 2
    os.write(1, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
