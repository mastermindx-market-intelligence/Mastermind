# Hermes binding to existing Executive children

Status: **source composition implemented; no installed native registration**.

## Implemented owner binding

`ExecutiveChildQualification` reads one existing, host-selected work or repair
child from the incumbent Executive Runtime. Its immediate parent may be the
original root or an admitted aggregation coordinator at depth 1 or 2. The
original mission root remains unchanged. It opens one `RuntimeStore.read()`
context and uses that connection for the raw root/coordinator/child rows,
admitted plan, current revision and current Attempt. Installed physical
read-binding validation must succeed on context exit before an observation is
returned.

The binding reuses:

- `_selected_child_coordinator_plan` and `_validated_plan_admission` for the
  immediate coordinator's actual admitted plan and the current ancestor
  reservations. Nested ancestry uses the existing bounded hierarchy owner.
- `_current_orchestration_tree_material_for_dispatch` for current persisted
  work/repair lineage and reserved slots.
- `_job_from_row`, `_attempt_from_row` and
  `derive_delegation_identity` or `derive_coordinator_child_delegation_identity`
  for canonical decoding and identity. The legacy work-parent identity helper
  keeps its separate existing contract.

Raw root, parent and depth are checked before legacy decoding can normalize a
missing root. A frozen `ExecutiveChildSelection` pins the root, parent, Job,
plan Attempt/digest/step, repair round and expected current Attempt. A null
expected Attempt requires a null current Attempt; it is not a wildcard.
Superseded work and changed coordinates refuse without creating another Job,
Attempt, event, queue, session or carrier request.

A successful `CURRENT_PLAN_CHILD` observation contains identity and status
only. It never returns credentials, grants, principals, paths, objective/result
text or a claim of acceptance. For a repair, it observes current persisted
lineage under the admitted plan; it does **not** independently re-prove the
repair creation event or its rejecting review.

## Trusted-host consumer

The existing `Bridge` can receive this optional diagnostic binding:

```python
from integrations.hermes_delegate.bridge import Bridge
from integrations.hermes_delegate.executive import (
    ExecutiveChildQualification,
    ExecutiveChildSelection,
)

# Coordinates come from the existing authenticated host's selection.
selection = ExecutiveChildSelection(
    root_job_id=root_id,
    parent_job_id=parent_id,
    job_id=child_id,
    plan_attempt_id=plan_attempt_id,
    plan_digest=plan_digest,
    plan_step_id=plan_step_id,
    repair_round=repair_round,
    expected_current_attempt_id=current_attempt_id,
)
bridge = Bridge(
    executive_qualification=ExecutiveChildQualification(runtime, selection),
)
observation = bridge.inspect_executive_binding()
```

This method is host-only and is not advertised or accepted by
`mmx_delegate`. The caller remains responsible for authenticated selection;
model arguments must never construct this binding. Qualification does not
populate the parent-local fixture tracker or alter submission, cancellation,
review or consumption. Unbound inspection refuses with
`EXECUTIVE_QUALIFICATION_NOT_BOUND`.

## Selected-child production composition

Beside that observation binding, `integrations/hermes_delegate/executive.py`
carries the explicit trusted-host production composition.

### Frozen authority inputs

The authenticated host freezes one child before any dispatch. Nothing else may
name it:

| Input | Source | Meaning |
|---|---|---|
| `root_job_id` | host selection | original strict-v2 aggregation root |
| `parent_job_id` | actual selected child's Runtime row | immediate admitted coordinator; the root for a direct child |
| `job_id` | host selection | one current work or repair child at depth 1, 2 or 3 |
| `plan_attempt_id` | host selection | the admitted plan Attempt |
| `plan_digest` | host selection | the admitted plan digest |
| `plan_step_id` | host selection | the admitted plan step |
| `repair_round` | host selection | the persisted repair round |
| `expected_current_attempt_id` | host selection | exact absence (`None`) or one exact Attempt |
| `attempt_ordinal` | host selection | the frozen Attempt ordinal (1 for the first Attempt) |

`ExecutiveSelectedChild` derives the canonical command reference from those
coordinates:

```
coo-cycle:{parent_job_id}:dispatch:{job_id}:attempt:{attempt_ordinal}
```

The ordinal is frozen with the selection, so the command is derived once and
is never recomputed from a later `attempt_count`. Direct children have equal
root and parent IDs, so their command bytes remain unchanged.

The private host capture still accepts only the original root and chosen child
IDs. It derives the immediate coordinator from the first actual selected Job
inside the same bounded Runtime observation. Every chosen child must share that
coordinator, original root and admitted plan Attempt/digest and must be its
current work or repair revision. No caller-provided coordinator selector is
introduced. The snapshot's root and root metadata remain the original mission;
its admitted plan belongs to the actual immediate coordinator.

All ancestor, plan and selected-child reads share the existing row, raw-byte,
statement and VM limits. The normal admitted-plan read remains unchanged.
Workspace brackets both existing policy versions before capture and rechecks
only the selected admission's version and source afterward; unavailability of
the unrelated version does not grant anything or block a valid legacy capture.
Canonical ancestor validation still requires its own policy evidence: the
original planner retains v1 transport proof even for a v2 reservation.
The closed publication retains every hash and source field and permits exactly
one coordinator and plan. Its source block is provenance, not a grant.

### Composition and installation

```python
from integrations.hermes_delegate.executive import (
    ExecutiveSelectedChild,
    ExecutiveSelectedChildComposition,
    install_selected_child_composition,
)

composition = ExecutiveSelectedChildComposition(
    service=executive_service,      # the incumbent ExecutiveControlService
    runtime=executive_service.runtime,
    children=(ExecutiveSelectedChild(selection=selection, attempt_ordinal=1),),
    loop=asyncio.get_running_loop(),  # the loop that owns the service
    authority=installed_coo_host,     # actual CooHostProvider
    context=authenticated_context,  # actual PrincipalAdmissionContext
    capability_profile_digest=authority.capability_profile_digest,
    receiving_request_guard=require_current_app_request,  # synchronous, returns None
)
install_selected_child_composition(composition)
```

`install_selected_child_composition` stores the binding only. It admits
nothing, reads no credential, starts no worker, and creates no Job, Attempt,
queue, session or lifecycle owner. The process default is unbound;
`clear_selected_child_composition()` restores it.

The context, capability digest and request guard come from the existing authenticated
App/installed principal owner. A Hermes role label cannot supply them.

Control calls `submit_async` / `status_async` on its own loop. A synchronous
in-process adapter uses the separate loop boundary described below.

### Actual invocation

The model-facing handler is the existing `mmx_delegate` handler. The
selected-child branch is closed: the action and the exact canonical command
reference, nothing else.

```python
from integrations.hermes_delegate.tool import dispatch

body = json.loads(dispatch({
    "action": "selected_child_submit",   # or "selected_child_status"
    "command": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
}))
```

The registered schema carries two closed branches. The bridge branch keeps
`action` plus `idempotency_key` and the existing delegation arguments. The
selected-child branch permits only `action` (`selected_child_submit` or
`selected_child_status`) and `command`. A model `idempotency_key`, Job id,
root id, carrier, objective, acceptance, reviewer field or cancel request on
that branch is refused with `UNKNOWN_FIELD`. `review` and `consume` remain
`REVIEW_AND_CONSUME_OWNER_ONLY`, and generic `cancel` is refused.

The branch never constructs a live `Bridge()` and never touches
`Bridge._by_key` / `_by_fingerprint`. The checked-in `tool_policy.json`
(`live_submit: false`) continues to govern the inert bridge path only; the
selected-child branch is bound to the incumbent Executive service and to that
service's own host-authority fences.

### Service entry and return path

`ExecutiveControlService.dispatch_selected_child` and
`ExecutiveControlService.selected_child_status` are the narrow service
entries. A new claim is an effect: it applies the incumbent readiness fences
(`_closing`, `coo_autonomy_armed`, `_require_current_autonomy`, `READY`
service state), the host-authority fence `_require_coo_worker_composed`, and
`_require_bound_coo_job` for the bound-root and admitted-plan membership
check. The selection shape — a current work or repair child of its actual
immediate coordinator under the frozen original root — is a fact about the
persisted Job and is checked before any of them.
Resolving a command that already owns a durable Attempt is a pure read of
Runtime truth, so it stays answerable even when this service can no longer
act.

Dispatch takes the existing `_dispatch_lock`, reobserves the original command,
and only if absent rechecks readiness. It calls the same incumbent dispatch body,
extracted as `_dispatch_cycle_job_exact_locked`; ordinary cycle callers retain
the `_dispatch_cycle_job_exact` wrapper and the same lock. The broad `CooCycle.run_once`
never runs for a selected child, and no supervisor, placement selection,
workspace preparation, lease replay or provider start is re-implemented.

The claim belongs to `AttemptRegistry.dispatch_cycle_job` and
`claim_job`. The frozen selection is re-proved inside the claim transaction
by `_assert_expected_child_selection`, in the same `BEGIN IMMEDIATE`
transaction that inserts the Attempt and flips the Job, so there is no
validate/release/lock gap. It compares the Job identity, parent, root, plan
Attempt, plan digest, plan step, repair round, the exact expected current
Attempt, the frozen ordinal against `attempt_count + 1`, the deterministic
command reference, and the currently admitted plan Attempt and digest.

That re-proof governs a **fresh** claim. A command that already owns a
`JOB_CLAIMED` event takes the incumbent replay branch, which returns that
existing Attempt and creates no new effect; the pre-claim freeze is
deliberately not re-applied there, because the frozen expected current
Attempt is exactly the state the first claim already changed.

Both explicit and task-bound selections must agree and name the exact Job and
command before the existing replay branch. Mismatch refuses; a bound selection
cannot silently disappear into an unconstrained claim. The same task binding
carries the private synchronous authority guard. It runs inside the fresh claim
transaction before mutation and before COMMIT, so current principal or mandate
revocation rolls back the Job, Attempt and claim event together.

The claim boundary is reached through the incumbent supervisor, whose
signature is outside this change's grant, so the frozen selection is carried
by the task-scoped `expected_child_selection` binding in
`control_plane/executive_runtime.py`. The binding is matched by exact Job and
command and is consumed only by the claim that owns it; `claim_job` and
`dispatch_cycle_job` also accept an explicit `expected_selection` argument
for a caller that can pass one directly.

Completion belongs to `ExecutiveService._finish_dispatched` and
`Runtime.validated_role_completion`. A repeated submit observes that exact
command and Attempt: it never recomputes `attempt_count + 1` into a fresh
Attempt, and it never retries, falls back to a second carrier, or selects
another child. When a dispatch fails after a durable claim, the incumbent
lost-return marker is recorded on the original command and the result is
reported as `EFFECT_UNKNOWN` on that same command and Attempt.

That uncertainty stays on its original command even after the service
quarantines itself: a claim that is already durable is still reported by
`selected_child_status` and by a repeated submit, so the model is never told
"refused, no effect" for an effect the Runtime already owns. The incumbent
`:reconciled` resolution event closes the ambiguity; until it exists the
status stays `EFFECT_UNKNOWN`. If marker persistence fails, the incumbent per-Job
dispatch error and quarantine retain the uncertainty; missing marker bytes are
not proof that it cleared.

A completed status is sourced from `Runtime.validated_role_completion` and
reduced with the incumbent `reduce_terminal_return`. The status read never
replaces terminal-return ownership and never delivers a second message; the
original parent still receives the single terminal return through the
existing Dialogue/Wake consumer.

### Response shape

The model-facing envelope adds the schema and the live-submit flag to the
canonical facts the service returns:

```json
{
  "schema": "mastermind.hermes_delegate.selected_child/v1",
  "state": "ACTIVE | COMPLETED | NOT_CLAIMED | EFFECT_UNKNOWN | UNVERIFIED | FAILED | CANCELLED | RATE_LIMITED | CANCEL_REQUESTED | REFUSED | UNAVAILABLE",
  "reason": null,
  "live_submit": true,
  "command_id": "coo-cycle:JOB-001:dispatch:JOB-003:attempt:1",
  "job_id": "JOB-003",
  "attempt_id": "ATT-...",
  "attempt_status": "CLAIMED",
  "job_status": "RUNNING"
}
```

`live_submit` is true when a canonical Attempt is observed, false for a proved
pre-dispatch refusal or unclaimed command, and null when the original effect or
its observation remains unavailable. An uncertain response retains the frozen
command and Job even when it cannot yet name an Attempt. A completed status
additionally carries `result_status`,
`result_envelope_digest` and `terminal_evidence_digest`. It never carries the
worker's result text.

### Handler and loop boundary

The async receiving Control path calls `submit_async` or `status_async` directly.
A synchronous adapter in the same process may use `run_coroutine_threadsafe`
from another thread. Calling its synchronous wrapper on the owning loop refuses
with `EXECUTIVE_SELECTED_CHILD_LOOP_REENTRANT`.

Once a submit is scheduled, timeout, malformed return or an unexpected exception
retains the original command as `EFFECT_UNKNOWN`. The scheduled operation is
not cancelled or retried. Recovery only reads that original command.

A remote Hermes process cannot share this Python binding. It requires the actual
authenticated MCP/App/Control transport and a native profile/session binding;
this module does not establish either by assigning a process-global object.

## Remaining live integration

Observation is not a launch grant and is stale as soon as the Runtime changes.
The installed Executive dispatcher must still establish principal, release,
workspace, capacity, budget and current eligibility at the actual effect.

The real Fabric run identity is the Executive **Attempt ID**. The deterministic
dialogue `operation_key` and `session_ref` come from the existing identity
projector. A model request key cannot replace any of these identities.

Do not call generic `create_job`, `submit_ceo_intent`, raw Fabric, or a broad
COO cycle as a shortcut for dispatching a selected child. Do not add a second
lifecycle, authentication, retry, return, queue or continuity owner.
Canonical completed-return integration must reuse
`Runtime.validated_role_completion`, the incumbent terminal-return reducer
and existing Dialogue/Wake original-parent consumer. This diagnostic does not
read protected result text or stand in for canonical acceptance.

Nested orchestration children are explicitly unsupported by this first
binding. The default admission, carrier and return-owner bindings remain
inert/unbound. The role-runtime #1966 installation hold is unaffected.

### Installed-native registration is still open

This change is a source composition. `boot_harness` registers tool *names* in
a process-local census; it does not install `mmx_delegate` in native Hermes,
and `ServiceRuntime._expected_disabled_mcp` still refuses a populated
`extension_allowlist` as `NATIVE_EXTENSION_NOT_INSTALLED`. That refusal is
correct and is not weakened here.

The remaining production dependencies are explicit:

1. An actual host owner selecting and freezing children from the current admitted
   plan, then supplying that immutable target to the existing installation.
2. A closed selected-child branch through the existing authenticated MCP/App/Control
   chain, including the exact capability schema and installed mission generation.
3. Native Hermes plugin registration with qualified profile/session lineage and a
   genuinely enrolled Executive principal connection. Provider BYOK credentials
   and the read-only Steward token do not authorize this operation.
4. The installed producer-to-consumer proof, including the original-command return.

None of these is satisfied by the process-local name census or an invented
principal, target, token, native session, or new-root admission.

No role label, metadata row or provider session string may substitute for a
real admitted Runtime Attempt, sealed harness session/generation, immutable
Dialogue source, current writer or matching Wake acknowledgment.

## Verification

```sh
PYTHONPATH=.:tests python3 -m pytest -q tests/test_hermes_executive_qualification.py
PYTHONPATH=.:tests python3 -m pytest -q tests/test_hermes_selected_child_dispatch.py
PYTHONPATH=.:tests python3 -m pytest -q tests/test_hermes_nested_selected_child.py
python3 -m unittest discover -s integrations/hermes_delegate/tests -v
```

The focused tests use actual Runtime admission, canonical sealed planner/work
fixtures and a genuine repair sequence. The selected-child tests compose the
real tool handler, the real service owner, the real Runtime claim and the
real terminal-return reduction; only the provider process is inert. They cover
changed identity and Attempt pins, superseded work, faulted invariant reads
with database guards intact, failure on read context exit, restart
reconstruction and unchanged Jobs/Attempts/events, plus replay before and
after completion, the frozen ordinal, stale selection/plan/Attempt refusal
before effect, wrong authority and unknown post-claim behavior. They do not
call a provider or claim a deployed Hermes-to-parent journey.

The repaired selected-child regressions also cover concurrent ambiguous starts,
post-scheduling timeout without cancellation, original identity after malformed
returns, failed uncertainty-marker persistence, mismatched bound claims, and real
installed-principal revocation between claim insertion and COMMIT.

The nested suite includes depth-2 and depth-3 capture through the real
Workspace/CooHost owners, the fixed installed target reader, canonical Runtime
qualification and claim, original-command replay and terminal completion. Its
full deepest-root case captures all 11 leaves of a 17-Job tree within the
unchanged shared budgets. The
service cases separately exercise the actual selected dispatch/status/return
owner. Negatives cover mixed coordinators, foreign roots, stale plan/Attempt
coordinates, root-scoped command substitution, rehashed foreign publication,
source/policy changes and permission revocation. These are disposable source
qualifications; they do not enroll or activate a live Hermes profile.
