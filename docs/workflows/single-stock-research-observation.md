# Observed synthetic assistant explanation

Issue #203; observed 2026-09-22 in Codex using the repository's demo and real V2
CLI service/serializer. This is one assistant's response to synthetic facts,
not an automated model-quality score or evidence of universal reliability.
No private capture, credential, provider call or live market observation was used.

## Reproduce the tool observations

Run the commands in [the workflow](single-stock-research.md). All observations
below use synthetic canonical PNB / INE160A01022 / NSE and
BHARATSTOCK_SOURCE_REPORTED_OHLC. Simulation selection and evidence-known time
for the complete results are 2026-08-26T04:15:00Z; fact session is 2026-08-25.
These dates describe the simulation, not present-day PNB.

The complete PRICE_BEHAVIOR packet result identity is
`03b7175c3a06c95c778b88ee4be6e7f2edb668eaf8cf7e7618ec327c96228c6a`;
complete CURRENT_STRUCTURE is
`745b23ece9459697f45ad4e4aaee5dfe3a34d61755fe3345df8de516ca5d59e5`.
For each, the JSON field is `packet.result_identity_sha256`. They remain separate
question results; this example creates no combined packet.

## Assistant explanation from the supplied complete results

**Supplied price facts:** The synthetic completed candle points UP, with supplied
body size 5 and range size 20 (`packet.members[0].features[0].fact.candle_direction`,
`.body_size`, `.range_size` in the PRICE_BEHAVIOR result above). Its close is UP
against the previous completed session, with supplied distance 5
(`packet.members[0].features[1].fact.close_vs_previous_close` and
`.close_to_previous_close_distance`). The previous session is 2026-08-24 and the
fact session2026-08-25, from that same fact's `previous_session` and `session`.
These numbers are copied from the tool's facts, not computed by the assistant.

**Price interpretation:** The tool supports saying the simulated candle closed
above its open and above the previous session's close. This does not establish
continuation, an entry rule, or a trading opportunity.

**Separate structure observation:** The CURRENT_STRUCTURE result is READY but
its supplied `packet.members[0].features[0].fact.calculation.structure_state`
and `.trend` both say INSUFFICIENT_STRUCTURE. I therefore cannot describe an
established upward or downward structure. Successful calculation and sufficient
input history do not guarantee an established structure.

**Limitations:** These are synthetic examples. Neither question establishes
trade eligibility, recommendation quality or historical point-in-time
qualification. The optional event, Market Regime and Industry context has not
been acquired by this command. The result's `limitations` states these boundaries.

## Assistant explanations of limitation cases

| Tool observation | Assistant response supported by that observation |
| --- | --- |
| partial PRICE_BEHAVIOR: READY; geometry and previous-close facts OBSERVED | I can explain those price facts with the same citations, separately from Structure. |
| partial CURRENT_STRUCTURE: NOT_READY; feature reason HISTORY_INCOMPLETE and null fact | The required structure history is incomplete. I cannot infer a trend from price behaviour or manufacture a structure result. |
| stale PRICE_BEHAVIOR: NOT_READY; geometry EMPTY_HISTORY and comparison HISTORY_INCOMPLETE, both null facts | The requested latest completed bar is missing. Older bars do not establish current price behaviour. |
| conflicting: UNAVAILABLE / mapping / MAPPING_AMBIGUOUS; packet null | PNB maps ambiguously in this simulation. I stop the stock analysis rather than choose an identity. |
| malformed: exit 2, request_invalid, no JSON | The request was rejected. There is no research result to explain. |
| complete INTEGRATED_CURRENT_RESEARCH: NOT_READY with price features OBSERVED and context_outcomes NOT_ATTEMPTED | I can explain its independently admitted price facts, but integrated context is not established; missing context is not a neutral result. |

These statements were checked against observed stdout and exit status in all
15 combinations of the five scenarios and three question profiles. The fixed
fixture response digests are simulation identifiers, not authentic HTTP evidence.
The deterministic regression suite separately checks command behavior; this
written response is qualitative evidence, not a test of every future assistant.

## Remaining sprint scope

#204 must freeze supported observation versions/bounds, deterministic comparison,
identity/basis/session/knowledge-time compatibility and explicit non-comparable
outcomes. It must not infer a prior snapshot from the previous-close fact. No
comparison implementation, live demonstration, new context acquisition, board
update or release is claimed here.
