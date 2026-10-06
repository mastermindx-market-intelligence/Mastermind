# H4 — Claude principal to the existing governed child-work graph

## The actual missing integration

The original handoff's conceptual fabric operations describe a workflow, not five mandatory new
APIs. Existing `executive_fabric` already supplies a read surface [S06]. Current principal
submission, however, creates a bounded plain job [S13]. CooCycle accepts only an admitted
aggregation root with exact provenance [S14]. A pair of unrelated successful jobs is not H4.

The existing Runtime root constructor repeats strict intent/fingerprint/workspace validation and
keeps its root-creation capability private [S35]. Do not forge `owner_seat`, change a job's parent
fields after creation, pass its private capability from a plugin, or impersonate a CEO intent.

## Selected admission design

Add a **versioned, role-correct principal orchestration operation inside the existing COO
admission contract**. The selected design is a distinct operation, provisionally named
`submit_principal_orchestration`, alongside—not a silent replacement for—today's bounded
`submit_principal_intent`. Its public naming must be reconciled with the existing contract owner
before implementation; if an accepted equivalent is found, consume that exact operation instead.
The architectural decision is fixed: no generic new fabric service or parallel queue.

The initial public semantics are an assigned workstream, stable operation key, bounded objective,
department, priority and current bounded business-impact classification. Reuse existing validators
and size/range rules. Do not accept a caller-authored execution tree, role, root ID, worktree,
provider/account/host, budget override, source release permission or raw worker dispatch arguments.
The existing admitted planner produces the work plan through normal cycle admission.

Trusted host composition must derive the permitted execution/profile union, source scope, proof
contract, principal binding and mission authority generation from current owners. An existing
bounded-job mission delegation does not automatically authorize orchestration. Extend that
root-installed delegation through an explicit reviewed version/action-kind ceiling; fail closed
on old or missing delegation. No new scope string or permission is treated as accepted merely
because this document proposes the operation.

### Existing-owner changes, in order

1. **Pure request/envelope owner:** add a separately discriminated normalized orchestration
   request with its role-correct principal context. Reuse bounded validators and preserve v1
   behavior. Keep request identity stable on workstream + operation key; cross-kind reuse of an
   existing key conflicts rather than creating another effect. The action kind joins semantic
   fingerprinting and typed receipt validation, not an independent retry identity store.
2. **Installed host/final guard:** qualify current mission orchestration permission, exact
   principal, capability generation, source custody and live effect state. Derive the existing
   host execution binding/placement union and dialogue source from their trusted owners.
3. **Existing Runtime root constructor owner:** factor shared validated root assembly inside
   that same owner so both accepted CEO and role-correct principal issuers can reach the same
   atomic Job/Event path. Each issuer keeps its own closed validation and provenance. Generic
   `create_job` remains unable to mint aggregation roots; the private root capability never
   becomes model-visible. Preserve all worktree, host-binding and dialogue-source checks [S35].
4. **Receipt/replay and cycle validation:** extend current source-schema discrimination explicitly
   to accepted principal orchestration provenance. Preserve exact actor/principal context and
   every root/parent/depth/source-fingerprint check. The existing `creator: ceo_intent` component
   marker is not permission to relabel the human/principal actor as CEO. Update replay/status
   parsing together so a committed root remains reconcilable after response loss [S36].
5. **COO MCP/package:** expose only the accepted role-correct operation and status semantics,
   with matching native schema/profile qualification. Do not expose raw CooCycle methods or
   direct provider spawning. H2 catches a stale package/catalog generation.

The above is one reviewed compatibility unit with an explicit migration. It is not implemented
by the current six-tool backend. Required changes to closed root/provenance law are owned by the
existing admission/Runtime owners and remain a release gate, not a prompt-authorized exception.

## Current staged implementation — H4-A before H4-B

The current #1240 successor source now implements **H4-A only** in the existing pure
`coo_principal_request.py` / `coo_principal_envelope.py` owners.

H4-A establishes these source contracts without opening Runtime:

- the orchestration public request contains exactly `operation_key`, `objective`,
  `department`, `priority`, `workstream` and `business_impact`;
- it deliberately accepts **no** caller `execution_profile`, attempt budget, write paths,
  validation commands, tree/root/plan, branch/worktree, provider/account/model/host, release,
  service, session or raw dispatch selector;
- common business fields reuse the existing CEO-request validators; business impact is closed to
  the current v2 `routine / material / critical` values;
- bounded worker submission and governed orchestration use the **same stable request_ref and
  intent_id** for one `work_ref + operation_key`, so changing action kind cannot mint a second
  logical operation;
- the action kind is separately fingerprinted. Semantic changes under one key preserve request
  identity but move the action fingerprint, supplying the later sink with conflict/reconciliation
  evidence rather than retry identity;
- `derive_principal_orchestration_envelope` binds the existing
  `PrincipalAdmissionContext`, grounding, business semantics and orchestration fingerprint under
  the distinct source-only schema
  `mastermind.executive_principal_orchestration.v1`;
- the H4-A envelope has **no execution_contract**, no workspace root and no placement information.

H4-A is intentionally **pre-sink / inert**. The current `ceo_intent.validate_intent` rejects this
new orchestration schema. A regression test requires that refusal. Therefore H4-A cannot create a
Job/root through today's CEO or bounded-principal sink even if a model can construct the public
business request.

**H4-B** is the next shared-owner compatibility unit against the **current protected V1 COO graph**.
The deeper current-master recensus supersedes the earlier assumption that #1041 must merge first:
canonical Runtime/CooCycle already supplies the strict aggregation root, planner, plan admission,
work, independent review, repair, immutable aggregation handoff and exact dispatch/reconciliation
path required by H4. H4's first live proof can run with direct depth-1 children under that root;
it does not require #1041's extra depth-2/domain layer.

#1041 is therefore a historical/reference source for this program, not a merge prerequisite. Its
later Fable principal disposition (should_close_unmerged) is compatible with H4 because none of
the H4 acceptance cases require an intermediate domain. Do not copy #1041's schema bump,
provider-charge ledger, domain service-custody layer or depth increase into H4.

H4-B must authenticate/authorize the role-correct principal action kind, derive the current host
execution/profile/source/proof/placement binding from existing owners, and connect the H4-A
envelope to the existing protected strict-V2 aggregation-root constructor atomically. It must
preserve the same request/intent identity and reject cross-kind or semantic drift rather than
creating another root.

### Current protected-root finding

Current protected Runtime has one private strict root constructor,
JobRegistry.create_v2_orchestration_root(...). It accepts only mastermind.ceo_intent.v2, derives
one deterministic intent command, binds the reviewed execution/placement and Dialogue source, and
persists root orchestration provenance with creator=ceo_intent.

That creator is not decorative. Current source reasserts it across root decoding, child lineage,
planner creation, interactive-plan creation, plan admission, dispatch/requeue, aggregation handoff,
finite-control validation, terminal proof and replay. H4-B therefore must factor one closed
root-source discriminator/validator used by every one of those paths. A scattered collection of
creator == ceo_intent OR creator == coo_principal exceptions is not acceptable.

The new principal root source must have:
- a distinct closed source/schema identity for governed orchestration;
- the same stable principal request_ref / intent_id used by H4-A and principal status;
- its own action fingerprint including governed_orchestration;
- exact current principal binding / mission authority generation;
- the same reviewed host execution/placement and Dialogue-source facts required by CEO v2;
- deterministic root command/replay identity under the existing event store;
- root provenance that preserves the actual principal issuer rather than relabeling it CEO.

Existing CEO-v2 roots and every historical creator=ceo_intent receipt remain byte/semantic
compatible. Generic create_job remains unable to mint aggregation roots and the private root
creation capability remains non-model-visible.

### Current principal-ingress finding

Current executive_ceo_ingress already has App-only principal submit/status frames and one shared
replay/grounding/fresh-admission path. H4 should reuse those owners:
- keep the existing principal status identity because H4-A intentionally shares request_ref /
  intent_id across action kinds;
- add a separately discriminated fresh principal-orchestration submit frame rather than widening
  the existing bounded-intent request shape;
- derive a trusted final orchestration sink envelope from H4-A plus current host bindings;
- never coerce that envelope into CEO v2 merely to reach create_v2_orchestration_root;
- durable cross-kind reuse under the same request identity must conflict on action/root fingerprint
  instead of minting a second root.

### Current authority-owner finding

The installed COO application already has the correct final-guard shape:

- it authenticates through the existing role-correct COO resource policy;
- it obtains one trusted `AuthorityFact` from the installed `authority_provider`;
- it derives `PrincipalAdmissionContext` from that exact authority generation;
- it obtains current Mission Workspace facts and applies the existing `NewEffectGate`;
- only after those checks does it build/send a modifying ingress frame.

### H4-B0 current source slice — versioned principal-action authority ceiling

The branch now implements the first non-colliding H4-B unit in the existing installed authority
owner. It does **not** open the orchestration sink.

Current V1 mission rows remain byte/semantic compatible and implicitly authorize only
`bounded_intent`. A V2 row is identified by the exact additional fields
`authority_version=2` and sorted unique `principal_actions`. The closed action vocabulary is:

- `bounded_intent`;
- `governed_orchestration`.

The existing `generation(row)` continues to hash every immutable mission-row field except dynamic
`enabled`. Therefore adding/removing/changing the V2 action set changes the same canonical
`authority_generation_digest`; no second action-policy digest or store is introduced. Old V1
generations cannot silently gain orchestration.

`AuthorityFact` now carries the normalized action tuple and the read-only mandate projects it under
`capability.principal_actions`. The current installed bounded-intent host guard and COO app both
require `bounded_intent` before today's submit path can approach Executive ingress. An
orchestration-only generation therefore refuses the current bounded tool pre-effect, while status
and mandate reads remain readable.

H4-B0 satisfies the authority-side requirements:

1. the action set participates in the existing authority generation identity/digest;
2. `governed_orchestration` is absent by default from V1 bounded-only generations;
3. the installed COO app re-reads the same current authority generation at its modifying boundary;
4. action-grant changes necessarily move the generation digest;
5. no action grant encodes provider/account/host/tree/worker selectors; and
6. no Runtime/root constructor, CEO ingress, CooCycle, MCP tool catalog or production config is
   changed by this slice.

### H4-B1a published source slice — one closed Runtime root-source discriminator

With #1041 closed unmerged, the branch first centralized the existing V1 orchestration lifecycle
around one closed Runtime root-source discriminator. The published B1a head still admitted only
`ceo_intent`; child provenance remained exactly `coo_cycle`. CEO-specific finite-control,
maintenance/source-capacity and CEO replay paths deliberately remained CEO-only.

### H4-B1b current source candidate — principal root creation, cycle admission and Fabric readback

The current source candidate advances that foundation without exposing a production caller.

The closed root creator vocabulary becomes exactly:

- `ceo_intent`;
- `coo_principal`.

The pre-persistence source discriminator remains role-sensitive: only reviewed root creators may
create the aggregation root; plan/work/review/repair children remain `coo_cycle`. Existing CEO-v2
receipts remain unchanged.

The H4-A orchestration bundle now includes a canonical full `bundle_digest` over its normalized
request plus trusted principal/authority/grounding envelope. Any mutation to principal binding,
authority generation, grounding or business semantics moves that digest; the Runtime source digest
binds the exact bundle generation.

`CooHostProvider.guard_orchestration(...)` is the source-only current-effect guard. It revalidates
the canonical H4 bundle, current root-sealed mission row, principal binding, authority generation,
explicit `governed_orchestration` action grant, current Mission Workspace and the same post-read
source snapshot before permitting the root effect.

`JobRegistry.create_principal_orchestration_root(...)` is a separate source-only constructor. It:

- validates the canonical full H4 bundle;
- uses the same existing `command_id_for(intent_id)` namespace as bounded COO work, so cross-kind
  reuse under one `work_ref + operation_key` cannot mint a second Job/root;
- invokes the fresh host admission guard before the Runtime effect;
- creates exactly one depth-0 `aggregation` root with creator `coo_principal`;
- preserves the actual principal/request/action/authority/grounding facts in the existing
  `JOB_CREATED` provenance;
- starts at A0 / READ only, with no write paths, validation commands, branch or worktree;
- accepts no caller provider/account/model/host/tree/worker selector;
- uses the existing private V2 root-creation capability internally, so generic `create_job`
  still cannot mint orchestration roots; and
- has **no production caller** in the current source tree.

The first review of B1b exposed two split-brain generic consumers and repaired them:

1. `CooCycle.run_once()` still required literal `creator=ceo_intent`, so a valid principal root
   immediately became `invalid_root`. It now consumes the same central reviewed-root discriminator.
2. the bounded Runtime/Fabric observer remembered and point-read only CEO root creation events. The
   bounded observer now accepts either reviewed root source while validating each creator's exact
   event schema separately, and `fabric_job_view.v2` validates principal-root workstream provenance
   directly from the immutable `JOB_CREATED` record. The CEO-specific
   `executive_inbox.ceo_intent_provenance` helper remains CEO-only.

A principal B1b root can therefore create the existing deterministic planner through CooCycle and
appear with that planner in the canonical bounded `executive_fabric` projection. It still cannot be
claimed as live orchestration.

The source-only proof currently includes:

- 25/25 discriminating H4 bundle/root/source tests;
- 481/481 dependency-free H4/Runtime/Fabric tests, with one unrelated host-specific sealed-worker
  process-identity fixture deliberately deselected rather than weakened;
- 125/125 full Phase-1F-C CooCycle + Fabric-v2 compatibility tests.

The local host cannot collect the signed COO ASGI suite because `jwt` is absent; hosted CI remains
the integration owner for those app tests.

### H4-B2 still required — trusted host binding, dispatch, ingress and reconciliation

B1b deliberately does **not** derive or install the reviewed host execution/placement binding that
real planner/work dispatch requires. Its root currently contains only Runtime's ordinary default
quota-class normalization, not an admitted provider/model/host/profile selection.

The existing Executive service's strict bound-root/dispatch path is still CEO-root-specific and the
current principal constructor has no production ingress caller. Therefore B2 must:

1. derive the current host execution/profile/source/proof/placement binding from existing owners,
   not from the model request;
2. carry the current Dialogue source through the existing trusted host composition;
3. extend the service's generic bound-root/dispatch validation to the reviewed root-source
   discriminator without widening CEO-only finite/release paths;
4. add a separately discriminated principal-orchestration ingress frame after the overlapping #1147
   ingress carrier is accepted/released;
5. preserve the existing principal `request_ref / intent_id` status and same-command reconciliation
   semantics after response loss; and
6. prove an actual planner/child dispatch only after those exact source gates and H1/H3 native
   admission are accepted.

Finite-drive admission/arm, CEO intent replay and C2 CEO-source maintenance remain CEO-only unless
their own owner later admits a separate principal use case; H4 does not need to widen them.

**H4-C** later exposes only the accepted orchestration operation/status through the COO MCP/package
after H1 native profile/schema qualification. No raw CooCycle method, worker selector or
provider/account selector becomes model-visible.

## Normal execution and consumption

The principal selects an outcome and quality/evidence constraints inside its mission. Model Router
selects an eligible capability tier; Capacity ranks eligible placements under existing cost,
quota, host and review reserves. The principal must not select an account to bypass a refusal.

CooCycle owns planner creation, plan admission, child/review/repair Jobs, finite budgets, dispatch
reconciliation and aggregation handoff [S14–S16]. OperatorHarnessOrchestrator owns the native
generation/turn/resume path [S17]. The package reads material canonical outcomes; it does not keep
its own child state table or call `run_once` in an LLM polling loop.

After a child returns, verify its exact Job/Attempt/revision and result receipt, consume an
available result without waiting for unrelated siblings, and advance an independent principal
integration decision. A failed review uses the existing repair lineage and reserved allowance.
A second identical failure without new evidence triggers the existing reassessment rule, not
another fresh child operation. Final aggregation must bind accepted current child revisions.

A plugin-generated `fabric_continue` alias must not acquire new retry/dispatch authority. Any
continuation action must be an existing admitted cycle/turn operation with current source and
binding facts. Native ephemeral subagents are not a substitute for durable governed children.

## Exact first live proof graph

Select a disposable, useful engineering-validation mission, not production code or credentials.
The proposed two independent outcomes are:

**A — reviewed bounded implementation:** a small deterministic local fixture implementation
with an explicit validation contract, confined to `proof_fixture/implementation/`. A synthetic
review exercise may intentionally provide a fixture revision with one documented unmet acceptance
condition; it must be clearly labeled, remain non-production, and be repaired through the normal
review/repair path. Do not intentionally inject a defect into live code to demonstrate repair.

**B — read-only evidence analysis:** evaluate a separate immutable contract/evidence input and
return structured findings; no source write grant. Its input/output ownership and logical scope
are disjoint from A. A mandatory-review requirement discovered for B overrides this proposed
classification; do not drop that review to make the graph fit.

Current canonical reservation is 1 planner + 9 slots for A's work/review/repair family + 1 for B
= **11**, below 16 [S15]. Two fully reviewed work steps would reserve 19 and refuse. These numbers
are observed current policy, not new constants for a plugin. Recompute with the admitted policy
at execution time; material policy change requires revalidation.

Router/Capacity must identify two eligible non-identical worker lanes. Qualification fails—not
falls back to claiming success—if only one lane is eligible. Same provider may be permitted by
current routing law, but the two actual admitted lane identities must differ; record what differs
without publishing provider-native session coordinates. Do not force cross-provider spend merely
to obtain two names when the acceptance contract only requires non-identical eligible lanes.

While A and B execute, the principal performs a concrete independent integration task: adjudicate
how their outputs meet the predeclared parent acceptance contract, prepare an integration mapping
without editing either child's paths, and consume each material return. This is useful judgment,
not a delay loop or duplicate implementation.

## Failure and recovery matrix

| Case | Required observation and continuation |
| --- | --- |
| Two simultaneous identical submits | One canonical root/command; later caller consumes duplicate receipt. |
| Response lost after root transaction | Original request status identifies the same root or preserves uncertainty; no second root. |
| Wrong workstream/principal/capability | Refuse before new root or child creation. |
| Planner proposes overlapping writes | Existing plan/source owner rejects; do not defer the collision until Git merge. |
| Worker lost/rate-limited | Existing Runtime/effect owner reconciles; no provider/account switch around a started modifier. |
| One child completes, one waits | Consume ready evidence and continue safe principal work; no all-sibling barrier unless dependency requires it. |
| Review requests repair | Exactly the existing revision/repair lineage; rejected old revision cannot reappear as accepted. |
| Parent interruption | Recover exact root/Attempt/generation and unconsumed returns using current owners, not a new chat-created graph. |
| Budget or child reserve exhausted | No new work; settle incumbent obligations and return precise existing-owner gate. |

## Acceptance

Cases H4-01 through H4-12 bind the required proofs. A real admitted principal must obtain the two
canonical child outcomes on the two lanes, perform useful independent work, consume a genuine
review/repair lineage and accept the current integrated result. A plan fixture, two direct API
jobs, a provider-native Task tool, or two Slack deliveries is insufficient. No Chairman provider,
account or session selection should be needed in the ordinary accepted route.

Before live work, source contract review must accept the new principal-root seam and dependency-
complete integration tests must pass. H1/H3 admission and exact runtime capacity remain gates.
The current session is planning this integration; no root, child, provider or review worker was
created to claim this acceptance.
