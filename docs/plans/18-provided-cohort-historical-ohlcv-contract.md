# Provided-cohort historical OHLCV contract

Status: **DEFERRED — historical contract for GitHub Issues #120 and #122; not active Sprint 10 work, implementation, or publication evidence**
Contract revision: `provided-cohort-historical-ohlcv@v1`
Risk: **R3** — financial research-integrity and deterministic historical-contract boundary
Historical relationship: preserves the fixed-cohort replacement for the former
membership/acquisition path. [Plans 12](12-market-regime-contract.md) and
[17](17-market-regime-layer-b-evidence-acquisition.md) remain historical records.

## Deferred decision and scope

Issue #115 is closed/not planned with no published implementation. Its
owner-supplied fixed-cohort concept is deferred to Sprint 15 / Issue #120
(historical OHLCV store) and Sprint 16 / Issue #122 (historical validation and
pre-structure gate). This contract evaluates one supplied cohort of **1 through
50 Nifty 50 equities** using supplied daily OHLCV only. The
`evaluate_provided_universe_ohlcv_v1` runtime boundary is deterministic and
zero-I/O: it performs no provider call, source discovery, credential use,
retention, publication, email, or other external effect.

The cohort is selected by the owner from the intended Nifty 50 scope, but the
contract makes **no** historical index-membership, eligibility, or constituent
claim. It does not reconstruct, validate, infer, or acquire membership history.
A supplied cohort is not a point-in-time index universe.

Every evaluated or insufficient report carries the literal research scope
`FIXED_COHORT_RETROSPECTIVE`. That scope means cohort selection may create
selection or survivorship bias. The report is not, and must never be described
as, an unbiased historical Nifty 50 index strategy backtest.

## Lanes and input boundary

| Lane | Permitted inputs | Required context | Excluded from this contract |
| --- | --- | --- | --- |
| Historical | owner-supplied cohort manifest and daily OHLCV bars | fixed-cohort retrospective limitation, canonical identities, UTC selection/evaluation times, decision session | index membership history, news, events, sectors, fundamentals, macro, dividends, separate corporate-action inputs, provider acquisition |
| Live/current/realtime | price and volume facts | news, events, and sector analysis remain required product evidence | fabrication or backfilling of those contextual feeds from historical inputs |

Live/current/realtime is retained product direction, not implementation scope of
this plan. No historical input may masquerade as live context, and no absent
live feed may be fabricated or treated as neutral.

Historical news, event, and sector inputs are deferred/not-yet-evaluated for
the later validation gate. Their exclusion from this OHLCV-only contract is not
a permanent product removal or a neutral substitute for missing context.

## Canonical inputs

### Cohort manifest

`ProvidedCohortManifestV1` contains an immutable canonical tuple of 1..50
`ProvidedEquityIdentityV1` members and the owner selection instant `selected_at`.
An identity supplies an ISIN, a canonical symbol, or both. When both are present,
they bind the same member; neither may be an empty placeholder. Duplicate
identity, ambiguous ISIN/symbol binding, and conflicting identity assertions
are rejected. The manifest contains no membership interval, sector, weight,
corporate-action, provider, source, or historical eligibility assertion.

`canonical_json_bytes()` serializes compact sorted-key UTF-8 canonical JSON for
contract version, research scope, UTC-`Z` `selected_at`, and member identities
sorted by `(isin, symbol)`. `cohort_identity_sha256` is SHA-256 over those
canonical bytes. Thus semantically identical member input orders yield the same
identity, while a changed member, identity binding, or selection instant changes
it.

`ProvidedUniverseHistoricalRequestV1` supplies that manifest, an explicit UTC
`evaluated_at` knowledge cutoff, a `decision_session`, and one
`ProvidedCohortOhlcvV1` set of bars. `selected_at <= evaluated_at` is required.
Its `canonical_json_bytes()` serializes the full supplied member/bar payload and
its `request_identity_sha256` binds that exact historical request. Neither
instant proves historical eligibility or makes future-known bars admissible.

### Daily OHLCV bars

`DailyOhlcvBarV1` supplies an exact daily session date, bound member identity,
open, high, low, close, volume, known-at instant, and one mandatory
`HistoricalPriceBasisV1.SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED` price basis. This
means OHLC are **split-adjusted and dividend-unadjusted**. A missing, different,
mixed, or ambiguous price basis is rejected. There is no dividend feed,
corporate-action feed, comparability proof, automatic adjustment, or price
reconstruction.

OHLC values must be finite and strictly positive Decimal values, satisfying
`low <= min(open, close) <= max(open, close) <= high`. Volume must be finite,
nonnegative, and integral. Decimal decisions are exact: binary floats, NaN,
infinity, rounding tolerance, and implied coercion are not admitted. A duplicate
member/session bar, inconsistent identity binding, or non-monotonic session
sequence is invalid. A bar known after `evaluated_at` is future-known and must
fail closed rather than be omitted.

## Evaluation contract

`evaluate_provided_universe_ohlcv_v1` evaluates one
`ProvidedUniverseHistoricalRequestV1` as follows:

1. Every supplied member must have the same strictly increasing daily
   session-date grid.
2. The common grid contains at least 21 sessions and ends exactly at
   `decision_session`; no nearest-date, previous-bar, calendar, or imputed
   fallback is allowed.
3. The comparison close is the close at the supplied session exactly 20
   positions before `decision_session`, not 20 calendar days or an inferred
   exchange session.
4. Exact Decimal close comparison yields `ADVANCE`, `DECLINE`, or `UNCHANGED`
   for every cohort member.
5. Counts are over all supplied members only. `BROAD_ADVANCE` applies when
   `advances / cohort_size >= 0.60`; `BROAD_DECLINE` applies when
   `declines / cohort_size >= 0.60`; otherwise the label is
   `MIXED_PARTICIPATION`.

The threshold is inclusive and scales with the supplied cohort, not a fixed
30-member threshold. One member can therefore be broad advance or decline;
50 members require at least 30 directional members. Mutually exclusive
member directions make both broad labels impossible.

## Result and failure behavior

`ProvidedUniverseHistoricalReportV1` contains the contract revision, research
scope, cohort identity, `request_identity_sha256`, selected/evaluated instants,
decision/comparison sessions, cohort size, `HistoricalEvidenceStateV1`,
`HistoricalParticipationLabelV1`, three counts, and `report_identity_sha256`.
Its `canonical_json_bytes()` and SHA-256 bind the complete report projection,
including the exact request identity, excluding only its own identity field.

A valid result has `HistoricalEvidenceStateV1.EVALUATED` and all label/count
fields. On missing, invalid, ambiguous, incompatible, duplicate, unordered,
non-common-grid, too-short, or future-known data, the outcome is
`HistoricalEvidenceStateV1.INSUFFICIENT_EVIDENCE`; label and all three counts
are null. It may contain only bounded diagnostics and input identities needed
to explain the rejection. It must never return partial counts, a best-effort or
previous label, substitute member, inferred bar, or contextual explanation.

Structural construction errors may be stable validation errors before a report
exists. A well-formed domain insufficiency is a full fail-closed report, not an
exception to swallow. Both results preserve `FIXED_COHORT_RETROSPECTIVE` and the
no-unbiased-index-backtest limitation.

## Edge cases

The first implementation must reject or fail closed for zero or 51 members;
duplicate, blank, malformed, conflicting, or ambiguous identities; invalid UTC
instant ordering; bars outside the manifest; missing or duplicate member/date
bars; mixed grids; a grid that does not end at the decision session; fewer than
21 supplied common sessions; invalid OHLC envelopes; invalid volume; a bar known
after `evaluated_at`; missing decision/comparison closes; and decimal coercion,
rounding, or equality tolerance. It must reject a historical request that
introduces membership, sector, news, event, fundamental, macro, dividend,
corporate-action, source, or provider material as if it affected calculation.

## Acceptance

Focused tests must prove canonical cohort order independence and sensitivity to
bound content; exact Decimal equality; inclusive 60% thresholds for 1, 60%, and
50-member cohorts; use of exactly the close 20 supplied sessions earlier; no
partial results for every invalid/missing condition; zero-I/O behavior; and the
fixed-cohort limitation on evaluated and insufficient reports.

## Integration

The runtime is one shared deterministic boundary for CLI, API, or MCP adapters.
An adapter may render a report but may not acquire data, recover invalid input,
recompute the decision, alter canonical identities, or retain an obsolete public
acquisition alias. Live consumers are a separate lane and require their own
current price/volume, news, event, and sector evidence contracts.

Sprint 15 / Issue #120 is the separate data boundary for this evaluator. It
supplies a versioned fixed-cohort historical OHLCV store after the current/live
path is usable. A later download/import path needs its own execution authority
and preserves immutable revisions; it does not give this zero-I/O evaluator
provider authority.

## Capability-aware historical validation

The Sprint 16 / Issue #122 validation gate predeclares every study's
feature/instrument/interval coverage and records one availability-ledger state:
`AVAILABLE`, `NOT_PUBLISHED`, `NOT_RETAINED`, `SOURCE_GAP`, `STALE`,
`CONFLICTED`, or `UNLICENSED`. Each entry also binds the window,
`published_at`, `known_at`, source, revision, and affected identities. A later
or current fact must never substitute for unavailable historical evidence, and
unavailable dates must remain visible rather than be dropped.

Each study declares a profile: `OHLCV_ONLY`, `OHLCV_PLUS_SECTOR`, or
`OHLCV_PLUS_NEWS_EVENTS`. Missing context blocks only a claim requiring that
profile; it never becomes neutral evidence or invalidates an OHLCV-only claim.
When availability cannot be proven, prospective/paper validation from the
immutable archive is required instead of a retrospective claim.

## Explicit non-goals

This plan does not authorize or implement provider selection, enquiries,
credentials, purchase, retrieval, acquisition, persistence, official source
contact, email, public report publication, historical membership reconstruction,
corporate-action/dividend handling, news/event/sector ingestion, fundamentals,
macro inputs, an unbiased index backtest, forecast, recommendation, trade,
broker order, or Market Structure implementation. It creates no claim that
Issue #115 is completed, merged, reviewed, or published.
