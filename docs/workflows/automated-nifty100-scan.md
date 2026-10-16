# Automated Nifty 100 Scan & AI Assistant Briefing Workflow

The `signal-decisions scan` command provides a unified, 1-click scanning and research briefing workflow for human CLI analysts and external AI agent harnesses. It combines:
1. Automated **24/7 safety eligibility** screening (8 conservative rules).
2. Automated **causal Break-of-Structure (BOS/CHOCH)** candidate evaluation.
3. Prompt-ready **trade briefing cards** (`swing-trade-brief@v1`) with structural protective stop levels, risk per share, and deterministic explanation ledgers.

---

## 1. Prerequisites and Credential Injection

The tool reads required provider credentials lazily from the execution environment:
* `BHARATSTOCK_API_KEY`: For 21-day market structure bars and 252-day history.
* `UPSTOX_ACCESS_TOKEN`: For live quotes, circuit limits, and corporate action dates.

We use **Doppler** to inject credentials securely without exposing secrets on the command line or saving them to disk:

```bash
doppler run -- signal-decisions scan [OPTIONS]
```

---

## 2. Running the Scanner

### A. Scan the Full Nifty 100 Universe

```bash
doppler run -- signal-decisions scan \
  --storage-root /absolute/path/to/SwingTradingAIAssistantData \
  --nifty100 \
  --output table
```

### B. Scan an Explicit List of Stocks

```bash
doppler run -- signal-decisions scan \
  --storage-root /absolute/path/to/SwingTradingAIAssistantData \
  --symbol TECHM \
  --symbol LTM \
  --symbol PFC \
  --symbol INFY \
  --symbol TCS \
  --output table
```

### C. Output Formats

* `--output table` *(Default)*: Formatted ASCII/Unicode summary table for terminal display.
* `--output json`: Compact canonical JSON adhering to `swing-trade-scan@v1` for automated ingestion.
* `--refresh`: Optional flag to force re-acquisition of the latest daily bars from BharatStock.

---

## 3. Terminal Table Output Example

```text
================================================================================
SWING TRADING CANDIDATE SCAN — EXPLICIT (2026-10-16T09:29:57Z)
================================================================================
Scanned: 5 | Candidates: 2 | Eligible: 3 | Ineligible: 2 | Unknown: 0
--------------------------------------------------------------------------------
CONFIRMED RESEARCH CANDIDATES:
SYMBOL     PRICE      SETUP    DATE         BROKEN HIGH  STOP REF   RISK/SH   
--------------------------------------------------------------------------------
LTM        INR 4387.4 UP CHOCH 2026-10-13   INR 4183.6   INR 3905.6 INR 481.8 
PFC        INR 335.0  UP CHOCH 2026-10-12   INR 332.25   INR 313.35 INR 21.65 
--------------------------------------------------------------------------------
FILTERED BY SAFETY POLICY (2 stocks):
  - TECHM: LOW_PRICE_AND_CIRCUIT_DISTANCE (Price: INR 1779.6)
  - TCS: SUPPORTED_CORPORATE_ACTION_BLACKOUT (Price: INR 2462.1)
--------------------------------------------------------------------------------
```

---

## 4. Understanding the Trade Briefing Card (`swing-trade-brief@v1`)

When `--output json` is selected, each candidate includes a prompt-ready `swing-trade-brief@v1` payload:

```json
{
  "schema": "swing-trade-brief@v1",
  "symbol": "LTM",
  "isin": "INE214T01019",
  "exchange": "NSE",
  "decision": "RESEARCH_CANDIDATE",
  "candidate_summary": {
    "current_price_inr": "4387.4",
    "setup_event": "CHOCH",
    "setup_direction": "UP",
    "event_session": "2026-10-13",
    "age_completed_sessions": 3,
    "broken_high_level_inr": "4183.6",
    "supporting_stop_reference_inr": "3905.6",
    "risk_per_share_inr": "481.8",
    "invalidation_condition": "Daily close strictly below supporting stop reference"
  },
  "safety_eligibility": {
    "status": "ELIGIBLE",
    "explanation_ledger": [ ... 8 safety rule entries ... ]
  },
  "ai_guidance": {
    "allowed_claims": [
      "State confirmed CHOCH setup at broken level INR 4183.6 confirmed on 2026-10-13.",
      "State current quote price is INR 4387.4.",
      "State structural protective stop reference is INR 3905.6.",
      "State risk per share is INR 481.8.",
      "State candidate age is 3 completed session(s) (within the 1–5 freshness window).",
      "State all 8 conservative safety eligibility gates passed (turnover, history, circuit distance, book liquidity, and 7-day corporate action blackout)."
    ],
    "forbidden_claims": [
      "Do not predict future percentage returns or guaranteed profitability.",
      "Do not set speculative target prices, reward multipliers, or profit-taking exits.",
      "Do not issue automated broker orders, capital allocation advice, or position sizes."
    ]
  }
}
```

---

## 5. External AI Assistant Integration (Outcome G06)

To have an AI assistant (ChatGPT, Claude, or a local harness) synthesize plain-English briefings for human traders:

### Canonical Prompt Template

```text
System: You are an objective financial research assistant. Your task is to explain
the following deterministic swing trading briefing card to a human trader.
You MUST adhere strictly to the allowed claims in ai_guidance. You MUST NOT make
any of the forbidden claims (no profit promises, no target prices, no broker instructions).

Briefing Card JSON:
{PASTE_SWING_TRADE_BRIEF_JSON}
```

### Expected AI Assistant Output

> **Candidate Briefing: LTIMindtree (LTM)**
> * **Status:** Confirmed Research Candidate (`RESEARCH_CANDIDATE`)
> * **Current Price:** ₹4,387.40
> * **Setup:** Upward Change of Character (`UP CHOCH`) confirmed on October 13, 2026, breaking above the previous high level of ₹4,183.60.
> * **Setup Freshness:** 3 completed sessions elapsed (within the 1–5 session freshness window).
> * **Protective Stop Level:** ₹3,905.60 (based on the confirmed supporting swing low).
> * **Risk per Share:** ₹481.80 (distance between current price and stop level).
> * **Invalidation Condition:** A daily close strictly below ₹3,905.60 invalidates the setup.
> * **Safety Clearance:** Cleared all 8 safety screening gates: 287 completed history sessions, 20-day median turnover exceeding ₹1,000 Crore, quote within circuit limits, and zero corporate action blackout events in the next 7 days.
