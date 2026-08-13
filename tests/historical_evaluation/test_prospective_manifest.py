"""Provider-free sealed readiness-manifest application tests."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from swing_trading_ai_assistant.historical_evaluation.prospective_cli import main
from swing_trading_ai_assistant.historical_evaluation.prospective_manifest import (
    PROSPECTIVE_MANIFEST_CONTRACT_VERSION_V1,
    RetainedReadinessManifestRequestV1,
    RetainedReadinessManifestServiceV1,
)
from swing_trading_ai_assistant.historical_evaluation.prospective_readiness import (
    ExecutionStateV1,
    PrimaryReasonV1,
    ReadinessStateV1,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "historical_evaluation"
VALIDATION = "4" * 64
CONFIGURATION = "5" * 64


def request() -> RetainedReadinessManifestRequestV1:
    return RetainedReadinessManifestRequestV1(
        FIXTURE / "retained-seal.json",
        FIXTURE / "universe.json",
        (FIXTURE / "schedule-august.json", FIXTURE / "schedule-july.json"),
        FIXTURE / "coverage-manifest.json",
        "nifty50-2026-07-31",
        datetime(2026, 6, 1, tzinfo=UTC),
        datetime(2026, 6, 1, tzinfo=UTC),
        date(2026, 7, 31),
        datetime(2026, 8, 13, tzinfo=UTC),
        VALIDATION,
        CONFIGURATION,
        "d8eaf6da41c6a3a76678aaafbade8541aa27b441",
    )


def test_manifest_is_exact_blocked_no_download_and_replayable() -> None:
    first = RetainedReadinessManifestServiceV1().run(request())
    second = RetainedReadinessManifestServiceV1().run(request())
    payload = first.canonical_json_bytes()

    assert payload == second.canonical_json_bytes()
    assert payload.endswith(b"\n") and not payload.endswith(b"\n\n")
    assert first.report.execution_state is ExecutionStateV1.NOT_REQUESTED
    assert first.report.readiness_state is ReadinessStateV1.BLOCKED
    assert first.report.ready_count == 0
    assert first.report.blocked_count == 50
    assert len(first.report.rows) == 50
    assert {row.primary_reason for row in first.report.rows} == {
        PrimaryReasonV1.MEMBERSHIP_LATE
    }
    assert first.provider_attempts == first.network_attempts == 0
    assert first.storage_write_attempts == 0
    assert first.report.provider_attempts == 0
    value = json.loads(payload)
    identity = value.pop("manifest_identity_sha256")
    canonical = (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        + b"\n"
    )
    assert identity == hashlib.sha256(canonical).hexdigest()
    assert value["contract_version"] == PROSPECTIVE_MANIFEST_CONTRACT_VERSION_V1
    assert value["sprint4_result"] == {
        "eligible_pairs": 0,
        "insufficient_pairs": 1550,
        "requested_pairs": 1550,
        "result_is_immutable": True,
    }
    serialized = payload.decode()
    for forbidden in (
        '"open"',
        '"high"',
        '"low"',
        '"close"',
        "access_token",
        "broker_order",
        "place_order",
    ):
        assert forbidden not in serialized
    assert (
        "UPSTOX_IS_CURRENT_MARKET_DATA_PROVIDER_NOT_PORTFOLIO_OR_ORDER_AUTHORITY"
        in serialized
    )
    assert (
        "READ_ONLY_PORTFOLIO_AND_FUTURE_ORDER_CONNECTORS_ARE_SEPARATE_BROKER_AGNOSTIC_BOUNDARIES"
        in serialized
    )


def test_exact_inputs_reject_corruption_coordinated_reseal_and_duplicate_path(
    tmp_path: Path,
) -> None:
    source = FIXTURE / "retained-seal.json"
    corrupt = tmp_path / "seal.json"
    corrupt.write_bytes(source.read_bytes() + b" ")
    with pytest.raises(ValueError, match="manifest unavailable"):
        RetainedReadinessManifestServiceV1().run(replace(request(), seal_path=corrupt))

    universe = tmp_path / "universe.json"
    value = json.loads((FIXTURE / "universe.json").read_bytes())
    value["constituents"][0]["symbol"] = "FORGED"
    universe.write_text(json.dumps(value, separators=(",", ":")) + "\n")
    with pytest.raises(ValueError, match="manifest unavailable"):
        RetainedReadinessManifestServiceV1().run(
            replace(request(), universe_path=universe)
        )

    with pytest.raises(ValueError, match="manifest request"):
        replace(
            request(),
            schedule_paths=(FIXTURE / "schedule-july.json",) * 2,
        )


def test_safe_reader_rejects_symlink_fifo_and_oversize(tmp_path: Path) -> None:
    symlink = tmp_path / "seal-link.json"
    symlink.symlink_to(FIXTURE / "retained-seal.json")
    with pytest.raises(ValueError, match="manifest unavailable"):
        RetainedReadinessManifestServiceV1().run(replace(request(), seal_path=symlink))

    oversized = tmp_path / "coverage.json"
    oversized.write_bytes(b"x" * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="manifest unavailable"):
        RetainedReadinessManifestServiceV1().run(
            replace(request(), coverage_manifest_path=oversized)
        )

    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    # Opening a FIFO read-only can block, so the stat-safe public service must
    # reject it before a blocking read. The application currently opens with
    # O_NONBLOCK to prove this behavior.
    with pytest.raises(ValueError, match="manifest unavailable"):
        RetainedReadinessManifestServiceV1().run(
            replace(request(), coverage_manifest_path=fifo)
        )


def test_cli_stdout_is_canonical_and_errors_are_sanitized(capsys) -> None:
    args = [
        "--seal",
        str(FIXTURE / "retained-seal.json"),
        "--universe",
        str(FIXTURE / "universe.json"),
        "--schedule",
        str(FIXTURE / "schedule-august.json"),
        "--schedule",
        str(FIXTURE / "schedule-july.json"),
        "--coverage-manifest",
        str(FIXTURE / "coverage-manifest.json"),
        "--cohort-id",
        "nifty50-2026-07-31",
        "--declared-at",
        "2026-06-01T00:00:00Z",
        "--declaration-retained-at",
        "2026-06-01T00:00:00Z",
        "--decision-session",
        "2026-07-31",
        "--evaluated-at",
        "2026-08-13T00:00:00Z",
        "--validation-policy-sha256",
        VALIDATION,
        "--configuration-sha256",
        CONFIGURATION,
        "--code-identity",
        "d8eaf6da41c6a3a76678aaafbade8541aa27b441",
    ]
    assert main(args) == 0
    captured = capsys.readouterr()
    assert (
        json.loads(captured.out)["contract_version"]
        == PROSPECTIVE_MANIFEST_CONTRACT_VERSION_V1
    )
    assert captured.err == ""

    bad = args.copy()
    bad[1] = "missing-secret-looking-path"
    assert main(bad) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "retained readiness manifest unavailable\n"
    assert "missing-secret" not in captured.err


def test_application_has_no_provider_network_credential_or_order_dependency() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "src/swing_trading_ai_assistant/historical_evaluation/prospective_manifest.py"
    ).read_text()
    for forbidden in (
        "httpx",
        "requests",
        "socket",
        "access_token",
        "UPSTOX_ACCESS_TOKEN",
        "place_order",
        "order execution",
    ):
        assert forbidden not in source
