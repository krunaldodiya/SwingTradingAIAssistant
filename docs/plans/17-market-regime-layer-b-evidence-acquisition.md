# Market Regime Layer B evidence acquisition

Status: **PLANNED — BLOCKED / CAPABILITY_EVIDENCE_MISSING**
Tracking: [parent acquisition goal — GitHub Issue #111](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/111), [planning/publication task — GitHub Issue #112](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/112), Milestone 2 (Sprint 10)
Risk: **R3** — point-in-time data integrity and release trust
Depends on: frozen [Plan 05](05-point-in-time-nifty50-universe-contract.md), [Plan 09](09-corporate-action-provenance-contract.md), [Plan 11](11-prospective-evidence-readiness-contract.md), [Plan 12](12-market-regime-contract.md), [Plan 13](13-market-regime-validation-protocol.md), and [Plan 16](16-market-regime-layer-b-acquisition-decision.md)

## Outcome and boundary

Sprint 10 has one conditional outcome: after its entry gate is met, acquire,
normalize, seal, and independently verify the complete predeclared
point-in-time evidence range required by frozen `nifty50-market-regime@v1`.
It must not compute a Market Regime label or inspect a validation outcome before
the Plan 13 source decision, acquisition manifest, exact range, partitions, and
identities are sealed.

This is an R3 planning and readiness record. It records the exact blocked
baseline and the gates a later implementation must satisfy; it is not acquisition
authority. Repository owner Krunal Dodiya's 2026-08-16 instruction authorizes
only Sprint 10 planning and publication of this plan, the Sprint 10 record,
sprint index, and roadmap through planning/publication task #112. It does not
authorize provider access, credentials, source selection, terms/use acceptance,
acquisition, persistence, runtime implementation, validation, or publication
beyond those four documentation records. Future source/use, acquisition and
evidence-publication, execution, and residual-risk decisions remain separate
and unauthorized.

### Exclusions

- No provider access, live request, source endpoint, licence, date range, budget,
  credential, approval identity, raw response, or acquisition implementation is
  declared here.
- No current constituent list may stand in for point-in-time membership; no
  inferred schedule, 49-name denominator, imputation, substitution,
  adjusted-price invention, or latest-wins overwrite is permitted.
- Plan 06 provisional current-month minutes and Plan 09 Upstox observations are
  not promoted to complete Layer B evidence authority.
- This plan adds no public Market Regime transport, CLI/API/MCP surface,
  label/count/direction/transition/return/outcome, prediction, recommendation,
  or trading claim.
- Plans 05, 09, 11, 12, 13, and 16 remain frozen. This plan neither changes nor
  reinterprets their facts, labels, cutoffs, reasons, or validation sequence.

## Five-line evaluation

1. Expected value: define the smallest controlled path from an independently approved capability manifest to complete retained Layer B evidence.
2. Scope fit: Nifty 50-only, point-in-time evidence work below the frozen Market Regime boundary; it adds no signal, strategy, or public transport.
3. Material data/research risk: incomplete, late, substituted, unauthoritative, non-comparable, or unlicensed evidence could manufacture an observed regime or invalidate release trust.
4. Smallest alternative: preserve the sealed `BLOCKED / CAPABILITY_EVIDENCE_MISSING` decision and prepare no-effect contracts until independently reviewable capability evidence exists.
5. Decision: **deferred / blocked** — no acquisition or implementation may start while the Plan 16 decision remains blocked.

## Authority and existing contract patterns

The R3 acquisition decision is a separate authority boundary. Plan 16 permits a
later planning boundary only when the exact reviewed build returns
`APPROVED_TO_ACQUIRE`; that state is not evidence acquisition or execution
authority. Before every future side effect, a later private executor must
independently authenticate an in-force, bounded execution authorization and
trusted execution-start receipt. Credentials, reachability, a digest, code
access, or a successful request are never authorization.

A permitted future implementation must reuse—not replace—the following existing
contracts and patterns:

- Plan 11's immutable, owner-approved, expiring
  `EvidenceExecutionAuthorizationV1`, which binds the source-policy digest,
  exact request-manifest and sorted 50-ISIN digests, allowed authorities and
  evidence classes, bounded scope, ceilings, decision identity, issuance, and
  expiry; its preflight remains provider-free.
- Plan 05's `Nifty50UniverseSnapshotV1` and `Nifty50UniverseStoreV1.retain` /
  `.resolve` pattern for immutable, content-addressed point-in-time universe
  evidence; a current symbol or current list cannot replace an ISIN-bound
  snapshot.
- Plan 11's `ScheduleEvidenceV2` semantics: a base schedule plus applicable
  official overlays, corrections, and supersessions; weekdays, standard hours,
  or missing candles are not calendar evidence.
- Plan 12's `MarketRegimeRequestV1`, `EvidenceAttemptV1`, and
  `MarketRegimeEvidenceBundleV1`, plus the existing
  `admit_verified_market_regime_facts_v1` and
  `reduce_attempts_to_insufficiency_v1` boundaries. An attempt records the exact
  requested identities and may preserve a failure or invalid candidate without
  asserting a verified fact; retained objects may enter only through unchanged
  admission and insufficiency reduction.
- Existing canonical-byte/SHA-256 identity binding, descriptor-relative
  no-follow/no-overwrite publication, storage-root lease, bounded ports,
  explicit trusted clocks, immutable revision lineage, and zero-call offline
  replay patterns.

There is no approved complete five-class Layer B evidence store, official
schedule-correction store, official daily-fact adapter, NSE_CM
comparability/continuity store, acquisition service, or public acquisition
interface. A future private adapter must not widen the candle
`PublicCommandReportV1` boundary.

## Acceptance criteria

The Sprint 10 planning record is complete only when all of the following are
true:

1. The four documentation records—this plan, the Sprint 10 record, sprint index,
   and roadmap—truthfully link Issues #111 and #112 and distinguish planning
   started from acquisition not started. Issue #112 closes only after the
   documentation candidate receives independent approval for its exact SHA,
   hosted gates, and merge, and that closure is observed. Parent #111 remains
   open and `BLOCKED / CAPABILITY_EVIDENCE_MISSING` until future acquisition
   closeout actually meets every criterion.
2. The current baseline is recorded as `BLOCKED /
   CAPABILITY_EVIDENCE_MISSING`, with its exact reviewed revision, manifest, and
   report identities, and without asserting an acquisition, readiness,
   admission, label, or execution authorization.
3. Every conditional phase has an explicit entry gate, required observable
   evidence, exit condition, and stop condition; none creates a substitute
   source, source claim, authorization, or approval.
4. Conditional RED cases challenge complete range accounting, exact 50
   ISIN-first membership, corrected schedule coverage, exact raw-close facts,
   corporate-action comparability/continuity, immutable retention, bounded
   side effects, interruption/replay, and no-label/no-outcome isolation.
5. Conditional implementation retains only authorized raw receipts and
   sanitized receipts immutably, publishes content-addressed generations
   atomically under the storage-root lease, and feeds retained objects only to
   the unchanged Plan 12 admission boundary.
6. Conditional independent verification recomputes retained-byte checksums and
   range accounting without acquisition-author control; it verifies all
   partitions, exact member-session facts, correction/supersession chains,
   cutoff clocks, source/use scope, authorization scope, and sealed identities
   against one candidate revision.
7. No future publication, Issue #111 closure, or Sprint 11 transition occurs
   unless the complete range is independently verified and every ordered Plan 13
   region—development, embargo 1, validation, embargo 2, and untouched
   test—remains sealed against labels and downstream outcomes. Any premature
   exposure invokes Plan 13 quarantine and requires a versioned manifest with
   genuinely new unexposed dates and holdout.

A missing or failed criterion is `BLOCKED`, not partial success. Any future
acceptance decision must name its authorized decision maker, candidate revision,
evidence, unmet criteria, and residual risk; neither this record nor an Issue
status supplies that authority.

## Current readiness evidence

The canonical observed baseline is `origin/main`
`2d5cb3734a35a77d107c21147a50c120555cdfab`. Its installed offline
`market-regime-acquisition-decision decide` command, given a structurally valid
caller payload, returned exit `1` with one canonical `BLOCKED` report on stdout
and empty stderr, as Plan 16 defines for a blocked decision. The observed
primary blocker is `CAPABILITY_EVIDENCE_MISSING`; the sealed manifest identity
is `53717e75d9e93344d7df55ea2a5e94e48e133ff0ad673f27e38ba040cc91bb2f` and the
canonical report identity is
`dbbc0bdf32cf081d491a119c05571bebf4dbd274bae858dd0e3d418b96bd1408`.

The manifest's capability group is absent. No admissible capability projection,
source/PIT evidence bundle, terms/use approval, operational-scope approval,
owner full-acquisition authorization, or trusted authorization-validation
receipt exists. The baseline therefore grants no provider access, acquisition,
readiness, admission, label, verification, publication, or later execution
authority. Sprint 10 planning has started; acquisition and all runtime
implementation have not started.

## Conditional phases

### Phase 0 — Freeze the planning and readiness record (in progress)

**Entry gate:** none; this phase is documentation-only and cannot grant runtime
authority.

**Required record:** the four documentation records preserve the current blocked
decision, exact identities, Issues #111 and #112, Milestone 2, frozen upstream
plans, scope exclusions, and the conditional gates below. They require the
distinct lifecycle: #112 is the current planning/publication task and may close
only after independent approval for the exact-SHA documentation candidate,
hosted gates, merge, and observed closure; parent #111 remains open and
`BLOCKED / CAPABILITY_EVIDENCE_MISSING` until future acquisition closeout
actually meets every criterion.

**Exit condition:** the four lifecycle records preserve the blocked baseline and
make no acquisition-completion or authorization claim, and #112 has received
independent exact-SHA approval, hosted gates, merge, and observed closure.
Issue #111 remains open and blocked.

**Stop condition:** stop this phase if a record would imply that planning,
tracker state, a credential, a manifest identity, or a historical probe
authorizes acquisition; if #112 lacks its required exact-SHA approval, hosted
gates, merge, or observed closure; or if #111 would be closed before future
acquisition closeout actually meets every criterion. Correct the claim rather
than inferring missing authority.

### Phase 1 — Conditional RED contracts (blocked)

**Entry gate:** an exact reviewed and published manifest build returns
`APPROVED_TO_ACQUIRE`, and complete independently reviewable identities exist
for source/PIT capability, terms/use, operational scope, owner authorization,
trusted clock, allowed range, endpoint, attempt, byte/duration ceilings,
credential owner, expiry, and revocation. A changed source or scope requires a
new five-line evaluation and renewed review before this phase.

**Required RED evidence:** discriminating tests first for complete range and
20-session pre-roll accounting; exact 50 ISIN-first membership per decision
session; corrected schedule through the next open with base/overlay/
supersession receipts; 100 exact raw close facts per decision session;
corporate-action negative completeness, revision, and identity continuity;
immutable raw receipts, normalized objects, manifests, and correction
generations; interruption, idempotent replay, partial failure, corrupt object,
stale or ambiguous revision, authorization expiry or revocation, request/byte/
time ceilings, and absence of label/outcome access.

**Exit condition:** each test fails because its new observable contract is
missing, not because a fixture, provider, credential, or infrastructure detail
is absent.

**Stop condition:** stop before any provider effect if the entry authorization
is absent, expired, revoked, out of scope, unverifiable, or bound to changed
identities; if a test requires a fabricated source or fixture to pass; or if a
case widens the frozen contract.

### Phase 2 — Conditional acquisition implementation (blocked)

**Entry gate:** Phase 1 has discriminatory RED evidence and the Phase 1
execution authorization remains independently valid at execution start.

**Required implementation:** one private adapter outside `market_regime` that:

1. validates the exact sealed authorization before every effect;
2. requests only approved sources and scope within hard request, concurrency,
   byte, and duration ceilings;
3. retains raw responses and sanitized receipts immutably;
4. normalizes explicit point-in-time universe, corrected schedule, raw daily
   close, and corporate comparability/continuity objects;
5. publishes content-addressed generations atomically under the storage-root
   lease;
6. seals complete-range accounting together with code, configuration, source,
   and revision identities, while keeping every ordered Plan 13 region—
   development, embargo 1, validation, embargo 2, and untouched test—sealed
   against labels and downstream outcomes; and
7. provides retained objects only to the unchanged Plan 12 `EvidenceAttemptV1`
   admission path.

**Exit condition:** focused positive, negative, failure, recovery, replay, and
no-look-ahead evidence is green without public transport or label/outcome
access. Refactoring may begin only after that unchanged green evidence.

**Stop condition:** stop the affected effect immediately on authorization
expiry/revocation/scope mismatch, clock failure, ceiling breach, unsafe or
corrupt object, incomplete/duplicate/substituted fact, ambiguous revision,
failed atomic publication, or any attempt to use current data, inferred
calendar, adjusted price, or caller assertion as evidence.

### Phase 3 — Conditional independent verification (blocked)

**Entry gate:** Phase 2 has one sealed candidate revision and retained immutable
objects available to an independent verifier.

**Required verification:** an independent verifier re-reads retained bytes and
recomputes checksums and accounting without acquisition-author control. It
verifies every decision session and pre-roll partition, every member-session
fact, no missing/duplicate/substituted fact, correction and supersession chains,
cutoff clocks, source/use and authorization scopes, and the exact candidate
revision. Throughout Sprint 10, every ordered Plan 13 region—development,
embargo 1, validation, embargo 2, and untouched test—remains sealed against
labels and downstream outcomes. It then runs the repository's applicable
focused and full verification gates plus the actual private runtime smoke path;
all evidence and independent R3 review bind to that exact candidate revision.

**Exit condition:** all required evidence is green on one unchanged candidate
revision and the verifier can reproduce the sealed identities without provider
access.

**Stop condition:** any changed candidate revision, unreproducible identity,
failed gate, non-independent verification, unsealed partition, missing fact, or
premature label or downstream-outcome exposure invokes Plan 13 quarantine and
returns the affected work to the relevant earlier phase. Resumption requires a
versioned manifest with genuinely new unexposed dates and holdout.

### Phase 4 — Conditional publication and closeout (blocked)

**Entry gate:** Phase 3 independently verifies the complete range on the exact
candidate revision, with all review and publication authority separately in
force, and all ordered Plan 13 regions—development, embargo 1, validation,
embargo 2, and untouched test—sealed against labels and downstream outcomes.

**Required closeout:** publish only the coherent verified candidate through the
repository delivery workflow, link the resulting review to Issue #111, record
the exact reviewed and merge identities and results, update the Sprint 10
outcome/evidence/carryover, and retain residual limitations. Hosted checks and
independent review must apply to the same candidate revision; any revision
change requires renewed review. Before future evidence publication or #111
closure, record either an explicit no-residual-risk result or a separately
authorized, identity-bound residual-risk decision naming each accepted risk,
consequence, likelihood or uncertainty basis, affected scope/assets,
compensating controls, evidence, authorized risk owner, the source and boundary
of that authority, conditions, and review/expiry. Absence of any required field
is a stop before future evidence publication, #111 closure, or Sprint 11
transition.

**Exit condition:** the authorized publication and closeout evidence records the
actual outcome without claiming that unmet evidence passed. Issue #111 closes
only after actual acquisition acceptance meets every criterion and the required
no-residual-risk result or separately authorized residual-risk decision exists.

**Stop condition:** do not publish future evidence, close Issue #111, or unblock
Sprint 11 if any complete-range evidence, independent verification, sealed
partition, required review, publication authority, or required no-residual-risk
result/residual-risk decision is missing or changes. Any premature exposure
invokes Plan 13 quarantine; resumption requires a versioned manifest with
genuinely new unexposed dates and holdout.

## Guardrails

- Do not treat `APPROVED_TO_ACQUIRE` as acquired, retained, complete,
  admissible, `READY`, `OBSERVED`, useful, or execution-authorized evidence.
- Do not treat access, credentials, HTTP success, media type, a digest, an Issue,
  a milestone, a historical probe, or silence as source/use or acquisition
  authority.
- Do not add an acquisition store, official source, endpoint, schedule feed,
  daily-fact adapter, public surface, source date range, licence, budget, or
  approval identity until its separate authority is present.
- Do not replace a missing session/member/fact with current data, inference,
  interpolation, symbol substitution, denominator reduction, adjusted prices,
  or a later revision; preserve the typed blocked result.
- Throughout Sprint 10, every ordered Plan 13 region—development, embargo 1,
  validation, embargo 2, and untouched test—remains sealed against labels and
  downstream outcomes. Any premature exposure invokes Plan 13 quarantine and
  requires a versioned manifest with genuinely new unexposed dates and holdout.
- Do not report blocked, stale, missing, failed, waived, or unrun evidence as
  accepted or green. A stop condition fails closed and requires the applicable
  authorized review before work resumes.
