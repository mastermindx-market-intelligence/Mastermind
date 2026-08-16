# OHF-P1A — Operator Harness Constitution

**Date:** 2026-08-16
**Status:** architecture contract for independent review. Not accepted law. Not armed.
**Depends on:** merged OHF-P0 (`da6bd78e078b96db8c121b16f1b10e3fd70e6fef`, PR #81)
**Does not depend on:** unmerged PR #66 or PR #72 becoming law
**Production arming / Phase 1F-C / CodexOperatorAdapter: prohibited by this commission**

Authoring verdict is not architecture acceptance. Final state of this PR:
`READY_FOR_INDEPENDENT_REVIEW`.

## 0. One-sentence law

Executive OS owns organizational work. A native harness owns the local
reasoning loop inside one Attempt. Provider-completed is evidence, never
Executive completion.

## 1. Source hierarchy used

Binding / merged:

- `research/MASTERMIND_CHARTER_V2.md` (P7 one source of truth; P8 shadow before authority)
- `config/strategic_state.yml` (`duplicate_control_planes: prohibited`)
- `config/authority_map.yml` (current merged map; no `seats:` block on master)
- `AGENTS.md` executive contract
- `research/EXECUTIVE_OS_PHASE1F_ORCHESTRATION_CONTRACT.md`
- `docs/EXECUTIVE_WORKER_ROUTING.md`
- `control_plane/executive_runtime.py` (`SCHEMA_VERSION = 2`)
- `control_plane/worker_adapter.py` (`WorkerExecutionAdapter` sealed floor)
- `research/EXECUTIVE_OS_OHF_P0_LIVE_ACCEPTANCE_2026-08-16.md`

Draft / not law:

- PR #66 Phase 1G Agent Fabric (`session_handles`, `mastermind.agent_handoff.v1`, L13–L16)
- PR #72 G0 source-law ruling (seats, decision altitude, priority split)

Superseded by P0 evidence:

- Phase 1G `session_handles` as a single row mixing `provider_session_id` with
  `pid/pgid/boot_id`. Live App Server proved those are different identities.
  Replace with `HarnessSession` + `ProcessGeneration`. Do not keep both names
  for the same concept.

Unresolved source-law dependency:

- P1A does **not** require PR #72 to merge. Seat labels and Chairman-reserved
  categories are organizational, not harness identity. If G0 later lands, OHF
  reads it; OHF must not encode G0 tables as if they already exist.

## 2. Ownership matrix

| Concept | Canonical owner | Durable source | Who may mutate | Native harness influence | Survives process restart |
|---|---|---|---|---|---|
| Company objective | Chairman / strategy Git | `strategic_state.yml` (advisory) | Chairman path only | no | yes (Git) |
| Job | Executive runtime | `jobs` | runtime txn | no | yes |
| Parent/child | Executive runtime | `jobs.parent_job_id` | runtime txn | no | yes |
| Authority envelope | Executive runtime + authority map | job authority columns | runtime txn | no | yes |
| Priority | Executive runtime | `jobs.priority` | runtime txn | no | yes |
| Attempt | Executive runtime | `attempts` | runtime txn | no | yes |
| Workspace | Executive runtime | `jobs.branch/worktree` | runtime txn | cwd must match; cannot choose | yes |
| Provider | placement | `workers.provider` + attempt | new Attempt if changed | no | yes |
| Provider account | placement | `workers.account_label` | new Attempt if changed | no | yes |
| Capacity pool | quota class | `worker_quota_classes` | supervisor | no; quota events are observations | yes |
| Exact model | ExecutionProfile | Attempt snapshot | new Attempt if changed | served≠requested → refuse or new Attempt | snapshot yes |
| Harness kind | ExecutionProfile | Attempt snapshot | new Attempt if AppServer→PTY | no | snapshot yes |
| Native session/thread | HarnessSession | Attempt native id + generations | resume inside Attempt only | yes, locally | yes if graceful |
| OS process | ProcessGeneration | `process_generations` (proposed) + current attempt process fields | supervisor | no | no |
| Native fork/helper | parent HarnessSession | subordinate handle JSON/events | adapter observation | yes, private | maybe; not a Job |
| Tool capability | ExecutionProfile policy | Attempt snapshot | new Attempt if load-bearing | discover ≠ permit | snapshot yes |
| Skill | ExecutionProfile | Attempt snapshot | see drift matrix | discover ≠ grant | snapshot yes |
| MCP | ExecutionProfile | Attempt snapshot | see drift matrix | discover ≠ grant | snapshot yes |
| Sandbox | ExecutionProfile | Attempt snapshot | new Attempt | no | snapshot yes |
| Approval policy | ExecutionProfile | Attempt snapshot | new Attempt | no | snapshot yes |
| Browser / devserver | Resource Fabric later | not in P1A | n/a | n/a | n/a |
| Result | Executive runtime | `attempts.result_json` after validation | runtime txn | candidate only | yes |
| Validation | Executive runtime | validation receipts | supervisor | no | yes |
| Independent review | Executive child Job | `jobs.reviews_job_id` | runtime txn | native review-subagent does **not** count | yes |
| Provider quota | provider | observation events | none in Executive | telemetry only | observation yes |

Non-negotiable: native provider state never owns Job lifecycle, authority,
Executive priority, review acceptance, Executive completion, or placement.

## 3. Identity model

```text
Job
 └── Attempt                         1:N
      └── primary HarnessSession     1:1
           ├── ProcessGeneration 1
           ├── ProcessGeneration 2
           └── ProcessGeneration N
           └── subordinate NativeSessionHandles (forks/helpers)
```

Cardinalities:

- One Job has many Attempts.
- One Attempt has exactly one **primary** HarnessSession.
- One HarnessSession has many ProcessGenerations; **at most one** Executive-owned
  active writer generation.
- Native forks/helpers are subordinate handles of the primary session, not
  additional HarnessSessions and not Executive Jobs.

This is design **A**, not B. B (N HarnessSessions per Attempt with roles) would
invite treating a helper as a second governed principal. P0 fork proof showed
branchable conversational state, not a second budget/authority principal.

`session_handles` from PR #66 is refined, not duplicated: the 1G row mixed
session id and process identity. Those become two objects.

Wake Fabric `SessionTarget` remains an alias/routing map, not lifecycle.

### 3.1 Attempt immutables

One Attempt is one immutable combination of:

Job, authority envelope, allowed-write paths, workspace identity, provider,
provider account, capacity slot, exact model, harness kind, harness version,
ExecutionProfile.

Change any of those → new Attempt or refuse. See §4.

### 3.2 HarnessSession must not cross Attempts

A native conversation can carry previous authority, workspace, tools, account,
and untrusted tool output. Reusing it under another Attempt is a governance
hole.

Law:

```text
process restart inside same Attempt → resume same HarnessSession
new Attempt → provider-neutral Handoff → fresh HarnessSession
```

P1A does **not** propose reusing one native session across Attempts. No proof
exists that authority cannot widen, workspace cannot drift, or tool output
cannot contaminate the next envelope.

## 4. Attempt-boundary matrix

| Case | Decision | Rationale |
|---|---|---|
| Graceful App Server restart | **same Attempt** | P0: PID 30646→30816, same thread |
| Crashed App Server with successful safe resume | **same Attempt** | same native session after bounded reconciliation |
| SIGKILL with active-writer refusal | **same Attempt while RECOVERY_PENDING**; after deadline **new Attempt** | P0: writer lease survives kill; V1 does not steal |
| Codex native context compaction | **same Attempt** | harness-private; not a governance boundary |
| Native thread fork for private analysis | **same Attempt** | subordinate handle; not a child Job |
| Fresh native thread because context became poor | **new Attempt** | new primary session; handoff required |
| Model changes | **new Attempt** | profile immutable |
| Served model differs from requested | **refuse** launch; if already running **new Attempt** after interrupt | cannot silently change the profile |
| Provider changes | **new Attempt** | realm change |
| Provider account changes | **new Attempt** | realm change; auth domain is not copyable |
| `CODEX_HOME` changes | **new Attempt** | different auth domain |
| Harness AppServer → PTY | **new Attempt** | different harness kind |
| Harness version changes | **new Attempt** if binary/protocol digest changes in a load-bearing way | treat as profile identity |
| Skill bundle changes | **new Attempt** if REQUIRED/FORBIDDEN set changes; **same Attempt** only for documented ALLOWED_AMBIENT baseline refresh that does not add unclassified/forbidden | see drift law |
| MCP bundle changes | **new Attempt** if required/forbidden servers change | |
| Ambient capability baseline changes | **new Attempt** for write profiles unless the new names are in the version allowlist | fail-closed unclassified |
| Sandbox changes | **new Attempt** | |
| Approval policy changes | **new Attempt** | |
| Network permission changes | **new Attempt** | |
| Authority changes | **new Attempt** | |
| Allowed-write paths change | **new Attempt** | |
| Workspace changes | **new Attempt** | |
| Base SHA changes | **new Attempt** | work identity changed |

## 5. Native helper / fork law

- Native helper/fork ≠ Executive child Job.
- No independent Executive budget, authority, review, provider/account, or
  durable company deliverable.
- V1 helpers may analyze / research / read-only explore inside the parent
  Attempt ceiling.
- They may **not** fan out write-capable parallel work.
- Parallel durable writes remain: Executive child Job → separate worktree →
  separate Attempt → validation/review.
- Do not promote a private helper retroactively into a Job.
- A native review subagent / forked thread / second agent in the same Attempt
  does **not** satisfy Phase 1F independent review. Minimum remains a different
  `worker_id`.

If helper work needs a different provider, account, worktree, deliverable,
review, or authority envelope: create the child Job **prospectively**.

## 6. Phase 1F-B compatibility

A parent with living children is a container and cannot be claimed as ordinary
worker work. Therefore OHF does **not** design:

- Fable leader claims parent, delegates, stays alive for hours, polls, aggregates.

Expected pattern:

```text
bounded planning turn (rich HarnessSession on a planning Attempt)
  → durable children created
  → leader process/session released (graceful stop; Attempt checkpoints)

children run independently (own Attempts, own sessions)

later explicit orchestration Attempt
  → receive durable results + provider-neutral handoff
  → bounded aggregation/repair turn on a fresh HarnessSession
```

Rich native continuity lives **inside one Attempt**, not across the parent
container's lifetime. Planning and later aggregation are different Attempts
joined by handoff, not one 3-hour native thread. This preserves L7 (no
persistent leader process) and avoids a second scheduler.

## 7. Single-writer law

At most one Executive-owned active ProcessGeneration may control one native
primary HarnessSession.

Fence key:

```text
(provider, account_label, native_session_id)
```

A native thread id is meaningless outside its provider/account realm.
Additionally: unique active Attempt per native session.

Durable owner: Executive SQLite, `BEGIN IMMEDIATE`, same pattern as
`worker_quota_classes.fence_counter` / `attempts.fence_generation`.
No sidecar lock DB. No filesystem lock as organizational truth.
Provider "active writer" is additional defense, not lifecycle authority.

Acquire:

1. Check no ACTIVE/QUIESCING/RESUMING generation for that fence key.
2. Old generation proven quiesced (process dead **and** resume-safe, or
   graceful stop completed).
3. Insert new generation; bump fence; record pid/pgid/start/boot.
4. Else enter RECOVERY_PENDING; do not start a second writer.

Release: graceful stop → process exit observed → generation ended → fence free.
Stale writer: SIGKILL path stays RECOVERY_BLOCKED_ACTIVE_WRITER until deadline,
then Attempt INTERRUPTED/LOST, checkpoint if trustworthy, handoff, new Attempt,
fresh session. V1 does not steal writers or delete Codex lock files.

Controller restart: `adopt_attempt` already CAS-bumps the Attempt lease. The
harness writer fence is separate: re-prove the process generation (pid +
start identity + boot id) before resume. Do not adopt a live App Server from
PID alone.

Host reboot: boot_id mismatch ⇒ generation dead. Native session may still
exist in provider storage. Resume only after writer-safe reconciliation;
otherwise new Attempt. **Untested in P0. Not VERIFIED.**

## 8. Recovery state machine

Do not add a new AttemptStatus for every harness fact. Map onto existing
Attempt statuses plus generation-scoped recovery class.

| Concept | Where | Notes |
|---|---|---|
| CLAIMED / RUNNING / CHECKPOINTED / COMPLETED / FAILED / LOST / CANCELLED | AttemptStatus (existing, durable) | |
| QUIESCING | ProcessGeneration.termination_class | graceful stop in flight |
| RECOVERY_PENDING | ProcessGeneration.recovery_class | durable; gates second writer |
| RECOVERY_BLOCKED_ACTIVE_WRITER | ProcessGeneration.recovery_class | P0 observed |
| RESUMING | ProcessGeneration.resume_intent/result | durable until success/fail |
| ACTIVE writer | derived: one generation with ended_at NULL and resume_result in {active, resumed} | |
| Adapter RPC errors | receipts only | |

Graceful (P0 verified):

```text
RUNNING → request stop → process exits → fence releases
→ new ProcessGeneration → thread/resume → same thread → RUNNING
```

Hard-crash (P0 observed):

```text
RUNNING → SIGKILL → process gone → RECOVERY_PENDING
→ bounded reconcile
  safe resume → new generation ACTIVE
  writer blocked → RECOVERY_BLOCKED_ACTIVE_WRITER
→ deadline exceeded → Attempt LOST/CHECKPOINTED + handoff + new Attempt
```

Deadline fail-closed attacks:

- Data loss: mitigate with last trusted checkpoint_json before interrupt.
- Duplicate work: new Attempt starts from handoff, not from silent resume.
- Double-writer: fence refuses a second generation while blocked.

## 9. ExecutionProfile

Immutable JSON snapshot + content digest **on the Attempt**. Not a mutable
profile row. A later content-addressed table is optional sharing; V1 does not
need it.

Required snapshot contents:

- harness kind, binary version, binary digest, protocol version
- requested model, served model
- auth class, provider, account/slot (labels only)
- requested capability digest, observed capability digest
- skill / MCP / plugin manifest digests
- sandbox, approval policy, network policy
- effective config digest (non-secret)
- capability policy: REQUIRED / ALLOWED_AMBIENT / FORBIDDEN
- unclassified handling: fail-closed on write profiles

Capability presence is not authority:

`DISCOVERED → AVAILABLE → PERMITTED → INVOKABLE → INVOKED`

Native tool list ≠ Executive permit. Skill installation ≠ capability grant.

P1A 0.147.0 ChatGPT Pro App Server, after `features.apps=false` and
`skills.bundled.enabled=false`:

- REQUIRED: `ohf-probe`, `ohf_probe` / `ohf_probe_echo` (laboratory)
- FORBIDDEN for write profiles until explicitly allowed: `codex_apps` (gone
  when apps disabled), GitHub connector tools, browser, network
- ALLOWED_AMBIENT is **not** "everything leftover". Residual
  `github:*`, `openai-templates:*`, `plugin-management` remain unclassified
  until a versioned allowlist is reviewed.
- Write-profile launch with those residuals: `LAUNCH_REFUSED_UNCLASSIFIED`

## 10. Configuration drift between generations

| Change | Action |
|---|---|
| model / provider / account / harness kind / sandbox / approval / network / filesystem roots / authority / workspace | new Attempt |
| harness patch version with same protocol+digest policy | new ProcessGeneration, re-attest; new Attempt if digest/policy changes |
| REQUIRED skill/MCP missing | refuse / interrupt |
| FORBIDDEN present | refuse / interrupt |
| ALLOWED_AMBIENT baseline add that is pre-approved for this binary | new ProcessGeneration, re-attest |
| unclassified appears | refuse write profile |
| native subagent policy | new Attempt if write fan-out would widen |

## 11. Adapter contract `mastermind.operator_harness/v1`

Do **not** extend `WorkerExecutionAdapter`. Sealed workers keep
`start / collect_result / cancel / run_validation_argv`.

Rich path is a sibling: `OperatorHarnessAdapter`. Shared utilities allowed.
Adapter returns typed observations. Supervisor/control service decides.
Runtime transaction mutates Executive state. Adapter must not mark Jobs complete.

| Method | Class |
|---|---|
| `probe` | COMMON_OPTIONAL |
| `describe_capabilities` | COMMON_REQUIRED |
| `prepare` | COMMON_REQUIRED |
| `start_session` | COMMON_REQUIRED |
| `resume_session` | COMMON_OPTIONAL (capability: persistent_session) |
| `begin_turn` | COMMON_REQUIRED |
| `read_events` | COMMON_REQUIRED |
| `send_input` / `steer` | COMMON_OPTIONAL |
| `respond_to_approval` | COMMON_OPTIONAL |
| `interrupt_turn` | COMMON_REQUIRED |
| `fork_session` | COMMON_OPTIONAL (Codex has it; others may not) |
| `checkpoint` | COMMON_OPTIONAL |
| `collect_candidate_result` | COMMON_REQUIRED |
| `graceful_stop` | COMMON_REQUIRED |
| `cancel` | COMMON_REQUIRED |
| `reconcile` | COMMON_REQUIRED |
| writer-steal / lock-file delete | REJECTED_FROM_INTERFACE |
| `complete_job` | REJECTED_FROM_INTERFACE |
| browser/devserver lease APIs | REJECTED_FROM_INTERFACE (later Resource Fabric) |
| Codex `plugin/list` | CODEX_SPECIFIC and not required (P0 race) |

## 12. Events

Two layers: provider-native raw (untrusted, redacted, size-bounded) and
normalized Executive events. Adapters need not emit every type.

Normalized vocabulary: `HARNESS_SESSION_STARTED`, `TURN_STARTED`,
`ASSISTANT_OUTPUT`, `TOOL_REQUESTED`, `TOOL_COMPLETED`, `APPROVAL_REQUIRED`,
`USAGE_OBSERVED`, `RATE_LIMIT_OBSERVED`, `CHECKPOINT_AVAILABLE`,
`CANDIDATE_RESULT`, `TURN_INTERRUPTED`, `HARNESS_SESSION_ENDED`.

Raw handling: redact credentials; bound size; cursor/replay; ignore duplicates
by provider event id when present; tolerate out-of-order; reconnect does not
imply new Attempt; malformed provider events are receipts, not state.

MCP: P0 did not observe structured MCP item events. Do not require the
provider event stream as sole audit. Future Executive-owned MCP should add
server-side receipts (Attempt + tool + input/result digests). Not implemented
in P1A.

Quota: store provider-defined horizons as instances (`used_percent`,
`window_duration_minutes`, `resets_at`, `rate_limit_reached_type`). Never
hard-code 5h/weekly/monthly columns. Classification remains
`provider_reported | failure_inferred | unknown`. Do not compute remaining.

## 13. Failures vs semantic work failure

Quota exhausted / concurrency limited → cool pool, do not fail the Job as code.
Auth expired/failed → interrupt Attempt, do not retry with copied `auth.json`.
Process crash / session unavailable / active writer → recovery machine.
Tool/MCP/transport → Attempt failure class, not pool cool unless provider 429.
Config attestation / capability missing or forbidden → refuse launch.
Workspace mismatch → refuse.
Validation failure → Job/Attempt failed, not quota.
Model/semantic failure → work failure.
Human intervention → approval_required, not crash.

Cross-provider failover is a new Attempt after handoff. ATT-1 must not silently
become another provider.

Handoff (`mastermind.agent_handoff.v1` from 1G, still a draft name we preserve
rather than duplicate): execution facts, decisions, artifacts, failures,
remaining work. No hidden chain-of-thought. Minimum for account failover,
cross-provider, machine loss, context rotation, operator takeover, and fresh
thread after session failure.

## 14. Host/controller cases (untested — design only)

| Case | Consult | Re-prove | Adopt process? | Resume session? |
|---|---|---|---|---|
| Executive control process restart | Attempt + lease + generation | fence + lease via `adopt_attempt` | only if pid+start+boot match | if writer-safe |
| Worker supervisor restart | same | same | same | same |
| Host reboot | boot_id | generation dead | never by old pid | only if provider session still writer-safe; else new Attempt |
| App Server alive, controller dead | generation row | process still matches | yes if identities match | no second writer |
| Controller alive, App Server dead | generation row | process gone | no | recovery machine |

None of these are VERIFIED by P0.

## 15. Codex-specific vs common

Common: session start, turn, events, interrupt, graceful stop, cancel,
capability describe, candidate result, reconcile.

Codex-specific: App Server JSON-RPC, `thread/fork`, `skills/extraRoots/set`,
`account/rateLimits/read`, `features.apps`, `skills.bundled.enabled`,
active-writer error string, ChatGPT auth domain.

A harness without fork is still a valid operator. Quota telemetry may be
unknown. Claude/Grok/Qwen adapters must not fake Codex thread ids.
