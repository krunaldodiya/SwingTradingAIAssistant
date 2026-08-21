# Provider-neutral adjusted daily close contract

Status: **PLANNED / NOT STARTED — GitHub Issue #127; no implementation, provider call, acquisition, retained fact, test, review, merge, or publication evidence exists under this plan**

Contract revision: `provider-neutral-adjusted-daily-close@v1` (planned)

Schema revision: `provider-neutral-adjusted-daily-close-schema@v1` (planned)

Risk: **R3 / High** — financial-research integrity, third-party revised data,
identity continuity, immutable evidence, and a new provider-backed fact boundary.

Outcome owner, acceptance authority, and residual-risk owner: **repository owner
through [GitHub Issue #127](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/127)**.

Depends on: the merged standalone [Plan 21](21-current-supplied-cohort-corporate-action-screen-contract.md)
corporate-action screen and the supplied-cohort identity/current raw-fact boundary
in [Plan 19](19-current-supplied-cohort-market-data-contract.md).

Sequence: Issue #125 / Plan 21 merges first; Issue #127 then implements and merges
this capability; only then may [PR #124](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/124)
rebase and replace its Market Regime v1 proposal with a separately versioned v2
that consumes both capabilities. Sprint 12 remains blocked until Sprint 11 /
[Issue #116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116)
closes through its own exact-revision gates.

## Outcome and boundary decision

Issue #127 plans one deterministic provider-neutral capability for explicit
**adjusted daily close** facts over an exact owner-supplied 1–50 member Nifty 50
equity cohort. The first concrete adapter is yfinance. Upstox remains primary for
current/live raw OHLCV and the retained corporate-action screen. The yfinance
fact is separate evidence; it never changes, fills, rewrites, or is serialized
inside an Upstox raw candle.

The five-line source evaluation is:

1. **Expected value:** adjusted daily closes avoid obvious split/dividend discontinuities in bounded 20-session research and yfinance supplies long-range daily history.
2. **Scope fit:** accepted as the separate adjusted-daily dependency for Sprint 11 Market Regime v2 and for later explicitly selected Nifty 50 daily research; not for live broker facts, authoritative corporate actions, or long-range intraday history.
3. **Material risk:** yfinance is an unofficial Yahoo client for personal/research use; ticker/ISIN mapping, provider revisions, adjustment semantics, licence/terms, and point-in-time replay remain material limits.
4. **Smallest alternative:** retain Upstox raw facts and Plan 21 screening, while adding one separate adjusted-close capability rather than an adjustment engine or a second OHLCV store.
5. **Decision:** **accepted for a separately qualified yfinance-first adjusted-daily adapter; rejected as strict point-in-time historical authority or silent fallback**.

This plan does not approve a general multi-provider framework. One narrow typed
port supports one capability. A later provider is admitted only by a separate
source qualification, contract/policy revision, adapter implementation, and
reviewed evidence; domain calculations do not change merely because another
adapter is added.

## Provider capability routing

| Capability | Selected first provider | Price/evidence basis | Rule |
| --- | --- | --- | --- |
| Current/live completed and partial OHLCV | Upstox | raw provider OHLCV | Primary live/raw fact. Existing candles and archives remain byte- and value-unchanged. |
| Corporate-action screen | Upstox through Plan 21 | retained nonexhaustive provider screen | Required separate report; never authoritative no-break proof. |
| Adjusted daily close | yfinance through this plan | explicit `ADJUSTED` daily close plus exact adapter mode/policy identity | Separate fact and retained object; never injected into raw OHLCV. |
| Angel One | none | unqualified for adjusted close and corporate-action screening | Deferred future adapter only. No implementation, credential, sandbox, or provider call is authorized now. |
| Any fallback | none by default | capability-specific | Selection is explicit before adapter construction and provenance-bound. No generic or silent fallback is permitted. |

A caller selects exactly one admitted provider for this capability. The request,
retained observation, fact, and report all carry the same `provider_id` and
capability/source/schema/policy identities. A provider failure returns one
closed insufficiency. It cannot trigger yfinance, Upstox, Angel One, another
provider, a cached latest object, or raw-price substitution unless a later
contract explicitly authorizes and records that exact route.

## Planned fact contract

The implementation specification must freeze exact field ordering, canonical
bytes, enums, limits, and identities before code. At minimum, the provider-
neutral model must contain the following semantic bindings.

### Owner input and request

`AdjustedDailyCloseInputV1` plans to bind:

- contract and schema revisions;
- exact Plan-19 `cohort_identity_sha256` and 1–50 canonical `(isin, symbol)`
  members;
- `decision_cutoff`, exact `comparison_session`, exact `decision_session`, and
  the retained official schedule evidence/source/release that derives the 21
  completed session positions;
- explicit `provider_id` selected for adjusted daily close;
- `price_basis = ADJUSTED` and the required adapter adjustment-mode policy;
- source, schema, provider-policy, mapping-policy, and code identities; and
- `input_identity_sha256` over the complete canonical projection.

The immutable request must copy those bindings and add only derived request and
runtime identities. It must not accept a provider URL, credential, storage path,
caller-authored receipt, raw Upstox candle, inferred exchange calendar, or
unbound Yahoo ticker.

### Exact identity mapping

The yfinance adapter uses a reviewed retained mapping from each canonical project
identity to exactly one `.NS` ticker. ISIN remains the project identity boundary;
the Yahoo ticker is provider routing metadata, not a replacement identity.
Mapping evidence must bind at least the ISIN, project symbol, exact provider
ticker, effective/observed time, `known_at`, source/revision, mapping-policy
identity, and retained-object identity.

Missing, duplicate, ambiguous, conflicting, future-known, stale, or symbol-
changed mapping is whole-result insufficiency. The adapter must not construct a
`.NS` ticker from an unverified symbol at runtime, search by company name, accept
a best match, or silently reuse a mapping outside its admitted effective and
knowledge-time bounds.

### First adapter: yfinance adjusted daily

The first adapter must explicitly request and verify yfinance's adjusted mode;
it may not rely on a library default. Its reviewed policy must pin the yfinance
package version and exact daily interval, date-bound semantics, timezone/session
normalization, adjustment arguments, action metadata request, timeout/retry/
concurrency limits, row/byte limits, and normalization rules. `interval` is
exactly daily for this capability. A returned value is not admitted merely
because a column is named `Close`.

For the exact retained schedule positions `S[0]..S[20]`, every member must yield
one finite positive canonical Decimal adjusted close per session, with no
missing, duplicate, conflicting, off-session, future-session, or noncanonical
row. The provider observation must preserve enough retained evidence to replay
which returned row supplied each normalized fact. Float-to-Decimal conversion,
if the provider boundary supplies binary values, requires a single frozen
textual conversion and validation rule; no hidden rounding or tolerance is
permitted.

The provider call is bounded and separately authorized. Structural admission,
private-root admission, cohort/mapping admission, and request identity
construction occur before network effects. No credential is required for
accepted yfinance use, and no future provider credential may enter repository,
test, issue, chat, output, log, receipt, or artifact data.

### Retained observation and adjusted-close fact

Each immutable retained yfinance observation must bind:

- provider and adapter release;
- exact provider tickers and project ISIN/member identities;
- request/date bounds, daily interval, explicit adjustment arguments, provider
  timezone/session metadata, and returned action metadata needed to explain the
  adjusted series;
- retrieval start/end, `retrieved_at`, `published_at` when the provider supplies
  it, conservative `known_at`, package/source revision, and response/normalized
  object digests;
- exact source, schema, mapping-policy, adjustment-policy, and code identities;
  and
- whether retained bytes are original provider bytes or an adapter-produced
  canonical observation. The adapter must never call normalized bytes original
  wire bytes when the library does not expose them.

`AdjustedDailyCloseFactV1` then binds one member/session adjusted Decimal close,
`provider_id`, `price_basis = ADJUSTED`, the exact adjustment-mode identity,
provider ticker and project ISIN binding, decision/knowledge timestamps,
retained observation/receipt identity, source/schema/policy/code identities, and
its own fact identity. A complete aggregate report binds every required fact and
its exact selected retained-object set. Public aggregate consumers may receive
opaque identities; raw provider responses, private paths, member diagnostics,
and credentials remain private.

## Temporal and historical integrity

A yfinance adjusted series retrieved now may reflect retrospective provider
corrections or adjustment revisions. Therefore:

- `known_at` cannot precede the actual retained retrieval/observation time;
- a later download cannot be represented as evidence available at an earlier
  historical cutoff;
- current/prospective use requires the retained observation and mapping to be
  admissible by the exact decision/evaluation cutoff defined by the consuming
  contract;
- each later retrieval is a new immutable revision with a new identity; it does
  not overwrite or silently supersede a prior fact;
- disagreement between retained revisions is explicit `CONFLICTED` or a closed
  insufficiency under the frozen policy, never latest-wins without identity;
- retrospective daily history is labelled revised/non-point-in-time and cannot
  support a strict as-published claim; and
- historical/backtest studies use only evidence actually available at their
  declared cutoff. An unavailable feature is recorded as unavailable/not
  applied, never backfilled from later yfinance data, and does not block an
  unrelated claim whose declared study profile does not require it.

The documented yfinance capability supports long daily history. Its intraday
history is limited to the latest 60 days and is outside this daily contract; it
is not a long-history one-minute source. yfinance is an unofficial Yahoo client,
not endorsed by Yahoo, and the planned adapter is limited to unofficial,
personal/research use subject to reviewed Yahoo/yfinance terms. This plan makes
no exchange-authority, finality, completeness, or licensed market-data claim.

Plan 22 changes sequencing, not the historical program's scope. Sprint 15 still
owns the deferred historical store, including point-in-time evidence and
availability ledgers. Sprint 16 still owns capability-aware validation before
Market Structure, including historical backtests; look-ahead, survivorship,
selection, and data-snooping controls; separated in-sample, walk-forward,
out-of-sample, and untouched-test regions; forward/paper testing; realistic
costs and slippage; and point-in-time membership, sector, corporate-action, and
source provenance. Unavailable features remain explicit at each cutoff without
fabrication, later backfill, silent neutralization, or dropped dates, and they do
not block unrelated declared study profiles. Market Structure remains after the
Sprint 16 gate. No initially planned feature is discarded by this current
adjusted-close dependency.

## Failure behavior and discrepancy handling

After structural admission, any missing, stale, ambiguous, corrupt, duplicate,
conflicting, future-known, wrong-session, wrong-provider, wrong-price-basis,
wrong-adjustment-mode, wrong-mapping, unretained, or incompletely bound evidence
returns one whole-result `INSUFFICIENT_EVIDENCE` with no partial adjusted fact
set. Structural input/runtime/private-root violations produce a bounded
sanitized error before a report. Neither path retries through a different
provider or raw value.

Plan 22 does not classify member direction or Market Regime. The later PR #124
v2 integration must consume, for the same cohort, sessions, cutoff, and schedule:

1. a successful Plan-21 corporate-action screen report;
2. a complete Plan-22 adjusted-daily-close report; and
3. the existing immutable Upstox raw close evidence without modifying it.

V2 must calculate raw and adjusted endpoint directions as separate typed
projections. An `OBSERVED` result requires the direction for every member to
agree across the two complete bases after the successful Plan-21 screen. V2
uses the adjusted-direction projection as its one classification basis and
retains the matching raw-direction projection as separately bound corroborating
evidence. Any member disagreement returns whole-result
`INSUFFICIENT_EVIDENCE` with the aggregate closed reason
`RAW_ADJUSTED_DIRECTION_CONFLICT`, null comparison label/counts, and no public
member/value leakage. It must not mix one raw endpoint with one adjusted
endpoint, silently choose whichever produces an observed label, or fall back to
the unscreened PR #124 v1 path.

## Market Structure and raw-candle boundary

This plan supplies adjusted **daily close only**. It cannot supply or authorize
Market Structure OHLC inputs. Existing Upstox raw `open`, `high`, `low`, `close`,
and volume facts remain unchanged, and no yfinance value is inserted into their
candle or archive representation.

A future separately approved Market Structure contract must choose one
consistent basis for the whole calculation: either a complete raw OHLC series or
a complete adjusted OHLC series whose open/high/low/close share one verified
adjustment basis. It must not combine raw highs/lows with adjusted closes or
switch basis inside a window. That later module remains after the Sprint 16 gate
and is not specified or started here.

## Acceptance and delivery sequence

Issue #127 implementation must provide focused positive, boundary, negative,
temporal, provider, and no-leakage evidence for at least:

- exact 1/5/50-member identity and 21-session coverage;
- explicit yfinance daily adjusted-mode invocation and retained receipt;
- `.NS` ticker-to-ISIN mapping, including missing/ambiguous/symbol-change
  failures;
- canonical Decimal conversion, fact/report identities, immutable revisions,
  and exact replay from selected retained objects;
- missing/stale/duplicate/conflicting/future-known rows and mappings;
- provider revision disagreement and retrospective non-PIT labels;
- separate Upstox raw and yfinance adjusted facts with no candle mutation;
- explicit provider selection, wrong-provider rejection, and zero silent
  fallback;
- bounded network/byte/time/retry/concurrency behavior, terms boundary,
  owner-private retention, and sanitized failures; and
- yfinance daily long-range qualification plus explicit rejection of long-range
  intraday use beyond the documented latest-60-day limitation.

Completion additionally requires exact-candidate focused and repository gates,
installed-wheel behavior, independent exact-revision functional,
security/provenance, and temporal/market-integrity review, hosted CI/security,
merge, and owner closeout in Issue #127. This plan records none of those future
results as complete.

The dependency order is fail-closed:

```text
Issue #125 / Plan 21 merged
  -> Issue #127 / Plan 22 implemented, reviewed, and merged
  -> PR #124 rebased to Market Regime v2 consuming both contracts
  -> Issue #116 / Sprint 11 reviewed, merged, and closed
  -> Sprint 12 may start
```

A failure or incomplete gate adds repair work before progression; it does not
permit skipping a dependency or starting Sprint 12.

## Explicit non-goals

Plan 22 does not implement code, add the yfinance dependency, call any provider,
acquire or retain data, change Plan 21, rewrite frozen Plan 12 or PR #124's
historical v1 proposal, implement Market Regime v2, start Sprint 12, adjust or
rewrite Upstox raw OHLCV, build a general adjustment engine, provide adjusted
OHLC candles, implement Market Structure, infer corporate actions from gaps,
implement Angel One, silently fall back across providers, claim strict
point-in-time Yahoo history, support long-range intraday history, publish the
future Issue #126 package, recommend a trade, or place an order.
