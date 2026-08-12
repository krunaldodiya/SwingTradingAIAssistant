# Plan 01: Nifty 50 Equity Upstox Market-Data Tool

## Outcome

Build one reliable, installable Python tool that downloads, validates, stores,
resumes, and queries historical one-minute Upstox candles for point-in-time
Nifty 50 equities. Prove the vertical slice with RELIANCE, expand through an
explicit equity universe, and derive supported higher intraday timeframes
locally rather than sending duplicate provider requests.

Shared data, provenance, validation, storage, and application contracts should
avoid unnecessary provider or equity-symbol coupling. That extensibility does
not authorize index, derivative, forex, crypto, or other instrument adapters,
datasets, or research in this plan. A future instrument needs a separate
approved module and cannot enter the equity research pipeline by implication.

This plan covers market data only. Indicators, swing strategies, market regime,
SMC, screening, backtesting, agent integration, and trade reasoning are out of
scope until the data layer is proven.

## Decision: do not use ExpiryTrack as the canonical equity store

ExpiryTrack remains a read-only reference. It cannot replace this market-data
tool because its local database contains no Nifty 50 constituent equity candles
and its legacy schema is derivative-oriented. The previously proposed
NIFTY/India VIX migration is superseded by the equity-only downloader-v1
boundary.

We will build a small equity data package in this repository. Shared internals
may reuse independently validated architectural lessons from ExpiryTrack—rate
limiting, chunking, vectorized loading, and resumability—but will not copy its
AGPL implementation. The client must use the current Upstox Historical Candle
Data V3 contract.

## Storage decision

Use a hybrid layout:

1. **Partitioned Parquet is the canonical candle store.** It is compressed,
   typed, columnar, portable, immutable by partition, and directly queryable.
2. **DuckDB is the catalog and query engine.** It stores instrument snapshots,
   ingestion runs, partition manifests, and quality results, and queries Parquet
   without importing every candle into a second copy.
3. **CSV is export-only.** It is larger, slower, and loses strong typing.
4. **Feather is not a canonical format.** It is useful for temporary dataframe
   interchange but is weaker than partitioned Parquet for durable datasets.

This storage decision does not make Arrow or Parquet a dependency of the
logical canonical candle model. **ARK-31** freezes that versioned logical model
and its validation contract; **ARK-42** owns the separately versioned physical
Parquet mapping, including its Arrow implementation details. The physical
mapping must faithfully represent the ARK-31 model and cannot redefine it.

For one-minute data, write one immutable file per instrument and calendar month.
Download workers may prepare separate partitions concurrently; one coordinator
updates the DuckDB catalog. Files become visible only after validation and
same-filesystem hard-link no-clobber publication.

Suggested layout:

```text
data/
  catalog.duckdb
  candles/
    provider=upstox/
      exchange=NSE/
        segment=NSE_EQ/
          instrument_type=EQ/
            security_id=INE002A01018/
              interval=1m/
                year=2022/
                  month=01/
                    bars.parquet
```

Use ISIN as the stable equity `security_id`. Keep Upstox instrument keys and
symbols as versioned mappings because symbols and provider tokens may change.
The shared identity contract may be extended by a future approved instrument
module; this plan does not define that module's identifier.

## Supported instrument family

| Family | First implementation | Required selection policy |
|---|---|---|
| NSE equities | Historical one-minute candles | Explicit symbols or named universe |

The downloader core—request planning, rate limiting, retries, validation,
partition writing, manifests, and querying—is reusable. V1 has one explicit NSE
equity adapter and rejects contradictory non-equity metadata before catalog or
provider access. Future instrument support requires a new adapter specification,
data and risk contracts, validation plan, and approved roadmap work.

## Upstox constraints

Historical Candle Data V3 supports one-minute active-instrument candles through:

```text
GET /v3/historical-candle/{instrument_key}/minutes/1/{to_date}/{from_date}
```

Upstox documents minute history from January 2022 and permits at most one month
per request for 1–15 minute intervals. Use the daily BOD JSON instrument master
and provider `instrument_key`; do not use the deprecated CSV master or treat
`exchange_token` as stable identity.

References:

- [Historical Candle Data V3](https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/)
- [Intraday Candle Data V3](https://upstox.com/developer/api-documentation/v3/get-intra-day-candle-data/)
- [Instruments](https://upstox.com/developer/api-documentation/instruments/)
- [Rate limits](https://upstox.com/developer/api-documentation/rate-limiting/)

## Minimum schemas

### ARK-31 logical canonical candle schema v1

- `provider`
- `instrument_key`
- `security_id`
- `symbol`
- `exchange`
- `segment`
- `instrument_type`
- nullable `underlying_id`, `expiry`, `strike`, and `option_type`
- `interval`
- `ts`
- `open`, `high`, `low`, `close`
- `volume`
- nullable `oi`
- `ingested_at`
- `source_version`
- `adjustment_state` (`raw` initially)

`ts` is the inclusive bar-open timestamp for the one-minute half-open interval
`[ts, ts + 1m)`. It persists as a timezone-aware UTC timestamp with zero
seconds and microseconds; exchange-session interpretation converts it
explicitly to the exchange timezone. The provider adapter must verify the
provider's timestamp convention and translate it to this convention before
constructing the canonical model; an unverified convention is invalid input.
`ingested_at` is a timezone-aware UTC retrieval timestamp and is not required
to be aligned to a minute boundary. Session-calendar validation is outside the
canonical model constructor and is supplied by the applicable exchange-calendar
validation boundary. `open`, `high`, `low`, `close`, and nullable `strike`/`oi`
use finite IEEE-754 float64 values.
`volume` is an integer greater than or equal to zero; boolean values are invalid.
OHLC values must be nonnegative and satisfy the envelope
`high >= max(open, close, low)` and `low <= min(open, close, high)`.

Schema metadata records version `v1`. Uniqueness is
`(provider, instrument_key, interval, ts)`. Optional contract-identity columns
remain nullable in the frozen schema, but the v1 equity adapter must emit
`underlying_id`, `expiry`, `strike`, and `option_type` as `None`; contradictory
metadata is rejected before catalog or provider access. Their presence in the
versioned physical schema is not a claim of non-equity adapter support.

### ARK-42 physical Parquet mapping

**Approved decision — Linear ARK-42.** ARK-42 maps the ARK-31 logical canonical
candle schema v1 to partitioned Parquet. It owns Arrow/Parquet field types,
metadata encoding, and compatibility tests; ARK-31 deliberately has no Arrow or
Parquet dependency.

**Approved physical schema v1.** The immutable Arrow field order is:

1. non-null `provider: string`
2. non-null `instrument_key: string`
3. non-null `security_id: string`
4. non-null `symbol: string`
5. non-null `exchange: string`
6. non-null `segment: string`
7. non-null `instrument_type: string`
8. nullable `underlying_id: string`
9. nullable `expiry: date32`
10. nullable `strike: float64`
11. nullable `option_type: string`
12. non-null `interval: string`
13. non-null `ts: timestamp[us, tz=UTC]`
14. non-null `open: float64`
15. non-null `high: float64`
16. non-null `low: float64`
17. non-null `close: float64`
18. non-null `volume: int64` in the inclusive physical range `0` through
    `9_223_372_036_854_775_807`
19. nullable `oi: float64`
20. non-null `ingested_at: timestamp[us, tz=UTC]`
21. non-null `source_version: string`
22. non-null `adjustment_state: string`

The Arrow schema metadata must contain the application version requirement
`swing_trading_ai_assistant.candle_schema_version` with bytes value `1`; it does
not add a `schema_version` column. The v1 reader checks this metadata before it
reads rows, rejects missing and unsupported versions separately, and accepts v1
only when field order, names, types, and nullability exactly match the above
contract. Row-to-domain conversion failures remain distinct from physical-schema
incompatibility.

Parquet writes use format version `2.6`, microsecond timestamp coercion without
truncation, no deprecated INT96 timestamps, and stored Arrow schema metadata.
PyArrow owns construction, conversion, and round-trip validation. DuckDB is an
independent direct-Parquet compatibility check only; it does not create or store
a candle table. Compression, dictionaries, row groups, page checksums, temporary
or atomic publication, manifests, provider fetching, and orchestration remain
the responsibility of later approved children.

The ARK-31 logical `volume` contract remains any nonnegative built-in integer.
ARK-42 rejects a logical volume above the physical signed-int64 maximum with an
explicit non-representable-value error; it does not redefine the logical model.
Reader and writer batches are bounded to `65_536` candles. The reader closes on
exhaustion and conversion failure; callers that stop early use its context
manager or call `close()` explicitly.

### ARK-43 Upstox equity canonical adapter

**Approved decision — Linear ARK-43.** The pure
`canonicalize_upstox_equity_candles` adapter maps already-normalized `Candle`
values plus one resolved `Instrument` and caller-supplied `ingested_at` to a
sorted tuple of ARK-31 canonical candles. Upstox Historical Candle V3 timestamps
are timeframe starts, so the adapter maps their UTC instant directly without a
shift. It supports only `NSE_EQ`/`EQ`, copies resolved identity, fixes the
approved Upstox provenance values, sets every derivative field and canonical OI
to `None`, and rejects positive source OI. It validates canonical uniqueness and
does not fetch, store, inspect raw payloads, use clocks, or apply calendar rules.
Its input is a finite `Sequence[Candle]` capped at 65,536 rows, safely above the
44,640 minutes in any calendar month and aligned with one-month one-minute
requests. Resolved identity must be NSE/NSE_EQ/EQ with absent derivative fields;
source OI is only absent or exact finite zero.

### ARK-32 monthly request planner

**Approved decision — Linear ARK-32.** A pure one-minute planner validates one
resolved NSE/NSE_EQ/EQ equity instrument and exact built-in date and `1m` inputs,
then produces immutable, contiguous, inclusive calendar-month requests. The
user-approved rules reject dates before 2022-01-01 atomically rather than
clipping them, and accept only `1m`; weekends and holidays remain in request
coverage. It computes the month count before output allocation. From the exact
built-in `date` contract and the approved lower bound, the derived natural
representational bound is January 2022 through December 9999 (95,736 months).
Planning is O(months), with no clock,
HTTP, credential, storage, candle, or calendar-service dependency.

### ARK-33 partition reconciliation

**Approved decision — Linear ARK-33.** A pure reconciliation boundary accepts a
finite sequence of ARK-32 planned instrument-months and supplied manifest and
physical-observation evidence, then returns one ordered immutable `SKIP` or
`REQUEST` decision per plan. It never reads files, candles, databases, clocks,
or providers. A partition is skipped only for exactly one matching evidence
record whose manifest is verified, file exists, canonical relative paths match,
lowercase SHA-256 values match, schema versions match and are physically
compatible, recorded dates match the plan, and coverage and quality both pass.
Missing or duplicate evidence requests the partition without inspecting or
selecting an evidence record; duplicate plans and orphan evidence are invalid.
`REQUEST` reasons are a stable ordered taxonomy: `MISSING_EVIDENCE`,
`DUPLICATE_EVIDENCE`, `MANIFEST_NOT_VERIFIED`, `FILE_MISSING`,
`PATH_INVALID_OR_MISMATCHED`, `CHECKSUM_INVALID_OR_MISMATCHED`,
`SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE`, `RECORDED_RANGE_MISMATCHED`,
`COVERAGE_NOT_PASSED`, and `QUALITY_NOT_PASSED`. Canonical paths are a lexical,
filesystem-independent relative slash-separated form with no empty, `.`, or
`..` components, no leading or trailing component whitespace, no backslashes,
no colons, and only printable Unicode characters. Evidence may faithfully record missing or
corrupt path, checksum, schema-version, and date observations as `None` or
invalid content; reconciliation converts those facts into the matching request
reason rather than fabricating values. Runtime scalar types remain exact. The
physical partition identity is `(provider, exchange, segment, instrument_type,
security_id, interval, year, month)`; symbols, provider instrument keys, and
requested partial dates do not affect duplicate, matching, or orphan checks.
The bounded input ceiling is 95,736 plans or evidence records; reconciliation is
O(plans + evidence).

### ARK-40 manifest lifecycle

**Approved decision — Linear ARK-40.** The lifecycle core is pure and owns one
immutable current manifest per physical instrument-month; `ingestion_runs`
owns immutable historical attempts and enforces historical run-ID uniqueness.
The core enforces only current-ID inequality and does not accumulate caller
history. Manifest fields are schema version, physical month plan, current run
ID, state, validation outcome and policy version, candle schema version, actual
UTC minute coverage, row count, lowercase SHA-256 checksum, canonical path,
source version, full-precision UTC lifecycle timestamps, and failure category.
It permits only `IN_PROGRESS` to `VERIFIED` or `FAILED`, `FAILED` to
`IN_PROGRESS` retry, and `VERIFIED` to physical-invalidation `FAILED`.

The failure taxonomy is exactly `INTERRUPTED`, `EMPTY_RESPONSE`,
`PROVIDER_RETRYABLE`, `PROVIDER_NON_RETRYABLE`, `NORMALIZATION_FAILED`,
`VALIDATION_FAILED`, `WRITE_FAILED`, `PUBLICATION_FAILED`, `FILE_MISSING`,
`PATH_INVALID_OR_MISMATCHED`, `CHECKSUM_INVALID_OR_MISMATCHED`,
`SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE`, `COVERAGE_NOT_PASSED`, and
`QUALITY_NOT_PASSED`. From `IN_PROGRESS`, only the first eight are allowed:
interruption/provider/normalization failures are `NOT_RUN`; empty and
validation failures are `FAILED`; write and publication failures are `PASSED`.
The last six are exclusively `VERIFIED` invalidations, remain `PASSED`, and
preserve complete verified artifact and provenance evidence. `EMPTY_RESPONSE`
is exactly zero rows with no schema, coverage, path, or checksum. Failed
diagnostic coverage, when present, is paired and UTC minute-aligned but may be
unordered or outside the plan; verified coverage alone is ordered and in-plan.

ARK-33 remains a supplied-observation adapter: it performs no I/O and does not
infer coverage from row counts or timestamps. Retry requires a caller-supplied
new current run ID, source version, validation policy version, and timestamps;
it preserves creation and plan but clears terminal artifacts and failure.
Physical invalidation preserves verified provenance and artifacts. All lifecycle
timestamps are caller-supplied full-precision UTC values; no lifecycle clock,
calendar service, or timezone database is used.

### ARK-34 atomic Parquet publication

**Approved decision — Linear ARK-34.** The publisher accepts a caller-supplied
storage-root `Path`, one exact ARK-32 plan, and one bounded sequence of exact
canonical equity candles. The sequence admission ceiling is 65,536 values and
is checked before indexing or storage I/O; semantic month validation remains
strict, so a successful calendar-month partition has at most its number of
days times 1,440 unique minutes (at most 44,640). It derives the sole canonical Hive path from the
physical identity only: `candles/provider=.../exchange=.../segment=.../`
`instrument_type=EQ/security_id=.../interval=1m/year=YYYY/month=MM/`
`bars.parquet`; symbols and provider instrument keys are never path inputs.
Every path-bearing identity value is an exact built-in ASCII string matching
`[A-Za-z0-9][A-Za-z0-9._-]{0,127}`. Hive components use known `key=` prefixes
plus those validated values; no process lock is used, and concurrent writers
converge through hard-link no-clobber. It reconstructs and validates every candle, rejects duplicates rather than
deduplicating, sorts by UTC timestamp, and validates/re-reads through the
authoritative temporary descriptor for exact ordered equality before publication;
that descriptor remains retained through final publication checks.

The caller-supplied storage root is a pre-existing durable real directory; the
publisher never creates or resolves it.  It walks every derived descendant by
directory descriptor with no-follow semantics, rejects links and non-directories,
and fsyncs each parent after a newly-created child. Cleanup only removes its exact
temporary sibling. Published evidence is sealed: exact revalidated plan, enum,
canonical path, lowercase SHA-256, schema, counts, UTC coverage, source version,
and byte size. Publication uses a hidden random mode-0600 sibling temporary file, a bounded
streaming SHA-256, and local POSIX hard-link no-clobber publication followed by
directory fsync. The storage root and its publication directories are
application-owned and protected from untrusted same-directory mutation; portable
Python cannot preserve a canonical pathname against an arbitrary writer after
return. Legitimate concurrent publisher processes remain supported by no-clobber
convergence. A matching existing file returns `ALREADY_PRESENT`; an invalid
or different file is a conflict and is never overwritten or repaired. Any error
after visibility raises an outcome-unknown publication error and leaves the
final file for ARK-33 reconciliation. The publisher has no catalog, manifest,
provider, DuckDB, clock, or credential side effects. ARK-42 fixes the writer to
Parquet 2.6, Snappy, dictionary/statistics enabled, data-page v1, page checksums
enabled, page index disabled, and at most one 65,536-row group. Byte stability is
within the pinned PyArrow 25 runtime scope.

### DuckDB catalog tables

- `instrument_snapshots`: dated Upstox instrument metadata and source hash.
- `ingestion_runs`: immutable request-attempt history, timing, code/config
  version, result, error class, and historical run-ID uniqueness.
- `partitions`: instrument/month, requested range, actual range, row count,
  checksum, path, status, and timestamps.
- `quality_issues`: gaps, duplicates, invalid OHLC envelopes, negative volume,
  off-session timestamps, and unresolved anomalies.

DuckDB stores catalog metadata only; it never stores candle rows. Candle rows
remain in canonical Parquet and are queried through DuckDB's Parquet scans.
Do not store credentials or access tokens in either Parquet or DuckDB.

## Non-functional requirements

### Provider-request minimization

- Fetch and persist one-minute candles as the canonical intraday source. Higher
  intraday timeframes must be derived locally from verified one-minute
  partitions with exchange-session-aware aggregation; requesting 3m, 5m, 15m,
  30m, or hourly history from Upstox for the same covered range is prohibited.
- **ARK-33 physical reconciliation:** a download plan is computed against the
  DuckDB partition manifest before any authenticated candle request is sent. A
  partition may be skipped only when its manifest status is verified and its
  immutable Parquet file exists, its checksum matches, its schema version is
  supported, and its recorded coverage passes the applicable quality policy.
- **ARK-40 manifest lifecycle:** manifest state transitions, temporary output,
  and terminal partition registration are managed as a separate lifecycle
  concern from physical reconciliation and skip decisions.
- Missing, unverified, corrupt, incompatible, or incomplete partitions are
  scheduled independently. Do not restart an interrupted multi-month or
  multi-instrument run from its original beginning.
- Resume decisions must not use `MAX(ts)` as proof of completeness. Persist the
  requested range, actual range, row count, checksum, validation outcome, source
  version, and terminal partition state so interruption and repair are
  deterministic.
- Temporary files and in-progress catalog states are never treated as completed
  work. After a crash, discard or quarantine abandoned temporary output and
  retry only the affected partition.
- Retries apply only to retryable provider failures, use bounded backoff and the
  provider's `Retry-After` guidance when valid, and share one account-level rate
  limiter across all workers.

Higher-timeframe aggregation is a query concern, not an ingestion request. Its
exact session buckets and incomplete-bucket policy are frozen in
[Plan 08](08-local-intraday-view-contract.md). Derived intraday facts remain
raw-only; the separately versioned corporate-action boundary owns any future
adjusted availability or formula. The raw-only corporate-action provenance and
explicit unsupported-adjustment contract is frozen in
[Plan 09](09-corporate-action-provenance-contract.md).

### Performance

- Treat network and provider rate limits as the expected ingestion bottleneck;
  parsing, validation, and storage must keep up without building an unbounded
  in-memory queue.
- Process one instrument-month partition at a time. Never load an entire
  multi-year or multi-instrument dataset into one dataframe merely to write it.
- Use columnar Arrow/Parquet operations and vectorized validation for candle
  batches; avoid per-row Python database inserts.
- Push filters, projections, and aggregations into DuckDB and Parquet scans.
- Store raw candles once; do not maintain duplicate DuckDB and Parquet copies by
  default.
- Capture elapsed time, rows/second, bytes written, peak memory, retries, and
  query latency in a reproducible benchmark report.

### Scalability

- Bound HTTP workers, completed-download buffers, write workers, open files, and
  retry queues through configuration with safe defaults.
- Partition work by instrument and month so scheduling, retries, repair, and
  horizontal distribution do not require redesigning the storage model.
- Use one shared rate limiter per provider account, even when many instrument
  adapters or workers are active.
- Keep the catalog small: store metadata and partition statistics in DuckDB, not
  a duplicate row for every candle.
- Ensure the design works for one RELIANCE partition and the full Nifty 50
  equity history without separate code paths for each scale.

### Maintainability

- Separate provider API adapters, credential providers, instrument resolution,
  request planning, normalization, validation, storage, and CLI orchestration.
- Keep the domain schemas independent of Upstox response objects. Provider
  adapters translate external payloads into versioned internal models.
- Use typed configuration and models; avoid global mutable clients, hard-coded
  symbols, absolute data paths, and business rules hidden in CLI handlers.
- Version catalog migrations and Parquet schemas, and test forward/backward
  compatibility before changing stored data.
- Use structured logs and explicit error categories without credential material.
- Require unit tests for pure components, contract tests for provider payloads,
  integration tests against temporary storage, and end-to-end tests for resume
  and repair behavior.
- Prefer small composable interfaces over a generic class with instrument-type
  conditionals spread through the codebase.

### Benchmark gates

After the RELIANCE vertical slice, record a reference-machine baseline for:

1. normalizing, validating, and writing one representative monthly partition;
2. querying one stock across its full history;
3. scanning a synthetic or downloaded 50-stock dataset for a selected range;
4. resuming a mostly completed backfill; and
5. detecting and repairing a deliberately damaged partition.

Add regression tests that flag material degradation from the recorded baseline.
Set absolute latency and memory budgets only after measuring the real RELIANCE
payload, so targets are evidence-based rather than invented.

## Milestone 0: credential-safe capability probe

Implement a diagnostic command that obtains the Upstox token through a portable
environment credential-provider interface. The CLI loads `UPSTOX_ACCESS_TOKEN`
from an ignored local `.env` file and must never print the secret. Application
code must not depend on macOS Keychain or any other operating-system credential
store; developers may use those tools manually outside the application.

For a caller-selected instrument, using RELIANCE only as the first validation
case:

1. download the current Upstox NSE instrument JSON;
2. resolve the supplied segment and trading symbol exclusively through that
   master instrument catalog;
3. request a small recent one-minute historical window;
4. report only response status, row count, first/last timestamp, and schema
   validation; and
5. make no persistent candle writes.

Gate: do not build the downloader until authentication, entitlement, URL shape,
and actual response schema are confirmed.

No provider, storage, ingestion, or domain constant may embed RELIANCE, its
ISIN, security ID, provider instrument key, or lookup alias. A bounded public
preview may inject an exact user-visible segment/symbol admission policy at the
package composition root; that product policy never substitutes for retained
point-in-time instrument resolution.

## Milestone 1: RELIANCE vertical slice

Implement one CLI workflow:

```text
market-data download --symbol RELIANCE --interval 1m \
  --from 2022-01-01 --to YYYY-MM-DD
```

The workflow must:

- resolve the instrument from a retained BOD snapshot;
- split the range into non-overlapping calendar-month requests;
- obey Upstox rate limits and retry retryable failures with bounded backoff;
- normalize timestamps consistently while preserving exchange-session meaning;
- sort, deduplicate, and validate each monthly partition;
- write Parquet through a temporary file and same-filesystem hard-link
  no-clobber publication;
- record the partition checksum and coverage in DuckDB; and
- resume without downloading already verified partitions.

Implementation order within the storage path is **ARK-31**, then **ARK-43**
(the normalized-to-canonical provider adapter), before **ARK-34**. **ARK-44**
was canceled and superseded by the equity-only downloader-v1 boundary; it is not
an implied part of ARK-31, ARK-43, or ARK-34.

Initial query proof:

```sql
SELECT min(ts), max(ts), count(*)
FROM read_parquet('data/candles/**/bars.parquet', hive_partitioning = true)
WHERE security_id = 'INE002A01018';
```

## Milestone 2: correctness and recovery

Before adding more stocks, verify:

- a repeated download is idempotent;
- interruption leaves no valid-looking partial partition;
- corrupt or incomplete partitions are detected and repaired;
- internal gaps are detected—`MAX(ts)` is not accepted as completeness proof;
- duplicates and impossible OHLC values fail validation;
- empty successful responses remain retryable or explicitly classified;
- random monthly samples match direct Upstox responses; and
- raw candle files never change because downstream adjustment logic changes.

Coverage must account for NSE holidays, special sessions, late listings, and
legitimate no-trade minutes. Do not forward-fill missing candles.

## Milestone 3: one-or-many instrument scalability

Replace the single symbol argument with a repeatable instrument, instrument file,
or named universe while preserving the RELIANCE workflow:

```text
market-data download --symbols RELIANCE,TCS,HDFCBANK --workers 4 ...
market-data download --universe nifty50-current --workers 8 ...
```

- Use bounded asynchronous HTTP concurrency; never start an unbounded task per
  instrument/month.
- Apply one shared provider rate limiter across all workers.
- Keep request concurrency separate from catalog writes.
- Schedule at partition granularity so individual months can retry independently.
- Provide progress, failure summaries, and a machine-readable coverage report.
- Make the current Nifty 50 universe an explicit snapshot, not a claim about
  historical membership.

Approximately 50 current equities across about 55 monthly windows requires
roughly 2,750 requests before retries and should yield approximately 20–25
million one-minute rows. That scale is modest for Parquet plus DuckDB.

## Milestone 4: packaged Nifty 50 downloader v1

Complete the equity downloader as a reusable installable Python package:

1. expose versioned Python download, coverage, and query interfaces over the
   same application contracts used by the CLI, beginning with the
   [public-preview contract](04-public-preview-contract.md);
2. support an explicit point-in-time Nifty 50 universe and bounded date ranges;
3. keep the canonical storage root configurable outside one project checkout so
   authorized related tools can reuse verified partitions;
4. derive approved higher intraday timeframes locally from canonical one-minute
   data with exchange-session-aware aggregation and no duplicate provider call;
5. document installation, credentials, storage ownership, interruption resume,
   coverage inspection, and safe query examples; and
6. prove clean-build, package-install, compatibility, performance, and release
   readiness gates.

This milestone does not add index, derivative, forex, crypto, or other
instrument adapters. Those require a future approved module and release plan.

## Acceptance gate

The data phase is complete only when:

- RELIANCE can be downloaded from the earliest available minute history through
  a requested recent date, including the current date through the latest
  completed scheduled minute when authoritative current-session evidence is
  supplied;
- reruns and crash recovery are safe and idempotent;
- coverage and known anomalies are visible rather than silently hidden;
- DuckDB can query one or many instruments directly from Parquet;
- a bounded multi-stock download succeeds without violating provider limits;
- data source, ingestion time, raw/adjusted state, and checksums are traceable;
- no credential or private dataset is tracked by Git;
- the package can be installed and its Python and CLI contracts query the same
  verified equity data;
- higher intraday timeframes are derived locally from verified one-minute data
  without an additional historical provider request;
- an explicitly configured shared storage root can be reused without weakening
  ownership, integrity, or credential boundaries;
- measured performance and memory usage satisfy the recorded benchmark budgets;
- provider, storage, validation, and orchestration components can be tested and
  changed independently;
- no trading, indicator, backtest, or AI-agent feature has entered this phase.

## Execution source of truth

Linear and the current sprint document determine the next approved atomic task;
this plan does not authorize work merely because it appears in a later
milestone. Deliver coherent independently verifiable slices with one writer per
file path, and complete the equity downloader-v1 milestone before starting
research-module implementation.
