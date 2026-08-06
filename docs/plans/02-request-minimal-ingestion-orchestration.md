# Request-minimal one-minute ingestion orchestration

Status: **Proposed after ARK-49 review repair**
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
    max_total_sleep: timedelta = timedelta(seconds=120)


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
    PARTITION_NOT_CLOSED = "PARTITION_NOT_CLOSED"
    SCHEDULE_UNSUPPORTED = "SCHEDULE_UNSUPPORTED"
    STORAGE_UNSAFE = "STORAGE_UNSAFE"
    CATALOG_UNAVAILABLE = "CATALOG_UNAVAILABLE"
    ATTEMPT_BUDGET_INSUFFICIENT = "ATTEMPT_BUDGET_INSUFFICIENT"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    LOCAL_REPAIR_BLOCKED = "LOCAL_REPAIR_BLOCKED"
    CANCELLED = "CANCELLED"


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
is skipped, locally recovered, or verified. `PARTIAL` means at least one result
completed and later work did not. `FAILED` means execution began but no desired
partition completed. `CANCELLED`, `ALREADY_RUNNING`, and `REJECTED` are exact
zero-request run outcomes. Timestamps are
injected UTC-aware clock values. `error_code` is a stable sanitized code, never
an exception, SQL string, token, URL, response body, path, or instrument value.

## Authoritative session schedule and validation identity

`ExpectedSessionSchedule` is immutable and contains an exact schedule schema
version, provider/source name, source release/version, UTC-aware `as_of`,
`Asia/Kolkata` timezone identifier, the covered first and last calendar dates,
and an ordered tuple of sessions. Each session contains its local trade date,
UTC-aware open instant, UTC-aware exclusive close instant, and session kind.
Normal NSE cash sessions and explicitly sourced special sessions are allowed;
holidays are represented by absence. Sessions must be unique, strictly ordered,
minute-aligned, inside the declared coverage, and wholly cover every canonical
acquisition month. Future or open sessions are rejected.

The schedule exposes a canonical SHA-256 digest over all fields and sessions.
`validation_policy_version` is not a free label: the effective value persisted
in the existing manifest is
`<policy-name>@<policy-version>+sessions-sha256:<64-lower-hex>`. This binds every
coverage decision to the exact point-in-time schedule without redesigning the
manifest or catalog schema. Local recovery must reproduce that identity and
fails closed on any mismatch. `source_version` continues to identify the
Upstox adapter/request contract, not the trading calendar.

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
- `AccountRateLimiter.acquire(cancellation)` and `defer_for(delay)` use one
  caller-owned limiter instance per Upstox account, shared by every job in the
  process. It is neither per-partition nor a mutable module global.
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
   instrument, expected session schedule, and resource limits.
2. Reject any interval other than `"1m"` before credentials, limiter, or HTTP.
3. Produce the touched months with `plan_upstox_equity_months`, expand each to
   its one canonical full-calendar-month acquisition plan, and reject the whole
   invocation if any month is not closed or fully covered by the schedule.
4. Acquire the protected root's exclusive lease. If it is already held, return
   `ALREADY_RUNNING` with zero provider activity and no storage/catalog change.
5. While holding the lease, open one DuckDB catalog connection. Catalog failure
   returns `FAILED/CATALOG_UNAVAILABLE` before provider-session creation.
6. For every plan, invoke the local observer on only its derived canonical path,
   using the command's authoritative expected-session evidence.
7. The storage-maintenance port removes only exact regular abandoned publisher siblings matching
   `.publish-[0-9a-f]{32}.tmp`, without following links, then fsyncs the parent.
8. Because the exclusive lease is held before catalog inspection, any visible
   `IN_PROGRESS` row belongs to a crashed earlier lease holder. Record it as
   `FAILED/INTERRUPTED` before retry or recovery. No elapsed-time threshold,
   process-ID test, hostname, or wall-clock staleness guess is permitted.
9. Re-read any visible canonical file through the physical schema boundary and
   the current validation policy.
10. If a final file is complete and valid but catalog verification is absent,
   create or retry a recovery run and persist `VERIFIED` locally. No request is
   made.
11. Invalidate a `VERIFIED` manifest whose path, file, checksum, schema,
    coverage, or quality evidence disagrees, using the exact ARK-40 category.
12. Move an invalid canonical final to a same-filesystem, no-follow, no-clobber
    quarantine name and fsync both directory transitions. If durable quarantine
    cannot be proven, return a run-fatal local-repair error and make no request.
13. Reload current manifests and physical evidence for every plan.
14. Call `reconcile_partition_plans` once for the complete desired range.
15. Build the ordered `REQUEST` tuple. If none exist, close local resources and
    return without resolving credentials or acquiring the limiter.
16. Before session creation, require the remaining total-attempt budget to admit
    at least one attempt for every `REQUEST` plan. Otherwise return
    `REJECTED/ATTEMPT_BUDGET_INSUFFICIENT` and make zero requests; this avoids a
    predictably partial range caused solely by caller configuration.
17. Lazily open one provider session and pass it to the bounded fetch port for
    requested partitions in plan order until complete, cancelled, a run-fatal
    error occurs, or the total provider-attempt budget is exhausted.

The lease covers observation, cleanup, recovery, provider work, publication,
and terminal catalog persistence. Crash releases it through the OS; restart
then classifies earlier `IN_PROGRESS` and abandoned temporary files safely.
Every package user and future adapter must enter persistent ingestion through
this coordinator; bypassing the lease is unsupported.

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
8. Persist the most specific failure category when coverage or quality is not
   passed. Unsupported or missing expected-session evidence fails closed.
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
Each attempt acquires the account limiter. Retry ordinal one means the delay
before the second HTTP attempt:

```text
base = min(base_backoff * 2 ** (retry_ordinal - 1), max_backoff)
local_delay = base / 2 + injected_uniform(0, base / 2)
effective_delay = max(local_delay, valid_retry_after)
```

Child C first replaces the current lossy response-header mapping with an
immutable bounded header collection that preserves arrival order and repeated
field values. The transport admits at most 128 fields, a 256-byte field name,
and a 4,096-byte value; excess or invalid header structure is a sanitized
terminal provider response error. Existing callers receive case-insensitive
lookup helpers rather than a flattened dictionary.

`Retry-After` is case-insensitive and accepted only when the preserved header
collection contains exactly one field value and that value is a nonnegative
decimal-seconds value or a strict IMF-fixdate. Comma-joined or repeated values
are ambiguous and ignored with a stable event code. A past date means zero.
Invalid or ambiguous values are ignored and recorded by stable code. A
valid delay greater than `max_retry_after` is published to the shared limiter,
but this bounded invocation makes no further request for that partition. Total
sleep cannot exceed `max_total_sleep`; exhaustion persists
`FAILED/PROVIDER_RETRYABLE`.

Authentication, authorization, catalog unavailability, unsafe local repair,
cancellation, or total attempt-budget exhaustion stops later provider work.
Ordinary partition-terminal failures remain isolated and may allow the next
partition when the run-fatal conditions do not apply.

## Crash and restart matrix

| Restart evidence | Deterministic outcome |
| --- | --- |
| Root lease held by another invocation | `ALREADY_RUNNING`; no mutation, credentials, limiter, or request. |
| Desired range touches an open month | `REJECTED/PARTITION_NOT_CLOSED`; no mutation or provider activity. |
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
| `VERIFIED`, all evidence agrees | `SKIP`; zero request. |
| `VERIFIED`, file missing | Invalidate `FILE_MISSING`; retry only this partition. |
| `VERIFIED`, path mismatch | Invalidate `PATH_INVALID_OR_MISMATCHED`; repair safely before any request. |
| `VERIFIED`, checksum mismatch | Invalidate `CHECKSUM_INVALID_OR_MISMATCHED`; quarantine and retry only this partition. |
| `VERIFIED`, unsupported schema | Invalidate `SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE`; quarantine and retry only this partition. |
| `VERIFIED`, coverage or quality fails | Invalidate the exact coverage or quality category; quarantine and retry only this partition. |
| Abandoned temp only | Remove exact temp safely; it never counts as complete; request only this partition. |
| Publication visible, terminal catalog commit absent | Validate and recover the final locally; zero repeat request. |
| Terminal catalog commit complete | Reconcile to `SKIP`. |
| Catalog unavailable, corrupt, partial, or unsupported | Stop before credentials or provider access. |

## Cancellation and partition isolation

Cancellation is checked after each completed plan, during limiter wait and
backoff sleep, immediately before a request, after a response, before
publication, and before a catalog transition. The synchronous HTTP call remains
bounded by its transport timeout. Best effort records `FAILED/INTERRUPTED` after
an `IN_PROGRESS` cancellation; when catalog persistence is unavailable, the row
remains `IN_PROGRESS` for restart recovery.

Cancellation before any plan enters `IN_PROGRESS` returns run outcome
`CANCELLED` and marks every already-planned item `CANCELLED`, with no manifest.
Cancellation after one plan enters `IN_PROGRESS` best-effort persists that
attempt as `FAILED/INTERRUPTED`, returns that item as `CANCELLED`, and marks all
later plans `NOT_ATTEMPTED`. Completed earlier results are retained, so the run
outcome is `PARTIAL` when at least one of them completed and otherwise
`CANCELLED`. Cancellation never becomes a provider retry.

One partition failure never rolls back a completed partition. Every untouched
plan remains explicit as `NOT_ATTEMPTED` rather than being falsely failed.

Run-level mapping is exhaustive: validation, schedule, open-month, and budget
rejections use `REJECTED`; lease contention uses `ALREADY_RUNNING`; cancellation
uses the rules above; a fatal condition after one or more completed partitions
uses `PARTIAL`; the same condition before any completion uses `FAILED`; and only
an all-complete result tuple uses `SUCCEEDED`. `failure_code` is `NONE` only for
`SUCCEEDED`; every other outcome uses its single immediate stop reason.

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
  `Retry-After`, shared limiter deferral, and both attempt budgets;
- cancellation at every defined boundary;
- authentication, catalog, and unsafe-repair run-fatal behavior;
- empty, malformed, and oversized response behavior;
- normalization, validation, publication, and catalog failure mapping;
- authoritative session coverage, holidays/special sessions supplied through
  the schedule port, missing/off-session bars, OHLC/volume quality,
  and unsupported schedule evidence;
- exact raw duplicates follow the approved normalization contract: identical
  rows are deduplicated and their count is reported in bounded validation/run
  evidence, while conflicting canonical keys remain a terminal validation
  failure; tests must not claim Child D can rediscover rows already removed by
  normalization;
- repeated, comma-joined, oversized, invalid, past, and single valid
  `Retry-After` fields are exercised through the preserving header boundary;
- root-lease contention, crash release, unsafe lock inode/mode, and the rule
  that only a held lease can interrupt earlier `IN_PROGRESS` state;
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

ARK-36 is a tracking parent, not one red-green-refactor task. Six ordered tasks
are the smallest honest decomposition. Cross-process exclusion and filesystem
mutation are separated from catalog recovery; provider response/retry policy,
market-session validation, one-partition lifecycle, and range coordination each
retain one independent reason to change.

### Child A: lease one storage root and perform safe local file maintenance

Inputs are one protected root, an exact canonical partition path, cancellation,
and injected OS operations. Outputs are an exclusive lease result and typed
bounded cleanup/quarantine results.

It owns the stable no-follow lock inode, non-blocking exclusive lease lifetime,
exact abandoned-temp discovery/removal, same-filesystem no-clobber quarantine,
descriptor identity checks, and required directory fsyncs. It never opens
DuckDB, interprets a manifest, validates candles, or calls a provider.

Done: one invocation either owns the root exclusively and can perform exact
durable local maintenance, or changes nothing and reports a safe typed reason.

### Child B: observe, recover, and invalidate one catalogued partition

Inputs are proof of the held Child A lease, one canonical full-month plan,
current manifest or absence, exact local-file evidence/maintenance ports, the
Child D validation port, expected schedule, and clock/run-ID dependencies only
when recovery requires a lifecycle transition. The output is typed
reconciliation evidence, recovered publication evidence when present,
performed catalog transition, and a sanitized local outcome.

It owns bounded physical re-read/checksum/schema/policy validation, safe
classification of earlier `IN_PROGRESS`, local recovery, and verified
invalidation. It delegates file mutation to Child A and cannot mark work
interrupted without lease proof. It never owns HTTP, credentials, provider
retry, normalization, or range scheduling.

Done: while exclusivity is proven, one physical month becomes trustworthy
reconciliation evidence or a safe typed repair outcome without provider access.

### Child C: execute one bounded account-rate-limited historical request

Inputs are one exact plan, the caller's already-open `ProviderSession`, shared
account limiter, retry policy, remaining invocation budget,
clock/sleeper/jitter, and cancellation. The output is a fetched response plus
retrieval time or a typed sanitized provider failure, with exact attempts and
retry events.

It owns exact Historical V3 request construction, retry classification,
the preserving bounded HTTP header contract, unambiguous `Retry-After`, equal
jitter, account deferral, budgets, and secret sanitization.
The range coordinator owns lazy session opening; this child never resolves a
credential, opens the catalog or Parquet, normalizes, or mutates lifecycle state.

Done: one planned month produces one bounded response or sanitized provider
outcome without exceeding account or request budgets.

### Child D: validate one canonical NSE equity month against supplied sessions

Inputs are one exact plan, canonical candles, authoritative
`ExpectedSessionSchedule`, raw and normalized row counts, and validation policy
version. The output is immutable
`ValidationEvidence` containing actual UTC range, row count, coverage and quality
outcomes, exact-raw-deduplication count, effective schedule-bound policy
identity, and stable reason codes.

It owns canonical-key uniqueness, strict ordering, plan identity, full-month
containment, expected bar-open coverage, holidays/special-session input
handling, missing and off-session bars, OHLC envelope, nonnegative volume, and
unsupported schedule behavior. It accepts the raw/normalized count delta as
bounded evidence of exact raw deduplication; conflicting canonical keys fail at
the canonicalization boundary before validation. It does not acquire calendars,
call providers, publish files, or mutate manifests.

Done: one canonical equity month receives reproducible point-in-time coverage
and quality evidence without provider, storage, or lifecycle side effects.

### Child E: execute one partition ingestion lifecycle

Inputs are one plan/current manifest, Child C fetch port, Child D validation
port, publisher, catalog, clock, run-ID factory, and cancellation. The output is
one `PartitionResult`.

It enforces `IN_PROGRESS` before HTTP, then fetch, normalize, canonicalize,
validate, publish, and terminal catalog evidence. It maps each failure to the
exact ARK-40 category and never re-fetches after any non-provider stage or
publication uncertainty.

Done: one requested month ends as traceable verified, failed, interrupted, or
cancelled evidence with no duplicate provider or publication attempt.

### Child F: coordinate a request-minimal RELIANCE date range

Inputs are one `IngestionCommand` plus Child A, Child B, and Child E ports. The
output is one immutable ordered `IngestionReport`.

It expands touched historical ranges to canonical full closed months, acquires
and holds the one root lease, completes local observation/recovery for every
month, reconciles once, lazily enables provider work, enforces total budget,
and executes requested partitions sequentially. It owns exact run-level
outcome/count mapping but no queue, background task, or higher-timeframe
provider path.

Done: a RELIANCE one-minute range is completely reconciled before credentials
or HTTP and downloads only independently required months.

Dependencies are `A + D -> B`, `B + C + D -> E`, and
`A + B + E -> F -> ARK-37`. The implementation order is `D, A, B, C, E, F`
under the one-item WIP limit. C is logically independent of A/B/D, but it does
not execute in parallel. ARK-37
remains the end-to-end crash and zero-request idempotency proof and must not
duplicate implementation owned by these children.

## Acceptance criteria and completion

ARK-49 is complete when:

- one independent Sol High review approves this complete contract and
  decomposition;
- the specification is linked from ARK-36;
- ARK-36 is converted to a tracking parent with six ordered executable tasks;
- every failure and edge above has a deterministic typed result;
- zero-request paths prove token, limiter, and HTTP inactivity;
- no path can promote unsupported coverage or quality evidence to `VERIFIED`;
  and
- repository and Linear sources of truth agree.

ARK-49 allows one specification pass and one Sol review-repair round. Each child
uses strict red-green-refactor TDD, the unchanged deterministic gates, the
approved single-writer routing and repair budget, and the required independent
high-risk review. No child implementation begins until this specification is
accepted and its Linear issue is Ready.
