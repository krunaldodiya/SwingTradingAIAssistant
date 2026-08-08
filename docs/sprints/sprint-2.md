# Sprint 2 — RELIANCE operational proof

Status: **committed; implementation ready to start**

## Sprint goal

Prove that the Sprint 1 RELIANCE one-minute pipeline works correctly on
representative real data, recovers safely, remains request-minimal, and has
reproducible performance and resource baselines.

The approved direction is to close Milestone 2 evidence under ARK-11 before any
multi-instrument, package/release, higher-timeframe, or research-module work.
ARK-67 completed the operational specification through merged PR 27.  ARK-94
then reconciled its planning placeholders to real atomic Linear work and froze
the commitment below.

## Timebox, hierarchy, and WIP

- Execution timebox: 2026-08-08 through 2026-08-14 inclusive.
- Tracking Saga: **ARK-11**, which is not implemented directly.
- Tracking Epic: **ARK-66**, which is not implemented directly.
- Tracking Epics: **ARK-68** and **ARK-71**, which are not implemented directly.
- Implementation WIP: one executable Story/Task.
- Frozen denominator: **24 executable Story/Task items**.  It excludes ARK-11,
  ARK-66, ARK-68, ARK-71, completed pre-sprint ARK-67, and planning task ARK-94.
- The current Linear team exposes `Todo` rather than a literal `Ready` status.
  For this sprint, `Todo` is the operational representation of the workflow's
  `Ready` state and still requires the complete Definition of Ready.

## Required pre-sprint specification

**ARK-67 — Freeze RELIANCE operational-validation and benchmark contract** is
Done and merged to `main` at `766505e8ee113c319a5ebf5a663faf6073cf1997`.
Its accepted [Plan 03](../plans/03-reliance-operational-validation-and-benchmarks.md)
governs the complete sprint.  ARK-67 and ARK-94 are pre-sprint planning work,
not part of the implementation denominator.

## Committed executable sequence

Linear blocker links are authoritative.  This total order is the coordinator's
deterministic single-WIP path; it never authorizes a blocked item to start.

| Order | Linear Task | Plan 03 ownership | Direct prerequisite(s) |
| ---: | --- | --- | --- |
| 1 | ARK-74 fixed fixture/schedule corpus | ARK-68a | none |
| 2 | ARK-75 coordinator admission | ARK-68b | ARK-74 |
| 3 | ARK-76 lease/storage refusal | ARK-68c | ARK-74 |
| 4 | ARK-77 catalog failure | ARK-68d | ARK-74 |
| 5 | ARK-78 local-repair refusal | ARK-68e | ARK-74 |
| 6 | ARK-80 attempt-budget stop | ARK-68g | ARK-74 |
| 7 | ARK-84 schedule coverage/no-fill | ARK-68k | ARK-74 |
| 8 | ARK-90 bounded measurement recorder | ARK-68q | ARK-74 |
| 9 | ARK-82 first-request verification | ARK-68i | ARK-74 |
| 10 | ARK-79 provider auth/authz stop | ARK-68f | ARK-82 |
| 11 | ARK-81 retry-wait stop | ARK-68h | ARK-82 |
| 12 | ARK-83 cancellation/crash mapping | ARK-68j | ARK-82 |
| 13 | ARK-85 physical invalidation | ARK-68l | ARK-82 |
| 14 | ARK-86 normalization/quality/empty response | ARK-68m | ARK-82 |
| 15 | ARK-87 raw immutability | ARK-68n | ARK-82 |
| 16 | ARK-70 zero-request resume | Plan 03 ARK-70 | ARK-82 |
| 17 | ARK-88 mutable-alias reconciliation | ARK-68o | ARK-70 |
| 18 | ARK-89 ordered mixed-range reconciliation | ARK-68p | ARK-70, ARK-85 |
| 19 | ARK-91 existing-boundary query proof | ARK-68r | ARK-74, ARK-90 |
| 20 | ARK-73 targeted disposable repair | Plan 03 ARK-73 | ARK-82, ARK-85, ARK-90 |
| 21 | ARK-92 collect five baseline samples | ARK-71a | ARK-75--ARK-91, ARK-70, ARK-73 |
| 22 | ARK-93 derive regression thresholds | ARK-71b | ARK-92 |
| 23 | ARK-69 authenticated one-month gate | Plan 03 ARK-69 | ARK-75--ARK-91, ARK-70, ARK-73, full gate, current owner authorization |
| 24 | ARK-72 M2 acceptance crosswalk | Plan 03 ARK-72 | ARK-69, ARK-70, ARK-73, ARK-93 |

Each Task contains one observable outcome, one-sentence completion predicate,
stop condition, accepted specification revision, strict TDD/review path, and an
autonomous repair budget.  Only ARK-74 enters `Todo` at sprint start; later
Tasks remain Backlog until their blockers are Done and the coordinator promotes
exactly one next item.

## Standing execution authority

Moving one of these bounded Tasks to `Todo` authorizes its safe normal lifecycle:
implementation, materially distinct reviewer-directed in-scope repairs within
its recorded budget, relevant gates, commits, Linear checkpoints, PR
publication, merge, and verification.  No per-command or per-repair owner pause
is required.

Owner input remains mandatory only for a product/scope/architecture change,
the ARK-69 live-provider and credential gate, destructive or non-recoverable
action outside a verified disposable root, coordinator transfer, an unacceptable
security/license decision, or the mandatory repeated-failure circuit breaker.

## Acceptance gate

Sprint 2 is complete only when:

- deterministic validation remains runnable without credentials or private
  market data;
- the owner-authorized live gate runs exactly one closed RELIANCE month with one
  total attempt, no retry, authoritative schedule evidence, isolated protected
  storage, catalog resolution, and no hard-coded provider identity;
- sampled stored evidence matches the same Upstox response used for ingestion
  under the frozen comparison rules without a second duplicate request;
- an insufficient or failed live result is recorded with sanitized evidence but
  leaves Sprint 2 blocked and incomplete;
- a fully verified rerun makes zero historical candle requests;
- one exact disposable test partition triggers only its own repair and returns
  verified evidence without mutating shared or canonical user data;
- the exact candidate crosswalk proves every mandatory Milestone 2 rule:
  interruption safety; internal-gap detection; corrupt/incomplete repair;
  duplicate and impossible-OHLC rejection; empty-success classification; raw
  file immutability; holiday, special-session, late-listing, and legitimate
  no-trade-minute handling; and no forward-filling;
- any rejected or unproven mandatory rule keeps ARK-11 and Sprint 2 open and is
  recorded as explicit blocker/carryover evidence;
- ingestion, query, resume, repair, memory, and file-descriptor baselines are
  reproducible and traceable to code, configuration, data scope, and machine;
- regression thresholds are evidence-based and limitations are explicit;
- credentials, private responses, generated datasets, and machine-specific
  storage paths are absent from Git and sanitized evidence;
- the complete deterministic quality gate and required independent review pass;
  and
- the pre-merge ARK-72 handoff records the exact candidate, selected denominator,
  checks, review, carryover, and retrospective inputs; the coordinator records
  the resulting merge and final issue closure in Linear after publication.

## Explicit exclusions

- ARK-12 multi-instrument scheduling or bounded concurrency;
- ARK-13 and ARK-59 through ARK-61 package/release, public interfaces,
  point-in-time Nifty 50 universe, and higher-timeframe work;
- ARK-39 PyPI publishing and deferred ARK-64 local-book protection;
- Market Regime, indicators, strategy, backtesting, AI integration, or another
  research module;
- indices, India VIX, futures, options, forex, crypto, and other instruments;
  and
- optimization without a measured bottleneck.

ARK-12 remains the next roadmap candidate only after ARK-11 closes.  No work
outside the frozen 24-item denominator is pre-authorized as Sprint 2 stretch.

## Risks and controls

- **Provider or credential availability:** deterministic evidence proceeds
  independently; authenticated work returns an explicit blocker rather than
  weakening the gate.
- **Private-data leakage:** use disposable ignored storage and sanitized reports;
  never attach candle payloads, tokens, provider keys, or local storage paths.
- **Benchmark noise:** record environment and configuration, use warm-up and
  repetition rules from ARK-67, report variance, and avoid universal claims.
- **Scope drift into product interfaces:** ARK-68 is a tracking Epic and its
  atomic children are evidence work only; stable Python/CLI contracts remain
  owned by ARK-59.
- **Premature scaling:** no additional equity or worker pool enters this sprint.

## Workflow pilot

ARK-67 is the first graph-lite workflow pilot. Before execution, record the full
schema-v1 checkpoint as a Linear comment, including specification revision,
repository state, completed phase, last verification, approved risk actor and
evidence, used/remaining iteration budget, next action, blocker, and timestamp.
Record observable elapsed time, handoff delay, agent turns, retries, repair
rounds, repeated gates, missed handoffs, owner-wait time, final acceptance, and
visible subscription usage. Do not infer unavailable token or cache telemetry.
The eventual Sprint 2 closeout records whether graph-lite is retained, revised,
or superseded.  It also measures owner interruptions per Task, review-repair
rounds, spec-drift findings, repeated gates on unchanged revisions,
context-restart time, and issue-to-merge elapsed time for the lightweight SDD
practices proposed in the accepted research note.

## Backlog reconciliation at planning

- ARK-17 is a duplicate of completed ARK-52.
- ARK-18 is canceled because canonical persistent acquisition is one minute;
  ARK-32 and ARK-55 own the active request/window behavior.
- ARK-21 and ARK-22 are canceled because implementing derivative adapters and
  identities is outside the approved equity-only architecture. This does not
  remove the frozen shared candle schema's nullable contract-identity fields.
- ARK-25 is canceled as superseded by the merged engineering standards and
  development workflow.
- ARK-19, ARK-20, and ARK-23 remain uncommitted Backlog hypotheses and are not
  Sprint 2 scope.
- ARK-68 and ARK-71 are non-executable tracking Epics.  ARK-74--ARK-93 are their
  real atomic children; suffix placeholders in Plan 03 are not Linear IDs.
- ARK-94 owns this post-specification commitment reconciliation and is excluded
  from the 24-item implementation denominator.
