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
| Submit assignments | `herdr agent prompt`; submit independent work before waiting. |
| Wait and inspect | `herdr agent wait`, then `herdr agent get`; inspect after timeouts too. |
| Diagnose state | `herdr agent get`, `herdr agent read`, and `herdr agent explain`. |
| Capture full result | `herdr agent read`; use export or portable result recovery if truncated. |
| Release completed resources | `herdr tab close` for the captured, completed task-owned tab only. |

Do not derive IDs from labels or sidebar order. Use stable unique agent names.
Tabs in one checkout share files; select explicit worktree paths for isolation.
Apply portable ownership and review identity checks to those actual paths.

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
