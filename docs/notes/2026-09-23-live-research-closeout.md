# Sprint 20 live-research closeout and disclosure exception

Event date: 2026-09-23
Recovered: 2026-09-27
Status: historical operational closeout with a one-time documented exception;
not a clean privacy pass or a standing exception.
Authority: [Issue #210 closeout](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/210#issuecomment-5792142241),
read back during recovery.

## Result and limits

The existing [assistant observation](../workflows/single-stock-research-observation.md)
records the earlier synthetic demonstration. Sprint 20 subsequently exercised
PNB, RELIANCE, and TCS for the completed 2026-09-22 session. Separate V2
price-behavior and structure questions returned `READY` with matching per-stock
canonical identity, selection identity, and price basis. RELIANCE and TCS still
reported `INSUFFICIENT_STRUCTURE` inside the structure facts: question readiness
did not establish a trend.

The final private v6 receipt has SHA-256
`cafb3852e6fd69b29fb035b5685a7e8b677ba7b83db87dec539d322b2c4e5ebc`,
at unchanged commit `7e43491210d34a386e2bc14aa7c8b0d96e13b282` and tree
`cdae48068d27beb82e2c90d3e2c9e98322b5fc91`. The closeout recorded seven
synthetic cases, 16 demo tests, and 169 focused existing tests. These are dated
receipts, not checks rerun during recovery, live outage qualification, historical
as-of qualification, broad eligibility, performance, or recommendation evidence.

## Exception that must remain visible

Independent functional/domain review passed. Security/privacy/provenance review
verified the final v6 artifacts but withdrew its clean privacy pass because an
earlier inspection output had entered Codex context with a pivot price and
nested calculation metadata outside the approved narrow projection. The record
does not report a known credential value, provider body, or complete raw OHLC
bar exposure; that limited statement does not erase the deviation.

After the owner delegated the presented closeout choice to the coordinator,
the coordinator selected a documented exception for this historical run only.
The original disclosure acceptance checkbox remains unchecked. The issue and
milestone were closed; no source change or PR was part of that operational
closeout. Project-board fields were unverified because the then-current token
lacked `read:project`.

Future disclosure remains governed by the current source and workflow contracts.
This exception does not authorize broader output disclosure, and in particular
does not override the owner-private V3/V4 restrictions in
[the current agent workflow](../workflows/agent-current-research-run.md).

## Recovery provenance

Hindsight bank `pi-projects`, document
`codex-20260923-sprint20-real-stock-v1`, content SHA-256
`514fec638db12d7e6d9bceba3baff746a75565ed237152032dec39a65daf7c8a`.
The GitHub closeout above corroborates the exception and final receipt. Private
receipts and market payloads were not reopened or reproduced for this import.
