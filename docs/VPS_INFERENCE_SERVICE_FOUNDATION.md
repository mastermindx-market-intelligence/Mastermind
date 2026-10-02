# VPS inference service foundation — BUILT_NOT_PROVEN / SOURCE_ONLY / EXECUTION_NOT_YET_COMPOSED

Retained source base: `8aa115c7e6d3ef9685d140256f5aa843cc0e4437`.
Current protected compatibility pin: `b3627c580dd37ac1c167f59ac4b7555a4330edef`.
The candidate has been synthetically integrated on that exact protected head with its selected regression suite green. Protected movement from the retained base is path-disjoint from this foundation-owned surface after the shared-server collision was removed; the later `remote_attempt_transport` movement is an accepted dependency for the execution slice, not part of this foundation.
The semantic slice is source-only. Source publication or a PR does not imply installation,
authentication, provider execution, call-site cutover, deployment, selection or production proof.

## Capability and admission

- `svc-vps-inference` is an explicitly enrolled non-human, non-CEO service identity
  alongside unchanged `svc-site-maintenance`. Emitter and sink share the closed
  registry. The service ceiling is READ/RESEARCH, authority A0, seat/escalation coo.
- Exactly three tools: `submit_service_intent`, `service_intent_status`, and
  `executive_fabric` restricted to `view=result`. Submit accepts only operation key
  and objective; department, priority, research profile and one attempt are fixed.
  No caller-controlled actor, provider, writes, commands or generic Job read exists.
- The dormant service App/profile contract reuses existing JWT verification, audit,
  CeoIngress transport and Fabric readers. Native MCP route mounting is deliberately
  deferred because open PR #1112 currently owns integrations/executive_mcp/server.py;
  this slice does not race that shared server file. Host configuration must supply the existing OAuth
  ResourcePolicy, shared JWKS, and reloadable exact policy/issuer/subject/client/
  resource/scope binding to `svc-vps-inference`. The scope is
  `mastermind.executive.service.inference`; service subjects are disjoint from CEO
  subjects. Every operation is verified again before reply; revocation withholds results.
- `ceo_intent.submit_intent(..., service_admission_guard=...)` requires a trusted
  host-owned synchronous guard for FRESH `svc-vps-inference` creation. The sink
  invokes it immediately before Job creation, without await or retry. Missing,
  noncallable, raised, asynchronous or non-None verdicts refuse. The guard receives
  a defensive envelope copy. Callback presence is not authentication authority.
  The future host must synchronously recheck current binding, arming and readiness.
- `executive_ceo_ingress._submit` forwards that keyword-only host input;
  `executive_inference_ingress` does not run an earlier substitute guard. Direct
  `executive_service_principal.submit` cannot bypass the sink requirement.
  Accepted duplicates resolve before the guard and status is read-only, so both
  remain readable while disarmed. Historical maintenance admission stays unchanged.
- Host service composition is absent. All candidate `executive_service.py` changes
  were removed; `executive_runtime.py`, `executive_coo_cycle.py` and related #1041
  domain execution remain owned by #1041. Source handler fixtures are not proof
  of an installed App-peer binding, listener route or running service capability.

## Identity, uncertainty and result discovery

The public `executive_service_principal.service_intent_id` binds schema, enrolled
principal and operation key. The canonical sink fingerprints the full envelope,
including grounding; changed content under the same key conflicts. Status reconciles
an accepted operation without requiring current grounding or fresh admission.

The service status response adds optional `terminal_result_ref` alongside its
unchanged canonical `receipt`. Absence means null. A non-null value has exactly:

```json
{
  "root_job_id": "JOB-001",
  "job_id": "JOB-001",
  "attempt_id": "ATT-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "result_envelope_digest": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "orchestration_role": "aggregation",
  "validation": "UNVALIDATED"
}
```

Both Job ids must equal the Job in the original service operation receipt. This
is the canonical Fabric result-ref tuple plus its existing role/validation tags;
it is navigation, not validated result content or acceptance. No store was added.
`validate_terminal_result_ref` and `terminal_result_ref_from_index` are pure,
operation-bound helpers for a future host resolver.

**This independent handler returns null honestly.** Ordinary service v1 Jobs are
not Fabric aggregation roots, and this foundation intentionally does not pretend
that admission is execution. The terminal reference is retained only for the
agentic/orchestration lane: if a future admitted service operation uses an existing
COO/Operator aggregation root, its host resolver may derive the reference through
`fabric_job_view.RESULT_REFERENCE_INDEX_SCHEMA` /
`compose_fabric_result_reference_index` over the canonical bounded root observation.
No newest-child selection, synthetic root or parallel result store is permitted.

The preferred routine-inference execution lane is smaller: the accepted service
request becomes one ordinary role-null READ/RESEARCH Executive Job, Runtime/Model
Router/Capacity select the eligible worker, and the already-merged
`AttemptBoundRemoteWorkerAdapter` binds the exact claimed Codex/Claude worker only
after canonical claim. The common Supervisor owns the Attempt and terminal Job
result. This is the existing Subagent Fabric and avoids a planner/reviewer/
aggregation tree for every small classifier or JSON reasoning call. The host
execution slice still must prove a trusted clean worker workspace, host-owned route
constraints, exact result contract, and service-only dispatch admission before any
call-site cutover. Agentic/tool-using research may instead use the existing COO/
Operator domain path. Interactive `/chat` remains a separate streaming lane.

`brain.fabric_inference_client.FabricInferenceClient` accepts an existing configured,
authenticated async tool caller. Submit sends once. A lost or malformed reply raises
`EffectUnknown(operation_key)`; reconciliation sends only status, including after
restart. Missing status never permits resubmission. Canonical conflicts remain
`FabricConflict`. There is no credential acquisition, retry loop, polling or provider
fallback. The caller retains its operation key in its existing operation record.

`result(operation_key)` first reads status and consumes only its operation-bound
terminal reference. It accepts no caller-selected child. The App independently
rereads status and requires the requested tuple to equal the discovered reference.
Null references fail closed before a Fabric read. Results must have the exact
closed projector shape, root Job selection, aggregation role, COMPLETED execution,
acceptance exactly NOT_PROJECTED, AVAILABLE complete content, SAME generation and
empty omissions/degradation/bounds. The returned closed projector document retains
role, execution_status, acceptance, role_result_digest, generation and content.
Review/work/plan/repair children are never terminal service answers.

## Remaining coupling and gates

CeoIngress has no public adapter seam for the existing `_submit`, `_backend_call`,
`_resolve_status_intent`, `_observe_trusted_grounding`, `_exact_top_keys`, and
`_coerce_grounding_shape` helpers. Their reuse is follow-up coupling to promote into
an owner-reviewed public interface, not authority. The new identity derivation uses
the public service API. No new private Runtime API is introduced.

The remaining gates are separate:

1. Compose the host execution slice with the incumbent #1041 service/runtime owner
   instead of racing its files. For routine inference, admit only exact
   `svc-vps-inference` Jobs to the existing Supervisor and post-claim
   `AttemptBoundRemoteWorkerAdapter`; preserve #1041's COO/Operator domain path for
   agentic research rather than forcing every call through an aggregation root.
2. Define a trusted service execution binding: fixed clean worker workspace/base,
   host-derived Model Router/Capacity constraints, no caller provider/model/worker,
   and an operation-bound direct Job result. The current 4,000-character CEO
   objective ceiling must not silently truncate real prompts; a larger bounded
   service payload needs an owner-reviewed carrier before broad cutover.
3. Compose the native MCP route only after #1112 shared-server custody clears (or its
   accepted successor provides a composition seam), then qualify the installed
   Executive/App/listener/service binding, synchronous admission owner and exact
   service-only dispatch gate.
4. Service OAuth/client enrollment through existing authentication machinery.
5. Provider/remote-worker-gateway arming and qualification through the existing
   shared Capacity and remote-worker owners; no direct-provider fallback.
6. Autonomous/background call-site cutover after one real direct-Job canary;
   `brain/cli_bridge.py` and `brain/provider_waterfall.py` remain unchanged here and
   their incumbent PR owners must be composed rather than overwritten.
7. Separately accepted interactive streaming for `/chat`; the current interface is
   terminal-result only.
8. Exact authorized deployment and real VPS canary proving admission, placement,
   claimed worker identity, execution, result consumption and uncertainty recovery.

## Local validation

Focused offline tests cover new service/client modules, CeoIntent, service principals
and CeoIngress. Fixtures use local signed JWTs, temporary runtimes and explicit
in-process adapters; they do not authenticate against an installed service or call
providers. Regression cases cover late revocation at the final grounding read,
sink guard refusal and direct-submit bypass, readable disarmed reconciliation,
review-child rejection, honest null discovery and exact result/reference binding.
These are source checks only, not runtime or provider qualification.

Repair validation inside the Codex sandbox: 197 focused tests passed; 99 existing
socket-dependent tests were blocked by the sandbox's Unix-socket bind denial and
were not claimed there. Independent host-shell rerun on the authorized M2 Studio executed the complete
selected regression set, including those socket paths, with **100% pass / rc=0**.
A synthetic current-protected integration on b3627c580dd37ac1c167f59ac4b7555a4330edef
also passed the same selected set at **100% / rc=0**. The existing dependency-complete
local Python environment was used without installation or provider/network calls.
`git diff --check` passed.
