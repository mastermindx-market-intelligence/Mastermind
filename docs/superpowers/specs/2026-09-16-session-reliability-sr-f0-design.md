# Mastermind Session Reliability SR-F0 Design

**Operation:** `session-reliability-sr-f0-20260916-sol-001`
**Existing owner:** `WS:CHAIRMAN-CONTROL-ROOM` / MAS-198
**Carrier:** Mastermind PR #706 / `sol/compact-continuation-anti-rehydration-20260916`
**State after merge:** protected procedure available; transport enforcement remains `SPEC_ONLY`
**Authority:** records/procedure only; no runtime, provider, transport, or lifecycle effect

## Outcome

Long, tool-heavy Mastermind sessions must lose zero deliberate work and create zero duplicate effects when a ChatGPT generation, connector call, or host command fails. The solution does not promise that provider errors disappear. It makes completed work, exact effect state, and the next action recoverable without replaying a large transcript.

The primary persona is Sol operating for Chairman Chris. The machine job is to bound evidence at source, checkpoint before pressure, classify failures truthfully, reconcile exact PIDs/effects, and rotate to one fresh conversation when the current surface is unsafe. The moat is continuity without another memory, retry, session, lifecycle, or authority plane.

## Evidence and authority boundary

The September 15 Executive OS failure packet is incident evidence, not source law. It records unusually large tool payloads, a timed-out broad search, a tainted connector event, contemporaneous Work Mode degradation, and repeated terminal generation failure. It cannot prove one private OpenAI exception or make transcript size the sole cause.

Canonical authority remains:

- `docs/EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW.md` for chat succession and predecessor fencing;
- `docs/sol_skills/ACTIVE_EXECUTION.md` for active-turn advancement and lawful stop boundaries;
- Executive OS for Job/Attempt/Worker/Event state and effect truth;
- Agent OS for durable organizational continuation;
- GitHub for implementation and immutable evidence.

## Approaches considered

### A. Kernel-only prompt amendment

A single compact Project rule is fast, but it leaves tool budgets, timeout/PID reconciliation, failure classification, diagnostics, and K-pass criteria undefined. It also conflicts with the current ACTIVE_EXECUTION final-response gate. Rejected as incomplete.

### B. New session registry or retry service

A dedicated chat/session database could track transcripts and retries, but it would duplicate existing Agent OS, RuntimeBinding, Executive effect, and context-rotation owners. Rejected by design.

### C. Hybrid extension of existing owners — selected

Add one detailed protected Skillpack companion, a compact bootstrap projection, a narrow amendment to the existing context-rotation law, and aligned ACTIVE_EXECUTION stop semantics. Keep Studio Direct response shaping in a later independent carrier. This closes the procedural gap without creating another control plane.

## SR-F0 source architecture

### `docs/sol_skills/SESSION_RELIABILITY.md`

A mandatory operational companion when a session expects more than three tool calls, starts or continues a host process, performs multi-source archaeology, resumes after any generation/tool failure, or crosses more than one material phase.

It owns only:

- session-health classification;
- conservative response/turn/command budgets;
- exact timeout/PID/taint reconciliation procedure;
- continuation-capsule format;
- failure triage and sanitized support diagnostics;
- local closeout/rotation sequence and K-pass criteria.

It does not own lifecycle, RuntimeBinding, source custody, retry authority, durable memory, or browser transport.

### `docs/sol_skills/INDEX.md`

Register `SESSION_RELIABILITY.md` and its mandatory selection triggers. Preserve Skillpack schema/version `1.0.1` and bootstrap major `1`; this additive procedure does not import the blocked 1.1.0 continuation-delta candidate.

### `docs/sol_skills/BOOTSTRAP_KERNEL.md`

Replace the incomplete failure-only line with one compact `SESSION RELIABILITY` law. It must require current protected `SESSION_RELIABILITY.md`, source-bounded output, checkpointing before context pressure, exact timeout/taint reconciliation, and fresh-chat succession after the closed threshold. It must forbid raw tool-history replay.

### `docs/sol_skills/ACTIVE_EXECUTION.md`

Add `CONTEXT_ROTATION` to the final-response gate as a lawful local turn boundary, never as completion or acceptance. It is available only when the exact surface is `ROTATION_REQUIRED`, modifying effects are reconciled, a compact durable continuation exists, and the successor can recover the same mission. The parent mission remains active. `MORE_WORK_EXISTS` still forbids an ordinary final response.

Step 7A and K5 must state that a verified semantic phase may checkpoint and rotate before another high-context phase. Productive effort is measured by durable capability progress and decision quality, not transcript size, wall-clock duration, or tool-call count.

### `docs/EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW.md`

Narrowly amend the existing law:

- two consecutive terminal generation failures with no successful intervening turn establish the repeated-failure threshold;
- one resume failure after unresolved timeout, connector taint, or `EFFECT_UNKNOWN` requires rotation;
- a single `Thinking failed` remains insufficient to prove context exhaustion;
- a tainted connector generation is unusable for further work;
- raw tool history is not a continuation manifest;
- planned retirement requires an already-durable continuation;
- one successor, one carrier, no blind retry, and effect fencing remain unchanged.

### Existing tests

Extend `tests/test_web_sol_context_rotation_source_law.py` and `tests/test_sol_skillpack_active_execution.py`. Do not create a second chat-rotation test owner. The tests must pin the new skill, INDEX enrollment, compact kernel, thresholds, budgets, capsule, no-duplicate-plane boundary, `CONTEXT_ROTATION` gate, and preservation of the single-failure truth rule.

### Incident research record

Create one sanitized research record containing confirmed observations, explicit inferences, ruled-out causes, and the rollout boundary. It is evidence only and must not carry live program state into the Skillpack.

## Operational contract

### Session classifications

`SESSION_HEALTHY` means bounded outputs, no unresolved process/effect, and a safe current surface. `ROTATION_SUSPECTED` follows one terminal generation failure, one tool timeout, pressure approaching budget, a material phase without a checkpoint, or unstable connector/browser behavior. `ROTATION_REQUIRED` follows two consecutive terminal generation failures with no successful intervening turn, one resume failure after unresolved timeout/taint/`EFFECT_UNKNOWN`, an unusable exact surface, or explicit Chairman retirement.

`ROTATION_SUSPECTED` permits only bounded reconciliation, checkpointing, and at most one clean retry when no effect is uncertain. `ROTATION_REQUIRED` stops tool execution in that conversation and continues from one compact successor capsule.

### Conservative budgets

- response soft target: 8 KiB or 150 lines;
- response hard ceiling: 16 KiB;
- search ceiling: 100 matches;
- turn raw-output target: 32 KiB;
- checkpoint after six material tool calls before another broad phase;
- normal command timeout: 15 seconds; hard default ceiling: 30 seconds;
- long work returns PID/status rather than blocking the reasoning turn.

These are Mastermind engineering budgets, not claims about undocumented provider limits.

### Continuation capsule

Maximum target: 12 KiB / 1500 words. It contains mission, canonical owners/identities, protected SHA/Skillpack, capability ledger, last confirmed effect, unresolved effects/PIDs/request refs, workspace/branch/PR, do-not-redo, exact next action, and acceptance/stop condition. It contains no hidden reasoning, secrets, raw logs, or raw tool history.

### Tool timeout and taint

A timeout freezes exact PID/action identity, permits one bounded status read, and never authorizes replay. The process is deliberately retained or terminated by exact identity, then verified. A tainted connector generation refuses further work and returns only a compact typed reconciliation instruction.

## Error and recovery flow

1. A tool-call failure is a tool/host boundary; reconcile its exact PID/action.
2. The first terminal generation failure after a completed tool call is `ROTATION_SUSPECTED`; verify effect state and allow at most one clean retry.
3. The second consecutive terminal generation failure is `ROTATION_REQUIRED`; stop using the conversation.
4. A fresh chat failing before its first tool call triggers platform/browser/account triage rather than transcript diagnosis.
5. Persistent clean-environment failure produces sanitized timestamps, model/mode, conversation identity, request ID when shown, HAR, and console diagnostics for support.

No step silently changes carrier, retries an unknown modification, or reconstructs hidden reasoning.

## Collision handling

- PR #706 remains the sole SR-F0 carrier.
- PR #504 remains the held host-discovery candidate; SR-F0 does not absorb its discovery semantics.
- PR #674 remains the held delegation-companion enrollment; SR-F0 must preserve current INDEX text and avoid claiming that companion protection.
- PR #147 remains the rejected/held Skillpack 1.1.0 continuation-delta carrier; SR-F0 stays on pack `1.0.1` and imports no blocked linter/commission law.
- PR #124 is a broad stale overlapping branch, not the context-rotation owner.

Latest-base integration and independent review must verify that no held carrier is silently overwritten.

## Non-goals

- no transcript or chat lifecycle database;
- no retry ledger, successor registry, or alternate RuntimeBinding writer;
- no Studio Direct transport code in SR-F0;
- no title-based successor selection or automatic carrier failover;
- no promise of infinite sessions or zero provider incidents;
- no live program state in Project instructions or the Skillpack;
- no claim that source law alone proves model adoption or transport enforcement.

## Acceptance

SR-F0 is accepted only when the exact head passes focused source-law tests, current-base integration, independent review, and protected CI; the protected Skillpack exposes the new companion and aligned stop semantics; the incident record remains sanitized; and the PR remains records/procedure-only.

After merge, procedural guidance is protected, while bounded Studio Direct output/timeout/taint enforcement remains `SPEC_ONLY` until SR-T1 is separately implemented, installed, and canaried. No session reliability capability is `PROVEN_LIVE` before the later SR-D1 and SR-PROD1 evidence gates.
