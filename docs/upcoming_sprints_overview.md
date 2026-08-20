# Upcoming Sprints Overview

This is the owner-level **current/live/realtime first** dependency sequence. It
is a minimum dependency plan, not authorization, delivery promise, acquisition
plan, publication claim, or evidence that any sprint completed. Each sprint
requires its own accepted contract, focused evidence, exact reviewed revision,
and applicable repository/hosted gates. Failed or insufficient evidence requires
a replacement sprint rather than automatic progression.

## Shared lane rule

Current/live/realtime work starts with current supplied-cohort price/volume,
then current Market Regime, Sector Analysis, news/events, and an integrated
current packet. The deterministic tool supplies facts only; an external AI may
produce explainable research or `NO_TRADE`, never a tool-invented autonomous
signal, recommendation, position size, entry/exit, or order.

Historical/backtest work is deferred, not deleted. It uses an explicit supplied
cohort and versioned OHLCV revision, makes no inferred historical index
membership claim, identifies `FIXED_COHORT_RETROSPECTIVE`, and discloses
selection/survivorship limits. Historical news, events, and sector inputs are
deferred/not-yet-evaluated, not permanently removed or silently neutral.

Every live fact is immutably archived from now with `published_at`, `known_at`,
source, revision, and affected identities. A per-feature/instrument/interval
ledger records only `AVAILABLE`, `NOT_PUBLISHED`, `NOT_RETAINED`, `SOURCE_GAP`,
`STALE`, `CONFLICTED`, or `UNLICENSED`. Coverage/windows are predeclared; no
later fact substitutes for unavailable history and unavailable dates are never
dropped.
Point-in-time backtests and forward tests use only evidence available by their
historical cutoff. An unavailable factor is explicitly unavailable/not applied;
it is never fabricated or backfilled from later evidence, and it does not block
unrelated available-feature research. The current/live contract may instead
require a factor as a whole-result gate for the specific claim it makes.


| Sprint | Tracker and lifecycle | Atomic outcome | Minimum dependency and gate | Explicit non-goals |
| --- | --- | --- | --- | --- |
| 10 | [#121](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/121) — current; High priority/risk | Current supplied-cohort `market-data` foundation: bounded current price/volume facts for 1–50 Nifty 50 identities and immutable archive records. | Canonical cohort identity/selection SHA; retained instrument resolution; latest completed daily OHLCV and optional `PARTIAL_CURRENT_SESSION`; provenance/availability ledger; whole-cohort insufficiency; no effect before admission. | Historical/backtest implementation, Market Regime, sectors, news/events, signals, recommendations, entries/exits, position sizing, orders. |
| 11 | [#116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116) — Todo; High priority/risk; blocked by [#125](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/125) | Current Market Regime over admitted archived current facts, after a provider-limited raw-close corporate-action screen. | First merge standalone [Plan 21](plans/21-upstox-current-corporate-action-screen-contract.md): its exact retained schedule binding must derive S0/S20 as 20 completed positions and each member's snapshot must be retained from the derived S20 close through cutoff with no supported in-window action. Then rebase to a current-regime v2 cutover that accepts only its successful report before direct S0/S20 breadth. The screen state remains nonexhaustive, not authoritative no-break proof; screen insufficiency is a whole-result gate only for that consuming current/live claim. | Historical membership reconstruction, historical/backtest validation, sectors, news/events, recommendation, order, adjustment, provider/NSE acquisition or automation. |
| 12 | [#117](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/117) — Todo; High priority/risk | Current Sector Analysis and Sector Participation with immutable current sector snapshots. | Sprints 10–11 current facts; approved current sector evidence/identity bindings; sector availability-ledger entries. | Historical taxonomy reconstruction/backfill, historical validation, recommendation, order. |
| 13 | [#118](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/118) — Todo; High priority/risk | Current news and event evidence with bounded fresh-input integration and immutable archive. | Current freshness/provenance/availability rules; no silent neutralization of absence. | Historical news/event backfill, historical validation, forecast, recommendation, order. |
| 14 | [#119](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/119) — Todo; High priority/risk | Integrated current packet binding price/volume, Market Regime, sector, news, events, and their archive identities for external-AI explainable research or `NO_TRADE`. | Exact Sprint 10–13 gates and current contracts. | Autonomous tool signal/recommendation, broker order, execution, historical-context substitution, claim of effectiveness. |
| 15 | [#120](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/120) — Todo; High priority/risk | Deferred fixed-cohort historical OHLCV store. | Current/live Sprints 10–14 usable; explicit cohort, versioned OHLCV revision, and predeclared coverage/windows. | Inferred index membership, historical news/event/sector neutralization, Market Structure, recommendation, order. |
| 16 | [#122](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/122) — Todo; High priority/risk | Capability-aware historical validation and pre-structure gate. | Sprint 15 store; study profile (`OHLCV_ONLY`, `OHLCV_PLUS_SECTOR`, or `OHLCV_PLUS_NEWS_EVENTS`); required availability-ledger entries; development/walk-forward/out-of-sample/untouched-test separation; identities and independent review. | Market Structure implementation, Price Action, Liquidity/SMC, recommendation, broker execution, guaranteed outcomes. |

## Market Structure boundary

Market Structure is **earliest Sprint 17** and is not specified or started by
this overview. Sprint 16 returns only `APPROVED_TO_START_MARKET_STRUCTURE` or
`BLOCKED` with exact reasons; failure adds a replacement sprint. This is a gate,
not a promise.

## Deferred and superseded historical records

Issue #121 is the active current foundation. Issues #111 and #115 are **closed /
not planned** with no published implementation. Plans 12 and 17 retain their
original evidence and conclusions as historical records; deferred Plan 18 is
linked to #120/#122. None are declared wrong at the time.

The former contemplated official-inquiry content SHA-256
`a2d762cd93dfca56d5623e260816c1aee0a6ae2a9a400097cc6f2d51c77f6412` and
authorization-payload SHA-256
`84797b9c424aa6da36d46b1b516f3cbe08d8205801d296953a5edf474d2ffe85` were
revoked before send. No inquiry email, provider contact, provider call,
credential use, or acquisition occurred. These are not Plan 11's historical
public-page research receipt hashes.
