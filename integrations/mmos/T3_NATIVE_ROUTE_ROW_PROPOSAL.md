# T3-native route row proposal (verbatim; PROTECTED file unchanged)

`config/executive_worker_routes.json` is protected (#2177). This document is
the exact proposed row — nothing in this proposal has been applied to the
live file. Owner of the live edit: the normal protected-change path for that
file, after the installed-Executive canary (see *Remaining live steps*).

Audit lane: item #14 closeout (AUDIT_T3_DURABLE_ADAPTER_OPUS_20261109;
REAUDIT_T3_ADAPTER_A3_OPUS_20261109; REAUDIT3_T3_ADAPTER_A4_OPUS_20261110
gap 4) and DONE_WHEN 2 (Model Router can choose T3).

## Proposed provider row (verbatim JSON)

```json
    "t3": {
      "adapter_id": "t3-native",
      "enabled": false,
      "autonomous_allowed": false,
      "production_armed": false,
      "arming_grant": "OQ-7 (Chairman ruling, 2026-11-08): scoped V1 arming for Wave 2 live testing — NOT blanket production arming. This row names the t3-native route only: enabled=false and production_armed=false keep it unselected until the installed Executive canary passes through control_plane/t3_native_composition.py (the reviewed composition of the SQLite adapter store, T3McpToolPort and the supervisor pre-ACK recovery binding). No model alias is bound to this row: t3-native has no entry in _ADAPTER_EXECUTION_SURFACES, so no worker-eligible alias can load today (same shape as the hermes-native row, which arms a route without claiming worker-alias eligibility). Actual placement follows the capacity quota-class metadata pattern {\"adapter_id\": \"t3-native\"} (worker_type t3-native), not a Model Router alias."
    }
```

Placement in the file: one additional key under `providers`, beside `hermes`
and `deepseek`. No other key of the live file changes; global
`production_armed` stays `false` (loader law).

## Why this exact shape

* `adapter_id: "t3-native"` resolves through the reviewed
  `ADAPTER_DESCRIPTORS` (implemented, implementation
  `control_plane.t3_execution_adapter.T3ExecutionAdapter`, runtime_kind
  `t3-native`) — the loader's `adapter_descriptor()` check passes.
* `enabled: false` + `autonomous_allowed: false` + `production_armed: false`
  is the deepseek precedent: naming the route selects nothing, binds no live
  worker, and launches nothing. The hermes precedent shows the alternative
  (enabled + armed + no aliases); the t3 row keeps the weaker, unselected
  shape because — unlike hermes-native — the t3-native adapter still has no
  `_ADAPTER_EXECUTION_SURFACES` entry, so a `worker_eligible` alias would be
  refused by the loader's adapter/execution-surface check. The row can be
  flipped to the hermes shape after the canary, together with that surface
  entry and an explicit alias.

## How `claim_job` picks the route up (`_join_native_runtime_binding`)

At `AttemptRegistry.claim_job` (control_plane/executive_runtime.py,
`_join_native_runtime_binding`), the claimed route's EFFECTIVE adapter id is
read from the worker's capacity quota-class `metadata.adapter_id`, falling
back to the admitted route descriptor resolved from the worker's provider
alias. When that effective adapter id resolves to the registered t3-native
descriptor, the claim-time `ExecutionBinding` is stamped with
`runtime_kind="t3-native"` and `operation_key=derive_t3_client_request_id(binding)`
(the sha256 over adapter id + child identity triple + admitted request
digest), with `caller_namespace` deliberately left empty (C3 finding 6: the
claim transaction holds Executive worker/lease identity, not the OAuth
credential; the port attests the real principal at launch).

So with this row in place, TWO worker shapes reach the t3-native launch
path:

1. **quota-class metadata** (the shape this lane tested end to end): a
   worker registered with `worker_type: "t3-native"` and a quota class
   carrying `metadata: {"adapter_id": "t3-native"}` — effective adapter id
   from capacity metadata.
2. **route-descriptor fallback** (this row's contribution): a worker whose
   `provider` alias is `t3` and whose quota class carries no `adapter_id` —
   effective adapter id falls back to the provider row's
   `adapter_id: "t3-native"` above.

Either way the supervisor owner composed by
`compose_t3_native_supervisor_owners` (keyed by the registered
`worker_id` with `worker_type == "t3-native"`) launches the claim through
`T3ExecutionAdapter.start`, and the supervisor persists the pre-ACK
`WorkerRecoveryBinding` exactly as for other adapters.

## Capability / quota class

The capacity quota class for the canary worker:

```json
"quota_classes": {
  "default": {
    "capabilities": ["code"],
    "metadata": {"adapter_id": "t3-native"}
  }
}
```

`provider` for the canary worker registration: `t3` (matching the proposed
provider alias, so the route-descriptor fallback also resolves). Job
constraints stay profile-less (no `execution_profile_id`): a claimed
profile-less job takes the supervisor's historical early-return path in
`_validate_execution_profile`, which is how the supervisor test drives the
adapter without a sealed execution profile. Binding a real
`execution_profile_id` requires the `_ADAPTER_EXECUTION_SURFACES` entry and
an alias row — deferred with the alias, above.

## Well-formedness proof (test, live file untouched)

`tests/test_t3_native_composition.py::test_route_row_proposal_loads_through_\
the_real_router` copies the live file to a temp path, inserts this row
verbatim under `providers`, and loads it through the real
`ModelRouter.load()`. The live file is never written.

## Remaining live steps (beyond this lane's source-only work)

1. Apply the row through the protected-change path for
   `config/executive_worker_routes.json`.
2. Enroll the token file on the installed Executive host and set
   `MASTERMIND_T3_MCP_ACCESS_TOKEN_FILE` in the service environment (the
   composition reads only the path; the token never enters the environment
   value, logs, or source).
3. Register the canary worker (`worker_type: "t3-native"`, quota class
   above) in the installed Runtime; `compose_t3_native_owners_for_service`
   then composes its supervisor owner at service start.
4. Run the canary job through the composed path on the installed Executive;
   verify the pre-ACK binding lands in `launch_metadata` and a simulated
   crash recovers through `reattach` with zero native launches.
5. Only after the canary: flip the row to the hermes shape (enabled +
   scoped arming), add the `_ADAPTER_EXECUTION_SURFACES` entry and a
   `worker_eligible` alias — separate reviewed changes, not this row.
