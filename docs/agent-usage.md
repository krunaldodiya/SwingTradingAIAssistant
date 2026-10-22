# AI agent tool usage guide

Status: **ACTIVE USAGE GUIDE** — the single source of truth for how an AI agent
(an external assistant or harness) uses this deterministic research tool.

This guide routes every research question to the exact installed command, states
what input it needs, how to read the result, which claims the result supports,
and links the authoritative contract for full detail. The linked contracts own
the normative semantics; where this guide and a linked contract — or actual
command output — disagree, the contract/output wins. Report the discrepancy
instead of guessing.

Audience: an external AI assistant consuming this tool, and the owner or
operator assisting it. Repository mission and hard boundaries:
[architecture-freeze-v1](architecture-freeze-v1.md). This is not the
development-agent workflow; that is [AGENTS.md](../AGENTS.md) plus
[agent-workflow.md](agent-workflow.md).

**Contents**

1. [Your role: facts from the tool, explanation from you](#1-your-role-facts-from-the-tool-explanation-from-you)
2. [Universal rules before running anything](#2-universal-rules-before-running-anything)
3. [Pick your question, then run the command](#3-pick-your-question-then-run-the-command)
4. [Capability reference](#4-capability-reference)
5. [Version labels are not one axis](#5-version-labels-are-not-one-axis)
6. [When a command does not return facts](#6-when-a-command-does-not-return-facts)
7. [Operator, capture and internal commands](#7-operator-capture-and-internal-commands)
8. [Documentation index](#8-documentation-index)
9. [Known documentation conflicts and follow-ups](#9-known-documentation-conflicts-and-follow-ups)
10. [Keeping this guide current](#10-keeping-this-guide-current)

## 1. Your role: facts from the tool, explanation from you

The deterministic layer (this repository) owns anything a machine can establish
exactly: retained market-data evidence and its provenance, completeness and
admissibility checks, arithmetic (price change, relative strength, volume
ratios, loss math), timestamps and source identities, safety/circuit gates, and
the explicit decision vocabulary (`OBSERVED`, `READY`, `MATCH`, `UNKNOWN`,
`NO_TRADE`, `INSUFFICIENT_EVIDENCE`, `RESEARCH_CANDIDATE`, ...).

You (the external AI assistant) own the explanation and comparison of the
structured facts the tool returns. You must never:

- read candle files, provider payloads, or retained raw market data and derive
  your own facts from them;
- compute indicators, structure levels, ratios, or dates from raw bars;
- invent, estimate or backfill a fact the tool did not return;
- turn a non-result (`UNKNOWN`, `NO_TRADE`, `NOT_READY`,
  `INSUFFICIENT_EVIDENCE`, `UNAVAILABLE`) into a positive claim;
- place orders, set targets, or assert recommendations, returns, win rates,
  rankings, or effectiveness.

This is a research-only tool. It never trades, never sizes positions and never
assesses a portfolio.

## 2. Universal rules before running anything

### 2.1 Commands and credential injection

Commands are console scripts installed with the project (`market-data`,
`signal-decisions`, `stock-observations`, `stock-safety-evidence`, and the
operator scripts in §7). In the owner's environment, commands that contact a
provider are wrapped for credential injection as `doppler run -- <command> ...`;
retained-only commands read no credentials and make no provider call. Each
capability below marks provider access where the contract documents it.

### 2.2 Private inputs and disclosure

- Storage roots are absolute **owner-private** directories (mode `0700`), e.g.
  under `~/SwingTradingAIAssistantData/...`. Never point a command at the
  repository, a shared, or a temporary location. Commands that require an
  existing root never create or repair it.
- Request files are absolute owner-private regular files (typically mode
  `0600`), not symlinks or hard links, with a bounded size (often 64 KiB).
  Run the command from the owner's machine with the owner's authorization.
- Outputs and derived facts stay inside the owner's disclosure scope. Some
  outputs are explicitly **not authorized for hosted-AI disclosure** (for
  example agent research V3/V4 event and cohort context); each contract states
  its own limit. Keep credentials, private paths, provider payloads and raw
  bars local.

### 2.3 Exit codes (consolidated)

| Exit | Universal meaning |
|---|---|
| `0` | The requested facts were established. What "established" means is per capability; `0` never means trade eligibility, approval, or a recommendation. |
| `1` | A valid, structured result that establishes no positive fact: not ready, missing evidence, `UNKNOWN`, `NO_TRADE`, `INSUFFICIENT_EVIDENCE`, `BLOCKED`, or an unavailable disposition. Read the JSON — it names the state and the reasons. |
| `2` | The request was rejected or the run failed before any report: invalid or malformed request, unsafe or missing private path, unsupported schema, structural rejection, or sanitized internal failure. Usually nothing is on stdout — but `market-data download`/`coverage`/`query` emit a terminal rejection/unavailability envelope on stdout for some admission paths; never read a terminal envelope as market facts. Treat exit `2` as "no evidence was produced" and fix the request. |

Command families with extra codes:

| Exit | Meaning | Commands |
|---|---|---|
| `3` | Partial coverage (some partitions succeeded) or whole-result insufficient evidence | `market-data download`, `market-data coverage`, `market-data query` |
| `4` | Evidence unavailable | the same three commands |
| `5` | Acquisition failed | the same three commands |
| `130` | Operator cancelled | the same three commands |
| `3` | One fixed "unavailable" diagnostic (not partial coverage) | `historical-census`, `evidence-readiness` |

stderr is never data. On exit `2` (and the fixed `3` above) stderr, when
non-empty, carries one sanitized token such as `request_invalid`,
`internal_error`, `unavailable`, or `probe_failed`; on the stdout-envelope
paths above it stays empty. Never parse stderr text as market facts.

### 2.4 Evidence discipline

- Completed-session facts and current/provisional facts are different evidence
  classes, and the tool labels them. Never present a provisional value as a
  completed-session fact.
- Selection, observation, known-at and retrieval times are part of the
  evidence. Never backdate a value or relabel a later observation as earlier
  knowledge.
- The tool substitutes evidence only where a contract explicitly defines an
  admissible fallback (for example the documented swing completed-session
  fallback). Absent such a rule, a missing fact stays missing: no provider
  switch, no older-row substitution, no "close enough".
- Retained evidence is immutable. Read records exactly by their handles; never
  "fix" or reinterpret a retained record.

### 2.5 What you may claim

| Evidence state | You may say | You may not say |
|---|---|---|
| Facts established (exit `0`) | restate and compare exactly the facts, labels and boundaries the contract permits | advice, targets, expected moves, "good stock", trade instructions |
| Structured non-result (exit `1`) | which fact is missing or not ready, and the reason token | the stock is bad; a move is coming; the evidence exists somewhere else |
| Rejection (exit `2`) | that the request was rejected and why | any market fact from that invocation |

Standing no-claims, even with exit `0`: eligibility beyond the tool's own gate
result for that exact input (an `ELIGIBLE` gate result is a point-in-time gate
outcome, not a trade instruction), recommendations, target prices, expected
returns, win rates, rankings, portfolio fit, and manipulation claims beyond the
filter result actually returned.

### 2.6 Research/analysis request protocol

The canonical rules are in
[`docs/mandatory-agent-instructions.md`](mandatory-agent-instructions.md) under
"Research/analysis request protocol". In short:

| Request | Default command | What it is |
| --- | --- | --- |
| Universe scan (`--nifty50`, `--niftynext50`, `--nifty100`, `--nifty200`) | `signal-decisions scan` | Integrated screen: every member passes identity binding, pair policy, the 8 safety/anti-manipulation gates, structure, price action/SMC, volume, sector participation, relative strength, regime, and basket selection. Not a per-stock dossier. |
| Deeper per-stock dossier | `market-data research-run-current --symbol SYM` | Agent packet for a validated candidate (V1–V6; V3–V6 private-context limits). |
| Whole-list research | `market-data setup-research-selection ...` | Factual research for an exact selection or 1–100 explicit symbols. |

Before a pass: use the latest completed official session (do not run a provider
refresh before the publication boundary; the scheduled after-close run is
authoritative), check the owner's private research ledger for a duplicate, and
state which layers ran. After a real pass: ask before storing a ledger entry
(default store; full detail; private; append-only). Never present a scan as a
completed dossier, and never turn a candidate into advice, targets, or position
sizes.

## 3. Pick your question, then run the command

Synopses are the installed console-script forms (repeatable options are shown
repeated). `ROOT` is the owner's absolute private storage root. Each row links
the authoritative contract; §4 adds exits, boundaries and prerequisites.

| If the question is… | Run | Contract |
|---|---|---|
| Current completed-session research for one stock, with explicit questions | `market-data research-current --symbol SYM --storage-root ROOT [--refresh] [--contract-version v2] [--question LATEST_COMPLETED_CANDLE\|PRICE_BEHAVIOR\|CURRENT_STRUCTURE\|INTEGRATED_CURRENT_RESEARCH] --output json` | [Single-stock current research](../README.md#single-stock-current-research), [single-stock-research.md](workflows/single-stock-research.md) |
| The compact agent dossier for one stock (V1–V6, optional context layers) | `market-data research-run-current --symbol SYM --storage-root ROOT --contract-version v6 [--analysis-input-file FILE] [--loss-scenario-input-file FILE] --output json` | [agent-current-research-run.md](workflows/agent-current-research-run.md) |
| Current research plus causal candidate facts from the same observation | `market-data setup-research-current --symbol SYM --storage-root ROOT --output json` | [Plan 61](plans/61-first-use-gap-reconciliation.md) |
| Whole-list research for an exact retained selection or an explicit list | `market-data setup-research-selection --selection-request-file FILE --selection-root DIR --storage-root ROOT --output json` (or repeated `--symbol`) | [Plan 62](plans/62-exact-selection-whole-list-research.md) |
| Latest causal Structure break (`MATCH`/`NO_MATCH`/`UNKNOWN`) for an explicit list | `market-data setup-screen-current --symbol SYM [--symbol SYM ...] --storage-root ROOT --output json` | [causal-setup-screen.md](workflows/causal-setup-screen.md) |
| Factual close-direction screen of an explicit 2–10 stock watchlist | `market-data watchlist-screen-current --symbol SYM --symbol SYM --close-direction UP\|DOWN\|UNCHANGED --storage-root ROOT --output json` | [watchlist-factual-screen.md](workflows/watchlist-factual-screen.md) |
| Candidate scan plus prompt-ready briefing cards (one exact Nifty universe or explicit list) | `signal-decisions scan --storage-root ROOT (--nifty50\|--niftynext50\|--nifty100\|--nifty200) --output json [--retain-decision-evidence]` (or repeated `--symbol A --symbol B`) | [automated-nifty100-scan.md](workflows/automated-nifty100-scan.md) |
| Record the evidence a decision will consume | `stock-observations observe --symbol SYM --question CURRENT_STRUCTURE --storage-root ROOT [--refresh] --output json` | [retained-stock-observations.md](workflows/retained-stock-observations.md) |
| V3 safety eligibility (8 gates) for one observation | `signal-decisions check-eligibility-v3 --observation HANDLE --storage-root ROOT --output json` | [supported-signal-decisions.md](workflows/supported-signal-decisions.md) |
| V3 causal decision from an earlier + later observation | `signal-decisions evaluate-v3 --previous-observation H1 --current-observation H2 --storage-root ROOT --output json` | [supported-signal-decisions.md](workflows/supported-signal-decisions.md) |
| Revisit or compare retained observation records | `stock-observations read --observation HANDLE --storage-root ROOT --output json`; `stock-observations compare --previous H1 --current H2 --storage-root ROOT --output json` | [retained-stock-observations.md](workflows/retained-stock-observations.md) |
| Read or aggregate retained scan decision evidence | `signal-decisions read-decision-evidence --decision-evidence HANDLE --storage-root ROOT --output json`; `signal-decisions measure-decision-evidence --storage-root ROOT --output json` | [automated-nifty100-scan.md](workflows/automated-nifty100-scan.md), [Plan 76](plans/76-source-bound-scan-decision-evidence.md) |
| Grade one retained decision page against the frozen G09 opportunity recipe | `signal-decisions grade-decision-evidence --storage-root ROOT [--decision-evidence HANDLE] [--output json\|table]` | [automated-nifty100-scan.md](workflows/automated-nifty100-scan.md), [Plan 81](plans/81-g09-decision-opportunity-grading.md) |
| Track paper observations from retained scans | `signal-decisions track --storage-root ROOT [--log-scan FILE] --output json` | [Plan 73](plans/73-paper-observation-tracking-registry.md) |
| Completed-session volume context vs its baseline | `market-data volume-context-current --input-file FILE --storage-root ROOT --output json` | [volume-context.md](volume-context.md) |
| Relative strength vs an explicit reference stock | `market-data relative-strength-current --input-file FILE --storage-root ROOT --output json` | [relative-strength.md](relative-strength.md) |
| Hypothetical loss arithmetic for caller assumptions | `market-data loss-scenario --input-file FILE [--contract-version v3]` | [loss-scenario.md](workflows/loss-scenario.md) |
| Raw retained current-price context | `market-data price-context-current --input-file FILE --storage-root ROOT [--acquire-missing] [--contract-version v2] --output json` | [Plan 36](plans/36-bounded-current-price-context-refresh-contract.md) |
| Retained current facts for a supplied cohort / one aggregate regime fact | `market-data cohort-current --cohort-file FILE --storage-root ROOT --cutoff UTC --output json`; `market-data regime-current --input-file FILE --storage-root ROOT --output json` | [Plan 19](plans/19-current-supplied-cohort-market-data-contract.md), [Plan 20](plans/20-current-supplied-cohort-market-regime-contract.md) |
| Inspect fixed owner-staged NSE safety evidence | `stock-safety-evidence inspect --storage-root ROOT --observation HANDLE --output json` | [owner-staged-nse-safety-evidence.md](workflows/owner-staged-nse-safety-evidence.md) |

## 4. Capability reference

### 4.1 Current research and screening (agent research path)

**`market-data research-current`** — one stock, versioned completed-session
research packet.
- Use for explicit question types (v2 `--question`): latest completed candle,
  price behavior, current structure, or the integrated research report.
- Needs: an existing owner-private root. Cold or `--refresh` runs contact the
  approved official calendar, Upstox BOD mapping and BharatStock under the
  owner's source authorization; warm reuse revalidates retained identities.
- Exits: `0` observed Price Action for the requested question; `1` structured
  unavailable/insufficient result; `2` invalid/internal.
- Boundaries: output carries feature-local facts, source/basis labels, actual
  knowledge times and scoped reasons — not raw bars, not trade eligibility.

**`market-data research-run-current`** — the compact agent dossier (V1–V6).
- Use when an external assistant needs one agent-ready per-stock packet. V2
  adds the documented completed-session fallback; V3 event notice and V4 cohort
  comparison are owner-private; V5 adds relative-strength/volume context
  (`--analysis-input-file`); V6 adds a caller-supplied hypothetical loss
  scenario (`--loss-scenario-input-file`).
- Exits: `0` the dossier's required price facts are present; `1` at least one
  is missing (the JSON names it). V3–V6 context layers report their own
  readiness; for V5/V6, exit `0`/`1` still describes price availability only.
  `2` invalid/internal.
- Boundaries: V3/V4 output (and NSE-derived V5 context) is owner-private and
  **not authorized for hosted-AI disclosure**; V1/V2 output may be given to an
  agent only within the owner's approved disclosure scope. No implicit fallback
  beyond the documented rules.

**`market-data setup-research-current`** — current research plus causal
candidate facts from one observation.
- Use to bridge facts and the candidate projection in a single report; the
  candidate state is `MATCH`, `NO_MATCH` or `UNKNOWN` with its admitted anchor.
- Exits: `0`/`1`; `2` `request_invalid`/`setup_research_failed`.

**`market-data setup-research-selection`** — whole-list research for an exact
selection.
- Use for an exact retained Nifty 100 selection request (with
  `--selection-root`), or 1–100 explicit repeated `--symbol` values.
- Exits: `0`/`1`; `1` `selection_unavailable`; `2`
  `selection_research_failed`/`request_invalid`.

**`market-data setup-screen-current`** — latest causal Structure break screen.
- Use for 1–10 explicit stocks; each row is a factual `MATCH`/`NO_MATCH`/
  `UNKNOWN` candidate state with its confirmed anchor and observation identity.
- Exits: `0` all rows factual; `1` any row `UNKNOWN`; `2` invalid.
- Boundary: detection is not active signal confirmation, eligibility or advice.

**`market-data watchlist-screen-current`** — factual close-direction screen.
- Use for an explicit 2–10 symbol watchlist; it does not discover or verify
  list or index membership.
- Needs: an existing owner-private root; it may contact the authorized calendar
  and mapping sources and the BharatStock price source even without a refresh
  flag.
- Exits: `0` all rows factual; `1` any row `UNKNOWN`; `2` invalid/internal.

**`signal-decisions scan`** — candidate scan + briefing cards.
- Use to evaluate exactly one current official universe per run —
  `--nifty50` (50), `--niftynext50` (50), `--nifty100` (100), or `--nifty200`
  (200; keeps Nifty 100 priority and the conditional N200-ex-N100 tier-2 fill) —
  or 1–100 explicit symbols added with repeated
  `--symbol` (`--symbol A --symbol B`), and emit prompt-ready
  `swing-trade-brief@v1` cards for the
  external assistant. `--retain-decision-evidence` writes immutable decision
  evidence for later reads.
- Needs: the owner's credential injection for the V3 safety reads.
- Exits: `0` scan completed (including rows that end `UNKNOWN`); `1` redacted
  unavailability envelope; `2` invalid.
- Boundaries: two gate layers apply — the V3 safety screen and the scan's
  anti-manipulation stage (see §9 item 1). Use the scan document's prompt
  template and allowed-claims rules for the hand-off.

### 4.2 Decisions and observation records

**`stock-observations observe`** — record an immutable observation.
- Use first: V3 decisions consume retained 64-hex observation handles.
  `PRICE_BEHAVIOR` for price/scan facts; `CURRENT_STRUCTURE` for V3 checks.
- For a decision pair, record an earlier and a later observation; `--refresh`
  forces fresh provider reads where the contract allows them.
- Read: the handle is the immutable record id. `NOT_READY` with a
  `LATEST_SESSION_MISSING` reason means the latest completed daily row is not
  yet published — re-run after it is; never substitute an older row.
- Exits: `0` READY; `1` not ready / unavailable; `2` invalid.

**`signal-decisions check-eligibility-v3` / `evaluate-v3`** — automated V3
safety and causal decisions.
- `check-eligibility-v3` runs the 8-gate `stock-eligibility@v3` screen for one
  observation; `evaluate-v3` resolves the `stock-signal-decision@v3` causal
  decision from an earlier + later observation pair.
- Needs: the owner's credential injection; the gates read current quote and
  corporate-action sources (quote freshness is part of the gates).
- Exits: `0` `ELIGIBLE` / `RESEARCH_CANDIDATE`; `1` everything else with the
  reason recorded; `2` invalid.
- Boundaries: `ELIGIBLE` is a gate result at that moment, not a trade
  instruction; `NO_TRADE` is a valid supported outcome.

**`signal-decisions check-eligibility` / `evaluate` (V2)** — offline retained
decisions.
- Use only for explicit V2 compatibility: these read retained records only and
  always exit `1` with an `UNKNOWN`/`NO_TRADE` disposition; they run no live
  gates.

**`stock-observations read` / `compare`** — exact retained record access.
- `read` returns one record by handle; `compare` states whether two records are
  comparable and their admitted differences.
- Exits: `0` READY / COMPARABLE; `1` otherwise; `2` invalid.

**`signal-decisions read-decision-evidence` / `measure-decision-evidence`** —
retained scan decision evidence.
- `read` returns one immutable evidence record by handle; `measure` aggregates
  retained evidence (`--split-at`, `--execution-convention`).
- Exits: `0`/`1`; `2` invalid.

**`signal-decisions grade-decision-evidence`** — report-only G09 opportunity
grading.
- Grades exactly one retained page: decision-day close, the first ten later
  official sessions, first-touch `+3.00%` gross, the 25 bp round trip, candidate
  buckets, and the page-denominator base rate.
- Reads only retained page, calendar, and capture evidence; retains nothing,
  makes no provider, network, credential, clock, or ledger-vault access, and
  gives no advice.
- Exits: `0` complete window with every row hit/no-hit; `1` pending/unavailable
  window or typed unavailable envelope; `2` invalid request.

**`signal-decisions track`** — paper observation registry.
- Records and updates paper observations from retained scans; descriptive only.
- Exits: `0`/`1`; `2` invalid.

### 4.3 Context facts

**`market-data volume-context-current`** — completed-session volume compared
with its prior-session baseline from retained evidence.
- Retained-only: no credentials, no provider call, no data acquisition.
- Exits: `0` all requested facts observed; `1` any non-ready state; `2` invalid.

**`market-data relative-strength-current`** — exact unadjusted price-change
difference against an explicit reference stock.
- Retained-only, same guarantees as above; exits `0`/`1`/`2`.

**`market-data loss-scenario`** — hypothetical loss arithmetic from caller
assumptions (request contracts v1–v3).
- Pure local arithmetic over the supplied request; no market evidence is read.
- Exits: `0` success; `2` invalid/internal.

**`market-data price-context-current`** — independent retained raw current-price
context (v1 default; v2 adds the bounded refresh contract).
- Needs: an existing owner-private root; `--acquire-missing` permits
  acquisition for v1 and is rejected together with `--contract-version v2`.
- Exits: `0` when the required features for the selected contract are
  observed; `1` otherwise; `2` invalid/internal.

**`market-data cohort-current`** — retained current facts for an owner-supplied
cohort file.
- The cohort file is closed canonical JSON (≤64 KiB) with `selected_at` and
  members; the command computes the cohort identity rather than trusting it.
- Exits: `0` COMPLETE; `1` INSUFFICIENT_EVIDENCE; `2` structural rejection.

**`market-data regime-current`** — one aggregate regime fact from the exact
21-ID input file and retained schedule evidence resolved under the same root.
- Retained-only, no network call. Its `--help` is deliberately rejected — use
  the Plan 20 invocation.
- Exits: `0` OBSERVED; `1` INSUFFICIENT_EVIDENCE; `2` structural rejection.

**`stock-safety-evidence inspect`** — inspect a fixed owner-staged NSE safety
evidence package without granting eligibility clearance.
- Exits: `0` STAGED; `1` UNAVAILABLE; `2` invalid.

## 5. Version labels are not one axis

Several unrelated version schemes share `v1…v6` labels. Read them per command:

| Label | Command | Meaning |
|---|---|---|
| V1–V6 | `market-data research-run-current` | Agent dossier generations: V1 base; V2 documented completed-session fallback; V3 owner-private event notice; V4 owner-private cohort comparison; V5 volume + relative-strength context; V6 adds a caller-supplied hypothetical loss scenario. |
| v1/v2 | `market-data research-current --contract-version` | Stock-research packet generations; v2 enables explicit `--question` types. |
| v1/v2 | `market-data price-context-current --contract-version` | Price-context request generations; v2 adds the bounded refresh contract. |
| v1/v2/v3 | `market-data loss-scenario --contract-version` | Loss-scenario request generations. |
| V2/V3 | `signal-decisions` | Decision contract generations: V2 is offline retained (always exit `1`); V3 is the automated safety/causal decision with provider reads. |

## 6. When a command does not return facts

- Exit `1` with structured JSON is a valid research output. Report the reason
  tokens exactly; do not retry blindly and do not look for the fact elsewhere.
- Only perform recovery actions the contract documents — for example re-running
  an observation after a `LATEST_SESSION_MISSING` publication delay, or using
  `--refresh`/`--acquire-missing` where the command defines it and the owner
  authorizes provider access.
- Exit `2`: fix the request (path, mode, schema, flags) and re-run. Never treat
  stderr as data and never present a partial guess.
- Exit `3`/`4`/`5`/`130` (download family): partial coverage, unavailability,
  failure and cancellation are operational states. Record what happened; do not
  substitute data.
- Never substitute another source, an older row, or a computed estimate for a
  fact the tool did not return.

## 7. Operator, capture and internal commands

Not the agent research path. Run these only with explicit operator authority;
several are credential-bound and mutate retained evidence.

| Command | Class | Purpose | Contract |
|---|---|---|---|
| `market-data download` / `coverage` / `query` | operator | persist / prove / query retained Nifty 50 scheduled-minute evidence; exits `0/2/3/4/5/130`; `download` contacts the provider, `coverage` and `query` are provider-free | [README](../README.md#downloader-v1-quickstart) |
| `market-data probe-upstox` | operator diagnostic | validate a master-catalog instrument without writing candle data | [README](../README.md#run-the-upstox-diagnostic) |
| `equity-data-download` | operator | configured-root structured daily OHLCV persistence | [README](../README.md#structured-daily-ohlcv-downloader) |
| `capture-forward-adjusted-ohlcv` | operator | immutable BharatStock V2 capture evidence | [Plan 30](plans/30-capture-forward-adjusted-ohlcv-evidence-contract.md) |
| `efficient-current-nifty100-adjusted-capture` | operator | official Nifty 100 BharatStock V2 capture (installed script name; internal program name `current-nifty100-bharatstock-capture`) | [Plan 33](plans/33-efficient-continuous-nifty100-capture-contract.md) |
| `market-data historical-ohlcv-upstox-raw` / `historical-ohlcv-upstox-raw-read` | operator | complete / read one retained Upstox raw daily OHLCV revision | [Plan 28](plans/28-fixed-cohort-historical-ohlcv-revision-store-contract.md) |
| `market-data cohort-current` / `regime-current` | agent (retained) | see §4.3 — usable by the agent, plan-level contracts | Plans 19/20 |
| `historical-census` | internal | provider-free strict retained census; exits `0`/`3` | [Plan 10](plans/10-five-session-opportunity-census-contract.md) |
| `evidence-readiness` | internal | fail-closed prerequisite manifest; exits `0`/`3` (`--help` exits `3`) | [Plan 11](plans/11-prospective-evidence-readiness-contract.md) |
| `market-regime-acquisition-decision` | internal | acquisition-decision reducer (stdin JSON); `0` APPROVED_TO_ACQUIRE / `1` BLOCKED / `2` | [Plan 16](plans/16-market-regime-layer-b-acquisition-decision.md) |
| `historical-validation-gate` | internal | capability-aware historical validation gate; `0` APPROVED_TO_START_MARKET_STRUCTURE / `1` BLOCKED / `2` | [Plan 29](plans/29-capability-aware-historical-validation-gate-contract.md) |
| `point-in-time-snapshots` | operator — **in delivery, Issue #335; not yet on `main`** | bounded point-in-time research evidence snapshots (request/read modes); its contract (Plan 80) lands with the issue | [Issue #335](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/335) |

Several of these reject `--help` with the sanitized diagnostic by design
(§9 item 10); take invocations from this guide and the linked contracts.

## 8. Documentation index

### 8.1 `docs/workflows/` usage and contract documents

| Document | Audience | Purpose |
|---|---|---|
| [agent-current-research-run.md](workflows/agent-current-research-run.md) | agent | The agent dossier command (`research-run-current`) V1–V6, fallback rules, disclosure limits. |
| [automated-nifty100-scan.md](workflows/automated-nifty100-scan.md) | agent + operator | The scan workflow, briefing cards, prompt template, decision-evidence reads, credential injection. |
| [supported-signal-decisions.md](workflows/supported-signal-decisions.md) | agent | V2/V3 decision commands, the 8 gates, provider reads, exit codes. |
| [retained-stock-observations.md](workflows/retained-stock-observations.md) | agent | Observe/read/compare handles, comparability, exit codes. |
| [watchlist-factual-screen.md](workflows/watchlist-factual-screen.md) | agent | Explicit watchlist close-direction screen end to end. |
| [causal-setup-screen.md](workflows/causal-setup-screen.md) | agent | The causal Structure break screen and its limits. |
| [loss-scenario.md](workflows/loss-scenario.md) | agent | Loss-scenario request schemas and arithmetic. |
| [owner-staged-nse-safety-evidence.md](workflows/owner-staged-nse-safety-evidence.md) | agent + operator | The staged safety-evidence inspection package and claim limits. |
| [single-stock-research.md](workflows/single-stock-research.md) | agent | Explain-one-stock walkthrough and consumption rules for `research-current`. |
| [single-stock-research-observation.md](workflows/single-stock-research-observation.md) | agent | Observed single-stock explanation example. |
| [single-stock-research-comparison.md](workflows/single-stock-research-comparison.md) | agent | In-process comparison contract and boundaries. |
| [single-stock-research-comparison-observation.md](workflows/single-stock-research-comparison-observation.md) | agent | Observed comparison example. |
| [causal-setup-evidence.md](workflows/causal-setup-evidence.md) | agent + developer | Pair-fact continuity/evidence contract (library / injected CLI). |
| [causal-setup-interpretation.md](workflows/causal-setup-interpretation.md) | agent | Interpretation claim boundary for candidate responses. |
| [causal-setup-age.md](workflows/causal-setup-age.md) | agent | Descriptive age count; no validity/expiry claims. |
| [causal-setup-comparison.md](workflows/causal-setup-comparison.md) | agent | Pair comparison facts. |
| [causal-setup-event-continuity.md](workflows/causal-setup-event-continuity.md) | agent | Continuity facts across observations. |
| [causal-setup-invalidation.md](workflows/causal-setup-invalidation.md) | agent | Anchored contradiction (invalidation) facts. |
| [causal-setup-level.md](workflows/causal-setup-level.md) | agent | Level facts. |
| [causal-setup-level-interpretation-v2.md](workflows/causal-setup-level-interpretation-v2.md) | agent | Level interpretation boundary. |
| [causal-setup-level-range.md](workflows/causal-setup-level-range.md) | agent | Level-range facts. |
| [causal-setup-level-range-inclusion.md](workflows/causal-setup-level-range-inclusion.md) | agent | Range-inclusion facts. |
| [causal-setup-first-inclusion-close.md](workflows/causal-setup-first-inclusion-close.md) | agent | First-inclusion close facts. |
| [causal-setup-inclusion-interpretation.md](workflows/causal-setup-inclusion-interpretation.md) | agent | Inclusion interpretation boundary. |
| [range-aware-interpretation-v3.md](workflows/range-aware-interpretation-v3.md) | agent | Range-aware interpretation boundary. |
| [github-hosted-ci.md](workflows/github-hosted-ci.md) · [self-hosted-ci.md](workflows/self-hosted-ci.md) | developer | CI procedures (not tool usage). |
| [published-oci.md](workflows/published-oci.md) · [linux-native-and-oci.md](workflows/linux-native-and-oci.md) · [macos-docker-desktop.md](workflows/macos-docker-desktop.md) · [windows-wsl2-docker-desktop.md](workflows/windows-wsl2-docker-desktop.md) | operator | Install and run the released image on each platform. |

The `causal-setup-*` family (except `causal-setup-screen.md`) and the
interpretation documents are **library / injected-CLI contracts** — none of
them is an installed console script; consume them through the Python API or the
injected CLI exactly as their documents show.

### 8.2 Top-level documents

| Document | Audience | Purpose |
|---|---|---|
| [architecture-freeze-v1.md](architecture-freeze-v1.md) | everyone | Authoritative mission, boundaries and internal-error policy. |
| [volume-context.md](volume-context.md) · [relative-strength.md](relative-strength.md) | agent | The two retained context commands in full. |
| [notes/2026-09-23-swing-completed-session-fallback.md](notes/2026-09-23-swing-completed-session-fallback.md) | agent | The owner-accepted completed-session fallback rules for agent research V2. |
| `plans/*.md` | mixed | Normative contracts and records behind each capability; the capability blocks in §3–§4 link the specific plan. |

## 9. Known documentation conflicts and follow-ups

These are known; this guide states the authoritative reading. Where prose and
code disagree, the command output wins.

1. **Two anti-manipulation gate layers are easy to conflate.**
   `signal-decisions scan` applies the V3 safety screen
   (`stock-eligibility@v3`: ≥252 history sessions, ≥INR 20 price, ≥INR 1 Cr
   median turnover, 2% circuit distance and relative spread) **and** a separate
   anti-manipulation/asset-quality stage (INR 50 price floor, 120-session
   listing floor, INR 25 Cr median turnover). The README and scan document
   quote only the second set; read the failed-rule tokens in the command's own
   output.
2. **Scan example output is stale.** The `SWING TRADING CANDIDATE SCAN` tables
   shown in the README and the scan document predate the current columns
   (industry, age, RVOL, price-action body, relative strength, retest state);
   the JSON briefs are authoritative.
3. **`volume-context.md` trailing note is superseded.** Volume/relative
   strength agent integration is delivered as V5 (`research-run-current`);
   the older "separate work" note no longer applies.
4. **Older single-stock-comparison docs say record comparison is deferred.**
   `stock-observations observe/read/compare` is delivered; see
   [retained-stock-observations.md](workflows/retained-stock-observations.md).
5. **README "Current implementation status" predates recent sprints.** Use the
   live tracker and the plan documents for status.
6. **Scan universes are exact and Nifty 500 is retired.** `signal-decisions scan`
   resolves exactly one current official universe per run (`--nifty50`,
   `--niftynext50`, `--nifty100`, `--nifty200`); `--nifty100` scans exactly the
   Nifty 100. The nightly diary uses `--nifty200`. Historical Nifty 500 evidence
   remains preserved, but no scan path resolves Nifty 500.
7. **Capture naming.** The installed script is
   `efficient-current-nifty100-adjusted-capture`; its internal program name is
   `current-nifty100-bharatstock-capture`; Plan 33 also records the retired
   yfinance-era flow. Use the installed script and current BharatStock contract.
8. **Exit codes for the scan, tracking, capture and download families were not
   consolidated in prose before this guide**; §2.3 records them as implemented
   at this revision.
9. **`signal-decisions --help` lists subcommands without descriptions.** Use
   the tables in §3–§4 for their meanings.
10. **Some private launchers reject `--help`** with the sanitized diagnostic by
    design: `point-in-time-snapshots`, `capture-forward-adjusted-ohlcv`,
    `efficient-current-nifty100-adjusted-capture`, `historical-validation-gate`,
    `market-regime-acquisition-decision`, and `market-data regime-current` exit
    `2`; `evidence-readiness` exits `3`.
    Take their invocations from this guide and their contracts.

Follow-ups (not changes made by this guide): correct the stale scan example and
the superseded notes above in their own documents; reconcile the anti-manipulation
prose with the two implemented gate layers.

## 10. Keeping this guide current

When a consumer-facing capability is added or changed, update §3–§4 here and the
README pointer in the same change; normative detail stays in the linked
contracts. Documentation-only edits to this guide are verified with
`git diff --check`, direct inspection of every claim against the installed CLI
and code, and a proportionate independent review.
