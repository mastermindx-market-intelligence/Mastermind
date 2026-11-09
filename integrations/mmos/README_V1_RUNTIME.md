# MMOS V1 Runtime — how a Hermes/project request becomes a finished child (operator view)

This document explains, for an operator, how a request flows **admit → classify/place → launch → read → result → parent continuity** in the V1 integration candidate, with the exact modules and functions involved. It is **derived from the code as merged** (every function named below exists in this tree and is pinned by tests); where a path is a *registered seam* rather than a proven-live lane, that is stated explicitly — naming a route selects nothing and launches nothing.

Status vocabulary: **source-complete** = code + tests exist in this tree; **registered seam** = descriptor/contract exists but no live worker can bind it yet; **proven-live** = exercised by the lanes' `LANE_*.md` ledgers as they land (see the ledger table at the end — lanes still in flight at publication time are marked *pending lane ledger*).

---

## 1. Admit — the request enters under its root

A caller (Hermes project actor, Executive COO cycle, or a host-side frame) sends a `ChildExecutionRequest` (`control_plane/child_execution_contracts.py`):

- **Entry points:** `ExecutiveControlService.admit_child_execution_request` (`control_plane/executive_service.py`) — or the frozen-frame ingress `_handle_child_request_admit_frame`, where the envelope is retrieved from `app_binding.child_request_material[command]` and never travels through the model.
- **Core admission:** `JobRegistry.admit_child_execution_request` (`control_plane/executive_runtime.py`). Idempotency is the triple `(root_ref, immediate_parent_run_ref, logical_child_key)` plus the `request_digest` (sha256 over `ChildExecutionRequest.canonical_payload()`; absent Rev 5 v1.1 fields are excluded, so a v1-era redelivery after the upgrade is a retry, never a conflict).
- **Outcomes:** a plain **QUEUED root-level Job** (no worker, host or placement decided yet), a **WAIT backpressure receipt** with a precise reason (nothing created), or a **digest conflict** (`CHILD_REQUEST_DIGEST_CONFLICT` — same triple, different content; never a second Job).
- **Pinned by:** `tests/test_child_execution_contracts.py` (envelope law), `tests/test_rev5_contracts_v1_1.py` (v1/v1.1 compat + digest pin), `tests/test_executive_runtime*` (admission/backpressure cases).

Status: **source-complete.**

## 2. Classify and place — one authority, one transaction

Classification (shared routing law, C0–C3): `ChildRoutingPolicy.evaluate` in `control_plane/child_execution_contracts.py`, byte-identical to the live Hermes plugin copy `plugins/mmx-router/child_routing_policy.py` (23-case parity test). A C3 frontier claim needs a concrete ≥24-char `witness:` line; without one it downgrades to the declared lane (`hard` / `C2_COMPLEX_BOUNDED`) or is refused. Business impact/urgency/"production" are **not** witnesses.

Preview (advisory only, never a grant): `route_preview.compose` (`integrations/executive_mcp/route_preview.py`) → `ModelRouter.load(...).explain_route(request)` (`control_plane/model_router.py`) builds a `RoutePreview` with `authority = NONE_SOURCE_PREVIEW_ONLY` and `production_armed = False` **by construction** — there is no code path from a preview to a reservation.

The claim (the single placement authority): `AttemptRegistry.claim_job` → `_claim_job_in_transaction` (`control_plane/executive_runtime.py`) — one SQLite transaction that:
1. rechecks lineage, admitted class and route descriptor (`_select_placement_in_transaction`, `control_plane/executive_placement_authority.py`),
2. reserves host slot + root concurrency + shared quota (`ResourceBroker._reserve_placement_in_transaction`),
3. issues the fenced `ExecutionBinding` (`issue_execution_binding` → `child_execution_contracts.ExecutionBinding`; Rev 5 v1.1 fields carry native runtime identity, workspace containment, the T3 `clientRequestId` operation key + caller namespace, and the descendant policy/envelope),
4. appends the `JOB_CLAIMED` event; command replay is validated read-only against the recorded claim.

Two transports reach the same authority, never a second one:
- **Host-executor pull (lane A):** `HostHeartbeatIntake._claim_for_host` / `HostExecutor.pull_once` (`control_plane/executive_host_executor.py`). A stale heartbeat earns zero new claims; a claim addressed to another host is refused, not queued.
- **Supervisor dispatch (lane B):** `ExecutionSupervisor.start_job` / `start_cycle_job` and `ExecutiveControlService.dispatch_selected_child` (the strictest exemplar: dispatch-lock, readiness fences, effect-unknown is a state — never a silent retry).

Status: **source-complete** (both transports), pinned by `tests/test_executive_runtime*`, `tests/test_executive_host_executor*`, `tests/test_executive_supervisor*`, `tests/test_executive_service*`.

## 3. Launch — the binding must be current at the adapter

The closed, reviewed adapter registry is `ADAPTER_DESCRIPTORS` (`control_plane/worker_adapter.py`). Every descriptor declares `runtime_kind`, `descendant_policy` and a SUPPORTED/UNSUPPORTED/UNKNOWN capability map; `capability_status()` reads fail-closed (undeclared = UNKNOWN) and `descriptor_problems()` completeness runs in the union tests.

| Runtime | Adapter | State in this candidate |
|---|---|---|
| `hermes-native` | `control_plane.hermes_worker_adapter.HermesWorkerAdapter` | **implemented** (`fabric_per_child`); `HermesWorkerAdapter._require_current_binding` refuses any start without a current, unexpired binding for its own adapter id, and retains the original process ref so a repeat start raises instead of replacing. **Built but unselected** — selection is a deployment act by the incumbent runtime, not a code fact. |
| `codex-cli` | `control_plane.codex_worker.CodexWorkerAdapter` | **implemented**; descendant fan-out fail-closed (`native_fanout_disabled`) until a shared-admission hook exists. |
| `canonical-paid-fabric` | `CanonicalPaidFabricWorkerAdapter` | **implemented** (`fabric_per_child`); paid launches re-validate the fresh claim with no awaited preparation between validation and start (`ExecutionSupervisor._start_claimed_job`). |
| `opencode-free-cli` | `control_plane.opencode_worker.OpenCodeWorkerAdapter` (outside reviewed binding path) | **registered, deliberately not implemented** — naming the route launches nothing (no confinement profile / broker composition yet). |
| `t3-native` | — (Rev 5 D3 lane owns the flip) | **registered seam**: NAMED-but-NOT-IMPLEMENTED, all capabilities UNKNOWN. Upstream source capability is not installed-fleet proof. |
| `dsh-acp` | — (Rev 5 D5 lane owns the flip) | **registered seam**: `native_fanout_disabled` until a real native descendant-admission hook is proven; `bounded_native_fanout` requires a named enforcement ref. |

Launch preconditions on the supervisor side: `ExecutionSupervisor._start_claimed_job` validates profile/worktree/commission, builds the spec, and only then reaches `adapter.start`; host-side, `HostExecutor.start_claimed` rechecks local pressure and releases unstarted claims through `release_unstarted_claim` (one transaction, quota freed, Job back to QUEUED).

Status: hermes-native/codex/paid-fabric **source-complete**; t3-native/dsh-acp **registered seams — pending lane ledger** (Rev 5 lanes in flight); opencode-free-cli **registered seam by design**.

## 4. Read and control

- Process identity is persisted under the same fence+lease (`AttemptRegistry.record_process` / `mark_running`, `control_plane/executive_runtime.py`).
- Collection runs as a task with heartbeats: `ExecutionSupervisor.finish_job` → `_collect_with_heartbeats` → `_persist_collection` → `_terminalize` — which requires a truthful durable OS exit code (a `None` exit code quarantines the attempt rather than guessing) and settles through `AttemptRegistry._terminal` → `complete_attempt` / `fail_attempt`, comparing attempt **and** fence against the binding.
- Cancel is acknowledged, not assumed (`acknowledge_cancel`); lease expiry is reconciled, never treated as proof of stop (`reconcile_expired`; host-side `lease_expired` returns an explicit `LeaseExpiryDisposition`).
- Supervisor restart adopts a live attempt only through `adopt_attempt` → `_reissue_placement_binding`, which may move **only** `fence_counter` and `lease_expiry` — every identity/route/host/quota field stays at its claim-time value.

Status: **source-complete.**

## 5. Result — a reference, not a transcript

The collection receipt is persisted and the result reference stored on the attempt/job before the parent is notified; `HermesWorkerAdapter.collect_result` rejects any receipt whose `run_id` differs from the originally retained one. Terminal status for selected children (`ExecutiveControlService.selected_child_status`) is sourced from the canonical validated role completion and never delivers a second message.

Status: **source-complete.**

## 6. Parent continuity — the session bridge

The bridge routes to incumbent owners; it owns no lifecycle, dialogue or placement:

- `SessionBridgeGateway.call` (`integrations/session_bridge/gateway.py`) dispatches `session_targets` / `session_send` / `session_summon`; `session_summon` must go through the existing Executive admission path.
- `HermesNativeSession` (`integrations/session_bridge/hermes_native.py`) binds and observes the native session: `request(binding, …)` / `observe(binding)`, with admission material kept separate from answer text (`_admission`).
- `RuntimeSessionReturn` (`integrations/session_bridge/runtime_return.py`) binds the original caller: `read_hermes` / `send_hermes`, continuation commits (`begin_continuation_commit`), original reply grants.
- `NativeReplyWriter` (`integrations/session_bridge/native_reply.py`) resolves the binding by `(native_session_id, operation_key, …)`; replaying the same `operation_key` reconciles rather than re-sends.

Continuity invariants: **root conserved** (`root_run_ref` unchanged down the tree), **immediate parent changes correctly per level**, both re-proved inside the claim transaction.

Status: **source-complete.**

---

## Lane ledger (proven-live evidence)

| Stage | hermes lane | t3 lane | dsh lane | fabric lane |
|---|---|---|---|---|
| Admit/classify/place/claim | source-complete (this tree) | pending lane ledger | pending lane ledger | pending lane ledger |
| Launch (`t3-native` / `dsh-acp` adapters) | n/a (plugin mirror per `mmos/CONTRACT_REV5.md` §4) | pending lane ledger | pending lane ledger | n/a |
| Native identity / workspace / fan-out binding (v1.1) | contract landed (`feat/mmos-rev5-contracts`) | pending lane ledger | pending lane ledger | pending lane ledger |

As the Rev 5 lanes land, each lane's `LANE_*.md` ledger upgrades its column from *pending* to **proven-live** with the exact receipts; until then this document claims source-completeness only, never installed-fleet proof (unknown is unknown).

*Derived from the candidate tree; full code-verified trace with line anchors: `mmos/cache/D8_FLOW_TRACE.md` (contracts & integration seat, Rev 5 D8).*
