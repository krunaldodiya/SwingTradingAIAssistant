"""Deterministic exploratory census reports over strict historical evidence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum
from typing import Final

_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_CODE_SHA: Final = re.compile(r"[0-9a-f]{40}\Z")
_WARNINGS: Final = (
    ("EXPLORATORY_DEVELOPMENT_ONLY", "This is a bounded development experiment."),
    (
        "NO_PREDICTION_OR_ACCURACY_CLAIM",
        "Historical labels are not forecasts and do not establish model accuracy.",
    ),
    (
        "NO_STRATEGY_OR_PROFITABILITY_ACCEPTANCE",
        "Gross terminal returns do not validate a strategy or future profitability.",
    ),
    ("NO_TRADE_RECOMMENDATION", "This report recommends no security or trade."),
    (
        "SHORT_DEPENDENT_SAMPLE",
        "Short overlapping single-period windows are not independent evidence of repeatability.",
    ),
)


class CensusExecutionStatusV1(StrEnum):
    SUCCEEDED = "SUCCEEDED"


class CensusEvidenceStatusV1(StrEnum):
    OBSERVED = "OBSERVED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class OpportunityCensusReportV1:
    execution_status: CensusExecutionStatusV1
    evidence_status: CensusEvidenceStatusV1
    research_role: str
    requested_stock_session_pairs: int
    eligible_anchor_count: int
    excluded_predeclared_anchor_count: int
    insufficient_anchor_count: int
    primary_reason_counts: tuple[tuple[str, int], ...]
    observed_outcome_count: int
    non_fill_outcome_count: int
    incomplete_horizon_outcome_count: int
    insufficient_outcome_count: int
    ambiguous_outcome_count: int
    strictly_gt_2_percent_count: int
    return_distribution: object | None
    evidence_seal_sha256: str
    configuration_sha256: str
    code_sha: str
    provider_attempt_count: int
    warnings: tuple[tuple[str, str], ...] = _WARNINGS

    def __post_init__(self) -> None:
        counts = (
            self.requested_stock_session_pairs,
            self.eligible_anchor_count,
            self.excluded_predeclared_anchor_count,
            self.insufficient_anchor_count,
            self.observed_outcome_count,
            self.non_fill_outcome_count,
            self.incomplete_horizon_outcome_count,
            self.insufficient_outcome_count,
            self.ambiguous_outcome_count,
            self.strictly_gt_2_percent_count,
            self.provider_attempt_count,
        )
        if (
            self.execution_status is not CensusExecutionStatusV1.SUCCEEDED
            or type(self.evidence_status) is not CensusEvidenceStatusV1
            or self.research_role != "EXPLORATORY_DEVELOPMENT"
            or any(type(value) is not int or value < 0 for value in counts)
            or self.requested_stock_session_pairs
            != self.eligible_anchor_count
            + self.excluded_predeclared_anchor_count
            + self.insufficient_anchor_count
            or self.eligible_anchor_count
            != self.observed_outcome_count
            + self.non_fill_outcome_count
            + self.incomplete_horizon_outcome_count
            + self.insufficient_outcome_count
            + self.ambiguous_outcome_count
            or type(self.primary_reason_counts) is not tuple
            or any(
                type(reason) is not str
                or reason
                not in {
                    "UNIVERSE_NOT_KNOWN_AT_DECISION_CUTOFF",
                    "CORPORATE_ACTION_EVIDENCE_MISSING_OR_STALE",
                }
                or type(count) is not int
                or count < 0
                for reason, count in self.primary_reason_counts
            )
            or len({reason for reason, _ in self.primary_reason_counts})
            != len(self.primary_reason_counts)
            or sum(count for _, count in self.primary_reason_counts)
            != self.insufficient_anchor_count
            or self.strictly_gt_2_percent_count > self.observed_outcome_count
            or (self.observed_outcome_count == 0) != (self.return_distribution is None)
            or self.evidence_status
            is not (
                CensusEvidenceStatusV1.INSUFFICIENT_EVIDENCE
                if self.observed_outcome_count == 0
                else CensusEvidenceStatusV1.OBSERVED
                if self.observed_outcome_count == self.requested_stock_session_pairs
                else CensusEvidenceStatusV1.PARTIAL
            )
            or self.provider_attempt_count != 0
            or self.warnings != _WARNINGS
            or _DIGEST.fullmatch(self.evidence_seal_sha256) is None
            or _DIGEST.fullmatch(self.configuration_sha256) is None
            or _CODE_SHA.fullmatch(self.code_sha) is None
        ):
            raise ValueError("invalid census report")

    def canonical_json_bytes(self) -> bytes:
        value = _report_value(self)
        value["report_identity_sha256"] = self.report_identity_sha256
        return _canonical(value)

    @property
    def report_identity_sha256(self) -> str:
        return hashlib.sha256(_canonical(_report_value(self))).hexdigest()


def build_strict_retained_census_v1(
    *,
    stock_count: int,
    decision_sessions: tuple[date, ...],
    universe_known_at: datetime,
    corporate_action_evidence_available: bool,
    evidence_seal_sha256: str,
    code_sha: str,
    configuration_sha256: str,
) -> OpportunityCensusReportV1:
    if (
        type(stock_count) is not int
        or stock_count != 50
        or type(decision_sessions) is not tuple
        or len(decision_sessions) != 31
        or decision_sessions != tuple(sorted(set(decision_sessions)))
        or type(universe_known_at) is not datetime
        or universe_known_at.tzinfo is None
        or type(corporate_action_evidence_available) is not bool
    ):
        raise ValueError("invalid retained census input")
    cutoff = universe_known_at.astimezone(UTC)
    late_sessions = sum(
        datetime(day.year, day.month, day.day, 10, tzinfo=UTC) < cutoff
        for day in decision_sessions
    )
    late = late_sessions * stock_count
    missing_actions = (
        0
        if corporate_action_evidence_available
        else (len(decision_sessions) * stock_count - late)
    )
    requested = len(decision_sessions) * stock_count
    return OpportunityCensusReportV1(
        CensusExecutionStatusV1.SUCCEEDED,
        CensusEvidenceStatusV1.INSUFFICIENT_EVIDENCE,
        "EXPLORATORY_DEVELOPMENT",
        requested,
        0,
        0,
        requested,
        (
            ("UNIVERSE_NOT_KNOWN_AT_DECISION_CUTOFF", late),
            ("CORPORATE_ACTION_EVIDENCE_MISSING_OR_STALE", missing_actions),
        ),
        0,
        0,
        0,
        0,
        0,
        0,
        None,
        evidence_seal_sha256,
        configuration_sha256,
        code_sha,
        0,
    )


def _report_value(value: OpportunityCensusReportV1) -> dict[str, object]:
    return {
        "ambiguous_outcome_count": value.ambiguous_outcome_count,
        "code_sha": value.code_sha,
        "configuration_sha256": value.configuration_sha256,
        "eligible_anchor_count": value.eligible_anchor_count,
        "evidence_seal_sha256": value.evidence_seal_sha256,
        "evidence_status": value.evidence_status.value,
        "excluded_predeclared_anchor_count": value.excluded_predeclared_anchor_count,
        "execution_status": value.execution_status.value,
        "incomplete_horizon_outcome_count": value.incomplete_horizon_outcome_count,
        "insufficient_anchor_count": value.insufficient_anchor_count,
        "insufficient_outcome_count": value.insufficient_outcome_count,
        "non_fill_outcome_count": value.non_fill_outcome_count,
        "observed_outcome_count": value.observed_outcome_count,
        "primary_reason_counts": [
            {"count": count, "reason": reason}
            for reason, count in value.primary_reason_counts
        ],
        "provider_attempt_count": value.provider_attempt_count,
        "requested_stock_session_pairs": value.requested_stock_session_pairs,
        "research_role": value.research_role,
        "return_distribution": value.return_distribution,
        "strictly_gt_2_percent_count": value.strictly_gt_2_percent_count,
        "warnings": [
            {"code": code, "message": message} for code, message in value.warnings
        ],
    }


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode()


@dataclass(frozen=True, slots=True)
class CensusOutcomeV1:
    symbol: str
    isin: str
    decision_date: date
    state: str
    gross_return_percent: str | None = None
    strictly_gt_2_percent: bool | None = None
    entry_date: date | None = None
    exit_date: date | None = None
    observation_sha256: str | None = None

    def __post_init__(self) -> None:
        observed = self.state == "OBSERVED"
        if (
            self.state
            not in {
                "OBSERVED",
                "NON_FILL",
                "INCOMPLETE_HORIZON",
                "INSUFFICIENT_EVIDENCE",
                "AMBIGUOUS",
            }
            or observed
            != (
                type(self.gross_return_percent) is str
                and type(self.strictly_gt_2_percent) is bool
            )
            or observed
            != (type(self.entry_date) is date and type(self.exit_date) is date)
            or observed
            != (
                type(self.observation_sha256) is str
                and _DIGEST.fullmatch(self.observation_sha256) is not None
            )
        ):
            raise ValueError("invalid census outcome")


@dataclass(frozen=True, slots=True)
class CensusDistributionV1:
    count: int
    minimum: str
    p25: str
    median: str
    p75: str
    mean: str
    maximum: str
    negative_count: int
    zero_count: int
    positive_count: int


@dataclass(frozen=True, slots=True)
class CensusWindowV1:
    symbol: str
    isin: str
    decision_date: date
    entry_date: date
    exit_date: date
    gross_return_percent: str
    observation_sha256: str


@dataclass(frozen=True, slots=True)
class GenericOpportunityCensusV1:
    outcomes: tuple[CensusOutcomeV1, ...]
    observed_count: int
    strictly_gt_2_count: int
    distribution: CensusDistributionV1 | None
    strict_windows: tuple[CensusWindowV1, ...]

    def __post_init__(self) -> None:
        if (
            type(self.outcomes) is not tuple
            or any(type(item) is not CensusOutcomeV1 for item in self.outcomes)
            or self.outcomes
            != tuple(
                sorted(self.outcomes, key=lambda item: (item.decision_date, item.isin))
            )
            or self.observed_count
            != sum(item.state == "OBSERVED" for item in self.outcomes)
            or self.strictly_gt_2_count
            != sum(item.strictly_gt_2_percent is True for item in self.outcomes)
            or (self.observed_count == 0) != (self.distribution is None)
        ):
            raise ValueError("invalid generic census")


def reduce_opportunity_outcomes_v1(
    outcomes: tuple[CensusOutcomeV1, ...],
) -> GenericOpportunityCensusV1:
    if type(outcomes) is not tuple or len(
        {(x.isin, x.decision_date) for x in outcomes}
    ) != len(outcomes):
        raise ValueError("invalid census outcomes")
    ordered = tuple(sorted(outcomes, key=lambda item: (item.decision_date, item.isin)))
    observed = tuple(item for item in ordered if item.state == "OBSERVED")
    values = sorted(
        Decimal(item.gross_return_percent)
        for item in observed
        if item.gross_return_percent is not None
    )
    distribution = None
    if values:

        def render(value: Decimal) -> str:
            return format(
                value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN), ".6f"
            )

        def rank(p: Decimal) -> Decimal:
            index = max(
                0,
                int((p * len(values)).to_integral_value(rounding="ROUND_CEILING")) - 1,
            )
            return values[index]

        distribution = CensusDistributionV1(
            len(values),
            render(values[0]),
            render(rank(Decimal("0.25"))),
            render(rank(Decimal("0.5"))),
            render(rank(Decimal("0.75"))),
            render(sum(values, Decimal(0)) / Decimal(len(values))),
            render(values[-1]),
            sum(v < 0 for v in values),
            sum(v == 0 for v in values),
            sum(v > 0 for v in values),
        )
    windows = tuple(
        CensusWindowV1(
            item.symbol,
            item.isin,
            item.decision_date,
            item.entry_date,
            item.exit_date,
            item.gross_return_percent,
            item.observation_sha256,
        )
        for item in observed
        if item.strictly_gt_2_percent is True
        and item.entry_date is not None
        and item.exit_date is not None
        and item.gross_return_percent is not None
        and item.observation_sha256 is not None
    )
    return GenericOpportunityCensusV1(
        ordered, len(observed), len(windows), distribution, windows
    )
