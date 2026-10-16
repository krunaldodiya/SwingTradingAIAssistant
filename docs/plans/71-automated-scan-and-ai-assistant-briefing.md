# Plan 71: automated Nifty 100 scan and AI assistant briefing

Status: accepted bounded specification under [Issue #309](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/309), Milestone 48. Owner and risk owner: Krunal Dodiya. Risk tier: R3 financial-research policy, provider provenance, and public AI decision contracts. Base: `797f6e0`.

## Outcome and consumer

A human CLI user and an external AI agent harness can invoke one versioned command to scan the default Nifty 100 universe or an explicit stock list, screen 24/7 safety eligibility, evaluate causal Break-of-Structure candidate status, and receive structured, prompt-ready trade briefing cards with deterministic explanation ledgers:

- `signal-decisions scan --storage-root ROOT --nifty100 [--output json|table]`
- `signal-decisions scan --storage-root ROOT --symbol SYM [--symbol SYM ...] [--output json|table]`

Every result contains:
1. An index-wide or cohort-wide summary of eligible, ineligible, candidate, and unknown stocks.
2. Individual structured trade briefing cards (`swing-trade-brief@v1`) for every evaluated stock.
3. Plain-language explanation ledgers from the underlying 8-rule safety policy and causal candidate policy.
4. A deterministic contract for external AI assistants (ChatGPT, Claude, local harnesses) to explain the trade setup without hallucinating or calculating unverified indicators.

This delivers the first working slice of Roadmap Delivery Group 3 (Outcomes G06 and G10).

## Scope and component reuse

The scan layer unifies delivered capabilities without introducing new providers, pricing models, or unverified indicator catalogues:

1. **Universe Selection:** Reuses delivered point-in-time Nifty 100 selection and explicit 1–100 equity bounds (`market_data/setup_research_selection.py`).
2. **Structure Capture:** Reuses `stock-observations observe` (`market_data/stock_observations.py`) to obtain immutable 21-bar `CURRENT_STRUCTURE` observations.
3. **24/7 Safety Screening:** Reuses `stock_eligibility_v3.py` with the 24/7 market hours and closed-market support delivered in PR #308.
4. **Causal Setup Evaluation:** Automatically resolves or pairs observations for stocks with confirmed Break of Structure events within age 1–5 sessions, evaluating validity through `signal_decisions_v3.py`.
5. **Human & AI Presentation:** Emits terminal-formatted tables (`--output table`) and canonical compact JSON (`--output json`).

No broker execution, order placement, position sizing, price-target guarantees, or external LLM API dependencies are added.

## Frozen schemas and contracts

### 1. `swing-trade-scan@v1`
The top-level scan response:
- `schema`: `"swing-trade-scan@v1"`
- `scan_timestamp`: ISO 8601 aware UTC instant
- `storage_root_sha256`: 64-hex SHA-256
- `universe_type`: `"NIFTY_100"` | `"EXPLICIT"`
- `total_stocks_scanned`: int
- `candidate_count`: int
- `eligible_count`: int
- `ineligible_count`: int
- `unknown_count`: int
- `candidates`: list of `swing-trade-brief@v1` objects
- `other_stocks`: list of abbreviated status summaries

### 2. `swing-trade-brief@v1`
Individual trade card for each candidate or evaluated stock:
- `schema`: `"swing-trade-brief@v1"`
- `symbol`: str
- `isin`: str
- `exchange`: `"NSE"`
- `decision`: `"RESEARCH_CANDIDATE"` | `"NO_TRADE"` | `"UNKNOWN"`
- `candidate_summary`: dict or null (when not a candidate):
  - `current_price_inr`: Decimal text
  - `setup_event`: `"BOS"` | `"CHOCH"`
  - `setup_direction`: `"UP"`
  - `event_session`: `"YYYY-MM-DD"`
  - `age_completed_sessions`: int (1..5)
  - `broken_high_level_inr`: Decimal text
  - `supporting_stop_reference_inr`: Decimal text
  - `risk_per_share_inr`: Decimal text (`current_price - supporting_stop_reference`)
  - `invalidation_condition`: `"Daily close strictly below supporting stop reference"`
- `safety_eligibility`:
  - `status`: `"ELIGIBLE"` | `"INELIGIBLE"` | `"UNKNOWN"`
  - `explanation_ledger`: full 8-rule ledger
- `ai_guidance`:
  - `allowed_claims`: list of deterministic facts the AI is authorized to state
  - `forbidden_claims`: list of prohibited claims (no target prices, profit claims, or broker advice)

## Adversarial matrix

| Risk or scenario | Required result/evidence |
|---|---|
| Full candidate pass | Stock with confirmed upward BOS age 1–5, price above broken high and stop, and 8 safety passes yields `RESEARCH_CANDIDATE` with complete briefing card. |
| Safety rejection | Stock failing any of the 8 safety gates (e.g. dividend blackout) yields `INELIGIBLE` and is clearly categorized in scan summary. |
| Causal rejection | Stock with age > 5, price below stop, or downtrend BOS yields `NO_TRADE` with explicit rejection rationale. |
| Incomplete data | Provider refusal or unavailable observation yields `UNKNOWN` without crashing the whole-list scan. |
| Empty / invalid cohort | Empty list or invalid symbol fails with exit code 2 and fixed diagnostic. |
| Output formats | Both `--output json` and `--output table` render identical factual outcomes. |
