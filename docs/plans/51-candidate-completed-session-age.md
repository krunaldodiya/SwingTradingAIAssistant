# Plan 51: bounded candidate completed-session age

Status: accepted bounded specification within the owner's October 5, 2026
Sprint 37 signal planning and implementation direction. Outcome and risk owner:
Krunal Dodiya. R3: public financial-research contract, causal schedule and
provenance. Base: `f405bbdb3b2e0b003905415098ed3141413e6dd5`.

Governing Issue: [#256](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/256).

## Necessity and smallest alternative

1. Value: answer how many admitted completed sessions have elapsed since an original upward BOS candidate, when that same event remains represented unchanged.
2. Fit: descriptive lifecycle timing for the external research consumer; no age-based filter, expiry, holding horizon, active status or trade eligibility.
3. Risk: substituting calendar days for sessions, counting a revised calendar silently, or treating a numerical age as validity or a deadline.
4. Smallest alternative: reuse Plan47/48/49 admission and the existing 21-session Structure source; count its exact ordered sessions rather than create an expiry policy, calendar reader or raw-price calculation.
5. Disposition: accepted, one original candidate and two admitted observations; the public projections currently contain event dates but no completed-session distance, and the AI must not calculate market facts itself.

Plan34 admission: the concrete research decision is distinguishing an observation
of today's event from an observation of an older, unchanged event in session
units. Dates alone cannot answer that across weekends, holidays and admitted
special sessions. Plan49 answers representation, not elapsed sessions. This
slice adds one exact count, not an independent confirmation or new opportunity.
Expected coverage is only the finite window where Plan49 establishes unchanged
event/anchor representation. Operational cost is one bounded 21-session scan.
Frequency, screening usefulness and returns are unmeasured; synthetic evidence
proves contract behavior only. No new provider, source, numerical threshold or
strategy is admitted. The approved architecture assigns deterministic market
facts to the tool and contextual interpretation to the external AI.

## Frozen observable contract

Pure SDK `observe_setup_age_v1(previous, current)` accepts exactly two typed
CURRENT_STRUCTURE `CurrentStockResearchResultV2` observations. Invoke Plan49
continuity first, retaining complete Plan48/47 admission, metadata/time bounds,
causal anchoring, selector identity, source-at-rest trust and failure precedence.
Admit both complete inputs before any semantic outcome. Caller-authored
candidate JSON, network, clocks, storage writes, persistence and calendar
acquisition are excluded. Existing mathematics and public versions stay intact.

Preserve Plan49 NON_COMPARABLE, UNKNOWN, NO_BASELINE, OUTSIDE_WINDOW,
NOT_REPRESENTED and REVISED_EVENT statuses/reasons, with null count. None
establishes age, disappearance, invalidation or expiry. For SAME_EVENT and
REPLAY, both admitted Structure source projections must exist. Require the same supported schedule source/release family, already checked by
packet admission, and identical ordered session lists over their common
date interval. Do not compare whole-window schedule digests for equality:
advancing windows and fresh retrieval naturally bind distinct identities.
Release values also embed evidence hashes; retain both, without requiring
digest equality. This clarification follows the real-producer first-path
discriminator and does not relax supported source/release admission.
An unequal source family or overlap yields NON_COMPARABLE with fixed reason
`INCOMPATIBLE_SCHEDULE_SOURCE` or `INCOMPATIBLE_ADMITTED_SESSION_OVERLAP`,
respectively; no count. Only this report changes; Plan49 remains unchanged.

For comparable SAME_EVENT, locate the original event session in current
`admitted_sessions`; count entries strictly after it through the current latest
completed session inclusive. Original event session contributes zero. This is
the current admitted schedule's factual count, not a universal calendar truth.
Count is an integer from 0 through 20; a same-session refresh yields 0. REPLAY
retains REPLAY with count 0. Non-replay count returns OBSERVED with reason
`COMPLETED_SESSIONS_SINCE_ORIGINAL_EVENT`. Duplicated, unordered, wrong-typed,
out-of-bound sessions, inconsistent latest session or impossible baseline
position are terminal integrity failures, even when other input evidence is
unknown or incompatible. Packet admission owns those input guarantees; the
age path also verifies the exact count/endpoint assumptions before counting.
No weekday arithmetic, guessed missing session, future calendar or raw bar.
An invalidated event may still have a descriptive age: count is independent
of Plan50's invalidation judgment and cannot overturn it.

Output `causal-setup-age@v1`, criterion
`ADMITTED_COMPLETED_SESSIONS_SINCE_ORIGINAL_UPWARD_BOS@v1`, own runtime identity,
both full observation hashes and Plan47 rows, Plan49 report identity/status,
status/reason, `completed_sessions_elapsed` (integer or null),
`original_event_session` and `current_completed_session` (both null without a
count), and both schedule projections when a count exists. Each schedule
projection contains source/release, evidence/schedule identity hashes and known
time (the bound feature knowledge time, not independently recovered calendar
publication time). Both original revisions remain visible. No prices, volumes, raw bars,
provider bodies, private paths, limitation payloads or arbitrary diagnostics.
Canonical sorted compact JSON plus LF; result SHA256 over unsigned report;
max 1 MiB. Limitations explicitly deny expiry, active status, eligibility,
recommendation, market effectiveness and persistence.

Injected actual CLI `setup-age --symbol SYMBOL --storage-root ABSOLUTE_ROOT
--previous-selection-time UTC --current-selection-time UTC --output json`
uses the existing observation port, with the same validation before two serial
CURRENT_STRUCTURE calls and exact selector binding. It is an existing CLI
adapter pattern, not a new reader, UI, transport or automatic historical fetch.
Exit0 OBSERVED/REPLAY/NO_BASELINE; exit1 inconclusive evidence statuses above;
exit2 malformed input, integrity or interruption, fixed diagnostic and no
partial stdout. A guarded runnable synthetic demo uses real producer admission
and actual CLI, labels its fixed dates as synthetic and denies network and
hidden-directory effects.

## First working path, complete acceptance and ownership

First establish discriminating actual CLI RED, then real-producer unchanged
event at age1 through SDK/CLI/demo. Complete same-session/replay0, multi-session
and weekend/holiday discrimination, every evidence status and matrix row before
freeze. The existing Linux distribution verifier must exercise isolated
installed SDK and actual CLI imports, OBSERVED/exit0 with exact count1,
REPLAY/exit0 count0 and UNKNOWN/exit1 null count, retaining identities. No new
installed entrypoint or OCI mount. Existing native/OCI/source substitution,
interruption and prior-wheel rollback gates remain mandatory.

Coordinator is sole writer and integration/tracker owner: new age SDK/CLI/
manifest under `research_comparison`, focused tests, synthetic example, existing
Linux verifier and its focused regressions, Plan51/Sprint37, sprint index and
small relevant operator/roadmap docs. Only mechanically affected manifests may
otherwise change. No dependency or retained-data migration. Approved tooling
is the existing owner-checkout `.venv`, outside this isolated worktree; official
uv only when authorized and needed, no copy/installation. Existing owner and
retained checkouts stay intact. Rollback is source/prior-wheel rollback with no
persisted age state. Public interfaces/operator docs and runtime/source trust
are affected; new sources/credentials, data retention/deletion, eligibility,
funding/settings, storage ownership and broker effects are not affected.

| Risk/adversarial matrix | Required observed evidence |
| --- | --- |
| Positive | Real admitted unchanged original event, advancing latest NO_MATCH, count1 and both schedule/revision identities |
| Session arithmetic | Same-session refresh/replay0; multiple completed sessions; weekend/holiday gaps not counted as days; event session excluded |
| Schedule compatibility | Fresh digests alone compatible; differing source family or common ordered sessions non-comparable, no count |
| Evidence states | No baseline, unknown, outside window, not represented and revision remain distinct, null count; invalidation is not reversed by age |
| Integrity/precedence | Wrong type/runtime/packet/diagnostic/time/anchor/session ordering/endpoint terminal even combined with unknown/incompatibility |
| Bounds/privacy | One stock/two observations, 21-session input/20 maximum age, malformed request before effects, metadata and 1MiB/plus-one; no private numerical facts |
| Causal timing | Plan48 selector/knowledge/deadline order retained; count only through admitted completed endpoint, no backdating |
| Retry/interruption/concurrency | Repeated/concurrent pure calls stable without input/file mutation; interrupted second call no partial stdout |
| Compatibility/recovery | Setup/comparison/continuity/invalidation regressions, source manifests and prior-wheel recovery; no storage mutation |
| Installed/delivery | Isolated installed SDK/actual CLI observed age1/replay0/unknown; hosted native/OCI/adversarial/rollback receipts |
| Independent review | Two fresh read-only complete base-to-clean-committed-candidate domain and security/privacy/provenance reviews; full pre/post SHA/tree/clean proofs |
| Final gates | GitHub-hosted-only static/full selected tests/87% branch coverage/sdist/wheel/installed/OCI/GitGuardian, exact main admission, private publication and fresh tag/digest pulls |

Handbook core plus specification/TDD fallback applies because no trusted
original procedure content identity was established. Two fresh native separate
review actors inherit supported host settings and cannot write candidate bytes
or spawn agents. Complete results, limitations, lifecycle and routing identities
are retained. Coordinator supplies exact base/head/tree and full diff after
commit, classifies blockers against accepted criteria, retains failed evidence,
repairs in scope and obtains current verdicts. Provider safety refusal is
INVALID/NO VERDICT and cannot be bypassed. Focused/static local checks are
lightweight feedback only; no heavy local suite/build/container acceptance.
Fresh shared account allowance plus account-wide Actions AND Packages $0 paid
usage/Stop usage Yes precede every hosted trigger; no paid capacity, reruns,
visibility or settings changes. Complete hosted run/attempt/job/log receipts
must be retained before expiry.

Goal begins only after governed Issue, Sprint37 milestone and private Delivery
Project fields are read back. Standing owner authority covers implementation,
review, draft PR, normal merge, exact-tree admission, private publication and
tracker/milestone closeout without redundant approval. Pause only dependent
work for consequential scope/authority conflict, source/provider/credentials,
out-of-scope protected effects, destructive action, unavailable evidence,
shared mutation, failed gate/review or unaccepted residual risk. All required
acceptance remains mandatory; a green PR is not delivery completion.

## Honest remaining boundaries

Later improvements/non-goals: expiry/validity policy or holding horizon,
generation/recommendation policy, persistent lifecycle/monitoring, broader
cohorts/history, new analytical families/providers/formulas/thresholds/catalogues,
effectiveness, eligibility and broker/money/risk/capital/position expansion.
No Future issue is selected or borrowed. CI retirement and Windows WSL2/Docker
Desktop qualification remain separate; four private_source historical cases
retain their own evidence boundary. Sprint36 is live-verified complete and its
pre-delivery prose is preserved.

All eight Plan47 outcomes remain distinct: detection; necessary analytical
coverage; generation responsibility/identity; confirmation/invalidation/expiry/
duplicates; observable lifecycle; coherent context/safety; correctness/AI
interpretation/effectiveness; verified phase closeout. This slice advances one
lifecycle timing fact only. Sprint completion cannot establish signal-phase
or product completion.
