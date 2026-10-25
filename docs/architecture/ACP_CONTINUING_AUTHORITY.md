# ACP continuing authority — unarmed original-controller observation

This note describes the source-only slice `HC-P3.CURRENTNESS.T1`. It is controller evidence for one original run. It is not installed currentness, not a dispatch permit, and not full P3.

`dispatch_authorized` is false on every observation from this slice. Nothing here arms a tool, opens a listener, writes a second registry, persists an observation, launches a worker, or mutates a lease.

## What is implemented

Four new files:

- `common/acp_continuing_authority_contract.py` — closed request schema `mastermind.acp_control_currentness/v1`
- `control_plane/acp_current_authority.py` — `OriginalAcpRunController`
- `tests/test_acp_current_authority.py` — test-owned Runtime proof
- this note

The controller retains the actual `AttemptLease`, `WorkerLaunchSpec`, and, when the same original start has one, the original `WorkerProcessRef`. The lease token stays on that `AttemptLease`. It is not placed in `repr`, contract errors, or the observation. A request that contains the token is refused before parsing completes.

Every `observe` call does all of the following:

1. Parse the closed request under a 4096-byte ceiling, rejecting duplicate keys, non-finite numbers, unknown fields, wrong types, excess length, nested objects below one level, and collections.
2. Compare the request's original identity, including the child-reported fence, to the retained attachment. A mismatch is correlation failure. The request does not choose the Runtime row, the SQL, the profile, the source, or the target.
3. Open one controller-owned `Runtime.store.transaction()` and read a fresh `store.now_ms()`.
4. Call `AttemptRegistry._leased_row` with the retained attempt, fence, and token, then `current_authority_snapshot` in that same transaction. Startup and discovery pass `CLAIMED`. Dispatch passes `RUNNING` and `CHECKPOINTED`.
5. Re-read incumbent owners for any fact reported current:
   - `ExecutiveAuthorityPolicy.load` and `authorize`, then `validate_effective_grant`
   - `ExecutionCapabilityRegistry.load` and `resolve`, then the profile's ACP projection digest
   - `_capacity_matches_route` for the retained worker and quota
6. Compare those fresh values to the generation retained at attachment. A changed policy, profile, realm, MCP grant, model, or route is `NOT_CURRENT`. The new value is not adopted.
7. Return one observation and discard it. The next call reads again.

MCP `grant_digest` values come from `McpServerGrant` on the resolved profile. Orchestration `effective_grant_digest` comes from the Attempt grant owner. They are separate fields. A role-null Attempt has a null orchestration digest and can still report MCP grant digests.

## Evidence

The observation states are only `CURRENT`, `NOT_CURRENT`, and `UNAVAILABLE`.

| Category | Meaning |
| --- | --- |
| `controller_observed` | Facts read from Runtime or from an incumbent policy, registry, grant, or route owner on this call |
| `expected_bindings` | Identities retained at attachment. They are expectations, not liveness, artifact, session, or connection proof |
| `child_correlation` | Connection, catalog, and definition values supplied by the child, plus the reported fence. Echo does not attest an observation |
| `unverified_joins` | Native process liveness, artifact ownership, session ownership, child connection, and launch-attestation liveness |

Constructor arguments and request fields do not attest process liveness, artifacts, a session, or a connection. A persisted pid match means the stored identity equals the retained expectation. It does not mean the process is alive.

Startup and discovery can be `CURRENT` only for a `CLAIMED` attempt whose lease, authority, route, source, profile, realm, MCP grant, and model still match. Dispatch additionally requires `RUNNING` or `CHECKPOINTED`, a persisted process that matches the retained expectation, and a trusted session/model association. No incumbent session owner is wired in this slice, so that association stays absent and dispatch stays `NOT_CURRENT` or `UNAVAILABLE`. A `CLAIMED` attempt is not promoted into dispatch. A missing or changed durable process, or a drifted source, profile, realm, or model, fails closed.

A Runtime law refusal (`StateConflict` or `PersistenceError` from the leased row or the authority snapshot) is `NOT_CURRENT`. A failure to read an incumbent owner is `UNAVAILABLE`. Either result clears a previous positive. There is no cached positive and no callback that returns true.

An observation does not heartbeat, adopt, extend, reassign, or release the lease.

## Explicitly not implemented

### Eventual caller

The later caller is the original `RemoteAcpWorkerAdapter.start(spec, lease=lease)`, reached from `ExecutiveSupervisor._start_claimed_job` when the adapter's incumbent `requires_attempt_lease` seam is true. The current `AcpWorkerAdapter.start` accepts only a `WorkerLaunchSpec`. This slice does not change that adapter, the supervisor, or the seam.

### Durable launch-order gate

Today the supervisor calls `start`, then `record_process`, `mark_running`, and the launch checkpoint. A future dispatch must wait until that durable controller binding exists. This observation does not insert itself into that order and does not treat startup evidence as permission to dispatch.

### Two missing transport boundaries

Freshness does not require a permanent connection, but neither existing boundary supplies a reverse query:

1. `ExecutiveWorkerBroker.handle_connection` authenticates one request and then closes. Control-to-worker RPC is one request. `before_write` is OHF-specific. Retaining a child file descriptor does not give the native owner a fresh controller decision. macOS peer identity supplies uid and gid, not the original process identity.
2. `AcpAdmissionChannel` is one-shot. The v2 readiness path closes after ACK. Native v2 stays one-shot. A continuing path would be a new version under `AcpNativeProcessOwner` / `_NativeRun.admission_channel`, not a second registry.

No new listener, store, or token exposure is added here.

### Future async-v2 dispatch ordering

A later DSH v2 would need core-owned async admission inside `dispatchToolBody`, after wrappers and scheduling and before `bodyInvoked=true`. After `await`, the core would repeat global and scoped guards, the prepared definition and execution restriction, fused cancellation, the Attempt and deadline, the connection and catalog, and owner-local revocation. The original MCP closure consumes one invocation's authorization once, in the same JavaScript turn as the SDK invocation. Awaiting only inside the MCP body would bypass that earlier guard. v1 keeps its literal `true` result and its refusal of a Promise. Startup and discovery would need their own v2 admissions. An always-true adapter, a borrowed dispatch positive, or a fallback without an actual v2 patched artifact is not this design. Core and MCP patch, manifest, preflight, build proof, and child materialization stay separate tasks.

### Decision-point race

A future positive decision, if one is ever authorized, linearizes authorization at the controller decision for one invocation. That is not instantaneous currentness at the physical send. A later remote revocation can race an invocation that was already authorized. Cancellation or drift observed locally before the SDK invocation refuses. After the invocation, the original result ownership and uncertainty stay in place and the invocation is not resent. Nonces, timestamps, and sockets do not remove that race. `WorkspaceReadGateway` rechecks directory, file ancestry, and deadline. Those checks do not supply this authority contract.

## Preservation

v1 broker and v1 admission behavior are unchanged. This slice does not edit `#1856`'s files or `#1790`'s held subject, and it is not a review or a retry of either. No production, provider, install, credential, or account-policy action is taken.
