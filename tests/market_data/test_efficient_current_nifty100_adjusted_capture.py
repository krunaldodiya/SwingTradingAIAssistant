from __future__ import annotations

import csv
import io
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data import bharatstock_capture as capture
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockDailyPrice,
    BharatStockError,
    BharatStockHistory,
    BharatStockInstrument,
)
from swing_trading_ai_assistant.market_data.efficient_current_nifty100_adjusted_capture import (
    NIFTY_50_URL,
    NIFTY_100_URL,
    NIFTY_NEXT_50_URL,
    OfficialSourceFetcherV2,
    SourceResponseV2,
    admit_current_nifty100_selection_v2,
    capture_current_nifty100_v2,
    project_current_nifty100_capture_v2,
)
from swing_trading_ai_assistant.market_data.efficient_current_nifty100_adjusted_capture_cli import (
    _run as run_capture_cli,
)
from swing_trading_ai_assistant.market_data.http import UrllibHttpTransport
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleEvidenceStore,
    ScheduleOutcome,
    ScheduleSession,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)


def _rows(start: int, count: int) -> list[tuple[str, str, str, str, str]]:
    return [
        (f"Company {item}", "Industry", f"S{item:03d}", "EQ", f"INE{item:09d}")
        for item in range(start, start + count)
    ]


def _csv(rows: list[tuple[str, str, str, str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("Company Name", "Industry", "Symbol", "Series", "ISIN Code"))
    writer.writerows(rows)
    return output.getvalue().encode()


class _Fetcher:
    def __init__(self, *, inconsistent: bool = False) -> None:
        witness = _rows(0 if not inconsistent else 1, 100)
        self.retrieved_at = datetime(2026, 8, 27, tzinfo=UTC)
        self.bodies = {
            NIFTY_50_URL: _csv(_rows(0, 50)),
            NIFTY_NEXT_50_URL: _csv(_rows(50, 50)),
            NIFTY_100_URL: _csv(witness),
        }

    def get(self, url: str) -> SourceResponseV2:
        return SourceResponseV2(url, url, 200, self.bodies[url], self.retrieved_at)


def test_selector_rejects_future_known_witnesses() -> None:
    future = _Fetcher()
    future.bodies[NIFTY_100_URL] = _csv(_rows(0, 99) + _rows(101, 1))
    assert admit_current_nifty100_selection_v2(future) is None


def test_selector_rejects_conflicting_member_identity() -> None:
    fetcher = _Fetcher()
    rows = _rows(0, 100)
    rows[99] = ("Company 99", "Industry", "S099", "EQ", "INE000000000")
    fetcher.bodies[NIFTY_100_URL] = _csv(rows)
    assert admit_current_nifty100_selection_v2(fetcher) is None


def test_official_selector_proves_membership_and_source_identity() -> None:
    selection = admit_current_nifty100_selection_v2(_Fetcher())

    assert selection is not None
    assert len(selection.members) == 100
    assert selection.members[:2] == (
        BharatStockInstrument("INE000000000", "NSE", "S000"),
        BharatStockInstrument("INE000000001", "NSE", "S001"),
    )
    assert admit_current_nifty100_selection_v2(_Fetcher(inconsistent=True)) is None


def test_public_projection_accounts_for_every_member_when_capture_store_fails() -> None:
    selection = admit_current_nifty100_selection_v2(_Fetcher())
    assert selection is not None

    result = project_current_nifty100_capture_v2(
        selection,
        capture.CaptureResultV2("STORE_UNAVAILABLE", None, "STORE_UNAVAILABLE"),
    )

    assert result.code == "INCOMPLETE_CURRENT_NIFTY100_CAPTURE"
    assert result.requested_members == 100
    assert result.observed_members == 0
    assert result.insufficient_members == 0
    assert result.unattempted_members == 100
    assert (
        result.requested_members
        == result.observed_members
        + result.insufficient_members
        + result.unattempted_members
    )


def test_public_projection_reports_99_real_histories_and_one_insufficiency() -> None:
    selection = admit_current_nifty100_selection_v2(_Fetcher())
    assert selection is not None
    schedule = _schedule()
    request = capture.CaptureRequestV2(
        members=selection.members,
        sessions=(_SESSION,),
        decision_cutoff=_CAPTURED_AT,
        schedule_evidence_sha256=schedule_digest(schedule),
        schedule_source=schedule.source,
        schedule_source_release=schedule.source_release,
        schedule_identity_sha256=capture.schedule_identity_v2(schedule),
        selection_identity_sha256=selection.selection_identity_sha256,
    )
    row = BharatStockDailyPrice(
        date(2026, 8, 26),
        Decimal("100"),
        Decimal("101"),
        Decimal("99"),
        Decimal("100"),
        1000,
        Decimal("100"),
        Decimal("1"),
    )
    members = tuple(
        capture.CaptureMemberResultV2(
            member,
            "INSUFFICIENT_EVIDENCE",
            "EMPTY_HISTORY",
            None,
        )
        if index == 99
        else capture.CaptureMemberResultV2(
            member,
            "OBSERVED",
            None,
            BharatStockHistory(
                member,
                (row,),
                datetime(2026, 8, 26, tzinfo=UTC),
                ("4" * 64, "5" * 64),
                2,
            ),
        )
        for index, member in enumerate(selection.members)
    )
    revision = capture.CaptureRevisionV2(
        request,
        members,
        capture._coverage_identity(members),  # pyright: ignore[reportPrivateUsage]
        None,
        datetime(2026, 8, 26, tzinfo=UTC),
    )

    result = project_current_nifty100_capture_v2(
        selection, capture.CaptureResultV2("CAPTURED", revision)
    )

    assert result.code == "INCOMPLETE_CURRENT_NIFTY100_CAPTURE"
    assert (
        result.requested_members,
        result.observed_members,
        result.insufficient_members,
        result.unattempted_members,
    ) == (100, 99, 1, 0)


def test_selector_rejects_duplicate_symbols() -> None:
    fetcher = _Fetcher()
    rows = _rows(0, 50)
    rows[-1] = ("Company 49", "Industry", "S000", "EQ", "INE000000049")
    fetcher.bodies[NIFTY_50_URL] = _csv(rows)

    assert admit_current_nifty100_selection_v2(fetcher) is None


_SESSION = date(2026, 8, 26)
_CAPTURED_AT = datetime(2026, 8, 27, 10, tzinfo=UTC)


def _members() -> tuple[BharatStockInstrument, ...]:
    return tuple(
        BharatStockInstrument(f"INE{index:09d}", "NSE", f"S{index:03d}")
        for index in range(100)
    )


def _schedule() -> ExpectedSessionSchedule:
    return ExpectedSessionSchedule(
        schema_version=3,
        source="nse-upstox-composed-calendar",
        source_release=f"composed-calendar@v1={'3' * 64}",
        as_of=_CAPTURED_AT,
        timezone="Asia/Kolkata",
        covered_from=_SESSION,
        covered_to=_SESSION,
        sessions=(
            ScheduleSession(
                _SESSION,
                datetime(2026, 8, 26, 3, 45, tzinfo=UTC),
                datetime(2026, 8, 26, 10, tzinfo=UTC),
                "REGULAR",
            ),
        ),
    )


def _retain_schedule(root: Path) -> ExpectedSessionSchedule:
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire_private_empty(root)
    assert acquired.outcome is LeaseOutcome.ACQUIRED and acquired.lease is not None
    try:
        assert (
            ScheduleEvidenceStore(root, acquired.lease).retain(_schedule()).outcome
            is ScheduleOutcome.RETAINED
        )
    finally:
        acquired.lease.close()
    return _schedule()


def _request(
    members: tuple[BharatStockInstrument, ...],
    parent: str | None = None,
) -> capture.CaptureRequestV2:
    schedule = _schedule()
    return capture.CaptureRequestV2(
        members=members,
        sessions=(_SESSION,),
        decision_cutoff=_CAPTURED_AT,
        schedule_evidence_sha256=schedule_digest(schedule),
        schedule_source=schedule.source,
        schedule_source_release=schedule.source_release,
        schedule_identity_sha256=capture.schedule_identity_v2(schedule),
        selection_identity_sha256=capture.selection_identity_v2(members),
        parent_revision_sha256=parent,
    )


def _write_request(root: Path, request: capture.CaptureRequestV2) -> Path:
    root.mkdir(mode=0o700, exist_ok=True)
    path = root / "request.json"
    path.write_bytes(capture._line(request.canonical_value()))  # pyright: ignore[reportPrivateUsage]
    path.chmod(0o600)
    return path


class _CliFetcher(_Fetcher):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def get(self, url: str) -> SourceResponseV2:
        self.calls.append(url)
        return super().get(url)


class _CliClient:
    def __init__(
        self,
        *,
        local: set[str] | None = None,
        shared_after: int | None = None,
        close: Decimal = Decimal("100"),
    ) -> None:
        self.local = set() if local is None else local
        self.shared_after = shared_after
        self.close = close
        self.calls: list[str] = []

    def history(
        self, instrument: BharatStockInstrument, start: date, end: date
    ) -> BharatStockHistory:
        assert (start, end) == (_SESSION, _SESSION)
        self.calls.append(instrument.isin)
        if self.shared_after is not None and len(self.calls) > self.shared_after:
            raise BharatStockError("RATE_LIMITED", member_local=False)
        if instrument.isin in self.local:
            raise BharatStockError("EMPTY_HISTORY", member_local=True)
        row = BharatStockDailyPrice(
            _SESSION,
            self.close,
            self.close + Decimal("1"),
            self.close - Decimal("1"),
            self.close,
            1000,
            self.close,
            Decimal("1"),
        )
        return BharatStockHistory(
            instrument,
            (row,),
            _CAPTURED_AT,
            ("4" * 64, "5" * 64),
            2,
        )


def _arguments(
    request_file: Path, selection_root: Path, capture_root: Path, schedule_root: Path
) -> list[str]:
    return [
        "--request-file",
        str(request_file),
        "--selection-root",
        str(selection_root),
        "--capture-storage-root",
        str(capture_root),
        "--schedule-root",
        str(schedule_root),
        "--output",
        "json",
    ]


def test_public_cli_cold_warm_reuse_and_distinct_corrections_and_order(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(capture, "_now", lambda: _CAPTURED_AT)
    members = _members()
    request = _request(members)
    selection_root = tmp_path / "selection"
    selection_root.mkdir(mode=0o700)
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    arguments = _arguments(
        _write_request(tmp_path, request),
        selection_root,
        capture_root,
        schedule_root,
    )

    cold_fetcher = _CliFetcher()
    cold_client = _CliClient()
    assert run_capture_cli(arguments, _fetcher=cold_fetcher, _client=cold_client) == 0
    cold = json.loads(capsys.readouterr().out)
    assert cold["code"] == "COMPLETE_CURRENT_NIFTY100_CAPTURE"
    assert (
        cold["requested_members"],
        cold["observed_members"],
        cold["insufficient_members"],
        cold["unattempted_members"],
    ) == (100, 100, 0, 0)
    assert len(cold_fetcher.calls) == 3
    assert len(cold_client.calls) == 100
    assert all(member.isin not in json.dumps(cold) for member in members)

    warm_fetcher = _CliFetcher()
    warm_client = _CliClient()
    assert run_capture_cli(arguments, _fetcher=warm_fetcher, _client=warm_client) == 0
    warm = json.loads(capsys.readouterr().out)
    assert warm == cold
    assert warm_fetcher.calls == []
    assert warm_client.calls == []

    correction = _request(members, cold["revision_identity_sha256"])
    assert correction.request_identity_sha256 != request.request_identity_sha256
    correction_fetcher = _CliFetcher()
    correction_fetcher.retrieved_at = datetime(2026, 8, 27, 9, tzinfo=UTC)
    correction_client = _CliClient(close=Decimal("101"))
    assert (
        run_capture_cli(
            _arguments(
                _write_request(tmp_path / "correction", correction),
                selection_root,
                capture_root,
                schedule_root,
            ),
            _fetcher=correction_fetcher,
            _client=correction_client,
        )
        == 0
    )
    corrected = json.loads(capsys.readouterr().out)
    assert corrected["revision_identity_sha256"] != cold["revision_identity_sha256"]
    assert len(correction_fetcher.calls) == 3
    assert len(correction_client.calls) == 100

    original_fetcher = _CliFetcher()
    original_client = _CliClient()
    assert (
        run_capture_cli(arguments, _fetcher=original_fetcher, _client=original_client)
        == 0
    )
    assert json.loads(capsys.readouterr().out) == cold
    assert original_fetcher.calls == []
    assert original_client.calls == []

    reordered = _request(tuple(reversed(members)))
    assert reordered.selection_identity_sha256 != request.selection_identity_sha256
    assert reordered.request_identity_sha256 != request.request_identity_sha256
    reordered_fetcher = _CliFetcher()
    reordered_client = _CliClient()
    assert (
        run_capture_cli(
            _arguments(
                _write_request(tmp_path / "reordered", reordered),
                selection_root,
                capture_root,
                schedule_root,
            ),
            _fetcher=reordered_fetcher,
            _client=reordered_client,
        )
        == 1
    )
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["reason"] == "CONSTITUENT_SOURCE_CONFLICT"
    assert len(reordered_fetcher.calls) == 3
    assert reordered_client.calls == []


def test_public_cli_reports_full_outcomes_for_storage_local_and_shared_failures(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(capture, "_now", lambda: _CAPTURED_AT)
    members = _members()
    request = _request(members)
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)

    storage_selection = tmp_path / "storage-selection"
    storage_selection.mkdir(mode=0o700)
    storage_client = _CliClient()
    assert (
        run_capture_cli(
            _arguments(
                _write_request(tmp_path / "storage", request),
                storage_selection,
                tmp_path / "missing-capture",
                schedule_root,
            ),
            _fetcher=_CliFetcher(),
            _client=storage_client,
        )
        == 1
    )
    storage = json.loads(capsys.readouterr().out)
    assert (
        storage["requested_members"],
        storage["observed_members"],
        storage["insufficient_members"],
        storage["unattempted_members"],
    ) == (100, 0, 0, 100)
    assert storage["reason"] == "STORAGE_UNSAFE_OR_HELD"
    assert storage_client.calls == []

    local_selection = tmp_path / "local-selection"
    local_selection.mkdir(mode=0o700)
    local_capture = tmp_path / "local-capture"
    local_capture.mkdir(mode=0o700)
    local_client = _CliClient(local={members[-1].isin})
    assert (
        run_capture_cli(
            _arguments(
                _write_request(tmp_path / "local", request),
                local_selection,
                local_capture,
                schedule_root,
            ),
            _fetcher=_CliFetcher(),
            _client=local_client,
        )
        == 1
    )
    local = json.loads(capsys.readouterr().out)
    assert (
        local["requested_members"],
        local["observed_members"],
        local["insufficient_members"],
        local["unattempted_members"],
    ) == (100, 99, 1, 0)
    assert local["reason"] == "MEMBER_EVIDENCE_INSUFFICIENT"
    assert len(local_client.calls) == 100

    shared_selection = tmp_path / "shared-selection"
    shared_selection.mkdir(mode=0o700)
    shared_capture = tmp_path / "shared-capture"
    shared_capture.mkdir(mode=0o700)
    shared_client = _CliClient(shared_after=1)
    assert (
        run_capture_cli(
            _arguments(
                _write_request(tmp_path / "shared", request),
                shared_selection,
                shared_capture,
                schedule_root,
            ),
            _fetcher=_CliFetcher(),
            _client=shared_client,
        )
        == 1
    )
    shared = json.loads(capsys.readouterr().out)
    assert (
        shared["requested_members"],
        shared["observed_members"],
        shared["insufficient_members"],
        shared["unattempted_members"],
    ) == (100, 1, 1, 98)
    assert shared["shared_failure"] == "RATE_LIMITED"
    assert shared["reason"] == "RATE_LIMITED"
    assert len(shared_client.calls) == 2


@pytest.mark.parametrize(
    "url",
    (
        "file:///etc/passwd",
        "https://untrusted.example/ind_nifty50list.csv",
        "https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv",
        NIFTY_50_URL + "?source=other",
    ),
)
def test_official_fetcher_rejects_nonexact_sources_before_transport(url, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("nonofficial source reached transport")

    monkeypatch.setattr(UrllibHttpTransport, "get", forbidden)
    with pytest.raises(ValueError, match="URL unsupported"):
        OfficialSourceFetcherV2().get(url)


def test_retained_observation_time_tampering_blocks_capture_reuse(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(capture, "_now", lambda: _CAPTURED_AT)
    request = _request(_members())
    selection_root = tmp_path / "selection"
    selection_root.mkdir(mode=0o700)
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    arguments = _arguments(
        _write_request(tmp_path, request),
        selection_root,
        capture_root,
        schedule_root,
    )
    assert run_capture_cli(arguments, _fetcher=_CliFetcher(), _client=_CliClient()) == 0
    capsys.readouterr()
    namespace = selection_root / "nifty100-selection-v3"
    binding = json.loads(
        (
            namespace / "requests" / f"{request.request_identity_sha256}.json"
        ).read_bytes()
    )
    source = namespace / "sources" / f"{binding['source_identity_sha256']}.json"
    source_value = json.loads(source.read_bytes())
    source_value["retrieved_at"] = datetime(2026, 8, 26, 23, tzinfo=UTC).isoformat()
    tampered = (
        json.dumps(source_value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    source.chmod(0o600)
    source.write_bytes(tampered)
    source.chmod(0o400)

    fetcher = _CliFetcher()
    client = _CliClient()
    assert run_capture_cli(arguments, _fetcher=fetcher, _client=client) == 1
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["reason"] == "SELECTION_EVIDENCE_UNAVAILABLE"
    assert fetcher.calls == []
    assert client.calls == []
    assert source.read_bytes() == tampered


@pytest.mark.parametrize("warm", [False, True])
def test_selection_root_authority_loss_returns_governed_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, warm: bool
) -> None:
    monkeypatch.setattr(capture, "_now", lambda: _CAPTURED_AT)
    request = _request(_members())
    selection_root = tmp_path / "selection"
    selection_root.mkdir(mode=0o700)
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    arguments = {
        "selection_root": selection_root,
        "capture_root": capture_root,
        "schedule_root": schedule_root,
    }
    if warm:
        assert (
            capture_current_nifty100_v2(
                request, **arguments, fetcher=_CliFetcher(), client=_CliClient()
            ).code
            == "COMPLETE_CURRENT_NIFTY100_CAPTURE"
        )
    open_directory = capture._open_directory  # pyright: ignore[reportPrivateUsage]
    renamed = False

    def detach_root(operation, parent, name, *, create):
        nonlocal renamed
        directory = open_directory(operation, parent, name, create=create)
        if name == "nifty100-selection-v3" and not renamed:
            selection_root.rename(tmp_path / "detached-selection")
            selection_root.mkdir(mode=0o700)
            renamed = True
        return directory

    monkeypatch.setattr(capture, "_open_directory", detach_root)
    fetcher = _CliFetcher()
    client = _CliClient()
    result = capture_current_nifty100_v2(
        request, **arguments, fetcher=fetcher, client=client
    )
    assert result.code == "INCOMPLETE_CURRENT_NIFTY100_CAPTURE"
    assert result.reason == (
        "SELECTION_EVIDENCE_UNAVAILABLE" if warm else "SELECTION_RETENTION_FAILED"
    )
    assert result.revision_identity_sha256 is None
    assert client.calls == []
    assert len(fetcher.calls) == (0 if warm else 3)


@pytest.mark.parametrize("damage", ["missing_source", "malformed_binding"])
def test_retained_selection_conflicts_never_refetch_or_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    monkeypatch.setattr(capture, "_now", lambda: _CAPTURED_AT)
    request = _request(_members())
    selection_root = tmp_path / "selection"
    selection_root.mkdir(mode=0o700)
    capture_root = tmp_path / "capture"
    capture_root.mkdir(mode=0o700)
    schedule_root = tmp_path / "schedule"
    _retain_schedule(schedule_root)
    arguments = {
        "selection_root": selection_root,
        "capture_root": capture_root,
        "schedule_root": schedule_root,
    }
    assert (
        capture_current_nifty100_v2(
            request, **arguments, fetcher=_CliFetcher(), client=_CliClient()
        ).code
        == "COMPLETE_CURRENT_NIFTY100_CAPTURE"
    )
    namespace = selection_root / "nifty100-selection-v3"
    binding = namespace / "requests" / f"{request.request_identity_sha256}.json"
    if damage == "missing_source":
        source_identity = json.loads(binding.read_bytes())["source_identity_sha256"]
        (namespace / "sources" / f"{source_identity}.json").unlink()
    else:
        binding.chmod(0o600)
        binding.write_bytes(b"{}\n")
        binding.chmod(0o400)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    fetcher = _CliFetcher()
    client = _CliClient()
    result = capture_current_nifty100_v2(
        request, **arguments, fetcher=fetcher, client=client
    )
    assert result.reason == "SELECTION_EVIDENCE_UNAVAILABLE"
    assert result.revision_identity_sha256 is None
    assert fetcher.calls == client.calls == []
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == before
