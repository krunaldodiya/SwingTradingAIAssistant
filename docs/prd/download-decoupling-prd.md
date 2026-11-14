# PRD: Decouple provider data capture from research and analysis

Status: **Approved for implementation — D1–D4 approved 2026-11-14**
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

A 20:00 head-start timer alone is not a correctness guarantee. The guarantee is
that the 20:30 research runner performs the capture preflight before it starts
any scan, research, or analysis.

## 2. Goal

Run a bounded provider capture **before** research, as the first step of the
research runner, with its own failure domain. Existing data stays in place; the
capture is additive and fetches only missing or new sessions. A separate 20:00
timer is an optional head start, not the correctness mechanism.

## 3. Non-goals

- No new provider, endpoint, credential store, or paid quota increase.
- No change to research strategy, safety policy, or price basis.
- No fabrication or backfill of provider history that does not exist.
- No raw/adjusted mixing or deletion of existing data.
- No silent fallback from one cache or price basis to another.
- No separate download-only schedule that can drift from the research runner.

## 4. Users and outcomes

| User | Outcome |
|---|---|
| Owner/operator | Provider data is retained even when the research pass or calendar fails. |
| Daily research pass | Starts only after the capture preflight; it reuses the captured terminal session and does not issue a duplicate provider request. |
| Recovery/audit | Existing data remains in place; only missing or new data is fetched. |

## 5. Datasets and sources of truth

Two retained datasets are involved and must not be conflated.

| Dataset | Path | Used by | Capture mode |
|---|---|---|---|
| Raw provider sessions | `bharatstock-session-cache-v1/isin=<ISIN>/exchange=NSE/session=<date>.json` | Research and the current structure/price action | Capture preflight; skip existing sessions |
| Adjusted daily history | `adjusted_daily/provider=bharatstock/request=<sha>/data.parquet` | Benchmark and relative strength | Existing `equity-data-download`; append request identities |

Capture writes the same paths. Existing files and request stores are reused;
nothing is migrated or deleted.

## 6. Functional requirements

| ID | Requirement |
|---|---|
| FR1 | The daily research runner performs the capture as its **first step**, before any scan, research, or analysis. A separate 20:00 timer MAY run the same capture earlier as an optional head start. |
| FR2 | Capture reads only the retained official Nifty 200 universe and the date. It never reads the exchange calendar, scanner pair state, safety eligibility, or research output. |
| FR3 | Capture writes the existing raw session cache used by research, not only the adjusted benchmark store. |
| FR4 | Capture is additive: existing session files and existing adjusted request stores are reused; only missing/new sessions are fetched. Existing data is not deleted or overwritten with a different basis. |
| FR5 | Capture is bounded, checkpointed, resumable, and idempotent. A re-run for the same date makes no provider request for sessions already present. |
| FR6 | At 20:30, the research runner checks the capture state: if the 20:00 head start is still active, it **waits**; if complete, it **skips**; if timed out or failed, it **resumes from the checkpoint**. It never kills or discards the active 20:00 work and never starts a duplicate capture. The 30-minute gap is a head-start budget, not a hard data-download limit. |
| FR7 | The research scan reuses a valid capture receipt and does not request the freshly captured terminal session again. If capture is incomplete, the preflight runs/resumes first; the scan records `CAPTURE_INCOMPLETE` and never fabricates a terminal fact. |
| FR8 | Quota use is observable per stage: requests used, configured maximum, symbols processed, sessions written/skipped, and outcome. No secret is logged. |
| FR9 | Research or calendar failure cannot prevent capture. Capture failure does not fabricate research facts; it blocks only the exact claim that depends on the missing capture. |

## 7. Design

### 7.1 Capture stages

The preflight has two independent sub-steps:

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

### 7.2 Two-layer schedule

- `swing-daily-scan.timer` (existing): 20:30 IST. Its runner performs the
  capture preflight as its first step, then scan/research/analysis.
- `swing-data-capture.timer` (optional): 20:00 IST. It runs the same capture as
  an early head start; it is not a correctness dependency.
- If the 20:00 capture is still active when the 20:30 runner starts, the runner
  waits for it. If it completed, the preflight is a no-op. If it timed out or
  failed, the preflight resumes from its checkpoint.
- The 20:00 service uses a clean 25-minute head-start budget. On reaching that budget it
  stops gracefully, leaves the checkpoint, and the 20:30 preflight continues.
- The research service may start later than 20:30 when the preflight takes
  longer; the 20:30 timer is a start trigger, not a deadline for the data.
  The research service timeout must allow the preflight plus the scan; if a
  very large backfill exceeds it, captured data remains checkpointed and the
  research retries.
- The scan service also carries `After=swing-data-capture.service` as a
  secondary ordering guard when the 20:00 head start is installed as a systemd
  service. A manual 20:00 capture is detected by the storage lock/checkpoint;
  the 20:30 runner waits rather than duplicating it.

### 7.3 Capture receipt and scan handshake

Write `capture-<date>.json` beside the daily artifacts with:

- latest provider session and per-symbol status;
- symbols complete, skipped, failed, or pending;
- requests used and configured maximum per stage;
- raw-session and adjusted-store outcomes;
- runtime/code identity, universe snapshot digest, and timestamps.

The 20:30 preflight reads the receipt. If every symbol is complete, the scan
receives the reuse flag. If the receipt is missing or incomplete, the preflight
runs/resumes the capture; the scan records a typed `CAPTURE_INCOMPLETE` marker
and never fabricates a terminal fact.

### 7.4 Locking and wait semantics

The 20:00 capture and the 20:30 research must not run concurrently:

- If the 20:00 capture is active at 20:30, the research runner waits.
- If it completed, the preflight skips.
- If it timed out or failed, the preflight resumes from the checkpoint.
- The runner never kills the active capture, never discards completed work, and
  never launches a duplicate capture.
- The adjusted sub-step uses the existing downloader's bounded batch lease; the
  preflight and the research scan are sequential. A manually started research
  pass during a capture batch observes the lease and waits/fails closed. That
  ordering-only residual must be documented and covered by a contention test.

## 8. Acceptance criteria

1. **Forced calendar failure:** the preflight capture completes; the research
   pass fails independently; captured sessions remain readable.
2. **Forced research failure:** the preflight is complete and the cache is
   intact.
3. **Re-run:** a second capture for the same date makes no provider request for
   sessions already present.
4. **20:00 active at 20:30:** the 20:30 runner waits; it does not kill or
   duplicate the capture; research starts after the capture finishes or its
   checkpoint is resumed.
5. **20:00 timed out/failed:** the 20:30 preflight resumes from the checkpoint
   and fetches only what is still missing.
6. **Scan reuse:** after a complete preflight, the scan makes no duplicate
   terminal provider request for that member.
7. **Quota:** the receipt/log states requests used and maximum per stage,
   including failed attempts.
8. **No data loss:** existing session files and adjusted request stores remain;
   no full re-download; no deletion of retained data.
9. **Tests:** both failure domains, the 20:00-active wait, the timed-out resume,
   resumable re-run, receipt status, quota, lock ordering, and actual scan reuse
   are covered by deterministic tests with no live provider dependency.

## 9. Rollout

1. Owner approves this PRD and D1–D4.
2. Implement the 20:30 preflight, the optional 20:00 head start, and the
   wait/resume behavior.
3. Add tests and independent functional/security review.
4. Merge; install/verify the optional 20:00 timer and verify the 20:30 preflight.
5. Close #421 only after the acceptance evidence exists.

## 10. Approved decisions

Owner approved 2026-11-14.

| ID | Decision |
|---|---|
| D1 | Capture the adjusted benchmark store in the same stage as the raw session cache, as two independent sub-steps; one failure must not stop the other. |
| D2 | Use the retained official Nifty 200 snapshot the scan admits; do not read the exchange calendar. |
| D3 | Receipt-driven scan reuse; when the receipt is missing or incomplete, refresh and record `CAPTURE_INCOMPLETE`. |
| D4 | The 20:30 research runner performs the capture preflight. The 20:00 timer is an optional head start. At 20:30: wait for an active capture, skip if complete, resume the checkpoint if timed out/failed; never discard, kill, or re-run from zero. The 30-minute gap is a head-start budget, not a data-download limit. |

## 11. References

- Issue #421: capture independently of research and calendar failures.
- Closed PR #425 and its functional/security reviews.
- `src/swing_trading_ai_assistant/market_data/bharatstock.py` (`history`,
  `session_cache_root`).
- `scripts/backfill_bharatstock_gap.py` (existing session-cache mechanics).
- `src/equity_data_downloader/core.py` (adjusted daily request store and lock).
- `scripts/daily_after_close_scan.sh` (20:30 research runner and preflight host).
- `scripts/systemd/swing-daily-scan.timer` and
  `scripts/systemd/swing-data-capture.timer`.
