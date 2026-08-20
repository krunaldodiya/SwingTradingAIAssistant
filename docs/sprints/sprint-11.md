# Sprint 11 — Current supplied-cohort Market Regime

Status: **TEMPORAL REVIEW REPAIR IMPLEMENTED — focused contract suite GREEN; the prior full-local gate on `d364bf11fac632b4d03b6c179b4519d3ca71f1bb` is superseded by this code change; final full gates, exact re-review, hosted CI/security, merge, and publication are pending**
Tracking: [GitHub Issue #116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116)
Milestone: **Sprint 11**
Plan: [Plan 20](../plans/20-current-supplied-cohort-market-regime-contract.md)
Risk: **R3 / High** — current financial-research fact integrity, immutable evidence, and private provenance

## Goal

Specify the next current/live deterministic Market Regime fact for the exact
owner-supplied Sprint-10 cohort of 1–50 members. The planned contract consumes
exactly 21 explicitly named immutable current-fact archive objects, validates
one common sequence of completed official exchange sessions ending at the latest
admissible decision session, compares each completed decision close with the
close exactly 20 schedule positions earlier using Decimal, and returns only an
aggregate breadth label or one whole-result insufficiency.

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

## Acceptance and lifecycle conditions

Issue #116 is the governing record; the **repository owner** is the outcome and
acceptance authority, and the Issue #116/owner direction authorizes
implementation within this epic. Before an ordinary
completion decision, implementation must demonstrate exact
archive/cohort/opaque-request-identity/report/ledger bindings; valid archive
partial snapshots may be present but never supply a decision/comparison close;
owner-bound schedule source/release/digest, complete classified calendar-date
coverage through cutoff-local date, and latest session with
`close_at <= decision_cutoff` (`as_of` is timely only); Decimal directions;
inclusive 60% boundaries; deterministic reason order; aggregate redaction; and
whole-result insufficiency for every evidence failure. The current temporal
repair additionally requires every member fact at S0 through S20 to have
`published_at >= close_at` and `known_at >= close_at`; facts at equality are
accepted, while `data_cutoff` remains the last-bar time and may precede close.
Focused evidence is GREEN on this worktree:

```text
uv run --no-sync --extra dev pytest -q -o addopts='' tests/market_regime/test_current_supplied_cohort.py tests/market_data/test_current_cohort.py
172 passed
```

The earlier full-local gate on
`d364bf11fac632b4d03b6c179b4519d3ca71f1bb` does not cover this repair and is
superseded. Final full local gates, independent exact-revision quality/security
re-review, hosted CI/security, merge, and publication evidence are pending and
are not asserted by this record.

The main unresolved implementation risks are that the Sprint-10 archive is
write-only/unindexed and persists only an opaque request identity—not the full
request or cohort manifest—and that retained official schedule evidence may not
yet provide a canonical decoder with complete `ExpectedSessionSchedule` v2/v3
classified cutoff-date coverage, admissible `as_of`, authoritative
source/release binding, closure, and special-session proof. The v1 envelope
remains admissible through persisted envelope/report/facts/ledger/partials
consistency plus the owner-supplied cohort hash; neither risk permits a fallback
or archive scan. `code_identity_sha256` is source-at-rest inventory/drift
evidence only: it neither attests executed bytes nor protects against actors
that replace package source, alter `__pycache__`/import state, or execute before
verification. No external trusted launcher or custom import system is added in
Sprint 11; that adjudicated external runtime-root threat boundary remains
unresolved. Implementation of the narrow reader/projection proceeds under Issue
#116, while any provider, source, or material scope change needs its own
approved decision.

## Boundaries preserved

Sprint 11 is the current-path successor to Sprint 10 and remains before current
Sector Analysis in the locked pipeline. It does not alter frozen
`nifty50-market-regime@v1` semantics in Plan 12, deferred Plan 18 historical
work, Sprint-10's recorded stale lifecycle wording, or Sprints 12–16 scope. It
makes no historical membership reconstruction/backtest claim and starts no
sector, news/event, recommendation, order, Market Structure, provider, source,
or raw-OHLC work.
