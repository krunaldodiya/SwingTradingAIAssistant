# Earliest completed post-event range inclusion

[Plan58](../plans/58-completed-level-range-inclusion.md) answers whether any
completed post-event bar in the current fully admitted window included the
original broken high, and identifies the earliest such completed session.

```python
from swing_trading_ai_assistant.research_comparison.setup_level_range_inclusion import (
    observe_setup_level_range_inclusion_v1,
)

report = observe_setup_level_range_inclusion_v1(previous, current)
```

Pass two existing typed CURRENT_STRUCTURE observations. The deterministic tool
admits both complete producer packets, sources, facts, runtime identities and
causal anchors through unchanged Plan56/54/49. A caller-authored report cannot
substitute for that evidence. Inclusive comparison is `low <= original_high <= high`,
with exact admitted Decimals. The event bar is excluded; every later completed
bar in the current21-session window is evaluated in order.

| Fields | Meaning |
| --- | --- |
| inclusion_observed=true | At least one evaluated completed range contains the original high |
| inclusion_observed=false | None of the fully admitted post-event ranges contains it |
| evaluated_post_event_bars | Ordered completed sessions and admitted bar hashes; no OHLC values |
| first_inclusion | Earliest included session/hash pair, or null when none |
| null factual fields | Existing replay/no-later/no-baseline/unknown/noncomparable/missing/revised state; no inferred negative finding |

The injected `setup_level_range_inclusion_cli.main(argv, observation_service=service)`
accepts `setup-level-range-inclusion --symbol SYMBOL --storage-root ABSOLUTE_ROOT
--previous-selection-time UTC --current-selection-time UTC --output json`.
It validates requests before effects, calls the supplied authorized port exactly
twice serially with CURRENT_STRUCTURE and exact selectors, computes once and
prepares complete canonical sorted compact JSON+LF, at most1MiB, before output.
The supplied port owns its acquisition authority. No automatic retry or new
provider/network/model/credentials/store is introduced. This is a usable injected
SDK/CLI, without a new global console entrypoint.

OBSERVED/REPLAY/NO_BASELINE/NO_LATER_SESSION exit0. Unknown/noncomparable/outside/
not-represented/revised exit1. Malformed request exits2/request_invalid with
zero calls and empty stdout. Integrity/runtime/interruption/serialization/bounds
failure exits2/setup_level_range_inclusion_failed with empty stdout and redacted
diagnostics. Exit0 grants no trade authorization. Preparing bytes before output
does not promise atomic OS stdout writes.

The closed report retains complete redacted previous/current rows and original
Plan54 witness, observation and continuity identities, independent original
Plan56 result reference, own closed SDK/CLI plus transitive runtime identity,
fixed limitations and unsigned result hash. No raw bars/prices/private paths,
provider bodies or arbitrary diagnostic text are exported.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python examples/causal_setup_level_range_inclusion_demo.py --scenario earlier
```

The guarded demo uses fixed August2026 synthetic observations and the actual
producer, SDK and injected CLI with exact selectors/byte equality. Scenarios:
earlier, none, latest, multiple, low-equal, high-equal, nearest-above,
nearest-below, event-only, invalidated, replay, unknown and refresh. Protected
effects are denied before producer execution. The strict installed qualifier
runs those cases with -I, validates installed runtime prefixes, regenerates
original Plan54/56 references independently from the same typed pair and closes
every nested row/witness/hash/fact. Source/mocked checks are feedback; actual
installed/nativeOCI/rollback qualification remains a hosted release gate.

The earliest completed session is only within this currently admitted finite
window and current knowledge. It is not first lifetime contact, an intrabar
time, exact traded tick, successful retest, reclaim, confirmation, eligibility
or effectiveness. Missing/revised anchors do not become a negative result.
Structural invalidation, age, close and latest range remain independent; an
included range can coexist with INVALIDATED. Existing evidence/interpretation
versions remain unchanged. No tolerance/expiry/history store/persistence/
monitoring/trading policy; ordinary source/prior-wheel rollback, no migration.
