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
retain no state. Removing this additive command leaves existing stores and
V1–V5 research commands usable. Full Risk Validation policy, costs modelling,
automatic stops, position sizing and portfolio assessment remain deferred.
