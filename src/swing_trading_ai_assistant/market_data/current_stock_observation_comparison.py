"""Compare two admitted current-stock V2 observations without raw market data."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final, Literal, TypeAlias, cast

from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockAdjustedMarketStructureFactV1,
    BharatStockCandleGeometryFactV2,
    BharatStockMemberFeatureV2,
    BharatStockPreviousCloseComparisonFactV2,
    BharatStockResearchPacketV2,
    validate_bharatstock_research_packet_v2,
)

from . import current_stock_research_v2 as current_research
from .current_stock_observation_comparison_runtime_identity_manifest import (
    CURRENT_STOCK_OBSERVATION_COMPARISON_RUNTIME_SOURCE_SHA256_V1,
)
from .current_stock_research_v2 import CurrentStockResearchResultV2
from .runtime_source_verifier import runtime_source_sha256

CONTRACT_VERSION_V1: Final = "current-stock-observation-comparison@v1"
SCHEMA_IDENTITY_SHA256_V1: Final = hashlib.sha256(
    b"current-stock-observation-comparison-schema@v1\n"
).hexdigest()
CONFIGURATION_IDENTITY_SHA256_V1: Final = hashlib.sha256(
    b"two-admitted-observations-one-stock-one-question-closed-facts@v1\n"
).hexdigest()
_SUPPORTED_QUESTIONS: Final = {"PRICE_BEHAVIOR", "CURRENT_STRUCTURE"}
_MAX_FACTS: Final = 12

ComparisonStatusV1: TypeAlias = Literal["COMPARABLE", "NON_COMPARABLE"]
ComparisonStateV1: TypeAlias = Literal[
    "UNCHANGED",
    "CHANGED",
    "NEWLY_AVAILABLE",
    "NEWLY_UNAVAILABLE",
    "UNAVAILABLE_IN_BOTH",
]


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
        module = ".".join(Path(relative).with_suffix("").parts[1:])
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
        if (
            type(self.path) is not str
            or not self.path
            or self.state
            not in {
                "UNCHANGED",
                "CHANGED",
                "NEWLY_AVAILABLE",
                "NEWLY_UNAVAILABLE",
                "UNAVAILABLE_IN_BOTH",
            }
            or type(self.previous_availability) is not str
            or not self.previous_availability
            or type(self.current_availability) is not str
            or not self.current_availability
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
            or (self.previous_availability == "OBSERVED")
            != (self.previous_value is not None)
            or (self.current_availability == "OBSERVED")
            != (self.current_value is not None)
            or (self.previous_availability == "OBSERVED")
            == (self.previous_reason is not None)
            or (self.current_availability == "OBSERVED")
            == (self.current_reason is not None)
            or (self.delta is not None and self.state not in {"CHANGED", "UNCHANGED"})
        ):
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
        if (
            self.contract_version != CONTRACT_VERSION_V1
            or self.schema_identity_sha256 != SCHEMA_IDENTITY_SHA256_V1
            or self.configuration_identity_sha256 != CONFIGURATION_IDENTITY_SHA256_V1
            or self.runtime_code_identity_sha256
            != current_stock_observation_comparison_runtime_code_identity_v1()
            or self.status not in {"COMPARABLE", "NON_COMPARABLE"}
            or type(self.code) is not str
            or not self.code
            or type(self.facts) is not tuple
            or len(self.facts) > _MAX_FACTS
            or any(
                type(item) is not CurrentStockObservationComparisonFactV1
                for item in self.facts
            )
            or len({item.path for item in self.facts}) != len(self.facts)
            or type(self.limitations) is not tuple
            or not self.limitations
            or any(type(item) is not str or not item for item in self.limitations)
            or (self.status == "COMPARABLE") != bool(self.facts)
            or (
                self.status == "COMPARABLE"
                and any(
                    value is None
                    for value in (
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
                )
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


_LIMITATIONS: Final = (
    "comparison_of_supplied_admitted_facts_only",
    "not_trade_eligibility",
    "not_recommendation_or_scoring",
    "no_raw_ohlc_or_recalculation_by_assistant",
)


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
    validate_bharatstock_research_packet_v2(result.packet)
    return raw, result.packet


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


def compare_current_stock_observations_v1(
    previous: CurrentStockResearchResultV2,
    current: CurrentStockResearchResultV2,
) -> CurrentStockObservationComparisonV1:
    """Compare exactly two admitted V2 observations in deterministic order."""
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
    previous_by_feature = {item.feature: item for item in previous_member.features}
    current_by_feature = {item.feature: item for item in current_member.features}
    facts: list[CurrentStockObservationComparisonFactV1] = []
    for feature_name in previous_packet.requested_features:
        previous_feature = previous_by_feature[feature_name]
        current_feature = current_by_feature[feature_name]
        previous_values = _feature_values(previous.question, previous_feature)
        current_values = dict(_feature_values(current.question, current_feature))
        facts.extend(
            _fact(
                path,
                previous_feature,
                current_feature,
                value,
                current_values[path],
            )
            for path, value in previous_values
        )
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
        tuple(facts),
        _LIMITATIONS,
    )


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
