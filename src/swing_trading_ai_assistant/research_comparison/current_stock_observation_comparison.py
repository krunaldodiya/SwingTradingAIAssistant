"""Compare two admitted current-stock V2 observations without raw market data."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)
from pathlib import Path
from typing import Final, Literal, TypeAlias, cast

from swing_trading_ai_assistant.market_data import (
    current_stock_research_v2 as current_research,
)
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockAdjustedMarketStructureFactV1,
    BharatStockCandleGeometryFactV2,
    BharatStockMemberFeatureV2,
    BharatStockPreviousCloseComparisonFactV2,
    BharatStockResearchPacketV2,
    validate_bharatstock_research_packet_v2,
)

from .current_stock_observation_comparison_runtime_identity_manifest import (
    CURRENT_STOCK_OBSERVATION_COMPARISON_RUNTIME_SOURCE_SHA256_V1,
)

CONTRACT_VERSION_V1: Final = "current-stock-observation-comparison@v1"
SCHEMA_IDENTITY_SHA256_V1: Final = hashlib.sha256(
    b"current-stock-observation-comparison-schema@v1\n"
).hexdigest()
CONFIGURATION_IDENTITY_SHA256_V1: Final = hashlib.sha256(
    b"two-admitted-observations-one-stock-one-question-closed-facts@v1\n"
).hexdigest()
_SUPPORTED_QUESTIONS: Final = {"PRICE_BEHAVIOR", "CURRENT_STRUCTURE"}
_MAX_FACTS: Final = 12
_FEATURE_AVAILABILITIES: Final = {
    "OBSERVED",
    "UNSUPPORTED_CAPABILITY",
    "DEPENDENCY_BLOCKED",
    "INSUFFICIENT_EVIDENCE",
    "NOT_ATTEMPTED",
}
_NUMERIC_FACT_PATHS: Final = {
    "CANDLE_GEOMETRY.range_size",
    "CANDLE_GEOMETRY.body_size",
    "CANDLE_GEOMETRY.upper_wick_size",
    "CANDLE_GEOMETRY.lower_wick_size",
    "PREVIOUS_CLOSE_COMPARISON.open_to_previous_close_distance",
    "PREVIOUS_CLOSE_COMPARISON.close_to_previous_close_distance",
}
_TEXT_FACT_PATHS: Final = {
    "CANDLE_GEOMETRY.candle_direction",
    "PREVIOUS_CLOSE_COMPARISON.open_vs_previous_close",
    "PREVIOUS_CLOSE_COMPARISON.close_vs_previous_close",
    "MARKET_STRUCTURE.structure_state",
    "MARKET_STRUCTURE.trend",
}
_TEXT_VALUE_DOMAINS: Final = {
    "CANDLE_GEOMETRY.candle_direction": frozenset({"UP", "DOWN", "UNCHANGED"}),
    "PREVIOUS_CLOSE_COMPARISON.open_vs_previous_close": frozenset(
        {"UP", "DOWN", "UNCHANGED"}
    ),
    "PREVIOUS_CLOSE_COMPARISON.close_vs_previous_close": frozenset(
        {"UP", "DOWN", "UNCHANGED"}
    ),
    "MARKET_STRUCTURE.structure_state": frozenset(
        {"CONFIRMED", "INSUFFICIENT_STRUCTURE"}
    ),
    "MARKET_STRUCTURE.trend": frozenset(
        {"UPTREND", "DOWNTREND", "RANGE_OR_TRANSITION", "INSUFFICIENT_STRUCTURE"}
    ),
}
_QUESTION_FACT_PATHS: Final = {
    "PRICE_BEHAVIOR": (
        "CANDLE_GEOMETRY.candle_direction",
        "CANDLE_GEOMETRY.range_size",
        "CANDLE_GEOMETRY.body_size",
        "CANDLE_GEOMETRY.upper_wick_size",
        "CANDLE_GEOMETRY.lower_wick_size",
        "PREVIOUS_CLOSE_COMPARISON.open_vs_previous_close",
        "PREVIOUS_CLOSE_COMPARISON.open_to_previous_close_distance",
        "PREVIOUS_CLOSE_COMPARISON.close_vs_previous_close",
        "PREVIOUS_CLOSE_COMPARISON.close_to_previous_close_distance",
    ),
    "CURRENT_STRUCTURE": (
        "MARKET_STRUCTURE.structure_state",
        "MARKET_STRUCTURE.trend",
    ),
}
_DECIMAL_TEXT: Final = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?\Z")
_DIGEST_TEXT: Final = re.compile(r"[0-9a-f]{64}\Z")
_ISIN_TEXT: Final = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]\Z")
_SYMBOL_TEXT: Final = re.compile(r"[A-Z0-9][A-Z0-9.&_-]{0,31}\Z")
_MAX_VALUE_TEXT: Final = 258
# Two admitted 258-character values can differ by 258 integer digits and
# 256 fractional digits, plus a sign and decimal point.
_MAX_DELTA_TEXT: Final = 516
_MAX_REASON_TEXT: Final = 256
_FAILURE_CODES: Final = frozenset(
    {
        "OBSERVATION_INVALID",
        "OBSERVATION_UNAVAILABLE",
        "INCOMPATIBLE_QUESTION_OR_CONTRACT",
        "INCOMPATIBLE_STOCK",
        "INVALID_TEMPORAL_ORDER",
        "INCOMPATIBLE_PRICE_BASIS",
    }
)
_PRICE_BASES: Final = frozenset(
    {
        "BHARATSTOCK_SOURCE_REPORTED_OHLC",
        "BHARATSTOCK_SPLIT_BONUS_FACTOR_ADJUSTED_OHLC",
    }
)
_LIMITATIONS: Final = (
    "comparison_of_supplied_admitted_facts_only",
    "not_trade_eligibility",
    "not_recommendation_or_scoring",
    "no_raw_ohlc_or_recalculation_by_assistant",
)

ComparisonStatusV1: TypeAlias = Literal["COMPARABLE", "NON_COMPARABLE"]
ComparisonStateV1: TypeAlias = Literal[
    "UNCHANGED",
    "CHANGED",
    "NEWLY_AVAILABLE",
    "NEWLY_UNAVAILABLE",
    "UNAVAILABLE_IN_BOTH",
]


def _comparison_decimal_context() -> Context:
    return Context(
        prec=1024,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[InvalidOperation, DivisionByZero, Overflow],
    )


def _admitted_numeric_text(value: str, *, delta: bool = False) -> Decimal:
    limit = _MAX_DELTA_TEXT if delta else _MAX_VALUE_TEXT
    unsigned = value[1:] if delta and value.startswith("-") else value
    if (
        len(value) > limit
        or _DECIMAL_TEXT.fullmatch(unsigned) is None
        or (delta and value == "-0")
    ):
        raise ValueError("invalid observation comparison fact")
    number = Decimal(value)
    if not number.is_finite() or (not delta and number < 0):
        raise ValueError("invalid observation comparison fact")
    return number


def _utc_instant(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() == UTC.utcoffset(None)
    )


def _strictly_before(left: object, right: object) -> bool:
    if type(left) is datetime and type(right) is datetime:
        return left < right
    if type(left) is date and type(right) is date:
        return left < right
    return False


def _same_admitted_fact_values(
    path: str,
    previous_value: str | None,
    current_value: str | None,
    delta: str | None,
) -> bool:
    if path in _NUMERIC_FACT_PATHS:
        before = (
            None if previous_value is None else _admitted_numeric_text(previous_value)
        )
        after = None if current_value is None else _admitted_numeric_text(current_value)
        if delta is not None:
            try:
                with localcontext(_comparison_decimal_context()):
                    computed = _admitted_numeric_text(delta, delta=True)
                    if before is None or after is None or after - before != computed:
                        raise ValueError("invalid observation comparison fact")
            except (InvalidOperation, Overflow, TypeError) as error:
                raise ValueError("invalid observation comparison fact") from error
        return before == after
    domain = _TEXT_VALUE_DOMAINS[path]
    if any(
        value is not None and value not in domain
        for value in (previous_value, current_value)
    ):
        raise ValueError("invalid observation comparison fact")
    return previous_value == current_value


def _wire(value: object) -> object:
    if type(value) is Decimal:
        return format(value, "f")
    if type(value) is datetime:
        return (
            value.astimezone(UTC)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    if type(value) is date:
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _wire(getattr(value, item.name)) for item in fields(value)}
    if type(value) is tuple:
        return [_wire(item) for item in cast(tuple[object, ...], value)]
    if type(value) is dict:
        return {
            cast(str, key): _wire(item)
            for key, item in cast(dict[object, object], value).items()
        }
    return value


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            _wire(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def current_stock_observation_comparison_runtime_code_identity_v1() -> str:
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for (
        relative,
        expected,
    ) in CURRENT_STOCK_OBSERVATION_COMPARISON_RUNTIME_SOURCE_SHA256_V1.items():
        module_parts = Path(relative).with_suffix("").parts[1:]
        if module_parts[-1] == "__init__":
            module_parts = module_parts[:-1]
        module = ".".join(module_parts)
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("observation comparison runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


@dataclass(frozen=True, slots=True)
class CurrentStockObservationComparisonFactV1:
    path: str
    state: ComparisonStateV1
    previous_availability: str
    current_availability: str
    previous_reason: str | None
    current_reason: str | None
    previous_value: str | None
    current_value: str | None
    delta: str | None

    def __post_init__(self) -> None:
        previous_observed = self.previous_availability == "OBSERVED"
        current_observed = self.current_availability == "OBSERVED"
        if (
            type(self.path) is not str
            or self.path not in _NUMERIC_FACT_PATHS | _TEXT_FACT_PATHS
            or self.state
            not in {
                "UNCHANGED",
                "CHANGED",
                "NEWLY_AVAILABLE",
                "NEWLY_UNAVAILABLE",
                "UNAVAILABLE_IN_BOTH",
            }
            or type(self.previous_availability) is not str
            or self.previous_availability not in _FEATURE_AVAILABILITIES
            or type(self.current_availability) is not str
            or self.current_availability not in _FEATURE_AVAILABILITIES
            or any(
                value is not None and (type(value) is not str or not value)
                for value in (
                    self.previous_reason,
                    self.current_reason,
                    self.previous_value,
                    self.current_value,
                    self.delta,
                )
            )
            or any(
                reason is not None and len(reason) > _MAX_REASON_TEXT
                for reason in (self.previous_reason, self.current_reason)
            )
            or previous_observed != (self.previous_value is not None)
            or current_observed != (self.current_value is not None)
            or previous_observed == (self.previous_reason is not None)
            or current_observed == (self.current_reason is not None)
            or (self.delta is not None and self.state not in {"CHANGED", "UNCHANGED"})
            or (self.delta is not None)
            != (
                previous_observed
                and current_observed
                and self.path in _NUMERIC_FACT_PATHS
            )
        ):
            raise ValueError("invalid observation comparison fact")
        same = _same_admitted_fact_values(
            self.path, self.previous_value, self.current_value, self.delta
        )
        if previous_observed and current_observed:
            expected = "UNCHANGED" if same else "CHANGED"
        elif previous_observed:
            expected = "NEWLY_UNAVAILABLE"
        elif current_observed:
            expected = "NEWLY_AVAILABLE"
        else:
            expected = "UNAVAILABLE_IN_BOTH"
        if self.state != expected:
            raise ValueError("invalid observation comparison fact")


@dataclass(frozen=True, slots=True)
class CurrentStockObservationComparisonV1:
    contract_version: Literal["current-stock-observation-comparison@v1"]
    schema_identity_sha256: str
    configuration_identity_sha256: str
    runtime_code_identity_sha256: str
    status: ComparisonStatusV1
    code: str
    question: str | None
    symbol: str | None
    isin: str | None
    exchange: str | None
    price_basis: str | None
    previous_observation_identity_sha256: str | None
    current_observation_identity_sha256: str | None
    previous_selection_time: datetime | None
    current_selection_time: datetime | None
    previous_completed_session: date | None
    current_completed_session: date | None
    previous_evidence_known_at: datetime | None
    current_evidence_known_at: datetime | None
    facts: tuple[CurrentStockObservationComparisonFactV1, ...]
    limitations: tuple[str, ...]
    result_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        comparable = self.status == "COMPARABLE"
        metadata = (
            self.question,
            self.symbol,
            self.isin,
            self.exchange,
            self.price_basis,
            self.previous_observation_identity_sha256,
            self.current_observation_identity_sha256,
            self.previous_selection_time,
            self.current_selection_time,
            self.previous_completed_session,
            self.current_completed_session,
            self.previous_evidence_known_at,
            self.current_evidence_known_at,
        )
        if (
            type(self.contract_version) is not str
            or self.contract_version != CONTRACT_VERSION_V1
            or type(self.schema_identity_sha256) is not str
            or self.schema_identity_sha256 != SCHEMA_IDENTITY_SHA256_V1
            or type(self.configuration_identity_sha256) is not str
            or self.configuration_identity_sha256 != CONFIGURATION_IDENTITY_SHA256_V1
            or type(self.runtime_code_identity_sha256) is not str
            or self.runtime_code_identity_sha256
            != current_stock_observation_comparison_runtime_code_identity_v1()
            or type(self.status) is not str
            or self.status not in {"COMPARABLE", "NON_COMPARABLE"}
            or type(self.code) is not str
            or self.code not in ({"COMPARISON_READY"} if comparable else _FAILURE_CODES)
            or type(self.facts) is not tuple
            or len(self.facts) > _MAX_FACTS
            or any(
                type(item) is not CurrentStockObservationComparisonFactV1
                for item in self.facts
            )
            or any(item.__post_init__() is not None for item in self.facts)
            or len({item.path for item in self.facts}) != len(self.facts)
            or (
                comparable
                and (
                    type(self.question) is not str
                    or self.question not in _QUESTION_FACT_PATHS
                    or tuple(item.path for item in self.facts)
                    != _QUESTION_FACT_PATHS[self.question]
                )
            )
            or type(self.limitations) is not tuple
            or self.limitations != _LIMITATIONS
            or any(type(item) is not str for item in self.limitations)
            or comparable != bool(self.facts)
            or (comparable and any(value is None for value in metadata))
            or (not comparable and any(value is not None for value in metadata))
        ):
            raise ValueError("invalid current-stock observation comparison")
        if comparable and (
            type(self.symbol) is not str
            or _SYMBOL_TEXT.fullmatch(self.symbol) is None
            or type(self.isin) is not str
            or _ISIN_TEXT.fullmatch(self.isin) is None
            or self.exchange != "NSE"
            or type(self.exchange) is not str
            or type(self.price_basis) is not str
            or self.price_basis not in _PRICE_BASES
            or any(
                type(value) is not str or _DIGEST_TEXT.fullmatch(value) is None
                for value in (
                    self.previous_observation_identity_sha256,
                    self.current_observation_identity_sha256,
                )
            )
            or self.previous_observation_identity_sha256
            == self.current_observation_identity_sha256
            or any(
                not _utc_instant(value)
                for value in (
                    self.previous_selection_time,
                    self.current_selection_time,
                    self.previous_evidence_known_at,
                    self.current_evidence_known_at,
                )
            )
            or type(self.previous_completed_session) is not date
            or type(self.current_completed_session) is not date
            or not _strictly_before(
                self.previous_selection_time, self.current_selection_time
            )
            or not _strictly_before(
                self.previous_completed_session, self.current_completed_session
            )
            or not _strictly_before(
                self.previous_evidence_known_at, self.current_evidence_known_at
            )
        ):
            raise ValueError("invalid current-stock observation comparison")
        payload = {
            item.name: getattr(self, item.name)
            for item in fields(self)
            if item.name != "result_identity_sha256"
        }
        object.__setattr__(self, "result_identity_sha256", _digest(payload))

    def canonical_json_bytes(self) -> bytes:
        self.__post_init__()
        return _canonical(self)


def _non_comparable(code: str) -> CurrentStockObservationComparisonV1:
    return CurrentStockObservationComparisonV1(
        contract_version=CONTRACT_VERSION_V1,
        schema_identity_sha256=SCHEMA_IDENTITY_SHA256_V1,
        configuration_identity_sha256=CONFIGURATION_IDENTITY_SHA256_V1,
        runtime_code_identity_sha256=current_stock_observation_comparison_runtime_code_identity_v1(),
        status="NON_COMPARABLE",
        code=code,
        question=None,
        symbol=None,
        isin=None,
        exchange=None,
        price_basis=None,
        previous_observation_identity_sha256=None,
        current_observation_identity_sha256=None,
        previous_selection_time=None,
        current_selection_time=None,
        previous_completed_session=None,
        current_completed_session=None,
        previous_evidence_known_at=None,
        current_evidence_known_at=None,
        facts=(),
        limitations=_LIMITATIONS,
    )


def _observation(
    result: CurrentStockResearchResultV2,
) -> tuple[bytes, BharatStockResearchPacketV2] | None:
    if type(result) is not CurrentStockResearchResultV2:
        return None
    raw = result.canonical_json_bytes()
    if result.runtime_code_identity_sha256 != current_research._runtime_identity():  # pyright: ignore[reportPrivateUsage]
        return None
    if type(result.packet) is not BharatStockResearchPacketV2:
        return (raw, cast(BharatStockResearchPacketV2, result.packet))
    packet = validate_bharatstock_research_packet_v2(result.packet)
    known_values = [
        source.known_at
        for slot, source in zip(
            packet.feature_slots,
            (packet.geometry_source, packet.comparison_source, packet.structure_source),
            strict=True,
        )
        if source is not None
        and any(
            coverage.feature == slot.feature and coverage.observed > 0
            for coverage in packet.coverage
        )
    ]
    if result.evidence_known_at != (max(known_values) if known_values else None):
        return None
    return raw, packet


def _completed_session(packet: BharatStockResearchPacketV2) -> date | None:
    sessions = tuple(
        slot.source.requested_sessions[-1]
        for slot in packet.feature_slots
        if slot.source is not None and slot.source.requested_sessions
    )
    return max(sessions) if sessions else None


def _value(value: object) -> str:
    if type(value) is Decimal:
        if value == 0:
            return "0"
        return format(value.normalize(), "f")
    if type(value) is date:
        return value.isoformat()
    return str(value)


def _fact(
    path: str,
    previous_feature: BharatStockMemberFeatureV2,
    current_feature: BharatStockMemberFeatureV2,
    previous_value: object | None,
    current_value: object | None,
) -> CurrentStockObservationComparisonFactV1:
    previous_observed = previous_feature.availability == "OBSERVED"
    current_observed = current_feature.availability == "OBSERVED"
    before = _value(previous_value) if previous_observed else None
    after = _value(current_value) if current_observed else None
    delta: str | None = None
    if previous_observed and current_observed:
        state: ComparisonStateV1 = (
            "UNCHANGED"
            if (
                previous_value == current_value
                if type(previous_value) is Decimal and type(current_value) is Decimal
                else before == after
            )
            else "CHANGED"
        )
        if type(previous_value) is Decimal and type(current_value) is Decimal:
            delta = _value(current_value - previous_value)
    elif previous_observed:
        state = "NEWLY_UNAVAILABLE"
    elif current_observed:
        state = "NEWLY_AVAILABLE"
    else:
        state = "UNAVAILABLE_IN_BOTH"
    return CurrentStockObservationComparisonFactV1(
        path,
        state,
        previous_feature.availability,
        current_feature.availability,
        previous_feature.reason,
        current_feature.reason,
        before,
        after,
        delta,
    )


def _feature_values(
    question: str,
    feature: BharatStockMemberFeatureV2,
) -> tuple[tuple[str, object | None], ...]:
    fact = feature.fact
    if feature.feature == "CANDLE_GEOMETRY":
        value = cast(BharatStockCandleGeometryFactV2 | None, fact)
        names = (
            "candle_direction",
            "range_size",
            "body_size",
            "upper_wick_size",
            "lower_wick_size",
        )
        return tuple(
            (f"CANDLE_GEOMETRY.{name}", None if value is None else getattr(value, name))
            for name in names
        )
    if feature.feature == "PREVIOUS_CLOSE_COMPARISON":
        value = cast(BharatStockPreviousCloseComparisonFactV2 | None, fact)
        names = (
            "open_vs_previous_close",
            "open_to_previous_close_distance",
            "close_vs_previous_close",
            "close_to_previous_close_distance",
        )
        return tuple(
            (
                f"PREVIOUS_CLOSE_COMPARISON.{name}",
                None if value is None else getattr(value, name),
            )
            for name in names
        )
    if question == "CURRENT_STRUCTURE" and feature.feature == "MARKET_STRUCTURE":
        value = cast(BharatStockAdjustedMarketStructureFactV1 | None, fact)
        calculation = None if value is None else value.calculation
        return (
            (
                "MARKET_STRUCTURE.structure_state",
                None if calculation is None else calculation.structure_state,
            ),
            (
                "MARKET_STRUCTURE.trend",
                None if calculation is None else calculation.trend,
            ),
        )
    raise ValueError("unsupported comparison feature")


def _comparison_facts(
    previous_packet: BharatStockResearchPacketV2,
    current_packet: BharatStockResearchPacketV2,
    question: str,
) -> tuple[CurrentStockObservationComparisonFactV1, ...]:
    previous_by_feature = {
        item.feature: item for item in previous_packet.members[0].features
    }
    current_by_feature = {
        item.feature: item for item in current_packet.members[0].features
    }
    facts: list[CurrentStockObservationComparisonFactV1] = []
    for feature_name in previous_packet.requested_features:
        previous_feature = previous_by_feature[feature_name]
        current_feature = current_by_feature[feature_name]
        previous_values = _feature_values(question, previous_feature)
        current_values = dict(_feature_values(question, current_feature))
        facts.extend(
            _fact(path, previous_feature, current_feature, value, current_values[path])
            for path, value in previous_values
        )
    return tuple(facts)


def compare_current_stock_observations_v1(
    previous: CurrentStockResearchResultV2,
    current: CurrentStockResearchResultV2,
) -> CurrentStockObservationComparisonV1:
    """Compare exactly two admitted V2 observations in deterministic order."""
    with localcontext(_comparison_decimal_context()):
        return _compare_current_stock_observations_v1(previous, current)


def _compare_current_stock_observations_v1(
    previous: CurrentStockResearchResultV2,
    current: CurrentStockResearchResultV2,
) -> CurrentStockObservationComparisonV1:
    try:
        previous_admitted = _observation(previous)
        current_admitted = _observation(current)
    except (AttributeError, TypeError, ValueError):
        return _non_comparable("OBSERVATION_INVALID")
    if previous_admitted is None or current_admitted is None:
        return _non_comparable("OBSERVATION_INVALID")
    previous_raw, previous_packet = previous_admitted
    current_raw, current_packet = current_admitted
    if previous.packet is None or current.packet is None:
        return _non_comparable("OBSERVATION_UNAVAILABLE")
    if (
        previous.contract_version != current_research.CONTRACT_VERSION_V2
        or current.contract_version != current_research.CONTRACT_VERSION_V2
        or previous.question != current.question
        or previous.question not in _SUPPORTED_QUESTIONS
    ):
        return _non_comparable("INCOMPATIBLE_QUESTION_OR_CONTRACT")
    previous_member = previous_packet.members[0]
    current_member = current_packet.members[0]
    if previous_member.member != current_member.member:
        return _non_comparable("INCOMPATIBLE_STOCK")
    previous_session = _completed_session(previous_packet)
    current_session = _completed_session(current_packet)
    if (
        previous.data_selection_time >= current.data_selection_time
        or previous_session is None
        or current_session is None
        or previous_session >= current_session
        or previous.evidence_known_at is None
        or current.evidence_known_at is None
        or previous.evidence_known_at >= current.evidence_known_at
        or previous.evidence_known_at > previous.acquisition_deadline
        or current.evidence_known_at > current.acquisition_deadline
    ):
        return _non_comparable("INVALID_TEMPORAL_ORDER")
    if (
        previous_member.price_basis is None
        or previous_member.price_basis != current_member.price_basis
    ):
        return _non_comparable("INCOMPATIBLE_PRICE_BASIS")
    try:
        facts = _comparison_facts(previous_packet, current_packet, previous.question)
        return CurrentStockObservationComparisonV1(
            CONTRACT_VERSION_V1,
            SCHEMA_IDENTITY_SHA256_V1,
            CONFIGURATION_IDENTITY_SHA256_V1,
            current_stock_observation_comparison_runtime_code_identity_v1(),
            "COMPARABLE",
            "COMPARISON_READY",
            previous.question,
            previous.symbol,
            previous_member.member.isin,
            previous_member.member.exchange,
            previous_member.price_basis,
            hashlib.sha256(previous_raw).hexdigest(),
            hashlib.sha256(current_raw).hexdigest(),
            previous.data_selection_time,
            current.data_selection_time,
            previous_session,
            current_session,
            previous.evidence_known_at,
            current.evidence_known_at,
            facts,
            _LIMITATIONS,
        )
    except (ArithmeticError, AttributeError, KeyError, TypeError, ValueError):
        return _non_comparable("OBSERVATION_INVALID")


def invalid_current_stock_observation_comparison_v1() -> (
    CurrentStockObservationComparisonV1
):
    """Return the closed typed result for an interrupted/invalid observation."""
    return _non_comparable("OBSERVATION_INVALID")


__all__ = [
    "CONTRACT_VERSION_V1",
    "CONFIGURATION_IDENTITY_SHA256_V1",
    "SCHEMA_IDENTITY_SHA256_V1",
    "CurrentStockObservationComparisonFactV1",
    "CurrentStockObservationComparisonV1",
    "compare_current_stock_observations_v1",
    "current_stock_observation_comparison_runtime_code_identity_v1",
    "invalid_current_stock_observation_comparison_v1",
]
