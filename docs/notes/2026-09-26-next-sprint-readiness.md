# Next achievable sprint: optional event-notice context

Date: 2026-09-26
Status: **accepted direction**; owner selected “Implement event-notice context
first” on 2026-09-26. Implementation is tracked in
[Sprint 24 issue #220](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/220).
Detailed contract and delivery evidence remain separate from direction approval.

## Context and verified baseline

The owner requested next-sprint planning and implementation after reviewing
documentation, Hindsight and GitHub. This note records the planning result, not
an approved analytical feature, release exception or delivered sprint.

The clean Linux checkout and remote main were checked at
`6dacc026a8a8cb30e94642f31847994ee37c30a6`.
Sprints 20–23 (#210, #211, #213, #215) and Windows validation #208 are closed.
There are no open PRs. The five open issues are future work: #126, #139, #144,
#177 and #178. After the owner's choice, Sprint 24 milestone 16 and issue #220
were created and read back; #220 is open, not delivered.
At the initial planning checkpoint the GitHub Project could not be read because
the CLI credential lacked project scope. Access was subsequently restored with
owner authorization. On resumption, issue #220 was read back as open and its
Project item as **In Progress**; the handoff records High priority, Story and
High risk. Implementation, review and release remain pending.

Both Hindsight banks responded. The canonical project tag and documented legacy
project tag were searched. The Sprint 23 delivery memory agrees with closed
#215 / merged #216 and explicitly separates future context-source composition.
Older memories and stale roadmap paragraphs still describe completed work as
pending; current GitHub and merged contracts govern this decision. The global
September 25 machine record supersedes the earlier uninstall discussion:
development now runs in Ubuntu WSL. No restore or machine cleanup is needed for
this planning task; private evidence availability has not been qualified.

## Recommended outcome

For one to ten explicitly requested stocks, an agent can see whether an admitted
official current notice snapshot contains matching notices, together with its
window, knowledge time and evidence identities, beside the existing completed-
session price dossier. Missing or conflicting notice evidence remains explicit
and does not erase independently admitted price facts.

This is the accepted Sprint 24 direction. It advances the already documented
agent-research programme and #215's separately governed context-composition
follow-up. It introduces no Volume, Relative Strength, ranking or signal.

## Why this slice

`agent-current-research-run.md` and `agent_research_run.py` explicitly leave
EVENT_NOTICES, MARKET_REGIME and INDUSTRY_PARTICIPATION not attempted.
`current_event_notice_v2.py` already supplies body-free per-member projections,
member-local conflicts, retained identities and immutable archive admission.
The current acquisition function bundles events with Industry and calendar
sources. Calling that entire bundle would make optional notices depend on
unrelated sources. A narrowly separated bounded event acquisition path is the
implementation seam to assess and freeze before coding.

The integrated V2 composer already accepts retained producers, but it requires
market context and Industry as well as events. The first slice should therefore
add optional notice context without claiming the full integrated question is
ready or changing the existing composer to accept invented inputs.

## First working slice and acceptance

- Freeze an opt-in successor of the agent dossier. Preserve default V1 and
  explicit V2 output and the existing one-session fallback semantics.
- Use the existing official NSE Equity unfiltered 1D source and exact source-use
  policy. Reuse the source parser, canonical mapping, member isolation and
  owner-private retain-before-return path. No new provider or dependency.
- Validate the bounded explicit stock list before acquisition. Acquire one
  notice snapshot for the batch, not once per stock. Freeze exact request,
  response-size, time and retry bounds by reusing the current source contract;
  do not broaden the window, poll, or fetch attachments.
- Return notice presence/count and body-free timestamps/identities only after
  retained admission. Keep missing, malformed, unavailable and conflicting
  states distinct. `NO_MATCHING_NOTICE_IN_SNAPSHOT` must never mean no event risk
  or complete news coverage.
- State the notice observation window and knowledge time separately from each
  stock's selected price end session. Today's acquired notice must not be
  represented as known at yesterday's cutoff or as synchronized with lagged
  price evidence. Preserve the existing price comparability meaning.
- Optional source failure must preserve admitted price facts. Shared unsafe
  storage, interruption and internal integrity failures must retain their
  existing fail-closed behavior. Freeze exit semantics and bounded failure
  projection explicitly before implementation.
- Keep source text, attachments, raw CSV, cookies, credentials and host paths
  out of the dossier. The existing source-use restrictions still apply;
  redaction alone is not authorization to send NSE-derived material to a
  hosted assistant. No hosted disclosure is part of this sprint.
- Demonstrate positive, no-match, unavailable, malformed, member-conflict,
  canonical mismatch, wrong cutoff/window, lagged-price, limit-plus-one,
  deadline, unsafe-storage and interruption behavior, plus unchanged V1/V2.
  Perform a bounded local smoke only within existing source authority; report
  unavailable external evidence rather than manufacture success.

## Implementation and delivery sequence

1. Record owner direction in a governing Issue using the repository work-item
   form; assign the next sprint only after confirming numbering and Project
   access. Freeze the successor contract and the first-working/later split.
2. Establish one-stock end-to-end acquisition, retention and dossier projection;
   then complete the accepted bounded multi-stock and failure criteria. Reuse
   existing components; stop if the seam needs a new general subsystem.
3. Run focused behavioral checks, stabilize the candidate, and obtain independent
   functional/domain and security/privacy/provenance reviews of exact committed
   bytes. Run applicable full/static/build/installed and hosted gates for runtime
   changes. Record failures and review limits truthfully.
4. Deliver through a reviewed PR under current release controls. Any previous
   #208 branch-protection exception expired and does not authorize this release.
   Verify Issue, milestone, Project and merged revision before closeout.

Risk: **R3** for a public research contract, external acquisition and private
evidence. The repository owner owns product direction and residual-risk
decisions; the coordinator owns implementation and integration; independent
reviewers own their verdicts. Rollback is the unchanged V1/V2 path, with no
deletion or reinterpretation of retained evidence. The proposal has no release
or residual-risk approval.

## Alternatives and later work

| Candidate | Disposition for this proposal | Reason |
| --- | --- | --- |
| Optional event-notice context | Recommended first | A documented missing dossier dimension with existing admitted producers. |
| Market Regime / Industry context | Later, separately bounded | Requires a meaningful explicit context cohort and exact same-pass/source/temporal composition; a requested single stock is not market breadth. |
| One Volume fact | Deferred | Plan 34 requires a demonstrated unmet question, baseline evaluation and an accepted formula; none is inferred from popularity. |
| #177 backup and recovery automation | Future | Valuable operational work, but full captured-evidence recovery/key/off-device requirements form a separate outcome. Current backup completeness is unverified. |
| #178 fundamentals | Future | Needs a concrete question plus source, freshness and provenance qualification. |
| #139 point-in-time backfill | Future | Larger historical-evidence contract; current acquisition cannot manufacture prior knowledge. |
| #144 dual-source Upstox/yfinance | Re-evaluate before scheduling | The later BharatStock migration retired active Yahoo acquisition; the old proposal is not fresh source authority. |
| #126 reusable PyPI package | Lower priority | Packaging/publication is separate from completing the current research experience. |

Default Nifty 100 selection, 100-stock scale, notice sentiment, general news,
notice narratives, strategy rules, recommendations, holdings, monitoring and
orders are outside this slice. No delivery date is promised before readiness.

## Open decisions and evidence limits

- Owner choice resolved: implement the event-notice slice first (#220).
- Project access restored; issue #220 and its In Progress Project status were
  revalidated on 2026-09-26. The previous protection exception remains expired.
  A fresh protection read returned HTTP 403 (GitHub plan restriction); any
  required release decision follows preparation of a reviewed passing candidate.
- Before implementation, freeze successor schema, independent acquisition seam,
  temporal and failure rules, and applicable source-use boundary in the Issue.
- Tests, live provider calls and runtime changes were not performed during this
  documentation-only planning pass. Its verification is `git diff --check`.
  Subsequent implementation and verification are recorded in #220.

## References

- [Agent research workflow](../workflows/agent-current-research-run.md)
- [Sprint 23 issue #215](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/215)
- [Sprint 22 issue #213](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/213)
- [September 22 planning direction](2026-09-22-next-sprint-and-linux-handoff.md)
- [Plan 25 event contract](../plans/25-current-supplied-cohort-event-notice-contract.md)
- [Plan 27 source-use boundary](../plans/27-current-same-pass-market-regime-contract.md#source-use-and-consumer-boundary)
- [Plan 34 admission gate](../plans/34-swing-research-feature-map.md)
- [Mandatory project instructions](../mandatory-agent-instructions.md)

## Resumed implementation assignment — 2026-09-26

The actual checkout is `/home/krunaldodiya/WorkSpace/Code/SwingTradingAIAssistant`,
on `codex/sprint24-planning`, preserving planning commit `11f5871` and both draft
files. The registered `/mnt/d` path is stale. Python 3.11 validation uses
`/tmp/sprint24-validation-venv`; the old Python 3.14 environment is not the test
environment. Both Hindsight banks recalled context successfully. The prior
retain operation for `sprint24-event-notice-context-20260926` is still pending;
memory persistence is not confirmed. Current Issue and repository authority
govern over older memories and dated roadmap status.

Plan 37 freezes the additive one-stock path followed by the accepted 1–10-member
batch, temporal, failure and compatibility matrix. Reusing Event V2 supplies
missing notice context without another source or research calculation; the
main risks are private-data disclosure, mismatched canonical identities and
false temporal alignment. The smallest adequate option is a V3 wrapper of the
existing V2 price dossier plus the existing event producer: **accepted** within
#220, with no extra analytical module.

Routing: one implementation agent uses inherited Codex model/effort (host model
telemetry unavailable), appropriate for the bounded but R3 integration and its
adversarial tests. It owns runtime, tests, Plan 37 and the workflow guide, with
no nested delegation, live sources or release effects. The coordinator owns
this note, tracker, integration and final gates. Separate fresh-context reviewers
will own functional/domain and security/privacy/provenance verdicts on the
committed candidate. The owner subsequently requested persistent goal mode; the Sprint 24
delivery goal is active, with the same authority and release boundaries.

## Candidate preparation

The implementation writer supplied 230 passing focused/affected cases in the
prepared Python 3.11 environment, clean focused formatting/lint/type checks,
and a complete local evidence report. This is not full-suite or release proof.
The retention-internal deadline gap was corrected with an explicit temporal
exception after source, canonical, prefix and storage-integrity checks; generic
integrity errors remain fatal. The accepted scope is unchanged.

Independent functional/domain and security/privacy/provenance assignments use
fresh native-agent contexts, requested GPT-6 Sol with high reasoning under the
project routing policy. They review the same complete base-to-committed-candidate
change, remain read-only and cannot delegate. Exact model telemetry is unavailable;
requested settings are not asserted as independently observed. Full local,
installed, bounded live-source, hosted and release evidence remains pending.
