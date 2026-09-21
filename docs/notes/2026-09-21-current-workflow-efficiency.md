# Current-workflow efficiency investigation

Date: 2026-09-21
Status: **open — #190 measurement and optimization; parent #172 remains open**

## Scope and baseline

The inspected runtime is merged commit
`b3465a9695d7f1d8f6284f8f375ccade51917684`. Measurements invoke the public
SDK with synthetic credentials and network-denied transports, preserving
canonical decoding and member outcomes. They measure local orchestration,
not provider latency, market validity or a production SLA. Setup is recorded
separately. The raw workflow requires an already-admitted calendar.

The raw one-stock workload contains 21 complete 375-minute sessions
(7,875 completed minute bars) plus 15 current minutes. After one discarded
warmup, three fresh-process repetitions produced these entry-to-return results:

| Public V2 mode | Median seconds | Min–max seconds | Actual transport attempts |
| --- | ---: | ---: | ---: |
| ACQUIRE_MISSING | 9.704 | 9.560–10.052 | 4 |
| RETAINED_ONLY | 3.012 | 2.930–3.014 | 0 |
| REFRESH_ONCE | 8.386 | 8.365–8.457 | 1 |

All requested member states were observed and canonical decoding succeeded.
Sampled per-call process RSS peaks were approximately 157–160 MB. Time to first
externally usable result equals return time for this synchronous interface.
The 50-member discarded cold warmup was stopped after 21 minutes 4 seconds
without a typed result. It had published 50 price partitions and nine action
records. Its capture/profiling overlap and incomplete observation are retained;
this is neither a completed baseline nor a production deadline failure. Three
additional full-size baseline repetitions were cancelled before starting. The
candidate must still complete the whole 50-member workload. No N=50 median or
percentage improvement may be inferred from this censored observation.

The replacement two-member baseline uses the same data shape per member, one
discarded warmup and three measured fresh processes:

| Public V2 mode | Median seconds | Min–max seconds | Actual transport attempts |
| --- | ---: | ---: | ---: |
| ACQUIRE_MISSING | 21.656 | 21.605–22.036 | 7 |
| RETAINED_ONLY | 5.116 | 5.093–5.239 | 0 |
| REFRESH_ONCE | 19.519 | 19.086–23.304 | 2 |

All runs completed successfully; sampled per-call RSS peaks were below 175 MB.
Refresh range/median was 21.61%, exceeding the predeclared 20% investigation
threshold. Three supplemental unchanged repetitions completed successfully; the original
slower sample remains included. The budgets below are frozen before production
optimization.

The separate BharatStock one-stock public measurements already credit its
direct-daily behavior. V1 cold/warm/refresh made 2/0/2 price GETs; the zero-call
warm case reused retained evidence. V2 CURRENT_STRUCTURE made 2/2/2 GETs.
Its retained-root invocation uses a current clock, not an exact-request replay.
The request key binds decision cutoff and schedule identities; source inspection
explains why a newer request can require acquisition. The raw timing rows did
not record those key components, so this explanation is a source-based inference,
not a directly recorded identity comparison or proof of a broken cache.

The separate BharatStock series used Python 3.14.6, an advancing system UTC
clock and a 5 ms in-process RSS sampler, rather than the raw series' Python
3.13.7, fixed logical clock and 20 ms external sampler. These are within-workflow
baselines; their absolute timings are not a provider comparison.

| Public workflow | Cold median ms | Retained-root median ms | Refresh median ms | Price GETs (cold / retained / refresh) |
| --- | ---: | ---: | ---: | --- |
| V1 Price Action, two daily rows | 379.3 | 406.3 | 936.3 | 2 / 0 / 2 |
| V2 Structure, 21 daily rows | 394.3 | 350.9 | 352.8 | 2 / 2 / 2 |

Each cell has one discarded warmup and three measured returns. Calendar/mapping
fixture GETs were respectively 3/0/2 for V1 and 3/2/2 for V2, recorded separately
from price GETs. Price responses used one page whenever acquisition occurred.
All 24 public returns met the expected observed/ready assertions. No synthetic
transport retry occurred. These immediate fixture responses do not exercise the
configured 15-second official HTTP timeout, slow sources or real deadlines.
Refresh changed fixture prices, but the harness did not compare recalculated
scalar identities; correctness remains a separate test obligation. All per-run
rows, including setup and sampled process RSS, are in the baseline record below.

## Direct-daily disposition

**Accepted constraint, unchanged:** BharatStock source-reported OHLCV and
Upstox raw minute-derived facts have distinct source and price-basis contracts.
BharatStock already supplies daily rows; repeating its completed migration is
outside #190's work.

**Rejected for the current raw contract:** silently replacing retained Upstox
minutes with another provider or a direct-daily profile. The measured raw shape
has 375 input minute bars per completed daily bar. This quantifies row
amplification only; it is not a measured latency saving or evidence that a new
endpoint would satisfy the same contract. No new direct-daily profile is
currently authorized or qualified here. Its adjustment basis, corporate-action
semantics, session completeness, source observation and retained-reader
compatibility have not been established. Do not infer equivalence from matching
OHLC values, reconstruct missing minutes, or relabel adjusted bars as raw.

**Implemented locally; acceptance pending:** reduce repeated decoding within the admitted
acquisition path. A diagnostic profile across the three one-stock modes recorded
39 provisional-partition loads and 1,211 decoded batches. Its instrumented
cumulative timings overlap and are not baseline measurements. Source inspection
shows full-cohort reinspection around each member effect. Targeted fresh member
inspection may reduce this work while preserving initial/global-mapping/final
full checks and every opener/publication authority guard. The local candidate implements that targeted inspection; timing and independent
review remain pending. No performance improvement is claimed from source shape alone.

## Implementation boundary and adversarial checks

Coordinator owns integration, measurement, documentation, manifest refresh,
tracker state and acceptance. One bounded implementer may own
`market_data/current_raw_acquisition.py` and focused acquisition/public-context
tests after the numeric budgets below are frozen. Independent functional and
security/provenance reviewers must inspect the eventual clean committed
candidate; the diagnosis and test-design workers supply no approval.

The candidate is targeted fresh inspection of the affected member around local
acquisition effects. Initial planning, full replanning after global mapping
acquisition, and final whole-cohort admission remain complete. Each targeted
inspection must freshly validate root/lease, exact schedule and selected
sessions, current mapping, catalog identity and the affected member's full
retained bytes. Existing opener, publication, cancellation and accounting guards
remain. No decoded-data cache, new provider, profile, public schema, persistence
format or research calculation is in scope. At most two measured optimization
experiments are allowed before reassessing the approach.

| Required challenge | Acceptance condition |
| --- | --- |
| Multi-member cold and refresh | Full ordered outcomes and exact attempts survive; unrelated retained row decoding no longer grows with every local effect. |
| Mapping acquisition | One global refresh rechecks every member against the newly retained mapping. |
| Target corruption, orphan, incomplete prefix, conflicting overlap | Existing explicit refusal or bounded acquisition applies before the affected opener; no metadata-only admission. |
| Root, catalog, mapping or schedule changes | Fresh authority checks prevent unauthorized opener/publication; no stale success. |
| Unrelated member corruption during another member's work | Final full admission refuses affected facts; incremental plans never supply final truth. |
| Local 404/malformed response versus shared 401/403/429 | Local failure permits independent later members; shared failure stops later effects. |
| Deadline/cancellation before opener, after response and before publication | Bounded stop, truthful attempt/completion counts, no hidden retry. |
| Settled ledger and physical-plan changes | Preserve attempts, completion and failure records; no added unauthorized slots, at most 5N+1 and 251 calls. |
| Exact close, no-op refresh, finalization and action refusal | Preserve the delivered #189 temporal/independence behavior and canonical result checks. |
| Cohort/row limits and historical readers | Retain existing boundary/limit-plus-one checks and V1 compatibility; measure all 50 members together. |

Focused tests and static checks precede stable-candidate independent reviews.
Expensive final suites, coverage, packages and hosted gates follow correction of
code-level blockers. Performance success never waives these delivery gates.

## Frozen numeric budgets — before production optimization

Frozen by the coordinator under accepted #190 scope on 2026-09-21T18:05:57.837400+00:00.
Baseline revision: `b3465a9695d7f1d8f6284f8f375ccade51917684`.
No executable source or test changes existed at freeze. Original and supplemental
N2 series are retained separately and pooled without dropping any sample. The
three supplemental refresh times were 20.356, 19.515 and 19.066 seconds. They
support a typical approximately 20-second cost but do not explain the original
23.304-second sample. Environmental variability remains an explicit limit;
no causal attribution or elimination of that sample is claimed.

These are offline engineering acceptance budgets for the frozen fixture and
machine, not a product SLA, live-provider promise or altered production deadline.

| Cohort | Cold maximum seconds | Retained maximum seconds | Refresh maximum seconds | Sampled call RSS ceiling |
| --- | ---: | ---: | ---: | ---: |
| N=1 | 12 | 4 | 10.5 | 256 MiB |
| N=2 | 19 | 6.5 | 17 | 256 MiB |
| N=50 | 600 | 180 | 600 | 1,024 MiB |

Each ceiling applies to every measured candidate repetition, not only its median.
For N2 cold and refresh, candidate maxima must also remain below the corresponding
minimum of all six baseline repetitions. The targets are therefore stricter than
merely beating the noisy baseline median. N1 and retained paths are regression
guards; N2 acquisition targets require a material reduction, and N50 ceilings
require usable whole-cohort completion with roughly linear-scale headroom from
the completed N2 workload. N50 has no completed before median and no relative
speedup claim is allowed. Memory ceilings bound the retained fixture/process
working set; sampled RSS can miss sub-sampling-interval spikes.

Candidate measurement: unchanged public harness, environment and per-member
shape; one discarded warmup then three fresh-process measured runs for each
N=1, N=2 and N=50, serialized after focused behavior checks and stable code.
Report all results, variance, setup, sampled memory and limits. Stop a candidate
call exceeding its ceiling and record failure, never a successful sample.
No automatic budget increases or repeated searches for a faster sample. At most
two targeted optimization experiments; reassess or revert if benefit is not
repeatable or integrity would weaken.

Counts remain cold 3N+1, retained zero, refresh N in this fixture (N50:151/0/50),
zero retries, no pagination and no live network. Contract limits remain 1–50
members, 10,000 scheduled minutes and at most 5N+1/251 attempts. Existing
30-second raw opener timeout and at-most-30-minute cooperative invocation
boundary are unchanged; logical-clock performance runs do not prove them.
Adversarial deadline/cancellation tests provide separate behavioral evidence.

Implementation authority is limited to the targeted fresh-member design and
adversarial matrix in this note. Coordinator owns source-manifest refresh and
integration; implementation may not weaken guards to meet these budgets.

## Remaining acceptance

Complete candidate measurements against the frozen budgets and exercise the
affected corruption, identity,
shared-stop, local-failure and final-admission paths. Keep request counts, no
retry/fallback, exact cohort denominators and historical reader behavior intact.
Final evidence must distinguish the configured 30-minute cooperative deadline
and 30-second raw opener timeout from actual elapsed-time enforcement. The
fixed logical clock in the synthetic baseline does not prove real cancellation
or a live latency bound. Independent reviews and applicable final gates remain.

## Focused candidate verification

The local acquisition source SHA-256 after formatting is
`f1a277c0ea35bc57c3eb41c62763c9f5df33de0062dfa758697b301cb2ff980c`.
Seven direct/transitive runtime manifests were refreshed. The discriminating
baseline check observed eight full-plan inspections; the candidate performs two
(initial and final) plus member-local inspections with unchanged provider
accounting. The complete focused acquisition file passed 71 tests, and public
raw V1/V2 context checks passed 235 tests. These are focused checks on uncommitted
candidate bytes, not final repository, review or release evidence.

Three additional deterministic optional-Industry tests passed after that public
selection. A typed local reader failure at one microsecond before the shared
deadline preserves observed raw Structure and direction. Exact deadline and
one-microsecond-over cases preserve `DEADLINE_EXCEEDED`. All three invoke the
real final raw recheck and open no provider request. This proves failure scope
and temporal boundaries with a controlled clock, not wall-clock I/O preemption.
Stock V2 optional contexts remain zero-call `NOT_ATTEMPTED` outcomes; an absent
optional source cannot delay that public command. Neither surface promises
survival after loss of mandatory shared authority or exhaustion of its deadline.

Source Ruff formatting/lint, explicit-interpreter Pyright and Vulture passed.
The initial Pyright attempt resolved the wrong interpreter and failed on missing
installed dependencies; the corrected run reports zero errors and warnings.
Intermediate test-authoring failures remain in the retained evidence. No full
repository suite or hosted gate has run for this candidate yet.

## Initial candidate measurements

One discarded warmup and three measured fresh-process runs for each N=1 and
N=2 completed against the unchanged frozen worker. All per-call latency and
sampled-memory ceilings passed. N1 cold/retained/refresh medians were
9.407 / 2.848 / 8.288 seconds. N2 medians were 17.503 / 5.267 / 15.746 seconds,
versus the six-sample pooled baseline 22.055 / 5.201 / 19.517 seconds.
N2 cold and refresh medians decreased approximately 20.6% and 19.3%; retained
median increased approximately 1.3%, inside its regression budget. These are
local fixture observations, not live-provider or full-cohort speed claims.

Every measured N2 cold/refresh call was faster than the corresponding minimum
of all six baseline calls, not merely the noisy median. For all 18 measured
N1/N2 public results, full recursive comparison found exactly four changed
fields: top-level and completed-context runtime identities, and their enclosing
result hashes. Every other field, including facts, provenance and accounting,
matched its baseline result exactly. Canonical decoding passed in every worker.

[Candidate observations](2026-09-21-current-workflow-candidate.json) retain each
measured time, sampled peak, budget result and comparison boundary. N50 whole
cohort measurement, independent reviews and final gates remain pending. No
N50 baseline median or percentage improvement exists.

## Account and process boundary decision

**Preserve the delivered scope:** Plan 36 explicitly limits accounting to one
invocation/process: at most `5N+1`, hard-capped at 251 provider attempts, with
shared authentication/authorization/rate failures stopping subsequent openers.
The existing account limiter uses process-local thread synchronization; a root
lease coordinates access to that root. Neither mechanism is a distributed
account quota across separate processes or different roots.

#190 introduces no parallel provider acquisition, continuous refresh service or
multi-process scheduler. Its measurements deny real network access; overlapping
local profiling and the separately authorized BharatStock operational capture
were not concurrent authenticated Upstox requests. No account-wide enforcement
or account-wide throughput guarantee is claimed. The accepted per-invocation
boundary is retained rather than adding a distributed coordinator to this
optimization. Any later orchestration that deliberately combines capture and
refresh under the same provider account across processes/roots must first own
an aggregate account budget and its enforcement; it cannot multiply the local
251-call limit and call that an account limit. This is a deployment boundary,
not permission to exceed provider limits or continue after a shared fatal stop.

## Retained measurement record

[The per-run baseline record](2026-09-21-current-workflow-baseline.json) includes
all original and supplemental observations, discarded warmups, sampled memory,
environment and exact harness/raw-output hashes. It omits bulky nested synthetic
results; their identities and original output hashes remain traceable to retained
local artifacts. [The archived harness and protocol](2026-09-21-current-workflow-measurement-protocol.md)
provide reproduction instructions and preserve the measurement boundary. This
is baseline evidence only, not candidate acceptance.

## References

- [Issue #190](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/190)
  owns acceptance and the current evidence record.
- [Plan 35](../plans/35-independent-current-raw-price-context-contract.md)
  owns the raw basis, admitted calendar and 1–50 member bounds.
- [Plan 36](../plans/36-bounded-current-price-context-refresh-contract.md)
  owns one-shot refresh and temporal/compatibility guarantees.
- [Plan 30](../plans/30-capture-forward-adjusted-ohlcv-evidence-contract.md)
  owns exact-request capture reuse and immutable provenance.

Local raw observations and executable measurement scripts are retained under
`~/.codex/artifacts/issue190-20260921/`; a final delivery must provide a durable,
reviewable measurement package rather than treating this partial note as proof
of completed #190 acceptance.
