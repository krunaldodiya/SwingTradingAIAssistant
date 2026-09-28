# Plan 39: completed-session Volume context

Status: frozen first implementation contract; not delivered.
Owner: Krunal Dodiya. Risk: R3. Sprint 26 / [#226](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/226).
Authority: owner selected Volume context on 2026-09-28 and requested planning
and implementation. Plan 34's admission gate applies. Baseline is
`f39731d538de07fc6bb5a7fdf184c837397c398d`.

## Necessary-only evaluation

1. Value: answer whether a completed session's reported volume is above, equal to or below its preceding-session baseline; existing price/structure facts cannot answer this.
2. Fit: one descriptive daily Volume fact over explicit canonical NSE equities; additive research context with no filter or effectiveness claim.
3. Risk: incompatible units, corporate actions, incomplete sessions, future knowledge, source substitution and division by zero can create misleading comparisons.
4. Smallest alternative: the AI cannot calculate from raw bars; reuse admitted Upstox raw daily evidence and Plan-21 screening, adding one deterministic calculation rather than a new provider or archive.
5. Disposition: accepted for the bounded retained-only CLI/SDK slice below. Broader Volume analysis and agent-dossier integration remain deferred.

## First working outcome and exact calculation

Add `market-data volume-context-current --input-file ABSOLUTE_PRIVATE_JSON
--storage-root ABSOLUTE_PRIVATE_ROOT --output json` and an equivalent Python
boundary. One response covers an explicit ordered 1–50-member canonical cohort.
Retained-only means no credential lookup, provider requests, repair or data writes.
The existing ingestion workflow supplies prerequisites; this slice does not
claim a cold-start acquisition experience.

The closed maximum-64-KiB request is `current-volume-context-request@v1` with
`contract_version`, `data_selection_time`, `admission_deadline`,
`schedule_identity_sha256`, and `members`. Members use the existing Plan-35
canonical member fields. Reject duplicate/unknown keys, invalid JSON values,
duplicate identities/symbols, unsupported instruments and invalid intervals
before effects. Selection/deadline are UTC, at most 30 minutes apart and before
IST rollover. Bind canonical request bytes, exact ordered selection, canonical
cohort and schedule identities. Preserve caller order and missing members.

Select the latest 21 official completed sessions S0..S20 at selection time.
The baseline is precisely the arithmetic mean of volumes S0..S19; S20 is
excluded from its own baseline. Require 21 regular, equal-duration completed
official sessions in this first slice; special or unequal-duration sessions
return unsupported rather than normalizing by minutes. Reuse existing bounds
of 64 calendar days and 10,000 selected minutes/member.

For integer volumes v0..v20, each in [0, 2^63-1], let B=sum(v0..v19).
When B>0 return the exact rational baseline B/20 and relative volume (20*v20)/B
as reduced numerator/denominator pairs, with ABOVE/EQUAL/BELOW from comparing
20*v20 with B. Do not use floating point, configurable thresholds or a
high/low/normal participation label. A zero latest volume is a valid ratio
zero if B>0. B=0 is `ZERO_BASELINE`, with no ratio or relation. Missing or
invalid volumes are never filled, skipped or used to shrink the baseline.

## Evidence and comparability

Only `UPSTOX / RAW / 1d-derived-from-retained-1m` is supported. Volume remains
source-reported unadjusted volume; no rescaling or assertion of institutional
activity, liquidity sufficiency or independent exchange certification.
Reuse exact retained Plan-35 calendar, mapping, raw-minute completeness and
Plan-21 corporate-action admission. An action observed anywhere in S0..S20
withholds the affected member; unavailable screening likewise withholds it.
The screen is nonexhaustive provider evidence, not proof of no corporate action.
State that limitation with every result. Historical point-in-time claims are
out of scope; preserve actual retained knowledge times and current cutoffs.

Expose volume only through a producer-bound retained-evidence boundary. No
caller-supplied list of numbers, copied JSON or self-declared hash establishes
production evidence admission. A pure math helper is testable independently
but cannot mint an observed research result. Reuse the existing raw reader and
its held lease; any private volume binding must be byte-bound and revalidated
with the exact raw inputs before return. Preserve old public projection bytes.

## Result, failures and compatibility

`current-volume-context@v1` binds request/result/calculation/runtime identities,
source and volume basis, ordered members, selected sessions, selection and
evidence cutoffs, source knowledge times, mapping/partition/screen identities,
availability/reasons and optional exact fact for each member. No raw bar series,
provider bodies, paths, credentials or exception strings are exposed. Keep all
output owner-private under existing source-use boundaries. Bound output to 1 MiB.

Missing calendar/mapping/bars/screen yields explicit dependency/insufficiency;
one member's absence does not suppress another admitted member. Never aggregate
or rank a reduced cohort. Unsafe/held/replaced roots, catalog corruption,
unexpected errors, source substitution and interruption are terminal with no
partial JSON. Treat ambiguous legacy corruption outcomes as terminal at this
new boundary, rather than calling them ordinary optional absence. Integrity
checks take precedence over zero-baseline or optional missing evidence.
Elapsed deadline/date rollover stops the request; never backdate or clamp time.
Exit 0 means every requested Volume fact is observed, 1 means an explicit
nonready result and 2 means malformed input or terminal internal/storage failure.
These exits never establish trade eligibility.

Existing price, structure, packet and agent V1–V4 contracts/defaults remain
unchanged. No change to their mathematics, schema, public bytes or exit behavior.
Format runtime sources before refreshing every directly/transitively affected
source manifest. New Volume code requires its own source identity coverage.

## Frozen adversarial and acceptance matrix

- Independent arithmetic expectations: above/equal/below, fractional mean,
  zero latest, zero baseline, maximum integers, ambient Decimal precision,
  20/21/22 lengths, negative/bool/float/nonintegral/oversized volume rejection.
- Real temporary-root producer positive through actual CLI; no private data,
  network or credentials. Missing calendar, mapping, minutes, action screen,
  observed actions and missing members; malformed and conflicting evidence.
- 1/50/51 members, duplicates/reordering, unknown/duplicate JSON keys,
  unsafe request files, canonical identity/source/basis substitution.
- Completed versus partial sessions, equal-duration versus special sessions,
  future knowledge, selection/deadline edges, clock regression and IST rollover.
- Corruption/substitution during projection and final recheck, corruption plus
  zero baseline/missing member, held/replaced root, interruption/retry with no
  writes and identical retained identities. No partial JSON on terminal errors.
- Existing price/agent compatibility, source-manifest consistency, private-output
  checks, installed-wheel command and source-checkout-independent runtime proof.

Tests first. Focused checks and static analysis precede stable candidate review;
full configured suite/coverage, build/installed and hosted gates remain required
for delivery. Independent functional/domain and security/privacy/provenance
reviewers inspect the same clean committed bytes without editing. Synthetic
evidence does not prove live-provider behavior or effectiveness.

## Ownership and continuation

The Codex coordinator owns the contract, implementation, shared files, tracker
and integration in isolated branch `codex/sprint26-volume`. Model/effort are
inherited; no independent reviewer or model telemetry is yet claimed. No
subordinate implementation agent or persistent goal has been started.
Runtime work is limited to a Volume module, its raw admission seam, CLI,
necessary source manifests, behavior tests and usage documentation.
Existing provider acquisition and private stores must not be modified or used
for execution. Pause only dependent work for source/authority ambiguity,
scope expansion, conflicting changes or release authority.

The desktop worktree tool failed with `Git is unavailable`; shell Git created
the isolated checkout instead. GitHub Issue #226 creation/readback passed.
GitHub Project and milestone tools are unavailable in the connector; sprint
number is owner-selected planning terminology, not a claimed milestone assignment.
No configured memory tool is available; this contract and the issue preserve
the decision. Release and full acceptance are still pending.
