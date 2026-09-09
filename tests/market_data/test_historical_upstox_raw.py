# pyright: reportIndexIssue=false, reportMissingParameterType=false, reportPrivateUsage=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false
from __future__ import annotations

import gzip
import hashlib
import json
import os
import stat
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from swing_trading_ai_assistant.market_data import (
    cli,
    historical_revision_store,
    historical_upstox_raw,
)
from swing_trading_ai_assistant.market_data.adjusted_daily import yfinance_adapter
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.historical_revision_store import (
    HistoricalOhlcvImportOutcomeV1,
)
from swing_trading_ai_assistant.market_data.instrument_snapshot import (
    FetchedInstrumentSnapshotV1,
    InstrumentSnapshotMetadataV1,
    InstrumentSnapshotStoreV1,
)
from swing_trading_ai_assistant.market_data.instruments import InstrumentCatalog
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    verify_manifest,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
    publish_partition,
)
from swing_trading_ai_assistant.market_data.provisional_store import (
    latest_provisional_partition,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleEvidenceStore,
    ScheduleOutcome,
    ScheduleSession,
)
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)


def test_raw_profile_is_the_only_historical_completion_command() -> None:
    parser = cli.build_parser()
    actions = [action for action in parser._actions if action.dest == "command"]
    choices = actions[0].choices if actions else {}
    commands = set(choices) if choices is not None else set()

    assert "historical-ohlcv-upstox-raw" in commands
    assert "historical-ohlcv-upstox-raw-read" in commands
    assert "historical-ohlcv-import" not in commands
    assert "historical-ohlcv-read" not in commands


def test_raw_profile_exports_frozen_literals() -> None:
    assert historical_upstox_raw.COMPLETION_CONTRACT_VERSION == (
        "upstox-raw-fixed-cohort-historical-ohlcv-completion@v1"
    )
    assert historical_upstox_raw.REVISION_CONTRACT_VERSION == (
        "fixed-cohort-historical-ohlcv-upstox-raw-revision-store@v1"
    )
    assert historical_upstox_raw.SOURCE_PROFILE == "UPSTOX_RAW"
    assert historical_upstox_raw.PRICE_BASIS == "RAW"
    assert historical_upstox_raw.completion_limits_v1() == {
        "max_members": 50,
        "max_calendar_months": 12,
        "max_sessions": 366,
        "max_rows": 18_300,
        "max_source_partitions": 600,
        "max_query_months_per_call": 12,
        "max_query_rows_per_call": 366,
        "max_artifact_bytes": 134_217_728,
        "max_source_policy_bytes": 1_048_576,
        "max_receipt_bytes": 1_048_576,
        "max_revision_bytes": 134_217_728,
        "max_lineage_depth": 128,
    }


def test_malformed_input_precedes_root_admission() -> None:
    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        b"{}", Path("/not-a-source"), Path("/not-a-destination"), None
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT


def test_excessive_nesting_is_malformed_before_all_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_reached(*_: object, **__: object) -> object:
        raise AssertionError("root, source, or destination effect reached")

    monkeypatch.setattr(historical_upstox_raw, "_admit_distinct_roots", fail_if_reached)
    monkeypatch.setattr(
        historical_upstox_raw.StorageRootLease,
        "try_acquire_existing_identity",
        fail_if_reached,
    )
    monkeypatch.setattr(
        historical_upstox_raw, "HistoricalOhlcvRevisionStoreV1", fail_if_reached
    )
    monkeypatch.setattr(
        historical_upstox_raw, "_publish_generated_candidate", fail_if_reached
    )
    depth = 1_500
    request_raw = (
        b"[" * depth + _canonical(_request_with_current_identities()) + b"]" * depth
    )

    assert (
        len(request_raw)
        < historical_upstox_raw.completion_limits_v1()["max_source_policy_bytes"]
    )
    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        request_raw, Path("/not-a-source"), Path("/not-a-destination"), None
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT


def test_malformed_mapping_digest_precedes_all_effects(
    monkeypatch: object,
) -> None:
    request = _request_with_current_identities()
    mapping = cast(
        dict[str, object],
        cast(dict[str, object], request["cohort"][0])["provider_mapping"],
    )
    mapping["mapping_evidence_sha256"] = "A" * 64

    def fail_if_reached(*_: object, **__: object) -> object:
        raise AssertionError("root, lease, catalog, or snapshot read reached")

    monkeypatch.setattr(historical_upstox_raw, "_admit_distinct_roots", fail_if_reached)
    monkeypatch.setattr(
        historical_upstox_raw.StorageRootLease,
        "try_acquire_existing_identity",
        fail_if_reached,
    )
    monkeypatch.setattr(historical_upstox_raw, "DuckDBCatalog", fail_if_reached)
    monkeypatch.setattr(
        historical_upstox_raw, "InstrumentSnapshotStoreV1", fail_if_reached
    )

    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(request), Path("/not-a-source"), Path("/not-a-destination"), None
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT


def test_unsupported_basis_precedes_source_admission() -> None:
    request = _request()
    request["price_basis"] = "ADJUSTED"
    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(request), Path("/not-a-source"), Path("/not-a-destination"), None
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY


def test_zero_members_is_malformed_before_source_admission() -> None:
    request = _request()
    request["cohort"] = []
    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(request), Path("/not-a-source"), Path("/not-a-destination"), None
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT


def test_malformed_non_null_effective_end_precedes_source_admission() -> None:
    for path, value in (
        (("symbol_effective_to",), "not-a-date"),
        (("provider_mapping", "mapping_effective_to"), "not-a-date"),
    ):
        request = _request_with_current_identities()
        target = cast(dict[str, object], request["cohort"][0])
        for field in path[:-1]:
            target = cast(dict[str, object], target[field])
        target[path[-1]] = value

        result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
            _canonical(request), Path("/not-a-source"), Path("/not-a-destination"), None
        )

        assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT


def test_member_generated_revision_grammar_precedes_source_admission() -> None:
    for path, value in (
        (("isin",), "INE002A010Å8"),
        (("effective_symbol",), "SYMBOL\n"),
        (("effective_symbol",), "S" * 65),
        (("provider_mapping", "provider_instrument_id"), "ID\x7f"),
        (("provider_mapping", "provider_instrument_id"), "I" * 65),
    ):
        request = _request_with_current_identities()
        target = cast(dict[str, object], request["cohort"][0])
        for field in path[:-1]:
            target = cast(dict[str, object], target[field])
        target[path[-1]] = value

        result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
            _canonical(request), Path("/not-a-source"), Path("/not-a-destination"), None
        )

        assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT


def test_source_identity_is_leased_before_source_reads(
    tmp_path: Path, monkeypatch
) -> None:
    source, destination = _private_roots_with_source_lock(tmp_path)
    source_identity = (
        historical_upstox_raw.StorageRootLease.admit_existing_private_identity(source)
    )
    assert source_identity is not None
    original = historical_upstox_raw.StorageRootLease.try_acquire_existing_identity
    acquired: list[tuple[Path, tuple[int, int]]] = []

    def capture(root: object, identity: tuple[int, int]):
        acquired.append((cast(Path, root), identity))
        return original(root, identity)

    monkeypatch.setattr(
        historical_upstox_raw.StorageRootLease,
        "try_acquire_existing_identity",
        capture,
    )
    identity = historical_upstox_raw.StorageRootLease.admit_existing_private_identity(
        destination
    )
    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(_request_with_current_identities()), source, destination, identity
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.INSUFFICIENT_EVIDENCE
    assert acquired == [(source, source_identity)]


def test_source_substitution_prevents_source_reads_and_precedes_destination(
    tmp_path: Path, monkeypatch
) -> None:
    source, destination = _private_roots_with_source_lock(tmp_path)
    original = historical_upstox_raw.StorageRootLease.try_acquire_existing_identity
    source_reads: list[object] = []

    def substitute(root: object, identity: tuple[int, int]):
        return original(root, (identity[0], identity[1] + 1))

    def forbidden_read(*args: object, **kwargs: object) -> object:
        source_reads.append((args, kwargs))
        raise AssertionError("source read reached")

    monkeypatch.setattr(
        historical_upstox_raw.StorageRootLease,
        "try_acquire_existing_identity",
        substitute,
    )
    monkeypatch.setattr(
        historical_upstox_raw.StoredCoverageEvaluatorV1,
        "admit",
        forbidden_read,
    )
    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(_request_with_current_identities()), source, destination, (-1, -1)
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.CONFLICTING_EVIDENCE
    assert source_reads == []


def test_missing_source_precedes_destination_substitution(tmp_path: Path) -> None:
    source, destination = _private_roots_with_source_lock(tmp_path)

    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(_request_with_current_identities()), source, destination, (-1, -1)
    )
    assert result.outcome is HistoricalOhlcvImportOutcomeV1.INSUFFICIENT_EVIDENCE


def test_held_source_lease_is_insufficient_before_destination_work(
    tmp_path: Path,
) -> None:
    source, destination = _private_roots_with_source_lock(tmp_path)
    source_identity = StorageRootLease.admit_existing_private_identity(source)
    destination_identity = StorageRootLease.admit_existing_private_identity(destination)
    assert source_identity is not None and destination_identity is not None
    held = StorageRootLease.try_acquire_existing_identity(source, source_identity)
    assert held.outcome is LeaseOutcome.ACQUIRED and held.lease is not None
    with held.lease:
        result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
            _canonical(_request_with_current_identities()),
            source,
            destination,
            destination_identity,
        )
    assert result.outcome is HistoricalOhlcvImportOutcomeV1.INSUFFICIENT_EVIDENCE


def test_source_assessment_retains_source_failure_precedence() -> None:
    assessment = historical_upstox_raw._SourceAssessmentV1()
    assessment.record_exception(FileNotFoundError())
    assessment.record_exception(historical_upstox_raw.CatalogSchemaError())
    assessment.record_exception(historical_upstox_raw.CatalogConflictError())

    try:
        assessment.raise_if_any()
    except historical_upstox_raw._Conflict:
        pass
    else:
        raise AssertionError(
            "conflicting retained evidence must outrank invalid and absent"
        )

    assessment = historical_upstox_raw._SourceAssessmentV1()
    assessment.record(historical_upstox_raw._Missing)
    assessment.record(historical_upstox_raw._Invalid)
    assessment.record(historical_upstox_raw._Unsupported)

    try:
        assessment.raise_if_any()
    except historical_upstox_raw._Unsupported:
        pass
    else:
        raise AssertionError("unsupported capability must outrank invalid and absent")


def test_source_precedence_beats_parent_and_destination_failure(
    tmp_path: Path, monkeypatch
) -> None:
    source, destination = _private_roots_with_source_lock(tmp_path)
    identity = StorageRootLease.admit_existing_private_identity(destination)
    assert identity is not None
    request = _request_with_current_identities()
    request["operation"] = "APPEND"
    request["parent_revision_sha256"] = "a" * 64

    def publication_must_not_run(*_: object, **__: object) -> object:
        raise AssertionError("source failure must precede parent and destination work")

    monkeypatch.setattr(
        historical_upstox_raw,
        "_publish_generated_candidate",
        publication_must_not_run,
    )
    for finding, expected in (
        (
            historical_upstox_raw._Unsupported,
            HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY,
        ),
        (
            historical_upstox_raw._Conflict,
            HistoricalOhlcvImportOutcomeV1.CONFLICTING_EVIDENCE,
        ),
        (
            historical_upstox_raw._Invalid,
            HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE,
        ),
        (
            historical_upstox_raw._Missing,
            HistoricalOhlcvImportOutcomeV1.INSUFFICIENT_EVIDENCE,
        ),
    ):

        def raise_source(
            *_: object, error: type[Exception] = finding, **__: object
        ) -> object:
            raise error

        monkeypatch.setattr(
            historical_upstox_raw, "_project_retained_source", raise_source
        )
        result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
            _canonical(request), source, destination, identity
        )
        assert result.outcome is expected


def test_completion_propagates_unexpected_source_defects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, destination = _private_roots_with_source_lock(tmp_path)
    identity = StorageRootLease.admit_existing_private_identity(destination)
    assert identity is not None
    request = _request_with_current_identities()

    for error in (
        AssertionError("injected assertion defect"),
        KeyError("injected key defect"),
        RuntimeError("injected runtime defect"),
        Exception("injected unexpected defect"),
    ):

        def raise_defect(*_: object, defect: Exception = error, **__: object) -> object:
            raise defect

        monkeypatch.setattr(
            historical_upstox_raw, "_project_retained_source", raise_defect
        )
        with pytest.raises(type(error), match="injected"):
            historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
                _canonical(request), source, destination, identity
            )


@pytest.mark.parametrize(
    "command", ("historical-ohlcv-upstox-raw", "historical-ohlcv-upstox-raw-read")
)
def test_historical_cli_execution_fault_is_not_a_request_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    source, destination = _private_roots_with_source_lock(tmp_path)
    request_file = tmp_path / "request.json"
    request_file.write_bytes(_canonical(_request_with_current_identities()))
    before = _tree_bytes(destination)

    def fail_execution(*_: object, **__: object) -> object:
        raise ValueError("private/path/token/provider-payload")

    monkeypatch.setattr(cli, "complete_upstox_raw_historical_ohlcv_v1", fail_execution)
    monkeypatch.setattr(
        cli.HistoricalOhlcvRevisionStoreV1, "read_exact", fail_execution
    )
    args = [command, "--storage-root", str(destination), "--output", "json"]
    if command == "historical-ohlcv-upstox-raw":
        args.extend(
            ["--source-storage-root", str(source), "--request-file", str(request_file)]
        )
    else:
        args.extend(["--revision-sha256", "a" * 64])

    assert cli.main(args) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "internal_error\n"
    assert _tree_bytes(destination) == before


def test_range_limit_plus_one_is_malformed_before_source_admission() -> None:
    request = _request()
    request["to_session"] = "2027-07-01"
    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(request), Path("/not-a-source"), Path("/not-a-destination"), None
    )
    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT

    request = _request()
    start = date(2026, 7, 1)
    request["expected_sessions"] = [
        (start + timedelta(days=offset)).isoformat() for offset in range(367)
    ]
    request["to_session"] = request["expected_sessions"][-1]
    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(request), Path("/not-a-source"), Path("/not-a-destination"), None
    )
    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT


def test_closed_request_accepts_all_supported_limits_and_rejects_limit_plus_one() -> (
    None
):
    request = _request_with_current_identities()
    lower = date(2024, 1, 1)
    request["from_session"] = lower.isoformat()
    request["to_session"] = "2024-12-31"
    request["expected_sessions"] = [
        (lower + timedelta(days=offset)).isoformat() for offset in range(366)
    ]
    cohort: list[dict[str, Any]] = []
    for index in range(50):
        member = json.loads(json.dumps(request["cohort"][0]))
        isin = _synthetic_isin(index)
        member["isin"] = isin
        member["effective_symbol"] = f"SYM{index:02d}"
        member["provider_mapping"]["provider_instrument_id"] = f"NSE_EQ|{isin}"
        member["symbol_effective_from"] = lower.isoformat()
        member["provider_mapping"]["mapping_effective_from"] = lower.isoformat()
        cohort.append(member)
    request["cohort"] = sorted(cohort, key=lambda member: (member["isin"], "NSE"))

    assert historical_upstox_raw._decode_request(_canonical(request)) is not None
    assert len(request["expected_sessions"]) == 366
    assert len(request["cohort"]) * len(request["expected_sessions"]) == 18_300
    assert len(request["cohort"]) * 12 == 600

    thirteen_months = json.loads(json.dumps(request))
    thirteen_months["to_session"] = "2025-01-01"
    thirteen_months["expected_sessions"] = ["2024-01-01"]
    assert historical_upstox_raw._decode_request(_canonical(thirteen_months)) is None

    three_hundred_sixty_seven_sessions = json.loads(json.dumps(request))
    three_hundred_sixty_seven_sessions["to_session"] = "2025-01-01"
    three_hundred_sixty_seven_sessions["expected_sessions"].append("2025-01-01")
    assert (
        historical_upstox_raw._decode_request(
            _canonical(three_hundred_sixty_seven_sessions)
        )
        is None
    )

    fifty_one_members = json.loads(json.dumps(request))
    fifty_one_members["cohort"].append(
        json.loads(json.dumps(fifty_one_members["cohort"][0]))
    )
    assert historical_upstox_raw._decode_request(_canonical(fifty_one_members)) is None


def test_unsupported_operator_capabilities_precede_root_admission() -> None:
    mutations = (
        ("contract_version", "other"),
        ("revision_contract_version", "other"),
        ("research_scope", "OTHER_SCOPE"),
        ("source_profile", "OTHER_PROFILE"),
        ("interval", "1h"),
        ("permitted_use", "OTHER_USE"),
        ("price_basis", "ADJUSTED"),
    )
    for field, value in mutations:
        request = _request()
        request[field] = value
        result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
            _canonical(request),
            Path("/not-a-source"),
            Path("/not-a-destination"),
            None,
        )
        assert result.outcome is HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY

    for field, value in (
        ("exchange", "BSE"),
        ("listed_equity_segment", "OTHER"),
        ("provider", "OTHER"),
    ):
        request = _request()
        target = (
            request["cohort"][0]["provider_mapping"]
            if field == "provider"
            else request["cohort"][0]
        )
        target[field] = value
        result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
            _canonical(request),
            Path("/not-a-source"),
            Path("/not-a-destination"),
            None,
        )
        assert result.outcome is HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY


@pytest.mark.private_source
def test_real_retained_reliance_july_initial_and_exact_retry(
    tmp_path: Path, monkeypatch
) -> None:
    request = _retained_request(
        "2026-07-01",
        "2026-07-31",
        _JULY_SESSIONS,
        "0fe8111d5993b20935484ab269c1a739757523011f1aacf23f6d3407bbe8b050",
    )
    source = Path.home() / "SwingTradingAIAssistantData"
    source_identity = (
        historical_upstox_raw.StorageRootLease.admit_existing_private_identity(source)
    )
    assert source_identity is not None
    source_fingerprints: list[tuple[int, int] | None] = []
    original_admission = (
        historical_upstox_raw.StorageRootLease.admit_existing_private_identity
    )

    def fingerprint(root: object) -> tuple[int, int] | None:
        identity = original_admission(root)
        if root == source:
            source_fingerprints.append(identity)
        return identity

    def fail_if_reached(*_: object, **__: object) -> object:
        raise AssertionError(
            "provider, credential, HTTP, downloader, or yfinance reached"
        )

    monkeypatch.setattr(
        historical_upstox_raw.StorageRootLease,
        "admit_existing_private_identity",
        fingerprint,
    )
    monkeypatch.setattr(
        cli._LazyEnvironmentAccessTokenProvider, "get_access_token", fail_if_reached
    )
    monkeypatch.setattr(cli._HistoricalProviderSession, "fetch", fail_if_reached)
    monkeypatch.setattr(cli, "_default_download_service", fail_if_reached)
    monkeypatch.setattr(yfinance_adapter, "_public_download", fail_if_reached)

    identity = historical_upstox_raw.StorageRootLease.admit_existing_private_identity(
        tmp_path
    )
    first = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(request), source, tmp_path, identity
    )
    second = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(request), source, tmp_path, identity
    )

    assert first.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert first.revision is not None
    assert len(first.revision["bars"]) == 23
    assert first.revision["bars"][0] == {
        "isin": "INE002A01018",
        "exchange": "NSE",
        "session": "2026-07-01",
        "open": "1298.9",
        "high": "1312.2",
        "low": "1296.5",
        "close": "1306.5",
        "volume": "6999059",
        "known_at": "2026-08-27T03:18:10.135710Z",
        "price_basis": "RAW",
    }
    assert first.revision["bars"][-1] == {
        "isin": "INE002A01018",
        "exchange": "NSE",
        "session": "2026-07-31",
        "open": "1295",
        "high": "1309.7",
        "low": "1293.6",
        "close": "1305",
        "volume": "8622344",
        "known_at": "2026-08-27T03:18:10.135710Z",
        "price_basis": "RAW",
    }
    objects = tmp_path / "historical_ohlcv_revisions" / "upstox-raw" / "v1" / "objects"
    artifact = json.loads(
        (objects / first.revision["source_artifact_sha256"]).read_bytes()
    )
    receipt = json.loads((objects / first.revision["receipt_sha256"]).read_bytes())
    assert [
        partition["parquet_sha256"] for partition in artifact["partition_receipts"]
    ] == ["43c6b3e45bbf31066f8c8a05007d9a76d257ee29217dec5201cd89bd6d54474c"]
    assert receipt["known_at"] == "2026-08-27T03:18:10.135710Z"
    assert receipt["known_at"] == max(row["known_at"] for row in artifact["bars"])
    assert source_fingerprints and all(
        fingerprint == source_identity for fingerprint in source_fingerprints
    )
    assert len(source_fingerprints) >= 3
    assert (
        first.revision["completion_request_identity_sha256"]
        == historical_upstox_raw.hashlib.sha256(_canonical(request)).hexdigest()
    )
    assert (
        first.revision["completion_request_identity_sha256"]
        != historical_upstox_raw.hashlib.sha256(
            _canonical(
                {
                    name: first.revision[name]
                    for name in historical_revision_store._REQUEST_FIELDS
                }
            )
        ).hexdigest()
    )
    assert second.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert second.revision_sha256 == first.revision_sha256


@pytest.mark.private_source
def test_real_retained_reliance_append_is_source_backed_and_preserves_known_at(
    tmp_path: Path, monkeypatch
) -> None:
    source = Path.home() / "SwingTradingAIAssistantData"
    schedule_digest = "0fe8111d5993b20935484ab269c1a739757523011f1aacf23f6d3407bbe8b050"
    parent_request = _retained_request(
        "2026-07-01", "2026-07-01", [_JULY_SESSIONS[0]], schedule_digest
    )
    identity = historical_upstox_raw.StorageRootLease.admit_existing_private_identity(
        tmp_path
    )
    assert identity is not None
    projected: list[int] = []
    original_projection = historical_upstox_raw._project_retained_source

    def capture_projection(*args: Any, **kwargs: Any) -> object:
        candidate = original_projection(*args, **kwargs)
        projected.append(len(candidate[1]["bars"]))
        return candidate

    monkeypatch.setattr(
        historical_upstox_raw, "_project_retained_source", capture_projection
    )
    validated: list[bool] = []
    original_validation = historical_upstox_raw.validate_generated_source_candidate_v1

    def capture_validation(*args: Any, **kwargs: Any) -> bool:
        valid = original_validation(*args, **kwargs)
        validated.append(valid)
        return valid

    monkeypatch.setattr(
        historical_upstox_raw,
        "validate_generated_source_candidate_v1",
        capture_validation,
    )
    parent = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(parent_request), source, tmp_path, identity
    )
    assert projected == [1]
    assert validated == [True]
    assert parent.revision is not None and parent.revision_sha256 is not None

    append_request = _retained_request(
        "2026-07-01", "2026-07-31", _JULY_SESSIONS, schedule_digest
    )
    append_request["operation"] = "APPEND"
    append_request["parent_revision_sha256"] = parent.revision_sha256
    append_request["observed_at"] = "2026-08-29T00:00:00Z"
    append = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(append_request), source, tmp_path, identity
    )

    assert append.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert projected == [1, 23]
    assert validated == [True, True]
    assert append.revision is not None
    assert append.revision["observed_at"] > parent.revision["observed_at"]
    assert append.revision["bars"][0] == parent.revision["bars"][0]
    assert append.revision["bars"][0]["known_at"] < append.revision["observed_at"]


@pytest.mark.private_source
def test_real_current_august_provisional_partition_is_insufficient(
    tmp_path: Path, monkeypatch
) -> None:
    request = _retained_request(
        "2026-08-03",
        "2026-08-26",
        _AUGUST_SESSIONS,
        "0fe8111d5993b20935484ab269c1a739757523011f1aacf23f6d3407bbe8b050",
    )
    source = Path.home() / "SwingTradingAIAssistantData"

    def fail_if_reached(*_: object, **__: object) -> object:
        raise AssertionError(
            "provider, credential, HTTP, downloader, repair, promotion, or yfinance reached"
        )

    monkeypatch.setattr(
        cli._LazyEnvironmentAccessTokenProvider, "get_access_token", fail_if_reached
    )
    monkeypatch.setattr(cli._HistoricalProviderSession, "fetch", fail_if_reached)
    monkeypatch.setattr(cli, "_default_download_service", fail_if_reached)
    monkeypatch.setattr(yfinance_adapter, "_public_download", fail_if_reached)
    evaluator = historical_upstox_raw.StoredCoverageEvaluatorV1()
    coverage_observed_at = datetime(2026, 9, 1, tzinfo=UTC)
    with evaluator.admit(source) as admission:
        coverage = evaluator.evaluate_under_admission(
            historical_upstox_raw.CoverageRequestV1(
                "NSE_EQ",
                "RELIANCE",
                date(2026, 8, 3),
                date(2026, 8, 26),
                source,
            ),
            coverage_observed_at,
            admission,
        )
    assert coverage.verified_partitions == ()
    assert [month.coverage_state.value for month in coverage.months] == ["MISSING"]
    with evaluator.admit(source) as admission:
        provisional = latest_provisional_partition(
            source,
            admission.lease,
            PlannedInstrumentMonth(
                "upstox",
                "NSE_EQ|INE002A01018",
                "INE002A01018",
                "RELIANCE",
                "NSE",
                "NSE_EQ",
                "EQ",
                "1m",
                2026,
                8,
                date(2026, 8, 1),
                date(2026, 8, 31),
            ),
        )
    assert provisional is not None
    metadata, rows = provisional
    assert metadata.cutoff == datetime(2026, 8, 26, 9, 59, tzinfo=UTC)
    assert metadata.row_count == len(rows) == 6_750

    identity = historical_upstox_raw.StorageRootLease.admit_existing_private_identity(
        tmp_path
    )
    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(request), source, tmp_path, identity
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.INSUFFICIENT_EVIDENCE
    assert not (tmp_path / "historical_ohlcv_revisions").exists()


_JULY_SESSIONS = [
    "2026-07-01",
    "2026-07-02",
    "2026-07-03",
    "2026-07-06",
    "2026-07-07",
    "2026-07-08",
    "2026-07-09",
    "2026-07-10",
    "2026-07-13",
    "2026-07-14",
    "2026-07-15",
    "2026-07-16",
    "2026-07-17",
    "2026-07-20",
    "2026-07-21",
    "2026-07-22",
    "2026-07-23",
    "2026-07-24",
    "2026-07-27",
    "2026-07-28",
    "2026-07-29",
    "2026-07-30",
    "2026-07-31",
]
_AUGUST_SESSIONS = [
    "2026-08-03",
    "2026-08-04",
    "2026-08-05",
    "2026-08-06",
    "2026-08-07",
    "2026-08-10",
    "2026-08-11",
    "2026-08-12",
    "2026-08-13",
    "2026-08-14",
    "2026-08-17",
    "2026-08-18",
    "2026-08-19",
    "2026-08-20",
    "2026-08-21",
    "2026-08-24",
    "2026-08-25",
    "2026-08-26",
]


@pytest.mark.private_source
def test_real_current_fifty_member_schedule_conflict_fails_closed(
    tmp_path: Path,
) -> None:
    source = Path.home() / "SwingTradingAIAssistantData"
    evaluator = historical_upstox_raw.StoredCoverageEvaluatorV1()
    with (
        evaluator.admit(source) as admission,
        historical_upstox_raw.DuckDBCatalog(
            source, read_only=True, lease=admission.lease
        ) as catalog,
    ):
        metadata = catalog.list_instrument_snapshots("upstox-bod-nse")[0]
        symbols = [
            row[0]
            for row in catalog.connection.execute(
                "SELECT DISTINCT symbol FROM partitions "
                "WHERE year = 2026 AND month = 7 AND state = 'VERIFIED' "
                "ORDER BY symbol"
            ).fetchall()
        ]
        schedule_digests = [
            policy.rsplit("sessions-sha256:", 1)[1]
            for (policy,) in catalog.connection.execute(
                "SELECT validation_policy_version FROM partitions "
                "WHERE year = 2026 AND month = 7 AND state = 'VERIFIED'"
            ).fetchall()
        ]
        assert (
            schedule_digests.count(
                "7c8cdef86c3874f9542a9544821805bfc23787975e29d0f297164776b5816db9"
            )
            == 49
        )
        assert (
            schedule_digests.count(
                "0fe8111d5993b20935484ab269c1a739757523011f1aacf23f6d3407bbe8b050"
            )
            == 1
        )
        snapshots = historical_upstox_raw.InstrumentSnapshotStoreV1(
            source, admission.lease, catalog
        )
        cohort: list[dict[str, Any]] = []
        for symbol in symbols:
            resolved = snapshots.resolve_equity(
                source="upstox-bod-nse",
                segment="NSE_EQ",
                symbol=symbol,
                as_of=metadata.retrieved_at,
            )
            instrument = resolved.instrument
            cohort.append(
                {
                    "isin": instrument.isin,
                    "exchange": "NSE",
                    "listed_equity_segment": "EQUITY",
                    "effective_symbol": instrument.symbol,
                    "symbol_effective_from": "2020-01-01",
                    "symbol_effective_to": None,
                    "provider_mapping": {
                        "provider": "UPSTOX",
                        "provider_instrument_id": instrument.instrument_key,
                        "mapping_effective_from": "2020-01-01",
                        "mapping_effective_to": None,
                        "mapping_evidence_known_at": metadata.retrieved_at.strftime(
                            "%Y-%m-%dT%H:%M:%S.%fZ"
                        ),
                        "mapping_evidence_sha256": metadata.observation_sha256,
                    },
                }
            )
    assert len(cohort) == 50
    request = _retained_request(
        "2026-07-01",
        "2026-07-31",
        _JULY_SESSIONS,
        "0fe8111d5993b20935484ab269c1a739757523011f1aacf23f6d3407bbe8b050",
    )
    request["cohort"] = sorted(
        cohort, key=lambda member: (member["isin"], member["exchange"])
    )
    identity = historical_upstox_raw.StorageRootLease.admit_existing_private_identity(
        tmp_path
    )
    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(request), source, tmp_path, identity
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.CONFLICTING_EVIDENCE
    assert not (tmp_path / "historical_ohlcv_revisions").exists()


def _retained_request(
    lower: str, upper: str, sessions: list[str], schedule_digest: str
) -> dict[str, object]:
    schema, runtime, configuration = (
        historical_upstox_raw.historical_upstox_raw_current_identities_v1()
    )
    return {
        "contract_version": historical_upstox_raw.COMPLETION_CONTRACT_VERSION,
        "revision_contract_version": historical_upstox_raw.REVISION_CONTRACT_VERSION,
        "research_scope": "FIXED_COHORT_RETROSPECTIVE",
        "source_profile": "UPSTOX_RAW",
        "operation": "INITIAL",
        "parent_revision_sha256": None,
        "correction_coordinates": [],
        "cohort": [
            {
                "isin": "INE002A01018",
                "exchange": "NSE",
                "listed_equity_segment": "EQUITY",
                "effective_symbol": "RELIANCE",
                "symbol_effective_from": "2020-01-01",
                "symbol_effective_to": None,
                "provider_mapping": {
                    "provider": "UPSTOX",
                    "provider_instrument_id": "NSE_EQ|INE002A01018",
                    "mapping_effective_from": "2020-01-01",
                    "mapping_effective_to": None,
                    "mapping_evidence_known_at": "2026-08-27T03:18:10.135710Z",
                    "mapping_evidence_sha256": (
                        "02e150b0b910f9ebe825b1c77f48126e4a0046073bf24ae767211fe66480bbf3"
                    ),
                },
            }
        ],
        "from_session": lower,
        "to_session": upper,
        "interval": "1d",
        "expected_sessions": sessions,
        "schedule_evidence_sha256": schedule_digest,
        "observed_at": "2026-08-28T00:00:00Z",
        "permitted_use": "OWNER_PRIVATE_RESEARCH",
        "price_basis": "RAW",
        "schema_identity_sha256": schema,
        "runtime_code_identity_sha256": runtime,
        "configuration_identity_sha256": configuration,
        "limits": historical_upstox_raw.completion_limits_v1(),
    }


def _synthetic_isin(index: int) -> str:
    prefix = f"INE{index:06d}A0"
    for digit in "0123456789":
        candidate = prefix + digit
        expanded = "".join(
            str(ord(value) - 55) if value.isalpha() else value for value in candidate
        )
        total = sum(
            (int(value) * 2 // 10 + int(value) * 2 % 10) if position % 2 else int(value)
            for position, value in enumerate(reversed(expanded))
        )
        if total % 10 == 0:
            return candidate
    raise AssertionError("synthetic ISIN checksum failed")


def _request() -> dict[str, object]:
    return {
        "contract_version": historical_upstox_raw.COMPLETION_CONTRACT_VERSION,
        "revision_contract_version": historical_upstox_raw.REVISION_CONTRACT_VERSION,
        "research_scope": "FIXED_COHORT_RETROSPECTIVE",
        "source_profile": "UPSTOX_RAW",
        "operation": "INITIAL",
        "parent_revision_sha256": None,
        "correction_coordinates": [],
        "cohort": [
            {
                "isin": "INE002A01018",
                "exchange": "NSE",
                "listed_equity_segment": "EQUITY",
                "effective_symbol": "RELIANCE",
                "symbol_effective_from": "2020-01-01",
                "symbol_effective_to": None,
                "provider_mapping": {
                    "provider": "UPSTOX",
                    "provider_instrument_id": "NSE_EQ|INE002A01018",
                    "mapping_effective_from": "2020-01-01",
                    "mapping_effective_to": None,
                    "mapping_evidence_known_at": "2026-08-27T03:18:10.135710Z",
                    "mapping_evidence_sha256": "0" * 64,
                },
            }
        ],
        "from_session": "2026-07-01",
        "to_session": "2026-07-01",
        "interval": "1d",
        "expected_sessions": ["2026-07-01"],
        "schedule_evidence_sha256": "0" * 64,
        "observed_at": "2026-08-28T00:00:00Z",
        "permitted_use": "OWNER_PRIVATE_RESEARCH",
        "price_basis": "RAW",
        "schema_identity_sha256": "0" * 64,
        "runtime_code_identity_sha256": "0" * 64,
        "configuration_identity_sha256": "0" * 64,
        "limits": historical_upstox_raw.completion_limits_v1(),
    }


def _request_with_current_identities() -> dict[str, object]:
    request = _request()
    schema, runtime, configuration = (
        historical_upstox_raw.historical_upstox_raw_current_identities_v1()
    )
    request["schema_identity_sha256"] = schema
    request["runtime_code_identity_sha256"] = runtime
    request["configuration_identity_sha256"] = configuration
    return request


def _private_roots_with_source_lock(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir(mode=0o700)
    destination.mkdir(mode=0o700)
    lock = source / ".ingestion.lock"
    lock.touch(mode=0o600)
    os.chmod(source, 0o700)
    os.chmod(destination, 0o700)
    os.chmod(lock, 0o600)
    assert stat.S_IMODE(source.stat().st_mode) == 0o700
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
    return source, destination


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _synthetic_source_root(parent: Path, name: str) -> Path:
    root = parent / name
    root.mkdir(mode=0o700)
    lock = root / ".ingestion.lock"
    lock.touch(mode=0o600)
    os.chmod(root, 0o700)
    os.chmod(lock, 0o600)
    return root


def _private_destination_root(parent: Path, name: str) -> Path:
    root = parent / name
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root


def _synthetic_source_snapshot(
    members: list[tuple[str, str]], retrieved_at: datetime
) -> FetchedInstrumentSnapshotV1:
    payload = _canonical(
        [
            {
                "instrument_key": f"NSE_EQ|{isin}",
                "segment": "NSE_EQ",
                "trading_symbol": symbol,
                "isin": isin,
                "instrument_type": "EQ",
                "exchange": "NSE",
            }
            for isin, symbol in members
        ]
    )
    compressed = gzip.compress(payload, mtime=0)
    return FetchedInstrumentSnapshotV1(
        retrieved_at=retrieved_at,
        observation_date=retrieved_at.date(),
        compressed_bytes=compressed,
        decompressed_bytes=payload,
        compressed_sha256=hashlib.sha256(compressed).hexdigest(),
        decompressed_sha256=hashlib.sha256(payload).hexdigest(),
        catalog=InstrumentCatalog.from_json_bytes(payload),
        etag=None,
        last_modified=None,
    )


def _seed_synthetic_retained_source(
    root: Path,
    members: list[tuple[str, str]],
    sessions: tuple[str, ...],
    *,
    known_at_by_month: dict[tuple[int, int], datetime],
    replacement_prices: dict[tuple[str, str], float] | None = None,
) -> tuple[str, InstrumentSnapshotMetadataV1]:
    session_dates = tuple(date.fromisoformat(session) for session in sessions)
    covered_from = date(session_dates[0].year, session_dates[0].month, 1)
    covered_to = (
        date(session_dates[-1].year, session_dates[-1].month + 1, 1) - timedelta(days=1)
        if session_dates[-1].month < 12
        else date(session_dates[-1].year, 12, 31)
    )
    closed_dates: list[ScheduleClosure] = []
    current = covered_from
    session_set = set(session_dates)
    while current <= covered_to:
        if current not in session_set:
            closed_dates.append(ScheduleClosure(current, "SYNTHETIC_CLOSED"))
        current += timedelta(days=1)
    schedule = ExpectedSessionSchedule(
        schema_version=3,
        source="nse-upstox-composed-calendar",
        source_release="composed-calendar@v1=" + "a" * 64,
        as_of=max(
            datetime(2026, 8, 27, 3, tzinfo=UTC),
            datetime.combine(covered_to + timedelta(days=1), datetime.min.time(), UTC),
        ),
        timezone="Asia/Kolkata",
        covered_from=covered_from,
        covered_to=covered_to,
        sessions=tuple(
            ScheduleSession(
                session,
                datetime(session.year, session.month, session.day, 3, 45, tzinfo=UTC),
                datetime(session.year, session.month, session.day, 10, tzinfo=UTC),
                "REGULAR",
            )
            for session in session_dates
        ),
        closures=tuple(closed_dates),
    )
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.outcome is LeaseOutcome.ACQUIRED and acquired.lease is not None
    with acquired.lease as lease:
        retained_schedule = ScheduleEvidenceStore(root, lease).retain(schedule)
    assert retained_schedule.outcome is ScheduleOutcome.RETAINED
    assert retained_schedule.digest is not None

    retrieved_at = datetime(2026, 8, 27, 3, 18, 10, 135710, tzinfo=UTC)
    fetched = _synthetic_source_snapshot(members, retrieved_at)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.outcome is LeaseOutcome.ACQUIRED and acquired.lease is not None
    with acquired.lease as lease, DuckDBCatalog(root) as catalog:
        metadata = InstrumentSnapshotStoreV1(root, lease, catalog).retain(fetched)

    replacement_prices = replacement_prices or {}
    grouped_sessions: dict[tuple[int, int], list[date]] = {}
    for session in session_dates:
        grouped_sessions.setdefault((session.year, session.month), []).append(session)
    manifests: list[tuple[PartitionManifest, PartitionManifest]] = []
    for member_index, (isin, symbol) in enumerate(members):
        for (year, month), month_sessions in grouped_sessions.items():
            plan = PlannedInstrumentMonth(
                "upstox",
                f"NSE_EQ|{isin}",
                isin,
                symbol,
                "NSE",
                "NSE_EQ",
                "EQ",
                "1m",
                year,
                month,
                date(year, month, 1),
                date(year, month + 1, 1) - timedelta(days=1)
                if month < 12
                else date(year, 12, 31),
            )
            known_at = known_at_by_month[(year, month)]
            candles = tuple(
                CanonicalCandle(
                    "upstox",
                    f"NSE_EQ|{isin}",
                    isin,
                    symbol,
                    "NSE",
                    "NSE_EQ",
                    "EQ",
                    None,
                    None,
                    None,
                    None,
                    "1m",
                    datetime(
                        session.year,
                        session.month,
                        session.day,
                        3,
                        45,
                        tzinfo=UTC,
                    )
                    + timedelta(minutes=minute),
                    replacement_prices.get(
                        (isin, session.isoformat()), float(100 + member_index)
                    ),
                    replacement_prices.get(
                        (isin, session.isoformat()), float(100 + member_index)
                    )
                    + 2,
                    replacement_prices.get(
                        (isin, session.isoformat()), float(100 + member_index)
                    )
                    - 1,
                    replacement_prices.get(
                        (isin, session.isoformat()), float(100 + member_index)
                    )
                    + 1,
                    1,
                    None,
                    known_at,
                    "upstox-historical-v3",
                    "raw",
                )
                for session in month_sessions
                for minute in range(375)
            )
            published = publish_partition(root, plan, candles)
            started = known_at - timedelta(minutes=1)
            active = PartitionManifest(
                1,
                plan,
                f"seed-{isin}-{year:04d}{month:02d}",
                None,
                ManifestState.IN_PROGRESS,
                ValidationOutcome.NOT_RUN,
                "nse-equity-month@v1+sessions-sha256:" + retained_schedule.digest,
                None,
                None,
                None,
                None,
                None,
                "upstox-historical-v3",
                started,
                started,
                started,
                None,
            )
            manifests.append(
                (
                    active,
                    verify_manifest(
                        active,
                        known_at,
                        published.actual_from_ts,
                        published.actual_to_ts,
                        published.row_count,
                        published.checksum_sha256,
                        published.canonical_path,
                    ),
                )
            )
    with DuckDBCatalog(root) as catalog:
        for active, verified in manifests:
            catalog.create_manifest(active)
            catalog.transition_manifest(active, verified)
    return retained_schedule.digest, metadata


def _synthetic_request(
    members: list[tuple[str, str]],
    sessions: tuple[str, ...],
    schedule_digest: str,
    metadata: InstrumentSnapshotMetadataV1,
    observed_at: str,
) -> dict[str, object]:
    request = _request_with_current_identities()
    request["cohort"] = [
        {
            "isin": isin,
            "exchange": "NSE",
            "listed_equity_segment": "EQUITY",
            "effective_symbol": symbol,
            "symbol_effective_from": "2020-01-01",
            "symbol_effective_to": None,
            "provider_mapping": {
                "provider": "UPSTOX",
                "provider_instrument_id": f"NSE_EQ|{isin}",
                "mapping_effective_from": "2020-01-01",
                "mapping_effective_to": None,
                "mapping_evidence_known_at": metadata.retrieved_at.strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ),
                "mapping_evidence_sha256": metadata.observation_sha256,
            },
        }
        for isin, symbol in members
    ]
    request["from_session"] = sessions[0]
    request["to_session"] = sessions[-1]
    request["expected_sessions"] = list(sessions)
    request["schedule_evidence_sha256"] = schedule_digest
    request["observed_at"] = observed_at
    return request


def _tree_bytes(root: Path) -> tuple[tuple[str, bytes], ...]:
    return tuple(
        sorted(
            (str(path.relative_to(root)), path.read_bytes())
            for path in root.rglob("*")
            if path.is_file()
        )
    )


def test_synthetic_fifty_member_initial_is_source_backed_exact_and_effect_free(
    tmp_path: Path, monkeypatch
) -> None:
    members = [(_synthetic_isin(index), f"SYM{index:02d}") for index in range(50)]
    source = _synthetic_source_root(tmp_path, "source")
    destination = _private_destination_root(tmp_path, "destination")
    session = ("2026-07-01",)
    schedule_digest, metadata = _seed_synthetic_retained_source(
        source,
        members,
        session,
        known_at_by_month={(2026, 7): datetime(2026, 8, 27, 4, tzinfo=UTC)},
    )
    request = _synthetic_request(
        members, session, schedule_digest, metadata, "2026-09-02T00:00:00Z"
    )
    source_before = _tree_bytes(source)

    def fail_if_reached(*_: object, **__: object) -> object:
        raise AssertionError(
            "provider, credential, HTTP, downloader, or yfinance reached"
        )

    monkeypatch.setattr(
        cli._LazyEnvironmentAccessTokenProvider, "get_access_token", fail_if_reached
    )
    monkeypatch.setattr(cli._HistoricalProviderSession, "fetch", fail_if_reached)
    monkeypatch.setattr(cli, "_default_download_service", fail_if_reached)
    monkeypatch.setattr(yfinance_adapter, "_public_download", fail_if_reached)

    identity = StorageRootLease.admit_existing_private_identity(destination)
    assert identity is not None
    first = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(request), source, destination, identity
    )
    retry = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(request), source, destination, identity
    )

    assert first.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert first.revision is not None and first.revision_sha256 is not None
    assert retry.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert retry.revision_sha256 == first.revision_sha256
    assert first.revision["lineage_depth"] == 0
    assert [row["isin"] for row in first.revision["bars"]] == [
        isin for isin, _ in members for _ in session
    ]
    assert [row["session"] for row in first.revision["bars"]] == list(session) * 50
    objects = (
        destination / "historical_ohlcv_revisions" / "upstox-raw" / "v1" / "objects"
    )
    artifact = json.loads(
        (objects / first.revision["source_artifact_sha256"]).read_bytes()
    )
    assert [value["isin"] for value in artifact["mapping_receipts"]] == [
        isin for isin, _ in members
    ]
    assert [value["isin"] for value in artifact["partition_receipts"]] == [
        isin for isin, _ in members
    ]
    assert [value["isin"] for value in artifact["bars"]] == [
        isin for isin, _ in members for _ in session
    ]
    assert _tree_bytes(source) == source_before
    readback = historical_revision_store.HistoricalOhlcvRevisionStoreV1(
        destination
    ).read_exact(first.revision_sha256)
    assert readback.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert readback.revision == first.revision


def test_synthetic_source_backed_append_copies_inherited_partition_receipts(
    tmp_path: Path,
) -> None:
    members = [(_synthetic_isin(0), "SYM00")]
    sessions = ("2026-07-01", "2026-07-02")
    source = _synthetic_source_root(tmp_path, "source")
    destination = _private_destination_root(tmp_path, "destination")
    schedule_digest, metadata = _seed_synthetic_retained_source(
        source,
        members,
        sessions,
        known_at_by_month={(2026, 7): datetime(2026, 8, 27, 4, tzinfo=UTC)},
    )
    parent_request = _synthetic_request(
        members, (sessions[0],), schedule_digest, metadata, "2026-09-02T00:00:00Z"
    )
    identity = StorageRootLease.admit_existing_private_identity(destination)
    assert identity is not None
    parent = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(parent_request), source, destination, identity
    )
    assert parent.revision is not None and parent.revision_sha256 is not None

    append_request = _synthetic_request(
        members, sessions, schedule_digest, metadata, "2026-09-03T00:00:00Z"
    )
    append_request["operation"] = "APPEND"
    append_request["parent_revision_sha256"] = parent.revision_sha256
    append = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(append_request), source, destination, identity
    )

    assert append.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert append.revision is not None
    objects = (
        destination / "historical_ohlcv_revisions" / "upstox-raw" / "v1" / "objects"
    )
    parent_artifact = json.loads(
        (objects / parent.revision["source_artifact_sha256"]).read_bytes()
    )
    append_artifact = json.loads(
        (objects / append.revision["source_artifact_sha256"]).read_bytes()
    )
    assert (
        parent_artifact["partition_receipts"][0]
        == append_artifact["partition_receipts"][0]
    )


def test_source_backed_append_propagates_parent_artifact_reader_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    members = [(_synthetic_isin(0), "SYM00")]
    sessions = ("2026-07-01", "2026-07-02")
    source = _synthetic_source_root(tmp_path, "source")
    destination = _private_destination_root(tmp_path, "destination")
    schedule_digest, metadata = _seed_synthetic_retained_source(
        source,
        members,
        sessions,
        known_at_by_month={(2026, 7): datetime(2026, 8, 27, 4, tzinfo=UTC)},
    )
    parent_request = _synthetic_request(
        members, (sessions[0],), schedule_digest, metadata, "2026-09-02T00:00:00Z"
    )
    identity = StorageRootLease.admit_existing_private_identity(destination)
    assert identity is not None
    parent = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(parent_request), source, destination, identity
    )
    assert parent.revision_sha256 is not None
    append_request = _synthetic_request(
        members, sessions, schedule_digest, metadata, "2026-09-03T00:00:00Z"
    )
    append_request["operation"] = "APPEND"
    append_request["parent_revision_sha256"] = parent.revision_sha256
    retained_before = _tree_bytes(destination)
    primary = RuntimeError("private-parent-artifact-reader-fault")

    def fail_parent_artifact(
        _: historical_revision_store.HistoricalOhlcvRevisionStoreV1,
        __: dict[str, Any],
        ___: int,
    ) -> dict[str, Any]:
        raise primary

    monkeypatch.setattr(
        historical_revision_store.HistoricalOhlcvRevisionStoreV1,
        "_artifact_for_revision",
        fail_parent_artifact,
    )

    with pytest.raises(RuntimeError) as raised:
        historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
            _canonical(append_request), source, destination, identity
        )

    assert raised.value is primary
    assert _tree_bytes(destination) == retained_before


def test_synthetic_source_backed_correction_replaces_only_named_month_coordinate(
    tmp_path: Path,
) -> None:
    members = [(_synthetic_isin(0), "SYM00")]
    sessions = ("2026-07-01", "2026-08-03")
    source = _synthetic_source_root(tmp_path, "source-initial")
    replacement_source = _synthetic_source_root(tmp_path, "source-replacement")
    destination = _private_destination_root(tmp_path, "destination")
    initial_times = {
        (2026, 7): datetime(2026, 9, 1, 4, tzinfo=UTC),
        (2026, 8): datetime(2026, 9, 1, 4, tzinfo=UTC),
    }
    schedule_digest, metadata = _seed_synthetic_retained_source(
        source, members, sessions, known_at_by_month=initial_times
    )
    replacement_schedule_digest, replacement_metadata = _seed_synthetic_retained_source(
        replacement_source,
        members,
        sessions,
        known_at_by_month={
            (2026, 7): initial_times[(2026, 7)],
            (2026, 8): datetime(2026, 9, 2, 4, tzinfo=UTC),
        },
        replacement_prices={(members[0][0], "2026-08-03"): 200.0},
    )
    assert replacement_schedule_digest == schedule_digest
    parent_request = _synthetic_request(
        members, sessions, schedule_digest, metadata, "2026-09-02T00:00:00Z"
    )
    identity = StorageRootLease.admit_existing_private_identity(destination)
    assert identity is not None
    parent = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(parent_request), source, destination, identity
    )
    assert parent.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert parent.revision is not None and parent.revision_sha256 is not None
    destination_before = _tree_bytes(destination)

    correction_request = _synthetic_request(
        members,
        sessions,
        replacement_schedule_digest,
        replacement_metadata,
        "2026-09-03T00:00:00Z",
    )
    correction_request["operation"] = "CORRECTION"
    correction_request["parent_revision_sha256"] = parent.revision_sha256
    correction_request["correction_coordinates"] = [
        {"isin": members[0][0], "exchange": "NSE", "session": "2026-08-03"}
    ]
    correction = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(correction_request), replacement_source, destination, identity
    )
    retry = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(correction_request), replacement_source, destination, identity
    )

    assert correction.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert correction.revision is not None and correction.revision_sha256 is not None
    assert retry.revision_sha256 == correction.revision_sha256
    assert correction.revision["lineage_depth"] == 1
    assert correction.revision["bars"][0] == parent.revision["bars"][0]
    corrected = next(
        row for row in correction.revision["bars"] if row["session"] == "2026-08-03"
    )
    parent_corrected = next(
        row for row in parent.revision["bars"] if row["session"] == "2026-08-03"
    )
    assert corrected["open"] == "200"
    assert corrected["known_at"] == "2026-09-02T04:00:00Z"
    assert corrected != parent_corrected
    assert all(
        (destination / relative).read_bytes() == raw
        for relative, raw in destination_before
    )
    objects = (
        destination / "historical_ohlcv_revisions" / "upstox-raw" / "v1" / "objects"
    )
    parent_artifact = json.loads(
        (objects / parent.revision["source_artifact_sha256"]).read_bytes()
    )
    correction_artifact = json.loads(
        (objects / correction.revision["source_artifact_sha256"]).read_bytes()
    )
    assert (
        parent_artifact["partition_receipts"][0]
        == correction_artifact["partition_receipts"][0]
    )
    assert (
        parent_artifact["partition_receipts"][1]["parquet_sha256"]
        != correction_artifact["partition_receipts"][1]["parquet_sha256"]
    )
    parent_readback = historical_revision_store.HistoricalOhlcvRevisionStoreV1(
        destination
    ).read_exact(parent.revision_sha256)
    correction_readback = historical_revision_store.HistoricalOhlcvRevisionStoreV1(
        destination
    ).read_exact(correction.revision_sha256)
    assert parent_readback.revision == parent.revision
    assert correction_readback.revision == correction.revision


def test_source_valid_missing_parent_precedes_destination_substitution(
    tmp_path: Path,
) -> None:
    members = [(_synthetic_isin(0), "SYM00")]
    sessions = ("2026-07-01",)
    source = _synthetic_source_root(tmp_path, "source")
    destination = _private_destination_root(tmp_path, "destination")
    schedule_digest, metadata = _seed_synthetic_retained_source(
        source,
        members,
        sessions,
        known_at_by_month={(2026, 7): datetime(2026, 8, 27, 4, tzinfo=UTC)},
    )
    request = _synthetic_request(
        members, sessions, schedule_digest, metadata, "2026-09-02T00:00:00Z"
    )
    request["operation"] = "CORRECTION"
    request["parent_revision_sha256"] = "a" * 64
    request["correction_coordinates"] = [
        {"isin": members[0][0], "exchange": "NSE", "session": sessions[0]}
    ]
    identity = StorageRootLease.admit_existing_private_identity(destination)
    assert identity is not None

    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(request), source, destination, None
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT
    assert not (destination / "historical_ohlcv_revisions").exists()


def test_schedule_absence_and_corruption_have_distinct_completion_outcomes(
    tmp_path: Path,
) -> None:
    members = [(_synthetic_isin(0), "SYM00")]
    sessions = ("2026-07-01",)
    for name, mutate, expected in (
        (
            "missing",
            lambda path: path.unlink(),
            HistoricalOhlcvImportOutcomeV1.INSUFFICIENT_EVIDENCE,
        ),
        (
            "corrupt",
            lambda path: (os.chmod(path, 0o600), path.write_bytes(b"corrupt")),
            HistoricalOhlcvImportOutcomeV1.CONFLICTING_EVIDENCE,
        ),
    ):
        source = _synthetic_source_root(tmp_path, f"source-{name}")
        destination = _private_destination_root(tmp_path, f"destination-{name}")
        schedule_digest, metadata = _seed_synthetic_retained_source(
            source,
            members,
            sessions,
            known_at_by_month={(2026, 7): datetime(2026, 8, 27, 4, tzinfo=UTC)},
        )
        schedule_path = (
            source / "calendar-schedules" / "sha256" / f"{schedule_digest}.json"
        )
        mutate(schedule_path)
        request = _synthetic_request(
            members, sessions, schedule_digest, metadata, "2026-09-02T00:00:00Z"
        )
        identity = StorageRootLease.admit_existing_private_identity(destination)
        assert identity is not None

        result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
            _canonical(request), source, destination, identity
        )

        assert result.outcome is expected
        assert not (destination / "historical_ohlcv_revisions").exists()


def test_substituted_catalog_evidence_is_conflicting(
    tmp_path: Path, monkeypatch
) -> None:
    members = [(_synthetic_isin(0), "SYM00")]
    sessions = ("2026-07-01",)
    source = _synthetic_source_root(tmp_path, "source")
    destination = _private_destination_root(tmp_path, "destination")
    schedule_digest, metadata = _seed_synthetic_retained_source(
        source,
        members,
        sessions,
        known_at_by_month={(2026, 7): datetime(2026, 8, 27, 4, tzinfo=UTC)},
    )
    request = _synthetic_request(
        members, sessions, schedule_digest, metadata, "2026-09-02T00:00:00Z"
    )
    identity = StorageRootLease.admit_existing_private_identity(destination)
    assert identity is not None

    monkeypatch.setattr(
        historical_upstox_raw,
        "_final_recheck_retained_source",
        lambda *_: (_ for _ in ()).throw(historical_upstox_raw.CatalogStorageError()),
    )
    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(request), source, destination, identity
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.CONFLICTING_EVIDENCE
    assert not (destination / "historical_ohlcv_revisions").exists()


@pytest.mark.parametrize(
    "defect",
    (
        AssertionError("injected assertion defect"),
        KeyError("injected key defect"),
        RuntimeError("injected runtime defect"),
        Exception("injected generic defect"),
        TypeError("injected type defect"),
        ValueError("injected value defect"),
    ),
    ids=("assertion", "key", "runtime", "generic", "type", "value"),
)
@pytest.mark.parametrize(
    "boundary",
    (
        "schedule",
        "snapshot",
        "coverage",
        "partition",
        "daily",
        "final-snapshot",
    ),
)
def test_unexpected_source_dependency_defects_propagate_without_destination_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    defect: Exception,
) -> None:
    members = [(_synthetic_isin(0), "SYM00")]
    sessions = ("2026-07-01",)
    source = _synthetic_source_root(tmp_path, f"{boundary}-source")
    destination = _private_destination_root(tmp_path, f"{boundary}-destination")
    schedule_digest, metadata = _seed_synthetic_retained_source(
        source,
        members,
        sessions,
        known_at_by_month={(2026, 7): datetime(2026, 8, 27, 4, tzinfo=UTC)},
    )
    request = _synthetic_request(
        members, sessions, schedule_digest, metadata, "2026-09-02T00:00:00Z"
    )
    identity = StorageRootLease.admit_existing_private_identity(destination)
    assert identity is not None
    before = _tree_bytes(destination)

    with monkeypatch.context() as patch:
        _UNEXPECTED_SOURCE_DEFECT_PATCHERS[boundary](
            patch, defect, source, schedule_digest
        )

        with pytest.raises(type(defect)) as raised:
            historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
                _canonical(request), source, destination, identity
            )

    assert raised.value is defect
    assert _tree_bytes(destination) == before


def _patch_schedule_defect(
    patch: pytest.MonkeyPatch, defect: Exception, source: Path, digest: str
) -> None:
    expected_schedule = (
        source / "calendar-schedules" / "sha256" / f"{digest}.json"
    ).read_bytes()
    original_closed_json = historical_upstox_raw._closed_json

    def fail_schedule(value: object, maximum: int) -> dict[str, Any]:
        if value == expected_schedule:
            raise defect
        return original_closed_json(value, maximum)

    patch.setattr(historical_upstox_raw, "_closed_json", fail_schedule)


def _patch_snapshot_defect(
    patch: pytest.MonkeyPatch, defect: Exception, _: Path, __: str
) -> None:
    def fail_snapshot(*_: object, **__: object) -> object:
        raise defect

    patch.setattr(InstrumentSnapshotStoreV1, "resolve_equity", fail_snapshot)


def _patch_coverage_defect(
    patch: pytest.MonkeyPatch, defect: Exception, _: Path, __: str
) -> None:
    def fail_coverage(*_: object, **__: object) -> object:
        raise defect

    patch.setattr(
        historical_upstox_raw.StoredCoverageEvaluatorV1,
        "evaluate_under_admission",
        fail_coverage,
    )


def _patch_partition_defect(
    patch: pytest.MonkeyPatch, defect: Exception, _: Path, __: str
) -> None:
    def fail_partition(*_: object, **__: object) -> object:
        raise defect

    patch.setattr(historical_upstox_raw, "read_partition_under_lease", fail_partition)


def _patch_daily_defect(
    patch: pytest.MonkeyPatch, defect: Exception, _: Path, __: str
) -> None:
    def fail_daily(*_: object, **__: object) -> object:
        raise defect

    patch.setattr(historical_upstox_raw.DuckDBDailyOHLCVEngineV1, "execute", fail_daily)


def _patch_final_snapshot_defect(
    patch: pytest.MonkeyPatch, defect: Exception, _: Path, __: str
) -> None:
    original_recheck = historical_upstox_raw._final_recheck_retained_source

    def fail_final_snapshot(*args: Any) -> None:
        with patch.context() as final_patch:

            def fail_snapshot(*_: object, **__: object) -> object:
                raise defect

            final_patch.setattr(
                InstrumentSnapshotStoreV1, "resolve_equity", fail_snapshot
            )
            original_recheck(*args)

    patch.setattr(
        historical_upstox_raw,
        "_final_recheck_retained_source",
        fail_final_snapshot,
    )


_UNEXPECTED_SOURCE_DEFECT_PATCHERS: dict[
    str, Callable[[pytest.MonkeyPatch, Exception, Path, str], None]
] = {
    "schedule": _patch_schedule_defect,
    "snapshot": _patch_snapshot_defect,
    "coverage": _patch_coverage_defect,
    "partition": _patch_partition_defect,
    "daily": _patch_daily_defect,
    "final-snapshot": _patch_final_snapshot_defect,
}


def test_projection_catalog_storage_error_is_conflicting(
    tmp_path: Path, monkeypatch
) -> None:
    members = [(_synthetic_isin(0), "SYM00")]
    sessions = ("2026-07-01",)
    source = _synthetic_source_root(tmp_path, "source")
    destination = _private_destination_root(tmp_path, "destination")
    schedule_digest, metadata = _seed_synthetic_retained_source(
        source,
        members,
        sessions,
        known_at_by_month={(2026, 7): datetime(2026, 8, 27, 4, tzinfo=UTC)},
    )
    request = _synthetic_request(
        members, sessions, schedule_digest, metadata, "2026-09-02T00:00:00Z"
    )
    identity = StorageRootLease.admit_existing_private_identity(destination)
    assert identity is not None

    def missing_catalog(*_: object, **__: object) -> object:
        raise historical_upstox_raw.CatalogStorageError()

    monkeypatch.setattr(historical_upstox_raw, "DuckDBCatalog", missing_catalog)
    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(request), source, destination, identity
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.CONFLICTING_EVIDENCE
    assert not (destination / "historical_ohlcv_revisions").exists()


def test_final_recheck_source_root_substitution_is_conflicting(
    tmp_path: Path, monkeypatch
) -> None:
    members = [(_synthetic_isin(0), "SYM00")]
    sessions = ("2026-07-01",)
    source = _synthetic_source_root(tmp_path, "source")
    destination = _private_destination_root(tmp_path, "destination")
    schedule_digest, metadata = _seed_synthetic_retained_source(
        source,
        members,
        sessions,
        known_at_by_month={(2026, 7): datetime(2026, 8, 27, 4, tzinfo=UTC)},
    )
    request = _synthetic_request(
        members, sessions, schedule_digest, metadata, "2026-09-02T00:00:00Z"
    )
    identity = StorageRootLease.admit_existing_private_identity(destination)
    assert identity is not None
    original_final_recheck = historical_upstox_raw._final_recheck_retained_source

    def substitute_source(*args: object) -> None:
        source.rename(source.with_name("moved-source"))
        source.mkdir(mode=0o700)
        original_final_recheck(*args)

    monkeypatch.setattr(
        historical_upstox_raw, "_final_recheck_retained_source", substitute_source
    )
    result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
        _canonical(request), source, destination, identity
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.CONFLICTING_EVIDENCE
    assert not (destination / "historical_ohlcv_revisions").exists()


def test_partition_digest_substitution_conflicts_before_and_during_final_recheck(
    tmp_path: Path, monkeypatch
) -> None:
    def complete_with_substitution(
        name: str, substituted_call: int
    ) -> HistoricalOhlcvImportOutcomeV1:
        members = [(_synthetic_isin(0), "SYM00")]
        sessions = ("2026-07-01",)
        source = _synthetic_source_root(tmp_path, f"{name}-source")
        destination = _private_destination_root(tmp_path, f"{name}-destination")
        schedule_digest, metadata = _seed_synthetic_retained_source(
            source,
            members,
            sessions,
            known_at_by_month={(2026, 7): datetime(2026, 8, 27, 4, tzinfo=UTC)},
        )
        request = _synthetic_request(
            members, sessions, schedule_digest, metadata, "2026-09-02T00:00:00Z"
        )
        identity = StorageRootLease.admit_existing_private_identity(destination)
        assert identity is not None
        original_reader = historical_upstox_raw.read_partition_under_lease
        calls = 0

        def substituted_reader(*args: object, **kwargs: object) -> object:
            nonlocal calls
            digest, candles = original_reader(*args, **kwargs)
            calls += 1
            if calls == substituted_call:
                return "0" * 64, candles
            return digest, candles

        with monkeypatch.context() as patch:
            patch.setattr(
                historical_upstox_raw,
                "read_partition_under_lease",
                substituted_reader,
            )
            result = historical_upstox_raw.complete_upstox_raw_historical_ohlcv_v1(
                _canonical(request), source, destination, identity
            )
        assert not (destination / "historical_ohlcv_revisions").exists()
        return result.outcome

    assert (
        complete_with_substitution("projection", 1)
        is HistoricalOhlcvImportOutcomeV1.CONFLICTING_EVIDENCE
    )
    assert (
        complete_with_substitution("final-recheck", 2)
        is HistoricalOhlcvImportOutcomeV1.CONFLICTING_EVIDENCE
    )


def test_daily_volume_int64_boundary_is_closed() -> None:
    assert historical_upstox_raw._volume(2**63 - 1) == str(2**63 - 1)  # pyright: ignore[reportPrivateUsage]
    try:
        historical_upstox_raw._volume(2**63)  # pyright: ignore[reportPrivateUsage]
    except historical_upstox_raw._Invalid:
        pass
    else:
        raise AssertionError("daily volume above signed int64 must be invalid")
