# PRD: Decouple provider data capture from research and analysis

Status: **Approved for implementation — D1–D3 approved 2026-11-14**
Date: 2026-11-14
Owner: repository owner
Tracking issue: [#421](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/421)
Supersedes: the closed attempt in PR #425

## 1. Problem

On 2026-11-09 a calendar conflict stopped the scan before any provider price
request. BharatStock was available and quota went unused.

The current daily runner starts with the research scan. Capture and research
therefore share one failure domain. When research or the calendar fails, the
day's provider data is not retained.

The attempted fix in PR #425 was closed because it:

1. wrote the `adjusted_daily` benchmark store, not the
   `bharatstock-session-cache-v1` cache research reads;
2. could hold the shared exclusive storage-root lease past the 20:30 research
   start and block it;
3. did not expose provider quota use per stage; and
4. did not test resumable capture or both failure domains.

It did not delete existing data. The close was about the wrong cache, lock
overlap, missing quota observability, and missing tests.

## 2. Goal

Run a bounded provider capture **before** research, as an independent process
with its own failure domain, while preserving all existing data and fetching
only missing or new sessions. This is a process change, not a data migration:
the existing files stay in place and in their current folders.

## 3. Non-goals

- No new provider, endpoint, credential store, or paid quota increase.
- No change to research strategy, safety policy, or price basis.
- No fabrication or backfill of provider history that does not exist.
- No raw/adjusted mixing or deletion of existing data.
- No silent fallback from one cache or price basis to another.

## 4. Users and outcomes

| User | Outcome |
|---|---|
| Owner/operator | Provider data is retained even when the research pass or calendar fails. |
| Daily research pass | Reuses the freshly captured terminal session and does not issue a duplicate provider request. |
| Recovery/audit | Existing data remains in place; only missing or new data is fetched. |

## 5. Datasets and sources of truth

Two retained datasets are involved and must not be conflated.

| Dataset | Path | Used by | Capture mode |
|---|---|---|---|
| Raw provider sessions | `bharatstock-session-cache-v1/isin=<ISIN>/exchange=NSE/session=<date>.json` | Research and the current structure/price action | New capture path; skip existing sessions |
| Adjusted daily history | `adjusted_daily/provider=bharatstock/request=<sha>/data.parquet` | Benchmark and relative strength | Existing `equity-data-download`; append request identities |

Capture writes the same paths. Existing files and request stores are reused;
nothing is migrated or deleted.

## 6. Functional requirements

| ID | Requirement |
|---|---|
| FR1 | Capture runs before the daily research scan, as a separate process/timer. |
| FR2 | Capture reads only the retained official Nifty 200 universe and the date. It never reads the exchange calendar, scanner pair state, safety eligibility, or research output. |
| FR3 | Capture writes the existing raw session cache used by research, not only the adjusted benchmark store. |
| FR4 | Capture is additive: existing session files and existing adjusted request stores are reused; only missing/new sessions are fetched. Existing data is not deleted or overwritten with a different basis. |
| FR5 | Capture is bounded, checkpointed, resumable, and idempotent. A re-run for the same date makes no provider request for sessions already present. |
| FR6 | The scheduled capture and the scheduled research scan do not overlap on the exclusive storage-root lock. The scan starts after capture completes or fails, with a capture deadline below the 15-minute schedule gap. |
| FR7 | The research scan reuses a valid capture receipt and does not request the freshly captured terminal session again. If capture failed or is incomplete, the scan may refresh and must record `CAPTURE_INCOMPLETE`. |
| FR8 | Quota use is observable per stage: requests used, configured maximum, symbols processed, sessions written/skipped, and outcome. No secret is logged. |
| FR9 | Research or calendar failure cannot prevent capture. Capture failure does not fabricate research facts; it blocks only the exact claim that depends on the missing capture. |

## 7. Design

### 7.1 Capture stages

The pre-research capture has two independent sub-steps:

1. **Raw session cache (required):** for each canonical Nifty 200 member,
   determine the newest cached session, skip the member when it is already at
   the requested end, and otherwise call
   `BharatStockClient.history(..., session_cache_root=root)` only for the newer
   range. Existing session files are reused; only new sessions are written.
   Record a checkpoint and cumulative `requests_used`, including failed or
   rate-limited attempts.
2. **Adjusted daily store (existing):** invoke the existing
   `equity-data-download` in bounded 100-member requests only for the adjusted
   range not already present. Reuse its request-identity store; no overwrite or
   full-range re-download.

Each sub-step has its own result. One failing does not stop the other.

### 7.2 Schedule and failure domains

- `swing-data-capture.timer`: 20:15 IST.
- `swing-daily-scan.timer`: 20:30 IST.
- Scan service: `After=swing-data-capture.service` (ordering only, not
  `Requires`), so a failed capture does not block research.
- Capture service timeout: 10 minutes, below the 15-minute gap.
- The scheduled capture and scan therefore do not overlap. The adjusted stage
  may hold the root lease during its bounded batch; that lease is released
  before the scheduled scan starts.

### 7.3 Capture receipt and scan handshake

Write `capture-<date>.json` beside the daily artifacts with:

- latest provider session and per-symbol status;
- symbols complete, skipped, failed, or pending;
- requests used and configured maximum per stage;
- raw-session and adjusted-store outcomes;
- runtime/code identity, universe snapshot digest, and timestamps.

The daily runner passes a reuse flag to the scan only when the receipt says every
symbol is complete and the terminal session is present. If the receipt is
missing or incomplete, the scan runs its normal refresh and records a typed
`CAPTURE_INCOMPLETE` marker; it never fabricates a terminal fact.

### 7.4 Locking

The scheduled capture and scheduled research must not run concurrently. The
20:15/20:30 timers, the 10-minute capture deadline, and the scan's `After=`
ordering provide that guarantee. The adjusted sub-step uses the existing
downloader's bounded batch lease; it must finish before the scan begins.

A manually started research pass during a capture batch can still observe the
lease and fail closed. That ordering-only residual must be documented and
covered by a contention/ordering test; it is not used to claim concurrent
capture/research support.

## 8. Acceptance criteria

1. **Forced calendar failure:** capture completes; the research pass fails
   independently; captured sessions remain readable.
2. **Forced research failure:** capture is complete and the cache is intact.
3. **Re-run:** a second capture for the same date makes no provider request for
   sessions already present.
4. **Scan reuse:** after a valid capture, the scan makes no duplicate terminal
   provider request for that member.
5. **Quota:** the receipt/log states requests used and maximum per stage,
   including failed attempts.
6. **Lock/order:** the scheduled capture and scan do not overlap; a contention
   test proves the documented ordering guarantee.
7. **No data loss:** existing session files and adjusted request stores remain;
   no full re-download; no deletion of retained data.
8. **Tests:** both failure domains, resumable re-run, receipt status, quota,
   lock ordering, and actual scan reuse are covered by deterministic tests with
   no live provider dependency.

## 9. Rollout

1. Owner approves this PRD and D1–D3.
2. Implement the capture CLI/script and receipt.
3. Add tests and independent functional/security review.
4. Merge, install the capture timer, and verify `--status`/`--check`.
5. Close #421 only after the acceptance evidence exists.

## 10. Approved decisions

Owner approved 2026-11-14.

| ID | Decision |
|---|---|
| D1 | Capture the adjusted benchmark store in the same stage as the raw session cache, as two independent sub-steps; one failure must not stop the other. |
| D2 | Use the retained official Nifty 200 snapshot the scan admits; do not read the exchange calendar. |
| D3 | Receipt-driven scan reuse; when the receipt is missing or incomplete, refresh and record `CAPTURE_INCOMPLETE`. |

## 11. References

- Issue #421: capture independently of research and calendar failures.
- Closed PR #425 and its functional/security reviews.
- `src/swing_trading_ai_assistant/market_data/bharatstock.py` (`history`,
  `session_cache_root`).
- `scripts/backfill_bharatstock_gap.py` (existing session-cache mechanics).
- `src/equity_data_downloader/core.py` (adjusted daily request store and lock).
- `scripts/daily_after_close_scan.sh` (current research-first runner).
