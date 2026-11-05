# Hermes binding to existing Executive children

Status: **source qualification; no live admission or installation**.

## Implemented owner binding

`ExecutiveChildQualification` reads one existing, host-selected direct work or
repair child from the incumbent Executive Runtime. It opens one
`RuntimeStore.read()` context and uses that connection for the raw root/child
rows, admitted plan, current revision and current Attempt. Installed physical
read-binding validation must succeed on context exit before an observation is
returned.

The binding reuses:

- `_validated_plan_admission` for the original admitted plan and reservation.
- `_current_orchestration_tree_material_for_dispatch` for current persisted
  work/repair lineage and reserved slots.
- `_job_from_row`, `_attempt_from_row` and
  `derive_delegation_identity` for canonical decoding and identity.

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

## Verification

```sh
PYTHONPATH=.:tests python3 -m pytest -q tests/test_hermes_executive_qualification.py
python3 -m unittest discover -s integrations/hermes_delegate/tests -v
```

The focused tests use actual Runtime admission, canonical sealed planner/work
fixtures and a genuine repair sequence. They cover changed identity and
Attempt pins, superseded work, faulted invariant reads with database guards intact, failure on read
context exit, restart reconstruction and unchanged Jobs/Attempts/events.
They do not call a provider or claim a deployed Hermes-to-parent journey.
