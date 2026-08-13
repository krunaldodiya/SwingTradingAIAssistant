# Market Regime v1 Fact Contract

Status: **ARK-166 APPROVED — FROZEN FACT CONTRACT**
Decisions: ARK-165 (scope and input policy), ARK-166 (complete V1 fact contract)
Contract version: `nifty50-market-regime@v1`

This document extends, does not replace, the ARK-165 source and scope decision.
It freezes the only Market Regime V1 classification rule, its private evidence
boundary, public report, identities, failure behavior, and implementation
handoff. It approves no source adapter, classifier implementation, provider
call, acquisition, CLI, API, MCP surface, or runtime. Implementation remains a
later strict-TDD task.

## Boundary evaluation and rule decision

- Expected value: one reproducible breadth fact gives downstream research bounded end-of-day Nifty 50 context without an indicator bundle.
- Scope fit: equal participation of the exact point-in-time 50-name cash-equity cohort is the sole ARK-165 factor family.
- Material risk: lookback and threshold choices could be fitted, and missing or incomparable members could manufacture breadth.
- Smallest alternative: compare one comparable `CLOSE` at two exact official-session endpoints, count every member once, and fail closed unless all 50 are valid.
- Decision: **accepted — freeze an exact 20-official-session comparison and an inclusive 30-of-50 supermajority for V1.**

Twenty official-session transitions are roughly one swing month while remaining
simple and interpretable. Thirty of 50 is an exact 60% supermajority that demands
breadth beyond a bare majority. These are design priors, not fitted parameters;
no retained outcome analysis, effectiveness claim, accuracy claim,
profitability claim, or prediction justifies them. The smaller alternatives of
one-session direction or 26-of-50 were rejected as respectively too noisy and
too close to a bare majority; multiple windows, optimized thresholds, weights,
and confidence scores were rejected as extra degrees of freedom. A future
empirical change requires a new contract version and out-of-sample governance.

## Purpose, scope, and non-claims

Market Regime answers only: *at the exact close of one completed authoritative
NSE Capital Market decision session, how many of the exactly 50 point-in-time
Nifty 50 members have a comparable close above, below, or equal to their close
exactly 20 official sessions earlier?*

It is an end-of-day descriptive market-context fact, not a signal, forecast,
strategy, opportunity score, recommendation, financial advice, risk override,
entry/exit rule, position-size rule, or permission to trade. It covers Nifty 50
cash equities and daily official-session facts only. It does not cover intraday,
an index instrument, India VIX, derivatives, macro data, other universes, or
broker execution. `NO_TRADE` belongs to later decision logic; an observed label
cannot repair another module's missing evidence or override a hard risk failure.

The V1 label is not a trend, volatility, sector, liquidity, relative-strength,
market-timing, or future-return conclusion. SMA, EMA, Bollinger Bands, RSI,
MACD, stochastic, ATR, ADX, volume, index candles, weights, scores, and hidden
factors remain excluded. There is no claim of stability, prediction,
profitability, trade timing, market safety, or suitability.

## Frozen classification rule

### Exact endpoints

Let `S[0] < ... < S[20]` be exactly 21 consecutive authoritative completed NSE
Capital Market official sessions. `S[20]` is `decision_session` and `S[0]` is
`comparison_session`. Thus the endpoint distance is exactly **20 official sessions**: the comparison session is the session reached by stepping backward
20 times in the authoritative session sequence. It is not 20 elapsed calendar
days, 20 weekdays, a duration, or “approximately a month.” Holidays, exchange
closures, and non-session dates do not consume a step. A special Capital Market
session consumes one step only when authoritative schedule evidence proves it.
An unresolved date, special-session scope, closure, timing change, conflict, or
missing intermediate session fails closed; a built-in calendar cannot fill it.

The decision cohort is exactly 50 unique ISIN-first Nifty 50 members whose
point-in-time membership interval covers `decision_session`. Membership at the
older endpoint is neither required nor inferred: the question follows the exact
decision-session cohort backward, one observation per decision-session member.
A symbol change never changes ISIN identity, and an unresolved identity
continuity is insufficient. No current-list backfill, substitution, deduplication,
imputation, survivorship filter, weighting, reduced denominator, or 49-of-49
classification is allowed.

### Comparable close and equality

For each decision-session member `i`, V1 compares the two exact finite positive
`Decimal` values designated as `CLOSE` by verified complete
`nse-session-ohlcv@v1` daily facts:

```text
current_i = comparable CLOSE(i, S[20])
prior_i   = comparable CLOSE(i, S[0])

ADVANCE   iff Decimal(current_i) > Decimal(prior_i)
DECLINE   iff Decimal(current_i) < Decimal(prior_i)
UNCHANGED iff Decimal(current_i) == Decimal(prior_i)
```

Comparison is exact Decimal ordering after admission of canonical decimal text.
There is no binary float, tolerance, tick-size rounding, percentage return,
quantization, adjusted epsilon, or unrounded hidden value. Numeric equality is
explicitly `UNCHANGED`. Source spellings such as `100.0` normalize to the one
private canonical value `100` before identity construction; a noncanonical
spelling inside a canonical input object is rejected. Equality contributes to
neither directional count and cannot be broken by symbol order or a previous
label.

V1's sole comparability path is
`RAW_CLOSE_NO_BREAK_PROVEN`: authoritative cutoff-safe corporate-action and
identity-continuity evidence must positively prove no split, bonus, rights,
symbol/ISIN discontinuity, or other comparability-breaking event over the
inclusive interval from `S[0]` through `S[20]`. The raw daily facts remain
immutable. V1 does not adjust prices. If a potentially breaking event exists,
status/terms are unresolved, negative completeness is unproven, or the raw
values are otherwise not economically comparable, the entire result is
`INSUFFICIENT_EVIDENCE`. An adjusted or back-adjusted series is not admitted by
this contract; admitting one requires a new source-policy decision and contract
version.

### Counts, state, and label

Only after every gate passes, define integer counts over exactly 50 members:

```text
advances  = count(direction_i == ADVANCE)
declines  = count(direction_i == DECLINE)
unchanged = count(direction_i == UNCHANGED)

BROAD_ADVANCE       iff advances >= 30
BROAD_DECLINE       iff declines >= 30
MIXED_PARTICIPATION otherwise
```

The comparisons are ordered as written. With exactly 50 mutually exclusive
observations, `advances >= 30` and `declines >= 30` cannot both be true; this
impossibility is a validation invariant, not a tie-break convention. Threshold
inclusivity is exact: 30 advances is `BROAD_ADVANCE`, 30 declines is
`BROAD_DECLINE`, and 29/29 or any other case with both directional counts below
30 is `MIXED_PARTICIPATION`. Fifty unchanged observations are
`MIXED_PARTICIPATION`.

The closed `evidence_state` enum is `OBSERVED | INSUFFICIENT_EVIDENCE`. The
closed observed `regime_label` enum is
`BROAD_ADVANCE | BROAD_DECLINE | MIXED_PARTICIPATION`. For `OBSERVED`, the label
and all three counts are non-null. For `INSUFFICIENT_EVIDENCE`,
`regime_label = null` and `advances = declines = unchanged = null`; partial
counts, a prior label, a confidence score, and a best-effort label are forbidden.
Insufficiency is a successful fact outcome, not an exception. Structurally
invalid requests are rejected before evaluation and produce no report.

## Exact time and availability boundary

`decision_cutoff` is reconstructed, never caller-authored: it is the exact close
instant of `decision_session` from the applicable retained authoritative NSE
Capital Market base schedule plus all applicable corrections and special-session
overlays. Exchange-local rules are evaluated in `Asia/Kolkata`; canonical
instants are UTC strings `YYYY-MM-DDTHH:MM:SS.ffffffZ`. Evaluation is post-close,
but running later never moves the cutoff. `knowledge_cutoff` is exactly equal to
`decision_cutoff` and is not a separate request field.

A mandatory fact is admissible only if its applicable/effective scope covers the
claimed member, session, or interval and its admissible knowledge time is at or
before `decision_cutoff`. Admissible knowledge time is the latest mandatory
clock among authoritative public availability, response completion, retrieval,
and immutable retention for that evidence class. A clock absent from a source
with no independently proved publication time cannot be invented. Publisher
business dates, HTTP `Date`/`Last-Modified`, filesystem times, report time,
replay wall clock, commit time, or caller-authored `known_at` do not prove
availability. Evidence first available, completed, retrieved, retained, revised,
or disambiguated after cutoff is late for this report even if it describes an
earlier session. Later corrections produce new input and report identities and
never rewrite the prior point-in-time result.

The current endpoint must be the complete exact decision-session daily fact; the
prior endpoint must be the complete exact `comparison_session` daily fact.
Neither nearest-date fallback nor previous available candle is allowed. Both
may be known by the decision cutoff, but no activity after the respective
authoritative closes may be included.

## Closed conceptual schemas

These schemas are conceptual immutable domain contracts for later implementation,
not code added by ARK-166. Every object is closed: an unknown field, missing
required field, duplicate field, unknown enum, wrong type, or invalid nullability
is an admission error. `tuple[T, N]` is an ordered immutable tuple of exact
length `N`; `Sha256` is 64 lowercase hexadecimal characters; `LocalDate` is
`YYYY-MM-DD`; `UtcInstant` has exactly six fractional digits and `Z`;
`CanonicalDecimal` is finite positive normalized base-10 decimal text matched by
`(?:0\.[0-9]*[1-9]|[1-9][0-9]*(?:\.[0-9]*[1-9])?)`: no sign, exponent,
leading integer zero, trailing fractional zero, or decimal point for an integer;
it is compared as an exact Decimal. `null` appears only where shown.

### Immutable request

```text
MarketRegimeRequestV1 {
  contract_version: Literal["nifty50-market-regime@v1"]
  segment: Literal["NSE_EQ"]
  decision_session: LocalDate
  request_identity_sha256: Sha256
}
```

The request identity is SHA-256 over canonical request content excluding only
`request_identity_sha256`. The request cannot contain a cutoff, comparison date,
cohort, symbol list, label, counts, threshold, lookback, raw OHLC, source
locator, provider choice, or arbitrary configuration. Those are derived or
policy-pinned, never caller-selected.

### Private evidence input

```text
EvidenceRefV1 {
  object_identity_sha256: Sha256
  source_identity: BoundedAscii
  source_authority: BoundedAscii
  schema_version: BoundedAscii
  calculation_version: BoundedAscii | null
  effective_from: LocalDate
  effective_through: LocalDate | null
  published_at: UtcInstant | null
  response_completed_at: UtcInstant
  retrieved_at: UtcInstant
  retained_at: UtcInstant
  revision_identity_sha256: Sha256
  supersedes_identity_sha256: Sha256 | null
}

OfficialSessionV1 {
  session_date: LocalDate
  open_at: UtcInstant
  close_at: UtcInstant
  schedule_evidence: EvidenceRefV1
}

MemberComparisonEvidenceV1 {
  isin: Isin
  symbol: CanonicalSymbol
  comparison_basis: Literal["RAW_CLOSE_NO_BREAK_PROVEN"]
  prior_session: LocalDate
  prior_close: CanonicalDecimal
  prior_close_fact: EvidenceRefV1
  current_session: LocalDate
  current_close: CanonicalDecimal
  current_close_fact: EvidenceRefV1
  comparability_policy_version: Literal["nifty50-raw-close-comparability@v1"]
  comparability_evidence: tuple[EvidenceRefV1, 1..16]
}

MarketRegimeEvidenceBundleV1 {
  request: MarketRegimeRequestV1
  decision_cutoff: UtcInstant
  official_sessions: tuple[OfficialSessionV1, 21]
  membership_evidence: EvidenceRefV1
  members: tuple[MemberComparisonEvidenceV1, 50]
  source_policy_identity_sha256: Sha256
  validation_policy_identity_sha256: Sha256
  policy_identity_sha256: Sha256
  code_identity_sha256: Sha256
  input_identity_sha256: Sha256
}
```

`official_sessions` is strictly ascending and consecutive under the selected
schedule revision. `members` is strictly ascending by ISIN and contains 50
unique ISINs and 50 unique canonical symbols. Evidence reference tuples are
sorted by `(source_identity, effective_from, object_identity_sha256)` and contain
no duplicate identity. The private input is the only layer that may contain the
two close values and detailed source receipts. It contains no open, high, low,
volume, intraday row, provider payload, credential, writable path, or
caller-authored conclusion.

`policy_identity_sha256` is a code-pinned digest over the complete frozen
semantic manifest: contract/calculation versions, exact field names and enums,
20-session rule, `CLOSE`, Decimal operators and equality, exact-50 rule,
30-count inclusive thresholds, comparability path, reason order, canonical JSON
profile, and validation limits. `code_identity_sha256` identifies the exact
reviewed classifier build when implementation later exists. Neither may be
accepted merely because a caller supplied matching-looking text.

`input_identity_sha256` is SHA-256 over the entire canonical
`MarketRegimeEvidenceBundleV1` excluding only `input_identity_sha256`; consequently it
binds the request, all private values, every selected evidence and revision,
source and validation policies, the frozen policy, and exact code identity.
Referenced content-addressed bytes are reopened with checksum, no-follow, and
scope validation; coordinated object replacement plus recomputed caller digests
cannot change admitted semantics.

### Public fact report

```text
MarketRegimeReportV1 {
  contract_version: Literal["nifty50-market-regime@v1"]
  calculation_version: Literal["nifty50-market-regime-classifier@v1"]
  request_identity_sha256: Sha256
  input_identity_sha256: Sha256
  source_policy_identity_sha256: Sha256
  validation_policy_identity_sha256: Sha256
  policy_identity_sha256: Sha256
  code_identity_sha256: Sha256
  decision_session: LocalDate
  comparison_session: LocalDate | null
  decision_cutoff: UtcInstant | null
  lookback_official_sessions: Literal[20]
  required_member_count: Literal[50]
  threshold_count: Literal[30]
  evidence_state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"]
  regime_label: Literal["BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"] | null
  advances: Integer[0..50] | null
  declines: Integer[0..50] | null
  unchanged: Integer[0..50] | null
  primary_reason: MarketRegimeReasonV1 | null
  additional_reasons: tuple[MarketRegimeReasonV1, 0..34]
  report_identity_sha256: Sha256
}
```

The public report contains aggregate facts and identities only. It never exposes
raw OHLC, either close value, per-member direction, member symbols/ISINs,
provider payloads, credentials, filesystem paths, free-form diagnostics, or an
AI-authored conclusion. `report_identity_sha256` is SHA-256 over the complete
canonical report excluding only itself. The report therefore binds request,
input, source policy, validation policy, frozen rule policy, code, state, label,
counts, reasons, endpoints, and cutoff. Identical admitted input bytes under the
same exact code produce byte-identical reports.

## Closed reason enum and precedence

`MarketRegimeReasonV1` is the following declaration-ordered closed enum. The
order shown is the exact primary-reason precedence, first matching reason wins:

```text
EVIDENCE_IDENTITY_MISMATCH
SOURCE_NOT_AUTHORITATIVE
PUBLICATION_UNPROVEN
CLOCK_UNTRUSTED
LICENCE_UNRESOLVED
MEMBERSHIP_MISSING
MEMBERSHIP_LATE
MEMBERSHIP_AMBIGUOUS
MEMBERSHIP_CORRUPT
MEMBERSHIP_COUNT_INVALID
SCHEDULE_MISSING
SCHEDULE_LATE
SCHEDULE_COVERAGE_INCOMPLETE
SCHEDULE_AMBIGUOUS
SCHEDULE_CORRUPT
COMPARISON_SESSION_UNRESOLVED
CURRENT_CLOSE_MISSING
CURRENT_CLOSE_LATE
CURRENT_CLOSE_INCOMPLETE
CURRENT_CLOSE_AMBIGUOUS
CURRENT_CLOSE_CORRUPT
PRIOR_CLOSE_MISSING
PRIOR_CLOSE_LATE
PRIOR_CLOSE_INCOMPLETE
PRIOR_CLOSE_AMBIGUOUS
PRIOR_CLOSE_CORRUPT
CORPORATE_ACTION_MISSING
CORPORATE_ACTION_LATE
CORPORATE_ACTION_STATUS_UNPROVEN
CORPORATE_ACTION_COMPLETENESS_UNPROVEN
CORPORATE_ACTION_REVISION_UNPROVEN
CORPORATE_ACTION_AMBIGUOUS
CORPORATE_ACTION_CORRUPT
IDENTITY_CONTINUITY_UNPROVEN
VALUES_NOT_COMPARABLE
```

For an observed report, `primary_reason = null` and `additional_reasons = ()`.
For an insufficient report, `primary_reason` is the earliest applicable enum and
`additional_reasons` contains every other applicable reason once, in the same
declaration order. Discovery order, input order, hash-map order, and provider
order never affect reasons. Unknown conditions cannot become arbitrary strings;
a condition not representable in V1 fails admission or requires a new version.
Malformed request/canonical JSON is `REQUEST_INVALID` at the application
admission boundary and produces no `MarketRegimeReportV1`, so it is deliberately
not a fact-reason enum member.

## Canonical JSON and identity profile

All request, private input, policy manifest, and report identity material uses
one profile:

1. UTF-8 bytes only, no BOM, with exactly one trailing LF in the serialized object; identity hashes include that LF.
2. Object keys sorted lexicographically by Unicode code point and compact separators `,` and `:` with no insignificant whitespace.
3. All strings must already be Unicode NFC; non-NFC text, unpaired surrogates, forbidden control characters, and invalid UTF-8 are rejected rather than silently repaired.
4. Duplicate object keys, unknown fields, missing fields, duplicate semantic identities, and duplicate set members are rejected before hashing; “last key wins” is forbidden.
5. JSON floats are forbidden. NaN, positive/negative Infinity, exponent notation, negative zero, and implementation-specific numeric spellings are forbidden. Counts are JSON integers; market values are canonical decimal strings and become exact Decimal values only after bounded validation.
6. Booleans and `null` use JSON lowercase spellings. Dates, instants, enums, ISINs, symbols, and SHA-256 values use their schema-defined canonical forms; arbitrary locale or timezone rendering is forbidden.
7. Arrays preserve schema semantics: session and member tuples use their required sort order; reason tuples use declaration order; evidence tuples use their stated sort key. Shuffled equivalent admitted inputs canonicalize to the same bytes, while order-sensitive data cannot be silently reordered.
8. The serializer uses minimal JSON escaping for required quotation mark, reverse solidus, and control escapes and otherwise emits NFC UTF-8 directly. A parser must reject trailing tokens and nesting or size limit violations.

A supplied identity is a claim. Admission reconstructs canonical bytes and checks
the digest; it never trusts a digest in place of validating content. Later
revisions create new immutable objects, input identity, and report identity.
Offline replay opens only explicitly identified objects and never searches for a
newer file, consults the network, reads the current clock, or mutates old bytes.

## Immutability, copy safety, and bounds

All conceptual records are frozen value objects. Constructors make a defensive copy: they defensively copy and deeply validate caller mappings/sequences before converting them to tuples;
no caller-owned mutable alias is retained. Nested evidence records are immutable.
Accessors return immutable values or defensive copies, never internal mutable
state. Evaluation does not mutate a request, evidence object, input bundle, or
report. Reuse of a mutable builder after construction cannot alter identities or
results. A later application persistence adapter must use validated copy-on-write
publication; it cannot mutate or replace an existing identity. Concurrent and
repeated evaluation of the same admitted bytes must be byte-identical.

V1 bounds are exact and tested at the limit and limit-plus-one:

- one request, one decision session, one comparison session, exactly 21 session records, exactly 50 member records, and exactly two close facts per member;
- exactly 50 unique valid ISINs and symbols; each member has 1 through 16 comparability evidence references and at most 800 total;
- request canonical bytes at most 4 KiB, private evidence bundle at most 2 MiB, policy manifest at most 64 KiB, and public report at most 64 KiB;
- JSON nesting depth at most 16, at most 1,024 total evidence references, and no additional-reason tuple longer than 34;
- identifiers and enum text at most 64 ASCII bytes, canonical symbols at most 32 ASCII bytes, source/authority/schema/calculation identifiers at most 256 ASCII bytes, and no source locator in the public report;
- canonical decimal text at most 32 ASCII bytes, finite and strictly greater than zero, with at most 20 significant digits and scale from 0 through 10; and
- provider attempts, network attempts, storage-write attempts, clock reads, random values, and environment-dependent fallback attempts are exactly zero in the pure evaluator.

Oversize, over-depth, malformed, duplicate, noncanonical, or unknown request
input is rejected before path allocation. A well-formed admitted request with
missing or bad mandatory market evidence receives bounded
`INSUFFICIENT_EVIDENCE`; it is never repaired by truncation.

## Validation invariants

A later implementation must reconstruct rather than trust all derived fields and
must reject a report or internal result unless all applicable equations hold:

```text
comparison_session == official_sessions[0].session_date
decision_session   == official_sessions[20].session_date
decision_cutoff    == official_sessions[20].close_at
knowledge_cutoff   == decision_cutoff
len(official_sessions) == 21
len(members) == 50 == count(unique isin) == count(unique symbol)
prior_session_i == comparison_session for every i
current_session_i == decision_session for every i

OBSERVED => advances + declines + unchanged == 50
OBSERVED => exactly one direction per member
OBSERVED => regime_label is non-null and counts are all non-null
OBSERVED => primary_reason is null and additional_reasons == ()
INSUFFICIENT_EVIDENCE => regime_label is null
INSUFFICIENT_EVIDENCE => advances == declines == unchanged == null
INSUFFICIENT_EVIDENCE => primary_reason is non-null
```

An observed label is recomputed from the counts, and every direction is
recomputed from private Decimal values. Digests, endpoint positions, schedule
consecutiveness, cutoff clocks, memberships, `CLOSE` field identity, exact daily
fact versions, corporate-action interval coverage, revision lineage, and all
nullability/count invariants are deeply checked. A caller-supplied count, label,
endpoint, cutoff, or comparability boolean has no authority.

## Edge-case truth table

| Case | Required result |
|---|---|
| 30 advance, 20 decline | `OBSERVED / BROAD_ADVANCE` |
| 30 advance, 19 decline, 1 unchanged | `OBSERVED / BROAD_ADVANCE` |
| 20 advance, 30 decline | `OBSERVED / BROAD_DECLINE` |
| 29 advance, 29 decline is impossible with 50; 25/25/0 | `OBSERVED / MIXED_PARTICIPATION` |
| 29 advance, 0 decline, 21 unchanged | `OBSERVED / MIXED_PARTICIPATION` |
| 0 advance, 0 decline, 50 unchanged | `OBSERVED / MIXED_PARTICIPATION` |
| Equal Decimal endpoint values with different admitted scale | one `UNCHANGED` |
| 20 elapsed days but not exactly 20 official-session transitions | reject/fail closed; never classify |
| Proven holiday between endpoints | skip it; it consumes no session step |
| Unresolved closure, special session, timing overlay, or 20th predecessor | `INSUFFICIENT_EVIDENCE / null` |
| 49 valid members, 51 rows, duplicate ISIN/symbol, or current-list backfill | `INSUFFICIENT_EVIDENCE / null` |
| One missing, late, corrupt, conflicting, incomplete, unauthorized, or incomparable close | `INSUFFICIENT_EVIDENCE / null`, no partial counts |
| Split/bonus/rights event or unproven negative completeness | `INSUFFICIENT_EVIDENCE / null`; no silent adjustment |
| Evidence/revision first known after cutoff | `INSUFFICIENT_EVIDENCE / null` for this replay |
| Float, NaN, Infinity, negative/zero close, duplicate JSON key, unknown enum/field | invalid admission; no report |
| Same evidence supplied in shuffled set order | identical canonical input and report bytes |
| Later correction or code/policy change | new identities; old report remains immutable |

## Package and application boundary

The future domain package may contain only immutable schema values, canonical
validation/identity helpers, and a pure deterministic Market Regime reducer. It
must have no provider client, HTTP/network port, credential reader, filesystem
search, writable storage, clock, calendar library as authority, LLM call, CLI
renderer, or source acquisition. The application layer may load an explicitly
identified already-retained private bundle, verify it, call the pure reducer,
and render the separate public `MarketRegimeReportV1`. Source adapters,
acquisition, capture authorization, and runtime surfaces require separately
approved work.

`PublicCommandReportV1` remains untouched and frozen for its existing candle
`download | coverage | query` contracts. Market Regime must not add a mode or
fields to it. Any future CLI/API/MCP wrapper uses the same
`nifty50-market-regime@v1` domain request/report and a separate renderer; no
wrapper may recompute market facts or expose the private close inputs.

## Versioning and implementation handoff

Any change to endpoint distance or session selection, `CLOSE`, Decimal semantics,
equality, comparability path, exact-50 denominator, threshold value or
inclusivity, label/state/reason enum or precedence, schema field/nullability,
canonicalization, identity coverage, public redaction, authority/cutoff rule,
validation invariant, or bound is a breaking contract change and requires a new
contract version. A source-policy or calculation/code revision also changes its
bound identity even when the outer contract version remains compatible. New
labels or a confidence score can never be slipped into V1.

ARK-166 authorizes documentation and executable documentation assertions only.
It does not authorize a classifier, provider, source, acquisition, application,
CLI, API, MCP server, retained-evidence classification, performance study, or
runtime. The Sprint 4/5 evidence remains not ready: 31 sessions from 2026-07-01
through 2026-08-12, a current list that cannot prove historical membership,
1,550 insufficient stock/session pairs, raw prices, and unsupported adjusted
price, corporate-action completeness, and historical symbol-change authority
cannot yield an observed V1 label. Synthetic fixtures may later prove mechanics only; they cannot validate effectiveness or cure evidence blockers.


## Source and authority policy retained from ARK-165

No new market-data source is admitted. NSE Indices Limited is the authoritative
Nifty 50 membership and reconstitution authority; NSE is the authoritative
exchange authority for Capital Market sessions, closures, special sessions,
timing changes, and corrections. The only price input is the existing private
provider-independent `nse-session-ohlcv@v1` fact. Corporate-action comparability
requires authoritative cutoff-safe positive status, negative completeness, and
revision lineage; Upstox observations remain discovery evidence only. No index
price series, India VIX, macro source, provider shortcut, or current
constituents for a historical session is admitted.

A future bounded file adapter must reject symlink and non-regular inputs, use
no-follow reads, and publish with copy-on-write replacement. Those adapter rules
do not grant the pure evaluator I/O.
