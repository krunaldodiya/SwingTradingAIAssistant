# Next research-assistant priorities and Linux handoff

Date: 2026-09-22
Owner: Krunal Dodiya
Status: accepted documentation of planning direction; implementation contracts,
numbered sprints, dates and GitHub milestone assignments are not yet approved
or created by this record.

**Later checkpoint — 2026-10-01.** Scheduling, delivery and restore instructions
below are September 22 history. Later accepted Plans and live GitHub govern:
[Plan 42](../plans/42-agent-volume-relative-strength-context.md) / closed
[#235](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/235) delivered
Volume and Relative Strength agent context; [Plan 43](../plans/43-single-stock-loss-scenario.md)
/ closed [#237](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/237)
delivered bounded caller-supplied loss-scenario arithmetic. Neither establishes
a validated strategy or full risk assessment. The Linux Hindsight restore step
is historical, not a current installation prerequisite; selected recovered
knowledge is being reconciled under [#234](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/234).

## Decision and context

After closing parent #172, the owner asked what would make the product a usable
swing-trading research assistant, independent of the existing future backlog.
The discussion prioritized an end-to-end research experience over adding a
catalogue of analytical modules. The owner then agreed to retain existing
future issues under named future sprint themes instead of leaving them orphaned.
The immediate request is documentation only, before replacing macOS with Linux.
Do not start implementation, create issues or assign milestones from this note.

The roadmap and upcoming-sprints overview link this decision. It records
priority and proposed scope, not a replacement for architecture, Plan 34's
necessary-only feature admission, source authorization or delivery gates.

## First priority after migration

**Single-stock, evidence-backed research through an external AI assistant.**

**Accepted broad direction, clarified 2026-09-23.** The first consumer was a
local coding assistant using the existing CLI. The broader product is primarily
consumed by an AI harness; manual use is secondary. Question-specific single-
stock and bounded-list factual workflows are intermediate capabilities, not the
final research experience. Eventual candidate and BUY, HOLD, EXIT or NO_TRADE
reasoning belongs to the consuming AI over supplied evidence. Strategy labels,
eligibility/risk rules, ranking, portfolio state, source authority and historical
and out-of-sample validation need separately accepted contracts before actionable
claims. The [architecture boundary](../architecture-freeze-v1.md#external-consumer-ai-agent-harness)
still assigns deterministic facts and calculations to the tool and excludes
broker orders. This clarification does not approve a signal, provider or sprint.

Provenance: recovered project-context records
`codex-20260922-swing-single-stock-planning` (2026-09-22) and
`codex-20260923-product-endstate-nifty100-agent-signals` (2026-09-23), reconciled
under #234 against the current architecture and accepted Plans on 2026-10-01.

Start with one supported stock and completed daily sessions. Reuse the existing
CLI/SDK and deterministic calculations. Select the smallest agent-facing
interface after inspecting the actual consumption gap; MCP, a new API, a new
provider and a dashboard are not predetermined requirements.

The three proposed user acceptance questions are:

1. Explain PNB's latest completed-session price behaviour and current structure.
2. What changed since my previous research snapshot?
3. What evidence is missing, stale or conflicting, and which conclusions remain
   supported?

Before implementation, freeze the smallest working contract for these questions.
The desired experience separates observed facts, AI interpretation and missing
evidence; binds numerical claims to sources, timestamps and evidence identities;
reuses captures; and bounds any explicitly authorized acquisition. Demonstrate
complete, partial, stale and conflicting inputs. Missing optional context must
not hide independent admitted facts. Research readiness is not trade eligibility.
Snapshot comparison needs two compatible observations; never invent a previous
snapshot or compare incompatible price bases as equivalent.

The deterministic tool continues to own calculations. The external AI explains
structured facts and does not calculate from raw OHLC, invent missing values,
silently substitute providers or place orders. Fresh Market Regime, Industry and
event acquisition is not already supplied by the V2 single-stock command;
inspect existing context capabilities and freeze any required integration scope.

## Subsequent product sequence

| Order | Intended outcome | Scope boundary |
| --- | --- | --- |
| 1 | Single-stock AI research experience | The bounded flow above, using delivered facts. |
| 2 | Watchlist comparison and factual screening | Explicit criteria, bounded canonical stocks, reasons for matches and missing evidence; no unexplained composite score. |
| 3 | Missing analytical context | Evaluate one Volume fact, then one Relative Strength fact only if an unmet question passes Plan 34's admission gate. These modules remain unapproved. |
| 4 | Risk-aware candidate assessment | Approve deterministic liquidity, invalidation, gap, cost and exposure rules before actionable trade-plan claims. Risk remains a prerequisite for those claims even if other work is scheduled first. |
| 5 | Read-only monitoring and outcome evaluation | Watchlist/holding changes, retained research decisions and later outcomes without hindsight or broker execution. |

Broad SMC/pattern catalogues, indicator proliferation and infrastructure
expansion are not prerequisites for the first usable research experience.
Historical qualification and performance claims retain their separate gates.

## Existing future issues: intended sprint homes

These are planning associations only. Keep the issues in the future backlog
until their entry conditions are met. Sprint numbers, dates and actual GitHub
milestones will be assigned when scheduling is committed. The table is not a
promise to execute all six in its row order.

| Issue | Intended named sprint / milestone | Entry condition |
| --- | --- | --- |
| [#177](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/177) | Reliable daily research operations | Dependable daily capture and recovery needs are scoped. Current ad hoc backups do not fulfill the complete encrypted-backup and verified-recovery issue. Closest supporting work to the next sprint, but its full scope must not delay the first research experience. |
| [#139](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/139) | Research evaluation and outcome tracking | A bounded historical decision/screening study needs point-in-time backfill; retain its existing prerequisites and causal knowledge limits. |
| [#144](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/144) | Historical evidence and price comparability | A specific study requires both raw and adjusted price bases; revalidate source authority before implementation. No provider is reactivated by this placement. |
| [#178](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/178) | Company and event-risk context | Basic research flow works and one concrete question establishes the need for bounded fundamentals. |
| [#167](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/167) | Portable assistant delivery | Installing and using the product outside the development environment requires the accepted native/container distribution scope. The owner's OS migration alone does not complete this issue. |
| [#126](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/126) | Reusable market-data distribution | The public package boundary is stable; retain one authoritative market-data implementation. This is separate from delivering the assistant itself. |

## Checkpoint before the OS migration

- Parent [#172](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/172),
  slices #186–#190 and routing documentation #199 are closed and Project Done.
  [PR #201](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/201)
  merged as `3fdc6e4efcb0fdeb2b42a181d223ea1e6efb4977` with the reviewed
  tree, required reviews, 5,162 local tests, hosted checks and main admission.
  Older documentation saying #172/#190 are open is a superseded checkpoint.
- The 15 old draft PRs were reconciled and closed: 13 heads were already in
  main, #13 was patch-equivalent, and #3 was superseded. Their history and
  branches remain preserved. At that audit there were zero open PRs and six
  open future issues; recheck live state after migration.
- Extra worktrees were removed. The original project retains unrelated owner
  changes on `chore/project-system-instructions`; it is not a clean main
  checkout. Do not reset or discard those changes. Local recovery is under
  `~/SwingTradingAIAssistantData/worktree-retirement-20260922` and retained
  delivery evidence under `~/.codex/artifacts/issue190-20260921`.
- [Drive recovery folder](https://drive.google.com/drive/folders/1lpf-J3oKrpTYBaKyP_iUuVTx0Uwpaprk)
  contains [captured data](https://drive.google.com/file/d/1VGq1kbGP0C96M8xT6lZQc1kp1o_rcqsv/view),
  including the September 21 capture, and [Hindsight exports](https://drive.google.com/file/d/1lpC31dtm3m7Y_KKIIylKzAbGoBL04z7c/view)
  for both `pi-global` and `pi-projects`. The old Hindsight archive was preserved.
  Capture backup excludes its reinstallable runtime and the private worktree
  recovery directory. Hindsight is a portable export, not a Docker-volume image.
  Local integrity passed; Drive sizes/readback passed, but remote checksum
  equality and a Linux restore have not been established.
- These backups do not prove that unrelated local edits, private recovery
  files, credentials or every migration dependency are safe to erase. Preserve
  any still-local work and securely migrate/re-establish credentials before
  formatting. macOS Keychain contents do not travel in the data archive.

## Recovered operating distinction — reconciled 2026-10-01

**Status: accepted discussion rationale, scoped to routine authorized capture.**
On September 15 the owner distinguished execution of an already reviewed CLI
for a bounded, authorized capture from feature development. Routine operation
does not need a new independent code review each day; direct built-in
exact-read, reparse and reuse verification plus truthful bounded evidence remain
required. Anomalies and code, configuration, process, provider or schema changes
retain their applicable review and authority gates. This record grants no new
provider, credential, recurring-capture or scheduler authority and does not
waive review of a changed implementation.

Provenance: original user correction of 2026-09-15 in recovered document
`pi-session:98d17070f2f9c631`, decision memory
`7988c98e-4245-44b9-98e4-0300d05b337d`; current
[canonical delivery controls](../mandatory-agent-instructions.md#delivery-and-evidence-controls)
continue to govern changes.

**Accepted operating preference, clarified 2026-09-18.** The owner directed
normal current-day BharatStock capture at or after 20:00 IST. A separately
authorized request for an already completed past session does not inherit a
wait until today's 20:00. Keep the historical target date and actual acquisition
and knowledge times; later retrieval cannot prove earlier availability. This
preference is compatible with the [roadmap's source-availability guidance](../roadmap.md):
it is no provider publication guarantee, new executable timing gate, recurring
schedule or present acquisition authorization. Provenance: original user
correction in `pi-session:19cc17c2a4fc52f0` (2026-09-18), decision memory
`733c60a7-9c5b-4df4-b3a1-3b8148d2e707`.

## Additional recovered proposals and operating context — 2026-10-01

**Proposed: explicitly gap-aware summaries.** The September 9 discussion
considered describing observed data when a requested window is incomplete.
Twenty observed sessions in a 21-session window must remain labelled incomplete;
an endpoint return or mean of observed values would need its own accepted
definition. This proposal does not approve those calculations, filling gaps,
substituting older bars, or treating partial coverage as confidence. Existing
[Plan 30](../plans/30-capture-forward-adjusted-ohlcv-evidence-contract.md)
feature-specific evidence requirements remain unchanged. Source: recovered
document `01a01d42-f289-7000-9d9a-c9025138589d`, September 9 owner/assistant
turns 1614–1615 in the private crosswalk.

**Proposed: separately qualified BharatStock-only generation.** The September
10–11 discussion considered an exact coverage inventory, acquisition budget,
new dataset generation and validation before switching consumers. Preserve
original Yahoo and earlier BharatStock evidence and actual knowledge times;
one provider does not by itself establish equivalent adjustment semantics.
Bulk regeneration was excluded from that evening's capture scope. This is no
completed migration or present download authorization. Source: the same recovered
document, September 10–11 turns 1738 and 1922–1923.

**Open: recurring capture activation.** September 11 intent favored a visible
existing coordinator over a hidden headless process. Useful proposed operating
requirements include the actual exchange calendar, duplicate prevention and
explicit interrupted or missed outcomes; a weekday-only schedule cannot cover
exceptional sessions. Present activation, retry and catch-up bounds remain
unverified. This historical intent does not install a scheduler, authorize new
provider effects or mandate the old harness. Source: the same recovered document,
September 11 turns 1908 and 1922–1932; current authority remains the canonical
adapter and the separately scoped operating request.

**Accepted historical preference: self-hosted research routing.** On September
11 the owner corrected use of Firecrawl Cloud: the intended route was the
existing self-hosted deployment. Prior Cloud-sourced research must retain that
provenance. Do not infer Cloud login or fallback permission from that request.
Old host variables and endpoints do not prove current Linux availability or
create a universal harness requirement. Source: the same recovered document,
owner turns at 18:25:07 and 18:31:02 UTC, corroborated by recovered records
`0a577cce-d990-4521-aba0-73c894f18ae7` and
`d8a94c61-3e5c-4002-9fdb-711cf0da90b1`.

**Accepted historical preference: handbook synchronization.** The August 28
owner request favored retaining handbook changes in GitHub; the adjacent
discussion proposed coherent reviewed PR batches. This is cross-repository
context, not a second handbook policy or authority to edit that repository here.
The canonical adapter reserves those changes to the handbook's own governed
workflow. Source: the same recovered document, owner turn at 03:57:59 UTC and
its adjacent response; the document's August 20 creation date is not the date
of that discussion.

**Historical privacy boundary, September 3.** The handbook publication record
kept earlier repository history in a separate private archive because it
contained sensitive operational material. Preserve that archive and its
historical branches and pull-request references as private; a synchronization
preference does not authorize publishing those older refs. This note makes no
claim about the archive's present availability or backup verification. Source:
recovered record `c6256d8e-7ff5-4a3c-97db-4db4b505b916` and the September 3
00:48 UTC publication report in `01a01d42-f289-7000-9d9a-c9025138589d`.

**Open historical design: explicit correction attempts.** A September 16
assignment referred to Issue #198 and proposed a distinct attempt for an exact
incomplete 100-stock, one-session capture: zero observed, 100 insufficient,
zero unattempted and no shared failure. Ordinary reuse would remain effect-free.
A correction would pin the admitted parent, ordered cohort, selection, schedule
and configuration, use the actual later cutoff, and reserve a separate private
attempt before credentials or provider calls. Duplicate, concurrent or
interrupted attempts would not silently replay effects. Bounded retained
responses and a provider-free verification path would preserve lineage and
actual counts; unchanged material content would produce an unchanged-attempt
receipt rather than an invented new revision. All earlier evidence would survive.

The owner explicitly paused this work on September 16 at 19:18:45 UTC. The
handoff reported uncommitted changes and tests that preceded later edits; it
did not establish a verified final implementation. Present tracker lineage and
delivery remain unverified. Retaining this proposal neither resumes it nor
establishes general retry, scheduling or acquisition authority. Source:
`pi-session:af10bcc3e6ea0ff6`, initial assignment at 18:57:20 UTC and the pause
and handoff at 19:18:45–19:18:50 UTC; corroborating pause record
`pi-explicit:2759581e312a82d5:db5b9e8ec8981e29`.

## Resume on Linux

1. Read this decision, then the current canonical project instructions and
   live tracker. Restore the latest main and preserved owner work separately.
2. Restore captured evidence and both Hindsight banks; verify restore results
   and private filesystem permissions. Recreate Linux environments rather than
   copying macOS virtual environments or assuming the old paths work.
3. Retrieve this decision from Drive if it has not yet been merged. This
   documentation-only handoff is not evidence of a GitHub commit or release.
4. Resume with the single-stock research experience. Define its governing
   implementation scope and acceptance criteria, then schedule future issues
   against the named themes when their prerequisites justify activation.

No new issue, PR, implementation, live market call, scheduled job or milestone
change is part of this documentation task. Only `git diff --check` is required;
do not run tests, builds, GitHub Actions or GitGuardian for this prose change.
