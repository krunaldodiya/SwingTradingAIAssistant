# Automated Nifty 100 Scan & AI Assistant Briefing Workflow

The `signal-decisions scan` command provides a unified, 1-click scanning and research briefing workflow for human CLI analysts and external AI agent harnesses. It combines:
1. Automated **24/7 safety eligibility** screening (8 conservative rules).
2. Canonical **retained-observation pair policy** candidate evaluation: each symbol's exact previous/current `CURRENT_STRUCTURE` observation pair is evaluated by the Plan 70 policy; the scanner never invents a pair or a scanner-local causal candidate.
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
* `--refresh`: Admit a new `CURRENT_STRUCTURE` observation for each symbol so the retained pair state can advance. Without it, an existing state is replayed (or a retained observation bootstraps the first seed); a scan never pairs stale data or invents a new predecessor.


### D. Retain exact decision evidence for later qualification

Use `--retain-decision-evidence` when a scan must be retained as an immutable
private input to later historical or AI qualification:

```bash
doppler run -- signal-decisions scan \
  --storage-root /absolute/path/to/SwingTradingAIAssistantData \
  --symbol INFY \
  --retain-decision-evidence \
  --output json
```

The response is a `scan-decision-evidence-envelope@v1` containing the unchanged
`swing-trade-scan@v1` result and a `decision_evidence_handle`. Read that exact
record later without a provider call:

```bash
signal-decisions read-decision-evidence \
  --storage-root /absolute/path/to/SwingTradingAIAssistantData \
  --decision-evidence HANDLE \
  --output json
```

The readback rejects altered, missing, substituted, or incompatible retained
observations. It is evidence retention only—not historical replay, an AI-model
evaluation, a performance/profit claim, execution-cost evidence, or trading advice.

Aggregate the retained evidence into the reachable G09 measurement:

```bash
signal-decisions measure-decision-evidence \
  --storage-root /absolute/path/to/SwingTradingAIAssistantData \
  --output json
```

Optional `--split-at <instant>` partitions retained scans into earlier/later
subsets with an explicit no-future-leakage guard; optional
`--execution-convention` records the caller-named execution assumption. The
report measures the mandatory policy independently from optional context,
performs no AI evaluation, and always lists the external prerequisites that
remain hard final-qualification gates (per-decision-date historical backfill,
out-of-sample/walk-forward evidence, an approved execution cost/slippage
convention, named AI model/source with immutable prompt/output provenance, and
return/profitability evidence). It never simulates or invents those results.

### E. Retained pair state and daily progression

The scanner persists at most one admitted pair transition per symbol under the
private `scanner-pair-state-v1/` namespace:

1. The first admitted observation seeds the state and the symbol is reported as
   an explicit non-candidate (`INSUFFICIENT_OBSERVATION_PAIR`); no predecessor is
   fabricated.
2. A later distinct admitted observation forms the exact previous/current pair,
   is evaluated by the canonical policy, and only then advances the state.
3. Re-scanning the same admitted observation replays the canonical policy result
   (`CAUSAL_REPLAY_HAS_NO_NEW_CONFIRMATION`) instead of recreating a candidate.

Malformed, foreign, race-conflicted, or runtime-mismatched state fails closed as
`OBSERVATION_PAIR_STATE_UNAVAILABLE` with an `UNKNOWN`/`UNKNOWN` row, and every
requested symbol still appears exactly once in `candidates` or `other_stocks`.

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

---

## 6. Portfolio Discovery Protocol: Two-Tier 5–10 Stock Basket Hierarchy

The AI assistant and CLI operator must adhere to the following canonical portfolio rules:

1. **Target Portfolio Size:** The swing trading basket contains between **5 to 10 stocks**.
2. **Priority #1 — Nifty 100 Large Caps:** The basket first admits every validated
   Nifty 100 candidate, up to all 10 basket slots.
3. **One-Pass Current Nifty 500 Scan:** The scanner evaluates each current official
   Nifty 500 member once, tags the Nifty 100 subset, and never repeats provider or
   data work for that subset.
4. **Tier 2 Basket Fill (Nifty 500 Ex-Nifty 100):** Only when fewer than five
   validated Nifty 100 candidates exist, validated Nifty 500-only candidates fill
   the remaining slots toward the 5–10 target. They never displace a validated
   Nifty 100 candidate.

---

## 7. Anti-Manipulation & Asset Quality Filter Stage

To prevent capital risk from operator pump-and-dump schemes, newly listed volatility, and illiquid small-caps, every candidate must clear this dedicated filter before admission:

| Anti-Manipulation Gate | Policy Threshold | Reason for Rejection |
|---|---|---|
| **Newly Listed Stocks (IPOs)** | History $\ge 120$ trading sessions ($\ge 6$ months) | Rejects untested IPOs with anchor lock-in risk (`NEWLY_LISTED_EXCLUDED`). |
| **Penny / Low-Priced Stocks** | Price $\ge \text{INR } 50.00$ | Rejects sub-50 operator-dominated penny stocks (`PENNY_STOCK_EXCLUDED`). |
| **Illiquid Small-Caps** | 20-day Median Turnover $\ge \text{INR } 25.0\text{ Crore / day}$ | Rejects thinly traded small-caps prone to syndicates (`ILLIQUID_SMALLCAP_EXCLUDED`). |
| **Circuit Band Buffer** | Distance to Upper/Lower Circuit $\ge 2.0\%$ | Rejects circuit-locked stocks where exits are trapped (`CIRCUIT_PROXIMITY`). |
