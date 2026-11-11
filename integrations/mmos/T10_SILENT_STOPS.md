# T10 — delegated child stops: every end reaches the parent with a cause (2026-11-11)

Patch: `integrations/t3/upstream_patches/silent_stop_return_0770446.patch` (sha256 `26dbd715…fac2`), applies after admission → text_delta → cross_project (41d968be). Evidence: `~/.mastermind/mmos_evidence/t10-20261111/`.

## Path table

| # | Path | Where (pin + 3 patches) | Before | After | Test |
|---|---|---|---|---|---|
| 1 | Stream ends with no terminal | `ProviderTurn*` → `handleRunUpdate` | settled failed with cause, parent woken once (already closed) | unchanged | `a delegated child whose stream ends without a terminal…` |
| 2 | Provider error (HTTP 400) | same | settled failed, error text as return line, woken once (already closed) | unchanged | `a delegated child that fails with HTTP 400…` |
| 3 | Normal completion | same | woken once | unchanged | `a normal delegated child completes and wakes its parent once` |
| 4 | Restart mid-child, resume on | restart reconcile + `effect:restart-continuation` | resumed, completed, woken once (already closed) | unchanged | `…cut by a restart resumes, finishes…` |
| 5 | Restart mid-child, resume off | `Orchestrator.ts` `finalizeAppOwnedSubagentTask`, `recoverDelegatedTasks` | `cancelled` with generic "Child task ended with status cancelled." | `cancelled` + "This task stopped before it finished: the server restarted … it was not resumed…" + last output | `…cut by a restart that is not resumed…` (red→green) |
| 6 | Restart, resume keeps failing | `recoverDelegatedTask` (`settledContinuationOf`) | after 60 s/180 s retries, generic text; resume error lost | "The server restarted before this task finished, and resuming it failed: <open error>" | `…whose resume keeps failing…` (red→green) |
| 7 | Same `clientRequestId` after restart | MCP `delegate-task` dedupe key `command:mcp:<providerSessionId>:…` | new parent session → new key → second child | unchanged (OPEN, see below); dead child is not reported fine | live scenario (iii) |

Resume never re-sends the original prompt: the continuation turn sends the server's continuation note (live proof prompt log). If no clean resume happens, the task settles and says so.

## Live proof (receipt `live_proof_receipt_073325.json`)
(i) HTTP 400 child: parent woken once, "[failed]: API Error: 400 …". (ii) restart, resume on: child [completed, cancelled→resumed], parent woken once "[completed]"; resume off: woken once "[cancelled]: This task stopped before it finished…". (iii) replay after restart: new taskId, second child, later reported cancelled with the restart text — never reported fine. (iv) normal: woken once.

## Open
- Replay dedupe across restarts (row 7): key is per provider session. Recommendation: key by parent thread + run lineage.
- A child still preparing (`startedAt` null) when the restart hits keeps the generic text.
- After a restart, a child the provider itself cancelled before the restart (not finalized yet) would be described as restart-cut. Status stays correct; only the wording.
- Status stays `cancelled` (not `interrupted`): three upstream delivery tests pin `cancelled`.
- Hung executor and unbounded finalization retry: upstream design, not changed.

## Install / rollback (team server; the install is the principal's)
Build from a clone at the pin with all four patches applied in order (MANIFEST commands), then swap the team server build under its existing launcher. Rollback: rebuild without `silent_stop_return_0770446.patch` (`git apply -R silent_stop_return_0770446.patch` on the clone) and restart under the same launcher. No schema or state migration; stored data is untouched either way.
