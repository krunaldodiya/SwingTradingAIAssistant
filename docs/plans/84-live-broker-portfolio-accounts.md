# Plan 84: live broker portfolio accounts and Angel One read-only review

Status: accepted bounded specification under [Issue #441](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/441). Owner and risk owner: Krunal Dodiya. Risk tier: R4 — broker credentials, private account data, multi-account isolation, and a live read-only provider surface. Base: `06530b87787892a320012e0f215247b4997c8cf3` (`main`, 2026-11-23).

## Authority and supersession

The owner directed on 2026-11-23 that portfolio accounts are **broker accounts**, that no manual CSV is ever supplied, and that no portfolio snapshot is stored. Holdings and performance are fetched live from the broker on every review.

This supersedes the manual CSV baseline in [Plan 83](83-read-only-portfolio-accounts.md) and the manual repository code merged in PR #438. Plan 83 remains historical evidence; its manual import, manual account type, snapshot storage, and snapshot tests are removed by this slice. No real manual account or snapshot exists in the owner data root.

The read-only account-connector boundary in `docs/notes/2026-08-09-provider-account-and-execution-connector-separation-hypothesis.md` still applies. This Plan supplies its bounded provider slice and does not authorize order execution.

## Outcome

- `portfolio accounts add --broker angel-one` checks four credential names, performs a read-only login, and stores only a non-secret reference.
- `portfolio accounts list` lists broker accounts and verification state.
- `portfolio review --account <id>` logs in, fetches current holdings, and returns a point-in-time performance review.
- The registry stores no holdings, values, P&L, CSV, or broker payload. No snapshot file is written.

## Registry v2

Path: `<storage-root>/.portfolio-accounts-v1/accounts.json`.

```json
{
  "schema_version": 2,
  "registry_salt": "<64 lowercase hex characters>",
  "accounts": [
    {
      "account_id": "angel-main",
      "broker": "ANGEL_ONE",
      "display_name": "Angel One main",
      "credential_prefix": "ANGEL_ONE",
      "identity_fingerprint": "hmac-sha256:<64 lowercase hex characters>",
      "created_at": "2026-11-23T12:30:00+00:00",
      "last_verified_at": "2026-11-23T12:30:00+00:00",
      "last_status": "CONNECTED"
    }
  ]
}
```

- `credential_prefix` matches `^[A-Z][A-Z0-9_]{0,62}$`. Credential names are `<PREFIX>_API_KEY`, `<PREFIX>_CLIENT_CODE`, `<PREFIX>_PIN`, `<PREFIX>_TOTP_SECRET`.
- `identity_fingerprint = HMAC-SHA256(bytes.fromhex(registry_salt), client_code)`. The raw client code and account number are never stored.
- `last_status` is `CONNECTED`, `AUTH_FAILED`, `CREDENTIALS_MISSING`, or `PROVIDER_UNAVAILABLE`.
- Duplicate `account_id`, duplicate `credential_prefix`, and duplicate `(broker, identity_fingerprint)` are rejected. A prefix is a single-account credential namespace.
- Missing, malformed, unknown-key, duplicate, foreign-owner, group/other-access, symlink, or oversize registry content fails closed.
- A schema-version 1 registry (the retired manual baseline) fails with `MANUAL_PORTFOLIO_RETIRED`; the old registry must be removed or renamed before adding broker accounts. No migration is provided because no real manual data exists.

## Credential and identity checks

`accounts add` performs, in order:

1. Validate the account id, display name, broker, and credential prefix.
2. Check all four credential names are present and non-blank. The error names only the missing variables.
3. Log in read-only to the broker with the supplied credentials.
4. Compute the identity fingerprint and reject a duplicate under the same broker.
5. Store the non-secret reference and status.

`--no-verify` is not accepted for broker accounts. A login failure stores nothing.

`review` rechecks the configured client code against the stored HMAC fingerprint before login and rejects `IDENTITY_MISMATCH`; if the login response exposes the authenticated client code, it must match the configured code as well. A repointed or shared prefix can therefore never return another account's holdings under this account's label.

## Angel One connector

Exactly two endpoints:

1. `POST /rest/auth/angelbroking/user/v1/loginByPassword`
2. `GET /rest/secure/angelbroking/portfolio/v1/getAllHolding`

No order, position, trade-book, profile, or generic request method exists. The JWT is held in memory for one command and never logged or stored.

- TOTP is generated locally from the base32 seed: HMAC-SHA1, 30-second step, six digits.
- Headers include `X-UserType`, `X-SourceID`, `X-ClientLocalIP`, `X-ClientPublicIP`, `X-MACAddress`, and `X-PrivateKey` (the API key).
- `X-ClientPublicIP` uses `PORTFOLIO_PUBLIC_IP` when set; otherwise the local address. An IP rejection maps to `IP_NOT_WHITELISTED`.
- `X-MACAddress` comes from `/sys/class/net/eth0/address`, with a fixed fallback.
- Only the two exact URLs are allowed. Redirects are refused, the final URL must equal the requested URL, headers are not forwarded, and responses are capped at 8 MiB.
- Holding symbols must match `^[A-Z0-9][A-Z0-9&.-]{0,19}$`; control characters, newlines, and bidi text are rejected before table output.
- Row P&L is computed as `current - invested`, never trusted from the broker. `data.holdings` and `data.totalholding` are reconciled against computed invested, current, and computed P&L with an INR 5.00 tolerance (broker totals are rounded). A broker-provided row P&L that disagrees with the computed value by more than INR 5.00 yields `PNL_INCONSISTENT`; a malformed provided P&L fails closed with `MALFORMED_RESPONSE`.
- Missing previous close or an empty holdings list yields `DAY_CHANGE_UNAVAILABLE`; any T1 quantity yields `T1_QUANTITY_PRESENT`; missing totals yields `TOTAL_NOT_PROVIDED`; partial totals yields `TOTAL_PARTIAL`.

## Review contract

`portfolio review --account <id> --output json`:

```json
{
  "schema_version": 1,
  "account_id": "angel-main",
  "broker": "ANGEL_ONE",
  "source": "ANGEL_ONE_HOLDINGS",
  "retrieved_at": "2026-11-23T12:35:00+00:00",
  "summary": {
    "holdings": 5,
    "invested": 100000.0,
    "current": 102500.0,
    "overall_pnl": 2500.0,
    "overall_pnl_pct": 2.5,
    "day_change": 500.0,
    "day_change_pct": 0.49,
    "top_holding_weight_pct": 25.0
  },
  "holdings": [],
  "limitations": ["BROKER_READ_ONLY", "POINT_IN_TIME_SNAPSHOT"]
}
```

- Money uses `Decimal` under a high-precision local context and is emitted rounded to two decimals.
- Ordering is current value descending, then symbol ascending.
- Every review carries `BROKER_READ_ONLY` and `POINT_IN_TIME_SNAPSHOT`.
- No `USER_SUPPLIED_UNVERIFIED` label is emitted, because the data is broker-read rather than user-supplied. No broker-verification claim beyond the read is made.
- No advice, target, ranking, or return claim.

## CLI

- `portfolio accounts add --broker angel-one --account-id ID --display-name NAME --credential-prefix PREFIX`
- `portfolio accounts list [--output json|table]`
- `portfolio accounts verify --account ID`
- `portfolio review --account ID [--output json|table]`

`portfolio import` is removed. Manual accounts and snapshot storage are removed.

## Failure codes and exits

`ACCOUNT_NOT_FOUND`, `ACCOUNT_ID_INVALID`, `BROKER_UNSUPPORTED`, `CREDENTIAL_PREFIX_INVALID`, `DISPLAY_NAME_INVALID`, `DUPLICATE_ACCOUNT_ID`, `DUPLICATE_CREDENTIAL_PREFIX`, `DUPLICATE_BROKER_IDENTITY`, `CREDENTIALS_MISSING`, `MALFORMED_CREDENTIAL`, `AUTH_FAILED`, `IP_NOT_WHITELISTED`, `PROVIDER_UNAVAILABLE`, `MALFORMED_RESPONSE`, `RECONCILIATION_MISMATCH`, `IDENTITY_MISMATCH`, `REGISTRY_PERMISSIONS`, `REGISTRY_CORRUPT`, `REGISTRY_TOO_LARGE`, `UNSUPPORTED_SCHEMA`, `MANUAL_PORTFOLIO_RETIRED`, `IO_ERROR`, `INVALID_ARGUMENT`, `INTERNAL_ERROR`.

Limitations: `BROKER_READ_ONLY`, `POINT_IN_TIME_SNAPSHOT`, `T1_QUANTITY_PRESENT`, `DAY_CHANGE_UNAVAILABLE`, `TOTAL_NOT_PROVIDED`, `TOTAL_PARTIAL`, `PNL_INCONSISTENT`.

Exit codes: `0` success; `1` domain/stored-state failure (`ACCOUNT_NOT_FOUND`, `REGISTRY_CORRUPT`, `DUPLICATE_ACCOUNT_ID`); `2` invalid request, unsafe/missing path, unsupported/retired schema, credential/auth/provider failure, parser failure, or internal error. Every failure prints a redacted JSON envelope on stderr.

## Acceptance

- No CSV import command, manual account type, snapshot module, or snapshot file remains.
- Broker account add checks all four credentials, performs a read-only login, stores only the reference, and rejects duplicate identities.
- Review fetches live holdings and returns the documented summary; no file is written under the data root.
- Missing credentials, auth failure, IP rejection, malformed payload, and reconciliation mismatch fail closed with closed codes.
- Manual registry/snapshot tests are removed; broker tests use an injected transport and a fake holdings payload.
- One account's credentials and data are never read by another account: duplicate prefixes are rejected, review rechecks the HMAC identity before login, and an authenticated identity mismatch fails before holdings.
- Redirects and foreign URLs are refused; oversized responses and malformed symbols fail closed.
- P&L is computed from holdings and reconciled; a broker P&L disagreement is surfaced as `PNL_INCONSISTENT`.
- Focused tests, Ruff, Pyright, independent functional/security reviews, and hosted CI pass.
- A real owner-authorized live smoke adds `angel-main` and reviews the account.

## Non-goals

- Upstox, Kite, Fyers, orders, positions/F&O, execution, advice, history, tax, benchmarking.
- Credential storage, a vault, a database, or cloud sync.
- Manual CSV import or any stored portfolio snapshot.
