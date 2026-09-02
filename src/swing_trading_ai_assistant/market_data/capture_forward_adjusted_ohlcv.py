"""Capture-forward owner-private adjusted daily OHLCV evidence for Plan 29."""

from __future__ import annotations

import errno
import hashlib
import importlib.metadata
import json
import os
import re
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from numbers import Real
from pathlib import Path
from types import ModuleType
from typing import Final, NoReturn, Protocol, cast

import pandas as pd

# pyright: ignore[reportMissingImports]
from swing_trading_ai_assistant.historical_evaluation.capability_validation import (
    CONTRACT_VERSION_V1 as PLAN29_CONTRACT_VERSION_V1,
)
from swing_trading_ai_assistant.historical_evaluation.capability_validation import (
    AvailabilityStateV1,
    CanonicalEquityV1,
    HistoricalAvailabilityEntryV1,
    HistoricalBarKnowledgeV1,
    HistoricalComparabilityProvenanceV1,
    HistoricalDecisionPointV1,
    HistoricalEvidenceFeatureV1,
    HistoricalEvidenceRevisionV1,
    HistoricalStudyDeclarationV1,
    HistoricalStudyProfileV1,
    HistoricalStudyRegionV1,
    HistoricalValidationReportV1,
    HistoricalValidationRequestV1,
    capability_validation_current_identities_v1,
    evaluate_capability_aware_historical_validation_v1,
)
from swing_trading_ai_assistant.market_data import storage_root_lease as lease_core
from swing_trading_ai_assistant.market_data.capture_forward_adjusted_ohlcv_runtime_identity_manifest import (
    CAPTURE_FORWARD_ADJUSTED_OHLCV_RUNTIME_SOURCE_SHA256_V1,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    read_runtime_source,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    MAX_SCHEDULE_BYTES,
    ExpectedSessionSchedule,
    parse_canonical_schedule_bytes,
    schedule_covers_full_calendar_range,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
    StorageRootLeaseOperation,
)

_yfinance_modules: list[ModuleType] = []

CONTRACT_VERSION_V1: Final = "capture-forward-adjusted-ohlcv@v1"
REVISION_CONTRACT_VERSION_V1: Final = "capture-forward-adjusted-ohlcv-revision@v1"
EVIDENCE_REVISION_CONTRACT_VERSION_V1: Final = (
    "capture-forward-adjusted-ohlcv-plan29-evidence@v1"
)
SOURCE_PROFILE_V1: Final = "YFINANCE_CAPTURE_FORWARD_ADJUSTED_OHLCV"
ADJUSTED_PRICE_BASIS_V1: Final = "ADJUSTED_YFINANCE_RATIO"
VOLUME_BASIS_V1: Final = "SOURCE_REPORTED_UNADJUSTED"
PERMITTED_USE_V1: Final = "OWNER_PRIVATE_RESEARCH"
EXPECTED_PROVIDER_SOURCE_V1: Final = "yfinance==1.6.0"
COMPOSED_SCHEDULE_SOURCE_V1: Final = "nse-upstox-composed-calendar"
LIMITATION_V1: Final = "FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION"
SOURCE_LIMITATION_V1: Final = (
    "UNOFFICIAL_PERSONAL_RESEARCH_CAPTURE_FORWARD_PROVIDER_REVISIONS_POSSIBLE"
)
MIN_MEMBERS_V1: Final = 1
MAX_MEMBERS_V1: Final = 50
MIN_WINDOW_SESSIONS_V1: Final = 4
MAX_WINDOW_SESSIONS_V1: Final = 366
MAX_REVISION_BYTES_V1: Final = 32 * 1024 * 1024

MAX_REQUEST_BYTES_V1: Final = 4 * 1024 * 1024
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ISIN = re.compile(r"[A-Z0-9]{12}\Z")
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.&_-]{0,31}\Z")
_PROVIDER_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.&_-]{0,31}\.NS\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}\Z")
_REVISION_NAME = re.compile(r"[0-9a-f]{64}\.json\Z")
_COMPOSED_RELEASE = re.compile(r"composed-calendar@v1=[0-9a-f]{64}\Z")


class _CaptureForwardAdjustedOhlcvProviderV1(Protocol):
    def download(self, **kwargs: object) -> object: ...


class _PandasSeries(Protocol):
    def tolist(self) -> list[object]: ...


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_line(value: object) -> bytes:
    return _canonical(value) + b"\n"


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _valid_digest(value: object) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _valid_token(value: object) -> bool:
    return type(value) is str and _TOKEN.fullmatch(value) is not None


def _valid_absolute_path(value: object) -> bool:
    return isinstance(value, Path) and value.is_absolute()


def _utc(value: datetime, name: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None:
        raise ValueError(f"{name} must be an aware instant")
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{name} must be an aware instant") from error


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class MappingEvidenceInvalid(ValueError):
    """Canonical provider mapping evidence is invalid."""


class ScheduleEvidenceInvalid(ValueError):
    """Composed schedule evidence is invalid."""


def mapping_identity_v1(
    *,
    isin: str,
    exchange: str,
    effective_symbol: str,
    provider_symbol: str,
    mapping_version: str,
    mapping_valid_from: date,
    mapping_valid_through: date | None,
) -> str:
    """Return the exact yfinance mapping identity used by capture requests."""

    return _sha(
        _canonical(
            {
                "effective_symbol": effective_symbol,
                "exchange": exchange,
                "isin": isin,
                "mapping_valid_from": mapping_valid_from.isoformat(),
                "mapping_valid_through": (
                    None
                    if mapping_valid_through is None
                    else mapping_valid_through.isoformat()
                ),
                "mapping_version": mapping_version,
                "provider": "YAHOO_FINANCE",
                "provider_symbol": provider_symbol,
            }
        )
    )


@dataclass(frozen=True, slots=True, order=True)
class CaptureForwardAdjustedOhlcvMemberV1:
    isin: str
    exchange: str
    effective_symbol: str
    symbol_history_identity_sha256: str
    provider_symbol: str
    mapping_version: str
    mapping_valid_from: date
    mapping_valid_through: date | None
    mapping_identity_sha256: str

    def __post_init__(self) -> None:
        valid = (
            _ISIN.fullmatch(self.isin) is not None
            and self.exchange == "NSE"
            and _SYMBOL.fullmatch(self.effective_symbol) is not None
            and _PROVIDER_SYMBOL.fullmatch(self.provider_symbol) is not None
            and _valid_digest(self.symbol_history_identity_sha256)
            and _valid_token(self.mapping_version)
            and type(self.mapping_valid_from) is date
            and (
                self.mapping_valid_through is None
                or (
                    type(self.mapping_valid_through) is date
                    and self.mapping_valid_through >= self.mapping_valid_from
                )
            )
        )
        expected = mapping_identity_v1(
            isin=self.isin,
            exchange=self.exchange,
            effective_symbol=self.effective_symbol,
            provider_symbol=self.provider_symbol,
            mapping_version=self.mapping_version,
            mapping_valid_from=self.mapping_valid_from,
            mapping_valid_through=self.mapping_valid_through,
        )
        if not valid or self.mapping_identity_sha256 != expected:
            raise ValueError("capture member is invalid")

    def canonical_value(self) -> dict[str, object]:
        return {
            "effective_symbol": self.effective_symbol,
            "exchange": self.exchange,
            "isin": self.isin,
            "mapping_identity_sha256": self.mapping_identity_sha256,
            "mapping_valid_from": self.mapping_valid_from.isoformat(),
            "mapping_valid_through": (
                None
                if self.mapping_valid_through is None
                else self.mapping_valid_through.isoformat()
            ),
            "mapping_version": self.mapping_version,
            "provider_symbol": self.provider_symbol,
            "symbol_history_identity_sha256": self.symbol_history_identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class CaptureForwardAdjustedOhlcvScheduleV1:
    sessions: tuple[date, ...]
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    decision_session_official_close_at: datetime
    schedule_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.sessions) is not tuple
            or any(type(session) is not date for session in self.sessions)
            or not MIN_WINDOW_SESSIONS_V1
            <= len(self.sessions)
            <= MAX_WINDOW_SESSIONS_V1
            or self.sessions != tuple(sorted(self.sessions))
            or len(set(self.sessions)) != len(self.sessions)
            or not _valid_digest(self.schedule_evidence_sha256)
            or self.schedule_source != COMPOSED_SCHEDULE_SOURCE_V1
            or _COMPOSED_RELEASE.fullmatch(self.schedule_source_release) is None
        ):
            raise ValueError("capture schedule is invalid")
        official_close = _utc(
            self.decision_session_official_close_at,
            "decision_session_official_close_at",
        )
        object.__setattr__(self, "decision_session_official_close_at", official_close)
        object.__setattr__(
            self,
            "schedule_identity_sha256",
            _sha(_canonical(self.canonical_value(include_identity=False))),
        )

    def canonical_value(self, *, include_identity: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "decision_session_official_close_at": _timestamp(
                self.decision_session_official_close_at
            ),
            "schedule_evidence_sha256": self.schedule_evidence_sha256,
            "schedule_source": self.schedule_source,
            "schedule_source_release": self.schedule_source_release,
            "sessions": [session.isoformat() for session in self.sessions],
        }
        if include_identity:
            value["schedule_identity_sha256"] = self.schedule_identity_sha256
        return value


def _capture_schema_preimage_v1() -> dict[str, object]:
    return {
        "bounds": {
            "members": [MIN_MEMBERS_V1, MAX_MEMBERS_V1],
            "request_bytes": MAX_REQUEST_BYTES_V1,
            "revision_bytes": MAX_REVISION_BYTES_V1,
            "window_sessions": [MIN_WINDOW_SESSIONS_V1, MAX_WINDOW_SESSIONS_V1],
        },
        "canonical_json": {
            "allow_nan": False,
            "encoding": "utf-8",
            "key_order": "lexicographic",
            "record_terminator": "LF",
            "separators": [",", ":"],
            "timestamp": "UTC_RFC3339_MICROSECONDS_Z",
        },
        "lexical_types": {
            "decimal_string": "finite_base10_decimal_string",
            "integer": "json_integer_not_boolean",
            "isin": _ISIN.pattern,
            "local_date": "YYYY-MM-DD",
            "nse_symbol": _SYMBOL.pattern,
            "provider_symbol": _PROVIDER_SYMBOL.pattern,
            "safe_token": _TOKEN.pattern,
            "schedule_source_release": _COMPOSED_RELEASE.pattern,
            "sha256": _DIGEST.pattern,
            "utc_instant": "timezone_aware_UTC_RFC3339_MICROSECONDS_Z",
        },
        "objects": {
            "AdjustedOhlcvBarV1": {
                "constraints": [
                    "finite_positive_OHLC",
                    "low_lte_min_open_close_lte_max_open_close_lte_high",
                    "volume_int_gte_0",
                ],
                "fields": [
                    ["close", "decimal_string", False],
                    ["high", "decimal_string", False],
                    ["low", "decimal_string", False],
                    ["member_exchange", "literal:NSE", False],
                    ["member_isin", "isin", False],
                    ["open", "decimal_string", False],
                    ["session", "local_date", False],
                    ["volume", "integer", False],
                ],
            },
            "CaptureForwardAdjustedOhlcvMemberV1": {
                "constraints": [
                    "mapping_identity_sha256_recomputed",
                    "mapping_interval_ordered",
                ],
                "fields": [
                    ["effective_symbol", "nse_symbol", False],
                    ["exchange", "literal:NSE", False],
                    ["isin", "isin", False],
                    ["mapping_identity_sha256", "sha256", False],
                    ["mapping_valid_from", "local_date", False],
                    ["mapping_valid_through", "local_date", True],
                    ["mapping_version", "safe_token", False],
                    ["provider_symbol", "provider_symbol", False],
                    ["symbol_history_identity_sha256", "sha256", False],
                ],
            },
            "CaptureForwardAdjustedOhlcvRequestV1": {
                "constraints": [
                    "canonical_sorted_unique_cohort_1_to_50",
                    "unique_provider_symbol",
                    "mapping_covers_complete_session_window",
                    "official_close_lte_cutoff_lte_evaluated_at",
                    "current_schema_runtime_configuration_required",
                    "cohort_and_request_identities_recomputed",
                ],
                "fields": [
                    ["cohort", "CaptureForwardAdjustedOhlcvMemberV1[]", False],
                    ["cohort_identity_sha256", "sha256", False],
                    ["configuration_identity_sha256", "sha256", False],
                    ["contract_version", f"literal:{CONTRACT_VERSION_V1}", False],
                    ["decision_cutoff", "utc_instant", False],
                    ["decision_session", "local_date", False],
                    ["evaluated_at", "utc_instant", False],
                    ["parent_revision_sha256", "sha256", True],
                    ["request_identity_sha256", "sha256", False],
                    ["runtime_code_identity_sha256", "sha256", False],
                    ["schedule", "CaptureForwardAdjustedOhlcvScheduleV1", False],
                    ["schema_identity_sha256", "sha256", False],
                ],
            },
            "CaptureForwardAdjustedOhlcvScheduleV1": {
                "constraints": [
                    "canonical_strictly_increasing_sessions_4_to_366",
                    "decision_session_official_close_at_matches_last_session",
                    "schedule_identity_sha256_recomputed",
                ],
                "fields": [
                    ["decision_session_official_close_at", "utc_instant", False],
                    ["schedule_evidence_sha256", "sha256", False],
                    ["schedule_identity_sha256", "sha256", False],
                    [
                        "schedule_source",
                        f"literal:{COMPOSED_SCHEDULE_SOURCE_V1}",
                        False,
                    ],
                    [
                        "schedule_source_release",
                        "schedule_source_release",
                        False,
                    ],
                    ["sessions", "local_date[]", False],
                ],
            },
            "AdjustedOhlcvCaptureRevisionV1": {
                "constraints": [
                    "complete_canonical_cohort_cross_session_grid",
                    "decision_close_lte_retrieved_at_lte_cutoff",
                    "cohort_revision_and_source_identities_recomputed",
                    "exact_schema_configuration_and_compatible_writer_runtime",
                ],
                "fields": [
                    ["bars", "AdjustedOhlcvBarV1[]", False],
                    ["cohort", "CaptureForwardAdjustedOhlcvMemberV1[]", False],
                    ["cohort_identity_sha256", "sha256", False],
                    ["configuration_identity_sha256", "sha256", False],
                    [
                        "contract_version",
                        f"literal:{REVISION_CONTRACT_VERSION_V1}",
                        False,
                    ],
                    ["decision_cutoff", "utc_instant", False],
                    ["decision_session", "local_date", False],
                    ["limitation", f"literal:{SOURCE_LIMITATION_V1}", False],
                    ["parent_revision_sha256", "sha256", True],
                    ["permitted_use", f"literal:{PERMITTED_USE_V1}", False],
                    ["price_basis", f"literal:{ADJUSTED_PRICE_BASIS_V1}", False],
                    [
                        "provider_source",
                        f"literal:{EXPECTED_PROVIDER_SOURCE_V1}",
                        False,
                    ],
                    ["request_identity_sha256", "sha256", False],
                    ["retrieved_at", "utc_instant", False],
                    ["revision_sha256", "sha256", False],
                    ["runtime_code_identity_sha256", "sha256", False],
                    ["schedule", "CaptureForwardAdjustedOhlcvScheduleV1", False],
                    ["schema_identity_sha256", "sha256", False],
                    ["source_identity_sha256", "sha256", False],
                    ["source_profile", f"literal:{SOURCE_PROFILE_V1}", False],
                    ["volume_basis", f"literal:{VOLUME_BASIS_V1}", False],
                ],
            },
        },
        "schema_contract": "capture-forward-adjusted-ohlcv-schema@v1",
    }


_SCHEMA_IDENTITY_SHA256: Final = _sha(_canonical(_capture_schema_preimage_v1()))
_CONFIGURATION_IDENTITY_SHA256: Final = _sha(
    _canonical(
        {
            "bounds": {
                "max_members": MAX_MEMBERS_V1,
                "max_revision_bytes": MAX_REVISION_BYTES_V1,
                "max_request_bytes": MAX_REQUEST_BYTES_V1,
                "max_window_sessions": MAX_WINDOW_SESSIONS_V1,
                "min_members": MIN_MEMBERS_V1,
                "min_window_sessions": MIN_WINDOW_SESSIONS_V1,
            },
            "provider_call": {
                "actions": False,
                "auto_adjust": True,
                "back_adjust": False,
                "group_by": "ticker",
                "ignore_tz": False,
                "interval": "1d",
                "keepna": True,
                "multi_level_index": True,
                "prepost": False,
                "progress": False,
                "repair": False,
                "rounding": False,
                "threads": False,
                "timeout": 10,
            },
        }
    )
)


def _read_manifest_source(root: Path, relative: str) -> bytes:
    if relative == "src/swing_trading_ai_assistant/__init__.py":
        return read_runtime_source(
            root.parent,
            "src/swing_trading_ai_assistant/swing_trading_ai_assistant/__init__.py",
        )
    return read_runtime_source(root, relative)


def _capture_source_identity_v1(configuration_identity_sha256: str) -> str:
    return _sha(
        _canonical(
            {
                "adapter": "YfinanceCaptureForwardAdjustedOhlcvAdapterV1",
                "configuration_identity_sha256": configuration_identity_sha256,
                "provider_source": EXPECTED_PROVIDER_SOURCE_V1,
                "source_profile": SOURCE_PROFILE_V1,
            }
        )
    )


def _runtime_code_identity() -> str:
    source = Path(__file__)
    if not source.is_absolute():
        raise RuntimeError("capture runtime identity invalid")
    root = source.parent.parent
    try:
        pairs: list[tuple[str, str]] = []
        for relative, expected in sorted(
            CAPTURE_FORWARD_ADJUSTED_OHLCV_RUNTIME_SOURCE_SHA256_V1.items()
        ):
            actual = _sha(_read_manifest_source(root, relative))
            if actual != expected:
                raise ValueError
            pairs.append((relative, actual))
        return _sha(_canonical(pairs))
    except (OSError, ValueError):
        raise RuntimeError("capture runtime identity invalid") from None


_COMPATIBLE_WRITER_RUNTIME_IDENTITIES_V1: Final = frozenset(
    {
        "d8b8feac77ce440d64a043185ff7fe17d5a9b38c74a0f04d181619cabd0f5ba0",
        "20f18fa4043742630d317448a1b0f8cc910535be16092f1e8b0669c81d0ebcb2",
        "720baa3615e1cf42efd0e73cec83f3cb524f48f8103cee6a34d71d23569b9e68",
        "84591e7c04f06227430d1511e0008e8136a0d2a83a30325c3ba9e2ef58e7e149",
        "c04ec0094424f0018a50f326f7ca4bac4d30c2e24f7e0d523b2e932f7c6db1e3",
        "7a620872d3b70684811912c46a5c1ef776383d18871ee63e5840a0a423ab020e",
    }
)


def _compatible_writer_runtime_identities_v1() -> frozenset[str]:
    return _COMPATIBLE_WRITER_RUNTIME_IDENTITIES_V1 | frozenset(
        {_runtime_code_identity()}
    )


def capture_forward_current_identities_v1() -> tuple[str, str, str]:
    """Return schema, loaded-source, and configuration identities."""

    return (
        _SCHEMA_IDENTITY_SHA256,
        _runtime_code_identity(),
        _CONFIGURATION_IDENTITY_SHA256,
    )


@dataclass(frozen=True, slots=True)
class CaptureForwardAdjustedOhlcvRequestV1:
    cohort: tuple[CaptureForwardAdjustedOhlcvMemberV1, ...]
    schedule: CaptureForwardAdjustedOhlcvScheduleV1
    decision_session: date
    decision_cutoff: datetime
    evaluated_at: datetime
    parent_revision_sha256: str | None
    schema_identity_sha256: str
    runtime_code_identity_sha256: str
    configuration_identity_sha256: str
    contract_version: str = CONTRACT_VERSION_V1
    cohort_identity_sha256: str = field(init=False)
    request_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            self.contract_version != CONTRACT_VERSION_V1
            or type(self.cohort) is not tuple
            or any(
                type(member) is not CaptureForwardAdjustedOhlcvMemberV1
                for member in self.cohort
            )
            or not MIN_MEMBERS_V1 <= len(self.cohort) <= MAX_MEMBERS_V1
            or self.cohort != tuple(sorted(self.cohort))
            or len({(member.isin, member.exchange) for member in self.cohort})
            != len(self.cohort)
            or len({member.provider_symbol for member in self.cohort})
            != len(self.cohort)
            or type(self.schedule) is not CaptureForwardAdjustedOhlcvScheduleV1
            or type(self.decision_session) is not date
            or self.decision_session != self.schedule.sessions[-1]
            or (
                self.parent_revision_sha256 is not None
                and not _valid_digest(self.parent_revision_sha256)
            )
        ):
            raise ValueError("capture request is invalid")
        cutoff = _utc(self.decision_cutoff, "decision_cutoff")
        evaluated = _utc(self.evaluated_at, "evaluated_at")
        if (
            self.schedule.decision_session_official_close_at > evaluated
            or cutoff < self.schedule.decision_session_official_close_at
            or cutoff > evaluated
            or any(
                self.schedule.sessions[0] < member.mapping_valid_from
                or (
                    member.mapping_valid_through is not None
                    and self.decision_session > member.mapping_valid_through
                )
                for member in self.cohort
            )
        ):
            raise ValueError("capture request is invalid")
        object.__setattr__(self, "decision_cutoff", cutoff)
        object.__setattr__(self, "evaluated_at", evaluated)
        current = capture_forward_current_identities_v1()
        if (
            self.schema_identity_sha256,
            self.runtime_code_identity_sha256,
            self.configuration_identity_sha256,
        ) != current:
            raise ValueError("capture request identity mismatch")
        cohort_identity = _sha(
            _canonical([member.canonical_value() for member in self.cohort])
        )
        object.__setattr__(self, "cohort_identity_sha256", cohort_identity)
        object.__setattr__(
            self,
            "request_identity_sha256",
            _sha(_canonical(self.canonical_value(include_request_identity=False))),
        )

    def canonical_value(
        self, *, include_request_identity: bool = True
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "cohort": [member.canonical_value() for member in self.cohort],
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "configuration_identity_sha256": self.configuration_identity_sha256,
            "contract_version": self.contract_version,
            "decision_cutoff": _timestamp(self.decision_cutoff),
            "decision_session": self.decision_session.isoformat(),
            "evaluated_at": _timestamp(self.evaluated_at),
            "parent_revision_sha256": self.parent_revision_sha256,
            "runtime_code_identity_sha256": self.runtime_code_identity_sha256,
            "schedule": self.schedule.canonical_value(),
            "schema_identity_sha256": self.schema_identity_sha256,
        }
        if include_request_identity:
            value["request_identity_sha256"] = self.request_identity_sha256
        return value

    def canonical_json_bytes(self) -> bytes:
        return _canonical_line(self.canonical_value())


def parse_capture_forward_request_v1(
    raw: bytes,
) -> CaptureForwardAdjustedOhlcvRequestV1:
    """Parse one exact canonical capture request without performing effects."""

    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST_BYTES_V1:
            raise ValueError
        value = json.loads(raw)
        if type(value) is not dict:
            raise ValueError
        row = cast(dict[str, object], value)
        try:
            cohort = tuple(
                _member_from_value(member)
                for member in cast(list[dict[str, object]], row["cohort"])
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            raise MappingEvidenceInvalid from None
        try:
            schedule = _schedule_from_value(cast(dict[str, object], row["schedule"]))
            decision_session = date.fromisoformat(cast(str, row["decision_session"]))
            decision_cutoff = _parse_instant(row["decision_cutoff"])
            evaluated_at = _parse_instant(row["evaluated_at"])
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ScheduleEvidenceInvalid from None
        if (
            len({(member.isin, member.exchange) for member in cohort}) != len(cohort)
            or len({member.provider_symbol for member in cohort}) != len(cohort)
            or any(
                schedule.sessions[0] < member.mapping_valid_from
                or (
                    member.mapping_valid_through is not None
                    and decision_session > member.mapping_valid_through
                )
                for member in cohort
            )
        ):
            raise MappingEvidenceInvalid
        if (
            decision_session != schedule.sessions[-1]
            or schedule.decision_session_official_close_at > evaluated_at
            or decision_cutoff < schedule.decision_session_official_close_at
            or decision_cutoff > evaluated_at
        ):
            raise ScheduleEvidenceInvalid
        request = CaptureForwardAdjustedOhlcvRequestV1(
            cohort=cohort,
            schedule=schedule,
            decision_session=decision_session,
            decision_cutoff=decision_cutoff,
            evaluated_at=evaluated_at,
            parent_revision_sha256=cast(str | None, row["parent_revision_sha256"]),
            schema_identity_sha256=cast(str, row["schema_identity_sha256"]),
            runtime_code_identity_sha256=cast(str, row["runtime_code_identity_sha256"]),
            configuration_identity_sha256=cast(
                str, row["configuration_identity_sha256"]
            ),
            contract_version=cast(str, row["contract_version"]),
        )
        if (
            row.get("cohort_identity_sha256") != request.cohort_identity_sha256
            or row.get("request_identity_sha256") != request.request_identity_sha256
            or raw != request.canonical_json_bytes()
        ):
            raise ValueError
        return request
    except (MappingEvidenceInvalid, ScheduleEvidenceInvalid):
        raise
    except (
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        RecursionError,
    ):
        raise ValueError("capture request JSON is invalid") from None


@dataclass(frozen=True, slots=True, order=True)
class AdjustedOhlcvBarV1:
    member_isin: str
    member_exchange: str
    session: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def __post_init__(self) -> None:
        values = (self.open, self.high, self.low, self.close)
        if (
            _ISIN.fullmatch(self.member_isin) is None
            or self.member_exchange != "NSE"
            or type(self.session) is not date
            or any(
                type(value) is not Decimal or not value.is_finite() for value in values
            )
            or any(value <= 0 for value in values)
            or not self.low
            <= min(self.open, self.close)
            <= max(self.open, self.close)
            <= self.high
            or type(self.volume) is not int
            or self.volume < 0
        ):
            raise ValueError("adjusted OHLCV bar is invalid")

    def canonical_value(self) -> dict[str, object]:
        return {
            "close": str(self.close),
            "high": str(self.high),
            "low": str(self.low),
            "member_exchange": self.member_exchange,
            "member_isin": self.member_isin,
            "open": str(self.open),
            "session": self.session.isoformat(),
            "volume": self.volume,
        }


@dataclass(frozen=True, slots=True)
class AdjustedOhlcvCaptureRevisionV1:
    request_identity_sha256: str
    cohort: tuple[CaptureForwardAdjustedOhlcvMemberV1, ...]
    cohort_identity_sha256: str
    schedule: CaptureForwardAdjustedOhlcvScheduleV1
    decision_session: date
    decision_cutoff: datetime
    retrieved_at: datetime
    provider_source: str
    source_identity_sha256: str
    parent_revision_sha256: str | None
    bars: tuple[AdjustedOhlcvBarV1, ...]
    schema_identity_sha256: str
    runtime_code_identity_sha256: str
    configuration_identity_sha256: str
    contract_version: str = REVISION_CONTRACT_VERSION_V1
    source_profile: str = SOURCE_PROFILE_V1
    price_basis: str = ADJUSTED_PRICE_BASIS_V1
    volume_basis: str = VOLUME_BASIS_V1
    permitted_use: str = PERMITTED_USE_V1
    limitation: str = SOURCE_LIMITATION_V1
    revision_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        retrieved = _utc(self.retrieved_at, "retrieved_at")
        cutoff = _utc(self.decision_cutoff, "decision_cutoff")
        expected_keys = tuple(
            (member.isin, member.exchange, session)
            for member in self.cohort
            for session in self.schedule.sessions
        )
        actual_keys = tuple(
            (bar.member_isin, bar.member_exchange, bar.session) for bar in self.bars
        )
        if (
            self.contract_version != REVISION_CONTRACT_VERSION_V1
            or self.source_profile != SOURCE_PROFILE_V1
            or self.price_basis != ADJUSTED_PRICE_BASIS_V1
            or self.volume_basis != VOLUME_BASIS_V1
            or self.permitted_use != PERMITTED_USE_V1
            or self.limitation != SOURCE_LIMITATION_V1
            or not _valid_digest(self.request_identity_sha256)
            or type(self.cohort) is not tuple
            or any(
                type(member) is not CaptureForwardAdjustedOhlcvMemberV1
                for member in self.cohort
            )
            or self.cohort != tuple(sorted(self.cohort))
            or self.cohort_identity_sha256
            != _sha(_canonical([member.canonical_value() for member in self.cohort]))
            or type(self.schedule) is not CaptureForwardAdjustedOhlcvScheduleV1
            or self.decision_session != self.schedule.sessions[-1]
            or self.schedule.decision_session_official_close_at > retrieved
            or retrieved > cutoff
            or self.provider_source != EXPECTED_PROVIDER_SOURCE_V1
            or self.schema_identity_sha256 != _SCHEMA_IDENTITY_SHA256
            or self.configuration_identity_sha256 != _CONFIGURATION_IDENTITY_SHA256
            or self.runtime_code_identity_sha256
            not in _compatible_writer_runtime_identities_v1()
            or self.source_identity_sha256
            != _capture_source_identity_v1(self.configuration_identity_sha256)
            or (
                self.parent_revision_sha256 is not None
                and not _valid_digest(self.parent_revision_sha256)
            )
            or type(self.bars) is not tuple
            or any(type(bar) is not AdjustedOhlcvBarV1 for bar in self.bars)
            or actual_keys != expected_keys
        ):
            raise ValueError("capture revision is invalid")
        object.__setattr__(self, "retrieved_at", retrieved)
        object.__setattr__(self, "decision_cutoff", cutoff)
        encoded = _canonical_line(self.canonical_value(include_revision_sha256=False))
        if len(encoded) > MAX_REVISION_BYTES_V1:
            raise ValueError("capture revision is invalid")
        object.__setattr__(self, "revision_sha256", _sha(encoded))

    def canonical_value(
        self, *, include_revision_sha256: bool = True
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "bars": [bar.canonical_value() for bar in self.bars],
            "cohort": [member.canonical_value() for member in self.cohort],
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "configuration_identity_sha256": self.configuration_identity_sha256,
            "contract_version": self.contract_version,
            "decision_cutoff": _timestamp(self.decision_cutoff),
            "decision_session": self.decision_session.isoformat(),
            "limitation": self.limitation,
            "parent_revision_sha256": self.parent_revision_sha256,
            "permitted_use": self.permitted_use,
            "price_basis": self.price_basis,
            "provider_source": self.provider_source,
            "request_identity_sha256": self.request_identity_sha256,
            "retrieved_at": _timestamp(self.retrieved_at),
            "runtime_code_identity_sha256": self.runtime_code_identity_sha256,
            "schedule": self.schedule.canonical_value(),
            "schema_identity_sha256": self.schema_identity_sha256,
            "source_identity_sha256": self.source_identity_sha256,
            "source_profile": self.source_profile,
            "volume_basis": self.volume_basis,
        }
        if include_revision_sha256:
            value["revision_sha256"] = self.revision_sha256
        return value

    def canonical_json_bytes(self) -> bytes:
        return _canonical_line(self.canonical_value())


@dataclass(frozen=True, slots=True)
class CaptureForwardAdjustedOhlcvSuccessV1:
    code: str
    revision: AdjustedOhlcvCaptureRevisionV1

    def __post_init__(self) -> None:
        if self.code not in {"CAPTURED", "REUSED"}:
            raise ValueError("capture success is invalid")


@dataclass(frozen=True, slots=True)
class CaptureForwardAdjustedOhlcvFailureV1:
    code: str
    reason: str

    def __post_init__(self) -> None:
        if self.code not in {
            "INSUFFICIENT_EVIDENCE",
            "STORE_UNAVAILABLE",
        } or not _valid_token(self.reason):
            raise ValueError("capture failure is invalid")


CaptureForwardAdjustedOhlcvResultV1 = (
    CaptureForwardAdjustedOhlcvSuccessV1 | CaptureForwardAdjustedOhlcvFailureV1
)


class _ImmutableEvidenceConflict(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CaptureForwardPlan29QualificationV1:
    evidence: HistoricalEvidenceRevisionV1
    request: HistoricalValidationRequestV1
    report: HistoricalValidationReportV1


class YfinanceCaptureForwardAdjustedOhlcvAdapterV1:
    """Normalize the sole admitted yfinance 1.6.0 DataFrame shape."""

    def download(self, **kwargs: object) -> object:  # noqa: C901
        expected_sessions = kwargs.pop("expected_sessions", None)
        normalize_plan33_order = kwargs.pop("_plan33_normalize_provider_order", False)
        tickers_value = kwargs.get("tickers")
        if (
            type(expected_sessions) is not tuple
            or type(tickers_value) is not tuple
            or type(normalize_plan33_order) is not bool
        ):
            return CaptureForwardAdjustedOhlcvFailureV1(
                "INSUFFICIENT_EVIDENCE", "FRAME_SCHEMA_INVALID"
            )
        tickers = cast(tuple[str, ...], tickers_value)
        try:
            _load_yfinance_module()
        except (ImportError, RuntimeError):
            return CaptureForwardAdjustedOhlcvFailureV1(
                "INSUFFICIENT_EVIDENCE", "PROVIDER_IDENTITY_MISMATCH"
            )
        response = _public_yfinance_download(**kwargs)
        if response is None:
            return CaptureForwardAdjustedOhlcvFailureV1(
                "INSUFFICIENT_EVIDENCE", "PROVIDER_EMPTY"
            )
        if not isinstance(response, pd.DataFrame):
            return CaptureForwardAdjustedOhlcvFailureV1(
                "INSUFFICIENT_EVIDENCE", "FRAME_SCHEMA_INVALID"
            )
        if response.empty:
            return CaptureForwardAdjustedOhlcvFailureV1(
                "INSUFFICIENT_EVIDENCE", "PROVIDER_EMPTY"
            )
        if (
            not isinstance(response.index, pd.DatetimeIndex)
            or response.index.tz is None
            or not response.index.is_unique
            or not isinstance(response.columns, pd.MultiIndex)
            or response.columns.nlevels != 2
            or tuple(response.columns.names) != ("Ticker", "Price")
            or not response.columns.is_unique
        ):
            return CaptureForwardAdjustedOhlcvFailureV1(
                "INSUFFICIENT_EVIDENCE", "FRAME_SCHEMA_INVALID"
            )
        fields = ("Open", "High", "Low", "Close", "Volume")
        expected_columns = tuple(
            (ticker, field) for ticker in tickers for field in fields
        )
        actual_columns = tuple(cast(Iterable[tuple[str, str]], response.columns))
        if set(actual_columns) != set(expected_columns):
            return CaptureForwardAdjustedOhlcvFailureV1(
                "INSUFFICIENT_EVIDENCE", "FRAME_COVERAGE_INCOMPLETE"
            )
        if actual_columns != expected_columns and not normalize_plan33_order:
            return CaptureForwardAdjustedOhlcvFailureV1(
                "INSUFFICIENT_EVIDENCE", "FRAME_SCHEMA_INVALID"
            )
        timezone = getattr(response.index.tz, "key", None) or getattr(
            response.index.tz, "zone", None
        )
        sessions = _session_dates(response.index)
        if sessions is None:
            return CaptureForwardAdjustedOhlcvFailureV1(
                "INSUFFICIENT_EVIDENCE", "FRAME_SCHEMA_INVALID"
            )
        ohlcv: dict[str, tuple[dict[str, object], ...]] = {}
        for ticker in tickers:
            columns: dict[str, list[object]] = {}
            for price_field in fields:
                values = cast(object, response[(ticker, price_field)])
                if not isinstance(values, pd.Series):
                    return CaptureForwardAdjustedOhlcvFailureV1(
                        "INSUFFICIENT_EVIDENCE", "FRAME_SCHEMA_INVALID"
                    )
                columns[price_field] = cast(_PandasSeries, values).tolist()
            ohlcv[ticker] = tuple(
                {
                    "open": columns["Open"][position],
                    "high": columns["High"][position],
                    "low": columns["Low"][position],
                    "close": columns["Close"][position],
                    "volume": columns["Volume"][position],
                }
                for position in range(len(response.index))
            )
        return {
            "timezone": timezone,
            "index": sessions,
            "ohlcv": ohlcv,
            "retrieved_at": datetime.now(UTC),
            "provider_source": EXPECTED_PROVIDER_SOURCE_V1,
        }


def _load_yfinance_module() -> ModuleType:
    if importlib.metadata.version("yfinance") != "1.6.0":
        raise RuntimeError("yfinance distribution identity mismatch")
    if not _yfinance_modules:
        _yfinance_modules.append(cast(ModuleType, __import__("yfinance")))
    module = _yfinance_modules[0]
    if module.__dict__.get("__version__") != "1.6.0":
        raise RuntimeError("yfinance module identity mismatch")
    return module


def _public_yfinance_download(**kwargs: object) -> object:
    download = _load_yfinance_module().__dict__.get("download")
    if not callable(download):
        raise RuntimeError("yfinance.download unavailable")
    return download(**kwargs)


def _session_dates(index: Iterable[object]) -> tuple[date, ...] | None:
    sessions: list[date] = []
    for value in index:
        as_date = getattr(value, "date", None)
        if not callable(as_date):
            return None
        result = as_date()
        if type(result) is not date:
            return None
        sessions.append(result)
    return tuple(sessions)


def _retained_schedule_matches_request(
    request: CaptureForwardAdjustedOhlcvRequestV1, schedule_root: Path
) -> bool:
    lease = _acquire_existing_private_lease(schedule_root)
    if lease is None:
        return False
    try:
        with lease.read_operation(schedule_root) as operation:
            calendar = _open_private_directory(
                operation,
                operation.descriptor,
                "calendar-schedules",
                create=False,
            )
            digests: _PrivateDirectory | None = None
            try:
                digests = _open_private_directory(
                    operation, calendar.descriptor, "sha256", create=False
                )
                raw = _read_exact_file(
                    operation,
                    digests,
                    f"{request.schedule.schedule_evidence_sha256}.json",
                    MAX_SCHEDULE_BYTES,
                    expected_mode=0o600,
                )
                schedule = parse_canonical_schedule_bytes(raw)
                operation.ensure_live()
                calendar.ensure_live()
                digests.ensure_live()
            finally:
                if digests is not None:
                    digests.close()
                calendar.close()
        if (
            type(schedule) is not ExpectedSessionSchedule
            or schedule_digest(schedule) != request.schedule.schedule_evidence_sha256
            or schedule.source != request.schedule.schedule_source
            or schedule.source_release != request.schedule.schedule_source_release
            or schedule.timezone != "Asia/Kolkata"
            or schedule.as_of > request.decision_cutoff
            or schedule.covered_from > request.schedule.sessions[0]
            or schedule.covered_to < request.decision_session
            or not schedule_covers_full_calendar_range(
                schedule, request.schedule.sessions[0], request.decision_session
            )
        ):
            return False
        retained_sessions = tuple(
            item
            for item in schedule.sessions
            if request.schedule.sessions[0]
            <= item.trade_date
            <= request.decision_session
        )
        return (
            tuple(item.trade_date for item in retained_sessions)
            == request.schedule.sessions
            and retained_sessions[-1].close_at
            == request.schedule.decision_session_official_close_at
        )
    except (OSError, ValueError, _ImmutableEvidenceConflict):
        return False
    finally:
        lease.close()


def capture_forward_adjusted_ohlcv_v1(
    request: CaptureForwardAdjustedOhlcvRequestV1,
    store_root: Path,
    schedule_root: Path,
) -> CaptureForwardAdjustedOhlcvResultV1:
    """Capture through the sole sealed yfinance adapter."""

    return _capture_forward_adjusted_ohlcv_with_provider_v1(
        request,
        YfinanceCaptureForwardAdjustedOhlcvAdapterV1(),
        store_root,
        schedule_root,
    )


def _ensure_capture_authority(
    operation: StorageRootLeaseOperation,
    revisions: _PrivateDirectory,
    requests: _PrivateDirectory,
    prepared: _PrivateDirectory,
) -> None:
    operation.ensure_live()
    revisions.ensure_live()
    requests.ensure_live()
    prepared.ensure_live()


def _ensure_capture_state(
    operation: StorageRootLeaseOperation,
    revisions: _PrivateDirectory,
    requests: _PrivateDirectory,
    prepared: _PrivateDirectory,
    request: CaptureForwardAdjustedOhlcvRequestV1,
    parent: AdjustedOhlcvCaptureRevisionV1 | None,
) -> None:
    _ensure_capture_authority(operation, revisions, requests, prepared)
    if parent is None:
        return
    admitted = _read_admitted_revision(
        operation,
        requests,
        revisions,
        parent.revision_sha256,
    )
    if admitted != parent or not _valid_correction_parent(request, admitted):
        raise _ImmutableEvidenceConflict("correction parent is no longer admitted")


def _capture_forward_adjusted_ohlcv_with_provider_v1(  # noqa: C901
    request: CaptureForwardAdjustedOhlcvRequestV1,
    provider: _CaptureForwardAdjustedOhlcvProviderV1,
    store_root: Path,
    schedule_root: Path,
) -> CaptureForwardAdjustedOhlcvResultV1:
    if (
        type(request) is not CaptureForwardAdjustedOhlcvRequestV1
        or not _valid_absolute_path(store_root)
        or not _valid_absolute_path(schedule_root)
    ):
        raise ValueError("capture invocation is invalid")
    if (
        request.schema_identity_sha256,
        request.runtime_code_identity_sha256,
        request.configuration_identity_sha256,
    ) != capture_forward_current_identities_v1():
        raise ValueError("capture request identity mismatch")
    if not _retained_schedule_matches_request(request, schedule_root):
        return CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE", "SCHEDULE_EVIDENCE_MISMATCH"
        )

    root_identity = StorageRootLease.admit_existing_private_identity(store_root)
    if root_identity is None:
        return CaptureForwardAdjustedOhlcvFailureV1(
            "STORE_UNAVAILABLE", "STORAGE_UNSAFE_OR_HELD"
        )
    lease_result = StorageRootLease.try_acquire_existing_identity(
        store_root, root_identity
    )
    if lease_result.outcome is LeaseOutcome.FAILED:
        lease_result = StorageRootLease.try_acquire_private_empty_identity(
            store_root, root_identity
        )
    if lease_result.outcome is not LeaseOutcome.ACQUIRED or lease_result.lease is None:
        return CaptureForwardAdjustedOhlcvFailureV1(
            "STORE_UNAVAILABLE", "STORAGE_UNSAFE_OR_HELD"
        )
    lease = lease_result.lease
    try:
        with lease.root_operation(store_root) as operation:
            root_descriptor = operation.descriptor
            revisions: _PrivateDirectory | None = None
            requests: _PrivateDirectory | None = None
            prepared: _PrivateDirectory | None = None
            try:
                revisions = _open_private_directory(
                    operation, root_descriptor, "revisions", create=True
                )
                requests = _open_private_directory(
                    operation, root_descriptor, "requests", create=True
                )
                prepared = _open_private_directory(
                    operation, root_descriptor, "prepared", create=True
                )
                try:
                    existing = _read_request_revision(
                        operation,
                        requests,
                        revisions,
                        request,
                    )
                except _CorrectionAncestorUnavailable:
                    _ensure_capture_authority(operation, revisions, requests, prepared)
                    return CaptureForwardAdjustedOhlcvFailureV1(
                        "STORE_UNAVAILABLE", "PARENT_REVISION_UNAVAILABLE"
                    )
                if existing is not None and not _revision_matches_request(
                    request, existing
                ):
                    _ensure_capture_authority(operation, revisions, requests, prepared)
                    return CaptureForwardAdjustedOhlcvFailureV1(
                        "STORE_UNAVAILABLE", "PUBLISHED_REVISION_MISMATCH"
                    )

                parent: AdjustedOhlcvCaptureRevisionV1 | None = None
                if request.parent_revision_sha256 is not None:
                    try:
                        parent = _read_admitted_revision(
                            operation,
                            requests,
                            revisions,
                            request.parent_revision_sha256,
                        )
                    except OSError:
                        if existing is not None:
                            _revalidate_request_pointer(
                                requests,
                                existing.request_identity_sha256,
                                existing.revision_sha256,
                            )
                        _ensure_capture_authority(
                            operation, revisions, requests, prepared
                        )
                        return CaptureForwardAdjustedOhlcvFailureV1(
                            "STORE_UNAVAILABLE", "PARENT_REVISION_UNAVAILABLE"
                        )
                    if not _valid_correction_parent(request, parent):
                        if existing is not None:
                            _revalidate_request_pointer(
                                requests,
                                existing.request_identity_sha256,
                                existing.revision_sha256,
                            )
                        _ensure_capture_authority(
                            operation, revisions, requests, prepared
                        )
                        return CaptureForwardAdjustedOhlcvFailureV1(
                            "INSUFFICIENT_EVIDENCE", "PARENT_REVISION_MISMATCH"
                        )

                if existing is not None:
                    try:
                        _ensure_capture_state(
                            operation,
                            revisions,
                            requests,
                            prepared,
                            request,
                            parent,
                        )
                    except (OSError, RuntimeError):
                        _revalidate_request_pointer(
                            requests,
                            existing.request_identity_sha256,
                            existing.revision_sha256,
                        )
                        raise
                    return CaptureForwardAdjustedOhlcvSuccessV1("REUSED", existing)

                prepared_recovery = _read_prepared_revision(
                    operation, prepared, request.request_identity_sha256
                )
                if prepared_recovery is not None:
                    recovered, held_prepared = prepared_recovery
                    try:
                        if not _revision_matches_request(request, recovered):
                            _ensure_capture_state(
                                operation,
                                revisions,
                                requests,
                                prepared,
                                request,
                                parent,
                            )
                            return CaptureForwardAdjustedOhlcvFailureV1(
                                "STORE_UNAVAILABLE", "PREPARED_REVISION_MISMATCH"
                            )
                        _ensure_capture_state(
                            operation, revisions, requests, prepared, request, parent
                        )
                        held_prepared.commit()
                        _ensure_capture_state(
                            operation, revisions, requests, prepared, request, parent
                        )
                        _publish_revision(operation, revisions, recovered)
                        _ensure_capture_state(
                            operation, revisions, requests, prepared, request, parent
                        )
                        exact = _read_revision_descriptor(
                            operation,
                            revisions,
                            recovered.revision_sha256,
                        )
                        if exact != recovered:
                            return CaptureForwardAdjustedOhlcvFailureV1(
                                "STORE_UNAVAILABLE", "EXACT_READBACK_FAILED"
                            )
                        operation.ensure_live()
                        os.fsync(root_descriptor)
                        _ensure_capture_state(
                            operation,
                            revisions,
                            requests,
                            prepared,
                            request,
                            parent,
                        )
                        _publish_request_pointer(
                            operation, requests, revisions, request, recovered
                        )
                        return CaptureForwardAdjustedOhlcvSuccessV1("CAPTURED", exact)
                    finally:
                        held_prepared.close()

                _ensure_capture_state(
                    operation, revisions, requests, prepared, request, parent
                )
                try:
                    frame = provider.download(
                        tickers=tuple(
                            member.provider_symbol for member in request.cohort
                        ),
                        start=request.schedule.sessions[0].isoformat(),
                        end=(request.decision_session + timedelta(days=1)).isoformat(),
                        interval="1d",
                        actions=False,
                        threads=False,
                        ignore_tz=False,
                        group_by="ticker",
                        auto_adjust=True,
                        back_adjust=False,
                        repair=False,
                        keepna=True,
                        progress=False,
                        prepost=False,
                        rounding=False,
                        timeout=10,
                        multi_level_index=True,
                        expected_sessions=tuple(
                            session.isoformat() for session in request.schedule.sessions
                        ),
                    )
                except Exception:
                    _ensure_capture_state(
                        operation, revisions, requests, prepared, request, parent
                    )
                    return CaptureForwardAdjustedOhlcvFailureV1(
                        "INSUFFICIENT_EVIDENCE", "PROVIDER_CALL_FAILED"
                    )
                _ensure_capture_state(
                    operation, revisions, requests, prepared, request, parent
                )
                normalized = _normalize_provider_frame(request, frame)
                if isinstance(normalized, CaptureForwardAdjustedOhlcvFailureV1):
                    _ensure_capture_state(
                        operation, revisions, requests, prepared, request, parent
                    )
                    return normalized
                revision = normalized
                if parent is not None and _same_correction_content(parent, revision):
                    _ensure_capture_state(
                        operation, revisions, requests, prepared, request, parent
                    )
                    return CaptureForwardAdjustedOhlcvFailureV1(
                        "INSUFFICIENT_EVIDENCE", "CORRECTION_CONTENT_UNCHANGED"
                    )
                _ensure_capture_state(
                    operation, revisions, requests, prepared, request, parent
                )
                _publish_prepared_revision(operation, prepared, revision)
                _ensure_capture_state(
                    operation, revisions, requests, prepared, request, parent
                )
                _publish_revision(operation, revisions, revision)
                _ensure_capture_state(
                    operation, revisions, requests, prepared, request, parent
                )
                exact = _read_revision_descriptor(
                    operation,
                    revisions,
                    revision.revision_sha256,
                )
                if exact != revision:
                    return CaptureForwardAdjustedOhlcvFailureV1(
                        "STORE_UNAVAILABLE", "EXACT_READBACK_FAILED"
                    )
                operation.ensure_live()
                os.fsync(root_descriptor)
                _ensure_capture_state(
                    operation, revisions, requests, prepared, request, parent
                )
                _publish_request_pointer(
                    operation, requests, revisions, request, revision
                )
                return CaptureForwardAdjustedOhlcvSuccessV1("CAPTURED", exact)
            finally:
                if prepared is not None:
                    prepared.close()
                if requests is not None:
                    requests.close()
                if revisions is not None:
                    revisions.close()
    except _ImmutableEvidenceConflict:
        return CaptureForwardAdjustedOhlcvFailureV1(
            "STORE_UNAVAILABLE", "EVIDENCE_CONFLICT"
        )
    except (OSError, RuntimeError):
        return CaptureForwardAdjustedOhlcvFailureV1(
            "STORE_UNAVAILABLE", "STORAGE_OPERATION_FAILED"
        )
    finally:
        lease.close()


def _revision_matches_request(
    request: CaptureForwardAdjustedOhlcvRequestV1,
    revision: AdjustedOhlcvCaptureRevisionV1,
) -> bool:
    return (
        revision.request_identity_sha256 == request.request_identity_sha256
        and revision.cohort == request.cohort
        and revision.cohort_identity_sha256 == request.cohort_identity_sha256
        and revision.schedule == request.schedule
        and revision.decision_session == request.decision_session
        and revision.decision_cutoff == request.decision_cutoff
        and revision.parent_revision_sha256 == request.parent_revision_sha256
        and revision.schema_identity_sha256 == request.schema_identity_sha256
        and revision.runtime_code_identity_sha256
        == request.runtime_code_identity_sha256
        and revision.configuration_identity_sha256
        == request.configuration_identity_sha256
    )


def _valid_correction_parent(
    request: CaptureForwardAdjustedOhlcvRequestV1,
    parent: AdjustedOhlcvCaptureRevisionV1,
) -> bool:
    return (
        parent.revision_sha256 == request.parent_revision_sha256
        and parent.cohort == request.cohort
        and parent.cohort_identity_sha256 == request.cohort_identity_sha256
        and parent.schedule == request.schedule
        and parent.decision_session == request.decision_session
        and parent.decision_cutoff == request.decision_cutoff
        and parent.schema_identity_sha256 == request.schema_identity_sha256
        and parent.runtime_code_identity_sha256 == request.runtime_code_identity_sha256
        and parent.configuration_identity_sha256
        == request.configuration_identity_sha256
    )


def _ensure_valid_revision_parent(
    child: AdjustedOhlcvCaptureRevisionV1,
    parent: AdjustedOhlcvCaptureRevisionV1,
) -> None:
    if not (
        parent.revision_sha256 == child.parent_revision_sha256
        and parent.cohort == child.cohort
        and parent.cohort_identity_sha256 == child.cohort_identity_sha256
        and parent.schedule == child.schedule
        and parent.decision_session == child.decision_session
        and parent.decision_cutoff == child.decision_cutoff
        and parent.schema_identity_sha256 == child.schema_identity_sha256
        and parent.runtime_code_identity_sha256 == child.runtime_code_identity_sha256
        and parent.configuration_identity_sha256 == child.configuration_identity_sha256
    ):
        raise _CorrectionAncestorUnavailable


def _same_correction_content(
    parent: AdjustedOhlcvCaptureRevisionV1,
    revision: AdjustedOhlcvCaptureRevisionV1,
) -> bool:
    return (
        parent.cohort == revision.cohort
        and parent.schedule == revision.schedule
        and parent.decision_session == revision.decision_session
        and parent.decision_cutoff == revision.decision_cutoff
        and parent.provider_source == revision.provider_source
        and parent.source_identity_sha256 == revision.source_identity_sha256
        and parent.bars == revision.bars
        and parent.schema_identity_sha256 == revision.schema_identity_sha256
        and parent.runtime_code_identity_sha256 == revision.runtime_code_identity_sha256
        and parent.configuration_identity_sha256
        == revision.configuration_identity_sha256
    )


def _normalize_provider_frame(  # noqa: C901 - closed provider admission
    request: CaptureForwardAdjustedOhlcvRequestV1, frame: object
) -> AdjustedOhlcvCaptureRevisionV1 | CaptureForwardAdjustedOhlcvFailureV1:
    if isinstance(frame, CaptureForwardAdjustedOhlcvFailureV1):
        return frame
    if not isinstance(frame, Mapping) or not frame:
        return CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE", "PROVIDER_EMPTY"
        )
    frame_mapping = cast(Mapping[str, object], frame)
    if frame_mapping.get("provider_source") != EXPECTED_PROVIDER_SOURCE_V1:
        return CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE", "PROVIDER_IDENTITY_MISMATCH"
        )
    if frame_mapping.get("timezone") != "Asia/Kolkata":
        return CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE", "FRAME_SCHEMA_INVALID"
        )
    index = frame_mapping.get("index")
    if type(index) is not tuple or index != request.schedule.sessions:
        return CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE", "FRAME_COVERAGE_INCOMPLETE"
        )
    retrieved_raw = frame_mapping.get("retrieved_at")
    try:
        retrieved_at = _utc(cast(datetime, retrieved_raw), "retrieved_at")
    except (TypeError, ValueError):
        return CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE", "FRAME_SCHEMA_INVALID"
        )
    raw_ohlcv = frame_mapping.get("ohlcv")
    if not isinstance(raw_ohlcv, Mapping):
        return CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE", "FRAME_COVERAGE_INCOMPLETE"
        )
    ohlcv = cast(Mapping[str, object], raw_ohlcv)
    if set(ohlcv) != {member.provider_symbol for member in request.cohort}:
        return CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE", "FRAME_COVERAGE_INCOMPLETE"
        )
    bars: list[AdjustedOhlcvBarV1] = []
    for member in request.cohort:
        raw_rows = ohlcv.get(member.provider_symbol)
        if type(raw_rows) is not tuple:
            return CaptureForwardAdjustedOhlcvFailureV1(
                "INSUFFICIENT_EVIDENCE", "FRAME_COVERAGE_INCOMPLETE"
            )
        rows = cast(tuple[object, ...], raw_rows)
        if len(rows) != len(request.schedule.sessions):
            return CaptureForwardAdjustedOhlcvFailureV1(
                "INSUFFICIENT_EVIDENCE", "FRAME_COVERAGE_INCOMPLETE"
            )
        for session, raw_row_value in zip(request.schedule.sessions, rows, strict=True):
            if not isinstance(raw_row_value, Mapping):
                return CaptureForwardAdjustedOhlcvFailureV1(
                    "INSUFFICIENT_EVIDENCE", "FRAME_SCHEMA_INVALID"
                )
            raw_row = cast(Mapping[str, object], raw_row_value)
            if set(raw_row) != {"open", "high", "low", "close", "volume"}:
                return CaptureForwardAdjustedOhlcvFailureV1(
                    "INSUFFICIENT_EVIDENCE", "FRAME_SCHEMA_INVALID"
                )
            values = tuple(
                _decimal(raw_row.get(name)) for name in ("open", "high", "low", "close")
            )
            volume = _volume(raw_row.get("volume"))
            if any(value is None for value in values) or volume is None:
                return CaptureForwardAdjustedOhlcvFailureV1(
                    "INSUFFICIENT_EVIDENCE", "FRAME_VALUE_INVALID"
                )
            try:
                bars.append(
                    AdjustedOhlcvBarV1(
                        member_isin=member.isin,
                        member_exchange=member.exchange,
                        session=session,
                        open=cast(Decimal, values[0]),
                        high=cast(Decimal, values[1]),
                        low=cast(Decimal, values[2]),
                        close=cast(Decimal, values[3]),
                        volume=volume,
                    )
                )
            except ValueError:
                return CaptureForwardAdjustedOhlcvFailureV1(
                    "INSUFFICIENT_EVIDENCE", "FRAME_VALUE_INVALID"
                )
    if retrieved_at < request.schedule.decision_session_official_close_at:
        return CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE", "RETRIEVED_BEFORE_OFFICIAL_CLOSE"
        )
    if retrieved_at > request.decision_cutoff:
        return CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE", "RETRIEVED_AFTER_DECISION_CUTOFF"
        )
    source_identity = _capture_source_identity_v1(request.configuration_identity_sha256)
    return AdjustedOhlcvCaptureRevisionV1(
        request_identity_sha256=request.request_identity_sha256,
        cohort=request.cohort,
        cohort_identity_sha256=request.cohort_identity_sha256,
        schedule=request.schedule,
        decision_session=request.decision_session,
        decision_cutoff=request.decision_cutoff,
        retrieved_at=retrieved_at,
        provider_source=EXPECTED_PROVIDER_SOURCE_V1,
        source_identity_sha256=source_identity,
        parent_revision_sha256=request.parent_revision_sha256,
        bars=tuple(bars),
        schema_identity_sha256=request.schema_identity_sha256,
        runtime_code_identity_sha256=request.runtime_code_identity_sha256,
        configuration_identity_sha256=request.configuration_identity_sha256,
    )


def _decimal(value: object) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if type(value) is Decimal:
        result = value
    elif isinstance(value, Real):
        result = Decimal(str(value))
    else:
        return None
    return result if result.is_finite() else None


def _volume(value: object) -> int | None:
    number = _decimal(value)
    if number is None or number < 0 or number != number.to_integral_value():
        return None
    result = int(number)
    return result if result >= 0 else None


@dataclass(slots=True)
class _PrivateDirectory:
    operation: StorageRootLeaseOperation
    parent_descriptor: int
    name: str
    descriptor: int
    identity: tuple[int, int, int, int]

    def ensure_live(self) -> None:
        self.operation.ensure_live()
        descriptor_metadata = os.fstat(self.descriptor)
        path_metadata = os.stat(
            self.name, dir_fd=self.parent_descriptor, follow_symlinks=False
        )
        descriptor_identity = (
            descriptor_metadata.st_dev,
            descriptor_metadata.st_ino,
            descriptor_metadata.st_mode,
            descriptor_metadata.st_uid,
        )
        path_identity = (
            path_metadata.st_dev,
            path_metadata.st_ino,
            path_metadata.st_mode,
            path_metadata.st_uid,
        )
        if (
            descriptor_identity != self.identity
            or path_identity != self.identity
            or not stat.S_ISDIR(descriptor_metadata.st_mode)
            or stat.S_IMODE(descriptor_metadata.st_mode) != 0o700
            or descriptor_metadata.st_uid != os.geteuid()
        ):
            raise OSError(errno.EBUSY, "private directory authority changed")

    def close(self) -> None:
        os.close(self.descriptor)


def _open_private_directory(
    operation: StorageRootLeaseOperation,
    parent_descriptor: int,
    name: str,
    *,
    create: bool,
) -> _PrivateDirectory:
    operation.ensure_live()
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
            operation.ensure_live()
            os.fsync(parent_descriptor)
        except FileExistsError:
            pass
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        dir_fd=parent_descriptor,
    )
    try:
        metadata = os.fstat(descriptor)
        directory = _PrivateDirectory(
            operation=operation,
            parent_descriptor=parent_descriptor,
            name=name,
            descriptor=descriptor,
            identity=(
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_uid,
            ),
        )
        directory.ensure_live()
        return directory
    except Exception:
        os.close(descriptor)
        raise


def _open_exact_file(
    directory: _PrivateDirectory,
    name: str,
    maximum: int,
    *,
    expected_mode: int = 0o400,
    expected_nlink: int = 1,
) -> tuple[int, bytes]:
    directory.ensure_live()
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
        dir_fd=directory.descriptor,
    )
    try:
        metadata = os.fstat(descriptor)
        path_metadata = os.stat(
            name, dir_fd=directory.descriptor, follow_symlinks=False
        )
        identity = _publication_identity(metadata)
        if (
            identity != _publication_identity(path_metadata)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != expected_mode
            or metadata.st_nlink != expected_nlink
            or metadata.st_size <= 0
            or metadata.st_size > maximum
        ):
            raise _ImmutableEvidenceConflict("unsafe immutable file")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            directory.ensure_live()
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise OSError(errno.EIO, "short read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if (
            _publication_identity(os.fstat(descriptor)) != identity
            or _publication_identity(
                os.stat(
                    name,
                    dir_fd=directory.descriptor,
                    follow_symlinks=False,
                )
            )
            != identity
        ):
            raise _ImmutableEvidenceConflict("immutable file changed")
        directory.ensure_live()
        return descriptor, b"".join(chunks)
    except Exception:
        os.close(descriptor)
        raise


def _publication_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _require_publication_name(
    directory: _PrivateDirectory,
    name: str,
    descriptor: int,
    *,
    expected_mode: int,
    expected_size: int,
) -> None:
    directory.ensure_live()
    held = os.fstat(descriptor)
    named = os.stat(name, dir_fd=directory.descriptor, follow_symlinks=False)
    if (
        _publication_identity(held) != _publication_identity(named)
        or not stat.S_ISREG(held.st_mode)
        or held.st_uid != os.geteuid()
        or stat.S_IMODE(held.st_mode) != expected_mode
        or held.st_nlink != 1
        or held.st_size != expected_size
    ):
        raise _ImmutableEvidenceConflict("publication identity changed")


def _read_held_exact_file(
    directory: _PrivateDirectory,
    name: str,
    descriptor: int,
    expected_size: int,
    *,
    expected_mode: int = 0o400,
) -> bytes:
    _require_publication_name(
        directory,
        name,
        descriptor,
        expected_mode=expected_mode,
        expected_size=expected_size,
    )
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = expected_size
    while remaining:
        directory.ensure_live()
        chunk = os.read(descriptor, min(remaining, 1024 * 1024))
        if not chunk:
            raise OSError(errno.EIO, "short read")
        chunks.append(chunk)
        remaining -= len(chunk)
    _require_publication_name(
        directory,
        name,
        descriptor,
        expected_mode=expected_mode,
        expected_size=expected_size,
    )
    return b"".join(chunks)


def _open_recoverable_publication(
    directory: _PrivateDirectory,
    name: str,
    maximum: int,
) -> tuple[int, bytes, int]:
    directory.ensure_live()
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
        dir_fd=directory.descriptor,
    )
    try:
        held = os.fstat(descriptor)
        mode = stat.S_IMODE(held.st_mode)
        if (
            not stat.S_ISREG(held.st_mode)
            or held.st_uid != os.geteuid()
            or mode not in (0o400, 0o600)
            or held.st_nlink != 1
            or not 1 <= held.st_size <= maximum
        ):
            raise _ImmutableEvidenceConflict("publication is unsafe")
        raw = _read_held_exact_file(
            directory,
            name,
            descriptor,
            held.st_size,
            expected_mode=mode,
        )
        return descriptor, raw, mode
    except Exception:
        os.close(descriptor)
        raise


class _CorrectionAncestorUnavailable(OSError):
    pass


@dataclass(slots=True)
class _HeldRecoverablePublication:
    directory: _PrivateDirectory
    name: str
    descriptor: int
    content: bytes
    mode: int

    def ensure_exact(self) -> None:
        exact = _read_held_exact_file(
            self.directory,
            self.name,
            self.descriptor,
            len(self.content),
            expected_mode=self.mode,
        )
        if exact != self.content:
            raise _ImmutableEvidenceConflict("publication readback failed")

    def commit(self) -> None:
        if self.mode == 0o600:
            _commit_held_publication(
                self.directory,
                self.name,
                self.descriptor,
                self.content,
            )
            self.mode = 0o400
        else:
            self.ensure_exact()

    def close(self) -> None:
        os.close(self.descriptor)


def _hold_recoverable_publication(
    directory: _PrivateDirectory,
    name: str,
    maximum: int,
) -> _HeldRecoverablePublication:
    descriptor, content, mode = _open_recoverable_publication(
        directory,
        name,
        maximum,
    )
    return _HeldRecoverablePublication(
        directory,
        name,
        descriptor,
        content,
        mode,
    )


def _commit_held_publication(
    directory: _PrivateDirectory,
    name: str,
    descriptor: int,
    content: bytes,
) -> None:
    directory.ensure_live()
    os.fsync(descriptor)
    directory.ensure_live()
    os.fsync(directory.descriptor)
    exact = _read_held_exact_file(
        directory,
        name,
        descriptor,
        len(content),
        expected_mode=0o600,
    )
    if exact != content:
        raise _ImmutableEvidenceConflict("publication readback failed")
    os.fchmod(descriptor, 0o400)
    os.fsync(descriptor)
    directory.ensure_live()
    os.fsync(directory.descriptor)
    exact = _read_held_exact_file(
        directory,
        name,
        descriptor,
        len(content),
    )
    if exact != content:
        raise _ImmutableEvidenceConflict("publication commit readback failed")


def _recover_publication(
    directory: _PrivateDirectory,
    name: str,
    content: bytes,
) -> bool:
    try:
        descriptor, existing, mode = _open_recoverable_publication(
            directory,
            name,
            len(content),
        )
    except FileNotFoundError:
        return False
    try:
        if existing != content:
            raise _ImmutableEvidenceConflict("immutable content conflict")
        if mode == 0o600:
            _commit_held_publication(directory, name, descriptor, content)
        else:
            directory.ensure_live()
            os.fsync(descriptor)
            directory.ensure_live()
            os.fsync(directory.descriptor)
            exact = _read_held_exact_file(
                directory,
                name,
                descriptor,
                len(content),
            )
            if exact != content:
                raise _ImmutableEvidenceConflict("publication recovery readback failed")
        return True
    finally:
        os.close(descriptor)


def _prepare_publication(
    operation: StorageRootLeaseOperation,
    directory: _PrivateDirectory,
    name: str,
    content: bytes,
) -> _HeldRecoverablePublication:
    operation.ensure_live()
    try:
        held = _hold_recoverable_publication(directory, name, len(content))
    except FileNotFoundError:
        directory.ensure_live()
        descriptor = os.open(
            name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=directory.descriptor,
        )
        try:
            view = memoryview(content)
            written = 0
            while written < len(view):
                directory.ensure_live()
                count = os.write(descriptor, view[written:])
                if count <= 0:
                    raise OSError(errno.EIO, "short write")
                written += count
            held = _HeldRecoverablePublication(
                directory,
                name,
                descriptor,
                content,
                0o600,
            )
            held.ensure_exact()
            return held
        except Exception:
            os.close(descriptor)
            raise
    if held.content != content:
        held.close()
        raise _ImmutableEvidenceConflict("immutable content conflict")
    return held


def _publish_bytes(
    operation: StorageRootLeaseOperation,
    directory: _PrivateDirectory,
    name: str,
    content: bytes,
) -> None:
    operation.ensure_live()
    if _recover_publication(directory, name, content):
        return
    directory.ensure_live()
    descriptor = os.open(
        name,
        os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
        dir_fd=directory.descriptor,
    )
    try:
        view = memoryview(content)
        written = 0
        while written < len(view):
            directory.ensure_live()
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError(errno.EIO, "short write")
            written += count
        _commit_held_publication(directory, name, descriptor, content)
    finally:
        os.close(descriptor)


def _read_exact_file(
    operation: StorageRootLeaseOperation,
    directory: _PrivateDirectory,
    name: str,
    maximum: int,
    *,
    expected_mode: int = 0o400,
    expected_nlink: int = 1,
) -> bytes:
    descriptor, raw = _open_exact_file(
        directory,
        name,
        maximum,
        expected_mode=expected_mode,
        expected_nlink=expected_nlink,
    )
    os.close(descriptor)
    return raw


def _pointer_bytes(request_identity_sha256: str, revision_sha256: str) -> bytes:
    return _canonical_line(
        {
            "request_identity_sha256": request_identity_sha256,
            "revision_sha256": revision_sha256,
        }
    )


def _publish_prepared_revision(
    operation: StorageRootLeaseOperation,
    prepared: _PrivateDirectory,
    revision: AdjustedOhlcvCaptureRevisionV1,
) -> None:
    _publish_bytes(
        operation,
        prepared,
        f"{revision.request_identity_sha256}.json",
        revision.canonical_json_bytes(),
    )


def _publish_revision(
    operation: StorageRootLeaseOperation,
    revisions: _PrivateDirectory,
    revision: AdjustedOhlcvCaptureRevisionV1,
) -> None:
    _publish_bytes(
        operation,
        revisions,
        f"{revision.revision_sha256}.json",
        revision.canonical_json_bytes(),
    )


def _publish_request_pointer(
    operation: StorageRootLeaseOperation,
    requests: _PrivateDirectory,
    revisions: _PrivateDirectory,
    request: CaptureForwardAdjustedOhlcvRequestV1,
    revision: AdjustedOhlcvCaptureRevisionV1,
) -> None:
    requested_pointer = (
        revision.revision_sha256,
        _prepare_publication(
            operation,
            requests,
            f"{request.request_identity_sha256}.json",
            _pointer_bytes(request.request_identity_sha256, revision.revision_sha256),
        ),
    )
    admitted, held_pointers, held_revisions = _validated_admission_chain(
        operation,
        requests,
        revisions,
        revision.revision_sha256,
        requested_pointer=requested_pointer,
    )
    try:
        if admitted != revision or not _revision_matches_request(request, admitted):
            raise _ImmutableEvidenceConflict("request pointer invalid")
        operation.ensure_live()
        requests.ensure_live()
        revisions.ensure_live()
        for held_revision in held_revisions:
            held_revision.ensure_exact()
        for held_pointer in held_pointers:
            held_pointer.ensure_exact()
        requested_pointer[1].commit()
        for held_revision in held_revisions:
            held_revision.ensure_exact()
        for held_pointer in held_pointers:
            held_pointer.ensure_exact()
    finally:
        for held_pointer in held_pointers:
            held_pointer.close()
        for held_revision in held_revisions:
            held_revision.close()


def _revalidate_request_pointer(
    requests: _PrivateDirectory,
    request_identity_sha256: str,
    revision_sha256: str,
) -> None:
    name = f"{request_identity_sha256}.json"
    expected = _pointer_bytes(request_identity_sha256, revision_sha256)
    descriptor, raw = _open_exact_file(requests, name, len(expected))
    try:
        if raw != expected:
            raise _ImmutableEvidenceConflict("request pointer changed")
    finally:
        os.close(descriptor)


def _open_pointer_revision(
    operation: StorageRootLeaseOperation,
    requests: _PrivateDirectory,
    request_identity_sha256: str,
    *,
    allow_uncommitted: bool,
) -> tuple[str, _HeldRecoverablePublication] | None:
    del operation
    name = f"{request_identity_sha256}.json"
    try:
        held = _hold_recoverable_publication(requests, name, 1024)
    except FileNotFoundError:
        return None
    try:
        parsed = json.loads(held.content)
        if type(parsed) is not dict:
            raise ValueError
        value = cast(dict[str, object], parsed)
        revision_sha256 = value.get("revision_sha256")
        if (
            set(value) != {"request_identity_sha256", "revision_sha256"}
            or value.get("request_identity_sha256") != request_identity_sha256
            or not _valid_digest(revision_sha256)
            or held.content
            != _pointer_bytes(request_identity_sha256, cast(str, revision_sha256))
            or (held.mode == 0o600 and not allow_uncommitted)
        ):
            raise ValueError
        return cast(str, revision_sha256), held
    except (json.JSONDecodeError, TypeError, ValueError):
        held.close()
        raise _ImmutableEvidenceConflict("request pointer invalid") from None
    except Exception:
        held.close()
        raise


def _raise_admission_failure(is_requested: bool, message: str) -> NoReturn:
    if not is_requested:
        raise _CorrectionAncestorUnavailable
    raise _ImmutableEvidenceConflict(message)


def _open_admission_pointer(
    operation: StorageRootLeaseOperation,
    requests: _PrivateDirectory,
    current: AdjustedOhlcvCaptureRevisionV1,
    requested_pointer: tuple[str, _HeldRecoverablePublication] | None,
    *,
    is_requested: bool,
) -> tuple[str, _HeldRecoverablePublication]:
    try:
        opened = (
            requested_pointer
            if is_requested and requested_pointer is not None
            else _open_pointer_revision(
                operation,
                requests,
                current.request_identity_sha256,
                allow_uncommitted=False,
            )
        )
    except OSError as error:
        if not is_requested:
            raise _CorrectionAncestorUnavailable from error
        raise
    if opened is None:
        _raise_admission_failure(is_requested, "capture revision is not admitted")
    return opened


def _read_correction_parent(
    operation: StorageRootLeaseOperation,
    revisions: _PrivateDirectory,
    parent_revision_sha256: str,
) -> tuple[AdjustedOhlcvCaptureRevisionV1, _HeldRecoverablePublication]:
    try:
        return _hold_revision_descriptor(
            operation,
            revisions,
            parent_revision_sha256,
        )
    except OSError as error:
        raise _CorrectionAncestorUnavailable from error


def _append_unique_held_publication(
    held: list[_HeldRecoverablePublication],
    candidate: _HeldRecoverablePublication,
) -> None:
    if all(item is not candidate for item in held):
        held.append(candidate)


def _validated_admission_chain(
    operation: StorageRootLeaseOperation,
    requests: _PrivateDirectory,
    revisions: _PrivateDirectory,
    revision_sha256: str,
    *,
    requested_pointer: tuple[str, _HeldRecoverablePublication] | None = None,
) -> tuple[
    AdjustedOhlcvCaptureRevisionV1,
    list[_HeldRecoverablePublication],
    list[_HeldRecoverablePublication],
]:
    held_pointers = [requested_pointer[1]] if requested_pointer is not None else []
    held_revisions: list[_HeldRecoverablePublication] = []
    try:
        requested, held_requested = _hold_revision_descriptor(
            operation, revisions, revision_sha256
        )
        held_revisions.append(held_requested)
        current = requested
        seen: set[str] = set()
        first = True
        while True:
            is_requested = first
            if current.revision_sha256 in seen or len(seen) >= MAX_WINDOW_SESSIONS_V1:
                _raise_admission_failure(
                    is_requested,
                    "capture correction chain is invalid",
                )
            seen.add(current.revision_sha256)
            admitted_sha256, held_pointer = _open_admission_pointer(
                operation,
                requests,
                current,
                requested_pointer,
                is_requested=is_requested,
            )
            first = False
            _append_unique_held_publication(held_pointers, held_pointer)
            if admitted_sha256 != current.revision_sha256:
                _raise_admission_failure(
                    is_requested,
                    "capture revision is not admitted",
                )
            if current.parent_revision_sha256 is None:
                for held_revision in held_revisions:
                    held_revision.ensure_exact()
                for pointer in held_pointers:
                    pointer.ensure_exact()
                return requested, held_pointers, held_revisions
            child = current
            parent, held_revision = _read_correction_parent(
                operation,
                revisions,
                cast(str, child.parent_revision_sha256),
            )
            held_revisions.append(held_revision)
            _ensure_valid_revision_parent(child, parent)
            current = parent
    except Exception:
        for pointer in held_pointers:
            pointer.close()
        for held_revision in held_revisions:
            held_revision.close()
        raise


def _read_request_revision(  # noqa: C901 - bounded immutable-admission transaction
    operation: StorageRootLeaseOperation,
    requests: _PrivateDirectory,
    revisions: _PrivateDirectory,
    request: CaptureForwardAdjustedOhlcvRequestV1,
    *,
    commit_pointer: bool = True,
) -> AdjustedOhlcvCaptureRevisionV1 | None:
    requested_pointer = _open_pointer_revision(
        operation,
        requests,
        request.request_identity_sha256,
        allow_uncommitted=True,
    )
    if requested_pointer is None:
        return None
    revision_sha256, _ = requested_pointer
    revision, held_pointers, held_revisions = _validated_admission_chain(
        operation,
        requests,
        revisions,
        revision_sha256,
        requested_pointer=requested_pointer,
    )
    try:
        if not _revision_matches_request(request, revision):
            raise _ImmutableEvidenceConflict("request pointer invalid")
        operation.ensure_live()
        requests.ensure_live()
        revisions.ensure_live()
        for held_revision in held_revisions:
            held_revision.ensure_exact()
        for pointer in held_pointers:
            pointer.ensure_exact()
        if not commit_pointer and requested_pointer[1].mode != 0o400:
            return None
        if commit_pointer:
            requested_pointer[1].commit()
        for held_revision in held_revisions:
            held_revision.ensure_exact()
        for pointer in held_pointers:
            pointer.ensure_exact()
        return revision
    finally:
        for pointer in held_pointers:
            pointer.close()
        for held_revision in held_revisions:
            held_revision.close()


def _read_prepared_revision(
    operation: StorageRootLeaseOperation,
    prepared: _PrivateDirectory,
    request_identity_sha256: str,
) -> tuple[AdjustedOhlcvCaptureRevisionV1, _HeldRecoverablePublication] | None:
    del operation
    name = f"{request_identity_sha256}.json"
    try:
        held = _hold_recoverable_publication(
            prepared,
            name,
            MAX_REVISION_BYTES_V1,
        )
    except FileNotFoundError:
        return None
    try:
        revision = _revision_from_value(json.loads(held.content))
        if (
            revision.request_identity_sha256 != request_identity_sha256
            or held.content != revision.canonical_json_bytes()
        ):
            raise ValueError
        return revision, held
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        held.close()
        raise _ImmutableEvidenceConflict("prepared revision invalid") from None
    except Exception:
        held.close()
        raise


def _read_admitted_revision(
    operation: StorageRootLeaseOperation,
    requests: _PrivateDirectory,
    revisions: _PrivateDirectory,
    revision_sha256: str,
) -> AdjustedOhlcvCaptureRevisionV1:
    requested, held_pointers, held_revisions = _validated_admission_chain(
        operation,
        requests,
        revisions,
        revision_sha256,
    )
    try:
        return requested
    finally:
        for pointer in held_pointers:
            pointer.close()
        for held_revision in held_revisions:
            held_revision.close()


def _admit_existing_private_empty_store_v1(store_root: Path) -> bool:
    descriptor: int | None = None
    admitted = False
    try:
        descriptor = lease_core._open_directory_without_symlink_components(  # pyright: ignore[reportPrivateUsage]
            store_root
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError
        lease_core._assert_private_empty_root(  # pyright: ignore[reportPrivateUsage]
            store_root, descriptor, metadata
        )
        admitted = True
    except Exception:
        admitted = False
    finally:
        if not lease_core._close_descriptor(  # pyright: ignore[reportPrivateUsage]
            descriptor
        ):
            admitted = False
    return admitted


def _acquire_existing_private_lease(store_root: Path) -> StorageRootLease | None:
    root_identity = StorageRootLease.admit_existing_private_identity(store_root)
    if root_identity is None:
        return None
    result = StorageRootLease.try_acquire_existing_identity(store_root, root_identity)
    if result.outcome is not LeaseOutcome.ACQUIRED:
        return None
    return result.lease


def read_capture_forward_request_revision_v1(  # noqa: C901 - one exact read
    store_root: Path, request: CaptureForwardAdjustedOhlcvRequestV1
) -> AdjustedOhlcvCaptureRevisionV1 | None:
    """Read-validate one request's immutable store state without creating it."""

    if type(
        request
    ) is not CaptureForwardAdjustedOhlcvRequestV1 or not _valid_absolute_path(
        store_root
    ):
        raise ValueError("request revision read is invalid")
    lease = _acquire_existing_private_lease(store_root)
    if lease is None:
        if _admit_existing_private_empty_store_v1(store_root):
            return None
        raise OSError(errno.EBUSY, "capture store unavailable")
    directories: list[_PrivateDirectory | None] = []
    try:
        with lease.read_operation(store_root) as operation:
            for name in ("revisions", "requests", "prepared"):
                try:
                    directory = _open_private_directory(
                        operation, operation.descriptor, name, create=False
                    )
                except FileNotFoundError:
                    directory = None
                directories.append(directory)
            if all(directory is None for directory in directories):
                return None
            if any(directory is None for directory in directories):
                raise _ImmutableEvidenceConflict("capture store state incomplete")
            revisions, requests, prepared = cast(
                tuple[_PrivateDirectory, _PrivateDirectory, _PrivateDirectory],
                tuple(directories),
            )
            existing = _read_request_revision(
                operation,
                requests,
                revisions,
                request,
                commit_pointer=False,
            )
            parent: AdjustedOhlcvCaptureRevisionV1 | None = None
            if request.parent_revision_sha256 is not None:
                parent = _read_admitted_revision(
                    operation, requests, revisions, request.parent_revision_sha256
                )
                if not _valid_correction_parent(request, parent):
                    raise _ImmutableEvidenceConflict("correction parent invalid")
            _ensure_capture_state(
                operation, revisions, requests, prepared, request, parent
            )
            if existing is not None:
                return existing
            prepared_recovery = _read_prepared_revision(
                operation, prepared, request.request_identity_sha256
            )
            if prepared_recovery is None:
                return None
            recovered, held_prepared = prepared_recovery
            try:
                if not _revision_matches_request(request, recovered):
                    raise _ImmutableEvidenceConflict("prepared revision invalid")
                return None
            finally:
                held_prepared.close()
    except _ImmutableEvidenceConflict:
        raise ValueError("request revision evidence conflict") from None
    finally:
        for directory in directories:
            if directory is not None:
                directory.close()
        lease.close()


def read_capture_forward_revision_v1(
    store_root: Path, revision_sha256: str
) -> AdjustedOhlcvCaptureRevisionV1:
    """Exact-read one explicitly named admitted immutable capture revision."""

    if not _valid_digest(revision_sha256):
        raise ValueError("capture revision read is invalid")
    lease = _acquire_existing_private_lease(store_root)
    if lease is None:
        raise ValueError("capture revision unavailable")
    try:
        with lease.read_operation(store_root) as operation:
            revisions = _open_private_directory(
                operation, operation.descriptor, "revisions", create=False
            )
            requests: _PrivateDirectory | None = None
            try:
                requests = _open_private_directory(
                    operation, operation.descriptor, "requests", create=False
                )
                revision = _read_admitted_revision(
                    operation, requests, revisions, revision_sha256
                )
                operation.ensure_live()
                requests.ensure_live()
                revisions.ensure_live()
                return revision
            finally:
                if requests is not None:
                    requests.close()
                revisions.close()
    except (OSError, _ImmutableEvidenceConflict):
        raise ValueError("capture revision unavailable") from None
    finally:
        lease.close()


def _hold_revision_descriptor(
    operation: StorageRootLeaseOperation,
    revisions: _PrivateDirectory,
    revision_sha256: str,
) -> tuple[AdjustedOhlcvCaptureRevisionV1, _HeldRecoverablePublication]:
    del operation
    name = f"{revision_sha256}.json"
    if _REVISION_NAME.fullmatch(name) is None:
        raise OSError(errno.EINVAL, "revision name invalid")
    held = _hold_recoverable_publication(revisions, name, MAX_REVISION_BYTES_V1)
    try:
        if held.mode != 0o400:
            raise ValueError
        value = json.loads(held.content)
        revision = _revision_from_value(value)
        if (
            revision.revision_sha256 != revision_sha256
            or held.content != revision.canonical_json_bytes()
        ):
            raise ValueError
        return revision, held
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        held.close()
        raise _ImmutableEvidenceConflict("capture revision invalid") from None
    except Exception:
        held.close()
        raise


def _read_revision_descriptor(
    operation: StorageRootLeaseOperation,
    revisions: _PrivateDirectory,
    revision_sha256: str,
) -> AdjustedOhlcvCaptureRevisionV1:
    revision, held = _hold_revision_descriptor(
        operation,
        revisions,
        revision_sha256,
    )
    try:
        return revision
    finally:
        held.close()


def _revision_from_value(value: object) -> AdjustedOhlcvCaptureRevisionV1:
    if type(value) is not dict:
        raise ValueError
    row = cast(dict[str, object], value)
    cohort_raw = cast(list[dict[str, object]], row["cohort"])
    cohort = tuple(_member_from_value(member) for member in cohort_raw)
    schedule = _schedule_from_value(cast(dict[str, object], row["schedule"]))
    bars_raw = cast(list[dict[str, object]], row["bars"])
    bars = tuple(_bar_from_value(bar) for bar in bars_raw)
    revision = AdjustedOhlcvCaptureRevisionV1(
        request_identity_sha256=cast(str, row["request_identity_sha256"]),
        cohort=cohort,
        cohort_identity_sha256=cast(str, row["cohort_identity_sha256"]),
        schedule=schedule,
        decision_session=date.fromisoformat(cast(str, row["decision_session"])),
        decision_cutoff=_parse_instant(row["decision_cutoff"]),
        retrieved_at=_parse_instant(row["retrieved_at"]),
        provider_source=cast(str, row["provider_source"]),
        source_identity_sha256=cast(str, row["source_identity_sha256"]),
        parent_revision_sha256=cast(str | None, row["parent_revision_sha256"]),
        bars=bars,
        schema_identity_sha256=cast(str, row["schema_identity_sha256"]),
        runtime_code_identity_sha256=cast(str, row["runtime_code_identity_sha256"]),
        configuration_identity_sha256=cast(str, row["configuration_identity_sha256"]),
        contract_version=cast(str, row["contract_version"]),
        source_profile=cast(str, row["source_profile"]),
        price_basis=cast(str, row["price_basis"]),
        volume_basis=cast(str, row["volume_basis"]),
        permitted_use=cast(str, row["permitted_use"]),
        limitation=cast(str, row["limitation"]),
    )
    if row.get("revision_sha256") != revision.revision_sha256:
        raise ValueError
    return revision


def _member_from_value(
    row: Mapping[str, object],
) -> CaptureForwardAdjustedOhlcvMemberV1:
    valid_from = date.fromisoformat(cast(str, row["mapping_valid_from"]))
    valid_through_raw = row["mapping_valid_through"]
    return CaptureForwardAdjustedOhlcvMemberV1(
        isin=cast(str, row["isin"]),
        exchange=cast(str, row["exchange"]),
        effective_symbol=cast(str, row["effective_symbol"]),
        symbol_history_identity_sha256=cast(str, row["symbol_history_identity_sha256"]),
        provider_symbol=cast(str, row["provider_symbol"]),
        mapping_version=cast(str, row["mapping_version"]),
        mapping_valid_from=valid_from,
        mapping_valid_through=(
            None
            if valid_through_raw is None
            else date.fromisoformat(cast(str, valid_through_raw))
        ),
        mapping_identity_sha256=cast(str, row["mapping_identity_sha256"]),
    )


def _schedule_from_value(
    row: Mapping[str, object],
) -> CaptureForwardAdjustedOhlcvScheduleV1:
    schedule = CaptureForwardAdjustedOhlcvScheduleV1(
        sessions=tuple(
            date.fromisoformat(cast(str, value))
            for value in cast(list[object], row["sessions"])
        ),
        schedule_evidence_sha256=cast(str, row["schedule_evidence_sha256"]),
        schedule_source=cast(str, row["schedule_source"]),
        schedule_source_release=cast(str, row["schedule_source_release"]),
        decision_session_official_close_at=_parse_instant(
            row["decision_session_official_close_at"]
        ),
    )
    if row.get("schedule_identity_sha256") != schedule.schedule_identity_sha256:
        raise ValueError
    return schedule


def _bar_from_value(row: Mapping[str, object]) -> AdjustedOhlcvBarV1:
    return AdjustedOhlcvBarV1(
        member_isin=cast(str, row["member_isin"]),
        member_exchange=cast(str, row["member_exchange"]),
        session=date.fromisoformat(cast(str, row["session"])),
        open=Decimal(cast(str, row["open"])),
        high=Decimal(cast(str, row["high"])),
        low=Decimal(cast(str, row["low"])),
        close=Decimal(cast(str, row["close"])),
        volume=cast(int, row["volume"]),
    )


def _parse_instant(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError
    return _utc(datetime.fromisoformat(value[:-1] + "+00:00"), "instant")


def compose_capture_forward_plan29_v1(
    store_root: Path,
    revision_sha256s: tuple[str, ...],
    *,
    regions: tuple[HistoricalStudyRegionV1, ...],
    evaluated_at: datetime,
) -> CaptureForwardPlan29QualificationV1:
    """Exact-read named admitted revisions before deterministic composition."""

    if (
        not _valid_absolute_path(store_root)
        or type(revision_sha256s) is not tuple
        or not 4 <= len(revision_sha256s) <= 366
        or any(not _valid_digest(value) for value in revision_sha256s)
        or len(set(revision_sha256s)) != len(revision_sha256s)
    ):
        raise ValueError("capture-forward composition is invalid")
    lease = _acquire_existing_private_lease(store_root)
    if lease is None:
        raise ValueError("capture-forward composition is invalid")
    try:
        with lease.read_operation(store_root) as operation:
            revisions = _open_private_directory(
                operation, operation.descriptor, "revisions", create=False
            )
            requests: _PrivateDirectory | None = None
            try:
                requests = _open_private_directory(
                    operation, operation.descriptor, "requests", create=False
                )
                captures = tuple(
                    _read_admitted_revision(
                        operation, requests, revisions, revision_sha256
                    )
                    for revision_sha256 in revision_sha256s
                )
                operation.ensure_live()
                requests.ensure_live()
                revisions.ensure_live()
            finally:
                if requests is not None:
                    requests.close()
                revisions.close()
    except (OSError, RuntimeError, _ImmutableEvidenceConflict):
        raise ValueError("capture-forward composition is invalid") from None
    finally:
        lease.close()
    return _compose_capture_forward_plan29_from_revisions_v1(
        captures, regions=regions, evaluated_at=evaluated_at
    )


def _compose_capture_forward_plan29_from_revisions_v1(  # noqa: C901
    captures: tuple[AdjustedOhlcvCaptureRevisionV1, ...],
    *,
    regions: tuple[HistoricalStudyRegionV1, ...],
    evaluated_at: datetime,
) -> CaptureForwardPlan29QualificationV1:

    evaluated = _utc(evaluated_at, "evaluated_at")
    if (
        type(captures) is not tuple
        or not 4 <= len(captures) <= 366
        or any(type(item) is not AdjustedOhlcvCaptureRevisionV1 for item in captures)
        or tuple(item.decision_session for item in captures)
        != tuple(sorted(item.decision_session for item in captures))
        or len({item.decision_session for item in captures}) != len(captures)
        or type(regions) is not tuple
        or len(regions) != len(captures)
        or any(type(region) is not HistoricalStudyRegionV1 for region in regions)
    ):
        raise ValueError("capture-forward composition is invalid")
    runs: list[HistoricalStudyRegionV1] = []
    for region in regions:
        if not runs or runs[-1] is not region:
            runs.append(region)
    if tuple(runs) != tuple(HistoricalStudyRegionV1):
        raise ValueError("capture-forward composition is invalid")
    first = captures[0]
    compatible_writer_runtimes = _compatible_writer_runtime_identities_v1()
    if any(
        capture.schema_identity_sha256 != _SCHEMA_IDENTITY_SHA256
        or capture.configuration_identity_sha256 != _CONFIGURATION_IDENTITY_SHA256
        or capture.runtime_code_identity_sha256 not in compatible_writer_runtimes
        or capture.source_identity_sha256
        != _capture_source_identity_v1(capture.configuration_identity_sha256)
        or capture.cohort != first.cohort
        or capture.cohort_identity_sha256 != first.cohort_identity_sha256
        or capture.provider_source != first.provider_source
        or capture.source_identity_sha256 != first.source_identity_sha256
        or capture.source_profile != first.source_profile
        or capture.price_basis != first.price_basis
        or capture.volume_basis != first.volume_basis
        or capture.schedule.schedule_source != first.schedule.schedule_source
        or capture.configuration_identity_sha256 != first.configuration_identity_sha256
        or capture.decision_cutoff > evaluated
        for capture in captures
    ):
        raise ValueError("capture-forward composition is invalid")

    cohort = tuple(
        CanonicalEquityV1(
            isin=member.isin,
            exchange=member.exchange,
            effective_symbol=member.effective_symbol,
            symbol_history_identity_sha256=member.symbol_history_identity_sha256,
            provider_mapping_identity_sha256=member.mapping_identity_sha256,
        )
        for member in first.cohort
    )
    sessions = tuple(capture.decision_session for capture in captures)
    capture_by_session = {capture.decision_session: capture for capture in captures}
    aggregate_revision = _sha(
        _canonical([capture.revision_sha256 for capture in captures])
    )
    schema, runtime, configuration = capability_validation_current_identities_v1()
    _, capture_forward_runtime, _ = capture_forward_current_identities_v1()
    composer_runtime = _sha(
        _canonical(
            {
                "capture_forward_runtime_code_identity_sha256": capture_forward_runtime,
                "plan29_runtime_code_identity_sha256": runtime,
            }
        )
    )
    source_identity = _sha(
        _canonical(
            {
                "capture_source_identities": [
                    capture.source_identity_sha256 for capture in captures
                ],
                "schedule_lineage": [
                    {
                        "schedule_identity_sha256": (
                            capture.schedule.schedule_identity_sha256
                        ),
                        "schedule_source": capture.schedule.schedule_source,
                        "schedule_source_release": (
                            capture.schedule.schedule_source_release
                        ),
                    }
                    for capture in captures
                ],
                "composer_runtime_code_identity_sha256": composer_runtime,
                "price_basis": ADJUSTED_PRICE_BASIS_V1,
                "source_profile": SOURCE_PROFILE_V1,
            }
        )
    )
    bars = tuple(
        HistoricalBarKnowledgeV1(
            member=member,
            session=session,
            known_at=capture_by_session[session].retrieved_at,
        )
        for member in cohort
        for session in sessions
    )
    comparability: list[HistoricalComparabilityProvenanceV1] = []
    receipt_by_key: dict[tuple[CanonicalEquityV1, date], str] = {}
    for member in cohort:
        for session in sessions:
            capture = capture_by_session[session]
            bar = next(
                item
                for item in capture.bars
                if item.member_isin == member.isin
                and item.member_exchange == member.exchange
                and item.session == session
            )
            receipt = _sha(
                _canonical(
                    {
                        "bar": bar.canonical_value(),
                        "capture_revision_sha256": capture.revision_sha256,
                        "price_basis": capture.price_basis,
                        "provider_source": capture.provider_source,
                        "retrieved_at": _timestamp(capture.retrieved_at),
                    }
                )
            )
            receipt_by_key[(member, session)] = receipt
            comparability.append(
                HistoricalComparabilityProvenanceV1(
                    member=member,
                    session=session,
                    source_identity_sha256=source_identity,
                    classification_receipt_sha256=receipt,
                    evidence_revision_sha256=aggregate_revision,
                    published_at=capture.retrieved_at,
                    known_at=capture.retrieved_at,
                )
            )
    evidence = HistoricalEvidenceRevisionV1(
        revision_contract_version=EVIDENCE_REVISION_CONTRACT_VERSION_V1,
        revision_sha256=aggregate_revision,
        cohort=cohort,
        sessions=sessions,
        interval="1d",
        source_profile=SOURCE_PROFILE_V1,
        price_basis=ADJUSTED_PRICE_BASIS_V1,
        temporal_status="POINT_IN_TIME",
        corporate_action_status="EVALUATED",
        comparability_status="ESTABLISHED",
        permitted_use=PERMITTED_USE_V1,
        bars=bars,
        comparability_provenance=tuple(comparability),
        source_identity_sha256=source_identity,
        schema_identity_sha256=schema,
        runtime_code_identity_sha256=composer_runtime,
        configuration_identity_sha256=configuration,
        limitation=LIMITATION_V1,
    )
    points = tuple(
        HistoricalDecisionPointV1(
            session=capture.decision_session,
            decision_cutoff=capture.decision_cutoff,
            region=region,
        )
        for capture, region in zip(captures, regions, strict=True)
    )
    ledger: list[HistoricalAvailabilityEntryV1] = []
    canonical_by_key = {(member.isin, member.exchange): member for member in cohort}
    for point in points:
        capture = capture_by_session[point.session]
        for feature in (
            HistoricalEvidenceFeatureV1.DAILY_OHLCV,
            HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY,
        ):
            for capture_member in first.cohort:
                member = canonical_by_key[
                    (capture_member.isin, capture_member.exchange)
                ]
                receipt = (
                    receipt_by_key[(member, point.session)]
                    if feature
                    is HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY
                    else _sha(
                        _canonical(
                            {
                                "capture_revision_sha256": capture.revision_sha256,
                                "feature": feature.value,
                                "member": member.canonical_value(),
                                "session": point.session.isoformat(),
                            }
                        )
                    )
                )
                ledger.append(
                    HistoricalAvailabilityEntryV1(
                        feature=feature,
                        member=member,
                        session=point.session,
                        interval="1d",
                        decision_cutoff=point.decision_cutoff,
                        state=AvailabilityStateV1.AVAILABLE,
                        source_identity_sha256=source_identity,
                        classification_receipt_sha256=receipt,
                        evidence_revision_sha256=aggregate_revision,
                        published_at=capture.retrieved_at,
                        known_at=capture.retrieved_at,
                    )
                )
    request = HistoricalValidationRequestV1(
        contract_version=PLAN29_CONTRACT_VERSION_V1,
        evaluated_at=evaluated,
        evidence_revision_sha256=aggregate_revision,
        cohort_identity_sha256=evidence.cohort_identity_sha256,
        cohort=cohort,
        decision_points=points,
        studies=tuple(
            HistoricalStudyDeclarationV1(profile=profile, minimum_coverage_bps=10_000)
            for profile in HistoricalStudyProfileV1
        ),
        availability_ledger=tuple(ledger),
        schema_identity_sha256=schema,
        runtime_code_identity_sha256=runtime,
        configuration_identity_sha256=configuration,
    )
    report = evaluate_capability_aware_historical_validation_v1(request, evidence)
    return CaptureForwardPlan29QualificationV1(evidence, request, report)


def serialize_capture_forward_result_v1(
    result: CaptureForwardAdjustedOhlcvResultV1,
) -> dict[str, str]:
    """Return a bounded owner-private-safe capture summary."""

    if isinstance(result, CaptureForwardAdjustedOhlcvFailureV1):
        return {"code": result.code, "reason": result.reason}
    return {
        "code": result.code,
        "contract_version": CONTRACT_VERSION_V1,
        "price_basis": result.revision.price_basis,
        "revision_sha256": result.revision.revision_sha256,
        "source_profile": result.revision.source_profile,
        "volume_basis": result.revision.volume_basis,
    }
