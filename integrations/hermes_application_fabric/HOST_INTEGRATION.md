# Existing-host activation and real-account acceptance

This is the integration contract for the current APPLICATION and Hermes host
owners. It does not enroll a role, install a runtime, create a session registry,
or authorize provider calls. The current owner source does not yet issue a
qualified Hermes factory. Activation remains closed until that owner supplies it.

## Smallest first live slice

The first real-account qualification can use one host-authorized strict model
and one eligible account through existing APPLICATION admission. It does not
need to wait for the entire AUTO selector extension. The original programme still
requires automatic routing and strict pool support before completion.

The APPLICATION owner accepts or replaces these proposed dedicated relations:

| Existing role profile | Proposed lane | Proposed service mode |
| --- | --- | --- |
| `mmmeta` | `hermes-meta-ceo` | `hermes_meta_fabric` |
| `mmsecretary` | `hermes-secretary` | `hermes_secretary_fabric` |

The owner's closed relation, workload/capability policy, internal service-token
resolution, entitlement, transport qualification and TTL remain authoritative.
Changing a consumer constant does not create any of those facts. A changed
owner-approved relation requires the corresponding narrow adapter update.

## Host composition

1. The incumbent installer/host verifies the selected Hermes source and adapter
   qualification. The private native auth-type seam was tested only at Hermes
   `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. The adapter constant records that
   revision; `create_primary_agent` does not independently verify a Git checkout.
2. The existing authenticated host obtains the original operation/session/turn
   identity and the qualified APPLICATION factory from its current owners.
   It independently checks that a new admission is permitted. An uncertain or
   previously admitted operation goes to original-owner recovery, not this
   constructor with a convenient `False` value.
3. The host creates one binding and retains that same binding in its existing
   lifecycle. Do not add a separate adapter session map or restore-by-ID path.

```python
from integrations.hermes_application_fabric import ApplicationBinding
from integrations.hermes_application_fabric.native import (
    create_primary_agent, register_middleware,
)

# All values/callbacks below are supplied by the incumbent authenticated host.
# This becomes runnable only after that host receives a qualified owner factory.
binding = ApplicationBinding.from_factory(
    qualified_factory,
    profile_id=authenticated_profile_id,
    operation_id=original_operation_id,
    session_id=original_session_id,
    turn_id=original_turn_id,
    requested_model=host_selected_model,
    strict_model=host_selected_model,
    authorized=current_role_session_grant_check,
    prior_admission_possible=False,  # Only with actual original-owner proof.
)

# resolve_existing_binding(call) returns the retained binding using the existing
# host's authenticated context and lifecycle, never request prose alone.
middleware_handle = register_middleware(plugin_context, resolve_existing_binding)
agent = create_primary_agent(model=host_selected_model)
```

4. Before creating agents, register the provider and middleware through these
   entrypoints. The provider refuses existing same-name custom/profile/auth-arm
   collisions. The host owns the returned middleware handle; do not live-swap an
   incumbent provider or install it via the naked CLI auth ladder.
5. The host's authorization callback must verify the current role, session,
   task/turn relationship, grant and revocation state for each `NativeCall`.
   Native metadata carries correlation only. The adapter checks that callback
   before dispatch and before returning executable tool calls. Host-selected
   model and request capability requirements must come from trusted policy.
6. Execute the original native conversation through the host's existing agent
   lifecycle. Hermes generates its API request ID before its internal loop; the
   adapter hashes it with the original operation/session/task/turn identity.
   The original owner client holds attempted/active/uncertain state. Facade
   eviction or rebuilding never replaces it.
7. The same host owns normal completion, interruption and original close. A
   downstream failure invokes the original local close fence. Preserve the
   owner's final or unknown close disposition; it is not inferred settlement.

No API key, endpoint, credential pool, fallback chain or provider auth store is
supplied to Hermes. There is no auxiliary/vision/async inference admission in
this primary synchronous slice. Host requirements needing streaming, opaque
reasoning replay or other unsupported carriers must refuse until qualified.

## Live acceptance sequence

Use the existing owner to admit a bounded, non-sensitive canary with one enabled
model/account. The host sets a small output budget within the account's approved
budget. Use the existing role's harmless read-only tool, with an observable
execution counter supplied by its current tool/test owner.

| Step | Required canonical evidence |
| --- | --- |
| Admission | Current role/session grant; dedicated Hermes service relation; entitlement/qualification reference; original operation; approved model constraint. |
| Selection/reservation | Actual provider, served model, physical account and quota bucket; one reservation through the existing lease/budget owner; actual policy/recipe revision. |
| First model turn | Original request/operation correlation and authenticated internal call; real model output and provider usage. No provider key inside Hermes. |
| Tool continuation | Original native tool-call ID, exactly one permitted tool execution, original result in next native request, same original APPLICATION owner. |
| Bounded denial | Existing owner's deterministic budget/entitlement refusal before provider dispatch. Do not spend funds merely to exhaust a real account. |
| Settlement | Actual usage/charge and original reservation settlement/close disposition from canonical owners. Synthetic token totals do not qualify. |
| Recovery | Controlled timeout/disconnect using an owner-authorized fixture/canary; reconcile the original request, prove tool execution is not repeated, and retain unknown effects until the owner resolves them. |

The public response need not initially carry every accounting field if existing
canonical owner evidence supplies an exact request-linked readback. Do not
interpret a capability ID as an account or invent an adapter accounting receipt.
Record links to those owner facts in the programme/PR evidence. Never include
service tokens, provider keys or credential file contents.

## Routing extension after the first account

AUTO and strict pool selection remain an extension of the current
ModelRouter/APPLICATION/Fabric account contract. Apply trusted capability and
strict constraints before ranking; use task complexity, expected latency,
headroom and cost; deduplicate by physical quota bucket across all model/pool
aliases; recheck and reserve atomically through the incumbent owner. The detailed
design is in [README](README.md#routing-and-physical-account-design).

Only original-owner proof that a new provider call is safe permits failover.
Neither an HTTP 429, timeout, changed account headroom nor a newly constructed
Hermes agent proves that fact. This adapter currently refuses strict pools and
supplies no failover or cross-process recovery service.
