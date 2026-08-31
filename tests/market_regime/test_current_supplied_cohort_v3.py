# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false, reportOperatorIssue=false, reportOptionalMemberAccess=false, reportOptionalOperand=false, reportReturnType=false
"""RED acceptance contracts for Plan 27's retained Market Regime V3 context.

The V3 module is intentionally imported only while each test executes.  Until
Plan 27 production exists, the focused run must fail solely because the
versioned authoritative module is absent, never during collection.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from importlib import import_module, machinery, util
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest

from swing_trading_ai_assistant.market_data.adjusted_daily import (
    adjusted_daily_request_identity_v2,
    adjusted_daily_schedule_identity_v2,
)
from swing_trading_ai_assistant.market_data.adjusted_daily.service import (
    _V2Member,
    mapping_identity_v2,
)
from swing_trading_ai_assistant.market_data.current_corporate_action_screen import (
    CurrentSuppliedCohortCorporateActionScreenResolverV1,
    UpstoxCorporateActionScreenProviderV1,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleEvidenceStore,
    ScheduleSession,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

_MODULE = "swing_trading_ai_assistant.market_regime.current_supplied_cohort_v3"
_V3_CONTRACT = "current-supplied-cohort-market-regime@v3"
_V3_SCHEMA_CONTRACT = "current-supplied-cohort-market-regime-schema@v3"
_V3_CALCULATION_CONTRACT = "current-supplied-cohort-market-regime-calculation@v3"
_ARCHIVE_CONTRACT = "current-same-pass-market-context-archive@v1"
_CUTOFF = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
_V3_SCHEMA_METADATA_DIGEST = (
    "fe7fcc792fb1a546437a032e7762e5cc5e95c9b4727f00e0cb78f92de4730d43"
)


_PLAN27_V3_SCHEMA_PREIMAGE = json.loads(
    (Path(__file__).parent / "data" / "plan27_v3_schema_preimage.json").read_text(
        encoding="utf-8"
    )
)

_PREFLIGHT_REASON_ORDER = (
    "SCHEDULE_EVIDENCE_MISSING",
    "SCHEDULE_EVIDENCE_STALE",
    "SCHEDULE_EVIDENCE_CONFLICTED",
    "SCHEDULE_CONTINUITY_UNPROVEN",
    "LATEST_COMPLETED_SESSION_UNRESOLVED",
)
_REASON_ORDER = (
    "COHORT_BINDING_MISMATCH",
    "RAW_MAPPING_MISSING",
    "RAW_MAPPING_STALE",
    "RAW_MAPPING_CONFLICTED",
    "RAW_ACQUISITION_UNAVAILABLE",
    "ACQUISITION_DEADLINE_EXCEEDED",
    "RAW_BAR_MISSING",
    "RAW_BAR_STALE",
    "RAW_BAR_CONFLICTED",
    "RAW_BAR_INVALID",
    "RAW_BAR_FUTURE_KNOWN",
    "CORPORATE_ACTION_SCREEN_INSUFFICIENT",
    "ADJUSTED_DAILY_CLOSE_HANDOFF_INVALID",
    "RAW_ADJUSTED_DIRECTION_CONFLICT",
)


_REQUEST_FIELDS = (
    "contract_version",
    "decision_cutoff",
    "cohort_selected_at",
    "members",
    "schedule_evidence_sha256",
    "schedule_identity_sha256",
    "plan22_schedule_identity_sha256",
    "schedule_source",
    "schedule_source_release",
    "include_partial_current_session",
    "plan21_cohort_identity_sha256",
    "canonical_cohort_identity_sha256",
    "plan22_request_identity_sha256",
    "request_identity_sha256",
)


_REPORT_FIELDS = (
    "contract_version",
    "schema_identity_sha256",
    "calculation_identity_sha256",
    "runtime_code_identity_sha256",
    "evidence_state",
    "request_identity_sha256",
    "canonical_cohort_identity_sha256",
    "cohort_size",
    "decision_cutoff",
    "decision_session",
    "comparison_session",
    "market_data_report_identity_sha256",
    "corporate_action_screen_identity_sha256",
    "adjusted_handoff_identity_sha256",
    "regime",
    "advances",
    "declines",
    "unchanged",
    "reasons",
    "report_identity_sha256",
)


_CONTEXT_FIELDS = (
    "contract_version",
    "schema_identity_sha256",
    "configuration_identity_sha256",
    "runtime_code_identity_sha256",
    "request",
    "raw_result",
    "market_data_report",
    "corporate_action_screen",
    "adjusted_handoff",
    "adjusted_failure",
    "adjusted_not_attempted",
    "market_regime_report",
    "direction_candidate",
    "component_ledger",
    "temporal_scope",
    "historical_availability_claim",
    "replay_capability",
    "context_identity_sha256",
    "context_object_sha256",
)


_RECEIPT_FIELDS = (
    "contract_version",
    "context_identity_sha256",
    "context_object_sha256",
    "context_byte_count",
    "context_filename",
    "archive_known_at",
    "context_receipt_identity_sha256",
)


_MARKER_FIELDS = (
    "contract_version",
    "context_identity_sha256",
    "context_object_sha256",
    "context_receipt_identity_sha256",
    "receipt_sha256",
    "archive_known_at",
    "completion_marker_identity_sha256",
)


_RETAINED_FIELDS = (
    "evidence_state",
    "context_identity_sha256",
    "context_object_sha256",
    "context_receipt_identity_sha256",
    "completion_marker_identity_sha256",
    "archive_known_at",
    "market_data_report",
    "market_regime_report",
    "partial_current_session",
    "retained_context_identity_sha256",
    "_archive_seal",
)


def _v3() -> Any:
    """Load the sole V3 authority at test execution time."""
    return import_module(_MODULE)


def test_v3_runtime_identity_supports_installed_package_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _v3()
    manifest = import_module(module._RUNTIME_MANIFEST_MODULE)
    baseline = module.current_same_pass_market_regime_runtime_code_identity_v3()
    installed_root = tmp_path / "site-packages"
    for loaded, relative_path in (
        (module, module._RUNTIME_SOURCE),
        (manifest, module._RUNTIME_MANIFEST),
    ):
        installed = installed_root.joinpath(*relative_path.split("/")[1:])
        installed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(loaded.__file__, installed)
        monkeypatch.setattr(loaded, "__file__", str(installed))
        monkeypatch.setattr(
            loaded,
            "__loader__",
            machinery.SourceFileLoader(loaded.__name__, str(installed)),
        )
    monkeypatch.setitem(sys.modules, manifest.__name__, manifest)

    assert module.current_same_pass_market_regime_runtime_code_identity_v3() == baseline
    source = installed_root.joinpath(
        "swing_trading_ai_assistant/market_regime/current_supplied_cohort_v3.py"
    )
    with source.open("ab") as copied:
        copied.write(b"\n")

    with pytest.raises(ValueError, match="V3 runtime identity invalid"):
        module.current_same_pass_market_regime_runtime_code_identity_v3()


def _type(module: Any, name: str) -> type[Any]:
    value = getattr(module, name, None)
    assert isinstance(value, type), f"missing Plan27 type {name}"
    return value


def _field_names(module: Any, name: str) -> tuple[str, ...]:
    return tuple(field.name for field in fields(_type(module, name)))


def _assert_closed_projection(
    module: Any, name: str, expected_fields: tuple[str, ...]
) -> None:
    assert _field_names(module, name) == expected_fields


def _fixture_module(name: str) -> Any:
    path = Path(__file__).parents[1] / "market_data" / f"{name}.py"
    spec = util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _members() -> tuple[Any, ...]:
    module = _v3()
    return (
        module.CurrentSamePassEquityMemberV1(
            "INE009A01021",
            "NSE",
            "EQUITY",
            "EQ",
            "INFY",
            date(2020, 1, 1),
            date(2030, 1, 1),
            "INFY.NS",
            "yfinance-symbol-mapping@v1",
            date(2020, 1, 1),
            None,
            "a" * 64,
            "nse-provider-map@v1",
        ),
        module.CurrentSamePassEquityMemberV1(
            "INE040A01034",
            "NSE",
            "EQUITY",
            "EQ",
            "HDFCBANK",
            date(2020, 1, 1),
            date(2030, 1, 1),
            "HDFCBANK.NS",
            "yfinance-symbol-mapping@v1",
            date(2020, 1, 1),
            None,
            "b" * 64,
            "nse-provider-map@v1",
        ),
        module.CurrentSamePassEquityMemberV1(
            "INE467B01029",
            "NSE",
            "EQUITY",
            "EQ",
            "TCS",
            date(2020, 1, 1),
            date(2030, 1, 1),
            "TCS.NS",
            "yfinance-symbol-mapping@v1",
            date(2020, 1, 1),
            None,
            "c" * 64,
            "nse-provider-map@v1",
        ),
    )


def test_v3_request_freezes_exact_fields_and_versioned_identities() -> None:
    module = _v3()

    _assert_closed_projection(
        module, "CurrentSamePassMarketRegimeRequestV3", _REQUEST_FIELDS
    )
    request = _type(module, "CurrentSamePassMarketRegimeRequestV3")
    assert _V3_CONTRACT in str(getattr(request, "__annotations__", {}))
    assert "request_identity_sha256" not in _REQUEST_FIELDS[:-1]


@pytest.mark.parametrize("size", (1, 5, 50))
def test_v3_request_admits_only_the_bounded_canonical_equity_cohort(size: int) -> None:
    module = _v3()

    member = _type(module, "CurrentSamePassEquityMemberV1")
    request = _type(module, "CurrentSamePassMarketRegimeRequestV3")
    assert "members" in request.__annotations__
    assert "provider_mapping_revision" in member.__annotations__
    assert 1 <= size <= 50


@pytest.mark.parametrize(
    "fault",
    (
        "permuted_members",
        "duplicate_isin",
        "duplicate_symbol",
        "invalid_effective_interval",
        "unsupported_exchange",
        "unsupported_capability",
    ),
)
def test_v3_request_rejects_noncanonical_or_unsupported_cohort_admission(
    fault: str,
) -> None:
    module = _v3()

    request = _type(module, "CurrentSamePassMarketRegimeRequestV3")
    assert fault
    assert _field_names(module, "CurrentSamePassEquityMemberV1")[-1] == (
        "provider_mapping_revision"
    )
    assert "members" in request.__annotations__


def test_v3_request_keeps_plan21_plan22_and_plan25_bridges_distinct() -> None:
    module = _v3()

    request = _type(module, "CurrentSamePassMarketRegimeRequestV3")
    annotations = request.__annotations__
    assert tuple(name for name in annotations if name.endswith("identity_sha256"))[
        -6:
    ] == (
        "schedule_identity_sha256",
        "plan22_schedule_identity_sha256",
        "plan21_cohort_identity_sha256",
        "canonical_cohort_identity_sha256",
        "plan22_request_identity_sha256",
        "request_identity_sha256",
    )
    member = _type(module, "CurrentSamePassEquityMemberV1")
    assert tuple(member.__annotations__)[-2:] == (
        "mapping_identity",
        "provider_mapping_revision",
    )


def test_v3_bridge_freezes_plan21_selected_time_and_plan22_mapping_projection() -> None:
    module = _v3()

    request = _type(module, "CurrentSamePassMarketRegimeRequestV3")
    member = _type(module, "CurrentSamePassEquityMemberV1")
    assert tuple(request.__annotations__)[1:4] == (
        "decision_cutoff",
        "cohort_selected_at",
        "members",
    )
    assert tuple(member.__annotations__)[3:12] == (
        "segment",
        "effective_symbol",
        "valid_from",
        "valid_through",
        "provider_symbol",
        "mapping_version",
        "mapping_valid_from",
        "mapping_valid_through",
        "mapping_identity",
    )


def test_v3_market_hour_and_post_close_session_contract_has_no_calendar_date_shortcut() -> (
    None
):
    module = _v3()

    raw_session = _type(module, "CurrentSamePassRawSessionV1")
    assert _field_names(module, "CurrentSamePassRawSessionV1") == (
        "position",
        "session",
        "open_at",
        "close_at",
        "kind",
        "session_identity_sha256",
    )
    assert "close_at" in raw_session.__annotations__
    assert _CUTOFF - timedelta(seconds=30) < _CUTOFF


@pytest.mark.parametrize(
    "mode,expected_relation",
    (
        ("market_hours", "prior_completed_session"),
        ("post_close", "today_completed_session"),
        ("pre_open", "prior_completed_session"),
        ("weekend_or_holiday", "prior_completed_session"),
    ),
)
def test_v3_resolves_latest_completed_official_session_by_close_time(
    mode: str, expected_relation: str
) -> None:
    module = _v3()
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
        module.CurrentSamePassRawSessionV1(
            position,
            item.trade_date,
            item.open_at,
            item.close_at,
            "SPECIAL" if item.kind == "SPECIAL" else "REGULAR",
        )
        for position, item in enumerate(completed)
    )
    member = _members()[0]
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
    plan22_schedule_identity = adjusted_daily_schedule_identity_v2(
        sessions=tuple(item.session for item in raw_sessions),
        decision_session_official_close_at=raw_sessions[-1].close_at,
        schedule_evidence_sha256=evidence_sha256,
        schedule_source=schedule.source,
        schedule_source_release=schedule.source_release,
    )
    plan22_request_identity = adjusted_daily_request_identity_v2(
        cohort_identity_sha256=canonical_identity,
        decision_cutoff=cutoff,
        schedule_identity_sha256=plan22_schedule_identity,
        members=(
            _V2Member(
                member.isin,
                member.exchange,
                member.instrument_type,
                member.segment,
                member.effective_symbol,
                member.provider_symbol,
                member.valid_from,
                member.valid_through,
                member.mapping_version,
                member.mapping_valid_from,
                member.mapping_valid_through,
                member.mapping_identity,
            ),
        ),
    )
    request_core = {
        "contract_version": _V3_CONTRACT,
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
    request = module.CurrentSamePassMarketRegimeRequestV3(
        **request_core,
        request_identity_sha256=module._identity_from_values(
            module.CurrentSamePassMarketRegimeRequestV3,
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


def test_v3_requires_exact_preacquired_adjusted_three_state_projection() -> None:
    module = _v3()

    success = _type(module, "_CurrentSamePassAdjustedSuccessV1")
    failure = _type(module, "_CurrentSamePassAdjustedFailureV1")
    not_attempted = _type(module, "_CurrentSamePassAdjustedNotAttemptedV1")
    failure_projection = _type(
        module, "CurrentSamePassAdjustedDailyCloseFailureProjectionV1"
    )
    not_attempted_projection = _type(
        module, "CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1"
    )
    assert tuple(success.__annotations__) == (
        "adjusted_handoff",
        "adjusted_failure",
        "adjusted_not_attempted",
    )
    assert tuple(failure.__annotations__) == (
        "adjusted_handoff",
        "adjusted_failure",
        "adjusted_not_attempted",
    )
    assert tuple(not_attempted.__annotations__) == (
        "adjusted_handoff",
        "adjusted_failure",
        "adjusted_not_attempted",
    )
    assert _field_names(
        module, "CurrentSamePassAdjustedDailyCloseFailureProjectionV1"
    ) == (
        "contract_version",
        "plan22_request_identity_sha256",
        "code",
        "reason",
        "failure_projection_identity_sha256",
    )
    assert _field_names(
        module, "CurrentSamePassAdjustedDailyCloseNotAttemptedProjectionV1"
    ) == (
        "contract_version",
        "plan22_request_identity_sha256",
        "evidence_state",
        "reason",
        "not_attempted_projection_identity_sha256",
    )
    assert failure_projection.__annotations__["plan22_request_identity_sha256"]
    assert not_attempted_projection.__annotations__["evidence_state"]


@pytest.mark.parametrize(
    "raw_direction,adjusted_direction,accepted",
    (
        ("ADVANCE", "ADVANCE", True),
        ("DECLINE", "DECLINE", True),
        ("UNCHANGED", "UNCHANGED", True),
        ("ADVANCE", "DECLINE", False),
        ("ADVANCE", "UNCHANGED", False),
        ("DECLINE", "ADVANCE", False),
        ("DECLINE", "UNCHANGED", False),
        ("UNCHANGED", "ADVANCE", False),
        ("UNCHANGED", "DECLINE", False),
    ),
)
def test_v3_requires_raw_and_adjusted_direction_equality_per_member(
    raw_direction: str,
    adjusted_direction: str,
    accepted: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_outer_composition_retains_real_context_and_archive_files(
        tmp_path,
        monkeypatch,
        exercise_archive_contracts=False,
        raw_directions=(raw_direction,),
        adjusted_directions=(adjusted_direction,),
        expected_state="OBSERVED" if accepted else "INSUFFICIENT_EVIDENCE",
    )


@pytest.mark.parametrize(
    "cohort_size,advances,declines,expected",
    (
        (5, 3, 0, "BROAD_ADVANCE"),
        (5, 0, 3, "BROAD_DECLINE"),
        (5, 2, 2, "MIXED_PARTICIPATION"),
        (50, 30, 0, "BROAD_ADVANCE"),
        (50, 0, 30, "BROAD_DECLINE"),
        (50, 29, 21, "MIXED_PARTICIPATION"),
        (5, 0, 0, "MIXED_PARTICIPATION"),
    ),
)
def test_v3_uses_inclusive_sixty_percent_breadth_without_reduced_denominator(
    cohort_size: int,
    advances: int,
    declines: int,
    expected: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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


def test_v3_private_direction_candidate_is_bound_prearchive_and_seal_only() -> None:
    module = _v3()

    candidate = _type(module, "_CurrentSamePassMemberDirectionCandidateV3")
    assert tuple(candidate.__annotations__) == (
        "request_identity_sha256",
        "raw_grid_identity_sha256",
        "corporate_action_screen_identity_sha256",
        "adjusted_handoff_identity_sha256",
        "market_regime_report_identity_sha256",
        "canonical_cohort_identity_sha256",
        "schedule_identity_sha256",
        "decision_cutoff",
        "rows",
        "direction_candidate_identity_sha256",
    )
    assert not hasattr(candidate, "canonical_json_bytes")


def test_v3_retained_context_accepts_no_caller_supplied_direction_candidate() -> None:
    module = _v3()

    retained = _type(module, "RetainedCurrentSamePassMarketContextV3")
    assert _field_names(module, "RetainedCurrentSamePassMarketContextV3") == (
        _RETAINED_FIELDS
    )
    assert "direction_candidate" not in retained.__annotations__
    assert "_archive_seal" in retained.__annotations__


def test_v3_freezes_context_schema_and_four_component_ledger() -> None:
    module = _v3()

    _assert_closed_projection(
        module, "PrivateCurrentSamePassMarketContextObjectV3", _CONTEXT_FIELDS
    )
    ledger = _type(module, "CurrentSamePassContextComponentLedgerRowV1")
    assert tuple(ledger.__annotations__) == (
        "position",
        "component",
        "contract_version",
        "evidence_state",
        "schema_identity_sha256",
        "runtime_code_identity_sha256",
        "primary_identity_sha256",
        "known_at",
        "reasons",
        "ledger_row_identity_sha256",
    )


@pytest.mark.parametrize("key", ("semantic_type", "unit", "nullability", "bounds"))
def test_v3_schema_preimage_is_complete_independent_and_rejects_every_field_drift(
    key: str,
) -> None:
    module = _v3()
    metadata = module.current_same_pass_market_regime_schema_metadata_v3()

    assert module._canonical(metadata) == module._canonical(_PLAN27_V3_SCHEMA_PREIMAGE)
    assert (
        module.current_same_pass_market_regime_schema_metadata_digest_v3(metadata)
        == _V3_SCHEMA_METADATA_DIGEST
    )

    for row_index, row in enumerate(_PLAN27_V3_SCHEMA_PREIMAGE["type_rows"]):
        for field_index, _field in enumerate(row["ordered_fields"]):
            mutated = deepcopy(metadata)
            mutated["type_rows"][row_index]["ordered_fields"][field_index][key] = (
                "FORGED"
            )
            with pytest.raises(ValueError, match="frozen contract"):
                module.current_same_pass_market_regime_schema_identity_from_metadata_v3(
                    mutated
                )
    state = deepcopy(metadata)
    state["state_projections"] = ()
    with pytest.raises(ValueError, match="frozen contract"):
        module.current_same_pass_market_regime_schema_identity_from_metadata_v3(state)

    unknown = deepcopy(metadata)
    unknown["unexpected"] = "FORGED"
    with pytest.raises(ValueError, match="unknown V3 schema metadata key"):
        module.current_same_pass_market_regime_schema_metadata_digest_v3(unknown)


def test_v3_identity_contracts_are_acyclic_and_archive_time_is_not_context_data() -> (
    None
):
    module = _v3()

    _assert_closed_projection(
        module, "CurrentSamePassContextReceiptV1", _RECEIPT_FIELDS
    )
    _assert_closed_projection(
        module, "CurrentSamePassContextCompletionMarkerV1", _MARKER_FIELDS
    )
    context = _type(module, "PrivateCurrentSamePassMarketContextObjectV3")
    assert "archive_known_at" not in context.__annotations__
    assert _CONTEXT_FIELDS[-1] == "context_object_sha256"


def test_v3_configuration_preimage_is_exhaustive_and_fixed() -> None:
    module = _v3()

    assert module._configuration_identity() == module._identity(
        {
            "contract_version": "current-same-pass-market-context-archive@v1",
            "structural_bounds": {
                "cohort_members": [1, 50],
                "resolved_sessions": 21,
                "context_bytes": [1, 4_194_304],
                "receipt_bytes": [1, 16_384],
                "marker_bytes": [1, 4_096],
            },
            "canonicalization": "CJ UTF-8 sorted keys compact no-NaN trailing-LF",
            "reason_order": {
                "preflight": list(_PREFLIGHT_REASON_ORDER),
                "post_session": list(_REASON_ORDER),
            },
            "precedence": (
                "schedule-before-raw-before-screen-before-adjusted; "
                "upstream-insufficiency-skips-adjusted; whole-result-suppression"
            ),
            "raw_source_policy": "current-same-pass-raw-daily-grid@v1-only",
            "partial_policy": "separate-optional-context",
            "retention_names_and_limits": {
                "context": "context-<identity>.json",
                "receipt": "retained-<identity>.json",
                "marker": "completion-<identity>.json",
                "pending_guard": "pending-<identity>.json",
                "admissible_guard": "admissible-<identity>.json",
                "context_bytes": 4_194_304,
                "receipt_bytes": 16_384,
                "marker_bytes": 4_096,
                "guard_bytes": 4_096,
            },
        }
    )
    assert (
        module._configuration_identity()
        == "09e6c023804b3cbe1aebd86c724c6465cc06454ca0744cde16a8bc30d11af1df"
    )


def test_v3_calculation_preimage_binds_adjusted_admission_state() -> None:
    module = _v3()

    assert module._calculation_identity() == module._identity(
        {
            "contract_version": _V3_CALCULATION_CONTRACT,
            "comparison": "Decimal(close(S20)) cmp Decimal(close(S0))",
            "raw_adjusted_direction_equality": True,
            "adjusted_admission": (
                "current-prospective-success-only; "
                "not-attempted-preserves-upstream-insufficiency"
            ),
            "advance_formula": "advances*5>=cohort_size*3",
            "decline_formula": "declines*5>=cohort_size*3",
            "reason_order": _REASON_ORDER,
            "suppression": "whole-result",
        }
    )
    assert (
        module._calculation_identity()
        == "73c25ec32259c05b26e95696d41fd93f1427ad9a77c8b381b6b05c585e44dd80"
    )


def test_v3_receipt_marker_and_retained_projection_copy_one_known_at() -> None:
    module = _v3()

    receipt = _type(module, "CurrentSamePassContextReceiptV1")
    marker = _type(module, "CurrentSamePassContextCompletionMarkerV1")
    retained = _type(module, "RetainedCurrentSamePassMarketContextV3")
    assert "archive_known_at" in receipt.__annotations__
    assert "archive_known_at" in marker.__annotations__
    assert "archive_known_at" in retained.__annotations__
    metadata = module.current_same_pass_market_regime_schema_metadata_v3()
    retained_row = next(
        row
        for row in metadata["type_rows"]
        if row["name"] == "RetainedCurrentSamePassMarketContextV3"
    )
    assert "_archive_seal" not in {
        field["name"] for field in retained_row["ordered_fields"]
    }


def test_v3_observed_and_insufficient_state_projections_are_mutually_exclusive() -> (
    None
):
    module = _v3()

    raw = _type(module, "PrivateCurrentSamePassRawDailyResultV1")
    report = _type(module, "CurrentSamePassMarketRegimeReportV3")
    assert tuple(raw.__annotations__) == (
        "evidence_state",
        "request_identity_sha256",
        "canonical_cohort_identity_sha256",
        "decision_session",
        "comparison_session",
        "resolved_sessions",
        "mapping_receipts",
        "official_active_session",
        "raw_grid",
        "partial_current_session",
        "reasons",
        "raw_result_identity_sha256",
    )
    metadata = module.current_same_pass_market_regime_schema_metadata_v3()
    ledger_state_projections = dict(metadata["state_projections"])[
        "CurrentSamePassContextComponentLedgerRowV1"
    ]
    assert ledger_state_projections == (
        (
            "RAW_GRID_V1/OBSERVED",
            "position=0,contract=current-same-pass-raw-daily-grid@v1,schema_runtime=RAW_GRID,primary=RAW_GRID,known_at=MAX_RAW_PARTIAL,reasons=EMPTY",
        ),
        (
            "RAW_GRID_V1/INSUFFICIENT_EVIDENCE",
            "position=0,contract=current-same-pass-raw-daily-grid@v1,schema_runtime=RAW_SUCCESSOR,primary=RAW_RESULT,known_at=PARTIAL_OR_NONE,reasons=RAW_RESULT",
        ),
        (
            "CORPORATE_ACTION_SCREEN_V1/SCREENED",
            "position=1,contract=current-supplied-cohort-corporate-action-screen@v1,schema_runtime=SCREEN,primary=SCREEN,known_at=MAX_PROVIDER_RETRIEVED,reasons=EMPTY",
        ),
        (
            "CORPORATE_ACTION_SCREEN_V1/INSUFFICIENT_EVIDENCE",
            "position=1,contract=current-supplied-cohort-corporate-action-screen@v1,schema_runtime=SCREEN,primary=SCREEN,known_at=MAX_PROVIDER_RETRIEVED_OR_NONE,reasons=CORPORATE_ACTION_SCREEN_INSUFFICIENT",
        ),
        (
            "ADJUSTED_DAILY_CLOSE_V2/SUCCESS",
            "position=2,contract=provider-neutral-adjusted-daily-close@v2,schema_runtime=NONE,primary=HANDOFF,known_at=HANDOFF_RETRIEVED,reasons=EMPTY",
        ),
        (
            "ADJUSTED_DAILY_CLOSE_V2/FAILURE",
            "position=2,contract=provider-neutral-adjusted-daily-close@v2,schema_runtime=NONE,primary=FAILURE_PROJECTION,known_at=NONE,reasons=ADJUSTED_FAILURE_REASON",
        ),
        (
            "ADJUSTED_DAILY_CLOSE_V2/NOT_ATTEMPTED",
            "position=2,contract=provider-neutral-adjusted-daily-close@v2,schema_runtime=NONE,primary=NOT_ATTEMPTED_PROJECTION,known_at=NONE,reasons=UPSTREAM_INSUFFICIENT_EVIDENCE",
        ),
        (
            "MARKET_REGIME_V3/OBSERVED",
            "position=3,contract=current-supplied-cohort-market-regime@v3,schema_runtime=V3_REPORT,primary=V3_REPORT,known_at=MAX_POSITIONS_0_2,reasons=EMPTY",
        ),
        (
            "MARKET_REGIME_V3/INSUFFICIENT_EVIDENCE",
            "position=3,contract=current-supplied-cohort-market-regime@v3,schema_runtime=V3_REPORT,primary=V3_REPORT,known_at=MAX_POSITIONS_0_2_OR_NONE,reasons=V3_REPORT",
        ),
    )
    assert tuple(report.__annotations__)[4] == "evidence_state"
    assert _REASON_ORDER[-1] == "RAW_ADJUSTED_DIRECTION_CONFLICT"


def test_v3_reasons_preserve_closed_global_precedence_and_suppression() -> None:
    module = _v3()

    report = _type(module, "CurrentSamePassMarketRegimeReportV3")
    assert _REASON_ORDER.index("RAW_BAR_FUTURE_KNOWN") < _REASON_ORDER.index(
        "CORPORATE_ACTION_SCREEN_INSUFFICIENT"
    )
    assert _REASON_ORDER.index(
        "ADJUSTED_DAILY_CLOSE_HANDOFF_INVALID"
    ) < _REASON_ORDER.index("RAW_ADJUSTED_DIRECTION_CONFLICT")
    assert "reasons" in report.__annotations__


def test_v3_deadline_contract_reserves_archive_window_and_distinguishes_overrun() -> (
    None
):
    module = _v3()

    raw = _type(module, "PrivateCurrentSamePassRawDailyResultV1")
    failure = _type(module, "CurrentSamePassArchiveFailureV1")
    assert _CUTOFF - timedelta(seconds=30) == datetime(
        2026, 8, 24, 9, 59, 30, tzinfo=UTC
    )
    assert "reasons" in raw.__annotations__
    assert "reason" in failure.__annotations__


def test_v3_retained_bytes_redact_private_grid_adjusted_screen_and_directions() -> None:
    module = _v3()

    retained = _type(module, "RetainedCurrentSamePassMarketContextV3")
    public_fields = set(retained.__annotations__)
    assert public_fields.isdisjoint(
        {
            "raw_result",
            "raw_grid",
            "corporate_action_screen",
            "adjusted_handoff",
            "adjusted_failure",
            "direction_candidate",
        }
    )


def test_v3_retained_context_has_no_direct_mint_and_serializes_public_projection() -> (
    None
):
    module = _v3()
    retained = _type(module, "RetainedCurrentSamePassMarketContextV3")

    assert not hasattr(module, "_mint_retained_context")
    with pytest.raises(TypeError, match="archive-minted"):
        retained()

    core = {
        "evidence_state": "RETAINED",
        "context_identity_sha256": "a" * 64,
        "context_object_sha256": "b" * 64,
        "context_receipt_identity_sha256": "c" * 64,
        "completion_marker_identity_sha256": "d" * 64,
        "archive_known_at": "2026-08-24T10:00:00.000000Z",
        "market_data_report": {"public": "market-data"},
        "market_regime_report": {"public": "market-regime"},
        "partial_current_session": {"public": "partial"},
    }
    retained_identity = hashlib.sha256(
        json.dumps(
            core, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        + b"\n"
    ).hexdigest()
    value = object.__new__(retained)
    for name, item in {
        **core,
        "archive_known_at": datetime(2026, 8, 24, 10, tzinfo=UTC),
        "retained_context_identity_sha256": retained_identity,
        "_archive_seal": "private archive seal must not serialize",
    }.items():
        object.__setattr__(value, name, item)

    expected = {**core, "retained_context_identity_sha256": retained_identity}
    expected_bytes = (
        json.dumps(
            expected, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        + b"\n"
    )
    assert value.canonical_json_bytes() == expected_bytes
    assert (
        value.retained_context_identity_sha256
        == hashlib.sha256(
            json.dumps(
                core, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            + b"\n"
        ).hexdigest()
    )
    assert b"_archive_seal" not in expected_bytes
    assert b"private archive seal" not in expected_bytes


def test_v3_context_archive_bounds_are_frozen_before_identity_and_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _v3()
    captured: dict[str, Any] = {}
    directions = ("UNCHANGED",) * 50
    test_outer_composition_retains_real_context_and_archive_files(
        tmp_path,
        monkeypatch,
        exercise_archive_contracts=False,
        raw_directions=directions,
        adjusted_directions=directions,
        expected_state="OBSERVED",
        capture=captured,
        include_partial=True,
    )
    candidate = captured["candidate"]
    context = candidate.context_object
    context_bytes = context.canonical_json_bytes()
    assert len(context.request.members) == 50
    assert len(context.raw_result.raw_grid.source_rows) == 1_050
    assert len(context.raw_result.raw_grid.bars) == 1_050
    assert context.raw_result.partial_current_session.state == "OBSERVED"
    assert context.raw_result.partial_current_session.rows is not None
    assert len(context.raw_result.partial_current_session.rows) == 50
    assert context_bytes == context.canonical_json_bytes()
    assert 1 <= len(context_bytes) <= 4_194_304

    bound_root = tmp_path / "context-bound"
    bound_root.mkdir(mode=0o700)
    descriptor = os.open(bound_root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        module._publish_exact(descriptor, "maximum.json", b"x" * 4_194_304, 4_194_304)
        assert (bound_root / "maximum.json").stat().st_size == 4_194_304
        with pytest.raises(ValueError, match="archive bounds"):
            module._publish_exact(
                descriptor,
                "maximum-plus-one.json",
                b"x" * 4_194_305,
                4_194_304,
            )
    finally:
        os.close(descriptor)


def test_v3_exact_retry_reuses_persisted_identity_time_and_adjusted_union() -> None:
    module = _v3()

    request = _type(module, "CurrentSamePassMarketRegimeRequestV3")
    retained = _type(module, "RetainedCurrentSamePassMarketContextV3")
    assert "request_identity_sha256" in request.__annotations__
    assert "archive_known_at" in retained.__annotations__
    assert _V3_SCHEMA_CONTRACT and _V3_CALCULATION_CONTRACT


def test_v3_leaves_plan20_v1_v2_and_industry_v1_without_alias_or_mutation() -> None:
    module = _v3()

    assert not hasattr(module, "evaluate_current_supplied_cohort_market_regime_v1")
    assert not hasattr(module, "evaluate_current_supplied_cohort_market_regime_v2")
    assert not hasattr(module, "reduce_current_industry_participation_v1")


def test_v3_context_contracts_use_exact_version_literals() -> None:
    module = _v3()

    request = _type(module, "CurrentSamePassMarketRegimeRequestV3")
    report = _type(module, "CurrentSamePassMarketRegimeReportV3")
    context = _type(module, "PrivateCurrentSamePassMarketContextObjectV3")
    assert _V3_CONTRACT in str(request.__annotations__)
    assert _V3_CONTRACT in str(report.__annotations__)
    assert _ARCHIVE_CONTRACT in str(context.__annotations__)


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
    module = _v3()
    members = _members()[:1]
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
        plan22_identity = adjusted_daily_request_identity_v2(
            cohort_identity_sha256=canonical_identity,
            decision_cutoff=cutoff,
            schedule_identity_sha256=plan22_schedule_identity,
            members=(
                _V2Member(
                    members[0].isin,
                    members[0].exchange,
                    members[0].instrument_type,
                    members[0].segment,
                    members[0].effective_symbol,
                    members[0].provider_symbol,
                    members[0].valid_from,
                    members[0].valid_through,
                    members[0].mapping_version,
                    members[0].mapping_valid_from,
                    members[0].mapping_valid_through,
                    members[0].mapping_identity,
                ),
            ),
        )
        request_core = {
            "contract_version": _V3_CONTRACT,
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
        request = module.CurrentSamePassMarketRegimeRequestV3(
            **request_core,
            request_identity_sha256=module._identity_from_values(
                module.CurrentSamePassMarketRegimeRequestV3,
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

        raw, screen, provider, archive = Effects(), Effects(), Effects(), Effects()
        result = (
            module.acquire_build_and_retain_current_supplied_cohort_market_regime_v3(
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


def test_preflight_failure_rejects_noncanonical_multi_reason_order() -> None:
    module = _v3()
    canonical_core = {
        "contract_version": "current-same-pass-preflight-failure@v1",
        "evidence_state": "INSUFFICIENT_EVIDENCE",
        "request_identity_sha256": "1" * 64,
        "canonical_cohort_identity_sha256": "2" * 64,
        "reasons": (
            "SCHEDULE_EVIDENCE_MISSING",
            "SCHEDULE_EVIDENCE_CONFLICTED",
        ),
        "consumer_disposition": "INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED",
    }

    with pytest.raises(ValueError, match="invalid same-pass preflight failure"):
        module.CurrentSamePassPreflightFailureV1(
            **{
                **canonical_core,
                "reasons": tuple(reversed(canonical_core["reasons"])),
            },
            failure_identity_sha256=module._identity(canonical_core),
        )


def test_preflight_failure_rejects_canonical_json_identity_mismatch() -> None:
    module = _v3()
    core = {
        "contract_version": "current-same-pass-preflight-failure@v1",
        "evidence_state": "INSUFFICIENT_EVIDENCE",
        "request_identity_sha256": "1" * 64,
        "canonical_cohort_identity_sha256": "2" * 64,
        "reasons": (
            "SCHEDULE_EVIDENCE_MISSING",
            "SCHEDULE_EVIDENCE_CONFLICTED",
        ),
        "consumer_disposition": "INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED",
    }
    mismatched_core = {**core, "reasons": ("SCHEDULE_EVIDENCE_MISSING",)}

    with pytest.raises(ValueError, match="invalid same-pass preflight failure"):
        module.CurrentSamePassPreflightFailureV1(
            **core,
            failure_identity_sha256=module._identity(mismatched_core),
        )


@pytest.mark.parametrize("reason", _PREFLIGHT_REASON_ORDER)
def test_post_resolution_v3_reason_admission_rejects_preflight_reasons(
    reason: str,
) -> None:
    module = _v3()

    with pytest.raises(ValueError, match="invalid reasons"):
        module._ordered_reasons((reason,))


def test_outer_composition_retains_real_context_and_archive_files(  # noqa: C901
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_evidence_factory: Any | None = None,
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
    """Exercise the public Plan-27 effect chain against real schedule and archive files."""
    screen_test = _fixture_module("test_current_corporate_action_screen")
    raw_test = _fixture_module("test_current_same_pass_daily")
    module = _v3()
    cohort_size = len(raw_directions) if raw_directions is not None else 1
    if adjusted_directions is not None and len(adjusted_directions) != cohort_size:
        raise ValueError("direction fixture size mismatch")
    scenario = screen_test._scenario(tmp_path, count=cohort_size, retain=screen_retain)
    original_cutoff = raw_test._CUTOFF
    try:
        raw_test._CUTOFF = screen_test._CUTOFF
        base_schedule = screen_test._schedule()
        schedule = ExpectedSessionSchedule(
            3,
            "nse-upstox-composed-calendar",
            "composed-calendar@v1=" + screen_test._RELEASE.removeprefix("sha256:"),
            base_schedule.as_of,
            base_schedule.timezone,
            base_schedule.covered_from,
            screen_test._CUTOFF.date(),
            base_schedule.sessions
            + (
                ScheduleSession(
                    screen_test._CUTOFF.date(),
                    datetime(2026, 8, 4, 3, 45, tzinfo=UTC),
                    datetime(2026, 8, 4, 13, tzinfo=UTC),
                    "SPECIAL",
                ),
            ),
            base_schedule.closures,
        )
        retained_schedule = scenario.schedule_store.retain(schedule)
        assert retained_schedule.digest is not None
        schedule_sha256 = retained_schedule.digest
        members = tuple(
            module.CurrentSamePassEquityMemberV1(
                manifest_member.isin,
                "NSE",
                "EQUITY",
                "EQ",
                manifest_member.symbol,
                screen_test._S0,
                screen_test._CUTOFF.date() if include_partial else screen_test._S20,
                f"{manifest_member.symbol}.NS",
                "yfinance-symbol-mapping@v1",
                screen_test._S0,
                None,
                mapping_identity_v2(
                    isin=manifest_member.isin,
                    exchange="NSE",
                    instrument_type="EQUITY",
                    segment="EQ",
                    effective_symbol=manifest_member.symbol,
                    provider_symbol=f"{manifest_member.symbol}.NS",
                    mapping_valid_from=screen_test._S0,
                    mapping_valid_through=None,
                ),
                f"upstox-bod-nse@fixture-{position}",
            )
            for position, manifest_member in enumerate(scenario.manifest.members)
        )
        plan21_identity = scenario.manifest.cohort_identity_sha256
        canonical_identity = raw_test.raw_daily._hash(
            {
                "contract_version": "current-same-pass-canonical-cohort@v1",
                "cohort_selected_at": screen_test._SELECTED_AT,
                "members": [member.value() for member in members],
            }
        )
        resolved_sessions = tuple(
            raw_test.CurrentSamePassRawSessionV1(
                position,
                item.trade_date,
                item.open_at,
                item.close_at,
                "SPECIAL" if item.kind == "SPECIAL" else "REGULAR",
            )
            for position, item in enumerate(schedule.sessions[:-1])
        )
        sessions = tuple(item.session for item in resolved_sessions)
        schedule_identity = raw_test.raw_daily.current_same_pass_schedule_identity_v1(
            schedule_evidence_sha256=schedule_sha256,
            schedule_source="nse-upstox-composed-calendar",
            schedule_source_release=schedule.source_release,
            timezone=schedule.timezone,
            coverage_through=schedule.covered_to,
            sessions=resolved_sessions,
        )
        plan22_schedule_identity = adjusted_daily_schedule_identity_v2(
            sessions=sessions,
            decision_session_official_close_at=resolved_sessions[-1].close_at,
            schedule_evidence_sha256=schedule_sha256,
            schedule_source="nse-upstox-composed-calendar",
            schedule_source_release=schedule.source_release,
        )
        plan22_identity = adjusted_daily_request_identity_v2(
            cohort_identity_sha256=canonical_identity,
            decision_cutoff=screen_test._CUTOFF,
            schedule_identity_sha256=plan22_schedule_identity,
            members=tuple(
                _V2Member(
                    member.isin,
                    member.exchange,
                    member.instrument_type,
                    member.segment,
                    member.effective_symbol,
                    member.provider_symbol,
                    member.valid_from,
                    member.valid_through,
                    member.mapping_version,
                    member.mapping_valid_from,
                    member.mapping_valid_through,
                    member.mapping_identity,
                )
                for member in members
            ),
        )
        request_identity = raw_test.raw_daily._hash(
            {
                "contract_version": _V3_CONTRACT,
                "decision_cutoff": screen_test._CUTOFF,
                "cohort_selected_at": screen_test._SELECTED_AT,
                "members": members,
                "schedule_evidence_sha256": schedule_sha256,
                "schedule_identity_sha256": schedule_identity,
                "plan22_schedule_identity_sha256": plan22_schedule_identity,
                "schedule_source": "nse-upstox-composed-calendar",
                "schedule_source_release": schedule.source_release,
                "include_partial_current_session": include_partial,
                "plan21_cohort_identity_sha256": plan21_identity,
                "canonical_cohort_identity_sha256": canonical_identity,
                "plan22_request_identity_sha256": plan22_identity,
            }
        )
        request = module.CurrentSamePassMarketRegimeRequestV3(
            _V3_CONTRACT,
            screen_test._CUTOFF,
            screen_test._SELECTED_AT,
            members,
            schedule_sha256,
            schedule_identity,
            plan22_schedule_identity,
            "nse-upstox-composed-calendar",
            schedule.source_release,
            include_partial,
            plan21_identity,
            canonical_identity,
            plan22_identity,
            request_identity,
        )

        effects: list[str] = []

        @dataclass
        class Provider:
            calls: int = 0

            def download(self, **_: object) -> object:
                self.calls += 1
                effects.append("plan22")
                return {
                    "timezone": "Asia/Kolkata",
                    "index": sessions,
                    "close": {
                        member.provider_symbol: tuple(
                            100
                            if position < len(sessions) - 1
                            else 101
                            if (adjusted_directions or ("UNCHANGED",) * cohort_size)[
                                member_position
                            ]
                            == "ADVANCE"
                            else 99
                            if (adjusted_directions or ("UNCHANGED",) * cohort_size)[
                                member_position
                            ]
                            == "DECLINE"
                            else 100
                            for position in range(len(sessions))
                        )
                        for member_position, member in enumerate(members)
                    },
                    "retrieved_at": screen_test._CUTOFF - timedelta(minutes=1),
                    "provider_source": "yfinance==1.6.0",
                    "temporal_label": "REVISED_NON_PIT",
                }

        @dataclass
        class Clock:
            values: list[datetime]

            def now(self) -> datetime:
                if len(self.values) > 1:
                    return self.values.pop(0)
                return self.values[0]

        class RecordingResolver:
            def resolve_exact(self, *args: object) -> object:
                effects.append("screen")
                return resolver.resolve_exact(*args)

        class DirectionalEvidence(raw_test._TemporaryRetainedEvidence):
            def query_and_project_under_lease(self, *args: Any, **kwargs: Any) -> Any:
                source_rows, bars = super().query_and_project_under_lease(
                    *args, **kwargs
                )
                direction_by_isin = {
                    member.isin: direction
                    for member, direction in zip(
                        members,
                        raw_directions or ("UNCHANGED",) * cohort_size,
                        strict=True,
                    )
                }
                first_session = resolved_sessions[0].session
                last_session = resolved_sessions[-1].session
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
                        raw_test._rehashed(
                            type(bar),
                            bar,
                            "raw_bar_identity_sha256",
                            open=Decimal("100"),
                            high=Decimal("102"),
                            low=Decimal("98"),
                            close=close,
                        )
                    )
                return source_rows, tuple(projected)

        class MaximumPartialEvidence(DirectionalEvidence):
            def partial_current_session_under_lease(
                self,
                partial_request: Any,
                mappings: tuple[Any, ...],
                active_session: Any,
                _lease: Any,
            ) -> Any:
                as_of = partial_request.decision_cutoff.replace(
                    second=0, microsecond=0
                ) - timedelta(minutes=1)
                known_at = partial_request.decision_cutoff
                rows = []
                for mapping in mappings:
                    receipt = raw_test.raw_daily._hash(
                        {
                            "mapping": mapping.raw_mapping_projection_identity_sha256,
                            "official_active_session": (
                                active_session.partial_official_session_identity_sha256
                            ),
                            "session": active_session.session,
                            "as_of": as_of,
                            "query_known_at": known_at,
                        }
                    )
                    core = {
                        "isin": mapping.member.isin,
                        "session": active_session.session,
                        "as_of": as_of,
                        "price": Decimal("100"),
                        "cumulative_volume": 1_000,
                        "provider": "UPSTOX",
                        "price_basis": "RAW",
                        "source_receipt_identity_sha256": receipt,
                        "known_at": known_at,
                    }
                    rows.append(
                        raw_test.raw_daily.PartialCurrentSessionRowV1(
                            **core,
                            partial_current_session_row_identity_sha256=(
                                raw_test.raw_daily._identity_from_values(
                                    raw_test.raw_daily.PartialCurrentSessionRowV1,
                                    core,
                                    "partial_current_session_row_identity_sha256",
                                )
                            ),
                        )
                    )
                core = {
                    "label": "PARTIAL_CURRENT_SESSION",
                    "state": "OBSERVED",
                    "session": active_session.session,
                    "as_of": as_of,
                    "known_at": known_at,
                    "rows": tuple(rows),
                    "reasons": (),
                }
                return raw_test.raw_daily.PartialCurrentSessionSnapshotV1(
                    **core,
                    partial_snapshot_identity_sha256=(
                        raw_test.raw_daily._identity_from_values(
                            raw_test.raw_daily.PartialCurrentSessionSnapshotV1,
                            core,
                            "partial_snapshot_identity_sha256",
                        )
                    ),
                )

        provider = Provider()
        raw = raw_test.UpstoxCurrentSamePassRawDailyV1(
            scenario.root,
            scenario.root / "schedule.json",
            clock=raw_test._FixedClock(screen_test._CUTOFF - timedelta(minutes=2)),
            evidence_port=(
                raw_evidence_factory(raw_test)
                if raw_evidence_factory is not None
                else MaximumPartialEvidence()
                if include_partial
                else DirectionalEvidence()
            ),
        )

        class RecordingRaw:
            def acquire_exact(self, *args: object, **kwargs: object) -> object:
                effects.append("raw-mapping")
                return raw.acquire_exact(*args, **kwargs)

        recording_raw = RecordingRaw()
        resolver = CurrentSuppliedCohortCorporateActionScreenResolverV1(
            scenario.schedule_store,
            UpstoxCorporateActionScreenProviderV1(scenario.store),
        )
        recording_resolver = RecordingResolver()
        inner_archive = module.FileCurrentSamePassMarketContextArchiveV1(
            scenario.root,
            clock=Clock(
                [screen_test._CUTOFF - timedelta(seconds=30)]
                + [screen_test._CUTOFF] * 32
            ),
        )
        if exercise_post_return_adversaries:

            class SameRootBackdatedDelegate:
                called = False

                def archive_exact(self, *_: object, **__: object) -> object:
                    self.called = True
                    raise AssertionError("mutable inner delegate was invoked")

            backdated_inner = SameRootBackdatedDelegate()
            with pytest.raises(AttributeError):
                inner_archive._archive = backdated_inner
            with pytest.raises(AttributeError):
                object.__setattr__(inner_archive, "_archive", backdated_inner)
            assert not hasattr(inner_archive, "_archive")
            assert not backdated_inner.called
            assert not (scenario.root / ".current-same-pass-market-regime-v3").exists()

        class ConcurrentFirstArchive:
            def archive_exact(
                self,
                archive_request: Any,
                candidate: Any,
                lease: Any,
                *,
                trusted_clock: Any = None,
            ) -> Any:
                exactness_failure = module._candidate_exactness_failure(
                    archive_request, candidate
                )
                assert exactness_failure is None, exactness_failure
                assert module._candidate_is_exact(archive_request, candidate)
                self.candidate = candidate
                gate = Barrier(2)

                def archive_once() -> Any:
                    gate.wait()
                    return inner_archive.archive_exact(
                        archive_request,
                        candidate,
                        lease,
                        trusted_clock=trusted_clock,
                    )

                with ThreadPoolExecutor(max_workers=2) as executor:
                    first, second = tuple(
                        executor.map(lambda _: archive_once(), range(2))
                    )
                if expect_archive_failure:
                    assert type(first) is module.CurrentSamePassArchiveFailureV1
                    assert type(second) is module.CurrentSamePassArchiveFailureV1
                    return first
                assert type(first) is module.RetainedCurrentSamePassMarketContextV3
                assert type(second) is module.RetainedCurrentSamePassMarketContextV3
                assert (
                    first.retained_context_identity_sha256
                    == second.retained_context_identity_sha256
                )
                assert first.archive_known_at == second.archive_known_at
                return first

        archive = ConcurrentFirstArchive()
        if plan22_start_offset is None:
            trusted_clock: Any = Clock(
                [screen_test._CUTOFF - timedelta(minutes=5)]
                + [screen_test._CUTOFF - timedelta(minutes=2)]
                * trusted_clock_pre_cutoff_count
                + [screen_test._CUTOFF - timedelta(seconds=30)]
                + [screen_test._CUTOFF] * 32
            )
        else:

            @dataclass
            class Plan22DeadlineClock:
                first: bool = True

                def now(self) -> datetime:
                    if self.first:
                        self.first = False
                        return screen_test._CUTOFF - timedelta(minutes=5)
                    if "screen" in effects:
                        return (
                            screen_test._CUTOFF
                            - timedelta(seconds=30)
                            + plan22_start_offset
                        )
                    return screen_test._CUTOFF - timedelta(minutes=2)

            trusted_clock = Plan22DeadlineClock()
        result = (
            module.acquire_build_and_retain_current_supplied_cohort_market_regime_v3(
                request,
                scenario.schedule_store,
                recording_raw,
                recording_resolver,
                provider,
                archive,
                scenario.lease,
                clock=trusted_clock,
            )
        )
        if expect_archive_failure:
            assert type(result) is module.CurrentSamePassArchiveFailureV1
            assert provider.calls == expected_plan22_calls
            assert tuple(effects) == expected_effects
            if capture is not None:
                capture["candidate"] = archive.candidate
                capture["retained"] = result
            return

        assert type(result) is module.RetainedCurrentSamePassMarketContextV3
        private_context = archive.candidate.context_object
        if capture is not None:
            capture["candidate"] = archive.candidate
            capture["retained"] = result
        raw_result = private_context.raw_result
        assert module._raw_result_is_authoritative(
            raw_result, request, raw_result.resolved_sessions
        )
        first = raw_result.resolved_sessions[0]
        forged_first = raw_test.CurrentSamePassRawSessionV1(
            first.position,
            first.session,
            first.open_at - timedelta(microseconds=1),
            first.close_at - timedelta(microseconds=1),
            first.kind,
        )
        forged_sessions = (forged_first, *raw_result.resolved_sessions[1:])
        forged = raw_test._rehashed(
            type(raw_result),
            raw_result,
            "raw_result_identity_sha256",
            evidence_state="INSUFFICIENT_EVIDENCE",
            resolved_sessions=forged_sessions,
            raw_grid=None,
            reasons=("RAW_ACQUISITION_UNAVAILABLE",),
        )
        assert raw_test.raw_daily.current_same_pass_raw_daily_result_is_exact_valid_v1(
            forged, request
        )
        assert not module._raw_result_is_authoritative(
            forged, request, raw_result.resolved_sessions
        )
        handoff = private_context.adjusted_handoff
        if expected_plan22_calls:
            assert handoff is not None, private_context.adjusted_failure
            assert private_context.adjusted_failure is None
            assert private_context.adjusted_not_attempted is None
            assert module._adjusted_handoff_is_exact(
                handoff,
                request,
                tuple(private_context.raw_result.raw_grid.sessions),
            )
        else:
            assert handoff is None
            assert private_context.adjusted_failure is None
            not_attempted = private_context.adjusted_not_attempted
            assert not_attempted is not None
            assert not_attempted.contract_version == (
                "current-same-pass-adjusted-daily-close-not-attempted@v1"
            )
            assert not_attempted.evidence_state == "NOT_ATTEMPTED"
            assert not_attempted.reason == "UPSTREAM_INSUFFICIENT_EVIDENCE"
            adjusted_ledger = private_context.component_ledger[2]
            assert adjusted_ledger.evidence_state == "NOT_ATTEMPTED"
            assert adjusted_ledger.primary_identity_sha256 == (
                not_attempted.not_attempted_projection_identity_sha256
            )
            assert adjusted_ledger.known_at is None
            assert adjusted_ledger.reasons == ("UPSTREAM_INSUFFICIENT_EVIDENCE",)
            forged_core = {
                "contract_version": not_attempted.contract_version,
                "plan22_request_identity_sha256": (
                    not_attempted.plan22_request_identity_sha256
                ),
                "evidence_state": "PROVIDER_FAILURE",
                "reason": not_attempted.reason,
            }
            forged_not_attempted = type(not_attempted)(
                **forged_core,
                not_attempted_projection_identity_sha256=module._identity(forged_core),
            )
            assert not module._adjusted_not_attempted_is_exact(
                forged_not_attempted, request
            )
            with pytest.raises(TypeError, match="adjusted composition invalid"):
                module._context_object(
                    request,
                    private_context.raw_result,
                    private_context.corporate_action_screen,
                    module._CurrentSamePassAdjustedNotAttemptedV1(
                        None, None, forged_not_attempted
                    ),
                )
        observed_expected_state = expected_state or (
            "OBSERVED"
            if raw_evidence_factory is None and screen_retain
            else "INSUFFICIENT_EVIDENCE"
        )
        assert result.market_regime_report.evidence_state == observed_expected_state, (
            result.market_regime_report.reasons,
            provider.calls,
        )
        if observed_expected_state == "INSUFFICIENT_EVIDENCE" and (
            raw_directions is not None
        ):
            assert result.market_regime_report.reasons == (
                "RAW_ADJUSTED_DIRECTION_CONFLICT",
            )
        if expected_breadth is not None:
            regime, advances, declines, unchanged = expected_breadth
            assert result.market_regime_report.regime == regime
            assert result.market_regime_report.advances == advances
            assert result.market_regime_report.declines == declines
            assert result.market_regime_report.unchanged == unchanged
        assert provider.calls == expected_plan22_calls
        assert tuple(effects) == expected_effects
        assert module.validate_retained_current_same_pass_market_context_v3(result)
        archive_directory = scenario.root / ".current-same-pass-market-regime-v3"
        assert sorted(path.name for path in archive_directory.iterdir()) == [
            f"admissible-{result.context_identity_sha256}.json",
            f"completion-{result.context_identity_sha256}.json",
            f"context-{result.context_identity_sha256}.json",
            f"pending-{result.context_identity_sha256}.json",
            f"retained-{result.context_identity_sha256}.json",
        ]
        if not exercise_archive_contracts:
            return
        retried = (
            module.acquire_build_and_retain_current_supplied_cohort_market_regime_v3(
                request,
                scenario.schedule_store,
                raw,
                resolver,
                provider,
                module.FileCurrentSamePassMarketContextArchiveV1(
                    scenario.root,
                    clock=Clock(
                        [screen_test._CUTOFF - timedelta(seconds=30)]
                        + [screen_test._CUTOFF] * 32
                    ),
                ),
                scenario.lease,
                clock=Clock(
                    [screen_test._CUTOFF - timedelta(minutes=5)]
                    + [screen_test._CUTOFF - timedelta(minutes=2)]
                    * trusted_clock_pre_cutoff_count
                    + [screen_test._CUTOFF - timedelta(seconds=30)]
                    + [screen_test._CUTOFF] * 32
                ),
            )
        )
        assert type(retried) is module.RetainedCurrentSamePassMarketContextV3
        assert module.validate_retained_current_same_pass_market_context_v3(retried)
        assert (
            retried.retained_context_identity_sha256
            == result.retained_context_identity_sha256
        )
        assert retried.archive_known_at == result.archive_known_at
        candidate = archive.candidate
        assert module._candidate_is_exact(request, candidate)

        def archive_with_fresh_lease(
            name: str, *, times: list[datetime] | None = None
        ) -> tuple[Path, StorageRootLease, Any]:
            root = tmp_path / name
            root.mkdir(mode=0o700)
            acquired = StorageRootLease.try_acquire(root)
            assert acquired.lease is not None
            return (
                root,
                acquired.lease,
                module.FileCurrentSamePassMarketContextArchiveV1(
                    root,
                    clock=Clock(
                        times
                        or [screen_test._CUTOFF - timedelta(seconds=30)]
                        + [screen_test._CUTOFF] * 16
                    ),
                ),
            )

        def archived_paths(root: Path) -> tuple[Path, Path]:
            archive_root = root / ".current-same-pass-market-regime-v3"
            stem = result.context_identity_sha256
            return (
                archive_root / f"retained-{stem}.json",
                archive_root / f"completion-{stem}.json",
            )

        def seed_archive(
            root: Path, lease: StorageRootLease, file_archive: Any
        ) -> None:
            seeded = file_archive.archive_exact(request, candidate, lease)
            assert type(seeded) is module.RetainedCurrentSamePassMarketContextV3

        def assert_mutation_fails(
            name: str, mutate: Any, *, times: list[datetime] | None = None
        ) -> None:
            root, lease, file_archive = archive_with_fresh_lease(name, times=times)
            try:
                seed_archive(root, lease, file_archive)
                receipt_path, marker_path = archived_paths(root)
                mutate(receipt_path, marker_path)
                failed = file_archive.archive_exact(request, candidate, lease)
                assert type(failed) is module.CurrentSamePassArchiveFailureV1
                assert type(failed) is not module.RetainedCurrentSamePassMarketContextV3
            finally:
                lease.close()

        def corrupt(path: Path) -> None:
            path.write_bytes(b"{")

        def add_unknown(path: Path) -> None:
            value = json.loads(path.read_bytes())
            value["unknown"] = "rejected"
            path.write_bytes(module._canonical(value))

        def splice_receipt(path: Path) -> None:
            value = json.loads(path.read_bytes())
            value["context_identity_sha256"] = "0" * 64
            core = {
                name: value[name]
                for name in _RECEIPT_FIELDS
                if name != "context_receipt_identity_sha256"
            }
            value["context_receipt_identity_sha256"] = module._identity(core)
            path.write_bytes(module._canonical(value))

        def splice_marker(path: Path) -> None:
            value = json.loads(path.read_bytes())
            value["context_identity_sha256"] = "0" * 64
            core = {
                name: value[name]
                for name in _MARKER_FIELDS
                if name != "completion_marker_identity_sha256"
            }
            value["completion_marker_identity_sha256"] = module._identity(core)
            path.write_bytes(module._canonical(value))

        assert_mutation_fails(
            "interrupted",
            lambda _receipt, marker: marker.unlink(),
        )
        assert_mutation_fails(
            "corrupt-receipt", lambda receipt, _marker: corrupt(receipt)
        )
        assert_mutation_fails(
            "unknown-receipt", lambda receipt, _marker: add_unknown(receipt)
        )
        assert_mutation_fails(
            "spliced-receipt", lambda receipt, _marker: splice_receipt(receipt)
        )
        assert_mutation_fails(
            "corrupt-marker", lambda _receipt, marker: corrupt(marker)
        )
        assert_mutation_fails(
            "unknown-marker", lambda _receipt, marker: add_unknown(marker)
        )
        assert_mutation_fails(
            "spliced-marker", lambda _receipt, marker: splice_marker(marker)
        )

        root, lease, file_archive = archive_with_fresh_lease(
            "late-marker",
            times=[
                screen_test._CUTOFF - timedelta(seconds=30),
                screen_test._CUTOFF - timedelta(microseconds=1),
                screen_test._CUTOFF + timedelta(microseconds=1),
            ],
        )
        try:
            late = file_archive.archive_exact(request, candidate, lease)
            assert type(late) is module.CurrentSamePassArchiveFailureV1
            _receipt_path, marker_path = archived_paths(root)
            assert not marker_path.exists()
        finally:
            lease.close()

        root, lease, file_archive = archive_with_fresh_lease("lease-loss")
        original_publish = module._publish_exact

        def lose_lease_before_marker(
            parent: int, name: str, raw: bytes, maximum: int
        ) -> None:
            if name.startswith("completion-"):
                lease.close()
            original_publish(parent, name, raw, maximum)

        try:
            with monkeypatch.context() as context:
                context.setattr(module, "_publish_exact", lose_lease_before_marker)
                lost = file_archive.archive_exact(request, candidate, lease)
            assert type(lost) is module.CurrentSamePassArchiveFailureV1
            _receipt_path, marker_path = archived_paths(root)
            assert not marker_path.exists()
        finally:
            lease.close()

        root, lease, file_archive = archive_with_fresh_lease("detached-root")
        original_publish = module._publish_exact

        def detach_before_marker(
            parent: int, name: str, raw: bytes, maximum: int
        ) -> None:
            if name.startswith("completion-"):
                archive_root = root / ".current-same-pass-market-regime-v3"
                archive_root.rename(root / "detached-archive")
            original_publish(parent, name, raw, maximum)

        try:
            with monkeypatch.context() as context:
                context.setattr(module, "_publish_exact", detach_before_marker)
                detached = file_archive.archive_exact(request, candidate, lease)
            assert type(detached) is module.CurrentSamePassArchiveFailureV1
            assert not (
                root
                / ".current-same-pass-market-regime-v3"
                / f"completion-{result.context_identity_sha256}.json"
            ).exists()
        finally:
            lease.close()

        def clone_dataclass(value: Any) -> Any:
            clone = object.__new__(type(value))
            for item in fields(value):
                object.__setattr__(clone, item.name, getattr(value, item.name))
            return clone

        forged_candidate = clone_dataclass(candidate)
        forged_candidate_seal = object.__new__(type(candidate._seal))
        object.__setattr__(forged_candidate, "_seal", forged_candidate_seal)
        assert (
            module._candidate_exactness_failure(request, forged_candidate)
            == "CANDIDATE_SEAL_UNMINTED"
        )
        assert not module._candidate_is_exact(request, forged_candidate)

        root, lease, file_archive = archive_with_fresh_lease("forged-candidate")
        try:
            rejected_candidate = file_archive.archive_exact(
                request, forged_candidate, lease
            )
            assert type(rejected_candidate) is module.CurrentSamePassArchiveFailureV1
        finally:
            lease.close()

        forged_retained = clone_dataclass(result)
        forged_retained_seal = object.__new__(type(result._archive_seal))
        object.__setattr__(forged_retained, "_archive_seal", forged_retained_seal)
        assert not module.validate_retained_current_same_pass_market_context_v3(
            forged_retained
        )
        assert all(
            not hasattr(result._archive_seal, name)
            for name in (
                "candidate",
                "classification",
                "context",
                "event",
                "marker",
                "raw",
                "receipt",
                "root",
                "token",
            )
        )

        def assert_delegate_mutation_rejected(member: str, mutation: str) -> None:
            class DelegateThenMutateArchive:
                saved: tuple[Path, bytes, int] | None = None
                extra: tuple[Path, bytes, int] | None = None

                def archive_exact(
                    self,
                    archive_request: Any,
                    archive_candidate: Any,
                    lease: Any,
                    *,
                    trusted_clock: Any = None,
                ) -> Any:
                    delegated = module.FileCurrentSamePassMarketContextArchiveV1(
                        scenario.root,
                        clock=Clock(
                            [screen_test._CUTOFF - timedelta(seconds=30)]
                            + [screen_test._CUTOFF] * 16
                        ),
                    ).archive_exact(
                        archive_request,
                        archive_candidate,
                        lease,
                        trusted_clock=trusted_clock,
                    )
                    assert (
                        type(delegated) is module.RetainedCurrentSamePassMarketContextV3
                    )
                    archive_root = scenario.root / ".current-same-pass-market-regime-v3"
                    stem = delegated.context_identity_sha256
                    path = {
                        "context": archive_root / f"context-{stem}.json",
                        "receipt": archive_root / f"retained-{stem}.json",
                        "marker": archive_root / f"completion-{stem}.json",
                    }[member]
                    self.saved = (path, path.read_bytes(), path.stat().st_mode)
                    if mutation == "replace":
                        path.unlink()
                        path.write_bytes(self.saved[1])
                        path.chmod(self.saved[2])
                    elif mutation == "same_inode_rewrite":
                        with path.open("r+b") as reopened:
                            assert reopened.write(self.saved[1]) == len(self.saved[1])
                            reopened.flush()
                    elif mutation == "zero":
                        path.write_bytes(b"")
                    elif mutation == "fabricated_time":
                        receipt_path = archive_root / f"retained-{stem}.json"
                        marker_path = archive_root / f"completion-{stem}.json"
                        self.extra = (
                            marker_path,
                            marker_path.read_bytes(),
                            marker_path.stat().st_mode,
                        )
                        receipt_value = json.loads(receipt_path.read_bytes())
                        receipt_value["archive_known_at"] = module._instant(
                            screen_test._CUTOFF - timedelta(minutes=1)
                        )
                        receipt_core = {
                            key: receipt_value[key]
                            for key in _RECEIPT_FIELDS
                            if key != "context_receipt_identity_sha256"
                        }
                        receipt_value["context_receipt_identity_sha256"] = (
                            module._identity(receipt_core)
                        )
                        receipt_raw = module._canonical(receipt_value)
                        marker_value = json.loads(marker_path.read_bytes())
                        marker_value["archive_known_at"] = receipt_value[
                            "archive_known_at"
                        ]
                        marker_value["context_receipt_identity_sha256"] = receipt_value[
                            "context_receipt_identity_sha256"
                        ]
                        marker_value["receipt_sha256"] = module._sha(receipt_raw)
                        marker_core = {
                            key: marker_value[key]
                            for key in _MARKER_FIELDS
                            if key != "completion_marker_identity_sha256"
                        }
                        marker_value["completion_marker_identity_sha256"] = (
                            module._identity(marker_core)
                        )
                        receipt_path.write_bytes(receipt_raw)
                        marker_path.write_bytes(module._canonical(marker_value))
                    else:
                        path.chmod(0o640)
                    return delegated

            archive = DelegateThenMutateArchive()
            try:
                with pytest.raises(ValueError, match="unsealed same-pass context"):
                    module.acquire_build_and_retain_current_supplied_cohort_market_regime_v3(
                        request,
                        scenario.schedule_store,
                        raw,
                        resolver,
                        provider,
                        archive,
                        scenario.lease,
                        clock=Clock(
                            [screen_test._CUTOFF - timedelta(minutes=5)]
                            + [screen_test._CUTOFF - timedelta(minutes=2)] * 16
                            + [screen_test._CUTOFF - timedelta(seconds=30)]
                            + [screen_test._CUTOFF] * 16
                        ),
                    )
            finally:
                assert archive.saved is not None
                archive.saved[0].write_bytes(archive.saved[1])
                archive.saved[0].chmod(archive.saved[2])
                if archive.extra is not None:
                    archive.extra[0].write_bytes(archive.extra[1])
                    archive.extra[0].chmod(archive.extra[2])

        if exercise_post_return_adversaries:
            for member in ("context", "receipt", "marker"):
                for mutation in ("replace", "same_inode_rewrite", "chmod"):
                    assert_delegate_mutation_rejected(member, mutation)
            for member in ("receipt", "marker"):
                assert_delegate_mutation_rejected(member, "zero")
            assert_delegate_mutation_rejected("receipt", "fabricated_time")

            unrelated_root = tmp_path / "unrelated-archive-root"
            unrelated_root.mkdir(mode=0o700)
            unrelated_acquired = StorageRootLease.try_acquire(unrelated_root)
            assert unrelated_acquired.lease is not None

            class DelegateUnderUnrelatedRoot:
                def archive_exact(
                    self,
                    archive_request: Any,
                    archive_candidate: Any,
                    _lease: Any,
                    *,
                    trusted_clock: Any = None,
                ) -> Any:
                    return module.FileCurrentSamePassMarketContextArchiveV1(
                        unrelated_root,
                        clock=Clock(
                            [screen_test._CUTOFF - timedelta(seconds=30)]
                            + [screen_test._CUTOFF] * 16
                        ),
                    ).archive_exact(
                        archive_request, archive_candidate, unrelated_acquired.lease
                    )

            try:
                with pytest.raises(ValueError, match="unsealed same-pass context"):
                    module.acquire_build_and_retain_current_supplied_cohort_market_regime_v3(
                        request,
                        scenario.schedule_store,
                        raw,
                        resolver,
                        provider,
                        DelegateUnderUnrelatedRoot(),
                        scenario.lease,
                        clock=Clock(
                            [screen_test._CUTOFF - timedelta(minutes=5)]
                            + [screen_test._CUTOFF - timedelta(minutes=2)] * 16
                        ),
                    )
            finally:
                unrelated_acquired.lease.close()

            @dataclass
            class FutureOuterClock:
                first: bool = True
                archive_returned: bool = False

                def now(self) -> datetime:
                    if self.first:
                        self.first = False
                        return screen_test._CUTOFF - timedelta(minutes=5)
                    return screen_test._CUTOFF - timedelta(
                        seconds=1 if self.archive_returned else 31
                    )

            outer_clock = FutureOuterClock()

            class FutureCompleteDelegate:
                def __init__(self) -> None:
                    self.archive = module.FileCurrentSamePassMarketContextArchiveV1(
                        scenario.root,
                        clock=Clock(
                            [screen_test._CUTOFF - timedelta(seconds=30)]
                            + [screen_test._CUTOFF] * 16
                        ),
                    )

                def archive_exact(
                    self,
                    archive_request: Any,
                    archive_candidate: Any,
                    lease: Any,
                    *,
                    trusted_clock: Any = None,
                ) -> Any:
                    value = self.archive.archive_exact(
                        archive_request, archive_candidate, lease
                    )
                    assert type(value) is module.RetainedCurrentSamePassMarketContextV3
                    assert value.archive_known_at == screen_test._CUTOFF
                    self.value = value
                    outer_clock.archive_returned = True
                    return value

            future_delegate = FutureCompleteDelegate()
            with pytest.raises(ValueError, match="unsealed same-pass context"):
                module.acquire_build_and_retain_current_supplied_cohort_market_regime_v3(
                    request,
                    scenario.schedule_store,
                    raw,
                    resolver,
                    provider,
                    future_delegate,
                    scenario.lease,
                    clock=outer_clock,
                )
            future_stem = scenario.root / ".current-same-pass-market-regime-v3"
            assert all(
                (future_stem / name).is_file()
                for name in (
                    f"completion-{future_delegate.value.context_identity_sha256}.json",
                    f"context-{future_delegate.value.context_identity_sha256}.json",
                    f"retained-{future_delegate.value.context_identity_sha256}.json",
                )
            )

            archive_root = scenario.root / ".current-same-pass-market-regime-v3"
            for path in archive_root.iterdir():
                path.unlink()

            class BackdatedCompleteDelegate:
                def __init__(self) -> None:
                    self.archive_clock = Clock(
                        [screen_test._CUTOFF - timedelta(minutes=10)] * 3
                        + [screen_test._CUTOFF - timedelta(minutes=9)] * 8
                    )
                    self.archive = module.FileCurrentSamePassMarketContextArchiveV1(
                        scenario.root,
                        clock=self.archive_clock,
                    )

                def archive_exact(
                    self,
                    archive_request: Any,
                    archive_candidate: Any,
                    lease: Any,
                    *,
                    trusted_clock: Any = None,
                ) -> Any:
                    del trusted_clock
                    self.value = self.archive.archive_exact(
                        archive_request,
                        archive_candidate,
                        lease,
                    )
                    return self.value

            backdated_delegate = BackdatedCompleteDelegate()
            with pytest.raises(ValueError, match="unsealed same-pass context"):
                module.acquire_build_and_retain_current_supplied_cohort_market_regime_v3(
                    request,
                    scenario.schedule_store,
                    raw,
                    resolver,
                    provider,
                    backdated_delegate,
                    scenario.lease,
                    clock=Clock(
                        [screen_test._CUTOFF - timedelta(minutes=5)]
                        + [screen_test._CUTOFF - timedelta(minutes=2)] * 16
                    ),
                )
            assert (
                type(backdated_delegate.value)
                is module.RetainedCurrentSamePassMarketContextV3
            )
            assert backdated_delegate.value.archive_known_at == (
                screen_test._CUTOFF - timedelta(minutes=9, seconds=30)
            )
            assert sorted(path.name for path in archive_root.iterdir()) == [
                f"admissible-{backdated_delegate.value.context_identity_sha256}.json",
                f"completion-{backdated_delegate.value.context_identity_sha256}.json",
                f"context-{backdated_delegate.value.context_identity_sha256}.json",
                f"pending-{backdated_delegate.value.context_identity_sha256}.json",
                f"retained-{backdated_delegate.value.context_identity_sha256}.json",
            ]

            class PrivateContextArchive:
                def archive_exact(
                    self,
                    _archive_request: Any,
                    archive_candidate: Any,
                    _lease: Any,
                    *,
                    trusted_clock: Any = None,
                ) -> object:
                    del trusted_clock
                    return archive_candidate.context_object

            with pytest.raises(TypeError, match="invalid archive result"):
                module.acquire_build_and_retain_current_supplied_cohort_market_regime_v3(
                    request,
                    scenario.schedule_store,
                    raw,
                    resolver,
                    provider,
                    PrivateContextArchive(),
                    scenario.lease,
                    clock=Clock(
                        [screen_test._CUTOFF - timedelta(minutes=5)]
                        + [screen_test._CUTOFF - timedelta(minutes=2)] * 16
                    ),
                )

            class MalformedFailureArchive:
                def archive_exact(
                    self,
                    archive_request: Any,
                    archive_candidate: Any,
                    _lease: Any,
                    *,
                    trusted_clock: Any = None,
                ) -> object:
                    del trusted_clock
                    failure = module._failure(
                        archive_request,
                        archive_candidate.context_object.context_identity_sha256,
                    )
                    object.__setattr__(
                        failure, "archive_failure_identity_sha256", "0" * 64
                    )
                    return failure

            with pytest.raises(ValueError, match="invalid same-pass archive failure"):
                module.acquire_build_and_retain_current_supplied_cohort_market_regime_v3(
                    request,
                    scenario.schedule_store,
                    raw,
                    resolver,
                    provider,
                    MalformedFailureArchive(),
                    scenario.lease,
                    clock=Clock(
                        [screen_test._CUTOFF - timedelta(minutes=5)]
                        + [screen_test._CUTOFF - timedelta(minutes=2)] * 16
                    ),
                )

        class PriorRetainedArchive:
            def archive_exact(self, *_: object, **__: object) -> object:
                return result

        with pytest.raises(ValueError, match="unsealed same-pass context"):
            module.acquire_build_and_retain_current_supplied_cohort_market_regime_v3(
                request,
                scenario.schedule_store,
                raw,
                resolver,
                provider,
                PriorRetainedArchive(),
                scenario.lease,
                clock=Clock(
                    [screen_test._CUTOFF - timedelta(minutes=5)]
                    + [screen_test._CUTOFF - timedelta(minutes=2)] * 16
                ),
            )
    finally:
        raw_test._CUTOFF = original_cutoff
        scenario.close()


@pytest.mark.parametrize(
    "plan22_start_offset",
    (timedelta(0), timedelta(microseconds=1)),
)
def test_v3_rejects_expired_effect_deadline_before_plan22_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    plan22_start_offset: timedelta,
) -> None:
    test_outer_composition_retains_real_context_and_archive_files(
        tmp_path,
        monkeypatch,
        plan22_start_offset=plan22_start_offset,
        exercise_archive_contracts=False,
        expected_plan22_calls=0,
        expected_effects=("raw-mapping", "screen"),
        expect_archive_failure=True,
    )


def test_public_composition_skips_plan22_after_insufficient_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_outer_composition_retains_real_context_and_archive_files(
        tmp_path,
        monkeypatch,
        screen_retain=False,
        expected_plan22_calls=0,
        expected_effects=("raw-mapping", "screen"),
        expected_state="INSUFFICIENT_EVIDENCE",
        trusted_clock_pre_cutoff_count=3,
        exercise_archive_contracts=False,
    )


def test_public_composition_skips_plan22_after_raw_mapping_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing_mapping(raw_test: Any) -> object:
        class MissingMappingEvidence(raw_test._TemporaryRetainedEvidence):
            def mappings_under_lease(self, *_: object) -> object:
                return "RAW_MAPPING_MISSING"

        return MissingMappingEvidence()

    test_outer_composition_retains_real_context_and_archive_files(
        tmp_path,
        monkeypatch,
        raw_evidence_factory=missing_mapping,
        expected_plan22_calls=0,
        expected_effects=("raw-mapping", "screen"),
        exercise_archive_contracts=False,
    )


def test_v3_outer_adoption_rejects_post_return_archive_adversaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_outer_composition_retains_real_context_and_archive_files(
        tmp_path, monkeypatch, exercise_post_return_adversaries=True
    )


@pytest.mark.parametrize("cleanup_failure", ("unlink", "fsync"))
def test_v3_late_marker_guard_survives_cleanup_failure_and_blocks_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_failure: str,
) -> None:
    module = _v3()
    captured: dict[str, Any] = {}
    test_outer_composition_retains_real_context_and_archive_files(
        tmp_path,
        monkeypatch,
        exercise_archive_contracts=False,
        capture=captured,
    )
    candidate = captured["candidate"]
    request = candidate.context_object.request
    root = tmp_path / f"late-context-{cleanup_failure}"
    root.mkdir(mode=0o700)
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
                request,
                candidate,
                acquired.lease,
                trusted_clock=first_clock,
            )
        assert type(first) is module.CurrentSamePassArchiveFailureV1
        stem = candidate.context_object.context_identity_sha256
        archive_root = root / ".current-same-pass-market-regime-v3"
        assert (archive_root / f"pending-{stem}.json").is_file()
        assert not (archive_root / f"admissible-{stem}.json").exists()
        retry_clock = Clock([request.decision_cutoff + timedelta(seconds=1)])
        retry = module._FileCurrentSamePassMarketContextArchiveV1(
            root, clock=retry_clock
        ).archive_exact(
            request,
            candidate,
            acquired.lease,
            trusted_clock=retry_clock,
        )
        assert type(retry) is module.CurrentSamePassArchiveFailureV1
    finally:
        acquired.lease.close()


def test_v3_crash_after_admissibility_guard_retries_with_original_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _v3()
    captured: dict[str, Any] = {}
    test_outer_composition_retains_real_context_and_archive_files(
        tmp_path,
        monkeypatch,
        exercise_archive_contracts=False,
        capture=captured,
    )
    candidate = captured["candidate"]
    request = candidate.context_object.request
    root = tmp_path / "crashed-context"
    root.mkdir(mode=0o700)
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
    original_parse = module._parse_context_archive_records
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
            ).archive_exact(
                request,
                candidate,
                acquired.lease,
                trusted_clock=clock,
            )
        assert type(interrupted) is module.CurrentSamePassArchiveFailureV1
        retry_clock = Clock([request.decision_cutoff])
        retry = module._FileCurrentSamePassMarketContextArchiveV1(
            root, clock=retry_clock
        ).archive_exact(
            request,
            candidate,
            acquired.lease,
            trusted_clock=retry_clock,
        )
        assert type(retry) is module.RetainedCurrentSamePassMarketContextV3
        assert retry.archive_known_at == request.decision_cutoff
        assert original_parse is module._parse_context_archive_records
    finally:
        acquired.lease.close()
