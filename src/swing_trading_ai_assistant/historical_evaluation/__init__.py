"""Pure historical-evaluation domain contracts with lazy public exports."""

from importlib import import_module
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from .census import (
        CensusEvidenceStatusV1,
        CensusExecutionStatusV1,
        OpportunityCensusReportV1,
        build_strict_retained_census_v1,
    )
    from .contracts import (
        ANCHOR_ELIGIBILITY_CONTRACT_VERSION_V1,
        ANCHOR_ELIGIBILITY_SCHEMA_VERSION_V1,
        FIVE_SESSION_OUTCOME_POLICY_VERSION_V1,
        AnchorEligibilityEvidenceV1,
        AnchorEligibilityObservationV1,
        AnchorEligibilityReasonV1,
        AnchorEligibilityRequestV1,
        AnchorEligibilityStatusV1,
        EvidenceAvailabilityV1,
        FiveSessionOutcomeEvidenceV1,
        FiveSessionOutcomeObservationV1,
        FiveSessionOutcomeReasonV1,
        FiveSessionOutcomeRequestV1,
        FiveSessionOutcomeStateV1,
        OfficialSessionV1,
        OutcomeSessionFactV1,
        PointInTimeEvidenceV1,
        ResolvedOfficialSessionsV1,
        calculate_five_session_outcome_v1,
        classify_anchor_eligibility_v1,
    )
    from .prerequisite_manifest import (
        PREREQUISITE_MANIFEST_CONTRACT_VERSION_V1,
        READINESS_CONTRACT_IDENTITY_SHA256_V1,
        READINESS_CONTRACT_VERSION_V1,
        SOURCE_POLICY_IDENTITY_SHA256_V1,
        SOURCE_POLICY_VERSION_V1,
        EvidenceReadinessPrerequisiteManifestV1,
        EvidenceReadinessPrerequisiteRequestV1,
        EvidenceReadinessPrerequisiteServiceV1,
        PrerequisiteManifestRequestV1,
        PrerequisiteManifestServiceV1,
    )
    from .prospective_readiness import (
        PROSPECTIVE_READINESS_CONTRACT_VERSION_V1,
        PROSPECTIVE_SOURCE_POLICY_VERSION_V1,
        AnchorSessionFactV1,
        AuthoritativeActionFilingV1,
        AuthorizationStateV1,
        AuthorizationValidationReceiptV1,
        CorporateActionEvidenceCandidateV1,
        CorporateActionObservationV1,
        DeclarationReceiptV1,
        EvidenceAuthorityV1,
        EvidenceClassV1,
        EvidenceExecutionAuthorizationV1,
        EvidenceRequestDescriptorV1,
        ExecutionStateV1,
        PlanningSourceCapabilityV1,
        PrimaryReasonV1,
        ProspectiveReadinessReportV1,
        ProspectiveReadinessRequestV1,
        ReadinessDiagnosticV1,
        ReadinessRowV1,
        ReadinessStateV1,
        ScheduleEvidenceCandidateV1,
        SourceReceiptV1,
        UniverseEvidenceCandidateV1,
        evaluate_prospective_readiness_v1,
    )

_EXPORT_MODULES: Final = (
    ".census",
    ".contracts",
    ".prerequisite_manifest",
    ".prospective_readiness",
)


def __getattr__(name: str) -> object:
    if name not in __all__:
        raise AttributeError(name)
    for module_name in _EXPORT_MODULES:
        module = import_module(module_name, __name__)
        if hasattr(module, name):
            value = getattr(module, name)
            globals()[name] = value
            return value
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted((*globals(), *__all__))


__all__ = [
    "PREREQUISITE_MANIFEST_CONTRACT_VERSION_V1",
    "READINESS_CONTRACT_IDENTITY_SHA256_V1",
    "READINESS_CONTRACT_VERSION_V1",
    "SOURCE_POLICY_IDENTITY_SHA256_V1",
    "SOURCE_POLICY_VERSION_V1",
    "EvidenceReadinessPrerequisiteManifestV1",
    "EvidenceReadinessPrerequisiteRequestV1",
    "EvidenceReadinessPrerequisiteServiceV1",
    "PrerequisiteManifestRequestV1",
    "PrerequisiteManifestServiceV1",
    "ANCHOR_ELIGIBILITY_CONTRACT_VERSION_V1",
    "ANCHOR_ELIGIBILITY_SCHEMA_VERSION_V1",
    "FIVE_SESSION_OUTCOME_POLICY_VERSION_V1",
    "PROSPECTIVE_READINESS_CONTRACT_VERSION_V1",
    "PROSPECTIVE_SOURCE_POLICY_VERSION_V1",
    "AnchorEligibilityEvidenceV1",
    "AnchorEligibilityObservationV1",
    "AnchorEligibilityReasonV1",
    "AnchorEligibilityRequestV1",
    "AnchorEligibilityStatusV1",
    "AnchorSessionFactV1",
    "AuthorizationStateV1",
    "AuthorizationValidationReceiptV1",
    "AuthoritativeActionFilingV1",
    "CensusEvidenceStatusV1",
    "CensusExecutionStatusV1",
    "CorporateActionEvidenceCandidateV1",
    "CorporateActionObservationV1",
    "DeclarationReceiptV1",
    "EvidenceAuthorityV1",
    "EvidenceAvailabilityV1",
    "EvidenceClassV1",
    "EvidenceExecutionAuthorizationV1",
    "EvidenceRequestDescriptorV1",
    "ExecutionStateV1",
    "FiveSessionOutcomeEvidenceV1",
    "FiveSessionOutcomeObservationV1",
    "FiveSessionOutcomeReasonV1",
    "FiveSessionOutcomeRequestV1",
    "FiveSessionOutcomeStateV1",
    "OfficialSessionV1",
    "OpportunityCensusReportV1",
    "OutcomeSessionFactV1",
    "PlanningSourceCapabilityV1",
    "PointInTimeEvidenceV1",
    "PrimaryReasonV1",
    "ProspectiveReadinessReportV1",
    "ProspectiveReadinessRequestV1",
    "ReadinessDiagnosticV1",
    "ReadinessRowV1",
    "ReadinessStateV1",
    "ResolvedOfficialSessionsV1",
    "ScheduleEvidenceCandidateV1",
    "SourceReceiptV1",
    "UniverseEvidenceCandidateV1",
    "build_strict_retained_census_v1",
    "calculate_five_session_outcome_v1",
    "classify_anchor_eligibility_v1",
    "evaluate_prospective_readiness_v1",
]
