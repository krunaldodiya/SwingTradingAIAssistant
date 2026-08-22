"""Aggregate-only current supplied-cohort Industry Participation V1."""

from __future__ import annotations

import hashlib
import importlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Final, Literal, cast

from swing_trading_ai_assistant.market_data.adjusted_daily import (
    AdjustedDailyCloseHandoffV2,
)
from swing_trading_ai_assistant.market_data.current_corporate_action_screen import (
    PublishedCurrentCorporateActionScreenV1,
)
from swing_trading_ai_assistant.market_data.current_industry_classification import (
    _CLASSIFICATION_RUNTIME_IDENTITY,  # pyright: ignore[reportPrivateUsage]
    _PARSED_SEAL,  # pyright: ignore[reportPrivateUsage]
    CLASSIFICATION_SCHEMA_IDENTITY_SHA256,
    CurrentIndustryClassificationFailureV1,
    RetainedCurrentIndustrySnapshotV1,
    _archive_minted_retained,  # pyright: ignore[reportPrivateUsage]
    _field,  # pyright: ignore[reportPrivateUsage]
    _identity_labels_safe,  # pyright: ignore[reportPrivateUsage]
    _industry,  # pyright: ignore[reportPrivateUsage]
    _PrivateIndustryRow,  # pyright: ignore[reportPrivateUsage]
    _valid_isin,  # pyright: ignore[reportPrivateUsage]
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)
from swing_trading_ai_assistant.market_regime.current_supplied_cohort import (
    CurrentSuppliedCohortMarketRegimeReportV1,
    PrivateCurrentCohortArchiveGridProjectionV1,
)
from swing_trading_ai_assistant.market_regime.current_supplied_cohort_v2 import (
    _DIRECTION_SEAL,  # pyright: ignore[reportPrivateUsage]
    _HANDOFF_SEAL,  # pyright: ignore[reportPrivateUsage]
    _V2_RUNTIME_IDENTITY,  # pyright: ignore[reportPrivateUsage]
    CurrentSuppliedCohortMarketRegimeReportV2,
    _CurrentSuppliedCohortMemberDirectionHandoffV2,  # pyright: ignore[reportPrivateUsage]
    _CurrentSuppliedCohortMemberDirectionV2,  # pyright: ignore[reportPrivateUsage]
    _evaluate_current_supplied_cohort_market_regime_with_handoff_v2,  # pyright: ignore[reportPrivateUsage]
)
from swing_trading_ai_assistant.market_regime.current_supplied_cohort_v2 import (
    CALCULATION_IDENTITY_SHA256 as _V2_CALCULATION_IDENTITY,  # pyright: ignore[reportPrivateUsage]
)
from swing_trading_ai_assistant.market_regime.current_supplied_cohort_v2 import (
    SCHEMA_IDENTITY_SHA256 as _V2_SCHEMA_IDENTITY,  # pyright: ignore[reportPrivateUsage]
)

CONTRACT_VERSION: Final = "current-supplied-cohort-industry-participation@v1"
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_RUNTIME_MANIFEST_MODULE: Final = "swing_trading_ai_assistant.sector_analysis.current_industry_participation_runtime_identity_manifest"
_RUNTIME_MANIFEST: Final = "src/swing_trading_ai_assistant/sector_analysis/current_industry_participation_runtime_identity_manifest.py"
_RUNTIME_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/adjusted_daily/__init__.py",
    "src/swing_trading_ai_assistant/market_data/adjusted_daily/service.py",
    "src/swing_trading_ai_assistant/market_data/current_corporate_action_screen.py",
    "src/swing_trading_ai_assistant/market_data/current_industry_classification.py",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py",
    "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort.py",
    "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_v2.py",
    "src/swing_trading_ai_assistant/sector_analysis/__init__.py",
    "src/swing_trading_ai_assistant/sector_analysis/current_industry_participation.py",
)
_REASON_ORDER: Final = (
    "MARKET_REGIME_UNAVAILABLE",
    "CLASSIFICATION_ARTIFACT_MISSING",
    "CLASSIFICATION_ARTIFACT_MALFORMED",
    "CLASSIFICATION_SOURCE_UNSUPPORTED",
    "CLASSIFICATION_TIER_UNSUPPORTED",
    "CLASSIFICATION_MEMBER_UNSUPPORTED",
    "CLASSIFICATION_AMBIGUOUS",
    "CLASSIFICATION_CONFLICTING",
    "COHORT_BINDING_MISMATCH",
    "MEMBER_IDENTITY_MISMATCH",
    "CLASSIFICATION_FUTURE_KNOWN",
    "CLASSIFICATION_SESSION_STALE",
    "CLASSIFICATION_ARCHIVE_FAILED",
)

_IST: Final = timezone(timedelta(hours=5, minutes=30))
_REPORT_SEAL: Final = object()


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n"
    )


def _identity(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _instant(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _source_sha(relative: str) -> str:
    names = {
        "src/swing_trading_ai_assistant/market_data/adjusted_daily/__init__.py": (
            "swing_trading_ai_assistant.market_data.adjusted_daily"
        ),
        "src/swing_trading_ai_assistant/market_data/adjusted_daily/service.py": (
            "swing_trading_ai_assistant.market_data.adjusted_daily.service"
        ),
        "src/swing_trading_ai_assistant/market_data/current_corporate_action_screen.py": (
            "swing_trading_ai_assistant.market_data.current_corporate_action_screen"
        ),
        "src/swing_trading_ai_assistant/market_data/current_industry_classification.py": (
            "swing_trading_ai_assistant.market_data.current_industry_classification"
        ),
        "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py": (
            "swing_trading_ai_assistant.market_data.runtime_source_verifier"
        ),
        "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort.py": (
            "swing_trading_ai_assistant.market_regime.current_supplied_cohort"
        ),
        "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_v2.py": (
            "swing_trading_ai_assistant.market_regime.current_supplied_cohort_v2"
        ),
        "src/swing_trading_ai_assistant/sector_analysis/__init__.py": (
            "swing_trading_ai_assistant.sector_analysis"
        ),
        "src/swing_trading_ai_assistant/sector_analysis/current_industry_participation.py": (
            __name__
        ),
        _RUNTIME_MANIFEST: _RUNTIME_MANIFEST_MODULE,
    }
    source = Path(__file__)
    root = source.parent.parent
    if not source.is_absolute() or root.name != "swing_trading_ai_assistant":
        raise ValueError("industry participation runtime identity invalid")
    try:
        return runtime_source_sha256(names[relative], root, relative)
    except (KeyError, ValueError):
        raise ValueError("industry participation runtime identity invalid") from None


def current_industry_participation_runtime_code_identity_v1() -> str:
    try:
        raw = importlib.import_module(
            _RUNTIME_MANIFEST_MODULE
        ).CURRENT_INDUSTRY_PARTICIPATION_RUNTIME_SOURCE_DIGESTS_V1
    except (AttributeError, ImportError):
        raise ValueError("industry participation runtime identity invalid") from None
    if type(raw) is not dict:
        raise ValueError("industry participation runtime identity invalid")
    mapping = cast(dict[str, object], raw)
    if tuple(mapping) != _RUNTIME_SOURCES or any(
        type(digest) is not str
        or _DIGEST.fullmatch(digest) is None
        or _source_sha(path) != digest
        for path, digest in mapping.items()
    ):
        raise ValueError("industry participation runtime identity invalid")
    manifest_digest = _source_sha(_RUNTIME_MANIFEST)
    composite = b"".join(
        path.encode() + b"\0" + cast(str, mapping[path]).encode() + b"\0"
        for path in _RUNTIME_SOURCES
    )
    return hashlib.sha256(
        composite
        + _RUNTIME_MANIFEST.encode()
        + b"\0"
        + manifest_digest.encode()
        + b"\0"
    ).hexdigest()


_PARTICIPATION_RUNTIME_IDENTITY: Final = (
    current_industry_participation_runtime_code_identity_v1()
)


SCHEMA_IDENTITY_SHA256: Final = _identity(
    {
        "contract_version": CONTRACT_VERSION,
        "failure_fields": ["evidence_state", "industries", "reasons"],
        "industry_count_fields": [
            "industry",
            "member_count",
            "advances",
            "declines",
            "unchanged",
        ],
        "report_fields": [
            "contract_version",
            "schema_identity_sha256",
            "calculation_identity_sha256",
            "runtime_code_identity_sha256",
            "market_regime_report_identity_sha256",
            "market_regime_handoff_identity_sha256",
            "classification_input_identity_sha256",
            "classification_schema_identity_sha256",
            "artifact_sha256",
            "artifact_revision",
            "snapshot_identity_sha256",
            "archive_identity_sha256",
            "archive_receipt_identity_sha256",
            "snapshot_runtime_code_identity_sha256",
            "cohort_identity_sha256",
            "cohort_size",
            "decision_cutoff",
            "decision_session",
            "comparison_session",
            "source_url",
            "source_authority",
            "classification_tier",
            "known_at",
            "publisher_published_at",
            "publisher_effective_from",
            "publisher_effective_through",
            "publisher_revision",
            "market_regime_advances",
            "market_regime_declines",
            "market_regime_unchanged",
            "evidence_state",
            "industries",
            "reasons",
            "report_identity_sha256",
        ],
    }
)
CALCULATION_IDENTITY_SHA256: Final = _identity(
    {
        "contract_version": CONTRACT_VERSION,
        "directions": ["ADVANCE", "DECLINE", "UNCHANGED"],
        "outcomes": [
            "OBSERVED",
            "MALFORMED_EVIDENCE",
            "UNSUPPORTED_CAPABILITY",
            "INSUFFICIENT_EVIDENCE",
        ],
        "reason_order": list(_REASON_ORDER),
        "required_evidence": [
            "exact_market_regime_v2_report_and_sealed_handoff",
            "sealed_retained_classification",
            "same_ist_decision_session",
        ],
    }
)


@dataclass(frozen=True, slots=True)
class IndustryCountV1:
    industry: str
    member_count: int
    advances: int
    declines: int
    unchanged: int

    def __post_init__(self) -> None:
        if (
            type(self.industry) is not str
            or not self.industry
            or any(
                type(value) is not int or value < 0
                for value in (
                    self.member_count,
                    self.advances,
                    self.declines,
                    self.unchanged,
                )
            )
            or self.member_count != self.advances + self.declines + self.unchanged
        ):
            raise ValueError("industry count invalid")


@dataclass(frozen=True, slots=True)
class CurrentIndustryParticipationFailureV1:
    evidence_state: Literal[
        "MALFORMED_EVIDENCE", "UNSUPPORTED_CAPABILITY", "INSUFFICIENT_EVIDENCE"
    ]
    reasons: tuple[str, ...]
    industries: None = None

    def __post_init__(self) -> None:
        reasons = _ordered(self.reasons)
        if self.evidence_state != _state(reasons):
            raise ValueError("industry participation failure invalid")
        object.__setattr__(self, "reasons", reasons)

    def canonical_json_bytes(self) -> bytes:
        return _canonical(
            {
                "evidence_state": self.evidence_state,
                "industries": None,
                "reasons": list(self.reasons),
            }
        )


@dataclass(frozen=True, slots=True, init=False)
class CurrentIndustryParticipationReportV1:
    contract_version: Literal["current-supplied-cohort-industry-participation@v1"]
    schema_identity_sha256: str
    calculation_identity_sha256: str
    runtime_code_identity_sha256: str
    market_regime_report_identity_sha256: str
    market_regime_handoff_identity_sha256: str
    classification_input_identity_sha256: str
    classification_schema_identity_sha256: str
    artifact_sha256: str
    artifact_revision: str
    snapshot_identity_sha256: str
    archive_identity_sha256: str
    archive_receipt_identity_sha256: str
    snapshot_runtime_code_identity_sha256: str
    cohort_identity_sha256: str
    cohort_size: int
    decision_cutoff: datetime
    decision_session: date
    comparison_session: date
    source_url: str
    source_authority: Literal["NSE_INDICES"]
    classification_tier: Literal["INDUSTRY"]
    known_at: datetime
    publisher_published_at: None
    publisher_effective_from: None
    publisher_effective_through: None
    publisher_revision: None
    market_regime_advances: int
    market_regime_declines: int
    market_regime_unchanged: int
    evidence_state: Literal["OBSERVED"]
    industries: tuple[IndustryCountV1, ...]
    reasons: tuple[()]
    report_identity_sha256: str
    _seal: object = field(repr=False, compare=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("participation report constructor unavailable")

    def canonical_json_bytes(self, *, include_identity: bool = True) -> bytes:
        result = {
            "archive_identity_sha256": self.archive_identity_sha256,
            "archive_receipt_identity_sha256": self.archive_receipt_identity_sha256,
            "artifact_revision": self.artifact_revision,
            "artifact_sha256": self.artifact_sha256,
            "calculation_identity_sha256": self.calculation_identity_sha256,
            "classification_input_identity_sha256": self.classification_input_identity_sha256,
            "classification_schema_identity_sha256": (
                self.classification_schema_identity_sha256
            ),
            "classification_tier": self.classification_tier,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "cohort_size": self.cohort_size,
            "comparison_session": self.comparison_session.isoformat(),
            "contract_version": self.contract_version,
            "decision_cutoff": _instant(self.decision_cutoff),
            "decision_session": self.decision_session.isoformat(),
            "evidence_state": self.evidence_state,
            "industries": [
                {
                    "advances": row.advances,
                    "declines": row.declines,
                    "industry": row.industry,
                    "member_count": row.member_count,
                    "unchanged": row.unchanged,
                }
                for row in self.industries
            ],
            "known_at": _instant(self.known_at),
            "market_regime_advances": self.market_regime_advances,
            "market_regime_declines": self.market_regime_declines,
            "market_regime_handoff_identity_sha256": self.market_regime_handoff_identity_sha256,
            "market_regime_report_identity_sha256": self.market_regime_report_identity_sha256,
            "market_regime_unchanged": self.market_regime_unchanged,
            "reasons": [],
            "publisher_effective_from": None,
            "publisher_effective_through": None,
            "publisher_published_at": None,
            "publisher_revision": None,
            "runtime_code_identity_sha256": self.runtime_code_identity_sha256,
            "schema_identity_sha256": self.schema_identity_sha256,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "snapshot_runtime_code_identity_sha256": (
                self.snapshot_runtime_code_identity_sha256
            ),
            "source_authority": self.source_authority,
            "source_url": self.source_url,
        }
        if include_identity:
            result["report_identity_sha256"] = self.report_identity_sha256
        return _canonical(result)


def reduce_current_industry_participation_v1(
    raw_v1_report: CurrentSuppliedCohortMarketRegimeReportV1,
    raw_private_grid: PrivateCurrentCohortArchiveGridProjectionV1,
    retained_screen: PublishedCurrentCorporateActionScreenV1,
    adjusted_handoff: AdjustedDailyCloseHandoffV2,
    classification: RetainedCurrentIndustrySnapshotV1
    | CurrentIndustryClassificationFailureV1,
) -> CurrentIndustryParticipationReportV1 | CurrentIndustryParticipationFailureV1:
    if (
        type(raw_v1_report) is not CurrentSuppliedCohortMarketRegimeReportV1
        or type(raw_private_grid) is not PrivateCurrentCohortArchiveGridProjectionV1
        or type(retained_screen) is not PublishedCurrentCorporateActionScreenV1
        or type(adjusted_handoff) is not AdjustedDailyCloseHandoffV2
        or type(classification)
        not in (
            RetainedCurrentIndustrySnapshotV1,
            CurrentIndustryClassificationFailureV1,
        )
    ):
        raise TypeError("industry participation input invalid")
    report, handoff = _evaluate_current_supplied_cohort_market_regime_with_handoff_v2(
        raw_v1_report, raw_private_grid, retained_screen, adjusted_handoff
    )
    retained, reasons = _admit_reducer_inputs(report, handoff, classification)
    if reasons:
        return CurrentIndustryParticipationFailureV1(_state(reasons), reasons)
    if retained is None or handoff is None:
        raise AssertionError("validated participation inputs missing")
    industries, failure = _aggregate_industries(retained, handoff, report)
    if failure is not None:
        return failure
    return _observed_report(report, handoff, retained, industries)


def _admit_reducer_inputs(
    report: CurrentSuppliedCohortMarketRegimeReportV2,
    handoff: _CurrentSuppliedCohortMemberDirectionHandoffV2 | None,  # pyright: ignore[reportPrivateUsage]
    classification: RetainedCurrentIndustrySnapshotV1
    | CurrentIndustryClassificationFailureV1,
) -> tuple[RetainedCurrentIndustrySnapshotV1 | None, tuple[str, ...]]:
    report_valid = _valid_market_regime_envelope(report)
    market_valid = report_valid and _valid_market_regime(report, handoff)
    reasons = ["MARKET_REGIME_UNAVAILABLE"] if not market_valid else []
    if type(classification) is CurrentIndustryClassificationFailureV1:
        reasons.extend(classification.reasons)
        return None, _ordered(tuple(reasons))
    if type(classification) is not RetainedCurrentIndustrySnapshotV1:
        raise TypeError("industry classification invalid")
    if not _valid_retained(classification):
        reasons.append("COHORT_BINDING_MISMATCH")
    elif report_valid:
        _append_temporal_and_binding_reasons(reasons, classification, report, handoff)
    return (
        classification if not reasons else None,
        () if not reasons else _ordered(tuple(reasons)),
    )


def _append_temporal_and_binding_reasons(
    reasons: list[str],
    classification: RetainedCurrentIndustrySnapshotV1,
    report: CurrentSuppliedCohortMarketRegimeReportV2,
    handoff: _CurrentSuppliedCohortMemberDirectionHandoffV2 | None,  # pyright: ignore[reportPrivateUsage]
) -> None:
    if not _same_session(classification, report):
        reasons.append("CLASSIFICATION_SESSION_STALE")
    if classification.known_at > report.decision_cutoff:
        reasons.append("CLASSIFICATION_FUTURE_KNOWN")
    if (
        classification.cohort_identity_sha256 != report.cohort_identity_sha256
        or classification.cohort_size != report.cohort_size
        or (
            handoff is not None
            and not _binding_matches(report, handoff, classification)
        )
    ):
        reasons.append("COHORT_BINDING_MISMATCH")


def _aggregate_industries(
    retained: RetainedCurrentIndustrySnapshotV1,
    handoff: _CurrentSuppliedCohortMemberDirectionHandoffV2,  # pyright: ignore[reportPrivateUsage]
    report: CurrentSuppliedCohortMarketRegimeReportV2,
) -> tuple[
    tuple[IndustryCountV1, ...],
    CurrentIndustryParticipationFailureV1 | None,
]:
    classifications = {
        (row.isin, row.exchange, row.effective_symbol): row.industry
        for row in _retained_rows(retained)
    }
    members = {
        (member.isin, member.exchange, member.effective_symbol)
        for member in handoff.members
    }
    if len(classifications) != retained.cohort_size or set(classifications) != members:
        return (), CurrentIndustryParticipationFailureV1(
            "MALFORMED_EVIDENCE", ("MEMBER_IDENTITY_MISMATCH",)
        )
    totals: dict[str, list[int]] = {}
    for member in handoff.members:
        values = totals.setdefault(
            classifications[(member.isin, member.exchange, member.effective_symbol)],
            [0, 0, 0, 0],
        )
        values[0] += 1
        values[{"ADVANCE": 1, "DECLINE": 2, "UNCHANGED": 3}[member.direction]] += 1
    industries = tuple(
        IndustryCountV1(industry, *totals[industry]) for industry in sorted(totals)
    )
    if (
        sum(row.member_count for row in industries),
        sum(row.advances for row in industries),
        sum(row.declines for row in industries),
        sum(row.unchanged for row in industries),
    ) != (report.cohort_size, report.advances, report.declines, report.unchanged):
        return (), CurrentIndustryParticipationFailureV1(
            "MALFORMED_EVIDENCE", ("COHORT_BINDING_MISMATCH",)
        )
    return industries, None


def _observed_report(
    report: CurrentSuppliedCohortMarketRegimeReportV2,
    handoff: _CurrentSuppliedCohortMemberDirectionHandoffV2,  # pyright: ignore[reportPrivateUsage]
    retained: RetainedCurrentIndustrySnapshotV1,
    industries: tuple[IndustryCountV1, ...],
) -> CurrentIndustryParticipationReportV1:
    if (
        report.comparison_session is None
        or report.advances is None
        or report.declines is None
        or report.unchanged is None
    ):
        raise AssertionError("observed regime report incomplete")

    return _with_identity(
        _report(
            contract_version=CONTRACT_VERSION,
            schema_identity_sha256=SCHEMA_IDENTITY_SHA256,
            calculation_identity_sha256=CALCULATION_IDENTITY_SHA256,
            runtime_code_identity_sha256=_PARTICIPATION_RUNTIME_IDENTITY,
            market_regime_report_identity_sha256=report.report_identity_sha256,
            market_regime_handoff_identity_sha256=handoff.handoff_identity_sha256,
            classification_schema_identity_sha256=retained.schema_identity_sha256,
            classification_input_identity_sha256=retained.input_identity_sha256,
            artifact_sha256=retained.artifact_sha256,
            artifact_revision=retained.artifact_revision,
            snapshot_identity_sha256=retained.snapshot_identity_sha256,
            archive_identity_sha256=retained.archive_identity_sha256,
            archive_receipt_identity_sha256=retained.archive_receipt_identity_sha256,
            snapshot_runtime_code_identity_sha256=(
                retained.snapshot_runtime_code_identity_sha256
            ),
            cohort_identity_sha256=retained.cohort_identity_sha256,
            cohort_size=retained.cohort_size,
            decision_cutoff=report.decision_cutoff,
            decision_session=report.decision_session,
            comparison_session=report.comparison_session,
            source_url="https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv",
            source_authority="NSE_INDICES",
            classification_tier="INDUSTRY",
            known_at=retained.known_at,
            publisher_published_at=None,
            publisher_effective_from=None,
            publisher_effective_through=None,
            publisher_revision=None,
            market_regime_advances=report.advances,
            market_regime_declines=report.declines,
            market_regime_unchanged=report.unchanged,
            evidence_state="OBSERVED",
            industries=industries,
            reasons=(),
            report_identity_sha256="",
        )
    )


def _report(**values: object) -> CurrentIndustryParticipationReportV1:
    result = object.__new__(CurrentIndustryParticipationReportV1)
    for name, value in values.items():
        object.__setattr__(result, name, value)
    object.__setattr__(result, "_seal", _REPORT_SEAL)
    return result


def _with_identity(
    report: CurrentIndustryParticipationReportV1,
) -> CurrentIndustryParticipationReportV1:
    identity = hashlib.sha256(
        report.canonical_json_bytes(include_identity=False)
    ).hexdigest()
    values = {
        name: getattr(report, name)
        for name in CurrentIndustryParticipationReportV1.__dataclass_fields__
        if name != "_seal"
    }
    values["report_identity_sha256"] = identity
    result = _report(**values)
    if not _valid_observed_report(result):
        raise ValueError("participation report invalid")
    return result


def _valid_observed_report(report: CurrentIndustryParticipationReportV1) -> bool:
    if (
        not _has_seal(report, _REPORT_SEAL)
        or report.contract_version != CONTRACT_VERSION
        or report.schema_identity_sha256 != SCHEMA_IDENTITY_SHA256
        or report.calculation_identity_sha256 != CALCULATION_IDENTITY_SHA256
        or report.runtime_code_identity_sha256 != _PARTICIPATION_RUNTIME_IDENTITY
        or report.classification_schema_identity_sha256
        != CLASSIFICATION_SCHEMA_IDENTITY_SHA256
        or not all(
            _valid_digest(value)
            for value in (
                report.market_regime_report_identity_sha256,
                report.market_regime_handoff_identity_sha256,
                report.classification_input_identity_sha256,
                report.classification_schema_identity_sha256,
                report.artifact_sha256,
                report.snapshot_identity_sha256,
                report.archive_identity_sha256,
                report.archive_receipt_identity_sha256,
                report.snapshot_runtime_code_identity_sha256,
                report.cohort_identity_sha256,
                report.report_identity_sha256,
            )
        )
        or report.artifact_revision != f"sha256:{report.artifact_sha256}"
        or report.source_url
        != "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv"
        or report.source_authority != "NSE_INDICES"
        or report.classification_tier != "INDUSTRY"
        or report.evidence_state != "OBSERVED"
        or report.reasons != ()
        or any(
            item is not None
            for item in (
                report.publisher_published_at,
                report.publisher_effective_from,
                report.publisher_effective_through,
                report.publisher_revision,
            )
        )
        or type(report.decision_cutoff) is not datetime
        or report.decision_cutoff.tzinfo is not UTC
        or type(report.known_at) is not datetime
        or report.known_at.tzinfo is not UTC
        or not all(
            type(item) is date
            for item in (report.decision_session, report.comparison_session)
        )
        or type(report.industries) is not tuple
        or tuple(row.industry for row in report.industries)
        != tuple(sorted(row.industry for row in report.industries))
        or len({row.industry for row in report.industries}) != len(report.industries)
        or any(type(row) is not IndustryCountV1 for row in report.industries)
        or (
            sum(row.member_count for row in report.industries),
            sum(row.advances for row in report.industries),
            sum(row.declines for row in report.industries),
            sum(row.unchanged for row in report.industries),
        )
        != (
            report.cohort_size,
            report.market_regime_advances,
            report.market_regime_declines,
            report.market_regime_unchanged,
        )
    ):
        return False
    return (
        report.report_identity_sha256
        == hashlib.sha256(
            report.canonical_json_bytes(include_identity=False)
        ).hexdigest()
    )


def _valid_market_regime_envelope(report: object) -> bool:
    return (
        type(report) is CurrentSuppliedCohortMarketRegimeReportV2
        and report.contract_version == "current-supplied-cohort-market-regime@v2"
        and report.evidence_state in {"OBSERVED", "INSUFFICIENT_EVIDENCE"}
        and type(report.reasons) is tuple
        and all(type(reason) is str and reason for reason in report.reasons)
        and report.schema_identity_sha256 == _V2_SCHEMA_IDENTITY
        and report.calculation_identity_sha256 == _V2_CALCULATION_IDENTITY
        and report.runtime_code_identity_sha256 == _V2_RUNTIME_IDENTITY
        and _valid_digest(report.report_identity_sha256)
        and _valid_digest(report.raw_report_identity_sha256)
        and _valid_digest(report.cohort_identity_sha256)
        and type(report.cohort_size) is int
        and 1 <= report.cohort_size <= 50
        and type(report.decision_cutoff) is datetime
        and report.decision_cutoff.tzinfo is UTC
        and type(report.decision_session) is date
        and report.report_identity_sha256
        == _identity(report.value(include_identity=False))
        and (
            report.evidence_state != "INSUFFICIENT_EVIDENCE"
            or (
                report.comparison_session is None
                and report.regime_label is None
                and report.advances is None
                and report.declines is None
                and report.unchanged is None
                and bool(report.reasons)
            )
        )
    )


def _valid_market_regime(
    report: CurrentSuppliedCohortMarketRegimeReportV2,
    handoff: _CurrentSuppliedCohortMemberDirectionHandoffV2 | None,  # pyright: ignore[reportPrivateUsage]
) -> bool:
    if (
        not _valid_market_regime_envelope(report)
        or handoff is None
        or type(handoff) is not _CurrentSuppliedCohortMemberDirectionHandoffV2
        or not _has_seal(handoff, _HANDOFF_SEAL)
        or report.evidence_state != "OBSERVED"
        or report.reasons != ()
        or report.comparison_session is None
        or report.regime_label
        not in {"BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"}
        or report.advances is None
        or report.declines is None
        or report.unchanged is None
        or report.report_identity_sha256 != handoff.paired_report_identity_sha256
        or not all(
            _valid_digest(value)
            for value in (
                report.corporate_action_screen_identity_sha256,
                report.adjusted_handoff_identity_sha256,
                handoff.raw_report_identity_sha256,
                handoff.corporate_action_screen_identity_sha256,
                handoff.adjusted_handoff_identity_sha256,
                handoff.cohort_identity_sha256,
                handoff.handoff_identity_sha256,
            )
        )
        or report.raw_report_identity_sha256 != handoff.raw_report_identity_sha256
        or report.corporate_action_screen_identity_sha256
        != handoff.corporate_action_screen_identity_sha256
        or report.adjusted_handoff_identity_sha256
        != handoff.adjusted_handoff_identity_sha256
    ):
        return False
    if (
        report.contract_version != "current-supplied-cohort-market-regime@v2"
        or report.cohort_size != handoff.cohort_size
        or report.cohort_identity_sha256 != handoff.cohort_identity_sha256
        or report.decision_cutoff != handoff.decision_cutoff
        or report.decision_session != handoff.decision_session
        or report.comparison_session != handoff.comparison_session
        or type(handoff.members) is not tuple
        or len(handoff.members) != report.cohort_size
    ):
        return False
    members = handoff.members
    if (
        tuple(member.isin for member in members)
        != tuple(sorted(member.isin for member in members))
        or len({member.isin for member in members}) != len(members)
        or any(
            type(member) is not _CurrentSuppliedCohortMemberDirectionV2
            or not _has_seal(member, _DIRECTION_SEAL)
            or member.exchange not in {"NSE", "BSE"}
            or not _field(member.effective_symbol)
            for member in members
        )
    ):
        return False
    handoff_value = {
        "adjusted_handoff_identity_sha256": handoff.adjusted_handoff_identity_sha256,
        "cohort_identity_sha256": handoff.cohort_identity_sha256,
        "cohort_size": handoff.cohort_size,
        "comparison_session": handoff.comparison_session.isoformat(),
        "corporate_action_screen_identity_sha256": handoff.corporate_action_screen_identity_sha256,
        "decision_cutoff": handoff.decision_cutoff.isoformat(),
        "decision_session": handoff.decision_session.isoformat(),
        "members": [
            {
                "direction": member.direction,
                "effective_symbol": member.effective_symbol,
                "exchange": member.exchange,
                "isin": member.isin,
            }
            for member in members
        ],
        "paired_report_identity_sha256": handoff.paired_report_identity_sha256,
        "raw_report_identity_sha256": handoff.raw_report_identity_sha256,
    }
    return handoff.handoff_identity_sha256 == _identity(handoff_value) and (
        sum(member.direction == "ADVANCE" for member in members),
        sum(member.direction == "DECLINE" for member in members),
        sum(member.direction == "UNCHANGED" for member in members),
    ) == (report.advances, report.declines, report.unchanged)


def _has_seal(value: object, expected: object) -> bool:
    return getattr(value, "_seal", None) is expected


def _retained_rows(
    value: RetainedCurrentIndustrySnapshotV1,
) -> tuple[_PrivateIndustryRow, ...]:
    return cast(tuple[_PrivateIndustryRow, ...], getattr(value, "_private_rows", ()))


def _valid_retained(value: RetainedCurrentIndustrySnapshotV1) -> bool:
    rows = _retained_rows(value)
    if (
        not _archive_minted_retained(value)
        or value.evidence_state != "RETAINED"
        or value.schema_identity_sha256 != CLASSIFICATION_SCHEMA_IDENTITY_SHA256
        or not all(
            _valid_digest(item)
            for item in (
                value.input_identity_sha256,
                value.artifact_sha256,
                value.snapshot_identity_sha256,
                value.archive_identity_sha256,
                value.archive_receipt_identity_sha256,
                value.retained_identity_sha256,
                value.snapshot_runtime_code_identity_sha256,
                value.cohort_identity_sha256,
            )
        )
        or value.artifact_revision != f"sha256:{value.artifact_sha256}"
        or value.snapshot_runtime_code_identity_sha256
        != _CLASSIFICATION_RUNTIME_IDENTITY
        or type(value.cohort_size) is not int
        or not 1 <= value.cohort_size <= 50
        or any(
            item is not None
            for item in (
                value.publisher_published_at,
                value.publisher_effective_from,
                value.publisher_effective_through,
                value.publisher_revision,
            )
        )
        or type(value.known_at) is not datetime
        or value.known_at.tzinfo is not UTC
        or type(rows) is not tuple
        or len(rows) != value.cohort_size
        or tuple(row.isin for row in rows) != tuple(sorted(row.isin for row in rows))
        or len({(row.isin, row.exchange, row.effective_symbol) for row in rows})
        != value.cohort_size
        or not _identity_labels_safe(rows)
        or any(
            type(row) is not _PrivateIndustryRow
            or not _has_seal(row, _PARSED_SEAL)
            or row.exchange != "NSE"
            or row.effective_symbol != row.symbol
            or not _valid_isin(row.isin)
            or not _industry(row.industry)
            or not _field(row.symbol)
            for row in rows
        )
    ):
        return False
    snapshot_value = {
        "artifact_sha256": value.artifact_sha256,
        "artifact_revision": value.artifact_revision,
        "cohort_identity_sha256": value.cohort_identity_sha256,
        "cohort_size": value.cohort_size,
        "evidence_state": "PROJECTED",
        "input_identity_sha256": value.input_identity_sha256,
        "private_rows": [
            {
                "effective_symbol": row.effective_symbol,
                "exchange": row.exchange,
                "industry": row.industry,
                "isin": row.isin,
                "symbol": row.symbol,
            }
            for row in rows
        ],
        "runtime_code_identity_sha256": value.snapshot_runtime_code_identity_sha256,
        "schema_identity_sha256": value.schema_identity_sha256,
    }
    archive_identity = _identity(
        {
            "raw_artifact_sha256": value.artifact_sha256,
            "snapshot_identity_sha256": value.snapshot_identity_sha256,
        }
    )
    receipt = _identity(
        {
            "archive_identity_sha256": archive_identity,
            "artifact_sha256": value.artifact_sha256,
            "input_identity_sha256": value.input_identity_sha256,
            "known_at": _instant(value.known_at),
            "snapshot_identity_sha256": value.snapshot_identity_sha256,
        }
    )
    retained_value = {
        "archive_identity_sha256": value.archive_identity_sha256,
        "archive_receipt_identity_sha256": value.archive_receipt_identity_sha256,
        "artifact_revision": value.artifact_revision,
        "artifact_sha256": value.artifact_sha256,
        "cohort_identity_sha256": value.cohort_identity_sha256,
        "cohort_size": value.cohort_size,
        "evidence_state": "RETAINED",
        "input_identity_sha256": value.input_identity_sha256,
        "known_at": _instant(value.known_at),
        "publisher_effective_from": None,
        "publisher_effective_through": None,
        "publisher_published_at": None,
        "publisher_revision": None,
        "schema_identity_sha256": value.schema_identity_sha256,
        "snapshot_identity_sha256": value.snapshot_identity_sha256,
        "snapshot_runtime_code_identity_sha256": value.snapshot_runtime_code_identity_sha256,
    }
    return (
        value.snapshot_identity_sha256 == _identity(snapshot_value)
        and value.archive_identity_sha256 == archive_identity
        and value.archive_receipt_identity_sha256 == receipt
        and value.retained_identity_sha256 == _identity(retained_value)
    )


def _same_session(
    classification: RetainedCurrentIndustrySnapshotV1,
    report: CurrentSuppliedCohortMarketRegimeReportV2,
) -> bool:
    return (
        classification.known_at.astimezone(_IST).date()
        == report.decision_cutoff.astimezone(_IST).date()
        == report.decision_session
    )


def _binding_matches(
    report: CurrentSuppliedCohortMarketRegimeReportV2,
    handoff: _CurrentSuppliedCohortMemberDirectionHandoffV2,  # pyright: ignore[reportPrivateUsage]
    classification: RetainedCurrentIndustrySnapshotV1,
) -> bool:
    return (
        report.cohort_identity_sha256 == classification.cohort_identity_sha256
        and report.cohort_size == classification.cohort_size
        and handoff.cohort_identity_sha256 == classification.cohort_identity_sha256
        and handoff.cohort_size == classification.cohort_size
    )


def _valid_digest(value: object) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _ordered(reasons: tuple[str, ...]) -> tuple[str, ...]:
    if not reasons or any(reason not in _REASON_ORDER for reason in reasons):
        raise ValueError("industry participation reasons invalid")
    return tuple(reason for reason in _REASON_ORDER if reason in reasons)


def _state(
    reasons: tuple[str, ...],
) -> Literal["MALFORMED_EVIDENCE", "UNSUPPORTED_CAPABILITY", "INSUFFICIENT_EVIDENCE"]:
    if any(
        reason
        in {
            "CLASSIFICATION_ARTIFACT_MALFORMED",
            "CLASSIFICATION_AMBIGUOUS",
            "CLASSIFICATION_CONFLICTING",
            "COHORT_BINDING_MISMATCH",
            "MEMBER_IDENTITY_MISMATCH",
        }
        for reason in reasons
    ):
        return "MALFORMED_EVIDENCE"
    if any(
        reason
        in {
            "CLASSIFICATION_SOURCE_UNSUPPORTED",
            "CLASSIFICATION_TIER_UNSUPPORTED",
            "CLASSIFICATION_MEMBER_UNSUPPORTED",
        }
        for reason in reasons
    ):
        return "UNSUPPORTED_CAPABILITY"
    return "INSUFFICIENT_EVIDENCE"
