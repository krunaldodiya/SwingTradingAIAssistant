# Plan 56: latest completed range around the original broken high

Status: accepted bounded Sprint42 specification under the owner's October5,
2026 next-sprint Goal direction and standing full delivery authorization.
Outcome/risk owner: Krunal Dodiya. R3 financial-research fact, privacy and
provenance. Base `1605fb0cdb7174b2c4fbdab9d338e55f6112d13d`, published Sprint41.
Live governing Issue/milestone/Project identifiers belong in the freeze receipt.

## Necessary question and smallest working slice

1. Value: does the latest completed post-event candle's inclusive low/high range contain the unchanged original broken high?
2. Fit: optional descriptive signal-lifecycle evidence; no strategy or eligibility policy.
3. Risk: close-above mistaken for range contact, later pivot substituted for original high, gap/range mistaken for an exact traded tick or successful retest.
4. Smallest alternative: reuse complete Plan54 admission and original causal anchor, compare the one admitted final bar's low/high with exact Decimal ordering.
5. Disposition: accepted after two actual guarded synthetic producer pairs have identical SAME_EVENT, NO_CONTRADICTION_OBSERVED, age1 and ABOVE facts but opposite range-inclusion expectations. No external trading references or new source/model/dependency.

Plan34 necessity is distinct information, not proven market usefulness or
effectiveness. Existing hashes distinguish revisions but supply no semantic
range relation. Existing contracts are correct and unchanged. No Future Issue
is activated. The first working path is both discriminating pairs through the
SDK and actual injected CLI, retaining the original anchor and final-bar witness.
Then finish the complete matrix below within this same sprint.

## Closed contract

`observe_setup_level_range_v1(previous, current)` takes exactly two typed
CURRENT_STRUCTURE observations. First invoke unchanged `observe_setup_level_v1`
for complete producer/packet/runtime/source/bar/diagnostic/time/continuity and
anchor admission, including inconclusive cases. No authored JSON substitute.
For its OBSERVED result only, recover its admitted original high and final
current source bar. Classify `CONTAINS_LEVEL` iff low <= high_anchor <= high;
otherwise `ENTIRELY_ABOVE` iff low > high_anchor, else `ENTIRELY_BELOW`.
Both equality boundaries count as inclusion. Decimal ordering is exact, with
no rounding, tolerance, arithmetic context, close filter or inferred tick path.

Output `causal-setup-level-range@v1`, criterion
`LATEST_COMPLETED_RANGE_VS_ORIGINAL_BROKEN_HIGH@v1`, contains exactly criterion,
contract_version, own runtime identity, previous/current observation hashes,
`level_identity_sha256`, continuity identity/status, full previous/current
redacted rows, status, reason, `range_relation`, witness, limitations and unsigned
result identity. Preserve Plan54's witness exactly, including original and
represented event/high identities and current bar identity; include no raw
price/OHLC/private payload. OBSERVED reason
`LATEST_COMPLETED_RANGE_COMPARED_WITH_ORIGINAL_BROKEN_HIGH`.
Every other Plan54 status/reason/witness is preserved with null range_relation:
replay, no baseline, no later session, UNKNOWN, NON_COMPARABLE, OUTSIDE_WINDOW,
NOT_REPRESENTED, REVISED_EVENT. Inclusion cannot override any such state.
Finite bounds: one stock, two observations, existing21-session windows, one
latest completed bar, canonical sorted compact JSON+LF <=1MiB atomically.

Own closed source-at-rest manifest binds new SDK+CLI, transitively binds unchanged
Plan54 runtime closure; source inventory mismatch/substitution terminal even
on inconclusive inputs. Format sources before refreshing manifest. No old
source, schema, manifest, detector, evidence-v2 or interpretation-v2 edit.
The three range values do not mean confirmation, invalidation, reclaim, exact
traded tick, successful retest, eligibility, recommendation, validity or profit.
Not first contact, any-bar contact or full post-event trajectory. No historical
search, expiry, persistence, monitoring, model or additional acquisition.

## Injected CLI and effects

`setup-level-range` follows Plan54 selectors/absolute storage root/output=json.
Validate request before effects, acquire exactly two serial selector-bound
CURRENT_STRUCTURE observations, evaluate once. Existing acquisition authority
belongs to the injected port. Adapter grants no network/provider/credential/
model/store/backdating/retry or transport authority. Request error exit2
`request_invalid`, zero calls/empty stdout. Admission/runtime/binding/overflow/
interruption error exit2 `setup_level_range_failed`, empty stdout. Successful
inconclusive Plan54 status set exits1; other results exit0. Exit0 is not trade
authorization. Stable explicit retry and concurrent pure SDK calls preserve
inputs and create no files. Guarded actual-producer demo uses fixed synthetic
dates, SDK/CLI byte equality, explicit synthetic disclaimer and no network.

## Frozen adversarial and full delivery matrix

| Case | Required evidence |
| --- | --- |
| Distinct working path | Actual admitted producer spans versus clear-above, identical old factual statuses, different range relation; actual CLI exactly two calls and SDK byte equality |
| Exact bounds | Inclusive low and high equality, just above/below under tiny Decimal context, clear-below, no close-driven range verdict |
| Causal witness | Original high retained despite newer pivot; latest bar only despite an earlier spanning bar; witness exact session/bar/anchor hashes |
| States and precedence | Replay/no-baseline/no-later/unknown/revised/absent/window/noncomparable; no plausible range on inconclusive; complete typed admission first |
| Independent facts | Structural invalidation may coexist with clear-below; age/close/invalidation remain independent; no eligibility/posture policy |
| Corrupt admission | Raw-bar/fact/hash/timing/diagnostic/provenance/stock/source substitution, authored component/packet rejected with redacted failures |
| Runtime integrity | Missing/extra/changed source inventory, changed upstream bound runtime, even replay/unknown fails terminally |
| CLI/effects | Malformed request zero calls, selectors exact, second-call failure/interruption/serialization failure empty stdout; no raw payload/path/error leak |
| Bounds/recovery | Existing21/plus-one typed bounds, canonical1MiB/plus-one, explicit retry determinism/input immutability/concurrency, prior wheel rollback |
| Compatibility | Existing SDKs/manifests/contracts/dependencies/workflows unchanged, all seven previous installed maps retained verbatim |
| Installed distribution | Actual isolated installed SDK+CLI contains/above/below/low-equal/high-equal/replay/unknown with strict envelope, hashes, witness, canonical privacy checks; no mocked acceptance |
| Full lifecycle | Two complete independent exact-candidate domain and security/privacy/provenance reviews, GitGuardian, full hosted tests>=87% aggregate branchcoverage/static/sdist/wheel/nativeOCI/adversarial/interruption/priorwheel; gated normal merge/exact-main/private publication/fresh pulls/full archives/live tracker/localmain |

## Ownership, continuation and authority

Coordinator sole source writer/integrator/tracker owner. Owned new SDK, CLI,
manifest, focused tests, guarded demo, Linux verifier and related verifier
tests, Plan56/Sprint42/operator and small related roadmap docs. No dependency,
workflow, old runtime, old manifest, retained-data or global configuration edits.
Two fresh independent read-only complete reviewers after stable committed bytes;
exact base/head/tree, complete diff/contract/evidence, pre/post clean identity
checks. No nested delegation, writer cannot approve own candidate. Inherited
host model/effort; optional telemetry unavailable disclosed. Handbook primary
TDD plus scoped governance/release/agile requirements-specification fallback.

Start persistent Goal only after this freeze and live Issue/private Project/
Sprint42 milestone/field readback. Owner authority covers routine implementation,
focused repairs, reviews, draft/ready PR, normal gated merge, exact main/private
publication/fresh pulls, full archives, tracker/localmain closeout. No redundant
approval. Fresh included shared account capacity/storage/reset and Actions AND
Packages $0 StopusageYes before every hosted trigger/retry/merge. Current
Issue250/Plan55 hosted-only controls supersede historical self-hosted paragraph;
no heavy local/self-hosted fallback, automatic rerun, paid/public/access/settings
workaround, admin/directmain/deletion. Approved owner .venv outside worktrees,
candidate imports; no installs/copies. Preserve prior worktrees/evidence.
Stop only dependent genuine authority/source/provider/credential/protected/
destructive/conflicting owner-work/failed-gate/unavailable evidence/unaccepted
residual-risk effects. Provider safety refusal INVALID/NO VERDICT, no bypass.
Full original matrix and live lifecycle must agree before Goal completion.

Signal phase remains incomplete: all eight Plan47 obligations distinct.
Later improvements: multi-session contact/first contact, evidence-v3/consumer
handoff, trading policy, confirmation/expiry/eligibility/monitoring/persistence,
Future sources, model/history/broker/money/risk/capital/position work deferred.

## Provisional remaining-product estimate

Owner requested an estimate before starting. Coordinator planning assumption:
roughly20–30 more bounded sprints for the core listed-equity swing-research tool,
including this sprint: signal rules/lifecycle/safety6–10; risk/capital/read-only
portfolio4–6; historical/AI-consumer evaluation/paper observation5–8; daily-flow
integration/final qualification3–5. Overlapping work explains the overall range;
not a sum of committed backlog items, accepted future scope, countdown, delivery
date or phase-completion percentage. Excludes all five Future issues. Real
market observation adds calendar time. Refresh after material scope/evidence.

## Accepted CI runtime recovery amendment (2026-10-05)

The owner directly replied "approved" to the prepared four-line recovery after qualification attempts `37336362844/1` and `/2` both reached the unchanged one-hour limit. This accepts only a narrow workflow exception: in `.github/workflows/ci.yml`, the `quality` and `main-backstop` job limits become 90 minutes, and both complete pytest commands gain `-vv --durations=0 --durations-min=0`. Detailed names are emitted during execution; full setup/execution/teardown durations depend on actual test completion. This is diagnostic room, not a demonstrated root-cause fix or performance improvement.

All original 13 requirements, eight criteria and twelve matrix rows remain required, with an explicit exception to workflow byte compatibility for these four lines. Runtime sources/manifests, selectors, two workers, dependencies, static/87% branch-coverage/build/installed/nativeOCI/adversarial/interruption/priorwheel gates, admission, permissions and private full lifecycle remain unchanged. Both complete failed archives remain failed, never acceptance.

The new stable complete candidate requires both independent exact-candidate reviews expanded to CI/admission/privacy. Exactly one initial measured qualification execution is authorized after fresh whole-account included capacity (reserve >=300 minutes for quality90/main-fallback90/publication60 and rounding) and Actions AND Packages $0 Stop-usage-Yes budgets. No automatic rerun, paid/public/access/settings/heavy-local/self-hosted fallback or lowered gate. If it cannot finish within90minutes, retain diagnostics and stop the dependent release until an evidenced correction or additional owner direction exists. Review the diagnostic/resource exception after the measured run; its retained 90-minute resource cap remains the explicit scoped owner decision, not retry authority.

The amended Plan56 appendix records the same accepted exception. Original accepted freeze below is retained verbatim as historical baseline and superseded only for these four workflow lines.

## Accepted compact CI diagnostics amendment (2026-10-06)

The owner directly answered "Approve proposed recovery" to the prepared exact
two-line correction after run37356966260/1 exceeded the approved90-minute
limit. In both existing complete pytest invocations, replace
`-vv --durations=0 --durations-min=0` with
`-q --durations=20 --durations-min=1`. Both job limits remain90minutes.
This supersedes only the earlier diagnostic flags: compact progress and the
20slowest recorded setup/call/teardown phases taking at least1second replace
full test names and exhaustive phase printing. Timing output depends on
actual test completion. Output amplification is measured; the timeout root
cause, speed improvement and full-run success remain unproven.

Preserve the original13requirements, eight Issue criteria and twelve matrix
rows; this is solely another explicit workflow-byte diagnostic exception.
All7,250 selected tests, two workers, dependencies, old runtime/manifests and
seven old installed maps, static/87%branchcoverage/build/installed/nativeOCI/
adversarial/interruption/priorwheel/admission/private-publication gates and
permissions remain required. Both old full cancelled archives and the new
empty archive plus partial individual-job response remain failed evidence,
never full acceptance. The run-level archive for37356966260/1 is empty and
its recovered individual-job response is incomplete; do not claim complete
phase measurements or complete archived logs for that attempt.

After both fresh independent exact-candidate reviews and bounded diagnostic
positive/failure/private-exclusion checks, authorize exactly ONE new complete
qualification with fresh whole-account included capacity (reserve>=300minutes)
and Actions AND Packages$0 StopusageYes checks before the trigger and merge.
No automatic rerun, longer cap, lowered gate, paid/public/settings/access/
heavy-local/self-hosted fallback. Preserve all earlier decisions and freezes.
If it cannot complete, retain actual evidence and stop dependent release for
a separately evidenced correction or owner direction. Full main/private
publication/tracker/localmain closeout and all original scope remain required.
