# Lane XP — cross-project delegated child (pin 0770446 + our two patches)

Status: IN PROGRESS (skeleton, first push). Driver model: glm-5.3. Branch
`t3/mmos-v4-xp`. Patch target: `integrations/t3/upstream_patches/cross_project_child_0770446.patch`.
Source clone: `/Volumes/Mastermind/build-cache/xp-t3code` (external volume, pin `0770446`,
both existing patches applied). Evidence: `~/.mastermind/mmos_evidence/xp-20261111/`.

## The goal

From a thread in project A, one `delegate_task` with `target.projectId` of project B starts
the child in B: isolated worktree in B's repository cut from the remote default-branch head
after a fetch; B's instructions and hooks apply to the child; the task stays on the parent
(`task_status`, `task_cancel`, finish wakes the parent, sidebar shows the child under the
parent); the child's permissions are no broader than the parent's (runtime mode clamped to
the parent's, provider enabled in B, B a registered project; unknown/archived/disabled
project id refused with one plain sentence).

## Design choice (working, to be finalized with census evidence)

Extend the LOCAL delegated-task path, not the remote-delegation path. Evidence so far:

- `OrchestratorMcpService.delegateTask` (apps/server/src/mcp/OrchestratorMcpService.ts:2396)
  dispatches `delegated_task.request`; `Orchestrator.dispatchDelegatedTaskRequest`
  (apps/server/src/orchestration-v2/Orchestrator.ts:8031) builds the child thread with
  `makeSubagentChildThread` (packages/provider-core/src/server/subagentProjection.ts:52),
  which spreads `...parentThread` — so the child inherits `projectId` from the parent. That
  spread is the one place a different project has to be injected.
- Worktree preparation runs under the CHILD thread's project:
  `ThreadLaunchService.scheduleRunPreparation` reads `thread.projectId`
  (apps/server/src/orchestration-v2/ThreadLaunchService.ts:1149) and creates the worktree
  with `cwd: project.workspaceRoot`. Setting the child's projectId to B therefore makes the
  child's worktree live in B's repository.
- The remote path (`peer/RemoteDelegation.ts:215-221`) explicitly REFUSES
  `isolation: "worktree"` ("A task in a linked environment runs in that project's checkout")
  and depends on a peer link plus follower polling; it cannot give done-when #2 (isolated
  checkout at remote head) and adds a network hop for a same-server case.

Planned shape (subject to census):

1. `delegated_task.request` command gains an optional `projectId` (contracts).
2. MCP `delegateTask`: when `target.projectId` names another registered project, admit it
   (registered, not archived/disabled; provider enabled in B), then pass that project on the
   command. Runtime-mode clamping against the parent stays where it is
   (`resolveRuntimeMode(parent.thread.runtimeMode, …)`).
3. Orchestrator: `childThread.projectId = command.projectId ?? parent's`; for a cross-project
   worktree child, the workspace strategy is cut from B's default branch as
   `origin/<default>` with `startFromOrigin: true` (fetch first; refuse on fetch failure —
   never silently fall back to a stale local branch).

## `t3_thread_launch` with `delegatedFrom` (question from the principal)

`delegatedFrom` is a separate display field on the thread, not `lineage`
(packages/contracts/src/orchestrationV2.ts:461; ThreadForkService deliberately strips it on
fork). The id it carries is a thread on ANOTHER server, so it cannot become
`lineage.parentThreadId` here; that is why the requester saw null. Fixing that display gap is
NOT this change: a same-server cross-project child gets real `lineage` through the
delegated-task path we extend here (makeSubagentChildThread sets
`parentThreadId`/`relationshipToParent: "subagent"`).

## Admission checks (who may be a target) — DRAFT, principal review panel decides

- target project must be registered on this server (exists in project service)
- not archived / deleted / disabled (exact state names from census)
- provider instance enabled in B (mirrors the caller-project check that exists today)
- runtime mode + interaction mode clamp to the parent's (existing mechanism, unchanged)
- cross-project child requires isolation "worktree" (no writing in B's root checkout)

## Cases refused and their sentences — DRAFT

(To be filled with the exact final sentences.)

## Restart behavior — TO VERIFY

`RestartContinuation.test.ts` covers prepared-run recovery; verify a cross-project child in
`preparing` state is re-prepared under B (task record stays on parent A's thread either way).

## Fetch failure — TO VERIFY

`git.fetchWorktreeBaseCommit` semantics on failure: must refuse the launch, not fall back to
the stale local ref. Census question open.

## Claude Code extra-directory question — TO ANSWER

Which of `--add-dir`, `/add-dir`, `permissions.additionalDirectories`, SDK
`additionalDirectories` this build's Claude Code supports; whether instructions from an
added folder load; recommendation only (not built in this lane).

## Done-when evidence

(To be filled: five lines, each test name + evidence file.)

## Ledger of what changed

(To be filled at the end.)
