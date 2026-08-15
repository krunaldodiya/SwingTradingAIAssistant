"""Bounded candidate-artifact capability probe and sanitized evidence projection."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, TypedDict, cast

CANDIDATE_ARTIFACT_URL: Final = (
    "https://www.niftyindices.com/Press_Release/ind_prs21022025.pdf"
)
PROBE_METHOD: Final = "GET"
PROBE_DEADLINE_SECONDS: Final = 30
MAX_TRANSPORT_WAIT_SECONDS: Final = 5
MAX_BODY_BYTES: Final = 1_048_576
MAX_BODY_READ_BYTES: Final = MAX_BODY_BYTES + 1

_RECEIPT_VERSION: Final = "market-regime-layer-b-capability-probe@v1"
_EVIDENCE_VERSION: Final = "market-regime-layer-b-capability-evidence@v1"
_NORMALIZED_MEDIA_TYPE: Final = "application/pdf"
_MAX_CONTENT_TYPE_BYTES: Final = 256
_MAX_RECEIPT_BYTES: Final = 4 * 1024
_MAX_EVIDENCE_BYTES: Final = 4 * 1024
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_WATCHDOG_CLEANUP_MARGIN_SECONDS: Final = 0.25
_WORKER_FILENAME: Final = "acquisition_capability_worker.py"
_MAX_WORKER_BYTES: Final = 16 * 1024
_WORKER_IDENTITY_SHA256: Final = (
    "65026c3d26fd266a9ae92c98cee286825b33023bfefc669753fe6261d6fc41d7"
)


class CapabilityProbeOutcomeV1(StrEnum):
    OBSERVED = "OBSERVED"
    FAILED = "FAILED"


class CapabilityProbeFailureV1(StrEnum):
    TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    HTTP_STATUS_REJECTED = "HTTP_STATUS_REJECTED"
    CONTENT_TYPE_REJECTED = "CONTENT_TYPE_REJECTED"
    BODY_EMPTY = "BODY_EMPTY"
    BODY_TOO_LARGE = "BODY_TOO_LARGE"
    CANDIDATE_PREFIX_REJECTED = "CANDIDATE_PREFIX_REJECTED"


class CapabilityEvidenceStateV1(StrEnum):
    OBSERVED = "OBSERVED"
    NOT_OBSERVED = "NOT_OBSERVED"


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


def _timestamp(value: datetime) -> str:
    instant = value.astimezone(UTC)
    return (
        f"{instant.year:04d}-{instant.month:02d}-{instant.day:02d}T"
        f"{instant.hour:02d}:{instant.minute:02d}:{instant.second:02d}."
        f"{instant.microsecond:06d}Z"
    )


def _require_utc_instant(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    if value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(UTC)


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def normalize_pdf_media_type_v1(values: tuple[bytes, ...]) -> str | None:
    """Apply the complete bounded byte rule for the single Content-Type value."""
    if type(values) is not tuple or len(values) != 1:
        return None
    value = values[0]
    if type(value) is not bytes or not 1 <= len(value) <= _MAX_CONTENT_TYPE_BYTES:
        return None
    if any(byte != 0x09 and not 0x20 <= byte <= 0x7E for byte in value):
        return None
    media_type = value.split(b";", 1)[0].strip(b" \t")
    if media_type.lower() != b"application/pdf":
        return None
    return _NORMALIZED_MEDIA_TYPE


def _receipt_value(
    receipt: CapabilityProbeReceiptV1, *, include_identity: bool
) -> dict[str, object]:
    value: dict[str, object] = {
        "receipt_version": receipt.receipt_version,
        "request_url": receipt.request_url,
        "method": receipt.method,
        "outcome": receipt.outcome.value,
        "failure": receipt.failure.value if receipt.failure is not None else None,
        "request_started_at": _timestamp(receipt.request_started_at),
        "response_completed_at": _timestamp(receipt.response_completed_at),
        "elapsed_microseconds": receipt.elapsed_microseconds,
        "http_status": receipt.http_status,
        "normalized_media_type": receipt.normalized_media_type,
        "body_bytes_observed": receipt.body_bytes_observed,
        "candidate_body_sha256": receipt.candidate_body_sha256,
        "candidate_prefix_matched": receipt.candidate_prefix_matched,
        "attempt_count": receipt.attempt_count,
        "network_call_count": receipt.network_call_count,
        "concurrency": receipt.concurrency,
        "retry_count": receipt.retry_count,
        "redirect_count": receipt.redirect_count,
        "credential_count": receipt.credential_count,
        "parser_invocation_count": receipt.parser_invocation_count,
        "filesystem_write_count": receipt.filesystem_write_count,
        "storage_write_count": receipt.storage_write_count,
    }
    if include_identity:
        value["receipt_identity_sha256"] = receipt.receipt_identity_sha256
    return value


@dataclass(frozen=True, slots=True, init=False)
class CapabilityProbeReceiptV1:
    receipt_version: str
    request_url: str
    method: str
    outcome: CapabilityProbeOutcomeV1
    failure: CapabilityProbeFailureV1 | None
    request_started_at: datetime
    response_completed_at: datetime
    elapsed_microseconds: int
    http_status: int | None
    normalized_media_type: str | None
    body_bytes_observed: int | None
    candidate_body_sha256: str | None
    candidate_prefix_matched: bool | None
    attempt_count: int
    network_call_count: int
    concurrency: int
    retry_count: int
    redirect_count: int
    credential_count: int
    parser_invocation_count: int
    filesystem_write_count: int
    storage_write_count: int
    receipt_identity_sha256: str

    def __post_init__(self) -> None:
        started = _require_utc_instant(self.request_started_at, "request_started_at")
        completed = _require_utc_instant(
            self.response_completed_at, "response_completed_at"
        )
        if (
            self.receipt_version != _RECEIPT_VERSION
            or self.request_url != CANDIDATE_ARTIFACT_URL
            or self.method != PROBE_METHOD
            or type(self.outcome) is not CapabilityProbeOutcomeV1
            or (
                self.failure is not None
                and type(self.failure) is not CapabilityProbeFailureV1
            )
            or started > completed
            or type(self.elapsed_microseconds) is not int
            or not 0 <= self.elapsed_microseconds <= 30_000_000
            or self.attempt_count != 1
            or type(self.attempt_count) is not int
            or self.network_call_count != 1
            or type(self.network_call_count) is not int
            or self.concurrency != 1
            or type(self.concurrency) is not int
            or self.retry_count != 0
            or type(self.retry_count) is not int
            or self.redirect_count != 0
            or type(self.redirect_count) is not int
            or self.credential_count != 0
            or type(self.credential_count) is not int
            or self.parser_invocation_count != 0
            or type(self.parser_invocation_count) is not int
            or self.filesystem_write_count != 0
            or type(self.filesystem_write_count) is not int
            or self.storage_write_count != 0
            or type(self.storage_write_count) is not int
        ):
            raise ValueError("invalid capability probe receipt envelope")
        if not self._has_valid_observation_row():
            raise ValueError("invalid capability probe receipt observation row")
        if not _is_digest(self.receipt_identity_sha256):
            raise ValueError("invalid capability probe receipt identity")
        expected = hashlib.sha256(
            _canonical(_receipt_value(self, include_identity=False))
        ).hexdigest()
        if self.receipt_identity_sha256 != expected:
            raise ValueError("capability probe receipt identity mismatch")
        if (
            len(_canonical(_receipt_value(self, include_identity=True)))
            > _MAX_RECEIPT_BYTES
        ):
            raise ValueError("capability probe receipt exceeds bound")

    def _has_valid_observation_row(self) -> bool:
        if self.outcome is CapabilityProbeOutcomeV1.OBSERVED:
            return (
                self.failure is None
                and self.http_status == 200
                and type(self.http_status) is int
                and self.normalized_media_type == _NORMALIZED_MEDIA_TYPE
                and type(self.body_bytes_observed) is int
                and 1 <= self.body_bytes_observed <= MAX_BODY_BYTES
                and _is_digest(self.candidate_body_sha256)
                and self.candidate_prefix_matched is True
            )
        if self.outcome is not CapabilityProbeOutcomeV1.FAILED or self.failure is None:
            return False
        rows: dict[
            CapabilityProbeFailureV1,
            tuple[int | None, str | None, int | None, str | None, bool | None],
        ] = {
            CapabilityProbeFailureV1.TRANSPORT_FAILURE: (None, None, None, None, None),
            CapabilityProbeFailureV1.DEADLINE_EXCEEDED: (None, None, None, None, None),
            CapabilityProbeFailureV1.CONTENT_TYPE_REJECTED: (
                200,
                None,
                None,
                None,
                None,
            ),
            CapabilityProbeFailureV1.BODY_EMPTY: (
                200,
                _NORMALIZED_MEDIA_TYPE,
                0,
                None,
                False,
            ),
            CapabilityProbeFailureV1.BODY_TOO_LARGE: (
                200,
                _NORMALIZED_MEDIA_TYPE,
                MAX_BODY_READ_BYTES,
                None,
                None,
            ),
        }
        if self.failure is CapabilityProbeFailureV1.HTTP_STATUS_REJECTED:
            return (
                type(self.http_status) is int
                and 100 <= self.http_status <= 599
                and self.http_status != 200
                and self.normalized_media_type is None
                and self.body_bytes_observed is None
                and self.candidate_body_sha256 is None
                and self.candidate_prefix_matched is None
            )
        if self.failure is CapabilityProbeFailureV1.CANDIDATE_PREFIX_REJECTED:
            return (
                self.http_status == 200
                and type(self.http_status) is int
                and self.normalized_media_type == _NORMALIZED_MEDIA_TYPE
                and type(self.body_bytes_observed) is int
                and 1 <= self.body_bytes_observed <= MAX_BODY_BYTES
                and self.candidate_body_sha256 is None
                and self.candidate_prefix_matched is False
            )
        expected = rows.get(self.failure)
        return (
            expected is not None
            and (
                self.http_status,
                self.normalized_media_type,
                self.body_bytes_observed,
                self.candidate_body_sha256,
                self.candidate_prefix_matched,
            )
            == expected
        )

    def canonical_json_bytes(self) -> bytes:
        _require_supervised_receipt(self)
        return _canonical(_receipt_value(self, include_identity=True))


def _evidence_value(
    evidence: CapabilityEvidenceRecordV1, *, include_identity: bool
) -> dict[str, object]:
    value: dict[str, object] = {
        "record_version": evidence.record_version,
        "state": evidence.state.value,
        "probe_receipt_identity_sha256": evidence.probe_receipt_identity_sha256,
        "assessed_at": _timestamp(evidence.assessed_at),
    }
    if include_identity:
        value["evidence_identity_sha256"] = evidence.evidence_identity_sha256
    return value


@dataclass(frozen=True, slots=True)
class CapabilityEvidenceRecordV1:
    record_version: str
    state: CapabilityEvidenceStateV1
    probe_receipt_identity_sha256: str
    assessed_at: datetime
    evidence_identity_sha256: str

    def __post_init__(self) -> None:
        _require_utc_instant(self.assessed_at, "assessed_at")
        if (
            self.record_version != _EVIDENCE_VERSION
            or type(self.state) is not CapabilityEvidenceStateV1
            or not _is_digest(self.probe_receipt_identity_sha256)
            or not _is_digest(self.evidence_identity_sha256)
        ):
            raise ValueError("invalid capability evidence record")
        expected = hashlib.sha256(
            _canonical(_evidence_value(self, include_identity=False))
        ).hexdigest()
        if self.evidence_identity_sha256 != expected:
            raise ValueError("capability evidence identity mismatch")
        if len(self.canonical_json_bytes()) > _MAX_EVIDENCE_BYTES:
            raise ValueError("capability evidence record exceeds bound")

    def canonical_json_bytes(self) -> bytes:
        return _canonical(_evidence_value(self, include_identity=True))


_SUPERVISED_RECEIPTS: list[tuple[CapabilityProbeReceiptV1, bytes]] = []


def _require_supervised_receipt(receipt: CapabilityProbeReceiptV1) -> None:
    if len(_SUPERVISED_RECEIPTS) != 1:
        raise ValueError("capability probe receipt lacks supervised origin")
    retained_receipt, canonical_snapshot = _SUPERVISED_RECEIPTS[0]
    if retained_receipt is not receipt:
        raise ValueError("capability probe receipt lacks supervised origin")
    CapabilityProbeReceiptV1.__post_init__(receipt)
    current = _canonical(_receipt_value(receipt, include_identity=True))
    if current != canonical_snapshot:
        raise ValueError("capability probe receipt changed after supervision")


def project_capability_evidence_v1(
    receipt: CapabilityProbeReceiptV1, *, assessed_at: datetime
) -> CapabilityEvidenceRecordV1:
    if type(receipt) is not CapabilityProbeReceiptV1:
        raise TypeError("receipt must be CapabilityProbeReceiptV1")
    _require_supervised_receipt(receipt)
    assessed = _require_utc_instant(assessed_at, "assessed_at")
    state = (
        CapabilityEvidenceStateV1.OBSERVED
        if receipt.outcome is CapabilityProbeOutcomeV1.OBSERVED
        else CapabilityEvidenceStateV1.NOT_OBSERVED
    )
    projection = {
        "record_version": _EVIDENCE_VERSION,
        "state": state.value,
        "probe_receipt_identity_sha256": receipt.receipt_identity_sha256,
        "assessed_at": _timestamp(assessed),
    }
    return CapabilityEvidenceRecordV1(
        record_version=_EVIDENCE_VERSION,
        state=state,
        probe_receipt_identity_sha256=receipt.receipt_identity_sha256,
        assessed_at=assessed,
        evidence_identity_sha256=hashlib.sha256(_canonical(projection)).hexdigest(),
    )


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.communicate()


def _communicate_until_deadline(
    process: subprocess.Popen[bytes], deadline: float
) -> tuple[bool, bytes]:
    try:
        payload, _ = process.communicate(timeout=max(0, deadline - time.monotonic()))
        return False, payload
    except subprocess.TimeoutExpired:
        _terminate_process_group(process)
        return True, b""


def _require_deadline_seconds(deadline_seconds: float) -> None:
    if type(deadline_seconds) not in (int, float) or isinstance(deadline_seconds, bool):
        raise ValueError("deadline_seconds must be numeric")
    if not 0 < deadline_seconds <= PROBE_DEADLINE_SECONDS:
        raise ValueError("deadline_seconds is outside the authorized bound")


def _worker_open_flags() -> int:
    flags = os.O_RDONLY
    for flag_name in ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK"):
        flags |= getattr(os, flag_name, 0)
    return flags


def _verified_worker_source() -> str:
    worker_path = Path(__file__).with_name(_WORKER_FILENAME)
    flags = _worker_open_flags()
    try:
        descriptor = os.open(worker_path, flags)
    except OSError as error:
        raise RuntimeError("capability probe worker path is not regular") from error
    try:
        initial = os.fstat(descriptor)
        if (
            not stat.S_ISREG(initial.st_mode)
            or not 0 < initial.st_size <= _MAX_WORKER_BYTES
        ):
            raise RuntimeError("capability probe worker identity mismatch")
        worker_buffer = bytearray()
        remaining = initial.st_size + 1
        while remaining:
            chunk = os.read(descriptor, min(4 * 1024, remaining))
            if not chunk:
                break
            if len(chunk) > remaining:
                raise RuntimeError("capability probe worker identity mismatch")
            worker_buffer.extend(chunk)
            remaining -= len(chunk)
        final = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if len(worker_buffer) != initial.st_size or any(
        getattr(initial, name) != getattr(final, name) for name in stable_fields
    ):
        raise RuntimeError("capability probe worker identity mismatch")
    worker_bytes = bytes(worker_buffer)
    if hashlib.sha256(worker_bytes).hexdigest() != _WORKER_IDENTITY_SHA256:
        raise RuntimeError("capability probe worker identity mismatch")
    try:
        worker_source = worker_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeError("capability probe worker encoding mismatch") from error
    if worker_source.encode("utf-8") != worker_bytes:
        raise RuntimeError("capability probe worker encoding mismatch")
    return worker_source


def _launch_verified_worker(
    worker_source: str, deadline: float
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(  # noqa: S603 - exact verified source bytes
        [
            sys.executable,
            "-I",
            "-c",
            worker_source,
            "__capability_probe_worker_v1__",
            str(deadline),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={},
        start_new_session=True,
        cwd=os.path.dirname(sys.executable),
    )


def _worker_observation(
    process: subprocess.Popen[bytes], timed_out: bool, payload: bytes
) -> object:
    if timed_out:
        return {"failure": "DEADLINE_EXCEEDED"}
    if process.returncode != 0 or not 0 < len(payload) <= _MAX_RECEIPT_BYTES:
        return {"failure": "TRANSPORT_FAILURE"}
    try:
        return json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"failure": "TRANSPORT_FAILURE"}


class _ObservationFields(TypedDict):
    http_status: int | None
    normalized_media_type: str | None
    body_bytes_observed: int | None
    candidate_body_sha256: str | None
    candidate_prefix_matched: bool | None


def _observation_row(
    observation: object,
) -> tuple[
    CapabilityProbeOutcomeV1,
    CapabilityProbeFailureV1 | None,
    _ObservationFields,
]:
    if type(observation) is not dict:
        observation = {"failure": "TRANSPORT_FAILURE"}
    row = cast(dict[str, object], observation)
    failure_value = row.get("failure")
    if failure_value is not None and type(failure_value) is not str:
        raise ValueError("invalid capability probe failure")
    failure = None if failure_value is None else CapabilityProbeFailureV1(failure_value)
    outcome = (
        CapabilityProbeOutcomeV1.OBSERVED
        if failure is None
        else CapabilityProbeOutcomeV1.FAILED
    )
    http_status = row.get("http_status")
    normalized_media_type = row.get("normalized_media_type")
    body_bytes_observed = row.get("body_bytes_observed")
    candidate_body_sha256 = row.get("candidate_body_sha256")
    candidate_prefix_matched = row.get("candidate_prefix_matched")
    if http_status is not None and type(http_status) is not int:
        raise ValueError("invalid capability probe HTTP status")
    if normalized_media_type is not None and type(normalized_media_type) is not str:
        raise ValueError("invalid capability probe media type")
    if body_bytes_observed is not None and type(body_bytes_observed) is not int:
        raise ValueError("invalid capability probe body length")
    if candidate_body_sha256 is not None and type(candidate_body_sha256) is not str:
        raise ValueError("invalid capability probe body identity")
    if (
        candidate_prefix_matched is not None
        and type(candidate_prefix_matched) is not bool
    ):
        raise ValueError("invalid capability probe prefix")
    fields = _ObservationFields(
        http_status=http_status,
        normalized_media_type=normalized_media_type,
        body_bytes_observed=body_bytes_observed,
        candidate_body_sha256=candidate_body_sha256,
        candidate_prefix_matched=candidate_prefix_matched,
    )
    return outcome, failure, fields


def _run_supervised_capability_probe_v1(
    *, deadline_seconds: float
) -> CapabilityProbeReceiptV1:
    _require_deadline_seconds(deadline_seconds)

    started_at = datetime.now(UTC)
    started_monotonic = time.monotonic()
    deadline = started_monotonic + deadline_seconds
    process = _launch_verified_worker(_verified_worker_source(), deadline)
    worker_deadline = deadline - min(
        _WATCHDOG_CLEANUP_MARGIN_SECONDS,
        deadline_seconds / 5,
    )
    timed_out, payload = _communicate_until_deadline(process, worker_deadline)

    completed_at = datetime.now(UTC)
    elapsed = int((time.monotonic() - started_monotonic) * 1_000_000)
    if elapsed > PROBE_DEADLINE_SECONDS * 1_000_000:
        raise RuntimeError(
            f"capability probe exceeded receipt elapsed bound: {elapsed} microseconds"
        )

    def receipt_from_fixed_worker(observation: object) -> CapabilityProbeReceiptV1:
        try:
            outcome, failure, fields = _observation_row(observation)
            projection = {
                "receipt_version": _RECEIPT_VERSION,
                "request_url": CANDIDATE_ARTIFACT_URL,
                "method": PROBE_METHOD,
                "outcome": outcome.value,
                "failure": failure.value if failure is not None else None,
                "request_started_at": _timestamp(started_at),
                "response_completed_at": _timestamp(completed_at),
                "elapsed_microseconds": elapsed,
                **fields,
                "attempt_count": 1,
                "network_call_count": 1,
                "concurrency": 1,
                "retry_count": 0,
                "redirect_count": 0,
                "credential_count": 0,
                "parser_invocation_count": 0,
                "filesystem_write_count": 0,
                "storage_write_count": 0,
            }
            receipt = object.__new__(CapabilityProbeReceiptV1)
            attributes = {
                "receipt_version": _RECEIPT_VERSION,
                "request_url": CANDIDATE_ARTIFACT_URL,
                "method": PROBE_METHOD,
                "outcome": outcome,
                "failure": failure,
                "request_started_at": started_at,
                "response_completed_at": completed_at,
                "elapsed_microseconds": elapsed,
                "http_status": fields["http_status"],
                "normalized_media_type": fields["normalized_media_type"],
                "body_bytes_observed": fields["body_bytes_observed"],
                "candidate_body_sha256": fields["candidate_body_sha256"],
                "candidate_prefix_matched": fields["candidate_prefix_matched"],
                "attempt_count": 1,
                "network_call_count": 1,
                "concurrency": 1,
                "retry_count": 0,
                "redirect_count": 0,
                "credential_count": 0,
                "parser_invocation_count": 0,
                "filesystem_write_count": 0,
                "storage_write_count": 0,
                "receipt_identity_sha256": hashlib.sha256(
                    _canonical(projection)
                ).hexdigest(),
            }
            for name, value in attributes.items():
                object.__setattr__(receipt, name, value)
            receipt.__post_init__()
            canonical_snapshot = _canonical(
                _receipt_value(receipt, include_identity=True)
            )
            _SUPERVISED_RECEIPTS[:] = [(receipt, canonical_snapshot)]
            return receipt
        except (TypeError, ValueError):
            if observation == {"failure": "TRANSPORT_FAILURE"}:
                raise
            return receipt_from_fixed_worker({"failure": "TRANSPORT_FAILURE"})

    observation = _worker_observation(process, timed_out, payload)
    return receipt_from_fixed_worker(observation)


def run_supervised_capability_probe_v1() -> CapabilityProbeReceiptV1:
    """Run the one fixed credential-free candidate-artifact probe."""
    return _run_supervised_capability_probe_v1(
        deadline_seconds=PROBE_DEADLINE_SECONDS,
    )
