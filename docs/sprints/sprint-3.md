# Sprint 3 — Usable single-symbol downloader preview

Status: **PLANNING CANDIDATE — NO IMPLEMENTATION STARTED**

## Sprint goal

Deliver an installable, persistent, end-to-end downloader preview that lets a
non-developer use the public CLI to download one supported `NSE_EQ` symbol
(initially RELIANCE) into an explicit storage root, inspect verified coverage,
repeat the same range without an unnecessary provider request, and query both
canonical one-minute candles and locally derived daily OHLCV.

This is the smallest coherent user-usable vertical slice. It is not the final
Nifty 50 downloader v1 release: point-in-time multi-symbol scaling, accepted
benchmark thresholds, and the separately authorized live-release gate remain
explicit later work.

## Timebox, capacity, and WIP

- Planned execution timebox: **2026-08-10 through 2026-08-16**
  (`Asia/Kolkata`), one week.
- Implementation WIP: one executable Task. Planning and backlog refinement do
  not authorize parallel implementation.
- Committed denominator: **8 executable Tasks** carrying the `Sprint 3` and
  `Task` labels. Duplicate ARK-120/121 records are excluded.
- Capacity basis: Sprint 2 delivered 21/24 tasks, but ARK-92 demonstrated that
  large evidence surfaces and repeated full gates can dominate elapsed time.
  Sprint 3 therefore commits to one user-visible path, uses smoke-first checks,
  and does not bundle multi-instrument scaling or the benchmark redesign.
- Prospective ranges below are elapsed wall-clock planning ranges, not labor
  hours or Linear-point conversions. Before each Task starts, its current range
  and assumptions must be recorded in Linear.

| Order | ID | Atomic outcome | Prospective wall-clock range |
| --- | --- | --- | --- |
| 1 | ARK-112 | approved public download, coverage, and query contract | 45--90 minutes |
| 2 | ARK-113 | authoritative point-in-time NSE session input | 2--4 hours |
| 3 | ARK-114 | versioned single-symbol application facade | 2--4 hours |
| 4 | ARK-115 | persistent `market-data download` CLI | 1.5--3 hours |
| 5 | ARK-116 | stored coverage and bounded direct-Parquet query interfaces | 2--4 hours |
| 6 | ARK-117 | approved daily OHLCV derivation contract | 45--90 minutes |
| 7 | ARK-118 | zero-provider daily OHLCV query implementation | 2--4 hours |
| 8 | ARK-119 | clean-install single-symbol quickstart proof | 1.5--3 hours |

The sequential planning envelope is approximately **12.5--25 hours** before an
unplanned reviewer repair, provider wait, or environment outage. Reaching an
item's upper bound triggers the workflow's concise overrun checkpoint and
value-aware hold decision; it does not authorize weaker evidence or repeated
unchanged gates.

## Dependency order

```text
ARK-112 -> ARK-113 -> ARK-114 -> ARK-115
                         |          |
                         v          v
                       ARK-116 -> ARK-117 -> ARK-118
                         |                       |
                         +----------+------------+
                                    v
                                  ARK-119
```

Linear blocker relations are authoritative. This ordering prioritizes a
persistent public download command before optional polish while preserving the
schedule and storage safety boundaries.

## User-visible acceptance

The exact approved specification may refine argument names, but the completed
preview must support the following bounded workflow with real ISO dates and an
explicit storage root outside the repository:

```bash
uv run market-data download \
  --segment NSE_EQ \
  --symbol RELIANCE \
  --from 2026-07-01 \
  --to 2026-07-31 \
  --storage-root /absolute/path/to/market-data

uv run market-data coverage \
  --segment NSE_EQ \
  --symbol RELIANCE \
  --from 2026-07-01 \
  --to 2026-07-31 \
  --storage-root /absolute/path/to/market-data

uv run market-data query \
  --segment NSE_EQ \
  --symbol RELIANCE \
  --from 2026-07-03 \
  --to 2026-07-03 \
  --timeframe 1d \
  --storage-root /absolute/path/to/market-data
```

Completion requires:

- canonical provider acquisition at one-minute granularity;
- immutable monthly Parquet plus metadata-only DuckDB catalog ownership under
  the caller-selected storage root;
- an authoritative, immutable, point-in-time NSE session schedule with source,
  as-of/release time, timezone, closures, covered range, and digest retained
  before provider or storage mutation;
- verified coverage, bounded selected-field query output, and typed
  missing/stale/corrupt/insufficient outcomes;
- repeated verified ranges making zero historical provider requests;
- daily OHLCV derived locally from verified one-minute data with zero provider
  requests and explicit incomplete-session handling;
- credentials supplied outside the repository, sanitized diagnostics, no
  committed private market data, and a clean-install quickstart; and
- task-appropriate TDD/review/gates plus hosted CI on each accepted code change.

If no authoritative calendar source is ready, the smallest acceptable Sprint 3
fallback is a caller-supplied, immutable, validated schedule artifact with full
provenance. Inferring weekdays or silently treating exchange holidays as open is
not acceptable.

## Definition of Ready

A committed Task may start only when:

- all Linear blockers are Done and the Task remains inside this sprint goal;
- an approved specification or predecessor contract freezes its typed inputs,
  outputs, edge cases, stop conditions, and observable completion predicate;
- the prospective wall-clock range and assumptions are recorded before
  `In Progress`;
- credentials, live-provider authority, calendar evidence, and disposable
  storage requirements are explicit; and
- its smallest smoke test and final risk-tier evidence are known.

`Todo` is the team's operational Ready state. Only one Task may be
`In Progress`.

## Definition of Done

A Task is Done only when its exact completion predicate is met, focused smoke
and affected tests are green, the risk-tier-required sealed-revision gate and
independent review pass, hosted security/quality checks pass, the exact accepted
revision is merged, documentation matches user behavior, and Linear is
synchronized. A blocked, simulated, or partially demonstrated row remains
incomplete.

## Carryover and hold decisions

- **ARK-111, ARK-92, and ARK-93: hold in Backlog.** Their benchmark-persistence
  chain remains required before a performance-threshold or final release claim,
  but it does not block the everyday single-symbol download/query preview. This
  applies the value-aware hold policy after ARK-92 consumed disproportionate
  time. The work is deferred, not canceled or accepted.
- **ARK-69: Backlog pending fresh owner authority.** It remains the one bounded
  authenticated closed-range live validation. Sprint 3 may not execute it or
  reuse credentials without explicit authorization immediately before the
  attempt. Without ARK-69, ARK-119 may prove an offline/installable preview but
  cannot claim live release readiness.
- **ARK-12 multi-instrument scaling: deferred.** Prepare atomic children during
  backlog refinement only after the committed preview is stable; do not add
  them to Sprint 3 silently.
- **ARK-13 final Nifty 50 downloader v1 release: deferred.** It requires the
  multi-instrument, benchmark/threshold, live-provider, packaging, and release
  gates that this sprint deliberately does not claim.

If a held item later becomes the highest-value unblocked work, it may be
replanned through an explicit scope exchange. No item is skipped, marked Done,
or removed from its historical Sprint 2 record.

## Explicit exclusions

- full point-in-time Nifty 50 multi-symbol scheduling or bounded concurrency;
- weekly/monthly aggregation, indicators, signals, scoring, backtesting, market
  regime research, recommendations, or AI reasoning;
- F&O, intraday trading, portfolio/account linking, broker order placement, or
  autonomous execution;
- credential persistence, TOTP/login automation, committed market data, or
  arbitrary SQL; and
- calling the preview the final Downloader v1 release while any required
  release gate is incomplete.

## Sprint review outcome

At review, demonstrate the exact clean-install workflow, the external storage
layout, verified coverage, zero-request resume, one-minute query, and local daily
OHLCV. Report the executable completion count out of 8, every held or blocked
row, and whether the preview is usable. Do not translate preview usability into
multi-symbol, performance-threshold, live-release, strategy, or trading
approval.
