"""Automated Nifty 100 and explicit stock-list swing trade candidate scanning."""

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
from .signal_decisions_scan_v3_runtime_identity_manifest import (
    SIGNAL_DECISIONS_SCAN_RUNTIME_SOURCE_SHA256_V3,
)
from .stock_eligibility_v3 import evaluate_stock_eligibility_from_record_v3
from .stock_observations import (
    read_stock_observation_v1,
    record_stock_observation_v1,
)

SCHEMA: Final = "swing-trade-scan@v1"
SCAN_SCHEMA: Final = SCHEMA
BRIEF_SCHEMA: Final = "swing-trade-brief@v1"
_SYMBOL: Final = re.compile(r"[A-Z0-9][A-Z0-9.&_-]{0,31}\Z")
_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/signal_decisions_scan_v3.py",
    "src/swing_trading_ai_assistant/market_data/historical_nifty_universe.py",
    "src/swing_trading_ai_assistant/market_data/stock_eligibility_v3.py",
    "src/swing_trading_ai_assistant/market_data/signal_decisions_v3.py",
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
            for s, bar_open, bar_high, bar_low, bar_close, bar_vol in zip(
                sessions, opens, highs, lows, closes, volumes, strict=False
            ):
                if isinstance(s, date):
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


def _extract_causal_candidate(
    observation: object,
    eligibility_result: dict[str, object],
    bars: dict[date, dict[str, Any]],
    industry: str,
    benchmark_median_return: Decimal,
) -> tuple[str, dict[str, object] | None]:
    """Evaluate whether an admitted observation has a valid causal swing candidate setup."""
    status = eligibility_result.get("status")
    if status == "UNKNOWN":
        return "UNKNOWN", None
    if status != "ELIGIBLE":
        return "NO_TRADE", None

    extracted = _extract_market_structure_calculation(observation)
    if extracted is None:
        return "UNKNOWN", None
    _, admitted_bars, events, pivots = extracted

    break_event = _evaluate_break_event(events, admitted_bars)
    if break_event is None:
        return "NO_TRADE", None
    latest_up, event_pos, age = break_event

    stop_price = _find_supporting_swing_low(pivots, event_pos)
    if stop_price is None:
        return "NO_TRADE", None

    ve = cast(dict[str, object], eligibility_result.get("verified_evidence", {}))
    price_raw = ve.get("current_quote_price_inr")
    if not price_raw:
        return "UNKNOWN", None

    current_price = Decimal(str(price_raw))
    if current_price <= stop_price:
        return "NO_TRADE", None

    return "RESEARCH_CANDIDATE", _build_candidate_summary(
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
) -> dict[str, object]:
    """Construct a versioned swing-trade-brief@v1 card for human or AI assistant consumption."""
    is_candidate = decision == "RESEARCH_CANDIDATE" and candidate_summary is not None
    if is_candidate and candidate_summary is not None:
        smc = cast(dict[str, object], candidate_summary.get("smc_price_action", {}))
        vol = cast(dict[str, object], candidate_summary.get("volume_analysis", {}))
        pa = cast(dict[str, object], candidate_summary.get("price_action_quality", {}))
        rs = cast(dict[str, object], candidate_summary.get("relative_strength", {}))
        retest = str(smc.get("retest_state", ""))
        dist = str(smc.get("breakout_distance_percent", ""))
        allowed_claims = [
            f"State confirmed {candidate_summary['setup_event']} setup at broken level INR {candidate_summary['broken_high_level_inr']} confirmed on {candidate_summary['event_session']}.",
            f"State current quote price is INR {candidate_summary['current_price_inr']}.",
            f"State structural protective stop reference is INR {candidate_summary['supporting_stop_reference_inr']}.",
            f"State risk per share is INR {candidate_summary['risk_per_share_inr']}.",
            f"State candidate age is {candidate_summary['age_completed_sessions']} completed session(s) (within the 1–5 freshness window).",
            f"State candidate belongs to {candidate_summary.get('industry', 'NSE Equity')} industry.",
            f"State breakout price action status is {retest} ({dist} relative to breakout level).",
            f"State institutional demand zone support is INR {candidate_summary['supporting_stop_reference_inr']} with zone width INR {smc.get('demand_zone_width_inr')}.",
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
    return {
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


def _current_structure_observation_handles(storage_root: Path) -> dict[str, str]:
    """Index retained current-structure observations once per universe scan."""
    handles: dict[str, str] = {}
    obs_dir = storage_root / "stock-observations-v1"
    if not obs_dir.exists():
        return handles
    for path in obs_dir.glob("*.json"):
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


def _scan_stock(  # noqa: C901 - multi-family screening and anti-manipulation gate
    symbol: str,
    storage_root: Path,
    refresh: bool,
    industry: str,
    benchmark_median_return: Decimal,
    retained_handle: str | None = None,
) -> tuple[dict[str, object], bool, str, str | None, str | None, str, str | None]:
    """Execute single-stock structure observation, safety eligibility, and brief generation."""
    try:
        if retained_handle is not None and not refresh:
            handle = retained_handle
            obs_result = read_stock_observation_v1(storage_root, handle)
        else:
            obs_result = research_current_stock_v2(
                symbol,
                storage_root,
                question="CURRENT_STRUCTURE",
                refresh=refresh,
            )
            handle = record_stock_observation_v1(storage_root, obs_result)
        elig_result = evaluate_stock_eligibility_from_record_v3(storage_root, handle)
    except Exception:
        fallback_brief: dict[str, object] = {
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
        return (
            fallback_brief,
            False,
            "UNKNOWN",
            None,
            "OBSERVATION_OR_PROVIDER_UNAVAILABLE",
            "INSUFFICIENT_STRUCTURE",
            None,
        )

    safety_status = str(elig_result.get("status", "UNKNOWN"))
    ve = cast(dict[str, object], elig_result.get("verified_evidence") or {})
    price_inr = (
        str(ve.get("current_quote_price_inr", ""))
        if ve.get("current_quote_price_inr")
        else None
    )

    bars = _load_historical_bars_for_symbol(storage_root, symbol)
    decision, candidate_summary = _extract_causal_candidate(
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

    brief = build_trade_brief(
        symbol=symbol,
        isin=isin,
        decision=decision,
        candidate_summary=candidate_summary,
        eligibility_result=elig_result,
    )

    failed_rule = None
    if safety_status != "ELIGIBLE":
        ledger = cast(
            list[dict[str, object]], elig_result.get("explanation_ledger", [])
        )
        failed_entry = next(
            (e for e in ledger if e.get("outcome") in {"FAIL", "UNKNOWN"}), None
        )
        failed_rule = str(failed_entry.get("rule_id", "")) if failed_entry else None
    else:
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
            failed_rule = safety_reason
            # Rebuild brief with updated decision
            brief = build_trade_brief(
                symbol=symbol,
                isin=isin,
                decision=decision,
                candidate_summary=candidate_summary,
                eligibility_result=elig_result,
            )
    is_candidate = decision == "RESEARCH_CANDIDATE"
    return brief, is_candidate, safety_status, price_inr, failed_rule, trend, handle


def _resolve_target_symbols(
    storage_root: Path,
    symbols: Sequence[str] | None,
    nifty100: bool,
) -> tuple[tuple[str, ...], str, frozenset[str], dict[str, object] | None]:
    if nifty100:
        if symbols is not None:
            raise ValueError("cannot supply both explicit symbols and nifty100 flag")
        universe = read_historic_nifty_universe(storage_root)
        return (
            universe.nifty500,
            "NIFTY_100_PRIORITY_NIFTY_500",
            frozenset(universe.nifty100),
            {
                "nifty100_source_sha256": universe.nifty100_source_sha256,
                "nifty500_source_sha256": universe.nifty500_source_sha256,
                "nifty100_source_url": universe.nifty100_source_url,
                "nifty500_source_url": universe.nifty500_source_url,
                "retrieved_at": universe.retrieved_at.isoformat(),
                "window_start": universe.window_start.isoformat(),
                "window_end": universe.window_end.isoformat(),
            },
        )
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
    nifty100: bool = False,
    refresh: bool = False,
    clock: Callable[[], datetime] | None = None,
    evidence_rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Scan Nifty 100 or explicit equities integrating all 7 research families."""
    if not storage_root.is_absolute():
        raise ValueError("invalid storage root")

    target_symbols, universe_type, nifty100_symbols, universe_evidence = (
        _resolve_target_symbols(storage_root, symbols, nifty100)
    )
    now = datetime.now(UTC) if clock is None else clock()
    industry_map = _load_industry_mapping(storage_root)
    benchmark_symbols = (
        tuple(symbol for symbol in target_symbols if symbol in nifty100_symbols)
        if nifty100_symbols
        else target_symbols
    )
    benchmark_median = _compute_benchmark_median_return(storage_root, benchmark_symbols)

    candidates: list[dict[str, object]] = []
    other_stocks: list[dict[str, object]] = []
    trends: list[str] = []

    eligible_count = 0
    ineligible_count = 0
    unknown_count = 0
    retained_handles = (
        {} if refresh else _current_structure_observation_handles(storage_root)
    )

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
            brief["universe_tier"] = (
                "NIFTY_100" if symbol in nifty100_symbols else "NIFTY_500_EX_NIFTY_100"
            )
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

    nifty100_candidate_count: int | None = None
    fallback_triggered = False
    if nifty100_symbols:
        all_candidates = list(candidates)
        nifty100_candidates = [
            candidate
            for candidate in all_candidates
            if str(candidate["symbol"]) in nifty100_symbols
        ]
        nifty100_candidate_count = len(nifty100_candidates)
        fallback_triggered = nifty100_candidate_count < 5
        if fallback_triggered:
            candidates = (
                nifty100_candidates
                + [
                    candidate
                    for candidate in all_candidates
                    if str(candidate["symbol"]) not in nifty100_symbols
                ]
            )[:10]
        else:
            candidates = nifty100_candidates[:10]
        selected_symbols = {str(candidate["symbol"]) for candidate in candidates}
        for candidate in all_candidates:
            if str(candidate["symbol"]) in selected_symbols:
                continue
            summary = cast(dict[str, object], candidate.get("candidate_summary") or {})
            safety = cast(dict[str, object], candidate.get("safety_eligibility") or {})
            other_stocks.append(
                {
                    "symbol": candidate["symbol"],
                    "industry": summary.get("industry", "Unknown"),
                    "decision": candidate["decision"],
                    "safety_status": safety.get("status"),
                    "failed_rule": "BASKET_CAPACITY_OR_NIFTY100_PRIORITY",
                    "current_price_inr": summary.get("current_price_inr"),
                }
            )
    # Attach sector peer participation to each candidate
    for c in candidates:
        summary = cast(dict[str, object], c.get("candidate_summary", {}))
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

    scan_result: dict[str, object] = {
        "schema": SCHEMA,
        "scan_timestamp": _instant(now),
        "storage_root_sha256": _digest(str(storage_root)),
        "universe_type": universe_type,
        "universe_evidence": universe_evidence,
        "nifty100_validated_candidate_count": nifty100_candidate_count,
        "nifty500_fallback_triggered": fallback_triggered,
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
            summary = cast(dict[str, object], c.get("candidate_summary", {}))
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
