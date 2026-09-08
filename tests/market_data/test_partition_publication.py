from __future__ import annotations

import concurrent.futures
import errno
import os
import threading
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.partition_publication as publication
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.parquet import (
    pq,
    write_candles_parquet,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
    PartitionPublicationError,
    PartitionValidationError,
    PartitionWriteError,
    PublicationConflictError,
    PublicationOutcome,
    PublicationOutcomeUnknown,
    PublishedPartitionEvidence,
    publish_partition,
)
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle


def _plan() -> PlannedInstrumentMonth:
    return PlannedInstrumentMonth(
        "upstox",
        "NSE_EQ|ID",
        "INE002A01018",
        "RELIANCE",
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2022,
        1,
        date(2022, 1, 1),
        date(2022, 1, 31),
    )


def _candle(**overrides: object) -> CanonicalCandle:
    values: dict[str, object] = {
        "provider": "upstox",
        "instrument_key": "NSE_EQ|ID",
        "security_id": "INE002A01018",
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "segment": "NSE_EQ",
        "instrument_type": "EQ",
        "underlying_id": None,
        "expiry": None,
        "strike": None,
        "option_type": None,
        "interval": "1m",
        "ts": datetime(2022, 1, 1, 3, 45, tzinfo=UTC),
        "open": 1.0,
        "high": 2.0,
        "low": 1.0,
        "close": 2.0,
        "volume": 1,
        "oi": None,
        "ingested_at": datetime(2022, 2, 1, tzinfo=UTC),
        "source_version": "upstox-historical-v3",
        "adjustment_state": "raw",
    }
    values.update(overrides)
    return CanonicalCandle(**values)  # type: ignore[arg-type]


def test_publish_uses_hive_path_roundtrips_and_is_idempotent(tmp_path: Path) -> None:
    first = _candle(ts=datetime(2022, 1, 1, 3, 46, tzinfo=UTC))
    second = _candle()
    published = publish_partition(tmp_path, _plan(), [first, second])
    assert published.outcome is PublicationOutcome.PUBLISHED
    assert published.canonical_path == (
        "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/instrument_type=EQ/"
        "security_id=INE002A01018/interval=1m/year=2022/month=01/bars.parquet"
    )
    assert published.row_count == 2
    assert (tmp_path / published.canonical_path).is_file()
    repeated = publish_partition(tmp_path, _plan(), [second, first])
    assert repeated.outcome is PublicationOutcome.ALREADY_PRESENT
    assert repeated.checksum_sha256 == published.checksum_sha256


def test_storage_root_must_be_a_preexisting_real_directory(tmp_path: Path) -> None:
    missing = tmp_path / "durable-root"
    with pytest.raises(PartitionPublicationError, match="storage unavailable"):
        publish_partition(missing, _plan(), [_candle()])
    assert not missing.exists()


@pytest.mark.skipif(not hasattr(__import__("os"), "mkfifo"), reason="POSIX FIFO")
def test_existing_final_symlink_or_fifo_is_a_typed_conflict(tmp_path: Path) -> None:
    relative = publication._relative_path(_plan())
    final = tmp_path / relative
    final.parent.mkdir(parents=True)
    final.symlink_to(tmp_path / "outside.parquet")
    with pytest.raises(PublicationConflictError):
        publish_partition(tmp_path, _plan(), [_candle()])
    final.unlink()
    os.mkfifo(final)
    with pytest.raises(PublicationConflictError):
        publish_partition(tmp_path, _plan(), [_candle()])


@pytest.mark.parametrize("row_count", [[], [_candle()] * 65_537])
def test_publish_rejects_empty_or_oversize_input(
    tmp_path: Path, row_count: list[CanonicalCandle]
) -> None:
    with pytest.raises(PartitionValidationError):
        publish_partition(tmp_path, _plan(), row_count)


def test_publish_rejects_duplicate_or_wrong_month_candles(tmp_path: Path) -> None:
    candle = _candle()
    with pytest.raises(PartitionValidationError):
        publish_partition(tmp_path, _plan(), [candle, candle])
    wrong_month = _candle(ts=datetime(2022, 2, 1, 3, 45, tzinfo=UTC))
    with pytest.raises(PartitionValidationError):
        publish_partition(tmp_path, _plan(), [wrong_month])


def test_existing_different_partition_is_a_no_clobber_conflict(tmp_path: Path) -> None:
    published = publish_partition(tmp_path, _plan(), [_candle()])
    changed = _candle(close=1.5, high=1.5)
    with pytest.raises(PublicationConflictError):
        publish_partition(tmp_path, _plan(), [changed])
    assert (tmp_path / published.canonical_path).is_file()


def test_security_id_cannot_escape_hive_path(tmp_path: Path) -> None:
    plan = _plan()
    object.__setattr__(plan, "security_id", "../escape")
    candle = _candle(security_id="../escape")
    with pytest.raises(PartitionValidationError):
        publish_partition(tmp_path, plan, [candle])


@pytest.mark.parametrize("field", publication._PATH_VALUE_FIELDS)
@pytest.mark.parametrize(
    "value", ["", "../escape", "a/b", "a\x00b", "naïve", "a" * 129, " a"]
)
def test_every_path_bearing_plan_value_rejects_unsafe_or_non_ascii(
    tmp_path: Path, field: str, value: str
) -> None:
    plan = _plan()
    object.__setattr__(plan, field, value)
    with pytest.raises(PartitionValidationError):
        publish_partition(tmp_path, plan, [_candle()])


def test_path_bearing_plan_values_require_exact_builtin_strings() -> None:
    class StringSubclass(str):
        pass

    for field in publication._PATH_VALUE_FIELDS:
        plan = _plan()
        object.__setattr__(plan, field, StringSubclass(getattr(plan, field)))
        with pytest.raises(PartitionValidationError):
            publication._validated_plan(plan)


@pytest.mark.parametrize("value", ["a", "a" * 128])
def test_path_bearing_identity_value_boundary_is_accepted(value: str) -> None:
    plan = _plan()
    object.__setattr__(plan, "security_id", value)
    assert publication._validated_plan(plan).security_id == value
    assert len(publication._relative_path(plan).split("/")[5]) == len(value) + len(
        "security_id="
    )


def test_write_failure_cleans_exact_temp_without_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        publication, "_write_temp", lambda *_: (_ for _ in ()).throw(OSError())
    )
    with pytest.raises(PartitionWriteError) as error:
        publish_partition(tmp_path, _plan(), [_candle()])
    assert error.value.failure_category.value == "WRITE_FAILED"
    assert not list(tmp_path.rglob("bars.parquet")) and not list(
        tmp_path.rglob(".publish-*.tmp")
    )


@pytest.mark.parametrize("failure_call", [10, 11])
def test_post_link_fsync_failures_leave_final_and_raise_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_call: int
) -> None:
    relative = publication._relative_path(_plan())
    (tmp_path / relative).parent.mkdir(parents=True)
    calls = 0
    original = publication._fsync_directory

    def failing_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise PublicationOutcomeUnknown("publication outcome unknown")
        original(descriptor)

    monkeypatch.setattr(publication, "_fsync_directory", failing_fsync)
    with pytest.raises(PublicationOutcomeUnknown) as error:
        publish_partition(tmp_path, _plan(), [_candle()])
    assert error.value.failure_category.value == "PUBLICATION_FAILED"
    assert list(tmp_path.rglob("bars.parquet"))


def test_nonexist_link_failure_is_publication_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        publication.os,
        "link",
        lambda *_, **__: (_ for _ in ()).throw(OSError(errno.EOPNOTSUPP, "no")),
    )
    with pytest.raises(PartitionPublicationError) as error:
        publish_partition(tmp_path, _plan(), [_candle()])
    assert error.value.failure_category.value == "PUBLICATION_FAILED"
    assert not list(tmp_path.rglob("bars.parquet"))


def test_temp_is_hidden_sibling_mode_600_and_has_no_provenance_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[int] = []
    original = publication._write_temp

    def inspect_temp(descriptor: int, rows: tuple[CanonicalCandle, ...]) -> None:
        seen.append(descriptor)
        assert (
            publication.stat.S_IMODE(publication.os.fstat(descriptor).st_mode) == 0o600
        )
        original(descriptor, rows)

    monkeypatch.setattr(publication, "_write_temp", inspect_temp)
    publish_partition(tmp_path, _plan(), [_candle()])
    assert len(seen) == 1 and not list(tmp_path.rglob(".publish-*.tmp"))


def test_cleanup_failure_preserves_primary_with_sanitized_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        publication,
        "_validate_fd",
        lambda *_: (_ for _ in ()).throw(PartitionWriteError("partition write failed")),
    )
    monkeypatch.setattr(
        publication.os,
        "unlink",
        lambda *_, **__: (_ for _ in ()).throw(OSError("private-path")),
    )
    with pytest.raises(PartitionWriteError) as error:
        publish_partition(tmp_path, _plan(), [_candle()])
    assert error.value.__notes__ == ["temporary publication cleanup failed"]
    assert not list(tmp_path.rglob("bars.parquet"))


def test_unknown_serializer_fault_preserves_identity_without_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fault = TypeError("serializer fault")
    monkeypatch.setattr(
        publication,
        "write_candles_parquet",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(fault),
    )

    with pytest.raises(TypeError) as raised:
        publish_partition(tmp_path, _plan(), [_candle()])

    assert raised.value is fault
    assert not list(tmp_path.rglob("bars.parquet"))
    assert not list(tmp_path.rglob(".publish-*.tmp"))


def test_unknown_reader_fault_preserves_primary_across_cleanup_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fault = AssertionError("reader fault")
    cleanup_calls: list[str] = []
    original_unlink = publication.os.unlink
    monkeypatch.setattr(
        publication,
        "iter_candles_from_parquet",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(fault),
    )

    def fail_temp_unlink(name: str, *args: object, **kwargs: object) -> None:
        if name.startswith(".publish-"):
            cleanup_calls.append(name)
            raise RuntimeError("secondary cleanup fault")
        original_unlink(name, *args, **kwargs)

    monkeypatch.setattr(publication.os, "unlink", fail_temp_unlink)

    with pytest.raises(AssertionError) as raised:
        publish_partition(tmp_path, _plan(), [_candle()])

    assert raised.value is fault
    assert len(cleanup_calls) == 1
    assert not list(tmp_path.rglob("bars.parquet"))
    assert len(list(tmp_path.rglob(".publish-*.tmp"))) == 1


def test_standalone_unknown_temp_cleanup_fault_preserves_identity_after_visibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fault = RuntimeError("temp cleanup fault")
    unlink_calls = 0
    original_unlink = publication.os.unlink

    def fail_first_temp_unlink(name: str, *args: object, **kwargs: object) -> None:
        nonlocal unlink_calls
        if name.startswith(".publish-"):
            unlink_calls += 1
            if unlink_calls == 1:
                raise fault
        original_unlink(name, *args, **kwargs)

    monkeypatch.setattr(publication.os, "unlink", fail_first_temp_unlink)

    with pytest.raises(RuntimeError) as raised:
        publish_partition(tmp_path, _plan(), [_candle()])

    assert raised.value is fault
    assert unlink_calls == 2
    assert list(tmp_path.rglob("bars.parquet"))
    assert not list(tmp_path.rglob(".publish-*.tmp"))


def test_standalone_final_cleanup_fault_still_closes_all_publication_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = TypeError("final descriptor cleanup defect")
    watched: set[int] = set()
    closed: set[int] = set()
    original_finish = publication._finish_publication
    original_close = publication.os.close

    def finish(result, primary, visible, parent_fd, root_fd):
        watched.update(fd for fd in (parent_fd, root_fd) if fd is not None)
        return original_finish(result, primary, visible, parent_fd, root_fd)

    def close(descriptor: int) -> None:
        original_close(descriptor)
        if descriptor in watched:
            closed.add(descriptor)
            if len(closed) == 1:
                raise failure

    monkeypatch.setattr(publication, "_finish_publication", finish)
    monkeypatch.setattr(publication.os, "close", close)
    try:
        with pytest.raises(TypeError) as raised:
            publish_partition(tmp_path, _plan(), [_candle()])
        assert raised.value is failure
        assert watched and closed == watched
        assert list(tmp_path.rglob("bars.parquet"))
    finally:
        for descriptor in watched - closed:
            original_close(descriptor)


def test_final_cleanup_fault_preserves_active_primary_and_closes_all_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = PartitionWriteError("partition write failed")
    cleanup_fault = TypeError("final descriptor cleanup defect")
    watched: set[int] = set()
    closed: set[int] = set()
    original_finish = publication._finish_publication
    original_close = publication.os.close

    def finish(result, failure, visible, parent_fd, root_fd):
        watched.update(fd for fd in (parent_fd, root_fd) if fd is not None)
        return original_finish(result, failure, visible, parent_fd, root_fd)

    def close(descriptor: int) -> None:
        original_close(descriptor)
        if descriptor in watched:
            closed.add(descriptor)
            if len(closed) == 1:
                raise cleanup_fault

    monkeypatch.setattr(
        publication, "_write_temp", lambda *_: (_ for _ in ()).throw(primary)
    )
    monkeypatch.setattr(publication, "_finish_publication", finish)
    monkeypatch.setattr(publication.os, "close", close)
    try:
        with pytest.raises(PartitionWriteError) as raised:
            publish_partition(tmp_path, _plan(), [_candle()])
        assert raised.value is primary
        assert watched and closed == watched
        assert not list(tmp_path.rglob("bars.parquet"))
    finally:
        for descriptor in watched - closed:
            original_close(descriptor)


def test_temp_collision_bound_preserves_existing_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = 0
    token = "0" * 32
    existing = tmp_path / f".publish-{token}.tmp"
    existing.write_bytes(b"existing publication")
    parent_fd = os.open(tmp_path, publication._DIRECTORY_FLAGS)

    def fixed_token(_size: int) -> str:
        nonlocal attempts
        attempts += 1
        return token

    monkeypatch.setattr(publication.secrets, "token_hex", fixed_token)
    try:
        with pytest.raises(PartitionWriteError):
            publication._create_temp(parent_fd)
        assert attempts == 32
        assert existing.read_bytes() == b"existing publication"
    finally:
        os.close(parent_fd)


@pytest.mark.parametrize("failure", ["fchmod", "fstat", "unsafe_mode"])
def test_create_temp_post_create_failures_close_and_remove_the_exact_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    parent_fd = os.open(tmp_path, publication._DIRECTORY_FLAGS)
    original_mode = publication.stat.S_IMODE
    try:
        if failure == "fchmod":
            calls = 0

            def nonrestrictive_once(mode: int) -> int:
                nonlocal calls
                calls += 1
                return 0o644 if calls == 1 else original_mode(mode)

            monkeypatch.setattr(publication.stat, "S_IMODE", nonrestrictive_once)
            monkeypatch.setattr(
                publication.os,
                "fchmod",
                lambda *_: (_ for _ in ()).throw(OSError("fchmod failed")),
            )
        elif failure == "unsafe_mode":
            monkeypatch.setattr(publication.stat, "S_IMODE", lambda _mode: 0o644)
        else:
            monkeypatch.setattr(
                publication.os,
                "fstat",
                lambda *_: (_ for _ in ()).throw(OSError("fstat failed")),
            )
        with pytest.raises(PartitionWriteError) as error:
            publication._create_temp(parent_fd)
        assert getattr(error.value, "__notes__", ()) == ()
        assert not list(tmp_path.glob(".publish-*.tmp"))
    finally:
        os.close(parent_fd)


def test_create_temp_cleanup_attempts_close_unlink_and_parent_fsync_independently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent_fd = os.open(tmp_path, publication._DIRECTORY_FLAGS)
    calls: list[str] = []
    original_close = publication.os.close
    try:
        monkeypatch.setattr(
            publication.os,
            "fstat",
            lambda *_: (_ for _ in ()).throw(OSError("fstat failed")),
        )

        def close_then_report(descriptor: int) -> None:
            calls.append("close")
            original_close(descriptor)
            raise OSError("close failed")

        monkeypatch.setattr(publication.os, "close", close_then_report)
        monkeypatch.setattr(
            publication.os,
            "unlink",
            lambda *_, **__: (calls.append("unlink"), (_ for _ in ()).throw(OSError()))[
                1
            ],
        )
        monkeypatch.setattr(
            publication, "_fsync_directory", lambda *_: calls.append("fsync")
        )
        with pytest.raises(PartitionWriteError) as error:
            publication._create_temp(parent_fd)
        assert error.value.__notes__ == [
            "publication descriptor cleanup failed",
            "temporary publication cleanup failed",
        ]
        assert calls == ["close", "unlink", "fsync"]
    finally:
        monkeypatch.setattr(publication.os, "close", original_close)
        os.close(parent_fd)


def test_outer_close_failures_after_visibility_are_unknown_and_all_attempted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    original = publication._close_one

    def fail_outer(descriptor: int, primary: Exception | None = None) -> bool:
        calls.append(descriptor)
        succeeded = original(descriptor, primary)
        return succeeded if len(calls) <= 9 else False

    monkeypatch.setattr(publication, "_close_one", fail_outer)
    with pytest.raises(PublicationOutcomeUnknown) as error:
        publish_partition(tmp_path, _plan(), [_candle()])
    assert tuple(getattr(error.value, "__notes__", ())) == (
        "publication descriptor cleanup failed",
    )
    assert len(calls) >= 11
    assert list(tmp_path.rglob("bars.parquet"))


def test_outer_close_failures_preserve_previsibility_primary_and_try_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    original = publication._close_one
    monkeypatch.setattr(
        publication,
        "_write_temp",
        lambda *_: (_ for _ in ()).throw(PartitionWriteError("partition write failed")),
    )

    def observe_fail(descriptor: int, primary: Exception | None = None) -> bool:
        calls.append(descriptor)
        succeeded = original(descriptor, primary)
        return succeeded if len(calls) <= 9 else False

    monkeypatch.setattr(publication, "_close_one", observe_fail)
    with pytest.raises(PartitionWriteError) as error:
        publish_partition(tmp_path, _plan(), [_candle()])
    assert tuple(getattr(error.value, "__notes__", ())) == (
        "publication descriptor cleanup failed",
    )
    assert len(calls) >= 11
    assert not list(tmp_path.rglob("bars.parquet"))


def test_existing_validation_descriptor_close_failure_is_typed_and_not_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish_partition(tmp_path, _plan(), [_candle()])
    calls = 0
    original = publication._close_one

    def fail_existing(descriptor: int, primary: Exception | None = None) -> bool:
        nonlocal calls
        calls += 1
        succeeded = original(descriptor, primary)
        return succeeded if calls != 10 else False

    monkeypatch.setattr(publication, "_close_one", fail_existing)
    with pytest.raises(PublicationConflictError) as error:
        publish_partition(tmp_path, _plan(), [_candle()])
    assert tuple(getattr(error.value, "__notes__", ())) == (
        "publication descriptor cleanup failed",
    )
    assert calls >= 12


class _OversizeSequence(Sequence[CanonicalCandle]):
    def __len__(self) -> int:
        return 65_537

    def __getitem__(self, index: int) -> CanonicalCandle:
        raise AssertionError("oversize values must not be indexed")


class _ExactCapSequence(Sequence[CanonicalCandle]):
    def __init__(self) -> None:
        self.accessed = False

    def __len__(self) -> int:
        return 65_536

    def __getitem__(self, index: int) -> CanonicalCandle:
        self.accessed = True
        if index >= 65_536:
            raise IndexError
        return _candle()


def test_oversize_sequence_is_rejected_before_indexing_or_storage_io(
    tmp_path: Path,
) -> None:
    with pytest.raises(PartitionValidationError):
        publish_partition(tmp_path / "uncreated", _plan(), _OversizeSequence())  # type: ignore[arg-type]
    assert not (tmp_path / "uncreated").exists()


def test_exact_cap_is_admitted_before_semantic_duplicate_rejection(
    tmp_path: Path,
) -> None:
    candles = _ExactCapSequence()
    with pytest.raises(PartitionValidationError):
        publish_partition(tmp_path, _plan(), candles)  # type: ignore[arg-type]
    assert candles.accessed


def test_full_january_unique_minute_capacity_publishes(tmp_path: Path) -> None:
    start = datetime(2021, 12, 31, 18, 30, tzinfo=UTC)
    candles = [_candle(ts=start + timedelta(minutes=index)) for index in range(44_640)]
    published = publish_partition(tmp_path, _plan(), candles)
    assert published.row_count == 44_640
    assert (published.actual_from_ts, published.actual_to_ts) == (
        start,
        datetime(2022, 1, 31, 18, 29, tzinfo=UTC),
    )


def test_frozen_writer_is_byte_stable_and_has_locked_footer_settings(
    tmp_path: Path,
) -> None:
    rows = [_candle(), _candle(ts=datetime(2022, 1, 1, 3, 46, tzinfo=UTC))]
    left_root, right_root = tmp_path / "left", tmp_path / "right"
    left_root.mkdir()
    right_root.mkdir()
    left = publish_partition(left_root, _plan(), rows)
    right = publish_partition(right_root, _plan(), list(reversed(rows)))
    left_path, right_path = (
        tmp_path / "left" / left.canonical_path,
        tmp_path / "right" / right.canonical_path,
    )
    metadata = pq.ParquetFile(left_path).metadata
    column = metadata.row_group(0).column(0)
    assert left.checksum_sha256 == right.checksum_sha256
    assert left_path.read_bytes() == right_path.read_bytes()
    assert (
        metadata.format_version,
        metadata.num_row_groups,
        metadata.row_group(0).num_rows,
        column.compression,
    ) == ("2.6", 1, 2, "SNAPPY")
    assert "RLE_DICTIONARY" in column.encodings


@pytest.mark.parametrize("failure_call", range(1, 10))
def test_each_new_directory_durability_boundary_prevents_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_call: int
) -> None:
    calls = 0
    original = publication._fsync_directory

    def fail_one(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise PublicationOutcomeUnknown("publication outcome unknown")
        original(descriptor)

    monkeypatch.setattr(publication, "_fsync_directory", fail_one)
    with pytest.raises(PartitionPublicationError):
        publish_partition(tmp_path, _plan(), [_candle()])
    assert not list(tmp_path.rglob("bars.parquet"))


def test_simultaneous_equal_writers_converge_without_temp_leftovers(
    tmp_path: Path,
) -> None:
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: publish_partition(tmp_path, _plan(), [_candle()]), range(2)
            )
        )
    assert {result.outcome for result in results} == {
        PublicationOutcome.PUBLISHED,
        PublicationOutcome.ALREADY_PRESENT,
    }
    assert not list(tmp_path.rglob(".publish-*.tmp"))


def test_barrier_before_link_makes_identical_writers_converge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    barrier = threading.Barrier(2)
    original = publication._link_temp

    def synchronized(parent_fd: int, name: str) -> None:
        barrier.wait()
        original(parent_fd, name)

    monkeypatch.setattr(publication, "_link_temp", synchronized)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: publish_partition(tmp_path, _plan(), [_candle()]), range(2)
            )
        )
    assert {result.outcome for result in results} == {
        PublicationOutcome.PUBLISHED,
        PublicationOutcome.ALREADY_PRESENT,
    }
    assert results[0].checksum_sha256 == results[1].checksum_sha256
    assert results[0].canonical_path == results[1].canonical_path
    assert not list(tmp_path.rglob(".publish-*.tmp"))


def test_simultaneous_different_writers_preserve_one_immutable_winner(
    tmp_path: Path,
) -> None:
    left = [_candle()]
    right = [_candle(close=1.5, high=1.5)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(publish_partition, tmp_path, _plan(), rows)
            for rows in (left, right)
        ]
    outcomes = [future.exception() or future.result().outcome for future in futures]
    assert outcomes.count(PublicationOutcome.PUBLISHED) == 1
    assert (
        sum(isinstance(outcome, PublicationConflictError) for outcome in outcomes) == 1
    )
    assert not list(tmp_path.rglob(".publish-*.tmp"))


def test_barrier_before_link_makes_different_writers_keep_winner_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The losing writer must validate, never replace, the link-race winner."""
    barrier = threading.Barrier(2)
    original = publication._link_temp

    def synchronized(parent_fd: int, name: str) -> None:
        barrier.wait(timeout=5)
        original(parent_fd, name)

    monkeypatch.setattr(publication, "_link_temp", synchronized)
    rows = ([_candle()], [_candle(close=1.5, high=1.5)])
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(publish_partition, tmp_path, _plan(), value)
            for value in rows
        ]
        results = [
            future.result() if future.exception() is None else future.exception()
            for future in futures
        ]
    winner = next(
        value for value in results if isinstance(value, PublishedPartitionEvidence)
    )
    loser = next(value for value in results if isinstance(value, BaseException))
    assert winner.outcome is PublicationOutcome.PUBLISHED
    assert isinstance(loser, PublicationConflictError)
    final = tmp_path / winner.canonical_path
    assert final.read_bytes()
    descriptor = os.open(final, os.O_RDONLY)
    try:
        assert publication._sha256_fd(descriptor) == winner.checksum_sha256
    finally:
        os.close(descriptor)
    assert final.stat().st_size == winner.byte_size
    assert not list(tmp_path.rglob(".publish-*.tmp"))


def test_temp_name_substitution_after_validation_never_returns_mismatched_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = publication._link_temp

    def substitute(parent_fd: int, name: str) -> None:
        os.unlink(name, dir_fd=parent_fd)
        descriptor = os.open(
            name, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent_fd
        )
        try:
            os.write(descriptor, b"attacker bytes")
        finally:
            os.close(descriptor)
        original(parent_fd, name)

    monkeypatch.setattr(publication, "_link_temp", substitute)
    with pytest.raises(PublicationOutcomeUnknown):
        publish_partition(tmp_path, _plan(), [_candle()])


def test_link_then_raise_is_outcome_unknown_and_retains_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = publication._link_temp

    def link_then_raise(parent_fd: int, name: str) -> None:
        original(parent_fd, name)
        raise OSError(errno.EIO, "ambiguous link")

    monkeypatch.setattr(publication, "_link_temp", link_then_raise)
    with pytest.raises(PublicationOutcomeUnknown):
        publish_partition(tmp_path, _plan(), [_candle()])
    assert list(tmp_path.rglob("bars.parquet"))


def test_existing_final_type_check_closes_opened_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    final = tmp_path / "bars.parquet"
    final.write_bytes(b"x")
    parent_fd = os.open(tmp_path, publication._DIRECTORY_FLAGS)
    closed: list[int] = []
    original_close = publication._close_one
    try:
        monkeypatch.setattr(
            publication.os, "fstat", lambda *_: (_ for _ in ()).throw(OSError())
        )

        def observe(descriptor: int, primary: Exception | None = None) -> bool:
            closed.append(descriptor)
            return original_close(descriptor, primary)

        monkeypatch.setattr(publication, "_close_one", observe)
        with pytest.raises(PublicationConflictError):
            publication._open_existing_final(parent_fd)
        assert len(closed) == 1
    finally:
        os.close(parent_fd)


def test_parent_advance_close_failure_closes_child_before_typed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root_fd = os.open(tmp_path, publication._DIRECTORY_FLAGS)
    calls: list[int] = []
    original = publication._close_one
    try:

        def fail_first(descriptor: int, primary: Exception | None = None) -> bool:
            calls.append(descriptor)
            closed = original(descriptor, primary)
            return False if len(calls) == 1 else closed

        monkeypatch.setattr(publication, "_close_one", fail_first)
        with pytest.raises(PartitionPublicationError):
            publication._open_or_create_parents(root_fd, ["candles"])
        assert len(calls) == 2
    finally:
        os.close(root_fd)


def test_existing_raced_directory_is_fsynced_before_advancing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "candles").mkdir()
    root_fd = os.open(tmp_path, publication._DIRECTORY_FLAGS)
    fsynced = False
    opens = 0
    original_open = publication.os.open
    try:

        def open_once_missing(name: str, *args: object, **kwargs: object) -> int:
            nonlocal opens
            opens += 1
            if name == "candles" and opens == 1:
                raise FileNotFoundError
            return original_open(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(publication.os, "open", open_once_missing)
        monkeypatch.setattr(
            publication.os,
            "mkdir",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(FileExistsError()),
        )

        def durable(descriptor: int) -> None:
            nonlocal fsynced
            fsynced = True

        monkeypatch.setattr(publication, "_fsync_directory", durable)
        descriptor = publication._open_or_create_parents(root_fd, ["candles"])
        os.close(descriptor)
        assert fsynced
    finally:
        os.close(root_fd)


def test_preexisting_child_fsyncs_parent_before_advancing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "candles").mkdir()
    root_fd = os.open(tmp_path, publication._DIRECTORY_FLAGS)
    fsynced = False
    original_close = publication._close_one
    try:

        def durable(_: int) -> None:
            nonlocal fsynced
            fsynced = True

        monkeypatch.setattr(publication, "_fsync_directory", durable)

        def close_after_fsync(
            descriptor: int, primary: Exception | None = None
        ) -> bool:
            assert fsynced
            return original_close(descriptor, primary)

        monkeypatch.setattr(publication, "_close_one", close_after_fsync)
        descriptor = publication._open_or_create_parents(root_fd, ["candles"])
        os.close(descriptor)
    finally:
        os.close(root_fd)


def test_parent_fsync_failure_closes_opened_child_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "candles").mkdir()
    root_fd = os.open(tmp_path, publication._DIRECTORY_FLAGS)
    closed: list[int] = []
    original = publication._close_one
    try:
        monkeypatch.setattr(
            publication,
            "_fsync_directory",
            lambda *_: (_ for _ in ()).throw(PublicationOutcomeUnknown("unknown")),
        )

        def observe(descriptor: int, primary: Exception | None = None) -> bool:
            closed.append(descriptor)
            return original(descriptor, primary)

        monkeypatch.setattr(publication, "_close_one", observe)
        with pytest.raises(PartitionPublicationError):
            publication._open_or_create_parents(root_fd, ["candles"])
        assert len(closed) == 2
    finally:
        os.close(root_fd)


def test_publish_parent_fsync_cleanup_preserves_typed_primary_and_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    original = publication._close_one
    monkeypatch.setattr(
        publication,
        "_fsync_directory",
        lambda *_: (_ for _ in ()).throw(PublicationOutcomeUnknown("private-path")),
    )

    def fail_child_close(descriptor: int, primary: Exception | None = None) -> bool:
        calls.append(descriptor)
        original(descriptor, primary)
        return len(calls) != 1

    monkeypatch.setattr(publication, "_close_one", fail_child_close)
    with pytest.raises(PartitionPublicationError) as error:
        publish_partition(tmp_path, _plan(), [_candle()])
    assert tuple(getattr(error.value, "__notes__", ())) == (
        "publication descriptor cleanup failed",
    )
    assert len(calls) == 3
    assert "private-path" not in str(error.value)


def test_final_replacement_in_last_durability_window_is_outcome_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = publication._remove_temp

    def replace_after_unlink(parent_fd: int, name: str) -> None:
        original(parent_fd, name)
        os.unlink("bars.parquet", dir_fd=parent_fd)
        descriptor = os.open(
            "bars.parquet", os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent_fd
        )
        os.close(descriptor)

    monkeypatch.setattr(publication, "_remove_temp", replace_after_unlink)
    with pytest.raises(PublicationOutcomeUnknown):
        publish_partition(tmp_path, _plan(), [_candle()])


def test_indeterminate_post_link_visibility_is_outcome_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        publication.os,
        "link",
        lambda *_, **__: (_ for _ in ()).throw(OSError(errno.EIO, "link")),
    )
    monkeypatch.setattr(publication, "_final_visibility", lambda *_: None)
    with pytest.raises(PublicationOutcomeUnknown):
        publish_partition(tmp_path, _plan(), [_candle()])


def test_writer_boundary_receives_every_frozen_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []
    original = pq.ParquetWriter

    def capture(*args: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(pq, "ParquetWriter", capture)
    write_candles_parquet(tmp_path / "frozen.parquet", [_candle()])
    assert calls == [
        {
            "version": "2.6",
            "compression": "snappy",
            "use_dictionary": True,
            "write_statistics": True,
            "data_page_version": "1.0",
            "write_page_checksum": True,
            "write_page_index": False,
            "coerce_timestamps": "us",
            "allow_truncated_timestamps": False,
            "use_deprecated_int96_timestamps": False,
            "store_schema": True,
        }
    ]


def test_existing_validation_stops_after_expected_plus_one_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "existing.parquet"
    path.write_bytes(b"x")
    seen = 0

    class Reader:
        def __enter__(self) -> Reader:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def __iter__(self) -> Reader:
            return self

        def __next__(self) -> tuple[CanonicalCandle, ...]:
            nonlocal seen
            seen += 1
            if seen > 65_537:
                raise AssertionError("reader was not bounded")
            return (_candle(),)

    monkeypatch.setattr(
        publication, "iter_candles_from_parquet", lambda *_args, **_kwargs: Reader()
    )
    descriptor = os.open(path, os.O_RDONLY)
    try:
        with pytest.raises(PartitionPublicationError):
            publication._validate_fd(
                descriptor, (_candle(),), PartitionPublicationError
            )
    finally:
        os.close(descriptor)
    assert seen == 2


def test_evidence_rejects_mutated_plan_and_noncanonical_fields() -> None:
    good = publish_partition  # keep construction test independent of I/O
    assert good is publish_partition
    plan = _plan()
    values: dict[str, object] = {
        "plan": plan,
        "outcome": PublicationOutcome.PUBLISHED,
        "canonical_path": publication._relative_path(plan),
        "checksum_sha256": "a" * 64,
        "candle_schema_version": 1,
        "row_count": 1,
        "actual_from_ts": _candle().ts,
        "actual_to_ts": _candle().ts,
        "source_version": "source",
        "byte_size": 1,
    }
    assert PublishedPartitionEvidence(**values)  # type: ignore[arg-type]
    values["source_version"] = " source "
    with pytest.raises(ValueError, match="invalid published partition evidence"):
        PublishedPartitionEvidence(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("outcome", "PUBLISHED"),
        ("canonical_path", "elsewhere.parquet"),
        ("checksum_sha256", "A" * 64),
        ("candle_schema_version", True),
        ("row_count", True),
        ("actual_from_ts", datetime(2022, 1, 1, 3, 45, 1, tzinfo=UTC)),
        ("byte_size", True),
    ],
)
def test_evidence_direct_construction_rejects_invalid_matrix(
    field: str, invalid: object
) -> None:
    plan = _plan()
    values: dict[str, object] = {
        "plan": plan,
        "outcome": PublicationOutcome.PUBLISHED,
        "canonical_path": publication._relative_path(plan),
        "checksum_sha256": "a" * 64,
        "candle_schema_version": 1,
        "row_count": 1,
        "actual_from_ts": _candle().ts,
        "actual_to_ts": _candle().ts,
        "source_version": "source",
        "byte_size": 1,
    }
    values[field] = invalid
    with pytest.raises(ValueError, match="invalid published partition evidence"):
        PublishedPartitionEvidence(**values)  # type: ignore[arg-type]
