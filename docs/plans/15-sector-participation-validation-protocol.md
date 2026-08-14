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
direction enum, and 49/51 handoff rows are structural no-report cases. Only
after both objects are canonical, digest-valid, version-correct, and the handoff
has exactly 50 rows do duplicate/unsorted handoff ISINs, report
identity/endpoint mismatch, or direction-total mismatch yield
`MEMBER_DIRECTION_HANDOFF_INVALID`, exactly as Plan 14 declares. No test derives
a direction from close values or replays Market Regime schedule/corporate-action
logic.

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

Tests evaluate multi-fault combinations so the earliest applicable reason is
primary and every lower applicable reason appears once in declaration order.
Discovery and candidate row order cannot alter domain reason ordering.

### Aggregation exhaustive oracle

Enumerate all 1,326 nonnegative direction triples `(a, d, u)` satisfying `a + d
+ u = 50`. For each, exercise one 50-member sector, fifty singleton sectors,
one singleton plus 49, 25/25 sectors, and a deterministic irregular partition.
The independent oracle must match every row and global equation exactly.
Each expected observed row has exactly `label`, `member_count`, `advances`,
`declines`, and `unchanged`; the oracle admits no extra row field, alias, or
derived percentage.

For helper cohort sizes 0..8, enumerate all three-way directions and every
restricted-growth sector partition. At production admission, exercise 0..49,
50, and 51 rows, duplicate/missing/extra joins, and every sector-label boundary.
Only exact 50 can be observed. Sector labels cover 1-byte and 128-byte valid NFC
UTF-8 plus empty, 129-byte, padded, control-character, invalid UTF-8, non-NFC,
and visually similar distinct labels.

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

- bijectively rename synthetic sector labels: associated counts remain, covered
  identities change;
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

### Audience privacy and redaction

Enumerate owner proofs at issue/expiry boundaries and every invalid class:
public, anonymous, unauthenticated, wrong owner, wrong purpose, wrong verifier,
wrong privacy policy, mismatched request, reused nonce, future-issued, expired,
identity mismatch, and caller boolean in place of attestation. Use a trusted
injected evaluation instant; wall-clock reads are forbidden.

Exercise all-singleton, one-singleton-plus-49, multiple-singleton, no-singleton,
and one-sector shapes. Invalid proof always yields
`PRIVACY_POLICY_UNSATISFIED` and null sectors. No row may be selectively
suppressed. Scan canonical output, string conversion, equality failures,
exceptions, logs, telemetry, and snapshots for ISINs, symbols, company names,
member directions, closes, source rows, paths, credentials, secrets, licence
text, and free-form diagnostics.

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

Run every valid and invalid reducer fixture with network, socket, filesystem,
database, environment, wall clock, sleep, randomness, credentials, logging,
telemetry, subprocess, and storage entry points replaced by fail-fast sentinels.
Required calls are exactly zero.

## Layer B — future one-bundle readiness without count disclosure

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
