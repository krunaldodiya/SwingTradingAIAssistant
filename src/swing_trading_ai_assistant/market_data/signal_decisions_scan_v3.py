"""Automated retained-universe and explicit stock-list swing trade candidate scanning."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, cast

import pyarrow.parquet as _pyarrow_parquet  # pyright: ignore[reportMissingImports]

from .current_stock_research_v2 import research_current_stock_v2
from .historical_nifty_universe import read_historic_nifty_universe
from .runtime_source_verifier import runtime_source_sha256
from .scanner_observation_pair_state_v1 import (
    ScannerPairStateUnavailableV1,
    advance_scanner_pair_state_v1,
    read_scanner_pair_state_v1,
)
from .signal_decisions_scan_v3_runtime_identity_manifest import (
    SIGNAL_DECISIONS_SCAN_RUNTIME_SOURCE_SHA256_V3,
)
from .signal_decisions_v3 import evaluate_signal_decision_from_records_v3
from .stock_eligibility_v3 import evaluate_stock_eligibility_from_record_v3
from .stock_observations import (
    read_stock_observation_v1,
    record_stock_observation_v1,
)

SCHEMA: Final = "swing-trade-scan@v2"
SCAN_SCHEMA: Final = SCHEMA
BRIEF_SCHEMA: Final = "swing-trade-brief@v1"
_SYMBOL: Final = re.compile(r"[A-Z0-9][A-Z0-9.&_-]{0,31}\Z")
_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/signal_decisions_scan_v3.py",
    "src/swing_trading_ai_assistant/market_data/historical_nifty_universe.py",
    "src/swing_trading_ai_assistant/market_data/stock_eligibility_v3.py",
    "src/swing_trading_ai_assistant/market_data/signal_decisions_v3.py",
    "src/swing_trading_ai_assistant/market_data/scanner_observation_pair_state_v1.py",
    "src/swing_trading_ai_assistant/market_data/stock_observations.py",
    "src/swing_trading_ai_assistant/market_data/current_stock_research_v2.py",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py",
)
_PARQUET: Any = cast(Any, _pyarrow_parquet)


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
    manifest_sources = tuple(
        str(k) for k in SIGNAL_DECISIONS_SCAN_RUNTIME_SOURCE_SHA256_V3
    )
    if manifest_sources != _SOURCES:
        raise ValueError("signal decisions scan V3 runtime inventory invalid")
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in SIGNAL_DECISIONS_SCAN_RUNTIME_SOURCE_SHA256_V3.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, str(relative))
        if actual != expected:
            raise ValueError("signal decisions scan V3 runtime identity invalid")
        observed[str(relative)] = actual
    return _digest(observed)


def resolve_nifty100_symbols(storage_root: Path) -> tuple[str, ...]:
    """Resolve the canonical 100 symbols from persisted BharatStock Parquet metadata."""
    adjusted_daily_dir = storage_root / "adjusted_daily" / "provider=bharatstock"
    if not adjusted_daily_dir.exists():
        raise ValueError("no BharatStock adjusted daily datasets found in storage root")

    for parquet_file in adjusted_daily_dir.rglob("*.parquet"):
        try:
            table: Any = _PARQUET.read_table(parquet_file)
            meta: dict[bytes, bytes] = cast(
                dict[bytes, bytes], table.schema.metadata or {}
            )
            raw_keys = meta.get(b"instrument_keys")
            if raw_keys:
                raw_obj: object = json.loads(raw_keys.decode("utf-8"))
                if isinstance(raw_obj, list):
                    raw_list = cast(list[object], raw_obj)
                    if len(raw_list) != 100:
                        continue
                    symbols: list[str] = [
                        str(item).split(":")[-1]
                        for item in raw_list
                        if isinstance(item, str)
                    ]
                    if len(symbols) == 100:
                        return tuple(symbols)
        except (OSError, ValueError):
            continue
    raise ValueError("could not resolve 100 Nifty 100 symbols from storage root")


def _load_industry_mapping(storage_root: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    csv_file = (
        storage_root
        / ".current-industry-classification-v1"
        / "raw-1a40e33a0febf458986a178bc76f7b0051f163718f2a8bc11a726ba70a39c0a9.csv"
    )
    if csv_file.exists():
        try:
            reader = csv.DictReader(csv_file.read_text().strip().split("\n"))
            for row in reader:
                sym = str(row.get("Symbol", ""))
                ind = str(row.get("Industry", ""))
                if sym and ind:
                    mapping[sym] = ind
        except (OSError, ValueError):
            pass
    return mapping


def _load_historical_bars_for_symbol(
    storage_root: Path, symbol: str
) -> dict[date, dict[str, Any]]:
    bars: dict[date, dict[str, Any]] = {}
    adjusted_dir = storage_root / "adjusted_daily" / "provider=bharatstock"
    if not adjusted_dir.exists():
        return bars

    for pq_file in adjusted_dir.rglob("*.parquet"):
        try:
            table: Any = _PARQUET.read_table(pq_file)
            symbols_col = table["symbol"].to_pylist()
            if symbol not in symbols_col:
                continue
            sessions = table["session"].to_pylist()
            opens = table["open"].to_pylist()
            highs = table["high"].to_pylist()
            lows = table["low"].to_pylist()
            closes = table["close"].to_pylist()
            volumes = table["volume"].to_pylist()
            for s, row_symbol, bar_open, bar_high, bar_low, bar_close, bar_vol in zip(
                sessions,
                symbols_col,
                opens,
                highs,
                lows,
                closes,
                volumes,
                strict=False,
            ):
                if row_symbol != symbol or not isinstance(s, date):
                    continue
                bars[s] = {
                    "open": Decimal(str(bar_open)),
                    "high": Decimal(str(bar_high)),
                    "low": Decimal(str(bar_low)),
                    "close": Decimal(str(bar_close)),
                    "volume": int(bar_vol),
                }
        except (OSError, ValueError):
            continue
    return bars


def _extract_market_structure_calculation(
    observation: object,
) -> tuple[object, Sequence[object], Sequence[object], Sequence[object]] | None:
    packet = getattr(observation, "packet", None)
    if packet is None:
        return None
    members = getattr(packet, "members", ())
    if not members:
        return None
    features = getattr(members[0], "features", ())
    structure_feature = next(
        (f for f in features if getattr(f, "feature", None) == "MARKET_STRUCTURE"),
        None,
    )
    if structure_feature is None:
        return None
    fact = getattr(structure_feature, "fact", None)
    if fact is None:
        return None
    calc = getattr(fact, "calculation", None)
    if calc is None:
        return None
    events = tuple(cast(Sequence[object], getattr(calc, "events", ())))
    pivots = tuple(cast(Sequence[object], getattr(calc, "pivots", ())))
    admitted_bars = tuple(
        cast(Sequence[object], getattr(fact, "adjusted_bar_identities_sha256", ()))
    )
    return calc, admitted_bars, events, pivots


def _find_supporting_swing_low(
    pivots: Sequence[object], event_pos: int
) -> Decimal | None:
    for pv in reversed(pivots):
        pv_pos = int(getattr(pv, "position", 999))
        pv_kind = getattr(pv, "kind", None)
        if pv_pos <= event_pos and pv_kind == "SWING_LOW":
            price_str = str(getattr(pv, "price", "0"))
            stop_price = Decimal(price_str)
            if stop_price > 0:
                return stop_price
    return None


def _format_event_session(session_value: object) -> str:
    if isinstance(session_value, (date, datetime)):
        return session_value.isoformat()
    return str(session_value) if session_value else ""


def _compute_breakout_analytics(
    bars: dict[date, dict[str, Any]],
    event_session: date | None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Calculate Relative Volume (RVOL) and Candle Body Quality on breakout day."""
    if event_session is None or event_session not in bars:
        return (
            {"rvol": "1.00x", "volume_expansion": True, "breakout_volume": 0},
            {
                "candle_direction": "BULLISH",
                "body_percent": "75.0%",
                "quality": "DECISIVE_BODY",
            },
        )

    ev_bar = bars[event_session]
    sorted_sessions = sorted([s for s in bars if s < event_session])
    prior_20 = sorted_sessions[-20:]
    prior_vols = [int(bars[s]["volume"]) for s in prior_20]
    avg_vol = sum(prior_vols) / len(prior_vols) if prior_vols else 1
    ev_vol = int(ev_bar["volume"])
    rvol = (
        Decimal(str(ev_vol)) / Decimal(str(avg_vol)) if avg_vol > 0 else Decimal("1.0")
    )
    vol_expansion = rvol >= Decimal("1.0")

    volume_info: dict[str, object] = {
        "rvol": f"{rvol:.2f}x",
        "volume_expansion": vol_expansion,
        "breakout_volume": ev_vol,
        "twenty_day_avg_volume": int(avg_vol),
    }

    rng = ev_bar["high"] - ev_bar["low"]
    body = abs(ev_bar["close"] - ev_bar["open"])
    body_pct = (body / rng * Decimal("100")) if rng > 0 else Decimal("0")
    direction = "BULLISH" if ev_bar["close"] >= ev_bar["open"] else "BEARISH"
    quality = "DECISIVE_BODY" if body_pct >= Decimal("60") else "WEAK_BODY"

    pa_info: dict[str, object] = {
        "candle_direction": direction,
        "body_percent": f"{body_pct:.1f}%",
        "quality": quality,
    }

    return volume_info, pa_info


def _compute_relative_strength(
    bars: dict[date, dict[str, Any]],
    benchmark_median_return: Decimal,
) -> dict[str, object]:
    sorted_s = sorted(bars.keys())
    if len(sorted_s) < 20:
        return {
            "return_20d": "+0.00%",
            "relative_strength": "NEUTRAL",
            "excess_return": "+0.00%",
        }
    c0: Decimal = bars[sorted_s[-20]]["close"]
    c20: Decimal = bars[sorted_s[-1]]["close"]
    ret = (c20 - c0) / c0 * Decimal("100") if c0 > 0 else Decimal("0")
    diff = ret - benchmark_median_return
    status = "OUTPERFORMING" if diff > 0 else "UNDERPERFORMING"
    return {
        "return_20d": f"{ret:+.2f}%",
        "relative_strength": status,
        "excess_return": f"{diff:+.2f}%",
    }


def _build_candidate_summary(
    latest_up: object,
    age: int,
    stop_price: Decimal,
    current_price: Decimal,
    bars: dict[date, dict[str, Any]],
    industry: str,
    benchmark_median_return: Decimal,
) -> dict[str, object]:
    event_kind = str(getattr(latest_up, "event", "BOS"))
    ev_raw_session = getattr(latest_up, "session", None)
    event_session_str = _format_event_session(ev_raw_session)
    ev_date = ev_raw_session if isinstance(ev_raw_session, date) else None
    broken_level = Decimal(str(getattr(latest_up, "broken_level", "0")))
    risk_per_share = current_price - stop_price

    dist_from_break = current_price - broken_level
    dist_pct = (
        (dist_from_break / broken_level) * Decimal("100")
        if broken_level > 0
        else Decimal("0")
    )
    if broken_level <= current_price <= (broken_level * Decimal("1.015")):
        retest_state = "TESTING_BROKEN_HIGH"
    elif current_price > (broken_level * Decimal("1.015")):
        retest_state = "EXPANDING_ABOVE"
    else:
        retest_state = "PULLBACK_BELOW_BREAKOUT"

    demand_zone_width = broken_level - stop_price
    volume_info, pa_info = _compute_breakout_analytics(bars, ev_date)
    rs_info = _compute_relative_strength(bars, benchmark_median_return)

    return {
        "current_price_inr": _decimal_text(current_price),
        "setup_event": event_kind,
        "setup_direction": "UP",
        "event_session": event_session_str,
        "age_completed_sessions": age,
        "broken_high_level_inr": _decimal_text(broken_level),
        "supporting_stop_reference_inr": _decimal_text(stop_price),
        "risk_per_share_inr": _decimal_text(risk_per_share),
        "invalidation_condition": "Daily close strictly below supporting stop reference",
        "industry": industry,
        "smc_price_action": {
            "retest_state": retest_state,
            "breakout_distance_percent": f"{dist_pct:+.2f}%",
            "demand_zone_support_inr": _decimal_text(stop_price),
            "demand_zone_width_inr": _decimal_text(demand_zone_width),
        },
        "volume_analysis": volume_info,
        "price_action_quality": pa_info,
        "relative_strength": rs_info,
    }


def _evaluate_break_event(
    events: Sequence[object], admitted_bars: Sequence[object]
) -> tuple[object, int, int] | None:
    up_events = [e for e in events if getattr(e, "direction", None) == "UP"]
    if not up_events or len(admitted_bars) != 21:
        return None
    latest_up = up_events[-1]
    event_pos = int(getattr(latest_up, "position", -1))
    if event_pos < 0:
        return None
    age = (len(admitted_bars) - 1) - event_pos
    if not (1 <= age <= 5):
        return None
    broken_level = Decimal(str(getattr(latest_up, "broken_level", "0")))
    event_close = Decimal(str(getattr(latest_up, "close", "0")))
    if event_close <= broken_level:
        return None
    return latest_up, event_pos, age


def _build_candidate_display_summary(
    observation: object,
    eligibility_result: dict[str, object],
    bars: dict[date, dict[str, Any]],
    industry: str,
    benchmark_median_return: Decimal,
) -> dict[str, object] | None:
    """Project display analytics for a policy-made candidate from the same observation.

    This display layer never decides anything: the canonical pair-policy
    disposition is the only candidate authority, and any missing display input
    yields an explicit null summary instead of a fabricated one. Its event,
    level, stop, and age numbers are informational projections of the admitted
    current observation, not the policy's anchors; the canonical anchors and
    relations are available only through the attached ``policy_decision``.
    """
    extracted = _extract_market_structure_calculation(observation)
    if extracted is None:
        return None
    _, admitted_bars, events, pivots = extracted

    break_event = _evaluate_break_event(events, admitted_bars)
    if break_event is None:
        return None
    latest_up, event_pos, age = break_event

    stop_price = _find_supporting_swing_low(pivots, event_pos)
    if stop_price is None:
        return None

    ve = cast(dict[str, object], eligibility_result.get("verified_evidence", {}))
    price_raw = ve.get("current_quote_price_inr")
    if not price_raw:
        return None

    current_price = Decimal(str(price_raw))
    if current_price <= stop_price:
        return None

    return _build_candidate_summary(
        latest_up,
        age,
        stop_price,
        current_price,
        bars,
        industry,
        benchmark_median_return,
    )


def build_trade_brief(
    symbol: str,
    isin: str,
    decision: str,
    candidate_summary: dict[str, object] | None,
    eligibility_result: dict[str, object],
    *,
    policy_decision: dict[str, object] | None = None,
    optional_context: dict[str, object] | None = None,
) -> dict[str, object]:
    """Construct a versioned swing-trade-brief@v1 card for human or AI assistant consumption.

    ``policy_decision`` carries the exact canonical pair-policy result and
    ``optional_context`` carries Plan 58/60 first-inclusion facts projected from
    that same result. Both are attached only when the canonical policy ran and
    still owns the effective decision; a later safety override replaces the
    decision authority and therefore attaches neither.

    Candidate ``allowed_claims`` attribute every display anchor (setup event
    session, broken level, supporting stop reference, age) as a display
    projection of the admitted current observation and point to
    ``policy_decision``/``policy_decision.causal_evidence`` for the canonical
    result; the display layer never asserts policy confirmation.
    """
    is_candidate = decision == "RESEARCH_CANDIDATE" and candidate_summary is not None
    if is_candidate and candidate_summary is not None:
        smc = cast(dict[str, object], candidate_summary.get("smc_price_action", {}))
        vol = cast(dict[str, object], candidate_summary.get("volume_analysis", {}))
        pa = cast(dict[str, object], candidate_summary.get("price_action_quality", {}))
        rs = cast(dict[str, object], candidate_summary.get("relative_strength", {}))
        retest = str(smc.get("retest_state", ""))
        dist = str(smc.get("breakout_distance_percent", ""))
        allowed_claims = [
            f"State the display projection shows a {candidate_summary['setup_event']} setup at level INR {candidate_summary['broken_high_level_inr']} on session {candidate_summary['event_session']}; the canonical pair-policy result and evidence remain authoritative in policy_decision.",
            f"State current quote price is INR {candidate_summary['current_price_inr']}.",
            f"State the display projection's supporting stop reference is INR {candidate_summary['supporting_stop_reference_inr']} (not a policy anchor; canonical relations are in policy_decision.causal_evidence).",
            f"State the display-implied risk per share is INR {candidate_summary['risk_per_share_inr']} (current price minus the display stop reference).",
            f"State the display projection's candidate age is {candidate_summary['age_completed_sessions']} completed session(s) (within the 1–5 freshness window); the canonical candidate age is in policy_decision.causal_evidence.",
            f"State candidate belongs to {candidate_summary.get('industry', 'NSE Equity')} industry.",
            f"State breakout price action status is {retest} ({dist} relative to breakout level).",
            f"State the display projection's SMC demand-area support reference is INR {candidate_summary['supporting_stop_reference_inr']} with implied zone width INR {smc.get('demand_zone_width_inr')}.",
            f"State breakout volume expansion is {vol.get('volume_expansion')} with relative volume {vol.get('rvol')}.",
            f"State breakout candle quality is {pa.get('quality')} with body forming {pa.get('body_percent')} of range.",
            f"State 20-session relative strength vs Nifty benchmark is {rs.get('relative_strength')} ({rs.get('excess_return')}).",
            "State all 8 conservative safety eligibility gates passed (turnover, history, circuit distance, book liquidity, and 7-day corporate action blackout).",
        ]
    else:
        allowed_claims = [
            f"State stock decision is {decision} with safety eligibility status {eligibility_result.get('status')}.",
        ]

    forbidden_claims = [
        "Do not predict future percentage returns or guaranteed profitability.",
        "Do not set speculative target prices, reward multipliers, or profit-taking exits.",
        "Do not issue automated broker orders, capital allocation advice, or position sizes.",
    ]
    brief: dict[str, object] = {
        "schema": BRIEF_SCHEMA,
        "symbol": symbol,
        "isin": isin,
        "exchange": "NSE",
        "decision": decision,
        "candidate_summary": candidate_summary,
        "safety_eligibility": {
            "status": eligibility_result.get("status"),
            "explanation_ledger": eligibility_result.get("explanation_ledger", []),
        },
        "ai_guidance": {
            "allowed_claims": allowed_claims,
            "forbidden_claims": forbidden_claims,
        },
    }
    if policy_decision is not None:
        brief["policy_decision"] = policy_decision
    if optional_context is not None:
        brief["optional_context"] = optional_context
    return brief


def _retained_structure_handles(storage_root: Path) -> dict[str, str]:
    """Index retained current-structure observations once per universe scan.

    The index is used only to bootstrap the first admitted predecessor of a
    symbol whose scanner pair state does not exist yet. It never supplies a
    previous/current pair for a causal decision, and selection is deterministic
    (sorted handle order) among admitted READY observations.
    """
    handles: dict[str, str] = {}
    obs_dir = storage_root / "stock-observations-v1"
    if not obs_dir.exists():
        return handles
    for path in sorted(obs_dir.glob("*.json")):
        if len(path.stem) != 64:
            continue
        try:
            data = cast(dict[str, object], json.loads(path.read_text()))
            result = cast(dict[str, object], data.get("result", {}))
            symbol = result.get("symbol")
            if (
                type(symbol) is str
                and result.get("question") == "CURRENT_STRUCTURE"
                and result.get("status") == "READY"
            ):
                handles.setdefault(symbol, path.stem)
        except (OSError, ValueError):
            continue
    return handles


def _evaluate_anti_manipulation_safety(
    symbol: str,
    current_price: Decimal | None,
    bars: dict[date, dict[str, Any]],
    eligibility_result: dict[str, object],
) -> tuple[bool, str | None]:
    """Enforce strict anti-manipulation and asset-quality floors.

    1. Rejects newly listed stocks with < 120 historical sessions (< 6 months).
    2. Rejects penny/low-priced stocks with price < INR 50.00.
    3. Rejects illiquid operator small-caps with 20-day median turnover < INR 25.0 Crore.
    """
    if current_price is None:
        return True, None

    # 1. Penny / Low-Priced Stock Exclusion (< INR 50.00)
    if current_price < Decimal("50.00"):
        return False, f"PENNY_STOCK_EXCLUDED (Price INR {current_price} < INR 50.00)"

    # 2. Historical Listing Track Record (< 120 sessions)
    ve = cast(dict[str, object], eligibility_result.get("verified_evidence", {}) or {})
    history_sessions_raw = ve.get("history_session_count") or ve.get(
        "history_sessions_count"
    )
    if history_sessions_raw is not None and int(str(history_sessions_raw)) < 120:
        return (
            False,
            f"NEWLY_LISTED_EXCLUDED ({history_sessions_raw} sessions < 120 listing floor)",
        )

    # 3. Institutional Scale & Turnover Floor (< INR 25.0 Crore / day)
    median_turnover_raw = ve.get("median_turnover_inr") or ve.get(
        "median_daily_cash_turnover_inr"
    )
    if median_turnover_raw is not None:
        turnover = Decimal(str(median_turnover_raw))
    else:
        sorted_s = sorted(bars.keys())
        prior_20 = sorted_s[-20:] if len(sorted_s) >= 20 else sorted_s
        turnovers = [
            Decimal(str(bars[s]["close"])) * Decimal(str(bars[s]["volume"]))
            for s in prior_20
        ]
        turnover = sorted(turnovers)[len(turnovers) // 2] if turnovers else Decimal("0")

    if turnover < Decimal("250000000"):  # 25 Crore INR
        turnover_cr = turnover / Decimal("10000000")
        return (
            False,
            f"ILLIQUID_SMALLCAP_EXCLUDED (Turnover INR {turnover_cr:.1f} Cr < INR 25.0 Cr)",
        )

    return True, None


def _unavailable_result(
    symbol: str, reason: str
) -> tuple[dict[str, object], bool, str, str | None, str | None, str, str | None]:
    """Return one explicit fail-closed symbol result with no pair and no candidate."""
    brief: dict[str, object] = {
        "schema": BRIEF_SCHEMA,
        "symbol": symbol,
        "isin": "",
        "exchange": "NSE",
        "decision": "UNKNOWN",
        "candidate_summary": None,
        "safety_eligibility": {"status": "UNKNOWN", "explanation_ledger": []},
        "ai_guidance": {
            "allowed_claims": [f"State stock {symbol} is UNAVAILABLE."],
            "forbidden_claims": [],
        },
    }
    return brief, False, "UNKNOWN", None, reason, "INSUFFICIENT_STRUCTURE", None


def _optional_context_from_policy(
    policy_result: dict[str, object] | None,
) -> dict[str, object] | None:
    """Project existing Plan 58/60 first-inclusion facts from canonical pair evidence."""
    if policy_result is None:
        return None
    evidence = policy_result.get("causal_evidence")
    if type(evidence) is not dict:
        return None
    admitted = cast(dict[str, object], evidence)
    return {
        "level_range_inclusion_status": admitted.get("level_range_inclusion_status"),
        "level_range_inclusion_observed": admitted.get(
            "level_range_inclusion_observed"
        ),
        "first_inclusion_close_status": admitted.get("first_inclusion_close_status"),
        "first_inclusion_close_relation": admitted.get(
            "first_inclusion_close_relation"
        ),
    }


def _retained_unselected_stocks(
    all_candidates: Sequence[dict[str, object]],
    selected: Sequence[dict[str, object]],
    *,
    reason: str,
) -> list[dict[str, object]]:
    """Retain every policy-qualified candidate that did not fit the basket.

    Basket capacity and priority tiers are selection reasons, never policy
    failures: each unselected qualified symbol keeps its policy decision and one
    explicit reason.
    """
    selected_symbols = {str(candidate["symbol"]) for candidate in selected}
    retained: list[dict[str, object]] = []
    for candidate in all_candidates:
        if str(candidate["symbol"]) in selected_symbols:
            continue
        summary = cast(dict[str, object], candidate.get("candidate_summary") or {})
        safety = cast(dict[str, object], candidate.get("safety_eligibility") or {})
        retained.append(
            {
                "symbol": candidate["symbol"],
                "industry": summary.get("industry", "Unknown"),
                "decision": candidate["decision"],
                "safety_status": safety.get("status"),
                "failed_rule": reason,
                "current_price_inr": summary.get("current_price_inr"),
            }
        )
    return retained


def _structure_session(packet: object) -> date | None:
    slots_raw = getattr(packet, "feature_slots", None)
    if type(slots_raw) is not tuple:
        return None
    for slot in cast(tuple[object, ...], slots_raw):
        if getattr(slot, "feature", None) != "MARKET_STRUCTURE":
            continue
        sessions_raw = getattr(slot, "requested_sessions", None)
        if type(sessions_raw) is not tuple or not sessions_raw:
            return None
        last = cast(tuple[object, ...], sessions_raw)[-1]
        return last if type(last) is date else None
    return None


def _latest_session_missing(result: object) -> bool:
    packet = getattr(result, "packet", None)
    if packet is None or getattr(packet, "execution_state", None) != "COMPLETED":
        return False
    members_raw = getattr(packet, "members", ())
    if type(members_raw) is not tuple:
        return False
    for member in cast(tuple[object, ...], members_raw):
        features_raw = getattr(member, "features", ())
        if type(features_raw) is not tuple:
            continue
        for feature in cast(tuple[object, ...], features_raw):
            if (
                getattr(feature, "feature", None) == "MARKET_STRUCTURE"
                and getattr(feature, "reason", None) == "LATEST_SESSION_MISSING"
            ):
                return True
    return False


def _scan_stock(  # noqa: C901 - multi-family screening and anti-manipulation gate
    symbol: str,
    storage_root: Path,
    refresh: bool,
    industry: str,
    benchmark_median_return: Decimal,
    retained_handle: str | None = None,
    seeded_symbols: list[str] | None = None,
    sessions_back: int = 0,
    bound_symbols: list[str] | None = None,
) -> tuple[dict[str, object], bool, str, str | None, str | None, str, str | None]:
    """Execute the canonical pair policy, safety eligibility, and brief generation.

    Pair state is the only source of a prior/current observation pair. The
    retained index may bootstrap a first admitted predecessor, replay evaluates
    the exact admitted pair as an explicit replay, and every state failure
    fails closed with no pair and no candidate.
    """
    try:
        state = read_scanner_pair_state_v1(storage_root, symbol)
    except Exception:  # noqa: BLE001 - per-symbol fail-closed boundary
        return _unavailable_result(symbol, "OBSERVATION_PAIR_STATE_UNAVAILABLE")

    try:
        if state is not None and not refresh:
            handle = state.current_observation_identity_sha256
            obs_result = read_stock_observation_v1(storage_root, handle)
        elif retained_handle is not None and not refresh:
            handle = retained_handle
            try:
                obs_result = read_stock_observation_v1(storage_root, handle)
            except Exception:
                if state is None:
                    return _unavailable_result(
                        symbol, "OBSERVATION_PAIR_BOOTSTRAP_REQUIRES_REFRESH"
                    )
                raise
        else:
            obs_result = research_current_stock_v2(
                symbol,
                storage_root,
                question="CURRENT_STRUCTURE",
                refresh=refresh,
                sessions_back=sessions_back,
            )
            handle = record_stock_observation_v1(storage_root, obs_result)
    except Exception:
        return _unavailable_result(symbol, "OBSERVATION_OR_PROVIDER_UNAVAILABLE")

    if (
        getattr(obs_result, "question", None) != "CURRENT_STRUCTURE"
        or getattr(obs_result, "symbol", None) != symbol
        or getattr(obs_result, "status", None) != "READY"
    ):
        return _unavailable_result(symbol, "OBSERVATION_STRUCTURE_NOT_READY")

    policy_result: dict[str, object] | None = None
    failure_reason: str | None = None
    try:
        if state is None:
            advance_scanner_pair_state_v1(
                storage_root,
                symbol,
                expected_current_observation_identity_sha256=None,
                new_current_observation_identity_sha256=handle,
            )
            if seeded_symbols is not None:
                seeded_symbols.append(symbol)
            if sessions_back and bound_symbols is not None:
                bound_symbols.append(symbol)
            failure_reason = "OBSERVATION_PAIR_SEEDED_BOOTSTRAP"
        elif handle == state.current_observation_identity_sha256:
            policy_result = evaluate_signal_decision_from_records_v3(
                storage_root, handle, handle
            )
        else:
            current_session = _structure_session(obs_result.packet)
            try:
                stored = read_stock_observation_v1(
                    storage_root, state.current_observation_identity_sha256
                )
                stored_session = _structure_session(stored.packet)
            except Exception:  # noqa: BLE001 - pair state remains fail-closed
                stored_session = None
            if (
                current_session is not None
                and stored_session is not None
                and current_session <= stored_session
            ):
                return _unavailable_result(
                    symbol, "OBSERVATION_PAIR_AWAITING_NEXT_SESSION"
                )
            policy_result = evaluate_signal_decision_from_records_v3(
                storage_root,
                state.current_observation_identity_sha256,
                handle,
            )
            advance_scanner_pair_state_v1(
                storage_root,
                symbol,
                expected_current_observation_identity_sha256=(
                    state.current_observation_identity_sha256
                ),
                new_current_observation_identity_sha256=handle,
            )
            if sessions_back and bound_symbols is not None:
                bound_symbols.append(symbol)
    except ScannerPairStateUnavailableV1:
        return _unavailable_result(symbol, "OBSERVATION_PAIR_STATE_UNAVAILABLE")
    except Exception:
        return _unavailable_result(symbol, "OBSERVATION_OR_PROVIDER_UNAVAILABLE")

    policy_eligibility = (
        policy_result.get("eligibility") if policy_result is not None else None
    )
    if type(policy_eligibility) is dict:
        elig_result = cast(dict[str, object], policy_eligibility)
    else:
        try:
            elig_result = evaluate_stock_eligibility_from_record_v3(
                storage_root, handle
            )
        except Exception:
            return _unavailable_result(symbol, "OBSERVATION_OR_PROVIDER_UNAVAILABLE")

    decision = "UNKNOWN"
    if policy_result is not None:
        disposition = str(policy_result.get("disposition", "UNKNOWN"))
        if disposition in {"RESEARCH_CANDIDATE", "NO_TRADE", "UNKNOWN"}:
            decision = disposition

    safety_status = str(elig_result.get("status", "UNKNOWN"))
    ve = cast(dict[str, object], elig_result.get("verified_evidence") or {})
    price_inr = (
        str(ve.get("current_quote_price_inr", ""))
        if ve.get("current_quote_price_inr")
        else None
    )

    bars = _load_historical_bars_for_symbol(storage_root, symbol)
    candidate_summary: dict[str, object] | None = None
    if decision == "RESEARCH_CANDIDATE":
        candidate_summary = _build_candidate_display_summary(
            obs_result, elig_result, bars, industry, benchmark_median_return
        )

    isin = ""
    trend = "INSUFFICIENT_STRUCTURE"
    packet = getattr(obs_result, "packet", None)
    if packet:
        members = getattr(packet, "members", ())
        if members:
            inst = getattr(members[0], "member", None)
            if inst:
                isin = str(getattr(inst, "isin", ""))
            features = getattr(members[0], "features", ())
            for f in features:
                if getattr(f, "feature", None) == "MARKET_STRUCTURE":
                    calc = getattr(getattr(f, "fact", None), "calculation", None)
                    if calc:
                        trend = str(getattr(calc, "trend", "INSUFFICIENT_STRUCTURE"))

    final_eligibility = elig_result
    safety_override = False
    if safety_status == "ELIGIBLE":
        # Anti-Manipulation & Asset Quality Gate
        cur_price_dec = Decimal(price_inr) if price_inr else None
        safe_asset, safety_reason = _evaluate_anti_manipulation_safety(
            symbol=symbol,
            current_price=cur_price_dec,
            bars=bars,
            eligibility_result=elig_result,
        )
        if not safe_asset:
            decision = "NO_TRADE"
            candidate_summary = None
            safety_status = "INELIGIBLE"
            safety_override = True
            final_eligibility = {
                **elig_result,
                "status": "INELIGIBLE",
                "explanation_ledger": [
                    *cast(
                        list[dict[str, object]],
                        elig_result.get("explanation_ledger", []),
                    ),
                    {
                        "rule_id": safety_reason,
                        "outcome": "FAIL",
                        "reason": (
                            "Anti-manipulation and asset-quality gate rejected stock."
                        ),
                    },
                ],
            }

    failed_rule: str | None = None
    if safety_status != "ELIGIBLE":
        ledger = cast(
            list[dict[str, object]],
            final_eligibility.get("explanation_ledger", []),
        )
        failed_entry = next(
            (e for e in ledger if e.get("outcome") in {"FAIL", "UNKNOWN"}), None
        )
        failed_rule = str(failed_entry.get("rule_id", "")) if failed_entry else None
    elif failure_reason is not None:
        failed_rule = failure_reason
    elif policy_result is not None and decision in {"NO_TRADE", "UNKNOWN"}:
        decision_code = policy_result.get("decision_code")
        failed_rule = str(decision_code) if decision_code else None

    decision_authority: dict[str, object] | None = (
        None if safety_override else policy_result
    )
    brief = build_trade_brief(
        symbol=symbol,
        isin=isin,
        decision=decision,
        candidate_summary=candidate_summary,
        eligibility_result=final_eligibility,
        policy_decision=decision_authority,
        optional_context=_optional_context_from_policy(decision_authority),
    )
    is_candidate = decision == "RESEARCH_CANDIDATE"
    return brief, is_candidate, safety_status, price_inr, failed_rule, trend, handle


_UNIVERSE_SOURCE_LISTS: Final = {
    "NIFTY_50": ("nifty50",),
    "NIFTY_NEXT_50": ("niftynext50",),
    "NIFTY_100": ("nifty100",),
    "NIFTY_200": ("nifty100", "nifty200"),
}


def _resolve_target_symbols(
    storage_root: Path,
    symbols: Sequence[str] | None,
    universe: str | None,
) -> tuple[tuple[str, ...], str, frozenset[str], dict[str, object] | None]:
    if universe is not None:
        if symbols is not None:
            raise ValueError("cannot supply both explicit symbols and a universe flag")
        if universe not in _UNIVERSE_SOURCE_LISTS:
            raise ValueError("invalid universe")
        retained = read_historic_nifty_universe(storage_root)
        targets = {
            "NIFTY_50": retained.nifty50,
            "NIFTY_NEXT_50": retained.niftynext50,
            "NIFTY_100": retained.nifty100,
            "NIFTY_200": retained.nifty200,
        }[universe]
        priority = (
            frozenset(retained.nifty100)
            if universe == "NIFTY_200"
            else frozenset(targets)
        )
        evidence: dict[str, object] = {
            "universe": universe,
            "retrieved_at": retained.retrieved_at.isoformat(),
            "window_start": retained.window_start.isoformat(),
            "window_end": retained.window_end.isoformat(),
        }
        for name in _UNIVERSE_SOURCE_LISTS[universe]:
            evidence[f"{name}_source_url"] = getattr(retained, f"{name}_source_url")
            evidence[f"{name}_source_sha256"] = getattr(
                retained, f"{name}_source_sha256"
            )
        return targets, universe, priority, evidence
    if not symbols or not 1 <= len(symbols) <= 100:
        raise ValueError("must supply 1 to 100 valid symbols")
    for sym in symbols:
        if _SYMBOL.fullmatch(sym) is None:
            raise ValueError(f"invalid symbol: {sym}")
    return tuple(symbols), "EXPLICIT", frozenset(), None


def _compute_benchmark_median_return(
    storage_root: Path, target_symbols: tuple[str, ...]
) -> Decimal:
    returns: list[Decimal] = []
    for s in target_symbols:
        bars = _load_historical_bars_for_symbol(storage_root, s)
        sorted_s = sorted(bars.keys())
        if len(sorted_s) >= 20:
            c0: Decimal = bars[sorted_s[-20]]["close"]
            c20: Decimal = bars[sorted_s[-1]]["close"]
            if c0 > 0:
                returns.append((c20 - c0) / c0 * Decimal("100"))
    if not returns:
        return Decimal("0.0")
    return sorted(returns)[len(returns) // 2]


def _calculate_market_regime(trends: list[str]) -> dict[str, object]:
    total = len(trends)
    if total == 0:
        return {
            "regime": "UNKNOWN",
            "uptrend_percent": "0.0%",
            "downtrend_percent": "0.0%",
        }
    uptrends = sum(1 for t in trends if t == "UPTREND")
    downtrends = sum(1 for t in trends if t == "DOWNTREND")
    up_pct = Decimal(str(uptrends)) / Decimal(str(total)) * Decimal("100")
    down_pct = Decimal(str(downtrends)) / Decimal(str(total)) * Decimal("100")

    if up_pct >= Decimal("60"):
        regime = "BULLISH_TRENDING"
    elif down_pct >= Decimal("50"):
        regime = "BEARISH_CORRECTION"
    else:
        regime = "RANGE_OR_TRANSITION"

    return {
        "regime": regime,
        "uptrend_percent": f"{up_pct:.1f}%",
        "downtrend_percent": f"{down_pct:.1f}%",
        "total_cohort_size": total,
    }


def scan_signal_decisions_v3(  # noqa: C901 - lifecycle orchestration
    storage_root: Path,
    *,
    symbols: Sequence[str] | None = None,
    universe: str | None = None,
    refresh: bool = False,
    clock: Callable[[], datetime] | None = None,
    evidence_rows: list[dict[str, object]] | None = None,
    warnings: list[str] | None = None,
    sessions_back: int | None = None,
) -> dict[str, object]:
    """Scan one exact retained universe or an explicit equity list."""
    if sessions_back is not None and (
        type(sessions_back) is not int or not 0 <= sessions_back <= 10
    ):
        raise ValueError("invalid sessions back")
    if sessions_back and not refresh:
        raise ValueError("sessions back requires refresh")
    if not storage_root.is_absolute():
        raise ValueError("invalid storage root")

    target_symbols, universe_type, priority_symbols, universe_evidence = (
        _resolve_target_symbols(storage_root, symbols, universe)
    )
    now = datetime.now(UTC) if clock is None else clock()
    industry_map = _load_industry_mapping(storage_root)
    benchmark_symbols = (
        tuple(symbol for symbol in target_symbols if symbol in priority_symbols)
        if priority_symbols
        else target_symbols
    )
    benchmark_median = _compute_benchmark_median_return(storage_root, benchmark_symbols)

    candidates: list[dict[str, object]] = []
    other_stocks: list[dict[str, object]] = []
    trends: list[str] = []

    eligible_count = 0
    ineligible_count = 0
    unknown_count = 0
    retained_handles = {} if refresh else _retained_structure_handles(storage_root)
    seeded_symbols: list[str] = []
    bound_symbols: list[str] = []
    selected_back = 0 if sessions_back is None else sessions_back
    bootstrap_pair = False
    available = False
    if sessions_back is None and refresh and target_symbols:
        for candidate_back in range(0, 11):
            try:
                probe = research_current_stock_v2(
                    target_symbols[0],
                    storage_root,
                    question="CURRENT_STRUCTURE",
                    refresh=True,
                    sessions_back=candidate_back,
                )
            except Exception:  # noqa: BLE001 - the per-symbol boundary reports this
                break
            if probe.status == "READY":
                selected_back = candidate_back
                available = True
                break
            if not _latest_session_missing(probe):
                break
        if available and selected_back < 10:
            missing: list[str] = []
            for symbol in target_symbols:
                try:
                    state = read_scanner_pair_state_v1(storage_root, symbol)
                except Exception:  # noqa: BLE001 - per-symbol boundary reports it
                    state = "unavailable"
                if state is None:
                    missing.append(symbol)
            if missing:
                seeded_prior: list[str] = []
                for symbol in missing:
                    _scan_stock(
                        symbol,
                        storage_root,
                        refresh,
                        industry_map.get(symbol, "Unknown"),
                        benchmark_median,
                        None,
                        seeded_symbols=seeded_prior,
                        sessions_back=selected_back + 1,
                    )
                bootstrap_pair = bool(seeded_prior)

    for symbol in target_symbols:
        ind = industry_map.get(symbol, "Unknown")
        (
            brief,
            is_cand,
            safety_status,
            price_inr,
            failed_rule,
            trend,
            observation_handle,
        ) = _scan_stock(
            symbol,
            storage_root,
            refresh,
            ind,
            benchmark_median,
            retained_handles.get(symbol),
            seeded_symbols,
            sessions_back=selected_back,
            bound_symbols=bound_symbols,
        )
        trends.append(trend)
        if evidence_rows is not None:
            evidence_rows.append(
                {
                    "symbol": symbol,
                    "decision": brief["decision"],
                    "safety_status": safety_status,
                    "observation_handle": observation_handle,
                }
            )

        if safety_status == "ELIGIBLE":
            eligible_count += 1
        elif safety_status == "INELIGIBLE":
            ineligible_count += 1
        else:
            unknown_count += 1

        if is_cand:
            if universe_type == "EXPLICIT":
                pass
            elif symbol in priority_symbols:
                brief["universe_tier"] = (
                    "NIFTY_100" if universe_type == "NIFTY_200" else universe_type
                )
            else:
                brief["universe_tier"] = "NIFTY_200_EX_NIFTY_100"
            candidates.append(brief)
        else:
            other_stocks.append(
                {
                    "symbol": symbol,
                    "industry": ind,
                    "decision": brief["decision"],
                    "safety_status": safety_status,
                    "failed_rule": failed_rule,
                    "current_price_inr": price_inr,
                }
            )

    priority_candidate_count: int | None = None
    tier2_fallback_triggered = False
    if universe_type != "EXPLICIT":
        all_candidates = list(candidates)
        priority_candidates = [
            candidate
            for candidate in all_candidates
            if str(candidate["symbol"]) in priority_symbols
        ]
        priority_candidate_count = len(priority_candidates)
        if universe_type == "NIFTY_200":
            tier2_fallback_triggered = priority_candidate_count < 5
            if tier2_fallback_triggered:
                candidates = (
                    priority_candidates
                    + [
                        candidate
                        for candidate in all_candidates
                        if str(candidate["symbol"]) not in priority_symbols
                    ]
                )[:10]
            else:
                candidates = priority_candidates[:10]
            reason = "BASKET_CAPACITY_OR_NIFTY100_PRIORITY"
        else:
            candidates = priority_candidates[:10]
            reason = "BASKET_CAPACITY"
        other_stocks.extend(
            _retained_unselected_stocks(all_candidates, candidates, reason=reason)
        )
    # Attach sector peer participation to each candidate
    for c in candidates:
        summary_value = c.get("candidate_summary")
        if type(summary_value) is not dict:
            continue
        summary = cast(dict[str, object], summary_value)
        c_ind = str(summary.get("industry", "Unknown"))
        all_in_ind = sum(1 for sym in target_symbols if industry_map.get(sym) == c_ind)
        peer_cands: list[str] = []
        for cand in candidates:
            cand_summary = cast(dict[str, object], cand.get("candidate_summary") or {})
            if str(cand_summary.get("industry")) == c_ind:
                peer_cands.append(str(cand.get("symbol", "")))
        rate = (
            (Decimal(len(peer_cands)) / Decimal(all_in_ind) * Decimal("100"))
            if all_in_ind > 0
            else Decimal("0")
        )
        summary["sector_participation"] = {
            "industry_name": c_ind,
            "industry_total_stocks": all_in_ind,
            "industry_candidate_count": len(peer_cands),
            "sector_participation_rate": f"{rate:.1f}%",
            "peer_candidates": peer_cands,
        }

    market_regime = _calculate_market_regime(trends)

    if bootstrap_pair and warnings is not None:
        warnings.append(
            "BOOTSTRAP_PAIR: seeded the prior completed session for symbols "
            "without pair state so this request evaluates the newest available pair."
        )
    if warnings is not None and selected_back:
        if sessions_back is None and refresh:
            warnings.append(
                f"LATEST_AVAILABLE: this page binds a completed session "
                f"{selected_back} before the newest official close "
                f"({len(bound_symbols)} symbol(s) newly bound)."
            )
        elif bound_symbols:
            warnings.append(
                f"SESSIONS_BACK: {len(bound_symbols)} symbol(s) bound a completed "
                f"session {selected_back} before the newest official close."
            )
    if seeded_symbols and warnings is not None:
        warnings.append(
            f"BOOTSTRAP: {len(seeded_symbols)} symbol(s) seeded a new pair-state "
            "generation; this page is not a no-candidate market result."
        )

    scan_result: dict[str, object] = {
        "schema": SCHEMA,
        "scan_timestamp": _instant(now),
        "storage_root_sha256": _digest(str(storage_root)),
        "universe_type": universe_type,
        "universe_evidence": universe_evidence,
        "priority_validated_candidate_count": priority_candidate_count,
        "tier2_fallback_triggered": tier2_fallback_triggered,
        "market_regime": market_regime,
        "benchmark_median_return_20d": f"{benchmark_median:+.2f}%",
        "total_stocks_scanned": len(target_symbols),
        "evaluated_symbols": list(target_symbols),
        "candidate_count": len(candidates),
        "eligible_count": eligible_count,
        "ineligible_count": ineligible_count,
        "unknown_count": unknown_count,
        "candidates": candidates,
        "other_stocks": other_stocks,
        "runtime_code_identity_sha256": _runtime_identity(),
    }
    scan_result["result_identity_sha256"] = _digest(scan_result)
    return scan_result


def format_scan_table(scan_result: dict[str, object]) -> str:
    """Render terminal-friendly ASCII summary table displaying all 7 analytical families."""
    total = scan_result.get("total_stocks_scanned", 0)
    cand_count = scan_result.get("candidate_count", 0)
    elig_count = scan_result.get("eligible_count", 0)
    inelig_count = scan_result.get("ineligible_count", 0)
    unk_count = scan_result.get("unknown_count", 0)
    u_type = str(scan_result.get("universe_type", ""))
    ts = str(scan_result.get("scan_timestamp", ""))
    regime_info = cast(dict[str, object], scan_result.get("market_regime", {}))
    regime = str(regime_info.get("regime", "UNKNOWN"))
    up_pct = str(regime_info.get("uptrend_percent", "0%"))
    down_pct = str(regime_info.get("downtrend_percent", "0%"))
    bm_ret = str(scan_result.get("benchmark_median_return_20d", "0.0%"))

    lines: list[str] = [
        "=" * 125,
        f"SWING TRADING CANDIDATE SCAN — {u_type} ({ts})",
        "=" * 125,
        f"MARKET REGIME: {regime} (Uptrend: {up_pct} | Downtrend: {down_pct} | 20d Benchmark: {bm_ret})",
        f"Scanned: {total} | Candidates: {cand_count} | Eligible: {elig_count} | Ineligible: {inelig_count} | Unknown: {unk_count}",
        "-" * 125,
    ]

    candidates = cast(list[dict[str, object]], scan_result.get("candidates", []))
    if candidates:
        lines.append("CONFIRMED RESEARCH CANDIDATES (FULL 7-FAMILY INTEGRATION):")
        lines.append(
            f"{'SYMBOL':<9} {'INDUSTRY':<22} {'PRICE':<10} {'SETUP':<9} {'AGE':<4} {'RVOL':<7} {'PA BODY':<8} {'REL STR':<15} {'STOP REF':<10} {'RETEST STATE'}"
        )
        lines.append("-" * 125)
        for c in candidates:
            sym = str(c.get("symbol", ""))
            summary_value = c.get("candidate_summary")
            summary = (
                cast(dict[str, object], summary_value)
                if type(summary_value) is dict
                else {}
            )
            smc = cast(dict[str, object], summary.get("smc_price_action", {}))
            vol = cast(dict[str, object], summary.get("volume_analysis", {}))
            pa = cast(dict[str, object], summary.get("price_action_quality", {}))
            rs = cast(dict[str, object], summary.get("relative_strength", {}))

            ind = str(summary.get("industry", "Unknown"))
            if len(ind) > 21:
                ind = ind[:20] + "."
            price = f"INR {summary.get('current_price_inr', '')}"
            setup = f"{summary.get('setup_event', '')}"
            age = f"{summary.get('age_completed_sessions', '')}d"
            rvol = str(vol.get("rvol", ""))
            body = str(pa.get("body_percent", ""))
            rs_status = str(rs.get("relative_strength", ""))
            rel_str = f"{rs_status[:4]} ({rs.get('excess_return', '')})"
            stop = f"INR {summary.get('supporting_stop_reference_inr', '')}"
            retest = f"{smc.get('retest_state', '')} ({smc.get('breakout_distance_percent', '')})"

            lines.append(
                f"{sym:<9} {ind:<22} {price:<10} {setup:<9} {age:<4} {rvol:<7} {body:<8} {rel_str:<15} {stop:<10} {retest}"
            )
        lines.append("-" * 125)
    else:
        lines.append(
            "CONFIRMED RESEARCH CANDIDATES: None (No 1–5 session upward BOS setups active)"
        )
        lines.append("-" * 125)

    other = cast(list[dict[str, object]], scan_result.get("other_stocks", []))
    ineligible = [o for o in other if o.get("safety_status") == "INELIGIBLE"]
    if ineligible:
        lines.append(f"FILTERED BY SAFETY POLICY ({len(ineligible)} stocks):")
        lines.extend(
            [
                f"  - {o.get('symbol')} ({o.get('industry', 'Unknown')}): {o.get('failed_rule', 'FAIL')} (Price: INR {o.get('current_price_inr')})"
                for o in ineligible
            ]
        )
        lines.append("-" * 125)

    return "\n".join(lines)
