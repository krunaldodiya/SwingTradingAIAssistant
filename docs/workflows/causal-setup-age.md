# Candidate completed-session age

[Plan51](../plans/51-candidate-completed-session-age.md) reports how many
admitted completed sessions follow one original upward BOS when Plan49 still
represents the event and high anchor unchanged. Count excludes the event
session; it is zero for same-session refresh and exact replay. Weekends and
declared closures contribute no session. Age never establishes validity,
expiry, active status, a holding horizon or trade eligibility.

Use two admitted CURRENT_STRUCTURE V2 observations:

```python
from swing_trading_ai_assistant.research_comparison.setup_age import (
    observe_setup_age_v1,
)

report = observe_setup_age_v1(previous, current)
```

The actual injected CLI is `setup_age_cli.main(argv,
observation_service=service)`. Supply `setup-age --symbol SYMBOL
--storage-root ABSOLUTE_ROOT --previous-selection-time UTC
--current-selection-time UTC --output json`. The existing observation port
supplies exactly two selector-bound observations. No automatic historical
reader, clock, acquisition authority, storage mutation or monitoring is added.

Run the guarded demo from the source checkout with its approved interpreter:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python examples/causal_setup_age_demo.py --scenario same-event
```

The demo labels fixed observations as synthetic and denies network and hidden
directory effects. Other scenarios: replay, unknown, revised-event,
not-represented, outside-window and no-baseline. Synthetic behavior does not
prove market frequency, usefulness or returns.

| Outcome | Count and interpretation |
| --- | --- |
| OBSERVED | Exact 0..20 completed-session count under the current admitted schedule |
| REPLAY | Count0 for an identical admitted baseline observation |
| NO_BASELINE | Null count; previous supported observation had no latest upward BOS |
| REVISED_EVENT | Null count; original event or high anchor changed factual evidence |
| NOT_REPRESENTED | Null count; original locus is absent despite sessions remaining |
| OUTSIDE_WINDOW | Null count; required original sessions left the finite window |
| UNKNOWN | Null count; required Structure is unavailable/insufficient |
| NON_COMPARABLE | Null count; input compatibility, schedule family or ordered overlap failed |

Exit0 OBSERVED/REPLAY/NO_BASELINE; exit1 other evidence outcomes; exit2 terminal
malformed/integrity/interruption with a fixed diagnostic and no partial stdout.
Both full observation hashes and Plan49 status/report identity remain bound.
When counted, original/current endpoints and both schedule identities, source/
release and bound feature knowledge times are exposed. Calendar publication
time is not independently recovered. Release hashes and window identities may
differ after fresh retrieval; the ordered common session interval must agree.
Prices, volumes, bars, bodies, private paths and arbitrary diagnostics stay
excluded. A changed calendar overlap cannot silently produce a count.

Representation and age cannot overturn Plan50 invalidation. Missing/revised/
outside evidence cannot establish disappearance or expiry. Broader signal
generation, eligibility, persistent lifecycle and effectiveness remain open.
