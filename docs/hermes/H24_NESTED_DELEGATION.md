# H24-07: canonical nested-delegation contract

## Delivery boundary

This packet adds a **pure, immutable validator and projection** for a trusted
Hermes host to describe an already admitted Executive team. It does not create
children, claim Attempts, reserve capacity, issue leases, accept results, write
Events, select providers, or activate a service. Its outputs are requests and
observations for the existing COO/Executive owner.

Implementation base: `b54cb10e4abdd3766c62d4088f6a576ecfe80437` in
`mastermindx-market-intelligence/Mastermind`.

Assigned branch: `sol/h24-07-nested-contract-20261106`.

Governing protected-source pin:
`88a8b103a5a69e4b4e870a184655dde9fd5875c3`, Skillpack
`mastermind.sol_skillpack.v1`, version `1.0.1`, bootstrap major `1`.
The current Chairman instruction authorizes concurrent source-only placement;
there is no wait for H24-01 or a soft wave seal.

Exactly three new files belong to this packet:

- `control_plane/hermes_delegation_contract.py`
- `tests/test_h24_hermes_delegation_contract.py`
- `docs/hermes/H24_NESTED_DELEGATION.md`

PR #2120's integration, C17/C29/C30 composition, C29–C34 exclusive files,
Runtime/Job/Attempt/lease stores, hierarchy policy and limits, and native Hermes
registration remain outside this writable grant. The packet's acceptance is
source conformance. Real nested subagents remain **BUILT_NOT_PROVEN** until the
separate owner composition and runtime evidence described below exist.

## Canonical source and exact limits

The source contract comes from these files at the immutable implementation base:

| Existing owner | Invariants consumed here |
| --- | --- |
| [Hierarchy contract](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/docs/EXECUTIVE_COO_HIERARCHY.md) | Four levels, conserved original root, retained terminal slots, exact inherited placement union, transitive aggregation. |
| [Pure hierarchy validators](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/executive_coo_hierarchy.py) | `validate_tree`, `validate_grant`, `inherited_grant`, `ancestors`, `descendant_ids`, `assert_admission_open`. |
| [COO policy](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/executive_coo_policy.py) | Exact hierarchy policy digest, full plan reservation arithmetic, review/repair budgets. |
| [Runtime](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/executive_runtime.py) | Immutable plan admissions, deferred steps, contiguous repairs, original commands, canonical requeue chain, exact current result/review acceptance. |
| [C17 selected-child schema](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/hermes_delegate/schema.py) | Only `selected_child_submit` / `selected_child_status`, with exactly `action` and `command`. |
| [C17 composition](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/hermes_delegate/executive.py) | Host-frozen selection, original ordinal, status before fresh admission, existing service and Runtime claim. |

The admitted plan is v5, its reservation wire is v3, and the hierarchy policy is
v2. These distinct version numbers must not be conflated.

| Limit or reservation | Exact value |
| --- | --- |
| Root depth | 0 |
| Allowed descendant depths | 1, 2, 3 |
| Maximum complete root observation | 17 Jobs, including the root |
| Original-root descendant allowance | 16 total, including terminal Jobs |
| Planner | 1 descendant slot inside its coordinator's allowance |
| Unreviewed leaf | 1 slot |
| Reviewed leaf | 9 slots: `(1 + 2 repair rounds) * (1 + 2 review Jobs per revision)` |
| Delegated coordinator | Its own Job plus its entire delegated descendant allowance |
| Review Job Attempt limit | 1 |
| Other orchestration Attempt policy ceiling | 2, subject to the existing Job's tighter limit and retry owner |

A root planner plus a coordinator granting 14 descendants reserves all 16 root
slots. That coordinator can reserve its planner plus a coordinator granting 12;
the latter reserves its planner plus eleven depth-3 leaves. Creating a coordinator
never replenishes the root budget. Terminal work never frees an allocation.

Reservations and materialized Jobs are checked separately. A reserved slot is
not charged a second time when materialized. A sibling cannot borrow another
step's reserved review or subtree allowance. Each child coordinator's allowance
strictly decreases, and its absolute depth ceiling cannot widen.

## Private immutable API

Callers supply the existing `CooCyclePolicy` value explicitly; this module does
not load files or query Runtime. The policy's canonical payload must match the
existing hierarchy digest. Frozen dataclasses contain only immutable scalars,
other frozen records, and tuples. Lists and malformed nested facts are refused.

| Operation | Output and meaning |
| --- | --- |
| `validate_observation(observation, policy=...)` | `TreeProjection`: retained descendant count, maximum observed depth, complete per-coordinator reservation totals. |
| `project_request(request, selected, observation, policy=...)` | `OwnerRequest`: exact frozen selection, original command, current observation stamp, and any original Attempt/fence/result references. |
| `project_aggregate(observation, binding, policy=...)` | `AggregateProjection`: dependency readiness, pending real Jobs, reserved steps without Jobs, unresolved commands, accepted result references. It never finalizes a parent. |

`OwnerObservation` carries a complete coherent root read, permission and authority
generation bindings, owner snapshot digest, Jobs, full plan reservations,
original command/Attempt observations, terminal/review evidence and, when
applicable, the existing owner's exact `JOB_REQUEUED` evidence. A caller's boolean,
digest, type name or constructor is **not authentication**. These records must
never be model-supplied public tool parameters.

The host freezes `FrozenChild` from canonical selection. The model receives only:

```json
{
  "action": "selected_child_submit",
  "command": "coo-cycle:JOB-C2:dispatch:JOB-W0:attempt:1"
}
```

`OwnerRequest.public_request()` returns a detached copy of those same two fields.
Private authority, root, parent, plan, reservation, Attempt and generation
coordinates do not become public request arguments. The bridge checks action
types before using C17's parser, so list/dict actions refuse without leaking a
`TypeError`. Canonical colon-containing plan-step identifiers remain valid;
dispatch coordinates still obey C17's unchanged command grammar.

### Fresh submission and original-command recovery

The dispositions below are projection descriptions, not new Executive states:

- `FRESH_REQUEST`: facts agree and the request can be presented to the existing
  owner for its transaction-local recheck. No capacity, quota, lease or Attempt
  has been acquired by this result.
- `RECONCILE_ORIGINAL`: the command already has canonical evidence, including an
  uncertain effect. The normalized action is always `selected_child_status`;
  it preserves the original Attempt when known. A missing return cannot cause
  a new command, ordinal, parent, root or carrier.
- `OBSERVE_UNCLAIMED`: an authorized complete observation contains no effect for
  that command. An already consumed ordinal with an omitted command refuses
  instead of manufacturing this disposition.

Current read permission and exact authority generation are required for all
three. Original-command reconciliation precedes fresh admission checks. Parent
cancellation, closed fresh-submit permission or a later repair therefore does
not erase authorized access to the original command. Changing authority
generation still requires the host's legitimate reauthorization of that same
command; the bridge supplies none.

Fresh descendants require every aggregation ancestor to remain QUEUED,
uncancelled and unstarted. RUNNING is not the source contract's admitting-parent
state. The child must remain the admitted step's exact current revision; old,
forked, skipped or replacement repair lineage refuses.

An owner-initiated requeue clears `Job.current_attempt_id` and retains the old
Attempt and count. Old-command status remains readable. A newly host-frozen
ordinal requires `RequeueFact` for the exact terminal predecessor, the canonical
requeue Event and the same latest Job Event. Its digest references owner-validated
evidence; it does not issue a retry grant. The Runtime must still validate its
actual retry chain, Job Attempt limit and normal claim gates.

### Placement and aggregate completeness

Fresh nested requests require the inherited, host-admitted placement-union
digest at every ancestor. Each coordinator inherits the parent's exact union;
the host may narrow a selected placement through the existing routing contract.
A missing union is not reconstructed from a requested model or an automatic
route. Legacy absence remains visible and cannot grant fresh H24 admission.

Dependent v5 steps may be reserved before their initial Job exists. The original
reservation keeps `initial_work_job_id` and `initial_work_command_id` absent,
even after the existing owner later materializes the dependency-qualified Job.
H24 retains that absence, charges the full reserve, lets independent siblings
progress, and exposes an unmaterialized obligation in `pending_steps`.

Aggregate readiness is derived from the complete admitted plan, not the set of
returned results. It requires all current transitive work, terminal evidence,
the exact current accepted repair revision and any required owner-validated
review. It also waits for every retained nonterminal descendant and unresolved
dispatch-return marker. A completed coordinator cannot hide a live grandchild;
a partial child result or omitted deferred step cannot finalize its parent.

Terminal evidence binds the original command, Job, Attempt, plan lineage and
fence generation. Review evidence additionally binds the exact completed current
review Job/Attempt and reviewed result. The existing result owner must establish
real principal independence and absence of an unresolved independent rejection;
the bridge cannot prove those facts merely by checking digest syntax.

## Actual owner join and transaction specimen

The following producer/consumer join is required before activation. It is not
implemented in incumbent owner files by this packet.

| Projection facts | Existing canonical producer or guard |
| --- | --- |
| Complete ancestry and retained grants | Runtime `_hierarchy_material` and `_coordinator_grant`, within the existing coherent root read. |
| Every reserved step, including deferred work | `_validated_plan_admission`; join its full plan and reservation with `_current_orchestration_tree_material_for_dispatch` rather than dropping steps absent from the current materialization. |
| Permission, generation, installed source and selected target | C29/C30 authenticated App/Control composition, `CooHostProvider`, `PrincipalAdmissionContext` and currentness guards. |
| Inherited placement | Owner-normalized `work_placement_union`, preserving exact normalized content/digest and absence. |
| Original command, Attempt and uncertainty | Existing `selected_child_status`, command Event lookup, Attempt registry and dispatch-effect reconciliation. |
| Accepted terminal/review references | `_validated_role_completion_material`, `_accepted_current_step_revision` and the existing independent-review validation. |
| Requeue continuation | The Runtime's exact terminal-Attempt / `JOB_REQUEUED` / latest-Job-Event checks at claim. |
| Final side effect | Existing COO/Executive claim, reservation, lease and aggregation owners only. |

Transaction sequence:

1. Authenticate through the installed owner and acquire one coherent complete
   root observation. Validate the retained admission, grants and evidence there.
2. Bind the exact immediate coordinator and frozen child command. Run the pure
   projection; its return has no modifying effect.
3. At the existing owner transaction boundary, recheck currentness and rederive
   the applicable facts. An observation digest is a comparison reference, not
   a lease and not a new revision store.
4. Resolve an already observed command first. Preserve its original Attempt,
   including after cancellation, disconnect or host restart. Unknown effect
   remains on its original command and carrier.
5. For genuinely fresh admission, run the existing permission, cancellation,
   exact-selection, reservation, placement, retry, Job-limit and lease checks in
   the same transaction that owns the claim. H24 creates no Job or reservation.
6. Retain terminal/review evidence through Runtime. Project complete transitive
   dependencies, then let the existing aggregation owner create its immutable
   handoff and perform the authorized transition.

Two pure projections of the same snapshot do not serialize each other. The
test fixture `OwnerTransactionSpecimen` demonstrates the required interleaving:
both requests are inert; the owner consumes the first; the second stale snapshot
is refused; a fresh observation of the same distinct reserved sibling may
progress. Replaying the first command returns the same original Attempt. This
is a deterministic transaction-sequence specimen, **not live concurrency or
installed Runtime proof**. The real atomic transaction remains indispensable.

## C17/C30 prerequisite and Hermes boundary

At the immutable base, `ExecutiveSelectedChild.command_id` constructs a
root-scoped command, and `ExecutiveChildQualification.qualify` explicitly
refuses `parent_job_id != root_job_id`. Runtime instead scopes a leaf command
to its immediate coordinator and an aggregation dispatch to the aggregation
Job itself. H24 validates the Runtime form. It does not rewrite nested commands
to manufacture C17 compatibility or substitute a coordinator as a new root.

The [C29/C30 composition commission](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120#issuecomment-6680534154)
owns authenticated ingress and the trusted installed selected-child target.
Those owners must preserve immediate-coordinator selection and original-root
accounting, produce these coherent private facts, and consume the normalized
request through the existing claim/status paths. Any C17 nested qualification
change belongs to their separately authorized source integration.

Upstream Hermes `delegate_task`, asynchronous delegation and worker registries
have their own internal child lifecycle. Their IDs, summaries or terminal
messages are not Executive Jobs, leases, grants, results or review acceptance.
A separately permitted host-private cognitive helper must remain internal and
cannot enter this projection as a canonical child. This packet neither registers
nor invokes that helper and does not activate unmanaged delegation.

Before claiming real nested Executive subagents, retain evidence of authenticated
C17/C30 composition, the actual shared reservation/claim transaction, unchanged
root/depth limits, cancellation fencing, original-Attempt recovery after restart,
terminal/review acceptance and original-parent consumption. Source tests and a
published branch alone prove none of that runtime behavior.

## Verification and parent return

The focused suite uses only the standard library and the checked-in policy:

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest tests.test_h24_hermes_delegation_contract -q
```

Result: **55 tests passed**, exit 0. It covers depths 0–3 / depth-4 refusal,
quota 16, retained terminal occupancy, exact reserves, sibling overbooking,
duplicate commands, root/parent/cycle substitution, stale plan and authority,
grant/placement widening, cancellation, original Attempt/fence reconciliation,
partial aggregates, deferred dependencies, contiguous repairs, exact reviews,
canonical requeue and independent sibling progression. No test is skipped.

The additional focused regression run combines this suite with the existing
`tests/test_executive_coo_hierarchy.py`, using an already present pytest environment
with `--noconftest -o addopts='' -q -p no:cacheprovider`. This avoids unrelated
global portfolio fixtures; it does not replace the Runtime or hierarchy code
under test. Result: **96 tests passed plus 41 subtests**, exit 0, no failures or
skips, in 14.12 seconds. No package was installed. The exact execution command was:

```sh
PYTHONDONTWRITEBYTECODE=1 /workspace/scratch/16d3df696438/qa-venv/bin/python -B -m pytest --noconftest -o addopts='' -q -p no:cacheprovider tests/test_h24_hermes_delegation_contract.py tests/test_executive_coo_hierarchy.py --junitxml=../h24-hierarchy-results.xml
```

Validated source SHA-256:
`35e4a7a3a024878a8741ef645c3fe8f6beab30f13bbfdbf94c7999b619da0559`.
Validated test SHA-256:
`31dce05d1aad041f01dc0b14a59ebd8fbe670efc76110a02252a9e70b064101f`.
The parent's checkpoint additionally retains the published head and owned diff
checksum; the documentation does not attempt to embed its own recursive checksum.

Return the branch, exact head with this immutable base as its sole parent,
changed paths, test commands/results and SHA-256 of the following exact owned
diff bytes:

```sh
git diff --no-ext-diff --binary --full-index b54cb10e4abdd3766c62d4088f6a576ecfe80437 HEAD -- control_plane/hermes_delegation_contract.py tests/test_h24_hermes_delegation_contract.py docs/hermes/H24_NESTED_DELEGATION.md | sha256sum
```

The next integration action is to compose this source contract with the existing
C17/C29/C30 owner paths under their applicable grant and prove the actual
transaction/return path. H24-07 does not merge, self-approve, install, write
credentials, activate services or claim production serving.
