"""Behavioral V4 parity for the retained current same-pass Market Regime context.

The fixture uses retained raw evidence and direct BharatStock history objects only.
It deliberately exercises the public acquisition path, not Yahoo or frame adapters.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib import import_module, util
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from swing_trading_ai_assistant.market_data import (
    current_same_pass_daily_v4 as raw_daily,
)
from swing_trading_ai_assistant.market_data.adjusted_daily.service_v3 import (
    AdjustedDailyInstrumentV3,
    adjusted_daily_request_identity_v3,
)
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockDailyPrice,
    BharatStockError,
    BharatStockHistory,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

_MODULE = "swing_trading_ai_assistant.market_regime.current_supplied_cohort_v4"
_CUTOFF = datetime(2026, 8, 4, 12, tzinfo=UTC)


def _v4() -> Any:
    """Load the sole V4 authority at test execution time."""
    return import_module(_MODULE)


def _bharatstock_fixture() -> Any:
    """Load the compact V4 retained-evidence fixture without package imports."""
    name = "current_supplied_cohort_v4_bharatstock_fixture"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = Path(__file__).with_name("test_bharatstock_regime_v4.py")
    spec = util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _fixture_module(name: str) -> Any:
    """Load a sibling V4 fixture by filename for downstream parity tests."""
    path = Path(__file__).parents[1] / "market_data" / f"{name}.py"
    spec = util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class _Clock:
    values: list[datetime]

    def now(self) -> datetime:
        return self.values.pop(0) if len(self.values) > 1 else self.values[0]


def _composition_clock(pre_cutoff_count: int) -> _Clock:
    return _Clock(
        [_CUTOFF - timedelta(minutes=5)]
        + [_CUTOFF - timedelta(minutes=2)] * pre_cutoff_count
        + [_CUTOFF - timedelta(seconds=30)]
        + [_CUTOFF] * 128
    )


def _rehashed_bar(bar: Any, **changes: object) -> Any:
    values = {
        field.name: getattr(bar, field.name)
        for field in fields(type(bar))
        if field.name != "raw_bar_identity_sha256"
    }
    values.update(changes)
    return type(bar)(
        **values,
        raw_bar_identity_sha256=raw_daily._identity_from_values(
            type(bar), values, "raw_bar_identity_sha256"
        ),
    )


def _directional_evidence(
    fixture: Any,
    directions: tuple[str, ...],
) -> Any:
    class DirectionalEvidence(fixture._TemporaryRetainedEvidence):
        def query_and_project_under_lease(self, *args: Any, **kwargs: Any) -> Any:
            source_rows, bars = super().query_and_project_under_lease(*args, **kwargs)
            request = args[0]
            direction_by_isin = {
                member.isin: direction
                for member, direction in zip(request.members, directions, strict=True)
            }
            sessions = args[2]
            first_session, last_session = sessions[0].session, sessions[-1].session
            projected = []
            for bar in bars:
                direction = direction_by_isin[bar.isin]
                close = (
                    Decimal("101")
                    if bar.session == last_session and direction == "ADVANCE"
                    else Decimal("99")
                    if bar.session == last_session and direction == "DECLINE"
                    else Decimal("100")
                )
                if bar.session == first_session:
                    close = Decimal("100")
                projected.append(
                    _rehashed_bar(
                        bar,
                        open=Decimal("100"),
                        high=Decimal("102"),
                        low=Decimal("98"),
                        close=close,
                    )
                )
            return source_rows, tuple(projected)

        def partial_current_session_under_lease(
            self,
            request: Any,
            mappings: tuple[Any, ...],
            active_session: Any,
            _lease: Any,
        ) -> Any:
            as_of = request.decision_cutoff.replace(
                second=0, microsecond=0
            ) - timedelta(minutes=1)
            rows = []
            for mapping in mappings:
                receipt = raw_daily._hash(
                    {
                        "mapping": mapping.raw_mapping_projection_identity_sha256,
                        "official_active_session": (
                            active_session.partial_official_session_identity_sha256
                        ),
                        "session": active_session.session,
                        "as_of": as_of,
                        "query_known_at": request.decision_cutoff,
                    }
                )
                values = {
                    "isin": mapping.member.isin,
                    "session": active_session.session,
                    "as_of": as_of,
                    "price": Decimal("100"),
                    "cumulative_volume": 1_000,
                    "provider": "UPSTOX",
                    "price_basis": "RAW",
                    "source_receipt_identity_sha256": receipt,
                    "known_at": request.decision_cutoff,
                }
                rows.append(
                    raw_daily.PartialCurrentSessionRowV1(
                        **values,
                        partial_current_session_row_identity_sha256=(
                            raw_daily._identity_from_values(
                                raw_daily.PartialCurrentSessionRowV1,
                                values,
                                "partial_current_session_row_identity_sha256",
                            )
                        ),
                    )
                )
            values = {
                "label": "PARTIAL_CURRENT_SESSION",
                "state": "OBSERVED",
                "session": active_session.session,
                "as_of": as_of,
                "known_at": request.decision_cutoff,
                "rows": tuple(rows),
                "reasons": (),
            }
            return raw_daily.PartialCurrentSessionSnapshotV1(
                **values,
                partial_snapshot_identity_sha256=raw_daily._identity_from_values(
                    raw_daily.PartialCurrentSessionSnapshotV1,
                    values,
                    "partial_snapshot_identity_sha256",
                ),
            )

    return DirectionalEvidence()


def _with_partial_request(request: Any) -> Any:
    active_date = request.decision_cutoff.astimezone(ZoneInfo("Asia/Kolkata")).date()
    members = tuple(
        replace(member, valid_through=active_date) for member in request.members
    )
    canonical_members = tuple(
        sorted(
            members,
            key=lambda item: (item.isin, item.exchange, item.effective_symbol),
        )
    )
    plan21_identity = raw_daily._hash(
        {
            "contract_version": "current-supplied-cohort-market-data@v1",
            "selected_at": request.cohort_selected_at,
            "members": [
                {"isin": member.isin, "symbol": member.effective_symbol}
                for member in canonical_members
            ],
        }
    )
    canonical_identity = raw_daily._hash(
        {
            "contract_version": "current-same-pass-canonical-cohort@v1",
            "cohort_selected_at": request.cohort_selected_at,
            "members": [member.value() for member in canonical_members],
        }
    )
    values = {
        field.name: getattr(request, field.name)
        for field in fields(type(request))
        if field.name
        not in {
            "members",
            "include_partial_current_session",
            "plan21_cohort_identity_sha256",
            "canonical_cohort_identity_sha256",
            "plan22_request_identity_sha256",
            "request_identity_sha256",
        }
    }
    values.update(
        members=members,
        include_partial_current_session=True,
        plan21_cohort_identity_sha256=plan21_identity,
        canonical_cohort_identity_sha256=canonical_identity,
        plan22_request_identity_sha256=adjusted_daily_request_identity_v3(
            cohort_identity_sha256=canonical_identity,
            decision_cutoff=request.decision_cutoff,
            schedule_identity_sha256=request.plan22_schedule_identity_sha256,
            members=tuple(
                AdjustedDailyInstrumentV3(
                    **{
                        field.name: getattr(member, field.name)
                        for field in fields(AdjustedDailyInstrumentV3)
                    }
                )
                for member in members
            ),
        ),
    )
    values["request_identity_sha256"] = raw_daily._hash(values)
    return raw_daily.CurrentSamePassMarketRegimeRequestV4(**values)


def _history(
    instrument: object,
    sessions: tuple[Any, ...],
    direction: str,
) -> BharatStockHistory:
    rows = []
    for position, item in enumerate(sessions):
        close = (
            Decimal("101")
            if position == len(sessions) - 1 and direction == "ADVANCE"
            else Decimal("99")
            if position == len(sessions) - 1 and direction == "DECLINE"
            else Decimal("100")
        )
        rows.append(
            BharatStockDailyPrice(
                item.session,
                Decimal("100"),
                Decimal("102"),
                Decimal("98"),
                close,
                1_000,
                close,
                Decimal("1"),
            )
        )
    return BharatStockHistory(
        instrument,
        tuple(rows),
        _CUTOFF - timedelta(minutes=1),
        ("a" * 64, "b" * 64),
        2,
    )


def _archive_paths(root: Path, identity: str) -> tuple[Path, Path, Path]:
    archive_root = root / ".current-same-pass-market-regime-v4"
    return (
        archive_root / f"context-{identity}.json",
        archive_root / f"retained-{identity}.json",
        archive_root / f"completion-{identity}.json",
    )


def test_outer_composition_retains_real_context_and_archive_files(  # noqa: C901
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_evidence_factory: Callable[[Any], object] | None = None,
    exercise_post_return_adversaries: bool = False,
    trusted_clock_pre_cutoff_count: int = 5,
    plan22_start_offset: timedelta | None = None,
    exercise_archive_contracts: bool = True,
    raw_directions: tuple[str, ...] | None = None,
    adjusted_directions: tuple[str, ...] | None = None,
    expected_state: str | None = None,
    expected_breadth: tuple[str, int, int, int] | None = None,
    expected_plan22_calls: int = 1,
    expected_effects: tuple[str, ...] = ("raw-mapping", "screen", "plan22"),
    screen_retain: bool = True,
    expect_archive_failure: bool = False,
    capture: dict[str, Any] | None = None,
    include_partial: bool = False,
) -> None:
    """Exercise V4's raw-first, screen, direct-provider, and archive chain.

    The extended fixture signature remains available to Industry, Packet, Market
    Structure, and Price Action parity tests, including the V4 active-session
    partial projection.
    """
    del monkeypatch
    tmp_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    fixture = _bharatstock_fixture()
    module = _v4()
    cohort_size = len(raw_directions) if raw_directions is not None else 1
    if adjusted_directions is not None and len(adjusted_directions) != cohort_size:
        raise ValueError("direction fixture size mismatch")
    directions = raw_directions or ("UNCHANGED",) * cohort_size
    adjusted = adjusted_directions or directions
    screen = fixture._screen_fixture()
    scenario = screen._scenario(tmp_path, count=cohort_size, retain=screen_retain)
    try:
        request, sessions = fixture._request(scenario, screen)
        if include_partial:
            request = _with_partial_request(request)
        effects: list[str] = []

        class Provider:
            calls = 0

            def history(
                self, instrument: object, _first: object, _last: object
            ) -> object:
                self.calls += 1
                if self.calls == 1:
                    effects.append("plan22")
                if provider_failure is not None:
                    raise BharatStockError(provider_failure, member_local=False)
                position = next(
                    index
                    for index, member in enumerate(request.members)
                    if member.isin == instrument.isin
                )
                return _history(instrument, sessions, adjusted[position])

        class RecordingRaw:
            def __init__(self, delegate: Any) -> None:
                self.delegate = delegate

            def acquire_exact(self, *args: object, **kwargs: object) -> object:
                effects.append("raw-mapping")
                return self.delegate.acquire_exact(*args, **kwargs)

        class RecordingResolver:
            def __init__(self, delegate: Any) -> None:
                self.delegate = delegate

            def resolve_exact(self, *args: object, **kwargs: object) -> object:
                effects.append("screen")
                return self.delegate.resolve_exact(*args, **kwargs)

        provider_failure: str | None = None
        evidence = (
            raw_evidence_factory(_fixture_module("test_current_same_pass_daily_v4"))
            if raw_evidence_factory is not None
            else _directional_evidence(fixture, directions)
        )
        raw = raw_daily.UpstoxCurrentSamePassRawDailyV1(
            scenario.root,
            scenario.root / "schedule.json",
            clock=_composition_clock(trusted_clock_pre_cutoff_count),
            evidence_port=evidence,
        )
        resolver = fixture.CurrentSuppliedCohortCorporateActionScreenResolverV1(
            scenario.schedule_store,
            fixture.UpstoxCorporateActionScreenProviderV1(scenario.store),
        )
        inner_archive = module.FileCurrentSamePassMarketContextArchiveV1(
            scenario.root, clock=_composition_clock(trusted_clock_pre_cutoff_count)
        )

        class CapturingArchive:
            candidate: Any | None = None

            def archive_exact(
                self, archive_request: Any, candidate: Any, lease: Any, **kwargs: Any
            ) -> object:
                self.candidate = candidate
                return inner_archive.archive_exact(
                    archive_request, candidate, lease, **kwargs
                )

        archive = CapturingArchive()
        provider = Provider()
        if plan22_start_offset is None:
            deadline_clock: Any = None
        else:

            class DeadlineClock:
                first = True

                def now(self) -> datetime:
                    if self.first:
                        self.first = False
                        return _CUTOFF - timedelta(minutes=5)
                    if "screen" in effects:
                        return _CUTOFF - timedelta(seconds=30) + plan22_start_offset
                    return _CUTOFF - timedelta(minutes=2)

            deadline_clock = DeadlineClock()

        def acquire() -> object:
            clock = deadline_clock or _composition_clock(trusted_clock_pre_cutoff_count)
            return module.acquire_build_and_retain_current_supplied_cohort_market_regime_v4(
                request,
                scenario.schedule_store,
                RecordingRaw(raw),
                RecordingResolver(resolver),
                provider,
                archive,
                scenario.lease,
                clock=clock,
            )

        result = acquire()
        if expect_archive_failure:
            assert type(result) is module.CurrentSamePassArchiveFailureV1
            assert provider.calls == expected_plan22_calls * cohort_size
            assert tuple(effects) == expected_effects
            if plan22_start_offset is not None:
                assert archive.candidate is None
            else:
                assert archive.candidate is not None
            if capture is not None:
                capture.update(
                    candidate=archive.candidate,
                    retained=result,
                    request=request,
                    provider=provider,
                )
            return

        assert type(result) is module.RetainedCurrentSamePassMarketContextV4
        assert module.validate_retained_current_same_pass_market_context_v4(result)
        assert archive.candidate is not None
        assert provider.calls == expected_plan22_calls * cohort_size
        assert tuple(effects) == expected_effects
        assert result.market_regime_report.evidence_state == (
            expected_state
            or (
                "OBSERVED"
                if screen_retain and raw_evidence_factory is None
                else "INSUFFICIENT_EVIDENCE"
            )
        )
        if expected_breadth is not None:
            regime, advances, declines, unchanged = expected_breadth
            assert (
                result.market_regime_report.regime,
                result.market_regime_report.advances,
                result.market_regime_report.declines,
                result.market_regime_report.unchanged,
            ) == (regime, advances, declines, unchanged)
        if capture is not None:
            capture.update(
                candidate=archive.candidate,
                retained=result,
                request=request,
                provider=provider,
                root=scenario.root,
            )
        context_path, receipt_path, marker_path = _archive_paths(
            scenario.root, result.context_identity_sha256
        )
        assert all(path.is_file() for path in (context_path, receipt_path, marker_path))
        context_bytes = context_path.read_bytes()
        assert b"bharatstock" in context_bytes
        assert b"YFINANCE" not in context_bytes

        if exercise_post_return_adversaries:
            original = context_path.read_bytes()

            class MutatingArchive:
                def archive_exact(
                    self,
                    archive_request: Any,
                    candidate: Any,
                    lease: Any,
                    **kwargs: Any,
                ) -> object:
                    value = module.FileCurrentSamePassMarketContextArchiveV1(
                        scenario.root, clock=_composition_clock(256)
                    ).archive_exact(archive_request, candidate, lease, **kwargs)
                    context_path.write_bytes(original + b" ")
                    return value

            with pytest.raises(ValueError, match="unsealed same-pass context"):
                module.acquire_build_and_retain_current_supplied_cohort_market_regime_v4(
                    request,
                    scenario.schedule_store,
                    raw,
                    resolver,
                    provider,
                    MutatingArchive(),
                    scenario.lease,
                    clock=_composition_clock(256),
                )
            context_path.write_bytes(original)

        if not exercise_archive_contracts:
            return
        retried = acquire()
        assert type(retried) is module.RetainedCurrentSamePassMarketContextV4
        assert (
            retried.retained_context_identity_sha256
            == result.retained_context_identity_sha256
        )
        assert retried.archive_known_at == result.archive_known_at

        archive_root = tmp_path / "corrupted-retry"
        archive_root.mkdir(mode=0o700)
        acquired = StorageRootLease.try_acquire(archive_root)
        assert acquired.lease is not None
        try:
            archive_clock = _Clock([_CUTOFF - timedelta(seconds=30)] + [_CUTOFF] * 128)
            fresh_archive = module.FileCurrentSamePassMarketContextArchiveV1(
                archive_root, clock=archive_clock
            )
            seeded = fresh_archive.archive_exact(
                request,
                archive.candidate,
                acquired.lease,
                trusted_clock=archive_clock,
            )
            assert type(seeded) is module.RetainedCurrentSamePassMarketContextV4
            corrupted_context, _corrupted_receipt, _corrupted_marker = _archive_paths(
                archive_root, result.context_identity_sha256
            )
            corrupted_context.write_bytes(corrupted_context.read_bytes() + b" ")
            corrupted = fresh_archive.archive_exact(
                request,
                archive.candidate,
                acquired.lease,
                trusted_clock=archive_clock,
            )
            assert type(corrupted) is module.CurrentSamePassArchiveFailureV1
        finally:
            acquired.lease.close()
    finally:
        scenario.close()


@pytest.mark.parametrize(
    ("raw_direction", "adjusted_direction", "state"),
    (
        ("ADVANCE", "ADVANCE", "OBSERVED"),
        ("DECLINE", "DECLINE", "OBSERVED"),
        ("UNCHANGED", "UNCHANGED", "OBSERVED"),
        ("ADVANCE", "DECLINE", "INSUFFICIENT_EVIDENCE"),
        ("DECLINE", "UNCHANGED", "INSUFFICIENT_EVIDENCE"),
    ),
)
def test_v4_requires_matching_raw_and_bharatstock_adjusted_directions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_direction: str,
    adjusted_direction: str,
    state: str,
) -> None:
    test_outer_composition_retains_real_context_and_archive_files(
        tmp_path,
        monkeypatch,
        exercise_archive_contracts=False,
        raw_directions=(raw_direction,),
        adjusted_directions=(adjusted_direction,),
        expected_state=state,
    )


@pytest.mark.parametrize(
    ("cohort_size", "advances", "declines", "expected"),
    (
        (5, 3, 0, "BROAD_ADVANCE"),
        (5, 0, 3, "BROAD_DECLINE"),
        (5, 2, 2, "MIXED_PARTICIPATION"),
        (50, 30, 0, "BROAD_ADVANCE"),
        (50, 0, 30, "BROAD_DECLINE"),
    ),
)
def test_v4_keeps_inclusive_sixty_percent_breadth_for_full_cohort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cohort_size: int,
    advances: int,
    declines: int,
    expected: str,
) -> None:
    directions = (
        ("ADVANCE",) * advances
        + ("DECLINE",) * declines
        + ("UNCHANGED",) * (cohort_size - advances - declines)
    )
    test_outer_composition_retains_real_context_and_archive_files(
        tmp_path,
        monkeypatch,
        exercise_archive_contracts=False,
        raw_directions=directions,
        adjusted_directions=directions,
        expected_state="OBSERVED",
        expected_breadth=(
            expected,
            advances,
            declines,
            cohort_size - advances - declines,
        ),
    )


def test_v4_retains_exact_active_session_partial_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    test_outer_composition_retains_real_context_and_archive_files(
        tmp_path,
        monkeypatch,
        include_partial=True,
        exercise_archive_contracts=False,
        capture=captured,
    )
    context = captured["candidate"].context_object
    partial = context.raw_result.partial_current_session
    assert partial.state == "OBSERVED"
    assert partial.rows is not None
    assert tuple(row.isin for row in partial.rows) == tuple(
        member.isin for member in context.request.members
    )
    assert raw_daily.current_same_pass_raw_daily_result_is_exact_valid_v4(
        context.raw_result, context.request
    )


def test_v4_preserves_supplied_member_order_but_rejects_identity_bridge_drift(
    tmp_path: Path,
    *,
    capture: dict[str, Any] | None = None,
) -> None:
    tmp_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    fixture = _bharatstock_fixture()
    screen = fixture._screen_fixture()
    scenario = screen._scenario(tmp_path, count=2)
    try:
        request, _sessions = fixture._request(scenario, screen)
        members = tuple(reversed(request.members))
        instruments = tuple(
            AdjustedDailyInstrumentV3(
                **{
                    field.name: getattr(member, field.name)
                    for field in fields(AdjustedDailyInstrumentV3)
                }
            )
            for member in members
        )
        values = {
            field.name: getattr(request, field.name)
            for field in fields(type(request))
            if field.name
            not in {
                "members",
                "plan22_request_identity_sha256",
                "request_identity_sha256",
            }
        }
        values["members"] = members
        values["plan22_request_identity_sha256"] = adjusted_daily_request_identity_v3(
            cohort_identity_sha256=request.canonical_cohort_identity_sha256,
            decision_cutoff=request.decision_cutoff,
            schedule_identity_sha256=request.plan22_schedule_identity_sha256,
            members=instruments,
        )
        values["request_identity_sha256"] = raw_daily._hash(values)
        reordered = raw_daily.CurrentSamePassMarketRegimeRequestV4(**values)
        assert reordered.members == members
        assert (
            reordered.canonical_cohort_identity_sha256
            == request.canonical_cohort_identity_sha256
        )
        assert (
            reordered.plan22_request_identity_sha256
            != request.plan22_request_identity_sha256
        )
        original_factory = fixture._request

        def reordered_factory(fresh_scenario: Any, fresh_screen: Any) -> Any:
            _, fresh_sessions = original_factory(fresh_scenario, fresh_screen)
            return reordered, fresh_sessions

        captured: dict[str, Any] = {}
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(fixture, "_request", reordered_factory)
            test_outer_composition_retains_real_context_and_archive_files(
                tmp_path / "reordered",
                patch,
                raw_directions=("UNCHANGED", "UNCHANGED"),
                exercise_archive_contracts=False,
                capture=captured,
            )
        retained_request = captured["candidate"].context_object.request
        assert retained_request.members == members
        assert (
            retained_request.request_identity_sha256
            == reordered.request_identity_sha256
        )
        if capture is not None:
            capture.update(captured)
        values["plan22_request_identity_sha256"] = "0" * 64
        values["request_identity_sha256"] = raw_daily._hash(values)
        with pytest.raises(ValueError, match="adjusted-daily identity bridge mismatch"):
            raw_daily.CurrentSamePassMarketRegimeRequestV4(**values)
    finally:
        scenario.close()


def test_v4_raw_mapping_rejection_and_screen_insufficiency_skip_bharatstock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _bharatstock_fixture()

    def missing_mapping(_raw_module: Any) -> object:
        class MissingMappingEvidence(fixture._TemporaryRetainedEvidence):
            def mappings_under_lease(self, *_: object) -> object:
                return "RAW_MAPPING_MISSING"

        return MissingMappingEvidence()

    test_outer_composition_retains_real_context_and_archive_files(
        tmp_path / "raw-missing",
        monkeypatch,
        raw_evidence_factory=missing_mapping,
        expected_plan22_calls=0,
        expected_effects=("raw-mapping", "screen"),
        exercise_archive_contracts=False,
    )
    test_outer_composition_retains_real_context_and_archive_files(
        tmp_path / "screen-insufficient",
        monkeypatch,
        screen_retain=False,
        expected_plan22_calls=0,
        expected_effects=("raw-mapping", "screen"),
        expected_state="INSUFFICIENT_EVIDENCE",
        trusted_clock_pre_cutoff_count=3,
        exercise_archive_contracts=False,
    )


@pytest.mark.parametrize("offset", (timedelta(0), timedelta(microseconds=1)))
def test_v4_reserves_archive_window_before_bharatstock_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offset: timedelta,
) -> None:
    test_outer_composition_retains_real_context_and_archive_files(
        tmp_path,
        monkeypatch,
        plan22_start_offset=offset,
        exercise_archive_contracts=False,
        expected_plan22_calls=0,
        expected_effects=("raw-mapping", "screen"),
        expect_archive_failure=True,
    )


def test_v4_rejects_post_return_archive_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_outer_composition_retains_real_context_and_archive_files(
        tmp_path,
        monkeypatch,
        exercise_post_return_adversaries=True,
        exercise_archive_contracts=False,
    )
