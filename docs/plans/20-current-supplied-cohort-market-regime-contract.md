# Current supplied-cohort Market Regime contract

Status: **PLANNED — specification only for GitHub Issue #116; no implementation, test, review, CI, merge, or publication evidence**
Contract revision: `current-supplied-cohort-market-regime@v1`
Schema revision: `current-supplied-cohort-market-regime-schema@v1`
Risk: **R3 / High** — financial-research integrity, immutable evidence, private current-data provenance, and a new cross-boundary public fact contract
Outcome owner and acceptance authority: **repository owner through GitHub Issue #116**; residual-risk acceptance remains with that owner.
Depends on: [Plan 19](19-current-supplied-cohort-market-data-contract.md), the current/live sequence in [Upcoming Sprints Overview](../upcoming_sprints_overview.md), and retained official NSE Capital Market schedule evidence.
Preserves: frozen [Plan 12](12-market-regime-contract.md), deferred [Plan 18](18-provided-cohort-historical-ohlcv-contract.md), and Sprint 10's current-fact archive contract.

## Outcome, authority, and lifecycle

Issue #116's observable outcome is one deterministic, aggregate-only current
Market Regime fact for the exact owner-supplied Sprint-10 cohort: compare every
member's completed decision close with its completed close exactly 20 completed
exchange sessions earlier, then report inclusive 60% breadth or one whole-result
insufficiency. It is not a historical Nifty 50 claim, backtest, forecast,
recommendation, trade signal, order, sector/news/event fact, or Market Structure
work.

This is R3 because an erroneous current regime can cross the deterministic-tool
boundary into financial research, immutable evidence and private owner data are
consumed, and recovery cannot make a previously emitted fact trustworthy. Issue
#116 and the owner direction authorize implementation within this approved epic;
before implementation can be accepted, it must have focused evidence, an
independent exact-revision review, applicable full repository/hosted security and
CI gates, and an owner lifecycle decision. This plan is a durable specification,
not evidence that those later acceptance activities occurred.

| Lifecycle area | Impact | disposition in this plan |
| --- | --- | --- |
| Upstream requirements and decisions | Affected | Issue #116 and Plan 19 provide the active current-data boundary; Plan 12 remains unchanged and frozen. |
| Consumers and compatibility | Affected | This adds a distinct versioned current supplied-cohort fact; it does not alter the `nifty50-market-regime@v1` reader/writer or Plan 18 historical evaluator. |
| Evidence, retention, and provenance | Affected | Read exactly 21 existing immutable Sprint-10 objects by content ID and retained official schedule evidence; no raw OHLC reconstruction. |
| Privacy and security | Affected | Archive/member facts and paths stay private; public results contain aggregate counts and opaque hashes only. |
| Operations and recovery | Affected | Read-only, bounded, no-network evaluation; unsafe/ambiguous evidence returns a whole insufficiency. A later corrected fact has a new identity and never rewrites an emitted report. |
| User/operator reference | Affected | One bounded CLI/API surface and this Sprint 11 record define input, output, and exit semantics. |
| Rollout, coexistence, and retirement | Affected | New `@v1` coexists only as a separate contract. No alias, fallback, or migration of Plan 12/18 representations is permitted. |
| Funding, third parties, and provider authority | Not affected | The design introduces no provider, licence, source, acquisition, credential, or network authority. |

### Assumptions and stop conditions

1. The owner supplies one valid 1–50 member cohort through Sprint 10 and can
   supply the same `cohort_identity_sha256`, 21 archive IDs, and one retained
   schedule binding: `schedule_evidence_sha256`,
   `schedule_source = "nse-authoritative-calendar"`, and exact
   `schedule_source_release = "sha256:<64 lowercase hex>"`. The repository
   owner selects this already-retained evidence under Issue #116.
2. A selected archive object can be decoded under the protected root into the
   persisted Sprint-10 v1 envelope fields: `code_identity`,
   `cohort_identity_sha256`, `contract_version`, `facts`, `ledger`, `partials`,
   `report`, and `request_identity_sha256`. The persisted request identity is an
   opaque Sprint-10 binding; v1 did not persist a nested request or cohort
   manifest, so this contract does not claim to reconstruct either.
3. Retained `ExpectedSessionSchedule` v2/v3 evidence resolved by exact digest
   and owner-bound source/release can prove the exact completed NSE Capital
   Market session sequence through its `as_of`, sessions, and closures. It may
   prove only continuity and session completion; it supplies no OHLC, close,
   member, source, or price fact.
4. The requested decision session is the latest official session whose scheduled
   close is at or before `decision_cutoff` and whose full 21-session sequence is
   provable. `as_of` is timely only, never a completion cutoff. If a closure,
   special-session scope, close time, digest, source/release, `as_of`, or
   schedule coverage is unresolved, evaluation stops with insufficiency.

Loss of any assumption is a stop condition for an observed result. It does not
permit provider fallback, raw retained-candle queries, partial-session
substitution, a shorter denominator, a prior label, or a reconstructed history.

## Decision, options, and compatibility

| Option | Decision | Reason and consequence |
| --- | --- | --- |
| Do nothing | Rejected | Leaves Issue #116's current-regime outcome unavailable despite Sprint-10 current immutable evidence. |
| Reuse frozen Plan 12 (`nifty50-market-regime@v1`) | Rejected | Plan 12 is exact 50 PIT members, 22 schedule positions and corporate-action proof; changing it would violate its frozen semantics and confound its historical record. |
| Reuse Plan 18 supplied historical OHLCV evaluator | Rejected | Its `FIXED_COHORT_RETROSPECTIVE` supplied-bar input neither consumes immutable current-fact archives nor proves official-session continuity. |
| Query/recompute raw retained OHLC or contact a provider | Rejected | It would bypass the Issue #116/Sprint-10 immutable temporal evidence boundary, add I/O/provider authority, and could introduce hindsight. |
| Read 21 named immutable Sprint-10 archive objects, prove their grid with retained official schedule evidence, then apply a pure Decimal reducer | **Accepted** | Smallest current-only path that binds the owner cohort, content, timing, and no-omitted-session proof without acquiring data. |

The accepted contract is deliberately incompatible with Plan 12 and Plan 18 at
the representation level. It shares only the mechanics of exact Decimal
comparison, `ADVANCE`/`DECLINE`/`UNCHANGED`, and inclusive 60% breadth. It
neither supersedes nor reinterprets Plan 12's frozen
`nifty50-market-regime@v1`; it neither activates nor replaces Plan 18's deferred
historical contract. A future change to the cohort cardinality, 21-ID rule,
20-position comparison, schedule authority, reason taxonomy, schema, or
canonical bytes requires a new contract revision and an explicit supersession
record that preserves this one.

Tradeoff: explicit content IDs and whole-result failure increase operator input
and make a write-only/unindexed archive less convenient. They prevent directory
scans, accidental candidate selection, private data exposure, omitted sessions,
and hindsight selection. The unresolved operational risk is how callers obtain
21 IDs because current Sprint-10 reports do not publish archive IDs; that is an
implementation prerequisite, not permission to scan archives or weaken the
input rule.

## Scope and deterministic rule

The contract consumes the exact Sprint-10 owner-supplied cohort of size `N`,
where `1 <= N <= 50`. It makes no point-in-time index-membership, historical
membership, constituent, corporate-action, sector, news, event, or eligibility
claim. All 21 selected envelopes must carry the same
`cohort_identity_sha256`, and their complete sorted report-member tuples must
be identical. The input's cohort hash and size must match that persisted
envelope/report/facts evidence. A differing member tuple, cohort hash, report or
envelope identity binding, or duplicate/ambiguous member binding fails the whole
result; the unpersisted Sprint-10 manifest fields are not reconstructed.

Let the retained official schedule establish one strictly increasing sequence:

```text
S[0] < S[1] < ... < S[20]
comparison_session = S[0]
decision_session   = S[20]
```

`S[20]` must be the latest schedule session with `close_at <= decision_cutoff`.
No scheduled session satisfying that completed-session bound may occur after it.
The schedule must prove that each adjacent pair contains no completed NSE Capital
Market exchange session omitted by the archive sequence. Weekend, holiday,
closure, and special-session treatment comes only from the retained official
schedule's sessions and closures. Calendar arithmetic, weekdays, archive-date
adjacency, and an inferred next/previous bar are not proof.

At each `S[j]`, exactly one selected archive object supplies exactly one complete,
fresh `CompletedDailyOhlcvFactV1` for every admitted member, and no object may
supply an extra conflicting date/fact candidate. For member `i`:

```text
prior_i   = Decimal(close(i, S[0]))
current_i = Decimal(close(i, S[20]))

ADVANCE   iff current_i > prior_i
DECLINE   iff current_i < prior_i
UNCHANGED iff current_i == prior_i
```

The comparison uses finite, positive, canonically encoded `Decimal` values only.
No float, tolerance, percentage return, rounding, adjustment, imputation, or raw
OHLC recomputation is admitted. A valid retained partial-current-session snapshot
may be present but is discarded; it is never a calculation input.

```text
BROAD_ADVANCE       iff advances * 5 >= cohort_size * 3
BROAD_DECLINE       iff declines * 5 >= cohort_size * 3
MIXED_PARTICIPATION otherwise
```

The comparisons are mutually exclusive; the decision order above is normative.
The threshold is inclusive and integer-only: 3/5 and 30/50 advances are broad
advance; 3/5 and 30/50 declines are broad decline. No reduced denominator,
partial directions, or partial counts exists.

```text
CurrentSuppliedCohortMemberDirectionV1 = Literal["ADVANCE", "DECLINE", "UNCHANGED"]
CurrentSuppliedCohortMarketRegimeEvidenceStateV1 = Literal[
  "OBSERVED", "INSUFFICIENT_EVIDENCE"
]
CurrentSuppliedCohortMarketRegimeLabelV1 = Literal[
  "BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"
]
```

## Canonical schemas and identities

All three representations are closed JSON objects. Their canonical external
bytes are UTF-8, compact JSON (`separators=(',', ':')`), lexicographically sorted
object keys, `allow_nan=false`, no duplicate keys, and exactly one trailing LF.
Arrays retain the order declared below; producers must not sort an external array
on admission. `UtcInstant` is exactly `YYYY-MM-DDTHH:MM:SS.ffffffZ`,
`LocalDate` is a real `YYYY-MM-DD`, and `Sha256` is 64 lowercase hexadecimal
characters. Decimal strings are finite positive canonical Decimal text: no sign,
exponent, leading zero other than `0`, trailing fractional zero, NaN, infinity,
or binary-number coercion. Unknown keys, missing keys, wrong types, malformed
UTF-8, noncanonical bytes, or invalid nullability are structural rejection before
a domain report exists.

Every `*_identity_sha256` is SHA-256 of the canonical projection that excludes
only that object's own identity field. `schema_identity_sha256` is the SHA-256
of the canonical closed schema bundle for this revision. `calculation_identity_sha256`
is the SHA-256 of the canonical rule projection containing the literal contract
revision, `completed_schedule_positions: 21`, `comparison_position_offset: 20`,
direction enum, threshold expression, and reason declaration order. A digest is
an integrity binding, not authority or proof that its content was timely.

The following two one-line JSON values, each followed by one LF, are the
authoritative canonical projections. Implementations MUST construct these exact
values before hashing; prose tables, generated schemas, and reordered arrays do
not supersede them.

Schema projection (`CURRENT_SUPPLIED_COHORT_MARKET_REGIME_SCHEMA_IDENTITY_SHA256_V1`
is exactly `1242118a1a48d484259f992784850173c9722d4d650df2e886d89af42e55ebd7`):

```json
{"canonical_json":{"allow_nan":false,"encoding":"UTF-8","object_keys":"LEXICOGRAPHIC","separators":[",",":"],"trailing_lf":true},"contract_version":"current-supplied-cohort-market-regime@v1","input_fields":["contract_version","cohort_identity_sha256","cohort_size","decision_cutoff","decision_session","archive_object_sha256s","schedule_evidence_sha256","schedule_source","schedule_source_release","input_identity_sha256"],"input_type":"CurrentSuppliedCohortMarketRegimeInputV1","report_fields":["contract_version","schema_identity_sha256","calculation_identity_sha256","input_identity_sha256","request_identity_sha256","cohort_identity_sha256","cohort_size","decision_cutoff","decision_session","comparison_session","archive_object_sha256s","schedule_evidence_sha256","schedule_source","schedule_source_release","code_identity_sha256","evidence_state","regime_label","advances","declines","unchanged","member_directions","reasons","report_identity_sha256"],"report_type":"CurrentSuppliedCohortMarketRegimeReportV1","request_fields":["contract_version","input_identity_sha256","cohort_identity_sha256","cohort_size","decision_cutoff","decision_session","archive_object_sha256s","schedule_evidence_sha256","schedule_source","schedule_source_release","schema_identity_sha256","calculation_identity_sha256","request_identity_sha256"],"request_type":"CurrentSuppliedCohortMarketRegimeRequestV1","schema_revision":"current-supplied-cohort-market-regime-schema@v1"}
```

Calculation projection
(`CURRENT_SUPPLIED_COHORT_MARKET_REGIME_CALCULATION_IDENTITY_SHA256_V1` is
exactly `037f80eca9caff6d6081bd464047b18a437511b1d5fa31e290c8622e1e0a9fd7`):

```json
{"comparison_position_offset":20,"completed_schedule_positions":21,"contract_version":"current-supplied-cohort-market-regime@v1","direction_values":["ADVANCE","DECLINE","UNCHANGED"],"evidence_states":["OBSERVED","INSUFFICIENT_EVIDENCE"],"labels":["BROAD_ADVANCE","BROAD_DECLINE","MIXED_PARTICIPATION"],"reason_order":["ARCHIVE_OBJECT_MISSING","ARCHIVE_OBJECT_UNSAFE","ARCHIVE_OBJECT_INVALID","ARCHIVE_CONTENT_ID_MISMATCH","ARCHIVE_BINDING_MISMATCH","SPRINT10_REPORT_INSUFFICIENT","SPRINT10_REPORT_INVALID","SPRINT10_MEMBER_FACT_INVALID","SPRINT10_LEDGER_UNAVAILABLE","SPRINT10_LEDGER_INVALID","COHORT_BINDING_MISMATCH","ARCHIVE_SESSION_DUPLICATE_OR_CONFLICTING","COMMON_SESSION_GRID_INVALID","SCHEDULE_EVIDENCE_MISSING","SCHEDULE_EVIDENCE_AMBIGUOUS","SCHEDULE_EVIDENCE_LATE","SCHEDULE_CONTINUITY_UNPROVEN","DECISION_SESSION_NOT_LATEST_ADMISSIBLE","FACT_CUTOFF_OR_FRESHNESS_UNPROVEN","FACT_FUTURE_KNOWN","PARTIAL_CURRENT_SESSION_SUBSTITUTION_FORBIDDEN"],"schedule_authority":{"source":"nse-authoritative-calendar","source_release_pattern":"sha256:<64 lowercase hex>"},"threshold_order":["BROAD_ADVANCE","BROAD_DECLINE","MIXED_PARTICIPATION"],"threshold_rule":"advances*5>=cohort_size*3;declines*5>=cohort_size*3"}
```

### 1. Owner input — `CurrentSuppliedCohortMarketRegimeInputV1`

The owner-private input file is the only caller-supplied selection surface. It
contains no filesystem path, member identity, OHLC, provider payload, or raw
schedule row. Fields are listed in canonical logical order; serialized object
keys use the lexicographic rule above.

| Field | Type / nullability | Rule |
| --- | --- | --- |
| `contract_version` | literal string, non-null | `current-supplied-cohort-market-regime@v1` |
| `cohort_identity_sha256` | `Sha256`, non-null | Exact expected Sprint-10 cohort identity, matched against every persisted envelope/report. |
| `cohort_size` | integer, non-null | `1..50`; must equal every selected persisted report-member tuple length. |
| `decision_cutoff` | `UtcInstant`, non-null | Knowledge/evidence boundary; never evaluation wall-clock time. |
| `decision_session` | `LocalDate`, non-null | Requested final session; must equal schedule-derived latest admissible session. |
| `archive_object_sha256s` | array of exactly 21 `Sha256`, non-null | Strictly increasing lexicographically, unique, explicit content IDs; each names one archive object, not a query/filter. |
| `schedule_evidence_sha256` | `Sha256`, non-null | Exact retained `ScheduleEvidenceStore.resolve` digest under the admitted storage root. |
| `schedule_source` | literal string, non-null | Exactly `nse-authoritative-calendar`; owner-selected under Issue #116. |
| `schedule_source_release` | `sha256:<64 lowercase hex>`, non-null | Exact official input-byte release binding; must equal the retained schedule's `source_release`. |
| `input_identity_sha256` | `Sha256`, non-null | Hash of every preceding field. |

### 2. Immutable internal request — `CurrentSuppliedCohortMarketRegimeRequestV1`

After structural input admission and private-root admission, the service creates
this immutable request. It has no public path field and performs no selection
beyond the 21 IDs already bound by input.

| Field | Type / nullability | Rule |
| --- | --- | --- |
| `contract_version` | literal string, non-null | Same contract revision. |
| `input_identity_sha256` | `Sha256`, non-null | Exact admitted input. |
| `cohort_identity_sha256` | `Sha256`, non-null | Copied from input. |
| `cohort_size` | integer, non-null | Copied from input. |
| `decision_cutoff` | `UtcInstant`, non-null | Copied from input. |
| `decision_session` | `LocalDate`, non-null | Copied from input. |
| `archive_object_sha256s` | exactly 21 `Sha256`, non-null | Copied in exact input order. |
| `schedule_evidence_sha256` | `Sha256`, non-null | Copied from input. |
| `schedule_source` | literal string, non-null | Copied from input; exactly `nse-authoritative-calendar`. |
| `schedule_source_release` | `sha256:<64 lowercase hex>`, non-null | Copied from input. |
| `schema_identity_sha256` | `Sha256`, non-null | Runtime's exact schema-bundle identity for this revision. |
| `calculation_identity_sha256` | `Sha256`, non-null | Runtime's exact frozen calculation-rule identity. |
| `request_identity_sha256` | `Sha256`, non-null | Hash of every preceding request field. |

### 3. Public aggregate report — `CurrentSuppliedCohortMarketRegimeReportV1`

The report is the only public result. It deliberately has no `members`, close,
partial, OHLC, raw schedule row, archive path, private-root identity, source
payload, credential, or diagnostic free text. Its required
`member_directions` field is always literal `null`; private directions are never
serialized.

| Field | Type / nullability | Observed / insufficient invariant |
| --- | --- | --- |
| `contract_version` | literal string, non-null | Same contract revision. |
| `schema_identity_sha256` | `Sha256`, non-null | Exact request schema identity. |
| `calculation_identity_sha256` | `Sha256`, non-null | Exact request calculation identity. |
| `input_identity_sha256` | `Sha256`, non-null | Binds owner input. |
| `request_identity_sha256` | `Sha256`, non-null | Binds immutable request. |
| `cohort_identity_sha256` | `Sha256`, non-null | Binds the admitted persisted Sprint-10 envelope/report cohort identity. |
| `cohort_size` | integer, non-null | `1..50`; matched against every selected persisted report-member tuple. |
| `decision_cutoff` | `UtcInstant`, non-null | Echoes request boundary. |
| `decision_session` | `LocalDate`, non-null | Echoes requested/final validated decision session. |
| `comparison_session` | `LocalDate` or `null` | Non-null only for `OBSERVED`; otherwise `null`. |
| `archive_object_sha256s` | exactly 21 `Sha256`, non-null | Same exact ordered IDs; binds selected immutable contents. |
| `schedule_evidence_sha256` | `Sha256`, non-null | Exact resolved retained schedule digest; no path is public. |
| `schedule_source` | literal string, non-null | Exactly `nse-authoritative-calendar`; binds owner-selected schedule authority. |
| `schedule_source_release` | `sha256:<64 lowercase hex>`, non-null | Exact retained official-input release binding. |
| `code_identity_sha256` | `Sha256`, non-null | Exact runtime source-inventory composite for the archive reader, schedule adapter, reducer, and adapter. |
| `evidence_state` | enum, non-null | `OBSERVED` or `INSUFFICIENT_EVIDENCE`. |
| `regime_label` | enum or `null` | Non-null only for `OBSERVED`. |
| `advances` | integer or `null` | Non-null only for `OBSERVED`; then `0..cohort_size`. |
| `declines` | integer or `null` | Non-null only for `OBSERVED`; then `0..cohort_size`. |
| `unchanged` | integer or `null` | Non-null only for `OBSERVED`; then `0..cohort_size`. |
| `member_directions` | required literal `null` | Always `null`, including `OBSERVED`; it makes the public redaction explicit without exposing member facts. |
| `reasons` | ordered array of closed reasons, non-null | Empty only for `OBSERVED`; nonempty, unique, declaration ordered for insufficiency. |
| `report_identity_sha256` | `Sha256`, non-null | Hash of every preceding report field. |

`OBSERVED` requires a non-null comparison session, non-null label/counts, null
member directions, empty reasons, and `advances + declines + unchanged ==
cohort_size`. `INSUFFICIENT_EVIDENCE` requires `comparison_session =
regime_label = advances = declines = unchanged = member_directions = null` and
one or more closed reasons. It is a successful domain fact outcome, not an
exception to swallow.

### Runtime code identity precondition

Before the immutable request is created or any report can exist, the adapter
must verify this exact ordered source inventory:

```text
CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_SOURCES_V1 = (
  "src/swing_trading_ai_assistant/market_data/cli.py",
  "src/swing_trading_ai_assistant/market_data/current_cohort.py",
  "src/swing_trading_ai_assistant/market_data/schedule_evidence.py",
  "src/swing_trading_ai_assistant/market_data/storage_root_lease.py",
  "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort.py",
)

CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_MANIFEST_V1 =
  "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_runtime_identity_manifest.py"
```

The manifest is generated and independently reviewed on the exact candidate
revision. It is a nonrecursive mapping from **every and only** the five inventory
paths above to their expected lowercase 64-hex SHA-256 values. It MUST NOT map
itself. A missing/extra/malformed map key or digest, an unordered/non-literal
mapping representation, or an unreviewed/generated-at-runtime manifest is a
structural identity failure.

For every inventory source and the manifest file, the runtime verifies the
trusted loaded-module source path and loader, exact regular unlinked file below
the installed project root, stable file identity, and safe readable bytes. No
added package directory, extension, import shadow, replaced path, unreadable
file, or unsafe link is admitted. It hashes each inventory source's observed
bytes and requires exact equality with the manifest map's expected digest. It
then hashes the manifest file's verified observed bytes, without seeking a
recursive expected digest for that file.

`code_identity_sha256` is `SHA-256` over the following exact byte sequence, in
the inventory order shown: for each inventory entry append UTF-8 relative path,
one `0x00`, the **expected** lowercase digest ASCII, and one `0x00`; after the
fifth entry append the manifest relative path, one `0x00`, the manifest file's
observed lowercase digest ASCII, and one final `0x00`. Thus the manifest
participates only through this final nonrecursive manifest-digest rule.

An altered inventory source, changed/unsafe manifest, map mismatch, loaded-source
path/loader mismatch, or composite construction failure is a pre-report
structural rejection: CLI exit `2`, sanitized stderr, no stdout report, and no
domain insufficiency reason.

## Archive, schedule, and timing admission

### Direct immutable archive read

The reader is a narrow private capability under an already-admitted owner-private
root. For each of exactly 21 declared IDs, it opens only
`.current-fact-archive-v1/<sha256>.json` by that literal name with directory and
file descriptors that never follow links. It must pin and recheck root/directory
identity, owner-only mode, regular-file type, single link, stable metadata, and
bytes across the read. It must not list, glob, scan, choose a nearest object, or
follow a redirect/symlink/hard link. The selected filename must be the declared
ID, the raw bytes must be canonical, and SHA-256(raw bytes) must equal both the
filename stem and declared ID. A missing, unsafe, changed, oversized, malformed,
noncanonical, or digest-mismatched object is insufficiency.

Each object has a maximum 2 MiB canonical byte size and maximum JSON nesting 32;
the input is at most 16 KiB and the public report at most 16 KiB. The adapter
admits no more than 21 objects, no recursive archive object, no repeated ID, and
no unbounded source text, error list, member list, or allocation. Limit plus one
is structural rejection where it is visible before a request; a safe domain
failure after an admitted request is the single whole-result insufficiency.

Every selected object must pass all persisted Sprint-10 v1 envelope validation,
using its canonical representation rather than a newly recomputed historical
result:

1. Its closed canonical envelope has exactly `code_identity`,
   `cohort_identity_sha256`, `contract_version`, `facts`, `ledger`, `partials`,
   `report`, and `request_identity_sha256`. The object does not contain a nested
   request; `request_identity_sha256` is an opaque binding and is checked only
   for canonical digest form and exact agreement with the nested report.
2. The persisted `CurrentCohortMarketDataReportV1` has a valid canonical report
   identity, equals `COMPLETE`, has no reasons, has
   `schema_identity_sha256 == CURRENT_COHORT_SCHEMA_IDENTITY_SHA256_V1`, and
   exactly agrees with the envelope's contract version, cohort identity, request
   identity, and code identity. Its historical code identity is checked for
   well-formed envelope/report consistency, not recomputed against subsequently
   changed source files.
3. The report contains one sorted `CurrentCohortMemberFactV1` per distinct
   member, with a total member count of 1–50. Its member tuple and the
   envelope/report cohort hash must agree across every selected object and with
   the owner-supplied cohort hash. The original Sprint-10 request, its manifest,
   selection instant, source-policy identity, and request-side schema identity
   are not reconstructible from the v1 envelope; the persisted report schema
   identity above remains mandatory validation.
4. Each member fact's `completed_daily` is the only price input: its member,
   session, canonical finite positive Decimal OHLC envelope, nonnegative volume,
   `COMPLETED_DAILY` meaning, receipt, data/publication/knowledge clocks, and
   `FRESH` state validate exactly as Sprint 10 requires. Each nested report must
   prove its fact was `FRESH` under the freshness policy at that archive
   report's own `invocation_cutoff`; each fact must have `data_cutoff <=
   published_at <= known_at <= invocation_cutoff <= decision_cutoff`. A prior
   session is not made stale merely because it is 20 schedule positions earlier;
   it is rejected when its own admitted archive evidence was stale, future-known,
   or unavailable by its own cutoff.
5. Any included partial snapshot and the envelope `partials` array must validate
   and match the nested member facts, but are discarded before the regime
   projection. A partial value can never supply, alter, or contextualize a
   decision/comparison close.
6. The ledger contains exactly one `DAILY_OHLCV` / `1d` entry for every member
   with `availability_state = AVAILABLE`, matching the completed fact's precise
   window, member, source, revision, affected identity, publication and known
   clocks. Missing, non-available, duplicated, conflicting, or mismatched ledger
   evidence is insufficient.
7. Across all objects, the contract version, cohort identity, member tuple, and
   member identity bindings are identical. Exactly one archive date belongs to
   each `S[j]`; a duplicate date, a second candidate for a date, or any
   cross-cohort/date conflict is insufficient. The 21 request identities need
   not be equal: each is retained as its own opaque point-in-time binding.

### Private projections and ports

The archive reader returns only immutable private values:

```text
PrivateCurrentCohortMemberCloseProjectionV1 =
  (member: CurrentCohortMemberV1, close: CanonicalDecimal)

PrivateCurrentCohortArchiveSessionProjectionV1 =
  (archive_object_sha256: Sha256, request_identity_sha256: Sha256,
   report_identity_sha256: Sha256, archive_code_identity_sha256: Sha256,
   invocation_cutoff: UtcInstant, session: LocalDate,
   members: tuple[PrivateCurrentCohortMemberCloseProjectionV1, ...])

PrivateCurrentCohortArchiveGridProjectionV1 =
  (cohort_identity_sha256: Sha256, cohort_size: 1..50,
   sessions: tuple[PrivateCurrentCohortArchiveSessionProjectionV1, ...])
```

`members` has exactly `cohort_size` entries sorted by `(isin, symbol)` with one
identity each. `sessions` has exactly 21 entries strictly ordered by `session`;
each position has the same sorted member tuple, and its archive ID is one of the
input's 21 IDs exactly once. These types never serialize to a public report.

```text
PrivateRetainedScheduleSessionProjectionV1 =
  (trade_date: LocalDate, close_at: UtcInstant, kind: nonempty ASCII)

PrivateRetainedScheduleContinuityProjectionV1 =
  (schedule_evidence_sha256: Sha256, schema_version: 2 | 3,
   source: Literal["nse-authoritative-calendar"],
   source_release: `sha256:<64 lowercase hex>`, as_of: UtcInstant,
   sessions: tuple[PrivateRetainedScheduleSessionProjectionV1, ...])
```

The schedule `sessions` projection is strictly ordered and has exactly the 21
admitted grid dates; it is derived from, but does not expose, the retained
canonical schedule bytes or paths.

```text
CurrentCohortArchiveReadOutcomeV1 = Literal["READY", "INSUFFICIENT_EVIDENCE"]
CurrentCohortScheduleReadOutcomeV1 = Literal["RESOLVED", "INSUFFICIENT_EVIDENCE"]

PrivateCurrentCohortArchiveReaderPortV1.read_exact(
  request: CurrentSuppliedCohortMarketRegimeRequestV1, lease
) -> ArchiveReadResultV1

PrivateCurrentCohortScheduleResolverPortV1.resolve_exact(
  schedule_evidence_sha256: Sha256,
  schedule_source: Literal["nse-authoritative-calendar"],
  schedule_source_release: `sha256:<64 lowercase hex>`,
  decision_cutoff: UtcInstant, lease
) -> ScheduleReadResultV1
```

`ArchiveReadResultV1.READY` carries exactly one valid grid; its insufficient
outcome carries `grid = null` and ordered closed reasons. `ScheduleReadResultV1`
has the analogous `projection` nullability. Neither outcome contains a member
list, close, canonical schedule bytes, relative path, or free-text diagnostics
outside the private boundary. The schedule port delegates to
`ScheduleEvidenceStore.resolve` under the same admitted retained-root lease; it
does not accept a caller path, a supplied schedule byte string, or a provider.

The pure regime core accepts only a `READY` grid and a `RESOLVED` schedule
projection. It cannot access the archive, schedule store, filesystem, network,
provider, clock, raw OHLC, or partial snapshots.

### Schedule-only continuity and latest admissible session

The repository owner selects the already-retained authoritative schedule evidence
under Issue #116. The owner input binds its exact
`schedule_evidence_sha256`, `schedule_source =
"nse-authoritative-calendar"`, and `schedule_source_release =
"sha256:<64 lowercase hex>"`. Under the same admitted retained storage-root
lease as archive reads, the adapter invokes
`ScheduleEvidenceStore.resolve(schedule_evidence_sha256)`. It admits only
`ScheduleOutcome.RESOLVED` with exact canonical bytes whose SHA-256 equals that
input digest; it never retains/restores bytes during this read-only evaluation.

The resolved `ExpectedSessionSchedule` must have schema version 2 or 3,
`source == "nse-authoritative-calendar"`, `source_release` exactly equal to the
owner input and matching `sha256:<64 lowercase hex>`. That release is the
SHA-256 binding of the official input bytes used to compose and retain this
schedule, not a substitute canonical-schedule digest; both values are included
in canonical retained bytes. It must have `Asia/Kolkata` timezone,
`as_of <= decision_cutoff`, canonical size at most the existing 1,000,000-byte
limit, no more than 4,096 total `sessions + closures` rows, and complete
classified calendar-date coverage through the `decision_cutoff` Asia/Kolkata
local date. It must cover `S[0]` through `S[20]`, have one unambiguous applicable
session for each grid date, and preserve every timely closure and special session
that changes that interval. Timely, unambiguous closures and special sessions are
accepted; missing, conflicting, out-of-scope, or unclassifiable evidence fails
closed. Separate publication, known, or correction fields are neither required
nor invented because this retained schedule schema does not carry them.

`as_of` is a timeliness bound only; it never changes which sessions are complete.
The schedule plus each selected Sprint-10 completed fact proves completion. A
date counts as an admissible completed schedule session only when its `close_at
<= decision_cutoff` and every corresponding selected
`CompletedDailyOhlcvFactV1` is admitted completion evidence under its own
archive-report cutoff. The schedule must prove both that the 21 archive sessions
are all official completed NSE Capital Market sessions from `S[0]` through
`S[20]`, without an omitted, duplicated, closure-misclassified, or unscoped
special session, and that `S[20]` is the latest session with
`close_at <= decision_cutoff`. It cannot add a close, select a different archive,
replace a missing archive fact, reinterpret a partial snapshot, or recompute raw
OHLC.

## Closed insufficiency reasons and deterministic order

After a structurally valid input/request, the evaluator collects every applicable
reason, deduplicates it, and renders it in this declaration order:

```text
CurrentSuppliedCohortMarketRegimeReasonV1 = Literal[
  "ARCHIVE_OBJECT_MISSING",
  "ARCHIVE_OBJECT_UNSAFE",
  "ARCHIVE_OBJECT_INVALID",
  "ARCHIVE_CONTENT_ID_MISMATCH",
  "ARCHIVE_BINDING_MISMATCH",
  "SPRINT10_REPORT_INSUFFICIENT",
  "SPRINT10_REPORT_INVALID",
  "SPRINT10_MEMBER_FACT_INVALID",
  "SPRINT10_LEDGER_UNAVAILABLE",
  "SPRINT10_LEDGER_INVALID",
  "COHORT_BINDING_MISMATCH",
  "ARCHIVE_SESSION_DUPLICATE_OR_CONFLICTING",
  "COMMON_SESSION_GRID_INVALID",
  "SCHEDULE_EVIDENCE_MISSING",
  "SCHEDULE_EVIDENCE_AMBIGUOUS",
  "SCHEDULE_EVIDENCE_LATE",
  "SCHEDULE_CONTINUITY_UNPROVEN",
  "DECISION_SESSION_NOT_LATEST_ADMISSIBLE",
  "FACT_CUTOFF_OR_FRESHNESS_UNPROVEN",
  "FACT_FUTURE_KNOWN",
  "PARTIAL_CURRENT_SESSION_SUBSTITUTION_FORBIDDEN",
]
```

Runtime code-identity verification runs first. Its failure, or a request/CLI/schema
violation before a report exists, is exit `2`, sanitized stderr, and no stdout
report—not a fabricated insufficiency report. Every post-admission evidence
problem returns one canonical `INSUFFICIENT_EVIDENCE` report with every
label/count and `member_directions` null. No reason implies a fallback, retry,
lower denominator, directory scan, provider call, raw query, or a hidden
member-level diagnostic.

`I(reason)` in the matrix below means one canonical
`INSUFFICIENT_EVIDENCE` report containing that reason in declaration order and
with `comparison_session`, label, counts, and `member_directions` null. Stage
precedence is: pre-report runtime/CLI; direct archive I/O in listed order; B1
intrinsic report; B2 envelope/report binding; member/ledger; grid; schedule
resolve, then authority/shape ambiguity, then `as_of` lateness, then continuity
fold; fact timing future-known, then other cutoff/freshness; reducer guard.
Within one stage, only independent failing objects may contribute multiple
reasons; their set is deduplicated then declaration ordered. Each trigger is
exclusive within its stage: the listed suppression selects one outcome rather
than alternative labels for the same defect. A later stage runs only when its
stated prerequisites are admitted.

| Reason | Stage | Exact trigger | Suppress | Output |
| --- | --- | --- | --- | --- |
| `ARCHIVE_OBJECT_MISSING` | direct archive read | Declared literal object name is absent. | Byte/envelope checks for that ID. | `I(ARCHIVE_OBJECT_MISSING)` |
| `ARCHIVE_OBJECT_UNSAFE` | direct archive read | Root/directory/file identity, mode, type, link count, no-follow, or stability check fails. | Byte/envelope checks for that ID. | `I(ARCHIVE_OBJECT_UNSAFE)` |
| `ARCHIVE_OBJECT_INVALID` | direct archive read | Bytes exceed 2 MiB/nesting 32 or are malformed/noncanonical. | Content-digest and envelope checks for that ID. | `I(ARCHIVE_OBJECT_INVALID)` |
| `ARCHIVE_CONTENT_ID_MISMATCH` | direct archive read | Canonical raw-byte SHA differs from declared ID or filename stem. | Envelope checks for that ID. | `I(ARCHIVE_CONTENT_ID_MISMATCH)` |
| `SPRINT10_REPORT_INSUFFICIENT` | B1 intrinsic report | An intrinsically valid persisted Sprint-10 report has `INSUFFICIENT_EVIDENCE`. | B2 binding and member/ledger admission for that object. | `I(SPRINT10_REPORT_INSUFFICIENT)` |
| `SPRINT10_REPORT_INVALID` | B1 intrinsic report | The report itself has invalid canonical bytes/identity, unsupported state, nonempty complete reasons, invalid required schema identity, or invalid member ordering. | B2 binding and member/ledger admission for that object. | `I(SPRINT10_REPORT_INVALID)` |
| `ARCHIVE_BINDING_MISMATCH` | B2 envelope binding | A valid envelope and a B1-admitted complete report disagree on contract version, request ID, code ID, or cohort ID. | Member/ledger admission for that object. | `I(ARCHIVE_BINDING_MISMATCH)` |
| `SPRINT10_MEMBER_FACT_INVALID` | member admission | A completed-daily/member/partial relation, Decimal/receipt/state, or required member tuple is invalid. | Direction/grid contribution for that member/object. | `I(SPRINT10_MEMBER_FACT_INVALID)` |
| `SPRINT10_LEDGER_UNAVAILABLE` | ledger admission | Required `DAILY_OHLCV`/`1d` ledger entry is not `AVAILABLE`. | No substitute ledger/fact may be chosen. | `I(SPRINT10_LEDGER_UNAVAILABLE)` |
| `SPRINT10_LEDGER_INVALID` | ledger admission | Ledger is missing, duplicate, malformed, or mismatches fact/member/window/provenance. | Ledger admission for that entry. | `I(SPRINT10_LEDGER_INVALID)` |
| `COHORT_BINDING_MISMATCH` | grid assembly | Input hash/size, envelope/report hash, or complete sorted member tuple differs across objects. | Cross-object grid/reducer admission. | `I(COHORT_BINDING_MISMATCH)` |
| `ARCHIVE_SESSION_DUPLICATE_OR_CONFLICTING` | grid assembly | Two objects claim one session, an object contains conflicting session/close candidates, or ID/date mapping is not one-to-one. | Schedule continuity/reducer admission. | `I(ARCHIVE_SESSION_DUPLICATE_OR_CONFLICTING)` |
| `COMMON_SESSION_GRID_INVALID` | grid assembly | Fewer/more than 21 usable sessions, non-increasing sessions, or non-common member grid remains after safe admission. | Schedule continuity/reducer admission. | `I(COMMON_SESSION_GRID_INVALID)` |
| `SCHEDULE_EVIDENCE_MISSING` | schedule resolve | `ScheduleEvidenceStore.resolve` is not `RESOLVED` for the input digest. | Schedule semantic checks. | `I(SCHEDULE_EVIDENCE_MISSING)` |
| `SCHEDULE_EVIDENCE_AMBIGUOUS` | schedule admission | Resolved object is not v2/v3, has a digest/canonical-byte/source/source-release/timezone/row-shape conflict, or does not exactly match owner-bound source/release. | Continuity/latest-session checks. | `I(SCHEDULE_EVIDENCE_AMBIGUOUS)` |
| `SCHEDULE_EVIDENCE_LATE` | schedule admission | `as_of > decision_cutoff`. | Continuity/latest-session checks. | `I(SCHEDULE_EVIDENCE_LATE)` |
| `SCHEDULE_CONTINUITY_UNPROVEN` | schedule fold | Classified calendar-date coverage through cutoff-local date, S0..S20 coverage, closure/special-session scope, or no-omitted-session proof is absent/incomplete. | Latest-session/reducer admission. | `I(SCHEDULE_CONTINUITY_UNPROVEN)` |
| `DECISION_SESSION_NOT_LATEST_ADMISSIBLE` | schedule fold | Requested `S[20]` is not the final session with `close_at <= decision_cutoff`. | Reducer admission. | `I(DECISION_SESSION_NOT_LATEST_ADMISSIBLE)` |
| `FACT_FUTURE_KNOWN` | fact timing | `known_at`, `published_at`, `data_cutoff`, or archive-report cutoff is after `decision_cutoff`. | The generic cutoff reason for that same future-clock violation; direction for that fact. | `I(FACT_FUTURE_KNOWN)` |
| `FACT_CUTOFF_OR_FRESHNESS_UNPROVEN` | fact timing | A required fact is stale, lacks a required clock, or violates own-report cutoff ordering without a future-known clock. | Direction for that fact. | `I(FACT_CUTOFF_OR_FRESHNESS_UNPROVEN)` |
| `PARTIAL_CURRENT_SESSION_SUBSTITUTION_FORBIDDEN` | projection/reducer guard | A partial snapshot is proposed as either decision or comparison close. | That proposed value; never substitute it. | `I(PARTIAL_CURRENT_SESSION_SUBSTITUTION_FORBIDDEN)` |

## CLI and API boundary

The one public command is a read-only current-regime adapter, not an alias for
Plan 12 or the historical evaluator:

```text
market-data regime-current \
  --input-file <absolute-owner-private-canonical-json> \
  --storage-root <absolute-owner-private-root> \
  --output json
```

`--input-file` carries the exact 21 IDs,
`schedule_evidence_sha256`, `schedule_source =
"nse-authoritative-calendar"`, and exact `schedule_source_release`. The
repository owner selected that already-retained schedule evidence under Issue
#116; the deterministic adapter validates the exact source/release/digest and
never treats an arbitrary nonempty retained schedule as official. `--storage-root`
is the one absolute, existing, owner-private retained root admitted without
following links. The schedule is resolved by digest below that same root through
`ScheduleEvidenceStore.resolve`; there is no schedule-path option, supplied
schedule byte string, provider URL, or public path identity. The root path is
never echoed, hashed into the public representation, logged, or included in
stderr. The command makes no network/provider/source call, archive publication,
data acquisition, persistence mutation, retry, or background task. It emits
exactly one canonical aggregate report on stdout and no fragments.

Exit `0` means `OBSERVED`; exit `1` means canonical whole-result
`INSUFFICIENT_EVIDENCE`; exit `2` means runtime-code-identity failure, malformed
CLI/input, unsafe/missing private path, unsupported schema/contract, or other
structural rejection before a report. Only sanitized structural diagnostics may
go to stderr for exit `2`; they must not disclose a private path, member, symbol,
ISIN, close, raw JSON, source payload, credential, or schedule row.

The corresponding Python/API boundary is
`evaluate_current_supplied_cohort_market_regime_v1(input, private_archive_reader,
retained_schedule_resolver) -> CurrentSuppliedCohortMarketRegimeReportV1`. It
accepts only the typed immutable input and narrow private read capabilities. It
returns the same report as the CLI; it exposes neither an archive directory API
nor a raw-candle/provider API, and it must not alter request IDs, select objects,
or recompute a decision.

## Acceptance and evidence plan

No test in this section has run. The implementation must add focused,
exact-revision evidence before it can claim completion, and then run applicable
full/release gates on that same revision.

| Category | Required acceptance cases |
| --- | --- |
| Positive | Cohort sizes 1, 5 with exactly 3 advances, and 50 with exactly 30 advances; exact Decimal advance/decline/equality; owner-bound `nse-authoritative-calendar` schedule/source-release/digest; 21 retained official sessions across a month/closure boundary; a timely, unambiguous applicable closure and special session accepted; decision close and comparison close at positions 20 and 0; reviewed nonrecursive runtime manifest with every-and-only frozen source map entry; exact source/map verification and ordered path-NUL-digest composite including the final manifest digest; canonical identity stability; archive/request/report/cohort/schedule/code/schema binding; aggregate-only redacted observed report. |
| Boundary | 2/5 versus 3/5 advances and declines; 29/50 versus 30/50; all unchanged; exactly 21 IDs, 21 sessions, and 1/50 members; fact and schedule `as_of` exactly at cutoff; decision session equal to latest session with `close_at <= decision_cutoff`; complete classified calendar-date coverage through cutoff-local date; exact 1,000,000-byte schedule and 4,096 combined rows; canonical owner-input identity stability and preserved declared archive-ID array order. |
| Archive and persisted-envelope failure | Fewer/more than 21 IDs; duplicate/noncanonical ID; missing, linked, hard-linked, replaced, unsafe, oversized, malformed, noncanonical, or filename/content-digest-mismatched object; malformed/mismatched envelope/report/member/partial/ledger; Sprint-10 insufficiency report; report `schema_identity_sha256` not equal to `CURRENT_COHORT_SCHEMA_IDENTITY_SHA256_V1`; wrong envelope/report/cohort/request/code identity binding; stale/non-fresh fact, missing receipt, unavailable ledger, conflicting close, duplicate date, or member substitution. The suite must also prove opaque request identities are not decoded as a missing request/manifest or used to infer source-policy/schema/selection fields. |
| Schedule, timing, and structural failure | Missing/unresolved or digest-mismatched retained schedule; source other than `nse-authoritative-calendar`; source-release mismatch or invalid `sha256:<64 lowercase hex>` form; noncanonical/over-1,000,000-byte/4,097-row schedule; unsupported v1, wrong timezone, `as_of > decision_cutoff`, incomplete classified coverage through cutoff-local date, omitted completed exchange session, conflicting/unscoped closure or special session, non-common/non-increasing grid, decision not latest admissible, no comparison position, data/published/known instant after cutoff, future-known fact, or missing/extra/malformed/unreviewed runtime manifest, source-map digest mismatch, unsafe manifest/source, loader/path mismatch, or composite verification failure. Every runtime-manifest case is exact exit `2` with no report; the other post-admission faults are canonical insufficiency. |
| Forbidden-path failure | Partial snapshot offered as a decision/comparison close; raw daily OHLC query/candle reconstruction attempt; provider/network/source/clock/archive-enumeration attempt; denominator reduction; partial directions/counts; member/raw/path leakage in public output or diagnostics. Valid partial presence alone is accepted then discarded. Every failure case must yield the closed whole-result behavior or pre-report structural exit. |

Focused gate (not run by this planning change):

```text
uv run pytest -q -o addopts='' tests/market_regime/test_current_supplied_cohort.py tests/market_data/test_current_cohort.py
```

Full candidate-revision gate (not run by this planning change) first performs
`uv sync --extra dev --frozen`, then the CI quality chain:

```text
uv run --no-sync --extra dev ruff format --check .
uv run --no-sync --extra dev ruff check .
uv run --no-sync --extra dev pyright
uv run --no-sync --extra dev vulture src --min-confidence 80
uv run --no-sync --extra dev pytest
uv build --no-build-isolation --python .venv/bin/python
```

Release evidence additionally requires the exact candidate revision, independent
exact-revision quality/security review, the corresponding hosted CI/security
result, pull-request merge, and publication/closure evidence accepted by the
Issue #116 owner. Evidence must record command/method, exact revision, result,
scope, and limits; a focused pass does not substitute for independent review,
full gate, merge, or publication.

## Explicit non-goals

Issue #116 and the owner direction authorize implementation of this contract
within the current-supplied-cohort Market Regime epic. This plan adds no provider,
source, network, acquisition, or raw-OHLC authority; any such addition or a
material scope change requires its own approved decision. It does not add a
factor, data source, indicator, corporate-action adjustment, raw OHLC query,
historical reconstruction/backtest, current partial-session substitution,
sector/news/event work, recommendation, financial advice, broker order, Market
Structure, or Sprints 12–16 refinement. It does not change Plan 12, Plan 18,
Plan 19, the Sprint 10 stale-lifecycle line, or any historical record. It creates
no claim that Issue #116 has been implemented, tested, reviewed, merged,
released, or published.

## Residual risks and review trigger

The archive is currently write-only/unindexed, so callers need a bounded
out-of-band way to obtain the 21 explicit IDs; this does not permit a directory
scan. Its v1 envelope deliberately persists only an opaque request identity, not
the original request or cohort manifest, so validation remains limited to the
persisted envelope/report/facts/ledger/partials and owner-supplied cohort hash.
The owner-selected retained schedule may lack a canonical decoder, an exact
`nse-authoritative-calendar` source/release binding, admissible `as_of`, complete
classified cutoff-date coverage, or closure/special-session coverage. It then
fails closed; an arbitrary retained schedule cannot replace it. Implementation of
the narrow archive reader and schedule projection proceeds under Issue #116; a
change to schedule authority, privacy boundary, provider/source, or Issue #116
acceptance criteria reopens this R3 decision and requires the applicable owner
review and updated exact-revision evidence plan.
