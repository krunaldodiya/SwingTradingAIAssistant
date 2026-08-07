# Sprint 2 — RELIANCE operational proof

Status: **sprint goal approved; formal commitment and implementation not started**

## Sprint goal

Prove that the Sprint 1 RELIANCE one-minute pipeline works correctly on
representative real data, recovers safely, remains request-minimal, and has
reproducible performance and resource baselines.

The approved direction is to close Milestone 2 evidence under ARK-11 before any
multi-instrument, package/release, higher-timeframe, or research-module work.
ARK-67 must first freeze the operational specification; only then can Ready
implementation tasks be committed to the one-week Sprint 2 timebox.

## Timebox, hierarchy, and WIP

- Planned execution timebox: one week. It starts only after ARK-67 is complete
  and the selected implementation tasks satisfy the Definition of Ready.
- Tracking Saga: **ARK-11**, which is not implemented directly.
- Tracking Epic: **ARK-66**, which is not implemented directly.
- Implementation WIP: one executable Story/Task.
- No Sprint 2 denominator is frozen yet. Only Ready Story/Task items may be
  selected during the post-ARK-67 commitment review.
- The current Linear team exposes `Todo` rather than a literal `Ready` status.
  For this sprint, `Todo` is the operational representation of the workflow's
  `Ready` state and still requires the complete Definition of Ready.

## Required pre-sprint specification

**ARK-67 — Freeze RELIANCE operational-validation and benchmark contract** is
the only operationally Ready (`Todo`) task. It is pre-sprint planning work, not
part of a Sprint 2 implementation denominator. It must define exact
deterministic and authenticated cases, measurements, provenance, resource
bounds, failure behavior, regression-policy method, a complete Milestone 2
crosswalk, and atomic implementation handoffs.

## Candidate implementation sequence

These Backlog tasks describe the approved direction but are not Sprint 2
commitments. ARK-67 may correct or split them before the commitment review:

1. **ARK-68 — Build deterministic M2 validation and benchmark harness.**
   Strict TDD over the existing application contracts; it must not prematurely
   define the later public package interface.
2. **ARK-69 — Validate exactly one closed RELIANCE month against live Upstox
   evidence.** Follow the frozen Plan 02 live gate: one total attempt, no retry,
   authoritative schedule evidence, a caller-created isolated protected root,
   explicit owner authorization, and tightly bounded sanitized output. Compare
   stored evidence with the same response used for ingestion; this task does
   not authorize a second duplicate candle request.
3. **ARK-70 — Prove measured zero-request resume.** An unchanged verified range
   performs no historical candle request and preserves exact request-count,
   manifest, checksum, elapsed-time, and resource evidence.
4. **ARK-73 — Prove targeted repair of one disposable partition.** Mutate only
   an exact validated target inside a caller-created isolated protected test
   root while holding the storage lease. Never damage, overwrite, or repair a
   shared or canonical user dataset.
5. **ARK-71 — Record RELIANCE ingestion, query, and resource baselines.**
   Capture reproducible elapsed-time, throughput, bytes, peak-memory,
   file-descriptor, retry, resume, repair, and DuckDB query evidence. Derive
   regression thresholds from measurements rather than inventing targets.
6. **ARK-72 — Reconcile the exact candidate against the Milestone 2 acceptance
   crosswalk.** Produce one pre-merge evidence handoff covering the selected
   sprint denominator, tests, gates, review, live evidence, benchmarks, scope,
   and unresolved limitations. Post-merge issue closure and the final Linear
   comment are coordinator operations, not claims made by the candidate about
   its own future merge SHA.

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

ARK-12 remains the next roadmap candidate only after ARK-11 closes. No Sprint 2
implementation or stretch work is pre-authorized by this planning record.

## Risks and controls

- **Provider or credential availability:** deterministic evidence proceeds
  independently; authenticated work returns an explicit blocker rather than
  weakening the gate.
- **Private-data leakage:** use disposable ignored storage and sanitized reports;
  never attach candle payloads, tokens, provider keys, or local storage paths.
- **Benchmark noise:** record environment and configuration, use warm-up and
  repetition rules from ARK-67, report variance, and avoid universal claims.
- **Scope drift into product interfaces:** ARK-68 is an evidence harness only;
  stable Python/CLI contracts remain owned by ARK-59.
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
or superseded.

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
