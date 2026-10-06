# Plan 58: earliest completed post-event range inclusion

Status: accepted bounded Sprint44 specification under the owner's October6,
2026 instruction to continue the next sprint using the same Goal workflow.
Outcome/risk owner: Krunal Dodiya. R3 public financial-research fact, causal
chronology and provenance/privacy. Base `c21ad5c6b4253abc59e3a977f1d06b844fd4be7d`,
tree `415c161a52013c591fc22974b0f95bada19a0fd5`, published Sprint43 main.
Governing Issue and Sprint44 milestone are recorded in the sprint record.

## Necessity and first working slice

1. Value: answer whether any completed bar strictly after the original upward BOS included its original broken high within the current admitted finite window, and identify the earliest such session.
2. Fit: optional descriptive chronology for an external research consumer; neither confirmation nor a required screen.
3. Risk: confuse inclusive low/high with an exact traded tick, successful retest or first lifetime contact; infer missing history or replace the original causal anchor.
4. Smallest alternative: scan the existing admitted21-session Structure window after unchanged Plan56/54/49 admission; no new data source, formula, store or policy.
5. Disposition: accepted after guarded actual-producer synthetic discovery; all trading and broader history additions deferred.

Plan34 discovery: two actual advancing producer pairs both yield SAME_EVENT,
NO_CONTRADICTION_OBSERVED and latest range ENTIRELY_ABOVE. One includes the
original high in the earlier post-event bar; the other does not. Plan56 cannot
answer that distinct question. Receipt: sprint44-evidence/necessity-discovery.json.
Synthetic event session is August25,2026 and admitted post-event sessions are
August26/27. These values are fixed fixtures, not current market observations.
Market occurrence frequency, effectiveness and trading usefulness are unmeasured.
Expected coverage is limited to fully admitted windows retaining the original
pivot/confirmation/event. Operational cost is one bounded scan of at most20
post-event bars; the processing bound is not a stock eligibility rule.

First working: actual producer pair with earlier inclusion but latest entirely
above, pure SDK and actual injected CLI with exactly two selector-bound calls,
same canonical output. Then complete every requirement, criterion and matrix
row below. Later improvements are separately governed and not acceptance debt.

## Frozen requirements

- R1: `observe_setup_level_range_inclusion_v1(previous,current)` takes exactly two typed CurrentStockResearchResultV2 observations and calls unchanged Plan56 once, including complete producer/packet/source/fact/runtime/diagnostic/causal/timing admission before any descriptive outcome.
- R2: OBSERVED resolves the original baseline broken high through unchanged Plan54 `_anchor`; original and currently represented anchors, chronology and complete21-bar current window remain admitted. Never substitute a newer pivot or caller-authored projection.
- R3: Iterate all current admitted source bars strictly after the original event, ordered by completed session. Verify each source session and source-row identity against both adjusted fact and calculation input identity. Require unique chronological complete21-session linkage; altered, missing, ambiguous or out-of-order evidence is terminal.
- R4: Inclusion is exact finite Decimal `low <= original_high <= high`. Event bar is excluded. Report the earliest included completed session in that entire currently admitted post-event sequence, never an intrabar time, exact traded tick, first lifetime contact or successful retest. No tolerance, rounding, threshold or arithmetic-context rule.
- R5: Closed output `causal-setup-level-range-inclusion@v1`, criterion `EARLIEST_COMPLETED_POST_EVENT_RANGE_INCLUSION@v1` inherits complete redacted Plan56 previous/current rows, observation hashes, continuity status/hash and exact original Plan54 witness. Replace range_relation with `inclusion_observed` (bool for OBSERVED, otherwise null), `evaluated_post_event_bars` (ordered session/bar_identity_sha256 pairs, otherwise null), `first_inclusion` (earliest same pair or null), and `latest_range_identity_sha256` (unchanged Plan56 result reference). Own runtime/hash and fixed limitations bind the new fact. OBSERVED reason is COMPLETED_POST_EVENT_RANGE_INCLUSION_EVALUATED. No redundant count or raw price/bar/private/path/body payload.
- R6: REPLAY, NO_LATER_SESSION, NO_BASELINE, UNKNOWN, NON_COMPARABLE, OUTSIDE_WINDOW, NOT_REPRESENTED and REVISED_EVENT inherit exact Plan56 status/reason/witness, with null new factual fields. Complete integrity admission precedes factual states even when replay/unknown/noncomparable. Missing representation never becomes false inclusion.
- R7: New closed SDK/CLI source-at-rest manifest plus unchanged Plan56 transitive runtime closure; missing/extra/changed bound source is terminal. Sorted compact JSON+LF, unsigned SHA256 identity, entire output <=1MiB before output; input immutability, repeat/concurrent pure stability, no writes or mutable cache.
- R8: `setup-level-range-inclusion` injected CLI validates all existing symbol/root/UTC selectors/output before effects, obtains exactly two serial CURRENT_STRUCTURE observations, checks exact returned selectors, computes once and prepares all bytes before write. Malformed request exit2/request_invalid/zero calls/empty stdout; integrity/runtime/interruption/serialization/bounds failure exit2/setup_level_range_inclusion_failed/empty stdout. Unknown/noncomparable/outside/not-represented/revised exit1; other factual states exit0. Exit0 is not trading authorization. No OS stdout transaction guarantee.
- R9: Inclusion remains independent of current close, age and anchored structural invalidation; it may coexist with INVALIDATED. No generation/confirmation/expiry/eligibility/AI recommendation policy. Old evidence-v1/v2/v3, interpretations and all existing SDK/CLI schemas/manifests remain unchanged.
- R10: Guarded actual-producer runnable synthetic demo exercises SDK+injected CLI, event-only exclusion, earlier/later/no/multiple inclusion, inclusive equality, strict nearest decimal neighbors, replay/unknown/same-session, and invalidation independence. Fixed dates explicitly labelled; deny protected effects before producer. Independent original Plan56/54 references regenerated from the same admitted pair; no authored/resealed substitute.
- R11: Append one isolated installed -I qualification map to the existing Linux verifier, strictly checking exact closed nested rows/witness/original references/identities/canonical bytes/facts/exits and installed runtime prefix. All nine prior installed maps and all prior verifier definitions/tests remain verbatim except the smallest added call/receipt field in verify. Preserve all prior source/manifests/public contracts/workflows/dependencies and retained evidence/checkouts.
- R12: Tests first discriminating behavior, complete matrix/focused/static feedback; stable clean committed full candidate, two fresh independent complete R3 domain and security/privacy/provenance reviews with pre/post exact base/head/tree/status and full native results; current blockers resolved before expensive acceptance.
- R13: Full unchanged hosted tests>=87% aggregate branchcoverage/static/sdist/wheel/actual installed/nativeOCI/adversarial/interruption/priorwheel/GitGuardian, exact merge/main admission, immutable private publication/tag+digest fresh pulls/credential logout/full archives/live Issue/Project/milestone/localmain/full-scope audit before Goal completion. No gate omission or approval transfer.

## Acceptance criteria

- A1: The actual producer discriminates earlier inclusion from no inclusion while latest range and continuity/invalidation facts match; usable SDK/CLI equality and exact two selectors.
- A2: Inclusive arithmetic, earliest chronological result, event exclusion and complete admitted source/fact/anchor linkage meet R2–R4.
- A3: Every factual temporal/unknown/unsupported/conflicting state and combined integrity-failure precedence meets R5–R9 without inferred policy.
- A4: Closed metadata-only output/runtime/identity/privacy/bounds, interruption/retry/concurrency/input preservation meet R5–R8.
- A5: Guarded producer demonstration and strict isolated installed qualifier prove exact facts/references/nested closure; malicious resealing rejected, all nine old maps preserved.
- A6: Old source/contracts/manifests/workflows/dependencies/evidence/checkouts remain compatible; source/prior-wheel rollback and nativeOCI proof retained.
- A7: Both complete independent exact-candidate reviews and full unchanged required hosted/security/build/coverage gates pass.
- A8: Normal PR merge, exact main admission/private publication/fresh pulls/full receipts, live tracker and ancestry-safe localmain closeout agree with every original requirement/matrix row before native Goal complete.

## Frozen adversarial matrix

| Row | Observable result, prohibited effects and evidence |
| --- | --- |
| M1 first working/distinct | Actual two-post-event producer earlier/none, latest entirely above in both, exact SDK/CLI bytes/calls; no raw price or policy |
| M2 chronology/arithmetic | Earliest/multiple/latest-only, event excluded, low/high equality and nearest Decimal neighbors/context; independently expected ordered sessions/hashes, no tick inference |
| M3 independence | INVALIDATED can coexist with inclusion; old close/age/range unchanged; no validity/eligibility override |
| M4 temporal semantics | Replay/same-session refresh/no baseline/unknown/revised/not-represented/outside/noncomparable stock/basis/time exact inherited outcomes and null factual fields |
| M5 admission/precedence | Full typed packet/runtime/diagnostic/time/source/stock/anchor corruption terminal even combined unknown/replay/noncomparable; authored report rejected/redacted |
| M6 source/causal linkage | Every post-event source/fact/session/hash, duplicate/order/ambiguous anchor/altered bar/missing original event terminal; original high retained, no newer anchor |
| M7 runtime | Missing/extra/changed new manifest and changed transitive bound runtime terminal for ordinary and unknown/replay; complete source closure |
| M8 CLI/effects | Malformed requests zero calls/empty stdout; exact selectors/two serial calls/once comparison; failure/interruption at first/second/compute/serialization empty stdout and fixed redacted diagnostic |
| M9 bounds/recovery | Existing21/plus-one, whole1MiB exact/plus-one, metadata bounds; explicit retry, concurrency stable/input unchanged; no storage or automatic retry |
| M10 installed/provenance | Actual isolated installed SDK/CLI scenario map; independently regenerated original Plan54/56 references and strict exact nested rows/witness/identities reject resealed mutations at each depth; installed prefix enforced |
| M11 compatibility/rollback | All nine old installed maps/verifier definitions/source/manifests/tests/workflows/evidence/checkouts preserved; nativeOCI source/digest/adversarial/interruption/prior-wheel real gates |
| M12 lifecycle | Two fresh full reviews, GitGuardian/full selected tests87%/static/build, gated merge/main/privatepub/freshpull/completearchives/tracker/localmain/full original13/8/12 audit |

## Ownership, Goal and execution authority

Coordinator is sole writer/integrator/tracker owner, inherited configured
model/effort, optional host telemetry unavailable disclosed. Owned new SDK/CLI/
manifest, focused tests, guarded example, append-only verifier definitions and
small verify call/receipt field plus new focused verifier tests, this Plan,
Sprint44/operator docs and small related roadmap checkpoints. No nested
delegation. Two fresh independent read-only reviewers of stable complete
base-to-candidate; asynchronous dispatch, foreground returns, native completion
event and authoritative lifecycle/full result capture, no polling/callback.

Handbook primary typed architecture/contract, selected governance/TDD/GCS/
goal/delegation/handoff sections and requirements-planning fallback apply.
Trusted original procedure identity not established; no alternate provider
activation. Existing approved owner .venv outside disposable worktrees,
candidate imports, no installs/environment copy/heavy local qualification.
Preserve all11 prior checkouts and all Sprint43 indexed evidence; no deletion.
Ordinary source/prior wheel recovery, no data migration.

After exact Plan/Issue/private Project/milestone/fields/context readback start
persistent Goal. Standing owner direction covers routine scoped implementation,
repair, reviews, draft/ready PR, normal gated merge, exact main/private
publication/fresh pulls/archives/tracker/localmain closeout without another
approval. One initial stable reviewed Sprint44 hosted qualification permitted;
no automatic rerun. Current Issue250 hosted-only authority and retained accepted
90-minute compact diagnostic workflow supersede historical self-hosted prose
for this slice; preserve exact current workflows (90 quality/main,60 publication).
Fresh whole-account included capacity/storage/reset, Actions AND Packages$0
StopusageYes, no-active/no-error inventory and >=300-minute reserve before every
hosted trigger/merge. No paid/public/settings/access/admin/direct-main/deletion/
heavy-local/self-hosted workaround, longer caps or weakened checks. Diagnose
failures honestly and stop only dependent effects at genuine scope/provider/
credential/protected/destructive/conflicting-owner-work/unavailable-window/
unaccepted-residual-risk boundaries; provider refusal INVALID/NO VERDICT, no bypass.

All eight Plan47 signal-phase obligations remain distinct and incomplete.
Deferred: v4 coherent consumer bundle/checker unless separately proven needed,
any lifetime history/tick/retest/confirmation/expiry/eligibility/monitoring/store,
new source/model/provider/strategy, Future issues, effectiveness, broker and
money/risk/capital/position expansion. Windows/private_source historical cases
and local CI retirement remain separately governed. No countdown or phase
completion claim follows from this bounded range fact.
