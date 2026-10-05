# Plan 52: coherent candidate evidence for external AI

Status: accepted bounded specification under the owner's October 5, 2026
Sprint 38 direction and explicit delegation to select the best next signal slice.
Outcome/risk owner: Krunal Dodiya. Risk R3: public financial-research evidence,
causal provenance and interpretation. Base:
`3c79333f6073017e4d27eadb39bc553369f5d793`.

Governing Issue: [#258](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/258).

## Necessity and smallest working slice

1. Value: give the consuming AI continuity, structural contradiction and session age for exactly the same admitted observation pair before it interprets a candidate.
2. Fit: deterministic candidate-generation evidence handoff; contextual recommendation/no-trade remains the external AI's responsibility, with eligibility and effectiveness unassessed.
3. Risk: separate commands can obtain different observation revisions, or age/continuity can be mistaken for continued validity despite observed contradiction.
4. Smallest alternative: compose delivered Plans49–51 on two typed observations obtained once; preserve their facts and limits rather than invent a formula, filter, expiry policy or store.
5. Disposition: accepted, one stock/two observations through a pure SDK and the existing injected CLI pattern; no new transport, producer, source, provider or analytical rule.

Plan34 admission: the unmet consumer question is which lifecycle facts belong
to one exact evidence pair. Existing commands each call the observation service
twice; separately invoking them does not ensure the same pair. Checking hashes
manually leaves deterministic consistency admission to the AI. A single bundle
binds the inputs and all component identities, while two service calls suffice.
This adds coherent provenance, not independent analytical confirmation. Expected
coverage is exactly the existing finite 21-session contracts, including explicit
unknowns. Frequency, usefulness, returns and cost savings are unmeasured. Merely
combining already-consistent reports would add no new market information; the
need is obtaining and admitting a consistent pair before any consumer handoff.

Expiry/persistence/monitoring lack an accepted policy or need; liquidity adequacy
requires its own evidence-backed applicability and thresholds; later-bar
confirmation needs a distinct named research decision. Those alternatives are
deferred. No Future Issue supplies scope. No generation/recommendation policy
or AI implementation is admitted by this evidence handoff.

## Frozen observable contract

Pure SDK `assemble_setup_evidence_v1(previous, current)` accepts exactly two
typed CURRENT_STRUCTURE `CurrentStockResearchResultV2` observations, never
caller-authored candidate or component JSON. Invoke the existing Plan49
continuity, Plan50 invalidation and Plan51 age functions on that same pair.
Retain their complete admission, input bounds, integrity-before-semantics,
temporal/deadline/mapping/source/basis and source-at-rest controls. Each component
keeps its version, complete result, reason, identities and explicit limitations.
No underlying Plan31/47–51 mathematics, output bytes or semantics change.

Before producing the bundle, require identical previous/current observation
hashes and projected rows across all three components, and require both age and
invalidation to reference the exact included continuity result identity.
Mismatch is terminal integrity failure, never partial evidence or UNKNOWN.
The SDK owns deterministic binding; the AI does not recompute market facts,
mint provenance, override integrity failure or infer validity/eligibility.
An INVALIDATED component may coexist with a descriptive OBSERVED age. Neither
fact overrides the other. Preserve all inconclusive outcomes independently.

Output `causal-setup-evidence@v1`, detection criterion from Plan47, own runtime
identity, both full observation identities and exactly three components named
`continuity`, `invalidation`, `age`. No aggregate active/valid/tradable/readiness
status or synthesized market verdict. Fixed consumer-boundary limitations state
that contextual recommendation/no-trade belongs to the external AI, actionable
recommendation/eligibility/effectiveness are not assessed, optional analytical
facts must not become hidden hard filters, and evidence does not authorize
orders. Canonical sorted compact JSON plus LF, SHA256 over the unsigned bundle,
maximum 1MiB across the whole bundle. Reject overflow atomically. No raw numerical
price/volume/bar/body/path/arbitrary diagnostic payload is exported.

Injected CLI `setup-evidence --symbol SYMBOL --storage-root ABSOLUTE_ROOT
--previous-selection-time UTC --current-selection-time UTC --output json`
uses the existing observation port. Validate all request fields before effects;
perform exactly two serial CURRENT_STRUCTURE calls with those selectors; verify
selector/result binding; assemble once. No automatic historical reader,
backdating or real provider effect is authorized. Exit1 if any component has an
inconclusive status (continuity UNKNOWN/NON_COMPARABLE/OUTSIDE_WINDOW; invalidation
additionally NOT_REPRESENTED/REVISED_EVIDENCE; age additionally
NOT_REPRESENTED/REVISED_EVENT); exit0 otherwise, including factual replay,
no-baseline and observed contradiction. Exit2 malformed/integrity/interruption,
fixed `request_invalid` or `setup_evidence_failed` diagnostic and no partial stdout.
Exit0 is not an actionable or eligible candidate. A guarded real-producer
synthetic demo labels its fixed dates and denies protected effects.

## Ownership, sequence and complete acceptance

Coordinator is sole source writer/integration/tracker owner. Owned files:
new `research_comparison/setup_evidence.py`, CLI and manifest; focused tests;
`examples/causal_setup_evidence_demo.py`; existing Linux distribution verifier
and its focused tests; Plan52/Sprint38/sprint index/workflow and small related
roadmap/operator docs. Only mechanically bound manifests may otherwise change.
No dependency, retained-data migration, source adoption or global tooling.
Use the approved owner-checkout .venv outside the managed isolated worktree,
explicitly bind candidate imports. Official uv only when needed/authorized.
Preserve owner and all retained sprint checkouts and receipts; no cleanup.

First establish discriminating actual CLI RED against the predecessor adapter;
then advancing unchanged-event real-producer SDK/CLI with exactly two calls.
Complete every matrix row before clean committed candidate freeze. Installed
acceptance adds isolated installed SDK/actual CLI same-event age1,
INVALIDATED with age still present, replay0 and unknown/exit1. Existing native,
OCI, source/digest/adversarial/interruption and prior-wheel rollback gates stay.
Rollback is ordinary source/prior-wheel rollback with no stored bundle state.

| Risk/adversarial matrix | Observable result/prohibited effect | Evidence |
| --- | --- | --- |
| Coherent positive | Three component hashes/rows refer to same pair; continuity SAME_EVENT, age1, current latest NO_MATCH | Real producer SDK/actual CLI, exactly two calls |
| Contradiction | INVALIDATED remains visible alongside independently observed age; no valid/active verdict | Anchored real-producer example and tests |
| Replay/revision | Replay0, source-only refresh, factual event/low revision retain distinct component semantics | Admitted pair tests |
| Missing/unsupported | No baseline, unknown, window loss, absence, incompatible schedule/mapping remain independent | Real producer and branch adversaries |
| Integrity/precedence | Complete malformed/runtime/packet/diagnostic/anchor/time validation terminal even with unknown; mismatched component binding terminal | Mutation/substitution and combined-failure tests |
| Bounds/privacy | One stock/two bounded observations, 21-session source, metadata/1MiB exact and plus-one; malformed selectors before effects, no private payload | SDK/CLI bounds and output assertions |
| Timing | Same selectors on all components, deadline/knowledge order intact; no historical-time acquisition claim | Temporal/selector tests |
| Interruption/retry/concurrency | Interrupted second call or later component emits no stdout; repeated/concurrent pure calls stable without writes/input mutation | CLI and pure SDK tests |
| Compatibility/recovery | Existing Plan47–51/public versions and manifests unchanged except necessary mechanical bindings; prior-wheel behavior | Focused regressions and hosted rollback |
| Installed | Real isolated installed SDK/CLI same-event, invalidated, replay, unknown, correct identities and exits | Existing hosted Linux verifier extended, mock feedback separate |
| Exact review | Two fresh independent read-only full base-to-clean-committed-candidate domain and security/privacy/provenance verdicts, complete results/pre-post SHA/tree/status | Separate native review actors, no nested delegation |
| Delivery | Full selected tests/87% aggregate branch coverage/static/sdist/wheel/installed/native/OCI/GitGuardian; normal merge/exact main admission/private publication/fresh pulls | Retained hosted run/attempt/job/log/receipt proof, live tracker closeout |

R3 public interface/provenance/operator documentation and installed release
evidence are affected. Data migration/retention/deletion, new source/credentials,
funding/settings, storage authority, analytical rules and broker effects are
not affected. Handbook core, requirements/specification fallback and TDD/release
controls apply; no trusted original procedure content identity established.
Reviewers inherit host settings, remain read-only, cannot delegate, and return
complete exact-candidate verdicts with checks/limits. Author review is not
independent. Safety refusals remain INVALID/NO VERDICT and are never bypassed.

Goal begins only after Issue, Sprint38 milestone and private Delivery Project
fields readback. Owner authority covers bounded implementation/review/draft PR,
normal merge after gates, exact main admission/private publication/fresh pulls,
receipts and Issue/Project/milestone/local-main closeout. No redundant approval.
Fresh shared included allowance/storage/reset and account-wide Actions AND
Packages $0 paid-usage Stop usage Yes precede every hosted trigger/retry/merge.
Unknown/exhausted allowance blocks execution, never permits paid capacity,
visibility/settings/scope changes, automatic reruns or local/self-hosted heavy
acceptance. Retain complete evidence before expiry. Lightweight focused/static
local feedback only. Stop affected work at real scope/source/provider/credential/
protected/destructive/conflicting-owner-work/failed-gate/unavailable-evidence or
unaccepted residual-risk boundaries. No --admin or direct main push.

All eight Plan47 obligations remain distinct: detection, necessary analytical
coverage, generation responsibility/identity, confirmation/invalidation/expiry/
duplicates, lifecycle, coherent context/safety, deterministic correctness/AI
interpretation/effectiveness and phase closeout. This slice advances coherent
generation evidence only. No phase/product completion, effectiveness, eligibility,
expiry, persistence/monitoring, new formula/catalogue/provider, broader history,
broker or money/risk/capital/position work. Windows, four private_source
historical cases and CI retirement remain separate. Sprint37's live closeout is
verified; its pre-delivery prose remains historical and is not reopened.
