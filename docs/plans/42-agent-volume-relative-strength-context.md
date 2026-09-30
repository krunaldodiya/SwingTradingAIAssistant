# Plan 42: agent Volume and Relative Strength context

Status: owner-accepted direction; frozen first implementation contract, not delivered.
Owner and risk owner: Krunal Dodiya. Sprint 28 / [#235](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/235). Risk R3.
Authority: on September 30, 2026 the owner accepted the recommended integration
of the existing Volume and Relative Strength facts into the agent research report.
Baseline: `ff872671d2ce52dd41bd45a6eef73d7f4133b7ea`.
Plans 34, 38, 39 and 41 govern reused research and evidence boundaries.

## Outcome and necessary-only admission

1. Value: the external agent can consume delivered Volume and reference-relative price facts beside the stock research it already receives.
2. Fit: additive factual consumer integration; no new analytical family or trading rule.
3. Risk: identity, date, basis or provenance substitution; optional context becoming a hidden gate; private evidence disclosure.
4. Smallest alternative: call existing retained producer services and project their results with independent source/time labels; do not recalculate from raw bars or build another archive.
5. Disposition: accepted for this report integration. Strategy/risk, screening filters, rankings, provider acquisition and historical effectiveness remain deferred.

The first working path is one stock and one distinct explicit reference, through
the real CLI and existing synthetic retained producer fixtures. Complete all
bounds and failure paths below before acceptance. No live provider execution,
credential access or owner-private evidence execution is authorized by this plan.

## Interface and input contract

Add opt-in `market-data research-run-current --contract-version v5`, wrapping the
existing V4 report. V1–V4 retain schemas, defaults, calculations and exit behavior.
V5 keeps the existing V4 cohort options and adds required
`--analysis-input-file ABSOLUTE_PRIVATE_JSON`. No new input schema: the file is
exactly the closed Plan-41 `current-relative-strength-request@v1` request, parsed
by its existing parser. It supplies 1–10 ordered research targets, one distinct
explicit reference, canonical identity/validity, official schedule identity,
selection time and admission deadline. Target symbols must equal `--symbol`
exactly in order, with no inferred union, dropped member, alias or reordering.
The reference is not an official index or silently selected cohort benchmark.

Reuse the existing no-follow, owner-private regular-file reader, maximum 64 KiB;
reject public, linked, missing, malformed or oversized files and wrong versions,
unknown/duplicate keys, invalid types, duplicate targets, target/reference overlap,
invalid intervals and target-count/order mismatches before research/storage or
provider effects. V1–V4 reject the new option before effects. Direct SDK calls
reconstruct and validate the typed request, symbols, root and inherited cohort
inputs too. No public SDK parameter accepts precomputed context JSON as evidence.

Use an additive `market_data/agent_analysis_context.py` SDK orchestrator, following
V4's existing dependency injection for tests. Production always invokes the real
Plan-39 and Plan-41 retained services. Construct the Volume request from precisely
the same ordered targets, schedule, selection and deadline as the RS request;
Volume does not include the reference. Producer admission remains authoritative.

## Observation, identity and output

Run existing V4 research then Volume and Relative Strength with the validated
request. Validate request liveness before V4 effects, across each stage and
immediately before return/emission. Reuse the existing monotonic invocation
control: do not clamp time, backdate selection, cross deadline/IST rollover or
hide clock regression between producers. The original request's 30-minute bound
is an overall deadline for V5, not a renewed allowance for each stage.

Return `agent-current-research-run@v5`. Preserve the V4 report and add
`analysis_context` containing the complete bounded producer results under
`volume` and `relative_strength`, request identity, explicit observation labels
and `jointly_comparable_with_stock_dossiers=false`. Both producer results retain
their own source/basis, latest 21 completed sessions, original cutoff/knowledge,
request/runtime/result/calculation and mapping/partition/screen identities,
ordered members, reference role and exact arithmetic. Never copy the stock's
one-session fallback date into these current retained producer results.

Each stock dossier adds `volume_context` and `relative_strength_context` with
that target's producer outcome and a pointer to its batch result. Canonical
ISIN/exchange/effective-symbol must match the request and real producer result.
A non-null dossier canonical identity must match too; mismatch is terminal,
not a missing-evidence result. When the dossier has no canonical identity,
independently producer-admitted analysis may remain visible under its own
canonical identity and an explicit `DOSSIER_IDENTITY_UNAVAILABLE` alignment;
it must not claim that missing price research was admitted. A matching identity
uses `CANONICAL_IDENTITY_MATCH`, which still does not prove common date/basis.
Preserve every target and exact order even when either calculation is unavailable.

No raw bar arrays, endpoint prices, source bodies, paths, private exception text,
credentials or new disclosure permission. Existing V4/NSE owner-private limits
apply to the whole report. Bound final canonical JSON to 4 MiB before emission
(two existing 1-MiB producer limits plus bounded V4 and projections); test bound
and plus one. Bind the new orchestrator into runtime source manifests and expose
a V5 result identity over its canonical report without the result identity field.

## Failure precedence and side effects

Input validation precedes all effects. Invalid user input returns exit 2 with a
sanitized input diagnostic. Runtime/source integrity, unsafe/held/replaced root,
corrupt retained evidence, provenance/identity substitution, unexpected failures,
interruption and liveness failure are terminal with no partial JSON (exit 2;
interrupt propagation may retain inherited process semantics). Optional absence
never catches these failures. Execute both analysis services even if the first
returns missing evidence, so missing Volume cannot hide RS evidence corruption.

After complete input, liveness and runtime validation, use V4's existing root
admission helper to admit the existing owner-private invocation root, capture
its identity while that lease is held, then release the lease before entering
unchanged V4. Missing roots remain terminal as in real V4; the helper does not
create a root. It may initialize the existing lease file in an admitted empty
root. Do not adopt a different root after V4 returns. Preserve V4's internal
guards. Across V4, subsequent read-only analysis stages and final emission the
pinned root authority must remain unchanged. No storage format or lock protocol
is added. Each producer retains its existing lease and exact final evidence recheck.
These are separate observations,
not a new atomic cross-producer snapshot or evidence-at-emission attestation.
No new lock protocol, receipt system, acquisition, retry, repair or persistence.
A held root is terminal when an invocation attempts required lease admission or
reading. A legitimate later lease acquired after completed producer observations
does not retroactively invalidate them; final checks bind root identity and
liveness, not continuous exclusive ownership through stdout emission.

Closed producer absence/unsupported reasons stay local and explicit. Missing RS
reference withholds comparisons but not Volume or independent price facts.
A missing target affects only its context. Preserve zero-baseline Volume and
valid EQUAL relations distinctly. Optional context does not change price-based
exit 0/1, research readiness or the inherited price-only `jointly_comparable`.
Label its scope explicitly in V5; never imply that true covers analysis context.
Expose analysis readiness separately using producer states. No trade eligibility.
An explicit retry revalidates retained evidence; existing immutable V4 reuse
remains governed by Plan 38. Rollback removes the additive V5 entry point and
leaves stores and V1–V4 usable.

## Frozen adversarial acceptance matrix

| Case | Observable result and prohibited effect | Method |
| --- | --- | --- |
| One target/reference with actual retained raw and screen evidence | Exact existing Volume and RS facts reach SDK and CLI with correct provenance; no additional provider calls or retained writes from analysis | Real producer fixtures and actual CLI dispatch; compare producer identities/arithmetic and file inventories |
| 1/10/0/11 targets; request order/duplicates/reference overlap; SDK mutation | Valid bounds work, invalid inputs fail before research effects | Parser/SDK/CLI tests with effect sentinels |
| Missing/public/link/oversize/duplicate/unknown/nonfinite request, legacy option | Sanitized exit 2, no stdout/provider/storage effect | Existing reader plus new CLI boundary tests |
| Missing calendar/mapping/target/screen/reference, zero Volume baseline, exact EQUAL | Typed local context remains; independent facts survive; unchanged price exit | Real retained cases plus targeted orchestration cases |
| Different sessions, one-session price fallback, source/basis/knowledge times | Separate source dates/bases remain visible, no joint snapshot claim or rewritten cutoff | Mixed producer/dossier fixtures |
| Canonical request/result/dossier identity or ordering mismatch | Terminal no partial JSON, no attachment to another stock | Adversarial dependency outputs and real mapping checks |
| Missing first context plus corrupt second evidence | Integrity failure wins, no partial report | Real retained corruption and orchestration fault tests |
| Deadline before V4, during stages, before return/CLI emission; rollover/regression | Terminal stop, no later effects or output | Controlled clock and emission-boundary tests |
| Held/replaced root, interrupted producer, explicit retry | No successful partial output; safe retry, original evidence intact | Temporary roots, injected boundaries and inventories |
| 4-MiB output and plus one; privacy | Bound enforced before emission; excluded private fields absent | Serialization edge and private-marker tests |
| V1–V4, standalone producers, all bound source manifests | Existing public behavior preserved; manifest identities updated truthfully | Compatibility tests, full manifest audit, installed wheel smoke |
| Stable candidate | Required full gates and two independent reviews on exact clean committed bytes | Functional/domain and security/privacy/provenance reports; full self-hosted validation and retained receipts |

Synthetic tests do not establish provider availability, real-market facts,
strategy usefulness or effectiveness. No market-window gate is needed for this
consumer wiring; no live capture is part of acceptance.

## Ownership, execution and deferred work

Coordinator owns this plan, tracker, review assignments, integration, publication
routing and final evidence. One native Codex implementation executor owns
`market_data/agent_analysis_context.py`, related CLI wiring, directly/transitively
bound runtime manifests, targeted new behavior tests and
`docs/workflows/agent-current-research-run.md`. Calculations and standalone
producer contracts are not changed. No nested delegation or other checkout edits.
Requested model/effort inherit host defaults; optional host telemetry is not
invented. Host permits routine scoped filesystem/command work. The managed
worktree helper failed with `Git is unavailable`; shell Git created isolated
`codex/sprint28-agent-context` from the verified baseline. PR #233's checkout is
untouched and #234 retains memory-migration ownership.

Two fresh native read-only reviewers will independently own functional/domain
and security/privacy/provenance review after the implementation assignment ends
and the candidate is committed. Neither authors it. Coordinator owns full gates;
executor owns discriminating red/green tests, focused static checks and complete
implementation evidence. Stop only dependent work for authority conflicts,
consequential ambiguity, source adoption, shared mutation, scope expansion or
release gates. Keep review bytes immutable. Merge/release require their current
authority; no acceptance claim follows merely from a goal completing.

Recovered September 23 all-admitted-feature direction supports the consumer
outcome but did not previously approve this integration. September 28 completion
estimates remain proposed. Capture timing/recurrence, historical qualification,
trailing exits, risk limits, portfolio shortcuts, signal contracts and the
separately reported V2 callback diagnostic defect are not absorbed into Sprint 28.
Broader memory inventory is not semantic coverage; no Hindsight service is used.
