"""Automated, source-bound G03 safety eligibility for one retained observation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Final, Protocol
from zoneinfo import ZoneInfo

from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockResearchPacketV2,
    validate_bharatstock_research_packet_v2,
)

from .bharatstock import BharatStockClient, BharatStockHistory, BharatStockInstrument
from .corporate_actions import (
    CorporateActionSnapshotV1,
    UpstoxCorporateActionsClientV1,
)
from .credentials import AccessToken, EnvironmentAccessTokenProvider
from .current_stock_research_v2 import CurrentStockResearchResultV2
from .http import UrllibHttpTransport
from .runtime_source_verifier import runtime_source_sha256
from .stock_eligibility_v3_runtime_identity_manifest import (
    STOCK_ELIGIBILITY_RUNTIME_SOURCE_SHA256_V3,
)
from .stock_observations import read_stock_observation_v1
from .upstox_full_quote_v3 import UpstoxFullQuoteV3, UpstoxFullQuoteV3Client

SCHEMA: Final = "stock-eligibility@v3"
SAFETY_POLICY_IDENTIFIER: Final = "supported-signal-safety-policy@v1"
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_IST: Final = ZoneInfo("Asia/Kolkata")
_QUOTE_MAX_AGE: Final = timedelta(minutes=15)
_HISTORY_CALENDAR_DAYS: Final = 420
_MIN_HISTORY_SESSIONS: Final = 252
_TURNOVER_WINDOW: Final = 20
_MIN_MEDIAN_TURNOVER: Final = Decimal("10000000")
_MIN_PRICE: Final = Decimal("20")
_MIN_CIRCUIT_DISTANCE: Final = Decimal("0.02")
_MAX_RELATIVE_SPREAD: Final = Decimal("0.02")
_ACTION_BLACKOUT_DAYS: Final = 7
_MAX_RESULT_BYTES: Final = 128 * 1024
_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/stock_eligibility_v3.py",
    "src/swing_trading_ai_assistant/market_data/bharatstock.py",
    "src/swing_trading_ai_assistant/market_data/corporate_actions.py",
    "src/swing_trading_ai_assistant/market_data/credentials.py",
    "src/swing_trading_ai_assistant/market_data/http.py",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py",
    "src/swing_trading_ai_assistant/market_data/stock_observations.py",
    "src/swing_trading_ai_assistant/market_data/upstox_full_quote_v3.py",
)
_LIMITATIONS: Final = (
    "This is a bounded research-safety screen, not an order, target, position size, profitability claim or suitability assessment.",
    "Passing the current book screen does not establish fill probability, market impact or execution capacity.",
    "The corporate-action screen covers only provider-supported dividends, bonus issues, splits and rights events; it does not clear broader event, disclosure, surveillance or news risk.",
    "Provider-observable history supports only the stated rolling measurements; it does not prove listing age or future availability.",
)
_POLICY: Final = {
    "identifier": SAFETY_POLICY_IDENTIFIER,
    "history_calendar_days": _HISTORY_CALENDAR_DAYS,
    "minimum_history_sessions": _MIN_HISTORY_SESSIONS,
    "turnover_window_sessions": _TURNOVER_WINDOW,
    "minimum_median_turnover_inr": "10000000",
    "minimum_price_inr": "20",
    "minimum_circuit_distance": "0.02",
    "maximum_relative_spread": "0.02",
    "corporate_action_blackout_days": _ACTION_BLACKOUT_DAYS,
    "quote_maximum_age_seconds": int(_QUOTE_MAX_AGE.total_seconds()),
}


class _V3Providers(Protocol):
    def get_quote(self, isin: str, symbol: str) -> UpstoxFullQuoteV3: ...

    def get_history(
        self, instrument: BharatStockInstrument, end: date
    ) -> BharatStockHistory: ...

    def get_corporate_actions(self, isin: str) -> CorporateActionSnapshotV1: ...


@dataclass(frozen=True, slots=True)
class _AdmittedObservation:
    symbol: str
    isin: str
    instrument: BharatStockInstrument
    latest_completed_session: date
    mapping_identity_sha256: str
    structure_source_identity_sha256: str
    capture_revision_identity_sha256: str
    schedule_identity_sha256: str


class _LiveProviders:
    """Lazily construct the existing configured provider clients for one run."""

    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        self._clock = clock
        self._token_provider: EnvironmentAccessTokenProvider | None = None
        self._quote_client: UpstoxFullQuoteV3Client | None = None
        self._actions_client: UpstoxCorporateActionsClientV1 | None = None
        self._history_client: BharatStockClient | None = None

    def _access_token(self) -> AccessToken:
        if self._token_provider is None:
            self._token_provider = EnvironmentAccessTokenProvider()
        return self._token_provider.get_access_token()

    def get_quote(self, isin: str, symbol: str) -> UpstoxFullQuoteV3:
        if self._quote_client is None:
            self._quote_client = UpstoxFullQuoteV3Client(
                UrllibHttpTransport(max_body_bytes=1024 * 1024), clock=self._clock
            )
        return self._quote_client.fetch(isin, symbol, self._access_token())

    def get_history(
        self, instrument: BharatStockInstrument, end: date
    ) -> BharatStockHistory:
        if self._history_client is None:
            self._history_client = BharatStockClient()
        return self._history_client.history(
            instrument, end - timedelta(days=_HISTORY_CALENDAR_DAYS - 1), end
        )

    def get_corporate_actions(self, isin: str) -> CorporateActionSnapshotV1:
        if self._actions_client is None:
            self._actions_client = UpstoxCorporateActionsClientV1(
                UrllibHttpTransport(max_body_bytes=1024 * 1024), clock=self._clock
            )
        return self._actions_client.fetch_strict_with_access_token(
            isin, self._access_token()
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _runtime_identity() -> str:
    if tuple(STOCK_ELIGIBILITY_RUNTIME_SOURCE_SHA256_V3) != _SOURCES:
        raise ValueError("stock eligibility V3 runtime inventory invalid")
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in STOCK_ELIGIBILITY_RUNTIME_SOURCE_SHA256_V3.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("stock eligibility V3 runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def _valid_request(storage_root: object, observation: object) -> tuple[Path, str]:
    if (
        not isinstance(storage_root, Path)
        or not storage_root.is_absolute()
        or type(observation) is not str
        or _DIGEST.fullmatch(observation) is None
    ):
        raise ValueError("invalid observation request")
    return storage_root, observation


def _admit_observation(
    observation: object,
) -> _AdmittedObservation | None:
    if type(observation) is not CurrentStockResearchResultV2:
        raise ValueError("invalid admitted observation")
    observation.canonical_json_bytes()
    if observation.question != "CURRENT_STRUCTURE":
        raise ValueError("current structure observation required")
    if observation.status != "READY" or observation.packet is None:
        return None
    if type(observation.packet) is not BharatStockResearchPacketV2:
        raise ValueError("unsupported current structure packet")
    packet = validate_bharatstock_research_packet_v2(observation.packet)
    if len(packet.members) != 1 or len(packet.mapping_projection.members) != 1:
        raise ValueError("invalid current structure cohort")
    mapping = packet.mapping_projection.members[0]
    member = packet.members[0]
    feature = member.feature("MARKET_STRUCTURE")
    source = packet.source("MARKET_STRUCTURE")
    if not (
        feature is not None
        and source is not None
        and feature.availability == "OBSERVED"
        and feature.support == "SUPPORTED"
        and feature.comparability == "SUPPORTED"
    ):
        return None
    bars = feature.source_bars
    sessions = source.admitted_sessions
    if (
        len(bars) != 21
        or len(sessions) != 21
        or tuple(item.session for item in bars) != sessions
        or tuple(sorted(set(sessions))) != sessions
        or observation.evidence_known_at != source.known_at
        or source.decision_cutoff != observation.acquisition_deadline
        or source.price_basis != packet.price_basis
        or source.volume_basis != "SOURCE_REPORTED"
        or (mapping.isin, mapping.exchange, mapping.effective_symbol)
        != (member.member.isin, member.member.exchange, member.member.symbol)
        or mapping.exchange != "NSE"
        or mapping.instrument_type != "EQUITY"
        or mapping.segment != "EQ"
        or observation.symbol != mapping.effective_symbol
        or any(
            not (
                item.low <= item.open <= item.high
                and item.low <= item.close <= item.high
                and item.open > 0
                and item.high > 0
                and item.low > 0
                and item.close > 0
                and type(item.volume) is int
                and item.volume > 0
            )
            for item in bars
        )
    ):
        raise ValueError("current structure evidence invalid")
    if type(mapping.instrument) is not BharatStockInstrument:
        raise ValueError("invalid current structure instrument")
    return _AdmittedObservation(
        mapping.effective_symbol,
        mapping.isin,
        mapping.instrument,
        sessions[-1],
        mapping.mapping_identity_sha256,
        source.source_identity_sha256,
        source.capture_revision_identity_sha256,
        source.schedule_identity_sha256,
    )


def _entry(
    rule_id: str,
    outcome: str,
    reason_code: str,
    explanation: str,
    evidence_references: Mapping[str, object] | None = None,
    derived_measurements: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "outcome": outcome,
        "reason_code": reason_code,
        "explanation": explanation,
        "evidence_references": {}
        if evidence_references is None
        else dict(evidence_references),
        "derived_measurements": (
            {} if derived_measurements is None else dict(derived_measurements)
        ),
    }


def _not_evaluated(rule_id: str, prior_rule_id: str) -> dict[str, object]:
    return _entry(
        rule_id,
        "NOT_EVALUATED",
        "EARLIER_REQUIRED_RULE_STOPPED_EVALUATION",
        f"This rule was not evaluated because {prior_rule_id} stopped the bounded safety run.",
        {"stopping_rule_id": prior_rule_id},
    )


def _append_not_evaluated(
    ledger: list[dict[str, object]],
    rule_ids: tuple[str, ...],
    stopping_rule_id: str,
) -> None:
    ledger.extend(_not_evaluated(rule_id, stopping_rule_id) for rule_id in rule_ids)


def _base_evidence(context: _AdmittedObservation) -> dict[str, object]:
    return {
        "mapping_identity_sha256": context.mapping_identity_sha256,
        "market_structure_source_identity_sha256": context.structure_source_identity_sha256,
        "capture_revision_identity_sha256": context.capture_revision_identity_sha256,
        "schedule_identity_sha256": context.schedule_identity_sha256,
        "latest_completed_session": context.latest_completed_session.isoformat(),
    }


def _finalize(
    *,
    status: str,
    symbol: str | None,
    observation_identity_sha256: str,
    runtime: str,
    ledger: list[dict[str, object]],
    verified_evidence: dict[str, object] | None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "schema": SCHEMA,
        "status": status,
        "safety_policy": {
            "identifier": SAFETY_POLICY_IDENTIFIER,
            "identity_sha256": _digest(_POLICY),
        },
        "symbol": symbol,
        "observation_identity_sha256": observation_identity_sha256,
        "verified_evidence": verified_evidence,
        "explanation_ledger": ledger,
        "limitations": list(_LIMITATIONS),
        "runtime_code_identity_sha256": runtime,
    }
    result["result_identity_sha256"] = _digest(result)
    if len(_canonical_bytes(result)) > _MAX_RESULT_BYTES:
        raise ValueError("stock eligibility V3 result exceeds output limit")
    return result


def _unknown(
    *,
    symbol: str | None,
    observation_identity_sha256: str,
    runtime: str,
    ledger: list[dict[str, object]],
    verified_evidence: dict[str, object] | None,
    remaining: tuple[str, ...],
    stopping_rule_id: str,
) -> dict[str, object]:
    _append_not_evaluated(ledger, remaining, stopping_rule_id)
    return _finalize(
        status="UNKNOWN",
        symbol=symbol,
        observation_identity_sha256=observation_identity_sha256,
        runtime=runtime,
        ledger=ledger,
        verified_evidence=verified_evidence,
    )


def _ineligible(
    *,
    symbol: str,
    observation_identity_sha256: str,
    runtime: str,
    ledger: list[dict[str, object]],
    verified_evidence: dict[str, object],
    remaining: tuple[str, ...],
    stopping_rule_id: str,
) -> dict[str, object]:
    _append_not_evaluated(ledger, remaining, stopping_rule_id)
    return _finalize(
        status="INELIGIBLE",
        symbol=symbol,
        observation_identity_sha256=observation_identity_sha256,
        runtime=runtime,
        ledger=ledger,
        verified_evidence=verified_evidence,
    )


def _quote_binding(
    quote: object, context: _AdmittedObservation
) -> UpstoxFullQuoteV3 | None:
    if type(quote) is not UpstoxFullQuoteV3:
        return None
    try:
        quote.__post_init__()
    except (TypeError, ValueError):
        return None
    if (
        quote.instrument_key != f"NSE_EQ|{context.isin}"
        or quote.symbol != context.symbol
    ):
        return None
    return quote


def _quote_integrity(
    quote: UpstoxFullQuoteV3, latest_session: date
) -> tuple[bool, str, dict[str, object]]:
    age = quote.retrieved_at - quote.quote_timestamp
    quote_session = quote.quote_timestamp.astimezone(_IST).date()
    details: dict[str, object] = {
        "quote_timestamp": _instant(quote.quote_timestamp),
        "quote_retrieved_at": _instant(quote.retrieved_at),
        "quote_session": quote_session.isoformat(),
        "required_completed_session": latest_session.isoformat(),
        "quote_age_seconds": int(age.total_seconds()),
    }
    if age < timedelta() or age > _QUOTE_MAX_AGE:
        return False, "QUOTE_TIMESTAMP_OUTSIDE_FRESHNESS_WINDOW", details
    if quote_session != latest_session:
        return False, "QUOTE_SESSION_DOES_NOT_MATCH_RETAINED_SESSION", details
    if not quote.lower_circuit_limit < quote.last_price < quote.upper_circuit_limit:
        return False, "QUOTE_PRICE_OUTSIDE_CIRCUIT_BOUNDS", details
    return True, "CURRENT_QUOTE_IS_FRESH_AND_INTERNALLY_COHERENT", details


def _decimal_exponent(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    if type(exponent) is not int:
        raise ValueError("invalid finite decimal")
    return exponent


def _decimal_precision(*values: Decimal, extra_digits: int = 0) -> int:
    """Return enough significant digits for exact bounded Decimal arithmetic."""
    return max(
        28,
        sum(len(value.as_tuple().digits) for value in values) + extra_digits,
        max(value.adjusted() for value in values)
        - min(_decimal_exponent(value) for value in values)
        + 1
        + extra_digits,
    )


def _decimal_product(left: Decimal, right: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = _decimal_precision(left, right)
        return left * right


def _decimal_sum(left: Decimal, right: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = _decimal_precision(left, right)
        return left + right


def _decimal_difference(left: Decimal, right: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = _decimal_precision(left, right)
        return left - right


def _decimal_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = _decimal_precision(numerator, denominator, extra_digits=16)
        return numerator / denominator


def _scaled_decimal_at_most(
    left: Decimal, left_factor: int, right: Decimal, right_factor: int
) -> bool:
    """Compare exact decimal products without using a rounded quotient."""
    return _decimal_product(left, Decimal(left_factor)) <= _decimal_product(
        right, Decimal(right_factor)
    )


def _price_and_circuit_measurements(
    quote: UpstoxFullQuoteV3,
) -> dict[str, object]:
    lower_distance = _decimal_ratio(
        _decimal_difference(quote.last_price, quote.lower_circuit_limit),
        quote.last_price,
    )
    upper_distance = _decimal_ratio(
        _decimal_difference(quote.upper_circuit_limit, quote.last_price),
        quote.last_price,
    )
    return {
        "last_price_inr": _decimal_text(quote.last_price),
        "minimum_price_inr": _decimal_text(_MIN_PRICE),
        "lower_circuit_distance": _decimal_text(lower_distance),
        "upper_circuit_distance": _decimal_text(upper_distance),
        "minimum_circuit_distance": _decimal_text(_MIN_CIRCUIT_DISTANCE),
        "lower_circuit_distance_meets_minimum": _scaled_decimal_at_most(
            quote.lower_circuit_limit, 100, quote.last_price, 98
        ),
        "upper_circuit_distance_meets_minimum": _scaled_decimal_at_most(
            quote.last_price, 102, quote.upper_circuit_limit, 100
        ),
    }


def _price_and_circuit_passes(quote: UpstoxFullQuoteV3) -> bool:
    return (
        quote.last_price >= _MIN_PRICE
        and _scaled_decimal_at_most(
            quote.lower_circuit_limit, 100, quote.last_price, 98
        )
        and _scaled_decimal_at_most(
            quote.last_price, 102, quote.upper_circuit_limit, 100
        )
    )


def _price_and_circuit_failure(quote: UpstoxFullQuoteV3) -> tuple[str, str]:
    if quote.last_price < _MIN_PRICE:
        return (
            "LAST_PRICE_BELOW_MINIMUM_SAFETY_FLOOR",
            "The observed last price is below the fixed INR 20 research-safety floor.",
        )
    if not _scaled_decimal_at_most(
        quote.lower_circuit_limit, 100, quote.last_price, 98
    ):
        return (
            "LOWER_CIRCUIT_DISTANCE_BELOW_SAFETY_POLICY",
            "The observed lower circuit is closer than the fixed 2% research-safety distance.",
        )
    return (
        "UPPER_CIRCUIT_DISTANCE_BELOW_SAFETY_POLICY",
        "The observed upper circuit is closer than the fixed 2% research-safety distance.",
    )


def _book_measurements(quote: UpstoxFullQuoteV3) -> dict[str, object] | None:
    if quote.best_bid <= 0 or quote.best_ask <= 0 or quote.best_bid >= quote.best_ask:
        return None
    midpoint = _decimal_ratio(_decimal_sum(quote.best_bid, quote.best_ask), Decimal(2))
    if midpoint <= 0:
        return None
    relative_spread = _decimal_ratio(
        _decimal_difference(quote.best_ask, quote.best_bid), midpoint
    )
    return {
        "best_bid_inr": _decimal_text(quote.best_bid),
        "best_ask_inr": _decimal_text(quote.best_ask),
        "relative_spread": _decimal_text(relative_spread),
        "maximum_relative_spread": _decimal_text(_MAX_RELATIVE_SPREAD),
        "relative_spread_meets_maximum": _scaled_decimal_at_most(
            quote.best_ask, 99, quote.best_bid, 101
        ),
        "total_buy_quantity": quote.total_buy_quantity,
        "total_sell_quantity": quote.total_sell_quantity,
    }


def _book_passes(quote: UpstoxFullQuoteV3, measurements: dict[str, object]) -> bool:
    del measurements
    return (
        quote.total_buy_quantity > 0
        and quote.total_sell_quantity > 0
        and _scaled_decimal_at_most(quote.best_ask, 99, quote.best_bid, 101)
    )


def _book_failure(quote: UpstoxFullQuoteV3) -> tuple[str, str]:
    if quote.total_buy_quantity <= 0:
        return (
            "CURRENT_BOOK_BUY_QUANTITY_NOT_POSITIVE",
            "The observed current book has no positive aggregate buy quantity.",
        )
    if quote.total_sell_quantity <= 0:
        return (
            "CURRENT_BOOK_SELL_QUANTITY_NOT_POSITIVE",
            "The observed current book has no positive aggregate sell quantity.",
        )
    return (
        "CURRENT_BOOK_RELATIVE_SPREAD_EXCEEDS_SAFETY_POLICY",
        "The observed best-bid/best-ask relative spread exceeds the fixed 2% research-safety limit.",
    )


def _history_valid(
    value: object, context: _AdmittedObservation
) -> BharatStockHistory | None:
    if type(value) is not BharatStockHistory:
        return None
    try:
        value.__post_init__()
        for row in value.rows:
            row.__post_init__()
    except (TypeError, ValueError):
        return None
    if (
        value.instrument != context.instrument
        or value.request_count != 2
        or len(value.response_sha256s) != 2
        or value.rows[-1].session != context.latest_completed_session
        or any(row.session > context.latest_completed_session for row in value.rows)
    ):
        return None
    return value


def _turnover_values(history: BharatStockHistory) -> tuple[Decimal, ...]:
    values = tuple(
        _decimal_product(row.close, Decimal(row.volume))
        for row in history.rows[-_TURNOVER_WINDOW:]
    )
    if len(values) != _TURNOVER_WINDOW:
        raise ValueError("insufficient turnover rows")
    return values


def _history_measurements(
    history: BharatStockHistory,
) -> tuple[dict[str, object], bool]:
    ordered = tuple(sorted(_turnover_values(history)))
    median_numerator = _decimal_sum(ordered[9], ordered[10])
    median = _decimal_ratio(median_numerator, Decimal(2))
    meets_minimum = median_numerator >= _decimal_product(
        _MIN_MEDIAN_TURNOVER, Decimal(2)
    )
    return (
        {
            "history_session_count": len(history.rows),
            "turnover_window_sessions": _TURNOVER_WINDOW,
            "median_turnover_inr": _decimal_text(median),
            "minimum_median_turnover_inr": _decimal_text(_MIN_MEDIAN_TURNOVER),
            "median_turnover_meets_minimum": meets_minimum,
        },
        meets_minimum,
    )


def _actions_valid(
    value: object, context: _AdmittedObservation
) -> CorporateActionSnapshotV1 | None:
    if type(value) is not CorporateActionSnapshotV1:
        return None
    try:
        value.__post_init__()
    except (TypeError, ValueError):
        return None
    if value.isin != context.isin:
        return None
    return value


def _blackout_event(
    actions: CorporateActionSnapshotV1, latest_session: date
) -> dict[str, object] | None:
    earliest = latest_session - timedelta(days=_ACTION_BLACKOUT_DAYS)
    latest = latest_session + timedelta(days=_ACTION_BLACKOUT_DAYS)
    candidates = tuple(
        event for event in actions.events if earliest <= event.effective_date <= latest
    )
    if not candidates:
        return None
    event = candidates[0]
    return {
        "event_identity_sha256": event.event_digest_sha256,
        "kind": event.kind.value,
        "effective_date": event.effective_date.isoformat(),
    }


def _evaluate_stock_eligibility_from_admitted_record_v3(  # noqa: C901 - explicit bounded provider safety precedence
    observation: object,
    observation_identity_sha256: str,
    *,
    providers: _V3Providers,
    clock: Callable[[], datetime],
) -> dict[str, object]:
    """Evaluate one typed observation using the frozen V3 provider policy.

    This private seam exists solely for deterministic adapter tests.  Public callers
    can supply only an absolute storage root and an immutable observation handle.
    """
    if (
        type(observation_identity_sha256) is not str
        or _DIGEST.fullmatch(observation_identity_sha256) is None
        or not callable(clock)
    ):
        raise ValueError("invalid admitted observation")
    runtime = _runtime_identity()
    context = _admit_observation(observation)
    symbol = getattr(observation, "symbol", None)
    if type(symbol) is not str:
        raise ValueError("invalid admitted observation")
    rule_ids = (
        "CURRENT_UPSTOX_QUOTE_BINDING",
        "CURRENT_QUOTE_FRESHNESS_AND_INTEGRITY",
        "LOW_PRICE_AND_CIRCUIT_DISTANCE",
        "CURRENT_BOOK_LIQUIDITY",
        "PROVIDER_OBSERVABLE_HISTORY",
        "ROLLING_CASH_TURNOVER",
        "SUPPORTED_CORPORATE_ACTION_BLACKOUT",
    )
    ledger: list[dict[str, object]] = []
    if context is None:
        ledger.append(
            _entry(
                "CANONICAL_NSE_EQUITY_IDENTITY",
                "UNKNOWN",
                "CURRENT_STRUCTURE_EVIDENCE_UNAVAILABLE",
                "The retained observation did not provide an admitted one-member NSE equity current-structure record.",
            )
        )
        return _unknown(
            symbol=symbol,
            observation_identity_sha256=observation_identity_sha256,
            runtime=runtime,
            ledger=ledger,
            verified_evidence=None,
            remaining=rule_ids,
            stopping_rule_id="CANONICAL_NSE_EQUITY_IDENTITY",
        )
    evidence = _base_evidence(context)
    ledger.append(
        _entry(
            "CANONICAL_NSE_EQUITY_IDENTITY",
            "PASS",
            "RETAINED_NSE_EQUITY_IDENTITY_BOUND",
            "The retained current-structure observation binds one NSE equity symbol and ISIN through its admitted mapping and structure source.",
            {
                "mapping_identity_sha256": context.mapping_identity_sha256,
                "market_structure_source_identity_sha256": (
                    context.structure_source_identity_sha256
                ),
            },
            {"latest_completed_session": context.latest_completed_session.isoformat()},
        )
    )
    try:
        quote_value = providers.get_quote(context.isin, context.symbol)
    except BaseException:  # noqa: BLE001 - closed provider and interruption boundary
        ledger.append(
            _entry(
                "CURRENT_UPSTOX_QUOTE_BINDING",
                "UNKNOWN",
                "UPSTOX_QUOTE_UNAVAILABLE",
                "A current exact-identity Upstox quote could not be obtained, so the safety screen cannot substitute another source or security.",
            )
        )
        return _unknown(
            symbol=context.symbol,
            observation_identity_sha256=observation_identity_sha256,
            runtime=runtime,
            ledger=ledger,
            verified_evidence=evidence,
            remaining=rule_ids[1:],
            stopping_rule_id="CURRENT_UPSTOX_QUOTE_BINDING",
        )
    quote = _quote_binding(quote_value, context)
    if quote is None:
        ledger.append(
            _entry(
                "CURRENT_UPSTOX_QUOTE_BINDING",
                "UNKNOWN",
                "UPSTOX_QUOTE_IDENTITY_OR_SCHEMA_INVALID",
                "The quote response did not bind exactly to the retained NSE equity identity, so it cannot be used for this observation.",
            )
        )
        return _unknown(
            symbol=context.symbol,
            observation_identity_sha256=observation_identity_sha256,
            runtime=runtime,
            ledger=ledger,
            verified_evidence=evidence,
            remaining=rule_ids[1:],
            stopping_rule_id="CURRENT_UPSTOX_QUOTE_BINDING",
        )
    evidence.update(
        quote_identity_sha256=quote.quote_identity_sha256,
        quote_response_sha256=quote.response_sha256,
        quote_timestamp=_instant(quote.quote_timestamp),
        quote_retrieved_at=_instant(quote.retrieved_at),
        current_quote_price_inr=_decimal_text(quote.last_price),
    )
    ledger.append(
        _entry(
            "CURRENT_UPSTOX_QUOTE_BINDING",
            "PASS",
            "UPSTOX_QUOTE_EXACTLY_BINDS_RETAINED_IDENTITY",
            "The Upstox quote instrument key and symbol exactly match the retained NSE equity ISIN and effective symbol.",
            {"quote_identity_sha256": quote.quote_identity_sha256},
        )
    )
    integrity_ok, integrity_code, integrity_measurements = _quote_integrity(
        quote, context.latest_completed_session
    )
    if not integrity_ok:
        ledger.append(
            _entry(
                "CURRENT_QUOTE_FRESHNESS_AND_INTEGRITY",
                "UNKNOWN",
                integrity_code,
                "The current quote was not sufficiently fresh, session-aligned and internally coherent for a source-bound safety decision.",
                {"quote_identity_sha256": quote.quote_identity_sha256},
                integrity_measurements,
            )
        )
        return _unknown(
            symbol=context.symbol,
            observation_identity_sha256=observation_identity_sha256,
            runtime=runtime,
            ledger=ledger,
            verified_evidence=evidence,
            remaining=rule_ids[2:],
            stopping_rule_id="CURRENT_QUOTE_FRESHNESS_AND_INTEGRITY",
        )
    ledger.append(
        _entry(
            "CURRENT_QUOTE_FRESHNESS_AND_INTEGRITY",
            "PASS",
            integrity_code,
            "The quote timestamp is fresh relative to provider retrieval, aligns to the retained completed session and has coherent circuit bounds.",
            {"quote_identity_sha256": quote.quote_identity_sha256},
            integrity_measurements,
        )
    )
    price_measurements = _price_and_circuit_measurements(quote)
    if not _price_and_circuit_passes(quote):
        price_reason, price_explanation = _price_and_circuit_failure(quote)
        ledger.append(
            _entry(
                "LOW_PRICE_AND_CIRCUIT_DISTANCE",
                "FAIL",
                price_reason,
                price_explanation,
                {"quote_identity_sha256": quote.quote_identity_sha256},
                price_measurements,
            )
        )
        return _ineligible(
            symbol=context.symbol,
            observation_identity_sha256=observation_identity_sha256,
            runtime=runtime,
            ledger=ledger,
            verified_evidence=evidence,
            remaining=rule_ids[3:],
            stopping_rule_id="LOW_PRICE_AND_CIRCUIT_DISTANCE",
        )
    ledger.append(
        _entry(
            "LOW_PRICE_AND_CIRCUIT_DISTANCE",
            "PASS",
            "PRICE_AND_CIRCUIT_DISTANCE_MEET_SAFETY_POLICY",
            "The observed quote meets the fixed price floor and remains at least the required distance from both circuit limits.",
            {"quote_identity_sha256": quote.quote_identity_sha256},
            price_measurements,
        )
    )
    book_measurements = _book_measurements(quote)
    if book_measurements is None:
        ledger.append(
            _entry(
                "CURRENT_BOOK_LIQUIDITY",
                "UNKNOWN",
                "CURRENT_BOOK_IS_INTERNALLY_INCOHERENT",
                "The quote did not contain a coherent positive best bid and ask pair, so a liquidity screen cannot be calculated safely.",
                {"quote_identity_sha256": quote.quote_identity_sha256},
            )
        )
        return _unknown(
            symbol=context.symbol,
            observation_identity_sha256=observation_identity_sha256,
            runtime=runtime,
            ledger=ledger,
            verified_evidence=evidence,
            remaining=rule_ids[4:],
            stopping_rule_id="CURRENT_BOOK_LIQUIDITY",
        )
    if not _book_passes(quote, book_measurements):
        book_reason, book_explanation = _book_failure(quote)
        ledger.append(
            _entry(
                "CURRENT_BOOK_LIQUIDITY",
                "FAIL",
                book_reason,
                book_explanation,
                {"quote_identity_sha256": quote.quote_identity_sha256},
                book_measurements,
            )
        )
        return _ineligible(
            symbol=context.symbol,
            observation_identity_sha256=observation_identity_sha256,
            runtime=runtime,
            ledger=ledger,
            verified_evidence=evidence,
            remaining=rule_ids[4:],
            stopping_rule_id="CURRENT_BOOK_LIQUIDITY",
        )
    ledger.append(
        _entry(
            "CURRENT_BOOK_LIQUIDITY",
            "PASS",
            "CURRENT_BOOK_MEETS_SAFETY_POLICY",
            "The observed best bid and ask are ordered, both book sides have positive total quantity and the relative spread meets the fixed limit.",
            {"quote_identity_sha256": quote.quote_identity_sha256},
            book_measurements,
        )
    )
    try:
        history_value = providers.get_history(
            context.instrument, context.latest_completed_session
        )
    except BaseException:  # noqa: BLE001 - closed provider and interruption boundary
        ledger.append(
            _entry(
                "PROVIDER_OBSERVABLE_HISTORY",
                "UNKNOWN",
                "BHARATSTOCK_HISTORY_UNAVAILABLE",
                "The bounded BharatStock completed-history request was unavailable, so no substitute history is used.",
            )
        )
        return _unknown(
            symbol=context.symbol,
            observation_identity_sha256=observation_identity_sha256,
            runtime=runtime,
            ledger=ledger,
            verified_evidence=evidence,
            remaining=rule_ids[5:],
            stopping_rule_id="PROVIDER_OBSERVABLE_HISTORY",
        )
    history = _history_valid(history_value, context)
    if history is None or len(history.rows) < _MIN_HISTORY_SESSIONS:
        ledger.append(
            _entry(
                "PROVIDER_OBSERVABLE_HISTORY",
                "UNKNOWN",
                "BHARATSTOCK_HISTORY_INSUFFICIENT_OR_MISALIGNED",
                "The provider history did not supply at least 252 valid completed sessions ending at the retained decision session.",
                None,
                {
                    "minimum_history_sessions": _MIN_HISTORY_SESSIONS,
                    "observed_history_sessions": (
                        None if history is None else len(history.rows)
                    ),
                },
            )
        )
        return _unknown(
            symbol=context.symbol,
            observation_identity_sha256=observation_identity_sha256,
            runtime=runtime,
            ledger=ledger,
            verified_evidence=evidence,
            remaining=rule_ids[5:],
            stopping_rule_id="PROVIDER_OBSERVABLE_HISTORY",
        )
    history_references = {
        "history_response_sha256s": list(history.response_sha256s),
        "history_retrieved_at": _instant(history.retrieved_at),
    }
    evidence.update(history_references)
    evidence["history_session_count"] = len(history.rows)
    ledger.append(
        _entry(
            "PROVIDER_OBSERVABLE_HISTORY",
            "PASS",
            "BHARATSTOCK_HISTORY_COVERS_RETAINED_SESSION",
            "The bounded BharatStock history is identity-bound, ordered and ends at the retained completed decision session with the required number of rows.",
            history_references,
            {
                "history_session_count": len(history.rows),
                "minimum_history_sessions": _MIN_HISTORY_SESSIONS,
            },
        )
    )
    turnover_measurements, turnover_meets_minimum = _history_measurements(history)
    evidence["median_turnover_inr"] = turnover_measurements["median_turnover_inr"]
    if not turnover_meets_minimum:
        ledger.append(
            _entry(
                "ROLLING_CASH_TURNOVER",
                "FAIL",
                "ROLLING_CASH_TURNOVER_BELOW_SAFETY_POLICY",
                "The median source-reported close-times-volume value across the newest 20 completed sessions is below the fixed research-liquidity threshold.",
                history_references,
                turnover_measurements,
            )
        )
        return _ineligible(
            symbol=context.symbol,
            observation_identity_sha256=observation_identity_sha256,
            runtime=runtime,
            ledger=ledger,
            verified_evidence=evidence,
            remaining=rule_ids[6:],
            stopping_rule_id="ROLLING_CASH_TURNOVER",
        )
    ledger.append(
        _entry(
            "ROLLING_CASH_TURNOVER",
            "PASS",
            "ROLLING_CASH_TURNOVER_MEETS_SAFETY_POLICY",
            "The median source-reported close-times-volume value across the newest 20 completed sessions meets the fixed research-liquidity threshold.",
            history_references,
            turnover_measurements,
        )
    )
    try:
        actions_value = providers.get_corporate_actions(context.isin)
    except BaseException:  # noqa: BLE001 - closed provider and interruption boundary
        ledger.append(
            _entry(
                "SUPPORTED_CORPORATE_ACTION_BLACKOUT",
                "UNKNOWN",
                "UPSTOX_CORPORATE_ACTIONS_UNAVAILABLE",
                "The strict Upstox corporate-action request was unavailable, so the supported event-risk screen cannot be cleared.",
            )
        )
        return _unknown(
            symbol=context.symbol,
            observation_identity_sha256=observation_identity_sha256,
            runtime=runtime,
            ledger=ledger,
            verified_evidence=evidence,
            remaining=(),
            stopping_rule_id="SUPPORTED_CORPORATE_ACTION_BLACKOUT",
        )
    actions = _actions_valid(actions_value, context)
    if actions is None:
        ledger.append(
            _entry(
                "SUPPORTED_CORPORATE_ACTION_BLACKOUT",
                "UNKNOWN",
                "UPSTOX_CORPORATE_ACTIONS_INVALID_OR_STALE",
                "The corporate-action response was not an exact, current snapshot for the retained ISIN, so the supported blackout screen cannot be cleared.",
            )
        )
        return _unknown(
            symbol=context.symbol,
            observation_identity_sha256=observation_identity_sha256,
            runtime=runtime,
            ledger=ledger,
            verified_evidence=evidence,
            remaining=(),
            stopping_rule_id="SUPPORTED_CORPORATE_ACTION_BLACKOUT",
        )
    actions_identity = hashlib.sha256(actions.canonical_json_bytes()).hexdigest()
    actions_references = {
        "corporate_actions_snapshot_identity_sha256": actions_identity,
        "corporate_actions_retrieved_at": _instant(actions.retrieved_at),
    }
    evidence.update(actions_references)
    blackout = _blackout_event(actions, context.latest_completed_session)
    if blackout is not None:
        ledger.append(
            _entry(
                "SUPPORTED_CORPORATE_ACTION_BLACKOUT",
                "FAIL",
                "SUPPORTED_CORPORATE_ACTION_IN_BLACKOUT_WINDOW",
                "A provider-supported corporate action has an effective date within the fixed seven-calendar-day blackout window around the retained session.",
                actions_references,
                {
                    "blackout_window_days": _ACTION_BLACKOUT_DAYS,
                    "retained_completed_session": context.latest_completed_session.isoformat(),
                    "blackout_event": blackout,
                },
            )
        )
        return _ineligible(
            symbol=context.symbol,
            observation_identity_sha256=observation_identity_sha256,
            runtime=runtime,
            ledger=ledger,
            verified_evidence=evidence,
            remaining=(),
            stopping_rule_id="SUPPORTED_CORPORATE_ACTION_BLACKOUT",
        )
    ledger.append(
        _entry(
            "SUPPORTED_CORPORATE_ACTION_BLACKOUT",
            "PASS",
            "NO_SUPPORTED_CORPORATE_ACTION_IN_BLACKOUT_WINDOW",
            "No provider-supported dividend, bonus, split or rights event was observed within the fixed blackout window around the retained session.",
            actions_references,
            {
                "blackout_window_days": _ACTION_BLACKOUT_DAYS,
                "retained_completed_session": context.latest_completed_session.isoformat(),
            },
        )
    )
    return _finalize(
        status="ELIGIBLE",
        symbol=context.symbol,
        observation_identity_sha256=observation_identity_sha256,
        runtime=runtime,
        ledger=ledger,
        verified_evidence=evidence,
    )


def evaluate_stock_eligibility_from_record_v3(
    storage_root: Path, observation: str
) -> dict[str, object]:
    """Read one retained record and run the bounded automatic V3 safety screen."""
    root, handle = _valid_request(storage_root, observation)
    return _evaluate_stock_eligibility_from_admitted_record_v3(
        read_stock_observation_v1(root, handle),
        handle,
        providers=_LiveProviders(clock=_utc_now),
        clock=_utc_now,
    )


__all__ = [
    "SAFETY_POLICY_IDENTIFIER",
    "SCHEMA",
    "evaluate_stock_eligibility_from_record_v3",
]
