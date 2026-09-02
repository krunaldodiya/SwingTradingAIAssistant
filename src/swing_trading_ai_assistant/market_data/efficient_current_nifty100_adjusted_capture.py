"""Bounded owner-private current Nifty 100 adjusted capture for Plan 33."""

from __future__ import annotations

import base64
import csv
import errno
import hashlib
import io
import json
import logging
import os
import stat
import sys
import threading
import time
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout, suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from shutil import rmtree
from typing import TYPE_CHECKING, Final, Protocol, cast
from urllib.request import HTTPRedirectHandler, build_opener

import multitasking as _untyped_multitasking  # pyright: ignore[reportMissingImports,reportUnknownVariableType]

from . import capture_forward_adjusted_ohlcv as low
from .efficient_current_nifty100_adjusted_capture_runtime_identity_manifest import (
    EFFICIENT_CURRENT_NIFTY100_RUNTIME_SOURCE_SHA256_V1,
)
from .http import HttpResponseBodyTooLarge, HttpTransportError, UrllibHttpTransport
from .runtime_source_verifier import read_runtime_source
from .storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
    StorageRootLeaseOperation,
)
from .universe_snapshot import (
    assert_private_storage_operation,
    open_private_storage_directory,
    publish_exact_storage_object,
    read_bounded_storage_object,
)

if TYPE_CHECKING:

    class CurlSession:
        def __init__(self, *, impersonate: str, retry: int) -> None:
            del impersonate, retry

        def request(self, method: str, url: str, **kwargs: object) -> object: ...

        def close(self) -> None: ...

    def _update_url_params(url: str, params: object) -> str:
        del url, params
        raise NotImplementedError

else:
    CurlSession = import_module("curl_cffi.requests").__dict__["Session"]
    _update_url_params = cast(
        Callable[[str, object], str],
        import_module("curl_cffi.requests.utils").__dict__["update_url_params"],
    )

CONTRACT_VERSION_V1: Final = "efficient-current-nifty100-adjusted-capture@v1"
CONFIGURATION_IDENTITY_SHA256_V1: Final = hashlib.sha256(
    b"plan33_yfinance_8|threads=8|interval=0.125|max_starts=256|max_target=16384|max_response=2097152|max_aggregate=134217728|retry=0"
).hexdigest()
_PROVIDER_CACHE_NAME_V1: Final = ".plan33-yfinance-cache"
NIFTY_50_URL: Final = (
    "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv"
)
NIFTY_NEXT_50_URL: Final = (
    "https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv"
)
NIFTY_100_URL: Final = (
    "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv"
)
MAX_REQUEST_BYTES_V1: Final = 262_144
MAX_RESULT_BYTES_V1: Final = 262_144
MAX_SOURCE_BYTES_V1: Final = 262_144
MIN_START_INTERVAL_SECONDS_V1: Final = 0.125
MAX_HTTP_STARTS_PER_COHORT_V1: Final = 256
MAX_REQUEST_TARGET_BYTES_V1: Final = 16_384
MAX_RESPONSE_BYTES_V1: Final = 2_097_152
MAX_SELECTION_REVISION_BYTES_V1: Final = 2_097_152
POOL_NAME_V1: Final = "plan33_yfinance_8"
MAX_PLAN33_BINDING_BYTES_V1: Final = 16_384
MAX_AGGREGATE_RESPONSE_BYTES_V1: Final = 134_217_728
COHORT_NAMES_V1: Final = ("NIFTY_50", "NIFTY_NEXT_50")
_HEADER: Final = ("Company Name", "Industry", "Symbol", "Series", "ISIN Code")
_PROVIDER_ADMISSION_LOCK: Final = threading.Lock()


class SourceBodyTooLarge(Exception):
    """The bounded official-source reader rejected a body."""


class ResourceLimitExceeded(Exception):
    """The bounded Yahoo transport ledger rejected an effect."""


class ProviderRateLimited(Exception):
    """The first observed provider HTTP 429 stopped the adapter."""


class EvidenceConflict(OSError):
    """Previously retained immutable evidence conflicts with current bytes."""


def _read_immutable_object_v1(
    operation: StorageRootLeaseOperation,
    parent: int,
    name: str,
    maximum: int,
) -> bytes:
    try:
        return read_bounded_storage_object(operation, parent, name, maximum)
    except ValueError:
        raise EvidenceConflict("immutable evidence conflict") from None
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise EvidenceConflict("immutable evidence conflict") from None
        raise


def _publish_immutable_object_v1(
    operation: StorageRootLeaseOperation,
    parent: int,
    name: str,
    payload: bytes,
) -> None:
    try:
        publish_exact_storage_object(operation, parent, name, payload)
    except ValueError as error:
        try:
            existing = _read_immutable_object_v1(operation, parent, name, len(payload))
        except FileNotFoundError:
            raise error from None
        if existing != payload:
            raise EvidenceConflict("immutable evidence conflict") from None
        raise
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise EvidenceConflict("immutable evidence conflict") from None
        raise


class _CurlResponseV1(Protocol):
    content: bytes
    status_code: int


class _MultitaskingV1(Protocol):
    config: dict[str, object]

    def getPool(self) -> dict[str, object]: ...

    def get_active_tasks(self) -> list[object]: ...

    def createPool(self, *, name: str, threads: int, engine: str) -> object:
        del name, threads, engine
        raise NotImplementedError


multitasking = cast(_MultitaskingV1, _untyped_multitasking)


@dataclass(frozen=True, slots=True)
class SharedFailureV1:
    code: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class SourceResponseV1:
    request_url: str
    response_url: str
    status: int
    body: bytes
    retrieved_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.request_url) is not str
            or type(self.response_url) is not str
            or type(self.status) is not int
            or type(self.body) is not bytes
            or type(self.retrieved_at) is not datetime
            or self.retrieved_at.tzinfo is None
            or len(self.body) > MAX_SOURCE_BYTES_V1
        ):
            raise ValueError("source response is invalid")


class SourceFetcherV1(Protocol):
    def get(self, url: str) -> SourceResponseV1: ...


@dataclass(frozen=True, slots=True)
class CohortRequestV1:
    name: str
    request: dict[str, object]
    members: tuple[tuple[str, str, str], ...]
    request_identity_sha256: str


@dataclass(frozen=True, slots=True)
class CurrentNifty100RequestV1:
    cohorts: tuple[CohortRequestV1, CohortRequestV1]
    schedule_identity_sha256: str
    decision_session: str
    decision_cutoff: str


@dataclass(frozen=True, slots=True, order=True)
class SelectionRowV1:
    isin: str
    symbol: str


@dataclass(frozen=True, slots=True)
class SelectionCohortV1:
    name: str
    rows: tuple[SelectionRowV1, ...]
    source_url: str
    response_url: str
    status: int
    retrieved_at: datetime
    source_sha256: str
    source_bytes: bytes


@dataclass(frozen=True, slots=True)
class SelectionRevisionV1:
    label: str
    retrieved_at: datetime
    cohorts: tuple[SelectionCohortV1, SelectionCohortV1]
    witness_url: str
    witness_response_url: str
    witness_status: int
    witness_retrieved_at: datetime
    witness_sha256: str
    witness_bytes: bytes
    selection_identity_sha256: str

    @property
    def member_count(self) -> int:
        return sum(len(cohort.rows) for cohort in self.cohorts)


@dataclass(frozen=True, slots=True)
class CohortOutcomeV1:
    cohort: str
    code: str
    reason: str | None = None
    revision_sha256: str | None = None
    request_identity_sha256: str | None = None
    selection_identity_sha256: str | None = None
    schedule_identity_sha256: str | None = None
    decision_session: str | None = None
    decision_cutoff: str | None = None
    configuration_identity_sha256: str | None = None
    retrieved_at: datetime | None = None
    source_identity_sha256: str | None = None
    source_profile: str | None = None


@dataclass(frozen=True, slots=True)
class CurrentNifty100ResultV1:
    code: str
    cohorts: tuple[CohortOutcomeV1, CohortOutcomeV1]
    selection_identity_sha256: str
    selection_retrieved_at: datetime
    schedule_identity_sha256: str
    decision_session: str
    configuration_identity_sha256: str
    member_count: int
    union_reason: str | None = None


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _unique_json_object_v1(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True, slots=True)
class _SelectionBoundLowRequestV1(low.CaptureForwardAdjustedOhlcvRequestV1):
    selection_identity_sha256: str = ""

    def __post_init__(self) -> None:
        if len(self.selection_identity_sha256) != 64 or any(
            value not in "0123456789abcdef" for value in self.selection_identity_sha256
        ):
            raise ValueError("selection-bound request is invalid")
        low.CaptureForwardAdjustedOhlcvRequestV1.__post_init__(self)

    def canonical_value(
        self, *, include_request_identity: bool = True
    ) -> dict[str, object]:
        value = low.CaptureForwardAdjustedOhlcvRequestV1.canonical_value(
            self, include_request_identity=False
        )
        value["selection_identity_sha256"] = self.selection_identity_sha256
        if include_request_identity:
            value["request_identity_sha256"] = self.request_identity_sha256
        return value


def _runtime_code_identity_v1() -> str:
    source = Path(__file__)
    if not source.is_absolute():
        raise RuntimeError("Plan 33 runtime identity invalid")
    root = source.parent.parent
    try:
        pairs: list[tuple[str, str]] = []
        for relative, expected in sorted(
            EFFICIENT_CURRENT_NIFTY100_RUNTIME_SOURCE_SHA256_V1.items()
        ):
            actual = _digest(read_runtime_source(root, relative))
            if actual != expected:
                raise ValueError
            pairs.append((relative, actual))
        _, low_runtime_identity, _ = low.capture_forward_current_identities_v1()
        pairs.append(("capture-forward-adjusted-ohlcv@v1", low_runtime_identity))
        if not pairs:
            raise ValueError
        return _digest(_canonical(pairs))
    except (OSError, RuntimeError, ValueError):
        raise RuntimeError("Plan 33 runtime identity invalid") from None


def preflight_request_v1(
    raw: bytes, *, acknowledged: bool
) -> tuple[str, str | None] | None:
    """Apply enablement and invocation acknowledgement before every effect."""

    if type(raw) is not bytes or len(raw) > MAX_REQUEST_BYTES_V1:
        return "MALFORMED_INPUT", None
    try:
        decoded: object = json.loads(raw, object_pairs_hook=_unique_json_object_v1)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError):
        return "MALFORMED_INPUT", None
    if type(decoded) is not dict:
        return "MALFORMED_INPUT", None
    value = cast(dict[str, object], decoded)
    if value.get("contract_version") != CONTRACT_VERSION_V1:
        return "MALFORMED_INPUT", None
    enabled = value.get("enabled")
    if type(enabled) is not bool:
        return "MALFORMED_INPUT", None
    if not enabled:
        return "DISABLED", "ADAPTER_DISABLED"
    if acknowledged is not True:
        return "AUTHORIZATION_DENIED", "OWNER_PRIVATE_USE_NOT_ACKNOWLEDGED"
    return None


def parse_request_v1(  # noqa: C901 - closed untrusted request boundary
    raw: bytes,
) -> CurrentNifty100RequestV1:
    """Parse the exact canonical dual-cohort request without effects."""

    if type(raw) is not bytes or not raw or len(raw) > MAX_REQUEST_BYTES_V1:
        raise ValueError("request is invalid")
    try:
        decoded: object = json.loads(raw, object_pairs_hook=_unique_json_object_v1)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise ValueError("request is invalid") from error
    if type(decoded) is not dict:
        raise ValueError("request is invalid")
    value = cast(dict[str, object], decoded)
    cohorts_value = value.get("cohorts")
    if (
        set(value) != {"contract_version", "enabled", "cohorts"}
        or value.get("contract_version") != CONTRACT_VERSION_V1
        or value.get("enabled") is not True
        or type(cohorts_value) is not list
    ):
        raise ValueError("request is invalid")
    rows = cast(list[object], cohorts_value)
    if len(rows) != 2:
        raise ValueError("request is invalid")
    cohorts: list[CohortRequestV1] = []
    shared: tuple[object, object, object] | None = None
    for expected_name, raw_row in zip(COHORT_NAMES_V1, rows, strict=True):
        if type(raw_row) is not dict:
            raise ValueError("request is invalid")
        row = cast(dict[str, object], raw_row)
        request_value = row.get("request")
        if (
            set(row) != {"name", "request"}
            or row.get("name") != expected_name
            or type(request_value) is not dict
        ):
            raise ValueError("request is invalid")
        request = cast(dict[str, object], request_value)
        expected_request_keys = {
            "cohort",
            "cohort_identity_sha256",
            "configuration_identity_sha256",
            "contract_version",
            "decision_cutoff",
            "decision_session",
            "evaluated_at",
            "parent_revision_sha256",
            "request_identity_sha256",
            "runtime_code_identity_sha256",
            "schedule",
            "schema_identity_sha256",
        }
        if set(request) != expected_request_keys:
            raise ValueError("request is invalid")
        members_value = request.get("cohort")
        schedule_value = request.get("schedule")
        request_identity = request.get("request_identity_sha256")
        if type(members_value) is not list:
            raise ValueError("request is invalid")
        member_values = cast(list[object], members_value)
        if (
            len(member_values) != 50
            or type(schedule_value) is not dict
            or type(request_identity) is not str
        ):
            raise ValueError("request is invalid")
        members: list[tuple[str, str, str]] = []
        for member_value in member_values:
            if type(member_value) is not dict:
                raise ValueError("request is invalid")
            member = cast(dict[str, object], member_value)
            expected_member_keys = {
                "effective_symbol",
                "exchange",
                "isin",
                "mapping_identity_sha256",
                "mapping_valid_from",
                "mapping_valid_through",
                "mapping_version",
                "provider_symbol",
                "symbol_history_identity_sha256",
            }
            provider_symbol = member.get("provider_symbol")
            member_mapping_missing = provider_symbol is None or provider_symbol == ""
            if set(member) not in (
                expected_member_keys,
                expected_member_keys - {"provider_symbol"},
            ):
                raise ValueError("request is invalid")
            isin = member.get("isin")
            symbol = member.get("effective_symbol")
            valid_through = member.get("mapping_valid_through")
            if (
                type(isin) is not str
                or len(isin) != 12
                or type(symbol) is not str
                or not symbol
                or (not member_mapping_missing and type(provider_symbol) is not str)
                or member.get("exchange") != "NSE"
                or any(
                    type(member.get(key)) is not str
                    for key in (
                        "mapping_identity_sha256",
                        "mapping_valid_from",
                        "mapping_version",
                        "symbol_history_identity_sha256",
                    )
                )
                or (valid_through is not None and type(valid_through) is not str)
            ):
                raise ValueError("request is invalid")
            members.append(
                (
                    isin,
                    symbol,
                    "" if member_mapping_missing else cast(str, provider_symbol),
                )
            )
        if len({member[0] for member in members}) != 50:
            raise ValueError("request is invalid")
        schedule = cast(dict[str, object], schedule_value)
        if (
            set(schedule)
            != {
                "decision_session_official_close_at",
                "schedule_evidence_sha256",
                "schedule_identity_sha256",
                "schedule_source",
                "schedule_source_release",
                "sessions",
            }
            or type(schedule.get("sessions")) is not list
            or not cast(list[object], schedule["sessions"])
            or any(
                type(item) is not str
                for item in cast(list[object], schedule["sessions"])
            )
            or any(
                type(schedule.get(key)) is not str
                for key in (
                    "decision_session_official_close_at",
                    "schedule_evidence_sha256",
                    "schedule_identity_sha256",
                    "schedule_source",
                    "schedule_source_release",
                )
            )
        ):
            raise ValueError("request is invalid")
        current_shared = (
            schedule["schedule_identity_sha256"],
            request.get("decision_session"),
            request.get("decision_cutoff"),
        )
        if shared is None:
            shared = current_shared
        cohorts.append(
            CohortRequestV1(
                expected_name,
                request,
                tuple(sorted(members)),
                request_identity,
            )
        )
    first, second = cohorts
    if {member[0] for member in first.members} & {
        member[0] for member in second.members
    }:
        raise ValueError("request is invalid")
    if shared is None:
        raise ValueError("request is invalid")
    return CurrentNifty100RequestV1(
        (first, second),
        cast(str, shared[0]),
        cast(str, shared[1]),
        cast(str, shared[2]),
    )


def _parse_source(
    body: bytes, expected_count: int
) -> tuple[SelectionRowV1, ...] | None:
    if type(body) is not bytes or len(body) > MAX_SOURCE_BYTES_V1:
        return None
    try:
        reader = csv.reader(io.StringIO(body.decode("utf-8-sig"), newline=""))
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        return None
    if not rows or tuple(rows[0]) != _HEADER or len(rows[1:]) != expected_count:
        return None
    admitted: list[SelectionRowV1] = []
    for row in rows[1:]:
        if (
            len(row) != len(_HEADER)
            or not all(type(field) is str and field for field in row)
            or row[3] != "EQ"
            or len(row[4]) != 12
        ):
            return None
        admitted.append(SelectionRowV1(row[4], row[2]))
    if (
        len({row.isin for row in admitted}) != expected_count
        or len({row.symbol for row in admitted}) != expected_count
    ):
        return None
    return tuple(sorted(admitted))


def _selection_source_identity_v1(selection: SelectionRevisionV1) -> str:
    sources = [
        {
            "url": cohort.source_url,
            "response_url": cohort.response_url,
            "status": cohort.status,
            "sha256": cohort.source_sha256,
            "byte_count": len(cohort.source_bytes),
        }
        for cohort in selection.cohorts
    ]
    sources.append(
        {
            "url": selection.witness_url,
            "response_url": selection.witness_response_url,
            "status": selection.witness_status,
            "sha256": selection.witness_sha256,
            "byte_count": len(selection.witness_bytes),
        }
    )
    return _digest(
        _canonical(
            {
                "contract_version": CONTRACT_VERSION_V1,
                "label": selection.label,
                "runtime_code_identity_sha256": _runtime_code_identity_v1(),
                "sources": sources,
                "cohorts": [
                    {
                        "name": cohort.name,
                        "rows": [[row.isin, row.symbol] for row in cohort.rows],
                    }
                    for cohort in selection.cohorts
                ],
            }
        )
    )


def _selection_identity_v1(selection: SelectionRevisionV1) -> str:
    return _digest(
        _canonical(
            {
                "contract_version": CONTRACT_VERSION_V1,
                "source_identity_sha256": _selection_source_identity_v1(selection),
                "retrieved_at": selection.retrieved_at.astimezone(UTC).isoformat(),
                "cohort_retrieved_at": [
                    cohort.retrieved_at.astimezone(UTC).isoformat()
                    for cohort in selection.cohorts
                ],
                "witness_retrieved_at": selection.witness_retrieved_at.astimezone(
                    UTC
                ).isoformat(),
            }
        )
    )


def admit_selection_v1(
    request: CurrentNifty100RequestV1, fetcher: SourceFetcherV1
) -> SelectionRevisionV1 | SharedFailureV1:
    """Acquire and admit the three exact bounded official constituent artifacts."""

    responses: list[SourceResponseV1] = []
    try:
        for url in (NIFTY_50_URL, NIFTY_NEXT_50_URL, NIFTY_100_URL):
            response = fetcher.get(url)
            if response.request_url != url or response.response_url != url:
                return SharedFailureV1(
                    "INSUFFICIENT_EVIDENCE", "CONSTITUENT_SOURCE_CONFLICT"
                )
            if response.status != 200 or len(response.body) > MAX_SOURCE_BYTES_V1:
                raise ValueError
            responses.append(response)
    except (OSError, ValueError, SourceBodyTooLarge):
        return SharedFailureV1("INSUFFICIENT_EVIDENCE", "CONSTITUENT_SOURCE_INVALID")
    first = _parse_source(responses[0].body, 50)
    second = _parse_source(responses[1].body, 50)
    witness = _parse_source(responses[2].body, 100)
    if first is None or second is None or witness is None:
        return SharedFailureV1("INSUFFICIENT_EVIDENCE", "CONSTITUENT_SOURCE_INVALID")
    first_set = {(row.isin, row.symbol) for row in first}
    second_set = {(row.isin, row.symbol) for row in second}
    if {row[0] for row in first_set} & {row[0] for row in second_set}:
        return SharedFailureV1("INSUFFICIENT_EVIDENCE", "CONSTITUENT_SOURCE_INVALID")
    if first_set | second_set != {(row.isin, row.symbol) for row in witness}:
        return SharedFailureV1("INSUFFICIENT_EVIDENCE", "CONSTITUENT_SOURCE_CONFLICT")
    for expected, actual in zip(request.cohorts, (first_set, second_set), strict=True):
        requested = {(isin, symbol) for isin, symbol, _ in expected.members}
        if requested != actual:
            return SharedFailureV1(
                "INSUFFICIENT_EVIDENCE", "CONSTITUENT_SOURCE_CONFLICT"
            )
    selection = SelectionRevisionV1(
        "CURRENT_OFFICIAL_LIST_AT_RETRIEVAL",
        max(response.retrieved_at for response in responses),
        (
            SelectionCohortV1(
                "NIFTY_50",
                first,
                NIFTY_50_URL,
                responses[0].response_url,
                responses[0].status,
                responses[0].retrieved_at,
                _digest(responses[0].body),
                responses[0].body,
            ),
            SelectionCohortV1(
                "NIFTY_NEXT_50",
                second,
                NIFTY_NEXT_50_URL,
                responses[1].response_url,
                responses[1].status,
                responses[1].retrieved_at,
                _digest(responses[1].body),
                responses[1].body,
            ),
        ),
        NIFTY_100_URL,
        responses[2].response_url,
        responses[2].status,
        responses[2].retrieved_at,
        _digest(responses[2].body),
        responses[2].body,
        "",
    )
    return replace(
        selection, selection_identity_sha256=_selection_identity_v1(selection)
    )


class TransportLedgerV1:
    """Locked fixed-cadence and byte-bound ledger shared by all provider workers."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_start: float | None = None
        self._starts = 0
        self._next_response = 0
        self._response_bytes: dict[int, int] = {}
        self._aggregate_bytes = 0
        self._violation = False
        self._rate_limited = False

    def begin_cohort(self) -> None:
        with self._lock:
            if self._response_bytes:
                self._violation = True
                raise ResourceLimitExceeded
            self._starts = 0
            self._aggregate_bytes = 0
            self._violation = False
            self._rate_limited = False

    def admit_start(self, method: str, url: str) -> int:
        target_bytes = len(method.encode("utf-8")) + len(url.encode("utf-8"))
        with self._lock:
            if self._rate_limited:
                raise ProviderRateLimited
            if target_bytes > MAX_REQUEST_TARGET_BYTES_V1:
                self._violation = True
                raise ResourceLimitExceeded
            if self._starts >= MAX_HTTP_STARTS_PER_COHORT_V1:
                self._violation = True
                raise ResourceLimitExceeded
            now = self._clock()
            if self._last_start is not None:
                remaining = MIN_START_INTERVAL_SECONDS_V1 - (now - self._last_start)
                if remaining > 0:
                    self._sleep(remaining)
                    now = self._clock()
            self._last_start = now
            self._starts += 1
            self._next_response += 1
            response = self._next_response
            self._response_bytes[response] = 0
            return response

    def admit_body(self, response: int, byte_count: int) -> None:
        if type(response) is not int or type(byte_count) is not int or byte_count < 0:
            raise ValueError("body byte count is invalid")
        with self._lock:
            if self._rate_limited:
                raise ProviderRateLimited
            current = self._response_bytes.get(response)
            if current is None:
                raise ValueError("response is not active")
            if (
                current + byte_count > MAX_RESPONSE_BYTES_V1
                or self._aggregate_bytes + byte_count > MAX_AGGREGATE_RESPONSE_BYTES_V1
            ):
                self._violation = True
                raise ResourceLimitExceeded
            self._response_bytes[response] = current + byte_count
            self._aggregate_bytes += byte_count

    def finish_response(self, response: int) -> None:
        with self._lock:
            if self._response_bytes.pop(response, None) is None:
                raise ValueError("response is not active")

    def mark_rate_limited(self) -> None:
        with self._lock:
            self._rate_limited = True

    @property
    def rate_limited(self) -> bool:
        with self._lock:
            return self._rate_limited

    @property
    def violated(self) -> bool:
        with self._lock:
            return self._violation


class BoundedYahooSessionV1(CurlSession):
    """curl-cffi session with the exact Plan 33 transport ledger."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        owns_provider_admission: bool = False,
        cache_authority: _ProviderCacheAuthorityV1 | None = None,
    ) -> None:
        super().__init__(impersonate="chrome", retry=0)
        self._ledger = TransportLedgerV1(clock=clock, sleep=sleep)
        self._owns_provider_admission = owns_provider_admission
        self._cache_authority = cache_authority

    def begin_cohort(self) -> None:
        self._ledger.begin_cohort()

    def request(self, method: str, url: str, **kwargs: object) -> object:
        if kwargs.get("content_callback") is not None:
            raise ResourceLimitExceeded
        params = kwargs.get("params")
        if params is not None and not isinstance(params, (dict, list, tuple)):
            raise ResourceLimitExceeded
        try:
            target_url = (
                url if params is None else _update_url_params(url, cast(object, params))
            )
        except (TypeError, ValueError):
            raise ResourceLimitExceeded from None
        response_id = self._ledger.admit_start(method, target_url)
        chunks = bytearray()

        def receive(chunk: bytes) -> None:
            self._ledger.admit_body(response_id, len(chunk))
            chunks.extend(chunk)

        kwargs["allow_redirects"] = False
        try:
            try:
                response = cast(
                    _CurlResponseV1,
                    super().request(
                        method,
                        url,
                        **kwargs,
                        content_callback=receive,
                    ),
                )
            except Exception as error:
                if self._ledger.violated:
                    raise ResourceLimitExceeded from error
                raise
            if chunks:
                response.content = bytes(chunks)
            elif response.content:
                self._ledger.admit_body(response_id, len(response.content))
            if response.status_code == 429:
                self._ledger.mark_rate_limited()
                raise ProviderRateLimited
            return response
        finally:
            self._ledger.finish_response(response_id)

    @property
    def rate_limited(self) -> bool:
        return self._ledger.rate_limited

    @property
    def resource_limited(self) -> bool:
        return self._ledger.violated

    def close(self) -> None:
        try:
            super().close()
        finally:
            try:
                if self._cache_authority is not None:
                    cache = self._cache_authority
                    self._cache_authority = None
                    cache.close()
            finally:
                if self._owns_provider_admission:
                    self._owns_provider_admission = False
                    _PROVIDER_ADMISSION_LOCK.release()


def _is_success(row: CohortOutcomeV1) -> bool:
    return row.code in {"REUSED", "INSERTED"} and row.reason is None


def _result_v1(
    request: CurrentNifty100RequestV1,
    selection: SelectionRevisionV1,
    outcomes: tuple[CohortOutcomeV1, CohortOutcomeV1],
    *,
    request_identities: tuple[str, str] | None = None,
) -> CurrentNifty100ResultV1:
    expected_request_identities = request_identities or tuple(
        cohort.request_identity_sha256 for cohort in request.cohorts
    )
    first, second = outcomes
    compatible = (
        _is_success(first)
        and _is_success(second)
        and first.selection_identity_sha256
        == second.selection_identity_sha256
        == selection.selection_identity_sha256
        and first.schedule_identity_sha256
        == second.schedule_identity_sha256
        == request.schedule_identity_sha256
        and first.decision_session
        == second.decision_session
        == request.decision_session
        and first.decision_cutoff == second.decision_cutoff == request.decision_cutoff
        and first.configuration_identity_sha256
        == second.configuration_identity_sha256
        == CONFIGURATION_IDENTITY_SHA256_V1
        and first.request_identity_sha256 == expected_request_identities[0]
        and second.request_identity_sha256 == expected_request_identities[1]
        and first.revision_sha256 is not None
        and second.revision_sha256 is not None
    )
    both_valid = _is_success(first) and _is_success(second)
    return CurrentNifty100ResultV1(
        code=(
            "COMPLETE_CURRENT_NIFTY100_CAPTURE"
            if compatible
            else "INCOMPLETE_CURRENT_NIFTY100_CAPTURE"
        ),
        cohorts=outcomes,
        selection_identity_sha256=selection.selection_identity_sha256,
        selection_retrieved_at=selection.retrieved_at,
        schedule_identity_sha256=request.schedule_identity_sha256,
        decision_session=request.decision_session,
        configuration_identity_sha256=CONFIGURATION_IDENTITY_SHA256_V1,
        member_count=selection.member_count,
        union_reason=None if compatible or not both_valid else "UNION_INCOMPATIBLE",
    )


def execute_admitted_v1(
    request: CurrentNifty100RequestV1,
    selection: SelectionRevisionV1,
    capture: Callable[[CohortRequestV1], CohortOutcomeV1],
) -> CurrentNifty100ResultV1:
    """Process both independently retained cohorts with frozen failure precedence."""

    outcomes: list[CohortOutcomeV1] = []
    for cohort in request.cohorts:
        if outcomes and outcomes[-1].reason == "RETENTION_FAILED":
            outcomes.append(
                CohortOutcomeV1(
                    cohort.name,
                    "NOT_ATTEMPTED",
                    "BLOCKED_BY_PRIOR_RETENTION_FAILURE",
                )
            )
            continue
        outcome = capture(cohort)
        if outcome.cohort != cohort.name:
            raise ValueError("cohort result order is invalid")
        outcomes.append(outcome)
    return _result_v1(
        request,
        selection,
        cast(tuple[CohortOutcomeV1, CohortOutcomeV1], tuple(outcomes)),
    )


def serialize_result_v1(result: CurrentNifty100ResultV1) -> dict[str, object]:
    """Return the fixed bounded public result without member or provider detail."""

    payload: dict[str, object] = {
        "code": result.code,
        "contract_version": CONTRACT_VERSION_V1,
        "selection_identity_sha256": result.selection_identity_sha256,
        "selection_retrieved_at": _timestamp(result.selection_retrieved_at),
        "schedule_identity_sha256": result.schedule_identity_sha256,
        "decision_session": result.decision_session,
        "configuration_identity_sha256": result.configuration_identity_sha256,
        "member_count": result.member_count,
        "cohorts": [
            {
                "cohort": row.cohort,
                "code": row.code,
                "reason": row.reason,
                "revision_sha256": row.revision_sha256,
                "request_identity_sha256": row.request_identity_sha256,
                "retrieved_at": (
                    None if row.retrieved_at is None else _timestamp(row.retrieved_at)
                ),
                "source_identity_sha256": row.source_identity_sha256,
                "source_profile": row.source_profile,
            }
            for row in result.cohorts
        ],
        "union_reason": result.union_reason,
    }
    if len(_canonical(payload)) > MAX_RESULT_BYTES_V1:
        raise ValueError("result exceeds public bound")
    return payload


class _RejectRedirectHandlerV1(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: object,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl


class OfficialSourceFetcherV1:
    """Fixed-endpoint official source fetcher with a 256-KiB body ceiling."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._transport = UrllibHttpTransport(
            timeout_seconds=10.0,
            max_body_bytes=MAX_SOURCE_BYTES_V1,
            opener=build_opener(_RejectRedirectHandlerV1()).open,
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    def get(self, url: str) -> SourceResponseV1:
        try:
            response = self._transport.get(url, {})
        except HttpResponseBodyTooLarge as error:
            raise SourceBodyTooLarge from error
        except HttpTransportError as error:
            raise OSError from error
        if response.request_url is None or response.response_url is None:
            raise OSError("official source URL unavailable")
        return SourceResponseV1(
            response.request_url,
            response.response_url,
            response.status_code,
            response.body,
            self._clock(),
        )


def selection_revision_bytes_v1(selection: SelectionRevisionV1) -> bytes:
    """Serialize exact private current-at-retrieval source evidence."""

    payload = {
        "contract_version": CONTRACT_VERSION_V1,
        "runtime_code_identity_sha256": _runtime_code_identity_v1(),
        "label": selection.label,
        "retrieved_at": selection.retrieved_at.astimezone(UTC).isoformat(),
        "selection_identity_sha256": selection.selection_identity_sha256,
        "selection_source_identity_sha256": _selection_source_identity_v1(selection),
        "cohorts": [
            {
                "name": cohort.name,
                "request_url": cohort.source_url,
                "response_url": cohort.response_url,
                "status": cohort.status,
                "retrieved_at": cohort.retrieved_at.astimezone(UTC).isoformat(),
                "sha256": cohort.source_sha256,
                "body_base64": base64.b64encode(cohort.source_bytes).decode("ascii"),
                "rows": [[row.isin, row.symbol] for row in cohort.rows],
            }
            for cohort in selection.cohorts
        ],
        "witness": {
            "request_url": selection.witness_url,
            "response_url": selection.witness_response_url,
            "status": selection.witness_status,
            "retrieved_at": selection.witness_retrieved_at.astimezone(UTC).isoformat(),
            "sha256": selection.witness_sha256,
            "body_base64": base64.b64encode(selection.witness_bytes).decode("ascii"),
        },
    }
    encoded = _canonical(payload) + b"\n"
    if len(encoded) > MAX_SELECTION_REVISION_BYTES_V1:
        raise ValueError("selection revision exceeds bound")
    return encoded


def _retained_timestamp_v1(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError("selection timestamp is invalid")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.astimezone(UTC).isoformat() != value:
        raise ValueError("selection timestamp is invalid")
    return parsed


def _retained_selection_v1(
    raw: bytes, current: SelectionRevisionV1
) -> SelectionRevisionV1:
    try:
        stored = json.loads(raw)
        if type(stored) is not dict:
            raise ValueError
        stored_row = cast(dict[str, object], stored)
        if (
            type(stored_row.get("cohorts")) is not list
            or type(stored_row.get("witness")) is not dict
            or type(stored_row.get("selection_identity_sha256")) is not str
        ):
            raise ValueError
        stored_cohorts = cast(list[dict[str, object]], stored_row["cohorts"])
        stored_witness = cast(dict[str, object], stored_row["witness"])
        if len(stored_cohorts) != 2 or any(
            type(row) is not dict for row in stored_cohorts
        ):
            raise ValueError
        cohort_times = tuple(
            _retained_timestamp_v1(row["retrieved_at"]) for row in stored_cohorts
        )
        witness_time = _retained_timestamp_v1(stored_witness["retrieved_at"])
        retained = replace(
            current,
            retrieved_at=_retained_timestamp_v1(stored_row["retrieved_at"]),
            cohorts=tuple(
                replace(cohort, retrieved_at=retrieved_at)
                for cohort, retrieved_at in zip(
                    current.cohorts, cohort_times, strict=True
                )
            ),
            witness_retrieved_at=witness_time,
            selection_identity_sha256=cast(
                str, stored_row["selection_identity_sha256"]
            ),
        )
        if (
            retained.retrieved_at != max(*cohort_times, witness_time)
            or stored_row.get("selection_source_identity_sha256")
            != _selection_source_identity_v1(retained)
            or retained.selection_identity_sha256 != _selection_identity_v1(retained)
            or raw != selection_revision_bytes_v1(retained)
        ):
            raise ValueError
        return retained
    except (
        KeyError,
        RecursionError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        raise EvidenceConflict("selection evidence conflict") from None


def _read_retained_selection_v1(
    selection: SelectionRevisionV1, root: Path
) -> SelectionRevisionV1 | None:
    try:
        root.lstat()
    except FileNotFoundError:
        return None
    identity = StorageRootLease.admit_existing_private_identity(root)
    if identity is None:
        raise OSError("selection store unavailable")
    lease_result = StorageRootLease.try_acquire_existing_identity(root, identity)
    if lease_result.outcome is not LeaseOutcome.ACQUIRED or lease_result.lease is None:
        return None
    lease = lease_result.lease
    directory: int | None = None
    try:
        with lease.read_operation(root) as operation:
            assert_private_storage_operation(operation)
            try:
                directory = open_private_storage_directory(
                    operation, operation.descriptor, "selections", False
                )
                raw = _read_immutable_object_v1(
                    operation,
                    directory,
                    f"{_selection_source_identity_v1(selection)}.json",
                    MAX_SELECTION_REVISION_BYTES_V1,
                )
                return _retained_selection_v1(raw, selection)
            except FileNotFoundError:
                return None
    except ValueError:
        raise EvidenceConflict("selection evidence conflict") from None
    finally:
        if directory is not None:
            os.close(directory)
        lease.close()


def _create_private_root_v1(root: Path) -> None:
    if (
        not root.is_absolute()
        or len(root.parts) < 2
        or any(part in {".", ".."} for part in root.parts)
    ):
        raise ValueError("selection root must be absolute")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    parent = os.open(os.sep, flags)
    descriptor: int | None = None
    try:
        for component in root.parts[1:-1]:
            opened = os.open(component, flags, dir_fd=parent)
            os.close(parent)
            parent = opened
        try:
            os.mkdir(root.name, mode=0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
        descriptor = os.open(root.name, flags, dir_fd=parent)
        held = os.fstat(descriptor)
        named = os.stat(root.name, dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISDIR(held.st_mode)
            or held.st_uid != os.geteuid()
            or stat.S_IMODE(held.st_mode) != 0o700
            or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise OSError("selection store unavailable")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def resolve_selection_v1(
    selection: SelectionRevisionV1, root: Path
) -> tuple[str, SelectionRevisionV1]:
    """Insert new selection bytes or return the exact previously retained revision."""

    _create_private_root_v1(root)
    payload = selection_revision_bytes_v1(selection)
    name = f"{_selection_source_identity_v1(selection)}.json"
    lease_result = StorageRootLease.try_acquire_private_empty(root)
    if lease_result.outcome is not LeaseOutcome.ACQUIRED:
        identity = StorageRootLease.admit_existing_private_identity(root)
        if identity is not None:
            lease_result = StorageRootLease.try_acquire_existing_identity(
                root, identity
            )
    if lease_result.outcome is not LeaseOutcome.ACQUIRED or lease_result.lease is None:
        raise OSError("selection store unavailable")
    lease = lease_result.lease
    directory: int | None = None
    try:
        with lease.root_operation(root) as operation:
            assert_private_storage_operation(operation)
            try:
                directory = open_private_storage_directory(
                    operation, operation.descriptor, "selections", True
                )
            except ValueError:
                raise EvidenceConflict("selection evidence conflict") from None
            try:
                existing = _read_immutable_object_v1(
                    operation, directory, name, MAX_SELECTION_REVISION_BYTES_V1
                )
            except FileNotFoundError:
                _publish_immutable_object_v1(operation, directory, name, payload)
                status, retained = "INSERTED", selection
                expected = payload
            else:
                status, retained = "REUSED", _retained_selection_v1(existing, selection)
                expected = existing
            exact = _read_immutable_object_v1(
                operation, directory, name, MAX_SELECTION_REVISION_BYTES_V1
            )
            if exact != expected:
                raise EvidenceConflict("selection exact read failed")
            return status, retained
    finally:
        if directory is not None:
            os.close(directory)
        lease.close()


def retain_selection_v1(selection: SelectionRevisionV1, root: Path) -> str:
    """Insert or exactly reuse one immutable private selection revision."""

    return resolve_selection_v1(selection, root)[0]


def _pool_is_exact_v1() -> bool:
    try:
        pool = multitasking.getPool()
    except (KeyError, TypeError):
        return False
    return pool == {"engine": "thread", "name": POOL_NAME_V1, "threads": 8}


def _dependency_logging_is_safe_v1() -> bool:
    return not logging.getLogger().isEnabledFor(
        logging.DEBUG
    ) and not logging.getLogger("yfinance").isEnabledFor(logging.DEBUG)


class _DiscardOutputV1:
    def write(self, value: str) -> int:
        return len(value)

    def flush(self) -> None:
        return None


def _descriptor_directory_path_v1(descriptor: int) -> Path:
    held = os.fstat(descriptor)
    if sys.platform == "darwin":
        location = Path(f"/.vol/{held.st_dev}/{held.st_ino}")
    elif sys.platform.startswith("linux"):
        location = Path(f"/proc/self/fd/{descriptor}")
    else:
        raise RuntimeError("provider runtime configuration invalid")
    resolved = os.stat(location)
    if not stat.S_ISDIR(held.st_mode) or (resolved.st_dev, resolved.st_ino) != (
        held.st_dev,
        held.st_ino,
    ):
        raise RuntimeError("provider runtime configuration invalid")
    return location


@dataclass(slots=True)
class _ProviderCacheAuthorityV1:
    lease: StorageRootLease
    operation: StorageRootLeaseOperation
    descriptor: int
    name: str
    location: Path
    identity: tuple[int, int, int, int]

    def ensure_descriptor_live(self) -> None:
        self.operation.ensure_live()
        held = os.fstat(self.descriptor)
        actual = (held.st_dev, held.st_ino, held.st_mode, held.st_uid)
        if (
            actual != self.identity
            or not stat.S_ISDIR(held.st_mode)
            or stat.S_IMODE(held.st_mode) != 0o700
            or held.st_uid != os.geteuid()
        ):
            raise RuntimeError("provider runtime configuration invalid")

    def ensure_live(self) -> None:
        self.ensure_descriptor_live()
        named = os.stat(
            self.name,
            dir_fd=self.operation.descriptor,
            follow_symlinks=False,
        )
        if self.identity != (named.st_dev, named.st_ino, named.st_mode, named.st_uid):
            raise RuntimeError("provider runtime configuration invalid")

    def close(self) -> None:
        try:
            self.ensure_descriptor_live()
            try:
                rmtree(".", dir_fd=self.descriptor)
            except OSError as error:
                if error.errno not in {errno.EBUSY, errno.EINVAL}:
                    raise
            if os.listdir(self.descriptor):
                raise RuntimeError("provider runtime configuration invalid")
            self.ensure_live()
            self.operation.ensure_live()
        finally:
            os.close(self.descriptor)
            try:
                self.operation.__exit__(None, None, None)
            finally:
                self.lease.close()


def _open_provider_cache_authority_v1(root: Path) -> _ProviderCacheAuthorityV1:
    identity = StorageRootLease.admit_existing_private_identity(root)
    if identity is None:
        raise RuntimeError("provider runtime configuration invalid")
    result = StorageRootLease.try_acquire_existing_identity(root, identity)
    if result.outcome is not LeaseOutcome.ACQUIRED or result.lease is None:
        raise RuntimeError("provider runtime configuration invalid")
    lease = result.lease
    operation = lease.root_operation(root)
    descriptor: int | None = None
    entered = False
    try:
        operation.__enter__()
        entered = True
        assert_private_storage_operation(operation)
        name = _PROVIDER_CACHE_NAME_V1
        with suppress(FileExistsError):
            os.mkdir(name, mode=0o700, dir_fd=operation.descriptor)
        created = os.stat(
            name,
            dir_fd=operation.descriptor,
            follow_symlinks=False,
        )
        created_identity = (
            created.st_dev,
            created.st_ino,
            created.st_mode,
            created.st_uid,
        )
        if (
            not stat.S_ISDIR(created.st_mode)
            or stat.S_IMODE(created.st_mode) != 0o700
            or created.st_uid != os.geteuid()
        ):
            raise RuntimeError("provider runtime configuration invalid")
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=operation.descriptor,
        )
        held = os.fstat(descriptor)
        if (
            held.st_dev,
            held.st_ino,
            held.st_mode,
            held.st_uid,
        ) != created_identity or os.listdir(descriptor):
            raise RuntimeError("provider runtime configuration invalid")
        authority = _ProviderCacheAuthorityV1(
            lease,
            operation,
            descriptor,
            name,
            _descriptor_directory_path_v1(descriptor),
            (held.st_dev, held.st_ino, held.st_mode, held.st_uid),
        )
        authority.ensure_live()
        return authority
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        if entered:
            operation.__exit__(None, None, None)
        lease.close()
        raise


def prepare_yfinance_runtime_v1(cache_root: Path) -> BoundedYahooSessionV1:
    """Create and verify one exact exclusive runtime before importing yfinance."""

    if not _PROVIDER_ADMISSION_LOCK.acquire(blocking=False):
        raise RuntimeError("provider runtime configuration invalid")
    cache: _ProviderCacheAuthorityV1 | None = None
    try:
        if (
            "yfinance" in sys.modules
            or version("multitasking") != "0.0.13"
            or version("yfinance") != "1.6.0"
            or not _dependency_logging_is_safe_v1()
        ):
            raise RuntimeError("provider runtime configuration invalid")
        if (
            multitasking.get_active_tasks()
            or multitasking.config["POOL_NAME"] != "Main"
        ):
            raise RuntimeError("provider runtime configuration invalid")
        multitasking.createPool(name=POOL_NAME_V1, threads=8, engine="thread")
        if not _pool_is_exact_v1():
            raise RuntimeError("provider runtime configuration invalid")
        cache = _open_provider_cache_authority_v1(cache_root)
        session = BoundedYahooSessionV1(
            owns_provider_admission=True,
            cache_authority=cache,
        )
    except BaseException:
        try:
            if cache is not None:
                cache.close()
        finally:
            _PROVIDER_ADMISSION_LOCK.release()
        raise
    try:
        previous_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            with (
                redirect_stdout(_DiscardOutputV1()),
                redirect_stderr(_DiscardOutputV1()),
            ):
                module = low._load_yfinance_module()  # pyright: ignore[reportPrivateUsage]
                set_cache = module.__dict__.get("set_tz_cache_location")
                if not callable(set_cache):
                    raise RuntimeError("provider runtime configuration invalid")
                set_cache(str(cache.location))
        finally:
            logging.disable(previous_disable)
        if (
            module.__dict__.get("__version__") != "1.6.0"
            or not _pool_is_exact_v1()
            or multitasking.get_active_tasks()
            or not _dependency_logging_is_safe_v1()
        ):
            raise RuntimeError("provider runtime configuration invalid")
    except BaseException:
        session.close()
        raise
    return session


class _Plan33ProviderV1:
    def __init__(self, session: BoundedYahooSessionV1) -> None:
        self._session = session
        self._adapter = low.YfinanceCaptureForwardAdjustedOhlcvAdapterV1()

    def download(self, **kwargs: object) -> object:
        if (
            not _pool_is_exact_v1()
            or multitasking.get_active_tasks()
            or not _dependency_logging_is_safe_v1()
            or kwargs.get("threads") is not False
        ):
            return low.CaptureForwardAdjustedOhlcvFailureV1(
                "INSUFFICIENT_EVIDENCE", "RUNTIME_CONFIGURATION_INVALID"
            )
        kwargs["threads"] = 8
        kwargs["session"] = self._session
        kwargs["_plan33_normalize_provider_order"] = True
        previous_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            with (
                redirect_stdout(_DiscardOutputV1()),
                redirect_stderr(_DiscardOutputV1()),
            ):
                return self._adapter.download(**kwargs)
        finally:
            logging.disable(previous_disable)


class _UnresolvedProbeV1:
    def download(self, **kwargs: object) -> object:
        del kwargs
        raise RuntimeError("unresolved")


def _plan33_binding_name_v1(
    cohort: CohortRequestV1,
    selection: SelectionRevisionV1,
    request_identity_sha256: str,
) -> str:
    identity = _digest(
        _canonical(
            {
                "configuration_identity_sha256": CONFIGURATION_IDENTITY_SHA256_V1,
                "contract_version": CONTRACT_VERSION_V1,
                "cohort": cohort.name,
                "request_identity_sha256": request_identity_sha256,
                "selection_identity_sha256": selection.selection_identity_sha256,
            }
        )
    )
    return f"{cohort.name.lower()}-{identity}.json"


def _plan33_binding_payload_v1(
    cohort: CohortRequestV1,
    result: low.CaptureForwardAdjustedOhlcvSuccessV1,
    selection: SelectionRevisionV1,
) -> bytes:
    revision = result.revision
    return (
        _canonical(
            {
                "configuration_identity_sha256": CONFIGURATION_IDENTITY_SHA256_V1,
                "contract_version": CONTRACT_VERSION_V1,
                "cohort": cohort.name,
                "decision_session": revision.decision_session.isoformat(),
                "request_identity_sha256": revision.request_identity_sha256,
                "retrieved_at": _timestamp(revision.retrieved_at),
                "revision_sha256": revision.revision_sha256,
                "schedule_identity_sha256": revision.schedule.schedule_identity_sha256,
                "selection_identity_sha256": selection.selection_identity_sha256,
                "source_identity_sha256": revision.source_identity_sha256,
                "source_profile": revision.source_profile,
            }
        )
        + b"\n"
    )


def _read_plan33_binding_v1(root: Path, name: str) -> bytes | None:
    identity = StorageRootLease.admit_existing_private_identity(root)
    if identity is None:
        raise OSError("Plan 33 binding store unavailable")
    lease_result = StorageRootLease.try_acquire_existing_identity(root, identity)
    if lease_result.outcome is not LeaseOutcome.ACQUIRED or lease_result.lease is None:
        raise OSError("Plan 33 binding store unavailable")
    lease = lease_result.lease
    directory: int | None = None
    try:
        with lease.read_operation(root) as operation:
            assert_private_storage_operation(operation)
            try:
                directory = open_private_storage_directory(
                    operation,
                    operation.descriptor,
                    "plan33_bindings",
                    False,
                )
                return _read_immutable_object_v1(
                    operation, directory, name, MAX_PLAN33_BINDING_BYTES_V1
                )
            except FileNotFoundError:
                return None
    except ValueError:
        raise EvidenceConflict("Plan 33 binding evidence conflict") from None
    finally:
        if directory is not None:
            os.close(directory)
        lease.close()


def _retain_plan33_binding_with_operation_v1(
    cohort: CohortRequestV1,
    result: low.CaptureForwardAdjustedOhlcvSuccessV1,
    selection: SelectionRevisionV1,
    operation: StorageRootLeaseOperation,
) -> None:
    revision = result.revision
    payload = _plan33_binding_payload_v1(cohort, result, selection)
    name = _plan33_binding_name_v1(cohort, selection, revision.request_identity_sha256)
    directory: int
    assert_private_storage_operation(operation)
    try:
        directory = open_private_storage_directory(
            operation,
            operation.descriptor,
            "plan33_bindings",
            True,
        )
    except ValueError:
        raise EvidenceConflict("Plan 33 binding evidence conflict") from None
    try:
        try:
            existing = _read_immutable_object_v1(
                operation, directory, name, MAX_PLAN33_BINDING_BYTES_V1
            )
        except FileNotFoundError:
            _publish_immutable_object_v1(operation, directory, name, payload)
        else:
            if existing != payload:
                raise EvidenceConflict("Plan 33 binding evidence conflict")
        if (
            _read_immutable_object_v1(
                operation, directory, name, MAX_PLAN33_BINDING_BYTES_V1
            )
            != payload
        ):
            raise EvidenceConflict("Plan 33 binding evidence conflict")
    finally:
        os.close(directory)


def _retain_plan33_binding_v1(
    cohort: CohortRequestV1,
    result: low.CaptureForwardAdjustedOhlcvSuccessV1,
    selection: SelectionRevisionV1,
    root: Path,
    *,
    operation: StorageRootLeaseOperation | None = None,
) -> None:
    if operation is not None:
        identity = StorageRootLease.admit_existing_private_identity(root)
        held = os.fstat(operation.descriptor)
        if identity != (held.st_dev, held.st_ino):
            raise OSError("Plan 33 binding store unavailable")
        _retain_plan33_binding_with_operation_v1(cohort, result, selection, operation)
        return

    lease_result = StorageRootLease.try_acquire_private_empty(root)
    if lease_result.outcome is not LeaseOutcome.ACQUIRED:
        identity = StorageRootLease.admit_existing_private_identity(root)
        if identity is not None:
            lease_result = StorageRootLease.try_acquire_existing_identity(
                root, identity
            )
    if lease_result.outcome is not LeaseOutcome.ACQUIRED or lease_result.lease is None:
        raise OSError("Plan 33 binding store unavailable")
    lease = lease_result.lease
    try:
        with lease.root_operation(root) as held_operation:
            _retain_plan33_binding_with_operation_v1(
                cohort, result, selection, held_operation
            )
    finally:
        lease.close()


def _cohort_outcome_v1(  # noqa: C901 - frozen failure translation
    cohort: CohortRequestV1,
    low_request: low.CaptureForwardAdjustedOhlcvRequestV1,
    result: object,
    selection: SelectionRevisionV1,
    request: CurrentNifty100RequestV1,
    session: BoundedYahooSessionV1 | None = None,
    *,
    binding_root: Path | None = None,
) -> CohortOutcomeV1:
    if isinstance(result, low.CaptureForwardAdjustedOhlcvSuccessV1):
        revision = result.revision
        selection_cohort = next(
            row for row in selection.cohorts if row.name == cohort.name
        )
        request_compatible = (
            revision.request_identity_sha256 == low_request.request_identity_sha256
            and revision.cohort == low_request.cohort
            and revision.schedule == low_request.schedule
            and revision.decision_session == low_request.decision_session
            and revision.configuration_identity_sha256
            == low_request.configuration_identity_sha256
            and revision.provider_source == low.EXPECTED_PROVIDER_SOURCE_V1
            and revision.source_profile == low.SOURCE_PROFILE_V1
            and {(member.isin, member.effective_symbol) for member in revision.cohort}
            == {(row.isin, row.symbol) for row in selection_cohort.rows}
        )
        if not request_compatible:
            return CohortOutcomeV1(
                cohort.name, "INSUFFICIENT_EVIDENCE", "EVIDENCE_CONFLICT"
            )
        selection_bound = revision.retrieved_at >= selection.retrieved_at
        if binding_root is not None and selection_bound:
            try:
                authority = (
                    getattr(session, "_cache_authority", None)
                    if session is not None
                    else None
                )
                if authority is None:
                    _retain_plan33_binding_v1(cohort, result, selection, binding_root)
                else:
                    authority.ensure_live()
                    _retain_plan33_binding_v1(
                        cohort,
                        result,
                        selection,
                        binding_root,
                        operation=authority.operation,
                    )
            except EvidenceConflict:
                return CohortOutcomeV1(
                    cohort.name, "INSUFFICIENT_EVIDENCE", "EVIDENCE_CONFLICT"
                )
            except (OSError, RuntimeError, ValueError):
                return CohortOutcomeV1(
                    cohort.name, "INSUFFICIENT_EVIDENCE", "RETENTION_FAILED"
                )

        return CohortOutcomeV1(
            cohort.name,
            "REUSED" if result.code == "REUSED" else "INSERTED",
            revision_sha256=revision.revision_sha256,
            request_identity_sha256=revision.request_identity_sha256,
            selection_identity_sha256=(
                selection.selection_identity_sha256 if selection_bound else None
            ),
            schedule_identity_sha256=revision.schedule.schedule_identity_sha256,
            decision_session=revision.decision_session.isoformat(),
            decision_cutoff=_timestamp(revision.decision_cutoff),
            configuration_identity_sha256=CONFIGURATION_IDENTITY_SHA256_V1,
            retrieved_at=revision.retrieved_at,
            source_identity_sha256=revision.source_identity_sha256,
            source_profile=revision.source_profile,
        )
    if session is not None and session.resource_limited:
        reason = "RESOURCE_LIMIT_EXCEEDED"
    elif session is not None and session.rate_limited:
        reason = "PROVIDER_RATE_LIMITED"
    elif isinstance(result, low.CaptureForwardAdjustedOhlcvFailureV1):
        if result.reason == "RUNTIME_CONFIGURATION_INVALID":
            reason = "CONFIGURATION_INVALID"
        elif result.reason == "PROVIDER_CALL_FAILED":
            reason = "PROVIDER_ERROR"
        elif result.reason.startswith("FRAME_") or result.reason in {
            "CORRECTION_CONTENT_UNCHANGED",
            "PROVIDER_EMPTY",
            "PROVIDER_TIMESTAMP_INVALID",
            "PROVIDER_TIMEZONE_INVALID",
            "PROVIDER_VALUE_INVALID",
            "RETRIEVED_AFTER_DECISION_CUTOFF",
            "RETRIEVED_BEFORE_OFFICIAL_CLOSE",
        }:
            reason = "PROVIDER_FRAME_INCOMPLETE"
        elif result.reason == "PROVIDER_IDENTITY_MISMATCH":
            reason = "PROVIDER_BASIS_INVALID"
        elif result.reason in {
            "PUBLISHED_REVISION_MISMATCH",
            "PARENT_REVISION_MISMATCH",
            "PREPARED_REVISION_MISMATCH",
            "EXACT_READBACK_FAILED",
            "EVIDENCE_CONFLICT",
        }:
            reason = "EVIDENCE_CONFLICT"
        elif result.code == "STORE_UNAVAILABLE":
            reason = "RETENTION_FAILED"
        else:
            reason = "PROVIDER_ERROR"
    else:
        reason = "PROVIDER_ERROR"
    return CohortOutcomeV1(cohort.name, "INSUFFICIENT_EVIDENCE", reason)


def _has_effect_stopping_failure(outcomes: list[CohortOutcomeV1 | None]) -> bool:
    return any(
        outcome is not None
        and outcome.reason in {"RETENTION_FAILED", "EVIDENCE_CONFLICT"}
        for outcome in outcomes
    )


def _selection_bound_low_request_v1(
    request: low.CaptureForwardAdjustedOhlcvRequestV1,
    selection: SelectionRevisionV1,
) -> low.CaptureForwardAdjustedOhlcvRequestV1:
    return _SelectionBoundLowRequestV1(
        cohort=request.cohort,
        schedule=request.schedule,
        decision_session=request.decision_session,
        decision_cutoff=request.decision_cutoff,
        evaluated_at=max(request.evaluated_at, selection.retrieved_at),
        parent_revision_sha256=request.parent_revision_sha256,
        schema_identity_sha256=request.schema_identity_sha256,
        runtime_code_identity_sha256=request.runtime_code_identity_sha256,
        configuration_identity_sha256=request.configuration_identity_sha256,
        contract_version=request.contract_version,
        selection_identity_sha256=selection.selection_identity_sha256,
    )


def _validated_reuse_v1(
    cohort: CohortRequestV1,
    low_request: low.CaptureForwardAdjustedOhlcvRequestV1,
    low_revision: low.AdjustedOhlcvCaptureRevisionV1 | None,
    selection: SelectionRevisionV1,
    request: CurrentNifty100RequestV1,
    *,
    binding_root: Path,
) -> CohortOutcomeV1 | None:
    name = _plan33_binding_name_v1(
        cohort, selection, low_request.request_identity_sha256
    )
    existing = _read_plan33_binding_v1(binding_root, name)
    if existing is None:
        return None
    try:
        parsed_value: object = json.loads(existing)
        if type(parsed_value) is not dict:
            raise ValueError("Plan 33 binding is not an object")
        parsed = cast(dict[str, object], parsed_value)
        revision_sha256 = parsed.get("revision_sha256")
        if (
            type(revision_sha256) is not str
            or len(revision_sha256) != 64
            or any(character not in "0123456789abcdef" for character in revision_sha256)
        ):
            raise ValueError("Plan 33 revision identity is invalid")
        if low_revision is None or revision_sha256 != low_revision.revision_sha256:
            raise ValueError("Plan 33 revision is unavailable")
        reused = low.CaptureForwardAdjustedOhlcvSuccessV1("REUSED", low_revision)
        if existing != _plan33_binding_payload_v1(cohort, reused, selection):
            raise ValueError("Plan 33 binding payload mismatch")
        outcome = _cohort_outcome_v1(cohort, low_request, reused, selection, request)
        if (
            not _is_success(outcome)
            or outcome.selection_identity_sha256 != selection.selection_identity_sha256
        ):
            raise ValueError("Plan 33 reuse binding mismatch")
        return outcome
    except (OSError, RuntimeError, TypeError, ValueError):
        raise EvidenceConflict("Plan 33 binding evidence conflict") from None


def capture_current_nifty100_v1(  # noqa: C901 - one fail-closed capture transaction
    raw_request: bytes,
    *,
    acknowledged: bool,
    selection_root: Path,
    nifty50_root: Path,
    nifty_next50_root: Path,
    schedule_root: Path,
    fetcher: SourceFetcherV1 | None = None,
) -> CurrentNifty100ResultV1 | SharedFailureV1:
    """Run one exact operator-triggered current Nifty 100 capture."""

    preflight = preflight_request_v1(raw_request, acknowledged=acknowledged)
    if preflight is not None:
        return SharedFailureV1(*preflight)
    if not all(
        path.is_absolute()
        for path in (selection_root, nifty50_root, nifty_next50_root, schedule_root)
    ):
        return SharedFailureV1("MALFORMED_INPUT", None)
    try:
        request = parse_request_v1(raw_request)
    except ValueError:
        return SharedFailureV1("MALFORMED_INPUT", None)
    try:
        _runtime_code_identity_v1()
    except RuntimeError:
        return SharedFailureV1("INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID")

    low_requests: list[low.CaptureForwardAdjustedOhlcvRequestV1] = []
    mapping_invalid = False
    schedule_invalid = False
    malformed = False
    for cohort in request.cohorts:
        try:
            low_requests.append(
                low.parse_capture_forward_request_v1(_canonical(cohort.request) + b"\n")
            )
        except low.MappingEvidenceInvalid:
            mapping_invalid = True
        except low.ScheduleEvidenceInvalid:
            schedule_invalid = True
        except ValueError:
            malformed = True
    if malformed:
        return SharedFailureV1("MALFORMED_INPUT", None)

    selection = admit_selection_v1(request, fetcher or OfficialSourceFetcherV1())
    if isinstance(selection, SharedFailureV1):
        return selection
    provider_symbols = [
        member[2]
        for cohort in request.cohorts
        for member in cohort.members
        if member[2]
    ]
    if any(not member[2] for cohort in request.cohorts for member in cohort.members):
        return SharedFailureV1("UNSUPPORTED_CAPABILITY", None)
    if len(provider_symbols) != len(set(provider_symbols)):
        mapping_invalid = True
    if mapping_invalid:
        return SharedFailureV1("INSUFFICIENT_EVIDENCE", "MAPPING_EVIDENCE_INVALID")
    if schedule_invalid:
        return SharedFailureV1("INSUFFICIENT_EVIDENCE", "SCHEDULE_INVALID")
    if len(low_requests) != len(request.cohorts):
        return SharedFailureV1("MALFORMED_INPUT", None)

    if not all(
        low._retained_schedule_matches_request(item, schedule_root)  # pyright: ignore[reportPrivateUsage]
        for item in low_requests
    ):
        return SharedFailureV1("INSUFFICIENT_EVIDENCE", "SCHEDULE_INVALID")
    try:
        retained_selection = _read_retained_selection_v1(selection, selection_root)
    except EvidenceConflict:
        return SharedFailureV1("INSUFFICIENT_EVIDENCE", "EVIDENCE_CONFLICT")
    except (OSError, RuntimeError, ValueError):
        return SharedFailureV1("INSUFFICIENT_EVIDENCE", "RETENTION_FAILED")
    expected_selection = retained_selection or selection
    low_requests = [
        _selection_bound_low_request_v1(item, expected_selection)
        for item in low_requests
    ]

    roots = (nifty50_root, nifty_next50_root)
    low_revisions: list[low.AdjustedOhlcvCaptureRevisionV1 | None] = [None, None]
    for index, (low_request, root) in enumerate(zip(low_requests, roots, strict=True)):
        try:
            low_revisions[index] = low.read_capture_forward_request_revision_v1(
                root, low_request
            )
        except ValueError:
            return SharedFailureV1("INSUFFICIENT_EVIDENCE", "EVIDENCE_CONFLICT")
        except (OSError, RuntimeError):
            return SharedFailureV1("INSUFFICIENT_EVIDENCE", "RETENTION_FAILED")
    try:
        _, selection = resolve_selection_v1(selection, selection_root)
    except EvidenceConflict:
        return SharedFailureV1("INSUFFICIENT_EVIDENCE", "EVIDENCE_CONFLICT")
    except (OSError, RuntimeError, ValueError):
        return SharedFailureV1("INSUFFICIENT_EVIDENCE", "RETENTION_FAILED")
    if selection != expected_selection:
        return SharedFailureV1("INSUFFICIENT_EVIDENCE", "EVIDENCE_CONFLICT")

    outcomes: list[CohortOutcomeV1 | None] = [None, None]
    validated_reuses: list[CohortOutcomeV1 | None] = [None, None]
    for index, (cohort, low_request) in enumerate(
        zip(request.cohorts, low_requests, strict=True)
    ):
        try:
            validated_reuses[index] = _validated_reuse_v1(
                cohort,
                low_request,
                low_revisions[index],
                selection,
                request,
                binding_root=selection_root,
            )
        except EvidenceConflict:
            return SharedFailureV1("INSUFFICIENT_EVIDENCE", "EVIDENCE_CONFLICT")
        except (OSError, RuntimeError, ValueError):
            return SharedFailureV1("INSUFFICIENT_EVIDENCE", "RETENTION_FAILED")

    session: BoundedYahooSessionV1 | None = None
    provider: _Plan33ProviderV1 | None = None
    runtime_unavailable = False
    cleanup_failed = False
    shared_failure: SharedFailureV1 | None = None
    try:
        for index, (cohort, low_request, root) in enumerate(
            zip(request.cohorts, low_requests, roots, strict=True)
        ):
            if validated_reuses[index] is not None:
                outcomes[index] = validated_reuses[index]
                continue
            if _has_effect_stopping_failure(outcomes):
                outcomes[index] = CohortOutcomeV1(
                    cohort.name,
                    "NOT_ATTEMPTED",
                    "BLOCKED_BY_PRIOR_RETENTION_FAILURE",
                )
                continue

            try:
                result = low._capture_forward_adjusted_ohlcv_with_provider_v1(  # pyright: ignore[reportPrivateUsage]
                    low_request, _UnresolvedProbeV1(), root, schedule_root
                )
            except (RuntimeError, ValueError):
                result = low.CaptureForwardAdjustedOhlcvFailureV1(
                    "INSUFFICIENT_EVIDENCE", "RUNTIME_CONFIGURATION_INVALID"
                )
            active_session: BoundedYahooSessionV1 | None = None
            if (
                isinstance(result, low.CaptureForwardAdjustedOhlcvFailureV1)
                and result.reason == "PROVIDER_CALL_FAILED"
            ):
                if runtime_unavailable:
                    outcomes[index] = CohortOutcomeV1(
                        cohort.name,
                        "INSUFFICIENT_EVIDENCE",
                        "CONFIGURATION_INVALID",
                    )
                    continue
                if session is None:
                    try:
                        session = prepare_yfinance_runtime_v1(selection_root)
                    except Exception:
                        runtime_unavailable = True
                        outcomes[index] = CohortOutcomeV1(
                            cohort.name,
                            "INSUFFICIENT_EVIDENCE",
                            "CONFIGURATION_INVALID",
                        )
                        continue
                    provider = _Plan33ProviderV1(session)
                if not _pool_is_exact_v1():
                    outcomes[index] = CohortOutcomeV1(
                        cohort.name,
                        "INSUFFICIENT_EVIDENCE",
                        "CONFIGURATION_INVALID",
                    )
                    continue
                active_provider = cast(_Plan33ProviderV1, provider)
                session.begin_cohort()
                active_session = session
                try:
                    result = low._capture_forward_adjusted_ohlcv_with_provider_v1(  # pyright: ignore[reportPrivateUsage]
                        low_request, active_provider, root, schedule_root
                    )
                except (RuntimeError, ValueError):
                    result = low.CaptureForwardAdjustedOhlcvFailureV1(
                        "INSUFFICIENT_EVIDENCE", "RUNTIME_CONFIGURATION_INVALID"
                    )
            if (
                isinstance(result, low.CaptureForwardAdjustedOhlcvFailureV1)
                and result.reason == "SCHEDULE_EVIDENCE_MISMATCH"
            ):
                shared_failure = SharedFailureV1(
                    "INSUFFICIENT_EVIDENCE", "SCHEDULE_INVALID"
                )
                break
            if (
                isinstance(result, low.CaptureForwardAdjustedOhlcvSuccessV1)
                and session is not None
            ):
                active_session = session

            outcome = _cohort_outcome_v1(
                cohort,
                low_request,
                result,
                selection,
                request,
                active_session,
                binding_root=selection_root
                if isinstance(result, low.CaptureForwardAdjustedOhlcvSuccessV1)
                else None,
            )
            if outcome.reason == "EVIDENCE_CONFLICT":
                shared_failure = SharedFailureV1(
                    "INSUFFICIENT_EVIDENCE", "EVIDENCE_CONFLICT"
                )
                break
            outcomes[index] = outcome
    finally:
        if session is not None:
            try:
                session.close()
            except (OSError, RuntimeError):
                cleanup_failed = True

    if cleanup_failed:
        outcomes = [
            CohortOutcomeV1(
                cohort.name, "INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID"
            )
            for cohort in request.cohorts
        ]
    elif shared_failure is not None:
        return shared_failure

    for index, outcome in enumerate(outcomes):
        if outcome is None:
            outcomes[index] = CohortOutcomeV1(
                request.cohorts[index].name,
                "NOT_ATTEMPTED",
                "BLOCKED_BY_PRIOR_RETENTION_FAILURE",
            )
    finalized = cast(tuple[CohortOutcomeV1, CohortOutcomeV1], tuple(outcomes))
    return _result_v1(
        request,
        selection,
        finalized,
        request_identities=cast(
            tuple[str, str],
            tuple(item.request_identity_sha256 for item in low_requests),
        ),
    )


def serialize_capture_result_v1(
    result: CurrentNifty100ResultV1 | SharedFailureV1,
) -> dict[str, object]:
    if isinstance(result, SharedFailureV1):
        payload: dict[str, object] = {
            "code": result.code,
            "contract_version": CONTRACT_VERSION_V1,
            "reason": result.reason,
        }
        if len(_canonical(payload)) > MAX_RESULT_BYTES_V1:
            raise ValueError("result exceeds public bound")
        return payload
    return serialize_result_v1(result)
