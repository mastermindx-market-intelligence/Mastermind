# VPS inference service foundation — BUILT_NOT_PROVEN / SOURCE_ONLY / EXECUTION_NOT_YET_COMPOSED

Retained source base: `8aa115c7e6d3ef9685d140256f5aa843cc0e4437`.
Last protected compatibility pin before this binding slice: `bdf2a972e68a70270c24d4b5d61a4d60edc4f288`.
The prior semantic head integrated on that exact protected head with its selected regression suite green and zero owned-path overlap. This binding slice remains source-only until its own fresh protected-base integration receipt is recorded; no ancestry-only merge is required.
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
- `executive_ceo_ingress._submit` forwards that keyword-only host input. Direct
  `executive_service_principal.submit` cannot bypass the sink requirement.
  Accepted duplicates resolve before the guard and status is read-only, so both
  remain readable while disarmed. Historical maintenance admission stays unchanged.
- Fresh `svc-vps-inference` admission now also requires a separate synchronous
  host execution binding. `executive_inference_execution` derives branch/worktree
  from the service intent id and derives research route/profile identity from the
  existing Model Router; only trusted host composition supplies the exact base SHA
  and eligible quota classes. The sink rebuilds and compares the binding before Job
  creation. The caller still cannot choose provider/model/worker/worktree, and the
  binding never enters the caller envelope/fingerprint. Duplicate/status replay
  never reruns live routing.
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
request now becomes one ordinary role-null READ/RESEARCH Executive Job with the
host-derived worktree/base/routing-profile/eligible-quota binding persisted in its
existing Job fields. Runtime Capacity then intersects quota eligibility with the
bound model aliases, routing-policy version and execution-profile digests before
claim. The already-merged `AttemptBoundRemoteWorkerAdapter` can bind the exact
claimed worker only after canonical claim. The common Supervisor owns the Attempt
and terminal Job result. This is the existing Subagent Fabric and avoids a planner/reviewer/
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
   instead of racing its files. The source binding contract now exists; the host
   still must materialize/reconcile the exact credentialless workspace, provide its
   reviewed current base/quota set, and admit only exact `svc-vps-inference` Jobs to
   the ordinary Supervisor/Attempt path. Preserve #1041's COO/Operator domain path
   for agentic research rather than forcing every call through an aggregation root.
2. Add a versioned pure-inference worker result contract and operation-bound direct
   Job result projection through the existing Supervisor/Runtime owners. The generic
   role-null worker schema has `additionalProperties:false` and no dedicated answer
   field, so treating `summary` as the model answer is explicitly forbidden. The
   current 4,000-character CEO objective ceiling must also not silently truncate real
   prompts; a larger bounded service payload needs an owner-reviewed carrier before
   broad cutover.
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
sink guard refusal and direct-submit bypass, missing/async/forged host execution
bindings, exact research-route/worktree persistence, duplicate reconciliation without
rerunning live routing, readable disarmed reconciliation, review-child rejection,
honest null discovery and exact result/reference binding. These are source checks
only, not runtime or provider qualification.

Repair validation inside the Codex sandbox: 197 focused tests passed; 99 existing
socket-dependent tests were blocked by the sandbox's Unix-socket bind denial and
were not claimed there. Independent host-shell rerun on the authorized M2 Studio executed the complete
selected regression set, including those socket paths, with **100% pass / rc=0**.
The prior #1147 semantic head also integrated on
`bdf2a972e68a70270c24d4b5d61a4d60edc4f288` at **100% / rc=0** with zero
owned-path overlap. After the host-binding source changes, the expanded local
Executive/App/MCP regression selection again completed **100% / rc=0**. A fresh
current-protected integration receipt for this new semantic head remains required
before release. The existing dependency-complete local Python environment was used
without installation or provider/network calls. `git diff --check` passed.

## October 12 source recovery and protected-base composition

The original eight-path request-binding candidate has been recovered byte-for-byte and published on this original carrier as **b1958754a0dc8b18361ddc2f9eed718d07a44482**, parent b832ee7d67f7a5060d7088dcb5a257328728f041. Its exact pre-commit patch SHA256 remains **9ff757d2b9348f71926a6f3aacdfd49f790d70f40759f2118b388fb4fd1cead5** (35,723 bytes). No replacement implementation, branch or request identity was minted. The located worktree is under the older Cluade/Mastermind repository, not the GitHub/Mastermind checkout that the earlier search used.

The service client now takes the existing closed `inference_request` alongside operation_key/objective. Its normalized contents participate in immutable provenance and same-operation conflict handling; the business objective is not an oversized prompt carrier. This is SOURCE-ONLY request binding, not a mounted/armed service, worker execution or result-consumption receipt.

The recovered original source ran **136 passed / 1 failed** across the five existing I/O/client/service/transport modules. The one failure is the previously held `test_direct_emitter_cannot_bypass_sink_guard`, whose request lacks inference_request and is rejected earlier by the principal validator. Its refused fixture edit remains unapplied. Do not modify admission order merely to satisfy that fixture and do not remove/deselect the case to claim a full-green source.

A history-preserving merge of protected **1f5befa44487ffb7ac2a0ca44ccd85c7c9da1355** is composed in this carrier. Exactly two textual conflicts concerned old source-line citation coordinates in `executive_service_principal.py` and its test. The resolutions retain both semantic sides and rebind only those quoted predicates to their actual final ceo_intent locations: L1038, L1436, L1345 and L1095. The existing service guard, host-binding requirements, Runtime owners and known held fixture remain unchanged by conflict resolution. The new protected 85807cf48e29e2fe5df19534d6b181fc25b9746f changes only acceptance-maintenance and its tests; no unsupported claim of whole-latest-tree verification follows.

The expanded composed-source selection ran **234 passed / 1 failed**, including existing CeoIntent and ModelRouter coverage. The same held fixture is the only failure; no new failure appeared. Candidate whitespace checks against the protected parent pass. Checking the entire old-base merge diff exposed existing upstream whitespace in unchanged font-license/source files; those protected/license bytes were not rewritten. An initial conflict resolver refused before file writes because its pattern count did not match; the conflict state was reconciled and a line-state parser resolved the exact two files. This tooling error was not a platform refusal or an unobserved write.

The earlier dependency text naming #1041 and #1112 as open merge blockers is superseded: #1041 is closed unmerged; #1112 is merged. Current protected V1 and role-correct service admission remain the intended owners. The actual standing M2 Fabric was separately located under the Macro Dashboard handoff-kit root (Bot renewal #1357 architecture §14); Executive's single worker row is not its entire inventory. Current service identity, exact host admission/mount, fresh eligible provider capacity, direct-result projection/consumption, actual Bot cutover, streaming and production canaries remain unproven. The related execution-002/stack worktrees are retained reference candidates, not copied or adopted here.

No source-capture/snapshot repair previously refused in #1357 was replayed through this carrier. No queue, provider, credential, auth enrollment, production account or deployment state changed. This remains **WIP/HOLD / REQUEST_BINDING_PUBLISHED / SOURCE_COMPOSITION_TESTED_WITH_ONE_KNOWN_FAILURE / MISSION_COMPLETE:false**.

## Next source slice: task-aware research through the existing ModelRouter

The Bot/service source canary on integration tree d4a4a38da6240c606d83deb944321523aa183a81 proved lossless 26,525-byte context admission, exact duplicate/conflict semantics, restart/status-only recovery, lost/tampered response handling and no false completed answer. It also causally exposed a gap: Bot comparative research requests elevated task fit, but the current service host always binds routine research. This is not an actual worker execution and must not be described as adaptive routing already working.

Implement a versioned **v2 inference request** with exactly one additional high-level field, `task_kind`: `evidence_extraction`, `comparative_analysis`, or `contradiction_adjudication`. The existing v1 four-field request and bytes remain unchanged; unknown schemas, raw model/provider/host/account fields and extra keys remain rejected. The request stays under the existing 48KiB bound. Named task intent is not a model selector or runtime authority.

The existing host-binding owner maps extraction to the existing research/routine/low WorkRequest and comparison to research/elevated/medium, then consumes the incumbent ModelRouter and existing quota/profile/grant constraints. Contradiction adjudication yields the existing frontier-lead classification and must refuse this ordinary-Job lane with a clear governed-judgment requirement. It cannot silently downgrade, dispatch a frontier child, invent a new graph or borrow CEO authority. A later accepted governed consumer remains necessary for that task.

The canonical sink rebuilds the exact expected execution binding from the normalized request that is already bound to the operation fingerprint. A v2 comparison paired with a stale routine host binding must be refused before Job creation; changing task kind under the same operation must conflict. The optional trusted host `inference_request` input is provided to the existing build/validate functions, not exposed as an arbitrary routing/credential choice. Host factories must pass their exact request into binding construction. Default v1 callers remain byte/route compatible.

Tests precede implementation: v1 invariance, closed v2/negative shapes, actual incumbent route aliases, refusal of frontier-in-ordinary-lane, stale/downgraded binding refusal with zero Jobs, real Runtime preservation of the comparison route, operation conflict after task mutation, and zero dispatch/Attempt creation. No `test_direct_emitter_cannot_bypass_sink_guard` edit is part of this slice; its prior refusal remains held. Current #1357 snapshot repair gates also remain separate and are not bypassed.

### Task-aware source implementation and review result

The v2 slice is implemented on this original carrier. Existing v1 callers preserve their normalized request and routine route; v2 extraction and comparison resolve distinct first-lawful suitability tiers through the incumbent ModelRouter. The public tool's schema comes from the I/O owner, not a divergent duplicate. The sink validates the host's binding against the actual fingerprinted request, refusing mismatched or downgraded task placement before Job creation. Contradiction adjudication is explicitly rejected from the ordinary-Job lane and still needs the separately admitted existing governed-judgment path. No provider/model/account/host selection field, queue or autonomous spending permission was introduced.

New tests: 23 task-fit cases, including both request-schema versions, unknown/selector fields, byte limits, real temporary Runtime admission and wrong-task operation conflicts. Focused regression: 202 passed. Full expanded selection: **257 passed / 1 known failed**, with the original refused fixture unchanged and not deselected. Both extra source citation locations were updated to the actual shifted sink line; no guard weakening followed from the citation correction.

Independent native read-only review completed on session 01a12dd9-1161-71d0-8d17-cd24d9342e01, process exit0. All seven source hashes matched the frozen review manifest before and after. Verdict: **no actionable finding within the inspected seven-file slice**. The reviewer inspected source and ran pure functions with injected routing/persistence; it did not independently run pytest, current Router configuration, installed auth/host/capacity or providers. It did not approve the held fixture or #1357 snapshot defects. Source hashes, final report and actual limitations are preserved in `tests/fixtures/vps_inference_task_fit/`. This is consequential native review, not paid-Fabric execution or independent served-model/billing attestation.

Task-aware request publication, installed schema selection, host factory request binding, current service identity, eligible capacity, real worker execution and returned-answer consumption remain distinct. V2 requires host factories to call build_execution_binding with their exact inference_request. An old routine-only factory refuses comparative requests at the sink rather than silently satisfying them with a weaker route. Source-only qualification does not arm or deploy that factory.
