# Inspect owner-staged NSE safety evidence

[Plan 67](../plans/67-owner-staged-nse-safety-evidence.md) / Issue #294 adds
one offline inspection boundary. It validates the shape and binding of a local
private package; it does not collect data, authenticate a source, establish
permission, clear eligibility, or produce a signal.

## Before you begin

Use an existing owner-private research root and a retained `CURRENT_STRUCTURE`
observation from the installed `stock-observations` workflow. Keep its exact
lowercase 64-character observation handle.

Manually obtain any reference files through a process you are independently
permitted to use. The software does not contact NSE or another source, and a
local digest cannot prove the origin, permission, currency, or completeness of
a staged file. The intended operator reference pages are [securities available
for trading](https://www.nseindia.com/market-data/securities-available-for-trading),
[ASM](https://www.nseindia.com/regulations/additional-surveillance-measure), and
[GSM](https://www.nseindia.com/regulations/graded-surveillance-measure).

Create exactly this package below the existing private root. The directory must
be owned by the effective user and mode `0700`; every file must be owned by that
user, a regular single-link file, and mode `0400` or `0600`.

```text
<private-root>/nse-safety-evidence-v1/
  equity-trading.csv
  asm.csv
  gsm.csv
```

Do not add a manifest, source URL, timestamp, JSON fact, symlink, hard link, or
extra file. The command reads existing staged bytes only. It never creates,
updates, deletes, or downloads a source artifact.

`equity-trading.csv` must have exactly the normalized columns `SYMBOL`,
`SERIES`, `ISIN_NUMBER`, and `DATE_OF_LISTING`. It must contain exactly one
`SERIES=EQ` row whose symbol and ISIN exactly match the admitted observation;
its date must be a real `DD-Mon-YYYY` calendar date. `asm.csv` and `gsm.csv`
must each have only a `SYMBOL` column, with no duplicate symbols. CSV is UTF-8
(a BOM is allowed), with a 1 MiB artifact limit, at most 10,000 data rows, and
at most 1,024 characters per field.

## Inspect the package

```sh
stock-safety-evidence inspect \
  --storage-root /absolute/private/research-root \
  --observation OBSERVATION_HANDLE \
  --output json
```

The SDK is
`inspect_owner_staged_nse_safety_evidence_v1(storage_root, observation)`. It
accepts no raw CSV, individual artifact paths, mapping, price, source URL,
timestamp, eligibility, or policy input.

On a valid staging package, the command exits `0` and returns
`stock-safety-evidence@v1` with `status: STAGED` and
`eligibility_status: UNKNOWN`. It reports the selected public symbol, selected
observation handle, fixed reference-page identities, artifact hashes, a package
hash, literal ASM/GSM staged-list membership, the fixed refusal set, and runtime
and result identities. It never returns raw rows, ISIN, listing date, private
paths, prices, source publication times, permissions, or exception text.

`OBSERVED_IN_STAGED_LIST` means only that the exact symbol appeared in those
local staged bytes. `NOT_OBSERVED_IN_STAGED_LIST` is not a safety, surveillance,
liquidity, event-risk, eligibility, or trading conclusion. Both outcomes remain
`UNKNOWN` and neither changes Sprint 52's `NO_TRADE` decision.

## Failures and safe use

Missing, malformed, unsafe, changed, or identity-mismatched evidence exits `1`
and returns only:

```json
{"code":"STAGED_EVIDENCE_UNAVAILABLE","contract_version":"stock-safety-evidence@v1","status":"UNAVAILABLE"}
```

Relative roots, malformed handles, unknown flags, or an attempted raw-input flag
exit `2`, write `request_invalid` to standard error, and do not access the root
or source package. A completed `STAGED` report proves local structural
admission only. Keep the original local files for diagnosis rather than editing
them to bypass a refusal.

Use a trusted installed package, console launcher, Python interpreter, and
import environment. The result identities support reproducibility and
correlation of exact admitted bytes; they do not authenticate the provider or
grant a licence. G03 and G04 require separately governed source authority,
listing-duration, execution-liquidity, price/currency, event-risk, and
actionability work.
