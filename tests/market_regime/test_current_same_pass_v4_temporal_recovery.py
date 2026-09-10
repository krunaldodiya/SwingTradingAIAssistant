"""V4 official-session, preflight and interrupted-retention regressions."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from test_current_supplied_cohort_v4 import (
    _fixture_module,
    _v4,
)
from test_current_supplied_cohort_v4 import (
    test_outer_composition_retains_real_context_and_archive_files as _retained_context_fixture,
)

from swing_trading_ai_assistant.market_data.adjusted_daily.service_v3 import (
    AdjustedDailyInstrumentV3,
    adjusted_daily_request_identity_v3,
    adjusted_daily_schedule_identity_v3,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleEvidenceStore,
    ScheduleSession,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

_V4_CONTRACT = "current-supplied-cohort-market-regime@v4"


def _members(tmp_path: Path) -> tuple[Any, ...]:
    root = tmp_path / "request-fixture"
    root.mkdir(mode=0o700)
    scenario, request, _sessions = _fixture_module(
        "test_current_same_pass_daily_v4"
    )._scenario_request(root)
    try:
        return request.members
    finally:
        scenario.close()


@pytest.mark.parametrize(
    "mode,expected_relation",
    (
        ("market_hours", "prior_completed_session"),
        ("post_close", "today_completed_session"),
        ("pre_open", "prior_completed_session"),
        ("weekend_or_holiday", "prior_completed_session"),
    ),
)
def test_v4_resolves_latest_completed_official_session_by_close_time(
    tmp_path: Path, mode: str, expected_relation: str
) -> None:
    module = _v4()
    cutoff = {
        "market_hours": datetime(2026, 8, 24, 6, tzinfo=UTC),
        "post_close": datetime(2026, 8, 24, 10, tzinfo=UTC),
        "pre_open": datetime(2026, 8, 24, 3, tzinfo=UTC),
        "weekend_or_holiday": datetime(2026, 8, 23, 6, tzinfo=UTC),
    }[mode]
    covered_from = date(2026, 7, 1)
    covered_to = cutoff.date()
    days = tuple(
        covered_from + timedelta(days=offset)
        for offset in range((covered_to - covered_from).days + 1)
    )
    session_days = tuple(
        day for day in days if day.weekday() < 5 and day != date(2026, 8, 19)
    )
    schedule = ExpectedSessionSchedule(
        3,
        "nse-upstox-composed-calendar",
        "composed-calendar@v1=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        cutoff - timedelta(minutes=1),
        "Asia/Kolkata",
        covered_from,
        covered_to,
        tuple(
            ScheduleSession(
                day,
                datetime(day.year, day.month, day.day, 3, 45, tzinfo=UTC),
                datetime(day.year, day.month, day.day, 9, 45, tzinfo=UTC),
                "SPECIAL" if day == date(2026, 8, 14) else "REGULAR",
            )
            for day in session_days
        ),
        tuple(
            ScheduleClosure(day, "NSE_CLOSED")
            for day in days
            if day not in session_days
        ),
    )
    completed = tuple(item for item in schedule.sessions if item.close_at <= cutoff)[
        -21:
    ]
    raw_sessions = tuple(
        (
            module.CurrentSamePassRawSessionV1(
                position,
                item.trade_date,
                item.open_at,
                item.close_at,
                "SPECIAL" if item.kind == "SPECIAL" else "REGULAR",
            )
            for position, item in enumerate(completed)
        )
    )
    member = _members(tmp_path)[0]
    selected_at = cutoff - timedelta(days=30)
    plan21_identity = module._identity(
        {
            "contract_version": "current-supplied-cohort-market-data@v1",
            "selected_at": selected_at,
            "members": [{"isin": member.isin, "symbol": member.effective_symbol}],
        }
    )
    canonical_identity = module._identity(
        {
            "contract_version": "current-same-pass-canonical-cohort@v1",
            "cohort_selected_at": selected_at,
            "members": [member.value()],
        }
    )
    evidence_sha256 = schedule_digest(schedule)
    schedule_identity = module.current_same_pass_schedule_identity_v1(
        schedule_evidence_sha256=evidence_sha256,
        schedule_source=schedule.source,
        schedule_source_release=schedule.source_release,
        timezone=schedule.timezone,
        coverage_through=schedule.covered_to,
        sessions=raw_sessions,
    )
    plan22_schedule_identity = adjusted_daily_schedule_identity_v3(
        sessions=tuple(item.session for item in raw_sessions),
        decision_session_official_close_at=raw_sessions[-1].close_at,
        schedule_evidence_sha256=evidence_sha256,
        schedule_source=schedule.source,
        schedule_source_release=schedule.source_release,
    )
    plan22_request_identity = adjusted_daily_request_identity_v3(
        cohort_identity_sha256=canonical_identity,
        decision_cutoff=cutoff,
        schedule_identity_sha256=plan22_schedule_identity,
        members=(
            AdjustedDailyInstrumentV3(
                **{
                    field.name: getattr(member, field.name)
                    for field in fields(AdjustedDailyInstrumentV3)
                }
            ),
        ),
    )
    request_core = {
        "contract_version": _V4_CONTRACT,
        "decision_cutoff": cutoff,
        "cohort_selected_at": selected_at,
        "members": (member,),
        "schedule_evidence_sha256": evidence_sha256,
        "schedule_identity_sha256": schedule_identity,
        "plan22_schedule_identity_sha256": plan22_schedule_identity,
        "schedule_source": schedule.source,
        "schedule_source_release": schedule.source_release,
        "include_partial_current_session": False,
        "plan21_cohort_identity_sha256": plan21_identity,
        "canonical_cohort_identity_sha256": canonical_identity,
        "plan22_request_identity_sha256": plan22_request_identity,
    }
    request = module.CurrentSamePassMarketRegimeRequestV4(
        **request_core,
        request_identity_sha256=module._identity_from_values(
            module.CurrentSamePassMarketRegimeRequestV4,
            request_core,
            "request_identity_sha256",
        ),
    )
    resolved = module.resolve_latest_completed_sessions_v1(request, schedule)
    expected_decision = (
        date(2026, 8, 24)
        if expected_relation == "today_completed_session"
        else date(2026, 8, 21)
    )
    assert resolved == raw_sessions
    assert resolved[-1].session == expected_decision


@pytest.mark.parametrize(
    ("outcome", "expected_reason"),
    (
        ("missing", "SCHEDULE_EVIDENCE_MISSING"),
        ("stale", "SCHEDULE_EVIDENCE_STALE"),
        ("conflicted", "SCHEDULE_EVIDENCE_CONFLICTED"),
        ("kind", "SCHEDULE_CONTINUITY_UNPROVEN"),
        ("schema", "SCHEDULE_CONTINUITY_UNPROVEN"),
        ("continuity", "SCHEDULE_CONTINUITY_UNPROVEN"),
        ("latest", "LATEST_COMPLETED_SESSION_UNRESOLVED"),
    ),
)
def test_public_composition_returns_preflight_no_trade_before_all_effects(
    tmp_path: Path, outcome: str, expected_reason: str
) -> None:
    """Schedule failures return only a typed no-trade result before effects."""
    module = _v4()
    members = _members(tmp_path)[:1]
    cutoff = datetime(2026, 8, 24, 10, tzinfo=UTC)
    selected_at = datetime(2026, 8, 1, 1, tzinfo=UTC)
    sessions = tuple(
        ScheduleSession(
            date(2026, 8, day),
            datetime(2026, 8, day, 3, 45, tzinfo=UTC),
            datetime(2026, 8, day, 9, tzinfo=UTC),
            "REGULAR",
        )
        for day in range(1, 25)
    )
    schedule = ExpectedSessionSchedule(
        3,
        "nse-upstox-composed-calendar",
        "composed-calendar@v1=cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        cutoff,
        "Asia/Kolkata",
        sessions[0].trade_date,
        sessions[-1].trade_date,
        sessions,
    )
    if outcome == "kind":
        schedule = ExpectedSessionSchedule(
            3,
            schedule.source,
            schedule.source_release,
            schedule.as_of,
            schedule.timezone,
            schedule.covered_from,
            schedule.covered_to,
            (
                ScheduleSession(
                    sessions[0].trade_date,
                    sessions[0].open_at,
                    sessions[0].close_at,
                    "UNKNOWN",
                ),
                *sessions[1:],
            ),
        )
    elif outcome == "schema":
        schedule = ExpectedSessionSchedule(
            2,
            schedule.source,
            schedule.source_release,
            schedule.as_of,
            schedule.timezone,
            schedule.covered_from,
            schedule.covered_to,
            schedule.sessions,
        )
    elif outcome == "stale":
        schedule = ExpectedSessionSchedule(
            3,
            schedule.source,
            schedule.source_release,
            cutoff + timedelta(minutes=1),
            schedule.timezone,
            schedule.covered_from,
            schedule.covered_to,
            schedule.sessions,
        )
    elif outcome == "continuity":
        schedule = ExpectedSessionSchedule(
            3,
            schedule.source,
            schedule.source_release,
            schedule.as_of,
            schedule.timezone,
            schedule.covered_from - timedelta(days=1),
            schedule.covered_to,
            schedule.sessions,
        )
    elif outcome == "latest":
        schedule = ExpectedSessionSchedule(
            3,
            schedule.source,
            schedule.source_release,
            schedule.as_of,
            schedule.timezone,
            schedule.covered_from,
            schedule.covered_to,
            schedule.sessions[:20],
            tuple(
                ScheduleClosure(date(2026, 8, day), "NSE_CLOSED")
                for day in range(21, 25)
            ),
        )
    root = tmp_path / outcome
    root.mkdir()
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    lease = acquired.lease
    store = ScheduleEvidenceStore(root, lease)
    try:
        retained = store.retain(schedule)
        assert retained.digest is not None
        schedule_digest = "0" * 64 if outcome == "missing" else retained.digest
        request_release = schedule.source_release
        plan21_identity = module._identity(
            {
                "contract_version": "current-supplied-cohort-market-data@v1",
                "selected_at": selected_at,
                "members": [
                    {"isin": members[0].isin, "symbol": members[0].effective_symbol}
                ],
            }
        )
        canonical_identity = module._identity(
            {
                "contract_version": "current-same-pass-canonical-cohort@v1",
                "cohort_selected_at": selected_at,
                "members": [members[0].value()],
            }
        )
        schedule_identity = "1" * 64
        plan22_schedule_identity = "2" * 64
        plan22_identity = adjusted_daily_request_identity_v3(
            cohort_identity_sha256=canonical_identity,
            decision_cutoff=cutoff,
            schedule_identity_sha256=plan22_schedule_identity,
            members=(
                AdjustedDailyInstrumentV3(
                    **{
                        field.name: getattr(members[0], field.name)
                        for field in fields(AdjustedDailyInstrumentV3)
                    }
                ),
            ),
        )
        request_core = {
            "contract_version": _V4_CONTRACT,
            "decision_cutoff": cutoff,
            "cohort_selected_at": selected_at,
            "members": members,
            "schedule_evidence_sha256": schedule_digest,
            "schedule_identity_sha256": schedule_identity,
            "plan22_schedule_identity_sha256": plan22_schedule_identity,
            "schedule_source": "nse-upstox-composed-calendar",
            "schedule_source_release": request_release,
            "include_partial_current_session": False,
            "plan21_cohort_identity_sha256": plan21_identity,
            "canonical_cohort_identity_sha256": canonical_identity,
            "plan22_request_identity_sha256": plan22_identity,
        }
        request = module.CurrentSamePassMarketRegimeRequestV4(
            **request_core,
            request_identity_sha256=module._identity_from_values(
                module.CurrentSamePassMarketRegimeRequestV4,
                request_core,
                "request_identity_sha256",
            ),
        )

        @dataclass
        class Effects:
            calls: int = 0

            def __getattr__(self, _name: str) -> Any:
                self.calls += 1
                raise AssertionError("schedule preflight must precede all effects")

        raw, screen, provider, archive = (Effects(), Effects(), Effects(), Effects())
        result = (
            module.acquire_build_and_retain_current_supplied_cohort_market_regime_v4(
                request,
                store,
                raw,
                screen,
                provider,
                archive,
                lease,
                clock=type(
                    "Clock", (), {"now": lambda self: cutoff - timedelta(minutes=5)}
                )(),
            )
        )
        assert type(result) is module.CurrentSamePassPreflightFailureV1
        assert result.evidence_state == "INSUFFICIENT_EVIDENCE"
        assert result.request_identity_sha256 == request.request_identity_sha256
        assert result.canonical_cohort_identity_sha256 == canonical_identity
        assert result.reasons == (expected_reason,)
        assert (
            result.consumer_disposition == "INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED"
        )
        assert result.failure_identity_sha256 == module._identity(
            {
                "contract_version": result.contract_version,
                "evidence_state": result.evidence_state,
                "request_identity_sha256": result.request_identity_sha256,
                "canonical_cohort_identity_sha256": result.canonical_cohort_identity_sha256,
                "reasons": result.reasons,
                "consumer_disposition": result.consumer_disposition,
            }
        )
        assert all(effect.calls == 0 for effect in (raw, screen, provider, archive))
    finally:
        lease.close()


@pytest.mark.parametrize("cleanup_failure", ("unlink", "fsync"))
def test_v4_late_marker_guard_survives_cleanup_failure_and_blocks_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_failure: str
) -> None:
    module = _v4()
    captured: dict[str, Any] = {}
    _retained_context_fixture(
        tmp_path, monkeypatch, exercise_archive_contracts=False, capture=captured
    )
    candidate = captured["candidate"]
    request = candidate.context_object.request
    root = tmp_path / f"late-context-{cleanup_failure}"
    root.mkdir(mode=448)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None

    @dataclass
    class Clock:
        values: list[datetime]

        def now(self) -> datetime:
            return self.values.pop(0) if len(self.values) > 1 else self.values[0]

    real_unlink = module.os.unlink
    real_fsync = module.os.fsync
    cleanup_unlinked = False

    def unlink(name: str, *, dir_fd: int) -> None:
        nonlocal cleanup_unlinked
        if name.startswith("completion-"):
            if cleanup_failure == "unlink":
                raise OSError("injected completion unlink failure")
            cleanup_unlinked = True
        real_unlink(name, dir_fd=dir_fd)

    def fsync(descriptor: int) -> None:
        if cleanup_failure == "fsync" and cleanup_unlinked:
            raise OSError("injected cleanup fsync failure")
        real_fsync(descriptor)

    first_clock = Clock(
        [
            request.decision_cutoff - timedelta(seconds=30),
            request.decision_cutoff - timedelta(seconds=30),
            request.decision_cutoff + timedelta(microseconds=1),
        ]
    )
    try:
        with monkeypatch.context() as fault:
            fault.setattr(module.os, "unlink", unlink)
            fault.setattr(module.os, "fsync", fsync)
            first = module._FileCurrentSamePassMarketContextArchiveV1(
                root, clock=first_clock
            ).archive_exact(
                request, candidate, acquired.lease, trusted_clock=first_clock
            )
        assert type(first) is module.CurrentSamePassArchiveFailureV1
        stem = candidate.context_object.context_identity_sha256
        archive_root = root / ".current-same-pass-market-regime-v4"
        assert (archive_root / f"pending-{stem}.json").is_file()
        assert not (archive_root / f"admissible-{stem}.json").exists()
        retry_clock = Clock([request.decision_cutoff + timedelta(seconds=1)])
        retry = module._FileCurrentSamePassMarketContextArchiveV1(
            root, clock=retry_clock
        ).archive_exact(request, candidate, acquired.lease, trusted_clock=retry_clock)
        assert type(retry) is module.CurrentSamePassArchiveFailureV1
    finally:
        acquired.lease.close()


def test_v4_crash_after_admissibility_guard_retries_with_original_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _v4()
    captured: dict[str, Any] = {}
    _retained_context_fixture(
        tmp_path, monkeypatch, exercise_archive_contracts=False, capture=captured
    )
    candidate = captured["candidate"]
    request = candidate.context_object.request
    root = tmp_path / "crashed-context"
    root.mkdir(mode=448)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None

    @dataclass
    class Clock:
        values: list[datetime]

        def now(self) -> datetime:
            return self.values.pop(0) if len(self.values) > 1 else self.values[0]

    clock = Clock(
        [
            request.decision_cutoff - timedelta(seconds=30),
            request.decision_cutoff - timedelta(seconds=30),
            request.decision_cutoff - timedelta(seconds=1),
            request.decision_cutoff,
        ]
    )
    try:
        with monkeypatch.context() as crash:
            crash.setattr(
                module,
                "_parse_context_archive_records",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("injected post-guard crash")
                ),
            )
            interrupted = module._FileCurrentSamePassMarketContextArchiveV1(
                root, clock=clock
            ).archive_exact(request, candidate, acquired.lease, trusted_clock=clock)
        assert type(interrupted) is module.CurrentSamePassArchiveFailureV1
        retry_clock = Clock([request.decision_cutoff])
        retry = module._FileCurrentSamePassMarketContextArchiveV1(
            root, clock=retry_clock
        ).archive_exact(request, candidate, acquired.lease, trusted_clock=retry_clock)
        assert type(retry) is module.RetainedCurrentSamePassMarketContextV4
        assert retry.archive_known_at == request.decision_cutoff
    finally:
        acquired.lease.close()
