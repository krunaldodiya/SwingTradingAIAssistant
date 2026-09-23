# Agent-initiated current research run

Sprint 22 [issue #213](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/213) adds a bounded factual input for an AI agent. The agent chooses one to ten explicit NSE equity symbols, invokes the installed local CLI, and receives one compact JSON dossier per stock. It need not formulate a human question or pick a price-direction criterion.

```sh
mkdir -m 700 -p "$HOME/SwingTradingAIAssistantData/agent-research"
market-data research-run-current \
  --contract-version v2 \
  --symbol PNB --symbol RELIANCE --symbol TCS \
  --storage-root "$HOME/SwingTradingAIAssistantData/agent-research" \
  --output json
```

The command may contact the existing official calendar and mapping sources and BharatStock price source. Market-data revisions remain under the absolute private **host** storage root. It emits JSON to stdout but does not publish it to an AI service or write a report file. Give an agent only the projected JSON within the owner's approved disclosure scope; keep credentials, private storage, source payloads and raw bars local.

`--contract-version v2` first asks BharatStock for the latest officially
completed session S and its preceding 20 sessions. If S's completed bar is
explicitly missing, it tries one 21-session window ending at the immediately
previous official session P. It first rechecks the missing bar after the wider
requests under the original deadline; conflicting or invalid latest-session
evidence or a changed official schedule blocks the fallback. Only an exact
missing-final-bar result from the versioned capture path qualifies; an ambiguous
incomplete-history result does not. All three price/structure features shift together
only when P's complete window is admitted. Each stock reports S, its selected
evidence end date, a zero- or one-session lag, and the fallback outcome. Mixed
S/P dates make the batch `jointly_comparable=false`. Incomplete P evidence
leaves the selected dossier unset while the separate `previous_window_attempt`
field retains any independently admitted P facts and precise feature-level
insufficiency. Missing P, conflicting evidence, shared provider failure and
deadline failure do not trigger an older search or a substitute provider. See the [September 23 decision
note](../notes/2026-09-23-swing-completed-session-fallback.md). Omitting the
option (or requesting `v1`) preserves the original S-only agent contract.

Each member has the canonical ISIN/exchange/effective symbol, its own selection and evidence-known times, price basis, research status, and admitted feature-level outcomes. A feature fact is present only when it is observed, supported and comparable. Candle direction, close versus previous close, and structure state/trend are deterministic facts, with source/result identities and completed session for citation. `null` plus a typed availability/support/comparability/reason means that feature cannot be used to support a claim. Three context features are explicitly `NOT_ATTEMPTED`; the command does not acquire event, market-regime or Industry context. An overall V2 `NOT_READY` status does not erase independently admitted feature facts.

If acquisition ends before any packet is available, all three price/structure features carry the terminal research status and code, with `null` facts and source identities. The three context entries still say `NOT_ATTEMPTED`. This keeps a failed member explicit without claiming that any market fact was observed.

`jointly_comparable` is true only if all three features for every member are observed on the same completed session with the same price basis, schedule identity and source profile. It does not claim a common acquisition cutoff, index membership or simultaneous market snapshot. Exit 0 means every requested price/structure fact is projected, exit 1 means at least one is unavailable, and exit 2 means input rejection or internal failure. No partial JSON is emitted for an internal failure. Explain missing facts and different selection times rather than manufacturing a conclusion.

This is an explicit-list current research path, not the default point-in-time Nifty 100 selector or a 100-stock capacity claim. It does not establish trade eligibility, rank stocks, issue BUY/HOLD/EXIT/NO_TRADE signals or validate a strategy. Those steps require separately governed point-in-time cohort, capacity, risk and historical/prospective validation evidence.
