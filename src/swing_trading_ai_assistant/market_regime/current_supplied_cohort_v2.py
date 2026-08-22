"""Pure V2 comparability gate for current supplied-cohort Market Regime."""

from __future__ import annotations

import hashlib
import importlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final, Literal, cast

from swing_trading_ai_assistant.market_data.adjusted_daily import (
    AdjustedCloseFact,
    AdjustedDailyCloseHandoffV2,
    AdjustedDailyMemberFactsV2,
    adjusted_daily_close_handoff_identity_v2,
    adjusted_daily_request_identity_v2,
    adjusted_daily_schedule_identity_v2,
    mapping_identity_v2,
)
from swing_trading_ai_assistant.market_data.current_corporate_action_screen import (
    PublishedCurrentCorporateActionScreenV1,
    published_current_corporate_action_screen_is_exact_valid_v1,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)

from .current_supplied_cohort import (
    CurrentCohortMemberV1,
    CurrentSuppliedCohortMarketRegimeReportV1,
    PrivateCurrentCohortArchiveGridProjectionV1,
    PrivateCurrentCohortMemberCloseProjectionV1,
)

CONTRACT_VERSION: Final = "current-supplied-cohort-market-regime@v2"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_RUNTIME_MANIFEST_MODULE: Final = (
    "swing_trading_ai_assistant.market_regime."
    "current_supplied_cohort_v2_runtime_identity_manifest"
)
_RUNTIME_MANIFEST: Final = (
    "src/swing_trading_ai_assistant/market_regime/"
    "current_supplied_cohort_v2_runtime_identity_manifest.py"
)
_RUNTIME_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/adjusted_daily/__init__.py",
    "src/swing_trading_ai_assistant/market_data/adjusted_daily/service.py",
    "src/swing_trading_ai_assistant/market_data/current_cohort.py",
    "src/swing_trading_ai_assistant/market_data/current_corporate_action_screen.py",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py",
    "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort.py",
    "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_v2.py",
)

_DIRECTION_SEAL: Final = object()
_HANDOFF_SEAL: Final = object()


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )


def _identity(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


SCHEMA_IDENTITY_SHA256: Final = _identity(
    {
        "contract_version": CONTRACT_VERSION,
        "report_fields": [
            "schema_identity_sha256",
            "calculation_identity_sha256",
            "runtime_code_identity_sha256",
            "raw_report_identity_sha256",
            "corporate_action_screen_identity_sha256",
            "adjusted_handoff_identity_sha256",
            "cohort_identity_sha256",
            "cohort_size",
            "decision_cutoff",
            "decision_session",
            "comparison_session",
            "evidence_state",
            "regime_label",
            "advances",
            "declines",
            "unchanged",
            "reasons",
            "report_identity_sha256",
        ],
    }
)
CALCULATION_IDENTITY_SHA256: Final = _identity(
    {
        "contract_version": CONTRACT_VERSION,
        "directions": ["UP", "DOWN", "FLAT"],
        "required_evidence": [
            "exact_raw_v1_grid",
            "sealed_published_plan21_screen",
            "exact_adjusted_handoff",
        ],
        "outcomes": ["OBSERVED", "INSUFFICIENT_EVIDENCE"],
    }
)


def _runtime_root() -> Path:
    source = Path(__file__)
    root = source.parent.parent
    if not source.is_absolute() or root.name != "swing_trading_ai_assistant":
        raise ValueError("V2 runtime identity invalid")
    return root


def _runtime_source_sha256(module_name: str, relative: str) -> str:
    try:
        return runtime_source_sha256(module_name, _runtime_root(), relative)
    except ValueError:
        raise ValueError("V2 runtime identity invalid") from None


def current_supplied_cohort_market_regime_runtime_code_identity_v2() -> str:
    """Verify reviewed source-at-rest identities; this is not byte attestation."""
    try:
        manifest = importlib.import_module(_RUNTIME_MANIFEST_MODULE)
        raw_mapping = (
            manifest.CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_SOURCE_DIGESTS_V2
        )
    except (AttributeError, ImportError):
        raise ValueError("V2 runtime identity invalid") from None
    if type(raw_mapping) is not dict:
        raise ValueError("V2 runtime identity invalid")
    mapping = cast(dict[str, object], raw_mapping)
    if tuple(mapping) != _RUNTIME_SOURCES or any(
        type(digest) is not str or _DIGEST.fullmatch(digest) is None
        for digest in mapping.values()
    ):
        raise ValueError("V2 runtime identity invalid")
    digests = cast(dict[str, str], mapping)
    loaded: dict[str, str] = {
        "src/swing_trading_ai_assistant/market_data/adjusted_daily/__init__.py": (
            "swing_trading_ai_assistant.market_data.adjusted_daily"
        ),
        "src/swing_trading_ai_assistant/market_data/adjusted_daily/service.py": (
            "swing_trading_ai_assistant.market_data.adjusted_daily.service"
        ),
        "src/swing_trading_ai_assistant/market_data/current_cohort.py": (
            "swing_trading_ai_assistant.market_data.current_cohort"
        ),
        "src/swing_trading_ai_assistant/market_data/current_corporate_action_screen.py": (
            "swing_trading_ai_assistant.market_data.current_corporate_action_screen"
        ),
        "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py": (
            "swing_trading_ai_assistant.market_data.runtime_source_verifier"
        ),
        "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort.py": (
            "swing_trading_ai_assistant.market_regime.current_supplied_cohort"
        ),
        "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_v2.py": (
            __name__
        ),
    }
    for relative in _RUNTIME_SOURCES:
        if _runtime_source_sha256(loaded[relative], relative) != digests[relative]:
            raise ValueError("V2 runtime identity invalid")
    manifest_digest = _runtime_source_sha256(
        _RUNTIME_MANIFEST_MODULE, _RUNTIME_MANIFEST
    )
    composite = b"".join(
        relative.encode() + b"\0" + digests[relative].encode() + b"\0"
        for relative in _RUNTIME_SOURCES
    )
    return hashlib.sha256(
        composite
        + _RUNTIME_MANIFEST.encode()
        + b"\0"
        + manifest_digest.encode()
        + b"\0"
    ).hexdigest()


_V2_RUNTIME_IDENTITY: Final = (
    current_supplied_cohort_market_regime_runtime_code_identity_v2()
)


@dataclass(frozen=True, slots=True, init=False)
class CurrentSuppliedCohortMarketRegimeReportV2:
    """Aggregate-only result with source-at-rest, not executed-byte, provenance."""

    contract_version: Literal["current-supplied-cohort-market-regime@v2"]
    schema_identity_sha256: str
    calculation_identity_sha256: str
    runtime_code_identity_sha256: str
    raw_report_identity_sha256: str
    corporate_action_screen_identity_sha256: str
    adjusted_handoff_identity_sha256: str
    cohort_identity_sha256: str
    cohort_size: int
    decision_cutoff: datetime
    decision_session: date
    comparison_session: date | None
    evidence_state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"]
    regime_label: str | None
    advances: int | None
    declines: int | None
    unchanged: int | None
    reasons: tuple[str, ...]
    report_identity_sha256: str

    def __init__(
        self,
        *,
        raw_report_identity_sha256: str,
        corporate_action_screen_identity_sha256: str,
        adjusted_handoff_identity_sha256: str,
        cohort_identity_sha256: str,
        cohort_size: int,
        decision_cutoff: datetime,
        decision_session: date,
        comparison_session: date | None,
        evidence_state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"],
        regime_label: str | None,
        advances: int | None,
        declines: int | None,
        unchanged: int | None,
        reasons: tuple[str, ...],
    ) -> None:
        object.__setattr__(self, "contract_version", CONTRACT_VERSION)
        object.__setattr__(self, "schema_identity_sha256", SCHEMA_IDENTITY_SHA256)
        object.__setattr__(
            self, "calculation_identity_sha256", CALCULATION_IDENTITY_SHA256
        )
        object.__setattr__(
            self,
            "runtime_code_identity_sha256",
            _V2_RUNTIME_IDENTITY,
        )
        object.__setattr__(
            self, "raw_report_identity_sha256", raw_report_identity_sha256
        )
        object.__setattr__(
            self,
            "corporate_action_screen_identity_sha256",
            corporate_action_screen_identity_sha256,
        )
        object.__setattr__(
            self, "adjusted_handoff_identity_sha256", adjusted_handoff_identity_sha256
        )
        object.__setattr__(self, "cohort_identity_sha256", cohort_identity_sha256)
        object.__setattr__(self, "cohort_size", cohort_size)
        object.__setattr__(self, "decision_cutoff", decision_cutoff)
        object.__setattr__(self, "decision_session", decision_session)
        object.__setattr__(self, "comparison_session", comparison_session)
        object.__setattr__(self, "evidence_state", evidence_state)
        object.__setattr__(self, "regime_label", regime_label)
        object.__setattr__(self, "advances", advances)
        object.__setattr__(self, "declines", declines)
        object.__setattr__(self, "unchanged", unchanged)
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(
            self,
            "report_identity_sha256",
            _identity(self.value(include_identity=False)),
        )

    def value(self, *, include_identity: bool = True) -> dict[str, object]:
        """Return the redacted, aggregate-only public representation."""
        result: dict[str, object] = {
            "adjusted_handoff_identity_sha256": self.adjusted_handoff_identity_sha256,
            "advances": self.advances,
            "calculation_identity_sha256": self.calculation_identity_sha256,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "cohort_size": self.cohort_size,
            "comparison_session": (
                None
                if self.comparison_session is None
                else self.comparison_session.isoformat()
            ),
            "contract_version": self.contract_version,
            "corporate_action_screen_identity_sha256": (
                self.corporate_action_screen_identity_sha256
            ),
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "decision_session": self.decision_session.isoformat(),
            "declines": self.declines,
            "evidence_state": self.evidence_state,
            "raw_report_identity_sha256": self.raw_report_identity_sha256,
            "reasons": list(self.reasons),
            "regime_label": self.regime_label,
            "runtime_code_identity_sha256": self.runtime_code_identity_sha256,
            "schema_identity_sha256": self.schema_identity_sha256,
            "unchanged": self.unchanged,
        }
        if include_identity:
            result["report_identity_sha256"] = self.report_identity_sha256
        return result


@dataclass(frozen=True, slots=True, init=False, repr=False)
class _CurrentSuppliedCohortMemberDirectionV2:
    isin: str
    exchange: str
    effective_symbol: str
    direction: Literal["ADVANCE", "DECLINE", "UNCHANGED"]
    _seal: object = field(repr=False, compare=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("private direction constructor unavailable")


@dataclass(frozen=True, slots=True, init=False, repr=False)
class _CurrentSuppliedCohortMemberDirectionHandoffV2:
    paired_report_identity_sha256: str
    raw_report_identity_sha256: str
    corporate_action_screen_identity_sha256: str
    adjusted_handoff_identity_sha256: str
    cohort_identity_sha256: str
    cohort_size: int
    decision_cutoff: datetime
    decision_session: date
    comparison_session: date
    members: tuple[_CurrentSuppliedCohortMemberDirectionV2, ...]
    handoff_identity_sha256: str
    _seal: object = field(repr=False, compare=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("private direction handoff constructor unavailable")


def _direction(**values: object) -> _CurrentSuppliedCohortMemberDirectionV2:
    result = object.__new__(_CurrentSuppliedCohortMemberDirectionV2)
    for name, value in values.items():
        object.__setattr__(result, name, value)
    object.__setattr__(result, "_seal", _DIRECTION_SEAL)
    return result


def _handoff(**values: object) -> _CurrentSuppliedCohortMemberDirectionHandoffV2:
    result = object.__new__(_CurrentSuppliedCohortMemberDirectionHandoffV2)
    for name, value in values.items():
        object.__setattr__(result, name, value)
    object.__setattr__(result, "_seal", _HANDOFF_SEAL)
    return result


def _member_direction_handoff(
    report: CurrentSuppliedCohortMarketRegimeReportV2,
    grid: PrivateCurrentCohortArchiveGridProjectionV1,
    adjusted_handoff: AdjustedDailyCloseHandoffV2,
) -> _CurrentSuppliedCohortMemberDirectionHandoffV2:
    if report.comparison_session is None:
        raise ValueError("V2 handoff invalid")
    adjusted_members = {member.isin: member for member in adjusted_handoff.members}
    members = tuple(
        _direction(
            isin=prior.member.isin,
            exchange=adjusted_members[prior.member.isin].exchange,
            effective_symbol=adjusted_members[prior.member.isin].effective_symbol,
            direction=(
                "ADVANCE"
                if current.close > prior.close
                else "DECLINE"
                if current.close < prior.close
                else "UNCHANGED"
            ),
        )
        for prior, current in sorted(
            zip(grid.sessions[0].members, grid.sessions[-1].members, strict=True),
            key=lambda pair: pair[0].member.isin,
        )
    )
    provisional = {
        "adjusted_handoff_identity_sha256": report.adjusted_handoff_identity_sha256,
        "cohort_identity_sha256": report.cohort_identity_sha256,
        "cohort_size": report.cohort_size,
        "comparison_session": report.comparison_session.isoformat(),
        "corporate_action_screen_identity_sha256": report.corporate_action_screen_identity_sha256,
        "decision_cutoff": report.decision_cutoff.isoformat(),
        "decision_session": report.decision_session.isoformat(),
        "members": [
            {
                "direction": member.direction,
                "effective_symbol": member.effective_symbol,
                "exchange": member.exchange,
                "isin": member.isin,
            }
            for member in members
        ],
        "paired_report_identity_sha256": report.report_identity_sha256,
        "raw_report_identity_sha256": report.raw_report_identity_sha256,
    }
    return _handoff(
        paired_report_identity_sha256=report.report_identity_sha256,
        raw_report_identity_sha256=report.raw_report_identity_sha256,
        corporate_action_screen_identity_sha256=report.corporate_action_screen_identity_sha256,
        adjusted_handoff_identity_sha256=report.adjusted_handoff_identity_sha256,
        cohort_identity_sha256=report.cohort_identity_sha256,
        cohort_size=report.cohort_size,
        decision_cutoff=report.decision_cutoff,
        decision_session=report.decision_session,
        comparison_session=report.comparison_session,
        members=members,
        handoff_identity_sha256=_identity(provisional),
    )


def evaluate_current_supplied_cohort_market_regime_v2(
    raw_v1_report: CurrentSuppliedCohortMarketRegimeReportV1,
    raw_private_grid: PrivateCurrentCohortArchiveGridProjectionV1,
    retained_screen: PublishedCurrentCorporateActionScreenV1,
    adjusted_handoff: AdjustedDailyCloseHandoffV2,
) -> CurrentSuppliedCohortMarketRegimeReportV2:
    """Return the Plan-20 aggregate report without exposing member directions."""
    return _evaluate_current_supplied_cohort_market_regime_with_handoff_v2(
        raw_v1_report,
        raw_private_grid,
        retained_screen,
        adjusted_handoff,
    )[0]


def _evaluate_current_supplied_cohort_market_regime_with_handoff_v2(
    raw_v1_report: CurrentSuppliedCohortMarketRegimeReportV1,
    raw_private_grid: PrivateCurrentCohortArchiveGridProjectionV1,
    retained_screen: PublishedCurrentCorporateActionScreenV1,
    adjusted_handoff: AdjustedDailyCloseHandoffV2,
) -> tuple[
    CurrentSuppliedCohortMarketRegimeReportV2,
    _CurrentSuppliedCohortMemberDirectionHandoffV2 | None,
]:
    """Evaluate V2 once and retain its directions only for same-pass consumers."""
    raw_identity = (
        raw_v1_report.report_identity_sha256
        if type(raw_v1_report) is CurrentSuppliedCohortMarketRegimeReportV1
        else ""
    )
    screen_identity = (
        retained_screen.private_result.private_result_identity_sha256
        if type(retained_screen) is PublishedCurrentCorporateActionScreenV1
        else ""
    )
    handoff_identity = (
        adjusted_handoff.handoff_identity_sha256
        if type(adjusted_handoff) is AdjustedDailyCloseHandoffV2
        else ""
    )
    if not _valid_raw_report_and_grid(raw_v1_report, raw_private_grid):
        return (
            _insufficient(
                raw_v1_report,
                raw_identity,
                screen_identity,
                handoff_identity,
                "RAW_V1_CLOSURE_INVALID",
            ),
            None,
        )
    if not _valid_screen(raw_v1_report, raw_private_grid, retained_screen):
        return (
            _insufficient(
                raw_v1_report,
                raw_identity,
                screen_identity,
                handoff_identity,
                "CORPORATE_ACTION_SCREEN_INSUFFICIENT",
            ),
            None,
        )
    if not _valid_adjusted_handoff(raw_v1_report, raw_private_grid, adjusted_handoff):
        return (
            _insufficient(
                raw_v1_report,
                raw_identity,
                screen_identity,
                handoff_identity,
                "ADJUSTED_DAILY_CLOSE_HANDOFF_INVALID",
            ),
            None,
        )
    raw_directions = _directions(
        raw_private_grid.sessions[0].members,
        raw_private_grid.sessions[-1].members,
    )
    adjusted_directions = _adjusted_directions(adjusted_handoff.members)
    if raw_directions != adjusted_directions:
        return (
            _insufficient(
                raw_v1_report,
                raw_identity,
                screen_identity,
                handoff_identity,
                "RAW_ADJUSTED_DIRECTION_CONFLICT",
            ),
            None,
        )
    report = CurrentSuppliedCohortMarketRegimeReportV2(
        raw_report_identity_sha256=raw_identity,
        corporate_action_screen_identity_sha256=screen_identity,
        adjusted_handoff_identity_sha256=handoff_identity,
        cohort_identity_sha256=raw_v1_report.cohort_identity_sha256,
        cohort_size=raw_v1_report.cohort_size,
        decision_cutoff=raw_v1_report.decision_cutoff,
        decision_session=raw_v1_report.decision_session,
        comparison_session=raw_v1_report.comparison_session,
        evidence_state="OBSERVED",
        regime_label=raw_v1_report.regime_label,
        advances=raw_v1_report.advances,
        declines=raw_v1_report.declines,
        unchanged=raw_v1_report.unchanged,
        reasons=(),
    )
    return report, _member_direction_handoff(report, raw_private_grid, adjusted_handoff)


def _insufficient(
    raw_report: object,
    raw_identity: str,
    screen_identity: str,
    handoff_identity: str,
    reason: str,
) -> CurrentSuppliedCohortMarketRegimeReportV2:
    """Build a whole-result failure with only a validated raw denominator."""
    if type(raw_report) is CurrentSuppliedCohortMarketRegimeReportV1:
        cohort_identity = raw_report.cohort_identity_sha256
        cohort_size = raw_report.cohort_size
        decision_cutoff = raw_report.decision_cutoff
        decision_session = raw_report.decision_session
    else:
        cohort_identity = ""
        cohort_size = 0
        decision_cutoff = datetime.min.replace(tzinfo=UTC)
        decision_session = date.min
    return CurrentSuppliedCohortMarketRegimeReportV2(
        raw_report_identity_sha256=raw_identity,
        corporate_action_screen_identity_sha256=screen_identity,
        adjusted_handoff_identity_sha256=handoff_identity,
        cohort_identity_sha256=cohort_identity,
        cohort_size=cohort_size,
        decision_cutoff=decision_cutoff,
        decision_session=decision_session,
        comparison_session=None,
        evidence_state="INSUFFICIENT_EVIDENCE",
        regime_label=None,
        advances=None,
        declines=None,
        unchanged=None,
        reasons=(reason,),
    )


def _valid_raw_report_and_grid(report: object, grid: object) -> bool:
    if (
        type(report) is not CurrentSuppliedCohortMarketRegimeReportV1
        or type(grid) is not PrivateCurrentCohortArchiveGridProjectionV1
        or report.contract_version != "current-supplied-cohort-market-regime@v1"
        or report.evidence_state != "OBSERVED"
        or report.reasons
        or report.comparison_session is None
        or report.regime_label
        not in {"BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"}
        or None in (report.advances, report.declines, report.unchanged)
        or grid.cohort_identity_sha256 != report.cohort_identity_sha256
        or grid.cohort_size != report.cohort_size
        or len(grid.sessions) != 21
        or grid.sessions[0].session != report.comparison_session
        or grid.sessions[-1].session != report.decision_session
        or tuple(session.session for session in grid.sessions)
        != tuple(sorted(session.session for session in grid.sessions))
        or len({session.session for session in grid.sessions}) != 21
        or tuple(session.archive_object_sha256 for session in grid.sessions)
        != report.archive_object_sha256s
        or any(
            session.request_identity_sha256 != report.request_identity_sha256
            or session.report_identity_sha256 != report.report_identity_sha256
            for session in grid.sessions
        )
    ):
        return False
    members = tuple(member.member for member in grid.sessions[0].members)
    if len(members) != report.cohort_size or len(set(members)) != report.cohort_size:
        return False
    if any(
        tuple(member.member for member in session.members) != members
        for session in grid.sessions
    ):
        return False
    directions = _directions(grid.sessions[0].members, grid.sessions[-1].members)
    advances = directions.count("UP")
    declines = directions.count("DOWN")
    unchanged = directions.count("FLAT")
    label = (
        "BROAD_ADVANCE"
        if advances * 5 >= report.cohort_size * 3
        else "BROAD_DECLINE"
        if declines * 5 >= report.cohort_size * 3
        else "MIXED_PARTICIPATION"
    )
    return (advances, declines, unchanged, label) == (
        report.advances,
        report.declines,
        report.unchanged,
        report.regime_label,
    )


def _valid_screen(
    report: CurrentSuppliedCohortMarketRegimeReportV1,
    grid: PrivateCurrentCohortArchiveGridProjectionV1,
    screen: object,
) -> bool:
    if report.comparison_session is None:
        return False
    return published_current_corporate_action_screen_is_exact_valid_v1(
        screen,
        cohort_identity_sha256=report.cohort_identity_sha256,
        comparison_session=report.comparison_session,
        decision_session=report.decision_session,
        decision_cutoff=report.decision_cutoff,
        schedule_evidence_sha256=report.schedule_evidence_sha256,
        schedule_source=report.schedule_source,
        schedule_source_release=report.schedule_source_release,
        expected_isins=tuple(member.member.isin for member in grid.sessions[0].members),
    )


def _valid_adjusted_handoff(
    report: CurrentSuppliedCohortMarketRegimeReportV1,
    grid: PrivateCurrentCohortArchiveGridProjectionV1,
    handoff: object,
) -> bool:
    if (
        report.comparison_session is None
        or type(handoff) is not AdjustedDailyCloseHandoffV2
    ):
        return False
    if (
        handoff.contract_version != "provider-neutral-adjusted-daily-close@v2"
        or handoff.provider_id != "YFINANCE"
        or handoff.price_basis != "ADJUSTED"
        or type(handoff.provider_source) is not str
        or not handoff.provider_source
        or handoff.temporal_label != "CURRENT_PROSPECTIVE"
        or handoff.cohort_identity_sha256 != report.cohort_identity_sha256
        or handoff.decision_cutoff != report.decision_cutoff
        or handoff.retrieved_at.tzinfo is not UTC
        or handoff.retrieved_at > report.decision_cutoff
        or handoff.schedule_evidence_sha256 != report.schedule_evidence_sha256
        or handoff.schedule_source != report.schedule_source
        or handoff.schedule_source_release != report.schedule_source_release
        or handoff.schedule_sessions
        != tuple(session.session for session in grid.sessions)
        or handoff.comparison_session != report.comparison_session
        or handoff.decision_session != report.decision_session
        or len(handoff.members) != report.cohort_size
        or not _is_aware(handoff.decision_session_official_close_at)
        or handoff.decision_session_official_close_at > report.decision_cutoff
        or handoff.schedule_identity_sha256
        != adjusted_daily_schedule_identity_v2(
            sessions=handoff.schedule_sessions,
            decision_session_official_close_at=handoff.decision_session_official_close_at,
            schedule_evidence_sha256=handoff.schedule_evidence_sha256,
            schedule_source=handoff.schedule_source,
            schedule_source_release=handoff.schedule_source_release,
        )
        or handoff.request_identity_sha256
        != adjusted_daily_request_identity_v2(
            cohort_identity_sha256=handoff.cohort_identity_sha256,
            decision_cutoff=handoff.decision_cutoff,
            schedule_identity_sha256=handoff.schedule_identity_sha256,
            members=handoff.members,
        )
        or handoff.handoff_identity_sha256
        != adjusted_daily_close_handoff_identity_v2(handoff)
    ):
        return False
    raw_members = {
        member.member.isin: member.member for member in grid.sessions[0].members
    }
    adjusted_members = handoff.members
    if tuple(member.isin for member in adjusted_members) != tuple(sorted(raw_members)):
        return False
    return all(
        _valid_adjusted_member(
            member,
            raw_members[member.isin],
            report.comparison_session,
            report.decision_session,
        )
        for member in adjusted_members
    )


def _valid_adjusted_member(
    member: AdjustedDailyMemberFactsV2,
    raw_member: CurrentCohortMemberV1,
    comparison_session: date,
    decision_session: date,
) -> bool:
    return not (
        type(member) is not AdjustedDailyMemberFactsV2
        or member.effective_symbol != raw_member.symbol
        or member.exchange not in {"NSE", "BSE"}
        or member.instrument_type != "EQUITY"
        or member.segment != "EQ"
        or member.mapping_version != "yfinance-symbol-mapping@v1"
        or member.mapping_identity
        != mapping_identity_v2(
            isin=member.isin,
            exchange=member.exchange,
            instrument_type=member.instrument_type,
            segment=member.segment,
            effective_symbol=member.effective_symbol,
            provider_symbol=member.provider_symbol,
            mapping_valid_from=member.mapping_valid_from,
            mapping_valid_through=member.mapping_valid_through,
        )
        or member.valid_from > comparison_session
        or member.valid_through is not None
        and member.valid_through < decision_session
        or member.mapping_valid_from > comparison_session
        or member.mapping_valid_through is not None
        and member.mapping_valid_through < decision_session
        or not _valid_adjusted_close(member.s0, comparison_session)
        or not _valid_adjusted_close(member.s20, decision_session)
    )


def _valid_adjusted_close(fact: object, session: date) -> bool:
    return (
        type(fact) is AdjustedCloseFact
        and fact.session == session
        and type(fact.adjusted_close) is Decimal
        and fact.adjusted_close.is_finite()
        and fact.adjusted_close > 0
    )


def _is_aware(value: datetime) -> bool:
    try:
        return value.tzinfo is not None and value.utcoffset() is not None
    except (OverflowError, TypeError, ValueError):
        return False


def _directions(
    prior_members: tuple[PrivateCurrentCohortMemberCloseProjectionV1, ...],
    current_members: tuple[PrivateCurrentCohortMemberCloseProjectionV1, ...],
) -> tuple[str, ...]:
    return tuple(
        "UP"
        if current.close > prior.close
        else "DOWN"
        if current.close < prior.close
        else "FLAT"
        for prior, current in sorted(
            zip(prior_members, current_members, strict=True),
            key=lambda pair: pair[0].member.isin,
        )
    )


def _adjusted_directions(
    members: tuple[AdjustedDailyMemberFactsV2, ...],
) -> tuple[str, ...]:
    return tuple(
        "UP"
        if member.s20.adjusted_close > member.s0.adjusted_close
        else "DOWN"
        if member.s20.adjusted_close < member.s0.adjusted_close
        else "FLAT"
        for member in members
    )
