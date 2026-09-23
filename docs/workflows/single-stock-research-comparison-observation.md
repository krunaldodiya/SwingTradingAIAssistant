# Observed synthetic comparison explanation

Issue #204; observed 2026-09-23 in Codex using the repository's fixed demo and
actual comparison CLI adapter. This is a qualitative response to synthetic
facts, not current PNB research or a model-wide reliability result.

## Supplied changes

The comparison is `COMPARABLE` for synthetic PNB / INE160A01022 / NSE on
`BHARATSTOCK_SOURCE_REPORTED_OHLC`. The previous selection is
2026-08-26T04:15:00Z with completed session 2026-08-25; the current selection is
2026-08-27T04:15:00Z with completed session 2026-08-26. Each evidence-known
time equals its selection time.

The supplied candle body changes from 5 to 8, with a tool-computed delta of 3
(`facts[path=CANDLE_GEOMETRY.body_size]`). The upper wick changes from 5 to 2,
delta -3 (`CANDLE_GEOMETRY.upper_wick_size`). Range stays 20, delta 0
(`CANDLE_GEOMETRY.range_size`), while direction stays UP
(`CANDLE_GEOMETRY.candle_direction`). These values and deltas are copied from
the comparison; the assistant did not recompute them from OHLC.

The complete comparison result identity is
`fb3e72758eef11ddc324fd82569c9020a0da3961c69486eb24cf7ad07cfaa813`.
Its previous/current observation identities are respectively
`2c5c5b15e2763daea51052a77ed5ac2e41aaa4044abd9579b3fdf81d5095037e`
and `910316da68a8f51323796f6be562711f4229d591c2b169c5a014f4d469942ad1`.

## Interpretation

The supplied facts support saying that the synthetic current candle has a
larger body and smaller upper wick than the explicitly selected previous
observation, while its total range and upward direction are unchanged. The
comparison does not establish continuation, quality, eligibility or an entry.

In the `newly-unavailable` scenario, previous-close comparison facts have state
`NEWLY_UNAVAILABLE`: the previous observation supplies them and the current one
has insufficient sessions. I report that loss of evidence instead of describing
the values as unchanged or inferring them from candle geometry.

The CURRENT_STRUCTURE command compares only supplied `structure_state` and
`trend`. In this fixture both remain `INSUFFICIENT_STRUCTURE`; a successful
comparison does not create an established trend.

## Limitations

Both observations use fixed synthetic sources and fresh temporary storage. No
provider integration, private-data handling, historical qualification or live
market claim was tested. The result compares admitted facts only and supplies
no trade recommendation, score, entry, exit or position size. The network guard
is a Python audit boundary for this demo, not a general native-code sandbox.
