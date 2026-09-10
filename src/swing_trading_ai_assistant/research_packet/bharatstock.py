"""Public research facts over one validated retained BharatStock capture revision."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Literal, TypeAlias, cast

from swing_trading_ai_assistant.market_data.bharatstock import (
    PRICE_BASIS,
    BharatStockHistory,
    BharatStockInstrument,
    BharatStockPriceBasis,
)
from swing_trading_ai_assistant.market_data.bharatstock_capture import (
    RetainedCaptureRevisionV2,
    retained_capture_ohlc_v2,
    validate_capture_revision_v2,
)
from swing_trading_ai_assistant.market_structure import current_live as structure

_CONTRACT = "bharatstock-retained-research-packet@v1"
# The factor-applied literal belongs only to immutable predecessor V2 evidence.
_RetainedPriceBasis: TypeAlias = (
    BharatStockPriceBasis | Literal["BHARATSTOCK_SPLIT_BONUS_FACTOR_ADJUSTED_OHLC"]
)


def _wire(value: object) -> object:
    if type(value) is Decimal:
        return format(value, "f")
    if type(value) is datetime:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if type(value) is date:
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _wire(getattr(value, item.name)) for item in fields(value)}
    if type(value) is tuple:
        return [_wire(item) for item in cast(tuple[object, ...], value)]
    if type(value) is dict:
        return {
            str(key): _wire(item)
            for key, item in cast(dict[object, object], value).items()
        }
    return value


def _identity(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            _wire(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class BharatStockAdjustedBarV1:
    """One source-reported BharatStock bar, never an Upstox raw bar."""

    session: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    source_row_identity_sha256: str


@dataclass(frozen=True, slots=True)
class BharatStockPriceActionFactV1:
    previous_session: date
    session: date
    candle_direction: Literal["UP", "DOWN", "UNCHANGED"]
    session_range_state: Literal["FLAT", "NON_FLAT"]
    range_size: Decimal
    body_size: Decimal
    upper_wick_size: Decimal
    lower_wick_size: Decimal
    open_vs_previous_close: Literal["UP", "DOWN", "UNCHANGED"]
    open_to_previous_close_distance: Decimal
    close_vs_previous_close: Literal["UP", "DOWN", "UNCHANGED"]
    close_to_previous_close_distance: Decimal


@dataclass(frozen=True, slots=True)
class BharatStockAdjustedMarketStructureFactV1:
    """Structure calculation over the revision's declared BharatStock basis."""

    price_basis: _RetainedPriceBasis
    adjusted_bar_identities_sha256: tuple[str, ...]
    calculation: structure.CurrentMarketStructureMemberV1

    def __post_init__(self) -> None:
        if (
            self.price_basis
            not in {
                PRICE_BASIS,
                "BHARATSTOCK_SPLIT_BONUS_FACTOR_ADJUSTED_OHLC",
            }
            or len(self.adjusted_bar_identities_sha256) != 21
            or any(
                type(item) is not str
                or len(item) != 64
                or any(character not in "0123456789abcdef" for character in item)
                for item in self.adjusted_bar_identities_sha256
            )
            or type(self.calculation) is not structure.CurrentMarketStructureMemberV1
        ):
            raise ValueError("invalid adjusted market-structure fact")


@dataclass(frozen=True, slots=True)
class BharatStockResearchMemberV1:
    member: BharatStockInstrument
    price_basis: _RetainedPriceBasis
    evidence_state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE", "NOT_ATTEMPTED"]
    reason: str | None
    adjusted_bars: tuple[BharatStockAdjustedBarV1, ...] | None
    market_structure_evidence_state: Literal[
        "OBSERVED", "INSUFFICIENT_EVIDENCE", "NOT_ATTEMPTED"
    ]
    market_structure_reason: str | None
    market_structure: BharatStockAdjustedMarketStructureFactV1 | None
    price_action_evidence_state: Literal[
        "OBSERVED", "INSUFFICIENT_EVIDENCE", "NOT_ATTEMPTED"
    ]
    price_action_reason: str | None
    price_action: BharatStockPriceActionFactV1 | None


@dataclass(frozen=True, slots=True)
class BharatStockResearchCoverageV1:
    requested: int
    observed: int
    insufficient: int
    not_attempted: int


@dataclass(frozen=True, slots=True)
class BharatStockResearchPacketV1:
    contract_version: Literal["bharatstock-retained-research-packet@v1"]
    revision_identity_sha256: str
    selection_identity_sha256: str
    price_basis: _RetainedPriceBasis
    shared_failure: str | None
    coverage: BharatStockResearchCoverageV1
    aggregate_evidence_state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"]
    members: tuple[BharatStockResearchMemberV1, ...]


def _direction(left: Decimal, right: Decimal) -> Literal["UP", "DOWN", "UNCHANGED"]:
    if left > right:
        return "UP"
    if left < right:
        return "DOWN"
    return "UNCHANGED"


def _adjusted_bars(
    member: BharatStockInstrument,
    history: BharatStockHistory,
    sessions: tuple[date, ...],
    revision: RetainedCaptureRevisionV2,
) -> tuple[BharatStockAdjustedBarV1, ...] | None:
    if (
        not sessions
        or history.instrument != member
        or len(history.rows) != len(sessions)
    ):
        return None
    bars: list[BharatStockAdjustedBarV1] = []
    for session, row in zip(sessions, history.rows, strict=True):
        if row.session != session:
            return None
        try:
            open_, high, low, close = retained_capture_ohlc_v2(revision, row)
        except ValueError:
            return None
        bars.append(
            BharatStockAdjustedBarV1(
                session,
                open_,
                high,
                low,
                close,
                row.volume,
                _identity(
                    {
                        "provider_source": revision.provider_source,
                        "price_basis": revision.price_basis,
                        "member": {
                            "isin": member.isin,
                            "exchange": member.exchange,
                            "symbol": member.symbol,
                        },
                        "history_response_sha256s": history.response_sha256s,
                        "history_retrieved_at": history.retrieved_at,
                        "session": row.session,
                        "open": row.open,
                        "high": row.high,
                        "low": row.low,
                        "close": row.close,
                        "volume": row.volume,
                        "adjusted_close": row.adjusted_close,
                        "adjustment_factor": row.adjustment_factor,
                    }
                ),
            )
        )
    return tuple(bars)


def _market_structure(
    member: BharatStockInstrument,
    bars: tuple[BharatStockAdjustedBarV1, ...],
    price_basis: _RetainedPriceBasis,
) -> BharatStockAdjustedMarketStructureFactV1:
    """Calculate structure over the selected provider-neutral math bars."""
    adjusted_bars = tuple(
        structure.MarketStructureMathBarV1(
            session=bar.session,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            source_bar_identity_sha256=bar.source_row_identity_sha256,
        )
        for bar in bars
    )
    calculation = structure.evaluate_market_structure_math_member_v1(
        structure.MarketStructureMathMemberInputV1(
            isin=member.isin,
            exchange=member.exchange,
            effective_symbol=member.symbol,
            bars=adjusted_bars,
        )
    )
    return BharatStockAdjustedMarketStructureFactV1(
        price_basis=price_basis,
        adjusted_bar_identities_sha256=tuple(
            bar.source_row_identity_sha256 for bar in bars
        ),
        calculation=calculation,
    )


def _price_action(
    bars: tuple[BharatStockAdjustedBarV1, ...],
) -> BharatStockPriceActionFactV1:
    previous, current = bars[-2:]
    range_size = current.high - current.low
    body_size = abs(current.close - current.open)
    return BharatStockPriceActionFactV1(
        previous_session=previous.session,
        session=current.session,
        candle_direction=_direction(current.close, current.open),
        session_range_state="FLAT" if range_size == 0 else "NON_FLAT",
        range_size=range_size,
        body_size=body_size,
        upper_wick_size=current.high - max(current.open, current.close),
        lower_wick_size=min(current.open, current.close) - current.low,
        open_vs_previous_close=_direction(current.open, previous.close),
        open_to_previous_close_distance=abs(current.open - previous.close),
        close_vs_previous_close=_direction(current.close, previous.close),
        close_to_previous_close_distance=abs(current.close - previous.close),
    )


def build_bharatstock_research_packet_v1(
    revision: RetainedCaptureRevisionV2,
) -> BharatStockResearchPacketV1:
    """Build source-reported current facts or exact predecessor V2 facts."""
    with localcontext(Context(prec=64, rounding=ROUND_HALF_EVEN)):
        return _build_bharatstock_research_packet_v1(revision)


def _build_bharatstock_research_packet_v1(
    revision: RetainedCaptureRevisionV2,
) -> BharatStockResearchPacketV1:
    validate_capture_revision_v2(revision)
    request = revision.request
    price_basis = cast(_RetainedPriceBasis, revision.price_basis)
    members: list[BharatStockResearchMemberV1] = []
    for result in revision.members:
        if result.evidence_state != "OBSERVED":
            reason = (
                revision.shared_failure
                if result.evidence_state == "NOT_ATTEMPTED"
                else result.reason
            )
            members.append(
                BharatStockResearchMemberV1(
                    result.member,
                    price_basis,
                    result.evidence_state,
                    reason,
                    None,
                    result.evidence_state,
                    reason,
                    None,
                    result.evidence_state,
                    reason,
                    None,
                )
            )
            continue
        history = result.history
        if history is None:
            raise ValueError("observed BharatStock capture member lacks history")
        bars = _adjusted_bars(result.member, history, request.sessions, revision)
        if bars is None:
            members.append(
                BharatStockResearchMemberV1(
                    result.member,
                    price_basis,
                    "INSUFFICIENT_EVIDENCE",
                    "INVALID_PRICE_HISTORY",
                    None,
                    "INSUFFICIENT_EVIDENCE",
                    "INVALID_PRICE_HISTORY",
                    None,
                    "INSUFFICIENT_EVIDENCE",
                    "INVALID_PRICE_HISTORY",
                    None,
                )
            )
            continue
        structure_observed = len(bars) >= 21
        price_action_observed = len(bars) >= 2
        structure_reason = None if structure_observed else "INSUFFICIENT_HISTORY"
        price_action_reason = None if price_action_observed else "INSUFFICIENT_HISTORY"
        complete = structure_observed and price_action_observed
        members.append(
            BharatStockResearchMemberV1(
                result.member,
                price_basis,
                "OBSERVED" if complete else "INSUFFICIENT_EVIDENCE",
                None if complete else "INSUFFICIENT_HISTORY",
                bars,
                "OBSERVED" if structure_observed else "INSUFFICIENT_EVIDENCE",
                structure_reason,
                _market_structure(result.member, bars[-21:], price_basis)
                if structure_observed
                else None,
                "OBSERVED" if price_action_observed else "INSUFFICIENT_EVIDENCE",
                price_action_reason,
                _price_action(bars) if price_action_observed else None,
            )
        )
    ordered = tuple(members)
    observed = sum(member.evidence_state == "OBSERVED" for member in ordered)
    insufficient = sum(
        member.evidence_state == "INSUFFICIENT_EVIDENCE" for member in ordered
    )
    not_attempted = sum(member.evidence_state == "NOT_ATTEMPTED" for member in ordered)
    coverage = BharatStockResearchCoverageV1(
        len(ordered), observed, insufficient, not_attempted
    )
    if (
        coverage.requested
        != coverage.observed + coverage.insufficient + coverage.not_attempted
    ):
        raise ValueError("capture coverage is incoherent")
    return BharatStockResearchPacketV1(
        _CONTRACT,
        revision.revision_identity_sha256,
        request.selection_identity_sha256,
        price_basis,
        revision.shared_failure,
        coverage,
        "OBSERVED" if observed == coverage.requested else "INSUFFICIENT_EVIDENCE",
        ordered,
    )
