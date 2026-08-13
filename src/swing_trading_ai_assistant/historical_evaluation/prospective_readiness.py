"""Pure, provider-free prospective point-in-time evidence readiness v1."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Final

from swing_trading_ai_assistant.market_data.corporate_actions import (
    CorporateActionSnapshotV1,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    canonical_schedule_bytes,
    parse_canonical_schedule_bytes,
    schedule_covers_full_calendar_range,
)
from swing_trading_ai_assistant.market_data.universe_snapshot import (
    Nifty50UniverseSnapshotV1,
)

PROSPECTIVE_READINESS_CONTRACT_VERSION_V1: Final = "forward-pit-evidence-readiness@v1"
PROSPECTIVE_SOURCE_POLICY_VERSION_V1: Final = (
    "prospective-pit-evidence-source-policy@v1"
)
MAX_REQUEST_BYTES_V1: Final = 4 * 1024 * 1024
MAX_REPORT_BYTES_V1: Final = 4 * 1024 * 1024
MAX_CORPORATE_ACTION_OBSERVATIONS_PER_ISIN_V1: Final = 366
MAX_CORPORATE_ACTION_OBSERVATIONS_V1: Final = 18_300
MAX_SOURCE_RECEIPTS_V1: Final = 1_024
MAX_REQUEST_DESCRIPTORS_V1: Final = 512
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ISIN = re.compile(r"INE[A-Z0-9]{8}[0-9]\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}\Z")
_COHORT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_NSE_INDICES_SOURCE = "niftyindices-official-constituent-csv"
_NSE_SCHEDULE_SOURCE = "nse-authoritative-calendar"
_PINNED_UNIVERSE_SHA256_V1: Final = (
    "936a32c8dee5d852221a159434064be79380fe75a40029c1e0b506c0086e0b30"
)
_PINNED_SCHEDULE_SHA256_V1: Final = frozenset(
    {
        "7c8cdef86c3874f9542a9544821805bfc23787975e29d0f297164776b5816db9",
        "09f7e6b8477d4588668957f3d063acd3982d4cb7c7f1ebcde49f3dbc496e5930",
    }
)


class EvidenceClassV1(StrEnum):
    MEMBERSHIP = "MEMBERSHIP"
    SECTOR = "SECTOR"
    SCHEDULE = "SCHEDULE"
    CORPORATE_ACTION = "CORPORATE_ACTION"
    ANCHOR_SESSION = "ANCHOR_SESSION"


class EvidenceAuthorityV1(StrEnum):
    NSE_INDICES_LIMITED = "NSE_INDICES_LIMITED"
    NSE_CAPITAL_MARKET = "NSE_CAPITAL_MARKET"
    UPSTOX_FUNDAMENTALS = "UPSTOX_FUNDAMENTALS"
    UPSTOX_MARKET_DATA = "UPSTOX_MARKET_DATA"


class PrimaryReasonV1(StrEnum):
    SOURCE_NOT_AUTHORITATIVE = "SOURCE_NOT_AUTHORITATIVE"
    PUBLICATION_UNPROVEN = "PUBLICATION_UNPROVEN"
    CLOCK_UNTRUSTED = "CLOCK_UNTRUSTED"
    LICENCE_UNRESOLVED = "LICENCE_UNRESOLVED"
    MEMBERSHIP_MISSING = "MEMBERSHIP_MISSING"
    MEMBERSHIP_LATE = "MEMBERSHIP_LATE"
    MEMBERSHIP_AMBIGUOUS = "MEMBERSHIP_AMBIGUOUS"
    MEMBERSHIP_CORRUPT = "MEMBERSHIP_CORRUPT"
    SECTOR_MISSING = "SECTOR_MISSING"
    SECTOR_LATE = "SECTOR_LATE"
    SECTOR_AMBIGUOUS = "SECTOR_AMBIGUOUS"
    SECTOR_CORRUPT = "SECTOR_CORRUPT"
    SCHEDULE_MISSING = "SCHEDULE_MISSING"
    SCHEDULE_LATE = "SCHEDULE_LATE"
    SCHEDULE_COVERAGE_INCOMPLETE = "SCHEDULE_COVERAGE_INCOMPLETE"
    SCHEDULE_AMBIGUOUS = "SCHEDULE_AMBIGUOUS"
    SCHEDULE_CORRUPT = "SCHEDULE_CORRUPT"
    CORPORATE_ACTION_MISSING = "CORPORATE_ACTION_MISSING"
    CORPORATE_ACTION_LATE = "CORPORATE_ACTION_LATE"
    CORPORATE_ACTION_STATUS_UNPROVEN = "CORPORATE_ACTION_STATUS_UNPROVEN"
    CORPORATE_ACTION_COMPLETENESS_UNPROVEN = "CORPORATE_ACTION_COMPLETENESS_UNPROVEN"
    CORPORATE_ACTION_REVISION_UNPROVEN = "CORPORATE_ACTION_REVISION_UNPROVEN"
    CORPORATE_ACTION_AMBIGUOUS = "CORPORATE_ACTION_AMBIGUOUS"
    CORPORATE_ACTION_CORRUPT = "CORPORATE_ACTION_CORRUPT"
    ANCHOR_SESSION_INCOMPLETE = "ANCHOR_SESSION_INCOMPLETE"
    ANCHOR_SESSION_LATE = "ANCHOR_SESSION_LATE"
    ANCHOR_SESSION_AMBIGUOUS = "ANCHOR_SESSION_AMBIGUOUS"
    ANCHOR_SESSION_CORRUPT = "ANCHOR_SESSION_CORRUPT"
    EVIDENCE_IDENTITY_MISMATCH = "EVIDENCE_IDENTITY_MISMATCH"


class ReadinessStateV1(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class ExecutionStateV1(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"


class AuthorizationStateV1(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    AUTHORIZED_AS_OF_VALIDATION = "AUTHORIZED_AS_OF_VALIDATION"
    AUTHORIZATION_INVALID = "AUTHORIZATION_INVALID"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _aware(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _valid_digest(value: object) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _valid_token(value: object) -> bool:
    return type(value) is str and _TOKEN.fullmatch(value) is not None


def _valid_isin(value: object) -> bool:
    if type(value) is not str or _ISIN.fullmatch(value) is None:
        return False
    expanded = "".join(
        str(ord(char) - 55) if char.isalpha() else char for char in value
    )
    total = 0
    parity = len(expanded) % 2
    for index, char in enumerate(expanded):
        number = int(char)
        if index % 2 == parity:
            number *= 2
        total += number // 10 + number % 10
    return total % 10 == 0


@dataclass(frozen=True, slots=True)
class DeclarationReceiptV1:
    declared_at: datetime
    retained_at: datetime
    trusted_clock_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            not _aware(self.declared_at)
            or not _aware(self.retained_at)
            or self.retained_at < self.declared_at
            or not _valid_digest(self.trusted_clock_identity_sha256)
        ):
            raise ValueError("invalid declaration receipt")
        object.__setattr__(self, "declared_at", self.declared_at.astimezone(UTC))
        object.__setattr__(self, "retained_at", self.retained_at.astimezone(UTC))

    @property
    def receipt_identity_sha256(self) -> str:
        return _sha(
            _canonical(
                {
                    "declared_at": _timestamp(self.declared_at),
                    "retained_at": _timestamp(self.retained_at),
                    "trusted_clock_identity_sha256": self.trusted_clock_identity_sha256,
                }
            )
        )

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


@dataclass(frozen=True, slots=True)
class SourceReceiptV1:
    evidence_class: EvidenceClassV1
    authority: EvidenceAuthorityV1
    release_identity: str
    source_bytes_sha256: str
    publication_proof_sha256: str
    public_available_at: datetime
    request_started_at: datetime
    response_completed_at: datetime
    retained_at: datetime
    trusted_clock_identity_sha256: str
    effective_from: date
    effective_to: date
    revision_identity: str
    supersedes_revision_identity: str | None
    licence_review_identity_sha256: str

    def __post_init__(self) -> None:
        times = (
            self.public_available_at,
            self.request_started_at,
            self.response_completed_at,
            self.retained_at,
        )
        if (
            type(self.evidence_class) is not EvidenceClassV1
            or type(self.authority) is not EvidenceAuthorityV1
            or not _valid_token(self.release_identity)
            or not _valid_digest(self.source_bytes_sha256)
            or not _valid_digest(self.publication_proof_sha256)
            or any(not _aware(value) for value in times)
            or self.response_completed_at < self.request_started_at
            or self.retained_at < self.response_completed_at
            or not _valid_digest(self.trusted_clock_identity_sha256)
            or type(self.effective_from) is not date
            or type(self.effective_to) is not date
            or self.effective_from > self.effective_to
            or not _valid_token(self.revision_identity)
            or (
                self.supersedes_revision_identity is not None
                and not _valid_token(self.supersedes_revision_identity)
            )
            or self.supersedes_revision_identity == self.revision_identity
            or not _valid_digest(self.licence_review_identity_sha256)
        ):
            raise ValueError("invalid source receipt")
        for field in (
            "public_available_at",
            "request_started_at",
            "response_completed_at",
            "retained_at",
        ):
            object.__setattr__(self, field, getattr(self, field).astimezone(UTC))

    @property
    def knowledge_time(self) -> datetime:
        return max(
            self.public_available_at,
            self.request_started_at,
            self.response_completed_at,
            self.retained_at,
        )

    @property
    def receipt_identity_sha256(self) -> str:
        return _sha(_canonical(_receipt_value(self)))

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


def _receipt_value(receipt: SourceReceiptV1) -> dict[str, object]:
    return {
        "authority": receipt.authority.value,
        "effective_from": receipt.effective_from.isoformat(),
        "effective_to": receipt.effective_to.isoformat(),
        "evidence_class": receipt.evidence_class.value,
        "licence_review_identity_sha256": receipt.licence_review_identity_sha256,
        "public_available_at": _timestamp(receipt.public_available_at),
        "publication_proof_sha256": receipt.publication_proof_sha256,
        "release_identity": receipt.release_identity,
        "request_started_at": _timestamp(receipt.request_started_at),
        "response_completed_at": _timestamp(receipt.response_completed_at),
        "retained_at": _timestamp(receipt.retained_at),
        "revision_identity": receipt.revision_identity,
        "source_bytes_sha256": receipt.source_bytes_sha256,
        "supersedes_revision_identity": receipt.supersedes_revision_identity,
        "trusted_clock_identity_sha256": receipt.trusted_clock_identity_sha256,
    }


@dataclass(frozen=True, slots=True)
class UniverseEvidenceCandidateV1:
    canonical_bytes: bytes
    membership_receipt: SourceReceiptV1
    sector_receipt: SourceReceiptV1

    def __post_init__(self) -> None:
        if (
            type(self.canonical_bytes) is not bytes
            or not 1 <= len(self.canonical_bytes) <= 64 * 1024
            or type(self.membership_receipt) is not SourceReceiptV1
            or type(self.sector_receipt) is not SourceReceiptV1
            or self.membership_receipt.evidence_class is not EvidenceClassV1.MEMBERSHIP
            or self.sector_receipt.evidence_class is not EvidenceClassV1.SECTOR
            or self.membership_receipt.source_bytes_sha256 != _sha(self.canonical_bytes)
            or self.sector_receipt.source_bytes_sha256 != _sha(self.canonical_bytes)
        ):
            raise ValueError("invalid universe evidence candidate")

    @property
    def candidate_identity_sha256(self) -> str:
        return _sha(
            _canonical(
                {
                    "canonical_bytes_sha256": _sha(self.canonical_bytes),
                    "membership_receipt": self.membership_receipt.receipt_identity_sha256,
                    "sector_receipt": self.sector_receipt.receipt_identity_sha256,
                }
            )
        )

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


@dataclass(frozen=True, slots=True)
class ScheduleEvidenceCandidateV1:
    canonical_bytes: bytes
    receipt: SourceReceiptV1

    def __post_init__(self) -> None:
        if (
            type(self.canonical_bytes) is not bytes
            or not 1 <= len(self.canonical_bytes) <= 1024 * 1024
            or type(self.receipt) is not SourceReceiptV1
            or self.receipt.evidence_class is not EvidenceClassV1.SCHEDULE
            or self.receipt.source_bytes_sha256 != _sha(self.canonical_bytes)
        ):
            raise ValueError("invalid schedule evidence candidate")

    @property
    def candidate_identity_sha256(self) -> str:
        return _sha(
            _canonical(
                {
                    "canonical_bytes_sha256": _sha(self.canonical_bytes),
                    "receipt": self.receipt.receipt_identity_sha256,
                }
            )
        )

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


@dataclass(frozen=True, slots=True)
class CorporateActionObservationV1:
    canonical_bytes: bytes
    receipt: SourceReceiptV1

    def __post_init__(self) -> None:
        if (
            type(self.canonical_bytes) is not bytes
            or not 1 <= len(self.canonical_bytes) <= 1024 * 1024
            or type(self.receipt) is not SourceReceiptV1
            or self.receipt.evidence_class is not EvidenceClassV1.CORPORATE_ACTION
            or self.receipt.source_bytes_sha256 != _sha(self.canonical_bytes)
        ):
            raise ValueError("invalid corporate action observation")

    @property
    def observation_identity_sha256(self) -> str:
        return _sha(
            _canonical(
                {
                    "canonical_bytes_sha256": _sha(self.canonical_bytes),
                    "receipt": self.receipt.receipt_identity_sha256,
                }
            )
        )

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


@dataclass(frozen=True, slots=True)
class AuthoritativeActionFilingV1:
    isin: str
    event_digest_sha256: str
    status: str
    terms_identity_sha256: str
    filing_bytes_sha256: str
    receipt: SourceReceiptV1

    def __post_init__(self) -> None:
        if (
            not _valid_isin(self.isin)
            or not _valid_digest(self.event_digest_sha256)
            or self.status not in {"ACTIVE", "CANCELLED", "SUPERSEDED"}
            or not _valid_digest(self.terms_identity_sha256)
            or not _valid_digest(self.filing_bytes_sha256)
            or type(self.receipt) is not SourceReceiptV1
            or self.receipt.source_bytes_sha256 != self.filing_bytes_sha256
            or self.receipt.authority is not EvidenceAuthorityV1.NSE_CAPITAL_MARKET
            or self.receipt.evidence_class is not EvidenceClassV1.CORPORATE_ACTION
        ):
            raise ValueError("invalid authoritative action filing")

    @property
    def filing_identity_sha256(self) -> str:
        return _sha(
            _canonical(
                {
                    "event_digest_sha256": self.event_digest_sha256,
                    "filing_bytes_sha256": self.filing_bytes_sha256,
                    "isin": self.isin,
                    "receipt": self.receipt.receipt_identity_sha256,
                    "status": self.status,
                    "terms_identity_sha256": self.terms_identity_sha256,
                }
            )
        )

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


@dataclass(frozen=True, slots=True)
class CorporateActionEvidenceCandidateV1:
    isin: str
    observations: tuple[CorporateActionObservationV1, ...]
    authoritative_filings: tuple[AuthoritativeActionFilingV1, ...] = ()

    def __post_init__(self) -> None:
        if (
            not _valid_isin(self.isin)
            or type(self.observations) is not tuple
            or len(self.observations) > MAX_CORPORATE_ACTION_OBSERVATIONS_PER_ISIN_V1
            or any(
                type(value) is not CorporateActionObservationV1
                for value in self.observations
            )
            or len({value.observation_identity_sha256 for value in self.observations})
            != len(self.observations)
            or type(self.authoritative_filings) is not tuple
            or any(
                type(value) is not AuthoritativeActionFilingV1
                for value in self.authoritative_filings
            )
            or any(value.isin != self.isin for value in self.authoritative_filings)
            or len(
                {value.filing_identity_sha256 for value in self.authoritative_filings}
            )
            != len(self.authoritative_filings)
        ):
            raise ValueError("invalid corporate action evidence candidate")

    @property
    def candidate_identity_sha256(self) -> str:
        return _sha(
            _canonical(
                {
                    "authoritative_filings": sorted(
                        value.filing_identity_sha256
                        for value in self.authoritative_filings
                    ),
                    "isin": self.isin,
                    "observations": sorted(
                        value.observation_identity_sha256 for value in self.observations
                    ),
                }
            )
        )

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


@dataclass(frozen=True, slots=True)
class AnchorSessionFactV1:
    isin: str
    decision_session: date
    schedule_sha256: str
    complete_grid_validation_sha256: str
    source_candle_checksum_sha256: str
    receipt: SourceReceiptV1

    def __post_init__(self) -> None:
        if (
            not _valid_isin(self.isin)
            or type(self.decision_session) is not date
            or not _valid_digest(self.schedule_sha256)
            or not _valid_digest(self.complete_grid_validation_sha256)
            or not _valid_digest(self.source_candle_checksum_sha256)
            or type(self.receipt) is not SourceReceiptV1
            or self.receipt.evidence_class is not EvidenceClassV1.ANCHOR_SESSION
            or self.receipt.source_bytes_sha256 != self.source_candle_checksum_sha256
        ):
            raise ValueError("invalid anchor session fact")

    @property
    def fact_identity_sha256(self) -> str:
        return _sha(
            _canonical(
                {
                    "complete_grid_validation_sha256": self.complete_grid_validation_sha256,
                    "decision_session": self.decision_session.isoformat(),
                    "isin": self.isin,
                    "receipt": self.receipt.receipt_identity_sha256,
                    "schedule_sha256": self.schedule_sha256,
                    "source_candle_checksum_sha256": self.source_candle_checksum_sha256,
                }
            )
        )

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


@dataclass(frozen=True, slots=True)
class PlanningSourceCapabilityV1:
    evidence_class: EvidenceClassV1
    authority: EvidenceAuthorityV1
    source_locator: str
    effective_from: date
    effective_to: date
    licence_review_identity_sha256: str
    maximum_response_bytes: int
    admission_contract_version: str

    def __post_init__(self) -> None:
        admitted = {
            EvidenceClassV1.MEMBERSHIP: EvidenceAuthorityV1.NSE_INDICES_LIMITED,
            EvidenceClassV1.SECTOR: EvidenceAuthorityV1.NSE_INDICES_LIMITED,
            EvidenceClassV1.SCHEDULE: EvidenceAuthorityV1.NSE_CAPITAL_MARKET,
            EvidenceClassV1.CORPORATE_ACTION: EvidenceAuthorityV1.UPSTOX_FUNDAMENTALS,
            EvidenceClassV1.ANCHOR_SESSION: EvidenceAuthorityV1.UPSTOX_MARKET_DATA,
        }
        if (
            type(self.evidence_class) is not EvidenceClassV1
            or self.authority is not admitted[self.evidence_class]
            or type(self.source_locator) is not str
            or not self.source_locator
            or len(self.source_locator.encode("utf-8")) > 2048
            or "?" in self.source_locator
            or type(self.effective_from) is not date
            or type(self.effective_to) is not date
            or self.effective_from > self.effective_to
            or not _valid_digest(self.licence_review_identity_sha256)
            or type(self.maximum_response_bytes) is not int
            or not 0 < self.maximum_response_bytes <= 4 * 1024 * 1024
            or not _valid_token(self.admission_contract_version)
        ):
            raise ValueError("invalid planning source capability")

    @property
    def capability_identity_sha256(self) -> str:
        return _sha(_canonical(_capability_value(self)))

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


def _capability_value(value: PlanningSourceCapabilityV1) -> dict[str, object]:
    return {
        "admission_contract_version": value.admission_contract_version,
        "authority": value.authority.value,
        "effective_from": value.effective_from.isoformat(),
        "effective_to": value.effective_to.isoformat(),
        "evidence_class": value.evidence_class.value,
        "licence_review_identity_sha256": value.licence_review_identity_sha256,
        "maximum_response_bytes": value.maximum_response_bytes,
        "source_locator": value.source_locator,
    }


@dataclass(frozen=True, slots=True)
class EvidenceExecutionAuthorizationV1:
    contract_version: str
    source_policy_version: str
    request_manifest_sha256: str
    sorted_isins_sha256: str
    allowed_evidence_classes: tuple[EvidenceClassV1, ...]
    allowed_authorities: tuple[EvidenceAuthorityV1, ...]
    effective_from: date
    effective_to: date
    maximum_attempts: int
    maximum_response_bytes: int
    maximum_concurrency: int
    maximum_duration_seconds: int
    approval_decision_sha256: str
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if (
            self.contract_version != PROSPECTIVE_READINESS_CONTRACT_VERSION_V1
            or self.source_policy_version != PROSPECTIVE_SOURCE_POLICY_VERSION_V1
            or not _valid_digest(self.request_manifest_sha256)
            or not _valid_digest(self.sorted_isins_sha256)
            or type(self.allowed_evidence_classes) is not tuple
            or self.allowed_evidence_classes
            != tuple(
                sorted(
                    set(self.allowed_evidence_classes), key=lambda value: value.value
                )
            )
            or any(
                type(value) is not EvidenceClassV1
                for value in self.allowed_evidence_classes
            )
            or type(self.allowed_authorities) is not tuple
            or self.allowed_authorities
            != tuple(
                sorted(set(self.allowed_authorities), key=lambda value: value.value)
            )
            or any(
                type(value) is not EvidenceAuthorityV1
                for value in self.allowed_authorities
            )
            or type(self.effective_from) is not date
            or type(self.effective_to) is not date
            or self.effective_from > self.effective_to
            or any(
                type(value) is not int or value <= 0
                for value in (
                    self.maximum_attempts,
                    self.maximum_response_bytes,
                    self.maximum_concurrency,
                    self.maximum_duration_seconds,
                )
            )
            or not _valid_digest(self.approval_decision_sha256)
            or not _aware(self.issued_at)
            or not _aware(self.expires_at)
            or self.expires_at <= self.issued_at
        ):
            raise ValueError("invalid evidence execution authorization")
        object.__setattr__(self, "issued_at", self.issued_at.astimezone(UTC))
        object.__setattr__(self, "expires_at", self.expires_at.astimezone(UTC))

    @property
    def authorization_identity_sha256(self) -> str:
        return _sha(_canonical(_authorization_value(self)))

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


def _authorization_value(value: EvidenceExecutionAuthorizationV1) -> dict[str, object]:
    return {
        "allowed_authorities": [item.value for item in value.allowed_authorities],
        "allowed_evidence_classes": [
            item.value for item in value.allowed_evidence_classes
        ],
        "approval_decision_sha256": value.approval_decision_sha256,
        "contract_version": value.contract_version,
        "effective_from": value.effective_from.isoformat(),
        "effective_to": value.effective_to.isoformat(),
        "expires_at": _timestamp(value.expires_at),
        "issued_at": _timestamp(value.issued_at),
        "maximum_attempts": value.maximum_attempts,
        "maximum_concurrency": value.maximum_concurrency,
        "maximum_duration_seconds": value.maximum_duration_seconds,
        "maximum_response_bytes": value.maximum_response_bytes,
        "request_manifest_sha256": value.request_manifest_sha256,
        "sorted_isins_sha256": value.sorted_isins_sha256,
        "source_policy_version": value.source_policy_version,
    }


@dataclass(frozen=True, slots=True)
class AuthorizationValidationReceiptV1:
    authorization_identity_sha256: str
    validated_at: datetime
    trusted_clock_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            not _valid_digest(self.authorization_identity_sha256)
            or not _aware(self.validated_at)
            or not _valid_digest(self.trusted_clock_identity_sha256)
        ):
            raise ValueError("invalid authorization validation receipt")
        object.__setattr__(self, "validated_at", self.validated_at.astimezone(UTC))

    @property
    def validation_identity_sha256(self) -> str:
        return _sha(
            _canonical(
                {
                    "authorization_identity_sha256": self.authorization_identity_sha256,
                    "trusted_clock_identity_sha256": self.trusted_clock_identity_sha256,
                    "validated_at": _timestamp(self.validated_at),
                }
            )
        )

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


@dataclass(frozen=True, slots=True)
class ProspectiveReadinessRequestV1:
    contract_version: str
    source_policy_version: str
    cohort_id: str
    declaration_receipt: DeclarationReceiptV1
    decision_session: date
    evaluated_at: datetime
    required_isins: tuple[str, ...]
    trusted_universe_snapshot_sha256: str
    validation_policy_sha256: str
    configuration_sha256: str
    code_identity: str
    sprint4_seal_sha256: str
    universe_candidates: tuple[UniverseEvidenceCandidateV1, ...] = ()
    schedule_candidates: tuple[ScheduleEvidenceCandidateV1, ...] = ()
    corporate_action_candidates: tuple[CorporateActionEvidenceCandidateV1, ...] = ()
    anchor_facts: tuple[AnchorSessionFactV1, ...] = ()
    planning_source_capabilities: tuple[PlanningSourceCapabilityV1, ...] = ()
    execution_authorization: EvidenceExecutionAuthorizationV1 | None = None
    authorization_validation_receipt: AuthorizationValidationReceiptV1 | None = None
    provider_attempts: int = 0
    network_attempts: int = 0
    storage_write_attempts: int = 0

    def __post_init__(self) -> None:
        try:
            if (
                self.contract_version != PROSPECTIVE_READINESS_CONTRACT_VERSION_V1
                or self.source_policy_version != PROSPECTIVE_SOURCE_POLICY_VERSION_V1
                or type(self.cohort_id) is not str
                or _COHORT.fullmatch(self.cohort_id) is None
                or type(self.declaration_receipt) is not DeclarationReceiptV1
                or type(self.decision_session) is not date
                or not _aware(self.evaluated_at)
                or self.declaration_receipt.declared_at >= self.evaluated_at
                or type(self.required_isins) is not tuple
                or len(self.required_isins) != 50
                or self.required_isins != tuple(sorted(self.required_isins))
                or len(set(self.required_isins)) != 50
                or any(not _valid_isin(value) for value in self.required_isins)
                or self.trusted_universe_snapshot_sha256 != _PINNED_UNIVERSE_SHA256_V1
                or not _valid_digest(self.validation_policy_sha256)
                or not _valid_digest(self.configuration_sha256)
                or not _valid_token(self.code_identity)
                or not _valid_digest(self.sprint4_seal_sha256)
            ):
                raise ValueError
            groups: tuple[tuple[object, ...], ...] = (
                self.universe_candidates,
                self.schedule_candidates,
                self.corporate_action_candidates,
                self.anchor_facts,
                self.planning_source_capabilities,
            )
            expected = (
                UniverseEvidenceCandidateV1,
                ScheduleEvidenceCandidateV1,
                CorporateActionEvidenceCandidateV1,
                AnchorSessionFactV1,
                PlanningSourceCapabilityV1,
            )
            if any(type(group) is not tuple for group in groups) or any(
                any(type(item) is not kind for item in group)
                for group, kind in zip(groups, expected, strict=True)
            ):
                raise ValueError
            evidence_receipts = (
                tuple(
                    receipt
                    for item in self.universe_candidates
                    for receipt in (item.membership_receipt, item.sector_receipt)
                )
                + tuple(item.receipt for item in self.schedule_candidates)
                + tuple(
                    observation.receipt
                    for item in self.corporate_action_candidates
                    for observation in item.observations
                )
                + tuple(
                    filing.receipt
                    for item in self.corporate_action_candidates
                    for filing in item.authoritative_filings
                )
                + tuple(item.receipt for item in self.anchor_facts)
            )
            if (
                self.declaration_receipt.retained_at > self.evaluated_at
                or any(
                    receipt.request_started_at < self.declaration_receipt.retained_at
                    for receipt in evidence_receipts
                )
                or len(
                    {
                        item.candidate_identity_sha256
                        for item in self.universe_candidates
                    }
                )
                != len(self.universe_candidates)
                or len(
                    {
                        item.candidate_identity_sha256
                        for item in self.schedule_candidates
                    }
                )
                != len(self.schedule_candidates)
                or len({item.isin for item in self.corporate_action_candidates})
                != len(self.corporate_action_candidates)
                or len({item.isin for item in self.anchor_facts})
                != len(self.anchor_facts)
                or any(
                    item.isin not in self.required_isins
                    for item in self.corporate_action_candidates
                )
                or any(
                    item.isin not in self.required_isins for item in self.anchor_facts
                )
                or len(
                    {item.evidence_class for item in self.planning_source_capabilities}
                )
                != len(self.planning_source_capabilities)
                or sum(
                    len(item.observations) for item in self.corporate_action_candidates
                )
                > MAX_CORPORATE_ACTION_OBSERVATIONS_V1
                or (
                    2 * len(self.universe_candidates)
                    + len(self.schedule_candidates)
                    + sum(
                        len(item.observations) + len(item.authoritative_filings)
                        for item in self.corporate_action_candidates
                    )
                    + len(self.anchor_facts)
                    > MAX_SOURCE_RECEIPTS_V1
                )
                or (
                    sum(len(item.canonical_bytes) for item in self.universe_candidates)
                    + sum(
                        len(item.canonical_bytes) for item in self.schedule_candidates
                    )
                    + sum(
                        len(observation.canonical_bytes)
                        for item in self.corporate_action_candidates
                        for observation in item.observations
                    )
                    > MAX_REQUEST_BYTES_V1
                )
                or (self.execution_authorization is None)
                != (self.authorization_validation_receipt is None)
                or (
                    self.execution_authorization is not None
                    and type(self.execution_authorization)
                    is not EvidenceExecutionAuthorizationV1
                )
                or (
                    self.authorization_validation_receipt is not None
                    and type(self.authorization_validation_receipt)
                    is not AuthorizationValidationReceiptV1
                )
                or any(
                    type(value) is not int or value != 0
                    for value in (
                        self.provider_attempts,
                        self.network_attempts,
                        self.storage_write_attempts,
                    )
                )
                or len(_canonical(_request_value(self, include_authorization=True)))
                > MAX_REQUEST_BYTES_V1
            ):
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            raise ValueError("invalid prospective readiness request") from None
        object.__setattr__(self, "evaluated_at", self.evaluated_at.astimezone(UTC))

    @property
    def sorted_isins_sha256(self) -> str:
        return _sha(_canonical(list(self.required_isins)))

    @property
    def request_manifest_sha256(self) -> str:
        return _sha(_canonical(_request_value(self, include_authorization=False)))

    @property
    def request_identity_sha256(self) -> str:
        return _sha(_canonical(_request_value(self, include_authorization=True)))

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


def _request_value(
    value: ProspectiveReadinessRequestV1, *, include_authorization: bool
) -> dict[str, object]:
    result: dict[str, object] = {
        "anchor_facts": sorted(
            item.fact_identity_sha256 for item in value.anchor_facts
        ),
        "code_identity": value.code_identity,
        "cohort_id": value.cohort_id,
        "configuration_sha256": value.configuration_sha256,
        "contract_version": value.contract_version,
        "corporate_action_candidates": sorted(
            item.candidate_identity_sha256 for item in value.corporate_action_candidates
        ),
        "decision_session": value.decision_session.isoformat(),
        "declaration_receipt": value.declaration_receipt.receipt_identity_sha256,
        "evaluated_at": _timestamp(value.evaluated_at),
        "network_attempts": value.network_attempts,
        "planning_source_capabilities": sorted(
            item.capability_identity_sha256
            for item in value.planning_source_capabilities
        ),
        "provider_attempts": value.provider_attempts,
        "required_isins": list(value.required_isins),
        "schedule_candidates": sorted(
            item.candidate_identity_sha256 for item in value.schedule_candidates
        ),
        "source_policy_version": value.source_policy_version,
        "sprint4_seal_sha256": value.sprint4_seal_sha256,
        "storage_write_attempts": value.storage_write_attempts,
        "trusted_universe_snapshot_sha256": value.trusted_universe_snapshot_sha256,
        "universe_candidates": sorted(
            item.candidate_identity_sha256 for item in value.universe_candidates
        ),
        "validation_policy_sha256": value.validation_policy_sha256,
    }
    if include_authorization:
        result["execution_authorization"] = (
            None
            if value.execution_authorization is None
            else value.execution_authorization.authorization_identity_sha256
        )
        result["authorization_validation_receipt"] = (
            None
            if value.authorization_validation_receipt is None
            else value.authorization_validation_receipt.validation_identity_sha256
        )
    return result


@dataclass(frozen=True, slots=True)
class ReadinessDiagnosticV1:
    evidence_class: EvidenceClassV1
    reason: PrimaryReasonV1
    evidence_identity_sha256: str | None

    def __post_init__(self) -> None:
        if (
            type(self.evidence_class) is not EvidenceClassV1
            or type(self.reason) is not PrimaryReasonV1
            or (
                self.evidence_identity_sha256 is not None
                and not _valid_digest(self.evidence_identity_sha256)
            )
        ):
            raise ValueError("invalid readiness diagnostic")

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


@dataclass(frozen=True, slots=True)
class ReadinessRowV1:
    isin: str
    readiness_state: ReadinessStateV1
    primary_reason: PrimaryReasonV1 | None
    diagnostics: tuple[ReadinessDiagnosticV1, ...]

    def __post_init__(self) -> None:
        if (
            not _valid_isin(self.isin)
            or type(self.readiness_state) is not ReadinessStateV1
            or type(self.diagnostics) is not tuple
            or any(
                type(value) is not ReadinessDiagnosticV1 for value in self.diagnostics
            )
            or len(set(self.diagnostics)) != len(self.diagnostics)
            or (
                self.readiness_state is ReadinessStateV1.READY
                and (self.primary_reason is not None or self.diagnostics)
            )
            or (
                self.readiness_state is ReadinessStateV1.BLOCKED
                and (
                    type(self.primary_reason) is not PrimaryReasonV1
                    or not self.diagnostics
                    or self.primary_reason is not self.diagnostics[0].reason
                )
            )
        ):
            raise ValueError("invalid readiness row")

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


@dataclass(frozen=True, slots=True)
class EvidenceRequestDescriptorV1:
    evidence_class: EvidenceClassV1
    isin: str | None
    authority: EvidenceAuthorityV1
    capability_identity_sha256: str
    source_locator: str
    effective_from: date
    effective_to: date
    purpose: str
    source_policy_version: str
    licence_review_identity_sha256: str
    maximum_response_bytes: int
    admission_contract_version: str

    def __post_init__(self) -> None:
        if (
            type(self.evidence_class) is not EvidenceClassV1
            or type(self.authority) is not EvidenceAuthorityV1
            or not _valid_digest(self.capability_identity_sha256)
            or type(self.source_locator) is not str
            or not self.source_locator
            or len(self.source_locator.encode("utf-8")) > 2048
            or "?" in self.source_locator
            or (self.isin is not None and not _valid_isin(self.isin))
            or type(self.effective_from) is not date
            or type(self.effective_to) is not date
            or not _valid_token(self.purpose)
            or self.source_policy_version != PROSPECTIVE_SOURCE_POLICY_VERSION_V1
            or not _valid_digest(self.licence_review_identity_sha256)
            or type(self.maximum_response_bytes) is not int
            or self.maximum_response_bytes <= 0
            or not _valid_token(self.admission_contract_version)
        ):
            raise ValueError("invalid evidence request descriptor")

    @property
    def descriptor_identity_sha256(self) -> str:
        return _sha(_canonical(_descriptor_value(self)))

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


def _descriptor_value(value: EvidenceRequestDescriptorV1) -> dict[str, object]:
    return {
        "admission_contract_version": value.admission_contract_version,
        "authority": value.authority.value,
        "capability_identity_sha256": value.capability_identity_sha256,
        "effective_from": value.effective_from.isoformat(),
        "effective_to": value.effective_to.isoformat(),
        "evidence_class": value.evidence_class.value,
        "isin": value.isin,
        "licence_review_identity_sha256": value.licence_review_identity_sha256,
        "maximum_response_bytes": value.maximum_response_bytes,
        "purpose": value.purpose,
        "source_locator": value.source_locator,
        "source_policy_version": value.source_policy_version,
    }


@dataclass(frozen=True, slots=True)
class ProspectiveReadinessReportV1:
    contract_version: str
    request_identity_sha256: str
    candidate_identity_sha256: tuple[str, ...]
    selected_identity_sha256: tuple[str, ...]
    decision_cutoff: datetime | None
    execution_state: ExecutionStateV1
    readiness_state: ReadinessStateV1
    authorization_state: AuthorizationStateV1
    rows: tuple[ReadinessRowV1, ...]
    ready_count: int
    blocked_count: int
    primary_reason_counts: tuple[tuple[PrimaryReasonV1, int], ...]
    request_descriptors: tuple[EvidenceRequestDescriptorV1, ...]
    provider_attempts: int = 0
    network_attempts: int = 0
    storage_write_attempts: int = 0

    def __post_init__(self) -> None:
        try:
            if (
                self.contract_version != PROSPECTIVE_READINESS_CONTRACT_VERSION_V1
                or not _valid_digest(self.request_identity_sha256)
                or type(self.candidate_identity_sha256) is not tuple
                or self.candidate_identity_sha256
                != tuple(sorted(set(self.candidate_identity_sha256)))
                or any(
                    not _valid_digest(value) for value in self.candidate_identity_sha256
                )
                or type(self.selected_identity_sha256) is not tuple
                or self.selected_identity_sha256
                != tuple(sorted(set(self.selected_identity_sha256)))
                or any(
                    not _valid_digest(value) for value in self.selected_identity_sha256
                )
                or (
                    self.decision_cutoff is not None
                    and not _aware(self.decision_cutoff)
                )
                or self.execution_state is not ExecutionStateV1.NOT_REQUESTED
                or type(self.readiness_state) is not ReadinessStateV1
                or type(self.authorization_state) is not AuthorizationStateV1
                or type(self.rows) is not tuple
                or len(self.rows) != 50
                or self.rows != tuple(sorted(self.rows, key=lambda row: row.isin))
                or len({row.isin for row in self.rows}) != 50
                or any(type(row) is not ReadinessRowV1 for row in self.rows)
                or type(self.ready_count) is not int
                or type(self.blocked_count) is not int
                or self.ready_count + self.blocked_count != 50
                or self.ready_count
                != sum(
                    row.readiness_state is ReadinessStateV1.READY for row in self.rows
                )
                or self.blocked_count != 50 - self.ready_count
                or type(self.primary_reason_counts) is not tuple
                or type(self.request_descriptors) is not tuple
                or len(self.request_descriptors) > MAX_REQUEST_DESCRIPTORS_V1
                or self.request_descriptors
                != tuple(
                    sorted(
                        self.request_descriptors,
                        key=lambda item: (item.evidence_class.value, item.isin or ""),
                    )
                )
                or any(
                    type(value) is not EvidenceRequestDescriptorV1
                    for value in self.request_descriptors
                )
                or any(
                    type(value) is not int or value != 0
                    for value in (
                        self.provider_attempts,
                        self.network_attempts,
                        self.storage_write_attempts,
                    )
                )
            ):
                raise ValueError
            counts: dict[PrimaryReasonV1, int] = {}
            for row in self.rows:
                if row.primary_reason is not None:
                    counts[row.primary_reason] = counts.get(row.primary_reason, 0) + 1
            expected = tuple(
                (reason, counts[reason])
                for reason in PrimaryReasonV1
                if reason in counts
            )
            if (
                self.primary_reason_counts != expected
                or sum(count for _, count in expected) != self.blocked_count
                or self.readiness_state
                is not (
                    ReadinessStateV1.READY
                    if self.ready_count == 50
                    else ReadinessStateV1.BLOCKED
                )
                or len(self.canonical_json_bytes()) > MAX_REPORT_BYTES_V1
            ):
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            raise ValueError("invalid prospective readiness report") from None

    @property
    def report_identity_sha256(self) -> str:
        return _sha(_canonical(_report_value(self, include_identity=False)))

    def canonical_json_bytes(self) -> bytes:
        return _canonical(_report_value(self, include_identity=True))

    def __init_subclass__(cls) -> None:
        raise TypeError("prospective readiness contracts cannot be subclassed")


def _diagnostic_value(value: ReadinessDiagnosticV1) -> dict[str, object]:
    return {
        "evidence_class": value.evidence_class.value,
        "evidence_identity_sha256": value.evidence_identity_sha256,
        "reason": value.reason.value,
    }


def _report_value(
    report: ProspectiveReadinessReportV1, *, include_identity: bool
) -> dict[str, object]:
    value: dict[str, object] = {
        "authorization_state": report.authorization_state.value,
        "blocked_count": report.blocked_count,
        "candidate_identity_sha256": list(report.candidate_identity_sha256),
        "contract_version": report.contract_version,
        "decision_cutoff": (
            None
            if report.decision_cutoff is None
            else _timestamp(report.decision_cutoff)
        ),
        "execution_state": report.execution_state.value,
        "network_attempts": report.network_attempts,
        "primary_reason_counts": [
            [reason.value, count] for reason, count in report.primary_reason_counts
        ],
        "provider_attempts": report.provider_attempts,
        "readiness_state": report.readiness_state.value,
        "ready_count": report.ready_count,
        "request_descriptors": [
            {
                **_descriptor_value(item),
                "descriptor_identity_sha256": item.descriptor_identity_sha256,
            }
            for item in report.request_descriptors
        ],
        "request_identity_sha256": report.request_identity_sha256,
        "rows": [
            {
                "diagnostics": [_diagnostic_value(item) for item in row.diagnostics],
                "isin": row.isin,
                "primary_reason": (
                    None if row.primary_reason is None else row.primary_reason.value
                ),
                "readiness_state": row.readiness_state.value,
            }
            for row in report.rows
        ],
        "selected_identity_sha256": list(report.selected_identity_sha256),
        "storage_write_attempts": report.storage_write_attempts,
    }
    if include_identity:
        value["report_identity_sha256"] = report.report_identity_sha256
    return value


def _authority_reason(receipt: SourceReceiptV1) -> PrimaryReasonV1 | None:
    expected = {
        EvidenceClassV1.MEMBERSHIP: EvidenceAuthorityV1.NSE_INDICES_LIMITED,
        EvidenceClassV1.SECTOR: EvidenceAuthorityV1.NSE_INDICES_LIMITED,
        EvidenceClassV1.SCHEDULE: EvidenceAuthorityV1.NSE_CAPITAL_MARKET,
        EvidenceClassV1.CORPORATE_ACTION: EvidenceAuthorityV1.UPSTOX_FUNDAMENTALS,
        EvidenceClassV1.ANCHOR_SESSION: EvidenceAuthorityV1.UPSTOX_MARKET_DATA,
    }
    if receipt.authority is not expected[receipt.evidence_class]:
        return PrimaryReasonV1.SOURCE_NOT_AUTHORITATIVE
    return None


def _receipt_reason(
    receipt: SourceReceiptV1,
    decision_session: date,
    cutoff: datetime,
    late_reason: PrimaryReasonV1,
) -> PrimaryReasonV1 | None:
    authority = _authority_reason(receipt)
    if authority is not None:
        return authority
    if (
        receipt.effective_from > decision_session
        or receipt.effective_to < decision_session
    ):
        return PrimaryReasonV1.PUBLICATION_UNPROVEN
    if receipt.knowledge_time > cutoff:
        return late_reason
    return None


def _resolve_schedule(  # noqa: C901 -- frozen gate transaction
    request: ProspectiveReadinessRequestV1,
) -> tuple[
    datetime | None, PrimaryReasonV1 | None, str | None, ExpectedSessionSchedule | None
]:
    if not request.schedule_candidates:
        return None, PrimaryReasonV1.SCHEDULE_MISSING, None, None
    if len(request.schedule_candidates) != 1:
        return None, PrimaryReasonV1.SCHEDULE_AMBIGUOUS, None, None
    candidate = request.schedule_candidates[0]
    try:
        schedule = parse_canonical_schedule_bytes(candidate.canonical_bytes)
        if (
            canonical_schedule_bytes(schedule) != candidate.canonical_bytes
            or _sha(candidate.canonical_bytes) not in _PINNED_SCHEDULE_SHA256_V1
        ):
            raise ValueError
    except Exception:
        return (
            None,
            PrimaryReasonV1.SCHEDULE_CORRUPT,
            candidate.candidate_identity_sha256,
            None,
        )
    if (
        schedule.source != _NSE_SCHEDULE_SOURCE
        or candidate.receipt.release_identity != schedule.source_release
    ):
        return (
            None,
            PrimaryReasonV1.SOURCE_NOT_AUTHORITATIVE,
            candidate.candidate_identity_sha256,
            schedule,
        )
    if candidate.receipt.public_available_at < schedule.as_of:
        return (
            None,
            PrimaryReasonV1.PUBLICATION_UNPROVEN,
            candidate.candidate_identity_sha256,
            schedule,
        )
    session = next(
        (
            item
            for item in schedule.sessions
            if item.trade_date == request.decision_session
        ),
        None,
    )
    if session is None:
        return (
            None,
            PrimaryReasonV1.SCHEDULE_COVERAGE_INCOMPLETE,
            candidate.candidate_identity_sha256,
            schedule,
        )
    cutoff = session.close_at
    if not schedule_covers_full_calendar_range(
        schedule, schedule.covered_from, request.decision_session
    ):
        return (
            cutoff,
            PrimaryReasonV1.SCHEDULE_COVERAGE_INCOMPLETE,
            candidate.candidate_identity_sha256,
            schedule,
        )
    receipt_reason = _receipt_reason(
        candidate.receipt,
        request.decision_session,
        cutoff,
        PrimaryReasonV1.SCHEDULE_LATE,
    )
    if receipt_reason is not None:
        return cutoff, receipt_reason, candidate.candidate_identity_sha256, schedule
    if request.evaluated_at < cutoff:
        return (
            cutoff,
            PrimaryReasonV1.CLOCK_UNTRUSTED,
            candidate.candidate_identity_sha256,
            schedule,
        )
    return cutoff, None, candidate.candidate_identity_sha256, schedule


def _resolve_universe(
    request: ProspectiveReadinessRequestV1, cutoff: datetime | None
) -> tuple[
    PrimaryReasonV1 | None,
    PrimaryReasonV1 | None,
    str | None,
]:
    if not request.universe_candidates:
        return PrimaryReasonV1.MEMBERSHIP_MISSING, PrimaryReasonV1.SECTOR_MISSING, None
    if len(request.universe_candidates) != 1:
        return (
            PrimaryReasonV1.MEMBERSHIP_AMBIGUOUS,
            PrimaryReasonV1.SECTOR_AMBIGUOUS,
            None,
        )
    candidate = request.universe_candidates[0]
    identity = candidate.candidate_identity_sha256
    try:
        snapshot = Nifty50UniverseSnapshotV1.from_canonical_json_bytes(
            candidate.canonical_bytes
        )
        if snapshot.canonical_json_bytes() != candidate.canonical_bytes:
            raise ValueError
    except Exception:
        return (
            PrimaryReasonV1.MEMBERSHIP_CORRUPT,
            PrimaryReasonV1.SECTOR_CORRUPT,
            identity,
        )
    if (
        _sha(candidate.canonical_bytes) != _PINNED_UNIVERSE_SHA256_V1
        or request.trusted_universe_snapshot_sha256 != _PINNED_UNIVERSE_SHA256_V1
    ):
        mismatch = PrimaryReasonV1.EVIDENCE_IDENTITY_MISMATCH
        return mismatch, mismatch, identity
    if tuple(item.isin for item in snapshot.constituents) != request.required_isins:
        mismatch = PrimaryReasonV1.EVIDENCE_IDENTITY_MISMATCH
        return mismatch, mismatch, identity
    if (
        snapshot.membership_source != _NSE_INDICES_SOURCE
        or snapshot.sector_source != _NSE_INDICES_SOURCE
        or candidate.membership_receipt.release_identity != snapshot.membership_release
        or candidate.sector_receipt.release_identity != snapshot.sector_release
    ):
        return (
            PrimaryReasonV1.SOURCE_NOT_AUTHORITATIVE,
            PrimaryReasonV1.SOURCE_NOT_AUTHORITATIVE,
            identity,
        )
    if (
        candidate.membership_receipt.public_available_at
        < snapshot.membership_published_at
        or candidate.sector_receipt.public_available_at < snapshot.sector_published_at
        or candidate.membership_receipt.retained_at < snapshot.membership_retrieved_at
        or candidate.sector_receipt.retained_at < snapshot.sector_retrieved_at
    ):
        return (
            PrimaryReasonV1.PUBLICATION_UNPROVEN,
            PrimaryReasonV1.PUBLICATION_UNPROVEN,
            identity,
        )
    if cutoff is None:
        return None, None, identity
    membership = _receipt_reason(
        candidate.membership_receipt,
        request.decision_session,
        cutoff,
        PrimaryReasonV1.MEMBERSHIP_LATE,
    )
    sector = _receipt_reason(
        candidate.sector_receipt,
        request.decision_session,
        cutoff,
        PrimaryReasonV1.SECTOR_LATE,
    )
    return membership, sector, identity


def _corporate_action_reason(  # noqa: C901 -- frozen revision reducer
    request: ProspectiveReadinessRequestV1,
    candidate: CorporateActionEvidenceCandidateV1 | None,
    cutoff: datetime | None,
) -> tuple[PrimaryReasonV1 | None, str | None]:
    if candidate is None:
        return PrimaryReasonV1.CORPORATE_ACTION_MISSING, None
    identity = candidate.candidate_identity_sha256
    if not candidate.observations:
        return PrimaryReasonV1.CORPORATE_ACTION_MISSING, identity
    parsed: list[tuple[CorporateActionSnapshotV1, CorporateActionObservationV1]] = []
    for observation in candidate.observations:
        try:
            snapshot = CorporateActionSnapshotV1.from_canonical_json_bytes(
                observation.canonical_bytes
            )
            if snapshot.canonical_json_bytes() != observation.canonical_bytes:
                raise ValueError
        except Exception:
            return PrimaryReasonV1.CORPORATE_ACTION_CORRUPT, identity
        if snapshot.isin != candidate.isin:
            return PrimaryReasonV1.EVIDENCE_IDENTITY_MISMATCH, identity
        if (
            snapshot.source != "upstox-fundamentals-v2"
            or observation.receipt.release_identity != snapshot.source_release
            or observation.receipt.response_completed_at < snapshot.retrieved_at
        ):
            return PrimaryReasonV1.SOURCE_NOT_AUTHORITATIVE, identity
        if cutoff is not None:
            receipt_reason = _receipt_reason(
                observation.receipt,
                request.decision_session,
                cutoff,
                PrimaryReasonV1.CORPORATE_ACTION_LATE,
            )
            if receipt_reason is not None:
                return receipt_reason, identity
        parsed.append((snapshot, observation))
    parsed.sort(key=lambda item: item[1].receipt.knowledge_time)
    previous: set[str] = set()
    for snapshot, observation in parsed:
        current = {event.event_digest_sha256 for event in snapshot.events}
        if (
            previous
            and not previous.issubset(current)
            and observation.receipt.supersedes_revision_identity is None
        ):
            return PrimaryReasonV1.CORPORATE_ACTION_REVISION_UNPROVEN, identity
        previous |= current
    event_digests = previous
    for filing in candidate.authoritative_filings:
        if cutoff is None:
            return PrimaryReasonV1.CORPORATE_ACTION_STATUS_UNPROVEN, identity
        filing_reason = _receipt_reason(
            filing.receipt,
            request.decision_session,
            cutoff,
            PrimaryReasonV1.CORPORATE_ACTION_LATE,
        )
        if filing_reason is not None:
            return filing_reason, identity
    filing_digests = {
        value.event_digest_sha256 for value in candidate.authoritative_filings
    }
    if event_digests - filing_digests:
        return PrimaryReasonV1.CORPORATE_ACTION_STATUS_UNPROVEN, identity
    # V1 Upstox has no authoritative negative-completeness capability. Even an
    # empty/current response or fully status-proven positives cannot establish it.
    return PrimaryReasonV1.CORPORATE_ACTION_COMPLETENESS_UNPROVEN, identity


def _anchor_reason(
    request: ProspectiveReadinessRequestV1,
    fact: AnchorSessionFactV1 | None,
    cutoff: datetime | None,
    schedule_digest: str | None,
) -> tuple[PrimaryReasonV1 | None, str | None]:
    if fact is None:
        return PrimaryReasonV1.ANCHOR_SESSION_INCOMPLETE, None
    identity = fact.fact_identity_sha256
    if fact.decision_session != request.decision_session or (
        schedule_digest is not None and fact.schedule_sha256 != schedule_digest
    ):
        return PrimaryReasonV1.ANCHOR_SESSION_CORRUPT, identity
    if cutoff is not None:
        reason = _receipt_reason(
            fact.receipt,
            request.decision_session,
            cutoff,
            PrimaryReasonV1.ANCHOR_SESSION_LATE,
        )
        if reason is not None:
            return reason, identity
    return None, identity


def _descriptors(
    request: ProspectiveReadinessRequestV1,
    rows: tuple[ReadinessRowV1, ...],
) -> tuple[EvidenceRequestDescriptorV1, ...]:
    capabilities = {
        item.evidence_class: item for item in request.planning_source_capabilities
    }
    per_isin = {EvidenceClassV1.CORPORATE_ACTION, EvidenceClassV1.ANCHOR_SESSION}
    incurable = {
        PrimaryReasonV1.SOURCE_NOT_AUTHORITATIVE,
        PrimaryReasonV1.LICENCE_UNRESOLVED,
        PrimaryReasonV1.CORPORATE_ACTION_COMPLETENESS_UNPROVEN,
        PrimaryReasonV1.CORPORATE_ACTION_REVISION_UNPROVEN,
        PrimaryReasonV1.EVIDENCE_IDENTITY_MISMATCH,
    }
    needed: set[tuple[EvidenceClassV1, str | None]] = set()
    for row in rows:
        for diagnostic in row.diagnostics:
            if diagnostic.reason not in incurable:
                needed.add(
                    (
                        diagnostic.evidence_class,
                        row.isin if diagnostic.evidence_class in per_isin else None,
                    )
                )
    result: list[EvidenceRequestDescriptorV1] = []
    for evidence_class, isin in sorted(
        needed, key=lambda item: (item[0].value, item[1] or "")
    ):
        capability = capabilities.get(evidence_class)
        if capability is None or not (
            capability.effective_from
            <= request.decision_session
            <= capability.effective_to
        ):
            continue
        # More polling of Upstox cannot cure negative corporate-action completeness.
        if evidence_class is EvidenceClassV1.CORPORATE_ACTION:
            continue
        result.append(
            EvidenceRequestDescriptorV1(
                evidence_class,
                isin,
                capability.authority,
                capability.capability_identity_sha256,
                capability.source_locator,
                capability.effective_from,
                capability.effective_to,
                f"retain-{evidence_class.value.lower()}-evidence",
                PROSPECTIVE_SOURCE_POLICY_VERSION_V1,
                capability.licence_review_identity_sha256,
                capability.maximum_response_bytes,
                capability.admission_contract_version,
            )
        )
    return tuple(result)


def _authorization_state(
    request: ProspectiveReadinessRequestV1,
    descriptors: tuple[EvidenceRequestDescriptorV1, ...],
) -> AuthorizationStateV1:
    if not descriptors:
        return AuthorizationStateV1.NOT_REQUIRED
    authorization = request.execution_authorization
    validation = request.authorization_validation_receipt
    if authorization is None or validation is None:
        return AuthorizationStateV1.NOT_AUTHORIZED
    classes = tuple(
        sorted(
            {item.evidence_class for item in descriptors}, key=lambda item: item.value
        )
    )
    authorities = tuple(
        sorted({item.authority for item in descriptors}, key=lambda item: item.value)
    )
    valid = (
        validation.authorization_identity_sha256
        == authorization.authorization_identity_sha256
        and authorization.request_manifest_sha256 == request.request_manifest_sha256
        and authorization.sorted_isins_sha256 == request.sorted_isins_sha256
        and all(item in authorization.allowed_evidence_classes for item in classes)
        and all(item in authorization.allowed_authorities for item in authorities)
        and authorization.effective_from
        <= request.decision_session
        <= authorization.effective_to
        and authorization.issued_at
        <= validation.validated_at
        <= authorization.expires_at
        and authorization.maximum_attempts >= len(descriptors)
        and authorization.maximum_response_bytes
        >= sum(item.maximum_response_bytes for item in descriptors)
    )
    return (
        AuthorizationStateV1.AUTHORIZED_AS_OF_VALIDATION
        if valid
        else AuthorizationStateV1.AUTHORIZATION_INVALID
    )


def evaluate_prospective_readiness_v1(
    request: ProspectiveReadinessRequestV1,
) -> ProspectiveReadinessReportV1:
    """Reduce already supplied immutable evidence without calls or writes."""
    if type(request) is not ProspectiveReadinessRequestV1:
        raise ValueError("invalid prospective readiness request")
    cutoff, schedule_reason, schedule_identity, schedule = _resolve_schedule(request)
    membership_reason, sector_reason, universe_identity = _resolve_universe(
        request, cutoff
    )
    common = (
        (EvidenceClassV1.MEMBERSHIP, membership_reason, universe_identity),
        (EvidenceClassV1.SECTOR, sector_reason, universe_identity),
        (EvidenceClassV1.SCHEDULE, schedule_reason, schedule_identity),
    )
    ca_by_isin = {item.isin: item for item in request.corporate_action_candidates}
    anchor_by_isin = {item.isin: item for item in request.anchor_facts}
    schedule_digest = (
        None if schedule is None else _sha(canonical_schedule_bytes(schedule))
    )
    rows: list[ReadinessRowV1] = []
    for isin in request.required_isins:
        diagnostics: list[ReadinessDiagnosticV1] = []
        for evidence_class, reason, identity in common:
            if reason is not None:
                diagnostics.append(
                    ReadinessDiagnosticV1(evidence_class, reason, identity)
                )
        ca_reason, ca_identity = _corporate_action_reason(
            request, ca_by_isin.get(isin), cutoff
        )
        if ca_reason is not None:
            diagnostics.append(
                ReadinessDiagnosticV1(
                    EvidenceClassV1.CORPORATE_ACTION, ca_reason, ca_identity
                )
            )
        anchor_reason, anchor_identity = _anchor_reason(
            request, anchor_by_isin.get(isin), cutoff, schedule_digest
        )
        if anchor_reason is not None:
            diagnostics.append(
                ReadinessDiagnosticV1(
                    EvidenceClassV1.ANCHOR_SESSION, anchor_reason, anchor_identity
                )
            )
        diagnostics.sort(key=lambda item: list(PrimaryReasonV1).index(item.reason))
        primary = None if not diagnostics else diagnostics[0].reason
        rows.append(
            ReadinessRowV1(
                isin,
                ReadinessStateV1.READY if primary is None else ReadinessStateV1.BLOCKED,
                primary,
                tuple(diagnostics),
            )
        )
    typed_rows = tuple(rows)
    descriptors = _descriptors(request, typed_rows)
    authorization_state = _authorization_state(request, descriptors)
    counts: dict[PrimaryReasonV1, int] = {}
    for row in typed_rows:
        if row.primary_reason is not None:
            counts[row.primary_reason] = counts.get(row.primary_reason, 0) + 1
    primary_counts = tuple(
        (reason, counts[reason]) for reason in PrimaryReasonV1 if reason in counts
    )
    candidates = tuple(
        sorted(
            {
                *(
                    item.candidate_identity_sha256
                    for item in request.universe_candidates
                ),
                *(
                    item.candidate_identity_sha256
                    for item in request.schedule_candidates
                ),
                *(
                    item.candidate_identity_sha256
                    for item in request.corporate_action_candidates
                ),
                *(item.fact_identity_sha256 for item in request.anchor_facts),
            }
        )
    )
    selected = candidates
    ready_count = sum(
        row.readiness_state is ReadinessStateV1.READY for row in typed_rows
    )
    return ProspectiveReadinessReportV1(
        PROSPECTIVE_READINESS_CONTRACT_VERSION_V1,
        request.request_identity_sha256,
        candidates,
        selected,
        cutoff,
        ExecutionStateV1.NOT_REQUESTED,
        ReadinessStateV1.READY if ready_count == 50 else ReadinessStateV1.BLOCKED,
        authorization_state,
        typed_rows,
        ready_count,
        50 - ready_count,
        primary_counts,
        descriptors,
        0,
        0,
        0,
    )


# Backward-compatible spelling only within this unmerged Sprint-5 branch.
build_prospective_readiness_report_v1 = evaluate_prospective_readiness_v1

__all__ = [
    "PROSPECTIVE_READINESS_CONTRACT_VERSION_V1",
    "PROSPECTIVE_SOURCE_POLICY_VERSION_V1",
    "AnchorSessionFactV1",
    "AuthorizationStateV1",
    "AuthorizationValidationReceiptV1",
    "AuthoritativeActionFilingV1",
    "CorporateActionEvidenceCandidateV1",
    "CorporateActionObservationV1",
    "EvidenceAuthorityV1",
    "EvidenceClassV1",
    "EvidenceExecutionAuthorizationV1",
    "EvidenceRequestDescriptorV1",
    "ExecutionStateV1",
    "PlanningSourceCapabilityV1",
    "PrimaryReasonV1",
    "ProspectiveReadinessReportV1",
    "ProspectiveReadinessRequestV1",
    "ReadinessDiagnosticV1",
    "ReadinessRowV1",
    "ReadinessStateV1",
    "ScheduleEvidenceCandidateV1",
    "SourceReceiptV1",
    "UniverseEvidenceCandidateV1",
    "evaluate_prospective_readiness_v1",
]
