"""Retained member-local Event V2 tests for Issue #187."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from swing_trading_ai_assistant.market_data import current_event_notice as event_v1
from swing_trading_ai_assistant.market_data import current_event_notice_v2 as event_v2
from swing_trading_ai_assistant.market_data import (
    current_research_binding_v2 as mapping_v2,
)
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.current_event_notice import (
    EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
    CurrentEventNoticeInputV1,
)
from swing_trading_ai_assistant.market_data.current_research_binding_v2 import (
    resolve_current_research_binding_v2,
)
from swing_trading_ai_assistant.market_data.instrument_snapshot import (
    SNAPSHOT_SOURCE_V1,
    FetchedInstrumentSnapshotV1,
    InstrumentSnapshotStoreV1,
)
from swing_trading_ai_assistant.market_data.instruments import InstrumentCatalog
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

_KNOWN = datetime(2026, 8, 26, 9, tzinfo=UTC)
_SOURCE_DATE = date(2026, 8, 26)
_CUTOFF = datetime(2026, 8, 26, 9, 5, tzinfo=UTC)
_HEADER = (
    "SYMBOL,COMPANY NAME,SUBJECT,DETAILS,BROADCAST DATE/TIME,RECEIPT,"
    "DISSEMINATION,DIFFERENCE,ATTACHMENT"
)
_INSTRUMENTS = [
    {
        "segment": "NSE_EQ",
        "name": "Alpha Limited",
        "exchange": "NSE",
        "isin": "INE002A01018",
        "instrument_type": "EQ",
        "instrument_key": "NSE_EQ|INE002A01018",
        "trading_symbol": "ALPHA",
    },
    {
        "segment": "NSE_EQ",
        "name": "Punjab National Bank",
        "exchange": "NSE",
        "isin": "INE160A01022",
        "instrument_type": "EQ",
        "instrument_key": "NSE_EQ|INE160A01022",
        "trading_symbol": "PNB",
    },
]


def _artifact(
    source_date: date = _SOURCE_DATE, *, symbols: tuple[str, str] = ("ALPHA", "PNB")
) -> bytes:
    event_date = source_date.strftime("%d-%b-%Y")
    receipt_date = source_date.isoformat()
    rows = [
        (
            f"{symbols[0]},Alpha Limited,Board update,Duplicate disclosure,"
            f"{event_date} 14:00:00,{receipt_date} 13:59:00,"
            f"{event_date} 14:00:01,00:00:01,-"
        ),
        (
            f"{symbols[0]},Alpha Limited,Board update,Duplicate disclosure,"
            f"{event_date} 14:00:00,{receipt_date} 13:59:00,"
            f"{event_date} 14:00:01,00:00:01,-"
        ),
        (
            f"{symbols[1]},Punjab National Bank,Board meeting,Quarterly update,"
            f"{event_date} 14:00:00,{receipt_date} 13:59:00,"
            f"{event_date} 14:00:01,00:00:01,-"
        ),
    ]
    return ("\ufeff" + "\n".join((_HEADER, *rows)) + "\n").encode()


def _input(raw: bytes, source_date: date = _SOURCE_DATE) -> CurrentEventNoticeInputV1:
    return CurrentEventNoticeInputV1(
        schema_identity_sha256=EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
        source_url=(
            "https://www.nseindia.com/companies-listing/"
            "corporate-filings-announcements?tabIndex=equity"
        ),
        source_segment="Equity",
        source_window="1D",
        source_filename=(
            f"CF-AN-equities-{(source_date.fromordinal(source_date.toordinal() - 1)).strftime('%d-%m-%Y')}"
            f"-to-{source_date.strftime('%d-%m-%Y')}.csv"
        ),
        artifact_identity_sha256=hashlib.sha256(raw).hexdigest(),
        acquisition_method="BOUNDED_OFFICIAL_FETCH",
        licence_policy_identity="nse-bounded-official-fetch-owner-private-v1",
        source_has_bom=True,
    )


def _mapping(root: Path, lease: StorageRootLease):
    decompressed = json.dumps(_INSTRUMENTS, separators=(",", ":")).encode()
    compressed = gzip.compress(decompressed, mtime=0)
    fetched = FetchedInstrumentSnapshotV1(
        datetime(2026, 8, 26, 8, tzinfo=UTC),
        date(2026, 8, 26),
        compressed,
        decompressed,
        hashlib.sha256(compressed).hexdigest(),
        hashlib.sha256(decompressed).hexdigest(),
        InstrumentCatalog.from_json_bytes(decompressed),
        None,
        None,
    )
    with DuckDBCatalog(root, lease=lease) as catalog:
        InstrumentSnapshotStoreV1(root, lease, catalog).retain(fetched)
    with DuckDBCatalog(root, lease=lease) as catalog:
        store = InstrumentSnapshotStoreV1(root, lease, catalog)
        resolved = tuple(
            store.resolve_equity(
                source=SNAPSHOT_SOURCE_V1,
                segment="NSE_EQ",
                symbol=item["trading_symbol"],
                as_of=fetched.retrieved_at,
            )
            for item in _INSTRUMENTS
        )
    return resolve_current_research_binding_v2(
        root,
        lease,
        resolved,
        selected_at=_KNOWN,
        decision_cutoff=_CUTOFF,
        schedule_identity_sha256="a" * 64,
    )


def test_retained_v2_local_duplicate_preserves_unaffected_member_and_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "event-v2"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    raw = _artifact()
    monkeypatch.setattr(event_v2, "_trusted_utc_now", lambda: _KNOWN)
    with acquired.lease as lease:
        mapping = _mapping(root, lease)
        first = event_v2.retain_current_event_notices_v2(
            root, lease, _input(raw), raw, mapping
        )
        # A retry is archive reconciliation, not a second logical acquisition.
        monkeypatch.setattr(
            event_v2,
            "_trusted_utc_now",
            lambda: datetime(2026, 8, 26, 9, 16, tzinfo=UTC),
        )
        second = event_v2.retain_current_event_notices_v2(
            root, lease, _input(raw), raw, mapping
        )

    assert first == second
    assert first.known_at == _KNOWN
    assert first.members[0].support == "CONFLICTED"
    assert first.members[0].notices == ()
    assert first.members[1].availability == "NOTICES_ADMITTED"
    assert len(first.members[1].notices) == 1
    serialized = first.canonical_json_bytes()
    assert b'"subject"' not in serialized
    assert b'"details"' not in serialized
    assert b'"attachment_url"' not in serialized
    assert b'"source_company_name"' not in serialized
    assert event_v2.validate_retained_current_event_notice_v2(first) is first


@pytest.mark.parametrize("interrupted_publish", (1, 2, 3, 4))
def test_event_v2_recovers_every_valid_publication_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interrupted_publish: int,
) -> None:
    root = tmp_path / f"event-v2-interrupt-{interrupted_publish}"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    raw = _artifact()
    monkeypatch.setattr(event_v2, "_trusted_utc_now", lambda: _KNOWN)
    original = event_v2._publish_object  # pyright: ignore[reportPrivateUsage]
    calls = 0

    def interrupt(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == interrupted_publish:
            raise RuntimeError("interrupted publication")
        original(*args, **kwargs)  # type: ignore[arg-type]

    with acquired.lease as lease:
        mapping = _mapping(root, lease)
        monkeypatch.setattr(event_v2, "_publish_object", interrupt)
        with pytest.raises(RuntimeError, match="interrupted"):
            event_v2.retain_current_event_notices_v2(
                root, lease, _input(raw), raw, mapping
            )
        monkeypatch.setattr(event_v2, "_publish_object", original)
        retained = event_v2.retain_current_event_notices_v2(
            root, lease, _input(raw), raw, mapping
        )
    assert retained.known_at == _KNOWN
    assert len(tuple((root / ".current-event-notice-v1").glob("v2-*"))) == 4


def test_event_v2_recovers_projection_prefix_across_ist_rollover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "event-v2-rollover"
    root.mkdir(mode=0o700)
    raw = _artifact()
    monkeypatch.setattr(event_v2, "_trusted_utc_now", lambda: _KNOWN)
    original = event_v2._publish_object  # pyright: ignore[reportPrivateUsage]
    calls = 0

    def interrupt_after_projection(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("interrupted publication")
        original(*args, **kwargs)  # type: ignore[arg-type]

    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    with acquired.lease as lease:
        mapping = _mapping(root, lease)
        monkeypatch.setattr(event_v2, "_publish_object", interrupt_after_projection)
        with pytest.raises(RuntimeError, match="interrupted"):
            event_v2.retain_current_event_notices_v2(
                root, lease, _input(raw), raw, mapping
            )
        monkeypatch.setattr(
            event_v2,
            "_trusted_utc_now",
            lambda: datetime(2026, 8, 27, 9, tzinfo=UTC),
        )
        monkeypatch.setattr(event_v2, "_publish_object", original)
        recovered = event_v2.retain_current_event_notices_v2(
            root, lease, _input(raw), raw, mapping
        )
    assert recovered.known_at == _KNOWN
    assert len(tuple((root / ".current-event-notice-v1").glob("v2-*"))) == 4


def test_event_v2_corrupt_prefix_fails_before_any_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "event-v2-corrupt-prefix"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    raw = _artifact()
    monkeypatch.setattr(event_v2, "_trusted_utc_now", lambda: _KNOWN)
    with acquired.lease as lease:
        mapping = _mapping(root, lease)
        retained = event_v2.retain_current_event_notices_v2(
            root, lease, _input(raw), raw, mapping
        )
        directory = root / ".current-event-notice-v1"
        for suffix in ("projection.json", "receipt.json", "complete.json"):
            (directory / f"v2-{retained.archive_identity_sha256}.{suffix}").unlink()
        raw_path = directory / f"v2-{retained.artifact_identity_sha256}.raw.csv"
        raw_path.chmod(0o600)
        raw_path.write_bytes(b"corrupt")
        with pytest.raises(ValueError, match="immutable archive conflict"):
            event_v2.retain_current_event_notices_v2(
                root, lease, _input(raw), raw, mapping
            )
    assert not list(directory.glob("*.projection.json"))


def test_event_v2_serializes_concurrent_identical_logical_commits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "event-v2-concurrent"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    raw = _artifact()
    monkeypatch.setattr(event_v2, "_trusted_utc_now", lambda: _KNOWN)
    with acquired.lease as lease:
        mapping = _mapping(root, lease)

        def retain(_: int):
            return event_v2.retain_current_event_notices_v2(
                root, lease, _input(raw), raw, mapping
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(retain, range(2)))
    assert results[0] == results[1]
    assert len(tuple((root / ".current-event-notice-v1").glob("v2-*"))) == 4


def test_event_and_mapping_semantics_reject_fully_rehashed_nested_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "event-v2-semantic-tampering"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    raw = _artifact()
    monkeypatch.setattr(event_v2, "_trusted_utc_now", lambda: _KNOWN)
    with acquired.lease as lease:
        mapping = _mapping(root, lease)
        retained = event_v2.retain_current_event_notices_v2(
            root, lease, _input(raw), raw, mapping
        )

    malformed_mapping = copy.deepcopy(retained.mapping_projection)
    object.__setattr__(
        malformed_mapping.members[0], "mapping_identity_sha256", "b" * 64
    )
    mapping_preimage = {
        item.name: getattr(malformed_mapping, item.name)
        for item in fields(malformed_mapping)
        if item.name != "mapping_projection_identity_sha256"
    }
    object.__setattr__(
        malformed_mapping,
        "mapping_projection_identity_sha256",
        mapping_v2._digest(mapping_preimage),  # pyright: ignore[reportPrivateUsage]
    )
    with pytest.raises(ValueError, match="mapping projection"):
        malformed_mapping.__post_init__()

    malformed_notice = copy.deepcopy(retained)
    object.__setattr__(
        malformed_notice.members[1].notices[0],
        "observation_identity_sha256",
        "not-a-digest",
    )
    event_preimage = {
        item.name: getattr(malformed_notice, item.name)
        for item in fields(malformed_notice)
        if item.name not in {"result_identity_sha256", "_seal"}
    }
    object.__setattr__(
        malformed_notice,
        "result_identity_sha256",
        event_v2._digest(event_preimage),  # pyright: ignore[reportPrivateUsage]
    )
    assert not event_v2.current_event_notice_semantics_are_valid_v2(malformed_notice)

    unauthorized = copy.deepcopy(retained)
    object.__setattr__(unauthorized, "source_url", "https://example.invalid/events")
    projection_core = {
        item.name: getattr(unauthorized, item.name)
        for item in fields(unauthorized)
        if item.name
        not in {
            "snapshot_identity_sha256",
            "archive_identity_sha256",
            "receipt_identity_sha256",
            "retained_identity_sha256",
            "result_identity_sha256",
            "_seal",
        }
    }
    snapshot_identity = hashlib.sha256(
        event_v2._canonical(projection_core)  # pyright: ignore[reportPrivateUsage]
    ).hexdigest()
    archive_identity = event_v2._v2_archive_identity(  # pyright: ignore[reportPrivateUsage]
        projection_core
    )
    receipt_core = {
        "protocol": "current-event-notice-v2-receipt@v2",
        "archive_identity_sha256": archive_identity,
        "artifact_identity_sha256": unauthorized.artifact_identity_sha256,
        "snapshot_identity_sha256": snapshot_identity,
        "runtime_code_identity_sha256": unauthorized.runtime_code_identity_sha256,
        "known_at": unauthorized.known_at,
        "attempt_history_identity_sha256": (
            unauthorized.attempt_history_identity_sha256
        ),
    }
    receipt_identity = event_v2._digest(  # pyright: ignore[reportPrivateUsage]
        receipt_core
    )
    retained_identity = event_v2._digest(  # pyright: ignore[reportPrivateUsage]
        {
            **receipt_core,
            "receipt_identity_sha256": receipt_identity,
            "mapping_projection_identity_sha256": (
                unauthorized.mapping_projection.mapping_projection_identity_sha256
            ),
        }
    )
    for name, value in (
        ("snapshot_identity_sha256", snapshot_identity),
        ("archive_identity_sha256", archive_identity),
        ("receipt_identity_sha256", receipt_identity),
        ("retained_identity_sha256", retained_identity),
    ):
        object.__setattr__(unauthorized, name, value)
    unauthorized_preimage = {
        item.name: getattr(unauthorized, item.name)
        for item in fields(unauthorized)
        if item.name not in {"result_identity_sha256", "_seal"}
    }
    object.__setattr__(
        unauthorized,
        "result_identity_sha256",
        event_v2._digest(  # pyright: ignore[reportPrivateUsage]
            unauthorized_preimage
        ),
    )
    assert not event_v2.current_event_notice_semantics_are_valid_v2(unauthorized)


@pytest.mark.parametrize(
    "raw",
    (
        b"[]",
        b'{"projection":1,"projection":2}',
        b'{"projection":' + b"[" * 17 + b"]" * 17 + b"}",
        b'{"projection":"' + b"x" * 4097 + b'"}',
    ),
)
def test_event_v2_bounded_prefix_decoder_rejects_malformed_shapes(raw: bytes) -> None:
    with pytest.raises(ValueError, match="immutable archive conflict"):
        event_v2._decode_stored_projection_v2(  # pyright: ignore[reportPrivateUsage]
            raw, {"projection"}
        )


def test_event_v2_bounded_prefix_decoder_rejects_before_over_limit_attachment() -> None:
    exact = b'{"x":[' + b",".join([b"0"] * 49_997) + b"]}"
    exact_stats = event_v2._BoundedJsonStatsV2()  # pyright: ignore[reportPrivateUsage]
    assert event_v2._decode_stored_projection_v2(  # pyright: ignore[reportPrivateUsage]
        exact, {"x"}, exact_stats
    ) == {"x": [0] * 49_997}
    assert exact_stats.nodes_admitted == exact_stats.nodes_allocated == 50_000
    overflow = b'{"x":[' + b",".join([b"0"] * 49_998) + b"]}"
    overflow_stats = event_v2._BoundedJsonStatsV2()  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(ValueError, match="immutable archive conflict"):
        event_v2._decode_stored_projection_v2(  # pyright: ignore[reportPrivateUsage]
            overflow, {"x"}, overflow_stats
        )
    assert overflow_stats.nodes_admitted == overflow_stats.nodes_allocated == 50_000
    assert overflow_stats.nodes_attached <= 50_000
    assert overflow_stats.nodes_rejected_before_allocation == 1


def test_event_v2_post_admission_mutation_and_future_source_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "event-v2-negative"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    raw = _artifact()
    monkeypatch.setattr(event_v2, "_trusted_utc_now", lambda: _KNOWN)
    with acquired.lease as lease:
        mapping = _mapping(root, lease)
        retained = event_v2.retain_current_event_notices_v2(
            root, lease, _input(raw), raw, mapping
        )
    object.__setattr__(retained, "known_at", _CUTOFF)
    with pytest.raises(ValueError, match="not admitted"):
        event_v2.validate_retained_current_event_notice_v2(retained)

    later = tmp_path / "event-v2-future"
    later.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(later)
    assert acquired.lease is not None
    monkeypatch.setattr(
        event_v2, "_trusted_utc_now", lambda: datetime(2026, 8, 27, 9, tzinfo=UTC)
    )
    with acquired.lease as lease:
        mapping = _mapping(later, lease)
        with pytest.raises(ValueError, match="source-time"):
            event_v2.retain_current_event_notices_v2(
                later, lease, _input(raw), raw, mapping
            )


def _binding_with_origin(mapping: Any, origin: str) -> Any:
    """Build synthetic admitted mappings only for source-date rejection tests."""
    projection = mapping_v2.validate_current_research_binding_v2(mapping)
    if origin == "RETAINED_INSTRUMENT_SNAPSHOT":
        return mapping
    members = tuple(
        replace(
            member,
            mapping_identity_sha256=mapping_v2.mapping_identity_v3(
                isin=member.isin,
                exchange=member.exchange,
                instrument_type=member.instrument_type,
                segment=member.segment,
                effective_symbol=member.effective_symbol,
                provider_symbol=member.provider_symbol,
                mapping_valid_from=member.mapping_valid_from,
                mapping_valid_through=member.mapping_valid_through,
            ),
            discovery_source=None,
            discovery_observation_identity_sha256=None,
            discovery_retrieved_at=None,
            discovery_failure_reasons=("RAW_MAPPING_MISSING",),
        )
        for member in projection.members
    )
    return mapping_v2._admit(  # pyright: ignore[reportPrivateUsage]
        mapping_v2._projection(  # pyright: ignore[reportPrivateUsage]
            origin="RETAINED_SAME_PASS_CONTEXT",
            selected_at=projection.selected_at,
            decision_cutoff=projection.decision_cutoff,
            schedule_identity_sha256=projection.schedule_identity_sha256,
            context_schedule_identity_sha256="f" * 64,
            members=members,
            context=("a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64),
        )
    )


@pytest.mark.parametrize(
    ("origin", "symbols"),
    (
        ("RETAINED_INSTRUMENT_SNAPSHOT", ("ALPHA", "PNB")),
        ("RETAINED_INSTRUMENT_SNAPSHOT", ("OUTSIDE", "UNLISTED")),
        ("RETAINED_SAME_PASS_CONTEXT", ("ALPHA", "PNB")),
        ("RETAINED_SAME_PASS_CONTEXT", ("OUTSIDE", "UNLISTED")),
    ),
)
def test_event_v2_rejects_fully_rehashed_mapping_expired_on_source_date_before_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    origin: str,
    symbols: tuple[str, str],
) -> None:
    root = tmp_path / f"event-source-date-{origin}-{symbols[0]}"
    root.mkdir(mode=0o700)
    source_date = date(2026, 8, 27)
    raw = _artifact(source_date, symbols=symbols)
    monkeypatch.setattr(
        event_v2, "_trusted_utc_now", lambda: datetime(2026, 8, 27, 9, tzinfo=UTC)
    )
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    with acquired.lease as lease:
        mapping = _binding_with_origin(_mapping(root, lease), origin)
        with pytest.raises(ValueError, match="source-time integrity invalid"):
            event_v2.retain_current_event_notices_v2(
                root, lease, _input(raw, source_date), raw, mapping
            )
    assert not (root / ".current-event-notice-v1").exists()


@pytest.mark.parametrize(
    "interleaving",
    ("root", "archive", "archive-mode", "raw", "projection", "receipt", "marker"),
)
def test_event_v2_final_authority_interleavings_reject_before_successful_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interleaving: str
) -> None:
    root = tmp_path / f"event-final-authority-{interleaving}"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    raw = _artifact()
    monkeypatch.setattr(event_v2, "_trusted_utc_now", lambda: _KNOWN)
    original = event_v2._verify_final_archive_binding  # pyright: ignore[reportPrivateUsage]

    def replace_immediately_before_return(
        operation: object, directory: int, objects: object = ()
    ) -> None:
        archive = root / ".current-event-notice-v1"
        if interleaving == "root":
            root.rename(root.with_name(f"{root.name}-replaced"))
            root.mkdir(mode=0o700)
            root.chmod(0o700)
        elif interleaving == "archive":
            archive.rename(root / ".replaced-event-archive")
            archive.mkdir(mode=0o700)
            archive.chmod(0o700)
        elif interleaving == "archive-mode":
            archive.chmod(0o755)
        else:
            os.unlink(
                archive
                / cast(tuple[tuple[str, object, int], ...], objects)[
                    ("raw", "projection", "receipt", "marker").index(interleaving)
                ][0]
            )
        original(operation, directory, objects)  # type: ignore[arg-type]

    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    with acquired.lease as lease:
        mapping = _mapping(root, lease)
        monkeypatch.setattr(
            event_v2,
            "_verify_final_archive_binding",
            replace_immediately_before_return,
        )
        with pytest.raises(ValueError, match="archive authority invalid"):
            event_v2.retain_current_event_notices_v2(
                root, lease, _input(raw), raw, mapping
            )


def _adopted_v1_projection(
    root: Path, lease: StorageRootLease, mapping: Any, raw: bytes
) -> Any:
    projection = mapping_v2.validate_current_research_binding_v2(mapping)
    event_input = _input(raw)
    parsed = event_v1.parse_current_event_notice_artifact_v1(event_input, raw)
    assert not isinstance(parsed, event_v1.CurrentEventNoticeFailureV1)
    cohort = tuple(
        event_v1.CurrentEventCohortMemberV1(
            member.isin,
            member.exchange,
            "EQUITY",
            member.effective_symbol,
            member.valid_from,
            member.valid_through,
            member.provider_mapping_revision,
        )
        for member in projection.members
    )
    snapshot = cast(
        Any, event_v1.project_current_supplied_cohort_event_notices_v1(parsed, cohort)
    )
    retained = cast(
        Any,
        event_v1.FileCurrentEventNoticeArchiveV1(root).archive_exact(
            event_input, raw, snapshot, lease
        ),
    )
    return event_v2.project_retained_current_event_notices_v2(
        root, lease, retained, mapping
    )


@pytest.mark.parametrize(
    "interleaving",
    ("root", "archive", "archive-mode", "raw", "projection", "receipt", "marker"),
)
def test_adopted_event_v1_final_authority_interleavings_reject_before_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interleaving: str
) -> None:
    root = tmp_path / f"event-v1-final-authority-{interleaving}"
    root.mkdir(mode=0o700)
    artifact_lines = _artifact().splitlines()
    raw = b"\n".join((artifact_lines[0], artifact_lines[1], artifact_lines[3])) + b"\n"
    monkeypatch.setattr(event_v1, "_trusted_utc_now", lambda: _KNOWN)
    original = event_v2._verify_final_archive_binding  # pyright: ignore[reportPrivateUsage]

    def replace_before_adopted_return(
        operation: object, directory: int, objects: object = ()
    ) -> None:
        archive = root / ".current-event-notice-v1"
        if interleaving == "root":
            root.rename(root.with_name(f"{root.name}-replaced"))
            root.mkdir(mode=0o700)
            root.chmod(0o700)
        elif interleaving == "archive":
            archive.rename(root / ".replaced-event-archive")
            archive.mkdir(mode=0o700)
            archive.chmod(0o700)
        elif interleaving == "archive-mode":
            archive.chmod(0o755)
        else:
            os.unlink(
                archive
                / cast(tuple[tuple[str, object, int], ...], objects)[
                    ("raw", "projection", "receipt", "marker").index(interleaving)
                ][0]
            )
        original(operation, directory, objects)  # type: ignore[arg-type]

    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    with acquired.lease as lease:
        mapping = _mapping(root, lease)
        monkeypatch.setattr(
            event_v2, "_verify_final_archive_binding", replace_before_adopted_return
        )
        with pytest.raises(ValueError, match="archive authority invalid"):
            _adopted_v1_projection(root, lease, mapping, raw)


def _rehash_adopted_v1_identity(value: Any, replaced: str) -> None:
    """Rehash every V1-derived identity available from V2's redacted projection."""
    snapshot = value.snapshot_identity_sha256
    archive = value.archive_identity_sha256
    receipt = value.receipt_identity_sha256
    retained = value.retained_identity_sha256
    if replaced == "archive_identity_sha256":
        archive = "f" * 64
    receipt_core = {
        "version": "retained-current-event-notice-receipt@v1",
        "artifact_identity_sha256": value.artifact_identity_sha256,
        "snapshot_identity_sha256": snapshot,
        "archive_identity_sha256": archive,
        "runtime_code_identity_sha256": value.source_runtime_code_identity_sha256,
        "known_at": event_v2._wire(value.known_at),  # pyright: ignore[reportPrivateUsage]
        "acquisition_method": value.acquisition_method,
        "licence_policy_identity": value.licence_policy_identity,
        "source_filename": value.source_filename,
        "source_encoding": value.source_encoding,
        "source_has_bom": value.source_has_bom,
    }
    if replaced == "receipt_identity_sha256":
        receipt = "e" * 64
    else:
        receipt = event_v2._digest(receipt_core)  # pyright: ignore[reportPrivateUsage]
    if replaced == "retained_identity_sha256":
        retained = "d" * 64
    else:
        retained = event_v2._digest(  # pyright: ignore[reportPrivateUsage]
            {**receipt_core, "receipt_identity_sha256": receipt}
        )
    for name, item in (
        ("archive_identity_sha256", archive),
        ("receipt_identity_sha256", receipt),
        ("retained_identity_sha256", retained),
    ):
        object.__setattr__(value, name, item)
    preimage = {
        item.name: getattr(value, item.name)
        for item in fields(value)
        if item.name not in {"result_identity_sha256", "_seal"}
    }
    object.__setattr__(
        value,
        "result_identity_sha256",
        event_v2._digest(preimage),  # pyright: ignore[reportPrivateUsage]
    )


@pytest.mark.parametrize(
    "replaced",
    ("archive_identity_sha256", "receipt_identity_sha256", "retained_identity_sha256"),
)
def test_adopted_event_v1_rejects_fully_rehashed_available_identity_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replaced: str
) -> None:
    root = tmp_path / f"event-v1-adoption-{replaced}"
    root.mkdir(mode=0o700)
    artifact_lines = _artifact().splitlines()
    raw = b"\n".join((artifact_lines[0], artifact_lines[1], artifact_lines[3])) + b"\n"
    monkeypatch.setattr(event_v1, "_trusted_utc_now", lambda: _KNOWN)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    with acquired.lease as lease:
        adopted = _adopted_v1_projection(root, lease, _mapping(root, lease), raw)
    substituted = copy.deepcopy(adopted)
    _rehash_adopted_v1_identity(substituted, replaced)
    assert not event_v2.current_event_notice_semantics_are_valid_v2(substituted)


@pytest.mark.parametrize(
    "case",
    (
        "wrong-field-type",
        "excessive-depth",
        "excessive-nodes",
        "excessive-token",
        "excessive-string",
        "decoder-recursion",
        "future-known-at",
        "wrong-source-date",
    ),
)
def test_event_v2_stored_prefix_admission_rejects_malformed_evidence_before_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    root = tmp_path / f"event-prefix-{case}"
    root.mkdir(mode=0o700)
    raw = _artifact()
    monkeypatch.setattr(event_v2, "_trusted_utc_now", lambda: _KNOWN)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    with acquired.lease as lease:
        mapping = _mapping(root, lease)
        retained = event_v2.retain_current_event_notices_v2(
            root, lease, _input(raw), raw, mapping
        )
        archive = root / ".current-event-notice-v1"
        projection = archive / f"v2-{retained.archive_identity_sha256}.projection.json"
        for suffix in ("receipt.json", "complete.json"):
            (archive / f"v2-{retained.archive_identity_sha256}.{suffix}").unlink()
        if case == "decoder-recursion":
            malformed = b'{"known_at":' + b"[" * 1_100 + b"0" + b"]" * 1_100 + b"}"
        else:
            payload = json.loads(projection.read_bytes())
            if case == "wrong-field-type":
                payload["known_at"] = False
            elif case == "excessive-depth":
                nested: object = 0
                for _ in range(17):
                    nested = [nested]
                payload["known_at"] = nested
            elif case == "excessive-nodes":
                payload["known_at"] = [0] * 50_000
            elif case == "excessive-token":
                payload["known_at"] = int("9" * 259)
            elif case == "excessive-string":
                payload["known_at"] = "x" * 4_097
            elif case == "future-known-at":
                payload["known_at"] = "2026-08-26T09:06:00.000000Z"
            else:
                payload["known_at"] = "2026-08-25T09:00:00.000000Z"
            malformed = json.dumps(
                payload, sort_keys=True, separators=(",", ":")
            ).encode()
        projection.write_bytes(malformed)
        with pytest.raises(ValueError, match="immutable archive conflict"):
            event_v2.retain_current_event_notices_v2(
                root, lease, _input(raw), raw, mapping
            )
        assert {path.name for path in archive.iterdir()} == {
            f"v2-{retained.artifact_identity_sha256}.raw.csv",
            f"v2-{retained.archive_identity_sha256}.projection.json",
        }
