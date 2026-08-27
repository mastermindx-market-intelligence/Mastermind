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

1. **Manual Single-Carrier Guard (Macro first):** use the real Git implementation branch as a race-safe carrier claim during the current manual multi-session phase.
2. **Transport-Neutral Logical Operation Admission (Executive OS):** once work is admitted through Executive OS, deduplicate on one transport-neutral logical operation before any worker is selected, while preserving existing Slack/MCP transport receipt identities.

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
4. Macro session worktrees share Git worktree/branch infrastructure, and the current sparse-worktree mint already refuses an existing branch under strict ownership modes.
5. Executive CEO intent already relies on the existing Executive SQLite/event plane for atomic idempotency; no dedupe table is needed.
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

### 3.1 Organizational work identity

For substantial Agent-OS-backed modifying work, Sol must commission against an exact organizational unit:

```text
WORK_ID = WS:<WORKSTREAM>#<WAVE_ID>
```

Examples:

```text
WS:ALPHA-INTELLIGENCE-INTEGRATION#K3E-SRC-A1P
WS:CHAIRMAN-CONTROL-ROOM#A2
WS:EXECUTIVE-CAPACITY-FABRIC#CF2-F
```

The workstream and wave remain Agent OS concepts. This composition does not create a new persisted entity.

A modifying wave should normally map to one independently useful PR/carrier. If a wave is genuinely decomposable into parallel modifying children, Sol must split it into explicit child wave identities or explicit child operation keys before dispatch. Workers may not invent sibling carriers by themselves.

### 3.2 Operation key

Every modifying Sol handoff must carry one existing CEO-request concept:

```text
OPERATION_KEY: <lowercase stable slug>
```

Rules:

- stable for the lifetime of one logical operation;
- never contains a worker/session/provider name;
- never contains a random nonce or timestamp merely to avoid a collision;
- retries/reconciliation reuse it;
- changed work receives a new key;
- for Agent-OS-backed work, Sol derives it deterministically from the stable work identity rather than from prose wording.

Recommended form:

```text
ws-<workstream-key-lower>-<wave-id-lower>
```

If a wave id contains unsupported characters, Sol uses the existing CEO-request operation-key normalization vocabulary; it does not invent a second identity algorithm in a worker hook.

For genuinely ad-hoc maintenance with no Agent OS workstream, Sol may author an explicit operation key, but the handoff must also name the repository and exact write surface. Such work receives weaker semantic duplicate detection until Executive admission owns it.

### 3.3 Carrier branch

Macro keeps its existing historical fleet branch namespace. A commissioned modifying operation uses:

```text
CARRIER_BRANCH = claude/op-<operation-key>
```

The `claude/` prefix is a repository fleet convention, not provider identity; Codex and Grok must not replace it with provider-specific branches for the same operation.

One operation touching more than one repository receives the same operation key but one carrier branch in each repository. Manual V0 does not claim to atomically acquire multiple repositories; architecture-sensitive multi-repo work remains Fable/Sol-owned until Executive OS owns the operation lifecycle.

## 4. Manual Single-Carrier Guard

### 4.1 New bounded command

Macro adds one script:

```text
scripts/commission_preflight.py
```

Primary interface:

```text
python3 scripts/commission_preflight.py claim \
  --operation-key <key> \
  --workstream WS:<KEY> \
  --wave <id> \
  --base <full-origin-main-sha>

python3 scripts/commission_preflight.py status --operation-key <key>
python3 scripts/commission_preflight.py review --operation-key <key>
```

The command has no database and writes no canonical state except the real Git carrier branch it is claiming.

### 4.2 Claim protocol

A claim is race-safe across separate worktrees and separate clones because the contested object is the **remote Git branch**, not a local marker.

Preconditions:

1. repository identity matches the expected Mastermind-X repository;
2. working tree is clean;
3. requested base is a full exact SHA and exists locally after fetch;
4. base is the current/frozen commission pickup base required by the handoff;
5. operation key passes the existing handoff/CEO-request shape law;
6. current branch is not already carrying unrelated dirty/unpushed work.

Claim algorithm:

1. Derive `claude/op-<operation-key>`.
2. If the current worktree is already on that carrier and its claim commit is an ancestor, return `CLAIMED_SELF`.
3. Check durable GitHub history for a prior PR with that head branch. A merged/closed completed carrier means `ALREADY_FINISHED_OR_RECONCILE`; do not recreate the key.
4. Build a **no-tree-change claim commit** with `git commit-tree`, parented to the exact base SHA. The commit message carries bounded provenance only: schema marker, operation key, work id, base SHA, and non-authoritative worker/session label when available. No secrets, prompt text, credentials or user data.
5. Attempt one create-only remote push using an absent-ref lease, conceptually:

   ```text
   git push origin \
     --force-with-lease=refs/heads/<carrier>: \
     <claim-commit>:refs/heads/<carrier>
   ```

   The empty expected value means the lease is valid only if the remote carrier does not exist. Two simultaneous claimers cannot both win.
6. On success, fetch and switch the current worktree onto the carrier branch, preserving the exact claim commit.
7. On rejected lease / existing remote ref, perform **no retry under a new branch or key**. Fetch the existing carrier and classify it.

The claim commit is implementation-carrier provenance only. With normal squash merge it does not enter default-branch history.

### 4.3 Collision classification

The script returns stable machine-readable states and a human-readable explanation:

| State | Meaning | Modifying behavior |
|---|---|---|
| `CLAIMED` | this session atomically created the carrier | may proceed |
| `CLAIMED_SELF` | current worktree already owns the same carrier | may resume |
| `DUPLICATE_ACTIVE` | carrier exists and is visibly active in a live worktree/open PR | zero modification |
| `RECONCILE_REQUIRED` | carrier exists but ownership/completion is ambiguous or stale | zero modification |
| `ALREADY_FINISHED` | historical PR proves operation carrier completed | zero modification |
| `CONFLICT` | same identity is associated with incompatible frozen commission metadata | zero modification |
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
- transfer keeps the same operation key and same carrier branch.

No worker may resolve ambiguity by deleting the remote branch and trying again.

## 5. Worker-facing wiring

### 5.1 Handoff contract

Every modifying operator handoff gains a compact machine-readable preamble before the prose mission:

```text
WORK_ID: WS:<KEY>#<WAVE>
OPERATION_KEY: <key>
REPOSITORY: <owner/repo>
BASE_SHA: <40-hex>
CARRIER_BRANCH: claude/op-<key>
MODE: modifying
```

The rest of the current full operator handoff remains unchanged.

For independent review:

```text
MODE: review_only
```

A review-only worker must not claim the carrier.

### 5.2 Shared repository law

Macro updates both `CLAUDE.md` and `AGENTS.md` because account-local instructions are not shared across worker families.

New law:

> When a Sol/Chairman commission contains `MODE: modifying` and an `OPERATION_KEY`, run `scripts/commission_preflight.py claim ...` before the first project edit. `DUPLICATE_ACTIVE`, `RECONCILE_REQUIRED`, `ALREADY_FINISHED`, `CONFLICT`, `BASE_STALE`, or `UNAVAILABLE` are stop states. Never mint another branch/key to bypass them.

A worker receiving substantial modifying work without a required operation identity must not invent a random collision-avoiding key. It returns for identity recovery or, where the handoff already names an exact Agent OS workstream/wave, mechanically uses the specified identity law.

### 5.3 Claude/Fable

Claude already has tracked `SessionStart` and `PreToolUse` hook infrastructure. The implementation may add a small context/guard hook that recognizes the carrier branch and makes the rule explicit before edit-capable actions.

The guard must not globally block unrelated legacy sessions during rollout. It only hard-enforces when a commission descriptor/recognized modifying commission is present, or when a session is already on a canonical carrier branch. The exact activation mechanism must be testable and repository-local; no hidden user-home database is permitted.

Fable remains allowed to investigate/reconcile a collision, but it is not allowed to silently adjudicate a changed operation into the first carrier.

### 5.4 Grok

Grok already has a tracked SessionStart hook path. The carrier preflight law is injected into Grok startup/instructions and, if the current harness exposes a reliable pre-tool write gate, the same bounded guard is added there.

The design does not depend on Grok reasoning over open PR prose. The deterministic preflight result is the authority for whether this manual session may modify.

### 5.5 Codex

Current checked-in Macro Codex lifecycle wiring guarantees environment setup/SessionStart sparse-worktree setup, but this design does **not** claim a current repository-controlled pre-edit hook equivalent to Claude's.

Therefore V0 Codex enforcement is explicitly two-layered:

1. `AGENTS.md` requires commission preflight as the first modifying step.
2. shipping/PR guards refuse a Sol-commissioned modifying carrier that does not use the canonical operation branch / identity once that commission context is observable.

This prevents duplicate delivery and strongly reduces duplicate work, but it is not described as perfect pre-edit enforcement for manually launched Codex sessions.

When Codex is launched by Executive/Symphony-style orchestration, the orchestrator's before-run boundary must perform logical-operation admission **before Codex starts**, eliminating this V0 limitation.

## 6. Agent OS relationship

Agent OS remains advisory.

After a carrier claim succeeds, the owning session may update the existing workstream `claim` projection where that is already part of normal handoff/organizational maintenance:

```yaml
claim:
  by: claude/op-<operation-key>
  at: <timestamp>
  expires: <bounded timestamp>
```

This is visibility and recovery context only.

The preflight script must not require Agent OS claim state to grant permission. A stale or missing Agent OS claim cannot override an existing Git carrier, and a fresh Agent OS claim cannot manufacture a Git carrier.

Agent OS `owns_paths` and generated collision views may be consulted as **secondary advisory collision evidence** for differently named operations. They do not become file locks.

## 7. Executive OS transport-neutral logical operation admission

The manual branch guard is retired from primary authority once Executive OS launches modifying workers. The final authority is an Executive admission identity above transport-specific receipts.

### 7.1 Logical operation id

The shared high-level CEO-request law derives a new internal, transport-neutral id from `operation_key`:

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
   -> logical_operation_id       # Executive operation identity
   -> mcp_intent_id              # MCP transport receipt identity
   -> slack_intent_id            # Slack transport receipt identity
```

This deliberately separates "which message/transport attempt was this?" from "which company operation is this?"

### 7.3 Extend the existing Job/Event plane, not a new store

Cross-transport uniqueness must be enforced inside the existing Executive runtime transaction boundary.

Preferred implementation shape:

- extend the existing Job/runtime schema with a nullable, indexed `logical_operation_id` for CEO-originated high-level operations;
- enforce a unique partial index for non-null logical operation ids;
- persist a transport-neutral normalized-request fingerprint alongside canonical Executive provenance using the existing Job/Event lifecycle, not a side database;
- legacy non-CEO Jobs and frozen compatibility paths may keep null until migrated by an explicit compatibility law.

An implementation may choose an equivalent same-transaction Event-plane representation if it proves the same atomicity and compatibility, but it may not add a dedupe table, operation registry service or second queue.

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

The fingerprint is computed from the normalized high-level business request **before transport-specific intent id insertion**, so Slack and MCP normalize to the same comparison object.

Transport retries remain transport-specific receipts but converge on the same logical Job.

### 7.5 Compatibility boundary

Current raw/frozen transport intent semantics are not silently rewritten.

Implementation must explicitly classify:

- existing accepted CEO intents created before logical-operation admission;
- high-level MCP request wrapper behavior;
- high-level Slack/CeoIngress behavior;
- any raw `submit-ceo-intent` operator/internal compatibility path.

The final product promise applies to the reviewed **high-level CEO request ingress** used for autonomous dispatch. A legacy raw intent API that bypasses `operation_key` cannot be falsely described as globally deduplicated; it must remain privileged/internal, be routed through the logical seam, or be explicitly deprecated by separate compatibility ruling.

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

- GitHub unreachable during claim: `UNAVAILABLE`, no modification.
- Remote branch already exists: never auto-create a sibling branch.
- Existing branch active: `DUPLICATE_ACTIVE`.
- Existing branch stale/unknown: `RECONCILE_REQUIRED`.
- Existing completed PR for operation branch: `ALREADY_FINISHED`.
- Same workstream/wave presented with a different operation key: worker reports identity conflict; does not pick one by preference.
- Commission base moved: follow current source-law collision/re-pin procedure; do not silently rebase the carrier.
- Claim succeeded but local switch failed: remote carrier exists; classify effect as committed claim and reconcile it. Do not retry with a different branch.
- Worker crashes after claim: carrier remains as recovery evidence. It is not silently garbage-collected into a free identity.

### Executive phase

- two concurrent transports submit same operation/payload: SQLite uniqueness produces one Job and one duplicate reconciliation result;
- same operation key, changed payload: conflict/refusal;
- client times out after submission: query logical operation status; no cross-carrier retry;
- stale grounding/authority failure: request is refused normally; duplicate prevention cannot widen admission authority;
- worker/provider failure after admission: existing Job/Attempt retry/reconciliation law owns it; logical operation dedupe does not become a retry engine.

## 10. Security and authority boundaries

The guard must never be interpreted as authorization.

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

Claim provenance is untrusted informational metadata. No branch commit may contain secrets, account identity, cookies, tokens, raw prompts or private transport identifiers.

## 11. Tests and discriminating proof

### Wave A — Manual Single-Carrier Guard

Required tests use local temporary Git repositories/bare remotes; no live GitHub mutation is required for the unit suite.

1. first claimant on absent remote ref succeeds;
2. two concurrent claim processes against the same bare remote: exactly one succeeds;
3. losing claimant creates zero alternative branch and does not modify its worktree;
4. same current worktree on claimed branch returns `CLAIMED_SELF`;
5. remote branch exists but not locally active -> `RECONCILE_REQUIRED`, not takeover;
6. completed historical carrier metadata -> `ALREADY_FINISHED`;
7. changed frozen commission metadata for same identity -> `CONFLICT`;
8. dirty worktree refuses before remote mutation;
9. wrong/stale exact base refuses;
10. failed local checkout after successful remote create reports effect-known remote claim and never retries under another key;
11. review mode performs zero writes/pushes;
12. no Agent OS state is consulted as a permission gate;
13. `CLAUDE.md` and `AGENTS.md` carry parity wording for the commission law;
14. existing sparse-worktree behavior and branch/worktree GC tests remain green;
15. real manual canary: launch two harmless worker worktrees with the same canary operation key and prove only one can claim the remote carrier while the loser returns a collision receipt before project modification.

The real canary must use a disposable no-product-impact operation and delete/close only through an explicit cleanup procedure after proof.

### Wave B — Executive Logical Operation Admission

1. MCP high-level request A + same normalized MCP request -> same Job;
2. Slack high-level request A + same normalized Slack request -> same Job;
3. MCP A then Slack A concurrently -> exactly one Job;
4. Slack A then MCP A concurrently -> exactly one Job;
5. same operation key + changed objective -> typed conflict, zero second Job;
6. same operation key + changed write paths/profile/validation -> typed conflict;
7. different operation keys with identical payload -> two operations (intentional distinct work);
8. existing pre-migration Job without logical id remains readable and does not crash migration;
9. transport-specific MCP/Slack intent-id regression vectors remain byte-identical;
10. existing raw compatibility path behavior is explicitly pinned and cannot silently bypass the claimed product guarantee;
11. no new SQLite table/store/queue is introduced;
12. duplicate submissions never create a second worker dispatch/attempt merely because the transport differs;
13. ambiguous client outcome reconciles by logical operation id without retrying through another transport;
14. production canary submits the same harmless operation through two approved ingress surfaces and proves one canonical Job + two transport receipts/one duplicate result as designed.

## 12. Rollout sequence

### Wave A1 — design/source-law acceptance

This document only. No hooks, branch policy or runtime changes become live from accepting the architecture.

### Wave A2 — Macro manual carrier implementation

One bounded Macro PR:

- `scripts/commission_preflight.py`;
- focused tests;
- minimal `CLAUDE.md` + `AGENTS.md` parity update;
- only the smallest hook/ship integration that is actually supported and can be proven without disrupting existing active sessions.

Non-goals: Executive runtime, Agent OS schema, Linear, Slack, provider routing, worker lifecycle, automatic dispatch.

### Wave A3 — manual fleet proof

Prove one same-operation collision across two disposable sessions. Record limitations by harness honestly, especially Codex pre-edit enforcement.

Only after this proof may the manual guard be called `PROVEN_LIVE` for the surfaces actually exercised.

### Wave B1 — Executive source-law amendment

Before runtime changes, freeze compatibility for transport-specific intent ids, Job schema migration, logical-operation fingerprinting and raw intent ingress.

This is required because current accepted `ceo_request.py` explicitly says cross-transport dedupe is not inferred.

### Wave B2 — Executive implementation

One bounded Mastermind PR extending the existing CEO request / Job/Event admission seam with transport-neutral logical operation uniqueness. No worker dispatch changes except what is required to prove zero duplicate dispatch.

### Wave B3 — production cross-transport proof

After the relevant ingress surfaces are production-proven, submit the same harmless high-level operation through two approved transports and prove one canonical Job.

### Retirement

After Executive logical admission + worker launch is `PROVEN_LIVE`, manual Git claim remains a defense-in-depth carrier integrity check. It is no longer the authority deciding whether a worker may start.

## 13. Explicit non-goals

- no new task/operation database;
- no Agent OS hard lock;
- no file-level lease system;
- no attempt to semantically deduplicate arbitrary prose with an LLM;
- no global ban on parallel work in the same workstream;
- no automatic carrier stealing after timeout;
- no cross-carrier failover;
- no provider/model-specific operation identity;
- no rewriting old merged branches/PRs;
- no claim that Git carrier identity is execution/liveness truth;
- no broad infrastructure program: each implementation wave is independently bounded.

## 14. Acceptance / stop conditions

### Manual guard complete

The manual transition capability is complete only when a real two-session collision can be induced deliberately and the second modifying session is prevented from acquiring another implementation carrier, with no new control plane and with the first carrier still usable through the normal PR flow.

### Executive logical admission complete

The final duplicate-dispatch capability is complete only when two concurrent high-level submissions of the same logical operation through different approved transports deterministically resolve to one canonical Executive Job before worker selection, while a changed payload conflicts and all existing transport receipt identities remain compatible.

At neither milestone does this program claim broader Autonomy V1 completion.

## 15. Exact continuation after design approval

1. Create the implementation plan for **Wave A2 only**.
2. Commission one bounded Macro implementation carrier for the manual guard.
3. Sol adversarially reviews A2 and requires the two-session canary before acceptance.
4. Record the resulting limitation/behavior in the appropriate Agent OS discovery/handoff.
5. Keep Wave B held until its source-law/compatibility amendment is explicitly reviewed against the then-current Executive OS ingress architecture.
