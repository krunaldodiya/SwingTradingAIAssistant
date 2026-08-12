# Bounded Nifty 50 Workflow Contract

Status: implemented by ARK-141 and ARK-12.

## Purpose

Provide one symbol-agnostic workflow for downloading, resuming, inspecting, and
querying one, several, or all point-in-time Nifty 50 equities. `NSE_EQ` is the
Upstox exchange-segment identifier; Upstox remains the sole candle provider.
The separate universe artifact proves index membership and sector provenance
only. It is never used as a price source.

## Inputs and outputs

The public selection is exactly one of `--symbol SYMBOL`,
`--symbols SYMBOL_A,SYMBOL_B`, or `--universe nifty50-current`. Shell input that
contains an ampersand must be quoted, for example `--symbol "M&M"` or
`--symbols "M&M,BAJAJ-AUTO"`. Download also accepts an optional canonical
`--universe-file` for first retention,
`--universe-as-of` (default: requested end date), and `--workers 1..8`
(default: 4). Coverage and query consume the already-retained universe and
accept the same selection and worker bound. Existing closed-date, timeframe,
field, row, schedule, and JSON-output arguments remain unchanged. The CLI
storage-root option is configurable and defaults to the recursively created
`~/SwingTradingAIAssistantData`; downstream typed requests still receive an
absolute `Path`.

Single-symbol commands retain their existing public report. Multi-symbol and
whole-universe commands return a bounded aggregate with contract version,
command, status, universe digest, worker count, total provider attempts, and
deterministically ordered per-symbol safe reports. Coverage and query always
report zero provider attempts.

## Rules

1. Resolve one retained universe snapshot under the invocation knowledge
   cutoff. Its effective interval must cover the complete requested date range.
2. Select by canonical constituent symbol, preserve universe ISIN order, and
   bind the resolved Upstox instrument by both symbol and constituent ISIN.
   A current symbol match with a different ISIN fails closed.
3. Hold one storage-root lease for the invocation. Use one writer per canonical
   file path, serialize schedule/snapshot/catalog/manifest publication, and
   allow provider network waits or verified reads to run concurrently.
4. Bound workers to eight and the selection to 50. Use one account-wide
   thread-safe limiter. The default reserves at most one provider request per
   second, below the documented Upstox standard-API rolling limits. Retry-after
   deferral remains bounded and never waives retry or attempt ceilings. The
   limiter covers the Upstox instrument-catalog, historical-candle, and
   intraday-candle requests.
5. Resume from catalog, manifest, immutable closed-month Parquet, and
   provisional current-month evidence. Closed verified partitions require zero
   provider requests. When the same-date target advances, the open month calls
   only Intraday V3, requires the retained prefix to remain byte-for-byte equal,
   and appends only newly completed minutes. After date rollover it finalizes
   pending prior dates from Historical V3 and appends a new content-addressed
   immutable generation. Older provisional generations remain addressable, and
   immutable closed-month data is never overwritten.
6. Coverage and query are read-only and provider-free. They resolve the same
   point-in-time universe under the same admitted lease before reading stored
   evidence.
7. Aggregate order never depends on thread completion. A mix of success and
   failure is `PARTIAL`; homogeneous rejection, unavailability, cancellation,
   or failure remains distinct. No credential, provider payload, local path, or
   exception text enters public JSON.

## Edge cases and validation

- Reject duplicate, malformed, empty, nonmember, non-`NSE_EQ`, over-50, or
  over-eight-worker requests before provider activity.
- A batch query may request at most 5,000 total rows across its selection and
  aggregate JSON may not exceed 8 MiB. A larger request is rejected; an
  unexpected serialization overflow fails closed without partial output.
- Missing/stale universe evidence is unavailable; ambiguous/corrupt evidence
  fails. A supplied universe file is bounded, no-follow, immutable, and exact
  canonical JSON.
- Root authority loss, malformed nested reports, attempt overflow, and worker
  exceptions fail closed with bounded public results.
- An ongoing session may return available completed minutes with explicit
  incomplete-to-target evidence; it is not falsely promoted to closed-month
  verification.

## Acceptance criteria

- `SBIN`, `RELIANCE`, any explicit admitted list, and all 50 use the same
  Upstox-backed implementation without a symbol constant or second downloader.
- A synthetic 50-member smoke proves no more than eight simultaneous workers,
  stable ISIN order, and bounded aggregate output.
- One/many coverage and query prove zero provider attempts and one retained
  point-in-time universe boundary.
- Fast gates pass during work; before merge Ruff format/lint, strict Pyright on
  production, Vulture, and pytest with branch coverage all pass unchanged.
- Changed production lines and branches meet the workflow coverage floor and
  project-wide branch coverage does not regress.

## Residual boundary

The caller-supplied membership artifact contract remains Plan 05. Automating an
authoritative membership source is separate from candle downloading and cannot
silently substitute the Upstox instrument catalogue for historical index
membership.
