from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

import swing_trading_ai_assistant.market_data.catalog as catalog_module
import swing_trading_ai_assistant.market_data.universe_snapshot as universe_module
from swing_trading_ai_assistant.market_data.catalog import (
    CatalogConflictError,
    CatalogPersistenceError,
    CatalogSchemaError,
    DuckDBCatalog,
)
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.current_cohort import (
    CurrentCohortMemberV1,
    CurrentSuppliedCohortManifestV1,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.market_data.universe_snapshot import (
    Nifty50ConstituentV1,
    Nifty50UniverseSnapshotV1,
    Nifty50UniverseStoreV1,
    UniverseSnapshotAmbiguousError,
    UniverseSnapshotCorruptError,
    UniverseSnapshotNotFoundError,
    UniverseSnapshotStaleError,
)

# Fixed offline alias evidence from the official Nifty 50 constituent CSV retrieved
# 2026-08-12 (SHA-256 9fb8832853c279448d2bc05f0e7dd5f460ed2ff35332fea8c40fc1250362ad28).
_NIFTY50_SYMBOLS_2026_08_12 = (
    "ADANIENT",
    "ADANIPORTS",
    "APOLLOHOSP",
    "ASIANPAINT",
    "AXISBANK",
    "BAJAJ-AUTO",
    "BAJFINANCE",
    "BAJAJFINSV",
    "BEL",
    "BHARTIARTL",
    "CIPLA",
    "COALINDIA",
    "DRREDDY",
    "EICHERMOT",
    "ETERNAL",
    "GRASIM",
    "HCLTECH",
    "HDFCBANK",
    "HDFCLIFE",
    "HINDALCO",
    "HINDUNILVR",
    "ICICIBANK",
    "ITC",
    "INFY",
    "INDIGO",
    "JSWSTEEL",
    "JIOFIN",
    "KOTAKBANK",
    "LT",
    "M&M",
    "MARUTI",
    "MAXHEALTH",
    "NTPC",
    "NESTLEIND",
    "ONGC",
    "POWERGRID",
    "RELIANCE",
    "SBILIFE",
    "SHRIRAMFIN",
    "SBIN",
    "SUNPHARMA",
    "TCS",
    "TATACONSUM",
    "TMPV",
    "TATASTEEL",
    "TECHM",
    "TITAN",
    "TRENT",
    "ULTRACEMCO",
    "WIPRO",
)


def _members() -> tuple[Nifty50ConstituentV1, ...]:
    return tuple(
        Nifty50ConstituentV1(_isin(i), f"SYM{i:02d}", "FINANCIALS") for i in range(50)
    )


def _isin(index: int) -> str:
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
    raise AssertionError


def _snapshot(
    *,
    published_at: datetime = datetime(2024, 1, 1, tzinfo=UTC),
    start: date = date(2024, 1, 1),
    end: date = date(2024, 12, 31),
    members: tuple[Nifty50ConstituentV1, ...] | None = None,
) -> Nifty50UniverseSnapshotV1:
    return Nifty50UniverseSnapshotV1(
        schema_version=1,
        universe_id="nifty-50",
        effective_from=start,
        effective_to=end,
        membership_source="nse-archive",
        membership_release="2024-01",
        membership_published_at=published_at,
        membership_retrieved_at=published_at,
        sector_source="nse-archive",
        sector_release="2024-01",
        sector_published_at=published_at,
        sector_retrieved_at=published_at,
        constituents=members or _members(),
    )


def test_snapshot_canonical_bytes_are_deterministic_and_exact() -> None:
    snapshot = _snapshot()
    payload = snapshot.canonical_json_bytes()
    assert payload == snapshot.canonical_json_bytes()
    assert payload.endswith(b"\n")
    assert Nifty50UniverseSnapshotV1.from_canonical_json_bytes(payload) == snapshot


def test_current_official_symbol_aliases_are_admitted_and_round_trip() -> None:
    members = tuple(
        sorted(
            (
                Nifty50ConstituentV1(_isin(index), symbol, "OFFICIAL FIXTURE")
                for index, symbol in enumerate(_NIFTY50_SYMBOLS_2026_08_12)
            ),
            key=lambda member: member.isin,
        )
    )

    snapshot = _snapshot(members=members)
    restored = Nifty50UniverseSnapshotV1.from_canonical_json_bytes(
        snapshot.canonical_json_bytes()
    )

    assert {member.symbol for member in restored.constituents} == set(
        _NIFTY50_SYMBOLS_2026_08_12
    )
    assert {"M&M", "BAJAJ-AUTO"} <= {member.symbol for member in restored.constituents}


def test_snapshot_revalidation_rejects_exact_member_with_forged_symbol_type() -> None:
    class CaseMaskingStr(str):
        def upper(self) -> str:
            return "MASKED-FORGED-SYMBOL"

    snapshot = _snapshot()
    member = snapshot.constituents[0]
    forged_symbol = CaseMaskingStr(member.symbol)
    assert str(forged_symbol) == member.symbol
    assert forged_symbol.upper() == "MASKED-FORGED-SYMBOL"
    object.__setattr__(member, "symbol", forged_symbol)
    assert type(member) is Nifty50ConstituentV1

    with pytest.raises(ValueError) as raised:
        snapshot.__post_init__()

    assert str(raised.value) == "invalid Nifty 50 constituent"


def test_snapshot_rejects_invalid_member_count_and_noncanonical_bytes() -> None:
    with pytest.raises(ValueError):
        _snapshot().__class__(
            1,
            "nifty-50",
            date(2024, 1, 1),
            date(2024, 12, 31),
            "nse-archive",
            "2024-01",
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 1, tzinfo=UTC),
            "nse-archive",
            "2024-01",
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 1, tzinfo=UTC),
            _members()[:-1],
        )
    with pytest.raises(UniverseSnapshotCorruptError):
        Nifty50UniverseSnapshotV1.from_canonical_json_bytes(
            _snapshot().canonical_json_bytes().replace(b'"nifty-50"', b'"NIFTY-50"')
        )


def test_store_resolves_only_evidence_known_by_cutoff(tmp_path) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        store = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog)
        metadata = store.retain(_snapshot())
        resolved = store.resolve(
            as_of=date(2024, 6, 1), knowledge_cutoff=datetime(2024, 1, 1, tzinfo=UTC)
        )
        assert resolved.metadata == metadata
        with pytest.raises(UniverseSnapshotNotFoundError):
            store.resolve(
                as_of=date(2023, 12, 31),
                knowledge_cutoff=datetime(2024, 1, 1, tzinfo=UTC),
            )
        with pytest.raises(UniverseSnapshotStaleError):
            store.resolve(
                as_of=date(2024, 6, 1),
                knowledge_cutoff=datetime(2023, 12, 31, tzinfo=UTC),
            )


def test_checksum_and_period_membership_are_historical_not_current(tmp_path) -> None:
    assert Nifty50ConstituentV1("INE002A01018", "RELIANCE", "ENERGY")
    # A checksum alone is not a Nifty equity identity.  The durable universe
    # contract deliberately excludes otherwise-valid foreign ISINs.
    with pytest.raises(ValueError):
        Nifty50ConstituentV1("US0378331005", "AAPL", "TECHNOLOGY")
    with pytest.raises(ValueError):
        Nifty50ConstituentV1("INE002A01019", "RELIANCE", "ENERGY")
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    old = _snapshot(end=date(2024, 6, 30))
    changed = list(_members())
    changed[0] = Nifty50ConstituentV1(changed[0].isin, "RENAMED", "ENERGY")
    new = _snapshot(start=date(2024, 7, 1), members=tuple(changed))
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        store = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog)
        store.retain(old)
        store.retain(new)
        assert (
            store.resolve(
                as_of=date(2024, 6, 1),
                knowledge_cutoff=datetime(2024, 1, 1, tzinfo=UTC),
            )
            .snapshot.constituents[0]
            .symbol
            == "SYM00"
        )
        assert (
            store.resolve(
                as_of=date(2024, 7, 1),
                knowledge_cutoff=datetime(2024, 1, 1, tzinfo=UTC),
            )
            .snapshot.constituents[0]
            .symbol
            == "RENAMED"
        )


def test_missing_object_and_overlapping_rows_fail_closed(tmp_path) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        store = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog)
        metadata = store.retain(_snapshot())
        assert store.retain(_snapshot()) == metadata
        changed = list(_members())
        changed[1] = Nifty50ConstituentV1(changed[1].isin, "OTHER", "ENERGY")
        store.retain(_snapshot(members=tuple(changed)))
        with pytest.raises(UniverseSnapshotAmbiguousError):
            store.resolve(
                as_of=date(2024, 6, 1),
                knowledge_cutoff=datetime(2024, 1, 1, tzinfo=UTC),
            )
        catalog.connection.execute(
            "DELETE FROM universe_snapshots WHERE snapshot_sha256 != ?",
            (metadata.snapshot_sha256,),
        )
        (tmp_path / metadata.relative_object_path).unlink()
        with pytest.raises(UniverseSnapshotCorruptError):
            store.resolve(
                as_of=date(2024, 6, 1),
                knowledge_cutoff=datetime(2024, 1, 1, tzinfo=UTC),
            )


def test_short_write_never_publishes_final_and_retry_is_exact(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        store = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog)
        real_write = universe_module.os.write
        calls = 0

        def short_write(descriptor: int, payload: bytes) -> int:
            nonlocal calls
            calls += 1
            return 0 if calls == 1 else real_write(descriptor, payload)

        monkeypatch.setattr(universe_module.os, "write", short_write)
        with pytest.raises(UniverseSnapshotCorruptError):
            store.retain(_snapshot())
        assert not list(tmp_path.rglob("snapshot.json"))
        monkeypatch.setattr(universe_module.os, "write", real_write)
        assert store.retain(_snapshot()).byte_count > 0


def test_corrupt_bytes_and_unsafe_root_fail_closed(tmp_path) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        store = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog)
        metadata = store.retain(_snapshot())
        object_path = tmp_path / metadata.relative_object_path
        object_path.chmod(0o600)
        object_path.write_bytes(b"corrupt")
        with pytest.raises(UniverseSnapshotCorruptError):
            store.resolve(
                as_of=date(2024, 6, 1),
                knowledge_cutoff=datetime(2024, 1, 1, tzinfo=UTC),
            )
        object_path.unlink()
        tmp_path.chmod(0o755)
        with pytest.raises(UniverseSnapshotCorruptError):
            store.retain(_snapshot())


def test_resolve_rejects_existing_canonical_file_with_unsafe_permissions(
    tmp_path,
) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        store = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog)
        metadata = store.retain(_snapshot())
        (tmp_path / metadata.relative_object_path).chmod(0o666)
        with pytest.raises(UniverseSnapshotCorruptError):
            store.resolve(
                as_of=date(2024, 6, 1),
                knowledge_cutoff=datetime(2024, 1, 1, tzinfo=UTC),
            )


@pytest.mark.parametrize(
    "payload",
    (
        b"",
        bytearray(b"{}"),
        b"[]",
        b'{"schema_version":NaN}',
        b'{"schema_version":1,"schema_version":1}',
        b"{" + b"[" * 17 + b"]" * 17 + b"}",
    ),
)
def test_canonical_parser_rejects_noncanonical_input_matrix(payload: object) -> None:
    with pytest.raises(UniverseSnapshotCorruptError):
        Nifty50UniverseSnapshotV1.from_canonical_json_bytes(payload)


def test_canonical_parser_rejects_wrong_key_order_member_shape_and_noncanonical_time() -> (
    None
):
    raw = json.loads(_snapshot().canonical_json_bytes())
    raw["unexpected"] = raw.pop("universe_id")
    cases = [raw]
    raw = json.loads(_snapshot().canonical_json_bytes())
    raw["constituents"] = {}
    cases.append(raw)
    raw = json.loads(_snapshot().canonical_json_bytes())
    raw["constituents"][0] = {
        "symbol": "SYM00",
        "isin": _isin(0),
        "sector": "FINANCIALS",
    }
    cases.append(raw)
    raw = json.loads(_snapshot().canonical_json_bytes())
    raw["membership_published_at"] = "2024-01-01T00:00:00Z"
    cases.append(raw)
    for value in cases:
        with pytest.raises(UniverseSnapshotCorruptError):
            Nifty50UniverseSnapshotV1.from_canonical_json_bytes(
                json.dumps(value, separators=(",", ":")).encode() + b"\n"
            )


def test_retain_rejects_symlink_replacement_and_cleans_temporary_conflict(
    tmp_path,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    with acquired.lease:
        catalog = DuckDBCatalog(root, lease=acquired.lease)
        catalog.__enter__()
        store = Nifty50UniverseStoreV1(root, acquired.lease, catalog)
        held = tmp_path / "held"
        root.rename(held)
        root.symlink_to(held, target_is_directory=True)
        with pytest.raises(UniverseSnapshotCorruptError):
            store.retain(_snapshot())
        with pytest.raises(CatalogPersistenceError):
            catalog.close()
    root.unlink()


def test_publish_conflict_preserves_foreign_final_and_removes_temporary(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)

    class Operation:
        def ensure_live(self) -> None:
            return None

    real_rename = universe_module._rename_noreplace

    def inject_conflict(
        source_parent: int, source: str, target_parent: int, target: str
    ) -> None:
        if target != "snapshot.json":
            real_rename(source_parent, source, target_parent, target)
            return
        foreign = os.open(
            "snapshot.json",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o400,
            dir_fd=target_parent,
        )
        try:
            os.write(foreign, b"foreign")
        finally:
            os.close(foreign)
        real_rename(source_parent, source, target_parent, target)

    monkeypatch.setattr(universe_module, "_rename_noreplace", inject_conflict)
    try:
        os.mkdir("universe_snapshots", 0o700, dir_fd=descriptor)
        parent = os.open(
            "universe_snapshots", os.O_RDONLY | os.O_DIRECTORY, dir_fd=descriptor
        )
        try:
            os.mkdir("sha256=test", 0o700, dir_fd=parent)
            child = os.open("sha256=test", os.O_RDONLY | os.O_DIRECTORY, dir_fd=parent)
            try:
                with pytest.raises(ValueError):
                    universe_module._publish_exact(
                        Operation(), child, "snapshot.json", b"expected"
                    )
                assert not (
                    tmp_path / "universe_snapshots/sha256=test/.snapshot.json.tmp"
                ).exists()
                assert (
                    tmp_path / "universe_snapshots/sha256=test/snapshot.json"
                ).read_bytes() == b"foreign"
            finally:
                os.close(child)
        finally:
            os.close(parent)
    finally:
        os.close(descriptor)


def test_publish_same_payload_race_is_idempotent_and_cleans_temporary(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)

    class Operation:
        def ensure_live(self) -> None:
            return None

    real_rename = universe_module._rename_noreplace

    def inject_matching_final(
        source_parent: int, source: str, target_parent: int, target: str
    ) -> None:
        if target != "snapshot.json":
            real_rename(source_parent, source, target_parent, target)
            return
        foreign = os.open(
            "snapshot.json",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o400,
            dir_fd=target_parent,
        )
        try:
            os.write(foreign, b"expected")
        finally:
            os.close(foreign)
        real_rename(source_parent, source, target_parent, target)

    monkeypatch.setattr(universe_module, "_rename_noreplace", inject_matching_final)
    try:
        universe_module._publish_exact(
            Operation(), descriptor, "snapshot.json", b"expected"
        )
        assert not (tmp_path / ".snapshot.json.tmp").exists()
        assert (tmp_path / "snapshot.json").read_bytes() == b"expected"
    finally:
        os.close(descriptor)


def test_resolve_rejects_invalid_request_and_metadata_mismatch(tmp_path) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        store = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog)
        store.retain(_snapshot())
        with pytest.raises(UniverseSnapshotCorruptError):
            store.resolve(
                as_of=datetime(2024, 1, 1, tzinfo=UTC),
                knowledge_cutoff=datetime(2024, 1, 1, tzinfo=UTC),
            )  # type: ignore[arg-type]
        catalog.connection.execute(
            "UPDATE universe_snapshots SET membership_release = 'other'"
        )
        with pytest.raises(UniverseSnapshotCorruptError):
            store.resolve(
                as_of=date(2024, 1, 1),
                knowledge_cutoff=datetime(2024, 1, 1, tzinfo=UTC),
            )


def test_defensive_helpers_cover_size_depth_metadata_and_bounded_file_branches(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(universe_module, "MAX_UNIVERSE_JSON_BYTES_V1", 1)
    with pytest.raises(ValueError):
        _snapshot().canonical_json_bytes()
    monkeypatch.undo()
    with pytest.raises(UniverseSnapshotCorruptError):
        Nifty50UniverseSnapshotV1.from_canonical_json_bytes(
            _snapshot().canonical_json_bytes() + b" "
        )
    with pytest.raises(ValueError):
        universe_module.UniverseSnapshotMetadataV1(
            1,
            "nifty-50",
            date(2024, 1, 1),
            date(2024, 1, 2),
            "source",
            "release",
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 1, tzinfo=UTC),
            "source",
            "release",
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 1, tzinfo=UTC),
            "a" * 64,
            1,
            "unsafe",
        )
    with pytest.raises(ValueError):
        universe_module._parse_timestamp(None)
    with pytest.raises(ValueError):
        universe_module._assert_depth({}, 17)
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(ValueError):
            universe_module._read_fd(directory_fd, 1)
        file_fd = os.open(
            "bounded", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory_fd
        )
        try:
            os.write(file_fd, b"abc")
        finally:
            os.close(file_fd)
        file_fd = os.open("bounded", os.O_RDONLY, dir_fd=directory_fd)
        try:
            with pytest.raises(ValueError):
                universe_module._read_fd(file_fd, 2)
        finally:
            os.close(file_fd)
    finally:
        os.close(directory_fd)


def test_retain_wrong_type_and_existing_object_mismatch_fail_closed(tmp_path) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        store = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog)
        with pytest.raises(UniverseSnapshotCorruptError):
            store.retain(object())  # type: ignore[arg-type]
        metadata = store.retain(_snapshot())
        object_path = tmp_path / metadata.relative_object_path
        object_path.chmod(0o600)
        object_path.write_bytes(b"not-the-canonical-snapshot")
        with pytest.raises(UniverseSnapshotCorruptError):
            store.retain(_snapshot())


def test_retain_rejects_final_window_replacement_without_cataloging_foreign_bytes(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    real_rename = universe_module._rename_noreplace

    def replace_after_link(
        source_parent: int, source: str, target_parent: int, target: str
    ) -> None:
        real_rename(source_parent, source, target_parent, target)
        if target != "snapshot.json":
            return
        os.unlink(target, dir_fd=target_parent)
        foreign = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o400,
            dir_fd=target_parent,
        )
        try:
            os.write(foreign, b"foreign-final")
        finally:
            os.close(foreign)

    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        store = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog)
        with monkeypatch.context() as scoped:
            scoped.setattr(universe_module, "_rename_noreplace", replace_after_link)
            with pytest.raises(UniverseSnapshotCorruptError):
                store.retain(_snapshot())
        assert catalog.list_universe_snapshots() == ()
        final = next(tmp_path.rglob("snapshot.json"))
        assert final.read_bytes() == b"foreign-final"


@pytest.mark.parametrize("operation", ("retain", "resolve"))
def test_private_root_is_rechecked_inside_held_operation(
    tmp_path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    """A chmod after admission cannot use the previously safe root."""
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    real_root_operation = acquired.lease.root_operation

    def chmod_before_operation(path: object) -> object:
        root.chmod(0o755)
        return real_root_operation(path)

    with acquired.lease, DuckDBCatalog(root, lease=acquired.lease) as catalog:
        store = Nifty50UniverseStoreV1(root, acquired.lease, catalog)
        if operation == "resolve":
            root.chmod(0o700)
            store.retain(_snapshot())
        expected_rows = catalog.list_universe_snapshots()
        monkeypatch.setattr(
            acquired.lease,
            "read_operation" if operation == "resolve" else "root_operation",
            chmod_before_operation,
        )
        with pytest.raises(UniverseSnapshotCorruptError):
            if operation == "retain":
                store.retain(_snapshot())
            else:
                store.resolve(
                    as_of=date(2024, 6, 1),
                    knowledge_cutoff=datetime(2024, 1, 1, tzinfo=UTC),
                )
        assert catalog.list_universe_snapshots() == expected_rows
        monkeypatch.setattr(acquired.lease, "root_operation", real_root_operation)
        root.chmod(0o700)


def test_cleanup_quarantines_substituted_temp_without_deleting_foreign_bytes(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    temporary = ".snapshot.json.stale.tmp"
    stale = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400, dir_fd=descriptor
    )
    os.close(stale)
    identity = universe_module._entry_identity(os.stat(temporary, dir_fd=descriptor))
    real_rename = universe_module._rename_noreplace

    def substitute(
        source_parent: int, source: str, target_parent: int, target: str
    ) -> None:
        os.unlink(source, dir_fd=source_parent)
        foreign = os.open(
            source,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o400,
            dir_fd=source_parent,
        )
        try:
            os.write(foreign, b"foreign")
        finally:
            os.close(foreign)
        real_rename(source_parent, source, target_parent, target)

    monkeypatch.setattr(universe_module, "_rename_noreplace", substitute)
    try:
        with pytest.raises(ValueError):
            universe_module._quarantine_then_remove_exact(
                descriptor, temporary, identity
            )
        retained = tuple(tmp_path.glob(".snapshot-quarantine.*/entry"))
        assert len(retained) == 1
        assert retained[0].read_bytes() == b"foreign"
    finally:
        os.close(descriptor)


def test_cleanup_retries_quarantine_collision_without_touching_foreign_bytes(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    temporary = ".snapshot.json.stale.tmp"
    stale = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400, dir_fd=descriptor
    )
    os.close(stale)
    identity = universe_module._entry_identity(os.stat(temporary, dir_fd=descriptor))
    collision_token = b"c" * 16
    accepted_token = b"a" * 16
    collision = tmp_path / f".snapshot-quarantine.{collision_token.hex()}"
    collision.mkdir()
    (collision / "foreign").write_bytes(b"foreign-quarantine")
    tokens = iter((collision_token, accepted_token))
    monkeypatch.setattr(universe_module.os, "urandom", lambda _: next(tokens))
    try:
        universe_module._quarantine_then_remove_exact(descriptor, temporary, identity)
        assert (collision / "foreign").read_bytes() == b"foreign-quarantine"
        assert not (tmp_path / temporary).exists()
        assert (
            tmp_path / f".snapshot-quarantine.{accepted_token.hex()}" / "entry"
        ).read_bytes() == b""
    finally:
        os.close(descriptor)


def test_cleanup_never_unlinks_a_post_validation_quarantine_path(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    temporary = ".snapshot.json.stale.tmp"
    stale = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400, dir_fd=descriptor
    )
    os.write(stale, b"owned")
    os.close(stale)
    identity = universe_module._entry_identity(os.stat(temporary, dir_fd=descriptor))

    def forbidden_unlink(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("quarantined entries must never be unlinked by pathname")

    monkeypatch.setattr(universe_module.os, "unlink", forbidden_unlink)
    try:
        universe_module._quarantine_then_remove_exact(descriptor, temporary, identity)
        retained = tuple(tmp_path.glob(".snapshot-quarantine.*/entry"))
        assert len(retained) == 1
        assert retained[0].read_bytes() == b"owned"
    finally:
        os.close(descriptor)


def test_atomic_noreplace_uses_linux_flag_and_surfaces_os_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, ...]] = []

    class Operation:
        argtypes: object = None
        restype: object = None

        def __call__(self, *values: object) -> int:
            calls.append(values)
            return -1

    class Library:
        renameat2 = Operation()

    monkeypatch.setattr(universe_module.sys, "platform", "linux")
    monkeypatch.setattr(
        universe_module.ctypes, "CDLL", lambda *_args, **_kwargs: Library()
    )
    monkeypatch.setattr(universe_module.ctypes, "get_errno", lambda: 17)
    with pytest.raises(OSError) as error:
        universe_module._rename_noreplace(1, "source", 2, "target")
    assert error.value.errno == 17
    assert calls == [(1, b"source", 2, b"target", 1)]


def test_atomic_noreplace_rejects_unsupported_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(universe_module.sys, "platform", "unsupported")
    with pytest.raises(OSError) as error:
        universe_module._rename_noreplace(1, "source", 2, "target")
    assert error.value.errno == universe_module.errno.ENOTSUP


def test_generated_temp_collisions_are_preserved_and_never_reopened(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    name = ".snapshot.json." + (b"x" * 16).hex() + ".tmp"
    (tmp_path / name).write_bytes(b"foreign")
    monkeypatch.setattr(universe_module.os, "urandom", lambda _: b"x" * 16)
    try:
        with pytest.raises(ValueError):
            universe_module._open_private_temporary(descriptor, "snapshot.json")
        assert (tmp_path / name).read_bytes() == b"foreign"
    finally:
        os.close(descriptor)


def test_resolve_rejects_external_hardlink(tmp_path) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        store = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog)
        metadata = store.retain(_snapshot())
        canonical = tmp_path / metadata.relative_object_path
        os.link(canonical, tmp_path / "external-hardlink")
        with pytest.raises(UniverseSnapshotCorruptError):
            store.resolve(
                as_of=date(2024, 6, 1),
                knowledge_cutoff=datetime(2024, 1, 1, tzinfo=UTC),
            )


def test_post_commit_object_mutation_compensates_only_matching_metadata(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        store = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog)
        original = universe_module._validate_retained_snapshot
        calls = 0

        def mutate_after_commit(*args: object) -> None:
            nonlocal calls
            calls += 1
            if calls == 3:
                descriptor = args[1]
                target = os.open("snapshot.json", os.O_WRONLY, dir_fd=descriptor)
                try:
                    os.write(target, b"X")
                finally:
                    os.close(target)
            original(*args)  # type: ignore[arg-type]

        monkeypatch.setattr(
            universe_module, "_validate_retained_snapshot", mutate_after_commit
        )
        with pytest.raises(UniverseSnapshotCorruptError):
            store.retain(_snapshot())
        assert catalog.list_universe_snapshots() == ()


def test_catalog_precommit_validator_rolls_back_universe_row(tmp_path) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        metadata = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog).retain(
            _snapshot()
        )
        catalog.connection.execute("DELETE FROM universe_snapshots")
        failure = ValueError()
        with pytest.raises(ValueError) as raised:
            catalog.save_universe_snapshot(
                metadata,
                precommit_validator=lambda: (_ for _ in ()).throw(failure),
            )
        assert raised.value is failure
        assert catalog.list_universe_snapshots() == ()


@pytest.mark.parametrize("unsafe", ("nested_directory", "canonical_file"))
def test_retain_rejects_unsafe_existing_object_permissions_without_catalog_mutation(
    tmp_path, unsafe: str
) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    snapshot = _snapshot()
    payload = snapshot.canonical_json_bytes()
    digest = universe_module.hashlib.sha256(payload).hexdigest()
    parent = tmp_path / "universe_snapshots"
    parent.mkdir(mode=0o700)
    object_directory = parent / f"sha256={digest}"
    object_directory.mkdir(mode=0o700)
    if unsafe == "nested_directory":
        object_directory.chmod(0o777)
    else:
        final = object_directory / "snapshot.json"
        final.write_bytes(payload)
        final.chmod(0o666)
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        store = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog)
        with pytest.raises(UniverseSnapshotCorruptError):
            store.retain(snapshot)
        assert catalog.list_universe_snapshots() == ()
    if unsafe == "nested_directory":
        assert object_directory.stat().st_mode & 0o777 == 0o777
    else:
        assert (object_directory / "snapshot.json").read_bytes() == payload


@pytest.mark.parametrize("checks", ((False,), (True, False)))
def test_bounded_read_rejects_entry_replacement_before_or_after_read(
    tmp_path, monkeypatch: pytest.MonkeyPatch, checks: tuple[bool, ...]
) -> None:
    path = tmp_path / "snapshot.json"
    path.write_bytes(b"ok")
    path.chmod(0o400)
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    values = iter(checks)

    class Operation:
        def ensure_live(self) -> None:
            return None

    monkeypatch.setattr(universe_module, "_same_entry", lambda *_: next(values))
    try:
        with pytest.raises(ValueError):
            universe_module._read_bounded(Operation(), descriptor, "snapshot.json", 2)
    finally:
        os.close(descriptor)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO")
def test_immutable_read_fifo_substitution_after_admission_fails_promptly(
    tmp_path,
) -> None:
    environment = {
        **os.environ,
        "PLAN33_FIFO_SUBPROCESS_ROOT": str(tmp_path.resolve()),
    }
    script = """
import os
import stat
import tempfile
from pathlib import Path

from swing_trading_ai_assistant.market_data import universe_snapshot as universe
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease


for stage in ("existing", "temporary", "final", "bounded"):
    with tempfile.TemporaryDirectory(
        dir=os.environ["PLAN33_FIFO_SUBPROCESS_ROOT"]
    ) as temporary:
        root = Path(temporary) / "root"
        root.mkdir(mode=0o700)
        lease = StorageRootLease.try_acquire_private_empty(root).lease
        assert lease is not None
        name = "snapshot.json"
        payload = b"expected"
        target = root / name
        with lease.root_operation(root) as operation:
            if stage in {"existing", "bounded"}:
                descriptor = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o400,
                    dir_fd=operation.descriptor,
                )
                try:
                    os.write(descriptor, payload)
                finally:
                    os.close(descriptor)
            real_open = universe.os.open
            replacement = [None]

            def substitute(path, flags, mode=0o777, **kwargs):
                path_text = os.fspath(path)
                readonly = (flags & os.O_ACCMODE) == os.O_RDONLY
                temporary_readback = (
                    stage == "temporary"
                    and readonly
                    and path_text.startswith(f".{name}.")
                    and path_text.endswith(".tmp")
                )
                final_readback = (
                    stage == "final"
                    and readonly
                    and path_text == name
                    and target.exists()
                )
                direct_read = (
                    stage in {"existing", "bounded"}
                    and readonly
                    and path_text == name
                )
                if replacement[0] is None and (
                    temporary_readback or final_readback or direct_read
                ):
                    os.unlink(path_text, dir_fd=kwargs["dir_fd"])
                    os.mkfifo(path_text, mode=0o400, dir_fd=kwargs["dir_fd"])
                    replacement[0] = root / path_text
                return real_open(path, flags, mode, **kwargs)

            universe.os.open = substitute
            try:
                try:
                    if stage == "bounded":
                        universe._read_bounded(operation, operation.descriptor, name, len(payload))
                    else:
                        universe._publish_exact(
                            operation, operation.descriptor, name, payload
                        )
                except ValueError:
                    pass
                else:
                    raise SystemExit(f"{stage} FIFO was accepted")
            finally:
                universe.os.open = real_open
            if replacement[0] is None or not stat.S_ISFIFO(
                replacement[0].lstat().st_mode
            ):
                raise SystemExit(f"{stage} FIFO was not preserved")
        lease.close()
"""
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and test script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr


def test_catalog_universe_boundaries_and_conflicts_fail_closed(tmp_path) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        metadata = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog).retain(
            _snapshot()
        )
        assert catalog.list_universe_snapshots() == (metadata,)
        assert catalog.has_universe_snapshot_coverage(as_of=date(2024, 6, 1))
        catalog.save_universe_snapshot(metadata)
        with pytest.raises(CatalogConflictError):
            catalog.save_universe_snapshot(object())  # type: ignore[arg-type]
        with pytest.raises(CatalogConflictError):
            catalog.save_universe_snapshot(
                replace(metadata, membership_release="conflicting-release")
            )
        with pytest.raises(CatalogConflictError):
            catalog.resolve_universe_snapshots(
                as_of=datetime(2024, 6, 1, tzinfo=UTC),  # type: ignore[arg-type]
                knowledge_cutoff=datetime(2024, 6, 1, tzinfo=UTC),
            )
        with pytest.raises(CatalogConflictError):
            catalog.resolve_universe_snapshots(
                as_of=date(2024, 6, 1), knowledge_cutoff=datetime(2024, 6, 1)
            )
        with pytest.raises(CatalogConflictError):
            catalog.has_universe_snapshot_coverage(
                as_of=datetime(2024, 6, 1, tzinfo=UTC)  # type: ignore[arg-type]
            )
        assert not catalog.has_universe_snapshot_coverage(as_of=date(2025, 1, 1))


def test_catalog_universe_read_failures_are_typed(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog).retain(_snapshot())

        def conflict(_: tuple[object, ...]) -> object:
            raise CatalogConflictError("injected catalog conflict")

        with monkeypatch.context() as scoped:
            scoped.setattr(catalog_module, "_universe_metadata_from_row", conflict)
            with pytest.raises(CatalogConflictError):
                catalog.list_universe_snapshots()
            with pytest.raises(CatalogConflictError):
                catalog.resolve_universe_snapshots(
                    as_of=date(2024, 6, 1),
                    knowledge_cutoff=datetime(2024, 6, 1, tzinfo=UTC),
                )

        real_connection = catalog._connection

        class ConflictConnection:
            def execute(self, *_: object, **__: object) -> object:
                raise CatalogConflictError("injected catalog conflict")

        catalog._connection = ConflictConnection()
        try:
            with pytest.raises(CatalogConflictError):
                catalog.has_universe_snapshot_coverage(as_of=date(2024, 6, 1))
        finally:
            catalog._connection = real_connection

        catalog.connection.close()
        with pytest.raises(CatalogPersistenceError):
            catalog.list_universe_snapshots()
        with pytest.raises(CatalogPersistenceError):
            catalog.resolve_universe_snapshots(
                as_of=date(2024, 6, 1),
                knowledge_cutoff=datetime(2024, 6, 1, tzinfo=UTC),
            )
        with pytest.raises(CatalogPersistenceError):
            catalog.has_universe_snapshot_coverage(as_of=date(2024, 6, 1))

    with pytest.raises(CatalogSchemaError):
        catalog_module._universe_metadata_from_row((1,))


def test_resolve_rejects_same_inode_mutation_after_valid_bounded_read(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        store = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog)
        metadata = store.retain(_snapshot())
        object_path = tmp_path / metadata.relative_object_path
        real_read = universe_module._read_fd

        def mutate_after_read(descriptor: int, maximum: int) -> bytes:
            data = real_read(descriptor, maximum)
            object_path.chmod(0o600)
            object_path.write_bytes(b"X" * len(data))
            object_path.chmod(0o400)
            return data

        with monkeypatch.context() as scoped:
            scoped.setattr(universe_module, "_read_fd", mutate_after_read)
            with pytest.raises(UniverseSnapshotCorruptError):
                store.resolve(
                    as_of=date(2024, 6, 1),
                    knowledge_cutoff=datetime(2024, 1, 1, tzinfo=UTC),
                )


@pytest.mark.parametrize("fault_type", (TypeError, ValueError))
def test_canonical_decoder_preserves_unexpected_helper_fault_identity(
    monkeypatch: pytest.MonkeyPatch, fault_type: type[Exception]
) -> None:
    payload = _snapshot().canonical_json_bytes()
    error = fault_type("unexpected decoder helper fault")
    reached = False

    def fail_member(_value: object) -> Nifty50ConstituentV1:
        nonlocal reached
        reached = True
        raise error

    monkeypatch.setattr(universe_module, "_parse_member", fail_member)

    with pytest.raises(fault_type) as raised:
        Nifty50UniverseSnapshotV1.from_canonical_json_bytes(payload)

    assert reached
    assert raised.value is error


@pytest.mark.parametrize(
    "fault_type",
    (AssertionError, KeyError, RuntimeError, Exception, TypeError, ValueError),
)
def test_resolve_preserves_unexpected_retained_read_fault_identity(
    tmp_path, monkeypatch: pytest.MonkeyPatch, fault_type: type[BaseException]
) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(tmp_path, lease=acquired.lease) as catalog:
        store = Nifty50UniverseStoreV1(tmp_path, acquired.lease, catalog)
        store.retain(_snapshot())
        error = fault_type("unexpected retained read fault")
        reached = False

        def fail_read(_descriptor: int, _maximum: int) -> bytes:
            nonlocal reached
            reached = True
            raise error

        monkeypatch.setattr(universe_module, "_read_fd", fail_read)

        with pytest.raises(fault_type) as raised:
            store.resolve(
                as_of=date(2024, 6, 1),
                knowledge_cutoff=datetime(2024, 1, 1, tzinfo=UTC),
            )

    assert reached
    assert raised.value is error


def test_default_cohort_cli_propagates_retained_universe_read_fault_without_archive(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "retained"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    snapshot = _snapshot()
    with acquired.lease, DuckDBCatalog(root, lease=acquired.lease) as catalog:
        Nifty50UniverseStoreV1(root, acquired.lease, catalog).retain(snapshot)

    member = snapshot.constituents[0]
    cohort_file = tmp_path / "cohort.json"
    manifest = CurrentSuppliedCohortManifestV1(
        datetime(2024, 1, 1, tzinfo=UTC),
        (CurrentCohortMemberV1(member.isin, member.symbol),),
    )
    cohort_file.write_bytes(
        json.dumps(
            {
                "contract_version": manifest.contract_version,
                "members": [{"isin": member.isin, "symbol": member.symbol}],
                "selected_at": "2024-01-01T00:00:00.000000Z",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )
    error = RuntimeError("unexpected universe read defect")
    reached = False

    def fail_read(_descriptor: int, _maximum: int) -> bytes:
        nonlocal reached
        reached = True
        raise error

    monkeypatch.setattr(universe_module, "_read_fd", fail_read)

    exit_code = main(
        [
            "cohort-current",
            "--cohort-file",
            str(cohort_file),
            "--storage-root",
            str(root),
            "--cutoff",
            "2024-06-01T00:00:00.000000Z",
            "--output",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert reached
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "internal_error\n"
    assert not (root / ".current-fact-archive-v1").exists()
