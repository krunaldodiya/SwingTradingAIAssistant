"""Historical Yahoo adjusted-daily handoff types and identity readers.

Active acquisition moved to :mod:`service_v3`.  These frozen V1/V2 data models
retain their original Yahoo labels so archived evidence is never reinterpreted.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final, Literal, TypeAlias

from swing_trading_ai_assistant.market_data.schedule_evidence import (
    exact_nse_schedule_source_release_pair_v1,
)

CONTRACT_VERSION: Final = "provider-neutral-adjusted-daily-close@v1-mvp"
PROVIDER_ID: Final = "YFINANCE"
PRICE_BASIS: Final = "ADJUSTED"
V2_CONTRACT_VERSION: Final = "provider-neutral-adjusted-daily-close@v2"
MAPPING_VERSION_V2: Final = "yfinance-symbol-mapping@v1"

ScheduleSourceV2: TypeAlias = Literal[
    "nse-authoritative-calendar",
    "nse-upstox-composed-calendar",
]


@dataclass(frozen=True, slots=True)
class AdjustedCloseFact:
    """One archived adjusted close for a supplied session."""

    session: date
    adjusted_close: Decimal


@dataclass(frozen=True, slots=True)
class AdjustedDailyMemberFacts:
    """Archived V1 member facts; not an active provider request."""

    isin: str
    project_symbol: str
    provider_symbol: str
    s0: AdjustedCloseFact
    s20: AdjustedCloseFact


@dataclass(frozen=True, slots=True)
class AdjustedDailyMemberFactsV2:
    """Archived V2 Yahoo member facts; labels remain immutable."""

    isin: str
    exchange: Literal["NSE", "BSE"]
    instrument_type: Literal["EQUITY"]
    segment: Literal["EQ"]
    effective_symbol: str
    valid_from: date
    valid_through: date | None
    provider_symbol: str
    mapping_version: Literal["yfinance-symbol-mapping@v1"]
    mapping_valid_from: date
    mapping_valid_through: date | None
    mapping_identity: str
    s0: AdjustedCloseFact
    s20: AdjustedCloseFact


@dataclass(frozen=True, slots=True)
class AdjustedDailyCloseHandoff:
    """Archived V1 Yahoo handoff, retained only for historical readers."""

    contract_version: str
    provider_id: Literal["YFINANCE"]
    price_basis: Literal["ADJUSTED"]
    provider_source: str
    retrieved_at: datetime
    temporal_label: Literal["REVISED_NON_PIT"]
    decision_cutoff: datetime
    comparison_session: date
    decision_session: date
    members: tuple[AdjustedDailyMemberFacts, ...]


@dataclass(frozen=True, slots=True)
class AdjustedDailyCloseHandoffV2:
    """Archived V2 Yahoo handoff, retained only for historical readers."""

    contract_version: Literal["provider-neutral-adjusted-daily-close@v2"]
    provider_id: Literal["YFINANCE"]
    price_basis: Literal["ADJUSTED"]
    provider_source: str
    retrieved_at: datetime
    temporal_label: Literal["CURRENT_PROSPECTIVE", "REVISED_NON_PIT"]
    cohort_identity_sha256: str
    request_identity_sha256: str
    decision_cutoff: datetime
    schedule_evidence_sha256: str
    schedule_source: ScheduleSourceV2
    schedule_source_release: str
    decision_session_official_close_at: datetime
    schedule_sessions: tuple[date, ...]
    schedule_identity_sha256: str
    comparison_session: date
    decision_session: date
    members: tuple[AdjustedDailyMemberFactsV2, ...]
    handoff_identity_sha256: str


@dataclass(frozen=True, slots=True)
class AdjustedDailyCloseSuccess:
    code: Literal["SUCCESS"]
    handoff: AdjustedDailyCloseHandoff


@dataclass(frozen=True, slots=True)
class AdjustedDailyCloseSuccessV2:
    code: Literal["SUCCESS"]
    handoff: AdjustedDailyCloseHandoffV2


@dataclass(frozen=True, slots=True)
class AdjustedDailyCloseFailure:
    """Historical-compatible classified outcome with no partial handoff."""

    code: Literal[
        "INVALID_REQUEST",
        "UNSUPPORTED_CAPABILITY",
        "INSUFFICIENT_DATA",
        "PROVIDER_FAILURE",
    ]
    reason: str


AdjustedDailyCloseResult: TypeAlias = (
    AdjustedDailyCloseSuccess | AdjustedDailyCloseFailure
)
AdjustedDailyCloseResultV2: TypeAlias = (
    AdjustedDailyCloseSuccessV2 | AdjustedDailyCloseFailure
)


@dataclass(frozen=True, slots=True)
class _V2Member:
    """Frozen V2 identity projection used to validate archived handoffs."""

    isin: str
    exchange: Literal["NSE", "BSE"]
    instrument_type: Literal["EQUITY"]
    segment: Literal["EQ"]
    effective_symbol: str
    provider_symbol: str
    valid_from: date
    valid_through: date | None
    mapping_version: Literal["yfinance-symbol-mapping@v1"]
    mapping_valid_from: date
    mapping_valid_through: date | None
    mapping_identity: str


def mapping_identity_v2(
    *,
    isin: str,
    exchange: Literal["NSE", "BSE"],
    instrument_type: Literal["EQUITY"],
    segment: Literal["EQ"],
    effective_symbol: str,
    provider_symbol: str,
    mapping_valid_from: date,
    mapping_valid_through: date | None,
) -> str:
    """Return the immutable Yahoo V2 mapping identity for historical reads."""
    return hashlib.sha256(
        json.dumps(
            {
                "effective_symbol": effective_symbol,
                "exchange": exchange,
                "instrument_type": instrument_type,
                "isin": isin,
                "mapping_valid_from": mapping_valid_from.isoformat(),
                "mapping_valid_through": (
                    None
                    if mapping_valid_through is None
                    else mapping_valid_through.isoformat()
                ),
                "mapping_version": MAPPING_VERSION_V2,
                "provider_id": PROVIDER_ID,
                "provider_symbol": provider_symbol,
                "segment": segment,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def adjusted_daily_schedule_identity_v2(
    *,
    sessions: Sequence[date],
    decision_session_official_close_at: datetime,
    schedule_evidence_sha256: str,
    schedule_source: ScheduleSourceV2,
    schedule_source_release: str,
) -> str:
    """Return the historical V2 schedule identity without acquiring data."""
    if not exact_nse_schedule_source_release_pair_v1(
        schedule_source, schedule_source_release
    ):
        raise ValueError("invalid schedule source/release pair")
    return _identity(
        {
            "decision_session_official_close_at": _instant(
                decision_session_official_close_at
            ),
            "schedule_evidence_sha256": schedule_evidence_sha256,
            "schedule_source": schedule_source,
            "schedule_source_release": schedule_source_release,
            "sessions": [session.isoformat() for session in sessions],
        }
    )


def adjusted_daily_request_identity_v2(
    *,
    cohort_identity_sha256: str,
    decision_cutoff: datetime,
    schedule_identity_sha256: str,
    members: Sequence[_V2Member | AdjustedDailyMemberFactsV2],
) -> str:
    """Return the frozen Yahoo V2 request identity for historical validation."""
    return _identity(
        {
            "cohort_identity_sha256": cohort_identity_sha256,
            "contract_version": V2_CONTRACT_VERSION,
            "decision_cutoff": _instant(decision_cutoff),
            "instruments": [_v2_member_identity_value(member) for member in members],
            "price_basis": PRICE_BASIS,
            "provider_id": PROVIDER_ID,
            "schedule_identity_sha256": schedule_identity_sha256,
        }
    )


def adjusted_daily_close_handoff_identity_v2(
    handoff: AdjustedDailyCloseHandoffV2,
) -> str:
    """Return the frozen Yahoo V2 handoff identity for historical validation."""
    return _identity(
        {
            "cohort_identity_sha256": handoff.cohort_identity_sha256,
            "comparison_session": handoff.comparison_session.isoformat(),
            "contract_version": handoff.contract_version,
            "decision_cutoff": _instant(handoff.decision_cutoff),
            "decision_session": handoff.decision_session.isoformat(),
            "decision_session_official_close_at": _instant(
                handoff.decision_session_official_close_at
            ),
            "members": [
                {
                    **_v2_member_identity_value(member),
                    "s0": _fact_value(member.s0),
                    "s20": _fact_value(member.s20),
                }
                for member in handoff.members
            ],
            "price_basis": handoff.price_basis,
            "provider_id": handoff.provider_id,
            "provider_source": handoff.provider_source,
            "request_identity_sha256": handoff.request_identity_sha256,
            "retrieved_at": _instant(handoff.retrieved_at),
            "schedule_evidence_sha256": handoff.schedule_evidence_sha256,
            "schedule_identity_sha256": handoff.schedule_identity_sha256,
            "schedule_sessions": [
                session.isoformat() for session in handoff.schedule_sessions
            ],
            "schedule_source": handoff.schedule_source,
            "schedule_source_release": handoff.schedule_source_release,
            "temporal_label": handoff.temporal_label,
        }
    )


def serialize_public_result_v1(result: AdjustedDailyCloseResult) -> dict[str, str]:
    """Redact a historical V1 result without re-acquiring provider data."""
    if isinstance(result, AdjustedDailyCloseFailure):
        return {"status": result.code, "reason": result.reason}
    return {"status": result.code, "provider": result.handoff.provider_id}


def serialize_public_result_v2(result: AdjustedDailyCloseResultV2) -> dict[str, str]:
    """Redact a historical V2 result without re-acquiring provider data."""
    if isinstance(result, AdjustedDailyCloseFailure):
        return {"status": result.code, "reason": result.reason}
    return {"status": result.code, "provider": result.handoff.provider_id}


def _v2_member_identity_value(
    member: _V2Member | AdjustedDailyMemberFactsV2,
) -> dict[str, object]:
    return {
        "effective_symbol": member.effective_symbol,
        "exchange": member.exchange,
        "instrument_type": member.instrument_type,
        "isin": member.isin,
        "mapping_identity": member.mapping_identity,
        "mapping_valid_from": member.mapping_valid_from.isoformat(),
        "mapping_valid_through": (
            None
            if member.mapping_valid_through is None
            else member.mapping_valid_through.isoformat()
        ),
        "mapping_version": member.mapping_version,
        "provider_symbol": member.provider_symbol,
        "segment": member.segment,
        "valid_from": member.valid_from.isoformat(),
        "valid_through": None
        if member.valid_through is None
        else member.valid_through.isoformat(),
    }


def _fact_value(fact: AdjustedCloseFact) -> dict[str, str]:
    return {
        "adjusted_close": str(fact.adjusted_close),
        "session": fact.session.isoformat(),
    }


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _identity(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        + b"\n"
    ).hexdigest()
