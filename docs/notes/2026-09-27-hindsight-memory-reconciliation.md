# Hindsight project-memory reconciliation

Date: 2026-09-27
Owner: Krunal Dodiya
Status: documentation recovery; a possible move to Mem0 remains proposed.

Accepted recovery scope: SwingTradingAIAssistant project memory only. The owner
confirmed on September 27 that other projects and unrelated memory can be
skipped, and requested persistence of these recovered Markdown notes on the
existing `codex/self-hosted-ci` branch for push. Material already covered by
project docs stays in its existing source. This follows the discussion-retention
workflow governed by [#179](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/179).

## Scope and evidence

The owner requested that SwingTrading knowledge present only in Hindsight be
imported into project docs, skipping material already documented. The comparison
used the working checkout at commit
`9214e48cf9900a194addcd508fe3b0e23acf5e5b`; the registered `/mnt/d/Code/` checkout
path was stale. No memory-backend switch is part of this change.

The local Hindsight MCP returned the full `pi-projects` inventory: 1,319 source
documents and 14,167 memory units (6,385 world facts, 3,555 experience facts,
4,227 derived observations). A single complete read was used to avoid gaps or
duplicates from offset pagination. The canonical project tag contained 9,416
units; combining it with the legacy tags produced 12,764 unique units:

- `project:swingtradingaiassistant`
- `project:github-com-krunaldodiya-swingtradingaiassistant`
- `repo:swingtradingaiassistant-3bdf2b0a07b5`
- `project:swing-trading-ai-assistant`
- `swing`

The remaining bank records were also inventoried. Three additional source
documents concerned an Issue #189 conversation, an old machine-migration
inventory, and a historical coordinator policy; three belonged to the engineering
handbook. Their project-relevant claims were checked against current instructions
and delivery records. Derived observations were not treated as independent
approval or as stronger evidence than their original records.

Inventory-wide text comparison against 91 tracked Markdown files located
candidate gaps. Targeted searches and inspection of original Hindsight documents,
current project docs, and relevant GitHub records determined the additions below.
Lexical similarity alone was not treated as proof that a decision was covered.
Unrelated conversations present under project tags were excluded.

The latest `mentioned_at` in this bank snapshot was September 23. Newer project
documents, including Sprint 25 material, were not overwritten with that older
state. This is a selective durable-knowledge recovery, not a lossless transcript
export, a complete revalidation of every historical assertion, or evidence that
Hindsight can be deleted. A backend migration and recovery verification remain
separate from this documentation task.

## Recovered gaps

| Knowledge absent from local docs | Destination |
| --- | --- |
| Retained five-video research review, specific deferred comparisons, rejected defaults, and paper-interpretation limits | [Playlist research disposition](2026-08-24-playlist-research-disposition.md) |
| September 23 clarification that agent-led stock/list research is the intended product experience and question-specific commands are intermediate steps | [Later owner clarification](2026-09-22-next-sprint-and-linux-handoff.md#later-owner-clarification-intended-end-product) |
| Later September 22 native/encrypted backup evidence and unresolved independent key custody | [Later backup checkpoint](2026-09-22-next-sprint-and-linux-handoff.md#later-september-22-backup-checkpoint) |
| Sprint 20 real-stock observation and its one-time disclosure exception | [Operational closeout](2026-09-23-live-research-closeout.md) |
| Source-isolation diagnostic lesson and a manifest-discovery pitfall | The two historical lessons below |

## Historical lesson: isolate source failures before broad conclusions

Status: recovered diagnostic finding, September 9; the Yahoo/yfinance acquisition
lane was later retired. This record does not recommend reactivating it.

An owner-authorized direct-library study of the same 100 capture stocks in ten
sequential batches found 62 valid and 38 invalid stocks, with a failure in every
batch. The retained summary distinguished 23 stocks with null September 7 OHLC,
adjusted close and volume from 20 with null September 8 close/adjusted close;
five overlapped. RELIANCE and TCS were valid, so successful sample stocks did not
establish full-cohort availability. Earlier admitted captures had valid prices
for the 23 September 7 cases. The different request windows/times prevented a
claim that the fault existed during earlier review or proved a permanent
library defect. Eleven existing revisions were unchanged.

The reusable lesson is to establish a bounded direct-source/library baseline
and isolate exact member/date/field categories early. A coarse rejection code,
a healthy sample, safe refusal, and demonstrated usable research output are
different claims. Existing acceptance criteria already required a complete
100-stock capture and rejection of non-finite prices; the incident was not proof
that acceptance criteria or null validation were absent.

Sources: `pi-projects` documents `2295d5d7-4d89-47d0-9f96-9a2fed290628` and
`74aa6213-3869-4aa6-a11f-de76ed5128f7`, both read back. Historical private evidence
was `summary.json` and `stock-results.csv` under
`~/SwingTradingAIAssistantData/post-market-20260908/stock-batch-debug-1/`.
Those private files were not reopened in this task. Current provider policy is
recorded in the [architecture](../architecture-freeze-v1.md).

## Historical lesson: a manifest scanner can miss declarations

Status: recovered September 20 diagnostic lesson; not a new runtime requirement.

An ad hoc verifier used a name-suffix heuristic and missed the annotated
`CURRENT_EVENT_NOTICE_RUNTIME_SOURCE_DIGESTS_V1: Final = {...}` declaration.
The historical correction used structural declaration discovery and an
independent cross-check; it reported 33 manifests and 727 bindings with zero
mismatches on that candidate. Those counts are historical, not today's expected
inventory or a current gate pass.

The lesson supplements the existing transitive-manifest policy: a clean result
from an incomplete scanner proves too little. Include supported declaration and
path forms, not just convenient suffixes. The current repository has
`test_all_runtime_identity_manifests_bind_every_supported_path_form` in
`tests/market_data/test_current_cohort.py`; this documentation task did not run it.

Source: `pi-projects` document `pi-session:1eec66ae6d314951`, fact
`fe8d54cf-0adb-46c6-85a8-9dd231b93990`, with corroborating record in
`20260918_104226_0468d3`. Current policy remains in the
[canonical adapter](../mandatory-agent-instructions.md#delivery-and-evidence-controls).

## Material left in its existing source

- Product boundaries, canonical identity, dynamic stock lists, missing-evidence
  isolation, source-reported BharatStock policy, and historical validation:
  architecture, Plans 23/29/30/33–38, roadmap, and workflow docs already cover them.
- Feature-family admission and optional facts versus hard filters: Plan 34
  already records these; the all-admitted-feature memory adds no new contract.
- Provider-lag fallback and practical evening capture timing: the September 23
  fallback note, current research workflow, and roadmap already preserve them.
- Agent authority, review, model routing, no nested delegation, and documentation
  checks: current canonical instructions supersede old harness-specific memories.
- Frozen sprint receipts, intermediate repair assignments, superseded failing
  candidates, and tool-status chatter were not promoted into current requirements.
  Existing plans, sprint records, code history, and GitHub remain their evidence.
- Global tooling preferences and unrelated project conversations were not copied
  into SwingTrading documentation. No secrets, raw market payloads, full chat
  transcripts, or recovery keys were imported.

Every addition keeps its original date, status, source pointer, and limitations.
The notes index links the recovered records so they can be read without Hindsight.
