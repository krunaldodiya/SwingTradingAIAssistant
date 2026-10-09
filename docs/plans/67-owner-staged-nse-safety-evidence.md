# Plan 67: owner-staged NSE safety-evidence intake

Accepted October 9, 2026 under [Issue #294](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/294),
Milestone 45. Owner and risk owner: Krunal Dodiya. Risk tier: R3 financial
research provenance, private evidence handling and safety gating. Base
`b1840fab6509e4343958e17e3792bf9e8d586675`.

## Question and smallest usable path

Can an owner manually stage a small, current exchange-reference package beside
an existing private retained observation and have the installed tool validate
its structure and exact binding without creating a source-authentication,
eligibility or signal claim?

The selected path is one offline, read-only command:

```text
stock-safety-evidence inspect --storage-root ABSOLUTE_PRIVATE_ROOT \
  --observation SHA256 --output json
```

It re-admits one Sprint 51 `CURRENT_STRUCTURE` observation, reads one fixed
operator-staged package under that same root, and produces a redacted canonical
staging report. A valid report always has `eligibility_status: UNKNOWN`; there
is no implementation path to `ELIGIBLE`, `ACTIONABLE`, entry, stop, target or
ranking output.

This is a working intake path rather than another descriptive market fact: an
operator can discover whether the exact staged bytes have the supported shape
and bind to the re-admitted identity without exposing their contents. It does
not close G03 or G04. A later eligibility policy must separately establish
source authority, listing-duration criteria, execution-liquidity criteria,
price/currency policy and event-risk coverage.

## Authority, source boundary and decision

The owner directed the next non-Future signal prerequisite after Sprint 52.
The following NSE reference pages are fixed only as the intended operator
reference locations:

- [securities available for trading](https://www.nseindia.com/market-data/securities-available-for-trading);
- [Additional Surveillance Measure](https://www.nseindia.com/regulations/additional-surveillance-measure); and
- [Graded Surveillance Measure](https://www.nseindia.com/regulations/graded-surveillance-measure).

NSE's [Terms of Use](https://www.nseindia.com/static/nse-terms-of-use) prohibit
systematic or automated collection. The [NSE research-data list](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/Data%20list%20under%20NSE%20Data%20Sharing%20Policy%20for%20Research%20and%20Analysis_20250728.pdf)
lists securities available for trading and surveillance measures as research
categories, subject to its own scope. Neither source gives this software a
licence, proves a local file's origin, or authorizes a downloader. The operator
must obtain any files through an independently permitted manual process.

The source decision is therefore deliberately narrow:

| Concern | Decision |
| --- | --- |
| Network, browser automation, credentials, downloader | Excluded. The installed command has no network dependency or source-acquisition code. |
| Local operator staging | Accepted as a private input boundary only. Ownership, paths, modes, descriptors and digests are checked. |
| Origin authentication and licence proof | Unavailable. A digest proves byte consistency, not origin or permission; the report states this limitation. |
| Eligibility/actionability | Blocked. No valid or invalid staged package can clear eligibility or alter Sprint 52's `NO_TRADE` decision. |
| Actual current status | Not claimed. There is no source-published time in the V1 package and staged-list absence is never safety clearance. |

## Fixed package and admission contract

The operator manually stages exactly these files beneath the existing private
storage root:

```text
<storage-root>/nse-safety-evidence-v1/
  equity-trading.csv
  asm.csv
  gsm.csv
```

There is no manifest, caller-authored source URL, capture time, safety boolean,
eligibility envelope or JSON fact input. This avoids treating a self-authored
claim as exchange provenance. Each file's fixed logical reference page is part
of the runtime contract; the response returns only its SHA-256 and fixed kind.

The package directory is owned by the effective user, mode `0700`, and contains
only those three regular single-link files. Each file is owned by the effective
user and mode `0400` or `0600`. The reader rejects relative paths, `.`/`..`,
symlinks, hard links, special files, unexpected entries, unsafe parent/package
identity, descriptor/path replacement and a changed file identity during read.
It opens bounded file descriptors beneath the private root without following
links. It neither creates nor modifies any source file, and existing root lease
behavior remains the only governed temporary coordination effect.

All CSV values are UTF-8 (BOM accepted) and use the Python standard library
CSV parser. Each artifact is bounded to 1 MiB, 10,000 rows and 1,024 characters
per field. A limit-plus-one result is unavailable. Duplicate headers after
normalization, duplicate source identities, invalid CSV, control characters,
formula-prefixed identity fields, unsupported header shape and duplicate or
conflicting matching rows fail closed.

| File | Required normalized columns | Required selected-row rule |
| --- | --- | --- |
| `equity-trading.csv` | `SYMBOL`, `SERIES`, `ISIN_NUMBER`, `DATE_OF_LISTING` | Exactly one `SERIES=EQ` row matches the re-admitted observation's effective symbol and ISIN; the listing field must be syntactically present and nonempty. |
| `asm.csv` | `SYMBOL` | At most one matching symbol. The response says only whether it was observed in the staged bytes. |
| `gsm.csv` | `SYMBOL` | At most one matching symbol. The response says only whether it was observed in the staged bytes. |

The `DATE_OF_LISTING` field is evidence presence only. Its value never becomes a
listing-age threshold. `NOT_OBSERVED_IN_STAGED_LIST` is not a claim that a
security has no surveillance, restriction, event risk or liquidity problem.
ASM/GSM presence is returned as a literal staged-list observation, never an
adverse-action, wrongdoing or trading-policy conclusion.

## SDK, CLI and public result

The SDK exposes only:

```python
inspect_owner_staged_nse_safety_evidence_v1(storage_root: Path, observation: str)
```

`storage_root` must be absolute and `observation` must be a lowercase 64-hex
Sprint 51 handle. The SDK accepts no paths for individual files, no raw CSV,
mapping, price, source time, status or policy value. It reuses the record reader
before inspecting the package and requires an admitted `CURRENT_STRUCTURE`
result with producer-owned mapping.

The public success envelope is `stock-safety-evidence@v1` and contains only:

- `status: STAGED` and `eligibility_status: UNKNOWN`;
- public symbol and observation handle;
- a fixed reference-page identity per artifact, artifact SHA-256 values and a
  canonical package identity;
- `listing_date_observed: true`, and each staged-list state;
- the fixed refusal set,
  `OPERATOR_STAGED_EVIDENCE_NOT_SOURCE_AUTHENTICATED`,
  `LISTING_DURATION_POLICY_UNAVAILABLE`,
  `EXECUTION_LIQUIDITY_POLICY_UNAVAILABLE`,
  `PRICE_CURRENCY_AND_LOW_PRICE_POLICY_UNAVAILABLE`, and
  `EVENT_RISK_COVERAGE_UNAVAILABLE`; and
- runtime and result identities.

It emits canonical compact JSON with a trailing LF, bounded to 64 KiB. It does
not expose raw CSV bytes, row values, counts, listing date, private paths,
permissions, source publication times or exception text. A completed staging
report exits zero because its stated staging operation succeeded; eligibility
remains unknown. Invalid arguments exit two with `request_invalid`. Missing,
unsafe, unavailable, malformed or mismatched selected inputs exit one with a
fixed redacted unavailable envelope. Help has no root or source effect.

## Determinism, compatibility and ownership

The report identity binds the exact admitted observation identity, exact runtime
identity, fixed package contract and three artifact digests. The same safe bytes
and observation reproduce the same report; replacement changes an artifact and
result identity or fails descriptor checks. It makes no temporal coherence or
historical replay claim. A package can be replaced only outside the process by
the owner; this slice adds no publisher, archive, latest pointer or retention
model.

Root is sole writer and owns the new safety-evidence module, CLI/entrypoint,
runtime manifest, focused tests, this Plan, Sprint 53 record and current
roadmap/overview status. Existing `stock-eligibility@v2`, `signal-decisions`,
Sprint 51 records and all prior runtime manifests remain compatible and are not
modified semantically. New runtime source is formatted before its manifest is
refreshed. No dependency is added.

## Frozen adversarial matrix

| Case | Required behavior |
| --- | --- |
| Valid identity-matching package; ASM/GSM absent | `STAGED`, `UNKNOWN`, literal not-observed states, no safety/actionability wording. |
| Valid identity-matching package; ASM or GSM present | `STAGED`, `UNKNOWN`, literal observed state, no adverse-action or policy conclusion. |
| Wrong observation question, mapping, symbol, ISIN, series or duplicate matching equity row | Fixed unavailable result; no partial public staging report. |
| Missing file/package, malformed UTF-8/CSV, header collision, nonempty invalid listing field, duplicate surveillance symbol | Fixed unavailable result; no raw parse detail. |
| 1 MiB/10,000-row/1,024-character boundary and plus one | Boundary accepted only when otherwise valid; plus one fails closed. |
| Relative root/handle, unexpected flag, individual source path, raw CSV/JSON input | `request_invalid` before root or source access. |
| Link, hardlink, special file, foreign owner, unsafe mode, traversal, extra entry or descriptor/path swap | Fixed unavailable result; no source-data write. |
| Artifact replacement/concurrent mutation during read | Identity recheck refuses or reports only a self-consistent exact package; never mixes bytes. |
| Network/socket/client import or source downloader invocation | Forbidden in focused tests; command stays offline. |
| Raw rows, paths, numeric price/listing data or exception text in success/failure | Absent from stdout/stderr assertions. |
| Existing V1/V2 observation and decision commands | Existing focused and installed behavior remains unchanged. |
| Runtime source/inventory substitution | Fails closed before public success. |

## Verification and delivery boundary

Start with a discriminating focused test for valid staging and immutable
`UNKNOWN`, then add the matrix before implementation is offered for review.
Synthetic CSV fixtures test parser and boundary behavior only; they do not prove
actual exchange access, permission, source origin, current status or market
qualification. R3 requires complete exact-byte functional/domain and
security/privacy/provenance reviews, current hosted full test/coverage/static/
build/installed/native OCI gates, normal PR merge, exact main admission, private
OCI publication/pull, retained receipts and live Issue/milestone/project
closeout. Before the ready-PR trigger, obtain a fresh account-wide GitHub
Actions/Packages allowance and $0 Stop-usage budget readback.

Pause at any proposed provider, credential, automated collection, source-origin
authentication, policy threshold, actionability, persistent replay or protected
external effect. These belong to a separately governed successor.
