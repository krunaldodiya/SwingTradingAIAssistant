"""Behavioral V4 raw same-pass evidence contracts and reusable V4 fixtures."""

from __future__ import annotations

import sys
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta
from importlib import util
from pathlib import Path
from typing import Any

from swing_trading_ai_assistant.market_data import (
    current_same_pass_daily_v4 as raw_daily,
)

_CUTOFF = datetime(2026, 8, 4, 12, tzinfo=UTC)


def _bharatstock_fixture() -> Any:
    name = "current_same_pass_daily_v4_bharatstock_fixture"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = Path(__file__).parents[1] / "market_regime/test_bharatstock_regime_v4.py"
    spec = util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class _FixedClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant


def _rehashed(
    model: type[Any], value: Any, identity_field: str, **changes: object
) -> Any:
    """Return a valid V4 value after changing observable fixture facts."""
    core = {
        field.name: getattr(value, field.name)
        for field in fields(model)
        if field.name != identity_field
    }
    core.update(changes)
    return model(
        **core,
        **{
            identity_field: raw_daily._identity_from_values(model, core, identity_field)
        },
    )


class _TemporaryRetainedEvidence:
    """V4 retained-evidence port usable by downstream behavioral fixtures."""

    def __init__(self, *, mismatch_source: bool = False) -> None:
        self._delegate = _bharatstock_fixture()._TemporaryRetainedEvidence(
            mismatch_source=mismatch_source
        )

    @property
    def mapping_calls(self) -> int:
        return self._delegate.mapping_calls

    @property
    def download_calls(self) -> int:
        return self._delegate.download_calls

    @property
    def query_calls(self) -> int:
        return self._delegate.query_calls

    @property
    def downstream_effects(self) -> list[str]:
        return self._delegate.downstream_effects

    def mappings_under_lease(self, *args: object, **kwargs: object) -> object:
        return self._delegate.mappings_under_lease(*args, **kwargs)

    def missing_downloads_under_lease(self, *args: object, **kwargs: object) -> object:
        return self._delegate.missing_downloads_under_lease(*args, **kwargs)

    def download_under_lease(self, *args: object, **kwargs: object) -> object:
        return self._delegate.download_under_lease(*args, **kwargs)

    def query_and_project_under_lease(self, *args: object, **kwargs: object) -> object:
        return self._delegate.query_and_project_under_lease(*args, **kwargs)


def _scenario_request(tmp_path: Path, *, count: int = 1) -> tuple[Any, Any, Any]:
    fixture = _bharatstock_fixture()
    screen = fixture._screen_fixture()
    scenario = screen._scenario(tmp_path, count=count)
    request, sessions = fixture._request(scenario, screen)
    return scenario, request, sessions


def _request(size: int, *, tmp_path: Path) -> Any:
    """Build a V4 request with retained schedule evidence for fixture consumers."""
    scenario, request, _sessions = _scenario_request(tmp_path, count=size)
    scenario.close()
    return request


def _raw_sessions(tmp_path: Path, *, count: int = 1) -> tuple[Any, ...]:
    scenario, _request_value, sessions = _scenario_request(tmp_path, count=count)
    try:
        return sessions
    finally:
        scenario.close()


def _acquire(
    tmp_path: Path, *, count: int = 1, evidence: object | None = None
) -> tuple[Any, Any, Any]:
    scenario, request, sessions = _scenario_request(tmp_path, count=count)
    raw = raw_daily.UpstoxCurrentSamePassRawDailyV1(
        scenario.root,
        scenario.root / "schedule.json",
        clock=_FixedClock(_CUTOFF - timedelta(minutes=2)),
        evidence_port=evidence or _TemporaryRetainedEvidence(),
    )
    result = raw.acquire_exact(
        request,
        sessions,
        scenario.lease,
        invocation_started_at=_CUTOFF - timedelta(minutes=5),
        acquisition_effect_deadline=_CUTOFF - timedelta(seconds=30),
        official_active_session=None,
        trusted_clock=_FixedClock(_CUTOFF - timedelta(minutes=2)),
    )
    return scenario, request, result


def test_v4_raw_acquires_retained_completed_grid_and_exactly_validates(
    tmp_path: Path,
) -> None:
    scenario, request, result = _acquire(tmp_path)
    try:
        assert result.evidence_state == "OBSERVED"
        assert result.raw_grid is not None
        assert result.raw_grid.contract_version == "current-same-pass-raw-daily-grid@v4"
        assert len(result.raw_grid.bars) == 21
        assert result.partial_current_session.state == "NOT_REQUESTED"
        assert raw_daily.current_same_pass_raw_daily_result_is_exact_valid_v4(
            result, request
        )
    finally:
        scenario.close()


def test_v4_raw_rejects_reordered_mapping_bindings_without_downstream_download(
    tmp_path: Path,
) -> None:
    class ReorderedMappings(_TemporaryRetainedEvidence):
        def mappings_under_lease(self, *args: object, **kwargs: object) -> object:
            value = super().mappings_under_lease(*args, **kwargs)
            return tuple(reversed(value))

    scenario, _request_value, result = _acquire(
        tmp_path, count=2, evidence=ReorderedMappings()
    )
    try:
        assert result.evidence_state == "INSUFFICIENT_EVIDENCE"
        assert result.reasons == ("RAW_MAPPING_CONFLICTED",)
        assert result.raw_grid is None
    finally:
        scenario.close()


def test_v4_raw_rehashed_insufficiency_remains_a_real_exact_fixture(
    tmp_path: Path,
) -> None:
    scenario, request, result = _acquire(tmp_path)
    try:
        assert result.raw_grid is not None
        insufficient = _rehashed(
            type(result),
            result,
            "raw_result_identity_sha256",
            evidence_state="INSUFFICIENT_EVIDENCE",
            raw_grid=None,
            reasons=("RAW_BAR_MISSING",),
        )
        assert raw_daily.current_same_pass_raw_daily_result_is_exact_valid_v4(
            insufficient, request
        )
        partial = raw_daily._partial_failure(request, "PARTIAL_SOURCE_UNAVAILABLE")
        assert partial.state == "UNAVAILABLE"
        assert partial.reasons == ("PARTIAL_SOURCE_UNAVAILABLE",)
    finally:
        scenario.close()


def test_v4_request_keeps_supplied_order_and_canonical_identity_separate(
    tmp_path: Path,
) -> None:
    scenario, request, _sessions = _scenario_request(tmp_path, count=2)
    try:
        assert tuple(member.isin for member in request.members) == tuple(
            member.isin for member in scenario.manifest.members
        )
        assert request.canonical_cohort_identity_sha256 == raw_daily._hash(
            {
                "contract_version": "current-same-pass-canonical-cohort@v1",
                "cohort_selected_at": request.cohort_selected_at,
                "members": [
                    item.value()
                    for item in sorted(
                        request.members,
                        key=lambda item: (
                            item.isin,
                            item.exchange,
                            item.effective_symbol,
                        ),
                    )
                ],
            }
        )
    finally:
        scenario.close()
