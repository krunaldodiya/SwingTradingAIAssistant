from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest

import swing_trading_ai_assistant.market_data.catalog as catalog_module
import swing_trading_ai_assistant.market_data.corporate_actions as action_module
from swing_trading_ai_assistant.market_data.catalog import (
    CatalogConflictError,
    CatalogSchemaError,
    DuckDBCatalog,
)
from swing_trading_ai_assistant.market_data.corporate_actions import (
    AdjustmentAvailabilityReportV1,
    AdjustmentAvailabilityServiceV1,
    CorporateActionAmbiguousError,
    CorporateActionCorruptError,
    CorporateActionEventV1,
    CorporateActionEvidenceStateV1,
    CorporateActionKindV1,
    CorporateActionMissingError,
    CorporateActionSnapshotMetadataV1,
    CorporateActionSnapshotStoreV1,
    CorporateActionSnapshotV1,
    CorporateActionStaleError,
    CorporateActionUnavailableError,
    UpstoxCorporateActionsClientV1,
)
from swing_trading_ai_assistant.market_data.http import HttpResponse
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

_ISIN = "INE062A01020"
_OTHER_ISIN = "INE002A01018"
_RETRIEVED = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
_TOKEN = "private-upstox-token"  # noqa: S105 - deterministic fake test credential


class RecordingTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        self.calls.append((url, dict(headers)))
        return self.response


def _details(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"value": value, "name": name} for name, value in pairs]


def _provider_event(kind: str) -> dict[str, object]:
    suffix = kind.lower()
    common: dict[str, object] = {
        "event_details": _details(
            ("Record date", "12 Aug 2026"),
            ("Announcement date", "01 Aug 2026"),
            ("Details", f"{suffix} observation"),
        ),
        "ratio": None,
        "amount": None,
        "expiry_date": "11 Aug 2026",
        "name": kind,
    }
    if kind == "Dividend":
        common["amount"] = 5.5000
        cast_details = common["event_details"]
        assert isinstance(cast_details, list)
        cast_details.extend(
            [
                {"value": "Final", "name": "Dividend type"},
                {"value": "5.5", "name": "Amount"},
                {"value": "11 Aug 2026", "name": "Ex dividend date"},
            ]
        )
    else:
        common["ratio"] = {
            "Bonus": "1:1",
            "Split": "2:1",
            "Rights": "1:5",
        }[kind]
        cast_details = common["event_details"]
        assert isinstance(cast_details, list)
        cast_details.extend(
            [
                {"value": str(common["ratio"]), "name": "Ratio"},
                {
                    "value": "11 Aug 2026",
                    "name": f"Ex {kind.lower()} date",
                },
            ]
        )
    return common


def _provider_payload(*kinds: str) -> bytes:
    return json.dumps(
        {"data": [_provider_event(kind) for kind in kinds], "status": "success"},
        separators=(",", ":"),
    ).encode()


def _client(
    payload: bytes | None = None,
    *,
    status: int = 200,
    clock: datetime = _RETRIEVED,
) -> tuple[UpstoxCorporateActionsClientV1, RecordingTransport]:
    transport = RecordingTransport(
        HttpResponse(
            status,
            payload
            if payload is not None
            else _provider_payload("Dividend", "Bonus", "Split", "Rights"),
        )
    )
    return UpstoxCorporateActionsClientV1(transport, clock=lambda: clock), transport


def _snapshot(
    *kinds: str, retrieved_at: datetime = _RETRIEVED
) -> CorporateActionSnapshotV1:
    client, _ = _client(
        _provider_payload(*(kinds or ("Dividend", "Bonus", "Split", "Rights"))),
        clock=retrieved_at,
    )
    return client.fetch(_ISIN, _TOKEN)


def _leased_store(root: Path):
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    lease = acquired.lease
    catalog = DuckDBCatalog(root, lease=lease)
    catalog.__enter__()
    return lease, catalog, CorporateActionSnapshotStoreV1(root, lease, catalog)


def test_upstox_client_uses_the_official_isin_endpoint_and_all_frozen_types() -> None:
    client, transport = _client()

    snapshot = client.fetch(_ISIN, _TOKEN)

    assert transport.calls == [
        (
            f"https://api.upstox.com/v2/fundamentals/{_ISIN}/corporate-actions",
            {"Accept": "application/json", "Authorization": f"Bearer {_TOKEN}"},
        )
    ]
    assert {event.kind for event in snapshot.events} == set(CorporateActionKindV1)
    dividend = next(
        event
        for event in snapshot.events
        if event.kind is CorporateActionKindV1.DIVIDEND
    )
    assert dividend.cash_amount_inr == "5.5"
    assert dividend.ratio_numerator is None
    assert snapshot.source == "upstox-fundamentals-v2"
    assert snapshot.source_release == "corporate-actions-v1"
    assert snapshot.retrieved_at == _RETRIEVED
    assert _TOKEN.encode() not in snapshot.canonical_json_bytes()


def test_provider_json_object_order_is_irrelevant_but_duplicates_fail_closed() -> None:
    snapshot = _snapshot("Dividend")
    assert snapshot.events[0].kind is CorporateActionKindV1.DIVIDEND

    duplicate = b'{"status":"success","status":"success","data":[]}'
    client, _ = _client(duplicate)
    with pytest.raises(CorporateActionCorruptError, match="response corrupt"):
        client.fetch(_ISIN, _TOKEN)


@pytest.mark.parametrize(
    "payload",
    (
        b'{"status":"success","data":[],"extra":true}',
        b'{"status":"failure","data":[]}',
        b'{"status":"success","data":NaN}',
        json.dumps(
            {"status": "success", "data": [_provider_event("Dividend")] * 1001}
        ).encode(),
    ),
)
def test_provider_envelope_bounds_and_unknown_fields_fail_closed(
    payload: bytes,
) -> None:
    client, _ = _client(payload)
    with pytest.raises(CorporateActionCorruptError):
        client.fetch(_ISIN, _TOKEN)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        (lambda event: event.update(name="Merger"), CorporateActionCorruptError),
        (lambda event: event.update(amount=0), CorporateActionCorruptError),
        (lambda event: event.update(ratio="0:1"), CorporateActionCorruptError),
        (
            lambda event: event["event_details"].append(  # type: ignore[union-attr]
                {"name": "Secret provider fact", "value": "x"}
            ),
            CorporateActionCorruptError,
        ),
    ),
)
def test_unknown_or_invalid_provider_event_facts_fail_closed(
    mutation, expected
) -> None:
    event = _provider_event("Bonus")
    mutation(event)
    payload = json.dumps({"status": "success", "data": [event]}).encode()
    client, _ = _client(payload)
    with pytest.raises(expected):
        client.fetch(_ISIN, _TOKEN)


@pytest.mark.parametrize(
    "mutation",
    (
        lambda event: event.update(amount="5.5"),
        lambda event: event["event_details"].__setitem__(  # type: ignore[index]
            5, {"name": "Ex dividend date", "value": "not a date"}
        ),
        lambda event: event["event_details"].__setitem__(  # type: ignore[index]
            4, {"name": "Amount", "value": "6"}
        ),
        lambda event: event["event_details"].__setitem__(  # type: ignore[index]
            5, {"name": "Ex dividend date", "value": "12 Aug 2026"}
        ),
        lambda event: event["event_details"].append(  # type: ignore[union-attr]
            {"name": "Ex split date", "value": "11 Aug 2026"}
        ),
    ),
)
def test_dividend_provider_detail_types_dates_and_redundancy_fail_closed(
    mutation,
) -> None:
    event = _provider_event("Dividend")
    mutation(event)
    client, _ = _client(json.dumps({"status": "success", "data": [event]}).encode())
    with pytest.raises(CorporateActionCorruptError):
        client.fetch(_ISIN, _TOKEN)


@pytest.mark.parametrize(
    "mutation",
    (
        lambda event: event["event_details"].__setitem__(  # type: ignore[index]
            3, {"name": "Ratio", "value": "2:1"}
        ),
        lambda event: event["event_details"].__setitem__(  # type: ignore[index]
            4, {"name": "Ex bonus date", "value": "not a date"}
        ),
        lambda event: event["event_details"].append(  # type: ignore[union-attr]
            {"name": "Amount", "value": "5.5"}
        ),
    ),
)
def test_ratio_provider_details_reconcile_and_reject_cross_event_labels(
    mutation,
) -> None:
    event = _provider_event("Bonus")
    mutation(event)
    client, _ = _client(json.dumps({"status": "success", "data": [event]}).encode())
    with pytest.raises(CorporateActionCorruptError):
        client.fetch(_ISIN, _TOKEN)


def test_split_numeric_details_are_strict_positive_decimals() -> None:
    event = _provider_event("Split")
    details = event["event_details"]
    assert isinstance(details, list)
    details.extend(
        [
            {"name": "Old face value", "value": "10"},
            {"name": "New face value", "value": "5"},
        ]
    )
    client, _ = _client(json.dumps({"status": "success", "data": [event]}).encode())
    assert client.fetch(_ISIN, _TOKEN).events[0].kind is CorporateActionKindV1.SPLIT

    details[-1] = {"name": "New face value", "value": "0"}
    client, _ = _client(json.dumps({"status": "success", "data": [event]}).encode())
    with pytest.raises(CorporateActionCorruptError):
        client.fetch(_ISIN, _TOKEN)


def test_provider_failures_are_sanitized_and_never_expose_credentials() -> None:
    client, _ = _client(b'{"secret":"' + _TOKEN.encode() + b'"}', status=503)
    with pytest.raises(CorporateActionUnavailableError) as caught:
        client.fetch(_ISIN, _TOKEN)
    assert _TOKEN not in str(caught.value)

    with pytest.raises(CorporateActionUnavailableError):
        client.fetch(_ISIN, "token with spaces")
    with pytest.raises(CorporateActionUnavailableError):
        client.fetch("NSE_EQ|SBIN", _TOKEN)


def test_future_announcement_and_invalid_clock_fail_at_the_provider_boundary() -> None:
    event = _provider_event("Dividend")
    event["event_details"] = _details(("Announcement date", "11 Aug 2026"))
    payload = json.dumps({"status": "success", "data": [event]}).encode()
    client, _ = _client(payload, clock=datetime(2026, 8, 10, tzinfo=UTC))
    with pytest.raises(CorporateActionCorruptError):
        client.fetch(_ISIN, _TOKEN)

    transport = RecordingTransport(HttpResponse(200, _provider_payload("Dividend")))
    invalid_clock = UpstoxCorporateActionsClientV1(
        transport, clock=lambda: datetime(2026, 8, 10)
    )
    with pytest.raises(CorporateActionUnavailableError):
        invalid_clock.fetch(_ISIN, _TOKEN)


def test_snapshot_canonical_round_trip_and_mutation_rejection() -> None:
    snapshot = _snapshot()
    payload = snapshot.canonical_json_bytes()
    assert CorporateActionSnapshotV1.from_canonical_json_bytes(payload) == snapshot

    with pytest.raises(CorporateActionCorruptError):
        CorporateActionSnapshotV1.from_canonical_json_bytes(payload + b" ")
    with pytest.raises(CorporateActionCorruptError):
        CorporateActionSnapshotV1.from_canonical_json_bytes(
            payload.replace(b'"schema_version":1', b'"schema_version":2')
        )
    with pytest.raises(CorporateActionCorruptError):
        CorporateActionSnapshotV1.from_canonical_json_bytes(
            b'{"events":[],"events":[],"isin":"' + _ISIN.encode() + b'"}'
        )


def test_event_and_report_contracts_reject_inconsistent_states() -> None:
    event = _snapshot("Dividend").events[0]
    with pytest.raises(ValueError):
        replace(event, event_digest_sha256="0" * 64)
    with pytest.raises(ValueError):
        replace(event, ratio_numerator=1)
    with pytest.raises(ValueError):
        CorporateActionEventV1(
            "0" * 64,
            CorporateActionKindV1.SPLIT,
            datetime(2026, 8, 1, tzinfo=UTC),
            date(2026, 8, 11),
            None,
            None,
            0,
            1,
        )
    with pytest.raises(ValueError):
        AdjustmentAvailabilityReportV1(
            1,
            _ISIN,
            _RETRIEVED,
            "adjusted",
            "available",
            "unsupported",
            None,
            CorporateActionEvidenceStateV1.AVAILABLE,
            None,
            None,
            None,
            None,
            (),
        )


def test_store_retains_idempotently_resolves_by_cutoff_and_keeps_raw_data(
    tmp_path,
) -> None:
    raw = tmp_path / "raw-month.parquet"
    raw.write_bytes(b"immutable raw candle bytes")
    raw.chmod(0o400)
    before = hashlib.sha256(raw.read_bytes()).hexdigest()
    lease, catalog, store = _leased_store(tmp_path)
    try:
        snapshot = _snapshot()
        first = store.retain(snapshot)
        second = store.retain(snapshot)
        assert second == first
        assert catalog.connection.execute(
            "SELECT count(*) FROM corporate_action_snapshots"
        ).fetchone() == (1,)
        metadata, resolved = store.resolve(isin=_ISIN, knowledge_cutoff=_RETRIEVED)
        assert metadata == first
        assert resolved == snapshot
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == before
        assert (raw.stat().st_mode & 0o777) == 0o400
    finally:
        catalog.close()
        lease.close()


@pytest.mark.parametrize(
    "error_type",
    (AssertionError, KeyError, RuntimeError, Exception, TypeError, ValueError),
)
def test_availability_preserves_unknown_retained_catalog_decoder_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_type: type[Exception]
) -> None:
    lease, catalog, store = _leased_store(tmp_path)
    primary = error_type("catalog decoder implementation fault")
    try:
        store.retain(_snapshot("Dividend"))

        def fail_metadata(_row: object) -> object:
            raise primary

        with monkeypatch.context() as scoped:
            scoped.setattr(
                catalog_module, "_corporate_action_metadata_from_row", fail_metadata
            )
            with pytest.raises(error_type) as raised:
                AdjustmentAvailabilityServiceV1(store).inspect(
                    isin=_ISIN, knowledge_cutoff=_RETRIEVED
                )
            assert raised.value is primary
    finally:
        catalog.close()
        lease.close()


def test_cutoff_states_are_missing_stale_available_and_ambiguous(tmp_path) -> None:
    lease, catalog, store = _leased_store(tmp_path)
    try:
        service = AdjustmentAvailabilityServiceV1(store)
        missing = service.inspect(isin=_ISIN, knowledge_cutoff=_RETRIEVED)
        assert missing.evidence_state is CorporateActionEvidenceStateV1.MISSING
        assert missing.price_state == "raw"
        assert missing.adjusted_state == "unsupported"
        assert missing.symbol_change_state == "unsupported"
        assert missing.calculation_version is None
        with pytest.raises(ValueError):
            replace(missing, symbol_change_state="available")

        store.retain(_snapshot("Dividend"))
        stale_cutoff = datetime(2026, 8, 9, tzinfo=UTC)
        stale = service.inspect(isin=_ISIN, knowledge_cutoff=stale_cutoff)
        assert stale.evidence_state is CorporateActionEvidenceStateV1.STALE
        with pytest.raises(CorporateActionStaleError):
            store.resolve(isin=_ISIN, knowledge_cutoff=stale_cutoff)
        with pytest.raises(CorporateActionMissingError):
            store.resolve(isin=_OTHER_ISIN, knowledge_cutoff=_RETRIEVED)

        available = service.inspect(isin=_ISIN, knowledge_cutoff=_RETRIEVED)
        assert available.evidence_state is CorporateActionEvidenceStateV1.AVAILABLE
        assert available.source == "upstox-fundamentals-v2"
        assert len(available.visible_events) == 1

        store.retain(_snapshot("Bonus"))
        ambiguous = service.inspect(isin=_ISIN, knowledge_cutoff=_RETRIEVED)
        assert ambiguous.evidence_state is CorporateActionEvidenceStateV1.AMBIGUOUS
        assert ambiguous.source is None
        with pytest.raises(CorporateActionAmbiguousError):
            store.resolve(isin=_ISIN, knowledge_cutoff=_RETRIEVED)
    finally:
        catalog.close()
        lease.close()


def test_date_only_announcement_is_hidden_until_next_ist_midnight(tmp_path) -> None:
    retrieved_at = datetime(2026, 8, 1, 6, 30, tzinfo=UTC)
    last_same_day_microsecond = datetime(2026, 8, 1, 18, 29, 59, 999_999, tzinfo=UTC)
    next_day_boundary_utc = datetime(2026, 8, 1, 18, 30, tzinfo=UTC)
    next_day_ist_midnight = datetime(
        2026, 8, 2, tzinfo=timezone(timedelta(hours=5, minutes=30))
    )
    snapshot = _snapshot("Dividend", retrieved_at=retrieved_at)
    canonical_bytes = snapshot.canonical_json_bytes()
    canonical_digest = hashlib.sha256(canonical_bytes).hexdigest()
    lease, catalog, store = _leased_store(tmp_path)
    try:
        metadata = store.retain(snapshot)
        service = AdjustmentAvailabilityServiceV1(store)

        hidden = service.inspect(isin=_ISIN, knowledge_cutoff=last_same_day_microsecond)
        visible_utc = service.inspect(
            isin=_ISIN, knowledge_cutoff=next_day_boundary_utc
        )
        visible_ist = service.inspect(
            isin=_ISIN, knowledge_cutoff=next_day_ist_midnight
        )

        assert hidden.evidence_state is CorporateActionEvidenceStateV1.AVAILABLE
        assert hidden.visible_events == ()
        assert (
            visible_utc.visible_events == visible_ist.visible_events == snapshot.events
        )
        assert (
            hidden.snapshot_sha256
            == visible_utc.snapshot_sha256
            == visible_ist.snapshot_sha256
            == canonical_digest
        )
        _, resolved = store.resolve(isin=_ISIN, knowledge_cutoff=next_day_ist_midnight)
        assert resolved.canonical_json_bytes() == canonical_bytes
        assert metadata.snapshot_sha256 == canonical_digest
    finally:
        catalog.close()
        lease.close()


def test_date_only_visibility_is_enforced_by_report_invariant() -> None:
    retrieved_at = datetime(2026, 8, 1, 6, 30, tzinfo=UTC)
    last_same_day_microsecond = datetime(2026, 8, 1, 18, 29, 59, 999_999, tzinfo=UTC)
    next_day_ist_midnight = datetime(2026, 8, 1, 18, 30, tzinfo=UTC)
    event = _snapshot("Dividend", retrieved_at=retrieved_at).events[0]

    def report(cutoff: datetime) -> AdjustmentAvailabilityReportV1:
        return AdjustmentAvailabilityReportV1(
            1,
            _ISIN,
            cutoff,
            "raw",
            "unsupported",
            "unsupported",
            None,
            CorporateActionEvidenceStateV1.AVAILABLE,
            "upstox-fundamentals-v2",
            "corporate-actions-v1",
            retrieved_at,
            "0" * 64,
            (event,),
        )

    with pytest.raises(ValueError, match="invalid adjustment availability report"):
        report(last_same_day_microsecond)
    assert report(next_day_ist_midnight).visible_events == (event,)


def test_date_only_visibility_does_not_relax_retrieval_cutoff(tmp_path) -> None:
    visibility_boundary = datetime(2026, 8, 1, 18, 30, tzinfo=UTC)
    retrieved_at = datetime(2026, 8, 1, 18, 30, 0, 1, tzinfo=UTC)
    lease, catalog, store = _leased_store(tmp_path)
    try:
        store.retain(_snapshot("Dividend", retrieved_at=retrieved_at))
        service = AdjustmentAvailabilityServiceV1(store)

        stale = service.inspect(isin=_ISIN, knowledge_cutoff=visibility_boundary)
        available = service.inspect(isin=_ISIN, knowledge_cutoff=retrieved_at)

        assert stale.evidence_state is CorporateActionEvidenceStateV1.STALE
        assert stale.visible_events == ()
        assert available.evidence_state is CorporateActionEvidenceStateV1.AVAILABLE
        assert len(available.visible_events) == 1
    finally:
        catalog.close()
        lease.close()


def test_changed_or_unsafe_retained_object_is_corrupt_not_missing(tmp_path) -> None:
    lease, catalog, store = _leased_store(tmp_path)
    try:
        metadata = store.retain(_snapshot("Dividend"))
        final = tmp_path / metadata.relative_object_path
        final.chmod(0o600)
        with pytest.raises(CorporateActionCorruptError):
            store.resolve(isin=_ISIN, knowledge_cutoff=_RETRIEVED)
        report = AdjustmentAvailabilityServiceV1(store).inspect(
            isin=_ISIN, knowledge_cutoff=_RETRIEVED
        )
        assert report.evidence_state is CorporateActionEvidenceStateV1.CORRUPT
        assert report.snapshot_sha256 is None
    finally:
        catalog.close()
        lease.close()


def test_catalog_v5_metadata_api_is_exact_and_bounded(tmp_path) -> None:
    lease, catalog, store = _leased_store(tmp_path)
    try:
        metadata = store.retain(_snapshot("Dividend"))
        assert catalog.has_corporate_action_snapshots(isin=_ISIN)
        assert catalog.latest_corporate_action_snapshots(
            isin=_ISIN, knowledge_cutoff=_RETRIEVED
        ) == (metadata,)
        assert not catalog.save_corporate_action_snapshot(metadata)
        with pytest.raises(ValueError):
            replace(metadata, source_release="conflicting-v2")
        with pytest.raises(CatalogConflictError):
            catalog.latest_corporate_action_snapshots(
                isin=_ISIN, knowledge_cutoff=datetime(2026, 8, 10)
            )
        with pytest.raises(CatalogConflictError):
            catalog.has_corporate_action_snapshots(isin=object())  # type: ignore[arg-type]
    finally:
        catalog.close()
        lease.close()


def test_catalog_v5_write_remove_and_row_failure_branches(
    tmp_path, monkeypatch
) -> None:
    lease, catalog, store = _leased_store(tmp_path)
    try:
        metadata = store.retain(_snapshot("Dividend"))
        catalog.remove_corporate_action_snapshot_exact(metadata)
        catalog.remove_corporate_action_snapshot_exact(metadata)
        assert catalog.save_corporate_action_snapshot(metadata)
        with pytest.raises(CatalogConflictError):
            catalog.save_corporate_action_snapshot(object())  # type: ignore[arg-type]
        with pytest.raises(CatalogConflictError):
            catalog.save_corporate_action_snapshot(
                metadata,
                precommit_validator=object(),  # type: ignore[arg-type]
            )
        with pytest.raises(CatalogConflictError):
            catalog.remove_corporate_action_snapshot_exact(object())  # type: ignore[arg-type]

        catalog.connection.execute(
            "UPDATE corporate_action_snapshots SET event_count = 0"
        )
        with pytest.raises(CatalogConflictError):
            catalog.remove_corporate_action_snapshot_exact(metadata)
        catalog.connection.execute(
            "UPDATE corporate_action_snapshots SET event_count = ?",
            (metadata.event_count,),
        )

        original_converter = catalog_module._corporate_action_metadata_from_row

        def catalog_failure(_row):
            raise CatalogConflictError("typed row failure")

        monkeypatch.setattr(
            catalog_module, "_corporate_action_metadata_from_row", catalog_failure
        )
        with pytest.raises(CatalogConflictError, match="typed row failure"):
            catalog.latest_corporate_action_snapshots(
                isin=_ISIN, knowledge_cutoff=_RETRIEVED
            )

        failure = RuntimeError("untrusted row failure")

        def unexpected_failure(_row: object) -> None:
            raise failure

        monkeypatch.setattr(
            catalog_module, "_corporate_action_metadata_from_row", unexpected_failure
        )
        with pytest.raises(RuntimeError) as raised:
            catalog.latest_corporate_action_snapshots(
                isin=_ISIN, knowledge_cutoff=_RETRIEVED
            )
        assert raised.value is failure
        monkeypatch.setattr(
            catalog_module,
            "_corporate_action_metadata_from_row",
            original_converter,
        )

        catalog.close()
        with pytest.raises(catalog_module.CatalogPersistenceError):
            catalog.has_corporate_action_snapshots(isin=_ISIN)
    finally:
        catalog.close()
        lease.close()


def test_v4_to_v5_migration_is_atomic_and_read_only_never_migrates(tmp_path) -> None:
    with DuckDBCatalog(tmp_path) as current:
        current.connection.execute("DROP TABLE corporate_action_snapshots")
        current.connection.execute("DROP TABLE provisional_partitions")
        current.connection.execute(catalog_module._PROVISIONAL_SCHEMA_SQL)
        current.connection.execute("DELETE FROM schema_migrations WHERE version >= 5")

    broken = DuckDBCatalog(tmp_path)
    failure = RuntimeError()
    broken._after_corporate_action_migration = lambda: (_ for _ in ()).throw(  # type: ignore[method-assign]
        failure
    )
    with pytest.raises(RuntimeError) as raised:
        broken.__enter__()
    assert raised.value is failure
    connection = duckdb.connect(str(tmp_path / "catalog.duckdb"))
    try:
        assert "corporate_action_snapshots" not in {
            row[0] for row in connection.execute("SHOW TABLES").fetchall()
        }
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,)]
    finally:
        connection.close()

    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    acquired.lease.close()
    read = StorageRootLease.try_admit_read_existing(tmp_path)
    assert read.lease is not None
    with read.lease, pytest.raises(CatalogSchemaError):
        DuckDBCatalog(tmp_path, read_only=True, lease=read.lease).__enter__()
    connection = duckdb.connect(str(tmp_path / "catalog.duckdb"))
    try:
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,)]
    finally:
        connection.close()

    with DuckDBCatalog(tmp_path) as upgraded:
        assert upgraded.connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,), (5,), (6,)]

    v3_root = tmp_path / "v3-catalog"
    v3_root.mkdir(mode=0o700)
    with DuckDBCatalog(v3_root) as current:
        current.connection.execute("DROP TABLE corporate_action_snapshots")
        current.connection.execute("DROP TABLE provisional_partitions")
        current.connection.execute("DELETE FROM schema_migrations WHERE version >= 4")
    with DuckDBCatalog(v3_root) as upgraded:
        assert upgraded.connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,), (5,), (6,)]


def test_metadata_reconstructs_and_rejects_wrong_content_path() -> None:
    snapshot = _snapshot("Dividend")
    payload = snapshot.canonical_json_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    metadata = CorporateActionSnapshotMetadataV1(
        1,
        _ISIN,
        snapshot.source,
        snapshot.source_release,
        snapshot.retrieved_at,
        digest,
        len(payload),
        1,
        f"corporate_action_snapshots/isin={_ISIN}/sha256={digest}/snapshot.json",
    )
    assert replace(metadata) == metadata
    with pytest.raises(ValueError):
        replace(metadata, relative_object_path="snapshot.json")


def test_only_the_frozen_upstox_adapter_identity_is_constructible_or_retained(
    tmp_path,
) -> None:
    snapshot = _snapshot("Dividend")
    with pytest.raises(ValueError):
        replace(snapshot, source="unsupported-feed")
    metadata = CorporateActionSnapshotMetadataV1(
        1,
        _ISIN,
        snapshot.source,
        snapshot.source_release,
        snapshot.retrieved_at,
        hashlib.sha256(snapshot.canonical_json_bytes()).hexdigest(),
        len(snapshot.canonical_json_bytes()),
        len(snapshot.events),
        "corporate_action_snapshots/isin="
        + _ISIN
        + "/sha256="
        + hashlib.sha256(snapshot.canonical_json_bytes()).hexdigest()
        + "/snapshot.json",
    )
    with pytest.raises(ValueError):
        replace(metadata, source_release="forged-v2")

    lease, catalog, store = _leased_store(tmp_path)
    try:
        forged = object.__new__(CorporateActionSnapshotV1)
        for name, value in {
            "schema_version": 1,
            "isin": _ISIN,
            "source": "unsupported-feed",
            "source_release": snapshot.source_release,
            "retrieved_at": _RETRIEVED,
            "events": snapshot.events,
        }.items():
            object.__setattr__(forged, name, value)
        with pytest.raises(CorporateActionCorruptError):
            store.retain(forged)
        assert not (tmp_path / "corporate_action_snapshots").exists()
        assert catalog.connection.execute(
            "SELECT count(*) FROM corporate_action_snapshots"
        ).fetchone() == (0,)
    finally:
        catalog.close()
        lease.close()


def test_forged_catalog_identity_fails_before_replay_filesystem_access(
    tmp_path, monkeypatch
) -> None:
    lease, catalog, store = _leased_store(tmp_path)
    try:
        metadata = store.retain(_snapshot("Dividend"))
        forged = object.__new__(CorporateActionSnapshotMetadataV1)
        for name in CorporateActionSnapshotMetadataV1.__dataclass_fields__:
            object.__setattr__(forged, name, getattr(metadata, name))
        object.__setattr__(forged, "source", "unsupported-feed")
        monkeypatch.setattr(
            catalog,
            "latest_corporate_action_snapshots",
            lambda **_kwargs: (forged,),
        )
        monkeypatch.setattr(
            action_module,
            "_open_action_object",
            lambda *_args: pytest.fail("forged metadata reached filesystem replay"),
        )
        with pytest.raises(CorporateActionCorruptError):
            store.resolve(isin=_ISIN, knowledge_cutoff=_RETRIEVED)

        monkeypatch.setattr(
            catalog,
            "latest_corporate_action_snapshots",
            lambda **_kwargs: (object(),),
        )
        with pytest.raises(CorporateActionCorruptError):
            store.resolve(isin=_ISIN, knowledge_cutoff=_RETRIEVED)
    finally:
        catalog.close()
        lease.close()


def test_catalog_revalidates_mutated_corporate_action_metadata(tmp_path) -> None:
    lease, catalog, store = _leased_store(tmp_path)
    try:
        metadata = store.retain(_snapshot("Dividend"))
        forged = replace(metadata)
        object.__setattr__(forged, "source", "unsupported-feed")
        with pytest.raises(CatalogConflictError):
            catalog.save_corporate_action_snapshot(forged)
        with pytest.raises(CatalogConflictError):
            catalog.remove_corporate_action_snapshot_exact(forged)
    finally:
        catalog.close()
        lease.close()


def test_json_depth_and_response_byte_ceiling_are_enforced() -> None:
    nested: object = []
    for _ in range(action_module.MAX_CORPORATE_ACTION_JSON_DEPTH_V1 + 2):
        nested = [nested]
    client, _ = _client(json.dumps({"status": "success", "data": nested}).encode())
    with pytest.raises(CorporateActionCorruptError):
        client.fetch(_ISIN, _TOKEN)

    client, _ = _client(
        b" " * (action_module.MAX_CORPORATE_ACTION_RESPONSE_BYTES_V1 + 1)
    )
    with pytest.raises(CorporateActionCorruptError):
        client.fetch(_ISIN, _TOKEN)


def test_malformed_event_shapes_dates_details_and_amounts_fail_closed() -> None:
    invalid_events: list[dict[str, object]] = []
    missing_key = _provider_event("Dividend")
    missing_key.pop("ratio")
    invalid_events.append(missing_key)
    wrong_types = _provider_event("Dividend")
    wrong_types["name"] = 7
    invalid_events.append(wrong_types)
    dividend_ratio = _provider_event("Dividend")
    dividend_ratio["ratio"] = "1:1"
    invalid_events.append(dividend_ratio)
    zero_dividend = _provider_event("Dividend")
    zero_dividend["amount"] = 0
    invalid_events.append(zero_dividend)
    list_dividend = _provider_event("Dividend")
    list_dividend["amount"] = []
    invalid_events.append(list_dividend)
    too_many_details = _provider_event("Dividend")
    too_many_details["event_details"] = _details(
        *((f"Detail {index}", "x") for index in range(33))
    )
    invalid_events.append(too_many_details)
    invalid_detail = _provider_event("Dividend")
    invalid_detail["event_details"] = ["not-an-object"]
    invalid_events.append(invalid_detail)
    duplicate_detail = _provider_event("Dividend")
    duplicate_detail["event_details"] = _details(
        ("Announcement date", "01 Aug 2026"),
        ("Announcement date", "01 Aug 2026"),
    )
    invalid_events.append(duplicate_detail)
    non_text_date = _provider_event("Dividend")
    non_text_date["expiry_date"] = 20260811
    invalid_events.append(non_text_date)

    for event in invalid_events:
        client, _ = _client(json.dumps({"status": "success", "data": [event]}).encode())
        with pytest.raises(CorporateActionCorruptError):
            client.fetch(_ISIN, _TOKEN)

    duplicate_event = _provider_event("Dividend")
    client, _ = _client(
        json.dumps(
            {"status": "success", "data": [duplicate_event, duplicate_event]}
        ).encode()
    )
    with pytest.raises(CorporateActionCorruptError):
        client.fetch(_ISIN, _TOKEN)


def test_canonical_parser_rejects_wrong_shapes_and_scalar_types() -> None:
    payload = _snapshot("Dividend").canonical_json_bytes()
    decoded = json.loads(payload)
    extra = dict(decoded)
    extra["extra"] = True
    wrong_events = dict(decoded)
    wrong_events["events"] = {}
    wrong_event = dict(decoded)
    wrong_event["events"] = [{"kind": "DIVIDEND"}]
    wrong_timestamp = dict(decoded)
    wrong_timestamp["retrieved_at"] = 20260810

    for value in (extra, wrong_events, wrong_event, wrong_timestamp):
        hostile = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
        with pytest.raises(CorporateActionCorruptError):
            CorporateActionSnapshotV1.from_canonical_json_bytes(hostile)
    with pytest.raises(CorporateActionCorruptError):
        CorporateActionSnapshotV1.from_canonical_json_bytes(b"")
    with pytest.raises(CorporateActionCorruptError):
        CorporateActionSnapshotV1.from_canonical_json_bytes("not-bytes")  # type: ignore[arg-type]


def test_constructor_and_public_dtos_reject_bypassed_values() -> None:
    with pytest.raises(ValueError):
        UpstoxCorporateActionsClientV1(
            RecordingTransport(HttpResponse(200, b"{}")),
            clock=None,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError):
        CorporateActionSnapshotMetadataV1(
            True,
            _ISIN,
            "upstox-fundamentals-v2",
            "corporate-actions-v1",
            _RETRIEVED,
            "0" * 64,
            1,
            0,
            f"corporate_action_snapshots/isin={_ISIN}/sha256={'0' * 64}/snapshot.json",
        )

    event = _snapshot("Dividend").events[0]
    with pytest.raises(ValueError):
        replace(event, effective_date=date(2026, 7, 31))
    with pytest.raises(ValueError):
        replace(event, record_date=date(2026, 8, 1))
    with pytest.raises(ValueError):
        AdjustmentAvailabilityReportV1(
            1,
            _ISIN,
            datetime(2026, 8, 9, tzinfo=UTC),
            "raw",
            "unsupported",
            "unsupported",
            None,
            CorporateActionEvidenceStateV1.AVAILABLE,
            "upstox-fundamentals-v2",
            "corporate-actions-v1",
            _RETRIEVED,
            "0" * 64,
            (event,),
        )


def test_post_catalog_revalidation_compensates_the_exact_insert(
    tmp_path, monkeypatch
) -> None:
    lease, catalog, store = _leased_store(tmp_path)
    try:
        original_save = catalog.save_corporate_action_snapshot

        def save_then_make_unsafe(metadata, *, precommit_validator=None):
            inserted = original_save(metadata, precommit_validator=precommit_validator)
            (tmp_path / metadata.relative_object_path).chmod(0o600)
            return inserted

        monkeypatch.setattr(
            catalog, "save_corporate_action_snapshot", save_then_make_unsafe
        )
        with pytest.raises(CorporateActionCorruptError):
            store.retain(_snapshot("Dividend"))
        assert catalog.connection.execute(
            "SELECT count(*) FROM corporate_action_snapshots"
        ).fetchone() == (0,)
    finally:
        catalog.close()
        lease.close()


def test_store_detects_directory_replacement_after_a_valid_read(
    tmp_path, monkeypatch
) -> None:
    lease, catalog, store = _leased_store(tmp_path)
    try:
        metadata = store.retain(_snapshot("Dividend"))
        digest_dir = (tmp_path / metadata.relative_object_path).parent
        displaced = digest_dir.with_name(f"{digest_dir.name}.displaced")
        original_read = action_module.read_bounded_storage_object

        def read_then_replace(*args, **kwargs):
            payload = original_read(*args, **kwargs)
            digest_dir.rename(displaced)
            digest_dir.mkdir(mode=0o700)
            return payload

        monkeypatch.setattr(
            action_module, "read_bounded_storage_object", read_then_replace
        )
        with pytest.raises(CorporateActionCorruptError):
            store.resolve(isin=_ISIN, knowledge_cutoff=_RETRIEVED)
    finally:
        catalog.close()
        lease.close()


def test_retain_detects_byte_mismatch_and_preserves_typed_errors(
    tmp_path, monkeypatch
) -> None:
    lease, catalog, store = _leased_store(tmp_path)
    try:
        monkeypatch.setattr(
            action_module,
            "read_bounded_storage_object",
            lambda *_args, **_kwargs: b"wrong-bytes",
        )
        with pytest.raises(CorporateActionCorruptError):
            store.retain(_snapshot("Dividend"))

        monkeypatch.setattr(
            action_module,
            "publish_exact_storage_object",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                CorporateActionCorruptError("typed failure")
            ),
        )
        with pytest.raises(CorporateActionCorruptError, match="typed failure"):
            store.retain(_snapshot("Bonus"))
    finally:
        catalog.close()
        lease.close()


def test_resolve_rejects_catalog_metadata_that_no_longer_matches_object(
    tmp_path,
) -> None:
    lease, catalog, store = _leased_store(tmp_path)
    try:
        metadata = store.retain(_snapshot("Dividend"))
        catalog.connection.execute(
            "UPDATE corporate_action_snapshots SET event_count = 0 "
            "WHERE snapshot_sha256 = ?",
            (metadata.snapshot_sha256,),
        )
        with pytest.raises(CorporateActionCorruptError):
            store.resolve(isin=_ISIN, knowledge_cutoff=_RETRIEVED)
    finally:
        catalog.close()
        lease.close()


@pytest.mark.parametrize(
    "error_type", (AssertionError, KeyError, RuntimeError, TypeError, ValueError)
)
def test_store_propagates_unknown_lower_catalog_decoder_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_type: type[Exception]
) -> None:
    lease, catalog, store = _leased_store(tmp_path)
    failure = error_type("catalog decoder implementation fault")
    try:
        store.retain(_snapshot("Dividend"))

        def fail(_row: object) -> None:
            raise failure

        monkeypatch.setattr(catalog_module, "_corporate_action_metadata_from_row", fail)
        with pytest.raises(error_type) as raised:
            store.resolve(isin=_ISIN, knowledge_cutoff=_RETRIEVED)
        assert raised.value is failure
    finally:
        catalog.close()
        lease.close()


@pytest.mark.parametrize("operation", ("retain", "resolve"))
def test_store_preserves_unknown_primary_over_object_cleanup_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    lease, catalog, store = _leased_store(tmp_path)
    primary = TypeError("primary implementation fault")
    cleanup = RuntimeError("cleanup implementation fault")
    descriptors: set[int] = set()
    original_open = action_module._open_action_object
    original_close = action_module.os.close
    try:
        if operation == "resolve":
            store.retain(_snapshot("Dividend"))

        def open_action(*args: object, **kwargs: object) -> int:
            descriptor = original_open(*args, **kwargs)
            descriptors.add(descriptor)
            return descriptor

        def close_action(descriptor: int) -> None:
            original_close(descriptor)
            if descriptor in descriptors:
                descriptors.remove(descriptor)
                raise cleanup

        monkeypatch.setattr(action_module, "_open_action_object", open_action)
        monkeypatch.setattr(action_module.os, "close", close_action)
        if operation == "retain":
            monkeypatch.setattr(
                action_module,
                "publish_exact_storage_object",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(primary),
            )

            def invoke() -> object:
                return store.retain(_snapshot("Bonus"))
        else:
            monkeypatch.setattr(
                action_module,
                "read_bounded_storage_object",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(primary),
            )

            def invoke() -> object:
                return store.resolve(isin=_ISIN, knowledge_cutoff=_RETRIEVED)

        with pytest.raises(TypeError) as raised:
            invoke()
        assert raised.value is primary
        assert descriptors == set()
    finally:
        catalog.close()
        lease.close()


def test_store_propagates_standalone_unknown_object_cleanup_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lease, catalog, store = _leased_store(tmp_path)
    cleanup = RuntimeError("cleanup implementation fault")
    descriptors: set[int] = set()
    original_open = action_module._open_action_object
    original_close = action_module.os.close
    try:
        store.retain(_snapshot("Dividend"))

        def open_action(*args: object, **kwargs: object) -> int:
            descriptor = original_open(*args, **kwargs)
            descriptors.add(descriptor)
            return descriptor

        def close_action(descriptor: int) -> None:
            original_close(descriptor)
            if descriptor in descriptors:
                descriptors.remove(descriptor)
                raise cleanup

        monkeypatch.setattr(action_module, "_open_action_object", open_action)
        monkeypatch.setattr(action_module.os, "close", close_action)
        with pytest.raises(RuntimeError) as raised:
            store.resolve(isin=_ISIN, knowledge_cutoff=_RETRIEVED)
        assert raised.value is cleanup
        assert descriptors == set()
    finally:
        catalog.close()
        lease.close()


def test_persistence_failure_does_not_leave_catalog_evidence(
    tmp_path, monkeypatch
) -> None:
    lease, catalog, store = _leased_store(tmp_path)
    try:
        snapshot = _snapshot("Dividend")
        failure = RuntimeError("injected catalog failure")

        def fail_save(*_args, **_kwargs):
            raise failure

        monkeypatch.setattr(catalog, "save_corporate_action_snapshot", fail_save)
        with pytest.raises(RuntimeError) as raised:
            store.retain(snapshot)
        assert raised.value is failure
        assert catalog.connection.execute(
            "SELECT count(*) FROM corporate_action_snapshots"
        ).fetchone() == (0,)
    finally:
        catalog.close()
        lease.close()


def test_schema_checksum_and_table_inventory_are_frozen() -> None:
    assert (
        hashlib.sha256(catalog_module._CORPORATE_ACTION_SCHEMA_SQL.encode()).hexdigest()
        == catalog_module._CORPORATE_ACTION_SCHEMA_CHECKSUM
    )
    with duckdb.connect(":memory:") as connection:
        connection.execute(catalog_module._CORPORATE_ACTION_SCHEMA_SQL)
        assert connection.execute("SHOW TABLES").fetchall() == [
            ("corporate_action_snapshots",)
        ]


def test_store_rejects_invalid_public_inputs_without_filesystem_mutation(
    tmp_path,
) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        store = CorporateActionSnapshotStoreV1(tmp_path, acquired.lease, catalog)
        with pytest.raises(CorporateActionCorruptError):
            store.retain(object())  # type: ignore[arg-type]
        hostile = object.__new__(CorporateActionSnapshotV1)
        with pytest.raises(CorporateActionCorruptError):
            store.retain(hostile)
        with pytest.raises(CorporateActionCorruptError):
            store.resolve(
                isin="invalid", knowledge_cutoff=datetime(2026, 8, 10, tzinfo=UTC)
            )
    assert "corporate_action_snapshots" not in os.listdir(tmp_path)
