# Sprint 11 — Current supplied-cohort Market Regime

Status: **CLOSED / COMPLETED** — [Issue #116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116)
closed after [PR #124](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/124)
merged exact reviewed head `d56120fb5966dffea32207b59f1edf0673b2e51b`
as merge commit `f03edf3690e34e25a57b58a15450129e3bf9a5e9`.
Tracking: [GitHub Issue #116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116)
Milestone: **Sprint 11**
Plan: [Plan 20](../plans/20-current-supplied-cohort-market-regime-contract.md)
Risk: **R3 / High** — current financial-research fact integrity, immutable evidence, and private provenance

## Goal

The delivered current/live deterministic Market Regime fact consumes the exact
owner-supplied Sprint-10 cohort of 1–50 members. Its V1 contract consumes
exactly 21 explicitly named immutable current-fact archive objects, validates
one common sequence of completed official exchange sessions ending at the
latest admissible decision session, compares each completed decision close with
the close exactly 20 schedule positions earlier using Decimal, and returns only
an aggregate breadth label or one whole-result insufficiency.

`BROAD_ADVANCE` and `BROAD_DECLINE` use inclusive integer 60% tests; otherwise
the fact is `MIXED_PARTICIPATION`. Any incomplete, unsafe, stale, future-known,
conflicting, cross-cohort, schedule-unproven, or partial-shaped/value source
placed in `completed_daily` or otherwise substituted for a completed close returns
`INSUFFICIENT_EVIDENCE` with label, counts, and the required public
`member_directions` field null. Private member directions, identities, raw
closes, archive paths, private-root details, provider payloads, and schedule rows
are never public output.

## Current implementation decision

[Plan 20](../plans/20-current-supplied-cohort-market-regime-contract.md) is the
R3 implementation specification for Issue #116. It selects direct no-follow
content-SHA archive reads plus retained official schedule continuity proof over
doing nothing, changing frozen Plan 12, reusing the deferred historical
contract, or querying/recomputing raw retained OHLC. The schedule proves only
that no completed exchange session was omitted; it never supplies a price fact.
The resulting reducer is pure and receives only a validated private projection.

The implemented public surface is:

```text
market-data regime-current \
  --input-file <absolute-owner-private-canonical-json> \
  --storage-root <absolute-owner-private-root> \
  --output json
```

The input has exactly 21 explicit archive IDs, a bound Sprint-10 cohort identity,
a decision cutoff/session, `schedule_evidence_sha256`,
`schedule_source = "nse-authoritative-calendar"`, and exact
`schedule_source_release = "sha256:<64 lowercase hex>"`. The repository owner
selects this already-retained schedule evidence under Issue #116; the
deterministic adapter validates exact source/release/digest and never treats an
arbitrary nonempty retained schedule as official. It resolves the schedule
through `ScheduleEvidenceStore.resolve` below the same private retained root;
there is no schedule path or supplied schedule bytes. The command is read-only:
no provider/network fallback, archive scan, raw-candle query, data acquisition,
or persistence effect. Archive partial snapshots may be present and must
validate, but can never substitute for a decision/comparison close. Exit
semantics are `0` for an observed report, `1` for canonical whole-result
insufficiency, and `2` for runtime-code-identity or other pre-report structural
rejection; public output and diagnostics redact private paths and member/raw
facts.

### V2 comparability cutover

The current V2 module is a pure input-only evaluator. It receives the observed
V1 report/private grid, retained Plan-21 screen, and Plan-22 adjusted-close V2
handoff; it performs no provider, network, storage, or clock operation. It
requires exact cohort/member/session/request/report/schedule provenance closure,
screened no-action evidence, and equal per-member raw/adjusted
`UP`/`DOWN`/`FLAT` Decimal directions. Otherwise it returns aggregate-only
`INSUFFICIENT_EVIDENCE` with the exact V1 denominator, null comparison
session/label/counts, and no member leakage or denominator reduction.

The adjusted handoff labels a result `CURRENT_PROSPECTIVE` only when valid V2
schedule/mapping admission completes and retrieval is no later than the decision
cutoff. Later retrieval remains `REVISED_NON_PIT`; V2 rejects it. This is not a
strict historical PIT claim and does not modify the owner-supplied mapping trust
boundary.

## Acceptance and lifecycle conditions

Issue #116 is the governing record; the **repository owner** is the outcome and
acceptance authority. Completion demonstrated exact
archive/cohort/opaque-request-identity/report/ledger bindings; valid archive
partial snapshots may be present but never supply a decision/comparison close;
owner-bound schedule source/release/digest, complete classified calendar-date
coverage through cutoff-local date, and latest session with
`close_at <= decision_cutoff` (`as_of` is timely only); Decimal directions;
inclusive 60% boundaries; deterministic reason order; aggregate redaction; and
whole-result insufficiency for every evidence failure. The temporal repair
requires every member fact at S0 through S20 to have
`published_at >= close_at` and `known_at >= close_at`; facts at equality are
accepted, while `data_cutoff` remains the last-bar time and may precede close.

Dependencies [#125](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/125),
[#127](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/127), and
[#132](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/132)
merged before PR #124. Exact reviewed head
`d56120fb5966dffea32207b59f1edf0673b2e51b` passed:

```text
296 focused tests; 2,867 full tests; 91.03% coverage
Ruff format/check; Pyright; Vulture 80; build
sealed no-network evaluator smoke; live current-prospective adjusted smoke
independent exact-revision review; hosted Quality/build; GitGuardian
```

PR #124 merged that head as
`f03edf3690e34e25a57b58a15450129e3bf9a5e9`, and Issue #116 closed/completed.
This final evidence supersedes the earlier local-gate record for
`d364bf11fac632b4d03b6c179b4519d3ca71f1bb`.

The Sprint-10 archive remains write-only/unindexed and persists only an opaque
request identity—not the full request or cohort manifest. Retained official
schedule evidence may not provide a canonical decoder with complete
`ExpectedSessionSchedule` v2/v3 classified cutoff-date coverage, admissible
`as_of`, authoritative source/release binding, closure, and special-session
proof; such evidence fails closed. The v1 envelope remains admissible through
persisted envelope/report/facts/ledger/partials consistency plus the
owner-supplied cohort hash; neither risk permits a fallback or archive scan.
`code_identity_sha256` is source-at-rest inventory/drift evidence only: it
neither attests executed bytes nor protects against actors that replace package
source, alter `__pycache__`/import state, or execute before verification. Sprint
11 added no external trusted launcher or custom import system; that external
runtime-root threat boundary remains unresolved. The delivered narrow
reader/projection remains bounded by Issue #116. Any provider, source,
schedule-authority, privacy-boundary, or material scope change requires its own
approved decision and fresh exact-revision evidence.

## Boundaries preserved

Sprint 11 is the completed current-path successor to Sprint 10. It delivered
V2 comparability semantics without altering frozen historical
`nifty50-market-regime@v1` exact-50 semantics in Plan 12, deferred Plan 18
historical work, Sprint-10's recorded stale lifecycle wording, or Sprints 12–16
scope. Future Plan-23 migrations remain separate. Sprint 12 is unblocked but
**NOT STARTED**. This closeout makes no historical membership
reconstruction/backtest claim and starts no sector, news/event, recommendation,
order, Market Structure, provider, source, or raw-OHLC work.
