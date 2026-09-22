# Plan 04: Public single-symbol preview contract

Status: **APPROVED IMPLEMENTATION CONTRACT**

This document remains authoritative for immutable closed months. The additive
[current-month contract](06-current-month-incremental-data-contract.md) owns
`PROVISIONAL` snapshots, current-day routing, and closed-plus-current report
composition; it does not weaken or reinterpret the rules below.

Depends on [Plan 01](01-data-foundation-and-upstox-ingestion.md) and
[Plan 02](02-request-minimal-ingestion-orchestration.md). The rejected ARK-112
candidate is superseded by this contract, which preserves the Sprint 3 product
scope in one coherent product contract.

## Purpose, value, and boundary

Expose the existing deterministic ingestion coordinator as one installable,
persistent preview for `NSE_EQ` `RELIANCE`: download a closed range to a
durable storage root, prove stored coverage, repeat without an unnecessary
historical request, and query bounded verified candles. The measurable value is
one three-command workflow whose evidence is stable and machine-readable.

A private wrapper script is rejected because it would duplicate admission,
serialization, exit, provenance, and credential boundaries. This preview does
not claim multi-symbol Nifty 50 scale, live-release readiness, strategy logic,
advice, autonomous decisions, or broker execution.

## Product admission and request bounds

`PreviewAdmissionPolicyV1` is an immutable dependency with the exact admitted
pair `segment="NSE_EQ"`, `symbol="RELIANCE"`. The package composition root
constructs and injects it; provider, storage, ingestion, and domain modules do
not contain that product choice. The literal symbol is allowed only as public
preview policy data. It is never a provider identity: no provider identity key,
ISIN, security ID, URL alias, or lookup result is embedded in production code.
Resolution always uses a retained point-in-time instrument snapshot.

Any other pair returns `REJECTED/UNSUPPORTED_PREVIEW_INSTRUMENT` before root,
schedule, snapshot, catalog, credential, limiter, or provider activity. Inputs
are exact types, not silently coerced. Dates are inclusive ISO dates from
`2022-01-01`; every touched month must be closed at the injected
`Asia/Kolkata` date. The application contract always receives an absolute
storage-root `Path`. The CLI supplies `~/SwingTradingAIAssistantData` when the
option is omitted and recursively creates a missing default or explicit root;
`--storage-root /absolute/path` remains the override. Relative paths, literal
unexpanded `~`, globs, and arbitrary catalog paths reject.

The fixed bounds are:

```text
MAX_TOUCHED_MONTHS_V1 = 12
MAX_CATALOG_PARTITIONS_V1 = 12
MAX_QUERY_PARQUET_PATHS_V1 = 12
MAX_QUERY_ROWS_V1 = 10_000
MAX_DAILY_QUERY_ROWS_V1 = 366
MAX_DAILY_SESSION_MINUTES_V1 = 600
MAX_DAILY_INPUT_ROWS_V1 = 219_600
MAX_DAILY_VOLUME_V1 = 9_223_372_036_854_775_807
MAX_PUBLIC_JSON_BYTES_V1 = 8_388_608
MAX_BOD_SNAPSHOT_FETCH_ATTEMPTS_V1 = 1
```

Month count is computed before path or plan allocation. Query accepts only
exact `1m` or `1d` and one to six distinct fields in declaration order from
`ts`, `open`, `high`, `low`, `close`, `volume`. The `1d` path is local
derivation from verified `1m` and retained schedule evidence, never a provider
daily-candle dependency or a hidden `1m` option.

## Shared application contract

These frozen dataclasses and enums are vendor-neutral. CLI, future API, and MCP
adapters call the same services and never call DuckDB, Parquet, a provider, or
`IngestionCoordinator` directly.

```python
@dataclass(frozen=True, slots=True)
class SingleSymbolDownloadRequestV1:
    segment: str
    symbol: str
    from_date: date
    to_date: date
    storage_root: Path


@dataclass(frozen=True, slots=True)
class PublicDownloadRequestV1:
    segment: str
    symbol: str
    from_date: date
    to_date: date


class PublicCommandStatusV1(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class PublicFailureCodeV1(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_PREVIEW_INSTRUMENT = "UNSUPPORTED_PREVIEW_INSTRUMENT"
    UNSUPPORTED_TIMEFRAME = "UNSUPPORTED_TIMEFRAME"
    QUERY_BOUNDS_EXCEEDED = "QUERY_BOUNDS_EXCEEDED"
    SCHEDULE_EVIDENCE_UNAVAILABLE = "SCHEDULE_EVIDENCE_UNAVAILABLE"
    INSTRUMENT_SNAPSHOT_UNAVAILABLE = "INSTRUMENT_SNAPSHOT_UNAVAILABLE"
    INSTRUMENT_NOT_FOUND = "INSTRUMENT_NOT_FOUND"
    INSTRUMENT_AMBIGUOUS = "INSTRUMENT_AMBIGUOUS"
    CREDENTIALS_UNAVAILABLE = "CREDENTIALS_UNAVAILABLE"
    QUERY_CATALOG_UNAVAILABLE = "QUERY_CATALOG_UNAVAILABLE"
    QUERY_RESOURCE_LIMIT_EXCEEDED = "QUERY_RESOURCE_LIMIT_EXCEEDED"
    QUERY_TIMEOUT = "QUERY_TIMEOUT"
    OUTPUT_LIMIT_EXCEEDED = "OUTPUT_LIMIT_EXCEEDED"
    COVERAGE_INSUFFICIENT = "COVERAGE_INSUFFICIENT"
    INGESTION_REJECTED = "INGESTION_REJECTED"
    INGESTION_UNAVAILABLE = "INGESTION_UNAVAILABLE"
    INGESTION_FAILED = "INGESTION_FAILED"
    INGESTION_CANCELLED = "INGESTION_CANCELLED"
    UNCLASSIFIED_FAILURE = "UNCLASSIFIED_FAILURE"


@dataclass(frozen=True, slots=True)
class PublicFailureV1:
    code: PublicFailureCodeV1
    run_failure_code: RunFailureCode | None
    historical_fetch_code: HistoricalFetchCode | None
    failure_category: FailureCategory | None
    validation_reason: ValidationReason | None
    months: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PublicMonthEvidenceV1:
    month: str
    partition_outcome: PartitionOutcome
    reconciliation_reasons: tuple[RequestReason, ...]
    provider_attempt_count: int
    actual_from_ts: datetime | None
    actual_to_ts: datetime | None
    row_count: int | None
    checksum_sha256: str | None
    candle_schema_version: int | None
    validation_policy_version: str | None
    schedule_digest_sha256: str | None
    failure_category: FailureCategory | None
    validation_reason: ValidationReason | None
    historical_fetch_code: HistoricalFetchCode | None


@dataclass(frozen=True, slots=True)
class DownloadPayloadV1:
    request: PublicDownloadRequestV1
    started_at: datetime
    completed_at: datetime
    planned_count: int
    skipped_count: int
    locally_recovered_count: int
    verified_count: int
    failed_count: int
    not_attempted_count: int
    cancelled_count: int
    instrument_snapshot_digest_sha256: str
    instrument_snapshot_retrieved_at: datetime
    instrument_snapshot_attempt_count: int
    historical_attempt_count: int
    months: tuple[PublicMonthEvidenceV1, ...]


PayloadT = TypeVar("PayloadT", covariant=True)


@dataclass(frozen=True, slots=True)
class PublicCommandReportV1(Generic[PayloadT]):
    contract_version: Literal["v1"]
    command: Literal["download", "coverage", "query"]
    status: PublicCommandStatusV1
    failure: PublicFailureV1 | None
    provider_attempt_count: int
    payload: PayloadT | None


DownloadReportV1 = PublicCommandReportV1[DownloadPayloadV1]
```

Coverage freezes its payload in the stored-coverage slice. Query freezes the
following vendor-neutral public types:

```python
class CandleFieldV1(StrEnum):
    TS = "ts"
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    VOLUME = "volume"


@dataclass(frozen=True, slots=True)
class PublicQueryRequestV1:
    segment: str
    symbol: str
    from_date: date
    to_date: date
    timeframe: Literal["1m", "1d"]
    fields: tuple[CandleFieldV1, ...]
    max_rows: int


@dataclass(frozen=True, slots=True)
class PublicQueryRowV1:
    ts: datetime
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None


@dataclass(frozen=True, slots=True)
class QueryPayloadV1:
    request: PublicQueryRequestV1
    row_count: int
    months: tuple[PublicCoverageMonthV1, ...]
    rows: tuple[PublicQueryRowV1, ...]


@dataclass(frozen=True, slots=True)
class DailyQueryPayloadV1:
    request: PublicQueryRequestV1
    calculation_version: Literal["nse-session-ohlcv@v1"]
    adjustment_state: Literal["raw"]
    row_count: int
    months: tuple[PublicCoverageMonthV1, ...]
    rows: tuple[PublicQueryRowV1, ...]


QueryReportV1 = PublicCommandReportV1[QueryPayloadV1 | DailyQueryPayloadV1]
```

The generic parameter is the sole extension point; the common envelope,
failure object, status set, and serializer do not change. Each payload has an
explicit allowlisted serializer. Generic `asdict`, arbitrary mappings, object
dumps, caller SQL, and exception serialization are forbidden.

JSON is UTF-8 with `ensure_ascii=True`, `allow_nan=False`, compact separators,
and one trailing newline. Dates use `YYYY-MM-DD`; UTC instants use
`YYYY-MM-DDTHH:MM:SS.ffffffZ`. Exact top-level key order is
`contract_version`, `command`, `status`, `failure`,
`provider_attempt_count`, `payload`. Encoded output including the newline may
not exceed `MAX_PUBLIC_JSON_BYTES_V1`; overflow returns a complete bounded
`FAILED/OUTPUT_LIMIT_EXCEEDED` report, never a partial payload.

Every declared key is emitted; nullable values use JSON `null` and are never
omitted. Exact nested key order is:

| Object | Exact ordered JSON keys |
| --- | --- |
| `PublicDownloadRequestV1` | `segment`, `symbol`, `from_date`, `to_date` |
| `PublicFailureV1` | `code`, `run_failure_code`, `historical_fetch_code`, `failure_category`, `validation_reason`, `months` |
| `PublicMonthEvidenceV1` | `month`, `partition_outcome`, `reconciliation_reasons`, `provider_attempt_count`, `actual_from_ts`, `actual_to_ts`, `row_count`, `checksum_sha256`, `candle_schema_version`, `validation_policy_version`, `schedule_digest_sha256`, `failure_category`, `validation_reason`, `historical_fetch_code` |
| `DownloadPayloadV1` | `request`, `started_at`, `completed_at`, `planned_count`, `skipped_count`, `locally_recovered_count`, `verified_count`, `failed_count`, `not_attempted_count`, `cancelled_count`, `instrument_snapshot_digest_sha256`, `instrument_snapshot_retrieved_at`, `instrument_snapshot_attempt_count`, `historical_attempt_count`, `months` |
| `PublicQueryRequestV1` | `segment`, `symbol`, `from_date`, `to_date`, `timeframe`, `fields`, `max_rows` |
| `QueryPayloadV1` | `request`, `row_count`, `months`, `rows` |
| `DailyQueryPayloadV1` | `request`, `calculation_version`, `adjustment_state`, `row_count`, `months`, `rows` |
| `PublicQueryRowV1` | only requested fields, in `CandleFieldV1` declaration order |

The internal `SingleSymbolDownloadRequestV1.storage_root` is never copied into
`PublicDownloadRequestV1`. `failure` is null only for success; `payload` is null
for rejected, unavailable, pure-cancelled, or failed commands and is present for
success and partial completion. Every payload count equals the corresponding
ordered month outcomes and all outcome counts sum to `planned_count`.
`provider_attempt_count` equals
`instrument_snapshot_attempt_count + historical_attempt_count` when a payload
exists. Without a payload it remains the truthful bounded attempts observed
before failure. Per-month attempts are copied from the matching
`PartitionResult.provider_attempts`; their sum is
`historical_attempt_count`. The snapshot count is zero or one.

Public output may include only stable enums, counts, dates, digests, schema and
policy versions, and selected candle values. It never includes a run ID, `Path`,
provider key, security ID, canonical path, URL, SQL, raw body, credential,
exception text, private market data, or arbitrary external text.

## One-minute verified query execution

`OneMinuteQueryServiceV1.query()` validates product admission before root or
query activity, acquires exactly one existing-root coverage admission, invokes
`evaluate_under_admission()` once, and consumes every returned verified
partition before releasing that same admission. Coverage and query make zero
provider calls. The public request never contains the storage root; no
selection token, catalog path, Parquet path, provider identity, or security ID
crosses the public boundary.

An incomplete coverage month returns
`INSUFFICIENT_EVIDENCE/COVERAGE_INSUFFICIENT`, retains the ordered public month
evidence, and returns zero rows without opening Parquet. A fully verified query
returns `SUCCEEDED`, including when the selected closed dates contain no bars.
Resource exhaustion returns `FAILED/QUERY_RESOURCE_LIMIT_EXCEEDED`; deadline
expiry returns `FAILED/QUERY_TIMEOUT`; malformed dependency data or any other
execution failure returns bounded `FAILED/UNCLASSIFIED_FAILURE`. Query reports
always have `provider_attempt_count=0`; `PARTIAL` is invalid.

Terminal query status and failure code are exhaustive:

| Status | Exact permitted failure codes |
| --- | --- |
| `REJECTED` | `INVALID_INPUT`, `UNSUPPORTED_PREVIEW_INSTRUMENT`, `UNSUPPORTED_TIMEFRAME`, `QUERY_BOUNDS_EXCEEDED`, `INSTRUMENT_NOT_FOUND`, `INSTRUMENT_AMBIGUOUS` |
| `UNAVAILABLE` | `INSTRUMENT_SNAPSHOT_UNAVAILABLE`, `QUERY_CATALOG_UNAVAILABLE` |
| `FAILED` | `QUERY_RESOURCE_LIMIT_EXCEEDED`, `QUERY_TIMEOUT`, `OUTPUT_LIMIT_EXCEEDED`, `UNCLASSIFIED_FAILURE` |

Every terminal failure has null source-detail fields and `months=[]`. Any other
status/code/detail combination is invalid and the defensive renderer emits
bounded `FAILED/UNCLASSIFIED_FAILURE`. `SUCCEEDED` has no failure and a
payload; `INSUFFICIENT_EVIDENCE` has the exact coverage failure and payload
defined above. Query never returns `PARTIAL` or `CANCELLED`.

The engine opens only the evaluator's verified selections, reopens and pins
each canonical Parquet descriptor under the live admission, and holds all
descriptors until rows are fully materialized. It accepts at most 12 paths and
10,000 output rows. DuckDB is in-memory with one thread, a `256MB` memory
limit, `max_temp_directory_size='0B'`, preserved insertion order disabled, and
known-extension auto-install and auto-load disabled. A daemon interrupter
enforces a five-second query deadline. Output overflow is an error, never
silent truncation.

SQL is an implementation-owned fixed template. The only constructed
identifiers come from `CandleFieldV1`; paths, inclusive IST dates, and
`max_rows + 1` are parameters. Dates become a UTC half-open predicate
`[from_date 00:00 Asia/Kolkata, day_after_to_date 00:00 Asia/Kolkata)`. The
engine reads timestamps as integer epoch microseconds, orders strictly by
`ts`, materializes only numeric candle values, and renders only requested
fields. Caller SQL, expressions, aliases, globs, arbitrary paths, provider
fallback, spilling, and unbounded output are forbidden.

## Session-aware daily OHLCV derivation

`TimeframeQueryServiceV1` reconstructs the internal request and invokes exactly
one service: exact `1d` routes to `DailyQueryServiceV1`; every other value is
handled by the existing one-minute service and therefore retains its typed
unsupported-timeframe behavior. The CLI calls this router once and passes its
report only to the shared query renderer and exit helper.

The daily service admits the product before root activity, validates a maximum
of 12 touched months and `max_rows <= 366`, then holds one existing-root
coverage admission through coverage evaluation, schedule resolution,
descriptor-pinned aggregation, and complete row materialization. It makes zero
provider calls. Incomplete coverage returns the exact ordered month evidence,
zero rows, and `INSUFFICIENT_EVIDENCE/COVERAGE_INSUFFICIENT` without resolving a
schedule or opening Parquet.

Every requested calendar date is classified by the exact retained authoritative
schedule as either a sourced session or closure. Schedule resolution requires
the selection's exact digest, canonical bytes, and `as_of <=` the invocation
cutoff. A session has UTC minute-aligned half-open bounds, maps to the same
`Asia/Kolkata` trade date at both endpoints, and contains at most 600 minutes.
Sessions are strictly ordered, non-overlapping, and bound to the matching
monthly selection digest. Weekday inference, candle-derived calendars,
forward-fill, and an unproven or future schedule are forbidden.

`DuckDBDailyOHLCVEngineV1` consumes at most 12 verified Parquet descriptors,
366 sessions, and 219,600 scheduled input minutes under the same admission. It
uses one fixed parameterized in-memory DuckDB statement with the one-thread,
`256MB`, zero-spill, no-extension, and five-second deadline controls of the
one-minute engine. Every yielded handle is reconstructed as the exact descriptor
type and must carry the corresponding admitted selection in order before its
path is consumed. Each session must contain exactly one distinct candle at every
scheduled minute, including the first minute and the minute immediately before
close. Exact count, distinct count, endpoints, and zero off-grid timestamps
together prove the complete one-minute grid. Missing, duplicate, or off-grid
minutes, contradictory provenance, malformed rows, or inconsistent OHLC values
fail closed and never produce an incomplete daily row.

For each proven complete session, `open` is the first minute open ordered by
timestamp, `high` is the maximum high, `low` is the minimum low, `close` is the
last minute close, and `volume` is the exact integer sum. DuckDB accumulates
volume as `HUGEINT`; a negative or greater-than-signed-64-bit result is
`FAILED/QUERY_RESOURCE_LIMIT_EXCEEDED`, never wraparound or float coercion. The
daily row timestamp is the authoritative session open in UTC. Public payloads
freeze `calculation_version="nse-session-ohlcv@v1"`,
`adjustment_state="raw"`, the verified month provenance, and only requested
fields. Before payload construction the service reconstructs the engine output
and requires exactly one ordered row per authoritative session with
`row.ts == session.open_at`; fewer, extra, shifted, or reordered rows fail
closed. Adjusted-price implementation, indicators, strategies, and additional
timeframes remain out of scope.

Daily reports reuse the exhaustive query status/failure matrix. Deadline
interrupt is `FAILED/QUERY_TIMEOUT`; resource exhaustion is the exact resource
failure; malformed schedule, coverage, or row dependencies fail as bounded
`FAILED/UNCLASSIFIED_FAILURE`. Query never returns `PARTIAL` or `CANCELLED`.

## Exhaustive conversion and exit behavior

The download converter must exhaustively match the current source enums. This
inventory is declaration-ordered and executable; a future or impossible value
fails closed as `FAILED/UNCLASSIFIED_FAILURE` with no payload.

| Source enum | Exact declaration-order members |
| --- | --- |
| `IngestionRunOutcome` | `SUCCEEDED,PARTIAL,FAILED,CANCELLED,ALREADY_RUNNING,REJECTED` |
| `RunFailureCode` | `NONE,UNSUPPORTED_INTERVAL,ALREADY_RUNNING,PARTITION_NOT_CLOSED,SCHEDULE_UNSUPPORTED,STORAGE_UNSAFE,CATALOG_UNAVAILABLE,ATTEMPT_BUDGET_INSUFFICIENT,ATTEMPT_BUDGET_EXHAUSTED,MAPPING_MIGRATION_REQUIRED,RETRY_WAIT_BOUND_EXCEEDED,AUTHENTICATION_FAILED,AUTHORIZATION_FAILED,LOCAL_REPAIR_BLOCKED,CANCELLED,PARTITION_FAILURE` |
| `PartitionOutcome` | `SKIPPED_VERIFIED,RECOVERED_LOCALLY,VERIFIED,FAILED,NOT_ATTEMPTED,CANCELLED` |
| `HistoricalFetchCode` | `AUTHENTICATION_FAILED,AUTHORIZATION_FAILED,PROVIDER_CLIENT,PROVIDER_CONTRACT,PROVIDER_RETRYABLE,ATTEMPT_BUDGET_EXHAUSTED,RETRY_WAIT_BOUND_EXCEEDED,CANCELLED` |
| `FailureCategory` | `INTERRUPTED,EMPTY_RESPONSE,PROVIDER_RETRYABLE,PROVIDER_NON_RETRYABLE,NORMALIZATION_FAILED,VALIDATION_FAILED,WRITE_FAILED,PUBLICATION_FAILED,FILE_MISSING,PATH_INVALID_OR_MISMATCHED,CHECKSUM_INVALID_OR_MISMATCHED,SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,COVERAGE_NOT_PASSED,QUALITY_NOT_PASSED` |
| `ValidationReason` | `NONE,SCHEDULE_DIGEST_MISSING,SCHEDULE_DIGEST_MISMATCH,SCHEDULE_RETAINED_BYTES_INVALID,SCHEDULE_COVERAGE_INCOMPLETE,COVERAGE_EXPECTED_BAR_MISSING,COVERAGE_OFF_SESSION_BAR,QUALITY_INVALID_OHLC,QUALITY_INVALID_VOLUME` |
| `RequestReason` | `MISSING_EVIDENCE,DUPLICATE_EVIDENCE,MANIFEST_NOT_VERIFIED,FILE_MISSING,PATH_INVALID_OR_MISMATCHED,CHECKSUM_INVALID_OR_MISMATCHED,SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,RECORDED_RANGE_MISMATCHED,COVERAGE_NOT_PASSED,QUALITY_NOT_PASSED` |

Conversion has two separate steps. First, validate the source report and map its
`RunFailureCode` to one public failure detail. Second, select status from the
validated outcome without discarding that detail. Domain `PARTIAL` always
becomes public `PARTIAL`, regardless of its non-`NONE` failure code. `NONE` is
valid only with domain `SUCCEEDED` and becomes public `SUCCEEDED` with no
failure. Pure `CANCELLED` becomes public `CANCELLED`. Other outcomes use the
failure-detail class shown below. A combination rejected by the existing
`IngestionReport` invariant, or absent from these tables, fails closed as
`FAILED/UNCLASSIFIED_FAILURE` with no payload.

`NOT_ATTEMPTED` is serialized exactly, counts only as not attempted, and never
inherits final-manifest facts. A zero-request repeat is `SUCCEEDED`, has zero
historical attempts, and every month is `SKIPPED_VERIFIED` or
`RECOVERED_LOCALLY`.

Output overflow is rendered through a dedicated constant-size serializer, not
the normal payload serializer: command is retained, status is `FAILED`, failure
is `OUTPUT_LIMIT_EXCEEDED` with all source-enum fields null and `months=[]`,
the truthful top-level attempt count is retained, and payload is null.

The run/result shape is also closed: `SUCCEEDED` requires every result completed
(`SKIPPED_VERIFIED`, `RECOVERED_LOCALLY`, or `VERIFIED`); `ALREADY_RUNNING`
requires all planned results `NOT_ATTEMPTED`; `REJECTED` has no completed
result; `FAILED` has no completed or cancelled result and leaves later work
`NOT_ATTEMPTED`; pure `CANCELLED` has no completed result; `PARTIAL` requires at
least one completed result. Conflicting counts, result order, nested lifecycle
facts, or enum combinations fail closed with no payload.

| Public status | Exit code |
| --- | --- |
| `SUCCEEDED` | 0 |
| `REJECTED` | 2 |
| `PARTIAL` | 3 |
| `INSUFFICIENT_EVIDENCE` | 3 |
| `UNAVAILABLE` | 4 |
| `FAILED` | 5 |
| `CANCELLED` | 130 |

For download, exhaustive failure-detail conversion is:

| Source code | Public failure detail class / code |
| --- | --- |
| `NONE` | `SUCCESS` / no `PublicFailureV1` |
| `UNSUPPORTED_INTERVAL`, `PARTITION_NOT_CLOSED`, `ATTEMPT_BUDGET_INSUFFICIENT` | `REJECTED` / `INGESTION_REJECTED` |
| `SCHEDULE_UNSUPPORTED` | `INSUFFICIENT` / `SCHEDULE_EVIDENCE_UNAVAILABLE` |
| `ALREADY_RUNNING`, `STORAGE_UNSAFE`, `CATALOG_UNAVAILABLE`, `AUTHORIZATION_FAILED` | `UNAVAILABLE` / `INGESTION_UNAVAILABLE` |
| `AUTHENTICATION_FAILED` | `UNAVAILABLE` / `CREDENTIALS_UNAVAILABLE` |
| `ATTEMPT_BUDGET_EXHAUSTED`, `MAPPING_MIGRATION_REQUIRED`, `RETRY_WAIT_BOUND_EXCEEDED`, `LOCAL_REPAIR_BLOCKED`, `PARTITION_FAILURE` | `FAILED` / `INGESTION_FAILED` |
| `CANCELLED` | `CANCELLED` / `INGESTION_CANCELLED` |

After source validation, status selection is exactly:

| Domain outcome | Failure requirement | Public status |
| --- | --- | --- |
| `SUCCEEDED` | exact `NONE` / `SUCCESS` | `SUCCEEDED` |
| `PARTIAL` | any exact non-`NONE` mapped detail | `PARTIAL`; retain that mapped public failure code |
| `CANCELLED` | exact `CANCELLED` | `CANCELLED` |
| `ALREADY_RUNNING`, `REJECTED`, `FAILED` | non-`NONE` `REJECTED` detail | `REJECTED` |
| `ALREADY_RUNNING`, `REJECTED`, `FAILED` | non-`NONE` `INSUFFICIENT` detail | `INSUFFICIENT_EVIDENCE` |
| `ALREADY_RUNNING`, `REJECTED`, `FAILED` | non-`NONE` `UNAVAILABLE` detail | `UNAVAILABLE` |
| `ALREADY_RUNNING`, `REJECTED`, `FAILED` | non-`NONE` `FAILED` detail | `FAILED` |
| any other combination, including non-`SUCCEEDED`/`NONE` or non-`CANCELLED` `CANCELLED` | invalid | `FAILED/UNCLASSIFIED_FAILURE`, no payload |

Nested `HistoricalFetchCode`, `FailureCategory`, `ValidationReason`, and
`RequestReason` never override the run status. They are retained only when
consistent with the source report. Authentication/authorization historical
codes must agree with their run code; provider/client/retry codes must agree
with an ingestion-failure run code; historical cancellation must agree with
run cancellation. Every other disagreement fails closed. This preserves the
mapped cause on partial work without turning partial work into failure.

## Instrument snapshot catalog migration

This document owns the historical preview boundary through catalog v2 only.
The frozen v3 point-in-time universe migration, including its DDL, checksum,
compatibility and rollback rules, is owned by Plan 05; it is not a redesign of
the public-preview contract.

Catalog v1 remains immutable: migration ID `swing-trading-catalog-v1`, version
`1`, checksum
`1bf5a64839169e61cdb839bc778131b2c0876da2d818537644677af861da006d`.
Catalog v2 appends migration ID
`swing-trading-catalog-v2-instrument-snapshots`, version `2`, checksum
`b457af377ccc986b47ca006a385ea538911dd03d1be8d066317fa09cfbbd9878`.
Its checksum input is exactly 1,606 UTF-8 bytes after `.strip()`, with LF
separators and no trailing newline:

```sql
CREATE TABLE instrument_snapshots (
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    source VARCHAR NOT NULL CHECK (
        regexp_full_match(source, '[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
    ),
    observation_date DATE NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    observation_sha256 VARCHAR NOT NULL CHECK (
        regexp_full_match(observation_sha256, '[0-9a-f]{64}')
    ),
    compressed_sha256 VARCHAR NOT NULL CHECK (
        regexp_full_match(compressed_sha256, '[0-9a-f]{64}')
    ),
    decompressed_sha256 VARCHAR NOT NULL CHECK (
        regexp_full_match(decompressed_sha256, '[0-9a-f]{64}')
    ),
    compressed_byte_count BIGINT NOT NULL CHECK (
        compressed_byte_count BETWEEN 0 AND 4000000
    ),
    decompressed_byte_count BIGINT NOT NULL CHECK (
        decompressed_byte_count BETWEEN 0 AND 50000000
    ),
    relative_object_path VARCHAR NOT NULL CHECK (
        relative_object_path = 'instrument_snapshots/sha256=' || compressed_sha256 || '/snapshot.json.gz'
        AND length(relative_object_path) <= 128
    ),
    relative_metadata_path VARCHAR NOT NULL CHECK (
        relative_metadata_path = 'instrument_snapshots/sha256=' || compressed_sha256 || '/observations/sha256=' || observation_sha256 || '.json'
        AND length(relative_metadata_path) <= 256
    ),
    etag VARCHAR CHECK (
        etag IS NULL OR regexp_full_match(etag, '[ -~]{1,512}')
    ),
    last_modified VARCHAR CHECK (
        last_modified IS NULL OR regexp_full_match(last_modified, '[ -~]{1,512}')
    ),
    PRIMARY KEY (source, retrieved_at, observation_sha256)
);
```

An empty catalog is created directly at v2. A valid legacy v1 catalog upgrades
in one transaction: validate the exact v1 signature and row, execute only the
v2 DDL, append only the v2 row, validate the exact v2 signature and ordered
ledger, then commit. V2 is exactly the prior three tables plus
`instrument_snapshots`; any extra relation, view, migration-ledger row, column,
constraint, or user index rejects. Valid populated `partitions` and
`ingestion_runs` rows are domain data, not schema-signature rows: migration
preserves them byte-for-byte and never restricts their count. Mixed/partial
signatures reject. V1 is never recomputed, updated, or deleted.

The immutable compressed object path is
`instrument_snapshots/sha256=<digest>/snapshot.json.gz`. Each retrieval also
publishes a canonical immutable observation sidecar whose ordered JSON fields
are `schema_version`, `source`, `observation_date`, `retrieved_at`,
`compressed_sha256`, `decompressed_sha256`, `compressed_byte_count`,
`decompressed_byte_count`, `relative_object_path`, `etag`, `last_modified`.
Every key is emitted in that order. Encoding is UTF-8 JSON with
`ensure_ascii=True`, `allow_nan=False`, compact separators, and exactly one
trailing newline. `schema_version` is integer `1`; `observation_date` is
`YYYY-MM-DD`; `retrieved_at` is UTC
`YYYY-MM-DDTHH:MM:SS.ffffffZ`; nullable headers are JSON `null`; non-null
headers match printable ASCII `[ -~]{1,512}`. The encoded ceiling is
`MAX_OBSERVATION_JSON_BYTES_V1 = 4096`, including the newline. The SHA-256 of
these exact bytes including the newline is `observation_sha256`; its path is
`instrument_snapshots/sha256=<digest>/observations/sha256=<observation_sha256>.json`.
Thus identical content can retain multiple truthful point-in-time retrievals.

Under the exclusive preparation lease, the only temporary files are
`.snapshot.json.gz.tmp` beside the object and
`.sha256=<observation_sha256>.json.tmp` beside the sidecar, plus
`.pending-observation-v1.json.tmp` beside the fixed recovery journal
`instrument_snapshots/pending-observation-v1.json`. On retry, an exact temporary
path is removed only after descriptor-relative no-follow checks prove it is a
regular, root-owned, restrictive file within the expected directory; unsafe
evidence fails closed. Temporary files are never provenance. Final files use
exclusive creation, bounded write, fsync, close, reopen/hash verification,
same-filesystem no-clobber publication, and parent-directory fsync. No glob,
random suffix, directory scan, broad cleanup, overwrite, or silent repair is
allowed.

The recovery journal is the single bounded discovery mechanism for a catalog
commit interrupted after a validated response. It is canonical JSON with the
exact `InstrumentSnapshotMetadataV1` field order, encoding rules, and 4,096-byte
ceiling; it contains no response body or secret. The journal is published and
fsynced before the object. Its exact paths are then the only paths recovery may
inspect. After the identical catalog row commits, recovery unlinks the journal
and fsyncs `instrument_snapshots`. A journal with no durable object is cleared
before the one permitted fresh response; a journal with a valid object may
publish or validate its canonical sidecar without refetch; a journal-identified
unsafe temp or mismatch fails before provider activity. This fixed journal is
required because an absent catalog row cannot reveal content-addressed paths
without an otherwise-forbidden directory scan.

The crash/retry matrix is exhaustive:

| Durable state | Retry behavior |
| --- | --- |
| `EMPTY` | after one permitted fresh BOD response, publish journal, object, sidecar, row, then clear journal |
| `SAFE_TEMP_ONLY` | remove only the exact proven-safe temps, fsync, then follow `EMPTY` |
| `UNSAFE_TEMP` | typed corruption; do not read, remove, replace, fetch, or mutate |
| `OBJECT_ONLY` | when identified by the canonical journal, validate the object and publish the journal-derived canonical sidecar and row without refetch; an undiscoverable orphan without a journal is never scanned or adopted |
| `OBJECT_AND_SIDECAR` | when identified by the canonical journal, validate canonical sidecar, both digests/counts/paths, and insert the exact sidecar-derived row without refetch or rewrite |
| `COMMIT_UNKNOWN` | reopen; identical row is success, absent row follows `OBJECT_AND_SIDECAR`, divergent row is corruption |
| `COMPLETE` | valid files and identical row are idempotent success |
| `MISMATCH` | row/file missing, corrupt, unsafe, or mismatched, or sidecar/object disagreement: typed corruption; no refetch, delete, overwrite, or silent repair |

Any file or directory fsync failure returns outcome unknown. The next invocation
uses only the resulting durable-state row above. Local object timestamps never
become retrieval provenance, and no sidecar is created without a corresponding
validated provider response or a previously durable canonical sidecar.

Same latest `retrieved_at` with different observation or content digests is
ambiguous. Complete v2 signature validation precedes commit. Empty creation and
populated v1 upgrade are transactional; a DDL, ledger, validation, or injected
fault rolls back, and reopening must expose the exact prior v1 signature and all
prior domain rows.

## Preparation boundary and provenance

The preparation slice owns four typed ports: a provenance-complete NSE schedule
source; one bounded no-credential BOD snapshot source; immutable snapshot
retention/cataloging; and offline equity resolution. The orchestrator performs:

1. Validate admission, dates, root syntax, and bounds in memory.
2. Acquire or accept the bounded authoritative schedule bytes and completely
   validate their canonical form, provenance, closed-month coverage, and digest
   in memory. Invalid schedule evidence creates no lock or storage state.
3. Acquire the protected-root lease and retain the exact already-validated
   schedule bytes.
4. Reuse a valid current-date snapshot or make at most one bounded BOD request;
   retain the compressed response immutably and append its metadata row.
5. Resolve the latest unambiguous retained snapshot with `retrieved_at <=` the
   injected invocation time. A snapshot fetched by this invocation may instead
   use its exact acquisition timestamp only when it is no later than a trusted
   post-fetch clock reading and its IST `observation_date` still equals the
   invocation date; injected future evidence and midnight-crossing evidence fail
   closed. Release the preparation lease and build one
   `IngestionCommand`.
6. Call `IngestionCoordinator.run` exactly once. It reacquires the lease and
   re-proves the retained schedule before catalog, credential, limiter,
   historical-provider, raw, manifest, or Parquet work.

Schedule evidence retains source, source release, UTC release/as-of time,
`Asia/Kolkata` timezone, covered dates, every sourced session/closure,
canonical bytes, and digest. Weekday inference, candle-derived calendars, and
silent holiday assumptions are forbidden. Missing, stale, corrupt, or
contradictory evidence fails closed.

The default CLI application composition may accept these exact canonical bytes
from an explicit absolute `--schedule-file`. It opens only a bounded, regular,
non-symlink, non-group/world-writable file; validates the exact canonical
representation before storage activity; and never embeds or infers a calendar.
Omitting or invalidating the file preserves `SCHEDULE_EVIDENCE_UNAVAILABLE`.

Snapshot metadata retains schema version, fixed bounded source ID,
`observation_date`, UTC `retrieved_at`, compressed and decompressed SHA-256,
bounded byte counts, content-addressed relative path, and sanitized bounded
`ETag`/`Last-Modified` when present. Retrieval time is provenance, not an
invented provider release time. Resolution requires one exact NSE/NSE_EQ/EQ
identity with stable security identity and no derivative fields. Zero matches
is `INSTRUMENT_NOT_FOUND`; multiple/conflicting matches are
`INSTRUMENT_AMBIGUOUS`; unavailable acquisition is
`INSTRUMENT_SNAPSHOT_UNAVAILABLE`. Coverage and query never fetch; they use
retained evidence and report zero provider attempts.

Credentials remain environment-only and are read lazily only after
reconciliation proves historical acquisition is required. No token, session,
customer identifier, TOTP, login automation, private response, or generated
dataset enters source control, fixtures, logs, reports, or error text.

## Implementation and acceptance

Implementation must preserve the existing coordinator, immutable Parquet,
metadata-only DuckDB, manifest, schedule, retry, cancellation, and
bounded-resource rules.

Acceptance requires executable tests proving admission before side effects,
exact serializer allowlists/order/ceiling, exhaustive enum conversion including
`NOT_ATTEMPTED`, status/exit precedence, exact v1-to-v2 migration and rollback,
orphan recovery, corrupt refusal, content-addressed no-clobber retention,
schedule-first mutation order, point-in-time offline resolution, lazy
credentials, zero provider attempts on repeat/read paths, bounded failures, no
provider identity leakage, and no broker execution.
Daily acceptance additionally proves authoritative regular and special-session
grouping, timezone boundaries, complete/missing/duplicate minutes, integer
volume overflow, raw/calculation provenance, deadline cleanup, exact `1d` CLI
routing, zero provider attempts, and a read-only disposable-root smoke.

## Issue #187 successor crosswalk

`current-supplied-cohort-research-packet@v5` and the explicit
`market-data research-current --contract-version v2` path are additive current
research successors. They do not alter this preview's request, response, reader,
or retained bytes.
