"""RED contract portfolio for current supplied-cohort Market Regime V1.

The Sprint-11 module is deliberately imported only inside execution.  Until it
exists, every collected case therefore fails at the same missing authoritative
module rather than at fixture construction or collection.
"""

from __future__ import annotations

import builtins
import glob as glob_module
import hashlib
import importlib.machinery
import json
import os
import socket
import time as time_module
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import pytest

from swing_trading_ai_assistant.market_data.current_cohort import (
    CURRENT_COHORT_SCHEMA_IDENTITY_SHA256_V1,
    CURRENT_COHORT_SOURCE_POLICY_IDENTITY_SHA256_V1,
    CompletedDailyOhlcvFactV1,
    CurrentBarStateV1,
    CurrentCohortMarketDataReportV1,
    CurrentCohortMarketDataRequestV1,
    CurrentCohortMarketDataServiceV1,
    CurrentCohortMemberFactV1,
    CurrentCohortMemberV1,
    CurrentEvidenceStateV1,
    CurrentFreshnessStateV1,
    CurrentSuppliedCohortManifestV1,
    HistoricalAvailabilityStateV1,
    ImmutableCurrentFactArchiveV1,
    PartialCurrentSessionSnapshotV1,
    available_ledger_entry_v1,
)
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
)

_CONTRACT = "current-supplied-cohort-market-regime@v1"
_SCHEMA = "1242118a1a48d484259f992784850173c9722d4d650df2e886d89af42e55ebd7"
_CALCULATION = "bc66f914bc6cafcef658e71814a4d8b0bbc180dc9676fdfc5a9bc628d6485d86"
_SOURCE = "nse-authoritative-calendar"
_RELEASE = "sha256:" + "b" * 64
_CUTOFF = datetime(2026, 1, 12, 10, tzinfo=UTC)
_REASONS = (
    "ARCHIVE_OBJECT_MISSING",
    "ARCHIVE_OBJECT_UNSAFE",
    "ARCHIVE_OBJECT_INVALID",
    "ARCHIVE_CONTENT_ID_MISMATCH",
    "ARCHIVE_BINDING_MISMATCH",
    "SPRINT10_REPORT_INSUFFICIENT",
    "SPRINT10_REPORT_INVALID",
    "SPRINT10_MEMBER_FACT_INVALID",
    "SPRINT10_LEDGER_UNAVAILABLE",
    "SPRINT10_LEDGER_INVALID",
    "COHORT_BINDING_MISMATCH",
    "ARCHIVE_SESSION_DUPLICATE_OR_CONFLICTING",
    "COMMON_SESSION_GRID_INVALID",
    "SCHEDULE_EVIDENCE_MISSING",
    "SCHEDULE_EVIDENCE_AMBIGUOUS",
    "SCHEDULE_EVIDENCE_LATE",
    "SCHEDULE_CONTINUITY_UNPROVEN",
    "DECISION_SESSION_NOT_LATEST_ADMISSIBLE",
    "FACT_CUTOFF_OR_FRESHNESS_UNPROVEN",
    "FACT_FUTURE_KNOWN",
)
_RUNTIME_SOURCES = (
    "src/swing_trading_ai_assistant/market_data/cli.py",
    "src/swing_trading_ai_assistant/market_data/current_cohort.py",
    "src/swing_trading_ai_assistant/market_data/schedule_evidence.py",
    "src/swing_trading_ai_assistant/market_data/storage_root_lease.py",
    "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort.py",
)
_RUNTIME_MANIFEST = "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_runtime_identity_manifest.py"


@dataclass
class _RecordingArchivePort:
    """The sole narrow-port double; it validates the immutable request and lease."""

    request_type: Any
    result: Any
    expected_input: Any
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    def read_exact(self, request: Any, lease: Any) -> Any:
        self.calls.append((request, lease))
        assert type(request) is self.request_type
        assert (
            request.input_identity_sha256 == self.expected_input.input_identity_sha256
        )
        assert (
            request.archive_object_sha256s == self.expected_input.archive_object_sha256s
        )
        assert request.decision_cutoff == self.expected_input.decision_cutoff
        assert lease is None
        return self.result


@dataclass
class _RecordingSchedulePort:
    """The sole narrow-port double; it validates every bound resolver argument."""

    result: Any
    expected_input: Any
    calls: list[tuple[Any, ...]] = field(default_factory=list)

    def resolve_exact(
        self, digest: str, source: str, release: str, cutoff: datetime, lease: Any
    ) -> Any:
        self.calls.append((digest, source, release, cutoff, lease))
        assert (digest, source, release, cutoff) == (
            self.expected_input.schedule_evidence_sha256,
            self.expected_input.schedule_source,
            self.expected_input.schedule_source_release,
            self.expected_input.decision_cutoff,
        )
        assert lease is None
        return self.result


def _api() -> tuple[Any, Callable[..., Any]]:
    """Load the sole Plan-20 surface only while a test executes."""
    module = importlib.import_module(
        "swing_trading_ai_assistant.market_regime.current_supplied_cohort"
    )
    evaluate = getattr(
        module, "evaluate_current_supplied_cohort_market_regime_v1", None
    )
    assert callable(evaluate), "missing Sprint-11 authoritative evaluator"
    return module, evaluate


def _type(module: Any, name: str) -> Any:
    value = getattr(module, name, None)
    assert value is not None, f"missing Plan-20 type {name}"
    return value


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )


def _sessions() -> tuple[date, ...]:
    return (
        date(2025, 12, 10),
        date(2025, 12, 11),
        date(2025, 12, 12),
        date(2025, 12, 15),
        date(2025, 12, 16),
        date(2025, 12, 17),
        date(2025, 12, 18),
        date(2025, 12, 19),
        date(2025, 12, 22),
        date(2025, 12, 23),
        date(2025, 12, 26),
        date(2025, 12, 29),
        date(2025, 12, 30),
        date(2025, 12, 31),
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
        date(2026, 1, 12),
    )


def _private_root(tmp_path: Path) -> Path:
    root = tmp_path / "retained"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.outcome is LeaseOutcome.ACQUIRED and acquired.lease is not None
    acquired.lease.close()
    return root


def _members(size: int) -> tuple[CurrentCohortMemberV1, ...]:
    return tuple(
        CurrentCohortMemberV1(f"INE{index:03d}A01018", f"M{index:03d}")
        for index in range(1, size + 1)
    )


def _schedule(
    root: Path,
    *,
    schema_version: int = 3,
    as_of: datetime = _CUTOFF,
    include_next_current_session: bool = False,
) -> tuple[str, ExpectedSessionSchedule]:
    dates = _sessions() + ((date(2026, 1, 13),) if include_next_current_session else ())
    session_dates = set(dates)
    schedule = ExpectedSessionSchedule(
        schema_version=schema_version,
        source=_SOURCE,
        source_release=_RELEASE,
        as_of=as_of,
        timezone="Asia/Kolkata",
        covered_from=dates[0],
        covered_to=dates[-1],
        sessions=tuple(
            ScheduleSession(
                day,
                datetime.combine(day, time(3, 45), UTC),
                datetime.combine(day, time(10), UTC),
                "SPECIAL" if day == date(2025, 12, 26) else "REGULAR",
            )
            for day in dates
        ),
        closures=tuple(
            ScheduleClosure(day, "WEEKEND_OR_OFFICIAL_CLOSURE")
            for offset in range((dates[-1] - dates[0]).days + 1)
            if (day := dates[0] + timedelta(days=offset)) not in session_dates
        ),
    )
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.outcome is LeaseOutcome.ACQUIRED and acquired.lease is not None
    try:
        expected = (
            ScheduleOutcome.RESOLVED
            if (
                root
                / "calendar-schedules"
                / "sha256"
                / f"{schedule_digest(schedule)}.json"
            ).exists()
            else ScheduleOutcome.RETAINED
        )
        retained = ScheduleEvidenceStore(root, acquired.lease).retain(schedule)
        assert retained.outcome is expected
    finally:
        acquired.lease.close()
    return schedule_digest(schedule), schedule


def _close_for(position: int, direction: Decimal) -> Decimal:
    """S1..S19 cannot be mistaken for the S0/S20 comparison pair."""
    if position == 0:
        return Decimal("100")
    if position == 20:
        with localcontext() as context:
            context.prec = 64
            return Decimal("100") + direction
    return Decimal("99") if direction >= 0 else Decimal("101")


def _archive_fixture(
    root: Path,
    *,
    size: int,
    directions: tuple[Decimal, ...],
    include_partial: bool = False,
    partial_cutoff: datetime | None = None,
    partial_member_indexes: tuple[int, ...] | None = None,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    assert len(directions) == size
    if include_partial and partial_cutoff is None:
        partial_cutoff = datetime(2026, 1, 13, 9, 30, tzinfo=UTC)
    if (not include_partial and partial_cutoff is not None) or (
        partial_member_indexes is not None
        and (
            not include_partial
            or any(
                type(index) is not int or not 0 <= index < size
                for index in partial_member_indexes
            )
            or len(set(partial_member_indexes)) != len(partial_member_indexes)
        )
    ):
        raise ValueError("invalid partial fixture")
    members = _members(size)
    cohort = CurrentSuppliedCohortManifestV1(datetime(2025, 12, 1, tzinfo=UTC), members)
    archive = ImmutableCurrentFactArchiveV1(root)
    records: list[dict[str, Any]] = []
    ids: list[str] = []
    for position, session in enumerate(_sessions()):
        partial_enabled = include_partial and position == 20
        cutoff = (
            partial_cutoff
            if partial_enabled
            else datetime.combine(session, time(10), UTC)
        )
        completed_session = session
        completed_cutoff = datetime.combine(completed_session, time(10), UTC)
        request = CurrentCohortMarketDataRequestV1(
            cohort,
            cutoff,
            partial_enabled,
            CURRENT_COHORT_SOURCE_POLICY_IDENTITY_SHA256_V1,
            CURRENT_COHORT_SCHEMA_IDENTITY_SHA256_V1,
        )
        completed = tuple(
            CompletedDailyOhlcvFactV1(
                member,
                completed_session,
                Decimal("99"),
                Decimal("102"),
                Decimal("98"),
                _close_for(position, direction),
                1,
                datetime.combine(completed_session, time(9), UTC),
                datetime.combine(completed_session, time(9, 30), UTC),
                completed_cutoff,
                hashlib.sha256(
                    f"{completed_session}:{member.isin}".encode()
                ).hexdigest(),
                CurrentFreshnessStateV1.FRESH,
            )
            for member, direction in zip(members, directions, strict=True)
        )
        partial_session = date(2026, 1, 13)
        selected_partial_indexes = (
            tuple(range(size))
            if partial_member_indexes is None
            else partial_member_indexes
        )
        partials = (
            tuple(
                PartialCurrentSessionSnapshotV1(
                    fact.member,
                    partial_session,
                    Decimal("1"),
                    1,
                    datetime.combine(partial_session, time(9), UTC),
                    datetime.combine(partial_session, time(9, 15), UTC),
                    datetime.combine(partial_session, time(9, 30), UTC),
                    hashlib.sha256(f"partial:{fact.member.isin}".encode()).hexdigest(),
                    CurrentBarStateV1.PARTIAL_CURRENT_SESSION,
                )
                for index, fact in enumerate(completed)
                if index in selected_partial_indexes
            )
            if partial_enabled
            else ()
        )
        partial_by_member = {partial.member: partial for partial in partials}
        facts = tuple(
            CurrentCohortMemberFactV1(
                fact.member, fact, partial_by_member.get(fact.member)
            )
            for fact in completed
        )
        report = CurrentCohortMarketDataReportV1(
            request=request,
            evidence_state=CurrentEvidenceStateV1.COMPLETE,
            members=facts,
            reasons=(),
        )
        ledger_items = []
        for fact in facts:
            ledger_items.append(
                available_ledger_entry_v1(
                    feature="DAILY_OHLCV",
                    interval="1d",
                    member=fact.member,
                    cutoff=cutoff,
                    fact=fact.completed_daily,
                    state=HistoricalAvailabilityStateV1.AVAILABLE,
                )
            )
            if partial_enabled:
                partial = fact.partial_current_session
                ledger_items.append(
                    available_ledger_entry_v1(
                        feature="PARTIAL_CURRENT_SESSION",
                        interval="1m",
                        member=fact.member,
                        cutoff=cutoff,
                        partial=partial,
                        state=(
                            HistoricalAvailabilityStateV1.AVAILABLE
                            if partial is not None
                            else HistoricalAvailabilityStateV1.NOT_RETAINED
                        ),
                    )
                )
        ledger = tuple(ledger_items)
        acquired = StorageRootLease.try_acquire(root)
        assert acquired.outcome is LeaseOutcome.ACQUIRED and acquired.lease is not None
        try:
            assert archive.archive(
                request, report, facts, partials, ledger, acquired.lease
            )
        finally:
            acquired.lease.close()
        value = {
            "code_identity": report.code_identity,
            "cohort_identity_sha256": cohort.cohort_identity_sha256,
            "contract_version": report.contract_version,
            "facts": [fact.value() for fact in facts],
            "ledger": [entry.value() for entry in ledger],
            "partials": [partial.value() for partial in partials],
            "report": report.value(),
            "request_identity_sha256": request.request_identity_sha256,
        }
        raw = _canonical(value)
        digest = hashlib.sha256(raw).hexdigest()
        path = root / ".current-fact-archive-v1" / f"{digest}.json"
        assert path.read_bytes() == raw
        ids.append(digest)
        records.append(
            {
                "id": digest,
                "path": path,
                "value": value,
                "session": session,
                "request": request,
                "report": report,
                "facts": facts,
            }
        )
    return {"cohort": cohort, "members": members, "records": records}, tuple(
        sorted(ids)
    )


def _input_value(
    fixture: dict[str, Any],
    archive_ids: tuple[str, ...],
    schedule_id: str,
    *,
    decision_cutoff: datetime = _CUTOFF,
    decision_session: date = date(2026, 1, 12),
) -> dict[str, object]:
    value: dict[str, object] = {
        "contract_version": _CONTRACT,
        "cohort_identity_sha256": fixture["cohort"].cohort_identity_sha256,
        "cohort_size": len(fixture["members"]),
        "decision_cutoff": decision_cutoff.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "decision_session": decision_session.isoformat(),
        "archive_object_sha256s": list(archive_ids),
        "schedule_evidence_sha256": schedule_id,
        "schedule_source": _SOURCE,
        "schedule_source_release": _RELEASE,
    }
    value["input_identity_sha256"] = hashlib.sha256(_canonical(value)).hexdigest()
    return value


def _admit_input(module: Any, value: dict[str, object]) -> Any:
    admitted = _type(
        module, "CurrentSuppliedCohortMarketRegimeInputV1"
    ).from_canonical_json_bytes(_canonical(value))
    assert admitted.canonical_json_bytes() == _canonical(value)
    return admitted


def _private_ready(
    module: Any,
    fixture: dict[str, Any],
    archive_ids: tuple[str, ...],
    schedule_id: str,
    schedule: ExpectedSessionSchedule,
) -> tuple[Any, Any]:
    close = _type(module, "PrivateCurrentCohortMemberCloseProjectionV1")
    archive_session = _type(module, "PrivateCurrentCohortArchiveSessionProjectionV1")
    grid_type = _type(module, "PrivateCurrentCohortArchiveGridProjectionV1")
    schedule_session = _type(module, "PrivateRetainedScheduleSessionProjectionV1")
    continuity_type = _type(module, "PrivateRetainedScheduleContinuityProjectionV1")
    by_id = {record["id"]: record for record in fixture["records"]}
    sessions = tuple(
        archive_session(
            record["id"],
            record["request"].request_identity_sha256,
            record["report"].report_identity_sha256,
            record["report"].code_identity,
            datetime.combine(record["session"], time(10), UTC),
            record["session"],
            tuple(
                close(fact.member, fact.completed_daily.close)
                for fact in record["facts"]
            ),
        )
        for record in sorted(
            (by_id[item] for item in archive_ids), key=lambda item: item["session"]
        )
    )
    grid = grid_type(
        fixture["cohort"].cohort_identity_sha256, len(fixture["members"]), sessions
    )
    continuity = continuity_type(
        schedule_id,
        schedule.schema_version,
        schedule.source,
        schedule.source_release,
        schedule.as_of,
        tuple(
            schedule_session(item.trade_date, item.close_at, item.kind)
            for item in schedule.sessions
        ),
    )
    assert type(grid) is grid_type and all(
        type(item) is archive_session for item in sessions
    )
    assert type(continuity) is continuity_type
    return grid, continuity


def _run_pure(
    module: Any,
    evaluate: Callable[..., Any],
    root: Path,
    *,
    directions: tuple[Decimal, ...],
    partial: bool = False,
) -> tuple[Any, Any, Any]:
    fixture, archive_ids = _archive_fixture(
        root, size=len(directions), directions=directions, include_partial=partial
    )
    schedule_id, schedule = _schedule(root)
    admitted = _admit_input(module, _input_value(fixture, archive_ids, schedule_id))
    grid, continuity = _private_ready(
        module, fixture, archive_ids, schedule_id, schedule
    )
    archive = _RecordingArchivePort(
        _type(module, "CurrentSuppliedCohortMarketRegimeRequestV1"),
        _type(module, "ArchiveReadResultV1")("READY", grid, ()),
        admitted,
    )
    resolver = _RecordingSchedulePort(
        _type(module, "ScheduleReadResultV1")("RESOLVED", continuity, ()), admitted
    )
    return evaluate(admitted, archive, resolver), archive, resolver


def _assert_observed(
    module: Any,
    report: Any,
    *,
    label: str,
    advances: int,
    declines: int,
    unchanged: int,
) -> None:
    assert type(report) is _type(module, "CurrentSuppliedCohortMarketRegimeReportV1")
    assert (report.evidence_state, report.regime_label) == ("OBSERVED", label)
    assert (
        report.advances,
        report.declines,
        report.unchanged,
        report.member_directions,
    ) == (advances, declines, unchanged, None)
    assert report.reasons == () and report.comparison_session == _sessions()[0]
    assert (report.schema_identity_sha256, report.calculation_identity_sha256) == (
        _SCHEMA,
        _CALCULATION,
    )


def _assert_insufficient(module: Any, report: Any, reasons: tuple[str, ...]) -> None:
    assert type(report) is _type(module, "CurrentSuppliedCohortMarketRegimeReportV1")
    assert report.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert report.reasons == tuple(sorted(set(reasons), key=_REASONS.index))
    assert (
        report.comparison_session,
        report.regime_label,
        report.advances,
        report.declines,
        report.unchanged,
        report.member_directions,
    ) == (None, None, None, None, None, None)


def _cli(module: Any) -> Callable[[list[str]], int]:
    cli = importlib.import_module("swing_trading_ai_assistant.market_data.cli")
    main = getattr(cli, "main", None)
    assert callable(main), "missing market-data CLI adapter"
    return main


def _cli_args(tmp_path: Path, root: Path, value: dict[str, object]) -> list[str]:
    input_file = tmp_path / "owner-input.json"
    input_file.write_bytes(_canonical(value))
    input_file.chmod(0o600)
    return [
        "regime-current",
        "--input-file",
        str(input_file),
        "--storage-root",
        str(root),
        "--output",
        "json",
    ]


def _refresh_identity(value: dict[str, Any], field: str) -> None:
    value[field] = hashlib.sha256(
        _canonical({key: item for key, item in value.items() if key != field})
    ).hexdigest()


def _make_report_insufficient(item: dict[str, Any]) -> None:
    report = item["report"]
    report.update(
        evidence_state="INSUFFICIENT_EVIDENCE",
        members=None,
        reasons=["DAILY_BAR_MISSING"],
    )
    _refresh_identity(report, "report_identity_sha256")


def _replace_archive(
    record: dict[str, Any], mutate: Callable[[dict[str, Any]], None]
) -> str:
    value = json.loads(_canonical(record["value"]))
    mutate(value)
    if value["report"]["evidence_state"] == "COMPLETE":
        value["report"]["members"] = value["facts"]
    _refresh_identity(value["report"], "report_identity_sha256")
    raw = _canonical(value)
    digest = hashlib.sha256(raw).hexdigest()
    new_path = record["path"].with_name(f"{digest}.json")
    new_path.write_bytes(raw)
    new_path.chmod(0o600)
    record["path"].unlink()
    record.update(id=digest, path=new_path, value=value)
    return digest


def _replace_schedule(
    root: Path, digest: str, mutate: Callable[[dict[str, Any]], None]
) -> str:
    path = root / "calendar-schedules" / "sha256" / f"{digest}.json"
    value = json.loads(path.read_bytes())
    mutate(value)
    raw = _canonical(value).rstrip(
        b"\n"
    )  # ScheduleEvidenceStore bytes intentionally have no LF.
    new_digest = hashlib.sha256(raw).hexdigest()
    new_path = path.with_name(f"{new_digest}.json")
    new_path.write_bytes(raw)
    path.unlink()
    return new_digest


def _replace_schedule_at_size(root: Path, digest: str, size: int) -> str:
    path = root / "calendar-schedules" / "sha256" / f"{digest}.json"
    value = json.loads(path.read_bytes())
    base = _canonical(value).rstrip(b"\n")
    assert len(base) < size and value["closures"]
    value["closures"][0]["reason"] += "X" * (size - len(base))
    raw = _canonical(value).rstrip(b"\n")
    assert len(raw) == size
    new_digest = hashlib.sha256(raw).hexdigest()
    new_path = path.with_name(f"{new_digest}.json")
    new_path.write_bytes(raw)
    path.unlink()
    return new_digest


def _replace_schedule_at_row_count(root: Path, digest: str, rows: int) -> str:
    def set_rows(value: dict[str, Any]) -> None:
        sessions = value["sessions"]
        session_dates = {item["trade_date"] for item in sessions}
        covered_to = date.fromisoformat(value["covered_to"])
        covered_from = covered_to - timedelta(days=rows - 1)
        value["covered_from"] = covered_from.isoformat()
        value["closures"] = [
            {
                "trade_date": (covered_from + timedelta(days=offset)).isoformat(),
                "reason": "HISTORICAL_CLOSURE",
            }
            for offset in range(rows)
            if (covered_from + timedelta(days=offset)).isoformat() not in session_dates
        ]
        assert len(value["sessions"]) + len(value["closures"]) == rows

    return _replace_schedule(root, digest, set_rows)


@pytest.mark.parametrize(
    ("directions", "label", "counts"),
    [
        ((Decimal("0.000000000000000000000000000001"),), "BROAD_ADVANCE", (1, 0, 0)),
        (
            (Decimal("1"), Decimal("1"), Decimal("1"), Decimal("0"), Decimal("0")),
            "BROAD_ADVANCE",
            (3, 0, 2),
        ),
        (
            (Decimal("-1"), Decimal("-1"), Decimal("-1"), Decimal("0"), Decimal("0")),
            "BROAD_DECLINE",
            (0, 3, 2),
        ),
        ((Decimal("0"),) * 5, "MIXED_PARTICIPATION", (0, 0, 5)),
        ((Decimal("1"),) * 30 + (Decimal("0"),) * 20, "BROAD_ADVANCE", (30, 0, 20)),
        ((Decimal("-0.000000000000000000000000000001"),), "BROAD_DECLINE", (0, 1, 0)),
    ],
)
def test_pure_evaluator_uses_s0_s20_exact_decimal_grid_and_aggregate_thresholds(
    tmp_path: Path,
    directions: tuple[Decimal, ...],
    label: str,
    counts: tuple[int, int, int],
) -> None:
    module, evaluate = _api()
    report, archive, resolver = _run_pure(
        module, evaluate, _private_root(tmp_path), directions=directions
    )
    _assert_observed(
        module,
        report,
        label=label,
        advances=counts[0],
        declines=counts[1],
        unchanged=counts[2],
    )
    assert len(archive.calls) == len(resolver.calls) == 1


@pytest.mark.parametrize(
    ("directions", "label"),
    [
        (
            (Decimal("1"), Decimal("1"), Decimal("0"), Decimal("0"), Decimal("0")),
            "MIXED_PARTICIPATION",
        ),
        (
            (Decimal("-1"), Decimal("-1"), Decimal("0"), Decimal("0"), Decimal("0")),
            "MIXED_PARTICIPATION",
        ),
        ((Decimal("1"),) * 29 + (Decimal("0"),) * 21, "MIXED_PARTICIPATION"),
        ((Decimal("-1"),) * 30 + (Decimal("0"),) * 20, "BROAD_DECLINE"),
    ],
)
def test_pure_evaluator_preserves_full_denominator_and_decimal_equality(
    tmp_path: Path, directions: tuple[Decimal, ...], label: str
) -> None:
    module, evaluate = _api()
    report, _, _ = _run_pure(
        module, evaluate, _private_root(tmp_path), directions=directions
    )
    assert report.regime_label == label
    assert type(report) is _type(module, "CurrentSuppliedCohortMarketRegimeReportV1")
    assert report.advances + report.declines + report.unchanged == len(directions)


def test_only_narrow_port_reason_propagation_is_ordered_and_stage_suppressed(
    tmp_path: Path,
) -> None:
    module, evaluate = _api()
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(root, size=1, directions=(Decimal("1"),))
    digest, schedule = _schedule(root)
    admitted = _admit_input(module, _input_value(fixture, ids, digest))
    archive = _RecordingArchivePort(
        _type(module, "CurrentSuppliedCohortMarketRegimeRequestV1"),
        _type(module, "ArchiveReadResultV1")(
            "INSUFFICIENT_EVIDENCE",
            None,
            ("ARCHIVE_OBJECT_INVALID", "ARCHIVE_OBJECT_INVALID"),
        ),
        admitted,
    )
    resolver = _RecordingSchedulePort(
        _type(module, "ScheduleReadResultV1")(
            "INSUFFICIENT_EVIDENCE", None, ("SCHEDULE_EVIDENCE_MISSING",)
        ),
        admitted,
    )
    report = evaluate(admitted, archive, resolver)
    _assert_insufficient(module, report, ("ARCHIVE_OBJECT_INVALID",))
    assert len(archive.calls) == 1 and resolver.calls == []


def test_typed_archive_port_propagates_common_session_grid_invalid_without_default_reader_mutation(
    tmp_path: Path,
) -> None:
    module, evaluate = _api()
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(root, size=1, directions=(Decimal("1"),))
    digest, _ = _schedule(root)
    admitted = _admit_input(module, _input_value(fixture, ids, digest))
    archive_result_type = _type(module, "ArchiveReadResultV1")
    archive_result = archive_result_type(
        "INSUFFICIENT_EVIDENCE", None, ("COMMON_SESSION_GRID_INVALID",)
    )
    assert type(archive_result) is archive_result_type
    archive = _RecordingArchivePort(
        _type(module, "CurrentSuppliedCohortMarketRegimeRequestV1"),
        archive_result,
        admitted,
    )
    schedule_result_type = _type(module, "ScheduleReadResultV1")
    schedule_result = schedule_result_type(
        "INSUFFICIENT_EVIDENCE", None, ("SCHEDULE_EVIDENCE_MISSING",)
    )
    assert type(schedule_result) is schedule_result_type
    resolver = _RecordingSchedulePort(schedule_result, admitted)
    report = evaluate(admitted, archive, resolver)
    _assert_insufficient(module, report, ("COMMON_SESSION_GRID_INVALID",))
    assert len(archive.calls) == 1 and resolver.calls == []


@pytest.mark.parametrize("fault", ("future", "date_mismatch", "non_utc"))
def test_typed_resolved_schedule_port_rejects_invalid_close_projections(
    tmp_path: Path, fault: str
) -> None:
    module, evaluate = _api()
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(root, size=1, directions=(Decimal("1"),))
    digest, schedule = _schedule(root)
    admitted = _admit_input(module, _input_value(fixture, ids, digest))
    grid, continuity = _private_ready(module, fixture, ids, digest, schedule)
    sessions = list(continuity.sessions)
    target = sessions[-1]
    if fault == "future":
        close_at = _CUTOFF + timedelta(microseconds=1)
    elif fault == "date_mismatch":
        close_at = datetime(2026, 1, 11, 10, tzinfo=UTC)
    else:
        close_at = datetime(2026, 1, 12, 10, tzinfo=timezone(timedelta(hours=1)))
    schedule_session = _type(module, "PrivateRetainedScheduleSessionProjectionV1")
    sessions[-1] = schedule_session(target.trade_date, close_at, target.kind)
    continuity_type = _type(module, "PrivateRetainedScheduleContinuityProjectionV1")
    invalid_continuity = continuity_type(
        continuity.schedule_evidence_sha256,
        continuity.schema_version,
        continuity.source,
        continuity.source_release,
        continuity.as_of,
        tuple(sessions),
    )
    archive = _RecordingArchivePort(
        _type(module, "CurrentSuppliedCohortMarketRegimeRequestV1"),
        _type(module, "ArchiveReadResultV1")("READY", grid, ()),
        admitted,
    )
    resolver = _RecordingSchedulePort(
        _type(module, "ScheduleReadResultV1")("RESOLVED", invalid_continuity, ()),
        admitted,
    )
    report = evaluate(admitted, archive, resolver)
    _assert_insufficient(module, report, ("SCHEDULE_CONTINUITY_UNPROVEN",))


@pytest.mark.parametrize("schema_version", (2, 3))
def test_s20_completed_archives_are_admissible_for_each_schedule_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], schema_version: int
) -> None:
    module, _ = _api()
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(root, size=1, directions=(Decimal("1"),))
    digest, _ = _schedule(root, schema_version=schema_version)
    value = _input_value(fixture, ids, digest)
    code = _cli(module)(_cli_args(tmp_path, root, value))
    captured = capsys.readouterr()
    assert code == 0 and captured.err == ""
    _assert_public_report_bytes(module, captured.out.encode(), value, observed=True)


def test_s20_partial_archive_is_admissible_and_discarded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module, _ = _api()
    root = _private_root(tmp_path)
    partial_cutoff = datetime(2026, 1, 13, 9, 30, tzinfo=UTC)
    fixture, ids = _archive_fixture(
        root,
        size=1,
        directions=(Decimal("1"),),
        include_partial=True,
        partial_cutoff=partial_cutoff,
    )
    s20 = fixture["records"][-1]
    assert s20["request"].include_partial_current_session is True
    assert s20["value"]["partials"]
    assert s20["facts"][0].partial_current_session == PartialCurrentSessionSnapshotV1(
        s20["facts"][0].member,
        date(2026, 1, 13),
        Decimal("1"),
        1,
        datetime(2026, 1, 13, 9, tzinfo=UTC),
        datetime(2026, 1, 13, 9, 15, tzinfo=UTC),
        partial_cutoff,
        hashlib.sha256(f"partial:{s20['facts'][0].member.isin}".encode()).hexdigest(),
        CurrentBarStateV1.PARTIAL_CURRENT_SESSION,
    )
    assert [
        (entry["feature"], entry["interval"]) for entry in s20["value"]["ledger"]
    ] == [("DAILY_OHLCV", "1d"), ("PARTIAL_CURRENT_SESSION", "1m")]
    digest, _ = _schedule(
        root, schema_version=3, as_of=partial_cutoff, include_next_current_session=True
    )
    value = _input_value(fixture, ids, digest, decision_cutoff=partial_cutoff)
    code = _cli(module)(_cli_args(tmp_path, root, value))
    captured = capsys.readouterr()
    assert code == 0 and captured.err == ""
    _assert_public_report_bytes(module, captured.out.encode(), value, observed=True)


@pytest.mark.parametrize(
    ("include_partial", "partial_member_indexes", "expected_ledger_count"),
    [
        (False, None, 2),
        (True, None, 4),
        (True, (0,), 4),
    ],
)
def test_direct_archive_reader_admits_authentic_sprint10_ledger_shapes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    include_partial: bool,
    partial_member_indexes: tuple[int, ...] | None,
    expected_ledger_count: int,
) -> None:
    module, _ = _api()
    root = _private_root(tmp_path)
    partial_cutoff = datetime(2026, 1, 13, 9, 30, tzinfo=UTC)
    fixture, ids = _archive_fixture(
        root,
        size=2,
        directions=(Decimal("1"), Decimal("0")),
        include_partial=include_partial,
        partial_cutoff=partial_cutoff if include_partial else None,
        partial_member_indexes=partial_member_indexes,
    )
    digest, _ = _schedule(
        root,
        as_of=partial_cutoff if include_partial else _CUTOFF,
        include_next_current_session=include_partial,
    )
    value = _input_value(
        fixture,
        ids,
        digest,
        decision_cutoff=partial_cutoff if include_partial else _CUTOFF,
    )
    final = fixture["records"][-1]["value"]
    assert len(final["ledger"]) == expected_ledger_count
    if partial_member_indexes == (0,):
        assert [entry["availability_state"] for entry in final["ledger"]] == [
            "AVAILABLE",
            "AVAILABLE",
            "AVAILABLE",
            "NOT_RETAINED",
        ]
    code = _cli(module)(_cli_args(tmp_path, root, value))
    captured = capsys.readouterr()
    assert code == 0 and captured.err == ""
    _assert_public_report_bytes(module, captured.out.encode(), value, observed=True)


@pytest.mark.parametrize(
    "mutation", ("partial_state", "partial_binding", "partial_order")
)
def test_direct_archive_reader_rejects_malformed_requested_partial_ledger_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], mutation: str
) -> None:
    module, _ = _api()
    root = _private_root(tmp_path)
    cutoff = datetime(2026, 1, 13, 9, 30, tzinfo=UTC)
    fixture, ids = _archive_fixture(
        root,
        size=2,
        directions=(Decimal("1"), Decimal("0")),
        include_partial=True,
        partial_cutoff=cutoff,
        partial_member_indexes=None if mutation == "partial_order" else (0,),
    )
    digest, _ = _schedule(root, as_of=cutoff, include_next_current_session=True)
    value = _input_value(fixture, ids, digest, decision_cutoff=cutoff)
    record = fixture["records"][-1]
    original_id = record["id"]

    def corrupt(item: dict[str, Any]) -> None:
        if mutation == "partial_state":
            item["ledger"][3]["availability_state"] = "SOURCE_GAP"
        elif mutation == "partial_binding":
            item["ledger"][3]["source_identity"] = "retained-market-data"
        else:
            item["ledger"][1], item["ledger"][3] = item["ledger"][3], item["ledger"][1]

    new_id = _replace_archive(record, corrupt)
    _replace_input_archive_id(value, original_id, new_id)
    _recompute_input_identity(value)
    code = _cli(module)(_cli_args(tmp_path, root, value))
    captured = capsys.readouterr()
    assert code == 1 and captured.err == ""
    _assert_public_report_bytes(
        module,
        captured.out.encode(),
        value,
        observed=False,
        reasons=("SPRINT10_LEDGER_INVALID",),
    )


@pytest.mark.parametrize("case", ("earlier", "later"))
def test_direct_archive_reader_rejects_partial_session_not_equal_to_archive_cutoff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    module, _ = _api()
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(
        root,
        size=1,
        directions=(Decimal("1"),),
        include_partial=True,
    )
    digest, _ = _schedule(root)
    record = fixture["records"][-1]
    original_id = record["id"]
    decision_cutoff = datetime(
        2026, 1, 14 if case == "earlier" else 15, 9, 30, tzinfo=UTC
    )
    value = _input_value(fixture, ids, digest, decision_cutoff=decision_cutoff)

    def change_session(item: dict[str, Any]) -> None:
        item["report"]["invocation_cutoff"] = decision_cutoff.strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        if case == "later":
            partial = item["facts"][0]["partial_current_session"]
            assert type(partial) is dict
            partial.update(
                session="2026-01-14",
                last_bar_at="2026-01-14T09:00:00.000000Z",
                published_at="2026-01-14T09:15:00.000000Z",
                known_at="2026-01-14T09:30:00.000000Z",
            )
            item["partials"][0] = partial

    new_id = _replace_archive(record, change_session)
    _replace_input_archive_id(value, original_id, new_id)
    _recompute_input_identity(value)
    code = _cli(module)(_cli_args(tmp_path, root, value))
    captured = capsys.readouterr()
    assert code == 1 and captured.err == ""
    _assert_public_report_bytes(
        module,
        captured.out.encode(),
        value,
        observed=False,
        reasons=("SPRINT10_MEMBER_FACT_INVALID",),
    )


_PUBLIC_REPORT_FIELDS = {
    "contract_version",
    "schema_identity_sha256",
    "calculation_identity_sha256",
    "input_identity_sha256",
    "request_identity_sha256",
    "cohort_identity_sha256",
    "cohort_size",
    "decision_cutoff",
    "decision_session",
    "comparison_session",
    "archive_object_sha256s",
    "schedule_evidence_sha256",
    "schedule_source",
    "schedule_source_release",
    "code_identity_sha256",
    "evidence_state",
    "regime_label",
    "advances",
    "declines",
    "unchanged",
    "member_directions",
    "reasons",
    "report_identity_sha256",
}


def _expected_request_identity(value: dict[str, object]) -> str:
    return hashlib.sha256(
        _canonical(
            {
                "contract_version": _CONTRACT,
                "input_identity_sha256": value["input_identity_sha256"],
                "cohort_identity_sha256": value["cohort_identity_sha256"],
                "cohort_size": value["cohort_size"],
                "decision_cutoff": value["decision_cutoff"],
                "decision_session": value["decision_session"],
                "archive_object_sha256s": value["archive_object_sha256s"],
                "schedule_evidence_sha256": value["schedule_evidence_sha256"],
                "schedule_source": value["schedule_source"],
                "schedule_source_release": value["schedule_source_release"],
                "schema_identity_sha256": _SCHEMA,
                "calculation_identity_sha256": _CALCULATION,
            }
        )
    ).hexdigest()


def _assert_public_report_bytes(
    module: Any,
    encoded: bytes,
    value: dict[str, object],
    *,
    observed: bool,
    reasons: tuple[str, ...] = (),
) -> dict[str, Any]:
    decoded = json.loads(encoded)
    assert encoded.endswith(b"\n") and _canonical(decoded) == encoded
    assert set(decoded) == _PUBLIC_REPORT_FIELDS
    assert (
        decoded["contract_version"],
        decoded["schema_identity_sha256"],
        decoded["calculation_identity_sha256"],
    ) == (_CONTRACT, _SCHEMA, _CALCULATION)
    for report_field in (
        "input_identity_sha256",
        "cohort_identity_sha256",
        "cohort_size",
        "decision_cutoff",
        "decision_session",
        "archive_object_sha256s",
        "schedule_evidence_sha256",
        "schedule_source",
        "schedule_source_release",
    ):
        assert decoded[report_field] == value[report_field]
    assert (
        decoded["code_identity_sha256"]
        == module.current_supplied_cohort_market_regime_runtime_code_identity_v1()
    )
    assert decoded["request_identity_sha256"] == _expected_request_identity(value)
    identity = decoded.pop("report_identity_sha256")
    assert identity == hashlib.sha256(_canonical(decoded)).hexdigest()
    if observed:
        assert decoded["evidence_state"] == "OBSERVED"
        assert decoded["reasons"] == [] and decoded["member_directions"] is None
        assert decoded["comparison_session"] == _sessions()[0].isoformat()
        assert decoded["regime_label"] is not None
        assert (
            decoded["advances"] + decoded["declines"] + decoded["unchanged"]
            == value["cohort_size"]
        )
    else:
        assert decoded["evidence_state"] == "INSUFFICIENT_EVIDENCE"
        assert decoded["reasons"] == list(reasons)
        assert all(
            decoded[field] is None
            for field in (
                "comparison_session",
                "regime_label",
                "advances",
                "declines",
                "unchanged",
                "member_directions",
            )
        )
    decoded["report_identity_sha256"] = identity
    return decoded


def _assert_redacted(
    output: str, fixture: dict[str, Any], root: Path, input_path: Path
) -> None:
    sentinels = (
        *(member.isin for member in fixture["members"]),
        *(member.symbol for member in fixture["members"]),
        *(
            json.dumps(fact.completed_daily.close.to_eng_string())
            for record in fixture["records"]
            for fact in record["facts"]
        ),
        *(
            fact.completed_daily.source_receipt_sha256
            for record in fixture["records"]
            for fact in record["facts"]
        ),
        str(root),
        str(input_path),
        ".current-fact-archive-v1",
        "calendar-schedules",
        "WEEKEND_OR_OFFICIAL_CLOSURE",
        '"close"',
    )
    assert all(sentinel not in output for sentinel in sentinels)


def test_input_roundtrip_report_schema_identity_and_cli_bytes_are_closed_and_redacted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module, evaluate = _api()
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(
        root,
        size=5,
        directions=(
            Decimal("1"),
            Decimal("1"),
            Decimal("1"),
            Decimal("-1"),
            Decimal("0"),
        ),
    )
    digest, _ = _schedule(root)
    value = _input_value(fixture, ids, digest)
    admitted = _admit_input(module, value)
    assert admitted.canonical_json_bytes() == _canonical(value)
    report, archive, _ = _run_pure(
        module,
        evaluate,
        root,
        directions=(
            Decimal("1"),
            Decimal("1"),
            Decimal("1"),
            Decimal("-1"),
            Decimal("0"),
        ),
    )
    assert type(archive.calls[0][0]) is _type(
        module, "CurrentSuppliedCohortMarketRegimeRequestV1"
    )
    assert type(report) is _type(module, "CurrentSuppliedCohortMarketRegimeReportV1")
    encoded = report.canonical_json_bytes()
    _assert_public_report_bytes(module, encoded, value, observed=True)
    args = _cli_args(tmp_path, root, value)
    code = _cli(module)(args)
    cli = capsys.readouterr()
    assert code == 0 and cli.err == "" and cli.out == encoded.decode()
    _assert_public_report_bytes(module, cli.out.encode(), value, observed=True)
    _assert_redacted(cli.out, fixture, root, Path(args[2]))


def _replace_input_archive_id(
    value: dict[str, object], old_id: str, new_id: str
) -> None:
    ids = list(value["archive_object_sha256s"])  # type: ignore[arg-type]
    assert len(ids) == 21 and old_id in ids
    ids[ids.index(old_id)] = new_id
    assert len(set(ids)) == 21
    value["archive_object_sha256s"] = sorted(ids)


def _recompute_input_identity(value: dict[str, object]) -> None:
    value["input_identity_sha256"] = hashlib.sha256(
        _canonical(
            {key: item for key, item in value.items() if key != "input_identity_sha256"}
        )
    ).hexdigest()


@pytest.mark.parametrize(
    ("reason", "mutation"),
    [
        ("ARCHIVE_OBJECT_MISSING", "missing"),
        ("ARCHIVE_OBJECT_UNSAFE", "unsafe"),
        ("ARCHIVE_OBJECT_INVALID", "malformed"),
        ("ARCHIVE_CONTENT_ID_MISMATCH", "digest"),
        ("ARCHIVE_BINDING_MISMATCH", "binding"),
        ("SPRINT10_REPORT_INSUFFICIENT", "insufficient"),
        ("SPRINT10_REPORT_INVALID", "report_schema"),
        ("SPRINT10_MEMBER_FACT_INVALID", "partial_as_completed"),
        ("SPRINT10_LEDGER_UNAVAILABLE", "unavailable_ledger"),
        ("SPRINT10_LEDGER_INVALID", "ledger"),
        ("COHORT_BINDING_MISMATCH", "cohort"),
        ("ARCHIVE_SESSION_DUPLICATE_OR_CONFLICTING", "duplicate_session"),
        ("SCHEDULE_EVIDENCE_MISSING", "schedule_missing"),
        ("SCHEDULE_EVIDENCE_AMBIGUOUS", "schedule_release"),
        ("SCHEDULE_EVIDENCE_LATE", "schedule_late"),
        ("SCHEDULE_CONTINUITY_UNPROVEN", "schedule_coverage"),
        ("DECISION_SESSION_NOT_LATEST_ADMISSIBLE", "latest"),
        ("FACT_CUTOFF_OR_FRESHNESS_UNPROVEN", "stale"),
        ("FACT_FUTURE_KNOWN", "future"),
    ],
)
def test_cli_real_retained_artifacts_produce_each_closed_reason(  # noqa: C901 - one case table mutates every closed evidence boundary
    tmp_path: Path, capsys: pytest.CaptureFixture[str], reason: str, mutation: str
) -> None:
    module, _ = _api()
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(
        root,
        size=1,
        directions=(Decimal("1"),),
        include_partial=mutation == "partial_as_completed",
    )
    digest, _ = _schedule(root)
    value = _input_value(fixture, ids, digest)
    record = (
        fixture["records"][-1]
        if mutation == "partial_as_completed"
        else fixture["records"][0]
    )
    original_id = record["id"]
    record["path"].chmod(0o600)
    if mutation == "missing":
        record["path"].unlink()
    elif mutation == "unsafe":
        record["path"].chmod(0o644)
    elif mutation == "malformed":
        record["path"].write_bytes(b"{")
    elif mutation == "digest":
        canonical_variant = json.loads(record["path"].read_bytes())
        canonical_variant["code_identity"] = "a" * 64
        canonical_variant["report"]["code_identity"] = "a" * 64
        _refresh_identity(canonical_variant["report"], "report_identity_sha256")
        record["path"].write_bytes(_canonical(canonical_variant))
    elif mutation == "binding":
        new_id = _replace_archive(
            record, lambda item: item.__setitem__("code_identity", "a" * 64)
        )
        _replace_input_archive_id(value, original_id, new_id)
    elif mutation == "insufficient":
        new_id = _replace_archive(record, _make_report_insufficient)
        _replace_input_archive_id(value, original_id, new_id)
    elif mutation == "report_schema":
        new_id = _replace_archive(
            record,
            lambda item: item["report"].__setitem__("schema_identity_sha256", "a" * 64),
        )
        _replace_input_archive_id(value, original_id, new_id)
    elif mutation == "partial_as_completed":
        assert record["value"]["partials"]
        new_id = _replace_archive(
            record,
            lambda item: item["facts"][0].__setitem__(
                "completed_daily", item["partials"][0]
            ),
        )
        _replace_input_archive_id(value, original_id, new_id)
    elif mutation == "unavailable_ledger":
        new_id = _replace_archive(
            record,
            lambda item: item["ledger"][0].__setitem__(
                "availability_state", "NOT_RETAINED"
            ),
        )
        _replace_input_archive_id(value, original_id, new_id)
    elif mutation == "ledger":
        new_id = _replace_archive(record, lambda item: item["ledger"].pop())
        _replace_input_archive_id(value, original_id, new_id)
    elif mutation == "cohort":

        def mismatch_cohort(item: dict[str, Any]) -> None:
            item["cohort_identity_sha256"] = "a" * 64
            item["report"]["cohort_identity_sha256"] = "a" * 64

        new_id = _replace_archive(record, mismatch_cohort)
        _replace_input_archive_id(value, original_id, new_id)
    elif mutation == "duplicate_session":
        source = json.loads(_canonical(fixture["records"][0]["value"]))
        record = fixture["records"][1]
        original_id = record["id"]

        def duplicate_session(item: dict[str, Any]) -> None:
            item.clear()
            item.update(source)
            item["code_identity"] = "a" * 64
            item["report"]["code_identity"] = "a" * 64

        new_id = _replace_archive(record, duplicate_session)
        _replace_input_archive_id(value, original_id, new_id)
    elif mutation == "schedule_missing":
        (root / "calendar-schedules" / "sha256" / f"{digest}.json").unlink()
    elif mutation == "schedule_release":
        value["schedule_source_release"] = "sha256:" + "c" * 64
    elif mutation == "schedule_late":
        value["schedule_evidence_sha256"] = _replace_schedule(
            root,
            digest,
            lambda item: item.__setitem__("as_of", "2026-01-12T10:00:00.000001Z"),
        )
    elif mutation == "schedule_coverage":

        def narrow_schedule(item: dict[str, Any]) -> None:
            item["covered_to"] = "2026-01-11"
            item["sessions"] = [
                session
                for session in item["sessions"]
                if session["trade_date"] <= "2026-01-11"
            ]
            item["closures"] = [
                closure
                for closure in item["closures"]
                if closure["trade_date"] <= "2026-01-11"
            ]

        value["schedule_evidence_sha256"] = _replace_schedule(
            root, digest, narrow_schedule
        )
    elif mutation == "latest":
        value["decision_session"] = "2026-01-09"
    elif mutation == "stale":
        new_id = _replace_archive(
            record,
            lambda item: item["facts"][0]["completed_daily"].__setitem__(
                "freshness_state", "STALE"
            ),
        )
        _replace_input_archive_id(value, original_id, new_id)
    elif mutation == "future":
        new_id = _replace_archive(
            record,
            lambda item: item["facts"][0]["completed_daily"].__setitem__(
                "known_at", "2026-01-12T10:00:00.000001Z"
            ),
        )
        _replace_input_archive_id(value, original_id, new_id)
    _recompute_input_identity(value)
    args = _cli_args(tmp_path, root, value)
    code = _cli(module)(args)
    captured = capsys.readouterr()

    assert code == 1 and captured.err == ""
    _assert_public_report_bytes(
        module, captured.out.encode(), value, observed=False, reasons=(reason,)
    )
    _assert_redacted(captured.out, fixture, root, Path(args[2]))


@pytest.mark.parametrize(
    ("case", "expected_code", "expected_reason"),
    [
        ("digest_mismatch", 1, "SCHEDULE_EVIDENCE_MISSING"),
        ("noncanonical", 1, "SCHEDULE_EVIDENCE_MISSING"),
        ("over_byte_limit", 1, "SCHEDULE_EVIDENCE_MISSING"),
        ("wrong_authority", 1, "SCHEDULE_EVIDENCE_AMBIGUOUS"),
        ("omitted_session", 1, "SCHEDULE_CONTINUITY_UNPROVEN"),
        ("byte_limit", 0, None),
        ("row_limit", 0, None),
        ("over_row_limit", 1, "SCHEDULE_EVIDENCE_AMBIGUOUS"),
    ],
)
def test_cli_schedule_adapter_digest_authority_continuity_and_exact_limits(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    case: str,
    expected_code: int,
    expected_reason: str | None,
) -> None:
    module, _ = _api()
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(root, size=1, directions=(Decimal("1"),))
    digest, _ = _schedule(root)
    value = _input_value(fixture, ids, digest)
    schedule_path = root / "calendar-schedules" / "sha256" / f"{digest}.json"
    if case == "digest_mismatch":
        value["schedule_evidence_sha256"] = "f" * 64
    elif case == "noncanonical":
        schedule_path.write_bytes(schedule_path.read_bytes() + b"\n")
    elif case == "over_byte_limit":
        value["schedule_evidence_sha256"] = _replace_schedule_at_size(
            root, digest, 1_000_001
        )
    elif case == "wrong_authority":
        value["schedule_evidence_sha256"] = _replace_schedule(
            root, digest, lambda item: item.__setitem__("source", "other-authority")
        )
    elif case == "omitted_session":
        value["schedule_evidence_sha256"] = _replace_schedule(
            root, digest, lambda item: item["sessions"].pop(10)
        )
    elif case == "byte_limit":
        value["schedule_evidence_sha256"] = _replace_schedule_at_size(
            root, digest, 1_000_000
        )
    elif case == "row_limit":
        value["schedule_evidence_sha256"] = _replace_schedule_at_row_count(
            root, digest, 4_096
        )
    else:
        value["schedule_evidence_sha256"] = _replace_schedule_at_row_count(
            root, digest, 4_097
        )
    _recompute_input_identity(value)
    args = _cli_args(tmp_path, root, value)
    code = _cli(module)(args)
    captured = capsys.readouterr()
    assert code == expected_code and captured.err == ""
    if expected_reason is None:
        _assert_public_report_bytes(module, captured.out.encode(), value, observed=True)
    else:
        _assert_public_report_bytes(
            module,
            captured.out.encode(),
            value,
            observed=False,
            reasons=(expected_reason,),
        )
    _assert_redacted(captured.out, fixture, root, Path(args[2]))


def test_real_archive_two_independent_same_stage_faults_reverse_order_are_deduplicated_and_ordered(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module, _ = _api()
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(root, size=1, directions=(Decimal("1"),))
    digest, _ = _schedule(root)
    value = _input_value(fixture, ids, digest)
    first_record, second_record = fixture["records"][:2]
    first_original, second_original = first_record["id"], second_record["id"]
    first = _replace_archive(first_record, lambda item: item["ledger"].pop())
    second = _replace_archive(
        second_record,
        lambda item: item["facts"][0].__setitem__("completed_daily", None),
    )
    _replace_input_archive_id(value, first_original, first)
    _replace_input_archive_id(value, second_original, second)
    _recompute_input_identity(value)
    assert (
        len(value["archive_object_sha256s"])
        == len(set(value["archive_object_sha256s"]))
        == 21
    )  # type: ignore[arg-type]
    code = _cli(module)(_cli_args(tmp_path, root, value))
    assert code == 1
    assert json.loads(capsys.readouterr().out)["reasons"] == [
        "SPRINT10_MEMBER_FACT_INVALID",
        "SPRINT10_LEDGER_INVALID",
    ]


@pytest.mark.parametrize(
    ("case", "reason", "partial"),
    [
        ("malformed_insufficient", "SPRINT10_REPORT_INVALID", False),
        ("report_cutoff", "SPRINT10_REPORT_INVALID", False),
        ("report_state", "SPRINT10_REPORT_INVALID", False),
        ("report_reasons", "SPRINT10_REPORT_INVALID", False),
        ("envelope_contract", "ARCHIVE_BINDING_MISMATCH", False),
        ("daily_open", "SPRINT10_MEMBER_FACT_INVALID", False),
        ("daily_volume", "SPRINT10_MEMBER_FACT_INVALID", False),
        ("daily_receipt", "SPRINT10_MEMBER_FACT_INVALID", False),
        ("daily_clock", "SPRINT10_MEMBER_FACT_INVALID", False),
        ("freshness_age", "FACT_CUTOFF_OR_FRESHNESS_UNPROVEN", False),
        ("partial_envelope_relation", "SPRINT10_MEMBER_FACT_INVALID", True),
        ("partial_state", "SPRINT10_MEMBER_FACT_INVALID", True),
        ("partial_price", "SPRINT10_MEMBER_FACT_INVALID", True),
        ("partial_volume", "SPRINT10_MEMBER_FACT_INVALID", True),
        ("partial_receipt", "SPRINT10_MEMBER_FACT_INVALID", True),
        ("partial_clock", "SPRINT10_MEMBER_FACT_INVALID", True),
        ("ledger_source", "SPRINT10_LEDGER_INVALID", False),
        ("ledger_revision", "SPRINT10_LEDGER_INVALID", False),
        ("ledger_affected", "SPRINT10_LEDGER_INVALID", False),
        ("ledger_window", "SPRINT10_LEDGER_INVALID", False),
        ("ledger_published", "SPRINT10_LEDGER_INVALID", False),
        ("ledger_clock", "SPRINT10_LEDGER_INVALID", False),
        ("ledger_feature", "SPRINT10_LEDGER_INVALID", False),
        ("ledger_instrument", "SPRINT10_LEDGER_INVALID", False),
        ("ledger_count", "SPRINT10_LEDGER_INVALID", False),
        ("ledger_order", "SPRINT10_LEDGER_INVALID", True),
    ],
)
def test_direct_archive_reader_rejects_closed_sprint10_admission_gaps(  # noqa: C901 - one case table mutates every retained-admission boundary
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    case: str,
    reason: str,
    partial: bool,
) -> None:
    module, _ = _api()
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(
        root, size=1, directions=(Decimal("1"),), include_partial=partial
    )
    digest, _ = _schedule(root)
    value = _input_value(
        fixture,
        ids,
        digest,
        decision_cutoff=(
            datetime(2026, 1, 13, 9, 30, tzinfo=UTC) if partial else _CUTOFF
        ),
    )
    record = fixture["records"][-1] if partial else fixture["records"][0]
    original_id = record["id"]

    def mutate(item: dict[str, Any]) -> None:  # noqa: C901 - case table keeps each causal mutation local
        if case == "malformed_insufficient":
            _make_report_insufficient(item)
            item["report"]["reasons"] = []
        elif case == "report_cutoff":
            item["report"]["invocation_cutoff"] = "not-an-instant"
        elif case == "report_state":
            item["report"]["evidence_state"] = "UNKNOWN"
        elif case == "report_reasons":
            item["report"]["reasons"] = ["DAILY_BAR_MISSING"]
        elif case == "envelope_contract":
            item["contract_version"] = "current-supplied-cohort-market-data@v0"
        elif case == "daily_open":
            item["facts"][0]["completed_daily"]["open"] = "0"
        elif case == "daily_volume":
            item["facts"][0]["completed_daily"]["volume"] = True
        elif case == "daily_receipt":
            item["facts"][0]["completed_daily"]["source_receipt_sha256"] = (
                "not-a-digest"
            )
        elif case == "daily_clock":
            item["facts"][0]["completed_daily"]["data_cutoff"] = (
                "2025-12-10T09:31:00.000000Z"
            )
        elif case == "freshness_age":
            item["report"]["invocation_cutoff"] = "2025-12-15T10:00:00.000000Z"
        elif case == "partial_envelope_relation":
            item["partials"].pop()
        elif case == "partial_state":
            item["partials"][0]["bar_state"] = "COMPLETED_DAILY"
        elif case == "partial_price":
            item["partials"][0]["observed_price"] = "0"
        elif case == "partial_volume":
            item["partials"][0]["observed_volume"] = True
        elif case == "partial_receipt":
            item["partials"][0]["source_receipt_sha256"] = "not-a-digest"
        elif case == "partial_clock":
            item["partials"][0]["published_at"] = "2026-01-13T09:31:00.000000Z"
        elif case == "ledger_source":
            item["ledger"][0]["source_identity"] = "other-retained-source"
        elif case == "ledger_revision":
            item["ledger"][0]["revision_identity_sha256"] = "a" * 64
        elif case == "ledger_affected":
            item["ledger"][0]["affected_identity_sha256"] = "a" * 64
        elif case == "ledger_window":
            item["ledger"][0]["window_through"] = "2025-12-10T09:01:00.000000Z"
        elif case == "ledger_published":
            item["ledger"][0]["published_at"] = "2025-12-10T09:31:00.000000Z"
        elif case == "ledger_clock":
            item["ledger"][0]["known_at"] = "2025-12-10T09:29:00.000000Z"
        elif case == "ledger_feature":
            item["ledger"][0]["feature"] = "OTHER"
        elif case == "ledger_instrument":
            item["ledger"][0]["instrument_identity"] = "wrong"
        elif case == "ledger_count":
            item["ledger"].pop()
        else:
            item["ledger"].reverse()

    new_id = _replace_archive(record, mutate)
    _replace_input_archive_id(value, original_id, new_id)
    _recompute_input_identity(value)
    code = _cli(module)(_cli_args(tmp_path, root, value))
    captured = capsys.readouterr()
    assert code == 1 and captured.err == ""
    _assert_public_report_bytes(
        module, captured.out.encode(), value, observed=False, reasons=(reason,)
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "fewer_ids",
        "more_ids",
        "duplicate_id",
        "noncanonical_id",
        "wrong_contract",
        "bad_cutoff",
        "malformed_release",
        "relative_root",
        "missing_root",
        "unsafe_root",
    ),
)
def test_cli_structural_rejections_exit_two_with_sanitized_diagnostics(  # noqa: C901 - one case table covers input and root boundaries
    tmp_path: Path, capsys: pytest.CaptureFixture[str], mutation: str
) -> None:
    module, _ = _api()
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(root, size=1, directions=(Decimal("1"),))
    digest, _ = _schedule(root)
    value = _input_value(fixture, ids, digest)
    root_arg = root
    if mutation == "fewer_ids":
        value["archive_object_sha256s"] = value["archive_object_sha256s"][:-1]  # type: ignore[index]
    elif mutation == "more_ids":
        value["archive_object_sha256s"] = [*value["archive_object_sha256s"], "f" * 64]  # type: ignore[index]
    elif mutation == "duplicate_id":
        value["archive_object_sha256s"] = [ids[0]] * 21
    elif mutation == "noncanonical_id":
        value["archive_object_sha256s"] = ["A" * 64] * 21
    elif mutation == "wrong_contract":
        value["contract_version"] = "wrong"
    elif mutation == "bad_cutoff":
        value["decision_cutoff"] = "not-an-instant"
    elif mutation == "malformed_release":
        value["schedule_source_release"] = "not-a-release"
    elif mutation == "relative_root":
        root_arg = Path("relative")
    elif mutation == "missing_root":
        root_arg = tmp_path / "missing"
    else:
        root.chmod(0o755)
    _recompute_input_identity(value)
    args = _cli_args(tmp_path, root_arg, value)
    code = _cli(module)(args)
    captured = capsys.readouterr()
    assert code == 2 and captured.out == ""
    for private in (
        str(root),
        str(root_arg),
        str(Path(args[2])),
        "owner-input.json",
        *(member.isin for member in fixture["members"]),
        *(member.symbol for member in fixture["members"]),
        *(
            fact.completed_daily.close.to_eng_string()
            for record in fixture["records"]
            for fact in record["facts"]
        ),
        *(
            fact.completed_daily.source_receipt_sha256
            for record in fixture["records"]
            for fact in record["facts"]
        ),
        ".current-fact-archive-v1",
        "calendar-schedules",
        "WEEKEND_OR_OFFICIAL_CLOSURE",
    ):
        assert private not in captured.err


@pytest.mark.parametrize("payload", (b"[]\n", b"null\n"))
def test_cli_rejects_canonical_non_object_owner_input_without_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], payload: bytes
) -> None:
    module, _ = _api()
    root = _private_root(tmp_path)
    input_file = tmp_path / "owner-input.json"
    input_file.write_bytes(payload)
    input_file.chmod(0o600)
    code = _cli(module)(
        [
            "regime-current",
            "--input-file",
            str(input_file),
            "--storage-root",
            str(root),
            "--output",
            "json",
        ]
    )
    captured = capsys.readouterr()
    assert code == 2 and captured.out == ""
    assert captured.err == "invalid regime-current request\n"


def test_runtime_identity_is_exact_path_nul_digest_composite() -> None:
    module, _ = _api()
    manifest_module = importlib.import_module(
        "swing_trading_ai_assistant.market_regime.current_supplied_cohort_runtime_identity_manifest"
    )
    source_digests = (
        manifest_module.CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_SOURCE_DIGESTS_V1
    )
    assert tuple(source_digests) == _RUNTIME_SOURCES
    manifest_digest = hashlib.sha256(
        Path(manifest_module.__file__).read_bytes()
    ).hexdigest()
    expected_bytes = (
        b"".join(
            path.encode() + b"\0" + source_digests[path].encode() + b"\0"
            for path in _RUNTIME_SOURCES
        )
        + _RUNTIME_MANIFEST.encode()
        + b"\0"
        + manifest_digest.encode()
        + b"\0"
    )
    assert (
        module.current_supplied_cohort_market_regime_runtime_code_identity_v1()
        == hashlib.sha256(expected_bytes).hexdigest()
    )


def test_runtime_identity_accepts_checkout_and_installed_package_layouts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _ = _api()
    manifest_module = importlib.import_module(
        "swing_trading_ai_assistant.market_regime.current_supplied_cohort_runtime_identity_manifest"
    )
    checkout_root = Path(module.__file__).parent.parent
    checkout_identity = (
        module.current_supplied_cohort_market_regime_runtime_code_identity_v1()
    )
    assert module._runtime_root() == checkout_root

    installed_root = tmp_path / "venv" / "site-packages" / "swing_trading_ai_assistant"
    modules = {
        "src/swing_trading_ai_assistant/market_data/cli.py": importlib.import_module(
            "swing_trading_ai_assistant.market_data.cli"
        ),
        "src/swing_trading_ai_assistant/market_data/current_cohort.py": importlib.import_module(
            "swing_trading_ai_assistant.market_data.current_cohort"
        ),
        "src/swing_trading_ai_assistant/market_data/schedule_evidence.py": importlib.import_module(
            "swing_trading_ai_assistant.market_data.schedule_evidence"
        ),
        "src/swing_trading_ai_assistant/market_data/storage_root_lease.py": importlib.import_module(
            "swing_trading_ai_assistant.market_data.storage_root_lease"
        ),
        "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort.py": module,
        _RUNTIME_MANIFEST: manifest_module,
    }
    for logical_path, imported_module in modules.items():
        destination = installed_root.joinpath(*logical_path.split("/")[2:])
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(Path(imported_module.__file__).read_bytes())
        destination.chmod(0o600)
        monkeypatch.setattr(imported_module, "__file__", str(destination))
        monkeypatch.setattr(
            imported_module,
            "__loader__",
            importlib.machinery.SourceFileLoader(
                imported_module.__name__, str(destination)
            ),
        )

    assert module._runtime_root() == installed_root
    assert (
        module.current_supplied_cohort_market_regime_runtime_code_identity_v1()
        == checkout_identity
    )


@pytest.mark.parametrize(
    "invalid",
    ("20260112", "2026-W03-1", "2026-1-12", "2026-01-12T00:00:00"),
)
def test_local_date_requires_canonical_calendar_spelling_and_preserves_identity_roundtrip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], invalid: str
) -> None:
    module, _ = _api()
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(root, size=1, directions=(Decimal("1"),))
    digest, _ = _schedule(root)
    valid = _input_value(fixture, ids, digest)
    admitted = _admit_input(module, valid)
    assert admitted.decision_session.isoformat() == valid["decision_session"]
    assert admitted.canonical_json_bytes() == _canonical(valid)

    valid["decision_session"] = invalid
    _recompute_input_identity(valid)
    args = _cli_args(tmp_path, root, valid)
    assert _cli(module)(args) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "invalid regime-current request\n"


@pytest.mark.parametrize("position", (0, 10, 20))
def test_before_official_close_at_any_grid_position_is_schedule_insufficiency(
    tmp_path: Path, position: int
) -> None:
    module, evaluate = _api()
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(root, size=1, directions=(Decimal("1"),))
    digest, schedule = _schedule(root)
    admitted = _admit_input(module, _input_value(fixture, ids, digest))
    grid, continuity = _private_ready(module, fixture, ids, digest, schedule)
    session = grid.sessions[position]
    tampered_sessions = list(grid.sessions)
    tampered_sessions[position] = replace(
        session,
        invocation_cutoff=continuity.sessions[position].close_at
        - timedelta(microseconds=1),
    )
    tampered_grid = _type(module, "PrivateCurrentCohortArchiveGridProjectionV1")(
        grid.cohort_identity_sha256, grid.cohort_size, tuple(tampered_sessions)
    )
    archive = _RecordingArchivePort(
        _type(module, "CurrentSuppliedCohortMarketRegimeRequestV1"),
        _type(module, "ArchiveReadResultV1")("READY", tampered_grid, ()),
        admitted,
    )
    resolver = _RecordingSchedulePort(
        _type(module, "ScheduleReadResultV1")("RESOLVED", continuity, ()), admitted
    )
    _assert_insufficient(
        module,
        evaluate(admitted, archive, resolver),
        ("SCHEDULE_CONTINUITY_UNPROVEN",),
    )


@pytest.mark.parametrize(
    "fault",
    (
        "missing",
        "extra",
        "malformed",
        "digest_mismatch",
        "unsafe_source",
        "unsafe_manifest",
        "loader_lookalike",
        "loader_source_path_mismatch",
        "loader_path_mismatch",
        "path_mismatch",
        "composite",
    ),
)
def test_runtime_manifest_and_source_map_fail_before_report_with_sanitized_exit_two(  # noqa: C901 - one case table covers runtime-identity tamper paths
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    module, _ = _api()
    manifest_module = importlib.import_module(
        "swing_trading_ai_assistant.market_regime.current_supplied_cohort_runtime_identity_manifest"
    )
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(root, size=1, directions=(Decimal("1"),))
    digest, _ = _schedule(root)
    source_digests = dict(
        manifest_module.CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_SOURCE_DIGESTS_V1
    )
    if fault == "missing":
        source_digests.pop(_RUNTIME_SOURCES[0])
    elif fault == "extra":
        source_digests["src/extra.py"] = "a" * 64
    elif fault == "malformed":
        source_digests[_RUNTIME_SOURCES[0]] = "not-a-digest"
    elif fault == "digest_mismatch":
        source_digests[_RUNTIME_SOURCES[0]] = "a" * 64
    elif fault == "unsafe_source":
        source_digests = {"../unsafe.py": "a" * 64}
    elif fault == "unsafe_manifest":
        monkeypatch.setattr(manifest_module, "__file__", "../unsafe-manifest.py")
    elif fault == "loader_lookalike":
        monkeypatch.setattr(module, "__loader__", type("SourceFileLoader", (), {})())
    elif fault == "loader_source_path_mismatch":
        monkeypatch.setattr(
            module,
            "__loader__",
            importlib.machinery.SourceFileLoader(
                module.__name__, str(tmp_path / "shadowed-source.py")
            ),
        )
    elif fault == "loader_path_mismatch":
        monkeypatch.setattr(
            module, "__file__", str(tmp_path / "shadowed-current-supplied-cohort.py")
        )
    elif fault == "path_mismatch":
        source_digests["src/swing_trading_ai_assistant/market_regime/other.py"] = (
            source_digests.pop(_RUNTIME_SOURCES[-1])
        )
    elif fault == "composite":
        source_digests = dict(reversed(tuple(source_digests.items())))
    monkeypatch.setattr(
        manifest_module,
        "CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_SOURCE_DIGESTS_V1",
        source_digests,
    )
    args = _cli_args(tmp_path, root, _input_value(fixture, ids, digest))
    code = _cli(module)(args)
    captured = capsys.readouterr()
    assert code == 2 and captured.out == ""
    _assert_redacted(captured.err, fixture, root, Path(args[2]))


def test_regime_current_requires_existing_lock_without_mutating_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module, _ = _api()
    root = tmp_path / "owner-private-root"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    input_file = tmp_path / "owner-private-input.json"
    input_file.write_bytes(b"{}\n")
    input_file.chmod(0o600)
    before = tuple(root.iterdir())

    assert (
        _cli(module)(
            [
                "regime-current",
                "--input-file",
                str(input_file),
                "--storage-root",
                str(root),
                "--output",
                "json",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "invalid regime-current request\n"
    assert tuple(root.iterdir()) == before
    assert not (root / ".ingestion.lock").exists()


@pytest.mark.parametrize("fault", ("replacement", "loss", "cleanup"))
def test_regime_current_normalizes_root_lease_and_cleanup_runtime_failures(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    module, _ = _api()
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(root, size=1, directions=(Decimal("1"),))
    digest, _ = _schedule(root)
    args = _cli_args(tmp_path, root, _input_value(fixture, ids, digest))
    original_acquire = StorageRootLease.try_acquire_existing_identity.__func__
    original_close = StorageRootLease.close

    if fault == "replacement":

        def replace_then_acquire(
            cls: type[StorageRootLease], candidate: object, identity: tuple[int, int]
        ) -> object:
            root.rename(tmp_path / "replaced-root")
            root.mkdir(mode=0o700)
            root.chmod(0o700)
            return original_acquire(cls, candidate, identity)

        monkeypatch.setattr(
            StorageRootLease,
            "try_acquire_existing_identity",
            classmethod(replace_then_acquire),
        )
    elif fault == "loss":

        def acquire_then_lose(
            cls: type[StorageRootLease], candidate: object, identity: tuple[int, int]
        ) -> object:
            acquired = original_acquire(cls, candidate, identity)
            assert acquired.lease is not None
            acquired.lease.close()
            return acquired

        monkeypatch.setattr(
            StorageRootLease,
            "try_acquire_existing_identity",
            classmethod(acquire_then_lose),
        )
    else:

        def close_then_fail(lease: StorageRootLease) -> None:
            original_close(lease)
            raise RuntimeError

        monkeypatch.setattr(StorageRootLease, "close", close_then_fail)

    assert _cli(module)(args) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    _assert_redacted(captured.err, fixture, root, Path(args[2]))


@pytest.mark.parametrize(
    "argv",
    (
        [
            "regime-current",
            "--input-file",
            "/owner/private/input.json",
            "--storage-root",
            "/owner/private/root",
            "--output",
            "not-json",
        ],
        [
            "regime-current",
            "--input-file",
            "/owner/private/input.json",
            "--storage-root",
            "/owner/private/root",
            "--private-path",
            "/secret/raw-token",
        ],
        [
            "regime-current",
            "--input-file",
            "relative/private/input.json",
            "--storage-root",
            "/owner/private/root",
            "--output",
            "json",
        ],
    ),
)
def test_regime_current_argument_admission_redacts_raw_tokens(
    capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    module, _ = _api()
    assert _cli(module)(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "invalid regime-current request\n"
    for token in argv[1:]:
        assert token not in captured.err


def test_regime_current_admission_leaves_other_command_values_to_argparse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _ = _api()
    cli = importlib.import_module("swing_trading_ai_assistant.market_data.cli")
    observed: list[object] = []

    def safe_probe(args: object) -> int:
        observed.append(args)
        return 0

    monkeypatch.setattr(cli, "_run_probe", safe_probe)
    assert (
        _cli(module)(
            [
                "probe-upstox",
                "--segment",
                "regime-current",
                "--symbol",
                "RELIANCE",
                "--from",
                "2026-01-01",
                "--to",
                "2026-01-02",
            ]
        )
        == 0
    )
    assert len(observed) == 1


def test_evaluator_has_no_filesystem_provider_network_clock_or_storage_side_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, evaluate = _api()
    root = _private_root(tmp_path)
    fixture, ids = _archive_fixture(root, size=1, directions=(Decimal("1"),))
    digest, schedule = _schedule(root)
    admitted = _admit_input(module, _input_value(fixture, ids, digest))
    grid, continuity = _private_ready(module, fixture, ids, digest, schedule)
    archive = _RecordingArchivePort(
        _type(module, "CurrentSuppliedCohortMarketRegimeRequestV1"),
        _type(module, "ArchiveReadResultV1")("READY", grid, ()),
        admitted,
    )
    monkeypatch.setattr(
        module,
        "current_supplied_cohort_market_regime_runtime_code_identity_v1",
        lambda: "0" * 64,
    )
    resolver = _RecordingSchedulePort(
        _type(module, "ScheduleReadResultV1")("RESOLVED", continuity, ()), admitted
    )

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"forbidden evaluator capability: {args!r} {kwargs!r}")

    for target, name in (
        (Path, "read_bytes"),
        (Path, "read_text"),
        (Path, "write_bytes"),
        (Path, "write_text"),
        (Path, "open"),
        (Path, "iterdir"),
        (Path, "glob"),
        (Path, "rglob"),
        (Path, "mkdir"),
        (Path, "touch"),
        (Path, "unlink"),
        (builtins, "open"),
        (os, "open"),
        (os, "read"),
        (os, "write"),
        (os, "listdir"),
        (os, "scandir"),
        (os, "walk"),
        (glob_module, "glob"),
        (glob_module, "iglob"),
        (socket, "create_connection"),
        (socket, "socket"),
        (time_module, "time"),
        (time_module, "monotonic"),
        (time_module, "perf_counter"),
        (time_module, "process_time"),
    ):
        monkeypatch.setattr(target, name, forbidden)
    monkeypatch.setattr(CurrentCohortMarketDataServiceV1, "evaluate", forbidden)
    monkeypatch.setattr(CurrentCohortMarketDataServiceV1, "_query_member", forbidden)
    monkeypatch.setattr(ImmutableCurrentFactArchiveV1, "archive", forbidden)
    monkeypatch.setattr(ScheduleEvidenceStore, "retain", forbidden)
    report = evaluate(admitted, archive, resolver)
    _assert_observed(
        module, report, label="BROAD_ADVANCE", advances=1, declines=0, unchanged=0
    )
