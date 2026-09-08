from __future__ import annotations

import contextlib
import hashlib
import json
import os
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.schedule_evidence as schedule_module
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    MAX_SCHEDULE_BYTES,
    SCHEDULE_SCHEMA_VERSION_V3,
    ExpectedSessionSchedule,
    ScheduleEvidenceResult,
    ScheduleEvidenceStore,
    ScheduleFailureCode,
    ScheduleOutcome,
    ScheduleSession,
    canonical_schedule_bytes,
    parse_canonical_schedule_bytes,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)


def _session(**overrides: object) -> ScheduleSession:
    values: dict[str, object] = {
        "trade_date": date(2026, 1, 2),
        "open_at": datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        "close_at": datetime(2026, 1, 2, 10, tzinfo=UTC),
        "kind": "regular",
    }
    values.update(overrides)
    return ScheduleSession(**values)  # type: ignore[arg-type]


def _schedule(**overrides: object) -> ExpectedSessionSchedule:
    values: dict[str, object] = {
        "schema_version": 1,
        "source": "nse",
        "source_release": "2026-01",
        "as_of": datetime(2026, 2, 1, tzinfo=UTC),
        "timezone": "Asia/Kolkata",
        "covered_from": date(2026, 1, 1),
        "covered_to": date(2026, 1, 31),
        "sessions": (_session(),),
    }
    values.update(overrides)
    return ExpectedSessionSchedule(**values)  # type: ignore[arg-type]


def _store(tmp_path: Path) -> tuple[ScheduleEvidenceStore, StorageRootLease]:
    result = StorageRootLease.try_acquire(tmp_path)
    assert result.outcome is LeaseOutcome.ACQUIRED
    assert result.lease is not None
    return ScheduleEvidenceStore(tmp_path, result.lease), result.lease


def _close(lease: StorageRootLease) -> None:
    lease.close()


def _path(root: Path, digest: str) -> Path:
    return root / "calendar-schedules" / "sha256" / f"{digest}.json"


def test_schedule_serialization_is_exact_and_digest_is_lowercase_sha256() -> None:
    schedule = _schedule()
    expected = (
        b'{"as_of":"2026-02-01T00:00:00.000000Z","covered_from":"2026-01-01",'
        b'"covered_to":"2026-01-31","schema_version":1,"sessions":[{"close_at":'
        b'"2026-01-02T10:00:00.000000Z","kind":"regular","open_at":"2026-01-02T03:'
        b'45:00.000000Z","trade_date":"2026-01-02"}],"source":"nse","source_release":'
        b'"2026-01","timezone":"Asia/Kolkata"}'
    )
    assert canonical_schedule_bytes(schedule) == expected
    assert schedule_digest(schedule) == hashlib.sha256(expected).hexdigest()
    assert schedule_digest(schedule) == schedule_digest(schedule).lower()


def test_v3_retains_and_round_trips_one_explicit_planned_current_session() -> None:
    schedule = ExpectedSessionSchedule(
        schema_version=SCHEDULE_SCHEMA_VERSION_V3,
        source="authoritative-nse-calendar",
        source_release="2026-08-11T09:00:00+05:30",
        as_of=datetime(2026, 8, 11, 3, 30, tzinfo=UTC),
        timezone="Asia/Kolkata",
        covered_from=date(2026, 8, 10),
        covered_to=date(2026, 8, 11),
        sessions=(
            ScheduleSession(
                date(2026, 8, 10),
                datetime(2026, 8, 10, 3, 45, tzinfo=UTC),
                datetime(2026, 8, 10, 10, 0, tzinfo=UTC),
                "REGULAR",
            ),
            ScheduleSession(
                date(2026, 8, 11),
                datetime(2026, 8, 11, 3, 45, tzinfo=UTC),
                datetime(2026, 8, 11, 10, 0, tzinfo=UTC),
                "REGULAR",
            ),
        ),
        closures=(),
    )

    encoded = canonical_schedule_bytes(schedule)

    assert parse_canonical_schedule_bytes(encoded) == schedule
    assert b'"schema_version":3' in encoded


def test_v2_still_rejects_a_session_that_has_not_closed_at_as_of() -> None:
    with pytest.raises(ValueError):
        ExpectedSessionSchedule(
            schema_version=2,
            source="authoritative-nse-calendar",
            source_release="release",
            as_of=datetime(2026, 8, 11, 3, 30, tzinfo=UTC),
            timezone="Asia/Kolkata",
            covered_from=date(2026, 8, 11),
            covered_to=date(2026, 8, 11),
            sessions=(
                ScheduleSession(
                    date(2026, 8, 11),
                    datetime(2026, 8, 11, 3, 45, tzinfo=UTC),
                    datetime(2026, 8, 11, 10, 0, tzinfo=UTC),
                    "REGULAR",
                ),
            ),
            closures=(),
        )


def test_v3_rejects_a_future_dated_session() -> None:
    with pytest.raises(ValueError):
        ExpectedSessionSchedule(
            schema_version=SCHEDULE_SCHEMA_VERSION_V3,
            source="authoritative-nse-calendar",
            source_release="release",
            as_of=datetime(2026, 8, 11, 3, 30, tzinfo=UTC),
            timezone="Asia/Kolkata",
            covered_from=date(2026, 8, 10),
            covered_to=date(2026, 8, 12),
            sessions=(
                ScheduleSession(
                    date(2026, 8, 12),
                    datetime(2026, 8, 12, 3, 45, tzinfo=UTC),
                    datetime(2026, 8, 12, 10, 0, tzinfo=UTC),
                    "FUTURE",
                ),
            ),
            closures=(),
        )


def test_schedule_models_and_success_result_are_immutable() -> None:
    schedule = _schedule()
    with pytest.raises(FrozenInstanceError):
        schedule.source = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        schedule.sessions[0].kind = "special"  # type: ignore[misc]

    result = ScheduleEvidenceResult(
        ScheduleOutcome.RESOLVED,
        ScheduleFailureCode.NONE,
        schedule,
        canonical_schedule_bytes(schedule),
        schedule_digest(schedule),
        f"calendar-schedules/sha256/{schedule_digest(schedule)}.json",
    )
    with pytest.raises(FrozenInstanceError):
        result.outcome = ScheduleOutcome.FAILED  # type: ignore[misc]


def test_first_publish_uses_exact_content_addressed_path_and_reads_back(
    tmp_path: Path,
) -> None:
    store, lease = _store(tmp_path)
    try:
        schedule = _schedule()
        digest = schedule_digest(schedule)
        result = store.retain(schedule)
        assert result.outcome is ScheduleOutcome.RETAINED
        assert result.failure_code is ScheduleFailureCode.NONE
        assert result.schedule == schedule
        assert result.canonical_bytes == canonical_schedule_bytes(schedule)
        assert result.digest == digest
        assert _path(tmp_path, digest).read_bytes() == result.canonical_bytes
        assert result.relative_path == f"calendar-schedules/sha256/{digest}.json"
    finally:
        _close(lease)


def test_identical_restore_and_lookup_are_idempotent(tmp_path: Path) -> None:
    store, lease = _store(tmp_path)
    try:
        schedule = _schedule()
        digest = schedule_digest(schedule)
        first = store.retain(schedule)
        object_path = _path(tmp_path, digest)
        object_path.unlink()
        restored = store.resolve(digest, supplied_bytes=first.canonical_bytes)
        looked_up = store.resolve(digest)
        assert restored.outcome is ScheduleOutcome.RETAINED
        assert looked_up.outcome is ScheduleOutcome.RESOLVED
        assert looked_up.schedule == schedule
        assert object_path.read_bytes() == first.canonical_bytes
    finally:
        _close(lease)


def test_missing_object_without_supplied_bytes_is_sanitized_failure(
    tmp_path: Path,
) -> None:
    store, lease = _store(tmp_path)
    try:
        result = store.resolve("a" * 64)
        assert result.outcome is ScheduleOutcome.FAILED
        assert result.failure_code is ScheduleFailureCode.SCHEDULE_UNSUPPORTED
        assert result.schedule is None
        assert result.canonical_bytes is None
        assert result.relative_path is None
        assert "a" * 64 not in result.message
        assert result.message == "schedule evidence unsupported"
    finally:
        _close(lease)


def test_present_different_bytes_are_refused_without_clobber(tmp_path: Path) -> None:
    store, lease = _store(tmp_path)
    try:
        original = _schedule(source_release="original")
        requested = _schedule(source_release="requested")
        digest = schedule_digest(requested)
        object_path = _path(tmp_path, digest)
        object_path.parent.mkdir(parents=True)
        retained = canonical_schedule_bytes(original)
        object_path.write_bytes(retained)
        result = store.resolve(
            digest, supplied_bytes=canonical_schedule_bytes(requested)
        )
        assert result.outcome is ScheduleOutcome.FAILED
        assert result.failure_code is ScheduleFailureCode.SCHEDULE_UNSUPPORTED
        assert object_path.read_bytes() == retained
    finally:
        _close(lease)


@pytest.mark.parametrize("bad_bytes", [b"{}", b' {"schema_version":1}'])
def test_present_corrupt_or_noncanonical_evidence_is_refused_without_replacement(
    tmp_path: Path, bad_bytes: bytes
) -> None:
    schedule = _schedule()
    digest = schedule_digest(schedule)
    store, lease = _store(tmp_path)
    try:
        object_path = _path(tmp_path, digest)
        object_path.parent.mkdir(parents=True)
        object_path.write_bytes(bad_bytes)
        result = store.resolve(
            digest, supplied_bytes=canonical_schedule_bytes(schedule)
        )
        assert result.outcome is ScheduleOutcome.FAILED
        assert result.failure_code is ScheduleFailureCode.SCHEDULE_UNSUPPORTED
        assert object_path.read_bytes() == bad_bytes
    finally:
        _close(lease)


@pytest.mark.parametrize("digest", ["A" * 64, "a" * 63, "a" * 65, "../" + "a" * 62])
def test_digest_path_shape_is_rejected(tmp_path: Path, digest: str) -> None:
    store, lease = _store(tmp_path)
    try:
        result = store.resolve(digest)
        assert result.outcome is ScheduleOutcome.FAILED
        assert result.failure_code is ScheduleFailureCode.SCHEDULE_UNSUPPORTED
    finally:
        _close(lease)


@pytest.mark.parametrize("node", ["symlink", "directory", "fifo"])
def test_present_nonregular_or_symlink_evidence_is_rejected_without_following(
    tmp_path: Path, node: str
) -> None:
    if node == "fifo" and not hasattr(os, "mkfifo"):
        pytest.skip("POSIX FIFO required")
    schedule = _schedule()
    digest = schedule_digest(schedule)
    store, lease = _store(tmp_path)
    try:
        object_path = _path(tmp_path, digest)
        object_path.parent.mkdir(parents=True)
        if node == "symlink":
            target = tmp_path / "outside"
            target.write_bytes(b"private")
            object_path.symlink_to(target)
        elif node == "directory":
            object_path.mkdir()
        else:
            os.mkfifo(object_path)
        result = store.resolve(digest)
        assert result.outcome is ScheduleOutcome.FAILED
        assert result.failure_code is ScheduleFailureCode.SCHEDULE_UNSUPPORTED
        assert object_path.exists() or object_path.is_symlink()
    finally:
        _close(lease)


def test_digest_mismatch_is_rejected_without_replacement(tmp_path: Path) -> None:
    schedule = _schedule()
    other = _schedule(source_release="other")
    digest = schedule_digest(schedule)
    store, lease = _store(tmp_path)
    try:
        object_path = _path(tmp_path, digest)
        object_path.parent.mkdir(parents=True)
        other_bytes = canonical_schedule_bytes(other)
        object_path.write_bytes(other_bytes)
        result = store.resolve(digest)
        assert result.outcome is ScheduleOutcome.FAILED
        assert result.failure_code is ScheduleFailureCode.SCHEDULE_UNSUPPORTED
        assert object_path.read_bytes() == other_bytes
    finally:
        _close(lease)


def _schedule_with_byte_size(target: int) -> ExpectedSessionSchedule:
    baseline = _schedule(source_release="x")
    source_length = target - len(canonical_schedule_bytes(baseline)) + 1
    return _schedule(source_release="x" * source_length)


def test_exact_one_million_byte_boundary_is_accepted(tmp_path: Path) -> None:
    schedule = _schedule_with_byte_size(MAX_SCHEDULE_BYTES)
    assert len(canonical_schedule_bytes(schedule)) == MAX_SCHEDULE_BYTES
    store, lease = _store(tmp_path)
    try:
        result = store.retain(schedule)
        assert result.outcome is ScheduleOutcome.RETAINED
    finally:
        _close(lease)


def test_one_byte_over_schedule_ceiling_is_rejected_without_object(
    tmp_path: Path,
) -> None:
    schedule = _schedule_with_byte_size(MAX_SCHEDULE_BYTES + 1)
    assert len(canonical_schedule_bytes(schedule)) == MAX_SCHEDULE_BYTES + 1
    store, lease = _store(tmp_path)
    try:
        result = store.retain(schedule)
        assert result.outcome is ScheduleOutcome.FAILED
        assert result.failure_code is ScheduleFailureCode.SCHEDULE_UNSUPPORTED
        assert not (tmp_path / "calendar-schedules").exists()
    finally:
        _close(lease)


def test_invalid_schedule_shape_is_typed_failure_and_not_published(
    tmp_path: Path,
) -> None:
    invalid = _schedule()
    object.__setattr__(invalid, "timezone", "UTC")
    store, lease = _store(tmp_path)
    try:
        result = store.retain(invalid)
        assert result.outcome is ScheduleOutcome.FAILED
        assert result.failure_code is ScheduleFailureCode.SCHEDULE_UNSUPPORTED
        assert not (tmp_path / "calendar-schedules").exists()
    finally:
        _close(lease)


def test_fsync_failure_is_sanitized_and_does_not_report_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, lease = _store(tmp_path)
    try:
        monkeypatch.setattr(
            schedule_module.os,
            "fsync",
            lambda _descriptor: (_ for _ in ()).throw(OSError("private fsync")),
        )
        result = store.retain(_schedule())
        assert result.outcome is ScheduleOutcome.FAILED
        assert result.failure_code is ScheduleFailureCode.SCHEDULE_UNSUPPORTED
        assert result.message == "schedule evidence unsupported"
    finally:
        _close(lease)


def test_atomic_link_failure_is_sanitized_and_leaves_no_final_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, lease = _store(tmp_path)
    try:
        monkeypatch.setattr(
            schedule_module.os,
            "link",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("private link")),
        )
        result = store.retain(_schedule())
        assert result.outcome is ScheduleOutcome.FAILED
        assert result.failure_code is ScheduleFailureCode.SCHEDULE_UNSUPPORTED
        assert not list(tmp_path.rglob("*.json"))
        assert not list(tmp_path.rglob(".schedule-*.tmp"))
    finally:
        _close(lease)


def test_unexpected_retain_fault_propagates_after_publication_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, lease = _store(tmp_path)
    failure = ValueError("synthetic implementation fault")
    try:
        monkeypatch.setattr(
            schedule_module.os,
            "write",
            lambda *_args: (_ for _ in ()).throw(failure),
        )
        with pytest.raises(ValueError) as raised:
            store.retain(_schedule())
        assert raised.value is failure
        assert not list(tmp_path.rglob("*.json"))
        assert not list(tmp_path.rglob(".schedule-*.tmp"))
    finally:
        _close(lease)


def test_unexpected_resolve_fault_does_not_fabricate_schedule_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule = _schedule()
    store, lease = _store(tmp_path)
    try:
        retained = store.retain(schedule)
        assert retained.digest is not None
        monkeypatch.setattr(
            schedule_module,
            "_read_existing",
            lambda *_args: (_ for _ in ()).throw(KeyError()),
        )
        with pytest.raises(KeyError):
            store.resolve(retained.digest)
        assert _path(
            tmp_path, retained.digest
        ).read_bytes() == canonical_schedule_bytes(schedule)
    finally:
        _close(lease)


def test_lease_closure_before_publication_fails_closed_without_final_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, lease = _store(tmp_path)
    original_publish = schedule_module._publish_bytes

    def close_before_publication(*args: object, **kwargs: object) -> bool:
        lease.close()
        return original_publish(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(schedule_module, "_publish_bytes", close_before_publication)
    result = store.retain(_schedule())
    assert result.outcome is ScheduleOutcome.FAILED
    assert result.failure_code is ScheduleFailureCode.SCHEDULE_UNSUPPORTED
    assert not list(tmp_path.rglob("*.json"))


def test_root_substitution_before_publication_fails_closed_without_old_root_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, lease = _store(tmp_path)
    original_publish = schedule_module._publish_bytes
    moved_root = tmp_path.parent / f"{tmp_path.name}-moved"

    def substitute_before_publication(*args: object, **kwargs: object) -> bool:
        tmp_path.rename(moved_root)
        tmp_path.mkdir()
        return original_publish(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        schedule_module, "_publish_bytes", substitute_before_publication
    )
    try:
        result = store.retain(_schedule())
        assert result.outcome is ScheduleOutcome.FAILED
        assert result.failure_code is ScheduleFailureCode.SCHEDULE_UNSUPPORTED
        assert not list(moved_root.rglob("*.json"))
        assert not list(tmp_path.rglob("*.json"))
    finally:
        lease.close()
        tmp_path.rmdir()
        moved_root.rename(tmp_path)


def test_lease_close_and_root_substitution_fail_closed(tmp_path: Path) -> None:
    result = StorageRootLease.try_acquire(tmp_path)
    assert result.lease is not None
    store = ScheduleEvidenceStore(tmp_path, result.lease)
    other_root = tmp_path / "other"
    other_root.mkdir()
    try:
        substituted = store.retain(_schedule(), root=other_root)
        assert substituted.outcome is ScheduleOutcome.FAILED
        assert substituted.failure_code is ScheduleFailureCode.SCHEDULE_UNSUPPORTED
        result.lease.close()
        closed = store.retain(_schedule())
        assert closed.outcome is ScheduleOutcome.FAILED
        assert closed.failure_code is ScheduleFailureCode.SCHEDULE_UNSUPPORTED
    finally:
        result.lease.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", "é"),
        ("source_release", ""),
        ("timezone", "Asia/Kolkata "),
        ("schema_version", True),
    ],
)
def test_schedule_validation_rejects_noncanonical_field_values(
    tmp_path: Path, field: str, value: object
) -> None:
    with pytest.raises(ValueError):
        _schedule(**{field: value})


def test_serialization_has_only_approved_top_level_and_session_fields() -> None:
    value = json.loads(canonical_schedule_bytes(_schedule()))
    assert set(value) == {
        "schema_version",
        "source",
        "source_release",
        "as_of",
        "timezone",
        "covered_from",
        "covered_to",
        "sessions",
    }
    assert set(value["sessions"][0]) == {
        "trade_date",
        "open_at",
        "close_at",
        "kind",
    }


def test_resolve_preserves_primary_fault_when_descriptor_close_also_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, lease = _store(tmp_path)
    failure = ValueError()
    descriptors: list[int] = []
    real_close = schedule_module.os.close

    def fail_resolve(_operation: object, parent_fd: int, *_args: object) -> None:
        descriptors.append(parent_fd)
        raise failure

    def close_then_fail(descriptor: int) -> None:
        real_close(descriptor)
        if descriptor in descriptors:
            raise OSError()

    try:
        retained = store.retain(_schedule())
        assert retained.digest is not None
        with monkeypatch.context() as scoped:
            scoped.setattr(schedule_module, "_resolve_in_parent", fail_resolve)
            scoped.setattr(schedule_module.os, "close", close_then_fail)
            with pytest.raises(ValueError) as raised:
                store.resolve(retained.digest)
            assert raised.value is failure
        assert len(descriptors) == 1
        with pytest.raises(OSError):
            schedule_module.os.fstat(descriptors[0])
    finally:
        lease.close()


def test_calendar_classification_propagates_computation_fault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule = _schedule(
        schema_version=SCHEDULE_SCHEMA_VERSION_V3,
        covered_to=date(2026, 1, 2),
        sessions=(
            _session(
                trade_date=date(2026, 1, 1),
                open_at=datetime(2026, 1, 1, 3, 45, tzinfo=UTC),
                close_at=datetime(2026, 1, 1, 10, tzinfo=UTC),
                kind="REGULAR",
            ),
            _session(kind="REGULAR"),
        ),
    )
    failure = RuntimeError("private/path/token")

    def fail_increment(**_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(schedule_module, "timedelta", fail_increment)
    with pytest.raises(RuntimeError) as raised:
        schedule_module.schedule_covers_full_calendar_range(
            schedule, schedule.covered_from, schedule.covered_to
        )
    assert raised.value is failure


@pytest.mark.parametrize("error_type", (OSError, AssertionError))
def test_publication_cleanup_failure_cannot_report_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_type: type[Exception]
) -> None:
    store, lease = _store(tmp_path)
    schedule = _schedule()
    failure = error_type("temporary unlink fault")
    cleanup_started = False
    real_unlink = os.unlink
    real_fsync = os.fsync

    def fail_unlink(path: str | Path, *, dir_fd: int | None = None) -> None:
        nonlocal cleanup_started
        if str(path).startswith(".schedule-"):
            cleanup_started = True
            raise failure
        real_unlink(path, dir_fd=dir_fd)

    def fail_cleanup_sync(descriptor: int) -> None:
        if cleanup_started:
            raise KeyError("secondary cleanup sync fault")
        real_fsync(descriptor)

    with lease:
        with monkeypatch.context() as scoped:
            scoped.setattr(os, "unlink", fail_unlink)
            scoped.setattr(os, "fsync", fail_cleanup_sync)
            if error_type is OSError:
                assert store.retain(schedule).outcome is ScheduleOutcome.FAILED
            else:
                with pytest.raises(AssertionError) as caught:
                    store.retain(schedule)
                assert caught.value is failure
        assert _path(tmp_path, schedule_digest(schedule)).read_bytes() == (
            canonical_schedule_bytes(schedule)
        )


def test_open_parent_keeps_recycled_descriptor_open_after_close_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, lease = _store(tmp_path)
    primary = AssertionError("post-close parent traversal fault")
    replacement: int | None = None
    child_descriptors: list[int] = []
    target: int | None = None
    real_dup = schedule_module.os.dup
    real_open = schedule_module.os.open
    real_close = schedule_module.os.close

    def track_dup(descriptor: int) -> int:
        nonlocal target
        target = real_dup(descriptor)
        return target

    def track_open(
        path: str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if path in ("calendar-schedules", "sha256"):
            child_descriptors.append(descriptor)
        return descriptor

    def release_then_fail(descriptor: int) -> None:
        nonlocal replacement
        if descriptor == target and replacement is None:
            real_close(descriptor)
            replacement = real_open(os.devnull, os.O_RDONLY)
            assert replacement == descriptor
            raise primary
        real_close(descriptor)

    try:
        with lease, lease.root_operation(tmp_path) as operation:
            with monkeypatch.context() as scoped:
                scoped.setattr(schedule_module.os, "dup", track_dup)
                scoped.setattr(schedule_module.os, "open", track_open)
                scoped.setattr(schedule_module.os, "close", release_then_fail)
                with pytest.raises(AssertionError) as raised:
                    schedule_module._open_parent(operation, create=True)
                assert raised.value is primary
            assert replacement is not None
            os.fstat(replacement)
            assert child_descriptors
            for descriptor in child_descriptors:
                with pytest.raises(OSError):
                    os.fstat(descriptor)
    finally:
        if replacement is not None:
            with contextlib.suppress(OSError):
                os.close(replacement)


def test_schedule_publication_keeps_recycled_descriptor_open_after_close_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, lease = _store(tmp_path)
    primary = AssertionError("post-close publication fault")
    replacement: int | None = None
    target: int | None = None
    real_open = schedule_module.os.open
    real_close = schedule_module.os.close

    def track_open(
        path: str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal target
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if path.startswith(".schedule-"):
            target = descriptor
        return descriptor

    def release_then_fail(descriptor: int) -> None:
        nonlocal replacement
        if descriptor == target and replacement is None:
            real_close(descriptor)
            replacement = real_open(os.devnull, os.O_RDONLY)
            assert replacement == descriptor
            raise primary
        real_close(descriptor)

    try:
        with lease, monkeypatch.context() as scoped:
            scoped.setattr(schedule_module.os, "open", track_open)
            scoped.setattr(schedule_module.os, "close", release_then_fail)
            with pytest.raises(AssertionError) as raised:
                store.retain(_schedule())
            assert raised.value is primary
        assert replacement is not None
        os.fstat(replacement)
        assert not list(tmp_path.rglob(".schedule-*.tmp"))
    finally:
        if replacement is not None:
            with contextlib.suppress(OSError):
                os.close(replacement)
