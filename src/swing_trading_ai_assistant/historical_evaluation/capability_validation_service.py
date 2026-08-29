"""Read-only Sprint-15 adapter for capability-aware historical validation V1."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from swing_trading_ai_assistant.market_data.historical_revision_store import (
    HistoricalOhlcvImportOutcomeV1,
    HistoricalOhlcvRevisionStoreV1,
)

from .capability_validation import (
    HistoricalValidationReasonV1,
    HistoricalValidationReportV1,
    HistoricalValidationRequestV1,
    build_blocked_historical_validation_report_v1,
    evaluate_capability_aware_historical_validation_v1,
    historical_evidence_from_sprint15_revision_v1,
    validate_current_historical_validation_request_v1,
)


@dataclass(frozen=True, slots=True)
class HistoricalValidationServiceV1:
    """Read one exact immutable revision and invoke the pure validation reducer."""

    storage_root: Path
    admitted_root_identity: tuple[int, int] | None = None

    def evaluate(
        self, request: HistoricalValidationRequestV1
    ) -> HistoricalValidationReportV1:
        validate_current_historical_validation_request_v1(request)
        result = HistoricalOhlcvRevisionStoreV1(
            self.storage_root, self.admitted_root_identity
        ).read_exact(request.evidence_revision_sha256)
        if (
            result.outcome is not HistoricalOhlcvImportOutcomeV1.SUCCESS
            or result.revision is None
        ):
            return build_blocked_historical_validation_report_v1(request)
        if result.revision_sha256 != request.evidence_revision_sha256:
            return build_blocked_historical_validation_report_v1(
                request,
                HistoricalValidationReasonV1.EVIDENCE_REVISION_IDENTITY_MISMATCH,
            )
        try:
            evidence = historical_evidence_from_sprint15_revision_v1(result.revision)
        except ValueError:
            return build_blocked_historical_validation_report_v1(
                request,
                HistoricalValidationReasonV1.EVIDENCE_REVISION_IDENTITY_MISMATCH,
            )
        if (
            request.cohort_identity_sha256 != evidence.cohort_identity_sha256
            or request.cohort != evidence.cohort
        ):
            return build_blocked_historical_validation_report_v1(
                request,
                HistoricalValidationReasonV1.COHORT_IDENTITY_MISMATCH,
            )
        sessions = tuple(point.session for point in request.decision_points)
        if sessions != evidence.sessions:
            return build_blocked_historical_validation_report_v1(
                request,
                HistoricalValidationReasonV1.DECISION_GRID_MISMATCH,
            )
        return evaluate_capability_aware_historical_validation_v1(request, evidence)


__all__ = ["HistoricalValidationServiceV1"]
