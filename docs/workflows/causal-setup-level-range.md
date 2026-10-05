# Latest completed range around the original broken high

[Plan56](../plans/56-latest-completed-level-range.md) answers whether one latest
completed post-event candle's inclusive low/high range contains the unchanged
original broken high. It reuses complete Plan54 typed admission and witnesses.

```python
from swing_trading_ai_assistant.research_comparison.setup_level_range import (
    observe_setup_level_range_v1,
)

report = observe_setup_level_range_v1(previous, current)
```

| Range relation | Exact meaning |
| --- | --- |
| CONTAINS_LEVEL | low <= original high <= high; both equality boundaries included |
| ENTIRELY_ABOVE | latest completed low > original high |
| ENTIRELY_BELOW | latest completed high < original high |
| null | No admitted later same-event range; existing temporal/unknown/revision states preserved |

The injected `setup_level_range_cli.main(argv, observation_service=service)`
accepts `setup-level-range --symbol SYMBOL --storage-root ABSOLUTE_ROOT
--previous-selection-time UTC --current-selection-time UTC --output json`.
Validate request first, then exactly two serial CURRENT_STRUCTURE selector-bound
observations. The supplied port owns acquisition authority. No new provider,
network, credential, model, persistence or automatic retry. Standalone injected
SDK/CLI only; no new global console entrypoint or change to evidence-v2/checker.

OBSERVED/REPLAY/NO_BASELINE/NO_LATER_SESSION exit0;
UNKNOWN/NON_COMPARABLE/OUTSIDE_WINDOW/NOT_REPRESENTED/REVISED_EVENT exit1.
Non-observed range/witness remain null. Invalid request exit2/request_invalid
before calls. Admission/runtime/interruption/serialization failure
exit2/setup_level_range_failed with empty stdout and redacted errors.
Canonical sorted compact JSON+LF <=1MiB, fully prepared before writing.

The versioned report binds both admitted observation identities/full redacted
rows, unchanged Plan54 result identity, continuity identity/status, closed own
and transitive runtime identity, original/represented causal high/event and
latest completed bar witness, plus unsigned result hash. No raw prices/OHLC,
provider bodies, private paths or arbitrary diagnostics are exported.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python examples/causal_setup_level_range_demo.py --scenario contains
```

Guarded fixed synthetic scenarios: contains, above, below, low-equal,
high-equal, replay, unknown. Actual producer, SDK and injected CLI; exact two
calls and byte equality. Installed hosted qualification uses isolated -I
processes, validates module paths beneath installed sys.prefix and checks the
actual canonical outputs, witnesses, identities and privacy. Source and mocked
qualifier checks remain feedback, not installed acceptance.

Daily range inclusion does not prove an exact traded tick, intrabar ordering,
reclaim, successful retest, confirmation, invalidation, eligibility, recommendation
or profit. This is the latest bar only, not first or any-bar contact. Original
anchor must remain unchanged and represented in the finite21-session window;
no newer pivot substitute or stale result. Close relation, age and structural
invalidation remain independent. Existing schemas and source identities stay
unchanged. Source/prior-wheel rollback requires no data migration.
