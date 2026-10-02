# Harness convergence: backend realization matrix

**Disposition:** DRAFT / RECORDS ONLY / CHUNK 3B / PRODUCTION INERT. This record continues the Chairman-authorized multi-turn harness-convergence planning operation. It does not freeze a new ABI, start an Executive Job, change a provider route, install a harness, mutate a capability profile, enroll an account, read credentials, run provider inference, or transfer an incumbent source owner.

**Planning operation:** `harness-convergence-dsh-teardown-20260916-sol-001`.

**Existing organizational home:** `WS:EXECUTIVE-CAPACITY-FABRIC`, program `shared-ai-provider-control`.

**Protected Mastermind source and Skillpack:** `a78b8fe23d8e1ed129880ac47e97ebe96afa8aea`, `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1.

**Current Macro observation:** `de36a37a3a4738e5cd59db31345790002f2582db`.

**DeepSeek Harness upstream source:** `deepseek-ai/deepseek-harness@0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`; the upstream `master` head was re-read during Chunk 3B and remains exactly the Chunk 2 pin.

**Existing parity program:** Mastermind #600 / `agent-fabric-end-to-end-fable-integration-20260913-sol-001`. Existing HF1, PF1, OCR-4/OCR-4A, Provider Control, Capacity, capability, native-process, OpenCode and ACP owners retain implementation custody.

## 1. Executive ruling

The backend-by-backend archaeology does **not** justify `mastermind.worker_adapter/v2`, `mastermind.operator_harness/v2`, a universal provider runner, a second context protocol, or a DSH/OpenCode control plane.

The two existing interface floors remain correct:

- `mastermind.worker_adapter/v1` + `mastermind.worker_execution_contract/v1` for one bounded foreground/sealed worker process;
- `mastermind.operator_harness/v1` for a sustained rich provider session with explicit start/turn/event/cancel/reconcile semantics.

The real common gap is narrower and asymmetric:

1. **Rich operator northbound contract:** already sufficiently expressive. The missing work is provider-specific realization and proof, especially pre-work observation of the exact session/model/effective capability state.
2. **Sealed worker northbound process contract:** already sufficiently minimal and provider-neutral. However the current **execution-capability policy and ExecutiveSupervisor profile/complete-attestation composition are still Codex-shaped**. They need a compatible provider-neutral evolution through the existing capability/HF1 owners.
3. **Context/method delivery:** existing Job packet, Agent OS/Session Truth, Skills/Craft and dependency/result identities need one deterministic Attempt-bound materialization receipt. They do not need a new memory database or universal typed provider prompt wire.

Therefore the convergence work is a **policy/materialization/attestation evolution around v1**, not an ABI replacement.

## 2. What is already provider-neutral and what is not

### 2.1 Worker adapter floor is already intentionally small

`WorkerExecutionAdapter` requires only:

```text
start
status
collect_result
cancel
run_validation_argv
```

Its own source law explicitly states that future provider adapters plug into this interface without receiving a queue, lease model or lifecycle database. Optional launch-attestation, UID-sweep and cleanup receipts are feature-detected by the supervisor and may be required by a provider's acceptance policy.

`WorkerLaunchSpec` already carries provider-neutral Attempt/job/worker identity, workspace/run directory, bounded prompt/result schema, authorities, model/effort, timeout/cancel bounds, expected base SHA, artifact/write boundaries, isolation manifests, worker UID/GID and secret-canary facts. Provider configuration and credentials are intentionally absent.

That is a feature, not a missing field set. Do not add provider home, API base URL, credential reference, account selector, session registry, retry policy or native configuration dictionary to `WorkerLaunchSpec`.

### 2.2 The sealed supervisor is still Codex-specific above that floor

Current `ExecutiveSupervisor._validate_execution_profile()` accepts only the present Codex sealed shape:

```text
execution_surface == codex-exec
auth_realm == dedicated-worker-account
approval_policy == never
network_policy == disabled
native_helper_policy == DISABLED
skills == empty
mcp_servers == empty
plugins == empty
```

The current `ExecutionCapabilityRegistry` itself admits only `codex-exec` and `codex-app-server` execution surfaces and one dedicated-worker-account auth realm. This means the broker/adapter boundary is provider-neutral but the policy projection above sealed workers is not yet provider-neutral.

Likewise, `ExecutiveSupervisor` currently treats the complete sealed launch-attestation schema as the Codex worker's `LAUNCH_ATTESTATION_SCHEMA_VERSION`; if an adapter does not expose `launch_attestation`, it receives only a legacy partial process/binary/base-SHA receipt. A non-Codex worker can implement the common process floor today, but there is no common complete sealed-environment attestation shape that proves an exact non-Codex capability profile.

This is the most important Chunk 3B implementation delta.

### 2.3 Rich OHF already has the necessary profile/attestation vocabulary

`RequestedExecutionProfile` already separates:

- Worker/provider/requested model;
- harness kind/version/binary digest;
- exact workspace identity;
- sandbox / approval / network policy;
- exact required, allowed-ambient and forbidden capability identities;
- native-helper policy;
- authority-policy hash;
- auth-realm requirement and optional expected provider account;
- expected effective-config digest;
- write-capability and allowed-write paths.

`ObservedHarnessAttestation` separately records the observed served model, harness version/binary, structured capability identities, effective Skills/MCP/plugins/apps, sandbox/approval/network state, effective-config digest, auth fact, workspace and observed native-helper ceiling. `compare_launch()` remains pure and no work turn may begin before `LaunchDecision.ALLOW`.

Do not duplicate this vocabulary for rich Claude, DSH or a future OpenCode operator.

## 3. Proposed compatible sealed-worker convergence seam

This section describes the minimum delta; names are conceptual until the incumbent HF1/capability owner freezes the exact schema.

### 3.1 Provider-neutral execution-profile realization

Evolve the existing `ExecutionCapabilityRegistry` owner so an execution profile can name additional reviewed sealed surfaces without moving provider-private configuration into Job data. For example, future accepted surfaces may distinguish:

```text
codex-exec
claude-foreground-cli
acp-stdio
opencode-native
```

and later a qualified DSH surface if needed.

The registry remains secret-free. Each surface maps through a reviewed adapter/native owner that knows how to realize it. A profile identity says **what effective capability must hold**, not how to construct arbitrary provider arguments.

Provider/model/host placement still occurs before adapter launch through Model Router/Capacity/Provider Control. The capability registry does not become a router.

### 3.2 Common sealed launch-evidence envelope, provider-private observation inside

The supervisor needs a provider-neutral way to require complete evidence without requiring every adapter to emit the Codex launch schema.

The compatible shape should bind common facts such as:

```text
Attempt / Worker / adapter identity
exact executable and process generation
workspace / base source identity
execution-profile and capability-policy identities
materialized-context/method identity
sandbox / network / approval / write boundary as applicable
credential-value-absent statement / secret-canary evidence where applicable
provider-private attestation identity + digest
```

The concrete adapter may retain a provider-private observation payload. The common envelope should never demand that Claude, ACP, OpenCode or DSH pretend to have Codex's config fields.

This can remain an **optional feature-detected receipt on `WorkerExecutionAdapter/v1` that a profile makes mandatory**. The v1 method protocol does not need a breaking change merely to standardize the receipt the supervisor expects from newly admitted profiles.

### 3.3 Deterministic Attempt context/materialization receipt

Before provider work, one existing owner composes only the Job-relevant projection of:

- `mastermind.executive_job_packet/v1`;
- exact Agent OS / Session Truth scoped context identity when required;
- exact Craft/Skill/practice method identity when admitted;
- accepted dependency/result/review identities;
- exact execution-capability profile/generation.

The output may be rendered as a prompt for a sealed worker or supplied through a provider-private rich turn loader. The common receipt should retain source/digest/omission identity and final model-input/materialization digest. It must not become a transcript store or copy Agent OS into another database.

A provider-native Skill input or MCP config remains adapter-private realization. Prompt-method Craft remains a compatibility realization whose receipt truthfully says native Skill attestation is false.

## 4. Backend realization matrix

### 4.1 Codex sealed worker

**Current floor:** `CodexWorkerAdapter` behind `WorkerExecutionAdapter/v1` and the current `ExecutiveSupervisor`.

**Company context/method realization:** Executive job packet in the sealed prompt; common Craft can wrap the prompt. Current sealed profile intentionally denies richer MCP/plugin/native-helper surfaces.

**Pre-dispatch / launch proof:** strongest existing sealed path. Exact binary/process/workspace/isolation/secret-canary and complete launch evidence are already supervisor-consumed.

**Anti-widening:** exact authority/write paths, isolated workspace/run roots, supervisor-owned validation, no caller provider-home fields.

**Unsupported/routing consequence:** richer Skills/MCP/resources/continuation belong to Codex rich App Server rather than pretending the sealed CLI supports them.

**Contract verdict:** `WorkerExecutionAdapter/v1` fits. No adapter-interface change.

**Minimum falsifier:** a profile requiring any unimplemented native surface must refuse before provider work; changed binary/base/profile identity must not cross RUNNING.

### 4.2 Codex rich App Server

**Current floor:** `CodexOperatorAdapter` implements `mastermind.operator_harness/v1`.

**Company context/method realization:** provider-private `TurnInputLoader`; CAP-S1 already demonstrates a closed `CodexTurnInputEnvelope` for path-bound native Skill input without changing the common OHF method contract.

**Pre-work proof:** App Server initialization reads actual account/config/Skills/MCP state before `thread/start`; binary is re-hashed at the launch boundary and again during initialization. Observed config becomes `ObservedHarnessAttestation` and is compared against the sealed request before the first work turn.

**Anti-widening:** wrong Worker/provider/harness/binary/version/workspace/sandbox/approval/network/helper/config identities refuse. Native helper ceiling is observed only when the exact parent policy/config supports it.

**Current optional operations:** native resume yes; fork/steering/approval/checkpoint/config staging currently no; provider-native idempotency false.

**Contract verdict:** OHF v1 is the reference conformance backend. No rich-contract extension found.

**Minimum falsifier:** same-name Skill with wrong content/source generation, unexpected MCP/plugin, unknown served model, changed config, changed binary or wrong resume session must refuse before a work turn or preserve effect uncertainty.

### 4.3 Claude-compatible sealed worker — GLM / Alibaba / MiniMax compatibility lane

**Current floor:** merged source for `ClaudeSubscriptionWorkerAdapter`, fixed reviewed subscription profiles/bindings and hermetic interactive-canary admission; production adapter descriptor remains disarmed.

**Important identity rule:** this is a **Claude Code execution harness for external compatible providers**, not native Anthropic Fable/Opus capacity.

**Current effective environment:** deliberately narrow. Read/Glob/Grep; optional Edit/Write only for WRITE_BRANCH; Bash/Agent/Task/Skill/Web/MCP denied; strict empty MCP; Chrome disabled; no session persistence; provider retries forced to zero where controllable.

**Company context/method realization:** ordinary sealed prompt; open Craft carrier #590 shows the common prompt-method wrapper can select a role and reach this adapter without provider-specific Craft code. Native Skill attestation remains false.

**Pre-work proof:** provider realm/capacity/catalog/admission facts are sealed outside `WorkerLaunchSpec`; launch attests exact binary/process/workspace/provider session/result. Production route remains held.

**Anti-widening:** launch cannot select provider/base URL/credential/fallback; credential bytes enter only at provider-private spawn boundary.

**Contract verdict:** the sealed worker method floor fits. To make this a normal profile-governed Executive lane, the provider-neutral capability-registry/supervisor profile and complete-attestation evolution is required; do not add Claude-provider fields to `WorkerLaunchSpec`.

**Minimum falsifier:** wrong binding/realm/capacity/admission generation, unexpected tool/MCP/native-helper exposure, autonomous use under interactive-only policy, or changed provider profile must refuse before spawn.

### 4.4 Native Anthropic Claude sealed worker / PF1

**Current state:** planned native owner, not the external-provider worker above. Current parity records explicitly distinguish PF1 native Anthropic subscription custody from #581's compatible-provider harness. A production native worker is not proven here.

**Target first slice:** foreground native Claude CLI behind the common sealed Worker contract, using dedicated worker-principal native authentication; no first-slice resume or hidden native fleet.

**Company context/method realization:** same sealed Attempt materialization path; provider-native Skills/MCP/browser are separate later profiles, not ambient defaults.

**Contract verdict:** `WorkerExecutionAdapter/v1` remains sufficient for PF1's first one-shot proof. The provider-neutral sealed profile/attestation evolution is a prerequisite for truthful capability parity beyond a minimal source-specific adapter.

**Minimum falsifier:** no copied/exported native credential; exact provider/model/binary/workspace; unexpected native settings/Skill/MCP/agent/browser surface refuses; process exit alone never fabricates provider-task success.

### 4.5 Future native Claude rich operator / OCR-4

**Target floor:** `mastermind.operator_harness/v1`; do not replace PF1 sealed worker.

**Planned native realization:** one transient provider-private generation helper per OHF ProcessGeneration using a pinned Agent SDK and exact Claude CLI. The helper owns one `ClaudeSDKClient`, a closed framed protocol and provider-private session state; it owns no Job/Attempt DB, retry loop, queue or memory authority.

**Critical conformance gate:** before implementation, prove the installed public Agent SDK/CLI can establish and expose enough session/configuration evidence with `connect(prompt=None)` **without sending a model work turn**. At minimum the exact provider-session identity, requested/served model evidence, effective customization/MCP state and CLI/SDK identity must be observable strongly enough for TX-4.

If a stable provider session cannot be observed/preselected and verified before the first work query, return `UNSUPPORTED_PREWORK_SESSION_ID`; do not weaken OHF by sending a hidden bootstrap model prompt merely to create identity.

**Permission learning from current native Claude browser work:** an inline child/tool list is not an authority boundary by itself. Native conformance work reproduced that omitted MCP tools could remain executable under a broader parent. Any Claude rich adapter therefore needs a complete effective tool/MCP census and exact deny-complement or stronger server-side enforcement, plus the existing requested-vs-observed comparison.

**Contract verdict:** OHF v1 is adequate **if and only if** the native surface can satisfy the pre-work attestation requirement. The blocker is provider observability, not a missing OHF field.

**Minimum falsifier:** initialize with zero user/model turn; prove exact provider session/model/config/tool set; then introduce one ambient MCP/tool or wrong session/model and require launch refusal before `query()`.

### 4.6 ACP sealed worker

**Current floor:** `AcpWorkerAdapter` composes official ACP SDK semantics into the existing Worker contract. Current first profile is READ/RESEARCH and refuses arbitrary validation/RUN_TESTS.

**Native process substrate:** `AcpNativeProcessOwner` now exists in protected source as a fixed reviewed executable/argv/environment process owner. It keeps provider selection, credentials and route activation outside `WorkerLaunchSpec`, binds exact workspace/base/UID/GID, and emits a native launch receipt. This source existence does not mean a production ACP factory/route is armed.

**Result/effect behavior:** protocol terminal alone cannot release the lane; success must validate through common `WorkerResult`/`CollectionReceipt`. Cancellation requires the original prompt terminal plus matching native cleanup. Lost RPC/unsettled SDK/native cleanup stays effect-uncertain; no hidden resubmission/account/host failover.

**Contract verdict:** `WorkerExecutionAdapter/v1` fits the current sealed ACP profile. A production non-Codex capability profile needs the common sealed capability/attestation evolution. A later sustained ACP operator can target OHF v1 rather than growing a second ACP lifecycle.

**Minimum falsifier:** wrong process/workspace/schema identity, missing terminal cleanup, prompt terminal without valid result, or capability outside the READ/RESEARCH profile must not produce success.

### 4.7 OpenCode native coding harness

**Current source substrate:** OpenCode Go request-custody/stream/loopback code exists, but the Attempt-owned `GoHarnessEndpoint` explicitly is **not** a Worker adapter, account allocator, retry ledger or daemon. It depends on the existing worker/supervisor to supply fixed session/model/account, private client capability, credential loader, request admission, cancellation and terminal-failure consumption.

**Useful property:** it fail-stops permanently after the first admitted provider failure so an OpenCode outer retry loop cannot send a second provider request after an unknown effect. This is subordinate protection, not a new retry owner.

**Current missing native vertical:** one fixed OpenCode coding process behind the common Worker adapter, exact effective-config observation, a write-capable reviewed profile, real provider/account admission and accepted coding result. Existing ACP first profile cannot be relabelled write-capable.

**Effective-environment risk:** OpenCode configuration is merged from multiple sources. An `OPENCODE_CONFIG` file by itself is not isolation. A native adapter must prove the final effective providers/plugins/tools/instructions/settings and prevent direct-provider fallback before loading the real provider credential.

**Company context/method realization:** one sealed process may receive the Attempt materialized prompt/method and preserve its own local transcript/tool state as subordinate execution state. Company continuity still belongs to Agent OS/Executive.

**Contract verdict:** start OpenCode as a `WorkerExecutionAdapter/v1` realization, not a new orchestration service. No v1 method change is needed. The provider-neutral sealed profile/attestation evolution is required before claiming environment parity. Later rich operation is a separate qualification.

**Minimum falsifier:** ambient project/global plugin/provider/tool survives the sealed profile, direct-provider fallback exists, outer retry after partial/unknown effect causes a second upstream send, or fixed model/session/account binding changes mid-Attempt -> refuse/quarantine.

### 4.8 DeepSeek Harness challenger

**Upstream stability check:** upstream `master` remains at the exact Chunk 2 pin during this review.

**Preferred qualification surface:** DSH ACP, not DSH's current Claude/Codex one-shot subagent wrappers. The ACP server offers new/list/resume/close, one prompt at a time per session, prompt cancellation, serialized semantic updates, model/reasoning configuration and MCP attachment. It persists resumable sessions across process restart.

**Important trust boundary:** ACP `authenticate` immediately succeeds; the stdio controller is trusted. Mastermind must provide process/host authentication and isolation outside DSH. DSH may not become the account/host/Job authority.

**Pre-work potential:** `initialize` and `session/new` expose protocol/configuration state before `session/prompt`, making DSH a plausible OHF-v1 challenger. However configured provider/model and advertised capabilities are not automatically proof of the actual served model or a sealed effective plugin/tool/profile closure. Qualification must establish exact observable evidence instead of filling OHF fields from configuration assumptions.

**Ambient/runtime risk:** DSH is an everything-is-a-plugin developer-preview system with persistence, jobs/subagents/retry/compaction and other services. A Mastermind execution profile must mount an explicit frozen closure, disable independent retry/fallback/autonomous producer surfaces, and prove the effective tool/profile census plus host sandbox. The DSH plugin tree cannot become a second company scheduler or memory owner.

**Contract verdict:** two legal candidate shapes exist, neither built today:

1. a narrow DSH sealed worker behind `WorkerExecutionAdapter/v1`; or
2. a sustained DSH ACP adapter behind `OperatorHarnessAdapter/v1` if exact pre-work/environment observations satisfy OHF.

No common ABI extension is justified before this conformance test.

**Minimum falsifier:** start a frozen DSH profile, prove exact binary/profile/provider/model/tool/retry/autonomous-producer state before prompt, then inject one ambient plugin/retry/model fallback or wrong resumed workspace/session; the adapter must refuse before work or preserve effect uncertainty.

## 5. Cross-backend conformance ledger

| Backend | Northbound floor | Current common-profile fit | Current main missing proof / implementation | ABI change? |
| --- | --- | --- | --- | --- |
| Codex sealed | Worker v1 | strong for current narrow Codex profile | none for baseline; broader capabilities belong rich | no |
| Codex rich | OHF v1 | strongest reference | production acceptance/current owner gates, not contract vocabulary | no |
| Claude-compatible external provider | Worker v1 | process floor yes; common capability profile not yet generic | production activation + provider-neutral sealed profile/attestation | no |
| Native Claude sealed PF1 | Worker v1 | target fits | actual native worker + provider-neutral sealed profile/attestation | no |
| Native Claude rich OCR-4 | OHF v1 | target fits conditionally | pre-work native session/model/effective-capability observability | no unless falsifier disproves realizability |
| ACP first profile | Worker v1 | process/result floor yes | production factory/route + provider-neutral sealed profile/attestation | no |
| OpenCode native | Worker v1 first | target fits | actual Worker adapter, sealed effective config, write profile, real canary | no |
| DSH ACP challenger | OHF v1 candidate | plausible, not qualified | frozen composition + pre-work attestation + no duplicate retry/lifecycle/tool authority | no evidence for change |

## 6. The exact shared implementation deltas

### Delta A — generalize capability policy without generalizing provider secrets

Current `ExecutionCapabilityRegistry` execution-surface/auth-realm enums and sealed Supervisor gate are Codex-specific. Existing capability/HF1 owners should evolve these to provider-neutral reviewed surface identities and profile-to-adapter realization while keeping provider homes, credentials and account selection adapter-private.

**Owner:** existing ExecutionCapabilityRegistry + HF1/Operator Harness convergence owner.

**Do not:** create `HarnessProfileRegistry`, provider-specific profile databases or caller-selected adapter args.

### Delta B — provider-neutral complete sealed launch evidence

Make the supervisor able to require complete launch/effective-environment evidence from a non-Codex adapter without requiring the Codex attestation schema. Preserve a small common envelope and provider-private evidence identity/digest.

**Owner:** HF1 / Executive supervisor common worker path.

**Do not:** weaken complete evidence to binary/PID only for non-Codex workers or make provider output self-authorizing.

### Delta C — Attempt materialization receipt

Compose Job packet + bounded Session Truth/Agent OS context + admitted method + dependency identities + capability generation before provider work. Record exact source/materialized-input digests and named omissions/degradation. Delivery may be prompt or native provider mechanism.

**Owner:** provider-neutral execution/materialization under HF1/Operator Harness, consuming Agent OS/Session Truth and capability owners.

**Do not:** persist another company memory store or put arbitrary provider-native paths into the Executive Job wire.

### Delta D — backend-specific effective observation

Each adapter must prove its own real environment:

- Codex App Server: already the reference;
- Claude: pre-work Agent SDK/CLI session/config plus exact MCP/tool denial/census;
- ACP: fixed native process/profile and protocol/result cleanup;
- OpenCode: merged effective config/provider/tool/retry state;
- DSH: frozen plugin/profile closure, route/tool/retry/autonomy state and host isolation.

Unknown required observations fail closed. No common layer fabricates provider facts.

## 7. What this means for COO/Fable parity

The path to a portable COO is **not** “give every model the Claude binary.” It is:

```text
same Executive responsibility semantics
+ same bounded company grounding
+ same role/practice method identity
+ same required capability profile
+ backend-specific effective realization and attestation
+ same result/review/repair/continuation owners
```

Native strengths may remain additional observed capabilities when policy allows them. A backend lacking required browser, rich continuation, helper ceiling or tool isolation simply does not qualify for that COO profile yet.

Only after this conformance layer exists is it meaningful to compare Opus/Fable against GLM, Grok, Qwen, Sol/Astra, MiniMax or other models without confounding model intelligence with a radically different working environment.

## 8. Chunk 3B decision and stop boundary

### Accepted planning decision

- Preserve `WorkerExecutionAdapter/v1`.
- Preserve `OperatorHarnessAdapter/v1`.
- Do not create one universal runtime.
- Generalize the **sealed capability-policy + supervisor attestation composition**, not the sealed provider wire.
- Add an Attempt-bound context/method materialization receipt through existing owners.
- Require backend-specific effective-environment observation; no configured/advertised capability is accepted as proof merely because it is named.
- Keep Claude native rich implementation gated on a no-work preflight; keep OpenCode and DSH as separate challenger backends until conformance is proven.

### Proof ceiling

This is source-backed architecture planning. No worker/provider canary, DSH/OpenCode execution, real Claude/GLM/MiniMax/Qwen/Grok call, credential access, capability mutation, installed runtime change or production route activation occurred. Open-PR reported tests were not reproduced here.

### Exact next action — Chunk 4

Define the controlled **behavioral qualification and generic-engine selection protocol** after conformance, without modifying routing:

1. same model across compatible harnesses to isolate harness contribution;
2. same operating profile across models to isolate model contribution;
3. task suites for coding, research, adversarial review and sustained COO operation;
4. accepted-result cost including review/repair, context overhead, provider usage and human interventions;
5. continuity/recovery and effect-uncertainty tests, not just answer quality;
6. qualification thresholds for OpenCode vs DSH generic lanes and for promoting a model to a portable COO profile;
7. only then define migration waves and route changes.

The benchmark must use real accepted-result consumers and exact source/capability generations. It may not reward a harness for hidden retries, leaked ambient tools, skipped independent review or provider fallback.