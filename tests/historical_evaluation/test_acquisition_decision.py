from __future__ import annotations

import ast
import hashlib
import json
import sys
import tomllib
from dataclasses import fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from swing_trading_ai_assistant.historical_evaluation import (
    acquisition_decision,
    acquisition_decision_cli,
    acquisition_manifest,
)
from swing_trading_ai_assistant.historical_evaluation.acquisition_decision_cli import (
    main,
)
from swing_trading_ai_assistant.market_regime import reducer as market_regime_reducer
from swing_trading_ai_assistant.sector_analysis import participation as sector_reducer

CONTRACT_VERSION = "market-regime-layer-b-acquisition-decision@v1"
MANIFEST_VERSION = "market-regime-layer-b-acquisition-manifest@v1"
RECEIPT_VERSION = "market-regime-layer-b-authorization-validation@v1"
TRUSTED_CLOCK_IDENTITY = "1" * 64
CAPABILITY_IDENTITY = "2" * 64
SOURCE_IDENTITY = "3" * 64
TERMS_IDENTITY = "4" * 64
OPERATIONAL_IDENTITY = "5" * 64
AUTHORITY_IDENTITY = "6" * 64
AUTHORIZATION_RECORD_IDENTITY = "7" * 64
GOLDEN_REPORTS: dict[str, tuple[bytes, str]] = {
    "SEALED_MANIFEST_MISSING": (
        b'{"assessed_at":null,"authenticated_capability_evidence_identity_sha256":null,"authorization_validation_receipt_identity_sha256":null,"contract_version":"market-regime-layer-b-acquisition-decision@v1","decision_state":"BLOCKED","primary_blocker":"SEALED_MANIFEST_MISSING","report_identity_sha256":"456d3e08b337220cf20fbd8be3f50ee7d764b80a88a7c0182b5a4ec6afcfc4ff","sealed_manifest_identity_sha256":null}\n',
        "456d3e08b337220cf20fbd8be3f50ee7d764b80a88a7c0182b5a4ec6afcfc4ff",
    ),
    "SEALED_MANIFEST_INVALID": (
        b'{"assessed_at":null,"authenticated_capability_evidence_identity_sha256":null,"authorization_validation_receipt_identity_sha256":null,"contract_version":"market-regime-layer-b-acquisition-decision@v1","decision_state":"BLOCKED","primary_blocker":"SEALED_MANIFEST_INVALID","report_identity_sha256":"5149c25f4279ae5f9ace3fba0d40253a65910b59dcb16f6abfc616691a46f2d4","sealed_manifest_identity_sha256":null}\n',
        "5149c25f4279ae5f9ace3fba0d40253a65910b59dcb16f6abfc616691a46f2d4",
    ),
    "CAPABILITY_EVIDENCE_MISSING": (
        b'{"assessed_at":null,"authenticated_capability_evidence_identity_sha256":null,"authorization_validation_receipt_identity_sha256":null,"contract_version":"market-regime-layer-b-acquisition-decision@v1","decision_state":"BLOCKED","primary_blocker":"CAPABILITY_EVIDENCE_MISSING","report_identity_sha256":"9fb3b0b63a2270ecde1dcb527f0a6684359ceedf0a94f5ccd3ce69028a84a46b","sealed_manifest_identity_sha256":"077d7df50d78d0ae4775f6280487c848769e8c1bd99d953ef4bc5811c0e3d640"}\n',
        "9fb3b0b63a2270ecde1dcb527f0a6684359ceedf0a94f5ccd3ce69028a84a46b",
    ),
    "SOURCE_AND_PIT_EVIDENCE_UNPROVEN": (
        b'{"assessed_at":null,"authenticated_capability_evidence_identity_sha256":"2222222222222222222222222222222222222222222222222222222222222222","authorization_validation_receipt_identity_sha256":null,"contract_version":"market-regime-layer-b-acquisition-decision@v1","decision_state":"BLOCKED","primary_blocker":"SOURCE_AND_PIT_EVIDENCE_UNPROVEN","report_identity_sha256":"43ce8ba01ecec269b69ca68d4c1da00d951b6f40ef472b958f1ab9868715b8c8","sealed_manifest_identity_sha256":"221df79b32b655094ee64920e47447df868f33fc280f8ffb8314a379a73167b9"}\n',
        "43ce8ba01ecec269b69ca68d4c1da00d951b6f40ef472b958f1ab9868715b8c8",
    ),
    "TERMS_AND_USE_UNAPPROVED": (
        b'{"assessed_at":null,"authenticated_capability_evidence_identity_sha256":"2222222222222222222222222222222222222222222222222222222222222222","authorization_validation_receipt_identity_sha256":null,"contract_version":"market-regime-layer-b-acquisition-decision@v1","decision_state":"BLOCKED","primary_blocker":"TERMS_AND_USE_UNAPPROVED","report_identity_sha256":"c8a6186ada297cc3be21d320cb453d9e74672b6b1108066b6436505d6aacc794","sealed_manifest_identity_sha256":"30b7a9bdb7a0c9dd7152f969eba39668f33b5862290ee1a3f172d700d621c89f"}\n',
        "c8a6186ada297cc3be21d320cb453d9e74672b6b1108066b6436505d6aacc794",
    ),
    "OPERATIONAL_SCOPE_UNAPPROVED": (
        b'{"assessed_at":null,"authenticated_capability_evidence_identity_sha256":"2222222222222222222222222222222222222222222222222222222222222222","authorization_validation_receipt_identity_sha256":null,"contract_version":"market-regime-layer-b-acquisition-decision@v1","decision_state":"BLOCKED","primary_blocker":"OPERATIONAL_SCOPE_UNAPPROVED","report_identity_sha256":"e56ca9ee346fb38d577f4e48f4c4a764e87fbc48cd09fbe53f52d7749bf79e28","sealed_manifest_identity_sha256":"5ca5ffd47c7b15b68cb1f98603a9a34a6948687d3b37bf4caf8a92fa87a6feeb"}\n',
        "e56ca9ee346fb38d577f4e48f4c4a764e87fbc48cd09fbe53f52d7749bf79e28",
    ),
    "OWNER_AUTHORIZATION_NOT_IN_FORCE": (
        b'{"assessed_at":"2026-08-15T06:00:00.000000Z","authenticated_capability_evidence_identity_sha256":"2222222222222222222222222222222222222222222222222222222222222222","authorization_validation_receipt_identity_sha256":"c4bfbe1f6b4c0664d4936e34338565904b035e8febd2afcc27326b4fa309879b","contract_version":"market-regime-layer-b-acquisition-decision@v1","decision_state":"BLOCKED","primary_blocker":"OWNER_AUTHORIZATION_NOT_IN_FORCE","report_identity_sha256":"44945d648e2d0a0a19bf8335bd3dcaadbe07692d3648e4b4afccff76631a41b9","sealed_manifest_identity_sha256":"4546c7d5e79dd78af15286699672733f203242a95ac533a555e72c60b7146307"}\n',
        "44945d648e2d0a0a19bf8335bd3dcaadbe07692d3648e4b4afccff76631a41b9",
    ),
    "APPROVED_TO_ACQUIRE": (
        b'{"assessed_at":"2026-08-15T06:00:00.000000Z","authenticated_capability_evidence_identity_sha256":"2222222222222222222222222222222222222222222222222222222222222222","authorization_validation_receipt_identity_sha256":"4106c7bea9ee70dda8bd66e4857737a8af6bac3cca8ae2c6a7c0e7a869795f71","contract_version":"market-regime-layer-b-acquisition-decision@v1","decision_state":"APPROVED_TO_ACQUIRE","primary_blocker":null,"report_identity_sha256":"7df55031fa1c60fa7624e33ddc7bb76e8fc678f3881609350d0e1f02a6a1304e","sealed_manifest_identity_sha256":"077d7df50d78d0ae4775f6280487c848769e8c1bd99d953ef4bc5811c0e3d640"}\n',
        "7df55031fa1c60fa7624e33ddc7bb76e8fc678f3881609350d0e1f02a6a1304e",
    ),
}

SCOPE_FIELDS = (
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


def _identity(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _instant(hour: int) -> str:
    return f"2026-08-15T{hour:02d}:00:00.000000Z"


def _datetime(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


def _base_manifest() -> dict[str, Any]:
    return {
        "manifest_version": MANIFEST_VERSION,
        "market_regime_contract_identity_sha256": "8" * 64,
        "layer_b_protocol_identity_sha256": "9" * 64,
        "acquisition_scope_identity_sha256": "a" * 64,
        "capability_evidence_state": "OBSERVED",
        "capability_evidence_identity_sha256": CAPABILITY_IDENTITY,
        "capability_assessed_at": _instant(2),
        "source_and_pit_evidence_bundle_identity_sha256": SOURCE_IDENTITY,
        "terms_and_use_approval_identity_sha256": TERMS_IDENTITY,
        "operational_scope_approval_identity_sha256": OPERATIONAL_IDENTITY,
        "prerequisites_assessed_at": _instant(3),
        "acquisition_authorization": {
            "authority_role": "FULL_ACQUISITION_AUTHORITY",
            "authority_identity_sha256": AUTHORITY_IDENTITY,
            "authorization_record_identity_sha256": AUTHORIZATION_RECORD_IDENTITY,
            "issued_at": _instant(0),
            "not_before": _instant(1),
            "expires_at": _instant(7),
        },
    }


def _build_sealed_values(
    *,
    manifest_updates: dict[str, object] | None = None,
    authorization_updates: dict[str, object] | None = None,
    receipt_updates: dict[str, object] | None = None,
    include_receipt: bool = True,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    manifest = _base_manifest()
    manifest.update(manifest_updates or {})
    authorization = manifest.get("acquisition_authorization")
    if authorization_updates:
        assert isinstance(authorization, dict)
        authorization = {**authorization, **authorization_updates}
        manifest["acquisition_authorization"] = authorization

    scope_projection = {field: manifest[field] for field in SCOPE_FIELDS}
    manifest["manifest_scope_identity_sha256"] = _identity(scope_projection)

    receipt: dict[str, Any] | None = None
    if include_receipt:
        receipt = {
            "receipt_version": RECEIPT_VERSION,
            "manifest_scope_identity_sha256": manifest[
                "manifest_scope_identity_sha256"
            ],
            "trusted_clock_source_identity_sha256": TRUSTED_CLOCK_IDENTITY,
            "validation_started_at": _instant(4),
            "authorization_validated_at": _instant(5),
            "validation_completed_at": _instant(6),
        }
        receipt.update(receipt_updates or {})
        receipt["receipt_identity_sha256"] = _identity(receipt)
        manifest["authorization_validation_receipt_identity_sha256"] = receipt[
            "receipt_identity_sha256"
        ]
    else:
        manifest["authorization_validation_receipt_identity_sha256"] = None

    manifest["manifest_identity_sha256"] = _identity(manifest)
    return manifest, receipt


def _pin_manifest(
    monkeypatch: pytest.MonkeyPatch,
    manifest: dict[str, Any] | None,
    *,
    canonical_bytes: bytes | None = None,
    companion_identity: str | None = None,
) -> None:
    raw = None if manifest is None else canonical_bytes or _canonical(manifest)
    identity = (
        None
        if manifest is None
        else companion_identity or str(manifest["manifest_identity_sha256"])
    )
    monkeypatch.setattr(
        acquisition_manifest, "SEALED_ACQUISITION_MANIFEST_CANONICAL_JSON_LF", raw
    )
    monkeypatch.setattr(
        acquisition_manifest, "SEALED_ACQUISITION_MANIFEST_IDENTITY_SHA256", identity
    )
    monkeypatch.setattr(
        acquisition_manifest,
        "TRUSTED_AUTHORIZATION_CLOCK_SOURCE_IDENTITY_SHA256",
        TRUSTED_CLOCK_IDENTITY,
    )


def _receipt_object(value: dict[str, Any]) -> object:
    return acquisition_decision.AuthorizationValidationReceiptV1(
        receipt_version=value["receipt_version"],
        manifest_scope_identity_sha256=value["manifest_scope_identity_sha256"],
        trusted_clock_source_identity_sha256=value[
            "trusted_clock_source_identity_sha256"
        ],
        validation_started_at=_datetime(value["validation_started_at"]),
        authorization_validated_at=_datetime(value["authorization_validated_at"]),
        validation_completed_at=_datetime(value["validation_completed_at"]),
        receipt_identity_sha256=value["receipt_identity_sha256"],
    )


def _request(
    receipt: dict[str, Any] | None,
    *,
    capability_state: str = "OBSERVED",
    capability_identity: str = CAPABILITY_IDENTITY,
) -> object:
    capability = acquisition_decision.CapabilityEvidenceInputV1(
        state=acquisition_decision.CapabilityEvidenceStateV1(capability_state),
        evidence_identity_sha256=capability_identity,
    )
    return acquisition_decision.AcquisitionDecisionInputV1(
        contract_version=CONTRACT_VERSION,
        capability_evidence=capability,
        authorization_validation_receipt=(
            None if receipt is None else _receipt_object(receipt)
        ),
    )


def _request_value(receipt: dict[str, Any] | None) -> dict[str, object]:
    return {
        "authorization_validation_receipt": receipt,
        "capability_evidence": {
            "evidence_identity_sha256": CAPABILITY_IDENTITY,
            "state": "OBSERVED",
        },
        "contract_version": CONTRACT_VERSION,
    }


def _assert_literal_golden_report(report: object, outcome: str) -> dict[str, object]:
    expected_bytes, expected_identity = GOLDEN_REPORTS[outcome]
    assert report.canonical_json_bytes() == expected_bytes
    assert report.report_identity_sha256 == expected_identity
    value = json.loads(expected_bytes)
    assert value["report_identity_sha256"] == expected_identity
    assert len(expected_bytes) <= 8 * 1024
    return value


def test_blocker_taxonomy_is_closed_typed_and_declaration_ordered() -> None:
    assert tuple(item.value for item in acquisition_decision.AcquisitionBlockerV1) == (
        "SEALED_MANIFEST_MISSING",
        "SEALED_MANIFEST_INVALID",
        "CAPABILITY_EVIDENCE_MISSING",
        "SOURCE_AND_PIT_EVIDENCE_UNPROVEN",
        "TERMS_AND_USE_UNAPPROVED",
        "OPERATIONAL_SCOPE_UNAPPROVED",
        "OWNER_AUTHORIZATION_NOT_IN_FORCE",
    )
    assert tuple(
        item.value for item in acquisition_decision.AcquisitionDecisionStateV1
    ) == ("APPROVED_TO_ACQUIRE", "BLOCKED")


def test_missing_seal_is_byte_stable_and_caller_inputs_cannot_replace_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, receipt = _build_sealed_values()
    assert receipt is not None
    _pin_manifest(monkeypatch, None)

    first = acquisition_decision.decide_acquisition_v1(_request(receipt))
    altered = acquisition_decision.decide_acquisition_v1(
        _request(
            {**receipt, "receipt_identity_sha256": "f" * 64},
            capability_identity="e" * 64,
        )
    )

    assert first == altered
    assert (
        first.decision_state is acquisition_decision.AcquisitionDecisionStateV1.BLOCKED
    )
    assert (
        first.primary_blocker
        is acquisition_decision.AcquisitionBlockerV1.SEALED_MANIFEST_MISSING
    )
    assert first.sealed_manifest_identity_sha256 is None
    assert first.authenticated_capability_evidence_identity_sha256 is None
    assert first.authorization_validation_receipt_identity_sha256 is None
    assert first.assessed_at is None
    assert first.canonical_json_bytes() == altered.canonical_json_bytes()
    _assert_literal_golden_report(first, "SEALED_MANIFEST_MISSING")


@pytest.mark.parametrize(
    "corruption",
    ("noncanonical", "oversize", "scope", "final_pin", "inline_binding"),
)
def test_every_seal_authentication_failure_is_manifest_invalid(
    monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    manifest, receipt = _build_sealed_values()
    assert receipt is not None
    raw = _canonical(manifest)
    companion = str(manifest["manifest_identity_sha256"])
    if corruption == "noncanonical":
        raw = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    elif corruption == "oversize":
        raw = _canonical(manifest) + b" " * (16 * 1024)
    elif corruption == "scope":
        manifest["capability_assessed_at"] = _instant(3)
        raw = _canonical(manifest)
    elif corruption == "final_pin":
        companion = "f" * 64
    else:
        manifest, receipt = _build_sealed_values(
            authorization_updates={"authority_role": "NOT_AN_AUTHORITY"}
        )
        assert receipt is not None
        raw = _canonical(manifest)
        companion = str(manifest["manifest_identity_sha256"])
    _pin_manifest(
        monkeypatch,
        manifest,
        canonical_bytes=raw,
        companion_identity=companion,
    )

    report = acquisition_decision.decide_acquisition_v1(_request(receipt))

    assert (
        report.primary_blocker
        is acquisition_decision.AcquisitionBlockerV1.SEALED_MANIFEST_INVALID
    )
    assert report.sealed_manifest_identity_sha256 is None
    assert report.authenticated_capability_evidence_identity_sha256 is None
    assert report.authorization_validation_receipt_identity_sha256 is None
    assert report.assessed_at is None
    _assert_literal_golden_report(report, "SEALED_MANIFEST_INVALID")


@pytest.mark.parametrize(
    ("manifest_updates", "capability", "expected"),
    (
        ({}, None, "CAPABILITY_EVIDENCE_MISSING"),
        (
            {
                "source_and_pit_evidence_bundle_identity_sha256": None,
                "terms_and_use_approval_identity_sha256": None,
                "operational_scope_approval_identity_sha256": None,
                "acquisition_authorization": None,
            },
            "matching",
            "SOURCE_AND_PIT_EVIDENCE_UNPROVEN",
        ),
        (
            {
                "terms_and_use_approval_identity_sha256": None,
                "operational_scope_approval_identity_sha256": None,
                "acquisition_authorization": None,
            },
            "matching",
            "TERMS_AND_USE_UNAPPROVED",
        ),
        (
            {
                "operational_scope_approval_identity_sha256": None,
                "acquisition_authorization": None,
            },
            "matching",
            "OPERATIONAL_SCOPE_UNAPPROVED",
        ),
        (
            {"acquisition_authorization": None},
            "matching",
            "OWNER_AUTHORIZATION_NOT_IN_FORCE",
        ),
        ({}, "matching", None),
    ),
)
def test_prerequisite_rows_stop_at_first_blocker_and_approved_row_is_exact(
    monkeypatch: pytest.MonkeyPatch,
    manifest_updates: dict[str, object],
    capability: str | None,
    expected: str | None,
) -> None:
    manifest, receipt = _build_sealed_values(manifest_updates=manifest_updates)
    assert receipt is not None
    _pin_manifest(monkeypatch, manifest)
    request = _request(receipt)
    if capability is None:
        request = replace(request, capability_evidence=None)

    report = acquisition_decision.decide_acquisition_v1(request)
    value = _assert_literal_golden_report(
        report,
        "APPROVED_TO_ACQUIRE" if expected is None else expected,
    )

    expected_state = "APPROVED_TO_ACQUIRE" if expected is None else "BLOCKED"
    assert report.decision_state.value == expected_state
    assert report.primary_blocker is (
        None
        if expected is None
        else acquisition_decision.AcquisitionBlockerV1(expected)
    )
    assert (
        report.sealed_manifest_identity_sha256 == manifest["manifest_identity_sha256"]
    )
    if expected == "CAPABILITY_EVIDENCE_MISSING":
        assert report.authenticated_capability_evidence_identity_sha256 is None
    else:
        assert (
            report.authenticated_capability_evidence_identity_sha256
            == CAPABILITY_IDENTITY
        )
    if expected in {
        "CAPABILITY_EVIDENCE_MISSING",
        "SOURCE_AND_PIT_EVIDENCE_UNPROVEN",
        "TERMS_AND_USE_UNAPPROVED",
        "OPERATIONAL_SCOPE_UNAPPROVED",
    }:
        assert report.authorization_validation_receipt_identity_sha256 is None
        assert report.assessed_at is None
    else:
        assert (
            report.authorization_validation_receipt_identity_sha256
            == receipt["receipt_identity_sha256"]
        )
        assert report.assessed_at == _datetime(receipt["validation_completed_at"])
    assert "additional_blockers" not in value


def test_capability_must_match_both_sealed_state_and_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, receipt = _build_sealed_values()
    assert receipt is not None
    _pin_manifest(monkeypatch, manifest)

    for request in (
        _request(receipt, capability_state="NOT_OBSERVED"),
        _request(receipt, capability_identity="f" * 64),
    ):
        report = acquisition_decision.decide_acquisition_v1(request)
        assert (
            report.primary_blocker
            is acquisition_decision.AcquisitionBlockerV1.CAPABILITY_EVIDENCE_MISSING
        )
        assert report.authenticated_capability_evidence_identity_sha256 is None
        assert report.authorization_validation_receipt_identity_sha256 is None
        assert report.assessed_at is None
    not_observed_manifest, not_observed_receipt = _build_sealed_values(
        manifest_updates={"capability_evidence_state": "NOT_OBSERVED"}
    )
    assert not_observed_receipt is not None
    _pin_manifest(monkeypatch, not_observed_manifest)
    matching_not_observed = acquisition_decision.decide_acquisition_v1(
        _request(not_observed_receipt, capability_state="NOT_OBSERVED")
    )
    assert matching_not_observed.primary_blocker is (
        acquisition_decision.AcquisitionBlockerV1.CAPABILITY_EVIDENCE_MISSING
    )


def test_scope_receipt_and_final_manifest_identities_form_a_finite_sequence() -> None:
    original, original_receipt = _build_sealed_values()
    scope_changed, scope_changed_receipt = _build_sealed_values(
        manifest_updates={"prerequisites_assessed_at": _instant(4)}
    )
    receipt_changed, changed_receipt = _build_sealed_values(
        receipt_updates={"validation_completed_at": "2026-08-15T06:30:00.000000Z"}
    )
    assert original_receipt and scope_changed_receipt and changed_receipt

    assert (
        original["manifest_scope_identity_sha256"]
        != scope_changed["manifest_scope_identity_sha256"]
    )
    assert (
        original_receipt["receipt_identity_sha256"]
        != scope_changed_receipt["receipt_identity_sha256"]
    )
    assert (
        original["manifest_identity_sha256"]
        != scope_changed["manifest_identity_sha256"]
    )

    assert (
        original["manifest_scope_identity_sha256"]
        == receipt_changed["manifest_scope_identity_sha256"]
    )
    assert (
        original_receipt["receipt_identity_sha256"]
        != changed_receipt["receipt_identity_sha256"]
    )
    assert (
        original["manifest_identity_sha256"]
        != receipt_changed["manifest_identity_sha256"]
    )

    scope_projection = {field: original[field] for field in SCOPE_FIELDS}
    assert original["manifest_scope_identity_sha256"] == _identity(scope_projection)
    receipt_projection = {
        key: value
        for key, value in original_receipt.items()
        if key != "receipt_identity_sha256"
    }
    assert original_receipt["receipt_identity_sha256"] == _identity(receipt_projection)
    final_projection = {
        key: value
        for key, value in original.items()
        if key != "manifest_identity_sha256"
    }
    assert original["manifest_identity_sha256"] == _identity(final_projection)
    assert len(_canonical(original)) <= 16 * 1024
    assert len(_canonical(original_receipt)) <= 4 * 1024


@pytest.mark.parametrize(
    ("authorization_updates", "manifest_updates", "receipt_updates", "approved"),
    (
        ({"issued_at": _instant(1)}, {}, {}, True),
        ({"issued_at": _instant(2)}, {}, {}, False),
        ({}, {"capability_assessed_at": _instant(1)}, {}, True),
        ({}, {"capability_assessed_at": _instant(5)}, {}, True),
        ({}, {"capability_assessed_at": _instant(0)}, {}, False),
        ({}, {"capability_assessed_at": _instant(6)}, {}, False),
        ({}, {"prerequisites_assessed_at": _instant(1)}, {}, True),
        ({}, {"prerequisites_assessed_at": _instant(5)}, {}, True),
        ({}, {"prerequisites_assessed_at": _instant(0)}, {}, False),
        ({}, {"prerequisites_assessed_at": _instant(6)}, {}, False),
        ({}, {}, {"validation_started_at": _instant(1)}, True),
        ({}, {}, {"validation_started_at": _instant(0)}, False),
        (
            {},
            {},
            {
                "validation_started_at": _instant(5),
                "authorization_validated_at": _instant(5),
            },
            True,
        ),
        (
            {},
            {},
            {
                "validation_started_at": _instant(6),
                "authorization_validated_at": _instant(5),
            },
            False,
        ),
        (
            {},
            {},
            {
                "authorization_validated_at": _instant(6),
                "validation_completed_at": _instant(6),
            },
            True,
        ),
        (
            {},
            {},
            {
                "authorization_validated_at": _instant(6),
                "validation_completed_at": _instant(5),
            },
            False,
        ),
        ({"expires_at": _instant(6)}, {}, {}, False),
        ({"expires_at": _instant(5)}, {}, {}, False),
    ),
)
def test_every_validation_time_equation_is_inclusive_or_exclusive_exactly(
    monkeypatch: pytest.MonkeyPatch,
    authorization_updates: dict[str, object],
    manifest_updates: dict[str, object],
    receipt_updates: dict[str, object],
    approved: bool,
) -> None:
    manifest, receipt = _build_sealed_values(
        authorization_updates=authorization_updates,
        manifest_updates=manifest_updates,
        receipt_updates=receipt_updates,
    )
    assert receipt is not None
    _pin_manifest(monkeypatch, manifest)

    report = acquisition_decision.decide_acquisition_v1(_request(receipt))

    assert report.primary_blocker is (
        None
        if approved
        else acquisition_decision.AcquisitionBlockerV1.OWNER_AUTHORIZATION_NOT_IN_FORCE
    )
    assert (
        report.authorization_validation_receipt_identity_sha256
        == receipt["receipt_identity_sha256"]
    )
    assert report.assessed_at == _datetime(receipt["validation_completed_at"])


def test_unauthenticated_receipt_contributes_no_identity_or_time_but_authenticated_out_of_force_receipt_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_receipt_manifest, _ = _build_sealed_values(include_receipt=False)
    _pin_manifest(monkeypatch, missing_receipt_manifest)
    missing = acquisition_decision.decide_acquisition_v1(_request(None))
    assert missing.primary_blocker is (
        acquisition_decision.AcquisitionBlockerV1.OWNER_AUTHORIZATION_NOT_IN_FORCE
    )
    assert missing.authorization_validation_receipt_identity_sha256 is None
    assert missing.assessed_at is None

    manifest, receipt = _build_sealed_values()
    assert receipt is not None
    _pin_manifest(monkeypatch, manifest)
    forged = {**receipt, "receipt_identity_sha256": "f" * 64}

    unauthenticated = acquisition_decision.decide_acquisition_v1(_request(forged))

    assert (
        unauthenticated.primary_blocker
        is acquisition_decision.AcquisitionBlockerV1.OWNER_AUTHORIZATION_NOT_IN_FORCE
    )
    assert unauthenticated.authorization_validation_receipt_identity_sha256 is None
    assert unauthenticated.assessed_at is None

    expired_manifest, expired_receipt = _build_sealed_values(
        authorization_updates={"expires_at": _instant(6)}
    )
    assert expired_receipt is not None
    _pin_manifest(monkeypatch, expired_manifest)
    authenticated = acquisition_decision.decide_acquisition_v1(
        _request(expired_receipt)
    )
    assert (
        authenticated.primary_blocker
        is acquisition_decision.AcquisitionBlockerV1.OWNER_AUTHORIZATION_NOT_IN_FORCE
    )
    assert (
        authenticated.authorization_validation_receipt_identity_sha256
        == expired_receipt["receipt_identity_sha256"]
    )
    assert authenticated.assessed_at == _datetime(
        expired_receipt["validation_completed_at"]
    )


@pytest.mark.parametrize(
    "mismatch",
    ("final_manifest_receipt_pin", "manifest_scope", "trusted_clock"),
)
def test_each_valid_self_hash_receipt_binding_mismatch_is_independently_unauthenticated(
    monkeypatch: pytest.MonkeyPatch,
    mismatch: str,
) -> None:
    manifest, receipt = _build_sealed_values()
    assert receipt is not None
    candidate = {
        key: value for key, value in receipt.items() if key != "receipt_identity_sha256"
    }
    if mismatch == "final_manifest_receipt_pin":
        candidate["validation_started_at"] = _instant(3)
    elif mismatch == "manifest_scope":
        candidate["manifest_scope_identity_sha256"] = "f" * 64
    else:
        candidate["trusted_clock_source_identity_sha256"] = "e" * 64
    candidate["receipt_identity_sha256"] = _identity(candidate)
    assert candidate["receipt_identity_sha256"] == _identity(
        {
            key: value
            for key, value in candidate.items()
            if key != "receipt_identity_sha256"
        }
    )

    if mismatch != "final_manifest_receipt_pin":
        manifest["authorization_validation_receipt_identity_sha256"] = candidate[
            "receipt_identity_sha256"
        ]
        del manifest["manifest_identity_sha256"]
        manifest["manifest_identity_sha256"] = _identity(manifest)
    _pin_manifest(monkeypatch, manifest)

    report = acquisition_decision.decide_acquisition_v1(_request(candidate))

    assert report.primary_blocker is (
        acquisition_decision.AcquisitionBlockerV1.OWNER_AUTHORIZATION_NOT_IN_FORCE
    )
    assert report.authorization_validation_receipt_identity_sha256 is None
    assert report.assessed_at is None


def test_domain_objects_and_report_are_provider_independent_and_have_no_market_regime_output() -> (
    None
):
    assert tuple(
        field.name for field in fields(acquisition_decision.CapabilityEvidenceInputV1)
    ) == (
        "state",
        "evidence_identity_sha256",
    )
    assert tuple(
        field.name for field in fields(acquisition_decision.AcquisitionDecisionInputV1)
    ) == (
        "contract_version",
        "capability_evidence",
        "authorization_validation_receipt",
    )
    assert tuple(
        field.name for field in fields(acquisition_decision.AcquisitionDecisionReportV1)
    ) == (
        "contract_version",
        "decision_state",
        "primary_blocker",
        "sealed_manifest_identity_sha256",
        "authenticated_capability_evidence_identity_sha256",
        "authorization_validation_receipt_identity_sha256",
        "assessed_at",
        "report_identity_sha256",
    )
    forbidden = {
        "provider",
        "url",
        "method",
        "status",
        "header",
        "body",
        "pdf",
        "label",
        "labels",
        "label_count",
        "count",
        "direction",
        "transition",
        "return",
        "performance",
        "prediction",
        "recommendation",
    }
    assert forbidden.isdisjoint(
        field.name for field in fields(acquisition_decision.AcquisitionDecisionReportV1)
    )


def test_reducer_touches_no_provider_side_effect_or_market_or_sector_reducer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, receipt = _build_sealed_values()
    assert receipt is not None
    _pin_manifest(monkeypatch, manifest)
    touched: list[str] = []

    def fail(name: str):
        def sentinel(*_args: object, **_kwargs: object) -> object:
            touched.append(name)
            raise AssertionError(name)

        return sentinel

    monkeypatch.setattr(
        market_regime_reducer,
        "reduce_attempts_to_insufficiency_v1",
        fail("market_regime"),
    )
    monkeypatch.setattr(
        sector_reducer,
        "reduce_sector_participation_v1",
        fail("sector"),
    )
    monkeypatch.setattr("builtins.open", fail("filesystem"))
    monkeypatch.setattr("socket.socket", fail("network"))
    monkeypatch.setattr("os.getenv", fail("environment"))
    monkeypatch.setattr("random.random", fail("random"))
    monkeypatch.setattr("time.time", fail("clock"))
    monkeypatch.setattr("time.monotonic", fail("clock"))

    report = acquisition_decision.decide_acquisition_v1(_request(receipt))

    assert (
        report.decision_state
        is acquisition_decision.AcquisitionDecisionStateV1.APPROVED_TO_ACQUIRE
    )
    assert touched == []


def test_decision_modules_have_no_market_sector_provider_or_side_effect_dependencies() -> (
    None
):
    package = Path(__file__).parents[2] / "src/swing_trading_ai_assistant"
    paths = (
        package / "historical_evaluation/acquisition_manifest.py",
        package / "historical_evaluation/acquisition_decision.py",
    )
    forbidden_imports = (
        "swing_trading_ai_assistant.market_data",
        "swing_trading_ai_assistant.market_regime",
        "swing_trading_ai_assistant.sector_analysis",
        "socket",
        "random",
        "urllib",
        "requests",
        "httpx",
    )
    forbidden_calls = {
        "getenv",
        "monotonic",
        "now",
        "open",
        "time",
        "utcnow",
        "urlopen",
    }
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = []
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)
        assert not any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for imported in imports
            for forbidden in forbidden_imports
        )
        assert forbidden_calls.isdisjoint(calls)


class _SingleBoundedRead:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.position = 0
        self.calls: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.calls.append(size)
        if len(self.calls) != 1 or size != 16 * 1024 + 1:
            raise AssertionError("stdin must receive exactly one 16 KiB-plus-one read")
        result = self.payload[:size]
        self.position += len(result)
        return result


class _BinaryStdin:
    def __init__(self, payload: bytes) -> None:
        self.buffer = _SingleBoundedRead(payload)

    def read(self, *_args: object, **_kwargs: object) -> str:
        raise AssertionError("CLI must read bounded bytes from stdin.buffer")


def test_cli_emits_only_one_canonical_blocked_or_approved_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest, receipt = _build_sealed_values()
    assert receipt is not None
    raw_request = _canonical(_request_value(receipt))

    _pin_manifest(monkeypatch, None)
    blocked_stdin = _BinaryStdin(raw_request)
    monkeypatch.setattr(sys, "stdin", blocked_stdin)
    assert main(["decide"]) == 1
    blocked_output = capsys.readouterr()
    assert blocked_output.err == ""
    blocked_value = json.loads(blocked_output.out)
    assert blocked_value["decision_state"] == "BLOCKED"
    assert blocked_value["primary_blocker"] == "SEALED_MANIFEST_MISSING"
    assert blocked_output.out.encode() == _canonical(blocked_value)
    assert blocked_stdin.buffer.calls == [16 * 1024 + 1]

    _pin_manifest(monkeypatch, manifest)
    approved_stdin = _BinaryStdin(raw_request)
    monkeypatch.setattr(sys, "stdin", approved_stdin)
    assert main(["decide"]) == 0
    approved_output = capsys.readouterr()
    assert approved_output.err == ""
    approved_value = json.loads(approved_output.out)
    assert approved_value["decision_state"] == "APPROVED_TO_ACQUIRE"
    assert approved_value["primary_blocker"] is None
    assert approved_output.out.encode() == _canonical(approved_value)
    assert approved_stdin.buffer.calls == [16 * 1024 + 1]


def test_cli_reads_exactly_16_kib_plus_one_and_never_consumes_or_parses_beyond_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret_tail = b"must-not-be-consumed-or-echoed"
    payload = b"x" * (16 * 1024 + 1) + secret_tail
    stdin = _BinaryStdin(payload)
    monkeypatch.setattr(sys, "stdin", stdin)

    assert main(["decide"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "request_invalid\n"
    assert stdin.buffer.calls == [16 * 1024 + 1]
    assert stdin.buffer.position == 16 * 1024 + 1
    assert payload[stdin.buffer.position :] == secret_tail
    assert "must-not" not in captured.err


@pytest.mark.parametrize(
    ("argv", "payload"),
    (
        ([], b"{}\n"),
        (["probe"], b"{}\n"),
        (["decide", "--manifest", "secret-path"], b"{}\n"),
        (["decide", "extra"], b"{}\n"),
        (["decide"], b"\xef\xbb\xbf{}\n"),
        (["decide"], b'{"contract_version":1.5}\n'),
        (
            ["decide"],
            b'{"unknown":{"a":{"b":{"c":{"d":{"e":{"f":{"g":{"h":0}}}}}}}}}\n',
        ),
        (["decide"], b'{"unknown":"\\ud800"}\n'),
        (["decide"], b'{"contract_version":"wrong"}\n'),
        (["decide"], b'{"contract_version":"wrong","contract_version":"wrong"}\n'),
        (["decide"], b"x" * (16 * 1024)),
    ),
)
def test_cli_rejects_commands_flags_extra_and_structural_input_with_fixed_redaction(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    payload: bytes,
) -> None:
    stdin = _BinaryStdin(payload)
    monkeypatch.setattr(sys, "stdin", stdin)

    assert main(argv) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "request_invalid\n"
    assert "secret" not in captured.err


def test_cli_rejects_noncanonical_external_bytes_without_normalizing_them(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, receipt = _build_sealed_values()
    assert receipt is not None
    value = _request_value(receipt)
    noncanonical = (
        json.dumps(value, indent=2, sort_keys=True).encode() + b"\n",
        json.dumps(value, separators=(",", ":"), sort_keys=False).encode() + b"\n",
        _canonical(value) + b"\n",
    )
    for payload in noncanonical:
        stdin = _BinaryStdin(payload)
        monkeypatch.setattr(sys, "stdin", stdin)
        assert main(["decide"]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == "request_invalid\n"


def test_cli_redacts_unexpected_internal_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _, receipt = _build_sealed_values()
    assert receipt is not None
    stdin = _BinaryStdin(_canonical(_request_value(receipt)))
    monkeypatch.setattr(sys, "stdin", stdin)

    def explode(_request: object) -> object:
        raise RuntimeError("secret path /Users/example and token=private")

    monkeypatch.setattr(acquisition_decision_cli, "decide_acquisition_v1", explode)

    assert main(["decide"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "internal_error\n"
    assert "secret" not in captured.err


def test_only_offline_decision_cli_is_installable_and_probe_is_not() -> None:
    project = Path(__file__).parents[2] / "pyproject.toml"
    scripts = tomllib.loads(project.read_text(encoding="utf-8"))["project"]["scripts"]
    assert scripts["market-regime-acquisition-decision"] == (
        "swing_trading_ai_assistant.historical_evaluation.acquisition_decision_cli:main"
    )
    assert not any(
        "probe" in name or "probe" in target for name, target in scripts.items()
    )
