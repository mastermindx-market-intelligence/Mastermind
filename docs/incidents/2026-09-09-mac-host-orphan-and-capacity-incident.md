# Mac host orphan and capacity incident — 2026-09-09

**Status:** RECORDS_ONLY / INCIDENT_CONTAINED / LOCAL_CARRIER_HARDENED / CANONICALIZATION_NOT_BUILT  
**Workstream owner:** existing `WS:EXECUTIVE-CAPACITY-FABRIC` plus the existing Worker Browser / DevServer Resource Fabric where browser resources are involved  
**Operation:** `mac-studio-orphan-capacity-incident-20260909-sol-001`  
**Chairman direction:** diagnose loud unattended-host fan activity, remove confirmed abandoned work, and harden recurrence without interrupting legitimate Claude, Grok, Codex or ChatGPT work  
**Protected source pin:** `mastermindx-market-intelligence/Mastermind@f3f2d9155796876009f2d427bfdecc7ee7b63e74`  
**Skillpack:** `mastermind.sol_skillpack.v1`, version `1.0.1`, bootstrap major `1`, loaded entirely from the protected source pin above

This document records an observed production-host incident and a bounded local containment. It is not merge authority, Executive service activation, CF2-P0 acceptance, provider-placement authority or permission to create another scheduler, queue, lifecycle store, process registry, retry plane or host-control plane.

## 1. Outcome before mechanism

### User job

The Chairman must be able to leave the Mac Studio unattended without returning to an unexplained hot host, abandoned agent descendants, silent saturation, or fan noise whose cause cannot be attributed.

### Machine job

Every admitted execution must have one accountable lifecycle owner; all descendants must remain bound to that owner; admission must stop before the host is saturated; browser/devserver work must consume a scarce host resource; and retired workspaces must leave the filesystem through an ownership-aware path.

### Moat

The durable advantage is not a generic process killer. It is one correction-safe chain from Executive Job and Attempt identity through host placement, process/session ownership, resource leases, receipts, visible operator state and exact cleanup. Unknown processes remain evidence to reconcile, not objects to kill by guess.

### 10/10 end state

A fresh Sol can answer, without opening Activity Monitor:

1. which Executive Attempt owns every heavy local process tree;
2. why it was admitted on this host;
3. which total-CPU and browser/devserver leases it consumes;
4. whether the attempt is active, draining, timed out, interrupted or effect-unknown;
5. whether all descendants were reaped;
6. which worktrees and dependency trees remain and why;
7. whether the host is in normal, saturated, draining or quiet mode; and
8. the exact safe next action when any invariant fails.

## 2. Verified incident

The inspected host was the authorized M2 Ultra Mac Studio with 24 logical CPU cores. At the start of the incident investigation:

- load average was approximately 26 on 24 logical cores;
- the host had approximately 1,694 processes and 17,344 threads;
- macOS reported no thermal or performance warning;
- the machine was being kept awake by active application and command-line power assertions;
- legitimate Claude, Grok, Codex, ChatGPT, Playwright, Next.js and browser work was still running despite no physical interaction overnight.

### 2.1 Confirmed abandoned process

One process was proven abandoned rather than inferred from its name:

- PID `21081`, Python 3.14;
- parent PID `1`, after its original parent had exited;
- sustained approximately 96–100% CPU;
- launched on 2026-09-01 and still running more than eight days later;
- approximately 185 accumulated CPU-hours;
- current working directory inside an old Claude/Fable scratch worktree;
- the referenced scratch directory and task-output file no longer existed;
- a stack sample showed active Python list/string/Unicode work rather than harmless sleep.

Only this confirmed abandoned PID was terminated. A second kill attempt returned process-not-found, and a fresh process read confirmed the PID was absent.

### 2.2 Legitimate saturation

The orphan was not the whole incident. A fresh census found twelve simultaneous external lanes while the only available cap was prose saying “local cap 4.” The launcher did not enforce that cap. The one-minute load reached approximately 43 on the 24-core host.

The workload included real build/review waves, Python contract checks, Git scans, Playwright browser tests, Next.js development servers and Chromium renderers. These processes retained valid parent chains and were not killed.

### 2.3 Filesystem-event and indexing amplification

The external `/Volumes/Mastermind` APFS SSD was healthy and had approximately 2.5 TiB free, but it contained a very large active namespace:

- approximately 9.7 million filesystem objects reported by `df`;
- 579 registered Git worktrees across the three inspected repositories:
  - Mastermind: 214;
  - macro: 254;
  - Terminal: 111;
- 112 external Claude workspace roots;
- 44 Terminal `node_modules` trees;
- 53 observed dependency materializations made through APFS clone semantics.

APFS clones avoid copying every data block, but each clone still creates a large new directory namespace for filesystem-event consumers and indexers to observe.

A six-sample, 50-second trend showed `fseventsd` rising from approximately 186% CPU to approximately 270% CPU while its resident memory continued increasing. The event daemon logs repeatedly recorded short-lived FSEvents client registrations without bundle identifiers. A live 25-second capture identified one such client as a legitimate `next-server` under a Playwright reviewer worktree; it generated more than twenty registration errors in roughly four seconds.

This is evidence of watcher and namespace amplification, not proof that the log message alone accounts for all `fseventsd` CPU. No system daemon was killed, no indexing policy was changed, and no privilege escalation was attempted.

### 2.4 Worktree retention

A read-only worktree census found:

- Mastermind: 209 present, 5 missing/prunable, 17 locked, 112 present for more than seven days;
- macro: 239 present, 15 missing, 74 locked;
- Terminal: 111 present, 43 locked;
- 95 registered paths under old Claude private-temp roots.

Only five Mastermind records were trivially prunable by `git worktree prune --dry-run`. The remaining estate cannot be deleted safely from age alone because worktree age does not prove closed ownership, clean state, release completion or absence of another worker.

The existing host worktree-storage helper allocates and checks worktrees but intentionally has no scheduler or workload-admission policy and no retirement command. No ad hoc removal was performed.

## 3. Root causes

### RC-1 — direct-child timeout was mistaken for tree cleanup

The active external lane used `subprocess.run(..., timeout=...)`. On timeout Python terminated only the direct child. A grandchild could survive, be adopted by PID 1 and continue indefinitely. There was no private process session, no transitive cleanup, no SIGTERM/SIGINT/SIGHUP cleanup and no normal-exit descendant check.

A controlled RED test reproduced the defect:

```text
RED_OBSERVATION child_pid=28466 original_ppid=28465 observed_ppid=1 pgid=4642 alive_after_timeout=true
AssertionError: legacy timeout left its grandchild running
```

The test descendant was then killed and its absence verified.

### RC-2 — the local lane cap was descriptive, not executable

The same operational notes recorded load spikes of 79 and 145–171 and as many as eleven simultaneous lanes, yet the launcher admitted work without a lock, active-count gate or host-load gate. Written etiquette could not prevent a new wave from starting during saturation.

### RC-3 — browser/devserver work was not represented as a scarce resource

A lane could run multiple Playwright workers and start its own Next.js development server while consuming the same undifferentiated lane slot as a lightweight read or Git check. Next development servers establish filesystem watchers and can create process groups inside the agent’s session. No global browser/devserver token bounded this amplification.

### RC-4 — process ownership stopped at the launcher boundary

The existing Executive supervisor source already has process-group cleanup, but the ad hoc Fable external lane did not run through that canonical lifecycle. Direct Claude/Cursor/Grok sessions launched outside the carrier also remain outside its automatic cleanup boundary.

### RC-5 — workspace creation had no paired retirement owner

The lane reuses one fix and one review worktree per PR or label, so it does not create two new trees every round. It does create durable trees for every distinct packet, and no accepted owner closes the loop when a PR is merged, closed, superseded or abandoned. Dependency namespaces therefore accumulate even when disk blocks are shared.

### RC-6 — unattended work and quiet overnight behavior were conflated

The host was intentionally prevented from sleeping while long-running agents remained eligible to work. A host that is actively running build and browser workloads cannot also be assumed quiet. The system needs an explicit operating mode, not an implicit expectation that physical inactivity means computational inactivity.

## 4. Bounded containment applied on the host

### 4.1 Confirmed orphan removal

PID `21081` was terminated only after parent, age, working-directory, deleted-output and sustained-CPU evidence agreed. No process was killed merely for having PPID 1, high CPU, a Claude/Grok name or an old start time.

### 4.2 Transitional local carrier hardening

The existing hot-state carrier at `~/.claude/.../meta-ceo-b-2026-09-08/ext/lane.py` was hardened in place under checksum compare-and-swap. This did not modify a Git checkout and is not a substitute for reviewed protected source.

Exact source transition:

```text
legacy lane.py
f0591dba91090bff77f83fd0dedf152342e8bb9d426a89c6888590f562230264

installed lane.py
199330a804e00fd38181490ca9f0f13d89bc25db21078a838c20a1da203ca7b2

installed lane_runtime.py
1b9caf07df82cece59ac0e2b78e6a5618a06c61cca0756a21671af7f18da718f
```

The installed behavior now provides:

- a private process session for each shell or agent command;
- verified cleanup of every remaining process in that owned session, including descendants that create a different process group;
- descendants-first, leader-last SIGTERM followed by bounded SIGKILL escalation;
- cleanup after timeout, parent exception, SIGTERM, SIGINT, SIGHUP and normal leader exit with lingering descendants;
- identity-mismatch refusal rather than broad group/session signaling;
- crash-safe advisory lane leases over the pre-existing `active/` marker directory;
- stale JSON-lease recovery only when the lease is unlocked;
- fail-closed counting of legacy markers without deleting them;
- duplicate lane-key exclusion;
- default maximum of four active lanes;
- refusal when one-minute load is at or above the 24-core host’s logical CPU count;
- bounded environment overrides only: active lanes 1–8, load ratio 0.5–1.5, niceness 0–19;
- default child niceness of 5;
- admission before GitHub reads, branch resolution or worktree allocation;
- exit code 75 and a redacted refusal receipt when admission fails;
- process receipts that omit command arguments, prompts, environment values, stdout and stderr.

### 4.3 Test evidence

The final exact installed bytes passed:

```text
15 runtime tests: OK
7 lane integration tests: OK
Python compilation: PASS
warnings-as-errors: PASS
three repeated full focused runs: PASS
```

The runtime tests include timeout cleanup, normal-exit cleanup, signal cleanup, SIGTERM-resistant escalation, same-session multigroup descendants, identity mismatch, stale crash leases, duplicate keys, active/load refusal and receipt redaction.

The integration tests prove both execution paths use the owner, shell timeout remains fatal after cleanup, admission happens before branch/worktree effects, the old plain marker write is absent and live saturation is refused before GitHub or worktree effects.

A pre/post process-identity comparison showed that the install signaled no existing worker, changed no surviving parent/process-group identity and restarted no active lane. Legacy lanes continued under the old loaded code and drained naturally. Future launches load the hardened carrier.

### 4.4 Rollback

The transition produced two local rollback copies and two redacted install receipts. Rollback requires restoring the legacy launcher before removing its helper. No rollback is automatically authorized from this document.

## 5. Safety and no-change proof

The incident response did **not**:

- enable the installed but disabled Executive launchd services;
- claim CF2-H0 native host acceptance, CF2-P0, CF2-I or provider readiness;
- create or mutate an Executive Job, Attempt, Worker or Event record;
- start, stop, sign in, switch or reconnect any provider account;
- terminate a legitimate Claude, Grok, Codex, ChatGPT, Playwright or browser wave;
- kill or restart `fseventsd`, Spotlight, WindowServer or DisplayLink;
- disable indexing or change the external volume;
- delete a worktree, branch, dependency tree or cache;
- read or record command prompts, credentials, tokens or full process arguments;
- create a second scheduler, lifecycle, registry, process authority or retry plane.

## 6. Capability ledger

| Capability | State | Evidence / boundary |
|---|---|---|
| Confirmed eight-day runaway removed | PROVEN_LIVE | PID absence observed after a single bounded kill |
| Future external-lane timeout tree cleanup | PROVEN_ON_HOST_SYNTHETIC | exact installed bytes pass timeout, resistant-child and multigroup tests |
| Future external-lane normal-exit and signal cleanup | PROVEN_ON_HOST_SYNTHETIC | exact installed bytes pass normal-exit and parent-signal tests |
| External-lane total admission cap and load refusal | PROVEN_ON_HOST_SYNTHETIC | exact installed bytes refuse before branch/worktree effects |
| Natural real worker timeout after the install | BUILT_NOT_PROVEN | no destructive production timeout was induced merely to obtain proof |
| Direct workers launched outside this lane carrier | DARK_OR_DISCONNECTED | no automatic owner binding exists for every native-app/CLI launch |
| Global browser/devserver host token | NOT_BUILT | browser-heavy work is still implicit inside ordinary lanes |
| Ownership-aware worktree retirement | NOT_BUILT | census exists; deletion authority and acceptance contract do not |
| FSEvents/Spotlight stabilization | PARTIAL | producers identified and future admission reduced; no zero-load persistence proof yet |
| Quiet overnight mode | NOT_BUILT | no admission-drain-release schedule exists |
| Canonical Executive OS integration | NOT_BUILT | local hot patch is transitional and intentionally does not mint durable lifecycle state |

## 7. Architecture ruling for the durable solution

### 7.1 One lifecycle owner

Executive OS remains the sole Job / Attempt / Worker / Event lifecycle and effect-reconciliation authority. The durable implementation must not turn `lane_runtime.py`, launchd, a shell wrapper, Activity Monitor, a new database or a worktree janitor into a parallel lifecycle.

The local carrier may remain a thin adapter only until its work is admitted as an Executive Attempt. At that point the existing Executive supervisor owns the private session/process tree and emits the existing lifecycle events.

### 7.2 One placement and capacity owner

Macro Shared AI Provider Control remains provider/account capacity authority; Capacity Fabric and Model Router remain host/provider/model placement owners. Host pressure is another placement input, not a new provider registry.

The durable host contract needs at least two resource dimensions on the existing Attempt admission path:

1. `host_total_lane` — canary ceiling four on the 24-core M2 Ultra;
2. `browser_devserver` — canary ceiling one, eligible to rise to two only after a measured sustained interval shows stable load, memory and filesystem-event behavior.

A browser-heavy Attempt consumes both. A lightweight read consumes only `host_total_lane`. The resource field must be derived from a reviewed commission or deterministic tool plan, not from model self-assertion after execution starts.

### 7.3 Browser/devserver ownership

The existing Worker Browser / DevServer Resource Fabric owns browser and devserver process resources. Playwright shards must not each mint an untracked Next development server.

The preferred useful vertical is one leased devserver per exact repository/head/environment identity, reused by its admitted browser proof and reaped with the Attempt. A production-build server or other watcher-minimizing path may replace `next dev` only after the touched Terminal tests prove semantic parity; “less CPU” alone is not license to change the test path.

### 7.4 Unknown-process law

A read-only orphan detector may emit candidates with PID, parent, session, age, CPU trend and safe executable identity. It may not kill them. Automatic cleanup requires one of:

- the current owner’s verified private process session;
- an exact accepted Executive Attempt binding;
- a separately authorized manual determination with evidence equivalent to this incident.

PPID 1, age, missing terminal window, name matching, fan noise and high CPU are not sufficient alone.

### 7.5 Operating modes

The host needs explicit modes projected through the existing Control Room/Executive surface:

- **RUN:** new work may be admitted under resource and pressure gates;
- **DRAIN:** no new work; current Attempts checkpoint, finish or reach a typed stop;
- **QUIET:** no new work and no unnecessary keep-awake assertion after the drain is empty;
- **INCIDENT:** no new work; Sol receives the exact pressure, owner and reconciliation evidence.

This is policy over the existing lifecycle, not a new scheduler.

## 8. Ownership-aware worktree retirement contract

A future retirement implementation must extend the existing worktree-storage owner and use Git as the worktree registry. It must begin read-only and must never run `rm -rf` as the primary lifecycle action.

A worktree is only a retirement candidate when all of the following are proven at one observation revision:

1. no active Executive Attempt, local lane lease or accepted continuation owns it;
2. its PR/operation is merged, closed, superseded or explicitly abandoned by the current owner;
3. the worktree is clean, or every remaining change has a separately accepted preservation disposition;
4. it is not locked, or the lock owner explicitly releases it;
5. no live process has a current directory or open file under the path;
6. the branch/commit identity needed for recovery exists durably in GitHub or another accepted owner;
7. a retention window has elapsed;
8. the dry-run receipt names the exact path, repo, HEAD, dirty state, lock state, owner evidence and proposed action.

The modifying step then uses `git worktree remove` through the canonical helper, verifies registry/path absence, runs bounded `git worktree prune`, and records the result. A failure or timeout is effect-unknown until path and registry state are re-read; there is no blind retry.

Dependency clones under a retired worktree leave only as part of that same worktree effect. The node-module cache itself is a separate shared artifact and is not deleted by worktree retirement.

## 9. FSEvents and indexing correction sequence

Do not begin by killing `fseventsd` or disabling Spotlight for the whole external volume. First remove the producer pressure lawfully:

1. enforce total and browser/devserver admission;
2. reuse one devserver resource rather than spawning one per shard where test semantics permit;
3. retire accepted stale worktrees through the contract above;
4. stop creating fresh full dependency namespaces when an exact read-only cache mount or other verified representation can serve the consumer;
5. observe `fseventsd` after browser/devserver count reaches zero and no worktree/dependency materialization is occurring.

Only if `fseventsd` remains persistently above a ruled threshold during that true zero-producer interval should a separate macOS daemon/index investigation or controlled host reboot be commissioned. This incident did not establish that zero-producer condition.

## 10. Next bounded vertical

### Mission

Integrate host process-session ownership and two-dimensional host admission into the existing Executive Attempt/supervisor path, then project one useful host-pressure receipt without enabling provider work or creating another lifecycle.

### Why it matters

The local hot patch protects one carrier. The product requirement is that all governed unattended work has the same property, including browser-heavy work and direct provider adapters.

### Authority precedence

1. live Chairman direction for this incident;
2. current protected Skillpack and Executive OS law;
3. current `WS:EXECUTIVE-CAPACITY-FABRIC` and Worker Browser / DevServer Resource Fabric ownership;
4. this records-only incident where it does not conflict with accepted source law.

### Verified state

- Executive supervisor source already owns supervised process cleanup;
- installed Executive service definitions remain disabled and no activation was authorized;
- CF2-H0 source protection does not establish native host acceptance or authorize CF2-P0/provider work;
- the local lane adapter now supplies host-proven falsifiers and exact behavior to port, not a new canonical owner.

### Exact scope

One independently useful PR should add, through existing Executive admission/supervisor owners:

- an Attempt-bound private process-session identity;
- timeout, interruption and normal-exit descendant reconciliation;
- `host_total_lane` and `browser_devserver` resource leases;
- pressure refusal before worktree/provider/GitHub modifying effects;
- a redacted operator receipt/projection;
- focused tests and one bounded Mac production proof.

### Non-goals

No Executive service activation merely because source exists; no provider login or model call; no global process scan-and-kill; no worktree deletion; no new scheduler/store/registry; no heuristic account failover; no replay of effect-unknown work; no whole-estate refactor.

### Required acceptance and production proof

1. RED-first test reproduces direct-child timeout orphaning.
2. A timeout reaps a child, grandchild and same-session different-process-group descendant.
3. Normal leader exit with a descendant is reconciled.
4. SIGTERM/SIGINT/HUP cleanup is bounded and leaves zero owned-session residuals.
5. Session identity mismatch refuses broad signaling.
6. Active total-lane ceiling refuses the next Attempt atomically.
7. One browser/devserver token refuses a concurrent second browser-heavy Attempt during canary.
8. Host saturation refuses before provider, worktree or GitHub modifying effects.
9. Unknown PPID-1 process candidates are reported but never automatically killed.
10. A real disposable governed Attempt runs through the actual Mac supervisor path to a visible receipt, then exits with zero descendants.
11. A browser-heavy canary runs through the real resource owner, produces its expected user/machine result and leaves zero devserver/browser descendants.
12. Current legacy behavior for unrelated Attempts remains unchanged.

### Stop condition

Stop at `BUILT_NOT_PROVEN / PRODUCTION_DISARMED` until exact-head independent review, hosted checks, current protected integration and the bounded real Mac proof all agree. Native service activation and fleet admission remain separate Sol/Chairman gates.

## 11. Exact continuation handoff

A fresh operator should:

1. reload the current protected Skillpack from one exact protected commit;
2. reconcile current protected Mastermind, Macro Agent OS, open CF2/Worker-Browser PRs and exact path ownership;
3. read the local red/green evidence and installed receipt without treating the hot patch as current law;
4. select the one existing Executive supervisor/admission carrier with no path collision;
5. implement the bounded vertical above using RED-first tests;
6. obtain independent adversarial review;
7. prove the disposable Mac journey and visible receipt;
8. update Agent OS workstream/decision state and the exact next action after accepted material work.

Do not ask the Chairman to allocate routine provider accounts, manually identify stale processes or relay routine shell commands. Do not enable disabled services, delete worktrees or restart system daemons to make a green-looking status.
