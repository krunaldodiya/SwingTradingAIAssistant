"""Automated Nifty 100 and explicit stock-list swing trade candidate scanning."""

from __future__ import annotations

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
                if isinstance(raw_obj, list) and len(raw_obj) == 100:
                    raw_list = cast(list[object], raw_obj)
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


def _build_candidate_summary(
    latest_up: object,
    age: int,
    stop_price: Decimal,
    current_price: Decimal,
) -> dict[str, object]:
    event_kind = str(getattr(latest_up, "event", "BOS"))
    event_session = _format_event_session(getattr(latest_up, "session", None))
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
    return {
        "current_price_inr": _decimal_text(current_price),
        "setup_event": event_kind,
        "setup_direction": "UP",
        "event_session": event_session,
        "age_completed_sessions": age,
        "broken_high_level_inr": _decimal_text(broken_level),
        "supporting_stop_reference_inr": _decimal_text(stop_price),
        "risk_per_share_inr": _decimal_text(risk_per_share),
        "invalidation_condition": "Daily close strictly below supporting stop reference",
        "smc_price_action": {
            "retest_state": retest_state,
            "breakout_distance_percent": f"{dist_pct:+.2f}%",
            "demand_zone_support_inr": _decimal_text(stop_price),
            "demand_zone_width_inr": _decimal_text(demand_zone_width),
        },
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
        latest_up, age, stop_price, current_price
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
        retest = str(smc.get("retest_state", ""))
        dist = str(smc.get("breakout_distance_percent", ""))
        allowed_claims = [
            f"State confirmed {candidate_summary['setup_event']} setup at broken level INR {candidate_summary['broken_high_level_inr']} confirmed on {candidate_summary['event_session']}.",
            f"State current quote price is INR {candidate_summary['current_price_inr']}.",
            f"State structural protective stop reference is INR {candidate_summary['supporting_stop_reference_inr']}.",
            f"State risk per share is INR {candidate_summary['risk_per_share_inr']}.",
            f"State candidate age is {candidate_summary['age_completed_sessions']} completed session(s) (within the 1–5 freshness window).",
            f"State breakout price action status is {retest} ({dist} relative to breakout level).",
            f"State institutional demand zone support is INR {candidate_summary['supporting_stop_reference_inr']} with zone width INR {smc.get('demand_zone_width_inr')}.",
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


def _find_retained_observation(
    storage_root: Path, symbol: str, question: str
) -> tuple[str, object] | None:
    obs_dir = storage_root / "stock-observations-v1"
    if not obs_dir.exists():
        return None
    for p in obs_dir.glob("*.json"):
        if len(p.stem) == 64:
            try:
                data: dict[str, object] = cast(
                    dict[str, object], json.loads(p.read_text())
                )
                res = cast(dict[str, object], data.get("result", {}))
                if (
                    res.get("symbol") == symbol
                    and res.get("question") == question
                    and res.get("status") == "READY"
                ):
                    obs = read_stock_observation_v1(storage_root, p.stem)
                    return p.stem, obs
            except (OSError, ValueError):
                continue
    return None


def _scan_stock(
    symbol: str,
    storage_root: Path,
    refresh: bool,
) -> tuple[dict[str, object], bool, str, str | None, str | None]:
    """Execute single-stock structure observation, safety eligibility, and brief generation."""
    try:
        retained = (
            None
            if refresh
            else _find_retained_observation(storage_root, symbol, "CURRENT_STRUCTURE")
        )
        if retained is not None:
            handle, obs_result = retained
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
        )

    safety_status = str(elig_result.get("status", "UNKNOWN"))
    ve = cast(dict[str, object], elig_result.get("verified_evidence") or {})
    price_inr = (
        str(ve.get("current_quote_price_inr", ""))
        if ve.get("current_quote_price_inr")
        else None
    )

    decision, candidate_summary = _extract_causal_candidate(obs_result, elig_result)

    isin = ""
    packet = getattr(obs_result, "packet", None)
    if packet:
        members = getattr(packet, "members", ())
        if members:
            inst = getattr(members[0], "member", None)
            if inst:
                isin = str(getattr(inst, "isin", ""))

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

    is_candidate = decision == "RESEARCH_CANDIDATE"
    return brief, is_candidate, safety_status, price_inr, failed_rule


def _resolve_target_symbols(
    storage_root: Path,
    symbols: Sequence[str] | None,
    nifty100: bool,
) -> tuple[tuple[str, ...], str]:
    if nifty100:
        if symbols is not None:
            raise ValueError("cannot supply both explicit symbols and nifty100 flag")
        return resolve_nifty100_symbols(storage_root), "NIFTY_100"
    if not symbols or not 1 <= len(symbols) <= 100:
        raise ValueError("must supply 1 to 100 valid symbols")
    for sym in symbols:
        if _SYMBOL.fullmatch(sym) is None:
            raise ValueError(f"invalid symbol: {sym}")
    return tuple(symbols), "EXPLICIT"


def scan_signal_decisions_v3(
    storage_root: Path,
    *,
    symbols: Sequence[str] | None = None,
    nifty100: bool = False,
    refresh: bool = False,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Scan Nifty 100 or an explicit equity list and return structured candidate briefings."""
    if not isinstance(storage_root, Path) or not storage_root.is_absolute():
        raise ValueError("invalid storage root")

    target_symbols, universe_type = _resolve_target_symbols(
        storage_root, symbols, nifty100
    )
    now = datetime.now(UTC) if clock is None else clock()
    candidates: list[dict[str, object]] = []
    other_stocks: list[dict[str, object]] = []

    eligible_count = 0
    ineligible_count = 0
    unknown_count = 0

    for symbol in target_symbols:
        brief, is_cand, safety_status, price_inr, failed_rule = _scan_stock(
            symbol, storage_root, refresh
        )
        if safety_status == "ELIGIBLE":
            eligible_count += 1
        elif safety_status == "INELIGIBLE":
            ineligible_count += 1
        else:
            unknown_count += 1

        if is_cand:
            candidates.append(brief)
        else:
            other_stocks.append(
                {
                    "symbol": symbol,
                    "decision": brief["decision"],
                    "safety_status": safety_status,
                    "failed_rule": failed_rule,
                    "current_price_inr": price_inr,
                }
            )

    scan_result: dict[str, object] = {
        "schema": SCHEMA,
        "scan_timestamp": _instant(now),
        "storage_root_sha256": _digest(str(storage_root)),
        "universe_type": universe_type,
        "total_stocks_scanned": len(target_symbols),
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
    """Render terminal-friendly ASCII summary and candidate tables from scan results."""
    total = scan_result.get("total_stocks_scanned", 0)
    cand_count = scan_result.get("candidate_count", 0)
    elig_count = scan_result.get("eligible_count", 0)
    inelig_count = scan_result.get("ineligible_count", 0)
    unk_count = scan_result.get("unknown_count", 0)
    u_type = scan_result.get("universe_type", "")
    ts = scan_result.get("scan_timestamp", "")

    lines: list[str] = [
        "=" * 80,
        f"SWING TRADING CANDIDATE SCAN — {u_type} ({ts})",
        "=" * 80,
        f"Scanned: {total} | Candidates: {cand_count} | Eligible: {elig_count} | Ineligible: {inelig_count} | Unknown: {unk_count}",
        "-" * 80,
    ]

    candidates = cast(list[dict[str, object]], scan_result.get("candidates", []))
    if candidates:
        lines.append("CONFIRMED RESEARCH CANDIDATES:")
        lines.append(
            f"{'SYMBOL':<10} {'PRICE':<10} {'SETUP':<8} {'DATE':<12} {'BROKEN HIGH':<12} {'STOP REF':<10} {'RISK/SH':<10} {'SMC RETEST':<16}"
        )
        lines.append("-" * 96)
        for c in candidates:
            sym = str(c.get("symbol", ""))
            summary = cast(dict[str, object], c.get("candidate_summary", {}))
            smc = cast(dict[str, object], summary.get("smc_price_action", {}))
            price = f"INR {summary.get('current_price_inr', '')}"
            setup = (
                f"{summary.get('setup_direction', '')} {summary.get('setup_event', '')}"
            )
            date_str = str(summary.get("event_session", ""))
            broken = f"INR {summary.get('broken_high_level_inr', '')}"
            stop = f"INR {summary.get('supporting_stop_reference_inr', '')}"
            risk = f"INR {summary.get('risk_per_share_inr', '')}"
            smc_retest = f"{smc.get('retest_state', '')} ({smc.get('breakout_distance_percent', '')})"
            lines.append(
                f"{sym:<10} {price:<10} {setup:<8} {date_str:<12} {broken:<12} {stop:<10} {risk:<10} {smc_retest:<16}"
            )
        lines.append("-" * 96)
    else:
        lines.append(
            "CONFIRMED RESEARCH CANDIDATES: None (No 1–5 session upward BOS setups active)"
        )
        lines.append("-" * 80)

    other = cast(list[dict[str, object]], scan_result.get("other_stocks", []))
    ineligible = [o for o in other if o.get("safety_status") == "INELIGIBLE"]
    if ineligible:
        lines.append(f"FILTERED BY SAFETY POLICY ({len(ineligible)} stocks):")
        lines.extend(
            [
                f"  - {o.get('symbol')}: {o.get('failed_rule', 'FAIL')} (Price: INR {o.get('current_price_inr')})"
                for o in ineligible
            ]
        )
        lines.append("-" * 80)

    return "\n".join(lines)
