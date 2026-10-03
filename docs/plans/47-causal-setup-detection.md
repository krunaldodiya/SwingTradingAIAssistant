# Plan 47: causal upward structure-break research candidates

Status: accepted bounded implementation contract under the owner's October 3
Sprint 33 planning/implementation instruction; implemented, verification pending.
Owner and risk owner: Krunal Dodiya. R3 public financial-research contract,
causal timing and provenance. Base: `08501889ef7aacab93ac58409209fbe46dfaed10`.
Sprint 33: Causal Setup Detection. Merge/release and protected verification
effects retain separate authority boundaries.

## Signal-phase completion baseline and ordered gaps

This is a finite checklist of required outcomes, not an approved catalogue or
a claim that every detailed policy is already specified. Completion requires
each row's evidence and resolution of its open questions. No percentage or
remaining-sprint count is inferred. The owner's latest exclusion of every
GitHub issue marked Future supersedes older references in Issue 244 and the
October 2 review report. None of those issues is selected, reactivated, or used
indirectly to supply this contract's scope.

| Order | Completion outcome | Delivered foundation and remaining question |
| --- | --- | --- |
| 1 | Versioned, causal, explainable detection through a usable public path | Structure already supplies pivots, trend, BOS/CHoCH; Price Action supplies geometry/previous-close relations. Sprint 33 exposes one existing upward BOS criterion. Later retest/level facts require a demonstrated unmet question, not assumed formulas. |
| 2 | Necessary analytical coverage, with every family explicitly disposed | Volume supplies latest versus prior-20 participation; Relative Strength supplies target versus explicit stock reference. Neither proves liquidity or effectiveness. Technical analysis reuses these facts; what specific missing fact changes a decision? Liquidity adequacy asks whether admitted turnover/history supports the intended research claim; a sweep/reclaim is a distinct hypothesis and remains unselected. Fundamentals asks what source-backed company evidence is necessary for the specific decision, with publication/revision/sector applicability specified before adoption. No Future-issue candidate families are imported. |
| 3 | Explicit generation responsibility and candidate identity | Tool owns factual detection, validation, timing, identities and provenance. External AI explains admitted facts and owns contextual recommendation/no-trade reasoning. It cannot invent facts, recompute OHLC or infer eligibility. First slice identifies one observed candidate; later generation policy requires its own sealed input/output contract. |
| 4 | Confirmation, invalidation, expiry and duplicate semantics | Delivered pivot confirmation precedes the BOS bar. First slice deduplicates identical observations only and does not infer a persistent active signal. What event invalidates a candidate, how long is it valid, and how are correction versus new opportunity distinguished? Those policies remain open for subsequent bounded contracts. |
| 5 | Observable lifecycle across admitted observations | Existing two-observation comparison is in-process evidence only. Freeze accepted transitions, timing, retry/correction and persistence need before durable monitoring. No broker-order or position-management expansion. |
| 6 | Coherent context and safety boundaries | Market/cohort regime, literal Industry participation and bounded event notices exist with independent sources/bases. Absence of a notice is snapshot absence. Optional context stays additive; mandatory eligibility, provenance, completed-bar and price-integrity failures remain closed. What precise safety evidence is required before an actionable recommendation? Until answered, no eligibility claim. |
| 7 | Separate deterministic correctness, AI interpretation and effectiveness evidence | Tests prove contracts, not returns. Evaluate causal decisions with point-in-time evidence, opportunity counts/retention, no-trade frequency, out-of-sample/walk-forward separation and realistic execution, costs/slippage. Protect ambiguous within-bar ordering and source knowledge. Missing evidence blocks only its claim. |
| 8 | Verified phase closeout | Every accepted outcome is delivered or explicitly dispositioned by the owner; required independent reviews, gates, exact revisions and tracker states agree. No silent price-action-only product reduction and no indicator/pattern/SMC catalogue. |

The order is dependency order, not a fixed sprint schedule. Context source
qualification may be planned independently when authorized; no source is
adopted here. Existing safety checks and evaluation costs/slippage remain.
The exhaustive review report and recovered Hindsight export are contextual
discovery only; live merged contracts and the current owner instruction govern.

## Necessary-only evaluation and smallest working slice

1. Value: answer which explicitly supplied stocks exhibit a close-confirmed upward continuation structure break on their latest admitted completed session.
2. Fit: Trade Recommendation Support receives descriptive research candidates; no autonomous buy/sell decision, ranking or actionable recommendation.
3. Risk: falsely relabelling BOS as profitable breakout, backdating knowledge, suppressing candidates with optional context or accepting copied/unadmitted evidence.
4. Smallest alternative: project delivered Structure events; they already answer this exact question. A new level/retest calculation adds no necessary information for it.
5. Accepted: one fixed `LATEST_COMPLETED_UPWARD_BOS@v1` detection path, with `MATCH`, `NO_MATCH`, `UNKNOWN`, causal anchor references and observation-bound identity.

## Closed public path

Add `market-data setup-screen-current --symbol SYMBOL [--symbol SYMBOL ...]
--storage-root ABSOLUTE_OWNER_PRIVATE_ROOT --output json`, and SDK
`screen_setup_current(symbols, storage_root, *, research)` in the existing
market-data application layer. Use 1–10 distinct, valid existing V2 symbol
inputs, requested order preserved. Validate all inputs before effects.
Reject canonical aliases/duplicate identities before returning any result.
No implicit Nifty membership, discovery, ranking or universal cohort filter.

Call the existing V2 producer once per stock, serially, using
`question=CURRENT_STRUCTURE`, `refresh=False`. Existing acquisition, retained
admission, storage authority and deadlines remain intact. This new workflow
does not authorize a real provider call or disclosure. Synthetic verification
does not prove live source availability. No new source, store or dependency.

Validate exact result type, canonical bytes, requested symbol/question and the
producer-bound BharatStock V2 packet before accessing facts. Require the
observed/supported/comparable Structure slot and matching source/price basis.
Only the existing typed Structure calculation is inspected; never recompute
pivots, trends or break rules. Current structure from other profiles is not
silently substituted. Integrity failure is terminal, ahead of missing context.

`MATCH`: an existing event is `BOS`, direction `UP`, and its session equals the
latest admitted session S20. Its referenced high pivot must exist and have
confirmation session strictly earlier than the event. Return the existing
event and pivot identities, pivot/confirmation/event sessions and prior trend;
do not expose raw bars or numerical prices. At most one such event is admitted;
ambiguous multiple events or inconsistent anchors are terminal integrity errors.
`NO_MATCH`: supported comparable Structure with no such latest-session event,
including down BOS, CHoCH, older upward BOS or range/transition.
`UNKNOWN`: missing/unsupported/incomparable required fact or
`INSUFFICIENT_STRUCTURE`; never call insufficient evidence a negative.
Missing Volume, Relative Strength, Industry, market or event context never
suppresses this independently observed detection. This command does not read
or synthesize those facts or classify company eligibility.

Every row preserves canonical identity/mapping, source profile, price basis,
session/schedule, producer/result/source/capture identities, selection time,
evidence knowledge time, availability/support/comparability and reason.
`candidate_identity_sha256` exists only for MATCH and binds the versioned
criterion, canonical identity, source/basis, event/pivot identity and source
revision. It is stable for identical admitted observations, not guaranteed
across rolling windows or corrections; a new observation is not a duplicate
policy or lifecycle transition. Output also binds requested order, complete
canonical order when established, runtime identity, and full result identity.
Joint comparability requires every row's observed fact to share session,
basis, schedule and source profile; independent rows never claim a common
acquisition cutoff. No numerical price, provider body, private path or error
string leaves the projection. Maximum output 1 MiB, canonical sorted compact
JSON plus LF. Exit 0: all rows MATCH/NO_MATCH; 1: at least one UNKNOWN;
2: malformed input/internal or storage integrity failure, no partial JSON.

Confirmation is the delivered pivot and close-confirmed BOS timing, not entry
confirmation. Candidate detection is neither trade eligibility nor advice.
Invalidation, expiry, persistence, outcome tracking, later retest, generation
policy and effectiveness remain later slices and explicitly unimplemented.

## Ownership, execution and evidence

Coordinator is sole writer: new setup screen module/manifest, CLI integration,
focused tests/demo, this Plan, Sprint 33/workflow and related roadmap checkpoints,
plus mechanically affected active runtime manifests. No nested delegation.
Existing V1–V6, watchlist, loss, Structure mathematics and historical identities
retain their semantics. Format sources before refreshing all bound manifests.
Use the existing approved `.venv`; no installation or hidden directory creation
is authorized by this contract. Independent domain and security/provenance
reviewers inspect a committed clean exact base-to-candidate change read-only.
Their fresh assignment identities and full results must be retained; author
self-review never substitutes. Goal starts only after tracker/readback freeze.

First establish actual CLI discriminating red, then the synthetic admitted
producer positive path, negative and insufficient paths. Complete all matrix
rows, focused/static compatibility checks, exact-byte reviews, then applicable
full coverage/build/installed/hosted gates within their required authority.
No test count or synthetic fixture proves market effectiveness or live access.

| Matrix row | Required observable result and prohibited effect | Evidence |
| --- | --- | --- |
| Positive | Latest UP BOS MATCH with earlier confirmed anchor, no prices | Actual CLI/SDK through real synthetic producer admission |
| Negative | Down BOS, CHoCH, older BOS, range return NO_MATCH | Independent synthetic bar expectations |
| Insufficient | Missing or insufficient Structure UNKNOWN, independent row retained | Producer failure/short-window tests |
| Causal | Later pivot confirmation cannot create earlier latest-bar detection; current acquired past bars retain current known time | Prefix/anchor and source-time checks |
| Bounds | 1/10 accepted, 0/11, duplicate/malformed symbols and relative roots rejected before producer | CLI/SDK request tests |
| Identity | Same observation stable; changed source/revision/order changes relevant identity; canonical aliases rejected | Replay/substitution tests |
| Integrity precedence | Forged/mutated objects, wrong question/symbol/basis/anchor or duplicate events terminal, including simultaneous missing fact | Real typed admission mutation tests |
| Optional context | Absent optional features do not change detection | Exact CURRENT_STRUCTURE profile tests |
| Interruption/retry | Interrupted producer yields no partial stdout; identical retained retry stable; no new persistence | CLI interrupted second row/retry tests |
| Concurrency | Pure projection has no shared mutable state; underlying lease exclusion preserved | Concurrent synthetic calls/held-root checks |
| Compatibility/rollback | Existing public versions and installed prior workflow remain usable | Focused regressions, package/source bindings and approved installed checks |
| Privacy/limits | No bars/prices/bodies/paths/errors; output <=1 MiB | Projection and terminal CLI assertions |
| Final gates | Two exact-byte independent verdicts and applicable stable candidate gates | Review package, full/static/build/installed/hosted receipts |

On failure, retain observed evidence, diagnose, apply one bounded in-scope
repair and rerun the failing criterion. Escalate consequential ambiguity or
scope expansion. Stop dependent work at provider/disclosure, installation,
hidden-directory, hosted verification, residual-risk, merge/release or destructive
authority boundaries; continue safe independent preparation. Completion remains
distinct from implementation, review and pre-merge acceptance.
