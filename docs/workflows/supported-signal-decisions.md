# Supported signal decisions workflow

[Plan 70](../plans/70-automated-supported-signal-decisions.md) defines the
automated V3 safety and causal-decision contract. It gives a human or an AI
harness the same structured evidence to explain why a stock is a bounded
research candidate, why it is rejected, or why the tool cannot decide safely.
It does not place orders, predict returns, set a target, or assess a portfolio.

## Inputs and provider access

First create and retain one or more `CURRENT_STRUCTURE` observations with
`stock-observations observe`. V3 reads the immutable 64-character handles from
an absolute observation root. `evaluate-v3` needs an earlier and a later
observation for the same possible setup.

The command obtains its bounded current evidence automatically. It uses the
configured provider credentials only at the existing provider boundaries; no
token, API key, raw provider payload, or source file is accepted on the command
line. For each V3 evaluation it makes at most four serial provider reads:

1. one exact NSE-equity Upstox Full Market Quotes V3 read for quote, circuit and
   top-of-book facts. The documented response may contain one through five ordered levels per side; the gate evaluates the best valid bid/ask pair;
2. the bounded BharatStock identity and completed-history reads needed for the
   retained ISIN and latest completed session; and
3. one strict Upstox corporate-actions read for that ISIN.

There is no retry, provider fallback, record write, background monitoring, or
broker action. A missing configured credential, provider refusal, malformed
response, stale evidence, or mismatched identity is an explicit closed result.

## Run the automated safety screen

```bash
signal-decisions check-eligibility-v3 \
  --storage-root /absolute/path/to/observations \
  --observation OBSERVATION_HANDLE \
  --output json
```

The `stock-eligibility@v3` response has an ordered `explanation_ledger`. Every
entry contains only these fields:

```text
rule_id, outcome, reason_code, explanation, evidence_references, derived_measurements
```

The fixed safety rules make the reason concrete:

| Rule | What the ledger explains |
| --- | --- |
| `CANONICAL_NSE_EQUITY_IDENTITY` | Whether the retained observation binds exactly one NSE EQ symbol, ISIN, mapping and structure source. |
| `CURRENT_UPSTOX_QUOTE_BINDING` | Whether the current Upstox instrument token and symbol exactly bind the retained ISIN and effective symbol. |
| `CURRENT_QUOTE_FRESHNESS_AND_INTEGRITY` | Quote timestamp, retrieval time, completed-session alignment and circuit coherence. |
| `LOW_PRICE_AND_CIRCUIT_DISTANCE` | Current price, INR 20 floor, both circuit distances, the 2% threshold, and whether each exact comparison passed. |
| `CURRENT_BOOK_LIQUIDITY` | Best bid/ask, relative spread, positive two-sided quantities, the 2% maximum spread, and the exact comparison outcome. |
| `PROVIDER_OBSERVABLE_HISTORY` | Whether at least 252 valid completed rows end at the retained decision session. |
| `ROLLING_CASH_TURNOVER` | The median `close × volume` across the newest 20 sessions and the INR 10,000,000 threshold. |
| `SUPPORTED_CORPORATE_ACTION_BLACKOUT` | Whether a provider-supported dividend, bonus, split or rights event falls within seven calendar days of the retained session. |

`ELIGIBLE` means every one of those bounded gates passed. `INELIGIBLE` means a
measured safety rule failed, with the failed rule and comparison values in the
ledger. `UNKNOWN` means a required fact could not be trusted; it never means the
stock is cleared. Rows after the first decisive stop are present as
`NOT_EVALUATED`, so the output also states why the tool did not make lower
priority reads.

## Evaluate a causal research candidate

```bash
signal-decisions evaluate-v3 \
  --storage-root /absolute/path/to/observations \
  --previous-observation PREVIOUS_OBSERVATION_HANDLE \
  --current-observation CURRENT_OBSERVATION_HANDLE \
  --output json
```

The `stock-signal-decision@v3` response nests the full safety result and adds a
second explanation ledger for the causal conditions. A result is
`RESEARCH_CANDIDATE` only when all of these facts pass:

1. the automatic V3 safety result is `ELIGIBLE`;
2. the retained pair represents the same upward-BOS event;
3. no later DOWN CHOCH of its specified supporting higher low was observed;
4. the event age is one through five completed sessions;
5. the current completed close is `ABOVE` the original broken high; and
6. the unchanged supporting `SWING_LOW` / `HL` is present and the current bound
   quote is strictly above its structural reference.

The decision ledger records the relevant comparison and the daily-close
invalidation condition for that structural reference. It calls out that
`NO_CONTRADICTION_OBSERVED` only describes the one checked contradiction; it is
not proof of validity, profitability, or future return.

`NO_TRADE` names the proven failed safety or causal condition. For example, it
can report a circuit or turnover failure, an event blackout, a changed or
invalidated setup, a stale candidate age, a completed close at/below the broken
high, or a current quote at/below the structural reference. `UNKNOWN` identifies
missing, revised, non-comparable, stale, malformed, unavailable, or
identity-conflicting evidence. These states give an AI harness enough factual
material to explain a decision without inventing market facts.

## Exit codes and safe output

V3 returns exit code `0` only for `ELIGIBLE` or `RESEARCH_CANDIDATE`. A valid
`INELIGIBLE`, `NO_TRADE`, or `UNKNOWN` result returns `1`. A malformed command
returns `2`, writes only `request_invalid` to standard error, and emits no JSON.
An unavailable selected record or provider boundary returns a fixed redacted V3
envelope and exit code `1`.

Responses include retained observation identities, safe source and result
hashes, separate source/retrieval times, rule explanations and policy comparison
values. They do not include provider headers, credentials, raw JSON, full bars,
storage paths, or exception text. Each V3 JSON response is canonical and capped
at 128 KiB.

## V2 retained compatibility

The earlier commands remain available without changed behavior:

```bash
signal-decisions check-eligibility --storage-root ROOT --observation HANDLE --output json
signal-decisions evaluate --storage-root ROOT --previous-observation OLD --current-observation NEW --output json
```

V2 remains an offline retained-evidence boundary. It returns `UNKNOWN` for
eligibility and `NO_TRADE` for decisions because it has no automated V3 provider
evidence. Use the explicit `-v3` commands when the installed runtime has the
normal provider configuration and an automated current decision is required.

## Policy scope

The V3 policy reuses admitted market structure and price action for its narrow
causal question, completed price-volume history and quote depth for safety, and
existing volume context only as additive evidence. Relative strength, market
regime and industry are not gates in this one-stock policy. Fundamentals, news,
surveillance, broader liquidity patterns, list-wide prioritization, AI narrative
synthesis, paper observation, and read-only hold/exit assessment are later
product slices with their own contracts.
