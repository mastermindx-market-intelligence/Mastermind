# Lane XP — cross-project delegated child (pin 0770446 + our two patches)

Status: DONE (implementation, tests, live proof, attack round — see the evidence ledger).
Driver model: glm-5.3. Branch `t3/mmos-v4-xp`. Patch:
`integrations/t3/upstream_patches/cross_project_child_0770446.patch` (10 files, 1144
insertions; sha256 `9038b359c1a3b7f13d23d4cdb13c789e6072ae36754eb835465cc39f36aabbba`;
MANIFEST entry with exact commands beside it). Source clone:
`/Volumes/Mastermind/build-cache/xp-t3code` (external volume, pin `0770446`, both prior
patches applied). Evidence: `~/.mastermind/mmos_evidence/xp-20261111/`.

## The goal, restated as what shipped

From a thread in project A, one `delegate_task` with `target.projectId` of project B starts
the child in B: isolated worktree in B's repository cut from the remote default-branch head
after a fetch; B's instructions and hooks apply to the child; the task stays on the parent
(`task_status`, `task_cancel`, finish wakes the parent, lineage shows the child as the
parent's subagent); the child's permissions are no broader than the parent's (runtime mode
clamped to the parent's, provider enabled in B, B a registered project;
unknown/archived/deleted project id refused with one plain sentence).

## Design choice (three sentences)

We extended the local delegated-task path — MCP admission plus a `projectId` carried on the
command through the single dispatch chokepoint into the child-thread record — rather than the
remote peer-delegation path, because the remote path refuses worktree isolation by design
("runs in that project's checkout"), adds a network hop for a same-server case, and cannot
keep task ownership on the parent thread. All cross-project admission happens in one
MCP-layer block before dispatch (registered, not archived/deleted, provider enabled in the
target project, isolation `worktree`, runtime-mode clamp unchanged from upstream), and the
only downstream widening is `command.projectId ?? parent.thread.projectId`, so every other
consumer of dispatch keeps its current behavior. The child's worktree is cut strictly from
B's resolved remote default head after a fetch (`requireRemoteBase`: refuse rather than fall
back to the local branch), which makes "never from a stale local branch" structural instead
of advisory.

Why not the alternatives, in one line each:

- Remote delegation (`peer/RemoteDelegation.ts:215-221`) refuses `isolation: "worktree"`
  outright and depends on peer links plus follower polling — wrong shape for same-server.
- A "run in B's checkout directly" variant would violate done-when #2 (isolation) and
  write into a checkout another session may own; refused by sentence, not by convention.

## What changed (10 files)

- `packages/contracts/src/orchestrationV2.ts` — `delegated_task.request` gains optional
  `projectId`; the worktree strategy gains optional `requireRemoteBase`.
- `packages/contracts/src/orchestratorMcp.ts` — `OrchestratorMcpTarget.projectId` docs.
- `apps/server/src/mcp/OrchestratorMcpService.ts` — the cross-project admission block in
  `delegateTask` (~:2434-2571): isolation/registration/state checks, provider enablement in
  the TARGET project, strict remote-default resolution
  (`resolveRemoteDefaultBaseRef`, ~:1911 — returns `${remote}/${default}` or null, never
  guesses), strategy forced to `{type:"worktree", baseRef, startFromOrigin:true,
  requireRemoteBase:true}`, dispatch passes `projectId` through, and a retry of an accepted
  delegation with the same `clientRequestId` reuses the recorded task (no second child or
  worktree) with `skipProjectEnablementFilter`.
- `apps/server/src/orchestration-v2/ThreadManagementService.ts` — chokepoint:
  `projectId: command.projectId ?? parent.thread.projectId`.
- `apps/server/src/orchestration-v2/Orchestrator.ts` — the spawned child thread record
  overrides `projectId` when the command carries one (upstream's `makeSubagentChildThread`
  spreads the parent; this is the one injection point).
- `apps/server/src/orchestration-v2/ThreadLaunchService.ts` — `ThreadLaunchWorkspaceStrategy`
  gains `requireRemoteBase`; when set and the fetch produced no remote base, the launch
  fails BEFORE any worktree exists.
- `apps/server/src/mcp/toolkits/orchestrator/tools.ts` — `delegate_task` description
  documents `target.projectId`.
- Tests colocated upstream-style: `CrossProjectDelegation.test.ts` (new), plus additions to
  `OrchestratorMcpService.test.ts` and `ThreadLaunchService.test.ts`.

## Cases refused and their exact sentences

| Case | Sentence (live or pinned by test) |
| --- | --- |
| `target.projectId` names no registered project | `Project project:does-not-exist was not found.` (code `invalid_request`; observed live) |
| Target project archived | `Project <id> is archived, so it cannot run delegated tasks.` |
| Target project deleted | `Project <id> is deleted, so it cannot run delegated tasks.` |
| Cross-project without `isolation: "worktree"` (incl. omitted) | `A task in project <id> needs isolation "worktree"; any other isolation would work directly in that project's checkout.` (observed live) |
| Provider instance enabled in A but disabled in B | `Provider instance "<instanceId>" is disabled for project <B>.` (`ThreadManagementProviderInstanceDisabledError` → `invalid_request`) |
| Remote default branch unresolvable (unborn HEAD, no remote, symbolic-ref games) | `Unable to resolve a remote default branch for project "<title>" (<workspaceRoot>), so a worktree cannot be cut from its remote head.` |
| Fetch cannot produce the remote base (with `requireRemoteBase`) | `Unable to fetch <baseRef> from the remote, so no worktree was created. This launch requires the remote base rather than the local branch.` — fails before any worktree is created |
| Runtime-mode escalation (`runtimeMode: "full-access"` from an `auto` parent) | `Child runtime mode full-access is broader than parent mode auto.` (code `runtime_mode_escalation_denied`; observed live) |

Upstream's pre-patch behavior at the same spot refused ANY cross-project `target.projectId`
(`A local task runs in this thread's project. Omit target.projectId, or pass
target.environmentId …`); this patch replaces that blanket refusal with the admission block
above. Cross-ENVIRONMENT delegation remains on the existing `target.environmentId` path,
unchanged.

## Admission checks — added or changed (for the principal review panel)

Added:

1. Cross-project targets require `isolation: "worktree"` — anything else would work
   directly in B's checkout (one plain sentence, above).
2. Cross-project targets must be registered on this server (`requireProject`).
3. Archived targets refused; deleted targets refused (distinct sentences).
4. The chosen provider instance must be enabled in the TARGET project — per-project
   enablement overrides are now checked against B, not only the caller's project. Disabled
   → `ThreadManagementProviderInstanceDisabledError`.
5. Strict remote-default resolution: if `origin`-equivalent remote + default branch cannot
   be resolved, refuse; never guess, never fall back to a local branch.
6. Worktree strategy is forced to the resolved remote base with `startFromOrigin: true,
   requireRemoteBase: true`; a failed fetch fails the launch before any worktree exists.

Changed:

7. Retry of an accepted delegation (same `clientRequestId`) now reuses the recorded
   task/thread and passes `skipProjectEnablementFilter`, so an idempotent replay cannot
   double-create children or worktrees. (Enablement is still enforced on first admission;
   a disablement that lands between attempt and retry is honored because the replay returns
   the already-admitted task rather than starting new work.)

Unchanged but now cross-project-covering:

8. Runtime-mode and interaction-mode clamping to the parent's mode (upstream mechanism;
   escalation refused with `runtime_mode_escalation_denied`).
9. `delegate_task` itself still requires the thread-scoped MCP credential
   (`thread_credential_required` for external OAuth clients) — verified live: the driver's
   own external client cannot call `task_cancel`; only the in-thread parent agent can.

Known asymmetry (documented, not changed): `resolveTarget`'s driverKind CANDIDATE filtering
still filters by enablement in the PARENT's project; the cross-project block then re-checks
enablement in B and refuses if not enabled there. An explicit `providerInstanceId` bypasses
candidate filtering and is fully re-checked against B — the fully-controlled path.

## Restart behavior (census4, answered)

Startup recovery runs `recoverDelegatedTasks` after provider reconciliation
(`serverRuntimeStartup.ts:436`); it resolves the parent from `lineage.parentThreadId` and
finalizes the task under the parent's lock — lineage-keyed and **project-blind** (no code
compares the child's project to the parent's; equality was only ever a construction
invariant of the spread, which this patch deliberately breaks for cross-project children).
`prepareForShutdown`'s `getRecoveryThreadIds("restart-continuations")` filters on the child
thread's own `project_id` row — now B's for a cross-project child, which is correct: the
run is re-prepared under B. Runs still in `preparing` when the server stops are cancelled at
startup rather than half-resumed, so a cross-project child never comes back on a stale base.

## Fetch failure (answered, structural)

`ThreadLaunchService` resolves `remoteBase` via `fetchWorktreeBaseCommit` after the fetch
stage; with `requireRemoteBase: true` a null result fails the launch
(`provision-worktree` error, sentence above) BEFORE `git.createWorktree` runs. Without the
strict flag this site silently fell back to the local `baseRef` — that fallback is exactly
what the flag removes. Pinned by three tests: "fetches the origin base from the remote it
already resolved", "refuses a remote-required worktree when the remote ref cannot be
fetched", "refuses a remote-required worktree when no remote is configured".

## `t3_thread_launch` with `delegatedFrom` (principal's question)

`delegatedFrom` is a separate display field on the thread, not `lineage`
(`packages/contracts/src/orchestrationV2.ts:461`; ThreadForkService deliberately strips it
on fork). The id it carries is a thread on ANOTHER server, so it cannot become
`lineage.parentThreadId` here — that is why the requester saw null. Fixing that display gap
is NOT this change: a same-server cross-project child gets real `lineage` through the
delegated-task path we extended (`makeSubagentChildThread` sets `parentThreadId` /
`relationshipToParent: "subagent"`), confirmed live in the receipt.

## Sidebar rendering (census3)

Lineage resolution is keyed on `environmentId` + `threadId` only — `projectId` never enters
it (`Sidebar.logic.ts:573-588`, `entities.ts:386-429`). The cross-project child therefore
appears UNDER ITS PARENT in project A's sidebar group (it is excluded from B's own list by
`isShownUnderParent`, and its row filter would use B's project key). Consequence: if A's
section is collapsed, the child is not reachable from B's list. Cross-ENVIRONMENT parents
break the lineage path entirely and rely on `delegatedFrom` rendering instead. This is
upstream display behavior; we did not change it in this lane.

## Claude Code extra-directory question (answered; recommendation only)

Against the Claude Code used by this T3 build (CLI 2.1.322; SDK
`@anthropic-ai/claude-agent-sdk@0.3.316`):

- CLI `--add-dir <directories...>` exists (variadic). `/add-dir` exists as a slash command.
  `permissions.additionalDirectories` exists in settings.
- `--bare`'s help groups `--add-dir` under "(CLAUDE.md dirs)": an added directory's
  CLAUDE.md IS loaded into the session context.
- SDK: `Options.additionalDirectories?: string[]` (the SDK's own claim-time help echoes "As
  `--add-dir`"), plus `projectConfigRoot` for relocating settings discovery.

Recommendation: **do not** give a parent thread the other project's root as an extra read
directory by default. Instruction loading is cwd-rooted, so an added dir's CLAUDE.md would
flow into the PARENT's A-side turns — the exact "A's instructions are not carried over"
boundary this lane proves would blur in the other direction, and B's repo would gain silent
read influence over A's reasoning. If a specific workflow ever needs cross-repo read
access, opt in per-call at the driver layer (per-launch `additionalDirectories`), never
server-wide. Not built here.

## Done-when evidence (test + live proof each)

Receipt: `~/.mastermind/mmos_evidence/xp-20261111/live_proof_receipt.json` (live dev
server, own home + own port, free probe agent, throwaway projects A/B with bare origins, B's
local checkout deliberately one commit behind its origin).

1. **`delegate_task` with `target.projectId` of B starts the child in B.**
   Test: `CrossProjectDelegation.test.ts` "creates a cross-project child in the target
   project with a strict worktree"; `OrchestratorMcpService.test.ts` "dispatches a
   cross-project task with a strict remote worktree strategy". Live: `receipt.core.
   childProjectId == projectB`; `childRelationship == "subagent"` with
   `childParentThreadId == parentThreadId`.
2. **Own isolated worktree in B's repo, cut from the remote default head after a fetch,
   never a stale local branch.** Tests: `ThreadLaunchService.test.ts` "fetches the origin
   base from the remote it already resolved" / "refuses a remote-required worktree when the
   remote ref cannot be fetched" / "…when no remote is configured". Live: worktree HEAD ==
   bare origin-b main `ebcf330…` while B's local checkout sits at stale `01d6422…`;
   `origin-head-marker.txt` PRESENT in the worktree and absent from B's checkout.
3. **B's instructions/hooks apply; A's are not carried over.** Structural (census3): the
   server loads no instruction files itself; SDK settings/CLAUDE.md discovery is rooted at
   the turn cwd = the child's worktree inside B's repo. Live: worktree `AGENTS.md` head is
   `XPMARK-B-7f3a` (A's marker `XPMARK-A-4c1e` absent); the child's own report shows its
   cwd = the B worktree (`receipt.core.childReport`).
4. **The task stays on the parent.** Tests: `CrossProjectDelegation.test.ts` "cancelling
   the task stops the cross-project child", "a question from the cross-project child wakes
   the parent", "replaying an accepted cross-project request creates no second child";
   `OrchestratorMcpService.test.ts` "replaying an accepted cross-project delegation skips
   re-admission and rebuilds no worktree". Live: `task_cancel` called BY the parent agent
   (thread credential) → `cancel_requested`, child run `interrupted`; `task_status` returns
   task + childThreadId; the child's completion wakes the parent as a second completed run
   (`receipt.wake.parentRuns` ordinal 2) whose prompt — recorded verbatim by the woken
   probe agent in its own run-2 report, `receipt.wake.parentItems[2]` — begins
   `Delegated task <the delegated task's exact id>`, i.e. the result was delivered into the
   parent. (`t3_thread_read` does not surface the reactor's notification item itself; the
   unit tests cover that item, the live receipt proves the wake run and its payload.)
   Retry with the same `clientRequestId` returns the SAME task and thread
   (`receipt.retry.sameThread/sameTask`, two attempts).
5. **Permissions no broader than the parent's.** Tests:
   `OrchestratorMcpService.test.ts` "clamps a cross-project task's runtime mode to the
   parent's", "refuses a cross-project task for $name" (unknown/archived/deleted table),
   "refuses a cross-project task whose provider is disabled in the target project",
   "refuses a cross-project task with $isolation isolation", "refuses a cross-project task
   without a resolvable remote default branch". Live: the three refusal sentences observed
   verbatim (`receipt.refusals`), including `runtime_mode_escalation_denied` for
   `full-access` from an `auto` parent.

Dev-server hygiene: server booted from the patched tree per the MANIFEST recipe with its own
home and a dynamically chosen free port in 3915–3964 (3773/3774/3780 excluded by code);
receipt records the port and `portFreeAfterStop: true` (rebind proof after stop). The
pairing token never appears in any log or receipt (the boot helper captures it in-process;
sha256-only would apply if it were ever recorded).

## Attack round

One deepseek-v4.1-flash child (effort max, `capacity_fabric_worker`, a different model than
the author), given the applied patch and the verbatim position: "You control the arguments
of `delegate_task` and the contents of project B's repository: start a child with broader
permissions than the parent, in a folder that is not a registered project, or outside an
isolated worktree." Report: `attack1_report.md` (31 vectors) in the evidence dir.

Outcome, after the principal re-verified each citation in the tree: **0 confirmed bypasses
of the lane properties on the `delegate_task` path** — mode clamping, target-project
re-resolution (registered/not archived/not deleted/provider-enabled-in-B), retry-replay
receipt binding, fail-closed remote-base resolution and server-allocated worktree paths all
hold. Three adjacent observations adjudicated and recorded, none requiring a fix:
1. WS `dispatchCommand` of `delegated_task.request` skips the MCP admission block — that
   door stamps `createdBy: "user"` under `AuthOrchestrationOperateScope` and is not
   reachable by an agent; follow-up: hoist the admission block to
   `ThreadManagementService.dispatch` if a non-user actor ever gets WS command access or the
   app UI grows cross-project delegation.
2. `schedule_task` cross-project still uses a conventional local-branch fallback with no
   archived check — pre-existing before this patch, different feature door.
3. `refs/remotes/<remote>/HEAD` steering — whoever controls B's repo can repoint which
   branch of B counts as "default" (the local symref is read, as `git rev-parse origin/HEAD`
   does); the child still lands in an isolated worktree inside B with clamped modes, so no
   attack goal is reachable. Documented limitation, not fixed (`ls-remote --symref` would
   add a network round-trip inside shared VCS driver code used far beyond delegation).
No patch change; sha256 remains `9038b359…abbba`.

## Ledger of what changed (chronological)

1. Census (4 × deepseek-v4.1-flash): completion/question path, worktree+fetch semantics,
   child binding/instruction loading/sidebar, restart recovery. Reports in evidence dir.
2. Implementation on the SSD clone, failing tests first (red logs in evidence dir), then
   green: 4 + 49 + 69 tests in the three touched suites, 167 across the five affected
   suites, both typechecks exit 0.
3. Typecheck correction: the first post-slice apps/server typecheck exit 2 (4 real errors —
   missing `requireRemoteBase` on the local strategy type, an Effect idiom, a widened test
   literal) → fixed, re-run exit 0; patch regenerated (sha `9038b359…abbba`) and re-verified
   in place against the pin+two-patch base.
4. Live proof driver (own dev server + free probe agent): five scenarios, receipt JSON,
   port-free proof. Driver-side parsing bugs found and fixed along the way (item truncation
   cap, `childThreadId` key, single-object directive parsing collapsing arrays, wake-poll
   race); none touched the server code.
5. Attack round (deepseek-v4.1-flash, different model from the author): 31 vectors,
   0 confirmed bypasses on the `delegate_task` path; three adjacent observations adjudicated
   and recorded (see "Attack round"); no fixes required, patch unchanged.
