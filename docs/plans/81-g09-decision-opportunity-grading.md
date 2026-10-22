# Plan 81: G09 decision opportunity grading (report-only)

Status: accepted bounded implementation contract under [Issue #343](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/343). Governing recipe: G09 filter-qualification recipe FROZEN v1, owner-accepted 2026-10-19 ([#332 comment 6257791900](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/332#issuecomment-6257791900)). Owner and risk owner: Krunal Dodiya. Risk tier: R3 financial-research reporting and public CLI. Base: `2b6b3aba96c0a47f824f0d85754b62a565ef8a1f`.

## Context

The first retained nightly decision page exists (2026-10-19, universe `NIFTY_200`, 200 rows, handle `0c7eca9f72fcf18be35263ce7eb2f9c3813a6b44f2e1ba49f74dcae34b48e1b0`). Recipe v1 section 10 authorizes the opportunity-side grader now. The owner selected G09 outcome-grading tooling as the next work item.

The recipe was written against the former Nifty-500 nightly scan set. Per the owner-approved universe transition (#339), its numbers and rules are unchanged and its scan-set denominators are the current nightly page rows: the exact Nifty 200, one page per retained run, one row per evaluated symbol. The grader reads whatever exact universe the page records and never resolves a universe itself.

## Outcome and first working slice

One read-only command reports the frozen-recipe opportunity facts for exactly one retained page:

`signal-decisions grade-decision-evidence --storage-root ROOT [--decision-evidence HANDLE] [--output json|table]`

- Re-admits the page through the existing runtime-bound evidence read path.
- Binds the decision session, the decision-day close, and the next up-to-10 official sessions from retained evidence only.
- Reports per-row hit/first-touch/pending/unavailable facts, candidate buckets, every non-candidate miss with its recorded reason, page counts, the fixed-denominator universe base rate, and pass-shape ingredients.
- Retains nothing; makes no provider, network, credential, clock, or ledger-vault access.

With no `--decision-evidence`, the command grades the latest retained page by `scan_timestamp` then handle. A second page handle in one invocation is refused: multi-page and walk-forward aggregation are outside this slice.

## Non-goals

No retained grading record or new namespace; no walk-forward/series aggregation; no Nifty 50 index context bar; no change to the nightly runner, scanner, evidence writer, measurement output, frozen recipe numbers, or universe handling; no AI evaluation or advice language; no provider authorization; no ledger-vault read. Missing evidence is never filled, simulated, or graded early.

## Read-only sources (all under `--storage-root`)

- Page: `scan-decision-evidence-v1/<handle>.json`, re-admitted with `read_scan_decision_evidence_v1` (`scan-decision-evidence@v1`, `swing-trade-scan@v2`). The page's symbols, decisions, reasons, observation handles, scan timestamp, universe type, and row count are authoritative for its own scope.
- Official calendar: `calendar-schedules/sha256/<digest>.json`, content-addressed by the SHA-256 of the stored bytes; each record has `sessions` (`trade_date`, `kind`, `open_at`, `close_at`), `closures`, and a covered range. Read under the storage-root read lease; a record whose file name, bytes, canonical re-serialization, or digest disagree fails closed.
- Capture bars: `bharatstock-capture-v3/revisions/<revision>.json`, enumerated under one borrowed read lease and re-admitted with `read_bharatstock_capture_revision_v2` before any bar is used. No raw-response, network, or provider path is imported or called.

All three stores are immutable and owner-only. Entry files must remain regular, single-link, owner-owned, non-symlink, and size-bounded; the grader refuses rather than skips unsafe entries.

## Decision session

The page stores a `scan_timestamp` but no decision-session field, and the nightly runner binds the latest completed session at run time. The grader therefore resolves the page's decision session `D` deterministically:

1. Collect all retained schedule sessions and closures.
2. `D` = the latest `trade_date` whose session `close_at` is at or before the page's `scan_timestamp`.
3. Every schedule record that covers `D` must list it as a session; any record listing `D` as a closure is a calendar conflict. No qualifying session, an ambiguous latest session, or a calendar conflict fails closed with `DECISION_SESSION_UNRESOLVED`.

The resolved `D` and the exact source records are printed in the report.

## Window rule

The window is the first **10** official sessions strictly after `D`, drawn from the union of retained schedule sessions, with any date that any retained record places in `closures` removed.

- Fewer than 10 retained later sessions means a pending window; the retained count and the known sessions are printed. Sessions are never extrapolated, guessed, or filled.
- A date listed both as a session and as a closure is `CALENDAR_CONFLICT` and fails closed.
- Nothing after session 10 is evaluated. The 5th session is reported as a progress marker only; it changes no threshold.

## Bar binding

For each page symbol the grader uses one admitted capture revision for the whole read, so the decision close and every window high share one adjustment basis:

1. Enumerate retained capture revisions once and index, from admitted revision values only, each revision's symbol, `observed_at`, request sessions, and per-session rows. Revisions without a row for the symbol or without `D` are not candidates. Bound the enumeration (see Bounds); unsafe or unreadable entries fail closed.
2. Choose the revision containing `D` and the most window sessions for that symbol; ties break on earliest `observed_at`, then revision identity. One revision per symbol is used.
3. The chosen revision's row for `D` supplies the decision-day close. A window session with no row in the chosen revision is reported `MISSING`; a later revision never backfills it in this slice.
4. A symbol with no admitted revision containing `D` is `UNAVAILABLE` with `DECISION_BAR_UNAVAILABLE`. Its rows/observation handles remain listed; no price is invented.

Adjustment handling inside one revision:

- When every used row has `adjusted_close`, use `adjusted_close` for the decision close and the implied factor `adjusted_close / close` for the high, so a split or bonus inside the window cannot create a false touch or a false reversal.
- When no used row has `adjusted_close`, use the source-reported `close` and `high` unchanged.
- A mix of adjusted and unadjusted used rows is `UNAVAILABLE` with `MIXED_ADJUSTMENT_EVIDENCE`; no raw/adjusted mixing.
- A row that fails the capture price invariants (non-positive, malformed, inconsistent adjustment identity) makes that row unavailable, never silently skipped.

Ratios and thresholds use `Decimal` with at least 64-digit precision and exact comparisons; no binary float is used for grading.

## Outcome arithmetic

- Opportunity bar: `high_s >= decision_close_D * 1.03` for some window session `s` (gross, inclusive boundary). First-touch session is the earliest such `s`; its 1-based index is `first_touch_day_index`.
- The opportunity threshold is gross; the cost bar applies to reported returns and buckets, not to the touch test.
- Cost bar: exactly 25 basis points round trip (`0.0025`).
- Exit rule (recorded owner clarification): if a touch occurs, exit at the touch threshold: gross `+3.00%`, net `+2.75%`, `exit_basis = OPPORTUNITY_THRESHOLD`. If the window completes without a touch, exit at session 10's close: `net = adjusted_close_s10 / adjusted_close_D - 1 - 0.0025`, `exit_basis = WINDOW_CLOSE`.
- Candidate buckets, net of cost: `profit` when a touch occurred; otherwise `flat` when the completed window's net close return is `>= 0`; otherwise `reversed`. The bucket's exact net return and exit session are always printed; a `flat` row may still show a small positive return below the +3% bar.
- A hit with an earlier missing session keeps the hit (the opportunity is real) but sets `first_touch_certified = false`; it never invents an earlier index. A completed window requires all ten sessions present.

## Row accounting, skips, and base rate

- Every page row is one of `HIT`, `NO_HIT`, `PENDING`, `UNAVAILABLE`. `PENDING` covers both an incomplete window and missing session rows without an observed touch.
- Every non-candidate row (`NO_TRADE`/`UNKNOWN`) that hits is a missed opportunity, listed with symbol, decision date `D`, the row's recorded skip reason, safety status, and whether it was a deliberate safety block. Reasons come only from the page (`scan.other_stocks[].failed_rule`); a missing reason is printed as `UNRECORDED` and sets `named_rule_trace_complete = false`, never invented.
- **Universe base rate denominator is the page's full evaluated row set** (the count of page rows; must equal `total_stocks_scanned` and the ordered `evaluated_symbols`). `PENDING` and `UNAVAILABLE` rows count as scanned non-hits unless their retained bars already show a touch, applying the same rule to every row. The denominator never shrinks.
- `candidate_rate = candidate hits / candidate rows`; `null` when the page has zero candidates. Zero-candidate pages are valid and unpenalized.
- `miss_rate = missed opportunities / all opportunities`; `null` when there are zero opportunities. No division by zero and no invented pass verdict.

## Pass-shape ingredients

The frozen recipe's three-way pass shape is a series judgement and is deferred. This slice prints its per-page ingredients only when the page's window is fully completed; while pending it prints `state = PENDING` and `null` ingredients:

- `missed_opportunities`, `opportunities`, `miss_rate`;
- `candidate_rate`, `base_rate`, `separation_multiple = candidate_rate / base_rate`;
- `named_rule_trace_complete`;
- `meets_miss_bar = miss_rate <= 0.20` and `meets_separation_bar = candidate_rate >= 2 * base_rate`, each `null` when its input is undefined;
- `verdict = NOT_EVALUATED_SINGLE_PAGE` (never a pass/fail claim from one page).

The run's exit code still distinguishes a complete report (`0`) from pending/partial (`1`); that is a data-state fact, not a recipe verdict.

## Report contract

Canonical compact JSON + trailing newline, `schema = "g09-decision-opportunity-report@v1"`, with `report_identity_sha256` over the report excluding that field. The report includes:

- `recipe`: frozen-v1 identity, source URL/comment, owner-accepted instant, opportunity bar `300` bp, cost bar `25` bp, window `10`.
- `page`: evidence handle, scan result identity, scan timestamp, universe type, resolved decision session and its schedule provenance, row count, decision counts, evaluated-symbol count.
- `window`: ordered sessions, retained sessions, state, missing sessions, 5-session progress marker.
- `rows`: symbol, decision, reason (or null), safety status, observation handle (or null), state, decision close and its bar-source revision/observed-at/price basis, first-touch session/index/ratio in bp, certification flag, bucket, exit basis/session, net return in bp, missing sessions, typed unavailability reason, and miss flag.
- `summary`: counts by state and decision, candidate quality buckets, opportunities, misses, base rate with the fixed denominator, candidate rate, named-rule completeness, pass-shape ingredients, and limitation lines.
- `limitations`: at minimum the recipe's missing-bar, no-AI, no-backfill, Nifty-50-context-deferred, and single-page-scope statements.

`--output table` prints only page identity, window state, counts, candidate rows, and the miss list; it is a view of the same computed report. Errors print one typed code to stderr, never a partial report or a private path.

## Exit codes

- `0`: valid report, every row `HIT` or `NO_HIT`, window complete.
- `1`: valid report with at least one `PENDING` or `UNAVAILABLE` row/window.
- `2`: typed request, evidence, calendar, store, or identity failure; nothing partial on stdout.

## Failure precedence (closed)

1. Invalid CLI request (handle format, output mode, repeated handles, wrong root type) -> exit 2, no report.
2. Unsafe/unreadable/unretained page, identity mismatch, or store lease failure -> exit 2, no report.
3. Decision session unresolved or calendar conflict -> exit 2, no report.
4. Page row count/evaluated symbols inconsistent with `total_stocks_scanned` -> exit 2, no report.
5. Per-symbol bar absence or mixed adjustment -> row `UNAVAILABLE`, report printed, exit 1.
6. Incomplete window -> row/page `PENDING`, report printed, exit 1.
7. A complete window with zero misses/opportunities -> valid report, exit 0.

## Bounds

Page rows: 1..500. Window sessions: exactly 10 when complete, fewer while pending. Schedule records read: at most 256; schedule bytes at most 4 MiB each. Capture revisions enumerated: at most 5000; one revision file at most 8 MiB; index rows at most 1,000,000. Report bytes at most 8 MiB. Canonical depth at most 64. All limits are refusals, never truncation.

## Adversarial matrix (frozen before implementation)

1. Day-1 touch counts; day-2, day-5, and day-10 touches count; day-11 does not.
2. Exact `+3.00%` boundary counts; `+2.9999%` does not.
3. A window with a missing 7th session cannot become a completed no-hit; it is pending/missing and never filled.
4. Fewer than 10 retained later sessions -> pending with the retained count; no extrapolation.
5. A split/bonus-shaped window: adjusted values inside one revision give the same economic ratio a raw basis would give without the action; adjusted/unadjusted mixes fail closed.
6. A candidate that touches on day 3 while day 1 is missing is a hit with `first_touch_certified = false`; no invented earlier index.
7. A completed no-touch candidate ending exactly at zero net is `flat`; below zero is `reversed`; the +25 bp cost is subtracted once.
8. Zero-candidate page: valid, `candidate_rate = null`, no crash and no pass claim.
9. Zero-opportunity page: valid, `miss_rate = null`, base rate zero, no division by zero.
10. Every non-candidate appears in the miss list when it hits, with its recorded reason; a missing recorded reason becomes `UNRECORDED` and breaks named-rule completeness.
11. Three observation-less rows still grade from retained capture bars; if their decision bars are absent they are `UNAVAILABLE`, not skipped from the denominator.
12. Decision-session resolution: after-close evening scan and next-morning post-midnight scan of the same completed session both resolve the same `D`; a holiday run resolves the prior session.
13. A schedule record that lists `D` as a closure -> exit 2; a second page handle -> exit 2; malformed handle -> exit 2.
14. Unsafe store entry (symlink, wrong owner/mode/link count, oversize, non-canonical name) -> fail closed, no report.
15. No network, provider, credential, clock, or ledger access on any path (monkeypatched to fail in tests).
16. Report re-run on the same retained bytes yields the identical canonical bytes and identity.

## Tests-first plan

1. Pure tests for decision-session resolution, window selection, schedule conflicts, ratio/boundary arithmetic, bucket boundaries, base-rate denominators, and pass-shape nullability.
2. Fixture-store tests for page re-admission, revision enumeration/admission, one-revision bar binding, missing bars, adjustment shapes, observation-less rows, and reason projection.
3. CLI tests for JSON/table, exit 0/1/2, repeated handles, malformed handles, and no partial stdout on failure.
4. Determinism tests for canonical bytes/identity and a no-effect test proving no writes and no provider/clock calls.

Tests use synthetic retained fixtures only; no live market data is required and no test reads the production store by default.

## Delivery and verification

- R3: independent functional/domain and security/privacy/provenance reviews on the exact committed candidate; focused checks first, then the applicable full gates and hosted CI.
- Format owned files before refreshing the directly and transitively bound source-at-rest manifests. Add the new module and any changed module to the generic market-data inventory and to the grading runtime manifest used by the new command; verify page readback remains self-consistent.
- Docs in the same governed change: `docs/agent-usage.md` command row; `docs/workflows/automated-nifty100-scan.md` grading section; Plan 34/Plan 61 recipe cross-references. Documentation-only verification is `git diff --check`.
- No change to `run.sh`, scanner thresholds, evidence writer, measurement output, or the frozen recipe; the nightly page remains byte-identical except manifest-driven runtime identity.
- After merge, run the command once against the production page as a read-only observation; today's honest result is a pending window (zero later sessions retained), not an outcome claim.

## Interpretation notes (bounded, flagged for review)

- Recipe v1 names the candidate buckets but does not define `flat`/`reversed` boundaries. This contract fixes them as stated above: profit = touch; flat = completed no-touch with net >= 0; reversed = completed no-touch with net < 0. The actual net return is always printed.
- Recipe v1 does not define the exit price for a touch. This contract uses the touch threshold (+3.00% gross), the only price derivable from daily bars without intraday assumptions.
- The recipe's per-session bar source is not specified. This contract uses one revision per symbol so the comparison basis is internally consistent; later revisions are ignored for that read and never backfill missing sessions.
- The recipe's own §6 pass shape is a series evaluation; single-page ingredients are reported without a verdict.

## Amendment 1 (owner-approved implementation corrections, 2026-10-20)

Recorded during the #343 implementation session. The frozen text above remains
the historical contract; this amendment supersedes only the items listed here.
Frozen recipe numbers, the opportunity/cost/window arithmetic, the fixed
page-row denominator, the no-backfill rule, and the single-page scope are
unchanged.

1. **Exit codes and failure precedence.** A typed evidence/calendar/store/
   identity failure prints one closed JSON unavailable envelope on stdout and
   exits `1`; invalid CLI requests exit `2` with one redacted stderr line. This
   matches the existing read commands and is the correction recorded for
   #343. Matrix item 13's closure-conflict case is therefore exit `1`;
   repeated/malformed handles remain exit `2`. A complete report exits `0`; a
   report with any pending or unavailable row/window exits `1`.
2. **Bounds.** Schedule records: at most 4,096 with 64 MiB total (the retained
   calendar has 1,556 records; 256 cannot represent it). Capture revisions:
   at most 20,000 files, 8 MiB each, 1,000,000 index rows, 100 members per
   revision. Report: 8 MiB; depth 64. All limits are refusals.
3. **Calendar integrity.** Raw bytes are bound to the file-name SHA-256; every
   session and closure must lie inside its record's covered range; duplicate
   JSON keys are rejected; a tie for the latest qualifying close instant is
   `CALENDAR_CONFLICT`. Canonical re-serialization is not required: the digest
   is over the exact retained bytes and duplicate-key ambiguity is refused.
4. **Revision indexing.** Selection metadata is read from retained revision
   values; the chosen revision is re-admitted before any bar is used. A later
   revision never backfills. Unsafe or unreadable entries fail closed.
5. **Report shape.** The resolved `D` and calendar counts are in `window`;
   `page` carries page identity, counts, and the evaluated-symbol count.
   `limitations` is top-level. `storage_root_sha256` is omitted to reduce
   linkability.
6. **Pass-shape ingredients.** Ingredients require a complete 10-session
   window and every row `HIT`/`NO_HIT`. Interim rates from unresolved rows are
   not published as final ingredients.
7. **No-handle selection.** The command reads each page's hash-bound raw
   `scan_timestamp` and fully re-admits only the chosen page, keeping the
   no-handle mode usable as pages accumulate.
8. **Read-only lease.** The grader and the evidence reader borrow an existing
   storage-root lease and never create `.ingestion.lock` or other store state.
   The lister alone treats an admitted private root with **neither a lock nor
   an evidence namespace** as an uninitialized store and reports zero coverage;
   any lock or namespace present is leased read-only, and unsafe, busy, or
   unavailable namespace states fail closed.

## Amendment 2 (owner-approved implementation clarifications, 2026-10-21)

Owner approved this amendment on 2026-10-21. It clarifies the implementation
without changing the frozen recipe, arithmetic, window, denominator, or
single-page scope.

1. **Calendar schemas.** Only exact integer `schema_version` values `1`, `2`, and
   `3` are admitted. Schema v1 records omit the `closures` key; v2/v3 records
   must contain it. Sessions must bind to their local trade date and minute
   boundary. This preserves compatibility with retained v1 evidence while
   rejecting malformed or unsupported calendar records.
2. **Additive report fields.** `window` carries `decision_close_at` and
   `calendar_sources` (raw-byte digest, covered range, session/closure counts)
   for auditability. Every completed row carries the exact `net_return` decimal
   string alongside `net_return_bp`; a touch exit and its exact net return are
   printed for candidate and non-candidate hits alike.
3. **Measurement identity.** Binding `storage_root_lease.py` in the measurement
   runtime inventory changes the identity field only; measurement numbers and
   semantics are unchanged. This identity closure is required by the read-only
   lease correction and is exempt from the Plan's measurement-output non-goal.
