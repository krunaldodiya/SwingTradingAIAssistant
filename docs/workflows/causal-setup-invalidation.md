# Evidence-based candidate invalidation

[Plan50](../plans/50-evidence-based-candidate-invalidation.md) answers whether
later confirmed structure contradicts one original upward BOS continuation
premise. INVALIDATED requires a later close-confirmed DOWN CHOCH at the same
HL low confirmed before that BOS. A CHOCH at another low is insufficient for
this criterion. The historical upward BOS remains an admitted fact.

Use two admitted CURRENT_STRUCTURE V2 observations:

```python
from swing_trading_ai_assistant.research_comparison.setup_invalidation import (
    observe_setup_invalidation_v1,
)

report = observe_setup_invalidation_v1(previous, current)
```

The injected CLI is `setup_invalidation_cli.main(argv,
observation_service=service)`. Supply `setup-invalidation --symbol SYMBOL
--storage-root ABSOLUTE_ROOT --previous-selection-time UTC
--current-selection-time UTC --output json`. The existing port supplies exactly
two observations; returned selectors must match. No automatic historical
acquisition, evidence backdating, persistence or monitoring is introduced.

Run the guarded source-checkout demo with the approved interpreter and source:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python examples/causal_setup_invalidation_demo.py --scenario invalidated
```

Other scenarios are no-contradiction, wick, equal-close, other-low, revised-low,
revised-event, replay, no-baseline, unknown, not-represented and outside-window.
Dates are explicitly synthetic; network and hidden-directory effects are denied.

| Outcome | Meaning |
| --- | --- |
| INVALIDATED | The fixed original continuation premise has the anchored contradiction witness |
| NO_CONTRADICTION_OBSERVED | That specific witness is absent while required original evidence is retained unchanged |
| REPLAY | Identical admitted baseline observations; no later evidence |
| NO_BASELINE | Previous observation had no latest upward BOS |
| REVISED_EVIDENCE | Original event or supporting low changed factual evidence |
| NOT_REPRESENTED | Original event is absent despite its sessions remaining |
| OUTSIDE_WINDOW | Required original sessions have left the admitted window |
| UNKNOWN | Required evidence or supporting anchor is unavailable/insufficient |
| NON_COMPARABLE | Stock/mapping/basis/profile/time compatibility failed |

Exit 0 covers INVALIDATED, NO_CONTRADICTION_OBSERVED, REPLAY and NO_BASELINE.
Exit 1 covers inconclusive evidence states. Exit 2 is a fixed terminal diagnostic
with no partial JSON. Preserve both observation identities, continuity status,
supporting-low identities and witness. Prices, bars, bodies and private paths
remain excluded. Source-only revision may preserve factual equality.

NO_CONTRADICTION_OBSERVED never means valid, active, eligible or profitable.
Missing evidence, revision and window loss cannot establish contradiction.
Expiry, trade confirmation, persistent lifecycle, recommendation and effectiveness
remain outside this version. Synthetic tests cannot prove market utility.
