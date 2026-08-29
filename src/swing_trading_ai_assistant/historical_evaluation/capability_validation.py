"""Capability-aware historical validation and pre-Market-Structure gate V1."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, cast

from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    read_runtime_source,
)

from .capability_validation_runtime_identity_manifest import (
    CAPABILITY_VALIDATION_RUNTIME_SOURCE_SHA256_V1,
)

CONTRACT_VERSION_V1: Final = "capability-aware-historical-validation-gate@v1"
MAX_MEMBERS_V1: Final = 50
MIN_DECISION_POINTS_V1: Final = 4
MAX_DECISION_POINTS_V1: Final = 366
MAX_LEDGER_ENTRIES_V1: Final = 73_200
MAX_REQUEST_BYTES_V1: Final = 64 * 1024 * 1024
MAX_REPORT_BYTES_V1: Final = 4 * 1024 * 1024
_LIMITATION: Final = "FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ISIN = re.compile(r"[A-Z0-9]{12}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}\Z")
_EFFECTIVE_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.&_-]{0,31}\Z")


class HistoricalValidationRuntimeIdentityError(RuntimeError):
    """Raised when the installed Sprint-16 source inventory is not exact."""


class AvailabilityStateV1(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_PUBLISHED = "NOT_PUBLISHED"
    NOT_RETAINED = "NOT_RETAINED"
    SOURCE_GAP = "SOURCE_GAP"
    STALE = "STALE"
    CONFLICTED = "CONFLICTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNLICENSED = "UNLICENSED"


class HistoricalStudyProfileV1(StrEnum):
    OHLCV_ONLY = "OHLCV_ONLY"
    OHLCV_PLUS_SECTOR = "OHLCV_PLUS_SECTOR"
    OHLCV_PLUS_NEWS_EVENTS = "OHLCV_PLUS_NEWS_EVENTS"


class HistoricalEvidenceFeatureV1(StrEnum):
    DAILY_OHLCV = "DAILY_OHLCV"
    CORPORATE_ACTION_COMPARABILITY = "CORPORATE_ACTION_COMPARABILITY"
    SECTOR_CLASSIFICATION = "SECTOR_CLASSIFICATION"
    NEWS_EVENTS = "NEWS_EVENTS"


class HistoricalStudyRegionV1(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"
    OUT_OF_SAMPLE = "OUT_OF_SAMPLE"
    UNTOUCHED_TEST = "UNTOUCHED_TEST"
    WALK_FORWARD = "WALK_FORWARD"


class ProfileQualificationOutcomeV1(StrEnum):
    QUALIFIED = "QUALIFIED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"


class MarketStructureReadinessGateV1(StrEnum):
    APPROVED_TO_START_MARKET_STRUCTURE = "APPROVED_TO_START_MARKET_STRUCTURE"
    BLOCKED = "BLOCKED"


class HistoricalValidationReasonV1(StrEnum):
    EVIDENCE_REVISION_UNAVAILABLE = "EVIDENCE_REVISION_UNAVAILABLE"
    EVIDENCE_REVISION_IDENTITY_MISMATCH = "EVIDENCE_REVISION_IDENTITY_MISMATCH"
    COHORT_IDENTITY_MISMATCH = "COHORT_IDENTITY_MISMATCH"
    DECISION_GRID_MISMATCH = "DECISION_GRID_MISMATCH"
    REVISION_NOT_POINT_IN_TIME = "REVISION_NOT_POINT_IN_TIME"
    COMPARABILITY_EVIDENCE_NOT_PROVEN = "COMPARABILITY_EVIDENCE_NOT_PROVEN"
    FUTURE_KNOWN_EVIDENCE = "FUTURE_KNOWN_EVIDENCE"
    EVIDENCE_REVISION_SUBSTITUTION = "EVIDENCE_REVISION_SUBSTITUTION"
    BAR_KNOWN_TIME_MISMATCH = "BAR_KNOWN_TIME_MISMATCH"
    AVAILABILITY_LEDGER_INCOMPLETE = "AVAILABILITY_LEDGER_INCOMPLETE"
    EVIDENCE_CAPABILITY_UNSUPPORTED = "EVIDENCE_CAPABILITY_UNSUPPORTED"
    EVIDENCE_UNLICENSED = "EVIDENCE_UNLICENSED"
    EVIDENCE_CONFLICTED = "EVIDENCE_CONFLICTED"
    EVIDENCE_STALE = "EVIDENCE_STALE"
    EVIDENCE_NOT_PUBLISHED = "EVIDENCE_NOT_PUBLISHED"
    EVIDENCE_NOT_RETAINED = "EVIDENCE_NOT_RETAINED"
    EVIDENCE_SOURCE_GAP = "EVIDENCE_SOURCE_GAP"
    COVERAGE_BELOW_PREDECLARED_THRESHOLD = "COVERAGE_BELOW_PREDECLARED_THRESHOLD"
    GATE_COVERAGE_THRESHOLD_BELOW_100_PERCENT = (
        "GATE_COVERAGE_THRESHOLD_BELOW_100_PERCENT"
    )
    OHLCV_ONLY_NOT_QUALIFIED = "OHLCV_ONLY_NOT_QUALIFIED"


_PROFILE_FEATURES: Final = {
    HistoricalStudyProfileV1.OHLCV_ONLY: (
        HistoricalEvidenceFeatureV1.DAILY_OHLCV,
        HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY,
    ),
    HistoricalStudyProfileV1.OHLCV_PLUS_SECTOR: (
        HistoricalEvidenceFeatureV1.DAILY_OHLCV,
        HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY,
        HistoricalEvidenceFeatureV1.SECTOR_CLASSIFICATION,
    ),
    HistoricalStudyProfileV1.OHLCV_PLUS_NEWS_EVENTS: (
        HistoricalEvidenceFeatureV1.DAILY_OHLCV,
        HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY,
        HistoricalEvidenceFeatureV1.NEWS_EVENTS,
    ),
}
_STATE_REASON: Final = {
    AvailabilityStateV1.NOT_PUBLISHED: HistoricalValidationReasonV1.EVIDENCE_NOT_PUBLISHED,
    AvailabilityStateV1.NOT_RETAINED: HistoricalValidationReasonV1.EVIDENCE_NOT_RETAINED,
    AvailabilityStateV1.SOURCE_GAP: HistoricalValidationReasonV1.EVIDENCE_SOURCE_GAP,
    AvailabilityStateV1.STALE: HistoricalValidationReasonV1.EVIDENCE_STALE,
    AvailabilityStateV1.CONFLICTED: HistoricalValidationReasonV1.EVIDENCE_CONFLICTED,
    AvailabilityStateV1.UNSUPPORTED: (
        HistoricalValidationReasonV1.EVIDENCE_CAPABILITY_UNSUPPORTED
    ),
    AvailabilityStateV1.UNLICENSED: HistoricalValidationReasonV1.EVIDENCE_UNLICENSED,
}
_FATAL_PROFILE_REASONS: Final = frozenset(
    {
        HistoricalValidationReasonV1.REVISION_NOT_POINT_IN_TIME,
        HistoricalValidationReasonV1.COMPARABILITY_EVIDENCE_NOT_PROVEN,
        HistoricalValidationReasonV1.FUTURE_KNOWN_EVIDENCE,
        HistoricalValidationReasonV1.EVIDENCE_REVISION_SUBSTITUTION,
        HistoricalValidationReasonV1.BAR_KNOWN_TIME_MISMATCH,
        HistoricalValidationReasonV1.AVAILABILITY_LEDGER_INCOMPLETE,
        HistoricalValidationReasonV1.EVIDENCE_CAPABILITY_UNSUPPORTED,
        HistoricalValidationReasonV1.EVIDENCE_UNLICENSED,
        HistoricalValidationReasonV1.EVIDENCE_CONFLICTED,
    }
)
_FEATURE_INTERVAL: Final = {
    HistoricalEvidenceFeatureV1.DAILY_OHLCV: "1d",
    HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY: "1d",
    HistoricalEvidenceFeatureV1.SECTOR_CLASSIFICATION: "as_of",
    HistoricalEvidenceFeatureV1.NEWS_EVENTS: "as_of",
}


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


def _utc(value: datetime, field_name: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None:
        raise ValueError(f"{field_name} must be an aware instant")
    try:
        result = value.astimezone(UTC)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an aware instant") from exc
    return result


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _instant(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError("instant is invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("instant is invalid") from exc
    return _utc(parsed, "instant")


def _date(value: object) -> date:
    if type(value) is not str or len(value) != 10:
        raise ValueError("date is invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date is invalid") from exc
    if parsed.isoformat() != value:
        raise ValueError("date is invalid")
    return parsed


def _reason_tuple(
    reasons: set[HistoricalValidationReasonV1],
) -> tuple[HistoricalValidationReasonV1, ...]:
    return tuple(reason for reason in HistoricalValidationReasonV1 if reason in reasons)


@dataclass(frozen=True, slots=True, order=True)
class CanonicalEquityV1:
    isin: str
    exchange: str
    effective_symbol: str
    symbol_history_identity_sha256: str
    provider_mapping_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.isin) is not str
            or _ISIN.fullmatch(self.isin) is None
            or not _valid_token(self.exchange)
            or _EFFECTIVE_SYMBOL.fullmatch(self.effective_symbol) is None
            or not _valid_digest(self.symbol_history_identity_sha256)
            or not _valid_digest(self.provider_mapping_identity_sha256)
        ):
            raise ValueError("canonical equity is invalid")

    def canonical_value(self) -> dict[str, str]:
        return {
            "effective_symbol": self.effective_symbol,
            "exchange": self.exchange,
            "isin": self.isin,
            "provider_mapping_identity_sha256": (self.provider_mapping_identity_sha256),
            "symbol_history_identity_sha256": self.symbol_history_identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class HistoricalDecisionPointV1:
    session: date
    decision_cutoff: datetime
    region: HistoricalStudyRegionV1

    def __post_init__(self) -> None:
        if type(self.session) is not date:
            raise ValueError("decision point is invalid")
        object.__setattr__(
            self, "decision_cutoff", _utc(self.decision_cutoff, "decision_cutoff")
        )
        if type(self.region) is not HistoricalStudyRegionV1:
            raise ValueError("decision point is invalid")

    def canonical_value(self) -> dict[str, str]:
        return {
            "decision_cutoff": _timestamp(self.decision_cutoff),
            "region": self.region.value,
            "session": self.session.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class HistoricalBarKnowledgeV1:
    member: CanonicalEquityV1
    session: date
    known_at: datetime

    def __post_init__(self) -> None:
        if type(self.member) is not CanonicalEquityV1:
            raise ValueError("bar knowledge is invalid")
        if type(self.session) is not date:
            raise ValueError("bar knowledge is invalid")
        object.__setattr__(self, "known_at", _utc(self.known_at, "known_at"))

    def canonical_value(self) -> dict[str, object]:
        return {
            "known_at": _timestamp(self.known_at),
            "member": self.member.canonical_value(),
            "session": self.session.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class HistoricalComparabilityProvenanceV1:
    member: CanonicalEquityV1
    session: date
    source_identity_sha256: str
    classification_receipt_sha256: str
    evidence_revision_sha256: str
    published_at: datetime
    known_at: datetime

    def __post_init__(self) -> None:
        if type(self.member) is not CanonicalEquityV1 or type(self.session) is not date:
            raise ValueError("comparability provenance is invalid")
        if not all(
            _valid_digest(value)
            for value in (
                self.source_identity_sha256,
                self.classification_receipt_sha256,
                self.evidence_revision_sha256,
            )
        ):
            raise ValueError("comparability provenance is invalid")
        published_at = _utc(self.published_at, "published_at")
        known_at = _utc(self.known_at, "known_at")
        if published_at > known_at:
            raise ValueError("comparability provenance is invalid")
        object.__setattr__(self, "published_at", published_at)
        object.__setattr__(self, "known_at", known_at)

    @property
    def key(self) -> tuple[CanonicalEquityV1, date]:
        return self.member, self.session

    def canonical_value(self) -> dict[str, object]:
        return {
            "classification_receipt_sha256": self.classification_receipt_sha256,
            "evidence_revision_sha256": self.evidence_revision_sha256,
            "known_at": _timestamp(self.known_at),
            "member": self.member.canonical_value(),
            "published_at": _timestamp(self.published_at),
            "session": self.session.isoformat(),
            "source_identity_sha256": self.source_identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class HistoricalEvidenceRevisionV1:
    revision_contract_version: str
    revision_sha256: str
    cohort: tuple[CanonicalEquityV1, ...]
    sessions: tuple[date, ...]
    interval: str
    source_profile: str
    price_basis: str
    temporal_status: str
    corporate_action_status: str
    comparability_status: str
    permitted_use: str
    bars: tuple[HistoricalBarKnowledgeV1, ...]
    comparability_provenance: tuple[HistoricalComparabilityProvenanceV1, ...]
    source_identity_sha256: str
    schema_identity_sha256: str
    runtime_code_identity_sha256: str
    configuration_identity_sha256: str
    limitation: str
    cohort_identity_sha256: str = field(init=False)
    evidence_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.cohort) is not tuple
            or any(type(member) is not CanonicalEquityV1 for member in self.cohort)
            or type(self.sessions) is not tuple
            or any(type(session) is not date for session in self.sessions)
            or type(self.bars) is not tuple
            or any(type(bar) is not HistoricalBarKnowledgeV1 for bar in self.bars)
            or type(self.comparability_provenance) is not tuple
            or any(
                type(provenance) is not HistoricalComparabilityProvenanceV1
                for provenance in self.comparability_provenance
            )
        ):
            raise ValueError("historical evidence revision is invalid")
        token_values = (
            self.revision_contract_version,
            self.interval,
            self.source_profile,
            self.price_basis,
            self.temporal_status,
            self.corporate_action_status,
            self.comparability_status,
            self.permitted_use,
        )
        if self.interval != "1d" or not all(
            _valid_token(value) for value in token_values
        ):
            raise ValueError("historical evidence revision is invalid")
        if not _valid_digest(self.revision_sha256) or not all(
            _valid_digest(value)
            for value in (
                self.source_identity_sha256,
                self.schema_identity_sha256,
                self.runtime_code_identity_sha256,
                self.configuration_identity_sha256,
            )
        ):
            raise ValueError("historical evidence revision is invalid")
        if self.limitation != _LIMITATION:
            raise ValueError("historical evidence revision is invalid")
        if (
            not 1 <= len(self.cohort) <= MAX_MEMBERS_V1
            or self.cohort != tuple(sorted(self.cohort))
            or len(set(self.cohort)) != len(self.cohort)
        ):
            raise ValueError("historical evidence revision is invalid")
        if (
            not MIN_DECISION_POINTS_V1 <= len(self.sessions) <= MAX_DECISION_POINTS_V1
            or self.sessions != tuple(sorted(self.sessions))
            or len(set(self.sessions)) != len(self.sessions)
        ):
            raise ValueError("historical evidence revision is invalid")
        expected_keys = tuple(
            (member, session) for member in self.cohort for session in self.sessions
        )
        actual_keys = tuple((bar.member, bar.session) for bar in self.bars)
        if actual_keys != expected_keys:
            raise ValueError("historical evidence revision is invalid")
        expected_comparability_keys = tuple(
            (member, session) for member in self.cohort for session in self.sessions
        )
        actual_comparability_keys = tuple(
            provenance.key for provenance in self.comparability_provenance
        )
        comparability_proven = (
            self.corporate_action_status == "EVALUATED"
            and self.comparability_status == "ESTABLISHED"
        )
        if (
            comparability_proven
            and actual_comparability_keys != expected_comparability_keys
        ) or (not comparability_proven and self.comparability_provenance):
            raise ValueError("historical evidence revision is invalid")
        cohort_identity = _sha(
            _canonical([member.canonical_value() for member in self.cohort])
        )
        object.__setattr__(self, "cohort_identity_sha256", cohort_identity)
        object.__setattr__(
            self,
            "evidence_identity_sha256",
            _sha(_canonical(self.canonical_value(include_evidence_identity=False))),
        )

    def canonical_value(
        self, *, include_evidence_identity: bool = True
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "bars": [bar.canonical_value() for bar in self.bars],
            "comparability_provenance": [
                provenance.canonical_value()
                for provenance in self.comparability_provenance
            ],
            "cohort": [member.canonical_value() for member in self.cohort],
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "comparability_status": self.comparability_status,
            "configuration_identity_sha256": self.configuration_identity_sha256,
            "corporate_action_status": self.corporate_action_status,
            "interval": self.interval,
            "limitation": self.limitation,
            "permitted_use": self.permitted_use,
            "price_basis": self.price_basis,
            "revision_contract_version": self.revision_contract_version,
            "revision_sha256": self.revision_sha256,
            "runtime_code_identity_sha256": self.runtime_code_identity_sha256,
            "schema_identity_sha256": self.schema_identity_sha256,
            "sessions": [session.isoformat() for session in self.sessions],
            "source_identity_sha256": self.source_identity_sha256,
            "source_profile": self.source_profile,
            "temporal_status": self.temporal_status,
        }
        if include_evidence_identity:
            value["evidence_identity_sha256"] = self.evidence_identity_sha256
        return value


@dataclass(frozen=True, slots=True)
class HistoricalAvailabilityEntryV1:
    feature: HistoricalEvidenceFeatureV1
    member: CanonicalEquityV1
    session: date
    interval: str
    decision_cutoff: datetime
    state: AvailabilityStateV1
    source_identity_sha256: str
    classification_receipt_sha256: str
    evidence_revision_sha256: str | None
    published_at: datetime | None
    known_at: datetime | None
    affected_identity_sha256: str = field(init=False)
    entry_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:  # noqa: C901 - closed state boundary
        if (
            type(self.feature) is not HistoricalEvidenceFeatureV1
            or type(self.state) is not AvailabilityStateV1
        ):
            raise ValueError("availability entry is invalid")
        if type(self.member) is not CanonicalEquityV1:
            raise ValueError("availability entry is invalid")
        if type(self.session) is not date:
            raise ValueError("availability entry is invalid")
        if self.interval != _FEATURE_INTERVAL[self.feature]:
            raise ValueError("availability entry is invalid")
        if not _valid_digest(self.source_identity_sha256) or not _valid_digest(
            self.classification_receipt_sha256
        ):
            raise ValueError("availability entry is invalid")
        cutoff = _utc(self.decision_cutoff, "decision_cutoff")
        object.__setattr__(self, "decision_cutoff", cutoff)
        available_or_stale = self.state in {
            AvailabilityStateV1.AVAILABLE,
            AvailabilityStateV1.STALE,
        }
        selected_revision = (
            available_or_stale or self.state is AvailabilityStateV1.CONFLICTED
        )
        if selected_revision != (self.evidence_revision_sha256 is not None):
            raise ValueError("availability entry is invalid")
        if self.evidence_revision_sha256 is not None and not _valid_digest(
            self.evidence_revision_sha256
        ):
            raise ValueError("availability entry is invalid")
        if available_or_stale != (
            self.published_at is not None and self.known_at is not None
        ):
            raise ValueError("availability entry is invalid")
        if not available_or_stale and (
            self.published_at is not None or self.known_at is not None
        ):
            raise ValueError("availability entry is invalid")
        if self.published_at is not None and self.known_at is not None:
            published = _utc(self.published_at, "published_at")
            known = _utc(self.known_at, "known_at")
            if published > known:
                raise ValueError("availability entry is invalid")
            object.__setattr__(self, "published_at", published)
            object.__setattr__(self, "known_at", known)
        affected = _sha(
            _canonical(
                {
                    "feature": self.feature.value,
                    "interval": self.interval,
                    "member": self.member.canonical_value(),
                    "session": self.session.isoformat(),
                }
            )
        )
        object.__setattr__(self, "affected_identity_sha256", affected)
        object.__setattr__(
            self,
            "entry_identity_sha256",
            _sha(_canonical(self.canonical_value(include_entry_identity=False))),
        )

    @property
    def key(self) -> tuple[HistoricalEvidenceFeatureV1, CanonicalEquityV1, date]:
        return self.feature, self.member, self.session

    def canonical_value(
        self, *, include_entry_identity: bool = True
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "affected_identity_sha256": self.affected_identity_sha256,
            "classification_receipt_sha256": self.classification_receipt_sha256,
            "decision_cutoff": _timestamp(self.decision_cutoff),
            "evidence_revision_sha256": self.evidence_revision_sha256,
            "feature": self.feature.value,
            "interval": self.interval,
            "known_at": None if self.known_at is None else _timestamp(self.known_at),
            "member": self.member.canonical_value(),
            "published_at": (
                None if self.published_at is None else _timestamp(self.published_at)
            ),
            "session": self.session.isoformat(),
            "source_identity_sha256": self.source_identity_sha256,
            "state": self.state.value,
        }
        if include_entry_identity:
            value["entry_identity_sha256"] = self.entry_identity_sha256
        return value


@dataclass(frozen=True, slots=True)
class HistoricalStudyDeclarationV1:
    profile: HistoricalStudyProfileV1
    minimum_coverage_bps: int
    declaration_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.profile) is not HistoricalStudyProfileV1 or (
            type(self.minimum_coverage_bps) is not int
            or not 1 <= self.minimum_coverage_bps <= 10_000
        ):
            raise ValueError("study declaration is invalid")
        object.__setattr__(
            self,
            "declaration_identity_sha256",
            _sha(_canonical(self.canonical_value(include_identity=False))),
        )

    def canonical_value(self, *, include_identity: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "minimum_coverage_bps": self.minimum_coverage_bps,
            "profile": self.profile.value,
        }
        if include_identity:
            value["declaration_identity_sha256"] = self.declaration_identity_sha256
        return value


_SCHEMA_IDENTITY_SHA256: Final = _sha(
    _canonical(
        {
            "contract": CONTRACT_VERSION_V1,
            "fields": {
                "availability_entry": [
                    "feature",
                    "member",
                    "session",
                    "interval",
                    "decision_cutoff",
                    "state",
                    "source_identity_sha256",
                    "classification_receipt_sha256",
                    "evidence_revision_sha256",
                    "published_at",
                    "known_at",
                    "affected_identity_sha256",
                    "entry_identity_sha256",
                ],
                "canonical_equity": [
                    "isin",
                    "exchange",
                    "effective_symbol",
                    "symbol_history_identity_sha256",
                    "provider_mapping_identity_sha256",
                ],
                "decision_point": ["session", "decision_cutoff", "region"],
                "study": [
                    "profile",
                    "minimum_coverage_bps",
                    "declaration_identity_sha256",
                ],
            },
        }
    )
)
_CONFIGURATION_IDENTITY_SHA256: Final = _sha(
    _canonical(
        {
            "bounds": {
                "max_decision_points": MAX_DECISION_POINTS_V1,
                "max_ledger_entries": MAX_LEDGER_ENTRIES_V1,
                "max_members": MAX_MEMBERS_V1,
                "max_report_bytes": MAX_REPORT_BYTES_V1,
                "max_request_bytes": MAX_REQUEST_BYTES_V1,
                "min_decision_points": MIN_DECISION_POINTS_V1,
            },
            "features": {
                profile.value: [feature.value for feature in features]
                for profile, features in _PROFILE_FEATURES.items()
            },
            "reason_order": [reason.value for reason in HistoricalValidationReasonV1],
            "region_order": [region.value for region in HistoricalStudyRegionV1],
        }
    )
)

_PACKAGE_INITIALIZER_RELATIVE: Final = "src/swing_trading_ai_assistant/__init__.py"


def _read_manifest_source(root: Path, relative: str) -> bytes:
    if relative == _PACKAGE_INITIALIZER_RELATIVE:
        return read_runtime_source(
            root.parent,
            "src/swing_trading_ai_assistant/swing_trading_ai_assistant/__init__.py",
        )
    return read_runtime_source(root, relative)


def _runtime_root() -> Path:
    source = Path(__file__)
    root = source.parent.parent
    if not source.is_absolute() or root.name != "swing_trading_ai_assistant":
        raise ValueError("historical validation runtime identity invalid")
    return root


def _loaded_runtime_code_identity() -> str:
    try:
        root = _runtime_root()
        pairs: list[tuple[str, str]] = []
        for relative, expected in sorted(
            CAPABILITY_VALIDATION_RUNTIME_SOURCE_SHA256_V1.items()
        ):
            actual = _sha(_read_manifest_source(root, relative))
            if actual != expected:
                raise ValueError
            pairs.append((relative, actual))
        return _sha(_canonical(pairs))
    except (OSError, ValueError):
        raise HistoricalValidationRuntimeIdentityError(
            "historical validation runtime identity invalid"
        ) from None


@cache
def _cached_runtime_code_identity() -> str:
    return _loaded_runtime_code_identity()


def capability_validation_current_identities_v1() -> tuple[str, str, str]:
    """Return schema, runtime, and configuration identities for V1 requests."""

    return (
        _SCHEMA_IDENTITY_SHA256,
        _cached_runtime_code_identity(),
        _CONFIGURATION_IDENTITY_SHA256,
    )


def _entry_order(
    entry: HistoricalAvailabilityEntryV1,
) -> tuple[date, int, str, str]:
    return (
        entry.session,
        tuple(HistoricalEvidenceFeatureV1).index(entry.feature),
        entry.member.isin,
        entry.member.exchange,
    )


@dataclass(frozen=True, slots=True)
class HistoricalValidationRequestV1:
    contract_version: str
    evaluated_at: datetime
    evidence_revision_sha256: str
    cohort_identity_sha256: str
    cohort: tuple[CanonicalEquityV1, ...]
    decision_points: tuple[HistoricalDecisionPointV1, ...]
    studies: tuple[HistoricalStudyDeclarationV1, ...]
    availability_ledger: tuple[HistoricalAvailabilityEntryV1, ...]
    schema_identity_sha256: str
    runtime_code_identity_sha256: str
    configuration_identity_sha256: str
    ledger_identity_sha256: str = field(init=False)
    request_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:  # noqa: C901 - closed request boundary
        if (
            type(self.cohort) is not tuple
            or any(type(member) is not CanonicalEquityV1 for member in self.cohort)
            or type(self.decision_points) is not tuple
            or any(
                type(point) is not HistoricalDecisionPointV1
                for point in self.decision_points
            )
            or type(self.studies) is not tuple
            or any(
                type(study) is not HistoricalStudyDeclarationV1
                for study in self.studies
            )
            or type(self.availability_ledger) is not tuple
            or any(
                type(entry) is not HistoricalAvailabilityEntryV1
                for entry in self.availability_ledger
            )
        ):
            raise ValueError("validation request is invalid")
        if self.contract_version != CONTRACT_VERSION_V1:
            raise ValueError("validation request is invalid")
        evaluated = _utc(self.evaluated_at, "evaluated_at")
        object.__setattr__(self, "evaluated_at", evaluated)
        if not all(
            _valid_digest(value)
            for value in (
                self.evidence_revision_sha256,
                self.cohort_identity_sha256,
                self.schema_identity_sha256,
                self.runtime_code_identity_sha256,
                self.configuration_identity_sha256,
            )
        ):
            raise ValueError("validation request is invalid")
        if (
            not 1 <= len(self.cohort) <= MAX_MEMBERS_V1
            or self.cohort != tuple(sorted(self.cohort))
            or len(set(self.cohort)) != len(self.cohort)
            or _sha(_canonical([member.canonical_value() for member in self.cohort]))
            != self.cohort_identity_sha256
        ):
            raise ValueError("cohort identity mismatch")
        if (
            not MIN_DECISION_POINTS_V1
            <= len(self.decision_points)
            <= MAX_DECISION_POINTS_V1
        ):
            raise ValueError("decision regions are invalid")
        sessions = tuple(point.session for point in self.decision_points)
        if sessions != tuple(sorted(sessions)) or len(set(sessions)) != len(sessions):
            raise ValueError("decision regions are invalid")
        if any(point.decision_cutoff > evaluated for point in self.decision_points):
            raise ValueError("decision regions are invalid")
        region_runs: list[HistoricalStudyRegionV1] = []
        for point in self.decision_points:
            if not region_runs or region_runs[-1] is not point.region:
                region_runs.append(point.region)
        if tuple(region_runs) != tuple(HistoricalStudyRegionV1):
            raise ValueError("decision regions are invalid")
        if tuple(study.profile for study in self.studies) != tuple(
            HistoricalStudyProfileV1
        ):
            raise ValueError("study declarations are invalid")
        if len(self.availability_ledger) > MAX_LEDGER_ENTRIES_V1:
            raise ValueError("availability ledger is invalid")
        members = frozenset(self.cohort)
        point_cutoffs = {
            point.session: point.decision_cutoff for point in self.decision_points
        }
        if any(
            entry.member not in members
            or entry.decision_cutoff != point_cutoffs.get(entry.session)
            for entry in self.availability_ledger
        ):
            raise ValueError("availability ledger is invalid")
        keys = tuple(entry.key for entry in self.availability_ledger)
        if len(set(keys)) != len(keys) or self.availability_ledger != tuple(
            sorted(self.availability_ledger, key=_entry_order)
        ):
            raise ValueError("availability ledger is invalid")
        ledger_identity = _sha(
            _canonical([entry.canonical_value() for entry in self.availability_ledger])
        )
        object.__setattr__(self, "ledger_identity_sha256", ledger_identity)
        object.__setattr__(
            self,
            "request_identity_sha256",
            _sha(_canonical(self.canonical_value(include_request_identity=False))),
        )

    def canonical_value(
        self, *, include_request_identity: bool = True
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "availability_ledger": [
                entry.canonical_value() for entry in self.availability_ledger
            ],
            "cohort": [member.canonical_value() for member in self.cohort],
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "configuration_identity_sha256": self.configuration_identity_sha256,
            "contract_version": self.contract_version,
            "decision_points": [
                point.canonical_value() for point in self.decision_points
            ],
            "evaluated_at": _timestamp(self.evaluated_at),
            "evidence_revision_sha256": self.evidence_revision_sha256,
            "ledger_identity_sha256": self.ledger_identity_sha256,
            "runtime_code_identity_sha256": self.runtime_code_identity_sha256,
            "schema_identity_sha256": self.schema_identity_sha256,
            "studies": [study.canonical_value() for study in self.studies],
        }
        if include_request_identity:
            value["request_identity_sha256"] = self.request_identity_sha256
        return value

    def canonical_json_bytes(self) -> bytes:
        return _canonical_line(self.canonical_value())


def _reject_json_scalar(value: str) -> object:
    del value
    raise ValueError("unsupported JSON scalar")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _closed_object(value: object, fields: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError("closed object is invalid")
    result = cast(dict[str, object], value)
    if frozenset(result) != fields:
        raise ValueError("closed object is invalid")
    return result


def _json_rows(value: object, maximum: int) -> list[object]:
    if type(value) is not list:
        raise ValueError("JSON rows are invalid")
    result = cast(list[object], value)
    if len(result) > maximum:
        raise ValueError("JSON rows are invalid")
    return result


def _optional_instant(value: object) -> datetime | None:
    return None if value is None else _instant(value)


_CANONICAL_EQUITY_FIELDS: Final = frozenset(
    {
        "effective_symbol",
        "exchange",
        "isin",
        "provider_mapping_identity_sha256",
        "symbol_history_identity_sha256",
    }
)


def _canonical_equity_from_row(value: object) -> CanonicalEquityV1:
    row = _closed_object(value, _CANONICAL_EQUITY_FIELDS)
    return CanonicalEquityV1(
        isin=cast(str, row["isin"]),
        exchange=cast(str, row["exchange"]),
        effective_symbol=cast(str, row["effective_symbol"]),
        symbol_history_identity_sha256=cast(str, row["symbol_history_identity_sha256"]),
        provider_mapping_identity_sha256=cast(
            str, row["provider_mapping_identity_sha256"]
        ),
    )


def parse_historical_validation_request_v1(
    raw: object,
) -> HistoricalValidationRequestV1:
    """Parse one bounded canonical request and verify every supplied identity."""

    try:
        if type(raw) is not bytes or not raw or len(raw) > MAX_REQUEST_BYTES_V1:
            raise ValueError
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_float=_reject_json_scalar,
            parse_constant=_reject_json_scalar,
        )
        if raw != _canonical_line(value):
            raise ValueError
        request_row = _closed_object(
            value,
            frozenset(
                {
                    "availability_ledger",
                    "cohort",
                    "cohort_identity_sha256",
                    "configuration_identity_sha256",
                    "contract_version",
                    "decision_points",
                    "evaluated_at",
                    "evidence_revision_sha256",
                    "ledger_identity_sha256",
                    "request_identity_sha256",
                    "runtime_code_identity_sha256",
                    "schema_identity_sha256",
                    "studies",
                }
            ),
        )
        cohort = tuple(
            _canonical_equity_from_row(row)
            for row in _json_rows(request_row["cohort"], MAX_MEMBERS_V1)
        )
        points: list[HistoricalDecisionPointV1] = []
        for raw_point in _json_rows(
            request_row["decision_points"], MAX_DECISION_POINTS_V1
        ):
            point = _closed_object(
                raw_point,
                frozenset({"decision_cutoff", "region", "session"}),
            )
            points.append(
                HistoricalDecisionPointV1(
                    session=_date(point["session"]),
                    decision_cutoff=_instant(point["decision_cutoff"]),
                    region=HistoricalStudyRegionV1(point["region"]),
                )
            )
        studies: list[HistoricalStudyDeclarationV1] = []
        for raw_study in _json_rows(
            request_row["studies"], len(HistoricalStudyProfileV1)
        ):
            study = _closed_object(
                raw_study,
                frozenset(
                    {
                        "declaration_identity_sha256",
                        "minimum_coverage_bps",
                        "profile",
                    }
                ),
            )
            declaration = HistoricalStudyDeclarationV1(
                profile=HistoricalStudyProfileV1(study["profile"]),
                minimum_coverage_bps=cast(int, study["minimum_coverage_bps"]),
            )
            if (
                study["declaration_identity_sha256"]
                != declaration.declaration_identity_sha256
            ):
                raise ValueError
            studies.append(declaration)
        ledger: list[HistoricalAvailabilityEntryV1] = []
        entry_fields = frozenset(
            {
                "affected_identity_sha256",
                "classification_receipt_sha256",
                "decision_cutoff",
                "entry_identity_sha256",
                "evidence_revision_sha256",
                "feature",
                "interval",
                "known_at",
                "member",
                "published_at",
                "session",
                "source_identity_sha256",
                "state",
            }
        )
        for raw_entry in _json_rows(
            request_row["availability_ledger"], MAX_LEDGER_ENTRIES_V1
        ):
            entry_row = _closed_object(raw_entry, entry_fields)
            member = _canonical_equity_from_row(entry_row["member"])
            entry = HistoricalAvailabilityEntryV1(
                feature=HistoricalEvidenceFeatureV1(entry_row["feature"]),
                member=member,
                session=_date(entry_row["session"]),
                interval=cast(str, entry_row["interval"]),
                decision_cutoff=_instant(entry_row["decision_cutoff"]),
                state=AvailabilityStateV1(entry_row["state"]),
                source_identity_sha256=cast(str, entry_row["source_identity_sha256"]),
                classification_receipt_sha256=cast(
                    str, entry_row["classification_receipt_sha256"]
                ),
                evidence_revision_sha256=cast(
                    str | None, entry_row["evidence_revision_sha256"]
                ),
                published_at=_optional_instant(entry_row["published_at"]),
                known_at=_optional_instant(entry_row["known_at"]),
            )
            if (
                entry_row["affected_identity_sha256"] != entry.affected_identity_sha256
                or entry_row["entry_identity_sha256"] != entry.entry_identity_sha256
            ):
                raise ValueError
            ledger.append(entry)
        request = HistoricalValidationRequestV1(
            contract_version=cast(str, request_row["contract_version"]),
            evaluated_at=_instant(request_row["evaluated_at"]),
            evidence_revision_sha256=cast(str, request_row["evidence_revision_sha256"]),
            cohort_identity_sha256=cast(str, request_row["cohort_identity_sha256"]),
            cohort=cohort,
            decision_points=tuple(points),
            studies=tuple(studies),
            availability_ledger=tuple(ledger),
            schema_identity_sha256=cast(str, request_row["schema_identity_sha256"]),
            runtime_code_identity_sha256=cast(
                str, request_row["runtime_code_identity_sha256"]
            ),
            configuration_identity_sha256=cast(
                str, request_row["configuration_identity_sha256"]
            ),
        )
        validate_current_historical_validation_request_v1(request)
        if (
            request_row["ledger_identity_sha256"] != request.ledger_identity_sha256
            or request_row["request_identity_sha256"] != request.request_identity_sha256
            or request.canonical_json_bytes() != raw
        ):
            raise ValueError
        return request
    except (
        UnicodeDecodeError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        RecursionError,
    ):
        raise ValueError("historical validation request JSON is invalid") from None


@dataclass(frozen=True, slots=True)
class ProfileValidationResultV1:
    profile: HistoricalStudyProfileV1
    declaration_identity_sha256: str
    outcome: ProfileQualificationOutcomeV1
    total_required_cells: int
    available_cells: int
    missing_cells: int
    coverage_bps: int
    state_count_items: tuple[tuple[AvailabilityStateV1, int], ...]
    reasons: tuple[HistoricalValidationReasonV1, ...]
    result_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "result_identity_sha256",
            _sha(_canonical(self.canonical_value(include_result_identity=False))),
        )

    @property
    def state_counts(self) -> Mapping[AvailabilityStateV1, int]:
        return MappingProxyType(dict(self.state_count_items))

    def canonical_value(
        self, *, include_result_identity: bool = True
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "available_cells": self.available_cells,
            "coverage_bps": self.coverage_bps,
            "declaration_identity_sha256": self.declaration_identity_sha256,
            "missing_cells": self.missing_cells,
            "outcome": self.outcome.value,
            "profile": self.profile.value,
            "reasons": [reason.value for reason in self.reasons],
            "state_counts": {
                state.value: count for state, count in self.state_count_items
            },
            "total_required_cells": self.total_required_cells,
        }
        if include_result_identity:
            value["result_identity_sha256"] = self.result_identity_sha256
        return value


@dataclass(frozen=True, slots=True)
class HistoricalValidationReportV1:
    contract_version: str
    evaluated_at: datetime
    request_identity_sha256: str
    evidence_revision_sha256: str
    evidence_identity_sha256: str | None
    cohort_identity_sha256: str
    ledger_identity_sha256: str
    schema_identity_sha256: str
    runtime_code_identity_sha256: str
    configuration_identity_sha256: str
    evidence_source_profile: str | None
    evidence_price_basis: str | None
    evidence_temporal_status: str | None
    evidence_corporate_action_status: str | None
    evidence_comparability_status: str | None
    limitation: str
    profile_results: tuple[ProfileValidationResultV1, ...]
    gate: MarketStructureReadinessGateV1
    gate_reasons: tuple[HistoricalValidationReasonV1, ...]
    report_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "evaluated_at", _utc(self.evaluated_at, "evaluated_at")
        )
        object.__setattr__(
            self,
            "report_identity_sha256",
            _sha(_canonical(self.canonical_value(include_report_identity=False))),
        )
        if len(self.canonical_json_bytes()) > MAX_REPORT_BYTES_V1:
            raise ValueError("validation report is too large")

    def canonical_value(
        self, *, include_report_identity: bool = True
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "configuration_identity_sha256": self.configuration_identity_sha256,
            "contract_version": self.contract_version,
            "evaluated_at": _timestamp(self.evaluated_at),
            "evidence_comparability_status": self.evidence_comparability_status,
            "evidence_corporate_action_status": self.evidence_corporate_action_status,
            "evidence_identity_sha256": self.evidence_identity_sha256,
            "evidence_price_basis": self.evidence_price_basis,
            "evidence_revision_sha256": self.evidence_revision_sha256,
            "evidence_source_profile": self.evidence_source_profile,
            "evidence_temporal_status": self.evidence_temporal_status,
            "gate": self.gate.value,
            "gate_reasons": [reason.value for reason in self.gate_reasons],
            "ledger_identity_sha256": self.ledger_identity_sha256,
            "limitation": self.limitation,
            "profile_results": [
                result.canonical_value() for result in self.profile_results
            ],
            "request_identity_sha256": self.request_identity_sha256,
            "runtime_code_identity_sha256": self.runtime_code_identity_sha256,
            "schema_identity_sha256": self.schema_identity_sha256,
        }
        if include_report_identity:
            value["report_identity_sha256"] = self.report_identity_sha256
        return value

    def canonical_json_bytes(self) -> bytes:
        return _canonical_line(self.canonical_value())


def validate_current_historical_validation_request_v1(
    request: HistoricalValidationRequestV1,
) -> None:
    current = capability_validation_current_identities_v1()
    if (
        request.schema_identity_sha256,
        request.runtime_code_identity_sha256,
        request.configuration_identity_sha256,
    ) != current:
        raise ValueError("validation request identity mismatch")


def _validate_request_evidence_binding(
    request: HistoricalValidationRequestV1,
    evidence: HistoricalEvidenceRevisionV1,
) -> None:
    validate_current_historical_validation_request_v1(request)
    if request.evidence_revision_sha256 != evidence.revision_sha256:
        raise ValueError("evidence revision identity mismatch")
    if request.cohort_identity_sha256 != evidence.cohort_identity_sha256:
        raise ValueError("cohort identity mismatch")
    if request.cohort != evidence.cohort:
        raise ValueError("cohort identity mismatch")
    sessions = tuple(point.session for point in request.decision_points)
    if sessions != evidence.sessions:
        raise ValueError("decision grid mismatch")


def _availability_map(
    request: HistoricalValidationRequestV1,
    evidence: HistoricalEvidenceRevisionV1,
) -> dict[
    tuple[HistoricalEvidenceFeatureV1, CanonicalEquityV1, date],
    HistoricalAvailabilityEntryV1,
]:
    members = frozenset(evidence.cohort)
    points = {point.session: point for point in request.decision_points}
    result: dict[
        tuple[HistoricalEvidenceFeatureV1, CanonicalEquityV1, date],
        HistoricalAvailabilityEntryV1,
    ] = {}
    for entry in request.availability_ledger:
        point = points.get(entry.session)
        if (
            entry.member not in members
            or point is None
            or entry.decision_cutoff != point.decision_cutoff
        ):
            raise ValueError("availability ledger is invalid")
        result[entry.key] = entry
    return result


def _evaluate_profile(  # noqa: C901 - closed qualification reducer
    declaration: HistoricalStudyDeclarationV1,
    request: HistoricalValidationRequestV1,
    evidence: HistoricalEvidenceRevisionV1,
    entries: Mapping[
        tuple[HistoricalEvidenceFeatureV1, CanonicalEquityV1, date],
        HistoricalAvailabilityEntryV1,
    ],
    bar_known_at: Mapping[tuple[CanonicalEquityV1, date], datetime],
    comparability_provenance: Mapping[
        tuple[CanonicalEquityV1, date], HistoricalComparabilityProvenanceV1
    ],
) -> ProfileValidationResultV1:
    reasons: set[HistoricalValidationReasonV1] = set()
    counts = dict.fromkeys(AvailabilityStateV1, 0)
    features = _PROFILE_FEATURES[declaration.profile]
    if (
        HistoricalEvidenceFeatureV1.DAILY_OHLCV in features
        and evidence.temporal_status != "POINT_IN_TIME"
    ):
        reasons.add(HistoricalValidationReasonV1.REVISION_NOT_POINT_IN_TIME)
    total = len(evidence.cohort) * len(request.decision_points) * len(features)
    available = 0
    missing = 0
    for point in request.decision_points:
        for feature in features:
            for member in evidence.cohort:
                entry = entries.get((feature, member, point.session))
                if entry is None:
                    missing += 1
                    reasons.add(
                        HistoricalValidationReasonV1.AVAILABILITY_LEDGER_INCOMPLETE
                    )
                    if (
                        feature
                        is HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY
                        and (
                            evidence.corporate_action_status != "EVALUATED"
                            or evidence.comparability_status != "ESTABLISHED"
                        )
                    ):
                        reasons.add(
                            HistoricalValidationReasonV1.COMPARABILITY_EVIDENCE_NOT_PROVEN
                        )
                    continue
                counts[entry.state] += 1
                future_known = (
                    entry.known_at is not None
                    and entry.known_at > point.decision_cutoff
                )
                if future_known:
                    reasons.add(HistoricalValidationReasonV1.FUTURE_KNOWN_EVIDENCE)
                comparability_unproven = (
                    feature
                    is HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY
                    and (
                        evidence.corporate_action_status != "EVALUATED"
                        or evidence.comparability_status != "ESTABLISHED"
                    )
                )
                if comparability_unproven:
                    reasons.add(
                        HistoricalValidationReasonV1.COMPARABILITY_EVIDENCE_NOT_PROVEN
                    )
                comparability_provenance_mismatch = False
                if (
                    feature
                    is HistoricalEvidenceFeatureV1.CORPORATE_ACTION_COMPARABILITY
                    and entry.state
                    in {
                        AvailabilityStateV1.AVAILABLE,
                        AvailabilityStateV1.STALE,
                    }
                ):
                    provenance = comparability_provenance.get((member, point.session))
                    comparability_provenance_mismatch = provenance is None or (
                        entry.source_identity_sha256
                        != provenance.source_identity_sha256
                        or entry.classification_receipt_sha256
                        != provenance.classification_receipt_sha256
                        or entry.evidence_revision_sha256
                        != provenance.evidence_revision_sha256
                        or entry.published_at != provenance.published_at
                        or entry.known_at != provenance.known_at
                    )
                    if comparability_provenance_mismatch:
                        reasons.add(
                            HistoricalValidationReasonV1.EVIDENCE_REVISION_SUBSTITUTION
                        )
                if entry.state is not AvailabilityStateV1.AVAILABLE:
                    reasons.add(_STATE_REASON[entry.state])
                    continue
                valid = (
                    entry.known_at is not None
                    and not future_known
                    and not comparability_provenance_mismatch
                )
                if comparability_unproven:
                    valid = False
                if feature is HistoricalEvidenceFeatureV1.DAILY_OHLCV:
                    if (
                        entry.evidence_revision_sha256 != evidence.revision_sha256
                        or entry.source_identity_sha256
                        != evidence.source_identity_sha256
                    ):
                        reasons.add(
                            HistoricalValidationReasonV1.EVIDENCE_REVISION_SUBSTITUTION
                        )
                        valid = False
                    if evidence.temporal_status != "POINT_IN_TIME":
                        valid = False
                    stored_known = bar_known_at[(member, point.session)]
                    if entry.known_at != stored_known:
                        reasons.add(
                            HistoricalValidationReasonV1.BAR_KNOWN_TIME_MISMATCH
                        )
                        valid = False
                if valid:
                    available += 1
    coverage = (available * 10_000) // total
    if coverage < declaration.minimum_coverage_bps:
        reasons.add(HistoricalValidationReasonV1.COVERAGE_BELOW_PREDECLARED_THRESHOLD)
    fatal = any(reason in _FATAL_PROFILE_REASONS for reason in reasons)
    unsupported = counts[AvailabilityStateV1.UNSUPPORTED] > 0
    outcome = (
        ProfileQualificationOutcomeV1.UNSUPPORTED_CAPABILITY
        if unsupported
        else ProfileQualificationOutcomeV1.QUALIFIED
        if coverage >= declaration.minimum_coverage_bps and not fatal
        else ProfileQualificationOutcomeV1.INSUFFICIENT_EVIDENCE
    )
    return ProfileValidationResultV1(
        profile=declaration.profile,
        declaration_identity_sha256=declaration.declaration_identity_sha256,
        outcome=outcome,
        total_required_cells=total,
        available_cells=available,
        missing_cells=missing,
        coverage_bps=coverage,
        state_count_items=tuple(
            (state, counts[state]) for state in AvailabilityStateV1
        ),
        reasons=_reason_tuple(reasons),
    )


def build_blocked_historical_validation_report_v1(
    request: HistoricalValidationRequestV1,
    reason: HistoricalValidationReasonV1 = (
        HistoricalValidationReasonV1.EVIDENCE_REVISION_UNAVAILABLE
    ),
) -> HistoricalValidationReportV1:
    """Return a complete zero-claim report for one admitted blocking condition."""

    validate_current_historical_validation_request_v1(request)
    if reason not in {
        HistoricalValidationReasonV1.EVIDENCE_REVISION_UNAVAILABLE,
        HistoricalValidationReasonV1.EVIDENCE_REVISION_IDENTITY_MISMATCH,
        HistoricalValidationReasonV1.COHORT_IDENTITY_MISMATCH,
        HistoricalValidationReasonV1.DECISION_GRID_MISMATCH,
    }:
        raise ValueError("blocked report reason is invalid")
    results: list[ProfileValidationResultV1] = []
    for declaration in request.studies:
        total = (
            len(request.cohort)
            * len(request.decision_points)
            * len(_PROFILE_FEATURES[declaration.profile])
        )
        reasons = _reason_tuple(
            {
                reason,
                HistoricalValidationReasonV1.COVERAGE_BELOW_PREDECLARED_THRESHOLD,
            }
        )
        results.append(
            ProfileValidationResultV1(
                profile=declaration.profile,
                declaration_identity_sha256=declaration.declaration_identity_sha256,
                outcome=ProfileQualificationOutcomeV1.INSUFFICIENT_EVIDENCE,
                total_required_cells=total,
                available_cells=0,
                missing_cells=total,
                coverage_bps=0,
                state_count_items=tuple((state, 0) for state in AvailabilityStateV1),
                reasons=reasons,
            )
        )
    gate_reason_set = {
        reason,
        HistoricalValidationReasonV1.COVERAGE_BELOW_PREDECLARED_THRESHOLD,
        HistoricalValidationReasonV1.OHLCV_ONLY_NOT_QUALIFIED,
    }
    if request.studies[0].minimum_coverage_bps != 10_000:
        gate_reason_set.add(
            HistoricalValidationReasonV1.GATE_COVERAGE_THRESHOLD_BELOW_100_PERCENT
        )
    gate_reasons = _reason_tuple(gate_reason_set)
    return HistoricalValidationReportV1(
        contract_version=CONTRACT_VERSION_V1,
        evaluated_at=request.evaluated_at,
        request_identity_sha256=request.request_identity_sha256,
        evidence_revision_sha256=request.evidence_revision_sha256,
        evidence_identity_sha256=None,
        cohort_identity_sha256=request.cohort_identity_sha256,
        ledger_identity_sha256=request.ledger_identity_sha256,
        schema_identity_sha256=request.schema_identity_sha256,
        runtime_code_identity_sha256=request.runtime_code_identity_sha256,
        configuration_identity_sha256=request.configuration_identity_sha256,
        evidence_source_profile=None,
        evidence_price_basis=None,
        evidence_temporal_status=None,
        evidence_corporate_action_status=None,
        evidence_comparability_status=None,
        limitation=_LIMITATION,
        profile_results=tuple(results),
        gate=MarketStructureReadinessGateV1.BLOCKED,
        gate_reasons=gate_reasons,
    )


def evaluate_capability_aware_historical_validation_v1(
    request: HistoricalValidationRequestV1,
    evidence: HistoricalEvidenceRevisionV1,
) -> HistoricalValidationReportV1:
    """Qualify supplied immutable evidence without market calculations or effects."""

    _validate_request_evidence_binding(request, evidence)
    entries = _availability_map(request, evidence)
    bar_known_at = {(bar.member, bar.session): bar.known_at for bar in evidence.bars}
    comparability_provenance = {
        provenance.key: provenance for provenance in evidence.comparability_provenance
    }
    results = tuple(
        _evaluate_profile(
            study,
            request,
            evidence,
            entries,
            bar_known_at,
            comparability_provenance,
        )
        for study in request.studies
    )
    ohlcv_declaration = request.studies[0]
    ohlcv_result = results[0]
    gate_reasons: set[HistoricalValidationReasonV1] = set()
    if ohlcv_declaration.minimum_coverage_bps != 10_000:
        gate_reasons.add(
            HistoricalValidationReasonV1.GATE_COVERAGE_THRESHOLD_BELOW_100_PERCENT
        )
    if ohlcv_result.outcome is not ProfileQualificationOutcomeV1.QUALIFIED:
        gate_reasons.update(ohlcv_result.reasons)
        gate_reasons.add(HistoricalValidationReasonV1.OHLCV_ONLY_NOT_QUALIFIED)
    gate = (
        MarketStructureReadinessGateV1.APPROVED_TO_START_MARKET_STRUCTURE
        if not gate_reasons
        else MarketStructureReadinessGateV1.BLOCKED
    )
    return HistoricalValidationReportV1(
        contract_version=CONTRACT_VERSION_V1,
        evaluated_at=request.evaluated_at,
        request_identity_sha256=request.request_identity_sha256,
        evidence_revision_sha256=evidence.revision_sha256,
        evidence_identity_sha256=evidence.evidence_identity_sha256,
        cohort_identity_sha256=evidence.cohort_identity_sha256,
        ledger_identity_sha256=request.ledger_identity_sha256,
        schema_identity_sha256=request.schema_identity_sha256,
        runtime_code_identity_sha256=request.runtime_code_identity_sha256,
        configuration_identity_sha256=request.configuration_identity_sha256,
        evidence_source_profile=evidence.source_profile,
        evidence_price_basis=evidence.price_basis,
        evidence_temporal_status=evidence.temporal_status,
        evidence_corporate_action_status=evidence.corporate_action_status,
        evidence_comparability_status=evidence.comparability_status,
        limitation=evidence.limitation,
        profile_results=results,
        gate=gate,
        gate_reasons=_reason_tuple(gate_reasons),
    )


def _sprint15_canonical_equity(row: Mapping[str, Any]) -> CanonicalEquityV1:
    mapping_value: object = row["provider_mapping"]
    if type(mapping_value) is not dict:
        raise ValueError
    mapping = cast(dict[str, object], mapping_value)
    symbol_history: dict[str, object] = {
        "effective_symbol": row["effective_symbol"],
        "symbol_effective_from": row["symbol_effective_from"],
        "symbol_effective_to": row["symbol_effective_to"],
    }
    provider_mapping: dict[str, object] = {
        "contract_version": "sprint15-provider-mapping-projection@v1",
        "mapping": mapping,
    }
    return CanonicalEquityV1(
        isin=cast(str, row["isin"]),
        exchange=cast(str, row["exchange"]),
        effective_symbol=cast(str, row["effective_symbol"]),
        symbol_history_identity_sha256=_sha(_canonical(symbol_history)),
        provider_mapping_identity_sha256=_sha(_canonical(provider_mapping)),
    )


def historical_evidence_from_sprint15_revision_v1(
    revision: Mapping[str, Any],
) -> HistoricalEvidenceRevisionV1:
    """Project one already exact-read Sprint-15 revision without relabelling it."""

    try:
        value = dict(revision)
        revision_sha256 = cast(str, value["revision_sha256"])
        preimage = dict(value)
        preimage.pop("revision_sha256")
        if (
            not _valid_digest(revision_sha256)
            or _sha(_canonical(preimage)) != revision_sha256
        ):
            raise ValueError
        if (
            value["contract_version"]
            != "fixed-cohort-historical-ohlcv-upstox-raw-revision-store@v1"
            or value["research_scope"] != "FIXED_COHORT_RETROSPECTIVE"
            or value["source_profile"] != "UPSTOX_RAW"
            or value["interval"] != "1d"
            or value["price_basis"] != "RAW"
            or value["temporal_status"] != "REVISED_NON_PIT"
            or value["corporate_action_status"] != "NOT_EVALUATED"
            or value["comparability_status"] != "NOT_ESTABLISHED"
            or value["permitted_use"] != "OWNER_PRIVATE_RESEARCH"
            or value["context_status"] != "HISTORICAL_CONTEXT_NOT_EVALUATED"
            or value["limitation"] != _LIMITATION
        ):
            raise ValueError
        cohort_rows = cast(list[dict[str, Any]], value["cohort"])
        cohort = tuple(_sprint15_canonical_equity(row) for row in cohort_rows)
        member_by_key = {(member.isin, member.exchange): member for member in cohort}
        sessions = tuple(
            _date(item) for item in cast(list[object], value["expected_sessions"])
        )
        bars = tuple(
            HistoricalBarKnowledgeV1(
                member=member_by_key[
                    (cast(str, row["isin"]), cast(str, row["exchange"]))
                ],
                session=_date(row["session"]),
                known_at=_instant(row["known_at"]),
            )
            for row in cast(list[dict[str, Any]], value["bars"])
        )
        return HistoricalEvidenceRevisionV1(
            revision_contract_version=cast(str, value["contract_version"]),
            revision_sha256=revision_sha256,
            cohort=cohort,
            sessions=sessions,
            interval=cast(str, value["interval"]),
            source_profile=cast(str, value["source_profile"]),
            price_basis=cast(str, value["price_basis"]),
            temporal_status=cast(str, value["temporal_status"]),
            corporate_action_status=cast(str, value["corporate_action_status"]),
            comparability_status=cast(str, value["comparability_status"]),
            permitted_use=cast(str, value["permitted_use"]),
            bars=bars,
            comparability_provenance=(),
            source_identity_sha256=cast(str, value["source_policy_sha256"]),
            schema_identity_sha256=cast(str, value["schema_identity_sha256"]),
            runtime_code_identity_sha256=cast(
                str, value["runtime_code_identity_sha256"]
            ),
            configuration_identity_sha256=cast(
                str, value["configuration_identity_sha256"]
            ),
            limitation=cast(str, value["limitation"]),
        )
    except (KeyError, TypeError, ValueError):
        raise ValueError("Sprint 15 historical revision is invalid") from None


__all__ = [
    "AvailabilityStateV1",
    "CONTRACT_VERSION_V1",
    "CanonicalEquityV1",
    "HistoricalAvailabilityEntryV1",
    "HistoricalBarKnowledgeV1",
    "HistoricalComparabilityProvenanceV1",
    "HistoricalDecisionPointV1",
    "HistoricalEvidenceFeatureV1",
    "HistoricalEvidenceRevisionV1",
    "HistoricalStudyDeclarationV1",
    "HistoricalStudyProfileV1",
    "HistoricalStudyRegionV1",
    "HistoricalValidationReasonV1",
    "HistoricalValidationReportV1",
    "HistoricalValidationRuntimeIdentityError",
    "HistoricalValidationRequestV1",
    "MarketStructureReadinessGateV1",
    "ProfileQualificationOutcomeV1",
    "ProfileValidationResultV1",
    "capability_validation_current_identities_v1",
    "build_blocked_historical_validation_report_v1",
    "evaluate_capability_aware_historical_validation_v1",
    "historical_evidence_from_sprint15_revision_v1",
    "parse_historical_validation_request_v1",
    "validate_current_historical_validation_request_v1",
]
