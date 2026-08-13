# Cross-provider model routing decision

Date: 2026-08-13  
Status: accepted target; activation pending provider qualification

## Context

The earlier routing records were designed when only the GPT-5.6 family was
available: Sol for architecture/high-risk review, Terra for production writing
and verification, and Luna for narrow read-only support. That remains the
configured fallback today. The owner has now selected a target separation in
which Claude Fable/Opus plans and reviews while GPT-5.6 Sol executes code.

This decision changes role routing, not product scope, market logic, quality
gates, credentials, or autonomous authority. No non-GPT provider is currently
authenticated. Catalogue visibility is not proof of access, subscription
coverage, tool compatibility, or economic value.

## Accepted target routing

| Responsibility | Default | Escalation and limits |
| --- | --- | --- |
| Coordinator and product authority | root coordinator | Retains scope, evidence, completion, and owner-escalation judgment; never delegates authority merely by model name. |
| Planning and specification | Claude Fable 5, read-only | Claude Opus 5 for architecture, new market rules, point-in-time evidence, security/authorization, or unresolved ambiguity. |
| Code and test implementation | GPT-5.6 Sol, high reasoning, sole writer | Receives an approved frozen specification, exact path ownership, red tests, acceptance criteria, and exclusions; stops rather than inventing a rule. |
| Routine independent review | Claude Fable 5, read-only | Reviews exact candidate SHA and test adequacy; never repairs its own findings. |
| High-risk/final review | Claude Opus 5, read-only | Required for published contracts/schemas, market/scoring rules, architecture, credentials/security, or repeated verification failure. |
| Test and release authority | deterministic tools and hosted CI | LLMs design and audit tests; only executed Ruff, Pyright, Vulture, pytest, build, security, and hosted checks establish pass/fail. |
| Publication | bounded publisher after approval | Publishes only the exact independently approved SHA; a model choice does not grant GitHub or Linear authority. |

Fable is the default planning/review economy tier; Opus is a risk escalation,
not a routine second opinion. GPT-5.6 Sol owns implementation and repair so the
writer remains proven in this repository while Claude supplies independent
model-family challenge.

## Work allocation guide

Percentages describe expected work, not token or subscription spend:

- normal increment: **20% planning / 55% execution / 25% review**;
- already-frozen mechanical implementation: **15% / 60% / 25%**;
- new or high-risk market logic: **30% / 40% / 30%**; and
- evidence/security/release boundary: **15% / 40% / 45%**.

These are planning guides, not quotas. Complexity or review findings may move
work between phases without weakening acceptance. Rework counts against the
execution model's effective cost.

## Activation gate

Do not change `.codex/agents` or active runtime routing until all of the
following are evidenced for the exact models and provider path:

1. authentication succeeds without exposing or retaining credentials in the
   repository or transcript;
2. Prime Agent can invoke the model, use required tools, read the repository,
   return non-empty results, and send a complete handoff;
3. the owner verifies that the purchased plan actually permits this third-party
   harness use and whether usage consumes subscription allowance or separately
   billed extra usage;
4. three bounded qualification tasks pass: read-only planning, read-only exact-
   SHA review, and a disposable isolated-worktree implementation;
5. the implementation candidate passes focused and affected tests, produces a
   valid commit, respects exact paths/authority, and needs no more than one
   material repair cycle under independent review; and
6. measured elapsed time, review findings, repair rounds, escaped defects, and
   actual available cost/usage evidence show benefit over the GPT-only baseline;
   no task may require more than one material repair cycle during qualification.

A model catalogue entry or advertised price is not sufficient evidence. Do not
record unverified intelligence percentages, cost multiples, or plan limits.

## Active fallback until activation

The repository remains on its checked-in GPT-only configuration: Terra is the
sole implementation/repair writer, Sol owns architecture and high-risk review,
and Luna is narrow low-risk read-only support. If Claude is unavailable,
rate-limited, incompatible with tools, produces an empty handoff, or exceeds the
repair budget, preserve the exact state and use this fallback. Never silently
substitute a weaker reviewer for a required high-risk review.

When the activation gate passes, update `.codex/config.toml`, the role TOMLs,
and their executable contract tests together in a separate approved workflow
change. Until then this note records the accepted target but does not pretend it
is running.

## Quality and independence invariants

- One writer owns a path; planners and reviewers remain read-only.
- The plan freezes purpose, inputs, outputs, deterministic rules, edge cases,
  validation, acceptance, exclusions, and owner-only decisions before handoff.
- The executor stops on ambiguity, architecture conflict, new market logic,
  credential/live-provider need, or destructive action.
- Review binds to the exact commit and unchanged tree, returns material findings
  together, and never waives deterministic gates.
- The same model family may provide fallback roles, but writer and reviewer must
  still be separate actors; the preferred cross-provider route adds diversity,
  not proof of correctness.
- Subscription pressure cannot authorize weaker evidence, skipped review, or a
  failed release.

## Sources and qualification boundary

- Repository `docs/development-workflow.md` and `.codex/agents/` own active
  mechanics.
- The installed Prime Agent 0.7.2 provider guide lists Claude Pro/Max and Kimi
  provider paths, but also warns that Anthropic third-party harness use may draw
  separately billed extra usage. This must be rechecked against current vendor
  terms before purchase or activation.
- The 2026-08-06 quota-routing note remains historical evidence and must not
  select current or target routing.
