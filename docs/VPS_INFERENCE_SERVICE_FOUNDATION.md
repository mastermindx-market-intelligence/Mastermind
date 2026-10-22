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

## Continuation: consume the admitted request and return its exact answer

Starting service source09719bb7 and Bot source1d7c04b0 are both clean/published. Current hosted failures were inspected rather than rerun: Bot has the same twelve known correctness failures; service has the single held fixture. Security analyses passed. No permission-clearing inference is drawn from changed modes or new CI. Protected master25c4b792 has no movement in this slice's execution/result source paths compared with the already composed1f5befa4; the compatible bootstrap pin remains cbc750.

Next bounded phases reuse existing owners. First, the Supervisor must fetch the exact normalized inference_request from the immutable JOB_CREATED service provenance, bind that request into the worker prompt, and select the already-existing dedicated `answer` result schema. Generic worker prompt/result behavior must remain unchanged. Public/caller Job constraints cannot impersonate that provenance. Research payload fields remain data beneath the worker's actual grant; requests cannot inject tools, network, writes or capital authority. No new launcher or provider fallback is introduced.

Second, direct service completion belongs to the existing Runtime terminal result, not JobPayload.summary, an aggregation graph or another result store. Reuse the I/O owner's result_document/reference schemas and the existing Supervisor collection/exit/assignment evidence. A service completion must be bound to original Job/current Attempt/Worker/request, must be terminal/validated, and must fail closed on output schema/digest/limit errors. Queued/running/failed/cancelled/old-attempt results cannot become answers. A bounded read follows exact service operation and optional expected reference in one existing Runtime observation; no arbitrary path read.

Third, expose only the direct operation-bound view through the existing `executive_fabric` read plane/service profile, keeping status small. The client must independently bind result reference, Job/Attempt/Worker and the original operation, and read-only status/result must never retry submission. Existing aggregation result compatibility is separately preserved; role-null service jobs are not falsely labelled aggregation. Installation, OAuth scope/subject, actual provider execution, active Bot cutover and production remain separately held.

Tests first: generic-vs-service prompt/schema selection; long/unicode payloads and immutable source binding; malformed/foreign service provenance refusal; actual Supervisor fake-adapter collection and Runtime persistence; stale attempt/cancel/oversize/tamper/restart cases; exact direct status/read/client round trip; no full answer in a status reply and no new storage/queue. Use temporary source fixtures only. The previously refused snapshot/source-capture repairs and old service fixture are out of scope and not replayed.

An independent native architecture reviewer is checking exact source09719bb7 on process9545, read-only with children disabled, returning to `.venv/service-result-design-review.md` in the existing Bot workspace. It has no implementation authority. Parent advances disjoint tests while retaining the exact return obligation; no background daemon is claimed.

### Execution prerequisite refused; independent answer-integrity slice

The new Supervisor tests executed on unchanged source: eight failures and two controls pass, proving the request is currently omitted from prompt/schema and bad service provenance is not discriminated there. The attempted `request_for_job` source edit was explicitly rejected by platform safety checks before dispatch. A direct diff/definition check confirmed no change to executive_inference_execution.py. It is held; do not retry it elsewhere, move it to a different mode or reconstruct it under another filename. A corrected synthetic Attempt identifier in the new tests follows the actual ATT-32hex grammar; that fixture correction is not an execution implementation.

The independent architecture reviewer completed on original process9545 with source09719bb7. It conditionally supports the existing Runtime.result_json route, but requires exact creation-event, current-Attempt/lease, output/collection/exit and bounded-observation validation. It also identified distinct byte ceilings in the reused transport: direct I/O192KiB, full wrapper16KiB, socket32KiB and public read plane256KiB must not be conflated. That implementation/installation lane remains unbuilt, not silently replaced.

Proceed independently on the existing I/O and consumer owners: add a backward-compatible v2 direct-result reference that records BOTH the raw provider-result digest and a separately named canonical structured-content digest. This closes the old document's inability to verify returned answer/content against its reference without pretending canonical JSON equals original raw bytes. Existing v1 reference/document behavior remains unchanged for legacy consumers. The new direct client path requires v2; a self-asserted digest is content integrity, not producer authentication or execution proof.

The service's existing contract validates a direct answer view only against the original operation/receipt fingerprint, exact status-selected reference, completed state, SAME Runtime observation, bounded complete payload and requested output ceiling. A new Python client `answer(operation_key, objective, inference_request)` normalizes and checks the caller-retained original request against the receipt before any result read, then uses the existing executive_fabric tool's dedicated service selection. This is not another tool or store. Generic/aggregation `result()` behavior remains unchanged. The client performs status/read only, never submit/retry; error/cancellation paths cannot become new work.

Tests first: v1 identity invariance, separate raw/content hashes, Unicode canonical identity, substituted content, foreign operation/Job/Attempt/Worker/reference/fingerprint, partial/stale/oversized output, changed original request, missing ref, no-submit behavior and cancellation. This isolated typed-client/contract work does not implement or bypass the refused Supervisor request reader, Runtime completion, read-plane producer or installed auth path. No active Bot/provider call site is cut over.

### Direct-answer contract/client implementation and executed evidence

The existing I/O owner now offers backward-compatible result-reference v2 with distinct `result_sha256` (original raw provider bytes) and `content_sha256` (canonical structured result). Result-document construction and validation recompute the latter and reject substituted answer content. Omitting the new digest preserves the existing v1 shape. Neither digest proves execution or authenticates a producer; the missing Supervisor/Runtime host path must establish that separately.

The existing service contract now validates a bounded complete direct-answer view against operation-derived identity, original admission fingerprint, exact status-selected Job/Attempt/Worker/reference, unchanged Runtime observation, requested output ceiling and explicit NOT_PROJECTED acceptance. The new read-only client `answer` first validates the caller-retained original objective/request against the reconciled receipt, then reads only that exact reference through the existing tool name. Wrong or missing reference, changed request, partial output, timeout and cancellation never submit or retry. Existing generic aggregation result() remains unchanged. The actual service App/MCP/Runtime producer of view=service_inference is not implemented or installed by this slice and an old backend remains unavailable rather than producing a guessed answer.

Tests exposed and corrected two issues in the new client implementation: an import of the broad control_plane package violated the existing no-direct-provider import guard, so the client now imports only its existing contract owner; a callback could mutate the passed reference dictionary before validation, so it now receives an isolated scalar-field copy while the original expected reference is retained. The guard was not loosened, and the mutation was reproduced by a failing test before the repair.

Focused direct-answer/I/O/client/task-fit selection: **123 passed**, exit0. Expanded selection including all original eight modules plus direct-answer and the new pending Supervisor-I/O tests: **298 passed / 9 failed**, exit1. Eight failures are the explicitly unimplemented/denied Supervisor request-consumption slice; the ninth is the unchanged held original service fixture. New direct-answer cases all pass. Do not report the expanded source as fully green or silently deselect those cases. Tests use synthetic receipts/answers and injected transports; no live provider or Runtime completion is claimed.

Independent read-only review of the exact four-file direct-answer slice is on original process79386, with a frozen SHA256 manifest in the Bot operation's `.venv/direct-answer-review-source.json`. The prior architecture reviewer9545 completed and its return was consumed. A later combined source/progress read was platform-refused; it was not replayed. Original test output remains readable from its process receipt. Source writes continue to work for other allowed changes; a mode change cannot authorize the denied request-reader edit. Preserve all prior held snapshot/source-capture/fixture boundaries.

### Existing service profile alignment (no new Runtime producer)

The direct-answer Python client needs the existing service tool profile to accept the same closed selection. Add a direct `view=service_inference` branch to the already-existing executive_fabric tool, alongside unchanged aggregation selection. The service validates only operation_key plus a content-bound v2 reference; arbitrary root/child/path/provider fields are rejected. No fourth tool, new route, credential or lifecycle owner is created.

The existing authenticated App branch must compare that reference with the original operation's status-selected reference before any result-reader call, validate the complete returned direct document, and recheck the enrolled identity before and after the read. Both legacy and direct result paths retain public complete-response bounds. An absent direct Runtime producer or unsupported underlying reader still returns unavailable; this source profile alignment must not be mistaken for installed result production or a workaround to the refused Supervisor edit.

New ASGI tests reuse the existing synthetic JWT/enrollment fixtures and an injected reader: accepted exact reference, unknown nested/outer fields, foreign reference, missing result, disabled/revoked identity before/after status/read, backend errors and substituted/partial answers. The first two new cases failed before implementation (tool schema rejected the direct selection and the real App returned invalid_input400). Actual OAuth enrollment, live service transport and Runtime result writing remain explicitly outside these tests.

### Client/App round trip and review-driven receipt isolation

The existing three-tool service profile now advertises a closed direct selection (`operation_key`, `view=service_inference`, content-bound reference) alongside unchanged aggregation selection. The App compares the request to the operation's status-selected reference, rechecks enrolled identity before entering the reader and again before responding, and validates the complete returned view. Backend absence is still an explicit refusal: the App does not read Runtime/files directly, and no underlying direct-view producer or host installation is implied.

Nineteen new profile cases pass, including the actual Python client calling the actual authenticated ASGI App with synthetic signed JWT/enrollment and injected status/result readers. The result is checked against the original request and exact reference at the client; identity revoked between the status and answer calls returns no data. Foreign references, disabled/revoked service identity, missing result, reader error, substituted content and partial projections refuse. This is a real source-level client/auth/App composition test, not live network/OAuth enrollment or provider output.

The first independent direct-answer review found one P1 mutable-receipt issue despite the earlier reference-copy repair: a callback could retain and modify the status receipt's fingerprint during the answer read, invalidating the original-request binding. Two causal tests reproduced it. The existing validate_submission_receipt now takes an isolated deep copy before validation, protecting both fingerprint and nested grounding across awaits; no new state/credential store or broader client import was introduced. Both receipt-mutation and reference-mutation regressions pass.

The latest complete eleven-module selection returned **319 passed / 9 failed**, with zero skips/errors, in the same isolated Python3.12 environment. The JUnit record separately confirms **41 direct-answer tests and 19 direct-profile tests passed**. Exactly eight failing cases describe the denied/unimplemented Supervisor input/schema seam; the ninth is the earlier held direct-emitter fixture. All remain collected. The new endpoint client itself never performs submission, retry, model execution or account writes. Per-suite counts, exact failure identities and reviewed source hashes are retained in `tests/fixtures/vps_inference_direct_return/verification.json` rather than hidden in a favorable aggregate.

The original independent reviewer is resuming the SAME native session01a12e45-8685-78a1-90bf-0e1263776291 on process52206 to verify the P1 repair and the added App/profile branch against seven frozen files. The initial reviewer79386 and architecture reviewer9545 have both completed and been consumed. Do not claim final review clearance until the resumed report is returned and read against the frozen source hashes. This pending review is not a separately running implementation worker and has no runtime/provider write authority.

### Final review disposition for the direct-return consumer slice

The resumed original reviewer52206 completed exit0 and its final return was read against all seven frozen hashes, which still matched. Verdict: **no actionable finding in this seven-file slice; prior P1 shared-receipt defect resolved**. It verified the original-request receipt isolation, unchanged client import boundary, closed direct/legacy selections, operation/reference/content binding and pre/post-read identity checks with source and pure injected probes. It explicitly did not rerun pytest, independently verify the synthetic JWT fixture machinery, or prove installed/Runtime/provider execution. Initial finding and final disposition are both preserved in `tests/fixtures/vps_inference_direct_return/`; no raw provider reasoning logs are published.

Release status remains **WIP/HOLD**, not full acceptance. The actual test receipt is319passed/9failed with no skips:41direct-answer cases and19authenticated-profile cases pass, while eight missing Supervisor-I/O cases plus the older held fixture remain red. The refused execution helper is confirmed absent; Supervisor/Runtime source and the held fixture are unchanged. No pending native reviewer remains. This source increment makes exact direct-answer consumption and authenticated App/profile validation testable and reviewed, but it cannot manufacture the still-missing canonical result producer or live provider answer.

## October 12 continuation — bounded direct-result observation in the existing Runtime owner

This phase is disjoint from the earlier platform-refused Supervisor request reader. Runtime has one bounded-observation owner; new read methods must reuse its fresh read transaction, statement/row/byte/VM budgets and SAME/UNKNOWN source-consistency receipt. Do not open a second SQLite connection, expose caller-provided SQL, create a lifecycle/ledger, or rely on a mutable worktree file for status.

**Proposed read contract:** Given a closed original service operation key, derive its existing service intent and immutable creation command. Inside a single bounded Runtime observation, verify the unique JOB_CREATED event and service-principal provenance; its parentless role-null Job, READ/RESEARCH/no-write constraints; exact current completed Attempt and worker; and identical fully closed direct inference result document in the Job and Attempt terminal columns. Require content-bound v2 result references and use the existing I/O validator, source-request max_output_chars and explicit raw-versus-canonical digest semantics. Return only the locator to a status consumer; return the answer document only when the caller supplies that exact locator. Absent/queued attempts yield no locator and no answer. Mismatched current attempt, job, role, operation, fingerprint, return contents, exit or cancellation fail closed.

Synthetic positive tests may inject a completed row into a **temporary SQLite fixture** to discriminate read validation, but must say this is NOT evidence of an accepted production completion writer or raw-provider-file authenticity. The canonical Supervisor/Runtime completion writer, collected-output sealing and read App transport remain separately unbuilt and must not be forged by this phase.

**Acceptance:** first RED tests on the missing observation method, then focused green with hard negative cases, plus preexisting bounded Runtime read regression. Preserve separate earlier held nine service failures, twelve Bot defects and the specific denied Supervisor operation. No production/worker/provider changes.

## October 12 — bounded Runtime direct-read source implementation

This continuation implements the read half, without recreating the Runtime, provider, worker queue, Job lifecycle, credential path or Supervisor. The existing BoundedRuntimeReadObservation now supports an exact service operation selection; one parameterized read over the immutable creation Event and canonical Job/Attempt terminal rows checks service-principal authority, complete Job/Attempt/Worker identity, current Attempt, closed request fingerprint, canonical result-document content hash and owner-established raw-result reference. An absent/queued result is null rather than an invented answer. The observation records its own source identity, and publication requires the same finalized SAME receipt. Synthetic completion via temporary SQL fixtures is a read-only validation technique, NOT proof of real collection, provider bytes or a trusted completion writer.

A separate thin read-only projection under control_plane/executive_inference_runtime_view.py reuses the existing observation, exposes a status-only locator or an exact complete answer, and enforces the existing 256 KiB complete-view budget while the I/O owner independently enforces its 192 KiB result document limit. No clipping of a large answer is allowed. Actual socket/outer wrapper ceilings remain smaller and may truthfully refuse large results; this slice does not pretend they have been made streamable.

Service STATUS gains an optional host-supplied existing read-bound Runtime. With it, ingress verifies physical database identity (path and inode) against its canonical writer Runtime, checks the source file before/after selection, and compares selected operation/fingerprint against the original immutable receipt. Without a qualified read binding the code fails closed or retains the previous null result; no caller can specify a file path or SQL. A source from a second temporary database with the same operation and Job ID is explicitly refused.

Source tests were RED before implementation, then 79 focused bounded-owner/status/projection cases passed. An expanded affected fifteen-module run completed 398 passed / 9 failed / 0 errors. All nine failed test identities are known from the preceding branch: eight remain the platform-refused Supervisor request/prompt/schema implementation, one is the earlier held direct-emitter fixture. None was hidden or deselected. This source must remain DRAFT/HOLD; neither a passed read test nor a synthetic completed-row fixture qualifies the missing writer, installed App/backend reader, actual worker execution, DCR or Bot live operation.

Independent native review identified three consequential read-path findings across its first two passes: missing result-to-observation identity, mixed Runtime-source status, and applying the 192 KiB document limit to the larger result view. All three were reproduced with focused regression tests and patched without modifying the previously refused Supervisor reader. Final exact-source independent review is in progress; its result is not yet an acceptance receipt. The current executed source runs, review prompts/manifests and JUnit remain under the Bot workspace ignored .venv until compact final evidence is published.

### Final bounded Runtime reader review — source acceptance, not live cutover

The same read-only reviewer reviewed the corrected six-file source after the earlier three causal defects were reproduced and patched. Its final verdict: **NO_ACTIONABLE_FINDING_WITHIN_FROZEN_DELTA**. All six code/test hashes matched before and after. The reviewer checked queued/completed receipt parity through the existing ceo_intent owner, SAME observation identity, failure/foreign source fences and independent SQL byte-bound probes. It did not run a genuine provider, write-producing test fixture, installed OAuth/Runtime or Supervisor. Exact reports and source hashes are preserved under `tests/fixtures/vps_inference_runtime_read/`.

Latest expanded affected test run: **400 passed / 9 known failed / 0 skipped / 0 errors**. The nine original held failures remain eight Supervisor prompt/schema cases from the specifically refused edit and one stale service direct-emitter fixture; none were edited or deselected. The new positive completed-result cases use synthetic SQL-written Attempt/Job terminal rows in disposable SQLite, not an authorized terminal writer. Status obtains both its receipt and locator in one existing bounded observation to eliminate the earlier receipt-A/locator-B splice, but this is still not a connected service App direct-result producer. Raw provider output, real model availability, source capture, installed identity, actual Host binding/transport and originating Bot PM consumption require separate operational proof.

Original branch custody and source effects are unchanged beyond the reviewed isolated source files. Do not merge, deploy or enable money movement based on this read-only source qualification. The Supervisor refusal remains frozen on its original target, not delegated, replayed or bypassed.

## October 13 — real Unix transport and enrolled App source canary

The original service branch now has a **dormant inference App peer capability on the existing CEO ingress Unix socket**, not a separate server/queue/credential plane. The host-only `CeoIngressInferenceBinding` requires a kernel peer UID distinct from both C1 and the incumbent Web/COO App, an installed grounding source, and separately guarded fresh-admission/ModelRouter binding factories. Its default is not armed; the model cannot choose provider, account, host, quota or launch capability. Disarmed fresh requests refuse; existing accepted operations can still reconcile by original key without a second Job.

The existing OAuth-authenticated inference App now submits and reads through that same source-qualified service-peer socket. The backend admits only the closed service Submit/Status/DirectRead frames, and a dedicated host grounding read; unrelated CEO, WebCEO, release and workspace frames are refused for the service peer. The client permits the service's 60KiB input frame but retains the 8KiB legacy CEO limit. Direct read preserves a selected content-bound reference and passes through the existing bounded Runtime projection (192KiB result document / 256KiB result view ceiling), returning unavailable instead of clipping if an envelope exceeds its owning transport budget. No fourth public MCP tool or independent result store is introduced.

**Source-only proof:** the first 32 focused tests passed, including a 20KiB request from a synthetic signed JWT App over a real test-owned AF_UNIX socket to the canonical Job sink, elevated task constraints, exact status, and direct result read from a temporary SQLite fixture with a qualified bounded source. A later 10KiB+ result and explicit non-service peer denial tests were added for broader verification. The original WebCEO-read mock direct-profile tests were reconciled to the new service peer frame, not silently removed; previously gated Supervisor fixture is still untouched.

**Real installation remains unproven and dormant.** The existing launcher `scripts/executive_os_phase1c.py` configures the original Web App peer only and has no admitted inference-service UID/enrollment, active host binding, installed namespace custody or current provider quota. The older #633 Auth0 DCR uncertain effect remains on its original carrier. Current protected master has independently evolved Executive Service native-continuation code; source integration/review must reconcile that latest shared file before release. No production listener, provider, credential, service policy, queue, account, trading or deployment setting was changed.

### Source-only real-socket admission, status and direct-result qualification (October 13)

This source increment adds the **dormant distinct service UID** to the incumbent CeoIngress Unix listener, not a second listener, queue, model router, auth issuer or lifecycle. The caller's JWT resource and enrolled client remain owned by the existing Inference App. The dedicated peer can submit closed typed service inference, read its own status and selected direct result, and read only its host-grounded context; C1/Web/Operator/release frames remain fenced. Named-user ACLs extend the existing socket without broad group/world permission. The host must still install a distinct, non-root OS identity; tests monkeypatch peer identity and ACL operations and do not constitute installed OS isolation.

The initial independent security review found **five defects** in this new transport slice. All five received causal RED tests and source repairs: a host guard's non-None verdict could be dropped before canonical admission; direct result read could use a foreign Runtime; an outer 48KiB release-frame limit made the 60KiB service request bound unreachable; inference UID could overlap Executive/Operator privilege; and an idle incomplete service connection could stall shutdown. An independent follow-up found **two further medium issues**: root UID zero could still be enrolled under a non-root Executive, and a non-reading client could stall post-effect response drain/teardown. Root UID is now explicitly refused and the service-only response path bounds delivery and teardown *after* canonical work returns, without cancelling submissions or changing C1/Web behavior. The final independent follow-up verdict must be recorded separately; it is NOT presumed favorable before it returns.

Executed evidence is pinned under `tests/fixtures/vps_inference_service_socket/verification.json`. The earlier affected-source regression recorded **599 passed, one previously held service fixture failed**, with no other errors; latest targeted regression after the seven security repairs recorded **145 passed, no failures/skips/errors**. Real AF_UNIX socket and authenticated synthetic-token App tests prove source ingress, 20KiB-to-near-48KiB request admission, exact elevated ModelRouter Job creation, disarmed recovery, foreign-UID refusal, source-bound status/direct result and refusal of tampered references. Larger responses and the new idle/backpressure probes are source tests; all complete-result rows are synthetic SQLite writes in temporary fixtures, not executed providers or installed Supervisor completion.

The latest protected master has moved from the original base, with **five conflicting canonical Executive/runtime files** on an untouched `git merge-tree` check. No merge, release or production change has been claimed; source composition against the new protected owners and the separately refused Supervisor request reader remain independent gates. Neither a passing socket suite nor a green security reviewer proves installed service identity, DCR enrollment, quota/provider admission, real worker completion, origin Bot PM consumption, streaming or natural paper-session trading acceptance.

### Final independent review and publication frontier — October 13

The original native independent reviewer returned **SCOPED CLEAR** after inspecting the last two focused repairs. Seven frozen source hashes matched before/after. The reviewer independently probed response delivery vs in-flight canonical work, transport abort during stalled drain/close, effect-unknown preservation, and root UID refusal. The original five-defect report, intermediate two-defect report, final scoped-clear report and exact two-layer test receipts are preserved under `tests/fixtures/vps_inference_service_socket/`; private local working paths were normalized to repo-relative paths for published copies.

**Final source selection:** 145 passing affected tests, no skips/errors/failures, after all seven security repairs. Earlier broad test selection: 599 passed / 1 unchanged held fixture failure (`test_direct_emitter_cannot_bypass_sink_guard`) before the last two patches; it is not relabelled as full green. The prior platform-denied Supervisor admitted-request reader and #1357 Bot snapshot/zero-qualified-evidence repairs were not replayed. Existing C1 and Web App handling retains its prior timing/authority behavior; only the dedicated service peer has a bounded response-delivery/close deadline after canonical work settles.

The test-backed OAuth App→existing Unix socket→canonical Job→source-qualified status/direct result path is **source-proven only**. All completed rows were inserted as synthetic fixtures, service peer UIDs were simulated, ACL shell commands were mocked, and no installed quota/provider, real completion writer, browser, natural-session paper trade or production identity was touched. A fresh read-only installed Executive check on October 13 observed Mastermind SHA `54e8659730141fc130ebbeb214dbb50f3edb04a7`, one AVAILABLE worker and zero RUNNING Attempts; that installation does not include the newer PR source. The latest protected master `9a8e9b50b6158eb38af78a5b867eedba1719b908` has five merge conflicts against the older original carrier, so source integration with current owners and independent exact-head CI remain release gates. Keep this PR DRAFT/HOLD.

### Protected-master source convergence — October 13, 2026 (pending final qualification)

Source parent `da868d8aaa47ef81ec01653c82a71a4e3166e10d` was composed with exact protected master `9a8e9b50b6158eb38af78a5b867eedba1719b908` on this ORIGINAL branch through the normal Git merge, not a second workspace/writer. Five textual conflicts were resolved without discarding either owner:

- `ceo_intent.py`: retain the service host admission/result-binding inputs AND newly protected strict-v2 `fresh_admission_observer` and its own guard.
- `executive_ceo_ingress.py`: preserve both corresponding host-sourced keyword paths to the same canonical mutation sink.
- `executive_runtime.py`: preserve the existing bounded service-result/receipt read AND new protected root-origin and admitted-plan readers under the same bounded observation owner; no new database/queue.
- `executive_service_principal.py` and its test: retain the current protected dynamic citation checks while rebinding source anchors to actual merged predicate lines; source annotations are evidence, never admission privileges.

First merged-source test selection: **317 passed**, including service principals, CEO ingress, root origins, and bounded Runtime/read safety. An independent exact-source merge review and additional tests covering newly protected native dispatch plus the known service Supervisor fixture are running separately. **Do not claim merge or release acceptance until they are reconciled.** Staged upstream `.patch` documentation contains its original diff-whitespace intentionally; own five conflict resolutions pass path-scoped `git diff --cached --check`. Protected patch files are not normalized or rewritten.

Current master separately merged governed Research citation transport (#1403) and Fabric inspector UI (#1411). These are reuse dependencies for later Bot UI product integration, not reasons to create a duplicate citation/worker status plane. This merge does not alter previously refused Supervisor request/prompt readers, the held direct-emitter fixture, the independently denied Bot snapshot/zero-evidence fixes, installed service identity, live provider capacity or any portfolio state. Until tested and committed, `MERGE_HEAD` remains the exact protected revision above.

#### Root-origin compatibility repair (post-merge independent review)

Independent source-only review of the five formerly conflicting owner files found one P1 **integration** defect that earlier green tests did not cover: registered non-CEO service Jobs carrying typed service provenance poisoned the existing bounded CEO-root mapping. The old pure classifier required the legacy six-field CEO record for every non-orchestration Job. The resulting fail-closed whole-map refusal hid unrelated valid CEO roots when one legitimate VPS inference or site-maintenance service Job was present.

Three actual admitted service-root cases reproduced the failure (normal registered VPS inference, valid 40KB near-limit inference, and registered site-maintenance). The existing `runtime_root_origin.classify_legacy_root_creation` now recognizes only its TWO enrolled READ/RESEARCH service principals with exact source-specific grounding, principal/task/authority registry checks, bounded canonical inference request, original command/fingerprint syntax, read-only A0/COO Job authority, and zero write paths. A valid service returns **NON_CEO with no provenance** and cannot become an actionable CEO candidate. Missing/unknown source, spoofed typed evidence, bad inference schema, forged Job/seat/rights or unknown root still invalidate the whole source map; no silent fallback to generic root classification. No new identity registry, query store, queue or Runtime reader was created.

The focused service-origin repair set passed **12**; additional adversarial tests passed **16**, with injected bad records confined to disposable SQLite. Wider merged-source suites: **317 passed** (ingress/principal/root-origin owner); **363 passed, 1 previous held direct-emitter fixture failed** (CEO/root/join service); **486 passed, 9 previous held Supervisor/input-schema and fixture tests failed** (native service). These are separate test scopes, not additive unique test counts. The nine failures and their original platform-refused Supervisor writer remain unchanged. Evidence digests/source hashes and exact test identities: `tests/fixtures/vps_inference_service_root_origin/verification.json`. Independent reviewer of the *repair* has been requested and remains pending, so no merge or release acceptance is yet claimed.

#### Second independent root-origin review and canonical sink-grant reconciliation

The first origin-repair reviewer returned **REQUEST_CHANGES** on two real valid-source cases: registered site maintenance allows an optional boot-packet field, and the canonical mutation sink permits **READ-only or RESEARCH-only subsets** even though the convenience registered-principal emitter requests both. Both cases were reproduced as three failing source tests before repair, then reconciled against the EXISTING `ceo_intent._grounding` parser and `_authorities`/service READ+RESEARCH ceiling, not a new grant plane. The closed principal/actor registry, matching requested/effective/Job authority, read-only A0/COO seat and zero write paths remain required; malformed/unknown service roots still fail closed.

An expanded test selection now returned **29 passed and two failed**. Both failing cases are earlier synthetic adversarial assertions that incorrectly mark sink-admitted optional grounding as a forged record. The attempted bounded revision of those two exact assertions was explicitly blocked by platform safety checks BEFORE DISPATCH, confirmed **NOT_APPLIED**, and was not retried via an alternate carrier. The source classifier has NOT been weakened to manufacture passing tests, nor were these cases skipped. This is a **known WIP test and release blocker**. A second independent read-only review of the sink-aligned source is in progress. Updated source hashes, exact red/failure receipts and review state are recorded in `tests/fixtures/vps_inference_service_root_origin/verification.json`. No production, trade, queue, credential, registry or actual worker effect occurred.

#### Follow-up independent adjudication received — source accepted, test fixture still red

The second independent read-only reviewer verified all frozen source hashes and returned **SCOPED_APPROVE** for the two P1 repairs. It independently probed 24 valid sink-normalized service inputs and 41 malformed/inconsistent refusals without database writes or provider activity, and confirmed the protected bounded root-observation, `SAME` receipt and all five owner-merge behaviors remain intact. It specifically confirms that the registered-principal emitter's full-grant preference is NOT the canonical sink's only lawful grant, and that the optional boot-packet field must not be mistaken for invalid grounding.

One P2 **test-expectation** defect remains: two synthetic adversarial cases in `tests/test_runtime_root_origin_service_adversarial.py` call sink-valid optional grounding malformed. Their bounded correction was safety-refused pre-dispatch and not retried. The latest mixed focused suite remains **29 passed / 2 failed**; it has not been made green through classifier regression, test deselection, alternate actor or silent modification. The previously known Supervisor/fixture failures are also unchanged. This evidence therefore clears only the reviewed SOURCE behavior, not CI, merge/release acceptance, installed identity or actual model execution. Review reports, SHA digests and exact assertions are retained under `tests/fixtures/vps_inference_service_root_origin/`. The remaining changes may be committed on the original PR for durable recovery while the PR stays DRAFT/HOLD.


## October 13/14 — heterogeneous Fabric capacity boundary and broker alias integrity

Source-only census of the actual M2 Fabric status publisher (`orch/fabric/status.json`, schema `mastermind.provider_capacity.v1`) showed separately reported Bailian, GLM, Grok, Cursor, MiniMax, GO, OC-free, Codex-native and Claude-native pools. These are **advisory reported slots** from the existing Fabric lease broker, NOT Executive WorkerRegistry quotas, current provider eligibility, model suitability receipts or authority to start a provider. The status output's specific slot counts change and must not be copied into route policy. Do not mirror status.json into new provider/credential/queue/lease tables.

The checked-in Executive policy `config/executive_worker_routes.json` is **`production_armed:false`** and admits autonomous Codex aliases only. Routine research's ordered aliases `fast.research` and `standard.research` both resolve to Codex profiles; elevated comparison routes to `standard.research`. GLM/Qwen/xAI autonomous provider flags remain disabled and the `openai-compatible` and `attended-fabric` adapter descriptors remain unimplemented. The original service's v2 purpose-to-ModelRouter bridge therefore does not yet provide Bot access to all M2 Fabric worker/frontier pools. Turning status headroom into worker eligibility without true original Job/Attempt lifecycle and provider/host admission would be an unsafe second-control-plane shortcut.

A new adversarial capacity test exposed a separate **existing Executive broker source defect**: a WorkerQuotaClass with its physical provider GLM, Qwen or xAI, or wrong model/effort/cost, could copy Codex `fast.research` alias metadata and appear selectable. Six causal synthetic SQLite tests were RED. The source-only broker matcher now compares physical provider, worker_provider, worker_type, model, effort and cost against the original ModelRouter profile, plus policy/capability digests, before preview/claim. The original Codex positive retains claimability. Independent review found four P2 compatibility problems in the initial patch: optional reviewed routing policy paths, the separate attended Fabric route, the actual external_pool_binding metadata producer format, and repeated policy rereads/possible generation drift between selection and claim. Those are being reconciled in the SAME existing broker source: host-owned `Runtime.at(routing_policy_path=...)` and CLI binding; one pinned route snapshot per candidate scan, revalidated before atomic mutation; existing attended-route catalogue contract preserved separately; physical row identity used instead of requiring redundant self-asserted provider/adapter metadata keys. This is not an authorization to deploy a new adapter.

Executed tests on the first source fix: 8 focused GREEN after the six REDs; affected broker/ModelRouter selection 97 GREEN. After the P2 compatibility correction, 79 targeted tests GREEN (including five existing attended catalogue tests and source-only external pool-binding cases); broader suite 276 passed with one earlier refused direct-emitter fixture failure. A new guarded adversarial SQLite-row probe found four further attended physical-check failures because SQLite row membership tests values, not column names. The relevant source hash was frozen for independent review, so this new repair is pending reviewer reconciliation; do not claim final source acceptance yet.

For real heterogeneity, the next bridge must bind the **existing** Fabric provider/host/account capability to the **existing Executive** Job/Attempt under the incumbent admission/effect owner and preserve one operation ID through results, not independently start Fabric_task runs from Bot. Require exact authorized provider, model, quota class, host, allocation generation, budget, observed capacity, attempt fence and verified completion; runtime's production flag and installation are separate gates. False reported availability must never become a live trading permission. Service source has not been installed, no worker/provider or real-market paper order was started, and prior platform-refused Supervisor/snapshot/fixture edits remain untouched.

### October 13/14 — final capacity-source adjudication (not a live provider cutover)

The initial independent read-only adversarial review found four real P2 defects in the physical provider identity patch; a subsequent independent review found three more P2s in its reconciliation. All seven were reproduced with RED probes and corrected **within the existing Executive broker/ModelRouter and original Phase 1B CLI**, without creating another admission, queue, retry, identity, budget or worker-result owner. The reviewer returned a final **SCOPED CLEAR** for the frozen five-file router/CLI/attended-source patch, with source hashes verified before/after. Reports and individual source/evidence hashes are retained under `tests/fixtures/vps_inference_provider_identity/`.

The final patch requires six physical columns for attended SQLite candidates, rejects wrong provider/worker provider/adapter/model/effort/cost rather than trusting matching nested catalogue data, and rechecks the outer alias/routing/capability metadata. Existing separately governed attended preview semantics are retained. Ordinary autonomous alias matching uses ONE host-selected `ModelRouter` snapshot per candidate scan, refuses provider/worker-type/profile metadata disagreement (including copied Codex aliases on GLM/Qwen/xAI workers), and makes a second current-policy comparison before the atomic Job claim proceeds. `Runtime.at(routing_policy_path=...)` is a trusted host constructor input, not Job/worker-controlled routing. Phase1B legacy CLI commands retain `None` as the default; original `run-once` and `reconcile` now accept the host policy option. Already-reviewed external-pool producer metadata may omit redundant provider/adapter keys because the physical registered identities are authoritative; contradictory optional keys refuse.

Executed selections: **84 focused source tests passed**, and **six CLI compatibility tests passed** with 11 unrelated tests deselected in that specific `-k` selection; both selections remain explicitly scoped, not combined into an invented unique-suite count. A broader affected set recorded **325 passed / 1 known inherited failure / 0 skipped or errors**; the failure is exactly `test_direct_emitter_cannot_bypass_sink_guard`, whose earlier requested compatibility edit was platform-refused and NOT_APPLIED. A separate three-case authentic-v2-service/temporary-SQLite canary confirmed no wrong-provider claim, preservation of original Job/Attempt identity and claim of the exact qualified model; it did not START a real provider. No test, held failure or source exception was relabelled as production proof.

The reviewer explicitly limited clearance: the 2-snapshot policy comparison detects ordinary observable drift but does not atomically bind file-system revocations through the SQLite commit or provider launch. Existing immutability/release/credential authorization remains with its original host. Legacy unaliased Jobs retain their prior route behavior; this is not a universal provider-auth proof. The M2 Fabric status file reports external headroom but the current Executive route policy is `production_armed:false`, with GLM/Qwen/xAI providers and openai-compatible/attended adapter implementations unarmed; current Bot service research aliases resolve to Codex. External heterogeneous Fabric execution, installation, true output provenance, real frontier result return and portfolio activity remain NOT PROVEN. No production or capital effects were performed.

### Latest protected acceptance-owner integration — October 13 (source-only)

After the independently scoped-clear physical provider alias/attended route/host policy correction was committed as `8a66c8b774152cc677424d241e6f4fa7adc89658`, the ORIGINAL carrier reconciled protected master `1ffe6b566b9addb58d13893bfb78e8505dce1752` via the normal history-preserving Git merge. This adds the current product-acceptance original-intent/consumed-ruling owner (#1414) into the same canonical Executive Runtime source without textual conflicts or competing authority. **268 targeted tests passed, 0 failed/skipped/errors**, spanning the new protected product-acceptance owner tests and the existing broker/capacity/attended source tests. Exact test JUnit digest and parents are in `tests/fixtures/vps_inference_provider_identity/protected_merge_verification.json`. The protected-master integration has NOT enabled production, worker capacity, portfolio trades, or genuine Bot product acceptance. Earlier held fixture/snapshot/Supervisor errors remain independent and may not be hidden by this green scoped merge.

### October 13 — verified current protected service ↔ published Bot source canary

A hash-bound source-only composition of this published service `be49c7ec453dac58f605e2eb18e4eedadefbe200` (including protected product acceptance source `1ffe6b566b9addb58d13893bfb78e8505dce1752`) with the **actual published remote Bot head** `1e127060b8a034b35853fd23c4be9ed55592728f` executed **5/5 hermetic canaries**. The two original extraction/comparison Bot evidence cases again reached the signed-JWT fixture App and existing AF_UNIX service status/direct read, then produced bounded cited CANDIDATE_ONLY claims from explicit synthetic completed rows. Three original v2-service provider-identity cases also proved that a false GLM research quota or wrong physical Codex adapter cannot claim the Bot's allowed model profile; the legitimate fixture Codex still claims the original Job only once. A first collection-only attempt exposed a missing test fixture in the ignored source export; that exact Git fixture was added and all 1021 source hashes revalidated before the succeeding run. The compact source/JUnit digest is saved in `tests/fixtures/vps_inference_provider_identity/bot_published_source_canary.json`, rather than publishing the 20 MB+ export. This is **not** a real provider, authenticated installed UID/ACL, production/market trade, licensing, capital/risk actuation or live model provenance proof. The newer local Bot commit's previously refused push was NOT retried or routed through this service carrier.

### October 13 — existing Fabric bridge gate confirmed; no duplicate dispatcher

A deeper owner census found the ORIGINAL cross-plane components already present: `executive_fabric_adapter.py` (Attempt-bound facade), `executive_fabric_bridge_broker.py` (authenticated Control start/status/collection), `executive_fabric_composition.py` (root-installed pinned host/profile facts), `fabric_remote_transport.py` (one pinned original remote transport), plus the shared Runtime/Capacity/Supervisor and Fabric controller. Source-only tests across the actual bridge, fencing, composition and recovery modules recorded **222 passed / zero failures/skips/errors**. This is not an installed backend or paid model run, and the history/evidence source is retained at `tests/fixtures/vps_inference_provider_identity/existing_fabric_bridge_activation_gate.json`.

The direct startup predicate in `scripts/executive_os_phase1c._validate_fabric_bridge_config` explicitly rejects **`fabric_bridge_armed:true`** via `FabricActivationRefused` until an actual backend AND isolation profile are admitted. Even an inert host binding source requires an exact path+approved SHA pair and a root-owned immutable file. Current adapter catalog still labels `attended-fabric` as **implemented:false** (the facade class exists but physical host backend is not installed), and `openai-compatible` as **implemented:false** with no implementation class; Codex remains the only autonomous implemented provider adapter in the checked-in route policy. Pure read-only checks verified this explicit refusal without opening credentials, creating Jobs, dispatching a Fabric task or touching production.

**Do not invent an alternate Bot dispatcher, Fabric lease ledger, retry queue, identity, price accounting or model selection policy.** Future work must finish the concrete backend on those ORIGINAL sources, authenticate the installed Control peer and physical realm, atomically bind fresh original Attempt/START commands at the incumbent O_EXCL reservation, and preserve status/collection/cancel/revocation through the existing Fabric broker. A separate original human/host release control must qualify the pinned profile, actual provider/worker availability and isolation. The platform-refused Supervisor prompt/completion-writer, Bot source-capture and snapshot correctness remain specific blocks to a genuine result-return and portfolio cutover. No claim of live Subagent Fabric integration, deployed service, true model origin or capital authority follows from this source clearance.

### October 14: source-only installed Control inference UID staging — fail-closed after security review

The original service code has been history-preservingly composed (uncommitted pending final review) with protected `78388ac29f7e54c9dfe7799a8e4769fb46d4aed6`, including finite-MiniMax original process, credential and assignment-revocation owners from #1391. One gateway conflict was resolved by retaining BOTH protected company-dialogue-principal framing and the separate inference/release request and response ceilings. Relevant merged inference/Fabric tests: **324 passed**; protected dialogue gateway tests: **80 passed**. These are independent source-only selections, not installation receipts.

The installed Phase1C Control source now accepts one optional, default-absent **configuration-only** inference pair `ceo_ingress_inference_peer_uid` + `ceo_ingress_inference_armed:false`. It requires complete existing CEO ingress and App configurations, positive non-root UID distinct from Control/Operator/worker/Web/allowed peer IDs, and refuses unknown inference-specific provider/credential selectors. Any `armed:true` or nonboolean value refuses. Crucially, merely supplying the pair **does not construct `CeoIngressInferenceBinding`, does not grant socket ACL, does not enable status/direct-result reading, and does not enable submission**. The separately authorized installed service-enrollment owner must first qualify the dedicated OS account, exact authenticated OAuth client, host policy/namespace custody and revocation. This source has NO such enrolled binding, so neither historical results nor new Jobs are exposed to an unqualified numeric UID.

The first feature implementation's source tests reproduced **15 missing behavior failures**, followed by an intermediate 48-pass test state. Independent security review found **HIGH**: config-only UID unintentionally allowed existing-result disclosure even when admission was disarmed, and **MEDIUM**: in-flight status/direct reads could publish after service entered `QUARANTINED`. Both were reproduced as RED tests. The installer now deliberately discards the configured candidate UID after validation; a real temporary AF_UNIX test confirms the unenrolled UID receives `peer_denied` for status, direct read and fresh submission with an original canonical Job present. The existing ingress handler also rechecks its `READY`/`AWAITING_CANARY` state and binding immediately after the awaited operation and before publishing a response; a paused-read/QUARANTINED test now refuses without result disclosure. Existing C1 and Web peers are unchanged. These fixes do not provide DCR, JWT issuer, separate identity registry or an alternate queue.

**Post-repair verification:** 48 focused tests passed / no skips or errors. Broader affected installer/service selection **395 passed / one unchanged, previously platform-refused direct-emitter fixture failure** / no skipped or errors. Protected dialogue gateway: **80 passed** and merged inference/bridge: **324 passed**. A separate expanded finite-owner selection recorded **280 passed / 3 failures** involving the protected #1391 probe/assignment-revocation fixtures; six implicated source files match protected master byte-for-byte. We neither weakened authenticated assignment sealing nor claimed that these failures prove this source change. Independent read-only reviewer checked five exact frozen SHA-256 sources and returned **SCOPED CLEAR** after the HIGH and MEDIUM fixes. The two reviewer reports, verified source/JUnit hashes and exact still-RED cases are stored in `tests/fixtures/vps_inference_installed_staging/`.

The real production installer has **no enrolled inference peer, no independent DCR/OS principal verification, no live provider/worker execution, and no risk/capital permission**. Separate held gates remain: prior platform-refused Supervisor admitted-prompt/result writer, 11 Bot snapshot failures plus zero-evidence routing error, two old root-origin adversarial fixture expectations, real admitted Fabric backend/physical quota, authenticated result consumption at original Bot PM, and browser/natural paper-session/forward evaluation. No installation, provider, account, queue, credential, portfolio, release or user setting effects occurred. Keep **DRAFT/HOLD**.

### October 14 — strict installed-source/template CI pin maintenance (no runtime change)

The exact-head GitHub test gate exposed two **newly introduced static-source** failures after the scoped-clear dormant inference staging: the default `control.json.template` is intentionally missing the two new optional inference UID/armed fields but its closed-key test did not list them as opt-in, and the D7 approved installed Control event-loop source SHA still pinned the older protected-master file. Independent source review of the complete current launcher at SHA-256 `accf4a5039b4edce733055ba4cc83a1c4e3f2181b0e12c6fe36a9ccaa568c9e1` had already returned scoped clear for the exact staged, **unenrolled** behavior. The sole canonical installed-wrapper function retains AST digest `060525ac61b01452e7a84397f0e68ab4be9c0a05f6dac560113bce8180adc819`, identical to the previously reviewed wrapper.

The source-security test now pins the independently reviewed complete launcher bytes, without modifying its AST, removing its hash guard, widening the `asyncio.run` exemption or adding an alternative event loop; negative source-mutation probes remain active. The static template-closed-key test explicitly excludes the new optional, non-installed inference fields rather than forcing unsafe default enrollment. **167 D4/D6/D7/D8 scoped tests passed** (five others deselected), plus a separate 25-pass focused template/config subset. Test/JUnit digests and immutable source identity are recorded inside the existing `tests/fixtures/vps_inference_installed_staging/verification.json` receipt. This resolves only these two new CI failures; the separately platform-refused eight Supervisor tests, two stale root-origin expectations and one direct-emitter fixture remain unchanged and must not be skipped or repurposed as acceptance. No service activation or production effect occurred.

### October 14 — content-bound historical inference read quarantine regression

The prior independent installer-security review noted that its paused-result/quarantine test exercised a **synthetic STATUS frame**, not the real completed direct-result source read. A new focused postreview test-only extension now uses the original authenticated test-owned service ingress, original admitted Job/Attempt and future-writer-simulated terminal bytes, exact `RuntimeReadBinding`/`SAME` observation and verified content-bound reference. Both `STATUS_SCHEMA` and **`DIRECT_RESULT_SCHEMA`** complete their canonical internal read before the synthetic host state becomes `QUARANTINED`; neither can publish the already-selected result to the Unix client afterward. **46 focused Runtime/socket tests passed**, including both new variants, zero skips/failures. Historical reviewer source hashes are preserved, and the added test-only SHA plus JUnit digest is separately recorded in `tests/fixtures/vps_inference_installed_staging/verification.json`. No production or earlier scoped-reviewed Control/App code was modified; no installed UID, OAuth, real worker, source data or trading effect occurred. The original disarmed service remains uninstalled and the PR remains DRAFT/HOLD.

### October 14 — historical unjoined Fabric root detail read contract (source-only)

Read-only installed Executive inspection showed root enumeration works but an individual Job/detail view returns a sanitized `backend_unavailable`, whose precise installed cause cannot be proven without deploying a fix. Reproduction against a **synthetic historical, unjoined ordinary Job** revealed one concrete producer-to-reader mismatch: `fabric_job_view` emits exact `MISSING_PRODUCER` fact `durable orchestration-root workstream join unavailable for included Jobs`, while the incumbent installed V2 WebCEO source validator expected an obsolete `durable CEO-intent ...` reason. That validator rejected the otherwise valid `PARTIAL` bounded root observation. The source validator now requires the producer's actual exact reason, with no alias/fallback, and still refuses omitted, tampered or obsolete missingness; valid CEO-root provenance remains `PROVEN`.

Two historical-root cases were **RED before** correction; four final focused cases now **PASS** with strict malformed-source negative assertions. An extended reader/Fabric selection recorded **141 passed, one ERROR**, the error being an unrelated unchanged protected sealed-worker Supervisor OS/process identity fixture (`test_v3_sealed_worker_same_observation_and_selected_detail`). That error is not deselected, erased or represented as green. Evidence and exact file/JUnit SHA-256 are committed under `tests/fixtures/vps_inference_historical_root_read/verification.json`. No protected Runtime, Supervisor, installed Control, real provider, OAuth, credential, queue or portfolio/trade state was modified. Production root-detail recovery remains unverified until the original installed reader receives this source and the same exact Job request succeeds. PR remains DRAFT/HOLD.

### October 14 — historical-root repair qualified through authenticated Web-CEO App

The original branch with source commit `68d99c249579d5a2e00179047f05e2d556cb47fe` cleanly composed with latest protected `2cc4942e136ad4fb544fd5c72ab1856608a5dac1`, preserving unrelated protected auth/CI/Fabric owners with no file conflict. **182 targeted merged-source tests passed**, including relevant Fabric V2 readers, signed WebCEO apps and protected auth/CI-policy tests. An additional direct test now exercises the ACTUAL signed test JWT WebCEO app → existing temporary AF_UNIX service ingress → canonical bounded Runtime reader for a historical Job with no orchestration provenance. It passes with `ok=true`, an explicit `PARTIAL` capability, the original `unjoined_job_ids` and a finalized `SAME` observation, instead of an opaque `backend_unavailable` result. The four earlier producer/validator parity and negative tests also pass, for **5/5** focused historical-root tests. No production account, OAuth DCR, installed service configuration, private historical DB, provider or portfolio was touched. Exact file hashes and both JUnit digests are in `tests/fixtures/vps_inference_historical_root_read/verification.json`.

The earlier larger 141-pass/one-error selection remains explicitly documented: its sealed-worker OS/process identity fixture error was in protected Supervisor code untouched by this repair. No refusal was bypassed. Production recovery of actual older installed Jobs awaits this original branch's separately authorized release; synthetic source/Socket proof alone does not establish live read availability or solve the distinct installed `executive_job` detail failure.

### October 14 — separate installed `executive_job` diagnosis from Fabric root-detail mismatch

After committing the protected-master historical `PARTIAL` root fix, the same signed test JWT WebCEO V2/real temporary Unix socket test was extended to request **both** `executive_job` and `executive_fabric(view=root)` for one queued, zero-Attempt, unjoined historical test Job. Both return `ok=true`. The Job reader retains its existing strict closed `Job`/Attempt schema; the Fabric projection explicitly reports `PARTIAL` with producer-authenticated missing provenance rather than a fabricated complete workstream. **5/5 focused cases pass**, with exact test-source and JUnit digests appended to `tests/fixtures/vps_inference_historical_root_read/verification.json`.

The live installed Executive still previously returned `backend_unavailable` for an exact Job detail. This new source-only evidence **does not diagnose the old installed record contents**, nor does it prove that installing PR #1147 will repair every historical Job detail. It narrows the issue: the current source's standard queued Job path is functional through the full installed-App test harness, and the identified Fabric-root missingness label mismatch is independently repaired. No old production Runtime was read directly or mutated, no noncanonical status accepted, and no model, credential, provider or capital side effect occurred. Any real installed follow-up must remain on the canonical read/release owner after an authorized deployment.
