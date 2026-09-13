# Optional Herdr adapter

Status: **OPTIONAL TOOL ADAPTER**

The portable procedure is [agent-workflow.md](agent-workflow.md), under the
[canonical project instructions](mandatory-agent-instructions.md). This file
maps it to Herdr when selected. It does not require Herdr, OMP, a model, a global
profile, or unrestricted permissions. Earlier OMP-only rules at this path were
superseded by [Issue #170](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/170).

## Select the adapter

Use current host Herdr guidance and installed command help to verify availability
and supported agent kinds/options. Do not assume OMP flags work for another
runtime or that a model identifier is a harness identifier. Select a supported
runtime and task-appropriate model under the canonical rules. If Herdr is absent,
use another mechanism from the portable capability table; only an unavailable
required control blocks dependent work.

## Map the portable lifecycle

| Portable action | Herdr mapping when supported by the installed version |
|---|---|
| Create visible resources | `herdr tab create`; retain returned tab and pane IDs. |
| Start assigned runtime | `herdr agent start`; use its supported kind and runtime-specific options. |
| Verify configuration | `herdr agent get` and runtime metadata, not an assumed OMP log schema. |
| Submit assignments | `herdr agent prompt` without `--wait` in an interactive coordinator; submit an independent same-outcome wave before returning control. |
| Wait and inspect | Use `herdr agent wait` only in headless/non-interactive execution or for a short same-turn dependency that cannot delay user input; otherwise inspect after a supported notification or on the next active turn. |
| Diagnose state | `herdr agent get`, `herdr agent read`, and `herdr agent explain`. |
| Capture full result | `herdr agent read`; use export or portable result recovery if truncated. |
| Release completed resources | `herdr tab close` for the captured, completed task-owned tab only. |

Do not derive IDs from labels or sidebar order. Use stable unique agent names.
Tabs in one checkout share files; select explicit worktree paths for isolation.
Apply portable ownership and review identity checks to those actual paths.

## Preserve the interactive foreground

For an interactive Pi/Herdr session, launch and prompt delegated work without a
foreground wait:

```bash
herdr agent prompt "$AGENT_NAME" "$COMPLETE_PROMPT"
```

Then return control to the conversation. Do not immediately run `herdr agent
wait`, do not poll `agent get` or `agent list`, and do not sleep until the task
finishes. Herdr 0.8.0 exposes user-facing notifications but no coordinator event
subscription. When supported, the assignment MUST end by showing a bounded
notification that contains no result payload or secret:

```bash
herdr notification show "Agent task settled" \
  --body "Inspect $AGENT_NAME when convenient" --sound done
```

Use `--sound request` for attention that genuinely needs input. The notification
is a signal to inspect authoritative lifecycle state; it is not evidence of
success. Notification delivery is configuration-dependent: a response containing
`"shown": false` or `"reason": "disabled"` means the path is unavailable and
MUST NOT be described as a delivered wake-up. Do not use `herdr agent prompt
<coordinator>` or send keys to the coordinator as a child callback: that injects
synthetic conversational input and can reorder or obscure real user messages. If
notifications are unavailable, leave the dedicated task tab visible, disclose
that result capture resumes on the next active coordinator turn, and do not
invent polling or another orchestration surface.

A synchronous `herdr agent prompt ... --wait` or `herdr agent wait` remains
permitted for headless/non-interactive execution and a short, bounded same-turn
dependency that cannot delay user input. It is prohibited for long-running work
in an interactive coordinator. Parallel Herdr tabs are capacity within one
active delivery outcome, not permission to start unrelated product and tooling
tasks together.

`working`, `blocked`, and `unknown` do not permit cleanup. `idle` or `done` permits
result capture but does not override an active or paused underlying goal. Default
settled-state waits may include blocked agents; inspect results rather than
waiting exclusively for `done`.

If session metadata appears only after input, use a documented no-work bootstrap
and verify required effective settings before assignment. Missing logs do not
permit invented evidence or silent model substitution. Read recovered files with
any read-only file tool; OMP `read`, its JSONL parser, and yolo flags are not part
of the portable contract. Preserve complete results before closing a completed
tab; never close the user's coordinator or another task's agent.
