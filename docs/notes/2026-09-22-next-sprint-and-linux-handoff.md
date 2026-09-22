# Next research-assistant priorities and Linux handoff

Date: 2026-09-22
Owner: Krunal Dodiya
Status: accepted documentation of planning direction; implementation contracts,
numbered sprints, dates and GitHub milestone assignments are not yet approved
or created by this record.

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
