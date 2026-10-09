# Supported signal decisions workflow

The current installed workflow is a retained-evidence, fail-closed boundary
defined by [Plan 66](../plans/66-source-bound-supported-decision-repair.md).
It reuses exact Sprint 51 observations, but it does not yet establish stock
eligibility or produce a trade suggestion.

## Before you begin

Create a `CURRENT_STRUCTURE` observation with `stock-observations observe` and
retain its returned observation handle. The commands below require an absolute
storage root and those immutable 64-character handles. They perform no network
request and make no record write.

## Inspect retained eligibility evidence

```bash
signal-decisions check-eligibility \
  --storage-root /absolute/path/to/observations \
  --observation OBSERVATION_HANDLE \
  --output json
```

The command re-admits the selected observation through the Sprint 51 record
reader. It validates the producer-owned canonical mapping, completed official
session window, source-reported OHLCV linkage, positive observed volume, and
producer-known time already covered by that admission chain.

Its `stock-eligibility@v2` result always has status `UNKNOWN`. When retained
structure evidence is available, it lists these four missing source capabilities:

- `LISTING_AND_TRADABILITY_EVIDENCE_UNAVAILABLE`
- `EXECUTION_LIQUIDITY_EVIDENCE_UNAVAILABLE`
- `PRICE_CURRENCY_AND_LOW_PRICE_POLICY_UNAVAILABLE`
- `EVENT_RISK_COVERAGE_UNAVAILABLE`

It reports opaque evidence identities and a session count only; it does not
expose raw bars or numeric prices. `UNKNOWN` is not clearance to trade.

## Derive a retained setup decision

```bash
signal-decisions evaluate \
  --storage-root /absolute/path/to/observations \
  --previous-observation PREVIOUS_OBSERVATION_HANDLE \
  --current-observation CURRENT_OBSERVATION_HANDLE \
  --output json
```

The command re-admits both records and derives existing causal continuity,
invalidation, age, level relation, and range-inclusion facts inside the process.
It returns `stock-signal-decision@v2` with `NO_TRADE` and
`ELIGIBILITY_EVIDENCE_UNAVAILABLE`, even when the retained pair has a matching
setup and an `ABOVE` level relation. The response binds the observation handles
and derived setup-evidence identity without returning an entry, stop, target,
or numeric price.

## Interface and failures

Neither command accepts JSON facts, bars, mapping strings, event notices,
eligibility envelopes, setup states, prices, levels, or caller-supplied known
times. An unknown option such as `--input-json`, a relative root, or a malformed
handle writes `request_invalid` to standard error and exits `2` before a record
is opened. A missing, unavailable, or unadmitted selected record returns the
fixed public `OBSERVATION_RECORD_UNAVAILABLE` envelope and exits `1`.

A valid fail-closed `UNKNOWN` or `NO_TRADE` response also exits `1`. Exit `0`
is not currently emitted because this contract has no eligible or actionable
outcome.

## Analytical-family disposition

| Family | Current use |
| --- | --- |
| Market Structure | Re-admitted from the selected current-structure observation; the pair evaluator derives causal setup facts from it. |
| Price Action | Reused only through the internally derived causal relation and range facts. |
| Volume | Confirms that the retained source window has positive source-reported volumes; it does not establish execution liquidity. |
| Relative Strength | Not used by this boundary. |
| Event Context | Does not establish event-risk coverage. A retained no-match notice cannot clear event risk. |
| Fundamentals and external providers | Excluded. The workflow adds no provider, network request, broker interaction, or fundamental feed. |

G03 and G04 remain open outcome gaps. A later governed slice must introduce
and admit the missing evidence before it can add `ELIGIBLE` or `ACTIONABLE`.
