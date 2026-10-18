# Plan 77: completed-bar breakout retest research context

Status: deferred after repository reconciliation on 2026-10-18; superseded as a mechanism by the Issue #329 / PR #330 scanner-policy alignment (see Supersession below). Owner and risk owner: Krunal Dodiya. Risk tier: R3 financial-research factual interpretation and provenance. Base: `fe4d36f652e8cea2baaf5dfe69f8242a04d3c665`.

## Outcome and smallest working slice

For an already-qualified scanner `RESEARCH_CANDIDATE`, expose one additive completed-bar Price Action fact answering: *after the exact confirmed upward BOS event, did a later admitted daily bar first reach the original broken high and how did that bar close relative to it?*

The fact is returned under `candidate_summary.price_action_retest`. It is explanatory research context only. It does not alter the scanner's safety result, causal decision, candidate count, universe handling, Nifty 100 priority, or basket selection.

## Necessary-only evaluation

1. **Expected value:** distinguish a completed-bar breakout hold, failure, or as-yet untested level using the existing exact BOS anchor.
2. **Scope fit:** supplies the smallest direct pullback/reclaim fact useful to daily swing research without importing a Price Action catalogue.
3. **Material risk:** calling a range touch a successful retest, using the event bar, choosing a later touch over the first, interpreting intrabar order, or making this optional fact a hidden candidate filter.
4. **Smallest adequate alternative:** inspect only already loaded daily bars after the existing upward BOS event and compare their exact low/close against the existing broken-high Decimal.
5. **Disposition:** deferred. The existing admitted pair workflow already supplies the required first-touch fact and exact close relation; a scanner-local parallel calculation would duplicate it and weaken its provenance boundary.

## Reconciliation — 2026-10-18

The proposed statuses are already represented by delivered pair facts:

- Plan 58 / `observe_setup_level_range_inclusion_v1` finds the earliest completed
  post-event bar with `low <= original_broken_high <= high`, excluding the event
  session and retaining exact admitted-bar identity.
- Plan 60 / `observe_setup_first_inclusion_close_v1` compares that exact first
  inclusion bar's close with the original broken high. Its `NO_INCLUSION` plus
  `ABOVE` / `AT` / `BELOW` outcomes supply the proposed no-retest, held, at-level,
  and failed facts without an intrabar reclaim claim.

The scanner must not create a second local interpretation from discovered
adjusted-daily files. Plan 70 requires its `RESEARCH_CANDIDATE` policy to consume
the exact retained pair through `assemble_setup_evidence_v4`; the current scanner
does not invoke that pair-policy boundary. A later, separately governed repair
must first align scanner candidate classification with that existing policy and
then project the delivered Plan 58/60 facts if they are useful to the scanner.

No new Price Action or Liquidity/SMC calculation is authorized by this plan.

### Supersession — 2026-10-18 (Issue #329 / PR #330)

The candidate-classification precondition recorded above is now delivered:
`signal-decisions scan` derives every `RESEARCH_CANDIDATE` from the canonical
retained pair policy and projects the delivered Plan 58/60 facts as optional
`optional_context` on the brief (`level_range_inclusion_status`,
`level_range_inclusion_observed`, `first_inclusion_close_status`,
`first_inclusion_close_relation`).

No scanner-local `candidate_summary.price_action_retest` calculation will be
added; this plan remains deferred as the rejected duplicate mechanism and is
retained as historical context.

## Frozen factual contract

The new pure internal evaluator receives the event session, positive broken-high Decimal, and the scanner's already loaded per-symbol completed daily bars. It performs no I/O, provider call, clock access, storage mutation, or candidate-policy evaluation.

It excludes the event session. It orders every later completed session ascending and identifies the first later bar whose `low <= broken_level`.

The closed result has exactly:

```text
status: RETEST_PENDING | NO_RETEST_OBSERVED | RETEST_HELD | RETEST_FAILED | RETEST_AT_LEVEL | UNKNOWN
reason: fixed code
broken_level_inr: canonical Decimal text | null
event_session: YYYY-MM-DD | null
first_touch_session: YYYY-MM-DD | null
first_touch_low_inr: canonical Decimal text | null
first_touch_close_inr: canonical Decimal text | null
```

| Status | Rule |
| --- | --- |
| `RETEST_PENDING` | No later completed bar is supplied. |
| `NO_RETEST_OBSERVED` | One or more later completed bars exist; none has `low <= broken_level`. |
| `RETEST_HELD` | The first later touch has `close > broken_level`. |
| `RETEST_FAILED` | The first later touch has `close < broken_level`. |
| `RETEST_AT_LEVEL` | The first later touch has `close == broken_level`. |
| `UNKNOWN` | Event session, broken level, later-bar low, or later-bar close is invalid or unavailable. |

`RETEST_HELD` is only a relation on the first completed touch bar. It does not prove a filled order, intrabar reclaim order, confirmation, validity, eligibility, future return, successful trade, liquidity event, institutional action, or price target.

## Integration and compatibility

`signal-decisions scan` adds the fact only to a qualifying candidate's existing `candidate_summary`. Existing decisions and all existing fields retain their values. The scanner may render the status in its table and expose a bounded AI allowed-claim statement, but it must not add a filter, score, rejection, no-trade outcome, or new provider effect.

No new public CLI command, source, provider, storage namespace, historical replay, AI call, order block, FVG, supply/demand zone, Fibonacci calculation, liquidity/SMC claim, or strategy policy is introduced.

## Frozen adversarial matrix

| Case | Required result |
| --- | --- |
| First later touch closes above / below / exactly at level | `RETEST_HELD` / `RETEST_FAILED` / `RETEST_AT_LEVEL` with that first touch's exact session, low, and close. |
| Later bars exist but none touches | `NO_RETEST_OBSERVED`; no invented touch fields. |
| No later bars | `RETEST_PENDING`; no negative claim. |
| Event-session range includes level | Ignored; it cannot be a retest. |
| Several later touches | First chronological touch determines every populated touch field and status. |
| Missing/non-Decimal low or close, invalid event session, nonpositive/invalid level | `UNKNOWN`; no candidate-policy or provider effect. |
| Optional fact values/states | Candidate decision, safety status, counts, selection, and existing fields remain unchanged. |
| Compatibility | Existing scan behavior without a qualifying candidate remains unchanged; no schema replacement or old-field reinterpretation. |
| Runtime/provenance | Formatted changed source and all directly/transitively bound source-at-rest manifests refresh exactly; no raw/provider/private-path data is introduced. |

## Acceptance evidence

Focused tests cover every matrix row plus scanner integration. The actual CLI/SDK smoke demonstrates a qualifying synthetic scan with an additive retest result. Ruff format/lint and Pyright pass before the committed candidate. R3 functional/domain and security/privacy/provenance reviews inspect the exact candidate; hosted gates, PR merge, and live tracker closeout remain required for delivery.
