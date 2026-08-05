# Plan 01: Generalized Upstox Market-Data Tool

## Outcome

Build one reliable, instrument-agnostic tool that downloads, validates, stores,
resumes, and queries historical Upstox candles. The core must support equities,
indices, futures, and options without encoding assumptions from any one family.
Prove it end to end with one-minute RELIANCE equity data, then enable the other
families through explicit instrument adapters and collection policies.

This generalized ingestion capability does not expand v1 research scope: the
locked research pipeline remains point-in-time Nifty 50 equities only. Index or
F&O records may be stored only as separately specified market-data artifacts and
cannot be consumed as v1 equity research facts by implication.

This plan covers market data only. Indicators, swing strategies, market regime,
SMC, screening, backtesting, agent integration, and trade reasoning are out of
scope until the data layer is proven.

## Decision: do not use ExpiryTrack as the generalized store

ExpiryTrack remains useful as a reference and its existing DuckDB can later be
opened read-only for Nifty 50 and India VIX context. It cannot replace this
market-data tool because its local database contains no Nifty 50 constituent
equity candles and its schema requires derivative concepts even for spot data.
It also separates active and expired collection through interfaces that do not
form a clean generalized instrument contract.

We will build a small instrument-agnostic data package in this repository. We may
reuse validated architectural lessons from ExpiryTrack—rate limiting, chunking,
vectorized loading, and resumability—but will not copy its AGPL implementation.
The new client must use the current Upstox Historical Candle Data V3 contract;
ExpiryTrack's generic active-instrument method still uses a V2-style path.

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
updates the DuckDB catalog. Files become visible only after validation and an
atomic temporary-file rename.

Suggested layout:

```text
data/
  catalog.duckdb
  candles/
    provider=upstox/
      exchange=NSE/
        segment=NSE_EQ/
          instrument_type=EQUITY/
            security_id=INE002A01018/
              interval=1m/
                year=2022/
                  month=01/
                    bars.parquet
```

Use ISIN as the stable equity `security_id`. For indices and derivatives, use a
canonical internal identifier derived from normalized contract metadata rather
than a mutable provider token. Keep Upstox instrument keys and symbols as
versioned mappings because symbols, tokens, and active/expired keys may change.

## Instrument-family support

| Family | First implementation | Required selection policy |
|---|---|---|
| NSE equities | Full historical and intraday candles | Explicit symbols or named universe |
| NSE/BSE indices | Full historical and intraday candles | Explicit index list |
| Active futures | Historical and intraday candles | Underlying plus expiry range |
| Active options | Historical and intraday candles | Underlying, expiry, call/put, and strike window |
| Expired futures/options | Separate Upstox expired-instrument adapter | Same filters; Upstox Plus entitlement required |

The downloader core—request planning, rate limiting, retries, validation,
partition writing, manifests, and querying—is shared. Provider endpoints,
instrument discovery, identifiers, expected fields, and collection filters are
family-specific adapters. Do not disguise an index or equity as a derivative,
and do not assume an expired instrument uses the active-instrument API.

## Upstox constraints

Historical Candle Data V3 supports one-minute active-instrument candles through:

```text
GET /v3/historical-candle/{instrument_key}/minutes/1/{to_date}/{from_date}
```

Upstox documents minute history from January 2022 and permits at most one month
per request for 1–15 minute intervals. Use the daily BOD JSON instrument master
and provider `instrument_key`; do not use the deprecated CSV master or treat
`exchange_token` as stable identity. Expired futures and options use separate
expired-instrument endpoints and may require Upstox Plus.

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
`(provider, instrument_key, interval, ts)`. Derivative columns are nullable for
equities and indices; no dummy expiry, strike, or contract type is permitted.
The common scalar types and nullability are shared only where every supported
instrument family has coherent semantics; family adapters own interpretation
and validation of their fields. The RELIANCE equity adapter emits every
derivative field as `None`.

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

### DuckDB catalog tables

- `instrument_snapshots`: dated Upstox instrument metadata and source hash.
- `ingestion_runs`: request, timing, code/config version, result, and error class.
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

Higher-timeframe aggregation is a query or derived-artifact concern, not an
ingestion request. Its exact session buckets, partial-bucket policy, and
corporate-action adjustment version require a separately approved
specification before those derived bars are exposed as research facts.

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
- Ensure the design works for one RELIANCE partition, the full Nifty 50 equity
  history, and explicitly bounded derivative collections without code-path
  forks for each scale.

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

No production constant may embed RELIANCE, its ISIN, or a provider instrument
key. Symbols and provider identifiers are mutable catalog data, not application
configuration.

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
- write Parquet through a temporary file and atomic rename;
- record the partition checksum and coverage in DuckDB; and
- resume without downloading already verified partitions.

Implementation order within the storage path is **ARK-31**, then **ARK-43**
(the normalized-to-canonical provider adapter), before **ARK-34**. **ARK-44**
is deferred; it is not an implied part of ARK-31, ARK-43, or ARK-34.

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

## Milestone 4: index and derivative adapters

Enable and test families sequentially without changing the storage core:

1. Nifty 50 and India VIX indices;
2. one active Nifty future;
3. one explicitly selected active Nifty option;
4. an expired future and option when the account entitlement permits; and
5. selected stock futures/options using the same explicit filtering model.

Each adapter must define its instrument discovery source, canonical identity,
endpoint, response validation, and coverage expectations. Open interest remains
nullable because it is not meaningful or available for every family.

Options collection must never mean "all options." Every options job must require
an underlying, expiry range, option type or both sides, and a bounded strike
selection policy. The planner must estimate requests and storage before starting
a large job and require an explicit override above a configured safety limit.

## Acceptance gate

The data phase is complete only when:

- RELIANCE can be downloaded from the earliest available minute history through
  a requested recent date;
- reruns and crash recovery are safe and idempotent;
- coverage and known anomalies are visible rather than silently hidden;
- DuckDB can query one or many instruments directly from Parquet;
- a bounded multi-stock download succeeds without violating provider limits;
- data source, ingestion time, raw/adjusted state, and checksums are traceable;
- no credential or private dataset is tracked by Git;
- index, future, and option adapters pass a small authenticated vertical slice;
- large option jobs cannot start without bounded selection and size estimation;
- measured performance and memory usage satisfy the recorded benchmark budgets;
- provider, storage, validation, and orchestration components can be tested and
  changed independently;
- no trading, indicator, backtest, or AI-agent feature has entered this phase.

## Immediate next action

Implement Milestone 0 only: the credential-safe RELIANCE capability probe. Use
its real response to freeze the shared downloader interfaces and fixtures. The
interfaces must contain no equity-only assumptions, but implementation of other
instrument adapters waits until the RELIANCE storage path passes its correctness
gates.
