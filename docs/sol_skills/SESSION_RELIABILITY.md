---
schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
skill: session_reliability
---

# SESSION RELIABILITY — Preserve Work Across Tool and Conversation Failure

Companion for long, tool-heavy, multi-source, process or recovery work. It extends,
never replaces, `ACTIVE_EXECUTION.md` and
`docs/EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW.md`.

## Mission

Lose no deliberate work and duplicate no modifying effect across model, connector,
browser or process failure. Chats are disposable; canonical state and compact durable
checkpoints preserve responsibility, not infinite chat life. Existing Executive,
Agent OS, GitHub, RuntimeBinding, provider and custody owners remain authoritative.
No transcript/lifecycle database, retry ledger, queue, alternate binding writer,
memory or transport authority is introduced.

## Active-turn frame

Reuse ACTIVE_EXECUTION's ephemeral frontier, adding only diagnostics needed now:
`SESSION_HEALTH`, `FAILURE_LAYER`, `ACTIVE_PHASE`, `PHASE_DONE_WHEN`,
`ALLOWED_SURFACES`, `DEFERRED_NONBLOCKING_FINDINGS`, `LAST_DURABLE_CHECKPOINT`,
`CURRENT_TOOL_OR_PROCESS_IDENTITY`, `CURRENT_SELECTED_MODE_AND_CAPABILITY_EVIDENCE`,
`UNRESOLVED EFFECTS`, `CUMULATIVE_RAW_OUTPUT_ESTIMATE`, `EXACT_NEXT_ACTION`.
Not a second mandatory form, per-tool checklist or persistent state store.

## Semantic phase discipline

**Recovery gap, not run length** is the invariant: unrecoverable accepted work should
not exceed the current coherent phase. **Depth is allowed; breadth is fenced.**
Necessary calls/time are not stop triggers. Broad exploration needs a named phase
question and stopping condition; defer nonblocking discoveries. One blocker permits
one bounded blocking subphase; a second broad blocker requires re-evaluation.
Apply ACTIVE_EXECUTION 7A/8 after each phase: verify/save, reassess and start the next
safe authorized critical-path phase in the same healthy turn. A task/checkpoint
alone is not a stop.

## Session-health classifications

### `SESSION_HEALTHY`

Normal bounded tool output, no unresolved process/effect, current durable material
frontier and a conversation that can safely continue.

### `ROTATION_SUSPECTED`

One terminal generation failure or tool timeout; output pressure with stale frontier/
unbounded retrieval; unrecoverable material work that cannot be saved; or unstable
connector/browser/provider behavior. Reconcile the exact request once. Freeze only
dependent uncertain work; read-only timeout or proven pre-dispatch failure does not
bar independent edits/tests. Save at a coherent milestone and reduce output.

Stop all modifications only for an unsafe surface or when all work depends on the
unknown effect. A justified visible mode change may aid technical recovery, but
proves neither cause nor rotation and grants no permission or carrier transfer.
Output pressure alone does not change `SESSION_HEALTHY`: with reconciled effects,
current frontier and bounded work, select/compress further output and continue beyond
soft targets. A clean phase alone is not continuity pressure.

### `ROTATION_REQUIRED`

Require rotation after two consecutive terminal generation failures with no successful intervening turn;
resume failure immediately following unresolved timeout/taint/`EFFECT_UNKNOWN`;
unsafe surface, including `Thinking failed` in an already heavy/unstable chat; or
explicit Chairman retirement. Stop execution there; do not keep issuing Continue.
Preserve PID/request/process/carrier/effect and use one fresh successor with the
compact capsule and minimum fresh reads, following the sequence below.

**Thinking failed != context exhausted**: a single failure may justify suspicion,
not a private provider-limit claim.

## Tool-output and command budgets

Engineering **pressure indicators and checkpoint prompts, never hard productivity
ceilings**. Healthy bounded work may exceed soft targets after selective retrieval
and durable saves. These are not provider limits or mandatory short turns.

### Per response

Soft **8 KiB or 150 lines**; hard **16 KiB**; search **100 matches**. Larger results
need a bounded excerpt, total bytes/lines, truncation flag, digest and cursor.

### Per active turn

Raw-output target **32 KiB**. ACTIVE_EXECUTION recovery-gap law controls milestone
saves; no tool-call counter triggers a checkpoint, authority recap or stop.

### Commands and processes

Normal timeout **15 seconds**, hard default **30 seconds**. Long work returns PID
and typed status. No unbounded home/temp/support/multi-repo recursion or unfiltered
process/log/metrics dump. Use exact roots, `git grep`, `find -maxdepth`, selected
`jq` fields, bounded output and cursors.

## Timeout and process continuation

On timeout: preserve exact PID/command/carrier/effect; start no replacement or
equivalent broad command; read status/output once; deliberately retain or terminate
only that process; verify; checkpoint before broad work. A timeout is never permission
to replay the command. `EFFECT_UNKNOWN` stays on its original carrier until canonical
readback proves accepted, conflicted, absent or still unknown.

## Connector taint

A tainted generation receives no more work. Return one compact typed error without
old raw payloads, retaining PID/action/effect and original carrier/connector generation.
Reconcile using a fresh generation of that carrier. Fresh generation is not failover
or permission to replay.

## Conversation-context discipline

Use exact ranges/fields when sufficient, not full files, PR bodies, logs, metrics,
schemas, process tables or repeated evidence. Return identity/query, findings, bounded
excerpt, size, truncation and cursor/artifact. raw tool history is not a continuation
manifest. Never reconstruct or replay private reasoning or the full prior tool
transcript after interruption, compaction, or rotation.

## Compact continuation capsule

Target maximum **12 KiB / 1500 words**:

```text
MISSION
CANONICAL OWNERS AND IDENTITIES
PROTECTED SHA + SKILLPACK ID
VERIFIED CAPABILITY LEDGER
LAST CONFIRMED EFFECT
UNRESOLVED EFFECTS / PIDS / REQUEST REFS
CURRENT WORKSPACE / BRANCH / PR
WHAT MUST NOT BE REDONE
EXACT NEXT ACTION
RECOMMENDED NEXT MODE + REASON (when material)
ACCEPTANCE AND STOP CONDITION
```

Retain conclusions/identities, not private reasoning, secrets, logs, payloads or stale
memory claims. Agent OS owns organizational truth; GitHub implementation evidence;
Executive lifecycle. Planned retirement needs durable continuity first. A checkpoint
transfers no custody, lease, RuntimeBinding or STARTed operation.

On persistence failure, do not loop. Emit one `NOT_CANONICALLY_PERSISTED` frontier
with last durable ref, uncertainties/effects, DO_NOT_REDO, next action and relevant
mode recommendation. Apply ACTIVE_EXECUTION 8's exact cause mapping: `EFFECT_UNKNOWN`
only for an ambiguous checkpoint write; `EXACT_HUMAN_GATE` only for a real human/admin
ceremony; a proven pre-dispatch persistence/platform outage is `ALL_SCOPED_LANES_BLOCKED` only without safe useful work; `MORE_WORK_EXISTS` when safe independent work remains. This is not a verified checkpoint. A successor
must reconcile and persist it before using it as durable truth.

## Failure-layer classifier

Diagnostic boundaries, not new Executive lifecycle states:

### `STREAM_ATTACHMENT_UNCERTAIN`

A detached UI/client stream, red-exclamation/unavailable resume stream or visible stop does not prove
the underlying request/process ended. Reacquire/read observable state before any Continue
or effect; do not duplicate Continue or effects merely because the client detached.

### `TURN_EXECUTION_ENDED`

The turn ended but chat/workspace/process may remain valid. Reconcile PID/action/effect; resume the same conversation on the next turn.

### `SESSION_UNSTABLE`

Heavy/unstable conversation or repeated terminal failures: Persist the frontier, seal predecessor and use a fresh same-mode chat through the rotation owner. Switching
mode is not substitute compaction.

### `WORKSPACE_OR_EFFECT_UNCERTAIN`

Files/process/request/branch/effect may survive the chat. Preserve exact original
identity. `EFFECT_UNKNOWN` blocks replay, mode movement, receiver change and rotation
until same-carrier reconciliation.

## Mode-specific continuation defaults

Astra Pro stays in the healthy chat with observed continuity/self-compaction, not
scheduled rotation. Extra High **10–20+ minute** bounded tool phases and Sol Pro
**30–50m+** productive turns may extend while safe. Sol stickiness across substantial
turns and the observed 2–3-turn renewal rhythm are practical defaults, **not a timer
law**. A materially heavy Sol chat checkpoints to a fresh successor. Do not bounce
a mature chat between modes for tools; genuine heavy-chat cross-mode need uses a
durable fresh-chat boundary. These are empirical defaults, not platform guarantees;
elapsed time alone never establishes `ROTATION_REQUIRED`.

## Failure triage

### Failure inside one tool call

A tool/host boundary: reconcile exact PID, action, carrier and effect.

### First terminal generation failure after a completed tool call

Low pressure plus reconciled effects permits `ROTATION_SUSPECTED` and at most one
bounded recovery, possibly a justified mode change. Already heavy/unsafe surface
requires `ROTATION_REQUIRED` instead. Thinking failed proves no context exhaustion.

### Second consecutive terminal generation failure

`REPEATED_TERMINAL_GENERATION_FAILURE` requires `ROTATION_REQUIRED`; stop this chat.

### Fresh conversation fails before its first tool call

Investigate platform/browser/account/model/device/network/extensions: current provider
status, hard-refresh/restart, clean/private browser profile and comparative browser/model/
device/network. Do not move unresolved effects to another carrier.

### Failure persists across clean environments

Collect a sanitized support packet: timestamp, observed model/mode, conversation/request ID when shown,
browser/version, environment comparisons, HAR and console errors. excluding credentials, private payloads and unnecessary confidential evidence.

## Closeout and rotation sequence

Material continuity pressure may justify `CHECKPOINTED_CONTINUATION` at a semantic
boundary and same-chat next-turn resume. Otherwise a clean phase is save-and-reassess:
start the next useful authorized phase in the same healthy turn. For actual
`ROTATION_REQUIRED` or explicit retirement:

1. Stop new modifying effects.
2. Reconcile existing effects/timed-out processes by exact identity.
3. Persist completed material results to canonical owners.
4. Save/refresh the compact capsule.
5. Establish the exact surface's closed rotation reason.
6. Retire only after durable continuity exists.
7. Use one successor through the existing rotation owner.
8. Load protected procedure and minimum fresh canonical state.
9. Resume the exact action, retaining DO_NOT_REDO.

`CONTEXT_ROTATION` is a procedural continuation transition, not finalization/lifecycle,
success or acceptance; mission remains active. Valid durable turn boundaries use
`CHECKPOINTED_CONTINUATION`. UI mode/fresh-chat controls are possible human-gate reasons,
not new enums. Preserve one successor, no blind retry and all effect fences.

## K6 pass criteria

All preceding recovery, output, effect, rotation and continuity conditions must hold. Verify their canonical receipts and absence of lost/duplicate work; this checklist creates no lifecycle/session/memory/retry owner.
