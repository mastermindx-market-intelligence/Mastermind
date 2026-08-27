# Single-Carrier Duplicate Dispatch Guard + Logical Operation Admission

**Date:** 2026-08-26  
**Owner:** Sol / Executive architecture  
**Status:** DESIGN FREEZE CANDIDATE — no implementation or runtime authority is created by this document  
**Protected Mastermind basis:** `98f60ddcd2e387ea42c23f64b66933650c4f2e19`  
**Macro basis observed during design:** `93472e2397e1d4e931c59cf0c6c5b2b2d4b5668f`

## 0. Outcome

The Chairman routinely supervises 20–30 concurrent Mastermind projects across many Sol, Fable, Claude, Codex and Grok sessions. During the manual-transition period, the same logical wave can accidentally be pasted into two worker sessions. Fable/Opus can often discover and reconcile that collision; bounded Codex/Grok workers cannot be relied on to reconstruct enough company state to do so.

The system must make that human coordination mistake cheap and safe.

The target end-state is:

```text
one Chairman/Sol logical operation
    -> one canonical admission identity
    -> one implementation carrier per repository
    -> zero accidental second modifying workers
```

A duplicate worker may become a read-only verifier or stop with a collision receipt. It may never silently become a second modifying authority.

This design has two dependency-ordered verticals:

1. **Manual Single-Carrier Guard:** use the real Git implementation branch as a race-safe carrier claim during the current manual multi-session phase.
2. **Transport-Neutral Logical Operation Admission:** once work is admitted through Executive OS, deduplicate on one transport-neutral logical operation before any worker is selected, while preserving existing Slack/MCP transport receipt identities.

The first vertical is transitional defense-in-depth. The second is the final authority boundary.

## 1. Existing law and constraints

This design extends existing owners instead of creating a new coordination plane.

- Executive OS remains sole Job / Attempt / Worker / Event lifecycle and CEO-intent admission authority.
- Agent OS remains organizational workstream / wave / decision / discovery / handoff truth. Its `claim` field remains **advisory only** and must never become a run lock.
- GitHub remains implementation/carrier/PR/CI evidence truth.
- Slack and MCP remain transports. Their receipt identities are not themselves the logical company operation.
- One logical modifying operation binds to one carrier until canonical reconciliation.
- No new queue, task table, claim database, lock service, scheduler, retry plane or lifecycle store is permitted.
- A branch claim is concurrency evidence, **not authority**. It cannot grant permissions, merge rights, deployment rights, or Chairman intent.

Current source-law facts this design preserves:

1. `docs/sol_skills/COMMISSION_WAVE.md` already requires a collision fence before dispatch and a stable operation key.
2. `docs/sol_skills/RECONCILE_STATE.md` already defines same-key duplicate vs changed-payload conflict semantics.
3. Agent OS workstreams already have stable `WS:<KEY>` identity, inline wave ids, `owns_paths`, and advisory `claim` metadata.
4. Macro session worktrees already use shared Git worktree/branch infrastructure, and the sparse-worktree mint can refuse existing branches under strict ownership modes.
5. Executive CEO intent already relies on the existing Executive SQLite/Event plane for atomic idempotency; no dedupe table is needed.
6. Current `control_plane/ceo_request.py` deliberately derives different Slack and MCP intent ids from the same `operation_key`; cross-transport dedupe is explicitly not inferred today.

## 2. Approaches considered

### A. Documentation-only collision check

Require workers to search open PRs and handoffs before coding.

**Rejected as insufficient.** This is effectively the present Fable behavior. It depends on model judgment and context reconstruction, which is the exact failure mode this design is meant to remove for cheaper workers.

### B. Agent OS claim as a hard lease

Use `WS.claim` / wave state as a lock and make hooks refuse work when another claim exists.

**Rejected by architecture.** Agent OS explicitly does not decide whether something may run. Turning its advisory state into a hard gate creates a second control plane and violates its I1 invariant.

### C. Real Git carrier now; Executive admission later

Use one deterministic remote implementation branch as the manual-phase atomic claim. Later make Executive OS own transport-neutral operation admission before worker dispatch.

**Accepted.** This reuses GitHub for the thing GitHub already owns—implementation/carrier truth—and Executive OS for the thing Executive OS already owns—runtime admission and lifecycle.

## 3. Identity law

The lock is useful only if two independent Sol sessions derive the **same identity** for the same organizational wave. Free-form operation-key naming is therefore not sufficient for Agent-OS-backed work.

### 3.1 Organizational work identity

For substantial Agent-OS-backed modifying work, Sol must commission against one exact organizational unit:

```text
WORK_ID = WS:<WORKSTREAM>#<WAVE_ID>
```

Examples:

```text
WS:ALPHA-INTELLIGENCE-INTEGRATION#K3E-SRC-A1P
WS:CHAIRMAN-CONTROL-ROOM#A2
WS:EXECUTIVE-CAPACITY-FABRIC#CF2-F
```

`WORK_ID` is a deterministic composition of two existing Agent OS concepts. It is not a new persisted entity or store.

A modifying wave normally maps to one independently useful PR/carrier. If a wave genuinely needs parallel modifying children, Sol first gives those children distinct durable wave ids. Workers may not invent sibling operation identities to obtain parallelism.

### 3.2 Deterministic manual operation key

For Agent-OS-backed modifying work, the operation key is **derived**, not creatively authored:

```text
operation_key =
  "ws-" + first_32_hex(
    sha256(
      b"mastermind.agentos.work_identity.v1\x00" + WORK_ID_utf8
    )
  )
```

This produces a legal current CEO-request operation key (`ws-` + 32 lowercase hex characters) without lossy slug normalization.

Properties:

- two Sol sessions given the same workstream + wave derive the same key;
- worker/provider/session identity is absent;
- timestamps/random nonces are absent;
- retries and reconciliation reuse the key;
- changed work uses a different durable wave identity and therefore a different key;
- the worker preflight recomputes this key from `WORK_ID` and refuses a handoff whose supplied `OPERATION_KEY` disagrees.

The human-readable identity remains `WORK_ID`; the hash exists only because the current operation-key wire vocabulary is narrower than all legal Agent OS identifiers.

Substantial modifying work with no stable workstream/wave is **outside the hard semantic-dedupe guarantee of Manual V0**. It continues to use current collision archaeology until it is assigned a durable work identity or admitted through Executive OS. This design does not invent an ad-hoc task registry to cover that gap.

### 3.3 Carrier branch

Macro keeps its existing historical fleet branch namespace. A commissioned modifying operation uses:

```text
CARRIER_BRANCH = claude/op-<operation-key>
```

The `claude/` prefix is the current repository fleet branch convention, not provider identity. Codex and Grok must not create provider-specific sibling branches for the same logical operation.

One operation touching more than one repository receives the same `WORK_ID` / operation key but one carrier branch in each repository. Manual V0 does not claim to atomically acquire multiple repositories; architecture-sensitive multi-repo modification remains Fable/Sol-owned until Executive OS owns the logical operation lifecycle.

## 4. Manual Single-Carrier Guard

### 4.1 New bounded command

Macro adds one script:

```text
scripts/commission_preflight.py
```

Primary interface:

```text
python3 scripts/commission_preflight.py claim \
  --workstream WS:<KEY> \
  --wave <id> \
  --operation-key <derived-key> \
  --base <full-origin-main-sha>

python3 scripts/commission_preflight.py status \
  --workstream WS:<KEY> --wave <id>

python3 scripts/commission_preflight.py review \
  --workstream WS:<KEY> --wave <id>
```

`claim` recomputes `WORK_ID`, operation key and carrier branch and refuses any supplied mismatch.

The command has no database and writes no canonical state except the real Git carrier branch it is claiming.

### 4.2 Claim protocol

A claim is race-safe across separate worktrees and separate clones because the contested object is the **remote Git branch**, not a local marker.

Preconditions:

1. repository identity matches the expected Mastermind-X repository;
2. working tree is clean;
3. requested base is a full exact SHA and exists locally after fetch;
4. base is the frozen commission pickup base required by the handoff;
5. workstream/wave identity and operation key satisfy the deterministic identity law;
6. current branch is not already carrying unrelated dirty/unpushed work.

Claim algorithm:

1. Recompute `WORK_ID`, operation key and `claude/op-<operation-key>`.
2. If the current worktree is already on that carrier and the recorded claim commit is an ancestor, return `CLAIMED_SELF`.
3. Check durable GitHub history for a prior PR with that head branch. A completed carrier returns `ALREADY_FINISHED`; do not recreate the operation key.
4. Build a **no-tree-change claim commit** with `git commit-tree`, parented to the exact base SHA. The commit message carries only bounded provenance: claim schema marker, `WORK_ID`, operation key, base SHA, and non-authoritative worker/session label when available. It carries no secrets, prompt text, credentials or user data.
5. Attempt exactly one create-only remote ref update using an absent-ref lease, conceptually:

   ```text
   git push origin \
     --force-with-lease=refs/heads/<carrier>: \
     <claim-commit>:refs/heads/<carrier>
   ```

   The empty expected value means the lease is valid only if the remote carrier does not already exist. Two simultaneous claimers cannot both win.
6. On success, fetch and switch the current worktree onto the carrier branch, preserving the claim commit.
7. On rejected lease / existing remote ref, perform **no retry under a new branch or key**. Fetch the existing carrier and classify it.

The implementation tests the exact Git version/lease behavior against a local bare remote before relying on this command form. If Git's absent-ref lease behavior is not discriminating on the supported host version, the implementation must use an equivalent single atomic create-only Git-ref operation; it may not weaken the race guarantee.

The claim commit is implementation-carrier provenance only. With normal squash merge it does not enter default-branch history.

### 4.3 Collision classification

The script returns stable machine-readable states and a human-readable explanation:

| State | Meaning | Modifying behavior |
|---|---|---|
| `CLAIMED` | this session atomically created the carrier | may proceed |
| `CLAIMED_SELF` | current worktree already owns the same carrier | may resume |
| `DUPLICATE_ACTIVE` | carrier exists and is visibly active in a live worktree/open PR | zero modification |
| `RECONCILE_REQUIRED` | carrier exists but ownership/completion is ambiguous or stale | zero modification |
| `ALREADY_FINISHED` | historical PR proves the operation carrier completed | zero modification |
| `CONFLICT` | same work identity is paired with incompatible frozen commission metadata | zero modification |
| `BASE_STALE` | exact commissioned base is no longer acceptable under source law | zero modification |
| `UNAVAILABLE` | Git/GitHub state cannot be read well enough to establish ownership | fail closed for modifying work |

A duplicate worker may run `review` mode against the existing branch/PR, but `review` never changes the branch, creates a PR, pushes a ref, or mutates Agent OS.

### 4.4 No automatic takeover

A stale-looking carrier is not automatically reusable.

`RECONCILE_REQUIRED` means:

- inspect the existing branch/PR/worktree/return;
- decide whether the first worker is active, crashed, completed, or abandoned;
- preserve any work already present;
- only Sol/Fable or a bounded explicit recovery procedure may transfer the carrier;
- transfer keeps the same work identity, operation key and carrier branch.

No worker may resolve ambiguity by deleting the remote branch and trying again.

### 4.5 Resume law

A same-worktree resume on the canonical carrier may return `CLAIMED_SELF`.

A different/new worktree finding an existing carrier is **not** assumed to be the same worker merely because a session label looks familiar. It returns `DUPLICATE_ACTIVE` or `RECONCILE_REQUIRED` until carrier ownership is reconciled. Session labels are provenance, not authority.

## 5. Worker-facing wiring

### 5.1 Handoff contract

Every Agent-OS-backed modifying operator handoff gains a compact machine-readable preamble before the prose mission:

```text
WORK_ID: WS:<KEY>#<WAVE>
OPERATION_KEY: ws-<32hex>
REPOSITORY: <owner/repo>
BASE_SHA: <40-hex>
CARRIER_BRANCH: claude/op-ws-<32hex>
MODE: modifying
```

The rest of the current complete operator handoff remains unchanged.

For independent review:

```text
MODE: review_only
```

A review-only worker does not claim the carrier.

### 5.2 Sol procedure

The protected Sol `COMMISSION_WAVE.md` procedure is amended in its own bounded Mastermind procedure wave to require:

1. exact Agent OS workstream + wave identity for substantial modifying manual commissions;
2. deterministic operation-key derivation from that identity;
3. the preamble above;
4. a final collision re-check before handing the packet to a worker;
5. no random new operation key or sibling branch after a collision;
6. `RECONCILE_STATE.md` on an existing/ambiguous carrier.

`RECONCILE_STATE.md` receives only the corresponding derived-identity clarification needed to make duplicate/manual-carrier reconciliation deterministic. The Skillpack remains procedure, not live state.

### 5.3 Shared repository law

Macro updates both `CLAUDE.md` and `AGENTS.md` because account-local instructions are not shared across worker families.

New law:

> When a Sol/Chairman commission contains `MODE: modifying` plus `WORK_ID` / `OPERATION_KEY`, run `scripts/commission_preflight.py claim ...` before the first project edit. `DUPLICATE_ACTIVE`, `RECONCILE_REQUIRED`, `ALREADY_FINISHED`, `CONFLICT`, `BASE_STALE`, or `UNAVAILABLE` are stop states. Never mint another branch/key to bypass them.

A worker may not replace a supplied operation key with a session-specific key. The preflight recomputes the key and fails mismatches.

### 5.4 Claude/Fable

Claude already has tracked `SessionStart` and `PreToolUse` hook infrastructure.

Manual V0 uses two controls:

- SessionStart/routing context prints the single-carrier law prominently for modifying commissions.
- Once a worktree is on a canonical carrier, any supported write/ship guard verifies it remains on that carrier; branch switching is not a bypass.

The design does **not** claim the current hook API can always infer a commission from an arbitrary pasted prompt before the worker runs preflight. The first-line worker law remains required during the manual phase.

Fable may investigate/reconcile a collision, but it may not silently adjudicate changed work into the existing carrier.

### 5.5 Grok

Grok already has a tracked SessionStart hook path. The same single-carrier law is injected there, and any reliable current pre-tool write gate may enforce carrier continuity after claim.

The design does not depend on Grok reasoning over open PR prose. Its required first modifying command is deterministic preflight.

### 5.6 Codex

Current checked-in Macro Codex lifecycle wiring guarantees setup/SessionStart sparse-worktree setup, but this design does **not** claim a current repository-controlled pre-edit hook equivalent to Claude's.

Therefore V0 Codex enforcement is explicitly limited:

1. `AGENTS.md` requires preflight as the first modifying step.
2. the canonical branch/PR/return packet makes a skipped claim detectable before acceptance/merge.
3. a second properly behaving Codex session cannot acquire the same carrier even if it runs from another clone.

This strongly reduces duplicate work and prevents duplicate canonical delivery, but it is not described as perfect pre-edit prevention for a manually launched Codex session that ignores repository law.

When Codex is launched by Executive/Symphony-style orchestration, logical-operation admission happens **before Codex starts**, eliminating this V0 limitation.

## 6. Agent OS relationship

Agent OS remains advisory.

After a carrier claim succeeds, the owning session may update the existing workstream `claim` projection where that is already part of normal organizational maintenance:

```yaml
claim:
  by: claude/op-<operation-key>
  at: <timestamp>
  expires: <bounded timestamp>
```

This is visibility and recovery context only.

The preflight script must not require Agent OS claim state to grant permission. A stale/missing Agent OS claim cannot override an existing Git carrier, and a fresh Agent OS claim cannot manufacture a Git carrier.

Agent OS `owns_paths` and generated collision views may be consulted as **secondary advisory collision evidence** for differently identified work. They do not become file locks.

## 7. Executive OS transport-neutral logical operation admission

The manual branch guard stops being primary authority once Executive OS launches modifying workers. The final authority is an Executive admission identity above transport-specific receipts.

### 7.1 Logical operation id

The shared high-level CEO-request law derives a new internal, transport-neutral id from the already-normalized `operation_key`:

```text
logical_operation_id =
  "op-" + first_32_hex(
    sha256(
      b"mastermind.executive.logical_operation.v1\x00" + operation_key_utf8
    )
  )
```

Properties:

- pure deterministic derivation;
- not caller-authored;
- same for Slack, MCP, Control Room and future admitted transports;
- does not replace `mcp-...` / `slack-...` transport intent ids;
- provider/model/session identity is absent.

### 7.2 Preserve transport receipt identity

Existing MCP and Slack intent-id derivations remain byte-compatible as transport/reconciliation receipts.

Conceptually:

```text
operation_key
   -> logical_operation_id       # Executive company-operation identity
   -> mcp_intent_id              # MCP transport receipt identity
   -> slack_intent_id            # Slack transport receipt identity
```

This separates "which transport submission was this?" from "which company operation is this?"

### 7.3 Extend the existing Job/Event plane, not a new store

Cross-transport uniqueness must be enforced inside the existing Executive runtime transaction boundary.

Preferred implementation shape for the later Executive wave:

- extend the existing Job/runtime schema with a nullable `logical_operation_id` for high-level CEO operations;
- enforce a unique partial index for non-null logical operation ids;
- persist a transport-neutral normalized-request fingerprint in the existing canonical Job/Event provenance path;
- legacy non-CEO Jobs and explicitly preserved compatibility paths may keep null until migrated by reviewed source law.

An equivalent same-transaction Event-plane implementation is acceptable if it proves the same atomic uniqueness and compatibility. A new dedupe table, operation registry service, queue or lock database is not.

### 7.4 Admission semantics

For high-level CEO requests:

```text
same logical_operation_id + same normalized request fingerprint
    -> duplicate/reconciliation
    -> return the same canonical Job
    -> zero second Job

same logical_operation_id + different normalized request fingerprint
    -> typed conflict
    -> zero second Job

new logical_operation_id
    -> normal policy/grounding/admission
    -> exactly one canonical Job
```

The fingerprint is computed from the normalized high-level business request **before transport-specific intent-id insertion**, so Slack and MCP compare the same business object.

Transport retries remain transport-specific receipts but converge on the same logical Job.

### 7.5 Compatibility boundary

Current raw/frozen transport intent semantics are not silently rewritten.

Before Executive implementation, a dedicated source-law amendment must classify:

- existing accepted CEO intents created before logical-operation admission;
- high-level MCP request wrapper behavior;
- high-level Slack/CeoIngress behavior;
- any raw `submit-ceo-intent` operator/internal compatibility path;
- the exact Job schema migration and rollback behavior.

The final product promise applies to the reviewed **high-level CEO request ingress** used for autonomous dispatch. A legacy raw intent API that lacks `operation_key` cannot be falsely described as globally deduplicated; it must remain privileged/internal, be routed through the logical seam, or be explicitly deprecated by reviewed compatibility law.

## 8. Worker dispatch after Executive admission

Once a logical operation is accepted:

1. Executive OS owns whether it is queued/claimed/running/terminal.
2. COO decomposition creates explicit child Jobs/operation identities according to the existing Job/Attempt/Worker lifecycle.
3. Worker branch derivation uses the admitted operation/child identity; workers no longer choose collision-avoiding branch names.
4. Git carrier claim becomes defense-in-depth and implementation evidence, not the primary admission decision.
5. A duplicate Chairman/Sol transport submission is reconciled before a second worker is selected.

This is the point at which the Chairman no longer has to remember which chat owns the work.

## 9. Failure and correction behavior

### Manual phase

- GitHub/remote unavailable during claim: `UNAVAILABLE`, no modification.
- Remote carrier already exists: never auto-create a sibling branch.
- Existing branch active: `DUPLICATE_ACTIVE`.
- Existing branch stale/unknown: `RECONCILE_REQUIRED`.
- Existing completed PR for operation branch: `ALREADY_FINISHED`.
- Same `WORK_ID` with mismatching supplied operation key: `CONFLICT` before any remote mutation.
- Commission base is not the exact frozen pickup base: `BASE_STALE`/reconciliation; do not silently rebase.
- Claim succeeded remotely but local switch failed: the remote claim is an effect-known mutation; report/reconcile it and never retry under another key.
- Worker crashes after claim: carrier remains recovery evidence. It is not silently converted into a free identity.

### Executive phase

- two concurrent transports submit same operation/payload: one Job + duplicate reconciliation;
- same operation key, changed payload: conflict/refusal;
- client times out after submission: query logical-operation status, no cross-carrier retry;
- stale grounding/authority failure: normal refusal; duplicate prevention cannot widen authority;
- worker/provider failure after admission: existing Job/Attempt retry/reconciliation law owns it; logical-operation dedupe does not become a retry engine.

## 10. Security and authority boundaries

A valid carrier claim proves only:

> this implementation identity was claimed first under the Git protocol.

It does not prove:

- Chairman intent;
- current source-law compatibility;
- Executive authority grant;
- merge permission;
- deploy permission;
- production acceptance;
- that the worker is still alive.

Claim provenance is untrusted informational metadata. No claim commit may contain secrets, account identity, cookies, tokens, raw prompts or private transport identifiers.

## 11. Tests and discriminating proof

### Wave A — Manual Single-Carrier Guard

Required tests use local temporary Git repositories/bare remotes; no live GitHub mutation is required for the unit suite.

1. deterministic `WORK_ID` -> operation-key vectors are pinned;
2. supplied operation-key mismatch is refused before Git mutation;
3. first claimant on absent remote ref succeeds;
4. two concurrent claim processes against the same bare remote: exactly one succeeds;
5. losing claimant creates zero alternative branch and does not modify its worktree;
6. same current worktree on claimed branch returns `CLAIMED_SELF`;
7. remote branch exists but ownership is not established -> `RECONCILE_REQUIRED`, not takeover;
8. completed historical carrier evidence -> `ALREADY_FINISHED`;
9. incompatible frozen claim metadata for the same work identity -> `CONFLICT`;
10. dirty worktree refuses before remote mutation;
11. wrong exact base refuses;
12. failed local checkout after successful remote create reports the committed remote claim and never retries under another key;
13. review mode performs zero writes/pushes;
14. no Agent OS state is consulted as a permission gate;
15. `CLAUDE.md` and `AGENTS.md` carry parity wording for the commission law;
16. current sparse-worktree/GC/branch behavior remains green;
17. real harmless canary: launch two disposable worker worktrees with the same work identity and prove only one can claim the remote carrier while the loser returns a collision receipt before project modification.

The canary cleanup is an explicit bounded cleanup step; failure/timeout does not imply permission to delete an ambiguous carrier.

### Wave B — Executive Logical Operation Admission

1. high-level MCP A + same normalized MCP A -> same Job;
2. high-level Slack A + same normalized Slack A -> same Job;
3. MCP A then Slack A concurrently -> exactly one Job;
4. Slack A then MCP A concurrently -> exactly one Job;
5. same operation key + changed objective -> typed conflict, zero second Job;
6. same operation key + changed write paths/profile/validation -> typed conflict;
7. different operation keys with identical payload -> two intentional operations;
8. pre-migration Job without logical id remains readable and migration-safe;
9. transport-specific MCP/Slack intent-id regression vectors remain byte-identical;
10. raw compatibility ingress behavior is explicitly pinned and cannot silently bypass the claimed product guarantee;
11. no new SQLite table/store/queue is introduced;
12. duplicate submissions never cause second worker selection/dispatch merely because the transport differs;
13. ambiguous client outcome reconciles by logical operation id without retrying through another transport;
14. production canary submits the same harmless operation through two approved ingress surfaces and proves one canonical Job.

## 12. Rollout sequence

### A1 — Design acceptance

This document only. No hook, branch policy or runtime authority becomes live from accepting the architecture.

### A2 — Sol procedure amendment

One bounded Mastermind procedure PR updates the protected Skillpack:

- `docs/sol_skills/COMMISSION_WAVE.md`;
- the minimum matching clarification in `docs/sol_skills/RECONCILE_STATE.md`;
- any existing Skillpack regression/compatibility test needed to prove bootstrap/version compatibility is unchanged.

Capability: independent Sol sessions commission the same Agent OS wave with the same deterministic operation identity.

### A3 — Macro manual carrier implementation

One bounded Macro PR:

- `scripts/commission_preflight.py`;
- focused tests;
- minimal `CLAUDE.md` + `AGENTS.md` parity update;
- only the smallest hook/context integration currently supported and provable without disrupting existing active sessions.

Non-goals: Executive runtime, Agent OS schema, Linear, Slack, provider routing, worker lifecycle, automatic dispatch.

### A4 — manual fleet proof

Prove one same-operation collision across two disposable sessions/worktrees. Record limitations by harness honestly, especially Codex pre-edit enforcement.

Only the surfaces actually exercised may be called `PROVEN_LIVE`.

### B1 — Executive source-law amendment

Before runtime changes, freeze compatibility for transport-specific intent ids, Job schema migration, logical-operation fingerprinting and raw intent ingress.

This is mandatory because the current accepted CEO-request law explicitly says cross-transport dedupe is not inferred.

### B2 — Executive implementation

One bounded Mastermind implementation PR extending the existing high-level CEO-request + Job/Event admission seam with transport-neutral logical-operation uniqueness. No new control plane.

### B3 — production cross-transport proof

After the relevant ingress surfaces themselves are production-proven, submit the same harmless high-level operation through two approved transports and prove one canonical Job before worker selection.

### Retirement

After Executive logical admission + worker launch is `PROVEN_LIVE`, manual Git claim remains defense-in-depth carrier integrity. It is no longer the authority deciding whether a worker may start.

## 13. Explicit non-goals

- no new task/operation database;
- no Agent OS hard lock;
- no file-level lease system;
- no LLM semantic dedupe of arbitrary prose;
- no global ban on parallel work in one workstream;
- no automatic carrier stealing after timeout;
- no cross-carrier failover;
- no provider/model-specific operation identity;
- no rewriting old merged branches/PRs;
- no claim that Git carrier identity is execution/liveness truth;
- no broad infrastructure program: every implementation wave is independently bounded.

## 14. Acceptance / stop conditions

### Manual guard complete

The manual transition capability is complete only when a real two-session collision can be induced deliberately and the second correctly-behaving modifying session is prevented from acquiring another implementation carrier, with no new control plane and with the first carrier still usable through the normal PR flow.

Manual V0 does not claim to stop a manually launched worker that deliberately ignores repository law before running preflight. The final Executive design removes that dependency by performing admission before worker launch.

### Executive logical admission complete

The final duplicate-dispatch capability is complete only when two concurrent high-level submissions of the same logical operation through different approved transports deterministically resolve to one canonical Executive Job **before worker selection**, while a changed payload conflicts and existing transport receipt identities remain compatible.

At neither milestone does this program claim broader Autonomy V1 completion.

## 15. Exact continuation after design approval

1. Invoke the implementation-planning procedure for **A2 + A3 only**, preserving them as separate bounded PRs.
2. Implement/merge the Sol procedure amendment first so future handoffs generate deterministic identity.
3. Commission one Macro carrier for A3 using that new procedure.
4. Sol adversarially reviews A3 and requires the two-session canary before acceptance.
5. Record the production/manual limitation and collision behavior in the appropriate Agent OS discovery/handoff.
6. Keep B1/B2 held until the then-current Executive ingress/source law is re-pinned and explicitly reviewed.
