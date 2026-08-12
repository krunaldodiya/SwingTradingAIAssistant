# Plan 06: Current-month incremental equity data

Status: **Implemented by ARK-145; ARK-148 remediation merged and Done.**

Extends [Plan 04](04-public-preview-contract.md) without changing the immutable
closed-month contract.

## Outcome

The same `download`, `coverage`, and `query` commands accept a range ending on
the current `Asia/Kolkata` date. Closed months remain fully verified immutable
partitions. The current month is an immutable sequence of provisional snapshots
identified by an exact completed-minute cutoff. No current-month request is
reported as full-month verified coverage.

Historical V3 remains the source for prior dates. Upstox Intraday V3 supplies
the current date because the authenticated Historical V3 response does not
include the current session. This is an internal provider-routing detail; the
user still invokes one `download` command and all public contracts remain
vendor-neutral.

## Schedule and time boundary

- A canonical schedule-v3 artifact must classify every date from local month
  start through the requested current date.
- The current date must be an explicitly sourced session or closure. Weekends,
  holidays, and special sessions are never inferred by the downloader.
- For an active session, the target is the last fully completed minute. At or
  after the sourced close, the target is the final minute beginning one minute
  before close and `session_complete=true`.
- A range spanning closed and current months supplies a canonical v2 closed-
  month schedule via `--closed-schedule-file` and the v3 current schedule via
  `--schedule-file`. The CLI composes separate preparation services internally.

The August 2026 operator evidence used for the bounded smoke came from NSE
Capital Market circular `NSE/CMTR/71775` and NSE's published equity normal-
market hours of 09:15–15:30 IST. Operator-supplied files remain the evidence;
the program does not scrape or invent a calendar.

## Incremental persistence

The catalog v6 `provisional_partitions` table stores metadata only. New
snapshots are content-addressed by instrument, month, schedule digest, UTC
cutoff, and the retained Parquet checksum. Catalog v6 preserves legacy v4/v5
rows and paths while allowing a corrected Historical V3 generation at the same
schedule and cutoff to coexist with the earlier immutable object. Publication
is atomic, descriptor-relative, no-follow, no-overwrite, and protected by the
existing storage-root lease.

For the first current-month invocation:

1. fetch prior dates once with Historical V3 when required;
2. fetch the current date once with Intraday V3 when a completed minute exists;
3. normalize and validate the union against the exact schedule; and
4. publish one immutable provisional snapshot plus metadata.

For a repeated invocation:

- derive the effective cutoff from the completed current-session minute, or from
  the final scheduled Historical V3 minute when there is no intraday target;
- reuse exact retained evidence with zero candle-provider calls when the request
  ends before today, today is an explicit closure, or the current session has no
  completed bar yet;
- if the target advanced on the same date, call only Intraday V3, require the
  retained prefix to remain byte-for-byte equal, and append only newly completed
  minutes in a new immutable snapshot;
- after the local date rolls over, treat prior-date Intraday V3 rows as awaiting
  finalization, request only the minimal pending Historical V3 date range, and
  publish a new immutable generation whose prior-date rows carry Historical V3
  values and provenance;
- allow corrected OHLCV only for that scheduled prior-date
  `upstox-intraday-v3` to `upstox-historical-v3` transition; require every
  canonical finalized minute to be present with Historical V3 provenance before
  publication; incomplete finalization fails closed as
  `HISTORICAL_FINALIZATION_INCOMPLETE`, while a changed current-date prefix,
  changed already-historical row, or unknown source transition remains rejected;
  and
- count only new timestamps as appended, never overwrite or relabel the earlier
  snapshot, and make the post-finalization repeat zero-provider
  `ALREADY_CURRENT`.

Every provider, row, byte, decoded field, output, retry, lock, and query path
remains bounded. Credentials are read lazily from `UPSTOX_ACCESS_TOKEN` only
after schedule, request, and storage admission requires a provider call.

## Public evidence

`CoverageStateV1.PROVISIONAL` means verified immutable evidence through
`data_cutoff`; it never means full-month completeness. A provisional month
reports the exact cutoff, session-complete flag, row count, checksum, schedule
digest, and instrument-snapshot provenance. Closed-plus-current download
payloads retain the closed month evidence and its snapshot provenance alongside
the current provisional month.

Coverage and one-minute query use zero provider calls. They reopen and verify
the catalog-selected immutable provisional object under the existing root
authority. A read admission never authorizes mutation and does not wait for the
exclusive writer: while a refresh is running, coverage and query return the
last atomically published snapshot. A catalog entry replacement race is retried
at most three times without sleeping; persistent corruption still fails closed.
Queries may combine verified closed months with the provisional current month,
subject to the unchanged 10,000-row public limit.

## Acceptance evidence

- deterministic first, unchanged-repeat, later-cutoff append, conflicting-
  prefix, missing-minute, unsafe-path, catalog, and serializer tests pass;
- zero-intraday-target repeats for a historical request end, explicit closure,
  and pre-first-completed-bar cutoff reuse identical metadata without another
  token, Historical V3, or Intraday V3 call;
- a date-rollover test requests only the pending prior date, accepts a corrected
  prior-date value with Historical V3 provenance in a checksum-distinct object
  even when schedule and cutoff are unchanged, proves the earlier object is
  byte-for-byte unchanged, rejects incomplete finalization without publishing an
  object or catalog row, and makes the next invocation zero-provider
  `ALREADY_CURRENT`;
- a live RELIANCE smoke persisted 2,625 August rows through
  `2026-08-11T09:59:00Z`, with zero missing bars;
- the next identical August request made zero snapshot, historical, and
  intraday requests;
- deterministic concurrent-reader tests return the last published snapshot
  while the refresh writer holds the root lock;
- adding July required one Historical V3 request, retained 8,625 verified July
  rows, reused the August snapshot, and the full-range repeat made zero provider
  requests; and
- coverage reported one `VERIFIED` and one `PROVISIONAL` month with zero
  provider attempts.

The generated market-data root and schedule artifacts are external smoke
evidence and are never committed.
