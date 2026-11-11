# Lane XP — cross-project delegated child (pin 0770446 + our two patches)

Status: DONE (implementation, tests, live proof, attack round, panel repairs — see the
evidence ledger and "Panel repairs" below).
Driver model: glm-5.3. Branches `t3/mmos-v4-xp` (feature), `t3/mmos-v4-xpb` (panel
repairs). Patch:
`integrations/t3/upstream_patches/cross_project_child_0770446.patch` (10 files, 1849
insertions, 16 deletions; sha256 `a5cfa90eba615daffdad358b4fa5177ca3077a84740084bbd1906be02544101d`
— includes the four panel repairs and the stale-tracking-ref proof test; the pre-repair
bytes were `9038b359…abbba`, 1144 insertions;
MANIFEST entry with exact commands beside it). Source clone:
`/Volumes/Mastermind/build-cache/xp-t3code` (external volume, pin `0770446`, both prior
patches applied). Evidence: `~/.mastermind/mmos_evidence/xp-20261111/` (feature round) and
`~/.mastermind/mmos_evidence/xpb-20261111/` (panel repairs round).

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
| Target project deleted | `Project <id> was not found.` — the project lookup hides deleted projects, so deleted and unregistered read identically (panel repair XPb-4 removed an unreachable separate sentence) |
| Raw `delegated_task.request` command with `projectId` set and no strict strategy (any door that bypasses MCP admission) | `A delegated task in project <id> needs a worktree cut from that project's remote head (isolation "worktree" with startFromOrigin and requireRemoteBase).` |
| Target unregistered/archived between admission and dispatch (re-read in the orchestrator) | `Project <id> is not available for delegated tasks.` |
| Retry with the same `clientRequestId` naming a different target project (or none) | `This request id was already used for a task in project <firstProjectId>, not <requestedProjectId>.` (`invalid_request`; no admission check runs against the new project) |
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

Formerly a known asymmetry, closed by panel repair XPb-3: `resolveTarget`'s driverKind
CANDIDATE filtering now uses the TARGET project's enablement for cross-project requests
(`enablementProjectId`, `OrchestratorMcpService.ts:1338-1372`); same-project filtering is
unchanged. An explicit `providerInstanceId` bypasses candidate filtering and is re-checked
against B as before.

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

## Panel repairs (branch `t3/mmos-v4-xpb`, 2026-11-11)

A five-reviewer panel (`~/.mastermind/mmos_evidence/xp-20261111/panel/SCORE.md`, 45
findings) returned four repairs; all four are implemented, red/green logged, and folded
into the regenerated patch (sha `a5cfa90e…0101d`). Evidence round:
`~/.mastermind/mmos_evidence/xpb-20261111/`.

1. **XPb-5 — orchestrator guard on raw cross-project commands**
   (`Orchestrator.ts:8084-8120`, child-record clearing at `:8164-8172`). The guard sits
   in `dispatchDelegatedTaskRequest`, the command body itself, because every executing
   sender of `delegated_task.request` passes through `orchestrator.dispatch →
   dispatchWithReceiptEffect → dispatchOnce` — both proven doors: the MCP `delegateTask`
   handler and the WS `dispatchCommand` door (`ws.ts` → `ThreadMessageIntake` →
   `threads.dispatch`) that admits raw commands. When `command.projectId` is set and
   differs from the parent thread's project, the command is refused unless the strategy
   is a worktree with `startFromOrigin: true` AND `requireRemoteBase: true`; the target
   project is re-read there (the orchestrator reads the same `projection_projects` store
   `ProjectService.getById` reads — cheap) and an unregistered or archived target is
   refused; and whenever the child's project differs from the parent's, `branch` and
   `worktreePath` are cleared. Retry choice, stated: the guard lives in the command body,
   so a receipt replay — which is how an MCP retry with `projectId` but no strategy
   behaves — returns the recorded events and never runs the guard
   ("replaying an accepted cross-project request creates no second child" still passes);
   no second door needs the strategy re-sent. Tests: "refuses a raw cross-project command
   without a strict worktree strategy", "refuses a raw cross-project command for an
   archived target project" (`CrossProjectDelegation.test.ts:298,334`).
2. **XPb-2 — retry naming a different target project** (`OrchestratorMcpService.ts:
   2588-2606`). On a replayed receipt whose child thread exists, the child's project is
   compared with the requested project (`target.projectId` when it differs from the
   parent's, else the parent's); a mismatch is refused `invalid_request` with the
   sentence in the table above, before any admission check runs against the new project.
   Rejected receipts keep their upstream replay behaviour; a replay with no child thread
   in its events is left alone (comparison skipped, no crash). Tests: "refuses a retry
   that names a different target project" (second call names an unregistered project, so
   the request-id sentence proves no admission ran), "refuses a retry that drops the
   target project" (`OrchestratorMcpService.test.ts:2810,2962`).
3. **XPb-3 — driver-kind filter uses the target project** (`OrchestratorMcpService.ts:
   1338-1339, 1372, call site 2466`). Test: "resolves a cross-project driver-kind target
   by the target project's enablement" (A enables only driver X, B only driver Y; from A,
   `target: {projectId: B, driverKind: Y}` with `isolation: "worktree"` resolves to B's
   instance).
4. **XPb-4 — unreachable deleted-project refusal removed** (formerly
   `OrchestratorMcpService.ts:~2492`). The project lookup hides deleted projects
   (`deleted_at IS NULL`), so "deleted" always surfaced as "was not found" and the
   `deletedAt !== null` branch was dead code. The mock-based test now asserts the real
   behaviour ("was not found"); no red run exists for this repair because the branch was
   unreachable — re-adding it and re-running kept the suite green, which is the finding.

Checks after the repairs: five suites 173 passed / 173 (baseline 167 + 6 new), both
typechecks exit 0 with zero `error TS` (one intermediate apps/server typecheck exit 2
from two mock-typing errors in the XPb-2 tests was fixed before these numbers; logs in
the evidence dir). Patch regenerated (`git diff` over the same 10 files, new test
intent-to-added) and proven on the pin with both prior patches applied first:
`git apply --check` exit 0, applied for real exit 0, all 10 patched files byte-identical
to the live clone (`~/.mastermind/mmos_evidence/xpb-20261111/patch_applies_on_pin_plus_two.log`).

Live re-check (same five scenarios as the feature round, re-run against the repaired
clone on a throwaway dev server, port 3915, free probe agent): all five pass — child in
B with subagent lineage, worktree HEAD equal to origin's current head with the marker
present and B's instructions only, retry same thread/task, cancel interrupts, and the
three refusal sentences verbatim; the completion wake reached the parent as its
completed ordinal-2 run (`receipt.wake.parentItems[2]`; the driver's wake-message text
counter reads 0 by a detection-format quirk, not a regression). Receipt:
`~/.mastermind/mmos_evidence/xpb-20261111/live_proof_receipt.json`, port free after
stop.

### Limits, in plain words (feature round)

- Projects are not a permission boundary on one T3 server: `t3_thread_launch` already
  lets a user start a thread in any project, so `target.projectId` grants no reach a
  user did not already have.
- A project with no remote cannot take cross-project workers: the worktree must be cut
  from the project's remote head, and a project whose remote cannot be resolved or
  fetched is refused.
- The worker never sees the target's unpushed commits: the worktree starts from the
  remote's head, not anyone's local checkout.
- Finished worktrees stay in the target repository until someone removes them; nothing
  reaps them automatically.
- Do not roll the server back while a cross-project worker is still preparing.
- With a linked machine, the project id is that machine's.

### Limits, in plain words (panel + steer 1)

- If the server restarts while a worker is still being prepared, that worker is
  cancelled. Calling again with the same request id returns that cancelled task, not a
  new worker. Use a new request id after a restart. (Upstream behaviour for every
  worktree worker: `ProviderRuntimeRecoveryService.ts:83-90, 531-540`;
  `ThreadLaunchService.ts:1116`.)
- If the server is killed between creating the worktree and releasing the run, the
  worktree and its branch stay in the target repository; nothing cleans them up on
  restart (`ThreadLaunchService.ts:694-748` is the only removal). Runbook clean-up
  step: `git worktree list` in the target repository.
- After a rollback to a build without this change, a parent that remembers the new tool
  description gets a plain `invalid_request` for `target.projectId`.
- `resolveRemoteDefaultBaseRef` gives one message for every git failure (no remote, no
  network, not a repository). It fails closed; accepted as is.

### Steer 2 — the "one commit behind the remote" field report

A field report said a worker started with `startFromOrigin: true` got a checkout one
commit behind the remote, twice. Proof test written first
(`ThreadLaunchService.test.ts:1157`, "launches from origin/main with the remote's current
head past a stale tracking ref"): the remote's default branch is advanced from a second
clone after the target repository's last fetch, so the target's
`refs/remotes/origin/main` is verifiably stale (asserted before launch); a launch with
the strict cross-project strategy then produces a worktree whose HEAD equals the
remote's CURRENT head, not the stale tracking ref. **The test passes unmodified** — no
fix was needed, and the test is included in the regenerated patch as a pinned proof.

How it passes: `ThreadLaunchService.ts:416-422` calls `GitVcsDriverCore.
fetchWorktreeBaseCommit` (`GitVcsDriverCore.ts:4690-4706`) BEFORE the base is resolved;
that helper runs `fetchRemote` with a forced scoped refspec
`+refs/heads/<branch>:refs/remotes/<remote>/<branch>` (`:4606-4613`) and only then
`rev-parse refs/remotes/<remote>/<branch>^{commit}` — so the base is always the
just-fetched commit, never the pre-existing tracking ref (the helper's own comment:
"A missing remote branch can leave a stale tracking ref; never resolve it"). A failed
fetch returns null, and with `requireRemoteBase: true` the launch refuses
(`ThreadLaunchService.ts:429-441`) instead of falling back.

What else could explain the field report's "one commit behind": (a) a push that landed
on the remote AFTER the launch's fetch — the worktree head equals the remote head at
fetch time, not at read time, so a report made minutes later can look one behind; (b)
the silent stale-local fallback for launches WITHOUT `requireRemoteBase` — the upstream
limit below; (c) a conventional local-branch base (no `startFromOrigin`), e.g. the
`schedule_task` door, which never fetches.

Same-project `startFromOrigin` path, read and compared: it is the SAME code
(`ThreadLaunchService.ts:401-427` — one `resolveWorktreeBaseRemote`/`fetchWorktreeBaseCommit`
pair serves both), so it has no separate defect. The upstream limit it keeps: with
`startFromOrigin: true` but `requireRemoteBase` unset, a failed fetch silently falls
back to the local `baseRef` (`ThreadLaunchService.ts:423-427`, the fallback the comment
at `:434-435` names; null return at `GitVcsDriverCore.ts:4695-4698`) — recorded here,
not changed, per the steer.

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
6. Panel repairs (lane XPb, glm-5.3): four repairs — orchestrator guard on raw
   cross-project commands (XPb-5), retry-must-name-the-same-project (XPb-2), driver-kind
   filter by target project (XPb-3), unreachable deleted-project refusal removed (XPb-4).
   Red/green logs per repair in `~/.mastermind/mmos_evidence/xpb-20261111/`; five suites
   173 passed (baseline 167), both typechecks exit 0; patch regenerated and proven on
   pin+two (`patch_applies_on_pin_plus_two.log`).
7. Steer 1: no code change; four restart/rollback limits added to "Panel repairs" above
   from the closed panel score (`xp-20261111/panel/SCORE.md`).
8. Steer 2: stale-tracking-ref freshness proof written test-first and passing unmodified
   (no fix needed); mechanism and alternative explanations recorded above; same-project
   `startFromOrigin` shares the mechanism, its `requireRemoteBase`-less fallback recorded
   as an upstream limit. Test included in the regenerated patch.
9. Live re-check of the feature round's five scenarios against the repaired clone:
   all pass (see "Panel repairs"); receipt and run log in the XPb evidence dir.
