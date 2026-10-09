# Supported Signal Decisions Workflow

## Overview

Sprint 52 delivers Group 2: Supported Signal Decisions under Plan 65, establishing:
1. **Stock Eligibility and Safety Gates (G03)**: Objective capability-specific
   validation ensuring only qualified stocks are evaluated for swing trading.
2. **Setup-to-Signal Decision Rules (G04)**: Deterministic policy translating
   candidate setup evidence and stock eligibility into actionable swing trade signals
   (`ACTIONABLE` / `SWING_LONG_CANDIDATE`) or explicit reason-bound `NO_TRADE` outcomes.
3. **Analytical Family Disposition (G07)**: Explicit reuse of Market Structure,
   Price Action, Volume, RS, and Event families, with external company fundamentals
   excluded.

## CLI Usage

### Check Stock Eligibility (G03)

```bash
signal-decisions check-eligibility --symbol RELIANCE --input-json input.json --output json
```

Input JSON schema:
```json
{
  "series": "EQ",
  "exchange": "NSE",
  "isin": "INE002A01018",
  "bars": [
    {
      "date": "2026-08-01",
      "open": 2800.0,
      "high": 2850.0,
      "low": 2790.0,
      "close": 2840.0,
      "volume": 150000.0
    }
  ],
  "event_notices": []
}
```

`bars` must contain at least 21 completed sessions in strictly increasing
`YYYY-MM-DD` order. Every OHLCV value must be finite; prices must be positive;
and a zero-volume session refuses eligibility. The 21-session and INR 10.0
minimum-close thresholds are fixed by Plan 65. The CLI does not accept caller
threshold overrides.

`event_notices` is required. Pass an admitted current event-risk snapshot for
the same symbol: `[]` records a verified snapshot with no notices, while every
non-empty snapshot is treated conservatively as event risk and yields
`EVENT_RISK_DETECTED`. A missing, `null`, or malformed snapshot yields
`UNKNOWN` with `EVENT_RISK_UNVERIFIED`, which also forbids an actionable
signal. This evaluator does not fetch, classify, or authenticate events; source
admission remains the existing Event Context boundary and its later workflow
qualification.

The input object has no optional fields. Unknown fields are rejected, including
`minimum_sessions` and `minimum_close_price`.

Exit codes:
- `0`: Stock is `ELIGIBLE` across all six gates.
- `1`: Stock is `INELIGIBLE` or `UNKNOWN` (with specific refusal codes in JSON output).
- `2`: Invalid arguments or input error.

### Evaluate Setup-to-Signal Decision (G04)

```bash
signal-decisions evaluate --symbol RELIANCE --input-json decision_input.json --output json
```

Input JSON schema:
```json
{
  "eligibility": { ... },
  "setup_match": "MATCH",
  "invalidation_status": "NO_CONTRADICTION_OBSERVED",
  "level_relation": "ABOVE",
  "level_range_inclusion": "EARLIEST_RANGE_INCLUDED",
  "broken_high": 2750.0,
  "confirmed_hl": 2650.0,
  "latest_close": 2800.0,
  "candidate_age_sessions": 3,
  "known_at": "2026-08-21T10:00:00.000000Z"
}
```

The five decision-state fields are required and accept only the enum values
defined in Plan 65. `broken_high`, `confirmed_hl`, `latest_close`, and
`candidate_age_sessions` are optional only for `NO_TRADE` results. An
`ACTIONABLE` result requires all four plus canonical UTC `known_at`
(`YYYY-MM-DDTHH:MM:SS.ffffffZ`), a causal stop below the broken high, and
includes that known time with `target_reference` and
`target_reference_kind: "BROKEN_HIGH_DESCRIPTIVE_LEVEL"`. That reference is a
descriptive structural level; it does not claim a price target or reward
multiple.

The eligibility object must be the exact `stock-eligibility@v1` result for the
same symbol with its matching canonical SHA-256 digest. This catches changes
after generation but does not authenticate a data provider: digest checking is
an integrity binding, while provider/source qualification remains outside this
deterministic evaluator.

The decision input rejects unknown fields. If price is `BELOW` the broken high,
an `UNKNOWN` range inclusion yields `NO_TRADE`; an actionable result requires
price `ABOVE`/`AT` or `EARLIEST_RANGE_INCLUDED`.

## Analytical Family Disposition (G07)

The decision evaluator consumes admitted facts and does not acquire, rank, or
reinterpret any analytical source. Its inputs retain these upstream boundaries:

| Family | G03/G04 disposition |
| --- | --- |
| Market Structure | Reuse `setup_match`, invalidation, broken-high, confirmed-higher-low, and candidate-age facts. |
| Price Action | Reuse level relation, range inclusion, and latest completed close facts. |
| Volume | Reuse existing volume evidence upstream; this component applies only the Plan 65 positive-volume sanity gate and makes no execution-liquidity or ranking claim. |
| Relative Strength | Remains admitted descriptive context upstream; G03/G04 adds no RS ranking, threshold, or source. |
| Event Context | Reuse the admitted event snapshot supplied to `event_notices`; G03/G04 neither fetches nor classifies notices. |
| Company fundamentals and other providers | Excluded. No external fundamental feed, provider, network access, or broker interaction is introduced. |

`known_at` records the time asserted by the admitted decision facts. It is
canonicalized and carried into an actionable result, but it does not authenticate
an upstream provider or turn a current snapshot into historical evidence.

Exit codes:
- `0`: Decision is `ACTIONABLE` (`BUY_SETUP_CONFIRMED`).
- `1`: Decision is `NO_TRADE` (with explicit reason code, e.g. `STOCK_INELIGIBLE`, `SETUP_INVALIDATED`, `PRICE_BELOW_BROKEN_LEVEL`).
- `2`: Invalid arguments or input error.
