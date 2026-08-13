# Market Regime v1 Fact Contract

Status: **ARK-166 APPROVED — FROZEN FACT CONTRACT**
Decisions: ARK-165 (scope and input policy), ARK-166 (complete V1 fact contract)
Contract version: `nifty50-market-regime@v1`

This document extends, and does not replace, ARK-165. It freezes the Market
Regime V1 rule, evidence boundary, typed facts, deterministic failure behavior,
identities, and implementation handoff. It approves no source adapter,
classifier implementation, provider call, acquisition, CLI, API, MCP surface,
or runtime. Implementation remains a later strict-TDD task.

## Boundary evaluation and rule decision

- Expected value: one reproducible breadth fact gives downstream research bounded end-of-day Nifty 50 context without an indicator bundle.
- Scope fit: equal participation of the exact point-in-time 50-name cash-equity cohort is the sole ARK-165 factor family.
- Material risk: lookback and threshold choices could be fitted, and missing or incomparable members could manufacture breadth.
- Smallest alternative: compare one comparable `CLOSE` at two exact official-session endpoints, count every member once, and fail closed unless all 50 are valid.
- Decision: **accepted — freeze an exact 20-official-session comparison and an inclusive 30-of-50 supermajority for V1.**

Twenty official-session transitions are roughly one swing month while remaining
simple and interpretable. Thirty of 50 is an exact 60% supermajority. These are
design priors, not fitted parameters; no retained outcome analysis,
effectiveness, accuracy, profitability, or prediction claim justifies them.
One-session direction and 26-of-50 were rejected as respectively too noisy and
too close to a bare majority. Multiple windows, optimized thresholds, weights,
and confidence scores were rejected as extra degrees of freedom. An empirical
change requires a new contract version and out-of-sample governance.

## Purpose, scope, and non-claims

Market Regime answers only: *for one completed authoritative NSE Capital Market
decision session, how many of the exactly 50 point-in-time Nifty 50 members have
a comparable close above, below, or equal to their close exactly 20 official
sessions earlier?* The market endpoint is the exact decision-session close. The
evidence used to establish that completed fact is collected only through the
separate fixed post-close boundary defined below.

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

### Exact endpoints and cohort

Let `S[0] < ... < S[20] < S[21]` be 22 consecutive authoritative NSE Capital
Market official sessions. `S[20]` is `decision_session`, `S[0]` is
`comparison_session`, and `S[21]` is used only to derive the post-close evidence
boundary. The comparison endpoint is reached by stepping backward exactly
**20 official sessions** from the decision session. It is not 20 elapsed days,
20 weekdays, a duration, or “approximately a month.” Holidays, closures, and
non-session dates consume no step. A special Capital Market session consumes a
step only when the authoritative schedule and its applicable corrections prove
it. An unresolved date, special-session scope, closure, timing correction, or
next-session open fails closed; a built-in calendar cannot fill it.

The cohort is exactly 50 unique ISIN-first Nifty 50 members whose point-in-time
membership intervals cover `decision_session`. Membership at the older endpoint
is neither required nor inferred: the exact decision-session cohort is followed
backward. A symbol change never changes ISIN identity, and unresolved identity
continuity is insufficient. No current-list backfill, substitution,
deduplication, imputation, survivorship filter, weighting, reduced denominator,
or 49-of-49 classification is allowed.

### Comparable close and equality

For every cohort member `i`, V1 compares two exact finite positive Decimal
values designated as `CLOSE` by verified complete `nse-session-ohlcv@v1` daily
facts:

```text
current_i = comparable CLOSE(i, S[20])
prior_i   = comparable CLOSE(i, S[0])

ADVANCE   iff Decimal(current_i) > Decimal(prior_i)
DECLINE   iff Decimal(current_i) < Decimal(prior_i)
UNCHANGED iff Decimal(current_i) == Decimal(prior_i)
```

There is no binary float, tolerance, tick rounding, percentage return,
quantization, adjusted epsilon, or hidden value. Numeric equality is
`UNCHANGED`. Every admitted decimal has one canonical textual form; for example,
`100` is admitted while external canonical bytes containing `100.0` for that
value are rejected. Equality therefore never depends on alternate admitted
scales.

V1's sole comparability path is `RAW_CLOSE_NO_BREAK_PROVEN`.
`CorporateActionComparabilityFactV1` must positively bind the ISIN and inclusive
endpoint interval to `NO_BREAK`, and must carry its typed status, negative
completeness, revision, and identity-continuity proofs. The raw daily facts stay
immutable. V1 does not adjust prices. A potentially breaking event, unresolved
terms, incomplete negative evidence, unproved revision lineage, or unproved
identity continuity makes the whole result `INSUFFICIENT_EVIDENCE`. Adjusted or
back-adjusted series are not admitted.

### Counts, state, and label

Only after every evidence gate passes are counts defined over exactly 50
members:

```text
advances  = count(direction_i == ADVANCE)
declines  = count(direction_i == DECLINE)
unchanged = count(direction_i == UNCHANGED)

BROAD_ADVANCE       iff advances >= 30
BROAD_DECLINE       iff declines >= 30
MIXED_PARTICIPATION otherwise
```

The comparisons are ordered as written. With 50 mutually exclusive
observations, both directional thresholds cannot hold. Thirty advances is
`BROAD_ADVANCE`; 30 declines is `BROAD_DECLINE`; every case with both below 30,
including 50 unchanged, is `MIXED_PARTICIPATION`.

The closed `evidence_state` enum is `OBSERVED | INSUFFICIENT_EVIDENCE`. The
closed observed `regime_label` enum is
`BROAD_ADVANCE | BROAD_DECLINE | MIXED_PARTICIPATION`. For `OBSERVED`, the label
and all counts are non-null. For `INSUFFICIENT_EVIDENCE`, `regime_label = null`
and `advances = declines = unchanged = null`; partial counts, a prior label,
confidence, and best effort are forbidden. Insufficiency is a successful domain
fact outcome, not an exception.

## Decision market endpoint and feasible evidence cutoff

The market endpoint and knowledge boundary are intentionally different:

```text
decision_market_close = S[20].close_at
evidence_cutoff       = S[21].open_at
knowledge_cutoff      = evidence_cutoff
```

All three values are reconstructed from `SessionScheduleFactV1`; none is a
request or caller field. `S[21]` is the next official Capital Market session
under the retained authoritative base schedule plus every applicable retained
correction, closure, timing change, and special-session overlay.
`evidence_cutoff` must be strictly later than `decision_market_close`. This fixed
post-close interval makes publication and immutable capture of the completed
daily close feasible while preventing the cutoff from drifting with evaluation
time. If the next official open or an applicable correction cannot be proved,
the result is insufficient rather than guessed.

For every mandatory evidence item, authoritative publication (when the class
has a publication clock), response completion, retrieval, and immutable
retention must each be at or before `evidence_cutoff`. Applicability/effective
scope must also cover the claimed member, session, or interval. A missing clock
cannot be invented. Publisher business dates, HTTP `Date`/`Last-Modified`,
filesystem times, report time, replay wall clock, commit time, and caller
`known_at` do not prove availability. Evidence first published, completed,
retrieved, retained, revised, or disambiguated after the evidence cutoff is late
for this report. Later corrections produce new identities and never rewrite a
prior point-in-time result.

The wider knowledge boundary does **not** widen any price fact. A
`DailyCloseFactV1` may describe only one named completed official session. The
current fact's market-event scope ends exactly at
`decision_market_close`; the prior fact ends at `S[0].close_at`. No trade, bar,
quote, auction result, or other trading observation from `S[21]` may enter any
price or comparability fact. The next session contributes schedule metadata only
for deriving its open. Nearest-date fallback and “previous available candle” are
forbidden.

## Lexical types and closed authorities

Every conceptual object below is closed: unknown or missing fields, duplicate
JSON keys, unknown enums, wrong types, and invalid nullability are structural
admission errors. The following lexical contracts are exact:

- `Sha256`: `^[0-9a-f]{64}$`.
- `LocalDate`: zero-padded `YYYY-MM-DD` that is a real Gregorian date.
- `UtcInstant`: `YYYY-MM-DDTHH:MM:SS.ffffffZ`, exactly six fractional digits.
- `Isin`: `^[A-Z]{2}[A-Z0-9]{9}[0-9]$`, exactly 12 ASCII characters, plus a valid ISO 6166/Luhn check digit.
- `CanonicalSymbol`: `^[A-Z0-9][A-Z0-9&.-]{0,31}$`, 1 through 32 ASCII bytes.
- `BoundedAscii`: `^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$`, 1 through 256 ASCII bytes.
- `CanonicalDecimal`: `^(?:0\.[0-9]*[1-9]|[1-9][0-9]*(?:\.[0-9]*[1-9])?)$`, at most 32 ASCII bytes, at most 20 significant digits, scale 0 through 10, finite, and strictly positive.

The only `AuthorityIdentityV1` values are `NSE_INDICES`, `NSE_CM`, and
`ADMITTED_EQUITY_FACT_PIPELINE`. Arbitrary authority strings are forbidden.
`tuple[T, a..b]` is immutable with the stated inclusive size bound.

## Request, typed attempts, and structural admission

### Immutable request

```text
MarketRegimeRequestV1 {
  contract_version: Literal["nifty50-market-regime@v1"]
  segment: Literal["NSE_EQ"]
  decision_session: LocalDate
  request_identity_sha256: Sha256
}
```

The request identity hashes canonical request content excluding only its own
field. The request cannot contain a cutoff, comparison date, cohort, symbols,
label, counts, lookback, threshold, raw OHLC, source locator, provider, or
configuration.

### Attempt envelope for absent, late, invalid, and irregular evidence

External byte parsing is deliberately separated from domain completeness.
Malformed UTF-8/JSON, a noncanonical byte sequence, unknown fields, an invalid
lexical value, over-depth input, or more than 51 received rows is a structural
parse failure and produces no `MarketRegimeReportV1`. After structural parsing,
a well-formed `EvidenceAttemptV1` can truthfully preserve missing, late, invalid,
49-row, 51-row, and duplicate-row outcomes without pretending that an exact
verified fact already exists.

```text
EvidenceRequestIdentityV1 {
  evidence_kind: Literal["MEMBERSHIP", "SESSION_SCHEDULE", "PRIOR_CLOSES",
                         "CURRENT_CLOSES", "CORPORATE_COMPARABILITY"]
  authority: AuthorityIdentityV1
  decision_session: LocalDate
  scope: Literal["DECISION_MEMBERSHIP", "TWENTY_PREDECESSORS_DECISION_NEXT",
                 "PRIOR_ENDPOINT_CLOSE", "CURRENT_ENDPOINT_CLOSE",
                 "COMPARABILITY_INTERVAL"]
  subject_isin: Isin | null
  subject_session: LocalDate | null
}

EvidenceAttemptFailureV1 = Literal[
  "NOT_RETURNED", "AFTER_EVIDENCE_CUTOFF", "INVALID_SOURCE_ROW",
  "IDENTITY_MISMATCH", "UNAUTHORIZED_AUTHORITY", "PUBLICATION_UNPROVEN",
  "CLOCK_UNTRUSTED", "LICENCE_UNRESOLVED"
]

EvidenceAttemptV1 {
  evidence_kind: same closed kind enum
  requested_identities: tuple[EvidenceRequestIdentityV1, 1..50]
  payload: MembershipCandidatePayloadV1 | ScheduleCandidatePayloadV1 |
           DailyCloseCandidatePayloadV1 | ComparabilityCandidatePayloadV1 | null
  failure: EvidenceAttemptFailureV1 | null
  attempt_identity_sha256: Sha256
}
```

Each payload variant and received row is also closed and typed:

```text
MembershipCandidateRowV1 {
  isin: Isin
  symbol: CanonicalSymbol
  effective_from: LocalDate
  effective_through: LocalDate | null
  provenance: ProvenanceV1
}
MembershipCandidatePayloadV1 {
  received_rows: tuple[MembershipCandidateRowV1, 0..51]
}

ScheduleCandidateRowV1 {
  session_date: LocalDate
  open_at: UtcInstant
  close_at: UtcInstant
  applied_corrections: tuple[ScheduleCorrectionV1, 0..32]
  provenance: ProvenanceV1
}
ScheduleCandidatePayloadV1 {
  received_rows: tuple[ScheduleCandidateRowV1, 0..51]
}

DailyCloseCandidateRowV1 {
  isin: Isin
  symbol: CanonicalSymbol
  session_date: LocalDate
  field: Literal["CLOSE"]
  close: CanonicalDecimal
  market_scope_ends_at: UtcInstant
  provenance: ProvenanceV1
}
DailyCloseCandidatePayloadV1 {
  received_rows: tuple[DailyCloseCandidateRowV1, 0..51]
}

ComparabilityCandidateRowV1 {
  isin: Isin
  interval_from: LocalDate
  interval_through: LocalDate
  comparison_basis: Literal["RAW_CLOSE_NO_BREAK_PROVEN"]
  status: Literal["NO_BREAK"]
  status_proof: CorporateActionStatusProofV1
  negative_completeness_proof: NegativeCompletenessProofV1
  revision_proof: RevisionLineageProofV1
  identity_continuity_proof: IdentityContinuityProofV1
}
ComparabilityCandidatePayloadV1 {
  received_rows: tuple[ComparabilityCandidateRowV1, 0..51]
}
```

These forward references resolve to the exact immutable proof/provenance schemas
in “Verified typed market facts”; they are not mappings or opaque provider rows.
An invalid row that cannot satisfy even this structural shape is represented by
the envelope's `INVALID_SOURCE_ROW` failure, optionally alongside the other
well-formed received rows.

The kind pins the payload variant and exact requested identities.
`MEMBERSHIP` requests one `DECISION_MEMBERSHIP` scope identity.
`SESSION_SCHEDULE` requests one `TWENTY_PREDECESSORS_DECISION_NEXT` scope identity;
its payload must ultimately prove 22 exact session rows, but the request does not
pretend to know their dates before schedule evidence resolves them.
`PRIOR_CLOSES` and `CURRENT_CLOSES` each request exactly the same 50 resolved
cohort ISINs at their respective resolved endpoint. `CORPORATE_COMPARABILITY`
requests exactly those 50 resolved ISINs over `[S[0], S[20]]`. Thus every
attempt records what was actually requested, not a generic source label.
Requested identities are strictly sorted and unique. Each payload holds
`received_rows: tuple[TypedCandidateRowV1, 0..51]` of its pinned row type.
Candidate rows are structurally typed but not asserted to be complete, unique,
timely, authoritative, or semantically valid.

At least one of `payload` and `failure` must be non-null. A clean attempt has a
payload and null failure; a missing attempt has null payload and
`NOT_RETURNED`; a late or invalid attempt may retain its bounded payload and a
typed failure. The reducer validates the requested/received identity equations.
Zero or 49 rows, 51 rows, duplicates, missing requested identities, extra
identities, or a typed failure produce ordered domain insufficiency reasons,
null label, and null counts. They are not structural parse failures and they are
never repaired by truncation, deduplication, or denominator reduction.

## Verified typed market facts

Candidate payloads can support classification only when pure validation
constructs the following immutable facts. These facts contain the referenced
market semantics; an `EvidenceRefV1` or caller digest alone can never stand in
for their content.

```text
EvidenceClockV1 {
  published_at: UtcInstant | null
  response_completed_at: UtcInstant
  retrieved_at: UtcInstant
  retained_at: UtcInstant
}

ProvenanceV1 {
  authority: AuthorityIdentityV1
  source_identity: BoundedAscii
  schema_version: BoundedAscii
  object_identity_sha256: Sha256
  revision_identity_sha256: Sha256
  supersedes_identity_sha256: Sha256 | null
  clock: EvidenceClockV1
}

MembershipMemberV1 {
  isin: Isin
  symbol: CanonicalSymbol
  effective_from: LocalDate
  effective_through: LocalDate | null
}

MembershipFactV1 {
  authority: Literal["NSE_INDICES"]
  decision_session: LocalDate
  members: tuple[MembershipMemberV1, 50]
  provenance: ProvenanceV1
}

ScheduleCorrectionV1 {
  affected_session: LocalDate
  correction_kind: Literal["CLOSURE", "SPECIAL_SESSION", "OPEN_TIME", "CLOSE_TIME"]
  corrected_open_at: UtcInstant | null
  corrected_close_at: UtcInstant | null
  provenance: ProvenanceV1
}

OfficialSessionV1 {
  session_date: LocalDate
  open_at: UtcInstant
  close_at: UtcInstant
}

SessionScheduleFactV1 {
  authority: Literal["NSE_CM"]
  sessions: tuple[OfficialSessionV1, 22]
  applied_corrections: tuple[ScheduleCorrectionV1, 0..32]
  base_schedule_provenance: ProvenanceV1
}

DailyCloseFactV1 {
  authority: Literal["ADMITTED_EQUITY_FACT_PIPELINE"]
  schema_version: Literal["nse-session-ohlcv@v1"]
  isin: Isin
  symbol: CanonicalSymbol
  session_date: LocalDate
  field: Literal["CLOSE"]
  close: CanonicalDecimal
  market_scope_ends_at: UtcInstant
  provenance: ProvenanceV1
}

CorporateActionStatusProofV1 {
  authority: Literal["NSE_CM"]
  isin: Isin
  interval_from: LocalDate
  interval_through: LocalDate
  status: Literal["NO_BREAK"]
  checked_event_identities: tuple[Sha256, 0..16]
  provenance: ProvenanceV1
}

NegativeCompletenessProofV1 {
  authority: Literal["NSE_CM"]
  isin: Isin
  interval_from: LocalDate
  interval_through: LocalDate
  covered_event_classes: Literal["ALL_COMPARABILITY_BREAKING_ACTIONS_V1"]
  completeness: Literal["COMPLETE"]
  provenance: ProvenanceV1
}

RevisionLineageProofV1 {
  authority: Literal["NSE_CM"]
  selected_revision_identity_sha256: Sha256
  checked_through: UtcInstant
  lineage_status: Literal["CURRENT_AT_EVIDENCE_CUTOFF"]
  provenance: ProvenanceV1
}

IdentityContinuityProofV1 {
  authority: Literal["NSE_CM"]
  isin: Isin
  interval_from: LocalDate
  interval_through: LocalDate
  prior_symbol: CanonicalSymbol
  current_symbol: CanonicalSymbol
  continuity_status: Literal["SAME_ISSUE_CONTINUITY_PROVEN"]
  provenance: ProvenanceV1
}

CorporateActionComparabilityFactV1 {
  authority: Literal["NSE_CM"]
  isin: Isin
  interval_from: LocalDate
  interval_through: LocalDate
  comparison_basis: Literal["RAW_CLOSE_NO_BREAK_PROVEN"]
  status: Literal["NO_BREAK"]
  status_proof: CorporateActionStatusProofV1
  negative_completeness_proof: NegativeCompletenessProofV1
  revision_proof: RevisionLineageProofV1
  identity_continuity_proof: IdentityContinuityProofV1
}

VerifiedMarketRegimeFactsV1 {
  request: MarketRegimeRequestV1
  membership: MembershipFactV1
  schedule: SessionScheduleFactV1
  prior_closes: tuple[DailyCloseFactV1, 50]
  current_closes: tuple[DailyCloseFactV1, 50]
  comparability: tuple[CorporateActionComparabilityFactV1, 50]
  source_policy_identity_sha256: Sha256
  validation_policy_identity_sha256: Sha256
  policy_identity_sha256: Sha256
  code_identity_sha256: Sha256
  input_identity_sha256: Sha256
}
```

The pure domain admission/reducer receives already parsed typed attempts and
resolved typed facts/bytes. A bounded application adapter must open explicitly
identified content-addressed objects, verify checksums, parse canonical bytes,
and close them before the reducer is called. No unresolved path, URI, locator,
callback, stream, or opaque evidence reference enters the reducer. The reducer
performs no I/O, provider lookup, filesystem read, network access, clock read,
or calendar lookup. It validates facts, emits either the observed result or the
ordered insufficiency reasons with null classification, and never catches a
structural byte parse failure as insufficiency.

## Cross-fact equations and validation invariants

All derived fields are reconstructed, never trusted:

```text
membership.authority == NSE_INDICES
schedule.authority == NSE_CM
all daily.authority == ADMITTED_EQUITY_FACT_PIPELINE
all comparability.authority == NSE_CM
all nested provenance.authority == the containing fact/proof authority

schedule.sessions == exactly S[0]..S[21], strictly ascending and consecutive
comparison_session == S[0].session_date
decision_session == S[20].session_date
decision_market_close == S[20].close_at
evidence_cutoff == knowledge_cutoff == S[21].open_at
decision_market_close < evidence_cutoff

len(membership.members) == 50
member ISINs and symbols are each unique and strictly ISIN-sorted
set(prior close ISINs) == set(current close ISINs)
                       == set(comparability ISINs)
                       == set(membership ISINs)
all four 50-item tuples are strictly ISIN-sorted
prior session for every ISIN == comparison_session
current session for every ISIN == decision_session
prior market_scope_ends_at == S[0].close_at
current market_scope_ends_at == decision_market_close
comparability interval == [comparison_session, decision_session]
all proof ISINs and intervals == their containing comparability fact
revision_proof.checked_through == evidence_cutoff
all mandatory evidence clocks <= evidence_cutoff
membership interval for every member covers decision_session

OBSERVED => advances + declines + unchanged == 50
OBSERVED => exactly one recomputed direction per member
OBSERVED => label and all counts are non-null
OBSERVED => primary_reason is null and additional_reasons == ()
INSUFFICIENT_EVIDENCE => label and all counts are null
INSUFFICIENT_EVIDENCE => primary_reason is non-null
```

Schedule corrections are strictly sorted by `(affected_session,
correction_kind, revision_identity_sha256)`, unique, and applied rather than
merely listed. Daily and corporate facts are cross-bound by ISIN, interval,
symbol continuity, revision, and authority. No next-session trading observation
is admissible. A caller-supplied count, label, endpoint, cutoff, authority,
comparability boolean, or digest-looking text has no authority.

## Private input and public report

`MarketRegimeEvidenceBundleV1` is the canonical private object containing the
request and `evidence_attempts: tuple[EvidenceAttemptV1, 1..5]` in dependency
order, plus source, validation, policy, code, and input identities. Membership
and schedule attempts come first. An endpoint or comparability attempt may
appear only after its exact 50 requested identities can be derived from verified
membership and schedule candidates; if that dependency is insufficient, the
later attempt is absent rather than fictional. No kind appears more than once. It may contain candidate close values and provenance but no open, high,
low, volume, intraday row, credentials, writable path, or caller conclusion.
`input_identity_sha256` hashes the entire canonical private bundle excluding
only itself.

The frozen semantic `policy_identity_sha256` binds contract/calculation
versions, fields, enums, 20-session rule, `CLOSE`, decimal operators, exact-50
rule, inclusive threshold, comparability path, reason order, canonical profile,
and bounds. `code_identity_sha256` identifies the reviewed future classifier
build. Neither is accepted solely because a caller supplies matching-looking
text.

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
  decision_market_close: UtcInstant | null
  evidence_cutoff: UtcInstant | null
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

The public report exposes aggregate facts and identities only: never raw OHLC,
close values, per-member direction, symbols/ISINs, provider payloads,
credentials, paths, free-form diagnostics, or an AI conclusion. The report
identity hashes the canonical report excluding itself. Identical admitted bytes
under identical policy and code produce byte-identical reports.

## Closed reason enum and precedence

The exact first-match precedence is declaration order:

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

Observed reports have no reasons. Insufficient reports use the earliest
applicable reason as primary and list every other applicable reason once in
declaration order. Discovery, candidate-row, map, and provider ordering do not
affect output. Malformed request or external canonical bytes are
`REQUEST_INVALID` at application admission and produce no report, so that value
is deliberately not a fact-reason member.

## Canonical JSON, ordering, and identity profile

All request, attempt, fact, policy, and report identity material uses one
profile:

1. UTF-8 only, no BOM, exactly one trailing LF; hashes include that LF.
2. Object keys lexicographically sorted by Unicode code point; compact `,` and `:` separators; no insignificant whitespace.
3. Strings must already be Unicode NFC. Invalid UTF-8, non-NFC, unpaired surrogates, and forbidden control characters are rejected, not repaired.
4. Duplicate keys, unknown/missing fields, invalid nullability, duplicate semantic identities, and bound violations are rejected before hashing.
5. JSON floats, NaN, Infinity, exponent notation, negative zero, and implementation-specific numeric spellings are forbidden. Counts are integers; market values are `CanonicalDecimal` strings.
6. Dates, instants, enums, ISINs, symbols, authorities, and digests use their exact lexical forms.
7. Every external array must already be in its schema order: attempts by declared kind, sessions by date, members and fact tuples by ISIN, corrections by their stated key, requested identities by their complete field tuple, and reasons by declaration order. Noncanonical ordering in external bytes is rejected; a parser never silently sorts admitted bytes.
8. A local typed builder may accept an unordered caller collection, defensively copy it, sort it **before serialization**, and emit the single canonical byte sequence. Once bytes exist, admission either accepts that exact sequence or rejects it. Replay reads the original identified bytes and performs no normalization.
9. Minimal JSON escaping is used; parsers reject trailing tokens, excessive size, and excessive nesting.

Thus shuffled external evidence bytes are rejected. Shuffled inputs to a typed
builder can produce identical canonical output only because normalization occurs
before bytes and identity exist. External decimal spelling is likewise never
normalized during admission. A supplied digest is only a claim; content is
validated and the digest reconstructed. Offline replay never searches for newer
files, consults the network/current clock, or mutates retained bytes.

## Immutability, copy safety, and bounds

All records are frozen values. Constructors defensively copy and deeply validate
caller mappings/sequences before tuple construction; no mutable alias is kept.
Accessors return immutable values or copies. Reusing a builder cannot alter
identities. A later persistence adapter uses validated copy-on-write publication
and rejects symlinks/non-regular inputs with no-follow reads.

Exact limits, including limit-plus-one tests, are:

- one request, 1 through 5 dependency-ordered evidence attempts, exactly 22 verified sessions, exactly 50 verified members, 50 prior closes, 50 current closes, and 50 comparability facts;
- each attempt payload contains 0 through 51 candidate rows; 51 is representable but semantically insufficient wherever exactly 50 are required;
- at most 16 checked corporate-action event identities per member and at most 32 schedule corrections;
- request bytes at most 4 KiB, private bundle at most 2 MiB, policy manifest and public report each at most 64 KiB;
- JSON nesting at most 16 and additional reasons at most 34;
- lexical bounds are exactly those in “Lexical types and closed authorities”; and
- provider attempts, network attempts, storage writes, filesystem reads, clock reads, random values, and calendar fallback attempts are exactly zero in the pure reducer.

Oversize, over-depth, malformed, or noncanonical external bytes are rejected
before domain evaluation. A structurally valid attempt with missing or bad
mandatory evidence returns bounded `INSUFFICIENT_EVIDENCE` and is never repaired.

## Edge-case truth table

| Case | Required result |
|---|---|
| 30 advance, 20 decline | `OBSERVED / BROAD_ADVANCE` |
| 30 advance, 19 decline, 1 unchanged | `OBSERVED / BROAD_ADVANCE` |
| 20 advance, 30 decline | `OBSERVED / BROAD_DECLINE` |
| 25 advance, 25 decline | `OBSERVED / MIXED_PARTICIPATION` |
| 29 advance, 0 decline, 21 unchanged | `OBSERVED / MIXED_PARTICIPATION` |
| 0 advance, 0 decline, 50 unchanged | `OBSERVED / MIXED_PARTICIPATION` |
| External decimal `100.0` when canonical value is `100` | structural rejection; no report |
| 20 elapsed days but not 20 official transitions | insufficient; never classify |
| Proven holiday between endpoints | skip it; it consumes no session step |
| Unresolved special session, timing overlay, predecessor, or next official open | `INSUFFICIENT_EVIDENCE / null` |
| Current close published and retained after decision close but by next official open | eligible if every other gate passes |
| Evidence first published or retained after next official open | `INSUFFICIENT_EVIDENCE / null` |
| Any next-session trading observation in a price fact | `INSUFFICIENT_EVIDENCE / null` |
| 49 rows, 51 rows, or duplicate ISIN/symbol in a well-formed attempt | `INSUFFICIENT_EVIDENCE / null`, never admission contradiction |
| One missing, late, corrupt, conflicting, incomplete, unauthorized, or incomparable close | `INSUFFICIENT_EVIDENCE / null`, no partial counts |
| Split/bonus/rights event or unproven negative completeness | `INSUFFICIENT_EVIDENCE / null`; no adjustment |
| Float, NaN, Infinity, duplicate JSON key, unknown field, or more than 51 rows | structural rejection; no report |
| Shuffled external canonical array | structural rejection; no report |
| Shuffled local builder collection | sort before serialization; one canonical output |
| Later correction or code/policy change | new identities; old report stays immutable |

## Package and application boundary

The future domain package may contain only immutable schema values, canonical
validation/identity helpers, pure attempt/fact admission, and a pure deterministic
Market Regime reducer. It has no provider client, HTTP/network port, credential
reader, filesystem access, writable storage, clock, calendar authority, LLM
call, CLI renderer, or source acquisition. The bounded application adapter may
load explicitly identified retained bytes, verify and parse them, close all
resources, call the domain, and render `MarketRegimeReportV1`. Acquisition,
capture authorization, and runtime surfaces require separately approved work.

`PublicCommandReportV1` remains untouched for candle `download | coverage |
query`. Market Regime adds no mode or fields to it. Any future CLI/API/MCP
wrapper uses the same domain request/report and a separate renderer; it cannot
recompute facts or expose private close inputs.

## Versioning and implementation handoff

A change to endpoint distance, session selection, market/evidence boundary,
`CLOSE`, decimal semantics, equality, comparability, denominator, threshold,
enums/precedence, schemas/nullability, canonicalization, identity coverage,
redaction, authority, invariant, or bound is breaking and requires a new
contract version. A source-policy or code revision also changes its bound
identity.

ARK-166 authorizes documentation and executable documentation assertions only.
It does not authorize a classifier, provider, source, acquisition, application,
CLI, API, MCP server, retained-evidence classification, performance study, or
runtime. Sprint 4/5 evidence remains not ready: 31 sessions from 2026-07-01
through 2026-08-12, a current list that cannot prove historical membership,
1,550 insufficient stock/session pairs, raw prices, and unsupported adjusted
price, corporate-action completeness, and historical symbol-change authority
cannot yield an observed V1 label. Synthetic fixtures may later prove mechanics
only; they cannot validate effectiveness or cure evidence blockers.

## Source and authority policy retained from ARK-165

No new market-data source is admitted. NSE Indices Limited (`NSE_INDICES`) is
the authoritative Nifty 50 membership/reconstitution authority. NSE Capital
Market (`NSE_CM`) is authoritative for sessions, corrections, and corporate
action/identity evidence. The only price fact is the existing private
provider-independent `nse-session-ohlcv@v1` fact exposed by
`ADMITTED_EQUITY_FACT_PIPELINE`. Upstox observations remain discovery evidence
only. No index price series, India VIX, macro source, provider shortcut, or
current constituents for a historical session is admitted.
