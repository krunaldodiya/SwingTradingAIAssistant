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

## Deadline accountability

This is a tracking-only accountability record. It preserves the historical
Sprint 2 timebox and does not change the committed work, its order, its WIP
limit, or any Definition-of-Done requirement. It is deliberately pending until
the cutoff so it does not precompute future completion or blocker evidence.
Deadline expiry never marks work Done, closes the sprint, or waives any gate;
committed work continues after the cutoff until its normal completion evidence
exists.

```json
{
  "deadline_id": "sprint-2-owner-cutoff-v1",
  "historical_timebox": {
    "start": "2026-08-08",
    "end": "2026-08-14"
  },
  "cutoff_local": "2026-08-09T22:00:00+05:30",
  "timezone": "Asia/Kolkata",
  "cutoff_utc": "2026-08-09T16:30:00Z",
  "decision_recorded_at_utc": "2026-08-08T07:16:18.133Z",
  "decision_recorded_at_source": "Linear ARK-97 createdAt",
  "conversation_decision_time": "unavailable/unproven",
  "original_denominator": [
    "ARK-74", "ARK-75", "ARK-76", "ARK-77", "ARK-78", "ARK-79",
    "ARK-80", "ARK-81", "ARK-82", "ARK-83", "ARK-84", "ARK-85",
    "ARK-86", "ARK-87", "ARK-88", "ARK-89", "ARK-90", "ARK-91",
    "ARK-70", "ARK-73", "ARK-92", "ARK-93", "ARK-69", "ARK-72"
  ],
  "original_denominator_count": 24,
  "tracking_governance_additions": [
    {
      "id": "ARK-95",
      "reason": "Accepted workflow-orchestration remediation and publication control.",
      "owner_approval_reference": "Accepted finite-Goal workflow authority; exact owner-chat decision time is unavailable/unproven.",
      "accepted_at": {"value": null, "status": "unproven", "source": "authoritative approval timestamp not retained in the sprint record"},
      "created_at": {"value": null, "status": "unproven", "source": "Linear issue history must be queried at snapshot time"},
      "started_at": {"value": null, "status": "unproven", "source": "Linear lifecycle history must be queried at snapshot time"},
      "completed_at": {"value": null, "status": "unproven", "source": "GitHub merge and Linear Done timestamps must be queried at snapshot time"},
      "included_in_original_denominator": false
    },
    {
      "id": "ARK-96",
      "reason": "Documentation reconciliation required by the accepted workflow change.",
      "owner_approval_reference": "Accepted finite-Goal workflow authority; exact owner-chat decision time is unavailable/unproven.",
      "accepted_at": {"value": null, "status": "unproven", "source": "authoritative approval timestamp not retained in the sprint record"},
      "created_at": {"value": null, "status": "unproven", "source": "Linear issue history must be queried at snapshot time"},
      "started_at": {"value": null, "status": "pending", "source": "Linear lifecycle history must be queried at snapshot time"},
      "completed_at": {"value": null, "status": "pending", "source": "Linear Done history must be queried at snapshot time"},
      "included_in_original_denominator": false
    },
    {
      "id": "ARK-97",
      "reason": "Tracking-only owner cutoff accountability record.",
      "owner_approval_reference": "Owner accepted a tracking-only deadline; exact conversation decision time is unavailable/unproven.",
      "accepted_at": {"value": null, "status": "unproven", "source": "exact owner-chat decision timestamp is unavailable"},
      "created_at": {"value": "2026-08-08T07:16:18.133Z", "status": "observed", "source": "Linear ARK-97 createdAt"},
      "started_at": {"value": null, "status": "pending", "source": "Linear lifecycle history must be queried at snapshot time"},
      "completed_at": {"value": null, "status": "pending", "source": "Linear Done history must be queried at snapshot time"},
      "included_in_original_denominator": false
    }
  ],
  "cutoff_snapshot": {
    "status": "pending_until_cutoff",
    "captured_at": null,
    "completed_baseline_ids": null,
    "completed_baseline_count": null,
    "unfinished_baseline_ids": null,
    "unfinished_baseline_count": null,
    "observed_state_or_blocker": null,
    "added_work_rows": null,
    "baseline_partition_rules": [
      "completed_baseline_ids and unfinished_baseline_ids are disjoint",
      "completed_baseline_ids and unfinished_baseline_ids together equal original_denominator",
      "completed_baseline_count + unfinished_baseline_count == original_denominator_count"
    ],
    "snapshot_rule": "Populate only at or after cutoff from raw authoritative evidence; added-work rows retain reason, approval reference, accepted/created/started/completed timestamps, and included_in_original_denominator=false."
  },
  "completion_classification_rules": {
    "required_events": [
      "successful hosted checks",
      "exact-SHA merge/publication",
      "Linear Done synchronization"
    ],
    "on_time": "every required event timestamp is less than or equal to cutoff_utc",
    "after_cutoff": "any required event timestamp is greater than cutoff_utc",
    "unproven": "missing, date-only, or coarse required timestamps are unproven",
    "raw_sources": [
      "GitHub hosted-check timestamps",
      "GitHub exact-SHA merge/publication timestamp",
      "Linear issue-history Done timestamp"
    ],
    "not_evidence": ["updatedAt", "issue age", "PR age"],
    "human_variance": "may be rounded; never infer labor-hours"
  },
  "post_cutoff_ledger": {
    "completed_after_ids": null,
    "carryover": null,
    "final_completion_at": null,
    "elapsed_overrun_as_of": null,
    "final_schedule_variance": null,
    "final_schedule_variance_rule": "null until all 24 baseline tasks have Definition-of-Done evidence"
  },
  "post_cutoff_interpretation": "continuing committed work is carryover/schedule overrun; only newly added work is expansion",
  "deadline_never_waives": {
    "scope": "deadline expiry only",
    "requirements": [
      "specification",
      "strict red-green-refactor TDD",
      "deterministic quality gates",
      "independent review",
      "hosted CI/security",
      "exact-SHA merge/publication",
      "ordering/WIP",
      "ARK-69 owner live authority",
      "Sprint Done/closure"
    ]
  }
}
```

### Time-accountability ledger

The [structured time-accountability ledger](sprint-2-time-accountability-ledger.json)
standardizes the prospective range, raw lifecycle/publication timestamps,
derived elapsed fields, and separately measured workflow waits and gates for
the frozen 24-item baseline plus ARK-95 through ARK-110 additions. Its current
snapshot is a **pre-cutoff candidate**: this page's cutoff report remains
`pending_until_cutoff` and no completed/unfinished partition has been
populated before **2026-08-09T22:00:00+05:30**.

At or after the cutoff, an authorized recorder must: capture the exact Linear
issue and state-history fields; capture the matching PR, required CI, and merge
timestamps for the exact candidate SHA; record their sources and timezones;
validate the frozen baseline partition; and calculate only elapsed fields whose
two authoritative operands are present. Missing values remain `UNSET`; do not
backfill estimates for completed work, derive labor hours from Linear points,
or use issue age or `updatedAt` as lifecycle evidence.

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
mutation actor: a bounded root handoff and one active mutator epoch authorize
only scoped Linear lifecycle/checkpoint transitions before implementation or
review. Worktree publication, push, PR, CI, merge, hosted verification, final
closure, and final Linear synchronization require the exact independently
approved SHA. These safe same-Goal steps do not require repeated owner approval.

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
  checks, review, carryover, and retrospective inputs; delivery publisher records
  hosted merge evidence and performs final Linear synchronization after
  publication. Root receives and reports that evidence only.

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
