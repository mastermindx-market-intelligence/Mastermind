# Director C shared-path proposals (Director A coordination) — 2026-11-09

Director C owns the shared Executive/Capacity path (`executive_runtime.py`
claim seam, `worker_adapter.py` descriptors, `workspace_lease.py`). The files
below are **Director A's exclusive scope** (`control_plane/t3_execution_adapter.py`,
`integrations/t3/**`, `dsh_acp_runtime.py`): this file carries PROPOSALS ONLY.
Nothing here edits, moves, or takes over their seam; no proposal is applied by
this lane.

## Landed on the shared path (context for the proposals)

Commit on `t3/executive-capacity-fleet-integration` (Director C lane):

- `control_plane/executive_runtime.py` — `_join_native_runtime_binding`:
  `AttemptRegistry.claim_job` now joins ExecutionBinding **v1.1** fields at the
  claim seam when the route's effective adapter id resolves to the registered
  `t3-native` descriptor: `runtime_kind="t3-native"`,
  `operation_key = derive_t3_client_request_id(binding)` (the T3
  `clientRequestId`), `caller_namespace = T3_REQUEST_NAMESPACE` — all derived
  from the SAME issued binding inside the SAME claim transaction, so the
  adapter's later derivation reproduces the persisted key byte for byte.
  Unknown/unimplemented adapter ids fail CLOSED with a typed `StateConflict`
  (commitment rolls back, Job stays QUEUED). Non-t3 routes stay plain v1.
- `control_plane/workspace_lease.py` — `attach_workspace_lease(binding, record)`:
  stamps the binding's v1.1 workspace-containment block (`workspace_ref`,
  `base_ref`, `writer_epoch`, `lease_ref`) from one REAL lease record; refuses
  non-active leases. `t3_workspace_id` stays the lease-side native join field,
  reached through `binding.lease_ref`.

## Proposal C-P1 — verify the join at launch (t3_execution_adapter.py)

`T3ExecutionAdapter.start_worker` derives `client_request_id =
derive_t3_client_request_id(binding)`. Proposed addition: when the current
binding is a v1.1 t3 binding (`binding.runtime_kind == "t3-native"`), refuse
with a typed error if

- `binding.operation_key != derive_t3_client_request_id(binding)`, or
- `binding.caller_namespace != T3_REQUEST_NAMESPACE`.

Rationale: closes "binding claims t3 identity but the adapter launches under a
different (namespace, key)". Today the adapter derives the key independently,
so a drifted binding would launch a NEW upstream identity while the broker
believes the old one is bound. Suggested test: claim through
`claim_job` with a t3 route, hand-corrupt `operation_key`, expect the typed
refusal; uncorrupted claim → launch proceeds with the SAME key.

## Proposal C-P2 — launch containment against the leased workspace

When the binding carries a workspace join (`binding.lease_ref` set via
`attach_workspace_lease`), the launch envelope's `workspace_ref`
(`str(spec.workspace_path)`) should be checked to resolve inside
`binding.workspace_ref`'s containment (exact match or a documented child path),
refusing typed on drift. Rationale: makes the Rev 5 §4 containment enforceable
at the only place the native workspace is actually chosen (A's seam).

## Proposal C-P3 — persist `t3_workspace_id` when the native workspace exists

`WorkspaceLeaseRecord.t3_workspace_id` is the nullable native join field; this
lease-side field should be filled by the T3 workspace lifecycle at real
workspace creation (acquire-time or a bounded fill API on
`WorkspaceLeaseStore`), never fabricated by the lease module. The broker-side
link is `binding.lease_ref == lease.lease_id`; consider recording the
`binding.lease_ref` in the launch intent for the reverse lookup.

## Contract tests already proving the shared side

`tests/test_executive_claim_job_placement_authority.py` (23 passed — 19
pre-existing + the 4 below; an earlier draft of this note said "35", which
was this file plus `tests/test_workspace_lease.py` (12) in one invocation):

- `test_t3_native_claim_issues_v1_1_binding_with_t3_idempotency_join`
- `test_plain_adapter_route_stays_a_v1_binding`
- `test_unknown_route_adapter_fails_closed_inside_the_claim_transaction`
- `test_workspace_lease_join_stamps_containment_by_contract`

All use real SQLite stores in temp dirs; no live launch anywhere.
