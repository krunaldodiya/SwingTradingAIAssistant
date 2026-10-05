# Plan 53: external setup interpretation with checked factual binding

Status: accepted bounded Sprint39 specification under the owner's October5,
2026 instruction to start the proposed AI interpretation/no-trade contract
using the same Goal delivery approach. Owner/risk owner: Krunal Dodiya.
Risk R3: public financial-research consumer contract, privacy and provenance.
Base `e585f7951abed166a3dbefefe934c3fa6a0e29d8`.
Governing [Issue260](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/260),
Sprint39 milestone31 and private SwingTradingAIAssistant Delivery Project.

## Necessary question and first working slice

1. Value: check that a caller-supplied external AI response cites the exact admitted candidate pair, preserves all three factual statuses and the descriptive age, and cannot express a structured actionable verdict.
2. Fit: signal-generation consumer boundary; reasoning remains external, while exact factual/provenance binding is deterministic.
3. Risk: a response hides INVALIDATED/UNKNOWN, cites a different revision, converts age to validity, or a validator misleadingly certifies explanation quality or market eligibility.
4. Smallest alternative: check one closed response against the existing Plan52 bundle regenerated from typed observations; no model/provider, new calculation, strategy, score or store.
5. Disposition: accepted, one pair and one external response, pure SDK plus the existing injected CLI pattern and real installed qualification.

Existing Plan52 only hands facts to the consumer. It cannot check a returned
response's exact evidence reference or changed/omitted structured claims.
Manual comparison leaves deterministic binding to an external consumer. This
checker adds enforcement at the return boundary, not independent market
confirmation. Expected coverage is every admitted Plan52 pair, including all
independent inconclusive states. Model accuracy, usefulness, frequency and
returns are unmeasured. No external AI call or evaluation dataset is adopted.

First usable path: caller-authored synthetic response to the real producer's
unchanged upward event with current latest NO_MATCH and descriptive age1;
the actual CLI reads that response once, obtains exactly two serial observations,
and checks it against their unchanged Plan52 result. Complete all matrix rows
after that path, including a rejected false invalidation claim.

## Closed input and deterministic check

SDK `setup_interpretation_request_v1_from_json(raw)` accepts 1–65536 UTF-8 bytes.
Reject duplicate keys at every depth, malformed/nonfinite/overdeep data,
unknown/missing keys and unsupported types/schema; no coercion/defaults.
SDK `check_setup_interpretation_v1(previous, current, response)` revalidates
the entire response before admitted observation/source reads, then calls
unchanged `assemble_setup_evidence_v1` once on exactly two typed observations.
Caller-authored bundle/component JSON never replaces that typed admission.

Response has exactly `schema=external-setup-interpretation-request@v1`,
`evidence_identity_sha256`, `disposition`, `explanation`, `facts`.
All hashes are exact lowercase64-hex strings. Disposition is exactly
`RESEARCH_ONLY` or `NO_TRADE`: a caller's research posture, not a tool-generated
decision or suitability verdict. No BUY/SELL/TRADE/ELIGIBLE/ACTIVE disposition.
Explanation is caller text, 1–2048 Unicode code points and nonblank; reject
surrogates/control characters except LF/tab. It is unverified narrative,
not a source of facts. Success intentionally returns this explicitly supplied
text as untrusted caller content; it never enters diagnostics or tool fact slots.

Facts has exactly `continuity`, `invalidation`, `age`. Each has exactly
`result_identity_sha256`, `status`; age additionally has
`completed_sessions_elapsed` (strict integer0–20 or null, never bool).
Status is an uppercase ASCII token of 1–32 letters/underscores. Matching is
exact against the corresponding regenerated component, including count/null.
Require the exact Plan52 result identity and all three component identities.
Any omission, mismatch or integrity failure is terminal, never UNKNOWN or
a partial check. NO_TRADE is permitted on every factual state; RESEARCH_ONLY
can preserve unknown or INVALIDATED. The checker invents no universal rule
that an optional missing fact, age or absence of contradiction forces a decision.

Output `external-setup-interpretation-check@v1` includes complete Plan52 evidence,
the normalized caller response and its canonical identity, own source-at-rest
runtime identity, and result identity. Explicit labels:
`verification=STRUCTURED_BINDING_ONLY`, `explanation_accuracy=NOT_ASSESSED`,
`external_authorship=CALLER_SUPPLIED_NOT_AUTHENTICATED`,
`actionable_recommendation=NOT_ASSESSED`, `eligibility=NOT_ASSESSED`,
`effectiveness=NOT_ASSESSED`. Do not label response/model quality as approved.
Hashing narrative binds bytes; it does not verify truth or authorship. Full
tool facts remain separate from caller explanation. Fixed limitations explain
these boundaries and prohibit treating this success as trade authorization.
Sorted compact JSON+LF and unsigned SHA256, whole output<=1MiB before any write;
overflow is terminal. No raw market payload or private path is extracted/exported.

## Injected CLI and effects

`setup-interpretation --symbol SYMBOL --storage-root ABSOLUTE_ROOT
--previous-selection-time UTC --current-selection-time UTC
--interpretation-file ABSOLUTE_PRIVATE_JSON --output json` uses the existing
observation port. Validate selectors and absolute paths first; use existing
owner-private bounded no-follow regular-file reader `_read_current_regime_input`
from market_data.cli, retaining its 64KiB/owner/single-link/private-mode and
before/after read rules. Parse/revalidate before observation calls. No new reader
framework or changed shared source. Read once, exactly two serial CURRENT_STRUCTURE
calls, exact selector/result binding, checker once, canonical complete output.
Request/file/parse errors: exit2 `request_invalid`, empty stdout and zero service
calls. Evidence/response-binding/runtime/overflow/interruption failure: exit2
`setup_interpretation_failed`, empty stdout. Success exit1 if Plan52 evidence has
any existing inconclusive status, otherwise0. NO_TRADE does not mean process
failure, and exit0 never certifies eligibility or narrative truth.

Only explicit caller file/package verification and existing injected port reads;
no model/network/provider/credential/hidden-dir/write/storage migration/retry
authority. Pure repeated/concurrent SDK checks stable and input-preserving.
Ordinary source/prior-wheel rollback, no stored response state. A guarded fixed-date
synthetic executable demo labels caller-authored responses; never claims actual
AI reasoning or historical-time acquisition. No real provider call is authorized.

## Safety evidence and remaining interpretation work

Before a future actionable recommendation, its own versioned contract must
establish applicable listing/history, canonical identity/mapping, data quality,
completed-bar/price/corporate-action integrity, liquidity/turnover and event-risk
evidence, including knowledge time and explicit missing/unsupported behavior.
Plan52 structure admission proves only its own admitted factual scope. This slice
identifies those missing safety capabilities; it invents no thresholds and adds
no eligibility gate. Selection/index membership never substitutes for eligibility.
Volume/Relative Strength/Industry/regime/other optional analytical context must
not become an all-feature mandatory conjunction. Actual AI interpretation quality
needs a separately authorized model/prompt/source-bounded evaluation; synthetic
responses and this checker do not prove it. Effectiveness additionally needs
point-in-time/out-of-sample/walk-forward/execution/cost evidence. These later
claims remain explicitly unassessed.

## Frozen adversarial and delivery matrix

| Case | Required observation/evidence |
| --- | --- |
| First working | Actual CLI+SDK, real admitted producer pair, exactly two selector-bound calls, same-event/age1/current NO_MATCH; caller narrative separate |
| Contradiction/missing/revision | INVALIDATED with OBSERVED age, replay0, unknown/null, revised-low/event/window/no-baseline/noncomparable independently preserved; exact component claims checked |
| False claims | Wrong bundle/component/stock/revision hash, omitted/swapped fact, changed status/count/null/bool and unsupported actionable disposition rejected |
| Complete admission/precedence | Revalidate malformed direct/mutated response before observations/runtime; complete producer/source integrity before successful check, including inconclusive state; no authored evidence substitutes |
| Bounds/parser | 1/65536 and plus-one, 2048 and plus-one/blank/control/surrogate narrative, digest/status/count bounds, duplicate keys at every depth/nonfinite/deep/UTF8/schema/type/extra keys |
| Real private reader | Missing/relative/public/wrong-owner/symlink-parent/file/hardlink/nonregular/oversized/mutated-file failure before service; descriptors closed |
| Timing/effects | Exact two serial selectors, wrong question/symbol/time terminal, no network/model/provider/store writes or hidden policy |
| Failure/recovery | Interrupted read/second call/check, stale binding and output overflow emit no stdout/fixed diagnostics; explicit identical retry, concurrent purity; previous contracts/prior wheel usable |
| Privacy/honesty | No raw market body/private argument/path/exception on success or failure; intentional caller explanation is unverified; unsupported claims in free prose cannot be automatically certified/detected |
| Source identity | Closed inventory for new SDK/CLI plus reused market_data.cli reader source; bind unchanged Plan52 runtime; reject missing/extra/substituted manifest entries |
| Installed | Isolated installed SDK+actual injected CLI: same-event, invalidated, replay, unknown, caller NO_TRADE and false-claim rejection; mocks remain feedback only |
| Full delivery | Two independent exact-candidate read-only full reviews, GitGuardian, hosted full selected tests>=87% aggregate branchcoverage/static/sdist/wheel/nativeOCI/adversarial/interruption/priorwheel; normal merge/exact main/private publication/fresh pulls/complete archived receipts/live tracker/localmain |

Coordinator sole writer owns new setup_interpretation SDK/CLI/manifest/tests/demo,
existing Linux verifier/focused tests, Plan53/Sprint39/operator and small roadmap
docs; only mechanically bound source manifests otherwise. No dependency/workflow
change. Use existing approved owner .venv with explicit candidate imports; no
installation/copied environment. Preserve every prior checkout/evidence, no cleanup.
Independent functional/domain and security/privacy/provenance review actors are
fresh, read-only, no nested delegation; full exact revision and complete reports
with pre/post clean SHA/tree/lifecycle proof. Optional telemetry not invented.

Goal begins after Issue/Project/milestone/readback and complete contract freeze.
Owner instruction covers scoped implementation, reviews, normal draft/ready PR,
gated normal merge/private publication/fresh pulls/retention/tracker/localmain
closeout under the same approach; no redundant routine confirmation. Fresh shared
included allowance/storage/reset and account-wide Actions AND Packages $0 paid
budgets/StopusageYes precede every hosted trigger/retry/merge. No automatic rerun,
paid capacity/settings/access/public workaround, local/self-hosted heavy fallback,
direct main push/admin or deletion. Genuine authority/scope/provider/protected/
destructive/conflicting-owner-work/failed-gate/unavailable-evidence/residual-risk
boundaries stop only affected work; provider refusal is INVALID/NO VERDICT.

All eight Plan47 obligations remain distinct. No signal-phase/product completion,
market eligibility/effectiveness, actual AI quality, generation/strategy/expiry
policy, persistence/monitoring/new formula/catalogue/source/provider/history,
broker or money/risk/capital/position expansion. Every Future Issue excluded.
Windows/private_source historical cases and CI retirement separately governed.
