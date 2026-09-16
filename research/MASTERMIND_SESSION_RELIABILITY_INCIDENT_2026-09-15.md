# Mastermind Session Reliability Incident — 2026-09-15

**Owner:** Sol
**Chairman:** Chris
**Status:** sanitized evidence for SR-F0; not source law or live program state

## Outcome under investigation

Long Mastermind sessions must preserve completed work, effect truth, and the exact next action when a
model generation, connector call, browser surface, or host command fails. The target is not “ChatGPT
never emits an error.” The target is zero lost deliberate work and zero duplicate effects after a
valid checkpoint.

## Confirmed observations

1. The Executive OS conversation accumulated several unusually large responses: roughly 58 KB of
tunnel metrics, 39 KB of process output, multiple 18–20 KB source/runbook reads, and long PR/schema
bodies.
2. A broad recursive Studio Direct search across several roots timed out after 30 seconds and remained
represented by PID `75339`.
3. The next action attempted to read that process output.
4. The turn failed with `Thinking failed`.
5. Two later plain `Continue` messages also failed before a new tool call was issued.
6. An earlier Studio Direct response returned `EFFECT_UNKNOWN` and marked its connector session tainted.
7. OpenAI contemporaneously reported elevated Work Mode errors affecting task start/resume and access
to workspace tools/files; the incident was later resolved.
8. OpenAI troubleshooting guidance recommends a new chat when a conversation is long or turn-heavy and
sanitized HAR/console/request diagnostics when failures persist across clean environments.

## Strong inference, not proof

The most plausible local chain was:

```text
large structured transcript
+ unresolved long-running tool state
+ prior tainted connector event
+ contemporaneous Work Mode degradation
-> failure while resuming/rehydrating the conversation
```

The private OpenAI exception, request stack, and internal context accounting were unavailable. This
record therefore does not claim that transcript size alone caused the failure.

## Ruled out as the primary cause

- Codex quota exhaustion: the failing continuation required no Codex action.
- Executive OS intellectual complexity: the failures happened before renewed reasoning or implementation.
- One malformed `Continue` prompt: later failures occurred before the prompt could be acted on.
- Total Studio Direct outage: bounded calls succeeded before and after the unstable period.

## Canonical owner and design consequence

Do not create another chat/session authority plane. The existing owner is
`docs/EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW.md`, with `ACTIVE_EXECUTION.md` governing the active
turn. Session reliability adds operational hygiene, bounded evidence, exact process reconciliation,
and compact succession to those owners.

Prompt-only guidance is insufficient because a connector can still return excessive output. Studio
Direct guardrails alone are insufficient because they do not define checkpointing, rotation, or
platform diagnostics. The selected architecture is hybrid but split into independent carriers.

## Rollout boundary

### SR-F0 — protected procedure and source law

One records/procedure PR: protected session-reliability skill, INDEX/kernel enrollment, aligned
ACTIVE_EXECUTION boundary, narrow context-rotation amendment, existing source-law tests, and this
sanitized incident record. After merge, transport enforcement remains `SPEC_ONLY`.

### SR-T1 — bounded Studio Direct transport

A separate Studio Direct carrier for bounded output/cursors, typed timeout/status, taint refusal, and
large-output/slow-process/no-replay tests. Source protection alone is `BUILT_NOT_PROVEN`; installation
and real canaries are separately required.

### SR-D1 and SR-PROD1

Disposable long-session canaries must force large outputs, timeout, connector restart, and fresh-chat
migration without company mutation. Production acceptance additionally requires three real Mastermind
programs to complete fresh-chat handoffs with zero lost work or duplicate effects.

## Success measures

Primary measures are zero lost deliberate work, duplicate modifying effects, unreconciled timed-out
processes, manual Chairman context reconstruction after a valid checkpoint, raw responses over the
hard ceiling, and false-complete claims after platform/tool failure.

Secondary measures are checkpoint age, fresh-chat recovery time, failure class, tool-heavy completion
rate, and recovery without repeated work. Longer model runtime is not itself a success measure.

## Do not build

- transcript database or chat lifecycle database;
- retry ledger or hidden replay cursor;
- alternate RuntimeBinding writer;
- title-based successor selection;
- automatic carrier failover;
- hidden prompt cache presented as company memory;
- an infinite-session objective;
- a rule that every provider error means context exhaustion;
- Project instructions containing live workstream/runtime state.

## Capability ruling

This incident record and SR-F0 source law do not enforce tool-response limits and do not prove fresh
model adoption. Session-reliability transport protection remains `SPEC_ONLY` until the separate SR-T1
implementation is protected, installed, and canaried. End-to-end capability remains unaccepted until
the disposable and real-program recovery gates pass.
