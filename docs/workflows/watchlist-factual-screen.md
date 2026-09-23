# Explicit watchlist factual screen

Issue: [#211](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/211). This first Sprint 21 slice compares admitted current price facts for an explicitly supplied list. It does not discover or verify watchlist or index membership.

Run the installed local CLI with 2–10 distinct NSE equity symbols and an absolute owner-private host storage root:

```sh
market-data watchlist-screen-current \
  --symbol PNB --symbol RELIANCE --symbol TCS \
  --storage-root "$HOME/SwingTradingAIAssistantData/watchlist-research" \
  --close-direction UP --output json
```

Create the dedicated private root first with `mkdir -m 700 -p "$HOME/SwingTradingAIAssistantData/watchlist-research"`. The command may contact the existing official calendar/mapping and BharatStock price sources, even without a refresh flag. Its `PRICE_BEHAVIOR` calls are sequential independent observations. Use it only with the existing source authorization and local credential setup. Data remains under the specified host root; the command does not publish a file or send output to an assistant by itself.

The JSON keeps requested order and reports a distinct identity for the requested symbols and the complete observed canonical list. Its `runtime_code_identity_sha256` binds the screen and CLI code that produced the verdicts. For each stock, `MATCH` means an admitted, supported, comparable close-versus-previous-close direction equals the selected criterion; `NO_MATCH` means a different admitted direction; `UNKNOWN` means this fact cannot support a verdict. Read `feature_availability`, `feature_support`, `feature_comparability`, `reason`, the actual completed `session`, price basis, source profile, timestamps and evidence identities before explaining a row. Exit 0 means all rows have a factual verdict, exit 1 means at least one is unknown, and exit 2 means malformed input or an internal failure. No partial JSON is emitted for an internal failure.

`jointly_comparable` is true only when every member has a supported fact for the same completed session, price basis, schedule identity and source profile. Each member still has its own selection and evidence-knowledge time; this output does not claim a common acquisition cutoff. A failure for one stock does not erase another stock's admitted fact. The projection excludes raw OHLCV, provider bodies, credentials, distance/price values and private storage paths. If a coding assistant explains the result, give it only this projected JSON within the owner's approved disclosure scope and cite each member's fact/source/result identities and times. Do not treat any verdict as stock eligibility, a trade recommendation, a ranking or a score.
