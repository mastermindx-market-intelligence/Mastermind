# Secretary Live-Bridge R0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove duplicate permanent-Secretary attention ownership and stop CTO-TRACE prompt accretion without pausing the live Secretary bridge or losing any non-Secretary CTO source.

**Architecture:** Update the existing `cto-trace-exec-ops-inbox` heartbeat in place so it remains the same active Class-M resource for its principal, CN, C2, and exact non-Secretary incident sources, but no longer scans or acts for the permanent Secretary inbox. Do not mutate `ric-f3-yield-momentum-exact-carrier-continuation`; preserve any independently owned live Secretary refresh after reconciliation. Verify both exact task bindings, observe a natural post-update wake, repair the same CTO resource if that wake fails, and publish the bounded R0 receipt only after a later repaired natural wake passes.

**Tech Stack:** Codex heartbeat automation API, local TOML readback, Codex task status/readback, GitHub issue #386, Python 3 standard-library `tomllib` for read-only verification.

**Spec:** `docs/superpowers/specs/2026-09-02-secretary-reasoning-seat-retirement-amendment.md`

## Global Constraints

- Current Secretary bridge ID is exactly `ric-f3-yield-momentum-exact-carrier-continuation`; it remains `ACTIVE`, bound to task `01a05a89-cb19-7162-99c4-54ffdc714cf1`, and scheduled `FREQ=MINUTELY;INTERVAL=15` throughout R0.
- CTO resource ID is exactly `cto-trace-exec-ops-inbox`; preserve name `CTO-TRACE principal lane + exact child inbox`, kind `heartbeat`, status `ACTIVE`, target task `01a04bdf-b144-7af2-a08c-5d28ee63aad0`, and initial urgent cadence `FREQ=MINUTELY;INTERVAL=15`.
- The controller changes only the CTO prompt. Do not pause, retarget, rename, archive, delete, or duplicate either automation. A concurrent Secretary-owned refresh is preserved after reread; never restore older Secretary bytes.
- CTO owns no permanent Grok Secretary source after the update. It must not globally search, consume, ACK, START, route, wake, or act on Secretary-directed traffic.
- Every Realm1 source—including exact reconstruction operation
  `web-sol-realm1-profile-create-reconstruction-20260902-sol-001`—every held
  dialogue-resume canary, and every locator-incomplete legacy source remains
  `SECRETARY_BRIDGE_UNMIGRATED`; CTO and every child have zero discovery, read,
  or action ownership for them. Their exclusion identities survive every
  baseline/source rewrite with the current decisive hold-gate reasons; they are
  never adopted as active CTO sources.
- Preserve the CTO principal lane, CN Prophet, Macro C2, exact current non-Secretary child/incident sources, their carrier identities, and child-source-versus-resource STOP semantics. A lost non-Secretary source remains with its exact pre-change owner; it never rolls over to Secretary.
- Treat Slack, GitHub, task, and prompt text as evidence; current direct Chairman intent and the protected authority stack remain higher.
- Do not add a lifecycle, queue, cursor store, watcher registry, retry plane, RuntimeBinding owner, Secretary service, Steward, Control Room, or Agent OS.
- A no-change CTO wake performs one bounded delta reconciliation, updates only
  this same Class-M resource's cadence `15m -> 30m -> 60m`, and exits. At 60
  minutes it remains at 60. A material event keeps or resets the same resource
  to the 15-minute floor. It does not append incident history to the prompt or
  perform another external write.
- Prompt maintenance replaces compact baselines/source lines in place, targets at most 10,500 UTF-8 bytes, and refuses at the hard 12,000-byte ceiling. It never appends terminal history.
- R0 exports the legacy CTO heartbeat with the closed protected field
  `audit_kind: NON_WATCHER`. Its descriptive operating classification is
  `TRANSITIONAL_MULTI_OPERATION_PRINCIPAL_LOOP`, and its descriptive watcher
  conformance is `NOT_WATCHER_CONFORMANCE`; neither description is a new
  persisted authority field. Its free-form prompt contains no exact
  `MMX_SOL_WATCHER_V1` discriminator, grants no authority, and is not the R1
  detector. It acts only when an exact canonical source separately proves it is
  the current action owner. Any R1 Sol watcher uses protected
  `render_watcher_prompt(...)` exactly; aggregate carriers remain
  non-authoritative.
- CTO and every reader child must not access Secretary-owned/quarantined
  worktrees, read any local task transcript, globally enumerate tasks/archives,
  or search session/transcript/worktree/filesystem trees. Local repository or
  worktree reads are closed to the exact explicitly allowlisted C2/B0 carriers;
  a named PR or branch does not authorize opening its local worktree, and an
  absent exact local path means zero local read. CN Prophet and every other
  named PR/workstream use bounded protected GitHub/ref reads only. Native reads
  use a closed exact task-ID allowlist repeated in every commission.
- Source effects, production effects, delivery, pickup ACK, START, RESULT, CONTINUE, and STOP remain distinct.
- Protected PR #268 and #390 are current law/evidence, not live carriers to revive. R0 is not Secretary retirement, production proof, or permission to alter PR #323, #357, #362, or #406.

---

### Task 1: Freeze exact pre-mutation state and construct the compact CTO prompt

**Files and surfaces:**

- Read: `/Users/chriswong/.codex/automations/cto-trace-exec-ops-inbox/automation.toml`
- Read: `/Users/chriswong/.codex/automations/ric-f3-yield-momentum-exact-carrier-continuation/automation.toml`
- Read: Codex tasks `01a04bdf-b144-7af2-a08c-5d28ee63aad0` and `01a05a89-cb19-7162-99c4-54ffdc714cf1`
- Produce: invocation-local pre-mutation SHA/field receipt, exact source-disposition table, and one reviewed compact replacement prompt
- Do not modify repository files in this task.

**Interfaces:**

- Consumes: the two existing heartbeat TOMLs and their exact current task states.
- Produces: exact precondition evidence for Task 2 and one bounded replacement prompt.

`COMPACT_CTO_PROMPT` is the complete reviewed payload produced by Step 3 at the
current-state fence. Task 2 passes that exact string and digest byte-for-byte.
Any later source, task, CTO hash, or Secretary hash movement invalidates the
candidate and requires regeneration plus re-review; Task 2 never edits a stale
candidate in flight.

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
- on the initial audit only, the CTO prompt was larger than 1,000,000 bytes;
  a repair pass instead binds whatever exact current prompt exists.

- [ ] **Step 2: Fresh-read both target tasks**

Use the native task read/status surface with a bounded recent-turn request.

Expected:

- task `01a05a89-cb19-7162-99c4-54ffdc714cf1` is active and has consumed the Chairman's resume instruction;
- task `01a04bdf-b144-7af2-a08c-5d28ee63aad0` is the current CTO-TRACE task;
- neither task has been replaced or retargeted.

- [ ] **Step 3: Reconcile and classify the current source set**

Read only the newest bounded baseline/source checkpoint and the exact carriers it
names. Produce a disposition table before writing the candidate:

- retain each current, exact, nonterminal, non-Secretary source with its carrier,
  operation, owner, and decisive lifecycle/effect state;
- remove a terminal child only when a fresh authenticated edge on that exact
  carrier proves terminal;
- classify every Realm1 source and the two held dialogue-resume canary
  roots, and locator-incomplete Secretary traffic as
  `SECRETARY_BRIDGE_UNMIGRATED`; CTO performs no discovery, read, or action for
  them;
- keep vague non-Secretary evidence with its exact pre-change source owner until
  an exact carrier exists; never transfer it to Secretary; and
- reject any source or state learned from an out-of-bound read.

Build one complete `COMPACT_CTO_PROMPT` with exactly these sections:

1. existing managed-resource identity; closed protected `audit_kind:
   NON_WATCHER`; descriptive operating classification
   `TRANSITIONAL_MULTI_OPERATION_PRINCIPAL_LOOP`; descriptive watcher
   conformance `NOT_WATCHER_CONFORMANCE`; and no exact
   `MMX_SOL_WATCHER_V1` discriminator;
2. Secretary ownership exclusion and `SECRETARY_BRIDGE_UNMIGRATED` partition;
3. inherited Realm1 worktree denylist, no-local-transcript rule, closed native
   task-ID allowlist, exact reconstruction operation exclusion, a closed local
   repository/worktree allowlist limited to exact C2/B0 carriers, and
   no-global-discovery rule for CTO and every child;
4. action-time authority/source-pinning rule;
5. exactly one bounded current baseline;
6. exact active non-Secretary source lines from the disposition table;
7. observation-only and terminal evidence, never execution sources;
8. no-change/material-event, lifecycle-separation, replacement-not-append, and
   protected Class-M cadence behavior: an unchanged turn updates only this same
   resource `15m -> 30m -> 60m`, stays at 60 after later unchanged turns, and a
   material event keeps or resets it to the 15-minute floor.

The bounded baseline retains its current exact evidence locators—including
receipt/run/job and canonical blob identifiers needed to distinguish generic
prose from proven state. Compression may remove narrative, never those
load-bearing identifiers or the held-canary gate reasons.

If the newest checkpoint has already genericized or omitted a load-bearing
identifier, resolve it from the last accepted disposition/candidate receipt and
fresh bounded protected evidence for the named run, job, blob, carrier, or ref.
Do not use broad archaeology or treat the corrupted newest prose as proof. The
candidate must also contain a prospective rewrite instruction that requires
every later baseline/source rewrite to retain the complete Secretary, Realm1,
and held-canary exclusion identities, every decisive held-canary gate reason,
and the current baseline's exact receipt/run/job/blob identifiers.

The free-form R0 heartbeat preserves attention but grants no authority. It may
act only when an exact canonical source separately proves CTO-TRACE is the
current action owner; otherwise the substantive action remains with that exact
owner. Do not
copy the prior prompt as a source registry, preserve terminal narrative, or
create a second control surface.

- [ ] **Step 4: Verify and review the complete candidate**

The candidate must pass all assertions before mutation:

```text
UTF-8 bytes <= 10500 and < 12000 hard ceiling
exactly one bounded baseline, active-source section, and wake procedure
retains every load-bearing current baseline receipt/run/job/blob locator and every held-canary gate reason rather than replacing them with generic status prose
contains a prospective self-update instruction that explicitly retains those exact proof identifiers, gate reasons, and complete Secretary/Realm1/held-canary exclusion identities through every later rewrite; current literal presence alone does not pass
contains every retained exact non-Secretary locator and decisive lifecycle edge
uses exactly audit_kind: NON_WATCHER, carries the two descriptive classifications separately, and contains no exact MMX_SOL_WATCHER_V1 discriminator
contains SECRETARY_BRIDGE_UNMIGRATED and both held canary roots/operation only as Secretary-owned exclusions
contains every Realm1 root only as a Secretary-owned exclusion, both exact denied paths, and no Realm1 reconstruction/PR/head/worktree/effect observation
contains exact Realm1 reconstruction operation web-sol-realm1-profile-create-reconstruction-20260902-sol-001 only as a Secretary-owned exclusion
forbids every local transcript-file read, global task/archive listing, and global session/transcript/worktree/filesystem discovery
forbids every local repository/worktree read except an exact explicitly allowlisted C2/B0 carrier; named PR/branch evidence, including CN Prophet, uses bounded protected GitHub/ref reads only
allows bounded native reads only for an explicit exact task-ID allowlist
requires every child commission to repeat its exact allowlist and denylist
keeps RESULT, CONTINUE, interruption, STOP, source effect, and production effect separate
contains no instruction to scan or act for the Secretary inbox
contains no new resource, lifecycle, scheduler, queue, registry, or control plane
requires NO_MATERIAL_CHANGE to update only this same rrule 15m -> 30m -> 60m and a material event to keep/reset 15m
```

Record the exact prompt byte count and SHA-256. A fresh reviewer must accept the
complete payload. Any fix changes the digest and requires rereview.

### Task 2: Update CTO-TRACE in place

**Files and surfaces:**

- Update through: Codex automation API
- Managed readback: `/Users/chriswong/.codex/automations/cto-trace-exec-ops-inbox/automation.toml`
- Must not change: `/Users/chriswong/.codex/automations/ric-f3-yield-momentum-exact-carrier-continuation/automation.toml`

**Interfaces:**

- Consumes: Task 1 precondition receipt and compact prompt.
- Produces: one updated existing CTO heartbeat with unchanged identity/binding
  and the initial urgent 15-minute cadence; later natural turns apply the
  protected cadence transition.

- [ ] **Step 1: Fresh-read the automation immediately before mutation**

Re-run Task 1 Step 1 and fresh-read the exact CTO task. The candidate fence is
open only when the exact CTO task is idle and both current TOML hashes, managed
fields, prompt digests, and source state equal the reviewed receipt. If a CTO
turn is active, wait for its exact completion and reconcile its result. If
either TOML or source state moved, regenerate and rereview the candidate; never
overwrite a live writer or restore older Secretary bytes.

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

Immediately read back the exact CTO payload digest and fields, newest Secretary
digest and fields, exact task states, and automation inventory. Prove one CTO
resource, one Secretary resource, and no duplicate purpose. Independent
Secretary movement is reconciled as live-owner state; only a migration-caused
Secretary mutation fails this update.

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

- Before the natural turn, CTO remains `ACTIVE`, 15-minute, bound to task
  `01a04bdf-b144-7af2-a08c-5d28ee63aad0`;
- CTO prompt is below 12,000 UTF-8 bytes;
- CTO prompt contains every exact non-Secretary source listed in Task 1;
- CTO prompt contains only a prohibition/reference to the Secretary, never active Secretary scanning/action ownership;
- the controller caused no Secretary mutation; the newest immediately-preceding
  Secretary hash is unchanged across the CTO update, or any independently owned
  movement is reread and reconciled without restoring old bytes;
- Secretary ID, name, kind, status, schedule, notification policy, target task,
  resumed handout, and sole Realm1/canary ownership remain correct;
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
- the audit export uses exactly `audit_kind: NON_WATCHER`, reports the operating
  and conformance descriptions separately, and the prompt contains no exact
  `MMX_SOL_WATCHER_V1` discriminator;
- the actual post-turn CTO `rrule` matches the observed result: a first
  `NO_MATERIAL_CHANGE` changes this same resource from 15 to 30 minutes, a later
  unchanged turn changes 30 to 60 minutes, 60 remains 60, and a material turn
  may keep or reset it to 15 minutes;
- CTO and every child avoided the two Realm1 denied worktrees, every local
  transcript file, global task/archive enumeration, and global
  session/transcript/worktree/filesystem discovery;
- CTO and every child retained the exact Realm1 reconstruction operation only as
  a Secretary-owned exclusion, performed no local repository/worktree read
  outside an exact C2/B0 allowlist, and did not open a CN Prophet worktree;
- every reader commission carried its closed allowlist and denylist;
- `SECRETARY_BRIDGE_UNMIGRATED`, the held canary ownership, all surviving exact
  sources, and one replacement baseline survived any self-update;
- held-canary gate reasons and the current baseline's load-bearing
  receipt/run/job/blob identifiers survived without genericization;
- Secretary remains live throughout.

- [ ] **Step 4: Apply the defined rollback only if acceptance fails**

If a non-Secretary CTO source was lost, retain its exact pre-change CTO/source
owner and restore it only in this same CTO resource. If a Secretary or held
Secretary-canary source was duplicated or lost, its action ownership remains
with the same live Secretary bridge. Never transfer unrelated CTO operations to
Secretary, and never create another automation or task. Reconcile uncertain
effects before retry.

Restore dropped source locators, exclusion identities, held-gate reasons, and
baseline proof identifiers from the last accepted pre-failure
disposition/candidate receipt, then reconcile against fresh bounded canonical
evidence and any newer authenticated carrier edge. Never reconstruct from the
failed turn's corrupted newest prompt alone. Recompute the complete payload's
byte count and digest and obtain independent review before the one in-place
repair.

Any failed canary blocks Task 4. After repairing the same resource, repeat Tasks
2 and 3 against the newest state and observe a later natural turn. Only that
repaired natural-canary receipt can authorize publication of R0 success.

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
secretary_bridge: ACTIVE / exact task 01a05a89-cb19-7162-99c4-54ffdc714cf1 / R0_CAUSED_MUTATION_NONE / newest owner state reconciled
cto_trace: ACTIVE / same task 01a04bdf-b144-7af2-a08c-5d28ee63aad0
effect: existing CTO prompt compacted in place; duplicate permanent Secretary source removed
non_secretary_sources: preserved
prompt_receipts: accepted candidate UTF-8 bytes + SHA-256 / immediately installed prompt bytes + SHA-256 + full CTO TOML SHA-256 + updated_at / post-canary prompt bytes + SHA-256 + full CTO TOML SHA-256 + updated_at
rewrite_sticky_exclusions: exact Secretary task/bridge identity / exact Realm1 operation, roots, and denied paths / exact held-canary roots and operation / all excluded from active CTO adoption
held_gate_reasons: Gate1 FALSE (#6754 unprotected) / Gate2 TRUE (#268 protected) / Gate3 FALSE (no THREE_ACCOUNT_CANARY_RECEIPT_V1 PASS)
baseline_proof_ids: protected run 33721661425 / job 100543070409 / legacy-jobs.yml blob 42206a63feb78637cd90f0a933aae5e0bed4823f / ci.yml blob 28cffa3890efa52df742a98b83f77b8433eb6f67
classification: R0_NON_WATCHER / NO_PROMPT_DERIVED_ACTION_AUTHORITY / R1_CANONICAL_RENDERER_REQUIRED
audit: audit_kind=NON_WATCHER / operating_classification=TRANSITIONAL_MULTI_OPERATION_PRINCIPAL_LOOP / watcher_conformance=NOT_WATCHER_CONFORMANCE / MMX_SOL_WATCHER_V1_ABSENT
canary: final repaired natural turn accepted; any earlier failed turn and repair are named in VERIFICATION_RECEIPT
cadence: actual post-canary rrule and the material-or-NO_MATERIAL_CHANGE reason for it
new_automations_tasks_control_planes: 0
verification: VERIFICATION_RECEIPT
capability: R0_LOCAL_APPLIED / R1_NOT_BUILT / CUTOVER_NOT_AUTHORIZED / PRODUCTION_UNPROVEN
next: apply protected #268/#390 law; drive existing #357/#406 carriers and repair #323/#362 without duplicates
```

- [ ] **Step 3: Verify issue readback**

Read the posted comment by ID/body digest. A GitHub delivery response without readback is not a durable receipt.

### Task 5: Drive existing implementation owners, never create a replacement lane

**Files and surfaces:**

- Read protected dependencies: merged PR #268 and #390 source law
- Read/coordinate existing open carriers: Mastermind PR #357, #406, #323, #362
- Integrate through: issue #386 and each exact existing carrier only
- Do not modify code in this R0 plan.

**Interfaces:**

- Consumes: accepted R0 receipt.
- Produces: an exact current dependency ledger for the R1 shadow canary.

- [ ] **Step 1: Reconcile current owner state**

For each open carrier, record exact head, draft/merge state, current
writer/task/worktree, test/check conclusion, review conclusion, and exact
blockers. For #268 and #390, record their current protected commit and contract;
never treat the merged PR as a writer or revive it.

- [ ] **Step 2: Route repairs only to existing owners**

- #357 owns deterministic Agent Relay turn-runtime composition.
- #406 owns terminal `RESULT` projection.
- #323 owns read-only Secretary grounding.
- #362 owns Operation Assurance A2 source compilation.
- protected #268 supplies the canonical watcher renderer, hostile-input law, and
  aggregate non-authority boundary; it is not an open repair lane.
- protected #390 supplies current-observation/exact-waiter law and remains
  `SPEC_ONLY` with `authorized_modes: []`; it is not an open implementation
  owner.

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

This does not authorize #390's held modes. `ACTIVE_CURRENT_WORKER` still requires
the protected R2 binding/resolver, and `TERMINAL_RESULT` still requires an exact
ORION R2 `APPLIED` receipt. The shadow may observe and compare only.

Until then, the live Secretary remains action owner and no cutover claim is allowed.

- [ ] **Step 4: Commit the next implementation plan only after owner movement**

When the occupied owner chain reaches a stable reviewed head, write the separate R1 TDD plan against those exact protected interfaces. Do not pre-author code against draft interfaces or duplicate their modules.
