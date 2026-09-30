# Stock-versus-reference Relative Strength

Sprint 27 / [Issue #230](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/230),
[Plan 41](plans/41-stock-reference-relative-strength.md). This owner-private,
retained-only CLI and Python boundary describes exact unadjusted price-change
differences. Delivery and release remain subject to the Issue's acceptance gates.

## Run

```bash
market-data relative-strength-current \
  --input-file /absolute/private/relative-strength-request.json \
  --storage-root /absolute/private/retained-root \
  --output json
```

The input must be an absolute, owner-private regular file (for example mode
`0600`), no larger than 64 KiB and neither a symlink nor a hard link. The
storage root must be absolute and private (mode `0700`); its existing ingestion
lease must be free. This command does not read credentials, call a provider,
acquire or repair data, create the root, or write retained evidence. Supply
retained calendar, mapping, raw minutes and corporate-action screening through
the existing authorized ingestion workflow. An absent root returns an explicit
missing-calendar result without creating files.

The closed request has exactly `contract_version`
(`current-relative-strength-request@v1`), `data_selection_time`,
`admission_deadline`, `schedule_identity_sha256`, `reference`, and `members`.
The selection and deadline use UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`. The deadline
must be later, no more than 30 minutes away, and before the next India calendar
date. The schedule digest identifies the exact retained official schedule.
`reference` is one explicit canonical NSE equity; `members` is an ordered list
of 1–49 distinct target equities. Each record has exactly `isin`, `exchange`
(`NSE`), `instrument_type` (`EQUITY`), `segment` (`EQ`), `effective_symbol`,
`valid_from`, and `valid_through`. The dates must include the India selection
date. Reference and targets cannot overlap by ISIN or effective symbol. Unknown
or duplicate JSON keys, unsupported types/instruments, bad intervals and list
bounds are rejected before storage access. Neither reference nor targets imply
an index, Industry or other selection category.

A saved request expires; use a fresh selection and deadline. Never backdate a
request to claim historical knowledge. Keep request and output private under
the existing source-use restrictions.

## Python

```python
from pathlib import Path
from swing_trading_ai_assistant.relative_strength import (
    relative_strength_request_from_json,
    research_current_relative_strength,
)

request = relative_strength_request_from_json(
    Path("/absolute/private/relative-strength-request.json").read_bytes()
)
result = research_current_relative_strength(
    request, Path("/absolute/private/retained-root")
)
```

The SDK also exports `RelativeStrengthRequest` for direct validated construction.
SDK callers own secure request-file reading and private result handling. Its
optional `clock` is a trusted callable returning aware UTC time; normal callers
use the system clock. The CLI enforces the private-file checks above.

## Read the result

The comparison uses the same latest 21 official completed regular sessions for
both instruments, delimiting 20 close-to-close daily intervals. It excludes
partial sessions and rejects special or unequal-duration sessions. Only retained
`UPSTOX / RAW / 1d-derived-from-retained-1m` evidence is supported. Each
instrument independently needs a valid canonical mapping, complete raw-minute
partitions, and a Plan 21 corporate-action screen across the full window.

For positive endpoint closes C0, C20 of a target and R0, R20 of the reference,
each observed `fact` reports reduced signed-integer numerator and positive
denominator pairs for target change `C20/C0 - 1`, reference change
`R20/R0 - 1`, and difference in **percentage points**
`100 × (C20/C0 - R20/R0)`. `relation` is `ABOVE`, `EQUAL`, or `BELOW` from the
exact sign, without rounding tolerance. For example, 100→110 against 200→210
gives `1/10`, `1/20`, `5/1` percentage points and `ABOVE`; this is arithmetic,
not a market observation. An endpoint whose Decimal coefficient exceeds 32
digits or whose exponent falls outside −16 through +16 yields
`PRICE_RANGE_UNSUPPORTED` for that instrument, without partial arithmetic.

The result binds the separate reference, ordered targets, exact producer order
`[reference, *members]`, selected sessions, source and knowledge times, mapping,
partition and screen identities, request/calculation/runtime/result identities,
availability and explicit reasons. Every target remains represented. A missing
reference withholds all comparisons as `REFERENCE_UNAVAILABLE` while retaining
each target's own state and reason; an unavailable target only withholds that
target when the reference is observed. An action anywhere in the window
withholds that instrument. The screen is nonexhaustive provider evidence, not
proof of no action. Raw bars, endpoint prices, provider bodies, credentials,
exception strings and host paths are absent from output.

Exit `0` means every target comparison was observed. Exit `1` means an explicit
nonready result. Exit `2` means malformed input or terminal storage, integrity,
time or internal failure, with no partial JSON. Explicit retry is read-only and
revalidates retained evidence; there is no automatic retry or fallback. This is
current-knowledge unadjusted price context, not total return, an official-index
benchmark, a rank, trade eligibility, a signal or a recommendation. It makes no
historical point-in-time qualification or effectiveness claim.
