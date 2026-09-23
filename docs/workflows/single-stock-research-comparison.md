# Compare two admitted stock observations

Issue: #204. Contract frozen and amended on 2026-09-22.

The deterministic tool compares exactly two in-process admitted
`current-stock-research@v2` observations. The assistant explains only the
comparison facts. It does not calculate changes from raw OHLC.

## Try the fixed synthetic workflow

From the repository's locked development environment, give the local coding
assistant this request:

> Read docs/workflows/single-stock-research-comparison.md. Run the complete and
> newly-unavailable synthetic comparisons. Explain the tool-supplied changes,
> cite the comparison result identity and exact fact paths, and state the
> simulation dates, stock identity, completed sessions, price basis and
> limitations. Do not recompute a delta or turn the comparison into a trade plan.

```sh
uv run python examples/single_stock_research_comparison_demo.py
uv run python examples/single_stock_research_comparison_demo.py \
  --scenario newly-unavailable
uv run python examples/single_stock_research_comparison_demo.py \
  --question CURRENT_STRUCTURE
```

The wrapper labels fixed synthetic PNB observations on stderr. It invokes the
bounded in-process comparison CLI adapter with an explicit observation port.
Injected calendar, mapping and price adapters create both observations through
the real V2 admission, calculation and serialization path. A process-wide Python audit
hook denies the socket family. No credential, provider request, owner file or
private capture is used. The control is for this trusted Python demo; it is not
an operating-system sandbox for native code or inherited connected descriptors.

Exit 0 means the two observations are comparable. Exit 1 carries a typed
non-comparable result, including a redacted `OBSERVATION_INVALID` result when an
observation is interrupted. Exit 2 is reserved for malformed CLI input and
supplies no JSON to explain. The complete PRICE_BEHAVIOR result has nine closed fact paths;
CURRENT_STRUCTURE has two. A result never exports raw bars, pivots or events.

## Consume the comparison safely

1. Establish provenance from the observed command execution. A copied JSON
   document and its self-declared hash do not prove admission. The demonstration
   compares objects minted and validated in the same process; it does not accept
   serialized observations as trusted input.
2. Require `contract_version=current-stock-observation-comparison@v1`, status,
   code, runtime/schema/configuration identities and
   `result_identity_sha256`. Stop on `NON_COMPARABLE`; report its code without
   inventing a partial comparison.
3. State `isin`, `exchange`, `symbol`, `price_basis`, both selection times,
   both completed sessions and both evidence-known times. The previous values
   are an explicitly selected observation, not the previous-close feature.
4. Cite `facts[i].path` and `result_identity_sha256` for every change. Copy
   `previous_value`, `current_value` and the tool's `delta`; do not derive a
   number from prices. Report the exact state: `UNCHANGED`, `CHANGED`,
   `NEWLY_AVAILABLE`, `NEWLY_UNAVAILABLE` or `UNAVAILABLE_IN_BOTH`.
5. Preserve each fact's previous/current availability and reason. Newly missing
   evidence is not an unchanged or neutral market fact. `READY` in an input
   observation and `COMPARABLE` here remain research readiness, never trade
   eligibility or a recommendation.
6. Use three parts: **supplied changes**, **interpretation**, **limitations**.
   Interpretation may explain a supplied relation in plain language; it may not
   add another fact, recommendation, entry, exit, position size or score.

The observed synthetic response is recorded in
[single-stock-research-comparison-observation.md](single-stock-research-comparison-observation.md).
It is one qualitative assistant observation, not a universal model evaluation.

## Production retained-history command deferred

Issue #204 does not install `market-data research-compare`. The existing
`market-data` entry point and delivered V1/V2 runtime identities remain
unchanged. The in-process CLI adapter requires an explicit admitted-observation
port and is exercised by the fixed synthetic demonstration above.

The unchanged V2 service acquires calendar evidence before it consults retained
mapping and price evidence, so it cannot safely retrieve two historical
observations using caller-selected clocks. Adding a production retained-history
command therefore requires a separately authorized retained-observation
reconstruction or archive capability. This slice does not add that capability,
alter the V2 acquisition boundary, or imply that disabled refresh is an offline
guarantee.

Adapter inputs are exactly two canonical UTC selection times, one symbol, one
absolute root and one of PRICE_BEHAVIOR or CURRENT_STRUCTURE. Both admitted observations
must have the current runtime, the same canonical stock/question/price basis,
strictly increasing selection, completed-session and evidence-known times, and
evidence known by its own deadline. Invalid observation, missing packet,
incompatible contract/question/stock/basis or invalid time order fails closed.
There is no observation file ingestion, archive/replay service, combined
question, watchlist comparison, new provider or new analytical fact.
