# Corporate-Action Provenance Contract

Status: implemented by ARK-143; date-only visibility remediated by ARK-147.

## Purpose and source decision

Retain immutable point-in-time corporate-action observations for Nifty 50
equities without rewriting canonical raw candles or inventing adjusted prices.
The selected v1 source is the authenticated Upstox Fundamentals corporate-
actions endpoint keyed by ISIN. It documents dividends, bonus issues, stock
splits, and rights issues. It does not document a revision identifier, response
as-of timestamp, historical symbol-change feed, or adjusted-price series.

Every bounded response is therefore retained as a new observation with the
local retrieval timestamp and exact canonical digest. Older observations remain
addressable. Symbol-change authority, adjusted OHLC, and adjustment formulas are
explicitly unsupported rather than inferred from candle or instrument data.

## Canonical evidence

- An observation identifies one Indian-equity ISIN, source
  `upstox-fundamentals-v2`, versioned adapter release, UTC retrieval time, and at
  most 1,000 events in at most 1 MiB of canonical UTF-8 JSON.
- Each event is one of `DIVIDEND`, `BONUS`, `SPLIT`, or `RIGHTS`; carries a
  deterministic event digest, announcement date, effective/ex date, optional
  record date, and either an exact positive decimal INR amount or a bounded
  positive integer ratio as applicable.
- Unknown event/detail labels, malformed dates, duplicate event identities,
  noncanonical JSON, duplicate keys, excessive nesting, and non-finite numbers
  fail closed. Provider wording is not exposed as a market fact.
- Canonical `announced_at` remains the start of the provider's announcement
  date in Asia/Kolkata so schema, canonical bytes, and existing event/snapshot
  digests remain compatible. Because the provider supplies a date without a
  publication time, the event becomes visible only at 00:00 Asia/Kolkata on the
  next calendar day; that instant is inclusive and the prior microsecond is
  hidden.
- Observation retrieval and event visibility are independent cutoffs. An event
  is returned only when `retrieved_at <= knowledge_cutoff` and its conservative
  next-day visibility instant is also at or before the cutoff.

## Retention and resolution

Canonical objects are immutable, content-addressed, owner-only `0400` files
under a private `0700` storage root. DuckDB catalog v5 stores metadata only.
Publication is descriptor-relative, no-follow, no-clobber, fsynced, bounded,
and verified before and during catalog commit.

Resolution selects the latest observation with `retrieved_at <= cutoff` for
the exact ISIN. No observation is `MISSING`; observations only after the cutoff
are `STALE`; different digests at the same latest timestamp are `AMBIGUOUS`;
unsafe bytes or metadata are `CORRUPT`. Revisions remain reproducible because
the selected digest and source release are returned.

## Adjustment boundary

The public Python result always declares `price_state=raw`,
`adjusted_state=unsupported`, `symbol_change_state=unsupported`, and
`calculation_version=null`. Corporate-action evidence state and visible events
are returned separately. Evidence availability does not imply that adjusted
prices or authoritative historical symbol changes exist. No event in this slice
changes a Parquet candle, partition checksum, OHLCV value, query row, or
manifest.

## Bounds and acceptance

One request, 1 MiB response, 1,000 events, 64-level JSON nesting, one immutable
object, and a targeted two-row catalog query are hard bounds. Executable checks
cover Upstox parsing, token non-leakage, split/bonus/dividend/rights validation,
cutoff no-look-ahead, date-only announcement visibility at the inclusive
next-day 00:00 Asia/Kolkata boundary (with the prior microsecond hidden),
independent retrieval cutoffs, retained revisions, missing/stale/ambiguous/corrupt
states, raw immutability, unsupported adjustment, v4-to-v5 migration, and
deterministic replay. Publication is blocked unless the exact candidate
evidences every behavior above and preserves schema compatibility.
