from __future__ import annotations

import json
import threading
import time
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.nifty50_read_workflow as read_module
from swing_trading_ai_assistant.market_data.bounded_nifty50_workflow import (
    Nifty50BatchOutcomeV1,
)
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.equity_admission import (
    Nifty50AdmissionPolicyV1,
)
from swing_trading_ai_assistant.market_data.nifty50_read_workflow import (
    BoundedNifty50ReadReportV1,
    BoundedNifty50ReadRequestV1,
    BoundedPointInTimeNifty50ReadServiceV1,
    Nifty50ReadResultV1,
    PointInTimeNifty50CoverageServiceV1,
    PointInTimeNifty50QueryServiceV1,
    render_bounded_nifty50_read_json,
)
from swing_trading_ai_assistant.market_data.public_contract import (
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicFailureCodeV1,
    PublicFailureV1,
)
from swing_trading_ai_assistant.market_data.public_coverage import CoverageRequestV1
from swing_trading_ai_assistant.market_data.public_query import QueryRequestV1
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.market_data.universe_snapshot import (
    Nifty50ConstituentV1,
    Nifty50UniverseSnapshotV1,
    Nifty50UniverseStoreV1,
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


def _seed(root: Path) -> None:
    root.chmod(0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    with acquired.lease, DuckDBCatalog(root, lease=acquired.lease) as catalog:
        Nifty50UniverseStoreV1(root, acquired.lease, catalog).retain(_snapshot())


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 8, 12, 8, tzinfo=UTC)


def _terminal(command: str):
    return PublicCommandReportV1(
        "v1",
        command,
        PublicCommandStatusV1.REJECTED,
        PublicFailureV1(PublicFailureCodeV1.INVALID_INPUT, None, None, None, None, ()),
        0,
        None,
    )


class _Coverage:
    def __init__(self, policy: Nifty50AdmissionPolicyV1) -> None:
        self.policy = policy
        self.calls = 0

    def coverage_under_lease(self, request: object, lease: object):
        assert lease is not None
        self.calls += 1
        return _terminal("coverage")


class _Query:
    def __init__(self, policy: Nifty50AdmissionPolicyV1) -> None:
        self.policy = policy
        self.calls = 0

    def query_under_lease(self, request: object, lease: object):
        assert lease is not None
        self.calls += 1
        return _terminal("query")


def test_coverage_resolves_requested_member_from_retained_point_in_time_universe(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)
    ports: list[_Coverage] = []

    def factory(policy: Nifty50AdmissionPolicyV1) -> _Coverage:
        port = _Coverage(policy)
        ports.append(port)
        return port

    request = CoverageRequestV1(
        "NSE_EQ", "SBIN", date(2026, 8, 1), date(2026, 8, 11), tmp_path
    )
    report = PointInTimeNifty50CoverageServiceV1(factory, clock=_Clock()).coverage(
        request
    )

    assert report.status is PublicCommandStatusV1.REJECTED
    assert ports[0].calls == 1
    assert ports[0].policy.ordered_symbols == ("SBIN",)
    assert ports[0].policy.admits("NSE_EQ", "SBIN")


def test_query_resolves_requested_member_without_provider_activity(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)
    ports: list[_Query] = []

    def factory(policy: Nifty50AdmissionPolicyV1) -> _Query:
        port = _Query(policy)
        ports.append(port)
        return port

    request = QueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 8, 1),
        date(2026, 8, 11),
        "1m",
        ("ts", "close"),
        1_000,
        tmp_path,
    )
    report = PointInTimeNifty50QueryServiceV1(factory, clock=_Clock()).query(request)

    assert report.status is PublicCommandStatusV1.REJECTED
    assert ports[0].calls == 1
    assert ports[0].policy.ordered_symbols == ("RELIANCE",)


def test_nonmember_read_fails_before_coverage_or_query_port(tmp_path: Path) -> None:
    _seed(tmp_path)
    calls = 0

    def factory(policy: Nifty50AdmissionPolicyV1) -> _Coverage:
        nonlocal calls
        calls += 1
        return _Coverage(policy)

    report = PointInTimeNifty50CoverageServiceV1(factory, clock=_Clock()).coverage(
        CoverageRequestV1(
            "NSE_EQ", "NOT_A_MEMBER", date(2026, 8, 1), date(2026, 8, 11), tmp_path
        )
    )

    assert report.status is PublicCommandStatusV1.REJECTED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT
    assert calls == 0


def test_missing_root_is_read_only_unavailable(tmp_path: Path) -> None:
    root = tmp_path / "absent"
    coverage = PointInTimeNifty50CoverageServiceV1(_Coverage, clock=_Clock()).coverage(
        CoverageRequestV1("NSE_EQ", "SBIN", date(2026, 8, 1), date(2026, 8, 11), root)
    )
    report = PointInTimeNifty50QueryServiceV1(_Query, clock=_Clock()).query(
        QueryRequestV1(
            "NSE_EQ",
            "SBIN",
            date(2026, 8, 1),
            date(2026, 8, 11),
            "1m",
            ("ts", "close"),
            1_000,
            root,
        )
    )

    assert coverage.status is PublicCommandStatusV1.UNAVAILABLE
    assert report.status is PublicCommandStatusV1.UNAVAILABLE
    assert not root.exists()


def test_many_symbol_coverage_uses_one_universe_and_stable_member_order(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)
    ports: list[_Coverage] = []

    def coverage_factory(policy: Nifty50AdmissionPolicyV1) -> _Coverage:
        port = _Coverage(policy)
        ports.append(port)
        return port

    service = BoundedPointInTimeNifty50ReadServiceV1(
        coverage_factory, _Query, clock=_Clock()
    )
    report = service.execute(
        BoundedNifty50ReadRequestV1(
            ("RELIANCE", "SBIN"),
            CoverageRequestV1(
                "NSE_EQ",
                "RELIANCE",
                date(2026, 8, 1),
                date(2026, 8, 11),
                tmp_path,
            ),
            workers=2,
        )
    )

    assert tuple(result.symbol for result in report.results) == ("SBIN", "RELIANCE")
    assert ports[0].calls == 2
    assert report.worker_count == 2
    decoded = json.loads(render_bounded_nifty50_read_json(report))
    assert decoded["provider_attempt_count"] == 0
    assert [result["symbol"] for result in decoded["results"]] == [
        "SBIN",
        "RELIANCE",
    ]


def test_all_member_query_smoke_is_bounded_to_eight_read_workers(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)
    lock = threading.Lock()
    active = 0
    maximum = 0

    class Query:
        def __init__(self, policy: Nifty50AdmissionPolicyV1) -> None:
            assert len(policy.ordered_symbols) == 50

        def query_under_lease(self, request: object, lease: object):
            nonlocal active, maximum
            assert lease is not None
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.005)
            with lock:
                active -= 1
            return _terminal("query")

    report = BoundedPointInTimeNifty50ReadServiceV1(
        _Coverage, Query, clock=_Clock()
    ).execute(
        BoundedNifty50ReadRequestV1(
            None,
            QueryRequestV1(
                "NSE_EQ",
                "SBIN",
                date(2026, 8, 1),
                date(2026, 8, 11),
                "1m",
                ("ts", "close"),
                100,
                tmp_path,
            ),
            workers=8,
        )
    )

    assert len(report.results) == 50
    assert report.worker_count == 8
    assert maximum == 8


def test_cli_coverage_accepts_explicit_symbol_list_and_returns_safe_aggregate(
    tmp_path: Path, capsys
) -> None:
    _seed(tmp_path)

    exit_code = main(
        [
            "coverage",
            "--segment",
            "NSE_EQ",
            "--symbols",
            "RELIANCE,SBIN",
            "--from",
            "2026-08-01",
            "--to",
            "2026-08-11",
            "--storage-root",
            str(tmp_path),
            "--workers",
            "2",
            "--output",
            "json",
        ]
    )

    decoded = json.loads(capsys.readouterr().out)
    assert exit_code == 4
    assert decoded["scope"] == "nifty50"
    assert decoded["provider_attempt_count"] == 0
    assert [result["symbol"] for result in decoded["results"]] == [
        "SBIN",
        "RELIANCE",
    ]

    query_exit = main(
        [
            "query",
            "--segment",
            "NSE_EQ",
            "--universe",
            "nifty50-current",
            "--from",
            "2026-08-01",
            "--to",
            "2026-08-11",
            "--timeframe",
            "1m",
            "--fields",
            "ts,close",
            "--max-rows",
            "100",
            "--storage-root",
            str(tmp_path),
            "--workers",
            "8",
            "--output",
            "json",
        ]
    )
    query = json.loads(capsys.readouterr().out)
    assert query_exit == 4
    assert query["command"] == "query"
    assert len(query["results"]) == 50


def test_cli_batch_admission_rejects_invalid_segment_and_symbol_list(
    tmp_path: Path, capsys
) -> None:
    exit_code = main(
        [
            "coverage",
            "--segment",
            "BSE_EQ",
            "--symbols",
            "SBIN,RELIANCE",
            "--from",
            "2026-08-01",
            "--to",
            "2026-08-11",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ]
    )
    assert exit_code == 2
    assert json.loads(capsys.readouterr().out)["status"] == "REJECTED"

    invalid_range = [
        "coverage",
        "--segment",
        "NSE_EQ",
        "--symbols",
        "SBIN,RELIANCE",
        "--from",
        "2026-08-11",
        "--to",
        "2026-08-01",
        "--storage-root",
        str(tmp_path),
        "--output",
        "json",
    ]
    assert main(invalid_range) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "REJECTED"

    invalid_query = [
        "query",
        "--segment",
        "NSE_EQ",
        "--universe",
        "nifty50-current",
        "--from",
        "2026-08-11",
        "--to",
        "2026-08-01",
        "--timeframe",
        "1m",
        "--fields",
        "ts,close",
        "--max-rows",
        "100",
        "--storage-root",
        str(tmp_path),
        "--output",
        "json",
    ]
    assert main(invalid_query) == 2
    invalid_query_output = json.loads(capsys.readouterr().out)
    assert invalid_query_output["command"] == "query"
    assert invalid_query_output["status"] == "REJECTED"

    with pytest.raises(SystemExit):
        main(
            [
                "coverage",
                "--segment",
                "NSE_EQ",
                "--symbols",
                "SBIN,SBIN",
                "--from",
                "2026-08-01",
                "--to",
                "2026-08-11",
                "--storage-root",
                str(tmp_path),
                "--output",
                "json",
            ]
        )


def test_single_read_wrappers_reject_invalid_clock_stale_range_and_factory_failure(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    class InvalidClock:
        def now(self) -> object:
            return None

    assert (
        PointInTimeNifty50CoverageServiceV1(_Coverage, clock=_Clock())
        .coverage(object())
        .status
        is PublicCommandStatusV1.REJECTED
    )
    assert (
        PointInTimeNifty50QueryServiceV1(_Query, clock=_Clock()).query(object()).status
        is PublicCommandStatusV1.REJECTED
    )
    valid_coverage = CoverageRequestV1(
        "NSE_EQ", "SBIN", date(2026, 8, 1), date(2026, 8, 11), tmp_path
    )
    valid_query = QueryRequestV1(
        "NSE_EQ",
        "SBIN",
        date(2026, 8, 1),
        date(2026, 8, 11),
        "1m",
        ("ts", "close"),
        1_000,
        tmp_path,
    )
    assert (
        PointInTimeNifty50CoverageServiceV1(_Coverage, clock=InvalidClock())
        .coverage(valid_coverage)
        .status
        is PublicCommandStatusV1.FAILED
    )
    assert (
        PointInTimeNifty50QueryServiceV1(_Query, clock=InvalidClock())
        .query(valid_query)
        .status
        is PublicCommandStatusV1.FAILED
    )
    stale = CoverageRequestV1(
        "NSE_EQ", "SBIN", date(2026, 6, 1), date(2026, 8, 11), tmp_path
    )
    assert (
        PointInTimeNifty50CoverageServiceV1(_Coverage, clock=_Clock())
        .coverage(stale)
        .status
        is PublicCommandStatusV1.UNAVAILABLE
    )
    stale_query = QueryRequestV1(
        "NSE_EQ",
        "SBIN",
        date(2026, 6, 1),
        date(2026, 8, 11),
        "1m",
        ("ts", "close"),
        1_000,
        tmp_path,
    )
    assert (
        PointInTimeNifty50QueryServiceV1(_Query, clock=_Clock())
        .query(stale_query)
        .status
        is PublicCommandStatusV1.UNAVAILABLE
    )
    assert (
        PointInTimeNifty50QueryServiceV1(_Query, clock=_Clock())
        .query(
            QueryRequestV1(
                "NSE_EQ",
                "NOPE",
                date(2026, 8, 1),
                date(2026, 8, 11),
                "1m",
                ("ts", "close"),
                1_000,
                tmp_path,
            )
        )
        .status
        is PublicCommandStatusV1.REJECTED
    )

    def broken_coverage(policy: Nifty50AdmissionPolicyV1) -> _Coverage:
        raise RuntimeError

    def broken_query(policy: Nifty50AdmissionPolicyV1) -> _Query:
        raise RuntimeError

    assert (
        PointInTimeNifty50CoverageServiceV1(broken_coverage, clock=_Clock())
        .coverage(valid_coverage)
        .status
        is PublicCommandStatusV1.UNAVAILABLE
    )
    assert (
        PointInTimeNifty50QueryServiceV1(broken_query, clock=_Clock())
        .query(valid_query)
        .status
        is PublicCommandStatusV1.UNAVAILABLE
    )


def test_bounded_read_dtos_and_terminal_boundaries_fail_closed(tmp_path: Path) -> None:
    _seed(tmp_path)
    prototype = CoverageRequestV1(
        "NSE_EQ", "SBIN", date(2026, 8, 1), date(2026, 8, 11), tmp_path
    )
    with pytest.raises(ValueError):
        BoundedNifty50ReadRequestV1((), prototype)
    with pytest.raises(ValueError):
        Nifty50ReadResultV1("bad symbol", _terminal("coverage"))
    with pytest.raises(ValueError):
        BoundedNifty50ReadReportV1("bad", Nifty50BatchOutcomeV1.FAILED, None, (), 0)
    with pytest.raises(ValueError):
        BoundedNifty50ReadRequestV1(
            None,
            QueryRequestV1(
                "NSE_EQ",
                "SBIN",
                date(2026, 8, 1),
                date(2026, 8, 11),
                "1m",
                ("ts", "close"),
                101,
                tmp_path,
            ),
        )

    service = BoundedPointInTimeNifty50ReadServiceV1(_Coverage, _Query, clock=_Clock())
    assert service.execute(object()).outcome is Nifty50BatchOutcomeV1.REJECTED

    absent = tmp_path / "absent"
    unavailable = service.execute(
        BoundedNifty50ReadRequestV1(
            ("SBIN",),
            CoverageRequestV1(
                "NSE_EQ",
                "SBIN",
                date(2026, 8, 1),
                date(2026, 8, 11),
                absent,
            ),
        )
    )
    assert unavailable.outcome is Nifty50BatchOutcomeV1.UNAVAILABLE

    nonmember = service.execute(BoundedNifty50ReadRequestV1(("NOPE",), prototype))
    assert nonmember.outcome is Nifty50BatchOutcomeV1.REJECTED

    stale = service.execute(
        BoundedNifty50ReadRequestV1(
            ("SBIN",),
            CoverageRequestV1(
                "NSE_EQ",
                "SBIN",
                date(2026, 6, 1),
                date(2026, 8, 11),
                tmp_path,
            ),
        )
    )
    assert stale.outcome is Nifty50BatchOutcomeV1.UNAVAILABLE

    def broken_factory(policy: Nifty50AdmissionPolicyV1) -> _Coverage:
        raise RuntimeError

    assert (
        BoundedPointInTimeNifty50ReadServiceV1(broken_factory, _Query, clock=_Clock())
        .execute(BoundedNifty50ReadRequestV1(("SBIN",), prototype))
        .outcome
        is Nifty50BatchOutcomeV1.FAILED
    )

    class InvalidClock:
        def now(self) -> object:
            return None

    failed = BoundedPointInTimeNifty50ReadServiceV1(
        _Coverage, _Query, clock=InvalidClock()
    ).execute(BoundedNifty50ReadRequestV1(("SBIN",), prototype))
    assert failed.outcome is Nifty50BatchOutcomeV1.FAILED


def test_bounded_read_worker_and_renderer_defend_nested_reports(tmp_path: Path) -> None:
    _seed(tmp_path)

    class MalformedCoverage:
        def __init__(self, policy: Nifty50AdmissionPolicyV1) -> None:
            pass

        def coverage_under_lease(self, request: object, lease: object) -> object:
            return object()

    report = BoundedPointInTimeNifty50ReadServiceV1(
        MalformedCoverage, _Query, clock=_Clock()
    ).execute(
        BoundedNifty50ReadRequestV1(
            ("SBIN",),
            CoverageRequestV1(
                "NSE_EQ",
                "SBIN",
                date(2026, 8, 1),
                date(2026, 8, 11),
                tmp_path,
            ),
        )
    )
    assert report.outcome is Nifty50BatchOutcomeV1.FAILED
    assert report.results[0].report.failure is not None
    assert (
        report.results[0].report.failure.code
        is PublicFailureCodeV1.UNCLASSIFIED_FAILURE
    )
    assert json.loads(render_bounded_nifty50_read_json(object()))["status"] == "FAILED"

    query_result = Nifty50ReadResultV1("SBIN", _terminal("query"))
    query_report = BoundedNifty50ReadReportV1(
        "query", Nifty50BatchOutcomeV1.REJECTED, "a" * 64, (query_result,), 1
    )
    assert (
        json.loads(render_bounded_nifty50_read_json(query_report))["command"] == "query"
    )
    object.__setattr__(query_report, "results", (object(),))
    assert (
        json.loads(render_bounded_nifty50_read_json(query_report))["status"] == "FAILED"
    )
    object.__setattr__(query_report, "results", (query_result,))
    object.__setattr__(query_report, "universe_snapshot_sha256", "secret-token")
    encoded = render_bounded_nifty50_read_json(query_report)
    assert b"secret-token" not in encoded
    assert json.loads(encoded)["status"] == "FAILED"

    valid = BoundedNifty50ReadReportV1(
        "query", Nifty50BatchOutcomeV1.REJECTED, "a" * 64, (query_result,), 1
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(read_module, "MAX_BATCH_READ_JSON_BYTES_V1", 1)
    try:
        bounded = render_bounded_nifty50_read_json(valid)
    finally:
        monkeypatch.undo()
    assert json.loads(bounded)["status"] == "FAILED"


def test_read_aggregate_preserves_all_terminal_classes() -> None:
    rejected = Nifty50ReadResultV1("SBIN", _terminal("coverage"))
    unavailable_report = PublicCommandReportV1(
        "v1",
        "coverage",
        PublicCommandStatusV1.UNAVAILABLE,
        PublicFailureV1(
            PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            None,
            None,
            None,
            None,
            (),
        ),
        0,
        None,
    )
    unavailable = Nifty50ReadResultV1("RELIANCE", unavailable_report)
    cancelled_report = PublicCommandReportV1(
        "v1",
        "coverage",
        PublicCommandStatusV1.CANCELLED,
        PublicFailureV1(
            PublicFailureCodeV1.INGESTION_CANCELLED, None, None, None, None, ()
        ),
        0,
        None,
    )
    cancelled = Nifty50ReadResultV1("SYM02", cancelled_report)
    success_report = _terminal("coverage")
    object.__setattr__(success_report, "status", PublicCommandStatusV1.SUCCEEDED)
    success = Nifty50ReadResultV1("SYM03", success_report)

    assert read_module._aggregate_read((success,)) is Nifty50BatchOutcomeV1.SUCCEEDED
    assert (
        read_module._aggregate_read((success, rejected))
        is Nifty50BatchOutcomeV1.PARTIAL
    )
    assert (
        read_module._aggregate_read((unavailable,)) is Nifty50BatchOutcomeV1.UNAVAILABLE
    )
    assert read_module._aggregate_read((cancelled,)) is Nifty50BatchOutcomeV1.CANCELLED
    assert read_module._aggregate_read(()) is Nifty50BatchOutcomeV1.FAILED
