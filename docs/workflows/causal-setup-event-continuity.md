# Candidate event continuity

[Plan 49](../plans/49-candidate-event-continuity.md) observes whether one prior
latest upward BOS remains represented in a later admitted Structure window.
It can find the old event when the latest-bar screen returns NO_MATCH.
Representation never establishes validity, expiry, invalidation or eligibility.

Use the pure Python API with two admitted CURRENT_STRUCTURE V2 results:

```python
from swing_trading_ai_assistant.research_comparison.setup_event_continuity import (
    observe_setup_event_continuity_v1,
)

report = observe_setup_event_continuity_v1(previous, current)
```

The injected CLI is `setup_event_continuity_cli.main(argv,
observation_service=service)`. Its port is the existing observation service:
one explicit stock, private absolute storage root, previous/current UTC selection
times, and `--output json`. It does not automatically acquire historical data.
Both calls use CURRENT_STRUCTURE and returned times must match their selectors.

Run the provider-free synthetic producer demonstration from a source checkout
with the approved interpreter and that checkout's `src` on PYTHONPATH:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python examples/causal_setup_event_continuity_demo.py --scenario same-event
```

Other scenarios: replay, revised-event, not-represented, unknown, outside-window,
no-baseline. Fixed synthetic dates are printed explicitly; network access and
hidden-directory creation are denied. These are not current market observations.

| Outcome | Meaning |
| --- | --- |
| REPLAY | Identical admitted observations with a prior MATCH |
| SAME_EVENT | Original locus and factual values still represented |
| REVISED_EVENT | Original locus represented with changed factual values |
| NOT_REPRESENTED | Original sessions present but the event is not represented |
| OUTSIDE_WINDOW | Original anchor/confirmation/event sessions no longer all present |
| NO_BASELINE | Previous observation had no latest upward BOS |
| UNKNOWN | Required Structure evidence unavailable/insufficient |
| NON_COMPARABLE | Identity, mapping, basis, profile or temporal incompatibility |

Exit 0 returns factual outcomes; exit 1 returns UNKNOWN, NON_COMPARABLE or
OUTSIDE_WINDOW. Exit 2 returns a fixed diagnostic and no partial JSON on malformed
input, integrity failure or interruption. Preserve both observation identities,
the original candidate and current representation; source-only revision need not
change factual equality. No prices, raw bars, private paths or provider bodies
are exported. NOT_REPRESENTED and OUTSIDE_WINDOW do not establish invalidation.
