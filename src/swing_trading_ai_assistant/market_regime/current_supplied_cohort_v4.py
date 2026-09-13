# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false, reportOperatorIssue=false, reportOptionalMemberAccess=false, reportOptionalOperand=false, reportReturnType=false
"""Plan-27 current same-pass Market Regime V4 and sealed context archive.

This module deliberately owns the deterministic V4 composition and immutable
context archive.  Raw acquisition remains behind ``CurrentSamePassRawDailyPortV1``;
the builder never reaches into a provider, retries adjusted acquisition, or
creates a replacement result.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import stat
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final, Literal, Protocol, TypeAlias, cast
from weakref import WeakKeyDictionary
from zoneinfo import ZoneInfo

from swing_trading_ai_assistant.market_data.adjusted_daily.service_v3 import (
    AdjustedDailyCloseFailure,
    AdjustedDailyCloseHandoffV3,
    AdjustedDailyCloseResultV3,
    AdjustedDailyCloseSuccessV3,
    AdjustedDailyInstrumentV3,
    acquire_adjusted_daily_close_v3,
    adjusted_daily_close_handoff_identity_v3,
    adjusted_daily_close_handoff_is_valid_v3,
    adjusted_daily_request_identity_v3,
    adjusted_daily_schedule_identity_v3,
)
from swing_trading_ai_assistant.market_data.bharatstock import (
    PRICE_BASIS,
    BharatStockClient,
    BharatStockPriceBasis,
)
from swing_trading_ai_assistant.market_data.current_cohort import (
    CurrentCohortMemberV1,
    CurrentSuppliedCohortManifestV1,
)
from swing_trading_ai_assistant.market_data.current_corporate_action_screen import (
    CurrentSuppliedCohortCorporateActionScreenInputV1,
    PrivateCorporateActionScreenOutcomeV1,
    PublishedCurrentCorporateActionScreenV1,
    _published_screen_core_valid,
    publish_current_corporate_action_screen_v1,
    published_current_corporate_action_screen_is_exact_valid_v1,
)
from swing_trading_ai_assistant.market_data.current_same_pass_daily_v4 import (
    CurrentSamePassAcquisitionOverrunV1,
    CurrentSamePassDecisionMarketDataReportV1,
    CurrentSamePassDecisionMarketDataRowV1,
    CurrentSamePassEquityMemberV4,
    CurrentSamePassMarketRegimeRequestV4,
    CurrentSamePassRawDailyPortV1,
    CurrentSamePassRawGridV1,
    CurrentSamePassRawSessionV1,
    PartialCurrentSessionSnapshotV1,
    PrivateCurrentSamePassRawDailyResultV1,
    _identity_from_values,
    current_same_pass_raw_daily_result_is_exact_valid_v4,
    current_same_pass_raw_daily_runtime_code_identity_v4,
    current_same_pass_raw_daily_schema_identity_v4,
    current_same_pass_schedule_identity_v1,
    resolve_latest_completed_sessions_v1,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256 as _runtime_source_sha256,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    same_metadata as _same_metadata,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleEvidenceStore,
    ScheduleOutcome,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

__all__ = (
    "CurrentSamePassEquityMemberV4",
    "CurrentSamePassRawGridV1",
)

CONTRACT_VERSION: Final = "current-supplied-cohort-market-regime@v4"
PREFLIGHT_FAILURE_CONTRACT_VERSION: Final = "current-same-pass-preflight-failure@v1"
SCHEMA_CONTRACT_VERSION: Final = "current-supplied-cohort-market-regime-schema@v4"
CALCULATION_CONTRACT_VERSION: Final = (
    "current-supplied-cohort-market-regime-calculation@v4"
)
ARCHIVE_CONTRACT_VERSION: Final = "current-same-pass-market-context-archive@v2"
ADJUSTED_NOT_ATTEMPTED_CONTRACT_VERSION: Final = (
    "current-same-pass-adjusted-daily-close-not-attempted@v1"
)
_RUNTIME_MANIFEST_MODULE: Final = (
    "swing_trading_ai_assistant.market_regime."
    "current_supplied_cohort_v4_runtime_identity_manifest"
)
_RUNTIME_MANIFEST: Final = (
    "src/swing_trading_ai_assistant/market_regime/"
    "current_supplied_cohort_v4_runtime_identity_manifest.py"
)
_RUNTIME_SOURCE: Final = (
    "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_v4.py"
)
_DIGEST: Final = re.compile(r"[0-9a-f]{64}")
_MAX_CONTEXT_BYTES: Final = 4_194_304
_MAX_RECEIPT_BYTES: Final = 16_384
_MAX_MARKER_BYTES: Final = 4_096

_CONTEXT_ARCHIVE_TRANSACTION_LOCK: Final = threading.RLock()
_PREFLIGHT_REASON_ORDER: Final = (
    "SCHEDULE_EVIDENCE_MISSING",
    "SCHEDULE_EVIDENCE_STALE",
    "SCHEDULE_EVIDENCE_CONFLICTED",
    "SCHEDULE_CONTINUITY_UNPROVEN",
    "LATEST_COMPLETED_SESSION_UNRESOLVED",
)
_REASON_ORDER: Final = (
    "COHORT_BINDING_MISMATCH",
    "RAW_MAPPING_MISSING",
    "RAW_MAPPING_STALE",
    "RAW_MAPPING_CONFLICTED",
    "RAW_ACQUISITION_UNAVAILABLE",
    "ACQUISITION_DEADLINE_EXCEEDED",
    "RAW_BAR_MISSING",
    "RAW_BAR_STALE",
    "RAW_BAR_CONFLICTED",
    "RAW_BAR_INVALID",
    "RAW_BAR_FUTURE_KNOWN",
    "CORPORATE_ACTION_SCREEN_INSUFFICIENT",
    "ADJUSTED_DAILY_CLOSE_HANDOFF_INVALID",
    "RAW_ADJUSTED_DIRECTION_CONFLICT",
)
_RAW_REASONS: Final = frozenset(_REASON_ORDER[:11])
_PREFLIGHT_REASONS: Final = frozenset(_PREFLIGHT_REASON_ORDER)


def _utc(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() == UTC.utcoffset(value)
    )


def _instant(value: datetime) -> str:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(value)
    ):
        raise ValueError("UTC instant required")
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _plain(value: object) -> object:
    if isinstance(value, datetime):
        return _instant(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if is_dataclass(value):
        return {
            item.name: _plain(getattr(value, item.name))
            for item in fields(value)
            if item.name != "_archive_seal"
        }
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            _plain(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _identity(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ValueError("sha256 required")
    return value


def _decimal_text(value: object) -> str:
    try:
        parsed = value if type(value) is Decimal else Decimal(cast(str, value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("finite decimal required") from None
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError("positive decimal required")
    text = format(parsed.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _ordered_reasons(reasons: tuple[str, ...], *, raw: bool = False) -> tuple[str, ...]:
    if type(reasons) is not tuple or len(set(reasons)) != len(reasons):
        raise ValueError("invalid reasons")
    allowed = _RAW_REASONS if raw else frozenset(_REASON_ORDER)
    if not reasons or any(
        type(reason) is not str or reason not in allowed for reason in reasons
    ):
        raise ValueError("invalid reasons")
    return tuple(reason for reason in _REASON_ORDER if reason in reasons)


def _ordered_preflight_reasons(reasons: tuple[str, ...]) -> tuple[str, ...]:
    if (
        type(reasons) is not tuple
        or not reasons
        or len(set(reasons)) != len(reasons)
        or any(
            type(reason) is not str or reason not in _PREFLIGHT_REASONS
            for reason in reasons
        )
    ):
        raise ValueError("invalid preflight schedule reasons")
    return tuple(reason for reason in _PREFLIGHT_REASON_ORDER if reason in reasons)


def _runtime_root() -> Path:
    return Path(__file__).resolve().parents[1]


def current_same_pass_market_regime_runtime_code_identity_v4() -> str:
    """Verify reviewed source-at-rest identities; never claim byte attestation."""
    modules = {
        _RUNTIME_SOURCE: __name__,
        _RUNTIME_MANIFEST: _RUNTIME_MANIFEST_MODULE,
    }
    try:
        manifest = importlib.import_module(_RUNTIME_MANIFEST_MODULE)
        digests = manifest.CURRENT_SAME_PASS_MARKET_REGIME_RUNTIME_SOURCE_DIGESTS_V4
        if type(digests) is not dict or tuple(digests) != (_RUNTIME_SOURCE,):
            raise ValueError("V4 runtime identity invalid")
        expected = digests[_RUNTIME_SOURCE]
        if type(expected) is not str or _DIGEST.fullmatch(expected) is None:
            raise ValueError("V4 runtime identity invalid")
        sources = []
        for relative_path in sorted((_RUNTIME_SOURCE, _RUNTIME_MANIFEST)):
            source_sha256 = _runtime_source_sha256(
                modules[relative_path], _runtime_root(), relative_path
            )
            if relative_path == _RUNTIME_SOURCE and source_sha256 != expected:
                raise ValueError("V4 runtime identity invalid")
            sources.append(
                {"relative_path": relative_path, "source_sha256": source_sha256}
            )
        return _identity(
            {
                "runtime_manifest_version": "plan27-source-at-rest@v1",
                "modules": sources,
            }
        )
    except (AttributeError, ImportError, OSError, ValueError) as exc:
        raise ValueError("V4 runtime identity invalid") from exc


@dataclass(frozen=True, slots=True)
class CurrentSamePassAdjustedDailyCloseFailureProjectionV1:
    contract_version: Literal["provider-neutral-adjusted-daily-close@v3"]
    plan22_request_identity_sha256: str
    code: str
    reason: str
    failure_projection_identity_sha256: str


@dataclass(frozen=True, slots=True)
class CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1:
    contract_version: Literal["current-same-pass-adjusted-daily-close-not-attempted@v1"]
    plan22_request_identity_sha256: str
    evidence_state: Literal["NOT_ATTEMPTED"]
    reason: Literal["UPSTREAM_INSUFFICIENT_EVIDENCE"]
    not_attempted_projection_identity_sha256: str


@dataclass(frozen=True, slots=True)
class _CurrentSamePassAdjustedSuccessV1:
    adjusted_handoff: AdjustedDailyCloseHandoffV3
    adjusted_failure: None
    adjusted_not_attempted: None


@dataclass(frozen=True, slots=True)
class _CurrentSamePassAdjustedFailureV1:
    adjusted_handoff: None
    adjusted_failure: CurrentSamePassAdjustedDailyCloseFailureProjectionV1
    adjusted_not_attempted: None


@dataclass(frozen=True, slots=True)
class _CurrentSamePassAdjustedNotAttemptedV1:
    adjusted_handoff: None
    adjusted_failure: None
    adjusted_not_attempted: CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1


CurrentSamePassAdjustedCompositionResultV1: TypeAlias = (
    _CurrentSamePassAdjustedSuccessV1
    | _CurrentSamePassAdjustedFailureV1
    | _CurrentSamePassAdjustedNotAttemptedV1
)


@dataclass(frozen=True, slots=True)
class CurrentSamePassPreflightFailureV1:
    """Typed no-trade result when schedule authority cannot yield sessions."""

    contract_version: Literal["current-same-pass-preflight-failure@v1"]
    evidence_state: Literal["INSUFFICIENT_EVIDENCE"]
    request_identity_sha256: str
    canonical_cohort_identity_sha256: str
    reasons: tuple[
        Literal[
            "SCHEDULE_EVIDENCE_MISSING",
            "SCHEDULE_EVIDENCE_STALE",
            "SCHEDULE_EVIDENCE_CONFLICTED",
            "SCHEDULE_CONTINUITY_UNPROVEN",
            "LATEST_COMPLETED_SESSION_UNRESOLVED",
        ],
        ...,
    ]
    consumer_disposition: Literal["INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED"]
    failure_identity_sha256: str

    def __post_init__(self) -> None:
        ordered_reasons = _ordered_preflight_reasons(
            cast(tuple[str, ...], self.reasons)
        )
        core = {
            "contract_version": self.contract_version,
            "evidence_state": self.evidence_state,
            "request_identity_sha256": self.request_identity_sha256,
            "canonical_cohort_identity_sha256": self.canonical_cohort_identity_sha256,
            "reasons": self.reasons,
            "consumer_disposition": self.consumer_disposition,
        }
        if (
            self.contract_version != PREFLIGHT_FAILURE_CONTRACT_VERSION
            or self.evidence_state != "INSUFFICIENT_EVIDENCE"
            or _digest(self.request_identity_sha256) != self.request_identity_sha256
            or _digest(self.canonical_cohort_identity_sha256)
            != self.canonical_cohort_identity_sha256
            or self.reasons != ordered_reasons
            or self.consumer_disposition != "INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED"
            or _digest(self.failure_identity_sha256) != self.failure_identity_sha256
            or self.failure_identity_sha256 != _identity(core)
        ):
            raise ValueError("invalid same-pass preflight failure")

    def canonical_json_bytes(self) -> bytes:
        return _canonical(self)


def _preflight_failure(
    request: CurrentSamePassMarketRegimeRequestV4, reasons: tuple[str, ...]
) -> CurrentSamePassPreflightFailureV1:
    core = {
        "contract_version": PREFLIGHT_FAILURE_CONTRACT_VERSION,
        "evidence_state": "INSUFFICIENT_EVIDENCE",
        "request_identity_sha256": request.request_identity_sha256,
        "canonical_cohort_identity_sha256": request.canonical_cohort_identity_sha256,
        "reasons": _ordered_preflight_reasons(reasons),
        "consumer_disposition": "INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED",
    }
    return CurrentSamePassPreflightFailureV1(
        **core, failure_identity_sha256=_identity(core)
    )


@dataclass(frozen=True, slots=True)
class CurrentSamePassMarketRegimeReportV4:
    contract_version: Literal["current-supplied-cohort-market-regime@v4"]
    schema_identity_sha256: str
    calculation_identity_sha256: str
    runtime_code_identity_sha256: str
    evidence_state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"]
    request_identity_sha256: str
    canonical_cohort_identity_sha256: str
    cohort_size: int
    decision_cutoff: datetime
    decision_session: date
    comparison_session: date
    market_data_report_identity_sha256: str
    corporate_action_screen_identity_sha256: str | None
    adjusted_handoff_identity_sha256: str | None
    regime: Literal["BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"] | None
    advances: int | None
    declines: int | None
    unchanged: int | None
    reasons: tuple[str, ...]
    report_identity_sha256: str


@dataclass(frozen=True, slots=True)
class _CurrentSamePassMemberDirectionRowV4:
    isin: str
    exchange: Literal["NSE"]
    effective_symbol: str
    direction: Literal["ADVANCE", "DECLINE", "UNCHANGED"]
    row_identity_sha256: str


@dataclass(frozen=True, slots=True)
class _CurrentSamePassMemberDirectionCandidateV4:
    request_identity_sha256: str
    raw_grid_identity_sha256: str
    corporate_action_screen_identity_sha256: str
    adjusted_handoff_identity_sha256: str
    market_regime_report_identity_sha256: str
    canonical_cohort_identity_sha256: str
    schedule_identity_sha256: str
    price_basis: BharatStockPriceBasis
    decision_cutoff: datetime
    rows: tuple[_CurrentSamePassMemberDirectionRowV4, ...]
    direction_candidate_identity_sha256: str


@dataclass(frozen=True, slots=True)
class CurrentSamePassContextComponentLedgerRowV1:
    position: int
    component: Literal[
        "RAW_GRID_V1",
        "CORPORATE_ACTION_SCREEN_V1",
        "ADJUSTED_DAILY_CLOSE_V2",
        "MARKET_REGIME_V4",
    ]
    contract_version: str
    evidence_state: str
    schema_identity_sha256: str | None
    runtime_code_identity_sha256: str | None
    primary_identity_sha256: str
    known_at: datetime | None
    reasons: tuple[str, ...]
    ledger_row_identity_sha256: str


@dataclass(frozen=True, slots=True)
class PrivateCurrentSamePassMarketContextObjectV4:
    contract_version: Literal["current-same-pass-market-context-archive@v2"]
    schema_identity_sha256: str
    configuration_identity_sha256: str
    runtime_code_identity_sha256: str
    request: CurrentSamePassMarketRegimeRequestV4
    raw_result: PrivateCurrentSamePassRawDailyResultV1
    market_data_report: CurrentSamePassDecisionMarketDataReportV1
    corporate_action_screen: object
    adjusted_handoff: AdjustedDailyCloseHandoffV3 | None
    adjusted_failure: CurrentSamePassAdjustedDailyCloseFailureProjectionV1 | None
    adjusted_not_attempted: (
        CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1 | None
    )
    market_regime_report: CurrentSamePassMarketRegimeReportV4
    direction_candidate: _CurrentSamePassMemberDirectionCandidateV4 | None
    component_ledger: tuple[CurrentSamePassContextComponentLedgerRowV1, ...]
    temporal_scope: Literal["CURRENT_SAME_PASS_ONLY"]
    historical_availability_claim: Literal[False]
    replay_capability: Literal["NONE"]
    context_identity_sha256: str
    context_object_sha256: str

    def canonical_json_bytes(self) -> bytes:
        return _canonical(self)


@dataclass(frozen=True, slots=True, init=False)
class _CurrentSamePassMarketContextCandidateV4:
    context_object: PrivateCurrentSamePassMarketContextObjectV4
    candidate_identity_sha256: str
    _seal: object = field(repr=False, compare=False, hash=False)

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("same-pass context candidates are composition-minted only")


@dataclass(frozen=True, slots=True)
class CurrentSamePassArchiveFailureV1:
    contract_version: Literal["current-same-pass-market-context-archive-failure@v1"]
    evidence_state: Literal["ARCHIVE_FAILED"]
    reason: Literal["SAME_PASS_CONTEXT_ARCHIVE_FAILED"]
    request_identity_sha256: str
    context_identity_sha256: str | None
    archive_failure_identity_sha256: str


@dataclass(frozen=True, slots=True)
class CurrentSamePassContextReceiptV1:
    contract_version: Literal["current-same-pass-market-context-receipt@v1"]
    context_identity_sha256: str
    context_object_sha256: str
    context_byte_count: int
    context_filename: str
    archive_known_at: datetime
    context_receipt_identity_sha256: str


@dataclass(frozen=True, slots=True)
class CurrentSamePassContextCompletionMarkerV1:
    contract_version: Literal["current-same-pass-market-context-marker@v1"]
    context_identity_sha256: str
    context_object_sha256: str
    context_receipt_identity_sha256: str
    receipt_sha256: str
    archive_known_at: datetime
    completion_marker_identity_sha256: str


@dataclass(frozen=True, slots=True, init=False, repr=False, eq=False)
class _CurrentSamePassMarketContextArchiveSealV1:
    """Opaque transitional seal; closure adoption supplies its private context."""

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("same-pass archive seals are closure-minted only")


def _retained_context_public_projection(
    *,
    evidence_state: str,
    context_identity_sha256: str,
    context_object_sha256: str,
    context_receipt_identity_sha256: str,
    completion_marker_identity_sha256: str,
    archive_known_at: datetime,
    market_data_report: object,
    market_regime_report: object,
    partial_current_session: object,
    retained_context_identity_sha256: str | None = None,
) -> dict[str, object]:
    """Return the sole serialized retained-context projection in Plan-27 order."""
    projection: dict[str, object] = {
        "evidence_state": evidence_state,
        "context_identity_sha256": context_identity_sha256,
        "context_object_sha256": context_object_sha256,
        "context_receipt_identity_sha256": context_receipt_identity_sha256,
        "completion_marker_identity_sha256": completion_marker_identity_sha256,
        "archive_known_at": archive_known_at,
        "market_data_report": market_data_report,
        "market_regime_report": market_regime_report,
        "partial_current_session": partial_current_session,
    }
    if retained_context_identity_sha256 is not None:
        projection["retained_context_identity_sha256"] = (
            retained_context_identity_sha256
        )
    return projection


@dataclass(frozen=True, slots=True, init=False)
class RetainedCurrentSamePassMarketContextV4:
    evidence_state: Literal["RETAINED"]
    context_identity_sha256: str
    context_object_sha256: str
    context_receipt_identity_sha256: str
    completion_marker_identity_sha256: str
    archive_known_at: datetime
    market_data_report: CurrentSamePassDecisionMarketDataReportV1
    market_regime_report: CurrentSamePassMarketRegimeReportV4
    partial_current_session: PartialCurrentSessionSnapshotV1
    retained_context_identity_sha256: str
    _archive_seal: _CurrentSamePassMarketContextArchiveSealV1 = field(
        repr=False,
        compare=False,
        hash=False,
    )

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("retained contexts are archive-minted only")

    @property
    def retention(self) -> dict[str, object]:
        return {
            "context_identity_sha256": self.context_identity_sha256,
            "archive_known_at": _instant(self.archive_known_at),
        }

    def canonical_json_bytes(self) -> bytes:
        """Serialize only the exact public retained-context projection."""
        return _canonical(
            _retained_context_public_projection(
                evidence_state=self.evidence_state,
                context_identity_sha256=self.context_identity_sha256,
                context_object_sha256=self.context_object_sha256,
                context_receipt_identity_sha256=self.context_receipt_identity_sha256,
                completion_marker_identity_sha256=self.completion_marker_identity_sha256,
                archive_known_at=self.archive_known_at,
                market_data_report=self.market_data_report,
                market_regime_report=self.market_regime_report,
                partial_current_session=self.partial_current_session,
                retained_context_identity_sha256=self.retained_context_identity_sha256,
            )
        )


class CurrentSamePassMarketContextArchivePortV1(Protocol):
    def archive_exact(
        self,
        request: CurrentSamePassMarketRegimeRequestV4,
        candidate: _CurrentSamePassMarketContextCandidateV4,
        lease: StorageRootLease,
        *,
        trusted_clock: _TrustedClockV1 | None = None,
    ) -> RetainedCurrentSamePassMarketContextV4 | CurrentSamePassArchiveFailureV1: ...


_V4_TYPE_FIELDS_V1: Final = (
    (
        "CurrentSamePassPreflightFailureV1",
        (
            "contract_version",
            "evidence_state",
            "request_identity_sha256",
            "canonical_cohort_identity_sha256",
            "reasons",
            "consumer_disposition",
            "failure_identity_sha256",
        ),
    ),
    (
        "CurrentSamePassMarketRegimeReportV4",
        (
            "contract_version",
            "schema_identity_sha256",
            "calculation_identity_sha256",
            "runtime_code_identity_sha256",
            "evidence_state",
            "request_identity_sha256",
            "canonical_cohort_identity_sha256",
            "cohort_size",
            "decision_cutoff",
            "decision_session",
            "comparison_session",
            "market_data_report_identity_sha256",
            "corporate_action_screen_identity_sha256",
            "adjusted_handoff_identity_sha256",
            "regime",
            "advances",
            "declines",
            "unchanged",
            "reasons",
            "report_identity_sha256",
        ),
    ),
    (
        "CurrentSamePassAdjustedDailyCloseFailureProjectionV1",
        (
            "contract_version",
            "plan22_request_identity_sha256",
            "code",
            "reason",
            "failure_projection_identity_sha256",
        ),
    ),
    (
        "CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1",
        (
            "contract_version",
            "plan22_request_identity_sha256",
            "evidence_state",
            "reason",
            "not_attempted_projection_identity_sha256",
        ),
    ),
    (
        "_CurrentSamePassAdjustedSuccessV1",
        ("adjusted_handoff", "adjusted_failure", "adjusted_not_attempted"),
    ),
    (
        "_CurrentSamePassAdjustedFailureV1",
        ("adjusted_handoff", "adjusted_failure", "adjusted_not_attempted"),
    ),
    (
        "_CurrentSamePassAdjustedNotAttemptedV1",
        ("adjusted_handoff", "adjusted_failure", "adjusted_not_attempted"),
    ),
    (
        "_CurrentSamePassMemberDirectionRowV4",
        ("isin", "exchange", "effective_symbol", "direction", "row_identity_sha256"),
    ),
    (
        "_CurrentSamePassMemberDirectionCandidateV4",
        (
            "request_identity_sha256",
            "raw_grid_identity_sha256",
            "corporate_action_screen_identity_sha256",
            "adjusted_handoff_identity_sha256",
            "market_regime_report_identity_sha256",
            "canonical_cohort_identity_sha256",
            "schedule_identity_sha256",
            "price_basis",
            "decision_cutoff",
            "rows",
            "direction_candidate_identity_sha256",
        ),
    ),
    (
        "CurrentSamePassContextComponentLedgerRowV1",
        (
            "position",
            "component",
            "contract_version",
            "evidence_state",
            "schema_identity_sha256",
            "runtime_code_identity_sha256",
            "primary_identity_sha256",
            "known_at",
            "reasons",
            "ledger_row_identity_sha256",
        ),
    ),
    (
        "PrivateCurrentSamePassMarketContextObjectV4",
        (
            "contract_version",
            "schema_identity_sha256",
            "configuration_identity_sha256",
            "runtime_code_identity_sha256",
            "request",
            "raw_result",
            "market_data_report",
            "corporate_action_screen",
            "adjusted_handoff",
            "adjusted_failure",
            "adjusted_not_attempted",
            "market_regime_report",
            "direction_candidate",
            "component_ledger",
            "temporal_scope",
            "historical_availability_claim",
            "replay_capability",
            "context_identity_sha256",
            "context_object_sha256",
        ),
    ),
    (
        "_CurrentSamePassMarketContextCandidateV4",
        ("context_object", "candidate_identity_sha256"),
    ),
    (
        "CurrentSamePassArchiveFailureV1",
        (
            "contract_version",
            "evidence_state",
            "reason",
            "request_identity_sha256",
            "context_identity_sha256",
            "archive_failure_identity_sha256",
        ),
    ),
    (
        "CurrentSamePassContextReceiptV1",
        (
            "contract_version",
            "context_identity_sha256",
            "context_object_sha256",
            "context_byte_count",
            "context_filename",
            "archive_known_at",
            "context_receipt_identity_sha256",
        ),
    ),
    (
        "CurrentSamePassContextCompletionMarkerV1",
        (
            "contract_version",
            "context_identity_sha256",
            "context_object_sha256",
            "context_receipt_identity_sha256",
            "receipt_sha256",
            "archive_known_at",
            "completion_marker_identity_sha256",
        ),
    ),
    (
        "RetainedCurrentSamePassMarketContextV4",
        (
            "evidence_state",
            "context_identity_sha256",
            "context_object_sha256",
            "context_receipt_identity_sha256",
            "completion_marker_identity_sha256",
            "archive_known_at",
            "market_data_report",
            "market_regime_report",
            "partial_current_session",
            "retained_context_identity_sha256",
        ),
    ),
)
_V4_SCHEMA_FIELD_ROWS_V1: Final = (
    (
        "CurrentSamePassPreflightFailureV1",
        (
            (
                "contract_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["current-same-pass-preflight-failure@v1"]',
            ),
            (
                "evidence_state",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["INSUFFICIENT_EVIDENCE"]',
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
                "reasons",
                "ORDERED_REASON_TUPLE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "SCHEDULE_PREFLIGHT_REASON_ORDER[1..5]",
            ),
            (
                "consumer_disposition",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED"]',
            ),
            (
                "failure_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "CurrentSamePassMarketRegimeReportV4",
        (
            (
                "contract_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["current-supplied-cohort-market-regime@v4"]',
            ),
            (
                "schema_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "calculation_identity_sha256",
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
            ("cohort_size", "INTEGER", "MEMBERS", "REQUIRED", "[1..50]"),
            (
                "decision_cutoff",
                "UTC_INSTANT",
                "UTC",
                "REQUIRED",
                "AWARE_UTC_MICROSECOND",
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
                "market_data_report_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "corporate_action_screen_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "NULLABLE",
                "LOWERCASE_64_HEX",
            ),
            (
                "adjusted_handoff_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "NULLABLE",
                "LOWERCASE_64_HEX",
            ),
            (
                "regime",
                "LITERAL",
                "NOT_APPLICABLE",
                "NULLABLE",
                'Literal["BROAD_ADVANCE","BROAD_DECLINE","MIXED_PARTICIPATION"]',
            ),
            ("advances", "INTEGER", "MEMBERS", "NULLABLE", "[0..50]"),
            ("declines", "INTEGER", "MEMBERS", "NULLABLE", "[0..50]"),
            ("unchanged", "INTEGER", "MEMBERS", "NULLABLE", "[0..50]"),
            (
                "reasons",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "tuple[MarketRegimeReason,0..14]",
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
    (
        "CurrentSamePassAdjustedDailyCloseFailureProjectionV1",
        (
            (
                "contract_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["provider-neutral-adjusted-daily-close@v3"]',
            ),
            (
                "plan22_request_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "code",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                "ONE_OF[INSUFFICIENT_DATA|INVALID_REQUEST|PROVIDER_FAILURE|UNSUPPORTED_CAPABILITY]",
            ),
            (
                "reason",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                "ONE_OF[CANONICAL_IDENTITY_OVERLAP|DECISION_CUTOFF_INVALID|DECISION_SESSION_AFTER_CUTOFF|EFFECTIVE_SYMBOL_OVERLAP|EXCHANGE_UNSUPPORTED|FRAME_COVERAGE_INCOMPLETE|FRAME_INDEX_INVALID|FRAME_SCHEMA_INVALID|INSTRUMENT_COUNT_INVALID|INSTRUMENT_IDENTITY_INVALID|INSTRUMENT_TYPE_UNSUPPORTED|MAPPING_EFFECTIVE_FOR_FACT_WINDOW_REQUIRED|MAPPING_IDENTITY_INVALID|MAPPING_VERSION_UNSUPPORTED|PRICE_BASIS_INVALID|PROVIDER_CALL_FAILED|PROVIDER_EMPTY|PROVIDER_MAPPING_OVERLAP|PROVIDER_MAPPING_UNSUPPORTED|PROVIDER_SELECTION_INVALID|REQUEST_IDENTITY_INVALID|REQUEST_SHAPE_INVALID|SCHEDULE_IDENTITY_INVALID|SCHEDULE_INVALID|SEGMENT_UNSUPPORTED|SYMBOL_EFFECTIVE_FOR_FACT_WINDOW_REQUIRED]",
            ),
            (
                "failure_projection_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1",
        (
            (
                "contract_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["current-same-pass-adjusted-daily-close-not-attempted@v1"]',
            ),
            (
                "plan22_request_identity_sha256",
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
                'Literal["NOT_ATTEMPTED"]',
            ),
            (
                "reason",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["UPSTREAM_INSUFFICIENT_EVIDENCE"]',
            ),
            (
                "not_attempted_projection_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "_CurrentSamePassAdjustedSuccessV1",
        (
            (
                "adjusted_handoff",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "AdjustedDailyCloseHandoffV3",
            ),
            (
                "adjusted_failure",
                "EXACT_NONE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LITERAL_NONE",
            ),
            (
                "adjusted_not_attempted",
                "EXACT_NONE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LITERAL_NONE",
            ),
        ),
    ),
    (
        "_CurrentSamePassAdjustedFailureV1",
        (
            (
                "adjusted_handoff",
                "EXACT_NONE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LITERAL_NONE",
            ),
            (
                "adjusted_failure",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "CurrentSamePassAdjustedDailyCloseFailureProjectionV1",
            ),
            (
                "adjusted_not_attempted",
                "EXACT_NONE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LITERAL_NONE",
            ),
        ),
    ),
    (
        "_CurrentSamePassAdjustedNotAttemptedV1",
        (
            (
                "adjusted_handoff",
                "EXACT_NONE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LITERAL_NONE",
            ),
            (
                "adjusted_failure",
                "EXACT_NONE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LITERAL_NONE",
            ),
            (
                "adjusted_not_attempted",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1",
            ),
        ),
    ),
    (
        "_CurrentSamePassMemberDirectionRowV4",
        (
            ("isin", "ISIN", "NOT_APPLICABLE", "REQUIRED", "NSE_ISIN_LUHN_12"),
            ("exchange", "LITERAL", "NOT_APPLICABLE", "REQUIRED", 'Literal["NSE"]'),
            (
                "effective_symbol",
                "NSE_SYMBOL",
                "NOT_APPLICABLE",
                "REQUIRED",
                "UTF8_BYTES[1..64]",
            ),
            (
                "direction",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["ADVANCE","DECLINE","UNCHANGED"]',
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
        "_CurrentSamePassMemberDirectionCandidateV4",
        (
            (
                "request_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "raw_grid_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "corporate_action_screen_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "adjusted_handoff_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "market_regime_report_identity_sha256",
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
                "price_basis",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["BHARATSTOCK_SOURCE_REPORTED_OHLC"]',
            ),
            (
                "decision_cutoff",
                "UTC_INSTANT",
                "UTC",
                "REQUIRED",
                "AWARE_UTC_MICROSECOND",
            ),
            (
                "rows",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "tuple[_CurrentSamePassMemberDirectionRowV4,N]",
            ),
            (
                "direction_candidate_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "CurrentSamePassContextComponentLedgerRowV1",
        (
            ("position", "INTEGER", "ORDINAL", "REQUIRED", "[0..3]"),
            (
                "component",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["RAW_GRID_V1","CORPORATE_ACTION_SCREEN_V1","ADJUSTED_DAILY_CLOSE_V2","MARKET_REGIME_V4"]',
            ),
            (
                "contract_version",
                "SAFE_REVISION",
                "NOT_APPLICABLE",
                "REQUIRED",
                "UTF8_BYTES[1..128]",
            ),
            (
                "evidence_state",
                "SAFE_REVISION",
                "NOT_APPLICABLE",
                "REQUIRED",
                "UTF8_BYTES[1..128]",
            ),
            (
                "schema_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "NULLABLE",
                "LOWERCASE_64_HEX",
            ),
            (
                "runtime_code_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "NULLABLE",
                "LOWERCASE_64_HEX",
            ),
            (
                "primary_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            ("known_at", "UTC_INSTANT", "UTC", "NULLABLE", "AWARE_UTC_MICROSECOND"),
            (
                "reasons",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "tuple[SafeRevision,0..32]",
            ),
            (
                "ledger_row_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "PrivateCurrentSamePassMarketContextObjectV4",
        (
            (
                "contract_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["current-same-pass-market-context-archive@v2"]',
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
                "request",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "CurrentSamePassMarketRegimeRequestV4",
            ),
            (
                "raw_result",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "PrivateCurrentSamePassRawDailyResultV1",
            ),
            (
                "market_data_report",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "CurrentSamePassDecisionMarketDataReportV1",
            ),
            (
                "corporate_action_screen",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "PublishedCurrentCorporateActionScreenV1",
            ),
            (
                "adjusted_handoff",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "NULLABLE",
                "AdjustedDailyCloseHandoffV3",
            ),
            (
                "adjusted_failure",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "NULLABLE",
                "CurrentSamePassAdjustedDailyCloseFailureProjectionV1",
            ),
            (
                "adjusted_not_attempted",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "NULLABLE",
                "CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1",
            ),
            (
                "market_regime_report",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "CurrentSamePassMarketRegimeReportV4",
            ),
            (
                "direction_candidate",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "NULLABLE",
                "_CurrentSamePassMemberDirectionCandidateV4",
            ),
            (
                "component_ledger",
                "ORDERED_TUPLE",
                "NOT_APPLICABLE",
                "REQUIRED",
                "tuple[CurrentSamePassContextComponentLedgerRowV1,4]",
            ),
            (
                "temporal_scope",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["CURRENT_SAME_PASS_ONLY"]',
            ),
            (
                "historical_availability_claim",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                "Literal[false]",
            ),
            (
                "replay_capability",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["NONE"]',
            ),
            (
                "context_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "context_object_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "_CurrentSamePassMarketContextCandidateV4",
        (
            (
                "context_object",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "PrivateCurrentSamePassMarketContextObjectV4",
            ),
            (
                "candidate_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "CurrentSamePassArchiveFailureV1",
        (
            (
                "contract_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["current-same-pass-market-context-archive-failure@v1"]',
            ),
            (
                "evidence_state",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["ARCHIVE_FAILED"]',
            ),
            (
                "reason",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["SAME_PASS_CONTEXT_ARCHIVE_FAILED"]',
            ),
            (
                "request_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "context_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "NULLABLE",
                "LOWERCASE_64_HEX",
            ),
            (
                "archive_failure_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "CurrentSamePassContextReceiptV1",
        (
            (
                "contract_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["current-same-pass-market-context-receipt@v1"]',
            ),
            (
                "context_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "context_object_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            ("context_byte_count", "INTEGER", "BYTES", "REQUIRED", "[1..4_194_304]"),
            (
                "context_filename",
                "SAFE_TEXT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "UTF8_BYTES[1..128]",
            ),
            (
                "archive_known_at",
                "UTC_INSTANT",
                "UTC",
                "REQUIRED",
                "AWARE_UTC_MICROSECOND",
            ),
            (
                "context_receipt_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "CurrentSamePassContextCompletionMarkerV1",
        (
            (
                "contract_version",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["current-same-pass-market-context-marker@v1"]',
            ),
            (
                "context_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "context_object_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "context_receipt_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "receipt_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "archive_known_at",
                "UTC_INSTANT",
                "UTC",
                "REQUIRED",
                "AWARE_UTC_MICROSECOND",
            ),
            (
                "completion_marker_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
    (
        "RetainedCurrentSamePassMarketContextV4",
        (
            (
                "evidence_state",
                "LITERAL",
                "NOT_APPLICABLE",
                "REQUIRED",
                'Literal["RETAINED"]',
            ),
            (
                "context_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "context_object_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "context_receipt_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "completion_marker_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
            (
                "archive_known_at",
                "UTC_INSTANT",
                "UTC",
                "REQUIRED",
                "AWARE_UTC_MICROSECOND",
            ),
            (
                "market_data_report",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "CurrentSamePassDecisionMarketDataReportV1",
            ),
            (
                "market_regime_report",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "CurrentSamePassMarketRegimeReportV4",
            ),
            (
                "partial_current_session",
                "CLOSED_OBJECT",
                "NOT_APPLICABLE",
                "REQUIRED",
                "PartialCurrentSessionSnapshotV1",
            ),
            (
                "retained_context_identity_sha256",
                "SHA256",
                "NOT_APPLICABLE",
                "REQUIRED",
                "LOWERCASE_64_HEX",
            ),
        ),
    ),
)


_V4_STATE_PROJECTIONS_V1: Final = (
    (
        "CurrentSamePassMarketRegimeReportV4",
        (
            ("OBSERVED", "regime/counts/adjusted_handoff=REQUIRED,reasons=EMPTY"),
            ("INSUFFICIENT_EVIDENCE", "regime/counts=NONE,reasons=NONEMPTY"),
        ),
    ),
    (
        "CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1",
        (
            (
                "NOT_ATTEMPTED",
                "reason=UPSTREAM_INSUFFICIENT_EVIDENCE,provider_effect=ABSENT",
            ),
        ),
    ),
    (
        "CurrentSamePassContextComponentLedgerRowV1",
        (
            (
                "RAW_GRID_V1/OBSERVED",
                "position=0,contract=current-same-pass-raw-daily-grid@v4,schema_runtime=RAW_GRID,primary=RAW_GRID,known_at=MAX_RAW_PARTIAL,reasons=EMPTY",
            ),
            (
                "RAW_GRID_V1/INSUFFICIENT_EVIDENCE",
                "position=0,contract=current-same-pass-raw-daily-grid@v4,schema_runtime=RAW_SUCCESSOR,primary=RAW_RESULT,known_at=PARTIAL_OR_NONE,reasons=RAW_RESULT",
            ),
            (
                "CORPORATE_ACTION_SCREEN_V1/SCREENED",
                "position=1,contract=current-supplied-cohort-corporate-action-screen@v1,schema_runtime=SCREEN,primary=SCREEN,known_at=MAX_PROVIDER_RETRIEVED,reasons=EMPTY",
            ),
            (
                "CORPORATE_ACTION_SCREEN_V1/INSUFFICIENT_EVIDENCE",
                "position=1,contract=current-supplied-cohort-corporate-action-screen@v1,schema_runtime=SCREEN,primary=SCREEN,known_at=MAX_PROVIDER_RETRIEVED_OR_NONE,reasons=CORPORATE_ACTION_SCREEN_INSUFFICIENT",
            ),
            (
                "ADJUSTED_DAILY_CLOSE_V2/SUCCESS",
                "position=2,contract=provider-neutral-adjusted-daily-close@v3,schema_runtime=NONE,primary=HANDOFF,known_at=HANDOFF_RETRIEVED,reasons=EMPTY",
            ),
            (
                "ADJUSTED_DAILY_CLOSE_V2/FAILURE",
                "position=2,contract=provider-neutral-adjusted-daily-close@v3,schema_runtime=NONE,primary=FAILURE_PROJECTION,known_at=NONE,reasons=ADJUSTED_FAILURE_REASON",
            ),
            (
                "ADJUSTED_DAILY_CLOSE_V2/NOT_ATTEMPTED",
                "position=2,contract=provider-neutral-adjusted-daily-close@v3,schema_runtime=NONE,primary=NOT_ATTEMPTED_PROJECTION,known_at=NONE,reasons=UPSTREAM_INSUFFICIENT_EVIDENCE",
            ),
            (
                "MARKET_REGIME_V4/OBSERVED",
                "position=3,contract=current-supplied-cohort-market-regime@v4,schema_runtime=V4_REPORT,primary=V4_REPORT,known_at=MAX_POSITIONS_0_2,reasons=EMPTY",
            ),
            (
                "MARKET_REGIME_V4/INSUFFICIENT_EVIDENCE",
                "position=3,contract=current-supplied-cohort-market-regime@v4,schema_runtime=V4_REPORT,primary=V4_REPORT,known_at=MAX_POSITIONS_0_2_OR_NONE,reasons=V4_REPORT",
            ),
        ),
    ),
    (
        "CurrentSamePassArchiveFailureV1",
        (("ARCHIVE_FAILED", "reason=SAME_PASS_CONTEXT_ARCHIVE_FAILED"),),
    ),
    (
        "RetainedCurrentSamePassMarketContextV4",
        (("RETAINED", "archive_projection=SERIALIZED_FIELDS_ONLY"),),
    ),
)


def _v4_schema_metadata_v1() -> dict[str, object]:
    """Return the frozen, exhaustive Plan-27 V4 field metadata."""
    field_rows = dict(_V4_SCHEMA_FIELD_ROWS_V1)
    rows = []
    for name, ordered_fields in _V4_TYPE_FIELDS_V1:
        exact_fields = field_rows.get(name)
        if (
            exact_fields is None
            or tuple(item[0] for item in exact_fields) != ordered_fields
        ):
            raise ValueError("incomplete exact V4 schema metadata")
        rows.append(
            {
                "name": name,
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
        "contract_version": SCHEMA_CONTRACT_VERSION,
        "type_rows": tuple(rows),
        "state_projections": _V4_STATE_PROJECTIONS_V1,
        "unknown_key_policy": "REJECT",
    }


def current_same_pass_market_regime_schema_metadata_v4() -> dict[str, object]:
    return _v4_schema_metadata_v1()


def current_same_pass_market_regime_schema_metadata_digest_v4(metadata: object) -> str:
    if type(metadata) is not dict or set(metadata) != {
        "contract_version",
        "type_rows",
        "state_projections",
        "unknown_key_policy",
    }:
        raise ValueError("unknown V4 schema metadata key")
    return _identity(metadata)


def current_same_pass_market_regime_schema_identity_from_metadata_v4(
    metadata: object,
) -> str:
    if _canonical(metadata) != _canonical(_v4_schema_metadata_v1()):
        raise ValueError("V4 schema metadata differs from frozen contract")
    return current_same_pass_market_regime_schema_metadata_digest_v4(metadata)


def _schema_identity() -> str:
    return current_same_pass_market_regime_schema_identity_from_metadata_v4(
        _v4_schema_metadata_v1()
    )


def _configuration_identity() -> str:
    return _identity(
        {
            "contract_version": ARCHIVE_CONTRACT_VERSION,
            "structural_bounds": {
                "cohort_members": [1, 50],
                "resolved_sessions": 21,
                "context_bytes": [1, _MAX_CONTEXT_BYTES],
                "receipt_bytes": [1, _MAX_RECEIPT_BYTES],
                "marker_bytes": [1, _MAX_MARKER_BYTES],
            },
            "canonicalization": "CJ UTF-8 sorted keys compact no-NaN trailing-LF",
            "reason_order": {
                "preflight": list(_PREFLIGHT_REASON_ORDER),
                "post_session": list(_REASON_ORDER),
            },
            "precedence": (
                "schedule-before-raw-before-screen-before-adjusted; "
                "upstream-insufficiency-skips-adjusted; whole-result-suppression"
            ),
            "raw_source_policy": "current-same-pass-raw-daily-grid@v4-only",
            "partial_policy": "separate-optional-context",
            "retention_names_and_limits": {
                "context": "context-<identity>.json",
                "receipt": "retained-<identity>.json",
                "marker": "completion-<identity>.json",
                "pending_guard": "pending-<identity>.json",
                "admissible_guard": "admissible-<identity>.json",
                "context_bytes": _MAX_CONTEXT_BYTES,
                "receipt_bytes": _MAX_RECEIPT_BYTES,
                "marker_bytes": _MAX_MARKER_BYTES,
                "guard_bytes": _MAX_MARKER_BYTES,
            },
        }
    )


def _calculation_identity() -> str:
    return _identity(
        {
            "contract_version": CALCULATION_CONTRACT_VERSION,
            "comparison": "Decimal(close(S20)) cmp Decimal(close(S0))",
            "raw_adjusted_direction_equality": True,
            "adjusted_admission": (
                "current-prospective-success-only; "
                "not-attempted-preserves-upstream-insufficiency"
            ),
            "advance_formula": "advances*5>=cohort_size*3",
            "decline_formula": "declines*5>=cohort_size*3",
            "reason_order": _REASON_ORDER,
            "suppression": "whole-result",
        }
    )


def _failure(
    request: CurrentSamePassMarketRegimeRequestV4, context_identity: str | None = None
) -> CurrentSamePassArchiveFailureV1:
    core = {
        "contract_version": "current-same-pass-market-context-archive-failure@v1",
        "evidence_state": "ARCHIVE_FAILED",
        "reason": "SAME_PASS_CONTEXT_ARCHIVE_FAILED",
        "request_identity_sha256": request.request_identity_sha256,
        "context_identity_sha256": context_identity,
    }
    return CurrentSamePassArchiveFailureV1(
        **core, archive_failure_identity_sha256=_identity(core)
    )


def _archive_failure_is_exact(
    request: CurrentSamePassMarketRegimeRequestV4,
    context_identity: str,
    value: object,
) -> bool:
    if type(value) is not CurrentSamePassArchiveFailureV1:
        return False
    core = {
        "contract_version": "current-same-pass-market-context-archive-failure@v1",
        "evidence_state": "ARCHIVE_FAILED",
        "reason": "SAME_PASS_CONTEXT_ARCHIVE_FAILED",
        "request_identity_sha256": request.request_identity_sha256,
        "context_identity_sha256": context_identity,
    }
    return (
        value.contract_version == core["contract_version"]
        and value.evidence_state == core["evidence_state"]
        and value.reason == core["reason"]
        and value.request_identity_sha256 == core["request_identity_sha256"]
        and value.context_identity_sha256 == core["context_identity_sha256"]
        and value.archive_failure_identity_sha256 == _identity(core)
    )


def _raw_direction(first: str, last: str) -> str:
    initial, final = Decimal(first), Decimal(last)
    return (
        "ADVANCE" if final > initial else "DECLINE" if final < initial else "UNCHANGED"
    )


def _decision_report(
    raw: PrivateCurrentSamePassRawDailyResultV1,
    request: CurrentSamePassMarketRegimeRequestV4,
) -> CurrentSamePassDecisionMarketDataReportV1:
    if raw.evidence_state != "OBSERVED" or raw.raw_grid is None:
        core = {
            "contract_version": "current-same-pass-decision-market-data@v4",
            "schema_identity_sha256": current_same_pass_raw_daily_schema_identity_v4(),
            "evidence_state": "INSUFFICIENT_EVIDENCE",
            "request_identity_sha256": request.request_identity_sha256,
            "canonical_cohort_identity_sha256": request.canonical_cohort_identity_sha256,
            "decision_session": raw.decision_session,
            "comparison_session": raw.comparison_session,
            "raw_grid_identity_sha256": None,
            "rows": None,
            "partial_current_session": raw.partial_current_session,
            "reasons": _ordered_reasons(raw.reasons, raw=True),
        }
        return CurrentSamePassDecisionMarketDataReportV1(
            **core,
            report_identity_sha256=_identity_from_values(
                CurrentSamePassDecisionMarketDataReportV1,
                core,
                "report_identity_sha256",
            ),
        )
    by_key = {(bar.isin, bar.session): bar for bar in raw.raw_grid.bars}
    rows: list[CurrentSamePassDecisionMarketDataRowV1] = []
    for member in request.members:
        bar = by_key.get((member.isin, raw.decision_session))
        if bar is None:
            return _decision_report(_raw_insufficient(raw, "RAW_BAR_MISSING"), request)
        core = {
            "isin": bar.isin,
            "session": bar.session,
            "close": bar.close,
            "volume": bar.volume,
            "provider": "UPSTOX",
            "price_basis": "RAW",
            "published_at": None,
            "known_at": bar.known_at,
            "raw_bar_identity_sha256": bar.raw_bar_identity_sha256,
        }
        rows.append(
            CurrentSamePassDecisionMarketDataRowV1(
                **core,
                row_identity_sha256=_identity_from_values(
                    CurrentSamePassDecisionMarketDataRowV1, core, "row_identity_sha256"
                ),
            )
        )
    core = {
        "contract_version": "current-same-pass-decision-market-data@v4",
        "schema_identity_sha256": current_same_pass_raw_daily_schema_identity_v4(),
        "evidence_state": "OBSERVED",
        "request_identity_sha256": request.request_identity_sha256,
        "canonical_cohort_identity_sha256": request.canonical_cohort_identity_sha256,
        "decision_session": raw.decision_session,
        "comparison_session": raw.comparison_session,
        "raw_grid_identity_sha256": raw.raw_grid.raw_grid_identity_sha256,
        "rows": tuple(rows),
        "partial_current_session": raw.partial_current_session,
        "reasons": (),
    }
    return CurrentSamePassDecisionMarketDataReportV1(
        **core,
        report_identity_sha256=_identity_from_values(
            CurrentSamePassDecisionMarketDataReportV1, core, "report_identity_sha256"
        ),
    )


def _raw_insufficient(
    raw: PrivateCurrentSamePassRawDailyResultV1, reason: str
) -> PrivateCurrentSamePassRawDailyResultV1:
    reasons = _ordered_reasons(tuple(set(raw.reasons) | {reason}), raw=True)
    core = {
        "evidence_state": "INSUFFICIENT_EVIDENCE",
        "request_identity_sha256": raw.request_identity_sha256,
        "canonical_cohort_identity_sha256": raw.canonical_cohort_identity_sha256,
        "decision_session": raw.decision_session,
        "comparison_session": raw.comparison_session,
        "raw_grid": None,
        "partial_current_session": raw.partial_current_session,
        "reasons": reasons,
    }
    return PrivateCurrentSamePassRawDailyResultV1(
        **core,
        raw_result_identity_sha256=_identity_from_values(
            PrivateCurrentSamePassRawDailyResultV1, core, "raw_result_identity_sha256"
        ),
    )


def _raw_result_is_authoritative(
    raw: PrivateCurrentSamePassRawDailyResultV1,
    request: CurrentSamePassMarketRegimeRequestV4,
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
) -> bool:
    """Bind the returned raw result to this builder's authoritative S0..S20."""
    if (
        not current_same_pass_raw_daily_result_is_exact_valid_v4(raw, request)
        or raw.resolved_sessions != sessions
        or raw.comparison_session != sessions[0].session
        or raw.decision_session != sessions[-1].session
    ):
        return False
    return (
        raw.evidence_state != "OBSERVED"
        or raw.raw_grid is not None
        and raw.raw_grid.schedule_identity_sha256 == request.schedule_identity_sha256
    )


def _adjusted_handoff_is_exact(
    handoff: object,
    request: CurrentSamePassMarketRegimeRequestV4,
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
) -> bool:
    if (
        type(handoff) is not AdjustedDailyCloseHandoffV3
        or not adjusted_daily_close_handoff_is_valid_v3(handoff)
    ):
        return False
    bridge = _plan22_bridge(request, sessions)
    schedule = bridge["plan21_schedule"]
    if not isinstance(schedule, dict):
        return False
    if (
        handoff.contract_version != "provider-neutral-adjusted-daily-close@v3"
        or handoff.provider_id != "BHARATSTOCK"
        or handoff.price_basis != PRICE_BASIS
        or handoff.provider_source != "bharatstock-api@v1"
        or handoff.cohort_identity_sha256 != request.canonical_cohort_identity_sha256
        or handoff.request_identity_sha256 != request.plan22_request_identity_sha256
        or handoff.request_identity_sha256 == request.request_identity_sha256
        or handoff.decision_cutoff != request.decision_cutoff
        or handoff.schedule_evidence_sha256 != request.schedule_evidence_sha256
        or handoff.schedule_source != request.schedule_source
        or handoff.schedule_source_release != request.schedule_source_release
        or handoff.decision_session_official_close_at != sessions[-1].close_at
        or handoff.schedule_sessions != tuple(item.session for item in sessions)
        or handoff.schedule_identity_sha256 != schedule["schedule_identity_sha256"]
        or handoff.comparison_session != sessions[0].session
        or handoff.decision_session != sessions[-1].session
        or handoff.retrieved_at > request.decision_cutoff
        or adjusted_daily_close_handoff_identity_v3(handoff)
        != handoff.handoff_identity_sha256
        or len(handoff.members) != len(request.members)
    ):
        return False
    return all(
        (
            fact.isin,
            fact.exchange,
            fact.instrument_type,
            fact.segment,
            fact.effective_symbol,
            fact.valid_from,
            fact.valid_through,
            fact.provider_symbol,
            fact.mapping_version,
            fact.mapping_valid_from,
            fact.mapping_valid_through,
            fact.mapping_identity,
            fact.price_basis,
            fact.s0.session,
            fact.s20.session,
        )
        == (
            member.isin,
            member.exchange,
            member.instrument_type,
            member.segment,
            member.effective_symbol,
            member.valid_from,
            member.valid_through,
            member.provider_symbol,
            member.mapping_version,
            member.mapping_valid_from,
            member.mapping_valid_through,
            member.mapping_identity,
            PRICE_BASIS,
            sessions[0].session,
            sessions[-1].session,
        )
        for fact, member in zip(handoff.members, request.members, strict=True)
    )


_ADJUSTED_FAILURE_PAIRS: Final = {
    "INVALID_REQUEST": frozenset(
        {
            "REQUEST_SHAPE_INVALID",
            "PROVIDER_SELECTION_INVALID",
            "PRICE_BASIS_INVALID",
            "DECISION_CUTOFF_INVALID",
            "SCHEDULE_INVALID",
            "SCHEDULE_IDENTITY_INVALID",
            "INSTRUMENT_COUNT_INVALID",
            "INSTRUMENT_IDENTITY_INVALID",
            "SYMBOL_EFFECTIVE_FOR_FACT_WINDOW_REQUIRED",
            "MAPPING_IDENTITY_INVALID",
            "MAPPING_EFFECTIVE_FOR_FACT_WINDOW_REQUIRED",
            "CANONICAL_IDENTITY_OVERLAP",
            "REQUEST_IDENTITY_INVALID",
        }
    ),
    "INSUFFICIENT_DATA": frozenset(
        {
            "RESPONSE_INVALID",
            "PAGINATION_INVALID",
            "NOT_FOUND",
            "REQUEST_REJECTED",
            "IDENTITY_MISMATCH",
            "PRICE_EVIDENCE_INVALID",
            "EMPTY_HISTORY",
            "PROVIDER_HISTORY_INVALID",
        }
    ),
    "PROVIDER_FAILURE": frozenset(
        {
            "REQUEST_BUDGET_EXHAUSTED",
            "AUTHENTICATION",
            "AUTHORIZATION",
            "TRANSPORT_FAILED",
            "RESPONSE_LIMIT_EXCEEDED",
            "REDIRECT_REJECTED",
            "RATE_LIMITED",
            "PROVIDER_UNAVAILABLE",
        }
    ),
}


def _adjusted_failure_is_exact(
    failure: object, request: CurrentSamePassMarketRegimeRequestV4
) -> bool:
    if type(failure) is not CurrentSamePassAdjustedDailyCloseFailureProjectionV1:
        return False
    core = {
        "contract_version": "provider-neutral-adjusted-daily-close@v3",
        "plan22_request_identity_sha256": request.plan22_request_identity_sha256,
        "code": failure.code,
        "reason": failure.reason,
    }
    return bool(
        failure.contract_version == core["contract_version"]
        and failure.plan22_request_identity_sha256
        == core["plan22_request_identity_sha256"]
        and failure.code in _ADJUSTED_FAILURE_PAIRS
        and failure.reason in _ADJUSTED_FAILURE_PAIRS[failure.code]
        and failure.failure_projection_identity_sha256 == _identity(core)
    )


def _adjusted_not_attempted_is_exact(
    projection: object,
    request: CurrentSamePassMarketRegimeRequestV4,
) -> bool:
    if (
        type(projection)
        is not CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1
    ):
        return False
    core = {
        "contract_version": ADJUSTED_NOT_ATTEMPTED_CONTRACT_VERSION,
        "plan22_request_identity_sha256": request.plan22_request_identity_sha256,
        "evidence_state": "NOT_ATTEMPTED",
        "reason": "UPSTREAM_INSUFFICIENT_EVIDENCE",
    }
    return bool(
        projection.contract_version == core["contract_version"]
        and projection.plan22_request_identity_sha256
        == core["plan22_request_identity_sha256"]
        and projection.evidence_state == core["evidence_state"]
        and projection.reason == core["reason"]
        and projection.not_attempted_projection_identity_sha256 == _identity(core)
    )


def _upstream_insufficient_adjusted_composition(
    request: CurrentSamePassMarketRegimeRequestV4,
) -> _CurrentSamePassAdjustedNotAttemptedV1:
    core = {
        "contract_version": ADJUSTED_NOT_ATTEMPTED_CONTRACT_VERSION,
        "plan22_request_identity_sha256": request.plan22_request_identity_sha256,
        "evidence_state": "NOT_ATTEMPTED",
        "reason": "UPSTREAM_INSUFFICIENT_EVIDENCE",
    }
    return _CurrentSamePassAdjustedNotAttemptedV1(
        None,
        None,
        CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1(
            **core,
            not_attempted_projection_identity_sha256=_identity(core),
        ),
    )


def _adjusted_composition(
    result: AdjustedDailyCloseResultV3,
    request: CurrentSamePassMarketRegimeRequestV4,
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
) -> CurrentSamePassAdjustedCompositionResultV1:
    if type(result) is AdjustedDailyCloseSuccessV3:
        handoff = result.handoff
        if not _adjusted_handoff_is_exact(handoff, request, sessions):
            raise ValueError("adjusted handoff invalid")
        return _CurrentSamePassAdjustedSuccessV1(handoff, None, None)
    if type(result) is AdjustedDailyCloseFailure:
        if (
            result.code not in _ADJUSTED_FAILURE_PAIRS
            or result.reason not in _ADJUSTED_FAILURE_PAIRS[result.code]
        ):
            raise ValueError("adjusted failure invalid")
        core = {
            "contract_version": "provider-neutral-adjusted-daily-close@v3",
            "plan22_request_identity_sha256": request.plan22_request_identity_sha256,
            "code": result.code,
            "reason": result.reason,
        }
        return _CurrentSamePassAdjustedFailureV1(
            None,
            CurrentSamePassAdjustedDailyCloseFailureProjectionV1(
                **core, failure_projection_identity_sha256=_identity(core)
            ),
            None,
        )
    raise TypeError("adjusted result type invalid")


def _adjusted_valid(
    adjusted: CurrentSamePassAdjustedCompositionResultV1,
    request: CurrentSamePassMarketRegimeRequestV4,
    raw: PrivateCurrentSamePassRawDailyResultV1,
) -> tuple[AdjustedDailyCloseHandoffV3 | None, str | None]:
    if type(adjusted) is _CurrentSamePassAdjustedFailureV1:
        if (
            adjusted.adjusted_handoff is not None
            or adjusted.adjusted_not_attempted is not None
            or not _adjusted_failure_is_exact(adjusted.adjusted_failure, request)
        ):
            raise TypeError("adjusted composition invalid")
        return None, "ADJUSTED_DAILY_CLOSE_HANDOFF_INVALID"
    if type(adjusted) is _CurrentSamePassAdjustedNotAttemptedV1:
        if (
            adjusted.adjusted_handoff is not None
            or adjusted.adjusted_failure is not None
            or not _adjusted_not_attempted_is_exact(
                adjusted.adjusted_not_attempted, request
            )
        ):
            raise TypeError("adjusted composition invalid")
        return None, None
    if (
        type(adjusted) is not _CurrentSamePassAdjustedSuccessV1
        or adjusted.adjusted_failure is not None
        or adjusted.adjusted_not_attempted is not None
    ):
        raise TypeError("adjusted composition invalid")
    if raw.raw_grid is None:
        return None, "ADJUSTED_DAILY_CLOSE_HANDOFF_INVALID"
    if not _adjusted_handoff_is_exact(
        adjusted.adjusted_handoff, request, raw.raw_grid.sessions
    ):
        raise TypeError("adjusted composition invalid")
    handoff = adjusted.adjusted_handoff
    if handoff.temporal_label != "CURRENT_OBSERVATION":
        return handoff, "ADJUSTED_DAILY_CLOSE_HANDOFF_INVALID"
    return handoff, None


def _plan21_input(
    request: CurrentSamePassMarketRegimeRequestV4,
    raw: PrivateCurrentSamePassRawDailyResultV1,
) -> CurrentSuppliedCohortCorporateActionScreenInputV1:
    manifest = CurrentSuppliedCohortManifestV1(
        request.cohort_selected_at,
        tuple(
            CurrentCohortMemberV1(member.isin, member.effective_symbol)
            for member in request.members
        ),
    )
    if manifest.cohort_identity_sha256 != request.plan21_cohort_identity_sha256:
        raise ValueError("Plan21 cohort bridge mismatch")
    return CurrentSuppliedCohortCorporateActionScreenInputV1(
        manifest,
        raw.comparison_session,
        raw.decision_session,
        request.decision_cutoff,
        request.schedule_evidence_sha256,
        request.schedule_source,
        request.schedule_source_release,
        "UPSTOX",
    )


def _screen_valid(
    screen: object,
    request: CurrentSamePassMarketRegimeRequestV4,
    raw: PrivateCurrentSamePassRawDailyResultV1,
) -> bool:
    return published_current_corporate_action_screen_is_exact_valid_v1(
        screen,
        cohort_identity_sha256=request.plan21_cohort_identity_sha256,
        comparison_session=raw.comparison_session,
        decision_session=raw.decision_session,
        decision_cutoff=request.decision_cutoff,
        schedule_evidence_sha256=request.schedule_evidence_sha256,
        schedule_source=request.schedule_source,
        schedule_source_release=request.schedule_source_release,
        expected_isins=tuple(member.isin for member in request.members),
    )


def _screen_is_exact_structure(
    screen: object,
    request: CurrentSamePassMarketRegimeRequestV4,
    raw: PrivateCurrentSamePassRawDailyResultV1,
) -> bool:
    if (
        type(screen) is not PublishedCurrentCorporateActionScreenV1
        or not _published_screen_core_valid(screen)
    ):
        return False
    # Plan21 stays canonical; V4 raw and adjusted rows retain selection order.
    private = screen.private_result
    if (
        private.cohort_identity_sha256 != request.plan21_cohort_identity_sha256
        or private.comparison_session != raw.comparison_session
        or private.decision_session != raw.decision_session
        or private.decision_cutoff != request.decision_cutoff
        or private.schedule_evidence_sha256 != request.schedule_evidence_sha256
        or private.schedule_source != request.schedule_source
        or private.schedule_source_release != request.schedule_source_release
        or tuple(item.provider_result.isin for item in private.member_results)
        != tuple(sorted(member.isin for member in request.members))
    ):
        return False
    if (
        private.outcome
        is PrivateCorporateActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
    ):
        return _screen_valid(screen, request, raw)
    return (
        private.outcome
        is not PrivateCorporateActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
    )


def _report_and_candidate(
    request: CurrentSamePassMarketRegimeRequestV4,
    raw: PrivateCurrentSamePassRawDailyResultV1,
    market_data: CurrentSamePassDecisionMarketDataReportV1,
    screen: object,
    adjusted: CurrentSamePassAdjustedCompositionResultV1,
) -> tuple[
    CurrentSamePassMarketRegimeReportV4,
    _CurrentSamePassMemberDirectionCandidateV4 | None,
]:
    runtime = current_same_pass_market_regime_runtime_code_identity_v4()
    schema, calc = _schema_identity(), _calculation_identity()
    screen_identity = getattr(
        getattr(screen, "public_report", screen), "report_identity_sha256", None
    )
    handoff, adjusted_reason = _adjusted_valid(adjusted, request, raw)
    screen_is_valid = _screen_valid(screen, request, raw)
    upstream_insufficient = raw.evidence_state != "OBSERVED" or not screen_is_valid
    if upstream_insufficient != (
        type(adjusted) is _CurrentSamePassAdjustedNotAttemptedV1
    ):
        raise TypeError("adjusted composition invalid")
    reasons: set[str] = set(raw.reasons)
    if not screen_is_valid:
        reasons.add("CORPORATE_ACTION_SCREEN_INSUFFICIENT")
    if adjusted_reason:
        reasons.add(adjusted_reason)
    raw_grid = raw.raw_grid
    rows: list[_CurrentSamePassMemberDirectionRowV4] = []
    if not reasons and raw_grid is not None and handoff is not None:
        bars = {(bar.isin, bar.session): bar for bar in raw_grid.bars}
        adjusted_members = {member.isin: member for member in handoff.members}
        for member in request.members:
            start, end, adjusted_member = (
                bars.get((member.isin, raw.comparison_session)),
                bars.get((member.isin, raw.decision_session)),
                adjusted_members.get(member.isin),
            )
            if start is None or end is None or adjusted_member is None:
                reasons.add("RAW_ADJUSTED_DIRECTION_CONFLICT")
                break
            direction = _raw_direction(start.close, end.close)
            if direction != _raw_direction(
                str(adjusted_member.s0.close),
                str(adjusted_member.s20.close),
            ):
                reasons.add("RAW_ADJUSTED_DIRECTION_CONFLICT")
                break
            core = {
                "isin": member.isin,
                "exchange": "NSE",
                "effective_symbol": member.effective_symbol,
                "direction": direction,
            }
            rows.append(
                _CurrentSamePassMemberDirectionRowV4(
                    **core, row_identity_sha256=_identity(core)
                )
            )
    if reasons:
        ordered = _ordered_reasons(tuple(reasons))
        core = {
            "contract_version": CONTRACT_VERSION,
            "schema_identity_sha256": schema,
            "calculation_identity_sha256": calc,
            "runtime_code_identity_sha256": runtime,
            "evidence_state": "INSUFFICIENT_EVIDENCE",
            "request_identity_sha256": request.request_identity_sha256,
            "canonical_cohort_identity_sha256": request.canonical_cohort_identity_sha256,
            "cohort_size": len(request.members),
            "decision_cutoff": request.decision_cutoff,
            "decision_session": raw.decision_session,
            "comparison_session": raw.comparison_session,
            "market_data_report_identity_sha256": market_data.report_identity_sha256,
            "corporate_action_screen_identity_sha256": screen_identity,
            "adjusted_handoff_identity_sha256": None
            if handoff is None
            else handoff.handoff_identity_sha256,
            "regime": None,
            "advances": None,
            "declines": None,
            "unchanged": None,
            "reasons": ordered,
        }
        return CurrentSamePassMarketRegimeReportV4(
            **core, report_identity_sha256=_identity(core)
        ), None
    advances = sum(row.direction == "ADVANCE" for row in rows)
    declines = sum(row.direction == "DECLINE" for row in rows)
    regime = (
        "BROAD_ADVANCE"
        if advances * 5 >= len(rows) * 3
        else "BROAD_DECLINE"
        if declines * 5 >= len(rows) * 3
        else "MIXED_PARTICIPATION"
    )
    core = {
        "contract_version": CONTRACT_VERSION,
        "schema_identity_sha256": schema,
        "calculation_identity_sha256": calc,
        "runtime_code_identity_sha256": runtime,
        "evidence_state": "OBSERVED",
        "request_identity_sha256": request.request_identity_sha256,
        "canonical_cohort_identity_sha256": request.canonical_cohort_identity_sha256,
        "cohort_size": len(request.members),
        "decision_cutoff": request.decision_cutoff,
        "decision_session": raw.decision_session,
        "comparison_session": raw.comparison_session,
        "market_data_report_identity_sha256": market_data.report_identity_sha256,
        "corporate_action_screen_identity_sha256": screen_identity,
        "adjusted_handoff_identity_sha256": handoff.handoff_identity_sha256,
        "regime": regime,
        "advances": advances,
        "declines": declines,
        "unchanged": len(rows) - advances - declines,
        "reasons": (),
    }
    report = CurrentSamePassMarketRegimeReportV4(
        **core, report_identity_sha256=_identity(core)
    )
    candidate_core = {
        "request_identity_sha256": request.request_identity_sha256,
        "raw_grid_identity_sha256": raw_grid.raw_grid_identity_sha256,
        "corporate_action_screen_identity_sha256": cast(str, screen_identity),
        "adjusted_handoff_identity_sha256": handoff.handoff_identity_sha256,
        "market_regime_report_identity_sha256": report.report_identity_sha256,
        "canonical_cohort_identity_sha256": request.canonical_cohort_identity_sha256,
        "schedule_identity_sha256": raw_grid.schedule_identity_sha256,
        "price_basis": PRICE_BASIS,
        "decision_cutoff": request.decision_cutoff,
        "rows": tuple(rows),
    }
    return report, _CurrentSamePassMemberDirectionCandidateV4(
        **candidate_core, direction_candidate_identity_sha256=_identity(candidate_core)
    )


def _ledger(
    request: CurrentSamePassMarketRegimeRequestV4,
    raw: PrivateCurrentSamePassRawDailyResultV1,
    market_data: CurrentSamePassDecisionMarketDataReportV1,
    screen: object,
    adjusted: CurrentSamePassAdjustedCompositionResultV1,
    report: CurrentSamePassMarketRegimeReportV4,
) -> tuple[CurrentSamePassContextComponentLedgerRowV1, ...]:
    raw_identity = (
        raw.raw_grid.raw_grid_identity_sha256
        if raw.raw_grid
        else raw.raw_result_identity_sha256
    )
    screen_report = getattr(screen, "public_report", screen)
    screen_identity = getattr(screen_report, "report_identity_sha256", "")
    adjusted_identity = (
        adjusted.adjusted_handoff.handoff_identity_sha256
        if type(adjusted) is _CurrentSamePassAdjustedSuccessV1
        else adjusted.adjusted_failure.failure_projection_identity_sha256
        if type(adjusted) is _CurrentSamePassAdjustedFailureV1
        else adjusted.adjusted_not_attempted.not_attempted_projection_identity_sha256
    )
    raw_known = (
        [
            item.known_at
            for item in (
                *raw.raw_grid.bars,
                *(raw.mapping_receipts or ()),
                raw.partial_current_session,
            )
            if _utc(item.known_at)
        ]
        if raw.evidence_state == "OBSERVED" and raw.raw_grid is not None
        else (
            [raw.partial_current_session.known_at]
            if _utc(raw.partial_current_session.known_at)
            else []
        )
    )
    raw_known_at = max(raw_known) if raw_known else None
    private_screen = getattr(screen, "private_result", None)
    screen_known_values = [
        getattr(getattr(item, "provider_result", None), "retrieved_at", None)
        for item in getattr(private_screen, "member_results", ())
    ]
    screen_known = [item for item in screen_known_values if _utc(item)]
    screen_known_at = max(screen_known) if screen_known else None
    adjusted_known_at = (
        adjusted.adjusted_handoff.retrieved_at
        if type(adjusted) is _CurrentSamePassAdjustedSuccessV1
        else None
    )
    regime_known_at = (
        max(
            item
            for item in (raw_known_at, screen_known_at, adjusted_known_at)
            if _utc(item)
        )
        if any(
            _utc(item) for item in (raw_known_at, screen_known_at, adjusted_known_at)
        )
        else None
    )
    rows = (
        (
            0,
            "RAW_GRID_V1",
            "current-same-pass-raw-daily-grid@v4",
            raw.evidence_state,
            raw_identity,
            raw_known_at,
            raw.reasons,
        ),
        (
            1,
            "CORPORATE_ACTION_SCREEN_V1",
            "current-supplied-cohort-corporate-action-screen@v1",
            "SCREENED"
            if _screen_valid(screen, request, raw)
            else "INSUFFICIENT_EVIDENCE",
            screen_identity,
            screen_known_at,
            ()
            if _screen_valid(screen, request, raw)
            else ("CORPORATE_ACTION_SCREEN_INSUFFICIENT",),
        ),
        (
            2,
            "ADJUSTED_DAILY_CLOSE_V2",
            "provider-neutral-adjusted-daily-close@v3",
            "SUCCESS"
            if type(adjusted) is _CurrentSamePassAdjustedSuccessV1
            else adjusted.adjusted_failure.code
            if type(adjusted) is _CurrentSamePassAdjustedFailureV1
            else "NOT_ATTEMPTED",
            adjusted_identity,
            adjusted_known_at,
            ()
            if type(adjusted) is _CurrentSamePassAdjustedSuccessV1
            else (adjusted.adjusted_failure.reason,)
            if type(adjusted) is _CurrentSamePassAdjustedFailureV1
            else ("UPSTREAM_INSUFFICIENT_EVIDENCE",),
        ),
        (
            3,
            "MARKET_REGIME_V4",
            CONTRACT_VERSION,
            report.evidence_state,
            report.report_identity_sha256,
            regime_known_at,
            report.reasons,
        ),
    )
    result = []
    for position, component, contract, state, identity, known_at, reasons in rows:
        core = {
            "position": position,
            "component": component,
            "contract_version": contract,
            "evidence_state": state,
            "schema_identity_sha256": (
                raw.raw_grid.schema_identity_sha256
                if raw.raw_grid is not None
                else current_same_pass_raw_daily_schema_identity_v4()
            )
            if position == 0
            else getattr(screen_report, "screen_schema_identity_sha256", None)
            if position == 1
            else None
            if position == 2
            else report.schema_identity_sha256,
            "runtime_code_identity_sha256": (
                raw.raw_grid.runtime_code_identity_sha256
                if raw.raw_grid is not None
                else current_same_pass_raw_daily_runtime_code_identity_v4()
            )
            if position == 0
            else getattr(screen_report, "runtime_code_identity_sha256", None)
            if position == 1
            else None
            if position == 2
            else report.runtime_code_identity_sha256,
            "primary_identity_sha256": identity,
            "known_at": known_at,
            "reasons": tuple(reasons),
        }
        result.append(
            CurrentSamePassContextComponentLedgerRowV1(
                **core, ledger_row_identity_sha256=_identity(core)
            )
        )
    return tuple(result)


def _context_object(
    request: CurrentSamePassMarketRegimeRequestV4,
    raw: PrivateCurrentSamePassRawDailyResultV1,
    screen: object,
    adjusted: CurrentSamePassAdjustedCompositionResultV1,
) -> PrivateCurrentSamePassMarketContextObjectV4:
    market_data = _decision_report(raw, request)
    report, candidate = _report_and_candidate(
        request, raw, market_data, screen, adjusted
    )
    handoff = (
        adjusted.adjusted_handoff
        if type(adjusted) is _CurrentSamePassAdjustedSuccessV1
        else None
    )
    failure = (
        adjusted.adjusted_failure
        if type(adjusted) is _CurrentSamePassAdjustedFailureV1
        else None
    )
    not_attempted = (
        adjusted.adjusted_not_attempted
        if type(adjusted) is _CurrentSamePassAdjustedNotAttemptedV1
        else None
    )
    ledger = _ledger(request, raw, market_data, screen, adjusted, report)
    runtime = current_same_pass_market_regime_runtime_code_identity_v4()
    identity_core = {
        "contract_version": ARCHIVE_CONTRACT_VERSION,
        "schema_identity_sha256": _schema_identity(),
        "configuration_identity_sha256": _configuration_identity(),
        "runtime_code_identity_sha256": runtime,
        "request_identity_sha256": request.request_identity_sha256,
        "raw_result_identity_sha256": raw.raw_result_identity_sha256,
        "market_data_report_identity_sha256": market_data.report_identity_sha256,
        "screen_identity": getattr(
            getattr(screen, "public_report", screen), "report_identity_sha256", None
        ),
        "adjusted_handoff_identity_sha256": None
        if handoff is None
        else handoff.handoff_identity_sha256,
        "adjusted_failure_projection_identity_sha256": None
        if failure is None
        else failure.failure_projection_identity_sha256,
        "adjusted_not_attempted_projection_identity_sha256": None
        if not_attempted is None
        else not_attempted.not_attempted_projection_identity_sha256,
        "market_regime_report_identity_sha256": report.report_identity_sha256,
        "direction_candidate_identity_sha256": None
        if candidate is None
        else candidate.direction_candidate_identity_sha256,
        "component_ledger": tuple(row.ledger_row_identity_sha256 for row in ledger),
        "temporal_scope": "CURRENT_SAME_PASS_ONLY",
        "historical_availability_claim": False,
        "replay_capability": "NONE",
    }
    context_identity = _identity(identity_core)
    base = {
        "contract_version": ARCHIVE_CONTRACT_VERSION,
        "schema_identity_sha256": _schema_identity(),
        "configuration_identity_sha256": _configuration_identity(),
        "runtime_code_identity_sha256": runtime,
        "request": request,
        "raw_result": raw,
        "market_data_report": market_data,
        "corporate_action_screen": screen,
        "adjusted_handoff": handoff,
        "adjusted_failure": failure,
        "adjusted_not_attempted": not_attempted,
        "market_regime_report": report,
        "direction_candidate": candidate,
        "component_ledger": ledger,
        "temporal_scope": "CURRENT_SAME_PASS_ONLY",
        "historical_availability_claim": False,
        "replay_capability": "NONE",
        "context_identity_sha256": context_identity,
    }
    context_object_sha256 = _sha(_canonical(base))
    context = PrivateCurrentSamePassMarketContextObjectV4(
        **base, context_object_sha256=context_object_sha256
    )
    return context


def _candidate_structure_exactness_failure(  # noqa: C901 - exact replay discriminator
    request: CurrentSamePassMarketRegimeRequestV4,
    candidate: object,
) -> str | None:
    """Replay every closed context binding and name the first failed invariant."""
    if type(candidate) is not _CurrentSamePassMarketContextCandidateV4:
        return "CANDIDATE_TYPE_MISMATCH"
    context = candidate.context_object
    if type(context) is not PrivateCurrentSamePassMarketContextObjectV4:
        return "CONTEXT_TYPE_MISMATCH"
    adjusted_states = (
        type(context.adjusted_handoff) is AdjustedDailyCloseHandoffV3
        and context.adjusted_failure is None
        and context.adjusted_not_attempted is None,
        context.adjusted_handoff is None
        and _adjusted_failure_is_exact(context.adjusted_failure, request)
        and context.adjusted_not_attempted is None,
        context.adjusted_handoff is None
        and context.adjusted_failure is None
        and _adjusted_not_attempted_is_exact(context.adjusted_not_attempted, request),
    )
    if sum(adjusted_states) != 1:
        return "ADJUSTED_STATE_INVALID"
    if context.request != request:
        return "REQUEST_MISMATCH"
    if not current_same_pass_raw_daily_result_is_exact_valid_v4(
        context.raw_result, request
    ):
        return "RAW_RESULT_REPLAY_FAILED"
    if not _screen_is_exact_structure(
        context.corporate_action_screen, request, context.raw_result
    ):
        return "SCREEN_REPLAY_FAILED"
    adjusted: CurrentSamePassAdjustedCompositionResultV1 = (
        _CurrentSamePassAdjustedSuccessV1(context.adjusted_handoff, None, None)
        if adjusted_states[0]
        else _CurrentSamePassAdjustedFailureV1(None, context.adjusted_failure, None)
        if adjusted_states[1]
        else _CurrentSamePassAdjustedNotAttemptedV1(
            None, None, context.adjusted_not_attempted
        )
    )
    try:
        expected = _context_object(
            request,
            context.raw_result,
            context.corporate_action_screen,
            adjusted,
        )
    except (TypeError, ValueError, AttributeError):
        return "CONTEXT_REPLAY_RAISED"
    if candidate.candidate_identity_sha256 != _identity(
        {
            "context_identity_sha256": expected.context_identity_sha256,
            "context_object_sha256": expected.context_object_sha256,
        }
    ):
        return "CANDIDATE_IDENTITY_MISMATCH"
    if expected.context_identity_sha256 != context.context_identity_sha256:
        return "CONTEXT_IDENTITY_MISMATCH"
    if expected.context_object_sha256 != context.context_object_sha256:
        return "CONTEXT_OBJECT_IDENTITY_MISMATCH"
    if expected.canonical_json_bytes() != context.canonical_json_bytes():
        return "CONTEXT_BYTES_MISMATCH"
    return None


def _candidate_structure_is_exact(
    request: CurrentSamePassMarketRegimeRequestV4,
    candidate: object,
) -> bool:
    return _candidate_structure_exactness_failure(request, candidate) is None


def _legacy_validate_retained_current_same_pass_market_context_v4(
    value: object,
    context: PrivateCurrentSamePassMarketContextObjectV4,
) -> bool:
    """Validate an archive projection against the caller's current candidate."""
    if (
        type(value) is not RetainedCurrentSamePassMarketContextV4
        or type(value._archive_seal) is not _CurrentSamePassMarketContextArchiveSealV1
    ):
        return False
    core = _retained_context_public_projection(
        evidence_state="RETAINED",
        context_identity_sha256=context.context_identity_sha256,
        context_object_sha256=context.context_object_sha256,
        context_receipt_identity_sha256=value.context_receipt_identity_sha256,
        completion_marker_identity_sha256=value.completion_marker_identity_sha256,
        archive_known_at=value.archive_known_at,
        market_data_report=context.market_data_report,
        market_regime_report=context.market_regime_report,
        partial_current_session=context.raw_result.partial_current_session,
    )
    return (
        value.context_identity_sha256 == context.context_identity_sha256
        and value.context_object_sha256 == context.context_object_sha256
        and value.retained_context_identity_sha256 == _identity(core)
    )


_ArchiveMemberIdentity: TypeAlias = tuple[int, int, int, int, int, int, int, int]


def _archive_member_identity(info: os.stat_result) -> _ArchiveMemberIdentity:
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _private_regular(info: os.stat_result, size: int) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == 0o600
        and info.st_nlink == 1
        and info.st_size == size
    )


def _read_exact_member(
    parent: int, name: str, maximum: int
) -> tuple[bytes, _ArchiveMemberIdentity] | None:
    try:
        fd = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent,
        )
    except FileNotFoundError:
        return None
    try:
        named_before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        opened_before = os.fstat(fd)
        if (
            not 1 <= opened_before.st_size <= maximum
            or not _private_regular(opened_before, opened_before.st_size)
            or not _same_metadata(named_before, opened_before)
        ):
            raise ValueError("unsafe archive object")
        chunks: list[bytes] = []
        remaining = opened_before.st_size
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                raise ValueError("short archive object")
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        named_after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        opened_after = os.fstat(fd)
        if (
            len(raw) != opened_before.st_size
            or not _same_metadata(named_before, named_after)
            or not _same_metadata(opened_before, opened_after)
            or not _same_metadata(opened_after, named_after)
            or not _private_regular(named_after, len(raw))
        ):
            raise ValueError("archive object changed")
        return raw, _archive_member_identity(named_after)
    finally:
        os.close(fd)


def _read_exact(parent: int, name: str, maximum: int) -> bytes | None:
    entry = _read_exact_member(parent, name, maximum)
    return None if entry is None else entry[0]


def _parse_archive_instant(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError("archive instant required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not _utc(result) or _instant(result) != value:
        raise ValueError("archive instant invalid")
    return result


def _parse_context_archive_records(
    context: PrivateCurrentSamePassMarketContextObjectV4,
    receipt_raw: bytes,
    marker_raw: bytes,
    decision_cutoff: datetime,
) -> tuple[CurrentSamePassContextReceiptV1, CurrentSamePassContextCompletionMarkerV1]:
    """Parse the immutable persisted commit records without normalizing bytes."""
    receipt_value = json.loads(receipt_raw)
    marker_value = json.loads(marker_raw)
    receipt_fields = {item.name for item in fields(CurrentSamePassContextReceiptV1)}
    marker_fields = {
        item.name for item in fields(CurrentSamePassContextCompletionMarkerV1)
    }
    if (
        type(receipt_value) is not dict
        or type(marker_value) is not dict
        or set(receipt_value) != receipt_fields
        or set(marker_value) != marker_fields
        or _canonical(receipt_value) != receipt_raw
        or _canonical(marker_value) != marker_raw
    ):
        raise ValueError("noncanonical archive records")
    receipt_time = _parse_archive_instant(receipt_value["archive_known_at"])
    marker_time = _parse_archive_instant(marker_value["archive_known_at"])
    receipt = CurrentSamePassContextReceiptV1(
        contract_version=receipt_value["contract_version"],
        context_identity_sha256=receipt_value["context_identity_sha256"],
        context_object_sha256=receipt_value["context_object_sha256"],
        context_byte_count=receipt_value["context_byte_count"],
        context_filename=receipt_value["context_filename"],
        archive_known_at=receipt_time,
        context_receipt_identity_sha256=receipt_value[
            "context_receipt_identity_sha256"
        ],
    )
    marker = CurrentSamePassContextCompletionMarkerV1(
        contract_version=marker_value["contract_version"],
        context_identity_sha256=marker_value["context_identity_sha256"],
        context_object_sha256=marker_value["context_object_sha256"],
        context_receipt_identity_sha256=marker_value["context_receipt_identity_sha256"],
        receipt_sha256=marker_value["receipt_sha256"],
        archive_known_at=marker_time,
        completion_marker_identity_sha256=marker_value[
            "completion_marker_identity_sha256"
        ],
    )
    receipt_core = {
        "contract_version": receipt.contract_version,
        "context_identity_sha256": receipt.context_identity_sha256,
        "context_object_sha256": receipt.context_object_sha256,
        "context_byte_count": receipt.context_byte_count,
        "context_filename": receipt.context_filename,
        "archive_known_at": receipt.archive_known_at,
    }
    marker_core = {
        "contract_version": marker.contract_version,
        "context_identity_sha256": marker.context_identity_sha256,
        "context_object_sha256": marker.context_object_sha256,
        "context_receipt_identity_sha256": marker.context_receipt_identity_sha256,
        "receipt_sha256": marker.receipt_sha256,
        "archive_known_at": marker.archive_known_at,
    }
    context_raw = context.canonical_json_bytes()
    if (
        receipt.contract_version != "current-same-pass-market-context-receipt@v1"
        or marker.contract_version != "current-same-pass-market-context-marker@v1"
        or type(receipt.context_byte_count) is not int
        or receipt.context_identity_sha256 != context.context_identity_sha256
        or receipt.context_object_sha256 != context.context_object_sha256
        or receipt.context_byte_count != len(context_raw)
        or receipt.context_filename != f"context-{context.context_identity_sha256}.json"
        or receipt.archive_known_at > decision_cutoff
        or receipt.context_receipt_identity_sha256 != _identity(receipt_core)
        or marker.context_identity_sha256 != context.context_identity_sha256
        or marker.context_object_sha256 != context.context_object_sha256
        or marker.context_receipt_identity_sha256
        != receipt.context_receipt_identity_sha256
        or marker.receipt_sha256 != _sha(receipt_raw)
        or marker.archive_known_at != receipt.archive_known_at
        or marker.completion_marker_identity_sha256 != _identity(marker_core)
        or not all(
            _DIGEST.fullmatch(item) is not None
            for item in (
                receipt.context_identity_sha256,
                receipt.context_object_sha256,
                receipt.context_receipt_identity_sha256,
                marker.context_identity_sha256,
                marker.context_object_sha256,
                marker.context_receipt_identity_sha256,
                marker.receipt_sha256,
                marker.completion_marker_identity_sha256,
            )
        )
    ):
        raise ValueError("spliced archive records")
    return receipt, marker


def _publish_exact(  # noqa: C901
    parent: int, name: str, raw: bytes, maximum: int
) -> None:
    if not 1 <= len(raw) <= maximum:
        raise ValueError("archive bounds")
    try:
        fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent,
        )
    except FileExistsError as error:
        existing = _read_exact(parent, name, maximum)
        if existing != raw:
            raise ValueError("immutable archive collision") from error
        return
    try:
        if os.write(fd, raw) != len(raw):
            raise OSError("short archive write")
        os.fsync(fd)
    finally:
        os.close(fd)


def _archive_directory_bound(root: int, directory: int) -> bool:
    """Prove the held directory is still the name under the leased root."""
    try:
        named = os.stat(
            ".current-same-pass-market-regime-v4",
            dir_fd=root,
            follow_symlinks=False,
        )
        opened = os.fstat(directory)
    except OSError:
        return False
    return (
        stat.S_ISDIR(named.st_mode)
        and stat.S_ISDIR(opened.st_mode)
        and named.st_uid == os.geteuid()
        and opened.st_uid == os.geteuid()
        and stat.S_IMODE(named.st_mode) == stat.S_IMODE(opened.st_mode) == 0o700
        and (named.st_dev, named.st_ino) == (opened.st_dev, opened.st_ino)
    )


def _context_archive_guard_bytes(
    phase: Literal["PENDING", "ADMISSIBLE"],
    *,
    context_identity: str,
    receipt_identity: str,
    marker_raw: bytes,
    archive_known_at: datetime,
) -> bytes:
    return _canonical(
        {
            "contract_version": "current-same-pass-market-context-guard@v1",
            "phase": phase,
            "context_identity_sha256": context_identity,
            "context_receipt_identity_sha256": receipt_identity,
            "completion_marker_sha256": _sha(marker_raw),
            "archive_known_at": archive_known_at,
        }
    )


class _FileCurrentSamePassMarketContextArchiveV1:
    """Create-only archive; current commits require marker and admissibility guard."""

    def __init__(self, root: object, *, clock: _TrustedClockV1 | None = None) -> None:
        if type(root) is not type(Path()):
            raise TypeError("Path root required")
        self._root = root
        self._clock = clock or _SystemClockV1()

    def archive_exact(  # noqa: C901
        self,
        request: CurrentSamePassMarketRegimeRequestV4,
        candidate: _CurrentSamePassMarketContextCandidateV4,
        lease: StorageRootLease,
        *,
        trusted_clock: _TrustedClockV1 | None = None,
    ) -> RetainedCurrentSamePassMarketContextV4 | CurrentSamePassArchiveFailureV1:
        archive_clock = trusted_clock or self._clock

        def retained_context(
            context: PrivateCurrentSamePassMarketContextObjectV4,
            receipt: CurrentSamePassContextReceiptV1,
            marker: CurrentSamePassContextCompletionMarkerV1,
        ) -> RetainedCurrentSamePassMarketContextV4:
            retained_core = _retained_context_public_projection(
                evidence_state="RETAINED",
                context_identity_sha256=context.context_identity_sha256,
                context_object_sha256=context.context_object_sha256,
                context_receipt_identity_sha256=receipt.context_receipt_identity_sha256,
                completion_marker_identity_sha256=marker.completion_marker_identity_sha256,
                archive_known_at=receipt.archive_known_at,
                market_data_report=context.market_data_report,
                market_regime_report=context.market_regime_report,
                partial_current_session=context.raw_result.partial_current_session,
            )
            retained_identity = _identity(retained_core)
            seal = object.__new__(_CurrentSamePassMarketContextArchiveSealV1)
            result = object.__new__(RetainedCurrentSamePassMarketContextV4)
            for name, value in {
                **retained_core,
                "retained_context_identity_sha256": retained_identity,
                "_archive_seal": seal,
            }.items():
                object.__setattr__(result, name, value)
            return result

        context_identity: str | None = None
        try:
            if (
                type(request) is not CurrentSamePassMarketRegimeRequestV4
                or type(lease) is not StorageRootLease
                or not cast(Any, _candidate_is_exact)(request, candidate)
            ):
                raise ValueError("invalid candidate")
            context = candidate.context_object
            context_identity = context.context_identity_sha256
            raw = context.canonical_json_bytes()
            if not 1 <= len(raw) <= _MAX_CONTEXT_BYTES:
                raise ValueError("invalid context bytes")
            with lease.root_operation(self._root) as operation:
                with suppress(FileExistsError):
                    os.mkdir(
                        ".current-same-pass-market-regime-v4",
                        0o700,
                        dir_fd=operation.descriptor,
                    )
                directory = os.open(
                    ".current-same-pass-market-regime-v4",
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=operation.descriptor,
                )
                if not _archive_directory_bound(operation.descriptor, directory):
                    os.close(directory)
                    raise ValueError("archive root binding changed")
                try:
                    stem = context.context_identity_sha256
                    context_name = f"context-{stem}.json"
                    receipt_name = f"retained-{stem}.json"
                    marker_name = f"completion-{stem}.json"
                    pending_name = f"pending-{stem}.json"
                    admissible_name = f"admissible-{stem}.json"
                    _publish_exact(directory, context_name, raw, _MAX_CONTEXT_BYTES)
                    if _read_exact(directory, context_name, _MAX_CONTEXT_BYTES) != raw:
                        raise ValueError("context stable read failed")
                    existing = _read_exact(directory, receipt_name, _MAX_RECEIPT_BYTES)
                    receipt_preexisted = existing is not None
                    if existing is None:
                        archive_known_at = archive_clock.now() + timedelta(seconds=30)
                        if (
                            not _utc(archive_known_at)
                            or archive_known_at > request.decision_cutoff
                        ):
                            raise ValueError("archive deadline")
                        receipt_core = {
                            "contract_version": "current-same-pass-market-context-receipt@v1",
                            "context_identity_sha256": stem,
                            "context_object_sha256": context.context_object_sha256,
                            "context_byte_count": len(raw),
                            "context_filename": context_name,
                            "archive_known_at": archive_known_at,
                        }
                        receipt = CurrentSamePassContextReceiptV1(
                            **receipt_core,
                            context_receipt_identity_sha256=_identity(receipt_core),
                        )
                        receipt_raw = _canonical(receipt)
                        _publish_exact(
                            directory, receipt_name, receipt_raw, _MAX_RECEIPT_BYTES
                        )
                    else:
                        receipt_value = json.loads(existing)
                        if (
                            type(receipt_value) is not dict
                            or set(receipt_value)
                            != {
                                field.name
                                for field in fields(CurrentSamePassContextReceiptV1)
                            }
                            or _canonical(receipt_value) != existing
                        ):
                            raise ValueError("invalid context receipt")
                        archive_known_at = datetime.fromisoformat(
                            str(receipt_value["archive_known_at"]).replace(
                                "Z", "+00:00"
                            )
                        )
                        receipt_core = {
                            "contract_version": receipt_value["contract_version"],
                            "context_identity_sha256": receipt_value[
                                "context_identity_sha256"
                            ],
                            "context_object_sha256": receipt_value[
                                "context_object_sha256"
                            ],
                            "context_byte_count": receipt_value["context_byte_count"],
                            "context_filename": receipt_value["context_filename"],
                            "archive_known_at": archive_known_at,
                        }
                        if (
                            not _utc(archive_known_at)
                            or receipt_core["context_identity_sha256"] != stem
                            or receipt_core["context_object_sha256"]
                            != context.context_object_sha256
                            or receipt_core["context_byte_count"] != len(raw)
                            or receipt_core["context_filename"] != context_name
                            or receipt_value["context_receipt_identity_sha256"]
                            != _identity(receipt_core)
                        ):
                            raise ValueError("spliced context receipt")
                        receipt = CurrentSamePassContextReceiptV1(
                            **receipt_core,
                            context_receipt_identity_sha256=receipt_value[
                                "context_receipt_identity_sha256"
                            ],
                        )
                        receipt_raw = existing
                    existing_marker = _read_exact(
                        directory, marker_name, _MAX_MARKER_BYTES
                    )
                    pending_guard = _read_exact(
                        directory, pending_name, _MAX_MARKER_BYTES
                    )
                    admissible_guard = _read_exact(
                        directory, admissible_name, _MAX_MARKER_BYTES
                    )
                    if receipt_preexisted and existing_marker is None:
                        raise ValueError("uncommitted context receipt")
                    if existing_marker is not None:
                        marker_value = json.loads(existing_marker)
                        if (
                            type(marker_value) is not dict
                            or set(marker_value)
                            != {
                                field.name
                                for field in fields(
                                    CurrentSamePassContextCompletionMarkerV1
                                )
                            }
                            or _canonical(marker_value) != existing_marker
                        ):
                            raise ValueError("invalid context completion marker")
                        marker_core = {
                            "contract_version": marker_value["contract_version"],
                            "context_identity_sha256": marker_value[
                                "context_identity_sha256"
                            ],
                            "context_object_sha256": marker_value[
                                "context_object_sha256"
                            ],
                            "context_receipt_identity_sha256": marker_value[
                                "context_receipt_identity_sha256"
                            ],
                            "receipt_sha256": marker_value["receipt_sha256"],
                            "archive_known_at": datetime.fromisoformat(
                                str(marker_value["archive_known_at"]).replace(
                                    "Z", "+00:00"
                                )
                            ),
                        }
                        if (
                            not _utc(marker_core["archive_known_at"])
                            or marker_core["archive_known_at"] != archive_known_at
                            or archive_known_at > request.decision_cutoff
                            or marker_core["context_identity_sha256"] != stem
                            or marker_core["context_object_sha256"]
                            != context.context_object_sha256
                            or marker_core["context_receipt_identity_sha256"]
                            != receipt.context_receipt_identity_sha256
                            or marker_core["receipt_sha256"] != _sha(receipt_raw)
                            or marker_value["completion_marker_identity_sha256"]
                            != _identity(marker_core)
                        ):
                            raise ValueError("spliced context completion marker")
                        marker = CurrentSamePassContextCompletionMarkerV1(
                            **marker_core,
                            completion_marker_identity_sha256=marker_value[
                                "completion_marker_identity_sha256"
                            ],
                        )
                        expected_pending_guard = _context_archive_guard_bytes(
                            "PENDING",
                            context_identity=stem,
                            receipt_identity=receipt.context_receipt_identity_sha256,
                            marker_raw=existing_marker,
                            archive_known_at=archive_known_at,
                        )
                        expected_admissible_guard = _context_archive_guard_bytes(
                            "ADMISSIBLE",
                            context_identity=stem,
                            receipt_identity=receipt.context_receipt_identity_sha256,
                            marker_raw=existing_marker,
                            archive_known_at=archive_known_at,
                        )
                        if (pending_guard, admissible_guard) not in (
                            (None, None),
                            (expected_pending_guard, expected_admissible_guard),
                        ):
                            raise ValueError("inadmissible context completion marker")
                        receipt, marker = _parse_context_archive_records(
                            context,
                            receipt_raw,
                            existing_marker,
                            request.decision_cutoff,
                        )
                        operation.ensure_live()
                        if (
                            not _archive_directory_bound(
                                operation.descriptor, directory
                            )
                            or _read_exact(directory, context_name, _MAX_CONTEXT_BYTES)
                            != raw
                            or _read_exact(directory, receipt_name, _MAX_RECEIPT_BYTES)
                            != receipt_raw
                            or _read_exact(directory, marker_name, _MAX_MARKER_BYTES)
                            != existing_marker
                            or (
                                pending_guard is not None
                                and (
                                    _read_exact(
                                        directory,
                                        pending_name,
                                        _MAX_MARKER_BYTES,
                                    )
                                    != expected_pending_guard
                                    or _read_exact(
                                        directory,
                                        admissible_name,
                                        _MAX_MARKER_BYTES,
                                    )
                                    != expected_admissible_guard
                                )
                            )
                        ):
                            raise ValueError("archive retry binding changed")
                        while archive_clock.now() < archive_known_at:
                            time.sleep(0.001)
                        operation.ensure_live()
                        if (
                            not _archive_directory_bound(
                                operation.descriptor, directory
                            )
                            or _read_exact(directory, context_name, _MAX_CONTEXT_BYTES)
                            != raw
                            or _read_exact(directory, receipt_name, _MAX_RECEIPT_BYTES)
                            != receipt_raw
                            or _read_exact(directory, marker_name, _MAX_MARKER_BYTES)
                            != existing_marker
                            or (
                                pending_guard is not None
                                and (
                                    _read_exact(
                                        directory,
                                        pending_name,
                                        _MAX_MARKER_BYTES,
                                    )
                                    != expected_pending_guard
                                    or _read_exact(
                                        directory,
                                        admissible_name,
                                        _MAX_MARKER_BYTES,
                                    )
                                    != expected_admissible_guard
                                )
                            )
                        ):
                            raise ValueError(
                                "archive retry changed before logical commit"
                            )
                        return retained_context(context, receipt, marker)
                    operation.ensure_live()
                    if (
                        not _archive_directory_bound(operation.descriptor, directory)
                        or not _utc(archive_known_at)
                        or archive_known_at > request.decision_cutoff
                        or archive_clock.now() > archive_known_at
                        or _read_exact(directory, context_name, _MAX_CONTEXT_BYTES)
                        != raw
                        or _read_exact(directory, receipt_name, _MAX_RECEIPT_BYTES)
                        != receipt_raw
                    ):
                        raise ValueError("archive pre-marker revalidation failed")
                    marker_core = {
                        "contract_version": "current-same-pass-market-context-marker@v1",
                        "context_identity_sha256": stem,
                        "context_object_sha256": context.context_object_sha256,
                        "context_receipt_identity_sha256": receipt.context_receipt_identity_sha256,
                        "receipt_sha256": _sha(receipt_raw),
                        "archive_known_at": archive_known_at,
                    }
                    marker = CurrentSamePassContextCompletionMarkerV1(
                        **marker_core,
                        completion_marker_identity_sha256=_identity(marker_core),
                    )
                    marker_raw = _canonical(marker)
                    pending_raw = _context_archive_guard_bytes(
                        "PENDING",
                        context_identity=stem,
                        receipt_identity=receipt.context_receipt_identity_sha256,
                        marker_raw=marker_raw,
                        archive_known_at=archive_known_at,
                    )
                    admissible_raw = _context_archive_guard_bytes(
                        "ADMISSIBLE",
                        context_identity=stem,
                        receipt_identity=receipt.context_receipt_identity_sha256,
                        marker_raw=marker_raw,
                        archive_known_at=archive_known_at,
                    )
                    admissible_published = False
                    try:
                        _publish_exact(
                            directory,
                            pending_name,
                            pending_raw,
                            _MAX_MARKER_BYTES,
                        )
                        os.fsync(directory)
                        _publish_exact(
                            directory, marker_name, marker_raw, _MAX_MARKER_BYTES
                        )
                        operation.ensure_live()
                        if (
                            _read_exact(directory, context_name, _MAX_CONTEXT_BYTES)
                            != raw
                            or _read_exact(directory, receipt_name, _MAX_RECEIPT_BYTES)
                            != receipt_raw
                            or _read_exact(directory, marker_name, _MAX_MARKER_BYTES)
                            != marker_raw
                        ):
                            raise ValueError("archive binding failed")
                        os.fsync(directory)
                        operation.ensure_live()
                        if (
                            archive_clock.now() > archive_known_at
                            or not _archive_directory_bound(
                                operation.descriptor, directory
                            )
                        ):
                            raise ValueError(
                                "archive marker deadline or root binding changed"
                            )
                        _publish_exact(
                            directory,
                            admissible_name,
                            admissible_raw,
                            _MAX_MARKER_BYTES,
                        )
                        os.fsync(directory)
                        admissible_published = True
                        while archive_clock.now() < archive_known_at:
                            time.sleep(0.001)
                        operation.ensure_live()
                        receipt, marker = _parse_context_archive_records(
                            context,
                            receipt_raw,
                            marker_raw,
                            request.decision_cutoff,
                        )
                        if (
                            not _archive_directory_bound(
                                operation.descriptor, directory
                            )
                            or _read_exact(directory, context_name, _MAX_CONTEXT_BYTES)
                            != raw
                            or _read_exact(directory, receipt_name, _MAX_RECEIPT_BYTES)
                            != receipt_raw
                            or _read_exact(directory, marker_name, _MAX_MARKER_BYTES)
                            != marker_raw
                            or _read_exact(directory, pending_name, _MAX_MARKER_BYTES)
                            != pending_raw
                            or _read_exact(
                                directory, admissible_name, _MAX_MARKER_BYTES
                            )
                            != admissible_raw
                        ):
                            raise ValueError("archive changed before logical commit")
                    except (OSError, RuntimeError, ValueError):
                        if not admissible_published:
                            with suppress(OSError):
                                os.unlink(marker_name, dir_fd=directory)
                                os.fsync(directory)
                        raise
                finally:
                    os.close(directory)
            if archive_known_at > request.decision_cutoff:
                raise ValueError("archive deadline")
            return retained_context(context, receipt, marker)
        except (
            AttributeError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return _failure(request, context_identity)


def _resolve_sessions(
    schedule_store: object,
    request: CurrentSamePassMarketRegimeRequestV4,
    lease: StorageRootLease,
) -> tuple[CurrentSamePassRawSessionV1, ...] | CurrentSamePassPreflightFailureV1:
    if (
        type(schedule_store) is not ScheduleEvidenceStore
        or schedule_store.lease is not lease
    ):
        raise TypeError("Plan27 requires the delivered ScheduleEvidenceStore")
    resolved = schedule_store.resolve(request.schedule_evidence_sha256)
    if resolved.outcome is ScheduleOutcome.FAILED:
        return _preflight_failure(request, ("SCHEDULE_EVIDENCE_MISSING",))
    schedule = resolved.schedule
    if (
        resolved.outcome not in {ScheduleOutcome.RETAINED, ScheduleOutcome.RESOLVED}
        or type(schedule) is not ExpectedSessionSchedule
        or resolved.digest != request.schedule_evidence_sha256
        or schedule_digest(schedule) != request.schedule_evidence_sha256
        or schedule.source != request.schedule_source
        or schedule.source_release != request.schedule_source_release
        or schedule.timezone != "Asia/Kolkata"
    ):
        return _preflight_failure(request, ("SCHEDULE_EVIDENCE_CONFLICTED",))
    cutoff_date = request.decision_cutoff.astimezone(ZoneInfo("Asia/Kolkata")).date()
    if schedule.as_of > request.decision_cutoff or schedule.covered_to < cutoff_date:
        return _preflight_failure(request, ("SCHEDULE_EVIDENCE_STALE",))
    classified_dates = {
        *(session.trade_date for session in schedule.sessions),
        *(closure.trade_date for closure in schedule.closures),
    }
    if not all(
        day in classified_dates
        for day in (
            schedule.covered_from + timedelta(days=offset)
            for offset in range((schedule.covered_to - schedule.covered_from).days + 1)
        )
    ):
        return _preflight_failure(request, ("SCHEDULE_CONTINUITY_UNPROVEN",))
    if (
        sum(
            session.close_at <= request.decision_cutoff for session in schedule.sessions
        )
        < 21
    ):
        return _preflight_failure(request, ("LATEST_COMPLETED_SESSION_UNRESOLVED",))
    try:
        sessions = resolve_latest_completed_sessions_v1(request, schedule)
    except ValueError:
        return _preflight_failure(request, ("SCHEDULE_CONTINUITY_UNPROVEN",))
    schedule_identity = current_same_pass_schedule_identity_v1(
        schedule_evidence_sha256=request.schedule_evidence_sha256,
        schedule_source=request.schedule_source,
        schedule_source_release=request.schedule_source_release,
        timezone=schedule.timezone,
        coverage_through=schedule.covered_to,
        sessions=sessions,
    )
    if schedule_identity != request.schedule_identity_sha256:
        return _preflight_failure(request, ("SCHEDULE_EVIDENCE_CONFLICTED",))
    return sessions


def _resolve_schedule(
    schedule_store: object,
    request: CurrentSamePassMarketRegimeRequestV4,
    lease: StorageRootLease,
) -> ExpectedSessionSchedule:
    """Re-read the exact immutable schedule after public preflight succeeds."""
    if (
        type(schedule_store) is not ScheduleEvidenceStore
        or schedule_store.lease is not lease
    ):
        raise TypeError("Plan27 requires the delivered ScheduleEvidenceStore")
    resolved = schedule_store.resolve(request.schedule_evidence_sha256)
    if (
        resolved.outcome not in {ScheduleOutcome.RETAINED, ScheduleOutcome.RESOLVED}
        or type(resolved.schedule) is not ExpectedSessionSchedule
        or resolved.digest != request.schedule_evidence_sha256
    ):
        raise ValueError("Plan27 schedule changed after preflight")
    return resolved.schedule


def _active_official_session(
    schedule: ExpectedSessionSchedule, cutoff: datetime
) -> object | None:
    active = tuple(
        session
        for session in schedule.sessions
        if session.open_at <= cutoff < session.close_at
    )
    return active[0] if len(active) == 1 else None


def _plan22_bridge(
    request: CurrentSamePassMarketRegimeRequestV4,
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
) -> dict[str, object]:
    members = tuple(
        AdjustedDailyInstrumentV3(
            isin=member.isin,
            exchange=member.exchange,
            instrument_type=member.instrument_type,
            segment=member.segment,
            effective_symbol=member.effective_symbol,
            provider_symbol=member.provider_symbol,
            valid_from=member.valid_from,
            valid_through=member.valid_through,
            mapping_version=member.mapping_version,
            mapping_valid_from=member.mapping_valid_from,
            mapping_valid_through=member.mapping_valid_through,
            mapping_identity=member.mapping_identity,
        )
        for member in request.members
    )
    schedule_identity = adjusted_daily_schedule_identity_v3(
        sessions=tuple(item.session for item in sessions),
        decision_session_official_close_at=sessions[-1].close_at,
        schedule_evidence_sha256=request.schedule_evidence_sha256,
        schedule_source=request.schedule_source,
        schedule_source_release=request.schedule_source_release,
    )
    if schedule_identity != request.plan22_schedule_identity_sha256:
        raise ValueError("Plan22 schedule bridge mismatch")
    request_identity = adjusted_daily_request_identity_v3(
        cohort_identity_sha256=request.canonical_cohort_identity_sha256,
        decision_cutoff=request.decision_cutoff,
        schedule_identity_sha256=request.plan22_schedule_identity_sha256,
        members=members,
    )
    if request_identity != request.plan22_request_identity_sha256:
        raise ValueError("Plan22 request bridge mismatch")
    return {
        "provider_id": "BHARATSTOCK",
        "decision_cutoff": request.decision_cutoff,
        "plan21_schedule": {
            "sessions": tuple(item.session for item in sessions),
            "decision_session_official_close_at": sessions[-1].close_at,
            "schedule_evidence_sha256": request.schedule_evidence_sha256,
            "schedule_source": request.schedule_source,
            "schedule_source_release": request.schedule_source_release,
            "schedule_identity_sha256": schedule_identity,
        },
        "instruments": tuple(
            {
                "isin": member.isin,
                "exchange": member.exchange,
                "instrument_type": member.instrument_type,
                "segment": member.segment,
                "effective_symbol": member.effective_symbol,
                "valid_from": member.valid_from,
                "valid_through": member.valid_through,
                "provider_symbol": member.provider_symbol,
                "mapping_version": member.mapping_version,
                "mapping_valid_from": member.mapping_valid_from,
                "mapping_valid_through": member.mapping_valid_through,
                "mapping_identity": member.mapping_identity,
            }
            for member in request.members
        ),
        "cohort_identity_sha256": request.canonical_cohort_identity_sha256,
        "request_identity_sha256": request_identity,
    }


def _sealed_v4_boundary() -> tuple[object, ...]:  # noqa: C901
    """Create the module-private authority for Plan-27 V4 retention."""
    minted_seals: set[object] = set()

    @dataclass(frozen=True, slots=True)
    class _CandidateBinding:
        candidate: _CurrentSamePassMarketContextCandidateV4
        context: PrivateCurrentSamePassMarketContextObjectV4

    @dataclass(frozen=True, slots=True)
    class _ArchiveBinding:
        candidate_seal: object
        candidate: _CurrentSamePassMarketContextCandidateV4
        retained_object_id: int
        trusted_clock: _TrustedClockV1
        root: Path
        root_identity: tuple[int, int]
        archive_directory: str
        context_name: str
        receipt_name: str
        marker_name: str
        context_filesystem_identity: _ArchiveMemberIdentity
        receipt_filesystem_identity: _ArchiveMemberIdentity
        marker_filesystem_identity: _ArchiveMemberIdentity
        context_bytes: bytes
        receipt_bytes: bytes
        marker_bytes: bytes
        context_sha256: str
        receipt_sha256: str
        marker_sha256: str
        receipt_identity: str
        marker_identity: str
        archive_known_at: datetime
        retained_identity: str

    candidate_bindings: dict[object, _CandidateBinding] = {}
    archive_bindings: dict[object, _ArchiveBinding] = {}

    @dataclass(frozen=True, slots=True, init=False, repr=False, eq=False)
    class CandidateSeal:
        def __init__(self, *_: object, **__: object) -> None:
            raise TypeError("same-pass candidate seals are closure-minted only")

    @dataclass(frozen=True, slots=True, init=False, repr=False, eq=False)
    class ArchiveSeal:
        def __init__(self, *_: object, **__: object) -> None:
            raise TypeError("same-pass archive seals are closure-minted only")

    def minted(seal: object) -> bool:
        return any(item is seal for item in minted_seals)

    def mint_candidate(
        context: PrivateCurrentSamePassMarketContextObjectV4,
    ) -> _CurrentSamePassMarketContextCandidateV4:
        result = object.__new__(_CurrentSamePassMarketContextCandidateV4)
        local_seal = object.__new__(CandidateSeal)
        minted_seals.add(local_seal)
        candidate_bindings[local_seal] = _CandidateBinding(result, context)
        object.__setattr__(result, "context_object", context)
        object.__setattr__(
            result,
            "candidate_identity_sha256",
            _identity(
                {
                    "context_identity_sha256": context.context_identity_sha256,
                    "context_object_sha256": context.context_object_sha256,
                }
            ),
        )
        object.__setattr__(result, "_seal", local_seal)
        return result

    def candidate_exactness_failure(
        request: CurrentSamePassMarketRegimeRequestV4,
        candidate: object,
    ) -> str | None:
        seal = getattr(candidate, "_seal", None)
        binding = candidate_bindings.get(seal)
        if type(candidate) is not _CurrentSamePassMarketContextCandidateV4:
            return "CANDIDATE_TYPE_MISMATCH"
        if type(seal) is not CandidateSeal:
            return "CANDIDATE_SEAL_TYPE_MISMATCH"
        if not minted(seal):
            return "CANDIDATE_SEAL_UNMINTED"
        if binding is None:
            return "CANDIDATE_BINDING_MISSING"
        if binding.candidate is not candidate:
            return "CANDIDATE_BINDING_MISMATCH"
        if binding.context is not candidate.context_object:
            return "CONTEXT_BINDING_MISMATCH"
        return _candidate_structure_exactness_failure(request, candidate)

    def candidate_is_exact(
        request: CurrentSamePassMarketRegimeRequestV4,
        candidate: object,
    ) -> bool:
        return candidate_exactness_failure(request, candidate) is None

    def _persisted_archive_binding(
        candidate: _CurrentSamePassMarketContextCandidateV4,
        value: RetainedCurrentSamePassMarketContextV4,
        lease: StorageRootLease,
        root: Path,
    ) -> (
        tuple[
            tuple[int, int],
            str,
            str,
            str,
            str,
            _ArchiveMemberIdentity,
            _ArchiveMemberIdentity,
            _ArchiveMemberIdentity,
            bytes,
            bytes,
            bytes,
        ]
        | None
    ):
        context = candidate.context_object
        context_raw = context.canonical_json_bytes()
        stem = context.context_identity_sha256
        directory_name = ".current-same-pass-market-regime-v4"
        context_name = f"context-{stem}.json"
        receipt_name = f"retained-{stem}.json"
        marker_name = f"completion-{stem}.json"
        try:
            with lease.read_operation(root) as operation:
                operation.ensure_live()
                root_info = os.fstat(operation.descriptor)
                directory = os.open(
                    directory_name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=operation.descriptor,
                )
                try:
                    if not _archive_directory_bound(operation.descriptor, directory):
                        return None
                    persisted_context = _read_exact_member(
                        directory, context_name, _MAX_CONTEXT_BYTES
                    )
                    persisted_receipt = _read_exact_member(
                        directory, receipt_name, _MAX_RECEIPT_BYTES
                    )
                    persisted_marker = _read_exact_member(
                        directory, marker_name, _MAX_MARKER_BYTES
                    )
                    operation.ensure_live()
                    if (
                        persisted_context is None
                        or persisted_receipt is None
                        or persisted_marker is None
                        or persisted_context[0] != context_raw
                    ):
                        return None
                    return (
                        (root_info.st_dev, root_info.st_ino),
                        directory_name,
                        context_name,
                        receipt_name,
                        marker_name,
                        persisted_context[1],
                        persisted_receipt[1],
                        persisted_marker[1],
                        persisted_context[0],
                        persisted_receipt[0],
                        persisted_marker[0],
                    )
                finally:
                    os.close(directory)
        except (OSError, RuntimeError, TypeError, ValueError):
            return None

    def retained_from_legacy(
        request: CurrentSamePassMarketRegimeRequestV4,
        candidate: _CurrentSamePassMarketContextCandidateV4,
        value: RetainedCurrentSamePassMarketContextV4,
        lease: StorageRootLease,
        root: Path,
        trusted_clock: _TrustedClockV1,
    ) -> RetainedCurrentSamePassMarketContextV4 | CurrentSamePassArchiveFailureV1:
        candidate_binding = candidate_bindings.get(candidate._seal)
        persisted = _persisted_archive_binding(candidate, value, lease, root)
        if (
            not candidate_is_exact(request, candidate)
            or candidate_binding is None
            or persisted is None
        ):
            return _failure(request, getattr(value, "context_identity_sha256", None))
        (
            root_identity,
            archive_directory,
            context_name,
            receipt_name,
            marker_name,
            context_filesystem_identity,
            receipt_filesystem_identity,
            marker_filesystem_identity,
            context_bytes,
            receipt_bytes,
            marker_bytes,
        ) = persisted
        try:
            receipt, marker = _parse_context_archive_records(
                candidate_binding.context,
                receipt_bytes,
                marker_bytes,
                request.decision_cutoff,
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return _failure(request, getattr(value, "context_identity_sha256", None))
        trusted_now = trusted_clock.now()
        if (
            not _utc(trusted_now)
            or receipt.archive_known_at > request.decision_cutoff
            or receipt.archive_known_at > trusted_now
        ):
            return _failure(request, getattr(value, "context_identity_sha256", None))
        context = candidate_binding.context
        retained_core = {
            "evidence_state": "RETAINED",
            "context_identity_sha256": context.context_identity_sha256,
            "context_object_sha256": context.context_object_sha256,
            "context_receipt_identity_sha256": receipt.context_receipt_identity_sha256,
            "completion_marker_identity_sha256": marker.completion_marker_identity_sha256,
            "archive_known_at": receipt.archive_known_at,
            "market_data_report": context.market_data_report,
            "market_regime_report": context.market_regime_report,
            "partial_current_session": context.raw_result.partial_current_session,
        }
        retained_identity = _identity(retained_core)
        if (
            not _legacy_validate_retained_current_same_pass_market_context_v4(
                value, context
            )
            or value.context_receipt_identity_sha256
            != receipt.context_receipt_identity_sha256
            or value.completion_marker_identity_sha256
            != marker.completion_marker_identity_sha256
            or value.archive_known_at != receipt.archive_known_at
            or value.retained_context_identity_sha256 != retained_identity
        ):
            return _failure(request, getattr(value, "context_identity_sha256", None))
        result = object.__new__(RetainedCurrentSamePassMarketContextV4)
        local_seal = object.__new__(ArchiveSeal)
        minted_seals.add(local_seal)
        archive_bindings[local_seal] = _ArchiveBinding(
            candidate._seal,
            candidate,
            id(result),
            trusted_clock,
            root,
            root_identity,
            archive_directory,
            context_name,
            receipt_name,
            marker_name,
            context_filesystem_identity,
            receipt_filesystem_identity,
            marker_filesystem_identity,
            context_bytes,
            receipt_bytes,
            marker_bytes,
            _sha(context_bytes),
            _sha(receipt_bytes),
            _sha(marker_bytes),
            receipt.context_receipt_identity_sha256,
            marker.completion_marker_identity_sha256,
            receipt.archive_known_at,
            retained_identity,
        )
        for name, item in {
            **retained_core,
            "retained_context_identity_sha256": retained_identity,
            "_archive_seal": local_seal,
        }.items():
            object.__setattr__(result, name, item)
        return result

    def validate(
        value: object,
        expected_candidate: object | None = None,
    ) -> bool:
        if type(value) is not RetainedCurrentSamePassMarketContextV4:
            return False
        seal = value._archive_seal
        binding = archive_bindings.get(seal)
        if (
            type(seal) is not ArchiveSeal
            or not minted(seal)
            or binding is None
            or binding.retained_object_id != id(value)
        ):
            return False
        candidate_binding = candidate_bindings.get(binding.candidate_seal)
        if candidate_binding is None:
            return False
        candidate = candidate_binding.candidate
        context = candidate_binding.context
        if not candidate_is_exact(context.request, candidate):
            return False
        if expected_candidate is not None and candidate is not expected_candidate:
            return False
        core = {
            "evidence_state": "RETAINED",
            "context_identity_sha256": context.context_identity_sha256,
            "context_object_sha256": context.context_object_sha256,
            "context_receipt_identity_sha256": binding.receipt_identity,
            "completion_marker_identity_sha256": binding.marker_identity,
            "archive_known_at": value.archive_known_at,
            "market_data_report": context.market_data_report,
            "market_regime_report": context.market_regime_report,
            "partial_current_session": context.raw_result.partial_current_session,
        }
        return (
            value.evidence_state == "RETAINED"
            and value.context_identity_sha256 == context.context_identity_sha256
            and value.context_object_sha256 == context.context_object_sha256
            and value.context_receipt_identity_sha256 == binding.receipt_identity
            and value.archive_known_at == binding.archive_known_at
            and value.completion_marker_identity_sha256 == binding.marker_identity
            and value.market_data_report == context.market_data_report
            and value.market_regime_report == context.market_regime_report
            and value.partial_current_session
            == context.raw_result.partial_current_session
            and value.retained_context_identity_sha256 == binding.retained_identity
            and value.retained_context_identity_sha256 == _identity(core)
        )

    def adopt(
        request: CurrentSamePassMarketRegimeRequestV4,
        value: object,
        current_candidate: object,
        lease: StorageRootLease,
        trusted_clock: _TrustedClockV1,
    ) -> bool:
        """Re-open the sealed logical commit under the caller's current lease."""
        if (
            type(lease) is not StorageRootLease
            or not validate(value, current_candidate)
            or not candidate_is_exact(request, current_candidate)
        ):
            return False
        binding = archive_bindings.get(value._archive_seal)
        if (
            binding is None
            or binding.candidate is not current_candidate
            or binding.trusted_clock is not trusted_clock
        ):
            return False
        try:
            with lease.read_operation(binding.root) as operation:
                operation.ensure_live()
                root_info = os.fstat(operation.descriptor)
                if (root_info.st_dev, root_info.st_ino) != binding.root_identity:
                    return False
                directory = os.open(
                    binding.archive_directory,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=operation.descriptor,
                )
                try:
                    if not _archive_directory_bound(operation.descriptor, directory):
                        return False
                    context = _read_exact_member(
                        directory, binding.context_name, _MAX_CONTEXT_BYTES
                    )
                    receipt = _read_exact_member(
                        directory, binding.receipt_name, _MAX_RECEIPT_BYTES
                    )
                    marker = _read_exact_member(
                        directory, binding.marker_name, _MAX_MARKER_BYTES
                    )
                    operation.ensure_live()
                    if (
                        context is None
                        or receipt is None
                        or marker is None
                        or context[1] != binding.context_filesystem_identity
                        or receipt[1] != binding.receipt_filesystem_identity
                        or marker[1] != binding.marker_filesystem_identity
                    ):
                        return False
                    receipt_record, _marker_record = _parse_context_archive_records(
                        binding.candidate.context_object,
                        receipt[0],
                        marker[0],
                        binding.candidate.context_object.request.decision_cutoff,
                    )
                    trusted_now = trusted_clock.now()
                    if (
                        not _utc(trusted_now)
                        or receipt_record.archive_known_at > trusted_now
                    ):
                        return False
                    return (
                        context[0] == binding.context_bytes
                        and receipt[0] == binding.receipt_bytes
                        and marker[0] == binding.marker_bytes
                        and _sha(context[0]) == binding.context_sha256
                        and _sha(receipt[0]) == binding.receipt_sha256
                        and _sha(marker[0]) == binding.marker_sha256
                    )
                finally:
                    os.close(directory)
        except (OSError, RuntimeError, TypeError, ValueError):
            return False

    def industry_projection(
        value: object,
    ) -> tuple[
        CurrentSamePassMarketRegimeReportV4,
        _CurrentSamePassMemberDirectionCandidateV4 | None,
    ]:
        if not validate(value):
            raise ValueError("invalid retained same-pass market context")
        binding = archive_bindings[value._archive_seal]
        context = candidate_bindings[binding.candidate_seal].context
        return context.market_regime_report, context.direction_candidate

    def packet_projection(value: object, request: object) -> dict[str, object] | None:
        """Return only packet-required identities and times after closure validation."""
        if not validate(value):
            return None
        binding = archive_bindings[value._archive_seal]
        context = candidate_bindings[binding.candidate_seal].context
        request_matches = (
            getattr(request, "decision_cutoff", None) == context.request.decision_cutoff
            and getattr(request, "cohort_selected_at", None)
            == context.request.cohort_selected_at
            and getattr(request, "canonical_cohort_identity_sha256", None)
            == context.request.canonical_cohort_identity_sha256
            and getattr(request, "plan21_cohort_identity_sha256", None)
            == context.request.plan21_cohort_identity_sha256
            and getattr(request, "members", None) == context.request.members
        )
        ledger = context.component_ledger
        return {
            "direction_candidate_identity_sha256": (
                context.direction_candidate.direction_candidate_identity_sha256
                if context.direction_candidate is not None
                else None
            ),
            "raw_grid_identity_sha256": (
                context.raw_result.raw_grid.raw_grid_identity_sha256
                if context.raw_result.raw_grid is not None
                else None
            ),
            "raw_result_identity_sha256": context.raw_result.raw_result_identity_sha256,
            "raw_runtime_code_identity_sha256": (
                context.raw_result.raw_grid.runtime_code_identity_sha256
                if context.raw_result.raw_grid is not None
                else current_same_pass_raw_daily_runtime_code_identity_v4()
            ),
            "raw_source_policy_identity_sha256": (
                context.raw_result.raw_grid.raw_source_policy_identity_sha256
                if context.raw_result.raw_grid is not None
                else None
            ),
            "raw_known_at": ledger[0].known_at,
            "regime_known_at": ledger[3].known_at,
            "adjusted_component_state": ledger[2].evidence_state,
            "adjusted_component_identity_sha256": ledger[2].primary_identity_sha256,
            "adjusted_component_reasons": ledger[2].reasons,
            "price_basis": PRICE_BASIS,
            "request_matches": request_matches,
        }

    def research_binding_projection(value: object) -> dict[str, object] | None:
        """Expose the minimum exact retained request/context proof for V5.

        This successor accessor does not alter V4 serialization.  Its authority
        comes from the closure-owned archive binding and therefore also works
        for retained contexts whose public market-data rows are unavailable.
        """
        if not validate(value):
            return None
        binding = archive_bindings[value._archive_seal]
        context = candidate_bindings[binding.candidate_seal].context
        request = context.request
        receipts = context.raw_result.mapping_receipts or ()
        return {
            "request_identity_sha256": request.request_identity_sha256,
            "canonical_cohort_identity_sha256": (
                request.canonical_cohort_identity_sha256
            ),
            "plan21_cohort_identity_sha256": request.plan21_cohort_identity_sha256,
            "cohort_selected_at": request.cohort_selected_at,
            "decision_cutoff": request.decision_cutoff,
            "schedule_identity_sha256": request.schedule_identity_sha256,
            "members": tuple(item.value() for item in request.members),
            "mapping_failure_reasons": context.raw_result.reasons,
            "mapping_receipts": tuple(
                {
                    "isin": receipt.member.isin,
                    "mapping_identity": receipt.member.mapping_identity,
                    "snapshot_source": receipt.snapshot_source,
                    "snapshot_schema_version": receipt.snapshot_schema_version,
                    "observation_sha256": receipt.observation_sha256,
                    "observation_date": receipt.observation_date,
                    "retrieved_at": receipt.retrieved_at,
                    "known_at": receipt.known_at,
                    "raw_mapping_projection_identity_sha256": (
                        receipt.raw_mapping_projection_identity_sha256
                    ),
                }
                for receipt in receipts
            ),
            "context_identity_sha256": context.context_identity_sha256,
            "context_object_sha256": context.context_object_sha256,
            "context_receipt_identity_sha256": (value.context_receipt_identity_sha256),
            "completion_marker_identity_sha256": (
                value.completion_marker_identity_sha256
            ),
            "retained_context_identity_sha256": (
                value.retained_context_identity_sha256
            ),
            "archive_known_at": value.archive_known_at,
            "raw_result_identity_sha256": (
                context.raw_result.raw_result_identity_sha256
            ),
            "market_data_report_identity_sha256": (
                context.market_data_report.report_identity_sha256
            ),
            "market_regime_report_identity_sha256": (
                context.market_regime_report.report_identity_sha256
            ),
            "market_regime_schema_identity_sha256": (
                context.market_regime_report.schema_identity_sha256
            ),
            "market_regime_calculation_identity_sha256": (
                context.market_regime_report.calculation_identity_sha256
            ),
            "market_regime_runtime_code_identity_sha256": (
                context.market_regime_report.runtime_code_identity_sha256
            ),
            "market_regime_evidence_state": (
                context.market_regime_report.evidence_state
            ),
            "market_regime_decision_session": (
                context.market_regime_report.decision_session
            ),
            "market_regime_comparison_session": (
                context.market_regime_report.comparison_session
            ),
            "market_regime_decision_cutoff": (
                context.market_regime_report.decision_cutoff
            ),
            "market_regime": context.market_regime_report.regime,
            "market_regime_advances": context.market_regime_report.advances,
            "market_regime_declines": context.market_regime_report.declines,
            "market_regime_unchanged": context.market_regime_report.unchanged,
            "market_regime_reasons": context.market_regime_report.reasons,
            "component_ledger": tuple(
                {
                    "position": row.position,
                    "component": row.component,
                    "contract_version": row.contract_version,
                    "evidence_state": row.evidence_state,
                    "schema_identity_sha256": row.schema_identity_sha256,
                    "runtime_code_identity_sha256": row.runtime_code_identity_sha256,
                    "primary_identity_sha256": row.primary_identity_sha256,
                    "known_at": row.known_at,
                    "reasons": row.reasons,
                    "ledger_row_identity_sha256": row.ledger_row_identity_sha256,
                }
                for row in context.component_ledger
            ),
        }

    file_archives: WeakKeyDictionary[
        object, _FileCurrentSamePassMarketContextArchiveV1
    ] = WeakKeyDictionary()

    class FileArchive:
        """Closure-sealed facade over the descriptor-relative archive effect."""

        __slots__ = ("__weakref__",)

        def __init__(
            self, root: object, *, clock: _TrustedClockV1 | None = None
        ) -> None:
            file_archives[self] = _FileCurrentSamePassMarketContextArchiveV1(
                root, clock=clock
            )

        def archive_exact(
            self,
            request: CurrentSamePassMarketRegimeRequestV4,
            candidate: _CurrentSamePassMarketContextCandidateV4,
            lease: StorageRootLease,
            *,
            trusted_clock: _TrustedClockV1 | None = None,
        ) -> RetainedCurrentSamePassMarketContextV4 | CurrentSamePassArchiveFailureV1:
            # The descriptor-relative archive reopens and stable-rereads every
            # artifact under this current lease before a closure record is minted.
            with _CONTEXT_ARCHIVE_TRANSACTION_LOCK:
                inner = file_archives.get(self) if type(self) is FileArchive else None
                if inner is None:
                    return _failure(request)
                archive_clock = trusted_clock or inner._clock
                value = inner.archive_exact(
                    request,
                    candidate,
                    lease,
                    trusted_clock=archive_clock,
                )
                if type(value) is CurrentSamePassArchiveFailureV1:
                    return value
                return retained_from_legacy(
                    request,
                    candidate,
                    value,
                    lease,
                    inner._root,
                    archive_clock,
                )

    def build(
        request: CurrentSamePassMarketRegimeRequestV4,
        raw: PrivateCurrentSamePassRawDailyResultV1,
        screen: object,
        adjusted: CurrentSamePassAdjustedCompositionResultV1,
        archive: CurrentSamePassMarketContextArchivePortV1,
        lease: StorageRootLease,
        *,
        trusted_clock: _TrustedClockV1 | None = None,
    ) -> RetainedCurrentSamePassMarketContextV4 | CurrentSamePassArchiveFailureV1:
        if (
            type(request) is not CurrentSamePassMarketRegimeRequestV4
            or type(raw) is not PrivateCurrentSamePassRawDailyResultV1
            or type(lease) is not StorageRootLease
        ):
            raise TypeError("invalid Plan27 composition")
        archive_clock = trusted_clock or _SystemClockV1()
        candidate = mint_candidate(_context_object(request, raw, screen, adjusted))
        result = archive.archive_exact(
            request,
            candidate,
            lease,
            trusted_clock=archive_clock,
        )
        if type(result) is RetainedCurrentSamePassMarketContextV4:
            if not adopt(request, result, candidate, lease, archive_clock):
                raise ValueError("archive returned an unsealed same-pass context")
            return result
        if type(result) is CurrentSamePassArchiveFailureV1:
            if not _archive_failure_is_exact(
                request, candidate.context_object.context_identity_sha256, result
            ):
                raise ValueError("invalid same-pass archive failure")
            return result
        raise TypeError("invalid archive result")

    return (
        FileArchive,
        build,
        candidate_is_exact,
        candidate_exactness_failure,
        validate,
        industry_projection,
        packet_projection,
        research_binding_projection,
    )


(
    FileCurrentSamePassMarketContextArchiveV1,
    build_and_retain_current_supplied_cohort_market_regime_v4,
    _candidate_is_exact,
    _candidate_exactness_failure,
    validate_retained_current_same_pass_market_context_v4,
    _industry_projection_from_retained_context_v4,
    _packet_projection_from_retained_context_v4,
    _research_binding_projection_from_retained_context_v4,
) = _sealed_v4_boundary()


class _TrustedClockV1(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class _SystemClockV1:
    def now(self) -> datetime:
        return datetime.now(UTC)


def acquire_build_and_retain_current_supplied_cohort_market_regime_v4(
    request: CurrentSamePassMarketRegimeRequestV4,
    schedule_store: object,
    raw_daily: CurrentSamePassRawDailyPortV1,
    corporate_action_resolver: object,
    adjusted_provider: BharatStockClient,
    archive: CurrentSamePassMarketContextArchivePortV1,
    lease: StorageRootLease,
    *,
    clock: _TrustedClockV1 | None = None,
) -> (
    RetainedCurrentSamePassMarketContextV4
    | CurrentSamePassArchiveFailureV1
    | CurrentSamePassPreflightFailureV1
):
    trusted_clock = clock or _SystemClockV1()
    invocation_started_at = trusted_clock.now()
    if (
        not _utc(invocation_started_at)
        or request.decision_cutoff < invocation_started_at + timedelta(seconds=60)
        or request.decision_cutoff > invocation_started_at + timedelta(minutes=30)
    ):
        raise ValueError("decision cutoff outside invocation lead window")
    acquisition_effect_deadline = request.decision_cutoff - timedelta(seconds=30)
    sessions = _resolve_sessions(schedule_store, request, lease)
    if type(sessions) is CurrentSamePassPreflightFailureV1:
        return sessions
    schedule = _resolve_schedule(schedule_store, request, lease)
    try:
        raw = raw_daily.acquire_exact(
            request,
            sessions,
            lease,
            invocation_started_at=invocation_started_at,
            acquisition_effect_deadline=acquisition_effect_deadline,
            official_active_session=_active_official_session(
                schedule, request.decision_cutoff
            ),
            trusted_clock=trusted_clock,
        )
    except CurrentSamePassAcquisitionOverrunV1:
        return _failure(request)
    if type(raw) is not PrivateCurrentSamePassRawDailyResultV1:
        raise TypeError("invalid raw result")
    if not _raw_result_is_authoritative(raw, request, sessions):
        raise ValueError("raw result is not bound to authoritative sessions")
    resolver = getattr(corporate_action_resolver, "resolve_exact", None)
    if not callable(resolver):
        raise TypeError("Plan21 resolver unavailable")
    screen = publish_current_corporate_action_screen_v1(
        resolver(_plan21_input(request, raw), lease)
    )
    if raw.evidence_state == "OBSERVED" and _screen_valid(screen, request, raw):
        adjusted_started_at = trusted_clock.now()
        if (
            not _utc(adjusted_started_at)
            or adjusted_started_at >= acquisition_effect_deadline
        ):
            return _failure(request)
        result = acquire_adjusted_daily_close_v3(
            _plan22_bridge(request, sessions), provider=adjusted_provider
        )
        adjusted_returned_at = trusted_clock.now()
        if (
            not _utc(adjusted_returned_at)
            or adjusted_returned_at > acquisition_effect_deadline
        ):
            return _failure(request)
        adjusted = _adjusted_composition(result, request, sessions)
    else:
        adjusted = _upstream_insufficient_adjusted_composition(request)
    return cast(Any, build_and_retain_current_supplied_cohort_market_regime_v4)(
        request,
        raw,
        screen,
        adjusted,
        archive,
        lease,
        trusted_clock=trusted_clock,
    )
