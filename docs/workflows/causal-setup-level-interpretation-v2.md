# Coherent level-aware candidate interpretation v2

[Plan55](../plans/55-level-aware-setup-interpretation.md) and
[Issue264](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/264)
define the additive v2 path. Existing v1 evidence, interpretation and level
commands and their output contracts remain supported unchanged.

Use `assemble_setup_evidence_v2(previous, current)` from
`research_comparison.setup_evidence_v2` with two admitted typed CURRENT_STRUCTURE
observations. It returns continuity, structural invalidation, descriptive age
and original broken-high relation for that exact pair. The legacy evidence hash
and unchanged component identities preserve linkage. Missing/revised/replay and
window states remain independent; no aggregate eligibility or active verdict.

The injected `research_comparison.setup_evidence_v2_cli.main` accepts
`setup-evidence-v2 --symbol SYMBOL --storage-root ABSOLUTE_PRIVATE_ROOT
--previous-selection-time UTC --current-selection-time UTC --output json`.
Inject the existing observation port with the caller's own acquisition authority.
This adapter does not install a historical reader, fetch market data or backdate
knowledge. It validates selectors before exactly two serial observations.

The external response uses `external-setup-interpretation-request@v2` with
exact `evidence_identity_sha256`, `disposition`, `explanation`, `facts`.
Disposition is caller RESEARCH_ONLY or NO_TRADE. Continuity and invalidation
claims contain exact result hash and status. Age additionally contains the
exact integer/null completed_sessions_elapsed. Level additionally contains the
exact ABOVE/AT/BELOW/null relation. No omitted/extra claims, coercion or
cross-version bundle substitution. Narrative accuracy and authorship remain
unassessed; caller text is explicitly untrusted content.

Parse using `setup_interpretation_request_v2_from_json` and check using
`check_setup_interpretation_v2` in `research_comparison.setup_interpretation_v2`.
The injected CLI module `setup_interpretation_v2_cli` accepts
`setup-interpretation-v2` with the same selectors and
`--interpretation-file ABSOLUTE_PRIVATE_JSON --output json`. The existing
owner-private/no-follow/single-link regular-file reader enforces the 64KiB bound.
Read/parse before acquisition, then check against one regenerated v2 packet.
Failure emits no partial JSON. Exit2 means malformed/failed binding/integrity or
interruption; exit1 preserves inconclusive component evidence; exit0 means a
successful contract check, never a confirmed trade or truthful narrative.

ABOVE does not confirm validity or eligibility. BELOW does not establish the
independently defined structural invalidation. Neither relation selects the
caller's posture. No external model/provider, expiry/eligibility policy or
broker effect is introduced.

The guarded `examples/causal_setup_level_interpretation_v2_demo.py` supports
above/at/below/invalidated/replay/unknown/no-trade/false-claim. Its real producer
uses fixed synthetic inputs and compares actual evidence and interpretation
CLI outputs with their SDK bytes; it also checks unchanged legacy components.
It does not evaluate an AI model, live markets or strategy effectiveness.
Installed qualification runs the actual SDK and CLI under isolated -I inside
the built environment; mock verifier tests are feedback only. Full hosted gates,
independent exact-byte reviews and normal private delivery remain required.
