# Sprint 49: exact selection and whole-list current research

October 7, 2026. [Issue #285](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/285),
milestone 41, private Delivery Project. Owner/risk owner Krunal Dodiya; R3.
[Plan 62](../plans/62-exact-selection-whole-list-research.md) freezes all twelve
acceptance rows before implementation and governs Plan61 G02 only.
Base `d301db57358aa5aef3873b64c1282dd3148e8cb2` follows complete Sprint48 closeout.
Root is sole writer/coordinator; the persistent Goal is active. The numbered
context is verified in the same saved project through supported independent
thread listing; no separate user-owned chat is created.

## Working behavior and honest use boundary

New installed SDK `run_setup_research_selection_current` and public
`market-data setup-research-selection` orchestrate unchanged G01 reports in
ordered chunks of at most ten. Explicit lists support 1–100 distinct symbols.
Default selection reads the exact retained Nifty100 capture request and official
three-witness selection evidence. Every admitted/unknown member remains; global
canonical collisions or selected-mapping conflicts are terminal. Each member
has one serial integrated producer call and its existing same-observation facts.

The outer report preserves original child reports and their identities, binds
the complete requested/actual canonical order and default selector knowledge,
and evaluates existing descriptive comparison predicates across every chunk.
Independently acquired observations have no shared acquisition cutoff. No batch
metric is averaged; no score, ranking, eligibility or recommendation is added.
Final JSON plus LF is buffered under 11 MiB, with original 1 MiB child limits.
Later failure/interruption emits no partial report; explicit retry revalidates
evidence and uses the existing producer's cache behavior.

Default means **CURRENT_AT_RETRIEVAL**, not today's discovered membership or
historical membership before witness retrieval. It requires an existing retained
selection, and never acquires, repairs or replaces unavailable witnesses.
Witness retrieval <= capture cutoff <= trusted invocation time; that cutoff
does not turn fresh research into historical evidence. NSE-derived information
stays owner-private; no external AI destination/disclosure is authorized here.

After installing the qualified release and preparing an existing absolute
owner-private research directory, an explicit invocation is:

```sh
market-data setup-research-selection --symbol PNB --symbol RELIANCE \
  --storage-root /ABSOLUTE/OWNER_PRIVATE_RESEARCH --output json
```

For default Nifty100, first use the existing approved
`current-nifty100-bharatstock-capture` workflow to retain its canonical current
capture request and official selection witnesses. This research command does
not perform that acquisition or create a request on the owner's behalf:

```sh
market-data setup-research-selection \
  --selection-request-file /ABSOLUTE/PRIVATE/current-capture-request.json \
  --selection-root /ABSOLUTE/PRIVATE/selection-store \
  --storage-root /ABSOLUTE/OWNER_PRIVATE_RESEARCH --output json
```

Request files must meet the existing absolute no-follow owner/private regular-
file admission and canonical current V3 format. Selector and research directories
can coincide: the selection reader releases its lease before research begins.
Missing/unsafe/corrupt selection evidence produces `selection_unavailable`,
exit1, no report and no producer effects. Available complete reports exit0;
reports retaining unknown facts exit1. Invalid/terminal/interrupted execution
exits2 with fixed sanitized diagnostics. Availability/MATCH is not trade approval.

## Verification checkpoint

Actual public explicit11 and default100 RED checks preceded implementation.
The explicit 1/10/11/100 working paths and default100 same-root path were
observed with the real V2 producer and fixed synthetic collaborators. Adversarial
checks cover input limits, exact retained evidence, temporal equality/plus-one,
cross-chunk canonical aliases, default mapping conflict plus missing members,
global session mismatch despite locally comparable child reports, interruption/
retry, concurrent invocation isolation and actual 11 MiB exact/plus-one buffering.
Fixture failures and the command file-path correction remain retained separately.

The nine source-mode demonstrations and eight verifier contract checks pass,
including deliberate incomplete/forged receipt rejection. They prepare hosted
clean installed-wheel qualification; they do not prove installed/live-source
execution. All affected source manifests, including the closed generic market-
data inventory, are mechanically refreshed after formatting. Current-source
statics pass (format, lint, types and unused-code checks). The main focused run
recorded 58 passes and one failure: a comparison-demo child imported the old
owner checkout through the shared environment. With this worktree's source
explicitly selected, all five comparison checks plus three affected boundary/
preflight checks pass (8 total). The failed run is retained; it is not a full
acceptance result. Earlier focused checks passed all 46 new SDK/CLI cases and
eight source-mode qualifier contract checks. The final source-mode qualifier
checks also pass (8/8) after the output-limitations wording change. Full repository
coverage and clean installed artifacts remain hosted prerequisites.

Both fresh independent exact committed R3 reviews, full selected hosted tests/
87% coverage/build/installed/native/prior-wheel/GitGuardian, exact normal merge,
main admission, private publication/fresh pull and tracker/evidence closeout
remain pending. Standing October7 owner approval covers routine in-scope hosted
checks and normal merge after gates. Fresh allowance and account Actions/Packages
$0 paid budgets with StopYes still precede ready CI; no blind rerun, local heavy
fallback, new paid capacity/settings/access/visibility/bypass or deletion.

**G02 remains open; 11 finite outcome gaps remain.** Only complete G02 delivery
reduces them to ten. G08 real-source/workflow, G09 AI/historical qualification,
complete product/signal-phase claims, G03–G12, five Future issues, Windows and
Issue250 retain their separate boundaries. This count is not a sprint forecast.

Evidence: `/home/krunaldodiya/Documents/Codex/2026-10-07/sprint49-evidence`.
Workspace: `/home/krunaldodiya/.codex/worktrees/sprint49-whole-list-research/SwingTradingAIAssistant`.
