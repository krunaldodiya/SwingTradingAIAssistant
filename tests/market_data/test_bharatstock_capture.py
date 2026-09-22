from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from swing_trading_ai_assistant.entrypoints.capture_forward_adjusted_ohlcv import main
from swing_trading_ai_assistant.market_data import bharatstock_capture as core
from swing_trading_ai_assistant.market_data import (
    capture_forward_adjusted_ohlcv as held_store,
)
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,
    BharatStockDailyPrice,
    BharatStockError,
    BharatStockHistory,
    BharatStockInstrument,
)
from swing_trading_ai_assistant.market_data.http import HttpResponse
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleEvidenceStore,
    ScheduleOutcome,
    ScheduleSession,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
    StorageRootLeaseError,
)
from swing_trading_ai_assistant.research_packet import bharatstock_v2
from swing_trading_ai_assistant.research_packet.bharatstock import (
    build_bharatstock_research_packet_v1,
)

_SESSIONS = (date(2026, 8, 24), date(2026, 8, 25), date(2026, 8, 26))
_NOW = datetime(2026, 8, 26, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def capture_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core, "_now", lambda: _NOW)


def _instrument(index: int) -> BharatStockInstrument:
    return BharatStockInstrument(
        isin=f"INE{index:09d}", exchange="NSE", symbol=f"S{index:03d}"
    )


def _schedule() -> ExpectedSessionSchedule:
    sessions = tuple(
        ScheduleSession(
            trade_date=session,
            open_at=datetime.combine(session, datetime.min.time(), tzinfo=UTC)
            + timedelta(hours=3, minutes=45),
            close_at=datetime.combine(session, datetime.min.time(), tzinfo=UTC)
            + timedelta(hours=10),
            kind="REGULAR",
        )
        for session in _SESSIONS
    )
    return ExpectedSessionSchedule(
        schema_version=3,
        source="nse-upstox-composed-calendar",
        source_release=f"composed-calendar@v1={'3' * 64}",
        as_of=_NOW,
        timezone="Asia/Kolkata",
        covered_from=_SESSIONS[0],
        covered_to=_SESSIONS[-1],
        sessions=sessions,
        closures=tuple(
            ScheduleClosure(_SESSIONS[0] + timedelta(days=offset), "WEEKEND")
            for offset in range((_SESSIONS[-1] - _SESSIONS[0]).days + 1)
            if _SESSIONS[0] + timedelta(days=offset) not in _SESSIONS
        ),
    )


def _retain_schedule(root: Path) -> ExpectedSessionSchedule:
    root.mkdir(mode=0o700)
    lease_result = StorageRootLease.try_acquire_private_empty(root)
    assert (
        lease_result.outcome is LeaseOutcome.ACQUIRED and lease_result.lease is not None
    )
    try:
        result = ScheduleEvidenceStore(root, lease_result.lease).retain(_schedule())
        assert result.outcome is ScheduleOutcome.RETAINED
    finally:
        lease_result.lease.close()
    return _schedule()


def _request(
    *members: BharatStockInstrument,
    parent: str | None = None,
) -> core.CaptureRequestV2:
    schedule = _schedule()
    return core.CaptureRequestV2(
        members=members or (_instrument(0),),
        sessions=_SESSIONS,
        decision_cutoff=_NOW + timedelta(hours=1),
        schedule_evidence_sha256=schedule_digest(schedule),
        schedule_source=schedule.source,
        schedule_source_release=schedule.source_release,
        selection_identity_sha256=core.selection_identity_v2(
            members or (_instrument(0),)
        ),
        schedule_identity_sha256=core.schedule_identity_v2(schedule),
        parent_revision_sha256=parent,
    )


class _Client:
    def __init__(
        self, *, local: set[str] | None = None, shared_after: int | None = None
    ) -> None:
        self.local = set() if local is None else local
        self.shared_after = shared_after
        self.calls: list[tuple[str, date, date]] = []

    def history(
        self,
        instrument: BharatStockInstrument,
        start: date,
        end: date,
        *,
        effect_guard: Callable[[], None] | None = None,
    ) -> BharatStockHistory:
        if effect_guard is not None:
            effect_guard()
        self.calls.append((instrument.isin, start, end))
        if self.shared_after is not None and len(self.calls) > self.shared_after:
            raise BharatStockError("RATE_LIMITED", member_local=False)
        if instrument.isin in self.local:
            raise BharatStockError("EMPTY_HISTORY", member_local=True)
        rows = tuple(
            BharatStockDailyPrice(
                session=session,
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=1000,
                adjusted_close=Decimal("100"),
                adjustment_factor=Decimal("1"),
            )
            for session in _SESSIONS
        )
        result = BharatStockHistory(
            instrument=instrument,
            rows=rows,
            retrieved_at=_NOW,
            response_sha256s=("5" * 64, "6" * 64),
            request_count=2,
        )
        if effect_guard is not None:
            effect_guard()
        return result


class _ChangingClient(_Client):
    def history(
        self,
        instrument: BharatStockInstrument,
        start: date,
        end: date,
        *,
        effect_guard: Callable[[], None] | None = None,
    ) -> BharatStockHistory:
        original = super().history(instrument, start, end, effect_guard=effect_guard)
        close = Decimal("100") + Decimal(len(self.calls)) / 100
        return replace(
            original,
            rows=tuple(
                replace(row, close=close, adjusted_close=close) for row in original.rows
            ),
        )


def test_capture_retains_original_order_and_isolates_one_member(tmp_path: Path) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    members = (_instrument(2), _instrument(0), _instrument(1))
    client = _Client(local={members[1].isin})
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    result = core.capture_bharatstock_v2(
        _request(*members), capture_root, schedule_root, client=client
    )

    assert result.code == "CAPTURED"
    assert tuple(item.member for item in result.revision.members) == members
    assert [item.evidence_state for item in result.revision.members] == [
        "OBSERVED",
        "INSUFFICIENT_EVIDENCE",
        "OBSERVED",
    ]
    assert (
        result.revision.actual_coverage_identity_sha256
        != result.revision.request.selection_identity_sha256
    )
    assert (
        result.revision.request.selection_identity_sha256
        == core.selection_identity_v2(members)
    )


def test_shared_failure_stops_later_calls_and_records_not_attempted(
    tmp_path: Path,
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    members = (_instrument(0), _instrument(1), _instrument(2))
    client = _Client(shared_after=1)

    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    result = core.capture_bharatstock_v2(
        _request(*members), capture_root, schedule_root, client=client
    )

    assert len(client.calls) == 2
    assert result.code == "CAPTURED"
    assert result.revision.shared_failure == "RATE_LIMITED"
    assert [item.evidence_state for item in result.revision.members] == [
        "OBSERVED",
        "INSUFFICIENT_EVIDENCE",
        "NOT_ATTEMPTED",
    ]
    assert [item.reason for item in result.revision.members[1:]] == [
        "RATE_LIMITED",
        "BLOCKED_BY_SHARED_FAILURE",
    ]


def test_exact_reuse_performs_no_transport_and_reader_returns_named_revision(
    tmp_path: Path,
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    request = _request(_instrument(0), _instrument(1))
    client = _Client()
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    first = core.capture_bharatstock_v2(
        request, capture_root, schedule_root, client=client
    )
    reused = core.capture_bharatstock_v2(
        request, capture_root, schedule_root, client=client
    )

    assert first.code == "CAPTURED"
    assert reused.code == "REUSED"
    assert first.from_acquisition is True
    assert reused.from_acquisition is False
    assert len(client.calls) == 2
    assert (
        core.read_bharatstock_capture_revision_v2(
            capture_root, first.revision.revision_identity_sha256
        )
        == first.revision
    )


@pytest.mark.parametrize("access", ["capture", "reader"])
def test_capture_admission_rejects_revision_pointer_digest_alias(
    tmp_path: Path, access: str
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    request = _request()
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    captured = core.capture_bharatstock_v2(
        request, capture_root, schedule_root, client=_Client()
    )
    assert captured.code == "CAPTURED" and captured.revision is not None
    namespace = capture_root / "bharatstock-capture-v3"
    alias_identity = "0" * 64
    alias = namespace / "revisions" / f"{alias_identity}.json"
    alias.write_bytes(captured.revision.canonical_json_bytes())
    alias.chmod(0o400)
    pointer = namespace / "requests" / f"{request.request_identity_sha256}.json"
    pointer_value = json.loads(pointer.read_bytes())
    pointer_value["revision_identity_sha256"] = alias_identity
    pointer.chmod(0o600)
    pointer.write_text(json.dumps(pointer_value) + "\n")
    pointer.chmod(0o400)

    if access == "reader":
        with pytest.raises(core.CaptureRevisionUnavailableV2):
            core.read_bharatstock_capture_revision_v2(
                capture_root, captured.revision.revision_identity_sha256
            )
    else:
        client = _Client()
        rejected = core.capture_bharatstock_v2(
            request, capture_root, schedule_root, client=client
        )
        assert (rejected.code, rejected.reason) == (
            "STORE_UNAVAILABLE",
            "EVIDENCE_CONFLICT",
        )
        assert client.calls == []


@pytest.mark.parametrize("access", ["capture", "reader"])
def test_unsafe_immutable_revision_returns_governed_storage_failure(
    tmp_path: Path, access: str
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    request = _request()
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    captured = core.capture_bharatstock_v2(
        request, capture_root, schedule_root, client=_Client()
    )
    assert captured.code == "CAPTURED" and captured.revision is not None
    revision_path = (
        capture_root
        / "bharatstock-capture-v3"
        / "revisions"
        / f"{captured.revision.revision_identity_sha256}.json"
    )
    revision_path.chmod(0o600)

    if access == "reader":
        with pytest.raises(core.CaptureRevisionUnavailableV2):
            core.read_bharatstock_capture_revision_v2(
                capture_root, captured.revision.revision_identity_sha256
            )
    else:
        client = _Client()
        rejected = core.capture_bharatstock_v2(
            request, capture_root, schedule_root, client=client
        )
        assert (rejected.code, rejected.reason) == (
            "STORE_UNAVAILABLE",
            "EVIDENCE_CONFLICT",
        )
        assert client.calls == []


@pytest.mark.parametrize("directory", ["namespace", "root"])
def test_detached_capture_namespace_cannot_admit_a_revision(
    tmp_path: Path, directory: str
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    namespace = (
        capture_root if directory == "root" else capture_root / "bharatstock-capture-v3"
    )
    detached = tmp_path / "detached"
    before: dict[Path, bytes] = {}

    class RenamingClient(_Client):
        def history(
            self,
            instrument: BharatStockInstrument,
            start: date,
            end: date,
            *,
            effect_guard: Callable[[], None] | None = None,
        ) -> BharatStockHistory:
            nonlocal before
            history = super().history(instrument, start, end, effect_guard=effect_guard)
            before = {
                path.relative_to(namespace): path.read_bytes()
                for path in namespace.rglob("*")
                if path.is_file()
            }
            namespace.rename(detached)
            namespace.mkdir(mode=0o700)
            return history

    result = core.capture_bharatstock_v2(
        _request(), capture_root, schedule_root, client=RenamingClient()
    )
    assert result.code == "STORE_UNAVAILABLE"
    assert result.revision is None
    assert {
        path.relative_to(detached): path.read_bytes()
        for path in detached.rglob("*")
        if path.is_file()
    } == before


def test_oversized_revision_is_rejected_before_immutable_admission(
    tmp_path: Path,
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    precise_price = Decimal("100." + "1" * 80_000)

    class PreciseClient(_Client):
        def history(
            self,
            instrument: BharatStockInstrument,
            start: date,
            end: date,
            *,
            effect_guard: Callable[[], None] | None = None,
        ) -> BharatStockHistory:
            history = super().history(instrument, start, end, effect_guard=effect_guard)
            return replace(
                history,
                rows=tuple(
                    replace(
                        row,
                        open=precise_price,
                        high=precise_price,
                        low=precise_price,
                        close=precise_price,
                        adjusted_close=None,
                        adjustment_factor=None,
                    )
                    for row in history.rows
                ),
            )

    result = core.capture_bharatstock_v2(
        _request(*(_instrument(index) for index in range(10))),
        capture_root,
        schedule_root,
        client=PreciseClient(),
    )
    assert (result.code, result.reason) == (
        "INSUFFICIENT_EVIDENCE",
        "REVISION_TOO_LARGE",
    )
    assert result.revision is None
    assert not any(
        path.is_file() for path in (capture_root / "bharatstock-capture-v3").rglob("*")
    )


def test_correction_requires_admitted_parent_and_changes_immutable_revision(
    tmp_path: Path,
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    first = core.capture_bharatstock_v2(
        _request(), root, schedule_root, client=_Client()
    )
    correction = core.capture_bharatstock_v2(
        _request(parent=first.revision.revision_identity_sha256),
        root,
        schedule_root,
        client=_Client(),
    )

    assert correction.code == "INSUFFICIENT_EVIDENCE"
    assert correction.reason == "CORRECTION_CONTENT_UNCHANGED"
    assert correction.from_acquisition is True
    unavailable = core.capture_bharatstock_v2(
        _request(parent="f" * 64), root, schedule_root, client=_Client()
    )
    assert unavailable.code == "STORE_UNAVAILABLE"
    assert unavailable.reason == "EVIDENCE_CONFLICT"


def test_reordered_selection_is_a_distinct_request_identity() -> None:
    first = _request(_instrument(0), _instrument(1))
    second = _request(_instrument(1), _instrument(0))

    assert first.selection_identity_sha256 != second.selection_identity_sha256
    assert first.request_identity_sha256 != second.request_identity_sha256


def test_reader_rejects_forged_named_revision(tmp_path: Path) -> None:
    with pytest.raises(core.CaptureRevisionUnavailableV2):
        core.read_bharatstock_capture_revision_v2(tmp_path / "missing", "0" * 64)


def test_interrupted_request_publication_recovers_prepared_revision_without_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    request = _request()
    client = _Client()
    original = held_store.publish_capture_bytes

    def interrupt_request_pointer(
        operation: object, directory: object, name: str, raw: bytes
    ) -> None:
        if name == f"{request.request_identity_sha256}.json":
            raise OSError("interrupted before request admission")
        original(operation, directory, name, raw)  # type: ignore[arg-type]

    monkeypatch.setattr(held_store, "publish_capture_bytes", interrupt_request_pointer)
    first = core.capture_bharatstock_v2(
        request, capture_root, schedule_root, client=client
    )
    monkeypatch.setattr(held_store, "publish_capture_bytes", original)
    recovered = core.capture_bharatstock_v2(
        request, capture_root, schedule_root, client=client
    )

    assert first.code == "STORE_UNAVAILABLE"
    assert recovered.code == "CAPTURED"
    assert recovered.from_acquisition is False
    assert len(client.calls) == 1


def test_exact_reader_rejects_unadmitted_revision(tmp_path: Path) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    captured = core.capture_bharatstock_v2(
        _request(), capture_root, schedule_root, client=_Client()
    )
    pointer = (
        capture_root
        / "bharatstock-capture-v3"
        / "requests"
        / f"{captured.revision.request.request_identity_sha256}.json"
    )
    pointer.chmod(0o600)
    pointer.unlink()

    with pytest.raises(core.CaptureRevisionUnavailableV2):
        core.read_bharatstock_capture_revision_v2(
            capture_root, captured.revision.revision_identity_sha256
        )


def test_unexpected_client_value_error_propagates_without_becoming_storage_failure(
    tmp_path: Path,
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)

    class BrokenClient(_Client):
        def history(
            self, *args: object, effect_guard: Callable[[], None] | None = None
        ) -> BharatStockHistory:
            raise ValueError("unexpected implementation defect")

    with pytest.raises(ValueError, match="unexpected implementation defect"):
        core.capture_bharatstock_v2(
            _request(), capture_root, schedule_root, client=BrokenClient()
        )


def test_provider_primary_survives_directory_cleanup_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    primary = ValueError("unexpected provider defect")
    open_directory = core._open_directory  # pyright: ignore[reportPrivateUsage]
    close = os.close
    owned: set[int] = set()

    def track_directory(*args, **kwargs):
        directory = open_directory(*args, **kwargs)
        owned.add(directory.descriptor)
        return directory

    def fail_after_close(descriptor: int) -> None:
        if descriptor in owned:
            owned.remove(descriptor)
            close(descriptor)
            raise OSError("secondary cleanup failure")
        close(descriptor)

    class BrokenClient(_Client):
        def history(
            self, *args: object, effect_guard: Callable[[], None] | None = None
        ) -> BharatStockHistory:
            raise primary

    monkeypatch.setattr(core, "_open_directory", track_directory)
    monkeypatch.setattr(held_store.os, "close", fail_after_close)
    with pytest.raises(ValueError) as raised:
        core.capture_bharatstock_v2(
            _request(), root, schedule_root, client=BrokenClient()
        )
    assert raised.value is primary
    assert owned == set()
    assert not tuple(root.rglob("*.json"))


@pytest.mark.parametrize("access", ["directory", "file"])
def test_post_open_primary_survives_descriptor_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, access: str
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    request = _request()
    revision_id = None
    if access == "file":
        captured = core.capture_bharatstock_v2(
            request, root, schedule_root, client=_Client()
        )
        assert captured.revision is not None
        revision_id = captured.revision.revision_identity_sha256
    target = "revisions" if access == "directory" else f"{revision_id}.json"
    before = {path: path.read_bytes() for path in root.rglob("*.json")}
    primary = AssertionError("unexpected post-open metadata failure")
    open_file, fstat, close = os.open, os.fstat, os.close
    owned: set[int] = set()

    def track_open(path, *args, **kwargs):
        descriptor = open_file(path, *args, **kwargs)
        if path == target and kwargs.get("dir_fd") is not None:
            owned.add(descriptor)
        return descriptor

    def fail_metadata(descriptor: int):
        if descriptor in owned:
            raise primary
        return fstat(descriptor)

    def fail_after_close(descriptor: int) -> None:
        if descriptor in owned:
            owned.remove(descriptor)
            close(descriptor)
            raise OSError("secondary descriptor cleanup failure")
        close(descriptor)

    monkeypatch.setattr(os, "open", track_open)
    monkeypatch.setattr(os, "fstat", fail_metadata)
    monkeypatch.setattr(os, "close", fail_after_close)
    with pytest.raises(AssertionError) as raised:
        if access == "directory":
            core.capture_bharatstock_v2(request, root, schedule_root, client=_Client())
        else:
            assert revision_id is not None
            core.read_bharatstock_capture_revision_v2(root, revision_id)
    assert raised.value is primary
    assert owned == set()
    assert {path: path.read_bytes() for path in root.rglob("*.json")} == before


@pytest.mark.parametrize("access", ["capture", "reader"])
def test_handled_exception_does_not_hide_standalone_directory_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, access: str
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    request = _request()
    captured = core.capture_bharatstock_v2(
        request, root, schedule_root, client=_Client()
    )
    assert captured.revision is not None
    revision_id = captured.revision.revision_identity_sha256
    before = {path: path.read_bytes() for path in root.rglob("*.json")}
    secondary = OSError("standalone directory cleanup failure")
    close = held_store._PrivateDirectory.close  # pyright: ignore[reportPrivateUsage]

    def fail_after_close(directory) -> None:
        close(directory)
        raise secondary

    monkeypatch.setattr(held_store._PrivateDirectory, "close", fail_after_close)
    with pytest.raises(RuntimeError) as raised:
        try:
            raise FileNotFoundError("already handled lookup miss")
        except FileNotFoundError:
            if access == "capture":
                core.capture_bharatstock_v2(
                    request, root, schedule_root, client=_Client()
                )
            else:
                core.read_bharatstock_capture_revision_v2(root, revision_id)
    assert raised.value.__cause__ is secondary
    assert {path: path.read_bytes() for path in root.rglob("*.json")} == before


def test_deadline_expiry_stops_before_another_member_call(tmp_path: Path) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    client = _Client()

    def clock() -> datetime:
        return _NOW if not client.calls else _NOW + timedelta(hours=2)

    result = core.capture_bharatstock_v2(
        _request(_instrument(0), _instrument(1)),
        capture_root,
        schedule_root,
        client=client,
        clock=clock,
    )
    assert result.reason == "ACQUISITION_DEADLINE_EXCEEDED"
    assert len(client.calls) == 1
    assert result.revision is None


@pytest.mark.parametrize("missing", [None, 0, 49, 50, 99, "all"])
def test_public_capture_to_research_preserves_exact_hundred_member_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    missing: int | str | None,
) -> None:
    sessions = tuple(
        date(2026, 7, 29) + timedelta(days=offset)
        for offset in range(29)
        if (date(2026, 7, 29) + timedelta(days=offset)).weekday() < 5
    )
    monkeypatch.setitem(globals(), "_SESSIONS", sessions)
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    members = tuple(_instrument(index) for index in range(100))
    local = (
        {member.isin for member in members}
        if missing == "all"
        else (set() if missing is None else {members[missing].isin})
    )
    client = _Client(local=local)
    monkeypatch.setattr(core, "BharatStockClient", lambda: client)
    request = _request(*members)
    request_file = tmp_path / "request.json"
    request_file.write_bytes(core._line(request.canonical_value()))
    request_file.chmod(0o600)
    arguments = [
        "--request-file",
        str(request_file),
        "--storage-root",
        str(capture_root),
        "--schedule-root",
        str(schedule_root),
        "--output",
        "json",
    ]
    assert main(arguments) == 0
    public = json.loads(capsys.readouterr().out)
    assert all(member.isin not in json.dumps(public) for member in members)
    assert len(client.calls) == 100
    revision = core.read_bharatstock_capture_revision_v2(
        capture_root,
        public["revision_identity_sha256"],
    )
    packet = build_bharatstock_research_packet_v1(revision)
    assert tuple(item.member for item in packet.members) == members
    assert packet.coverage.requested == 100
    assert packet.coverage.observed == 100 - len(local)
    assert packet.coverage.insufficient == len(local)
    assert packet.coverage.not_attempted == 0
    assert packet.aggregate_evidence_state == (
        "OBSERVED" if not local else "INSUFFICIENT_EVIDENCE"
    )
    for item in packet.members:
        if item.member.isin in local:
            assert item.evidence_state == "INSUFFICIENT_EVIDENCE"
            assert item.reason == "EMPTY_HISTORY"
            assert item.price_action is None
        else:
            assert item.evidence_state == "OBSERVED"
            assert item.price_action.range_size == Decimal("2")
            assert item.price_action.close_to_previous_close_distance == Decimal("0")
            assert item.market_structure.calculation.trend == "INSUFFICIENT_STRUCTURE"
            assert item.adjusted_bars[-1].session == sessions[-1]
    if missing == 99:
        independent = core.capture_bharatstock_v2(
            _request(*members[:-1]),
            capture_root,
            schedule_root,
            client=client,
        )
        baseline = build_bharatstock_research_packet_v1(independent.revision)
        assert tuple(item.price_action for item in packet.members[:-1]) == tuple(
            item.price_action for item in baseline.members
        )
        assert tuple(item.history for item in revision.members[:-1]) == tuple(
            item.history for item in independent.revision.members
        )
    environment = dict(os.environ)
    environment.pop("BHARATSTOCK_API_KEY", None)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    warm = subprocess.run(  # noqa: S603 - fixed interpreter/module and private fixture paths
        [
            sys.executable,
            "-m",
            "swing_trading_ai_assistant.entrypoints.capture_forward_adjusted_ohlcv",
            *arguments,
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert warm.returncode == 0, warm.stderr
    reused = json.loads(warm.stdout)
    assert reused["code"] == "REUSED"
    assert reused["revision_identity_sha256"] == public["revision_identity_sha256"]


def test_partial_directory_open_failure_releases_already_open_descriptors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    original = core._open_directory
    opened: list[int] = []

    def fail_prepared(operation: object, parent: object, name: str, *, create: bool):
        if name == "prepared":
            raise OSError("cannot open prepared directory")
        result = original(operation, parent, name, create=create)
        if name in {"requests", "revisions"}:
            opened.append(result.descriptor)
        return result

    monkeypatch.setattr(core, "_open_directory", fail_prepared)
    result = core.capture_bharatstock_v2(
        _request(),
        capture_root,
        schedule_root,
        client=_Client(),
    )
    assert result.code == "STORE_UNAVAILABLE"
    assert len(opened) == 2
    for descriptor in opened:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_price_correction_keeps_original_immutable_evidence_readable(
    tmp_path: Path,
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    first = core.capture_bharatstock_v2(
        _request(), root, schedule_root, client=_Client()
    )

    class CorrectedClient(_Client):
        def history(
            self,
            instrument: BharatStockInstrument,
            start: date,
            end: date,
            *,
            effect_guard: Callable[[], None] | None = None,
        ) -> BharatStockHistory:
            original = super().history(
                instrument, start, end, effect_guard=effect_guard
            )
            return replace(
                original,
                rows=tuple(
                    replace(
                        row, close=Decimal("100.5"), adjusted_close=Decimal("100.5")
                    )
                    for row in original.rows
                ),
                response_sha256s=("a" * 64, "b" * 64),
            )

    correction_request = _request(parent=first.revision.revision_identity_sha256)
    client = CorrectedClient()
    corrected = core.capture_bharatstock_v2(
        correction_request, root, schedule_root, client=client
    )
    assert corrected.code == "CAPTURED"
    assert corrected.revision.members[0].history.rows[-1].close == Decimal("100.5")
    assert first.revision.members[0].history.rows[-1].close == Decimal("100")
    assert (
        corrected.revision.revision_identity_sha256
        != first.revision.revision_identity_sha256
    )
    assert (
        core.read_bharatstock_capture_revision_v2(
            root, first.revision.revision_identity_sha256
        )
        == first.revision
    )
    assert (
        core.read_bharatstock_capture_revision_v2(
            root, corrected.revision.revision_identity_sha256
        )
        == corrected.revision
    )
    assert (
        core.capture_bharatstock_v2(
            correction_request, root, schedule_root, client=client
        ).code
        == "REUSED"
    )
    assert len(client.calls) == 1


def test_correction_admission_preserves_the_readable_lineage_limit(
    tmp_path: Path,
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    client = _ChangingClient()
    parent = None
    for _ in range(64):
        request = _request(parent=parent)
        result = core.capture_bharatstock_v2(
            request, root, schedule_root, client=client
        )
        assert result.code == "CAPTURED"
        parent = result.revision.revision_identity_sha256
    assert core.read_bharatstock_capture_revision_v2(root, parent) == result.revision
    before = {path: path.read_bytes() for path in root.rglob("*.json")}
    rejected = core.capture_bharatstock_v2(
        _request(parent=parent), root, schedule_root, client=client
    )
    assert (rejected.code, rejected.reason) == (
        "INSUFFICIENT_EVIDENCE",
        "CORRECTION_LINEAGE_LIMIT",
    )
    assert rejected.revision is None
    assert len(client.calls) == 64
    assert {path: path.read_bytes() for path in root.rglob("*.json")} == before
    assert (
        core.capture_bharatstock_v2(request, root, schedule_root, client=client).code
        == "REUSED"
    )
    assert len(client.calls) == 64


@pytest.mark.parametrize(
    ("prepared", "unchanged"), [(False, False), (True, False), (True, True)]
)
def test_fresh_and_prepared_corrections_enforce_parent_evidence(
    tmp_path: Path, prepared: bool, unchanged: bool
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    parent = core.capture_bharatstock_v2(
        _request(),
        root,
        schedule_root,
        client=_Client(),
        clock=lambda: _NOW + timedelta(seconds=1),
    ).revision
    request = _request(parent=parent.revision_identity_sha256)
    client = _Client() if unchanged else _ChangingClient()
    observed_at = parent.observed_at if unchanged else _NOW
    if prepared:
        revision = core._acquire_revision(  # pyright: ignore[reportPrivateUsage]
            request, client, lambda: observed_at
        )
        path = (
            root
            / "bharatstock-capture-v3"
            / "prepared"
            / f"{request.request_identity_sha256}.json"
        )
        path.write_bytes(revision.canonical_json_bytes())
        path.chmod(0o600)
        client = _Client()
    before = {path: path.read_bytes() for path in root.rglob("*.json")}
    result = core.capture_bharatstock_v2(
        request, root, schedule_root, client=client, clock=lambda: observed_at
    )
    assert (result.code, result.reason) == (
        "INSUFFICIENT_EVIDENCE",
        "CORRECTION_CONTENT_UNCHANGED" if unchanged else "CORRECTION_OBSERVATION_ORDER",
    )
    assert result.revision is None
    assert {path: path.read_bytes() for path in root.rglob("*.json")} == before
    assert (
        core.read_bharatstock_capture_revision_v2(root, parent.revision_identity_sha256)
        == parent
    )
    assert len(client.calls) == (0 if prepared else 1)


@pytest.mark.parametrize("access", ["reader", "reuse", "recovery"])
def test_invalid_retained_decimal_returns_governed_failure(
    tmp_path: Path, access: str
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    request = _request()
    first = core.capture_bharatstock_v2(
        request, root, schedule_root, client=_Client()
    ).revision
    namespace = root / "bharatstock-capture-v3"
    path = namespace / "revisions" / f"{first.revision_identity_sha256}.json"
    value = json.loads(path.read_bytes())
    value["members"][0]["history"]["rows"][0]["open"] = "not-a-decimal"
    if access == "recovery":
        path.unlink()
        (namespace / "requests" / f"{request.request_identity_sha256}.json").unlink()
        path = namespace / "prepared" / f"{request.request_identity_sha256}.json"
    path.chmod(0o600)
    path.write_bytes(
        (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    path.chmod(0o600 if access == "recovery" else 0o400)
    if access == "reader":
        with pytest.raises(core.CaptureRevisionUnavailableV2):
            core.read_bharatstock_capture_revision_v2(
                root, first.revision_identity_sha256
            )
    else:
        client = _Client()
        result = core.capture_bharatstock_v2(
            request, root, schedule_root, client=client
        )
        assert result.code == "STORE_UNAVAILABLE"
        assert result.revision is None
        assert client.calls == []


@pytest.mark.parametrize("access", ["capture", "reader", "schedule", "deadline"])
def test_root_lease_cleanup_failure_returns_governed_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, access: str
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    request = _request()
    first = core.capture_bharatstock_v2(
        request, root, schedule_root, client=_Client()
    ).revision
    acquire = core._acquire_root  # pyright: ignore[reportPrivateUsage]
    close = StorageRootLease.close
    target = None
    target_root = schedule_root if access == "schedule" else root

    def acquire_target(path):
        nonlocal target
        lease = acquire(path)
        if path == target_root:
            target = lease
        return lease

    def failing_close(lease):
        close(lease)
        if lease is target:
            raise StorageRootLeaseError("descriptor cleanup failed")

    monkeypatch.setattr(core, "_acquire_root", acquire_target)
    monkeypatch.setattr(StorageRootLease, "close", failing_close)
    if access == "reader":
        with pytest.raises(core.CaptureRevisionUnavailableV2):
            core.read_bharatstock_capture_revision_v2(
                root, first.revision_identity_sha256
            )
    else:
        client = _Client()
        if access == "deadline":
            request = _request(_instrument(1))
        result = core.capture_bharatstock_v2(
            request,
            root,
            schedule_root,
            client=client,
            clock=(lambda: _NOW + timedelta(hours=2)) if access == "deadline" else None,
        )
        assert result.code == (
            "INSUFFICIENT_EVIDENCE" if access == "schedule" else "STORE_UNAVAILABLE"
        )
        assert result.revision is None
        assert client.calls == []


def test_malformed_retained_revision_is_unavailable_not_an_internal_key_error(
    tmp_path: Path,
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    first = core.capture_bharatstock_v2(
        _request(), root, schedule_root, client=_Client()
    )
    identity = first.revision.revision_identity_sha256
    path = root / "bharatstock-capture-v3" / "revisions" / f"{identity}.json"
    path.chmod(0o600)
    path.write_bytes(b"{}\n")
    path.chmod(0o400)
    with pytest.raises(core.CaptureRevisionUnavailableV2):
        core.read_bharatstock_capture_revision_v2(root, identity)
    client = _Client()
    assert (
        core.capture_bharatstock_v2(_request(), root, schedule_root, client=client).code
        == "STORE_UNAVAILABLE"
    )
    assert client.calls == []


def test_new_request_parser_rejects_predecessor_identity_without_writing() -> None:
    request = _request()
    predecessor = request.canonical_value()
    predecessor["contract_version"] = "bharatstock-capture@v2"
    predecessor["schema_identity_sha256"] = (
        "16a032ed40ed922c9d5d9a16c6abc3dff2297e12554ffce9b75f770b55136990"
    )
    predecessor["runtime_code_identity_sha256"] = (
        "fcd99dbbfbf8b969d34d11d72bbcfd089f4dbaaf2ba883d7cadc47ba34e99f43"
    )
    predecessor["configuration_identity_sha256"] = (
        "21cc3f28838938411836094184a77ad0d39b24fd0f110b30854978c4549f2ced"
    )
    predecessor.pop("request_identity_sha256")
    predecessor["request_identity_sha256"] = core._digest(  # pyright: ignore[reportPrivateUsage]
        core._canonical(predecessor)  # pyright: ignore[reportPrivateUsage]
    )

    with pytest.raises(ValueError, match="request JSON is invalid"):
        core.parse_bharatstock_capture_request_v2(core._line(predecessor))  # pyright: ignore[reportPrivateUsage]


def test_prepared_publication_primary_survives_close_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    request = _request()
    request_name = f"{request.request_identity_sha256}.json"
    primary = AssertionError("prepared readback failure")
    secondary = OSError("prepared close failure")
    open_file, read, close = os.open, os.read, os.close
    owned: set[int] = set()
    descriptors: list[int] = []
    close_attempts: list[int] = []

    def track_open(path, flags, *args, **kwargs):
        descriptor = open_file(path, flags, *args, **kwargs)
        if (
            path == request_name
            and flags & os.O_RDWR
            and kwargs.get("dir_fd") is not None
        ):
            owned.add(descriptor)
            descriptors.append(descriptor)
        return descriptor

    def fail_read(descriptor, size):
        if descriptor in owned:
            raise primary
        return read(descriptor, size)

    def fail_after_close(descriptor):
        if descriptor in owned:
            owned.remove(descriptor)
            close_attempts.append(descriptor)
            close(descriptor)
            raise secondary
        close(descriptor)

    monkeypatch.setattr(os, "open", track_open)
    monkeypatch.setattr(os, "read", fail_read)
    monkeypatch.setattr(os, "close", fail_after_close)

    with pytest.raises(AssertionError) as raised:
        core.capture_bharatstock_v2(request, root, schedule_root, client=_Client())

    assert raised.value is primary
    assert close_attempts == descriptors
    assert owned == set()


def test_publication_commit_primary_survives_close_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    request = _request()
    request_name = f"{request.request_identity_sha256}.json"
    primary = AssertionError("commit readback failure")
    secondary = OSError("publication close failure")
    open_file, read, close = os.open, os.read, os.close
    owned: set[int] = set()
    descriptors: list[int] = []
    close_attempts: list[int] = []

    def track_open(path, flags, *args, **kwargs):
        descriptor = open_file(path, flags, *args, **kwargs)
        if (
            path != request_name
            and flags & os.O_RDWR
            and isinstance(path, str)
            and path.endswith(".json")
            and kwargs.get("dir_fd") is not None
        ):
            owned.add(descriptor)
            descriptors.append(descriptor)
        return descriptor

    def fail_read(descriptor, size):
        if descriptor in owned:
            raise primary
        return read(descriptor, size)

    def fail_after_close(descriptor):
        if descriptor in owned:
            owned.remove(descriptor)
            close_attempts.append(descriptor)
            close(descriptor)
            raise secondary
        close(descriptor)

    monkeypatch.setattr(os, "open", track_open)
    monkeypatch.setattr(os, "read", fail_read)
    monkeypatch.setattr(os, "close", fail_after_close)

    with pytest.raises(AssertionError) as raised:
        core.capture_bharatstock_v2(request, root, schedule_root, client=_Client())

    assert raised.value is primary
    assert close_attempts == descriptors
    assert owned == set()


@pytest.mark.parametrize("stage", ["open", "recover"])
def test_interrupted_publication_recovery_primary_survives_close_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    request = _request()
    request_name = f"{request.request_identity_sha256}.json"
    client = _Client()
    publish = held_store.publish_capture_bytes

    def interrupt_request_pointer(operation, directory, name, raw):
        if name == request_name:
            raise OSError("interrupted before request admission")
        publish(operation, directory, name, raw)

    monkeypatch.setattr(held_store, "publish_capture_bytes", interrupt_request_pointer)
    interrupted = core.capture_bharatstock_v2(
        request, root, schedule_root, client=client
    )
    assert interrupted.code == "STORE_UNAVAILABLE"
    monkeypatch.setattr(held_store, "publish_capture_bytes", publish)
    revision_paths = tuple(
        (root / "bharatstock-capture-v3" / "revisions").glob("*.json")
    )
    assert len(revision_paths) == 1
    target_name = revision_paths[0].name
    primary = AssertionError(f"recovery {stage} failure")
    secondary = OSError("recovery close failure")
    open_file, close = os.open, os.close
    operation_name = "fstat" if stage == "open" else "fsync"
    operation = getattr(os, operation_name)
    owned: set[int] = set()
    descriptors: list[int] = []
    close_attempts: list[int] = []

    def track_open(path, flags, *args, **kwargs):
        descriptor = open_file(path, flags, *args, **kwargs)
        if path == target_name and kwargs.get("dir_fd") is not None:
            owned.add(descriptor)
            descriptors.append(descriptor)
        return descriptor

    def fail_operation(descriptor):
        if descriptor in owned:
            raise primary
        return operation(descriptor)

    def fail_after_close(descriptor):
        if descriptor in owned:
            owned.remove(descriptor)
            close_attempts.append(descriptor)
            close(descriptor)
            raise secondary
        close(descriptor)

    monkeypatch.setattr(os, "open", track_open)
    monkeypatch.setattr(os, operation_name, fail_operation)
    monkeypatch.setattr(os, "close", fail_after_close)

    with pytest.raises(AssertionError) as raised:
        core.capture_bharatstock_v2(request, root, schedule_root, client=client)

    assert raised.value is primary
    assert len(client.calls) == 1
    assert close_attempts == descriptors
    assert owned == set()


@pytest.mark.parametrize("access", ["prepared", "publication", "exact_file"])
def test_standalone_publication_close_failure_surfaces_cleanup_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, access: str
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    request = _request()
    request_name = f"{request.request_identity_sha256}.json"
    secondary = OSError("standalone publication close failure")
    close_attempts: list[int] = []
    revision_id: str | None = None

    if access == "prepared":
        close = held_store._HeldRecoverablePublication.close  # pyright: ignore[reportPrivateUsage]

        def fail_after_close(publication):
            descriptor = publication.descriptor
            close(publication)
            close_attempts.append(descriptor)
            raise secondary

        monkeypatch.setattr(
            held_store._HeldRecoverablePublication,  # pyright: ignore[reportPrivateUsage]
            "close",
            fail_after_close,
        )
    else:
        if access == "exact_file":
            captured = core.capture_bharatstock_v2(
                request, root, schedule_root, client=_Client()
            )
            assert captured.revision is not None
            revision_id = captured.revision.revision_identity_sha256
        target_name = f"{revision_id}.json"
        open_file, close = os.open, os.close
        owned: set[int] = set()

        def track_open(path, flags, *args, **kwargs):
            descriptor = open_file(path, flags, *args, **kwargs)
            if kwargs.get("dir_fd") is not None and (
                (access == "exact_file" and path == target_name)
                or (
                    access == "publication"
                    and flags & os.O_RDWR
                    and isinstance(path, str)
                    and path.endswith(".json")
                    and path != request_name
                )
            ):
                owned.add(descriptor)
            return descriptor

        def fail_after_close(descriptor):
            if descriptor in owned:
                owned.remove(descriptor)
                close_attempts.append(descriptor)
                close(descriptor)
                raise secondary
            close(descriptor)

        monkeypatch.setattr(os, "open", track_open)
        monkeypatch.setattr(os, "close", fail_after_close)

    with pytest.raises(RuntimeError) as raised:
        try:
            raise FileNotFoundError("already handled lookup miss")
        except FileNotFoundError:
            if access != "exact_file":
                core.capture_bharatstock_v2(
                    request, root, schedule_root, client=_Client()
                )
            else:
                assert revision_id is not None
                core.read_bharatstock_capture_revision_v2(root, revision_id)

    assert raised.value.__cause__ is secondary
    assert len(close_attempts) == 1


def test_prepared_publication_cancellation_closes_its_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    request = _request()
    request_name = f"{request.request_identity_sha256}.json"
    cancellation = asyncio.CancelledError("capture cancelled")
    open_file, write, fstat, close = os.open, os.write, os.fstat, os.close
    owned: set[int] = set()
    descriptors: list[int] = []
    close_attempts: list[int] = []

    def track_open(path, flags, *args, **kwargs):
        descriptor = open_file(path, flags, *args, **kwargs)
        if (
            path == request_name
            and flags & os.O_RDWR
            and kwargs.get("dir_fd") is not None
        ):
            owned.add(descriptor)
            descriptors.append(descriptor)
        return descriptor

    def cancel_write(descriptor, data):
        if descriptor in owned:
            raise cancellation
        return write(descriptor, data)

    def track_close(descriptor):
        if descriptor in owned:
            owned.remove(descriptor)
            close_attempts.append(descriptor)
        close(descriptor)

    monkeypatch.setattr(os, "open", track_open)
    monkeypatch.setattr(os, "write", cancel_write)
    monkeypatch.setattr(os, "close", track_close)

    try:
        with pytest.raises(asyncio.CancelledError) as raised:
            core.capture_bharatstock_v2(request, root, schedule_root, client=_Client())

        assert raised.value is cancellation
        assert close_attempts == descriptors
        assert owned == set()
        with pytest.raises(OSError):
            fstat(descriptors[0])
    finally:
        for descriptor in tuple(owned):
            close(descriptor)
            owned.remove(descriptor)


def test_recoverable_publication_constructor_failure_closes_open_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    lease = core._acquire_root(root)  # pyright: ignore[reportPrivateUsage]
    assert lease is not None
    name = "prepared.json"
    content = b'{"publication":"prepared"}\n'

    with (
        lease,
        lease.root_operation(root) as operation,
        held_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
            operation, operation.descriptor, "prepared", create=True
        ) as prepared,
    ):
        held = held_store.prepare_capture_publication(
            operation, prepared, name, content
        )
        held.close()
        primary = MemoryError("recoverable publication construction failed")
        open_file, fstat, close = os.open, os.fstat, os.close
        owned: set[int] = set()
        descriptors: list[int] = []
        close_attempts: list[int] = []

        def track_open(path, flags, *args, **kwargs):
            descriptor = open_file(path, flags, *args, **kwargs)
            if path == name and kwargs.get("dir_fd") is not None:
                owned.add(descriptor)
                descriptors.append(descriptor)
            return descriptor

        def track_close(descriptor):
            if descriptor in owned:
                owned.remove(descriptor)
                close_attempts.append(descriptor)
            close(descriptor)

        class FailingHeldPublication:
            def __init__(self, *args) -> None:
                raise primary

        monkeypatch.setattr(os, "open", track_open)
        monkeypatch.setattr(os, "close", track_close)
        monkeypatch.setattr(
            held_store,
            "_HeldRecoverablePublication",
            FailingHeldPublication,
        )

        try:
            with pytest.raises(MemoryError) as raised:
                held_store.prepare_capture_publication(
                    operation, prepared, name, content
                )

            assert raised.value is primary
            assert close_attempts == descriptors
            assert owned == set()
            with pytest.raises(OSError):
                fstat(descriptors[0])
        finally:
            for descriptor in tuple(owned):
                close(descriptor)
                owned.remove(descriptor)


def test_recovery_name_disappearance_never_republishes_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    request = _request()
    request_name = f"{request.request_identity_sha256}.json"
    client = _Client()
    publish = held_store.publish_capture_bytes

    def interrupt_request_pointer(operation, directory, name, raw):
        if name == request_name:
            raise OSError("interrupted before request admission")
        publish(operation, directory, name, raw)

    monkeypatch.setattr(held_store, "publish_capture_bytes", interrupt_request_pointer)
    assert (
        core.capture_bharatstock_v2(request, root, schedule_root, client=client).code
        == "STORE_UNAVAILABLE"
    )
    monkeypatch.setattr(held_store, "publish_capture_bytes", publish)
    (target,) = (root / "bharatstock-capture-v3" / "revisions").glob("*.json")
    original = target.read_bytes()
    detached = tmp_path / "detached-revision.json"
    stat = os.stat
    disappeared = False

    def disappear_after_open(path, *args, **kwargs):
        nonlocal disappeared
        if not disappeared and path == target.name and kwargs.get("dir_fd") is not None:
            disappeared = True
            target.rename(detached)
        return stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", disappear_after_open)
    result = core.capture_bharatstock_v2(request, root, schedule_root, client=client)
    assert disappeared
    assert result.code == "STORE_UNAVAILABLE"
    assert result.revision is None
    assert len(client.calls) == 1
    assert not target.exists()
    assert detached.read_bytes() == original
    assert not (root / "bharatstock-capture-v3" / "requests" / request_name).exists()


def test_borrowed_exact_root_lease_remains_caller_owned_after_capture(
    tmp_path: Path,
) -> None:
    root = tmp_path / "shared-root"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire_private_empty(root)
    assert acquired.outcome is LeaseOutcome.ACQUIRED and acquired.lease is not None
    lease = acquired.lease
    request = _request()
    try:
        retained = ScheduleEvidenceStore(root, lease).retain(_schedule())
        assert retained.outcome is ScheduleOutcome.RETAINED
        result = core.capture_bharatstock_v2(
            request, root, root, client=_Client(), lease=lease
        )
        assert result.code == "CAPTURED"
        assert result.revision is not None
        assert (
            core.read_bharatstock_capture_revision_v2(
                root, result.revision.revision_identity_sha256, lease=lease
            )
            == result.revision
        )
        with lease.read_operation(root):
            pass
    finally:
        lease.close()
    denied = _Client()
    assert (
        core.capture_bharatstock_v2(
            request, root, root, client=denied, lease=lease
        ).code
        == "STORE_UNAVAILABLE"
    )
    assert denied.calls == []


def test_borrowed_foreign_lease_cannot_authorize_capture_or_read(
    tmp_path: Path,
) -> None:
    root, other = tmp_path / "capture", tmp_path / "other"
    root.mkdir(mode=0o700)
    other.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire_private_empty(other)
    assert acquired.lease is not None
    client = _Client()
    with acquired.lease as lease:
        result = core.capture_bharatstock_v2(
            _request(), root, root, client=client, lease=lease
        )
        assert result.code == "STORE_UNAVAILABLE" and client.calls == []
        with pytest.raises(core.CaptureRevisionUnavailableV2):
            core.read_bharatstock_capture_revision_v2(root, "0" * 64, lease=lease)
        with lease.read_operation(other):
            pass
    assert list(root.iterdir()) == []


def test_pr185_v3_evidence_stays_readable_but_cannot_be_used_by_current_writer(
    tmp_path: Path,
) -> None:
    # Generated by exact PR185 wheel 7d9794ab...fb19f9, not today's constructor.
    raw = (
        Path(__file__).parents[1]
        / "fixtures"
        / "market_data"
        / "bharatstock-pr185-v3.json"
    ).read_bytes()
    value = json.loads(raw)
    revision_sha = value["revision_identity_sha256"]
    request_sha = value["request"]["request_identity_sha256"]
    acquired = StorageRootLease.try_acquire_private_empty(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        namespace = tmp_path / "bharatstock-capture-v3"
        namespace.mkdir(mode=0o700)
        revisions = namespace / "revisions"
        requests = namespace / "requests"
        revisions.mkdir(mode=0o700)
        requests.mkdir(mode=0o700)
        revision_path = revisions / f"{revision_sha}.json"
        revision_path.write_bytes(raw)
        revision_path.chmod(0o400)
        request_path = requests / f"{request_sha}.json"
        request_path.write_bytes(
            json.dumps(
                {
                    "request_identity_sha256": request_sha,
                    "revision_identity_sha256": revision_sha,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
            + b"\n"
        )
        request_path.chmod(0o400)
        retained = core.read_bharatstock_capture_revision_v2(
            tmp_path, revision_sha, lease=acquired.lease
        )
        assert retained.canonical_json_bytes() == raw
        assert retained.request.runtime_code_identity_sha256 == (
            "bcda597760ea97f8a0762845e32ef8fe4532a1b93dfd4876cf0df418b88bd49d"
        )
        packet = build_bharatstock_research_packet_v1(retained)
        assert packet.members[0].price_action_evidence_state == "OBSERVED"
        client = _Client()
        with pytest.raises(ValueError):
            core.capture_bharatstock_v2(
                retained.request,
                tmp_path,
                tmp_path,
                client=client,
                lease=acquired.lease,
            )
        with pytest.raises(ValueError):
            core.parse_bharatstock_capture_request_v2(
                json.dumps(
                    value["request"], separators=(",", ":"), sort_keys=True
                ).encode()
                + b"\n"
            )
        with pytest.raises(ValueError):
            replace(retained.request, runtime_code_identity_sha256="0" * 64)
        assert client.calls == []
        assert revision_path.read_bytes() == raw


@pytest.mark.parametrize("access", ["capture", "read"])
def test_borrowed_generic_lease_cannot_admit_a_shared_root(
    tmp_path: Path, access: str
) -> None:
    root = tmp_path / "root"
    _retain_schedule(root)
    first = core.capture_bharatstock_v2(_request(), root, root, client=_Client())
    assert first.revision is not None
    root.chmod(0o755)
    generic = StorageRootLease.try_acquire(root)
    assert generic.outcome is LeaseOutcome.ACQUIRED and generic.lease is not None
    with generic.lease:
        if access == "read":
            with pytest.raises(core.CaptureRevisionUnavailableV2):
                core.read_bharatstock_capture_revision_v2(
                    root, first.revision.revision_identity_sha256, lease=generic.lease
                )
        else:
            client = _Client()
            result = core.capture_bharatstock_v2(
                replace(_request(), decision_cutoff=_NOW + timedelta(hours=2)),
                root,
                root,
                client=client,
                lease=generic.lease,
            )
            assert result.code == "STORE_UNAVAILABLE" and client.calls == []
        with generic.lease.read_operation(root):
            pass


@pytest.mark.parametrize("failure", ["deadline", "root", "private_mode"])
def test_inner_price_request_stops_after_guard_loss(
    tmp_path: Path, failure: str
) -> None:
    root = tmp_path / "root"
    _retain_schedule(root)
    request = _request()
    current_time = [_NOW]
    requests: list[str] = []

    class Transport:
        def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
            requests.append(url)
            assert len(requests) == 1, "a second HTTP request followed guard loss"
            if failure == "deadline":
                current_time[0] = request.decision_cutoff + timedelta(microseconds=1)
            elif failure == "root":
                root.rename(tmp_path / "displaced")
                root.mkdir(mode=0o700)
            else:
                root.chmod(0o755)
            instrument = request.members[0]
            return HttpResponse(
                200,
                json.dumps(
                    {
                        "isin": instrument.isin,
                        "exchange": "NSE",
                        "symbol": instrument.symbol,
                    }
                ).encode(),
                request_url=url,
                response_url=url,
            )

    result = core.capture_bharatstock_v2(
        request,
        root,
        root,
        client=BharatStockClient(api_key="synthetic-test-key", transport=Transport()),
        clock=lambda: current_time[0],
    )
    assert len(requests) == 1 and result.revision is None
    if failure == "deadline":
        assert result.reason == "ACQUISITION_DEADLINE_EXCEEDED"
    else:
        assert result.code == "STORE_UNAVAILABLE"


@pytest.mark.parametrize(
    "writer",
    [
        "c5f74daf212167b3d4dac510e83e5602b2dbafa0d02a9dc9036b7c9c9cd81c10",
        "c903f7c2e87a867c0aa8d76c1056c08d72bd91a005f670c9028d4970bb177cb3",
        "29698ddcb2499ebbbee3030c731147855ba0f99a57ceac65456a93648deb9f0c",
    ],
)
def test_released_v3_capture_is_readable_without_authorizing_new_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, writer: str
) -> None:
    root = tmp_path / "capture"
    _retain_schedule(root)
    current_request = _request()
    with monkeypatch.context() as old_writer:
        old_writer.setattr(core, "_runtime_identity", lambda: writer)
        request = replace(current_request, runtime_code_identity_sha256=writer)
        captured = core.capture_bharatstock_v2(request, root, root, client=_Client())
        assert captured.revision is not None
        raw = captured.revision.canonical_json_bytes()
        revision_sha = captured.revision.revision_identity_sha256
        comparison_capture = core.capture_bharatstock_v2(
            replace(request, sessions=_SESSIONS[-2:]), root, root, client=_Client()
        )
        assert comparison_capture.revision is not None
        comparison_sha = comparison_capture.revision.revision_identity_sha256
    original_files = {path: path.read_bytes() for path in root.rglob("*.json")}
    retained = core.read_bharatstock_capture_revision_v2(root, revision_sha)
    core.validate_capture_revision_v2(retained)
    assert retained.canonical_json_bytes() == raw
    assert retained.request.runtime_code_identity_sha256 == writer
    packet = build_bharatstock_research_packet_v1(retained)
    assert packet.members[0].price_action_evidence_state == "OBSERVED"
    binding = core.read_bharatstock_capture_binding_v2(root, comparison_sha)
    admitted = core.validate_retained_capture_binding_v2(binding)
    source = bharatstock_v2._source(  # pyright: ignore[reportPrivateUsage]
        "PREVIOUS_CLOSE_COMPARISON",
        admitted,
        bharatstock_v2.bharatstock_research_runtime_code_identity_v2(),
    )
    assert source.capture_runtime_code_identity_sha256 == writer
    assert source.capture_revision_identity_sha256 == comparison_sha
    with pytest.raises(ValueError):
        replace(source, capture_runtime_code_identity_sha256="0" * 64)
    with pytest.raises(ValueError):
        replace(source, price_basis="BHARATSTOCK_SPLIT_BONUS_FACTOR_ADJUSTED_OHLC")
    client = _Client()
    with pytest.raises(ValueError):
        core.validate_current_capture_request_v2(retained.request)
    with pytest.raises(ValueError):
        core.capture_bharatstock_v2(retained.request, root, root, client=client)
    with pytest.raises(ValueError):
        core.parse_bharatstock_capture_request_v2(
            json.dumps(retained.request.canonical_value(), sort_keys=True).encode()
        )
    with pytest.raises(ValueError):
        replace(retained.request, runtime_code_identity_sha256="0" * 64)
    forged = replace(retained)
    object.__setattr__(forged.request, "runtime_code_identity_sha256", "0" * 64)
    with pytest.raises(ValueError):
        core.validate_capture_revision_v2(forged)
    assert client.calls == []
    assert {path: path.read_bytes() for path in root.rglob("*.json")} == original_files
