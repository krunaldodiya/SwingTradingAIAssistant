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

Each member has the canonical ISIN/exchange/effective symbol, its own selection and evidence-known times, price basis, research status, and admitted feature-level outcomes. A feature fact is present only when it is observed, supported and comparable. Candle direction, close versus previous close, and structure state/trend are deterministic facts, with source/result identities and completed session for citation. `null` plus a typed availability/support/comparability/reason means that feature cannot be used to support a claim. In V1 and V2, three context features are explicitly `NOT_ATTEMPTED`; those versions do not acquire event, market-regime or Industry context. An overall V2 `NOT_READY` status does not erase independently admitted feature facts.

If acquisition ends before any packet is available, all three price/structure features carry the terminal research status and code, with `null` facts and source identities. The three context entries still say `NOT_ATTEMPTED`. This keeps a failed member explicit without claiming that any market fact was observed.

`jointly_comparable` is true only if all three features for every member are observed on the same completed session with the same price basis, schedule identity and source profile. It does not claim a common acquisition cutoff, index membership or simultaneous market snapshot. Exit 0 means every requested price/structure fact is projected, exit 1 means at least one is unavailable, and exit 2 means input rejection or internal failure. No partial JSON is emitted for an internal failure. Explain missing facts and different selection times rather than manufacturing a conclusion.

This is an explicit-list current research path, not the default point-in-time Nifty 100 selector or a 100-stock capacity claim. It does not establish trade eligibility, rank stocks, issue BUY/HOLD/EXIT/NO_TRADE signals or validate a strategy. Those steps require separately governed point-in-time cohort, capacity, risk and historical/prospective validation evidence.


## Optional current event context (V3)

Use `--contract-version v3` on the same command to add official NSE notice
context. V3 keeps V2's price selection, one-session fallback, comparability and
price-based exit codes. It validates the same one-to-ten unique explicit symbols
before effects. For a batch with current retained mappings it initializes the
fixed NSE announcements page and downloads one unfiltered Equity `1D` CSV for
the previous/current IST dates. It does not fetch attachments, Industry or
Market Regime context, retry the source, or substitute another provider.

Each member adds `event_context`: admitted notice count, availability/support,
reason, source-observation and retention times, and source/mapping/result/retention
identities. A conflict remains local to that member. `NO_MATCHING_NOTICE_IN_SNAPSHOT`
with count zero means only no matching notice in that admitted snapshot; it does
not establish no event risk or source completeness. Unavailable or unsupported
context has a null count. Notice text, publisher timestamp strings, attachment
URLs, raw CSV, credentials, cookies and storage paths are excluded.

`event_observation` has its own selection time and 120-second cutoff after price
work. These times do not rewrite the original price window or turn lagged price
facts into current-session facts. Publisher timezone is unknown and reported as
null. Current mapping validity and exact retained canonical identity are checked
before notices are attached. Event evidence is retained privately before return.
Closed source failures preserve independent price facts; unsafe or held storage,
lost authority, corruption, unexpected internal errors and interruption prevent
partial JSON publication. A new command after interruption can reuse completed
immutable retention when its exact request and observation identities match.

**Keep all V3 output owner-private. Even redacted NSE-derived counts, status and
provenance may not be sent to hosted AI services, published or redistributed.**
This opt-in is bounded personal/noncommercial local research under the existing
source-use contract, not a new disclosure permission. See
[Plan 37](../plans/37-agent-current-event-notice-context-contract.md).

## Optional comparison-cohort context (V4)

V4 adds one separately observed Market Regime and Industry context to the V3
stock dossiers. Choose 1–10 research stocks and a separate ordered comparison
list of 2–50 stocks. The lists may overlap or differ; the command never silently
unites them, substitutes a member or reduces the comparison denominator.
A caller description does not establish index membership or market-wide breadth.

With an existing private dated-mapping document:

```sh
market-data research-run-current \
  --contract-version v4 \
  --symbol PNB \
  --context-symbol PNB --context-symbol TCS \
  --context-purpose "My explicit comparison group" \
  --context-mappings-file /absolute/private/cohort-mappings.json \
  --storage-root "$HOME/SwingTradingAIAssistantData/agent-research" \
  --output json
```

The mapping file must be an absolute, owner-private regular file, with no
symlink or hardlink, and at most 64 KiB. The closed JSON contract is
`agent-current-cohort-mappings@v1`: its `members` array must match the requested
context symbols exactly and in order. Each member includes canonical identity,
original dated validity, BharatStock mapping identity and provider revision.
The exact required fields and validation rules are in
[Plan 38's dated-input contract](../plans/38-agent-current-cohort-context-contract.md#accepted-dated-mapping-input-supplement--2026-09-27).
Duplicate or unknown keys, invalid dates, a wrong mapping digest and mismatched
members reject the command before acquisition. The digest follows the existing
`mapping_identity_v3` function; it is not an arbitrary label.

Use supported dated mapping declarations. Today's symbol lookup does not prove
past identity: do not manufacture historical start dates to make a request pass.
The output labels mapping authority `OWNER_SUPPLIED`, preserves the supplied
revision and intervals, and fingerprints the input bytes. It cross-checks current
retained identities and requires the declared intervals to cover all 21 selected
completed sessions. These checks do not independently verify a caller's
historical assertion. This workflow does not acquire historical mapping evidence
automatically or establish historical index membership.

Omitting `--context-mappings-file` leaves cohort facts null with
`MAPPING_EVIDENCE_NOT_PROVIDED`, while independent V3 stock research continues.
An explicitly supplied unreadable, unsafe or malformed file rejects the command;
it is not treated as omission. Context options are rejected by V1–V3.

The batch `cohort_context` records the requested group, caller purpose, identity,
source profile, times, availability and admitted aggregate facts. Context reuses
Upstox raw completed daily data with existing BharatStock direction-comparability
evidence. Stock dossiers use their existing source profile and selection times.
Equal end dates do not establish joint comparability, and the original
price-only `jointly_comparable` field retains its meaning. Context never shifts
lagged stock prices forward or stitches singleton dossiers into a cohort.

A missing comparison member withholds the whole-cohort aggregate. Unavailable
Industry classification withholds Industry rows while preserving admitted Market
Regime and stock facts. Existing calendar coverage, historical mapping intervals,
source admission and time bounds still apply; supplied mappings alone do not
guarantee observed context. Corrupted retained evidence, unsafe storage,
unexpected errors and interruption remain fatal, with no partial JSON output.
The exit code continues to describe price/structure availability, so exit 0 does
not imply that cohort context is available. Check each context availability and
reason before using a fact.

All V4 output remains owner-private, including aggregate counts, Industry names,
status and provenance. It is not authorized for hosted AI disclosure or
redistribution. V3's event limitation still applies: no matching notice means
only no match in that snapshot, not no event risk or source completeness.
Relative Strength, rankings, trading signals and orders are outside this command.
