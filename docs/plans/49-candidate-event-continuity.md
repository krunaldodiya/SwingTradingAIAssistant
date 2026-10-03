# Plan 49: bounded candidate event continuity

Status: accepted implementation contract within the owner's October 3, 2026
Sprint 35 signal/research planning and implementation direction. Owner and risk
owner: Krunal Dodiya. Risk R3: public research, causal knowledge and provenance.
Base: `3ef1c304100a92be17596a1432a25011e888d9da`.

## Necessity and direction

1. Value: answer whether one previously detected upward BOS is still represented in a later admitted Structure window, even after it stops being the latest-bar event.
2. Fit: factual research continuity before any active-signal policy; no recommendation or new calculation.
3. Risk: confusing latest-screen absence, rolling-window loss or revised evidence with invalidation, expiry or continued validity.
4. Smallest alternative: inspect existing typed events and anchors; Plan 48 compares latest-bar candidates and cannot answer this question. Reuse its admission and compatibility rules.
5. Disposition: accepted, one stock, two observations, one previous MATCH; no new market formula, source, provider, threshold or persistence.

[Plan 34](34-swing-research-feature-map.md) admission: the distinct information is
representation of the original event outside the latest bar, not another signal
filter. The bounded producer already carries 21 admitted completed sessions and
typed Structure events/pivots. Cost is one scan of that finite calculation.
Expect explainable coverage only while original anchor, confirmation and event
sessions remain in the window. Missing evidence is explicit. Synthetic checks
establish contract correctness, not occurrence frequency or trading utility.
No scores, effectiveness, liquidity or eligibility claims are admitted.

All eight [Plan 47 baseline outcomes](47-causal-setup-detection.md#signal-phase-completion-baseline-and-ordered-gaps)
remain: detection; necessary analytical coverage; generation responsibility and
identity; confirmation/invalidation/expiry/duplicates; observable lifecycle;
context/safety; correctness/interpretation/effectiveness; verified phase closeout.
This slice advances factual lifecycle observation only. Validity, expiry,
invalidation, persistent monitoring, generation policy, liquidity adequacy,
source-backed fundamentals, eligibility and effectiveness remain open.
Every Future-marked Issue is excluded; #250's migration follow-ups are separate.

## Frozen contract

Pure SDK `observe_setup_event_continuity_v1(previous, current)` accepts exactly
two `CurrentStockResearchResultV2` CURRENT_STRUCTURE observations. Call Plan 48
comparison first: validate both complete inputs, metadata bounds, runtime,
packet, diagnostics, causal anchors, provenance and deadlines before semantic
results. Preserve its stock/mapping/profile/basis/temporal compatibility and
knowledge ordering, including same-session refresh. No caller-authored candidate
or event JSON, network, clock, storage, acquisition, or state mutation.

Ordered semantic outcomes:

- NON_COMPARABLE: Plan 48 compatibility failure, same fixed reason.
- UNKNOWN: previous required Structure unknown; current unknown when a baseline exists.
- NO_BASELINE: supported previous NO_MATCH, even if current MATCH or exact replay.
- REPLAY: identical admitted observations with previous MATCH.
- OUTSIDE_WINDOW: any original pivot, confirmation or event session is absent from current admitted sessions; this cannot establish removal or invalidation.
- NOT_REPRESENTED: required sessions present but no current event has the original locus.
- REVISED_EVENT: one current event has the original locus, but admitted factual event/anchor values differ.
- SAME_EVENT: one current event has the original locus and equal admitted factual event/anchor values, regardless of latest-bar status or source-only revision.

Locus and equality use Plan 48's exact event/pivot fields; exclude rolling-window
positions and revision-bound digests from factual equality. Search all current
events, not only latest. Resolve the exact referenced pivot; require unique
matching locus and pivot, SWING_HIGH, UPTREND and strictly causal confirmation,
with positions bound to current admitted sessions. Ambiguity/inconsistency is
terminal integrity failure. Presence is representation in this calculation,
not publisher correction lineage or signal validity. No matched event means
NOT_REPRESENTED, never an inferred replacement or invalidation.

Output `causal-setup-event-continuity@v1`: criterion, own runtime identity, both
full observation hashes, both Plan 47 rows, Plan 48 comparison identity/status,
status/reason and optional current representation containing only the same
non-numerical event/pivot fields as Plan 47. Both revisions remain visible.
Canonical sorted compact JSON plus LF, result SHA256, maximum 1 MiB. No prices,
bars, bodies, private paths, limitation payloads or arbitrary diagnostics.

Injected CLI `setup-event-continuity --symbol SYMBOL --storage-root ABSOLUTE_ROOT
--previous-selection-time UTC --current-selection-time UTC --output json` uses
the existing observation port. Validate request before two serial calls with
CURRENT_STRUCTURE; validate returned selector binding; no historical reader or
backdating. Exit 1 UNKNOWN/NON_COMPARABLE/OUTSIDE_WINDOW; 0 other factual outcomes;
2 malformed/integrity/interruption, fixed diagnostics and no partial stdout.
Guarded runnable synthetic demo exercises the real producer and actual CLI;
explicitly identify fixed synthetic dates and deny protected effects.

## First working path, ownership and verification

First: real-producer MATCH replay through SDK/CLI/demo. Then advancing-window
SAME_EVENT while latest screen NO_MATCH, all statuses and matrix rows. Existing
Plan 47/48/public versions and mathematics retain behavior. Later improvements:
validity/expiry/invalidation, persistence/scheduler, multi-stock history,
generation/eligibility/effectiveness and all new sources remain outside scope.

Coordinator sole writer: new continuity module, CLI and source manifest under
research_comparison; focused tests; synthetic example; this Plan, Sprint 35 and
small related documentation. Only mechanically bound manifests may change.
Approved tooling: existing main checkout `.venv` outside this worktree, official
uv only if environment management is needed; no installation or environment copy.
Fallback handbook specification/TDD sections used; no original procedure's
approved content identity established. No nested delegation.

| Risk/adversarial matrix | Acceptance evidence |
| --- | --- |
| Positive/replay | Real producer replay; old event retained in advancing window despite latest NO_MATCH; stable bytes |
| Revision | Same locus factual change REVISED_EVENT; retrieval-only change SAME_EVENT |
| Missing/unknown | NO_BASELINE, UNKNOWN, OUTSIDE_WINDOW, NOT_REPRESENTED remain distinct |
| Integrity/precedence | Wrong type/runtime/diagnostic/packet/anchor/time terminal even combined with unknown or mismatch; duplicate locus terminal |
| Timing/compatibility | Plan 48 stock/mapping/basis/profile/order failures retained; no later evidence backdated |
| Bounds/privacy | Metadata bounds, one stock/two observations, 1 MiB/plus-one; no prices/bodies/paths |
| Interruption/retry/concurrency | Second-call interruption no stdout; repeated/concurrent pure calls identical and no writes |
| Compatibility/rollback | Plan 47/48 regressions and prior-wheel behavior remain; no storage migration |
| Exact candidate | Clean committed base-to-head reviewed independently for domain and security/privacy/provenance; pre/post SHA/tree/clean checks |
| Final gates | Hosted-only full tests/87% coverage/static/sdist/wheel/installed/OCI/security; exact retained receipts |

Lightweight synthetic focused checks and static checks are repair feedback only;
no local full suite, build or container run. Fresh allowance and Actions/Packages
account $0 Stop usage Yes readback precede hosted execution. Preserve failures.
Independent read-only review assignments cover full base-to-candidate and affected
context: functional/domain and security/privacy/provenance, separately identified
actors, no author approval or inherited verdict. Exact identities supplied after
candidate freeze; reviewers return PASS/BLOCKERS with paths, violated acceptance,
checks and limits. If independent capability unavailable, only review-dependent
acceptance pauses. No final completion claim before required evidence.

Impacts: interfaces and operator docs affected; source manifests/provenance
affected; no retained-data migration, deletion, new dependency, rollout effect,
credentials, external acquisition or financial execution. No production utility
or Windows qualification claim. Owner retains funding, release and risk authority.

Goal starts only after Issue, Sprint 35 milestone and Project fields readback.
Pause only affected work for consequential ambiguity, new source/provider,
credentials/protected effect, destructive action, shared mutation, unavailable
evidence, scope expansion, exact-byte review, merge/release or residual risk.
Current authorization covers planning/implementation/verification/review, not
automatic merge/new release, paid usage, local retirement or global settings.
