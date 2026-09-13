---
schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
skill: active_execution
---

# ACTIVE EXECUTION — Keep CEO Work on the Critical Path

Use this skill after current-state recovery whenever Sol is leading substantial continuing or
modifying work in the active session. It governs the middle of a CEO turn: after `COLD_START.md`
has found the frontier and before `CLOSEOUT.md` records the accepted result.

It does **not** create a lifecycle, scheduler, retry engine, memory store, queue, permission layer,
or background worker. Executive OS, Agent OS, GitHub, Linear, Slack, Workbench/process owners and
provider runtimes keep their existing authority.

## Mission

Advance the highest-leverage unfinished capability through the real critical path until either:

* the requested outcome is production-proven at the level the commission requires; or
* every materially useful in-scope lane is stopped by a genuine authority, effect-uncertainty,
  platform, or external-human boundary.

A detailed status artifact is not a substitute for capability advancement. A blocker on one lane is
not permission to end the whole turn while another in-scope critical-path lane remains executable.

## Step 1 — Freeze the active-turn frame

After recovery/reconciliation, keep one compact working frame:

```text
OUTCOME
CURRENT_CRITICAL_DEPENDENCY
ACTIVE_LANE
HELD_OR_BLOCKED_LANES
LAST_MATERIAL_CAPABILITY_DELTA
MATERIAL_INVALIDATORS_SINCE_PIN
TOOL_SURFACE_STATE
FINALIZATION_CLASSIFICATION
```

This is an ephemeral reasoning aid, not a new truth store. Do not persist it as another lifecycle
ledger. Exact durable facts still belong to their canonical owners.

`CURRENT_CRITICAL_DEPENDENCY` is the next dependency whose completion most directly unlocks the
requested outcome. Do not replace it with the easiest available task merely to show activity.

## Step 2 — Execute one observable capability step

Choose the smallest action that can materially advance the current dependency. Prefer an action that
produces one of these observable deltas:

* a previously absent user/machine capability now works;
* a blocking implementation defect is removed;
* a required real-path proof is obtained;
* a required authority/review/release gate is truthfully closed;
* a durable worker/process is lawfully started for work that should outlive this reasoning turn;
* a material uncertainty is converted into an exact known state that unlocks the next action.

Run the action through the canonical owner/tool. Preserve source-writer custody, one-carrier effect
reconciliation, and all modification gates from `INDEX.md`.

## Step 3 — Require a capability delta, not activity

After each material action, ask only what changed in externally recoverable capability state.

Supporting work includes archaeology, manifests, reviews, ledgers, receipts, documentation, test
runs, refactors, handoffs and status summaries. Supporting work is valuable when it unlocks, de-risks,
or proves the capability. It is not itself forward motion merely because it is thorough.

If two consecutive material work cycles produce **no capability delta and no newly resolved blocking
uncertainty**, declare `NO_DELTA_LOOP` and re-plan immediately. Do not produce a third equivalent
artifact/status cycle. Change tactic, change the in-scope lane, or name the real blocker.

## Step 4 — Treat a blocker as lane-local first

When the active lane hits a boundary:

1. classify it precisely: `HUMAN_AUTH`, `PERMISSION`, `TOOL_DEGRADED`, `EFFECT_UNKNOWN`,
   `WAITING_EXTERNAL`, `SOURCE_COLLISION`, `PLATFORM_FAILURE`, or another exact accepted type;
2. freeze that lane without inventing success or retry authority;
3. inspect the already-authorized program DAG for the highest-leverage path-disjoint dependency;
4. if one exists, switch to it immediately and continue;
5. stop the whole turn for the blocker only when every materially useful in-scope lane is blocked,
   or when proceeding elsewhere would violate dependency/authority law.

Example: a local administrator authentication ceremony blocks installation, but nonprivileged
preflight, exact release qualification, or a disjoint implementation dependency remains available.
The authentication gate stops installation only; it does not terminate the CEO turn.

Never route around a denial or `EFFECT_UNKNOWN` mutation by changing carriers, devices, providers, or
tools. Lane switching is for genuinely independent permitted work. An `EFFECT_UNKNOWN` in one lane
does not itself permit finalization while another useful lane is provably independent of the unknown
effect; freeze the uncertain lane and continue only work whose safety and result cannot depend on it.

## Step 5 — Bound reconciliation and concurrent-session churn

Freeze the exact repo/PR/branch/operation identities needed for the next action. Reconcile again only
when a **material invalidator** could change that action, such as:

* the owned carrier/head changed;
* governing authority/procedure changed;
* a dependency or imported interface changed;
* a worker returned material evidence;
* a modifying effect became ambiguous;
* a relevant production/runtime generation changed.

Unrelated protected-master movement, another session's path-disjoint merge, or a new status message is
not a reason to restart global archaeology. Apply the bounded compatibility rules in
`RECONCILE_STATE.md` and return to execution.

## Step 6 — Discover tool capability once, then react to evidence

Use the current tool surface rather than assumptions. For host tools, apply the current protected
host-discovery procedure when present. Within a stable connection/generation:

* discover the needed schema/capability once;
* record a tool lane as usable, degraded, refused, or unknown from direct evidence;
* do not repeatedly rediscover the same failure in place of useful work;
* re-probe only after a connection/device/schema change, an explicit recovery signal, or when the
  next critical action genuinely requires fresh proof.

A listed/online device is not proof its backend can execute. A successful ping is not proof of file,
process, browser, desktop, or provider-session readiness. Conversely, one degraded connector does not
make unrelated GitHub/research/file lanes unavailable.

## Step 7 — Offload work that should outlive the reasoning turn

A ChatGPT reasoning turn is not a daemon. Once Sol sends a final response, local reasoning and tool
execution for that turn stop.

When work involves long waits, builds, tests, external workers, durable process handles, or provider
execution that should survive the current turn, use the existing production-proven Executive,
Workbench/process, provider-worker, watcher/dialogue, or other canonical owner when current authority
allows it. Record the exact Job/Attempt/process/operation identity and return path.

Never claim work will continue in the background unless a real external durable owner has accepted or
started it and canonical evidence supports that claim. `QUEUED`, delivered, acknowledged, started,
running, completed and accepted remain distinct.

If no such durable execution capability is production-proven for the needed action, continue useful
work in the present turn and report that limitation truthfully at the eventual stop boundary.

## Step 8 — Final-response gate

Before ending a substantial active-execution turn, classify the state into exactly one of:

* `PROVEN_OUTCOME` — the requested capability meets its declared completion/proof law;
* `EXACT_HUMAN_GATE` — the only remaining critical action requires a specific human/admin ceremony
  that this session cannot lawfully perform, and every other useful in-scope lane is exhausted;
* `EFFECT_UNKNOWN` — an unresolved modifying effect makes every remaining useful in-scope action
  unsafe or dependent on that unknown effect; same-carrier reconciliation is required before any
  further scoped continuation can be safe;
* `ALL_SCOPED_LANES_BLOCKED` — every materially useful authorized lane is blocked, with exact blockers
  and next owners known;
* `PLATFORM_FAILURE` — the required platform/tool substrate is unavailable and no independent useful
  in-scope lane remains;
* `DURABLE_EXECUTION_RUNNING` — real external durable execution is proven started/running under its
  canonical owner, with a lawful return/wake path armed; local turn continuation would add no useful
  work until that result arrives.

If the truthful classification is `MORE_WORK_EXISTS`, **do not finalize**. Select the highest-leverage
unblocked dependency and continue execution.

A requested effort window such as "work for 60–120 minutes" is not a correctness boundary. Use the
productive turn fully; stop on outcome/gate evidence, not because an arbitrary amount of time elapsed
or because enough prose was produced.

## Step 9 — Make every genuine stop recoverable

When a permitted finalization class is reached, leave:

```text
FINALIZATION_CLASSIFICATION
CAPABILITY_DELTA
EXACT_CURRENT_IDENTITIES
BLOCKED_LANES_AND_REASON
DURABLE_EXECUTION_OR_RETURN_REF (if any)
EXACT_NEXT_ACTION
WHAT_MUST_NOT_BE_REDONE
```

Use `CLOSEOUT.md` after material implementation, proof, ruling, reconciliation or handoff so a fresh
session can recover without this chat. Store each fact only in its existing canonical owner.

## Pressure cases

### A — local human gate, another lane open

Installation reaches a native administrator prompt. Source/release qualification and nonprivileged
preflight remain unfinished and path-disjoint. Correct behavior: freeze installation as
`HUMAN_AUTH`, continue the best unblocked lane, and do not finalize as `EXACT_HUMAN_GATE` yet.

### B — connector write disappears

A GitHub or Slack write action is unavailable but read/research/host work needed for the same outcome
remains legal. Correct behavior: record the missing write capability once, keep any effect-unknown
operation on its original carrier, and continue independent useful work. Do not loop on capability
rediscovery.

### C — protected master moves on unrelated paths

The candidate-owned blobs and governing material source are unchanged. Correct behavior: perform the
bounded compatibility check required by `RECONCILE_STATE.md`, then resume. Do not restart the program
archaeology.

### D — artifact substitution

Two consecutive cycles produce another manifest, status report or decision matrix but no capability
delta or resolved blocker. Correct behavior: classify `NO_DELTA_LOOP`, re-plan, and execute a real
capability step before producing more support artifacts.

### E — turn-independent execution claim

Sol has not started an Executive Attempt, Workbench/process handle, external worker, or equivalent
canonical durable executor. Correct behavior: never say "work will keep running after this reply."
If useful local work remains, continue it; otherwise stop with the exact missing durable capability.

## K5 pass criteria

A substantial CEO continuation passes this skill when:

* the primary outcome and current critical dependency remain explicit;
* one blocked lane never ends the whole turn while a useful independent lane remains;
* two non-delta cycles force re-planning instead of a third status/artifact loop;
* tool degradation is recorded once per stable generation rather than rediscovered repeatedly;
* unrelated concurrent movement does not trigger global archaeology;
* no effect-unknown modification changes carrier or gets blind-retried;
* effect uncertainty in one lane does not become a global stop while a useful lane is provably
  independent of that uncertainty;
* no background continuation is claimed without a real durable owner and return path;
* Sol never finalizes while the truthful state is `MORE_WORK_EXISTS`;
* the final stop classification and exact next action are recoverable by a fresh session; and
* no new lifecycle, queue, retry, memory, permission, or control plane was created to enforce this
  procedure.
