# Lane: Executive E2E admission → t3-native launch → return wiring — Director C2 (2026-11-09)

Branch `t3/executive-e2e-return-wiring`, created from `70dabba15` (merged head
of `t3/t3-hermes-restart-recovery`). Director C2 (successor of Director C on
the Executive shared path), reporting to the Fable COO principal. Mission:
T3_HANDOFF_V2 DONE_WHEN 2 + 5, source side. All work confined to this
isolated worktree; no push, no PR, no master write, nothing under `~/.hermes`
edited, no daemon, no port. Read-only on `control_plane/t3_execution_adapter.py`
(Director A3's rework), `config/executive_worker_routes.json`,
`control_plane/worker_adapter.py` descriptors.

## Deliverables

1. `tests/test_mmos_admission_to_t3_native_e2e.py` — **16 tests**, the E2E
   fake-port proof driving the REAL Executive runtime (real SQLite in tmp)
   and the REAL t3 adapter public API; only the native port, the return
   transport and the GitHub evidence port are in-memory fakes.
2. `control_plane/child_execution_contracts.py` — v1.2 sparse
   `original_requester` block (Director F gap 1), digest-compatible.
3. `control_plane/execution_return_wiring.py` — post-seal return wiring
   (Director F gap 2): sealed facts + T3 ledger entry + bounded GitHub
   evidence → `project_execution_return` → `HermesExecutionReturnDeliverer`
   → durable receipt as an events row (no new table).
4. `control_plane/github_attempt_evidence_reader.py` — read-only, injectable,
   unknown-safe GitHub evidence reader (Director F gap 3).
5. `control_plane/child_request_execution_composition.py` — the SMALLEST
   honest bridge over the missing runtime seam (see below).
6. `control_plane/executive_runtime.py` — 3 hunks, all outside PR #2177's
   protected hunks (proof below).
7. This ledger.

## What was missing in the runtime (recorded, not papered over)

`JobRegistry.admit_child_execution_request` admits an idempotent child
request and creates an **admission-ledger** Job (constraints
`{"required_capabilities": ["read"]}` — a record of WHO ASKED). The placement
authority (`AttemptRegistry.claim_job` with placement observations, fabric
placement intent, and C's v1.1 native binding join) composes ONLY with a Job
carrying a `child_placement` constraint spec. **No runtime seam turns an
admitted child request into that placement Job** — the two lanes are
deliberately separate in the runtime today.

`child_request_execution_composition.py` is the smallest honest bridge:
admit through the real idempotent admission API, then create the placement
Job under a deterministic `child-placement:<sha256(triple)>` command id
(the events table's UNIQUE command_id arbitrates concurrency atomically —
exactly one placement Job per triple can ever exist). Nothing in it changes
claim, placement, binding or seal law. The E2E proof uses this composition
and says so in its docstring.

## E2E assertion ledger (all PROVEN_BY_TEST)

Module: `tests/test_mmos_admission_to_t3_native_e2e.py` — **16 passed**
(`env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q
tests/test_mmos_admission_to_t3_native_e2e.py`).

| # | Test | Proves |
|---|---|---|
| 1 | `test_e2e_admission_to_t3_native_launch_seal_and_return` | Full path: Model Router (real policy, eligible alias for C1 implementation) → admission ADMITTED with v1.2 block persisted on the admission Job's JOB_CREATED provenance → placement claim (C's v1.1 join: `runtime_kind=t3-native`, `caller_namespace=T3_REQUEST_NAMESPACE`, `operation_key == derive_t3_client_request_id(binding)`) → **exactly ONE native launch**; envelope `client_request_id == binding.operation_key` verbatim and envelope namespace carries the binding's caller namespace as its principal suffix → collect → seal → return **delivered once** to the ORIGINAL conversation (`conv-7`), record `mastermind.execution_return/v1`, `acceptance=not_accepted` (delivery ≠ acceptance), `stage=checks_green` (open PR, all checks concluded, `merge_state=not_merged`), `t3_thread_id` from the adapter's ledger, 64-hex `seal_digest`; ONE `EXECUTION_RETURN_DELIVERY` events row; adapter ledgered the result reference BEFORE company acceptance; `_normalized_schema_digest` **unchanged** after the receipt row exists. |
| 2 | `test_nm14_replayed_handoff_never_mints_a_second_job_or_launch` | NM-14: replayed handoff → admission REPLAY (same job id), `placement_created=False`, same placement Job, `ready_to_claim=False` (sealed — never claims/launches again); still exactly one admission/placement JOB_CREATED event each, `launch_count==1`, one transport send. |
| 3 | `test_nm14_different_digest_same_triple_is_typed_conflict` | NM-14: same idempotency triple, different brief digest → typed `StateConflict` matching `CHILD_REQUEST_DIGEST_CONFLICT`; no second Job of either kind minted. |
| 4 | `test_nm14_concurrent_composition_is_atomic_one_job` | NM-14: two threads composing the same handoff behind a barrier → no errors, exactly one placement Job, one admission Job, states `[ADMITTED, REPLAY]` (loser reconciled, no retry). |
| 5 | `test_no_admission_no_launch_adapter_fails_closed` | Without an Executive claim the adapter fails closed (`no current broker ExecutionBinding`) and `launch_count==0`. |
| 6 | `test_no_admission_shell_launch_refused_without_binding` | Armed shell path without `POOL_EXECUTION_BINDING` → deny "missing binding"; nothing launches. |
| 7 | `test_nm07_admission_ui_timeout_receipt_lookup_no_duplicate` | NM-07: admission succeeded, reply lost → receipt lookup by deterministic `admission_command_id` recovers the SAME Job; retry → REPLAY, same handles; exactly 2 Job rows total (admission + placement), admission Job `attempt_count==0` (it is the ledger, not the unit of placement). |
| 8 | `test_nm15_shell_shapes_refused_with_a_valid_claimed_binding` (3 params) | NM-15: #2329 shapes — interpreter one-liner carrying the wrapper, whitespace/case-normalized variant, computed command word — all denied **structurally** ("unobservable launch"/"unaccounted descendant") even with a REAL binding claimed through the placement authority projected in env: structural refusal precedes binding law. |
| 9 | `test_nm15_lawful_direct_shape_reaches_the_binding_gate` | Precedence proof: the direct wrapper shape is NOT structurally refused — it proceeds into binding law (see the recorded guard gap below). |
| 10 | `test_v1_and_v1_1_digest_pins_survive_the_v1_2_extension` | v1 pin `5832f479…37413` and v1.1 fixture pin `ab61aae3…7b1da9` byte-identical; absent v1.2 block not even serialized; v1.1 schema label preserved. |
| 11 | `test_v1_2_block_participates_in_digest_and_labels_the_schema` | Present block changes the digest, labels schema `ChildExecutionRequest.v1.2`, round-trips through to_dict/from_dict; requester swap under the same triple is a conflict (`is_idempotency_conflict`), never a retry. |
| 12 | `test_v1_2_missing_required_requester_field_is_refused` | Blank `teammate_id` / `carrier_kind` refuse at construction. |
| 13 | `test_unknown_github_evidence_keeps_the_stage_honest` | No PR evidence observed → `pr_number=None`, `checks=None`, `merge_state=unknown`, stage stops at `branch_pushed`; never claims checks or merge. |
| 14 | `test_delivery_failure_records_honest_refused_receipt` | Transport raises → seal still COMPLETED; exactly one send, one refused receipt (`TRANSPORT_REFUSED`); re-invoking the seam short-circuits on the durable receipt — no retry loop, transport count stays 1. |

(Parametrized tests counted once each in the narrative; the module reports
16 passed total.)

## PR #2177 non-overlap proof (Director C's method, reproduced)

`control_plane/executive_runtime.py` was edited in exactly **3 hunks**,
all outside PR #2177's protected hunks:

1. `admit_child_execution_request` provenance block (~l.16864): persist the
   v1.2 `original_requester` block on the admission Job's JOB_CREATED
   provenance (outside the `child_request` schema fields — a provenance
   record, never a schema change).
2. `AttemptRegistry.__init__` (~l.18981): `self._execution_return_seam = None`
   (the optional seam holder).
3. `AttemptRegistry._terminal` post-commit (~l.19150): after the seal is
   durably committed, invoke the seam if installed, fenced by try/except
   (last resort only — the seam itself never raises).

Checker: `/tmp/check_2177_overlap.py` (committed copy:
`integrations/mmos/fixtures/` is NOT used; the checker is reproduced by the
method below). The #2177 API record is gone from GitHub, so the diff is
reconstructed from the surviving pull refs — base `5c3d38852`, head
`70a6cf453` — yielding **62 hunks**, matching Director C's recorded count.
The checker diffs the lane base `70dabba15` against the working tree and:

- A. every #2177 old-hunk byte block present in the lane BASE file is still
  present verbatim in HEAD (`missing_head ⊆ missing_base`);
- B. no old-file byte range this lane removed/replaced intersects any #2177
  old-hunk byte block located in the lane BASE file.

Result at the lane working tree (re-run at the committed HEAD below):

```
#2177 protected hunks in control_plane/executive_runtime.py: 62
lane hunks in control_plane/executive_runtime.py (base vs working tree): 3
#2177 blocks absent from lane BASE (pre-existing history, not this lane): [5, 30, 32]
#2177 blocks absent from lane HEAD: [5, 30, 32]
protected blocks destroyed BY THIS LANE: none
RESULT: PASS
```

Blocks [5, 30, 32] were ALREADY absent at the lane base `70dabba15`
(pre-existing history between the #2177 head and this lane's base — not this
lane's doing; `missing_head == missing_base`).

## Schema digest proof (no new table)

The delivery receipt is an events ROW (`event_type =
EXECUTION_RETURN_DELIVERY`, `command_id = execution-return:{attempt_id}`,
UNIQUE-enforced), not a schema change. `_normalized_schema_digest` hashes
`sqlite_master` DDL only, and test 1 asserts it INSIDE the same runtime
whose events table now carries the receipt row:

```
_normalized_schema_digest(connection) == _NORMALIZED_V7_SCHEMA_DIGEST
# 7692d62bd4126dd6fcaec2873ee9506a1faac96b3246684366e1dfa6e34c6a87
```

## v1.2 digest-compatibility proof

- v1 digest pin: `5832f479ded965053bf96f395735e1cb8ee33882b4a5e1a4c7ce9c8bbc237413`
  — unchanged by the extension (`tests/test_rev5_contracts_v1_1.py` pin,
  re-asserted in the E2E module).
- v1.1 fixture digest pin:
  `ab61aae30704e1366dd77bd8c40ed59409234b6df4efa4592fac4625137b1da9` —
  unchanged.
- v1.2 block is sparse-all-or-nothing per the established law: absent →
  omitted from serialization AND digest; present → participates (a requester
  swap under one triple is a CHILD_REQUEST_DIGEST_CONFLICT, correct, because
  the requester selects the return destination).
- Provenance `child_request` schema label stays `ChildExecutionRequest.v1`
  (`child_request_of`/`ready_counts` SQL filters depend on it); the v1.2
  label lives only on the request object and its own round-trip.

## Recorded finding — guard v1/v1.1 schema gap (fail-closed; NOT patched here)

The runtime's C v1.1 join labels a claimed t3-native binding
`ExecutionBinding.v1.1` (the `operation_key`/`caller_namespace` extension
fields are set). The shared-placement guard's restated binding law
(`_binding_problems`, stdlib-only by design) accepts ONLY the
`ExecutionBinding.v1` schema label, so a REAL claimed t3-native binding
projected into `POOL_EXECUTION_BINDING` is refused at the binding gate with
"schema must be ExecutionBinding.v1". This is fail-closed (no hole), but it
means an armed lawful session cannot currently present a v1.1 binding to the
guard. Fixing it means widening the guard's acceptance set — the guard
owner's call (WO-11 r5 lane), deliberately not done in this lane. E2E test 9
documents the precedence and this exact refusal.

## PROVEN_BY_TEST vs SOURCE_ONLY

- PROVEN_BY_TEST: everything in the assertion ledger above — against the
  real runtime, real adapter public API, real contracts, real projection
  and real deliverer classes; fake port/transport/gh only.
- SOURCE_ONLY (composition awaiting runtime owner): the
  admit→placement-bridge (`child_request_execution_composition.py`) is a
  lane module, not a runtime seam; if the runtime owner later builds a
  native bridge, the composition module retires and the E2E swaps its
  helper — the assertions do not change.
- SOURCE_ONLY (delivery beyond the fake): the return wiring's real-path
  proof needs a real T3 port, a real Secretary native transport and a real
  gh CLI receipt channel (below).

## Verification commands and counts

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_mmos_admission_to_t3_native_e2e.py
# 16 passed

env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_child_execution_contracts.py tests/test_rev5_contracts_v1_1.py
# 103 passed (digest pins re-proven after the v1.2 extension)

# Union (mission list + every test file matching
# `grep -rl 'claim_job\|complete_attempt' tests/`, 77 files):
# UNION_COUNT_PLACEHOLDER

/opt/homebrew/bin/python3.12 /tmp/check_2177_overlap.py $(cat /tmp/lane_base_sha)
# RESULT: PASS (above)
```

## Gaps remaining for live proof

1. **Real T3 port**: the E2E proves envelope identity against
   CountingT3Port-derived fakes; a live proof needs the real native client
   behind T3NativeClientPort (Director A3's rework owns that seam).
2. **Real Secretary transport**: the deliverer ran over an in-memory
   transport; live proof needs SecretaryNativeSendTransport + a real
   HermesNativeSession, with the receipt's `transport_ref` read back.
3. **Real gh CLI receipt channel**: GitHub evidence ran over a fake port;
   live proof needs `gh pr view`/`gh pr checks` against the real repository
   (the reader's GhCliEvidencePort is ready; tests never touch the network).
4. **Guard v1.1 acceptance** (recorded finding above) — guard owner's lane.
5. **Runtime-native admit→placement bridge** (recorded above) — runtime
   owner's call; the composition module is the interim honest bridge.


> Integrator note (Fable): the 77-file union run was NOT completed inside the lane (turn ended mid-run); counts above are the lane's focused suites. The integrator re-runs the union on the merged build head.
