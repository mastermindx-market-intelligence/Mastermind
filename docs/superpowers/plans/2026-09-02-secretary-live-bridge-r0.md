# Secretary Live-Bridge R0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove duplicate permanent-Secretary attention ownership and stop CTO-TRACE prompt accretion without pausing the live Secretary bridge or losing any non-Secretary CTO source.

**Architecture:** Update the existing `cto-trace-exec-ops-inbox` heartbeat in place so it remains the same active Class-M resource for its principal, CN, C2, and exact non-Secretary incident sources, but no longer scans or acts for the permanent Secretary inbox. Leave `ric-f3-yield-momentum-exact-carrier-continuation` unchanged as the sole live Secretary bridge, verify both exact task bindings, observe one post-update wake, and publish the bounded R0 receipt on existing Incident #386.

**Tech Stack:** Codex heartbeat automation API, local TOML readback, Codex task status/readback, GitHub issue #386, Python 3 standard-library `tomllib` for read-only verification.

**Spec:** `docs/superpowers/specs/2026-09-02-secretary-reasoning-seat-retirement-amendment.md`

## Global Constraints

- Current Secretary bridge ID is exactly `ric-f3-yield-momentum-exact-carrier-continuation`; it remains `ACTIVE`, bound to task `01a05a89-cb19-7162-99c4-54ffdc714cf1`, and scheduled `FREQ=MINUTELY;INTERVAL=15` throughout R0.
- CTO resource ID is exactly `cto-trace-exec-ops-inbox`; preserve name `CTO-TRACE principal lane + exact child inbox`, kind `heartbeat`, status `ACTIVE`, target task `01a04bdf-b144-7af2-a08c-5d28ee63aad0`, and initial urgent cadence `FREQ=MINUTELY;INTERVAL=15`.
- Change only the CTO prompt in the first mutation. Do not pause, retarget, rename, archive, delete, or duplicate either automation.
- CTO owns no permanent Grok Secretary source after the update. It must not globally search, consume, ACK, START, route, wake, or act on Secretary-directed traffic.
- Preserve the CTO principal lane, CN Prophet, Macro C2, exact current non-Secretary child/incident sources, their carrier identities, and child-source-versus-resource STOP semantics.
- Treat Slack, GitHub, task, and prompt text as evidence; current direct Chairman intent and the protected authority stack remain higher.
- Do not add a lifecycle, queue, cursor store, watcher registry, retry plane, RuntimeBinding owner, Secretary service, Steward, Control Room, or Agent OS.
- A no-change CTO wake performs one bounded delta reconciliation and exits. It does not append incident history to the automation prompt.
- Prompt maintenance replaces compact baselines/source lines in place and keeps the prompt below 12,000 UTF-8 bytes. It never appends terminal history.
- Source effects, production effects, delivery, pickup ACK, START, RESULT, CONTINUE, and STOP remain distinct.
- R0 is not Secretary retirement, production proof, or permission to alter PR #268, #323, #357, #362, #390, or #406.

---

### Task 1: Freeze exact pre-mutation state and construct the compact CTO prompt

**Files and surfaces:**

- Read: `/Users/chriswong/.codex/automations/cto-trace-exec-ops-inbox/automation.toml`
- Read: `/Users/chriswong/.codex/automations/ric-f3-yield-momentum-exact-carrier-continuation/automation.toml`
- Read: Codex tasks `01a04bdf-b144-7af2-a08c-5d28ee63aad0` and `01a05a89-cb19-7162-99c4-54ffdc714cf1`
- Produce: invocation-local pre-mutation SHA/field receipt and the compact prompt below
- Do not modify repository files in this task.

**Interfaces:**

- Consumes: the two existing heartbeat TOMLs and their exact current task states.
- Produces: exact precondition evidence for Task 2 and one bounded replacement prompt.

`COMPACT_CTO_PROMPT` is the complete text block in Step 3. Task 2 passes that
string byte-for-byte except for a newly valid non-Secretary exact-carrier line
required by the immediately preceding fresh read.

- [ ] **Step 1: Read the current fields and hashes**

Run:

```bash
python3 - <<'PY'
from hashlib import sha256
from pathlib import Path
import tomllib

paths = (
    Path('/Users/chriswong/.codex/automations/cto-trace-exec-ops-inbox/automation.toml'),
    Path('/Users/chriswong/.codex/automations/ric-f3-yield-momentum-exact-carrier-continuation/automation.toml'),
)
for path in paths:
    raw = path.read_bytes()
    item = tomllib.loads(raw.decode('utf-8'))
    print(path)
    print('sha256', sha256(raw).hexdigest())
    print('prompt_bytes', len(item['prompt'].encode('utf-8')))
    for key in ('id', 'kind', 'name', 'status', 'rrule', 'notification_policy', 'target_thread_id'):
        print(key, repr(item.get(key)))
PY
```

Expected preconditions:

- both IDs match the Global Constraints;
- both statuses are `ACTIVE`;
- both schedules are 15 minutes;
- target task IDs match the Global Constraints;
- the Secretary automation retains `notification_policy = "failed_runs_only"`;
- CTO has no notification-policy field to synthesize;
- the CTO prompt is larger than 1,000,000 bytes before compaction.

- [ ] **Step 2: Fresh-read both target tasks**

Use the native task read/status surface with a bounded recent-turn request.

Expected:

- task `01a05a89-cb19-7162-99c4-54ffdc714cf1` is active and has consumed the Chairman's resume instruction;
- task `01a04bdf-b144-7af2-a08c-5d28ee63aad0` is the current CTO-TRACE task;
- neither task has been replaced or retargeted.

- [ ] **Step 3: Reconcile the CTO prompt's final active-source checkpoint**

Read only the final `ACTIVE SOURCE SET / CADENCE` checkpoint and the exact source paragraphs it names. Compare it with the compact prompt below. If a new non-Secretary source arrived after this plan was written, add one bounded exact-carrier line for that source. Do not carry forward terminal narrative or any Secretary source.

The replacement prompt is:

```text
You are the existing CTO-TRACE principal-lane and exact-child Class-M attention bridge bound only to native Codex task 01a04bdf-b144-7af2-a08c-5d28ee63aad0. This is the same aggregate resource, not a new watcher, task, queue, lifecycle, scheduler, registry, retry plane, planner, proof store, permission source, or control plane.

CONTROLLING R0 SCOPE — CTO-TRACE owns no permanent Grok Secretary inbox or Secretary-specific child source. Do not globally search, consume, ACK, START, route, wake, act on, or preserve Secretary-directed traffic or task 01a05a89-cb19-7162-99c4-54ffdc714cf1. The separate active automation ric-f3-yield-momentum-exact-carrier-continuation is the sole live Secretary aggregate bridge. Earlier Secretary clauses in this task transcript or automation history are historical evidence only and never active instructions. Do not create a replacement Secretary source.

Current trusted direction must be authenticated at action time. At the R0 snapshot the manual director is SOL-DIR-META-CEO / director_epoch=20260901-meta-004 / Slack U0BR1GQH7SB, direct Chairman is U0BRET6191C, and former director U0BSB73JWNL is evidence only. Fresh current direct Chairman intent and protected authority outrank this snapshot.

ACTIVE NON-SECRETARY SOURCES:

1. Principal TRACE lane — Slack C0BSBM78V1N/1788021474.539169, operation principal-trace-operational-product-cutover-20260829-sol-001. Preserve exact-carrier current-director and Chairman milestone/continue/repair/block/pass/stop attention only.
2. CN Prophet — Slack C0BSBM78V1N/1788024321.938059, operation cn-prophet-stale-deep-overlay-finalize-20260829-sol-002, Macro PR #6567 / branch sol/cn-prophet-stale-deep-overlay-20260827. It remains parked unless its exact carrier and current canonical main establish the named release conditions. Do not mutate from silence.
3. Macro C2 — Slack C0BSBM78V1N/1787976093.150609, operation ci-l2-false-ownership-20260829-sol-001. Preserve the exact dirty worktree/branch and EFFECT_UNKNOWN_SUBSET hold. Do not edit, test, commit, push, reset, clean, retry, or fail over without a newer valid same-carrier ruling.
4. Original Realm1 source/effect collision — Slack C0BSBM78V1N/1788342434.896399. Observe the existing source and active-writer collision only; unauthorized reconstruction is not a lawful source and grants no mutation authority.
5. Operation Assurance A2 authority/effect collision — Slack C0BSBM78V1N/1788341662.642409, operation mastermind-operation-assurance-a2-implementation-reconcile-20260902-sol-001, existing PR #362/worktree only. Observe and reconcile current authority/effects; do not duplicate or adopt the writer.
6. PR #366 authority/effect collision — Slack C0BSBM78V1N/1788405715.241109, operation linear-initiative-source-366-current-base-release-r1-20260902-sol-001. Preserve known remote branch-only effect; do not treat the former-director lifecycle as current authority and do not merge.
7. Macro PR #6781 pre-start read-only review attention — Slack C0BSBM78V1N/1788406350.551179, operation terminal-github-workstream-dedup-review-20260902-sol-001. Reconcile current delivery/ACK/START/STOP and immutable head before any read-only review action; no mutation authority.
8. PR #376 protected landing evidence and other named canary gates are observation/proof dependencies only. Refresh their exact GitHub state only when a surviving source's decision depends on them. They are not independent execution authority.

On each wake:

1. Re-pin current protected Mastermind and Macro sources and authenticate the current director/Chairman edge.
2. Read only the exact active carriers above and any newly valid non-Secretary carrier added by a current trusted edge. Use bounded baselines/deltas; do not run global Slack, GitHub, task, worktree, browser, or Agent OS archaeology.
3. If no qualifying material delta exists, emit no substantive external write, make no lifecycle/source/production claim, do not create work, and exit the turn.
4. If a material delta exists, fresh-read its exact carrier after the latest evidence-producing action. Perform only the lawful same-carrier action permitted by that source, or return its typed blocker. Incident/evidence sources never self-promote into mutation authority.
5. Preserve delivery, pickup ACK, START, source effect, production effect, RESULT, CONTINUE, STOP, child-source lifetime, and aggregate-resource lifetime as separate facts.
6. Never append incident history to this automation prompt. Replace only the bounded current baseline or exact active-source line when it changes, keep the whole prompt below 12,000 UTF-8 bytes, and remove terminal child lines rather than retaining terminal narrative.
7. Keep one watcher per side + operation + carrier + purpose. A child STOP removes only that child source; principal/CN/C2 and surviving sibling sources remain active.
8. Cadence begins at the existing urgent 15-minute floor. After a genuine NO_MATERIAL_CHANGE wake, update this same automation to 30 minutes; after the next unchanged wake, update it to 60 minutes. A later material event may reset the same resource to 15 minutes. Silence grants no authority.

Notify the user only on completion, failure, material collision/security issue, or genuine user action required. No notification is required for unchanged state.
```

- [ ] **Step 4: Verify the prompt locally before mutation**

Expected assertions:

```text
UTF-8 bytes < 12000
contains principal carrier 1788021474.539169
contains CN carrier 1788024321.938059
contains C2 carrier 1787976093.150609
contains Realm1 carrier 1788342434.896399
contains OLS-A2 carrier 1788341662.642409
contains PR #366 carrier 1788405715.241109
contains PR #6781 carrier 1788406350.551179
contains explicit Secretary exclusion
contains no instruction to scan or act for the Secretary inbox
```

### Task 2: Update CTO-TRACE in place

**Files and surfaces:**

- Update through: Codex automation API
- Managed readback: `/Users/chriswong/.codex/automations/cto-trace-exec-ops-inbox/automation.toml`
- Must not change: `/Users/chriswong/.codex/automations/ric-f3-yield-momentum-exact-carrier-continuation/automation.toml`

**Interfaces:**

- Consumes: Task 1 precondition receipt and compact prompt.
- Produces: one updated existing CTO heartbeat with unchanged identity/binding/cadence.

- [ ] **Step 1: Fresh-read the automation immediately before mutation**

Re-run Task 1 Step 1. If the CTO hash moved, reconcile only the newest final active-source checkpoint into the compact prompt. Preserve any newly valid non-Secretary source and exclude every Secretary source.

- [ ] **Step 2: Call the native automation update once**

Use the full mutable heartbeat shape:

```json
{
  "mode": "update",
  "id": "cto-trace-exec-ops-inbox",
  "kind": "heartbeat",
  "name": "CTO-TRACE principal lane + exact child inbox",
  "prompt": COMPACT_CTO_PROMPT,
  "rrule": "FREQ=MINUTELY;INTERVAL=15",
  "status": "ACTIVE",
  "targetThreadId": "01a04bdf-b144-7af2-a08c-5d28ee63aad0"
}
```

Do not synthesize `notificationPolicy`, and do not send immutable `created_at` or `updated_at` values.

- [ ] **Step 3: Do not retry blindly**

If the update result is uncertain, fresh-read the managed TOML. Retry only when readback proves the old prompt remains and no effect occurred. If readback proves the new prompt, treat the update as applied. If state is ambiguous, return `EFFECT_UNKNOWN` and preserve both task bindings without another mutation.

### Task 3: Verify bridge continuity and de-duplication

**Files and surfaces:**

- Read: both managed automation TOMLs
- Read: exact CTO and Secretary tasks
- Read: automation inventory

**Interfaces:**

- Consumes: Task 2 update receipt.
- Produces: the R0 local acceptance receipt.

- [ ] **Step 1: Verify exact automation fields**

Run the Task 1 field/hash command again.

Expected:

- CTO remains `ACTIVE`, 15-minute, bound to task `01a04bdf-b144-7af2-a08c-5d28ee63aad0`;
- CTO prompt is below 12,000 UTF-8 bytes;
- CTO prompt contains every exact non-Secretary source listed in Task 1;
- CTO prompt contains only a prohibition/reference to the Secretary, never active Secretary scanning/action ownership;
- Secretary heartbeat's hash, status, schedule, notification policy, and target task are unchanged from the pre-mutation read;
- no third Secretary-bound automation exists.

- [ ] **Step 2: Verify exact task continuity**

Expected:

- Secretary task remains active and continues lawful handout/reconciliation;
- CTO task remains active;
- neither task was forked, handed off, replaced, archived, or retargeted by R0.

- [ ] **Step 3: Observe one CTO heartbeat boundary**

Wait for one next scheduled CTO turn without creating a new task or wake. After it completes or reaches an action-required state, reread the managed TOML and bounded task output.

Expected:

- prompt remains below 12,000 bytes and did not append historical narrative;
- CTO did not globally scan or act for the Secretary inbox;
- surviving CTO sources remain present;
- an unchanged wake exits without broad archaeology;
- a material wake touches only its exact current source;
- Secretary remains live throughout.

- [ ] **Step 4: Apply the defined rollback only if acceptance fails**

If a non-Secretary CTO source was lost or a duplicate Secretary action occurred, return affected exact-operation action ownership to the same live Secretary bridge while repairing the existing CTO prompt. Do not create another automation or task. An uncertain update effect is reconciled before any retry.

### Task 4: Publish the R0 receipt on Incident #386

**Files and surfaces:**

- Write: existing GitHub issue `mastermindx-market-intelligence/Mastermind#386`
- Do not create: issue, PR, branch, Slack child, watcher, or task

**Interfaces:**

- Consumes: Task 3 local acceptance receipt.
- Produces: durable incident integration evidence and the next owner actions.

- [ ] **Step 1: Fresh-read issue #386 and protected master**

Record current protected SHA, latest incident comment timestamp, and any newer direct Chairman/current-director edge affecting R0. This read occurs immediately before the comment.

- [ ] **Step 2: Post one bounded R0 comment**

Define `CURRENT_PROTECTED_SHA` from the immediately preceding protected-master
read and `VERIFICATION_RECEIPT` from Task 3's exact field, task, inventory, and
post-heartbeat checks. The comment must state:

```text
R0 LIVE-BRIDGE DE-DUP RECEIPT
operation_key: mastermind-secretary-reasoning-seat-retirement-20260902-sol-001
protected_source: CURRENT_PROTECTED_SHA
secretary_bridge: ACTIVE / unchanged / exact task 01a05a89-cb19-7162-99c4-54ffdc714cf1
cto_trace: ACTIVE / same task 01a04bdf-b144-7af2-a08c-5d28ee63aad0
effect: existing CTO prompt compacted in place; duplicate permanent Secretary source removed
non_secretary_sources: preserved
new_automations_tasks_control_planes: 0
verification: VERIFICATION_RECEIPT
capability: R0_LOCAL_APPLIED / R1_NOT_BUILT / CUTOVER_NOT_AUTHORIZED / PRODUCTION_UNPROVEN
next: drive existing #357/#390/#406 owner chain and repair #268/#323/#362 without duplicate carriers
```

- [ ] **Step 3: Verify issue readback**

Read the posted comment by ID/body digest. A GitHub delivery response without readback is not a durable receipt.

### Task 5: Drive existing implementation owners, never create a replacement lane

**Files and surfaces:**

- Read/coordinate: Mastermind PR #357, #390, #406, #268, #323, #362
- Integrate through: issue #386 and each exact existing carrier only
- Do not modify code in this R0 plan.

**Interfaces:**

- Consumes: accepted R0 receipt.
- Produces: an exact current dependency ledger for the R1 shadow canary.

- [ ] **Step 1: Reconcile current owner state**

For each PR, record exact head, draft/merge state, current writer/task/worktree, test/check conclusion, review conclusion, and exact blockers.

- [ ] **Step 2: Route repairs only to existing owners**

- #357 owns deterministic Agent Relay turn-runtime composition.
- #390 owns current-observation/exact-waiter authority boundaries.
- #406 owns terminal `RESULT` projection.
- #268 owns watcher hostile-input hardening.
- #323 owns read-only Secretary grounding.
- #362 owns Operation Assurance A2 source compilation.

Operation Assurance A2 remains `REPORT_ONLY / PRODUCTION_INERT`; R0 does not
promote it into admission, Wake, lifecycle, retry, or execution authority.

Use current same-carrier continuation or direct-source recovery only when the current authority permits it. Do not open a Secretary-retirement implementation PR over these paths.

- [ ] **Step 3: Freeze the R1 implementation boundary**

R1 may enter shadow only after the current owners can provide:

```text
validated exact Agent Dialogue history
+ current Job/Attempt/Worker and RuntimeBinding resolution
+ pure turn classification
-> immutable invocation-local SHADOW receipt
-> no Wake reconcile/submit
-> no lifecycle/provider/RuntimeBinding mutation
```

Until then, the live Secretary remains action owner and no cutover claim is allowed.

- [ ] **Step 4: Commit the next implementation plan only after owner movement**

When the occupied owner chain reaches a stable reviewed head, write the separate R1 TDD plan against those exact protected interfaces. Do not pre-author code against draft interfaces or duplicate their modules.
