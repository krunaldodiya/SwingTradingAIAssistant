from __future__ import annotations

import json
import threading
import time
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.bounded_nifty50_workflow as workflow_module
from swing_trading_ai_assistant.market_data.bounded_nifty50_workflow import (
    BoundedNifty50DownloadReportV1,
    BoundedNifty50DownloadRequestV1,
    BoundedNifty50DownloadServiceV1,
    CanonicalFileNifty50UniverseSourceV1,
    Nifty50BatchOutcomeV1,
    Nifty50SymbolDownloadResultV1,
    render_bounded_nifty50_download_json,
)
from swing_trading_ai_assistant.market_data.public_contract import (
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicFailureCodeV1,
    PublicFailureV1,
)
from swing_trading_ai_assistant.market_data.universe_snapshot import (
    Nifty50ConstituentV1,
    Nifty50UniverseSnapshotV1,
    UniverseSnapshotCorruptError,
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


def _snapshot() -> Nifty50UniverseSnapshotV1:
    members = [
        Nifty50ConstituentV1(_isin(index), f"SYM{index:02d}", "FINANCIALS")
        for index in range(50)
    ]
    members[0] = Nifty50ConstituentV1(members[0].isin, "SBIN", "FINANCIALS")
    members[1] = Nifty50ConstituentV1(members[1].isin, "RELIANCE", "ENERGY")
    members.sort(key=lambda member: member.isin)
    observed = datetime(2026, 8, 1, tzinfo=UTC)
    return Nifty50UniverseSnapshotV1(
        1,
        "nifty-50",
        date(2026, 7, 1),
        date(2026, 9, 30),
        "nse-archive",
        "2026-q3",
        observed,
        observed,
        "nse-archive",
        "2026-q3",
        observed,
        observed,
        tuple(members),
    )


def _terminal_report() -> PublicCommandReportV1[None]:
    return PublicCommandReportV1(
        "v1",
        "download",
        PublicCommandStatusV1.REJECTED,
        PublicFailureV1(PublicFailureCodeV1.INVALID_INPUT, None, None, None, None, ()),
        0,
        None,
    )


class _Source:
    def __init__(self, snapshot: Nifty50UniverseSnapshotV1) -> None:
        self.snapshot = snapshot
        self.calls = 0

    def load(self) -> Nifty50UniverseSnapshotV1:
        self.calls += 1
        return self.snapshot


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 8, 12, 8, tzinfo=UTC)


class _SymbolService:
    def __init__(self) -> None:
        self.symbols: list[str] = []

    def download_under_lease(self, request: object, lease: object):
        assert lease is not None
        self.symbols.append(request.symbol)  # type: ignore[attr-defined]
        return _terminal_report()


def _request(root: Path) -> BoundedNifty50DownloadRequestV1:
    return BoundedNifty50DownloadRequestV1(
        symbols=("RELIANCE", "SBIN"),
        universe_as_of=date(2026, 8, 11),
        knowledge_cutoff=datetime(2026, 8, 12, 7, tzinfo=UTC),
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 11),
        storage_root=root,
        workers=1,
    )


def test_one_or_many_selection_uses_isin_order_and_one_outer_lease(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    source = _Source(_snapshot())
    symbol_service = _SymbolService()
    service = BoundedNifty50DownloadServiceV1(
        source,
        lambda policy: symbol_service,
        clock=_Clock(),
    )

    report = service.download(_request(tmp_path))

    assert report.outcome is Nifty50BatchOutcomeV1.REJECTED
    assert tuple(item.symbol for item in report.results) == ("SBIN", "RELIANCE")
    assert symbol_service.symbols == ["SBIN", "RELIANCE"]
    assert source.calls == 1
    assert report.universe_snapshot_sha256 is not None


def test_retained_universe_supports_zero_source_rerun(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    first_source = _Source(_snapshot())
    first_worker = _SymbolService()
    request = _request(tmp_path)
    BoundedNifty50DownloadServiceV1(
        first_source, lambda policy: first_worker, clock=_Clock()
    ).download(request)

    second_worker = _SymbolService()
    report = BoundedNifty50DownloadServiceV1(
        None, lambda policy: second_worker, clock=_Clock()
    ).download(request)

    assert report.universe_snapshot_sha256 is not None
    assert second_worker.symbols == ["SBIN", "RELIANCE"]


def test_non_member_selection_fails_before_symbol_service(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    source = _Source(_snapshot())
    worker = _SymbolService()
    request = _request(tmp_path)
    invalid = BoundedNifty50DownloadRequestV1(
        symbols=("NOT_A_MEMBER",),
        universe_as_of=request.universe_as_of,
        knowledge_cutoff=request.knowledge_cutoff,
        from_date=request.from_date,
        to_date=request.to_date,
        storage_root=request.storage_root,
    )

    report = BoundedNifty50DownloadServiceV1(
        source, lambda policy: worker, clock=_Clock()
    ).download(invalid)

    assert report.outcome is Nifty50BatchOutcomeV1.REJECTED
    assert report.results == ()
    assert worker.symbols == []


def test_canonical_file_source_and_renderer_are_bounded(tmp_path: Path) -> None:
    path = tmp_path / "universe.json"
    path.write_bytes(_snapshot().canonical_json_bytes())
    path.chmod(0o400)

    loaded = CanonicalFileNifty50UniverseSourceV1(path.resolve()).load()
    assert loaded == _snapshot()

    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    report = BoundedNifty50DownloadServiceV1(
        _Source(loaded), lambda policy: _SymbolService(), clock=_Clock()
    ).download(_request(root.resolve()))
    rendered = json.loads(render_bounded_nifty50_download_json(report))
    assert rendered["scope"] == "nifty50"
    assert [item["symbol"] for item in rendered["results"]] == [
        "SBIN",
        "RELIANCE",
    ]


def test_universe_file_rejects_writable_or_symlink_source(tmp_path: Path) -> None:
    path = tmp_path / "universe.json"
    path.write_bytes(_snapshot().canonical_json_bytes())
    path.chmod(0o666)
    source = CanonicalFileNifty50UniverseSourceV1(path.resolve())
    try:
        source.load()
    except Exception as error:
        assert type(error).__name__ == "UniverseSnapshotCorruptError"
    else:
        raise AssertionError("writable universe source was accepted")

    path.chmod(0o400)
    link = tmp_path / "linked.json"
    link.symlink_to(path)
    linked = CanonicalFileNifty50UniverseSourceV1(link.absolute())
    try:
        linked.load()
    except Exception as error:
        assert type(error).__name__ == "UniverseSnapshotCorruptError"
    else:
        raise AssertionError("symlink universe source was accepted")


def test_worker_pool_is_concurrent_bounded_and_result_order_is_stable(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    lock = threading.Lock()
    active = 0
    maximum = 0

    class Worker:
        def download_under_lease(self, request: object, lease: object):
            nonlocal active, maximum
            assert lease is not None
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return _terminal_report()

    request = _request(tmp_path)
    selected = ("SBIN", "RELIANCE", "SYM02", "SYM03", "SYM04", "SYM05")
    concurrent = BoundedNifty50DownloadRequestV1(
        selected,
        request.universe_as_of,
        request.knowledge_cutoff,
        request.from_date,
        request.to_date,
        request.storage_root,
        workers=3,
    )
    report = BoundedNifty50DownloadServiceV1(
        _Source(_snapshot()), lambda policy: Worker(), clock=_Clock()
    ).download(concurrent)

    assert maximum == 3
    assert report.worker_count == 3
    expected = tuple(
        member.symbol
        for member in _snapshot().constituents
        if member.symbol in set(selected)
    )
    assert tuple(item.symbol for item in report.results) == expected


def test_all_50_member_smoke_stays_within_eight_workers_and_is_deterministic(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    lock = threading.Lock()
    active = 0
    maximum = 0

    class Worker:
        def download_under_lease(self, request: object, lease: object):
            nonlocal active, maximum
            assert lease is not None
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.005)
            with lock:
                active -= 1
            return _terminal_report()

    request = _request(tmp_path)
    all_members = BoundedNifty50DownloadRequestV1(
        None,
        request.universe_as_of,
        request.knowledge_cutoff,
        request.from_date,
        request.to_date,
        request.storage_root,
        workers=8,
    )
    report = BoundedNifty50DownloadServiceV1(
        _Source(_snapshot()), lambda policy: Worker(), clock=_Clock()
    ).download(all_members)

    assert len(report.results) == 50
    assert maximum == 8
    assert report.worker_count == 8
    assert tuple(item.symbol for item in report.results) == tuple(
        member.symbol for member in _snapshot().constituents
    )


def test_public_batch_dtos_reject_invalid_shapes(tmp_path: Path) -> None:
    request = _request(tmp_path)
    with pytest.raises(ValueError):
        BoundedNifty50DownloadRequestV1(
            (),
            request.universe_as_of,
            request.knowledge_cutoff,
            request.from_date,
            request.to_date,
            request.storage_root,
        )
    with pytest.raises(ValueError):
        Nifty50SymbolDownloadResultV1(
            "SBIN", _isin(0), PublicCommandStatusV1.SUCCEEDED, None, 38
        )
    with pytest.raises(ValueError):
        BoundedNifty50DownloadReportV1(
            Nifty50BatchOutcomeV1.REJECTED, "bad-digest", (), 0, 0
        )
    rejected = Nifty50SymbolDownloadResultV1(
        "SBIN",
        _isin(0),
        PublicCommandStatusV1.REJECTED,
        PublicFailureCodeV1.INVALID_INPUT,
        0,
    )
    with pytest.raises(ValueError):
        BoundedNifty50DownloadReportV1(
            Nifty50BatchOutcomeV1.SUCCEEDED, "a" * 64, (rejected,), 0, 1
        )
    with pytest.raises(ValueError):
        Nifty50SymbolDownloadResultV1(
            "SBIN",
            "secret-token",
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INVALID_INPUT,
            0,
        )
    with pytest.raises(ValueError):
        CanonicalFileNifty50UniverseSourceV1(Path("relative.json"))


def test_aggregate_status_precedence_and_invalid_renderer_fail_closed() -> None:
    succeeded = Nifty50SymbolDownloadResultV1(
        "SBIN", _isin(0), PublicCommandStatusV1.SUCCEEDED, None, 0
    )
    rejected = Nifty50SymbolDownloadResultV1(
        "RELIANCE",
        _isin(1),
        PublicCommandStatusV1.REJECTED,
        PublicFailureCodeV1.INVALID_INPUT,
        0,
    )
    unavailable = Nifty50SymbolDownloadResultV1(
        "SYM02",
        _isin(2),
        PublicCommandStatusV1.UNAVAILABLE,
        PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
        0,
    )
    cancelled = Nifty50SymbolDownloadResultV1(
        "SYM03",
        _isin(3),
        PublicCommandStatusV1.CANCELLED,
        PublicFailureCodeV1.INGESTION_CANCELLED,
        0,
    )
    assert workflow_module._aggregate((succeeded,)) is Nifty50BatchOutcomeV1.SUCCEEDED
    assert (
        workflow_module._aggregate((succeeded, rejected))
        is Nifty50BatchOutcomeV1.PARTIAL
    )
    assert (
        workflow_module._aggregate((unavailable,)) is Nifty50BatchOutcomeV1.UNAVAILABLE
    )
    assert workflow_module._aggregate((cancelled,)) is Nifty50BatchOutcomeV1.CANCELLED
    assert workflow_module._aggregate(()) is Nifty50BatchOutcomeV1.FAILED
    decoded = json.loads(render_bounded_nifty50_download_json(object()))
    assert decoded["status"] == "FAILED"


def test_source_short_read_and_identity_change_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "universe.json"
    path.write_bytes(_snapshot().canonical_json_bytes())
    path.chmod(0o400)
    source = CanonicalFileNifty50UniverseSourceV1(path.resolve())

    monkeypatch.setattr(workflow_module.os, "read", lambda *_args: b"")
    with pytest.raises(UniverseSnapshotCorruptError):
        source.load()
    monkeypatch.undo()

    identities = iter(((1,), (1,), (2,)))
    monkeypatch.setattr(
        workflow_module, "_file_identity", lambda _value: next(identities)
    )
    with pytest.raises(UniverseSnapshotCorruptError):
        source.load()


def test_service_terminal_boundaries_are_typed_and_provider_free(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    request = _request(tmp_path)
    service = BoundedNifty50DownloadServiceV1(
        None, lambda policy: _SymbolService(), clock=_Clock()
    )
    assert service.download(object()).outcome is Nifty50BatchOutcomeV1.REJECTED
    assert service.download(request).outcome is Nifty50BatchOutcomeV1.UNAVAILABLE

    class InvalidClock:
        def now(self) -> object:
            return None

    assert (
        BoundedNifty50DownloadServiceV1(
            _Source(_snapshot()), lambda policy: _SymbolService(), clock=InvalidClock()
        )
        .download(request)
        .outcome
        is Nifty50BatchOutcomeV1.REJECTED
    )

    class CorruptSource:
        def load(self) -> Nifty50UniverseSnapshotV1:
            raise UniverseSnapshotCorruptError("corrupt")

    assert (
        BoundedNifty50DownloadServiceV1(
            CorruptSource(), lambda policy: _SymbolService(), clock=_Clock()
        )
        .download(request)
        .outcome
        is Nifty50BatchOutcomeV1.FAILED
    )

    class MalformedSource:
        def load(self) -> object:
            return object()

    assert (
        BoundedNifty50DownloadServiceV1(
            MalformedSource(),  # type: ignore[arg-type]
            lambda policy: _SymbolService(),
            clock=_Clock(),
        )
        .download(request)
        .outcome
        is Nifty50BatchOutcomeV1.FAILED
    )


def test_stale_universe_generic_factory_failure_and_malformed_worker_are_bounded(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    request = _request(tmp_path)
    stale = BoundedNifty50DownloadRequestV1(
        request.symbols,
        request.universe_as_of,
        request.knowledge_cutoff,
        date(2025, 12, 1),
        request.to_date,
        request.storage_root,
        request.workers,
    )
    assert (
        BoundedNifty50DownloadServiceV1(
            _Source(_snapshot()), lambda policy: _SymbolService(), clock=_Clock()
        )
        .download(stale)
        .outcome
        is Nifty50BatchOutcomeV1.UNAVAILABLE
    )

    other_root = tmp_path / "generic"
    other_root.mkdir(mode=0o700)
    generic_request = _request(other_root)

    def broken_factory(policy: object) -> _SymbolService:
        raise RuntimeError

    assert (
        BoundedNifty50DownloadServiceV1(
            _Source(_snapshot()), broken_factory, clock=_Clock()
        )
        .download(generic_request)
        .outcome
        is Nifty50BatchOutcomeV1.FAILED
    )

    malformed_root = tmp_path / "malformed"
    malformed_root.mkdir(mode=0o700)

    class MalformedWorker:
        def download_under_lease(self, request: object, lease: object) -> object:
            return object()

    malformed = BoundedNifty50DownloadServiceV1(
        _Source(_snapshot()), lambda policy: MalformedWorker(), clock=_Clock()
    ).download(_request(malformed_root))
    assert malformed.outcome is Nifty50BatchOutcomeV1.FAILED
    assert all(
        result.failure_code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE
        for result in malformed.results
    )
