# Astra External Fabric Delegation — Architecture Freeze

Date: 2026-09-14
Status: **CHAIRMAN-APPROVED ARCHITECTURE FREEZE / SOURCE CANDIDATE / SPEC_ONLY / PRODUCTION_INERT**
Operation: `codex-astra-fabric-delegation-20260914-sol-001`
Existing program: `WS:EXECUTIVE-CAPACITY-FABRIC`
Existing integration operation: `agent-fabric-end-to-end-fable-integration-20260913-sol-001`
Protected source pin used for this freeze: `cf4c082d83fffe35daee81aa3d30bd27450bacf1`
Skillpack: `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap-major 1, loaded atomically from the protected source pin above.

This record freezes the architecture for reducing scarce Codex/Astra usage by making the existing Mastermind Agent Fabric the default execution substrate for bounded delegable work. It is an approved product/system design, not a claim that the implementation is installed or production-proven. Protection of this record does not arm a provider, credential, route, worker, COO cycle, Wake path, or autonomous production effect.

## 1. Outcome and 10/10 end state

The Chairman should be able to give an Astra orchestrator a substantial project and receive a reviewed, useful result without Astra spending most of its Codex budget reading the repository, making routine edits, running repeated tests, or carrying large worker transcripts in its own context.

Astra remains the scarce principal reasoning layer. It owns intent recovery, decomposition, architecture, hard cross-return judgment, exception adjudication, and final acceptance. The existing Executive/COO/Capacity/worker fabric owns routine execution. The fabric may use qualified external provider capacity so that implementation, research, testing, and independent review do not consume Codex capacity unless the task genuinely requires it.

The machine end state is:

```text
Chairman / project objective
          |
          v
Astra principal orchestrator
(intent, architecture, decomposition,
 exceptions, synthesis, acceptance)
          |
          | existing five-tool Executive MCP
          | submit_ceo_intent + canonical reads
          v
Authenticated Mastermind Executive App
(stateless transport; no lifecycle state)
          |
          | existing CeoIngress v2 request_ref path
          v
Executive Runtime strict-v2 root
(Job / Attempt / lineage / effect truth)
          |
          v
Existing COO cycle + Capacity
(plan / readiness / review / repair / placement)
          |
          +-------------------+-------------------+
          v                   v                   v
  qualified external     qualified native    bounded Codex
  subscription lanes     provider lanes      fallback only
          |                   |                   |
          +-------------------+-------------------+
                              |
                              v
                    canonical WorkerResult
                 + review / artifact evidence
                              |
                              v
                    Dialogue / Wake / binding
                              |
                              v
                     compact parent result
                              |
                              v
                   Astra final adjudication
```

The system is successful when Astra can complete representative projects while remaining primarily an orchestrator and measured Astra + internal-Codex usage falls materially without lowering acceptance quality.

## 2. Current source truth and capability ledger

The freeze is based on current protected source, not the older planning snapshot in PR #600.

| Capability | Current state at freeze | Architectural consequence |
|---|---|---|
| Executive five-tool MCP schemas and authenticated App composition | `BUILT_NOT_PROVEN` as source for this Codex use; production Codex registration not established | Reuse unchanged; do not add a parallel Fabric MCP server. |
| `submit_ceo_intent` caller shape | Existing frozen five-tool contract | Preserve unchanged unless a real canary proves insufficiency. |
| Executive App admission -> CeoIngress v2 | Built in `integrations/mastermind_executive_app/admission.py` | This is the delegation ingress. No new submit schema is needed. |
| CeoIngress automated v2 / strict-v2 root | Built in `control_plane/executive_ceo_ingress.py` and `control_plane/ceo_intent.py` | Trusted host composition, not Astra, decides whether the accepted request is strict-v2/cycle-eligible. |
| COO planner/review/repair/aggregation machinery | Existing source | Extend/use current owners; do not build another orchestration layer. |
| One-child native round trip | `BUILT_NOT_PROVEN` at protected W6-B source | Useful substrate; not production proof of external Fabric execution. |
| ACP/common-worker integration | Source merged | Reuse the existing worker contract and receipts. |
| Subscription provider plan metadata | Source merged | Reuse existing provider profile owner. |
| Subscription plan-to-harness binding | PR #583, not protected at freeze | Dependency gate; do not duplicate its files or source ownership. |
| Alibaba Codex Responses binding | `BUILT_NOT_PROVEN` on #583 candidate; autonomous disabled | First preferred external canary lane once #583 and its activation gates are accepted. |
| GLM / MiniMax external lanes | Mostly `SPEC_ONLY` on #583 candidate | Held until one external closed loop is proven. |
| Web/strategic vs operational autonomy law | PR #612 source candidate, not protected at freeze | Autonomous continuation must not outrun the accepted authority boundary. |
| Codex -> Mastermind Executive MCP registration | `DARK_OR_DISCONNECTED` / absent from observed Codex MCP census | First practical integration gap to close. |
| Codex exact-current-session Wake primitive | Built/tested for current `RuntimeBinding` / process generation; not yet proven for this Astra orchestration journey | First canary must prove exact parent binding; arbitrary/newest Codex tabs are forbidden fallback targets. |
| Repo-local internal Codex subagent policy | Built: Terra/medium, max 3 | Keep as bounded fallback, not the default execution path. |

The older `docs/EXECUTIVE_MCP.md` description of the legacy submit path must not be over-read. Current source composes the native five-tool MCP through `build_executive_mcp_app(...)`, whose Executive App admission layer keeps the five-tool caller shape but derives a stable `req-*` identity and sends the existing CeoIngress v2 frame. The receipt still truthfully reports `dispatched=false`: admission and later COO execution are distinct events.

## 3. Frozen authority and ownership boundaries

No new control plane is introduced.

| Concern | Canonical owner | This program may do |
|---|---|---|
| Root/child Job and Attempt lifecycle | Executive Runtime | Submit/admit through existing interfaces; never mirror lifecycle in Codex. |
| Plan, review, repair, aggregation, bounded continuation | Existing COO cycle / control service | Use and later extend ready-frontier behavior through the current owner only. |
| Provider/account/host suitability and quota | Capacity + Model Router / existing placement owner | Consume placement decisions; Astra never chooses provider credentials or account numbers. |
| Provider process/session execution | Existing common worker / Operator Harness / reviewed adapters | Qualify lanes and return canonical results. |
| Provider plan and harness binding | Existing subscription profile/binding owners | Consume #583 lineage; do not fork a second provider catalog. |
| Source workspace custody | Existing Executive workspace owner for workers; `mmx-workspace` for attended Web/host work | Never let Astra or external workers mint unmanaged worktrees. |
| Result routing and exact continuation | Dialogue + Wake + RuntimeBinding | Use existing exact-parent semantics; no Codex polling daemon or result bus. |
| Organizational continuity | Agent OS in Macro | Record material decisions/discoveries/handoffs through its current writer. |
| Codex tool transport | Existing Executive MCP / authenticated App | Stateless client composition only; no durable Fabric state. |

A provider thread, a Codex subagent, an Astra conversation, a Job, and an Attempt remain distinct identities. No transcript or model conversation becomes company lifecycle truth.

## 4. Frozen Codex client boundary

### 4.1 Reuse the current five-tool MCP

The Codex harness must connect to the existing authenticated five-tool Mastermind Executive MCP. The public tool surface remains:

- `executive_state`
- `executive_inbox`
- `executive_job`
- `ceo_intent_status`
- `submit_ceo_intent`

Do not add `fabric.delegate`, `spawn_minimax`, `spawn_glm`, `pool_run`, a generic shell tool, or another public worker-spawn API for this first vertical.

### 4.2 Why `submit_ceo_intent` is sufficient

The current Executive App admission path already:

1. validates the frozen `submit_ceo_intent` shape;
2. derives `request_ref` from the caller's stable `operation_key`;
3. reads trusted grounding immediately before effect;
4. removes `operation_key` from the semantic request;
5. sends `mastermind.executive_ceo_ingress_submit.v2` to the existing dedicated CeoIngress socket;
6. preserves `effect_unknown` rather than retrying;
7. reconciles only by the same `request_ref`.

The trusted Executive host decides whether v2 admission becomes a strict-v2 `executive_coo_cycle` root. Astra cannot set `intent_kind`, `business_impact`, execution binding, dialogue source, provider, model, account, UID, socket, or credential home.

That separation is frozen. The model authors bounded intent; trusted code authors execution authority and physical placement.

### 4.3 Admission is not execution

`dispatched=false` remains mandatory in the admission receipt. The client must never reinterpret it as failure, and the server must never change it to imply immediate execution.

The sequence is:

```text
Astra submit_ceo_intent
  -> accepted QUEUED root / dispatched=false
  -> existing strict-v2 COO cycle becomes eligible under its own gates
  -> child planning/dispatch/review/repair
  -> canonical result
```

If the installed host is not configured for strict-v2/autonomous COO admission, the request may remain a truthful queued root. That is an installation/gate failure to surface, not a reason to create a second dispatcher in Codex.

### 4.4 Exact Astra parent binding is part of completion

An arbitrary manually opened Codex tab/session is not automatically the parent merely because it called `submit_ceo_intent`. Production proof requires the Astra orchestrator to be an Executive-owned current Codex operator generation with an exact `RuntimeBinding`, process generation, and provider-native handle that the existing Codex Wake path can re-enter.

The system must never route by "latest Codex session", newest window, human-readable title, or provider account. If the exact bound Astra generation cannot be resolved, the durable result remains unconsumed and the capability is `PARTIAL`/blocked rather than being delivered to a neighboring session.

An attended arbitrary Codex session may prove MCP registration and read/submit connectivity, but it does not count as the end-to-end parent-continuation proof unless current Runtime evidence binds that exact native session/generation.

## 5. Astra operating policy

Astra is the principal, not the default worker.

### Delegate externally by default when all are true

A work unit is externally delegable when it has a bounded objective, explicit acceptance evidence, enough source identity for an independent worker to acquire its own context, and no decision reserved to Astra/Sol/Chairman.

Preferred delegation classes include:

- repository archaeology and source-grounded inventory;
- bounded implementation inside declared write paths;
- test execution and failure diagnosis;
- independent exact-artifact review;
- documentation tied to an accepted implementation;
- bounded research/synthesis with explicit inputs and output contract;
- repair work tied to an exact rejected candidate and review.

### Astra retains directly

Astra should keep work when it is primarily:

- Chairman-intent recovery;
- product/value thesis;
- systems/experience/intelligence architecture;
- cross-program/source-owner arbitration;
- a novel authority or safety ruling;
- a material plan/budget/depth expansion;
- final acceptance;
- reconciliation of ambiguous effects where the current evidence requires principal judgment.

### Internal Codex fallback

The existing repo-local internal-agent default remains Terra/medium with at most three concurrent threads. Internal Codex agents are a fallback when the Fabric cannot satisfy the required capability before effects begin, not the first choice for ordinary bounded execution.

A fallback must record a reason such as `FABRIC_UNAVAILABLE`, `REQUIRED_CAPABILITY_UNAVAILABLE`, or `EXTERNAL_LANE_NOT_PROVEN`. Unknown quota is not permission to assume availability. Once an external worker has started or an effect is uncertain, the same operation must not silently fall back to an internal Codex agent.

## 6. Context and token economics

The entire purpose of this feature is defeated if external work is delegated but its transcript is replayed into Astra.

### Worker input

A worker receives the smallest self-contained execution packet needed to do its bounded job:

- exact root/child/attempt identity supplied by existing Runtime;
- exact source/base and workspace grant;
- objective and acceptance contract;
- required capability package;
- declared write/validation boundary;
- exact dependency/result revision when applicable.

The worker reads source itself. Do not copy the entire Astra conversation into the child prompt.

### Parent return

The normal Astra return is a bounded result envelope/projected job view containing only:

```text
root/job/attempt identity
terminal or current state
provider/harness/host attribution when safe to expose
exact source/artifact revision or digest
bounded summary
validation evidence
independent review state/verdict
unresolved blockers / next required decision
result bounding receipts, if any
```

Full worker transcripts, reasoning traces, shell logs, and source dumps are not normal parent context. Astra may explicitly inspect additional canonical evidence only when a contradiction, review, or acceptance question requires it.

The existing `executive_job` output-bounding behavior remains the default read mechanism rather than a new result-summary store.

## 7. Routing and scarcity law

Astra never supplies a provider, model, provider home, API endpoint, credential, account number, or host target to `submit_ceo_intent`.

Capacity chooses the least-scarce capable eligible worker using current observations and reviewed bindings. The first external canary should prefer the closest already-built lane, currently the Alibaba Codex Responses binding from #583, only after all of its activation gates are satisfied.

Fable remains scarce principal capacity. External routine workers should absorb ordinary implementation/research/review tasks where capable. Provider expansion is not a prerequisite for the first token-relief proof.

## 8. Effect, retry, cancellation, and failover semantics

### Stable identity

Every modifying Astra delegation uses one stable `operation_key`. The authenticated App derives the canonical `request_ref`. Repeating the same logical request must reconcile to the same operation; changing the payload under the same identity must refuse.

### EFFECT_UNKNOWN

If the modifying call may have crossed the effect boundary but its reply is lost:

- do not resubmit with a new `operation_key`;
- do not fail over to Slack, a raw socket, a direct provider CLI, or an internal Codex agent;
- reconcile the same `request_ref` using the existing status/reconcile path;
- preserve effect uncertainty until canonical evidence resolves it.

### Provider failure

Pre-effect refusal may allow ordinary placement of another eligible worker if current policy permits it. Post-START or effect-unknown provider/host/account switching is forbidden until canonical reconciliation says the prior effect is settled and the existing retry owner permits a new attempt.

### Cancellation

Cancellation belongs to the existing Runtime/worker adapter contract. Astra does not kill provider processes directly. If process/RPC cleanup cannot be proven, the attempt stays uncertain/quarantined rather than being declared failed and retried elsewhere.

## 9. Fanout and recursion ceiling

This system must not transform one expensive Astra task into an invisible unbounded external agent tree.

All planner, work, review, repair, and aggregation children remain visible Runtime Jobs under current child/depth/budget rules. External workers do not gain a hidden recursive delegation authority from prompt text. A worker may use model-native helpers only when its admitted capability/profile explicitly permits them and their consumption remains inside the canonical budget/accounting owner.

The first vertical uses the current bounded COO child/review policy. Broader ready-frontier parallelism and deeper policy changes are separate reviewed waves after one real external closed loop succeeds.

## 10. Authentication, secrets, and installation

The Codex client should use the existing authenticated Streamable HTTP MCP surface and its supported OAuth flow where serviceability is proven. Do not commit bearer tokens, OAuth access tokens, cookies, provider credentials, policy secrets, or account credentials into `.codex/config.toml`, repository files, prompts, Agent OS, or Git history.

The installed Executive MCP process remains a dedicated non-login service identity and a stateless client of the canonical CeoIngress socket. Codex registration must not weaken the App's resource/scope checks or add the Codex user to Executive control/worker/C1 identities.

The active Codex process must prove the registered MCP tool census and auth generation before a modifying canary. A saved configuration entry is not proof that a running Codex session inherited credentials or can invoke the server.

## 11. Failure behavior

The first vertical must explicitly exercise and preserve these states:

| Condition | Required behavior |
|---|---|
| Executive MCP unreachable before effect | Refuse external delegation; internal fallback may be considered only before any effect and only with a recorded reason. |
| Auth missing/expired/revoked | Refuse; never paste or mint an ad-hoc token into repo config. |
| Strict-v2 host gate unavailable | Keep truthful queued/not-dispatchable state; do not side-step the COO cycle. |
| No eligible external provider | Park/return capability blocker; do not select a secret account manually in Astra. |
| Capacity observation stale/unknown | Treat as unknown, never unlimited. |
| Worker effect unknown | Quarantine/reconcile; no provider or internal failover. |
| Source/dependency revision moved | Refuse or re-admit through current owner; stale output cannot unblock a dependent child. |
| Review rejects candidate | Existing bounded repair/re-review path; Astra does not self-approve. |
| Result too large | Preserve canonical bounding receipt; Astra pulls more evidence only on demand. |
| Parent Wake unavailable | Result remains durable/unconsumed; no busy model polling. |
| Wrong/unbound Codex parent | Refuse delivery; never choose a neighboring/latest session. |
| Duplicate completion/return | Existing command/event identity reconciles; no duplicate child or result promotion. |
| Runtime/reasoning process restart | Recover objective, children, result and next action from canonical owners, not transcript replay. |

## 12. Instrumentation and acceptance ruler

Functional delegation alone is not success. The project exists to reduce scarce Codex consumption.

For every pilot, capture where available:

- Astra input/output/reasoning usage or the closest provider-reported usage counters;
- internal Codex subagent count and usage;
- external delegated worker count and provider/harness attribution;
- percentage of executable work units externalized;
- result-envelope bytes returned to Astra;
- number of manual Chairman message-relay/account-selection/`CONTINUE` actions;
- admission-to-first-dispatch latency;
- terminal-worker-result-to-parent-consumption latency;
- review/repair latency;
- duplicate/effect-unknown incidents and recovery outcome;
- accepted artifact/result and independent review evidence.

### First token-relief acceptance target

Use two materially comparable bounded project runs: a baseline Codex-heavy run and the external-Fabric run. The external-Fabric run passes the token-economics gate when:

1. the same acceptance contract is satisfied with independent review quality not worse than baseline;
2. Astra + internal-Codex measured usage is at least **50% lower** than the baseline using the best common usage unit available to both runs;
3. at least one substantive execution work unit is completed by a qualified external provider lane;
4. no full worker transcript is injected into Astra's normal result context;
5. the Chairman performs zero routine account selection and zero message shuttling between admission and returned candidate;
6. effect-unknown, duplicate, and restart paths do not create duplicate Jobs or provider attempts;
7. the returned candidate is consumed by the exact Executive-bound Astra Codex generation, not merely visible in Runtime.

If exact tokens are not exposed by a harness, use one documented common usage proxy for both runs and label it as a proxy. Do not fabricate token precision.

## 13. First independently useful vertical

This freeze authorizes planning for one closed-loop capability only:

> **An Executive-owned Astra orchestrator submits one bounded program through the existing five-tool Executive MCP; the installed App admits the request through CeoIngress v2 into the existing strict-v2/COO fabric; one qualified external worker lane performs substantive work; the canonical review/result path returns a compact result to the exact bound Astra Codex generation; Astra performs final acceptance; measured Astra/internal-Codex usage is materially lower than the baseline.**

The first external lane should be Alibaba Codex Responses if #583 is accepted and its current activation gates pass. That is a routing recommendation, not an override of Capacity or provider eligibility.

### Held for follow-on plans

The following are explicitly outside this first implementation plan:

- broad ready-frontier parallelism correction;
- deeper/nested child policy expansion;
- GLM/MiniMax fleet completion;
- multi-host recovery beyond what the first canary requires;
- Live Fabric UI redesign;
- new MCP tool names or schema expansion;
- OpenAI Agents API adoption as a Mastermind scheduler;
- generic external-agent spawning from arbitrary workers;
- production deployment authority or live-capital authority.

## 14. No-rebuild boundaries

The implementation is rejected if it introduces any of the following:

- a second Job/Attempt/lifecycle store;
- a Codex-owned task queue;
- a provider/account registry outside existing profile/Capacity owners;
- a new retry or effect-unknown journal;
- a worker transcript database;
- a generic `pool run`/shell/provider-spawn MCP tool;
- a second Wake/result bus;
- caller-selected provider credentials or host targets;
- blind failover after uncertain effect;
- a hidden recursive subagent tree not counted by current policy;
- a change to the frozen five-tool schema merely to make this first canary convenient;
- a newest-tab/newest-session Codex parent resolver.

## 15. Dependencies and gates

Implementation may build and test source behind disabled/non-arming gates, but real autonomous canary execution requires all applicable current gates.

- PR #612 or an equivalent accepted current authority ruling must permit the intended operational continuation without a routine Astra/Web turn.
- PR #583 or its accepted successor must own the reviewed subscription harness binding; this plan must not duplicate its files.
- A current provider realm/credential enrollment and Capacity observation must exist for the selected external lane.
- The installed Executive MCP/App/CeoIngress generation must be current and authenticated.
- The strict-v2/COO path must be armed through its existing owner, not by Codex configuration.
- The selected project/source workspace must use current canonical custody.
- The Astra orchestrator used for production proof must be materialized/bound through the existing Codex Operator/RuntimeBinding path.

A missing gate produces a named blocker. It does not authorize a bypass.

## 16. Frozen decision

**APPROVED AND FROZEN:** Astra becomes an external-delegation-first principal through the **existing authenticated five-tool Executive MCP**, which already maps `submit_ceo_intent` into the transport-neutral CeoIngress v2 path. Executive Runtime/COO/Capacity remain the orchestration and placement authorities. External workers carry routine execution load. Internal Codex subagents are bounded fallback. Parent context receives compact canonical results, not worker transcripts, and end-to-end completion requires exact Runtime-bound Astra parent consumption.

Any implementation that requires a second scheduler, a raw provider-spawn interface, provider choice by Astra, a duplicate lifecycle, an in-place widening of the five-tool contract, or guessed/latest-session parent routing is outside this freeze and must return for architecture review.