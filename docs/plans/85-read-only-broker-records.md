# Plan 85: read-only broker records and a broker-neutral contract

Status: accepted bounded specification under [Issue #443](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/443). Owner and risk owner: Krunal Dodiya. Risk tier: R4 — broker credentials, private account data, multi-account isolation, and live read-only provider surfaces. Base: `649ceec56f3e846a2b8493cdd083916a7bdfd606` (`main`, 2026-11-24).

## Authority and supersession

The owner directed on 2026-11-25 that the tool expose **holdings, positions, orders, trades, and GTT rules** through one read-only structure that can support more than one broker. This extends the read-only boundary of [Plan 84](84-live-broker-portfolio-accounts.md) beyond its original holdings-only slice.

Plan 84 remains authoritative for account registration, credential binding, identity checks, and the holdings performance review. Its non-goals for order execution and stored portfolio snapshots remain unchanged. This Plan supersedes only its holdings-only connector scope and its deferred positions/orders item. No order placement, modification, cancellation, position conversion, GTT mutation, or execution surface is authorized.

## Outcome

- One broker-neutral record contract describes holdings, positions, order-book rows, trade-book rows, and GTT rules.
- A `BrokerConnector` protocol and adapter registry isolate broker-specific credentials, login, identity, capabilities, and payload parsing.
- Angel One implements every section through documented read-only SmartAPI endpoints.
- `portfolio holdings|positions|orders|trades|gtt|snapshot` returns JSON and table output; no file is written.
- `portfolio review` keeps its existing holdings summary contract.

## First working slice and later work

First slice:

- common record types and section envelopes;
- Angel One adapter for all five sections;
- CLI read commands and snapshot;
- focused parsing, failure, pagination, CLI, and read-only boundary tests;
- documentation and a live owner-authorized smoke.

Later work, not authorized here:

- Upstox, Kite, or Fyers adapters;
- historical records, persistence, reconciliation, or tax reporting;
- position-level analytics, F&O research, or portfolio advice;
- order/GTT mutation or execution.

## Broker-neutral contract

### Sections

`Section` is a closed enum: `holdings`, `positions`, `orders`, `trades`, `gtt`.

A connector declares the sections it supports. A section request outside the connector's capabilities fails with `SECTION_UNSUPPORTED`; a snapshot records that section as `UNSUPPORTED` and continues.

### Common record fields

All records use canonical NSE-style `symbol` text, `exchange`, and optional provider `symbol_token` and `isin`. Money and quantities are decimal values; JSON emits numbers with at most two decimal places. Nullable fields are explicit. Provider-specific status and timestamp strings are preserved, not reinterpreted as a cross-broker state machine.

Holding records add optional `exchange`, `symbol_token`, and `isin` to the existing holding row. The existing invested/current/P&L/day arithmetic and review contract are unchanged.

Position record:

- `symbol`, `exchange`, `symbol_token`, `product_type`, `instrument_type`
- `quantity` (signed net quantity), `average_price`, `last_price`
- `pnl`, `pnl_pct`, `realised_pnl`, `unrealised_pnl`, `multiplier`
- `pnl_source`: `BROKER`, `DERIVED`, or null
- `reported_at` (provider text, optional)

Order record:

- `order_id`, `exchange_order_id`, `parent_order_id`
- `symbol`, `exchange`, `symbol_token`
- `side` (`BUY` or `SELL`), `order_type`, `product_type`, `variety`
- `status` (provider-reported, uppercased), `status_message` (optional, bounded)
- `quantity`, `filled_quantity`, `pending_quantity`
- `price`, `trigger_price`, `average_fill_price`
- `validity`, `reported_at`

Trade record:

- `trade_id`, `order_id`
- `symbol`, `exchange`, `symbol_token`
- `side`, `product_type`
- `quantity`, `price`, `trade_value`
- `reported_at`

GTT record:

- `rule_id`
- `symbol`, `exchange`, `symbol_token`
- `side`, `product_type`, `gtt_type`
- `quantity`, `disclosed_quantity`
- `price`, `trigger_price`
- `stoploss_price`, `stoploss_trigger_price`
- `status` (optional), `created_at`, `updated_at`, `expires_at`

### Section envelope

```json
{
  "schema_version": 1,
  "account_id": "angel-main",
  "broker": "ANGEL_ONE",
  "section": "positions",
  "status": "OK",
  "source": "ANGEL_ONE_POSITIONS",
  "retrieved_at": "2026-11-25T05:30:00+00:00",
  "records": [],
  "limitations": ["BROKER_READ_ONLY", "POINT_IN_TIME_SNAPSHOT"]
}
```

On a section failure the same envelope carries `status: "UNAVAILABLE"`, a closed `error_code`, and an empty `records` list. On an unsupported section it carries `status: "UNSUPPORTED"`. Inside a snapshot these bodies preserve every other section. An individual section command instead fails with the existing redacted error envelope on stderr and exit `2` for provider, auth, or parser failure, matching `portfolio review`.

### Snapshot envelope

```json
{
  "schema_version": 1,
  "account_id": "angel-main",
  "broker": "ANGEL_ONE",
  "retrieved_at": "2026-11-25T05:30:00+00:00",
  "capabilities": ["holdings", "positions", "orders", "trades", "gtt"],
  "sections": {
    "positions": {
      "status": "OK",
      "source": "ANGEL_ONE_POSITIONS",
      "records": [],
      "limitations": []
    }
  },
  "limitations": ["BROKER_READ_ONLY", "POINT_IN_TIME_SNAPSHOT"]
}
```

Section-level limitations list data-specific limitations; the snapshot envelope
carries the two global labels. Section-level failures do not erase other
sections. Login, identity, credential, and registry failures fail the whole
command because no trustworthy session exists.

### Ordering, units, and nullability

- Holdings keep the existing review ordering: current value descending, then symbol.
- Positions, orders, trades, and GTT rules preserve provider order. The contract does not claim a cross-broker sort.
- Quantities are signed only for positions; order and trade quantities are non-negative.
- Zero prices, zero trigger prices, and zero average fills are emitted as `null` where the field is optional.
- `reported_at` is provider text. It is not asserted to be UTC, IST, or a complete date.
- Unknown optional fields are ignored. Unknown required fields, invalid types, negative quantities where prohibited, control characters, and malformed identifiers fail that section with `MALFORMED_RESPONSE`.

## Adapter boundary

`BrokerConnector` exposes `broker`, `capabilities`, `authenticated_client_code`, `login()`, and one method per section. `BrokerAdapter` owns the broker's credential suffixes, connector construction, and verification login. `SUPPORTED_BROKERS` is derived from the adapter registry. A connector that lacks a section omits it from `capabilities` and its method raises `SECTION_UNSUPPORTED`; callers check capabilities before fetching.

The account registry remains schema v2 and stores no broker payload. It stores only the broker name, credential prefix, and HMAC identity fingerprint. Adding another broker requires a new adapter and a new credential suffix set, not a registry migration or a contract change.

## Reference review

The owner pointed to the separate ProAlgoTrader broker layer for design comparison. Its broker-title registry, frozen domain records, denormalized symbol/token fields, and separation between a broker adapter and execution mode informed this contract. Its mutating order/position state machines and normalized execution enums were not adopted: this slice is read-only, preserves provider-reported status and timestamp text, and adds no execution semantics. No source was copied.

## Angel One connector

Read-only endpoints only:

1. `POST /rest/auth/angelbroking/user/v1/loginByPassword`
2. `GET /rest/secure/angelbroking/portfolio/v1/getAllHolding`
3. `GET /rest/secure/angelbroking/order/v1/getPosition`
4. `GET /rest/secure/angelbroking/order/v1/getOrderBook`
5. `GET /rest/secure/angelbroking/order/v1/getTradeBook`
6. `POST /rest/secure/angelbroking/gtt/v1/ruleList`

`placeOrder`, `modifyOrder`, `cancelOrder`, `convertPosition`, `createRule`, `modifyRule`, and `cancelRule` are not allowlisted and have no client method. URLs, redirects, and response size remain closed under the Plan 84 transport rules.

Credential suffixes are `API_KEY`, `CLIENT_CODE`, `PIN`, and `TOTP_SECRET`. The HMAC identity and authenticated-client-code check remain unchanged.

Parsing rules:

- For positions, orders, trades, and GTT, a successful response with `data: null` is an empty section. A non-list `data` for a list section is malformed. Holdings retain their Plan 84 object/list handling.
- `tradingsymbol`, `exchange`, and identifiers are validated and bounded before table output. `clientid` is never emitted.
- Order IDs prefer `uniqueorderid`, then `orderid`. The exchange order ID is retained separately.
- Order and GTT statuses are provider-reported and uppercased. An empty status is malformed for orders; a null GTT status yields `GTT_STATUS_UNAVAILABLE`.
- Position P&L uses a broker-provided `pnl`/`unrealised` value when present. If only `ltp` is present and the instrument is equity, P&L is derived as `(ltp - average_price) * quantity` and marked `pnl_source: DERIVED` plus `POSITION_PNL_DERIVED_FROM_LTP`. Non-equity positions without broker P&L are not derived; they carry `POSITION_PNL_DERIVATION_UNSUPPORTED`. If neither source is present, P&L is null and the section carries `POSITION_PNL_UNAVAILABLE`. A missing `ltp` yields `POSITION_LTP_UNAVAILABLE`.
- GTT rules are fetched in pages of 50 for `FORALL`, up to 20 pages. A full final page at the bound yields `GTT_RESULTS_TRUNCATED` rather than an unbounded retry.
- Trade value uses `tradevalue` when present; otherwise `quantity * price` plus `TRADE_VALUE_COMPUTED`.

## CLI

- `portfolio holdings --account ID [--storage-root ROOT] [--output json|table]`
- `portfolio positions --account ID ...`
- `portfolio orders --account ID ...`
- `portfolio trades --account ID ...`
- `portfolio gtt --account ID ...`
- `portfolio snapshot --account ID ...`

Existing commands remain:

- `portfolio accounts add|list|verify`
- `portfolio review --account ID`

Every command logs in once, checks the configured and authenticated identity, reads only, and writes no file. JSON is the stable machine surface; table output is a convenience view.

## Failure codes and limitations

New code: `SECTION_UNSUPPORTED`.

Reused codes: `ACCOUNT_NOT_FOUND`, `BROKER_UNSUPPORTED`, `CREDENTIALS_MISSING`, `MALFORMED_CREDENTIAL`, `AUTH_FAILED`, `IP_NOT_WHITELISTED`, `PROVIDER_UNAVAILABLE`, `MALFORMED_RESPONSE`, `IDENTITY_MISMATCH`, `IO_ERROR`, `INVALID_ARGUMENT`, `INTERNAL_ERROR`.

Limitations: `BROKER_READ_ONLY`, `POINT_IN_TIME_SNAPSHOT`, `POSITION_PNL_DERIVED_FROM_LTP`, `POSITION_PNL_DERIVATION_UNSUPPORTED`, `POSITION_PNL_UNAVAILABLE`, `POSITION_LTP_UNAVAILABLE`, `GTT_STATUS_UNAVAILABLE`, `GTT_RESULTS_TRUNCATED`, `TRADE_VALUE_COMPUTED`, plus the existing holdings limitations.

Exit codes: `0` every requested section is OK; `1` a requested section is unsupported or a domain/account failure; `2` invalid request, unsafe storage, credential/auth/provider failure, parser failure, or internal error. A snapshot with some successful sections and some `UNAVAILABLE` sections exits `1` after emitting the complete JSON envelope, so partial success is never reported as full success.

## Security and privacy

- No order or GTT mutation method exists in the connector.
- Credentials, JWTs, client codes, raw provider payloads, and private storage paths never appear in output, errors, tests, or logs.
- GTT `clientid`, provider request IDs, and account identifiers are not projected.
- Free-form broker text is bounded, control-character checked, and emitted only as an optional order status message.
- Output is owner-private point-in-time account data. It is not committed, published, or sent to a hosted AI service by the tool.
- The registry remains the only persisted file and contains no records.

## Acceptance

- The record contract, envelopes, capabilities, ordering, nullability, and failure statuses are documented and tested.
- Angel One returns holdings, positions, orders, trades, and GTT against synthetic payloads, including `data: null`, optional fields, malformed rows, and GTT pagination.
- The allowlist contains exactly the six read-only endpoints; mutation endpoints are rejected before transport.
- `portfolio holdings|positions|orders|trades|gtt|snapshot` emit deterministic JSON; tables render without control-character injection.
- A snapshot with one failing section emits every other section and exits `1`; a fully successful snapshot exits `0`.
- Existing account registration, identity checks, and `portfolio review` tests remain green.
- Focused tests, Ruff, Pyright, full suite/coverage, installed-wheel smoke, and hosted CI pass.
- Independent functional/domain and security/privacy reviews approve the exact candidate.
- A live owner-authorized smoke reads the real account without writing or publishing records.

## Non-goals

- Order placement, modification, cancellation, position conversion, or GTT mutation.
- Upstox/Kite/Fyers implementations in this slice; only the adapter seam is provided.
- Stored records, history, replay, database, CSV, tax, or reconciliation.
- F&O analytics, position sizing, advice, targets, rankings, or return claims.
- Cross-broker semantic normalization of provider statuses beyond the documented common fields.
