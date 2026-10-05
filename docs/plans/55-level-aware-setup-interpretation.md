# Plan 55: coherent level-aware external candidate interpretation

Status: accepted bounded Sprint41 specification under the owner's October5,
2026 next-sprint same Goal instruction and standing full delivery authorization
without redundant approval. Outcome/risk owner: Krunal Dodiya. R3 public
financial-research consumer interface, privacy and provenance. Base
`f311eb021b2e76fc97f80d8865d89a0f75fc4056`, exact published Sprint40 main.
Governing Issue and Sprint41 milestone are recorded in the live freeze receipt.

## Necessary question and first working slice

1. Value: can an external consumer acknowledge the delivered broken-high relation alongside continuity, invalidation and age for one exact admitted pair, with false structured claims rejected?
2. Fit: signal-generation evidence/consumer boundary; explanatory reasoning remains external and suitability/effectiveness remain unassessed.
3. Risk: join independently acquired revisions, omit or change the level fact, promote ABOVE to confirmation or BELOW to structural invalidation, or silently alter previous closed schemas.
4. Smallest alternative: combine unchanged Plan52 v1 evidence and Plan54 v1 level on the same two typed observations, then reuse Plan53 validation rules in an explicitly separate v2 contract. No new market calculation, provider, model or store.
5. Disposition: accepted after real-producer synthetic discovery confirms v1 evidence omits level and its checker correctly rejects a level claim; other analytical/retest/expiry/eligibility policies deferred.

Plan34 admission: discovery records ABOVE and BELOW pairs with SAME_EVENT,
NO_CONTRADICTION_OBSERVED and age1, but no existing coherent handoff/checker
can admit their level claim. Separate commands acquire separate pairs and ask
the external AI to reconcile deterministic identity. New v2 composition binds
one pair and checks its return; it adds provenance coherence and enforcement,
not independent market confirmation. Coverage is exactly the existing finite
21-session contracts, including unknown/revised/window states. Market frequency,
usefulness, effectiveness and operational savings remain unmeasured. No Future
Issue is selected. Existing v1 public schemas, source bytes and identities stay.

## Closed public contracts

`assemble_setup_evidence_v2(previous, current)` accepts exactly two typed
CURRENT_STRUCTURE CurrentStockResearchResultV2 observations. Call unchanged
`assemble_setup_evidence_v1` once and unchanged `observe_setup_level_v1` once
on that same pair. Retain complete producer/source/runtime/diagnostic/timing/
mapping/basis admission before any successful handoff. Never accept authored
component JSON in place of typed admission. Require equal previous/current
observation hashes and full rows in all four components; verify level's unsigned
hash and exact continuity reference. Any inconsistent binding is terminal,
including otherwise UNKNOWN evidence.

Output `causal-setup-evidence@v2` contains the unchanged detection criterion,
both observation hashes, exactly four full components `continuity`,
`invalidation`, `age`, `level`, own runtime identity, unsigned result identity
and `legacy_evidence_identity_sha256` referencing the regenerated v1 bundle.
Preserve the three original components byte-for-byte and complete Plan54 level
semantics/witness/reason/null. Fixed limitations retain all v1 limits and state
ABOVE/AT/BELOW is descriptive, ABOVE does not confirm eligibility/validity and
BELOW does not establish Plan50 structural invalidation. No aggregate verdict.
Sorted compact JSON+LF, whole output <=1MiB, no raw market/private payload.

`setup_interpretation_request_v2_from_json(raw)` and
`check_setup_interpretation_v2(previous, current, response)` retain Plan53
exact input, parser, narrative, posture, bounds and validation precedence.
Response schema is exactly `external-setup-interpretation-request@v2`.
Facts contains exactly the original three claims and `level`. Level has exactly
`result_identity_sha256`, `status`, `relation`; relation is ABOVE/AT/BELOW or
null with no coercion. Original claims retain their exact v1 fields/types.
Revalidate the entire response before observation/source access, regenerate
v2 evidence once, require its exact hash and every component claim exact.
Changed/omitted relation, count/null/status/hash, swapped stock/revision and
v1/v2 substitution are terminal. No caller-supplied bundle substitutes.

Output `external-setup-interpretation-check@v2` retains the Plan53 labels,
complete v2 evidence, normalized caller response/hash and own runtime/result
identity. STRUCTURED_BINDING_ONLY; narrative accuracy/authorship, eligibility,
actionable recommendation and effectiveness unassessed. RESEARCH_ONLY/NO_TRADE
remain caller postures permitted on every factual state, no hidden policy.
Narrative is explicitly supplied untrusted caller text; it never becomes a
tool fact or diagnostic. Canonical whole output <=1MiB atomically.

Use new closed source-at-rest manifests for new v2 SDK/CLI modules, shared
Plan53 validation helper source and unchanged private file-reader source as
applicable. Include original v1 evidence and level runtime identities in the
v2 runtime closure. Missing/extra/substituted source inventory is terminal;
format every changed source before refreshing manifests. Old manifests stay.

## Injected working paths and effects

New injected `setup-evidence-v2` and `setup-interpretation-v2` CLI adapters
retain Plan52/53 selectors, absolute paths and CURRENT_STRUCTURE port. The
interpretation adapter retains `--interpretation-file` and the unchanged
owner-private bounded no-follow reader. Validate request before effects; read
one response once and obtain exactly two serial selector-bound observations,
compose/check once. No acquisition, network/model/provider/credential/write,
backdating, automatic retry, persistence or new transport authority.

Request/file/parser error exit2 request_invalid, zero service calls/empty
stdout; observation/runtime/binding/overflow/interruption exit2 fixed
setup_evidence_failed or setup_interpretation_failed, empty stdout.
Successful exit1 if any of the four components is inconclusive using unchanged
v1 component status sets (level UNKNOWN/NON_COMPARABLE/OUTSIDE_WINDOW/
NOT_REPRESENTED/REVISED_EVENT); otherwise0. Replay, no baseline and no later
session are not process failures; exit0 never means eligibility or narrative
truth. Pure repeats/concurrent checks input-preserving and write-free.

First working path: real guarded producer ABOVE pair, assembled v2 packet,
caller response checked by actual CLI through exactly two admitted port calls.
Then complete BELOW/AT, INVALIDATED with independent age/relation, replay,
unknown and false-relation rejection. Demo fixed dates and synthetic caller
authorship explicit, no live market/model/effectiveness claim.

## Frozen adversarial and delivery matrix

| Case | Observable result, prohibited effect and evidence |
| --- | --- |
| Working/coherence | Real-producer SDK and actual CLI v2 equality, four exact pair/component bindings and legacy hash, exactly two calls; no separate reacquisition |
| Independent facts | ABOVE/AT/BELOW unchanged, INVALIDATED with age and level retained; no level-driven eligibility/invalidation/posture policy |
| States/time | Replay/null, source-only no-later, no-baseline, unknown, revised event/low, absence/window/noncomparable and exact selectors remain independent |
| False response | Wrong bundle/component/stock/revision hash, level status/relation/null, omitted/extra/swapped fact, changed age/bool and actionable disposition rejected |
| Complete admission | Malformed response precedes acquisition; complete typed packet/runtime/source/diagnostic/bar/anchor/time admission before successful check even with unknown; authored components rejected |
| Composition integrity | Substituted component rows/hashes/continuity/unsigned identity terminal; no partial or relabelled UNKNOWN; old components byte-for-byte retained |
| Parser/bounds | 1/65536/plus-one bytes, duplicate nested keys/nonfinite/deep/UTF8/schema/types, 2048/plus-one/blank/control/surrogate narrative, whole1MiB/plus-one atomic |
| Private reader/effects | Existing no-follow/owner/private/single-link/regular/size/change checks and closure; request failures before service, no network/model/write/secret/raw market leak |
| Recovery/concurrency | Read/second observation/component/serialization interruption empty stdout; explicit repeat stable, concurrent pure calls stable, inputs unchanged; source/prior wheel rollback |
| Source/compatibility | Closed new manifests with unchanged transitive source closures; v1 evidence/interpretation/level/public versions and all six old installed maps unchanged |
| Installed | Actual isolated -I SDK and injected CLI ABOVE/AT/BELOW/invalidated/replay/unknown, NO_TRADE and false relation rejected; mocks only feedback |
| Full lifecycle | Two independent complete exact-candidate domain and security/privacy/provenance reviews, GitGuardian, full hosted tests>=87% aggregate branchcoverage/static/sdist/wheel/nativeOCI/adversarial/interruption/priorwheel; normal merge/exact main/private publication/fresh pulls/complete archives/live tracker/localmain |

## Ownership, Goal and closeout

Coordinator sole source writer/integration/tracker owner, no nested delegation.
Owned: new setup_evidence_v2 and setup_interpretation_v2 SDK/CLI/manifests,
focused tests and guarded demo, existing Linux verifier/focused tests,
Plan55/Sprint41/operator and small related roadmap documents. No existing SDK,
producer/market math, dependency, workflow, retained-data or old manifest edit.
Approved owner .venv outside worktrees with candidate imports, no installation
or copied environment. Preserve all prior checkout/evidence; no cleanup.
Tests first, lightweight focused/static feedback, stable committed candidate,
two fresh independent read-only full reviews then full hosted acceptance.
Each reviewer receives exact base/head/tree/full diff/matrix and complete
evidence; retain full reports/pre-post identities, no nested delegation.
Handbook primary TDD, scoped governance/contracts/release and requirements
specification fallback; trusted original procedure identity not established.

Goal starts only after this exact contract and live Issue/private Project/
Sprint41 milestone/field readback. Standing owner authorization covers in-scope
routine implementation/repair, review, draft/ready PR, gated normal merge,
exact main admission/private publication/fresh pulls, archives and tracker/
localmain closeout. No redundant approval. Fresh shared included account
allowance/storage/reset and Actions AND Packages $0 StopusageYes controls before
every hosted trigger/retry/merge; all quality gates retained. No automatic rerun,
paid/public/access/settings workaround, heavy local/self-hosted fallback,
admin/directmain/deletion. Stop only dependent genuine authority/source/provider/
credential/protected/destructive/conflicting-owner-work/failed-gate/unavailable
evidence/unaccepted residual-risk effects; never fabricate a pass. Provider
review refusal remains INVALID/NO VERDICT and cannot be bypassed.

Full original matrix/Issue criteria and exact final live states agree before
Goal completion. All eight Plan47 obligations stay distinct and overall signal
phase incomplete. No new analytical calculation, level/retest catalogue,
strategy/confirmation/eligibility/expiry/monitoring/persistence/Future/source/
model/history/broker/money/risk/capital/position expansion. Windows/private_source
historical cases and local CI retirement remain separately governed. Sprint40
completion is live verified; earlier pre-delivery wording remains history.
