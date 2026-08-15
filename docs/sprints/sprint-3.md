# Sprint 3 — Nifty 50 downloader v1

Status: **CLOSED — DOWNLOADER V1 RELEASE GATE PASSED**

## Goal

Deliver the installable, persistent Nifty 50 equity downloader v1: one, many, or
all retained point-in-time members; current-month continuity; bounded shared
resources; provider-free coverage/query; local timeframes; point-in-time
corporate-action provenance; package/install proof; and release evidence.

The first seven slices delivered the historical single-symbol preview. The
extension completes the final multi-symbol release boundary while preserving
the deterministic tool/AI split. It adds no signal, score, advice,
portfolio/account connection, autonomous decision, or broker execution.

## Delivered slices

The sprint delivered seven coherent slices. The earlier issue graph remains
historical tracking detail.

| Slice | Coherent outcome | Dependencies |
| --- | --- | --- |
| 1. Public contract | Admission, common report/serializer, snapshot provenance, catalog migration, preparation handoff | Plans 01–02 |
| 2. Authoritative preparation | Injected admission; provenance-complete NSE schedule; bounded BOD fetch; immutable snapshot store; offline resolver; schedule-first preparation | 1 |
| 3. Persistent download | Shared public conversion, download service, JSON renderer, and `market-data download` CLI | 2 |
| 4. Stored coverage | Read-only root admission, verified selection, coverage service/report, and `market-data coverage` CLI | 3 |
| 5. One-minute query | Bounded direct-Parquet query service/report and `1m` CLI adapter | 4 |
| 6. Daily query | Session-aware daily derivation contract/service and `1d` CLI adapter, with zero provider calls | 5 |
| 7. Usability proof | Clean install, disposable-root end-to-end workflow, docs, and sprint-close evidence | 6 |

The source contract was
[Plan 04](../plans/04-public-preview-contract.md). Each slice retained
executable contract evidence, and the final publication evidence below records
the exact repository checks, review results, and merged revision.

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

## Verification evidence

The completed Sprint 3 evidence combined focused offline cases, affected
integration cases, one disposable-root end-to-end smoke, recorded repository
and hosted checks, and one owner-authorized provider smoke.

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
- recorded offline, disposable-root, repository, hosted, installation, and
  documentation evidence passes; and
- missing, stale, corrupt, insufficient, `NO_TRADE`, cancellation, and partial
  outcomes remain visible and typed rather than becoming success.

## Preview closeout deferred boundaries (historical)

These were the held boundaries at the seven-slice preview close. The downloader-
v1 extension later promoted the multi-symbol, benchmark, authenticated proof,
current-month, local-view, and release-readiness items into Slices 8–13 below.

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

The extension proceeds as seven coherent, independently verifiable slices:

| Slice | Required outcome | Linear scope | Depends on |
| --- | --- | --- | --- |
| 8. Runtime trust boundary | Compose authoritative schedule evidence in production and close the probe date, provider-envelope, and redirect credential gaps | ARK-139, ARK-19, ARK-20, ARK-23 | Preview closeout |
| 9. Milestone 2 proof | Persist comparable benchmarks, derive thresholds, run the one authorized same-response RELIANCE gate, and close correctness/recovery acceptance | ARK-111, ARK-92, ARK-93, ARK-69, ARK-11 | 8 |
| 10. Point-in-time universe | Retain versioned Nifty 50 membership and sector snapshots with effective dates and provenance | ARK-140 | 8 |
| 10a. Current-month continuity | Persist and query the current month through the latest completed minute; append only the advancing same-day suffix | ARK-145 | 8–10 |
| 11. Bounded multi-instrument workflows | Download, resume, inspect coverage, and query one or many admitted instruments under shared bounded resources | ARK-141, ARK-12 | 9–10a |
| 12. Local views and adjustment boundary | Derive approved higher intraday views from verified `1m` data and represent corporate-action/raw-adjusted provenance without rewriting raw bars | ARK-142, ARK-143 | 10–11 |
| 13. Downloader-v1 release proof | Prove clean install, Python/CLI parity, compatibility, bounded performance, documentation, repository checks, and release readiness | ARK-144, ARK-13 | 9–12 |

The dependency chain is deliberate: research-module implementation remains
blocked until Slice 13 closes. An unavailable credential or authoritative
external source may block only its bounded live proof, not unrelated offline
product evidence.

Optional post-v1 work is kept out of this completion chain in the
[data downloader future TODO](../plans/data-downloader-v1-future-todo.md).

The current-month contract and its exact live evidence are recorded in
[Plan 06](../plans/06-current-month-incremental-data-contract.md). This closes
the former gap between a requested recent date and the latest completed minute:
the current month is explicit `PROVISIONAL` evidence, never falsely marked as a
fully verified closed month.

The one/many/all-50 selection, point-in-time ISIN binding, shared resource
bounds, and provider-free read contract are recorded in
[Plan 07](../plans/07-bounded-nifty50-workflow-contract.md).

The zero-provider `3m`, `5m`, `15m`, `30m`, and `1h` session-anchored view
contract, including current-session completed-bucket behavior, is recorded in
[Plan 08](../plans/08-local-intraday-view-contract.md).

The immutable Upstox corporate-action observation and explicit raw-only,
adjusted-unsupported provenance boundary is recorded in
[Plan 09](../plans/09-corporate-action-provenance-contract.md).

## Downloader-v1 acceptance crosswalk

This table crosswalks every Plan 01 acceptance row. `PASS` means the
functional requirement has exact local or retained operational evidence. The
final reviewed source tree contained 1,973 passing tests at 93.22% project
branch coverage; publication evidence is recorded below.

| ID | Plan 01 requirement | Result | Exact evidence |
| --- | --- | --- | --- |
| `A01` | RELIANCE from earliest supported history through a requested recent date, including the current date through the latest completed scheduled minute | PASS | Plan 06 retained a live 8,625-row verified July partition plus a 2,625-row provisional August snapshot through `2026-08-11T09:59:00Z`; an identical repeat made zero candle-provider requests. |
| `A02` | Safe, idempotent reruns and crash recovery | PASS | ARK-69 and the ingestion, publication, lease, recovery, and current-month suites prove zero-request replay, atomic/no-clobber publication, typed recovery, and no valid-looking partial result. |
| `A03` | Visible coverage and known anomalies | PASS | Stored and open-month coverage tests prove scheduled minutes rather than `MAX(ts)` and retain typed missing, stale, corrupt, insufficient, provisional, and partial evidence. |
| `A04` | Direct-Parquet query for one or many instruments | PASS | ARK-141 provides bounded point-in-time single, explicit-list, and all-50 coverage/query orchestration over the same provider-free direct-Parquet services. |
| `A05` | Bounded multi-stock download within provider limits | PASS | ARK-141 enforces one shared account limiter, `1..8` workers, at most 50 symbols, bounded attempts, deterministic ordering, cancellation, and per-symbol terminal results. |
| `A06` | Traceable source, ingestion time, raw/adjusted state, and checksums | PASS | Manifests and catalog metadata retain source/release/retrieval/checksum evidence; ARK-143 adds immutable Upstox corporate-action observations and explicit `raw`/`unsupported` adjustment and symbol-change states. |
| `A07` | No tracked credential or private dataset | PASS | `.gitignore` excludes environment secrets, tokens, Parquet, DuckDB, databases, generated data, and artifacts; the tracked-file scan is empty except the safe `.env.example`. |
| `A08` | Clean install and Python/CLI parity over the same verified data | PASS | The wheel installs into a clean virtual environment and exposes `market-data`; public CLI adapters wrap the same versioned download, coverage, and query application contracts used by Python callers. |
| `A09` | Local higher intraday timeframes with zero additional historical request | PASS | ARK-142 derives `3m`, `5m`, `15m`, `30m`, and `1h` session-anchored views from admitted `1m`; existing `1d` remains session-aware and provider-free. |
| `A10` | Reusable explicitly configured shared root without weakened boundaries | PASS | Every public request requires an explicit absolute owner-private root; descriptor-bound leases, no-follow reads, immutable objects, bounded read snapshots, and concurrent-reader tests preserve authority and integrity. |
| `A11` | Measured performance and memory satisfy retained budgets | PASS | ARK-92 retained five samples per B01–B05 workload and ARK-93 accepted all 35 applicable latency, throughput, RSS, descriptor, and exact-invariant thresholds without tuning. |
| `A12` | Independently testable provider, storage, validation, and orchestration components | PASS | Typed ports and focused suites isolate Upstox adapters, schedule/instrument/universe/action evidence, Parquet/catalog storage, validation, single-symbol services, and bounded orchestration. |
| `A13` | No trading, indicator, backtest, or AI-agent feature in the data phase | PASS | The shipped package surface is market-data download, coverage, query, and diagnostic capability only; research logic, advice, portfolio access, and broker execution remain absent and out of scope. |

## Publication evidence

Functional acceptance and every publication proof completed on the exact
publication chain. PR #82 merged reviewed candidate
`57ffe8e405ca7becb790c3267becbf7c673cd801` as
`23b07d0c6204de230e5cebe17c8f54001751b253` on `main`.

| Publication proof | State | Required terminal evidence |
| --- | --- | --- |
| Independent exact-candidate review of ARK-141, ARK-142, and ARK-143 | PASS | Three fresh read-only reviews approved exact candidate `57ffe8e` / tree `62ce6bc9`; focused reviewer suites passed 175, 178, and 317 tests. |
| Fresh five-tool repository checks on the ARK-144 release-proof tree | PASS | Ruff format and lint, strict Pyright, Vulture at 80%, and all 1,973 pytest cases passed at 93.22% coverage; one expected Python 3.13 fork deprecation warning remained non-failing. |
| Clean wheel installation and CLI/Python import smoke | PASS | Python 3.11 build, fresh wheel installation, package import, and CLI help passed; wheel SHA-256 `a31524d17f71c28da42f3d014c8016efc8baacbbca00876fc663fa899348a670`. |
| Hosted pull-request CI on the exact candidate | PASS | GitHub Actions `Quality and build` run `31578188264` and GitGuardian succeeded on exact head `57ffe8e`. |
| Final merge revision and Linear/sprint synchronization | PASS | PR #82 merged as `23b07d0`; ARK-141–144, ARK-12, ARK-60, ARK-61, and ARK-13 were read back as Done. |
