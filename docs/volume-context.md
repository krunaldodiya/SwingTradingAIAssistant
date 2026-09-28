# Completed-session Volume context

Sprint 26 / [Issue #226](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/226),
[Plan 39](plans/39-completed-session-volume-context.md). This working branch adds
an owner-private, retained-only CLI and Python interface. Delivery and release
remain subject to the issue's acceptance gates.

## Run

```bash
market-data volume-context-current \
  --input-file /absolute/private/volume-request.json \
  --storage-root /absolute/private/retained-root \
  --output json
```

The request must be a regular owner-private file (for example, mode `0600`),
not a symbolic or hard link, and no larger than 64 KiB. Use an absolute private
root (mode `0700`). A retained root's existing ingestion lock must be available.
The command does not acquire data, read credentials, create or repair the root,
or modify retained evidence. Use the existing authorized ingestion workflow to
supply the calendar, current mapping, raw minute data and corporate-action screen.
A missing or empty root produces a missing-calendar result without creating files.

The closed request contains exactly these fields:

| Field | Value |
| --- | --- |
| `contract_version` | `current-volume-context-request@v1` |
| `data_selection_time` | Current UTC selection instant, formatted `YYYY-MM-DDTHH:MM:SS.ffffffZ` |
| `admission_deadline` | A later UTC instant, at most 30 minutes after selection and before the next India calendar date |
| `schedule_identity_sha256` | SHA-256 identity of the exact retained official schedule |
| `members` | Ordered list of 1–50 canonical NSE equities, with unique ISINs and symbols |

Each member contains exactly `isin`, `exchange` (`NSE`), `instrument_type`
(`EQUITY`), `segment` (`EQ`), `effective_symbol`, `valid_from` and `valid_through`.
The validity dates use `YYYY-MM-DD` and must include the India selection date.
These identity fields match the existing current price-context request. Extra
keys, duplicate JSON keys, unsupported instruments and duplicate members fail.
The supplied list is preserved; missing stocks are not removed or replaced.

A previously saved request's deadline will expire. Select a fresh invocation
time; do not backdate a request to make newer evidence appear historically known.
Keep request and result files private under the existing provider-use restrictions.

## Python

```python
from pathlib import Path
from swing_trading_ai_assistant.volume_analysis import (
    research_current_volume,
    volume_request_from_json,
)

request = volume_request_from_json(
    Path("/absolute/private/volume-request.json").read_bytes()
)
result = research_current_volume(request, Path("/absolute/private/retained-root"))
```

The SDK also exports `VolumeRequest` for callers constructing a validated request.
Its optional `clock` is a trusted callable returning an aware UTC `datetime`;
ordinary callers should use the system-clock default. SDK callers own secure
file reading and result handling. The CLI applies the private-file checks above.

## Read the result

For the latest 21 completed official regular sessions, the first 20 form the
baseline. The final session is excluded from that mean. All sessions must have
the same duration and complete compatible evidence. Special or unequal sessions
are unsupported; partial current sessions are excluded.

The optional per-member `fact` has exact reduced rational fields:

- `baseline_numerator` / `baseline_denominator`: prior-20-session mean volume.
- `relative_numerator` / `relative_denominator`: latest-session volume divided by that mean.
- `relation`: `ABOVE`, `EQUAL` or `BELOW` the baseline.

For example, a mean of 10 and latest volume of 25 produces a baseline of `10/1`,
a ratio of `5/2` and `ABOVE`. This example is arithmetic, not a market observation.
A zero latest volume is valid when the baseline is positive. A zero baseline
returns `ZERO_BASELINE` and no fact; no infinite or neutral ratio is invented.

The response includes the ordered selection, selected sessions, source and
knowledge-time bindings, calculation and runtime identities, result identity,
member availability and limitations. It never includes raw bar series,
private paths, tokens or provider response bodies. Source-reported raw volume is
not adjusted or independently certified. A corporate action in the window
withholds the member; a no-action screen remains nonexhaustive provider evidence.

Exit `0` means every requested fact is observed. Exit `1` means at least one
member is nonready, with explicit reasons. Exit `2` means invalid input or a
terminal integrity, storage or invocation failure, with no partial JSON result.
An interrupted process also emits no partial result. Neither successful execution
nor an above-baseline value establishes stock eligibility, liquidity sufficiency,
a ranking, a trading signal or a recommendation. Agent V1–V4 integration and
Relative Strength are separate work.
