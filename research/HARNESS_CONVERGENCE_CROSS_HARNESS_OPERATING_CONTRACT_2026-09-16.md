# Harness convergence: cross-harness operating contract

**Disposition:** DRAFT / RECORDS ONLY / CHUNK 3A / PRODUCTION INERT. This document is a decision input inside the existing harness-convergence planning operation. It does not freeze architecture, start an Executive Job, assign a replacement writer, arm a provider route, install a harness, change a capability profile, or authorize credentials/provider inference.

**Planning operation:** `harness-convergence-dsh-teardown-20260916-sol-001`.

**Existing organizational home:** `WS:EXECUTIVE-CAPACITY-FABRIC`, program `shared-ai-provider-control`.

**Current protected Mastermind source / Skillpack:** `a78b8fe23d8e1ed129880ac47e97ebe96afa8aea`, `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1.

**Current Macro observation:** `5bf621772d7b77a06d2ba08c676c7961eb60260a`.

**Incumbent parity plan:** Mastermind #600, proposed plan head `a5c4f0f4c9561874ded59abf9a9466fe33734538`, existing integration operation `agent-fabric-end-to-end-fable-integration-20260913-sol-001`.

**Related open carriers:** #660 provider-neutral remote Operator Harness proxy; #590 Craft-through-Claude-compatible proof. They retain their own authors, gates and completion ceilings.

## 1. Ruling: standardize the company operating contract, not one executable

The desired product is not that every model runs the same binary, sees byte-identical prompts, or gives up useful native capabilities. The desired product is that any admitted worker or operator receives the same **company-grade operating conditions for its assigned job** and returns evidence through the same company authority path.

Three different meanings of parity must therefore stay separate:

1. **Governance parity** — every worker is admitted, bounded, attributed, reviewed, reconciled and continued through the same company owners.
2. **Environment parity** — every worker receives the capabilities, context, method and workspace needed for its role, with effective realization proved rather than merely configured.
3. **Behavioral parity** — comparable tasks actually produce acceptable outcomes at competitive cost/reliability. This is empirical and cannot be inferred from interfaces or tool lists.

Engine parity is not a goal by itself. Claude Code, Codex App Server, ACP, OpenCode and a future DSH runtime may remain different engines when their native implementation is useful. A common engine may later absorb compatible generic/API-model lanes if qualification demonstrates a lower total burden.

This means **no new Harness ABI v2, context database, model session registry or universal runner is justified by Chunk 3A**. The current worker and Operator Harness v1 contracts remain the northbound execution seams until a concrete incompatibility proves otherwise.

## 2. Existing owners already cover most of the operating contract

The cross-harness operating contract is a composition of existing authoritative owners. The name in this document is conceptual: it is not a new service or store.

| Requirement | Existing owner / contract | Current consequence |
| --- | --- | --- |
| Responsibility, Job identity, Attempt identity, lineage and authoritative terminal state | Executive Runtime / existing orchestration provenance | A native session or harness task never becomes company work merely because it exists. |
| Sealed foreground execution | `WorkerExecutionAdapter` + `mastermind.worker_execution_contract/v1` | Common start/status/result/cancel/validation floor already exists. |
| Rich session/turn execution | `mastermind.operator_harness/v1` | Common rich operations, effect semantics, process generations, provider-session binding and candidate results already exist. |
| Exact execution grants | `ExecutionCapabilityProfile` -> `RequestedExecutionProfile` / capability manifests | Skills, MCP, resources, plugins, native helper, write/network/approval/sandbox/auth policy belong here, not in provider prompt prose. |
| Organizational context | Agent OS `context_bundle.v1`, acquired read-only by `session_truth_acquire.py` and reconciled by Session Truth | No second context index or memory store is required. |
| Bounded execution-specific context | `mastermind.executive_job_packet/v1` | Objective, exact authorities/write paths/validation identities, route/profile identities, quota class, checkpoint and orchestration lineage already have a packet. |
| Working method / role practice | Capability Skills and proposed common Craft materialization | Method is distinct from authority. A role method may be prompt-rendered or natively mounted without creating a second role store. |
| Effective environment proof | OHF requested-vs-observed attestation; sealed launch/binary/process/effective-grant evidence | Configured or advertised capabilities cannot be treated as effective without provider/host evidence. |
| Typed results and artifacts | `WorkerResult` / `CollectionReceipt`; `CandidateResult`; `mastermind.executive_orchestration_result/v1` | Provider/native terminal messages are evidence inputs, never Job completion by themselves. |
| Review, repair and aggregation | existing Executive COO cycle / Runtime transactions | Native subagent orchestration may not become a shadow company review/repair scheduler. |
| Placement, quota and realm/host eligibility | Model Router + Capacity + Provider Control | Harnesses do not choose accounts/hosts/fallbacks after admission. |
| Durable organizational continuation | Agent OS | Native transcripts are subordinate execution state, not company memory. |
| Exact live continuation / return | SessionTargetRegistry + RuntimeBinding + Dialogue/Wake + OHF epoch/generation/session identities | Provider conversation/thread/session is rotating runtime identity, not stable responsibility. |
| Effect/retry reconciliation | Executive/OHF OperationId and existing retry-safety owners | Timeout/lost reply is never permission to replay on another provider, host or account. |

The most important architecture conclusion is that **cross-harness convergence is mostly a composition and conformance problem, not a missing-platform problem**.

## 3. The six-part effective operating environment

Every admitted worker/operator should be able to derive one effective environment from six already-owned inputs.

### 3.1 Responsibility envelope

Source: Executive Job/Attempt/orchestration provenance.

Must identify at minimum:

- exact Job and Attempt;
- root/parent lineage and orchestration role when applicable;
- objective and acceptance/result contract;
- current source/workspace identity;
- requested authorities and allowed writes;
- dependency revision / reviewed target for review or repair;
- attempt/repair/review ceilings that apply to this operation.

A provider-native task id, Claude query id, Codex thread id, ACP session id, DSH session id or OpenCode session id never replaces these identities.

### 3.2 Organizational grounding

Source: existing Agent OS `context_bundle.v1`, through the existing read-only Session Truth acquisition/reconciliation path when the workstream is in scope.

The current compiler already provides bounded, cited, authority-ordered context: higher law, workstream state, current decisions, fresh discoveries, latest handoff and artifact pointers, with omissions/degradation named. Mastermind already has a canonical read path for this data.

Therefore do **not** create `worker_memory`, `harness_context_db`, another retrieval index, or a second context packet family merely for workers.

A worker normally needs only the relevant projection, not the entire raw organizational store or CEO receipt. The launch/materialization layer should bind exact source/digest identity and a bounded projection appropriate to the Job.

### 3.3 Working method

Source: existing capability package/Skill owner and the common Craft method where admitted.

A method answers *how to work* for one role; it does not answer *what the worker may do*.

Examples:

- orchestration method for plan/aggregation;
- reviewer method for independent review;
- backend/frontend/research/data-science/verifier methods for bounded work.

Provider-native Skills may be used when exact source identity and effective loading can be attested. Prompt-method delivery is an acceptable compatibility path for a harness without a trustworthy native Skill primitive, provided the receipt says that native Skill attestation is false and no authority is inferred from the prompt.

### 3.4 Capability and authority profile

Source: existing execution-capability policy and RequestedExecutionProfile.

This is the normative description of required/forbidden capabilities and execution constraints. It should remain distinct from both context and method.

Required properties include:

- execution surface / harness identity;
- model and served-model expectation;
- exact workspace/source identity;
- sandbox, approval and network policy;
- write capability / exact allowed write paths;
- Skill, MCP, resource and plugin grants;
- native-helper policy and ceiling where applicable;
- authentication realm requirement;
- forbidden and allowed-ambient capabilities;
- exact profile/policy/package generation digests.

The profile is not allowed to contain provider credentials or caller-selected provider homes.

### 3.5 Provider-private realization

Source: the concrete adapter behind the existing worker/OHF boundary.

Each harness may realize the same company requirement differently:

- Codex may use App Server config, exact Skill roots/Skill inputs, MCP and thread/turn operations;
- Claude may use Claude Code / Agent SDK settings, Skills/MCP/tools and native process/session primitives;
- ACP may expose its standard automation surface;
- OpenCode may use its native configuration/instructions/tools;
- a future DSH engine may use a sealed profile/patch closure and ACP mapping;
- a generic API-only lane may have fewer capabilities and therefore qualify for fewer profiles.

The common contract should **not** force native mechanics into a universal wire. The existing CAP-S1 Codex Skill design is the model: common requested capability identity above, provider-specific path/source realization inside the adapter.

### 3.6 Evidence and continuation

Source: existing worker/OHF result contracts, Executive result seal, RuntimeBinding/Wake and Agent OS continuity.

The worker must return enough attributable evidence for the current consumer to decide whether the useful task is complete. The provider may retain richer local telemetry, but the company receipt must identify what was actually accepted.

Provider-native continuation is subordinate:

- native session resume is useful execution continuity;
- RuntimeBinding binds the current exact surface to stable logical responsibility;
- Agent OS preserves durable organizational continuation;
- neither native resume nor a handoff summary alone transfers company authority.

## 4. The one material gap: launch-time context composition

The repository already owns each major source of context, but their composition into every non-Codex/native harness is not yet one proven cross-harness capability.

The existing pieces are:

1. `mastermind.executive_job_packet/v1` — bounded execution-specific Job data;
2. Agent OS `context_bundle.v1` — bounded cited organizational state;
3. Session Truth — current-source reconciliation and semantic identity over requested scope;
4. capability packages / Skills / Craft — role method and exact reusable methods;
5. execution capability profiles — actual permissions and required runtime capabilities;
6. dependency/result identities — exact upstream work/review/repair evidence already owned by Executive Runtime.

The missing delta should be **one deterministic launch-time materialization step plus an evidence receipt**, implemented through existing owners. It is not another persistence layer.

Conceptually:

```text
Executive Job / Attempt
  + accepted capability/effective grant
  + exact Session Truth / Agent OS scoped context identity
  + selected role method / Skill grants
  + exact dependency/result references
        |
        v
bounded effective context for this Attempt
        |
        +--> sealed worker prompt/materialization
        +--> Codex rich turn input + exact native capabilities
        +--> Claude native query/session materialization
        +--> ACP/OpenCode/DSH provider-private realization
        |
        v
materialization/effective-environment evidence tied to Attempt + profile generations
```

Do not freeze a new public schema name until the incumbent HF1/OHF/capability owners prove which fields are actually missing. The evidence receipt, if required, should cite/digest existing source identities rather than copy their whole payloads into a second durable store.

### What this materializer must never own

It may not:

- create Jobs or Attempts;
- select provider/account/host/model outside the already-admitted binding;
- widen authority, tools or write paths;
- create a retry budget or fallback provider;
- write Agent OS memory;
- create a native session registry;
- declare task completion;
- hide omitted/degraded context;
- mutate a sealed profile after native work begins.

## 5. Native helper/subagent law

This is the other major place where a superficially unified harness could accidentally create a second orchestration plane.

There are two kinds of delegation and they must remain visibly distinct.

### Canonical child Job

Use an Executive child Job when the child work has any of these properties:

- independent acceptance or review value;
- its own provider/capacity placement decision;
- separate durable artifacts/result evidence;
- separate attempt/retry/effect reconciliation;
- can continue after the current native parent process/session ends;
- must be visible to company orchestration/aggregation;
- changes independence requirements or requires a different authority grant.

This is company orchestration and belongs to Executive Runtime/COO/Capacity.

### Native helper inside one Attempt

A native harness helper/subagent may remain a subordinate implementation technique only when all of the following are true:

- it is explicitly permitted by the admitted capability profile;
- its depth/count/resource ceiling is known and enforced;
- it inherits no broader authority than the parent Attempt;
- it cannot select a new provider/account/host outside the admitted realm;
- it cannot claim independent review;
- it creates no new company Job, retry owner, durable obligation or organizational memory;
- its effects remain attributable to the parent Attempt and included in its result/effect reconciliation;
- process/session cleanup proves the helper tree has reached the required quiescence.

A native helper can improve local reasoning parallelism without becoming a hidden fleet scheduler. DSH teams/jobs, Claude subagents, Codex native helpers and similar mechanisms all face this same distinction.

## 6. Current capability ledger for cross-harness parity

State here refers to cross-harness company capability, not whether individual source files exist.

| Capability | Current state | Evidence / limitation |
| --- | --- | --- |
| Provider-neutral sealed worker execution floor | `BUILT` | `WorkerExecutionAdapter` and `worker_execution_contract/v1` are protected source. |
| Provider-neutral rich operator method contract | `BUILT` | `operator_harness/v1` already defines common required/optional operations and effect semantics. |
| Provider-neutral remote rich proxy | `BUILT_NOT_PROVEN / UNMERGED` | #660 remains open; it deliberately adds no provider selector or new lifecycle. |
| Closed orchestration roles/results/review/repair | `BUILT` source / broader live journey not proven here | Existing COO cycle and orchestration result schema own plan/work/repair/review/aggregation. |
| Organizational context compiler | `PROVEN SOURCE CAPABILITY` | Macro `context_bundle.v1` is bounded/read-only; this planning turn did not run a worker through it. |
| Mastermind read-only acquisition/reconciliation of Agent OS context | `BUILT` source | `session_truth_acquire.py` already consumes canonical `context_bundle.v1`; Session Truth retains semantic identity/admission boundaries. |
| Sealed Executive Job packet | `BUILT` | `mastermind.executive_job_packet/v1` already carries execution-specific Job/profile/orchestration facts. |
| Exact capability-profile model | `BUILT` | Capability Skills/MCP/resources/plugins and requested-vs-observed OHF identities exist. Cross-provider realization is incomplete. |
| Codex native Skill/source attestation | `BUILT_NOT_PROVEN` / canary-gated | CAP-S1 defines exact provider-private realization and cleanup; do not generalize its wire mechanically. |
| Common Craft role materialization | `BUILT_NOT_PROVEN / OPEN CARRIER` | #590 demonstrates one provider-neutral prompt-method wrapper through a Claude-compatible adapter; not protected/live. |
| Cross-harness context + method + capability materialization | `PARTIAL` | Sources exist; no universal new store is missing, but equivalent effective realization/receipt is not proven across the target harness matrix. |
| Claude rich sustained common adapter | `SPEC_ONLY / INCOMPLETE` | Native Claude is heavily useful outside this contract; sustained common OHF parity remains a separate implementation lane. |
| ACP common worker | `BUILT_NOT_PROVEN`, narrow profile | Existing ACP integration is READ/RESEARCH and production routes/native factory remain held. |
| OpenCode native generic coding runtime | `BUILT_NOT_PROVEN` per current handoff | Candidate for generic compatible lanes; not adjudicated against DSH in Chunk 3A. |
| DSH as a Mastermind execution backend | `NOT_BUILT` | DSH ACP remains a challenger, not current critical-path dependency. |
| Exact return to logical parent / Web re-entry | `PARTIAL` | RuntimeBinding/Wake/Dialogue pieces exist; exact unattended personal-Web continuation remains separate full-parity proof. |
| Same workflow quality across harnesses | `NOT_PROVEN` | Requires controlled behavioral evaluation after conformance and permission proof. |

## 7. Cross-harness conformance test families

A tool list or a successful answer is insufficient. Every backend eventually admitted to one common profile class should pass the applicable discriminating tests.

### 7.1 Identity / route

- exact model/provider/harness/realm/profile generations match the admitted binding;
- wrong/missing realm or changed binary/config refuses before native work;
- no native default, alternate account or fallback endpoint silently substitutes.

### 7.2 Effective environment

- every required Skill/MCP/resource/tool is effectively present through the expected source generation;
- every forbidden capability is absent or independently denied at the enforcing layer;
- allowed ambient capabilities are explicitly identified rather than silently accepted;
- tool visibility does not exceed effective permission;
- provider-private initialization cannot widen the requested manifest.

### 7.3 Context/materialization

- the Job/Attempt and role are exact;
- cited organizational context comes from the requested current workstream/source identity;
- omitted/degraded context remains visible as degradation rather than becoming empty/healthy;
- role method source/digest matches the admitted package or prompt-method receipt;
- upstream dependency/review/repair identity cannot be swapped by the model or harness;
- materialization does not expose credentials or arbitrary host paths.

### 7.4 Result/evidence

- provider terminal state without a schema-valid result never completes the Job;
- Job/Attempt/Worker/root/role identity cannot be substituted in a result;
- artifacts and validations are bound to the exact accepted bytes/source revision;
- a rich CandidateResult remains a candidate until Executive acceptance;
- review of old bytes cannot approve later repair output.

### 7.5 Native helper / child control

- disallowed native helper capability refuses before work;
- admitted helper ceiling cannot exceed the parent profile;
- helper activity cannot create an independent company Job/review authority implicitly;
- native children are quiescent or explicitly reconciled before parent Attempt completion.

### 7.6 Continuation / effect uncertainty

- resume binds the already-owned provider session and exact workspace/source generation;
- wrong native session refuses rather than opening a fresh lookalike continuation;
- timeout/lost reply preserves `EFFECT_UNKNOWN` where applicable;
- no host/account/provider failover occurs until the existing owner has reconciled the original effect;
- RuntimeBinding generation protects against stale predecessor/surface authority.

## 8. Architecture laws proposed for later review

These are planning proposals, not protected law yet.

**Operating contract law**

> Every autonomous Mastermind worker or operator executes under the existing Executive lifecycle and one admitted execution/capability profile. Native harnesses may implement the assigned work with provider-specific mechanics, but they may not become owners of company admission, placement, identity, global retry, organizational memory, review independence or completion.

**Environment realization law**

> Required context, method and capabilities must be effectively realized and attributable to their exact source/profile generations. Configuration presence, prompt prose, tool advertisement or provider default state alone is not conformance.

**Native helper law**

> A native helper/subagent is subordinate execution inside one Attempt unless it enters the canonical Executive child-Job path. It may not independently claim review, capacity placement, durable company responsibility or effect recovery.

**No engine-equality law**

> Cross-harness parity means equivalent governed workflow capability for the admitted job, not identical native features, prompts, tool schemas or internal session mechanics. Unsupported capabilities remain explicit and constrain eligibility.

## 9. What NOT to build from this chunk

Do not create:

- `HarnessOS`, a second scheduler or a global DSH orchestrator;
- a new `harness_jobs` / session / retry database;
- a provider-neutral credential or account store;
- a second context index, worker memory database or transcript store;
- a second provider/account router inside a worker broker;
- a universal prompt format that exposes provider-private paths/mechanics;
- a fake common resume/steer/checkpoint capability for engines that do not support it;
- recursive native helpers that hide company child work from Executive limits;
- an engine benchmark before conformance, permission and evidence correctness are established.

## 10. Exact continuation: Chunk 3B

Chunk 3B should stay narrower than a migration plan.

**Mission:** define the **launch-time context and capability realization contract** across the current target backends, using existing source owners only.

For Codex sealed, Codex rich, Claude-compatible sealed, future Claude rich, ACP, OpenCode and DSH-challenger rows, record:

1. what exact company context/method/capabilities the profile requires;
2. how that harness can realize each requirement natively or through a compatibility projection;
3. what pre-dispatch evidence proves the effective environment;
4. what runtime evidence proves it did not widen authority;
5. what is unsupported and therefore must restrict routing;
6. which current PR/owner owns the missing implementation;
7. the minimum falsifier/canary for that row.

The output should decide whether the missing common delta is only a materialization/attestation receipt, or whether one existing contract actually needs a reviewed compatible extension. Do **not** choose DSH versus OpenCode or change provider routing in Chunk 3B.

After Chunk 3B, a separate chunk can define the controlled behavioral benchmark and generic-engine selection criteria. Migration waves come only after those two questions are settled.

## 11. Source register

| Ref | Exact source / observation |
| --- | --- |
| MM-PIN | protected Mastermind `a78b8fe23d8e1ed129880ac47e97ebe96afa8aea`; Skillpack INDEX/ACTIVE_EXECUTION/WEB_CEO_DELEGATION loaded from that same commit |
| M-WORKER | `control_plane/worker_adapter.py`; `control_plane/worker_execution_contract.py` at MM-PIN |
| M-OHF | `control_plane/operator_harness_contract.py` at MM-PIN |
| M-CAP | `control_plane/executive_agent_capabilities.py`; CAP-S1 protocol-attestation amendment at MM-PIN |
| M-JOB | `control_plane/executive_supervisor.py` at MM-PIN, including `mastermind.executive_job_packet/v1` prompt construction and launch/profile validation |
| M-RESULT | `control_plane/executive_orchestration_result.py`; `control_plane/executive_coo_cycle.py`; `control_plane/executive_coo_policy.py` at MM-PIN |
| M-CONT | `control_plane/session_targets.py`; Web-Sol context-continuity design at MM-PIN |
| M-TRUTH | `control_plane/session_truth_acquire.py`; `control_plane/session_truth.py` at MM-PIN |
| M-OCR4A | PR #660 head `a614e422c1c84b3b55be6aa855205fd2e3b1931c`, open at observation |
| M-CRAFT | PR #590 head `32861e4b1c2940eca4f25d709f1423d2b6700696`, open Draft/HOLD at observation; `worker_craft.py` in that candidate |
| M-PARITY | PR #600 plan head `a5c4f0f4c9561874ded59abf9a9466fe33734538`; latest consumed comments keep CEO-offline composition on existing Executive/COO/Capacity/Dialogue owners and exact Web re-entry separate |
| MACRO-PIN | Macro main `5bf621772d7b77a06d2ba08c676c7961eb60260a` |
| A-CONTEXT | Macro `scripts/agentos.py` at MACRO-PIN: read-only `context_bundle.v1`, default bounded budget, authority-ordered sections, no scheduler/queue/second retriever |
| A-WS | Macro `agentos/workstreams/WS-EXECUTIVE-CAPACITY-FABRIC.md` at MACRO-PIN; HF1 remains the provider-neutral worker/broker umbrella and warns against provider-specific brokers |

## 12. Proof ceiling

This Chunk 3A conclusion is source archaeology and architecture synthesis. No provider call, DSH/OpenCode launch, worker canary, profile mutation, credential read, browser interaction, Executive runtime mutation, test suite, CI run or production proof was performed here. Open PR author test counts were not reproduced. `BUILT`, `PARTIAL`, `SPEC_ONLY` and related labels above describe inspected source capability only where explicitly stated.

The research may be reviewed as a delta to the incumbent #600/#687 planning set. It must not be treated as a new implementation commission or as acceptance of any open carrier.