# Automated Nifty Universe Scan & AI Assistant Briefing Workflow

The `signal-decisions scan` command provides a unified, 1-click scanning and research briefing workflow for human CLI analysts and external AI agent harnesses. It combines:
1. Automated **24/7 safety eligibility** screening (8 conservative rules).
2. Canonical **retained-observation pair policy** candidate evaluation: each symbol's exact previous/current `CURRENT_STRUCTURE` observation pair is evaluated by the Plan 70 policy; the scanner never invents a pair or a scanner-local causal candidate.
3. Prompt-ready **trade briefing cards** (`swing-trade-brief@v1`) with display-projected stop references, risk per share, and deterministic explanation ledgers.

---

## 1. Prerequisites and Credential Injection

The tool reads required provider credentials lazily from the execution environment:
* `BHARATSTOCK_API_KEY`: For 21-day market structure bars and 252-day history.
* `UPSTOX_ACCESS_TOKEN`: For live quotes, circuit limits, and corporate action dates.

We use **Doppler** to inject credentials securely without exposing secrets on the command line or saving them to disk:

```bash
doppler run -- signal-decisions scan [OPTIONS]
```

---

## 2. Running the Scanner

### A. Scan an Exact Nifty Universe

Choose exactly one universe per run: `--nifty50` (50), `--niftynext50` (50),
`--nifty100` (100), or `--nifty200` (200). `--nifty100` scans exactly the
current official Nifty 100. The nightly diary uses `--nifty200`, which keeps
Nifty 100 priority and the conditional N200-ex-N100 tier-2 fill; Nifty 50,
Nifty Next 50, and Nifty 100 scans are exact with no cross-universe gap fill.
Nifty 500 is retired as a runtime scan universe.

**Candidate carry.** A confirmed upward `BOS` remains a research candidate for
one through five completed sessions while the event is unchanged, no later DOWN
`CHOCH` of the original supporting low was observed, the completed close stays
above the original broken high, the quote stays above the supporting low, safety
is eligible, and the price has not moved more than one structural risk unit
(`broken high − supporting low`) above the breakout. The policy identifier for
this behavior is `supported-signal-decision-policy@v2`.

**Timing.** Scans and research commands may be run at any time. The scheduled
nightly runner is `scripts/daily_after_close_scan.sh`, tracked in this
repository; install its systemd user timer with
`scripts/install_research_schedule.sh` (units are tracked under
`scripts/systemd/`, so a lost home directory is repaired by re-running the
installer; `--check` reports any unit missing from the running system). It writes
diary pages to
`$SWING_STORAGE_ROOT/daily-scan/` (default
`~/SwingTradingAIAssistantData/daily-scan/`), never to an ad-hoc home folder,
and injects credentials through an explicit Doppler project/config scope
(`SWING_DOPPLER_PROJECT`, `SWING_DOPPLER_CONFIG`) without mutating global
Doppler configuration. It carries an 08:00–19:59 IST skip, a weekend skip, a
retained-calendar NSE closure skip, and a duplicate same-day page skip so the
diary does not capture intraday, not-yet-published, or duplicate data. After a
successful scan with at least one candidate it also runs the deterministic
`swing-analysis` artifact and `market-data research-run-current --contract-version v2`
for exactly those candidates, writing `analysis-YYYY-MM-DD.json` and
`research-YYYY-MM-DD.json` beside the scan page. Those post-scan stages never
alter the scan page or its decision, and a post-scan failure is logged in the
matching `.err` file without failing the scan. The guards apply to the scheduled
job only and do not restrict on-demand scans or `market-data` research commands.
Interpretation and prior-candidate tracking remain manual; the ledger entry and
its off-device copy are written by the runner.

```bash
doppler run -- signal-decisions scan \
  --storage-root /absolute/path/to/SwingTradingAIAssistantData \
  --nifty200 \
  --output table
```

### B. Scan an Explicit List of Stocks

```bash
doppler run -- signal-decisions scan \
  --storage-root /absolute/path/to/SwingTradingAIAssistantData \
  --symbol TECHM \
  --symbol LTM \
  --symbol PFC \
  --symbol INFY \
  --symbol TCS \
  --output table
```

### C. Output Formats

* `--output table` *(Default)*: Formatted ASCII/Unicode summary table for terminal display.
* `--output json`: Compact canonical JSON adhering to `swing-trade-scan@v3` for automated ingestion.
* `--refresh`: Admit a new `CURRENT_STRUCTURE` observation for each symbol so the retained pair state can advance. Without it, an existing state is replayed (or a retained observation bootstraps the first seed); a scan never pairs stale data or invents a new predecessor.

When no later completed session exists, the scan re-evaluates the stored
previous→current pair without advancing state. Re-running on the same session
therefore returns the same candidate result; `--refresh` on the same session
also re-evaluates that pair and does not advance. Only a genuinely later
observation advances the pair.

The scan timestamp is a research-run label, not a market session. Runs on
weekends and exchange holidays reuse the same last completed sessions, so their
candidate facts must match the prior run on those sessions even though the
research label differs.


### D. Retain exact decision evidence for later qualification

Use `--retain-decision-evidence` when a scan must be retained as an immutable
private input to later historical or AI qualification:

```bash
doppler run -- signal-decisions scan \
  --storage-root /absolute/path/to/SwingTradingAIAssistantData \
  --symbol INFY \
  --retain-decision-evidence \
  --output json
```

The response is a `scan-decision-evidence-envelope@v1` containing the unchanged
`swing-trade-scan@v3` result and a `decision_evidence_handle`. Read that exact
record later without a provider call:

```bash
signal-decisions read-decision-evidence \
  --storage-root /absolute/path/to/SwingTradingAIAssistantData \
  --decision-evidence HANDLE \
  --output json
```

The readback rejects altered, missing, substituted, or incompatible retained
observations. It is evidence retention only—not historical replay, an AI-model
evaluation, a performance/profit claim, execution-cost evidence, or trading advice.

Aggregate the retained evidence into the reachable G09 measurement:

```bash
signal-decisions measure-decision-evidence \
  --storage-root /absolute/path/to/SwingTradingAIAssistantData \
  --output json
```

Optional `--split-at <instant>` partitions retained scans into earlier/later
subsets with an explicit no-future-leakage guard; optional
`--execution-convention` records the caller-named execution assumption.
`--since <instant>` selects an explicit runtime segment; records before the
boundary are reported as metadata-only `excluded_handles` and never admitted.
`--dedupe-by-day` keeps the latest page per scan date and reports older pages
as metadata-only `superseded_handles`. The
report measures the mandatory policy independently from optional context,
performs no AI evaluation, and always lists the external prerequisites that
remain hard final-qualification gates (per-decision-date historical backfill,
out-of-sample/walk-forward evidence, an approved execution cost/slippage
convention, named AI model/source with immutable prompt/output provenance, and
return/profitability evidence). It never simulates or invents those results.

Grade exactly one retained decision page against the frozen G09 opportunity
recipe (owner-accepted 2026-10-19):

```bash
signal-decisions grade-decision-evidence \
  --storage-root /absolute/path/to/SwingTradingAIAssistantData \
  [--decision-evidence HANDLE] \
  [--output json|table]
```

Without `--decision-evidence`, the command grades the latest retained page by
`scan_timestamp` then handle; a second handle in one invocation is refused. It
re-admits the page and one capture revision per symbol, resolves the decision
session from the retained official calendar, and evaluates the first ten later
sessions only. It retains nothing and makes no provider, network, credential,
clock, or ledger-vault access. Missing bars are never backfilled: they remain
`PENDING` or `UNAVAILABLE`, and every page row stays in the base-rate
denominator. Pass-shape ingredients are printed only when the window is
complete, and no single-page report is a pass/fail, profitability, or advice
claim. The frozen contract, bounds, and interpretation notes are in
[Plan 81](../plans/81-g09-decision-opportunity-grading.md).

Aggregate the single-page reports over an explicit segment without changing the
recipe or inventing a completed window:

```bash
.venv/bin/python scripts/g09_series_report.py \
  --storage-root /absolute/path/to/SwingTradingAIAssistantData \
  --since 2026-10-24T00:00:00.000000Z \
  --dedupe-by-day \
  --output json
```

The series report selects retained pages by `scan_timestamp`, keeps the newest
page per decision day when `--dedupe-by-day` is set, and grades each selected
page with the same grader. It is read-only and reports `series_state` as
`COMPLETE` only when every selected page has a completed ten-session window;
otherwise it is `PENDING`. `UNAVAILABLE` pages are reported separately. It does
not turn a partial series into a pass/fail, profitability, or advice claim.

### E. Retained pair state and daily progression

The scanner persists at most one new admitted pair transition per symbol per
scan under the private `scanner-pair-state-v1/` namespace:

1. The first admitted observation seeds the state and the symbol is reported as
   an explicit non-candidate (`OBSERVATION_PAIR_SEEDED_BOOTSTRAP`); no predecessor is
   fabricated. A runtime-identity change starts a new generation: its first
   `--refresh` scan is a bootstrap of this kind for every symbol and is not a
   no-candidate market result; eligible seed rows use
   `OBSERVATION_PAIR_SEEDED_BOOTSTRAP`, and the CLI writes a `BOOTSTRAP:` warning
   to stderr whenever any symbol seeded, independent of safety precedence. When
   the newest closed session's data is not published yet, the scan binds the
   latest available completed session and writes `LATEST_AVAILABLE`; when
   pair state is empty it seeds the prior completed session and evaluates the
   newest available pair in the same request (`BOOTSTRAP_PAIR`), so one command
   always yields a page. An explicit `--sessions-back N --refresh` still binds
   older sessions for historical runs and writes `SESSIONS_BACK`. A
   no-refresh first scan with an unreadable/stale retained handle reports
   `OBSERVATION_PAIR_BOOTSTRAP_REQUIRES_REFRESH`.
2. A later distinct admitted observation forms the exact previous/current pair,
   is evaluated by the canonical policy, and only then advances the state.
3. Re-scanning the same admitted observation replays the canonical policy result
   (`CAUSAL_REPLAY_HAS_NO_NEW_CONFIRMATION`) instead of recreating a candidate.

Malformed, foreign, race-conflicted, or runtime-mismatched state fails closed as
`OBSERVATION_PAIR_STATE_UNAVAILABLE` with an `UNKNOWN`/`UNKNOWN` row, and every
requested symbol still appears exactly once in `candidates` or `other_stocks`.

---

## 3. Terminal Table Output Example

```text
================================================================================
SWING TRADING CANDIDATE SCAN — EXPLICIT (2026-10-16T09:29:57Z)
================================================================================
Scanned: 5 | Candidates: 2 | Eligible: 3 | Ineligible: 2 | Unknown: 0
--------------------------------------------------------------------------------
CONFIRMED RESEARCH CANDIDATES:
SYMBOL     PRICE      SETUP    DATE         BROKEN HIGH  STOP REF   RISK/SH   
--------------------------------------------------------------------------------
LTM        INR 4387.4 UP CHOCH 2026-10-13   INR 4183.6   INR 3905.6 INR 481.8 
PFC        INR 335.0  UP CHOCH 2026-10-12   INR 332.25   INR 313.35 INR 21.65 
--------------------------------------------------------------------------------
FILTERED BY SAFETY POLICY (2 stocks):
  - TECHM: LOW_PRICE_AND_CIRCUIT_DISTANCE (Price: INR 1779.6)
  - TCS: SUPPORTED_CORPORATE_ACTION_BLACKOUT (Price: INR 2462.1)
--------------------------------------------------------------------------------
```

---

## 4. Understanding the Trade Briefing Card (`swing-trade-brief@v1`)

When `--output json` is selected, each candidate includes a prompt-ready `swing-trade-brief@v1` payload:

```json
{
  "schema": "swing-trade-brief@v1",
  "symbol": "LTM",
  "isin": "INE214T01019",
  "exchange": "NSE",
  "decision": "RESEARCH_CANDIDATE",
  "candidate_summary": {
    "current_price_inr": "4387.4",
    "setup_event": "CHOCH",
    "setup_direction": "UP",
    "event_session": "2026-10-13",
    "age_completed_sessions": 3,
    "broken_high_level_inr": "4183.6",
    "supporting_stop_reference_inr": "3905.6",
    "risk_per_share_inr": "481.8",
    "invalidation_condition": "Daily close strictly below supporting stop reference"
  },
  "safety_eligibility": {
    "status": "ELIGIBLE",
    "explanation_ledger": [ ... 8 safety rule entries ... ]
  },
  "ai_guidance": {
    "allowed_claims": [
      "State the display projection shows a CHOCH setup at level INR 4183.6 on session 2026-10-13; the canonical pair-policy result and evidence remain authoritative in policy_decision.",
      "State current quote price is INR 4387.4.",
      "State the display projection's supporting stop reference is INR 3905.6 (not a policy anchor; canonical relations are in policy_decision.causal_evidence).",
      "State the display-implied risk per share is INR 481.8 (current price minus the display stop reference).",
      "State the display projection's candidate age is 3 completed session(s) (within the 1–5 freshness window); the canonical candidate age is in policy_decision.causal_evidence.",
      "State all 8 conservative safety eligibility gates passed (turnover, history, circuit distance, book liquidity, and 7-day corporate action blackout)."
    ],
    "forbidden_claims": [
      "Do not predict future percentage returns or guaranteed profitability.",
      "Do not set speculative target prices, reward multipliers, or profit-taking exits.",
      "Do not issue automated broker orders, capital allocation advice, or position sizes."
    ]
  }
}
```

The full card also attaches `policy_decision` (the canonical pair-policy result with its `causal_evidence`) and `optional_context`; both are omitted from this display example.

---

## 5. External AI Assistant Integration (Outcome G06)

To have an AI assistant (ChatGPT, Claude, or a local harness) synthesize plain-English briefings for human traders:

### Canonical Prompt Template

```text
System: You are an objective financial research assistant. Your task is to explain
the following deterministic swing trading briefing card to a human trader.
You MUST adhere strictly to the allowed claims in ai_guidance. You MUST NOT make
any of the forbidden claims (no profit promises, no target prices, no broker instructions).

Briefing Card JSON:
{PASTE_SWING_TRADE_BRIEF_JSON}
```

### Expected AI Assistant Output

> **Candidate Briefing: LTIMindtree (LTM)**
> * **Status:** Confirmed Research Candidate (`RESEARCH_CANDIDATE`)
> * **Current Price:** ₹4,387.40
> * **Setup (display projection):** Upward Change of Character (`UP CHOCH`) shown on October 13, 2026 at level ₹4,183.60; the canonical pair-policy result and evidence are authoritative in `policy_decision`.
> * **Setup Freshness (display projection):** 3 completed sessions elapsed (within the 1–5 session freshness window); the canonical candidate age is in `policy_decision.causal_evidence`.
> * **Protective Stop Reference (display projection):** ₹3,905.60 (supporting swing low; not the policy's invalidation anchor).
> * **Display-Implied Risk per Share:** ₹481.80 (current price minus the display stop reference).
> * **Display Invalidation Note:** A daily close strictly below the display stop reference (₹3,905.60); canonical invalidation status is in `policy_decision.causal_evidence`.
> * **Safety Clearance:** Cleared all 8 safety screening gates: 287 completed history sessions, 20-day median turnover exceeding ₹1,000 Crore, quote within circuit limits, and zero corporate action blackout events in the next 7 days.

---

## 6. Portfolio Discovery Protocol: Two-Tier 5–10 Stock Basket Hierarchy

The AI assistant and CLI operator must adhere to the following canonical portfolio rules:

1. **Target Portfolio Size:** The swing trading basket contains between **5 to 10 stocks**.
2. **Priority #1 — Nifty 100 Large Caps:** The basket first admits every validated
   Nifty 100 candidate, up to all 10 basket slots.
3. **One-Pass Current Nifty 200 Scan:** The scanner evaluates each current official
   Nifty 200 member once, tags the Nifty 100 subset, and never repeats provider or
   data work for that subset.
4. **Tier 2 Basket Fill (Nifty 200 Ex-Nifty 100):** Only when fewer than five
   validated Nifty 100 candidates exist, validated Nifty 200-only candidates fill
   the remaining slots toward the 5–10 target. They never displace a validated
   Nifty 100 candidate.

---

## 7. Anti-Manipulation & Asset Quality Filter Stage

To prevent capital risk from operator pump-and-dump schemes, newly listed volatility, and illiquid small-caps, every candidate must clear this dedicated filter before admission:

| Anti-Manipulation Gate | Policy Threshold | Reason for Rejection |
|---|---|---|
| **Newly Listed Stocks (IPOs)** | History $\ge 120$ trading sessions ($\ge 6$ months) | Rejects untested IPOs with anchor lock-in risk (`NEWLY_LISTED_EXCLUDED`). |
| **Penny / Low-Priced Stocks** | Price $\ge \text{INR } 50.00$ | Rejects sub-50 operator-dominated penny stocks (`PENNY_STOCK_EXCLUDED`). |
| **Illiquid Small-Caps** | 20-day Median Turnover $\ge \text{INR } 25.0\text{ Crore / day}$ | Rejects thinly traded small-caps prone to syndicates (`ILLIQUID_SMALLCAP_EXCLUDED`). |
| **Circuit Band Buffer** | Distance to Upper/Lower Circuit $\ge 2.0\%$ | Rejects circuit-locked stocks where exits are trapped (`CIRCUIT_PROXIMITY`). |

Industry labels for the scan come from the retained
`.nifty200-industry-mapping-v1` artifact: a closed manifest with the official
NSE source URL, retrieval time, SHA-256, and exactly 200 rows, plus the raw CSV.
The loader requires a regular file opened without following symlinks, bounds the
read, verifies the hash, the exact CSV header, symbol syntax/uniqueness, and
non-empty bounded industry labels before use. It falls back to the older Nifty
100 mapping only when the Nifty 200 artifact is absent or invalid, and verifies
that fallback file's content-addressed hash too. Missing or invalid labels remain
`Unknown`; industry is context and never changes a candidate decision.

## Candidate analysis (post-scan)

The scan remains the decision layer. The missing price-action/SMC facts are a
separate, additive analysis artifact; they do not change candidate status or the
scan schema:

```bash
doppler run -- swing-analysis \
  --scan-json ~/SwingTradingAIAssistantData/daily-scan/scan-YYYY-MM-DD.json \
  --output json
```

The artifact schema is `swing-analysis@v2`. Per candidate it reports ATR20,
ATR-percent, event-session volume versus the prior 20-session average and
median, completed-bar retest state, 252-session swing support/resistance
clusters with nearest levels and ATR distances, weekly trend, a real
last-bearish-candle demand zone, ATR-normalized extension and risk, and explicit
flags.

It also evaluates `swing-analysis-policy@v1` and returns a deterministic
`members[].policy.outcome` (with report-level `policy.outcome_counts` and
`policy.gate_counts`):

| Outcome | Rule |
|---|---|
| `QUALIFIED` | Every gate `PASS`. |
| `WATCH` | No `FAIL` or `UNAVAILABLE`; at least one `PENDING` gate. |
| `NOT_QUALIFIED` | At least one gate `FAIL`. |
| `INSUFFICIENT` | No `FAIL`, but at least one gate `UNAVAILABLE`. |

| Gate | Pass rule |
|---|---|
| `ATR_AVAILABLE` | ATR20 is present. |
| `VOLUME_EXPANSION` | Event volume $\ge 1.50\times$ the prior 20-session average. |
| `CANDLE_BODY_QUALITY` | Bullish event body $\ge 60\%$ of the event range. |
| `RETEST_CONFIRMED` | Completed-bar state is `RETEST_CONFIRMED`; `TESTING`, `NO_RETEST`, and `NO_SESSIONS_AFTER_EVENT` are `PENDING`; `BELOW_LEVEL` is `FAIL`. |
| `WEEKLY_TREND_UP` | Weekly trend is `UPTREND`; `RANGE_OR_TRANSITION` is `PENDING`; `DOWNTREND` is `FAIL`. |
| `DEMAND_ZONE_VALID` | A demand zone exists and the latest close is at or above its low. |
| `EXTENSION_WITHIN_2_ATR` | Latest close is at most $2.00$ ATR above the broken high. |
| `RISK_POSITIVE` | Latest close is strictly above the structural stop. |

The policy is `PROVISIONAL_RESEARCH`: the thresholds are explicit, versioned,
and owner-directed, but have not been shown by baseline/out-of-sample evidence
to improve a trading outcome. The report preserves every scan candidate and
reports outcome and gate counts; it does not suppress, reorder, or reclassify
the scan candidate set. Flags remain available for research filtering.

### Full per-stock lifecycle

To project every scan member through the actual lifecycle, run:

```bash
swing-analysis --lifecycle \
  --scan-json /absolute/scan.json \
  --storage-root /absolute/storage-root \
  --analysis-json /absolute/swing-analysis.json \
  --output json
```

The artifact schema is `swing-lifecycle@v1`. Each member carries ordered stages:
`UNIVERSE`, `DATA`, `SAFETY`, `STRUCTURE`, `POLICY`, `CANDIDATE_ANALYSIS`, and
`BASKET`. Statuses are `PASS`, `FAIL`, `UNKNOWN`, `INSUFFICIENT`,
`NOT_EVALUATED`, `NOT_APPLICABLE`, or `NOT_REACHED` as applicable.

The command is read-only: it reads the retained scan and pair-state
observations, makes no provider call, and mutates no state. A safety or data
stop is recorded as terminal; later stages are `NOT_EVALUATED` and are not
fabricated. Candidate analysis is attached only for policy candidates in the
scan's selected candidate list; qualified candidates retained in `other_stocks`
because of basket capacity are `NOT_APPLICABLE` / `NOT_REACHED`. Omitting
`--analysis-json` leaves selected candidates at `NOT_EVALUATED`.

When `--analysis-json` is supplied, the report is bound to the exact scan result
identity, its report identity is recomputed and recorded, and its candidate
coverage must match the selected candidate set.

## Research delivery gate

A scan is not a delivered research result until its private-ledger entry is
written and synced (or the owner explicitly says skip). The answer must name the
entry path and state which layers ran. Reporting candidates before persistence is
a protocol violation.

The scheduled runner satisfies the write automatically:
`scripts/write_scan_ledger_entry.py` derives the entry from the artifacts the run
already produced and appends it once per retained handle, under
`$SWING_LEDGER_ROOT/entries/<year>/<session>-<handle8>-nifty200-scan.md`. Set
`SWING_LEDGER_ROOT` in the service unit (the installer defaults it to
`~/SwingTradingAIAgentLedgerVault`). Unattended writes are marked
`status: unconfirmed`; the owner confirms them in place.

Immediately after writing, the runner pushes the ledger to
`gdrive:SwingResearchLedger` with one `rclone copy --update`. That makes the
off-device copy part of the pass rather than a later hope. Set
`SWING_RCLONE_BIN`, `SWING_LEDGER_REMOTE` or `SWING_SYNC_LOG_DIR` to override the
defaults.

The same installer also enables `research-ledger-sync.timer`, an hourly one-way
`rclone copy` for entries written outside a scheduled run (backfills, manual
passes). Both paths copy new and changed files only and never delete anything on
the Drive side. Keep both schedules installed together: a ledger written but
never synced is still single copy. `scripts/install_research_schedule.sh --check` fails when either schedule
is missing, so a vanished home directory is detected rather than assumed healthy.

The writer refuses a degenerate page because recording it would create a false
"no candidates" market record. The test is the page's shape, not a list of failure
codes: a genuine market result always admits at least one member to the safety
screen, so a page where no member reached a safety outcome means the pass stopped
upstream. This matters because the scan reports the first eligibility rule id,
and observation and safety use different providers: an allowlist of observation
codes would miss a rejected Upstox credential and record that failed pass as a
real zero-candidate day.

Check coverage over any segment:

```bash
python scripts/check_ledger_coverage.py \
  --storage-root /absolute/path/to/SwingTradingAIAssistantData \
  --ledger-root /absolute/path/to/SwingTradingAIAgentLedgerVault \
  --since 2026-10-19
```

It exits `1` and lists every session with a real retained page that no ledger
entry cites. Coverage is per retained page and matched by its exact handle: a
same-day note that shares only the date does not count, and every page that
admitted market facts needs its own entry. `DEGENERATE_ONLY` days are reported
separately and do not fail the check.

A pass fails, rather than reporting success, when the entry cannot be written or
the off-device copy fails. An unset `SWING_LEDGER_ROOT` is a configuration
failure for a scheduled run. Writers serialise on a lock outside the vault and
publish atomically: the entry is written, permissioned and flushed to disk as a
temporary file, then linked into place and the directory entry synced, so an
interruption can leave only a stranded temporary file, never a partial entry
that a retry would accept as existing. Staging names are excluded from both
`rclone` paths, so a stranded one never becomes a permanent remote object.
Backfill a missing day from its retained page without rerunning research:

```bash
python scripts/write_scan_ledger_entry.py \
  --scan-json "$ROOT/scan-decision-evidence-v1/<handle>.json" \
  --ledger-root "$LEDGER" --status recorded --backfill
```

## Market breadth trend

A zero-candidate week should be explainable, not mysterious. After every scan the
runner writes `breadth-YYYY-MM-DD.json` beside the diary page by running:

```bash
python scripts/breadth_trend_report.py \
  --storage-root /absolute/path/to/SwingTradingAIAssistantData \
  --sessions 20 --output json
```

It reads retained scan pages only: no provider call, no credential, no network.
Per completed session it reports the scanned universe's uptrend share, downtrend
share, regime label, cohort size and candidate count. It reports the first and
last shares plus their endpoint deltas, then labels the window `IMPROVING`,
`DETERIORATING`, `FLAT`, or `INSUFFICIENT_HISTORY` from the least-squares change
in uptrend share. Endpoint deltas are contextual facts, not the label criterion:
a series that peaked mid-window and has fallen since would otherwise read as
flat. `confluence` states whether the downtrend share moved the same way.

Two limits are stated in the output itself:

- **It is not an index.** Plan 81 records the Nifty 50 index context bar as
  deferred and admits no index source, and the scan benchmark is the median of
  the scanned stocks (Plan 74). Breadth here means member structure over the
  scanned universe.
- **It cannot reach beyond retained evidence.** The window is whatever sessions
  the store holds, and pages where no member reached a safety outcome are
  excluded, so a provider outage cannot appear as a flat market.

## Performance

The parsed instrument snapshot is cached in process memory by its immutable
content hash. The first lookup parses and validates the snapshot; later lookups
(including every other symbol in the same scan) reuse the parsed catalog. This
removes the repeated multi-second parse that previously dominated a 200-symbol
run.

BharatStock history is also assembled from a persisted per-session cache under
`bharatstock-session-cache-v1`. Each record carries the session row, provider,
price/volume basis, response digests, retrieval time, and a SHA-256 of the
record itself. A window uses cached sessions when valid and fetches only
genuinely missing sessions; a corrupt or mismatched record falls back to the
provider instead of entering a decision. `--refresh` always re-fetches the
terminal session, so corrections are still observed. Composed windows keep at
most 64 distinct source responses; beyond that the full window is re-fetched
and the cache is rewritten.

For a deliberate historical gap, `scripts/backfill_bharatstock_gap.py` fills only
the requested range through the same cache path. It is sequential, sleeps
between symbols, writes a checkpoint after each symbol, and stops immediately on
`RATE_LIMITED` so it can be resumed. It refuses to overwrite existing records,
skips fully covered symbols, and reports remaining gaps. Example:

```bash
doppler run -- .venv/bin/python scripts/backfill_bharatstock_gap.py \
  --storage-root /absolute/path/to/SwingTradingAIAssistantData \
  --universe-snapshot /absolute/path/to/universe_snapshots/nifty-universe-v3.json \
  --start 2026-08-01 --end 2026-09-21 \
  --checkpoint /absolute/path/to/backfill-checkpoint.json \
  --delay 2.0
```

This is a data-acquisition tool, not a scan or research decision. It does not
reconstruct as-published point-in-time history across corporate actions.

