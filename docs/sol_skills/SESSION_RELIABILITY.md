---
schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
skill: session_reliability
---

# SESSION RELIABILITY — Preserve Work Across Tool and Conversation Failure

Use this companion for long, tool-heavy, multi-source, process-bearing, or recovery work. It extends
`ACTIVE_EXECUTION.md` and `docs/EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW.md`; it does not replace them.

## Mission

Achieve zero lost deliberate work and zero duplicate modifying effects when a model generation,
connector call, browser surface, or host process fails. The objective is not an infinitely long chat
or a promise that provider incidents disappear. Conversation state is disposable working memory;
canonical state and compact durable checkpoints carry responsibility forward.

This procedure creates no transcript database, no chat lifecycle database, no retry ledger, no
alternate RuntimeBinding writer, no queue, no memory authority, and no transport authority.
Executive OS, Agent OS, GitHub, RuntimeBinding, provider surfaces, and source-custody owners retain
their existing authority.

## Active-turn frame

Keep only the minimum frame needed for the current action:

```text
SESSION_HEALTH
CURRENT_PHASE
LAST_DURABLE_CHECKPOINT
CURRENT_TOOL_OR_PROCESS_IDENTITY
UNRESOLVED EFFECTS
CUMULATIVE_RAW_OUTPUT_ESTIMATE
EXACT_NEXT_ACTION
```

This frame is ephemeral. Never persist it as another state store.

## Session-health classifications

### `SESSION_HEALTHY`

Tool calls complete normally, outputs remain bounded, no process/effect is unresolved, a current
checkpoint exists for completed material work, and the exact conversation can continue safely.

### `ROTATION_SUSPECTED`

Any one of:

- one terminal generation failure;
- one tool timeout;
- cumulative raw output approaching the turn budget;
- a material phase boundary without a recent checkpoint;
- unstable connector latency, browser behavior, or provider surface.

Action: start no new modifying effect until current effects are clear; update the compact continuation;
finish only the bounded read/reconciliation already in flight; reduce output; allow at most one clean
retry when no effect is uncertain.

### `ROTATION_REQUIRED`

Any one of:

- two consecutive terminal generation failures with no successful intervening turn;
- one resume failure immediately after an unresolved tool timeout, connector taint, or `EFFECT_UNKNOWN`;
- the exact surface cannot safely continue;
- the Chairman explicitly retires the conversation.

Action: stop tool execution in that conversation; never keep issuing `Continue`; preserve exact PID,
request, process, carrier, and effect identity; continue through one fresh conversation using the
compact capsule and minimum fresh canonical reads.

The truth rule remains **Thinking failed != context exhausted**. A single failure may justify
`ROTATION_SUSPECTED`; it never proves a private provider context limit.

## Tool-output and command budgets

These are conservative Mastermind engineering budgets, not undocumented provider limits.

### Per response

- soft target: **8 KiB or 150 lines**;
- hard ceiling: **16 KiB**;
- search ceiling: **100 matches**;
- larger results return a bounded excerpt, total byte/line count, truncation flag, digest, and cursor.

### Per active turn

- cumulative raw-output target: **32 KiB**;
- after **six material tool calls**, synthesize and checkpoint before another broad phase;
- do not load multiple complete source files, PR bodies, logs, metrics, schemas, or process tables when
  exact ranges or selected fields answer the question.

### Commands and processes

- normal command timeout: **15 seconds**;
- hard default ceiling: **30 seconds**;
- long work returns PID and typed status instead of blocking the reasoning turn;
- no unbounded recursive search across home, temp, system support roots, or multiple repositories;
- no unfiltered process, log, or metrics dump;
- prefer exact roots, `git grep`, `find -maxdepth`, field-selected `jq`, byte/line caps, and cursors.

## Timeout and process continuation

When a command times out:

1. freeze the exact PID, command, carrier, and requested effect;
2. start no replacement or equivalent broad command;
3. perform one bounded status/output read;
4. deliberately retain it or terminate only that exact process;
5. verify the selected result;
6. checkpoint before broad work resumes.

A timeout is never permission to replay the command. `EFFECT_UNKNOWN` remains on its original carrier
until canonical reconciliation proves accepted, conflicted, not found, or still unknown.

## Connector taint

A tainted connector generation is unusable for additional work. Refuse further calls in that
generation, return one compact typed error, and preserve the original PID/action/effect plus the
**original carrier and connector generation**. Reconcile from a fresh connector generation while
remaining bound to that original carrier; a fresh generation is not carrier failover. Connector taint
never authorizes replay or carrier failover and never includes prior raw payloads in the error.

## Conversation-context discipline

Do not place full process listings, metrics pages, logs, repository trees, large PR bodies, long
source files, irrelevant connector schemas, or repeated evidence in the reasoning transcript.
Return source identity, exact query, selected findings, bounded excerpt, byte/line count, truncation
flag, and cursor or artifact reference.

The rule is: **raw tool history is not a continuation manifest**. Never reconstruct or replay private reasoning or the
full prior tool transcript after interruption, compaction, or rotation.

## Compact continuation capsule

Maximum target: **12 KiB / 1500 words**.

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
ACCEPTANCE AND STOP CONDITION
```

The capsule contains conclusions and exact identities, not hidden chain-of-thought, secrets, raw
logs, tool payloads, or stale Project-memory claims. Durable organizational truth still goes to Agent
OS; implementation evidence stays in GitHub; Executive OS remains lifecycle authority.

Planned retirement requires an already-durable continuation before the predecessor is abandoned.
A checkpoint never transfers source custody, leases, RuntimeBinding, or a STARTed operation.

## Failure triage

### Failure inside one tool call

Treat it as a tool/host boundary. Reconcile exact PID, action, carrier, and effect.

### First terminal generation failure after a completed tool call

Classify `ROTATION_SUSPECTED`. Ensure no unresolved effect remains and make at most one clean retry.

### Second consecutive terminal generation failure

Classify `ROTATION_REQUIRED` under `REPEATED_TERMINAL_GENERATION_FAILURE`. Stop using the chat.

### Fresh conversation fails before its first tool call

Treat platform, browser, account, model, device, network, and extension state as the leading boundary.
Check current provider status, hard-refresh/restart, use a clean/private browser profile, and compare a
different browser/model/device/network without moving any unresolved effect to another carrier.

### Failure persists across clean environments

Collect a sanitized support packet: timestamp, model/mode, conversation identity, request ID when
shown, browser/version, clean-environment comparisons, HAR, and console errors. Exclude credentials,
private tool payloads, and company-confidential evidence not required by support.

## Closeout and rotation sequence

1. stop new modifying effects;
2. reconcile every existing effect and timed-out process by exact identity;
3. checkpoint the completed semantic phase in its canonical owners;
4. write or refresh the compact capsule;
5. establish the closed rotation reason for the exact surface;
6. retire the predecessor only after durable continuation exists;
7. create/use one successor through the existing context-rotation owner;
8. load current protected procedure and minimum fresh canonical state;
9. continue the exact next action without redoing completed work.

`CONTEXT_ROTATION` is a continuation boundary, not success, completion, or acceptance. The parent
mission remains active. One successor/no blind retry/effect fencing from the context-rotation law
continue to govern.

## K6 pass criteria

A session-reliability continuation passes when:

- no response exceeds the hard ceiling without explicit bounded cursoring;
- every timeout preserves PID/action identity and is reconciled once;
- no tainted connector generation receives additional work;
- no `EFFECT_UNKNOWN` changes carrier or gets replayed;
- a single failure is not mislabeled as proven context exhaustion;
- a repeated terminal failure rotates instead of receiving more `Continue` prompts;
- a fresh successor recovers the exact next action without raw transcript rehydration;
- deliberate repository edits and accepted effects are neither lost nor duplicated;
- the stop boundary is recoverable through existing canonical owners; and
- no new lifecycle, session registry, transcript store, retry ledger, or memory plane was created.
