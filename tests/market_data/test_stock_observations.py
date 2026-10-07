"""Behavioral checks for exact retained research across executions."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data import stock_observations_cli as cli

_HELPER = Path(__file__).with_name("test_current_stock_observation_comparison.py")
_SPEC = importlib.util.spec_from_file_location(
    "stock_observation_test_sources", _HELPER
)
assert _SPEC is not None and _SPEC.loader is not None
sources = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = sources
_SPEC.loader.exec_module(sources)

PREVIOUS = datetime(2026, 8, 26, 4, 15, tzinfo=UTC)
CURRENT = datetime(2026, 8, 27, 4, 15, tzinfo=UTC)


@pytest.fixture
def recorded(tmp_path):
    service = importlib.import_module(
        "swing_trading_ai_assistant.market_data.stock_observations"
    )
    root = tmp_path / "evidence"
    original = sources._observation(root, PREVIOUS)
    handle = service.record_stock_observation_v1(root, original)
    return service, root, original, handle


def _publish_test_record(service, root, value):
    raw = service._canonical(value)
    handle = hashlib.sha256(raw).hexdigest()
    target = root / "stock-observations-v1" / f"{handle}.json"
    target.write_bytes(raw)
    target.chmod(0o400)
    return handle


def _snapshot(root):
    return {
        str(path.relative_to(root)): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_mode & 0o777,
        )
        for path in root.rglob("*")
        if path.is_file() and path.name != ".storage-root.lock"
    }


@pytest.mark.parametrize("question", ["PRICE_BEHAVIOR", "CURRENT_STRUCTURE"])
def test_original_result_survives_readback_without_source_acquisition(
    tmp_path, question
):
    service = importlib.import_module(
        "swing_trading_ai_assistant.market_data.stock_observations"
    )
    root = tmp_path / "evidence"
    original = sources._observation(root, PREVIOUS, question=question)
    handle = service.record_stock_observation_v1(root, original)
    with pytest.MonkeyPatch.context() as patch:

        def deny(*_args, **_kwargs):
            raise AssertionError("readback attempted current source acquisition")

        patch.setattr(sources, "research_current_stock_v2", deny)
        patch.setattr(
            importlib.import_module(
                "swing_trading_ai_assistant.market_data.current_stock_research_v2"
            ),
            "research_current_stock_v2",
            deny,
        )
        patch.setattr(socket, "socket", deny)
        before = _snapshot(root)
        restored = service.read_stock_observation_v1(root, handle)
        assert _snapshot(root) == before
    assert restored.canonical_json_bytes() == original.canonical_json_bytes()
    assert restored.data_selection_time == PREVIOUS
    assert service.record_stock_observation_v1(root, original) == handle
    record = root / "stock-observations-v1" / f"{handle}.json"
    assert record.stat().st_mode & 0o777 == 0o400
    assert b"source_bars" not in record.read_bytes()


def test_selected_missing_baseline_is_explicit_and_does_not_create_evidence(tmp_path):
    service = importlib.import_module(
        "swing_trading_ai_assistant.market_data.stock_observations"
    )
    root = tmp_path / "missing"
    with pytest.raises(service.StockObservationUnavailableV1):
        service.read_stock_observation_v1(root, "a" * 64)
    assert not root.exists()


def test_two_retained_observations_compare_original_admitted_facts(tmp_path):
    service = importlib.import_module(
        "swing_trading_ai_assistant.market_data.stock_observations"
    )
    root = tmp_path / "evidence"
    previous = sources._observation(root, PREVIOUS)
    previous_handle = service.record_stock_observation_v1(root, previous)
    current = sources._observation(root, CURRENT, close=sources.Decimal("108"))
    current_handle = service.record_stock_observation_v1(root, current)
    comparison = service.compare_stock_observations_v1(
        root, previous_handle, current_handle
    )
    result = json.loads(comparison.canonical_json_bytes())
    assert result["status"] == "COMPARABLE"
    facts = {x["path"]: x for x in result["facts"]}
    assert facts["CANDLE_GEOMETRY.body_size"]["delta"] == "3"
    assert (
        service.read_stock_observation_v1(root, previous_handle).canonical_json_bytes()
        == previous.canonical_json_bytes()
    )


def test_newly_unavailable_fact_is_preserved_after_readback(recorded):
    service, root, _, previous = recorded
    current = sources._observation(root, CURRENT, one_session=True)
    handle = service.record_stock_observation_v1(root, current)
    result = service.compare_stock_observations_v1(root, previous, handle)
    assert result.status == "COMPARABLE"
    parsed = json.loads(result.canonical_json_bytes())
    missing = [
        x for x in parsed["facts"] if x["path"].startswith("PREVIOUS_CLOSE_COMPARISON")
    ]
    assert missing and all(
        x["state"] == "NEWLY_UNAVAILABLE" and x["delta"] is None for x in missing
    )


def test_same_observation_is_non_comparable_and_not_an_unchanged_signal(recorded):
    service, root, _, handle = recorded
    compared = service.compare_stock_observations_v1(root, handle, handle)
    assert compared.status == "NON_COMPARABLE"
    assert compared.code == "INVALID_TEMPORAL_ORDER"


def test_terminal_unavailable_research_is_not_promoted_to_facts(recorded):
    service, root, original, handle = recorded
    unavailable = replace(
        original,
        status="UNAVAILABLE",
        stage="source",
        code="SOURCE_UNAVAILABLE",
        packet=None,
        evidence_known_at=None,
    )
    missing_handle = service.record_stock_observation_v1(root, unavailable)
    restored = service.read_stock_observation_v1(root, missing_handle)
    assert restored.canonical_json_bytes() == unavailable.canonical_json_bytes()
    assert (
        service.compare_stock_observations_v1(root, handle, missing_handle).code
        == "OBSERVATION_UNAVAILABLE"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("contract_version", "observation-record@v99"),
        ("runtime_code_identity_sha256", "0" * 64),
        ("extra", "unadmitted"),
    ],
)
def test_unknown_record_contract_or_runtime_or_extra_field_is_rejected(
    recorded, field, value
):
    service, root, _, handle = recorded
    saved = json.loads((root / "stock-observations-v1" / f"{handle}.json").read_bytes())
    saved[field] = value
    forged = _publish_test_record(service, root, saved)
    before = _snapshot(root)
    with pytest.raises(service.StockObservationUnavailableV1):
        service.read_stock_observation_v1(root, forged)
    assert _snapshot(root) == before


@pytest.mark.parametrize(
    "kind", ["mapping", "revision", "known-time", "selection", "limitations", "fact"]
)
def test_substituted_original_evidence_cannot_be_read_as_admitted_facts(recorded, kind):
    service, root, _, handle = recorded
    saved = json.loads((root / "stock-observations-v1" / f"{handle}.json").read_bytes())
    result = saved["result"]
    if kind == "mapping":
        result["packet"]["mapping_projection"]["members"][0]["isin"] = "INE062A01020"
    elif kind == "revision":
        result["packet"]["feature_slots"][0]["source"][
            "capture_revision_identity_sha256"
        ] = "a" * 64
    elif kind == "known-time":
        result["evidence_known_at"] = "2026-08-27T04:15:00.000000Z"
    elif kind == "selection":
        result["data_selection_time"] = "2026-08-25T04:15:00.000000Z"
    elif kind == "limitations":
        result["limitations"] = ["eligible_to_trade"]
    else:
        result["packet"]["members"][0]["extra_fact"] = "BUY"
    forged = _publish_test_record(service, root, saved)
    with pytest.raises(service.StockObservationUnavailableV1):
        service.read_stock_observation_v1(root, forged)


@pytest.mark.parametrize("unsafe", ["mode", "hardlink", "symlink", "truncated"])
def test_unsafe_or_corrupt_selected_object_fails_closed(recorded, unsafe):
    service, root, _, handle = recorded
    record = root / "stock-observations-v1" / f"{handle}.json"
    if unsafe == "mode":
        record.chmod(0o600)
    elif unsafe == "hardlink":
        os.link(record, root / "linked")
    elif unsafe == "symlink":
        other = root / "original"
        record.rename(other)
        record.symlink_to(other)
    else:
        record.chmod(0o600)
        record.write_bytes(b"{}\n")
        record.chmod(0o400)
    with pytest.raises(service.StockObservationUnavailableV1):
        service.read_stock_observation_v1(root, handle)


def test_missing_capture_revision_refuses_original_record(recorded):
    service, root, original, handle = recorded
    revision = original.packet.feature_slots[0].source.capture_revision_identity_sha256
    path = root / "bharatstock-capture-v3" / "revisions" / f"{revision}.json"
    assert path.exists()
    path.unlink()
    with pytest.raises(service.StockObservationUnavailableV1):
        service.read_stock_observation_v1(root, handle)


def test_lease_contention_and_retry_preserve_exact_handle(recorded):
    service, root, original, handle = recorded
    with service._lease(root):
        with pytest.raises(service.StockObservationUnavailableV1):
            service.read_stock_observation_v1(root, handle)
        with pytest.raises(service.StockObservationUnavailableV1):
            service.record_stock_observation_v1(root, original)
    assert service.record_stock_observation_v1(root, original) == handle


def test_interrupted_publish_never_reports_success_and_retry_recovers(
    recorded, monkeypatch
):
    service, root, _, _ = recorded
    current = sources._observation(root, CURRENT)
    publish = service.private_store.publish_capture_bytes

    def interrupt(*args, **kwargs):
        held = service.private_store.prepare_capture_publication(*args, **kwargs)
        held.close()
        raise OSError("synthetic private failure")

    monkeypatch.setattr(service.private_store, "publish_capture_bytes", interrupt)
    with pytest.raises(service.StockObservationUnavailableV1):
        service.record_stock_observation_v1(root, current)
    monkeypatch.setattr(service.private_store, "publish_capture_bytes", publish)
    handle = service.record_stock_observation_v1(root, current)
    assert (
        service.read_stock_observation_v1(root, handle).canonical_json_bytes()
        == current.canonical_json_bytes()
    )


def test_json_nesting_and_duplicate_key_boundaries():
    service = importlib.import_module(
        "swing_trading_ai_assistant.market_data.stock_observations"
    )

    def nested(level):
        value = 0
        for _ in range(level):
            value = [value]
        return service._canonical({"value": value})

    assert service._closed_json(nested(63))["value"]
    for raw in [
        nested(64),
        b'{"same":1,"same":2}\n',
        b'{"value":NaN}\n',
        b'{"value":1.5}\n',
        b"x" * (service.MAX_RECORD_BYTES_V1 + 1),
    ]:
        with pytest.raises(ValueError):
            service._closed_json(raw)


def test_real_cli_process_missing_baseline_is_sanitized(tmp_path):
    root = tmp_path / "private-path-must-not-leak"
    script = "import sys; from swing_trading_ai_assistant.market_data.stock_observations_cli import main; sys.exit(main())"
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and CLI probe
        [
            sys.executable,
            "-c",
            script,
            "read",
            "--storage-root",
            str(root),
            "--observation",
            "a" * 64,
            "--output",
            "json",
        ],
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        },
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result == {
        "contract_version": "stock-observations@v1",
        "status": "UNAVAILABLE",
        "code": "OBSERVATION_RECORD_UNAVAILABLE",
    }
    assert str(root).encode() not in completed.stdout + completed.stderr
    assert not root.exists()


def test_cli_observe_read_and_compare_lifecycle(recorded, monkeypatch, capsys):
    service, root, original, handle = recorded
    monkeypatch.setattr(
        cli, "research_current_stock_v2", lambda *args, **kwargs: original
    )
    # 1. Observe command
    code = cli.main(
        [
            "observe",
            "--symbol",
            "PNB",
            "--storage-root",
            str(root),
            "--question",
            "PRICE_BEHAVIOR",
            "--output",
            "json",
        ]
    )
    assert code == 0
    observed_out = json.loads(capsys.readouterr().out)
    assert observed_out["status"] == "RECORDED"
    assert observed_out["observation_identity_sha256"] == handle

    # 2. Read command
    code = cli.main(
        [
            "read",
            "--storage-root",
            str(root),
            "--observation",
            handle,
            "--output",
            "json",
        ]
    )
    assert code == 0
    read_out = json.loads(capsys.readouterr().out)
    assert read_out["status"] == "READ"
    assert read_out["observation_identity_sha256"] == handle
    assert read_out["research"] == json.loads(original.canonical_json_bytes())

    # 3. Compare command with second observation
    current = sources._observation(root, CURRENT, close=sources.Decimal("108"))
    current_handle = service.record_stock_observation_v1(root, current)
    code = cli.main(
        [
            "compare",
            "--storage-root",
            str(root),
            "--previous",
            handle,
            "--current",
            current_handle,
            "--output",
            "json",
        ]
    )
    assert code == 0
    compare_out = json.loads(capsys.readouterr().out)
    assert compare_out["status"] == "COMPARABLE"
    assert compare_out["previous_observation_identity_sha256"] == handle
    assert compare_out["current_observation_identity_sha256"] == current_handle


@pytest.mark.parametrize(
    "args",
    [
        [
            "observe",
            "--symbol",
            "invalid symbol!",
            "--storage-root",
            "/var/empty",
            "--question",
            "PRICE_BEHAVIOR",
            "--output",
            "json",
        ],
        [
            "read",
            "--storage-root",
            "relative/path",
            "--observation",
            "a" * 64,
            "--output",
            "json",
        ],
        [
            "compare",
            "--storage-root",
            "/var/empty",
            "--previous",
            "short-handle",
            "--current",
            "b" * 64,
            "--output",
            "json",
        ],
    ],
)
def test_cli_rejects_malformed_arguments_with_exit_code_2(args, capsys):
    code = cli.main(args)
    assert code == 2
    err = capsys.readouterr().err
    assert err == "request_invalid\n"


def test_installed_stock_observations_verifier_contract(tmp_path, monkeypatch):
    root_dir = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root_dir / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "linux_distribution", root_dir / "scripts/verify_linux_distribution.py"
    )
    assert spec is not None and spec.loader is not None
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)

    # Prepare fake successful probe and command runs
    records = [
        {"handle": "1" * 64, "result": {"symbol": "PNB", "status": "READY"}},
        {"handle": "2" * 64, "result": {"symbol": "PNB", "status": "READY"}},
    ]

    def fake_run(args, **kwargs):
        cmd_str = " ".join(args)
        if "-c" in args:
            return subprocess.CompletedProcess(
                args, 0, json.dumps(records).encode(), b""
            )
        if "read" in args and "--observation" in args:
            handle = args[args.index("--observation") + 1]
            if handle == "1" * 64:
                payload = {
                    "contract_version": "stock-observations@v1",
                    "status": "READ",
                    "observation_identity_sha256": "1" * 64,
                    "research": records[0]["result"],
                }
                return subprocess.CompletedProcess(
                    args, 0, json.dumps(payload).encode(), b""
                )
            if handle == "2" * 64:
                payload = {
                    "contract_version": "stock-observations@v1",
                    "status": "READ",
                    "observation_identity_sha256": "2" * 64,
                    "research": records[1]["result"],
                }
                return subprocess.CompletedProcess(
                    args, 0, json.dumps(payload).encode(), b""
                )
            # Missing baseline
            payload = {
                "contract_version": "stock-observations@v1",
                "status": "UNAVAILABLE",
                "code": "OBSERVATION_RECORD_UNAVAILABLE",
            }
            return subprocess.CompletedProcess(
                args, 1, json.dumps(payload).encode(), b""
            )
        if "compare" in args:
            payload = {
                "contract_version": "stock-observations@v1",
                "status": "COMPARABLE",
                "previous_observation_identity_sha256": "1" * 64,
                "current_observation_identity_sha256": "2" * 64,
                "comparison": {},
            }
            return subprocess.CompletedProcess(
                args, 0, json.dumps(payload).encode(), b""
            )
        if "--help" in args:
            return subprocess.CompletedProcess(args, 0, b"stock-observations help", b"")
        raise AssertionError(f"unexpected command: {cmd_str}")

    monkeypatch.setattr(verifier, "_run", fake_run)
    outcomes = verifier._verify_installed_stock_observations(
        tmp_path / "venv/bin/python", tmp_path
    )
    assert outcomes["synthetic_only"] is True
    assert outcomes["recorded"] == 2
    assert outcomes["original_readback"] == "exact"
    assert outcomes["console_comparison"] == "COMPARABLE"
    assert outcomes["missing_baseline"] == "explicit"
