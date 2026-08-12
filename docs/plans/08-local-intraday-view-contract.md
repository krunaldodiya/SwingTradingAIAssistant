# Local Intraday View Contract

Status: implementation candidate for ARK-142.

## Purpose

Expose deterministic `3m`, `5m`, `15m`, `30m`, and `1h` OHLCV views from
the canonical raw `1m` evidence. Upstox is not called for a higher timeframe,
and no second candle copy is persisted.

## Contract

- Every bucket is anchored to the authoritative exchange-session open, never
  to midnight or the first observed candle.
- A bucket is `[start, min(start + interval, session close))`. A shorter final
  session-tail bucket is complete when every scheduled minute in that interval
  exists; this preserves the regular 15-minute close tail for `30m` and `1h`.
- Closed verified sessions require exactly one on-grid raw candle for every
  scheduled minute. Missing, duplicate, off-grid, or out-of-session evidence
  returns `INSUFFICIENT_EVIDENCE`; it never produces a partial research fact.
- A provisional current session exposes only buckets whose complete expected
  interval is at or before the persisted cutoff. The advancing bucket is
  omitted, and the month remains explicitly `PROVISIONAL` with
  `session_complete=false`.
- OHLCV is first open, maximum high, minimum low, last close, and checked
  integer volume sum. Prices remain raw; calculation version is
  `nse-session-intraday-ohlcv@v1` and adjustment state is `raw`.
- Retained schedule evidence owns regular, holiday, and special-session bounds.
  No weekday, standard-hours, or forward-fill inference is allowed.

## Bounds and failures

- At most 12 verified monthly Parquet inputs, 500,000 one-minute input rows,
  10,000 output rows, 256 MiB DuckDB memory, five seconds, and the existing
  public JSON ceiling.
- Provider attempts are always zero. Cancellation/deadline, resource overflow,
  root-authority loss, malformed contracts, or output overflow remain typed and
  fail closed.
- Weekly/monthly views, indicators, signals, persisted derived bars, provider
  higher-timeframe requests, and adjusted-price formulas are out of scope.

## Acceptance

Tests cover every supported interval, regular and special sessions, shorter
session tails, missing/duplicate/off-grid minutes, integer volume overflow,
deadline/resource mapping, selected fields, current-session cutoff behavior,
provenance, CLI routing, and provider non-use. The unchanged full gate passes
before publication.
