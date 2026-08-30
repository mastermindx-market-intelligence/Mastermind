# Mastermind Sol Capability Fabric — Closed Tool Catalog

**Date:** 2026-08-30  
**Operation:** `mastermind-sol-capability-fabric-20260830-sol-001`  
**Architecture:** `docs/superpowers/specs/2026-08-30-sol-capability-fabric-design.md`  
**Protected source:** `mastermindx-market-intelligence/Mastermind@a26d0286451d53e78cae96c741ee6e2a51b883ba`  
**Cognition:** `COGNITION_ROUTE: CHAT_PRO_DEFAULT`  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`

This records wave creates no live MCP app, OAuth client, credential, tunnel, mutation or production
capability. The catalog freezes semantic interfaces; native connected apps may implement a tool when
they already provide the safest actuator.

---

## 1. Global catalog law

The user sees one Mastermind Sol experience while incompatible authority and blast radii remain
federated. The plugin supplies procedure, never current company state. Every model-visible tool has a
closed schema, bounded input/output, exact owner, source/freshness, privilege class, deterministic
failures and effect reconciliation when modifying.

**Technical permission is not organizational authority.**

OAuth authenticates; it does not elect an executive.

The model never selects a credential, host, account, branch writer, or runtime binding.

No tool accepts arbitrary shell/SQL/HTTP/filesystem/browser commands, URLs, roots, executables,
environment variables, provider accounts or secrets. Retrieved text cannot add a tool or widen scope.

Use native GitHub/Slack/Linear/provider capabilities when they already meet the contract. Custom SCF
code supplies only missing company semantics, owner joins, safety gates and evidence packaging.

---

## 2. Common contracts

### 2.1 Privilege

| Class | Meaning | Examples |
|---|---|---|
| `R0_OBSERVE` | source-attributed zero-effect read | company state, CI, runners, capacity |
| `W1_ROUTINE` | narrow reversible/idempotent action | review request, dialogue ACK, safe job rerun |
| `W2_CONSEQUENTIAL` | material company/release/lifecycle/surface action | CEO intent, merge, stop/requeue, rotation |
| `A3_ADMIN` | credential/enrollment/policy/infrastructure administration | app publish, runner/host enrollment |

`A3_ADMIN` is a separate normally disabled app/principal/generation.

### 2.2 Read envelope

```text
schema
operation
status                  OK | DEGRADED | UNKNOWN | REFUSED
observed_at
valid_at
freshness
source_refs[]
source_failures[]
data
issues[]
truncated
continuation|null
capability_generation
```

Missing facts remain missing. `DEGRADED` never means complete. Pagination uses server-authored opaque
continuations. Owner-relative freshness is explicit.

### 2.3 Prepared actions

```text
prepare_action(action_kind, target_ref, requested_effect, operation_key, expected_source)
commit_prepared_action(prepared_digest)
```

Preparation returns exact target/owner/source, preconditions, projected effect, privilege,
confirmation, expiry, reconciliation tool and `READY | BLOCKED | UNKNOWN | REFUSED`. Commit accepts
the digest only, re-reads every load-bearing predicate, performs at most one request and never changes
target/payload/credential.

These are common wire semantics, not one cross-owner dispatcher. Every app exposes namespaced,
owner-specific prepare/commit tools only. The prepared value is an opaque self-contained expiring
envelope or owner-native receipt; there is no durable prepared-action database, queue, lock or
lifecycle.

### 2.4 Effect truth

```text
NOT_APPLIED
APPLIED
EFFECT_UNKNOWN
```

Every modifying family supports:

```text
reconcile_effect(operation_key, action_kind, target_ref)
```

It reads canonical status and never resubmits. `EFFECT_UNKNOWN` blocks retry and failover.

### 2.5 Immutable generation

```text
app_id, app_generation, schema_digest, manifest_digest,
server_build_digest, policy_id, production_armed
```

Schema changes create a reviewed generation; silent live drift is prohibited.

---

## 3. Tool census

| Domain | Tools | Class/owner |
|---|---|---|
| Common | `capability_status`, `prepare_action`, `commit_prepared_action`, `reconcile_effect` | R0/W2/A3; exact target owner |
| Steward | `company_state`, `attention_state`, `responsibility_detail`, `source_disagreements`, `capability_ledger` | R0; Steward/Control Room |
| GitHub | `operation_evidence`, `collision_census`, `assess_release_gate`, `workflow_diagnosis`, `build_proof_packet` | R0; GitHub + pure semantic engine |
| GitHub actions | `request_review`, `rerun_failed_job`, `submit_pr_review`, `merge_expected_head` | W1/W2; GitHub |
| Runner | `runner_fleet`, `runner_health`, `runner_pressure`, `workflow_affinity`, `explain_queued_job` | R0; GitHub runner/host facts |
| CodeIntel | `code_discovery`, `workspace_semantics` | R0; accepted CodeIntel facades |
| Executive | `submit_ceo_intent`, `intent_status`, `job_status`, `attempt_status`, stop/requeue prepare+commit | R0/W2; Executive OS |
| Dialogue | `dialogue_state`, `dialogue_ack`, `dialogue_continue`, `dialogue_request_repair`, `dialogue_stop` | R0/W1/W2; Dialogue/Relay |
| Surface | `inspect_sol_surface`, `foreground_sol_surface`, `provision_sol_surface`, `wake_sol_surface`, `rotate_sol_surface`, `retire_sol_surface` | R0/W1/W2; RuntimeBinding/Wake/Surface |
| Fleet | `fleet_capacity`, `placement_explanation`, `fleet_bottlenecks`, `commission_child`, `child_status` | R0/W2; Capacity/Executive |
| Ops | `host_fleet_health`, `service_health`, `tunnel_health`, `deployment_identity`, `runtime_versions`, `disk_pressure`, `provider_adapter_health`, `wake_transport_health`, `relay_health`, `codeintel_health` | R0; exact owners |
| Ops actions | `restart_exact_service`, `rotate_exact_tunnel` | W2/A3; exact service/tunnel owner |
| Admin | `admin_capability_status`, `prepare_admin_action`, `commit_admin_action` | R0/A3; isolated admin app |
| Audit | `audit_operation`, `economic_outcome`, `closeout_status` | R0; existing owner receipts |

Final manifests may namespace names, but semantics and ownership remain fixed.

---

## 4. Common and Steward tools

### `capability_status`

Input: bounded capability names or current app inventory. Output per capability:

```text
name, app_id, app_generation, privilege_class, availability,
production_armed, required_scopes, current_scopes,
confirmation_required, prepared_action_required, canonical_owner,
dependency_states, schema_digest, last_proven_at, proof_state, issues
```

Proof state uses exactly `PROVEN_LIVE`, `BUILT_NOT_PROVEN`, `PARTIAL`, `DARK_OR_DISCONNECTED`,
`BROKEN`, `SPEC_ONLY`, `NOT_BUILT`, `REJECTED_BY_DESIGN`. Source code or broad OAuth scopes cannot
produce availability or live proof.

### `company_state`

Steward composes exact responsibility, runtime, attention, blocker, capability and source-failure
facts. It answers what exists, what is running/queued/blocked/returned/terminal, who owes the next
turn, which sources disagree and what actions are serviceable. It does not parse arbitrary prose into
lifecycle or attention.

### `attention_state`

Composes Wake/Inbox/structured Agent OS/Executive facts. Authority, pressure, serviceability and
bundle relation remain separate. Priority cannot change authority; independent interrupts remain
visible.

### `responsibility_detail`

Requires exact `responsibility_ref`; joins Agent OS identity with exact Job/Attempt, RuntimeBinding,
GitHub, attention, decisions/discoveries/handoff and source disagreements. Title similarity cannot
create a join.

### `source_disagreements`

Returns exact competing claims, sources, canonical owner, current ruling or unresolved state and
repair destination. It never silently edits the losing projection.

### `capability_ledger`

Returns precise company capability state. It cannot average states into a percentage or call merged
code live without real proof.

---

## 5. GitHub semantic and action tools

GitHub stays implementation/evidence truth; SCF does not mirror it into a database.

### `operation_evidence`

Input: stable operation key and optional repository. Output matching branches, PRs, commits, reviews,
paths, runs, artifacts and production receipts. Operation text in a PR is evidence to validate;
multiple plausible carriers return `OPERATION_CARRIER_CONFLICT`.

### `collision_census`

Input exact repository, candidate branch/head/base, owned paths and semantic owners. Output protected
SHA, merge base, ahead/behind, open path overlaps, semantic conflicts, current-writer evidence,
source-law movement and `CLEAR | COLLISION | UNKNOWN`. It never authorizes reset/rebase/force push.

### `assess_release_gate`

Pure deterministic input/output:

```text
INPUT
repository, PR, expected head/base/paths/checks/capability state,
fresh GitHub facts, source-law facts, production-proof facts

OUTPUT
protected_sha, candidate_sha, merge_base, ahead_by, behind_by,
changed_paths, path/semantic collisions, required_checks/check_state,
review_state, unresolved_threads, source_law_compatibility,
production_proof_state, completion_claim_validity,
expected_head_merge_eligible, issues
```

Verdict is `ELIGIBLE | HELD | REFUSED | UNKNOWN`. It assesses; it never merges. Green CI does not
satisfy production proof, and a records-only PR may be eligible while remaining `SPEC_ONLY`.

### `workflow_diagnosis`

Returns exact trigger/SHA/attempt/jobs/steps/logs/artifacts, runner evidence, superseding-head state,
first-party failure/queue facts and whether a retry family is permitted. Job title alone is not root
cause.

### `build_proof_packet`

Returns operation/repository/base/head/PR, changed patches, reviews/threads, checks/logs/artifacts,
security, acceptance and production references, capability claim, missing evidence and packet digest.
Worker prose never overrides GitHub or production truth.

### Native action tools

- `request_review` — W1; reconcile current requested reviewers.
- `rerun_failed_job` — W1; exact terminal failed/cancelled accepted retry unit only.
- `submit_pr_review` — W1/W2; review binds to exact head.
- `merge_expected_head` — W2; requires prepared release, current source/checks/review and exact head;
  reconcile from PR merged state/resulting commit.

Repository settings, branch policy, app installation and runner administration are absent from the
normal app. Unsafe endpoint families remain assessment-only.

---

## 6. Runner observatory

### `runner_fleet`

Returns runner reference/scope/name metadata, OS/architecture, online/offline, busy, labels/group,
version, observation time, current job/host references and sources. It never returns registration
tokens, credentials, raw argv or private addresses.

### `runner_health`

Classifies `HEALTHY_IDLE`, `HEALTHY_BUSY`, `OFFLINE`, `HOST_UNREACHABLE`,
`RUNNER_SERVICE_DEGRADED`, `VERSION_DRIFT`, `LABEL_DRIFT`, `OBSERVATION_INCOMPLETE` with evidence.

### `runner_pressure` / `workflow_affinity`

Join queued jobs with eligible runners by scope/group/labels and report demand/service facts without
inventing duration or mutating placement.

### `explain_queued_job`

Distinguishes:

```text
VALID_WAIT, NO_ELIGIBLE_RUNNER, ALL_ELIGIBLE_BUSY, RUNNER_OFFLINE,
LABEL_MISMATCH, RUNNER_GROUP_MISMATCH, CONCURRENCY_LIMIT,
ENVIRONMENT_GATE, UPSTREAM_JOB_PENDING, GITHUB_STATE_UNKNOWN
```

Queue age alone cannot prove failure. Register/delete/relabel/regroup belongs to A3.

---

## 7. Code Intelligence tools

`code_discovery` maps to accepted global `search_code`, `list_repositories`, `index_status` and
carries indexed repository/ref/SHA, freshness, coverage and canonical-verification requirement.

`workspace_semantics` maps to exact Attempt-local `workspace_status`, `symbol_overview`,
`find_symbol`, `find_references`, `find_implementations`, `diagnostics`. The model cannot choose root,
worktree, executable, endpoint, environment or backend. CodeIntel never edits and remains advisory
until Git/local verification.

---

## 8. Executive and Dialogue tools

### Executive

- `submit_ceo_intent` — W2, exact CeoIngress schema/admission/idempotency; accepted `QUEUED` is not
  START/execution/completion.
- `intent_status`, `job_status`, `attempt_status` — R0 canonical reads.
- `prepare_stop_attempt` / `commit_stop_attempt` — W2 exact current Attempt, lease/fence/cause.
- `prepare_requeue_attempt` / `commit_requeue_attempt` — W2 using existing retry-safety and atomic
  Runtime mutation; effect unknown, moved Attempt, live writer or candidate/result/seal blocks.

### Dialogue

- `dialogue_state` — exact operation/carrier/latest semantic edge/awaiting side/transport state.
- `dialogue_ack` — W1 pickup acknowledgement, never START.
- `dialogue_continue` and `dialogue_request_repair` — exact current action-authoritative parent.
- `dialogue_stop` — explicit terminal edge plus watcher-disarm instruction; `WATCH_STOP_FAILED` never
  reopens a terminal child.

No dialogue tool creates a worker, lifecycle state, authority transfer or new carrier.

---

## 9. Surface and fleet tools

### Surface

`inspect_sol_surface` returns logical role/responsibility/root Job/session alias/binding ID and
generation/reasoning surface/model-mode/action-target/continuation/health with sources. It never
selects by newest tab, title, responsiveness or self-attestation.

`foreground_sol_surface` brings one verified managed surface forward; it sends no prompt and creates
no ACK/START/authority transfer.

`provision_sol_surface` accepts admitted responsibility/role/cognition/bootstrap requirements;
Capacity and host policy select the surface. Output keeps phases separate:

```text
SURFACE_CREATED_OR_SELECTED
BOOTSTRAP_DELIVERED
PICKUP_ACK_PENDING | PICKUP_ACKNOWLEDGED
START_PENDING | STARTED
RUNTIME_BINDING_PENDING | RUNTIME_BOUND
```

`wake_sol_surface` uses Wake and preserves delivered/acknowledged/source-resolved distinctions.

`rotate_sol_surface` requires durable continuation, successor selection/ACK, binding-generation
commit, predecessor fence and prior-effect reconciliation. `retire_sol_surface` requires terminal
responsibility or proven successor; closing a tab is not retirement.

### Fleet

`fleet_capacity` and `placement_explanation` expose required capabilities, eligible/excluded avenues,
cost/scarcity reason, cognition route, why-not/why-Fable and placement state from Capacity.

`fleet_bottlenecks` separates dependency, capacity, Sol, Chairman, runner, source, provider, review,
effect-unknown and actual-worker-shortage causes.

`commission_child` is W2. Input is a complete semantic mission, scope, acceptance, authority,
method/failure/stop/handoff and route requirements. Provider account, host, native session, raw
prompt-only commission, shell command and model-chosen branch are rejected. Executive creates the
child and Capacity places it. `INTENT_ACCEPTED`, `JOB_QUEUED`, placement, claim, ACK and START remain
separate.

`child_status` reads canonical Executive/dialogue/GitHub evidence; worker prose cannot supersede it.

---

## 10. Operations and administration

R0 Ops tools:

```text
host_fleet_health, service_health, tunnel_health, deployment_identity,
runtime_versions, disk_pressure, provider_adapter_health,
wake_transport_health, relay_health, codeintel_health
```

Only allowlisted host/service/tunnel identities are accepted. Results omit secrets, raw argv,
environment and arbitrary filesystem/network data.

`restart_exact_service` is W2 and accepts exact allowlisted service reference, expected instance/build
identity and reason. The server chooses one predefined service-manager operation. No unit name,
command, args, environment, sudo, host selector or restart-all. Ambiguity returns `EFFECT_UNKNOWN`
and no second restart.

`rotate_exact_tunnel` is W2/A3 depending on credential/certificate effect and cannot create arbitrary
forwarding.

The isolated Admin app exposes only `admin_capability_status`, `prepare_admin_action`,
`commit_admin_action`. It uses separate app/resource/scopes/principal and explicit administrative
authority. Candidate families are immutable app/plugin publication or disposable runner enrollment;
one wave selects one family. It never exposes credentials, generic org admin, shell, SSH or browser
settings control.

---

## 11. Audit, economics and closeout

`audit_operation` reconstructs Chairman intent, accepted architecture, Executive lifecycle,
RuntimeBinding/Wake/dialogue, GitHub evidence/production proof and Agent OS/Linear closeout through
references; it creates no timeline database.

`economic_outcome` reports measured Chairman manual interventions, archaeology, prompt transfers, Sol
tokens spent on deterministic reconstruction, time from worker RESULT to Sol adjudication, release
delay, runner diagnosis, route cost, expensive-worker use, duplicate/stale operations,
`EFFECT_UNKNOWN` and production-proof rates. Missing data stays unknown.

`closeout_status` reports GitHub, Executive, Agent OS, Linear, Dialogue/watcher and production proof
separately. Any missing required owner returns `PARTIAL_CLOSEOUT` with exact remaining actions.

---

## 12. Native/custom and OAuth partition

| Capability | Preferred implementation |
|---|---|
| GitHub repository/PR/diff/check/review and guarded native actions | native GitHub connector behind SCF policy |
| release/collision/operation semantics | custom pure engine |
| runner inventory/queue explanation | bounded GitHub/host observer |
| company state/attention | Steward app |
| CEO lifecycle | Executive app |
| dialogue | Company Dialogue app |
| surface action | RuntimeBinding/Wake/Web-Sol Surface app |
| commission/placement | Executive/Capacity Fleet app |
| code semantics | accepted CodeIntel facade |
| service/tunnel health | Ops app |
| enrollment/publication | isolated Admin app |
| reasoning workflow | Mastermind Sol plugin |

Illustrative technical scopes are separated by app and read/write class:

```text
mastermind.steward.read
mastermind.github.evidence.read
mastermind.github.review.write
mastermind.github.release.write
mastermind.runner.read
mastermind.executive.read
mastermind.executive.intent.submit
mastermind.executive.attempt.stop
mastermind.executive.attempt.requeue
mastermind.dialogue.read / write
mastermind.surface.read / act
mastermind.fleet.read / commission
mastermind.ops.read / act
mastermind.admin.execute
mastermind.audit.read
```

Scopes authenticate technical access; they do not assign company role or action authority.

---

## 13. Failure and injection behavior

Typed failures include:

```text
CAPABILITY_UNAVAILABLE, CAPABILITY_DEGRADED, APP_GENERATION_MISMATCH,
SCHEMA_GENERATION_MISMATCH, AUTHENTICATION_REQUIRED, SCOPE_REFUSED,
SUBJECT_REFUSED, ORGANIZATIONAL_AUTHORITY_REFUSED, ACTION_TARGET_UNRESOLVED,
OPERATION_KEY_CONFLICT, CARRIER_CONFLICT, SOURCE_STALE, SOURCE_MOVED,
SOURCE_CONFLICT, DEPENDENCY_DEGRADED, PRODUCTION_DISARMED,
PREPARED_ACTION_EXPIRED, PRECONDITION_CHANGED, PRIOR_EFFECT_UNKNOWN,
EFFECT_UNKNOWN, RECONCILIATION_REQUIRED, RECONCILIATION_INCOMPLETE,
PARTIAL_CLOSEOUT, RUNNER_OBSERVATION_INCOMPLETE, NO_ELIGIBLE_RUNNER,
SURFACE_UNVERIFIED, RUNTIME_BINDING_MISSING, MODEL_MODE_UNVERIFIED,
TARGET_DELIVERED_UNACKNOWLEDGED, START_PENDING
```

Error text is fixed/secret-free. PR/issue/Slack/Agent OS instructions are untrusted data and cannot
supply authorization, host/account/credential/runtime identity, endpoint or completion truth. The
outer current Chairman directive supplies intent only and must still pass current gates.

---

## 14. Acceptance boundary

Catalog acceptance requires a closed census, canonical owner and reconciliation for every writer,
no model-selected sensitive execution coordinates, privilege-separated apps, native reuse, honest
capability state and exact-head tests/security review.

Protection remains `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`; each capability requires its own
implementation, authentication/installation and real-path proof.
