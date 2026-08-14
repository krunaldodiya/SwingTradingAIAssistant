# Sprint 8 — Sector Analysis: Sector Participation v1 specification

Status: **PLANNED — OWNER APPROVED; ALL ISSUES TODO/UNSTARTED**
Owner decision: **approved on 2026-08-13 IST**
Planning base: `418445cd0e68af4a2e1b5b2a22a8d920398c6849`
Planned window: unassigned

## Goal and architecture placement

Plan the minimal V1 fact contract for architecture-locked Module 2, **Sector
Analysis**. `nifty50-sector-participation@v1` counts the exact private directions
from one observed Market Regime fact by authoritative point-in-time Sector-tier
labels. It is not an added or renamed eleventh module.

The increment is specification only: boundary/non-claims, taxonomy policy, fact
contract, validation/readiness preregistration, documentation review evidence,
and a future reviewed handoff. Implementation, sources, licence acceptance,
acquisition, provider/data/credential access, storage, private-delivery runtime,
CLI/API/MCP, and observed output are excluded.

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
  preregisters structural/domain distinction, exact oracle, selectors,
  adversaries, metamorphisms, upstream boundary, privacy, zero I/O, readiness,
  and feasible future chronology.
- Per the owner clarification, this planning increment adds no documentation
  assertion and no test file. Existing focused checks remain repository-quality
  evidence only, not implementation, reducer, evidence-readiness,
  privacy-runtime, or observed-result proof.
- The roadmap preserves Sector Analysis as locked Module 2.

## Exact Linear issue order, scope, and state

The repository mirrors the exact operational order and scope below. Every issue
is currently **Todo / unstarted**. This planning commit does not transition an
issue, create an issue, or write to Linear. Future delivery is strictly
sequential WIP-one in this exact order:

| Order | Issue | Exact scope | Current state |
|---:|---|---|---|
| 1 | ARK-175 | boundary and non-claims | Todo / unstarted |
| 2 | ARK-176 | taxonomy policy | Todo / unstarted |
| 3 | ARK-177 | fact contract | Todo / unstarted |
| 4 | ARK-178 | validation and readiness | Todo / unstarted |
| 5 | ARK-179 | publish and review | Todo / unstarted |

No later issue starts before the preceding issue's acceptance and review stop
boundary. There is no implementation/source/runtime/data/provider/credential or
interface work in these issues.

### ARK-175 — boundary and non-claims

Freeze placement as the minimal V1 fact inside Module 2 Sector Analysis; inherit
the exact Market Regime endpoints/cohort/directions; define observed versus
unobserved upstream behavior; and freeze every descriptive, trading, predictive,
performance, data-family, and public-delivery non-claim.

Acceptance: no architecture conflict, no eleventh module, owner approval dated
2026-08-13 IST, and no claimed implementation or observed fact. Stop on a changed
module, endpoint, cohort, purpose, or need for source contact.

### ARK-176 — taxonomy policy

Freeze NSE Indices authority, exact Sector tier, ISIN join, effective and
knowledge time, immutable selector/source/schema/release binding, trusted clocks,
revision lineage/manifest completeness, licence/private-use proof, and rejection
of current-map backfill or taxonomy substitution.

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

Preregister structural/no-report versus domain insufficiency, exhaustive and
property oracles, selector binding, revision forks/cycles/conflicts, schedule and
corporate-action upstream adversaries, corrected post-cutoff metamorphisms,
privacy/redaction, zero I/O, one-bundle readiness without count disclosure, and
the feasible non-circular chronology.

Acceptance: every contract edge has a future zero-tolerance test and readiness
cannot disclose an outcome. Stop if tests require real data/provider access,
recompute upstream facts, tune outcomes, or imply implementation proof.

### ARK-179 — publish and review

Publish the exact-SHA specification candidate for independent adversarial review,
resolve findings, run documentation-only checks, and preserve the future strict-
TDD handoff without starting implementation or changing operational issue state.

Acceptance: exact reviewed SHA plus existing focused-test, lint, Markdown, and
diff evidence, with no new assertion/test file, and explicit residual
authorization/readiness blockers. Stop before
push/PR unless separately directed, and before source, runtime, implementation,
or observed-result activity.

## Specification acceptance checklist

Review must verify:

- minimal V1 fact contract inside locked Module 2 Sector Analysis, never an
  eleventh module;
- exact owner approval date, issue order/scope, and Todo/unstarted truth;
- closed `SectorParticipationRequestV1` and
  `OwnerPrivateAudienceProofV1` schemas;
- discriminated observed/unobserved upstream envelope, handoff only when
  observed, and exact nullable endpoint outcomes;
- bounded candidate/attempt admission representing missing, late, 0/49/51,
  duplicate, ambiguous, corrupt, wrong-tier, clock, licence, and revision
  defects as insufficiency while malformed bytes produce no report;
- receipt/selector and sealed authority/source/schema/release/clock/revision/
  manifest/licence proof binding, reconstructed rather than caller-trusted;
- exact equations, whole-report failure, reason precedence, privacy suppression,
  canonical identities, and zero I/O;
- byte-identical unchanged old replay versus new identities/outcome for a
  separately sealed changed post-cutoff input;
- explicit revision forks/cycles/conflicts, schedule corrections, and corporate-
  action completeness adversaries without downstream recomputation; and
- authorization → source/licence/acquisition/retention → strict-TDD Layer A and
  review → sealing → count-free readiness → one ready-bundle reduction.

## Data and readiness truth

No Market Regime sector handoff implementation exists. No official point-in-time
50-row Sector evidence, taxonomy release binding, selector trace, complete
revision graph/manifest, approved retained-use licence, acquisition authority,
reviewed Sector Participation build, or owner-private runtime proof is admitted.
The future readiness gate is therefore blocked and has not run.

Synthetic fixtures can later prove mechanics only. A current public file cannot
prove historical effective, publication, clock, revision, licence, or retained-
use truth. The existing retained Market Regime sample cannot cure these gaps.

## Review evidence boundary and stop

Focused no-coverage tests, Ruff, Markdown checks, and diff inspection in this
planning repair show documentation consistency only. They do not prove a
request parser, evidence selector, handoff, reducer, private audience, readiness
gate, or market fact exists.

This repository-only repair stops after one local documentation commit. Do not
push, open a PR, contact a provider, use credentials/data, mutate storage, or
write Linear. Future Sprint 8 delivery starts at Todo ARK-175 only when
separately authorized, proceeds sequentially through ARK-179, and stops before
implementation. The later feasible chronology remains the one frozen in Plan 15.
