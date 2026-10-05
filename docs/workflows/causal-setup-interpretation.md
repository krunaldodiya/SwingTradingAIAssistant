# Checking an external setup interpretation

[Plan53](../plans/53-external-setup-interpretation-contract.md) checks one caller
response against the [Plan52 evidence](causal-setup-evidence.md) regenerated
from two typed CURRENT_STRUCTURE observations. It verifies structured factual
binding. Explanation truth, external authorship, eligibility, actionable
recommendation and effectiveness remain explicitly unassessed.

Use `setup_interpretation_request_v1_from_json(raw)` and
`check_setup_interpretation_v1(previous, current, response)` from
`swing_trading_ai_assistant.research_comparison.setup_interpretation`. The parser
accepts 1–65536 UTF-8 bytes. The direct SDK revalidates the complete response;
copied bundle/component JSON cannot replace typed producer observations.

The response has exactly `schema=external-setup-interpretation-request@v1`,
`evidence_identity_sha256`, `disposition`, `explanation` and `facts`. Disposition
is the caller's `RESEARCH_ONLY` or `NO_TRADE` posture. Explanation is nonblank
caller text of 1–2048 Unicode code points, with no surrogates or controls except
LF/tab. Facts has exactly `continuity`, `invalidation` and `age`; each cites its
exact `result_identity_sha256` and `status`. Age also preserves
`completed_sessions_elapsed`, including null. Every identity/status/count must
equal the regenerated evidence. Duplicate/extra/missing fields and false claims
are terminal. The checker cannot detect unsupported claims in free prose.

For the injected CLI, call `setup_interpretation_cli.main(argv,
observation_service=service)` with:

```text
setup-interpretation --symbol SYMBOL --storage-root ABSOLUTE_ROOT
  --previous-selection-time UTC --current-selection-time UTC
  --interpretation-file ABSOLUTE_PRIVATE_JSON --output json
```

Supply an existing authorized observation service. The adapter validates all
selectors, then reads one owner-private regular file with the existing bounded
no-follow reader. It rejects symlinks, hardlinks, oversized/public/wrong-owner
files and detected mutation before acquisition. Exactly two serial port calls
supply the selected pair. It adds no model/provider or historical reader authority.

Exit0 means factual binding succeeded with no existing inconclusive component;
exit1 means binding succeeded while preserving an inconclusive component.
Caller `NO_TRADE` is not a process failure. Exit2 returns `request_invalid` for
request/file/parse failures or `setup_interpretation_failed` for evidence,
binding, runtime, overflow or interruption failures, with empty stdout. Successful
output intentionally includes the caller explanation as unverified content.
Fixed failure diagnostics never echo caller text, private paths or exceptions.
The complete canonical JSON output is at most 1MiB and retains all Plan52 facts.
Exit0, a digest, continuity or age never grants trade authorization.

The synthetic example uses the real admitted producer, separately executes the
SDK and actual CLI and requires identical canonical output. With the approved
environment and candidate imports selected:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python examples/causal_setup_interpretation_demo.py --scenario no-trade
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python examples/causal_setup_interpretation_demo.py --scenario invalidated
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python examples/causal_setup_interpretation_demo.py --scenario false-claim
```

Other cases are `same-event`, `replay` and `unknown`. These fixed observations and
caller-authored responses are synthetic; no external AI is used or evaluated.
The installed gate runs all six cases with isolated installed imports. Complete
acceptance and delivery receipts belong to
[Issue260](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/260).

A future actionable contract still needs versioned history, identity/mapping,
data quality, completed-bar/price/corporate-action integrity, liquidity/turnover
and event-risk capabilities. This slice adds no thresholds or eligibility rule.
Index selection never substitutes for eligibility; optional analytical context
does not become a mandatory conjunction. Actual AI quality and effectiveness
require their own authorized evidence. Existing interfaces remain unchanged.
