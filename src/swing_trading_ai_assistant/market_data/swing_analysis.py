"""Candidate-level swing analysis over retained scan results.

This module deliberately does NOT change the scan decision policy or schema. It
adds the missing price-action/SMC facts as an analysis artifact:

- ATR20 volatility context
- event-session volume versus the prior 20-session average
- completed-bar retest state
- multi-swing support/resistance clusters over up to 252 sessions
- weekly trend context
- a real demand/order-block zone (last bearish candle before the impulse)

Every member carries the provider history identity and an analysis identity.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Final, cast

from .bharatstock import (
    BharatStockClient,
    BharatStockDailyPrice,
    BharatStockError,
    BharatStockInstrument,
)
from .scan_decision_evidence import admit_retained_scan_document_v1

SCHEMA: Final = "swing-analysis@v2"
POLICY_SCHEMA: Final = "swing-analysis-policy@v1"
_MAX_SESSIONS: Final = 252
_LOOKBACK_DAYS: Final = 420
_PIVOT_RADIUS: Final = 2
_WEEKLY_PIVOT_RADIUS: Final = 1
_ATR_PERIOD: Final = 20
_MIN_HISTORY: Final = 60
_VOLUME_MIN_RATIO: Final = Decimal("1.5")
_EXTENSION_MAX_ATR: Final = Decimal("2")
_CANDLE_BODY_MIN_PERCENT: Final = Decimal("60")


@dataclass(frozen=True, slots=True)
class AnalysisBar:
    session: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


def _bars(rows: Sequence[BharatStockDailyPrice]) -> tuple[AnalysisBar, ...]:
    return tuple(
        AnalysisBar(row.session, row.open, row.high, row.low, row.close, row.volume)
        for row in rows
    )


def _atr(rows: Sequence[AnalysisBar], period: int = _ATR_PERIOD) -> Decimal | None:
    if len(rows) < period + 1:
        return None
    values: list[Decimal] = []
    for index in range(len(rows) - period, len(rows)):
        previous = rows[index - 1].close
        current = rows[index]
        values.append(
            max(
                current.high - current.low,
                abs(current.high - previous),
                abs(current.low - previous),
            )
        )
    return sum(values, Decimal(0)) / Decimal(period)


def _pivots(
    rows: Sequence[AnalysisBar], radius: int
) -> tuple[tuple[int, str, Decimal], ...]:
    found: list[tuple[int, str, Decimal]] = []
    for index in range(radius, len(rows) - radius):
        high = rows[index].high
        low = rows[index].low
        if (
            all(high > rows[index + offset].high for offset in (-2, -1, 1, 2))
            and radius == 2
        ):
            found.append((index, "SWING_HIGH", high))
        elif radius == 2 and all(
            low < rows[index + offset].low for offset in (-2, -1, 1, 2)
        ):
            found.append((index, "SWING_LOW", low))
        elif radius == 1:
            if high > rows[index - 1].high and high > rows[index + 1].high:
                found.append((index, "SWING_HIGH", high))
            elif low < rows[index - 1].low and low < rows[index + 1].low:
                found.append((index, "SWING_LOW", low))
    return tuple(found)


def _clusters(
    pivots: Sequence[tuple[int, str, Decimal]],
    rows: Sequence[AnalysisBar],
    tolerance: Decimal,
) -> list[dict[str, object]]:
    clusters: list[dict[str, object]] = []
    for target_kind in ("SWING_HIGH", "SWING_LOW"):
        selected = sorted(
            [pivot for pivot in pivots if pivot[1] == target_kind],
            key=lambda item: item[2],
        )
        for index, kind, price in selected:
            if (
                clusters
                and clusters[-1]["kind"] == kind
                and abs(price - cast(Decimal, clusters[-1]["price"])) <= tolerance
            ):
                cluster = clusters[-1]
                cluster["touches"] = cast(int, cluster["touches"]) + 1
                cluster["last_session"] = max(
                    cast(str, cluster["last_session"]),
                    rows[index].session.isoformat(),
                )
                values = cast(list[Decimal], cluster.pop("_values"))
                values.append(price)
                cluster["price"] = sum(values, Decimal(0)) / Decimal(len(values))
                cluster["_values"] = values
            else:
                clusters.append(
                    {
                        "kind": kind,
                        "price": price,
                        "touches": 1,
                        "last_session": rows[index].session.isoformat(),
                        "_values": [price],
                    }
                )
    for cluster in clusters:
        cluster.pop("_values", None)
        cluster["price"] = str(
            cast(Decimal, cluster["price"]).quantize(Decimal("0.01"))
        )
    return clusters


def _weekly(rows: Sequence[AnalysisBar]) -> dict[str, object]:
    weeks: dict[tuple[int, int], list[AnalysisBar]] = {}
    for row in rows:
        key = row.session.isocalendar()[:2]
        weeks.setdefault((key[0], key[1]), []).append(row)
    weekly = tuple(
        AnalysisBar(
            min(item.session for item in values),
            values[0].open,
            max(item.high for item in values),
            min(item.low for item in values),
            values[-1].close,
            sum(item.volume for item in values),
        )
        for _, values in sorted(weeks.items())
    )
    if len(weekly) < 4:
        return {"trend": "INSUFFICIENT", "weeks": len(weekly)}
    pivots = _pivots(weekly, _WEEKLY_PIVOT_RADIUS)
    highs = [price for _, kind, price in pivots if kind == "SWING_HIGH"]
    lows = [price for _, kind, price in pivots if kind == "SWING_LOW"]
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
            trend = "UPTREND"
        elif highs[-1] < highs[-2] and lows[-1] < lows[-2]:
            trend = "DOWNTREND"
        else:
            trend = "RANGE_OR_TRANSITION"
    else:
        recent = weekly[-4:]
        if all(
            recent[index].high > recent[index - 1].high
            and recent[index].low > recent[index - 1].low
            for index in range(1, len(recent))
        ):
            trend = "UPTREND"
        elif all(
            recent[index].high < recent[index - 1].high
            and recent[index].low < recent[index - 1].low
            for index in range(1, len(recent))
        ):
            trend = "DOWNTREND"
        else:
            trend = "RANGE_OR_TRANSITION"
    average = sum((item.close for item in weekly[-20:]), Decimal(0)) / Decimal(
        min(20, len(weekly))
    )
    return {
        "trend": trend,
        "weeks": len(weekly),
        "sessions": len(rows),
        "last_week_close": str(weekly[-1].close),
        "twenty_week_average": str(average),
        "above_twenty_week_average": weekly[-1].close > average,
    }


def _volume(rows: Sequence[AnalysisBar], event_index: int) -> dict[str, object]:
    prior = rows[max(0, event_index - 20) : event_index]
    if not prior:
        return {"ratio": None, "prior_sessions": 0}
    average = Decimal(sum(row.volume for row in prior)) / Decimal(len(prior))
    ordered = sorted(row.volume for row in prior)
    middle = len(ordered) // 2
    median = (
        Decimal(ordered[middle])
        if len(ordered) % 2
        else Decimal(ordered[middle - 1] + ordered[middle]) / Decimal(2)
    )
    event = rows[event_index]
    return {
        "event_volume": event.volume,
        "prior_sessions": len(prior),
        "prior_average": str(average.quantize(Decimal("0.01"))),
        "prior_median": str(median.quantize(Decimal("0.01"))),
        "ratio": str((Decimal(event.volume) / average).quantize(Decimal("0.01")))
        if average
        else None,
    }


def _retest(
    rows: Sequence[AnalysisBar],
    event_index: int,
    broken_high: Decimal,
) -> dict[str, object]:
    after = rows[event_index + 1 :]
    if not after:
        return {"state": "NO_SESSIONS_AFTER_EVENT", "sessions_after_event": 0}
    if after[-1].close < broken_high:
        state = "BELOW_LEVEL"
    elif any(row.low <= broken_high and row.close > broken_high for row in after):
        state = "RETEST_CONFIRMED"
    elif any(row.low <= broken_high for row in after):
        state = "TESTING"
    else:
        state = "NO_RETEST"
    return {
        "state": state,
        "sessions_after_event": len(after),
        "low_since_event": str(min(row.low for row in after)),
        "last_close": str(after[-1].close),
    }


def _demand_zone(rows: Sequence[AnalysisBar], event_index: int) -> dict[str, object]:
    origin: AnalysisBar | None = None
    for index in range(event_index - 1, max(-1, event_index - 6), -1):
        if rows[index].close < rows[index].open:
            origin = rows[index]
            break
    if origin is None:
        base = rows[max(0, event_index - 5) : event_index]
        if not base:
            return {"kind": "UNAVAILABLE"}
        low = min(row.low for row in base)
        high = max(row.high for row in base)
        after = rows[event_index + 1 :]
        return {
            "kind": "BASE_RANGE",
            "low": str(low),
            "high": str(high),
            "origin_session": None,
            "tested_after_event": any(row.low <= high for row in after),
        }
    after = rows[event_index + 1 :]
    tested = any(row.low <= origin.high for row in after)
    return {
        "kind": "LAST_BEARISH_CANDLE",
        "low": str(origin.low),
        "high": str(origin.high),
        "origin_session": origin.session.isoformat(),
        "tested_after_event": tested,
    }


def _policy_stop(policy: dict[str, object]) -> object | None:
    ledger = policy.get("explanation_ledger")
    if type(ledger) is not list:
        return None
    for entry in cast(list[object], ledger):
        if type(entry) is not dict:
            continue
        row = cast(dict[str, object], entry)
        if (
            row.get("rule_id") != "CAUSAL_SUPPORTING_LOW_STOP_REFERENCE"
            or row.get("outcome") != "PASS"
        ):
            continue
        measurements = row.get("derived_measurements")
        if type(measurements) is dict:
            return cast(dict[str, object], measurements).get(
                "structural_stop_reference_inr"
            )
    return None


def _gate(
    gate_id: str,
    status: str,
    observed: object,
    requirement: str,
) -> dict[str, object]:
    return {
        "id": gate_id,
        "status": status,
        "observed": observed,
        "requirement": requirement,
    }


def _atr_gate(atr: Decimal | None) -> dict[str, object]:
    return _gate(
        "ATR_AVAILABLE",
        "PASS" if atr is not None else "UNAVAILABLE",
        str(atr.quantize(Decimal("0.01"))) if atr is not None else None,
        "atr20 present",
    )


def _volume_gate(volume: dict[str, object]) -> dict[str, object]:
    ratio = volume.get("ratio")
    if ratio is None:
        status = "UNAVAILABLE"
    elif Decimal(str(ratio)) >= _VOLUME_MIN_RATIO:
        status = "PASS"
    else:
        status = "FAIL"
    return _gate("VOLUME_EXPANSION", status, ratio, ">=1.50x prior 20-session average")


def _retest_gate(retest: dict[str, object]) -> dict[str, object]:
    state = str(retest.get("state"))
    if state == "RETEST_CONFIRMED":
        status = "PASS"
    elif state == "BELOW_LEVEL":
        status = "FAIL"
    elif state in {"TESTING", "NO_RETEST", "NO_SESSIONS_AFTER_EVENT"}:
        status = "PENDING"
    else:
        status = "UNAVAILABLE"
    return _gate("RETEST_CONFIRMED", status, state, "state == RETEST_CONFIRMED")


def _weekly_gate(weekly: dict[str, object]) -> dict[str, object]:
    trend = str(weekly.get("trend"))
    if trend == "UPTREND":
        status = "PASS"
    elif trend == "DOWNTREND":
        status = "FAIL"
    elif trend == "RANGE_OR_TRANSITION":
        status = "PENDING"
    else:
        status = "UNAVAILABLE"
    return _gate("WEEKLY_TREND_UP", status, trend, "weekly trend == UPTREND")


def _demand_gate(demand: dict[str, object], close: Decimal) -> dict[str, object]:
    kind = str(demand.get("kind"))
    zone_low = demand.get("low")
    if kind == "UNAVAILABLE" or zone_low is None:
        status = "UNAVAILABLE"
    elif close >= Decimal(str(zone_low)):
        status = "PASS"
    else:
        status = "FAIL"
    return _gate(
        "DEMAND_ZONE_VALID",
        status,
        {"kind": kind, "zone_low": zone_low, "latest_close": str(close)},
        "zone available and latest close >= zone low",
    )


def _extension_gate(extension_atr: Decimal | None) -> dict[str, object]:
    if extension_atr is None:
        status = "UNAVAILABLE"
    elif extension_atr <= _EXTENSION_MAX_ATR:
        status = "PASS"
    else:
        status = "FAIL"
    return _gate(
        "EXTENSION_WITHIN_2_ATR",
        status,
        str(extension_atr.quantize(Decimal("0.01")))
        if extension_atr is not None
        else None,
        "<=2.00 ATR above broken high",
    )


def _candle_gate(candle: AnalysisBar) -> dict[str, object]:
    span = candle.high - candle.low
    body = abs(candle.close - candle.open)
    body_percent = (body / span * 100) if span > 0 else None
    if body_percent is None:
        status = "UNAVAILABLE"
    elif candle.close > candle.open and body_percent >= _CANDLE_BODY_MIN_PERCENT:
        status = "PASS"
    else:
        status = "FAIL"
    return _gate(
        "CANDLE_BODY_QUALITY",
        status,
        {
            "direction": "BULLISH" if candle.close > candle.open else "BEARISH",
            "body_percent": str(body_percent.quantize(Decimal("0.01")))
            if body_percent is not None
            else None,
        },
        "bullish body >=60% of event range",
    )


def _risk_gate(risk_atr: Decimal | None) -> dict[str, object]:
    if risk_atr is None:
        status = "UNAVAILABLE"
    elif risk_atr > 0:
        status = "PASS"
    else:
        status = "FAIL"
    return _gate(
        "RISK_POSITIVE",
        status,
        str(risk_atr.quantize(Decimal("0.01"))) if risk_atr is not None else None,
        "latest close above structural stop",
    )


def _research_policy(
    atr: Decimal | None,
    volume: dict[str, object],
    retest: dict[str, object],
    weekly: dict[str, object],
    demand: dict[str, object],
    close: Decimal,
    extension_atr: Decimal | None,
    risk_atr: Decimal | None,
    candle: AnalysisBar,
) -> dict[str, object]:
    gates: list[dict[str, object]] = [
        _atr_gate(atr),
        _volume_gate(volume),
        _candle_gate(candle),
        _retest_gate(retest),
        _weekly_gate(weekly),
        _demand_gate(demand, close),
        _extension_gate(extension_atr),
        _risk_gate(risk_atr),
    ]
    failed = [str(gate["id"]) for gate in gates if gate["status"] == "FAIL"]
    pending = [str(gate["id"]) for gate in gates if gate["status"] == "PENDING"]
    unavailable = [str(gate["id"]) for gate in gates if gate["status"] == "UNAVAILABLE"]
    if failed:
        outcome = "NOT_QUALIFIED"
    elif unavailable:
        outcome = "INSUFFICIENT"
    elif pending:
        outcome = "WATCH"
    else:
        outcome = "QUALIFIED"
    return {
        "schema": POLICY_SCHEMA,
        "mode": "PROVISIONAL_RESEARCH",
        "outcome": outcome,
        "failed_gates": failed,
        "pending_gates": pending,
        "unavailable_gates": unavailable,
        "gates": gates,
    }


def _policy_summary(members: Sequence[dict[str, object]]) -> dict[str, object]:
    outcomes = {
        "QUALIFIED": 0,
        "WATCH": 0,
        "NOT_QUALIFIED": 0,
        "INSUFFICIENT": 0,
    }
    gate_counts: dict[str, dict[str, int]] = {}
    for member in members:
        policy = member.get("policy")
        if type(policy) is not dict:
            continue
        outcome = cast(dict[str, object], policy).get("outcome")
        if type(outcome) is str and outcome in outcomes:
            outcomes[outcome] += 1
        gates = cast(dict[str, object], policy).get("gates")
        if type(gates) is not list:
            continue
        for gate in cast(list[object], gates):
            if type(gate) is not dict:
                continue
            gate_row = cast(dict[str, object], gate)
            gate_id = gate_row.get("id")
            status = gate_row.get("status")
            if type(gate_id) is not str or type(status) is not str:
                continue
            bucket = gate_counts.setdefault(gate_id, {})
            bucket[status] = bucket.get(status, 0) + 1
    return {
        "schema": POLICY_SCHEMA,
        "mode": "PROVISIONAL_RESEARCH",
        "outcome_counts": outcomes,
        "gate_counts": gate_counts,
    }


def _identity(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _finite_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
        if not parsed.is_finite():
            return None
        parsed.quantize(Decimal("0.01"))
    except (ValueError, ArithmeticError):
        return None
    return parsed


def _unavailable_member(
    symbol: str,
    isin: str,
    exchange: str,
    *,
    flag: str,
    gate_id: str,
    observed: object,
    requirement: str,
    sessions: int = 0,
) -> dict[str, object]:
    member: dict[str, object] = {
        "symbol": symbol,
        "isin": isin,
        "exchange": exchange,
        "latest_session": None,
        "history": {"sessions": sessions},
        "flags": [flag],
        "policy": {
            "schema": POLICY_SCHEMA,
            "mode": "PROVISIONAL_RESEARCH",
            "outcome": "INSUFFICIENT",
            "failed_gates": [],
            "pending_gates": [],
            "unavailable_gates": [gate_id],
            "gates": [_gate(gate_id, "UNAVAILABLE", observed, requirement)],
        },
    }
    member["analysis_identity_sha256"] = _identity(member)
    return member


class _CandidateInputError(Exception):
    def __init__(
        self,
        flag: str,
        gate_id: str,
        observed: object,
        requirement: str,
    ) -> None:
        super().__init__(requirement)
        self.flag = flag
        self.gate_id = gate_id
        self.observed = observed
        self.requirement = requirement


def _candidate_inputs(
    candidate: dict[str, object],
) -> tuple[date, Decimal, Decimal | None, Decimal | None, str]:
    summary_value = candidate.get("candidate_summary")
    if type(summary_value) is not dict:
        raise _CandidateInputError(
            "INVALID_SCAN_INPUT",
            "CANDIDATE_INPUT_VALID",
            "candidate_summary missing",
            "candidate_summary object",
        )
    summary = cast(dict[str, object], summary_value)
    event_text = summary.get("event_session")
    if type(event_text) is not str:
        raise _CandidateInputError(
            "INVALID_SCAN_INPUT",
            "CANDIDATE_INPUT_VALID",
            "event_session missing",
            "ISO event session",
        )
    try:
        event_session = date.fromisoformat(event_text)
    except ValueError as error:
        raise _CandidateInputError(
            "INVALID_SCAN_INPUT",
            "CANDIDATE_INPUT_VALID",
            event_text,
            "ISO event session",
        ) from error
    broken_high = _finite_decimal(summary.get("broken_high_level_inr"))
    if broken_high is None or broken_high <= 0:
        raise _CandidateInputError(
            "INVALID_SCAN_INPUT",
            "CANDIDATE_INPUT_VALID",
            summary.get("broken_high_level_inr"),
            "finite positive broken high",
        )
    display_stop = _finite_decimal(summary.get("supporting_stop_reference_inr"))
    policy_value = candidate.get("policy_decision")
    policy = cast(dict[str, object], policy_value) if type(policy_value) is dict else {}
    stop = _finite_decimal(_policy_stop(policy))
    stop_source = "POLICY_STRUCTURAL" if stop is not None else "DISPLAY_PROJECTION"
    if stop is None:
        stop = display_stop
    return event_session, broken_high, display_stop, stop, stop_source


def _analyze_member(
    symbol: str,
    isin: str,
    exchange: str,
    rows: Sequence[BharatStockDailyPrice],
    candidate: dict[str, object],
) -> dict[str, object]:
    bars = _bars(rows)[-_MAX_SESSIONS:]
    try:
        event_session, broken_high, display_stop, stop, stop_source = _candidate_inputs(
            candidate
        )
    except _CandidateInputError as error:
        return _unavailable_member(
            symbol,
            isin,
            exchange,
            flag=error.flag,
            gate_id=error.gate_id,
            observed=error.observed,
            requirement=error.requirement,
            sessions=len(bars),
        )
    if len(bars) < _MIN_HISTORY:
        return _unavailable_member(
            symbol,
            isin,
            exchange,
            flag="INSUFFICIENT_HISTORY",
            gate_id="MINIMUM_HISTORY",
            observed=len(bars),
            requirement=">=60 sessions",
            sessions=len(bars),
        )
    event_index = next(
        (index for index, row in enumerate(bars) if row.session == event_session),
        None,
    )
    if event_index is None:
        return _unavailable_member(
            symbol,
            isin,
            exchange,
            flag="EVENT_SESSION_OUTSIDE_WINDOW",
            gate_id="EVENT_SESSION_IN_WINDOW",
            observed={
                "event_session": event_session.isoformat(),
                "first_session": bars[0].session.isoformat(),
                "last_session": bars[-1].session.isoformat(),
            },
            requirement="event session in retained window",
            sessions=len(bars),
        )
    atr = _atr(bars)
    current = bars[-1]
    volume = _volume(bars, event_index)
    retest = _retest(bars, event_index, broken_high)
    pivots = _pivots(bars, _PIVOT_RADIUS)
    tolerance = (atr or Decimal("0")) * Decimal("0.5")
    clusters = _clusters(pivots, bars, tolerance)
    resistance = [
        cluster
        for cluster in clusters
        if cluster["kind"] == "SWING_HIGH"
        and Decimal(str(cluster["price"])) > current.close
    ][:5]
    support = list(
        reversed(
            [
                cluster
                for cluster in clusters
                if cluster["kind"] == "SWING_LOW"
                and Decimal(str(cluster["price"])) < current.close
            ][-5:]
        )
    )
    weekly = _weekly(bars)
    demand = _demand_zone(bars, event_index)
    extension = current.close - broken_high
    extension_atr = extension / atr if atr else None
    risk_per_share = current.close - Decimal(str(stop)) if stop is not None else None
    risk_atr = risk_per_share / atr if risk_per_share is not None and atr else None
    atr_percent = atr / current.close * 100 if atr and current.close else None
    nearest_resistance = resistance[0] if resistance else None
    nearest_support = support[0] if support else None
    resistance_distance_atr = (
        (Decimal(str(nearest_resistance["price"])) - current.close) / atr
        if nearest_resistance is not None and atr
        else None
    )
    support_distance_atr = (
        (current.close - Decimal(str(nearest_support["price"]))) / atr
        if nearest_support is not None and atr
        else None
    )
    flags: list[str] = []
    ratio = volume.get("ratio")
    if ratio is not None and Decimal(str(ratio)) < 1:
        flags.append("VOLUME_RATIO_BELOW_1")
    if retest.get("state") != "RETEST_CONFIRMED":
        flags.append("RETEST_NOT_CONFIRMED")
    if weekly.get("trend") != "UPTREND":
        flags.append("WEEKLY_TREND_NOT_UP")
    if demand.get("tested_after_event") is True:
        flags.append("DEMAND_ZONE_TESTED")
    if extension_atr is not None and extension_atr > _EXTENSION_MAX_ATR:
        flags.append("EXTENSION_ABOVE_2_ATR")
    member: dict[str, object] = {
        "symbol": symbol,
        "isin": isin,
        "exchange": exchange,
        "event_session": event_session.isoformat(),
        "latest_session": current.session.isoformat(),
        "history": {
            "sessions": len(bars),
            "first_session": bars[0].session.isoformat(),
            "last_session": bars[-1].session.isoformat(),
        },
        "atr20": str(atr.quantize(Decimal("0.01"))) if atr else None,
        "atr_percent": str(atr_percent.quantize(Decimal("0.01")))
        if atr_percent is not None
        else None,
        "volume": volume,
        "retest": retest,
        "levels": {
            "broken_high": str(broken_high),
            "structural_stop": str(stop) if stop is not None else None,
            "structural_stop_source": stop_source,
            "display_stop": str(display_stop) if display_stop is not None else None,
            "extension_atr": str(extension_atr.quantize(Decimal("0.01")))
            if extension_atr is not None
            else None,
            "risk_per_share": str(risk_per_share.quantize(Decimal("0.01")))
            if risk_per_share is not None
            else None,
            "risk_atr": str(risk_atr.quantize(Decimal("0.01")))
            if risk_atr is not None
            else None,
            "resistance": resistance,
            "support": support,
            "nearest_resistance": nearest_resistance,
            "nearest_support": nearest_support,
            "resistance_distance_atr": str(
                resistance_distance_atr.quantize(Decimal("0.01"))
            )
            if resistance_distance_atr is not None
            else None,
            "support_distance_atr": str(support_distance_atr.quantize(Decimal("0.01")))
            if support_distance_atr is not None
            else None,
        },
        "weekly": weekly,
        "demand_zone": demand,
        "flags": flags,
    }
    member["policy"] = _research_policy(
        atr,
        volume,
        retest,
        weekly,
        demand,
        current.close,
        extension_atr,
        risk_atr,
        bars[event_index],
    )
    member["analysis_identity_sha256"] = _identity(member)
    return member


def _read_scan_bytes(path: Path) -> bytes:
    descriptor = os.open(
        path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    )
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4 * 1024 * 1024:
            raise ValueError("invalid scan document")
        data = os.read(descriptor, 4 * 1024 * 1024 + 1)
        if len(data) != info.st_size:
            raise ValueError("invalid scan document")
        return data
    finally:
        os.close(descriptor)


def analyze_scan(scan_path: Path) -> dict[str, object]:
    """Read one retained scan page and analyze every candidate."""
    raw = _read_scan_bytes(scan_path)
    scan = admit_retained_scan_document_v1(raw)
    candidates = cast(list[dict[str, object]], scan.get("candidates") or [])
    client = BharatStockClient()
    end = datetime.now().date()
    start = end - timedelta(days=_LOOKBACK_DAYS)
    members: list[dict[str, object]] = []
    for candidate in candidates:
        symbol_value = candidate.get("symbol")
        isin_value = candidate.get("isin")
        exchange_value = candidate.get("exchange")
        symbol = symbol_value if type(symbol_value) is str else ""
        isin = isin_value if type(isin_value) is str else ""
        exchange = exchange_value if type(exchange_value) is str else ""
        if not symbol or not isin or not exchange:
            members.append(
                _unavailable_member(
                    symbol,
                    isin,
                    exchange,
                    flag="INVALID_SCAN_INPUT",
                    gate_id="CANDIDATE_INPUT_VALID",
                    observed={
                        "symbol": symbol,
                        "isin": isin,
                        "exchange": exchange,
                    },
                    requirement="non-empty symbol, isin and exchange",
                )
            )
            continue
        try:
            instrument = BharatStockInstrument(isin, exchange, symbol)
            history = client.history(instrument, start, end)
        except (BharatStockError, ValueError, OSError) as error:
            members.append(
                _unavailable_member(
                    symbol,
                    isin,
                    exchange,
                    flag="PROVIDER_HISTORY_UNAVAILABLE",
                    gate_id="PROVIDER_HISTORY_AVAILABLE",
                    observed=type(error).__name__,
                    requirement="provider history available",
                )
            )
            continue
        rows = sorted(history.rows, key=lambda row: row.session)
        try:
            member = _analyze_member(symbol, isin, exchange, tuple(rows), candidate)
        except (ArithmeticError, ValueError) as error:
            members.append(
                _unavailable_member(
                    symbol,
                    isin,
                    exchange,
                    flag="ANALYSIS_INPUT_UNAVAILABLE",
                    gate_id="ANALYSIS_COMPLETE",
                    observed=type(error).__name__,
                    requirement="analysis completed",
                    sessions=len(rows),
                )
            )
            continue
        member.pop("analysis_identity_sha256", None)
        member["provider_history"] = {
            "retrieved_at": history.retrieved_at.isoformat(),
            "response_sha256s": list(history.response_sha256s),
            "request_count": history.request_count,
        }
        member["analysis_identity_sha256"] = _identity(member)
        members.append(member)
    report: dict[str, object] = {
        "schema": SCHEMA,
        "scan_result_identity_sha256": scan.get("result_identity_sha256"),
        "scan_timestamp": scan.get("scan_timestamp"),
        "latest_session": max(
            (
                cast(str, member["latest_session"])
                for member in members
                if member.get("latest_session") is not None
            ),
            default=None,
        ),
        "scan_runtime_code_identity_sha256": scan.get("runtime_code_identity_sha256"),
        "policy": _policy_summary(members),
        "members": members,
    }
    report["report_identity_sha256"] = _identity(report)
    return report


__all__ = ["SCHEMA", "analyze_scan"]
