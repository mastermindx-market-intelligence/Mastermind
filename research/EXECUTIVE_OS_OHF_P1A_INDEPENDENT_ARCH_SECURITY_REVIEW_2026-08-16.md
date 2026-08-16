# OHF-P1A-R1 — Independent architecture, lifecycle & security review

**Date:** 2026-08-16
**Commission:** OHF-P1A-R1
**PR:** [#84](https://github.com/mastermindx-market-intelligence/Mastermind/pull/84)
**Architecture SHA reviewed:** `f3c1cdb7d3b40103450cf3f845ac0648479585e7`
**This artifact does not review itself.** If it is committed, that later SHA is a review-artifact commit, not a new architecture head.
**Production / implementation / schema-migration / Phase 1F-C authority:** none.
**Author docs were not edited in this pass.**

Final verdict: **REVISE_AND_REREVIEW**

P1A's direction (Executive owns lifecycle; native harness is not a second control plane; process ≠ session; SIGKILL ≠ writer release; no auth.json copying; no cross-Attempt session reuse) is compatible with Charter P7 and Phase 1F. The **identity, fence, recovery, profile-sealing, transport, and adapter-contract** freeze is not. A P1B coder would still have to invent those rules. That fails the review success criterion.

---

## A. Review lineage

| Item | Value |
|---|---|
| PR | #84 (open draft, `MERGEABLE`, `BEHIND`) |
| Architecture SHA reviewed | `f3c1cdb7d3b40103450cf3f845ac0648479585e7` |
| P1A base | `da6bd78e078b96db8c121b16f1b10e3fd70e6fef` |
| Current master | `37c34e2e83fe101cd7328bd74b5d33f46064239d` (`#83` Gate B preflight) |
| Master drift classification | **COMPATIBLE_BUT_REQUIRES_REBASE** |
| CI `test` | SUCCESS |
| CodeQL + Analyze (actions/js/python) | SUCCESS |

Master `#83` touches `ops/executive_os/git_handoff_preflight.py` and two test files. **No overlap with #84 files.** Semantically it **hardens** workspace-root/symlink/cleanup identity for Gate B; it does not collide with OHF identity law. It does change “path string is not cleanup authority,” which **supports** P1A’s warning not to reduce workspace proof to cwd — rebase before any merge, do not treat “no overlapping files” as a semantic proof.

P0 is closed (`da6bd78`). This review does not rerun P0C.

---

## B. Source-law census

| Source | Class |
|---|---|
| `research/MASTERMIND_CHARTER_V2.md` P7/P8 | BINDING |
| `config/strategic_state.yml` `duplicate_control_planes` | BINDING |
| `config/authority_map.yml` (merged; no `seats:`) | BINDING |
| `AGENTS.md` executive contract | BINDING |
| Phase 1F orchestration contract | BINDING |
| `docs/EXECUTIVE_WORKER_ROUTING.md` | BINDING |
| `control_plane/executive_runtime.py` SCHEMA_VERSION=2 | MERGED_IMPLEMENTATION |
| `control_plane/worker_adapter.py` sealed floor | MERGED_IMPLEMENTATION |
| `control_plane/executive_supervisor.py` restart = terminate live children | MERGED_IMPLEMENTATION |
| `control_plane/codex_worker.py` stdio-owned `create_subprocess_exec` | MERGED_IMPLEMENTATION |
| `control_plane/executive_workspace.py` exact-SHA worktree | MERGED_IMPLEMENTATION |
| `control_plane/executive_backup.py` offline restore | MERGED_IMPLEMENTATION |
| P0 live acceptance memo | BINDING *as evidence*, not as OHF runtime law |
| P1A four memos + spike | DRAFT_ONLY (architecture candidate) |
| PR #66 Agent Fabric | DRAFT_ONLY |
| PR #72 G0 source law | DRAFT_ONLY |
| 1G `session_handles` mixed pid+session | SUPERSEDED by P0 (this review agrees) |

**Hidden #72 dependency:** none found. P1A correctly refuses to encode unmerged seats/decision altitude.

**Hidden #66 dependency:** `mastermind.agent_handoff.v1` is cited as a name to preserve. That is a **name reservation**, not a runtime dependency. Acceptable if P1A states the handoff *minimum fields* without requiring #66 to merge. Today those fields are listed in 1G, not frozen in P1A — **underspecified**, not a silent #66 import.

---

## C. P0 evidence integrity

| Fact | P1A use | Class |
|---|---|---|
| Graceful session resume (PID 30646→30816, same thread) | used as same-Attempt resume | SUPPORTED |
| SIGKILL active-writer refusal | used as no-steal V1 | SUPPORTED |
| Native fork ≠ Job | used | SUPPORTED |
| Minimal-surface partial reduction | used; unclassified refuse | SUPPORTED |
| Main process cleanup VERIFIED | not overclaimed as descendant cleanup | SUPPORTED |
| Transitive orphan UNKNOWN | left UNKNOWN | SUPPORTED |
| Host reboot | designed, labeled untested | UNDERUSED as law (no fail-closed restore/reboot law) |
| Controller restart | “adopt if pid+start+boot match” | **OVERCLAIMED** — contradicts merged supervisor + stdio topology |

---

## D. Definition of Attempt

An Executive Attempt is **one leased execution placement of a Job**: a single claim against one `(worker_id, quota_class)` with one authority-policy hash, one workspace binding, one lease/fence generation, and one retry slot (`attempt_number` toward `attempt_limit`).

Merged evidence (`claim_job`, `record_process`, terminal immutability trigger):

**Immutable after claim:** `attempt_id`, `job_id`, `attempt_number`, `worker_id`, `quota_class`, `authority_policy_hash`, `started_at_ms`.

**Mutable after claim:** status, checkpoint/result, heartbeat, lease rotation via `adopt_attempt`, write-once process identity, COALESCE-once `provider_session_id`.

OHF may attach native-session epochs **inside** that placement. It may **not** redefine Attempt as “one native thread.” Doing so would consume retry ceilings, repair counts, and failure metrics for conversational hygiene.

---

## E. HarnessSession cardinality

**CARDINALITY_B:** Attempt 1:N **sequential** primary HarnessSessions (at most one current; prior epochs terminal).

P1A’s CARDINALITY_A (1:1) is neat and security-motivated, and it is the wrong merge with existing Attempt accounting.

- **Case A (context rotation, identical placement):** a new native thread is a new **session epoch**, not a new Attempt. Treating it as a new Attempt burns `attempt_limit` (default 10), pollutes failure/retry/latency/quality metrics, and can exhaust Phase 1F repair budget on a still-valid placement.
- **Case B (session lost/corrupt, same placement):** new epoch inside the same Attempt after handoff of execution facts; do not increment `attempt_count`.
- **Case C** is CARDINALITY_B.

Concurrent primary sessions remain forbidden (one Executive writer). Native forks remain subordinates, not epochs and not Jobs.

**Still true:** a HarnessSession/epoch **must not cross Attempts**. New Attempt ⇒ fresh native session + provider-neutral handoff. No proof exists for safe reuse of a contaminated thread under a new authority/workspace/account.

This cardinality change is an **identity-model revision**. P1B must not implement 1:1 and hope to migrate.

---

## F. Attempt-boundary matrix

| Case | Verdict |
|---|---|
| Graceful process restart | SAME_ATTEMPT (same epoch if resume succeeds) |
| Safe crash recovery (writer proven released + resume) | SAME_ATTEMPT |
| SIGKILL blocked writer | SAME_ATTEMPT while recovering; after deadline SAME_ATTEMPT with **new epoch** *or* NEW_ATTEMPT if placement is abandoned |
| Context compaction | SAME_ATTEMPT, same epoch |
| Context rotation (intentional fresh primary thread, same placement) | SAME_ATTEMPT, **new epoch** |
| Fresh primary session after corruption | SAME_ATTEMPT, new epoch |
| Native fork | SAME_ATTEMPT, subordinate handle |
| Model change | NEW_ATTEMPT |
| Served-model mismatch | REFUSE launch; if after start, interrupt + NEW_ATTEMPT |
| Provider change | NEW_ATTEMPT |
| Account / auth-home change | NEW_ATTEMPT |
| Harness kind change | NEW_ATTEMPT |
| Harness version / binary digest change | NEW_ATTEMPT (V1 exact digest; drop the patch-compatible exception) |
| REQUIRED/FORBIDDEN skill/MCP change | NEW_ATTEMPT or REFUSE |
| Ambient unclassified appears | REFUSE write profile; read-only may continue only under explicit policy |
| Sandbox / approval / network | NEW_ATTEMPT |
| Authority / write-path / workspace / base SHA | NEW_ATTEMPT |

P1A’s “fresh thread because context became poor = NEW_ATTEMPT” is **rejected**.

---

## G. Account / auth realm

`workers.account_label` is **not sufficient**.

Merged facts: NOT unique; write-once at `register_worker`; default `"dedicated-codex-home"`; not authenticated; two workers may share it; `CODEX_HOME` is a launch/policy path, not a SQLite column; service re-register refuses label mismatch but that is config equality, not provider identity.

Required durable property: a **slot auth domain** that is unique per worker slot, bound at registration, and re-attestable without storing credentials (provider + worker_id today; later a non-secret provider account id if `account/read` ever exposes one).

Production **cannot** prove “this home still belongs to the intended ChatGPT account” from P0. P0 proved file isolation, not account identity. Mark **ACCOUNT_REALM_ATTESTATION_UNPROVEN**.

Gate: does **not** block drafting adapter types; **does** block multi-account activation and production arming. V1 fence should key on `(worker_id, native_session_id)` because `worker_id` is the unique slot PK, not `account_label`.

Credential refresh vs account switch: fail closed if provider-reported auth type/plan/non-secret account id changes; inode/mtime of `auth.json` is **not** identity (refresh can rewrite the file). UNKNOWN detection of silent account switch inside the same home → PRODUCTION_ARMING_GATE.

---

## H. Writer-fence verdict

| Question | Answer |
|---|---|
| Correct fence key | `(worker_id, native_session_id)` in V1; conceptually `(provider, auth_realm_id, native_session_id)` once a real realm exists |
| Current SQL key correct? | **NO** — `UNIQUE(native_session_id) WHERE ended_at_ms IS NULL` assumes global uniqueness of opaque ids |
| Process death frees writer? | **YES, as specified** — that unique is tied to `ended_at_ms IS NULL`. Terminalizing a generation after SIGKILL would free the fence while the provider writer may still be held (H2). |
| Provider writer release represented separately? | **NO** |
| Fresh session S2 on same account after blocked S1? | **Intended in prose, not represented.** If unique is on `native_session_id` only, S2 can insert; if S1’s row stays open forever, S1 is locked (good) and S2 is fine — unless they accidentally share ids across accounts (H1). Account-wide freeze is not in SQL; the risk is the opposite: **under-fencing**. |
| Double-writer path remains? | **YES** across accounts/providers with colliding opaque ids; **YES** if `ended_at_ms` is set while provider writer remains |

H1 and H2 are confirmed.

---

## I. Minimum writer/process state model

Four independent facts. Do not collapse them.

1. **Process liveness:** `alive | proven_dead | unknown` from pid+pgid+start+boot (and host realm later). `ended_at_ms` records *process death observation*, not fence release.
2. **Executive writer ownership:** which generation (if any) is the Executive-authorized writer for `(worker_id, native_session_id)`. Released only by graceful stop + confirmed process death, or by **abandoning that native session id** (epoch terminal; S1 never reused).
3. **Provider writer knowledge:** `HELD | RELEASED | UNKNOWN`. SIGKILL starts as UNKNOWN, may become HELD on resume refusal. Never invent RELEASED.
4. **Resume safety:** derived: Executive owns it AND (provider RELEASED or still our live process) AND process identity matches. UNKNOWN ⇒ not safe.

SQL must not use `ended_at_ms IS NULL` as the writer fence. Use an explicit `executive_writer_held` (or equivalent) that stays true after unclean death until abandon/reconcile.

---

## J. Schema verdict

Proposed migration is **not ready**. Do not implement SCHEMA_VERSION 3.

| Item | Verdict |
|---|---|
| `native_session_id` as extra Attempt column beside `provider_session_id` | **CHANGE** — one canonical name (see §K) |
| `harness_kind` / `harness_version` columns | **DERIVE** indexed projections of requested profile, or omit |
| `execution_profile_json` + digest (single blob) | **CHANGE** — split requested vs observed |
| `writer_generation_id` on Attempt | **DERIVE** from the unique held-writer generation; pointer only if the same txn updates both |
| Attempt `harness_recovery_class` | **REMOVE** — generation owns recovery |
| `native_subordinates_json` | **POSTPONE** — restart correctness does not require it; events suffice |
| `process_generations` table | **KEEP** with **CHANGE**d keys and writer-release fields |
| `host_id` | **POSTPONE** — nullable opaque later; do not freeze hostname hash |
| pid/pgid/start/boot on generations | **KEEP** as canonical process identity |
| Attempt pid/pgid/start/boot | **DERIVE** cache of current generation; same-txn projection |
| termination / resume fields | **CHANGE** — split process death vs provider writer vs resume safety |
| `runtime_metadata_json` | **POSTPONE** / receipts |

Canonical owner per duplicated concept:

| Fact | Canonical |
|---|---|
| Native primary session id | one Attempt/epoch column (renamed `provider_session_id` or migrated) |
| Current OS process | current `process_generations` row with `executive_writer_held` |
| Requested profile | `requested_execution_profile_json` sealed at claim/prepare |
| Observed attestation | `observed_harness_attestation_json` sealed before first work turn |
| Recovery class | generation only |
| Workspace | existing workspace receipt (inode+SHA), not cwd string |

---

## K. Session identity verdict

**RENAME/MIGRATE_TO_NATIVE_SESSION_ID** *or* **REUSE_PROVIDER_SESSION_ID** — pick one. This review picks **REUSE_PROVIDER_SESSION_ID** for V1: it already exists, is write-once, and already means “provider-managed session.” Document that for Codex App Server it stores the thread id. Do **not** add `native_session_id` as a synonym column (Charter P7).

CARDINALITY_B adds **session epoch**: `session_epoch INTEGER` on Attempt or a small `harness_session_epochs` table keyed by `(attempt_id, epoch_number)` with at most one current. That is the moment a table becomes justified — not a parallel `native_session_id`.

---

## L. ExecutionProfile verdict

Two concepts, staged seal:

1. **RequestedExecutionProfile** — sealed before process start (model, harness kind, sandbox, approval, network, REQUIRED/FORBIDDEN/allowlist, workspace identity, worker_id).
2. **ObservedHarnessAttestation** — sealed after initialize + capability list, **before first meaningful work turn**.

First work turn allowed only when attestation is committed and launch_decision is OK for that profile class.

Served ≠ requested: **REFUSE**; do not seal a lying profile.

TOCTOU re-attest: every new ProcessGeneration; after config reload; after workspace identity change; after harness binary change (which is NEW_ATTEMPT in V1). Not per-turn unless a reload notification fires.

H7 confirmed: one immutable blob mixing requested+observed has no legal seal point.

---

## M. Capability policy

| Class | Behavior |
|---|---|
| REQUIRED missing | REFUSE launch |
| FORBIDDEN present | REFUSE launch |
| UNCLASSIFIED on write profile | REFUSE |
| UNCLASSIFIED on read-only laboratory | may proceed if required subset present |
| ALLOWED_AMBIENT | version+binary-digest-scoped allowlist; names alone are weak |

Names should bind, where observable, to harness binary digest + schema/content digest. Same name + different power is not silently trusted (P1B_IMPLEMENTATION_GATE for digest binding; V1 may start with name+harness-digest).

**Residual Codex plugin/template surface:** **BLOCKS_ONLY_WRITE_CAPABLE_CANARY**. Does not block P1A revision work, P1B contract writing after rereview, or read-only probes. Blocks write-capable OHF canaries until an explicit 0.147.0 allowlist or a proven `features.plugins=false` experiment.

Named follow-up experiment (not this review): if `codex features list` still shows `plugins stable true`, run the existing P1A spike with `features.plugins=false` on the dedicated home, restore config, and record residual skills. Do not disable native quality blindly.

---

## N. Controller / App Server topology

**Who owns the App Server process today (OHF laboratory)?** The spawning client (`AppServerClient` / `Popen` stdio).

**Who would own it in production under current Executive patterns?** The adapter process that calls `create_subprocess_exec` (`CodexWorker` locally, or broker-side adapter remotely). Pipes live in that process’s memory. Stdin is often closed after prompt on the **sealed** path.

**Can a new controller reattach to those pipes?** **No.** There is no reattach API. Merged `ExecutiveSupervisor.reconcile_restart` **terminates live local children** because “the in-memory JSONL parser was lost,” then marks LOST. `adopt_attempt()` rotates **lease/fence only**.

P1A conflates lease adoption with process transport adoption (H4). Lawful V1 controller-restart path:

```text
A. App Server / worker child cannot be adopted.
   Identity-safe terminate if still live → absence verified
   → Attempt recovery / LOST as today’s supervisor
   → new ProcessGeneration only after writer-safe reconcile
   → likely new session epoch; never a second writer on S1
```

A future broker that owns App Server transport (outcome B) is a **different commission**. Do not specify PID adoption as if stdio were inheritable.

---

## O. Recovery matrix

| Case | Class |
|---|---|
| Graceful process replacement | VERIFIED (P0 Codex App Server) |
| SIGTERM resume | VERIFIED in P0 for graceful path; post-SIGKILL contaminated |
| SIGKILL | VERIFIED unsafe to blind-resume |
| Controller crash | DESIGNED incorrectly in P1A; merged code is terminate+LOST. Treat P1A text as **UNSAFE** until amended to match topology |
| Supervisor crash | same |
| Host reboot | DESIGNED, UNKNOWN as evidence |
| Native session missing | DESIGNED fail-closed |
| Active writer refusal | VERIFIED |
| Config drift | VERIFIED as P0 probe row; production re-attest DESIGNED |
| Workspace drift | DESIGNED; must use existing inode+SHA receipts, not cwd |

---

## P. Native helper verdict

| Question | Answer |
|---|---|
| Helpers in read-only Attempts? | Allowed if the harness ceiling is actually read-only |
| Helpers in write-capable Attempts? | **Not in V1 unless `supports_subagent_capability_ceiling` is proven** |
| Per-helper read-only enforceable? | **Not by prompt.** Parent write tools/MCP/shell inherit. |
| Harness lacks ceilings? | Disable native helpers in write-capable Attempts |
| Helper as independent review? | **No.** Different `worker_id` Job remains the minimum |

H8 confirmed. P1A “analyze / research / read-only explore” is prompt policy, not a capability boundary.

---

## Q. OperatorHarnessAdapter verdict

| Method | Class |
|---|---|
| `describe_capabilities` | COMMON_REQUIRED |
| `prepare` | **REDESIGN** — split validate vs mutate; must not start processes or touch credentials |
| `start_session` | COMMON_REQUIRED |
| `begin_turn` | COMMON_REQUIRED |
| `read_events` | COMMON_REQUIRED |
| `interrupt_turn` | COMMON_REQUIRED |
| `collect_candidate_result` | COMMON_REQUIRED — never completes the Job |
| `graceful_stop` | COMMON_REQUIRED |
| `cancel` | COMMON_REQUIRED |
| `reconcile` | **REDESIGN** — inspect/report only; supervisor decides kill/resume |
| `probe` | COMMON_OPTIONAL |
| `resume_session` | COMMON_OPTIONAL |
| `send_input` / `steer` | COMMON_OPTIONAL |
| `respond_to_approval` | COMMON_OPTIONAL |
| `fork_session` | COMMON_OPTIONAL / PROVIDER_SPECIFIC |
| `checkpoint` | COMMON_OPTIONAL |
| writer-steal, `complete_job`, browser/devserver | REMOVE |

Provider mapping: fork/resume/quota = OPTIONAL. Required methods are NATURAL for Codex App Server, Claude SDK, Grok ACP, Qwen structured, and a PTY wrapper can implement start/turn/events/stop awkwardly but not impossibly. Do not require Codex thread ids.

**Is the interface semantically typed enough for P1B?** **NO.**

Missing before P1B (not vague):

- Dataclasses: `RequestedExecutionProfile`, `ObservedHarnessAttestation`, `LaunchDecision`, `SessionRef`, `ProcessGenerationRef`, `TurnRef`, `EventCursor`, `CandidateResult`, `ReconcileReport`, `CapabilityManifest`, `AuthRealmFact`
- Per-method: preconditions, postconditions, idempotency key, timeout, cancellation, which exceptions map to the failure taxonomy
- `prepare`: explicit prohibition on subprocess, credential read, workspace mutation
- `reconcile`: returns liveness/writer/resume-safety observations; may not kill unless a separate `signal_process` bounded op exists
- Event fields: `attempt_id`, epoch, `process_generation_id`, `provider_event_id`, `turn_id`
- Cursor semantics for reconnect/duplicates

---

## R. Phase 1F compatibility

Planning Attempt → create children → **release** leader (no persistent leader) → children independent → aggregation as a **new Attempt** because it is a new work phase / parent-container law, **not** because the native thread rotated.

Handoff carries execution facts. Native planner context is lost.

**V1_QUALITY_TRADEOFF_ACCEPTED** must be written explicitly. Parking a native thread without a worker lease would be a hidden persistent leader and would either cross Attempt boundaries on resume or consume provider resources while the parent is a container. Reject for V1. Require later parity evaluation; do not pretend there is no cost.

Attempt accounting: context rotation must **not** consume `attempt_limit`. Aggregation Attempts **do** consume a Job attempt (they are real placements). If that is too expensive, raise `attempt_limit` for orchestration Jobs — do not collapse aggregation into the planning Attempt.

---

## S. Backup/restore

Merged restore is **offline**: service marker absent, flock, whole-DB swap. It does **not** reconcile live OS processes.

Required source law for any future OHF-active schema:

1. Backup while OHF RUNNING is allowed only as a crash-consistency snapshot, never as a license to resurrect writers.
2. Restore **invalidates all `executive_writer_held` generations**. They become `provider_writer=UNKNOWN`, process liveness unknown.
3. Service must not start work until reconcile: no resume of restored session ids; fresh epochs or LOST+handoff.
4. A restored DB must not authorize a second writer on an old S1.

P1A leaving this “partially UNKNOWN” is insufficient if v3 can persist active rich-harness state. **H10 confirmed.**

---

## T. Rollback semantics

| Mode | Reality |
|---|---|
| Feature disable | stop writing new columns; old rows remain |
| Old-binary rollback | **fails closed** if SCHEMA_VERSION is 3 and old code requires 2 |
| DB restore | offline; invalidates writers (see §S) |
| Forward-fix | the only safe v3 escape besides restore+rebuild |
| Migration rollback | not promised |

Do not call “stop using new columns” binary rollback.

---

## U. Multi-host compatibility

Attempt / sequential session epoch / ProcessGeneration can later grow an opaque `host_realm_id` without redefining those three objects **if** V1 does not freeze hostname-hash as identity. POSTPONE `host_id`. Current process identity (pid+start+boot) is host-local; that is enough for single-host V1.

---

## V. Threat matrix

| Threat | P/D/R | Layer |
|---|---|---|
| Two Executive processes on one thread | P/D | fence `(worker_id, session)` + provider writer |
| Session reused across Attempts | P | epoch dies with Attempt; new Attempt fresh session |
| SIGKILL writer remains | D/R | provider_writer=HELD/UNKNOWN; do not free Executive hold |
| Stale generation resumes after newer owns | P | generation_number + held-writer uniqueness |
| Resume changes model/sandbox/approval | P/D | requested profile digest |
| Wrong cwd/worktree | P | workspace receipt inode+SHA (`executive_workspace` + `#83` path rules) |
| CODEX_HOME other account | D UNKNOWN | ACCOUNT_REALM_ATTESTATION_UNPROVEN |
| Ambient app/skill after update | D/P | observed attestation vs allowlist |
| Project SKILL.md / plugin / MCP injection | P | REQUIRED/FORBIDDEN + unclassified fail-closed |
| Malicious MCP result | P | allowlist + treat output untrusted |
| Credential in events | P | redaction; never persist |
| Native fork concurrent writes | P | disable helpers in write Attempts unless ceiling exists |
| Helper counted as review | P | 1F different worker_id |
| Authority widening via session reuse | P | no cross-Attempt session |
| Provider completed without validation | P | candidate ≠ complete_job |
| Controller crash mid-handoff | R | terminate child; do not adopt stdio |
| Host reboot ACTIVE generation | R | boot_id mismatch; writer UNKNOWN |
| Restore stale writer | P | invalidate holds on restore |
| Malicious AGENTS.md / browser injection | P | sandbox + policy; model is not the boundary |
| Global user config overrides profile | D/P | effective config digest vs requested |
| Helper inherits parent write tools | P | disable helpers or harness ceiling |
| Opaque session id collision across accounts | P | fence includes worker_id (**missing in P1A SQL**) |

---

## W. Findings

### R1 — Attempt 1:1 primary session fights merged retry accounting
- **Class:** ARCH_BLOCKER
- **Severity:** high
- **Contract:** constitution §3–§4
- **Evidence:** `attempt_limit` default 10; claim increments `attempt_count`; P1A maps context rotation to NEW_ATTEMPT
- **Failure:** three context rotations look like three failed placements; Job hits limit while still valid
- **Remediation:** CARDINALITY_B; rotation = new epoch; rewrite boundary matrix

### R2 — Writer SQL key omits realm (H1)
- **Class:** ARCH_BLOCKER
- **Contract:** constitution §7 vs schema §2.2
- **Evidence:** opaque ids; `account_label` not unique
- **Failure:** account A and B both thread `abc` → unique index serializes or collides wrongly
- **Remediation:** unique `(worker_id, native_session_id)` WHERE executive_writer_held; never `native_session_id` alone

### R3 — `ended_at_ms` used as writer fence (H2, H11)
- **Class:** ARCH_BLOCKER
- **Evidence:** P0 SIGKILL writer held after process death; schema unique on `ended_at_ms IS NULL`; terminal Attempt “must end open generations in the same txn”
- **Failure:** LOST after deadline sets ended_at → fence free → second writer on S1
- **Remediation:** §I four-fact model; abandoning S1 is explicit and does not claim provider RELEASED

### R4 — Controller “process adoption” is physically false (H4)
- **Class:** ARCH_BLOCKER
- **Evidence:** `CodexWorker` owns pipes; `reconcile_restart` terminates live children; `adopt_attempt` docstring: does not assert process alive
- **Failure:** P1B implements PID adoption, new controller cannot talk to App Server, double-start
- **Remediation:** topology A only; delete adopt-live-App-Server language

### R5 — ExecutionProfile has no seal point (H7)
- **Class:** ARCH_BLOCKER
- **Failure:** model writes before attestation, or observed blob mutated after “immutable”
- **Remediation:** requested vs observed; first turn gated

### R6 — Adapter is a method list (H9)
- **Class:** REQUIRED_BEFORE_P1A_MERGE (blocks P1B equally)
- **Remediation:** typed contract §Q; split `prepare`/`reconcile`

### R7 — Backup/restore can resurrect writers (H10)
- **Class:** ARCH_BLOCKER for any v3 that persists held writers
- **Remediation:** §S invalidate-on-restore law

### R8 — `account_label` treated as auth realm (H5)
- **Class:** P1B_IMPLEMENTATION_GATE (multi-account) / PRODUCTION_ARMING_GATE
- **Evidence:** default `"dedicated-codex-home"`; no UNIQUE
- **Remediation:** fence on `worker_id`; ACCOUNT_REALM_ATTESTATION_UNPROVEN

### R9 — Duplicate session/process/profile columns (H6)
- **Class:** REQUIRED_BEFORE_P1A_MERGE
- **Remediation:** P7 one name; Attempt process fields are projections

### R10 — Native helper read-only is prompt-only (H8)
- **Class:** WRITE_CANARY_GATE
- **Remediation:** disable helpers in write-capable V1 unless ceiling capability is proven

### R11 — Harness version both immutable and patch-flexible
- **Class:** REQUIRED_BEFORE_P1A_MERGE
- **Remediation:** V1 exact binary digest per Attempt

### R12 — Phase 1F context loss not accepted as a tradeoff (H12)
- **Class:** REQUIRED_BEFORE_P1A_MERGE
- **Remediation:** explicit `V1_QUALITY_TRADEOFF_ACCEPTED`; no parked leader

### R13 — Residual plugins classified correctly as unclassified
- **Class:** NONBLOCKING_RESIDUE for architecture; WRITE_CANARY_GATE for write tests
- **Remediation:** optional `features.plugins=false` experiment; do not fake a clean profile

### R14 — `native_subordinates_json` and `host_id` hostname hash
- **Class:** NONBLOCKING_RESIDUE if postponed; REQUIRED_BEFORE_P1A_MERGE if kept as v3
- **Remediation:** POSTPONE both

---

## X. What may proceed

| Action | |
|---|---|
| Merge #84 as accepted architecture? | **NO** |
| Start P1B `CodexOperatorAdapter`? | **NO** |
| Implement schema v3? | **NO** |
| Browser/DevServer proof? | **NO** |
| Claude / Grok / Qwen **production-inert P0-style probes**? | **YES** (evidence, not OHF runtime) |
| Write-capable Codex OHF canary? | **NO** |
| Production-arm Codex rich operator? | **NO** |
| Start Phase 1F-C? | **NO** |

Author remediation of #84 (docs/contracts only) may proceed. Independent **exact-head re-review** is required after that. Do not mix remediation into this review commit’s meaning.

---

## Y. Final verdict

**REVISE_AND_REREVIEW**

H1–H4, H7, H10, H11 are architecture blockers. H5, H8, H9, H12 are gates that would still leave P1B inventing policy. The OHF *direction* is not BLOCK_ARCHITECTURE: Executive remains the only lifecycle authority if the amendments above are made. Until they land on a new architecture SHA, P1B is blocked.
