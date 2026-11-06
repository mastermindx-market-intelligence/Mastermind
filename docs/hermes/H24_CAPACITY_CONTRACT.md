# H24-02: Hermes capacity decision owner-call contract

## Scope and ownership

This is a source-only, pure projection for one already selected Hermes child.
It composes incumbent ModelRouter suitability, Runtime identities, qualified
Capacity facts, physical policy and Placement selection. It does not acquire
capacity, rank models, choose another provider/account, reserve a lane, commit a
placement, insert an Attempt or start a Worker.

- Implementation base: `b54cb10e4abdd3766c62d4088f6a576ecfe80437`.
- Branch: `sol/h24-02-capacity-policy-20261106`.
- Owned new files: `control_plane/hermes_capacity_decision.py`,
  `tests/test_hermes_capacity_decision.py`, and this document.
- Existing router, Runtime, Capacity, Placement, host registries, provider
  configuration, PR #2120 integration paths and C29–C34 owner files are unchanged.

The authority hierarchy remains the incumbent
[Executive COO hierarchy](../EXECUTIVE_COO_HIERARCHY.md). The Executive owner
retains final claim and commitment. `CANDIDATE` is an offline decision about the
supplied observations, **not admitted capacity or actual Worker START**.

## Exact callable

```python
from control_plane.hermes_capacity_decision import (
    HermesCapacityDecision, HermesCapacityRequest, decide_hermes_capacity,
)
from control_plane.model_router import ModelRouter

def decide_hermes_capacity(
    request: HermesCapacityRequest, *, router: ModelRouter,
) -> HermesCapacityDecision: ...

decision = decide_hermes_capacity(request, router=current_preloaded_router)
wire = decision.to_dict()
```

The function receives a current, preloaded incumbent router. It never calls
`ModelRouter.load`, reads a clock, opens a store, samples a host, or calls a
provider. `now_ms` is explicitly supplied trusted UTC milliseconds. Repeating a
call with unchanged inputs yields identical canonical JSON and decision SHA-256.
`to_dict()` returns a fresh defensive copy; the decision retains immutable JSON.

All adapter records are frozen, slotted dataclasses. Enum values and record
types are closed. Existing incumbent record types are reused rather than
redefined. Nested owner dictionaries remain caller-owned snapshots: callers must
not mutate them or the injected router during a call. The adapter does not write
to them. Concurrent readers of one stable snapshot are supported; this does not
serialize concurrent owner writes or reserve shared capacity.

### Request fields

| Field | Exact type / responsibility |
| --- | --- |
| `requirements` | `TaskRequirements(work: WorkRequest, requires_tools: bool, requires_vision: bool, context_tokens: int, required_profile_capabilities: frozenset[str] = frozenset())` |
| `suitability` | Current incumbent `RoutingDecision`; must equal `router.route(requirements.work)` and be a Worker route. |
| `origin` | `OriginalSelection(expected: ExpectedChildSelection, child: Job, planner_job: Job, original_attempt: Attempt \| None, admitted_plan_identity: dict[str, str])`. The dictionary has exactly `plan_attempt_id` and `plan_digest`. |
| `responsibility` | Existing Agent OS `ResponsibilityFact`, naming the same original root. Existing Placement rules enforce current source and waiting-capacity state. |
| `root_work_placement_union` | Tuple of existing approved placement-union member dictionaries. |
| `inherited_work_placement_union` | Tuple narrowed through the actual hierarchy. Each member must belong to the root union and any union retained in the child. |
| `selected_placement` | Exactly `provider_realm`, `quota_class`, and optionally `model`. This is one incumbent-selected member, not a request to search all pools. |
| `demand` | Existing `PlacementDemand`, with the same selected provider/quota and all incumbent required capabilities. |
| `candidates` | Tuple of `CandidateInputs`, bounded by incumbent `MAX_CANDIDATES` (three at this base). Duplicate Worker identities refuse the call. An empty tuple returns `UNAVAILABLE`. |
| `now_ms` | Positive integer supplied by the trusted owner. Booleans are not integers here. |
| `evaluation_mode` | `EvaluationMode.OWNER_QUALIFIED` by default. `EvaluationMode.FIXTURE_ONLY` must be explicit and accepts only synthetic physical policy. A string is not an enum value. |

`OriginalSelection.original_attempt` is the retained, completed **planner
Attempt** named by the admitted plan. It is not a fabricated prospective child
Attempt. Its planner Job must also be completed and retain that Attempt. The
child must be queued, have role `work` or `repair`, and have no current Attempt.
The original root, immediate parent, plan digest/step, repair round, next ordinal
and original dispatch command are checked by the incumbent selected-child
validator. Existing child effects must be reobserved through their original
command instead of entering a new-candidate path.

Child task kind, risk, ambiguity, required capabilities and excluded Worker IDs
cannot be dropped while constructing the WorkRequest. Child profile/policy,
provider/model/effort/cost, alias/quota narrowing and paid/attended route identity
also remain binding. Incorrectly assembled inputs refuse; the adapter does not
silently repair the request or broaden its union.

### Candidate fields and trusted acquisition boundary

`CandidateInputs` has exactly these fields:

```text
worker: Worker
quota: WorkerQuotaClass | None
placement_fact: PlacementCandidateFact
source_before: OwnerEpoch | None
facts: OwnerCapacityFacts | None
source_after: OwnerEpoch | None
readiness: dict | None
physical: PhysicalInputs
native_snapshot: dict | None = None
native_join: dict | None = None
```

These are **private in-process owner inputs**. They are not a public Hermes JSON
request, an authenticated native receipt, or permission for Hermes to assert its
own entitlement. The caller must obtain registered Worker/Quota records and
current authenticated Capacity/host observations from their incumbent owners.
Do not expose this constructor as an unauthenticated admission endpoint.

`OwnerEpoch(source_ref: str, generation: int, source_digest: str)` identifies an
opaque source incarnation/revision. The source owner must advance the generation
on every relevant change, including an A→B→A change with an identical final
digest. Capture `source_before`, acquire the complete facts, then capture
`source_after`. All three epochs, including `facts.epoch`, must match. The epoch
covers the worker/quota fence, model capability and entitlement, host boot,
physical lane association and availability observations. This module does not
mint generations, persist epochs, or authenticate their origin. An owner unable
to supply this contract must return missing/unknown inputs.

`OwnerCapacityFacts` contains the following closed fields:

| Group | Fields |
| --- | --- |
| Source/currentness | `epoch`, `observed_at_ms`, `expires_at_ms`, `coverage` (`COMPLETE`, `PARTIAL`, `DISCONNECTED`) |
| Registered identity | `worker_id`, `quota_class`, `quota_fence_generation`, `model_alias`, `execution_profile_digest` |
| Host/lane/source join | `host_ref`, `boot_ref`, `lane_id`, `capacity_capability_id`, `worker_source_config_digest`, `physical_request_fingerprint` |
| Model suitability facts | `model_enabled`, `model_entitled`, `supports_tools`, `supports_vision`, `context_window_tokens` |
| Available finite capacity | `startable_jobs`, `cooldown_active`, `lane_limit`, `lane_in_use` |

The booleans and numeric capability/capacity facts may be `None`, meaning
unknown. Unknown entitlement, required capability, context window, quota,
cooldown or lane load cannot produce a candidate. `startable_jobs` is the
owner's finite estimate across all applicable quota horizons after entitlement
checks; it is not a guessed token balance. A cooldown of `None` is not `False`.
The complete owner observation must be current, have a lifetime no greater than
the incumbent 15 seconds, and satisfy `observed_at_ms <= now_ms < expires_at_ms`.

**V1 readiness and catalog overlap are insufficient for quota.** The existing V1
capacity observation proves its five readiness conditions and source join, not
entitlement or available provider quota. The model catalog does not supply
admission. The finite native V2 contract at this base is provider-specific; when
its actual wire and join are supplied, both are revalidated by
`native_capacity_v2.known_admissible`, including currentness, exact join, auth,
health, cooldown and quota. Neither V1 nor V2 is normalized into a new generic
provider/account registry. No acquisition or missing provider integration is
implemented by this packet.

Worker provider/account labels are opaque incumbent identities. Equality and
existing validators apply; there is no account guessing, email/path identity,
catalog alias conversion, ranking by account, or fallback across provider realms.
The registered Worker adapter must own the exact current model execution surface.
Model, quota and capability registry profile/policy identities must agree.
Unrelated Worker/Quota metadata is not projected into output.

### Physical owner inputs

```text
PhysicalInputs(
    request: dict,
    policy: dict,
    current_charges: tuple[dict, ...] | None,
    observations: dict | None,
    pressure_snapshot: dict | None,
)
```

Use the existing host-qualified physical request/policy/observation schemas.
The request must retain `operation_key = "finite-initial:<child job id>"` and
`command_id = "physical:<original dispatch command>:reserve"`. These identities
only bind a hypothetical evaluation; this adapter never submits that command.

The qualified owner must bind this Worker/lane to the request using the existing
`physical_request_fingerprint(request)`. That fingerprint covers the physical
profile, carrier, source and destination association. It excludes acquisition
time and command ID according to the incumbent definition; the command is
checked separately. The adapter does not infer a generic profile mapping from
the existing provider-specific finite admission implementation.

Host and boot identities must match the Capacity join, pressure snapshot,
capacity snapshot and qualified physical policy. Both snapshots must be
complete, their copied HP0 facts must agree, and the supplied pool availability
must equal the incumbent `_observed_pools` calculation. Existing physical policy
validates sample freshness, sequence, demand, charges and protected reserves.
Memory/CPU pressure is evaluated from measured owner inputs, not adapter-specific
thresholds. `None` charges/observations or partial/disconnected telemetry cannot
be replaced with empty charges or zero load.

`evaluate_reservation` is the incumbent **pure evaluator**. Its hypothetical
`RESERVED` result is only hashed, never exposed as an actual reservation receipt.
`OWNER_QUALIFIED` refuses synthetic policy. Explicit `FIXTURE_ONLY` decisions
retain `physical_qualification: SYNTHETIC_TEST_ONLY` and cannot satisfy the live
C30 owner-call contract.

## Decision semantics and provenance

After qualification, only the existing `select_placement` chooses among supplied
candidates. Its closure, source freshness, effect, occupancy, mode and capacity
rules remain authoritative. Available capacity ranks before degraded capacity;
an exact top tie abstains. No new tie breaker, model ranker, account preference,
union-member search, fallback tier or capacity writer is added.

| State | Meaning |
| --- | --- |
| `CANDIDATE` | Incumbent Placement selected one qualified input snapshot. It still requires current owner revalidation before a claim. |
| `REFUSED` | Invalid/inconsistent request or identity, unmet capabilities, illegal narrowing/widening, or no eligible candidate with a contract refusal. |
| `UNAVAILABLE` | Missing, stale, partial, disconnected, busy, cooling, exhausted or otherwise unavailable observations; also no route or an incumbent abstention. |

An invalid/unavailable sibling does not erase an independently qualified one.
Duplicate Worker identity is globally refused, matching incumbent semantics.

The closed wire includes `schema`, `state`, `code`, `candidate`, per-Worker
`trace`, `provenance`, `incumbent_selection` and `decision_sha256`. Provenance
binds original selection, router decision, requirements, effective constraints,
both placement unions, selected member, decision time and evaluation mode.
The selected candidate includes Worker/quota/model/profile, host/boot/lane,
source generation/digest/expiry, quota fence, owner-fact and registration digests,
readiness/native snapshot digests and physical input/evaluation digests.
Owner refusal codes are preserved as fixed `owner_code` identifiers; exception
messages and provider responses are not emitted.

Every result, including failures, explicitly carries:

```json
{
  "selection_is_commitment": false,
  "capacity_reserved": false,
  "admitted_capacity": false,
  "worker_started": false,
  "claim_time_revalidation_required": true
}
```

## C30 selected-child preflight seam

At this immutable base,
`ExecutiveControlService.dispatch_selected_child(job_id=..., command_id=...,
expected_selection=..., admission_guard=...)` in `executive_service.py` holds the
incumbent dispatch lock and reobserves the original command/Attempt before a
fresh path. It invokes the private synchronous guard and carries the same guard
into `_recheck_selected_child_admission` inside Runtime's fresh-claim transaction.

The C30 owner can compose H24 into that existing guard without creating another
claim/admission plane:

1. Preserve the current guard and original root, admitted plan, command and
   selection. Existing effects continue through original-command reobservation.
2. Acquire current source-qualified inputs from incumbent owners. Use the real
   child's requirements, inherited union and already selected placement member.
   Reacquire/recheck at each existing guard invocation, including the canonical
   claim transaction; a cached H24 decision is not a permission token.
3. Call `decide_hermes_capacity(..., router=current_preloaded_router)` in
   `OWNER_QUALIFIED` mode. Refuse unless state is `CANDIDATE`, selected physical
   qualification is `QUALIFIED`, and source acquisition/closure remains valid.
4. Preserve or verify the exact selected Worker/quota/model/fence/host/lane in the
   existing Executive choice/commit path. A boolean guard proving that *some*
   candidate exists does not authorize claiming a different candidate. Any
   mismatch or changed epoch requires re-evaluation by the same owners.
5. Return `None` only on guard success; the existing guard contract refuses any
   other return. The Executive owner alone performs its atomic fresh claim,
   Placement commitment, physical reservation/begin and subsequent Worker start.

This packet supplies the seam, not its activation. It edits no C30 integration
path, creates no live source collector, and proves no provider entitlement or
production-serving behavior. Future integration must retain source authentication
and transaction fences; syntactically valid caller-supplied booleans are not
authenticated evidence.

## Reproducible fixture trace

Run from the repository root; no providers, host sampling or credentials are
used. `qualified_inputs()` is a synthetic fixture factory, not an owner source.

```bash
python - <<'PY'
import json
from tests.test_hermes_capacity_decision import qualified_inputs
from control_plane.hermes_capacity_decision import decide_hermes_capacity
request, router = qualified_inputs()
print(json.dumps(decide_hermes_capacity(request, router=router).to_dict(),
                 sort_keys=True, indent=2))
PY
```

Observed fixture projection (abbreviated; command above emits the full wire):

```json
{
  "state": "CANDIDATE",
  "code": "INCUMBENT_SELECTED",
  "decision_sha256": "41a4b783b3f68021bad1fe5d36094a3330502d69cc8f1e17197fcdd2960577a5",
  "evaluation_mode": "FIXTURE_ONLY",
  "incumbent_aliases": ["fast.engineering", "standard.engineering"],
  "selected": {
    "worker_id": "worker-a",
    "quota_class": "routine",
    "provider": "codex",
    "model_alias": "fast.engineering",
    "model": "gpt-5.6-luna",
    "physical_qualification": "SYNTHETIC_TEST_ONLY"
  },
  "trace": [{
    "worker_id": "worker-a",
    "state": "QUALIFIED_INPUT",
    "code": "OWNER_CHECKS_PASSED",
    "evidence_sha256": "876d995302dc4a866eb1ad3ab55d686b3b42dcccc1df5583c72e0bb63cb06ed8"
  }]
}
```

The aliases and model above are observations from this base's incumbent router,
not constants in the adapter. Two equally available supplied models in the same
incumbent suitability tier produce the incumbent `tie_abstained` result.
The same fixture in default owner-qualified mode is `UNAVAILABLE`, with
`owner_code: SYNTHETIC_POLICY_REFUSED`. Missing original Attempt is
`REFUSED / ORIGINAL_ATTEMPT_MISSING`. Empty candidates are
`UNAVAILABLE / NO_ELIGIBLE_CANDIDATE`.

## Verification

Executed on the isolated branch with Python 3.12, without installing dependencies:

```bash
python -m unittest tests.test_hermes_capacity_decision -q
python -m py_compile control_plane/hermes_capacity_decision.py tests/test_hermes_capacity_decision.py
git diff --check b54cb10e4abdd3766c62d4088f6a576ecfe80437
```

The new standard-library suite runs **83 tests**. It covers healthy qualified
fixture input; tool/vision/context mismatches; disabled/unentitled models;
current provider, adapter, profile and capability-policy drift; measured memory
and CPU pressure; stale TTL/sample/boot; source ABA; missing quota/cooldown;
wrong/inherited union and child requirements; exhausted/overcommitted lanes;
absent original Attempt and invalid/terminal child; native-wire refusal;
partial/disconnected observation; empty routes; incumbent tie/rank/exclusions;
explicit synthetic-mode separation; and physical child/lane binding.

The concurrency case runs 32 decisions through eight threads using snapshots
read from a temporary canonical Runtime store. It compares the complete database
dump before and after and verifies identical outputs and unchanged inputs. The
pure-call test rejects file open, socket construction, process start, clock
reads and router loading during evaluation. No runtime implementation is mocked
to turn an unavailable lane into an available one.

Pytest is not installed in this environment; no install was attempted. This is
the scoped H24 suite exercising actual incumbent pure functions. It is not a
claim that the repository-wide pytest suite, CI, live C30 integration, provider
acquisition, admission, deployment or Worker START has passed.
