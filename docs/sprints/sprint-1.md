# Sprint 1 — Resumable one-minute storage

## Sprint goal

Establish the smallest trustworthy persistent-data slice: plan RELIANCE
instrument-month work, skip already verified coverage without an Upstox candle
request, and define the canonical Parquet/DuckDB persistence boundary.

## Historical cadence and scope

- Initial cadence: one week.
- Tracking parent: ARK-10, which was not implemented directly.

## Included scope

Sprint 1 included the following ordered ARK-10 children:

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

The recorded Sprint 1 set excluded later backlog items. ARK-42 and ARK-43 were
prerequisite contract work for the persistence path, so they preceded physical
reconciliation and write steps without changing the sprint goal. ARK-44 was
canceled and superseded by the equity-only downloader-v1 boundary.

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

## Historical acceptance evidence

Executable children closed with recorded implementation and verification
evidence, manifest/provenance evidence, bounded resource behavior, and Linear
disposition. Storage, crash recovery, credentials, concurrency, and provider
retry changes also received additional verification.

## Final status

Sprint 1 closed on 2026-08-07 with **21 of 21 executable Story/Task items
complete (100%)**. Tracking parents, canceled work, and deferred work are not
part of that denominator. This is a historical Sprint 1 closure record;
subsequent sprint work is tracked independently.

The completed increment includes the canonical logical and physical candle
contracts, Upstox NSE equity normalization, calendar-month planning, physical
and manifest reconciliation, atomic Parquet publication, DuckDB catalog
evidence, protected storage ownership, retained session schedules, validated
equity-month coverage, bounded provider requests, requested-partition
lifecycle, leased local recovery, request-minimal range coordination, and the
interruption/repeated-run zero-request proof.

Closure evidence:

- PR 23 merged the final Sprint 1 integration into `main` as commit
  `314587e9dae9c1d96b180a7b254d94ef86295259`.
- PR 25 merged the Sprint 1 documentation reconciliation into `main` as commit
  `a3d2f0ccac641030f40c87076e55f5754d650b28`.
- PR 2 and PR 24 were closed unmerged as obsolete; neither is merge evidence
  for the completed Sprint 1 increment.
- The exact final candidate passed Ruff format and lint, strict Pyright,
  Vulture, and **949 tests with 87.79% branch coverage**.
- The required GitHub **Quality and build** and **GitGuardian Security Checks**
  completed successfully before merge.
- The demo and retrospective are complete.

Scope disposition at close:

- ARK-64 is deferred and excluded from the 21-item denominator. It requires
  future approved planning before work may begin.
- ARK-65 was canceled without code and is excluded from the denominator. Its
  useful schedule-completeness requirement remains inside completed ARK-58.
- ARK-44 remains canceled and replaced by the equity-only downloader-v1
  boundary.
- The broader Nifty 50 downloader/data phase is not complete. Package release,
  multi-instrument concurrency, higher-timeframe aggregation, the point-in-time
  Nifty 50 universe, and research modules remain later approved work.

## Retrospective

What worked:

- focused implementation and independent verification kept the storage and
  recovery contracts testable;
- immutable monthly evidence and request-minimal reconciliation protected the
  Upstox request budget and made interruption recovery explicit; and
- final integration preserved the equity-only architecture and restored the
  required CI/security checks.

What did not work:

- the sprint record remained on an intermediate 823-test checkpoint after the
  implementation and review work had finished;
- task and approval state was not always surfaced immediately, which caused
  avoidable idle time and repeated status checks; and
- PR 24 was opened against the already-merged integration branch instead of
  current `main`, creating an avoidable branch-base reconciliation.

Historical follow-up:

- the closure record was reconciled with its denominator, merge commit, exact
  final checks, deferred and canceled work, and retrospective;
- task-state reporting and durable checkpointing were identified as follow-up
  needs; and
- later documentation work used current `origin/main`. A proposed checkpoint
  experiment remained unproven at this retrospective.
