from __future__ import annotations

import errno
import gzip
import json
import os
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.download_preparation as preparation_module
import swing_trading_ai_assistant.market_data.instrument_snapshot as snapshot_module
from swing_trading_ai_assistant.market_data.catalog import (
    CatalogConflictError,
    DuckDBCatalog,
)
from swing_trading_ai_assistant.market_data.download_preparation import (
    AuthoritativeScheduleInputV1,
    CanonicalFileScheduleSourceV1,
    DownloadPreparationReportV1,
    DownloadPreparationRequestV1,
    DownloadPreparationServiceV1,
    PreparationFailureCodeV1,
    PreparationOutcomeV1,
)
from swing_trading_ai_assistant.market_data.http import (
    HttpResponse,
    HttpResponseHeaders,
)
from swing_trading_ai_assistant.market_data.instrument_snapshot import (
    InstrumentSnapshotClientV1,
    InstrumentSnapshotCorruptError,
    InstrumentSnapshotMetadataV1,
    InstrumentSnapshotNotFoundError,
    InstrumentSnapshotStoreV1,
    InstrumentSnapshotUnavailableError,
)
from swing_trading_ai_assistant.market_data.preview_admission import (
    PreviewAdmissionPolicyV1,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    SCHEDULE_SCHEMA_VERSION_V3,
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleEvidenceResult,
    ScheduleFailureCode,
    ScheduleOutcome,
    ScheduleSession,
    canonical_schedule_bytes,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

RELIANCE = {
    "segment": "NSE_EQ",
    "name": "RELIANCE INDUSTRIES LIMITED",
    "exchange": "NSE",
    "isin": "INE002A01018",
    "instrument_type": "EQ",
    "instrument_key": "NSE_EQ|INE002A01018",
    "trading_symbol": "RELIANCE",
}


class StaticTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        self.requests.append((url, headers))
        return self.response


class StaticScheduleSource:
    def __init__(self, value: AuthoritativeScheduleInputV1 | Exception) -> None:
        self.value = value
        self.calls = 0

    def load(self) -> AuthoritativeScheduleInputV1:
        self.calls += 1
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


class CountingSnapshotSource:
    def __init__(self, client: InstrumentSnapshotClientV1) -> None:
        self.client = client
        self.calls = 0

    def fetch(self):  # type annotation is inferred from the delegated method
        self.calls += 1
        return self.client.fetch()


class NoFetchSnapshotSource:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self):
        self.calls += 1
        raise AssertionError("snapshot source must not run")


class FailingSnapshotCatalog:
    def __init__(self, catalog: DuckDBCatalog) -> None:
        self.catalog = catalog

    def save_instrument_snapshot(self, metadata: object) -> None:
        raise RuntimeError("injected catalog failure")

    def list_instrument_snapshots(self, source: str, *, retrieved_at_lte=None):
        return self.catalog.list_instrument_snapshots(
            source, retrieved_at_lte=retrieved_at_lte
        )


def _schedule() -> ExpectedSessionSchedule:
    covered_from = date(2026, 7, 1)
    covered_to = date(2026, 7, 31)
    session_date = date(2026, 7, 1)
    closures = tuple(
        ScheduleClosure(covered_from + timedelta(days=offset), "sourced closure")
        for offset in range(1, 31)
    )
    return ExpectedSessionSchedule(
        schema_version=2,
        source="nse-authoritative-test",
        source_release="release-2026-08-01",
        as_of=datetime(2026, 8, 1, tzinfo=UTC),
        timezone="Asia/Kolkata",
        covered_from=covered_from,
        covered_to=covered_to,
        sessions=(
            ScheduleSession(
                session_date,
                datetime(2026, 7, 1, 3, 45, tzinfo=UTC),
                datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
                "regular",
            ),
        ),
        closures=closures,
    )


def _schedule_input() -> AuthoritativeScheduleInputV1:
    schedule = _schedule()
    return AuthoritativeScheduleInputV1(schedule, canonical_schedule_bytes(schedule))


def _open_schedule() -> ExpectedSessionSchedule:
    covered_from = date(2026, 8, 1)
    covered_to = date(2026, 8, 11)
    sessions = (
        ScheduleSession(
            date(2026, 8, 10),
            datetime(2026, 8, 10, 3, 45, tzinfo=UTC),
            datetime(2026, 8, 10, 10, 0, tzinfo=UTC),
            "regular",
        ),
        ScheduleSession(
            date(2026, 8, 11),
            datetime(2026, 8, 11, 3, 45, tzinfo=UTC),
            datetime(2026, 8, 11, 10, 0, tzinfo=UTC),
            "regular",
        ),
    )
    closures = tuple(
        ScheduleClosure(covered_from + timedelta(days=offset), "sourced closure")
        for offset in range(9)
    )
    return ExpectedSessionSchedule(
        schema_version=SCHEDULE_SCHEMA_VERSION_V3,
        source="nse-authoritative-test",
        source_release="release-2026-08-11",
        as_of=datetime(2026, 8, 11, 3, 30, tzinfo=UTC),
        timezone="Asia/Kolkata",
        covered_from=covered_from,
        covered_to=covered_to,
        sessions=sessions,
        closures=closures,
    )


def test_open_month_preparation_retains_v3_schedule_and_resolves_instrument(
    tmp_path: Path,
) -> None:
    schedule = _open_schedule()
    snapshot_client, _ = _snapshot_client(datetime(2026, 8, 11, 3, 0, tzinfo=UTC))
    service = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(
            AuthoritativeScheduleInputV1(schedule, canonical_schedule_bytes(schedule))
        ),
        CountingSnapshotSource(snapshot_client),
    )

    report = service.prepare_open_month(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            tmp_path,
            datetime(2026, 8, 11, 6, 30, tzinfo=UTC),
        )
    )

    assert report.outcome is PreparationOutcomeV1.SUCCEEDED
    assert report.prepared is not None
    assert report.prepared.schedule == schedule
    assert report.prepared.instrument.instrument_key == "NSE_EQ|INE002A01018"


def test_canonical_file_schedule_source_loads_exact_bounded_evidence(
    tmp_path: Path,
) -> None:
    canonical = canonical_schedule_bytes(_schedule())
    source_path = tmp_path / "schedule.json"
    source_path.write_bytes(canonical)
    source_path.chmod(0o600)

    loaded = CanonicalFileScheduleSourceV1(source_path).load()

    assert loaded.schedule == _schedule()
    assert loaded.canonical_bytes == canonical


@pytest.mark.parametrize(
    "unsafe", ("symlink", "group-writable", "oversized", "fifo", "noncanonical")
)
def test_canonical_file_schedule_source_rejects_unsafe_inputs(
    tmp_path: Path, unsafe: str
) -> None:
    canonical = canonical_schedule_bytes(_schedule())
    safe = tmp_path / "safe.json"
    safe.write_bytes(canonical)
    safe.chmod(0o600)
    source_path = tmp_path / "schedule.json"
    if unsafe == "symlink":
        source_path.symlink_to(safe)
    elif unsafe == "group-writable":
        source_path.write_bytes(canonical)
        source_path.chmod(0o620)
    elif unsafe == "oversized":
        source_path.write_bytes(b"x" * 1_000_001)
        source_path.chmod(0o600)
    elif unsafe == "fifo":
        os.mkfifo(source_path, mode=0o600)
    else:
        source_path.write_bytes(b"{}")
        source_path.chmod(0o600)

    with pytest.raises(ValueError, match="authoritative schedule file"):
        CanonicalFileScheduleSourceV1(source_path).load()


def test_canonical_file_schedule_source_rejects_relative_path() -> None:
    with pytest.raises(ValueError, match="authoritative schedule file"):
        CanonicalFileScheduleSourceV1(Path("relative-schedule.json")).load()


def test_canonical_file_schedule_source_rejects_short_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = tmp_path / "schedule.json"
    source_path.write_bytes(canonical_schedule_bytes(_schedule()))
    source_path.chmod(0o600)
    monkeypatch.setattr(preparation_module.os, "read", lambda *_: b"")

    with pytest.raises(ValueError, match="authoritative schedule file"):
        CanonicalFileScheduleSourceV1(source_path).load()


def test_canonical_file_schedule_source_rejects_same_inode_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical = canonical_schedule_bytes(_schedule())
    source_path = tmp_path / "schedule.json"
    source_path.write_bytes(canonical)
    source_path.chmod(0o600)
    real_read = os.read
    mutated = False

    def mutate_after_read(descriptor: int, size: int) -> bytes:
        nonlocal mutated
        chunk = real_read(descriptor, size)
        if chunk and not mutated:
            mutated = True
            with source_path.open("r+b", buffering=0) as writer:
                writer.seek(len(canonical) - 2)
                original = writer.read(1)
                writer.seek(len(canonical) - 2)
                writer.write(b" " if original != b" " else b"\n")
                os.fsync(writer.fileno())
        return chunk

    monkeypatch.setattr(preparation_module.os, "read", mutate_after_read)

    with pytest.raises(ValueError, match="authoritative schedule file"):
        CanonicalFileScheduleSourceV1(source_path).load()


def test_canonical_file_schedule_source_rejects_path_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical = canonical_schedule_bytes(_schedule())
    source_path = tmp_path / "schedule.json"
    source_path.write_bytes(canonical)
    source_path.chmod(0o600)
    displaced_path = tmp_path / "displaced.json"
    real_read = os.read
    substituted = False

    def substitute_after_read(descriptor: int, size: int) -> bytes:
        nonlocal substituted
        chunk = real_read(descriptor, size)
        if chunk and not substituted:
            substituted = True
            source_path.rename(displaced_path)
            source_path.write_bytes(canonical)
            source_path.chmod(0o600)
        return chunk

    monkeypatch.setattr(preparation_module.os, "read", substitute_after_read)

    with pytest.raises(ValueError, match="authoritative schedule file"):
        CanonicalFileScheduleSourceV1(source_path).load()


@pytest.mark.parametrize("attack", ("same-inode", "path-substitution"))
def test_schedule_file_race_stops_before_storage_snapshot_or_provider_activity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, attack: str
) -> None:
    canonical = canonical_schedule_bytes(_schedule())
    source_path = tmp_path / "schedule.json"
    source_path.write_bytes(canonical)
    source_path.chmod(0o600)
    displaced_path = tmp_path / "displaced.json"
    real_read = os.read
    attacked = False

    def attack_after_read(descriptor: int, size: int) -> bytes:
        nonlocal attacked
        chunk = real_read(descriptor, size)
        if chunk and not attacked:
            attacked = True
            if attack == "same-inode":
                with source_path.open("r+b", buffering=0) as writer:
                    writer.seek(len(canonical) - 2)
                    writer.write(b" ")
                    os.fsync(writer.fileno())
            else:
                source_path.rename(displaced_path)
                source_path.write_bytes(canonical)
                source_path.chmod(0o600)
        return chunk

    monkeypatch.setattr(preparation_module.os, "read", attack_after_read)
    snapshot = NoFetchSnapshotSource()
    storage_root = tmp_path / "storage"
    service = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        CanonicalFileScheduleSourceV1(source_path),
        snapshot,
    )

    report = service.prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            storage_root,
            datetime(2026, 8, 10, tzinfo=UTC),
        )
    )

    assert report.outcome is PreparationOutcomeV1.INSUFFICIENT_EVIDENCE
    assert report.failure_code is PreparationFailureCodeV1.SCHEDULE_UNAVAILABLE
    assert snapshot.calls == 0
    assert not storage_root.exists()


def _snapshot_client(
    retrieved_at: datetime,
) -> tuple[InstrumentSnapshotClientV1, StaticTransport]:
    body = gzip.compress(json.dumps([RELIANCE], separators=(",", ":")).encode())
    transport = StaticTransport(
        HttpResponse(
            200,
            body,
            HttpResponseHeaders.from_items(
                (
                    ("ETag", '"snapshot-v1"'),
                    ("Last-Modified", "Mon, 10 Aug 2026 02:00:00 GMT"),
                )
            ),
        )
    )
    return InstrumentSnapshotClientV1(transport, clock=lambda: retrieved_at), transport


def test_preview_admission_is_exact_and_has_no_provider_identity() -> None:
    policy = PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE")
    assert policy.admits("NSE_EQ", "RELIANCE")
    assert not policy.admits("NSE_EQ", "TCS")
    assert not policy.admits("NSE_FO", "RELIANCE")
    assert "INE002A01018" not in repr(policy)
    with pytest.raises(ValueError):
        PreviewAdmissionPolicyV1("NSE_EQ", "TCS")
    with pytest.raises(ValueError):
        PreviewAdmissionPolicyV1(1, "RELIANCE")  # type: ignore[arg-type]


def test_snapshot_client_retains_exact_bounded_response_provenance() -> None:
    retrieved_at = datetime(2026, 8, 10, 3, 0, tzinfo=UTC)
    client, transport = _snapshot_client(retrieved_at)

    fetched = client.fetch()

    assert fetched.retrieved_at == retrieved_at
    assert fetched.observation_date == date(2026, 8, 10)
    assert fetched.etag == '"snapshot-v1"'
    assert fetched.last_modified == "Mon, 10 Aug 2026 02:00:00 GMT"
    assert fetched.catalog.resolve(segment="NSE_EQ", symbol="RELIANCE").isin == (
        "INE002A01018"
    )
    assert len(fetched.compressed_sha256) == 64
    assert len(fetched.decompressed_sha256) == 64
    assert len(transport.requests) == 1


def test_snapshot_client_fails_closed_for_bad_responses_and_clock() -> None:
    with pytest.raises(ValueError):
        InstrumentSnapshotClientV1(StaticTransport(HttpResponse(200, b"")), clock=None)
    for response, clock in (
        (HttpResponse(503, b"provider secret"), lambda: datetime.now(UTC)),
        (HttpResponse(200, b"not-gzip"), lambda: datetime.now(UTC)),
        (HttpResponse(200, gzip.compress(b"[]")), lambda: "not-a-time"),
    ):
        with pytest.raises(InstrumentSnapshotUnavailableError) as error:
            InstrumentSnapshotClientV1(StaticTransport(response), clock=clock).fetch()
        assert "secret" not in str(error.value)
    oversized = HttpResponse(200, b"x" * 4_000_001)
    with pytest.raises(InstrumentSnapshotUnavailableError):
        InstrumentSnapshotClientV1(
            StaticTransport(oversized), clock=lambda: datetime.now(UTC)
        ).fetch()


def test_snapshot_client_enforces_decompressed_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(snapshot_module, "DEFAULT_MAX_CATALOG_DECOMPRESSED_BYTES", 10)
    response = HttpResponse(200, gzip.compress(b"[" + b" " * 10 + b"]"))
    with pytest.raises(InstrumentSnapshotUnavailableError):
        InstrumentSnapshotClientV1(
            StaticTransport(response), clock=lambda: datetime.now(UTC)
        ).fetch()


def test_snapshot_metadata_contract_rejects_path_and_header_drift() -> None:
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    fetched = client.fetch()
    with pytest.raises(ValueError):
        InstrumentSnapshotMetadataV1(
            1,
            "upstox-bod-nse",
            fetched.observation_date,
            fetched.retrieved_at,
            "a" * 64,
            fetched.compressed_sha256,
            fetched.decompressed_sha256,
            len(fetched.compressed_bytes),
            len(fetched.decompressed_bytes),
            "wrong/path",
            "wrong/sidecar",
            "\n",
            None,
        )
    with pytest.raises(ValueError):
        replace(fetched, observation_date=date(2026, 8, 9))


def test_canonical_snapshot_documents_reject_malformed_or_oversized_values() -> None:
    with pytest.raises(ValueError):
        snapshot_module._canonical_observation_bytes(
            (
                1,
                "source",
                date.today(),
                "not-a-time",
                "a" * 64,
                "b" * 64,
                1,
                1,
                "path",
                None,
                None,
            )
        )
    fetched, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    value = fetched.fetch()
    lease_metadata = snapshot_module.InstrumentSnapshotMetadataV1(
        1,
        "upstox-bod-nse",
        value.observation_date,
        value.retrieved_at,
        "a" * 64,
        value.compressed_sha256,
        value.decompressed_sha256,
        len(value.compressed_bytes),
        len(value.decompressed_bytes),
        f"instrument_snapshots/sha256={value.compressed_sha256}/snapshot.json.gz",
        f"instrument_snapshots/sha256={value.compressed_sha256}/observations/sha256={'a' * 64}.json",
        None,
        None,
    )
    valid_journal = snapshot_module._canonical_journal_bytes(lease_metadata)
    noncanonical = valid_journal.replace(b'"schema_version":1', b'"schema_version" : 1')
    with pytest.raises(InstrumentSnapshotCorruptError):
        snapshot_module._parse_canonical_journal(noncanonical)
    wrong_type = json.loads(valid_journal)
    wrong_type["schema_version"] = "1"
    with pytest.raises(InstrumentSnapshotCorruptError):
        snapshot_module._parse_canonical_journal(
            (json.dumps(wrong_type, separators=(",", ":")) + "\n").encode()
        )
    object.__setattr__(lease_metadata, "etag", "x" * 5000)
    with pytest.raises(ValueError):
        snapshot_module._canonical_journal_bytes(lease_metadata)
    with pytest.raises(ValueError):
        snapshot_module._canonical_observation_bytes(
            snapshot_module._metadata_without_digest(lease_metadata)
        )
    for malformed in (b"[]\n", b'{"schema_version":1,"schema_version":1}\n'):
        with pytest.raises(InstrumentSnapshotCorruptError):
            snapshot_module._parse_canonical_journal(malformed)


def test_no_clobber_publication_handles_races_and_reopen_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.lease is not None
    with lease_result.lease as lease, lease.root_operation(tmp_path) as operation:
        real_link = snapshot_module.os.link

        def raced_link(
            _src: str,
            dst: str,
            *,
            src_dir_fd: int,
            dst_dir_fd: int,
            follow_symlinks: bool,
        ) -> None:
            del src_dir_fd, follow_symlinks
            descriptor = os.open(
                dst,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=dst_dir_fd,
            )
            os.write(descriptor, b"expected")
            os.close(descriptor)
            raise OSError(errno.EEXIST, "raced")

        monkeypatch.setattr(snapshot_module.os, "link", raced_link)
        snapshot_module._publish_exact(
            operation, operation.descriptor, ".race.tmp", "race.final", b"expected"
        )

        def divergent_link(
            _src: str,
            dst: str,
            *,
            src_dir_fd: int,
            dst_dir_fd: int,
            follow_symlinks: bool,
        ) -> None:
            del src_dir_fd, follow_symlinks
            descriptor = os.open(
                dst,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=dst_dir_fd,
            )
            os.write(descriptor, b"wrong")
            os.close(descriptor)
            raise OSError(errno.EEXIST, "raced")

        monkeypatch.setattr(snapshot_module.os, "link", divergent_link)
        with pytest.raises(OSError):
            snapshot_module._publish_exact(
                operation,
                operation.descriptor,
                ".divergent.tmp",
                "divergent.final",
                b"expected",
            )
        monkeypatch.setattr(snapshot_module.os, "link", real_link)

        real_read = snapshot_module._read_bounded

        def corrupt_temp(parent_fd: int, name: str, limit: int) -> bytes:
            if name == ".corrupt.tmp":
                return b"wrong"
            return real_read(parent_fd, name, limit)

        monkeypatch.setattr(snapshot_module, "_read_bounded", corrupt_temp)
        with pytest.raises(InstrumentSnapshotCorruptError):
            snapshot_module._publish_exact(
                operation,
                operation.descriptor,
                ".corrupt.tmp",
                "corrupt.final",
                b"expected",
            )


def test_snapshot_store_retains_repeated_observations_and_resolves_offline(
    tmp_path: Path,
) -> None:
    first_client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    second_client, _ = _snapshot_client(datetime(2026, 8, 10, 4, 0, tzinfo=UTC))
    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.lease is not None
    with lease_result.lease as lease, DuckDBCatalog(tmp_path) as catalog:
        store = InstrumentSnapshotStoreV1(tmp_path, lease, catalog)
        first = store.retain(first_client.fetch())
        assert store.retain(first_client.fetch()) == first
        second = store.retain(second_client.fetch())
        resolved = store.resolve_equity(
            source="upstox-bod-nse",
            segment="NSE_EQ",
            symbol="RELIANCE",
            as_of=datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
        )

        assert first.compressed_sha256 == second.compressed_sha256
        assert first.observation_sha256 != second.observation_sha256
        assert resolved.metadata == second
        assert resolved.instrument.security_id == "INE002A01018"
        assert len(catalog.list_instrument_snapshots("upstox-bod-nse")) == 2


def test_snapshot_catalog_rejects_divergent_existing_row(tmp_path: Path) -> None:
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.lease is not None
    with lease_result.lease as lease, DuckDBCatalog(tmp_path) as catalog:
        metadata = InstrumentSnapshotStoreV1(tmp_path, lease, catalog).retain(
            client.fetch()
        )
        catalog.connection.execute(
            "UPDATE instrument_snapshots SET decompressed_sha256 = ?",
            ("0" * 64,),
        )
        with pytest.raises(CatalogConflictError, match="instrument snapshot conflicts"):
            catalog.save_instrument_snapshot(metadata)


def test_snapshot_store_refuses_a_mismatched_sidecar(tmp_path: Path) -> None:
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.lease is not None
    with lease_result.lease as lease, DuckDBCatalog(tmp_path) as catalog:
        store = InstrumentSnapshotStoreV1(tmp_path, lease, catalog)
        metadata = store.retain(client.fetch())
        sidecar = tmp_path / metadata.relative_metadata_path
        sidecar.write_bytes(b"{}\n")
        with pytest.raises(InstrumentSnapshotCorruptError):
            store.resolve_equity(
                source=metadata.source,
                segment="NSE_EQ",
                symbol="RELIANCE",
                as_of=datetime(2026, 8, 10, 3, 30, tzinfo=UTC),
            )


def test_snapshot_store_rejects_missing_ambiguous_and_unsafe_local_evidence(
    tmp_path: Path,
) -> None:
    first_client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.lease is not None
    with lease_result.lease as lease, DuckDBCatalog(tmp_path) as catalog:
        store = InstrumentSnapshotStoreV1(tmp_path, lease, catalog)
        with pytest.raises(InstrumentSnapshotNotFoundError):
            store.resolve_equity(
                source="upstox-bod-nse",
                segment="NSE_EQ",
                symbol="RELIANCE",
                as_of=datetime(2026, 8, 10, 3, 30, tzinfo=UTC),
            )
        with pytest.raises(InstrumentSnapshotCorruptError):
            store.retain(object())  # type: ignore[arg-type]
        fetched = first_client.fetch()
        bad = replace(fetched)
        object.__setattr__(bad, "compressed_sha256", "0" * 64)
        with pytest.raises(InstrumentSnapshotCorruptError):
            store.retain(bad)
        metadata = store.retain(fetched)
        temp = (
            tmp_path / metadata.relative_object_path
        ).parent / ".snapshot.json.gz.tmp"
        temp.write_text("unsafe")
        os.chmod(temp, 0o644)
        later = replace(
            fetched,
            retrieved_at=datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        )
        with pytest.raises(InstrumentSnapshotCorruptError):
            store.retain(later)


def test_snapshot_store_cleans_safe_temp_and_rejects_object_drift(
    tmp_path: Path,
) -> None:
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    fetched = client.fetch()
    object_dir = (
        tmp_path / "instrument_snapshots" / f"sha256={fetched.compressed_sha256}"
    )
    object_dir.mkdir(parents=True)
    temp = object_dir / ".snapshot.json.gz.tmp"
    temp.write_bytes(b"abandoned")
    os.chmod(temp, 0o600)
    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.lease is not None
    with lease_result.lease as lease, DuckDBCatalog(tmp_path) as catalog:
        store = InstrumentSnapshotStoreV1(tmp_path, lease, catalog)
        metadata = store.retain(fetched)
        assert not temp.exists()
        (tmp_path / metadata.relative_object_path).write_bytes(b"drift")
        with pytest.raises(InstrumentSnapshotCorruptError):
            store.resolve_equity(
                source=metadata.source,
                segment="NSE_EQ",
                symbol="RELIANCE",
                as_of=datetime(2026, 8, 10, 3, 30, tzinfo=UTC),
            )


def test_snapshot_store_refuses_symlinked_snapshot_directory(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "instrument_snapshots").symlink_to(outside, target_is_directory=True)
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.lease is not None
    with (
        lease_result.lease as lease,
        DuckDBCatalog(tmp_path) as catalog,
        pytest.raises(InstrumentSnapshotCorruptError),
    ):
        InstrumentSnapshotStoreV1(tmp_path, lease, catalog).retain(client.fetch())
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("unsafe_kind", ("mode", "oversized_journal"))
def test_snapshot_store_refuses_unsafe_root_evidence(
    tmp_path: Path, unsafe_kind: str
) -> None:
    snapshot_root = tmp_path / "instrument_snapshots"
    snapshot_root.mkdir()
    if unsafe_kind == "mode":
        os.chmod(snapshot_root, 0o777)  # noqa: S103 - deliberate unsafe fixture
    else:
        (snapshot_root / "pending-observation-v1.json").write_bytes(b"x" * 4097)
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    source = NoFetchSnapshotSource()
    report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(_schedule_input()),
        source,
    ).prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            tmp_path,
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        )
    )
    assert source.calls == 0
    assert report.failure_code is PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_CORRUPT


def test_snapshot_store_refuses_divergent_existing_object(tmp_path: Path) -> None:
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    fetched = client.fetch()
    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.lease is not None
    with lease_result.lease as lease, DuckDBCatalog(tmp_path) as catalog:
        store = InstrumentSnapshotStoreV1(tmp_path, lease, catalog)
        metadata = store.retain(fetched)
        (tmp_path / metadata.relative_object_path).write_bytes(b"divergent")
        with pytest.raises(InstrumentSnapshotCorruptError):
            store.retain(fetched)


@pytest.mark.parametrize("temp_state", ("none", "safe", "unsafe"))
def test_preparation_recovers_pending_observation_before_fetch(
    tmp_path: Path, temp_state: str
) -> None:
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    fetched = client.fetch()
    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.lease is not None
    with (
        lease_result.lease as lease,
        DuckDBCatalog(tmp_path) as catalog,
        pytest.raises(InstrumentSnapshotCorruptError),
    ):
        InstrumentSnapshotStoreV1(
            tmp_path, lease, FailingSnapshotCatalog(catalog)
        ).retain(fetched)
        assert catalog.list_instrument_snapshots("upstox-bod-nse") == ()
    journal = tmp_path / "instrument_snapshots" / "pending-observation-v1.json"
    assert journal.is_file()
    if temp_state != "none":
        temp = (
            tmp_path
            / "instrument_snapshots"
            / f"sha256={fetched.compressed_sha256}"
            / ".snapshot.json.gz.tmp"
        )
        temp.write_bytes(b"abandoned")
        os.chmod(temp, 0o644 if temp_state == "unsafe" else 0o600)

    source = NoFetchSnapshotSource()
    report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(_schedule_input()),
        source,
    ).prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            tmp_path,
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        )
    )

    assert source.calls == 0
    if temp_state == "unsafe":
        assert (
            report.failure_code is PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_CORRUPT
        )
        assert journal.exists()
    else:
        assert report.outcome is PreparationOutcomeV1.SUCCEEDED
        assert report.prepared is not None
        assert report.prepared.snapshot_attempt_count == 0
        assert not journal.exists()


@pytest.mark.parametrize("has_final_journal", (False, True))
@pytest.mark.parametrize("temp_mode", (0o600, 0o644))
def test_preparation_preflights_fixed_journal_temp_before_fetch(
    tmp_path: Path, has_final_journal: bool, temp_mode: int
) -> None:
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    snapshot_root = tmp_path / "instrument_snapshots"
    if has_final_journal:
        fetched = client.fetch()
        lease_result = StorageRootLease.try_acquire(tmp_path)
        assert lease_result.lease is not None
        with (
            lease_result.lease as lease,
            DuckDBCatalog(tmp_path) as catalog,
            pytest.raises(InstrumentSnapshotCorruptError),
        ):
            InstrumentSnapshotStoreV1(
                tmp_path, lease, FailingSnapshotCatalog(catalog)
            ).retain(fetched)
    else:
        snapshot_root.mkdir()
    journal_temp = snapshot_root / ".pending-observation-v1.json.tmp"
    journal_temp.write_bytes(b"abandoned")
    os.chmod(journal_temp, temp_mode)
    source = (
        NoFetchSnapshotSource()
        if has_final_journal or temp_mode != 0o600
        else CountingSnapshotSource(client)
    )

    report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(_schedule_input()),
        source,
    ).prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            tmp_path,
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        )
    )

    if temp_mode != 0o600:
        assert source.calls == 0
        assert journal_temp.exists()
        assert (
            report.failure_code is PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_CORRUPT
        )
    else:
        assert not journal_temp.exists()
        assert source.calls == (0 if has_final_journal else 1)
        assert report.outcome is PreparationOutcomeV1.SUCCEEDED


@pytest.mark.parametrize("leave_sidecar", (False, True))
def test_pending_journal_handles_missing_object_without_fetching_blindly(
    tmp_path: Path, leave_sidecar: bool
) -> None:
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    fetched = client.fetch()
    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.lease is not None
    with (
        lease_result.lease as lease,
        DuckDBCatalog(tmp_path) as catalog,
        pytest.raises(InstrumentSnapshotCorruptError),
    ):
        InstrumentSnapshotStoreV1(
            tmp_path, lease, FailingSnapshotCatalog(catalog)
        ).retain(fetched)
    object_path = (
        tmp_path
        / "instrument_snapshots"
        / f"sha256={fetched.compressed_sha256}"
        / "snapshot.json.gz"
    )
    object_path.unlink()
    if not leave_sidecar:
        for sidecar in object_path.parent.joinpath("observations").iterdir():
            sidecar.unlink()

    source = (
        NoFetchSnapshotSource() if leave_sidecar else CountingSnapshotSource(client)
    )
    report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(_schedule_input()),
        source,
    ).prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            tmp_path,
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        )
    )
    if leave_sidecar:
        assert source.calls == 0
        assert (
            report.failure_code is PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_CORRUPT
        )
    else:
        assert source.calls == 1
        assert report.outcome is PreparationOutcomeV1.SUCCEEDED


def test_pending_recovery_rejects_corrupt_journal_before_fetch(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "instrument_snapshots"
    snapshot_root.mkdir()
    (snapshot_root / "pending-observation-v1.json").write_bytes(b"{}\n")
    source = NoFetchSnapshotSource()
    report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(_schedule_input()),
        source,
    ).prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            tmp_path,
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        )
    )
    assert source.calls == 0
    assert report.failure_code is PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_CORRUPT


def test_snapshot_store_rejects_ambiguous_latest_observations(tmp_path: Path) -> None:
    retrieved_at = datetime(2026, 8, 10, 3, 0, tzinfo=UTC)
    first, _ = _snapshot_client(retrieved_at)
    changed = dict(RELIANCE, name="RELIANCE INDUSTRIES LTD")
    body = gzip.compress(json.dumps([changed], separators=(",", ":")).encode())
    second = InstrumentSnapshotClientV1(
        StaticTransport(HttpResponse(200, body)), clock=lambda: retrieved_at
    )
    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.lease is not None
    with lease_result.lease as lease, DuckDBCatalog(tmp_path) as catalog:
        store = InstrumentSnapshotStoreV1(tmp_path, lease, catalog)
        store.retain(first.fetch())
        store.retain(second.fetch())
        with pytest.raises(InstrumentSnapshotCorruptError):
            store.resolve_equity(
                source="upstox-bod-nse",
                segment="NSE_EQ",
                symbol="RELIANCE",
                as_of=retrieved_at,
            )


def test_invalid_schedule_fails_before_lock_or_storage_mutation(tmp_path: Path) -> None:
    policy = PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE")
    schedule_source = StaticScheduleSource(ValueError("invalid schedule"))
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    snapshot_source = CountingSnapshotSource(client)
    service = DownloadPreparationServiceV1(policy, schedule_source, snapshot_source)

    report = service.prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            tmp_path,
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        )
    )

    assert report.outcome is PreparationOutcomeV1.INSUFFICIENT_EVIDENCE
    assert report.failure_code is PreparationFailureCodeV1.SCHEDULE_UNAVAILABLE
    assert list(tmp_path.iterdir()) == []
    assert snapshot_source.calls == 0


def test_preparation_rejects_before_sources_and_reports_lock_contention(
    tmp_path: Path,
) -> None:
    schedule_source = StaticScheduleSource(_schedule_input())
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    snapshot_source = CountingSnapshotSource(client)
    service = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        schedule_source,
        snapshot_source,
    )
    assert (
        service.prepare(object()).failure_code is PreparationFailureCodeV1.INVALID_INPUT
    )
    request = DownloadPreparationRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 1),
        date(2026, 7, 31),
        tmp_path,
        datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
    )
    object.__setattr__(request, "symbol", "TCS")
    assert (
        service.prepare(request).failure_code
        is PreparationFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT
    )
    object.__setattr__(request, "symbol", "RELIANCE")
    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.lease is not None
    with lease_result.lease:
        assert (
            service.prepare(request).failure_code
            is PreparationFailureCodeV1.STORAGE_UNAVAILABLE
        )


def test_admission_precedes_root_io_and_month_bound_is_in_memory(
    tmp_path: Path,
) -> None:
    missing_root = tmp_path / "missing"
    admitted_twelve = DownloadPreparationRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2025, 8, 1),
        date(2026, 7, 31),
        missing_root,
        datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
    )
    with pytest.raises(ValueError):
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2025, 7, 1),
            date(2026, 7, 31),
            missing_root,
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        )
    request = replace(admitted_twelve, symbol="TCS")
    schedule_source = StaticScheduleSource(AssertionError("source must not run"))
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        schedule_source,
        CountingSnapshotSource(client),
    ).prepare(request)
    assert (
        report.failure_code is PreparationFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT
    )
    assert schedule_source.calls == 0
    assert not missing_root.exists()


@pytest.mark.parametrize("forbidden", ("~", "*", "[x]", "?"))
def test_preparation_request_rejects_tilde_and_glob_storage_roots(
    forbidden: str,
) -> None:
    with pytest.raises(ValueError):
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            Path("/") / "synthetic-root" / forbidden,
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        )


def test_preparation_maps_snapshot_unavailability_without_leaking_response(
    tmp_path: Path,
) -> None:
    unavailable = InstrumentSnapshotClientV1(
        StaticTransport(HttpResponse(503, b"private response")),
        clock=lambda: datetime(2026, 8, 10, 3, 0, tzinfo=UTC),
    )
    service = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(_schedule_input()),
        CountingSnapshotSource(unavailable),
    )
    report = service.prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            tmp_path,
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        )
    )
    assert report.outcome is PreparationOutcomeV1.UNAVAILABLE
    assert (
        report.failure_code is PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE
    )
    assert report.prepared is None


def test_preparation_contracts_and_schedule_retention_failure_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    schedule = _schedule()
    with pytest.raises(ValueError):
        AuthoritativeScheduleInputV1(schedule, b"not-canonical")
    with pytest.raises(ValueError):
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2021, 12, 31),
            date(2021, 12, 31),
            tmp_path,
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        )
    with pytest.raises(ValueError):
        DownloadPreparationReportV1(
            PreparationOutcomeV1.SUCCEEDED,
            PreparationFailureCodeV1.NONE,
            None,
        )
    with pytest.raises(ValueError):
        DownloadPreparationReportV1(
            PreparationOutcomeV1.FAILED,
            PreparationFailureCodeV1.NONE,
            None,
        )

    class FailingScheduleStore:
        def __init__(self, *_: object) -> None:
            pass

        def retain(self, *_: object, **__: object) -> ScheduleEvidenceResult:
            return ScheduleEvidenceResult(
                ScheduleOutcome.FAILED,
                ScheduleFailureCode.SCHEDULE_UNSUPPORTED,
                None,
                None,
                None,
                message="schedule evidence unsupported",
            )

    monkeypatch.setattr(
        preparation_module, "ScheduleEvidenceStore", FailingScheduleStore
    )
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(_schedule_input()),
        CountingSnapshotSource(client),
    ).prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            tmp_path,
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        )
    )
    assert report.failure_code is PreparationFailureCodeV1.SCHEDULE_UNAVAILABLE


def test_preparation_rejects_non_contract_schedule_and_future_snapshot(
    tmp_path: Path,
) -> None:
    future_client, _ = _snapshot_client(datetime(2026, 8, 10, 5, 0, tzinfo=UTC))
    invalid_source = StaticScheduleSource(_schedule_input())
    invalid_source.value = object()  # type: ignore[assignment]
    request = DownloadPreparationRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 1),
        date(2026, 7, 31),
        tmp_path,
        datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
    )
    invalid_report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        invalid_source,
        CountingSnapshotSource(future_client),
    ).prepare(request)
    assert invalid_report.failure_code is PreparationFailureCodeV1.SCHEDULE_UNAVAILABLE
    future_report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(_schedule_input()),
        CountingSnapshotSource(future_client),
    ).prepare(request)
    assert (
        future_report.failure_code
        is PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE
    )


def test_preparation_accepts_only_fresh_same_day_snapshot_with_trusted_clock(
    tmp_path: Path,
) -> None:
    invocation = datetime(2026, 8, 10, 4, 0, tzinfo=UTC)
    fetched_at = invocation + timedelta(seconds=1)
    observed_at = fetched_at + timedelta(seconds=1)
    client, _ = _snapshot_client(fetched_at)

    class PostFetchClock:
        def now(self) -> datetime:
            return observed_at

    report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(_schedule_input()),
        CountingSnapshotSource(client),
        clock=PostFetchClock(),
    ).prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            tmp_path,
            invocation,
        )
    )

    assert report.outcome is PreparationOutcomeV1.SUCCEEDED
    assert report.prepared is not None
    assert report.prepared.snapshot_retrieved_at == fetched_at


@pytest.mark.parametrize(
    ("invocation", "fetched_at", "observed_at"),
    (
        (
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
            datetime(2026, 8, 10, 4, 0, 2, tzinfo=UTC),
            datetime(2026, 8, 10, 4, 0, 1, tzinfo=UTC),
        ),
        (
            datetime(2026, 8, 10, 18, 29, tzinfo=UTC),
            datetime(2026, 8, 10, 18, 31, tzinfo=UTC),
            datetime(2026, 8, 10, 18, 32, tzinfo=UTC),
        ),
    ),
)
def test_preparation_rejects_untrusted_or_midnight_crossing_fresh_snapshot(
    tmp_path: Path,
    invocation: datetime,
    fetched_at: datetime,
    observed_at: datetime,
) -> None:
    client, _ = _snapshot_client(fetched_at)

    class PostFetchClock:
        def now(self) -> datetime:
            return observed_at

    report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(_schedule_input()),
        CountingSnapshotSource(client),
        clock=PostFetchClock(),
    ).prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            tmp_path,
            invocation,
        )
    )

    assert report.outcome is PreparationOutcomeV1.UNAVAILABLE
    assert (
        report.failure_code is PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE
    )


@pytest.mark.parametrize("observed_at", (object(), datetime(2026, 8, 10, 4, 0)))
def test_preparation_rejects_invalid_post_fetch_clock(
    tmp_path: Path, observed_at: object
) -> None:
    invocation = datetime(2026, 8, 10, 4, 0, tzinfo=UTC)
    client, _ = _snapshot_client(invocation + timedelta(seconds=1))

    class InvalidPostFetchClock:
        def now(self) -> object:
            return observed_at

    report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(_schedule_input()),
        CountingSnapshotSource(client),
        clock=InvalidPostFetchClock(),  # type: ignore[arg-type]
    ).prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            tmp_path,
            invocation,
        )
    )

    assert report.outcome is PreparationOutcomeV1.UNAVAILABLE
    assert (
        report.failure_code is PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE
    )


@pytest.mark.parametrize(
    ("records", "expected"),
    (
        ([], PreparationFailureCodeV1.INSTRUMENT_NOT_FOUND),
        ([RELIANCE, RELIANCE], PreparationFailureCodeV1.INSTRUMENT_AMBIGUOUS),
    ),
)
def test_preparation_preserves_instrument_resolution_failures(
    tmp_path: Path,
    records: list[dict[str, object]],
    expected: PreparationFailureCodeV1,
) -> None:
    body = gzip.compress(json.dumps(records, separators=(",", ":")).encode())
    client = InstrumentSnapshotClientV1(
        StaticTransport(HttpResponse(200, body)),
        clock=lambda: datetime(2026, 8, 10, 3, 0, tzinfo=UTC),
    )
    report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(_schedule_input()),
        CountingSnapshotSource(client),
    ).prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            tmp_path,
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        )
    )
    assert report.outcome is PreparationOutcomeV1.REJECTED
    assert report.failure_code is expected


def test_preparation_rejects_non_nse_equity_identity_as_corrupt(
    tmp_path: Path,
) -> None:
    wrong_exchange = dict(RELIANCE, exchange="BSE")
    body = gzip.compress(json.dumps([wrong_exchange], separators=(",", ":")).encode())
    client = InstrumentSnapshotClientV1(
        StaticTransport(HttpResponse(200, body)),
        clock=lambda: datetime(2026, 8, 10, 3, 0, tzinfo=UTC),
    )
    report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(_schedule_input()),
        CountingSnapshotSource(client),
    ).prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            tmp_path,
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        )
    )
    assert report.outcome is PreparationOutcomeV1.FAILED
    assert report.failure_code is PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_CORRUPT


def test_preparation_retains_schedule_then_reuses_snapshot_without_fetch(
    tmp_path: Path,
) -> None:
    policy = PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE")
    schedule_source = StaticScheduleSource(_schedule_input())
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    snapshot_source = CountingSnapshotSource(client)
    service = DownloadPreparationServiceV1(policy, schedule_source, snapshot_source)
    request = DownloadPreparationRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 1),
        date(2026, 7, 31),
        tmp_path,
        datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
    )

    first = service.prepare(request)
    second = service.prepare(request)

    assert first.outcome is PreparationOutcomeV1.SUCCEEDED
    assert second.outcome is PreparationOutcomeV1.SUCCEEDED
    assert first.prepared is not None and second.prepared is not None
    assert first.prepared.instrument == second.prepared.instrument
    assert first.prepared.snapshot_attempt_count == 1
    assert second.prepared.snapshot_attempt_count == 0
    assert snapshot_source.calls == 1
    assert (tmp_path / ".ingestion.lock").exists()
    assert (tmp_path / "catalog.duckdb").exists()
    assert any((tmp_path / "calendar-schedules").rglob("*.json"))


def test_preparation_refreshes_a_valid_stale_snapshot_once(tmp_path: Path) -> None:
    stale_client, _ = _snapshot_client(datetime(2026, 8, 9, 3, 0, tzinfo=UTC))
    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.lease is not None
    with lease_result.lease as lease, DuckDBCatalog(tmp_path) as catalog:
        InstrumentSnapshotStoreV1(tmp_path, lease, catalog).retain(stale_client.fetch())
    current_client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    source = CountingSnapshotSource(current_client)
    report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(_schedule_input()),
        source,
    ).prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 7, 31),
            tmp_path,
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        )
    )
    assert report.outcome is PreparationOutcomeV1.SUCCEEDED
    assert source.calls == 1


@pytest.mark.parametrize(
    ("from_date", "to_date", "invocation_time"),
    (
        (
            date(2025, 12, 1),
            date(2025, 12, 31),
            datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
        ),
        (
            date(2026, 7, 1),
            date(2026, 7, 31),
            datetime(2026, 7, 31, 23, 0, tzinfo=UTC),
        ),
    ),
)
def test_preparation_rejects_incomplete_or_future_schedule_evidence(
    tmp_path: Path,
    from_date: date,
    to_date: date,
    invocation_time: datetime,
) -> None:
    client, _ = _snapshot_client(datetime(2026, 8, 10, 3, 0, tzinfo=UTC))
    report = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        StaticScheduleSource(_schedule_input()),
        CountingSnapshotSource(client),
    ).prepare(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            from_date,
            to_date,
            tmp_path,
            invocation_time,
        )
    )
    assert report.failure_code is PreparationFailureCodeV1.SCHEDULE_UNAVAILABLE
    assert list(tmp_path.iterdir()) == []
