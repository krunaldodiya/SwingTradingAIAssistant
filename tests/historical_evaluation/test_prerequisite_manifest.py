"""Fail-closed provider-free prerequisite manifest tests."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest

from swing_trading_ai_assistant.historical_evaluation.prerequisite_manifest import (
    EvidenceReadinessPrerequisiteManifestV1,
    PrerequisiteManifestRequestV1,
    PrerequisiteManifestServiceV1,
)
from swing_trading_ai_assistant.historical_evaluation.prospective_cli import main

F = Path(__file__).resolve().parents[1] / "fixtures" / "historical_evaluation"
PLAN11 = (
    Path(__file__).resolve().parents[2]
    / "docs/plans/11-prospective-evidence-readiness-contract.md"
)
CODE_LABEL = "c204f820f9d5deddcbe14c39bdebc33f0e95031e"


def request():
    return PrerequisiteManifestRequestV1(
        PLAN11,
        F / "retained-seal.json",
        F / "universe.json",
        F / "schedule-july.json",
        F / "schedule-august.json",
        F / "coverage-manifest.json",
        CODE_LABEL,
    )


def test_manifest_is_exact_fail_closed_deterministic_and_self_identifying():
    a = PrerequisiteManifestServiceV1().run(request())
    payload = a.canonical_json_bytes()
    assert (
        payload == PrerequisiteManifestServiceV1().run(request()).canonical_json_bytes()
    )
    assert payload.endswith(b"\n") and not payload.endswith(b"\n\n")
    v = json.loads(payload)
    identity = v.pop("manifest_identity_sha256")
    canonical = (
        json.dumps(
            v, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True
        ).encode()
        + b"\n"
    )
    assert identity == hashlib.sha256(canonical).hexdigest()
    assert v["prerequisite_state"] == "DECLARATION_RECEIPT_MISSING"
    assert v["admission_state"] == v["evaluator_state"] == "NOT_EVALUATED"
    assert v["readiness_state"] == v["authorization_state"] == "NOT_ASSESSED"
    assert v["execution_state"] == "NOT_REQUESTED"
    assert v["report_row_count"] == v["request_descriptor_count"] == 0
    assert v["report_rows"] == v["request_descriptors"] == []
    assert v["retained_equity_count"] == 50
    assert len(v["retained_equity_accounting"]) == 50
    assert v["operator_claims"] == {
        "classification": "UNVERIFIED_NOT_AUTHORITY",
        "code_version_label": CODE_LABEL,
        "configuration_record_state": "ABSENT_UNVERIFIED_PREREQUISITE",
        "validation_policy_record_state": "ABSENT_UNVERIFIED_PREREQUISITE",
    }
    assert "code_identity" not in v["authority_bindings"]
    assert "configuration_sha256" not in v["authority_bindings"]
    assert "validation_policy_sha256" not in v["authority_bindings"]
    assert (
        v["authority_bindings"]["plan11_contract_repository_bytes"]["sha256"]
        == hashlib.sha256(PLAN11.read_bytes()).hexdigest()
    )
    assert v["sprint4_result"] == {
        "classification": "INSUFFICIENT_EVIDENCE",
        "eligible_pairs": 0,
        "insufficient_pairs": 1550,
        "provider_attempts": 0,
        "requested_pairs": 1550,
        "result_is_immutable": True,
    }
    assert (
        v["provider_attempts"]
        == v["network_attempts"]
        == v["storage_write_attempts"]
        == 0
    )
    s = payload.decode()
    assert (
        '"open"' not in s
        and '"close"' not in s
        and "access_token" not in s
        and "place_order" not in s
    )


@pytest.mark.parametrize(
    "field,name",
    [
        ("sprint4_seal_path", "retained-seal.json"),
        ("universe_path", "universe.json"),
        ("coverage_manifest_path", "coverage-manifest.json"),
    ],
)
def test_corrupt_or_resealed_pinned_input_rejected(tmp_path, field, name):
    p = tmp_path / name
    p.write_bytes((F / name).read_bytes() + b" ")
    with pytest.raises(ValueError, match="unavailable"):
        PrerequisiteManifestServiceV1().run(replace(request(), **{field: p}))


def test_symlink_fifo_oversize_and_duplicate_paths_rejected(tmp_path):
    link = tmp_path / "link"
    link.symlink_to(F / "retained-seal.json")
    with pytest.raises(ValueError):
        PrerequisiteManifestServiceV1().run(replace(request(), sprint4_seal_path=link))
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(ValueError):
        PrerequisiteManifestServiceV1().run(
            replace(request(), coverage_manifest_path=fifo)
        )
    big = tmp_path / "big"
    big.write_bytes(b"x" * 1_000_001)
    with pytest.raises(ValueError):
        PrerequisiteManifestServiceV1().run(
            replace(request(), coverage_manifest_path=big)
        )
    with pytest.raises(ValueError, match="request"):
        replace(request(), august_schedule_path=F / "schedule-july.json")


def test_duplicate_nan_and_noncanonical_are_rejected_before_use(tmp_path):
    original = (F / "retained-seal.json").read_bytes()
    mutations = (
        original.replace(b"{", b'{"provider_attempt_count":0,', 1),
        original.replace(
            b'"provider_attempt_count":0', b'"provider_attempt_count":NaN', 1
        ),
        original + b" ",
    )
    for index, payload in enumerate(mutations):
        p = tmp_path / str(index)
        p.write_bytes(payload)
        with pytest.raises(ValueError):
            PrerequisiteManifestServiceV1().run(replace(request(), sprint4_seal_path=p))


def args():
    return [
        "--contract",
        str(PLAN11),
        "--seal",
        str(F / "retained-seal.json"),
        "--universe",
        str(F / "universe.json"),
        "--july-schedule",
        str(F / "schedule-july.json"),
        "--august-schedule",
        str(F / "schedule-august.json"),
        "--coverage-manifest",
        str(F / "coverage-manifest.json"),
        "--code-version-label",
        CODE_LABEL,
    ]


def test_cli_stdout_is_canonical_and_errors_sanitized(capsys):
    assert main(args()) == 0
    captured = capsys.readouterr()
    assert (
        json.loads(captured.out)["prerequisite_state"] == "DECLARATION_RECEIPT_MISSING"
    )
    assert captured.err == ""
    bad = args()
    bad[1] = "secret-looking-missing"
    assert main(bad) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "evidence readiness prerequisite manifest unavailable\n"
    assert "secret" not in captured.err


def test_no_provider_network_environment_evaluator_or_order_dependency():
    src = (
        Path(__file__).resolve().parents[2]
        / "src/swing_trading_ai_assistant/historical_evaluation/prerequisite_manifest.py"
    ).read_text()
    for forbidden in (
        "httpx",
        "requests",
        "socket",
        "getenv",
        "environ",
        "access_token",
        "place_order",
        "evaluate_prospective_readiness_v1",
        "DeclarationReceiptV1",
        "SourceReceiptV1",
    ):
        assert forbidden not in src


def test_manifest_rejects_reviewer_caller_owned_accounting_exploit():
    genuine = PrerequisiteManifestServiceV1().run(request())
    with pytest.raises(TypeError, match="service-only"):
        EvidenceReadinessPrerequisiteManifestV1(
            code_version_label=CODE_LABEL,
            retained_equity_accounting=genuine.retained_equity_accounting,
            _construction_token=object(),
        )
    with pytest.raises(TypeError):
        genuine.retained_equity_accounting[0]["symbol"] = "FABRICATED"
    forged = list(genuine.retained_equity_accounting)
    first = dict(forged[0])
    first["candle_object_sha256"] = ("0" * 64, first["candle_object_sha256"][1])
    forged[0] = MappingProxyType(first)
    object.__setattr__(genuine, "retained_equity_accounting", tuple(forged))
    with pytest.raises(ValueError, match="accounting"):
        genuine.canonical_json_bytes()


def test_symlinked_parent_component_is_rejected(tmp_path):
    parent = tmp_path / "linked-parent"
    parent.symlink_to(F, target_is_directory=True)
    with pytest.raises(ValueError, match="unavailable"):
        PrerequisiteManifestServiceV1().run(
            replace(request(), sprint4_seal_path=parent / "retained-seal.json")
        )


def test_contract_bytes_are_pinned_and_caller_labels_are_not_authority(tmp_path):
    corrupted = tmp_path / "plan11.md"
    corrupted.write_bytes(PLAN11.read_bytes() + b" ")
    with pytest.raises(ValueError, match="unavailable"):
        PrerequisiteManifestServiceV1().run(replace(request(), contract_path=corrupted))
    first = json.loads(
        PrerequisiteManifestServiceV1().run(request()).canonical_json_bytes()
    )
    second = json.loads(
        PrerequisiteManifestServiceV1()
        .run(replace(request(), code_version_label="FABRICATED"))
        .canonical_json_bytes()
    )
    assert first["authority_bindings"] == second["authority_bindings"]
    assert second["operator_claims"]["classification"] == "UNVERIFIED_NOT_AUTHORITY"
    assert second["operator_claims"]["code_version_label"] == "FABRICATED"
    assert first["manifest_identity_sha256"] != second["manifest_identity_sha256"]
