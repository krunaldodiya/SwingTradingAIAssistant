# Data Foundation and Agent-Tool Boundary

Date: 2026-08-04
Status: superseded in part; current boundary recorded on 2026-08-07

## Context

The project was reframed from a conventional Python trading script into a
research tool that any AI-agent harness can consume for Nifty 50 equity swing
trading. We also examined prior trading repositories, ExpiryTrack, its existing
DuckDB market data, and current Upstox historical-data capabilities.

## Accepted direction

- The product is a deterministic, agent-agnostic research tool. AI harnesses own
  contextual reasoning; this repository owns trustworthy market facts,
  validation, evidence, freshness, and provenance.
- The v1 universe, downloader, persisted datasets, and research pipeline remain
  point-in-time Nifty 50 equities. Non-equity ingestion is not part of the
  current platform or roadmap.
- The accepted replacement for the earlier ExpiryTrack ownership idea is an
  installable equity data package in this repository with configurable shared
  storage. ExpiryTrack remains read-only reference material.
- Existing trading repositories are references for concepts and lessons, not
  sources for copy-pasted implementation.
- Missing or weak evidence and `NO_TRADE` are valid outcomes, not failures that
  an AI should fill with speculation.

These decisions are reflected in `docs/architecture-freeze-v1.md` and
`docs/plans/01-data-foundation-and-upstox-ingestion.md`.

## Durable research findings

- ExpiryTrack's existing DuckDB contains index and derivative reference data but
  no Nifty 50 constituent equity candles; it is not an approved current data
  source for this tool.
- Its legacy schema is derivative-specific and represents spot instruments using
  fake expiry metadata. Equities need a separate generalized schema.
- Upstox Historical Candle Data V3 documents one-minute equity history from
  January 2022, requested in monthly windows for 1–15 minute intervals.
- Raw one-minute bars should remain immutable. Higher timeframes should be
  derived with NSE-session-aware aggregation and explicit corporate-action
  adjustment versions.
- Current instrument lists cannot establish historical Nifty 50 membership.
  Point-in-time membership is required to avoid survivorship bias.

## Proposed ideas

- Use ISIN as the canonical equity identity while preserving provider instrument
  keys and symbol history.
- Store ingestion runs, expected-versus-actual coverage, trading sessions, data
  quality issues, corporate actions, and adjustment factors alongside raw bars.
- Expose typed data and research operations to agents rather than arbitrary SQL.
- Keep API, CLI, and MCP as adapters around the same versioned application
  contracts; choose the first transport only after those contracts are stable.

## Open questions

- Which authoritative source will provide point-in-time Nifty 50 membership and
  corporate actions?
- What equity entitlements and historical limits apply to the configured Upstox
  account?
- Does Upstox apply any undocumented price adjustments, or must all adjustment
  logic be maintained locally?
- Should long-term research access use read-only DuckDB, immutable Parquet
  snapshots, or a dedicated data service once concurrent ingestion begins?

## Scope correction: data first

Status: Accepted

The first workstream contains only the market-data tool. It proves RELIANCE
one-minute acquisition, storage, validation, resumability, and querying before
expanding to the point-in-time Nifty 50 equity universe. Shared internals remain
extensible where the equity implementation proves an abstraction, but index,
derivative, forex, crypto, and other adapters are not approved. Market regime,
strategies, backtesting, and agent integration remain deferred until the equity
data package is complete.

ExpiryTrack's existing database is not an equity source because it has no
constituent-stock candles. The accepted data design is a clean installable equity
market-data package in this repository, with immutable monthly Parquet partitions
as the canonical candle store and DuckDB as the catalog and query engine.
ExpiryTrack remains a read-only reference, not a scheduled NIFTY/India VIX
source.

Performance, scalability, and maintainability are accepted release gates. The
pipeline must use bounded concurrency and memory, immutable instrument-month
partitions, vectorized columnar processing, and DuckDB predicate pushdown. Its
provider, normalization, validation, storage, and orchestration layers must
remain independently testable. Concrete performance budgets will be frozen from
the measured RELIANCE vertical-slice baseline rather than guessed in advance.

## Historical next step

Status: **completed and superseded by the current Linear execution order**

The credential-safe RELIANCE capability probe was the next step at the time of
this note. It is complete; current work must be selected from Linear and the
active sprint rather than this historical section.

## Milestone 0 implementation record

Status: Completed

The probe keeps credentials, provider HTTP, instrument resolution, response
normalization, schema validation, and CLI orchestration as separate testable
boundaries. It resolves the caller-supplied segment and symbol through the
Upstox master catalog, calls Historical Candle V3, validates the seven-field
candle shape in memory, and emits only status, row count, first/last timestamp,
and a schema-valid flag. It contains no candle-storage dependency or write path.

ExpiryTrack commit `e937fedc42465df72932818ef4d2c1481f755965` informed the
review of HTTP lifecycle, throttling, and response-shape risks. No implementation
was copied. Its older active-instrument route and SQLite credential design were
rejected for this probe in favor of the documented V3 route. The initially built
macOS Keychain provider was subsequently removed by the accepted portable
credential decision below.

The public Upstox NSE BOD catalog was successfully fetched and RELIANCE resolved
to ISIN `INE002A01018`. The later credential-safe live gate used an ignored
local `.env` token and returned 375 valid one-minute candles for 2026-08-03.
The probe emitted only its bounded diagnostic summary; neither the token nor
candle payload was printed or persisted.

## Portable credentials and master-symbol resolution correction

Status: accepted; supersedes the application-level Keychain design

Runtime credentials must come only from environment configuration loaded from
an ignored `.env` file. macOS Keychain is an optional manual convenience for a
developer or agent retrieving credentials during local work; it is not an
application integration. This keeps the downloader portable across macOS,
Linux, Windows, containers, and CI. `.env.example` documents variable names but
contains no credential values.

Production code must also contain no fixed equity symbol, ISIN, or provider
instrument key. A caller supplies an instrument selector and the provider
adapter resolves it from the current or retained Upstox master instrument file.
RELIANCE remains only the first test/validation fixture, not application
configuration.

## Milestone 0 hardening record

Status: Accepted

The capability probe's provider boundary must cap both successful and error
response bodies, cap gzip catalog expansion, prevent bearer-token forwarding on
cross-origin redirects, and preserve only response headers needed for retry and
correlation. Environment credential failures are bounded, deterministic, and
redacted. A successful response with no candles is not evidence that the actual
candle schema or entitlement works.

### ARK-16 catalog response budget

Status: accepted

The public NSE instrument catalog uses a dedicated 4 MB compressed-response
budget in the production CLI, while historical success and error responses
retain their 1 MB budget. A direct public fetch on 2026-08-04 measured 1,934,668
compressed bytes and resolved RELIANCE (`NSE_EQ|INE002A01018`); the 4 MB cap
therefore provides a little over 2 MB of headroom without loosening the
authenticated historical limit. The separate gzip-expansion cap remains 50 MB.
This is a bounded transport concern only and does not alter provider headers,
credentials, date validation, or response decoding.

### ARK-29 oversized authenticated response sanitization

Status: accepted after independent security review

The bounded transport now returns a non-raising sentinel from request/body-read
frames when a success or HTTP-error response exceeds its configured byte limit.
Only after bearer-bearing request objects and adapter token references are
released does the public boundary raise a sanitized `HttpResponseBodyTooLarge`.
Fake-bearer regressions cover both response paths through the full historical
client and assert that captured traceback locals, transitive objects, cause, and
context retain no authorization dictionary, urllib request/error, or access
token. The 4 MB compressed catalog, 50 MB decompressed catalog, and 1 MB
historical limits are unchanged.

The provider model can represent explicit identity metadata without requiring
the shared transport and provenance layers to encode one symbol convention.
That technical capability does not authorize non-equity ingestion or research.
The current downloader, persisted datasets, validation, and decision-support
scope remain point-in-time Nifty 50 equities. See
`docs/architecture-freeze-v1.md` and
`docs/plans/01-data-foundation-and-upstox-ingestion.md`.

## Long-lived read-only authentication option

Status: accepted after a live capability probe

Upstox now documents an Analytics Token intended for read-only research and
data pipelines. It is generated once in the Developer Apps Analytics tab, is
valid for one year, and supports Historical Data and other market-data GET APIs
without a static IP. This is a closer security and operational fit for the
data-only downloader than automating the standard customer login with a stored
TOTP seed.

The standard OAuth flow should remain available as a fallback, but Upstox
explicitly keeps customer login on its own site and exposes no public endpoint
for applications to submit customer credentials directly. TOTP may improve the
interactive login experience, but it is not an official headless-login API.
Browser automation that stores a TOTP seed would therefore be brittle, would
expand the credential attack surface, and should not be part of production
code.

The live RELIANCE probe accepted the Analytics Token and returned 375 valid
one-minute candles for 2026-08-03. Runtime configuration remains the portable
`UPSTOX_ACCESS_TOKEN` environment variable, so the application does not need to
distinguish a standard daily OAuth token from an Analytics Token. The local
development token is stored in ignored `.env`; an optional Keychain copy is an
out-of-band developer convenience and is not read by production code.

The first urllib request returned HTTP 403 even though the same token, URL, and
headers succeeded through another HTTP client. A controlled live comparison
isolated the difference to Python urllib's default user agent. ARK-30 added a
stable application user agent at the shared transport boundary; the subsequent
production probe returned HTTP 200 with a valid schema.

Official references:

- <https://upstox.com/developer/api-documentation/analytics-token/>
- <https://upstox.com/developer/api-documentation/authentication/>
- <https://upstox.com/developer/api-documentation/access-token-request/>

## ExpiryTrack NIFTY and India VIX migration opportunity

Status: **superseded as an active roadmap item on 2026-08-07; retained as a
read-only reference audit**

The equity-only downloader-v1 boundary supersedes the proposed migration. Do not
ingest these index or derivative records in the current roadmap. A future
instrument module would require a new architecture decision, specification,
point-in-time data and risk contracts, and independent validation. The remaining
details preserve what was observed in the reference database; they are not an
implementation instruction.

A read-only audit of ExpiryTrack's `market_data.duckdb` on 2026-08-04 found a
24 GB physical database with 168,481,043 rows in one canonical `market_data`
table. The table has a primary key on `(expired_instrument_key, ts)` and exposes
3m, 5m, 15m, 30m, 1h, and 1d timeframes as views rather than duplicate stored
tables.

The requested reusable subset is approximately 129,042,075 one-minute rows:

- NIFTY spot: 167,376 rows;
- NIFTY futures: 479,169 rows;
- NIFTY calls: 62,916,160 rows;
- NIFTY puts: 65,311,622 rows; and
- India VIX spot: 167,748 rows.

Observed coverage begins on 2024-07-12 for NIFTY options, 2024-08-02 for NIFTY
futures, and 2024-08-13 for NIFTY spot and India VIX. NIFTY derivatives extend
through 2026-07-28; spot and India VIX extend through 2026-07-31. These ranges
must be treated as observed source coverage, not an unverified claim of complete
exchange history.

If a future approved module reopens this evidence, it should not copy the candles
into a second row-oriented DuckDB table. Any migration design would need to open
the source read-only, normalize its legacy schema under an approved
instrument-specific contract, validate bounded partitions, and preserve
immutable files, manifests, checksums, lineage, quality findings, and observed
coverage.

BANKNIFTY and SENSEX source downloads were observed as incomplete. Any future
approved migration would still need to verify instrument identity, OHLC
envelopes, session timestamps, expected coverage, volume and OI semantics,
partition-level row reconciliation, and idempotent restart behavior before the
source database could be considered imported.
