# Sector Participation v1 Validation Protocol

Status: **OWNER APPROVED — PREREGISTERED; NO IMPLEMENTATION OR OBSERVED OUTCOME**
Contract under validation: `nifty50-sector-participation@v1`
Owner approval date: **2026-08-13 IST**

This protocol freezes future mechanical validation and one-bundle readiness
questions before implementation or sector counts exist. It authorizes
repository documentation edits and review only and, per the owner clarification,
adds no documentation assertion and no test file. It does not authorize source
contact, licence acceptance, acquisition, provider/data/credential access,
storage, implementation, runtime, a readiness run, or a Sector Participation
report.

## Purpose, hypotheses, and prohibited interpretation

Layer A asks whether a future pure implementation exactly realizes Plan 14 with
zero side effects. Layer B asks only whether one sealed future bundle has every
required authority, byte, selector, clock, lineage, manifest, licence, upstream,
code, policy, and audience prerequisite. Layer B's readiness result contains no
sector labels, sector counts, member directions, or outcome preview.

The mechanical hypothesis is exact equality between an independent oracle and
every state, count, equation, reason, nullability, redaction, identity, and
admission/no-report decision. Tolerance is zero. The readiness hypothesis is
only that a complete sealed bundle is `READY` and every missing prerequisite is
`BLOCKED` with exact reasons.

No return, percentage, rank, strength, leader, laggard, rotation, performance,
effectiveness, usefulness, prediction, threshold search, market narrative, or
trading outcome may be computed, inspected, optimized, or reported. There is no
true class, predictive target, or usefulness metric.

Layer A emits only conformance evidence about synthetic mechanics; it emits no
market label and cannot establish source, evidence, licence, audience, or
one-bundle readiness. Layer B emits only the readiness object defined below; it
does not reuse a Layer A pass/fail result as a market fact or inspect the future
report. Neither layer measures label quality, truth, usefulness, prediction, or
performance, and neither may be presented as evidence for any of them.

## Independent oracle and fixture boundaries

All Layer A fixtures are synthetic and visibly non-market. They use temporary
immutable bytes only and need no provider, retained market-data root, account,
credential, network, or production storage. The independent oracle:

1. parses the closed request, discriminated upstream envelope, evidence bundle,
   attempts, candidates, audience proof, and canonical bytes;
2. distinguishes structural parse/admission failure (no report) from a
   structurally valid domain insufficiency;
3. for an observed upstream branch, validates but never recomputes the bound
   Market Regime report/handoff and derives the exact 50 requested ISINs;
4. replays every candidate selector against immutable source-object bytes and
   independently reconstructs authority, source, schema, release, clocks,
   revision graph, manifest, licence proof, and 50 assignments;
5. joins exact handoff directions to exact assignments by ISIN and computes the
   four frozen equations; and
6. emits counts only when the owner-private proof and every gate pass; otherwise
   emits null sectors and exact reasons in frozen order.

The oracle is separately authored from the implementation under test. It may
consume the same frozen specification and canonical input bytes, but it must not
import or call the production parser, selector, canonicalizer, identity
projection, admission logic, grouping helper, reducer, fixtures, or generated
expected values. It reconstructs expected values from stdlib primitives and
compares the complete expected structural/no-report decision or complete
canonical report bytes, never only selected fields or implementation-produced
intermediate counts.

Production bounds are always exercised. Smaller helper cohorts may exhaustively
prove generic grouping only; they never replace exact-50 admission tests.
Repository documentation review in this slice checks only that this protocol
and contract text contain these semantics. It adds no assertion or test file and
is not evidence that any schema, selector, reducer, audience boundary, or
readiness gate is implemented.

## Layer A — preregistered strict-TDD mechanics

### Structural admission versus domain insufficiency

The suite first freezes a two-column oracle:

| Input class | Required behavior |
|---|---|
| malformed UTF-8/JSON, duplicate key, unknown/missing field, invalid union/nullability, noncanonical bytes, excessive nesting/bytes, >51 candidate rows | structural rejection; no report |
| well-formed upstream absent or insufficient envelope | report with `MARKET_REGIME_NOT_OBSERVED` and exact nullable endpoints |
| well-formed missing/late/0/49/51/duplicate/ambiguous/corrupt/wrong-tier/clock/licence/revision candidate | insufficient report with null sectors and exact reasons |
| fully verified observed branch and valid owner proof | observed owner-private report |

Every closed schema receives missing-field, unknown-field, wrong-type,
duplicate-key, invalid-enum, invalid-nullability, exact-limit, and
limit-plus-one cases. Tests explicitly cover `SectorParticipationRequestV1`,
both upstream envelope branches, `MarketRegimeSectorHandoffV1`, every candidate
and verified proof, `OwnerPrivateAudienceProofV1`, bundle, reducer input, and
report.

### Upstream envelope and endpoint oracle

Exhaust every discriminant/field combination. Only an `OBSERVED` envelope may
carry a handoff. `ABSENT` requires null report fields and yields null comparison,
close, cutoff, and Market Regime report identity. `INSUFFICIENT_EVIDENCE`
requires a bound Plan 12 report, no handoff, and copies exactly one of:

```text
SCHEDULE_UNVERIFIED => null / null / null
ENDPOINTS_VERIFIED_NEXT_OPEN_UNRESOLVED => value / value / null
CUTOFF_VERIFIED => value / value / value
```

Every well-formed absent/insufficient branch yields
`MARKET_REGIME_NOT_OBSERVED`. Foreign versions, malformed or noncanonical
report/handoff bytes, digest mismatch, inconsistent observed counts, an invalid
direction enum, a duplicate handoff ISIN, an externally unsorted
`handoff.members` tuple, and 49/51 handoff rows are structural no-report cases.
The ordering fixture swaps two otherwise valid exact-50 handoff rows and
recomputes the handoff digest; its digest-valid but noncanonical external order
is still structurally rejected. The duplicate fixture replaces one row's ISIN
with another present ISIN and recomputes the digest; its fixed 50-row shape does
not prevent structural rejection.

Only after both objects are canonically ordered, digest-valid, version-correct,
and the handoff has exactly 50 strict-sorted unique rows do report
identity/endpoint mismatch or direction-total mismatch yield
`MEMBER_DIRECTION_HANDOFF_INVALID`. No test derives a direction from close
values or replays Market Regime schedule/corporate-action logic.

### Candidate-to-verified selector oracle

Build canonical source objects whose selectors address every candidate field.
An independent stdlib selector implementation must reproduce exact selected
bytes and values. For taxonomy release, all 50 assignments, all revision nodes,
the lineage proof, every manifest entry, and the licence proof, tests assert the
full chain:

```text
receipt bytes -> receipt SHA-256 -> sealed source/schema/release binding
-> exact selector -> candidate value -> parsed verified value
-> object/revision/supersession identity -> containing fact identity
-> bundle/input/report identity
```

The oracle separately hashes the source, validation, privacy, licence, semantic,
and code manifest bytes. It requires the bundle and report identity claims,
including `licence_policy_identity_sha256` and the semantic manifest's
`policy_identity_sha256`, to equal Plan 14's exact one-manifest projections.

The requested-ISIN exact-order oracle starts from the strict ISIN-sorted
`handoff.members[*].isin` tuple, then rebuilds canonical, digest-valid attempt
and bundle bytes for each fixed-length-50 mutation: swap two positions
(permutation), replace one position with another present ISIN (duplicate plus
missing), and replace one position with a lexically valid nonmember ISIN
(missing/excess substitution). The unmodified ordered tuple proceeds; every
mutant remains structurally valid and yields `EVIDENCE_IDENTITY_MISMATCH` with
null sectors at its existing precedence, never structural rejection or a
classification ambiguity/corruption reason.

Zero-match, multi-match, out-of-range, escaped, mutable, or cross-object
selectors fail closed. Coordinated rehashing of object, candidate, attempt,
bundle, and caller-supplied manifests cannot replace the expected reviewed
build's sealed authority/source/schema/release, identity projection, selector
profile, clock authority, licence policy, privacy policy, or code identity.
No digest-only fixture can construct a verified release, assignment, lineage,
manifest, licence, audience, or reviewed-build fact.

The candidate-reason table in Plan 14 is parameterized row-for-row. It must prove
these exact families:

- null attempt/payload, zero and 49 rows, missing member, absent release/manifest;
- 51 rows, extra member, corrupt text/date/label/interval, selector mismatch;
- duplicate rows, overlapping intervals, conflicting labels/releases;
- wrong authority, source, schema, release, tier, or effective scope;
- each clock absent, one microsecond late, untrusted, rollback-conflicting, or
  forged from HTTP, filesystem, report, replay, or caller time;
- absent/digest-only/wrong-scope/wrong-date licence and each missing permission;
- absent selected revision, incomplete lineage, gap, orphan, missing edge,
  self-cycle, multi-node cycle, fork, conflicting current children, superseded
  selection, post-cutoff selection, checked-through before/after cutoff, and
  manifest/lineage disagreement; and
- every identity mismatch and final join/equation mismatch.

Effective-time and cutoff boundaries are partitioned, never described by an
overlapping shorthand. Let `D` be `decision_session` and `K` be
`knowledge_cutoff`. For the taxonomy release and every assignment:
Enumerate the full Cartesian matrix of `effective_from` in
`{D - 1 day, D, D + 1 day}` and `effective_through` in
`{D - 1 day, D, D + 1 day, null}`, plus invalid-date-text cases.

| Interval class | Exact generated cells | Exact result |
|---|---|---|
| valid and covering | `effective_from` is `D - 1 day` or `D`; `effective_through` is null, `D`, or `D + 1 day`; and the interval is non-inverted | no corrupt or effective-scope reason |
| valid and non-covering | a non-inverted interval starts at `D + 1 day`, or ends at `D - 1 day` | `SECTOR_EFFECTIVE_SCOPE_MISMATCH` |
| invalid/inverted | date text is semantically invalid, or non-null `effective_through < effective_from` | `SECTOR_CLASSIFICATION_CORRUPT`; if the independent coverage predicate also finds that `D` is not covered, additionally `SECTOR_EFFECTIVE_SCOPE_MISMATCH` |

The generator evaluates corruption and coverage as independent predicates over
every fact and row. A single invalid/inverted cell that also independently
misses `D`, or a fixture with one invalid/inverted interval and a separate valid
non-covering interval, therefore emits exactly
`[SECTOR_CLASSIFICATION_CORRUPT, SECTOR_EFFECTIVE_SCOPE_MISMATCH]` in Plan 14
declaration order. A corrupt cell for which coverage is not independently
defined emits only `SECTOR_CLASSIFICATION_CORRUPT`. The licence interval receives
the same date cells, but every invalid or non-covering licence proof maps only to
`LICENCE_UNRESOLVED` as Plan 14 requires.

Every required publication, response-completion, retrieval, and retention clock
is independently placed at `K - 1 microsecond`, `K`, and `K + 1 microsecond`;
equality passes, while the first instant after `K` yields
`SECTOR_CLASSIFICATION_LATE`. Lineage `checked_through` is placed one
microsecond before, exactly at, and one microsecond after `K`; only exact
equality passes and either mismatch yields
`SECTOR_CLASSIFICATION_REVISION_UNPROVEN`. Selected-revision publication and
knowledge edges receive the same boundary cases. Multi-fault fixtures assert
the complete reason tuple in Plan 14 declaration order, never a combined or
implementation-selected reason.

Tests evaluate multi-fault combinations so the earliest applicable reason is
primary and every lower applicable reason appears once in declaration order.
Discovery and candidate row order cannot alter domain reason ordering.

### Aggregation exhaustive oracle

For every possible sector size `n` from 1 through 50, enumerate every
nonnegative per-sector direction triple `(a, d, u)` satisfying `a + d + u = n`.
This is all 23,425 triples across the 50 sizes, with no sampling. Materialize
each triple inside an admitted exact-50 fixture; the remaining `50 - n` members
occupy deterministic distinct synthetic sector rows so the oracle independently
reconciles the selected row and the complete report.

Separately enumerate all 1,326 nonnegative production-wide direction triples
whose sum is 50. Exercise one 50-member sector, fifty singleton sectors, one
singleton plus 49, 25/25 sectors, and deterministic irregular partitions. The
oracle derives expected rows directly from the 50 `(ISIN, direction, sector)`
relations, never from reducer rows or implementation-produced subtotals. For
every case it proves the selected per-sector triple, every row equation, the
four global equations, exact equality to the upstream advances/declines/
unchanged triple, exactly 50 total contributions, and no missing, residual, or
double-counted member.

Each expected observed row has exactly `label`, `member_count`, `advances`,
`declines`, and `unchanged`; the oracle admits no extra row field, alias, or
derived percentage. For helper cohort sizes 0..8, enumerate all three-way
directions and every restricted-growth sector partition. At production
admission, exercise 0..49, 50, and 51 rows, duplicate/missing/extra joins, and
every sector-label boundary. Only exact 50 can be observed. Sector labels cover
1-byte and 128-byte valid NFC UTF-8 plus empty, 129-byte, padded,
control-character, invalid UTF-8, non-NFC, and visually similar distinct
labels.

### Properties and metamorphisms

Seeded generated tests retain the seed and smallest failing canonical fixture.
They assert:

- each upstream ISIN joins exactly once and contributes once to one direction
  and one exact sector;
- every row equation and all four global equations hold;
- observed output has 1..50 UTF-8-byte-sorted rows and no reasons;
- insufficient output has null sectors, at least one reason, and no partial or
  cached count reachable through serialization, copying, logs, or exceptions;
- external noncanonical order is rejected rather than silently sorted;
- immutable inputs are deeply copy-safe; and
- identical admitted canonical bytes and sealed policies produce byte-identical
  identities and reports with exactly zero I/O.

Safe synthetic metamorphisms are:

- permute the local insertion order of identical synthetic joint member facts:
  exhaust every permutation of fixed representative helper fixtures at sizes
  0..8 and use retained-seed exact-50 permutations; all rebuild the same
  canonical input, identities, and report bytes, while a noncanonical external
  tuple remains a structural rejection and is never silently repaired;
- bijectively rename synthetic sector labels: each renamed row retains its
  associated `(member_count, advances, declines, unchanged)` quadruple, global
  totals remain exact, output rows re-sort by renamed UTF-8 bytes, and every
  label-covered identity changes;
- bijectively rename synthetic ISINs in both handoff and assignment candidates:
  counts remain, covered identities change;
- exchange all `ADVANCE`/`DECLINE`: those columns/totals exchange and
  `UNCHANGED` remains;
- split/merge synthetic sector partitions: child rows sum to the parent while
  the identities change;
- add a lower-precedence fault: primary remains and the additional reason is
  inserted once at its declaration position; and
- mutate one identity-covered byte: its digest changes or admission rejects it.

These mechanics never authorize changing official labels. The post-cutoff
metamorphism is specifically two separate tests:

1. mutate only an external future-data store while replaying the **unchanged
   sealed old input**; the old report remains byte-identical because no external
   state is read; and
2. create a **separately sealed changed input** that contains the post-cutoff
   revision; source/revision/manifest/input/report identities and the derived
   outcome are new. The suite never requires byte identity across changed input.

### Schedule and corporate-action boundary adversaries

Inject upstream schedule corrections for closure, special session, open-time,
and close-time changes; duplicate/cyclic/conflicting correction revisions;
unresolved next open; and corporate-action status, negative-completeness,
revision-lineage, and identity-continuity defects. The expected downstream
behavior is only to accept or reject the exact bound upstream report/handoff.
Sector Participation must make zero schedule lookups, fold zero corrections,
read zero closes, classify zero actions, and derive zero member directions.

A corrected upstream report/handoff is a new immutable input with new identities.
An old sealed input remains unchanged. This suite guards against downstream
silently recomputing schedule corrections or corporate-action completeness from
raw evidence.

### Cross-authority no-lookahead matrix

Freeze one exact synthetic base fixture `B0`: strict-sorted valid ISINs
`I[0]..I[49]`; `I[0]..I[16] = ADVANCE`, `I[17]..I[32] = DECLINE`, and
`I[33]..I[49] = UNCHANGED`; `I[0]..I[24]` map to `ALPHA` and the rest to
`BETA`; every effective interval is `[D - 1 day, D + 1 day]`; every required
source/proof clock is `K - 1 microsecond`; lineage is complete and checked
through `K`; and the owner proof and all bindings pass. `B0` emits `OBSERVED`
report `R0`, null reasons, `ALPHA = (25, 17, 8, 0)`, and
`BETA = (25, 0, 8, 17)`.

First, for each family below, mutate only its named external future store while
replaying the unchanged canonical `B0` bytes. No field is rebuilt or rehashed.
Every such replay must return the exact byte-identical `R0`; the fail-fast store
sentinel must record zero reads.

Then construct these separately sealed, canonical changed inputs from `B0`.
Every named containing identity is rehashed; every unmentioned field remains
byte-identical:

1. **Membership correction.** Replace `I[49]` with a new strict-sorting valid
   `I[50]` in the upstream membership-derived input and handoff, retaining
   `UNCHANGED` and `BETA`, and set the correction's trusted upstream
   publication/response/retrieval/retention instants to `K`. Remove `I[49]`'s
   assignment candidate and create `I[50]`'s `BETA` assignment with interval
   `[D - 1 day, D + 1 day]`: rebuild the assignment source-object bytes and
   receipt digest, exact row selector, selected value, assignment provenance/
   object/revision/supersession trace and its source selectors, complete lineage
   proof checked through `K`, and the exact replacement coverage-manifest entry.
   Rebuild the bound Market Regime input/report identity, handoff,
   requested-ISIN tuple, classification attempt, reconstructed facts, manifest,
   bundle/input, and report identities. The changed input emits `OBSERVED`, null
   reasons, and the same two count rows as `R0`. Its source/receipt/selector/
   revision/manifest/input/report bytes and every containing identity differ
   from `B0`/`R0`; identity equality is required only within each input, never
   across them.
2. **Classification-release revision after cutoff.** Replace the release source
   bytes and release/revision identities; set all four required publication,
   response-completion, retrieval, and retention clocks to
   `K + 1 microsecond`; update every assignment's bound release claim and its
   source selectors; and select the new post-cutoff revision. Rebuild a complete
   licence-proof source object, receipt digest, exact selector/selected values,
   provenance/object/revision/supersession trace and source selectors, plus the
   complete lineage nodes/edges checked through `K`; bind
   `LicenceProofV1.classification_release_identity_sha256` to the new release,
   retain valid permissions and an interval covering `D`, and place its four
   required clocks at `K + 1 microsecond`. Recompute the licence-proof identity;
   reverify the sealed licence-policy manifest/identity (byte-identical because
   its policy bytes did not change); and rebuild the classification attempt,
   manifest, bundle/input, and report identities. The canonical input emits
   `INSUFFICIENT_EVIDENCE`, `sectors = null`, primary
   `SECTOR_CLASSIFICATION_LATE`, and additional reasons exactly
   `[SECTOR_CLASSIFICATION_REVISION_UNPROVEN]`, with no
   `LICENCE_UNRESOLVED`. Source, release, licence-proof, revision, manifest,
   bundle/input, and report identities differ from `B0`/`R0`.
3. **Assignment-mapping revision after cutoff.** Change only `I[49]`'s selected
   label from `BETA` to `ALPHA` in new assignment source bytes, set that
   revision's four required clocks to `K + 1 microsecond`, add its supersession
   edge, select it, and rebuild its selector/provenance, lineage, manifest,
   bundle, and report identities. The canonical input emits
   `INSUFFICIENT_EVIDENCE`, `sectors = null`, primary
   `SECTOR_CLASSIFICATION_LATE`, and additional reasons exactly
   `[SECTOR_CLASSIFICATION_REVISION_UNPROVEN]`. Assignment, object, revision,
   manifest, bundle/input, and report identities differ from `B0`/`R0`.
4. **Schedule correction at the upstream boundary.** Move the authoritative
   decision close and derived next-open cutoff forward by one minute, defining
   `K' = K + 1 minute`; timestamp all correction evidence at
   `K - 1 microsecond`; set revision `lineage.checked_through = K'`; and rebuild
   the complete lineage proof, its source bytes/selectors/provenance, the
   containing classification attempt, Market Regime input/observed report,
   handoff endpoints/identities, sector bundle/input, and report identities.
   The fully rebound input emits `OBSERVED`, null reasons, the same count rows,
   new copied endpoints, and new lineage/upstream/handoff/bundle/report
   identities. A paired mismatch fixture instead rehashes only the changed
   handoff endpoint while retaining the old observed report; it emits
   `INSUFFICIENT_EVIDENCE`,
   `sectors = null`, primary `MEMBER_DIRECTION_HANDOFF_INVALID`, and no
   additional reason.
5. **Corporate-action completeness correction at the upstream boundary.**
   Timestamp a separately sealed upstream status/negative-completeness/lineage/
   identity-continuity correction at `K`, change `I[16]` from `ADVANCE` to
   `UNCHANGED` in the resulting upstream comparable-price decision, and rebuild
   Market Regime totals and report, handoff member/totals, and all downstream
   identities. The fully rebound input
   emits `OBSERVED`, null reasons, `ALPHA = (25, 16, 8, 1)`, and unchanged
   `BETA`. A paired fixture rehashes only the changed handoff member/direction
   while retaining the old report totals; it emits `INSUFFICIENT_EVIDENCE`,
   `sectors = null`, primary `MEMBER_DIRECTION_HANDOFF_INVALID`, and no
   additional reason.

Schedule and corporate-action raw evidence is never a Sector Participation
input. Those paired cases prove that downstream either accepts a completely
newly bound observed report/handoff or rejects the exact binding mismatch; it
never folds a correction, reads a close, classifies an action, derives a
direction, or retroactively changes `B0`/`R0`.

### Audience privacy and Layer A redaction

Enumerate owner proofs at issue/expiry boundaries and every invalid class:
public, anonymous, unauthenticated, wrong owner, wrong purpose, wrong verifier,
wrong privacy policy, mismatched request, reused nonce, future-issued, expired,
identity mismatch, and caller boolean in place of attestation. Use a trusted
injected evaluation instant; wall-clock reads are forbidden.

Exercise all-singleton, one-singleton-plus-49, multiple-singleton, no-singleton,
and one-sector shapes. Invalid proof always yields
`PRIVACY_POLICY_UNSATISFIED` and null sectors. No row may be selectively
suppressed. Layer A scans only report and reducer-runtime surfaces: canonical
report bytes, returned objects, string/debug representations, equality diffs,
exceptions, logs, telemetry, and snapshots.

Every admitted canary is schema-valid and channel-specific: distinct valid
synthetic ISINs; bounded valid symbol/company/source/selector/path/licence-text
markers where that channel can occur in immutable source bytes; valid SHA-256
patterns for identity fields; valid `UtcInstant` boundary patterns for time
fields; and a distinguishable repeating sequence of the three valid direction
enums across handoff members. Singleton literals stay valid; foreign enum or
constrained-field values are rejection fixtures, never canaries smuggled into
an admitted object. Credentials, secrets, and any other channel outside a
closed admitted schema live only in fail-fast harness sentinels.

A raw-close canary exists only behind a forbidden upstream accessor in that
out-of-boundary harness. It is never inserted into a handoff, bundle, or other
admitted Sector Participation input. Swapping any harness-only canary must leave
the complete canonical report bytes unchanged and record zero accessor calls.
The scanner rejects any raw canary occurrence on the named Layer A surfaces; a
deliberate harness leak is its positive control. Authorized sector labels and
opaque bounded identity digests are separately allowlisted without allowing
their underlying sensitive canaries.

### Canonical identities and zero I/O

Golden vectors cover request, both upstream branches, handoff, every candidate
schema, attempt, receipts/selectors, all verified facts, audience proof, trusted
manifests, evidence bundle, observed report, and every insufficient primary
reason. An independent stdlib encoder recomputes each projection and proves
that it excludes only its own identity field. Canonical bytes require exactly
one trailing LF: a missing LF or any extra LF rejects, while that one required LF
does not. Unknown fields, duplicate object keys, noncanonical integers, or JSON
whitespace outside strings reject. JSON arrays are the valid wire encoding of
contract tuples; tests reject a wrong array length, noncanonical array order, or
duplicate array member exactly where the closed schema prohibits it, not arrays
as a type. Verified semantic strings must be NFC; exact `CandidateText` is
preserved without normalization and a semantically invalid candidate string
yields the frozen corrupt reason.

Layer A identity sensitivity partitions fields before generating a mutation:

- **independently mutable admitted fields:** mutate one schema-valid canonical
  field while preserving every invariant, then require its direct identity and
  every transitively containing identity to change;
- **invariant-coupled groups:** mutate the underlying canonical fact and rebuild
  the entire legal group before comparison—for example report/handoff
  endpoints and totals, the requested-ISIN/handoff/assignment/manifest cohort,
  source/release/object/revision/selector chains, or audience/request/policy
  bindings—then require all covered identities to recompute and the exact
  admitted domain outcome to remain well formed; and
- **singleton literals and foreign invalid values:** attempt the foreign value
  only as an invalid fixture and require structural rejection before any
  identity-sensitivity comparison.

Mutating an excluded self-identity claim cannot change its recomputed projection
and instead produces an identity mismatch or structural rejection.
Canonical-invalid byte mutations exercise rejection separately. Coordinated
rehashing remains unable to replace a sealed source, policy, clock, audience, or
reviewed-build root.

Run every valid and invalid Layer A reducer fixture with network, socket,
filesystem, database, environment, wall clock, sleep, randomness, credentials,
logging, telemetry, subprocess, and storage entry points replaced by fail-fast
sentinels. Required calls are exactly zero.

## Layer B — future one-bundle readiness without count disclosure

Layer B is not a second conformance suite and Layer A success is not a readiness
predicate by itself. The two layers have disjoint result schemas, fixtures, and
measurements. No Layer A synthetic sector label or count may enter a readiness
fixture, and no `READY`/`BLOCKED` value may be interpreted as a sector label,
usefulness score, prediction, or performance result.

Layer B starts blocked. It may run only after the separate authorization and
implementation/review steps in the chronology below. Its closed types are:

```text
ReadinessRequirementV1 = Literal[
  "R01_AUTHORIZED_REVIEWED_IMPLEMENTATION",
  "R02_OBSERVED_MARKET_REGIME_REPORT",
  "R03_PRIVATE_MARKET_REGIME_HANDOFF",
  "R04_OFFICIAL_SECTOR_TAXONOMY_RELEASE",
  "R05_EXACT_50_SECTOR_ASSIGNMENTS",
  "R06_IMMUTABLE_SOURCE_OBJECTS_AND_SELECTOR_TRACES",
  "R07_TRUSTED_EVIDENCE_CLOCKS",
  "R08_COMPLETE_REVISION_LINEAGE",
  "R09_COMPLETE_COVERAGE_MANIFEST",
  "R10_APPROVED_RETAINED_USE_LICENCE",
  "R11_SEALED_STUDY_IDENTITIES",
  "R12_OWNER_PRIVATE_AUDIENCE_PROOF",
]

ReadinessBlockerReasonV1 = Literal[
  "IMPLEMENTATION_AUTHORIZATION_MISSING",
  "SOURCE_PRIVATE_DELIVERY_AUTHORIZATION_MISSING",
  "REVIEWED_IMPLEMENTATION_BUILD_MISSING",
  "OBSERVED_MARKET_REGIME_REPORT_MISSING",
  "PRIVATE_MARKET_REGIME_HANDOFF_MISSING",
  "OFFICIAL_SECTOR_TAXONOMY_RELEASE_UNPROVEN",
  "EXACT_50_SECTOR_ASSIGNMENTS_UNPROVEN",
  "SOURCE_OBJECT_OR_SELECTOR_TRACE_INCOMPLETE",
  "EVIDENCE_CLOCKS_UNPROVEN",
  "REVISION_LINEAGE_INCOMPLETE",
  "COVERAGE_MANIFEST_INCOMPLETE",
  "RETAINED_USE_LICENCE_UNAPPROVED",
  "SEALED_STUDY_IDENTITIES_INCOMPLETE",
  "OWNER_PRIVATE_AUDIENCE_PROOF_INVALID",
]

SectorParticipationReadinessV1 {
  study_identity_sha256: Sha256 | null
  evidence_bundle_identity_sha256: Sha256 | null
  readiness_state: Literal["READY", "BLOCKED"]
  covered_requirement_ids: tuple[ReadinessRequirementV1, 0..12]
  blocker_reasons: tuple[ReadinessBlockerReasonV1, 0..14]
  readiness_identity_sha256: Sha256
}
```

`ReadinessRequirementV1` is closed to exactly the twelve IDs above; declaration
order is its only canonical order. `ReadinessBlockerReasonV1` is a separate
readiness-only type and never reuses `SectorParticipationReasonV1`, whose values
explain a domain report rather than authorization, review, or pre-reduction
readiness. The exhaustive requirement-to-blocker map is:

| Requirement | Required predicate; exhaustive mapped blocker reason(s) |
|---|---|
| `R01_AUTHORIZED_REVIEWED_IMPLEMENTATION` | separately authenticated implementation authorization, source/private-delivery authorization, and reviewed implementation build are all present; respectively `IMPLEMENTATION_AUTHORIZATION_MISSING`, `SOURCE_PRIVATE_DELIVERY_AUTHORIZATION_MISSING`, `REVIEWED_IMPLEMENTATION_BUILD_MISSING` |
| `R02_OBSERVED_MARKET_REGIME_REPORT` | one canonical observed `nifty50-market-regime@v1` report; `OBSERVED_MARKET_REGIME_REPORT_MISSING` |
| `R03_PRIVATE_MARKET_REGIME_HANDOFF` | its same-input reviewed 50-row private handoff; `PRIVATE_MARKET_REGIME_HANDOFF_MISSING` |
| `R04_OFFICIAL_SECTOR_TAXONOMY_RELEASE` | official release proving the exact Sector tier; `OFFICIAL_SECTOR_TAXONOMY_RELEASE_UNPROVEN` |
| `R05_EXACT_50_SECTOR_ASSIGNMENTS` | exact official assignments for all 50 decision-session ISINs; `EXACT_50_SECTOR_ASSIGNMENTS_UNPROVEN` |
| `R06_IMMUTABLE_SOURCE_OBJECTS_AND_SELECTOR_TRACES` | immutable source objects and complete selector traces for every selected value; `SOURCE_OBJECT_OR_SELECTOR_TRACE_INCOMPLETE` |
| `R07_TRUSTED_EVIDENCE_CLOCKS` | trusted publication/response/retrieval/retention clocks by cutoff; `EVIDENCE_CLOCKS_UNPROVEN` |
| `R08_COMPLETE_REVISION_LINEAGE` | complete acyclic lineage checked exactly through cutoff; `REVISION_LINEAGE_INCOMPLETE` |
| `R09_COMPLETE_COVERAGE_MANIFEST` | exact complete acquisition/coverage manifest; `COVERAGE_MANIFEST_INCOMPLETE` |
| `R10_APPROVED_RETAINED_USE_LICENCE` | approved retention and owner-private aggregate-use licence proof; `RETAINED_USE_LICENCE_UNAPPROVED` |
| `R11_SEALED_STUDY_IDENTITIES` | source, validation, semantic, privacy, licence, selector, audience, code, evidence, and reviewed-build identities are sealed and recomputed; `SEALED_STUDY_IDENTITIES_INCOMPLETE` |
| `R12_OWNER_PRIVATE_AUDIENCE_PROOF` | one valid authenticated nonanonymous owner-private proof; `OWNER_PRIVATE_AUDIENCE_PROOF_INVALID` |

Coverage and nullability are exact. A requirement appears once in
`covered_requirement_ids` if and only if every predicate in its row passes.
The tuple contains no duplicate and is the declaration-ordered subsequence of
the twelve IDs. `blocker_reasons` contains every failing mapped predicate, no
other value, no duplicate, and follows its declaration order. Thus every
uncovered requirement has at least one mapped blocker and no covered requirement
has one. Authorization and review are admitted only from separately
authenticated, identity-bound artifacts; caller booleans or matching-looking
text cannot cover `R01`.

`READY` requires non-null study and evidence-bundle identities, all twelve
requirement IDs in exact declaration order, and the empty blocker tuple.
`BLOCKED` requires a proper ordered subset and one or more blocker reasons; its
two identity fields are either both null or both non-null. Both are null exactly
when canonical bundle bytes are absent or structurally inadmissible. Otherwise
both equal Plan 14's recomputed `expected_bundle_identity`: the one-bundle study
has no second digest or caller-selected study name. A null identity pair
necessarily leaves `R11` uncovered and emits
`SEALED_STUDY_IDENTITIES_INCOMPLETE`. These are the only legal
state/nullability/coverage shapes.

The readiness identity is content-derived, never supplied on trust.
`CanonicalSectorParticipationReadinessIdentityProjectionV1(result)` contains
every `SectorParticipationReadinessV1` field except only
`readiness_identity_sha256`, including the null or recomputed identity pair,
state, and the two canonical tuples unchanged:

```text
expected_readiness_identity =
  SHA256(canonical_json_lf(
    CanonicalSectorParticipationReadinessIdentityProjectionV1(result)
  ))
result.readiness_identity_sha256 == expected_readiness_identity
```

The gate recomputes that equality before recording or returning the result. It
contains no sector label, count, member direction, member identity, Market
Regime count, or preview. `READY` means only all prerequisites can be
mechanically admitted; it does not assert a result is useful, surprising,
tradable, or already reduced. Any missing item is `BLOCKED`; no synthetic
substitute, current-map repair, partial denominator, inferred lineage, or count
inspection is allowed. Original and revised candidates remain separate immutable
failures or studies.

### Layer B identity sensitivity and count-free redaction

Layer B uses only readiness prerequisites and `SectorParticipationReadinessV1`
inputs/outputs; it imports no Layer A report fixture, sector label, count, member
direction, or member identity. Identity sensitivity is restricted to fields
actually covered by the closed readiness projection:
`study_identity_sha256`, `evidence_bundle_identity_sha256`, `readiness_state`,
ordered `covered_requirement_ids`, and ordered `blocker_reasons`. There is no
other projected V1 field.

- A schema-valid, invariant-preserving mutation of an independently mutable
  projected field changes canonical readiness bytes and
  `readiness_identity_sha256`.
- An input-driven coupled mutation rebuilds the complete legal projected group,
  especially `readiness_state`/coverage/blockers and the paired study/evidence-
  bundle identities; any changed projected field changes readiness bytes and
  identity.
- An admitted prerequisite or authorization-proof mutation that leaves all five
  projected fields identical must produce byte-identical readiness output and
  the identical readiness identity; its admission and own proof identity are
  tested separately.
- A foreign singleton state, requirement, or blocker literal, invalid tuple
  order, duplicate, or illegal nullability shape rejects before identity
  comparison.

The excluded `readiness_identity_sha256` self-field and coordinated sealed-root
rehash receive the same mismatch/rejection checks as Layer A. Layer B redaction
uses schema-valid opaque digest and `UtcInstant` canaries only in readiness
prerequisite artifacts. It scans readiness canonical bytes, returned objects,
string/debug representations, equality diffs, exceptions, logs, telemetry, and
snapshots for any sector label, count, member direction/identity, raw source
value, credential, secret, or free-form diagnostic. A harness-only deliberate
readiness leak is the positive control; changing that out-of-boundary sentinel
must not change the canonical readiness bytes or `READY`/`BLOCKED` outcome.

## One feasible future chronology and sealing

The chronology is strict and deliberately avoids the prior circular plan:

1. **Separate authorization.** Obtain explicit owner authorization for the
   implementation slice and separate authority for source/private-delivery work.
2. **Source, licence, acquisition, retention.** Approve the source binding,
   licence and retained-use scope, bounded acquisition manifest, capture
   authority, credentials if unavoidable, budget, and storage; then retain raw
   candidate bytes and trusted receipts without computing sector counts.
3. **Strict TDD Layer A implementation/review.** First implement/review the
   prerequisite Market Regime observed-only handoff; then write failing Layer A
   tests and implement the pure Sector Participation schemas, admission,
   identities, privacy suppression, and reducer. No same-input handoff is
   claimed before this step.
4. **Seal code, evidence, and policies.** After independent review, seal the
   reviewed build and the exact source, validation, semantic, privacy, licence,
   selector, audience, evidence, manifest, request/date/cohort, and cutoff bytes.
5. **Readiness without count disclosure.** Run Layer B only over those sealed
   identities. It emits `READY` or `BLOCKED`, never sector counts/directions.
6. **Reduce one ready bundle.** If and only if readiness is `READY`, reduce that
   exact one bundle once and deliver only through the owner-private boundary.

Failure at any step stops. No later external revision rewrites an older study;
it requires a separately sealed input and identity. There is no same-input
handoff before implementation, no readiness run before code review/sealing, no
result-driven policy edit, and no tuning loop.

## Measurements and acceptance thresholds

Layer A records fixture identity, seed, structural/domain class, expected/actual
state and endpoints, candidate/reason mapping, selector equality, identity
equality, row/global equations, reason order, redaction scan, and side-effect
count. Acceptance requires zero disagreements, zero partial reports, zero
look-ahead/current-map admissions, zero privacy leaks, zero unauthorized
aggregate deliveries, zero I/O calls, and byte-exact golden/replay agreement.

Layer B records only readiness requirement coverage, blocker reasons, and opaque
policy/receipt/bundle identities. It records no sector count or member direction.
Any Layer A disagreement or missing Layer B prerequisite is a hard stop, never a
warning or confidence discount.

## Stop conditions and future handoff

Stop Layer A on the first oracle, structural/domain distinction, selector,
identity, equation, nullability, reason-order, replay, redaction, or zero-I/O
failure. Preserve the seed and canonical bytes. Stop Layer B before source
contact if its separate authority is missing, and stop before reduction for any
`BLOCKED` readiness result.

Stop on current-map backfill, tier substitution, incomplete revision graph,
licence ambiguity, clock invention, partial count, public/singleton leakage,
recomputation of upstream schedule/corporate-action facts, changed old replay,
or any inspection/tuning based on sector counts before sealing. Repairing code
requires a new reviewed build identity; changing evidence or policy requires
new recomputed study, evidence-bundle, and readiness identities.

Today's artifact is preregistration, not execution. Future work inherits no
provider, credential, data, acquisition, retention, runtime, or implementation
permission from it.
