from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data import cli, historical_revision_store
from swing_trading_ai_assistant.market_data.historical_revision_store import (
    HistoricalOhlcvImportOutcomeV1,
    HistoricalOhlcvImportResultV1,
    HistoricalOhlcvRevisionStoreV1,
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _rebind_source_inputs(
    request: dict[str, object],
    policy: dict[str, object],
    artifact: dict[str, object],
    receipt: dict[str, object],
) -> tuple[bytes, bytes, bytes, bytes]:
    artifact_raw = _canonical(artifact)
    policy["artifact_sha256"] = _digest(artifact_raw)
    policy_raw = _canonical(policy)
    receipt["source_policy_sha256"] = _digest(policy_raw)
    receipt["source_artifact_sha256"] = _digest(artifact_raw)
    receipt_raw = _canonical(receipt)
    request["source_policy_sha256"] = _digest(policy_raw)
    request["source_artifact_sha256"] = _digest(artifact_raw)
    request["receipt_sha256"] = _digest(receipt_raw)
    return _canonical(request), policy_raw, artifact_raw, receipt_raw


def _with_request_to_session(
    inputs: tuple[bytes, bytes, bytes, bytes], to_session: str
) -> tuple[bytes, bytes, bytes, bytes]:
    request_raw, policy_raw, artifact_raw, receipt_raw = inputs
    request = json.loads(request_raw)
    request["to_session"] = to_session
    request["schedule_evidence_sha256"] = historical_revision_store._schedule_identity(  # pyright: ignore[reportPrivateUsage]
        request["from_session"],
        request["to_session"],
        request["expected_sessions"],
    )
    return _rebind_source_inputs(
        request,
        json.loads(policy_raw),
        json.loads(artifact_raw),
        json.loads(receipt_raw),
    )


def _member(number: int = 2) -> dict[str, object]:
    isin = f"INE{number:03}A01018"
    symbol = f"SYMBOL{number:02}"
    return {
        "isin": isin,
        "exchange": "NSE",
        "listed_equity_segment": "EQUITY",
        "effective_symbol": symbol,
        "symbol_effective_from": "2024-01-01",
        "symbol_effective_to": None,
        "provider_mapping": {
            "provider": "OPERATOR_LOCAL_IMPORT",
            "provider_instrument_id": f"{symbol}-EQ",
            "mapping_effective_from": "2024-01-01",
            "mapping_effective_to": None,
            "mapping_evidence_sha256": _digest(f"mapping-evidence-{number}".encode()),
        },
    }


def _bar(
    session: str,
    *,
    member: dict[str, object] | None = None,
    close: str = "100.5",
    known_at: str = "2024-01-04T00:00:00Z",
) -> dict[str, object]:
    selected = _member() if member is None else member
    return {
        "isin": selected["isin"],
        "exchange": selected["exchange"],
        "session": session,
        "open": "100",
        "high": "101",
        "low": "99",
        "close": close,
        "volume": "10",
        "known_at": known_at,
        "price_basis": "SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED",
    }


def _inputs(
    *,
    sessions: tuple[str, ...] = ("2024-01-02", "2024-01-03"),
    operation: str = "INITIAL",
    parent: str | None = None,
    correction_coordinates: list[dict[str, str]] | None = None,
    members: list[dict[str, object]] | None = None,
    bars: list[dict[str, object]] | None = None,
) -> tuple[bytes, bytes, bytes, bytes]:
    cohort = [_member()] if members is None else members
    artifact = {
        "schema_version": "operator-local-historical-ohlcv-artifact@v1",
        "bars": (
            [_bar(session, member=member) for member in cohort for session in sessions]
            if bars is None
            else bars
        ),
    }
    artifact_raw = _canonical(artifact)
    policy = {
        "schema_version": "operator-local-historical-ohlcv-source-policy@v1",
        "source_name": "owner-supplied-fixture",
        "permitted_use": "OWNER_PRIVATE_RESEARCH",
        "ohlcv_adjustment_semantics": "SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED",
        "artifact_sha256": _digest(artifact_raw),
    }
    policy_raw = _canonical(policy)
    receipt = {
        "schema_version": "operator-local-historical-ohlcv-receipt@v1",
        "source_policy_sha256": _digest(policy_raw),
        "source_artifact_sha256": _digest(artifact_raw),
        "acquired_at": "2024-01-04T00:00:00Z",
        "known_at": "2024-01-04T00:00:00Z",
        "permitted_use": "OWNER_PRIVATE_RESEARCH",
        "ohlcv_adjustment_semantics": "SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED",
    }
    identities = historical_revision_store._required_identities()  # pyright: ignore[reportPrivateUsage]
    receipt_raw = _canonical(receipt)
    request = {
        "contract_version": "fixed-cohort-historical-ohlcv-revision-store@v1",
        "research_scope": "FIXED_COHORT_RETROSPECTIVE",
        "operation": operation,
        "parent_revision_sha256": parent,
        "correction_coordinates": correction_coordinates or [],
        "cohort": cohort,
        "from_session": sessions[0],
        "to_session": sessions[-1],
        "interval": "1d",
        "expected_sessions": list(sessions),
        "schedule_evidence_sha256": historical_revision_store._schedule_identity(  # pyright: ignore[reportPrivateUsage]
            sessions[0], sessions[-1], list(sessions)
        ),
        "source_policy_sha256": _digest(policy_raw),
        "source_artifact_sha256": _digest(artifact_raw),
        "receipt_sha256": _digest(receipt_raw),
        "acquired_at": "2024-01-04T00:00:00Z",
        "known_at_cutoff": "2024-01-05T00:00:00Z",
        "permitted_use": "OWNER_PRIVATE_RESEARCH",
        "price_basis": "SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED",
        "schema_identity_sha256": identities[0],
        "runtime_code_identity_sha256": identities[1],
        "configuration_identity_sha256": identities[2],
        "limits": {
            "max_members": 50,
            "max_sessions": 10000,
            "max_rows": 500000,
            "max_artifact_bytes": 134217728,
            "max_source_policy_bytes": 1048576,
            "max_receipt_bytes": 1048576,
            "max_revision_bytes": 134217728,
            "max_lineage_depth": 128,
        },
    }
    return _canonical(request), policy_raw, artifact_raw, receipt_raw


def _import(
    store: HistoricalOhlcvRevisionStoreV1,
    inputs: tuple[bytes, bytes, bytes, bytes],
):
    return store.import_exact(*inputs)


def _open_descriptor_count() -> int:
    return len(os.listdir("/dev/fd"))


def test_initial_revision_is_content_addressed_replayable_and_exact_readable(
    tmp_path: Path,
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    inputs = _inputs()

    first = _import(store, inputs)
    replay = _import(store, inputs)

    assert first.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert replay.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert (
        os.stat(
            tmp_path
            / "historical_ohlcv_revisions"
            / "v1"
            / "revisions"
            / f"{first.revision_sha256}.json"
        ).st_mode
        & 0o777
    ) == 0o400
    assert first.revision_sha256 == replay.revision_sha256
    assert first.revision is not None
    assert first.revision["revision_sha256"] == first.revision_sha256
    read = store.read_exact(first.revision_sha256)
    assert read.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert read.revision == first.revision
    assert (tmp_path / "historical_ohlcv_revisions" / "v1" / "revisions").is_dir()


def test_request_identity_changes_with_bound_content(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    changed_root = tmp_path / "changed"
    first_root.mkdir(mode=0o700)
    changed_root.mkdir(mode=0o700)
    first = _import(HistoricalOhlcvRevisionStoreV1(first_root), _inputs())
    changed = _import(
        HistoricalOhlcvRevisionStoreV1(changed_root),
        _inputs(
            bars=[
                _bar("2024-01-02", close="100.5"),
                _bar("2024-01-03", close="100.75"),
            ]
        ),
    )

    assert first.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert changed.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert first.revision_sha256 != changed.revision_sha256
    assert first.revision is not None and changed.revision is not None
    assert (
        first.revision["request_identity_sha256"]
        != changed.revision["request_identity_sha256"]
    )


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda request, _policy, _artifact, _receipt: request.update(
                {"price_basis": "RAW"}
            ),
            HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY,
        ),
        (
            lambda request, _policy, _artifact, _receipt: request.update(
                {"interval": "1m"}
            ),
            HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT,
        ),
        (
            lambda request, _policy, _artifact, _receipt: request.update(
                {"cohort": []}
            ),
            HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT,
        ),
        (
            lambda request, _policy, _artifact, _receipt: request.update(
                {"cohort": [_member()] * 51}
            ),
            HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT,
        ),
        (
            lambda _request, policy, _artifact, _receipt: policy.update(
                {"ohlcv_adjustment_semantics": "RAW"}
            ),
            HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY,
        ),
        (
            lambda _request, _policy, artifact, _receipt: artifact["bars"].append(
                deepcopy(artifact["bars"][0])
            ),
            HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE,
        ),
        (
            lambda _request, _policy, artifact, _receipt: artifact["bars"].reverse(),
            HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE,
        ),
        (
            lambda _request, _policy, artifact, _receipt: artifact["bars"][0].update(
                {"low": "102"}
            ),
            HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE,
        ),
        (
            lambda _request, _policy, artifact, _receipt: artifact["bars"][0].update(
                {"open": "0"}
            ),
            HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE,
        ),
        (
            lambda _request, _policy, artifact, _receipt: artifact["bars"][0].update(
                {"open": "NaN"}
            ),
            HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE,
        ),
        (
            lambda _request, _policy, artifact, _receipt: artifact["bars"][0].update(
                {"price_basis": "RAW"}
            ),
            HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY,
        ),
        (
            lambda _request, _policy, artifact, _receipt: artifact["bars"][0].update(
                {"volume": "1.5"}
            ),
            HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE,
        ),
        (
            lambda _request, _policy, artifact, _receipt: artifact["bars"][0].update(
                {"known_at": "2024-01-06T00:00:00Z"}
            ),
            HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE,
        ),
        (
            lambda _request, _policy, artifact, _receipt: artifact["bars"][0].update(
                {"isin": "INE000A01000"}
            ),
            HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE,
        ),
        (
            lambda _request, _policy, artifact, _receipt: artifact["bars"].pop(),
            HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE,
        ),
    ],
)
def test_invalid_request_or_evidence_has_zero_revision_publication(
    tmp_path: Path,
    mutate,
    expected: HistoricalOhlcvImportOutcomeV1,
) -> None:
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs()
    request = json.loads(request_raw)
    policy = json.loads(policy_raw)
    artifact = json.loads(artifact_raw)
    receipt = json.loads(receipt_raw)
    mutate(request, policy, artifact, receipt)
    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(
        *_rebind_source_inputs(request, policy, artifact, receipt)
    )

    assert result.outcome is expected
    assert not (tmp_path / "historical_ohlcv_revisions").exists()
    assert not (tmp_path / ".ingestion.lock").exists()


def test_append_requires_parent_prefix_and_preserves_parent(tmp_path: Path) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    initial = _import(store, _inputs())
    assert initial.revision_sha256 is not None
    append = _import(
        store,
        _inputs(
            sessions=("2024-01-02", "2024-01-03", "2024-01-04"),
            operation="APPEND",
            parent=initial.revision_sha256,
        ),
    )

    assert append.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert append.revision_sha256 != initial.revision_sha256
    parent = store.read_exact(initial.revision_sha256)
    assert parent.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert parent.revision is not None
    assert [bar["session"] for bar in parent.revision["bars"]] == [
        "2024-01-02",
        "2024-01-03",
    ]

    invalid = _import(
        store,
        _inputs(
            sessions=("2024-01-02", "2024-01-04"),
            operation="APPEND",
            parent=initial.revision_sha256,
        ),
    )
    assert invalid.outcome is HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT


def test_correction_requires_named_changed_coordinate_and_keeps_parent_bytes(
    tmp_path: Path,
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    initial = _import(store, _inputs())
    assert initial.revision_sha256 is not None and initial.revision is not None
    changed_bars = [_bar("2024-01-02"), _bar("2024-01-03", close="101")]
    coordinate = {"isin": "INE002A01018", "exchange": "NSE", "session": "2024-01-03"}
    correction = _import(
        store,
        _inputs(
            operation="CORRECTION",
            parent=initial.revision_sha256,
            correction_coordinates=[coordinate],
            bars=changed_bars,
        ),
    )

    assert correction.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert correction.revision_sha256 != initial.revision_sha256
    assert store.read_exact(initial.revision_sha256).revision == initial.revision
    unchanged = _import(
        store,
        _inputs(
            operation="CORRECTION",
            parent=initial.revision_sha256,
            correction_coordinates=[coordinate],
        ),
    )
    assert unchanged.outcome is HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT


def test_cli_import_and_exact_read_share_the_revision_store_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request, policy, artifact, receipt = _inputs()
    files = {
        "request.json": request,
        "policy.json": policy,
        "artifact.json": artifact,
        "receipt.json": receipt,
    }
    for name, raw in files.items():
        (tmp_path / name).write_bytes(raw)
    storage_root = tmp_path / "storage"
    storage_root.mkdir(mode=0o700)

    assert (
        cli.main(
            [
                "historical-ohlcv-import",
                "--request-file",
                str(tmp_path / "request.json"),
                "--source-policy-file",
                str(tmp_path / "policy.json"),
                "--source-artifact-file",
                str(tmp_path / "artifact.json"),
                "--receipt-file",
                str(tmp_path / "receipt.json"),
                "--storage-root",
                str(storage_root),
                "--output",
                "json",
            ]
        )
        == 0
    )
    imported = json.loads(capsys.readouterr().out)
    revision = imported["revision_sha256"]
    assert imported["outcome"] == "SUCCESS"
    assert "source_artifact" not in imported

    assert (
        cli.main(
            [
                "historical-ohlcv-read",
                "--revision-sha256",
                revision,
                "--storage-root",
                str(storage_root),
                "--output",
                "json",
            ]
        )
        == 0
    )
    read = json.loads(capsys.readouterr().out)
    assert read["outcome"] == "SUCCESS"
    assert read["revision_sha256"] == revision


def test_read_fails_closed_when_published_revision_bytes_are_divergent(
    tmp_path: Path,
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    stored = _import(store, _inputs())
    assert stored.revision_sha256 is not None
    revision_path = (
        tmp_path
        / "historical_ohlcv_revisions"
        / "v1"
        / "revisions"
        / f"{stored.revision_sha256}.json"
    )
    revision_path.chmod(0o600)
    revision_path.write_bytes(b"{}")
    revision_path.chmod(0o400)

    assert (
        store.read_exact(stored.revision_sha256).outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )


def test_fifty_member_initial_and_member_major_append_are_accepted(
    tmp_path: Path,
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    members = [_member(number) for number in range(1, 51)]
    initial = _import(
        store,
        _inputs(sessions=("2024-01-02", "2024-01-03"), members=members),
    )
    assert initial.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert initial.revision_sha256 is not None

    appended = _import(
        store,
        _inputs(
            sessions=("2024-01-02", "2024-01-03", "2024-01-04"),
            operation="APPEND",
            parent=initial.revision_sha256,
            members=members,
        ),
    )

    assert appended.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert appended.revision is not None
    assert len(appended.revision["bars"]) == 150
    assert appended.revision["bars"][2]["isin"] == members[0]["isin"]
    assert appended.revision["bars"][3]["isin"] == members[1]["isin"]


def test_correction_rejects_cohort_mapping_or_coordinate_substitution(
    tmp_path: Path,
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    members = [_member(1), _member(2)]
    initial = _import(store, _inputs(members=members))
    assert initial.revision_sha256 is not None
    changed = [
        _bar("2024-01-02", member=members[0]),
        _bar("2024-01-03", member=members[0]),
        _bar("2024-01-02", member=members[1]),
        _bar("2024-01-03", member=members[1], close="100.75"),
    ]
    coordinate = {
        "isin": str(members[1]["isin"]),
        "exchange": "NSE",
        "session": "2024-01-03",
    }
    accepted = _import(
        store,
        _inputs(
            operation="CORRECTION",
            parent=initial.revision_sha256,
            correction_coordinates=[coordinate],
            members=members,
            bars=changed,
        ),
    )
    assert accepted.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS

    substituted = deepcopy(members)
    substituted[1]["provider_mapping"]["mapping_evidence_sha256"] = _digest(  # type: ignore[index]
        b"substituted-mapping"
    )
    rejected = _import(
        store,
        _inputs(
            operation="CORRECTION",
            parent=initial.revision_sha256,
            correction_coordinates=[coordinate],
            members=substituted,
            bars=changed,
        ),
    )
    assert rejected.outcome is HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT


@pytest.mark.parametrize(
    "field",
    (
        "schedule_evidence_sha256",
        "schema_identity_sha256",
        "runtime_code_identity_sha256",
        "configuration_identity_sha256",
    ),
)
def test_request_identity_labels_must_match_closed_preimages(
    tmp_path: Path, field: str
) -> None:
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs()
    request = json.loads(request_raw)
    request[field] = _digest(b"caller-label")

    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(
        _canonical(request), policy_raw, artifact_raw, receipt_raw
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT
    assert not (tmp_path / "historical_ohlcv_revisions").exists()
    assert not (tmp_path / ".ingestion.lock").exists()


@pytest.mark.parametrize(
    "raw",
    (
        b"{} ",
        b'{"operation":"INITIAL","operation":"INITIAL"}',
        b'{"nested":' + b"[" * 65 + b"0" + b"]" * 65 + b"}",
        b"[]",
    ),
)
def test_hostile_request_json_is_typed_and_effect_free(
    tmp_path: Path, raw: bytes
) -> None:
    _, policy_raw, artifact_raw, receipt_raw = _inputs()

    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(
        raw, policy_raw, artifact_raw, receipt_raw
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT
    assert not (tmp_path / "historical_ohlcv_revisions").exists()
    assert not (tmp_path / ".ingestion.lock").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("operation", {}),
        ("operation", []),
        ("contract_version", {}),
        ("research_scope", []),
        ("limits", []),
        ("from_session", {}),
        ("expected_sessions", {}),
        ("cohort", {}),
        ("correction_coordinates", {}),
    ),
)
def test_wrong_request_primitives_are_typed_and_effect_free(
    tmp_path: Path, field: str, value: object
) -> None:
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs()
    request = json.loads(request_raw)
    request[field] = value

    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(
        _canonical(request), policy_raw, artifact_raw, receipt_raw
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT
    _assert_no_storage_effect(tmp_path)


@pytest.mark.parametrize(
    "mapping_effective_to",
    ("not-a-date", "2024-02-30", {}, [], True, 1),
)
def test_non_null_malformed_mapping_effective_to_is_typed_and_effect_free(
    tmp_path: Path, mapping_effective_to: object
) -> None:
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs()
    request = json.loads(request_raw)
    request["cohort"][0]["provider_mapping"]["mapping_effective_to"] = (
        mapping_effective_to
    )

    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(
        _canonical(request), policy_raw, artifact_raw, receipt_raw
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT
    _assert_no_storage_effect(tmp_path)


def test_source_cross_reference_and_future_known_are_invalid_evidence(
    tmp_path: Path,
) -> None:
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs()
    request = json.loads(request_raw)
    policy = json.loads(policy_raw)
    artifact = json.loads(artifact_raw)
    receipt = json.loads(receipt_raw)
    receipt["known_at"] = "2024-01-06T00:00:00Z"
    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(
        *_rebind_source_inputs(request, policy, artifact, receipt)
    )
    assert result.outcome is HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE
    assert not (tmp_path / "historical_ohlcv_revisions").exists()
    assert not (tmp_path / ".ingestion.lock").exists()


def test_readback_rejects_forged_missing_disclosure_and_source_reference(
    tmp_path: Path,
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    stored = _import(store, _inputs())
    assert stored.revision is not None and stored.revision_sha256 is not None
    forged = deepcopy(stored.revision)
    forged["limitation"] = "MISSING"
    forged.pop("revision_sha256")
    forged_id = _digest(_canonical(forged))
    forged["revision_sha256"] = forged_id
    revision_path = (
        tmp_path
        / "historical_ohlcv_revisions"
        / "v1"
        / "revisions"
        / f"{forged_id}.json"
    )
    revision_path.write_bytes(_canonical(forged))
    revision_path.chmod(0o400)

    assert (
        store.read_exact(forged_id).outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )


def test_store_rejects_group_accessible_root(tmp_path: Path) -> None:
    tmp_path.chmod(0o755)
    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(*_inputs())
    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )


def test_cli_rejects_fifo_without_storage_effect(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, policy, artifact, receipt = _inputs()
    for name, raw in {
        "policy.json": policy,
        "artifact.json": artifact,
        "receipt.json": receipt,
    }.items():
        (tmp_path / name).write_bytes(raw)
    fifo = tmp_path / "request.fifo"
    os.mkfifo(fifo)

    exit_code = cli.main(
        [
            "historical-ohlcv-import",
            "--request-file",
            str(fifo),
            "--source-policy-file",
            str(tmp_path / "policy.json"),
            "--source-artifact-file",
            str(tmp_path / "artifact.json"),
            "--receipt-file",
            str(tmp_path / "receipt.json"),
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ]
    )

    assert exit_code == 2
    assert capsys.readouterr().out == ""
    assert not (tmp_path / "historical_ohlcv_revisions").exists()
    assert not (tmp_path / ".ingestion.lock").exists()


def _historical_root_file_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mode & 0o777)
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize(
    "inside_file",
    ("request.json", "policy.json", "artifact.json", "receipt.json"),
)
@pytest.mark.parametrize("state", ("initial", "append", "replay"))
def test_cli_rejects_storage_contained_import_inputs_before_domain_effect(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    inside_file: str,
    state: str,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir(mode=0o700)
    if state == "initial":
        inputs = _inputs()
    else:
        store = HistoricalOhlcvRevisionStoreV1(storage_root)
        parent = _import(store, _inputs())
        assert parent.revision_sha256 is not None
        inputs = (
            _inputs(
                sessions=("2024-01-02", "2024-01-03", "2024-01-04"),
                operation="APPEND",
                parent=parent.revision_sha256,
            )
            if state == "append"
            else _inputs()
        )
    names = ("request.json", "policy.json", "artifact.json", "receipt.json")
    external = tmp_path / "external"
    external.mkdir(mode=0o700)
    paths: dict[str, Path] = {}
    for name, raw in zip(names, inputs, strict=True):
        directory = storage_root if name == inside_file else external
        path = directory / name
        path.write_bytes(raw)
        paths[name] = path
    before = _historical_root_file_snapshot(storage_root)
    invoked = False

    def reject_domain_effect(
        _self: HistoricalOhlcvRevisionStoreV1, *_args: object
    ) -> HistoricalOhlcvImportResultV1:
        nonlocal invoked
        invoked = True
        raise AssertionError("contained input reached revision store")

    monkeypatch.setattr(
        HistoricalOhlcvRevisionStoreV1, "import_exact", reject_domain_effect
    )
    exit_code = cli.main(
        [
            "historical-ohlcv-import",
            "--request-file",
            str(paths["request.json"]),
            "--source-policy-file",
            str(paths["policy.json"]),
            "--source-artifact-file",
            str(paths["artifact.json"]),
            "--receipt-file",
            str(paths["receipt.json"]),
            "--storage-root",
            str(storage_root),
            "--output",
            "json",
        ]
    )

    assert exit_code == 2
    assert capsys.readouterr().out == ""
    assert not invoked
    assert _historical_root_file_snapshot(storage_root) == before
    if state == "initial":
        assert not (storage_root / ".ingestion.lock").exists()
        assert not (storage_root / "historical_ohlcv_revisions").exists()


def test_cli_rejects_contained_input_under_unsafe_storage_root_without_effect(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_root = tmp_path / "unsafe-storage"
    storage_root.mkdir(mode=0o755)
    inputs = _inputs()
    external = tmp_path / "external"
    external.mkdir(mode=0o700)
    names = ("request.json", "policy.json", "artifact.json", "receipt.json")
    paths: dict[str, Path] = {}
    for name, raw in zip(names, inputs, strict=True):
        path = (storage_root if name == "request.json" else external) / name
        path.write_bytes(raw)
        paths[name] = path
    invoked = False

    def reject_domain_effect(
        _self: HistoricalOhlcvRevisionStoreV1, *_args: object
    ) -> HistoricalOhlcvImportResultV1:
        nonlocal invoked
        invoked = True
        raise AssertionError("unsafe root reached revision store")

    monkeypatch.setattr(
        HistoricalOhlcvRevisionStoreV1, "import_exact", reject_domain_effect
    )
    exit_code = cli.main(
        [
            "historical-ohlcv-import",
            "--request-file",
            str(paths["request.json"]),
            "--source-policy-file",
            str(paths["policy.json"]),
            "--source-artifact-file",
            str(paths["artifact.json"]),
            "--receipt-file",
            str(paths["receipt.json"]),
            "--storage-root",
            str(storage_root),
            "--output",
            "json",
        ]
    )

    assert exit_code == 2
    assert capsys.readouterr().out == ""
    assert not invoked
    assert not (storage_root / ".ingestion.lock").exists()
    assert not (storage_root / "historical_ohlcv_revisions").exists()


def test_cli_rejects_symlinked_input_component_before_domain_effect(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_root = tmp_path / "storage"
    storage_root.mkdir(mode=0o700)
    external = tmp_path / "external"
    external.mkdir(mode=0o700)
    request, policy, artifact, receipt = _inputs()
    for name, raw in {
        "request.json": request,
        "policy.json": policy,
        "artifact.json": artifact,
        "receipt.json": receipt,
    }.items():
        (external / name).write_bytes(raw)
    linked = tmp_path / "linked-external"
    linked.symlink_to(external, target_is_directory=True)
    invoked = False

    def reject_domain_effect(
        _self: HistoricalOhlcvRevisionStoreV1, *_args: object
    ) -> HistoricalOhlcvImportResultV1:
        nonlocal invoked
        invoked = True
        raise AssertionError("symlinked input reached revision store")

    monkeypatch.setattr(
        HistoricalOhlcvRevisionStoreV1, "import_exact", reject_domain_effect
    )
    exit_code = cli.main(
        [
            "historical-ohlcv-import",
            "--request-file",
            str(linked / "request.json"),
            "--source-policy-file",
            str(external / "policy.json"),
            "--source-artifact-file",
            str(external / "artifact.json"),
            "--receipt-file",
            str(external / "receipt.json"),
            "--storage-root",
            str(storage_root),
            "--output",
            "json",
        ]
    )

    assert exit_code == 2
    assert capsys.readouterr().out == ""
    assert not invoked
    assert not (storage_root / ".ingestion.lock").exists()
    assert not (storage_root / "historical_ohlcv_revisions").exists()


def test_append_rejects_overlap_reorder_and_member_coordinate_changes(
    tmp_path: Path,
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    members = [_member(1), _member(2)]
    initial = _import(store, _inputs(members=members))
    for sessions, bars, expected in (
        (
            ("2024-01-02", "2024-01-03"),
            None,
            HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT,
        ),
        (
            ("2024-01-03", "2024-01-02", "2024-01-04"),
            None,
            HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT,
        ),
        (
            ("2024-01-02", "2024-01-03", "2024-01-04"),
            [
                _bar("2024-01-02", member=members[0], close="100.75"),
                _bar("2024-01-03", member=members[0]),
                _bar("2024-01-04", member=members[0]),
                _bar("2024-01-02", member=members[1]),
                _bar("2024-01-03", member=members[1]),
                _bar("2024-01-04", member=members[1]),
            ],
            HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT,
        ),
    ):
        result = _import(
            store,
            _inputs(
                sessions=sessions,
                operation="APPEND",
                parent=initial.revision_sha256,
                members=members,
                bars=bars,
            ),
        )
        assert result.outcome is expected


def test_correction_rejects_unclaimed_coordinate_difference(tmp_path: Path) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    initial = _import(store, _inputs())
    assert initial.revision_sha256 is not None
    coordinate = {"isin": "INE002A01018", "exchange": "NSE", "session": "2024-01-03"}
    bars = [_bar("2024-01-02", close="100.75"), _bar("2024-01-03", close="100.75")]

    result = _import(
        store,
        _inputs(
            operation="CORRECTION",
            parent=initial.revision_sha256,
            correction_coordinates=[coordinate],
            bars=bars,
        ),
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT


def test_unbounded_precision_decimal_is_canonical_without_context_rounding(
    tmp_path: Path,
) -> None:
    exact = "123456789012345678901234567890.123456789"
    bar = _bar("2024-01-02", close=exact)
    bar.update({"open": exact, "high": exact, "low": exact})

    result = _import(
        HistoricalOhlcvRevisionStoreV1(tmp_path),
        _inputs(sessions=("2024-01-02",), bars=[bar]),
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert result.revision is not None
    assert result.revision["bars"][0]["close"] == exact


def test_lineage_ceiling_is_enforced_before_publication(tmp_path: Path) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    sessions = ["2024-01-02"]
    parent = _import(store, _inputs(sessions=tuple(sessions)))
    assert parent.revision_sha256 is not None
    current = date.fromisoformat(sessions[-1])
    for _ in range(128):
        current += timedelta(days=1)
        sessions.append(current.isoformat())
        parent = _import(
            store,
            _inputs(
                sessions=tuple(sessions),
                operation="APPEND",
                parent=parent.revision_sha256,
            ),
        )
        assert parent.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
        assert parent.revision_sha256 is not None
    current += timedelta(days=1)
    rejected = _import(
        store,
        _inputs(
            sessions=(*sessions, current.isoformat()),
            operation="APPEND",
            parent=parent.revision_sha256,
        ),
    )
    assert rejected.outcome is HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT


@pytest.mark.parametrize(
    ("request_raw", "source_policy_path", "expected_exit", "expected_outcome"),
    (
        (b"{}", "policy.json", 1, "MALFORMED_INPUT"),
        (None, "/dev/null", 2, None),
    ),
)
def test_cli_negative_inputs_are_bounded_and_effect_free(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    request_raw: bytes | None,
    source_policy_path: str,
    expected_exit: int,
    expected_outcome: str | None,
) -> None:
    request, policy, artifact, receipt = _inputs()
    external = tmp_path / "external"
    external.mkdir(mode=0o700)
    storage_root = tmp_path / "storage"
    storage_root.mkdir(mode=0o700)
    request_path = external / "request.json"
    request_path.write_bytes(request if request_raw is None else request_raw)
    for name, raw in {
        "policy.json": policy,
        "artifact.json": artifact,
        "receipt.json": receipt,
    }.items():
        (external / name).write_bytes(raw)
    policy_path = (
        Path(source_policy_path)
        if source_policy_path.startswith("/")
        else external / source_policy_path
    )

    exit_code = cli.main(
        [
            "historical-ohlcv-import",
            "--request-file",
            str(request_path),
            "--source-policy-file",
            str(policy_path),
            "--source-artifact-file",
            str(external / "artifact.json"),
            "--receipt-file",
            str(external / "receipt.json"),
            "--storage-root",
            str(storage_root),
            "--output",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == expected_exit
    if expected_outcome is None:
        assert captured.out == ""
        assert "invalid historical-ohlcv-import request" in captured.err
    else:
        assert json.loads(captured.out)["outcome"] == expected_outcome
    assert not (storage_root / "historical_ohlcv_revisions").exists()
    assert not (storage_root / ".ingestion.lock").exists()


def test_existing_revision_with_missing_source_is_not_repaired(
    tmp_path: Path,
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    inputs = _inputs()
    stored = _import(store, inputs)
    assert stored.revision is not None
    source_policy = (
        tmp_path
        / "historical_ohlcv_revisions"
        / "v1"
        / "objects"
        / str(stored.revision["source_policy_sha256"])
    )
    source_policy.unlink()

    replay = _import(store, inputs)

    assert (
        replay.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert not source_policy.exists()


def test_readback_revalidates_retained_source_policy_semantics(tmp_path: Path) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    inputs = _inputs()
    stored = _import(store, inputs)
    assert stored.revision is not None
    _, policy_raw, _, receipt_raw = inputs
    policy = json.loads(policy_raw)
    receipt = json.loads(receipt_raw)
    policy["permitted_use"] = "PUBLIC_RESEARCH"
    forged_policy = _canonical(policy)
    receipt["source_policy_sha256"] = _digest(forged_policy)
    forged_receipt = _canonical(receipt)
    forged = deepcopy(stored.revision)
    forged["source_policy_sha256"] = _digest(forged_policy)
    forged["receipt_sha256"] = _digest(forged_receipt)
    request = {
        field: forged[field]
        for field in (
            "contract_version",
            "research_scope",
            "operation",
            "parent_revision_sha256",
            "correction_coordinates",
            "cohort",
            "from_session",
            "to_session",
            "expected_sessions",
            "schedule_evidence_sha256",
            "source_policy_sha256",
            "source_artifact_sha256",
            "receipt_sha256",
            "acquired_at",
            "known_at_cutoff",
            "permitted_use",
            "price_basis",
            "schema_identity_sha256",
            "runtime_code_identity_sha256",
            "configuration_identity_sha256",
        )
    }
    request["interval"] = "1d"
    request["limits"] = historical_revision_store._LIMITS  # pyright: ignore[reportPrivateUsage]
    forged["request_identity_sha256"] = _digest(_canonical(request))
    forged.pop("revision_sha256")
    forged_id = _digest(_canonical(forged))
    forged["revision_sha256"] = forged_id
    objects = tmp_path / "historical_ohlcv_revisions" / "v1" / "objects"
    for digest, raw in (
        (forged["source_policy_sha256"], forged_policy),
        (forged["receipt_sha256"], forged_receipt),
    ):
        path = objects / str(digest)
        path.write_bytes(raw)
        path.chmod(0o400)
    revision_path = (
        tmp_path
        / "historical_ohlcv_revisions"
        / "v1"
        / "revisions"
        / f"{forged_id}.json"
    )
    revision_path.write_bytes(_canonical(forged))
    revision_path.chmod(0o400)

    assert (
        store.read_exact(forged_id).outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )


def _assert_no_storage_effect(root: Path) -> None:
    assert not (root / ".ingestion.lock").exists()
    assert not (root / "historical_ohlcv_revisions").exists()


def test_loaded_runtime_identity_is_pinned_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = historical_revision_store._required_identities()  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(
        historical_revision_store,
        "runtime_source_sha256",
        lambda *_args: (_ for _ in ()).throw(ValueError),
    )

    assert historical_revision_store._required_identities() == expected  # pyright: ignore[reportPrivateUsage]


def test_runtime_identity_failure_never_mints_empty_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        historical_revision_store,
        "runtime_source_sha256",
        lambda *_args: (_ for _ in ()).throw(ValueError),
    )

    with pytest.raises(
        ValueError, match="historical revision runtime identity invalid"
    ):
        historical_revision_store._loaded_runtime_code_identity()  # pyright: ignore[reportPrivateUsage]


def test_historical_readback_accepts_prior_runtime_identity_and_successor_binds_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity_a = _digest(b"runtime-a")
    identity_b = _digest(b"runtime-b")
    monkeypatch.setattr(
        historical_revision_store,
        "_LOADED_RUNTIME_CODE_IDENTITY_SHA256",
        identity_a,
    )
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    parent = _import(store, _inputs())
    assert parent.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert parent.revision is not None and parent.revision_sha256 is not None
    parent_path = (
        tmp_path
        / "historical_ohlcv_revisions"
        / "v1"
        / "revisions"
        / f"{parent.revision_sha256}.json"
    )
    parent_bytes = parent_path.read_bytes()

    monkeypatch.setattr(
        historical_revision_store,
        "_LOADED_RUNTIME_CODE_IDENTITY_SHA256",
        identity_b,
    )
    child = _import(
        store,
        _inputs(
            sessions=("2024-01-02", "2024-01-03", "2024-01-04"),
            operation="APPEND",
            parent=parent.revision_sha256,
        ),
    )

    assert (
        store.read_exact(parent.revision_sha256).outcome
        is HistoricalOhlcvImportOutcomeV1.SUCCESS
    )
    assert parent_path.read_bytes() == parent_bytes
    assert child.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert child.revision is not None
    assert parent.revision["runtime_code_identity_sha256"] == identity_a
    assert child.revision["runtime_code_identity_sha256"] == identity_b


def test_revision_retains_complete_request_projection(tmp_path: Path) -> None:
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs()
    request = json.loads(request_raw)
    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(
        request_raw, policy_raw, artifact_raw, receipt_raw
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert result.revision is not None
    assert {
        field: result.revision[field]
        for field in historical_revision_store._REQUEST_FIELDS  # pyright: ignore[reportPrivateUsage]
    } == request
    assert result.revision["request_identity_sha256"] == _digest(_canonical(request))


def test_schema_and_configuration_preimages_are_complete_and_sensitive() -> None:
    for metadata in (
        historical_revision_store._SCHEMA_IDENTITY_PREIMAGE,  # pyright: ignore[reportPrivateUsage]
        historical_revision_store._CONFIGURATION_IDENTITY_PREIMAGE,  # pyright: ignore[reportPrivateUsage]
    ):
        changed = deepcopy(metadata)
        changed["metadata_version"] = f"{changed['metadata_version']}-changed"
        assert _digest(_canonical(changed)) != _digest(_canonical(metadata))
    schema = historical_revision_store._SCHEMA_IDENTITY_PREIMAGE  # pyright: ignore[reportPrivateUsage]
    assert {
        "canonical_json",
        "scalar_types",
        "objects",
        "identity_preimages",
        "cross_object_invariants",
        "failure_grammar",
    } <= set(schema)
    assert {
        "HistoricalOhlcvRevisionV1",
        "LimitsV1",
        "ScheduleIdentityPreimageV1",
    } <= set(schema["objects"])


@pytest.mark.parametrize(
    ("mutate", "expected"),
    (
        (
            lambda request, _policy, _artifact, _receipt: request.update(
                {"price_basis": "RAW"}
            ),
            HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY,
        ),
        (
            lambda request, _policy, artifact, _receipt: (
                request.update({"price_basis": "RAW"}),
                artifact["bars"][1].update({"open": 100}),
            ),
            HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT,
        ),
        (
            lambda request, _policy, _artifact, receipt: (
                request.update({"price_basis": "RAW"}),
                receipt.update({"known_at": "2024-01-06T00:00:00Z"}),
            ),
            HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY,
        ),
        (
            lambda _request, policy, artifact, _receipt: (
                policy.update({"ohlcv_adjustment_semantics": "RAW"}),
                artifact["bars"][1].update({"open": "0"}),
            ),
            HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY,
        ),
    ),
)
def test_whole_candidate_failure_precedence(
    tmp_path: Path, mutate, expected: HistoricalOhlcvImportOutcomeV1
) -> None:
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs()
    request = json.loads(request_raw)
    policy = json.loads(policy_raw)
    artifact = json.loads(artifact_raw)
    receipt = json.loads(receipt_raw)
    mutate(request, policy, artifact, receipt)
    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(
        *_rebind_source_inputs(request, policy, artifact, receipt)
    )

    assert result.outcome is expected
    _assert_no_storage_effect(tmp_path)


@pytest.mark.parametrize(
    "field",
    ("source_policy_sha256", "source_artifact_sha256", "receipt_sha256"),
)
def test_request_source_digest_mismatches_are_invalid_evidence(
    tmp_path: Path, field: str
) -> None:
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs()
    request = json.loads(request_raw)
    request[field] = _digest(b"other")

    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(
        _canonical(request), policy_raw, artifact_raw, receipt_raw
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE
    _assert_no_storage_effect(tmp_path)


@pytest.mark.parametrize(
    "raw",
    (
        b"{} ",
        b'{"schema_version":"a","schema_version":"a"}',
        b"[]",
        b"",
    ),
)
def test_hostile_source_json_is_malformed_and_effect_free(
    tmp_path: Path, raw: bytes
) -> None:
    request, policy, artifact, receipt = _inputs()

    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(
        request, raw, artifact, receipt
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT
    _assert_no_storage_effect(tmp_path)


def test_first_initial_uses_private_empty_atomic_acquisition(tmp_path: Path) -> None:
    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(*_inputs())

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    lock = tmp_path / ".ingestion.lock"
    assert lock.is_file()
    assert lock.stat().st_mode & 0o777 == 0o600


def test_group_accessible_root_has_no_lease_effect(tmp_path: Path) -> None:
    tmp_path.chmod(0o755)

    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(*_inputs())

    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    _assert_no_storage_effect(tmp_path)


@pytest.mark.parametrize(
    ("mutate", "expected"),
    (
        (
            lambda request, policy, _artifact, _receipt: (
                request.update({"price_basis": "RAW"}),
                policy.pop("source_name"),
            ),
            HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT,
        ),
        (
            lambda _request, _policy, artifact, _receipt: (
                artifact["bars"][0].update({"price_basis": "RAW"}),
                artifact["bars"][1].update({"open": 100}),
            ),
            HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT,
        ),
        (
            lambda _request, _policy, artifact, _receipt: (
                artifact["bars"][0].update({"open": "0"}),
                artifact["bars"][1].update({"price_basis": "RAW"}),
            ),
            HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY,
        ),
        (
            lambda request, _policy, artifact, _receipt: (
                request.update(
                    {
                        "operation": "CORRECTION",
                        "parent_revision_sha256": _digest(b"missing-parent"),
                        "correction_coordinates": [],
                    }
                ),
                artifact["bars"].pop(),
            ),
            HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE,
        ),
        (
            lambda request, _policy, _artifact, _receipt: request.update(
                {
                    "operation": "CORRECTION",
                    "parent_revision_sha256": _digest(b"missing-parent"),
                    "correction_coordinates": [],
                }
            ),
            HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT,
        ),
    ),
)
def test_remaining_whole_candidate_failure_precedence(
    tmp_path: Path, mutate, expected: HistoricalOhlcvImportOutcomeV1
) -> None:
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs()
    request = json.loads(request_raw)
    policy = json.loads(policy_raw)
    artifact = json.loads(artifact_raw)
    receipt = json.loads(receipt_raw)
    mutate(request, policy, artifact, receipt)

    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(
        *_rebind_source_inputs(request, policy, artifact, receipt)
    )

    assert result.outcome is expected
    _assert_no_storage_effect(tmp_path)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda policy, receipt: policy.update({"artifact_sha256": _digest(b"other")}),
        lambda policy, receipt: receipt.update(
            {"source_policy_sha256": _digest(b"other")}
        ),
        lambda policy, receipt: receipt.update(
            {"source_artifact_sha256": _digest(b"other")}
        ),
        lambda policy, receipt: receipt.update({"acquired_at": "2024-01-03T00:00:00Z"}),
        lambda policy, receipt: receipt.update({"known_at": "2024-01-06T00:00:00Z"}),
        lambda policy, receipt: receipt.update({"permitted_use": "PUBLIC_RESEARCH"}),
        lambda policy, receipt: receipt.update({"ohlcv_adjustment_semantics": "RAW"}),
    ),
)
def test_policy_and_receipt_cross_reference_failures(tmp_path: Path, mutate) -> None:
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs()
    request = json.loads(request_raw)
    policy = json.loads(policy_raw)
    artifact = json.loads(artifact_raw)
    receipt = json.loads(receipt_raw)
    mutate(policy, receipt)
    expected = (
        HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY
        if (
            policy["permitted_use"] != "OWNER_PRIVATE_RESEARCH"
            or receipt["permitted_use"] != "OWNER_PRIVATE_RESEARCH"
            or policy["ohlcv_adjustment_semantics"]
            != "SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED"
            or receipt["ohlcv_adjustment_semantics"]
            != "SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED"
        )
        else HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE
    )

    artifact_raw = _canonical(artifact)
    policy_raw = _canonical(policy)
    receipt_raw = _canonical(receipt)
    request["source_policy_sha256"] = _digest(policy_raw)
    request["source_artifact_sha256"] = _digest(artifact_raw)
    request["receipt_sha256"] = _digest(receipt_raw)
    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(
        _canonical(request), policy_raw, artifact_raw, receipt_raw
    )

    assert result.outcome is expected
    _assert_no_storage_effect(tmp_path)


def test_iterative_readback_rereads_target_after_lineage_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    initial = _import(store, _inputs())
    assert initial.revision_sha256 is not None
    child = _import(
        store,
        _inputs(
            sessions=("2024-01-02", "2024-01-03", "2024-01-04"),
            operation="APPEND",
            parent=initial.revision_sha256,
        ),
    )
    assert child.revision_sha256 is not None
    calls: list[str] = []
    original = HistoricalOhlcvRevisionStoreV1._validate_stored_revision_local  # pyright: ignore[reportPrivateUsage]

    def track(
        _self: HistoricalOhlcvRevisionStoreV1,
        revision_id: str,
        objects: int,
        revisions: int,
    ) -> dict[str, object]:
        calls.append(revision_id)
        return original(_self, revision_id, objects, revisions)

    monkeypatch.setattr(
        HistoricalOhlcvRevisionStoreV1, "_validate_stored_revision_local", track
    )
    assert (
        store.read_exact(child.revision_sha256).outcome
        is HistoricalOhlcvImportOutcomeV1.SUCCESS
    )
    assert calls.count(child.revision_sha256) == 2
    assert calls.count(initial.revision_sha256) == 1


def test_writer_rejects_root_substitution_after_identity_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    root_a.mkdir(mode=0o700)
    root_b.mkdir(mode=0o700)
    store = HistoricalOhlcvRevisionStoreV1(root_a)
    parent = _import(store, _inputs())
    assert parent.revision_sha256 is not None
    seeded = historical_revision_store.StorageRootLease.try_acquire_private_empty(
        root_b
    )
    assert seeded.lease is not None
    with seeded.lease:
        pass
    admit = historical_revision_store.StorageRootLease.admit_existing_private_identity

    def substitute(root: object) -> tuple[int, int] | None:
        identity = admit(root)
        root_a.rename(tmp_path / "old-root-a")
        root_b.rename(root_a)
        return identity

    monkeypatch.setattr(
        historical_revision_store.StorageRootLease,
        "admit_existing_private_identity",
        substitute,
    )
    lease = store._acquire_writer_lease("APPEND")  # pyright: ignore[reportPrivateUsage]

    assert lease.outcome is historical_revision_store.LeaseOutcome.FAILED
    assert not (root_a / "historical_ohlcv_revisions").exists()


def test_iterative_readback_rejects_cycle_before_repeated_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    request_raw, _, artifact_raw, _ = _inputs(
        sessions=("2024-01-02", "2024-01-03"),
        operation="APPEND",
        parent=_digest(b"parent"),
    )
    request = json.loads(request_raw)
    bars = json.loads(artifact_raw)["bars"]
    target_id = _digest(b"target")
    parent_id = _digest(b"parent")
    child = historical_revision_store._revision_value(  # pyright: ignore[reportPrivateUsage]
        request, bars, 2
    )
    parent = deepcopy(child)
    parent["parent_revision_sha256"] = target_id
    child["parent_revision_sha256"] = parent_id
    values = {target_id: child, parent_id: parent}
    calls: list[str] = []

    def local(
        _self: HistoricalOhlcvRevisionStoreV1,
        revision_id: str,
        _objects: int,
        _revisions: int,
    ) -> dict[str, object]:
        calls.append(revision_id)
        return values[revision_id]

    monkeypatch.setattr(
        HistoricalOhlcvRevisionStoreV1, "_validate_stored_revision_local", local
    )

    with pytest.raises(RuntimeError):
        store._validate_stored_lineage_iterative(  # pyright: ignore[reportPrivateUsage]
            target_id, 0, 0
        )
    assert calls == [target_id, parent_id]


def _nested_json(containers: int) -> bytes:
    value: object = "leaf"
    for _ in range(containers):
        value = {"nested": value}
    return _canonical(value)


@pytest.mark.parametrize(
    ("maximum", "containers", "accepted"),
    (
        (1_048_576, 64, True),
        (1_048_576, 65, False),
        (134_217_728, 64, True),
        (134_217_728, 65, False),
        (1_048_576, 64, True),
        (1_048_576, 65, False),
        (1_048_576, 64, True),
        (1_048_576, 65, False),
    ),
)
def test_closed_json_counts_only_containers_at_exact_depth_limit(
    maximum: int, containers: int, accepted: bool
) -> None:
    raw = _nested_json(containers)

    if accepted:
        assert historical_revision_store._closed_json(  # pyright: ignore[reportPrivateUsage]
            raw, maximum
        )
    else:
        with pytest.raises(ValueError):
            historical_revision_store._closed_json(  # pyright: ignore[reportPrivateUsage]
                raw, maximum
            )


@pytest.mark.parametrize(
    "coordinate",
    (
        {"isin": "!", "exchange": "NSE", "session": "2024-01-02"},
        {"isin": "INE002A01018", "exchange": "BSE", "session": "2024-01-02"},
        {"isin": "INE002A01018", "exchange": "NSE", "session": "not-a-date"},
        {
            "isin": "INE002A01018",
            "exchange": "NSE",
            "session": "2024-01-02",
            "unknown": "field",
        },
    ),
)
def test_malformed_correction_coordinates_precede_parent_lookup(
    tmp_path: Path, coordinate: dict[str, str]
) -> None:
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs(
        operation="CORRECTION",
        parent=_digest(b"missing-parent"),
        correction_coordinates=[coordinate],
    )

    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(
        request_raw, policy_raw, artifact_raw, receipt_raw
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT
    _assert_no_storage_effect(tmp_path)


@pytest.mark.parametrize(
    "coordinates",
    (
        [
            {"isin": "INE002A01018", "exchange": "NSE", "session": "2024-01-02"},
            {"isin": "INE002A01018", "exchange": "NSE", "session": "2024-01-02"},
        ],
        [
            {"isin": "INE002A01018", "exchange": "NSE", "session": "2024-01-03"},
            {"isin": "INE002A01018", "exchange": "NSE", "session": "2024-01-02"},
        ],
    ),
)
def test_correction_coordinates_must_be_strictly_sorted_unique(
    tmp_path: Path, coordinates: list[dict[str, str]]
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    parent = _import(store, _inputs())
    assert parent.revision_sha256 is not None
    bars = [_bar("2024-01-02", close="100.75"), _bar("2024-01-03", close="100.75")]

    result = _import(
        store,
        _inputs(
            operation="CORRECTION",
            parent=parent.revision_sha256,
            correction_coordinates=coordinates,
            bars=bars,
        ),
    )
    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT


def _revision_path(root: Path, revision_id: str) -> Path:
    return (
        root / "historical_ohlcv_revisions" / "v1" / "revisions" / f"{revision_id}.json"
    )


def _write_revision(path: Path, value: dict[str, object]) -> str:
    preimage = deepcopy(value)
    preimage.pop("revision_sha256", None)
    revision_id = _digest(_canonical(preimage))
    value["revision_sha256"] = revision_id
    path = path.with_name(f"{revision_id}.json")
    path.write_bytes(_canonical(value))
    path.chmod(0o400)
    return revision_id


def test_exact_replay_rejects_divergent_existing_revision_bytes(tmp_path: Path) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    inputs = _inputs()
    stored = _import(store, inputs)
    assert stored.revision_sha256 is not None
    path = _revision_path(tmp_path, stored.revision_sha256)
    path.chmod(0o600)
    path.write_bytes(b"{}")
    path.chmod(0o400)

    replay = _import(store, inputs)

    assert (
        replay.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert path.read_bytes() == b"{}"


def test_recursive_grandparent_and_correction_tampering_are_rejected(
    tmp_path: Path,
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    initial = _import(store, _inputs())
    assert initial.revision is not None and initial.revision_sha256 is not None
    appended = _import(
        store,
        _inputs(
            sessions=("2024-01-02", "2024-01-03", "2024-01-04"),
            operation="APPEND",
            parent=initial.revision_sha256,
        ),
    )
    assert appended.revision is not None and appended.revision_sha256 is not None
    target = _import(
        store,
        _inputs(
            sessions=("2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"),
            operation="APPEND",
            parent=appended.revision_sha256,
        ),
    )
    assert target.revision is not None and target.revision_sha256 is not None

    forged_parent = deepcopy(appended.revision)
    forged_parent["from_session"] = "2024-01-01"
    forged_parent["schedule_evidence_sha256"] = (
        historical_revision_store._schedule_identity(  # pyright: ignore[reportPrivateUsage]
            "2024-01-01", "2024-01-04", forged_parent["expected_sessions"]
        )
    )
    request = {
        field: forged_parent[field]
        for field in historical_revision_store._REQUEST_FIELDS  # pyright: ignore[reportPrivateUsage]
    }
    forged_parent["request_identity_sha256"] = _digest(_canonical(request))
    forged_parent_id = _write_revision(
        _revision_path(tmp_path, appended.revision_sha256), forged_parent
    )
    forged_target = deepcopy(target.revision)
    forged_target["parent_revision_sha256"] = forged_parent_id
    request = {
        field: forged_target[field]
        for field in historical_revision_store._REQUEST_FIELDS  # pyright: ignore[reportPrivateUsage]
    }
    forged_target["request_identity_sha256"] = _digest(_canonical(request))
    forged_target_id = _write_revision(
        _revision_path(tmp_path, target.revision_sha256), forged_target
    )

    assert (
        store.read_exact(forged_target_id).outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )


def test_recursive_correction_coordinate_tampering_is_rejected(tmp_path: Path) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    parent = _import(store, _inputs())
    assert parent.revision_sha256 is not None
    correction = _import(
        store,
        _inputs(
            operation="CORRECTION",
            parent=parent.revision_sha256,
            correction_coordinates=[
                {
                    "isin": "INE002A01018",
                    "exchange": "NSE",
                    "session": "2024-01-03",
                }
            ],
            bars=[_bar("2024-01-02"), _bar("2024-01-03", close="100.75")],
        ),
    )
    assert correction.revision is not None and correction.revision_sha256 is not None
    forged = deepcopy(correction.revision)
    forged["correction_coordinates"] = [
        {"isin": "INE002A01018", "exchange": "NSE", "session": "2024-01-02"}
    ]
    request = {
        field: forged[field]
        for field in historical_revision_store._REQUEST_FIELDS  # pyright: ignore[reportPrivateUsage]
    }
    forged["request_identity_sha256"] = _digest(_canonical(request))
    forged_id = _write_revision(
        _revision_path(tmp_path, correction.revision_sha256), forged
    )

    assert (
        store.read_exact(forged_id).outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )


@pytest.mark.parametrize(
    ("input_index", "raw"),
    (
        (1, b'{"schema_version":"a","schema_version":"a"}'),
        (2, b'{"schema_version":1,"bars":[]}'),
        (3, b'{"schema_version":"a","known_at":NaN}'),
        (1, b"[]"),
        (2, b"{}"),
        (3, b"{} "),
        (1, b""),
    ),
)
def test_each_source_input_hostile_shape_is_malformed_before_effect(
    tmp_path: Path, input_index: int, raw: bytes
) -> None:
    inputs = list(_inputs())
    inputs[input_index] = raw

    result = HistoricalOhlcvRevisionStoreV1(tmp_path).import_exact(*inputs)

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT
    _assert_no_storage_effect(tmp_path)


def _scalar_paths(
    value: object, path: tuple[object, ...] = ()
) -> list[tuple[object, ...]]:
    if type(value) is dict:
        return [
            child_path
            for key, child in value.items()
            for child_path in _scalar_paths(child, (*path, key))
        ]
    if type(value) is list:
        return [
            child_path
            for index, child in enumerate(value)
            for child_path in _scalar_paths(child, (*path, index))
        ]
    return [path]


def _replace_scalar(value: object, path: tuple[object, ...]) -> None:
    parent = value
    for item in path[:-1]:
        parent = parent[item]  # type: ignore[index]
    leaf = parent[path[-1]]  # type: ignore[index]
    if type(leaf) is bool:
        parent[path[-1]] = not leaf  # type: ignore[index]
    elif type(leaf) is int:
        parent[path[-1]] = leaf + 1  # type: ignore[index]
    elif type(leaf) is str:
        parent[path[-1]] = f"{leaf} changed"  # type: ignore[index]
    else:
        parent[path[-1]] = "changed"  # type: ignore[index]


def test_schema_and_configuration_metadata_couples_every_leaf_contract() -> None:
    schema = historical_revision_store._SCHEMA_IDENTITY_PREIMAGE  # pyright: ignore[reportPrivateUsage]
    for contract in schema["objects"].values():
        assert set(contract["field_contracts"]) == set(contract["fields"])
    assert set(
        schema["objects"]["HistoricalOhlcvRevisionV1"]["field_contracts"]
    ) == set(historical_revision_store._REVISION_FIELDS)  # pyright: ignore[reportPrivateUsage]
    for metadata in (
        schema,
        historical_revision_store._CONFIGURATION_IDENTITY_PREIMAGE,  # pyright: ignore[reportPrivateUsage]
    ):
        original_digest = _digest(_canonical(metadata))
        for path in _scalar_paths(metadata):
            changed = deepcopy(metadata)
            _replace_scalar(changed, path)
            assert _digest(_canonical(changed)) != original_digest, path


def test_schema_and_configuration_metadata_require_all_blocker_leaves() -> None:
    schema = historical_revision_store._SCHEMA_IDENTITY_PREIMAGE  # pyright: ignore[reportPrivateUsage]
    configuration = historical_revision_store._CONFIGURATION_IDENTITY_PREIMAGE  # pyright: ignore[reportPrivateUsage]
    required_field_contract_leaves = {
        "type",
        "nullable",
        "bounds",
        "literal",
        "literals",
        "ordering",
    }
    for contract in schema["objects"].values():
        for field_contract in contract["field_contracts"].values():
            assert required_field_contract_leaves <= set(field_contract)

    assert schema["canonical_json"]["container_depth"] == {
        "counted_containers": ["object", "list"],
        "scalar_depth_effect": "none",
        "maximum_accepted": 64,
        "first_rejected": 65,
    }
    assert schema["identity_preimages"]["runtime"] == {
        "algorithm": "SHA-256",
        "formula": "runtime_source_sha256(_RUNTIME_SOURCE) at module load",
        "source": "src/swing_trading_ai_assistant/market_data/historical_revision_store.py",
        "mutable_path_read": "never",
    }
    assert (
        schema["objects"]["CorrectionCoordinateV1"]["field_contracts"]["session"][
            "cross_reference"
        ]
        == "candidate full-grid and CORRECTION parent row"
    )
    assert schema["state_transitions"]["APPEND"]["to_session"] == (
        "not before parent inclusive to_session and at or after final expected session; inclusive upper bound may be non-session"
    )
    assert schema["state_transitions"]["APPEND"]["expected_sessions"] == (
        "nonempty strict suffix after exact parent sequence and parent inclusive to_session"
    )
    assert schema["cross_object_invariants"][4] == (
        "APPEND digest parent, empty corrections, contiguous suffix strictly after parent inclusive upper range, parent preservation"
    )
    assert schema["state_transitions"]["CORRECTION"]["coordinates"] == (
        "nonempty sorted unique candidate full-grid coordinates"
    )
    assert schema["state_transitions"]["CORRECTION"]["mutable_fields"] == [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "known_at",
    ]
    assert schema["state_transitions"]["INITIAL"]["existing_root"] == (
        "identity-pinned exact readable candidate replay only"
    )
    assert configuration["storage_authority"] == {
        "lease_name": ".ingestion.lock",
        "lease_mode": 0o600,
        "visible_directory_mode": 0o700,
        "visible_file_mode": 0o400,
        "path_resolution": "no-follow",
        "initial_existing_root": "identity-pinned exact replay only",
        "cli_admitted_root_identity": "required for supplied domain read/write authority",
    }
    assert configuration["durability"] == {
        "file_fsync_before_link": True,
        "parent_directory_fsync_after_link_or_exact_existing": True,
        "existing_directory_retry_parent_fsync": True,
        "existing_directory_parent_fsync_before_open": True,
        "initial_exact_replay_hierarchy_parent_fsync": True,
        "sibling_directory_failure_closes_open_descriptors": True,
        "exact_readback_after_publication": True,
        "uncertainty_on_cleanup_or_fsync_or_readback_failure": True,
    }


@pytest.mark.parametrize(
    "field", ("source_policy_sha256", "source_artifact_sha256", "receipt_sha256")
)
def test_readback_rejects_independent_source_reference_substitution(
    tmp_path: Path, field: str
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    stored = _import(store, _inputs())
    assert stored.revision is not None and stored.revision_sha256 is not None
    _, policy_raw, artifact_raw, receipt_raw = _inputs()
    policy = json.loads(policy_raw)
    artifact = json.loads(artifact_raw)
    receipt = json.loads(receipt_raw)
    if field == "source_policy_sha256":
        policy["source_name"] = "independent-policy"
        replacement = _canonical(policy)
    elif field == "source_artifact_sha256":
        artifact["bars"][0]["close"] = "100.75"
        replacement = _canonical(artifact)
    else:
        receipt["source_policy_sha256"] = _digest(b"independent-policy")
        replacement = _canonical(receipt)
    replacement_id = _digest(replacement)
    objects = tmp_path / "historical_ohlcv_revisions" / "v1" / "objects"
    replacement_path = objects / replacement_id
    replacement_path.write_bytes(replacement)
    replacement_path.chmod(0o400)
    forged = deepcopy(stored.revision)
    forged[field] = replacement_id
    request = {
        name: forged[name]
        for name in historical_revision_store._REQUEST_FIELDS  # pyright: ignore[reportPrivateUsage]
    }
    forged["request_identity_sha256"] = _digest(_canonical(request))
    forged_id = _write_revision(
        _revision_path(tmp_path, stored.revision_sha256), forged
    )

    assert (
        store.read_exact(forged_id).outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )


@pytest.mark.parametrize("source_index", (1, 2, 3))
@pytest.mark.parametrize(
    "raw",
    (
        b'{"schema_version":"a","schema_version":"a"}',
        b'{"schema_version":1.5}',
        b'{"schema_version":NaN}',
        _nested_json(65),
        b"[]",
        b'{"schema_version":"a"}',
        b'{"schema_version":"a","unknown":"field"}',
        b'{"schema_version":1}',
        b"{} ",
        b"",
    ),
)
def test_each_source_json_boundary_rejects_every_hostile_class(
    source_index: int, raw: bytes
) -> None:
    inputs = list(_inputs())
    inputs[source_index] = raw

    assert (
        historical_revision_store._parse_source_structure(  # pyright: ignore[reportPrivateUsage]
            inputs[1], inputs[2], inputs[3]
        )
        is None
    )


@pytest.mark.parametrize("source_index", (1, 2, 3))
def test_each_source_json_boundary_rejects_oversize_bytes(
    monkeypatch: pytest.MonkeyPatch, source_index: int
) -> None:
    inputs = list(_inputs())
    maximum_key = (
        "max_source_policy_bytes"
        if source_index == 1
        else "max_artifact_bytes"
        if source_index == 2
        else "max_receipt_bytes"
    )
    limited = dict(historical_revision_store._LIMITS)  # pyright: ignore[reportPrivateUsage]
    limited[maximum_key] = len(inputs[source_index]) - 1
    monkeypatch.setattr(historical_revision_store, "_LIMITS", limited)

    assert (
        historical_revision_store._parse_source_structure(  # pyright: ignore[reportPrivateUsage]
            inputs[1], inputs[2], inputs[3]
        )
        is None
    )


def test_iterative_lineage_rejects_depth_129_before_next_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    request = json.loads(_inputs()[0])
    identifiers = [_digest(str(index).encode()) for index in range(130)]
    values: dict[str, dict[str, object]] = {}
    for index, revision_id in enumerate(identifiers):
        value = dict(request)
        value.update(
            {
                "operation": "APPEND",
                "parent_revision_sha256": identifiers[index + 1]
                if index + 1 < len(identifiers)
                else _digest(b"unread"),
                "correction_coordinates": [],
                "request_identity_sha256": _digest(_canonical(request)),
                "lineage_depth": 1,
                "context_status": "HISTORICAL_CONTEXT_NOT_EVALUATED",
                "limitation": "FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION",
                "bars": [],
                "revision_sha256": revision_id,
            }
        )
        values[revision_id] = value
    calls: list[str] = []

    def local(
        _self: HistoricalOhlcvRevisionStoreV1,
        revision_id: str,
        _objects: int,
        _revisions: int,
    ) -> dict[str, object]:
        calls.append(revision_id)
        return values[revision_id]

    monkeypatch.setattr(
        HistoricalOhlcvRevisionStoreV1, "_validate_stored_revision_local", local
    )
    monkeypatch.setattr(
        historical_revision_store,
        "_validate_transition",
        lambda *_args: (1, HistoricalOhlcvImportOutcomeV1.SUCCESS),
    )

    with pytest.raises(RuntimeError):
        store._validate_stored_lineage_iterative(  # pyright: ignore[reportPrivateUsage]
            identifiers[0], 0, 0
        )

    assert calls == identifiers[:129]


def test_iterative_lineage_retains_at_most_two_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class TrackedRevision(dict[str, object]):
        live = 0
        peak = 0

        def __init__(self, value: dict[str, object]) -> None:
            super().__init__(value)
            type(self).live += 1
            type(self).peak = max(type(self).peak, type(self).live)

        def __del__(self) -> None:
            type(self).live -= 1

    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    request = json.loads(_inputs()[0])
    target_id, parent_id, initial_id = (_digest(item) for item in (b"t", b"p", b"i"))

    def value(
        operation: str, parent: str | None, depth: int, revision_id: str
    ) -> dict[str, object]:
        result = dict(request)
        result.update(
            {
                "operation": operation,
                "parent_revision_sha256": parent,
                "correction_coordinates": [],
                "request_identity_sha256": _digest(_canonical(request)),
                "lineage_depth": depth,
                "context_status": "HISTORICAL_CONTEXT_NOT_EVALUATED",
                "limitation": "FIXED_COHORT_RETROSPECTIVE_SELECTION_SURVIVORSHIP_LIMITATION",
                "bars": [],
                "revision_sha256": revision_id,
            }
        )
        return result

    values = {
        target_id: value("APPEND", parent_id, 1, target_id),
        parent_id: value("APPEND", initial_id, 1, parent_id),
        initial_id: value("INITIAL", None, 0, initial_id),
    }
    monkeypatch.setattr(
        HistoricalOhlcvRevisionStoreV1,
        "_validate_stored_revision_local",
        lambda _self, revision_id, _objects, _revisions: TrackedRevision(
            values[revision_id]
        ),
    )
    monkeypatch.setattr(
        historical_revision_store,
        "_validate_transition",
        lambda *_args: (1, HistoricalOhlcvImportOutcomeV1.SUCCESS),
    )

    assert (
        store._validate_stored_lineage_iterative(  # pyright: ignore[reportPrivateUsage]
            target_id, 0, 0
        )["revision_sha256"]
        == target_id
    )
    assert TrackedRevision.peak <= 2


def test_writer_parent_reverification_uses_iterative_validator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    parent = _import(store, _inputs())
    assert parent.revision_sha256 is not None
    calls = 0
    original = HistoricalOhlcvRevisionStoreV1._validate_stored_lineage_iterative  # pyright: ignore[reportPrivateUsage]

    def track(
        self: HistoricalOhlcvRevisionStoreV1,
        revision_id: str,
        objects: int,
        revisions: int,
    ) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return original(self, revision_id, objects, revisions)

    monkeypatch.setattr(
        HistoricalOhlcvRevisionStoreV1, "_validate_stored_lineage_iterative", track
    )
    result = _import(
        store,
        _inputs(
            sessions=("2024-01-02", "2024-01-03", "2024-01-04"),
            operation="APPEND",
            parent=parent.revision_sha256,
        ),
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert calls >= 3


class _PostLinkFault:
    def __init__(self, target: str, stage: str, source_name: str) -> None:
        self.target = target
        self.stage = stage
        self.source_name = source_name
        self.parent: int | None = None
        self.name: str | None = None
        self.read_count = 0
        self.triggered = False
        self.publish_original = historical_revision_store._publish_object  # pyright: ignore[reportPrivateUsage]
        self.unlink_original = os.unlink
        self.fsync_original = os.fsync
        self.read_original = historical_revision_store._read_object  # pyright: ignore[reportPrivateUsage]

    def publish(self, parent: int, name: str, raw: bytes) -> bool:
        if (
            self.target == "revision"
            and name.endswith(".json")
            or self.target == "source"
            and name == self.source_name
        ):
            self.parent, self.name = parent, name
        return self.publish_original(parent, name, raw)

    def unlink(self, path: str | bytes, *args: object, **kwargs: object) -> None:
        if (
            self.stage == "temp_unlink"
            and not self.triggered
            and self.parent is not None
            and kwargs.get("dir_fd") == self.parent
            and isinstance(path, str)
            and path.startswith(".")
        ):
            self.triggered = True
            raise OSError("injected temporary unlink failure")
        self.unlink_original(path, *args, **kwargs)  # type: ignore[arg-type]

    def fsync(self, descriptor: int) -> None:
        if (
            self.stage == "parent_fsync"
            and not self.triggered
            and self.parent == descriptor
        ):
            self.triggered = True
            raise OSError("injected parent fsync failure")
        self.fsync_original(descriptor)

    def read(self, parent: int, name: str, maximum: int) -> bytes:
        if parent == self.parent and name == self.name:
            self.read_count += 1
            if self.stage == "exact_read" and self.read_count == 2:
                self.triggered = True
                raise OSError("injected exact readback failure")
        return self.read_original(parent, name, maximum)


@pytest.mark.parametrize("target", ("source", "revision"))
@pytest.mark.parametrize("stage", ("temp_unlink", "parent_fsync", "exact_read"))
def test_post_link_publication_failure_replays_exact_or_rejects_partial_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, stage: str
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    inputs = _inputs()
    request = json.loads(inputs[0])
    source_name = str(request["source_policy_sha256"])
    fault = _PostLinkFault(target, stage, source_name)

    with monkeypatch.context() as scoped:
        scoped.setattr(historical_revision_store, "_publish_object", fault.publish)
        if stage == "temp_unlink":
            scoped.setattr(os, "unlink", fault.unlink)
        elif stage == "parent_fsync":
            scoped.setattr(os, "fsync", fault.fsync)
        else:
            scoped.setattr(historical_revision_store, "_read_object", fault.read)
        failed = _import(store, inputs)

    assert fault.triggered
    assert (
        failed.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    objects = tmp_path / "historical_ohlcv_revisions" / "v1" / "objects"
    if target == "source":
        assert (objects / source_name).read_bytes() == inputs[1]
    else:
        revisions = tmp_path / "historical_ohlcv_revisions" / "v1" / "revisions"
        assert len(tuple(revisions.iterdir())) == 1

    replay = _import(store, inputs)

    expected = (
        HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
        if target == "source"
        else HistoricalOhlcvImportOutcomeV1.SUCCESS
    )
    assert replay.outcome is expected
    assert (replay.revision is not None) is (target == "revision")


@pytest.mark.parametrize("target", ("source", "revision"))
def test_exact_retry_fsyncs_every_matching_existing_publication_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    inputs = _inputs()
    initial = _import(store, inputs)
    assert initial.revision_sha256 is not None
    source_name = str(json.loads(inputs[0])["source_policy_sha256"])
    target_parent: int | None = None
    fsync_triggered = False
    original_read = historical_revision_store._read_object  # pyright: ignore[reportPrivateUsage]
    original_fsync = os.fsync

    def read(parent: int, name: str, maximum: int) -> bytes:
        nonlocal target_parent
        if (target == "source" and name == source_name) or (
            target == "revision" and name == f"{initial.revision_sha256}.json"
        ):
            target_parent = parent
        return original_read(parent, name, maximum)

    def fail_matching_parent_fsync(descriptor: int) -> None:
        nonlocal fsync_triggered
        if descriptor == target_parent and not fsync_triggered:
            fsync_triggered = True
            raise OSError("exact existing directory fsync failed")
        original_fsync(descriptor)

    with monkeypatch.context() as scoped:
        scoped.setattr(historical_revision_store, "_read_object", read)
        scoped.setattr(os, "fsync", fail_matching_parent_fsync)
        replay = _import(store, inputs)

    assert fsync_triggered
    assert (
        replay.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert _import(store, inputs).outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS


@pytest.mark.parametrize(
    "components",
    (
        ("historical_ohlcv_revisions",),
        ("historical_ohlcv_revisions", "v1", "objects"),
        ("historical_ohlcv_revisions", "v1", "revisions"),
    ),
)
def test_existing_directory_retry_propagates_owning_parent_fsync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, components: tuple[str, ...]
) -> None:
    descriptors = [
        os.open(
            tmp_path,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
    ]
    try:
        for component in components:
            os.mkdir(component, 0o700, dir_fd=descriptors[-1])
            descriptors.append(
                os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=descriptors[-1],
                )
            )
        parent = descriptors[-2]
        original_fsync = os.fsync
        triggered = False

        def fail_owning_parent(descriptor: int) -> None:
            nonlocal triggered
            if descriptor == parent:
                triggered = True
                raise OSError("injected existing-directory parent fsync failure")
            original_fsync(descriptor)

        monkeypatch.setattr(os, "fsync", fail_owning_parent)

        with pytest.raises(OSError, match="existing-directory parent fsync failure"):
            historical_revision_store._open_directory(  # pyright: ignore[reportPrivateUsage]
                parent, components[-1]
            )

        assert triggered
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def test_initial_existing_nonempty_root_rejects_without_historical_mutation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "store"
    root.mkdir(mode=0o700)
    foreign = root / "unrelated"
    foreign.write_bytes(b"preserve")
    lock = root / ".ingestion.lock"
    lock.write_bytes(b"")
    lock.chmod(0o600)

    result = _import(HistoricalOhlcvRevisionStoreV1(root), _inputs())

    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert foreign.read_bytes() == b"preserve"
    assert lock.read_bytes() == b""
    assert not (root / "historical_ohlcv_revisions").exists()


def test_initial_existing_root_allows_only_exact_replay_before_directory_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    inputs = _inputs()
    initial = _import(store, inputs)
    assert initial.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS

    def reject_directory_open(_parent: int, _name: str) -> int:
        raise AssertionError("INITIAL exact replay attempted directory mutation path")

    monkeypatch.setattr(
        historical_revision_store, "_open_directory", reject_directory_open
    )
    replay = _import(store, inputs)

    assert replay.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert replay.revision_sha256 == initial.revision_sha256


def test_append_accepts_inclusive_non_session_upper_range(tmp_path: Path) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    parent = _import(store, _inputs(sessions=("2024-01-04",)))
    assert parent.revision_sha256 is not None
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs(
        sessions=("2024-01-04", "2024-01-05"),
        operation="APPEND",
        parent=parent.revision_sha256,
    )
    request = json.loads(request_raw)
    request["to_session"] = "2024-01-07"
    request["schedule_evidence_sha256"] = historical_revision_store._schedule_identity(  # pyright: ignore[reportPrivateUsage]
        request["from_session"],
        request["to_session"],
        request["expected_sessions"],
    )
    inputs = _rebind_source_inputs(
        request,
        json.loads(policy_raw),
        json.loads(artifact_raw),
        json.loads(receipt_raw),
    )

    result = _import(store, inputs)

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert result.revision is not None
    assert result.revision["to_session"] == "2024-01-07"


def test_append_rejects_suffix_inside_parent_inclusive_range(tmp_path: Path) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    parent = _import(
        store,
        _with_request_to_session(_inputs(sessions=("2024-01-05",)), "2024-01-07"),
    )
    assert parent.revision_sha256 is not None

    result = _import(
        store,
        _with_request_to_session(
            _inputs(
                sessions=("2024-01-05", "2024-01-06"),
                operation="APPEND",
                parent=parent.revision_sha256,
            ),
            "2024-01-07",
        ),
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT


def test_append_rejects_shrinking_parent_inclusive_range(tmp_path: Path) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    parent = _import(
        store,
        _with_request_to_session(_inputs(sessions=("2024-01-05",)), "2024-01-07"),
    )
    assert parent.revision_sha256 is not None

    result = _import(
        store,
        _inputs(
            sessions=("2024-01-05", "2024-01-06"),
            operation="APPEND",
            parent=parent.revision_sha256,
        ),
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT


def test_append_accepts_later_suffix_and_inclusive_upper_range(tmp_path: Path) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    parent = _import(
        store,
        _with_request_to_session(_inputs(sessions=("2024-01-05",)), "2024-01-07"),
    )
    assert parent.revision_sha256 is not None

    result = _import(
        store,
        _with_request_to_session(
            _inputs(
                sessions=("2024-01-05", "2024-01-08"),
                operation="APPEND",
                parent=parent.revision_sha256,
            ),
            "2024-01-09",
        ),
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert result.revision is not None
    assert result.revision["to_session"] == "2024-01-09"


def test_initial_existing_root_rejects_divergent_candidate_without_mutation(
    tmp_path: Path,
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    initial = _import(store, _inputs())
    assert initial.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    before = _historical_root_file_snapshot(tmp_path)

    changed = _import(
        store,
        _inputs(
            bars=[
                _bar("2024-01-02", close="100.5"),
                _bar("2024-01-03", close="100.75"),
            ]
        ),
    )

    assert (
        changed.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert _historical_root_file_snapshot(tmp_path) == before


def test_cli_read_negative_paths_preserve_real_ingestion_lock(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    stored = _import(store, _inputs())
    assert stored.revision_sha256 is not None
    lock = tmp_path / ".ingestion.lock"
    lock_before = lock.read_bytes()
    revision_path = _revision_path(tmp_path, stored.revision_sha256)
    revision_before = revision_path.read_bytes()

    malformed_exit = cli.main(
        [
            "historical-ohlcv-read",
            "--revision-sha256",
            "not-a-digest",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ]
    )
    malformed = json.loads(capsys.readouterr().out)
    missing_exit = cli.main(
        [
            "historical-ohlcv-read",
            "--revision-sha256",
            _digest(b"missing"),
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ]
    )
    missing = json.loads(capsys.readouterr().out)

    assert malformed_exit == 1
    assert malformed["outcome"] == "MALFORMED_INPUT"
    assert missing_exit == 1
    assert missing["outcome"] == "PUBLICATION_UNCERTAIN_OR_CONFLICT"
    assert lock.read_bytes() == lock_before
    assert revision_path.read_bytes() == revision_before


def test_cli_unsafe_root_has_no_real_lease_effect(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    unsafe_root = tmp_path / "unsafe"
    unsafe_root.mkdir(mode=0o755)

    exit_code = cli.main(
        [
            "historical-ohlcv-read",
            "--revision-sha256",
            _digest(b"missing"),
            "--storage-root",
            str(unsafe_root),
            "--output",
            "json",
        ]
    )

    assert exit_code == 2
    assert capsys.readouterr().out == ""
    assert not (unsafe_root / ".ingestion.lock").exists()
    assert not (unsafe_root / "historical_ohlcv_revisions").exists()


@pytest.mark.parametrize(
    ("coordinate", "parent_kind"),
    (
        (
            {"isin": "INE002A01019", "exchange": "NSE", "session": "2024-01-02"},
            "missing",
        ),
        (
            {"isin": "INE002A01019", "exchange": "NSE", "session": "2024-01-02"},
            "existing",
        ),
        (
            {"isin": "INE002A01018", "exchange": "NSE", "session": "2024-01-04"},
            "missing",
        ),
        (
            {"isin": "INE002A01018", "exchange": "NSE", "session": "2024-01-04"},
            "existing",
        ),
    ),
)
def test_correction_full_grid_membership_precedes_parent_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    coordinate: dict[str, str],
    parent_kind: str,
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    parent = _import(store, _inputs())
    assert parent.revision_sha256 is not None
    parent_id = (
        parent.revision_sha256
        if parent_kind == "existing"
        else _digest(b"missing-parent")
    )
    request, policy, artifact, receipt = _inputs(
        operation="CORRECTION",
        parent=parent_id,
        correction_coordinates=[coordinate],
    )
    calls = 0
    original_read = HistoricalOhlcvRevisionStoreV1.read_exact

    def track_read(
        self: HistoricalOhlcvRevisionStoreV1, revision_sha256: object
    ) -> HistoricalOhlcvImportResultV1:
        nonlocal calls
        calls += 1
        return original_read(self, revision_sha256)

    monkeypatch.setattr(HistoricalOhlcvRevisionStoreV1, "read_exact", track_read)

    result = store.import_exact(request, policy, artifact, receipt)

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE
    assert calls == 0


@pytest.mark.parametrize(
    ("count", "accepted"),
    ((500_000, True), (500_001, False)),
)
def test_source_artifact_max_rows_is_structural_at_exact_ceiling(
    monkeypatch: pytest.MonkeyPatch, count: int, accepted: bool
) -> None:
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs()
    request = historical_revision_store._parse_request_structure(  # pyright: ignore[reportPrivateUsage]
        request_raw
    )
    source = historical_revision_store._parse_source_structure(  # pyright: ignore[reportPrivateUsage]
        policy_raw, artifact_raw, receipt_raw
    )
    assert request is not None
    assert source is not None
    policy, artifact, receipt = source
    bounded_artifact = dict(artifact)
    bounded_artifact["bars"] = [artifact["bars"][0]] * count

    monkeypatch.setattr(
        historical_revision_store,
        "_parse_source_structure",
        lambda _policy, _artifact, _receipt: (policy, bounded_artifact, receipt),
    )

    candidate = historical_revision_store._parse_import_candidate_structure(  # pyright: ignore[reportPrivateUsage]
        request_raw, artifact_raw, artifact_raw, receipt_raw
    )

    assert (candidate is not None) is accepted
    if not accepted:
        result = HistoricalOhlcvRevisionStoreV1(
            Path("/invalid/structural-ceiling")
        ).import_exact(request_raw, artifact_raw, artifact_raw, receipt_raw)
        assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT


def test_revision_schema_request_projection_metadata_is_exact_deep_copy() -> None:
    objects = historical_revision_store._SCHEMA_IDENTITY_PREIMAGE["objects"]  # pyright: ignore[reportPrivateUsage]
    request_fields = objects["FixedCohortHistoricalOhlcvRequestV1"]["field_contracts"]
    revision_fields = objects["HistoricalOhlcvRevisionV1"]["field_contracts"]

    for field in historical_revision_store._REQUEST_FIELDS:  # pyright: ignore[reportPrivateUsage]
        assert revision_fields[field] == request_fields[field]
        assert revision_fields[field] is not request_fields[field]


@pytest.mark.parametrize("command", ("import", "read"))
def test_cli_preserves_admitted_root_identity_for_domain_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    root_a.mkdir(mode=0o700)
    root_b.mkdir(mode=0o700)
    inputs = _inputs()
    imported_a = _import(HistoricalOhlcvRevisionStoreV1(root_a), inputs)
    imported_b = _import(HistoricalOhlcvRevisionStoreV1(root_b), inputs)
    assert imported_a.revision_sha256 is not None
    assert imported_a.revision_sha256 == imported_b.revision_sha256
    for name, raw in zip(
        ("request.json", "policy.json", "artifact.json", "receipt.json"),
        inputs,
        strict=True,
    ):
        (tmp_path / name).write_bytes(raw)
    root_b_before = _historical_root_file_snapshot(root_b)
    old_root_a = tmp_path / "old-root-a"

    def substitute() -> None:
        root_a.rename(old_root_a)
        root_b.rename(root_a)

    if command == "import":
        original_import = HistoricalOhlcvRevisionStoreV1.import_exact

        def import_after_substitution(
            self: HistoricalOhlcvRevisionStoreV1,
            request_raw: object,
            source_policy_raw: object,
            source_artifact_raw: object,
            receipt_raw: object,
        ) -> HistoricalOhlcvImportResultV1:
            substitute()
            return original_import(
                self, request_raw, source_policy_raw, source_artifact_raw, receipt_raw
            )

        monkeypatch.setattr(
            HistoricalOhlcvRevisionStoreV1, "import_exact", import_after_substitution
        )
        arguments = [
            "historical-ohlcv-import",
            "--request-file",
            str(tmp_path / "request.json"),
            "--source-policy-file",
            str(tmp_path / "policy.json"),
            "--source-artifact-file",
            str(tmp_path / "artifact.json"),
            "--receipt-file",
            str(tmp_path / "receipt.json"),
            "--storage-root",
            str(root_a),
            "--output",
            "json",
        ]
    else:
        original_read = HistoricalOhlcvRevisionStoreV1.read_exact

        def read_after_substitution(
            self: HistoricalOhlcvRevisionStoreV1, revision_sha256: object
        ) -> HistoricalOhlcvImportResultV1:
            substitute()
            return original_read(self, revision_sha256)

        monkeypatch.setattr(
            HistoricalOhlcvRevisionStoreV1, "read_exact", read_after_substitution
        )
        arguments = [
            "historical-ohlcv-read",
            "--revision-sha256",
            imported_a.revision_sha256,
            "--storage-root",
            str(root_a),
            "--output",
            "json",
        ]

    assert cli.main(arguments) == 1
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["outcome"] == "PUBLICATION_UNCERTAIN_OR_CONFLICT"
    assert _historical_root_file_snapshot(root_a) == root_b_before


@pytest.mark.parametrize(
    "component",
    ("historical_ohlcv_revisions", "v1", "objects", "revisions"),
)
def test_initial_exact_replay_fsyncs_each_existing_hierarchy_parent_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, component: str
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    inputs = _inputs()
    assert _import(store, inputs).outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    original_open_existing = historical_revision_store._open_existing_directory  # pyright: ignore[reportPrivateUsage]
    original_fsync = os.fsync
    original_open = os.open
    target_parent: int | None = None
    parent_fsync_count = 0
    opened_before_parent_fsync = False

    def open_existing(parent: int, name: str) -> int:
        nonlocal target_parent
        if name == component:
            target_parent = parent
        return original_open_existing(parent, name)

    def observe_fsync(descriptor: int) -> None:
        nonlocal parent_fsync_count
        if descriptor == target_parent:
            parent_fsync_count += 1
        original_fsync(descriptor)

    def observe_open(
        path: str | bytes,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal opened_before_parent_fsync
        if path == component and dir_fd == target_parent:
            opened_before_parent_fsync = parent_fsync_count == 0
        if mode == 0o777:
            return original_open(path, flags, dir_fd=dir_fd)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    with monkeypatch.context() as scoped:
        scoped.setattr(
            historical_revision_store, "_open_existing_directory", open_existing
        )
        scoped.setattr(os, "fsync", observe_fsync)
        scoped.setattr(os, "open", observe_open)
        result = _import(store, inputs)

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert target_parent is not None
    assert parent_fsync_count >= 1
    assert not opened_before_parent_fsync


@pytest.mark.parametrize(
    "component",
    ("historical_ohlcv_revisions", "v1", "objects", "revisions"),
)
def test_initial_exact_replay_parent_fsync_failure_prevents_child_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, component: str
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    inputs = _inputs()
    assert _import(store, inputs).outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    original_open_existing = historical_revision_store._open_existing_directory  # pyright: ignore[reportPrivateUsage]
    original_fsync = os.fsync
    original_open = os.open
    target_parent: int | None = None
    triggered = False
    child_opened = False

    def open_existing(parent: int, name: str) -> int:
        nonlocal target_parent
        if name == component:
            target_parent = parent
        return original_open_existing(parent, name)

    def fail_target_parent(descriptor: int) -> None:
        nonlocal triggered
        if descriptor == target_parent and not triggered:
            triggered = True
            raise OSError("injected exact-replay hierarchy fsync failure")
        original_fsync(descriptor)

    def observe_open(
        path: str | bytes,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal child_opened
        if path == component and dir_fd == target_parent:
            child_opened = True
        if mode == 0o777:
            return original_open(path, flags, dir_fd=dir_fd)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    with monkeypatch.context() as scoped:
        scoped.setattr(
            historical_revision_store, "_open_existing_directory", open_existing
        )
        scoped.setattr(os, "fsync", fail_target_parent)
        scoped.setattr(os, "open", observe_open)
        result = _import(store, inputs)

    assert triggered
    assert not child_opened
    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert _import(store, inputs).outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS


def _inject_sibling_directory_open_failure(
    monkeypatch: pytest.MonkeyPatch,
    sibling_parent: Callable[[], int | None],
) -> None:
    original_open = os.open

    def fail_sibling_open(
        path: str | bytes,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if path == "revisions" and dir_fd == sibling_parent():
            raise OSError("injected sibling directory open failure")
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", fail_sibling_open)


def _inject_sibling_parent_fsync_failure(
    monkeypatch: pytest.MonkeyPatch,
    sibling_parent: Callable[[], int | None],
) -> None:
    original_fsync = os.fsync

    def fail_sibling_parent_fsync(descriptor: int) -> None:
        if descriptor == sibling_parent():
            raise OSError("injected sibling parent fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_sibling_parent_fsync)


def _assert_repeated_sibling_directory_failure_closes_descriptors(
    monkeypatch: pytest.MonkeyPatch,
    attempt: Callable[[], HistoricalOhlcvImportResultV1],
    directory_attribute: str,
    original_open_directory: Callable[[int, str], int],
    failure: str,
) -> None:
    objects_opened = False
    sibling_parent: int | None = None

    def observe_sibling_open(parent: int, name: str) -> int:
        nonlocal objects_opened, sibling_parent
        if name == "objects":
            objects_opened = True
        elif name == "revisions":
            assert objects_opened
            sibling_parent = parent
        return original_open_directory(parent, name)

    baseline_descriptors = _open_descriptor_count()
    with monkeypatch.context() as scoped:
        scoped.setattr(
            historical_revision_store, directory_attribute, observe_sibling_open
        )

        def current_sibling_parent() -> int | None:
            return sibling_parent

        if failure == "second_open":
            _inject_sibling_directory_open_failure(scoped, current_sibling_parent)
        else:
            _inject_sibling_parent_fsync_failure(scoped, current_sibling_parent)
        for _ in range(4):
            objects_opened = False
            sibling_parent = None
            result = attempt()
            assert sibling_parent is not None
            assert (
                result.outcome
                is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
            )
            assert _open_descriptor_count() == baseline_descriptors

    assert attempt().outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS


@pytest.mark.parametrize("failure", ("second_open", "sibling_parent_fsync"))
def test_initial_replay_sibling_directory_failure_closes_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    inputs = _inputs()
    initial = _import(store, inputs)
    assert initial.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS

    def attempt() -> HistoricalOhlcvImportResultV1:
        return _import(store, inputs)

    _assert_repeated_sibling_directory_failure_closes_descriptors(
        monkeypatch,
        attempt,
        "_open_existing_directory",
        historical_revision_store._open_existing_directory,  # pyright: ignore[reportPrivateUsage]
        failure,
    )


@pytest.mark.parametrize("failure", ("second_open", "sibling_parent_fsync"))
def test_import_sibling_directory_failure_closes_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    inputs = _inputs()
    import_attempt = 0

    def attempt() -> HistoricalOhlcvImportResultV1:
        nonlocal import_attempt
        root = tmp_path / f"import-attempt-{import_attempt}"
        root.mkdir(mode=0o700)
        import_attempt += 1
        return _import(HistoricalOhlcvRevisionStoreV1(root), inputs)

    _assert_repeated_sibling_directory_failure_closes_descriptors(
        monkeypatch,
        attempt,
        "_open_directory",
        historical_revision_store._open_directory,  # pyright: ignore[reportPrivateUsage]
        failure,
    )


@pytest.mark.parametrize("failure", ("second_open", "sibling_parent_fsync"))
def test_exact_read_sibling_directory_failure_closes_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    initial = _import(store, _inputs())
    assert initial.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert initial.revision_sha256 is not None

    def attempt() -> HistoricalOhlcvImportResultV1:
        return store.read_exact(initial.revision_sha256)

    _assert_repeated_sibling_directory_failure_closes_descriptors(
        monkeypatch,
        attempt,
        "_open_existing_directory",
        historical_revision_store._open_existing_directory,  # pyright: ignore[reportPrivateUsage]
        failure,
    )
