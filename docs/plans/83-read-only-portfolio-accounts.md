# Plan 83: read-only portfolio review from a manual holdings baseline

Status: accepted bounded specification under [Issue #437](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/437). Owner and risk owner: Krunal Dodiya. Risk tier: R3 — private portfolio data, private local persistence, and a deliberate product-boundary change. Base: `0f5f5ea99d1504a2cca85490bbadbd7b2ecab9c0` (`main`, 2026-11-23).

## Outcome

A CLI user can register one or more **manual** portfolio accounts in a private local registry, import a typed holdings snapshot, list the accounts, and request a deterministic read-only performance review for one account.

The snapshot is explicitly user supplied and unverified. It never claims broker verification, never contacts a broker, and never stores credentials. This is the manual baseline required before any broker connector.

## Authority and documented gates

- The read-only portfolio direction is already accepted in `docs/architecture-freeze-v1.md` (Module 10, Portfolio Monitoring: read-only, limited to supported listed-equity holdings; may assess evidence, concentration, risk, performance, and hold/exit conditions; no orders; not long-term advisory).
- `docs/notes/2026-08-09-provider-account-and-execution-connector-separation-hypothesis.md` remains an **open hypothesis**. Its promotion gate 2 requires a manual user-supplied snapshot contract **before** a broker connector. Gate 1 is satisfied by the owner's 2026-11-23 approval of this bounded problem.
- The owner chose the documented manual-first order on 2026-11-23.
- `docs/agent-usage.md` currently says the tool "never assesses a portfolio." That contradicts this accepted slice. The same change updates the sentence to permit read-only review of user-supplied supported listed-equity holdings; it must not claim broker verification or long-term advice.
- The Angel One connector is **not** part of this Plan. It remains a later, separately gated slice that requires the manual baseline to be accepted, provider-specific evidence, and independent security/privacy/provenance review.

| Evaluation | Result |
| --- | --- |
| Expected value | Replaces retyped portfolio figures with a validated, private, reproducible snapshot and a deterministic review, without any broker credential. |
| Scope fit | Implements the documented manual baseline and the accepted read-only portfolio boundary. |
| Material risk | Private financial data; a malformed or partial snapshot could misstate value or P&L; a soft boundary change could imply broker verification or advice. |
| Smallest alternative | Do nothing and keep the portfolio outside the tool. Rejected because the owner explicitly requested account-level review and the manual contract is the documented prerequisite. |
| Decision | Accepted: manual account registry, typed CSV snapshot, append-only private storage, deterministic review, no network access. |

## Scope

- `portfolio accounts add --broker manual` — register one manual account.
- `portfolio accounts list` — list registered accounts.
- `portfolio import` — validate and store one holdings snapshot.
- `portfolio review` — review the latest snapshot for one account.

## Design

### Private registry

Path: `<storage-root>/.portfolio-accounts-v1/accounts.json`.

- Directory `0700`; file `0600`; reject symlinks, non-regular files, unsafe modes, and foreign owners.
- Atomic write: exclusive temporary file in the same directory, `fsync`, `os.replace`, directory `fsync`.
- `flock` on `.lock` serializes writers where the platform supports it.
- Schema version `1`; unknown versions fail closed.

```json
{
  "schema_version": 1,
  "accounts": [
    {
      "account_id": "manual-main",
      "broker": "MANUAL",
      "display_name": "Manual main",
      "created_at": "2026-11-23T12:00:00+05:30",
      "last_import_at": "2026-11-23T12:05:00+05:30"
    }
  ]
}
```

- `account_id`: caller-chosen lowercase slug, unique.
- `broker`: exactly `MANUAL` in this slice.
- No credential field, identity fingerprint, client code, or account number exists.
- `last_import_at` is `null` until the first successful import.

### Snapshot input

`portfolio import --file <path> --as-of <ISO-8601 timestamp>`.

- UTF-8 CSV, at most 1 MiB, regular file only; symlinks are rejected. The input is opened with `O_NOFOLLOW`, and its size is bounded before and after the read.
- One header row. A leading UTF-8 BOM and completely empty leading lines are tolerated. A row with empty cells is validated and rejected explicitly, never skipped as blank.
- Required columns, in any order: `symbol`, `exchange`, `quantity`, `average_price`, `last_price`.
- Optional columns: `isin`, `previous_close`.
- Missing required columns, duplicate headers, or unknown columns fail the whole import with `INPUT_HEADER_INVALID`. Unknown columns are rejected rather than silently ignored.
- Row rules:
  - `symbol`: trimmed, uppercased, `^[A-Z0-9][A-Z0-9&.-]{0,19}$`.
  - `exchange`: exactly `NSE` after trimming surrounding whitespace. Any other exchange is isolated as a rejected row with `UNSUPPORTED_EXCHANGE`.
  - `quantity` and `average_price`: finite decimal `>= 0`.
  - `last_price` and optional `previous_close`: finite decimal `> 0`.
  - Every number must be within `1e-9` to `1e12` in magnitude (zero is allowed only where the rule permits it); larger or smaller finite values are rejected with the field's closed reason. This bounds `Decimal.quantize` and JSON output.
  - `isin`, when present: 12-character Indian ISIN, `^INE[0-9A-Z]{8}[0-9]$`.
  - A repeated symbol within one file rejects the later row with `DUPLICATE_SYMBOL`. The first valid symbol is marked before exchange or number validation, so a rejected first occurrence still blocks a later duplicate.
- A rejected row never disappears silently. It is stored with its data-row number, symbol when known, and a closed reason code.
- If no row is valid, the import fails with `NO_VALID_HOLDINGS` and stores nothing.
- A partial import is allowed but carries `PARTIAL_SNAPSHOT`.
- `as_of` must be timezone-aware and is the owner-declared point-in-time. `imported_at` is the system time and is stored separately.
- The raw CSV is not retained; only its SHA-256, the validated rows, and the rejected-row reasons are stored.

### Snapshot storage

Path: `<storage-root>/.portfolio-accounts-v1/snapshots/<account_id>/<snapshot_id>.json`.

- `snapshot_id`: `YYYYMMDDTHHMMSSffffffZ-<8 hex>` (microsecond precision), generated at import.
- A second import with the same microsecond timestamp fails with `SNAPSHOT_COLLISION` rather than relying on the random suffix for ordering.
- Snapshot files are append-only and never overwritten. The `snapshots/` container and the account directory are both `0700`.
- File `0600`; account snapshot directory `0700`; atomic write.
- The snapshot is a point-in-time record. It is never presented as historical holdings at an earlier cutoff.

```json
{
  "schema_version": 1,
  "account_id": "manual-main",
  "source": "MANUAL_SNAPSHOT",
  "as_of": "2026-11-23T11:30:00+05:30",
  "imported_at": "2026-11-23T12:05:00+05:30",
  "input_sha256": "<64 hex characters>",
  "holdings": [
    {
      "symbol": "HDFCBANK",
      "exchange": "NSE",
      "isin": "INE040A01034",
      "quantity": "100",
      "average_price": "790.58",
      "last_price": "829.85",
      "previous_close": "846.00"
    }
  ],
  "rejected": [
    {"row": 4, "symbol": "XYZ", "reason": "UNSUPPORTED_EXCHANGE"}
  ],
  "limitations": ["USER_SUPPLIED_UNVERIFIED", "PARTIAL_SNAPSHOT"]
}
```

Decimal values are stored as strings to keep exact arithmetic.

### Review contract

`portfolio review --account <id> --output json` returns:

```json
{
  "schema_version": 1,
  "account_id": "manual-main",
  "broker": "MANUAL",
  "source": "MANUAL_SNAPSHOT",
  "snapshot_id": "20261123T120500123456Z-1a2b3c4d",
  "as_of": "2026-11-23T11:30:00+05:30",
  "imported_at": "2026-11-23T12:05:00+05:30",
  "summary": {
    "holdings": 5,
    "invested": 409652.15,
    "current": 401447.75,
    "overall_pnl": -8207.0,
    "overall_pnl_pct": -2.0,
    "day_change": -11170.75,
    "day_change_pct": -2.71,
    "top_holding_weight_pct": 20.68
  },
  "holdings": [],
  "rejected": [],
  "limitations": ["USER_SUPPLIED_UNVERIFIED", "SECTOR_UNKNOWN", "MEMBERSHIP_UNVERIFIED"]
}
```

- Money is computed with `Decimal` and emitted rounded to two decimal places.
- Ordering is current value descending, then symbol ascending.
- `weight_pct` is each holding's share of current value.
- Day change is present only when every accepted holding has `previous_close`; otherwise both day fields are `null` with `DAY_CHANGE_UNAVAILABLE`.
- Every review always carries `USER_SUPPLIED_UNVERIFIED`.
- `SECTOR_UNKNOWN` and `MEMBERSHIP_UNVERIFIED` are explicit because the manual input supplies neither sector nor index membership.
- Loaded snapshots are revalidated, not trusted:
  - `limitations` must have no duplicates and only the closed vocabulary `USER_SUPPLIED_UNVERIFIED`, `MEMBERSHIP_UNVERIFIED`, `SECTOR_UNKNOWN`, `PARTIAL_SNAPSHOT`, `DAY_CHANGE_UNAVAILABLE`;
  - the three mandatory labels are required;
  - `PARTIAL_SNAPSHOT` must match non-empty `rejected`, and `DAY_CHANGE_UNAVAILABLE` must match any missing `previous_close`;
  - rejected-row reasons must belong to the closed row-reason set;
  - duplicate holding symbols are rejected.
- No advice, target, ranking, or return claim is emitted.

### Failure codes

`ACCOUNT_NOT_FOUND`, `ACCOUNT_ID_INVALID`, `BROKER_UNSUPPORTED`, `DISPLAY_NAME_INVALID`, `INVALID_ARGUMENT`, `DUPLICATE_ACCOUNT_ID`, `REGISTRY_PERMISSIONS`, `REGISTRY_CORRUPT`, `UNSUPPORTED_SCHEMA`, `IO_ERROR`, `INPUT_UNREADABLE`, `INPUT_TOO_LARGE`, `INPUT_HEADER_INVALID`, `AS_OF_INVALID`, `NO_VALID_HOLDINGS`, `NO_SNAPSHOT`, `SNAPSHOT_CORRUPT`, `SNAPSHOT_PERMISSIONS`, `SNAPSHOT_COLLISION`, `INTERNAL_ERROR`.

Exit codes: `0` success; `1` domain or stored-state failure; `2` invalid request or internal error. Every failure prints a JSON error envelope to `stderr` containing only a closed code and a redacted message — never a traceback, private path, or holdings value.

## Acceptance

- Add two manual accounts and list both; duplicate account ids are rejected.
- Import a valid CSV and review it with exact invested, current, P&L, and weights.
- A partial CSV stores accepted rows and reports every rejected row with a reason.
- A CSV with no valid rows stores nothing.
- Unsupported exchanges, invalid symbols, duplicate symbols, invalid ISINs, malformed numbers, and malformed headers fail closed or are isolated.
- `as_of` must be timezone-aware; `imported_at` is system time.
- Registry and snapshot files are `0600`, atomic, append-only, and rejected when permissions are loosened. The registry, `snapshots/` container, and account directories are `0700`; the lock file is `0600`, opened with `O_NOFOLLOW`, and never follows a symlink.
- A non-directory or symlinked registry/snapshot path and a read-only storage root produce a closed `REGISTRY_PERMISSIONS`, `SNAPSHOT_PERMISSIONS`, or `IO_ERROR`, never a traceback.
- Same-microsecond imports are rejected as `SNAPSHOT_COLLISION`; microsecond ordering selects the true latest snapshot.
- Out-of-range finite decimals and stored values that would overflow formatting are rejected at import or load.
- Loaded snapshots cannot drop or forge the mandatory unverified labels, invent rejection reasons, or contain duplicate holdings.
- One account's import or review never reads another account's snapshots.
- No credential, broker call, order, position, or network request exists in the slice.
- `docs/agent-usage.md` no longer states that the tool never assesses a portfolio; it states the exact read-only, user-supplied limits.
- Focused tests, full pytest with the 87% coverage gate, `ruff`, and `pyright` pass.
- Independent functional and security/privacy reviews cover the exact candidate.

## Later connector credential model (not implemented in this slice)

This section freezes the credential boundary for the separately gated broker connector. Nothing below exists in slice 1, which stores no credentials and makes no broker call.

- **Keyed by account, never by broker.** The registry stores an opaque `account_id` and a `credential_ref` pointer. Two Angel One accounts therefore use two namespaces, not one shared `ANGEL_ONE_*` set.
- **Reference grammar.** Slice 2 starts with `env:<PREFIX>`, where the resolver reads exactly `<PREFIX>_API_KEY`, `<PREFIX>_CLIENT_CODE`, `<PREFIX>_PIN`, and `<PREFIX>_TOTP_SECRET` (names vary by broker). A later deployment may use `doppler:<project>/<config>#<PREFIX>` or `keyring:<service>:<account>` without changing the registry contract.
- **Examples.** `angel-main` → `env:ANGEL_MAIN`; `angel-family` → `env:ANGEL_FAMILY`; `upstox-main` → `env:UPSTOX_MAIN`; `kite-main` → `env:KITE_MAIN`.
- **No ambient cross-account access.** The resolver receives one `credential_ref` and must not enumerate another account's namespace. When stronger isolation is required, run one account operation per subprocess with only that account's secrets injected, or use one Doppler config/project per account.
- **Identity binding.** On first verification, the connector authenticates and stores `identity_fingerprint = HMAC-SHA256(registry_salt, broker_client_identity)`. A second account resolving to the same broker identity is rejected with `DUPLICATE_BROKER_IDENTITY`. The raw client code, account number, and personal identifiers are not stored.
- **Per-account token lifecycle.** Each account has its own login, token, expiry, refresh, and revocation path. Tokens are never shared, cached across accounts, logged, or written to the registry. Broker-specific flows differ: Angel One PIN plus TOTP, Upstox daily access token, Kite API key plus daily request-token exchange, Fyers OAuth.
- **Removal.** Removing an account deletes only its registry record and snapshots. The operator deletes the referenced secret; the tool never deletes or rotates provider secrets automatically.
- **Closed failures.** `CREDENTIAL_REF_INVALID`, `CREDENTIALS_MISSING`, `TOKEN_EXPIRED`, `IDENTITY_MISMATCH`, `DUPLICATE_BROKER_IDENTITY`, `AUTH_FAILED`, `IP_NOT_WHITELISTED`, `PROVIDER_UNAVAILABLE`.

This section does not satisfy gates 2–6 of the account-connector hypothesis by itself. Slice 2 still requires its own accepted Plan, provider evidence, independent security/privacy review, and isolation tests.

## Non-goals

- Angel One, Upstox, or any broker login, credential, holdings API, or token.
- Intraday/F&O positions, order book, trade book, orders, execution, or position sizing.
- Historical holdings reconstruction, time-series performance, tax, charges, or benchmarking.
- Sector classification, index-membership verification, advice, targets, rankings, or return claims.
- Encryption/vault subsystem, database, cloud sync, or multi-user access control.
