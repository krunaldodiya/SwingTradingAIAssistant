"""Pure, fail-closed Market Regime Layer B acquisition decision."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final, TypeVar, cast

from . import acquisition_manifest

_CONTRACT_VERSION: Final = "market-regime-layer-b-acquisition-decision@v1"
_MANIFEST_VERSION: Final = "market-regime-layer-b-acquisition-manifest@v1"
_RECEIPT_VERSION: Final = "market-regime-layer-b-authorization-validation@v1"
_AUTHORITY_ROLE: Final = "FULL_ACQUISITION_AUTHORITY"
_MAX_MANIFEST_BYTES: Final = 16 * 1024
_MAX_RECEIPT_BYTES: Final = 4 * 1024
_MAX_REPORT_BYTES: Final = 8 * 1024
_MAX_JSON_DEPTH: Final = 8
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_UTC_INSTANT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")
_SCOPE_FIELDS: Final = (
    "manifest_version",
    "market_regime_contract_identity_sha256",
    "layer_b_protocol_identity_sha256",
    "acquisition_scope_identity_sha256",
    "capability_evidence_state",
    "capability_evidence_identity_sha256",
    "capability_assessed_at",
    "source_and_pit_evidence_bundle_identity_sha256",
    "terms_and_use_approval_identity_sha256",
    "operational_scope_approval_identity_sha256",
    "prerequisites_assessed_at",
    "acquisition_authorization",
)
_MANIFEST_FIELDS: Final = frozenset(
    (
        *_SCOPE_FIELDS,
        "manifest_scope_identity_sha256",
        "authorization_validation_receipt_identity_sha256",
        "manifest_identity_sha256",
    )
)
_RECEIPT_FIELDS: Final = frozenset(
    {
        "receipt_version",
        "manifest_scope_identity_sha256",
        "trusted_clock_source_identity_sha256",
        "validation_started_at",
        "authorization_validated_at",
        "validation_completed_at",
        "receipt_identity_sha256",
    }
)
_AUTHORIZATION_FIELDS: Final = frozenset(
    {
        "authority_role",
        "authority_identity_sha256",
        "authorization_record_identity_sha256",
        "issued_at",
        "not_before",
        "expires_at",
    }
)
_EnumT = TypeVar("_EnumT", bound=StrEnum)


class CapabilityEvidenceStateV1(StrEnum):
    OBSERVED = "OBSERVED"
    NOT_OBSERVED = "NOT_OBSERVED"


class AcquisitionDecisionStateV1(StrEnum):
    APPROVED_TO_ACQUIRE = "APPROVED_TO_ACQUIRE"
    BLOCKED = "BLOCKED"


class AcquisitionBlockerV1(StrEnum):
    SEALED_MANIFEST_MISSING = "SEALED_MANIFEST_MISSING"
    SEALED_MANIFEST_INVALID = "SEALED_MANIFEST_INVALID"
    CAPABILITY_EVIDENCE_MISSING = "CAPABILITY_EVIDENCE_MISSING"
    SOURCE_AND_PIT_EVIDENCE_UNPROVEN = "SOURCE_AND_PIT_EVIDENCE_UNPROVEN"
    TERMS_AND_USE_UNAPPROVED = "TERMS_AND_USE_UNAPPROVED"
    OPERATIONAL_SCOPE_UNAPPROVED = "OPERATIONAL_SCOPE_UNAPPROVED"
    OWNER_AUTHORIZATION_NOT_IN_FORCE = "OWNER_AUTHORIZATION_NOT_IN_FORCE"


@dataclass(frozen=True, slots=True)
class CapabilityEvidenceInputV1:
    state: CapabilityEvidenceStateV1
    evidence_identity_sha256: str

    def __post_init__(self) -> None:
        if type(self.state) is not CapabilityEvidenceStateV1:
            raise ValueError("invalid capability evidence state")
        _require_sha256(self.evidence_identity_sha256)

    def __init_subclass__(cls) -> None:
        raise TypeError("acquisition decision contracts cannot be subclassed")


@dataclass(frozen=True, slots=True)
class AcquisitionAuthorizationBindingV1:
    authority_role: str
    authority_identity_sha256: str
    authorization_record_identity_sha256: str
    issued_at: datetime
    not_before: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.authority_role) is not str
            or self.authority_role != _AUTHORITY_ROLE
        ):
            raise ValueError("invalid acquisition authority role")
        _require_sha256(self.authority_identity_sha256)
        _require_sha256(self.authorization_record_identity_sha256)
        for name in ("issued_at", "not_before", "expires_at"):
            value = _require_utc_datetime(getattr(self, name))
            object.__setattr__(self, name, value)

    def __init_subclass__(cls) -> None:
        raise TypeError("acquisition decision contracts cannot be subclassed")


@dataclass(frozen=True, slots=True)
class AuthorizationValidationReceiptV1:
    receipt_version: str
    manifest_scope_identity_sha256: str
    trusted_clock_source_identity_sha256: str
    validation_started_at: datetime
    authorization_validated_at: datetime
    validation_completed_at: datetime
    receipt_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.receipt_version) is not str
            or self.receipt_version != _RECEIPT_VERSION
        ):
            raise ValueError("invalid authorization validation receipt version")
        _require_sha256(self.manifest_scope_identity_sha256)
        _require_sha256(self.trusted_clock_source_identity_sha256)
        _require_sha256(self.receipt_identity_sha256)
        for name in (
            "validation_started_at",
            "authorization_validated_at",
            "validation_completed_at",
        ):
            value = _require_utc_datetime(getattr(self, name))
            object.__setattr__(self, name, value)
        if len(_canonical(_receipt_value(self))) > _MAX_RECEIPT_BYTES:
            raise ValueError("authorization validation receipt exceeds bound")

    def canonical_json_bytes(self) -> bytes:
        return _canonical(_receipt_value(self))

    def __init_subclass__(cls) -> None:
        raise TypeError("acquisition decision contracts cannot be subclassed")


@dataclass(frozen=True, slots=True)
class AcquisitionDecisionInputV1:
    contract_version: str
    capability_evidence: CapabilityEvidenceInputV1 | None
    authorization_validation_receipt: AuthorizationValidationReceiptV1 | None

    def __post_init__(self) -> None:
        if (
            type(self.contract_version) is not str
            or self.contract_version != _CONTRACT_VERSION
        ):
            raise ValueError("invalid acquisition decision contract version")
        if self.capability_evidence is not None:
            _revalidate_capability(self.capability_evidence)
        if self.authorization_validation_receipt is not None:
            _revalidate_receipt(self.authorization_validation_receipt)

    def canonical_json_bytes(self) -> bytes:
        return _canonical(_decision_input_value(self))

    @classmethod
    def from_canonical_json_bytes(cls, raw: bytes) -> AcquisitionDecisionInputV1:
        return parse_acquisition_decision_input_v1(raw)

    def __init_subclass__(cls) -> None:
        raise TypeError("acquisition decision contracts cannot be subclassed")


@dataclass(frozen=True, slots=True)
class AcquisitionAuthorizationManifestV1:
    manifest_version: str
    market_regime_contract_identity_sha256: str
    layer_b_protocol_identity_sha256: str
    acquisition_scope_identity_sha256: str
    capability_evidence_state: CapabilityEvidenceStateV1 | None
    capability_evidence_identity_sha256: str | None
    capability_assessed_at: datetime | None
    source_and_pit_evidence_bundle_identity_sha256: str | None
    terms_and_use_approval_identity_sha256: str | None
    operational_scope_approval_identity_sha256: str | None
    prerequisites_assessed_at: datetime
    acquisition_authorization: AcquisitionAuthorizationBindingV1 | None
    manifest_scope_identity_sha256: str
    authorization_validation_receipt_identity_sha256: str | None
    manifest_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.manifest_version) is not str
            or self.manifest_version != _MANIFEST_VERSION
        ):
            raise ValueError("invalid acquisition manifest version")
        for name in (
            "market_regime_contract_identity_sha256",
            "layer_b_protocol_identity_sha256",
            "acquisition_scope_identity_sha256",
            "manifest_scope_identity_sha256",
            "manifest_identity_sha256",
        ):
            _require_sha256(getattr(self, name))
        object.__setattr__(
            self,
            "capability_assessed_at",
            _validate_capability_group(
                self.capability_evidence_state,
                self.capability_evidence_identity_sha256,
                self.capability_assessed_at,
            ),
        )
        for name in (
            "source_and_pit_evidence_bundle_identity_sha256",
            "terms_and_use_approval_identity_sha256",
            "operational_scope_approval_identity_sha256",
            "authorization_validation_receipt_identity_sha256",
        ):
            _require_optional_sha256(getattr(self, name))
        object.__setattr__(
            self,
            "prerequisites_assessed_at",
            _require_utc_datetime(self.prerequisites_assessed_at),
        )
        if self.acquisition_authorization is not None:
            _revalidate_authorization(self.acquisition_authorization)
        manifest_value = _manifest_value(self)
        scope_projection = {field: manifest_value[field] for field in _SCOPE_FIELDS}
        if self.manifest_scope_identity_sha256 != _identity(scope_projection):
            raise ValueError("invalid acquisition manifest scope identity")
        final_projection = {
            key: item
            for key, item in manifest_value.items()
            if key != "manifest_identity_sha256"
        }
        if self.manifest_identity_sha256 != _identity(final_projection):
            raise ValueError("invalid acquisition manifest identity")
        if len(_canonical(manifest_value)) > _MAX_MANIFEST_BYTES:
            raise ValueError("acquisition manifest exceeds bound")

    def canonical_json_bytes(self) -> bytes:
        return _canonical(_manifest_value(self))

    def __init_subclass__(cls) -> None:
        raise TypeError("acquisition decision contracts cannot be subclassed")


@dataclass(frozen=True, slots=True)
class AcquisitionDecisionReportV1:
    contract_version: str
    decision_state: AcquisitionDecisionStateV1
    primary_blocker: AcquisitionBlockerV1 | None
    sealed_manifest_identity_sha256: str | None
    authenticated_capability_evidence_identity_sha256: str | None
    authorization_validation_receipt_identity_sha256: str | None
    assessed_at: datetime | None
    report_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.contract_version) is not str
            or self.contract_version != _CONTRACT_VERSION
        ):
            raise ValueError("invalid acquisition decision report version")
        if type(self.decision_state) is not AcquisitionDecisionStateV1:
            raise ValueError("invalid acquisition decision state")
        if (
            self.primary_blocker is not None
            and type(self.primary_blocker) is not AcquisitionBlockerV1
        ):
            raise ValueError("invalid acquisition blocker")
        if (self.decision_state is AcquisitionDecisionStateV1.APPROVED_TO_ACQUIRE) != (
            self.primary_blocker is None
        ):
            raise ValueError("inconsistent acquisition decision state")
        for name in (
            "sealed_manifest_identity_sha256",
            "authenticated_capability_evidence_identity_sha256",
            "authorization_validation_receipt_identity_sha256",
        ):
            _require_optional_sha256(getattr(self, name))
        if self.assessed_at is not None:
            object.__setattr__(
                self, "assessed_at", _require_utc_datetime(self.assessed_at)
            )
        _validate_report_nullability(self)
        _require_sha256(self.report_identity_sha256)
        if self.report_identity_sha256 != _identity(_report_projection(self)):
            raise ValueError("invalid acquisition decision report identity")
        if len(_canonical(_report_value(self))) > _MAX_REPORT_BYTES:
            raise ValueError("acquisition decision report exceeds bound")

    def canonical_json_bytes(self) -> bytes:
        return _canonical(_report_value(self))

    def __init_subclass__(cls) -> None:
        raise TypeError("acquisition decision contracts cannot be subclassed")


def parse_acquisition_decision_input_v1(raw: bytes) -> AcquisitionDecisionInputV1:
    """Admit only the exact bounded canonical decision-input representation."""
    value = _strict_canonical_object(raw, maximum=16 * 1024)
    _require_closed(
        value,
        {"contract_version", "capability_evidence", "authorization_validation_receipt"},
    )
    capability_value = value["capability_evidence"]
    capability: CapabilityEvidenceInputV1 | None
    if capability_value is None:
        capability = None
    else:
        capability_object = _require_closed(
            capability_value, {"state", "evidence_identity_sha256"}
        )
        capability = CapabilityEvidenceInputV1(
            state=_enum(CapabilityEvidenceStateV1, capability_object["state"]),
            evidence_identity_sha256=_require_sha256(
                capability_object["evidence_identity_sha256"]
            ),
        )
    receipt_value = value["authorization_validation_receipt"]
    receipt = None if receipt_value is None else _parse_receipt(receipt_value)
    request = AcquisitionDecisionInputV1(
        contract_version=_require_literal(value["contract_version"], _CONTRACT_VERSION),
        capability_evidence=capability,
        authorization_validation_receipt=receipt,
    )
    if request.canonical_json_bytes() != raw:
        raise ValueError("noncanonical acquisition decision input")
    return request


def decide_acquisition_v1(
    request: AcquisitionDecisionInputV1,
) -> AcquisitionDecisionReportV1:
    """Reduce one structurally admitted input against the immutable build seal."""
    _revalidate_request(request)
    sealed_bytes = acquisition_manifest.SEALED_ACQUISITION_MANIFEST_CANONICAL_JSON_LF
    if sealed_bytes is None:
        return _blocked(AcquisitionBlockerV1.SEALED_MANIFEST_MISSING)
    try:
        manifest = _parse_sealed_manifest(
            sealed_bytes,
            acquisition_manifest.SEALED_ACQUISITION_MANIFEST_IDENTITY_SHA256,
        )
    except Exception:
        return _blocked(AcquisitionBlockerV1.SEALED_MANIFEST_INVALID)

    capability = request.capability_evidence
    if (
        capability is None
        or capability.state is not CapabilityEvidenceStateV1.OBSERVED
        or manifest.capability_evidence_state is not CapabilityEvidenceStateV1.OBSERVED
        or capability.state is not manifest.capability_evidence_state
        or capability.evidence_identity_sha256
        != manifest.capability_evidence_identity_sha256
    ):
        return _blocked(
            AcquisitionBlockerV1.CAPABILITY_EVIDENCE_MISSING,
            manifest=manifest,
        )
    if manifest.source_and_pit_evidence_bundle_identity_sha256 is None:
        return _blocked(
            AcquisitionBlockerV1.SOURCE_AND_PIT_EVIDENCE_UNPROVEN,
            manifest=manifest,
            capability_authenticated=True,
        )
    if manifest.terms_and_use_approval_identity_sha256 is None:
        return _blocked(
            AcquisitionBlockerV1.TERMS_AND_USE_UNAPPROVED,
            manifest=manifest,
            capability_authenticated=True,
        )
    if manifest.operational_scope_approval_identity_sha256 is None:
        return _blocked(
            AcquisitionBlockerV1.OPERATIONAL_SCOPE_UNAPPROVED,
            manifest=manifest,
            capability_authenticated=True,
        )

    receipt = _authenticated_receipt(request.authorization_validation_receipt, manifest)
    authorization = manifest.acquisition_authorization
    if (
        authorization is None
        or receipt is None
        or not _authorization_in_force(manifest, authorization, receipt)
    ):
        return _blocked(
            AcquisitionBlockerV1.OWNER_AUTHORIZATION_NOT_IN_FORCE,
            manifest=manifest,
            capability_authenticated=True,
            receipt=receipt,
        )
    return _report(
        decision_state=AcquisitionDecisionStateV1.APPROVED_TO_ACQUIRE,
        primary_blocker=None,
        manifest=manifest,
        capability_authenticated=True,
        receipt=receipt,
    )


def _parse_sealed_manifest(
    raw: object, companion_identity: object
) -> AcquisitionAuthorizationManifestV1:
    if type(raw) is not bytes:
        raise ValueError("invalid sealed acquisition manifest bytes")
    value = _strict_canonical_object(raw, maximum=_MAX_MANIFEST_BYTES)
    _require_closed(value, _MANIFEST_FIELDS)
    authorization_value = value["acquisition_authorization"]
    authorization = (
        None
        if authorization_value is None
        else _parse_authorization(authorization_value)
    )
    capability_state_value = value["capability_evidence_state"]
    capability_identity_value = value["capability_evidence_identity_sha256"]
    capability_assessed_at_value = value["capability_assessed_at"]
    capability_state = (
        None
        if capability_state_value is None
        else _enum(CapabilityEvidenceStateV1, capability_state_value)
    )
    capability_identity = _optional_sha256(capability_identity_value)
    capability_assessed_at = (
        None
        if capability_assessed_at_value is None
        else _parse_utc_instant(capability_assessed_at_value)
    )
    manifest = AcquisitionAuthorizationManifestV1(
        manifest_version=_require_literal(value["manifest_version"], _MANIFEST_VERSION),
        market_regime_contract_identity_sha256=_require_sha256(
            value["market_regime_contract_identity_sha256"]
        ),
        layer_b_protocol_identity_sha256=_require_sha256(
            value["layer_b_protocol_identity_sha256"]
        ),
        acquisition_scope_identity_sha256=_require_sha256(
            value["acquisition_scope_identity_sha256"]
        ),
        capability_evidence_state=capability_state,
        capability_evidence_identity_sha256=capability_identity,
        capability_assessed_at=capability_assessed_at,
        source_and_pit_evidence_bundle_identity_sha256=_optional_sha256(
            value["source_and_pit_evidence_bundle_identity_sha256"]
        ),
        terms_and_use_approval_identity_sha256=_optional_sha256(
            value["terms_and_use_approval_identity_sha256"]
        ),
        operational_scope_approval_identity_sha256=_optional_sha256(
            value["operational_scope_approval_identity_sha256"]
        ),
        prerequisites_assessed_at=_parse_utc_instant(
            value["prerequisites_assessed_at"]
        ),
        acquisition_authorization=authorization,
        manifest_scope_identity_sha256=_require_sha256(
            value["manifest_scope_identity_sha256"]
        ),
        authorization_validation_receipt_identity_sha256=_optional_sha256(
            value["authorization_validation_receipt_identity_sha256"]
        ),
        manifest_identity_sha256=_require_sha256(value["manifest_identity_sha256"]),
    )
    manifest_value = _manifest_value(manifest)
    scope_projection = {field: manifest_value[field] for field in _SCOPE_FIELDS}
    if manifest.manifest_scope_identity_sha256 != _identity(scope_projection):
        raise ValueError("invalid acquisition manifest scope identity")
    final_projection = {
        key: item
        for key, item in manifest_value.items()
        if key != "manifest_identity_sha256"
    }
    if manifest.manifest_identity_sha256 != _identity(final_projection):
        raise ValueError("invalid acquisition manifest identity")
    if _require_sha256(companion_identity) != manifest.manifest_identity_sha256:
        raise ValueError("sealed acquisition manifest companion pin mismatch")
    if manifest.canonical_json_bytes() != raw:
        raise ValueError("noncanonical sealed acquisition manifest")
    return manifest


def _parse_authorization(value: object) -> AcquisitionAuthorizationBindingV1:
    item = _require_closed(value, _AUTHORIZATION_FIELDS)
    return AcquisitionAuthorizationBindingV1(
        authority_role=_require_literal(item["authority_role"], _AUTHORITY_ROLE),
        authority_identity_sha256=_require_sha256(item["authority_identity_sha256"]),
        authorization_record_identity_sha256=_require_sha256(
            item["authorization_record_identity_sha256"]
        ),
        issued_at=_parse_utc_instant(item["issued_at"]),
        not_before=_parse_utc_instant(item["not_before"]),
        expires_at=_parse_utc_instant(item["expires_at"]),
    )


def _parse_receipt(value: object) -> AuthorizationValidationReceiptV1:
    item = _require_closed(value, _RECEIPT_FIELDS)
    receipt = AuthorizationValidationReceiptV1(
        receipt_version=_require_literal(item["receipt_version"], _RECEIPT_VERSION),
        manifest_scope_identity_sha256=_require_sha256(
            item["manifest_scope_identity_sha256"]
        ),
        trusted_clock_source_identity_sha256=_require_sha256(
            item["trusted_clock_source_identity_sha256"]
        ),
        validation_started_at=_parse_utc_instant(item["validation_started_at"]),
        authorization_validated_at=_parse_utc_instant(
            item["authorization_validated_at"]
        ),
        validation_completed_at=_parse_utc_instant(item["validation_completed_at"]),
        receipt_identity_sha256=_require_sha256(item["receipt_identity_sha256"]),
    )
    if len(receipt.canonical_json_bytes()) > _MAX_RECEIPT_BYTES:
        raise ValueError("authorization validation receipt exceeds bound")
    return receipt


def _authenticated_receipt(
    receipt: AuthorizationValidationReceiptV1 | None,
    manifest: AcquisitionAuthorizationManifestV1,
) -> AuthorizationValidationReceiptV1 | None:
    if receipt is None:
        return None
    try:
        _revalidate_receipt(receipt)
        trusted_clock = _require_sha256(
            acquisition_manifest.TRUSTED_AUTHORIZATION_CLOCK_SOURCE_IDENTITY_SHA256
        )
        projection = _receipt_projection(receipt)
        if (
            receipt.receipt_identity_sha256 != _identity(projection)
            or manifest.authorization_validation_receipt_identity_sha256 is None
            or receipt.receipt_identity_sha256
            != manifest.authorization_validation_receipt_identity_sha256
            or receipt.manifest_scope_identity_sha256
            != manifest.manifest_scope_identity_sha256
            or receipt.trusted_clock_source_identity_sha256 != trusted_clock
        ):
            return None
        return receipt
    except Exception:
        return None


def _authorization_in_force(
    manifest: AcquisitionAuthorizationManifestV1,
    authorization: AcquisitionAuthorizationBindingV1,
    receipt: AuthorizationValidationReceiptV1,
) -> bool:
    capability_assessed_at = manifest.capability_assessed_at
    if capability_assessed_at is None:
        return False
    return (
        authorization.issued_at <= authorization.not_before
        and authorization.not_before
        <= capability_assessed_at
        <= receipt.authorization_validated_at
        and authorization.not_before
        <= manifest.prerequisites_assessed_at
        <= receipt.authorization_validated_at
        and authorization.not_before <= receipt.validation_started_at
        and receipt.validation_started_at
        <= receipt.authorization_validated_at
        <= receipt.validation_completed_at
        and receipt.validation_completed_at < authorization.expires_at
    )


def _blocked(
    blocker: AcquisitionBlockerV1,
    *,
    manifest: AcquisitionAuthorizationManifestV1 | None = None,
    capability_authenticated: bool = False,
    receipt: AuthorizationValidationReceiptV1 | None = None,
) -> AcquisitionDecisionReportV1:
    return _report(
        decision_state=AcquisitionDecisionStateV1.BLOCKED,
        primary_blocker=blocker,
        manifest=manifest,
        capability_authenticated=capability_authenticated,
        receipt=receipt,
    )


def _report(
    *,
    decision_state: AcquisitionDecisionStateV1,
    primary_blocker: AcquisitionBlockerV1 | None,
    manifest: AcquisitionAuthorizationManifestV1 | None,
    capability_authenticated: bool,
    receipt: AuthorizationValidationReceiptV1 | None,
) -> AcquisitionDecisionReportV1:
    projection: dict[str, object] = {
        "contract_version": _CONTRACT_VERSION,
        "decision_state": decision_state.value,
        "primary_blocker": None if primary_blocker is None else primary_blocker.value,
        "sealed_manifest_identity_sha256": (
            None if manifest is None else manifest.manifest_identity_sha256
        ),
        "authenticated_capability_evidence_identity_sha256": (
            manifest.capability_evidence_identity_sha256
            if manifest is not None and capability_authenticated
            else None
        ),
        "authorization_validation_receipt_identity_sha256": (
            None if receipt is None else receipt.receipt_identity_sha256
        ),
        "assessed_at": (
            None
            if receipt is None
            else _format_utc_instant(receipt.validation_completed_at)
        ),
    }
    return AcquisitionDecisionReportV1(
        contract_version=_CONTRACT_VERSION,
        decision_state=decision_state,
        primary_blocker=primary_blocker,
        sealed_manifest_identity_sha256=cast(
            str | None, projection["sealed_manifest_identity_sha256"]
        ),
        authenticated_capability_evidence_identity_sha256=cast(
            str | None,
            projection["authenticated_capability_evidence_identity_sha256"],
        ),
        authorization_validation_receipt_identity_sha256=cast(
            str | None,
            projection["authorization_validation_receipt_identity_sha256"],
        ),
        assessed_at=None if receipt is None else receipt.validation_completed_at,
        report_identity_sha256=_identity(projection),
    )


def _validate_report_nullability(report: AcquisitionDecisionReportV1) -> None:
    sealed = report.sealed_manifest_identity_sha256
    capability = report.authenticated_capability_evidence_identity_sha256
    receipt = report.authorization_validation_receipt_identity_sha256
    assessed = report.assessed_at
    blocker = report.primary_blocker
    if blocker in {
        AcquisitionBlockerV1.SEALED_MANIFEST_MISSING,
        AcquisitionBlockerV1.SEALED_MANIFEST_INVALID,
    }:
        valid = sealed is capability is receipt is assessed is None
    elif blocker is AcquisitionBlockerV1.CAPABILITY_EVIDENCE_MISSING:
        valid = sealed is not None and capability is receipt is assessed is None
    elif blocker in {
        AcquisitionBlockerV1.SOURCE_AND_PIT_EVIDENCE_UNPROVEN,
        AcquisitionBlockerV1.TERMS_AND_USE_UNAPPROVED,
        AcquisitionBlockerV1.OPERATIONAL_SCOPE_UNAPPROVED,
    }:
        valid = (
            sealed is not None
            and capability is not None
            and receipt is assessed is None
        )
    elif blocker is AcquisitionBlockerV1.OWNER_AUTHORIZATION_NOT_IN_FORCE:
        valid = (
            sealed is not None
            and capability is not None
            and (
                (receipt is None and assessed is None)
                or (receipt is not None and assessed is not None)
            )
        )
    else:
        valid = (
            blocker is None
            and sealed is not None
            and capability is not None
            and receipt is not None
            and assessed is not None
        )
    if not valid:
        raise ValueError("invalid acquisition decision report nullability")


def _manifest_value(value: AcquisitionAuthorizationManifestV1) -> dict[str, object]:
    return {
        "manifest_version": value.manifest_version,
        "market_regime_contract_identity_sha256": value.market_regime_contract_identity_sha256,
        "layer_b_protocol_identity_sha256": value.layer_b_protocol_identity_sha256,
        "acquisition_scope_identity_sha256": value.acquisition_scope_identity_sha256,
        "capability_evidence_state": (
            None
            if value.capability_evidence_state is None
            else value.capability_evidence_state.value
        ),
        "capability_evidence_identity_sha256": value.capability_evidence_identity_sha256,
        "capability_assessed_at": (
            None
            if value.capability_assessed_at is None
            else _format_utc_instant(value.capability_assessed_at)
        ),
        "source_and_pit_evidence_bundle_identity_sha256": value.source_and_pit_evidence_bundle_identity_sha256,
        "terms_and_use_approval_identity_sha256": value.terms_and_use_approval_identity_sha256,
        "operational_scope_approval_identity_sha256": value.operational_scope_approval_identity_sha256,
        "prerequisites_assessed_at": _format_utc_instant(
            value.prerequisites_assessed_at
        ),
        "acquisition_authorization": (
            None
            if value.acquisition_authorization is None
            else _authorization_value(value.acquisition_authorization)
        ),
        "manifest_scope_identity_sha256": value.manifest_scope_identity_sha256,
        "authorization_validation_receipt_identity_sha256": value.authorization_validation_receipt_identity_sha256,
        "manifest_identity_sha256": value.manifest_identity_sha256,
    }


def _authorization_value(value: AcquisitionAuthorizationBindingV1) -> dict[str, str]:
    return {
        "authority_role": value.authority_role,
        "authority_identity_sha256": value.authority_identity_sha256,
        "authorization_record_identity_sha256": value.authorization_record_identity_sha256,
        "issued_at": _format_utc_instant(value.issued_at),
        "not_before": _format_utc_instant(value.not_before),
        "expires_at": _format_utc_instant(value.expires_at),
    }


def _receipt_projection(value: AuthorizationValidationReceiptV1) -> dict[str, object]:
    result = _receipt_value(value)
    del result["receipt_identity_sha256"]
    return result


def _receipt_value(value: AuthorizationValidationReceiptV1) -> dict[str, object]:
    return {
        "receipt_version": value.receipt_version,
        "manifest_scope_identity_sha256": value.manifest_scope_identity_sha256,
        "trusted_clock_source_identity_sha256": value.trusted_clock_source_identity_sha256,
        "validation_started_at": _format_utc_instant(value.validation_started_at),
        "authorization_validated_at": _format_utc_instant(
            value.authorization_validated_at
        ),
        "validation_completed_at": _format_utc_instant(value.validation_completed_at),
        "receipt_identity_sha256": value.receipt_identity_sha256,
    }


def _decision_input_value(value: AcquisitionDecisionInputV1) -> dict[str, object]:
    return {
        "contract_version": value.contract_version,
        "capability_evidence": (
            None
            if value.capability_evidence is None
            else {
                "state": value.capability_evidence.state.value,
                "evidence_identity_sha256": value.capability_evidence.evidence_identity_sha256,
            }
        ),
        "authorization_validation_receipt": (
            None
            if value.authorization_validation_receipt is None
            else _receipt_value(value.authorization_validation_receipt)
        ),
    }


def _report_projection(value: AcquisitionDecisionReportV1) -> dict[str, object]:
    result = _report_value(value)
    del result["report_identity_sha256"]
    return result


def _report_value(value: AcquisitionDecisionReportV1) -> dict[str, object]:
    return {
        "contract_version": value.contract_version,
        "decision_state": value.decision_state.value,
        "primary_blocker": None
        if value.primary_blocker is None
        else value.primary_blocker.value,
        "sealed_manifest_identity_sha256": value.sealed_manifest_identity_sha256,
        "authenticated_capability_evidence_identity_sha256": value.authenticated_capability_evidence_identity_sha256,
        "authorization_validation_receipt_identity_sha256": value.authorization_validation_receipt_identity_sha256,
        "assessed_at": None
        if value.assessed_at is None
        else _format_utc_instant(value.assessed_at),
        "report_identity_sha256": value.report_identity_sha256,
    }


def _revalidate_request(value: object) -> None:
    if type(value) is not AcquisitionDecisionInputV1:
        raise ValueError("acquisition decision input required")
    AcquisitionDecisionInputV1.__post_init__(value)


def _revalidate_capability(value: object) -> None:
    if type(value) is not CapabilityEvidenceInputV1:
        raise ValueError("capability evidence input required")
    CapabilityEvidenceInputV1.__post_init__(value)


def _revalidate_receipt(value: object) -> None:
    if type(value) is not AuthorizationValidationReceiptV1:
        raise ValueError("authorization validation receipt required")
    AuthorizationValidationReceiptV1.__post_init__(value)


def _revalidate_authorization(value: object) -> None:
    if type(value) is not AcquisitionAuthorizationBindingV1:
        raise ValueError("acquisition authorization binding required")
    AcquisitionAuthorizationBindingV1.__post_init__(value)


def _canonical(value: object) -> bytes:
    _validate_json_tree(value)
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


def _identity(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _strict_canonical_object(raw: object, *, maximum: int) -> dict[str, object]:
    if type(raw) is not bytes or len(raw) > maximum:
        raise ValueError("invalid bounded canonical JSON")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid JSON") from error
    _validate_json_tree(value)
    if type(value) is not dict:
        raise ValueError("JSON object required")
    result = cast(dict[str, object], value)
    if _canonical(result) != raw:
        raise ValueError("noncanonical JSON")
    return result


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_number(_: str) -> object:
    raise ValueError("invalid JSON number")


def _validate_json_text(value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("invalid Unicode") from error
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("noncanonical Unicode")


def _validate_json_tree(value: object, depth: int = 0) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("JSON depth exceeded")
    if value is None or type(value) in {bool, int}:
        return
    if type(value) is str:
        _validate_json_text(value)
        return
    if type(value) is list:
        for item in cast(list[object], value):
            _validate_json_tree(item, depth + 1)
        return
    if type(value) is dict:
        for key, item in cast(dict[object, object], value).items():
            if type(key) is not str:
                raise ValueError("JSON object key must be text")
            _validate_json_tree(key, depth + 1)
            _validate_json_tree(item, depth + 1)
        return
    raise ValueError("unsupported JSON value")


def _require_closed(value: object, expected: Collection[str]) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError("closed JSON object required")
    result = cast(dict[str, object], value)
    if set(result) != set(expected):
        raise ValueError("closed JSON object fields mismatch")
    return result


def _require_literal(value: object, expected: str) -> str:
    if type(value) is not str or value != expected:
        raise ValueError("invalid literal")
    return value


def _enum(enum_type: type[_EnumT], value: object) -> _EnumT:
    if type(value) is not str:
        raise ValueError("invalid enum")
    try:
        return enum_type(value)
    except ValueError as error:
        raise ValueError("invalid enum") from error


def _require_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError("invalid SHA-256 identity")
    return value


def _require_optional_sha256(value: object) -> None:
    if value is not None:
        _require_sha256(value)


def _validate_capability_group(
    state: object, identity: object, assessed_at: object
) -> datetime | None:
    group = (state, identity, assessed_at)
    if any(item is None for item in group):
        if not all(item is None for item in group):
            raise ValueError("partial sealed capability evidence group")
        return None
    if type(state) is not CapabilityEvidenceStateV1:
        raise ValueError("invalid sealed capability evidence state")
    _require_sha256(identity)
    return _require_utc_datetime(assessed_at)


def _optional_sha256(value: object) -> str | None:
    return None if value is None else _require_sha256(value)


def _parse_utc_instant(value: object) -> datetime:
    if type(value) is not str or _UTC_INSTANT.fullmatch(value) is None:
        raise ValueError("invalid UTC instant")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise ValueError("invalid UTC instant") from error
    if _format_utc_instant(parsed) != value:
        raise ValueError("noncanonical UTC instant")
    return parsed


def _require_utc_datetime(value: object) -> datetime:
    if type(value) is not datetime:
        raise ValueError("UTC datetime required")
    item = value
    try:
        offset = item.utcoffset()
    except Exception as error:
        raise ValueError("invalid UTC datetime") from error
    if offset != timedelta(0):
        raise ValueError("UTC datetime required")
    return item.astimezone(UTC)


def _format_utc_instant(value: datetime) -> str:
    item = _require_utc_datetime(value)
    return (
        f"{item.year:04d}-{item.month:02d}-{item.day:02d}T"
        f"{item.hour:02d}:{item.minute:02d}:{item.second:02d}."
        f"{item.microsecond:06d}Z"
    )
