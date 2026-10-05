# Coherent candidate evidence for an external AI

[Plan52](../plans/52-coherent-candidate-evidence.md) obtains exactly one pair of
admitted CURRENT_STRUCTURE observations and returns the delivered continuity,
anchored invalidation and completed-session-age reports bound to that pair.
Each component preserves its own contract, status, reason, identities and limits.

Use `assemble_setup_evidence_v1(previous, current)` from
`swing_trading_ai_assistant.research_comparison.setup_evidence` with typed
producer observations. Copied candidate/component JSON is not admitted evidence.
For the injected CLI, call `setup_evidence_cli.main(argv,
observation_service=service)` with `setup-evidence --symbol SYMBOL
--storage-root ABSOLUTE_ROOT --previous-selection-time UTC
--current-selection-time UTC --output json`. Supply an existing authorized
observation service; this adapter adds no historical reader or provider authority.
It validates selectors before exactly two serial CURRENT_STRUCTURE calls.

Read `continuity`, `invalidation` and `age` separately. In particular, an
`INVALIDATED` candidate can still have an observed age; age cannot reverse that
contradiction. Window loss, absence, revised evidence and unknown never become
validity or expiry. Both full observation identities and component/result/runtime
identities remain bound. A mismatched pair or continuity reference is terminal.

Exit0 reports factual/replay/no-baseline results; exit1 preserves at least one
component's inconclusive outcome; exit2 is malformed, integrity or interruption,
with fixed diagnostics and no partial stdout. Exit0 never establishes an active,
valid, eligible or tradable candidate. The whole canonical JSON bundle is at
most1MiB; no raw bars/prices/volumes/provider bodies/private paths leave it.

The deterministic tool supplies and admits facts, timing and provenance. The
external AI owns contextual recommendation/no-trade reasoning and must not
invent/recompute market facts or override integrity failures. Eligibility and
financial effectiveness remain unassessed. Optional analytical context must not
become hidden mandatory filters without an accepted strategy contract. No broker
orders, generation policy, expiry, persistence or monitoring is added.

A labelled synthetic example exercises the real admitted producer and actual
injected CLI, denying network and protected effects. With the approved environment
and candidate source path selected:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python examples/causal_setup_evidence_demo.py --scenario same-event
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python examples/causal_setup_evidence_demo.py --scenario invalidated
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python examples/causal_setup_evidence_demo.py --scenario unknown
```

The fixed synthetic dates are not current market data. Existing setup-screen,
comparison, continuity, invalidation and age interfaces retain their semantics.
Installed qualification and complete delivery evidence belong to the governing
[Issue258](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/258).
