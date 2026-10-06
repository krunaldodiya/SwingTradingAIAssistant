# Inclusion-aware external research interpretation

Sprint45 / [Plan59](../plans/59-inclusion-aware-setup-interpretation.md) /
[Issue272](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/272).
Delivery and release are pending; the live Issue owns current lifecycle state.

An external consumer can acknowledge six independently descriptive facts from
one exact pair of admitted observations: event continuity, structural
invalidation, completed-session age, latest close relation, latest range
relation, and earliest completed post-event range inclusion in the finite
admitted window. The deterministic tool checks structured claims; it does not
verify the caller's explanation or assess eligibility or effectiveness.

The versioned SDK accepts the same two typed CURRENT_STRUCTURE observations as
the existing v3 and inclusion APIs:

```python
from swing_trading_ai_assistant.research_comparison.setup_evidence_v4 import (
    assemble_setup_evidence_v4,
)
from swing_trading_ai_assistant.research_comparison.setup_interpretation_v4 import (
    check_setup_interpretation_v4,
    setup_interpretation_request_v4_from_json,
)

# previous/current are actual admitted typed observations, not authored JSON.
evidence = assemble_setup_evidence_v4(previous, current)
response = setup_interpretation_request_v4_from_json(caller_response_bytes)
checked = check_setup_interpretation_v4(previous, current, response)
```

Use `setup_evidence_v4_cli.main` with command `setup-evidence-v4`, or
`setup_interpretation_v4_cli.main` with `setup-interpretation-v4`, through the
existing injected observation service. Select one canonical symbol, an absolute
storage root, exact UTC previous/current selection times, and JSON output.
Interpretation also requires `--interpretation-file`: an absolute owner-private,
single-link regular file with no symlink path, containing 1–65536 bytes.
The parser validates it before either observation is acquired. Each command
acquires exactly two serial selector-bound observations; no new provider or
model is invoked by the composition/checking SDK.

The caller's closed `external-setup-interpretation-request@v4` contains exactly
`schema`, `evidence_identity_sha256`, `disposition`, `explanation`, and `facts`.
The first five fact claims retain the v3 shapes. The additional
`level_range_inclusion` claim contains exactly `result_identity_sha256`,
`status`, `inclusion_observed`, and `first_inclusion`. Inclusion is a boolean or
null. First inclusion is null or exactly `session` (a real YYYY-MM-DD date) and
`bar_identity_sha256` (64 lowercase hexadecimal characters). Copy these facts
from the generated evidence; the tool regenerates them from the typed pair and
rejects false, missing, swapped, or substituted claims.

`RESEARCH_ONLY` and `NO_TRADE` are caller postures. Successful checking means
`STRUCTURED_BINDING_ONLY`: explanation accuracy, actionable recommendation,
eligibility and effectiveness remain `NOT_ASSESSED`; authorship is caller
supplied and unauthenticated. Structural invalidation can coexist with range
inclusion. A range spanning the original level does not prove an exact traded
tick, a successful retest, confirmation, lifetime first contact, or a usable
trade. Unknown evidence remains unknown, never a negative inclusion finding.

Success writes one canonical JSON object plus LF after the complete output is
prepared (maximum 1 MiB). Exit0 includes factual replay/no-baseline/no-later
states and grants no trading authority. Exit1 denotes any unchanged upstream
inconclusive state. Request/file/parser failures produce exit2,
`request_invalid`, and no output or acquisition. Later acquisition/admission/
identity/binding/output failures produce exit2 and the fixed diagnostic
`setup_evidence_failed` or `setup_interpretation_failed`, without private data.
Reader interruption uses `setup_interpretation_failed`. Retry is explicit; an
operating-system stdout write is not an atomic publication guarantee.

Run the fixed-date guarded demonstration with the project's approved Python
environment:

```text
python examples/causal_setup_inclusion_interpretation_v4_demo.py --scenario earlier
python examples/causal_setup_inclusion_interpretation_v4_demo.py --scenario none
python examples/causal_setup_inclusion_interpretation_v4_demo.py --scenario no-trade
python examples/causal_setup_inclusion_interpretation_v4_demo.py --scenario false-session
```

These are synthetic August2026 observations, not current market evidence or
performance validation. The demonstration runs the actual producer, original
APIs, new SDK and both injected CLIs under the existing protected-effect guard.
Source qualification isolates its clock and audit state in a fresh process;
installed qualification uses a clean wheel under `-I` and checks the original
nested references. Prior v1/v2/v3 and inclusion contracts remain available.
