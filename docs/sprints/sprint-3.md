# Sprint 3 — Usable single-symbol downloader preview

Status: **EXTENDED — DOWNLOADER V1 COMPLETION IN PROGRESS**

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
  --schedule-file /var/tmp/nse-schedule.json \
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

## Closeout record

All seven coherent slices were delivered in dependency order:

| Slice | Accepted revision |
| --- | --- |
| 1. Public contract | [PR #69](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/69), merge `859a5bf` |
| 2. Authoritative preparation | [PR #70](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/70), merge `3efe4cf` |
| 3. Persistent download | [PR #71](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/71), merge `6f68a59` |
| 4. Stored coverage | [PR #72](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/72), merge `dfd7cd3` |
| 5. One-minute query | [PR #73](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/73), merge `d6dca86` |
| 6. Daily query | [PR #74](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/74), merge `ff677c2` |
| 7. Usability proof | this sprint-close revision |

The final controlled smoke uses an external disposable root and actual public
services. It supplies deterministic authoritative schedule, snapshot, and
historical responses; verifies one persistent monthly Parquet publication; and
then proves an identical download makes zero snapshot and historical requests.
Coverage, bounded selected-field `1m`, and locally derived `1d` all succeed with
zero provider attempts. Public JSON contains no storage path or credential.

The source distribution and wheel build successfully. The wheel installs into
a fresh temporary virtual environment, reports package version `0.1.0`, and
exposes `download`, `coverage`, `query`, and `probe-upstox`. The final local
suite contains **1,349 tests** and reaches **91.27% branch coverage**; Ruff
format and lint, strict Pyright on production source, Vulture at 80%, the full
pytest gate, and hosted CI are required on the accepted closeout revision.

The seven-slice closeout shipped a controlled single-symbol preview, not
live-release or multi-symbol readiness. The package has no embedded exchange-
calendar feed; Slice 8 adds explicit bounded canonical `--schedule-file`
composition while continuing to fail closed without approved evidence. The
authenticated closed-range Upstox gate,
multi-symbol point-in-time scheduling, benchmark release thresholds, research
logic, advice, and broker execution remain explicitly deferred.

## Downloader-v1 completion extension

The seven-slice preview closeout above remains accepted historical evidence.
Sprint 3 is extended because Plan 01 requires the complete equity downloader-v1
milestone before research-module implementation begins. The remaining work is
therefore a release prerequisite, not feature polish or speculative
optimization.

The extension proceeds as six coherent, independently verifiable slices:

| Slice | Required outcome | Linear scope | Depends on |
| --- | --- | --- | --- |
| 8. Runtime trust boundary | Compose authoritative schedule evidence in production and close the probe date, provider-envelope, and redirect credential gaps | ARK-139, ARK-19, ARK-20, ARK-23 | Preview closeout |
| 9. Milestone 2 proof | Persist comparable benchmarks, derive thresholds, run the one authorized same-response RELIANCE gate, and close correctness/recovery acceptance | ARK-111, ARK-92, ARK-93, ARK-69, ARK-11 | 8 |
| 10. Point-in-time universe | Retain versioned Nifty 50 membership and sector snapshots with effective dates and provenance | ARK-140 | 8 |
| 11. Bounded multi-instrument workflows | Download, resume, inspect coverage, and query one or many admitted instruments under shared bounded resources | ARK-141, ARK-12 | 9–10 |
| 12. Local views and adjustment boundary | Derive approved higher intraday views from verified `1m` data and represent corporate-action/raw-adjusted provenance without rewriting raw bars | ARK-142, ARK-143 | 10–11 |
| 13. Downloader-v1 release proof | Prove clean install, Python/CLI parity, compatibility, bounded performance, documentation, full gate, and release readiness | ARK-144, ARK-13 | 9–12 |

The dependency chain is deliberate: research-module implementation remains
blocked until Slice 13 closes. Work may proceed concurrently only where file
ownership and dependencies are disjoint; contracts, schemas, migrations, and
configuration stay serialized. An unavailable credential or authoritative
external source may block only its bounded live proof, not unrelated offline
implementation.

Optional post-v1 work is kept out of this completion chain in the
[data downloader future TODO](../plans/data-downloader-v1-future-todo.md).
