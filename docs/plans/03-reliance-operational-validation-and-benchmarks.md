# Plan 03: RELIANCE operational validation and benchmark contract

Status: **Conditional activation — this document is an ARK-67 high-risk review
candidate now.  It is accepted and active only if this exact reviewed candidate
passes the required Sol review, is merged, and ARK-67 is closed; no later
status-only edit may substitute for those conditions.  No implementation child
is thereby a Sprint 2 commitment.**
Scope: ARK-11 Milestone 2 operational proof for one closed **RELIANCE** NSE
equity calendar month at one-minute frequency
Depends on: [Plan 01](01-data-foundation-and-upstox-ingestion.md),
[Plan 02](02-request-minimal-ingestion-orchestration.md), and the accepted
ARK-31/32/33/34/35/40/42/43/49/58 contracts

## 1. Purpose, status, and boundary

This plan freezes the operational evidence required to decide whether the
existing Sprint 1 one-minute RELIANCE ingestion path is safe to advance through
Milestone 2.  It is a test and operational-tooling contract, not a new market
data product interface.  It proves that the already-frozen application
contracts can ingest, reconcile, recover, query, and measure one representative
closed NSE equity month without weakening provenance, request minimization, or
storage ownership.

**Status and authority.** ARK-67 is pre-sprint specification work.  It does
not start Sprint 2, select its denominator, approve credentials, authorize a
provider request, change Linear, or implement an ARK-68--ARK-73 candidate.
The Plan 02 range coordinator and all of its exact typed outcomes remain the
governing public/application contract.  ARK-59 owns any future stable
Python/CLI/package interface.  This plan must not be used to redesign a
manifest, DuckDB catalog, schedule digest, canonical candle, Parquet schema,
or lifecycle transition.

### In scope

- Deterministic, credential-free fixtures and evidence checks for the existing
  RELIANCE/NSE/NSE_EQ/EQ/`1m` contracts.
- A one-time, owner-authorized authenticated operational gate for exactly one
  closed RELIANCE calendar month.
- Existing DuckDB catalog and direct-Parquet query proof, recovery/repair
  evidence, and representative bounded-resource measurements.
- A traceable acceptance dossier for ARK-11 Milestone 2.

### Non-goals

- A different provider, instrument, symbol universe, index, India VIX,
  derivative, option, future, crypto, forex, or higher timeframe.
- An open month, incremental data, a second candle request for comparison, or
  provider retry beyond the frozen live gate.
- Calendar acquisition, a new late-listing/no-trade exception model, a new
  persisted evidence schema, or inferred holiday/session rules.
- User-facing API/CLI/package work, release/publishing, multi-instrument
  scheduling, bounded worker pools, strategy/research modules, indicators,
  backtests, recommendations, or order execution.
- Tuning or optimization before a measured bottleneck exists.

### Governing ownership (no redesign)

| Concern | Sole governing owner used by this plan | Operational implication |
| --- | --- | --- |
| Month planning and `1m` admission | ARK-32 / Plan 02 coordinator | Calendar-month requests only; open months and other intervals reject before side effects. |
| Local skip/request decision | ARK-33 reconciliation | The harness supplies observation evidence; it never substitutes its own completeness rule. |
| State, failures, and recovery history | ARK-40 lifecycle and catalog | Use only existing `IN_PROGRESS`, `VERIFIED`, `FAILED`, categories, and report-only Plan 02 run codes. |
| Canonical row and physical file validity | ARK-31, ARK-42, ARK-43, ARK-34 | Validate/re-read/publish through existing boundaries; never alter an existing raw Parquet file. |
| Raw normalization | existing normalization boundary | Exact duplicate timestamp rows are normalized once; conflicting timestamp rows fail. |
| Session proof | Plan 02 `ExpectedSessionSchedule`, `schedule-digest-v2`, Child D/E | Calendar evidence is authoritative and retained by digest; the harness does not guess a calendar. |
| Orchestration/cancellation/provider use | Plan 02 Children A--I | Preserve the exhaustive `IngestionReport`/`PartitionResult` mapping, lease, budgets, and lazy provider session. |
| Query | existing DuckDB catalog and direct Parquet scan boundary | Query stored Parquet; never create a DuckDB candle copy. |

The word “RELIANCE” below denotes an invocation fixture or owner-selected live
symbol argument, never a production constant.  The current master-catalog
resolution supplies the current NSE equity mapping.  No implementation may
hard-code its ISIN, instrument key, symbol-to-key mapping, filesystem location,
or provider payload.

## 2. Deterministic fixture and configuration contract

All deterministic cases run offline, with temporary caller-created protected
roots, injected ports, fakes, and synthetic canonical rows.  They require no
credential, token source, provider response, private market data, or real
machine path.  Fixture names are stable test-tooling labels only; they add no
application, manifest, catalog, or public-report field.

### 2.1 Common fixture rules

`reliance_closed_month` is an exact built-in-date closed calendar month selected
by the test clock.  It is represented by an existing resolved `Instrument`
fixture whose NSE/NSE_EQ/EQ identity is valid under the existing constructor;
the actual provider aliases are synthetic non-secret values.  Every case uses
the existing ARK-32 full-month plan, even when the requested edge dates touch
only part of the month.

`schedule_v2_complete` is canonical schedule-digest-v2 bytes made by the
existing digest serializer.  For every date from the month’s first through last
day it contains exactly one minute-aligned session or one sourced closure.  It
contains at least these generated variants:

| Fixture | Schedule fact | Rows expected by existing validation policy |
| --- | --- | --- |
| `regular_session_month` | ordinary sessions plus explicit non-session closures | one row for every expected session minute |
| `holiday_month` | one explicit full-day holiday closure | no row for that closure date; all scheduled minutes present |
| `special_session_month` | one explicitly shorter or otherwise non-default, minute-aligned session | rows only for precisely that session’s expected minutes |
| `incomplete_schedule_month` | deliberately omits a date or conflicts a session/closure | unsupported before lease/provider activity |

The fixture factory derives all timestamps from the supplied schedule and makes
nonnegative finite OHLCV rows satisfying the ARK-31 envelope.  It does not
assume a universal NSE close time, weekday, holiday list, special-session
duration, listing date, or no-trade convention.  `raw_count` is the finite
provider-normalized input count and `normalized_count` is the count after the
existing normalization boundary.  A fixture never forwards a missing row or
synthesizes a price.

The harness uses only existing injected ports: `UtcClock`, cancellation token,
sleeper, jitter source, run-ID factory, schedule store, root lease, local
observer/maintenance port, provider-session factory/session, limiter, catalog,
and event sink.  The fake provider records only an integer request count and a
preconfigured typed result; it stores no URL, header, token, body, or instrument
text in assertions or reports.

### 2.2 Named data fixtures

| Fixture | Construction | Required evidence |
| --- | --- | --- |
| `valid_month` | all expected session-minute rows, canonical schema/identity | `coverage_passed=True`, `quality_passed=True`, ordered coverage, valid sealed publication evidence |
| `interrupted_in_progress` | existing current manifest in `IN_PROGRESS`, no final or a valid/invalid final as named by case | existing `INTERRUPTED` transition and only affected-month retry/recovery evidence |
| `internal_gap` | remove one expected scheduled minute between two present expected minutes | `coverage_passed=False`, stable `COVERAGE_EXPECTED_BAR_MISSING`; no fill |
| `corrupt_physical` | write a bounded disposable file failing the named physical/checksum/schema/quality check | exact existing verified invalidation category and targeted maintenance outcome |
| `incomplete_physical` | valid physical shape with `internal_gap` evidence | exact `COVERAGE_NOT_PASSED` invalidation before a targeted request |
| `exact_duplicate_raw` | two otherwise identical raw normalized-input rows with one timestamp | normalized output contains one row; bounded raw-versus-normalized and duplicate-count evidence |
| `conflicting_duplicate_raw` | two same-key raw rows whose canonical values differ | terminal `FAILED/NORMALIZATION_FAILED`; no publication |
| `impossible_raw_ohlc_or_volume` | finite raw row violating the ARK-31 high/low envelope or raw negative/invalid volume | existing `FAILED/NORMALIZATION_FAILED`; no pure-validation claim, publication, or retry request |
| `validator_defense_quality` | deliberately corrupted in-memory canonical object injected directly into the pure validation boundary | `quality_passed=False` with `QUALITY_INVALID_OHLC` or `QUALITY_INVALID_VOLUME`; coverage evidence remains independently evaluated; never reached by a normal raw-provider path |
| `empty_success` | successful typed response containing zero rows | `FAILED/EMPTY_RESPONSE`, one attempt only, no schema/coverage/path/checksum fabrication |
| `immutable_raw` | a verified Parquet file and its checksum before a downstream-policy/re-read operation | identical file digest/bytes and no publication overwrite |
| `late_listing_or_no_trade` | a missing expected minute whose supplied v2 schedule still declares a trading session | fail closed as `COVERAGE_EXPECTED_BAR_MISSING`; no exception, fill, or `VERIFIED` |

`late_listing_or_no_trade` deliberately has no passing variant in this plan.  The
current validation contract derives required minutes solely from the supplied
schedule and has no instrument-specific listing/no-trade exception input.  A
future pass requires independently authoritative, approved evidence and a
separate contract; ARK-67 neither creates nor persists one.  If it occurs in
the live month, the live result is insufficient and Milestone 2 remains blocked.

### 2.3 Fixed harness configuration

The deterministic harness supplies `interval="1m"`, a closed month clock, one
active partition, a one-attempt fake-provider policy when checking the live-gate
shape, and all Plan 02 resource ceilings.  Test cases that exercise the normal
retry contract use its exact default/injected policy and prove its existing
budget semantics separately; they do not change the operational live policy.
The protected test root is created by the test, is empty or explicitly seeded,
and is destroyed by the test framework only after all handles close.  Fixtures
must not use a user/canonical root.

The offline configuration record must retain, in test output or an ignored
artifact, only: fixture name/version, source revision, test command, dependency
lock identity, Python/PyArrow/DuckDB versions, injected clock, schedule digest,
schedule coverage/as-of/source/release/timezone/kind/closure provenance, policy
version, requested/expanded date range, retry/attempt/wait limits,
`partition_checksums` in physical plan order, result enums/counts, and
measurement fields in section 5.  It must exclude
credentials, provider payloads, machine-specific absolute roots, SQL, URLs,
instrument keys, and raw candles.

### 2.4 Fixed synthetic benchmark corpus

The benchmark corpus is distinct from every live invocation.  Its test-only
identity is `benchmark-nse-eq-v1`, with exact synthetic fields
`provider=upstox`, `exchange=NSE`, `segment=NSE_EQ`, `instrument_type=EQ`,
`security_id=INE000A01000`, `symbol=TESTEQ`, `instrument_key=NSE_EQ|TESTEQ`,
and `interval=1m`.  It is a fixture input only: no production source,
configuration, catalog migration, or live command may contain this mapping.

For every corpus schedule, the exact v2 fields are `schema_version=2`,
`source="synthetic-benchmark"`, `source_release="benchmark-nse-eq-v1"`,
`timezone="Asia/Kolkata"`, session `kind="synthetic-regular"`, and closure
reason `synthetic-benchmark-closure-v1`.  For each synthetic calendar month,
the schedule declares the first twenty local calendar dates as sessions from
`03:45:00Z` (inclusive) to `10:00:00Z` (exclusive), and every remaining date as
one closure.  Thus each month has exactly 20 sessions of 375 one-minute bars,
7,500 expected/normalized/published rows, and a fully classified first-to-last
calendar range.  The fixed B01 month is **2024-02**;
its injected clock is `2024-03-01T00:00:00Z`, its expected first timestamp is
`2024-02-01T03:45:00Z`, and its expected last timestamp is
`2024-02-20T09:59:00Z`.  Its nine remaining dates are closures.  These dates,
session times, closures, identity, and row counts are synthetic fixture facts,
not assertions about an actual NSE calendar, RELIANCE listing history, symbol,
or provider identity.

The B02 corpus is exactly **2024-01**, **2024-02**, and **2024-03**, all with
the same 20-session/7,500-row shape, respectively 11, 9, and 11 closures, and an
injected clock of `2024-04-01T00:00:00Z`.  The B05 corpus is exactly the twelve
months **2023-01** through **2023-12**, again 20 sessions and 7,500 rows per
month: 240 sessions, 125 closures, 12 Parquet partitions, and 90,000 rows total,
with expected aggregate bounds
`2023-01-01T03:45:00Z` through `2023-12-20T09:59:00Z`.

There is one canonical range-wide schedule per workload, serialized/digested
under the existing Plan 02 v2 algorithm: B01/B03/B04 cover `2024-02-01` through
`2024-02-29` with `as_of` instant `2024-03-01T00:00:00Z` (canonical serialized
form `2024-03-01T00:00:00.000000Z`); B02 covers `2024-01-01` through
`2024-03-31` with `as_of` `2024-04-01T00:00:00Z` (serialized
`2024-04-01T00:00:00.000000Z`); and B05 covers `2023-01-01` through
`2023-12-31` with `as_of` `2024-01-01T00:00:00Z` (serialized
`2024-01-01T00:00:00.000000Z`).  Every partition in a multi-month command binds
to that command’s one exact schedule digest in its existing validation-policy
version; no per-month substitute digest is permitted.

**Test-only canonical row-generator contract.**  The corpus generator accepts
only `2023-01` through `2024-03`.  For one accepted year/month, let the session
index be `s = day - 1` for its first twenty calendar dates (`0 <= s <= 19`),
the minute index be `0 <= m <= 374`, and the row index be `r = 375*s + m`.
The row timestamp is the corresponding UTC calendar date at `03:45:00Z` plus
`m` minutes.  Let `q = 12*(year - 2023) + (month - 1)` and
`b = 100000 + 10000*q + r`, both exact built-in integers.  Its raw and canonical
`open`, `high`, `low`, and `close` values are respectively the built-in floats
obtained by exactly one conversion each from
`Decimal(b).scaleb(-2)`, `Decimal(b + 4).scaleb(-2)`,
`Decimal(b - 3).scaleb(-2)`, and `Decimal(b + 1).scaleb(-2)`; no intermediate
float arithmetic is permitted.  `volume` is the exact built-in integer
`1000000 + 7500*q + r`, and raw open interest is `None`.

Each generated canonical row uses the identity already fixed above;
`Instrument.isin` equals `security_id`, every `Instrument` derivative metadata
field is `None`, and canonical derivative fields and `oi` are `None`.
`ingested_at` is `00:00:00Z` on the first day of the following calendar month,
`source_version` is `upstox-historical-v3`, and `adjustment_state` is `raw`.
Rows are emitted in ascending month, session, then minute order.  The validation
policy is exactly `nse-equity-month@v1`; `raw_count`, `normalized_count`, and
published row count are each exactly 7,500 per month.  The fake response is
HTTP 200 with empty headers and no error.  These are test-support facts only;
they do not create a production generator, provider payload, or public API.

The exact range-wide v2 schedule digests are
`32b239c6e8924bdf4fb676f0f2b8b070c14869e9d3202badc001b20e863b17fd` for
B01/B03/B04,
`031e66087b1e7ef8d9097e585da5428d777875243c6c06f1b48670e0d2f327b3` for
B02, and
`edf3d0818bf0862dbb171708d6010ef380c77bf44e622ec9166a53e865d8c1db` for
B05.  A generator result whose schedule bytes do not produce the named workload
digest is invalid fixture evidence; it must not substitute a per-month schedule.

Ingestion and repair workloads process at most one partition at a time and use
no worker or queue concurrency.  B05 instead scans its 12 immutable partitions
through one DuckDB thread; it is not a one-file-at-a-time claim, and its FD peak
is measured under section 5.2.

The live gate instead records its owner-selected closed month, catalog-resolved
identity, and authoritative schedule only at execution time.  It does not use,
inherit, or promote any fixed synthetic benchmark date or identity.

## 3. Exact deterministic operational case matrix

Each row is one focused behavior test or a small parameterized family whose
assertions use existing typed values.  `R` means an `IngestionReport`, `P` one
`PartitionResult`, `M` an existing manifest/lifecycle observation, `V` existing
validation evidence, and `Q` a query result.  These abbreviations describe test
evidence only; they introduce no new durable model.  The complete outcome table
in Plan 02 remains authoritative for all cancellation precedence/counts.

| ID | Setup/action | Exact expected typed evidence and no-side-effect proof |
| --- | --- | --- |
| D01 | invalid interval or open month | `R=REJECTED` with `UNSUPPORTED_INTERVAL` or `PARTITION_NOT_CLOSED`; every planned `P=NOT_ATTEMPTED`; request/session/limiter/sleeper calls = 0. |
| D02 | malformed, incomplete, or non-v2 command schedule | `R=REJECTED/SCHEDULE_UNSUPPORTED`, no lease/catalog/provider mutation, and no request. |
| D03 | normal valid missing month | `P=VERIFIED`, one bounded fake request, sealed existing publication evidence, `M=VERIFIED`, `V` coverage/quality pass. |
| D04 | unchanged verified rerun | `R=SUCCEEDED/NONE`, `P=SKIPPED_VERIFIED`, request/session/limiter calls = 0; manifest/checksum/path unchanged. |
| D05 | valid final with absent catalog verification | `P=RECOVERED_LOCALLY`, recovery lifecycle evidence and request/session/limiter calls = 0. |
| D06 | interrupted before `IN_PROGRESS`, during `IN_PROGRESS` at every Plan 02 boundary, between partitions, and after all terminal results | Exact Plan 02 `R` outcome/failure code, ordered `P` values/counts, attempts, and best-effort `M=FAILED/INTERRUPTED` only where that contract requires it.  No later request after cancellation. |
| D07 | crash state: `IN_PROGRESS` with no final, valid final, invalid final, and abandoned exact temp | `INTERRUPTED` is recorded only under held lease; no-final retries only target month; valid final recovers locally with zero request; invalid final is quarantined before request; exact temp never verifies. |
| D08 | `internal_gap` in fresh response | one request then `P=FAILED`, existing `VALIDATION_FAILED`, stable reason `COVERAGE_EXPECTED_BAR_MISSING`; no Parquet publication, no fill. |
| D09 | verified `incomplete_physical` | existing `M` invalidation `COVERAGE_NOT_PASSED`, targeted quarantine/repair evidence, and only that month becomes requestable. |
| D10 | missing file, invalid canonical path, checksum mismatch, unsupported schema, or quality failure in verified evidence | exact existing `FILE_MISSING`, `PATH_INVALID_OR_MISMATCHED`, `CHECKSUM_INVALID_OR_MISMATCHED`, `SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE`, or `QUALITY_NOT_PASSED`; no invented category and no broad/root repair. |
| D11 | `exact_duplicate_raw` | normalization produces one canonical row for the timestamp; raw/normalized counts and bounded duplicate count show removal; valid remaining data can verify. |
| D12 | `conflicting_duplicate_raw` | `P=FAILED` with existing `M=FAILED/NORMALIZATION_FAILED`, no `VERIFIED` or publication, and no claim that Child E rediscovered the removed exact duplicate. |
| D13 | raw impossible OHLC or negative/invalid volume; then pure-validator defense objects | Raw end-to-end input yields `P=FAILED`, `M=FAILED/NORMALIZATION_FAILED`, no publication or retry request.  Separately, deliberately corrupted in-memory canonical objects sent only to the pure validation boundary yield `QUALITY_INVALID_OHLC` or `QUALITY_INVALID_VOLUME`; the normal raw-provider path never reaches that defense branch. |
| D14 | `empty_success` | fresh `M=FAILED/EMPTY_RESPONSE`; exactly one request for the partition/invocation; no retry, schema, coverage, path, or checksum. |
| D15 | `immutable_raw` before/after local observation and a downstream-policy action | same pre/post SHA-256 (and byte comparison if test storage permits); `ALREADY_PRESENT`/skip/recovery only, never overwrite/mutate the canonical raw file. |
| D16 | `holiday_month` and `special_session_month` | `V` passes only from complete digest-v2 date classification and exact supplied session minutes; closure has no required bar, special session has no inferred default-session bars. |
| D17 | `late_listing_or_no_trade` missing in a scheduled session | `V.coverage_passed=False`, `COVERAGE_EXPECTED_BAR_MISSING`, no forward fill and no `VERIFIED`.  It is an explicit unproven blocker, not a waiver. |
| D18 | valid stored artifact with current alias drift; failed/invalid old alias requiring new request | first is `SKIPPED_VERIFIED`/`RECOVERED_LOCALLY`, zero request; second is run-fatal `FAILED` or `PARTIAL` with `MAPPING_MIGRATION_REQUIRED`, zero request. |
| D19 | catalog/lease/unsafe maintenance failure; held lease; substitution/unsafe root | exact `ALREADY_RUNNING`, `CATALOG_UNAVAILABLE`, `LOCAL_REPAIR_BLOCKED`, or `STORAGE_UNSAFE` mapping; no unauthorized repair or provider request. |
| D20 | total attempt budget insufficient/exhausted, provider authentication/authorization/retry-wait fatal stop | exact existing run code and Plan 02 result precedence; no later provider request; wait/attempt ledger remains bounded. |
| D21 | multi-month range with verified, missing, and invalid partitions | ordered full-month plans; verified skip, local recovery, and requests only for independently affected months; result counts equal tuple length. |
| D22 | `1m` verified data queried through existing boundary | `Q` is derived from DuckDB/direct `read_parquet`, is filter/projection-bounded, and agrees with manifest row count/min/max coverage; no candle copy in DuckDB. |

### Required assertions shared by every applicable row

1. Assert complete ordered `PartitionResult` tuples, all count fields, run enum,
   failure enum, provider attempt count, and request count—not only a boolean.
2. Assert a zero-request path leaves token/session factory, limiter, sleeper,
   and HTTP fake untouched.  It may perform the Plan 02-authorized local
   lease/schedule/catalog observation; do not misstate that as no local work.
3. Assert stable sanitized errors/events contain only allowed categories/codes,
   never fixture aliases, paths, payloads, URLs, SQL, or secrets.
4. Assert the exact target path/partition is the only mutable local scope and
   that unrelated disposable partitions retain their pre-test checksum.
5. Assert all rows remain in schedule session bounds, all coverage is UTC
   minute-aligned, and a missing value is represented as failed evidence—not a
   synthetic candle or forward-filled OHLCV.

## 4. Authenticated live operational gate

This is a manual, owner-authorized gate after deterministic evidence and the
full quality/review prerequisites pass.  It is not a test retry loop.  Failure,
insufficiency, missing authority, or unavailable credential leaves ARK-11 and
Sprint 2 open; it never converts to a simulated pass.

### 4.1 Preconditions and exact attempt shape

Before opening a provider session, the operator records the exact candidate
revision, quality-gate evidence, current owner authorization, selected closed
month, `schedule-digest-v2` digest/as-of/source release, catalog-resolution
proof, and caller-created isolated protected root.  The root must be distinct
from shared/canonical/user datasets and must satisfy the existing ARK-34/35
protected-root rules.  It is supplied by the caller; the command/tool must not
create, discover, clean, or broaden it.

Before session creation, the selected physical identity must have no pre-existing
target Parquet partition, current manifest, or immutable target-run history in
that isolated root.  The stable lease file, retained supplied schedule evidence,
and an empty catalog newly initialized through its approved owner during this
invocation are the only permitted pre-existing/initial local facts.  This makes
one request necessary rather than allowing a skip/recovery to masquerade as the
live gate.  It authorizes neither broad cleanup nor creation of the caller root.

The only authorized candle action is:

| Field | Frozen value |
| --- | --- |
| Instrument family | RELIANCE resolved at execution through current master catalog as NSE/NSE_EQ/EQ |
| Requested/physical scope | exactly one canonical, closed calendar month at `1m` |
| Schedule | complete authoritative `schedule-digest-v2` for that month |
| Provider-session opening | at most one lazily opened environment-token session, only after local reconciliation finds a request necessary |
| Historical candle attempts | exactly one total attempt; `max_attempts_per_partition=1`, `max_total_provider_attempts=1` |
| Retry/backoff/defer | no retry; no second candle request for any reason |
| Storage ownership | caller-created isolated protected root; one invocation lease |
| Comparison source | the one `HistoricalResponse` used to normalize/canonicalize/ingest is also the sole sampled comparison source |
| Identity | resolve catalog mapping at execution; no source/package constant for provider key, ISIN, or mapping |

“Same response” means the retained in-memory response already received by the
one permitted request.  The sampled comparison must compare selected canonical
timestamps/OHLCV and raw/normalized row-count evidence from that response to
the rows sealed in the published partition in the same invocation.  It may not
call Historical Candle V3 again, refresh a candle payload, or use a separately
downloaded comparison file.

The sample is `same-response-sample-v1`.  Let `n` be the normalized sorted
response row count, `checksum` the sealed published checksum, and `digest` the
command schedule digest.  For `n >= 1`, initialize the ordered unique index set
with `0`, and add `n - 1` only when `n > 1`.  Its hash seed is the UTF-8 bytes of
the exact ASCII string
`same-response-sample-v1|<checksum>|<digest>|<source_revision>|<n>`; the values
substituted into angle brackets are respectively the lowercase sealed checksum,
lowercase schedule digest, exact Git source revision, and decimal `n`.  For
counter values 0 through 63 in order, calculate
`SHA-256(seed + b"|" + decimal-counter-as-ASCII) mod n`; skip an index already
selected and otherwise append it until eight hash-derived indices have been
added or the 64 counters are exhausted.  Thus the sample contains first/last
plus at most eight unique hash-derived positions and never more than ten rows.
For `n` of one or two it contains only the available endpoint indices; hash
collisions are skipped without replacement, and an exhausted collision budget
simply produces fewer than eight hash-derived positions.  The artifact records
only algorithm version, `n`, selected-count, comparison pass/fail, and mismatch
count—not indices, timestamps, or candle values.

### 4.2 Live result mapping and output safety

A live success requires: catalog resolution; exactly one request; a successful
non-empty response; Plan 02 normalization and schedule-bound validation pass;
sealed publication/manifest/catalog success; and bounded sampled equality with
the same response.  The operational transcript/artifact may contain only:

- gate result (`VERIFIED`, `FAILED`, `REJECTED`, `CANCELLED`, or blocked);
- stable category/code, one request/attempt count, raw/normalized row counts;
- first/last timestamp, schedule digest/version/as-of, checksum, source/code
  revision, policy version, and sampled-comparison pass/fail/count; and
- elapsed/resource measurement fields from section 5.

It must not contain token, authorization header, private provider payload,
instrument key, ISIN, SQL, absolute root/path, host/user name, exception text,
or raw candle values.  The temporary root and generated data stay ignored and
are not committed, attached, or copied to a shared/canonical dataset.

A zero-request local skip is not a live-gate success because it does not prove
the one owner-authorized response.  A provider failure, empty result,
validation failure, missing schedule proof, inability to retain sanitized
evidence, or sampled mismatch is a recorded blocked/incomplete outcome.  No
retry, re-run, or alternative month is authorized by this gate; a later attempt
requires new owner authorization and a separately recorded decision.

## 5. Measurement and benchmark protocol

The objective is a reproducible baseline, not a universal performance promise.
Measurements are observability evidence for the existing path and introduce no
manifest/catalog/public contract field.  Use a bounded ignored report or test
assertion record and retain only sanitized values.

### 5.1 Workloads and query proof

| Workload ID | Exact workload | Success proof |
| --- | --- | --- |
| B01 `ingest` | the fixed synthetic 2024-02 7,500-row month: normalize, validate, publish, and persist catalog terminal evidence in a fresh disposable root | existing sealed evidence and `VERIFIED`; one fake/known request, 7,500 published rows |
| B02 `resume` | the exact three-month 2024-01..03 corpus, each 7,500 rows: January and February `VERIFIED`; March has a valid final with no catalog verification | `SUCCEEDED/NONE`, exactly two `SKIPPED_VERIFIED`, one `RECOVERED_LOCALLY`, three planned results, and zero historical requests, provider-session-factory calls, or limiter calls |
| B03 `repair` | the unchanged February command/schedule has one 2024-02 target with a valid 7,500-row final but a `VERIFIED` manifest checksum differing at the first hex nibble (`0` becomes `1`; every other value becomes `0`); the January verified control is explicitly out of plan | exact `CHECKSUM_INVALID_OR_MISMATCHED`, February-only quarantine/request/publication, one fake request and one repair; February `partition_checksums` has length one.  January has identical pre/post control evidence, is absent from results/request count/quarantine, and is neither mutated nor queried through the February command.  Other corrupt/incomplete modes remain D09/D10 correctness cases, not timed B03 variants. |
| B04 `query_month` | existing DuckDB catalog opens one disposable-root database and executes a parameterized/filter-bounded direct Parquet scan for the synthetic identity and 2024-02 | `min(ts)=2024-02-01T03:45:00Z`, `max(ts)=2024-02-20T09:59:00Z`, `count(*)=7,500`, all agreeing with sealed manifest evidence |
| B05 `query_history_shape` | the fixed synthetic 12-partition 2023-01..12 corpus (90,000 rows, no provider data) through a direct Parquet filtered aggregate | `count(*)=90,000` and fixed corpus bounds; DuckDB stores no candle rows |

Every benchmark DuckDB query (B04 and B05) uses exactly one connection and,
before the query, executes `SET threads = 1` and `SET memory_limit = '256MB'`.
It then executes `SET temp_directory = '<iteration-disposable-protected-root>/duckdb-tmp'`.
It never creates a DuckDB candle table.  B05 scans all 12 immutable Parquet
partitions through that one connection/thread, and the external FD sampler
measures the scan’s peak.

#### B03 out-of-plan control provenance

The B03 January verified control is test-only, explicitly outside the unchanged
February command’s plan, and is not a second plan/result/query target.  It never
appears in that command’s `IngestionReport.results` or physical-plan-order
`partition_checksums`, causes no provider request, and is neither quarantined,
mutated, nor queried through the February command.  Its only bounded sanitized
observation is `control_partition_evidence_v1`, whose fields are in this exact
order: `physical_identity`, `pre_physical_checksum`, `post_physical_checksum`,
`pre_manifest_fingerprint`, `post_manifest_fingerprint`,
`manifest_bound_schedule_digest`.

`physical_identity` is the ordered tuple `(provider, exchange, segment,
instrument_type, security_id, interval, year, month)`.  Every checksum, digest,
and fingerprint is lowercase SHA-256.  The pre/post physical checksums must be
equal; the pre/post manifest fingerprints must be equal; and
`manifest_bound_schedule_digest` is the January control’s own existing digest
extracted from its validation-policy provenance and is identical before/after.
No current February schedule replaces it.  This sanitized evidence emits no
alias, path, or raw candle value.

`control_manifest_fingerprint_v1` is the lowercase SHA-256 of UTF-8 canonical
JSON for a complete existing `PartitionManifest`.  The named **test-only**
projection adds no persisted production schema.  Its top-level fields are
exactly `manifest_schema_version`, `plan`, `ingestion_run_id`,
`candle_schema_version`, `state`, `validation_outcome`,
`validation_policy_version`, `actual_from_ts`, `actual_to_ts`, `row_count`,
`checksum_sha256`, `canonical_path`, `source_version`, `created_at`,
`attempt_started_at`, `updated_at`, and `failure_category`.  Its nested `plan`
contains exactly `provider`, `instrument_key`, `security_id`, `symbol`,
`exchange`, `segment`, `instrument_type`, `interval`, `year`, `month`,
`from_date`, and `to_date`; no field may be omitted.

Canonicalization is exactly
`json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))`
encoded as UTF-8 before SHA-256.  Enums serialize as `.value`; dates use
`YYYY-MM-DD`; UTC datetimes use RFC3339 with literal `Z` and exactly six
fractional digits; `None` becomes JSON `null`; and exact ints, bools, and
strings are preserved.  The complete projection is used only to compute the
fingerprint and is not emitted, so its aliases/path remain outside sanitized
output.

The live gate may add a single B01/B04 record for its one response, but it must
not add requests.  B05 is a shape/resource test only, not a claim about full
historical coverage or a substitute for multi-stock scale work.

### 5.2 Required measurement fields and units

Every measured iteration records the following fields.  Resource fields have no
`null` pass path: invalid sampling blocks the resource evidence.

| Field | Unit/type | Provenance |
| --- | --- | --- |
| `workload_id`, `iteration_kind`, `iteration_index` | stable label, `warmup`/`measured`, positive integer | harness configuration |
| `source_revision`, `source_tree`, `lock_identity` | Git identifiers / lock digest | exact candidate checkout |
| `python_version`, `platform`, `cpu_model`, `cpu_count`, `memory_total_bytes`, `filesystem_type` | sanitized environment strings/integers/bytes | local runtime/environment probe; no host/user/path |
| `duckdb_version`, `pyarrow_version`, `os_version` | version string | loaded dependency/runtime |
| `fixture_id`, `fixture_version`, `schedule_digest`, `policy_version`, `requested_range`, `physical_month_count` | stable labels/digest/date/count | injected fixture and Plan 02 command |
| `partition_checksums` | ordered tuple of `(year, month, lowercase_sha256)` | sealed partition evidence in physical-plan order; length one for B01/B04 and the live one-partition checksum remains the existing sealed `checksum` |
| `elapsed_wall_ms`, `elapsed_cpu_ms` | milliseconds | monotonic clock/process CPU clock around whole workload |
| `phase_elapsed_ms` | milliseconds by normalize, validate, publish, catalog, query; `null` when not applicable | injected phase timers |
| `rows_raw`, `rows_normalized`, `rows_published`, `bytes_parquet` | count/count/count/bytes | normalization, sealed publication evidence |
| `throughput_rows_per_s` | rows/second | `rows_normalized / elapsed_wall_s`; `null` if elapsed is zero |
| `request_count`, `provider_attempt_count`, `retry_count`, `resume_count`, `repair_count` | nonnegative counts | fake/live session and existing report/lifecycle results |
| `peak_rss_bytes`, `open_fd_start`, `open_fd_peak`, `open_fd_end` | nonnegative bytes/counts | external parent sampler; invalid/missing resource evidence blocks |
| `sampler_method`, `psutil_version`, `sampler_sample_count`, `sampler_max_gap_ms`, `resource_evidence_status` | stable method/version/count/milliseconds/status | pinned dev/test `psutil` parent sampler |
| `query_result_count`, `query_min_ts`, `query_max_ts`, `query_elapsed_ms` | count/timestamps/milliseconds | existing DuckDB/direct-Parquet query result and monotonic timer |
| `outcome`, `failure_code`, `partition_outcomes` | existing enum/ordered enum tuple | `IngestionReport`, `PartitionResult` |

All derived arithmetic retains enough precision to reproduce the displayed
value.  Wall time is monotonic, not wall-clock time.  Memory/FDS are process
measurements, not claims of whole-machine use.  No measurement aggregates runs
from different source revisions, fixtures, dependencies, or environments.

Each warm-up and measured iteration runs in a fresh child process.  A parent
measurement process, using the pinned dev/test `psutil` dependency, externally
monitors the child on Darwin with `Process.memory_info().rss` and
`Process.num_fds()` under this frozen ordered protocol:

1. The child initializes, sends exactly `READY`, then blocks and must not start
   the workload.
2. The parent receives `READY`, captures the counted start RSS/FD sample while
   the child remains blocked, then sends exactly `START` to release it.
3. The child receives `START`, runs the workload, closes every workload-owned
   handle, sends exactly `DONE`, then blocks and must not exit.
4. The parent receives `DONE`, captures the counted end RSS/FD sample while the
   child remains alive and blocked, then sends exactly `EXIT` to release it.
5. The child receives `EXIT` and exits.

`READY` and `DONE` are child signals; `START` and `EXIT` are parent
acknowledgements/releases.  No signal doubles as an acknowledgement.  The 10ms
monotonic sampling starts strictly after the counted start sample and continues
through the counted end sample.  Both boundary samples are included in
`sampler_sample_count` and peak calculations.  The parent records sampler
method/version, sample count, and maximum observed inter-sample gap.  A sampling
exception, unsupported `num_fds()`, fewer than two samples, or a maximum gap
above 50ms makes `resource_evidence_status=INVALID` and blocks the workload’s
resource acceptance; it never becomes null/partial pass evidence.  The parent
sampler is measurement-only and does not alter the production task, queue,
worker, or provider cardinality.  On every valid controlled iteration,
`open_fd_end == open_fd_start`.

Before ARK-68q adds locked `psutil` to dev/test
tooling, it must record the concrete dependency/license/security/maintenance
assessment and stop for Sol/owner direction if that assessment is unacceptable.

### 5.3 Warm-up, repetition, and environment comparability

For each B01--B05 configuration, run **one warm-up followed by five measured
repetitions** in the same process invocation class, with a fresh disposable
root for each mutation workload and a fresh query connection for each query
iteration.  Do not report a warm-up as a sample.  A cancelled, failed, or
invalid iteration is recorded with its typed outcome and is not discarded or
replaced.  If fewer than five valid measured iterations exist, report the set
as insufficient for a regression threshold; do not average in a fabricated
success.

Compare a candidate to a baseline only when all of these match: workload and
fixture version, schedule digest/range/as-of/source/release/timezone/kind and
closure provenance, policy version, ordered `partition_checksums`, source data
shape, command and resource limits, Python/lock/PyArrow/DuckDB major-minor
versions, pinned `psutil` version and sampler method, CPU architecture/count,
filesystem type, and measurement method.  OS patch,
frequency governor, thermal state, background load, cache state, or available
memory differences are recorded as comparability warnings.  A non-comparable
result is useful observation but cannot pass/fail a performance regression.

No network latency baseline is derived from the live one-attempt gate.  Network
and provider timing are reported separately and never used to label a local
storage/query regression.

### 5.4 Reproducible regression policy and stop rules

For each workload/metric, the baseline and candidate summary is exactly the
five valid, comparable measured values sorted ascending as
`x1 <= x2 <= x3 <= x4 <= x5`: `median=x3`, `minimum=x1`, `maximum=x5`, and
`spread=x4-x2`.  Raw ordered samples and that four-value summary are retained;
warm-ups, failures, cancellations, and non-comparable samples are never
discarded, substituted, or moved between sets.  A baseline is stable only when
it has five valid comparable samples and either (a) `median=0` and `spread=0`,
or (b) `median>0` and `spread <= median`.  A non-comparable or unstable baseline
has deterministic status `UNSET` and cannot pass the benchmark gate.  ARK-71b
may record that `UNSET` outcome or reject threshold adoption; it may not tune,
drop, rerun, or select samples post hoc.

For a stable baseline, the exact data-derived tolerance is
`three_spreads = 3 * baseline_spread`.  The candidate comparison uses its five
valid comparable samples and the following fixed directions:

| Metric family | Baseline threshold | `REGRESSION_SUSPECTED` when candidate median is |
| --- | --- | --- |
| Lower is better: `elapsed_wall_ms`, applicable phase/query elapsed, `peak_rss_bytes`, and `open_fd_peak - open_fd_start` | `baseline_median + three_spreads` | greater than the threshold |
| Higher is better: `throughput_rows_per_s` | `max(0, baseline_median - three_spreads)` | less than the threshold |
| Exact invariants: request/attempt counts, checksum, lifecycle/result evidence, and FD closure | no statistical threshold | different from the workload’s specified count/evidence, or any measured `open_fd_end != open_fd_start` |

Peak RSS and FD evidence must also preserve the existing Plan 02 resource
cardinality and closure bounds.  This policy contains no universal latency, memory, throughput, or FD
number: every numeric threshold is derived solely from the recorded baseline
spread.  A candidate with fewer than five valid comparable values, an unstable
candidate set under the same stability test, or a null required reference-machine
resource field remains `UNSET`, not pass.

For the controlled benchmark, FD closure is an exact per-iteration invariant:
`open_fd_end == open_fd_start`.  Either a greater or a smaller ending count is
a failed/uncontrolled measurement, never a statistical pass or a value to be
absorbed by the FD-peak threshold.

On `REGRESSION_SUSPECTED`, stop optimization/release acceptance, preserve the
sanitized samples, rerun only the same bounded workload once to rule out a
measurement error, and escalate the material finding to Sol.  Two materially
identical measurement failures after repair trigger the workflow circuit
breaker.  Any correctness, checksum, request-count, lifecycle, or resource-bound
failure stops immediately and is not averaged.

### 5.5 Durable one-shot baseline artifact

ARK-111 owns the persistence boundary and ARK-92 owns its single collection.
The artifact is canonical UTF-8 JSON with `ensure_ascii=True`, sorted keys, one
trailing newline, and a hard maximum of 4,000,000 bytes. Its top level is
exactly `schema_version=ark92-baseline-artifact-v1` plus the ordered B01--B05
`results`. Each result retains exactly one warm-up, five measured records, the
typed retained/insufficient status and counts, and `threshold_claim=null`.
Records contain only the section 5.2 fields and their complete comparability
identity; strings are at most 512 bytes, ordered evidence at most 366 items,
and integer evidence at most signed 64-bit maximum. Failed, cancelled, and
protocol-invalid records retain zero activity/success evidence and use the
closed outcome/failure/resource matrix. No path, SQL, provider alias,
instrument key, credential, raw payload, or live market value is serializable.

Output and disposable work root must be distinct, absent absolute paths below
the repository's gitignored `artifacts/` directory. Directories are private,
the final file is mode `0600`, publication never overwrites, and a substituted
work-root identity or permission change stops before publication. Run exactly
once from the repository root:

```bash
uv run --extra dev python tests/market_data/ark92_benchmark_baseline_collection.py \
  --output "$PWD/artifacts/benchmarks/ark92-b01-b05-baseline-v1.json" \
  --work-root "$PWD/artifacts/benchmarks/ark92-b01-b05-work-v1"
```

After successful collection, record the artifact byte count and SHA-256.
ARK-93 consumes that exact immutable file; it may not edit, replace, select, or
rerun samples. A failed/insufficient collection remains evidence and does not
authorize another collection without the section 5.4 measurement-error rule.

## 6. Failure, cancellation, safety, and provenance rules

The harness and live gate inherit Plan 02’s stop conditions.  The following
operational rules make them auditable without creating alternative behavior:

- Cancellation checks and exact before/during/between/after mappings are those
  in Plan 02; the harness must parameterize every listed boundary.  It never
  transform cancellation into retry or erase charged attempts.
- After authentication, authorization, catalog, unsafe-repair,
  mapping-migration, retry-wait-bound, or total-attempt-budget fatal stop, no
  later partition request occurs.  After a post-attempt Child H escape, report
  the actual invocation attempt delta/current readable manifest as Plan 02
  requires and stop; never manufacture a terminal state or zero attempts.
- A validation, normalization, publication, physical-schema, checksum, or
  empty-response failure is evidence, not permission to loosen validation,
  overwrite raw data, or make an unapproved duplicate request.
- Mutating repair is limited to the one exact disposable partition under the
  held lease.  Absent a proven safe target/quarantine, return the existing
  zero-request `LOCAL_REPAIR_BLOCKED` behavior.  Never touch a user root,
  sibling, broad glob, catalog outside the target transaction, or canonical
  shared dataset.
- Schedule bytes are content-addressed/no-clobber and manifest recovery binds
  to the old digest.  Present corrupt schedule evidence is never replaced;
  current calendars never substitute for a manifest-bound digest.
- Credentials are environment-provided only after a request is necessary.  Do
  not inspect, log, serialize, fixture, shell-expand, or test against real
  credentials.  Provider/private response data and generated artifacts stay
  ignored.  Bounded sanitized logs are retained only as permitted above.

## 7. Milestone 2 acceptance crosswalk

Every row is mandatory.  `Pass` requires the exact named evidence at the
candidate revision; a missing, rejected, or unproven row blocks ARK-11/Sprint
2 rather than being waived.

| Milestone 2 requirement | Required proof in this plan | Pass condition / blocker |
| --- | --- | --- |
| Repeated download is idempotent | D03, D04, B02 | verified rerun has `SKIPPED_VERIFIED`, zero historical requests, identical sealed evidence; otherwise blocked. |
| Interruption is safe | D06, D07 | Plan 02 typed cancellation/crash mapping, no valid-looking temp/partial artifact, target-only restart; otherwise blocked. |
| Corrupt/incomplete partition is detected and repaired | D09, D10, B03 | exact invalidation, target-only safe repair/recovery, unrelated control unchanged; otherwise blocked. |
| Internal gaps are detected; no `MAX(ts)` shortcut | D08, D09 | missing interior scheduled minute fails coverage with stable reason; otherwise blocked. |
| Duplicates and impossible OHLC fail correctly | D11--D13 | exact duplicate normalization/count evidence; raw conflicting/invalid OHLC/volume input fails through existing `NORMALIZATION_FAILED`, while pure-validator defense objects prove `QUALITY_INVALID_OHLC`/`QUALITY_INVALID_VOLUME`; otherwise blocked. |
| Empty successful response is explicit | D14 | exact `EMPTY_RESPONSE`, one attempt/no fabricated artifact; otherwise blocked. |
| Raw candle files remain immutable | D15 | pre/post digest/bytes equal; no overwrite; otherwise blocked. |
| Holidays and special sessions are explicit | D16 and complete v2 digest checks | schedule evidence classifies every date and validation follows supplied minutes; otherwise blocked. |
| Late listing / legitimate no-trade handling | D17 and live observation | current contract fails closed without authoritative exception evidence; any live instance blocks M2 until separately approved evidence/contract exists. |
| No forward fill | D08, D17 | no synthetic timestamp/OHLCV; coverage fails visibly; otherwise blocked. |
| Random/monthly sample matches direct response | section 4 same-response comparison | bounded deterministic sample agrees with the one ingestion response; no second request; otherwise blocked. |
| Query proof | D22, B04/B05 | DuckDB/direct Parquet aggregate agrees with manifest; no DuckDB candle copy; otherwise blocked. |
| Request minimal and zero-request resume | D04, D05, D18, B02 | token/session/limiter/HTTP untouched on local paths; otherwise blocked. |
| Resource/performance evidence | B01--B05, section 5 | comparable raw samples/provenance and evidence-based threshold status; no universal target claim; otherwise blocked from benchmark acceptance. |
| Live representative proof | section 4 | one authorized closed month, one total attempt, catalog resolution, v2 schedule, isolated root, sanitized same-response comparison; failure/insufficiency blocks. |

## 8. Atomic future handoffs and dependency order

The Sprint 2 list is a **backlog candidate set**, not a commitment.  Before any
child is moved to Ready, its owner must record the one-sentence predicate,
iteration budget, accepted specification revision, dependencies, and the
high-risk Sol review path.  Each candidate below has one observable outcome and
one primary reason to change.  Implement one only under the repository’s
single-writer/single-WIP rule, strict red-green-refactor TDD, and full relevant
quality gate.

Current ARK-68 is not atomic: it combines fixtures, validation cases,
instrumentation, query proof, and benchmark policy.  Before any implementation,
the coordinator must make ARK-68 cease to be an executable Task and reclassify
or replace it as the appropriate non-executable tracking parent in Linear.
The coordinator must then create real atomic child issue IDs with explicit
blocker links before any child enters Ready.  The suffixes below are planning
placeholders only; they neither create Linear issues nor satisfy the execution
gate.

| Candidate placeholder | Case ownership | One observable outcome / primary reason to change | Done | Depends on |
| --- | --- | --- | --- | --- |
| ARK-68a fixed fixture/schedule corpus | benchmark fixture support | The offline corpus produces the fixed canonical rows and range-wide v2 schedule bytes.  Reason: deterministic inputs. | Done when one credential-free fixture call returns the frozen corpus and its exact command schedule digest. | Plan 03 conditionally active |
| ARK-68b coordinator-admission proof | D01, D02 | One invalid interval/open-month/schedule command returns its exact preflight rejection before ownership or provider activity.  Reason: command admission. | Done when every named coordinator admission case has its exact `REJECTED` code and zero later side effects. | 68a |
| ARK-68c lease/storage-refusal proof | D19 lease contention and storage unsafe | One held or unsafe root returns its exact ownership refusal without provider activity.  Reason: protected-root ownership. | Done when lease contention and unsafe-root cases return their existing refusal code with no unauthorized mutation or request. | 68a |
| ARK-68d catalog-failure proof | D19 catalog failure | One unavailable/corrupt catalog returns `CATALOG_UNAVAILABLE` before provider-session creation.  Reason: catalog availability. | Done when the catalog failure report has its exact typed code and zero provider activity. | 68a |
| ARK-68e local-repair-refusal proof | D19 unsafe local maintenance | One unsafe target/quarantine refusal returns `LOCAL_REPAIR_BLOCKED` without a request.  Reason: repair safety. | Done when the unsafe local-repair case has its exact zero-request failure evidence. | 68a |
| ARK-68f provider-auth/authz-stop proof | D20 authentication and authorization | One provider authentication or authorization failure stops later provider work with its exact run code.  Reason: credential boundary. | Done when each auth/authz failure preserves charged attempts and makes no later request. | ARK-68i |
| ARK-68g attempt-budget-stop proof | D20 attempt-budget insufficient/exhausted | One insufficient or exhausted total-attempt budget returns its exact preflight/runtime stop.  Reason: bounded requests. | Done when the budget case records the existing code and never exceeds its request cardinality. | 68a |
| ARK-68h retry-wait-stop proof | D20 retry-wait bound | One over-bound retry/limiter wait returns `RETRY_WAIT_BOUND_EXCEEDED` before another wait or request.  Reason: bounded waiting. | Done when the wait case preserves the charged ledger and makes no later provider request. | ARK-68i |
| ARK-68i first-request verification proof | D03 | One missing synthetic month reaches `VERIFIED` through exactly one bounded fake request.  Reason: baseline acquisition evidence. | Done when the 7,500-row B01 partition has sealed verified evidence after one fake request. | 68a |
| ARK-70 zero-request resume proof | D04, D05 | A verified or locally recoverable partition completes without provider/session/limiter use.  Reason: request-minimal idempotency. | Done when the named local states return the exact skip/recovery result with zero historical requests. | ARK-68i |
| ARK-68j cancellation/crash-state proof | D06, D07 | One injected cancellation/crash boundary preserves the exact Plan 02 ordered lifecycle/report evidence.  Reason: interruption safety. | Done when every named before/during/between/after boundary has its exhaustive typed outcome and no later request. | ARK-68i |
| ARK-68k schedule-coverage/no-fill proof | D08, D16, D17 | One schedule-bound validation run classifies an internal gap, closure, special session, or unproven no-trade case without fabricating a bar.  Reason: coverage integrity. | Done when the named schedule cases return their exact coverage evidence and no forward-filled row. | 68a |
| ARK-68l verified-physical-invalidation proof | D09, D10 | One verified physical mismatch becomes the exact existing invalidation category.  Reason: trustworthy local evidence. | Done when every named missing/path/checksum/schema/coverage/quality observation selects only its existing invalidation category. | ARK-68i |
| ARK-68m normalization/quality/empty classification proof | D11, D12, D13, D14 | One raw response classifies exact duplicate, conflict, invalid OHLC/volume, or empty success through the existing terminal mapping.  Reason: source-data integrity. | Done when each named raw/defense input has its required normalization, validation, or empty-response evidence and no unauthorized publication/retry. | ARK-68i |
| ARK-68n raw-immutability proof | D15 | One verified raw partition retains identical bytes/checksum across observation and downstream-policy work.  Reason: immutable source evidence. | Done when the before/after digest and bytes are equal without a publication overwrite. | ARK-68i |
| ARK-68o mutable-alias reconciliation proof | D18 | One stored-alias difference yields either local recovery/skip or exact zero-request migration stop.  Reason: physical-identity stability. | Done when valid old aliases avoid a request and a required fresh old-alias request returns `MAPPING_MIGRATION_REQUIRED`. | ARK-70 |
| ARK-68p ordered range-reconciliation proof | D21 | One mixed three-month range emits the ordered skip/recover/request tuple for only independently affected months.  Reason: request selection. | Done when result order/counts and request cardinality equal the Plan 02 reconciliation decision. | ARK-70, ARK-68l |
| ARK-68q bounded measurement recorder | B01--B05 fields | One fresh-child workload iteration records the complete section 5 provenance/resource measurement or an explicit blocked resource result.  Reason: reproducible instrumentation. | Done when the pinned-`psutil` assessment is recorded before dependency addition and one child/parent sample record satisfies the fixed sampler method or blocks. | 68a |
| ARK-68r existing-boundary query proof | D22, B04, B05 | One configured DuckDB direct-Parquet query returns the frozen aggregate without a candle table.  Reason: query-boundary evidence. | Done when B04/B05 use the fixed one-connection settings and return their manifest-consistent aggregate. | 68a, ARK-68q |
| ARK-69 live one-month gate | section 4 | One owner-authorized closed RELIANCE month yields one sanitized same-response result under exactly one attempt/no retry.  Reason: authenticated representative proof. | Done when the one permitted response is ingested and compared under the live gate without a second request. | ARK-68b--ARK-68r, ARK-70, ARK-73, full gate/review, owner authorization |
| ARK-73 targeted disposable repair proof | B03 | One exact checksum-mismatched disposable partition alone repairs while its control remains unchanged.  Reason: repair isolation. | Done when B03 records the February target-only invalidation/quarantine/request/publication and the out-of-plan control evidence. | ARK-68i, ARK-68l, ARK-68q |
| ARK-71a baseline collection | section 5 samples | Five comparable B01--B05 measured samples are retained without a threshold claim.  Reason: establish evidence. | Done when each workload has its five raw comparable measurements or an explicit blocked status. | ARK-68q, ARK-68r, ARK-70, ARK-73 |
| ARK-71b threshold decision | section 5.4 | One deterministic threshold status is derived from ARK-71a samples.  Reason: regression policy. | Done when every workload is `UNSET`, threshold-accepted, or rejected by the frozen sample rule without sample tuning. | ARK-71a |
| ARK-72 M2 pre-merge crosswalk | section 7 | One candidate-revision dossier resolves every section 7 row, selected denominator, gates/review, carryover, and limitations.  Reason: acceptance reconciliation. | Done when every mandatory crosswalk row is evidenced or explicitly blocks acceptance. | ARK-69, ARK-70, ARK-73, ARK-71b |

Each placeholder above has exactly one observable outcome, one primary reason
to change, and one-sentence Done condition.  ARK-72 is a bounded
evidence/reconciliation task, not a claim that it will merge or close Linear.
Only after the required Linear reclassification/replacement, real child creation,
and blocker recording may the coordinator reconcile their actual IDs for
scheduling; this document does not alter issue tracking.

Required order is:

```text
68a -> {68b, 68c, 68d, 68e, 68g, 68i, 68k, 68q}
68i -> {70, 68f, 68h, 68j, 68l, 68m, 68n}
70 -> {68o, 68p}
68l + 68q -> 73
68a + 68q -> 68r
{68b--68r, 70, 73} -> 71a -> 71b
{68b--68r, 70, 73} + full deterministic gate + owner authorization -> 69
69 + 70 + 73 + 71b -> 72
```

Read-only review/reconciliation never runs in parallel with a repository
writer.  Each code candidate has a Sol High combined independent review because
it touches the high-risk data/provenance/provider/storage boundary; no duplicate
Terra review applies to the same exact candidate.

## 9. Definition of done and residual limitations

ARK-67 is done when this document is the accepted bounded operational contract;
it specifies deterministic fixtures/cases, the one-attempt live gate,
measurements/provenance/threshold method, stop/safety rules, full Milestone 2
crosswalk, and atomic candidate handoffs without changing production contracts.
Its documentation change requires focused documentation checks, not artificial
tests-first evidence.  It does not mean that any Milestone 2 behavior has been
implemented, run live, benchmarked, reviewed, merged, published, or marked done
in Linear.

Residual limitations are explicit:

- A one-month RELIANCE proof is representative operational evidence, not
  provider-wide, multi-instrument, historical-coverage, performance, or
  research-strategy validation.
- The existing schedule contract has no late-listing/legitimate-no-trade
  exception input; these remain fail-closed blockers pending separately
  authoritative, approved work.
- Initial thresholds are intentionally unset until comparable measurements
  exist; no universal latency/memory target is claimed.
- The live attempt is credential/provider dependent and can correctly leave the
  milestone blocked.  Its isolated artifacts are intentionally non-reproducible
  outside the authorized environment, while its sanitized provenance is
  traceable.
- Nothing here authorizes a public interface, dataset retention, broader
  universe, second provider request, or a relaxation of Plan 02’s resource,
  lifecycle, provenance, and ownership constraints.
