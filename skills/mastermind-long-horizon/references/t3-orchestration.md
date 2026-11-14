# Native T3 orchestration and communication

Contents: Recover before delegating; complete child briefs; original returns; communication; reasoning; whole-goal continuity.

## Recover before delegating

Use the existing source mission, admitted native parent and Capacity Fabric. Read
actual `orchestrator_capabilities` and `tools/list` from that same connection.
An outside-agent connection has no native parent merely because a prompt supplies
its thread ID. Never impersonate a parent or turn a shell/process tool into an
agent-handoff interface. `NativeParent` in
`integrations/session_bridge/t3_orchestration.py` checks the server-returned parent
and Capacity identity before native child-only calls.

Keep the principal focused on decomposition, integration and acceptance. Route
bounded implementation/research labor through the already-authorized paid Fabric.
Use native children for coordination or reasoning only when their existing grant
and budget permit it. A nested child or a second provider is not a recovery path
for a denied/unknown effect. Reuse admitted workers; do not spawn a new agent for
every question, test failure or context limit.

## Give children a complete but bounded assignment

A native `delegate_task` child receives the task text, not all parent history.
Include the immutable source, original DONE_WHEN, assigned phases, exact allowed
paths, evidence required, non-goals, stop/budget conditions and return destination.
Use the existing `MissionBrief` and `ChildBrief` when available. Never shrink the
parent's acceptance to a child's deliverable.

For code-writing children use native `isolation: worktree`. It starts from the
parent's current committed state; uncommitted changes are not transferred. Verify
that base against the intended source before relying on it. A base SHA written
in a brief does not change or authenticate the checkout. No-write shared children
have narrower task scope, not magically enforced read-only permissions.

Before parallel work compare exact writable subtrees, shared contracts, migrations
and generated outputs. Ancestor/descendant path overlap requires coordination even
when branches differ. The provided collision check is advisory, not a lease,
reservation or proof that two logically coupled changes can merge independently.
Keep the fan-out small enough to consume every return within the current budget.

## Preserve native identity and consume original returns

Retain the actual task ID, child thread, original run, parent connection and mission
fingerprint. Use async delegation when independent work remains. If the native
runtime reports that completion will wake the parent, follow that return contract
rather than creating another polling loop or watcher.

`task_status` is not a harmless read: T3 marks the result delivered. A lost response
is an uncertain delivery effect. Reconcile it through the original owner; do not
blindly replay, substitute the latest thread answer or invent consumption.

A completed child turn can still have live descendants. Require original-run
identity, `workState=result_available`, no pending child work/question/approval,
matching terminal status and a retained result before evaluating acceptance.
`result_ready_for_parent_review` is not `accepted`. Verify changed code, actual
checks and original consumer criteria before recording parent acceptance.

## Communicate deliberately

Use explicit message kinds: question, progress, blocker, result, correction or
direction. Include the original mission fingerprint and concise source reference.
A question requests information without replacing the assignment. A correction
identifies the affected evidence and next action without silently expanding scope.

Use `t3_thread_send` with an explicit supported mode:
- `queue`: a later turn, with its own run identity; receipt is not pickup.
- `steer`: current-run direction only when an active native run was observed.
- `restart`: a deliberate native lifecycle action, not the default for a question.

Pause/Stop are native controls, not queued words. `task_cancel` is broader than one
run interruption: it stops the selected task's running/queued turns, delegates
and watches, including later work in that child thread. Use exact-run interruption
when that is the intended scope. A cancellation request is not terminal shutdown.
Do not answer a native permission approval as if it were a routine user question.

## Reasoning that the model actually supports

Read the selected model's advertised option IDs and allowed values. Set only an
explicit supported value; do not guess aliases such as max, xhigh or thought_level.
Omission inherits the native selection; an explicit empty option set clears it.
Preserve unrelated options, provider, model, permission mode and interaction mode.

Use stronger reasoning for ambiguous architecture, difficult debugging, critical
integration and acceptance review. Prefer a smaller effort for mechanical reads,
formatting and already-specified edits. Avoid multiplying maximum effort across a
wide fan-out. A setting is not evidence of improved reasoning or provider obedience.
Report decisions, assumptions and useful concise rationale, not hidden reasoning
streams or raw thinking transcripts.

`set_reasoning` performs idle/delegated-work checks and exact readback through the
existing native configure tool. Its preflight is not atomic server CAS. Do not
change a running user thread, silently switch providers, reset a budget or interpret
an unsupported option as a reason to enable another account.

## Whole-goal continuity

Keep a compact active frontier: objective, all outstanding criteria, current task,
known original effects, admitted children/returns, accepted evidence, next action
and remaining budget boundary. Save it to the existing source notes/plan at real
milestones and read it back. Do not replace source authority with a scratch list.

Reconcile a new user message as a side question, refinement, addition, explicit
replacement or native stop. Preserve unmentioned requirements and outstanding
children. In the inspected T3 API there is no assumed generic goal-setting verb;
use actually available provider goals/task tools or the bound source plan. Do not
invent `t3_goal`, install a Stop-hook loop, or create another scheduled task merely
to keep the conversation alive.
