# PRD: Decouple provider data capture from research and analysis

Status: **Draft — owner approval required**
Date: 2026-11-14
Owner: repository owner
Tracking issue: [#421](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/421)
Supersedes: the closed attempt in PR #425

## 1. Problem

On 2026-11-09 a calendar conflict stopped the scan before any provider price
request. BharatStock was available and quota went unused. The later backfill
needed 348 requests and contributed to quota pressure.

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

## 2. Goal

Run a bounded provider capture **before** research, as an independent process
with its own failure domain, while preserving all existing data and fetching
only missing/new sessions.

## 3. Non-goals

- No new provider, endpoint, credential store, or paid quota increase.
- No change to strategy, safety thresholds, or the 21-session trigger.
- No fabrication or backfill of provider history that does not exist.
- No point-in-time relabeling, raw/adjusted mixing, or deletion of existing data.
- No silent fallback from one cache or price basis to another.

## 4. Users and outcomes

| User | Outcome |
|---|---|
| Owner/operator | Provider data is retained even when the research pass or calendar fails. |
| Daily research pass | Reuses the freshly captured terminal session and does not issue a duplicate provider request. |
| Recovery/audit | Existing data and the encrypted off-device backup remain intact; only missing data is fetched. |

## 5. Datasets and sources of truth

Two retained datasets are involved and must not be conflated.

| Dataset | Path | Used by | Capture mode |
|---|---|---|---|
| Raw provider sessions | `bharatstock-session-cache-v1/isin=<ISIN>/exchange=NSE/session=<date>.json` | Research and the 21-session current structure/price action | New capture path; skip existing sessions |
| Adjusted daily history | `adjusted_daily/provider=bharatstock/request=<sha>/data.parquet` | Benchmark, relative strength, long-horizon context | Existing `equity-data-download`; append request identities |

The 252-session requirement is a **provider-history eligibility rule**, not a
252-session trigger. The 21-session setup remains the trigger. A full-year
retained history is useful for benchmark/long-horizon context; provider-limited
symbols remain fail-closed rather than invented.

## 6. Functional requirements

| ID | Requirement |
|---|---|
| FR1 | Capture runs before the daily research scan, as a separate process/timer. |
| FR2 | Capture reads only the retained official Nifty 200 universe and the date. It never reads the exchange calendar, scanner pair state, safety eligibility, or research output. |
| FR3 | Capture writes the existing raw session cache used by research, not only the adjusted benchmark store. |
| FR4 | Capture is additive: existing session files and existing adjusted request stores are reused; only missing/new sessions are fetched. No existing data is deleted or overwritten with a different basis. |
| FR5 | Capture is bounded, checkpointed, resumable, and idempotent. A re-run for the same date makes no provider request for sessions already present. |
| FR6 | Capture and research do not overlap on the exclusive storage-root lock. The scan starts after capture completes or fails, with a capture deadline below the 15-minute schedule gap. |
| FR7 | The research scan reuses a valid capture receipt and does not request the freshly captured terminal session again. If capture failed or is incomplete, the scan may refresh and must report that separately. |
| FR8 | Quota use is observable per stage: requests used, configured maximum, symbols processed, sessions written/skipped, and outcome. No secret is logged. |
| FR9 | Research or calendar failure cannot prevent capture. Capture failure does not fabricate research facts; it blocks only the exact claim that depends on the missing capture. |
| FR10 | A one-time history mode can fill missing raw sessions up to the provider's returned history (target 252 sessions). Existing sessions are skipped; provider-limited symbols remain below 252 and fail closed. |
| FR11 | The encrypted data-root backup includes the captured data and replaces the previous snapshot only after remote verification. Existing local data is never removed by capture. |

## 7. Design

### 7.1 Capture stages

The pre-research capture has two independent sub-steps:

1. **Raw session cache (required):** for each canonical Nifty 200 member, use
   `BharatStockClient.history(..., session_cache_root=root)` over a bounded date
   range. Write only sessions not already present. Record a checkpoint and
   cumulative `requests_used`.
2. **Adjusted daily store (existing):** invoke the existing
   `equity-data-download` in bounded 100-member requests for the same range.
   Reuse its request-identity store; no overwrite.

Each sub-step has its own result. One failing does not stop the other.

### 7.2 Schedule and failure domains

- `swing-data-capture.timer`: 20:15 IST.
- `swing-daily-scan.timer`: 20:30 IST.
- Scan service: `After=swing-data-capture.service` (ordering only, not
  `Requires`), so a failed capture does not block research.
- Capture service timeout: 10 minutes, below the 15-minute gap.
- Capture never holds one exclusive root lease across all provider calls; cache
  writes use the existing short client/storage operation boundary.

### 7.3 Capture receipt and scan handshake

Write `capture-<date>.json` beside the daily artifacts with:

- latest provider session and per-symbol status;
- symbols with complete/incomplete session caches;
- requests used and configured maximum;
- raw-session and adjusted-store outcomes;
- runtime/code identity and timestamps.

The daily runner passes a reuse flag to the scan when the receipt says the
terminal session is present for the member. If it is absent or incomplete, the
scan runs its normal refresh and records `CAPTURE_INCOMPLETE`, never a fabricated
terminal fact.

### 7.4 Locking

The capture must acquire the storage root only for short read/write operations,
not across provider network calls. If the existing client cannot guarantee that,
the capture writes through a per-session narrow path, and the systemd ordering
plus timeout is the second safety layer. A contention test must prove capture
does not block a concurrently started research pass.

### 7.5 Quota and resumability

- Each stage logs `requests_used` and its configured maximum.
- A checkpoint records completed symbols and written sessions per date.
- A re-run skips completed symbols/sessions and makes no provider call for them.
- Rate limiting stops the stage, persists the checkpoint, and reports the
  category without exposing credentials.

## 8. Acceptance criteria

1. **Forced calendar failure:** capture completes; the research pass fails
   independently; captured sessions remain readable.
2. **Forced research failure:** capture is complete and the cache is intact.
3. **Re-run:** a second capture for the same date makes no provider request for
   already-present sessions.
4. **Scan reuse:** after a valid capture, the scan makes no duplicate terminal
   provider request for that member.
5. **Quota:** the receipt/log states requests used and maximum per stage.
6. **Lock:** capture does not block a research pass; the scan starts after the
   capture deadline at the latest.
7. **252 history:** the history mode reaches 252 sessions where provider history
   exists; symbols below 252 remain fail-closed and are named.
8. **No data loss:** existing session files and adjusted request stores remain;
   no full re-download; no deletion of retained data.
9. **Backup:** the encrypted snapshot includes the new data and replaces the
   previous snapshot only after verification.
10. **Tests:** both failure domains, resumable re-run, quota receipt, lock
    ordering, and scan reuse are covered by deterministic tests with no live
    provider dependency.

## 9. Rollout

1. Owner approves this PRD and the open decisions below.
2. Implement the capture CLI/script and receipt.
3. Add tests and independent functional/security review.
4. Merge, install the capture timer, and verify `--status`/`--check`.
5. Run the initial 252-session history mode for the Nifty 200; record
   provider-limited symbols.
6. Run the encrypted backup and verify the remote snapshot.
7. Close #421 only after the acceptance evidence exists.

## 10. Open decisions

| ID | Decision | Recommendation |
|---|---|---|
| D1 | Should the adjusted benchmark store be captured in the same stage as the raw session cache? | Yes, as two independent sub-steps; one failure must not stop the other. |
| D2 | Universe source for capture | Use the same retained official Nifty 200 snapshot the scan admits; do not read the exchange calendar. |
| D3 | Scan handshake | Receipt-driven reuse flag; refresh and record `CAPTURE_INCOMPLETE` when the receipt is missing/incomplete. |
| D4 | 252-session session-cache target | One-time history mode for missing sessions, then daily incremental; never fabricate provider gaps. |
| D5 | Backup retention | Keep the existing replace-after-verification behavior unless the owner requests multiple historical snapshots. |

## 11. References

- Issue #421: capture independently of research and calendar failures.
- Closed PR #425 and its functional/security reviews.
- `src/swing_trading_ai_assistant/market_data/bharatstock.py` (`history`,
  `session_cache_root`).
- `scripts/backfill_bharatstock_gap.py` (existing session-cache mechanics).
- `src/equity_data_downloader/core.py` (adjusted daily request store and lock).
- `scripts/daily_after_close_scan.sh` (current research-first runner).
- `scripts/backup_data_root.sh` (encrypted, verified snapshot replacement).
