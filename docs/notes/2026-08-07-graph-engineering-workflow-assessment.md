# Graph engineering workflow assessment

Date: 2026-08-07
Status: accepted

## Context

Graph engineering has recently been presented as the next layer beyond loop
engineering. The project already uses bounded agent loops, one root coordinator,
specialized implementation and review roles, deterministic gates, durable
handoffs, live completion signals, and a circuit breaker. The owner approved a
strict assessment of whether explicit graph control could improve speed and
recovery without creating excessive subscription usage or another platform to
maintain.

## Findings

- The new label describes established state-machine and directed-graph ideas:
  small capability nodes, explicit routing edges, and checkpointed state.
- Loop engineering remains necessary inside implementation, verification,
  review, and research nodes. Graph control addresses what happens between
  those loops.
- Durable checkpoints can prevent completed work from being repeated after an
  interruption, and event-driven edges can remove routine heartbeat polling.
- Parallel fan-out is useful for genuinely independent research. It is a poor
  default for dependent coding work because coordination, duplicated context,
  and error propagation can outweigh speed gains.
- Anthropic reports materially higher token use for its multi-agent research
  system and warns that coding normally offers fewer independent branches than
  research. Its figures describe that system and must not be treated as a cost
  forecast for this project.
- Existing graph frameworks demonstrate checkpoint, pause/resume, and
  human-approval patterns, but adopting one here would add dependency, hosting,
  security, storage, and operational costs before a need has been demonstrated.

## Decision and rationale

Accepted: use graph-lite execution control in the authoritative development
workflow. Make the existing nodes, transitions, checkpoint fields, resume
rules, and cost limits explicit while retaining Linear, active Goal/task state,
Git, Codex completion messages, and the existing model-routing roles.

Deferred: any LangGraph, Microsoft Agent Framework, Temporal, or other dedicated
workflow runtime. A framework requires separate approval supported by evidence
that the existing substrate cannot provide reliable execution.

Rejected for now: an always-running agent army, parallel code writers, routine
polling agents, and model-decided edges when a deterministic condition is
available.

## Consequences and validation

- One executable task and one repository writer remain absolute limits.
- A waiting or blocked node has no active agent.
- Checkpoints are bound to an exact source revision, preserve the approved risk
  classification and evidence, identify the planner or owner decision actor,
  and record the next action.
- Resume jumps directly to the checkpoint's saved authorized next action; it
  does not repeat completed readiness, risk-classification, or Sol-planning
  work.
- The approved repair budget and the mandatory circuit breaker both govern every
  repair edge. Two materially identical verifier rejections or same-gate
  failures after repair route to Sol even if budget remains.
- Completion signals drive normal handoffs; the heartbeat remains crash recovery.
- The first suitable approved atomic task will pilot the workflow. Evaluation
  uses observable time, handoff, retry, repair, gate-repetition, acceptance, and
  user-visible quota evidence. Unavailable token telemetry is not inferred.

## References

- [We Are Entering the Graph Engineering Phase](https://www.drjoshcsimmons.com/writing/we-are-entering-the-graph-engineering-phase)
- [From Agent Loops to Structured Graphs](https://arxiv.org/abs/2604.11378)
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Towards a Science of Scaling Agent Systems](https://arxiv.org/abs/2512.08296)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Microsoft Agent Framework durable extension](https://learn.microsoft.com/en-us/agent-framework/integrations/durable-extension)
- [Loops, Graphs, and the Layer That Matters](https://iii.dev/blog/loops-graphs-and-the-layer-that-matters/)
