"""Direct BharatStock adjusted-daily-close handoff for the active live path.

This boundary consumes only BharatStock's canonical ISIN/exchange history.  It
keeps factor-adjusted facts separate from Plan-27's Upstox raw OHLCV evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Final, Literal, TypeAlias, cast

from swing_trading_ai_assistant.market_data.bharatstock import (
    PRICE_BASIS,
    PROVIDER_SOURCE,
    BharatStockClient,
    BharatStockDailyPrice,
    BharatStockError,
    BharatStockHistory,
    BharatStockInstrument,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    exact_nse_schedule_source_release_pair_v1,
)

from .service import AdjustedCloseFact, AdjustedDailyCloseFailure

V3_CONTRACT_VERSION: Final = "provider-neutral-adjusted-daily-close@v3"
PROVIDER_ID: Final = "BHARATSTOCK"
MAPPING_VERSION_V3: Final = "bharatstock-isin-exchange-mapping@v1"
_SESSION_COUNT: Final = 21
_ISIN: Final = re.compile(r"INE[A-Z0-9]{8}[0-9]\Z")
_SYMBOL: Final = re.compile(r"[A-Z0-9][A-Z0-9&._-]{0,63}\Z")
_SHA256: Final = re.compile(r"[0-9a-f]{64}\Z")

ScheduleSourceV3: TypeAlias = Literal[
    "nse-authoritative-calendar",
    "nse-upstox-composed-calendar",
]


@dataclass(frozen=True, slots=True)
class AdjustedDailyInstrumentV3:
    """One canonical instrument and its direct-provider mapping interval."""

    isin: str
    exchange: Literal["NSE", "BSE"]
    instrument_type: Literal["EQUITY"]
    segment: Literal["EQ"]
    effective_symbol: str
    valid_from: date
    valid_through: date | None
    provider_symbol: str
    mapping_version: Literal["bharatstock-isin-exchange-mapping@v1"]
    mapping_valid_from: date
    mapping_valid_through: date | None
    mapping_identity: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> AdjustedDailyInstrumentV3:
        parsed = _member_from_mapping(value)
        if isinstance(parsed, AdjustedDailyCloseFailure):
            raise ValueError(parsed.reason)
        return parsed


@dataclass(frozen=True, slots=True)
class AdjustedDailyMemberFactsV3:
    """Two adjusted-close facts plus the exact BharatStock response provenance."""

    isin: str
    exchange: Literal["NSE", "BSE"]
    instrument_type: Literal["EQUITY"]
    segment: Literal["EQ"]
    effective_symbol: str
    valid_from: date
    valid_through: date | None
    provider_symbol: str
    mapping_version: Literal["bharatstock-isin-exchange-mapping@v1"]
    mapping_valid_from: date
    mapping_valid_through: date | None
    mapping_identity: str
    s0: AdjustedCloseFact
    s20: AdjustedCloseFact
    source_retrieved_at: datetime
    response_sha256s: tuple[str, ...]
    provider_request_count: int


@dataclass(frozen=True, slots=True)
class AdjustedDailyCloseHandoffV3:
    """Complete, factor-adjusted direct-provider handoff for an admitted cohort."""

    contract_version: Literal["provider-neutral-adjusted-daily-close@v3"]
    provider_id: Literal["BHARATSTOCK"]
    price_basis: Literal["BHARATSTOCK_SPLIT_BONUS_FACTOR_ADJUSTED_OHLC"]
    provider_source: Literal["bharatstock-api@v1"]
    retrieved_at: datetime
    temporal_label: Literal["CURRENT_OBSERVATION", "REVISED_NON_PIT"]
    cohort_identity_sha256: str
    request_identity_sha256: str
    decision_cutoff: datetime
    schedule_evidence_sha256: str
    schedule_source: ScheduleSourceV3
    schedule_source_release: str
    decision_session_official_close_at: datetime
    schedule_sessions: tuple[date, ...]
    schedule_identity_sha256: str
    comparison_session: date
    decision_session: date
    members: tuple[AdjustedDailyMemberFactsV3, ...]
    handoff_identity_sha256: str


@dataclass(frozen=True, slots=True)
class AdjustedDailyCloseSuccessV3:
    code: Literal["SUCCESS"]
    handoff: AdjustedDailyCloseHandoffV3


AdjustedDailyCloseResultV3: TypeAlias = (
    AdjustedDailyCloseSuccessV3 | AdjustedDailyCloseFailure
)


@dataclass(frozen=True, slots=True)
class _RequestV3:
    decision_cutoff: datetime
    cohort_identity_sha256: str
    request_identity_sha256: str
    schedule_evidence_sha256: str
    schedule_source: ScheduleSourceV3
    schedule_source_release: str
    decision_session_official_close_at: datetime
    sessions: tuple[date, ...]
    schedule_identity_sha256: str
    members: tuple[AdjustedDailyInstrumentV3, ...]


def acquire_adjusted_daily_close_v3(
    request: object, provider: BharatStockClient
) -> AdjustedDailyCloseResultV3:
    """Acquire all 21 exact sessions for every member with no fallback or retry."""
    parsed = _parse_request(request)
    if isinstance(parsed, AdjustedDailyCloseFailure):
        return parsed

    facts: list[AdjustedDailyMemberFactsV3] = []
    for member in parsed.members:
        instrument = BharatStockInstrument(
            member.isin, member.exchange, member.provider_symbol
        )
        try:
            history = provider.history(
                instrument, parsed.sessions[0], parsed.sessions[-1]
            )
        except BharatStockError as error:
            if error.member_local:
                return AdjustedDailyCloseFailure("INSUFFICIENT_DATA", error.category)
            return AdjustedDailyCloseFailure("PROVIDER_FAILURE", error.category)

        fact = _member_facts(member, history, parsed.sessions)
        if isinstance(fact, AdjustedDailyCloseFailure):
            return fact
        facts.append(fact)

    retrieved_at = max(fact.source_retrieved_at for fact in facts)
    without_identity = AdjustedDailyCloseHandoffV3(
        contract_version=V3_CONTRACT_VERSION,
        provider_id=PROVIDER_ID,
        price_basis=PRICE_BASIS,
        provider_source=PROVIDER_SOURCE,
        retrieved_at=retrieved_at,
        temporal_label=(
            "CURRENT_OBSERVATION"
            if retrieved_at <= parsed.decision_cutoff
            else "REVISED_NON_PIT"
        ),
        cohort_identity_sha256=parsed.cohort_identity_sha256,
        request_identity_sha256=parsed.request_identity_sha256,
        decision_cutoff=parsed.decision_cutoff,
        schedule_evidence_sha256=parsed.schedule_evidence_sha256,
        schedule_source=parsed.schedule_source,
        schedule_source_release=parsed.schedule_source_release,
        decision_session_official_close_at=parsed.decision_session_official_close_at,
        schedule_sessions=parsed.sessions,
        schedule_identity_sha256=parsed.schedule_identity_sha256,
        comparison_session=parsed.sessions[0],
        decision_session=parsed.sessions[-1],
        members=tuple(facts),
        handoff_identity_sha256="",
    )
    handoff = replace(
        without_identity,
        handoff_identity_sha256=adjusted_daily_close_handoff_identity_v3(
            without_identity
        ),
    )
    return AdjustedDailyCloseSuccessV3("SUCCESS", handoff)


def mapping_identity_v3(
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
    """Return the direct-provider mapping identity, never a Yahoo alias."""
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
                "mapping_version": MAPPING_VERSION_V3,
                "provider_id": PROVIDER_ID,
                "provider_symbol": provider_symbol,
                "segment": segment,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def adjusted_daily_schedule_identity_v3(
    *,
    sessions: Sequence[date],
    decision_session_official_close_at: datetime,
    schedule_evidence_sha256: str,
    schedule_source: ScheduleSourceV3,
    schedule_source_release: str,
) -> str:
    """Bind the same provider-neutral Plan-21 schedule evidence under V3."""
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


def adjusted_daily_request_identity_v3(
    *,
    cohort_identity_sha256: str,
    decision_cutoff: datetime,
    schedule_identity_sha256: str,
    members: Sequence[AdjustedDailyInstrumentV3 | AdjustedDailyMemberFactsV3],
) -> str:
    """Bind the original supplied member order and direct mapping semantics."""
    return _identity(
        {
            "cohort_identity_sha256": cohort_identity_sha256,
            "contract_version": V3_CONTRACT_VERSION,
            "decision_cutoff": _instant(decision_cutoff),
            "instruments": [_member_identity_value(member) for member in members],
            "price_basis": PRICE_BASIS,
            "provider_id": PROVIDER_ID,
            "schedule_identity_sha256": schedule_identity_sha256,
        }
    )


def adjusted_daily_close_handoff_identity_v3(
    handoff: AdjustedDailyCloseHandoffV3,
) -> str:
    """Bind fact values, actual response hashes, and provider observation times."""
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
                    **_member_identity_value(member),
                    "provider_request_count": member.provider_request_count,
                    "response_sha256s": list(member.response_sha256s),
                    "s0": _fact_value(member.s0),
                    "s20": _fact_value(member.s20),
                    "source_retrieved_at": _instant(member.source_retrieved_at),
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


def adjusted_daily_close_handoff_is_valid_v3(handoff: object) -> bool:
    """Strictly validate a V3 handoff before a downstream reducer consumes it."""
    if type(handoff) is not AdjustedDailyCloseHandoffV3:
        return False
    value = handoff
    if (
        value.contract_version != V3_CONTRACT_VERSION
        or value.provider_id != PROVIDER_ID
        or value.price_basis != PRICE_BASIS
        or value.provider_source != PROVIDER_SOURCE
        or not _utc(value.retrieved_at)
        or not _utc(value.decision_cutoff)
        or value.temporal_label
        != (
            "CURRENT_OBSERVATION"
            if value.retrieved_at <= value.decision_cutoff
            else "REVISED_NON_PIT"
        )
        or not _digest(value.cohort_identity_sha256)
        or not _digest(value.request_identity_sha256)
        or not _digest(value.schedule_evidence_sha256)
        or not _digest(value.schedule_identity_sha256)
        or not _utc(value.decision_session_official_close_at)
        or type(value.schedule_sessions) is not tuple
        or len(value.schedule_sessions) != _SESSION_COUNT
        or any(type(session) is not date for session in value.schedule_sessions)
        or tuple(sorted(value.schedule_sessions)) != value.schedule_sessions
        or value.comparison_session != value.schedule_sessions[0]
        or value.decision_session != value.schedule_sessions[-1]
        or value.decision_session_official_close_at > value.decision_cutoff
        or not exact_nse_schedule_source_release_pair_v1(
            value.schedule_source, value.schedule_source_release
        )
        or value.schedule_identity_sha256
        != adjusted_daily_schedule_identity_v3(
            sessions=value.schedule_sessions,
            decision_session_official_close_at=value.decision_session_official_close_at,
            schedule_evidence_sha256=value.schedule_evidence_sha256,
            schedule_source=value.schedule_source,
            schedule_source_release=value.schedule_source_release,
        )
        or type(value.members) is not tuple
        or not 1 <= len(value.members) <= 100
    ):
        return False
    if any(
        not _member_fact_is_valid(member, value.schedule_sessions)
        for member in value.members
    ) or not _members_non_overlapping(value.members):
        return False
    if value.request_identity_sha256 != adjusted_daily_request_identity_v3(
        cohort_identity_sha256=value.cohort_identity_sha256,
        decision_cutoff=value.decision_cutoff,
        schedule_identity_sha256=value.schedule_identity_sha256,
        members=value.members,
    ):
        return False
    return value.handoff_identity_sha256 == adjusted_daily_close_handoff_identity_v3(
        value
    )


def _parse_members(
    value: object, sessions: tuple[date, ...]
) -> tuple[AdjustedDailyInstrumentV3, ...] | AdjustedDailyCloseFailure:
    raw_members = _sequence(value)
    if raw_members is None or not 1 <= len(raw_members) <= 100:
        return _invalid("INSTRUMENT_COUNT_INVALID")
    members: list[AdjustedDailyInstrumentV3] = []
    for raw in raw_members:
        member_mapping = _mapping(raw)
        if member_mapping is None:
            return _invalid("INSTRUMENT_IDENTITY_INVALID")
        member = _member_from_mapping(member_mapping)
        if isinstance(member, AdjustedDailyCloseFailure):
            return member
        if (
            member.valid_from > sessions[0]
            or member.valid_through is not None
            and member.valid_through < sessions[-1]
        ):
            return _invalid("SYMBOL_EFFECTIVE_FOR_FACT_WINDOW_REQUIRED")
        if (
            member.mapping_valid_from > sessions[0]
            or member.mapping_valid_through is not None
            and member.mapping_valid_through < sessions[-1]
        ):
            return _invalid("MAPPING_EFFECTIVE_FOR_FACT_WINDOW_REQUIRED")
        members.append(member)
    result = tuple(members)
    return (
        result
        if _members_non_overlapping(result)
        else _invalid("CANONICAL_IDENTITY_OVERLAP")
    )


def _parse_request(request: object) -> _RequestV3 | AdjustedDailyCloseFailure:
    mapping = _mapping(request)
    if mapping is None:
        return _invalid("REQUEST_SHAPE_INVALID")
    if mapping.get("provider_id") != PROVIDER_ID:
        return _invalid("PROVIDER_SELECTION_INVALID")
    if mapping.get("price_basis") != PRICE_BASIS:
        return _invalid("PRICE_BASIS_INVALID")
    cutoff = mapping.get("decision_cutoff")
    if not _utc(cutoff):
        return _invalid("DECISION_CUTOFF_INVALID")
    schedule = _parse_schedule(mapping.get("plan21_schedule"), cast(datetime, cutoff))
    if isinstance(schedule, AdjustedDailyCloseFailure):
        return schedule
    evidence, source, release, official_close, sessions, schedule_identity = schedule
    cohort_identity = mapping.get("cohort_identity_sha256")
    request_identity = mapping.get("request_identity_sha256")
    if not _digest(cohort_identity) or not _digest(request_identity):
        return _invalid("REQUEST_IDENTITY_INVALID")
    members_tuple = _parse_members(mapping.get("instruments"), sessions)
    if isinstance(members_tuple, AdjustedDailyCloseFailure):
        return members_tuple
    expected = adjusted_daily_request_identity_v3(
        cohort_identity_sha256=cast(str, cohort_identity),
        decision_cutoff=cast(datetime, cutoff),
        schedule_identity_sha256=schedule_identity,
        members=members_tuple,
    )
    if request_identity != expected:
        return _invalid("REQUEST_IDENTITY_INVALID")
    return _RequestV3(
        cast(datetime, cutoff),
        cast(str, cohort_identity),
        cast(str, request_identity),
        evidence,
        source,
        release,
        official_close,
        sessions,
        schedule_identity,
        members_tuple,
    )


def _parse_schedule(
    value: object, cutoff: datetime
) -> (
    tuple[str, ScheduleSourceV3, str, datetime, tuple[date, ...], str]
    | AdjustedDailyCloseFailure
):
    mapping = _mapping(value)
    if mapping is None:
        return _invalid("SCHEDULE_INVALID")
    sessions_value = _sequence(mapping.get("sessions"))
    if (
        sessions_value is None
        or len(sessions_value) != _SESSION_COUNT
        or any(type(session) is not date for session in sessions_value)
    ):
        return _invalid("SCHEDULE_INVALID")
    sessions = tuple(cast(date, session) for session in sessions_value)
    if any(
        left >= right for left, right in zip(sessions[:-1], sessions[1:], strict=True)
    ):
        return _invalid("SCHEDULE_INVALID")
    evidence = mapping.get("schedule_evidence_sha256")
    source = mapping.get("schedule_source")
    release = mapping.get("schedule_source_release")
    official_close = mapping.get("decision_session_official_close_at")
    identity = mapping.get("schedule_identity_sha256")
    if (
        not _digest(evidence)
        or type(source) is not str
        or type(release) is not str
        or not exact_nse_schedule_source_release_pair_v1(source, release)
        or not _utc(official_close)
        or cast(datetime, official_close) > cutoff
        or not _digest(identity)
    ):
        return _invalid("SCHEDULE_IDENTITY_INVALID")
    expected = adjusted_daily_schedule_identity_v3(
        sessions=sessions,
        decision_session_official_close_at=cast(datetime, official_close),
        schedule_evidence_sha256=cast(str, evidence),
        schedule_source=cast(ScheduleSourceV3, source),
        schedule_source_release=release,
    )
    if identity != expected:
        return _invalid("SCHEDULE_IDENTITY_INVALID")
    return (
        cast(str, evidence),
        cast(ScheduleSourceV3, source),
        release,
        cast(datetime, official_close),
        sessions,
        cast(str, identity),
    )


def _member_from_mapping(
    mapping: Mapping[str, object],
) -> AdjustedDailyInstrumentV3 | AdjustedDailyCloseFailure:
    fields = tuple(
        mapping.get(name)
        for name in (
            "isin",
            "exchange",
            "instrument_type",
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
    )
    (
        isin,
        exchange,
        instrument_type,
        segment,
        effective_symbol,
        valid_from,
        valid_through,
        provider_symbol,
        mapping_version,
        mapping_valid_from,
        mapping_valid_through,
        mapping_identity,
    ) = fields
    if (
        type(isin) is not str
        or not _valid_isin(isin)
        or type(exchange) is not str
        or exchange not in {"NSE", "BSE"}
        or instrument_type != "EQUITY"
        or segment != "EQ"
        or type(effective_symbol) is not str
        or _SYMBOL.fullmatch(effective_symbol) is None
        or type(provider_symbol) is not str
        or provider_symbol != effective_symbol
        or type(valid_from) is not date
        or valid_through is not None
        and type(valid_through) is not date
        or valid_through is not None
        and valid_from > valid_through
        or mapping_version != MAPPING_VERSION_V3
        or type(mapping_valid_from) is not date
        or mapping_valid_through is not None
        and type(mapping_valid_through) is not date
        or mapping_valid_through is not None
        and mapping_valid_from > mapping_valid_through
        or not _digest(mapping_identity)
    ):
        return _invalid("MAPPING_IDENTITY_INVALID")
    expected = mapping_identity_v3(
        isin=isin,
        exchange=cast(Literal["NSE", "BSE"], exchange),
        instrument_type="EQUITY",
        segment="EQ",
        effective_symbol=effective_symbol,
        provider_symbol=provider_symbol,
        mapping_valid_from=mapping_valid_from,
        mapping_valid_through=mapping_valid_through,
    )
    if mapping_identity != expected:
        return _invalid("MAPPING_IDENTITY_INVALID")
    return AdjustedDailyInstrumentV3(
        isin,
        cast(Literal["NSE", "BSE"], exchange),
        "EQUITY",
        "EQ",
        effective_symbol,
        valid_from,
        valid_through,
        provider_symbol,
        MAPPING_VERSION_V3,
        mapping_valid_from,
        mapping_valid_through,
        cast(str, mapping_identity),
    )


def _member_facts(
    member: AdjustedDailyInstrumentV3, history: object, sessions: tuple[date, ...]
) -> AdjustedDailyMemberFactsV3 | AdjustedDailyCloseFailure:
    if type(history) is not BharatStockHistory:
        return AdjustedDailyCloseFailure(
            "INSUFFICIENT_DATA", "PROVIDER_HISTORY_INVALID"
        )
    value = history
    instrument = BharatStockInstrument(
        member.isin, member.exchange, member.provider_symbol
    )
    if (
        value.instrument != instrument
        or not _utc(value.retrieved_at)
        or type(value.response_sha256s) is not tuple
        or not value.response_sha256s
        or any(not _digest(digest) for digest in value.response_sha256s)
        or type(value.request_count) is not int
        or value.request_count != len(value.response_sha256s)
        or type(value.rows) is not tuple
        or len(value.rows) != _SESSION_COUNT
    ):
        return AdjustedDailyCloseFailure(
            "INSUFFICIENT_DATA", "PROVIDER_HISTORY_INVALID"
        )
    for row, session in zip(value.rows, sessions, strict=True):
        if not _price_is_valid(row, session):
            return AdjustedDailyCloseFailure(
                "INSUFFICIENT_DATA", "PROVIDER_FACTOR_INVALID"
            )
    return AdjustedDailyMemberFactsV3(
        isin=member.isin,
        exchange=member.exchange,
        instrument_type=member.instrument_type,
        segment=member.segment,
        effective_symbol=member.effective_symbol,
        valid_from=member.valid_from,
        valid_through=member.valid_through,
        provider_symbol=member.provider_symbol,
        mapping_version=member.mapping_version,
        mapping_valid_from=member.mapping_valid_from,
        mapping_valid_through=member.mapping_valid_through,
        mapping_identity=member.mapping_identity,
        s0=AdjustedCloseFact(sessions[0], value.rows[0].adjusted_close),
        s20=AdjustedCloseFact(sessions[-1], value.rows[-1].adjusted_close),
        source_retrieved_at=value.retrieved_at,
        response_sha256s=value.response_sha256s,
        provider_request_count=value.request_count,
    )


def _price_is_valid(row: object, session: date) -> bool:
    if type(row) is not BharatStockDailyPrice:
        return False
    value = row
    prices = (
        value.open,
        value.high,
        value.low,
        value.close,
        value.adjusted_close,
        value.adjustment_factor,
    )
    if (
        value.session != session
        or any(
            type(price) is not Decimal or not price.is_finite() or price <= 0
            for price in prices
        )
        or type(value.volume) is not int
        or value.volume < 0
        or not value.low
        <= min(value.open, value.close)
        <= max(value.open, value.close)
        <= value.high
    ):
        return False
    with localcontext(Context(prec=64, rounding=ROUND_HALF_EVEN)):
        return value.adjusted_close == value.close * value.adjustment_factor


def _member_fact_is_valid(member: object, sessions: tuple[date, ...]) -> bool:
    if type(member) is not AdjustedDailyMemberFactsV3:
        return False
    value = member
    try:
        mapped = AdjustedDailyInstrumentV3.from_mapping(_member_fields(value))
    except (AttributeError, TypeError, ValueError):
        return False
    return not (
        _member_fields(value) != _member_fields(mapped)
        or value.valid_from > sessions[0]
        or value.valid_through is not None
        and value.valid_through < sessions[-1]
        or value.mapping_valid_from > sessions[0]
        or value.mapping_valid_through is not None
        and value.mapping_valid_through < sessions[-1]
        or type(value.s0) is not AdjustedCloseFact
        or type(value.s20) is not AdjustedCloseFact
        or value.s0.session != sessions[0]
        or value.s20.session != sessions[-1]
        or any(
            type(fact.adjusted_close) is not Decimal
            or not fact.adjusted_close.is_finite()
            or fact.adjusted_close <= 0
            for fact in (value.s0, value.s20)
        )
        or not _utc(value.source_retrieved_at)
        or type(value.response_sha256s) is not tuple
        or not value.response_sha256s
        or any(not _digest(digest) for digest in value.response_sha256s)
        or type(value.provider_request_count) is not int
        or value.provider_request_count != len(value.response_sha256s)
    )


def _members_non_overlapping(
    members: Sequence[AdjustedDailyInstrumentV3 | AdjustedDailyMemberFactsV3],
) -> bool:
    for index, left in enumerate(members):
        for right in members[index + 1 :]:
            if _intervals_overlap(
                left.valid_from,
                left.valid_through,
                right.valid_from,
                right.valid_through,
            ):
                if (left.isin, left.exchange) == (right.isin, right.exchange):
                    return False
                if (left.exchange, left.effective_symbol) == (
                    right.exchange,
                    right.effective_symbol,
                ):
                    return False
            if _intervals_overlap(
                left.mapping_valid_from,
                left.mapping_valid_through,
                right.mapping_valid_from,
                right.mapping_valid_through,
            ) and (
                left.mapping_identity == right.mapping_identity
                or left.provider_symbol == right.provider_symbol
            ):
                return False
    return True


def _intervals_overlap(
    left_from: date,
    left_through: date | None,
    right_from: date,
    right_through: date | None,
) -> bool:
    return (left_through is None or right_from <= left_through) and (
        right_through is None or left_from <= right_through
    )


def _member_fields(
    member: AdjustedDailyInstrumentV3 | AdjustedDailyMemberFactsV3,
) -> dict[str, object]:
    return {
        "isin": member.isin,
        "exchange": member.exchange,
        "instrument_type": member.instrument_type,
        "segment": member.segment,
        "effective_symbol": member.effective_symbol,
        "valid_from": member.valid_from,
        "valid_through": member.valid_through,
        "provider_symbol": member.provider_symbol,
        "mapping_version": member.mapping_version,
        "mapping_valid_from": member.mapping_valid_from,
        "mapping_valid_through": member.mapping_valid_through,
        "mapping_identity": member.mapping_identity,
    }


def _member_identity_value(
    member: AdjustedDailyInstrumentV3 | AdjustedDailyMemberFactsV3,
) -> dict[str, object]:
    return {
        "effective_symbol": member.effective_symbol,
        "exchange": member.exchange,
        "instrument_type": member.instrument_type,
        "isin": member.isin,
        "mapping_identity": member.mapping_identity,
        "mapping_valid_from": member.mapping_valid_from.isoformat(),
        "mapping_valid_through": None
        if member.mapping_valid_through is None
        else member.mapping_valid_through.isoformat(),
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


def _valid_isin(value: str) -> bool:
    if _ISIN.fullmatch(value) is None:
        return False
    digits = "".join(
        str(ord(character) - 55) if character.isalpha() else character
        for character in value
    )
    total = 0
    for index, character in enumerate(reversed(digits)):
        number = int(character)
        if index % 2:
            number *= 2
            number = number // 10 + number % 10
        total += number
    return total % 10 == 0


def _mapping(value: object) -> Mapping[str, object] | None:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def _sequence(value: object) -> Sequence[object] | None:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    return cast(Sequence[object], value)


def _digest(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _utc(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() == UTC.utcoffset(None)
    )


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _identity(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        + b"\n"
    ).hexdigest()


def _invalid(reason: str) -> AdjustedDailyCloseFailure:
    return AdjustedDailyCloseFailure("INVALID_REQUEST", reason)
