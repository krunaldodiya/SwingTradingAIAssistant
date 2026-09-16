"""Closed public API for independent current raw price context (Issue #188)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, TypedDict, cast
from zoneinfo import ZoneInfo

from swing_trading_ai_assistant.market_data.current_industry_archive_reader import (
    AdmittedCurrentIndustryProjectionV1,
    CurrentIndustryReadFailureV1,
    admitted_current_industry_binding_v1,
    read_current_industry_archive_exact_v1,
)
from swing_trading_ai_assistant.market_data.current_industry_archive_reader import (
    CurrentIndustryArchiveReferenceV1 as ArchivedIndustryReferenceV1,
)
from swing_trading_ai_assistant.market_data.current_raw_acquisition import (
    acquire_missing_current_raw_evidence_v1,
)
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    AdmittedCurrentRawContextV1,
    CurrentPriceContextClockV1,
    CurrentPriceContextMemberV1,
    CurrentRawInvocationControlV1,
    CurrentRawPriceContextInputV1,
    is_valid_current_price_context_isin_v1,
    read_retained_current_raw_context_v1,
    recheck_retained_current_raw_context_v1,
    validate_admitted_current_raw_context_v1,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    StorageRootLease,
    StorageRootLeaseError,
)
from swing_trading_ai_assistant.market_regime.current_raw_price_context import (
    RawCohortBreadthV1,
)
from swing_trading_ai_assistant.market_structure.current_live import (
    CurrentMarketStructureMemberV1,
    MarketStructureEventV1,
    MarketStructurePivotV1,
)
from swing_trading_ai_assistant.research_packet.current_price_context_runtime_identity_manifest import (
    CURRENT_PRICE_CONTEXT_RUNTIME_SOURCE_SHA256_V1,
)
from swing_trading_ai_assistant.sector_analysis.current_raw_industry_participation import (
    CurrentRawIndustryGroupV1,
    reduce_current_raw_industry_participation_v1,
)

_REQUEST_CONTRACT = "current-price-context-request@v1"
_RESULT_CONTRACT = "current-price-context@v1"
_QUESTIONS = (
    "RAW_MARKET_STRUCTURE",
    "RAW_20_SESSION_DIRECTION",
    "RAW_COHORT_BREADTH",
    "RAW_INDUSTRY_PARTICIPATION",
)
_IST = ZoneInfo("Asia/Kolkata")
_MAX_REQUEST_BYTES = 64 * 1024
_MAX_RESULT_BYTES = 1_048_576
_LIMITATIONS = (
    "UPSTOX_RAW_ONLY",
    "RETAINED_EVIDENCE_REQUIRED",
    "CURRENT_MAPPING_SCOPE",
)
_MEMBER_REASON_STATES = {
    "CALENDAR_PREREQUISITE_MISSING": "DEPENDENCY_BLOCKED",
    "CALENDAR_FUTURE_KNOWN": "INSUFFICIENT_EVIDENCE",
    "COMPLETED_SESSION_WINDOW_UNAVAILABLE": "INSUFFICIENT_EVIDENCE",
    "CALENDAR_UNSUPPORTED": "UNSUPPORTED",
    "RAW_WINDOW_LIMIT_EXCEEDED": "UNSUPPORTED",
    "SCHEDULE_AUTHORITY_CHANGED": "INSUFFICIENT_EVIDENCE",
    "ACQUISITION_STOPPED": "DEPENDENCY_BLOCKED",
    "RAW_MAPPING_MISSING": "DEPENDENCY_BLOCKED",
    "RAW_MAPPING_UNSUPPORTED": "UNSUPPORTED",
    "RAW_MAPPING_STALE": "INSUFFICIENT_EVIDENCE",
    "RAW_MAPPING_CORRUPT": "INSUFFICIENT_EVIDENCE",
    "RAW_PARTITION_CORRUPT": "INSUFFICIENT_EVIDENCE",
    "RAW_BAR_MISSING": "INSUFFICIENT_EVIDENCE",
    "RAW_BAR_CONFLICTED": "INSUFFICIENT_EVIDENCE",
    "RAW_BAR_INVALID": "INSUFFICIENT_EVIDENCE",
    "SCREEN_UNAVAILABLE": "INSUFFICIENT_EVIDENCE",
    "ACTION_IN_WINDOW": "INSUFFICIENT_EVIDENCE",
}
_INDUSTRY_REASONS = frozenset(
    {
        "INDUSTRY_REFERENCE_NOT_PROVIDED",
        "INDUSTRY_NOT_ATTEMPTED",
        "MEMBER_DIRECTION_UNAVAILABLE",
        "UNSUPPORTED_CLASSIFICATION_SCHEMA",
        "CLASSIFICATION_ARCHIVE_MISSING",
        "CLASSIFICATION_ARCHIVE_MALFORMED",
        "CLASSIFICATION_ARCHIVE_SUBSTITUTED",
        "CLASSIFICATION_ARTIFACT_MISSING",
        "CLASSIFICATION_ARTIFACT_MALFORMED",
        "CLASSIFICATION_ARTIFACT_SUBSTITUTED",
        "CLASSIFICATION_COHORT_BINDING_MISMATCH",
        "CLASSIFICATION_FUTURE_KNOWN",
        "CLASSIFICATION_MARKER_SUBSTITUTED",
        "CLASSIFICATION_PROJECTION_SUBSTITUTED",
        "CLASSIFICATION_RECEIPT_SUBSTITUTED",
        "CLASSIFICATION_SNAPSHOT_SUBSTITUTED",
        "CLASSIFICATION_STALE",
    }
)


class _ResultBindingsV1(TypedDict):
    schema_identity_sha256: str
    calculation_identity_sha256: str
    configuration_identity_sha256: str
    schedule_identity_sha256: str
    ordered_selection_identity_sha256: str
    canonical_cohort_identity_sha256: str
    questions: tuple[str, ...]
    data_selection_time: datetime
    evidence_cutoff: datetime
    provider: Literal["UPSTOX"]
    price_basis: Literal["RAW"]
    bar_basis: Literal["1d-derived-from-retained-1m"]
    source_bindings_identity_sha256: str


def current_price_context_runtime_code_identity_v1() -> str:
    """Verify the reviewed source map before exposing a public result."""
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in CURRENT_PRICE_CONTEXT_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("current price context runtime identity is invalid")
        observed[relative] = actual
    return _digest_value(observed)


@dataclass(frozen=True, slots=True)
class CurrentIndustryArchiveReferenceV1:
    contract_version: Literal["current-industry-archive-reference@v1"]
    snapshot_identity_sha256: str
    retained_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            self.contract_version != "current-industry-archive-reference@v1"
            or not _digest(self.snapshot_identity_sha256)
            or not _digest(self.retained_identity_sha256)
        ):
            raise ValueError("current Industry archive reference is invalid")


@dataclass(frozen=True, slots=True)
class CurrentPriceContextRequestV1:
    contract_version: Literal["current-price-context-request@v1"]
    data_selection_time: datetime
    admission_deadline: datetime
    schedule_identity_sha256: str
    members: tuple[CurrentPriceContextMemberV1, ...]
    questions: tuple[
        Literal[
            "RAW_MARKET_STRUCTURE",
            "RAW_20_SESSION_DIRECTION",
            "RAW_COHORT_BREADTH",
            "RAW_INDUSTRY_PARTICIPATION",
        ],
        ...,
    ]
    industry_archive_reference: CurrentIndustryArchiveReferenceV1 | None
    request_identity_sha256: str = ""

    def __post_init__(self) -> None:
        if (
            self.contract_version != _REQUEST_CONTRACT
            or not _utc(self.data_selection_time)
            or not _utc(self.admission_deadline)
            or not self.data_selection_time < self.admission_deadline
            or self.admission_deadline - self.data_selection_time
            > timedelta(minutes=30)
            or self.data_selection_time.astimezone(_IST).date()
            != self.admission_deadline.astimezone(_IST).date()
            or not _digest(self.schedule_identity_sha256)
            or type(self.members) is not tuple
            or not 1 <= len(self.members) <= 50
            or any(
                type(member) is not CurrentPriceContextMemberV1
                for member in self.members
            )
            or len({member.isin for member in self.members}) != len(self.members)
            or len({member.effective_symbol for member in self.members})
            != len(self.members)
            or self.questions != _QUESTIONS
            or type(self.industry_archive_reference)
            not in (CurrentIndustryArchiveReferenceV1, type(None))
        ):
            raise ValueError("current price context request is invalid")
        identity = self.identity_of(self)
        if any(
            not member.valid_from
            <= self.data_selection_time.astimezone(_IST).date()
            <= member.valid_through
            for member in self.members
        ):
            raise ValueError("current price context member is not valid at selection")
        if self.request_identity_sha256 not in ("", identity):
            raise ValueError("current price context request identity is invalid")
        object.__setattr__(self, "request_identity_sha256", identity)
        if len(_canonical(_wire(_without_request_identity(self)))) > _MAX_REQUEST_BYTES:
            raise ValueError("current price context request exceeds its bound")

    @staticmethod
    def identity_of(value: CurrentPriceContextRequestV1) -> str:
        if type(value) is not CurrentPriceContextRequestV1:
            raise ValueError("current price context request is invalid")
        return _digest_value(
            {
                "contract_version": value.contract_version,
                "data_selection_time": value.data_selection_time,
                "admission_deadline": value.admission_deadline,
                "schedule_identity_sha256": value.schedule_identity_sha256,
                "members": value.members,
                "questions": value.questions,
                "industry_archive_reference": value.industry_archive_reference,
            }
        )


@dataclass(frozen=True, slots=True)
class CurrentPriceContextFeatureV1:
    question: str
    state: Literal[
        "OBSERVED",
        "UNSUPPORTED",
        "DEPENDENCY_BLOCKED",
        "INSUFFICIENT_EVIDENCE",
        "NOT_ATTEMPTED",
    ]
    reasons: tuple[str, ...]
    support: Literal["SUPPORTED", "UNSUPPORTED"] = "SUPPORTED"
    readiness: Literal["READY", "WITHHELD"] = "WITHHELD"

    def __post_init__(self) -> None:
        if (
            self.question not in _QUESTIONS
            or self.state
            not in (
                "OBSERVED",
                "UNSUPPORTED",
                "DEPENDENCY_BLOCKED",
                "INSUFFICIENT_EVIDENCE",
                "NOT_ATTEMPTED",
            )
            or type(self.reasons) is not tuple
            or any(type(reason) is not str or not reason for reason in self.reasons)
            or self.support not in ("SUPPORTED", "UNSUPPORTED")
            or self.readiness not in ("READY", "WITHHELD")
            or (
                self.state == "OBSERVED" and (self.reasons or self.readiness != "READY")
            )
            or (
                self.state != "OBSERVED"
                and (not self.reasons or self.readiness != "WITHHELD")
            )
            or (self.state == "UNSUPPORTED") != (self.support == "UNSUPPORTED")
        ):
            raise ValueError("current price context feature is invalid")


@dataclass(frozen=True, slots=True)
class CurrentPriceContextMemberResultV1:
    position: int
    isin: str
    exchange: Literal["NSE"]
    effective_symbol: str
    state: Literal[
        "OBSERVED", "UNSUPPORTED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE"
    ]
    reason: str | None
    structure: CurrentMarketStructureMemberV1 | None
    direction: Literal["ADVANCE", "DECLINE", "UNCHANGED"] | None
    mapping_observation_sha256: str | None
    mapping_retrieved_at: datetime | None
    partition_checksums: tuple[str, ...]
    raw_source_times: tuple[datetime, ...]
    screen_identity_sha256: str | None
    screen_knowledge_at: datetime | None

    def __post_init__(self) -> None:
        if (
            type(self.position) is not int
            or self.position < 0
            or type(self.isin) is not str
            or not is_valid_current_price_context_isin_v1(self.isin)
            or self.exchange != "NSE"
            or type(self.effective_symbol) is not str
            or not 1 <= len(self.effective_symbol) <= 64
            or any(
                char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.&_-"
                for char in self.effective_symbol
            )
            or not any(
                char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                for char in self.effective_symbol
            )
            or self.state
            not in (
                "OBSERVED",
                "UNSUPPORTED",
                "DEPENDENCY_BLOCKED",
                "INSUFFICIENT_EVIDENCE",
            )
            or (self.state == "OBSERVED") != (self.reason is None)
            or (
                self.reason is not None
                and (
                    type(self.reason) is not str
                    or self.reason not in _MEMBER_REASON_STATES
                    or _MEMBER_REASON_STATES[self.reason] != self.state
                )
            )
            or (self.structure is None) != (self.direction is None)
            or (self.state == "OBSERVED") != (self.structure is not None)
            or (
                self.structure is not None
                and type(self.structure) is not CurrentMarketStructureMemberV1
            )
            or (
                self.direction is not None
                and self.direction not in {"ADVANCE", "DECLINE", "UNCHANGED"}
            )
            or (
                self.mapping_retrieved_at is not None
                and not _utc(self.mapping_retrieved_at)
            )
            or type(self.partition_checksums) is not tuple
            or any(not _digest(item) for item in self.partition_checksums)
            or type(self.raw_source_times) is not tuple
            or any(not _utc(item) for item in self.raw_source_times)
            or (
                self.screen_knowledge_at is not None
                and not _utc(self.screen_knowledge_at)
            )
            or (
                self.mapping_observation_sha256 is not None
                and not _digest(self.mapping_observation_sha256)
            )
            or (
                (self.mapping_observation_sha256 is None)
                != (self.mapping_retrieved_at is None)
            )
            or len(self.partition_checksums) != len(self.raw_source_times)
            or (
                self.screen_identity_sha256 is not None
                and not _digest(self.screen_identity_sha256)
            )
            or (
                self.screen_identity_sha256 is not None
                and self.screen_knowledge_at is None
            )
            or (
                self.state == "OBSERVED"
                and (
                    self.mapping_observation_sha256 is None
                    or not 1 <= len(self.partition_checksums) <= 3
                    or self.screen_identity_sha256 is None
                    or self.screen_knowledge_at is None
                )
            )
            or (
                self.state != "OBSERVED"
                and (
                    self.structure is not None
                    or self.direction is not None
                    or self.mapping_observation_sha256 is not None
                    or self.mapping_retrieved_at is not None
                    or self.partition_checksums
                    or self.raw_source_times
                    or self.screen_identity_sha256 is not None
                    or (
                        self.screen_knowledge_at is not None
                        and self.reason != "ACTION_IN_WINDOW"
                    )
                )
            )
            or (
                self.reason == "ACTION_IN_WINDOW"
                and (
                    self.screen_identity_sha256 is not None
                    or self.screen_knowledge_at is None
                )
            )
        ):
            raise ValueError("current price context member result is invalid")


def _member_source_times_at_or_before(
    member: CurrentPriceContextMemberResultV1, cutoff: datetime
) -> bool:
    return all(
        value is None or value <= cutoff
        for value in (
            member.mapping_retrieved_at,
            member.screen_knowledge_at,
        )
    ) and all(value <= cutoff for value in member.raw_source_times)


@dataclass(frozen=True, slots=True)
class CurrentPriceContextBreadthV1:
    """Public complete-cohort accounting without raw bars or private receipts."""

    requested_count: int
    observed_count: int
    advances: int
    declines: int
    unchanged: int
    insufficient_count: int
    label: Literal["BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"] | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.requested_count) is not int
            or not 1 <= self.requested_count <= 50
            or any(
                type(value) is not int or value < 0
                for value in (
                    self.observed_count,
                    self.advances,
                    self.declines,
                    self.unchanged,
                    self.insufficient_count,
                )
            )
            or self.observed_count + self.insufficient_count != self.requested_count
            or self.advances + self.declines + self.unchanged != self.observed_count
            or type(self.reasons) is not tuple
            or any(type(reason) is not str or not reason for reason in self.reasons)
            or self.label
            not in (
                "BROAD_ADVANCE",
                "BROAD_DECLINE",
                "MIXED_PARTICIPATION",
                None,
            )
            or (self.label is not None)
            != (self.insufficient_count == 0 and not self.reasons)
            or (self.label is None and not self.reasons)
        ):
            raise ValueError("current price context breadth is invalid")


def _expected_breadth_label(
    advances: int, declines: int, requested_count: int
) -> Literal["BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"]:
    if advances * 5 >= requested_count * 3:
        return "BROAD_ADVANCE"
    if declines * 5 >= requested_count * 3:
        return "BROAD_DECLINE"
    return "MIXED_PARTICIPATION"


def _raw_feature_state_and_reasons(
    members: tuple[CurrentPriceContextMemberResultV1, ...],
) -> tuple[
    Literal["OBSERVED", "UNSUPPORTED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE"],
    tuple[str, ...],
]:
    reasons = tuple(
        dict.fromkeys(member.reason for member in members if member.reason is not None)
    )
    if (
        len(reasons) == 1
        and all(member.state != "OBSERVED" for member in members)
        and reasons[0]
        in {
            "CALENDAR_PREREQUISITE_MISSING",
            "CALENDAR_FUTURE_KNOWN",
            "COMPLETED_SESSION_WINDOW_UNAVAILABLE",
            "CALENDAR_UNSUPPORTED",
            "RAW_WINDOW_LIMIT_EXCEEDED",
            "SCHEDULE_AUTHORITY_CHANGED",
            "ACQUISITION_STOPPED",
        }
    ):
        return cast(
            Literal[
                "OBSERVED", "UNSUPPORTED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE"
            ],
            _MEMBER_REASON_STATES[reasons[0]],
        ), reasons
    return "OBSERVED", ()


def _expected_raw_feature(
    question: str,
    ready: bool,
    state: Literal[
        "OBSERVED", "UNSUPPORTED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE"
    ],
    reasons: tuple[str, ...],
    members: tuple[CurrentPriceContextMemberResultV1, ...],
) -> CurrentPriceContextFeatureV1:
    member_reasons = tuple(
        dict.fromkeys(member.reason for member in members if member.reason is not None)
    )
    withheld_reasons = reasons or member_reasons or ("MEMBER_EVIDENCE_UNAVAILABLE",)
    return CurrentPriceContextFeatureV1(
        question,
        "OBSERVED"
        if ready
        else (state if state != "OBSERVED" else "INSUFFICIENT_EVIDENCE"),
        () if ready else withheld_reasons,
        readiness="READY" if ready else "WITHHELD",
    )


def _expected_features(
    members: tuple[CurrentPriceContextMemberResultV1, ...],
    breadth: CurrentPriceContextBreadthV1 | None,
    industry_state: Literal[
        "OBSERVED",
        "NOT_ATTEMPTED",
        "UNSUPPORTED",
        "INSUFFICIENT_EVIDENCE",
        "CONFLICTED",
    ],
    industry_feature_reasons: tuple[str, ...],
) -> tuple[CurrentPriceContextFeatureV1, ...]:
    raw_state, raw_reasons = _raw_feature_state_and_reasons(members)
    industry_feature = CurrentPriceContextFeatureV1(
        "RAW_INDUSTRY_PARTICIPATION",
        cast(
            Literal[
                "OBSERVED",
                "UNSUPPORTED",
                "DEPENDENCY_BLOCKED",
                "INSUFFICIENT_EVIDENCE",
                "NOT_ATTEMPTED",
            ],
            "INSUFFICIENT_EVIDENCE"
            if industry_state in ("NOT_ATTEMPTED", "CONFLICTED")
            else industry_state,
        ),
        () if industry_state == "OBSERVED" else industry_feature_reasons,
        support="UNSUPPORTED" if industry_state == "UNSUPPORTED" else "SUPPORTED",
        readiness="READY" if industry_state == "OBSERVED" else "WITHHELD",
    )
    return (
        _expected_raw_feature(
            "RAW_MARKET_STRUCTURE",
            all(member.structure is not None for member in members),
            raw_state,
            raw_reasons,
            members,
        ),
        _expected_raw_feature(
            "RAW_20_SESSION_DIRECTION",
            all(member.direction is not None for member in members),
            raw_state,
            raw_reasons,
            members,
        ),
        _expected_raw_feature(
            "RAW_COHORT_BREADTH",
            breadth is not None and breadth.label is not None,
            raw_state,
            raw_reasons,
            members,
        ),
        industry_feature,
    )


@dataclass(frozen=True, slots=True)
class CurrentPriceContextResultV1:
    contract_version: Literal["current-price-context@v1"]
    request_identity_sha256: str
    schema_identity_sha256: str
    calculation_identity_sha256: str
    configuration_identity_sha256: str
    schedule_identity_sha256: str
    ordered_selection_identity_sha256: str
    canonical_cohort_identity_sha256: str
    requested_count: int
    questions: tuple[str, ...]
    schedule_as_of: datetime | None
    data_selection_time: datetime
    evidence_cutoff: datetime
    provider: Literal["UPSTOX"]
    price_basis: Literal["RAW"]
    bar_basis: Literal["1d-derived-from-retained-1m"]
    source_bindings_identity_sha256: str
    acquisition_mode: Literal["RETAINED_ONLY", "ACQUIRE_MISSING"]
    acquisition_outcome: Literal[
        "NOT_ATTEMPTED",
        "CALENDAR_PREREQUISITE_MISSING",
        "RETAINED_EVIDENCE_READY",
        "ACQUISITION_COMPLETED",
        "ACQUISITION_PARTIAL",
        "ACQUISITION_BLOCKED",
        "STOPPED",
    ]
    acquisition_provider_calls: int
    members: tuple[CurrentPriceContextMemberResultV1, ...]
    breadth: CurrentPriceContextBreadthV1 | None
    features: tuple[CurrentPriceContextFeatureV1, ...]
    limitations: tuple[str, ...]
    runtime_code_identity_sha256: str
    industry_evidence_state: Literal[
        "OBSERVED",
        "NOT_ATTEMPTED",
        "UNSUPPORTED",
        "INSUFFICIENT_EVIDENCE",
        "CONFLICTED",
    ] = "NOT_ATTEMPTED"
    industry_snapshot_identity_sha256: str | None = None
    industry_retained_identity_sha256: str | None = None
    industry_known_at: datetime | None = None
    industry_groups: tuple[CurrentRawIndustryGroupV1, ...] = ()
    result_identity_sha256: str = ""

    def __post_init__(self) -> None:
        if (
            self.contract_version != _RESULT_CONTRACT
            or not _digest(self.request_identity_sha256)
            or (
                self.schema_identity_sha256 != _RESULT_SCHEMA_IDENTITY_SHA256
                or self.calculation_identity_sha256
                != _RESULT_CALCULATION_IDENTITY_SHA256
                or self.configuration_identity_sha256
                != _RESULT_CONFIGURATION_IDENTITY_SHA256
            )
            or any(
                not _digest(value)
                for value in (
                    self.schedule_identity_sha256,
                    self.ordered_selection_identity_sha256,
                    self.canonical_cohort_identity_sha256,
                    self.source_bindings_identity_sha256,
                )
            )
            or type(self.requested_count) is not int
            or not 1 <= self.requested_count <= 50
            or self.questions != _QUESTIONS
            or (self.schedule_as_of is not None and not _utc(self.schedule_as_of))
            or not _utc(self.data_selection_time)
            or not _utc(self.evidence_cutoff)
            or self.evidence_cutoff < self.data_selection_time
            or (
                self.schedule_as_of is not None
                and self.schedule_as_of > self.evidence_cutoff
            )
            or self.provider != "UPSTOX"
            or self.price_basis != "RAW"
            or self.bar_basis != "1d-derived-from-retained-1m"
            or self.acquisition_mode not in ("RETAINED_ONLY", "ACQUIRE_MISSING")
            or self.acquisition_outcome
            not in (
                "NOT_ATTEMPTED",
                "CALENDAR_PREREQUISITE_MISSING",
                "RETAINED_EVIDENCE_READY",
                "ACQUISITION_COMPLETED",
                "ACQUISITION_PARTIAL",
                "ACQUISITION_BLOCKED",
                "STOPPED",
            )
            or type(self.acquisition_provider_calls) is not int
            or not 0 <= self.acquisition_provider_calls <= 5 * self.requested_count + 1
            or (
                self.acquisition_mode == "RETAINED_ONLY"
                and (
                    self.acquisition_outcome != "NOT_ATTEMPTED"
                    or self.acquisition_provider_calls != 0
                )
            )
            or (
                self.acquisition_mode == "ACQUIRE_MISSING"
                and self.acquisition_outcome == "NOT_ATTEMPTED"
            )
            or (
                self.acquisition_outcome
                in ("CALENDAR_PREREQUISITE_MISSING", "RETAINED_EVIDENCE_READY")
                and self.acquisition_provider_calls != 0
            )
            or (
                self.acquisition_outcome
                in ("ACQUISITION_COMPLETED", "ACQUISITION_PARTIAL")
                and self.acquisition_provider_calls < 1
            )
            or type(self.members) is not tuple
            or not 1 <= len(self.members) <= 50
            or len(self.members) != self.requested_count
            or any(
                type(item) is not CurrentPriceContextMemberResultV1
                for item in self.members
            )
            or tuple(item.position for item in self.members)
            != tuple(range(len(self.members)))
            or len({item.isin for item in self.members}) != len(self.members)
            or (
                len({item.effective_symbol for item in self.members})
                != len(self.members)
            )
            or any(
                not _member_source_times_at_or_before(item, self.evidence_cutoff)
                for item in self.members
            )
            or any(
                item.structure is not None
                and (
                    item.structure.isin != item.isin
                    or item.structure.exchange != item.exchange
                    or item.structure.effective_symbol != item.effective_symbol
                )
                for item in self.members
            )
            or (
                self.breadth is not None
                and (
                    type(self.breadth) is not CurrentPriceContextBreadthV1
                    or self.breadth.requested_count != len(self.members)
                    or self.breadth.observed_count
                    != sum(item.direction is not None for item in self.members)
                    or self.breadth.advances
                    != sum(item.direction == "ADVANCE" for item in self.members)
                    or self.breadth.declines
                    != sum(item.direction == "DECLINE" for item in self.members)
                    or self.breadth.unchanged
                    != sum(item.direction == "UNCHANGED" for item in self.members)
                    or self.breadth.insufficient_count
                    != sum(item.direction is None for item in self.members)
                    or (
                        self.breadth.label is not None
                        and (
                            self.breadth.reasons
                            or self.breadth.label
                            != _expected_breadth_label(
                                self.breadth.advances,
                                self.breadth.declines,
                                self.breadth.requested_count,
                            )
                        )
                    )
                    or (
                        self.breadth.label is None
                        and self.breadth.reasons != ("MEMBER_DIRECTION_UNAVAILABLE",)
                    )
                )
            )
            or type(self.features) is not tuple
            or tuple(item.question for item in self.features) != _QUESTIONS
            or any(
                type(item) is not CurrentPriceContextFeatureV1 for item in self.features
            )
            or any(
                reason not in _INDUSTRY_REASONS
                for item in self.features
                if item.question == "RAW_INDUSTRY_PARTICIPATION"
                for reason in item.reasons
            )
            or type(self.limitations) is not tuple
            or self.limitations != _LIMITATIONS
            or self.runtime_code_identity_sha256
            != current_price_context_runtime_code_identity_v1()
            or self.industry_evidence_state
            not in (
                "OBSERVED",
                "NOT_ATTEMPTED",
                "UNSUPPORTED",
                "INSUFFICIENT_EVIDENCE",
                "CONFLICTED",
            )
            or (
                (self.industry_snapshot_identity_sha256 is None)
                != (self.industry_retained_identity_sha256 is None)
            )
            or (
                self.industry_snapshot_identity_sha256 is not None
                and (
                    not _digest(self.industry_snapshot_identity_sha256)
                    or not _digest(self.industry_retained_identity_sha256)
                    or not _utc(self.industry_known_at)
                )
            )
            or (
                self.industry_known_at is not None
                and (
                    not _utc(self.industry_known_at)
                    or self.industry_known_at > self.evidence_cutoff
                )
            )
            or type(self.industry_groups) is not tuple
            or any(
                type(item) is not CurrentRawIndustryGroupV1
                for item in self.industry_groups
            )
            or (
                self.industry_evidence_state == "OBSERVED"
                and (
                    self.industry_snapshot_identity_sha256 is None
                    or self.industry_retained_identity_sha256 is None
                    or self.industry_known_at is None
                    or not self.industry_groups
                )
            )
            or (
                self.industry_evidence_state != "OBSERVED"
                and (
                    self.industry_snapshot_identity_sha256 is not None
                    or self.industry_retained_identity_sha256 is not None
                    or self.industry_known_at is not None
                    or self.industry_groups
                )
            )
        ):
            raise ValueError("current price context result is invalid")
        if self.acquisition_outcome == "STOPPED" and (
            self.acquisition_mode != "ACQUIRE_MISSING"
            or self.breadth is not None
            or self.industry_evidence_state != "NOT_ATTEMPTED"
            or any(
                item.state != "DEPENDENCY_BLOCKED"
                or item.reason != "ACQUISITION_STOPPED"
                or item.structure is not None
                or item.direction is not None
                for item in self.members
            )
        ):
            raise ValueError("current price context result is invalid")
        raw_state, _ = _raw_feature_state_and_reasons(self.members)
        if (self.breadth is None) != (raw_state != "OBSERVED"):
            raise ValueError("current price context result is invalid")
        if self.industry_evidence_state == "OBSERVED" and (
            self.breadth is None
            or self.breadth.label is None
            or tuple(group.industry for group in self.industry_groups)
            != tuple(sorted(group.industry for group in self.industry_groups))
            or len({group.industry for group in self.industry_groups})
            != len(self.industry_groups)
            or sum(group.member_count for group in self.industry_groups)
            != self.requested_count
            or sum(group.advances for group in self.industry_groups)
            != self.breadth.advances
            or sum(group.declines for group in self.industry_groups)
            != self.breadth.declines
            or sum(group.unchanged for group in self.industry_groups)
            != self.breadth.unchanged
        ):
            raise ValueError("current price context result is invalid")
        industry_feature_reasons = self.features[-1].reasons
        if (
            self.industry_evidence_state == "NOT_ATTEMPTED"
            and industry_feature_reasons
            != (
                ("INDUSTRY_NOT_ATTEMPTED",)
                if self.acquisition_outcome == "STOPPED"
                else ("INDUSTRY_REFERENCE_NOT_PROVIDED",)
            )
        ):
            raise ValueError("current price context result is invalid")
        if self.features != _expected_features(
            self.members,
            self.breadth,
            self.industry_evidence_state,
            industry_feature_reasons,
        ):
            raise ValueError("current price context result is invalid")
        identity = _digest_value(_without_identity(self))
        if self.result_identity_sha256 not in ("", identity):
            raise ValueError("current price context result identity is invalid")
        object.__setattr__(self, "result_identity_sha256", identity)

    def canonical_json_bytes(self) -> bytes:
        raw = _canonical(_wire(self))
        if len(raw) > _MAX_RESULT_BYTES:
            raise ValueError("current price context result exceeds its bound")
        return raw


def current_price_context_request_from_canonical_json_bytes_v1(
    raw: bytes,
) -> CurrentPriceContextRequestV1:
    """Decode only the closed canonical owner-supplied request representation."""
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_REQUEST_BYTES:
        raise ValueError("current price context request is invalid")
    try:
        decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        if type(decoded) is not dict:
            raise ValueError
        value = cast(dict[str, object], decoded)
        if _canonical(value) != raw or set(value) != {
            "contract_version",
            "data_selection_time",
            "admission_deadline",
            "schedule_identity_sha256",
            "members",
            "questions",
            "industry_archive_reference",
        }:
            raise ValueError
        reference = _reference_from_value(value["industry_archive_reference"])
        members = _members_from_value(value["members"])
        questions = value["questions"]
        if type(questions) is not list:
            raise ValueError
        question_values = cast(list[object], questions)
        return CurrentPriceContextRequestV1(
            contract_version=cast(
                Literal["current-price-context-request@v1"], value["contract_version"]
            ),
            data_selection_time=_parse_instant(value["data_selection_time"]),
            admission_deadline=_parse_instant(value["admission_deadline"]),
            schedule_identity_sha256=cast(str, value["schedule_identity_sha256"]),
            members=members,
            questions=cast(
                tuple[
                    Literal[
                        "RAW_MARKET_STRUCTURE",
                        "RAW_20_SESSION_DIRECTION",
                        "RAW_COHORT_BREADTH",
                        "RAW_INDUSTRY_PARTICIPATION",
                    ],
                    ...,
                ],
                tuple(question_values),
            ),
            industry_archive_reference=reference,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        TypeError,
        ValueError,
    ):
        raise ValueError("current price context request is invalid") from None


_RESULT_SCHEMA_IDENTITY_SHA256 = hashlib.sha256(
    b"current-price-context-result-schema@v1"
).hexdigest()
_RESULT_CALCULATION_IDENTITY_SHA256 = hashlib.sha256(
    b"current-price-context-calculation@v1"
).hexdigest()
_RESULT_CONFIGURATION_IDENTITY_SHA256 = hashlib.sha256(
    b"current-price-context-configuration@v1"
).hexdigest()


def _result_bindings(
    request: CurrentPriceContextRequestV1,
    raw_input: CurrentRawPriceContextInputV1,
    *,
    evidence_cutoff: datetime,
    industry: CurrentIndustryArchiveReferenceV1 | None = None,
) -> _ResultBindingsV1:
    """One closed non-sensitive provenance binding for all public outcomes."""
    return _ResultBindingsV1(
        schema_identity_sha256=_RESULT_SCHEMA_IDENTITY_SHA256,
        calculation_identity_sha256=_RESULT_CALCULATION_IDENTITY_SHA256,
        configuration_identity_sha256=_RESULT_CONFIGURATION_IDENTITY_SHA256,
        schedule_identity_sha256=request.schedule_identity_sha256,
        ordered_selection_identity_sha256=raw_input.ordered_selection_identity_sha256,
        canonical_cohort_identity_sha256=raw_input.canonical_cohort_identity_sha256,
        questions=request.questions,
        data_selection_time=request.data_selection_time,
        evidence_cutoff=evidence_cutoff,
        provider="UPSTOX",
        price_basis="RAW",
        bar_basis="1d-derived-from-retained-1m",
        source_bindings_identity_sha256=_digest_value(
            {
                "schedule": request.schedule_identity_sha256,
                "members": tuple(
                    (member.isin, member.effective_symbol) for member in request.members
                ),
                "industry": industry,
            }
        ),
    )


def current_price_context_result_from_canonical_json_bytes_v1(
    raw: bytes,
) -> CurrentPriceContextResultV1:
    """Decode one fully validated public DTO without minting any capability."""
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_RESULT_BYTES:
        raise ValueError("current price context result is invalid")
    try:
        decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        if type(decoded) is not dict:
            raise ValueError
        value = cast(dict[str, object], decoded)
        if _canonical(value) != raw:
            raise ValueError
        result = _result_from_value(value)
        if result.canonical_json_bytes() != raw:
            raise ValueError
        return result
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        TypeError,
        ValueError,
        InvalidOperation,
    ):
        raise ValueError("current price context result is invalid") from None


def _result_from_value(value: object) -> CurrentPriceContextResultV1:
    if type(value) is not dict:
        raise ValueError
    raw = cast(dict[str, object], value)
    if set(raw) != {item.name for item in fields(CurrentPriceContextResultV1)}:
        raise ValueError
    members_value = _list(raw["members"])
    features_value = _list(raw["features"])
    groups_value = _list(raw["industry_groups"])
    breadth_value = raw["breadth"]
    result = CurrentPriceContextResultV1(
        contract_version=cast(
            Literal["current-price-context@v1"], raw["contract_version"]
        ),
        request_identity_sha256=cast(str, raw["request_identity_sha256"]),
        schema_identity_sha256=cast(str, raw["schema_identity_sha256"]),
        calculation_identity_sha256=cast(str, raw["calculation_identity_sha256"]),
        configuration_identity_sha256=cast(str, raw["configuration_identity_sha256"]),
        schedule_identity_sha256=cast(str, raw["schedule_identity_sha256"]),
        ordered_selection_identity_sha256=cast(
            str, raw["ordered_selection_identity_sha256"]
        ),
        canonical_cohort_identity_sha256=cast(
            str, raw["canonical_cohort_identity_sha256"]
        ),
        requested_count=_integer(raw["requested_count"]),
        questions=_strings(raw["questions"]),
        schedule_as_of=(
            None
            if raw["schedule_as_of"] is None
            else _parse_instant(raw["schedule_as_of"])
        ),
        data_selection_time=_parse_instant(raw["data_selection_time"]),
        evidence_cutoff=_parse_instant(raw["evidence_cutoff"]),
        provider=cast(Literal["UPSTOX"], raw["provider"]),
        price_basis=cast(Literal["RAW"], raw["price_basis"]),
        bar_basis=cast(Literal["1d-derived-from-retained-1m"], raw["bar_basis"]),
        source_bindings_identity_sha256=cast(
            str, raw["source_bindings_identity_sha256"]
        ),
        acquisition_mode=cast(
            Literal["RETAINED_ONLY", "ACQUIRE_MISSING"], raw["acquisition_mode"]
        ),
        acquisition_outcome=cast(Any, raw["acquisition_outcome"]),
        acquisition_provider_calls=_integer(raw["acquisition_provider_calls"]),
        members=tuple(_member_result_from_value(item) for item in members_value),
        breadth=None if breadth_value is None else _breadth_from_value(breadth_value),
        features=tuple(_feature_from_value(item) for item in features_value),
        limitations=_strings(raw["limitations"]),
        runtime_code_identity_sha256=cast(str, raw["runtime_code_identity_sha256"]),
        industry_evidence_state=cast(Any, raw["industry_evidence_state"]),
        industry_snapshot_identity_sha256=cast(
            str | None, raw["industry_snapshot_identity_sha256"]
        ),
        industry_retained_identity_sha256=cast(
            str | None, raw["industry_retained_identity_sha256"]
        ),
        industry_known_at=None
        if raw["industry_known_at"] is None
        else _parse_instant(raw["industry_known_at"]),
        industry_groups=tuple(
            _industry_group_from_value(item) for item in groups_value
        ),
        result_identity_sha256=cast(str, raw["result_identity_sha256"]),
    )
    return result


def _member_result_from_value(value: object) -> CurrentPriceContextMemberResultV1:
    raw = _object(
        value, {item.name for item in fields(CurrentPriceContextMemberResultV1)}
    )
    return CurrentPriceContextMemberResultV1(
        position=_integer(raw["position"]),
        isin=cast(str, raw["isin"]),
        exchange=cast(Literal["NSE"], raw["exchange"]),
        effective_symbol=cast(str, raw["effective_symbol"]),
        state=cast(Any, raw["state"]),
        reason=cast(str | None, raw["reason"]),
        structure=None
        if raw["structure"] is None
        else _structure_from_value(raw["structure"]),
        direction=cast(Any, raw["direction"]),
        mapping_observation_sha256=cast(str | None, raw["mapping_observation_sha256"]),
        mapping_retrieved_at=(
            None
            if raw["mapping_retrieved_at"] is None
            else _parse_instant(raw["mapping_retrieved_at"])
        ),
        partition_checksums=_strings(raw["partition_checksums"]),
        raw_source_times=tuple(
            _parse_instant(item) for item in _list(raw["raw_source_times"])
        ),
        screen_identity_sha256=cast(str | None, raw["screen_identity_sha256"]),
        screen_knowledge_at=(
            None
            if raw["screen_knowledge_at"] is None
            else _parse_instant(raw["screen_knowledge_at"])
        ),
    )


def _structure_from_value(value: object) -> CurrentMarketStructureMemberV1:
    raw = _object(value, {item.name for item in fields(CurrentMarketStructureMemberV1)})
    member = CurrentMarketStructureMemberV1(
        isin=cast(str, raw["isin"]),
        exchange=cast(str, raw["exchange"]),
        effective_symbol=cast(str, raw["effective_symbol"]),
        input_bar_identities_sha256=_strings(raw["input_bar_identities_sha256"]),
        structure_state=cast(Any, raw["structure_state"]),
        trend=cast(Any, raw["trend"]),
        pivots=tuple(_pivot_from_value(item) for item in _list(raw["pivots"])),
        events=tuple(_event_from_value(item) for item in _list(raw["events"])),
    )
    if raw["member_identity_sha256"] != member.member_identity_sha256:
        raise ValueError
    return member


def _pivot_from_value(value: object) -> MarketStructurePivotV1:
    raw = _object(value, {item.name for item in fields(MarketStructurePivotV1)})
    pivot = MarketStructurePivotV1(
        kind=cast(Any, raw["kind"]),
        position=_integer(raw["position"]),
        confirmation_position=_integer(raw["confirmation_position"]),
        session=_date_from_value(raw["session"]),
        confirmation_session=_date_from_value(raw["confirmation_session"]),
        price=_decimal(raw["price"]),
        relation=cast(Any, raw["relation"]),
        unclassified_reason=cast(Any, raw["unclassified_reason"]),
        source_bar_identity_sha256=cast(str, raw["source_bar_identity_sha256"]),
        comparison_bar_identities_sha256=cast(
            tuple[str, str, str, str], _strings(raw["comparison_bar_identities_sha256"])
        ),
    )
    if raw["pivot_identity_sha256"] != pivot.pivot_identity_sha256:
        raise ValueError
    return pivot


def _event_from_value(value: object) -> MarketStructureEventV1:
    raw = _object(value, {item.name for item in fields(MarketStructureEventV1)})
    event = MarketStructureEventV1(
        event=cast(Any, raw["event"]),
        direction=cast(Any, raw["direction"]),
        position=_integer(raw["position"]),
        session=_date_from_value(raw["session"]),
        close=_decimal(raw["close"]),
        broken_pivot_identity_sha256=cast(str, raw["broken_pivot_identity_sha256"]),
        broken_level=_decimal(raw["broken_level"]),
        prior_trend=cast(Any, raw["prior_trend"]),
        previous_close_bar_identity_sha256=cast(
            str, raw["previous_close_bar_identity_sha256"]
        ),
        current_close_bar_identity_sha256=cast(
            str, raw["current_close_bar_identity_sha256"]
        ),
    )
    if raw["event_identity_sha256"] != event.event_identity_sha256:
        raise ValueError
    return event


def _breadth_from_value(value: object) -> CurrentPriceContextBreadthV1:
    raw = _object(value, {item.name for item in fields(CurrentPriceContextBreadthV1)})
    return CurrentPriceContextBreadthV1(
        _integer(raw["requested_count"]),
        _integer(raw["observed_count"]),
        _integer(raw["advances"]),
        _integer(raw["declines"]),
        _integer(raw["unchanged"]),
        _integer(raw["insufficient_count"]),
        cast(Any, raw["label"]),
        _strings(raw["reasons"]),
    )


def _feature_from_value(value: object) -> CurrentPriceContextFeatureV1:
    raw = _object(value, {item.name for item in fields(CurrentPriceContextFeatureV1)})
    return CurrentPriceContextFeatureV1(
        cast(str, raw["question"]),
        cast(Any, raw["state"]),
        _strings(raw["reasons"]),
        cast(Any, raw["support"]),
        cast(Any, raw["readiness"]),
    )


def _industry_group_from_value(value: object) -> CurrentRawIndustryGroupV1:
    raw = _object(value, {item.name for item in fields(CurrentRawIndustryGroupV1)})
    return CurrentRawIndustryGroupV1(
        cast(str, raw["industry"]),
        _integer(raw["member_count"]),
        _integer(raw["advances"]),
        _integer(raw["declines"]),
        _integer(raw["unchanged"]),
    )


def _object(value: object, expected: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(cast(dict[str, object], value)) != expected:
        raise ValueError
    return cast(dict[str, object], value)


def _list(value: object) -> list[object]:
    if type(value) is not list:
        raise ValueError
    return cast(list[object], value)


def _strings(value: object) -> tuple[str, ...]:
    parsed = _list(value)
    if any(type(item) is not str for item in parsed):
        raise ValueError
    return tuple(cast(str, item) for item in parsed)


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError
    return value


def _date_from_value(value: object) -> date:
    if type(value) is not str:
        raise ValueError
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError
    return parsed


def _decimal(value: object) -> Decimal:
    if type(value) is not str:
        raise ValueError
    parsed = Decimal(value)
    if not parsed.is_finite():
        raise ValueError
    return parsed


def research_current_price_context_v1(  # noqa: C901 -- one bounded public composition
    request: CurrentPriceContextRequestV1,
    storage_root: Path,
    *,
    acquire_missing: bool = False,
    clock: CurrentPriceContextClockV1 | None = None,
) -> CurrentPriceContextResultV1:
    """Return only verified raw facts and local Industry availability."""
    if type(request) is not CurrentPriceContextRequestV1:
        raise ValueError("current price context input is invalid")
    if type(acquire_missing) is not bool or (
        clock is not None and not callable(getattr(clock, "now", None))
    ):
        raise ValueError("current price context options are invalid")
    observed_now = datetime.now(UTC) if clock is None else clock.now()
    if not _utc(observed_now):
        raise ValueError("current price context clock is invalid")
    if not request.data_selection_time <= observed_now < request.admission_deadline:
        raise ValueError("current price context deadline exceeded")
    if (
        observed_now.astimezone(_IST).date()
        != request.data_selection_time.astimezone(_IST).date()
    ):
        raise ValueError("current price context IST date changed")
    runtime_identity = current_price_context_runtime_code_identity_v1()
    raw_input = CurrentRawPriceContextInputV1(
        request.request_identity_sha256,
        request.data_selection_time,
        request.admission_deadline,
        request.schedule_identity_sha256,
        request.members,
    )
    control = CurrentRawInvocationControlV1(
        _SystemClock() if clock is None else clock,
        selection=request.data_selection_time,
        deadline=request.admission_deadline,
    )
    acquisition_outcome: Literal[
        "NOT_ATTEMPTED",
        "CALENDAR_PREREQUISITE_MISSING",
        "RETAINED_EVIDENCE_READY",
        "ACQUISITION_COMPLETED",
        "ACQUISITION_PARTIAL",
        "ACQUISITION_BLOCKED",
        "STOPPED",
    ] = "NOT_ATTEMPTED"
    acquisition_provider_calls = 0
    if acquire_missing:
        acquired = acquire_missing_current_raw_evidence_v1(
            raw_input, storage_root, control=control
        )
        acquisition_outcome = acquired.outcome
        acquisition_provider_calls = acquired.provider_calls
        if acquisition_outcome == "STOPPED":
            member_results = _withheld_members(
                request.members, "DEPENDENCY_BLOCKED", "ACQUISITION_STOPPED"
            )
            return CurrentPriceContextResultV1(
                contract_version=_RESULT_CONTRACT,
                request_identity_sha256=request.request_identity_sha256,
                requested_count=len(request.members),
                schedule_as_of=None,
                **_result_bindings(request, raw_input, evidence_cutoff=observed_now),
                acquisition_mode="ACQUIRE_MISSING",
                acquisition_outcome=acquisition_outcome,
                acquisition_provider_calls=acquisition_provider_calls,
                members=member_results,
                breadth=None,
                features=_features(
                    "DEPENDENCY_BLOCKED",
                    ("ACQUISITION_STOPPED",),
                    member_results,
                    None,
                    "NOT_ATTEMPTED",
                    ("INDUSTRY_NOT_ATTEMPTED",),
                ),
                limitations=_LIMITATIONS,
                runtime_code_identity_sha256=runtime_identity,
            )
    industry_state: Literal[
        "OBSERVED",
        "NOT_ATTEMPTED",
        "UNSUPPORTED",
        "INSUFFICIENT_EVIDENCE",
        "CONFLICTED",
    ] = "NOT_ATTEMPTED"
    industry_reasons: tuple[str, ...] = ("INDUSTRY_REFERENCE_NOT_PROVIDED",)
    industry_groups: tuple[CurrentRawIndustryGroupV1, ...] = ()
    industry_known_at: datetime | None = None
    archive: (
        AdmittedCurrentIndustryProjectionV1 | CurrentIndustryReadFailureV1 | None
    ) = None
    admitted = StorageRootLease.try_admit_read_existing(storage_root)
    if (
        admitted.lease is None
        and storage_root.exists()
        and StorageRootLease.admit_existing_private_identity(storage_root) is None
    ):
        raise StorageRootLeaseError("current price context root authority unavailable")
    raw_projection = None
    raw_value: AdmittedCurrentRawContextV1 | None = None
    if admitted.lease is None:
        member_results = _withheld_members(
            request.members, "DEPENDENCY_BLOCKED", "CALENDAR_PREREQUISITE_MISSING"
        )
        feature_state: Literal[
            "OBSERVED", "UNSUPPORTED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE"
        ] = "DEPENDENCY_BLOCKED"
        reasons = ("CALENDAR_PREREQUISITE_MISSING",)
        breadth = None
    else:
        with admitted.lease as lease:
            retained = read_retained_current_raw_context_v1(
                storage_root, request=raw_input, lease=lease, control=control
            )
            feature_state, reasons = retained.state, retained.reasons
            if retained.admitted is None:
                member_results = _withheld_members(
                    request.members,
                    cast(
                        Literal[
                            "UNSUPPORTED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE"
                        ],
                        retained.state,
                    ),
                    retained.reasons[0],
                )
                breadth = None
            else:
                raw_value = retained.admitted
                raw_projection = validate_admitted_current_raw_context_v1(raw_value)
                member_results = tuple(
                    CurrentPriceContextMemberResultV1(
                        item.position,
                        item.isin,
                        item.exchange,
                        item.effective_symbol,
                        item.state,
                        item.reason,
                        item.structure,
                        item.direction,
                        item.mapping_observation_sha256,
                        item.mapping_retrieved_at,
                        item.partition_checksums,
                        item.raw_source_times,
                        item.screen_identity_sha256,
                        item.screen_knowledge_at,
                    )
                    for item in raw_projection.members
                )
                breadth = _public_breadth(raw_projection.breadth, member_results)
                if request.industry_archive_reference is not None:
                    archive = read_current_industry_archive_exact_v1(
                        ArchivedIndustryReferenceV1(
                            request.industry_archive_reference.contract_version,
                            request.industry_archive_reference.snapshot_identity_sha256,
                            request.industry_archive_reference.retained_identity_sha256,
                        ),
                        storage_root=storage_root,
                        lease=lease,
                        raw=raw_value,
                    )
                    if type(archive) is CurrentIndustryReadFailureV1:
                        industry_state, industry_reasons = (
                            archive.state
                            if archive.state != "MALFORMED_EVIDENCE"
                            else "INSUFFICIENT_EVIDENCE",
                            (archive.reason,),
                        )
                    else:
                        grouped = reduce_current_raw_industry_participation_v1(
                            raw_value,
                            cast(AdmittedCurrentIndustryProjectionV1, archive),
                        )
                        industry_state = grouped.evidence_state
                        industry_reasons = grouped.reasons
                        industry_groups = grouped.groups
                        industry_known_at = admitted_current_industry_binding_v1(
                            cast(AdmittedCurrentIndustryProjectionV1, archive)
                        )[0].known_at
                recheck_retained_current_raw_context_v1(
                    raw_value, storage_root, lease=lease, control=control
                )
                reference = request.industry_archive_reference
                if (
                    type(archive) is AdmittedCurrentIndustryProjectionV1
                    and reference is not None
                ):
                    final_archive = read_current_industry_archive_exact_v1(
                        ArchivedIndustryReferenceV1(
                            reference.contract_version,
                            reference.snapshot_identity_sha256,
                            reference.retained_identity_sha256,
                        ),
                        storage_root=storage_root,
                        lease=lease,
                        raw=raw_value,
                    )
                    if type(final_archive) is CurrentIndustryReadFailureV1:
                        industry_state, industry_reasons = (
                            final_archive.state
                            if final_archive.state != "MALFORMED_EVIDENCE"
                            else "INSUFFICIENT_EVIDENCE",
                            (final_archive.reason,),
                        )
                        industry_groups = ()
                        industry_known_at = None
                    else:
                        grouped = reduce_current_raw_industry_participation_v1(
                            raw_value,
                            cast(AdmittedCurrentIndustryProjectionV1, final_archive),
                        )
                        industry_state = grouped.evidence_state
                        industry_reasons = grouped.reasons
                        industry_groups = grouped.groups
                        industry_known_at = admitted_current_industry_binding_v1(
                            cast(AdmittedCurrentIndustryProjectionV1, final_archive)
                        )[0].known_at
            control.ensure_live()
    return CurrentPriceContextResultV1(
        contract_version=_RESULT_CONTRACT,
        request_identity_sha256=request.request_identity_sha256,
        requested_count=len(request.members),
        schedule_as_of=(
            None if raw_projection is None else raw_projection.schedule_as_of
        ),
        **_result_bindings(
            request,
            raw_input,
            evidence_cutoff=(
                raw_projection.evidence_cutoff
                if raw_projection is not None
                else observed_now
            ),
            industry=request.industry_archive_reference,
        ),
        acquisition_mode="ACQUIRE_MISSING" if acquire_missing else "RETAINED_ONLY",
        acquisition_outcome=cast(Any, acquisition_outcome),
        acquisition_provider_calls=acquisition_provider_calls,
        members=member_results,
        breadth=breadth,
        features=_features(
            feature_state,
            reasons,
            member_results,
            breadth,
            industry_state,
            industry_reasons,
        ),
        limitations=_LIMITATIONS,
        runtime_code_identity_sha256=runtime_identity,
        industry_evidence_state=industry_state,
        industry_snapshot_identity_sha256=(
            request.industry_archive_reference.snapshot_identity_sha256
            if industry_state == "OBSERVED"
            and request.industry_archive_reference is not None
            else None
        ),
        industry_retained_identity_sha256=(
            request.industry_archive_reference.retained_identity_sha256
            if industry_state == "OBSERVED"
            and request.industry_archive_reference is not None
            else None
        ),
        industry_known_at=industry_known_at,
        industry_groups=industry_groups,
    )


def _withheld_members(
    members: tuple[CurrentPriceContextMemberV1, ...],
    state: Literal["UNSUPPORTED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE"],
    reason: str,
) -> tuple[CurrentPriceContextMemberResultV1, ...]:
    return tuple(
        CurrentPriceContextMemberResultV1(
            index,
            item.isin,
            item.exchange,
            item.effective_symbol,
            state,
            reason,
            None,
            None,
            None,
            None,
            (),
            (),
            None,
            None,
        )
        for index, item in enumerate(members)
    )


def _public_breadth(
    raw: RawCohortBreadthV1,
    members: tuple[CurrentPriceContextMemberResultV1, ...],
) -> CurrentPriceContextBreadthV1:
    """Preserve complete-cohort counts even when a label is rightly withheld."""
    observed = tuple(item for item in members if item.direction is not None)
    advances = sum(item.direction == "ADVANCE" for item in observed)
    declines = sum(item.direction == "DECLINE" for item in observed)
    unchanged = len(observed) - advances - declines
    insufficient = len(members) - len(observed)
    if raw.requested_count != len(members):
        raise ValueError("current price context breadth is invalid")
    return CurrentPriceContextBreadthV1(
        requested_count=len(members),
        observed_count=len(observed),
        advances=advances,
        declines=declines,
        unchanged=unchanged,
        insufficient_count=insufficient,
        label=raw.label,
        reasons=raw.reasons,
    )


def _features(
    state: Literal[
        "OBSERVED", "UNSUPPORTED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE"
    ],
    reasons: tuple[str, ...],
    members: tuple[CurrentPriceContextMemberResultV1, ...],
    breadth: CurrentPriceContextBreadthV1 | None,
    industry_state: Literal[
        "OBSERVED",
        "NOT_ATTEMPTED",
        "UNSUPPORTED",
        "INSUFFICIENT_EVIDENCE",
        "CONFLICTED",
    ],
    industry_reasons: tuple[str, ...],
) -> tuple[CurrentPriceContextFeatureV1, ...]:
    structure_ready = state == "OBSERVED" and all(
        item.structure is not None for item in members
    )
    direction_ready = state == "OBSERVED" and all(
        item.direction is not None for item in members
    )
    breadth_ready = breadth is not None and breadth.label is not None

    def raw_feature(question: str, ready: bool) -> CurrentPriceContextFeatureV1:
        withheld_reasons = reasons or tuple(
            dict.fromkeys(item.reason for item in members if item.reason is not None)
        )
        return CurrentPriceContextFeatureV1(
            question,
            "OBSERVED"
            if ready
            else (state if state != "OBSERVED" else "INSUFFICIENT_EVIDENCE"),
            () if ready else withheld_reasons or ("MEMBER_EVIDENCE_UNAVAILABLE",),
            readiness="READY" if ready else "WITHHELD",
        )

    return (
        raw_feature("RAW_MARKET_STRUCTURE", structure_ready),
        raw_feature("RAW_20_SESSION_DIRECTION", direction_ready),
        raw_feature("RAW_COHORT_BREADTH", breadth_ready),
        CurrentPriceContextFeatureV1(
            "RAW_INDUSTRY_PARTICIPATION",
            cast(
                Literal[
                    "OBSERVED",
                    "UNSUPPORTED",
                    "DEPENDENCY_BLOCKED",
                    "INSUFFICIENT_EVIDENCE",
                    "NOT_ATTEMPTED",
                ],
                "INSUFFICIENT_EVIDENCE"
                if industry_state in ("NOT_ATTEMPTED", "CONFLICTED")
                else industry_state,
            ),
            () if industry_state == "OBSERVED" else industry_reasons,
            support="UNSUPPORTED" if industry_state == "UNSUPPORTED" else "SUPPORTED",
            readiness="READY" if industry_state == "OBSERVED" else "WITHHELD",
        ),
    )


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def _reference_from_value(value: object) -> CurrentIndustryArchiveReferenceV1 | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise ValueError
    reference = cast(dict[str, object], value)
    if set(reference) != {
        "contract_version",
        "snapshot_identity_sha256",
        "retained_identity_sha256",
    }:
        raise ValueError
    return CurrentIndustryArchiveReferenceV1(
        contract_version=cast(
            Literal["current-industry-archive-reference@v1"],
            reference["contract_version"],
        ),
        snapshot_identity_sha256=cast(str, reference["snapshot_identity_sha256"]),
        retained_identity_sha256=cast(str, reference["retained_identity_sha256"]),
    )


def _members_from_value(value: object) -> tuple[CurrentPriceContextMemberV1, ...]:
    if type(value) is not list:
        raise ValueError
    result: list[CurrentPriceContextMemberV1] = []
    for item in cast(list[object], value):
        if type(item) is not dict:
            raise ValueError
        member = cast(dict[str, object], item)
        if set(member) != {
            "isin",
            "exchange",
            "instrument_type",
            "segment",
            "effective_symbol",
            "valid_from",
            "valid_through",
        }:
            raise ValueError
        result.append(
            CurrentPriceContextMemberV1(
                isin=cast(str, member["isin"]),
                exchange=cast(Literal["NSE"], member["exchange"]),
                instrument_type=cast(Literal["EQUITY"], member["instrument_type"]),
                segment=cast(Literal["EQ"], member["segment"]),
                effective_symbol=cast(str, member["effective_symbol"]),
                valid_from=date.fromisoformat(cast(str, member["valid_from"])),
                valid_through=date.fromisoformat(cast(str, member["valid_through"])),
            )
        )
    return tuple(result)


def _parse_instant(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError("current price context timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise ValueError("current price context timestamp is invalid") from None
    if parsed.tzinfo is not UTC:
        raise ValueError("current price context timestamp is invalid")
    return parsed


def _utc(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is UTC


def _digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _wire(value: object) -> object:
    if type(value) is datetime:
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if type(value) is date:
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        instance = cast(Any, value)
        return {
            str(item.name): _wire(getattr(instance, item.name))
            for item in fields(instance)
        }
    if type(value) is tuple:
        return [_wire(item) for item in cast(tuple[object, ...], value)]
    if type(value) is dict:
        return {
            str(key): _wire(item)
            for key, item in cast(dict[object, object], value).items()
        }
    return value


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field")
        value[key] = item
    return value


def _without_request_identity(value: CurrentPriceContextRequestV1) -> dict[str, object]:
    return {
        item.name: getattr(value, item.name)
        for item in fields(value)
        if item.name != "request_identity_sha256"
    }


def _digest_value(value: object) -> str:
    return hashlib.sha256(_canonical(_wire(value))).hexdigest()


def _without_identity(value: CurrentPriceContextResultV1) -> dict[str, object]:
    return {
        item.name: getattr(value, item.name)
        for item in fields(value)
        if item.name != "result_identity_sha256"
    }
