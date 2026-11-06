# H24-08 — physical Fabric lane health

## Scope and source identity

This packet implements a pure, ephemeral readiness join for a contemplated
Hermes child. It has no acquisition callback, host/API probe, clock read,
reservation, provider call, controller, retry loop, scheduler, health store,
credential access, or Runtime mutation. Its output is evidence for the existing
admission owner, not an admission receipt.

- Immutable implementation base: `b54cb10e4abdd3766c62d4088f6a576ecfe80437`.
- Isolated branch: `sol/h24-08-fabric-health-20261106`.
- Procedure pin: protected Mastermind `master` at
  `88a8b103a5a69e4b4e870a184655dde9fd5875c3`; Skillpack schema
  `mastermind.sol_skillpack.v1`, version `1.0.1`, bootstrap major `1`.
- Owned changes: `control_plane/hermes_admission_health.py`,
  `tests/test_h24_hermes_admission_health.py`, and this document, all new.
- H24-01/H24-05 wave seals are not source-build prerequisites under the current
  concurrent placement instruction. No sibling implementation is imported.
- PR #2120 integration paths, C29–C34, capacity probes, worker/slot control,
  Runtime, host registries, provider pools, and ModelRouter remain read-only.

**Supported positive path:** the existing Linux native host snapshot V2 and
native provider-capacity V2. At this base, `native_capacity_v2` permits MiniMax
only. The module does not silently extend that contract to other providers or
convert Darwin V1 counters, GLM's `provider_readiness=UNKNOWN`, or Hermes role
metadata into native ready capacity. Unsupported evidence refuses. This is a
source-level composition seam; no installed acquisition producer or live
Hermes selected-child execution is claimed.

## Consumer and trust boundary

Call `compose_admission_health(expected=..., observations=..., now_ms=...,
now_monotonic_ms=..., reader_generation=..., policy=HealthPolicy(...))` from an
already authorized, trusted composition owner. There is no default production
policy. `expected` must be obtained independently from the current registration,
Runtime, physical realm, source, and process owners. It must never be copied from
the candidate observation merely to make equality checks pass.

Every observation is a closed envelope with exactly these fields:

```python
{
    "owner": "executive_host_capacity",  # exact owner for this input
    "source_verified": True,            # acquisition owner's attestation
    "reader_generation": "opaque-current-reader-process-epoch",
    "observed_at_ms": 1793956800000,     # reader acquisition UTC milliseconds
    "observed_monotonic_ms": 50000,     # same reader's monotonic milliseconds
    "expires_at_ms": 1793956815000,
    "value": owner_observation,
}
```

These are **in-process injected facts**, not public admission assertions.
`source_verified=True`, a schema, a digest, and matching identifiers cannot
authenticate arbitrary caller-supplied JSON. Authentication, root custody,
physical enrollment, nonce validation, and source acquisition remain with the
existing owners. No callable acquisition adapter is accepted, so composition
cannot invoke one accidentally. Missing input is `None`, never an empty success
object, zero measurement, or optimistic default.

The acquiring reader supplies both clocks and its restart-unique generation.
Remote-host monotonic values must never be compared with the controller's
monotonic clock. Receipt freshness does not replace original source freshness:
the host sampling window, Worker/quota `last_seen_at`, worker observation expiry,
and each provider health/cooling/quota timestamp are checked independently.

`expected` contains exactly:

| Group | Fields |
|---|---|
| Runtime lineage / original effect | `root_job_id`, `job_id`, `worker_id`, `quota_class`, `quota_fence_generation`, nullable `original_attempt_id`, paired nullable `original_broker_operation` / `original_request_sha256` |
| Physical lane | `provider`, `slot_id`, `lane_id`, `credential_scope_sha256`, `process_generation`, `process_identity_sha256` |
| Host owner binding | `host_binding`: `host_ref`, `boot_ref`, `capacity_pool_ref`, `source_generation_sha256`, `execution_scope_sha256`, `namespace_sha256`, `ancestry_sha256` |
| Worker source | Exact `worker_source_config` and V2 `capacity_join`; computed source-config digest must equal the join digest |
| Provider source | Exact V2 `provider_source`, `producer_sha256`, `realm_generation`, `enrollment_receipt_digest` |

The physical credential reference is an opaque, secret-free owner identity. No
credential bytes, credential paths, account login, or API keys are input fields.
Different credentials and realm generations remain separate even when provider
and model labels match. The enrollment digest and physical reference must come
from the same current owner-bound realm; H24-08 cannot establish that relationship
by inspecting secrets.

## Input-to-owner mapping

| Input / exact envelope owner | Existing source at the immutable base | Facts and freshness used |
|---|---|---|
| `host` / `executive_host_capacity` | `validate_native_host_capacity_snapshot`, `project_native_host_capacity` in `control_plane/executive_host_capacity.py`; capture remains in the existing host owner | All seven host/scope bindings, `observed_at_ms`, `total_observation_window_ms`, explicit metric/null pairs, `telemetry_status`, `unknown_fields` |
| `worker_capacity` / `worker_capacity_observer` | `validate_worker_capacity_observation` in `control_plane/executive_capacity_observation.py`; source-config validators in `executive_capacity_observation_producer.py`; actual acquisition in `ops/executive_os/worker_capacity_observer.py` | Host/capability/source-config digest; realm/credential metadata, binary attestation, broker-generation readiness; `observed_at`/`expires_at`, original fixed 15-second lifetime |
| `provider` / `native_capacity_acquisition` | `NativeCapacitySource` in `control_plane/native_capacity_acquisition.py` remains acquisition owner; H24 calls only `validate_snapshot`, `validate_join`, and `known_admissible` from `native_capacity_v2.py` | Exact source/registration/producer pins, boot/capability/realm generations and enrollment digest, provider health, every quota horizon, cooling and last outcome; no row-to-row fact borrowing |
| `runtime` / `executive_runtime` | `WorkerRegistry.get_worker/get_quota_class`, Job/Attempt registries and immutable record fields in `control_plane/executive_runtime.py` | Existing root/current Job, Worker and quota identity/status, `last_seen_at`, held Job/Attempt, quota fence, metadata capacity join, original Attempt |
| `slot` / `slot` | Existing Slot/local semaphore and cluster lease broker; source snapshot in `ops/native_fabric/quota_continuity/source/slot.py`; `provider_worker_slots.py` is static realm inventory only | Exact lane/slot/worker/host/boot/physical credential/process identity, liveness, occupancy, complete owner-observed available count and held Attempt; envelope TTL bounds this read |
| `transport` / `remote_worker_transport` | `TransportEffect` and request/response identity owner in `control_plane/remote_worker_transport.py`; broker composition remains in `executive_fabric_composition.py` | Exact host/worker/Job/Attempt, pre-submit vs submitted/controller/worker phase, outcome, `no_effect` vs `effect_unknown`; envelope TTL bounds the owner-derived projection |

Host and provider validation stays with its existing implementation. The Runtime,
Slot, and transport fragments below are explicit bounded projections of owner
reads, not new persistent schemas, alternate registries, or proof that producers
for these projections have been installed.

### Runtime fragment

`value` has exactly `root`, `job`, `worker`, `quota`, `attempt`.

- `root` and `job`: `job_id`, `root_job_id`, `status`, `current_attempt_id`.
  A missing root/Job is a blocker. Root state may be `QUEUED`, `RUNNING`, or
  `CHECKPOINTED`; only a `QUEUED` child without an original Attempt can qualify
  as a new candidate. A running/lost/finished child with a missing Attempt is a
  reconciliation gap, not unattempted work.
- `worker`: `worker_id`, `provider`, `status`, `last_seen_at`, `active_job_id`.
- `quota`: those Worker fields plus `quota_class`, `active_attempt_id`,
  `fence_generation`, `capacity_join` copied from the owner's quota metadata.
  Both Worker and quota must be `AVAILABLE` and unoccupied. Each original
  `last_seen_at` must independently be current.
- `attempt`: `None` for owner-proven unattempted work, otherwise exactly
  `attempt_id`, `job_id`, `worker_id`, `quota_class`, `status`, `fence_generation`.
  Any original Attempt, including terminal/LOST, routes to original
  reconciliation. This module never decides that a retry is safe.

### Slot and transport fragments

Slot fields are `slot_id`, `lane_id`, `worker_id`, `provider`, `host_ref`,
`boot_ref`, `credential_scope_sha256`, `process_generation`,
`process_identity_sha256`, `process_alive`, `state`, `owner_attempt_id`,
`host_occupied`, `available_count`. `free` is an explicit owner-qualified result
after the existing local/cluster ownership checks; absence of a lease row or
static catalog membership alone must not manufacture it. Other projected states
are `held`, `rented`, `lost`, `unknown`. Unknown liveness/count/occupancy remains
unknown. A live lane/broker process is not a started child.

Transport fields are `host_ref`, `worker_id`, `job_id`, `attempt_id`, `phase`,
`outcome`, `effect`, `broker_operation`, `request_sha256`. The operation name is
validated by the incumbent transport validator; the digest must bind that
owner's entire original validated request, including its `operation_id`. A
different status read or submit digest cannot replace the original effect.
The only potentially eligible combination is a current
`PRE_SUBMIT`/`ready`/`no_effect` result with no Attempt or original request. `SUBMITTED`,
`CONTROLLER_CREATED`, `WORKER_STARTED`, `UNKNOWN`, any original Attempt, or an
uncertain effect requires original reconciliation. A controller PID, successful
transport envelope, role-status read, or `ok` response does not establish worker
START. `error`, `refused`, `unavailable`, and `unknown` never become success.

## Policy table

All thresholds below are required `HealthPolicy` inputs from the actual admission
owner. The test values are synthetic and are not production defaults.

| Check | Conservative policy |
|---|---|
| Observation age | `1 <= max_age_ms <= 15000`; use the oldest host sampling instant, not just the last sample |
| Epoch / clock | Exact reader generation, host boot/source/scope, worker source digest, broker generation, capability/realm generation and process identity; monotonic age must be nonnegative and agree with wall age within 2 seconds |
| Source times | No future source timestamp and no use at or after expiry; original-owner validators are also applied |
| CPU capacity | `effective_cpu_capacity_millicores >= min_cpu_capacity_millicores`; this is a ceiling observation, never a reserved CPU claim |
| CPU pressure | `host_cpu_busy_milli_pct <= max_cpu_busy_milli_pct` and `cpu_some_avg10 <= max_cpu_pressure_milli_pct` |
| Memory | Effective headroom meets `min_memory_headroom_bytes`; both memory `some` and `full` `avg10` pressure meet `max_memory_pressure_milli_pct` |
| Disk / I/O | `disk_usable_bytes >= min_disk_usable_bytes`; I/O `some` and `full` `avg10` pressure meet `max_io_pressure_milli_pct` |
| Partial metrics | Any applicable unknown metric makes host evidence `PARTIAL` and ineligible; explicit `NOT_APPLICABLE` fields remain null |
| Provider | Existing V2 `known_admissible` must pass for the exact joined row, source, boot and realm. All quota horizons must be positive and unexpired; missing quota is unknown |
| Cooling / 429 | Active cooling blocks. Its reset timestamp is not a retry timer or permission to auto-clear the block |
| Occupancy | Worker/quota/slot/host all independently unoccupied; positive count never overrides a collision, dead process, or missing source |
| Concurrent requests | Multiple readers may observe the same free count. Neither decrements it. Only the existing owner's atomic revalidation/reservation can prevent oversubscription |

The decision expiry is the earliest of all envelope deadlines, original source
lifetimes, host-window age, and quota resets, projected onto both the reader's UTC
and monotonic clocks. Blocked/partial decisions have no reusable positive
validity: their expiry is at or before now. Even a still-valid positive result
requires fresh transactional owner revalidation immediately before reservation.

Restart ABA protection depends on independently observed current generations.
Reappearing content A after A→B→A does not make an old reader/broker/process epoch
current. Content digests must not be substituted for restart-unique process
identity. A pure stateless join cannot discover an unobserved restart if its
authority owner reuses every identity; this is why genuine current owner
measurements are required, not a second H24 generation store.

## Output and normalized reasons

The immutable `HealthDecision` returns eligibility, grounded source/code pairs,
source completeness, input-envelope SHA-256 digests, original Attempt reference,
original request digest, and expiry. The digests bind evaluated bytes; they are
not signatures.

| Status | Meaning |
|---|---|
| `READY` | Every required input is valid, current, compatible, and currently unblocked; eligible only to present to the reservation owner |
| `BLOCKED` | At least one definitive blocker is known; other missing sources remain visible |
| `PARTIAL` | Some source evidence exists, but uncertainty, stale evidence, or missing inputs prevents eligibility |
| `UNAVAILABLE` | No usable source set, or the trusted expected binding cannot be validated |

Recovery is `ORIGINAL_RECONCILE` whenever original work/effect is present,
`NEW_CANDIDATE_ELIGIBLE` for a fully qualified new candidate,
`NO_ELIGIBLE_CANDIDATE` for a definite blocker without an original effect, or
`OWNER_EVIDENCE_REQUIRED` for unresolved evidence. These are explanatory action
classes, not Runtime transitions or retry authority. Every rendered result says
`admitted=false`, `reserved=false`, `worker_started=false`,
`retry_authorized=false`, `requires_owner_reservation=true`. These are the effects
and proof limits of this evaluation, not a denial that an original Attempt may
already exist.

| Reason family | Representative normalized codes |
|---|---|
| Missing / malformed / wrong owner | `SOURCE_MISSING`, `SOURCE_VALUE_MISSING`, `SOURCE_UNVERIFIED`, `SOURCE_OWNER_MISMATCH`, `INPUT_INVALID`, `OBSERVATIONS_INVALID`, `OWNER_VALIDATION_REFUSED` |
| Freshness / epoch | `READER_GENERATION_CHANGED`, `MONOTONIC_CLOCK_MISMATCH`, `MONOTONIC_OBSERVATION_EXPIRED`, `OBSERVATION_EXPIRED_OR_FUTURE`, `NATIVE_BINDING_MISMATCH`, `NATIVE_STALE`, `HOST_BOOT_CHANGED` |
| Capacity source / realm | `SOURCE_CONFIG_MISMATCH`, `CAPACITY_SOURCE_MISMATCH`, `CAPACITY_JOIN_MISMATCH`, `PROVIDER_REALM_MISMATCH`, `QUOTA_BINDING_MISMATCH`, plus the incumbent `CAPACITY_OBSERVE_*` / `V2_*` validator reasons |
| Physical pressure | `HOST_METRICS_PARTIAL`, `CPU_CAPACITY_LOW`, `CPU_PRESSURE`, `MEMORY_HEADROOM_LOW`, `MEMORY_PRESSURE`, `DISK_HEADROOM_LOW`, `IO_PRESSURE` |
| Lifecycle / occupancy | `ROOT_MISSING`, `JOB_MISSING`, `ROOT_OR_JOB_NOT_ACTIVE`, `JOB_NOT_UNATTEMPTED`, `WORKER_MISSING`, `QUOTA_MISSING`, `WORKER_NOT_AVAILABLE`, `QUOTA_NOT_AVAILABLE`, `WORKER_OCCUPIED`, `QUOTA_OCCUPIED` |
| Lane / Slot | `SLOT_IDENTITY_MISMATCH`, `SLOT_HOST_BOOT_MISMATCH`, `LANE_HEALTH_UNKNOWN`, `WORKER_PROCESS_DEAD`, `HOST_OCCUPIED`, `SLOT_NOT_FREE`, `AVAILABLE_COUNT_UNKNOWN`, `NO_AVAILABLE_CAPACITY` |
| Provider / cooling | `PROVIDER_COOLING`, `PROVIDER_QUOTA_EXHAUSTED`, `V2_HEALTH_UNQUALIFIED`, `V2_AUTH_UNQUALIFIED`, `V2_COOLING_UNQUALIFIED`, `V2_QUOTA_UNQUALIFIED` |
| Original effects | `ORIGINAL_ATTEMPT_PRESENT`, `ORIGINAL_ATTEMPT_MISSING`, `ORIGINAL_ATTEMPT_RECONCILE`, `ATTEMPT_IDENTITY_MISMATCH`, `ORIGINAL_TRANSPORT_RECONCILE`, `TRANSPORT_EFFECT_UNKNOWN`, `TRANSPORT_NOT_READY`, `TRANSPORT_IDENTITY_MISMATCH`, `TRANSPORT_REQUEST_IDENTITY_MISMATCH` |

No arbitrary exception message is projected. Unknown built-in owner-validation
errors become `OWNER_VALIDATION_REFUSED`. Unsupported schemas retain their
owner's refusal rather than acquiring a permissive fallback.

## Validation and genuine measurements still needed

The self-contained `unittest` suite uses synthetic owner fixtures and existing
pure builders/validators. It needs no package installation. Exact command:

```sh
PYTHONPATH=. python -m unittest discover -s tests -p test_h24_hermes_admission_health.py
python -m py_compile control_plane/hermes_admission_health.py tests/test_h24_hermes_admission_health.py
```

Qualification on Python 3.12.14: **59 tests passed**, including 25 named chaos
vectors and 1,685 nested malformed-input cases; both modules compiled successfully.
This is focused local source qualification. No hosted CI, installed-source
qualification, or live host/provider measurement is asserted by that result.

The suite covers the positive path, every packet chaos condition, raw-source
freshness despite refreshed receipt envelopes, incorrect provider/physical
realms, boot/process/reader ABA, vanished roots, original Attempt loss, pressure,
cooling, unknown transport after submission, controller-created vs START,
partial/unavailable distinctions, concurrent reads against one free count, and
closed nested types. It also replaces filesystem, socket, subprocess, SQLite,
wall-clock and monotonic-clock entry points with traps during evaluation and
verifies the caller's inputs remain unchanged. The named chaos table lives in
the owned test file; no extra fixture path is needed.

Before any actual consumer could claim active capacity, its existing owner must
supply fresh authenticated Runtime root/Job/quota/Attempt reads, the live
host/boot/source/scope sampling window and pressure/headroom, the exact lane and
process generation/liveness, current physical-credential/realm enrollment,
current provider quota/health/cooling facts, and the original transport outcome.
It must then perform its existing atomic reservation and admission. H24-02 may
consume this same normalized result without gaining reservation authority.

This packet does not provide those live measurements, install a producer, repair
or activate C29/C30, or prove any host/worker START. No merge, self-approval,
credential operation, service installation, or production-serving claim occurs.

## Parent checkpoint contract

Return this branch's exact head and base, the three-file owned diff checksum,
exact commands/results, and the remaining live-measurement boundary. The checksum
is SHA-256 over the UTF-8 full-index binary Git diff for these three added paths,
in Git path order. The files are published through the isolated GitHub branch
with an expected-base ref update and committed-byte readback. The final return
binds the observed head; this document avoids a self-referential commit/checksum.

The parent may inspect/integrate this source through its own current authority.
No source-only result changes protected release or execution ownership.
