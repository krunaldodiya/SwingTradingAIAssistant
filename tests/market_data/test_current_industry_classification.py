"""RED contract tests for owner-private current Industry classification V1."""

from __future__ import annotations

import builtins
import hashlib
import importlib
import json
import os
import socket
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

_SOURCE_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv"
_LEGACY_SOURCE_URL = (
    "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv"
)
_HEADER = "Company Name,Industry,Symbol,Series,ISIN Code"
_CUTOFF = datetime(2026, 8, 21, 10, tzinfo=UTC)
_SESSION = date(2026, 8, 21)
_MAX_ARTIFACT_BYTES = 1_048_576


def _api() -> Any:
    return importlib.import_module(
        "swing_trading_ai_assistant.market_data.current_industry_classification"
    )


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _isin(index: int) -> str:
    """Return a deterministic syntactically and checksum-valid ISIN."""
    prefix = f"INE{index:08d}"
    digits = "".join(str(ord(char) - 55) if char.isalpha() else char for char in prefix)
    for check in range(10):
        total = sum(
            value if position % 2 == 0 else (value * 2 - 9 if value > 4 else value * 2)
            for position, value in enumerate(map(int, reversed(digits + str(check))))
        )
        if total % 10 == 0:
            return prefix + str(check)
    raise AssertionError("unreachable ISO 6166 check digit")


def _artifact(
    *,
    company_at: dict[int, str] | None = None,
    industry_at: dict[int, str] | None = None,
    symbol_at: dict[int, str] | None = None,
    isin_at: dict[int, str] | None = None,
    row_count: int = 100,
    row_order: tuple[int, ...] | None = None,
    series: str = "EQ",
) -> bytes:
    companies = company_at or {}
    industries = industry_at or {}
    symbols = symbol_at or {}
    isins = isin_at or {}
    order = tuple(range(row_count)) if row_order is None else row_order
    rows = [
        ",".join(
            (
                companies.get(index, f"Company {index:03d}"),
                industries.get(
                    index, ("Banking", "Information Technology", "Pharma")[index % 3]
                ),
                symbols.get(index, f"SYM{index:03d}"),
                series,
                isins.get(index, _isin(index)),
            )
        )
        for index in order
    ]
    return ("\n".join((_HEADER, *rows)) + "\n").encode()


def _input(api: Any, artifact: bytes, **overrides: object) -> Any:
    digest = hashlib.sha256(artifact).hexdigest()
    value: dict[str, object] = {
        "contract_version": "current-supplied-cohort-industry-classification@v1",
        "schema_identity_sha256": api.CLASSIFICATION_SCHEMA_IDENTITY_SHA256,
        "source_url": _SOURCE_URL,
        "source_authority": "NSE_INDICES",
        "source_domain": "nsearchives.nseindia.com",
        "acquisition_method": "BOUNDED_OFFICIAL_FETCH",
        "artifact_byte_count": len(artifact),
        "artifact_sha256": digest,
        "artifact_revision": f"sha256:{digest}",
        "classification_tier": "INDUSTRY",
        "publisher_published_at": None,
        "publisher_effective_from": None,
        "publisher_effective_through": None,
        "publisher_revision": None,
        "licence_policy_identity_sha256": (
            api.CURRENT_INDUSTRY_LICENCE_POLICY_IDENTITY_SHA256
        ),
    }
    value.update(overrides)
    return api.CurrentIndustryClassificationInputV1.from_canonical_json_bytes(
        _canonical(value)
    )


def _legacy_input(api: Any, artifact: bytes, **overrides: object) -> Any:
    values: dict[str, object] = {
        "schema_identity_sha256": (api.LEGACY_CLASSIFICATION_SCHEMA_IDENTITY_SHA256),
        "source_url": _LEGACY_SOURCE_URL,
        "source_domain": "www.niftyindices.com",
        "acquisition_method": "OPERATOR_ACQUIRED",
        "licence_policy_identity_sha256": "a" * 64,
    }
    values.update(overrides)
    return _input(api, artifact, **values)


def _members(api: Any, size: int, *, exchange: str = "NSE") -> tuple[Any, ...]:
    return tuple(
        api.CurrentIndustryCohortMemberV1(
            isin=_isin(index), exchange=exchange, effective_symbol=f"SYM{index:03d}"
        )
        for index in range(size)
    )


def _parse(api: Any, artifact: bytes, **input_overrides: object) -> Any:
    return api.parse_current_industry_artifact_v1(
        _input(api, artifact, **input_overrides), artifact
    )


def _assert_failure(result: Any, state: str, *reasons: str) -> None:
    assert result.evidence_state == state
    assert result.reasons == reasons
    assert not hasattr(result, "rows") or result.rows is None
    public = result.canonical_json_bytes().decode()
    for secret in ("Company 000", _isin(0), "SYM000", "Banking"):
        assert secret not in public


def _parse_and_project(api: Any, size: int = 3) -> Any:
    artifact = _artifact()
    parsed = _parse(api, artifact)
    assert parsed.evidence_state == "PARSED"
    return api.project_current_supplied_cohort_industry_v1(
        parsed,
        "b" * 64,
        _members(api, size),
    )


def _private_lease(tmp_path: Path) -> StorageRootLease:
    tmp_path.chmod(0o700)
    acquired = StorageRootLease.try_acquire_private_empty(tmp_path)
    assert acquired.lease is not None
    return acquired.lease


def test_parses_only_exact_bounded_nse_indices_artifact_and_null_publisher_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    artifact = _artifact()

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("parser performed forbidden I/O")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    parsed = _parse(api, artifact)

    assert parsed.evidence_state == "PARSED"
    assert parsed.source_url == _SOURCE_URL
    assert parsed.source_authority == "NSE_INDICES"
    assert parsed.source_domain == "nsearchives.nseindia.com"
    assert parsed.acquisition_method == "BOUNDED_OFFICIAL_FETCH"
    assert parsed.classification_tier == "INDUSTRY"
    assert parsed.artifact_byte_count == len(artifact)
    assert parsed.artifact_sha256 == hashlib.sha256(artifact).hexdigest()
    assert parsed.artifact_revision == f"sha256:{parsed.artifact_sha256}"
    assert (
        parsed.publisher_published_at,
        parsed.publisher_effective_from,
        parsed.publisher_effective_through,
        parsed.publisher_revision,
    ) == (None, None, None, None)
    assert len(parsed.private_rows) == 100


def test_delivered_legacy_and_current_source_cases_do_not_cross_pair() -> None:
    api = _api()
    artifact = _artifact()
    legacy = api.parse_current_industry_artifact_v1(
        _legacy_input(api, artifact), artifact
    )
    assert legacy.evidence_state == "PARSED"
    assert (
        legacy.schema_identity_sha256
        == api.LEGACY_CLASSIFICATION_SCHEMA_IDENTITY_SHA256
    )
    assert legacy.source_url == _LEGACY_SOURCE_URL
    assert legacy.acquisition_method == "OPERATOR_ACQUIRED"

    for crossed in (
        _input(
            api,
            artifact,
            acquisition_method="OPERATOR_ACQUIRED",
            licence_policy_identity_sha256="a" * 64,
        ),
        _legacy_input(
            api,
            artifact,
            acquisition_method="BOUNDED_OFFICIAL_FETCH",
            licence_policy_identity_sha256=(
                api.CURRENT_INDUSTRY_LICENCE_POLICY_IDENTITY_SHA256
            ),
        ),
    ):
        _assert_failure(
            api.parse_current_industry_artifact_v1(crossed, artifact),
            "UNSUPPORTED_CAPABILITY",
            "CLASSIFICATION_SOURCE_UNSUPPORTED",
        )


@pytest.mark.parametrize("size", (1, 50))
def test_projects_exact_one_and_fifty_member_cohorts_without_exposing_unused_rows(
    size: int,
) -> None:
    api = _api()
    snapshot = _parse_and_project(api, size)

    assert snapshot.evidence_state == "PROJECTED"
    assert snapshot.cohort_size == size
    assert tuple(row.isin for row in snapshot.private_rows) == tuple(
        sorted(_isin(index) for index in range(size))
    )
    assert len(snapshot.private_rows) == size
    assert _isin(99) not in snapshot.canonical_json_bytes().decode()
    with pytest.raises(FrozenInstanceError):
        snapshot.cohort_size = 2


@pytest.mark.parametrize("size", (0, 51))
def test_rejects_out_of_bound_cohort_sizes_at_the_structural_boundary(
    size: int,
) -> None:
    api = _api()
    parsed = _parse(api, _artifact())
    with pytest.raises((TypeError, ValueError), match="(?i)cohort"):
        api.project_current_supplied_cohort_industry_v1(
            parsed, "b" * 64, _members(api, size)
        )


@pytest.mark.parametrize(
    ("artifact", "input_overrides"),
    (
        (b"\xef\xbb\xbf" + _artifact(), {}),
        (
            _artifact().replace(
                _HEADER.encode(), b"Company,Industry,Symbol,Series,ISIN Code"
            ),
            {},
        ),
        (_artifact(row_count=99), {}),
        (_artifact(row_count=101), {}),
        (_artifact(series="BE"), {}),
        (_artifact(industry_at={0: "Banking "}), {}),
        (_artifact(industry_at={0: f"Banking {_isin(0)}"}), {}),
        (_artifact(), {"artifact_sha256": "f" * 64}),
        (_artifact(), {"artifact_byte_count": len(_artifact()) + 1}),
        (b"x" * (_MAX_ARTIFACT_BYTES + 1), {}),
    ),
    ids=(
        "bom",
        "wrong-header",
        "ninety-nine-rows",
        "one-hundred-one-rows",
        "non-eq",
        "surrounding-space",
        "identity-bearing-industry",
        "digest-mismatch",
        "byte-count-mismatch",
        "size-limit-plus-one",
    ),
)
def test_malformed_artifact_and_integrity_boundaries_fail_closed(
    artifact: bytes, input_overrides: dict[str, object]
) -> None:
    api = _api()
    result = _parse(api, artifact, **input_overrides)
    _assert_failure(result, "MALFORMED_EVIDENCE", "CLASSIFICATION_ARTIFACT_MALFORMED")


@pytest.mark.parametrize(
    "artifact",
    ("artifact", bytearray(b"artifact"), memoryview(b"artifact"), 1),
)
def test_parser_rejects_non_bytes_artifact_at_the_structural_boundary(
    artifact: object,
) -> None:
    api = _api()
    admitted = _artifact()

    with pytest.raises(TypeError, match="classification artifact invalid"):
        api.parse_current_industry_artifact_v1(_input(api, admitted), artifact)


def test_parser_preserves_none_as_typed_missing_artifact_evidence() -> None:
    api = _api()
    admitted = _artifact()

    _assert_failure(
        api.parse_current_industry_artifact_v1(_input(api, admitted), None),
        "INSUFFICIENT_EVIDENCE",
        "CLASSIFICATION_ARTIFACT_MISSING",
    )


@pytest.mark.parametrize(
    "input_overrides",
    (
        {"source_url": _SOURCE_URL + "?redirected=1"},
        {"source_domain": "www.niftyindices.com"},
        {"source_authority": "YFINANCE"},
        {"acquisition_method": "NETWORK"},
        {"classification_tier": "SECTOR"},
    ),
    ids=(
        "url-variant",
        "alternate-domain",
        "alternate-authority",
        "network",
        "sector-tier",
    ),
)
def test_unsupported_source_or_tier_never_uses_a_fallback(
    input_overrides: dict[str, object],
) -> None:
    api = _api()
    result = _parse(api, _artifact(), **input_overrides)
    expected = (
        "CLASSIFICATION_TIER_UNSUPPORTED"
        if input_overrides.get("classification_tier") == "SECTOR"
        else "CLASSIFICATION_SOURCE_UNSUPPORTED"
    )
    _assert_failure(result, "UNSUPPORTED_CAPABILITY", expected)


def test_requires_exact_nse_isin_projection_and_never_reduces_the_denominator() -> None:
    api = _api()
    parsed = _parse(api, _artifact())
    bse = api.project_current_supplied_cohort_industry_v1(
        parsed, "b" * 64, _members(api, 1, exchange="BSE")
    )
    absent = api.project_current_supplied_cohort_industry_v1(
        parsed,
        "b" * 64,
        (
            api.CurrentIndustryCohortMemberV1(
                isin=_isin(999), exchange="NSE", effective_symbol="OUTSIDE"
            ),
        ),
    )
    for result in (bse, absent):
        _assert_failure(
            result,
            "UNSUPPORTED_CAPABILITY",
            "CLASSIFICATION_MEMBER_UNSUPPORTED",
        )
        assert result.cohort_size == 1


def test_projection_is_timeless_and_retention_stamps_trusted_utc_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    artifact = _artifact()
    snapshot = _parse_and_project(api, 1)
    known_at = datetime.now(UTC)
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: known_at)
    lease = _private_lease(tmp_path)
    archive = api.FileCurrentIndustryArchiveV1(tmp_path)
    try:
        retained = archive.archive_exact(
            _input(api, artifact), artifact, snapshot, lease
        )
    finally:
        lease.close()

    assert retained.known_at == known_at + api._RETENTION_COMPLETION_SAFETY_MARGIN
    assert not hasattr(snapshot, "known_at")
    assert not hasattr(snapshot, "decision_cutoff")


def test_archive_owns_its_clock_and_binds_completion_time_to_retained_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    artifact = _artifact()
    snapshot = _parse_and_project(api, 1)
    clock = datetime.now(UTC)
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: clock)
    lease = _private_lease(tmp_path)
    try:
        retained = api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, lease
        )
    finally:
        lease.close()

    assert retained.known_at == clock + api._RETENTION_COMPLETION_SAFETY_MARGIN
    assert (
        retained.retained_identity_sha256
        == hashlib.sha256(
            retained.canonical_json_bytes(include_identity=False)
        ).hexdigest()
    )


@pytest.mark.parametrize(
    "field",
    ("Company Name", "Symbol", "Series"),
)
def test_parser_rejects_formula_prefixes_in_every_source_text_field(field: str) -> None:
    api = _api()
    artifact = _artifact().replace(
        {
            "Company Name": b"Company 000",
            "Symbol": b"SYM000",
            "Series": b"EQ",
        }[field],
        b"=FORMULA",
        1,
    )

    _assert_failure(
        _parse(api, artifact),
        "MALFORMED_EVIDENCE",
        "CLASSIFICATION_ARTIFACT_MALFORMED",
    )


def test_parser_rejects_noncanonical_nse_symbol_grammar() -> None:
    api = _api()

    _assert_failure(
        _parse(api, _artifact(symbol_at={0: "not_nse"})),
        "MALFORMED_EVIDENCE",
        "CLASSIFICATION_ARTIFACT_MALFORMED",
    )


def test_archive_is_immutable_content_addressed_and_idempotent(tmp_path: Path) -> None:
    api = _api()
    artifact = _artifact()
    snapshot = _parse_and_project(api)
    archive = api.FileCurrentIndustryArchiveV1(tmp_path)
    lease = _private_lease(tmp_path)
    try:
        first = archive.archive_exact(_input(api, artifact), artifact, snapshot, lease)
        second = archive.archive_exact(_input(api, artifact), artifact, snapshot, lease)
    finally:
        lease.close()

    assert first.evidence_state == second.evidence_state == "RETAINED"
    assert first.raw_artifact_sha256 == hashlib.sha256(artifact).hexdigest()
    assert first.snapshot_identity_sha256 == snapshot.snapshot_identity_sha256
    assert first.archive_identity_sha256 == second.archive_identity_sha256
    public = first.canonical_json_bytes().decode()
    for secret in ("Company 000", _isin(0), "SYM000", "Banking", str(tmp_path)):
        assert secret not in public


def test_archive_reconstructs_a_complete_deterministic_receipt_after_process_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    artifact = _artifact()
    snapshot = _parse_and_project(api)
    clock = datetime.now(UTC)
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: clock)
    first_lease = _private_lease(tmp_path)
    try:
        first = api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, first_lease
        )
    finally:
        first_lease.close()

    assert not hasattr(api, "parse_retained_current_industry_receipt_v1")
    assert not hasattr(api, "RetainedCurrentIndustryReceiptV1")

    marker_path = (
        tmp_path
        / ".current-industry-classification-v1"
        / f"completion-{snapshot.snapshot_identity_sha256}.json"
    )
    assert marker_path.is_file()

    monkeypatch.setattr(
        api,
        "_trusted_utc_now",
        lambda: (_ for _ in ()).throw(AssertionError("duplicate timestamp")),
    )
    acquired = StorageRootLease.try_acquire_existing(tmp_path)
    assert acquired.lease is not None
    try:
        second = api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, acquired.lease
        )
    finally:
        acquired.lease.close()

    assert second.known_at == first.known_at
    assert (
        second.archive_receipt_identity_sha256 == first.archive_receipt_identity_sha256
    )
    assert second.retained_identity_sha256 == first.retained_identity_sha256


def test_retention_receipt_bound_round_trips_maximum_admitted_unicode_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    wide_industry = "\U00010000" * 512
    artifact = _artifact(industry_at=dict.fromkeys(range(50), wide_industry))
    snapshot = api.project_current_supplied_cohort_industry_v1(
        _parse(api, artifact),
        "b" * 64,
        _members(api, 50),
    )
    clock = datetime.now(UTC)
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: clock)
    first_lease = _private_lease(tmp_path)
    try:
        first = api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, first_lease
        )
    finally:
        first_lease.close()

    receipt_path = (
        tmp_path
        / ".current-industry-classification-v1"
        / f"retained-{snapshot.snapshot_identity_sha256}.json"
    )
    assert len(receipt_path.read_bytes()) <= api._MAX_RETENTION_RECEIPT_BYTES

    monkeypatch.setattr(
        api,
        "_trusted_utc_now",
        lambda: (_ for _ in ()).throw(AssertionError("replay sampled a clock")),
    )
    acquired = StorageRootLease.try_acquire_existing(tmp_path)
    assert acquired.lease is not None
    try:
        second = api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, acquired.lease
        )
    finally:
        acquired.lease.close()

    assert second.canonical_json_bytes() == first.canonical_json_bytes()


def test_retention_receipt_limit_plus_one_fails_before_publication_and_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    artifact = _artifact()
    snapshot = _parse_and_project(api)
    over_limit = b"x" * (api._MAX_RETENTION_RECEIPT_BYTES + 1)
    with pytest.raises(ValueError):
        api._retention_receipt_value(over_limit)

    def oversized_receipt(_retained: object) -> bytes:
        return over_limit

    monkeypatch.setattr(api, "_retention_receipt_bytes", oversized_receipt)
    lease = _private_lease(tmp_path)
    try:
        result = api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, lease
        )
    finally:
        lease.close()

    _assert_failure(result, "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARCHIVE_FAILED")
    receipt_path = (
        tmp_path
        / ".current-industry-classification-v1"
        / f"retained-{snapshot.snapshot_identity_sha256}.json"
    )
    assert not receipt_path.exists()

    monkeypatch.undo()
    replay_root = tmp_path / "replay"
    replay_root.mkdir(mode=0o700)
    first_lease = _private_lease(replay_root)
    try:
        api.FileCurrentIndustryArchiveV1(replay_root).archive_exact(
            _input(api, artifact), artifact, snapshot, first_lease
        )
    finally:
        first_lease.close()
    replay_receipt = (
        replay_root
        / ".current-industry-classification-v1"
        / f"retained-{snapshot.snapshot_identity_sha256}.json"
    )
    replay_receipt.chmod(0o600)
    replay_receipt.write_bytes(over_limit)
    replay_receipt.chmod(0o400)
    acquired = StorageRootLease.try_acquire_existing(replay_root)
    assert acquired.lease is not None
    try:
        replay = api.FileCurrentIndustryArchiveV1(replay_root).archive_exact(
            _input(api, artifact), artifact, snapshot, acquired.lease
        )
    finally:
        acquired.lease.close()

    _assert_failure(replay, "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARCHIVE_FAILED")


@pytest.mark.parametrize("fault", ("missing", "corrupt", "late"))
def test_archive_rejects_missing_corrupt_or_late_completion_marker(
    tmp_path: Path, fault: str
) -> None:
    api = _api()
    artifact = _artifact()
    snapshot = _parse_and_project(api)
    first_lease = _private_lease(tmp_path)
    try:
        first = api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, first_lease
        )
    finally:
        first_lease.close()

    marker_path = (
        tmp_path
        / ".current-industry-classification-v1"
        / f"completion-{snapshot.snapshot_identity_sha256}.json"
    )
    marker_path.chmod(0o600)
    if fault == "missing":
        marker_path.unlink()
    elif fault == "corrupt":
        marker_path.write_bytes(b"{}")
        marker_path.chmod(0o400)
    else:
        late = first.known_at + timedelta(microseconds=1)
        late_ns = int(late.timestamp()) * 1_000_000_000 + late.microsecond * 1_000
        os.utime(marker_path, ns=(late_ns, late_ns))
        marker_path.chmod(0o400)

    acquired = StorageRootLease.try_acquire_existing(tmp_path)
    assert acquired.lease is not None
    try:
        result = api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, acquired.lease
        )
    finally:
        acquired.lease.close()

    _assert_failure(result, "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARCHIVE_FAILED")


def test_marker_deadline_uses_link_metadata_not_only_temp_write_time() -> None:
    api = _api()
    info = SimpleNamespace(st_mtime_ns=10, st_ctime_ns=20)

    assert api._marker_filesystem_mtime_ns(info) == 20


def test_late_first_completion_never_publishes_marker_and_retry_fails_missing_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    artifact = _artifact()
    snapshot = _parse_and_project(api)
    sampled_at = datetime.now(UTC)
    late = (
        sampled_at + api._RETENTION_COMPLETION_SAFETY_MARGIN + timedelta(microseconds=1)
    )
    clock_values = iter((sampled_at, late))
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: next(clock_values))
    first_lease = _private_lease(tmp_path)
    try:
        first = api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, first_lease
        )
    finally:
        first_lease.close()

    _assert_failure(first, "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARCHIVE_FAILED")
    archive_directory = tmp_path / ".current-industry-classification-v1"
    receipt_path = (
        archive_directory / f"retained-{snapshot.snapshot_identity_sha256}.json"
    )
    marker_path = (
        archive_directory / f"completion-{snapshot.snapshot_identity_sha256}.json"
    )
    assert receipt_path.is_file()
    assert not marker_path.exists()

    monkeypatch.setattr(
        api,
        "_trusted_utc_now",
        lambda: (_ for _ in ()).throw(AssertionError("retry sampled a clock")),
    )
    acquired = StorageRootLease.try_acquire_existing(tmp_path)
    assert acquired.lease is not None
    try:
        retry = api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, acquired.lease
        )
    finally:
        acquired.lease.close()

    _assert_failure(retry, "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARCHIVE_FAILED")
    assert not marker_path.exists()


def test_archive_rejects_corrupt_deterministic_retained_receipt(tmp_path: Path) -> None:
    api = _api()
    artifact = _artifact()
    snapshot = _parse_and_project(api)
    first_lease = _private_lease(tmp_path)
    try:
        api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, first_lease
        )
    finally:
        first_lease.close()

    receipt_path = (
        tmp_path
        / ".current-industry-classification-v1"
        / f"retained-{snapshot.snapshot_identity_sha256}.json"
    )
    receipt_path.chmod(0o600)
    receipt_path.write_bytes(receipt_path.read_bytes().replace(b"Banking", b"Bunking"))
    receipt_path.chmod(0o400)
    acquired = StorageRootLease.try_acquire_existing(tmp_path)
    assert acquired.lease is not None
    try:
        result = api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, acquired.lease
        )
    finally:
        acquired.lease.close()

    _assert_failure(result, "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARCHIVE_FAILED")


def test_archive_rejects_missing_deterministic_retained_receipt_after_snapshot(
    tmp_path: Path,
) -> None:
    api = _api()
    artifact = _artifact()
    snapshot = _parse_and_project(api)
    first_lease = _private_lease(tmp_path)
    try:
        api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, first_lease
        )
    finally:
        first_lease.close()

    receipt_path = (
        tmp_path
        / ".current-industry-classification-v1"
        / f"retained-{snapshot.snapshot_identity_sha256}.json"
    )
    receipt_path.chmod(0o600)
    receipt_path.unlink()
    acquired = StorageRootLease.try_acquire_existing(tmp_path)
    assert acquired.lease is not None
    try:
        result = api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, acquired.lease
        )
    finally:
        acquired.lease.close()

    _assert_failure(result, "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARCHIVE_FAILED")


def test_archive_rejects_spliced_deterministic_retained_receipt(tmp_path: Path) -> None:
    api = _api()
    artifact = _artifact()
    first_snapshot = _parse_and_project(api, 1)
    second_snapshot = _parse_and_project(api, 2)
    first_lease = _private_lease(tmp_path)
    try:
        api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, first_snapshot, first_lease
        )
    finally:
        first_lease.close()
    acquired = StorageRootLease.try_acquire_existing(tmp_path)
    assert acquired.lease is not None
    try:
        api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, second_snapshot, acquired.lease
        )
    finally:
        acquired.lease.close()

    archive_directory = tmp_path / ".current-industry-classification-v1"
    first_receipt = (
        archive_directory / f"retained-{first_snapshot.snapshot_identity_sha256}.json"
    )
    second_receipt = (
        archive_directory / f"retained-{second_snapshot.snapshot_identity_sha256}.json"
    )
    first_receipt.chmod(0o600)
    first_receipt.write_bytes(second_receipt.read_bytes())
    first_receipt.chmod(0o400)
    acquired = StorageRootLease.try_acquire_existing(tmp_path)
    assert acquired.lease is not None
    try:
        result = api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, first_snapshot, acquired.lease
        )
    finally:
        acquired.lease.close()

    _assert_failure(result, "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARCHIVE_FAILED")


@pytest.mark.parametrize(
    "publish_error",
    (FileExistsError("private collision"), OSError("unsafe private link")),
    ids=("collision", "unsafe-link"),
)
def test_archive_rejects_private_publish_collision_or_unsafe_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    publish_error: OSError,
) -> None:
    api = _api()
    artifact = _artifact()
    snapshot = _parse_and_project(api)
    archive = api.FileCurrentIndustryArchiveV1(tmp_path)
    lease = _private_lease(tmp_path)

    def fail_link(*_args: object, **_kwargs: object) -> object:
        raise publish_error

    monkeypatch.setattr(os, "link", fail_link)
    try:
        result = archive.archive_exact(_input(api, artifact), artifact, snapshot, lease)
    finally:
        lease.close()
    _assert_failure(result, "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARCHIVE_FAILED")


def _timeless_input(api: Any, artifact: bytes) -> Any:
    digest = hashlib.sha256(artifact).hexdigest()
    value = {
        "contract_version": "current-supplied-cohort-industry-classification@v1",
        "schema_identity_sha256": api.CLASSIFICATION_SCHEMA_IDENTITY_SHA256,
        "source_url": _SOURCE_URL,
        "source_authority": "NSE_INDICES",
        "source_domain": "nsearchives.nseindia.com",
        "acquisition_method": "BOUNDED_OFFICIAL_FETCH",
        "artifact_byte_count": len(artifact),
        "artifact_sha256": digest,
        "artifact_revision": f"sha256:{digest}",
        "classification_tier": "INDUSTRY",
        "publisher_published_at": None,
        "publisher_effective_from": None,
        "publisher_effective_through": None,
        "publisher_revision": None,
        "licence_policy_identity_sha256": (
            api.CURRENT_INDUSTRY_LICENCE_POLICY_IDENTITY_SHA256
        ),
    }
    return api.CurrentIndustryClassificationInputV1.from_canonical_json_bytes(
        _canonical(value)
    )


def test_input_and_parsed_artifact_are_timeless_until_trusted_retention() -> None:
    api = _api()
    artifact = _artifact()

    parsed = api.parse_current_industry_artifact_v1(
        _timeless_input(api, artifact), artifact
    )

    assert parsed.evidence_state == "PARSED"
    assert not hasattr(_timeless_input(api, artifact), "known_at")
    assert not hasattr(parsed, "known_at")


@pytest.mark.parametrize(
    ("industry", "expected_reason"),
    (
        (f"Banking {_isin(1)}", "CLASSIFICATION_ARTIFACT_MALFORMED"),
        ("Bank\u0085ing", "CLASSIFICATION_ARTIFACT_MALFORMED"),
        ("Bank\u202e ing", "CLASSIFICATION_ARTIFACT_MALFORMED"),
        ("Bank\u2028ing", "CLASSIFICATION_ARTIFACT_MALFORMED"),
        ("=FORMULA", "CLASSIFICATION_ARTIFACT_MALFORMED"),
        ("+FORMULA", "CLASSIFICATION_ARTIFACT_MALFORMED"),
        ("-FORMULA", "CLASSIFICATION_ARTIFACT_MALFORMED"),
        ("@FORMULA", "CLASSIFICATION_ARTIFACT_MALFORMED"),
    ),
)
def test_parser_rejects_cross_row_identity_and_unsafe_industry_labels(
    industry: str, expected_reason: str
) -> None:
    api = _api()
    result = _parse(api, _artifact(industry_at={0: industry}))

    _assert_failure(result, "MALFORMED_EVIDENCE", expected_reason)


def test_parser_distinguishes_duplicate_equal_from_conflicting_identity_evidence() -> (
    None
):
    api = _api()
    duplicate_equal = _artifact(
        industry_at={1: "Banking"},
        isin_at={1: _isin(0)},
        symbol_at={1: "SYM000"},
    )
    conflicting_isin = _artifact(isin_at={1: _isin(0)})
    conflicting_symbol = _artifact(symbol_at={1: "SYM000"})

    _assert_failure(
        _parse(api, duplicate_equal),
        "MALFORMED_EVIDENCE",
        "CLASSIFICATION_AMBIGUOUS",
    )
    _assert_failure(
        _parse(api, conflicting_isin),
        "MALFORMED_EVIDENCE",
        "CLASSIFICATION_CONFLICTING",
    )
    _assert_failure(
        _parse(api, conflicting_symbol),
        "MALFORMED_EVIDENCE",
        "CLASSIFICATION_CONFLICTING",
    )


def test_archive_requires_admitted_root(tmp_path: Path) -> None:
    api = _api()
    archive = api.FileCurrentIndustryArchiveV1(tmp_path)

    assert type(archive) is api.FileCurrentIndustryArchiveV1


def test_projection_rejects_source_symbol_mismatch_and_private_representations() -> (
    None
):
    api = _api()
    parsed = _parse(api, _artifact())
    mismatch = api.project_current_supplied_cohort_industry_v1(
        parsed,
        "b" * 64,
        (
            api.CurrentIndustryCohortMemberV1(
                isin=_isin(0), exchange="NSE", effective_symbol="OTHER"
            ),
        ),
    )

    _assert_failure(mismatch, "MALFORMED_EVIDENCE", "MEMBER_IDENTITY_MISMATCH")
    assert _isin(0) not in repr(parsed)
    with pytest.raises(TypeError):
        api.PrivateCurrentIndustrySnapshotV1()
    with pytest.raises(TypeError):
        api.RetainedCurrentIndustrySnapshotV1()


def test_input_rejects_caller_supplied_known_at() -> None:
    api = _api()
    artifact = _artifact()
    value = json.loads(_input(api, artifact).canonical_json_bytes())
    value["known_at"] = "2026-08-21T10:00:00.000000Z"

    with pytest.raises(ValueError, match="classification input invalid"):
        api.CurrentIndustryClassificationInputV1.from_canonical_json_bytes(
            _canonical(value)
        )


@pytest.mark.parametrize("fault", ("unsafe-directory", "final-verification"))
def test_archive_fails_closed_on_final_directory_or_receipt_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    api = _api()
    artifact = _artifact()
    snapshot = _parse_and_project(api)
    lease = _private_lease(tmp_path)
    archive = api.FileCurrentIndustryArchiveV1(tmp_path)
    if fault == "unsafe-directory":
        directory = tmp_path / ".current-industry-classification-v1"
        directory.mkdir(mode=0o700)
        directory.chmod(0o755)
    else:
        monkeypatch.setattr(
            api,
            "_verify_archive_binding",
            lambda *_args: (_ for _ in ()).throw(OSError("replaced binding")),
        )
    try:
        result = archive.archive_exact(_input(api, artifact), artifact, snapshot, lease)
    finally:
        lease.close()

    _assert_failure(result, "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARCHIVE_FAILED")


@pytest.mark.parametrize(
    "industry",
    (
        f"Banking {_isin(1).lower()}",
        "Insurance sym.001",
        "Finance SYM_002",
        "Banks SYM-003",
        "Banks SYM&004",
    ),
)
def test_identity_bearing_labels_reject_all_source_identities_case_insensitively(
    industry: str,
) -> None:
    api = _api()
    symbol_at = {
        1: "SYM.001",
        2: "SYM_002",
        3: "SYM-003",
        4: "SYM&004",
    }
    assert _parse(api, _artifact(symbol_at=symbol_at)).evidence_state == "PARSED"

    _assert_failure(
        _parse(api, _artifact(industry_at={0: industry}, symbol_at=symbol_at)),
        "MALFORMED_EVIDENCE",
        "CLASSIFICATION_ARTIFACT_MALFORMED",
    )


@pytest.mark.parametrize(
    ("industry", "company_at"),
    (
        ("Company 001", None),
        ("cOmPaNy 002", None),
        ("XCompany 001Y", None),
        ("élan", {1: "ÉLAN"}),
        ("Åland", {1: "A\u030aland"}),
        ("A\u030aland", {1: "Åland"}),
        ("Åland", {1: "Åland"}),
    ),
)
def test_identity_bearing_labels_reject_cross_row_company_names_case_insensitively(
    industry: str, company_at: dict[int, str] | None
) -> None:
    api = _api()

    _assert_failure(
        _parse(
            api,
            _artifact(company_at=company_at, industry_at={0: industry}),
        ),
        "MALFORMED_EVIDENCE",
        "CLASSIFICATION_ARTIFACT_MALFORMED",
    )


def test_classification_schema_freezes_nfkc_casefold_privacy_key() -> None:
    api = _api()

    assert (
        api.CLASSIFICATION_SCHEMA_IDENTITY_SHA256
        == "b5e5bfd3aded2af88230447b28bebada4f101f8f9eb8b2dd03b77177626db175"
    )
    assert (
        api.LEGACY_CLASSIFICATION_SCHEMA_IDENTITY_SHA256
        == "29b292b6d8f6f048ca4a86ef3b5185b6be5a903770fd8f2be5818c76932b2552"
    )


def test_parser_schema_identity_binds_input_parsed_snapshot_and_retention(
    tmp_path: Path,
) -> None:
    api = _api()
    artifact = _artifact()
    parsed = _parse(api, artifact)
    snapshot = _parse_and_project(api)
    lease = _private_lease(tmp_path)
    try:
        retained = api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, lease
        )
    finally:
        lease.close()

    expected = api.CLASSIFICATION_SCHEMA_IDENTITY_SHA256
    assert (
        _input(api, artifact).schema_identity_sha256,
        parsed.schema_identity_sha256,
        snapshot.schema_identity_sha256,
        retained.schema_identity_sha256,
    ) == (expected, expected, expected, expected)
    assert expected in snapshot.canonical_json_bytes().decode()
    assert expected in retained.canonical_json_bytes().decode()


def test_input_rejects_a_substituted_classification_schema_identity() -> None:
    api = _api()
    value = json.loads(_input(api, _artifact()).canonical_json_bytes())
    value["schema_identity_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="classification input invalid"):
        api.CurrentIndustryClassificationInputV1.from_canonical_json_bytes(
            _canonical(value)
        )


def test_cohort_member_representation_redacts_identity() -> None:
    api = _api()
    member = api.CurrentIndustryCohortMemberV1(
        isin=_isin(0), exchange="NSE", effective_symbol="SYM000"
    )

    assert _isin(0) not in repr(member)


def test_retained_snapshot_constructor_is_unavailable() -> None:
    api = _api()

    with pytest.raises(TypeError, match="constructor unavailable"):
        api.RetainedCurrentIndustrySnapshotV1()


def test_archive_rejects_root_permissions_before_and_after_archive_open(
    tmp_path: Path,
) -> None:
    api = _api()
    artifact = _artifact()
    snapshot = _parse_and_project(api)
    lease = _private_lease(tmp_path)
    tmp_path.chmod(0o777)
    try:
        result = api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
            _input(api, artifact), artifact, snapshot, lease
        )
    finally:
        lease.close()

    _assert_failure(result, "INSUFFICIENT_EVIDENCE", "CLASSIFICATION_ARCHIVE_FAILED")
