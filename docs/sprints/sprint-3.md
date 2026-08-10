# Sprint 3 — Usable single-symbol downloader preview

Status: **ACTIVE**

## Goal

Deliver an installable, persistent CLI preview that downloads one admitted
`NSE_EQ` symbol, initially RELIANCE, to an explicit external storage root;
proves stored coverage; repeats without an unnecessary historical request; and
queries verified one-minute and locally derived daily OHLCV.

The preview preserves the deterministic tool/AI boundary and is not the final
multi-symbol Nifty 50 downloader release. It adds no signal, score, advice,
portfolio/account connection, autonomous decision, or broker execution.

## Delivery plan

The sprint executes as seven coherent PR-sized slices. The earlier issue graph
remains historical tracking detail and does not force per-issue handoffs,
approvals, gates, or commits.

| Slice | Coherent outcome | Dependencies |
| --- | --- | --- |
| 1. Public contract | Admission, common report/serializer, snapshot provenance, catalog migration, preparation handoff | Plans 01–02 |
| 2. Authoritative preparation | Injected admission; provenance-complete NSE schedule; bounded BOD fetch; immutable snapshot store; offline resolver; schedule-first preparation | 1 |
| 3. Persistent download | Shared public conversion, download service, JSON renderer, and `market-data download` CLI | 2 |
| 4. Stored coverage | Read-only root admission, verified selection, coverage service/report, and `market-data coverage` CLI | 3 |
| 5. One-minute query | Bounded direct-Parquet query service/report and `1m` CLI adapter | 4 |
| 6. Daily query | Session-aware daily derivation contract/service and `1d` CLI adapter, with zero provider calls | 5 |
| 7. Usability proof | Clean install, disposable-root end-to-end workflow, docs, and sprint-close evidence | 6 |

The current contract is
[Plan 04](../plans/04-public-preview-contract.md). Each implementation slice
gets a short implementer-owned spec in its tests and public contract, follows
red-green-refactor, runs the fast changed-file gate during work, and runs the
unchanged five-tool full gate once before merge. Published contract/schema,
market-logic, credential-boundary, or twice-failed slices receive one
independent high-effort review; ordinary plumbing does not.

One writer owns a file path. Disjoint paths may proceed concurrently in
separate worktrees; shared contracts, schemas, migrations, and configuration
remain serialized.

## User-visible workflow

The completed preview supports closed ISO date ranges and explicit JSON output:

```bash
uv run market-data download \
  --segment NSE_EQ --symbol RELIANCE \
  --from 2026-07-01 --to 2026-07-31 \
  --storage-root /var/tmp/swing-market-data --output json

uv run market-data coverage \
  --segment NSE_EQ --symbol RELIANCE \
  --from 2026-07-01 --to 2026-07-31 \
  --storage-root /var/tmp/swing-market-data --output json

uv run market-data query \
  --segment NSE_EQ --symbol RELIANCE \
  --from 2026-07-03 --to 2026-07-03 --timeframe 1m \
  --fields ts,open,high,low,close,volume --max-rows 1000 \
  --storage-root /var/tmp/swing-market-data --output json

uv run market-data query \
  --segment NSE_EQ --symbol RELIANCE \
  --from 2026-07-01 --to 2026-07-31 --timeframe 1d \
  --fields ts,open,high,low,close,volume --max-rows 31 \
  --storage-root /var/tmp/swing-market-data --output json
```

July 2026 is an example closed month, not authority to make a live request.
The daily path is local derivation from verified canonical one-minute data; it
never calls a provider.

## Evidence ladder

Use the cheapest proof that exposes the next risk, in this order:

1. focused offline tests for the changed contract, pure rule, failure, and
   boundary;
2. affected integration tests for catalog, storage, provider adapter, or CLI;
3. one disposable-root end-to-end smoke using deterministic inputs;
4. the full repository gate before merge; and
5. one authenticated provider smoke only when credentials are supplied and
   live-provider authority is explicit for that bounded attempt.

Mocks never substitute for the final authenticated provider smoke, because the
earlier Upstox probe showed that transport defaults can fail despite passing
unit tests. Conversely, a live smoke never substitutes for deterministic
failure, integrity, or recovery tests.

## Completion evidence

Sprint 3 is complete only when all of the following are demonstrated:

- exact public admission occurs before side effects and resolves identity from
  retained point-in-time snapshot evidence;
- authoritative immutable NSE session evidence is retained with source,
  release/as-of time, timezone, coverage, closures, and digest;
- immutable monthly Parquet and metadata-only DuckDB remain the canonical
  storage design, with atomic writes and explicit corruption outcomes;
- coverage proves every required scheduled minute rather than using `MAX(ts)`,
  a row count, weekday inference, or forward fill;
- an identical verified download makes zero historical provider requests;
- query selects only catalog-owned verified partitions, uses bounded fields,
  rows, paths, time, memory, and output, and accepts no arbitrary SQL;
- daily OHLCV is session-aware, explicit about incomplete data, and makes zero
  provider requests;
- credentials remain environment-only and no token, session, private market
  data, or generated dataset enters source control, logs, fixtures, or error
  text;
- focused tests, disposable-root smoke, the full gate, hosted CI, installation,
  and documentation pass on the accepted revisions; and
- missing, stale, corrupt, insufficient, `NO_TRADE`, cancellation, and partial
  outcomes remain visible and typed rather than becoming success.

## Deferred boundaries

- Point-in-time multi-symbol Nifty 50 scheduling and bounded concurrency remain
  later downloader-v1 work.
- Benchmark threshold redesign and final performance-release claims remain
  deferred; Sprint 3 still preserves bounded resources and detects material
  regressions.
- The authenticated closed-range release probe remains separately authorized;
  offline completion cannot be described as live release readiness.
- Weekly/monthly aggregation, indicators, signals, scoring, backtesting,
  regimes, recommendations, F&O, crypto, account linking, and execution are out
  of scope.

Write the sprint record once at close with the seven-slice result, gate/smoke
evidence, held boundaries, and any incomplete work. Do not create per-issue
sprint records or unchanged-state reports.
