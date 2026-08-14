# Sprint 8 — Sector Analysis: Sector Participation v1 specification

Status: **IN PROGRESS — OWNER APPROVED; ARK-179 ACTIVE WIP**
Owner decision: **approved on 2026-08-13 IST**
Planning base: `418445cd0e68af4a2e1b5b2a22a8d920398c6849`
Planned window: unassigned

## Goal and architecture placement

Plan the minimal V1 fact contract for architecture-locked Module 2, **Sector
Analysis**. `nifty50-sector-participation@v1` counts the exact private directions
from one observed Market Regime fact by authoritative point-in-time Sector-tier
labels. It is not an added or renamed eleventh module.

The increment is specification only: boundary/non-claims, taxonomy policy, fact
contract, validation/readiness preregistration, independently reviewed component
history, and pre-publication candidate reconciliation. Implementation, sources,
licence acceptance, acquisition or download, provider/data/credential access,
data-root or storage mutation, runtime, public surfaces, observed output,
ranking, and effectiveness claims are excluded.

The owner approved this direction on 2026-08-13 IST. That decision does not
approve any excluded work.

## Proposed-boundary evaluation

- Expected value: reproducible sector composition of the already-derived exact-50 Market Regime breadth fact.
- Scope fit: the minimal first contract inside locked Module 2 Sector Analysis; Nifty 50 end-of-day facts only.
- Material risk: historical taxonomy backfill, wrong tier, incomplete evidence lineage, and singleton disclosure.
- Smallest alternative: exact ISIN-to-Sector counts with full reconciliation and whole-report insufficiency.
- Decision: **accepted for planning only**; implementation and real evidence remain deferred.

## Planning artifacts

- [Plan 14](../plans/14-sector-participation-contract.md) freezes the closed
  request, observed/unobserved upstream envelope, observed-only private handoff,
  candidate/attempt/admission trace, taxonomy evidence, facts, equations,
  reasons, privacy, identities, bounds, and implementation stop.
- [Plan 15](../plans/15-sector-participation-validation-protocol.md)
  preregisters the independent exhaustive per-sector and aggregate oracle,
  boundary/revision/no-lookahead adversaries, permutation and renaming
  metamorphisms, privacy canaries, identity sensitivity, byte-exact replay,
  zero I/O, count-free readiness, and the feasible future chronology.
- Per the owner clarification, this planning increment adds no documentation
  assertion and no test file. Existing focused checks remain repository-quality
  evidence only, not implementation, reducer, evidence-readiness,
  privacy-runtime, or observed-result proof.
- The roadmap preserves Sector Analysis as locked Module 2.

## Exact Linear issue order, scope, and state

The repository mirrors the current Linear order and state at this
pre-publication point: ARK-175, ARK-176, ARK-177, and ARK-178 are **Done**;
ARK-179 is the sole **In Progress** issue. This repository edit reconciles that
already-observed tracker truth; it does not itself transition an issue or write
to Linear. Delivery remains sequential WIP-one in this exact order:

| Order | Issue | Exact scope | Current state |
|---:|---|---|---|
| 1 | ARK-175 | boundary and non-claims | Done |
| 2 | ARK-176 | taxonomy policy | Done |
| 3 | ARK-177 | fact contract | Done |
| 4 | ARK-178 | validation and readiness | Done |
| 5 | ARK-179 | publish and review | In Progress |

The first four specification components reached their review stop boundaries
before ARK-179 started. There is no implementation/source/runtime/data/provider/
credential/download/data-root/public-interface work in these issues.

### ARK-175 — boundary and non-claims

Freeze placement as the minimal V1 fact inside Module 2 Sector Analysis; inherit
the exact Market Regime endpoints/cohort/directions; define observed versus
unobserved upstream behavior; and freeze every descriptive, trading, predictive,
performance, data-family, and public-delivery non-claim.

Acceptance: no architecture conflict, no eleventh module, owner approval dated
2026-08-13 IST, and no claimed implementation or observed fact. Stop on a changed
module, endpoint, cohort, purpose, or need for source contact.

### ARK-176 — taxonomy policy

Freeze NSE Indices authority and classification by exact ISIN to the same
decision-session 50-member cohort; exact official Sector tier, release, and
effective interval; knowledge cutoff and trusted publication,
response-completion, retrieval, and immutable-retention clocks;
immutable selector/source/schema binding; revision, supersession, manifest,
licence/private-use, and conflict rules. Current CSV `Industry` or sector labels
remain opaque rather than official Sector-tier proof; reject current-map
backfill, alias inference, and inferred sector-index membership.

Acceptance: one exact policy maps every valid/invalid candidate without source
selection or acquisition. Stop on ambiguous authority/tier/licence, inferred
history, partial mapping, or provider/data need.

### ARK-177 — fact contract

Freeze all closed schemas, bounded structural request, discriminated upstream
envelope, observed-only handoff, candidate/attempt/verified trace,
owner-private proof, trusted manifests, canonical identities, exact equations,
nullability, reasons, truth tables, bounds, and zero-I/O reducer boundary.

Acceptance: an independent implementer need not invent a field, trust decision,
selector, reason, identity, or equation. Stop on already-verified-only input,
caller-trusted facts, partial output, or implementation work.

### ARK-178 — validation and readiness

Plan 15 preregisters structural/no-report versus domain insufficiency,
exhaustive per-sector direction triples and exact aggregate reconciliation,
independent and property oracles, selector binding, effective/cutoff and
revision boundaries, cross-authority no-lookahead, schedule and
corporate-action upstream adversaries, permutation/renaming and post-cutoff
metamorphisms, privacy canaries, identity sensitivity, byte-exact replay, zero
I/O, one-bundle readiness without count disclosure, and the feasible
non-circular chronology.

Acceptance: every contract edge has a future zero-tolerance test and readiness
cannot disclose an outcome. Stop if tests require real data/provider access,
recompute upstream facts, tune outcomes, or imply implementation proof.

### ARK-179 — publish and review

Seal the exact cumulative specification candidate in a durable commit; run the
workflow-required authoritative full gate on that sealed revision; obtain an
independent exact-SHA review and resolve every finding in separate preserved
repair commits; push and open the publication PR; require successful hosted CI
and GitGuardian evidence; merge only with authorization; and reconcile final
Linear and sprint state without starting implementation.

Acceptance: sealed candidate and any repair SHAs plus exact cumulative diff;
passing authoritative full-gate evidence; independent approval of the final
exact SHA; push/PR URL and exact head; successful hosted CI and GitGuardian
results for that head; authorized merge and resulting `main` SHA; ARK-179
**Done** and Sprint 8 closure reconciled in Linear and repository Markdown; and
explicit residual authorization/readiness blockers. Any failed or missing gate,
review, hosted check, authorization, merge, or reconciliation blocks final
publication. Stop before implementation, source/runtime/provider/credential/
data-root access, readiness, or observed-result activity.

## Reviewed component and repair history

The immutable history below is the exact review record from this Goal epoch.
Before each exact-SHA review, the issue-scoped Verification role reported
**PASS**, the Antipattern role reported **PASS**, and the Quality role reported
**APPROVE**. The named ExactShaReview roles were independent, read-only agent
reviews; they were not hosted CI, an external human review, or publication.

| Issue | Preserved component and repair revisions | Independent exact-SHA verdict | Cumulative reviewed paths |
|---|---|---|---|
| ARK-175 | `3e7d879bf131a1290d1441e3bac962be63136bef` | `BoundaryExactShaReview`: **APPROVE**, no findings | `docs/plans/14-sector-participation-contract.md` |
| ARK-176 | `d418e67a3aac0b4cb9e237517d6dc761e30179c9` | `TaxonomyExactShaReview`: **APPROVE**, no findings | Plan 14 and `docs/sprints/sprint-8.md` |
| ARK-177 | Initial `260457a4d05573f122d76badf7205d080035c85e` preserved after **REQUEST_CHANGES**; separate repair `dde53e82a47e9adde5c6b6a9137e2cacf66ea6f0` | `ContractExactShaReview`: repair candidate **APPROVE** | Plans 14 and 15 |
| ARK-178 | Initial `f3dd0bfa6c342b0e9fdfa4e0cc9e74e76b764da0`; separate repairs `3064a4919a6721e8df772ecba123b125904e0d9a`, `c456ea92b1fac75ebf5a045f32933e16ca73add6`, and final `4f7582caff607b3a7046bdbd0f8a87c6977be0c7`, all preserved | Earlier exact-review findings were repaired separately; `ValidationExactShaReview`: final repair candidate **APPROVE** | Plans 14 and 15 plus Sprint 8; final repair changes Plan 15 only |

The reviewed component range has exact main parent
`aa68b0029eab22323700e8837238e28f41e1d694` and tip
`4f7582caff607b3a7046bdbd0f8a87c6977be0c7`.
Its cumulative name-status audit contains only three modified Markdown paths:
Plans 14 and 15 and this Sprint 8 record; the audited stat is 894 insertions and
139 deletions. ARK-179 pre-publication reconciliation expands the candidate
path set only with `docs/sprints/README.md` and `docs/roadmap.md`, while updating
this already-in-scope record. No source, test, configuration, workflow, lock,
provider, credential, data, or generated path is in scope.

## Specification acceptance checklist

Review must verify:

- minimal V1 fact contract inside locked Module 2 Sector Analysis, never an
  eleventh module;
- exact owner approval date, issue order/scope, current states, and WIP-one truth;
- closed `SectorParticipationRequestV1` and
  `OwnerPrivateAudienceProofV1` schemas;
- discriminated observed/unobserved upstream envelope, handoff only when
  observed, and exact nullable endpoint outcomes;
- bounded candidate/attempt admission representing missing, late, 0/49/51,
  duplicate, ambiguous, corrupt, wrong-tier, clock, licence, and revision
  defects as insufficiency while malformed bytes produce no report;
- receipt/selector and sealed authority/source/schema/release/clock/revision/
  manifest/licence proof binding, reconstructed rather than caller-trusted;
- exhaustive per-sector size/direction triples, exact aggregate equations,
  whole-report failure, reason precedence, permutation invariance, label
  renaming, privacy suppression/canaries, identity sensitivity, and zero I/O;
- byte-identical unchanged old replay across membership, classification,
  assignment mapping, schedule, and corporate-action future revisions versus
  new identities/outcomes for a separately sealed changed post-cutoff input;
- explicit effective/cutoff edges, duplicate/extra rows, revision
  forks/cycles/conflicts, schedule corrections, and corporate-action
  completeness adversaries without downstream recomputation; and
- strict conformance/readiness/result separation followed by authorization →
  source/licence/acquisition/retention → strict-TDD Layer A and review → sealing
  → count-free readiness → one ready-bundle reduction.

## Data and readiness truth

No Market Regime sector handoff implementation exists. No official point-in-time
50-row Sector evidence, taxonomy release binding, selector trace, complete
revision graph/manifest, approved retained-use licence, acquisition authority,
download, authorized retained data root, reviewed Sector Participation build,
owner-private runtime proof, or public delivery surface is admitted. The future
readiness gate is therefore blocked and has not run.

Synthetic fixtures can later prove mechanics only. A current public file cannot
prove historical effective, publication, clock, revision, licence, or retained-
use truth. The existing retained Market Regime sample cannot cure these gaps.
There is no observed sector result, ranking, predictive conclusion, performance
measurement, or effectiveness evidence.

## Pre-publication actuals, pending facts, and stop

### Current pre-publication writer stop — this uncommitted drafting step only

This temporary stop governs only the present pre-publication reconciliation. It
does not narrow the final ARK-179 publisher obligations and acceptance above.

Actuals at this candidate point are limited to owner approval, the four
preserved specification-component histories and independent agent-role reviews
above, current Linear state reconciliation, and a Markdown-only diff audit. No
ARK-179 validation or commit has been performed. Earlier focused no-coverage,
Ruff, Markdown, and diff checks are component review evidence only; they do not
prove a parser, evidence selector, handoff, reducer, private audience, readiness
gate, market fact, publication, or merge.

The following are pending facts because the prohibited actions that could
produce them have not occurred; they are not claimed evidence:

- final ARK-179 candidate commit SHA and sealed cumulative diff;
- push or remote feature-branch recovery checkpoint;
- PR number/URL and hosted documentation-gate result;
- hosted CI, GitGuardian, or other hosted security-check result;
- merge authorization, merge event, and resulting `main` SHA;
- final publication evidence, ARK-179 **Done**, and Sprint 8 closure.

Residual authorization/readiness blockers are unchanged: implementation
authorization; separate source, licence, acquisition/download, immutable
retention, and owner-private-delivery authorization; an observed Market Regime
report and its exact private Market Regime handoff; exact point-in-time
membership, Sector-tier, revision, manifest, selector, and clock evidence; an
authorized retained data root; reviewed Sector Participation implementation and
owner-private runtime; sealed build/policy/code/audience proofs; and one
count-free readiness admission. None is satisfied by specification review.

Do not validate, commit, push, open a PR, contact a provider, use credentials or
data, download anything, mutate a data root or storage, expose a public surface,
write Linear, run readiness, or merge in this step. ARK-179 remains the sole
**In Progress** issue and Sprint 8 remains open before publication and
implementation. The later feasible chronology remains the one frozen in Plan
15.
