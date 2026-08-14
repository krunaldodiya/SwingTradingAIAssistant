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
   identities. A paired mismatch fixture retains the old observed Market Regime
   report bytes, identity, fields, and totals, but changes the handoff endpoint
   and then transitively rebuilds the handoff digest; observed-envelope handoff
   bytes/identity claim; complete evidence-bundle canonical bytes and
   `input_identity_sha256`; reducer `evidence_bundle_identity_sha256`;
   reconstructed classification facts' `input_identity_sha256` when present;
   and the eventual insufficient report identity. The old classification
   candidate/attempt content remains byte-identical; only its containing
   evidence-bundle identity and reconstructed-facts input binding change. All
   bytes, schemas, and claimed digests are therefore canonical and aligned
   before the retained report/handoff endpoint mismatch is evaluated. It emits
   `INSUFFICIENT_EVIDENCE`, `sectors = null`,
   primary `MEMBER_DIRECTION_HANDOFF_INVALID`, and no additional reason.
5. **Corporate-action completeness correction at the upstream boundary.**
   Timestamp a separately sealed upstream status/negative-completeness/lineage/
   identity-continuity correction at `K`, change `I[16]` from `ADVANCE` to
   `UNCHANGED` in the resulting upstream comparable-price decision, and rebuild
   Market Regime totals and report, handoff member/totals, and all downstream
   identities. The fully rebound input
   emits `OBSERVED`, null reasons, `ALPHA = (25, 16, 8, 1)`, and unchanged
   `BETA`. A paired mismatch fixture retains the old observed report bytes,
   identity, fields, and totals, changes only the canonical handoff member
   direction for `I[16]`, and transitively rebuilds the handoff digest;
   observed-envelope handoff bytes/identity claim; evidence-bundle canonical
   bytes and `input_identity_sha256`; reducer
   `evidence_bundle_identity_sha256`; reconstructed classification facts'
   `input_identity_sha256` when present; and the eventual insufficient report
   identity. The old classification candidate/attempt content remains
   byte-identical; only its containing evidence-bundle identity and
   reconstructed-facts input binding change. With every
   containing claim canonical and rehashed, only the retained old report totals
   semantically disagree. It emits `INSUFFICIENT_EVIDENCE`, `sectors = null`,
   primary `MEMBER_DIRECTION_HANDOFF_INVALID`, and no additional reason.

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
measurements. Layer B privately verifies the sealed prerequisite bundle
described below; it never accepts a Layer A pass/fail value or synthetic report
as readiness evidence. No `READY`/`BLOCKED` value may be interpreted as a
sector label, usefulness score, prediction, or performance result.

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

### Deployment-root attestation, verified context, and raw candidates

The production composition is two-stage and has no self-pinning cycle:

```text
outer_candidate = parse_canonical_outer_candidate(candidate_input)
bundle_self_identity = recompute_untrusted_bundle_self_identity(outer_candidate)
reviewed_build_identity = recompute_expected_reviewed_build_identity(
  internal_expected_reviewed_build,
)
provisional_context = verify_deployment_attestation(
  deployment_attestation_bytes,
  embedded_deployment_root,
  reviewed_build_identity,
)
T = verify_candidate_clock(outer_candidate, provisional_context)
verified_internal_context = finalize_context(
  provisional_context,
  internal_expected_reviewed_build,
  T,
)
result = evaluate_readiness(outer_candidate, verified_internal_context)
```

Only `candidate_input` crosses the request API. Deployment tooling supplies the
attestation through an internal immutable channel; neither it nor the root key
is a request field. The evaluator runs only after internal attestation
verification has produced `verified_internal_context`.

```text
ReadinessSignatureProfileV1 =
  Literal["ED25519_RFC8032_STRICT_CANONICAL_JSON_LF_V1"]

ReadinessSignedRecordKindV1 = Literal[
  "READINESS_DEPLOYMENT_ATTESTATION",
  "IMPLEMENTATION_AUTHORIZATION",
  "SOURCE_LICENCE_RETENTION_OWNER_PRIVATE_DELIVERY_AUTHORIZATION",
  "TRUSTED_EVALUATION_INSTANT",
  "OWNER_PRIVATE_NONCE_ADMISSION_DECISION",
]

ReadinessVerificationKeyV1 {
  record_kind: ReadinessSignedRecordKindV1
  signature_profile: ReadinessSignatureProfileV1
  public_key_bytes_hex: HexBytes[32..32]
  key_identity_sha256: Sha256
}

SectorParticipationReadinessDeploymentRootV1 {
  record_kind: Literal["READINESS_DEPLOYMENT_ATTESTATION"]
  signature_profile: ReadinessSignatureProfileV1
  public_key_bytes_hex: HexBytes[32..32]
  key_identity_sha256: Sha256
}

ImplementationAuthorizationPayloadV1 {
  record_kind: Literal["IMPLEMENTATION_AUTHORIZATION"]
  authorization_scope:
    Literal["NIFTY50_SECTOR_PARTICIPATION_V1_IMPLEMENTATION"]
  decision: Literal["AUTHORIZED", "REJECTED"]
  issued_at: UtcInstant
  expires_at: UtcInstant
  code_identity_sha256: Sha256
  validation_policy_identity_sha256: Sha256
  payload_content_identity_sha256: Sha256
}

SourcePrivateDeliveryAuthorizationPayloadV1 {
  record_kind:
    Literal["SOURCE_LICENCE_RETENTION_OWNER_PRIVATE_DELIVERY_AUTHORIZATION"]
  authorization_scope:
    Literal["NIFTY50_SECTOR_PARTICIPATION_V1_SOURCE_LICENCE_RETENTION_OWNER_PRIVATE_DELIVERY"]
  decision: Literal["AUTHORIZED", "REJECTED"]
  issued_at: UtcInstant
  expires_at: UtcInstant
  source_policy_identity_sha256: Sha256
  licence_policy_identity_sha256: Sha256
  privacy_policy_identity_sha256: Sha256
  payload_content_identity_sha256: Sha256
}

TrustedEvaluationInstantPayloadV1 {
  record_kind: Literal["TRUSTED_EVALUATION_INSTANT"]
  evaluated_at: UtcInstant
  payload_content_identity_sha256: Sha256
}

OwnerPrivateNonceAdmissionPayloadV1 {
  record_kind: Literal["OWNER_PRIVATE_NONCE_ADMISSION_DECISION"]
  decision: Literal["FRESH_ACCEPTED", "REUSED_REJECTED"]
  nonce_identity_sha256: Sha256
  audience_proof_identity_sha256: Sha256
  request_identity_sha256: Sha256
  evidence_bundle_identity_sha256: Sha256
  evaluated_at: UtcInstant
  payload_content_identity_sha256: Sha256
}

ReadinessSignedRecordV1 {
  record_kind: ReadinessSignedRecordKindV1
  signature_profile: ReadinessSignatureProfileV1
  signer_key_identity_sha256: Sha256
  payload_canonical_bytes_hex: HexBytes[1..65536]
  payload_content_identity_sha256: Sha256
  signature_bytes_hex: HexBytes[64..64]
  signed_record_identity_sha256: Sha256
}

SectorParticipationReadinessTrustContextV1 {
  expected_reviewed_build: ExpectedReviewedBuildV1
  signature_profile: ReadinessSignatureProfileV1
  implementation_authorization_key: ReadinessVerificationKeyV1
  source_private_delivery_authorization_key: ReadinessVerificationKeyV1
  evaluation_clock_key: ReadinessVerificationKeyV1
  nonce_admission_key: ReadinessVerificationKeyV1
  trust_context_identity_sha256: Sha256
}

ReadinessDeploymentAttestationPayloadV1 {
  record_kind: Literal["READINESS_DEPLOYMENT_ATTESTATION"]
  deployment_scope:
    Literal["NIFTY50_SECTOR_PARTICIPATION_V1_READINESS_GATE"]
  decision: Literal["APPROVED", "REVOKED"]
  issued_at: UtcInstant
  expires_at: UtcInstant
  expected_reviewed_build_identity_sha256: Sha256
  signature_profile: ReadinessSignatureProfileV1
  implementation_authorization_key: ReadinessVerificationKeyV1
  source_private_delivery_authorization_key: ReadinessVerificationKeyV1
  evaluation_clock_key: ReadinessVerificationKeyV1
  nonce_admission_key: ReadinessVerificationKeyV1
  trust_context_identity_sha256: Sha256
  payload_content_identity_sha256: Sha256
}

SectorParticipationReadinessDeploymentAttestationV1 {
  record_kind: Literal["READINESS_DEPLOYMENT_ATTESTATION"]
  signature_profile: ReadinessSignatureProfileV1
  signer_key_identity_sha256: Sha256
  payload_canonical_bytes_hex: HexBytes[1..4096]
  payload_content_identity_sha256: Sha256
  signature_bytes_hex: HexBytes[64..64]
  attestation_identity_sha256: Sha256
}

SectorParticipationReadinessCandidateInputV1 {
  evidence_bundle_candidate_bytes_hex: HexBytes[0..2097152] | null
  evidence_bundle_identity_claim_text: CandidateText | null
  implementation_authorization_record_bytes_hex: HexBytes[0..65536] | null
  source_private_delivery_authorization_record_bytes_hex:
    HexBytes[0..65536] | null
  evaluation_clock_record_bytes_hex: HexBytes[0..65536] | null
  nonce_admission_record_bytes_hex: HexBytes[0..65536] | null
  candidate_input_identity_sha256: Sha256
}
```

Every schema above is closed. Key, typed-payload, signed-record, trust-context,
deployment-payload, deployment-attestation, and candidate-input identities are
SHA-256 of their canonical projection excluding only their own identity field;
all projections use canonical JSON plus one LF.
`CanonicalExpectedReviewedBuildIdentityProjectionV1(build)` contains every
`ExpectedReviewedBuildV1` field; that Plan 14 type has no outer self-identity
field, so none is omitted. Its canonical hash is
`expected_reviewed_build_identity_sha256`.

The trust-context projection contains the full internally supplied immutable
`ExpectedReviewedBuildV1`, frozen profile, and four typed verification keys.
The deployment payload contains only the derived reviewed-build identity, those
four keys/profile, recomputed trust-context identity, bounded scope/decision/
window metadata, and its content identity; it never duplicates the build.
Each of the four canonical key objects is bounded above by 512 bytes, and each
of the nine remaining fixed scalar fields including JSON key/separator overhead
is bounded above by 128 bytes; 256 bytes cover outer braces/separators. Thus the
payload upper bound is `4 × 512 + 9 × 128 + 256 = 3,456` bytes, and the frozen
`HexBytes[1..4096]` payload cap leaves 640 bytes of headroom without admitting a
second build-sized object.

One fixed `SectorParticipationReadinessDeploymentRootV1` public key and profile
is generated independently before the reviewed build, embedded in the gate, and
covered by the resulting code identity. Its bytes contain no build, context, or
attestation digest and are independent of the final build identity.

After build sealing/review, internal composition supplies the full canonical
`ExpectedReviewedBuildV1` through a separate immutable non-request channel and
recomputes the all-fields build identity above. The external authorized release
signer signs only the compact payload containing that digest and the future
context keys. The gate verifies the attestation under the embedded root,
requires exact root signer-key identity/profile/kind, scope, and `APPROVED`
decision, and requires the signed build digest to equal the independently
recomputed internal build identity. It combines the separate full build with
the signed keys/profile, recomputes the trust-context projection, and requires
equality to the signed context identity. The immutable context retains the full
build by reference; the attestation neither copies nor embeds it. No final-build-
dependent hash is embedded in the code that computes that same build.

This produces only a provisional context. After it authenticates candidate
clock instant `T`, finalization additionally requires
`issued_at <= T < expires_at`. The attestation, full build, and context are
internal deployment artifacts, never caller replacements.

`ED25519_RFC8032_STRICT_CANONICAL_JSON_LF_V1` signs the exact full canonical
typed payload bytes, including their recomputed content-identity field. Strict
verification interprets a signature as canonical 32-byte compressed Edwards
point `R` followed by little-endian scalar `S`; requires `S < L`; requires both
the 32-byte public key encoding and `R` to decode to valid curve points and
re-encode byte-identically; rejects noncanonical encodings, the identity,
small-order or torsion public keys or `R`, malformed lengths, and any failed
RFC 8032 equation `[S]B = R + [SHA-512(R || A || M) mod L]A`. No permissive
ZIP-215-style or scalar-reduction acceptance is allowed.

An independently authored crypto oracle shares no production verification
helper. Golden fixtures cover valid signatures plus message, kind, profile,
public-key, signature, `R`, and `S` bit flips; wrong key/message; `S + L`
malleability; noncanonical point/scalar encodings; identity, small-order, and
torsion points; malformed lengths; and failed equations. Fixture private keys
are never runtime or source-controlled. Isolated test setup generates any
needed deterministic ephemeral private keys from harness material held outside
source, then retains only public vectors, canonical messages, and signatures.

A missing, malformed, revoked, wrong-scope, wrong-profile, wrong-root-key,
bad-signature, wrong-build-digest, or context-projection-mismatched deployment
attestation cannot construct a provisional context. A correctly signed
attestation that is future-issued or expired at authenticated `T`, or a missing/
malformed/noncanonical/bad-signature/wrong-key/wrong-profile/wrong-kind clock
record, cannot finalize that context.

For every such deployment-or-clock trust failure, the pure internal entrypoint
first parses the outer candidate and independently canonicalizes/recomputes the
bundle's Plan 14 self-identity without using a readiness predicate or context
value. It evaluates no readiness predicate. Canonical self-consistent bundle
bytes/claim yield `BLOCKED` with both identity fields equal that recomputed
bundle identity, every requirement uncovered, and the complete fourteen-reason
blocker tuple in declaration order. An absent, malformed, noncanonical, or self-
identity/claim-mismatched bundle yields the same result with a null pair. Either
shape necessarily includes `REVIEWED_IMPLEMENTATION_BUILD_MISSING` and
`SEALED_STUDY_IDENTITIES_INCOMPLETE`. A malformed outer candidate produces no
readiness object. Caller material never becomes alternate context.

The candidate input is a closed envelope of untrusted bounded raw bytes. Its own
unknown/missing field, wrong outer type, duplicate key, noncanonical outer
serialization, bad outer identity, or bound violation is structural rejection
and produces no readiness object. By contrast, each null, empty, malformed,
noncanonical, wrong-type, bad-self-hash, bad-signature, wrong-key, wrong-profile,
or wrong-kind inner candidate is an admitted failed prerequisite and produces
the mapped readiness blockers. No inner candidate failure becomes outer
structural rejection.

Bundle admission first parses the raw bundle candidate and recomputes Plan 14's
one bundle projection. Null, malformed, noncanonical, or identity-mismatched
bundle bytes produce the reachable null study/evidence-bundle identity pair,
leave `R11` uncovered, and add `SEALED_STUDY_IDENTITIES_INCOMPLETE`, plus every
other mapped blocker whose prerequisite cannot be established. A valid bundle
requires its recomputed identity to equal both its own `input_identity_sha256`
and the parsed candidate claim. Only then may that identity occupy the two
allowlisted readiness fields.

The evaluation instant exists only if the raw clock record parses as
`ReadinessSignedRecordV1`, verifies under the provisional context's pinned clock
key/profile, and its canonical payload parses as
`TrustedEvaluationInstantPayloadV1` with matching kind/content identities.
There is no fallback instant. A null, empty, malformed, noncanonical,
bad-signature, wrong-key, wrong-profile, or wrong-kind clock record routes
directly through the full deployment-trust failure branch above: no context is
finalized and no readiness predicate, including `R01` or `R12`, is partially
evaluated. No caller field, ambient clock, replay time, or filesystem/network
timestamp substitutes for authenticated `T`.

The implementation authorization passes exactly when its raw signed record and
typed payload authenticate under the pinned implementation key/profile, its
decision is `AUTHORIZED`, `issued_at <= T < expires_at`, and its code and
validation-policy identities equal the sealed reviewed build. Any failure adds
`IMPLEMENTATION_AUTHORIZATION_MISSING`. The source authorization passes exactly
when it authenticates under the pinned source key/profile, has decision
`AUTHORIZED`, satisfies the same time window, and its source/licence/privacy
policy identities equal the sealed build and valid bundle. Any failure adds
`SOURCE_PRIVATE_DELIVERY_AUTHORIZATION_MISSING`. A missing or invalid sealed-
build/bundle binding adds `REVIEWED_IMPLEMENTATION_BUILD_MISSING`. `R01` is
covered only when all three predicates pass; blockers occur once in frozen
order.

For `R12`, the gate validates the parsed bundle's complete
`OwnerPrivateAudienceProofV1` at authenticated `T`. The raw nonce record must
authenticate under the pinned nonce key/profile and parse as the closed nonce
payload; `decision` must be `FRESH_ACCEPTED`; its `evaluated_at` must equal `T`;
and nonce, audience-proof, request, and bundle identities must equal the exact
parsed proof/input values. Any failure, including a valid signed
`REUSED_REJECTED`, leaves `R12` uncovered and adds only
`OWNER_PRIVATE_AUDIENCE_PROOF_INVALID` for that requirement. Fresh acceptance
is the authenticated immutable result of one prior admission; a later reuse is
a separately signed candidate. The evaluator accepts no caller boolean and
performs no nonce-store lookup.

Layer B candidate fixtures independently cover each raw inner value as null,
empty, malformed UTF-8/JSON, noncanonical, bad self-hash, bad signature, wrong
pinned key, wrong profile, and wrong record/payload kind. Authorization fixtures
cover issue/expiry at `T - 1 microsecond`, `T`, and `T + 1 microsecond`,
`REJECTED`, wrong policy/build binding, and all multi-fault blocker
combinations. Nonce fixtures cover every proof/request/bundle/evaluation
binding, `FRESH_ACCEPTED`, signed `REUSED_REJECTED`, and bad authentication.
Deployment fixtures cross every root-key/profile/kind/scope/decision/window/
build-digest/key/context-projection defect with (a) canonical self-consistent
bundle bytes/claim, (b) absent or malformed/noncanonical/self-mismatched bundle,
and (c) malformed outer candidate. Clock fixtures independently cross null,
empty, malformed, noncanonical, bad-signature, wrong-key, wrong-profile, and
wrong-kind records with the same three candidate/bundle shapes. They assert
respectively the recomputed identity pair plus full blockers, null pair plus
full blockers, or no readiness object. Strict Ed25519 adversaries and
coordinated forged attestation/payload/signature/build-digest/candidate/bundle
self-hashes remain included.

With admitted prerequisites, the evaluator privately validates all 50 exact
handoff ISIN/direction rows and reconstructs assignments, selectors, clocks,
lineage, manifest, licence, and audience proofs. It performs no sector grouping,
aggregation, prediction, or report reduction. Candidate-derived private values
are invocation-local and never returned or retained. The only output is one
canonical `SectorParticipationReadinessV1`.

The attestation verifier, context finalizer, and evaluator are pure over the
explicit deployment-attestation bytes, fixed embedded root, separate canonical
internal reviewed build, and candidate bytes. After verification the evaluator
receives only `(candidate_input, verified_internal_context)`. The entire chain
makes zero network, filesystem, database, environment, wall-clock, randomness,
credential, logging, telemetry, subprocess, storage, or nonce-store calls and
maps the same root/build/attestation/candidate tuple to one byte-identical
count-free readiness outcome.

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

### Layer B identity sensitivity and count-free redaction

Layer B keeps candidate, deployment, and trust identities separate. Only
`SectorParticipationReadinessCandidateInputV1` is fuzzed through the request
API. Deployment-attestation fixtures exercise the fixed-root signature and
post-build binding; trust-context fixtures exercise reconstruction and key/
projection integrity internally. Neither artifact can become alternate caller
trust.

Readiness identity sensitivity remains restricted to fields actually covered by
the closed output projection: `study_identity_sha256`,
`evidence_bundle_identity_sha256`, `readiness_state`, ordered
`covered_requirement_ids`, and ordered `blocker_reasons`. A legal changed
projected field changes canonical readiness bytes and identity. An input-driven
coupled mutation rebuilds the complete legal state/coverage/blocker and paired-
identity group. An authenticated candidate-record mutation that leaves all five
projected fields identical must produce byte-identical readiness output and
identity; its candidate, payload, signature, and admission identities are tested
separately. Foreign output literals/order/nullability reject before identity
comparison. The excluded readiness self-identity and coordinated sealed-root
rehash retain their mismatch/rejection checks.

On readiness output surfaces, the redaction allowlist has exactly one private
value: any non-null canonical self-consistent bundle identity—including the
trust-blocked shape above—may appear only as both required study/evidence-bundle
identity fields and those two output-projection positions. Its equality-bound
occurrences inside private candidate records are allowed input locations, not
output exceptions. It may appear in no other readiness field or surface; a null
pair permits no output occurrence.

Canaries use distinct markers per independent channel or distinguishable multi-
field patterns and intentionally repeat a marker across contract-required
equality groups. Groups cover bundle identity; handoff/request/assignment/
manifest ISINs; selector/source/candidate/verified values; full internal reviewed
build and its derived digest; signed payload/content/envelope/attestation
identities; deployment root and signer key; authorization kinds, policies,
windows, signer-key identities and signatures; authenticated clock instants;
nonce/proof/request/bundle/evaluation bindings; context verification keys and
projection; and all other identity-bound repetitions.

The scanner requires zero group occurrences outside allowed private candidate,
internal deployment-attestation, or trust-context locations and the sole
bundle-identity output allowlist. It also rejects sector counts, credentials,
secrets, and free-form diagnostics in readiness bytes, returned objects,
previews, string/debug representations, equality diffs, errors/exceptions,
logs, telemetry, or retained snapshots. Positive controls leak a
non-allowlisted candidate/deployment/context marker or put the allowed bundle
identity in a forbidden field/surface. Changing a harness-only control must not
change readiness bytes or `READY`/`BLOCKED`.

## One feasible future chronology and sealing

The chronology is strict and deliberately avoids the prior circular plan:

1. **Initial work authorization only.** Obtain owner authorization to perform
   implementation work and separate authority to investigate source/licence/
   acquisition/retention/private-delivery work. These step-1 decisions are not
   `R01` records and cannot claim or bind identities that do not yet exist.
2. **Source, licence, acquisition, retention.** Approve the source binding,
   licence and retained-use scope, bounded acquisition manifest, capture
   authority, credentials if unavoidable, budget, and storage; then retain raw
   candidate bytes and trusted receipts without computing sector counts.
3. **Strict TDD Layer A implementation/review.** Implement/review the prerequisite
   observed-only handoff, then the pure schemas, admission, identities, privacy,
   and reducer under Layer A. No same-input handoff is claimed before this step.
4. **Seal final build, evidence, and policies.** Complete independent review and
   seal final code/build plus source, validation, semantic, privacy, licence,
   selector, audience, evidence, manifest, request/date/cohort, and cutoff bytes.
   Preserve the full canonical reviewed build internally and derive its exact
   all-fields identity without copying it into a future attestation.
5. **Issue compact post-build trust and final R01 evidence.** The external
   authorized release signer signs the bounded deployment payload containing the
   final reviewed-build digest, profile, four verification keys, and context
   projection—not the full build. Only now issue the two final signed identity-
   bound R01 authorization records with windows covering readiness evaluation.
6. **Authenticate evaluation and nonce admission.** At readiness time, issue the
   signed evaluation-clock record, perform the one-time owner-private nonce
   admission, and issue its signed fresh/reused decision bound to the exact
   proof, request, bundle, and authenticated instant.
7. **Construct and run count-free readiness.** Construct the raw candidate input;
   internally verify the compact deployment attestation against the separate
   full reviewed build, then evaluate exactly
   `(candidate_input, verified_internal_context)`. Emit only `READY` or `BLOCKED`
   readiness fields, never sector labels/counts/directions.
8. **Reduce one ready bundle.** If and only if readiness is `READY`, reduce that
   exact bundle once and deliver only through the owner-private boundary.

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
