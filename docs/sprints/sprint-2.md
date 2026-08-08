# Sprint 2 — RELIANCE operational proof

Status: **active; execution follows the accepted finite-goal contract**

## Sprint goal

Prove that the Sprint 1 RELIANCE one-minute pipeline works correctly on
representative real data, recovers safely, remains request-minimal, and has
reproducible performance and resource baselines.

The approved direction is to close Milestone 2 evidence under ARK-11 before any
multi-instrument, package/release, higher-timeframe, or research-module work.
ARK-67 must first freeze the operational specification; only then can Ready
implementation tasks be committed to the one-week Sprint 2 timebox.

## Timebox, hierarchy, and WIP

- Execution timebox: **2026-08-08 through 2026-08-14** (one week). ARK-67 is
  complete and every selected child has the accepted Plan 03 revision,
  completion predicate, stop condition, dependency links, iteration budget,
  and high-risk review path recorded in Linear.
- Tracking Saga: **ARK-11**, which is not implemented directly.
- Tracking Epic: **ARK-66**, which is not implemented directly.
- Implementation WIP: one executable Story/Task.
- Frozen denominator: **24 executable Tasks**. ARK-66, ARK-68, and ARK-71 are
  tracking-only Epics/Sagas and are excluded. ARK-67 is completed pre-sprint
  specification work and is also excluded.
- The current Linear team exposes `Todo` rather than a literal `Ready` status.
  For this sprint, `Todo` is the operational representation of the workflow's
  `Ready` state and still requires the complete Definition of Ready.

## Completed pre-sprint specification

**ARK-67 — Freeze RELIANCE operational-validation and benchmark contract** is
Done. [Plan 03](../plans/03-reliance-operational-validation-and-benchmarks.md)
was independently approved and merged by
[PR 27](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/27) at
`766505e8ee113c319a5ebf5a663faf6073cf1997`. It is pre-sprint planning work,
not part of the Sprint 2 denominator.

## Committed implementation backlog

The former broad ARK-68 and ARK-71 Tasks are now non-executable tracking Epics.
Their real children and the four retained atomic Tasks form this denominator:

| ID | Atomic outcome |
| --- | --- |
| ARK-74 | fixed synthetic fixture and v2 schedule corpus |
| ARK-75 | coordinator admission rejection |
| ARK-76 | lease and storage refusal |
| ARK-77 | catalog failure stop |
| ARK-78 | unsafe local-repair refusal |
| ARK-79 | provider authentication/authorization stop |
| ARK-80 | total-attempt-budget stop |
| ARK-81 | retry-wait-bound stop |
| ARK-82 | one-request synthetic verification |
| ARK-83 | cancellation and crash-state mapping |
| ARK-84 | schedule coverage without forward fill |
| ARK-85 | verified physical invalidation |
| ARK-86 | normalization, quality-defense, and empty-response classification |
| ARK-87 | raw partition immutability |
| ARK-88 | mutable-alias reconciliation |
| ARK-89 | ordered mixed-range reconciliation |
| ARK-90 | bounded benchmark measurement recorder |
| ARK-91 | existing-boundary DuckDB query proof |
| ARK-70 | measured zero-request resume |
| ARK-73 | targeted repair of one disposable partition |
| ARK-92 | five comparable B01--B05 baseline samples |
| ARK-93 | deterministic regression-threshold decision |
| ARK-69 | one owner-authorized closed-month live gate |
| ARK-72 | exact-candidate Milestone 2 acceptance crosswalk |

All 24 carry the `Sprint 2` and `Task` labels and use Linear `Todo` as Ready.
Explicit blocker links are authoritative. The default single-WIP order is:

```text
74 -> 82 -> 70 -> 85 -> 90 -> 73 -> 75 -> 76 -> 77 -> 78 -> 80 -> 84
   -> 91 -> 79 -> 81 -> 83 -> 86 -> 87 -> 88 -> 89 -> 92 -> 93 -> 69 -> 72
```

This order brings the reusable corpus and successful one-request path forward,
then proves resume, invalidation, measurement, and repair before completing the
remaining failure/coverage matrix. Baselines and thresholds precede the live
gate; the acceptance crosswalk remains last. A blocked live gate records the
frozen failure and leaves the sprint incomplete; it does not authorize a retry
or denominator change.

## Standing execution authority

Committing a bounded Ready child inside an accepted finite Goal grants the root
authority to route its safe normal lifecycle, but not to perform a mutating or
blocking operation. Terra implementer is the sole content writer: strict TDD,
reviewer-directed in-scope repairs within the recorded budget, deterministic
gates, and the exact candidate commit. Delivery publisher is the sole external
mutation actor: scoped Linear checkpoints, push/PR/async-CI/merge/publication
verification only for the exact independently approved SHA. These safe
same-Goal steps do not require repeated owner approval.

Owner input remains mandatory only for a scope, architecture, trading-rule, or
product decision; the ARK-69 live provider/credential gate; destructive or
non-recoverable shared-data action; a material security/licensing exception; or
the mandatory circuit breaker after two materially identical failures. An owner
interrupt requires quiescing and stop proof before another epoch starts.
Ordinary review findings inside an approved child return automatically to the
same implementer while its budget remains.

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

ARK-12 remains the next roadmap candidate only after ARK-11 closes. No work
outside the frozen 24-item denominator is pre-authorized by this planning
record.

## Risks and controls

- **Provider or credential availability:** deterministic evidence proceeds
  independently; authenticated work returns an explicit blocker rather than
  weakening the gate.
- **Private-data leakage:** use disposable ignored storage and sanitized reports;
  never attach candle payloads, tokens, provider keys, or local storage paths.
- **Benchmark noise:** record environment and configuration, use warm-up and
  repetition rules from ARK-67, report variance, and avoid universal claims.
- **Scope drift into product interfaces:** ARK-68's children produce evidence
  harness behavior only; stable Python/CLI contracts remain owned by ARK-59.
- **Premature scaling:** no additional equity or worker pool enters this sprint.

## Workflow pilot

ARK-67 completed the first graph-lite workflow pilot. Exact-revision
checkpoints, the isolated writer worktree, deterministic gates, and independent
review preserved state correctly through repair rounds. ARK-95 supersedes its
root-as-publisher assumption: the root now remains responsive and non-mutating,
Terra implementer creates the candidate, and delivery publisher alone performs
authorized scoped publication after review. The pilot's owner-wait finding is
addressed by one finite-Goal authority envelope, not by autonomous execution.

Continue recording observable elapsed time, handoff delay, agent turns,
retries, repair rounds, repeated gates, missed handoffs, owner-wait time, final
acceptance, and visible subscription usage. Do not infer unavailable token or
cache telemetry. Sprint closeout decides whether this revised graph-lite
control is retained, revised again, or superseded.

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
