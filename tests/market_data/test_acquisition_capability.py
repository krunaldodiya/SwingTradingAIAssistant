from __future__ import annotations

import ast
import hashlib
import http.client
import inspect
import json
import os
import socket
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import psutil
import pytest

from swing_trading_ai_assistant.market_data import (
    acquisition_capability,
    acquisition_capability_worker,
)

CANDIDATE_URL = "https://www.niftyindices.com/Press_Release/ind_prs21022025.pdf"
MAX_BODY_BYTES = 1_048_576
CONTENT_TYPE = (("Content-Type", "application/pdf"),)
PDF = b"%PDF-1.7\n"


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


@dataclass(frozen=True)
class _DescriptorStat:
    st_mode: int
    st_size: int
    st_dev: int = 1
    st_ino: int = 2
    st_mtime_ns: int = 3
    st_ctime_ns: int = 4


def _identity(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class _Response:
    status: int = 200
    headers: tuple[tuple[str, str], ...] = CONTENT_TYPE
    body: bytes = PDF
    close_without_response: bool = False
    slow_stream: bool = False


@dataclass
class _ObservedServer:
    url: str
    requests: list[dict[str, object]]
    request_started: threading.Event
    client_disconnected: threading.Event


@contextmanager
def _server(response: _Response) -> Iterator[_ObservedServer]:
    requests: list[dict[str, object]] = []
    request_started = threading.Event()
    client_disconnected = threading.Event()
    stop_stream = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            requests.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "headers": tuple(
                        (name.lower(), value) for name, value in self.headers.items()
                    ),
                    "content_length": self.headers.get("Content-Length"),
                }
            )
            request_started.set()
            if response.close_without_response:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                client_disconnected.set()
                return
            self.send_response(response.status)
            for name, value in response.headers:
                self.send_header(name, value)
            if not response.slow_stream:
                self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            if response.slow_stream:
                try:
                    self.wfile.write(PDF)
                    self.wfile.flush()
                    while not stop_stream.wait(0.02):
                        self.wfile.write(b"x")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    client_disconnected.set()
                return
            try:
                self.wfile.write(response.body)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                client_disconnected.set()

        def log_message(self, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield _ObservedServer(
            url=f"http://127.0.0.1:{server.server_port}/candidate",
            requests=requests,
            request_started=request_started,
            client_disconnected=client_disconnected,
        )
    finally:
        stop_stream.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _observe_local(
    server: _ObservedServer,
    monkeypatch: pytest.MonkeyPatch,
    *,
    deadline_seconds: float = 2.0,
) -> dict[str, object]:
    local = urlsplit(server.url)
    connection = http.client.HTTPConnection(
        local.hostname,
        local.port,
        timeout=deadline_seconds,
    )
    monkeypatch.setattr(
        acquisition_capability_worker,
        "_open_connection",
        lambda _fixed_url, _deadline: connection,
    )
    try:
        return acquisition_capability_worker._probe(time.monotonic() + deadline_seconds)
    except Exception:
        return {"failure": "TRANSPORT_FAILURE"}


def _receipt_value(receipt: object) -> dict[str, object]:
    raw = receipt.canonical_json_bytes()
    value = json.loads(raw)
    identity = value.pop("receipt_identity_sha256")
    assert identity == _identity(value)
    value["receipt_identity_sha256"] = identity
    assert raw == _canonical(value)
    forbidden_fragments = (
        "location",
        "exception",
        "traceback",
        "authorization",
        "cookie",
        "token",
        "secret",
        "127.0.0.1",
        "/candidate",
    )
    lowered = raw.decode("ascii").lower()
    assert not any(fragment in lowered for fragment in forbidden_fragments)
    return value


def _assert_fixed_receipt_envelope(receipt: object) -> None:
    assert receipt.receipt_version == "market-regime-layer-b-capability-probe@v1"
    assert receipt.request_url == CANDIDATE_URL
    assert receipt.method == "GET"
    assert receipt.attempt_count == 1
    assert receipt.network_call_count == 1
    assert receipt.concurrency == 1
    assert receipt.retry_count == 0
    assert receipt.redirect_count == 0
    assert receipt.credential_count == 0
    assert receipt.parser_invocation_count == 0
    assert receipt.filesystem_write_count == 0
    assert receipt.storage_write_count == 0
    assert receipt.request_started_at.tzinfo is not None
    assert receipt.request_started_at.utcoffset() == UTC.utcoffset(None)
    assert receipt.request_started_at <= receipt.response_completed_at
    assert 0 <= receipt.elapsed_microseconds <= 30_000_000
    _receipt_value(receipt)


def _assert_failed_row(
    receipt: object,
    failure: str,
    *,
    status: int | None,
    media: str | None,
    body_bytes: int | None,
    prefix: bool | None,
) -> None:
    assert receipt.outcome is acquisition_capability.CapabilityProbeOutcomeV1.FAILED
    assert receipt.failure is acquisition_capability.CapabilityProbeFailureV1(failure)
    assert receipt.http_status == status
    assert receipt.normalized_media_type == media
    assert receipt.body_bytes_observed == body_bytes
    assert receipt.candidate_body_sha256 is None
    assert receipt.candidate_prefix_matched is prefix
    _assert_fixed_receipt_envelope(receipt)
    evidence = acquisition_capability.project_capability_evidence_v1(
        receipt,
        assessed_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
    )
    assert (
        evidence.state is acquisition_capability.CapabilityEvidenceStateV1.NOT_OBSERVED
    )


def test_fixed_public_probe_has_no_caller_options_and_no_live_probe_parameters() -> (
    None
):
    assert acquisition_capability.CANDIDATE_ARTIFACT_URL == CANDIDATE_URL
    assert acquisition_capability.PROBE_METHOD == "GET"
    assert acquisition_capability.PROBE_DEADLINE_SECONDS == 30
    assert acquisition_capability.MAX_TRANSPORT_WAIT_SECONDS == 5
    assert acquisition_capability.MAX_BODY_BYTES == MAX_BODY_BYTES
    assert acquisition_capability.MAX_BODY_READ_BYTES == MAX_BODY_BYTES + 1
    assert (
        tuple(
            inspect.signature(
                acquisition_capability.run_supervised_capability_probe_v1
            ).parameters
        )
        == ()
    )
    assert tuple(
        inspect.signature(
            acquisition_capability._run_supervised_capability_probe_v1
        ).parameters
    ) == ("deadline_seconds",)
    assert not hasattr(acquisition_capability, "_probe_worker")
    assert not hasattr(acquisition_capability, "_worker_main")
    worker = Path(acquisition_capability.__file__).with_name(
        "acquisition_capability_worker.py"
    )
    assert worker.is_absolute()
    assert not worker.is_symlink()
    assert hashlib.sha256(worker.read_bytes()).hexdigest() == (
        acquisition_capability._WORKER_IDENTITY_SHA256
    )


def test_utc_timestamp_uses_four_digit_year_on_the_portable_boundary() -> None:
    assert (
        acquisition_capability._timestamp(datetime(1, 2, 3, 4, 5, 6, 7, tzinfo=UTC))
        == "0001-02-03T04:05:06.000007Z"
    )


def test_supervisor_executes_the_exact_pinned_worker_source_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Process:
        returncode = -9

    launched: list[list[str]] = []
    worker_path = Path(acquisition_capability.__file__).with_name(
        "acquisition_capability_worker.py"
    )
    verified_source = worker_path.read_bytes().decode("utf-8")
    monkeypatch.setattr(
        acquisition_capability.subprocess,
        "Popen",
        lambda arguments, **_options: launched.append(arguments) or Process(),
    )
    monkeypatch.setattr(
        acquisition_capability,
        "_communicate_until_deadline",
        lambda _process, _deadline: (True, b""),
    )
    moments = iter((100.0, 100.1))
    monkeypatch.setattr(
        acquisition_capability.time,
        "monotonic",
        lambda: next(moments),
    )

    acquisition_capability._run_supervised_capability_probe_v1(
        deadline_seconds=2,
    )

    assert launched == [
        [
            sys.executable,
            "-I",
            "-c",
            verified_source,
            "__capability_probe_worker_v1__",
            "102.0",
        ]
    ]


def test_supervisor_rejects_worker_mutation_before_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched: list[object] = []
    mutated = b"mutated worker bytes"
    reads = iter((mutated, b""))
    status = _DescriptorStat(stat.S_IFREG, len(mutated))
    monkeypatch.setattr(acquisition_capability.os, "open", lambda *_args: 41)
    monkeypatch.setattr(acquisition_capability.os, "fstat", lambda _fd: status)
    monkeypatch.setattr(
        acquisition_capability.os,
        "read",
        lambda _fd, _size: next(reads),
    )
    monkeypatch.setattr(acquisition_capability.os, "close", lambda _fd: None)
    monkeypatch.setattr(
        acquisition_capability.subprocess,
        "Popen",
        lambda *_args, **_kwargs: launched.append(object()),
    )
    moments = iter((100.0,))
    monkeypatch.setattr(
        acquisition_capability.time,
        "monotonic",
        lambda: next(moments),
    )

    with pytest.raises(RuntimeError, match="worker identity mismatch"):
        acquisition_capability._run_supervised_capability_probe_v1(
            deadline_seconds=2,
        )

    assert launched == []


@pytest.mark.parametrize(
    ("mode", "size"),
    (
        (stat.S_IFDIR, 1),
        (stat.S_IFREG, acquisition_capability._MAX_WORKER_BYTES + 1),
    ),
)
def test_worker_descriptor_shape_and_size_fail_before_read(
    monkeypatch: pytest.MonkeyPatch,
    mode: int,
    size: int,
) -> None:
    reads: list[int] = []
    closed: list[int] = []
    status = _DescriptorStat(mode, size)
    monkeypatch.setattr(acquisition_capability.os, "open", lambda *_args: 41)
    monkeypatch.setattr(acquisition_capability.os, "fstat", lambda _fd: status)
    monkeypatch.setattr(
        acquisition_capability.os,
        "read",
        lambda _fd, count: reads.append(count) or b"",
    )
    monkeypatch.setattr(acquisition_capability.os, "close", closed.append)

    with pytest.raises(RuntimeError, match="worker identity mismatch"):
        acquisition_capability._verified_worker_source()

    assert reads == []
    assert closed == [41]


def test_worker_descriptor_read_is_bounded_to_maximum_plus_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[int] = []
    status = _DescriptorStat(
        stat.S_IFREG,
        acquisition_capability._MAX_WORKER_BYTES,
    )

    def read_extra_byte(_descriptor: int, count: int) -> bytes:
        requested.append(count)
        return b"x" * count

    monkeypatch.setattr(acquisition_capability.os, "open", lambda *_args: 41)
    monkeypatch.setattr(acquisition_capability.os, "fstat", lambda _fd: status)
    monkeypatch.setattr(acquisition_capability.os, "read", read_extra_byte)
    monkeypatch.setattr(acquisition_capability.os, "close", lambda _fd: None)

    with pytest.raises(RuntimeError, match="worker identity mismatch"):
        acquisition_capability._verified_worker_source()

    assert sum(requested) == acquisition_capability._MAX_WORKER_BYTES + 1
    assert max(requested) <= 4 * 1024


def test_dns_timeout_is_inside_connect_budget_and_maps_to_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = threading.Event()

    def blocked_resolution(*_args: object, **_kwargs: object) -> object:
        release.wait(timeout=1)
        return ()

    monkeypatch.setattr(
        acquisition_capability_worker.socket,
        "getaddrinfo",
        blocked_resolution,
    )
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="DNS deadline"):
            acquisition_capability_worker._resolve_addresses(
                "www.niftyindices.com",
                443,
                started + 0.02,
            )
    finally:
        release.set()
    assert time.monotonic() - started < 0.5

    monkeypatch.setattr(
        acquisition_capability_worker,
        "_probe",
        lambda _deadline: (_ for _ in ()).throw(
            TimeoutError("connect deadline exceeded")
        ),
    )
    writes: list[bytes] = []
    monkeypatch.setattr(
        acquisition_capability_worker.os,
        "write",
        lambda _descriptor, payload: writes.append(payload) or len(payload),
    )
    assert (
        acquisition_capability_worker.main(
            [
                "__capability_probe_worker_v1__",
                str(time.monotonic() + 1),
            ]
        )
        == 0
    )
    assert json.loads(writes[0]) == {"failure": "TRANSPORT_FAILURE"}


def test_connect_attempts_only_the_first_normalized_dns_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = (
        socket.AddressFamily.AF_INET,
        socket.SocketKind.SOCK_STREAM,
        socket.IPPROTO_TCP,
        "",
        ("192.0.2.1", 443),
    )
    second = (
        socket.AddressFamily.AF_INET,
        socket.SocketKind.SOCK_STREAM,
        socket.IPPROTO_TCP,
        "",
        ("192.0.2.2", 443),
    )
    attempts: list[tuple[str, int]] = []
    closed: list[bool] = []
    created: list[tuple[object, ...]] = []

    class FailingSocket:
        def __init__(self, *arguments: object) -> None:
            created.append(arguments)

        def settimeout(self, _timeout: float) -> None:
            return None

        def connect(self, address: tuple[str, int]) -> None:
            attempts.append(address)
            raise OSError("first address failed")

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(
        acquisition_capability_worker,
        "_resolve_addresses",
        lambda _host, _port, _deadline: (first, second),
    )
    monkeypatch.setattr(
        acquisition_capability_worker.socket,
        "socket",
        FailingSocket,
    )

    with pytest.raises(OSError, match="first address failed"):
        acquisition_capability_worker._open_connection(
            urlsplit(CANDIDATE_URL),
            time.monotonic() + 1,
        )

    assert attempts == [("192.0.2.1", 443)]
    assert len(created) == 1
    assert closed == [True]


def test_media_normalization_is_the_complete_minimal_byte_rule() -> None:
    accepted = (
        (b"application/pdf",),
        (b" APPLICATION/PDF\t",),
        (b"\tApplication/Pdf ; charset=UTF-8",),
        (b'application/pdf;ignored="anything"',),
        (b"application/pdf;" + b"x" * 240,),
    )
    for values in accepted:
        assert (
            acquisition_capability.normalize_pdf_media_type_v1(values)
            == "application/pdf"
        )

    rejected = (
        (),
        (b"application/pdf", b"application/pdf"),
        (b"",),
        (b" \t",),
        (b"application/pdfx",),
        (b"text/plain; application/pdf",),
        (b"application/pdf\r",),
        (b"application/pdf\n",),
        (b"application/pdf\x7f",),
        (b"application/pd\xff",),
        (b"application/pdf\x00",),
        (b"application/pdf\x0b",),
        (b" " * 257,),
    )
    for values in rejected:
        assert acquisition_capability.normalize_pdf_media_type_v1(values) is None


@pytest.mark.parametrize(
    ("response", "failure", "status", "media", "body_bytes", "prefix"),
    (
        (
            _Response(status=404),
            "HTTP_STATUS_REJECTED",
            404,
            None,
            None,
            None,
        ),
        (
            _Response(headers=(("Content-Type", "text/plain"),)),
            "CONTENT_TYPE_REJECTED",
            200,
            None,
            None,
            None,
        ),
        (
            _Response(
                headers=(
                    ("Content-Type", "application/pdf"),
                    ("content-type", "application/pdf"),
                )
            ),
            "CONTENT_TYPE_REJECTED",
            200,
            None,
            None,
            None,
        ),
        (
            _Response(body=b""),
            "BODY_EMPTY",
            200,
            "application/pdf",
            0,
            False,
        ),
        (
            _Response(body=PDF + b"x" * (MAX_BODY_BYTES + 100 - len(PDF))),
            "BODY_TOO_LARGE",
            200,
            "application/pdf",
            MAX_BODY_BYTES + 1,
            None,
        ),
        (
            _Response(body=b"x"),
            "CANDIDATE_PREFIX_REJECTED",
            200,
            "application/pdf",
            1,
            False,
        ),
    ),
)
def test_http_status_media_and_bounded_body_select_exact_sanitized_observations(
    response: _Response,
    failure: str,
    status: int,
    media: str | None,
    body_bytes: int | None,
    prefix: bool | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _server(response) as server:
        observation = _observe_local(server, monkeypatch)

    assert len(server.requests) == 1
    assert observation["failure"] == failure
    assert observation.get("http_status") == status
    assert observation.get("normalized_media_type") == media
    assert observation.get("body_bytes_observed") == body_bytes
    assert observation.get("candidate_body_sha256") is None
    assert observation.get("candidate_prefix_matched") == prefix
    assert not hasattr(acquisition_capability, "_receipt_from_observation")
    with pytest.raises(TypeError):
        acquisition_capability.project_capability_evidence_v1(
            observation,
            assessed_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        )


def test_maximum_body_is_observed_once_hashed_transiently_and_never_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = PDF + b"x" * (MAX_BODY_BYTES - len(PDF))
    with _server(
        _Response(
            headers=(("Content-Type", "Application/PDF ; secret=not-retained"),),
            body=body,
        )
    ) as server:
        observation = _observe_local(server, monkeypatch)

    assert len(server.requests) == 1
    request = server.requests[0]
    headers = dict(request["headers"])
    assert request["method"] == "GET"
    assert request["path"] == "/Press_Release/ind_prs21022025.pdf"
    assert request["content_length"] is None
    assert headers["accept"] == "application/pdf"
    assert headers["user-agent"] == "SwingTradingAIAssistant/0.1"
    for forbidden in (
        "authorization",
        "proxy-authorization",
        "cookie",
        "x-api-key",
        "content-type",
    ):
        assert forbidden not in headers

    assert observation == {
        "failure": None,
        "http_status": 200,
        "normalized_media_type": "application/pdf",
        "body_bytes_observed": MAX_BODY_BYTES,
        "candidate_body_sha256": hashlib.sha256(body).hexdigest(),
        "candidate_prefix_matched": True,
    }


def test_transport_failure_has_no_partial_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _server(_Response(close_without_response=True)) as server:
        observation = _observe_local(server, monkeypatch)

    assert len(server.requests) == 1
    assert observation == {"failure": "TRANSPORT_FAILURE"}


def test_redirect_is_rejected_without_following_location_or_making_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with (
        _server(_Response()) as target,
        _server(
            _Response(
                status=302,
                headers=(("Location", f"{target.url}?token=secret"),),
                body=b"redirect body secret",
            )
        ) as source,
    ):
        observation = _observe_local(source, monkeypatch)

    assert len(source.requests) == 1
    assert target.requests == []
    assert observation == {"failure": "HTTP_STATUS_REJECTED", "http_status": 302}
    assert b"secret" not in _canonical(observation).lower()


def test_local_slow_stream_is_killed_without_producing_capability_evidence() -> None:
    before = {child.pid for child in psutil.Process().children(recursive=False)}
    with _server(_Response(slow_stream=True)) as server:
        local = urlsplit(server.url)
        script = (
            "import http.client,sys;"
            "connection=http.client.HTTPConnection(sys.argv[1],int(sys.argv[2]));"
            "connection.request('GET','/candidate');"
            "connection.getresponse().read()"
        )
        process = subprocess.Popen(  # noqa: S603 - fixed interpreter and test-owned arguments
            [
                sys.executable,
                "-c",
                script,
                str(local.hostname),
                str(local.port),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        child = psutil.Process(process.pid)
        assert child.pid not in before
        assert server.request_started.wait(timeout=1)
        assert os.getpgid(child.pid) == child.pid
        started = time.monotonic()
        timed_out, payload = acquisition_capability._communicate_until_deadline(
            process,
            started + 1.25,
        )
        elapsed = time.monotonic() - started
        assert timed_out is True
        assert payload == b""
        assert 1.25 <= elapsed < 2.0
        assert server.client_disconnected.wait(timeout=1)
        _, alive = psutil.wait_procs([child], timeout=1)
        assert alive == []

    with pytest.raises(TypeError):
        acquisition_capability.project_capability_evidence_v1(
            (timed_out, payload),
            assessed_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        )


def test_supervisor_reserves_cleanup_margin_and_records_actual_elapsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Process:
        returncode = -9

    communicated_at: list[float] = []
    monkeypatch.setattr(
        acquisition_capability.subprocess,
        "Popen",
        lambda *_args, **_kwargs: Process(),
    )
    monkeypatch.setattr(
        acquisition_capability,
        "_communicate_until_deadline",
        lambda _process, deadline: communicated_at.append(deadline) or (True, b""),
    )
    moments = iter((100.0, 101.1))
    monkeypatch.setattr(
        acquisition_capability.time,
        "monotonic",
        lambda: next(moments),
    )

    receipt = acquisition_capability._run_supervised_capability_probe_v1(
        deadline_seconds=1.25,
    )

    assert communicated_at == [101.0]
    _assert_failed_row(
        receipt,
        "DEADLINE_EXCEEDED",
        status=None,
        media=None,
        body_bytes=None,
        prefix=None,
    )
    assert 1_099_000 < receipt.elapsed_microseconds < 1_101_000


def test_production_watchdog_cleanup_margin_keeps_truthful_receipt_inside_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Process:
        returncode = -9

    communicated_at: list[float] = []
    monkeypatch.setattr(
        acquisition_capability.subprocess,
        "Popen",
        lambda *_args, **_kwargs: Process(),
    )
    monkeypatch.setattr(
        acquisition_capability,
        "_communicate_until_deadline",
        lambda _process, deadline: communicated_at.append(deadline) or (True, b""),
    )
    moments = iter((100.0, 129.9))
    monkeypatch.setattr(
        acquisition_capability.time,
        "monotonic",
        lambda: next(moments),
    )

    receipt = acquisition_capability._run_supervised_capability_probe_v1(
        deadline_seconds=30,
    )

    assert communicated_at == [129.75]
    _assert_failed_row(
        receipt,
        "DEADLINE_EXCEEDED",
        status=None,
        media=None,
        body_bytes=None,
        prefix=None,
    )
    assert 29_899_000 < receipt.elapsed_microseconds < 29_901_000


def test_capability_projection_is_finite_provider_independent_and_self_identifying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    class Process:
        returncode = -9

    monkeypatch.setattr(
        acquisition_capability.subprocess,
        "Popen",
        lambda *_args, **_kwargs: Process(),
    )
    monkeypatch.setattr(
        acquisition_capability,
        "_communicate_until_deadline",
        lambda _process, _deadline: (True, b""),
    )
    moments = iter((100.0, 100.1))
    monkeypatch.setattr(
        acquisition_capability.time,
        "monotonic",
        lambda: next(moments),
    )
    receipt = acquisition_capability._run_supervised_capability_probe_v1(
        deadline_seconds=2,
    )
    assessed_at = datetime(2026, 8, 15, 12, tzinfo=UTC)

    evidence = acquisition_capability.project_capability_evidence_v1(
        receipt, assessed_at=assessed_at
    )

    assert tuple(
        field.name
        for field in fields(acquisition_capability.CapabilityEvidenceRecordV1)
    ) == (
        "record_version",
        "state",
        "probe_receipt_identity_sha256",
        "assessed_at",
        "evidence_identity_sha256",
    )
    assert (
        evidence.state is acquisition_capability.CapabilityEvidenceStateV1.NOT_OBSERVED
    )
    assert evidence.assessed_at == assessed_at
    raw = evidence.canonical_json_bytes()
    value = json.loads(raw)
    identity = value.pop("evidence_identity_sha256")
    assert identity == _identity(value)
    value["evidence_identity_sha256"] = identity
    assert raw == _canonical(value)
    forbidden = {
        "provider",
        "request_url",
        "method",
        "http_status",
        "normalized_media_type",
        "body_bytes_observed",
        "candidate_body_sha256",
        "candidate_prefix_matched",
        "pdf",
        "authority",
        "evidence_kind",
        "label",
        "count",
    }
    assert forbidden.isdisjoint(value)


def test_supervised_receipt_mutation_invalidates_serialization_and_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Process:
        returncode = -9

    monkeypatch.setattr(
        acquisition_capability.subprocess,
        "Popen",
        lambda *_args, **_kwargs: Process(),
    )
    monkeypatch.setattr(
        acquisition_capability,
        "_communicate_until_deadline",
        lambda _process, _deadline: (True, b""),
    )
    moments = iter((100.0, 100.1))
    monkeypatch.setattr(
        acquisition_capability.time,
        "monotonic",
        lambda: next(moments),
    )
    receipt = acquisition_capability._run_supervised_capability_probe_v1(
        deadline_seconds=2,
    )
    receipt.canonical_json_bytes()

    object.__setattr__(receipt, "retry_count", 1)

    with pytest.raises(ValueError):
        receipt.canonical_json_bytes()
    with pytest.raises(ValueError):
        acquisition_capability.project_capability_evidence_v1(
            receipt,
            assessed_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        )


def test_probe_receipt_has_only_finite_sanitized_contract_fields() -> None:
    assert tuple(
        field.name for field in fields(acquisition_capability.CapabilityProbeReceiptV1)
    ) == (
        "receipt_version",
        "request_url",
        "method",
        "outcome",
        "failure",
        "request_started_at",
        "response_completed_at",
        "elapsed_microseconds",
        "http_status",
        "normalized_media_type",
        "body_bytes_observed",
        "candidate_body_sha256",
        "candidate_prefix_matched",
        "attempt_count",
        "network_call_count",
        "concurrency",
        "retry_count",
        "redirect_count",
        "credential_count",
        "parser_invocation_count",
        "filesystem_write_count",
        "storage_write_count",
        "receipt_identity_sha256",
    )
    assert tuple(
        item.value for item in acquisition_capability.CapabilityProbeFailureV1
    ) == (
        "TRANSPORT_FAILURE",
        "DEADLINE_EXCEEDED",
        "HTTP_STATUS_REJECTED",
        "CONTENT_TYPE_REJECTED",
        "BODY_EMPTY",
        "BODY_TOO_LARGE",
        "CANDIDATE_PREFIX_REJECTED",
    )


def test_receipt_contract_has_no_public_constructor_or_rehydration_path() -> None:
    assert (
        tuple(
            inspect.signature(
                acquisition_capability.CapabilityProbeReceiptV1
            ).parameters
        )
        == ()
    )
    assert not hasattr(
        acquisition_capability.CapabilityProbeReceiptV1,
        "from_canonical_json_bytes",
    )


def test_probe_source_has_no_parser_persistence_catalogue_storage_or_credential_path() -> (
    None
):
    market_data = (
        Path(__file__).parents[2] / "src/swing_trading_ai_assistant/market_data"
    )
    paths = tuple(market_data.glob("acquisition_capability*.py"))
    assert paths
    forbidden_imports = (
        "duckdb",
        "pyarrow",
        "sqlite3",
        "tempfile",
        "swing_trading_ai_assistant.market_data.catalog",
        "swing_trading_ai_assistant.market_data.credentials",
        "swing_trading_ai_assistant.market_regime",
        "swing_trading_ai_assistant.sector_analysis",
    )
    forbidden_calls = {
        "dump",
        "dumps_pdf",
        "getenv",
        "makedirs",
        "mkdir",
        "open",
        "write_bytes",
        "write_text",
    }
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports: list[str] = []
        calls: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    if (
                        node.func.attr == "open"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "os"
                    ):
                        calls.append("os.open")
                    else:
                        calls.append(node.func.attr)
        assert not any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for imported in imports
            for forbidden in forbidden_imports
        )
        assert forbidden_calls.isdisjoint(calls)
