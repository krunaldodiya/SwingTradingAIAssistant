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

Exit codes:
- `0`: Stock is `ELIGIBLE` across all six gates.
- `1`: Stock is `INELIGIBLE` (with specific failure codes in JSON output).
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
  "candidate_age_sessions": 3
}
```

Exit codes:
- `0`: Decision is `ACTIONABLE` (`BUY_SETUP_CONFIRMED`).
- `1`: Decision is `NO_TRADE` (with explicit reason code, e.g. `STOCK_INELIGIBLE`, `SETUP_INVALIDATED`, `PRICE_BELOW_BROKEN_LEVEL`).
- `2`: Invalid arguments or input error.
