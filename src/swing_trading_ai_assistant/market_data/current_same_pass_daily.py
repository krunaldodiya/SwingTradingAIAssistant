# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false, reportOperatorIssue=false, reportOptionalMemberAccess=false, reportOptionalOperand=false, reportReturnType=false
"""Plan-27 current-only, same-pass raw daily evidence boundary.

This module deliberately has one Upstox implementation.  It never consults
Plan-20 archives and never turns a session timestamp into a knowledge time.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final, Literal, Protocol
from zoneinfo import ZoneInfo

from .adjusted_daily import adjusted_daily_request_identity_v2
from .adjusted_daily.service import _V2Member
from .catalog import DuckDBCatalog
from .current_cohort import (
    CurrentCohortMemberV1,
    CurrentSuppliedCohortAdmissionPolicyV1,
    RetainedCurrentCohortInstrumentResolverV1,
)
from .current_same_pass_daily_runtime_identity_manifest import (
    CURRENT_SAME_PASS_RAW_DAILY_RUNTIME_SOURCE_SHA256_V1,
)
from .instrument_snapshot import (
    InstrumentSnapshotCorruptError,
    InstrumentSnapshotNotFoundError,
    InstrumentSnapshotStoreV1,
    SnapshotInstrumentAmbiguousError,
    SnapshotInstrumentNotFoundError,
)
from .manifest_lifecycle import ManifestState, PartitionManifest, ValidationOutcome
from .monthly_request_planner import PlannedInstrumentMonth
from .partition_publication import provisional_partition_relative_path
from .provisional_metadata import (
    MAX_PROVISIONAL_BYTES_V1,
    MAX_PROVISIONAL_ROWS_V1,
    ProvisionalPartitionMetadataV1,
)
from .public_contract import (
    CoverageStateV1,
    PublicCommandStatusV1,
    QueryPayloadV1,
)
from .public_download import SingleSymbolDownloadRequestV1
from .public_query import QueryRequestV1
from .runtime_source_verifier import runtime_source_sha256
from .schedule_evidence import (
    SCHEDULE_SCHEMA_VERSION_V3,
    ExpectedSessionSchedule,
    ScheduleSession,
    schedule_digest,
)
from .storage_root_lease import StorageRootLease

RAW_DAILY_CONTRACT_VERSION_V1: Final = "current-same-pass-raw-daily-grid@v1"
REQUEST_CONTRACT_VERSION_V3: Final = "current-supplied-cohort-market-regime@v3"
RAW_SCHEMA_CONTRACT_VERSION_V1: Final = (
    "current-supplied-cohort-market-regime-schema@v3"
)
RUNTIME_MANIFEST_VERSION_V1: Final = "plan27-source-at-rest@v1"
_MAX_COHORT_SIZE_V1: Final = 50
_SESSION_COUNT_V1: Final = 21
_MAX_RAW_ROWS_V1: Final = _MAX_COHORT_SIZE_V1 * _SESSION_COUNT_V1
_SAFE_PROVENANCE_PATH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/=-]{0,1023}\Z")
_MAX_RAW_QUERY_ROWS_PER_MEMBER_V1: Final = 10_000
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SYMBOL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_REVISION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@=:+-]{0,127}\Z")
_COMPOSED_RELEASE = re.compile(r"composed-calendar@v1=[0-9a-f]{64}\Z")
_SAFE_PATH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/=-]{0,254}\Z")


class RawDailyReasonV1:
    """Closed, globally ordered current raw insufficiency reasons."""

    COHORT_BINDING_MISMATCH = "COHORT_BINDING_MISMATCH"
    RAW_MAPPING_MISSING = "RAW_MAPPING_MISSING"
    RAW_MAPPING_STALE = "RAW_MAPPING_STALE"
    RAW_MAPPING_CONFLICTED = "RAW_MAPPING_CONFLICTED"
    RAW_ACQUISITION_UNAVAILABLE = "RAW_ACQUISITION_UNAVAILABLE"
    ACQUISITION_DEADLINE_EXCEEDED = "ACQUISITION_DEADLINE_EXCEEDED"
    RAW_BAR_MISSING = "RAW_BAR_MISSING"
    RAW_BAR_STALE = "RAW_BAR_STALE"
    RAW_BAR_CONFLICTED = "RAW_BAR_CONFLICTED"
    RAW_BAR_INVALID = "RAW_BAR_INVALID"
    RAW_BAR_FUTURE_KNOWN = "RAW_BAR_FUTURE_KNOWN"


RAW_DAILY_REASON_ORDER_V1: Final = (
    RawDailyReasonV1.COHORT_BINDING_MISMATCH,
    RawDailyReasonV1.RAW_MAPPING_MISSING,
    RawDailyReasonV1.RAW_MAPPING_STALE,
    RawDailyReasonV1.RAW_MAPPING_CONFLICTED,
    RawDailyReasonV1.RAW_ACQUISITION_UNAVAILABLE,
    RawDailyReasonV1.ACQUISITION_DEADLINE_EXCEEDED,
    RawDailyReasonV1.RAW_BAR_MISSING,
    RawDailyReasonV1.RAW_BAR_STALE,
    RawDailyReasonV1.RAW_BAR_CONFLICTED,
    RawDailyReasonV1.RAW_BAR_INVALID,
    RawDailyReasonV1.RAW_BAR_FUTURE_KNOWN,
)
PARTIAL_REASON_ORDER_V1: Final = (
    "PARTIAL_SOURCE_UNAVAILABLE",
    "PARTIAL_SESSION_MISMATCH",
    "PARTIAL_MEMBER_MISSING",
    "PARTIAL_MEMBER_CONFLICTED",
    "PARTIAL_SNAPSHOT_INVALID",
    "PARTIAL_FUTURE_KNOWN",
)


def _utc(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )


def _instant(value: datetime) -> str:
    if not _utc(value):
        raise ValueError("invalid UTC instant")
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _digest(value: object) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _valid_header(value: object) -> bool:
    return value is None or (
        type(value) is str
        and 1 <= len(value) <= 512
        and all(" " <= character <= "~" for character in value)
    )


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(_value(value))).hexdigest()


def _value(value: object) -> object:
    if type(value) is datetime:
        return _instant(value)
    if type(value) is date:
        return value.isoformat()
    if type(value) is Decimal:
        return _decimal_text(value)
    if type(value) is dict:
        return {str(key): _value(item) for key, item in value.items()}
    if type(value) is list:
        return [_value(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {item.name: _value(getattr(value, item.name)) for item in fields(value)}
    if hasattr(value, "value") and callable(value.value):
        return value.value()
    if type(value) is tuple:
        return [_value(item) for item in value]
    return value


def _identity(value: object, own_field: str) -> str:
    if not hasattr(value, "__dataclass_fields__"):
        raise ValueError("invalid identity projection")
    return _hash(
        {
            item.name: _value(getattr(value, item.name))
            for item in fields(value)
            if item.name != own_field
        }
    )


def _decimal_text(value: object) -> str:
    if type(value) is not Decimal or not value.is_finite() or value <= 0:
        raise ValueError("invalid positive decimal")
    rendered = format(value, "f")
    if rendered.startswith("+") or rendered == "-0" or rendered.endswith("."):
        raise ValueError("invalid positive decimal")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered.startswith("0") and len(rendered) > 1 and rendered[1] != ".":
        raise ValueError("invalid positive decimal")
    return rendered


def _as_decimal(value: object) -> Decimal:
    if type(value) is Decimal:
        result = value
    elif type(value) is str:
        try:
            result = Decimal(value)
        except InvalidOperation as error:
            raise ValueError("invalid positive decimal") from error
    else:
        raise ValueError("invalid positive decimal")
    _decimal_text(result)
    return result


def _valid_isin(value: object) -> bool:
    if type(value) is not str or re.fullmatch(r"[A-Z0-9]{12}", value) is None:
        return False
    digits = "".join(
        character if character.isdigit() else str(ord(character) - 55)
        for character in value
    )
    total = 0
    for position, character in enumerate(reversed(digits)):
        digit = int(character)
        if position % 2:
            digit *= 2
            digit = digit - 9 if digit > 9 else digit
        total += digit
    return total % 10 == 0


def _ordered_reasons(value: object, allowed: tuple[str, ...]) -> tuple[str, ...]:
    if type(value) is not tuple or any(
        type(item) is not str or item not in allowed for item in value
    ):
        raise ValueError("invalid reasons")
    return tuple(item for item in allowed if item in set(value))


@dataclass(frozen=True, slots=True)
class CurrentSamePassEquityMemberV1:
    isin: str
    exchange: Literal["NSE"]
    instrument_type: Literal["EQUITY"]
    segment: Literal["EQ"]
    effective_symbol: str
    valid_from: date
    valid_through: date
    provider_symbol: str
    mapping_version: Literal["yfinance-symbol-mapping@v1"]
    mapping_valid_from: date
    mapping_valid_through: date | None
    mapping_identity: str
    provider_mapping_revision: str

    def __post_init__(self) -> None:
        if (
            not _valid_isin(self.isin)
            or self.exchange != "NSE"
            or self.instrument_type != "EQUITY"
            or self.segment != "EQ"
            or _SYMBOL.fullmatch(self.effective_symbol) is None
            or type(self.valid_from) is not date
            or type(self.valid_through) is not date
            or self.valid_from > self.valid_through
            or type(self.provider_symbol) is not str
            or not 1 <= len(self.provider_symbol.encode()) <= 64
            or self.mapping_version != "yfinance-symbol-mapping@v1"
            or type(self.mapping_valid_from) is not date
            or self.mapping_valid_through is not None
            and type(self.mapping_valid_through) is not date
            or self.mapping_valid_through is not None
            and self.mapping_valid_from > self.mapping_valid_through
            or not _digest(self.mapping_identity)
            or _REVISION.fullmatch(self.provider_mapping_revision) is None
        ):
            raise ValueError("invalid same-pass equity member")

    def value(self) -> dict[str, object]:
        return _value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True, init=False)
class CurrentSamePassMarketRegimeRequestV3:
    contract_version: Literal["current-supplied-cohort-market-regime@v3"]
    decision_cutoff: datetime
    cohort_selected_at: datetime
    members: tuple[CurrentSamePassEquityMemberV1, ...]
    schedule_evidence_sha256: str
    schedule_identity_sha256: str
    plan22_schedule_identity_sha256: str
    schedule_source: Literal["nse-upstox-composed-calendar"]
    schedule_source_release: str
    include_partial_current_session: bool
    plan21_cohort_identity_sha256: str
    canonical_cohort_identity_sha256: str
    plan22_request_identity_sha256: str
    request_identity_sha256: str

    def __init__(
        self,
        contract_version: str,
        decision_cutoff: datetime,
        cohort_selected_at: datetime,
        members: tuple[CurrentSamePassEquityMemberV1, ...],
        schedule_evidence_sha256: str,
        schedule_identity_sha256: str,
        plan22_schedule_identity_sha256: str,
        schedule_source: str,
        schedule_source_release: str,
        include_partial_current_session: bool,
        plan21_cohort_identity_sha256: str,
        canonical_cohort_identity_sha256: str,
        plan22_request_identity_sha256: str,
        request_identity_sha256: str,
    ) -> None:
        if (
            contract_version != REQUEST_CONTRACT_VERSION_V3
            or not _utc(decision_cutoff)
            or not _utc(cohort_selected_at)
            or type(members) is not tuple
            or type(include_partial_current_session) is not bool
            or not all(type(item) is CurrentSamePassEquityMemberV1 for item in members)
            or not 1 <= len(members) <= _MAX_COHORT_SIZE_V1
            or not all(
                _digest(item)
                for item in (
                    schedule_evidence_sha256,
                    schedule_identity_sha256,
                    plan22_schedule_identity_sha256,
                    plan21_cohort_identity_sha256,
                    canonical_cohort_identity_sha256,
                    plan22_request_identity_sha256,
                    request_identity_sha256,
                )
            )
            or schedule_source != "nse-upstox-composed-calendar"
            or _COMPOSED_RELEASE.fullmatch(schedule_source_release) is None
        ):
            raise ValueError("invalid same-pass market-regime request")
        canonical_members = tuple(
            sorted(
                members,
                key=lambda item: (item.isin, item.exchange, item.effective_symbol),
            )
        )
        if len({item.isin for item in canonical_members}) != len(
            canonical_members
        ) or len({item.effective_symbol for item in canonical_members}) != len(
            canonical_members
        ):
            raise ValueError("invalid same-pass market-regime request")
        plan21_identity = _hash(
            {
                "contract_version": "current-supplied-cohort-market-data@v1",
                "selected_at": cohort_selected_at,
                "members": [
                    {"isin": item.isin, "symbol": item.effective_symbol}
                    for item in canonical_members
                ],
            }
        )
        canonical_identity = _hash(
            {
                "contract_version": "current-same-pass-canonical-cohort@v1",
                "cohort_selected_at": cohort_selected_at,
                "members": [item.value() for item in canonical_members],
            }
        )
        if (
            plan21_cohort_identity_sha256 != plan21_identity
            or canonical_cohort_identity_sha256 != canonical_identity
        ):
            raise ValueError("request cohort identity bridge mismatch")
        plan22_identity = adjusted_daily_request_identity_v2(
            cohort_identity_sha256=canonical_identity,
            decision_cutoff=decision_cutoff,
            schedule_identity_sha256=plan22_schedule_identity_sha256,
            members=tuple(
                _V2Member(
                    item.isin,
                    item.exchange,
                    item.instrument_type,
                    item.segment,
                    item.effective_symbol,
                    item.provider_symbol,
                    item.valid_from,
                    item.valid_through,
                    item.mapping_version,
                    item.mapping_valid_from,
                    item.mapping_valid_through,
                    item.mapping_identity,
                )
                for item in canonical_members
            ),
        )
        if plan22_request_identity_sha256 != plan22_identity:
            raise ValueError("request adjusted-daily identity bridge mismatch")
        for field_name, value in (
            ("contract_version", REQUEST_CONTRACT_VERSION_V3),
            ("decision_cutoff", decision_cutoff),
            ("cohort_selected_at", cohort_selected_at),
            ("members", canonical_members),
            ("schedule_evidence_sha256", schedule_evidence_sha256),
            ("schedule_identity_sha256", schedule_identity_sha256),
            ("plan22_schedule_identity_sha256", plan22_schedule_identity_sha256),
            ("schedule_source", schedule_source),
            ("schedule_source_release", schedule_source_release),
            ("include_partial_current_session", include_partial_current_session),
            ("plan21_cohort_identity_sha256", plan21_cohort_identity_sha256),
            ("canonical_cohort_identity_sha256", canonical_cohort_identity_sha256),
            ("plan22_request_identity_sha256", plan22_request_identity_sha256),
        ):
            object.__setattr__(self, field_name, value)
        calculated_request_identity = _identity(self, "request_identity_sha256")
        if request_identity_sha256 != calculated_request_identity:
            raise ValueError("request identity bridge mismatch")
        object.__setattr__(self, "request_identity_sha256", calculated_request_identity)

    def value(self) -> dict[str, object]:
        return _value(self)  # type: ignore[return-value]

    def canonical_json_bytes(self) -> bytes:
        return _canonical(self.value())


@dataclass(frozen=True, slots=True, init=False)
class CurrentSamePassRawSessionV1:
    position: int
    session: date
    open_at: datetime
    close_at: datetime
    kind: Literal["REGULAR", "SPECIAL"]
    session_identity_sha256: str

    def __init__(
        self,
        position: int,
        session: date,
        open_at: datetime,
        close_at: datetime,
        kind: str,
        session_identity_sha256: str | None = None,
    ) -> None:
        if (
            type(position) is not int
            or not 0 <= position < _SESSION_COUNT_V1
            or type(session) is not date
            or not _utc(open_at)
            or not _utc(close_at)
            or close_at <= open_at
            or kind not in {"REGULAR", "SPECIAL"}
        ):
            raise ValueError("invalid same-pass raw session")
        object.__setattr__(self, "position", position)
        object.__setattr__(self, "session", session)
        object.__setattr__(self, "open_at", open_at)
        object.__setattr__(self, "close_at", close_at)
        object.__setattr__(self, "kind", kind)
        calculated = _identity(self, "session_identity_sha256")
        if (
            session_identity_sha256 is not None
            and session_identity_sha256 != calculated
        ):
            raise ValueError("invalid same-pass raw session")
        object.__setattr__(self, "session_identity_sha256", calculated)

    def value(self) -> dict[str, object]:
        return _value(self)  # type: ignore[return-value]


def current_same_pass_schedule_identity_v1(
    *,
    schedule_evidence_sha256: str,
    schedule_source: str,
    schedule_source_release: str,
    timezone: str,
    coverage_through: date,
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
) -> str:
    """Hash the exact composed Plan-27 schedule evidence projection."""
    if (
        not _digest(schedule_evidence_sha256)
        or schedule_source != "nse-upstox-composed-calendar"
        or _COMPOSED_RELEASE.fullmatch(schedule_source_release) is None
        or timezone != "Asia/Kolkata"
        or type(coverage_through) is not date
        or type(sessions) is not tuple
        or len(sessions) != _SESSION_COUNT_V1
        or not all(
            type(item) is CurrentSamePassRawSessionV1
            and item.position == position
            and item.session <= coverage_through
            for position, item in enumerate(sessions)
        )
        or any(
            first.session >= second.session
            for first, second in zip(sessions, sessions[1:], strict=False)
        )
    ):
        raise ValueError("invalid composed Plan27 schedule identity input")
    return _hash(
        {
            "schedule_evidence_sha256": schedule_evidence_sha256,
            "schedule_source": schedule_source,
            "schedule_source_release": schedule_source_release,
            "timezone": timezone,
            "coverage_through": coverage_through,
            "sessions": [
                {
                    "position": item.position,
                    "session": item.session,
                    "open_at": item.open_at,
                    "close_at": item.close_at,
                    "kind": item.kind,
                }
                for item in sessions
            ],
        }
    )


@dataclass(frozen=True, slots=True)
class CurrentSamePassPartialOfficialSessionV1:
    """Private authoritative active-session evidence for the optional partial."""

    session: date
    open_at: datetime
    close_at: datetime
    kind: Literal["REGULAR", "SPECIAL"]
    schedule_identity_sha256: str
    partial_official_session_identity_sha256: str

    def __post_init__(self) -> None:
        valid = (
            type(self.session) is date
            and _utc(self.open_at)
            and _utc(self.close_at)
            and self.close_at > self.open_at
            and self.kind in {"REGULAR", "SPECIAL"}
            and _digest(self.schedule_identity_sha256)
        )
        if not valid or self.partial_official_session_identity_sha256 != _identity(
            self, "partial_official_session_identity_sha256"
        ):
            raise ValueError("invalid same-pass partial official session")

    def value(self) -> dict[str, object]:
        return _value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class CurrentSamePassRawMappingReceiptV1:
    contract_version: Literal["current-same-pass-raw-mapping-receipt@v1"]
    member: CurrentSamePassEquityMemberV1
    snapshot_schema_version: Literal[1]
    snapshot_source: Literal["upstox-bod-nse"]
    observation_date: date
    retrieved_at: datetime
    observation_sha256: str
    compressed_sha256: str
    decompressed_sha256: str
    compressed_byte_count: int
    decompressed_byte_count: int
    relative_object_path: str
    relative_metadata_path: str
    etag: str | None
    last_modified: str | None
    instrument_key: str
    security_id: str
    resolved_symbol: str
    resolved_exchange: Literal["NSE"]
    resolved_segment: Literal["NSE_EQ"]
    resolved_instrument_type: Literal["EQ"]
    resolved_isin: str
    known_at: datetime
    raw_mapping_projection_identity_sha256: str

    def __post_init__(self) -> None:
        if not self._is_exact():
            raise ValueError("invalid same-pass raw mapping receipt")

    def _is_exact(self) -> bool:
        return bool(
            type(self.contract_version) is str
            and self.contract_version == "current-same-pass-raw-mapping-receipt@v1"
            and type(self.member) is CurrentSamePassEquityMemberV1
            and type(self.snapshot_schema_version) is int
            and self.snapshot_schema_version == 1
            and type(self.snapshot_source) is str
            and self.snapshot_source == "upstox-bod-nse"
            and type(self.observation_date) is date
            and _utc(self.retrieved_at)
            and _utc(self.known_at)
            and self.known_at == self.retrieved_at
            and all(
                _digest(item)
                for item in (
                    self.observation_sha256,
                    self.compressed_sha256,
                    self.decompressed_sha256,
                )
            )
            and type(self.compressed_byte_count) is int
            and 0 <= self.compressed_byte_count <= 4_000_000
            and type(self.decompressed_byte_count) is int
            and 0 <= self.decompressed_byte_count <= 50_000_000
            and type(self.relative_object_path) is str
            and _SAFE_PATH.fullmatch(self.relative_object_path) is not None
            and type(self.relative_metadata_path) is str
            and _SAFE_PATH.fullmatch(self.relative_metadata_path) is not None
            and _valid_header(self.etag)
            and _valid_header(self.last_modified)
            and type(self.instrument_key) is str
            and 1 <= len(self.instrument_key.encode()) <= 128
            and _valid_isin(self.security_id)
            and type(self.resolved_symbol) is str
            and _SYMBOL.fullmatch(self.resolved_symbol) is not None
            and self.resolved_symbol == self.member.effective_symbol
            and type(self.resolved_exchange) is str
            and self.resolved_exchange == "NSE"
            and type(self.resolved_segment) is str
            and self.resolved_segment == "NSE_EQ"
            and type(self.resolved_instrument_type) is str
            and self.resolved_instrument_type == "EQ"
            and _valid_isin(self.resolved_isin)
            and self.resolved_isin == self.member.isin
            and _digest(self.raw_mapping_projection_identity_sha256)
            and self.raw_mapping_projection_identity_sha256
            == _identity(self, "raw_mapping_projection_identity_sha256")
        )

    def value(self) -> dict[str, object]:
        return _value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class CurrentSamePassRawCoverageSourceRowV1:
    contract_version: Literal["current-same-pass-raw-coverage-source@v1"]
    isin: str
    session: date
    source_kind: Literal["VERIFIED_MANIFEST", "PROVISIONAL_PARTITION"]
    manifest_schema_version: int | None
    plan_provider: Literal["upstox"]
    plan_instrument_key: str
    plan_security_id: str
    plan_symbol: str
    plan_exchange: Literal["NSE"]
    plan_segment: Literal["NSE_EQ"]
    plan_instrument_type: Literal["EQ"]
    plan_interval: Literal["1m"]
    plan_year: int
    plan_month: int
    plan_from_date: date
    plan_to_date: date
    ingestion_run_id: str | None
    candle_schema_version: int | None
    state: Literal["VERIFIED"] | None
    validation_outcome: Literal["PASSED"] | None
    validation_policy_version: str | None
    actual_from_ts: datetime
    actual_to_ts: datetime
    row_count: int
    checksum_sha256: str
    canonical_path: str
    source_version: str | None
    manifest_created_at: datetime | None
    attempt_started_at: datetime | None
    manifest_updated_at: datetime | None
    failure_category: None
    coverage_state: Literal["VERIFIED", "PROVISIONAL"]
    schedule_digest_sha256: str
    evidence_published_at: datetime | None
    evidence_known_at: datetime | None
    provisional_schema_version: int | None
    provisional_cutoff: datetime | None
    provisional_session_complete: bool | None
    provisional_byte_size: int | None
    provisional_instrument_snapshot_digest_sha256: str | None
    provisional_instrument_snapshot_retrieved_at: datetime | None
    provisional_historical_attempt_count: int | None
    provisional_intraday_attempt_count: int | None
    query_completed_at: datetime
    source_receipt_identity_sha256: str

    def __post_init__(self) -> None:
        common = (
            self.contract_version == "current-same-pass-raw-coverage-source@v1"
            and _valid_isin(self.isin)
            and type(self.session) is date
            and self.plan_provider == "upstox"
            and type(self.plan_instrument_key) is str
            and 1 <= len(self.plan_instrument_key.encode()) <= 128
            and _valid_isin(self.plan_security_id)
            and _SYMBOL.fullmatch(self.plan_symbol) is not None
            and self.plan_exchange == "NSE"
            and self.plan_segment == "NSE_EQ"
            and self.plan_instrument_type == "EQ"
            and self.plan_interval == "1m"
            and type(self.plan_year) is int
            and 2022 <= self.plan_year <= 9999
            and type(self.plan_month) is int
            and 1 <= self.plan_month <= 12
            and type(self.plan_from_date) is date
            and type(self.plan_to_date) is date
            and (self.plan_from_date.year, self.plan_from_date.month)
            == (self.plan_year, self.plan_month)
            and (self.plan_to_date.year, self.plan_to_date.month)
            == (self.plan_year, self.plan_month)
            and self.plan_from_date <= self.plan_to_date
            and all(
                _utc(item)
                for item in (
                    self.actual_from_ts,
                    self.actual_to_ts,
                    self.query_completed_at,
                )
            )
            and self.actual_from_ts <= self.actual_to_ts
            and type(self.row_count) is int
            and 1 <= self.row_count <= 2_147_483_647
            and _digest(self.checksum_sha256)
            and _SAFE_PROVENANCE_PATH.fullmatch(self.canonical_path) is not None
            and _digest(self.schedule_digest_sha256)
        )
        manifest_fields = (
            self.manifest_schema_version,
            self.ingestion_run_id,
            self.candle_schema_version,
            self.state,
            self.validation_outcome,
            self.validation_policy_version,
            self.source_version,
            self.manifest_created_at,
            self.attempt_started_at,
            self.manifest_updated_at,
        )
        provisional_fields = (
            self.provisional_schema_version,
            self.provisional_cutoff,
            self.provisional_session_complete,
            self.provisional_byte_size,
            self.provisional_instrument_snapshot_digest_sha256,
            self.provisional_instrument_snapshot_retrieved_at,
            self.provisional_historical_attempt_count,
            self.provisional_intraday_attempt_count,
        )
        verified = (
            self.source_kind == "VERIFIED_MANIFEST"
            and self.coverage_state == "VERIFIED"
            and type(self.manifest_schema_version) is int
            and 1 <= self.manifest_schema_version <= 2_147_483_647
            and type(self.ingestion_run_id) is str
            and 1 <= len(self.ingestion_run_id.encode()) <= 128
            and type(self.candle_schema_version) is int
            and 1 <= self.candle_schema_version <= 2_147_483_647
            and self.state == "VERIFIED"
            and self.validation_outcome == "PASSED"
            and type(self.validation_policy_version) is str
            and _REVISION.fullmatch(self.validation_policy_version) is not None
            and type(self.source_version) is str
            and _REVISION.fullmatch(self.source_version) is not None
            and all(
                _utc(item)
                for item in (
                    self.manifest_created_at,
                    self.attempt_started_at,
                    self.manifest_updated_at,
                )
            )
            and self.evidence_published_at is None
            and self.evidence_known_at is None
            and all(item is None for item in provisional_fields)
        )
        provisional = (
            self.source_kind == "PROVISIONAL_PARTITION"
            and self.coverage_state == "PROVISIONAL"
            and all(item is None for item in manifest_fields)
            and _utc(self.evidence_published_at)
            and _utc(self.evidence_known_at)
            and self.evidence_published_at == self.evidence_known_at
            and type(self.provisional_schema_version) is int
            and self.provisional_schema_version == 1
            and _utc(self.provisional_cutoff)
            and self.provisional_cutoff.second == 0
            and self.provisional_cutoff.microsecond == 0
            and self.provisional_cutoff == self.actual_to_ts
            and type(self.provisional_session_complete) is bool
            and type(self.provisional_byte_size) is int
            and 1 <= self.provisional_byte_size <= MAX_PROVISIONAL_BYTES_V1
            and _digest(self.provisional_instrument_snapshot_digest_sha256)
            and _utc(self.provisional_instrument_snapshot_retrieved_at)
            and type(self.provisional_historical_attempt_count) is int
            and type(self.provisional_intraday_attempt_count) is int
            and 0 <= self.provisional_historical_attempt_count <= 1
            and 0 <= self.provisional_intraday_attempt_count <= 1
            and self.row_count <= MAX_PROVISIONAL_ROWS_V1
            and self.canonical_path
            in (
                provisional_partition_relative_path(
                    PlannedInstrumentMonth(
                        self.plan_provider,
                        self.plan_instrument_key,
                        self.plan_security_id,
                        self.plan_symbol,
                        self.plan_exchange,
                        self.plan_segment,
                        self.plan_instrument_type,
                        self.plan_interval,
                        self.plan_year,
                        self.plan_month,
                        self.plan_from_date,
                        self.plan_to_date,
                    ),
                    self.provisional_cutoff,
                    self.schedule_digest_sha256,
                ),
                provisional_partition_relative_path(
                    PlannedInstrumentMonth(
                        self.plan_provider,
                        self.plan_instrument_key,
                        self.plan_security_id,
                        self.plan_symbol,
                        self.plan_exchange,
                        self.plan_segment,
                        self.plan_instrument_type,
                        self.plan_interval,
                        self.plan_year,
                        self.plan_month,
                        self.plan_from_date,
                        self.plan_to_date,
                    ),
                    self.provisional_cutoff,
                    self.schedule_digest_sha256,
                    self.checksum_sha256,
                ),
            )
            and self.provisional_cutoff <= self.evidence_published_at
        )
        if (
            not common
            or not (verified or provisional)
            or self.source_receipt_identity_sha256
            != _identity(self, "source_receipt_identity_sha256")
        ):
            raise ValueError("invalid same-pass raw coverage source")

    def value(self) -> dict[str, object]:
        return _value(self)  # type: ignore[return-value]


def _source_evidence_known_at(
    source: CurrentSamePassRawCoverageSourceRowV1,
) -> datetime:
    value = (
        source.manifest_updated_at
        if source.source_kind == "VERIFIED_MANIFEST"
        else source.evidence_known_at
    )
    if value is None:
        raise ValueError("invalid coverage-source known-at")
    return value


@dataclass(frozen=True, slots=True)
class CurrentSamePassRawBarV1:
    isin: str
    session: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    provider: Literal["UPSTOX"]
    price_basis: Literal["RAW"]
    interval: Literal["1d-derived-from-retained-1m"]
    published_at: None
    known_at: datetime
    raw_mapping_projection_identity_sha256: str
    source_receipt_identity_sha256: str
    schedule_identity_sha256: str
    raw_source_policy_identity_sha256: str
    raw_bar_identity_sha256: str

    def __post_init__(self) -> None:
        valid = (
            _valid_isin(self.isin)
            and type(self.session) is date
            and all(
                _as_decimal(item)
                for item in (self.open, self.high, self.low, self.close)
            )
            and self.high >= max(self.open, self.close)
            and self.low <= min(self.open, self.close)
            and type(self.volume) is int
            and 0 <= self.volume <= 18_446_744_073_709_551_615
            and self.provider == "UPSTOX"
            and self.price_basis == "RAW"
            and self.interval == "1d-derived-from-retained-1m"
            and self.published_at is None
            and _utc(self.known_at)
            and all(
                _digest(item)
                for item in (
                    self.raw_mapping_projection_identity_sha256,
                    self.source_receipt_identity_sha256,
                    self.schedule_identity_sha256,
                    self.raw_source_policy_identity_sha256,
                )
            )
        )
        if not valid or self.raw_bar_identity_sha256 != _identity(
            self, "raw_bar_identity_sha256"
        ):
            raise ValueError("invalid same-pass raw bar")

    def value(self) -> dict[str, object]:
        return _value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class CurrentSamePassRawGridV1:
    contract_version: Literal["current-same-pass-raw-daily-grid@v1"]
    schema_identity_sha256: str
    configuration_identity_sha256: str
    runtime_code_identity_sha256: str
    request_identity_sha256: str
    canonical_cohort_identity_sha256: str
    schedule_identity_sha256: str
    latest_completed_session_resolution_identity_sha256: str
    raw_mapping_set_identity_sha256: str
    raw_source_policy_identity_sha256: str
    sessions: tuple[CurrentSamePassRawSessionV1, ...]
    source_rows: tuple[CurrentSamePassRawCoverageSourceRowV1, ...]
    bars: tuple[CurrentSamePassRawBarV1, ...]
    raw_grid_identity_sha256: str

    def __post_init__(self) -> None:
        valid = (
            self.contract_version == RAW_DAILY_CONTRACT_VERSION_V1
            and all(
                _digest(item)
                for item in (
                    self.schema_identity_sha256,
                    self.configuration_identity_sha256,
                    self.runtime_code_identity_sha256,
                    self.request_identity_sha256,
                    self.canonical_cohort_identity_sha256,
                    self.schedule_identity_sha256,
                    self.latest_completed_session_resolution_identity_sha256,
                    self.raw_mapping_set_identity_sha256,
                    self.raw_source_policy_identity_sha256,
                )
            )
            and type(self.sessions) is tuple
            and len(self.sessions) == _SESSION_COUNT_V1
            and tuple(item.position for item in self.sessions)
            == tuple(range(_SESSION_COUNT_V1))
            and all(type(item) is CurrentSamePassRawSessionV1 for item in self.sessions)
            and type(self.source_rows) is tuple
            and type(self.bars) is tuple
            and 1 <= len(self.bars) <= _MAX_RAW_ROWS_V1
            and len(self.source_rows) == len(self.bars)
            and all(
                type(item) is CurrentSamePassRawCoverageSourceRowV1
                for item in self.source_rows
            )
            and all(type(item) is CurrentSamePassRawBarV1 for item in self.bars)
            and tuple((item.isin, item.session) for item in self.bars)
            == tuple(sorted((item.isin, item.session) for item in self.bars))
            and len({(item.isin, item.session) for item in self.bars}) == len(self.bars)
        )
        if not valid or self.raw_grid_identity_sha256 != _identity(
            self, "raw_grid_identity_sha256"
        ):
            raise ValueError("invalid same-pass raw grid")

    def value(self) -> dict[str, object]:
        return _value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class PartialCurrentSessionRowV1:
    isin: str
    session: date
    as_of: datetime
    price: Decimal
    cumulative_volume: int
    provider: Literal["UPSTOX"]
    price_basis: Literal["RAW"]
    source_receipt_identity_sha256: str
    known_at: datetime
    partial_current_session_row_identity_sha256: str

    def __post_init__(self) -> None:
        if not (
            _valid_isin(self.isin)
            and type(self.session) is date
            and _utc(self.as_of)
            and _as_decimal(self.price)
            and type(self.cumulative_volume) is int
            and 0 <= self.cumulative_volume <= 18_446_744_073_709_551_615
            and self.provider == "UPSTOX"
            and self.price_basis == "RAW"
            and _digest(self.source_receipt_identity_sha256)
            and _utc(self.known_at)
            and self.as_of <= self.known_at
            and self.partial_current_session_row_identity_sha256
            == _identity(self, "partial_current_session_row_identity_sha256")
        ):
            raise ValueError("invalid partial row")

    def value(self) -> dict[str, object]:
        return _value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class PartialCurrentSessionSnapshotV1:
    label: Literal["PARTIAL_CURRENT_SESSION"]
    state: Literal[
        "NOT_REQUESTED", "NOT_APPLICABLE", "OBSERVED", "UNAVAILABLE", "CONFLICTED"
    ]
    session: date | None
    as_of: datetime | None
    known_at: datetime | None
    rows: tuple[PartialCurrentSessionRowV1, ...] | None
    reasons: tuple[str, ...]
    partial_snapshot_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            self.label != "PARTIAL_CURRENT_SESSION"
            or self.state
            not in {
                "NOT_REQUESTED",
                "NOT_APPLICABLE",
                "OBSERVED",
                "UNAVAILABLE",
                "CONFLICTED",
            }
            or (self.session is not None and type(self.session) is not date)
            or (self.as_of is not None and not _utc(self.as_of))
            or (self.known_at is not None and not _utc(self.known_at))
            or _ordered_reasons(self.reasons, PARTIAL_REASON_ORDER_V1) != self.reasons
            or (
                self.state == "NOT_REQUESTED"
                and any(
                    item is not None
                    for item in (self.session, self.as_of, self.known_at, self.rows)
                )
            )
            or (
                self.state == "OBSERVED"
                and (
                    self.session is None
                    or self.as_of is None
                    or self.known_at is None
                    or not self.rows
                    or self.reasons
                )
            )
            or self.partial_snapshot_identity_sha256
            != _identity(self, "partial_snapshot_identity_sha256")
        ):
            raise ValueError("invalid partial current-session snapshot")

    def value(self) -> dict[str, object]:
        return _value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class PrivateCurrentSamePassRawDailyResultV1:
    evidence_state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"]
    request_identity_sha256: str
    canonical_cohort_identity_sha256: str
    decision_session: date
    comparison_session: date
    resolved_sessions: tuple[CurrentSamePassRawSessionV1, ...]
    mapping_receipts: tuple[CurrentSamePassRawMappingReceiptV1, ...] | None
    official_active_session: CurrentSamePassPartialOfficialSessionV1 | None
    raw_grid: CurrentSamePassRawGridV1 | None
    partial_current_session: PartialCurrentSessionSnapshotV1
    reasons: tuple[str, ...]
    raw_result_identity_sha256: str

    def __post_init__(self) -> None:
        valid = (
            self.evidence_state in {"OBSERVED", "INSUFFICIENT_EVIDENCE"}
            and _digest(self.request_identity_sha256)
            and _digest(self.canonical_cohort_identity_sha256)
            and type(self.decision_session) is date
            and type(self.comparison_session) is date
            and self.comparison_session < self.decision_session
            and type(self.resolved_sessions) is tuple
            and len(self.resolved_sessions) == _SESSION_COUNT_V1
            and all(
                type(item) is CurrentSamePassRawSessionV1
                for item in self.resolved_sessions
            )
            and (
                self.mapping_receipts is None
                or (
                    type(self.mapping_receipts) is tuple
                    and all(
                        type(item) is CurrentSamePassRawMappingReceiptV1
                        for item in self.mapping_receipts
                    )
                )
            )
            and (
                self.official_active_session is None
                or type(self.official_active_session)
                is CurrentSamePassPartialOfficialSessionV1
            )
            and type(self.partial_current_session) is PartialCurrentSessionSnapshotV1
            and _ordered_reasons(self.reasons, RAW_DAILY_REASON_ORDER_V1)
            == self.reasons
            and (
                (
                    self.evidence_state == "OBSERVED"
                    and type(self.raw_grid) is CurrentSamePassRawGridV1
                    and type(self.mapping_receipts) is tuple
                    and not self.reasons
                )
                or (
                    self.evidence_state == "INSUFFICIENT_EVIDENCE"
                    and self.raw_grid is None
                    and bool(self.reasons)
                )
            )
        )
        if not valid or self.raw_result_identity_sha256 != _identity(
            self, "raw_result_identity_sha256"
        ):
            raise ValueError("invalid same-pass raw result")

    def value(self) -> dict[str, object]:
        return _value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class CurrentSamePassDecisionMarketDataRowV1:
    isin: str
    session: date
    close: Decimal
    volume: int
    provider: Literal["UPSTOX"]
    price_basis: Literal["RAW"]
    published_at: None
    known_at: datetime
    raw_bar_identity_sha256: str
    row_identity_sha256: str

    def __post_init__(self) -> None:
        if not (
            _valid_isin(self.isin)
            and type(self.session) is date
            and _as_decimal(self.close)
            and type(self.volume) is int
            and 0 <= self.volume <= 18_446_744_073_709_551_615
            and self.provider == "UPSTOX"
            and self.price_basis == "RAW"
            and self.published_at is None
            and _utc(self.known_at)
            and _digest(self.raw_bar_identity_sha256)
            and self.row_identity_sha256 == _identity(self, "row_identity_sha256")
        ):
            raise ValueError("invalid decision market-data row")

    def value(self) -> dict[str, object]:
        return _value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class CurrentSamePassDecisionMarketDataReportV1:
    contract_version: Literal["current-same-pass-decision-market-data@v1"]
    schema_identity_sha256: str
    evidence_state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"]
    request_identity_sha256: str
    canonical_cohort_identity_sha256: str
    decision_session: date
    comparison_session: date
    raw_grid_identity_sha256: str | None
    rows: tuple[CurrentSamePassDecisionMarketDataRowV1, ...] | None
    partial_current_session: PartialCurrentSessionSnapshotV1
    reasons: tuple[str, ...]
    report_identity_sha256: str

    def __post_init__(self) -> None:
        valid = (
            self.contract_version == "current-same-pass-decision-market-data@v1"
            and _digest(self.schema_identity_sha256)
            and self.evidence_state in {"OBSERVED", "INSUFFICIENT_EVIDENCE"}
            and _digest(self.request_identity_sha256)
            and _digest(self.canonical_cohort_identity_sha256)
            and type(self.decision_session) is date
            and type(self.comparison_session) is date
            and (
                (
                    self.evidence_state == "OBSERVED"
                    and _digest(self.raw_grid_identity_sha256)
                    and self.rows is not None
                    and not self.reasons
                )
                or (
                    self.evidence_state == "INSUFFICIENT_EVIDENCE"
                    and self.raw_grid_identity_sha256 is None
                    and self.rows is None
                    and bool(self.reasons)
                )
            )
            and type(self.partial_current_session) is PartialCurrentSessionSnapshotV1
            and _ordered_reasons(self.reasons, RAW_DAILY_REASON_ORDER_V1)
            == self.reasons
        )
        if not valid or self.report_identity_sha256 != _identity(
            self, "report_identity_sha256"
        ):
            raise ValueError("invalid decision market-data report")

    def value(self) -> dict[str, object]:
        return _value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class CurrentSamePassAcquisitionCompletionV1:
    """Terminal synchronous download outcome; returned for every attempted call."""

    completed_at: datetime
    outcome: Literal["SUCCEEDED", "FAILED", "EXCEPTION"]
    quiescent: Literal[True]
    reason: str | None

    def __post_init__(self) -> None:
        if (
            not _utc(self.completed_at)
            or self.outcome not in {"SUCCEEDED", "FAILED", "EXCEPTION"}
            or self.quiescent is not True
            or (self.outcome == "SUCCEEDED") != (self.reason is None)
            or (
                self.reason is not None
                and (
                    type(self.reason) is not str
                    or self.reason not in RAW_DAILY_REASON_ORDER_V1
                )
            )
        ):
            raise ValueError("invalid acquisition completion")


class CurrentSamePassAcquisitionOverrunV1(RuntimeError):
    """A started effect returned too late to retain any domain context."""


class CurrentSamePassRawDailyPortV1(Protocol):
    def acquire_exact(
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        sessions: tuple[CurrentSamePassRawSessionV1, ...],
        lease: StorageRootLease,
        *,
        invocation_started_at: datetime | None = None,
        acquisition_effect_deadline: datetime | None = None,
        official_active_session: ScheduleSession | None = None,
        trusted_clock: _TrustedClockV1 | None = None,
    ) -> PrivateCurrentSamePassRawDailyResultV1: ...


class _TrustedClockV1(Protocol):
    def now(self) -> datetime: ...


class CurrentSamePassRawEvidencePortV1(Protocol):
    """Owned projection seam; the default uses only retained catalog/query APIs."""

    def mappings_under_lease(
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        lease: StorageRootLease,
    ) -> tuple[CurrentSamePassRawMappingReceiptV1, ...] | str: ...

    def missing_downloads_under_lease(
        self,
        mappings: tuple[CurrentSamePassRawMappingReceiptV1, ...],
        sessions: tuple[CurrentSamePassRawSessionV1, ...],
        lease: StorageRootLease,
    ) -> tuple[SingleSymbolDownloadRequestV1, ...] | str: ...

    def download_under_lease(
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        missing: tuple[SingleSymbolDownloadRequestV1, ...],
        lease: StorageRootLease,
    ) -> CurrentSamePassAcquisitionCompletionV1: ...

    def partial_current_session_under_lease(
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        mappings: tuple[CurrentSamePassRawMappingReceiptV1, ...],
        active_session: CurrentSamePassPartialOfficialSessionV1,
        lease: StorageRootLease,
    ) -> PartialCurrentSessionSnapshotV1 | str: ...

    def query_and_project_under_lease(
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        mappings: tuple[CurrentSamePassRawMappingReceiptV1, ...],
        sessions: tuple[CurrentSamePassRawSessionV1, ...],
        schedule_identity: str,
        source_policy_identity: str,
        lease: StorageRootLease,
    ) -> (
        tuple[
            tuple[CurrentSamePassRawCoverageSourceRowV1, ...],
            tuple[CurrentSamePassRawBarV1, ...],
        ]
        | str
    ): ...


@dataclass(frozen=True, slots=True)
class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class _AcquisitionDeadlineGateV1:
    deadline: datetime
    clock: _TrustedClockV1

    def __enter__(self) -> _AcquisitionDeadlineGateV1:
        now = self.clock.now()
        if not _utc(now) or now >= self.deadline:
            raise RuntimeError("acquisition deadline exceeded")
        return self

    def __exit__(self, *_: object) -> None:
        return None


@dataclass(frozen=True, slots=True)
class _DefaultCurrentSamePassRawEvidencePortV1:
    storage_root: Path
    schedule_file: Path
    clock: _TrustedClockV1

    def mappings_under_lease(
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        lease: StorageRootLease,
    ) -> tuple[CurrentSamePassRawMappingReceiptV1, ...] | str:
        receipts: list[CurrentSamePassRawMappingReceiptV1] = []
        resolver = RetainedCurrentCohortInstrumentResolverV1(
            self.storage_root, request.decision_cutoff
        )
        for member in request.members:
            try:
                resolved_identity = resolver.resolve_under_lease(
                    CurrentCohortMemberV1(member.isin, member.effective_symbol), lease
                )
                if resolved_identity is None:
                    return RawDailyReasonV1.RAW_MAPPING_CONFLICTED
                with DuckDBCatalog(
                    self.storage_root, read_only=True, lease=lease
                ) as catalog:
                    resolved = InstrumentSnapshotStoreV1(
                        self.storage_root, lease, catalog
                    ).resolve_equity(
                        source="upstox-bod-nse",
                        segment="NSE_EQ",
                        symbol=member.effective_symbol,
                        as_of=request.decision_cutoff,
                    )
                    catalog.ensure_read_identity()
                metadata, instrument = resolved.metadata, resolved.instrument
                if (
                    metadata.observation_date
                    != request.decision_cutoff.astimezone(
                        ZoneInfo("Asia/Kolkata")
                    ).date()
                ):
                    return RawDailyReasonV1.RAW_MAPPING_STALE
                if (
                    resolved_identity.instrument != instrument
                    or resolved_identity.retrieved_at != metadata.retrieved_at
                    or metadata.retrieved_at > request.decision_cutoff
                    or instrument.isin != member.isin
                    or instrument.symbol != member.effective_symbol
                    or instrument.exchange != "NSE"
                    or instrument.segment != "NSE_EQ"
                    or instrument.instrument_type != "EQ"
                ):
                    return RawDailyReasonV1.RAW_MAPPING_CONFLICTED
                values = {
                    "contract_version": "current-same-pass-raw-mapping-receipt@v1",
                    "member": member,
                    "snapshot_schema_version": metadata.schema_version,
                    "snapshot_source": metadata.source,
                    "observation_date": metadata.observation_date,
                    "retrieved_at": metadata.retrieved_at,
                    "observation_sha256": metadata.observation_sha256,
                    "compressed_sha256": metadata.compressed_sha256,
                    "decompressed_sha256": metadata.decompressed_sha256,
                    "compressed_byte_count": metadata.compressed_byte_count,
                    "decompressed_byte_count": metadata.decompressed_byte_count,
                    "relative_object_path": metadata.relative_object_path,
                    "relative_metadata_path": metadata.relative_metadata_path,
                    "etag": metadata.etag,
                    "last_modified": metadata.last_modified,
                    "instrument_key": instrument.instrument_key,
                    "security_id": instrument.security_id,
                    "resolved_symbol": instrument.symbol,
                    "resolved_exchange": instrument.exchange,
                    "resolved_segment": instrument.segment,
                    "resolved_instrument_type": instrument.instrument_type,
                    "resolved_isin": instrument.isin,
                    "known_at": metadata.retrieved_at,
                }
                receipts.append(
                    CurrentSamePassRawMappingReceiptV1(
                        **values,
                        raw_mapping_projection_identity_sha256=_identity_from_values(
                            CurrentSamePassRawMappingReceiptV1,
                            values,
                            "raw_mapping_projection_identity_sha256",
                        ),
                    )
                )
            except (
                InstrumentSnapshotNotFoundError,
                SnapshotInstrumentNotFoundError,
            ):
                return RawDailyReasonV1.RAW_MAPPING_MISSING
            except InstrumentSnapshotCorruptError:
                return RawDailyReasonV1.RAW_MAPPING_STALE
            except SnapshotInstrumentAmbiguousError:
                return RawDailyReasonV1.RAW_MAPPING_CONFLICTED
            except Exception:
                return RawDailyReasonV1.RAW_MAPPING_CONFLICTED
        return tuple(receipts)

    def missing_downloads_under_lease(
        self,
        mappings: tuple[CurrentSamePassRawMappingReceiptV1, ...],
        sessions: tuple[CurrentSamePassRawSessionV1, ...],
        lease: StorageRootLease,
    ) -> tuple[SingleSymbolDownloadRequestV1, ...] | str:
        missing: list[SingleSymbolDownloadRequestV1] = []
        try:
            with DuckDBCatalog(
                self.storage_root, read_only=True, lease=lease
            ) as catalog:
                for mapping in mappings:
                    for plan in _plans_for_mapping(mapping, sessions):
                        manifest = catalog.get_manifest(plan)
                        if manifest is None:
                            missing.append(
                                SingleSymbolDownloadRequestV1(
                                    "NSE_EQ",
                                    mapping.member.effective_symbol,
                                    plan.from_date,
                                    plan.to_date,
                                    self.storage_root,
                                )
                            )
                        elif not _verified_manifest(manifest):
                            return RawDailyReasonV1.RAW_BAR_CONFLICTED
                catalog.ensure_read_identity()
        except Exception:
            return RawDailyReasonV1.RAW_BAR_INVALID
        return tuple(missing)

    def download_under_lease(
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        missing: tuple[SingleSymbolDownloadRequestV1, ...],
        lease: StorageRootLease,
    ) -> CurrentSamePassAcquisitionCompletionV1:
        policy = _cohort_policy(request)
        from .cli import _default_download_service  # noqa: PLC0415

        download = _default_download_service(
            self.schedule_file,
            self.schedule_file,
            policy=policy,
            publication_gate=_AcquisitionDeadlineGateV1(
                request.decision_cutoff - timedelta(seconds=30), self.clock
            ),
        )
        try:
            for download_request in missing:
                report = download.download_under_lease(download_request, lease)
                if report.status is not PublicCommandStatusV1.SUCCEEDED:
                    return CurrentSamePassAcquisitionCompletionV1(
                        self.clock.now(),
                        "FAILED",
                        True,
                        RawDailyReasonV1.RAW_ACQUISITION_UNAVAILABLE,
                    )
            return CurrentSamePassAcquisitionCompletionV1(
                self.clock.now(), "SUCCEEDED", True, None
            )
        except Exception:
            return CurrentSamePassAcquisitionCompletionV1(
                self.clock.now(),
                "EXCEPTION",
                True,
                RawDailyReasonV1.RAW_ACQUISITION_UNAVAILABLE,
            )

    def partial_current_session_under_lease(
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        mappings: tuple[CurrentSamePassRawMappingReceiptV1, ...],
        active_session: CurrentSamePassPartialOfficialSessionV1,
        lease: StorageRootLease,
    ) -> PartialCurrentSessionSnapshotV1 | str:
        """Read each member's last completed retained one-minute bar."""
        from .cli import _default_query_service  # noqa: PLC0415

        as_of = request.decision_cutoff.replace(second=0, microsecond=0) - timedelta(
            minutes=1
        )
        if as_of < active_session.open_at:
            return "PARTIAL_SOURCE_UNAVAILABLE"
        query = _default_query_service(policy=_cohort_policy(request), clock=self.clock)
        completed_rows: list[
            tuple[CurrentSamePassRawMappingReceiptV1, tuple[object, ...]]
        ] = []
        for mapping in mappings:
            report = query.query_under_lease(
                QueryRequestV1(
                    "NSE_EQ",
                    mapping.member.effective_symbol,
                    active_session.session,
                    active_session.session,
                    "1m",
                    ("close", "volume"),
                    10_000,
                    self.storage_root,
                ),
                lease,
            )
            payload = getattr(report, "payload", None)
            values = getattr(payload, "rows", None)
            if (
                report.status is not PublicCommandStatusV1.SUCCEEDED
                or type(values) is not tuple
            ):
                return "PARTIAL_SOURCE_UNAVAILABLE"
            expected_minutes = tuple(
                active_session.open_at + timedelta(minutes=offset)
                for offset in range(
                    int((as_of - active_session.open_at).total_seconds() // 60) + 1
                )
            )
            expected_set = set(expected_minutes)
            completed_by_minute: dict[datetime, object] = {}
            for row in values:
                timestamp = getattr(row, "ts", None)
                if timestamp not in expected_set:
                    return "PARTIAL_MEMBER_CONFLICTED"
                if (
                    getattr(row, "close", None) is None
                    or getattr(row, "volume", None) is None
                    or timestamp in completed_by_minute
                ):
                    return "PARTIAL_MEMBER_CONFLICTED"
                completed_by_minute[timestamp] = row
            if set(completed_by_minute) != expected_set:
                return "PARTIAL_MEMBER_MISSING"
            completed = tuple(
                completed_by_minute[minute] for minute in expected_minutes
            )
            completed_rows.append((mapping, completed))
        known_at = self.clock.now()
        if not _utc(known_at) or known_at > request.decision_cutoff:
            return "PARTIAL_FUTURE_KNOWN"
        rows: list[PartialCurrentSessionRowV1] = []
        for mapping, completed in completed_rows:
            receipt = _hash(
                {
                    "mapping": mapping.raw_mapping_projection_identity_sha256,
                    "official_active_session": active_session.partial_official_session_identity_sha256,
                    "session": active_session.session,
                    "as_of": as_of,
                    "query_known_at": known_at,
                }
            )
            core = {
                "isin": mapping.member.isin,
                "session": active_session.session,
                "as_of": as_of,
                "price": Decimal(str(completed[-1].close)),
                "cumulative_volume": sum(int(row.volume) for row in completed),
                "provider": "UPSTOX",
                "price_basis": "RAW",
                "source_receipt_identity_sha256": receipt,
                "known_at": known_at,
            }
            rows.append(
                PartialCurrentSessionRowV1(
                    **core,
                    partial_current_session_row_identity_sha256=_identity_from_values(
                        PartialCurrentSessionRowV1,
                        core,
                        "partial_current_session_row_identity_sha256",
                    ),
                )
            )
        core = {
            "label": "PARTIAL_CURRENT_SESSION",
            "state": "OBSERVED",
            "session": active_session.session,
            "as_of": as_of,
            "known_at": known_at,
            "rows": tuple(rows),
            "reasons": (),
        }
        return PartialCurrentSessionSnapshotV1(
            **core,
            partial_snapshot_identity_sha256=_identity_from_values(
                PartialCurrentSessionSnapshotV1,
                core,
                "partial_snapshot_identity_sha256",
            ),
        )

    def query_and_project_under_lease(  # noqa: C901
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        mappings: tuple[CurrentSamePassRawMappingReceiptV1, ...],
        sessions: tuple[CurrentSamePassRawSessionV1, ...],
        schedule_identity: str,
        source_policy_identity: str,
        lease: StorageRootLease,
    ) -> (
        tuple[
            tuple[CurrentSamePassRawCoverageSourceRowV1, ...],
            tuple[CurrentSamePassRawBarV1, ...],
        ]
        | str
    ):
        """Aggregate exact official daily bars from bounded retained one-minute rows."""
        from .cli import _default_query_service  # noqa: PLC0415

        if _expected_minute_count(sessions) > _MAX_RAW_QUERY_ROWS_PER_MEMBER_V1:
            return RawDailyReasonV1.RAW_BAR_INVALID
        query = _default_query_service(policy=_cohort_policy(request), clock=self.clock)
        source_rows: list[CurrentSamePassRawCoverageSourceRowV1] = []
        bars: list[CurrentSamePassRawBarV1] = []
        for mapping in mappings:
            try:
                report = query.query_under_lease(
                    QueryRequestV1(
                        "NSE_EQ",
                        mapping.member.effective_symbol,
                        sessions[0].session,
                        sessions[-1].session,
                        "1m",
                        ("open", "high", "low", "close", "volume"),
                        _MAX_RAW_QUERY_ROWS_PER_MEMBER_V1,
                        self.storage_root,
                    ),
                    lease,
                )
                completed_at = self.clock.now()
                if not _utc(completed_at):
                    return RawDailyReasonV1.RAW_BAR_INVALID
                if completed_at > request.decision_cutoff:
                    return RawDailyReasonV1.RAW_BAR_FUTURE_KNOWN
                if (
                    report.status is not PublicCommandStatusV1.SUCCEEDED
                    or type(report.payload) is not QueryPayloadV1
                ):
                    return RawDailyReasonV1.RAW_BAR_MISSING
                aggregated = _aggregate_retained_minutes(sessions, report.payload.rows)
                if type(aggregated) is str:
                    return aggregated
                bindings = _source_bindings_for_mapping(
                    self.storage_root,
                    request,
                    mapping,
                    sessions,
                    report.payload.months,
                    completed_at,
                    lease,
                )
                if type(bindings) is str:
                    return bindings
                for session in sessions:
                    plan, evidence, evidence_schedule_digest = bindings[
                        (session.session.year, session.session.month)
                    ]
                    source = _coverage_source_row(
                        mapping,
                        session,
                        plan,
                        evidence,
                        evidence_schedule_digest,
                        completed_at,
                    )
                    known_at = max(
                        mapping.retrieved_at,
                        _source_evidence_known_at(source),
                        completed_at,
                    )
                    if known_at > request.decision_cutoff:
                        return RawDailyReasonV1.RAW_BAR_FUTURE_KNOWN
                    open_value, high, low, close, volume = aggregated[session.session]
                    bar_values = {
                        "isin": mapping.member.isin,
                        "session": session.session,
                        "open": open_value,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": volume,
                        "provider": "UPSTOX",
                        "price_basis": "RAW",
                        "interval": "1d-derived-from-retained-1m",
                        "published_at": None,
                        "known_at": known_at,
                        "raw_mapping_projection_identity_sha256": (
                            mapping.raw_mapping_projection_identity_sha256
                        ),
                        "source_receipt_identity_sha256": (
                            source.source_receipt_identity_sha256
                        ),
                        "schedule_identity_sha256": schedule_identity,
                        "raw_source_policy_identity_sha256": source_policy_identity,
                    }
                    source_rows.append(source)
                    bars.append(
                        CurrentSamePassRawBarV1(
                            **bar_values,
                            raw_bar_identity_sha256=_identity_from_values(
                                CurrentSamePassRawBarV1,
                                bar_values,
                                "raw_bar_identity_sha256",
                            ),
                        )
                    )
            except Exception:
                return RawDailyReasonV1.RAW_BAR_INVALID
        return tuple(source_rows), tuple(bars)


class UpstoxCurrentSamePassRawDailyV1:
    """Acquire and prove a current 21×N raw grid under one supplied live lease."""

    def __init__(
        self,
        storage_root: Path,
        schedule_file: Path,
        *,
        clock: _TrustedClockV1 | None = None,
        evidence_port: CurrentSamePassRawEvidencePortV1 | None = None,
    ) -> None:
        if type(storage_root) is not type(Path()) or type(schedule_file) is not type(
            Path()
        ):
            raise ValueError("invalid raw daily adapter")
        self._storage_root = storage_root
        self._schedule_file = schedule_file
        self._clock = clock or _SystemClock()
        self._evidence_port = evidence_port

    def acquire_exact(  # noqa: C901
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        sessions: tuple[CurrentSamePassRawSessionV1, ...],
        lease: StorageRootLease,
        *,
        invocation_started_at: datetime | None = None,
        acquisition_effect_deadline: datetime | None = None,
        official_active_session: ScheduleSession | None = None,
        trusted_clock: _TrustedClockV1 | None = None,
    ) -> PrivateCurrentSamePassRawDailyResultV1:
        _admit_sessions(request, sessions)
        if type(lease) is not StorageRootLease:
            raise TypeError("invalid storage-root lease")
        clock = self._clock if trusted_clock is None else trusted_clock
        invocation = (
            clock.now() if invocation_started_at is None else invocation_started_at
        )
        deadline = (
            request.decision_cutoff - timedelta(seconds=30)
            if acquisition_effect_deadline is None
            else acquisition_effect_deadline
        )
        if (
            not _utc(invocation)
            or not _utc(deadline)
            or deadline != request.decision_cutoff - timedelta(seconds=30)
            or request.decision_cutoff < invocation + timedelta(seconds=60)
            or request.decision_cutoff > invocation + timedelta(minutes=30)
        ):
            raise ValueError("decision cutoff outside invocation lead window")
        evidence = self._evidence_port or _DefaultCurrentSamePassRawEvidencePortV1(
            self._storage_root, self._schedule_file, clock
        )
        schedule_identity = _schedule_identity(request, sessions)
        active: CurrentSamePassPartialOfficialSessionV1 | None = None
        partial = (
            _not_requested_partial()
            if not request.include_partial_current_session
            else _not_applicable_partial()
        )
        if _deadline_reached(clock, deadline):
            return _insufficient(
                request,
                sessions,
                partial,
                (RawDailyReasonV1.ACQUISITION_DEADLINE_EXCEEDED,),
            )
        mappings = evidence.mappings_under_lease(request, lease)
        if type(mappings) is str:
            return _insufficient(request, sessions, partial, (mappings,))
        mapping_reason = _admit_mappings(request, mappings)
        if mapping_reason is not None:
            return _insufficient(
                request,
                sessions,
                partial,
                (mapping_reason,),
            )
        if request.include_partial_current_session:
            if official_active_session is None:
                partial = _not_applicable_partial()
            elif (
                type(official_active_session) is not ScheduleSession
                or official_active_session.trade_date <= sessions[-1].session
                or not (
                    official_active_session.open_at
                    <= request.decision_cutoff
                    < official_active_session.close_at
                )
            ):
                partial = _partial_failure(request, "PARTIAL_SESSION_MISMATCH")
            else:
                active_values = {
                    "session": official_active_session.trade_date,
                    "open_at": official_active_session.open_at,
                    "close_at": official_active_session.close_at,
                    "kind": official_active_session.kind,
                    "schedule_identity_sha256": schedule_identity,
                }
                active = CurrentSamePassPartialOfficialSessionV1(
                    **active_values,
                    partial_official_session_identity_sha256=_identity_from_values(
                        CurrentSamePassPartialOfficialSessionV1,
                        active_values,
                        "partial_official_session_identity_sha256",
                    ),
                )
                try:
                    partial = _admit_partial(
                        request,
                        evidence.partial_current_session_under_lease(
                            request, mappings, active, lease
                        ),
                        active,
                        mappings,
                        sessions,
                    )
                except Exception:
                    partial = _partial_failure(request, "PARTIAL_SOURCE_UNAVAILABLE")
        if _deadline_reached(clock, deadline):
            return _insufficient(
                request,
                sessions,
                partial,
                (RawDailyReasonV1.ACQUISITION_DEADLINE_EXCEEDED,),
                mapping_receipts=mappings,
                official_active_session=active,
            )
        missing = evidence.missing_downloads_under_lease(mappings, sessions, lease)
        if type(missing) is str:
            return _insufficient(
                request,
                sessions,
                partial,
                (missing,),
                mapping_receipts=mappings,
                official_active_session=active,
            )
        if type(missing) is not tuple or any(
            type(item) is not SingleSymbolDownloadRequestV1 for item in missing
        ):
            return _insufficient(
                request,
                sessions,
                partial,
                (RawDailyReasonV1.RAW_BAR_INVALID,),
                mapping_receipts=mappings,
                official_active_session=active,
            )
        if missing:
            try:
                completion = evidence.download_under_lease(request, missing, lease)
            except Exception as error:
                raise CurrentSamePassAcquisitionOverrunV1(
                    "acquisition completion cannot be proved"
                ) from error
            returned_at = clock.now()
            if (
                type(completion) is not CurrentSamePassAcquisitionCompletionV1
                or not _utc(returned_at)
                or completion.quiescent is not True
                or not (
                    invocation <= completion.completed_at <= returned_at <= deadline
                )
            ):
                raise CurrentSamePassAcquisitionOverrunV1(
                    "acquisition completion cannot be proved"
                )
            if completion.outcome != "SUCCEEDED":
                return _insufficient(
                    request,
                    sessions,
                    partial,
                    (
                        completion.reason
                        or RawDailyReasonV1.RAW_ACQUISITION_UNAVAILABLE,
                    ),
                    mapping_receipts=mappings,
                    official_active_session=active,
                )
        source_policy_identity = _source_policy_identity()
        projected = evidence.query_and_project_under_lease(
            request,
            mappings,
            sessions,
            schedule_identity,
            source_policy_identity,
            lease,
        )
        if type(projected) is str:
            return _insufficient(
                request,
                sessions,
                partial,
                (projected,),
                mapping_receipts=mappings,
                official_active_session=active,
            )
        source_rows, bars = projected
        reason = _admit_projected_grid(
            request,
            mappings,
            sessions,
            source_rows,
            bars,
            schedule_identity,
            source_policy_identity,
        )
        if reason is not None:
            return _insufficient(
                request,
                sessions,
                partial,
                (reason,),
                mapping_receipts=mappings,
                official_active_session=active,
            )
        if _deadline_exceeded(clock, deadline):
            return _insufficient(
                request,
                sessions,
                partial,
                (RawDailyReasonV1.ACQUISITION_DEADLINE_EXCEEDED,),
                mapping_receipts=mappings,
                official_active_session=active,
            )
        grid_values = {
            "contract_version": RAW_DAILY_CONTRACT_VERSION_V1,
            "schema_identity_sha256": current_same_pass_raw_daily_schema_identity_v1(),
            "configuration_identity_sha256": _configuration_identity(),
            "runtime_code_identity_sha256": current_same_pass_raw_daily_runtime_code_identity_v1(),
            "request_identity_sha256": request.request_identity_sha256,
            "canonical_cohort_identity_sha256": request.canonical_cohort_identity_sha256,
            "schedule_identity_sha256": schedule_identity,
            "latest_completed_session_resolution_identity_sha256": _latest_completed_session_resolution_identity(
                request, sessions, schedule_identity
            ),
            "raw_mapping_set_identity_sha256": _hash(
                {
                    "request_identity_sha256": request.request_identity_sha256,
                    "mappings": [
                        item.raw_mapping_projection_identity_sha256 for item in mappings
                    ],
                }
            ),
            "raw_source_policy_identity_sha256": source_policy_identity,
            "sessions": sessions,
            "source_rows": source_rows,
            "bars": bars,
        }
        grid = CurrentSamePassRawGridV1(
            **grid_values,
            raw_grid_identity_sha256=_identity_from_values(
                CurrentSamePassRawGridV1, grid_values, "raw_grid_identity_sha256"
            ),
        )
        result_values = {
            "evidence_state": "OBSERVED",
            "request_identity_sha256": request.request_identity_sha256,
            "canonical_cohort_identity_sha256": request.canonical_cohort_identity_sha256,
            "decision_session": sessions[-1].session,
            "comparison_session": sessions[0].session,
            "resolved_sessions": sessions,
            "mapping_receipts": mappings,
            "official_active_session": active,
            "raw_grid": grid,
            "partial_current_session": partial,
            "reasons": (),
        }
        return PrivateCurrentSamePassRawDailyResultV1(
            **result_values,
            raw_result_identity_sha256=_identity_from_values(
                PrivateCurrentSamePassRawDailyResultV1,
                result_values,
                "raw_result_identity_sha256",
            ),
        )


def _latest_completed_session_resolution_identity(
    request: CurrentSamePassMarketRegimeRequestV3,
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
    schedule_identity: str,
) -> str:
    return _hash(
        {
            "decision_cutoff": request.decision_cutoff,
            "schedule_identity_sha256": schedule_identity,
            "decision_session": sessions[-1].session,
            "S0": sessions[0].session,
            "S20": sessions[-1].session,
        }
    )


def _identity_from_values(
    model: type[object], values: dict[str, object], own_field: str
) -> str:
    return _hash(
        {
            field.name: _value(values[field.name])
            for field in fields(model)
            if field.name != own_field
        }
    )


def _cohort_policy(
    request: CurrentSamePassMarketRegimeRequestV3,
) -> CurrentSuppliedCohortAdmissionPolicyV1:
    return CurrentSuppliedCohortAdmissionPolicyV1(
        tuple(
            CurrentCohortMemberV1(item.isin, item.effective_symbol)
            for item in request.members
        )
    )


def _plans_for_mapping(
    mapping: CurrentSamePassRawMappingReceiptV1,
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
) -> tuple[PlannedInstrumentMonth, ...]:
    plans: list[PlannedInstrumentMonth] = []
    first, last = sessions[0].session, sessions[-1].session
    for offset in range((last.year - first.year) * 12 + last.month - first.month + 1):
        month_index = first.month - 1 + offset
        year, month = first.year + month_index // 12, month_index % 12 + 1
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        plans.append(
            PlannedInstrumentMonth(
                "upstox",
                mapping.instrument_key,
                mapping.security_id,
                mapping.resolved_symbol,
                mapping.resolved_exchange,
                mapping.resolved_segment,
                mapping.resolved_instrument_type,
                "1m",
                year,
                month,
                first if offset == 0 else date(year, month, 1),
                last
                if year == last.year and month == last.month
                else date(next_year, next_month, 1) - timedelta(days=1),
            )
        )
    return tuple(plans)


def _verified_manifest(value: object) -> bool:
    return bool(
        type(value) is PartitionManifest
        and value.state is ManifestState.VERIFIED
        and value.validation_outcome is ValidationOutcome.PASSED
        and value.failure_category is None
        and all(
            getattr(value, name) is not None
            for name in (
                "candle_schema_version",
                "actual_from_ts",
                "actual_to_ts",
                "row_count",
                "checksum_sha256",
                "canonical_path",
            )
        )
    )


def _source_bindings_for_mapping(
    storage_root: Path,
    request: CurrentSamePassMarketRegimeRequestV3,
    mapping: CurrentSamePassRawMappingReceiptV1,
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
    coverage_months: tuple[object, ...],
    query_completed_at: datetime,
    lease: StorageRootLease,
) -> (
    dict[
        tuple[int, int],
        tuple[
            PlannedInstrumentMonth,
            PartitionManifest | ProvisionalPartitionMetadataV1,
            str,
        ],
    ]
    | str
):
    try:
        plans = _plans_for_mapping(mapping, sessions)
        coverage = {getattr(item, "month", None): item for item in coverage_months}
        if len(coverage) != len(coverage_months) or set(coverage) != {
            f"{plan.year:04d}-{plan.month:02d}" for plan in plans
        }:
            return RawDailyReasonV1.RAW_BAR_CONFLICTED
        current_month = request.decision_cutoff.astimezone(ZoneInfo("Asia/Kolkata"))
        output: dict[
            tuple[int, int],
            tuple[
                PlannedInstrumentMonth,
                PartitionManifest | ProvisionalPartitionMetadataV1,
                str,
            ],
        ] = {}
        with DuckDBCatalog(storage_root, read_only=True, lease=lease) as catalog:
            for plan in plans:
                month = coverage[f"{plan.year:04d}-{plan.month:02d}"]
                if (plan.year, plan.month) != (current_month.year, current_month.month):
                    manifest = catalog.get_manifest(plan)
                    if type(manifest) is not PartitionManifest or not (
                        _coverage_matches_manifest(month, manifest)
                    ):
                        return RawDailyReasonV1.RAW_BAR_CONFLICTED
                    output[(plan.year, plan.month)] = (
                        plan,
                        manifest,
                        month.schedule_digest_sha256,
                    )
                    continue
                provisional = catalog.latest_provisional_partition_for_symbol(
                    segment="NSE_EQ",
                    symbol=mapping.member.effective_symbol,
                    year=plan.year,
                    month=plan.month,
                    cutoff_lte=query_completed_at,
                    published_at_lte=query_completed_at,
                )
                if type(provisional) is not ProvisionalPartitionMetadataV1:
                    return RawDailyReasonV1.RAW_BAR_MISSING
                if not _coverage_matches_provisional(month, provisional, request):
                    return RawDailyReasonV1.RAW_BAR_CONFLICTED
                provisional_plan = provisional.plan
                if provisional_plan != plan:
                    return RawDailyReasonV1.RAW_BAR_CONFLICTED
                output[(plan.year, plan.month)] = (
                    provisional_plan,
                    provisional,
                    provisional.schedule_digest_sha256,
                )
            catalog.ensure_read_identity()
        return output
    except Exception:
        return RawDailyReasonV1.RAW_BAR_INVALID


def _coverage_matches_provisional(
    coverage: object,
    metadata: ProvisionalPartitionMetadataV1,
    request: CurrentSamePassMarketRegimeRequestV3,
) -> bool:
    return bool(
        type(coverage).__name__ == "PublicCoverageMonthV1"
        and coverage.coverage_state is CoverageStateV1.PROVISIONAL
        and coverage.actual_from_ts == metadata.actual_from_ts
        and coverage.actual_to_ts == metadata.actual_to_ts
        and coverage.row_count == metadata.row_count
        and coverage.checksum_sha256 == metadata.checksum_sha256
        and coverage.candle_schema_version == 1
        and coverage.validation_policy_version is None
        and coverage.data_cutoff == metadata.cutoff
        and coverage.session_complete == metadata.session_complete
        and coverage.schedule_digest_sha256 == request.schedule_evidence_sha256
        and coverage.failure_category is None
        and coverage.evidence_published_at == metadata.published_at
        and coverage.evidence_known_at == metadata.published_at
        and metadata.schedule_digest_sha256 == request.schedule_evidence_sha256
        and metadata.published_at <= request.decision_cutoff
        and metadata.instrument_snapshot_retrieved_at <= request.decision_cutoff
    )


def _coverage_source_row(
    mapping: CurrentSamePassRawMappingReceiptV1,
    session: CurrentSamePassRawSessionV1,
    plan: PlannedInstrumentMonth,
    evidence: PartitionManifest | ProvisionalPartitionMetadataV1,
    schedule_digest_sha256: str,
    query_completed_at: datetime,
) -> CurrentSamePassRawCoverageSourceRowV1:
    values: dict[str, object] = {
        "contract_version": "current-same-pass-raw-coverage-source@v1",
        "isin": mapping.member.isin,
        "session": session.session,
        "plan_provider": plan.provider,
        "plan_instrument_key": plan.instrument_key,
        "plan_security_id": plan.security_id,
        "plan_symbol": plan.symbol,
        "plan_exchange": plan.exchange,
        "plan_segment": plan.segment,
        "plan_instrument_type": plan.instrument_type,
        "plan_interval": plan.interval,
        "plan_year": plan.year,
        "plan_month": plan.month,
        "plan_from_date": plan.from_date,
        "plan_to_date": plan.to_date,
        "failure_category": None,
        "query_completed_at": query_completed_at,
    }
    if type(evidence) is PartitionManifest:
        values.update(
            {
                "source_kind": "VERIFIED_MANIFEST",
                "manifest_schema_version": evidence.manifest_schema_version,
                "ingestion_run_id": evidence.ingestion_run_id,
                "candle_schema_version": evidence.candle_schema_version,
                "state": evidence.state.value,
                "validation_outcome": evidence.validation_outcome.value,
                "validation_policy_version": evidence.validation_policy_version,
                "actual_from_ts": evidence.actual_from_ts,
                "actual_to_ts": evidence.actual_to_ts,
                "row_count": evidence.row_count,
                "checksum_sha256": evidence.checksum_sha256,
                "canonical_path": evidence.canonical_path,
                "source_version": evidence.source_version,
                "manifest_created_at": evidence.created_at,
                "attempt_started_at": evidence.attempt_started_at,
                "manifest_updated_at": evidence.updated_at,
                "coverage_state": "VERIFIED",
                "schedule_digest_sha256": schedule_digest_sha256,
                "evidence_published_at": None,
                "evidence_known_at": None,
                "provisional_schema_version": None,
                "provisional_cutoff": None,
                "provisional_session_complete": None,
                "provisional_byte_size": None,
                "provisional_instrument_snapshot_digest_sha256": None,
                "provisional_instrument_snapshot_retrieved_at": None,
                "provisional_historical_attempt_count": None,
                "provisional_intraday_attempt_count": None,
            }
        )
    else:
        values.update(
            {
                "source_kind": "PROVISIONAL_PARTITION",
                "manifest_schema_version": None,
                "ingestion_run_id": None,
                "candle_schema_version": None,
                "state": None,
                "validation_outcome": None,
                "validation_policy_version": None,
                "actual_from_ts": evidence.actual_from_ts,
                "actual_to_ts": evidence.actual_to_ts,
                "row_count": evidence.row_count,
                "checksum_sha256": evidence.checksum_sha256,
                "canonical_path": evidence.relative_path,
                "source_version": None,
                "manifest_created_at": None,
                "attempt_started_at": None,
                "manifest_updated_at": None,
                "coverage_state": "PROVISIONAL",
                "schedule_digest_sha256": evidence.schedule_digest_sha256,
                "evidence_published_at": evidence.published_at,
                "evidence_known_at": evidence.published_at,
                "provisional_schema_version": evidence.schema_version,
                "provisional_cutoff": evidence.cutoff,
                "provisional_session_complete": evidence.session_complete,
                "provisional_byte_size": evidence.byte_size,
                "provisional_instrument_snapshot_digest_sha256": (
                    evidence.instrument_snapshot_digest_sha256
                ),
                "provisional_instrument_snapshot_retrieved_at": (
                    evidence.instrument_snapshot_retrieved_at
                ),
                "provisional_historical_attempt_count": (
                    evidence.historical_attempt_count
                ),
                "provisional_intraday_attempt_count": evidence.intraday_attempt_count,
            }
        )
    return CurrentSamePassRawCoverageSourceRowV1(
        **values,
        source_receipt_identity_sha256=_identity_from_values(
            CurrentSamePassRawCoverageSourceRowV1,
            values,
            "source_receipt_identity_sha256",
        ),
    )


def _expected_minute_count(sessions: tuple[CurrentSamePassRawSessionV1, ...]) -> int:
    total = 0
    for session in sessions:
        seconds = (session.close_at - session.open_at).total_seconds()
        if seconds <= 0 or seconds % 60:
            return _MAX_RAW_QUERY_ROWS_PER_MEMBER_V1 + 1
        total += int(seconds // 60)
    return total


def _aggregate_retained_minutes(  # noqa: C901
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
    rows: tuple[object, ...],
) -> dict[date, tuple[Decimal, Decimal, Decimal, Decimal, int]] | str:
    expected: dict[datetime, date] = {}
    for session in sessions:
        minute = session.open_at
        while minute < session.close_at:
            if minute in expected:
                return RawDailyReasonV1.RAW_BAR_CONFLICTED
            expected[minute] = session.session
            minute += timedelta(minutes=1)
    if len(expected) > _MAX_RAW_QUERY_ROWS_PER_MEMBER_V1:
        return RawDailyReasonV1.RAW_BAR_INVALID
    observed: dict[datetime, object] = {}
    for row in rows:
        timestamp = getattr(row, "ts", None)
        if type(timestamp) is not datetime or not _utc(timestamp):
            return RawDailyReasonV1.RAW_BAR_INVALID
        if timestamp not in expected:
            return RawDailyReasonV1.RAW_BAR_CONFLICTED
        if timestamp in observed:
            return RawDailyReasonV1.RAW_BAR_CONFLICTED
        values = tuple(
            getattr(row, field, None) for field in ("open", "high", "low", "close")
        )
        volume = getattr(row, "volume", None)
        if any(value is None for value in values) or volume is None:
            return RawDailyReasonV1.RAW_BAR_MISSING
        try:
            open_value, high, low, close = tuple(
                _as_decimal(str(value)) for value in values
            )
        except (InvalidOperation, ValueError):
            return RawDailyReasonV1.RAW_BAR_INVALID
        if (
            type(volume) is not int
            or not 0 <= volume <= 18_446_744_073_709_551_615
            or high < max(open_value, close, low)
            or low > min(open_value, close, high)
        ):
            return RawDailyReasonV1.RAW_BAR_INVALID
        observed[timestamp] = (
            open_value,
            high,
            low,
            close,
            volume,
        )
    if len(observed) != len(expected):
        return RawDailyReasonV1.RAW_BAR_MISSING
    aggregated: dict[date, tuple[Decimal, Decimal, Decimal, Decimal, int]] = {}
    for session in sessions:
        minute = session.open_at
        session_rows: list[tuple[Decimal, Decimal, Decimal, Decimal, int]] = []
        while minute < session.close_at:
            row = observed.get(minute)
            if type(row) is not tuple:
                return RawDailyReasonV1.RAW_BAR_MISSING
            session_rows.append(row)  # type: ignore[arg-type]
            minute += timedelta(minutes=1)
        if not session_rows:
            return RawDailyReasonV1.RAW_BAR_MISSING
        open_value = session_rows[0][0]
        high = max(row[1] for row in session_rows)
        low = min(row[2] for row in session_rows)
        close = session_rows[-1][3]
        volume = sum(row[4] for row in session_rows)
        if (
            high < max(open_value, close, low)
            or low > min(open_value, close, high)
            or volume > 18_446_744_073_709_551_615
        ):
            return RawDailyReasonV1.RAW_BAR_INVALID
        aggregated[session.session] = (open_value, high, low, close, volume)
    return aggregated


def _coverage_matches_manifest(
    coverage: object,
    manifest: PartitionManifest,
) -> bool:
    return bool(
        type(coverage).__name__ == "PublicCoverageMonthV1"
        and coverage.coverage_state is CoverageStateV1.VERIFIED
        and coverage.actual_from_ts == manifest.actual_from_ts
        and coverage.actual_to_ts == manifest.actual_to_ts
        and coverage.row_count == manifest.row_count
        and coverage.checksum_sha256 == manifest.checksum_sha256
        and coverage.candle_schema_version == manifest.candle_schema_version
        and coverage.validation_policy_version == manifest.validation_policy_version
        and _digest(coverage.schedule_digest_sha256)
        and coverage.failure_category is None
        and coverage.evidence_published_at is None
        and coverage.evidence_known_at is None
    )


def _deadline_reached(clock: _TrustedClockV1, deadline: datetime) -> bool:
    now = clock.now()
    if not _utc(now):
        raise ValueError("trusted clock unavailable")
    return now >= deadline


def _admit_mappings(
    request: CurrentSamePassMarketRegimeRequestV3,
    mappings: tuple[CurrentSamePassRawMappingReceiptV1, ...],
) -> str | None:
    if (
        type(mappings) is not tuple
        or len(mappings) != len(request.members)
        or any(
            type(item) is not CurrentSamePassRawMappingReceiptV1 for item in mappings
        )
    ):
        return RawDailyReasonV1.RAW_MAPPING_CONFLICTED
    try:
        if tuple(item.member for item in mappings) != request.members:
            return RawDailyReasonV1.RAW_MAPPING_CONFLICTED
        cutoff_date = request.decision_cutoff.astimezone(
            ZoneInfo("Asia/Kolkata")
        ).date()
        for item in mappings:
            if not item._is_exact():
                return RawDailyReasonV1.RAW_MAPPING_CONFLICTED
            if item.observation_date != cutoff_date:
                return RawDailyReasonV1.RAW_MAPPING_STALE
            if (
                not _utc(item.retrieved_at)
                or not _utc(item.known_at)
                or item.known_at != item.retrieved_at
                or item.retrieved_at > request.decision_cutoff
            ):
                return RawDailyReasonV1.RAW_MAPPING_CONFLICTED
    except (AttributeError, TypeError, ValueError):
        return RawDailyReasonV1.RAW_MAPPING_CONFLICTED
    return None


def _deadline_exceeded(clock: _TrustedClockV1, deadline: datetime) -> bool:
    now = clock.now()
    if not _utc(now):
        raise ValueError("trusted clock unavailable")
    return now > deadline


def _schedule_identity(
    request: CurrentSamePassMarketRegimeRequestV3,
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
) -> str:
    """Use the request's authoritative V3 schedule identity, never a local rehash."""
    del sessions
    return request.schedule_identity_sha256


def _source_policy_identity() -> str:
    return _hash(
        {
            "provider": "UPSTOX",
            "price_basis": "RAW",
            "download_contract": "single-symbol-download@v1",
            "query_contract": "query@v1",
            "current_aware_retained_interval": "1m",
            "daily_calculation": "nse-session-ohlcv@v1",
            "candle_schema": 1,
            "manifest_schema": 1,
            "provisional_partition_schema": 1,
            "validation_policy": "equity-month-validation@v1",
            "adapter_runtime_identity": "plan27-source-at-rest@v1",
        }
    )


def _configuration_preimage_v1() -> dict[str, object]:
    return {
        "contract_version": RAW_DAILY_CONTRACT_VERSION_V1,
        "structural_bounds": {
            "cohort_members": [1, _MAX_COHORT_SIZE_V1],
            "completed_sessions": {"exact": _SESSION_COUNT_V1},
            "mapping_receipts": {
                "observed_exact": "cohort_size",
                "range": [1, _MAX_COHORT_SIZE_V1],
            },
            "completed_source_rows": {
                "exact": "21*cohort_size",
                "range": [_SESSION_COUNT_V1, _MAX_RAW_ROWS_V1],
            },
            "completed_raw_bars": {
                "exact": "21*cohort_size",
                "range": [_SESSION_COUNT_V1, _MAX_RAW_ROWS_V1],
            },
            "optional_partial_rows": {
                "allowed_counts": [0, "cohort_size"],
                "range": [0, _MAX_COHORT_SIZE_V1],
            },
            "per_member_retained_minute_query_rows": {
                "range": [1, _MAX_RAW_QUERY_ROWS_PER_MEMBER_V1],
            },
        },
        "canonicalization": "CJ UTF-8 sorted keys compact no-NaN trailing-LF",
        "reason_order": {
            "raw": list(RAW_DAILY_REASON_ORDER_V1),
            "partial": list(PARTIAL_REASON_ORDER_V1),
        },
        "precedence": (
            "mapping-before-partial-before-coverage; "
            "catalog-errors-fail-closed; missing-ranges-only-download"
        ),
        "raw_source_policy": _source_policy_identity(),
        "partial_policy": {
            "role": "separate-optional-context",
            "failure": "visible-nonfatal-unavailable",
            "completed_projection_use": "forbidden",
        },
        "retention_names_and_limits": {
            "new_raw_archive_names": [],
            "new_raw_archive_byte_limits": [],
            "storage_authority": "caller-supplied-live-StorageRootLease",
        },
    }


def _source_plan_matches(
    source: CurrentSamePassRawCoverageSourceRowV1,
    mapping: CurrentSamePassRawMappingReceiptV1,
    expected: PlannedInstrumentMonth,
) -> bool:
    return bool(
        source.plan_provider == expected.provider == "upstox"
        and source.plan_instrument_key
        == expected.instrument_key
        == mapping.instrument_key
        and source.plan_security_id == expected.security_id == mapping.security_id
        and source.plan_symbol == expected.symbol == mapping.resolved_symbol
        and source.plan_exchange == expected.exchange == "NSE"
        and source.plan_segment == expected.segment == "NSE_EQ"
        and source.plan_instrument_type == expected.instrument_type == "EQ"
        and source.plan_interval == expected.interval == "1m"
        and source.plan_year == expected.year
        and source.plan_month == expected.month
        and source.plan_from_date == expected.from_date
        and source.plan_to_date == expected.to_date
        and source.plan_from_date <= source.session <= source.plan_to_date
    )


def _configuration_identity() -> str:
    return _hash(_configuration_preimage_v1())


def _admit_projected_grid(
    request: CurrentSamePassMarketRegimeRequestV3,
    mappings: tuple[CurrentSamePassRawMappingReceiptV1, ...],
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
    source_rows: tuple[CurrentSamePassRawCoverageSourceRowV1, ...],
    bars: tuple[CurrentSamePassRawBarV1, ...],
    schedule_identity: str,
    source_policy_identity: str,
) -> str | None:
    expected = tuple(
        (member.isin, session.session)
        for member in request.members
        for session in sessions
    )
    if (
        type(source_rows) is not tuple
        or type(bars) is not tuple
        or tuple((item.isin, item.session) for item in source_rows) != expected
        or tuple((item.isin, item.session) for item in bars) != expected
    ):
        return RawDailyReasonV1.RAW_BAR_MISSING
    mapping_by_isin = {item.member.isin: item for item in mappings}
    plans_by_isin_month = {
        mapping.member.isin: {
            (plan.year, plan.month): plan
            for plan in _plans_for_mapping(mapping, sessions)
        }
        for mapping in mappings
    }
    for source, bar in zip(source_rows, bars, strict=True):
        mapping = mapping_by_isin.get(source.isin)
        plan = plans_by_isin_month.get(source.isin, {}).get(
            (source.session.year, source.session.month)
        )
        if (
            mapping is None
            or plan is None
            or not _source_plan_matches(source, mapping, plan)
        ):
            return RawDailyReasonV1.RAW_BAR_CONFLICTED
        source_known_at = _source_evidence_known_at(source)
        if (
            source_known_at > request.decision_cutoff
            or source.query_completed_at > request.decision_cutoff
        ):
            return RawDailyReasonV1.RAW_BAR_FUTURE_KNOWN
        if (
            bar.raw_mapping_projection_identity_sha256
            != mapping.raw_mapping_projection_identity_sha256
            or not sessions[0].session <= source.session <= sessions[-1].session
            or bar.source_receipt_identity_sha256
            != source.source_receipt_identity_sha256
            or bar.schedule_identity_sha256 != schedule_identity
            or bar.raw_source_policy_identity_sha256 != source_policy_identity
            or bar.known_at
            != max(
                mapping.retrieved_at,
                source_known_at,
                source.query_completed_at,
            )
        ):
            return RawDailyReasonV1.RAW_BAR_CONFLICTED
        if bar.known_at > request.decision_cutoff:
            return RawDailyReasonV1.RAW_BAR_FUTURE_KNOWN
    return None


def _partial_snapshot_is_exact(value: object) -> bool:
    if type(value) is not PartialCurrentSessionSnapshotV1:
        return False
    try:
        if (
            value.label != "PARTIAL_CURRENT_SESSION"
            or value.state
            not in {
                "NOT_REQUESTED",
                "NOT_APPLICABLE",
                "OBSERVED",
                "UNAVAILABLE",
                "CONFLICTED",
            }
            or value.partial_snapshot_identity_sha256
            != _identity_from_values(
                PartialCurrentSessionSnapshotV1,
                {
                    item.name: getattr(value, item.name)
                    for item in fields(PartialCurrentSessionSnapshotV1)
                    if item.name != "partial_snapshot_identity_sha256"
                },
                "partial_snapshot_identity_sha256",
            )
        ):
            return False
        if value.state in {"NOT_REQUESTED", "NOT_APPLICABLE"}:
            return (
                value.session is None
                and value.as_of is None
                and value.known_at is None
                and value.rows is None
                and value.reasons == ()
            )
        if value.state in {"UNAVAILABLE", "CONFLICTED"}:
            return (
                type(value.session) is date
                and value.as_of is None
                and value.known_at is None
                and value.rows is None
                and value.reasons
                == _ordered_reasons(value.reasons, PARTIAL_REASON_ORDER_V1)
            )
        return bool(
            type(value.session) is date
            and _utc(value.as_of)
            and _utc(value.known_at)
            and type(value.rows) is tuple
            and value.rows
            and value.reasons == ()
            and all(
                type(row) is PartialCurrentSessionRowV1
                and row.session == value.session
                and row.as_of == value.as_of
                and row.known_at <= value.known_at
                and row.partial_current_session_row_identity_sha256
                == _identity_from_values(
                    PartialCurrentSessionRowV1,
                    {
                        item.name: getattr(row, item.name)
                        for item in fields(PartialCurrentSessionRowV1)
                        if item.name != "partial_current_session_row_identity_sha256"
                    },
                    "partial_current_session_row_identity_sha256",
                )
                for row in value.rows
            )
        )
    except (AttributeError, TypeError, ValueError):
        return False


def current_same_pass_raw_daily_result_is_exact_valid_v1(  # noqa: C901
    value: object, request: CurrentSamePassMarketRegimeRequestV3
) -> bool:
    """Revalidate retained raw evidence before a context can be archived."""
    if (
        type(value) is not PrivateCurrentSamePassRawDailyResultV1
        or type(request) is not CurrentSamePassMarketRegimeRequestV3
        or not _partial_snapshot_is_exact(value.partial_current_session)
        or value.request_identity_sha256 != request.request_identity_sha256
        or value.canonical_cohort_identity_sha256
        != request.canonical_cohort_identity_sha256
    ):
        return False
    try:
        expected_result_identity = _identity_from_values(
            PrivateCurrentSamePassRawDailyResultV1,
            {
                item.name: getattr(value, item.name)
                for item in fields(PrivateCurrentSamePassRawDailyResultV1)
                if item.name != "raw_result_identity_sha256"
            },
            "raw_result_identity_sha256",
        )
        _admit_sessions(request, value.resolved_sessions)
        if (
            value.comparison_session != value.resolved_sessions[0].session
            or value.decision_session != value.resolved_sessions[-1].session
        ):
            return False
        if value.raw_result_identity_sha256 != expected_result_identity:
            return False
        mappings = value.mapping_receipts
        if mappings is not None and _admit_mappings(request, mappings) is not None:
            return False
        partial = value.partial_current_session
        if not request.include_partial_current_session:
            if (
                value.official_active_session is not None
                or partial.state != "NOT_REQUESTED"
            ):
                return False
        elif partial.state == "OBSERVED":
            if (
                mappings is None
                or value.official_active_session is None
                or _admit_partial(
                    request,
                    partial,
                    value.official_active_session,
                    mappings,
                    value.resolved_sessions,
                )
                is not partial
            ):
                return False
        elif partial.state == "NOT_APPLICABLE":
            if value.official_active_session is not None:
                return False
        elif value.official_active_session is None:
            return False
        if value.evidence_state == "INSUFFICIENT_EVIDENCE":
            return value.raw_grid is None and value.reasons == _ordered_reasons(
                value.reasons, RAW_DAILY_REASON_ORDER_V1
            )
        if (
            value.evidence_state != "OBSERVED"
            or value.reasons
            or value.raw_grid is None
            or mappings is None
        ):
            return False
        grid = value.raw_grid
        _admit_sessions(request, grid.sessions)
        if (
            grid.contract_version != RAW_DAILY_CONTRACT_VERSION_V1
            or grid.schema_identity_sha256
            != current_same_pass_raw_daily_schema_identity_v1()
            or grid.configuration_identity_sha256 != _configuration_identity()
            or grid.runtime_code_identity_sha256
            != current_same_pass_raw_daily_runtime_code_identity_v1()
            or grid.request_identity_sha256 != request.request_identity_sha256
            or grid.canonical_cohort_identity_sha256
            != request.canonical_cohort_identity_sha256
            or value.comparison_session != grid.sessions[0].session
            or value.decision_session != grid.sessions[-1].session
            or grid.schedule_identity_sha256 != request.schedule_identity_sha256
            or grid.schedule_identity_sha256
            != _schedule_identity(request, grid.sessions)
            or grid.latest_completed_session_resolution_identity_sha256
            != _latest_completed_session_resolution_identity(
                request, grid.sessions, grid.schedule_identity_sha256
            )
            or grid.raw_source_policy_identity_sha256 != _source_policy_identity()
            or grid.sessions != value.resolved_sessions
            or grid.raw_mapping_set_identity_sha256
            != _hash(
                {
                    "request_identity_sha256": request.request_identity_sha256,
                    "mappings": [
                        item.raw_mapping_projection_identity_sha256 for item in mappings
                    ],
                }
            )
            or len(grid.source_rows) != len(request.members) * _SESSION_COUNT_V1
            or len(grid.bars) != len(grid.source_rows)
            or grid.raw_grid_identity_sha256
            != _identity_from_values(
                CurrentSamePassRawGridV1,
                {
                    item.name: getattr(grid, item.name)
                    for item in fields(CurrentSamePassRawGridV1)
                    if item.name != "raw_grid_identity_sha256"
                },
                "raw_grid_identity_sha256",
            )
        ):
            return False
        expected = tuple(
            (member.isin, session.session)
            for member in request.members
            for session in grid.sessions
        )
        if (
            tuple((item.isin, item.session) for item in grid.source_rows) != expected
            or tuple((item.isin, item.session) for item in grid.bars) != expected
        ):
            return False
        for source, bar in zip(grid.source_rows, grid.bars, strict=True):
            if (
                type(source) is not CurrentSamePassRawCoverageSourceRowV1
                or type(bar) is not CurrentSamePassRawBarV1
                or source.source_receipt_identity_sha256
                != _identity_from_values(
                    CurrentSamePassRawCoverageSourceRowV1,
                    {
                        item.name: getattr(source, item.name)
                        for item in fields(CurrentSamePassRawCoverageSourceRowV1)
                        if item.name != "source_receipt_identity_sha256"
                    },
                    "source_receipt_identity_sha256",
                )
                or bar.raw_bar_identity_sha256
                != _identity_from_values(
                    CurrentSamePassRawBarV1,
                    {
                        item.name: getattr(bar, item.name)
                        for item in fields(CurrentSamePassRawBarV1)
                        if item.name != "raw_bar_identity_sha256"
                    },
                    "raw_bar_identity_sha256",
                )
                or bar.source_receipt_identity_sha256
                != source.source_receipt_identity_sha256
                or bar.schedule_identity_sha256 != grid.schedule_identity_sha256
                or bar.raw_source_policy_identity_sha256
                != grid.raw_source_policy_identity_sha256
                or _source_evidence_known_at(source) > request.decision_cutoff
                or source.query_completed_at > request.decision_cutoff
                or bar.known_at > request.decision_cutoff
            ):
                return False
        return (
            _admit_projected_grid(
                request,
                mappings,
                grid.sessions,
                grid.source_rows,
                grid.bars,
                grid.schedule_identity_sha256,
                grid.raw_source_policy_identity_sha256,
            )
            is None
        )
    except (AttributeError, TypeError, ValueError):
        return False


def _schedule_has_complete_v3_calendar(schedule: ExpectedSessionSchedule) -> bool:
    """Require every covered local date to be explicitly classified."""
    classified = {
        *(item.trade_date for item in schedule.sessions),
        *(item.trade_date for item in schedule.closures),
    }
    return (
        schedule.schema_version == SCHEDULE_SCHEMA_VERSION_V3
        and all(item.kind in ("REGULAR", "SPECIAL") for item in schedule.sessions)
        and all(
            current in classified
            for current in (
                schedule.covered_from + timedelta(days=offset)
                for offset in range(
                    (schedule.covered_to - schedule.covered_from).days + 1
                )
            )
        )
    )


def resolve_latest_completed_sessions_v1(
    request: CurrentSamePassMarketRegimeRequestV3,
    schedule: ExpectedSessionSchedule,
) -> tuple[CurrentSamePassRawSessionV1, ...]:
    if (
        type(request) is not CurrentSamePassMarketRegimeRequestV3
        or type(schedule) is not ExpectedSessionSchedule
        or schedule.source != request.schedule_source
        or schedule.source_release != request.schedule_source_release
        or schedule_digest(schedule) != request.schedule_evidence_sha256
        or schedule.as_of > request.decision_cutoff
        or not _schedule_has_complete_v3_calendar(schedule)
        or not schedule.sessions
        or schedule.covered_to
        < request.decision_cutoff.astimezone(ZoneInfo("Asia/Kolkata")).date()
    ):
        raise ValueError("schedule evidence mismatch")
    completed = tuple(
        item for item in schedule.sessions if item.close_at <= request.decision_cutoff
    )
    if len(completed) < _SESSION_COUNT_V1:
        raise ValueError("latest completed session unresolved")
    selected = completed[-_SESSION_COUNT_V1:]
    return tuple(
        CurrentSamePassRawSessionV1(
            position,
            item.trade_date,
            item.open_at,
            item.close_at,
            item.kind,
        )
        for position, item in enumerate(selected)
    )


def _admit_sessions(
    request: CurrentSamePassMarketRegimeRequestV3,
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
) -> None:
    if (
        type(request) is not CurrentSamePassMarketRegimeRequestV3
        or type(sessions) is not tuple
        or len(sessions) != _SESSION_COUNT_V1
        or any(type(item) is not CurrentSamePassRawSessionV1 for item in sessions)
        or tuple(item.position for item in sessions) != tuple(range(_SESSION_COUNT_V1))
        or any(
            left.session >= right.session or left.close_at > right.open_at
            for left, right in zip(sessions, sessions[1:], strict=False)
        )
        or sessions[-1].close_at > request.decision_cutoff
    ):
        raise ValueError("invalid resolved same-pass sessions")
    if any(
        not member.valid_from
        <= sessions[0].session
        <= sessions[-1].session
        <= member.valid_through
        or not member.mapping_valid_from <= sessions[0].session
        or member.mapping_valid_through is not None
        and sessions[-1].session > member.mapping_valid_through
        for member in request.members
    ):
        raise ValueError("member not effective for completed grid")


def _not_requested_partial() -> PartialCurrentSessionSnapshotV1:
    prototype = {
        "label": "PARTIAL_CURRENT_SESSION",
        "state": "NOT_REQUESTED",
        "session": None,
        "as_of": None,
        "known_at": None,
        "rows": None,
        "reasons": [],
    }
    return PartialCurrentSessionSnapshotV1(
        "PARTIAL_CURRENT_SESSION",
        "NOT_REQUESTED",
        None,
        None,
        None,
        None,
        (),
        _hash(prototype),
    )


def _not_applicable_partial() -> PartialCurrentSessionSnapshotV1:
    prototype = {
        "label": "PARTIAL_CURRENT_SESSION",
        "state": "NOT_APPLICABLE",
        "session": None,
        "as_of": None,
        "known_at": None,
        "rows": None,
        "reasons": [],
    }
    return PartialCurrentSessionSnapshotV1(
        "PARTIAL_CURRENT_SESSION",
        "NOT_APPLICABLE",
        None,
        None,
        None,
        None,
        (),
        _hash(prototype),
    )


def _active_market_window(
    request: CurrentSamePassMarketRegimeRequestV3,
    active_session: ScheduleSession | None,
) -> bool:
    """Official schedule, never a weekday/clock heuristic, owns active status."""
    return bool(
        type(active_session) is ScheduleSession
        and active_session.open_at <= request.decision_cutoff < active_session.close_at
    )


def _partial_failure(
    request: CurrentSamePassMarketRegimeRequestV3, reason: str
) -> PartialCurrentSessionSnapshotV1:
    if reason not in PARTIAL_REASON_ORDER_V1:
        reason = "PARTIAL_SNAPSHOT_INVALID"
    state = "CONFLICTED" if reason == "PARTIAL_MEMBER_CONFLICTED" else "UNAVAILABLE"
    core = {
        "label": "PARTIAL_CURRENT_SESSION",
        "state": state,
        "session": request.decision_cutoff.astimezone(ZoneInfo("Asia/Kolkata")).date(),
        "as_of": None,
        "known_at": None,
        "rows": None,
        "reasons": (reason,),
    }
    return PartialCurrentSessionSnapshotV1(
        **core,
        partial_snapshot_identity_sha256=_identity_from_values(
            PartialCurrentSessionSnapshotV1, core, "partial_snapshot_identity_sha256"
        ),
    )


def _admit_partial(
    request: CurrentSamePassMarketRegimeRequestV3,
    value: object,
    active_session: CurrentSamePassPartialOfficialSessionV1,
    mappings: tuple[CurrentSamePassRawMappingReceiptV1, ...],
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
) -> PartialCurrentSessionSnapshotV1:
    completed_minute = request.decision_cutoff.replace(
        second=0, microsecond=0
    ) - timedelta(minutes=1)
    expected_schedule = _schedule_identity(request, sessions)
    if type(value) is str:
        return _partial_failure(request, value)
    if type(value) is not PartialCurrentSessionSnapshotV1:
        return _partial_failure(request, "PARTIAL_SNAPSHOT_INVALID")
    if (
        not request.include_partial_current_session
        or type(active_session) is not CurrentSamePassPartialOfficialSessionV1
        or active_session.schedule_identity_sha256 != expected_schedule
        or active_session.session <= sessions[-1].session
        or not (
            active_session.open_at
            <= completed_minute
            <= value.known_at
            <= request.decision_cutoff
            < active_session.close_at
        )
        or value.state != "OBSERVED"
        or value.session != active_session.session
        or value.as_of != completed_minute
        or value.known_at is None
        or value.rows is None
        or len(value.rows) != len(request.members)
        or tuple(row.isin for row in value.rows)
        != tuple(member.isin for member in request.members)
    ):
        return _partial_failure(request, "PARTIAL_SNAPSHOT_INVALID")
    mapping_by_isin = {item.member.isin: item for item in mappings}
    if any(
        type(row) is not PartialCurrentSessionRowV1
        or row.session != active_session.session
        or row.as_of != completed_minute
        or row.known_at != value.known_at
        or row.source_receipt_identity_sha256
        != _hash(
            {
                "mapping": mapping_by_isin[
                    row.isin
                ].raw_mapping_projection_identity_sha256,
                "official_active_session": active_session.partial_official_session_identity_sha256,
                "session": active_session.session,
                "as_of": completed_minute,
                "query_known_at": value.known_at,
            }
        )
        or row.partial_current_session_row_identity_sha256
        != _identity_from_values(
            PartialCurrentSessionRowV1,
            {
                field.name: getattr(row, field.name)
                for field in fields(PartialCurrentSessionRowV1)
                if field.name != "partial_current_session_row_identity_sha256"
            },
            "partial_current_session_row_identity_sha256",
        )
        for row in value.rows
    ) or value.partial_snapshot_identity_sha256 != _identity_from_values(
        PartialCurrentSessionSnapshotV1,
        {
            field.name: getattr(value, field.name)
            for field in fields(PartialCurrentSessionSnapshotV1)
            if field.name != "partial_snapshot_identity_sha256"
        },
        "partial_snapshot_identity_sha256",
    ):
        return _partial_failure(request, "PARTIAL_SNAPSHOT_INVALID")
    return value


def _insufficient(
    request: CurrentSamePassMarketRegimeRequestV3,
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
    partial: PartialCurrentSessionSnapshotV1,
    reasons: tuple[str, ...],
    *,
    mapping_receipts: tuple[CurrentSamePassRawMappingReceiptV1, ...] | None = None,
    official_active_session: CurrentSamePassPartialOfficialSessionV1 | None = None,
) -> PrivateCurrentSamePassRawDailyResultV1:
    ordered = _ordered_reasons(reasons, RAW_DAILY_REASON_ORDER_V1)
    values = {
        "evidence_state": "INSUFFICIENT_EVIDENCE",
        "request_identity_sha256": request.request_identity_sha256,
        "canonical_cohort_identity_sha256": request.canonical_cohort_identity_sha256,
        "decision_session": sessions[-1].session,
        "comparison_session": sessions[0].session,
        "resolved_sessions": sessions,
        "mapping_receipts": mapping_receipts,
        "official_active_session": official_active_session,
        "raw_grid": None,
        "partial_current_session": partial,
        "reasons": ordered,
    }
    return PrivateCurrentSamePassRawDailyResultV1(
        **values,
        raw_result_identity_sha256=_identity_from_values(
            PrivateCurrentSamePassRawDailyResultV1,
            values,
            "raw_result_identity_sha256",
        ),
    )


_RAW_V3_TYPE_FIELDS_V1: Final = (
    (
        "CurrentSamePassEquityMemberV1",
        (
            "isin",
            "exchange",
            "instrument_type",
            "segment",
            "effective_symbol",
            "valid_from",
            "valid_through",
            "provider_symbol",
            "mapping_version",
            "mapping_valid_from",
            "mapping_valid_through",
            "mapping_identity",
            "provider_mapping_revision",
        ),
    ),
    (
        "CurrentSamePassMarketRegimeRequestV3",
        (
            "contract_version",
            "decision_cutoff",
            "cohort_selected_at",
            "members",
            "schedule_evidence_sha256",
            "schedule_identity_sha256",
            "plan22_schedule_identity_sha256",
            "schedule_source",
            "schedule_source_release",
            "include_partial_current_session",
            "plan21_cohort_identity_sha256",
            "canonical_cohort_identity_sha256",
            "plan22_request_identity_sha256",
            "request_identity_sha256",
        ),
    ),
    (
        "CurrentSamePassRawSessionV1",
        (
            "position",
            "session",
            "open_at",
            "close_at",
            "kind",
            "session_identity_sha256",
        ),
    ),
    (
        "CurrentSamePassPartialOfficialSessionV1",
        (
            "session",
            "open_at",
            "close_at",
            "kind",
            "schedule_identity_sha256",
            "partial_official_session_identity_sha256",
        ),
    ),
    (
        "CurrentSamePassRawMappingReceiptV1",
        (
            "contract_version",
            "member",
            "snapshot_schema_version",
            "snapshot_source",
            "observation_date",
            "retrieved_at",
            "observation_sha256",
            "compressed_sha256",
            "decompressed_sha256",
            "compressed_byte_count",
            "decompressed_byte_count",
            "relative_object_path",
            "relative_metadata_path",
            "etag",
            "last_modified",
            "instrument_key",
            "security_id",
            "resolved_symbol",
            "resolved_exchange",
            "resolved_segment",
            "resolved_instrument_type",
            "resolved_isin",
            "known_at",
            "raw_mapping_projection_identity_sha256",
        ),
    ),
    (
        "CurrentSamePassRawCoverageSourceRowV1",
        (
            "contract_version",
            "isin",
            "session",
            "source_kind",
            "manifest_schema_version",
            "plan_provider",
            "plan_instrument_key",
            "plan_security_id",
            "plan_symbol",
            "plan_exchange",
            "plan_segment",
            "plan_instrument_type",
            "plan_interval",
            "plan_year",
            "plan_month",
            "plan_from_date",
            "plan_to_date",
            "ingestion_run_id",
            "candle_schema_version",
            "state",
            "validation_outcome",
            "validation_policy_version",
            "actual_from_ts",
            "actual_to_ts",
            "row_count",
            "checksum_sha256",
            "canonical_path",
            "source_version",
            "manifest_created_at",
            "attempt_started_at",
            "manifest_updated_at",
            "failure_category",
            "coverage_state",
            "schedule_digest_sha256",
            "evidence_published_at",
            "evidence_known_at",
            "provisional_schema_version",
            "provisional_cutoff",
            "provisional_session_complete",
            "provisional_byte_size",
            "provisional_instrument_snapshot_digest_sha256",
            "provisional_instrument_snapshot_retrieved_at",
            "provisional_historical_attempt_count",
            "provisional_intraday_attempt_count",
            "query_completed_at",
            "source_receipt_identity_sha256",
        ),
    ),
    (
        "CurrentSamePassRawBarV1",
        (
            "isin",
            "session",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "provider",
            "price_basis",
            "interval",
            "published_at",
            "known_at",
            "raw_mapping_projection_identity_sha256",
            "source_receipt_identity_sha256",
            "schedule_identity_sha256",
            "raw_source_policy_identity_sha256",
            "raw_bar_identity_sha256",
        ),
    ),
    (
        "CurrentSamePassRawGridV1",
        (
            "contract_version",
            "schema_identity_sha256",
            "configuration_identity_sha256",
            "runtime_code_identity_sha256",
            "request_identity_sha256",
            "canonical_cohort_identity_sha256",
            "schedule_identity_sha256",
            "latest_completed_session_resolution_identity_sha256",
            "raw_mapping_set_identity_sha256",
            "raw_source_policy_identity_sha256",
            "sessions",
            "source_rows",
            "bars",
            "raw_grid_identity_sha256",
        ),
    ),
    (
        "PartialCurrentSessionRowV1",
        (
            "isin",
            "session",
            "as_of",
            "price",
            "cumulative_volume",
            "provider",
            "price_basis",
            "source_receipt_identity_sha256",
            "known_at",
            "partial_current_session_row_identity_sha256",
        ),
    ),
    (
        "PartialCurrentSessionSnapshotV1",
        (
            "label",
            "state",
            "session",
            "as_of",
            "known_at",
            "rows",
            "reasons",
            "partial_snapshot_identity_sha256",
        ),
    ),
    (
        "PrivateCurrentSamePassRawDailyResultV1",
        (
            "evidence_state",
            "request_identity_sha256",
            "canonical_cohort_identity_sha256",
            "decision_session",
            "comparison_session",
            "resolved_sessions",
            "mapping_receipts",
            "official_active_session",
            "raw_grid",
            "partial_current_session",
            "reasons",
            "raw_result_identity_sha256",
        ),
    ),
    (
        "CurrentSamePassDecisionMarketDataRowV1",
        (
            "isin",
            "session",
            "close",
            "volume",
            "provider",
            "price_basis",
            "published_at",
            "known_at",
            "raw_bar_identity_sha256",
            "row_identity_sha256",
        ),
    ),
    (
        "CurrentSamePassDecisionMarketDataReportV1",
        (
            "contract_version",
            "schema_identity_sha256",
            "evidence_state",
            "request_identity_sha256",
            "canonical_cohort_identity_sha256",
            "decision_session",
            "comparison_session",
            "raw_grid_identity_sha256",
            "rows",
            "partial_current_session",
            "reasons",
            "report_identity_sha256",
        ),
    ),
)
_RAW_V3_SCHEMA_FIELD_ROWS_V1: Final = (
    (
        "CurrentSamePassEquityMemberV1",
        (
            ("isin", "ISIN", "NOT_APPLICABLE", "REQUIRED", "NSE_ISIN_LUHN_12"),
            ("exchange", "LITERAL", "NOT_APPLICABLE", "REQUIRED", 'Literal["NSE"]'),
            (
                "instrument_type",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["EQUITY"]',
            ),
            ("segment", "LITERAL", "NOT_APPLICABLE", "REQUIRED", 'Literal["EQ"]'),
            (
                "effective_symbol",
                "NSE_SYMBOL",
                "NOT_APPLICABLE",
                "REQUIRED",
                "UTF8_BYTES[1..64]",
            ),
            ("valid_from", "LOCAL_DATE", "ISO_8601_DATE", "REQUIRED", "YYYY_MM_DD"),
            ("valid_through", "LOCAL_DATE", "ISO_8601_DATE", "REQUIRED", "YYYY_MM_DD"),
            (
                "provider_symbol",
                "SAFE_TEXT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "UTF8_BYTES[1..64]",
            ),
            (
                "mapping_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["yfinance-symbol-mapping@v1"]',
            ),
            (
                "mapping_valid_from",
                "LOCAL_DATE",
                "ISO_8601_DATE",
                "REQUIRED",
                "YYYY_MM_DD",
            ),
            (
                "mapping_valid_through",
                "LOCAL_DATE",
                "ISO_8601_DATE",
                "NULLABLE",
                "YYYY_MM_DD",
            ),
            (
                "mapping_identity",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "provider_mapping_revision",
                "SAFE_REVISION",
                "NOT_APPLICABLE",
                "REQUIRED",
                "UTF8_BYTES[1..128]",
            ),
        ),
    ),
    (
        "CurrentSamePassMarketRegimeRequestV3",
        (
            (
                "contract_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["current-supplied-cohort-market-regime@v3"]',
            ),
            (
                "decision_cutoff",
                "UTC_INSTANT",
                "UTC",
                "REQUIRED",
                "AWARE_UTC_MICROSECOND",
            ),
            (
                "cohort_selected_at",
                "UTC_INSTANT",
                "UTC",
                "REQUIRED",
                "AWARE_UTC_MICROSECOND",
            ),
            (
                "members",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "tuple[CurrentSamePassEquityMemberV1,1..50]",
            ),
            (
                "schedule_evidence_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "schedule_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "plan22_schedule_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "schedule_source",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["nse-upstox-composed-calendar"]',
            ),
            (
                "schedule_source_release",
                "SOURCE_RELEASE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "composed-calendar@v1=LOWERCASE_64_HEX",
            ),
            (
                "include_partial_current_session",
                "BOOLEAN",
                "BOOLEAN",
                "REQUIRED",
                "EXACT_BOOLEAN",
            ),
            (
                "plan21_cohort_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "canonical_cohort_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "plan22_request_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "request_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "CurrentSamePassRawSessionV1",
        (
            ("position", "INTEGER", "ORDINAL", "REQUIRED", "[0..20]"),
            ("session", "LOCAL_DATE", "ISO_8601_DATE", "REQUIRED", "YYYY_MM_DD"),
            ("open_at", "UTC_INSTANT", "UTC", "REQUIRED", "AWARE_UTC_MICROSECOND"),
            ("close_at", "UTC_INSTANT", "UTC", "REQUIRED", "AWARE_UTC_MICROSECOND"),
            (
                "kind",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["REGULAR","SPECIAL"]',
            ),
            (
                "session_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "CurrentSamePassPartialOfficialSessionV1",
        (
            ("session", "LOCAL_DATE", "ISO_8601_DATE", "REQUIRED", "YYYY_MM_DD"),
            ("open_at", "UTC_INSTANT", "UTC", "REQUIRED", "AWARE_UTC_MICROSECOND"),
            ("close_at", "UTC_INSTANT", "UTC", "REQUIRED", "AWARE_UTC_MICROSECOND"),
            (
                "kind",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["REGULAR","SPECIAL"]',
            ),
            (
                "schedule_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "partial_official_session_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "CurrentSamePassRawMappingReceiptV1",
        (
            (
                "contract_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["current-same-pass-raw-mapping-receipt@v1"]',
            ),
            (
                "member",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "CurrentSamePassEquityMemberV1",
            ),
            (
                "snapshot_schema_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                "Literal[1]",
            ),
            (
                "snapshot_source",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["upstox-bod-nse"]',
            ),
            (
                "observation_date",
                "LOCAL_DATE",
                "ISO_8601_DATE",
                "REQUIRED",
                "YYYY_MM_DD",
            ),
            ("retrieved_at", "UTC_INSTANT", "UTC", "REQUIRED", "AWARE_UTC_MICROSECOND"),
            (
                "observation_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "compressed_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "decompressed_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            ("compressed_byte_count", "INTEGER", "BYTES", "REQUIRED", "[0..4_000_000]"),
            (
                "decompressed_byte_count",
                "INTEGER",
                "BYTES",
                "REQUIRED",
                "[0..50_000_000]",
            ),
            (
                "relative_object_path",
                "SAFE_RELATIVE_PATH",
                "NOT_APPLICABLE",
                "REQUIRED",
                "UTF8_BYTES[1..255]",
            ),
            (
                "relative_metadata_path",
                "SAFE_RELATIVE_PATH",
                "NOT_APPLICABLE",
                "REQUIRED",
                "UTF8_BYTES[1..255]",
            ),
            (
                "etag",
                "SAFE_HEADER",
                "NOT_APPLICABLE",
                "NULLABLE",
                "CONTRACT_VALIDATED_HEADER",
            ),
            (
                "last_modified",
                "SAFE_HEADER",
                "NOT_APPLICABLE",
                "NULLABLE",
                "CONTRACT_VALIDATED_HEADER",
            ),
            (
                "instrument_key",
                "SAFE_TEXT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "UTF8_BYTES[1..128]",
            ),
            ("security_id", "ISIN", "NOT_APPLICABLE", "REQUIRED", "NSE_ISIN_LUHN_12"),
            (
                "resolved_symbol",
                "NSE_SYMBOL",
                "NOT_APPLICABLE",
                "REQUIRED",
                "UTF8_BYTES[1..64]",
            ),
            (
                "resolved_exchange",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["NSE"]',
            ),
            (
                "resolved_segment",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["NSE_EQ"]',
            ),
            (
                "resolved_instrument_type",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["EQ"]',
            ),
            ("resolved_isin", "ISIN", "NOT_APPLICABLE", "REQUIRED", "NSE_ISIN_LUHN_12"),
            ("known_at", "UTC_INSTANT", "UTC", "REQUIRED", "AWARE_UTC_MICROSECOND"),
            (
                "raw_mapping_projection_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "CurrentSamePassRawCoverageSourceRowV1",
        (
            (
                "contract_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["current-same-pass-raw-coverage-source@v1"]',
            ),
            ("isin", "ISIN", "NOT_APPLICABLE", "REQUIRED", "NSE_ISIN_LUHN_12"),
            ("session", "LOCAL_DATE", "ISO_8601_DATE", "REQUIRED", "YYYY_MM_DD"),
            (
                "source_kind",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["VERIFIED_MANIFEST","PROVISIONAL_PARTITION"]',
            ),
            (
                "manifest_schema_version",
                "INTEGER_OR_NONE",
                "VERSION",
                "CONDITIONAL",
                "None|[1,2147483647]",
            ),
            (
                "plan_provider",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["upstox"]',
            ),
            (
                "plan_instrument_key",
                "SAFE_TEXT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "UTF8_BYTES[1..128]",
            ),
            (
                "plan_security_id",
                "ISIN",
                "NOT_APPLICABLE",
                "REQUIRED",
                "NSE_ISIN_LUHN_12",
            ),
            (
                "plan_symbol",
                "NSE_SYMBOL",
                "NOT_APPLICABLE",
                "REQUIRED",
                "UTF8_BYTES[1..64]",
            ),
            (
                "plan_exchange",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["NSE"]',
            ),
            (
                "plan_segment",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["NSE_EQ"]',
            ),
            (
                "plan_instrument_type",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["EQ"]',
            ),
            ("plan_interval", "LITERAL", "NOT_APPLICABLE", "REQUIRED", 'Literal["1m"]'),
            ("plan_year", "INTEGER", "CALENDAR_YEAR", "REQUIRED", "[2022..9999]"),
            ("plan_month", "INTEGER", "CALENDAR_MONTH", "REQUIRED", "[1..12]"),
            ("plan_from_date", "LOCAL_DATE", "ISO_8601_DATE", "REQUIRED", "YYYY_MM_DD"),
            ("plan_to_date", "LOCAL_DATE", "ISO_8601_DATE", "REQUIRED", "YYYY_MM_DD"),
            (
                "ingestion_run_id",
                "SAFE_TEXT_OR_NONE",
                "NOT_APPLICABLE",
                "CONDITIONAL",
                "None|UTF8_BYTES[1..128]",
            ),
            (
                "candle_schema_version",
                "INTEGER_OR_NONE",
                "VERSION",
                "CONDITIONAL",
                "None|[1,2147483647]",
            ),
            (
                "state",
                "LITERAL_OR_NONE",
                "NOT_APPLICABLE",
                "CONDITIONAL",
                'None|Literal["VERIFIED"]',
            ),
            (
                "validation_outcome",
                "LITERAL_OR_NONE",
                "NOT_APPLICABLE",
                "CONDITIONAL",
                'None|Literal["PASSED"]',
            ),
            (
                "validation_policy_version",
                "SAFE_REVISION_OR_NONE",
                "NOT_APPLICABLE",
                "CONDITIONAL",
                "None|UTF8_BYTES[1..128]",
            ),
            (
                "actual_from_ts",
                "UTC_INSTANT",
                "UTC",
                "REQUIRED",
                "AWARE_UTC_MICROSECOND",
            ),
            ("actual_to_ts", "UTC_INSTANT", "UTC", "REQUIRED", "AWARE_UTC_MICROSECOND"),
            ("row_count", "INTEGER", "ROWS", "REQUIRED", "[1,2147483647]"),
            (
                "checksum_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "canonical_path",
                "SAFE_RELATIVE_PATH",
                "NOT_APPLICABLE",
                "REQUIRED",
                "UTF8_BYTES[1..1024]",
            ),
            (
                "source_version",
                "SAFE_REVISION_OR_NONE",
                "NOT_APPLICABLE",
                "CONDITIONAL",
                "None|UTF8_BYTES[1..128]",
            ),
            (
                "manifest_created_at",
                "UTC_INSTANT_OR_NONE",
                "UTC",
                "CONDITIONAL",
                "None|AWARE_UTC_MICROSECOND",
            ),
            (
                "attempt_started_at",
                "UTC_INSTANT_OR_NONE",
                "UTC",
                "CONDITIONAL",
                "None|AWARE_UTC_MICROSECOND",
            ),
            (
                "manifest_updated_at",
                "UTC_INSTANT_OR_NONE",
                "UTC",
                "CONDITIONAL",
                "None|AWARE_UTC_MICROSECOND",
            ),
            (
                "failure_category",
                "EXACT_NONE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LITERAL_NONE",
            ),
            (
                "coverage_state",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["VERIFIED","PROVISIONAL"]',
            ),
            (
                "schedule_digest_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "evidence_published_at",
                "UTC_INSTANT_OR_NONE",
                "UTC",
                "CONDITIONAL",
                "None|AWARE_UTC_MICROSECOND",
            ),
            (
                "evidence_known_at",
                "UTC_INSTANT_OR_NONE",
                "UTC",
                "CONDITIONAL",
                "None|AWARE_UTC_MICROSECOND",
            ),
            (
                "provisional_schema_version",
                "INTEGER_OR_NONE",
                "VERSION",
                "CONDITIONAL",
                "None|Literal[1]",
            ),
            (
                "provisional_cutoff",
                "UTC_INSTANT_OR_NONE",
                "UTC",
                "CONDITIONAL",
                "None|AWARE_UTC_MINUTE",
            ),
            (
                "provisional_session_complete",
                "BOOLEAN_OR_NONE",
                "NOT_APPLICABLE",
                "CONDITIONAL",
                "None|BOOLEAN",
            ),
            (
                "provisional_byte_size",
                "INTEGER_OR_NONE",
                "BYTES",
                "CONDITIONAL",
                "None|[1,67108864]",
            ),
            (
                "provisional_instrument_snapshot_digest_sha256",
                "SHA256_OR_NONE",
                "NOT_APPLICABLE",
                "CONDITIONAL",
                "None|LOWERCASE_64_HEX",
            ),
            (
                "provisional_instrument_snapshot_retrieved_at",
                "UTC_INSTANT_OR_NONE",
                "UTC",
                "CONDITIONAL",
                "None|AWARE_UTC_MICROSECOND",
            ),
            (
                "provisional_historical_attempt_count",
                "INTEGER_OR_NONE",
                "ATTEMPTS",
                "CONDITIONAL",
                "None|[0,1]",
            ),
            (
                "provisional_intraday_attempt_count",
                "INTEGER_OR_NONE",
                "ATTEMPTS",
                "CONDITIONAL",
                "None|[0,1]",
            ),
            (
                "query_completed_at",
                "UTC_INSTANT",
                "UTC",
                "REQUIRED",
                "AWARE_UTC_MICROSECOND",
            ),
            (
                "source_receipt_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "CurrentSamePassRawBarV1",
        (
            ("isin", "ISIN", "NOT_APPLICABLE", "REQUIRED", "NSE_ISIN_LUHN_12"),
            ("session", "LOCAL_DATE", "ISO_8601_DATE", "REQUIRED", "YYYY_MM_DD"),
            (
                "open",
                "DECIMAL_TEXT",
                "INR_PER_SHARE",
                "REQUIRED",
                "FINITE_NON_EXPONENT_POSITIVE",
            ),
            (
                "high",
                "DECIMAL_TEXT",
                "INR_PER_SHARE",
                "REQUIRED",
                "FINITE_NON_EXPONENT_POSITIVE",
            ),
            (
                "low",
                "DECIMAL_TEXT",
                "INR_PER_SHARE",
                "REQUIRED",
                "FINITE_NON_EXPONENT_POSITIVE",
            ),
            (
                "close",
                "DECIMAL_TEXT",
                "INR_PER_SHARE",
                "REQUIRED",
                "FINITE_NON_EXPONENT_POSITIVE",
            ),
            ("volume", "UINT64", "SHARES", "REQUIRED", "[0,18446744073709551615]"),
            ("provider", "LITERAL", "NOT_APPLICABLE", "REQUIRED", 'Literal["UPSTOX"]'),
            ("price_basis", "LITERAL", "NOT_APPLICABLE", "REQUIRED", 'Literal["RAW"]'),
            (
                "interval",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["1d-derived-from-retained-1m"]',
            ),
            (
                "published_at",
                "EXACT_NONE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LITERAL_NONE",
            ),
            ("known_at", "UTC_INSTANT", "UTC", "REQUIRED", "AWARE_UTC_MICROSECOND"),
            (
                "raw_mapping_projection_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "source_receipt_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "schedule_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "raw_source_policy_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "raw_bar_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "CurrentSamePassRawGridV1",
        (
            (
                "contract_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["current-same-pass-raw-daily-grid@v1"]',
            ),
            (
                "schema_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "configuration_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "runtime_code_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "request_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "canonical_cohort_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "schedule_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "latest_completed_session_resolution_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "raw_mapping_set_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "raw_source_policy_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "sessions",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "tuple[CurrentSamePassRawSessionV1,21]",
            ),
            (
                "source_rows",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "tuple[CurrentSamePassRawCoverageSourceRowV1,exact=21*cohort_size;range=21..1050]",
            ),
            (
                "bars",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "tuple[CurrentSamePassRawBarV1,exact=21*cohort_size;range=21..1050]",
            ),
            (
                "raw_grid_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "PartialCurrentSessionRowV1",
        (
            ("isin", "ISIN", "NOT_APPLICABLE", "REQUIRED", "NSE_ISIN_LUHN_12"),
            ("session", "LOCAL_DATE", "ISO_8601_DATE", "REQUIRED", "YYYY_MM_DD"),
            ("as_of", "UTC_INSTANT", "UTC", "REQUIRED", "AWARE_UTC_MICROSECOND"),
            (
                "price",
                "DECIMAL_TEXT",
                "INR_PER_SHARE",
                "REQUIRED",
                "FINITE_NON_EXPONENT_POSITIVE",
            ),
            (
                "cumulative_volume",
                "UINT64",
                "SHARES",
                "REQUIRED",
                "[0,18446744073709551615]",
            ),
            ("provider", "LITERAL", "NOT_APPLICABLE", "REQUIRED", 'Literal["UPSTOX"]'),
            ("price_basis", "LITERAL", "NOT_APPLICABLE", "REQUIRED", 'Literal["RAW"]'),
            (
                "source_receipt_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            ("known_at", "UTC_INSTANT", "UTC", "REQUIRED", "AWARE_UTC_MICROSECOND"),
            (
                "partial_current_session_row_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "PartialCurrentSessionSnapshotV1",
        (
            (
                "label",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["PARTIAL_CURRENT_SESSION"]',
            ),
            (
                "state",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                "ONE_OF[NOT_REQUESTED|NOT_APPLICABLE|OBSERVED|UNAVAILABLE|CONFLICTED]",
            ),
            ("session", "LOCAL_DATE", "ISO_8601_DATE", "NULLABLE", "YYYY_MM_DD"),
            ("as_of", "UTC_INSTANT", "UTC", "NULLABLE", "AWARE_UTC_MICROSECOND"),
            ("known_at", "UTC_INSTANT", "UTC", "NULLABLE", "AWARE_UTC_MICROSECOND"),
            (
                "rows",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "NULLABLE",
                "tuple[PartialCurrentSessionRowV1,count=0_or_cohort_size;range=0..50]",
            ),
            (
                "reasons",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "tuple[PartialReason,0..6]",
            ),
            (
                "partial_snapshot_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "PrivateCurrentSamePassRawDailyResultV1",
        (
            (
                "evidence_state",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["OBSERVED","INSUFFICIENT_EVIDENCE"]',
            ),
            (
                "request_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "canonical_cohort_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "decision_session",
                "LOCAL_DATE",
                "ISO_8601_DATE",
                "REQUIRED",
                "YYYY_MM_DD",
            ),
            (
                "comparison_session",
                "LOCAL_DATE",
                "ISO_8601_DATE",
                "REQUIRED",
                "YYYY_MM_DD",
            ),
            (
                "resolved_sessions",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "tuple[CurrentSamePassRawSessionV1,21]",
            ),
            (
                "mapping_receipts",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "NULLABLE",
                "tuple[CurrentSamePassRawMappingReceiptV1,observed_exact=cohort_size;range=1..50]",
            ),
            (
                "official_active_session",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "NULLABLE",
                "CurrentSamePassPartialOfficialSessionV1",
            ),
            (
                "raw_grid",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "NULLABLE",
                "CurrentSamePassRawGridV1",
            ),
            (
                "partial_current_session",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "PartialCurrentSessionSnapshotV1",
            ),
            (
                "reasons",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "tuple[RawDailyReason,0..11]",
            ),
            (
                "raw_result_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "CurrentSamePassDecisionMarketDataRowV1",
        (
            ("isin", "ISIN", "NOT_APPLICABLE", "REQUIRED", "NSE_ISIN_LUHN_12"),
            ("session", "LOCAL_DATE", "ISO_8601_DATE", "REQUIRED", "YYYY_MM_DD"),
            (
                "close",
                "DECIMAL_TEXT",
                "INR_PER_SHARE",
                "REQUIRED",
                "FINITE_NON_EXPONENT_POSITIVE",
            ),
            ("volume", "UINT64", "SHARES", "REQUIRED", "[0,18446744073709551615]"),
            ("provider", "LITERAL", "NOT_APPLICABLE", "REQUIRED", 'Literal["UPSTOX"]'),
            ("price_basis", "LITERAL", "NOT_APPLICABLE", "REQUIRED", 'Literal["RAW"]'),
            (
                "published_at",
                "EXACT_NONE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LITERAL_NONE",
            ),
            ("known_at", "UTC_INSTANT", "UTC", "REQUIRED", "AWARE_UTC_MICROSECOND"),
            (
                "raw_bar_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "row_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "CurrentSamePassDecisionMarketDataReportV1",
        (
            (
                "contract_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["current-same-pass-decision-market-data@v1"]',
            ),
            (
                "schema_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "evidence_state",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["OBSERVED","INSUFFICIENT_EVIDENCE"]',
            ),
            (
                "request_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "canonical_cohort_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "decision_session",
                "LOCAL_DATE",
                "ISO_8601_DATE",
                "REQUIRED",
                "YYYY_MM_DD",
            ),
            (
                "comparison_session",
                "LOCAL_DATE",
                "ISO_8601_DATE",
                "REQUIRED",
                "YYYY_MM_DD",
            ),
            (
                "raw_grid_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "NULLABLE",
                "LOWERCASE_64_HEX",
            ),
            (
                "rows",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "NULLABLE",
                "tuple[CurrentSamePassDecisionMarketDataRowV1,N]",
            ),
            (
                "partial_current_session",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "PartialCurrentSessionSnapshotV1",
            ),
            (
                "reasons",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "tuple[RawDailyReason,0..11]",
            ),
            (
                "report_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
)


_RAW_V3_STATE_PROJECTIONS_V1: Final = (
    (
        "CurrentSamePassRawCoverageSourceRowV1",
        (
            (
                "VERIFIED_MANIFEST",
                "manifest_schema_version=[1,2147483647],ingestion_run_id=REQUIRED,"
                "candle_schema_version=[1,2147483647],state=VERIFIED,"
                "validation_outcome=PASSED,validation_policy_version=REQUIRED,"
                "source_version=REQUIRED,manifest_created_at=REQUIRED,"
                "attempt_started_at=REQUIRED,manifest_updated_at=REQUIRED,"
                "coverage_state=VERIFIED,evidence_published_at=NONE,"
                "evidence_known_at=NONE,provisional_schema_version=NONE,"
                "provisional_cutoff=NONE,provisional_session_complete=NONE,"
                "provisional_byte_size=NONE,"
                "provisional_instrument_snapshot_digest_sha256=NONE,"
                "provisional_instrument_snapshot_retrieved_at=NONE,"
                "provisional_historical_attempt_count=NONE,"
                "provisional_intraday_attempt_count=NONE,row_count=[1,2147483647]",
            ),
            (
                "PROVISIONAL_PARTITION",
                "manifest_schema_version=NONE,ingestion_run_id=NONE,"
                "candle_schema_version=NONE,state=NONE,validation_outcome=NONE,"
                "validation_policy_version=NONE,source_version=NONE,"
                "manifest_created_at=NONE,attempt_started_at=NONE,"
                "manifest_updated_at=NONE,coverage_state=PROVISIONAL,"
                "evidence_published_at=REQUIRED,evidence_known_at=REQUIRED,"
                "provisional_schema_version=1,provisional_cutoff=REQUIRED,"
                "provisional_session_complete=REQUIRED,"
                "provisional_byte_size=[1,67108864],"
                "provisional_instrument_snapshot_digest_sha256=REQUIRED,"
                "provisional_instrument_snapshot_retrieved_at=REQUIRED,"
                "provisional_historical_attempt_count=[0,1],"
                "provisional_intraday_attempt_count=[0,1],row_count=[1,10000]",
            ),
        ),
    ),
    (
        "PrivateCurrentSamePassRawDailyResultV1",
        (
            (
                "OBSERVED",
                "resolved_sessions=REQUIRED,mapping_receipts=REQUIRED,raw_grid=REQUIRED,reasons=EMPTY",
            ),
            (
                "INSUFFICIENT_EVIDENCE",
                "resolved_sessions=REQUIRED,raw_grid=NONE,reasons=NONEMPTY",
            ),
        ),
    ),
    (
        "CurrentSamePassDecisionMarketDataReportV1",
        (
            (
                "OBSERVED",
                "raw_grid_identity_sha256=REQUIRED,rows=REQUIRED,reasons=EMPTY",
            ),
            (
                "INSUFFICIENT_EVIDENCE",
                "raw_grid_identity_sha256=NONE,rows=NONE,reasons=NONEMPTY",
            ),
        ),
    ),
    (
        "PartialCurrentSessionSnapshotV1",
        (
            (
                "NOT_REQUESTED",
                "session=NONE,as_of=NONE,known_at=NONE,rows=NONE,reasons=EMPTY",
            ),
            (
                "NOT_APPLICABLE",
                "session=NONE,as_of=NONE,known_at=NONE,rows=NONE,reasons=EMPTY",
            ),
            (
                "OBSERVED",
                "session=REQUIRED,as_of=REQUIRED,known_at=REQUIRED,rows=REQUIRED,reasons=EMPTY",
            ),
            (
                "UNAVAILABLE",
                "session=REQUIRED,as_of=NONE,known_at=NONE,rows=NONE,reasons=NONEMPTY",
            ),
            (
                "CONFLICTED",
                "session=REQUIRED,as_of=NONE,known_at=NONE,rows=NONE,reasons=NONEMPTY",
            ),
        ),
    ),
)


def _raw_v3_schema_metadata_v1() -> dict[str, object]:
    """Return the frozen, exhaustive Plan-27 field metadata."""
    field_rows = dict(_RAW_V3_SCHEMA_FIELD_ROWS_V1)
    type_rows = []
    for type_name, ordered_fields in _RAW_V3_TYPE_FIELDS_V1:
        exact_fields = field_rows.get(type_name)
        if (
            exact_fields is None
            or tuple(item[0] for item in exact_fields) != ordered_fields
        ):
            raise ValueError("incomplete exact schema metadata")
        type_rows.append(
            {
                "name": type_name,
                "ordered_fields": tuple(
                    {
                        "name": field_name,
                        "semantic_type": semantic_type,
                        "unit": unit,
                        "nullability": nullability,
                        "bounds": bounds,
                    }
                    for field_name, semantic_type, unit, nullability, bounds in exact_fields
                ),
            }
        )
    return {
        "contract_version": RAW_SCHEMA_CONTRACT_VERSION_V1,
        "type_rows": tuple(type_rows),
        "state_projections": _RAW_V3_STATE_PROJECTIONS_V1,
        "unknown_key_policy": "REJECT",
    }


def current_same_pass_raw_daily_schema_metadata_v1() -> dict[str, object]:
    return _raw_v3_schema_metadata_v1()


def current_same_pass_raw_daily_schema_metadata_digest_v1(metadata: object) -> str:
    if type(metadata) is not dict or set(metadata) != {
        "contract_version",
        "type_rows",
        "state_projections",
        "unknown_key_policy",
    }:
        raise ValueError("unknown raw schema metadata key")
    return _hash(metadata)


def current_same_pass_raw_daily_schema_identity_from_metadata_v1(
    metadata: object,
) -> str:
    if _canonical(metadata) != _canonical(_raw_v3_schema_metadata_v1()):
        raise ValueError("raw schema metadata differs from frozen contract")
    return current_same_pass_raw_daily_schema_metadata_digest_v1(metadata)


def current_same_pass_raw_daily_schema_identity_v1() -> str:
    return current_same_pass_raw_daily_schema_identity_from_metadata_v1(
        _raw_v3_schema_metadata_v1()
    )


def current_same_pass_raw_daily_runtime_code_identity_v1() -> str:
    """Verify exact Plan-27 repository-relative source-at-rest identities."""
    source_path = (
        "src/swing_trading_ai_assistant/market_data/current_same_pass_daily.py"
    )
    manifest_path = (
        "src/swing_trading_ai_assistant/market_data/"
        "current_same_pass_daily_runtime_identity_manifest.py"
    )
    package_root = Path(__file__).resolve().parents[1]
    modules = {
        source_path: __name__,
        manifest_path: (
            "swing_trading_ai_assistant.market_data."
            "current_same_pass_daily_runtime_identity_manifest"
        ),
    }
    try:
        expected = CURRENT_SAME_PASS_RAW_DAILY_RUNTIME_SOURCE_SHA256_V1
        if tuple(expected) != (source_path,):
            raise ValueError
        sources = []
        for relative_path in sorted((source_path, manifest_path)):
            observed = runtime_source_sha256(
                modules[relative_path], package_root, relative_path
            )
            if relative_path == source_path and observed != expected[source_path]:
                raise ValueError
            sources.append({"relative_path": relative_path, "source_sha256": observed})
        return _hash(
            {
                "runtime_manifest_version": RUNTIME_MANIFEST_VERSION_V1,
                "modules": sources,
            }
        )
    except (OSError, ValueError):
        raise ValueError("runtime code identity unavailable") from None
