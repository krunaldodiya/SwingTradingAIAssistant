# Compare two admitted setup observations

Sprint 34 / [Issue 248](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/248)
implements [Plan 48](../plans/48-candidate-observation-comparison.md).

The SDK accepts exactly two producer-admitted V2 CURRENT_STRUCTURE observations:

```python
from swing_trading_ai_assistant.research_comparison.setup_observation_comparison import (
    compare_setup_observations_v1,
)

report = compare_setup_observations_v1(previous, current)
```

An unchanged observation is REPLAY. A later observation with the same event and
anchor facts is SAME_EVENT even when provenance hashes change. The same event
location with changed admitted factual values is REVISED_EVENT. A distinct
location is DIFFERENT_EVENT. APPEARED, ABSENT and NO_MATCH describe observed
matches only. UNKNOWN means required evidence is missing; NON_COMPARABLE means
stock, source, mapping meaning, basis or time ordering cannot support comparison.
REPLAY preserves each original detection status, including UNKNOWN.

The CLI adapter takes a caller-owned observation service and two explicit UTC
selectors. It does not read arbitrary exported JSON, install a production
historical reader or authorize providers. Call
`setup_observation_comparison_cli.main(argv, observation_service=service)` with:

```text
setup-compare --symbol PNB --storage-root /absolute/owner/private/root
  --previous-selection-time 2026-08-26T04:15:00.000000Z
  --current-selection-time 2026-08-26T04:16:00.000000Z --output json
```

Selectors must describe genuinely admitted observations at those times. Fetching
current data and labelling it historically known is forbidden. Equal selectors
are useful for exact replay; different observations at equal selectors return
NON_COMPARABLE. Existing public setup/comparison APIs retain their versions.

Run the guarded demonstration with the approved environment and this checkout's
source path when that environment's editable installation points elsewhere:

```sh
PYTHONPATH=src /path/to/approved/environment/bin/python examples/causal_setup_comparison_demo.py --scenario same-event
```

Other scenarios: `replay`, `absent`, `unknown`. The example states its fixed
synthetic clock and prohibits network and hidden-directory creation. Synthetic
proof does not establish live availability or market effectiveness.

The report retains both observation identities and projected event/source/time
evidence. It publishes no numerical prices, bars, source bodies, paths or private
diagnostics. It does not establish validity, expiry, invalidation, correction
publisher lineage, a persistent active signal, a new trading opportunity,
eligibility, recommendation or effectiveness. The full eight-row signal/research
baseline remains in Plan 47; risk/capital/money management/position sizing follow
the owner-dispositioned signal/research work.
