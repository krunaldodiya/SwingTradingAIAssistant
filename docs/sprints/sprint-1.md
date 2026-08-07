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
steps without changing the sprint goal. ARK-44 is canceled and superseded by
the equity-only downloader-v1 boundary.

## Accepted behavioral rules

- Canonical intraday acquisition is one minute only.
- Higher intraday timeframes are derived locally; they do not cause Upstox
  historical requests.
- Verified immutable instrument-month partitions are the resume unit.
- Persistence uses one canonical full closed calendar month per physical
  identity. Historical edge ranges expand to that month; an open/current month
  is rejected before credentials or provider access until mutable live-update
  behavior is separately specified.
- `MAX(ts)` is not completeness proof.
- A skip requires agreement between manifest status, file presence, checksum,
  schema version, coverage, and quality result.
- Abandoned temporary files and in-progress manifest entries are incomplete.
- Retryable requests use bounded backoff, valid `Retry-After` guidance, and one
  shared provider-account rate limiter.
- ARK-31 schema v1 persists UTC timestamps, finite float64 price/strike/OI
  values, nonnegative OHLC and any nonnegative integer volume, and rejects
  boolean volume. The approved Linear ARK-42 physical mapping rejects volume
  above signed-int64 representability without changing ARK-31. It uses the exact
  approved Arrow field order, nullability, metadata version, and Parquet
  compatibility settings; DuckDB reads Parquet directly without a candle table.
- `ts` is the inclusive UTC bar-open for `[ts, ts + 1m)`, with zero seconds and
  microseconds; adapters verify and translate provider timestamp conventions.
  `ingested_at` is UTC-aware and need not be minute-aligned, while session
  calendar validation is outside the canonical-model constructor.
- Optional contract-identity fields remain nullable in the frozen shared schema,
  but the v1 equity adapter emits them as `None` and rejects contradictory
  non-equity metadata before catalog or provider access. This does not claim
  support for another instrument family.

## Explicitly deferred

- Higher-timeframe aggregation implementation until its NSE session-bucketing,
  partial-bucket, and adjustment-version specification is approved.
- Multi-instrument concurrency (ARK-12).
- Package/release completion work beyond this sprint, including the rebaselined
  equity-only ARK-13 milestone.
- Index, derivative, forex, crypto, and other instrument adapters; ARK-44 was
  canceled and superseded rather than deferred.
- ExpiryTrack NIFTY/India VIX migration, which is superseded as an active roadmap
  item and retained only as a reference audit.
- Market-regime, indicator, strategy, backtesting, and agent-facing features.

## Definition of Done

Each executable child requires red-green-refactor evidence, the deterministic
quality gate, independent verification, manifest/provenance evidence, bounded
resource behavior, and a concise Linear handoff. Storage, crash recovery,
credentials, concurrency, and provider retry changes additionally require Sol
high-risk review.

## Status

Planning started on 2026-08-05. ARK-31 froze the logical canonical schema and
ARK-42 implements its physical Parquet mapping. The approved Linear ARK-43
adapter maps normalized Upstox NSE equity candles into that logical contract
before ARK-34. ARK-33 and ARK-40 remain ordered implementation children for
physical reconciliation and manifest lifecycle respectively. The approved Linear
ARK-32 planner decomposes one-minute NSE equity date ranges into contiguous
calendar-month requests before physical reconciliation. The approved Linear
ARK-33 reconciliation boundary now decides deterministic `SKIP` or `REQUEST`
outcomes from supplied manifest and physical evidence before any provider
request. The approved Linear ARK-40 lifecycle now manages immutable pure
manifest transitions and retry/invalidation evidence separately. The approved
Linear ARK-34 publisher now owns atomic, no-clobber Parquet publication and
descriptor-anchored read-back evidence, without catalog mutation. Its durable
root is caller-created and all derived directories are no-follow and fsynced;
no-lock writers converge via no-clobber link and exact temporary cleanup.
ARK-44 is canceled and superseded by the equity-only downloader-v1 boundary.

The ARK-49 request-minimal ingestion contract was independently approved and
decomposed into ordered atomic children. ARK-56 now executes one requested
partition lifecycle with independently approved attempt provenance, exact
manifest recovery, sanitized hostile boundaries, request-minimal verified skip,
publication evidence, cancellation handling, and terminal catalog evidence.
Its final gate passed 823 tests at 87.37% coverage with no Upstox request during
verification. Linear remains authoritative for the remaining ordered children:
leased-partition recovery, bounded RELIANCE range coordination, and the final
interruption/zero-request proof.
