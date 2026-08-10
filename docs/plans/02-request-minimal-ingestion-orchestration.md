# Request-minimal one-minute ingestion orchestration

Status: **Accepted — ARK-49, with owner-approved ARK-58 completeness update**
Scope: Sprint 1 RELIANCE NSE equity one-minute vertical slice
Depends on: ARK-32, ARK-33, ARK-34, ARK-35, ARK-40, ARK-42, and ARK-43

## Purpose

Freeze the application boundary that coordinates monthly planning, trustworthy
local evidence, bounded Upstox fetching, canonical validation, atomic Parquet
publication, and DuckDB lifecycle evidence. The contract must ensure that:

- all desired partitions are reconciled locally before credentials or an
  authenticated candle request are used;
- verified or locally recoverable work causes zero Upstox requests;
- interruption resumes at one instrument-month rather than restarting the
  requested range;
- every provider attempt is bounded, traceable, and sanitized; and
- only canonical one-minute acquisition can reach the provider.

This specification does not change the architecture freeze or trading logic.
It makes ARK-36 implementation-ready by replacing one cross-cutting task with
ordered atomic children.

## Non-goals

- CLI, API, MCP, or agent-harness adapters.
- Multi-instrument or multi-account concurrency.
- Instrument-master refresh or trading-calendar acquisition.
- Customer login, TOTP, token persistence, or credential automation.
- Higher-timeframe provider acquisition or higher-timeframe aggregation.
- Acquisition of an open calendar month or an incrementally mutable partial
  month. Sprint 1 persists only canonical, closed calendar months.
- Catalog, manifest, canonical candle, or Parquet schema redesign.
- DuckDB candle storage, mutable Parquet overwrite, or broker order placement.
- Market-regime, indicator, strategy, backtesting, or trading-suggestion work.

## Existing contracts and ownership

The orchestrator composes, but does not redefine, these approved boundaries:

- `monthly_request_planner.py` owns ordered, non-overlapping one-minute
  calendar-month plans and rejects higher-timeframe acquisition.
- `partition_reconciliation.py` owns the pure `SKIP` or `REQUEST` decision from
  supplied manifest and physical evidence.
- `manifest_lifecycle.py` owns immutable `IN_PROGRESS`, `VERIFIED`, and
  `FAILED` transitions and their exact failure categories.
- `partition_publication.py` owns no-clobber, same-filesystem atomic Parquet
  publication and sealed publication evidence.
- `catalog.py` owns one connection, exact replay, current manifests, and
  immutable terminal attempt history.
- `http.py` owns bounded HTTP transport and stable provider error categories.
- `historical.py` owns the Upstox Historical Candle V3 request and response
  adapter.
- `normalization.py`, `upstox_canonical.py`, and `parquet.py` own their existing
  provider, logical, and physical schema boundaries.

Dependency direction is one-way:

```text
range coordinator
  -> monthly planner
  -> local partition observer and repair port
  -> pure reconciliation
  -> single-partition lifecycle executor
       -> bounded provider fetch port and shared account limiter
       -> normalization and canonicalization
       -> versioned equity-month validation policy
       -> atomic publisher
       -> pure manifest lifecycle and DuckDB catalog
```

Provider, HTTP, validation, publication, catalog, and domain modules never
import the coordinator. Future CLI, API, and MCP adapters wrap the same typed
application contract.

## Typed range contract

The implementation uses immutable, exact-runtime-type domain objects. Names
below freeze responsibility; implementation may place closely related models
in the same application module without changing ownership.

```python
@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts_per_partition: int = 3
    base_backoff: timedelta = timedelta(seconds=1)
    max_backoff: timedelta = timedelta(seconds=8)
    max_retry_after: timedelta = timedelta(seconds=60)
    # One invocation-wide budget for every wait: limiter admission, account
    # deferral, and retry backoff. It is not a per-request budget.
    max_total_wait: timedelta = timedelta(seconds=120)


@dataclass(frozen=True, slots=True)
class IngestionCommand:
    instrument: Instrument
    from_date: date
    to_date: date
    interval: str
    storage_root: Path
    expected_sessions: ExpectedSessionSchedule
    validation_policy_version: str
    retry_policy: RetryPolicy
    max_total_provider_attempts: int


class IngestionRunOutcome(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ALREADY_RUNNING = "ALREADY_RUNNING"
    REJECTED = "REJECTED"


class RunFailureCode(StrEnum):
    NONE = "NONE"
    UNSUPPORTED_INTERVAL = "UNSUPPORTED_INTERVAL"
    ALREADY_RUNNING = "ALREADY_RUNNING"
    PARTITION_NOT_CLOSED = "PARTITION_NOT_CLOSED"
    SCHEDULE_UNSUPPORTED = "SCHEDULE_UNSUPPORTED"
    STORAGE_UNSAFE = "STORAGE_UNSAFE"
    CATALOG_UNAVAILABLE = "CATALOG_UNAVAILABLE"
    ATTEMPT_BUDGET_INSUFFICIENT = "ATTEMPT_BUDGET_INSUFFICIENT"
    ATTEMPT_BUDGET_EXHAUSTED = "ATTEMPT_BUDGET_EXHAUSTED"
    MAPPING_MIGRATION_REQUIRED = "MAPPING_MIGRATION_REQUIRED"
    RETRY_WAIT_BOUND_EXCEEDED = "RETRY_WAIT_BOUND_EXCEEDED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    LOCAL_REPAIR_BLOCKED = "LOCAL_REPAIR_BLOCKED"
    CANCELLED = "CANCELLED"
    PARTITION_FAILURE = "PARTITION_FAILURE"


class PartitionOutcome(StrEnum):
    SKIPPED_VERIFIED = "SKIPPED_VERIFIED"
    RECOVERED_LOCALLY = "RECOVERED_LOCALLY"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class PartitionResult:
    plan: PlannedInstrumentMonth
    outcome: PartitionOutcome
    reconciliation_reasons: tuple[RequestReason, ...]
    ingestion_run_id: str | None
    provider_attempts: int
    final_manifest: PartitionManifest | None
    failure_category: FailureCategory | None
    error_code: str | None


@dataclass(frozen=True, slots=True)
class IngestionReport:
    outcome: IngestionRunOutcome
    failure_code: RunFailureCode
    results: tuple[PartitionResult, ...]
    planned_count: int
    skipped_count: int
    locally_recovered_count: int
    provider_attempt_count: int
    verified_count: int
    failed_count: int
    not_attempted_count: int
    cancelled_count: int
    started_at: datetime
    completed_at: datetime
```

`interval` must be the exact built-in string `"1m"` before planning. The
instrument must be a currently resolved NSE equity instrument supplied through
the existing master-catalog boundary; production code contains no RELIANCE
instrument-key, ISIN, or symbol constant. The storage root must already be a
protected real directory under the ARK-34/35 contract.

The requested dates select desired data, not physical partition boundaries.
After the existing planner identifies the touched months, the coordinator
constructs one canonical acquisition plan per touched month whose dates are the
first and last calendar day. Every plan must be a closed month: its last
calendar day is strictly earlier than the injected current local date and the
authoritative schedule covers the complete month. An open/current month is
`REJECTED/PARTITION_NOT_CLOSED` before storage mutation, credentials, limiter,
or HTTP. Expanding historical edge ranges is intentional: it uses the same one
provider call while ensuring every later overlapping request has one reusable
physical identity. Query consumers may select the originally requested dates
from that canonical month.

The command value is created through a validating constructor; malformed exact
types never enter orchestration. For every valid command, expected operational
conditions return a typed `IngestionReport` rather than an exception. Counts in
the report must equal the ordered result tuple. `SUCCEEDED` means every result
is skipped, locally recovered, or verified. Timestamps are injected UTC-aware
clock values. `error_code` is a stable sanitized code, never an exception, SQL
string, token, URL, response body, path, or instrument value.

### Exhaustive run outcome and failure-code table

`completed` means `SKIPPED_VERIFIED`, `RECOVERED_LOCALLY`, or `VERIFIED`. The
coordinator applies the first matching row by precedence and records one result
for every planned month in plan order. `failure_code` is the immediate run-stop
reason except that ordinary partition failures use `PARTITION_FAILURE`.

| Condition and precedence | Results and terminal state | Run outcome / failure code | Provider requests |
| --- | --- | --- | --- |
| Preflight rejects interval, closed-month, schedule, protected root, or minimum attempt budget before any `IN_PROGRESS` | all planned results `NOT_ATTEMPTED` | `REJECTED` / exact code (`UNSUPPORTED_INTERVAL`, `PARTITION_NOT_CLOSED`, `SCHEDULE_UNSUPPORTED`, `STORAGE_UNSAFE`, or `ATTEMPT_BUDGET_INSUFFICIENT`) | 0 |
| Root lease is held | all planned results `NOT_ATTEMPTED` | `ALREADY_RUNNING` / `ALREADY_RUNNING` | 0 |
| Cancellation before any result becomes terminal or any partition enters `IN_PROGRESS` | all planned results `CANCELLED`; no manifest | `CANCELLED` / `CANCELLED` | 0 |
| Cancellation after a partition entered `IN_PROGRESS`, with no earlier completed result | current `CANCELLED`, earlier failures retained, later `NOT_ATTEMPTED`; best-effort current manifest `FAILED/INTERRUPTED` | `CANCELLED` / `CANCELLED` | 0 or more |
| Same in-flight cancellation with one or more earlier completed results | completed results retained, current `CANCELLED`, later `NOT_ATTEMPTED` | `PARTIAL` / `CANCELLED` | 0 or more |
| Cancellation between partitions after one or more terminal results but before the next `IN_PROGRESS` | all earlier completed/failed results retained; every remaining unstarted plan `CANCELLED` with no manifest | `PARTIAL` / `CANCELLED` if any earlier result completed, otherwise `CANCELLED` / `CANCELLED` | bounded attempts already made; no new request |
| Cancellation after every planned result is terminal | no result, count, manifest, or request changes | normal all-result precedence (`SUCCEEDED`, `PARTIAL`, or `FAILED`) | unchanged |
| Run-fatal authentication, authorization, catalog, unsafe-local-repair, mapping migration, retry-wait-bound, or runtime total-attempt-budget exhaustion before a completed result | affected failure retained, later `NOT_ATTEMPTED` | `FAILED` / exact fatal code, including `ATTEMPT_BUDGET_EXHAUSTED` | 0 or bounded attempts already made; no later request |
| Same run-fatal condition after one or more completed results | completed and failed results retained, later `NOT_ATTEMPTED` | `PARTIAL` / exact fatal code | bounded attempts already made; no later request |
| After one or more provider attempts, Child H escapes a non-catalog clock, lifecycle-contract, malformed-return, or generic exception before safe terminal persistence | affected result `FAILED` with `PARTITION_FAILURE`, exact current-invocation run ID, exact provider-attempt delta, and the safely readable current-run manifest even when it remains `IN_PROGRESS`; earlier results retained and later plans `NOT_ATTEMPTED` | `FAILED` / `PARTITION_FAILURE`, or `PARTIAL` / `PARTITION_FAILURE` when an earlier result completed | bounded attempts already made; charged wait ledger retained; no later request |
| All desired partitions were attempted and failed ordinarily, with no completed result or run-fatal stop | every result `FAILED` | `FAILED` / `PARTITION_FAILURE` | bounded attempts |
| One or more ordinary terminal failures and one or more completed results, with no run-fatal stop | every plan has its actual completed or failed result | `PARTIAL` / `PARTITION_FAILURE` | bounded attempts |
| Every desired partition completes locally or by verified acquisition | every result completed | `SUCCEEDED` / `NONE` | 0 or more |

Only cancellation before any terminal result or the first `IN_PROGRESS`
transition is zero-request. An in-flight cancellation may follow a sent request,
publication, or local recovery work. A local `SKIPPED_VERIFIED` result is
terminal, so later cancellation follows the between-partition row and preserves
that skip. Between-partition cancellation changes every unstarted result to
`CANCELLED`, not `NOT_ATTEMPTED`; after-terminal cancellation is observationally
irrelevant. Counts always equal the final result tuple. `NOT_ATTEMPTED` never
means failure, and no row permits a later provider request after a run-fatal
stop. `NONE` is exclusive to `SUCCEEDED`.

The post-attempt Child H exception row is a run stop, not an ordinary isolated
terminal failure. It never fabricates a terminal manifest or failure category.
The result mirrors a manifest failure category only when safely read terminal
evidence proves one; an exact current-run `IN_PROGRESS` manifest remains valid
failure provenance for this row. Provider attempts are the delta charged during
the current Child H call and are never synthesized as zero after a request. The
single invocation wait ledger remains charged internally; this contract does
not add a public wait field.

## Authoritative session schedule and validation identity

`ExpectedSessionSchedule` is immutable and contains an exact schedule schema
version, provider/source name, source release/version, UTC-aware `as_of`,
`Asia/Kolkata` timezone identifier, the covered first and last calendar dates,
and ordered session and closure evidence. Each session contains its local trade
date, UTC-aware open instant, UTC-aware exclusive close instant, and session
kind. Each closure contains its local date and a nonempty source reason.

The frozen v1 schedule remains readable for existing evidence, but it represents
holidays only by absence and therefore cannot prove that a trading session was
not accidentally omitted. New ARK-58 commands require `schedule-digest-v2`.
For every calendar date in every requested full closed month, v2 contains
exactly one matching session or one sourced closure. Sessions and closures are
unique, strictly ordered, inside the declared coverage, and cannot overlap.
Sessions remain minute-aligned. Missing dates, duplicate dates, a session and
closure on the same date, empty closure reasons, future evidence, open months,
or incomplete first-to-last-day coverage fail with `SCHEDULE_UNSUPPORTED`
before lease acquisition, storage/catalog mutation, credentials, limiter use,
or HTTP. The tool never guesses weekends, holidays, or special sessions.

Schedule digest schemas use UTF-8 encoding of
`json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))`.
The frozen v1 `value` has only `schema_version`, `source`, `source_release`, `as_of`,
`timezone`, `covered_from`, `covered_to`, and `sessions`; each session has only
`trade_date`, `open_at`, `close_at`, and `kind`. `schema_version` is the JSON
integer `1`. The v2 `value` adds only `closures`; each closure has only
`trade_date` and `reason`, and `schema_version` is the JSON integer `2`.
`source`, `source_release`, `timezone`, `kind`, and v2 closure reasons are nonempty
ASCII strings, and `timezone` is exactly `Asia/Kolkata`. Instants are UTC RFC
3339 with a literal `Z` and exactly six fractional digits; dates are `YYYY-MM-DD`. No
whitespace, omitted field, alternate timestamp spelling, map insertion order,
or Unicode normalization is accepted. The digest is lowercase SHA-256 hex of
precisely those bytes.

`ScheduleEvidenceStore` retains the bytes at protected-root relative
`calendar-schedules/sha256/<digest>.json`. It is content-addressed, no-follow,
no-clobber, atomically published, and never overwritten or deleted here. Before
any `IN_PROGRESS`, the coordinator validates the supplied command schedule and
proves that retained bytes equal it. If an object is missing, Child D may
first-publish or restore it only from supplied canonical versioned schedule-digest
bytes whose lowercase SHA-256 exactly equals the referenced command or manifest
policy digest. Reads verify
path shape, regular-file identity, byte ceiling, digest, and versioned schedule-digest
parsing. The exact retained-byte ceiling is 1,000,000 bytes. A missing command
object without matching supplied bytes, and every present unreadable, corrupt,
unequal, or digest-mismatched command object, is
`REJECTED/SCHEDULE_UNSUPPORTED` before provider activity. A missing or bad
manifest-bound object fails closed under the lifecycle mapping below. Present bad
evidence is never overwritten or replaced. A manifest-bound object is never
substituted from a current schedule: restoration is permitted only from
identical supplied canonical bytes for that manifest digest. No catalog or
history inspection decides this behavior.

`validation_policy_version` is not a free label: the existing manifest persists
`<policy-name>@<policy-version>+sessions-sha256:<64-lower-hex>`. Recovery extracts
that digest and looks up exactly those retained bytes; it never substitutes the
current command schedule. A verified manifest that cannot re-prove coverage from
its retained schedule is invalidated with existing `COVERAGE_NOT_PASSED`; when
coverage passes and quality fails it uses `QUALITY_NOT_PASSED`. For a fresh
`IN_PROGRESS` attempt, any failed session evidence is existing
`VALIDATION_FAILED`, with a stable report/event reason from
`SCHEDULE_DIGEST_MISSING`, `SCHEDULE_DIGEST_MISMATCH`,
`SCHEDULE_RETAINED_BYTES_INVALID`, `SCHEDULE_COVERAGE_INCOMPLETE`,
`COVERAGE_EXPECTED_BAR_MISSING`, `COVERAGE_OFF_SESSION_BAR`,
`QUALITY_INVALID_OHLC`, or `QUALITY_INVALID_VOLUME`. Existing manifest and
catalog schemas gain no field: that reason is bounded report/event evidence.
`source_version` continues to identify the Upstox adapter/request contract, not
the trading calendar.

## Physical identity and mutable provider aliases

Physical identity is exactly `(provider, exchange, segment, instrument_type,
security_id, interval, year, month)`. It excludes requested edge dates,
`symbol`, and `instrument_key`: `security_id` is stable, while the latter two
are mutable Upstox acquisition aliases.

Manifest-present local recovery uses one internally consistent stored
provider/key/symbol/security-ID mapping from its plan and artifact. Without a
manifest, recovery derives one mapping from bounded stored canonical rows and
requires all rows to agree before writing recovery evidence for the current
full-month physical identity. A mutable-alias difference from the current
command is neither a request nor quarantine reason; a valid verified old-mapping
artifact continues to `SKIP`.

The current resolved mapping is used only for a fresh HTTP request and fresh
canonicalization. Since `retry_manifest` retains the old plan and publication
requires plan aliases to match rows, a failed/invalidated manifest with obsolete
stored aliases cannot migrate safely **only when a fresh provider request and
publication are actually required**. In that case return zero-request run-fatal
`FAILED/MAPPING_MIGRATION_REQUIRED` before retry until a separately approved
mapping-migration contract exists. A valid final with its internally consistent
stored aliases recovers locally regardless of current aliases. A manifest-absent
missing or invalid final may use the current mapping for a fresh request.
Alias-only change never quarantines or redownloads data.

For that mapping stop, the affected `PartitionResult` is `FAILED` with
`failure_category=None`, `error_code="MAPPING_MIGRATION_REQUIRED"`, and its
unchanged existing manifest (if any); no ARK-40 transition or catalog schema
change is invented. The run-level `RunFailureCode` is the same value.

## Injected ports

- `StorageRootLease.try_acquire(root) -> LeaseResult` owns one stable
  `.ingestion.lock` regular file beneath the protected root. It opens with
  no-follow/close-on-exec protections, verifies the descriptor identity and
  restrictive ownership/mode, and takes a non-blocking exclusive OS advisory
  lock held until the complete invocation closes. The file is never deleted.
  Lock contention returns `ALREADY_RUNNING`; it never guesses whether another
  process is stale.
- `ProviderSessionFactory.open() -> ProviderSession` is owned by the range
  coordinator and obtains the environment token only after reconciliation
  proves a request is necessary. One invocation opens at most one session.
- `ProviderSession.fetch(plan) -> HistoricalResponse` wraps exactly one
  one-minute, one-month `HistoricalRequest`.
- `AccountRateLimiter.acquire(cancellation, remaining_wait)` and
  `defer_for(delay, remaining_wait)` use one caller-owned limiter instance per
  Upstox account, shared by every job in the process. They fail before waiting
  if their known availability/defer time exceeds the supplied remaining
  invocation wait budget. It is neither per-partition nor a mutable module
  global.
- `EquityMonthValidationPolicy.validate(plan, candles, expected_sessions)`
  returns typed `ValidationEvidence` with policy version, actual UTC coverage,
  row count, `coverage_passed`, and `quality_passed`.
- `ExpectedSessionSchedule` is the authoritative point-in-time value defined
  above. Calendar acquisition is outside Sprint 1. Missing, incomplete,
  inconsistent, open-month, or digest-mismatched evidence fails closed and
  cannot produce `VERIFIED`.
- `UtcClock`, `CancellableSleeper`, `JitterSource`, `RunIdFactory`,
  `CancellationToken`, and a typed sanitized event sink make time, waiting,
  identity, cancellation, and diagnostics deterministic in tests.

## Pre-request algorithm

The range coordinator executes these steps in order:

1. Reconstruct and validate the complete command, retry policy, resolved
   instrument, expected session schedule/digest bytes, and resource limits.
2. Reject any interval other than `"1m"` before credentials, limiter, or HTTP.
3. Produce the touched months with `plan_upstox_equity_months`, expand each to
   its one canonical full-calendar-month acquisition plan, and reject the whole
   invocation if any month is not closed or its v2 schedule does not explicitly
   classify every first-to-last calendar date as one session or sourced closure.
   This proof occurs before lease acquisition and all storage/provider activity.
4. Acquire the protected root's exclusive lease. If it is already held, return
   `ALREADY_RUNNING` with zero provider activity and no storage/catalog change.
5. While holding the lease, Child D retains or re-reads exact supplied
   schedule-digest bytes. It may create a missing object only when those exact
   canonical bytes hash to the referenced digest; it never replaces present bad
   evidence. Failure returns `REJECTED/SCHEDULE_UNSUPPORTED` before catalog,
   credentials, limiter, or HTTP.
6. Open one DuckDB catalog connection. Catalog failure returns
   `FAILED/CATALOG_UNAVAILABLE` before provider-session creation.
7. For every plan, invoke the local observer on only its derived canonical path,
   using manifest-bound retained schedule evidence and stored aliases where they
   exist; it never compares aliases with the current command for local validity.
8. The storage-maintenance port removes only exact regular abandoned publisher siblings matching
   `.publish-[0-9a-f]{32}.tmp`, without following links, then fsyncs the parent.
9. Because the exclusive lease is held before catalog inspection, any visible
   `IN_PROGRESS` row belongs to a crashed earlier lease holder. Record it as
   `FAILED/INTERRUPTED` before retry or recovery. No elapsed-time threshold,
   process-ID test, hostname, or wall-clock staleness guess is permitted.
10. Re-read any visible canonical file through the physical schema boundary and
   the current validation policy.
11. If a final file is complete and valid but catalog verification is absent,
   create or retry a recovery run and persist `VERIFIED` locally. No request is
   made.
12. Invalidate a `VERIFIED` manifest whose path, file, checksum, schema,
   coverage, or quality evidence disagrees, using the exact ARK-40 category.
13. If reconciliation proves a failed/invalidated old-alias manifest needs a
    fresh request/publication, return zero-request run-fatal
    `MAPPING_MIGRATION_REQUIRED`; a valid stored final recovers locally first.
14. Move an invalid canonical final to a same-filesystem, no-follow, no-clobber
   quarantine name and fsync both directory transitions. If durable quarantine
   cannot be proven, return a run-fatal local-repair error and make no request.
15. Reload current manifests and physical evidence for every plan.
16. Call `reconcile_partition_plans` once for the complete desired range.
17. Build the ordered `REQUEST` tuple. If none exist, close local resources and
   return without resolving credentials or acquiring the limiter.
18. Before session creation, require the remaining total-attempt budget to admit
   at least one attempt for every `REQUEST` plan. Otherwise return
   `REJECTED/ATTEMPT_BUDGET_INSUFFICIENT` and make zero requests; this avoids a
   predictably partial range caused solely by caller configuration.
19. Lazily open one provider session and pass it to the bounded fetch port for
    requested partitions in plan order until complete, cancelled, a run-fatal
    error occurs, or the total provider-attempt budget is exhausted. Runtime
    exhaustion returns `FAILED` or `PARTIAL` by completed-result precedence with
    exact run code `ATTEMPT_BUDGET_EXHAUSTED`, preserves completed work, and
    marks every later plan `NOT_ATTEMPTED` without another provider request.

The lease covers observation, cleanup, recovery, provider work, publication,
and terminal catalog persistence. Crash releases it through the OS; restart
then classifies earlier `IN_PROGRESS` and abandoned temporary files safely.
The [public-preview contract](04-public-preview-contract.md) may use the same
protected root for a schedule-first preparation phase: it completely validates
the acquired schedule bytes in memory before lease acquisition or mutation,
then retains those exact bytes and snapshot evidence under the lease; the
coordinator later reacquires the lease and revalidates the retained schedule.
Every package user and future adapter must enter persistent candle ingestion
through this coordinator; bypassing it is unsupported.

Budget exhaustion preserves completed work and marks every untouched plan
`NOT_ATTEMPTED`. It never rolls back completed partitions and never causes the
next invocation to redownload partitions that now reconcile to `SKIP`.

## Single-partition lifecycle

For one requested plan:

1. Create `IN_PROGRESS`, or perform the approved `FAILED -> IN_PROGRESS` retry,
   with a globally unique run ID and injected provenance/time.
2. Check cancellation before limiter acquisition.
3. Acquire one permit from the shared account limiter.
4. Send one `HistoricalRequest(plan.instrument_key, "minutes", 1,
   plan.from_date, plan.to_date)`.
5. Apply only the provider retry policy below.
6. Persist `FAILED/EMPTY_RESPONSE` for a successful response containing no rows;
   do not repeat the same empty request in the invocation.
7. Normalize, canonicalize with the response-retrieval timestamp, and apply the
   versioned session-aware validation policy.
8. For every fresh `IN_PROGRESS` validation failure, persist only existing
   `FAILED/VALIDATION_FAILED` and expose the stable reason code in the report
   and event. `COVERAGE_NOT_PASSED` and `QUALITY_NOT_PASSED` are reserved solely
   for invalidating an already `VERIFIED` manifest during local observation.
9. Publish validated canonical rows atomically.
10. Derive `VERIFIED` only from sealed `PublishedPartitionEvidence`, then append
    terminal history and update current state in one catalog transaction.

Normalization, validation, write, publication, or catalog failures are never
retried through another provider request in the same invocation. A visible
publication with an uncertain catalog outcome is resolved by local observation
on restart.

## Retry and account-limiter policy

Retryable provider failures are limited to:

- HTTP 408;
- HTTP 429;
- HTTP 5xx; and
- transport `TIMEOUT` or `NETWORK`.

Terminal failures include HTTP 401, HTTP 403, every other 4xx, an oversized or
malformed successful response, and every non-provider stage failure.

There are at most `max_attempts_per_partition` HTTP attempts for one partition
and never more than `max_total_provider_attempts` in the complete invocation.
`max_total_wait` is one monotonic invocation-wide ledger, initialized before the
first limiter acquisition. Every blocking interval is charged to it: account
limiter admission, account-wide Retry-After deferral, and local retry-backoff
sleep. The ledger is neither reset per partition nor granted to a later request.
Every port receives remaining wait time and must return a typed bound failure
before it waits when the known wait would exceed it. Retry ordinal one means the
delay before the second HTTP attempt:

```text
base = min(base_backoff * 2 ** (retry_ordinal - 1), max_backoff)
local_delay = base / 2 + injected_uniform(0, base / 2)
effective_delay = max(local_delay, valid_retry_after)
```

The preserving-header transport child first replaces the current lossy response-header mapping with an
immutable bounded header collection that preserves arrival order and repeated
field values. The transport admits at most 128 fields, a 256-byte field name,
and a 4,096-byte value; excess or invalid header structure is a sanitized
terminal provider response error. Existing callers receive case-insensitive
lookup helpers rather than a flattened dictionary.

`Retry-After` is case-insensitive and accepted only when the preserved header
collection contains exactly one field value and that value is a nonnegative
decimal-seconds value or a strict IMF-fixdate. Comma-joined or repeated values
are ambiguous and ignored with a stable event code. A past date means zero.
Invalid or ambiguous values are ignored and recorded by stable code. A valid
delay is accepted only if it is at most `max_retry_after` **and** at most the
remaining `max_total_wait`; only then is it published to the shared limiter and
scheduled. A valid delay above either bound, a limiter admission wait above the
remaining ledger, or any later combined wait over the ledger fails before the
wait, persists existing `FAILED/PROVIDER_RETRYABLE` for an in-progress partition,
and returns run-fatal `RETRY_WAIT_BOUND_EXCEEDED`. It does not call `defer_for`,
sleep, or make a later provider request. Accepted account deferral is bounded by
the same ledger even though it is shared with other jobs.

Authentication, authorization, catalog unavailability, unsafe local repair,
mapping migration, cancellation, retry-wait bound failure, or total
attempt-budget exhaustion stops later provider work.
Ordinary partition-terminal failures remain isolated and may allow the next
partition when the run-fatal conditions do not apply.

## Crash and restart matrix

| Restart evidence | Deterministic outcome |
| --- | --- |
| Root lease held by another invocation | `ALREADY_RUNNING`; no mutation, credentials, limiter, or request. |
| Desired range touches an open month | `REJECTED/PARTITION_NOT_CLOSED`; no mutation or provider activity. |
| Referenced schedule object is missing and supplied canonical bytes hash exactly to that command or manifest digest | First-publish or restore those exact bytes once, then continue; no provider request is caused by retention alone. |
| Command-referenced schedule object is missing without matching supplied bytes, or is present unreadable/corrupt/unequal/digest-mismatched | `REJECTED/SCHEDULE_UNSUPPORTED` before work; present bad evidence is never replaced. |
| Manifest-bound schedule object is missing without matching supplied bytes, or is present unreadable/corrupt/unequal/digest-mismatched | Fail closed with no current-calendar substitution; a verified manifest is invalidated `COVERAGE_NOT_PASSED`, and a fresh in-progress validation failure is `VALIDATION_FAILED` with a stable schedule reason. Present bad evidence is never replaced. |
| Historical request touches only part of a closed month | Expand to the canonical full month; one reusable physical identity and at most one partition request. |
| No manifest, no final | Create `IN_PROGRESS`; request only this partition. |
| No manifest, valid final | Create recovery run and verify locally; zero request. |
| No manifest, invalid final | Quarantine durably, then request; quarantine failure is zero-request run-fatal. |
| `IN_PROGRESS`, no final | Record `INTERRUPTED`; retry only this partition. |
| `IN_PROGRESS`, valid final | Record `INTERRUPTED`; retry as recovery and verify locally; zero request. |
| `IN_PROGRESS`, invalid final | Record `INTERRUPTED`; quarantine, then retry only this partition. |
| `FAILED`, no final | Retry only this partition. |
| `FAILED`, valid final | Recovery retry and local verification; zero request. |
| `FAILED`, invalid final | Quarantine, then retry only this partition. |
| `FAILED` or invalidated manifest has obsolete aliases and its missing/invalid final requires fresh request/publication | `MAPPING_MIGRATION_REQUIRED`; zero request, no alias-only quarantine, until separately specified migration. |
| `FAILED` or invalidated manifest has obsolete aliases but valid final evidence | Recover locally with stored aliases; zero request and no mapping migration. |
| `VERIFIED`, all evidence agrees | `SKIP`; zero request. |
| `VERIFIED`, file missing | Invalidate `FILE_MISSING`; retry only this partition. |
| `VERIFIED`, path mismatch | Invalidate `PATH_INVALID_OR_MISMATCHED`; repair safely before any request. |
| `VERIFIED`, checksum mismatch | Invalidate `CHECKSUM_INVALID_OR_MISMATCHED`; quarantine and retry only this partition. |
| `VERIFIED`, unsupported schema | Invalidate `SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE`; quarantine and retry only this partition. |
| `VERIFIED`, coverage or quality fails | Invalidate the exact coverage or quality category; quarantine and retry only this partition. |
| `VERIFIED`, current aliases differ but stored artifact/manifest mapping is internally consistent | `SKIP`; zero request and no alias-only quarantine. |
| Abandoned temp only | Remove exact temp safely; it never counts as complete; request only this partition. |
| Publication visible, terminal catalog commit absent | Validate and recover the final locally; zero repeat request. |
| Terminal catalog commit complete | Reconcile to `SKIP`. |
| Catalog unavailable, corrupt, partial, or unsupported | `FAILED/CATALOG_UNAVAILABLE` before credentials or provider access. |

## Cancellation and partition isolation

Cancellation is checked after each completed plan, during limiter wait and
backoff sleep, immediately before a request, after a response, before
publication, and before a catalog transition. The synchronous HTTP call remains
bounded by its transport timeout. Best effort records `FAILED/INTERRUPTED` after
an `IN_PROGRESS` cancellation; when catalog persistence is unavailable, the row
remains `IN_PROGRESS` for restart recovery.

Cancellation before any plan has a terminal result or enters `IN_PROGRESS`
returns `CANCELLED/CANCELLED`, marks every planned item `CANCELLED`, and makes
no manifest or request. A local `SKIPPED_VERIFIED` result is terminal; later
cancellation therefore preserves it and uses the between-partition rule.
Whether the current invocation entered `IN_PROGRESS` is determined by the
current invocation's issued run ID, never by the mere presence of a historical
`FAILED` or `VERIFIED` manifest. A historical manifest returned when cancellation
prevents a new transition does not create an in-flight classification.
Cancellation after one plan enters `IN_PROGRESS` best-effort persists that
attempt as `FAILED/INTERRUPTED`, returns that item as `CANCELLED`, and marks all
later plans `NOT_ATTEMPTED`. It is `PARTIAL/CANCELLED` only if an earlier result
completed; otherwise it is `CANCELLED/CANCELLED`. The current request count may
already be nonzero. Cancellation never becomes a provider retry.

Cancellation observed between partitions retains every earlier completed or
failed result and marks every remaining unstarted plan `CANCELLED` without a
manifest. It is `PARTIAL/CANCELLED` if any retained earlier result completed and
otherwise `CANCELLED/CANCELLED`; `cancelled_count` equals those remaining plans
and provider attempts remain the bounded attempts already recorded. Cancellation
after every plan has a terminal result changes nothing: normal all-result
precedence determines `SUCCEEDED`, `PARTIAL`, or `FAILED`.

One partition failure never rolls back a completed partition. Every untouched
plan remains explicit as `NOT_ATTEMPTED` rather than being falsely failed.

The outcome table above is the only run-level mapping. In particular,
`ALREADY_RUNNING/ALREADY_RUNNING` is a successful refusal to enter an owned
invocation; `NONE` is exclusive to `SUCCEEDED`.

## Resource bounds

- One coordinator and one active partition in Sprint 1.
- One non-blocking root lease held by one process for the invocation.
- One in-flight provider request and one active response body.
- Zero background tasks, download queues, retry queues, or completed futures.
- One DuckDB connection and one active Parquet reader or writer.
- Existing HTTP response-body ceiling: 1,000,000 bytes.
- Existing normalized/canonical and Parquet batch ceiling: 65,536 rows.
- Plans, observations, and results are bounded `O(months)` using the existing
  planner ceiling; candle rows are bounded to one month at a time.
- Provider attempts are bounded by both the per-partition and invocation limits.
- Every limiter, deferral, and backoff wait is bounded by the one invocation
  `max_total_wait` ledger; no worker inherits unspent time from another run.
- Each adapter closes its file descriptors/readers before the next partition.

Representative tests must assert these cardinalities, and a benchmark must
record peak memory and file-descriptor counts for one full month and for a
mostly verified multi-month range.

## Higher-timeframe zero-request invariant

The persistent provider-ingestion command accepts `"1m"` only. Inputs such as
`"3m"`, `"5m"`, `"15m"`, `"30m"`, hourly, daily, or weekly fail before
planning, token resolution, limiter acquisition, or HTTP. Higher-timeframe bars
are a separately approved local aggregation/query concern derived from canonical
one-minute data and can never construct `HistoricalRequest` in this workflow.

## Credential, provenance, and diagnostic rules

- Tokens remain environment-provided and are read only inside the lazily opened
  provider session. They are never persisted or passed to domain models.
- No customer ID, TOTP secret, token, authorization header, response body, SQL,
  database path, canonical path, instrument key, or private provider payload is
  present in stable errors or events.
- Each manifest records source version, validation policy version, run ID,
  requested and actual coverage, row count, checksum, canonical path, and
  lifecycle timestamps through the existing domain contract.
- The validation policy version includes the exact schedule SHA-256 identity
  defined above. Reports/events may expose only that digest, schedule version,
  and `as_of`, never an unbounded schedule payload.
- Provider attempt events contain only run ID, attempt ordinal, stable category,
  sanitized status class, and clock time.
- Hostile exception, header, token, payload, path, and instrument text must not
  survive boundary translation.

## Live-provider gate

Live access is separate from deterministic tests and requires:

1. the full repository gate, build, lock, and diff checks to pass;
2. explicit owner authorization at execution time;
3. an environment-provided token;
4. an isolated caller-created protected storage root;
5. exactly one canonical closed RELIANCE calendar month with an authoritative
   schedule identity;
6. a total attempt budget of one and no retry; and
7. sanitized output limited to category, row count, first/last timestamp,
   checksum, request count, and gate result.

No generated dataset is committed. Missing authoritative expected-session
evidence disables live `VERIFIED`; it does not become a weaker coverage check.

## Deterministic verification

Tests use injected fakes and temporary local storage. They must prove:

- every pre-request rejection leaves session factory, token source, limiter,
  sleeper, and HTTP untouched;
- a verified repeat and locally recoverable publication make zero calls;
- a mixed verified, missing, and invalid range requests only affected months;
- every row in the crash/restart matrix;
- exact retry categories, equal jitter, valid/invalid/past/oversized
  `Retry-After`, shared limiter deferral, both attempt budgets, the one global
  wait ledger, fail-before-wait behavior, and no later request after a
  retry-wait bound failure;
- cancellation before any terminal result or the first `IN_PROGRESS`, during every in-progress
  boundary, between partitions after both completed and failed results, and
  after all terminal results, including exact result counts and request counts;
- authentication, catalog, and unsafe-repair run-fatal behavior;
- empty, malformed, and oversized response behavior;
- normalization, validation, publication, and catalog failure mapping;
- authoritative session coverage, holidays/special sessions supplied through
  the schedule port, explicit v2 closure evidence for every non-session date,
  missing/off-session bars, OHLC/volume quality,
  and unsupported schedule evidence;
- exact raw duplicates follow the approved normalization contract: identical
  rows are deduplicated and their count is reported in bounded validation/run
  evidence, while conflicting canonical keys remain a terminal validation
  failure; tests must not claim Child E can rediscover rows already removed by
  normalization;
- repeated, comma-joined, oversized, invalid, past, and single valid
  `Retry-After` fields are exercised through the preserving header boundary;
- root-lease contention, crash release, unsafe lock inode/mode, and the rule
  that only a held lease can interrupt earlier `IN_PROGRESS` state;
- frozen exact `schedule-digest-v1` regression bytes, plus exact
  `schedule-digest-v2` bytes with explicit closures, content-addressed no-clobber first publish
  or identical-byte restore, retained-byte mismatch, refusal to replace present
  bad evidence, and manifest-bound recovery without current-calendar
  substitution or catalog/history query;
- stable `security_id` recovery with mutable alias drift, including verified
  skip, manifest-absent stored-mapping recovery, and zero-request
  `MAPPING_MIGRATION_REQUIRED` for failed/invalidated old mappings;
- arbitrary historical edge dates converge on one full closed monthly identity,
  while an open month fails before mutation and provider activity;
- abandoned temporary output never becomes valid evidence;
- higher-timeframe input causes zero credential and provider activity;
- stable sanitization under hostile external values; and
- memory, file, task, queue, and request cardinalities remain bounded.

Run the deterministic Python quality gate plus `uv lock --check`, `uv build`,
and `git diff --check`. Each implementation child requires one combined Sol
High independent review because it touches storage, provenance, provider retry,
credentials, or cross-module orchestration. Do not add a duplicate Terra review.

## ARK-36 atomic decomposition

ARK-36 is a tracking parent, not one red-green-refactor task. Nine ordered
children are the smallest honest decomposition: lease differs from filesystem
mutation, header transport differs from retry behavior, schedule retention
differs from validation, and each remaining child has one observable behavior
and one reason to change.

### Child A: acquire one protected storage-root lease

It owns only creation/verification of the stable no-follow lock inode and one
non-blocking advisory-lock lifetime. It returns `LeaseResult` and never scans,
removes, quarantines, opens DuckDB, validates data, or calls a provider.

ARK-51 correction: an acquired `StorageRootLease` retains the protected root's
verified `(st_dev, st_ino)` identity. Its narrow root-operation context proves
that the lease remains open and that the supplied root path still identifies
that same real directory before a child performs mutation. A closed lease,
wrong supplied root, or substituted root fails closed.

Done: one caller either holds the verified protected-root lease or observes
`ALREADY_RUNNING` without changing any other storage state.

### Child B: safely maintain one leased local partition directory

With Child A lease proof and one exact canonical path, it owns only bounded
exact-temp removal, same-filesystem no-clobber quarantine, descriptor checks,
and required directory fsyncs. It neither interprets manifests nor acquires a
lease, validates candles, or accesses a provider.

ARK-51 correction: Child B receives the held lease and one exact canonical
target. The target path must have the approved publication shape
`candles/provider=.../exchange=.../segment=.../instrument_type=.../security_id=.../interval=.../year=YYYY/month=MM/bars.parquet`; relative, outside, dot-component,
arbitrary-contained, reordered, hidden/control, and reserved `.ingestion.lock`
paths are rejected. It may remove only an exact abandoned publisher sibling
regular file whose name matches `.publish-[0-9a-f]{32}.tmp`, without following
symlinks, and must fsync its verified parent directory. A missing exact temp is
idempotent typed `NOT_FOUND`. For one unsafe canonical regular file, quarantine
uses a bounded hidden sibling in the same verified parent, no-follow/no-clobber
creation, the same filesystem, and durable fsyncs for both directory
transitions. It returns the exact quarantine path on `QUARANTINED`; a
`FAILED/LOCAL_REPAIR_BLOCKED` result may also carry the exact retained or
durability-ambiguous quarantine path. A missing quarantine source is
`FAILED/LOCAL_REPAIR_BLOCKED` because prior quarantine cannot be proven.
Outcomes are exactly `REMOVED`, `QUARANTINED`, `NOT_FOUND`, and `FAILED`;
successful outcomes use `NONE`, while unsafe local failures use
`LOCAL_REPAIR_BLOCKED`. Quarantine-name generation uses at most 32 attempts and
an injectable source of cryptographic 32-character lowercase hex tokens.
Canonical containment and every relevant path/descriptor identity and type are
validated without following symlinks; wrong types, collisions, link/unlink,
fsync, cleanup, and lease-authority failures fail closed. The portable
descriptor-relative check-then-unlink residual is accepted inside the private
application-owned sole-writer boundary only; this specification does not claim
protection against a hostile same-directory writer replacing a pathname between
the final identity check and unlink.

Done: one lease holder can remove or quarantine only its exact safe local target
and otherwise returns a typed no-provider failure.

### Child C: preserve bounded HTTP response-header fields

It owns only immutable arrival-ordered repeated response-header representation,
bounded parsing, and case-insensitive lookup helpers that replace lossy mapping
transport. It performs no retry classification, sleep, rate limiting, or
historical request.

Done: a bounded transport response preserves every valid repeated header field
or returns one sanitized structural transport error.

### Child D: retain and resolve one content-addressed session schedule

With Child A lease proof, it owns versioned schedule-digest serialization, digest
calculation, no-clobber content-addressed schedule retention/identical-byte
restore, and verified lookup by manifest policy digest. Frozen v1 evidence
remains readable for historical manifests, but every new ARK-58 command requires
v2 with an explicit session or sourced closure for every date in each requested
closed month. A missing object may be written only from supplied canonical bytes
whose lowercase SHA-256 equals that digest; a present unreadable, corrupt,
unequal, or mismatched object is never replaced. It does not obtain calendars,
inspect catalog/history, judge candles, or change manifests/catalog rows.

Done: one valid schedule is immutably retrievable by its exact digest or fails
closed with `SCHEDULE_UNSUPPORTED`.

### Child E: validate one canonical NSE equity month against supplied schedule bytes

It takes one exact plan, canonical candles, Child D resolved schedule bytes,
raw/normalized row counts, and policy version; it returns immutable coverage,
quality, and stable reason evidence. It owns session/bar/quality rules only and
does not retain schedules, access storage, mutate lifecycle, or call a provider.

Done: one canonical equity month receives reproducible schedule-bound validation
evidence without provider, storage, or lifecycle side effects.

### Child F: execute one bounded account-rate-limited historical request

It takes one exact plan, caller-opened `ProviderSession`, Child C headers,
shared limiter, remaining invocation attempt/wait budget, clock/sleeper/jitter,
and cancellation. It owns Historical V3 construction, retry classification,
Retry-After parsing, wait-ledger accounting, and sanitized provider events; it
does not resolve credentials, open storage/catalog, or mutate lifecycle.

Done: one planned month returns one bounded response or typed provider failure
without exceeding the invocation request or wait budget.

### Child G: observe, recover, or invalidate one leased catalogued partition

With Child A proof, Child B maintenance, Child D schedule lookup, Child E
validation, one physical plan, and manifest/physical evidence, it owns local
re-read, stored-alias recovery, crashed `IN_PROGRESS` classification, local
recovery, and verified invalidation. It never makes HTTP requests and returns
`MAPPING_MIGRATION_REQUIRED` rather than migrating a failed stored alias.

Done: one leased physical month becomes trustworthy reconciliation evidence or a
typed local outcome without provider access.

### Child H: execute one requested partition ingestion lifecycle

It takes a requestable current mapping, Child F fetch, Child E validation,
publisher, catalog, clock, run ID, and cancellation. It owns `IN_PROGRESS`,
normalization/canonicalization, fresh `VALIDATION_FAILED` mapping, publication,
and terminal lifecycle persistence; it never refetches after a non-provider
failure.

Done: one requestable month ends with traceable verified, failed, interrupted,
or cancelled evidence and no duplicate provider/publication attempt.

### Child I: coordinate one request-minimal RELIANCE date range

It takes one `IngestionCommand` and Children A through H. It owns full-month
planning, run-level table/count mapping, sequential ordering, lazy session
opening, and the rule that complete local reconciliation precedes credentials
and provider use; it owns no transport, filesystem primitive, validation rule,
or lifecycle transition.

If Child H escapes after consuming a provider attempt, Child I snapshots the
current invocation's attempt delta and safely readable current-run manifest,
applies the approved post-attempt exception row, and stops. It never converts
that work into zero attempts or forces a terminal lifecycle transition.

Done: one RELIANCE one-minute range emits the exhaustive ordered report and
requests only independently required full months.

Dependencies are `A -> B`, `A -> D`, `D -> E`, `C -> F`,
`A + B + D + E -> G`, `E + F -> H`, and `A + B + C + D + E + F + G + H -> I
-> ARK-37`. The implementation order is `A, B, C, D, E, F, G, H, I` under the
one-item WIP limit. Independent children never execute in parallel. ARK-37
remains end-to-end crash and zero-request idempotency proof and does not
duplicate child implementation.

## Coordinator contract-compatibility matrix

Before the one formal Sol High review of this high-risk, broad specification,
the coordinator completes and records this deterministic matrix against the
exact candidate commit. It is a coordinator-owned document/code comparison,
not another reviewer, subagent, model pass, or acceptance-gate waiver. Every
row records the governing location, candidate location, compatible/incompatible
result, and any required repair; an incompatible row blocks formal review.

| Required check | Exact compatibility proof |
| --- | --- |
| Frozen typed contracts | Every touched planner, reconciliation, lifecycle, publication, catalog, HTTP, historical, normalization, canonical, and Parquet contract is named; no required field, type, ownership, or transition is invented. |
| Physical identity | Full-month identity is exactly provider/exchange/segment/instrument type/security ID/interval/year/month; edge dates and mutable aliases do not create a second identity. |
| Lifecycle transition | Every fresh, retry, recovery, invalidation, interruption, and cancellation maps to an existing ARK-40 transition/category or a report-only run code; no manifest/catalog schema change is implied. |
| Exhaustive typed outcome | The run table covers zero/mixed/all failure results, precedence, counts, and request cardinality for every valid command. |
| Boundary-state exhaustiveness | Cancellation and every other stateful outcome enumerate before, during, between, and after terminal boundary states, with precedence, result counts, manifest effect, and request cardinality. |
| Provenance retention | Schedule bytes, digest serialization/version, policy binding, immutable lookup, and recovery behavior are exact and bounded. |
| Bounded resource and wait | Request, response, plan, file, connection, retry, limiter, and all wait cardinalities are bounded; every over-bound wait fails before waiting. |
| Crash/concurrency ownership | Lease acquisition precedes mutable observation; only lease ownership permits stale interruption, cleanup, quarantine, recovery, or retention mutation. |
| Callable dependency proof | Every required read, write, or query occurs only after its dependency is available and maps to an existing callable contract, or is isolated as an approved atomic child; prose does not assume an unstated API. |
| Atomic children | Each child has one observable behavior, one reason to change, a one-sentence Done condition, and explicit dependencies/order with no stale count or label. |

## Acceptance criteria and completion

ARK-49 is complete when:

- one independent Sol High review approves this complete contract and
  decomposition;
- the coordinator contract-compatibility matrix is complete with no unresolved
  incompatible row before that review begins;
- the specification is linked from ARK-36;
- ARK-36 is converted to a tracking parent with nine ordered executable tasks;
- every failure and edge above has a deterministic typed result;
- zero-request paths prove token, limiter, and HTTP inactivity;
- no path can promote unsupported coverage or quality evidence to `VERIFIED`;
  and
- repository and Linear sources of truth agree.

The original specification review-repair budget is exhausted. The authorized
last focused cancellation-only OS-read-only Sol High recheck approved the
corrected candidate. No further automatic repair round is authorized by this
plan. Each child uses strict red-green-refactor TDD, unchanged deterministic
gates, the approved single-writer routing, and the required independent
high-risk review. No child implementation begins until this specification is
accepted and its Linear issue is Ready.
