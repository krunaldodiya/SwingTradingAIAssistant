# Plan 54: latest completed close versus the original broken high

Status: accepted bounded Sprint40 specification under the owner's October5,
2026 instruction to continue the next sprint with the same Goal approach,
without redundant approvals. Outcome/risk owner: Krunal Dodiya. R3 public
financial-research fact, causal price-basis and source integrity. Base
`5f2eacc2f448c3d3ff5df017ee787a6099e8c075`, exact published Sprint39 main.
Sprint40 milestone32; [Issue262](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/262).

## Necessary question and first working slice

1. Value: distinguish whether the latest admitted completed close is above, exactly at, or below the causally confirmed high broken by the original upward BOS.
2. Fit: optional descriptive level context for swing candidate interpretation; neither a mandatory screen nor entry/eligibility/validity confirmation.
3. Risk: replace the original level with a newer pivot, infer retention from absence of invalidation, apply arbitrary tolerance or hindsight, or expose raw prices/private material.
4. Smallest alternative: compare one admitted latest close directly to the original unchanged broken high using the existing typed producer pair and Plan49 admission; no pattern, tolerance, new source, store or reconstruction.
5. Disposition: accepted after discriminating real-producer synthetic discovery; all other level/retest/strategy additions deferred.

Plan34 gap evidence: the existing guarded real producer yields two advancing
pairs with SAME_EVENT, NO_CONTRADICTION_OBSERVED, OBSERVED age1, yet their latest
closes are respectively above and below the original broken high. Those
lifecycle statuses/count do not answer this question. Latest detection NO_MATCH
also does not encode this relation. The external AI cannot read raw bars or
perform this market calculation. This slice adds a distinct price-level fact;
it does not claim independent confirmation, effectiveness or observed market
frequency. Discovery receipt: sprint40-evidence/necessity-discovery.json.

First working path: advancing same-event real-producer pair, exact original
broken high, latest close ABOVE, pure SDK plus actual injected CLI obtaining
the pair exactly once. Complete the following matrix before acceptance.

## Closed SDK contract

`observe_setup_level_v1(previous, current)` accepts exactly two existing typed
CurrentStockResearchResultV2 observations. Call unchanged
`observe_setup_event_continuity_v1` once, admitting complete producer packets,
canonical stocks/mappings, source profiles/bases, raw source-bar linkage,
causality, diagnostics, timing and runtime identities before reading prices.
No caller-authored projection substitutes for typed admission. New closed
source-at-rest manifest binds this SDK and its CLI and the unchanged continuity
runtime closure. Missing/extra/substituted source is terminal even when evidence
is inconclusive.

Output `causal-setup-level@v1`, criterion
`LATEST_COMPLETED_CLOSE_VS_ORIGINAL_BROKEN_HIGH@v1` includes complete redacted
previous/current Plan49 rows, both observation identities, continuity status
and result identity, new runtime identity, status/reason, relation, witness and
limitations. Sorted compact JSON plus LF, unsigned SHA256 result identity,
whole output at most1MiB before any write. No raw bars, numerical prices/volume,
provider bodies, paths or arbitrary diagnostics.

Only SAME_EVENT is eligible for a later-close comparison. Resolve the exact
original baseline event and its original broken SWING_HIGH, and the current
unchanged represented event/high, by the admitted identities. Never select the
latest/newest unrelated pivot. Require unique causal anchors and original
broken level equal to the admitted high price. Read the last bar of current
MARKET_STRUCTURE's admitted21-session source window; require its session matches
the admitted current row/source and its bar identity matches the admitted
calculation's final input identity. Raw bars stay inside the deterministic tool.

When current last session is strictly later than original event session,
status=OBSERVED, reason=LATEST_COMPLETED_CLOSE_COMPARED_WITH_ORIGINAL_BROKEN_HIGH;
relation is ABOVE if close>original high, AT if equal, BELOW if less. Compare
finite admitted Decimals exactly, without arithmetic, rounding, tolerance,
percent threshold or Decimal-context dependence. Witness binds original event
session, original high pivot/confirmation sessions, original and current
represented event/high identities, current completed session, final admitted
bar identity, and original/current feature source/capture/schedule identities
already present in the rows. No intrabar touch/path or retest claim.

A source-only same-session refresh with SAME_EVENT yields NO_LATER_SESSION,
reason=NO_COMPLETED_SESSION_AFTER_ORIGINAL_EVENT, relation/witness null. REPLAY
preserves REPLAY and its reason, relation/witness null. UNKNOWN, NO_BASELINE,
NON_COMPARABLE, OUTSIDE_WINDOW, NOT_REPRESENTED, REVISED_EVENT retain exact
Plan49 status/reason and null relation/witness; never substitute a revised
level or infer that missing evidence is BELOW. All complete upstream admission
and integrity failures precede those factual outcomes. An impossible earlier
current bar, missing/ambiguous admitted anchors, broken level mismatch or
bar/session/identity inconsistency is terminal, not unknown.

ABOVE never establishes validity, eligibility, confirmation, expiry, profit or
trade authorization. BELOW does not replace Plan50's independently specified
anchored structural invalidation. Plan50 INVALIDATED may coexist with a level
relation; neither overrides the other. Plans47–53 and every previous public
contract/manifest remain unchanged. No automatic integration into Plan52 or
Plan53 v1; changing their closed schemas requires a separate contract.

## Injected CLI and effects

`setup-level --symbol SYMBOL --storage-root ABSOLUTE_ROOT
--previous-selection-time UTC --current-selection-time UTC --output json`
uses the established injected observation port. Validate all request fields
before effects, then exactly two serial CURRENT_STRUCTURE calls with exact
selectors; compare once and prepare bounded complete bytes before output.
No historical reader, automatic refresh/retry, provider adoption/acquisition,
network/model/credentials/private response-file read or persistent state.
Existing port authority remains its caller's responsibility.

Malformed selector/input: exit2, fixed request_invalid, empty stdout and zero
calls. Evidence/runtime/integrity/interruption/overflow: exit2, fixed
setup_level_failed, no partial stdout. Success exit1 for UNKNOWN/NON_COMPARABLE/
OUTSIDE_WINDOW/NOT_REPRESENTED/REVISED_EVENT; exit0 for OBSERVED, REPLAY,
NO_BASELINE or NO_LATER_SESSION. Exit0 never certifies an actionable candidate.
Retry is explicitly caller-driven; pure SDK repeats/concurrent calls stable,
input-preserving, no writes. Ordinary source/prior-wheel rollback, no migration.

## Frozen adversarial and delivery matrix

| Case | Required behavior and evidence |
| --- | --- |
| First working | Real producer ABOVE and actual SDK/CLI canonical equality, exactly two selector-bound calls/once comparison |
| Distinct relation | Real producer BELOW while same-event/no-contradiction/age1 persists; exact AT; arbitrary newer pivot cannot replace original high |
| Independence | BELOW is not INVALIDATED; structural INVALIDATED remains its own fact; no hidden trade/no-trade or confirmation policy |
| Temporal states | Replay, source-only same-session refresh, later completed session, current latest NO_MATCH, no baseline, unknown, revised event/high, missing representation/window and noncomparable stock/basis/time remain distinct |
| Admission/precedence | Typed/full producer packet/runtime/diagnostic/mapping/price/source/bar/anchor/time integrity terminal even with unknown; no authored report substitute |
| Causal/session integrity | Exact confirmed original high and represented unchanged event, last admitted completed bar/session/identity; missing or ambiguous high/event, altered source/close/bar and impossible earlier session fail closed |
| Bounds/privacy | One stock/two observations, existing21 bars; metadata and whole1MiB exact/plus-one; no prices/raw/private/path/error leak; malformed requests before effects |
| Arithmetic | Strict ABOVE/AT/BELOW Decimals, nearest distinct decimal values and changed Decimal context; no tolerance/rounding/threshold |
| Recovery/concurrency | Interrupted first/second observation/comparison/serialization no stdout; explicit retry stable, concurrent pure result stable, input bytes unchanged; prior-wheel rollback usable |
| Source/compatibility | Closed new SDK/CLI manifest plus unchanged Plan49 source closure; all existing Plan47–53/public interfaces and five installed maps preserved |
| Installed | Isolated -I installed SDK and actual CLI ABOVE/AT/BELOW, replay and unknown; SDK/CLI canonical equality with exact facts/identities/exits; mocks are feedback only |
| Full lifecycle | Two independent complete exact-candidate domain and security/privacy/provenance reviews, GitGuardian, full hosted selected tests>=87% aggregate branchcoverage/static/sdist/wheel/nativeOCI/adversarial/source/digest/interruption/prior-wheel; normal merge/exact main/private publication/fresh pulls/full archives/live tracker/localmain |

Coordinator sole writer/integration/tracker owner: new setup_level SDK/CLI/
manifest, focused tests and guarded real-producer demo, existing Linux verifier
and its focused tests, this Plan/Sprint40/operator docs and small related roadmap
checkpoints. No dependency/workflow/shared producer or old manifest change.
Existing approved owner-checkout .venv outside worktrees, explicit candidate
imports; no installations/copied environments. Admit regular source file modes
only within this new owned checkout as necessary; preserve all8initial checkouts
and all earlier evidence. No cleanup or deletion.

Independent reviewers are fresh read-only actors for a clean committed full
base-to-candidate; exact pre/post SHA/tree/status, full reports, no nested
agents. Coordinator uses inherited configured model/effort; optional observed
telemetry unavailable stays disclosed. Handbook primary TDD, scoped contract/
governance/release controls and planning fallback apply. Trusted original
provider content identity was not established from available skill descriptors.
Affected: descriptive public consumer contract, provenance/privacy, operator
instructions and installed/release evidence. Not affected: stored market data,
source/provider authority, models, dependencies, hardware/settings/funding,
account access or historical identities. No migration; source/prior wheel
recovery. The discovered gap is synthetic; market frequency/value unmeasured.

## Authority, Goal and full closeout

After governing Issue/Project/milestone/specification/matrix readback, use the
persistent Goal. Latest owner instruction delegates scoped routine decisions,
implementation/repair, reviews, normal draft/ready PR, gated normal merge,
private publication/fresh pulls/archives and tracker/localmain closeout without
another approval request. Existing project and hosted-only safeguards remain.
Fresh included shared-account minutes/storage/reset and account-wide Actions
AND Packages $0 paid budgets/StopusageYes precede every hosted trigger/retry/
merge; complete all gates, no blind/automatic rerun, paid/public/access/settings
workaround, heavy local/self-hosted fallback, admin or direct-main push.
Diagnose genuine failed gates and repair within scope; preserve failures and
renew affected exact reviews/evidence. Genuine provider safety/credential/
unavailable evidence/conflicting owner work/higher-authority conditions stop
only dependent effects; do not fabricate success or enlarge scope.

All8Plan47 phase obligations remain distinct. This completes only the bounded
level fact, not overall signal phase. No retest/intrabar/level catalogue,
strategy/generation/expiry/duplicate/persistence/monitoring, model/provider,
eligibility/safety thresholds, effectiveness, Future Issue, broker or money/
risk/capital/position expansion. Windows/private_source historical cases and
local CI retirement remain separately governed. Full receipts/Issue/Project/
milestone32/localmain must agree before Goal complete.
