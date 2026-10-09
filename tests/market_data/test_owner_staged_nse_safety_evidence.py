"""Contract checks for the offline owner-staged NSE safety-evidence boundary."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
from inspect import signature
from pathlib import Path
from typing import cast

import pytest
from test_current_stock_research import _NOW, _Clock
from test_setup_invalidation import _AnchoredPrices
from test_setup_screen import _service

from swing_trading_ai_assistant.market_data import (
    owner_staged_nse_safety_evidence as safety_evidence,
)
from swing_trading_ai_assistant.market_data.bharatstock import BharatStockClient
from swing_trading_ai_assistant.market_data.current_cohort import (
    current_cohort_runtime_code_identity_v1,
)
from swing_trading_ai_assistant.market_data.owner_staged_nse_safety_evidence import (
    MAX_ARTIFACT_BYTES_V1,
    MAX_FIELD_CHARACTERS_V1,
    MAX_ROWS_V1,
    OwnerStagedNseSafetyEvidenceUnavailableV1,
    _runtime_identity,
    inspect_owner_staged_nse_safety_evidence_v1,
)
from swing_trading_ai_assistant.market_data.owner_staged_nse_safety_evidence_cli import (
    main as cli_main,
)
from swing_trading_ai_assistant.market_data.owner_staged_nse_safety_evidence_runtime_identity_manifest import (
    OWNER_STAGED_NSE_SAFETY_EVIDENCE_RUNTIME_SOURCE_SHA256_V1,
)
from swing_trading_ai_assistant.market_data.runtime_identity_manifest import (
    MARKET_DATA_RUNTIME_SOURCE_SHA256_V1,
)
from swing_trading_ai_assistant.market_data.stock_observations import (
    record_stock_observation_v1,
)

_PACKAGE = "nse-safety-evidence-v1"
_ISIN = "INE160A01022"


def _structure_observation(root: Path, *, question: str = "CURRENT_STRUCTURE"):
    root.mkdir(mode=0o700, exist_ok=True)
    clock = _Clock()
    clock.value = _NOW
    if question != "CURRENT_STRUCTURE":
        return _service()("PNB", root, question=question, clock=clock)
    return _service()(
        "PNB",
        root,
        question=question,
        clock=clock,
        price_client=cast(
            BharatStockClient,
            _AnchoredPrices(clock.value, close=134, wick=120),
        ),
    )


def _write(package: Path, name: str, value: str, *, mode: int = 0o600) -> Path:
    path = package / name
    path.write_text(value, encoding="utf-8")
    path.chmod(mode)
    return path


def _stage_package(
    root: Path,
    *,
    equity: str | None = None,
    asm: str = "SYMBOL\nOTHER\n",
    gsm: str = "SYMBOL\nOTHER\n",
) -> Path:
    package = root / _PACKAGE
    package.mkdir(mode=0o700)
    _write(
        package,
        "equity-trading.csv",
        equity
        or "SYMBOL,SERIES,ISIN NUMBER,DATE OF LISTING\nPNB,EQ,INE160A01022,05-Jun-1995\n",
    )
    _write(package, "asm.csv", asm)
    _write(package, "gsm.csv", gsm)
    return package


def _snapshot(root: Path) -> dict[str, tuple[str, int]]:
    return {
        str(path.relative_to(root)): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_mode & 0o777,
        )
        for path in root.rglob("*")
        if path.is_file()
    }


def _artifact_identity(package: Path) -> dict[str, tuple[int, int, int, int]]:
    result: dict[str, tuple[int, int, int, int]] = {}
    for path in package.iterdir():
        metadata = path.stat()
        if path.is_file():
            result[path.name] = (
                metadata.st_ino,
                metadata.st_uid,
                metadata.st_nlink,
                metadata.st_mode & 0o777,
            )
    return result


@pytest.fixture
def retained_observation(tmp_path: Path) -> tuple[Path, str]:
    observed = _structure_observation(tmp_path)
    return tmp_path, record_stock_observation_v1(tmp_path, observed)


def test_valid_operator_staged_package_is_inspectable_but_never_eligible(
    retained_observation: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, handle = retained_observation
    _stage_package(root)
    before = _snapshot(root)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("source acquisition attempted")

    monkeypatch.setattr(socket, "socket", forbidden)
    result = inspect_owner_staged_nse_safety_evidence_v1(root, handle)

    assert _snapshot(root) == before
    assert result["schema"] == "stock-safety-evidence@v1"
    assert result["status"] == "STAGED"
    assert result["eligibility_status"] == "UNKNOWN"
    assert result["symbol"] == "PNB"
    assert result["observation_identity_sha256"] == handle
    evidence = result["operator_staged_evidence"]
    assert evidence["listing_date_observed"] is True
    assert evidence["asm_membership"] == "NOT_OBSERVED_IN_STAGED_LIST"
    assert evidence["gsm_membership"] == "NOT_OBSERVED_IN_STAGED_LIST"
    assert [item["kind"] for item in evidence["artifacts"]] == [
        "EQUITY_TRADING",
        "ASM",
        "GSM",
    ]
    assert all(len(item["artifact_sha256"]) == 64 for item in evidence["artifacts"])
    assert result["refusal_reasons"] == [
        "OPERATOR_STAGED_EVIDENCE_NOT_SOURCE_AUTHENTICATED",
        "LISTING_DURATION_POLICY_UNAVAILABLE",
        "EXECUTION_LIQUIDITY_POLICY_UNAVAILABLE",
        "PRICE_CURRENCY_AND_LOW_PRICE_POLICY_UNAVAILABLE",
        "EVENT_RISK_COVERAGE_UNAVAILABLE",
    ]
    public = json.dumps(result, sort_keys=True)
    assert "ELIGIBLE" not in public
    assert "ACTIONABLE" not in public
    assert "05-Jun-1995" not in public
    assert _ISIN not in public
    assert "SYMBOL,SERIES" not in public
    assert str(root) not in public
    unsigned = dict(result)
    identity = unsigned.pop("result_identity_sha256")
    assert (
        identity
        == hashlib.sha256(
            json.dumps(
                unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
            + b"\n"
        ).hexdigest()
    )


def test_staged_surveillance_membership_is_literal_and_never_clearance(
    retained_observation: tuple[Path, str],
) -> None:
    root, handle = retained_observation
    _stage_package(root, asm="SYMBOL\nPNB\n", gsm="SYMBOL\nPNB\n")

    result = inspect_owner_staged_nse_safety_evidence_v1(root, handle)

    evidence = result["operator_staged_evidence"]
    assert evidence["asm_membership"] == "OBSERVED_IN_STAGED_LIST"
    assert evidence["gsm_membership"] == "OBSERVED_IN_STAGED_LIST"
    assert result["eligibility_status"] == "UNKNOWN"
    assert "ELIGIBLE" not in json.dumps(result, sort_keys=True)


def test_public_sdk_has_no_raw_source_or_policy_input_surface() -> None:
    parameters = set(signature(inspect_owner_staged_nse_safety_evidence_v1).parameters)
    assert parameters == {"storage_root", "observation"}
    assert (
        not {
            "artifact",
            "artifact_root",
            "bars",
            "eligibility",
            "mapping",
            "price",
            "source_url",
            "source_time",
        }
        & parameters
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "missing",
        "extra",
        "mode",
        "hardlink",
        "symlink",
        "special",
        "wrong_mapping",
        "duplicate_equity",
        "duplicate_asm",
        "duplicate_gsm",
        "malformed_header",
        "header_collision",
        "invalid_listing",
        "short_listing",
        "invalid_utf8",
        "formula",
    ),
)
def test_unsafe_or_unadmitted_staged_package_fails_closed(  # noqa: C901 - closed adversarial package matrix
    retained_observation: tuple[Path, str], mutation: str
) -> None:
    root, handle = retained_observation
    package = _stage_package(root)
    equity = package / "equity-trading.csv"
    if mutation == "missing":
        (package / "gsm.csv").unlink()
    elif mutation == "extra":
        _write(package, "unexpected.csv", "SYMBOL\nPNB\n")
    elif mutation == "mode":
        equity.chmod(0o644)
    elif mutation == "hardlink":
        gsm = package / "gsm.csv"
        gsm.unlink()
        os.link(package / "asm.csv", gsm)
    elif mutation == "symlink":
        equity.unlink()
        equity.symlink_to("asm.csv")
    elif mutation == "special":
        gsm = package / "gsm.csv"
        gsm.unlink()
        os.mkfifo(gsm, 0o600)
    elif mutation == "wrong_mapping":
        _write(
            package,
            "equity-trading.csv",
            "SYMBOL,SERIES,ISIN NUMBER,DATE OF LISTING\nPNB,EQ,INE000A01000,05-Jun-1995\n",
        )
    elif mutation == "duplicate_equity":
        _write(
            package,
            "equity-trading.csv",
            "SYMBOL,SERIES,ISIN NUMBER,DATE OF LISTING\n"
            "PNB,EQ,INE160A01022,05-Jun-1995\n"
            "PNB,EQ,INE160A01022,05-Jun-1995\n",
        )
    elif mutation == "duplicate_asm":
        _write(package, "asm.csv", "SYMBOL\nPNB\nPNB\n")
    elif mutation == "duplicate_gsm":
        _write(package, "gsm.csv", "SYMBOL\nPNB\nPNB\n")
    elif mutation == "malformed_header":
        _write(package, "equity-trading.csv", "SYMBOL,ISIN NUMBER\nPNB,INE160A01022\n")
    elif mutation == "header_collision":
        _write(
            package,
            "equity-trading.csv",
            "SYMBOL,Symbol,ISIN NUMBER,DATE OF LISTING\n"
            "PNB,EQ,INE160A01022,05-Jun-1995\n",
        )
    elif mutation == "invalid_listing":
        _write(
            package,
            "equity-trading.csv",
            "SYMBOL,SERIES,ISIN NUMBER,DATE OF LISTING\n"
            "PNB,EQ,INE160A01022,not-a-listing-date\n",
        )
    elif mutation == "short_listing":
        _write(
            package,
            "equity-trading.csv",
            "SYMBOL,SERIES,ISIN NUMBER,DATE OF LISTING\n"
            "PNB,EQ,INE160A01022,5-Jun-1995\n",
        )
    elif mutation == "invalid_utf8":
        equity.write_bytes(b"SYMBOL,SERIES,ISIN NUMBER,DATE OF LISTING\nPNB,EQ,\xff\n")
        equity.chmod(0o600)
    else:
        _write(package, "asm.csv", "SYMBOL\n=PNB\n")
    with pytest.raises(OwnerStagedNseSafetyEvidenceUnavailableV1):
        inspect_owner_staged_nse_safety_evidence_v1(root, handle)


@pytest.mark.parametrize(
    "kind",
    ("bytes", "rows", "field"),
)
def test_csv_limits_fail_closed(
    retained_observation: tuple[Path, str], kind: str
) -> None:
    root, handle = retained_observation
    package = _stage_package(root)
    equity = package / "equity-trading.csv"
    if kind == "bytes":
        _write(package, "equity-trading.csv", "x" * (MAX_ARTIFACT_BYTES_V1 + 1))
    elif kind == "rows":
        rows = "".join(
            "OTHER,EQ,INE000A01000,05-Jun-1995\n" for _ in range(MAX_ROWS_V1)
        )
        _write(
            package,
            "equity-trading.csv",
            "SYMBOL,SERIES,ISIN NUMBER,DATE OF LISTING\n"
            "PNB,EQ,INE160A01022,05-Jun-1995\n" + rows,
        )
    else:
        _write(
            package,
            "equity-trading.csv",
            "SYMBOL,SERIES,ISIN NUMBER,DATE OF LISTING\n"
            "PNB,EQ,INE160A01022,05-Jun-1995\n"
            f"{'x' * (MAX_FIELD_CHARACTERS_V1 + 1)},BE,INE000A01000,05-Jun-1995\n",
        )
    assert equity.exists()
    with pytest.raises(OwnerStagedNseSafetyEvidenceUnavailableV1):
        inspect_owner_staged_nse_safety_evidence_v1(root, handle)


def test_supported_csv_boundaries_and_bom_are_inspectable(
    retained_observation: tuple[Path, str],
) -> None:
    root, handle = retained_observation
    package = _stage_package(root)
    _write(
        package,
        "equity-trading.csv",
        "\ufeffSYMBOL,SERIES,ISIN NUMBER,DATE OF LISTING\n"
        "PNB,EQ,INE160A01022,05-Jun-1995\n",
    )
    _write(package, "asm.csv", f"SYMBOL\n{'X' * MAX_FIELD_CHARACTERS_V1}\n")
    (package / "asm.csv").chmod(0o400)

    result = inspect_owner_staged_nse_safety_evidence_v1(root, handle)

    assert result["status"] == "STAGED"
    assert result["eligibility_status"] == "UNKNOWN"


def test_artifact_and_row_boundaries_are_inspectable(
    retained_observation: tuple[Path, str],
) -> None:
    root, handle = retained_observation
    package = _stage_package(root)
    full_rows = [f"R{index:04d}{'X' * 1018}\n" for index in range(1_023)]
    exact_size = ("SYMBOL\n" + "".join(full_rows) + f"LAST{'X' * 1012}\n").encode(
        "utf-8"
    )
    assert len(exact_size) == MAX_ARTIFACT_BYTES_V1
    (package / "asm.csv").write_bytes(exact_size)
    (package / "asm.csv").chmod(0o600)
    result = inspect_owner_staged_nse_safety_evidence_v1(root, handle)
    assert result["operator_staged_evidence"]["asm_membership"] == (
        "NOT_OBSERVED_IN_STAGED_LIST"
    )

    _write(
        package,
        "gsm.csv",
        "SYMBOL\n" + "".join(f"OTHER{index:05d}\n" for index in range(MAX_ROWS_V1)),
    )
    result = inspect_owner_staged_nse_safety_evidence_v1(root, handle)
    assert result["operator_staged_evidence"]["gsm_membership"] == (
        "NOT_OBSERVED_IN_STAGED_LIST"
    )


def test_package_replacement_after_artifact_read_fails_closed(
    retained_observation: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, handle = retained_observation
    package = _stage_package(root)
    original = safety_evidence._read_open_artifact  # pyright: ignore[reportPrivateUsage]
    replaced = False

    def replace_after_read(artifact: safety_evidence._OpenedArtifact) -> bytes:  # pyright: ignore[reportPrivateUsage]
        nonlocal replaced
        raw = original(artifact)
        if artifact.name == "equity-trading.csv":
            path = package / artifact.name
            path.unlink()
            path.write_bytes(raw)
            path.chmod(0o600)
            replaced = True
        return raw

    monkeypatch.setattr(safety_evidence, "_read_open_artifact", replace_after_read)
    with pytest.raises(OwnerStagedNseSafetyEvidenceUnavailableV1):
        inspect_owner_staged_nse_safety_evidence_v1(root, handle)
    assert replaced


def test_cross_artifact_in_place_mutation_has_no_staged_output(
    retained_observation: tuple[Path, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, handle = retained_observation
    package = _stage_package(root)
    before = _artifact_identity(package)
    original = safety_evidence._read_open_artifact  # pyright: ignore[reportPrivateUsage]
    mutated = False

    def mutate_after_first_read(
        artifact: safety_evidence._OpenedArtifact,  # pyright: ignore[reportPrivateUsage]
    ) -> bytes:
        nonlocal mutated
        raw = original(artifact)
        if artifact.name == "equity-trading.csv":
            _write(
                package,
                artifact.name,
                "SYMBOL,SERIES,ISIN NUMBER,DATE OF LISTING\n"
                "PNB,EQ,INE160A01022,06-Jun-1995\n",
            )
            _write(package, "asm.csv", "SYMBOL\nPNB\n")
            mutated = True
        return raw

    monkeypatch.setattr(safety_evidence, "_read_open_artifact", mutate_after_first_read)
    assert (
        cli_main(
            [
                "inspect",
                "--storage-root",
                str(root),
                "--observation",
                handle,
                "--output",
                "json",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "code": "STAGED_EVIDENCE_UNAVAILABLE",
        "contract_version": "stock-safety-evidence@v1",
        "status": "UNAVAILABLE",
    }
    assert '"status":"STAGED"' not in captured.out
    assert "identity" not in captured.out
    assert mutated
    assert _artifact_identity(package) == before


def test_generic_runtime_inventory_includes_staged_evidence_modules() -> None:
    expected = {
        "owner_staged_nse_safety_evidence.py",
        "owner_staged_nse_safety_evidence_cli.py",
        "owner_staged_nse_safety_evidence_runtime_identity_manifest.py",
    }
    assert expected <= MARKET_DATA_RUNTIME_SOURCE_SHA256_V1.keys()
    assert len(current_cohort_runtime_code_identity_v1()) == 64


def test_non_structure_observation_and_invalid_request_have_no_package_effect(
    tmp_path: Path,
) -> None:
    observed = _structure_observation(tmp_path, question="PRICE_BEHAVIOR")
    handle = record_stock_observation_v1(tmp_path, observed)
    _stage_package(tmp_path)
    before = _snapshot(tmp_path)
    with pytest.raises(OwnerStagedNseSafetyEvidenceUnavailableV1):
        inspect_owner_staged_nse_safety_evidence_v1(tmp_path, handle)
    with pytest.raises(ValueError, match="invalid safety evidence request"):
        inspect_owner_staged_nse_safety_evidence_v1(tmp_path, "not-a-handle")
    assert _snapshot(tmp_path) == before


def test_cli_returns_success_only_for_staging_and_hides_missing_root(
    retained_observation: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    root, handle = retained_observation
    _stage_package(root)

    assert (
        cli_main(
            [
                "inspect",
                "--storage-root",
                str(root),
                "--observation",
                handle,
                "--output",
                "json",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["eligibility_status"] == "UNKNOWN"

    missing = root.parent / "private-root-must-not-leak"
    assert (
        cli_main(
            [
                "inspect",
                "--storage-root",
                str(missing),
                "--observation",
                "a" * 64,
                "--output",
                "json",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "code": "STAGED_EVIDENCE_UNAVAILABLE",
        "contract_version": "stock-safety-evidence@v1",
        "status": "UNAVAILABLE",
    }
    assert str(missing) not in captured.out
    assert not missing.exists()


def test_cli_rejects_raw_or_relative_inputs_before_root_access(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        cli_main(
            [
                "inspect",
                "--storage-root",
                "relative",
                "--observation",
                "a" * 64,
                "--output",
                "json",
                "--input-json",
                str(tmp_path / "forged.json"),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "request_invalid\n"
    assert not (tmp_path / "forged.json").exists()


def test_runtime_identity_is_bound() -> None:
    assert len(_runtime_identity()) == 64


def test_runtime_source_substitution_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        OWNER_STAGED_NSE_SAFETY_EVIDENCE_RUNTIME_SOURCE_SHA256_V1,
        "src/swing_trading_ai_assistant/market_data/owner_staged_nse_safety_evidence.py",
        "0" * 64,
    )
    with pytest.raises(ValueError):
        _runtime_identity()


def test_installed_command_hides_missing_root(tmp_path: Path) -> None:
    root = tmp_path / "private-root-must-not-leak"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = Path(sys.executable).with_name("stock-safety-evidence")
    completed = subprocess.run(  # noqa: S603 - controlled installed command
        [
            str(command),
            "inspect",
            "--storage-root",
            str(root),
            "--observation",
            "a" * 64,
            "--output",
            "json",
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
    )
    assert completed.returncode == 1
    assert completed.stderr == b""
    assert json.loads(completed.stdout) == {
        "code": "STAGED_EVIDENCE_UNAVAILABLE",
        "contract_version": "stock-safety-evidence@v1",
        "status": "UNAVAILABLE",
    }
    assert str(root).encode() not in completed.stdout
    assert not root.exists()
