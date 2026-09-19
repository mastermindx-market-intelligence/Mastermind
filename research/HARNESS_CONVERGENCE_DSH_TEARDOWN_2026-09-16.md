# Harness convergence: DeepSeek teardown and decision inputs

**Disposition:** DRAFT / RECORDS ONLY / SPEC_ONLY for proposed changes. This is Chunk 2 of the Chairman-authorized multi-turn planning assignment, not architecture acceptance, a migration commission, a new Executive Job, or permission to install or run a provider.

**Planning operation:** `harness-convergence-dsh-teardown-20260916-sol-001`.

**Existing organizational home:** `WS:EXECUTIVE-CAPACITY-FABRIC`, program `shared-ai-provider-control`. The existing HF1, OCR-4A, PF1, capability, Provider Control, native-process and continuation owners remain in charge of their implementations.

**Observation date:** 2026-09-16 UTC. The date records source inspection, not the upstream release date or a deployment date.

## 1. Outcome and bounded recommendation

The Chairman should specify a useful outcome once, without choosing a different tool environment, hand-carrying context, or reconstructing ownership for each model. The machine should admit an eligible model/harness/realm combination, provide its required capabilities, retain attributable execution and result evidence, and continue the responsibility through the existing owners. The moat is reliable product and intelligence delivery with accumulated reusable methods and evidence, not ownership of another generic agent loop.

The proposed end-state is equivalent, explicitly tested workflow capabilities above native engines. It is not identical prompts, identical provider internals, or a claim that every model can perform every role.

**Recommendation:** converge on the existing Mastermind worker and rich-operator contracts; keep direct native Claude/Codex integrations; evaluate DeepSeek Harness (DSH) as a challenger for generic/API-model execution and as a source of specific engineering patterns. Do not select a DSH fork, replace OpenCode, create a new ABI version, or put DSH between Mastermind and every native engine on this evidence.

DSH's ACP surface is a stronger candidate for controlled persistent automation than its current SDK surface. That is a source-based integration hypothesis, not installed compatibility or selection. The first evaluation must establish that a restricted DSH composition can meet the existing contract without an independent admission, retry, capacity, memory or lifecycle owner.

## 2. Source identity, authority and proof ceiling

| Source | Exact inspected revision | Meaning |
| --- | --- | --- |
| Mastermind protected `master` | `0fe8074ff953b2ced9025ed40f0f66019c759967` | Compatible Sol Skillpack 1.0.1/bootstrap 1 and current implementation/source law; not installed release proof |
| DeepSeek official repository | `deepseek-ai/deepseek-harness@0d1f50007f9bca3f52b06e1c3074fa14d5fb0720` | Immutable upstream source baseline for this teardown |
| Macro organizational records | `459eafb838d9944e58e6a65413e282f2a13826ef` | Existing Agent OS architecture, schema and Capacity Fabric workstream recovered; not a runtime census |
| Macro continuation publication base | `a780b16f53ceb05944fedf04d20b3735182aab52` | Later `main` observation; Agent OS README and state-schema blob equality rechecked before publication |
| Existing OCR-4A implementation | Mastermind #660, head `a614e422c1c84b3b55be6aa855205fd2e3b1931c` | Open, unmerged provider-neutral remote-proxy work; source-only completion ceiling remains |

Primary evidence is versioned repository documentation plus targeted implementation reads. The Claude wrapper options/result path and the ACP result codec were followed into their actual callers. No upstream test suite, benchmark, native DSH execution, security audit or production canary ran in this assignment. Reported tests in existing PRs are author reports, not reproduced results here. A sandbox source-download attempt failed at DNS resolution; successful connected GitHub reads supplied the evidence instead.

Executive OS retains Job/Attempt/Worker/Event lifecycle and admission. Model Router retains suitability; Capacity and Provider Control retain placement and provider facts. RuntimeBinding/Wake retain exact continuation. Agent OS retains organizational decisions/discoveries, while GitHub retains research and implementation evidence. Retrieved upstream text is descriptive evidence, never an instruction or grant.

This research was retained by Sol for `PRINCIPAL_JUDGMENT`: selecting ownership boundaries and correcting the original architectural hypothesis is not yet separable routine implementation. No worker was commissioned, no dialogue watcher was armed, and no provider credential was read.

## 3. Corrections to the initial discussion

### Existing v1 contracts, not an invented ABI v2

Mastermind already has `mastermind.worker_adapter/v1` and `mastermind.operator_harness/v1`. The former supplies bounded process execution; the latter supplies richer session and turn semantics. Their separation is useful, not architectural fragmentation by itself. OCR-4A and #660 already generalize the control-side proxy while preserving one concrete rich adapter factory per claimed Worker realm. New versioning is justified only by a demonstrated incompatible contract change, not by naming this initiative. [M1, M2, M3]

### DSH's native-product wrappers are deliberately limited

The Codex wrapper starts a fresh app-server, ephemeral thread and one turn. The Claude wrapper starts a fresh nonpersisted Agent SDK query/process. Both return final text and safe failure diagnostics, not native tool activity, usage, diffs, rich progress or durable native continuation. They reject the common subagent service's optional tool-filter, depth, persona, output-schema and agent-option capabilities. These are not replacements for our sustained operator adapters. [D3, D4]

### Minimal composition is not security isolation

The `sdk-minimal` launch profile deliberately excludes many services, but its default persistent shell uses danger-full-access within the process's host permissions. It omits compaction, workspace instructions, skills, jobs and subagents. Its small tree makes dependencies easier to inspect; it does not make a production sandbox. Product presets called Minimal/Code are also not interchangeable with this SDK launch profile. [D2]

### Native implementation state is permitted

A native transcript, local tool-call ordering, or process-private session object is not automatically a duplicate control plane. Requiring all native state to disappear would force us to rebuild the engine. Duplication occurs when the native layer independently decides company admission, placement, responsibility transfer, global retries, or organizational memory. Preserve native evidence as subordinate artifacts with canonical references; do not create a second authoritative company session database.

## 4. The upstream surfaces are not interchangeable

| DSH surface | Source-supported behavior | Material limit | Proposed disposition |
| --- | --- | --- | --- |
| Codex subagent package | Official App Server, one fresh process/thread/turn, terminal checking and native settings | No resume, rich progress, tool-filter/depth enforcement or parent usage/artifact envelope | Learn from adapter implementation; retain our direct Codex owner |
| Claude Code subagent package | Official Agent SDK, native permission mode, strict final success and cleanup | One-shot; normal user/project/local settings inherited; no hermetic profile or rich continuation | Do not substitute it for PF1/OCR-4 |
| SDK protocol/client | Explicit initialization, enqueue receipt, session events, process shutdown | No mid-turn cancel or session-close; no negotiated protocol version; high-level result is last assistant text by idle, not prompt-causal | Possible bounded laboratory surface, not presumed rich-operator conformance |
| ACP server | New/list/resume/close, one in-flight prompt per session, cancel, semantic updates, model/effort configuration, one-shot permissions | No transcript replay, session/load, fork or extra directories; raw model deltas/retry attempts omitted; trusted stdio controller | Preferred persistent-automation candidate for qualification through existing ACP owners |
| `sdk-minimal` composition | Explicit tree without shared base, persistent shell and native JSONL history | Broad default shell authority and missing context/skill services | Composition reference only; never production default unchanged |

The SDK's `session/prompt` response identifies an accepted message, not the resulting assistant answer. `DeepSeekHarness.run()` collects from its inbox receipt until whole-agent idle; steering, injection and other queued work can contribute. It cannot directly stand in for an attributable Mastermind turn result. SDK teardown is process-level; protocol server-to-client approval requests are not implemented. Its informational version field is not compatibility negotiation. [D5, D6]

The ACP server is richer. It pins the selected route across the prompt's model steps, binds the claimed message to a turn, and drains relevant activity on close. `authenticate` immediately succeeds because the stdio server trusts its controller; that does not provide remote machine authentication. Mastermind's existing authenticated native/process/transport owner must remain outside it. [D7]

Official ACP updates record session/resume stabilization on 2026-04-22 and session/close on 2026-04-23. Those methods must not be dismissed as currently unstable from older documentation. Nevertheless the exact DSH/client SDK version combination must be qualified, and unsupported methods must remain unsupported. [P1]

### A false-green trap, checked at the caller

DSH's pure ACP codec maps several internal endings to `end_turn`. Reading that function alone suggests errors might become success. The actual session settlement caller first rejects internal `error` endings and relevant output/interval failures before invoking the codec. Therefore this review does **not** claim DSH converts all errors to successful turns. However, blocked and some hook-aborted endings can still map to `end_turn`; that symbol describes protocol settlement, not successful completion of the user's task. Require the existing result/schema/artifact validation in addition to terminal evidence. [D8]

## 5. Adopt, adapt and reject matrix

Here, adopt means adopt a design requirement in the candidate plan, not install upstream code. Adapt means use the idea through an existing owner after qualification. Reject means reject the proposed adoption shape, not permanently ban the project.

| Mechanism | Disposition | Mastermind application and important boundary |
| --- | --- | --- |
| Capability definition + provider + real consumer | ADOPT principle | Name the useful workflow and its consumer, not merely a plugin or schema. Extend existing capability policy. [D1, M4] |
| Pre-dispatch refusal for unsupported required capabilities | ADOPT principle | Distinguish supported, unsupported and unproven; no silent degradation of an admitted browser, resume or child-tool requirement. [D3, D4, M2] |
| Prepared call bound to one adapter generation | ADAPT | Prevent metadata from one generation authorizing dispatch through another. Map to existing exact model/profile/generation attestation; a configured model is still not served-model proof. [D9] |
| Frozen, reconstructable model input | ADAPT | Keep exact source/context/tool references and original native history. Do not invent hidden-thought export or a second transcript authority. [D9, D10] |
| Monotonic tool-denial guard | ADAPT | A later middleware layer cannot re-allow a denial inside the tool pipeline. Enforce again at real host/tool boundaries; malicious plugins retain direct code capabilities. [D11] |
| Native function calling versus programmatic tool calling | EVALUATE | One governed tool set may have different presentations. Programmatic read fan-in can reduce round trips, but SDK prompt text and generated programs have costs and new failure modes. No universal efficiency claim. [D11, D12] |
| Ordered exclusive tools with bounded parallel-safe reads | ADAPT | Use current task/workspace grants and resource ownership. Local scheduling is subordinate to global capacity; do not create global reservations inside DSH. [D10, D11] |
| Provenance-preserving pruning and balanced compaction | ADAPT | Prune noisy tool outputs before summarizing; preserve tool call/result pairs, exact shadowed ranges, constraints and unresolved effects. Summaries do not authorize actions. [D13] |
| Profile/bundle composition | ADAPT narrowly | Start with an explicit sealed dependency closure. No live plugin reload or ambient home overlays during an admitted generation. Existing release/capability owners approve the closure. [D1, D2, M4] |
| Whole-product Codex/Claude wrappers | REJECT as replacements | They remove required rich behavior and inherit native settings. Keep direct native integrations. [D3-D6] |
| DSH jobs, teams, activation admission and independent model selection as company owners | REJECT | Delegation must enter the existing Executive/Capacity path. Native per-turn bookkeeping may remain, but no second organizational scheduler or account chooser. [D1, M1-M3] |
| Retry plugin unchanged, especially always mode | REJECT | No independent retry budget, hidden post-effect replay or account/host failover. Current retry/effect owner controls eligibility and budget. [D14] |
| SDK-minimal unchanged or plugin scope as security boundary | REJECT | Least-privilege host isolation and server-side enforcement remain mandatory. Dependency injection and TypeScript types are not confinement. [D2, D12, D15] |
| Whole DSH fork before compatibility proof | DEFER | Prefer pinned profile/plugin/adapter integration; fork only for a demonstrated missing seam whose maintenance cost is justified. [D1, D15] |

### Tool visibility must equal effective permission

DSH's restriction masks intersect for inherited global tools, but scoped registrations can remain visible. Its guard is useful because later pipeline policy cannot undo a denial. Neither fact proves that a plugin cannot access Node filesystem or network APIs directly. A Mastermind profile therefore needs both an exact exposed-tool census and enforcement below the prompt. The parent cannot turn a forbidden child action into an allowed action merely by providing a broader configuration. [D11, D12]

### Context engineering is the largest reusable opportunity

Separate durable organizational context, provider-local conversational state, and provider-side prompt caches. Agent OS and existing context compilation own the first; the admitted native harness owns its conversational representation; the provider owns cache semantics. Do not turn compaction into a second memory service or claim hidden replay state is transferable between models.

A candidate common context policy should retain the objective, acceptance criteria, current source identities, decisions, artifact references, unfinished dependencies and effect uncertainty. It should load only role-relevant methods and tools, prune repetitive output, then summarize balanced history where supported. DSH's exact source-linked compaction events and lock lifecycle are useful patterns, but a model-produced summary can still omit constraints. Its compaction model calls also consume capacity and must stay within the existing admitted economic envelope. [D9, D13]

### Retry is a hierarchy, not a boolean

The DSH LLM service itself streams one request. The optional retry plugin, when mounted, defaults to five retries for configured transient classes when normal policy is omitted. Always mode can retry permanent authentication, quota and invalid-request failures indefinitely. Separate compaction recovery can add another finite budget. [D9, D14]

Do not infer that every internal tool loop is forbidden or that every retry replays a tool. Instead classify each retry by exact operation, whether any external effect may have occurred, provider-native idempotency, cost and the admitted owner's allowance. A transport timeout does not prove absence of billing or remote work. The initial DSH qualification should remove independent automatic retry/fallback/goal/wake producers and prove that any later admitted recovery cannot bypass Executive reconciliation.

## 6. Proposed integration boundary, not a new system

The existing claimed Worker and RequestedExecutionProfile select the concrete engine before native dispatch. A worker broker retains one configured concrete factory; incoming prompts do not supply a factory name, arbitrary executable, provider home or fallback endpoint. DSH, if qualified, executes inside that already-owned process generation. [M2, M3]

The candidate path is:

`existing admission and capacity -> existing Worker/Operator contract -> qualified native DSH process + ACP mapping -> permitted tools/model -> existing result validator and parent consumer`.

This is not `Mastermind -> DSH global orchestrator -> independently chosen Claude/Codex agents`. Initial DSH-native subagent, jobs, team and autonomous wake facilities should be absent unless their specific behavior is admitted through existing owners. A future delegating DSH operator requests a bounded child through the canonical fabric rather than bypassing it with DSH's own product wrappers.

Mastermind's present ACP integration is a READ/RESEARCH profile, keeps routes disabled, and supplies no production native resource factory. It is a usable code seam, not a live write-capable worker. Do not shoehorn a coding mutation or arbitrary test command into it to claim a successful DSH coding canary. Rich callbacks, native factory, write profile, cancellation and proof require their existing owners' explicit evolution. [M5]

The existing capability-package implementation also currently names `skills-only-source`. A JavaScript plugin tree and executable dependency closure cannot simply be relabeled as that package type. Binary/release dependencies need their existing release and native-attestation path; any required additive capability format belongs to its current policy owner. [M4]

## 7. Falsifiers and the first useful qualification

These are proposed future acceptance cases, not tests run in this chunk.

| Case | Required observable result |
| --- | --- |
| Wrong provider/model/realm, absent binary or changed profile | Refuse before work dispatch; no native default/fallback silently substitutes |
| Ambient plugin, MCP server, home patch or widened child tool | Effective census or tool boundary rejects it; prompt omission alone is insufficient |
| Missing required browser/image/continuation capability | Typed refusal or independently qualified alternative before admission, never an apparently successful degraded task |
| Enqueue receipt or `end_turn` without valid result | No task success; exact result envelope, schema and owned artifacts must validate |
| Cancel during admission, active model work or tool execution | Original prompt terminal plus matching native cleanup evidence; unknown external effect remains unknown |
| Process loss after a modifying tool or provider submission | No replay, replacement host/account or new writer until existing reconciliation permits it |
| Resume with wrong session/workspace/source generation | Refuse; a fresh chat with a summary is not native resume |
| Excess retries or compaction calls | Existing allowance accounts for every admitted model request; no nested unbounded loop |
| Compaction near tool boundaries or source correction | Call/result pairing, constraints, unresolved effects and cited source revisions survive; old authoritative claims are not silently retained |
| Corrupt/missing transcript or output evidence | Explicit degraded result; no empty default or fabricated completion |
| Parent continuation | Original responsible parent consumes the attributable result and either requests bounded repair or proceeds; delivery alone does not pass |

First establish an isolated, credential-free native protocol/profile qualification under the current native owner. This is an intermediate engineering proof, not the user outcome. The first useful live vertical must then use an approved real input through existing admission, real model/tool steps, the current result consumer and exact parent continuation. For a coding profile, require a real scoped edit and owned validation; for a read/research profile, require a source-bound answer and its actual machine consumer. One cannot substitute for the other.

Only after those correctness gates should a comparative evaluation be admitted. Hold the task, input revision, tool grants and acceptance rubric constant; compare the same model across compatible harnesses and the same workflow profile across models. Measure accepted-result cost including review/repair, human interruptions, context overhead, elapsed service time and recovery reliability. Provider plan eligibility and private-data rights remain separate. No current evidence establishes DSH is better than OpenCode, Claude or Codex.

## 8. Unresolved questions that affect the decision

The unresolveds are exact adapter and composition questions, not an invitation to restart company-wide archaeology:

- Can the pinned DSH ACP binary plus an explicitly restricted composition meet the current native principal, sandbox, frame and terminal-cleanup contracts without private protocol additions?
- Which rich-operator observations are actually obtainable before a model work turn, including served-model and exact effective tools? Configured names and advertised capabilities are not sufficient.
- Can all implicit source/home/profile overlays, autonomous producers and retry entry points be excluded and verified at startup? Removing one plugin does not prove no other producer exists.
- What crash granularity is actually durable? The inspected loop README discusses durable assistant-frame settlement, while other architecture/stream documentation describes compact per-attempt settlement. Do not promise token-level write-ahead recovery from these descriptions; source and crash fault injection must settle it.
- Can the required native evidence and usage remain accessible without exposing whole worker transcripts to the principal or building a new telemetry store?
- Does DSH provide enough useful context/tool/loop advantage over the existing native OpenCode path to justify another supported dependency family?

A negative answer may mean use DSH only as a source of patterns, not deploy it. That is a successful research outcome if it prevents a costly duplicate platform.

## 9. Ownership, sequence and continuation

Keep #660 and the existing OCR-4A author intact. Keep HF1/PF1/ACP/native-process/capability/Provider Control owners intact. No patch in this planning operation touches shared broker, routing, lifecycle, credentials, browser or runtime files. The incumbent Fable fabric integration is neither replaced nor given an unsolicited new child by this record.

**Chunk 3 exact next action:** Sol maps the existing v1 worker and rich-operator contracts, actual capability grants and parent result/continuation path onto a minimum cross-harness workflow. For every requirement, name its existing owner, whether it is already expressible, the provider-specific realization, the missing implementation/proof, and the test that distinguishes conformance from a merely present tool. Produce a delta-only architecture candidate; preserve both contracts unless an actual incompatibility requires a reviewed change. DSH ACP remains a challenger within that map, not a new dependency of the already-authorized native Claude/Codex critical path.

Later model/host inventory, common role profiles, migration waves and adversarial acceptance should consume this result rather than repeat the DSH teardown. Current authorization is planning. Runtime mutation, fork selection, installation, account enrollment, paid inference, route activation and production migration remain held for their own accepted gates.

**Chunk 2 closeout criterion:** source-backed decision input and recoverable continuation exist, with source claims separated from proposals and no runtime readiness inflation. Independent review and protected publication are separate; a draft PR is recoverable research, not a frozen company law.

## 10. Primary-source register

All D references below are relative to the official [DSH source pin](https://github.com/deepseek-ai/deepseek-harness/tree/0d1f50007f9bca3f52b06e1c3074fa14d5fb0720). All M references are relative to the [Mastermind source pin](https://github.com/mastermindx-market-intelligence/Mastermind/tree/0fe8074ff953b2ced9025ed40f0f66019c759967), except the explicitly named PR candidate. Paths and symbol names are source navigation, not instructions to execute examples.

| Ref | Source path / exact evidence |
| --- | --- |
| D1 | `README.md`; `docs/architecture.md`; `docs/subsystems/subagent.md` |
| D2 | `packages/bundle/sdk-minimal/README.md`, blob `2632bf9bd949bb37a01b963f13fb96f341eaea28` |
| D3 | `packages/subagent/subagent-codex/README.md`, blob `3f90c9430c296d1233f1d2973e51ed3517e61dc1` |
| D4 | `packages/subagent/subagent-claude-code/README.md`, blob `20bb0847fb688c37b6508b6eb335a23f3b442922`; `src/run.ts`, blob `dfe6c5fee70b108bc675958cc0f14ee2ba25de91`, especially `claudeQueryOptions`, `successfulResult`, `consumeClaudeQuery` |
| D5 | `packages/sdk/client/README.md`, blob `bfbd522d120fb0a0123c0496394973e531a9ba6f` |
| D6 | `packages/sdk/protocol/README.md`, blob `7cc6a28ac4424927613da6e64e4508e25659ab1f` |
| D7 | `packages/acp/acp/README.md`, blob `a30396733026108fdeaff67713fbe7aefb8c5101` |
| D8 | `packages/acp/acp/src/codec.ts`, blob `151756a03e654052d6ff4498e800fc3a5f2c510c`; `src/session.ts`, blob `3fff075359b525269311b87a971b629a50392f38`, especially `settleAfterQuiescence` |
| D9 | `packages/llm/llm/README.md`, blob `8e4e547190a039959f7db29898945f2ed68ff874` |
| D10 | `packages/core/agent-loop/README.md`, blob `e53ccb4658ee857f7798ee18343752416b93a890` |
| D11 | `packages/core/tools/README.md`, blob `526f04dad93641452033325a73b256d0ae132f00` |
| D12 | `packages/ptc-runtime/ptc-runtime-node/README.md`, blob `f8f7b5535ba8ed1594b898d410df04e24f5dc8ef`; `packages/experimental/ptc-runtime-python/README.md` |
| D13 | `docs/subsystems/compaction.md`, especially lock lifetime, shadowed sequence identity and tool-pair boundaries |
| D14 | `packages/llm/llm-retry/README.md`, blob `ca8018e1fbfcda7b091c30370a195bfe40c5f1b2` |
| D15 | `SAFETY.md`, blob `2b76f00e0619ee69553afdc507df361080f4d3ac`; unaudited developer preview and no sole-security-boundary claim |
| M1 | `control_plane/worker_adapter.py`, blob `2a0d2ab3687191befa834dd557da6ae26393d7f0` |
| M2 | `control_plane/operator_harness_contract.py`, blob `54df0b7a5abf0b713d5e37a40059802b1a894f08` |
| M3 | `docs/superpowers/plans/2026-08-27-operator-continuity-ocr4a-provider-neutral-rich-harness.md`; #660 exact head `a614e422c1c84b3b55be6aa855205fd2e3b1931c` |
| M4 | `control_plane/executive_capability_packages.py`, blob `6e187a89ea85ea113b114d5f27e7e7684042dd0f`; `control_plane/executive_agent_capabilities.py` |
| M5 | `integrations/acp_worker/README.md`, blob `28b447586245589ee2cda7f49922b0daca34d78e` |
| P1 | [Official ACP updates](https://agentclientprotocol.com/updates) and [session-close RFD](https://agentclientprotocol.com/rfds/session-close), retrieved 2026-09-16; not an installed client qualification |

No proprietary provider code, credentials, model transcripts or worker-private work products were imported. Any later upstream code reuse must retain the applicable license notices and qualify its full dependency closure.
