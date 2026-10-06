# Same-pair range-aware research handoff

[Plan57](../plans/57-range-aware-setup-interpretation.md) adds SDK
`assemble_setup_evidence_v3(previous, current)` and
`check_setup_interpretation_v3(previous, current, response)`. Both receive two
typed admitted CURRENT_STRUCTURE observations. A caller cannot substitute a
precomputed JSON bundle. The unchanged four full v2 components are retained;
`level_range` adds the unchanged Plan56 report on the same pair.

The separate injected commands are `setup-evidence-v3` and
`setup-interpretation-v3`; these Python adapters require the existing authorized
observation service, and are not new global `market-data` subcommands. Supply
`--symbol`, absolute `--storage-root`, exact UTC `--previous-selection-time`
and `--current-selection-time`, and `--output json`. Interpretation also needs
an absolute owner-private `--interpretation-file`, single-link regular file,
1..65536bytes. The unchanged reader rejects links, unsafe mode/owner, changing
files and malformed responses before acquiring observations.

The exact response schema is `external-setup-interpretation-request@v3` with
`evidence_identity_sha256`, caller `disposition` (RESEARCH_ONLY or NO_TRADE),
`explanation` (nonblank bounded2048characters), and `facts`. Exactly five
claims are continuity/invalidation/age/level/level_range. All require exact
`result_identity_sha256` and `status`; age additionally has
`completed_sessions_elapsed`, level has `relation`, range has `range_relation`
(CONTAINS_LEVEL/ENTIRELY_ABOVE/ENTIRELY_BELOW or null). Copy structured values
from the admitted v3 bundle without coercion. Any false binding fails closed.
Old v1/v2 schemas remain unchanged and are rejected by the v3 checker.

Success verifies STRUCTURED_BINDING_ONLY. Explanation truth, model authorship,
recommendation, eligibility and effectiveness are not assessed. Low/high
containment proves no exact traded tick, successful retest, confirmation,
validity or eligibility. Close, range, invalidation and age remain independent.

Exit0 means five components completed under their existing contracts; exit1
is a successful inconclusive report; neither authorizes a trade. Request/file/
parser error exits2 `request_invalid`, no acquisition/output. Observation,
admission, source, binding, serialization/bound or interruption error exits2
with fixed `setup_evidence_failed`/`setup_interpretation_failed`, empty stdout.
One response read, two serial selector-bound acquisitions and one composition/
check; no automatic retry, extra provider/model/write authority. Complete
canonical sorted compact JSON plus LF is bounded1MiB before stdout writes;
OS stdout write failure is outside transaction guarantees.

The guarded synthetic example
`examples/causal_setup_range_interpretation_v3_demo.py --scenario contains`
exercises actual admitted SDK and both injected CLIs; additional cases above,
below, low-equal, high-equal, invalidated, replay, unknown, no-trade and
false-claim cover boundaries and false range rejection. It uses fixed historical
synthetic observations and caller-authored prose, not current market data or a
model evaluation. Source execution is focused feedback, not installed acceptance.

The Linux receipt adds `installed_setup_range_interpretation_v3` while retaining
all eight old maps. Isolated installed `-I` execution verifies source paths and
regenerates original v1/v2/Plan54/Plan56 reports. Owner-private temporary
qualification reference files bind full nested canonical bytes, witnesses and
upstream identities; changing and resealing a candidate cannot supply those
independent references. This creates no application persistence mechanism.
Installed/nativeOCI/full hosted and published main evidence remains governed
by the sprint's live Issue and complete release gates.
