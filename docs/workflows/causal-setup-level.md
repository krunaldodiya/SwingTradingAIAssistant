# Latest completed close versus the original broken high

[Plan54](../plans/54-candidate-broken-level-relation.md) adds one optional,
descriptive fact: ABOVE, AT or BELOW the high broken by the original upward BOS.
The exact original event and high must remain unchanged and causally represented
in the current admitted 21-session Structure window. A newer high does not
replace the original. The latest completed close is compared exactly, without
a tolerance, arithmetic, rounding or retest policy.

Use two admitted CURRENT_STRUCTURE V2 observations:

```python
from swing_trading_ai_assistant.research_comparison.setup_level import (
    observe_setup_level_v1,
)

report = observe_setup_level_v1(previous, current)
```

The injected command is `setup_level_cli.main(argv,
observation_service=service)`. Supply `setup-level --symbol SYMBOL
--storage-root ABSOLUTE_ROOT --previous-selection-time UTC
--current-selection-time UTC --output json`. Request validation precedes exactly
two serial selector-bound observation calls. Acquisition authority belongs to
the supplied port; this module adds no provider, network, model, store or retry.

| Status | Meaning and command exit |
| --- | --- |
| OBSERVED | A strictly later completed close is ABOVE/AT/BELOW the original high; exit0 |
| NO_LATER_SESSION | Same-event source refresh, no completed session after the original event; null relation/witness; exit0 |
| REPLAY | Identical admitted observation; null relation/witness; exit0 |
| NO_BASELINE | Previous supported observation has no candidate; null relation/witness; exit0 |
| UNKNOWN | Required Structure unavailable; null relation/witness; exit1 |
| NON_COMPARABLE | Stock, mapping, price/source basis or temporal compatibility fails; null relation/witness; exit1 |
| OUTSIDE_WINDOW | Required original locus left the admitted finite window; null relation/witness; exit1 |
| NOT_REPRESENTED | Original event absent while its sessions remain; null relation/witness; exit1 |
| REVISED_EVENT | Original event/high evidence changed; null relation/witness; exit1 |

Malformed requests return exit2/request_invalid before any calls. Complete
producer, runtime, packet/source/bar/anchor integrity, interrupted calls or
output overflow return exit2/setup_level_failed with empty stdout. Whole sorted
compact JSON plus LF is prepared before writing, at most 1MiB. Repeat/concurrent
SDK calls preserve inputs and produce the same bytes.

The report binds both complete redacted observation rows and identities,
continuity status/identity and the new runtime closure. Its witness identifies
the original and represented event/high, their causal sessions, and the latest
completed source bar. Raw bars, prices, volumes, private paths, provider bodies
and arbitrary diagnostics stay internal to the deterministic tool.

Run the guarded fixed synthetic examples with the approved source interpreter:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python examples/causal_setup_level_demo.py --scenario above
```

Scenarios: above, at, below, replay, unknown. The real producer supplies typed
observations; the fixture asserts actual SDK/CLI byte equality and exact selected
pair calls. The installed distribution gate runs all five in isolated `-I`
processes and requires imports under the installed environment. Local fixture and
mocked verifier checks are feedback; genuine installed acceptance is hosted.

ABOVE does not establish validity, confirmation, eligibility, effectiveness or
trade authorization. BELOW does not establish Plan50 structural invalidation.
A below-level close and independently observed structural invalidation may
coexist. Latest detection NO_MATCH does not erase the admitted original high.
Plans47–53 retain their public schemas and meanings; this new fact is not added
to their closed evidence/interpretation v1 schemas. No overall signal-phase
completion or market usefulness/frequency claim follows from synthetic proof.
Ordinary source/prior-wheel rollback needs no migration or persistent repair.
