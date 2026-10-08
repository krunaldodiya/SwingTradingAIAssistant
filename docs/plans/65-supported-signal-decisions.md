# Plan 65: supported signal decisions and stock eligibility/safety gates

Accepted October 8, 2026 under [Issue #292](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/292),
milestone 44. Owner and risk owner: Krunal Dodiya. R3 financial-research provenance,
safety gating, and decision policy. Base: `ee61272f84afe108b4e7101a31ee4d72083e29e8` (main).

## Question and least adequate correction

How can the research tool objectively evaluate candidate stocks and causal setup
facts to decide whether a swing setup is actionable or requires NO_TRADE without
relying on unspecified external AI suggestions or arbitrary unverified rules?

Selected: two tightly coupled, deterministic components operating fail-closed:
1. **Stock Eligibility and Safety Gates (G03)**: an objective verification layer
   evaluating canonical identity, sufficient history window, OHLCV data quality,
   positive liquidity/turnover, price integrity, and corporate event risk.
2. **Setup-to-Signal Decision Policy (G04)**: a deterministic decision engine
   taking admitted candidate setup facts and G03 eligibility to produce an explicit
   disposition (`ACTIONABLE` or reason-bound `NO_TRADE`).
3. **Analytical Family Disposition (G07)**: formal confirmation that existing
   Structure, Price Action, Volume, Relative Strength, and Event Context families
   are reused; external company fundamentals and unapproved feeds remain excluded.

## G03: Stock Eligibility and Safety Contract

Schema: `stock-eligibility@v1`.

The eligibility engine evaluates candidate stocks across six objective categories
without requiring external subscriptions or subjective ranking:

| Gate | Criterion | Fail-Closed Refusal Reason |
| --- | --- | --- |
| 1. Canonical Mapping | Instrument series must be `EQ`, exchange `NSE`, valid ISIN present. | `UNSUPPORTED_MAPPING` |
| 2. History Window | At least 21 completed trading sessions in the evaluation window. | `INSUFFICIENT_HISTORY` |
| 3. Data Quality | All OHLCV bars valid (`low <= open, close <= high`; positive volume). | `DATA_QUALITY_INVALID` |
| 4. Liquidity Sanity | Average daily volume > 0 and no zero-volume halted sessions in window. | `INSUFFICIENT_LIQUIDITY` |
| 5. Price Integrity | Latest completed close >= 10.0 INR (penny stock protection). | `PRICE_INTEGRITY_FAILED` |
| 6. Event Risk | No active suspension or immediate corporate action notice in snapshot. | `EVENT_RISK_DETECTED` |

Outcomes:
- `ELIGIBLE`: all six gates passed.
- `INELIGIBLE`: one or more gates failed, with explicit failure codes list.
- `UNKNOWN`: mapping or data cannot be verified from available evidence.

Any outcome other than `ELIGIBLE` forbids actionable signal generation.

## G04: Setup-to-Signal Decision Rules

Schema: `stock-signal-decision@v1`.

Inputs:
- `eligibility`: `StockEligibilityResult`
- `setup_screen`: candidate setup result (`MATCH`, `NO_MATCH`, or `UNKNOWN` for `LATEST_COMPLETED_UPWARD_BOS@v1`)
- `invalidation`: `NO_CONTRADICTION_OBSERVED`, `INVALIDATED`, or `UNKNOWN`
- `level_relation`: `ABOVE`, `AT`, `BELOW`, or `UNKNOWN` (close vs broken high)
- `inclusion`: `EARLIEST_RANGE_INCLUDED`, `NO_INCLUSION`, or `UNKNOWN`
- `broken_high`: price level of broken structure high
- `confirmed_hl`: price level of confirmed higher low before BOS
- `candidate_age`: completed session count

Decision Precedence:
1. **Safety/Eligibility Check**: If stock is not `ELIGIBLE`, return `NO_TRADE` with reason `STOCK_INELIGIBLE` and embedded eligibility failures.
2. **Invalidation Check**: If invalidation is `INVALIDATED` (e.g. DOWN CHOCH confirmed), return `NO_TRADE` with reason `SETUP_INVALIDATED`.
3. **Setup Match Check**: If setup screen is `NO_MATCH` or `UNKNOWN`, return `NO_TRADE` with reason `NO_SETUP_MATCH` or `SETUP_UNKNOWN`.
4. **Price Position Check**: If close is `BELOW` broken high and inclusion is `NO_INCLUSION`, return `NO_TRADE` with reason `PRICE_BELOW_BROKEN_LEVEL`.
5. **Actionable Signal**: If all gates pass (stock is `ELIGIBLE`, setup is `MATCH`, invalidation is `NO_CONTRADICTION_OBSERVED`, and close is `ABOVE`/`AT` or range included):
   - Disposition: `ACTIONABLE`
   - Signal type: `SWING_LONG_CANDIDATE`
   - Stop loss reference: `confirmed_hl`
   - Entry reference: latest close
   - Target reference: broken high + risk delta (or descriptive level)
   - Age sessions: `candidate_age`

## G07: Analytical Family Disposition

- Market Structure (Plan 31): **REUSE** (BOS, CHOCH, HL, HH).
- Price Action (Plan 32): **REUSE** (ranges, closes).
- Volume Context (Plan 39): **REUSE** (relative volume baseline).
- Relative Strength (Plan 41): **REUSE** (stock reference RS).
- Event Context (Plan 25/37/38): **REUSE** (announcements).
- Company Fundamentals: **EXCLUDED** (Future #178 remains excluded).

## Boundaries and Non-Goals

- No automated order execution or broker API connection.
- No investment advice, return guarantees, or performance claims.
- All decisions are deterministic, reproducible, and explainable from admitted facts.
