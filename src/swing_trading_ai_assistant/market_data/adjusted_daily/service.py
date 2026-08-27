"""Narrow provider-neutral adjusted-daily-close acquisition for Issue #127 MVP.

The caller supplies the cohort, schedule, and a yfinance-compatible download adapter.
This module owns only adjusted-close facts; it never reads or mutates Upstox raw
OHLCV contracts.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Final, Literal, Protocol, TypeAlias, cast

from swing_trading_ai_assistant.market_data.schedule_evidence import (
    exact_nse_schedule_source_release_pair_v1,
)

CONTRACT_VERSION = "provider-neutral-adjusted-daily-close@v1-mvp"
PROVIDER_ID = "YFINANCE"
PRICE_BASIS = "ADJUSTED"
_SESSION_COUNT = 21
V2_CONTRACT_VERSION = "provider-neutral-adjusted-daily-close@v2"
MAPPING_VERSION_V2: Final = "yfinance-symbol-mapping@v1"
_ISIN = re.compile(r"INE[A-Z0-9]{8}[0-9]\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ScheduleSourceV2: TypeAlias = Literal[
    "nse-authoritative-calendar",
    "nse-upstox-composed-calendar",
]


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
    """Private V2 handoff bound to one admitted cohort and Plan-21 schedule."""

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


@dataclass(frozen=True, slots=True)
class _V2Request:
    decision_cutoff: datetime
    cohort_identity_sha256: str
    request_identity_sha256: str
    schedule_evidence_sha256: str
    schedule_source: ScheduleSourceV2
    schedule_source_release: str
    decision_session_official_close_at: datetime
    sessions: tuple[date, ...]
    schedule_identity_sha256: str
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

    handoff_without_identity = AdjustedDailyCloseHandoffV2(
        contract_version=V2_CONTRACT_VERSION,
        provider_id=v1_result.handoff.provider_id,
        price_basis=v1_result.handoff.price_basis,
        provider_source=v1_result.handoff.provider_source,
        retrieved_at=v1_result.handoff.retrieved_at,
        temporal_label=(
            "CURRENT_PROSPECTIVE"
            if v1_result.handoff.retrieved_at <= parsed.decision_cutoff
            else "REVISED_NON_PIT"
        ),
        cohort_identity_sha256=parsed.cohort_identity_sha256,
        request_identity_sha256=parsed.request_identity_sha256,
        decision_cutoff=v1_result.handoff.decision_cutoff,
        schedule_evidence_sha256=parsed.schedule_evidence_sha256,
        schedule_source=parsed.schedule_source,
        schedule_source_release=parsed.schedule_source_release,
        decision_session_official_close_at=parsed.decision_session_official_close_at,
        schedule_sessions=parsed.sessions,
        schedule_identity_sha256=parsed.schedule_identity_sha256,
        comparison_session=v1_result.handoff.comparison_session,
        decision_session=v1_result.handoff.decision_session,
        members=tuple(
            AdjustedDailyMemberFactsV2(
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
                s0=fact.s0,
                s20=fact.s20,
            )
            for member, fact in zip(
                parsed.members, v1_result.handoff.members, strict=True
            )
        ),
        handoff_identity_sha256="",
    )
    handoff = replace(
        handoff_without_identity,
        handoff_identity_sha256=adjusted_daily_close_handoff_identity_v2(
            handoff_without_identity
        ),
    )
    return AdjustedDailyCloseSuccessV2("SUCCESS", handoff)


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


def serialize_public_result_v2(result: AdjustedDailyCloseResultV2) -> dict[str, str]:
    """Return an intentionally redacted V2 summary safe for external consumers."""
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
    schedule = _parse_v2_schedule(request_mapping.get("plan21_schedule"), sessions)
    if isinstance(schedule, AdjustedDailyCloseFailure):
        return schedule
    members = _parse_v2_members(
        request_mapping.get("instruments"), sessions[0], sessions[-1]
    )
    if isinstance(members, AdjustedDailyCloseFailure):
        return members
    cohort_identity = request_mapping.get("cohort_identity_sha256")
    request_identity = request_mapping.get("request_identity_sha256")
    if (
        type(cohort_identity) is not str
        or _SHA256.fullmatch(cohort_identity) is None
        or type(request_identity) is not str
        or _SHA256.fullmatch(request_identity) is None
    ):
        return _invalid("REQUEST_IDENTITY_INVALID")
    (
        schedule_evidence,
        schedule_source,
        schedule_source_release,
        official_close,
        schedule_identity,
    ) = schedule
    expected_request_identity = adjusted_daily_request_identity_v2(
        cohort_identity_sha256=cohort_identity,
        decision_cutoff=decision_cutoff,
        schedule_identity_sha256=schedule_identity,
        members=members,
    )
    if request_identity != expected_request_identity:
        return _invalid("REQUEST_IDENTITY_INVALID")
    return _V2Request(
        decision_cutoff,
        cohort_identity,
        request_identity,
        schedule_evidence,
        schedule_source,
        schedule_source_release,
        official_close,
        sessions,
        schedule_identity,
        members,
    )


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


def _parse_v2_schedule(
    schedule: object, sessions: tuple[date, ...]
) -> tuple[str, ScheduleSourceV2, str, datetime, str] | AdjustedDailyCloseFailure:
    schedule_mapping = _mapping(schedule)
    if schedule_mapping is None:
        return _invalid("SCHEDULE_INVALID")
    evidence = schedule_mapping.get("schedule_evidence_sha256")
    source = schedule_mapping.get("schedule_source")
    release = schedule_mapping.get("schedule_source_release")
    official_close = schedule_mapping.get("decision_session_official_close_at")
    identity = schedule_mapping.get("schedule_identity_sha256")
    if (
        type(evidence) is not str
        or _SHA256.fullmatch(evidence) is None
        or type(source) is not str
        or type(release) is not str
        or not exact_nse_schedule_source_release_pair_v1(source, release)
        or type(official_close) is not datetime
        or not _is_aware(official_close)
        or type(identity) is not str
        or _SHA256.fullmatch(identity) is None
    ):
        return _invalid("SCHEDULE_IDENTITY_INVALID")
    expected = adjusted_daily_schedule_identity_v2(
        sessions=sessions,
        decision_session_official_close_at=official_close,
        schedule_evidence_sha256=evidence,
        schedule_source=cast(ScheduleSourceV2, source),
        schedule_source_release=release,
    )
    if identity != expected:
        return _invalid("SCHEDULE_IDENTITY_INVALID")
    return evidence, cast(ScheduleSourceV2, source), release, official_close, identity


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
    raw_members: object, comparison_session: date, decision_session: date
) -> tuple[_V2Member, ...] | AdjustedDailyCloseFailure:
    member_rows = _sequence(raw_members)
    if member_rows is None or not 1 <= len(member_rows) <= 100:
        return _invalid("INSTRUMENT_COUNT_INVALID")

    members: list[_V2Member] = []
    for raw_member in member_rows:
        member = _parse_v2_member(raw_member, comparison_session, decision_session)
        if isinstance(member, AdjustedDailyCloseFailure):
            return member
        members.append(member)
    return _validate_v2_member_overlaps(members)


def _parse_v2_equity_classification(
    member: Mapping[str, object],
) -> tuple[Literal["EQUITY"], Literal["EQ"]] | AdjustedDailyCloseFailure:
    instrument_type = member.get("instrument_type")
    segment = member.get("segment")
    if any(
        type(value) is not str or not value.strip()
        for value in (instrument_type, segment)
    ):
        return _invalid("INSTRUMENT_IDENTITY_INVALID")
    if instrument_type != "EQUITY":
        return AdjustedDailyCloseFailure(
            "UNSUPPORTED_CAPABILITY", "INSTRUMENT_TYPE_UNSUPPORTED"
        )
    if segment != "EQ":
        return AdjustedDailyCloseFailure(
            "UNSUPPORTED_CAPABILITY", "SEGMENT_UNSUPPORTED"
        )
    return "EQUITY", "EQ"


def _parse_v2_mapping(
    member: Mapping[str, object],
) -> (
    tuple[Literal["yfinance-symbol-mapping@v1"], date, date | None, str]
    | AdjustedDailyCloseFailure
):
    mapping_version = member.get("mapping_version")
    mapping_valid_from = member.get("mapping_valid_from")
    mapping_valid_through = member.get("mapping_valid_through")
    mapping_identity = member.get("mapping_identity")
    if (
        type(mapping_version) is not str
        or type(mapping_valid_from) is not date
        or (
            mapping_valid_through is not None
            and type(mapping_valid_through) is not date
        )
        or type(mapping_identity) is not str
        or _SHA256.fullmatch(mapping_identity) is None
        or mapping_valid_through is not None
        and mapping_valid_from > mapping_valid_through
    ):
        return _invalid("MAPPING_IDENTITY_INVALID")
    if mapping_version != MAPPING_VERSION_V2:
        return AdjustedDailyCloseFailure(
            "UNSUPPORTED_CAPABILITY", "MAPPING_VERSION_UNSUPPORTED"
        )
    return (
        MAPPING_VERSION_V2,
        mapping_valid_from,
        mapping_valid_through,
        mapping_identity,
    )


def _parse_v2_member(
    raw_member: object, comparison_session: date, decision_session: date
) -> _V2Member | AdjustedDailyCloseFailure:
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
        type(isin) is not str
        or not _valid_isin(isin)
        or any(
            type(value) is not str or not value.strip()
            for value in (exchange, effective_symbol, provider_symbol)
        )
        or type(valid_from) is not date
        or (valid_through is not None and type(valid_through) is not date)
        or valid_through is not None
        and valid_from > valid_through
    ):
        return _invalid("INSTRUMENT_IDENTITY_INVALID")

    exchange_value = cast(Literal["NSE", "BSE"], exchange)
    effective_symbol_value = cast(str, effective_symbol)
    provider_symbol_value = cast(str, provider_symbol)
    if exchange_value not in {"NSE", "BSE"}:
        return AdjustedDailyCloseFailure(
            "UNSUPPORTED_CAPABILITY", "EXCHANGE_UNSUPPORTED"
        )
    classification = _parse_v2_equity_classification(member)
    if isinstance(classification, AdjustedDailyCloseFailure):
        return classification
    instrument_type_value, segment_value = classification
    expected_suffix = ".NS" if exchange_value == "NSE" else ".BO"
    provider_base = provider_symbol_value.removesuffix(expected_suffix)
    if (
        not provider_base
        or provider_base != effective_symbol_value
        or provider_base == provider_symbol_value
    ):
        return AdjustedDailyCloseFailure(
            "UNSUPPORTED_CAPABILITY", "PROVIDER_MAPPING_UNSUPPORTED"
        )
    if (
        valid_from > comparison_session
        or valid_through is not None
        and valid_through < decision_session
    ):
        return _invalid("SYMBOL_EFFECTIVE_FOR_FACT_WINDOW_REQUIRED")

    mapping = _parse_v2_mapping(member)
    if isinstance(mapping, AdjustedDailyCloseFailure):
        return mapping
    (
        mapping_version,
        mapping_valid_from,
        mapping_valid_through,
        mapping_identity,
    ) = mapping
    if (
        mapping_valid_from > comparison_session
        or mapping_valid_through is not None
        and mapping_valid_through < decision_session
    ):
        return _invalid("MAPPING_EFFECTIVE_FOR_FACT_WINDOW_REQUIRED")

    expected_identity = mapping_identity_v2(
        isin=isin,
        exchange=exchange_value,
        instrument_type=instrument_type_value,
        segment=segment_value,
        effective_symbol=effective_symbol_value,
        provider_symbol=provider_symbol_value,
        mapping_valid_from=mapping_valid_from,
        mapping_valid_through=mapping_valid_through,
    )
    if mapping_identity != expected_identity:
        return _invalid("MAPPING_IDENTITY_INVALID")
    return _V2Member(
        isin,
        exchange_value,
        instrument_type_value,
        segment_value,
        effective_symbol_value,
        provider_symbol_value,
        valid_from,
        valid_through,
        mapping_version,
        mapping_valid_from,
        mapping_valid_through,
        mapping_identity,
    )


def _validate_v2_member_overlaps(
    members: Sequence[_V2Member],
) -> tuple[_V2Member, ...] | AdjustedDailyCloseFailure:
    for position, left in enumerate(members):
        for right in members[position + 1 :]:
            if _intervals_overlap(
                left.valid_from,
                left.valid_through,
                right.valid_from,
                right.valid_through,
            ):
                if (left.isin, left.exchange) == (right.isin, right.exchange):
                    return _invalid("CANONICAL_IDENTITY_OVERLAP")
                if (left.exchange, left.effective_symbol) == (
                    right.exchange,
                    right.effective_symbol,
                ):
                    return _invalid("EFFECTIVE_SYMBOL_OVERLAP")
            if _intervals_overlap(
                left.mapping_valid_from,
                left.mapping_valid_through,
                right.mapping_valid_from,
                right.mapping_valid_through,
            ) and (
                left.mapping_identity == right.mapping_identity
                or left.provider_symbol == right.provider_symbol
            ):
                return _invalid("PROVIDER_MAPPING_OVERLAP")
    return tuple(sorted(members, key=_v2_member_canonical_key))


def _intervals_overlap(
    left_from: date,
    left_through: date | None,
    right_from: date,
    right_through: date | None,
) -> bool:
    return (left_through is None or right_from <= left_through) and (
        right_through is None or left_from <= right_through
    )


def _v2_member_canonical_key(member: _V2Member) -> tuple[str, str, str]:
    return member.isin, member.exchange, member.effective_symbol


def _valid_isin(isin: str) -> bool:
    if _ISIN.fullmatch(isin) is None:
        return False
    digits = "".join(
        str(ord(character) - 55) if character.isalpha() else character
        for character in isin
    )
    total = 0
    for index, character in enumerate(reversed(digits)):
        value = int(character)
        if index % 2:
            value *= 2
            value = value // 10 + value % 10
        total += value
    return total % 10 == 0


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
                    "s0": {
                        "adjusted_close": str(member.s0.adjusted_close),
                        "session": member.s0.session.isoformat(),
                    },
                    "s20": {
                        "adjusted_close": str(member.s20.adjusted_close),
                        "session": member.s20.session.isoformat(),
                    },
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
        "valid_through": (
            None if member.valid_through is None else member.valid_through.isoformat()
        ),
    }


def _identity(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        + b"\n"
    ).hexdigest()


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


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
