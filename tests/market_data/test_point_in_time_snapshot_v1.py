"""Plan 80 bounded point-in-time research evidence snapshot tests."""

from __future__ import annotations

import base64
import hashlib
import json
import stat
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data import bharatstock_capture as capture_store
from swing_trading_ai_assistant.market_data import (
    efficient_current_nifty100_adjusted_capture as nifty_capture,
)
from swing_trading_ai_assistant.market_data import schedule_evidence
from swing_trading_ai_assistant.market_data.bharatstock import BharatStockInstrument
from swing_trading_ai_assistant.market_data.point_in_time_snapshot_v1 import (
    CONTRACT_VERSION,
    REPORT_SCHEMA,
    SNAPSHOT_SCHEMA,
    PointInTimeSnapshotRequestV1,
    PointInTimeSnapshotUnavailable,
    build_point_in_time_snapshot_v1,
    list_point_in_time_snapshot_handles_v1,
    parse_point_in_time_snapshot_request_v1,
    read_point_in_time_snapshot_v1,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)

_CUTOFF = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)
_DECISION = date(2026, 9, 21)
_DAYS = tuple(date(2026, 9, 1) + timedelta(days=offset) for offset in range(21))
_CONFLICT_DAY = date(2026, 9, 10)
_RETRIEVED = datetime(2026, 9, 22, 3, 0, 0, tzinfo=UTC)
_LATE = datetime(2026, 10, 17, 12, 0, 0, tzinfo=UTC)
_LATE_CUTOFF = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)
_CONFIGURATION = "1" * 64
_RUNTIME = "2" * 64
_SCHEMA_ID = "3" * 64
_RESPONSE = "4" * 64
_RESPONSE_TWO = "5" * 64
_PAIR_RELEASE = "composed-calendar@v1=" + "a" * 64
_NAMESPACE = "point-in-time-evidence-snapshots-v1"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _line(value: object) -> bytes:
    return _canonical(value) + b"\n"


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _line_digest(value: object) -> str:
    return hashlib.sha256(_line(value)).hexdigest()


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _members(prefix: str = "SYM") -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "exchange": "NSE",
            "isin": f"IN{prefix[0]}{index:08d}0",
            "symbol": f"{prefix}{index:03d}",
        }
        for index in range(100)
    )


def _instrument(entry: dict[str, str]) -> BharatStockInstrument:
    return BharatStockInstrument(
        isin=entry["isin"], exchange=entry["exchange"], symbol=entry["symbol"]
    )


def _csv_body(entries: tuple[dict[str, str], ...]) -> bytes:
    rows = ["Company Name,Industry,Symbol,Series,ISIN Code"]
    rows.extend(
        f"Company {entry['symbol']},Diversified,{entry['symbol']},EQ,{entry['isin']}"
        for entry in entries
    )
    return ("\n".join(rows) + "\n").encode("utf-8")


def _selection(
    members: tuple[dict[str, str], ...],
) -> tuple[str, bytes, str]:
    bodies = (
        _csv_body(members[:50]),
        _csv_body(members[50:]),
        _csv_body(members),
    )
    identity = capture_store.selection_identity_v2(
        tuple(_instrument(entry) for entry in members)
    )
    source_identity = nifty_capture._source_identity(  # pyright: ignore[reportPrivateUsage]
        bodies, _RETRIEVED
    )
    source = {
        "members": [dict(entry) for entry in members],
        "retrieved_at": _instant(_RETRIEVED),
        "selection_identity_sha256": identity,
        "source_bytes_b64": [base64.b64encode(body).decode("ascii") for body in bodies],
        "source_identity_sha256": source_identity,
        "source_urls": [
            nifty_capture.NIFTY_50_URL,
            nifty_capture.NIFTY_NEXT_50_URL,
            nifty_capture.NIFTY_100_URL,
        ],
    }
    return identity, _line(source), source_identity


def _schedule(
    days: tuple[date, ...], covered_from: date, covered_to: date
) -> schedule_evidence.ExpectedSessionSchedule:
    return schedule_evidence.ExpectedSessionSchedule(
        schema_version=schedule_evidence.SCHEDULE_SCHEMA_VERSION_V3,
        source=schedule_evidence.COMPOSED_NSE_SCHEDULE_SOURCE_V1,
        source_release=_PAIR_RELEASE,
        as_of=datetime(2026, 9, 26, 6, 0, 0, tzinfo=UTC),
        timezone="Asia/Kolkata",
        covered_from=covered_from,
        covered_to=covered_to,
        sessions=tuple(
            schedule_evidence.ScheduleSession(
                trade_date=day,
                open_at=datetime.combine(day, time(3, 45), tzinfo=UTC),
                close_at=datetime.combine(day, time(10, 0), tzinfo=UTC),
                kind="regular",
            )
            for day in days
        ),
        closures=(),
    )


def _write_schedule(
    store: Path, schedule: schedule_evidence.ExpectedSessionSchedule
) -> tuple[str, str]:
    raw = schedule_evidence.canonical_schedule_bytes(schedule)
    digest = hashlib.sha256(raw).hexdigest()
    directory = store / "evidence" / "schedule" / "calendar-schedules" / "sha256"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{digest}.json").write_bytes(raw)
    return digest, capture_store.schedule_identity_v2(schedule)


def _row(session: date, close: str) -> dict[str, object]:
    return {
        "session": session.isoformat(),
        "open": "100.0",
        "high": "101.0",
        "low": "99.0",
        "close": close,
        "volume": 1000,
        "adjusted_close": close,
        "adjustment_factor": "1.0",
    }


def _member_result(
    entry: dict[str, str],
    session: date,
    *,
    close: str,
    retrieved: datetime,
    insufficient: frozenset[str],
) -> dict[str, object]:
    if entry["symbol"] in insufficient:
        return {
            "member": dict(entry),
            "evidence_state": "INSUFFICIENT_EVIDENCE",
            "reason": "provider history unavailable",
            "history": None,
        }
    return {
        "member": dict(entry),
        "evidence_state": "OBSERVED",
        "reason": None,
        "history": {
            "instrument": dict(entry),
            "request_count": 2,
            "response_sha256s": [_RESPONSE, _RESPONSE_TWO],
            "retrieved_at": _instant(retrieved),
            "rows": [_row(session, close)],
        },
    }


def _revision(
    *,
    session: date,
    members: tuple[dict[str, str], ...],
    selection_identity: str,
    schedule_digest: str,
    schedule_identity: str,
    observed: datetime,
    cutoff: datetime,
    retrieved: datetime,
    close: str,
    insufficient: frozenset[str],
) -> tuple[str, str, dict[str, object]]:
    request: dict[str, object] = {
        "configuration_identity_sha256": _CONFIGURATION,
        "contract_version": capture_store.CONTRACT_VERSION_V3,
        "decision_cutoff": _instant(cutoff),
        "members": [dict(entry) for entry in members],
        "parent_revision_sha256": None,
        "runtime_code_identity_sha256": _RUNTIME,
        "schedule_evidence_sha256": schedule_digest,
        "schedule_identity_sha256": schedule_identity,
        "schedule_source": schedule_evidence.COMPOSED_NSE_SCHEDULE_SOURCE_V1,
        "schedule_source_release": _PAIR_RELEASE,
        "schema_identity_sha256": _SCHEMA_ID,
        "selection_identity_sha256": selection_identity,
        "sessions": [session.isoformat()],
    }
    request_identity = _canonical_digest(request)
    request["request_identity_sha256"] = request_identity
    results = tuple(
        _member_result(
            entry,
            session,
            close=close,
            retrieved=retrieved,
            insufficient=insufficient,
        )
        for entry in members
    )
    typed = tuple(capture_store._member_from_value(item) for item in results)  # pyright: ignore[reportPrivateUsage]
    value: dict[str, object] = {
        "actual_coverage_identity_sha256": capture_store._coverage_identity(typed),  # pyright: ignore[reportPrivateUsage]
        "members": list(results),
        "observed_at": _instant(observed),
        "price_basis": "BHARATSTOCK_SOURCE_REPORTED_OHLC",
        "provider_source": "bharatstock-api@v1",
        "request": request,
        "shared_failure": None,
        "source_profile": capture_store.SOURCE_PROFILE_V3,
        "volume_basis": "SOURCE_REPORTED",
    }
    identity = _line_digest(value)
    value["revision_identity_sha256"] = identity
    return identity, request_identity, value


def _seed_store(
    root: Path,
    *,
    batch: str,
    members: tuple[dict[str, str], ...],
    selection_identity: str,
    schedule: tuple[str, str],
    days: tuple[date, ...] = _DAYS,
    skip: frozenset[date] = frozenset(),
    insufficient: frozenset[str] = frozenset(),
    close: str = "100.5",
    close_overrides: dict[date, str] | None = None,
    retrieved: datetime = _RETRIEVED,
    retrieved_overrides: dict[date, datetime] | None = None,
    observed: datetime = _RETRIEVED,
    cutoff: datetime = _CUTOFF,
) -> dict[str, str]:
    store = root / "daily-capture" / batch / "session-fixture-01"
    revisions = store / "evidence" / "capture" / "bharatstock-capture-v3" / "revisions"
    revisions.mkdir(parents=True, exist_ok=True)
    digest, schedule_identity = schedule
    identities: dict[str, str] = {}
    for day in days:
        if day in skip:
            continue
        identity, request_identity, value = _revision(
            session=day,
            members=members,
            selection_identity=selection_identity,
            schedule_digest=digest,
            schedule_identity=schedule_identity,
            observed=observed,
            cutoff=cutoff,
            retrieved=(retrieved_overrides or {}).get(day, retrieved),
            close=(close_overrides or {}).get(day, close),
            insufficient=insufficient,
        )
        (revisions / f"{identity}.json").write_bytes(_line(value))
        identities[day.isoformat()] = request_identity
    return identities


def _bind_selection(
    store: Path, request_identity: str, selection: tuple[str, bytes, str]
) -> None:
    _, source_raw, source_identity = selection
    requests = store / "evidence" / "selection" / "nifty100-selection-v3" / "requests"
    sources = store / "evidence" / "selection" / "nifty100-selection-v3" / "sources"
    requests.mkdir(parents=True, exist_ok=True)
    sources.mkdir(parents=True, exist_ok=True)
    (requests / f"{request_identity}.json").write_bytes(
        _line(
            {
                "request_identity_sha256": request_identity,
                "source_identity_sha256": source_identity,
            }
        )
    )
    (sources / f"{source_identity}.json").write_bytes(source_raw)


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "store"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.outcome is LeaseOutcome.ACQUIRED and acquired.lease is not None
    acquired.lease.close()
    return root


def _request(
    decisions: tuple[date, ...] = (_DECISION,),
) -> PointInTimeSnapshotRequestV1:
    return PointInTimeSnapshotRequestV1(
        decision_sessions=decisions,
        window_sessions=21,
        decision_cutoff=_CUTOFF,
        cohort_size=100,
        permitted_use="bounded research use",
        limitation="not a decision replay or performance claim",
    )


def _seed_complete(
    root: Path,
) -> tuple[tuple[dict[str, str], ...], tuple[str, bytes, str], dict[str, str]]:
    members = _members()
    selection = _selection(members)
    store = root / "daily-capture" / "batch-one" / "session-fixture-01"
    schedule = _write_schedule(store, _schedule(_DAYS, _DAYS[0], _DAYS[-1]))
    identities = _seed_store(
        root,
        batch="batch-one",
        members=members,
        selection_identity=selection[0],
        schedule=schedule,
    )
    _bind_selection(store, identities[_DECISION.isoformat()], selection)
    return members, selection, identities


def test_complete_snapshot_is_deterministic_and_retained(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _seed_complete(root)

    report = build_point_in_time_snapshot_v1(root, _request())
    assert report["schema"] == REPORT_SCHEMA
    assert report["contract_version"] == CONTRACT_VERSION
    assert report["namespace"] == _NAMESPACE
    assert report["retained"] is True
    assert report["totals"] == {
        "cohort_members": 100,
        "cells_required": 2100,
        "cells_available": 2100,
        "members_available": 100,
        "members_required": 100,
        "coverage_bps": 10000,
    }
    assert report["revision_counts"] == {
        "files_discovered": 21,
        "admitted": 21,
        "ignored_not_v3": 0,
        "ignored_empty": 0,
        "sources_selection_mismatch": 0,
    }
    entry = report["decision_sessions"][0]
    assert entry["decision_session"] == "2026-09-21"
    assert entry["certified"] is True
    assert entry["window_start"] == "2026-09-01"
    assert entry["coverage_bps"] == 10000
    assert entry["insufficiency_counts"] == {}

    handle = report["snapshot_identity_sha256"]
    path = root / _NAMESPACE / f"{handle}.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o400
    assert build_point_in_time_snapshot_v1(root, _request())[
        "snapshot_identity_sha256"
    ] == (handle)
    assert list_point_in_time_snapshot_handles_v1(root) == (handle,)

    snapshot = read_point_in_time_snapshot_v1(root, handle)
    assert snapshot["schema"] == SNAPSHOT_SCHEMA
    assert snapshot["contract_version"] == CONTRACT_VERSION
    assert len(snapshot["sources"]) == 21
    assert snapshot["totals"]["cells_available"] == 2100
    members = snapshot["members"]
    assert len(members) == 100
    assert sum(len(member["bars"]) for member in members) == 2100
    first = members[0]
    assert first["symbol"] == "SYM000"
    assert snapshot["decision_dates"][0]["members"][0]["availability"] == "AVAILABLE"
    bar = first["bars"][0]
    assert bar["session"] == "2026-09-01"
    assert bar["close"] == "100.5"
    assert bar["source_indices"] == [0]
    assert bar["retrieved_at"].startswith("2026-09-22T03:00:00")
    assert bar["response_sha256s"] == [_RESPONSE, _RESPONSE_TWO]


def test_bar_retrieved_after_cutoff_is_typed_insufficiency(tmp_path: Path) -> None:
    root = _root(tmp_path)
    members = _members()
    selection = _selection(members)
    store = root / "daily-capture" / "batch-one" / "session-fixture-01"
    schedule = _write_schedule(store, _schedule(_DAYS, _DAYS[0], _DAYS[-1]))
    identities = _seed_store(
        root,
        batch="batch-one",
        members=members,
        selection_identity=selection[0],
        schedule=schedule,
        retrieved_overrides={_CONFLICT_DAY: _LATE},
    )
    _bind_selection(store, identities[_DECISION.isoformat()], selection)

    report = build_point_in_time_snapshot_v1(root, _request())
    assert report["totals"]["cells_available"] == 2000
    assert report["totals"]["coverage_bps"] == 0
    entry = report["decision_sessions"][0]
    assert entry["members_available"] == 0
    assert entry["insufficiency_counts"] == {"RETRIEVED_AFTER_CUTOFF": 100}

    snapshot = read_point_in_time_snapshot_v1(root, report["snapshot_identity_sha256"])
    sessions = {
        bar["session"] for member in snapshot["members"] for bar in member["bars"]
    }
    assert "2026-09-10" not in sessions
    assert len(sessions) == 20


def test_duplicate_sources_conflict_or_agree(tmp_path: Path) -> None:
    root = _root(tmp_path)
    members = _members()
    selection = _selection(members)
    schedule = _schedule(_DAYS, _DAYS[0], _DAYS[-1])
    for batch, retrieved, overrides in (
        ("batch-one", _RETRIEVED, {}),
        ("batch-two", _RETRIEVED + timedelta(seconds=1), {_CONFLICT_DAY: "100.6"}),
    ):
        store = root / "daily-capture" / batch / "session-fixture-01"
        reference = _write_schedule(store, schedule)
        identities = _seed_store(
            root,
            batch=batch,
            members=members,
            selection_identity=selection[0],
            schedule=reference,
            close_overrides=overrides,
            retrieved=retrieved,
        )
        _bind_selection(store, identities[_DECISION.isoformat()], selection)

    report = build_point_in_time_snapshot_v1(root, _request())
    assert report["revision_counts"]["admitted"] == 42
    assert report["totals"]["cells_available"] == 2000
    entry = report["decision_sessions"][0]
    assert entry["members_available"] == 0
    assert entry["insufficiency_counts"] == {"CONFLICTING_DUPLICATE_BARS": 100}

    snapshot = read_point_in_time_snapshot_v1(root, report["snapshot_identity_sha256"])
    agreeing = [
        bar
        for member in snapshot["members"]
        for bar in member["bars"]
        if bar["session"] == "2026-09-11"
    ]
    assert len(agreeing) == 100
    assert all(len(bar["source_indices"]) == 2 for bar in agreeing)
    assert all(
        bar["session"] != "2026-09-10"
        for member in snapshot["members"]
        for bar in member["bars"]
    )


def test_late_duplicate_bars_are_never_relabelled(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _seed_complete(root)
    members = _members()
    selection = _selection(members)
    late_store = root / "daily-capture" / "batch-two" / "session-fixture-01"
    schedule = _write_schedule(late_store, _schedule(_DAYS, _DAYS[0], _DAYS[-1]))
    _seed_store(
        root,
        batch="batch-two",
        members=members,
        selection_identity=selection[0],
        schedule=schedule,
        days=(_CONFLICT_DAY,),
        close_overrides={_CONFLICT_DAY: "100.9"},
        observed=_LATE,
        cutoff=_LATE_CUTOFF,
    )

    report = build_point_in_time_snapshot_v1(root, _request())
    assert report["totals"]["members_available"] == 100
    assert report["decision_sessions"][0]["insufficiency_counts"] == {}

    handle = report["snapshot_identity_sha256"]
    snapshot = read_point_in_time_snapshot_v1(root, handle)
    late_index = next(
        source["source_index"]
        for source in snapshot["sources"]
        if source["observed_at"].startswith("2026-10-17")
    )
    duplicate = [
        bar
        for member in snapshot["members"]
        for bar in member["bars"]
        if bar["session"] == "2026-09-10"
    ]
    assert len(duplicate) == 100
    assert all(late_index not in bar["source_indices"] for bar in duplicate)
    raw = (root / _NAMESPACE / f"{handle}.json").read_bytes()
    assert b"100.5" in raw
    assert b"100.9" not in raw


def test_member_not_observed_is_typed_insufficiency(tmp_path: Path) -> None:
    root = _root(tmp_path)
    members = _members()
    selection = _selection(members)
    store = root / "daily-capture" / "batch-one" / "session-fixture-01"
    schedule = _write_schedule(store, _schedule(_DAYS, _DAYS[0], _DAYS[-1]))
    identities = _seed_store(
        root,
        batch="batch-one",
        members=members,
        selection_identity=selection[0],
        schedule=schedule,
        insufficient=frozenset({"SYM000"}),
    )
    _bind_selection(store, identities[_DECISION.isoformat()], selection)

    report = build_point_in_time_snapshot_v1(root, _request())
    assert report["totals"]["coverage_bps"] == 9900
    entry = report["decision_sessions"][0]
    assert entry["members_available"] == 99
    assert entry["insufficiency_counts"] == {"MEMBER_NOT_OBSERVED": 1}

    snapshot = read_point_in_time_snapshot_v1(root, report["snapshot_identity_sha256"])
    entry_member = next(
        item
        for item in snapshot["decision_dates"][0]["members"]
        if item["symbol"] == "SYM000"
    )
    assert entry_member["availability"] == "INSUFFICIENT"
    assert entry_member["insufficiency"] == {
        "MEMBER_NOT_OBSERVED": [day.isoformat() for day in _DAYS]
    }
    member = next(item for item in snapshot["members"] if item["symbol"] == "SYM000")
    assert member["bars"] == []


def test_session_not_retained_is_typed_insufficiency(tmp_path: Path) -> None:
    root = _root(tmp_path)
    members = _members()
    selection = _selection(members)
    store = root / "daily-capture" / "batch-one" / "session-fixture-01"
    schedule = _write_schedule(store, _schedule(_DAYS, _DAYS[0], _DAYS[-1]))
    identities = _seed_store(
        root,
        batch="batch-one",
        members=members,
        selection_identity=selection[0],
        schedule=schedule,
        skip=frozenset({_CONFLICT_DAY}),
    )
    _bind_selection(store, identities[_DECISION.isoformat()], selection)

    report = build_point_in_time_snapshot_v1(root, _request())
    assert report["totals"]["cells_available"] == 2000
    entry = report["decision_sessions"][0]
    assert entry["members_available"] == 0
    assert entry["insufficiency_counts"] == {"SESSION_NOT_RETAINED": 100}


def test_uncertified_window_blocks_the_decision_date(tmp_path: Path) -> None:
    root = _root(tmp_path)
    members = _members()
    selection = _selection(members)
    store = root / "daily-capture" / "batch-one" / "session-fixture-01"
    first = _write_schedule(store, _schedule(_DAYS[:11], _DAYS[0], _DAYS[10]))
    _write_schedule(store, _schedule(_DAYS[11:], _DAYS[11], _DAYS[-1]))
    identities = _seed_store(
        root,
        batch="batch-one",
        members=members,
        selection_identity=selection[0],
        schedule=first,
    )
    _bind_selection(store, identities[_DECISION.isoformat()], selection)

    report = build_point_in_time_snapshot_v1(root, _request())
    entry = report["decision_sessions"][0]
    assert entry["certified"] is False
    assert entry["window_start"] is None
    assert entry["coverage_bps"] == 0
    assert entry["insufficiency_counts"] == {"WINDOW_NOT_CERTIFIED": 100}

    snapshot = read_point_in_time_snapshot_v1(root, report["snapshot_identity_sha256"])
    assert snapshot["decision_dates"][0]["certified"] is False
    assert snapshot["decision_dates"][0]["members"] == []
    assert snapshot["decision_dates"][0]["window_sessions"] == []


def test_tampered_revision_bytes_are_refused(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _seed_complete(root)
    revisions = (
        root
        / "daily-capture"
        / "batch-one"
        / "session-fixture-01"
        / "evidence"
        / "capture"
        / "bharatstock-capture-v3"
        / "revisions"
    )
    path = sorted(revisions.iterdir())[0]
    path.write_bytes(path.read_bytes().replace(b"100.5", b"100.6", 1))

    with pytest.raises(PointInTimeSnapshotUnavailable):
        build_point_in_time_snapshot_v1(root, _request())
    assert not (root / _NAMESPACE).exists()


def test_selection_members_mismatch_is_refused(tmp_path: Path) -> None:
    root = _root(tmp_path)
    members = _members()
    selection = _selection(members)
    mismatched = _selection(_members(prefix="ALT"))
    store = root / "daily-capture" / "batch-one" / "session-fixture-01"
    schedule = _write_schedule(store, _schedule(_DAYS, _DAYS[0], _DAYS[-1]))
    identities = _seed_store(
        root,
        batch="batch-one",
        members=members,
        selection_identity=selection[0],
        schedule=schedule,
    )
    _bind_selection(store, identities[_DECISION.isoformat()], mismatched)

    with pytest.raises(PointInTimeSnapshotUnavailable):
        build_point_in_time_snapshot_v1(root, _request())
    assert not (root / _NAMESPACE).exists()


def test_request_parsing_admits_exact_shape_and_rejects_violations() -> None:
    def raw(**overrides: object) -> bytes:
        value: dict[str, object] = {
            "cohort_size": 100,
            "decision_cutoff": "2026-09-26T12:00:00.000000Z",
            "decision_sessions": ["2026-09-21"],
            "limitation": "bounded",
            "permitted_use": "research",
            "window_sessions": 21,
        }
        value.update(overrides)
        return _canonical(value)

    parsed = parse_point_in_time_snapshot_request_v1(raw())
    assert parsed.decision_sessions == (_DECISION,)
    assert parsed.cohort_size == 100
    assert parsed.window_sessions == 21

    rejected = (
        raw(decision_cutoff="2026-09-26T12:00:00"),
        raw(decision_cutoff="2027-01-01T00:00:00+05:30"),
        raw(decision_sessions=["2026-09-21", "2026-09-21"]),
        raw(decision_sessions=["not-a-day"]),
        raw(window_sessions=20),
        raw(cohort_size=0),
        raw(unknown_field=1),
        b"",
        b"[]",
        b"{not json}",
    )
    for candidate in rejected:
        with pytest.raises(ValueError, match="invalid request"):
            parse_point_in_time_snapshot_request_v1(candidate)


def test_empty_store_and_invalid_arguments_are_bounded(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with pytest.raises(PointInTimeSnapshotUnavailable):
        build_point_in_time_snapshot_v1(root, _request())
    with pytest.raises(PointInTimeSnapshotUnavailable):
        read_point_in_time_snapshot_v1(root, "0" * 64)
    with pytest.raises(ValueError, match="invalid snapshot handle"):
        read_point_in_time_snapshot_v1(root, "not-a-digest")
    with pytest.raises(ValueError, match="invalid storage root"):
        build_point_in_time_snapshot_v1(Path("relative"), _request())
    with pytest.raises(ValueError, match="invalid storage root"):
        list_point_in_time_snapshot_handles_v1(Path("relative"))


def test_existing_snapshot_with_different_bytes_is_refused(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _seed_complete(root)
    handle = build_point_in_time_snapshot_v1(root, _request())[
        "snapshot_identity_sha256"
    ]
    path = root / _NAMESPACE / f"{handle}.json"
    path.chmod(0o600)
    path.write_bytes(b"conflicted")
    path.chmod(0o400)

    with pytest.raises(
        PointInTimeSnapshotUnavailable, match="SNAPSHOT_IDENTITY_CONFLICT"
    ):
        build_point_in_time_snapshot_v1(root, _request())
