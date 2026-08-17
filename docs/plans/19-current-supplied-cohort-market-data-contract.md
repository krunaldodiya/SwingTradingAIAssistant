# Current supplied-cohort market-data contract

Status: **LOCAL IMPLEMENTATION — exact-revision review and publication pending for GitHub Issue #121**
Contract revision: `current-supplied-cohort-market-data@v1`
Risk: **R3** — current market-data integrity, provider effects, and research boundary

## Outcome and scope

Sprint 10 makes the existing `market-data` tool usable for current/live swing
research over an explicit owner-supplied cohort of **1–50 Nifty 50 equities**.
It returns bounded current price/volume facts. The cohort is owner intent: this
contract makes no historical membership, constituent, or eligibility assertion
and performs no historical membership reconstruction.

This is current/live foundation work. Historical/backtest work, including
fixed-cohort OHLCV storage and validation, is deferred to Issues #120/#122.
Historical news, event, and sector inputs are deferred/not-yet-evaluated—not
permanently removed or silently treated as neutral.

## Canonical cohort admission

`CurrentSuppliedCohortManifestV1` has contract version, UTC `selected_at`, a
canonical tuple of 1–50 unique supplied Nifty 50 equity identities, and
`cohort_identity_sha256`. Canonical bytes are compact sorted-key UTF-8 JSON with
one trailing newline; the SHA-256 projection excludes only its own identity.
Identities are normalized and sorted deterministically. Blank, malformed,
duplicate, conflicting, ambiguous, or out-of-cohort identities fail closed.

The existing `market-data` boundary resolves every cohort member through a
retained instrument identity. A missing, duplicate, ambiguous, stale, or
unbound mapping is whole-cohort insufficiency, not a reason to omit, substitute,
or fall back to a current index list.

The supplied manifest is never its own Nifty 50 admission authority. Under the
same retained-root read lease used for identity resolution and market-data
queries, every supplied `(isin, symbol)` must also occur in the cutoff-eligible
retained Nifty 50 universe snapshot. A missing, corrupt, ambiguous, stale, or
nonmatching snapshot fails the whole cohort closed before any provider effect.

## Request and bounded provider boundary

`CurrentCohortMarketDataRequestV1` binds the canonical cohort, invocation
cutoff, requested current-session mode, source policy/schema identity, and
`request_identity_sha256`. Provider-backed calls occur only after this admission
succeeds. They retain existing credential ownership, rate-limit, attempt,
concurrency, byte, duration, cancellation, protected-storage, and sanitized-error
controls. A new provider/source needs the required five-line evaluation and
separate execution authority; this plan neither adopts one nor grants authority.

One bounded request returns, for every admitted member:

1. the latest **completed** daily OHLCV fact with source receipt/provenance,
   freshness, knowledge timestamp, and bar state; and
2. only when explicitly requested and available, a current-session partial
   price/volume snapshot with `PARTIAL_CURRENT_SESSION` state and its knowledge
   timestamp.

A partial snapshot is current swing-research context only. It must never be
represented as a completed daily bar, substituted for a close, or consumed as a
historical close. Daily facts and partial snapshots remain distinct typed states.

## Result and failure behavior

`CurrentCohortMarketDataReportV1` binds cohort identity, invocation cutoff,
request identity, source receipts/provenance, freshness, bar state, code/schema
identity, and report identity. It emits deterministic market facts only.

When every required member has admissible evidence, it returns the complete
cohort result. Missing required evidence, invalid provenance/freshness, invalid
identity resolution, request-bound violation, or provider failure returns
whole-cohort insufficiency with bounded reasons. It must not return partial
cohort counts, silently downgrade a failure, invent a market fact, or expose
credentials/private raw data in errors.

## Acceptance and integration

Focused checks must prove canonical order-independent cohort SHA binding;
rejection of malformed/duplicate/ambiguous/stale/out-of-cohort resolution;
bounded request admission before any provider effect; latest-completed daily
versus explicit partial-current-session state; no partial-as-close conversion;
whole-cohort insufficiency; and receipt/freshness/code/schema/report identity
binding. They must prove the tool does not calculate Market Regime, sectors,
news/events, trade signals, recommendations, entries/exits, position size, or
orders.

The shared boundary is consumed by Sprint 11 current Market Regime, then current
Sector Analysis, current news/events, and the Sprint 14 integrated current
packet. The external AI may reason over that future packet and return
explainable research or `NO_TRADE`; it may not cause the deterministic tool to
invent a signal or order. Historical Plan 18 remains deferred and is not a
Sprint 10 dependency.

## Explicit non-goals

This plan does not implement or authorize historical/backtest storage or
validation, historical index membership reconstruction, historical news/event/
sector backfill, a new provider/source, a provider call before admission,
autonomous trade signals, recommendations, financial advice, broker orders,
Market Structure, Price Action, Liquidity/SMC, or a claim that Issue #121 is
implemented, reviewed, merged, or published.

## Executable types and invariants

All object encodings are closed: unknown keys, duplicate JSON keys, wrong types,
invalid nullability, noncanonical decimal text, and malformed timestamps are
structural rejection. `UtcInstant` is
`YYYY-MM-DDTHH:MM:SS.ffffffZ`; `Sha256` is 64 lowercase hex characters;
`LocalDate` is a real `YYYY-MM-DD`; and all canonical bytes are UTF-8 JSON with
sorted keys, compact separators, `allow_nan=false`, and one trailing newline.
Each SHA-256 field hashes the stated projection excluding only that field.

| Type | Required fields | Invariants |
| --- | --- | --- |
| `CurrentCohortMemberV1` | `isin: Isin`, `symbol: CanonicalSymbol` | Both identities are required and retained identity resolution must bind them to exactly one `NSE_EQ` / `NSE` / `EQ` instrument. |
| `CurrentSuppliedCohortManifestV1` | `contract_version`, `selected_at`, `members`, `cohort_identity_sha256` | Version is `current-supplied-cohort-market-data@v1`; 1..50 unique members sorted by `(isin, symbol)`; hash covers version, selection instant, and canonical member tuple. |
| `CurrentCohortMarketDataRequestV1` | `contract_version`, `cohort`, `invocation_cutoff`, `include_partial_current_session`, `source_policy_identity_sha256`, `schema_identity_sha256`, `request_identity_sha256` | `invocation_cutoff` is UTC; boolean partial mode is explicit; request hash covers every prior field by value, including the full cohort manifest. |
| `CompletedDailyOhlcvFactV1` | `member`, `session`, `open`, `high`, `low`, `close`, `volume`, `data_cutoff`, `published_at`, `known_at`, `source_receipt_sha256`, `freshness_state` | Session is the latest completed session at/before cutoff; `data_cutoff` is its last market-bar timestamp, never a knowledge time; `published_at` and `known_at` remain separate retained-evidence times. OHLC are finite positive Decimals with `low <= min(open, close) <= max(open, close) <= high`; volume is a nonnegative integer; it is never a partial session. |
| `PartialCurrentSessionSnapshotV1` | `member`, `session`, `observed_price`, `observed_volume`, `last_bar_at`, `published_at`, `known_at`, `source_receipt_sha256`, `bar_state` | `bar_state = PARTIAL_CURRENT_SESSION`; `last_bar_at` is the observed market-bar timestamp and is distinct from `known_at`; price is finite positive Decimal; volume is nonnegative integer; it has no daily OHLC close semantics and cannot populate `CompletedDailyOhlcvFactV1`. |
| `CurrentCohortMemberFactV1` | `member`, `completed_daily`, `partial_current_session` | `completed_daily` is required only in a complete report; partial is non-null only when requested and available. |
| `CurrentCohortMarketDataReportV1` | `contract_version`, `cohort_identity_sha256`, `request_identity_sha256`, `invocation_cutoff`, `evidence_state`, `members`, `reasons`, `code_identity`, `schema_identity_sha256`, `report_identity_sha256` | Report SHA covers all preceding content; complete means every supplied member has one fact; insufficiency has `members = null` and no partial member list. |

```text
CurrentEvidenceStateV1 = Literal["COMPLETE", "INSUFFICIENT_EVIDENCE"]
CurrentBarStateV1 = Literal["COMPLETED_DAILY", "PARTIAL_CURRENT_SESSION"]
CurrentFreshnessStateV1 = Literal["FRESH", "STALE", "UNKNOWN"]
CurrentCohortReasonV1 = Literal[
  "COHORT_INVALID", "IDENTITY_UNRESOLVED", "IDENTITY_AMBIGUOUS",
  "IDENTITY_STALE", "OUT_OF_COHORT", "DAILY_BAR_MISSING",
  "DAILY_BAR_INVALID", "SOURCE_RECEIPT_MISSING", "FRESHNESS_STALE",
  "REQUEST_BOUND_EXCEEDED", "PROVIDER_UNAVAILABLE", "CANCELLED"
]
```

`COMPLETE` requires an empty reason tuple, exactly one
`CompletedDailyOhlcvFactV1` for every supplied member, and no unresolved
identity. `INSUFFICIENT_EVIDENCE` requires `members = null`, one or more unique
closed reasons in declaration order, and no counts or partial result. An
unrequested or unavailable partial snapshot does not itself make an otherwise
complete daily result insufficient; only a missing required completed daily fact
does.

`code_identity` verifies every Python module in the bounded `market_data`
implementation package against the review-generated source inventory before
digesting the observed hashes, including retained universe, identity, query,
archive, and CLI dependencies. Loaded modules must resolve to their exact
reviewed source path through the source loader. Additional package directories,
extensions, or other import-shadow entries fail closed. A missing, replaced,
non-regular, hard-linked, oversized, unreadable, or digest-mismatched source
also fails closed. The generated inventory does not list itself recursively,
but its exact source bytes are included in the final identity.

## Retained query, aggregation, and supplied-cohort download integration

The exact existing read port is the retained `market_data` daily query boundary:
after cohort admission and retained instrument resolution, the service queries
the retained current market-data root for each member's daily facts and selects
the latest **completed** session at or before `invocation_cutoff`. It does not
derive a completed bar from a current partial snapshot, infer a session, use a
future-known row, or read raw candles across the public boundary.

`data_cutoff` is the last market-bar timestamp, never a publication or knowledge
timestamp. Provisional evidence carries that value in
`PublicCoverageMonthV1`; verified evidence derives it from the selected retained
row. The service resolves verified-manifest `updated_at` under the same retained
root lease for verified `published_at` and `known_at`, while provisional facts
use their immutable metadata `published_at`. Those timestamps remain distinct
in facts, report identities, and freshness decisions.

The verified evidence lookup is internal to this boundary. The frozen public v1
coverage/query/download month contract remains byte- and value-compatible:
provisional-only timing fields remain null for verified public months and no
serializer keys or public invariants change.

The only optional effect path is a supplied-cohort integration over the existing
`market_data` download/ingestion port. It is invoked only after the complete
cohort/request admission and a separately in-force execution authorization have
been validated. It receives the bounded canonical member set, daily interval,
cutoff, protected root, and existing provider controls; then the service rereads
through the retained query port above. Absence of that authorization, an
unavailable provider, or insufficient post-download evidence yields the report's
whole-cohort insufficiency. This contract grants no provider authority and does
not add a provider or source.

Freshness is explicit: a completed daily fact is `FRESH` only when its source
receipt and `known_at` are at/before the invocation cutoff and the source policy
accepts its age for that cutoff. `STALE` and `UNKNOWN` cannot be silently
promoted. Partial snapshots are admitted only with `known_at <= invocation_cutoff`
and preserve their separate `PARTIAL_CURRENT_SESSION` state.

## CLI file schema and exit behavior

The new public adapter is one command, not an alias for historical evaluation:

```text
market-data cohort-current \
  --cohort-file <absolute-json-file> \
  --storage-root <absolute-owner-private-root> \
  --cutoff <UtcInstant> \
  [--include-partial-current-session] \
  --output json
```

`--cohort-file` is closed JSON at most 64 KiB:

```json
{
  "contract_version": "current-supplied-cohort-market-data@v1",
  "selected_at": "2026-08-17T00:00:00.000000Z",
  "members": [
    {"isin": "INE002A01018", "symbol": "RELIANCE"}
  ]
}
```

The adapter computes, rather than trusts a caller-supplied, cohort identity.
It rejects relative, unreadable, oversized, duplicate-key, or noncanonical
input before retained-root access or provider effect. The storage root must
already exist. Every path component is opened without following links; the
owner-private mode and exact directory identity are pinned across the
invocation. An exclusive lock on the directory itself prevents a replaced lock
filename from creating a second writer. A missing root, linked component,
identity change, permission change, or competing writer fails closed.
The command emits one canonical JSON report on stdout and no report fragments. Exit `0` means
`COMPLETE`; exit `1` means `INSUFFICIENT_EVIDENCE`; exit `2` means structural
request/CLI rejection before a report. Sanitized diagnostics go to stderr only
for exit `2`; credentials, raw provider payloads, and private paths never do.

## Immutable archive and temporal availability

Every admitted live/current fact is immutably archived from now. Its archive
record binds feature, instrument identity, interval, observation/session scope,
`published_at`, `known_at`, source identity/receipt, revision identity, affected
identities, canonical payload identity, and retention location. A later source
revision creates a new immutable record and never rewrites the previously known
fact. The archive is required evidence for later historical validation; a
current or later fact can never substitute for an earlier unavailable fact.

Archive directories must remain owner-private and bound to their canonical
retained-root directory entry throughout publication. Content-addressed objects
are owner-owned read-only regular files with one link; replay revalidates their
path identity, metadata stability, and bytes. A symlink, hard link, replaced
entry, detached directory, unsafe mode, or unstable read fails publication
closed, so `COMPLETE` is never returned without the canonical immutable object.

`HistoricalAvailabilityStateV1` is closed:

```text
Literal[
  "AVAILABLE", "NOT_PUBLISHED", "NOT_RETAINED", "SOURCE_GAP",
  "STALE", "CONFLICTED", "UNLICENSED"
]
```

`FeatureAvailabilityLedgerEntryV1` has `feature`, `instrument_identity`,
`interval`, `window_from`, `window_through`, `availability_state`,
`published_at`, `known_at`, `source_identity`, `revision_identity_sha256`, and
`affected_identity_sha256`. `AVAILABLE` requires immutable admissible archive
evidence for the precise feature/instrument/interval window. Every other state
is a bounded observed limitation; it must not be remapped to `AVAILABLE`, a
current fact, a later revision, or neutral context. Coverage/windows are
predeclared before a study and unavailable dates remain in the ledger rather
than being dropped.

Historical study profiles are explicit and versioned:

```text
HistoricalStudyProfileV1 = Literal[
  "OHLCV_ONLY", "OHLCV_PLUS_SECTOR", "OHLCV_PLUS_NEWS_EVENTS"
]
```

Missing sector/news/event context blocks only claims that require the selected
profile. It cannot invalidate an `OHLCV_ONLY` claim or be silently treated as a
neutral sector/news/event fact. When required historical availability cannot be
proven, the applicable validation is prospective/paper observation from this
immutable archive, not a substituted retrospective claim.

## Five-line evaluation

1. Expected value: archive current facts now so later claims have temporal
   availability evidence rather than hindsight reconstruction.
2. Scope fit: bounded supplied-cohort current price/volume facts and their
   provenance fit the existing `market-data` responsibility.
3. Material data/research risk: later revisions, missing retention, stale or
   conflicting facts could manufacture historical availability or neutral context.
4. Smallest alternative: retain one immutable fact/ledger record per admitted
   feature/instrument/interval instead of reconstructing unavailable history.
5. Decision: **accepted** — require immutable archive and the closed
   availability ledger, subject to separate provider/source execution authority.
