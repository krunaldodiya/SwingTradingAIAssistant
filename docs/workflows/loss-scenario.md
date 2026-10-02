# Hypothetical single-stock loss scenario

`market-data loss-scenario --input-file /absolute/private/scenario.json`
calculates loss for one caller-declared NSE LONG equity scenario in INR.
The input must be a regular owner-private file (for example mode `0600`), with
no symlink in its path and no hardlink; the limit is 64 KiB. No provider,
credential, research evidence or storage root is needed.

Example input (synthetic assumptions; the identity is not verified):

```json
{
  "schema": "equity-loss-scenario-request@v1",
  "instrument": {"isin": "INE002A01018", "exchange": "NSE", "symbol": "EXAMPLE"},
  "side": "LONG",
  "currency": "INR",
  "bar_frequency": "1d",
  "holding_sessions": 5,
  "entry_price": "100.00",
  "stop_price": "95.00",
  "quantity": 10
}
```

The result contains entry notional `1000.00`, stop proceeds `950.00`, loss per
share `5.00`, and gross scenario loss `50.00`. These amounts use exact integer
paise, independently of the caller's decimal precision or rounding settings.
Prices must be positive strings with exactly two fractional digits, at most
`999999999.99`; the stop must be below the entry. Quantity is a whole number
from 1 to 1,000,000. Holding sessions is an explicit assumption from 2 to 20 daily
sessions, not a recommended holding period or an approved exit policy.
No fields may be omitted or added. Duplicate JSON keys are rejected.

The result explicitly states `CALLER_SUPPLIED_ASSUMPTIONS`, instrument verification
`NOT_PERFORMED`, market evidence `NOT_USED`, risk eligibility `NOT_ASSESSED`, and
costs/slippage `EXCLUDED`. Stop execution is not guaranteed. Actual losses may
exceed the scenario. Fees, taxes and slippage are excluded. Liquidity, events,
gaps, portfolio exposure and trade suitability have not been assessed.
The calculation does not validate a stop, recommend a quantity or authorize a
trade, and does not claim a maximum loss or a current market fact.

The Python SDK exposes `loss_scenario_request_from_json(bytes)` and
`calculate_loss_scenario(request)` from
`swing_trading_ai_assistant.market_data.loss_scenario`. The calculator revalidates
the complete request even when it came from the parser. The result includes the
normalized assumptions, calculation version, request identity, verified runtime
identity and result identity. Identities are lowercase SHA-256 over sorted compact
JSON plus LF; the result identity covers everything except itself.

Success emits one complete canonical JSON document, bounded to 16 KiB, and exits
0. Invalid inputs and runtime failures exit 2, emit a fixed sanitized diagnostic
on stderr, and emit no JSON. Interrupts retain the existing CLI semantics.
Repeated calls with the same input and runtime return identical results and
retain no state. Full Risk Validation policy, verified costs modelling,
automatic stops, position sizing and portfolio assessment remain deferred.

## Include caller-assumed costs with V2

Use `market-data loss-scenario --contract-version v2 --input-file /absolute/private/scenario.json`
to include one aggregate cost assumption for entry and exit of the entire
position. Set the input schema to `equity-loss-scenario-request@v2` and add
the required field `"round_trip_costs": "12.34"` to the example above. All
other fields and validation rules stay the same. The cost is an INR amount,
not a per-share fee, and excludes slippage.

The amount must be a plain string with exactly two fractional digits, from
`0.00` through `999999999.99`. Explicit zero is valid; omission, signs,
whitespace, exponents and leading zeros such as `01.00` are rejected. The
upper limit is a representation bound, not a fee policy; a cost above the
entry notional is allowed. No fee or tax schedule is calculated or verified.

V2 returns schema `equity-loss-scenario@v2` with the original four amounts
plus `assumed_round_trip_costs` and `scenario_loss_including_assumed_costs`.
The example returns gross loss `50.00`, assumed costs `12.34` and total
`62.34`. The total is gross loss plus the supplied aggregate cost, calculated
exactly in integer paise. The complete request, including costs, is retained
in `assumptions` and bound to the request/result identities.

V2 labels costs as `costs_basis=CALLER_SUPPLIED_AGGREGATE` and
`cost_completeness=NOT_VERIFIED`, with `slippage=EXCLUDED`. It omits V1's
combined costs/slippage-excluded label. Costs remain caller assumptions with
unverified completeness and accuracy. Stop execution is not guaranteed and
actual losses may exceed this scenario; no liquidity, event, gap, portfolio
or trade suitability assessment is performed.

The matching SDK functions are `loss_scenario_request_v2_from_json(bytes)`
and `calculate_loss_scenario_v2(request)` in the same module. They revalidate
the complete V2 request, including objects changed after parsing, and report
calculation version `integer-paise-long-loss-with-costs@v2`. The private reader,
64-KiB input bound, 16-KiB canonical output bound, sanitized failures and
effect-free retry behavior apply to both versions. Input validation precedes
runtime verification and calculation.

Omitting `--contract-version` or selecting `v1` preserves the original V1
schema, arithmetic and labels. Select V1 with a V1 request to roll back to the
gross-only calculation; no stored data requires migration. Version selection
never converts a request. Research V6 continues accepting only V1 scenarios
and rejects V2 before research/storage effects. Fee schedules, slippage
calculation and a later research dossier integration remain deferred.
