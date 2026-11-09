# Claude-style long-horizon work: research, implementation and OS contract

Date: 2026-11-09. Assignment: investigate Claude Code's long-horizon harness, implement the reusable parts in Mastermind's existing T3 integration, and update the editable Mastermind OS design. This report distinguishes documented mechanisms, source inspection, implemented code, executable verification and live-provider acceptance.

## Decision

Reuse the native T3/Claude machinery; add the missing source-plan continuity layer rather than create another agent runtime. A task list alone is not the mechanism that keeps an agent working. The useful composition is a complete requirements/acceptance inventory, dependency-ready bounded focus, durable progress, verified intermediate outcomes, context restoration, and a native continuation condition that respects permissions and explicit stops.

The implementation adds a read-only plan projection, extends the incumbent SessionStart context hook, supplies Claude/Codex-discoverable workflow skills, and opts the repository into Claude's documented task tools. It does not fork T3, install a competing Stop-hook loop, change provider accounts, or establish a second task database. The four Paper boards specify how the eventual embedded T3 experience should expose these semantics.

## 1. What Claude Code actually provides

### Planning is different from task tracking and continuation

`EnterPlanMode`/`ExitPlanMode` separate approach design from implementation. `TaskCreate`, `TaskUpdate`, `TaskList` and `TaskGet` represent actionable work and dependencies. They make progress explicit, but their existence does not guarantee that the model will finish the parent project. Current documentation makes task-tool availability model-dependent and exposes `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` as the opt-in. We enable that one variable in this repository without changing its model, permission mode or other settings.

Sources: [tools reference](https://code.claude.com/docs/en/tools-reference), [interactive mode](https://code.claude.com/docs/en/interactive-mode).

`/goal` is a separate mechanism: after a turn, an evaluator checks a completion condition and can trigger another turn. The condition replaces any prior goal in that session, so a narrow task goal must not silently replace the whole assignment. The evaluator judges the transcript; it does not independently inspect the filesystem or execute tests. Consequently, a goal verdict is not equivalent to externally verified acceptance. Goal activation does not expand permissions. Clearing a goal, stopping, and continuing a conversation are distinct operations.

Source: [goal documentation](https://code.claude.com/docs/en/goal).

### Context management is not a task ledger

Compaction reduces conversation context, but critical requirements and outstanding work need durable, explicit representation. Session resume restores a native conversation identity; project instructions and skills supply reusable behavior. These have different jobs. A stale summary is not authority to discard a requirement, replay an interrupted write or resurrect an explicitly stopped goal.

Sources: [how Claude Code works](https://code.claude.com/docs/en/how-claude-code-works), [memory](https://code.claude.com/docs/en/memory), [skills](https://code.claude.com/docs/en/skills).

Hooks offer lifecycle integration, including session startup/compaction and tool or completion events. They can inject context and enforce checks. An indiscriminate Stop hook, however, can create a second continuation loop alongside the native goal mechanism. This implementation extends the existing SessionStart adapter only; it registers no global hooks and adds no Stop hook.

Source: [hooks reference](https://code.claude.com/docs/en/hooks).

Subagents isolate high-volume exploration in separate contexts and return bounded results. They are useful for independent investigation or verification, not an excuse for the principal to forget the original assignment. One principal focus does not forbid parallel independent work. Original child/thread/run receipts must be retained and read before replacement or retry.

Source: [subagents](https://code.claude.com/docs/en/sub-agents).

### The engineering pattern behind reliable long runs

Anthropic's long-running-agent experiment separates initialization from incremental coding. A full feature list, progress artifacts, small coherent changes and verification counter two observed failure modes: attempting too much at once and declaring the entire project finished after partial progress. These are reported engineering patterns, not a claim about inaccessible proprietary Claude Code internals.

Source: [Effective harnesses for long-running agents, 2025-11-26](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents).

A later application-building experiment uses planner/generator/evaluator separation and structured handoffs. It also illustrates that context-reset and evaluation choices have model-dependent tradeoffs and overhead. We adopt explicit completion evidence and bounded task transitions, not a blanket requirement to spawn a separate reviewer for every edit. Actual repository review/security/release controls still apply.

Source: [Harness design for long-running apps, 2026-03-24](https://www.anthropic.com/research/harness-design-long-running-apps).

## 2. Exact T3 donor/incumbent comparison

Inspection pin: `pingdotgg/t3code@2b65ffb641f152fadf443096bad7f4a0677caae4`. Do not infer that every installed provider or version exposes every capability seen at this source revision.

| Mechanism | Existing T3 seam | Composition decision |
| --- | --- | --- |
| Claude task projection | `apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.ts`: task list mapping, TaskCreate/TaskUpdate/TaskList handling and plan steps | Reuse; do not create another native task API. |
| Claude goal display/restore | Same adapter: `nextClaudeGoal`, goal acknowledgements and state projection | Keep native goal identity; a source plan does not activate a goal. |
| Provider continuation | `apps/server/src/orchestration-v2/ProviderContinuationService.ts` | Preserve native dispatch, disabled-instance handling and original identities. |
| Restart recovery | `apps/server/src/orchestration-v2/RestartContinuation.ts` | Preserve native bounded restart chain and stop/permission constraints; no custom restart daemon. |
| Plan UI | `apps/web/src/components/chat/ProposedPlanCard.tsx` and mobile equivalent | Extend the product presentation around these concepts, not duplicate the runtime. |
| Outside-agent access | `docs/user/outside-agents.md`, `docs/orchestration-v2/orchestrator-mcp-server.md` | Prefer existing MCP; authorized host CLI remains a host-assisted path, not cloud-direct OAuth proof. |
| Provider-specific settings/skills | Claude adapter and `docs/user/providers-claude.md` | Repository-local discovery wrappers; verify loading separately from file creation. |

Source root: [exact T3 revision](https://github.com/pingdotgg/t3code/tree/2b65ffb641f152fadf443096bad7f4a0677caae4). In the inspected adapter, task mapping appears around lines 4688-4835, and goal parsing around 2078-2141. The continuation service explicitly handles disabled instances; restart recovery limits repeated restart chains.

## 3. Implemented source

### Read-only source-plan adapter

`integrations/session_bridge/project_task_context.py` parses exactly one `mastermind-plan` JSON fence in the existing GitHub-owned Markdown plan. It does not create another registry or execute anything.

The schema requires the full objective, stable requirement IDs, allowed paths, non-goals, task IDs, dependencies, per-task acceptance criteria, editorial states and evidence references. Every requirement must remain covered. Duplicate IDs/JSON keys, unknown references, dependency cycles, multiple principal foci and malformed shapes are rejected explicitly.

The projection identifies dependency-ready work and preserves an active principal focus. A blocked dependency does not hide an independent task. Delegated in-progress work needs its original native reference and is not silently rescheduled as a new principal task. When only delegated work remains, the suggested action is to read the original delegate, not launch another one.

A task definition digest includes its own requirements/criteria and upstream definitions. Changing a task or requirement invalidates affected downstream evidence while retaining unrelated accepted work. A claimed completed descendant cannot satisfy a dependency while its ancestors remain incomplete.

Evidence coverage is deliberately weaker than evidence authentication. Every projection declares `execution_authority=false`, `evidence_authentication=NOT_PERFORMED`, `mission_accepted=UNOBSERVED` and `runtime_revalidation_required=true`. A plausible reference or passing task label is not a release authorization. All tasks being source-complete yields `REVIEW_PARENT_ACCEPTANCE`, not mission success.

### Two source-binding modes

An exact byte digest is suitable for a fixed review or launch input. A semantic contract digest binds requirements, definitions and scope while allowing ordinary progress/evidence updates. Every read still returns the current source digest. A changed contract is a typed error; it is never silently repinned. A comparison reports removed/changed/unchanged tasks and whether scope review is required, without treating a decision link as authenticated approval.

The reader is confined to an explicit `docs/plans/*.md` path under an assigned workspace. It uses bounded reads, regular-file checks, no-follow directory/file traversal, nonblocking opens, before/after metadata checks and size limits. Symlinks, FIFOs, arbitrary paths, stale revisions, wrong workstreams and oversized context fail explicitly. No scan of ambient credentials or provider configuration is part of this module. Platforms without the required safe-open primitives fail explicitly rather than fall back to an unsafe read.

### Existing context hook, not another one

`integrations/session_bridge/agentos_session_start.py` accepts the optional plan binding and composes it with the existing Agent OS context. Existing invocations without a plan are unchanged. Startup, resume, compact, clear and fork events are covered. Cross-workspace injection is refused. Compact context retains the full requirement inventory and task identities, with full detail for the current focus and exact-source pointers for off-focus acceptance details.

A missing/stale/malformed plan produces a visible degraded reason rather than an empty successful plan. A healthy incumbent Agent OS bundle is retained when the optional plan fails, within the existing delivery bound. Restoring a plan never restores permission or activates an explicitly cleared goal. Registering the hook for an assigned workspace remains a separate native action; this source change does not modify global user settings.

### Reusable native-discoverable workflow

The canonical skill is `skills/mastermind-long-horizon/SKILL.md`, with integration details in its `references/` directory. Thin repository wrappers live in `.claude/skills/mastermind-long-horizon/` and `.agents/skills/mastermind-long-horizon/`. The latter is the Codex skill discovery surface; see [OpenAI Codex skills](https://developers.openai.com/codex/skills).

The workflow is: preserve the entire assignment; select one ready bounded task; implement; verify; save/read back evidence; reassess the parent outcome; continue useful safe work. It distinguishes side questions, additions/refinements, explicit scope replacement, pause and stop. It instructs the agent to read existing native tasks before creating projections and retain original delegation/run references. It does not impose a new review ceremony or override repository controls.

`.claude/settings.json` changes only the documented task-tool opt-in. It leaves the model, permission mode and existing environment entries intact. No global skill installation, provider route, credential, background watcher or runtime service is created by this diff.

## 4. Mastermind OS editable Paper implementation

File: [Mastermind OS](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/). The new boards reuse the established Code/Atelier shell and existing Noir tokens. Existing accepted boards are untouched. All four added boards have editable layers rather than flattened screenshots.

| Board | Exact node | Page | Purpose |
| --- | --- | --- | --- |
| LH01 - Code - Long-horizon focus | `1MO8-0` | `p-U-0`, 17 Code workspace Product | One active task, entire project plan, latest direction retained, evidence progressively disclosed. |
| LH02 - Code - Plan and acceptance | `1N1Y-0` | `p-U-0` | Dependencies, criterion-level proof, unfinished requirements and scope-change preview. |
| LH03 - Code - Recovery and boundaries | `1N5Q-0` | `p-W-0`, 17A States | Interrupted action, preserved plan, read-only original-run reconciliation and no duplicate send. |
| LH06 - Code - Long-horizon integration | `1N9I-0` | `p-X-0`, 17B Build | Component/owner mapping, state-action matrix, scope pin semantics and rollout acceptance. |

The product journey goes from project outcome to focused task to evidence, then to the next ready task. The plan remains attached when a side instruction arrives. A scope edit previews the delta and reopens only affected proof. Evidence and activity remain collapsed in the default quiet view; the product does not expose a wall of reasoning.

Desktop uses an adjacent plan rail; the build contract specifies a plan drawer on mobile. This change does not claim a new mobile runtime implementation. Existing native mobile plan components are the intended reuse seam.

Controls must reflect capability: `Queue next` is not `Steer now`; `Pause goal` is not `Stop turn`; restoring source context is not resuming execution. On an uncertain effect, the sole recovery action reads the original run. Missing source/provider/permission states retain visible scope but do not fabricate actionable controls. A blocked lane does not hide independent permitted work. The builder contract requires source proof, installed behavior and product acceptance to remain separate.

Visual verification: exact-node screenshots were reviewed at 1x for LH01, LH02, LH03 and LH06, including legibility, layout, clipping and state/control consistency. Paper reported `APPLIED_RESPONSE_OBSERVED` for the owned mutations. Document drift was reconciled before a renamed-node operation; no unknown write was replayed. The token hash is not treated as a document revision or exclusive lock.

## 5. Verification and installed boundary

Final focused command `python3 -m pytest -o addopts='' -q tests/test_project_task_context.py tests/test_agentos_session_start.py` returned **102 passed in 2.61s** (Studio process 54770, exit 0); `git diff --check` passed. These checks cover the new projection and incumbent startup hook: complete scope, fresh evidence coverage, dependency ordering, stale evidence, affected-subgraph invalidation, independent blocked lanes, delegated original references, principal focus conflicts, source pinning, safe paths/symlinks/FIFOs, context size, malformed input and startup/compact/resume/clear/fork behavior. Changed acceptance text, dependencies and task titles require scope review; normal state/evidence progress does not.

Installed observations on the authorized M2 host:

- T3 Code (Beta) reports version `0.1.7`; native CLI is `/Users/chriswong/.t3/bin/t3`.
- Native thread listing succeeds for existing Mastermind project `bc18d268-d100-484a-8952-3ce2b0b0a66b`, environment `5f4cd5f0-e3df-407d-af02-1aa833637937`.
- The managed source worktree is not itself a registered T3 project. The existing project's root is `/Users/chriswong/Documents/Cluade/Mastermind`, a separate checkout; this is not the managed GitHub worktree.
- The inherited default selection points to `GLM2 / glm-5.3`, while that provider is disabled. Its configured fallback is also disabled. This is configuration drift, not proof that T3 is broken or a security denial.
- Enabled Capacity Fabric-backed instances exist, and a separate user-owned engineering program is running on one. This lane does not alter its provider settings, interfere with that run, or assume its budget/route is ours.
- The exposed Executive continuation target list for Claude is empty; no target or dispatch receipt is invented. No provider launch, global hook installation, automatic goal activation or live-model behavior acceptance is claimed by the source tests. No disabled instance was re-enabled and no alternative account was selected to manufacture a passing canary.

A local read-only metadata query was used only to resolve project IDs and enabled/default provider flags missing from the CLI discovery surface. It did not read credentials, reproduce OAuth, or mutate runtime storage. Subsequent project/thread identity was verified through the native CLI. Empty linked-environment output was not mistaken for absence of a local environment.

## 6. Activation and remaining consumer proof

After protected source delivery, consume the exact accepted head in a clean, owned T3 worktree. Reconcile the project's inherited provider selection through the existing T3/Capacity owner; do not change a live writer's configuration or infer permission from this report. The native canary must then prove:

1. The actual provider discovers `mastermind-long-horizon` from the appropriate repository wrapper and reads the canonical skill, rather than merely echoing a pasted description.
2. The assigned source plan loads at the expected workstream and semantic contract; an actual scope change is rejected while ordinary progress updates remain readable.
3. The provider handles a bounded multi-task fixture in dependency order, preserves an unrelated requirement after a side question, and does not repeat a completed independent task.
4. Session restoration preserves native thread/run identity and remaining scope. Explicit pause/stop remains stopped. An uncertain effect is read back at its original target before any further action.
5. All source tasks being done still requires actual end-to-end acceptance evidence. The eventual OS consumer renders LH01-LH03 with the same identities, state semantics and real receipts.

The consumer must use T3's existing native continuation and request handling. Native CLI send queues a next turn when busy; it is not evidence of immediate steering. Use existing approved route/model limits and inherited permissions; a read-only canary cannot grant itself a stronger runtime mode.

Rollback is source-scoped: remove the wrappers and task-tool opt-in, and stop passing plan-binding flags to the incumbent hook. The adapter creates no runtime state to migrate or delete. Existing T3 threads/tasks, Agent OS records and evidence remain untouched. Do not remove another owner's hooks or configuration.

## Provenance and non-claims

Procedure pin: `Mastermind@494d095813dad415938800fa0e4d2719497738fa`. Product doctrine: `macro@55c3b6c0afa0757d11487375c88572fa94f84561`. Source operation: `claude-t3-long-horizon-20261109`. Organizational linkage remains `PLAN_NOT_ORG_LINKED` until its actual owner returns a link; source planning is not runtime admission. Adjacent PR #2372's T3 web client and #2345's embedded OS implementation remain disjoint.

This is an original implementation of documented patterns, not extracted proprietary Claude source. No task completion label, source test, design board or PR status is presented as proof of deployed autonomous behavior. Native-provider and eventual embedded-OS consumer proof remain explicit until their real receipts exist.
