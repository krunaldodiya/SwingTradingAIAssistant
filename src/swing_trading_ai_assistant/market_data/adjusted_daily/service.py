"""Narrow provider-neutral adjusted-daily-close acquisition for Issue #127 MVP.

The caller supplies the cohort, schedule, and a yfinance-compatible download adapter.
This module owns only adjusted-close facts; it never reads or mutates Upstox raw
OHLCV contracts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal, Protocol, TypeAlias, cast

CONTRACT_VERSION = "provider-neutral-adjusted-daily-close@v1-mvp"
PROVIDER_ID = "YFINANCE"
PRICE_BASIS = "ADJUSTED"
_SESSION_COUNT = 21
V2_CONTRACT_VERSION = "provider-neutral-adjusted-daily-close@v2"


class AdjustedDailyDownloadAdapter(Protocol):
    """Adapter boundary for a normalized yfinance adjusted-daily response."""

    def download(self, **kwargs: object) -> object:
        """Return the normalized frame mapping defined by this module."""


@dataclass(frozen=True, slots=True)
class AdjustedCloseFact:
    """One normalized adjusted close for a supplied session."""

    session: date
    adjusted_close: Decimal


@dataclass(frozen=True, slots=True)
class AdjustedDailyMemberFacts:
    """The two bounded comparison facts for one supplied cohort member."""

    isin: str
    project_symbol: str
    provider_symbol: str
    s0: AdjustedCloseFact
    s20: AdjustedCloseFact


@dataclass(frozen=True, slots=True)
class AdjustedDailyMemberFactsV2:
    """The two bounded comparison facts for one canonical listed equity."""

    isin: str
    exchange: Literal["NSE", "BSE"]
    effective_symbol: str
    provider_symbol: str
    s0: AdjustedCloseFact
    s20: AdjustedCloseFact


@dataclass(frozen=True, slots=True)
class AdjustedDailyCloseHandoff:
    """Private adjusted-close handoff; it is separate from raw OHLCV values."""

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
    """V2 private handoff retaining canonical listed-equity identity."""

    contract_version: Literal["provider-neutral-adjusted-daily-close@v2"]
    provider_id: Literal["YFINANCE"]
    price_basis: Literal["ADJUSTED"]
    provider_source: str
    retrieved_at: datetime
    temporal_label: Literal["REVISED_NON_PIT"]
    decision_cutoff: datetime
    comparison_session: date
    decision_session: date
    members: tuple[AdjustedDailyMemberFactsV2, ...]


@dataclass(frozen=True, slots=True)
class AdjustedDailyCloseSuccess:
    """Successful acquisition with complete, normalized facts for every member."""

    code: Literal["SUCCESS"]
    handoff: AdjustedDailyCloseHandoff


@dataclass(frozen=True, slots=True)
class AdjustedDailyCloseSuccessV2:
    """Successful V2 acquisition with complete canonical member facts."""

    code: Literal["SUCCESS"]
    handoff: AdjustedDailyCloseHandoffV2


@dataclass(frozen=True, slots=True)
class AdjustedDailyCloseFailure:
    """A safe, classified outcome that never contains partial adjusted facts."""

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
class _V1Request:
    decision_cutoff: datetime
    sessions: tuple[date, ...]
    members: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True, slots=True)
class _V2Member:
    isin: str
    exchange: Literal["NSE", "BSE"]
    effective_symbol: str
    provider_symbol: str


@dataclass(frozen=True, slots=True)
class _V2Request:
    decision_cutoff: datetime
    sessions: tuple[date, ...]
    members: tuple[_V2Member, ...]


def acquire_adjusted_daily_close_v1(
    request: object, *, provider: AdjustedDailyDownloadAdapter
) -> AdjustedDailyCloseResult:
    """Fetch complete adjusted closes for the caller's exact S0 and S20 sessions.

    Invalid supplied inputs fail before the adapter call. Provider and frame
    failures return classified results rather than partial member facts.
    """
    parsed = _parse_request(request)
    if isinstance(parsed, AdjustedDailyCloseFailure):
        return parsed
    return _acquire_parsed_v1(parsed, provider)


def acquire_adjusted_daily_close_v2(
    request: object, *, provider: AdjustedDailyDownloadAdapter
) -> AdjustedDailyCloseResultV2:
    """Fetch V2 adjusted closes for explicit canonical listed-equity rows."""
    parsed = _parse_request_v2(request)
    if isinstance(parsed, AdjustedDailyCloseFailure):
        return parsed

    v1_result = _acquire_parsed_v1(
        _V1Request(
            parsed.decision_cutoff,
            parsed.sessions,
            tuple(
                (member.isin, member.effective_symbol, member.provider_symbol)
                for member in parsed.members
            ),
        ),
        provider,
    )
    if isinstance(v1_result, AdjustedDailyCloseFailure):
        return v1_result

    return AdjustedDailyCloseSuccessV2(
        "SUCCESS",
        AdjustedDailyCloseHandoffV2(
            contract_version=V2_CONTRACT_VERSION,
            provider_id=v1_result.handoff.provider_id,
            price_basis=v1_result.handoff.price_basis,
            provider_source=v1_result.handoff.provider_source,
            retrieved_at=v1_result.handoff.retrieved_at,
            temporal_label=v1_result.handoff.temporal_label,
            decision_cutoff=v1_result.handoff.decision_cutoff,
            comparison_session=v1_result.handoff.comparison_session,
            decision_session=v1_result.handoff.decision_session,
            members=tuple(
                AdjustedDailyMemberFactsV2(
                    isin=member.isin,
                    exchange=member.exchange,
                    effective_symbol=member.effective_symbol,
                    provider_symbol=member.provider_symbol,
                    s0=fact.s0,
                    s20=fact.s20,
                )
                for member, fact in zip(
                    parsed.members, v1_result.handoff.members, strict=True
                )
            ),
        ),
    )


def _acquire_parsed_v1(
    request: _V1Request, provider: AdjustedDailyDownloadAdapter
) -> AdjustedDailyCloseResult:
    try:
        frame = provider.download(
            tickers=tuple(member[2] for member in request.members),
            start=request.sessions[0].isoformat(),
            end=(request.sessions[-1] + timedelta(days=1)).isoformat(),
            interval="1d",
            actions=False,
            threads=False,
            ignore_tz=False,
            group_by="ticker",
            auto_adjust=True,
            back_adjust=False,
            repair=False,
            keepna=True,
            progress=False,
            prepost=False,
            rounding=False,
            timeout=10,
            multi_level_index=True,
        )
    except Exception:
        return AdjustedDailyCloseFailure("PROVIDER_FAILURE", "PROVIDER_CALL_FAILED")

    return _normalize_frame(request, frame)


def serialize_public_result_v1(result: AdjustedDailyCloseResult) -> dict[str, str]:
    """Return an intentionally redacted summary safe for external consumers."""
    if isinstance(result, AdjustedDailyCloseFailure):
        return {"code": result.code, "reason": result.reason}
    return {
        "code": result.code,
        "provider_id": result.handoff.provider_id,
        "price_basis": result.handoff.price_basis,
        "contract_version": result.handoff.contract_version,
    }


def _parse_request(request: object) -> _V1Request | AdjustedDailyCloseFailure:
    parsed = _parse_common_request(request)
    if isinstance(parsed, AdjustedDailyCloseFailure):
        return parsed
    request_mapping, decision_cutoff, sessions = parsed
    members = _parse_members(
        request_mapping.get("mapped_members"),
        request_mapping.get("plan19_cohort"),
    )
    if members is None:
        return _invalid("MEMBER_MAPPING_INVALID")
    return _V1Request(decision_cutoff, sessions, members)


def _parse_request_v2(request: object) -> _V2Request | AdjustedDailyCloseFailure:
    parsed = _parse_common_request(request)
    if isinstance(parsed, AdjustedDailyCloseFailure):
        return parsed
    request_mapping, decision_cutoff, sessions = parsed
    members = _parse_v2_members(request_mapping.get("instruments"), sessions[-1])
    if isinstance(members, AdjustedDailyCloseFailure):
        return members
    return _V2Request(decision_cutoff, sessions, members)


def _parse_common_request(
    request: object,
) -> (
    tuple[Mapping[str, object], datetime, tuple[date, ...]] | AdjustedDailyCloseFailure
):
    request_mapping = _mapping(request)
    if request_mapping is None:
        return _invalid("REQUEST_SHAPE_INVALID")
    if request_mapping.get("provider_id") != PROVIDER_ID:
        return _invalid("PROVIDER_SELECTION_INVALID")
    if request_mapping.get("price_basis") != PRICE_BASIS:
        return _invalid("PRICE_BASIS_INVALID")

    decision_cutoff = request_mapping.get("decision_cutoff")
    if type(decision_cutoff) is not datetime or not _is_aware(decision_cutoff):
        return _invalid("DECISION_CUTOFF_INVALID")

    schedule = request_mapping.get("plan21_schedule")
    sessions = _parse_sessions(schedule)
    if sessions is None:
        return _invalid("SCHEDULE_INVALID")

    schedule_mapping = _mapping(schedule)
    if schedule_mapping is None:
        return _invalid("SCHEDULE_INVALID")
    official_close = schedule_mapping.get("decision_session_official_close_at")
    if type(official_close) is not datetime or not _is_aware(official_close):
        return _invalid("SCHEDULE_INVALID")
    if official_close > decision_cutoff:
        return _invalid("DECISION_SESSION_AFTER_CUTOFF")
    return request_mapping, decision_cutoff, sessions


def _parse_sessions(schedule: object) -> tuple[date, ...] | None:
    schedule_mapping = _mapping(schedule)
    if schedule_mapping is None:
        return None
    raw_sessions = _sequence(schedule_mapping.get("sessions"))
    if raw_sessions is None or len(raw_sessions) != _SESSION_COUNT:
        return None
    if any(type(item) is not date for item in raw_sessions):
        return None
    sessions = tuple(cast(date, item) for item in raw_sessions)
    if any(left >= right for left, right in zip(sessions, sessions[1:], strict=False)):
        return None
    return sessions


def _parse_members(
    raw_members: object, cohort: object
) -> tuple[tuple[str, str, str], ...] | None:
    member_rows = _sequence(raw_members)
    if member_rows is None or not 1 <= len(member_rows) <= 50:
        return None

    members: list[tuple[str, str, str]] = []
    for raw_member in member_rows:
        member = _mapping(raw_member)
        if member is None:
            return None
        isin = member.get("isin")
        project_symbol = member.get("project_symbol")
        provider_symbol = member.get("provider_symbol")
        if not all(
            type(value) is str and value.strip()
            for value in (isin, project_symbol, provider_symbol)
        ):
            return None
        members.append(
            (
                cast(str, isin),
                cast(str, project_symbol),
                cast(str, provider_symbol),
            )
        )

    if any(
        len({member[index] for member in members}) != len(members) for index in range(3)
    ):
        return None
    if not _cohort_matches(members, cohort):
        return None
    return tuple(members)


def _parse_v2_members(
    raw_members: object, decision_session: date
) -> tuple[_V2Member, ...] | AdjustedDailyCloseFailure:
    member_rows = _sequence(raw_members)
    if member_rows is None or not 1 <= len(member_rows) <= 100:
        return _invalid("INSTRUMENT_COUNT_INVALID")

    members: list[_V2Member] = []
    for raw_member in member_rows:
        member = _mapping(raw_member)
        if member is None:
            return _invalid("INSTRUMENT_IDENTITY_INVALID")
        isin = member.get("isin")
        exchange = member.get("exchange")
        effective_symbol = member.get("effective_symbol")
        provider_symbol = member.get("provider_symbol")
        valid_from = member.get("valid_from")
        valid_through = member.get("valid_through")
        if (
            not all(
                type(value) is str and value.strip()
                for value in (isin, exchange, effective_symbol, provider_symbol)
            )
            or type(valid_from) is not date
            or (valid_through is not None and type(valid_through) is not date)
        ):
            return _invalid("INSTRUMENT_IDENTITY_INVALID")
        isin_value = cast(str, isin)
        exchange_value = cast(Literal["NSE", "BSE"], exchange)
        effective_symbol_value = cast(str, effective_symbol)
        provider_symbol_value = cast(str, provider_symbol)
        valid_from_value = valid_from
        valid_through_value = valid_through
        if exchange_value not in {"NSE", "BSE"}:
            return AdjustedDailyCloseFailure(
                "UNSUPPORTED_CAPABILITY", "EXCHANGE_UNSUPPORTED"
            )
        expected_suffix = ".NS" if exchange_value == "NSE" else ".BO"
        if len(provider_symbol_value) == len(
            expected_suffix
        ) or not provider_symbol_value.endswith(expected_suffix):
            return AdjustedDailyCloseFailure(
                "UNSUPPORTED_CAPABILITY", "PROVIDER_MAPPING_UNSUPPORTED"
            )
        if (
            valid_from_value > decision_session
            or valid_through_value is not None
            and valid_through_value < decision_session
        ):
            return _invalid("SYMBOL_EFFECTIVE_AT_DECISION_SESSION_REQUIRED")
        members.append(
            _V2Member(
                isin_value,
                exchange_value,
                effective_symbol_value,
                provider_symbol_value,
            )
        )

    if any(
        len({getattr(member, field) for member in members}) != len(members)
        for field in ("isin", "effective_symbol", "provider_symbol")
    ):
        return _invalid("INSTRUMENT_IDENTITY_DUPLICATE")
    return tuple(members)


def _cohort_matches(members: Sequence[tuple[str, str, str]], cohort: object) -> bool:
    cohort_mapping = _mapping(cohort)
    if cohort_mapping is None:
        return False
    raw_members = _sequence(cohort_mapping.get("members"))
    if raw_members is None or len(raw_members) != len(members):
        return False
    pairs: list[tuple[str, str]] = []
    for raw_member in raw_members:
        member = _mapping(raw_member)
        if member is None:
            return False
        isin = member.get("isin")
        symbol = member.get("project_symbol")
        if type(isin) is not str or type(symbol) is not str:
            return False
        pairs.append((isin, symbol))
    return pairs == [(isin, symbol) for isin, symbol, _ in members]


def _normalize_frame(request: _V1Request, frame: object) -> AdjustedDailyCloseResult:
    frame_mapping = _mapping(frame)
    if frame_mapping is None or not frame_mapping:
        return AdjustedDailyCloseFailure("INSUFFICIENT_DATA", "PROVIDER_EMPTY")
    if frame_mapping.get("timezone") != "Asia/Kolkata":
        return AdjustedDailyCloseFailure("INSUFFICIENT_DATA", "FRAME_INDEX_INVALID")

    index = _sequence(frame_mapping.get("index"))
    if index is None or tuple(index) != request.sessions:
        return AdjustedDailyCloseFailure(
            "INSUFFICIENT_DATA", "FRAME_COVERAGE_INCOMPLETE"
        )

    close = _mapping(frame_mapping.get("close"))
    if close is None:
        return AdjustedDailyCloseFailure("INSUFFICIENT_DATA", "FRAME_SCHEMA_INVALID")

    retrieved_at = frame_mapping.get("retrieved_at")
    provider_source = frame_mapping.get("provider_source")
    if (
        type(retrieved_at) is not datetime
        or not _is_aware(retrieved_at)
        or provider_source != "yfinance==1.6.0"
        or frame_mapping.get("temporal_label") != "REVISED_NON_PIT"
    ):
        return AdjustedDailyCloseFailure("INSUFFICIENT_DATA", "FRAME_SCHEMA_INVALID")

    facts: list[AdjustedDailyMemberFacts] = []
    for isin, project_symbol, provider_symbol in request.members:
        values = _sequence(close.get(provider_symbol))
        if values is None:
            return AdjustedDailyCloseFailure(
                "INSUFFICIENT_DATA", "FRAME_SCHEMA_INVALID"
            )
        if len(values) != _SESSION_COUNT:
            return AdjustedDailyCloseFailure(
                "INSUFFICIENT_DATA", "FRAME_COVERAGE_INCOMPLETE"
            )
        normalized = tuple(_decimal(value) for value in values)
        if any(value is None for value in normalized):
            return AdjustedDailyCloseFailure(
                "INSUFFICIENT_DATA", "FRAME_SCHEMA_INVALID"
            )
        facts.append(
            AdjustedDailyMemberFacts(
                isin=isin,
                project_symbol=project_symbol,
                provider_symbol=provider_symbol,
                s0=AdjustedCloseFact(request.sessions[0], cast(Decimal, normalized[0])),
                s20=AdjustedCloseFact(
                    request.sessions[-1], cast(Decimal, normalized[-1])
                ),
            )
        )

    return AdjustedDailyCloseSuccess(
        "SUCCESS",
        AdjustedDailyCloseHandoff(
            contract_version=CONTRACT_VERSION,
            provider_id=PROVIDER_ID,
            price_basis=PRICE_BASIS,
            provider_source=cast(str, provider_source),
            retrieved_at=retrieved_at,
            temporal_label="REVISED_NON_PIT",
            decision_cutoff=request.decision_cutoff,
            comparison_session=request.sessions[0],
            decision_session=request.sessions[-1],
            members=tuple(facts),
        ),
    )


def _mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return cast(Mapping[str, object], value)


def _sequence(value: object) -> Sequence[object] | None:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    return cast(Sequence[object], value)


def _decimal(value: object) -> Decimal | None:
    if type(value) not in (int, float, Decimal) or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except Exception:
        return None
    return number if number.is_finite() and number > 0 else None


def _invalid(reason: str) -> AdjustedDailyCloseFailure:
    return AdjustedDailyCloseFailure("INVALID_REQUEST", reason)


def _is_aware(value: datetime) -> bool:
    try:
        return value.tzinfo is not None and value.utcoffset() is not None
    except (OverflowError, TypeError, ValueError):
        return False
