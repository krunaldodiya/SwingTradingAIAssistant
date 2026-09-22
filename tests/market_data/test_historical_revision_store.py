# pyright: reportPrivateUsage=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false
from __future__ import annotations

import hashlib
import json
import os
import stat
from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from swing_trading_ai_assistant.market_data import cli, historical_upstox_raw
from swing_trading_ai_assistant.market_data import (
    historical_revision_store as store_module,
)
from swing_trading_ai_assistant.market_data.historical_revision_store import (
    HistoricalOhlcvImportOutcomeV1,
    HistoricalOhlcvRevisionStoreV1,
    historical_upstox_raw_current_identities_v1,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleSession,
    canonical_schedule_bytes,
)


def test_raw_initial_replay_is_content_addressed_and_exact_readable(
    tmp_path: Path,
) -> None:
    first = _publish(tmp_path, _inputs())
    replay = _publish(tmp_path, _inputs())

    assert first.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert replay.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert replay.revision_sha256 == first.revision_sha256
    assert replay.revision == first.revision
    assert (
        HistoricalOhlcvRevisionStoreV1(tmp_path).read_exact(first.revision_sha256)
        == first
    )


@pytest.mark.parametrize("cleanup_fault", [False, True])
def test_replay_reader_fault_propagates_without_further_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_fault: bool
) -> None:
    published = _publish(tmp_path, _inputs())
    assert published.revision_sha256 is not None
    retained_before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    primary = RuntimeError("private-replay-reader-fault")
    original_read_object = store_module._read_object
    original_publish_object = store_module._publish_object
    original_open_directory = store_module._open_directory
    original_close = store_module.os.close
    owned: set[int] = set()
    cleaned = 0
    faulted = False
    publication_calls = 0

    def fail_replay_read(
        parent: int,
        name: str,
        maximum: int,
        expected_identity: tuple[int, int] | None = None,
    ) -> bytes:
        nonlocal faulted
        if name == f"{published.revision_sha256}.json" and not faulted:
            faulted = True
            raise primary
        return original_read_object(parent, name, maximum, expected_identity)

    def track_directory(parent: int, name: str) -> int:
        descriptor = original_open_directory(parent, name)
        owned.add(descriptor)
        return descriptor

    def close_directory(descriptor: int) -> None:
        nonlocal cleaned
        tracked = descriptor in owned
        owned.discard(descriptor)
        original_close(descriptor)
        if tracked:
            cleaned += 1
            if cleanup_fault:
                raise TypeError("private-publication-cleanup-fault")

    def count_publication(parent: int, name: str, raw: bytes) -> bool:
        nonlocal publication_calls
        publication_calls += 1
        return original_publish_object(parent, name, raw)

    monkeypatch.setattr(store_module, "_read_object", fail_replay_read)
    monkeypatch.setattr(store_module, "_publish_object", count_publication)
    monkeypatch.setattr(store_module, "_open_directory", track_directory)
    monkeypatch.setattr(store_module.os, "close", close_directory)

    with pytest.raises(RuntimeError) as raised:
        _publish(tmp_path, _inputs())

    assert raised.value is primary
    assert faulted
    assert publication_calls == 0
    assert not owned
    assert cleaned > 0
    assert {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == retained_before


def test_parent_artifact_reader_preserves_primary_through_cleanup_faults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published = _publish(tmp_path, _inputs())
    assert published.revision_sha256 is not None
    retained_before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    primary = RuntimeError("private-parent-artifact-fault")
    original_open = store_module._open_existing_directory
    original_close = store_module.os.close
    opened: set[int] = set()
    attempted_cleanup: list[int] = []

    def track_open(parent: int, name: str) -> int:
        descriptor = original_open(parent, name)
        opened.add(descriptor)
        return descriptor

    def fail_parent_artifact(
        _: HistoricalOhlcvRevisionStoreV1, __: dict[str, Any], ___: int
    ) -> dict[str, Any]:
        raise primary

    def fail_secondary_cleanup(descriptor: int) -> None:
        original_close(descriptor)
        if descriptor in opened:
            attempted_cleanup.append(descriptor)
            raise RuntimeError("private-secondary-cleanup-fault")

    monkeypatch.setattr(store_module, "_open_existing_directory", track_open)
    monkeypatch.setattr(
        HistoricalOhlcvRevisionStoreV1, "_artifact_for_revision", fail_parent_artifact
    )
    monkeypatch.setattr(store_module.os, "close", fail_secondary_cleanup)

    with pytest.raises(RuntimeError) as raised:
        HistoricalOhlcvRevisionStoreV1(tmp_path)._read_exact_source_artifact(  # pyright: ignore[reportPrivateUsage]
            published.revision_sha256
        )

    assert raised.value is primary
    assert len(attempted_cleanup) == 5
    assert {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == retained_before


@pytest.mark.parametrize("fault_type", (RuntimeError, TypeError, ValueError))
def test_exact_read_preserves_unknown_validation_helper_fault(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault_type: type[Exception],
) -> None:
    published = _publish(tmp_path, _inputs())
    assert published.revision_sha256 is not None
    calls = 0

    def fail_schedule_decoder(_: object) -> object:
        nonlocal calls
        calls += 1
        raise fault_type("private-retained-validation-fault")

    monkeypatch.setattr(
        store_module, "parse_canonical_schedule_bytes", fail_schedule_decoder
    )

    with pytest.raises(fault_type, match="private-retained-validation-fault"):
        HistoricalOhlcvRevisionStoreV1(tmp_path).read_exact(published.revision_sha256)

    assert calls == 1


@pytest.mark.parametrize(
    "fault_type",
    (AssertionError, KeyError, RuntimeError, TypeError, ValueError, Exception),
)
def test_exact_read_console_propagates_lower_reader_fault_through_secondary_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fault_type: type[Exception],
) -> None:
    published = _publish(tmp_path, _inputs())
    assert published.revision_sha256 is not None
    retained_before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    original_read = store_module.os.read
    original_close = store_module.os.close
    fault_descriptor: int | None = None
    cleanup_faulted = False

    def fault_retained_object_read(descriptor: int, maximum: int) -> bytes:
        nonlocal fault_descriptor
        if fault_descriptor is None and stat.S_ISREG(os.fstat(descriptor).st_mode):
            fault_descriptor = descriptor
            raise fault_type("private-retained-reader-fault")
        return original_read(descriptor, maximum)

    def fail_secondary_cleanup(descriptor: int) -> None:
        nonlocal cleanup_faulted
        if descriptor == fault_descriptor:
            original_close(descriptor)
            cleanup_faulted = True
            raise TypeError("private-secondary-cleanup-fault")
        original_close(descriptor)

    monkeypatch.setattr(store_module.os, "read", fault_retained_object_read)
    monkeypatch.setattr(store_module.os, "close", fail_secondary_cleanup)

    assert (
        cli.main(
            [
                "historical-ohlcv-upstox-raw-read",
                "--storage-root",
                str(tmp_path),
                "--revision-sha256",
                published.revision_sha256,
                "--output",
                "json",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()

    assert fault_descriptor is not None
    assert cleanup_faulted
    assert captured.out == ""
    assert captured.err == "internal_error\n"
    assert "private-retained-reader-fault" not in captured.err
    assert "private-secondary-cleanup-fault" not in captured.err
    assert {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == retained_before


def test_divergent_second_initial_has_no_publication_effect(tmp_path: Path) -> None:
    first = _publish(tmp_path, _inputs())
    assert first.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    root = tmp_path / "historical_ohlcv_revisions" / "upstox-raw" / "v1"
    objects = root / "objects"
    revisions = root / "revisions"
    before_objects = {path.name: path.read_bytes() for path in objects.iterdir()}
    before_revisions = {path.name: path.read_bytes() for path in revisions.iterdir()}

    divergent = _publish(tmp_path, _inputs(open_value="101"))

    assert (
        divergent.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert {
        path.name: path.read_bytes() for path in objects.iterdir()
    } == before_objects
    assert {
        path.name: path.read_bytes() for path in revisions.iterdir()
    } == before_revisions


def test_append_and_correction_preserve_predecessor_bytes(tmp_path: Path) -> None:
    parent = _publish(tmp_path, _inputs())
    assert parent.revision is not None and parent.revision_sha256 is not None
    parent_bytes = _read_revision_bytes(tmp_path, parent.revision_sha256)

    appended = _publish(
        tmp_path,
        _inputs(
            operation="APPEND",
            parent=parent.revision_sha256,
            sessions=("2026-07-01", "2026-07-02"),
            upper="2026-07-02",
        ),
    )
    assert appended.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert _read_revision_bytes(tmp_path, parent.revision_sha256) == parent_bytes

    corrected = _publish(
        tmp_path,
        _inputs(
            operation="CORRECTION",
            parent=parent.revision_sha256,
            corrections=[
                {"isin": "INE002A01018", "exchange": "NSE", "session": "2026-07-01"}
            ],
            open_value="101",
        ),
    )
    assert corrected.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert _read_revision_bytes(tmp_path, parent.revision_sha256) == parent_bytes


@pytest.mark.parametrize(
    "raw",
    (
        b"{}",
        b'{"operation":"INITIAL","operation":"INITIAL"}',
        b'{"nested":1.0}',
        b'{"nested":NaN}',
        b"[1]",
        b'{"nested": ' + b"[" * 65 + b"0" + b"]" * 65 + b"}",
    ),
)
def test_hostile_json_is_rejected_before_storage_effect(
    tmp_path: Path, raw: bytes
) -> None:
    result = HistoricalOhlcvRevisionStoreV1(tmp_path)._publish_generated_source(  # pyright: ignore[reportPrivateUsage]
        raw,
        b"{}",
        b"{}",
        b"{}",
        completion_request_identity_sha256=_sha(b"operator"),
    )
    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT
    assert not (tmp_path / "historical_ohlcv_revisions").exists()


def test_old_adjusted_or_operator_local_candidate_is_unsupported(
    tmp_path: Path,
) -> None:
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs()
    request = json.loads(request_raw)
    request["price_basis"] = "SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED"
    request_raw = _canonical(request)

    result = HistoricalOhlcvRevisionStoreV1(tmp_path)._publish_generated_source(  # pyright: ignore[reportPrivateUsage]
        request_raw,
        policy_raw,
        artifact_raw,
        receipt_raw,
        completion_request_identity_sha256=_sha(b"operator"),
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY
    assert not (tmp_path / "historical_ohlcv_revisions").exists()


def test_invalid_bar_envelope_precedes_missing_parent(tmp_path: Path) -> None:
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs(
        operation="APPEND", parent=_sha(b"missing")
    )
    artifact = json.loads(artifact_raw)
    artifact["bars"][0]["low"] = "101"
    artifact_raw = _canonical(artifact)
    request = json.loads(request_raw)
    request["source_artifact_sha256"] = _sha(artifact_raw)
    policy = json.loads(policy_raw)
    policy["artifact_sha256"] = _sha(artifact_raw)
    policy_raw = _canonical(policy)
    receipt = json.loads(receipt_raw)
    receipt["source_policy_sha256"] = _sha(policy_raw)
    receipt["source_artifact_sha256"] = _sha(artifact_raw)
    receipt_raw = _canonical(receipt)
    request["source_policy_sha256"] = _sha(policy_raw)
    request["receipt_sha256"] = _sha(receipt_raw)

    result = HistoricalOhlcvRevisionStoreV1(tmp_path)._publish_generated_source(  # pyright: ignore[reportPrivateUsage]
        _canonical(request),
        policy_raw,
        artifact_raw,
        receipt_raw,
        completion_request_identity_sha256=_sha(b"operator"),
    )
    assert result.outcome is HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE


def test_source_objects_and_revision_are_immutable_0400(tmp_path: Path) -> None:
    result = _publish(tmp_path, _inputs())
    assert result.revision_sha256 is not None and result.revision is not None
    root = tmp_path / "historical_ohlcv_revisions" / "upstox-raw" / "v1"
    names = [
        result.revision_sha256 + ".json",
        result.revision["source_policy_sha256"],
        result.revision["source_artifact_sha256"],
        result.revision["receipt_sha256"],
    ]
    directories = [
        root / "revisions",
        root / "objects",
        root / "objects",
        root / "objects",
    ]
    assert [
        os.stat(directory / name).st_mode & 0o777
        for directory, name in zip(directories, names, strict=True)
    ] == [0o400] * 4


def test_group_accessible_root_is_effect_free(tmp_path: Path) -> None:
    tmp_path.chmod(0o750)
    result = HistoricalOhlcvRevisionStoreV1(tmp_path)._publish_generated_source(  # pyright: ignore[reportPrivateUsage]
        *_inputs(), completion_request_identity_sha256=_sha(b"operator")
    )
    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )


def test_publication_fault_retains_visible_content_addressed_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    original = store_module._publish_object

    def fail_after_first(parent: int, name: str, raw: bytes) -> bool:
        nonlocal calls
        calls += 1
        published = original(parent, name, raw)
        if calls == 1:
            raise OSError("injected")
        return published

    monkeypatch.setattr(store_module, "_publish_object", fail_after_first)
    result = HistoricalOhlcvRevisionStoreV1(tmp_path)._publish_generated_source(  # pyright: ignore[reportPrivateUsage]
        *_inputs(), completion_request_identity_sha256=_sha(b"operator")
    )
    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    objects = tmp_path / "historical_ohlcv_revisions" / "upstox-raw" / "v1" / "objects"
    assert objects.exists() and any(objects.iterdir())


def test_decimal_canonicalization_and_runtime_identity_are_closed() -> None:
    assert store_module._decimal("123.45", positive=True) == "123.45"
    assert store_module._decimal("1.0", positive=True) is None
    schema, runtime, configuration = historical_upstox_raw_current_identities_v1()
    assert schema == "97974bbe56885a032b0ffad83dc8c1e0b41c999b84ee748c680613eeecb091e5"
    assert all(
        len(value) == 64 and value.islower()
        for value in (schema, runtime, configuration)
    )


_LEGACY_SCHEMA_IDENTITY_V1 = (
    "223b4f56cbb3dcb9a3d4a7408bc542266b279861fcf458d5b6d7e4c4e52aa196"
)


def test_old_schema_write_is_rejected_before_destination_effect(tmp_path: Path) -> None:
    request, policy, artifact, receipt = _candidate_objects_from(_inputs())
    request["schema_identity_sha256"] = _LEGACY_SCHEMA_IDENTITY_V1

    result = HistoricalOhlcvRevisionStoreV1(tmp_path)._publish_generated_source(  # pyright: ignore[reportPrivateUsage]
        _canonical(request),
        _canonical(policy),
        _canonical(artifact),
        _canonical(receipt),
        completion_request_identity_sha256=_sha(b"operator"),
    )

    assert result.outcome is HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT
    assert not (tmp_path / "historical_ohlcv_revisions").exists()


def test_old_schema_revision_remains_exact_readable(tmp_path: Path) -> None:
    published = _publish(tmp_path, _inputs())
    assert published.revision_sha256 is not None
    legacy_id, legacy_raw = _rewrite_initial_revision_schema(
        tmp_path, published.revision_sha256, _LEGACY_SCHEMA_IDENTITY_V1
    )

    readback = HistoricalOhlcvRevisionStoreV1(tmp_path).read_exact(legacy_id)

    assert readback.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert readback.revision_sha256 == legacy_id
    assert _read_revision_bytes(tmp_path, legacy_id) == legacy_raw


def test_current_successor_accepts_exact_readable_old_schema_parent(
    tmp_path: Path,
) -> None:
    parent = _publish(tmp_path, _inputs())
    assert parent.revision_sha256 is not None
    legacy_id, _ = _rewrite_initial_revision_schema(
        tmp_path, parent.revision_sha256, _LEGACY_SCHEMA_IDENTITY_V1
    )

    successor = _publish(
        tmp_path,
        _inputs(
            operation="APPEND",
            parent=legacy_id,
            sessions=("2026-07-01", "2026-07-02"),
            upper="2026-07-02",
        ),
    )

    assert successor.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert successor.revision is not None
    assert (
        successor.revision["schema_identity_sha256"]
        == (historical_upstox_raw_current_identities_v1()[0])
    )


def test_generated_candidate_rejects_raw_disclosure_mutations() -> None:
    for field, value in (
        ("price_basis", "ADJUSTED"),
        ("adjustment_state", "adjusted"),
        ("temporal_status", "PIT"),
        ("corporate_action_status", "EVALUATED"),
        ("comparability_status", "ESTABLISHED"),
    ):
        request, policy, artifact, receipt = _candidate_objects()
        receipt[field] = value

        assert not _generated_candidate_is_valid(request, policy, artifact, receipt)


def test_exact_read_rejects_recomputed_source_literal_mutations(
    tmp_path: Path,
) -> None:
    published = _publish(tmp_path, _inputs())
    assert published.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    root = tmp_path / "historical_ohlcv_revisions" / "upstox-raw" / "v1"
    objects = root / "objects"
    revisions = root / "revisions"

    for target, field, value in (
        ("policy", "temporal_status", "PIT"),
        ("policy", "corporate_action_status", "EVALUATED"),
        ("policy", "comparability_status", "ESTABLISHED"),
        ("artifact", "schema_version", "other-artifact@v1"),
        ("artifact", "source_profile", "OTHER"),
    ):
        request, policy, artifact, receipt = _candidate_objects()
        source = policy if target == "policy" else artifact
        source[field] = value
        _refresh_candidate_chain(request, policy, artifact, receipt)
        assert not _generated_candidate_is_valid(request, policy, artifact, receipt)

        policy_raw = _canonical(policy)
        artifact_raw = _canonical(artifact)
        receipt_raw = _canonical(receipt)
        revision = store_module._revision_value(
            request,
            cast(list[dict[str, Any]], artifact["bars"]),
            0,
            _sha(b"operator"),
        )
        revision_raw = _canonical(revision)
        for name, raw in (
            (request["source_policy_sha256"], policy_raw),
            (request["source_artifact_sha256"], artifact_raw),
            (request["receipt_sha256"], receipt_raw),
        ):
            path = objects / name
            if path.exists():
                assert path.read_bytes() == raw
            else:
                path.write_bytes(raw)
                path.chmod(0o400)
        revision_path = revisions / f"{revision['revision_sha256']}.json"
        revision_path.write_bytes(revision_raw)
        revision_path.chmod(0o400)

        result = HistoricalOhlcvRevisionStoreV1(tmp_path).read_exact(
            revision["revision_sha256"]
        )
        assert (
            result.outcome
            is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
        )


def test_generated_candidate_rejects_closed_receipt_and_volume_mutations() -> None:
    request, policy, artifact, receipt = _candidate_objects()
    artifact["bars"][0]["volume"] = str(2**63)
    _refresh_candidate_digests(policy, artifact, receipt)
    assert not _generated_candidate_is_valid(request, policy, artifact, receipt)

    request, policy, artifact, receipt = _candidate_objects()
    mapping = artifact["mapping_receipts"][0]
    mapping["resolved_security_id"] = "OTHER"
    _refresh_mapping_identity(mapping)
    _refresh_candidate_digests(policy, artifact, receipt)
    assert not _generated_candidate_is_valid(request, policy, artifact, receipt)

    request, policy, artifact, receipt = _candidate_objects()
    partition = artifact["partition_receipts"][0]
    partition["plan_security_id"] = "OTHER"
    _refresh_partition_identity(partition)
    _refresh_candidate_digests(policy, artifact, receipt)
    assert not _generated_candidate_is_valid(request, policy, artifact, receipt)
    for target, field, value, refresh in (
        (
            "mapping",
            "relative_object_path",
            "instrument_snapshots/sha256=" + "d" * 64 + "/snapshot.json.gz",
            _refresh_mapping_identity,
        ),
        ("mapping", "snapshot_schema_version", 2, _refresh_mapping_identity),
        ("partition", "plan_from_date", "2026-07-02", _refresh_partition_identity),
        ("partition", "plan_to_date", "2026-07-30", _refresh_partition_identity),
        (
            "partition",
            "canonical_path",
            "candles/other.parquet",
            _refresh_partition_identity,
        ),
        ("partition", "candle_schema_version", 2, _refresh_partition_identity),
    ):
        request, policy, artifact, receipt = _candidate_objects()
        receipt_value = artifact[f"{target}_receipts"][0]
        receipt_value[field] = value
        refresh(receipt_value)
        _refresh_candidate_digests(policy, artifact, receipt)
        assert not _generated_candidate_is_valid(request, policy, artifact, receipt)
    request, policy, artifact, receipt = _candidate_objects()
    receipt["source_policy_sha256"] = "e" * 64
    assert not _generated_candidate_is_valid(request, policy, artifact, receipt)


@pytest.mark.parametrize(
    ("field", "maximum"),
    (
        ("compressed_byte_count", 4_000_000),
        ("decompressed_byte_count", 50_000_000),
    ),
)
def test_mapping_receipt_byte_count_bounds_reject_recomputed_candidates_and_exact_reads(
    tmp_path: Path, field: str, maximum: int
) -> None:
    request, policy, artifact, receipt = _candidate_objects()
    mapping = artifact["mapping_receipts"][0]
    mapping[field] = maximum
    _refresh_mapping_identity(mapping)
    _refresh_candidate_chain(request, policy, artifact, receipt)

    assert _generated_candidate_is_valid(request, policy, artifact, receipt)
    accepted = HistoricalOhlcvRevisionStoreV1(tmp_path)._publish_generated_source(  # pyright: ignore[reportPrivateUsage]
        _canonical(request),
        _canonical(policy),
        _canonical(artifact),
        _canonical(receipt),
        completion_request_identity_sha256=_sha(b"operator"),
    )
    assert accepted.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert accepted.revision_sha256 is not None
    assert (
        HistoricalOhlcvRevisionStoreV1(tmp_path).read_exact(accepted.revision_sha256)
        == accepted
    )

    for invalid in (-1, maximum + 1):
        request, policy, artifact, receipt = _candidate_objects()
        mapping = artifact["mapping_receipts"][0]
        mapping[field] = invalid
        _refresh_mapping_identity(mapping)
        _refresh_candidate_chain(request, policy, artifact, receipt)

        assert not _generated_candidate_is_valid(request, policy, artifact, receipt)
        revision_id = _write_recomputed_candidate_for_exact_read(
            tmp_path, request, policy, artifact, receipt
        )
        assert (
            HistoricalOhlcvRevisionStoreV1(tmp_path).read_exact(revision_id).outcome
            is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
        )


@pytest.mark.parametrize("field", ("etag", "last_modified"))
def test_mapping_receipt_nullable_snapshot_headers_have_retained_bounds(
    field: str,
) -> None:
    for value in ("a" * 65, "a" * 512):
        request, policy, artifact, receipt = _candidate_objects()
        mapping = artifact["mapping_receipts"][0]
        mapping[field] = value
        _refresh_mapping_identity(mapping)
        _refresh_candidate_chain(request, policy, artifact, receipt)

        assert _generated_candidate_is_valid(request, policy, artifact, receipt)

    for value in ("", "\x1f", "a" * 513):
        request, policy, artifact, receipt = _candidate_objects()
        mapping = artifact["mapping_receipts"][0]
        mapping[field] = value
        _refresh_mapping_identity(mapping)
        _refresh_candidate_chain(request, policy, artifact, receipt)

        assert not _generated_candidate_is_valid(request, policy, artifact, receipt)


@pytest.mark.parametrize(
    "mutation",
    (
        {"ingestion_run_id": ""},
        {"ingestion_run_id": " run"},
        {"validation_policy_version": ""},
        {"validation_policy_version": "policy@v1 "},
        {"actual_from_ts": ""},
        {"actual_from_ts": "2026-07-01T03:45:00.1Z"},
        {"actual_to_ts": "not-an-instant"},
        {
            "actual_from_ts": "2026-07-01T10:00:00.000000Z",
            "actual_to_ts": "2026-07-01T03:45:00.000000Z",
        },
    ),
)
def test_partition_receipt_semantics_reject_recomputed_candidates_and_exact_reads(
    tmp_path: Path, mutation: dict[str, str]
) -> None:
    accepted = _publish(tmp_path, _inputs())
    assert accepted.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    request, policy, artifact, receipt = _candidate_objects()
    partition = artifact["partition_receipts"][0]
    partition.update(mutation)
    _refresh_partition_identity(partition)
    _refresh_candidate_chain(request, policy, artifact, receipt)

    assert not _generated_candidate_is_valid(request, policy, artifact, receipt)
    revision_id = _write_recomputed_candidate_for_exact_read(
        tmp_path, request, policy, artifact, receipt
    )
    assert (
        HistoricalOhlcvRevisionStoreV1(tmp_path).read_exact(revision_id).outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )


def test_partition_receipt_canonical_text_and_retained_instant_boundaries_are_admitted() -> (
    None
):
    request, policy, artifact, receipt = _candidate_objects()
    partition = artifact["partition_receipts"][0]
    partition.update(
        {
            "ingestion_run_id": "r",
            "validation_policy_version": "p",
            "actual_from_ts": "2026-07-01T03:45:00.000000Z",
            "actual_to_ts": "2026-07-01T03:45:00.000000Z",
        }
    )
    _refresh_partition_identity(partition)
    _refresh_candidate_chain(request, policy, artifact, receipt)

    assert _generated_candidate_is_valid(request, policy, artifact, receipt)


def test_operator_observed_at_rejects_fractional_instants() -> None:
    request, policy, artifact, receipt = _candidate_objects()
    assert request["observed_at"] == "2026-08-27T04:00:00Z"
    assert receipt["observed_at"] == "2026-08-27T04:00:00Z"
    assert artifact["mapping_receipts"][0]["retrieved_at"].endswith(".135710Z")
    assert artifact["mapping_receipts"][0]["mapping_known_at"].endswith(".135710Z")
    assert _generated_candidate_is_valid(request, policy, artifact, receipt)

    observed_at = "2026-08-27T04:00:00.000001Z"
    request["observed_at"] = observed_at
    receipt["observed_at"] = observed_at
    _refresh_candidate_chain(request, policy, artifact, receipt)

    assert not _generated_candidate_is_valid(request, policy, artifact, receipt)


def test_every_hardened_receipt_field_rejects_omission_and_wrong_type() -> None:
    receipt_sets = (
        (
            "mapping_receipts",
            "mapping_receipt_identity_sha256",
            store_module._MAPPING_RECEIPT_FIELDS,
            _refresh_mapping_identity,
        ),
        (
            "partition_receipts",
            "partition_receipt_identity_sha256",
            store_module._PARTITION_RECEIPT_FIELDS,
            _refresh_partition_identity,
        ),
    )
    for collection, identity_field, fields, refresh in receipt_sets:
        for field in sorted(fields):
            request, policy, artifact, receipt = _candidate_objects()
            item = artifact[collection][0]
            del item[field]
            if field != identity_field:
                refresh(item)
            _refresh_candidate_chain(request, policy, artifact, receipt)
            assert not _generated_candidate_is_valid(request, policy, artifact, receipt)

            request, policy, artifact, receipt = _candidate_objects()
            item = artifact[collection][0]
            item[field] = "invalid" if type(item[field]) is int else 0
            if field != identity_field:
                refresh(item)
            _refresh_candidate_chain(request, policy, artifact, receipt)
            assert not _generated_candidate_is_valid(request, policy, artifact, receipt)


def test_receipt_cross_references_reject_recomputed_substitution() -> None:
    request, policy, artifact, receipt = _candidate_objects()
    mapping = artifact["mapping_receipts"][0]
    mapping["observation_sha256"] = "e" * 64
    mapping["relative_metadata_path"] = (
        "instrument_snapshots/sha256="
        + mapping["compressed_sha256"]
        + "/observations/sha256="
        + "e" * 64
        + ".json"
    )
    _refresh_mapping_identity(mapping)
    _refresh_candidate_chain(request, policy, artifact, receipt)
    assert not _generated_candidate_is_valid(request, policy, artifact, receipt)

    request, policy, artifact, receipt = _candidate_objects()
    partition = artifact["partition_receipts"][0]
    partition["plan_instrument_key"] = "NSE_EQ|OTHER"
    _refresh_partition_identity(partition)
    _refresh_candidate_chain(request, policy, artifact, receipt)
    assert not _generated_candidate_is_valid(request, policy, artifact, receipt)

    request, policy, artifact, receipt = _candidate_objects()
    receipt["schedule_evidence_sha256"] = "e" * 64
    _refresh_candidate_chain(request, policy, artifact, receipt)
    assert not _generated_candidate_is_valid(request, policy, artifact, receipt)


def test_candidate_row_and_partition_limit_plus_one_are_rejected_directly() -> None:
    request, policy, artifact, receipt = _candidate_objects()
    artifact["bars"] = artifact["bars"] * 18_301
    assert (
        store_module._parse_import_candidate_structure(
            _canonical(request),
            _canonical(policy),
            _canonical(artifact),
            _canonical(receipt),
        )
        is None
    )

    request, _, artifact, receipt = _candidate_objects()
    artifact["partition_receipts"] = artifact["partition_receipts"] * 601
    assert not store_module._validate_closed_receipts(request, artifact, receipt)


def _publish(root: Path, inputs: tuple[bytes, bytes, bytes, bytes]):
    identity = store_module.StorageRootLease.admit_existing_private_identity(root)
    store = HistoricalOhlcvRevisionStoreV1(root, identity)
    request, policy, artifact, receipt = _candidate_objects_from(inputs)
    if request["operation"] != "INITIAL":
        parent_artifact = store._read_exact_source_artifact(  # pyright: ignore[reportPrivateUsage]
            request["parent_revision_sha256"]
        )
        assert parent_artifact is not None
        assert historical_upstox_raw._inherit_partition_receipts(  # pyright: ignore[reportPrivateUsage]
            request, policy, artifact, receipt, parent_artifact
        )
        _refresh_candidate_chain(request, policy, artifact, receipt)
        inputs = tuple(
            _canonical(value) for value in (request, policy, artifact, receipt)
        )  # type: ignore[assignment]
    return store._publish_generated_source(  # pyright: ignore[reportPrivateUsage]
        *inputs, completion_request_identity_sha256=_sha(b"operator")
    )


def _inputs(
    *,
    operation: str = "INITIAL",
    parent: str | None = None,
    corrections: list[dict[str, str]] | None = None,
    sessions: tuple[str, ...] = ("2026-07-01",),
    upper: str = "2026-07-01",
    open_value: str = "100",
) -> tuple[bytes, bytes, bytes, bytes]:
    schema, runtime, configuration = historical_upstox_raw_current_identities_v1()
    known_at = "2026-08-27T04:00:00Z"
    upper_date = date.fromisoformat(upper)
    as_of = max(
        datetime(2026, 8, 27, 4, tzinfo=UTC),
        datetime.combine(upper_date + timedelta(days=1), datetime.min.time(), UTC),
    )
    observed_at = as_of.strftime("%Y-%m-%dT%H:%M:%SZ")
    schedule_value = ExpectedSessionSchedule(
        schema_version=3,
        source="nse-upstox-composed-calendar",
        source_release="composed-calendar@v1=" + "a" * 64,
        as_of=as_of,
        timezone="Asia/Kolkata",
        covered_from=date.fromisoformat(sessions[0]),
        covered_to=date.fromisoformat(upper),
        sessions=tuple(
            ScheduleSession(
                date.fromisoformat(session),
                datetime(
                    date.fromisoformat(session).year,
                    date.fromisoformat(session).month,
                    date.fromisoformat(session).day,
                    3,
                    45,
                    tzinfo=UTC,
                ),
                datetime(
                    date.fromisoformat(session).year,
                    date.fromisoformat(session).month,
                    date.fromisoformat(session).day,
                    10,
                    tzinfo=UTC,
                ),
                "REGULAR",
            )
            for session in sessions
        ),
    )
    schedule = json.loads(canonical_schedule_bytes(schedule_value))
    mapping_receipt = {
        "contract_version": "upstox-retained-raw-mapping-receipt@v1",
        "isin": "INE002A01018",
        "exchange": "NSE",
        "effective_symbol": "RELIANCE",
        "requested_provider_instrument_id": "NSE_EQ|INE002A01018",
        "snapshot_schema_version": 1,
        "snapshot_source": "upstox-bod-nse",
        "observation_date": "2026-08-27",
        "retrieved_at": "2026-08-27T03:18:10.135710Z",
        "observation_sha256": "a" * 64,
        "compressed_sha256": "b" * 64,
        "decompressed_sha256": "c" * 64,
        "compressed_byte_count": 1,
        "decompressed_byte_count": 1,
        "relative_object_path": "instrument_snapshots/sha256="
        + "b" * 64
        + "/snapshot.json.gz",
        "relative_metadata_path": (
            "instrument_snapshots/sha256="
            + "b" * 64
            + "/observations/sha256="
            + "a" * 64
            + ".json"
        ),
        "etag": None,
        "last_modified": None,
        "resolved_instrument_key": "NSE_EQ|INE002A01018",
        "resolved_security_id": "INE002A01018",
        "resolved_symbol": "RELIANCE",
        "resolved_exchange": "NSE",
        "resolved_segment": "NSE_EQ",
        "resolved_instrument_type": "EQ",
        "mapping_known_at": "2026-08-27T03:18:10.135710Z",
    }
    mapping_receipt["mapping_receipt_identity_sha256"] = _sha(
        _canonical(mapping_receipt)
    )
    partition_receipt = {
        "contract_version": "upstox-retained-verified-partition-receipt@v1",
        "isin": "INE002A01018",
        "manifest_schema_version": 1,
        "plan_provider": "upstox",
        "plan_instrument_key": "NSE_EQ|INE002A01018",
        "plan_security_id": "INE002A01018",
        "plan_symbol": "RELIANCE",
        "plan_exchange": "NSE",
        "plan_segment": "NSE_EQ",
        "plan_instrument_type": "EQ",
        "plan_interval": "1m",
        "plan_year": 2026,
        "plan_month": 7,
        "plan_from_date": "2026-07-01",
        "plan_to_date": "2026-07-31",
        "ingestion_run_id": "run",
        "candle_schema_version": 1,
        "state": "VERIFIED",
        "validation_outcome": "PASSED",
        "validation_policy_version": "policy@v1",
        "actual_from_ts": "2026-07-01T03:45:00Z",
        "actual_to_ts": "2026-07-01T10:00:00Z",
        "row_count": 1,
        "parquet_sha256": "d" * 64,
        "canonical_path": (
            "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/"
            "instrument_type=EQ/security_id=INE002A01018/interval=1m/"
            "year=2026/month=07/bars.parquet"
        ),
        "source_version": "upstox-historical-v3",
        "manifest_created_at": "2026-08-27T03:00:00Z",
        "attempt_started_at": "2026-08-27T03:01:00Z",
        "manifest_updated_at": "2026-08-27T03:02:00Z",
        "failure_category": None,
        "schedule_digest_sha256": _sha(_canonical(schedule)),
    }
    touched_months = [
        (year, month)
        for year in range(
            date.fromisoformat(sessions[0]).year, date.fromisoformat(upper).year + 1
        )
        for month in range(1, 13)
        if (year, month)
        >= (date.fromisoformat(sessions[0]).year, date.fromisoformat(sessions[0]).month)
        and (year, month)
        <= (date.fromisoformat(upper).year, date.fromisoformat(upper).month)
    ]
    partition_receipts = []
    for year, month in touched_months:
        receipt_value = dict(partition_receipt)
        receipt_value["plan_year"] = year
        receipt_value["plan_month"] = month
        receipt_value["plan_from_date"] = f"{year:04d}-{month:02d}-01"
        receipt_value["plan_to_date"] = (
            f"{year:04d}-{month:02d}-{monthrange(year, month)[1]:02d}"
        )
        receipt_value["canonical_path"] = (
            "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/"
            "instrument_type=EQ/security_id=INE002A01018/interval=1m/"
            f"year={year:04d}/month={month:02d}/bars.parquet"
        )
        receipt_value["partition_receipt_identity_sha256"] = _sha(
            _canonical(receipt_value)
        )
        partition_receipts.append(receipt_value)
    bars = [
        {
            "isin": "INE002A01018",
            "exchange": "NSE",
            "session": session,
            "open": open_value,
            "high": "102",
            "low": "99",
            "close": "101",
            "volume": "1000",
            "known_at": known_at,
            "price_basis": "RAW",
        }
        for session in sessions
    ]
    artifact = {
        "schema_version": "upstox-retained-raw-historical-ohlcv-artifact@v1",
        "source_profile": "UPSTOX_RAW",
        "schedule": schedule,
        "mapping_receipts": [mapping_receipt],
        "partition_receipts": partition_receipts,
        "bars": bars,
    }
    artifact_raw = _canonical(artifact)
    policy = {
        "schema_version": "upstox-retained-raw-historical-ohlcv-source-policy@v1",
        "source_profile": "UPSTOX_RAW",
        "source_name": "UPSTOX_RETAINED_VERIFIED_1M",
        "provider": "UPSTOX",
        "source_version": "upstox-historical-v3",
        "source_interval": "1m",
        "output_interval": "1d",
        "aggregation_version": "nse-session-ohlcv@v1",
        "price_basis": "RAW",
        "adjustment_state": "raw",
        "temporal_status": "REVISED_NON_PIT",
        "corporate_action_status": "NOT_EVALUATED",
        "comparability_status": "NOT_ESTABLISHED",
        "permitted_use": "OWNER_PRIVATE_RESEARCH",
        "artifact_sha256": _sha(artifact_raw),
    }
    policy_raw = _canonical(policy)
    receipt = {
        "schema_version": "upstox-retained-raw-historical-ohlcv-receipt@v1",
        "source_profile": "UPSTOX_RAW",
        "source_policy_sha256": _sha(policy_raw),
        "source_artifact_sha256": _sha(artifact_raw),
        "mapping_receipts_identity_sha256": _sha(
            _canonical([mapping_receipt["mapping_receipt_identity_sha256"]])
        ),
        "partition_receipts_identity_sha256": _sha(
            _canonical(
                [
                    value["partition_receipt_identity_sha256"]
                    for value in partition_receipts
                ]
            )
        ),
        "schedule_evidence_sha256": _sha(_canonical(schedule)),
        "observed_at": observed_at,
        "known_at": known_at,
        "permitted_use": "OWNER_PRIVATE_RESEARCH",
        "price_basis": "RAW",
        "adjustment_state": "raw",
        "temporal_status": "REVISED_NON_PIT",
        "corporate_action_status": "NOT_EVALUATED",
        "comparability_status": "NOT_ESTABLISHED",
    }
    receipt_raw = _canonical(receipt)
    request = {
        "contract_version": "fixed-cohort-historical-ohlcv-upstox-raw-revision-store@v1",
        "research_scope": "FIXED_COHORT_RETROSPECTIVE",
        "source_profile": "UPSTOX_RAW",
        "operation": operation,
        "parent_revision_sha256": parent,
        "correction_coordinates": corrections or [],
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
                    "mapping_evidence_sha256": "a" * 64,
                },
            }
        ],
        "from_session": sessions[0],
        "to_session": upper,
        "interval": "1d",
        "expected_sessions": list(sessions),
        "schedule_evidence_sha256": _sha(_canonical(schedule)),
        "source_policy_sha256": _sha(policy_raw),
        "source_artifact_sha256": _sha(artifact_raw),
        "receipt_sha256": _sha(receipt_raw),
        "observed_at": observed_at,
        "permitted_use": "OWNER_PRIVATE_RESEARCH",
        "price_basis": "RAW",
        "adjustment_state": "raw",
        "aggregation_version": "nse-session-ohlcv@v1",
        "temporal_status": "REVISED_NON_PIT",
        "corporate_action_status": "NOT_EVALUATED",
        "comparability_status": "NOT_ESTABLISHED",
        "schema_identity_sha256": schema,
        "runtime_code_identity_sha256": runtime,
        "configuration_identity_sha256": configuration,
        "limits": store_module._LIMITS,
    }
    return _canonical(request), policy_raw, artifact_raw, receipt_raw


def _candidate_objects() -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
]:
    request_raw, policy_raw, artifact_raw, receipt_raw = _inputs()
    return tuple(
        cast(dict[str, Any], json.loads(raw))
        for raw in (request_raw, policy_raw, artifact_raw, receipt_raw)
    )  # type: ignore[return-value]


def _candidate_objects_from(
    raw_values: tuple[bytes, bytes, bytes, bytes],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    return tuple(cast(dict[str, Any], json.loads(raw)) for raw in raw_values)  # type: ignore[return-value]


def _generated_candidate_is_valid(
    request: dict[str, Any],
    policy: dict[str, Any],
    artifact: dict[str, Any],
    receipt: dict[str, Any],
) -> bool:
    return store_module.validate_generated_source_candidate_v1(
        request, policy, artifact, receipt, _sha(b"operator")
    )


def _refresh_mapping_identity(mapping: dict[str, Any]) -> None:
    identity = dict(mapping)
    del identity["mapping_receipt_identity_sha256"]
    mapping["mapping_receipt_identity_sha256"] = _sha(_canonical(identity))


def _refresh_partition_identity(partition: dict[str, Any]) -> None:
    identity = dict(partition)
    del identity["partition_receipt_identity_sha256"]
    partition["partition_receipt_identity_sha256"] = _sha(_canonical(identity))


def _refresh_candidate_digests(
    policy: dict[str, Any], artifact: dict[str, Any], receipt: dict[str, Any]
) -> None:
    artifact_sha256 = _sha(_canonical(artifact))
    policy["artifact_sha256"] = artifact_sha256
    receipt["source_artifact_sha256"] = artifact_sha256
    receipt["mapping_receipts_identity_sha256"] = _sha(
        _canonical(
            [
                item["mapping_receipt_identity_sha256"]
                for item in artifact["mapping_receipts"]
            ]
        )
    )
    receipt["partition_receipts_identity_sha256"] = _sha(
        _canonical(
            [
                item["partition_receipt_identity_sha256"]
                for item in artifact["partition_receipts"]
            ]
        )
    )


def _refresh_candidate_chain(
    request: dict[str, Any],
    policy: dict[str, Any],
    artifact: dict[str, Any],
    receipt: dict[str, Any],
) -> None:
    artifact_sha256 = _sha(_canonical(artifact))
    policy["artifact_sha256"] = artifact_sha256
    policy_sha256 = _sha(_canonical(policy))
    receipt["source_policy_sha256"] = policy_sha256
    receipt["source_artifact_sha256"] = artifact_sha256
    receipt["mapping_receipts_identity_sha256"] = _sha(
        _canonical(
            [
                item.get("mapping_receipt_identity_sha256")
                for item in artifact["mapping_receipts"]
            ]
        )
    )
    receipt["partition_receipts_identity_sha256"] = _sha(
        _canonical(
            [
                item.get("partition_receipt_identity_sha256")
                for item in artifact["partition_receipts"]
            ]
        )
    )
    request["source_policy_sha256"] = policy_sha256
    request["source_artifact_sha256"] = artifact_sha256
    request["receipt_sha256"] = _sha(_canonical(receipt))


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_revision_bytes(root: Path, revision: str) -> bytes:
    return (
        root
        / "historical_ohlcv_revisions"
        / "upstox-raw"
        / "v1"
        / "revisions"
        / f"{revision}.json"
    ).read_bytes()


def _write_recomputed_candidate_for_exact_read(
    root: Path,
    request: dict[str, Any],
    policy: dict[str, Any],
    artifact: dict[str, Any],
    receipt: dict[str, Any],
) -> str:
    store_root = root / "historical_ohlcv_revisions" / "upstox-raw" / "v1"
    objects = store_root / "objects"
    revision = store_module._revision_value(  # pyright: ignore[reportPrivateUsage]
        request,
        cast(list[dict[str, Any]], artifact["bars"]),
        0,
        _sha(b"operator"),
    )
    for name, raw in (
        (request["source_policy_sha256"], _canonical(policy)),
        (request["source_artifact_sha256"], _canonical(artifact)),
        (request["receipt_sha256"], _canonical(receipt)),
    ):
        path = objects / name
        assert not path.exists()
        path.write_bytes(raw)
        path.chmod(0o400)
    revision_path = store_root / "revisions" / f"{revision['revision_sha256']}.json"
    assert not revision_path.exists()
    revision_path.write_bytes(_canonical(revision))
    revision_path.chmod(0o400)
    return cast(str, revision["revision_sha256"])


def _rewrite_initial_revision_schema(
    root: Path, revision_id: str, schema_identity_sha256: str
) -> tuple[str, bytes]:
    revision = json.loads(_read_revision_bytes(root, revision_id))
    revision["schema_identity_sha256"] = schema_identity_sha256
    revision.pop("revision_sha256")
    legacy_id = _sha(_canonical(revision))
    revision["revision_sha256"] = legacy_id
    legacy_raw = _canonical(revision)
    revisions = root / "historical_ohlcv_revisions" / "upstox-raw" / "v1" / "revisions"
    (revisions / f"{revision_id}.json").unlink()
    legacy_path = revisions / f"{legacy_id}.json"
    legacy_path.write_bytes(legacy_raw)
    legacy_path.chmod(0o400)
    return legacy_id, legacy_raw


def test_lineage_depth_128_is_admitted_and_129_is_rejected(tmp_path: Path) -> None:
    parent = _publish(tmp_path, _inputs())
    assert parent.revision_sha256 is not None
    sessions = [date(2026, 7, 1).isoformat()]
    for offset in range(1, 129):
        sessions.append((date(2026, 7, 1) + timedelta(days=offset)).isoformat())
        result = _publish(
            tmp_path,
            _inputs(
                operation="APPEND",
                parent=parent.revision_sha256,
                sessions=tuple(sessions),
                upper=sessions[-1],
            ),
        )
        assert result.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
        assert result.revision_sha256 is not None
        parent = result
    next_session = (date(2026, 7, 1) + timedelta(days=129)).isoformat()
    rejected = _publish(
        tmp_path,
        _inputs(
            operation="APPEND",
            parent=parent.revision_sha256,
            sessions=(*sessions, next_session),
            upper=next_session,
        ),
    )
    assert rejected.outcome is HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT


def test_symlinked_destination_root_is_rejected_without_publication(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)

    result = HistoricalOhlcvRevisionStoreV1(link)._publish_generated_source(  # pyright: ignore[reportPrivateUsage]
        *_inputs(), completion_request_identity_sha256=_sha(b"operator")
    )
    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert not (target / "historical_ohlcv_revisions").exists()


def test_exact_retry_fsyncs_visible_publication_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _publish(tmp_path, _inputs())
    assert first.revision_sha256 is not None
    calls = 0
    original = store_module.os.fsync

    def count_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        original(descriptor)

    monkeypatch.setattr(store_module.os, "fsync", count_fsync)
    replay = _publish(tmp_path, _inputs())
    assert replay.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert replay.revision_sha256 == first.revision_sha256
    assert calls >= 2


def test_exact_retry_fsyncs_interrupted_immutable_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = store_module.os.fsync
    interrupted_identity: tuple[int, int] | None = None

    def interrupt_first_immutable_file(descriptor: int) -> None:
        nonlocal interrupted_identity
        info = os.fstat(descriptor)
        if interrupted_identity is None and stat.S_ISREG(info.st_mode):
            interrupted_identity = (info.st_dev, info.st_ino)
            raise OSError("interrupted immutable file fsync")
        original(descriptor)

    monkeypatch.setattr(store_module.os, "fsync", interrupt_first_immutable_file)
    first = _publish(tmp_path, _inputs())
    assert (
        first.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert interrupted_identity is not None

    synced_regular_identities: list[tuple[int, int]] = []

    def track_retry_fsync(descriptor: int) -> None:
        info = os.fstat(descriptor)
        if stat.S_ISREG(info.st_mode):
            synced_regular_identities.append((info.st_dev, info.st_ino))
        original(descriptor)

    monkeypatch.setattr(store_module.os, "fsync", track_retry_fsync)
    retry = _publish(tmp_path, _inputs())

    assert retry.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert interrupted_identity in synced_regular_identities


def test_cli_rejects_request_file_inside_destination_root(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    request.write_bytes(b"{}")
    admitted = store_module.StorageRootLease.admit_existing_private_identity(tmp_path)
    assert admitted is not None
    root = cli._AdmittedHistoricalStorageRootV1(tmp_path, admitted, tmp_path.parts[1:])
    with pytest.raises(ValueError):
        cli._read_historical_local_file(request, 1024, root)


def test_inherited_partition_receipt_requires_exact_schedule_and_identity() -> None:
    _, _, artifact, _ = _candidate_objects()
    parent = cast(dict[str, Any], artifact["partition_receipts"][0])
    child = dict(parent)
    child["schedule_digest_sha256"] = "b" * 64
    _refresh_partition_identity(child)

    assert not store_module._same_inherited_partition_receipt(parent, child)  # pyright: ignore[reportPrivateUsage]


def test_append_and_correction_reject_recomputed_inherited_receipt_mutation(
    tmp_path: Path,
) -> None:
    parent = _publish(
        tmp_path,
        _inputs(
            sessions=("2026-07-01", "2026-08-03"),
            upper="2026-08-03",
        ),
    )
    assert parent.revision_sha256 is not None

    request, policy, artifact, receipt = _candidate_objects_from(
        _inputs(
            operation="APPEND",
            parent=parent.revision_sha256,
            sessions=("2026-07-01", "2026-08-03", "2026-08-04"),
            upper="2026-08-04",
        )
    )
    artifact["mapping_receipts"][0]["etag"] = "mutated"
    _refresh_mapping_identity(artifact["mapping_receipts"][0])
    _refresh_candidate_chain(request, policy, artifact, receipt)
    appended = HistoricalOhlcvRevisionStoreV1(tmp_path)._publish_generated_source(  # pyright: ignore[reportPrivateUsage]
        _canonical(request),
        _canonical(policy),
        _canonical(artifact),
        _canonical(receipt),
        completion_request_identity_sha256=_sha(b"operator"),
    )
    assert appended.outcome is HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT

    request, policy, artifact, receipt = _candidate_objects_from(
        _inputs(
            operation="CORRECTION",
            parent=parent.revision_sha256,
            corrections=[
                {
                    "isin": "INE002A01018",
                    "exchange": "NSE",
                    "session": "2026-08-03",
                }
            ],
            sessions=("2026-07-01", "2026-08-03"),
            upper="2026-08-03",
            open_value="101",
        )
    )
    artifact["partition_receipts"][0]["ingestion_run_id"] = "mutated"
    _refresh_partition_identity(artifact["partition_receipts"][0])
    _refresh_candidate_chain(request, policy, artifact, receipt)
    corrected = HistoricalOhlcvRevisionStoreV1(tmp_path)._publish_generated_source(  # pyright: ignore[reportPrivateUsage]
        _canonical(request),
        _canonical(policy),
        _canonical(artifact),
        _canonical(receipt),
        completion_request_identity_sha256=_sha(b"operator"),
    )
    assert corrected.outcome is HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT


def test_initial_retry_resumes_visible_valid_source_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = store_module._publish_object
    calls = 0

    def interrupt_after_first(parent: int, name: str, raw: bytes) -> bool:
        nonlocal calls
        calls += 1
        published = original(parent, name, raw)
        if calls == 1:
            raise OSError("interrupted")
        return published

    monkeypatch.setattr(store_module, "_publish_object", interrupt_after_first)
    interrupted = _publish(tmp_path, _inputs())
    assert (
        interrupted.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    monkeypatch.setattr(store_module, "_publish_object", original)

    retry = _publish(tmp_path, _inputs())

    assert retry.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert retry.revision_sha256 is not None
    assert (
        HistoricalOhlcvRevisionStoreV1(tmp_path).read_exact(retry.revision_sha256)
        == retry
    )


def test_divergent_initial_rejects_visible_partial_source_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = store_module._publish_object
    calls = 0

    def interrupt_after_first(parent: int, name: str, raw: bytes) -> bool:
        nonlocal calls
        calls += 1
        published = original(parent, name, raw)
        if calls == 1:
            raise OSError("interrupted")
        return published

    monkeypatch.setattr(store_module, "_publish_object", interrupt_after_first)
    interrupted = _publish(tmp_path, _inputs())
    assert (
        interrupted.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    monkeypatch.setattr(store_module, "_publish_object", original)

    root = tmp_path / "historical_ohlcv_revisions" / "upstox-raw" / "v1"
    objects = root / "objects"
    revisions = root / "revisions"
    before_objects = {path.name: path.read_bytes() for path in objects.iterdir()}

    divergent = _publish(tmp_path, _inputs(open_value="101"))

    assert (
        divergent.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert {
        path.name: path.read_bytes() for path in objects.iterdir()
    } == before_objects
    assert not any(revisions.iterdir())


@pytest.mark.parametrize(
    ("operation", "publication_index", "prefix_length"),
    tuple(
        (operation, publication_index, prefix_length)
        for operation in ("INITIAL", "APPEND", "CORRECTION")
        for publication_index in range(4)
        for prefix_length in (0, 1, None)
    ),
)
def test_direct_final_prefix_interruption_retries_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    publication_index: int,
    prefix_length: int | None,
) -> None:
    parent = _publish(tmp_path, _inputs())
    assert parent.revision_sha256 is not None
    if operation == "INITIAL":
        root = tmp_path / "initial-retry"
        root.mkdir(mode=0o700)
        _prepare_private_initial_root(root)
        inputs = _inputs()
    elif operation == "APPEND":
        root = tmp_path
        inputs = _inputs(
            operation="APPEND",
            parent=parent.revision_sha256,
            sessions=("2026-07-01", "2026-07-02"),
            upper="2026-07-02",
        )
    else:
        root = tmp_path
        inputs = _inputs(
            operation="CORRECTION",
            parent=parent.revision_sha256,
            corrections=[
                {"isin": "INE002A01018", "exchange": "NSE", "session": "2026-07-01"}
            ],
            open_value="101",
        )

    original_publish = store_module._publish_object
    publications = 0

    def interrupt_selected_publication(parent_fd: int, name: str, raw: bytes) -> bool:
        nonlocal publications
        publications += 1
        if publications != publication_index + 1:
            return original_publish(parent_fd, name, raw)
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=parent_fd,
        )
        try:
            prefix = raw if prefix_length is None else raw[:prefix_length]
            if prefix:
                assert os.write(descriptor, prefix) == len(prefix)
        finally:
            os.close(descriptor)
        raise KeyboardInterrupt("direct final publication interrupted")

    monkeypatch.setattr(store_module, "_publish_object", interrupt_selected_publication)
    with pytest.raises(KeyboardInterrupt):
        _publish(root, inputs)

    retry = _publish(root, inputs)

    assert retry.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    assert retry.revision_sha256 is not None
    assert (
        HistoricalOhlcvRevisionStoreV1(root).read_exact(retry.revision_sha256) == retry
    )


@pytest.mark.parametrize(
    "unexpected_parent",
    (
        (),
        ("historical_ohlcv_revisions",),
        ("historical_ohlcv_revisions", "upstox-raw"),
        ("historical_ohlcv_revisions", "upstox-raw", "v1"),
    ),
)
def test_initial_existing_writer_rejects_unrelated_hierarchy_content(
    tmp_path: Path, unexpected_parent: tuple[str, ...]
) -> None:
    root = tmp_path / "destination"
    root.mkdir(mode=0o700)
    lock = root / ".ingestion.lock"
    lock.write_bytes(b"")
    lock.chmod(0o600)
    parent = root
    for name in unexpected_parent:
        parent /= name
        parent.mkdir(mode=0o700)
    unrelated = parent / "unrelated"
    unrelated.write_bytes(b"unrelated")
    unrelated.chmod(0o400)

    result = _publish(root, _inputs())

    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert unrelated.read_bytes() == b"unrelated"
    version = root / "historical_ohlcv_revisions" / "upstox-raw" / "v1"
    for directory in (version / "objects", version / "revisions"):
        if directory.exists():
            assert not list(directory.iterdir())


@pytest.mark.parametrize(
    ("mode", "candidate"),
    (
        (0o600, b"divergent"),
        (0o400, b"divergent"),
        (0o400, b"exact-prefix"),
    ),
)
def test_nonexact_direct_final_remains_conflict(
    tmp_path: Path, mode: int, candidate: bytes
) -> None:
    root = tmp_path / "destination"
    root.mkdir(mode=0o700)
    _prepare_private_initial_root(root)
    objects = root / "historical_ohlcv_revisions" / "upstox-raw" / "v1" / "objects"
    objects.mkdir(mode=0o700, parents=True)
    revisions = objects.parent / "revisions"
    revisions.mkdir(mode=0o700)
    for directory in (
        objects.parent.parent.parent,
        objects.parent.parent,
        objects.parent,
        objects,
        revisions,
    ):
        directory.chmod(0o700)
    inputs = _inputs()
    request, _, _, _ = _candidate_objects_from(inputs)
    policy = inputs[1]
    final = objects / request["source_policy_sha256"]
    final.write_bytes(candidate)
    final.chmod(mode)

    result = _publish(root, inputs)

    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert final.read_bytes() == candidate
    assert policy != candidate
    assert not any(revisions.iterdir())


def test_initial_root_insertion_after_hierarchy_open_conflicts_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "destination"
    root.mkdir(mode=0o700)
    _prepare_private_initial_root(root)
    unrelated = root / "unrelated"
    original_open_directory = store_module._open_directory
    inserted = False

    def insert_after_hierarchy_open(parent: int, name: str) -> int:
        nonlocal inserted
        descriptor = original_open_directory(parent, name)
        if not inserted and name == store_module._REVISION_DIRECTORY:
            unrelated.write_bytes(b"unrelated")
            unrelated.chmod(0o400)
            inserted = True
        return descriptor

    monkeypatch.setattr(store_module, "_open_directory", insert_after_hierarchy_open)

    result = _publish(root, _inputs())

    assert inserted
    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert unrelated.read_bytes() == b"unrelated"
    version = root / "historical_ohlcv_revisions" / "upstox-raw" / "v1"
    assert not list((version / "objects").iterdir())
    assert not list((version / "revisions").iterdir())


def test_direct_final_replacement_after_descriptor_admission_retains_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "destination"
    root.mkdir(mode=0o700)
    _prepare_private_initial_root(root)
    objects = root / "historical_ohlcv_revisions" / "upstox-raw" / "v1" / "objects"
    objects.mkdir(mode=0o700, parents=True)
    revisions = objects.parent / "revisions"
    revisions.mkdir(mode=0o700)
    for directory in (
        objects.parent.parent.parent,
        objects.parent.parent,
        objects.parent,
        objects,
        revisions,
    ):
        directory.chmod(0o700)
    inputs = _inputs()
    request, _, _, _ = _candidate_objects_from(inputs)
    policy = inputs[1]
    final = objects / request["source_policy_sha256"]
    final.write_bytes(policy[:1])
    final.chmod(0o600)
    foreign = b"foreign replacement"
    original_write = store_module.os.write
    replaced = False

    def replace_after_admission(descriptor: int, payload: bytes) -> int:
        nonlocal replaced
        if not replaced:
            final.unlink()
            final.write_bytes(foreign)
            final.chmod(0o600)
            replaced = True
        return original_write(descriptor, payload)

    monkeypatch.setattr(store_module.os, "write", replace_after_admission)

    result = _publish(root, inputs)

    assert replaced
    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert final.read_bytes() == foreign
    assert not any(revisions.iterdir())


def test_exact_immutable_replacement_after_admission_remains_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "destination"
    root.mkdir(mode=0o700)
    _prepare_private_initial_root(root)
    objects = root / "historical_ohlcv_revisions" / "upstox-raw" / "v1" / "objects"
    objects.mkdir(mode=0o700, parents=True)
    revisions = objects.parent / "revisions"
    revisions.mkdir(mode=0o700)
    for directory in (
        objects.parent.parent.parent,
        objects.parent.parent,
        objects.parent,
        objects,
        revisions,
    ):
        directory.chmod(0o700)
    inputs = _inputs()
    request, _, _, _ = _candidate_objects_from(inputs)
    policy = inputs[1]
    final = objects / request["source_policy_sha256"]
    final.write_bytes(policy)
    final.chmod(0o400)
    original_read = store_module._read_object
    replaced = False

    def replace_before_identity_bound_read(
        parent: int,
        name: str,
        maximum: int,
        expected_identity: tuple[int, int] | None = None,
    ) -> bytes:
        nonlocal replaced
        if not replaced and expected_identity is not None:
            final.unlink()
            final.write_bytes(policy)
            final.chmod(0o400)
            replaced = True
        return original_read(parent, name, maximum, expected_identity)

    monkeypatch.setattr(
        store_module, "_read_object", replace_before_identity_bound_read
    )

    result = _publish(root, inputs)

    assert replaced
    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert final.read_bytes() == policy
    assert not any(revisions.iterdir())


def test_exact_read_rechecks_destination_root_before_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _publish(tmp_path, _inputs())
    assert first.revision_sha256 is not None
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    original = (
        store_module.HistoricalOhlcvRevisionStoreV1._read_stored_exact_from_directories
    )
    moved = tmp_path.with_name(f"{tmp_path.name}-moved")
    replaced = False

    def replace_root_after_read(
        self: HistoricalOhlcvRevisionStoreV1,
        revision_id: str,
        objects: int,
        revisions: int,
    ) -> dict[str, Any]:
        nonlocal replaced
        value = original(self, revision_id, objects, revisions)
        if not replaced:
            tmp_path.rename(moved)
            tmp_path.mkdir(mode=0o700)
            replaced = True
        return value

    monkeypatch.setattr(
        store_module.HistoricalOhlcvRevisionStoreV1,
        "_read_stored_exact_from_directories",
        replace_root_after_read,
    )

    result = store.read_exact(first.revision_sha256)

    assert replaced
    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )


@pytest.mark.parametrize(
    "edge",
    ("store-root", "profile", "version", "objects", "revisions"),
)
def test_exact_read_rechecks_each_named_hierarchy_edge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, edge: str
) -> None:
    first = _publish(tmp_path, _inputs())
    assert first.revision_sha256 is not None
    store = HistoricalOhlcvRevisionStoreV1(tmp_path)
    original = (
        store_module.HistoricalOhlcvRevisionStoreV1._read_stored_exact_from_directories
    )
    replaced = False

    def replace_edge_after_read(
        self: HistoricalOhlcvRevisionStoreV1,
        revision_id: str,
        objects: int,
        revisions: int,
    ) -> dict[str, Any]:
        nonlocal replaced
        value = original(self, revision_id, objects, revisions)
        if not replaced:
            version = tmp_path / "historical_ohlcv_revisions" / "upstox-raw" / "v1"
            edges = {
                "store-root": version.parent.parent,
                "profile": version.parent,
                "version": version,
                "objects": version / "objects",
                "revisions": version / "revisions",
            }
            target = edges[edge]
            moved = target.with_name(f"{target.name}-moved")
            target.rename(moved)
            target.mkdir(mode=0o700)
            replaced = True
        return value

    monkeypatch.setattr(
        store_module.HistoricalOhlcvRevisionStoreV1,
        "_read_stored_exact_from_directories",
        replace_edge_after_read,
    )

    result = store.read_exact(first.revision_sha256)

    assert replaced
    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )


def test_exact_retry_rechecks_destination_root_before_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _publish(tmp_path, _inputs())
    assert first.outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    original = (
        store_module.HistoricalOhlcvRevisionStoreV1._read_stored_exact_from_directories
    )
    moved = tmp_path.with_name(f"{tmp_path.name}-moved")
    replaced = False

    def replace_root_after_read(
        self: HistoricalOhlcvRevisionStoreV1,
        revision_id: str,
        objects: int,
        revisions: int,
    ) -> dict[str, Any]:
        nonlocal replaced
        value = original(self, revision_id, objects, revisions)
        if not replaced:
            tmp_path.rename(moved)
            tmp_path.mkdir(mode=0o700)
            replaced = True
        return value

    monkeypatch.setattr(
        store_module.HistoricalOhlcvRevisionStoreV1,
        "_read_stored_exact_from_directories",
        replace_root_after_read,
    )

    result = _publish(tmp_path, _inputs())

    assert replaced
    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )


@pytest.mark.parametrize("quarantine", (False, True))
def test_stale_candidate_temp_or_quarantine_remains_conflict(
    tmp_path: Path, quarantine: bool
) -> None:
    root = tmp_path / "destination"
    root.mkdir(mode=0o700)
    _prepare_private_initial_root(root)
    objects = root / "historical_ohlcv_revisions" / "upstox-raw" / "v1" / "objects"
    objects.mkdir(mode=0o700, parents=True)
    revisions = objects.parent / "revisions"
    revisions.mkdir(mode=0o700)
    for directory in (
        objects.parent.parent.parent,
        objects.parent.parent,
        objects.parent,
        objects,
        revisions,
    ):
        directory.chmod(0o700)
    inputs = _inputs()
    request, _, _, _ = _candidate_objects_from(inputs)
    prefix = ".quarantine." if quarantine else "."
    stale = objects / f"{prefix}{request['source_policy_sha256']}.{'0' * 32}.tmp"
    stale.write_bytes(b"unrelated")
    stale.chmod(0o400)

    result = _publish(root, inputs)

    assert (
        result.outcome
        is HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT
    )
    assert stale.read_bytes() == b"unrelated"
    assert not any(revisions.iterdir())


def test_publication_paths_never_call_link_unlink_or_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_os = store_module.os

    class PublicationOs:
        def __getattr__(self, name: str) -> Any:
            if name in {"link", "rename", "unlink"}:
                raise AssertionError(f"publication helper called os.{name}")
            return getattr(original_os, name)

    monkeypatch.setattr(store_module, "os", PublicationOs())
    initial = _publish(tmp_path, _inputs())
    assert initial.revision_sha256 is not None
    assert (
        _publish(tmp_path, _inputs()).outcome is HistoricalOhlcvImportOutcomeV1.SUCCESS
    )
    appended_inputs = _inputs(
        operation="APPEND",
        parent=initial.revision_sha256,
        sessions=("2026-07-01", "2026-07-02"),
        upper="2026-07-02",
    )
    appended = _publish(tmp_path, appended_inputs)
    assert appended.revision_sha256 is not None
    assert (
        _publish(tmp_path, appended_inputs).outcome
        is HistoricalOhlcvImportOutcomeV1.SUCCESS
    )
    correction_inputs = _inputs(
        operation="CORRECTION",
        parent=initial.revision_sha256,
        corrections=[
            {"isin": "INE002A01018", "exchange": "NSE", "session": "2026-07-01"}
        ],
        open_value="101",
    )
    assert (
        _publish(tmp_path, correction_inputs).outcome
        is HistoricalOhlcvImportOutcomeV1.SUCCESS
    )
    assert (
        _publish(tmp_path, correction_inputs).outcome
        is HistoricalOhlcvImportOutcomeV1.SUCCESS
    )


def _prepare_private_initial_root(root: Path) -> None:
    lock = root / ".ingestion.lock"
    lock.write_bytes(b"")
    lock.chmod(0o600)
