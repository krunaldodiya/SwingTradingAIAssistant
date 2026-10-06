# First range-including completed close

[Plan60](../plans/60-first-inclusion-close.md) governs the additive
`causal-setup-first-inclusion-close@v1` contract. Given exactly two admitted
CURRENT_STRUCTURE observations of the same canonical stock, it preserves
Plan58's earliest completed post-event range-inclusion chronology and compares
that session's final close with the original causally broken high.

OBSERVED carries `first_close_relation` ABOVE, AT or BELOW and the original
`first_inclusion` session/bar identity. NO_INCLUSION means the admitted finite
window was completely evaluated and no such range was found; relation and first
inclusion are null. REPLAY, NO_LATER_SESSION, NO_BASELINE, UNKNOWN,
NON_COMPARABLE, OUTSIDE_WINDOW, NOT_REPRESENTED and REVISED_EVENT retain upstream
meaning with null relation. Missing history is never NO_INCLUSION.

This is a completed-bar description, not evidence of an intrabar reclaim,
successful retest or confirmation. It is independent of current close and
structural invalidation. BELOW does not invalidate the candidate, and ABOVE does
not establish validity, eligibility, advice or trading authorization. There are
no tolerance, expiry or effectiveness rules. The window is finite21 admitted
sessions, not lifetime history. Numerical prices and raw source rows remain
inside the deterministic tool.

SDK: `setup_first_inclusion_close.observe_setup_first_inclusion_close_v1(previous,current)`.
Injected CLI: `setup_first_inclusion_close_cli.main(argv, observation_service=...)`
accepts `setup-first-inclusion-close --symbol SYMBOL --storage-root ABSOLUTE_ROOT
--previous-selection-time UTC --current-selection-time UTC --output json`.
It validates requests before calls and obtains exactly two selector-bound
CURRENT_STRUCTURE observations through the approved supplied port. This path
adds no provider permission or storage acquisition policy.

Exit0 describes supported states including NO_INCLUSION; exit1 signals unknown,
noncomparable, outside/not-represented/revised evidence. Exit2 returns no JSON
and only `request_invalid` or `setup_first_inclusion_close_failed`.
Complete canonical sorted compact JSON plus LF is prepared before stdout,
bounded to1MiB, with runtime, observation, original-inclusion and own identities.
No operating-system stdout transaction is promised.

Guarded fixed-date synthetic example:

```text
python examples/causal_setup_first_inclusion_close_demo.py --scenario first-below
python examples/causal_setup_first_inclusion_close_demo.py --scenario first-at
python examples/causal_setup_first_inclusion_close_demo.py --scenario earlier
python examples/causal_setup_first_inclusion_close_demo.py --scenario none
```

The first three preserve latest ABOVE while distinguishing the earlier close.
Protected effects are denied; clocks restored; original references regenerated
from the same typed pair. Synthetic checks prove the bounded contract, not real
provider availability, market frequency or profitable execution. Source-only
feedback does not replace actual installed-wheel/private OCI release gates.
