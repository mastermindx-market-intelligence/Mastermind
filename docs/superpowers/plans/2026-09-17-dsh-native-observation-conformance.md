# DSH Native Observation Conformance Implementation Plan

> For agentic workers: use the current accepted execution-plan/TDD procedure after source custody and the gates below are established. This document is not a worker assignment or permission to launch a runtime.

**Goal:** Build the smallest native, provider-free conformance vertical that observes one owned DSH Agent accurately and feeds existing OHF admission logic, so a later real worker is not admitted from requested settings or incomplete inventories.

**Architecture:** Mastermind implements the original observation/composition code; the pinned DSH engine continues to own its native Agent loop. Collect in the same native process from the exact owned AgentHandle, then use the existing native-process, OHF wire, comparison and evidence owners. Do not introduce another agent loop, remote-control service, evaluator, registry, credential store or lifecycle.

**Tech stack:** Pinned DSH TypeScript/ESM APIs for native observation; the existing Python OHF contracts for the consumer; the existing native process owner for any subsequently admitted process. The Node executable used for this turn's source-method experiment is not an admitted DSH build toolchain.

**Spec:** Existing PR #687 research, especially `research/HARNESS_CONVERGENCE_DSH_PREWORK_ATTESTATION_FALSIFIER_2026-09-17.md` at `78274b30948f4da6d2f7415ee04a9678d9499ed2`, plus the backend-realization matrix and execution-host identity gap. This plan narrows the next source slice; it does not supersede the full product thesis.

**Disposition:** DRAFT / SPEC_ONLY for the proposed native implementation / SOURCE-METHOD EXPERIMENT EXECUTED / PRODUCTION INERT. No native collector implementation, DSH installation, provider call, runtime admission or source release is claimed.

**Parent:** `harness-convergence-dsh-teardown-20260916-sol-001`. **Decision operation:** `harness-convergence-dsh-native-observation-contract-20260917-sol-001`. Both are source/continuation references, not newly minted Executive lifecycle records.

## 1. Authority, outcome and verified state

Current live Chairman direction appointed Sol CEO of the orphaned harness program and requests continued advancement. Sol owns this design and its integration decision. The current procedure pin is Mastermind `b14982837cc8146e3dc49e5862558ee399a1aa3d`, Skillpack 1.0.1 / bootstrap 1. Relevant OHF contracts, Codex observation code, ACP integration and the cited native-Claude preflight plan are unchanged from the previously checked protected `42d210bc07a75234092ff5be71f6038ccacaa884`.

The user job remains useful heterogeneous coding, research and sustained operator work, with company context, skills, governed tools, visible progress, validated output and reliable interruption/recovery. The machine job is to place and admit only a genuinely capable configuration, preserve provenance and effect truth, and learn from comparable accepted outcomes. The moat is portable company method/context plus measured execution quality, not a universal wrapper or a copied interface.

The 10/10 end-state includes a real task from Executive admission through native tool work, useful result, review/repair, parent consumption, visible operational state and outcome instrumentation. Neither this design nor a passing laboratory fixture completes that outcome.

Current source facts:

- Research carrier #687 was at `78274b30948f4da6d2f7415ee04a9678d9499ed2` before this addition. Preserve the preceding nine research artifacts.
- A2 evidence-lock implementation #692 remains a separate slice at `a5ad195e224cacb364862e4987f669b2bb3f261e`. Its successful hosted repository/security checks are already consumed; independent review and Agent Evaluation adoption remain outstanding in the observed records. Do not rerun unchanged tests or extend #692 with DSH code.
- #600, the incumbent orchestration-parity integration plan, is open/Draft at `a5c4f0f4c9561874ded59abf9a9466fe33734538`.
- #660, the provider-neutral remote OHF proxy, is open/unmerged at `a614e422c1c84b3b55be6aa855205fd2e3b1931c`. Its source must not be treated as protected or production-proven.
- A bounded open-PR title/body search for DSH returned #687 and #692 only. That search is not proof that every possible unmentioned local branch is absent; source custody and path collision must still be checked at implementation admission.
- The proposed `experiments/harness_convergence/` and `tests/harness_convergence/` trees are absent at the protected pin.

The connected tools expose no usable Executive/Studio Direct ingress in this turn's discovery. Directory search did not resolve that named connector. This is a limitation of this session's available submit surface, not proof that the installed company fabric is down. No worker dispatch, pickup or START is claimed. Direct design work is retained for PRINCIPAL_JUDGMENT; ordinary implementation should use the least-scarce eligible worker once there is a complete admitted packet and working return path.

## 2. Two important refinements to the preceding finding

### Native current model versus provider response identity

The prior finding correctly rejects copying a requested model or an advisory ACP catalog option into an observation. It must not be expanded into a requirement that every backend make a hidden inference before pre-work admission.

Protected `CodexOperatorAdapter._initialize_and_attest` obtains `config/read` from the native process and populates the existing `served_model` field from that observed effective configuration. Protected native-Claude preflight law explicitly permits a served/current model observation or verification of the requested model before the first turn. The comparable DSH target is independently read native effective route/configuration, not a caller echo. A later provider response's identity is additional evidence; no pre-work configuration claim proves the vendor's physical backend.

Keep three meanings separate in evidence without creating a new common ABI: requested selection; native-resolved effective selection bound to the owned composition; response-reported model where available. Production mapping still requires the existing OHF/capability owner's adoption. Unknown required model evidence remains refusal. This is not permission to fill `served_model` with a requested value or to weaken the comparator.

DSH `resolveCallConfig` explicitly does not bind a later dispatch. `prepareCall` returns a one-shot, registration-bound handle. Merely preparing a throwaway call outside the Agent and allowing the Agent to prepare another does not preserve that guarantee. Initial observation must be accompanied by an immutable admitted composition and pre-dispatch drift checks through the native execution owner. This plan does not modify the Agent loop to smuggle in a precomputed call.

### Exact Agent observation, not a new public inspector

DSH already offers `ctx.agents.create/resume`, `AgentHandle.agent`, setup-before-publication, `ctx.tools.schemas(agent)`, `ctx.tools.get(name, agent)`, and Loader entries. Prefer an original same-process observation module composed by the trusted native helper. It reads an exact handle the helper owns; it does not search for a newest session, accept an arbitrary session ID as authority, or expose a global inspection endpoint.

Stock ACP alone remains insufficient. Adding a general Web inspector, inventing `ctx.pluginInventory`, scraping a UI, or creating a second RPC server is unnecessary. The existing plugin-inventory service is Remote-only diagnostic projection, not a Context service, complete provenance record or admission authority.

## 3. Chosen approach and alternatives

**Chosen for N0:** same-process collector plus provider-free native fixture and existing OHF consumer. This gives direct access to the exact Agent scope after composition, without changing the company control plane. N0 is development conformance, not an operational Worker registration.

**Not selected as the first slice:** stock ACP-only field mapping. It cannot independently supply complete effective capability, process, realm or configuration evidence. An eventual narrow ACP extension may be evaluated by its existing owner, but no custom method or extra control channel is created here.

**Rejected:** universal Harness OS, replacement Agent loop, duplicated tool framework, a general-purpose configuration/credential inspector, or weakening OHF to fit incomplete observations.

N0 does not depend on merging the unrelated A2 utility. Actual rich remote rollout does depend on the accepted proxy/native-process/capability owners. In particular #660 currently requires `resume_session` and native-resume support. A one-shot observer cannot claim that profile merely by returning a capability flag. Preserve that requirement; implement and prove real resume in the later rich adapter wave, or stay outside that route. Do not widen N0 into all sustained-operator behavior just to fit an unmerged proxy.

## 4. Frozen N0 source surface

The next implementation candidate, after custody/admission, is limited to:

1. `experiments/harness_convergence/dsh_native/observe.ts` — read exact native scope and construct a closed, nonsecret transient observation.
2. `experiments/harness_convergence/dsh_native/fixture_host.ts` — compose and own one provider-free fixture Agent; own teardown; never start a second driver.
3. `experiments/harness_convergence/dsh_native/ohf_consumer.py` — validate the private observation and combine separately supplied trusted host evidence into existing OHF types; call existing `compare_launch` and `first_work_turn_allowed`.
4. `tests/harness_convergence/dsh_native_observation.spec.ts` — real mounted-fixture scope/composition/drift tests.
5. `tests/harness_convergence/test_dsh_native_observation.py` — wire/identity/completeness/refusal and real-comparator tests.
6. `docs/runbooks/DSH_NATIVE_OBSERVATION_CONFORMANCE.md` — exact admitted supply identity, reproduction, evidence ceilings and cleanup instructions.

These are proposed new paths, not permission to create a competing branch/PR or source writer. Before the first implementation write, reconcile #600/HF1/OHF/capability custody and choose one source carrier. Keep #687 records-only and #692 unchanged. No edits to `control_plane/**`, existing proxy/ACP implementations, Agent Eval core/corpus, workflows, account/realm/configuration files or dependency locks are admitted by this plan. An indispensable wider change returns to Sol before edit; do not hide it as a test exception.

## 5. Native producer contract

The trusted fixture factory owns one Context composition, one returned AgentHandle and a native model-selection reference installed in that Agent scope. The observation function takes those owned objects, not model/user-selected paths, executable names, provider endpoints, commands or credentials.

The required observations are:

- Exact Agent/session correlation from the retained handle, plus current native composition identity. Company Job/Attempt/Worker/ProcessGeneration identity is supplied and verified by its existing owner, never minted from hostname, PID alone or an ACP UUID.
- Complete ordered `ctx.tools.schemas(handle.agent)` output. Omitted scope is forbidden. Preserve model-facing name, description, schema and order in the digest; set comparison alone loses prompt identity. Enforce exact allowed identities in addition to digest equality.
- The resolved definitions and their admitted source/composition provenance. Equal schema does not imply equal executable behavior. Freeze module/source and setup composition through the supply/native owner; do not stringify function bodies as provenance.
- Native effective model/provider/effort/token settings from the installed selection and native resolver, with evidence provenance identified. Do not return a prior successful catalog state as current health or actual response identity.
- Loader/composition observations after setup and creation settle. Loader diagnostic rows alone do not cover every scoped registration, disabled/conditional row, dependency or executable identity. Pair them with the admitted complete source recipe and exact Agent view. Pending, failed, conditional or unexplained entries refuse the first profile.
- Native tool presentation mode. N0 uses `native`, not PTC/both. The `run_code` transport is automatically introduced in non-native modes outside ordinary filtering; do not mistake a presentation change for a harmless cosmetic option.
- Completeness/unknown observations for every load-bearing dimension. Missing inventory is not an empty tuple; no `complete=true` supplied by a caller grants admission.

N0 fixtures use two explicitly artificial, in-memory tools and a fixture model adapter that counts and rejects real generation calls. They contain no private company data, provider credentials, real filesystem tool, shell, browser, MCP process/HTTP mount, autonomous job, subagent, title generation, compaction or retry plugin. These fixtures are public development stressors, not confirmation holdouts or a claimed production profile.

Observation serialization is a provider-private transient payload on the existing evidence/transport boundary, not a new persisted canonical schema or registry. Freeze a closed JSON field set in the implementation tests. Initial conformance bounds are 64 tool schemas, 128 composition rows, JSON depth 32 and 65,536 encoded bytes, also subject to any stricter existing transport limit. Exceeding a limit refuses; truncation must never look complete. Preserve arrays' order. Hash only a reviewed nonsecret allowlisted projection; never export or hash raw credentials, headers, environment dumps or arbitrary effective configuration.

## 6. Host evidence and consumer contract

The collector must not self-attest OS isolation, executable identity, provider principal or process-to-host placement. Existing native-process/realm/capability owners supply their independent receipts. Agent-native identity and OS ProcessGeneration identity must agree at intake. A byte digest supplies content integrity, not authenticated origin.

The Python consumer imports existing OHF dataclasses/comparison/wire functions rather than duplicating policy. Before constructing a complete `ObservedHarnessAttestation`, it checks closed shape, bounded values, exact expected native/process/session correlation and required observation completeness. It must not accept an untrusted callback or boolean that simply reports ALLOW.

Unknown, absent, stale-generation, mismatched, ambiguous or truncated required facts produce the existing unsupported/attestation-failure path. Complete admissible observations are passed to the existing comparator. Negative comparison blocks the first work turn; the experiment does not send a work turn merely to see whether it would have succeeded. Positive controls are explicitly synthetic admission examples, not real provider or production acceptance.

Use the existing materialization/attestation evidence path when this reaches an operational adapter. Do not embed secret-bearing or provider-private dictionaries into WorkerLaunchSpec, create an evidence database, or assign new company identities in the observer.

## 7. Ordering, correction and failure behavior

The permitted ordering is:

```text
existing owner admits fixed supply/profile/process budget
-> isolate process, environment, workspace and output before loading plugins
-> compose exact native services and fixture Agent
-> complete setup and creation announcements
-> collect exact scoped/native observations
-> combine separately verified host evidence
-> existing OHF comparison
-> persist bounded conformance evidence through the existing artifact owner
-> dispose owned handle and settle the native process/streams
```

No initialization is presumed effect-free: plugin setup and session creation can perform I/O or persist state. The N0 fixture has no MCP declarations and no autonomous producers; process/network negative controls must enforce that rather than relying on an empty input list.

A snapshot is not a lifetime grant. For later real work, revalidate required scope/config/source at the actual request and tool-dispatch boundaries using native hooks plus host enforcement. Native guards can deny but cannot elevate the Executive grant. No check-then-mutate window may admit changed tools or a different model/registration. If immutable closure or the required recheck cannot be enforced, that profile remains unsupported.

Correction creates new evidence under the proper native generation; it does not overwrite a finalized receipt, re-age an observation, silently switch models or revive an old handle. Rejected setup must unwind unpublished resources; post-publication cancellation must await owned teardown. Lost terminal/cleanup evidence remains uncertain and blocks retry/failover. No blanket process kill, worker-worktree cleanup or new recovery ledger is authorized.

## 8. Ordered tasks and discriminating acceptance

### Task 1 — native producer, not a look-alike mock

- [ ] Read the fixed source APIs listed in section 10 and assert their digests in the supplied bundle.
- [ ] Write RED tests for omitted scope, agent-owned tool escape, sibling isolation, same-schema implementation replacement and PTC mode change.
- [ ] Implement `observeOwnedAgent` in `observe.ts`, reading the exact retained Agent and installed native selection. Implement the minimal fixture composition in `fixture_host.ts` with native Agent creation and disposal.
- [ ] Prove a complete expected fixture can be observed, while all five mutations are rejected or reported as the exact incomplete state. A hand-built Python/JS dictionary is not native producer proof.
- [ ] Commit only the producer/fixture/test portion after the named tests pass.

Example test intent, to instantiate using the native fixture helper built in this task:

```text
fixture = create owned Agent with one permitted inherited tool
observe exact Agent -> expected schema/source identities
register unexpected tool in that Agent's own scope
observe again -> reject scope drift, despite inherited allow filter
observe sibling Agent -> must not contain the first Agent's tool
```

### Task 2 — one real existing-gate consumer

- [ ] Write RED tests for missing census, a fake empty census, altered schema/order, old native session, changed ProcessGeneration, wrong effective model and caller-selected ALLOW.
- [ ] Implement `compareNativeObservation` in `ohf_consumer.py`: validate and bind the private observation, construct existing OHF types only from complete owner-proven facts, invoke `compare_launch`, and expose its exact decision with the honest evidence scope.
- [ ] Feed actual fixture-producer bytes from Task 1 into this consumer. The positive control uses fully identified synthetic host evidence; omitting or changing it must refuse. The first-work counter stays zero in all N0 cases.
- [ ] Assert the consumer creates no Job, Worker, route, capacity grant, registry, provider call or new persistent store. Preserve existing comparator behavior; do not globally veto optional unknowns as a shortcut.
- [ ] Commit the consumer and its discriminating tests.

### Task 3 — native setup/cancellation and evidence qualification

- [ ] Run creation failure, late composition change, observation-size overflow, unexpected setup-time subprocess/network attempt and cancellation-before-observation cases under the existing qualified process owner.
- [ ] Assert no late observation is accepted after generation disposal and no failed setup publishes a success result. Teardown errors remain visible and cannot be converted to clean absence.
- [ ] Exercise incomplete plugin provenance separately from tool-schema completeness; matching schemas with a replaced implementation must not pass.
- [ ] Record exact runtime/source/dependency/profile/fixture identities, nonsecret native output, process/stream cleanup, test counts, known omissions and actual evidence scope in the existing artifact graph.
- [ ] Obtain exact-head/current-base tests and independent source review. Record N0 as BUILT_NOT_PROVEN for production, with the specific native fixture capability separately demonstrated.

N0 acceptance requires the real pinned native fixture producer AND the existing comparator consumer, including negative lifecycle/effect cases. The seven source-method fixtures below are design evidence, not a substitute. Do not create a green-only mapper and call native observation complete.

### Supply/activation gate

Actual DSH composition requires a qualified exact source/dependency/executable bundle and its existing native-process permission. This turn verified selected source blobs, not a complete installed dependency closure. Before native execution, the existing supply/capability owner must bind the fixed package recipe, executable/dependency hashes and notices. No floating installer, latest package, runtime network acquisition or reuse of the source-probe Node as an implicitly admitted toolchain. Missing supply is a concrete execution gate, not license to synthesize a positive fixture receipt.

## 9. Executed source-method experiment this turn

The exact `ToolRuntime.view`, `get`, `schemas` and `schemaOf` method text was extracted from verified upstream tool blob `6be7be61e257cd9e38c8a3122298316bf3df9892` and executed with explicitly artificial layer/mode dependencies under Node `v26.8.1`. No DSH application, Cordis lifecycle, provider adapter or production process was installed or run. The JSON snapshot dependency was a fixture clone, not proof of the upstream serializer implementation.

All seven asserted cases matched:

1. Global census sees only the inherited read tool.
2. Exact Agent census sees an Agent-owned write tool despite an inherited allow filter.
3. A sibling scope does not see that Agent-owned tool.
4. Same-name tools can expose identical schemas while their implementations differ.
5. Exact-scope resolution selects the shadowing implementation.
6. PTC adds `run_code` outside ordinary filtering.
7. A native sibling scope does not acquire that PTC transport.

Result identity: SHA-256 `2986609bb9ccac2236e1c2ff7a2e66c6a7dbb017139f4c71797e9de5d20bb4d1`. Evidence scope: `PINNED_SOURCE_METHOD_FIXTURE_NOT_DSH_RUNTIME`. The recipe is preserved in this document's appendix; it accepts only the exact pinned source blob and exercises no provider.

## 10. Exact implementation source references

Upstream repository `deepseek-ai/deepseek-harness`, commit `0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`:

- `packages/core/agent/src/index.ts`, blob `a7d39f6f9a80efc6a5038b8a1622b452b570e53e`, lines 33-204: setup commit, handle ownership, create/resume publication and disposal.
- `packages/core/tools/src/index.ts`, blob `6be7be61e257cd9e38c8a3122298316bf3df9892`, lines 1145-1274: exact-scope view, own-layer exemption, schema projection and PTC insertion.
- `packages/llm/llm/src/index.ts`, blob `bc5b5d6eb3f4215c2354bfa982ff22cae3e9cfbf`, lines 165-195 and 851-945: native resolution versus registration-bound prepared dispatch.
- `packages/host/plugin-inventory/src/index.ts`, blob `3beef6f0c0ac11001af6656f6af05e65678eb67d`: Remote-only Loader diagnostics, no new Context inventory API.
- `packages/bundle/acp-app/cordis.patch.yml`, blob `0fb24fee65f54f506519f1f5cf1a807e15406f04`: stock ACP is a patch over the larger base, not a sealed minimal profile.

Mastermind at protected `b14982837cc8146e3dc49e5862558ee399a1aa3d`:

- `control_plane/codex_operator_adapter.py`, blob `b1f7cfc1f083a6df19fe14c77384d9d5118054fc`, lines 1220-1339: existing native config/skills/MCP observation and mapping.
- `control_plane/operator_harness_contract.py`, blob `54df0b7a5abf0b713d5e37a40059802b1a894f08`: existing identity, requested/observed and comparison owners.
- `docs/superpowers/plans/2026-08-27-operator-continuity-ocr4-claude-sustained-operator.md`, blob `c0e1c5cf46f0fb1c191787b71bf31a389b48e5a3`, Task 2: observable served/current model or verified request before first turn, no hidden bootstrap query.

Unmerged #660 at `a614e422c1c84b3b55be6aa855205fd2e3b1931c`: `control_plane/remote_operator_harness_adapter.py`, blob `977d41020f0d2093c9c2a30808f20e0ce00b49d8`, lines 75-120: current mandatory native-resume profile. This is collision/dependency evidence, not protected authority.

## 11. Acceptance, routing and continuation

Sol adopts this as the proposed next design boundary for the harness program, not as protected production law or transfer of #600/#660/HF1/OHF/Agent Evaluation custody. The implementation worker should be the least-scarce eligible bounded engineer, preferably Terra/CTO Sol once frozen; WHY NOT FABLE: the source APIs, scope and falsifiers are now explicit and do not require a new principal program. Fable's existing integration/adoption decisions remain with that incumbent role. No actual worker was assigned by this record.

The primary next action is Sol's source-custody and supply preflight for the exact N0 six-path producer-to-consumer wave, then RED-first implementation on one reconciled carrier. Stop before native execution if its exact bundle/principal/process grant is unavailable. Report that precise gate; do not ask Chairman to choose accounts or manually relay generic prompts. #692 review/release decisions proceed independently; they are not a prerequisite for writing this isolated native conformance source.

Later waves remain distinct: a bounded real read/research Worker; then write/test capability; then truthful sustained rich operation including resume, cancellation, parent consumption and visible runtime proof. N0 must not expand into those waves, and those later capabilities must not be declared shipped from N0 tests.

This is a material architecture/conformance checkpoint for CONTEXT_ROTATION, not program completion. Preserve the nine earlier artifacts, #692 source/test evidence and this seven-case experiment. No Task/Job/Attempt/Worker, provider/credential operation, DSH install, hidden inference, holdout exposure, route, merge or deployment occurred. The retained A2 MacBook workspace is unchanged; its separate cleanup discrepancy was not retried. Continue from this source plus current exact heads, not the prior tool transcript.

## Appendix: provider-free source-method reproduction

The following original recipe requires Python 3 and an already available Node capable of TypeScript type stripping. Its input is a local copy of the exact upstream tools source; it never downloads dependencies. Running it is a source-method experiment only. The temporary TypeScript contains four extracted methods and fixture dependencies, not the complete upstream runtime.

```python
import hashlib, json, subprocess, sys, tempfile
from pathlib import Path
source = Path(sys.argv[1]).read_bytes()
blob = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
assert blob == '6be7be61e257cd9e38c8a3122298316bf3df9892'
text = source.decode()
def method(signature):
    start = text.index('  ' + signature)
    return text[start:text.index('\n  }', start) + 4]
methods = '\n'.join(method(s) for s in [
    'private view(scope?: ScopeKey): ToolView {',
    'get(name: string, scope?: ScopeKey): ToolDefinition | undefined {',
    'schemas(scope?: ScopeKey): ToolSchema[] {',
    'private schemaOf(definition: ToolDefinition, detachParameters: boolean): ToolSchema {',
])
program = '''import assert from 'node:assert/strict';
const RUN_CODE_NAME = 'run_code';
const snapshotJsonValue = value => structuredClone(value);
const read = {name:'read_file',description:'read',parameters:{type:'object'},execute:()=> 'original'};
const write = {name:'write_file',description:'write',parameters:{type:'object'},execute:()=> 'write'};
const shadow = {...read,execute:()=> 'different-implementation'};
const global = {tools:new Map([['read_file',read]])};
const A={}, B={}, P={};
const ownA={tools:new Map([['write_file',write],['read_file',shadow]]),admits:name=>name==='read_file'};
const ownB={tools:new Map(),admits:name=>name==='read_file'};
const byScope=new Map([[A,ownA],[B,ownB],[P,ownB]]);
class NativeView {
 layers={global,chainLayers:scope=>byScope.has(scope)?[byScope.get(scope)]:[],peek:scope=>byScope.get(scope)};
 modeFor(scope){return scope===P?'ptc':'native'}
 requirePtcTransport(){return {name:RUN_CODE_NAME,description:'code',parameters:{type:'object'}}}
METHODS
}
const tools=new NativeView();
const names=scope=>tools.schemas(scope).map(x=>x.name).sort();
const rows=[];
function check(name,actual,expected){assert.deepEqual(actual,expected);rows.push({case:name,actual,expected,pass:true})}
check('global_census_omits_agent_owned_tool',names(),['read_file']);
check('exact_agent_census_sees_scoped_tool_despite_inherited_allow_filter',names(A),['read_file','write_file']);
check('sibling_scope_does_not_see_agent_A_tool',names(B),['read_file']);
check('schema_identity_does_not_prove_implementation_identity',tools.schemas(A).find(x=>x.name==='read_file'),tools.schemas().find(x=>x.name==='read_file'));
check('same_name_actual_implementation_is_shadowed',tools.get('read_file',A).execute(),'different-implementation');
check('ptc_transport_is_added_outside_filter',names(P),['read_file','run_code']);
check('native_scope_has_no_ptc_transport',tools.get('run_code',B)===undefined,true);
console.log(JSON.stringify({scope:'PINNED_SOURCE_METHOD_FIXTURE_NOT_DSH_RUNTIME',tools_blob:'BLOB',native_runtime_installed:false,provider_calls:0,cases:rows},null,2));
'''.replace('METHODS', methods).replace('BLOB', blob)
with tempfile.TemporaryDirectory(prefix='dsh-source-method-') as directory:
    path = Path(directory) / 'probe.ts'
    path.write_text(program)
    run = subprocess.run(['node','--disable-warning=ExperimentalWarning',str(path)],
                         text=True,capture_output=True,timeout=15,check=True)
    result = json.loads(run.stdout)
    assert len(result['cases']) == 7 and all(row['pass'] for row in result['cases'])
    assert hashlib.sha256(run.stdout.encode()).hexdigest() == '2986609bb9ccac2236e1c2ff7a2e66c6a7dbb017139f4c71797e9de5d20bb4d1'
    print(run.stdout, end='')
```
