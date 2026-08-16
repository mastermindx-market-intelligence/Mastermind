# Executive OS Phase 1G — Agent Fabric Infrastructure Design

**Status:** infrastructure contract for implementation waves; **not deployed or armed**  
**Program:** Multi-Provider Agent Fabric  
**Base:** `3823a2bb000946dc6d318ec1ba6f163d67046884`  
**Companion documents:**

- `research/EXECUTIVE_OS_PHASE1G_AGENT_FABRIC_MASTER_DESIGN.md`
- `research/EXECUTIVE_OS_PHASE1G_MASTERPLAN_AND_WAVES.md`
- `research/EXECUTIVE_OS_PHASE1F_ORCHESTRATION_CONTRACT.md`
- `research/EXECUTIVE_OS_PHASE1C_A_SECURE_SUPERVISOR.md`

---

## 0. Infrastructure verdict

The existing Phase 1C-A control/worker split remains the security foundation. Phase 1G scales it by introducing **isolated worker slots**, not by turning the interactive Mac user, one shared worker UID, tmux, or a provider desktop app into the control plane.

The selected host model is:

```text
one durable control service
        │
        ├── one typed broker socket per worker slot
        │
        ├── one dedicated OS principal per concurrently active slot
        │
        ├── one provider home / credential boundary per account
        │
        ├── one active Attempt per slot initially
        │
        └── one exact assigned worktree per Attempt
```

A provider account may eventually expose several separately metered pools, but it does not share provider-home credentials with another account. A pool limit affects only its account/pool/horizon records.

ChatGPT Business Workspace Agents are outside the worker-slot fleet. That account is a protected executive surface and is registered as non-claimable capacity. Dedicated Codex Max accounts are separate worker accounts, each with its own worker principal, provider home, pool state, and whole-UID cleanup boundary.

---

## 1. Host topology

### 1.1 Persistent services

```text
launchd
  ├─ com.mastermind.executive.control
  │    principal: _mastermind_exec
  │    owns: Executive SQLite, policy/config projections, worktree creation,
  │          placement, receipts, backups, control socket
  │
  ├─ com.mastermind.executive.worker.codex-01
  │    principal: _mastermind_codex_01
  │    owns: CODEX_HOME_01, worker state, private broker socket endpoint
  │
  ├─ com.mastermind.executive.worker.codex-02
  │    principal: _mastermind_codex_02
  │
  ├─ com.mastermind.executive.worker.glm-01
  │    principal: _mastermind_glm_01
  │
  ├─ com.mastermind.executive.worker.qwen-01
  │    principal: _mastermind_qwen_01
  │
  ├─ com.mastermind.executive.worker.cursor-01
  │    principal: _mastermind_cursor_01
  │
  └─ com.mastermind.executive.worker.grok-01
       principal: _mastermind_grok_01
```

Only provisioned slots exist. The list above is a shape, not a requirement to create every account immediately.

### 1.2 Why one principal per slot

The Phase 1C-A worker’s whole-UID residual sweep assumes every other process under the worker UID is residue. Reusing that UID for several providers or accounts would make cancellation of one Attempt capable of killing unrelated workers.

Therefore:

- different concurrently active slots use different UIDs;
- different provider homes are never multiplexed by environment mutation inside one long-running broker;
- a provider account starts with one slot unless provider terms and acceptance prove safe concurrency;
- scaling one account to several concurrent slots requires either separate credentials/subaccounts or a reviewed same-account concurrency design that preserves process isolation and plan terms.

### 1.3 Root is installer only

Root may:

- provision service accounts and groups;
- install reviewed binaries and launchd plists;
- create root-owned config/receipt roots;
- set ownership/modes;
- install or remove worker-slot definitions;
- perform offline restore.

Root never runs an agent Job and never becomes a generic provider credential broker.

---

## 2. Filesystem layout

The exact paths may be adjusted by a later implementation PR, but the ownership and separation laws are binding.

```text
/Library/Application Support/MastermindExecutive/
  releases/<exact-sha>/                       root:wheel, immutable reviewed code
  bin/
    codex-<version>                           root:wheel 0555
    qwen-<version>                            root:wheel 0555 or signed install receipt
    provider wrappers                         root:wheel 0555
  config/
    control.json                              root:_mastermind_exec 0440
    worker-slots.json                         root:_mastermind_exec 0440
    placement-policy.json                     root:_mastermind_exec 0440
    worker/<slot-id>.json                     root:<slot-group> 0440
  receipts/
    runtime/
    binaries/
    provider-adapters/

/var/db/mastermind-executive/
  control/                                    _mastermind_exec 0700
    db/
    admin-checkout/<exact-sha>/
    launch-receipts/
    placement-receipts/
    capacity-receipts/
    backups/
  jobs/
    workspaces/                               control:worker-parent 0710
    runs/                                     control:worker-parent 0710
    handoffs/                                 _mastermind_exec 0700
  workers/
    codex-01/
      provider-home/                          _mastermind_codex_01 0700
      state/                                  _mastermind_codex_01 0700
      tmux/                                   _mastermind_codex_01 0700
    codex-02/
      provider-home/                          _mastermind_codex_02 0700
      state/                                  _mastermind_codex_02 0700
      tmux/                                   _mastermind_codex_02 0700
    glm-01/
    qwen-01/
    cursor-01/
    grok-01/

/var/run/mastermind-executive/
  control.sock                                launchd, control:ops 0660
  workers/
    codex-01.sock                             launchd, control:control 0600
    codex-02.sock
    glm-01.sock
    qwen-01.sock
    cursor-01.sock
    grok-01.sock
  tmux/
    <slot-id>.sock                            slot principal only

/var/log/mastermind-executive/
  control/                                    control only
  workers/<slot-id>/                          slot principal; collected/sanitized by control
```

The provider-home directories contain authentication state and are never placed inside a worktree, repository, run artifact, backup exported to Git, MCP result, or model prompt.

---

## 3. Configuration authorities

### 3.1 Tracked policy versus host inventory

The public repository tracks schemas, allowed provider/adapter kinds, placement policy, and test fixtures. It does **not** track real account emails, credential values, OAuth state, browser profiles, or provider-home contents.

Recommended split:

```text
tracked and reviewed
  config/provider_catalog.yml
  config/agent_profiles.yml
  config/placement_policy.yml
  schema definitions and synthetic fixtures

root-owned host inventory
  /Library/Application Support/MastermindExecutive/config/worker-slots.json
  stable opaque account_id and slot_id
  provider/plan/compliance/capacity-domain metadata
  credential_ref/provider_home path
  no secret values

protected provider home
  actual auth state, readable only by slot UID
```

### 3.2 One-source rule

Static installed worker identity comes from the root-owned exact-SHA host inventory. The Executive database contains the currently registered projection and lifecycle state, bound to the inventory digest.

On control-service startup:

1. verify installed inventory ownership, mode, schema, canonical paths, and digest;
2. compare each runtime worker/account registration against the installed digest;
3. mark removed/drifted slots DRAINING/OFFLINE rather than silently recreating them;
4. refuse placement on unregistered or drifted slots;
5. never infer credentials from environment-variable discovery.

This is policy/config → runtime state, not two competing authorities.

### 3.3 Account identity

Use stable opaque identifiers such as:

```text
chatgpt-business
codex-max-01
codex-max-02
anthropic-lead-01
zai-max-01
alibaba-team-seat-01
xai-heavy-01
cursor-ultra-01
```

Do not store provider login email addresses unless there is a demonstrated operational need and a reviewed private field. Public projections receive bounded labels only.

---

## 4. Worker-slot lifecycle

### 4.1 Provision

```text
root installs reviewed release
→ root creates dedicated principal/group/home
→ root installs slot config and launchd template
→ provider authentication is completed under the slot principal
→ worker broker starts but remains NOT_READY
→ broker performs binary/config/provider-home identity checks
→ bounded provider probe verifies authenticated tool access without exposing secrets
→ control service registers slot/account/pools
→ slot enters AVAILABLE only after acceptance receipt
```

Provider authentication may require an interactive operator/device-login step. That is provisioning, not Job execution, and it must not be simulated by copying another account’s provider home.

### 4.2 Drain

```text
operator/control marks slot DRAINING
→ no new placement
→ current Attempt completes or is explicitly cancelled
→ whole-UID/session reconciliation
→ slot OFFLINE
```

### 4.3 Remove or rotate

Removal or credential rotation requires:

- slot drained/offline;
- provider process/session absence;
- provider-home replacement under the same principal or a fresh slot identity;
- new acceptance/probe receipt;
- updated inventory digest;
- explicit runtime registration update.

A successful request after an auth failure may clear an auth horizon only under a provider-specific rule; it never clears unrelated weekly/monthly hard limits.

---

## 5. Control-to-worker protocol

The control service never sends arbitrary shell or prompt-selected executable paths.

### 5.1 Versioned operations

```text
status
health
probe-capacity
prepare-attempt
start-attempt
attempt-status
read-events
send-typed-input
checkpoint
interrupt
collect
cancel
reconcile
```

### 5.2 `WorkerSlotSpec`

Installed and trusted, not model-authored:

```text
schema
slot_id
account_id
pool_ids
provider
adapter_id
execution_runtime
service_principal
provider_home
broker_socket
binary identities
allowed environment keys
max_concurrency
compliance_mode
inventory_sha256
```

### 5.3 `LaunchSpec`

Derived from canonical Job/Attempt/placement state:

```text
schema
job_id
attempt_id
fence_generation
lease-bound launch nonce
worker/slot/account/pool identity
adapter and exact model alias resolution
objective digest
prompt/input artifact reference
worktree and run identities
base SHA
allowed write paths
test argv
skill bundle digest
network/tool policy
wall-clock/turn/output limits
sibling-denial manifest
```

Raw provider credentials, lease tokens, and unbounded prompts do not appear in public receipts.

### 5.4 Kernel peer identity

Every worker broker accepts only the configured control principal through kernel-reported peer credentials. A worker cannot call a sibling broker or the control DB.

---

## 6. Capacity telemetry architecture

### 6.1 Observation sources

In descending confidence:

1. provider usage endpoint/plugin reporting exact or provider-calculated values;
2. structured response headers/fields;
3. structured CLI status output;
4. explicit provider rate-limit/reset error;
5. successful-session estimates;
6. bounded operator observation;
7. unknown.

### 6.2 Collection boundary

Provider probes that require provider authentication run under the worker-slot UID. The broker returns a strict non-secret `CapacityObservation`; it does not return provider-home files, cookies, tokens, or raw HTTP data.

```text
worker UID
  provider-specific probe
        ↓
  adapter sanitizes and validates
        ↓
  typed observation over private broker socket
        ↓
control validates slot/account/pool binding
        ↓
SQLite observation + event transaction
```

### 6.3 Polling policy

No high-frequency global poller is required initially.

Observations occur:

- at slot startup/acceptance;
- before a placement when state is stale beyond provider policy;
- after a completed or failed Attempt;
- on explicit rate-limit/auth/concurrency errors;
- through a bounded operator refresh command.

Provider polling is rate-limited and cannot block unrelated provider placement indefinitely.

### 6.4 Account isolation

An observation carries trusted slot/account/pool identity from installed config. Provider text cannot name a different account. A parser failure yields a degraded observation for that pool only.

For the current topology:

- `codex-max-01` limit affects only slot/pool 01;
- `codex-max-02` remains eligible;
- `chatgpt-business` is not a candidate regardless of its reported health;
- Claude, Cursor, Grok, GLM, and Qwen states never cross-update one another.

---

## 7. Placement and dispatch transaction

```text
queued child Job
→ build PlacementRequest from durable Job/profile/authority state
→ read canonical worker/account/pool/horizon projections
→ deterministic eligibility and rank
→ persist placement receipt or no-capacity exception
→ atomically claim selected worker quota class / create Attempt
→ bind Attempt to placement_id, account_id, pool_id, slot_id, adapter_id
→ prepare exact-SHA workspace
→ send typed LaunchSpec to selected broker
→ persist launch attestation and process/session identity
→ mark RUNNING only after durable identity receipt
```

A placement recommendation does not reserve capacity outside the atomic claim. If a race loses the slot, the transaction is abandoned and placement recomputes from fresh state.

---

## 8. Session runtime infrastructure

### 8.1 Structured process first

For Codex, Claude Code/GLM, Qwen Code, and Cursor CLI, prefer a directly supervised process when stable JSON/JSONL/stream output exists.

The broker owns:

- process group/session creation;
- stdout/stderr/event files;
- incremental parser cursor;
- provider session ID;
- bounded input channel where supported;
- cancellation and whole-slot cleanup.

### 8.2 ACP

Grok Build can use an ACP runtime where available. ACP transport remains inside the worker broker and is normalized to the common event contract.

### 8.3 tmux containment

Tmux is optional per Attempt and private per slot.

Use an explicit socket, never the interactive user’s default tmux server:

```text
/var/run/mastermind-executive/tmux/<slot-id>.sock
```

The broker invokes tmux with fixed argv and a slot-private environment. Session names are derived from Attempt IDs and validated against a strict regex.

Allowed internal primitives:

```text
new-session with reviewed executable argv
has-session
list-panes in machine format
capture-pane with fixed bounds
send-keys/literal input produced from a typed adapter action
send-signal / interrupt
kill-session
```

Forbidden:

- model-authored tmux argv;
- shell interpolation;
- attaching to the operator’s personal tmux server;
- session names from prompts;
- using pane text as sole completion evidence;
- leaving a session alive after terminal Attempt sealing.

### 8.4 Tmux adoption

After broker/control restart, adoption requires all of:

- active durable Attempt and unexpired/adoptable lease;
- matching slot/account/pool/adapter;
- matching tmux socket inode/owner/mode;
- matching session name;
- matching pane PID/PGID/start identity/boot ID;
- matching worktree identity and base SHA;
- no unexpected additional panes/processes;
- transcript cursor integrity.

Any ambiguity makes the Attempt LOST and triggers cleanup, never optimistic adoption.

### 8.5 Transcript transport

Provider events are written to a slot-private append-only event stream and selectively projected into bounded Attempt events/results.

ChatGPT MCP reads structured Job/Attempt state. A future transcript-tail tool, if commissioned, returns sanitized bounded deltas by cursor; it never creates a live generic terminal bridge.

---

## 9. Checkpoint and handoff storage

Checkpoint sources:

1. provider-native session checkpoint/reference;
2. Git checkpoint commit or deterministic patch artifact;
3. common structured progress payload;
4. validation/test receipts;
5. bounded transcript/event tail.

The control service owns the final `mastermind.agent_handoff.v1` artifact and digest. A worker may propose fields, but the supervisor fills objective, Job/Attempt identity, Git identity, changed-file census, validation receipts, and placement metadata from trusted state.

Handoffs are private runtime artifacts. Cross-session durable organizational discoveries still belong in Agent OS through the existing sanctioned process; the handoff is execution continuity, not a second knowledge store.

---

## 10. Multi-account Codex infrastructure

This is the first live expansion because the user already owns separate Codex-focused Max accounts and they do not consume the ChatGPT Business workspace account.

### 10.1 Initial shape

```text
account codex-max-01
  slot codex-01
  principal _mastermind_codex_01
  CODEX_HOME /var/db/.../workers/codex-01/provider-home
  pool codex-max-01.agentic-20x

account codex-max-02
  slot codex-02
  principal _mastermind_codex_02
  CODEX_HOME /var/db/.../workers/codex-02/provider-home
  pool codex-max-02.agentic-20x
```

Additional accounts follow the same template. Actual account count and login identities remain host/operator inventory.

### 10.2 Exact-model failover

A Codex Attempt that receives an account-specific hard limit:

```text
ATT-1 codex-max-01
→ RATE_LIMITED observation for pool 01
→ checkpoint/seal/requeue
→ placement T1 chooses healthy codex-max-02
→ ATT-2 in fresh worktree
```

No OAuth file or `CODEX_HOME` is swapped inside ATT-1. ChatGPT Business is not a candidate.

### 10.3 Provider binary

All Codex slots may share the same root-owned attested binary inode/path, but each uses a separate provider home and process principal. The installed binary receipt remains common; provider authentication remains slot-private.

---

## 11. New provider infrastructure

### GLM Max

- one slot/principal/provider home initially;
- officially supported client path;
- explicit five-hour and weekly capacity horizons;
- provider usage query normalized through broker;
- conservative max concurrency 1 until live evidence and terms support more.

### Qwen / Alibaba

- technical adapter supports Qwen Code structured mode;
- entitlement compliance mode controls whether the slot is autonomous;
- Team Plan begins `operator_assisted` unless clarified;
- PAYG/API credentials, when used, are a different account/pool from Team Credits;
- assigned seat and shared pack remain distinct capacity pools.

### Cursor

- dedicated Cursor home/account boundary;
- CLI structured output and session IDs;
- separately observed pool identities only when provider evidence distinguishes them;
- no credential sharing with xAI/Grok.

### Grok Build

- dedicated xAI account/provider home;
- ACP or structured output;
- SuperGrok weekly pool can receive usage from non-Build Grok surfaces, so unknown external consumption is represented as provider-reported remaining/unknown rather than inferred solely from Build sessions.

### Claude

- dedicated account slots as already applicable;
- current key-rotor evidence becomes an observation adapter, not a second routing authority;
- frontier reserve and leadership preference are placement policy.

---

## 12. Failure domains

| Failure | Containment | Required state transition |
|---|---|---|
| one account rate-limited | named pool/horizon only | Attempt RATE_LIMITED; sibling accounts unchanged |
| provider auth revoked | named account/slot | account AUTH_FAILED; slot OFFLINE/DRAINING |
| broker dies | one slot | adopt if identity exact, else Attempt LOST |
| tmux session disappears | one Attempt | SESSION_LOST/LOST; checkpoint if possible |
| control service restarts | all dispatch paused | reconcile/adopt from durable state; no auto-success |
| provider output malformed | one Attempt/parser | typed failure; raw text sanitized/bounded |
| telemetry stale | capacity confidence shrinks | no fabricated remaining amount; policy may defer/probe |
| workspace seal fails | one Attempt plus dispatch quarantine | do not terminalize successfully |
| inventory digest changes | affected slots | refuse new placement until reviewed registration sync |
| ChatGPT Business exhausted | executive surface only | never consumes or disables worker Codex pools |
| worker Codex pool exhausted | that dedicated account only | rotate to another worker account; Business untouched |

---

## 13. Threat model

### Threat: prompt directs agent to select another credential

**Defense:** credential/account/pool are absent from model-writable fields; deterministic placement and installed slot config select them.

### Threat: one provider home is copied to create apparent capacity

**Defense:** account/slot acceptance binds provider home identity and assigned principal; copying does not create a new licensed/account pool and is refused by provisioning policy.

### Threat: generic tmux control becomes remote shell

**Defense:** no raw tmux MCP or model tool; fixed internal adapter operations only; typed input and fixed executable argv.

### Threat: provider error text injects instructions or secrets

**Defense:** data-only structured fields, redaction before persistence, no server-side chaining from output text to a new Job/input.

### Threat: stale process writes after failover

**Defense:** lease/fence, process/session identity, whole-slot cleanup, workspace sealing, fresh workspace for next Attempt.

### Threat: account limit contaminates all accounts

**Defense:** observations are bound to trusted slot/account/pool identities and tests mutate cross-account routing.

### Threat: leader grants itself more workers/authority

**Defense:** Phase 1F bounds, child shrink-only authority/path/cost rules, deterministic cycle, same ExecutiveAuthorityPolicy.

### Threat: low-cost worker quality destroys frontier savings

**Defense:** independent review, task-class evaluation, repair/escalation bounds, routing quality evidence, stop condition when repair burn exceeds savings.

---

## 14. Deployment sequence

No “big bang” fleet install.

1. pass current Phase 1C-A exact-SHA acceptance;
2. install capacity schema/inventory support with zero new worker slots;
3. register ChatGPT Business as non-claimable and existing Codex account 01 as current slot;
4. provision Codex account 02 under a fresh principal/home;
5. pass two-slot isolation and exact-model failover canary;
6. add one GLM fixture/live slot;
7. add Qwen, Cursor, and Grok one provider at a time;
8. add tmux only for adapters that need it;
9. arm hierarchical orchestration only after provider failover is proven;
10. arm production ChatGPT control last.

Every install remains exact-SHA, root-reviewed, rollback-capable, and receipt-producing.

---

## 15. Implementation file map

Expected future surfaces; names may change only by explicit review:

```text
control_plane/
  executive_capacity.py          schemas/registries/observations
  executive_placement.py         deterministic candidate and receipts
  executive_sessions.py          common session runtime contracts
  executive_handoff.py           handoff schema and trusted assembly
  executive_worker_slots.py      installed slot inventory validation

control_plane/providers/
  base.py
  codex.py
  claude.py
  glm.py
  qwen.py
  cursor.py
  grok.py

config/
  provider_catalog.yml
  placement_policy.yml
  agent_profiles.yml             later W12

ops/executive_os/
  worker-slot plist template
  slot provisioning/retirement
  provider-home acceptance helpers
  multi-slot acceptance harness

scripts/
  executive_capacity.py
  executive_placement.py
  executive_worker_slot.py
  executive_failover_canary.py

integrations/executive_mcp/
  read-only capacity/project tools only in a separately reviewed schema wave
```

Provider-specific SDK dependencies remain outside the sealed stdlib-only control-plane import boundary unless a separately reviewed runtime split says otherwise.

---

## 16. Infrastructure acceptance summary

Phase 1G infrastructure is operational only when all of the following are proven on the real host:

- separate account → slot → principal → provider-home → pool binding;
- ChatGPT Business cannot be claimed as a worker;
- at least two dedicated Codex accounts remain quota and process isolated;
- one account’s cancellation or rate limit cannot affect another;
- deterministic placement and receipt match the actual launched slot;
- structured events and transcript deltas reach the Attempt state without secrets;
- restart adoption or LOST classification is honest for process, ACP, and tmux runtimes;
- workspace sealing prevents stale writers after failover;
- independent review gates parent completion;
- no second control plane or generic terminal authority exists.