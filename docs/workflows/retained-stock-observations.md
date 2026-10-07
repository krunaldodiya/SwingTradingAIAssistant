# Record, revisit and compare stock research

Plan64 / Issue290. This workflow supplies descriptive facts, not actionable
signals, eligibility, recommendations, performance or capital decisions.

Use the installed `stock-observations` command and an existing owner-private
research root with directory mode700. The existing approved current sources,
calendar, mapping, data bounds and access restrictions apply to observation.
Read and compare acquire no source data and do not alter retained evidence.

## Record current research

```sh
stock-observations observe --symbol PNB \
  --storage-root /absolute/private/research-root \
  --question PRICE_BEHAVIOR --output json
```

For Structure, select `--question CURRENT_STRUCTURE`. `--refresh` asks the
existing producer for a fresh current capture within its existing rules.
It does not change an earlier record or authorize historical acquisition.

The result includes `observation_identity_sha256` only after durable private
record publication. Keep this exact handle and its research output. Selection,
deadline, evidence-known time and completed session are separate meanings.
The command offers no historical-date or clock override.

Exit0 means READY research or a COMPARABLE pair. Exit1 includes insufficient,
unavailable, not-ready or non-comparable evidence; examine the typed status/code.
RECORDED or READ means record handling succeeded, not that its research was
ready. A storage refusal has no usable handle. Exit2 is malformed input with
the sanitized `request_invalid` diagnostic and no source effect.

## Revisit the exact observation

```sh
stock-observations read --storage-root /absolute/private/research-root \
  --observation ORIGINAL_64_HEX_HANDLE --output json
```

Use the returned lowercase64hex handle, not the sample text. The command
rechecks retained mapping and capture revisions and reproduces the original
public research bytes. It preserves their original knowledge and acquisition
times. A later source correction cannot silently replace this selection.
Missing, unsafe, changed or incompatible evidence produces
`UNAVAILABLE/OBSERVATION_RECORD_UNAVAILABLE`; do not refill it with a fresh
request presented as an old observation. Public JSON and a self-declared hash
alone are not admitted records.

## Compare with a later observation

Record a new current observation for the same question/stock after a later
completed market session, then select both handles explicitly:

```sh
stock-observations compare --storage-root /absolute/private/research-root \
  --previous EARLIER_64_HEX_HANDLE --current LATER_64_HEX_HANDLE --output json
```

The envelope names both record handles and contains the existing complete
comparison contract. Require COMPARABLE, canonical stock identity, matching
question/basis and increasing selection/completed-session/evidence-known times.
Two acquisitions for the same completed session are NON_COMPARABLE, even if
the source changed. A missing earlier record is an explicit unavailable
baseline. Neither outcome is an unchanged signal or NO_TRADE decision.

Copy tool-provided fact values, deltas, state and availability. Cite each fact
path and the comparison's result identity. Newly unavailable evidence remains
missing; do not infer its value or recalculate from prices. Both old and new
handles remain independently selectable after a correction.

## Recovery and compatibility

Retry an interrupted record publication only with the same admitted typed
observation; the SDK exact retry is idempotent and never overwrites conflicting
bytes. Re-running observe creates a new acquisition with its actual current
times; it is not a retry of an old observation. Read never recovers or commits
an incomplete object. Do not edit, rename, chmod, link or delete retained files
to bypass a refusal. Keep the original record and evidence for diagnosis.

This first record version requires the admitted current runtime. Unknown or
incompatible old record versions fail closed without migration or mutation.
Existing evidence and older capture readers retain their original contracts.

SDK: `record_stock_observation_v1(root, typed_result)` returns a handle;
`read_stock_observation_v1(root, handle)` returns the re-admitted original V2
result; `compare_stock_observations_v1(root, previous, current)` returns the
existing admitted comparison. Record accepts typed producer evidence only,
not arbitrary JSON. Expected refusal is `StockObservationUnavailableV1`.

Software/synthetic qualification is distinct from actual-source readback and
a real chronological session pair. No whole-workflow or G05/G08 completion
claim follows from installing the command alone. Record actual missing source
or session prerequisites rather than manufacturing an earlier baseline.
