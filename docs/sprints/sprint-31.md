# Sprint 31: hypothetical loss including caller-assumed costs

Owner/risk owner: Krunal Dodiya. Governing [#242](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/242), milestone 23.
[Plan 45](../plans/45-loss-scenario-assumed-costs.md) freezes the R3 contract.
Status: planning complete; implementation assignment ready, validation pending.

The October 2 owner request authorizes completing planning and starting
implementation. The selected outcome adds one caller-supplied aggregate cost
amount to the existing hypothetical loss calculation through opt-in V2 CLI/SDK.
The read-only planning agent inspected delivered code and rejected AI-side
calculation, fee-source adoption and unnecessary V7 integration as alternatives.
The coordinator accepted the bounded slice within the existing risk-context epic.
The contract freezes fields, labels, exact arithmetic, bounds, failure precedence,
adversarial checks, compatibility and non-goals before code changes.

Sprint 30 closeout was verified live: #240 closed, Delivery Project Done,
milestone 22 closed with zero open issues, PR241 merged October 2 at
`07704641aff54f8b0d56cfa99d0f882dd93422ad`. Local main, origin/main and the live
remote ref match. Old Sprint30 local-only headings remain dated checkpoints.
No Sprint30 release permission is transferred to Sprint31.

The original checkout was clean at `7ba761501a94528a0aea4094fea8b56880e88f6e` on
`codex/sprint30-loss-context`. This sole active checkout now uses
`codex/sprint31-assumed-costs`, created from verified main; the old branch and
main are preserved. No other worktree or competing writer was found, so a new
worktree/environment was unnecessary. Future items #178/#177/#144/#139/#126
remain Todo without sprint assignment. Project-local `.agents` is absent.
No runtime memory retrieval tool is exposed; repository-retained reconciled
notes supply context only.

Coordinator owns planning/tracker/integration/review and full gates. Completed
read-only native agent `/root/sprint31_planning` supplied the planning proposal;
its complete result is retained in this chat. A separate native executor owns
the exact files in Plan45 and focused checks, without nested delegation. Two
fresh non-mutating functional/domain and security/privacy/provenance reviewers
will assess the stable committed full candidate afterward.

Inherited model/effort are requested; actual telemetry and a genuine Fast
service-tier control are unavailable/unverified. The handbook was found at the
installed `software-engineering-handbook/software-engineering-handbook/2.0.0`
plugin path after the catalog's shorter path failed. Its planning and TDD
fallbacks are used; no approved original expert skill is exposed.

The canonical project `.venv` and official uv are reused without dependency
changes or manual environment copying. Use visible synthetic fixture/evidence
paths; prior hidden-fixture approvals do not transfer. Protected provider effects,
credentials, source adoption, new installations and hidden directories remain
outside this assignment. Any PR stays draft until separately authorized.
Implementation, independent review, full gates, hosted gates and release remain
distinct pending states; no completion is claimed from planning alone.

## Goal activation correction — October 2, 2026

The owner reiterated the standing Goal requirement after implementation started.
The coordinator had delegated activation to the executor without verifying it;
the executor identified the tool as chat-scoped and left it inactive to avoid
taking coordinator ownership. A coordinator `get_goal` read confirmed null.
The coordinator then created the persistent Sprint31 goal and received `active`
for this chat. It covers implementation, both independent reviews and applicable
verification under Plan45; merge/release authority is unchanged. The coordinator
owns goal lifecycle and the existing executor retains sole implementation-file
ownership. The executor was notified to continue and not alter the chat goal.
This is an execution correction, not a contract or scope change.

## Implementation checkpoint — October 2, 2026

The bounded implementation is committed at
`a917a6188fd26ac74d46776f3e6f7ac389b38add`. The actual V2 CLI first failed with
exit 2 before implementation and then returned the required exact amounts.
Focused evidence records 212 passing tests plus one separately executed retained
V6 compatibility test, also passing. An intermediate matrix run recorded a wrong
test expectation for unsupported-version exception handling; the failed attempt
is retained and the test was corrected to the existing CLI contract. Ruff,
Pyright (zero errors/warnings), Vulture80 and all 15 refreshed active manifests
passed focused checks. These are not full-suite or installed-wheel claims.

Evidence lives in the visible owner-host directory
`/home/krunaldodiya/Documents/Codex/2026-10-02/sprint31-evidence`.
Coordinator will freeze the combined candidate, including this checkpoint,
after the executor releases mutation ownership. Both independent reviews and
the authoritative self-hosted full acceptance gate remain pending. The existing
distribution verifier does not exercise the new V2 command; a targeted clean
installed-wheel V2 smoke remains required. No merge/release is authorized.
