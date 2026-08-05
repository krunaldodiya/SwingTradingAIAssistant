# Sprint 1 — Resumable one-minute storage

## Sprint goal

Establish the smallest trustworthy persistent-data slice: plan RELIANCE
instrument-month work, skip already verified coverage without an Upstox candle
request, and define the canonical Parquet/DuckDB persistence boundary under
strict TDD.

## Timebox and WIP

- Initial cadence: one week.
- Implementation WIP: one executable story/task.
- Tracking parent: ARK-10, which is not implemented directly.

## Committed scope

Sprint 1 is limited to atomic children of ARK-10 that fit the timebox after
decomposition and meet the Definition of Ready. The ordered delivery path is:

1. **ARK-31:** freeze the versioned canonical candle schema and persistence
   boundary, independently of Arrow/Parquet;
2. **ARK-42:** map that frozen logical model to physical Parquet without
   changing its contract;
3. **ARK-43:** normalize provider candles into the canonical model before
   **ARK-34**;
4. plan non-overlapping calendar-month requests from a requested date range;
5. **ARK-33:** reconcile physical Parquet files and checksums before deciding
   whether a verified partition can be skipped;
6. **ARK-40:** define manifest lifecycle transitions and terminal registration;
7. write one validated monthly Parquet partition atomically and register its
   metadata in DuckDB; and
8. prove interruption recovery and a zero-candle-request repeated run.

Only Ready children explicitly labeled `Sprint 1` are sprint commitments. Later
items remain backlog rather than silently expanding the sprint. This is an
explicit scope exchange: ARK-42 and ARK-43 are prerequisite contract work for
the persistence path, so they precede the physical reconciliation and write
steps without changing the sprint goal. ARK-44 remains deferred.

## Accepted behavioral rules

- Canonical intraday acquisition is one minute only.
- Higher intraday timeframes are derived locally; they do not cause Upstox
  historical requests.
- Verified immutable instrument-month partitions are the resume unit.
- `MAX(ts)` is not completeness proof.
- A skip requires agreement between manifest status, file presence, checksum,
  schema version, coverage, and quality result.
- Abandoned temporary files and in-progress manifest entries are incomplete.
- Retryable requests use bounded backoff, valid `Retry-After` guidance, and one
  shared provider-account rate limiter.
- ARK-31 schema v1 persists UTC timestamps, finite float64 price/strike/OI
  values, nonnegative OHLC and volume constraints, and rejects boolean volume.
- `ts` is the inclusive UTC bar-open for `[ts, ts + 1m)`, with zero seconds and
  microseconds; adapters verify and translate provider timestamp conventions.
  `ingested_at` is UTC-aware and need not be minute-aligned, while session
  calendar validation is outside the canonical-model constructor.
- Shared scalar types and nullability apply only to fields coherent across
  instrument families; adapters retain family-specific interpretation. The
  RELIANCE equity adapter emits derivative fields as `None`.

## Explicitly deferred

- Higher-timeframe aggregation implementation until its NSE session-bucketing,
  partial-bucket, and adjustment-version specification is approved.
- Multi-instrument concurrency (ARK-12).
- Index and derivatives adapters (ARK-13).
- ARK-44.
- ExpiryTrack NIFTY/India VIX migration, which remains proposed.
- Market-regime, indicator, strategy, backtesting, and agent-facing features.

## Definition of Done

Each executable child requires red-green-refactor evidence, the deterministic
quality gate, independent verification, manifest/provenance evidence, bounded
resource behavior, and a concise Linear handoff. Storage, crash recovery,
credentials, concurrency, and provider retry changes additionally require Sol
high-risk review.

## Status

Planning started on 2026-08-05. ARK-31 is approved to freeze the logical
canonical schema, with ARK-42 owning its physical Parquet mapping and ARK-43
normalizing provider data before ARK-34. ARK-33 and ARK-40 remain ordered
implementation children for physical reconciliation and manifest lifecycle
respectively; ARK-44 is deferred. No production Sprint 1 implementation existed
at the start of the sprint.
