# Plan 41: stock-versus-reference-stock Relative Strength

Status: accepted direction and frozen first implementation contract; not delivered.
Owner and risk owner: Krunal Dodiya. Risk R3 (financial-research facts, source integrity,
private retained evidence and public CLI/SDK contract). Sprint 27 / [#230](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/230).
Authority: owner selected the recommended stock/reference-stock comparison in this
chat on 2026-09-30. The agent specifies implementation within that accepted direction.
Baseline: `92cf3d029db69bb297c92c087486c04f68759389`, tree
`d911f6ae769884ed92949851d832cb9344922554`. Plans 21, 34 and 35 govern reused admission.

## Necessary-only admission

1. Value: answer whether a requested stock gained more or lost less than a caller-chosen reference over the same 20 completed daily intervals; direction, breadth, Industry, Structure and Volume do not supply this magnitude comparison.
2. Fit: one exact descriptive price-change comparison for canonical listed equities, separate from index selection and optional analytical filters.
3. Risk: unequal windows, identity/source/basis substitution, corporate actions, future knowledge, rounding and missing reference evidence can create false relative performance.
4. Smallest alternative: reuse retained Upstox RAW admission and Plan 21 screening; the AI cannot calculate market facts from raw bars, and an official-index or cohort-aggregate benchmark would add unnecessary source or aggregation scope.
5. Disposition: accepted for the retained-only CLI/SDK slice below; effectiveness, official indexes, rankings and consumer integration remain deferred.

## First working outcome and mathematical contract

One command and equivalent Python boundary answer the accepted question:
`market-data relative-strength-current --input-file ABSOLUTE_PRIVATE_JSON
--storage-root ABSOLUTE_PRIVATE_ROOT --output json`.
The first positive path compares one target with one distinct explicit reference
using actual synthetic retained producer evidence through the real CLI. Complete
all bounds and failure paths below before acceptance. No provider or credential
access, repair, acquisition, retained-data writes, new archive or cold-start claim.

Select exactly the latest 21 official completed sessions S0..S20 at selection time,
representing 20 close-to-close daily intervals. Both instruments use that same
schedule/window, source and price basis; never select independent fallback windows.
Require regular equal-duration sessions in this first version, as for Plan 39;
special/unequal-duration windows are explicitly unsupported. No partial bars.

For positive finite endpoint closes C0,C20 of a target and R0,R20 of the reference:
- target fractional price change = C20/C0 - 1;
- reference fractional price change = R20/R0 - 1;
- difference in percentage points = 100 * (C20/C0 - R20/R0);
- relation ABOVE, EQUAL or BELOW is the sign of that exact difference, with no rounding or tolerance.

Return each quantity as a reduced signed integer numerator and positive denominator.
A zero numerator has denominator one. Use exact rational arithmetic from admitted
Decimal values, independent of ambient Decimal precision. This is an unadjusted
price-change comparison, not total return, a ratio of returns, RSI, a rank or a
future-return claim. Independently specified example: a target from 100 to 110
and reference from 200 to 210 give 1/10, 1/20, +5 percentage points and ABOVE.
A target declining 5% while its reference declines 10% also gives +5 points.
No multi-window optimization, threshold, annualization or configurable formula.

At this new arithmetic boundary each endpoint must have at most 32 coefficient
digits and a Decimal exponent between -16 and +16 inclusive. This generous finite
bound prevents adversarial numeric allocation; test exact bounds and plus one.
An otherwise admitted endpoint outside it yields `PRICE_RANGE_UNSUPPORTED` for
that instrument, with no partial arithmetic. Nonpositive/nonfinite/malformed
values cannot become admitted observations. Existing producers retain their own
validation and failures; this bound does not weaken or redefine them.

## Request and identity

The closed request is `current-relative-strength-request@v1`, maximum 64 KiB.
Exactly these keys: `contract_version`, `data_selection_time`, `admission_deadline`,
`schedule_identity_sha256`, `reference`, `members`.
`reference` is one existing Plan-35 canonical member object; `members` is an
ordered array of 1–49 target member objects. Each member has exactly `isin`,
`exchange`, `instrument_type`, `segment`, `effective_symbol`, `valid_from`,
`valid_through`, with existing canonical validation. Targets are unique by
identity and effective symbol. Reference must be distinct from every target,
including aliases. Reject malformed types, unsupported instruments, duplicate
or unknown JSON keys, nonfinite JSON constants, wrong versions and bad intervals
before storage/provider effects. Validate direct SDK construction as well.

UTC selection/deadline are at most 30 minutes apart and before IST rollover.
Preserve target order. Bind the canonical request, ordered target list, separate
reference identity and exact producer list `[reference, *members]`; that list has
2–50 members and is an explicit request transformation, not an inferred universe.
Output exposes these identities and original roles; it never calls the reference
an index or assumes that either list represents a market/Industry. Changing the
reference, ordering, window, mapping or source changes the relevant identities.
Retain the existing 64-calendar-day, three-month and 10,000-minute/member bounds.

## Evidence, compatibility and source provenance

Support only `UPSTOX / RAW / 1d-derived-from-retained-1m`. Preserve original source
observation/knowledge times, canonical mappings, session schedule, partition
checksums and corporate-action screen identities. Reuse Plan 35's held storage
lease, strict missing-partition distinction and final retained-evidence recheck.
Bind the exact endpoint closes inside the existing opaque producer admission,
including integrity validation and final recomputation/recheck. Do not admit
caller-supplied prices, copied JSON or a self-declared digest as production facts.
Private endpoint binding is sufficient; a new persistence/sealing system is not.

Both instruments must independently pass the existing action screen over S0..S20.
An action anywhere in that window withholds the instrument; missing screening
also withholds it. State that this nonexhaustive provider screen does not prove
absence of all actions. Preserve current knowledge truthfully: no historical
point-in-time qualification, adjusted-price substitution, BharatStock/Yahoo
fallback, official index evidence, dividend or total-return claim.

Keep every existing public projection/schema/default/exit and mathematical
contract unchanged, including Volume. Adding producer-private endpoint binding
must preserve prior consumers' public bytes; runtime-source identities change
truthfully. Format runtime sources before updating every directly/transitively
bound manifest. Preserve closed legacy inventories (notably Plan 20's five paths)
and update literal provenance examples only when their verified identity changes.

## Results and failure precedence

`current-relative-strength@v1` binds request, calculation, runtime and result
identities; source/basis, session window, reference and ordered target identities;
selection/cutoff/knowledge times, mapping/partition/screen provenance; and closed
availability/reasons. Reference has its own availability/provenance, and every
target remains represented with optional exact fact. No cohort aggregate or rank.
Each fact contains target and reference fractional changes, difference in percentage
points and relation. Withheld comparisons contain null facts and explicit reasons.
Output is bounded to 1 MiB and owner-private; omit raw bar arrays, endpoint prices,
provider bodies, host paths, credentials and exception strings.

Precedence is input validation, shared runtime/storage/integrity/liveness admission,
then evidence comparability and optional arithmetic. Unsafe/held/replaced roots,
corrupt catalogs/screens/partitions, forged admission or substituted evidence,
unexpected faults and interruption are terminal: no partial CLI JSON. Inherited
unclassified errors are not rebranded as ordinary optional absence. Scan/recheck
all selected evidence before returning an unavailable reference result, so a
missing reference cannot hide target corruption. Clock regression, deadline
expiry or IST rollover aborts, including immediately before CLI emission.

Absent calendar yields a shared dependency result with all targets represented.
Absent/stale/insufficient mapping, bars or action screen withholds the affected
instrument. Absent/unsupported reference withholds all target comparisons with
`REFERENCE_UNAVAILABLE`, while preserving each target's independently admitted
availability and reason. A missing target with an observed reference withholds
only that target. If both are unavailable, publish the reference dependency and
retain the target reason separately. No denominator shrinkage or substitution.
A valid equal-price comparison is observed EQUAL, not missing evidence.

Exit 0 means all requested comparisons observed; exit 1 means an explicit nonready
result; exit 2 means malformed input or terminal internal/storage failure. These
are research outcomes, never trade eligibility. Explicit retry is read-only and
revalidates evidence; no automatic retries, fallback, background job or lock repair.
Rollback removes the additive entry point, preserving existing stores/readers.

## Frozen adversarial matrix

All rows use deterministic synthetic evidence or isolated temporary roots. No real
provider or owner-private data execution is authorized by this acceptance matrix.

| Case | Observable outcome and forbidden effect | Evidence method |
| --- | --- | --- |
| One target/reference, mixed gains/losses, equal fractional changes at different price levels | Exact independently calculated fractions/points and sign; no rounded decisions | Pure math tests and real producer-to-SDK/CLI positive test |
| Decimal precision changes, tiny/large endpoints and sign reversal | Identical exact answer; numeric bounds yield explicit unsupported outcomes | Literal rational expectations, boundary and limit-plus-one cases |
| 1/49/0/50 targets, reference overlap/alias, duplicates/order/version/fields/64 KiB | Valid limits preserved; invalid request rejected before effects | SDK/parser/private-file/CLI tests with effect sentinels |
| Missing calendar, mapping, minute or screen; action in reference/target; range failure | Full ordered target result; unavailable reference blocks comparisons, target absence remains local | Actual retained temporary-root fixtures and result assertions |
| Partial/special/unequal sessions, different windows/basis/source, mapping validity, future knowledge | Unsupported/insufficient or terminal integrity rejection as appropriate; no substitution | Producer/contract/temporal adversarial fixtures |
| Corrupt catalog/screen/partition or forged admission plus missing reference/target | Integrity wins; no partial JSON and no successful comparison | Actual corruption/substitution and combined-failure tests |
| Deadline before/during read/serialization/emission, clock regression, IST rollover | Terminal stop before output; no clamping or backdating | Controlled clock SDK and real CLI-boundary tests |
| Held/replaced root, interruption, retry, evidence changed during final recheck | Terminal rejection or exact safe read-only retry; original files unchanged | Lease/no-follow tests, before/after file inventories, injected boundary changes |
| Old price/Volume/agent readers and bound manifests | Unchanged public behavior; exact current source identities | Focused compatibility, all-manifest check, verified demo provenance |
| Installed package and complete candidate | CLI/SDK work from clean wheel without checkout; tampered source rejected | sdist/wheel, clean install smoke, independent reviews and full self-hosted CI |

No statistical effectiveness test is warranted because this slice makes no
predictive or selection-benefit claim. Pure arithmetic examples suffice alongside
adversarial integration; no new test framework or optimization project.

## Ownership, execution and delivery

Coordinator owns this contract, tracker, integration decisions, publication,
review assignments and final gates. One native implementation executor owns
`relative_strength/`, the producer-private endpoint seam in
`market_data/current_raw_price_context.py`, CLI wiring, related tests, directly
required runtime manifests and `docs/relative-strength.md`. No nested delegation.
Coordinator and executor serialize changes in shared files. Independent native
functional/domain and security/privacy/provenance reviewers are assigned after
writers finish; neither reviewer authors the candidate. Each reviews the complete
base-to-clean-committed-candidate change and reports exact commit/tree and limits.
Requested implementation setting: supported `gpt-6-sol`, high reasoning for R3
cross-boundary work; reviewer settings are recorded at dispatch. Host-observed
telemetry is separate; no unverifiable identity is asserted.

The software-engineering-handbook core and requirements-planning fallback apply.
The original provider skills are not registered in this session; no source identity
or invocation is invented. Native tools supply shell, GitHub, Goal and independent
agents; no memory connector is available. Issue and checked-in contract carry the
decision with readback. The desktop worktree tool returned `Git is unavailable`;
shell Git created isolated `codex/sprint27-relative-strength` at
`/home/krunaldodiya/WorkSpace/Code/SwingTradingAIAssistant-sprint27`.

Start persistent Goal only after this contract and Issue are retained/read back.
Tests first; focused formatting/static/affected tests precede exact-candidate
reviews. Resolve blockers before expensive full suite/coverage and final package/
self-hosted CI gates. Reuse existing disposable Podman CI; no paid-hosted fallback
or Docker installation. Record exact evidence, including failures. A review pass,
implementation completion, PR creation, merge and sprint closure are distinct.

Non-goals: agent-dossier/Volume integration, official indexes/cohort averages,
rankings/screens/signals, tuning or extra windows, new sources/captures, providers,
archives/attestation/replay, fundamentals, monitoring, registry publication and
unrelated tracker cleanup. Source adoption, protected/credential effects,
destructive actions, conflicting changes, unapproved scope, unavailable temporal
evidence, consequential ambiguity and merge/release authority stop only dependent
work. Freeze mutations during exact-byte review. Do not mark unfinished Goal or
sprint complete at an authority gate.
