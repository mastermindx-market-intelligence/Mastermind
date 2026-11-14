# T3 and Hermes long-horizon hardening; Paperclip adoption assessment

Date: 2026-11-09. Parent source: PR #2375 and `docs/plans/2026-11-09-claude-t3-long-horizon.md`. This report extends, rather than replaces, the original Claude/T3 investigation. The current Chairman assignment also requests Hermes parity, Grok Bot continuity research, and assessment of Paperclip with the existing Hermes bots retained.

## Decision

Build the project-continuity layer once and consume it through the native T3 and Hermes interfaces. Use Paperclip as a candidate management frontend above the existing Hermes runtime, not as a reason to clone bots or introduce another scheduler, memory system or task authority. Prefer a gateway-based pilot that preserves the selected original Hermes session. Keep the Hermes client as a recovery surface until actual pilot acceptance.

This is not a claim of Claude Code intelligence parity, Grok's private implementation, or a bug-free Paperclip client. Model capability, native harness behavior, source composition, installation, and observed product completion are separate claims. The work below substantially strengthens composition and recovery; live provider behavior and full interface migration remain unproven.

## 1. Implemented mechanisms

| Problem | Implemented composition | Existing owner retained |
| --- | --- | --- |
| A side question or refinement erases the mission | Explicit direction classification; side questions/pause/stop cannot rewrite scope or erase progress; refinements/additions retain unmentioned requirements and task IDs | Current user intent and GitHub source plan |
| Agent repeatedly tries the same failed approach | Two consecutive attempts on the same task/hypothesis with no progress advise a changed hypothesis or tactic | Native execution, permission and actual original effects |
| The next useful task is unclear | Dependency-ready ranking by downstream unlocks, with stable source-order tie-breaking and no displacement of an active principal | Existing task plan, native writer and delegate references |
| Code changes make old tests misleading | Changed implementation task IDs reopen that task and downstream evidence, even if requirement text is unchanged | Canonical code/test/evidence owners |
| Context is too large after compaction | Bounded frontier keeps every requirement, task ID/dependency/state, blocker, next action and native reference; full focused-task acceptance remains; off-focus detail stays at the exact source | Same GitHub Markdown plan, not a duplicate state database |
| Restoring context accidentally resumes stopped work | Native stop, pending input, unknown effect, missing capability and budget boundaries dominate continuation advice | Native runtime and Executive/Capacity admission |
| Queueing is confused with steering or Stop | T3 follow-up composition is explicitly queue-next; pause/stop requests require actual native controls and cannot be encoded as pretend interruptions | Existing T3 CLI/MCP client and original ThreadReceipt |
| Hermes changes session ID during compression | Read the same profile's native compression lineage to recover an explicit predecessor binding; forks/resets/delegates do not inherit | Hermes SessionDB, read-only metadata |
| Profiles or unloaded tools expose stale context | Native profile-scoped configuration, empty-argument tool dispatch identity, before/after binding checks, registration leases, collision refusal and retained-handler fencing | Hermes plugin manager and registry |

The shared `long_horizon_guidance` module is deliberately pure. It accepts bounded observations but labels them unauthenticated, returns `execution_authority=false` and `native_action=NONE`, and never dispatches or accepts work. This is not a second admission engine.

### T3 consumer

`integrations/session_bridge/t3_project_context.py` composes the shared source context into the incumbent `HandoffBrief` and existing `T3CliClient` follow-up inputs. It creates no process launcher, connection, identity store, runner or queue. Explicit write scope cannot exceed the plan's path constraints and still requires the incumbent isolated-worktree base. The caller must corroborate the immutable GitHub source ref against the inspected plan bytes.

Tests exercise the real incumbent client with an injected transport: full requirements survive a side question and a progress update; the original native thread is retained; a new queued turn gets its own run; a lost send preserves the original unknown effect rather than retrying it. These are composition tests, not a live T3 model demonstration. The incumbent 8-KiB brief-objective limit remains; oversize input fails explicitly, not by dropping requirements.

The existing `agentos_session_start.py` now shares the same formatter and preserves off-focus blockers, next actions and delegated references. Optional-plan failure retains healthy incumbent Agent OS context. No second SessionStart/Stop system was installed.

### Hermes consumer

`integrations/session_bridge/hermes_project_plugin.py` contributes four native items: a namespaced execution skill, a bounded stable habits section, a per-turn `pre_llm_call` context read, and the read-only `mmx_project_context` tool. The tool has no arguments: the native dispatcher, not the model, supplies session identity. It can be read at task boundaries within a long turn rather than relying on a cached startup summary.

The profile's existing plugin settings explicitly bind a native session to an inspected workspace, source plan, workstream and semantic contract digest. Unbound sessions receive no project context. Only the same profile's native compression lineage can extend that binding to a continuation. No aliases, copied credentials, duplicate profiles or private transcript database are created. A changed/revoked binding or unloaded registration withholds old data even when the read was already in progress.

The package builder copies canonical source bytes into a new build directory and records hashes. It refuses existing destinations and native installation paths. It is not an installer. The actual native manifest parser, plugin loader, skill registration, tool dispatch and unload were separately exercised against disposable state.

## 2. What Grok Bot contributes as a design pattern

Public Grok documentation describes a persistent bot identity, selective lasting memory, reusable skills and scheduled/event-triggered routines. It explicitly distinguishes durable responsibilities and preferences from task-specific messages. It also recommends proving a one-off workflow before turning it into a reusable skill or routine. These facts support the pattern, not a claim that we know its hidden prompts, private scheduler internals or every cause of its observed quality.

The corresponding original Mastermind habits are: retain one long-lived owner for an ongoing responsibility; keep durable preferences separate from current project facts; recover the complete outstanding assignment before acting on a wake; convert verified techniques into bounded skills; and use the existing authorized event/schedule owner only after a real successful task. Storing every conversation token forever is not the objective. Neither a new message nor a wake silently replaces unfinished work or grants a new spend allowance.

Hermes already has many building blocks: native todo persistence, goals, completion contracts, additive subgoals, quality gates, wait barriers, skills, memory and scheduling. Rebuilding these would create conflicting ownership. The new layer connects them to complete project scope and evidence. Native `/goal` replaces a standing objective; `/subgoal` adds to it. `/goal draft` starts a turn and is not an inert preview. Native turn-counter resets are not durable organizational budget resets. Quality-gate shell commands must be explicitly safe and authorized, not harvested from arbitrary plan or web text.

Primary documentation checked during this continuation:
- https://docs.x.ai/grok-bot/bots
- https://docs.x.ai/grok-bot/skills-routines-and-automations
- https://docs.x.ai/grok-bot/how-grok-bot-works
- https://x.ai/news/designing-grok-bot
- https://hermes-agent.nousresearch.com/docs/user-guide/features/goals
- https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks
- https://www.anthropic.com/research/effective-harnesses-for-long-running-agents
- https://code.claude.com/docs/en/goal

## 3. Paperclip: keep the bots, change the management surface

### Actual installed state

A bounded read-only census found Paperclip already partially configured, not blank. The running local server reports version `2026.1106.0`, commit `d69631b01b9c658f80bf8bed389863dce82643e1`, local-trusted/private mode and an existing MastermindX company `a5f907fc-c4b1-478c-a1b1-1748d32206dd`.

Its existing Meta-CEO agent `4e45902f-a976-4e68-b5be-139076e2d461` is paused and uses `hermes_local`. Heartbeat is disabled; wake-on-demand is true. The inspected record had maxConcurrentRuns 20 and no explicit profile environment binding. No setting, bot or company was modified by this work.

The installed upstream adapter package is `@paperclipai/hermes-paperclip-adapter@2026.1106.0`. The gateway execute file was inspected and qualified with SHA-256 `6025c9c15bea0bae236c900f9da23d85e3fdcdea1017e8ffb2dd7434fdfa2c1d`.

### Local versus gateway

The local adapter starts a Hermes CLI child and, in the inspected version, adds `--yolo --print --quiet --worktree`. Session persistence support does not by itself prove the original bot's profile, permission and custody are preserved. Do not unpause the existing local record merely to obtain a demo.

The gateway adapter calls an already-running Hermes API server, retains native run IDs and reads original events/status. It can preserve an explicitly selected existing Hermes `session_id` in `payloadTemplate` with `sessionKeyStrategy=none`. A profile-specific route prefix is preserved. The ordinary issue-key strategy creates stable per-issue context but does not automatically mean adoption of the existing supervisor conversation.

This supports a gateway pilot, not an automatic whole-fleet migration. Resolve the actual profile, original session, existing credential owner and native admission first. Keep one dispatch owner, heartbeat disabled and bounded concurrency. Issue-specific work still requires context isolation; a long-lived bot identity is not permission to mix every issue into one unrestricted conversation. Keep existing Executive/Agent OS/Capacity authority and reuse the organization's existing projection bridge rather than starting a second company/task lifecycle.

### Reliability evidence and limitations

The installed adapter passed six isolated HTTP cases, totaling nine checks: stable per-issue keys; explicit original session and route preservation; recovery from event-stream failure by reading the original run; critical-header protection and redaction; cancellation as failure rather than success; timeout stopping/reading only the original run; authentication denial without fallback; lost create response without automatic replay; and missing run identity as a protocol failure.

These used an ephemeral loopback fixture, not the real Hermes server. A lost real create response can still have executed. The test proves no immediate automatic replay, not global exactly-once behavior across a later heartbeat or new Paperclip run. Native bot adoption and the full Paperclip UI journey remain unproven.

Public issues are investigation leads, not proof the installed system is broken. For example, Paperclip issue #8713 reports an overlong Codex prompt-cache key. The inspected installed Hermes source already contains `_bounded_prompt_cache_key` in `agent/transports/codex.py`, which preserves short keys and hashes overlong ones to a bounded value. That source observation is not an end-to-end Codex-provider proof, but it prevents falsely labeling an already-fixed installed path as necessarily broken.

The actual live Hermes health endpoint reports application version 0.23.0 and process commit `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`; the installed source checkout used for API qualification is newer. The relevant compared plugin/compression tracked paths were unchanged, but actual live loading of the new plugin was not observed. One bounded read of the possible run route timed out; it establishes neither endpoint absence nor successful authenticated admission.

Primary adapter source and investigation lead:
- https://github.com/paperclipai/paperclip/blob/master/packages/adapters/hermes/README.md
- https://github.com/paperclipai/paperclip/issues/8713

## 4. Verification and exact provenance

The authoritative receipt is `docs/evidence/2026-11-09-t3-hermes-horizon-qualification.json`. It records actual commands, result objects, exact candidate file hashes, native API fingerprints, dirty native paths and the distinction between installed APIs and live-agent behavior.

- **402 focused tests and 90 subtests passed** across the source-plan, startup, guidance, Hermes composition, T3 client/composition and affected identity-guard suites.
- **11 installed Hermes native API checks passed** using real PluginContext/PluginManager/registry/SessionDB and temporary profiles. This includes real leased compression, fresh-manager restart, same-ID profile isolation, fork/delegate/reset exclusion, revocation, retained-handler fencing, actual packaged manifest loading and native unload.
- **9 installed Paperclip adapter checks across 6 HTTP fixture cases passed**. No production company/agent changes or live Hermes runs occurred.
- Python compilation, Node syntax validation and `git diff --check` passed.

Hermes source HEAD was `ba4ddf9945a213ede9dda016602a86591ed634f9`, qualified together with actual API-byte fingerprint `ed210718c3e210e3889c8584ae7f0f5687d7b7395515d033cc7b789fb2cb9d37`. The checkout contains another writer's added `provide_gateway_turn_context` hook declaration in `hermes_cli/plugins.py`; it was preserved, included in the fingerprint and not misrepresented as pristine upstream. Isolated native plugin-host proxy mode and live model obedience were not qualified.

The initial bare-interpreter qualification encountered Hermes's native bootstrap relaunch path. Its owned process was stopped and reconciled. The successful qualifier now requires the installed committed dependency-environment interpreter, refuses optimized assertions, disables lazy installation only in its own process and rechecks native bytes afterward. No production provider environment was switched.

A pre-existing hosted CI failure on PR #2375 came from two unchanged 500-character input-limit literals whose lines moved after merged #2365. The exact upstream change added named manual-pool options; the finite guard entry was updated to the inspected file SHA and new locations 57/280. Drift-negative tests remain. No additional literal was exempted, no required check was bypassed, and no independent approval was claimed.

A bounded paid Fabric public-source census was attempted once: `horizon-paperclip-adapter-census-20261109`. It ended FAILED/TURN_LIMIT without useful evidence and was not replayed. Principal investigation supplied the findings in this report. No worker is represented as still running.

## 5. Editable Mastermind OS design

The original accepted LH01/LH02/LH03/LH06 boards are retained. Added and visually inspected **LH07 - Agents - Shared continuity + Paperclip**, node `1SJE-0`, on page `p-X-0` in file `01M3NRCX55B452A12819WNE1RH`. The board preserves the existing Atelier shell and specifies shared T3/Hermes task context, profile/session lineage, no-progress and evidence habits, an explicitly paused Paperclip pilot, retained bot identity, one dispatch owner, native recovery and live-proof requirements.

The edit and screenshot readback were observed; the owned working indicator was released. This is an editable build contract, not a deployed UI or native mobile implementation. No accepted unrelated board was overwritten.

## 6. Remaining live acceptance and exact next actions

Protected merge, selected installation, live model progression and UI acceptance are still separate. Source cannot honestly be called fully operational until the actual selected native consumer loads the skill/context, preserves the full project through a side question and refinement, completes dependency-ready tasks, survives real compaction/restart, and honors stop, budget and original-effect recovery.

For T3, use the existing native/Capacity integration owner and original project/thread contract; the adjacent #2374 owns its live session-control surface. Do not use generic host-shell tools as an agent-handoff substitute, impersonate a native parent, change providers or duplicate the running engineering program.

For Hermes, release the exact source package through the existing plugin installer, select the real bot/profile/session and explicitly bind the source contract. Keep the profile's existing admission, memory, credentials and wake owner. Exercise a real task and capture original native run/result evidence. This report does not claim that installing an inert package is the same as live consumption.

For Paperclip, use the existing paused Meta-CEO record for a bounded gateway pilot only after the real bot/profile/session and credential/admission route are resolved. Verify same-bot memory/identity, separate issue context, interruption, cancellation, reconnect, stop and one-owner scheduling, then decide whether to replace the desktop client. Never infer that a cleaner management UI repairs all backend behavior.

The original Secretary thread acknowledged the native acceptance request and reported a provider stand-down. Its cited c4 source brief did not itself establish the reported hold; treat this as a reported boundary requiring the actual owner to clarify, not a fabricated global prohibition or permission to override it. Return actual execution evidence or the precise current gate to PR #2375 and that same thread. Delivery and pickup are not acceptance.
