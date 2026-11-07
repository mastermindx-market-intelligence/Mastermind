# Hermes as a persistent Mastermind teammate
## Research findings, architecture decisions, and implementation masterplan

**Research date:** 6 November 2026  
**Status:** Research proposal and implementation plan; no runtime deployment or product acceptance is claimed.  
**Commission:** Make the existing Hermes harness a continuously useful, learning teammate integrated with Executive OS, Agent OS, Subagent Fabric, Mastermind OS, the VPS, repositories, and host fleet.

## 1. Recommended direction

Keep Hermes as the primary conversational harness and evolve the Mastermind integration around its existing extension points. Combine its memory-provider interface, session machinery, skills mechanisms, and tool ecosystem with Mastermind's existing sources of authority. Reuse selected OpenClaw memory mechanisms, OpenMausBot interaction patterns, and, where justified by measured tasks, specialist executors such as the OpenHands SDK.

The target is a persistent logical teammate whose useful knowledge, commitments, identity, and evidence survive changes of conversation, model, process, and computer. Achieving that requires several distinct capabilities:

1. Memory that retrieves the right information, preserves source and scope, and can be corrected.
2. Durable work that continues through existing admission, runtime, placement, and return paths.
3. Learning that produces tested improvements to skills and procedures.
4. Tools and computer access that are deeply capable within the authority of each task.
5. A coherent product where the Chairman can see work, steer it, inspect memory, and take control.
6. Evidence that these capabilities improve accepted outcomes over repeated use.

More stored notes alone do not establish improvement. Continuous base-model weight training is also not a prerequisite. The first implementation should improve contextual knowledge, retrieval, procedures, and execution reliability. Any later model training would be a separate, evaluated decision.

This is an extension of the existing Meta-CEO/open-harness and Chairman Control Room program. It preserves its product journeys, source owners, and acceptance work rather than creating a competing program. The governing research parents are the 24 October open-harness convergence masterplan and the 30 October Meta-CEO autonomy masterplan. [I1][I2]

### What can make Mastermind better

The strongest differentiator is an integrated operating environment: remembered facts tied to current sources; useful skills tied to measured outcomes; work tied to admitted responsibilities; compute chosen from the available fleet; and every consequential result returned to its original parent.

Treat the following as engineering objectives, not superiority claims:

- More granular role, project, and task boundaries for memory and credentials.
- Portable continuity across qualified engines and hosts.
- Explicit correction, supersession, retention, and forgetting controls.
- Evidence-based skill improvement with rollback.
- Real browser and computer handoff, with effect reconciliation after interruptions.
- A single view of the organization and its work, backed by canonical records.
- Low cost during quiet periods, with computation concentrated on meaningful events.

## 2. What exists, and what still needs proof

### 2.1 Source baseline

The protected Mastermind source baseline inspected for this report is:

**mastermindx-market-intelligence/Mastermind at b0a280be474ae67e7681f68dc0dfe3af2aea1626.**

The skill index and governing laws were read at that same revision. The existing integration selects:

**NousResearch/hermes-agent at 1c0cd667746d3395fe9e1b6c74f8f85952486f18.**

This is the selected integration source pin, not a claim that every fleet host runs the same revision. The separate #2147 source record describes an M2 installation at local revision 2bd378ed1b8d with a read-only capacity connection; it does not claim enrolled worker execution. Revalidate each host's actual version and profile before qualification. [I15]

Do not make an upstream upgrade a prerequisite for the first useful slice. This selected Hermes revision already contains the MemoryProvider seam, the v2 pre-compression checkpoint contract, encrypted vault machinery, and skill guards. These are available source mechanisms, not proof that Mastermind has enrolled and qualified them in production. [H1][H2][H3][H4]

### 2.2 Existing integration boundaries

| Surface | Inspected source establishes | Implementation implication |
|---|---|---|
| Native Hermes backend | GatewayRunner owns native sessions, tickets, admission bindings, and original results; the existing role supervisor owns the process. | Extend this backend; do not add a parallel session service. |
| Executive delegation | The host freezes exact job, attempt, step, plan digest, and selected-child binding. The model cannot choose a different root. | Keep delegation behind the existing closed mmx_delegate interface. |
| Native tools | Tool registration and manifests use exact allowlists; built-in Hermes delegation and skills are disabled in the inspected extension. | Integrate capabilities explicitly; turning on every upstream tool is not a valid rollout. |
| Steward | Six grounded read tools expose responsibilities, attention, runtime, blockers, and surfaces. | Use this read seam for relevant company context; do not silently turn it into a writer. |
| Model mapping | Provider mapping consumes the model catalog and remains subordinate to routing and Capacity. Generic Hermes fallback is deliberately not rendered. | Route changes must respect the existing effect and quota rules. |
| Secretary qualification | The inspected qualification profiles enable clarify only; browser, computer, terminal, skill and cron surfaces remain disarmed there. | Installed upstream code is not proof of qualified live capability. |
| Timers | The inspected unported inventory says Wake has no scheduler; Hermes cron remains the timer owner until a supported canonical binding exists. | Event delivery and timer ownership must be handled separately. |

Sources: [I3][I4][I5][I6][I7][I8][I9].

PR #2120 was observed merged, with merge commit 28a894186eb56654ab4e833eb11a183d2eed46ae. PR #2134 was observed open at head ae40096acf4f911babb2a9b51e5c7e48c3d29a2e; its body referred to an older revision, so the body is not evidence for the current head's checks. Neither source status establishes end-to-end production acceptance. The later #2134 snapshot explicitly retains live enrollment, original-parent result consumption, and automatic continuation through the dispatcher task-to-admission/request join as outstanding proof. It also points to an existing independent Hermes worker adapter carrier, #2147, observed open at de68fadba4a3579b9d487a397d056f34a95657e6; implementation must reconcile that carrier before creating overlapping worker-adapter work. [I10][I11][I15]

Keep the two ingress scopes distinct: mmx_delegate addresses a frozen Executive-selected child; #2147's mmx_fabric_worker is a separately granted native attended-worker surface using the existing Fabric facade. Its source requires real host/session grants, an enrolled execution channel, and original-effect admission. A read-only capacity connection cannot be promoted to submit authority by changing a tool name. [I15]

### 2.3 Read-only capability observations

A call to the exposed Executive state surface returned backend_unavailable. This is evidence about that invocation and surface, not a diagnosis of the whole fleet.

The exposed Fabric capability surface reported an available adapter and bounded pre-task capacity rejection continuity, while reporting native_parent_wake=false, background_execution=false, and process-generation controller tracking without restart persistence. Worker admission and start were not exercised. These observations identify a live proof gap; they do not establish that every internal deployment has the same limitations.

The immediate implementation path can therefore begin with source work and focused qualification. Live enrollment must first reconcile the existing carrier and runtime bindings. An old author or chat is not an approval dependency.

## 3. What to learn from commercial teammates

These are documented product mechanisms, not claims about private implementations or model training. Public evidence does not establish how the proprietary systems train their models internally.

| Product | Documented mechanism worth learning from | Mastermind adaptation |
|---|---|---|
| ChatGPT Dot | Persistent responsibility, a cloud computer, connected apps, memory, proactive research, schedules, and visible activity. | Preserve one teammate across conversations; show ongoing responsibilities and results in Mastermind OS. [P1] |
| Grok Bot | Named bots with role and conversation continuity; skills, routines, event triggers, and secure credential entry. | Separate role identities while sharing explicitly published company knowledge. Turn successful work into tested reusable routines. [P2][P3] |
| Claude Duet | A continuing main thread, topic channels sharing memory, a cloud computer, connectors, proactive briefs, and a quieter task view. | Maintain continuity across surfaces and reserve the main conversation for useful results and decisions. [P5] |
| Manus | File-backed context, a current task frontier, stable prompt structure, and retained failure evidence. | Keep long-term artifacts outside the prompt and refresh the active objective without erasing mistakes. [P7] |

Grok's documented vault keeps secret values from the model, but personal vault items are account-wide across personal bots. Mastermind should make credential scope explicit per role and task. This is a concrete improvement target rather than an inferred weakness in an unseen implementation. [P4]

Dot and Duet documentation distinguish disconnecting an app from removing information already remembered. Mastermind should expose those operations separately: stop access, stop future ingestion, stop retrieval, and remove permitted derived copies. The UI must explain any retained audit history. [P1][P5]

Duet's documented preview also limits browser viewing and takeover. Mastermind's fleet integration should include visible computer sessions and a reliable handoff, because those are central to the requested product. [P5]

The common product lesson is that continuity comes from an assembled system: durable identity, useful context, a computer, connected tools, recurring work, and feedback. We should reproduce the useful workflow with original implementation and lawful sources. Similar features in an open repository do not prove it copied a paid product's private engine.

### 3.1 What the memory architecture research adds

Anthropic's 6 November article distinguishes retained agent knowledge from weight training and compaction. It describes transcripts, notes, higher-level representations, and injected context, with consolidation checking notes against earlier evidence. Its example demonstrates that correcting a bad memory can alter later behavior; it is not a general performance guarantee. [P8]

OpenAI's memory article describes background synthesis to address stale, incomplete, or irrelevant remembered context. Its evaluation separates carrying useful context forward, following preferences, and staying current over time. These are useful dimensions for Mastermind's own evaluation, rather than evidence that our implementation already matches the product. [P9]

Claude Managed Agents' Dreams API produces a separate reorganized memory store while preserving its input; deterministic edits and synthesis are different operations. Take the snapshot, comparison, and explicit-promotion pattern. This documentation does not establish that Duet uses that API internally. [P10]

Manus's engineering account supports stable prompt prefixes, durable file references, refreshing the current objective, and keeping failure evidence available. Some implementation details, such as token-level action masking, require provider support. For Mastermind, preserve stable tool definitions where practical while enforcing actual permissions at the receiving owner. [P7]

## 4. Open-source reuse decisions

### 4.1 Pinned donor inventory

| Project and inspected revision | License observation | Decision |
|---|---|---|
| Hermes: selected 1c0cd667746d3395fe9e1b6c74f8f85952486f18; comparison snapshot 6b21d0564de0492e2ebd0d8f63fca86c03b5c892 | MIT at the inspected revisions. | Primary harness. Implement adapters at existing seams; take later changes only for a named need. |
| OpenClaw: 39d85007e9ba04ca502bf06da2ed51d35cbad491 | MIT. | Reuse or adapt provenance, consolidation eligibility, source rehydration, and evaluation scenarios. |
| OpenMausBot: 164002b72b54127c4b8fa6d7bb017463b6b02ab2 | Apache-2.0 core; separately licensed enterprise subtree; branding excluded from the general reuse proposition. | Reuse selected core UI/contract ideas or code with attribution. Exclude enterprise code and branding from the donor set. |
| NanoClaw: b6266ec9667ec3c1478a651987089b28714a729a | MIT. | Reference for small, isolated worker execution. Do not import its application runtime wholesale. |
| OpenHands software-agent-sdk: 039e5926d9655fd9b69b8c85604ec28ef17699bb | MIT. | Optional specialist coding executor behind Fabric if it wins a specific workload. |
| OpenManus: 3309bf4e416fb1c74b008f3e86494439a31bad53 | MIT. | Secondary reference for agent/browser composition; no first-phase dependency. |

Sources and exact license files: [H5][O1][O5][O6][O7][O8][O9].

“maus” is interpreted here as milind-soni/OpenMausBot, the matching current open teammate project. OpenManus is assessed separately, so the plan covers both plausible intended references.

A public GitHub repository is not a blanket license for every file, dependency, brand, dataset, model, or connected service. Preserve the applicable license and notices when copying permitted code, record the upstream revision and modified files, and inspect transitive dependencies. OpenMausBot's enterprise license expressly limits production and redistribution without separate rights. No such code is required by this plan. [O6]

### 4.2 Concrete mechanisms to take

**Hermes: use the existing seams.** Its external memory-provider interface supports retrieval and turn/session lifecycle integration. That external provider coexists with built-in memory rather than automatically replacing it. Define the owner of each native note and prevent a second uncontrolled publisher of shared company facts. [H1]

Its compression implementation and tests provide a useful fail-closed checkpoint pattern. API v2 is a prose-memory boundary, not an execution ledger: tool receipts and unresolved effects must remain in their native canonical records. Required checkpoint mode also cannot be assumed to cover a separately compacting native engine. [H2][H6]

The selected vault implementation supplies model-blind handles and encrypted local storage. The inspected file backend places its key and encrypted payload under the same profile home. That protects stored bytes from some exposure paths, but does not isolate secrets from a compromised process with access to both. Host-level isolation and qualified credential backends remain necessary. [H3]

**OpenClaw: use provenance before consolidation.** Adapt its entry origins, deterministic eligibility checks, and re-reading of a source before promotion. Exclude recalled memories from being counted as new independent evidence. Keep time, source, scope, and supersession visible. Its documentation acknowledges provenance coverage gaps; these mechanisms do not make prompt injection impossible. [O1][O2][O3]

Candidate files include extensions/memory-core/src/memory-entry-origins.ts, dreaming-consolidation-candidates.ts, and short-term-promotion-rehydrate.ts. These are not independent drop-in libraries: isolate the useful behavior, retain attribution, and write focused adapter tests. Mastermind should learn from verified worker outcomes even where a donor excludes subagent material, because our canonical receipts establish a stronger evidence path. [O2]

**OpenMausBot: take control and transparency.** Its memory design includes bounded overview notes, topic files, a budget display, revision-aware edits, journal/undo, and scope controls. Adapt those product mechanisms to Mastermind's owners. Its own documented crash and journal limits mean that its local journal should not become Mastermind's canonical evidence store. Its memory-off setting also illustrates why policy must be enforced at the receiving owner, not only at the UI toggle. [O4]

Its typed provider contracts and distinction between a turn that never started and one with uncertain execution are useful design references. Map them into the existing Capacity/runtime contracts rather than importing a new failover waterfall or runtime database. [O5]

**OpenHands: keep it an executor.** The SDK provides agent conversations, tools, workspaces, and an Agent Server; its repository documentation separates those responsibilities from application-level automation. If selected, package a bounded coding job under Fabric with the same evidence, cancellation, and return contract as other workers. No second scheduling system is needed. [O8]

**NanoClaw and OpenManus: reserve for gaps.** Study actual implementation and security boundaries, not a draft architecture document as proof of shipped behavior. Introduce a component only after identifying the task it serves better than the existing stack. The initial release should not depend on running several complete teammate applications side by side. [O7][O9]

### 4.3 How to reuse code without inheriting a second platform

For Hermes, prefer its existing public extension points and the already maintained Mastermind integration. For a donor helper, first inspect its imports and license boundary, then either use a versioned package that fits the current owner or vendor the smallest coherent permitted module with its tests and notices. Keep TypeScript helpers in an existing TypeScript owner where appropriate and Python adapters in the Hermes integration; avoid adding a service solely to connect a copied helper.

Record the upstream revision, exact copied paths, local modifications, dependencies, and qualification result in the existing integration provenance/delta records. Recheck an upstream change when it addresses a named defect, security issue, or consumer need. A large automatic upstream merge is not the default improvement mechanism.

Use design reference and original implementation when extraction would require most of another application's runtime. That is especially relevant to memory UI and orchestration contracts. Direct reuse remains the first choice where the component actually fits; code volume alone is not a useful reuse metric.

An open adapter does not establish entitlement to a proprietary service. Every selected provider still uses its authorized account and existing Capacity/model eligibility.

### 4.4 Additional memory and tool components

| Candidate at inspected revision | Evidence and reuse boundary | Recommendation |
|---|---|---|
| Letta Code, 5473a6639bd3b76fef74e293f6eed9ed6c2e9ad3 | Apache-2.0. A reviewed helper constructs a bounded projected-memory snapshot for reflection. Current Letta repository documentation redirects development to Letta Code. | Consider the projection/reflection technique or a small qualified helper. Preserve Agent OS and the existing runtime as owners. [O10] |
| Graphiti, 747b480ec6b12ecb718f1e2bc588b20ee36ea9c2 | Apache-2.0 at this pin. Episodic/entity and temporal relationship machinery are relevant to historical relationship retrieval. | Optional derived index only after it beats a simple retrieval baseline on a defined failure set. [O11] |
| Mem0, f1791daa86d469249c9b002f62644d58a1eb96a0 | Apache-2.0 OSS. Current README distinguishes managed proprietary optimizations from OSS results and describes agent-confirmed facts receiving equal weight. | Optional extraction/retrieval component; do not import hosted benchmark claims or treat an assistant's claim as verified execution evidence. [O12] |
| Playwright, 530161aae0ba59643dbbfa3c1b8c929874cc18ec | Apache-2.0. | Use where it fits the existing browser owner; it is not a replacement for task or credential authority. [O13] |
| browser-use b49a68e4060acb226da8f784194fef301c53a6d7; Stagehand c91e16776c3fb9964bbb9df6b9fe65a8f077ae7d | MIT licenses verified; current execution/session implementations were not audited end to end in this research. | Optional future workers for a demonstrated gap; neither is a required first-release dependency. [O14] |

Do not combine several independent memory platforms simply to collect features. The next experiment should answer a specific question: for example, whether temporal graph retrieval resolves historical ownership questions that the existing index misses.

## 5. Architecture and ownership

### 5.1 One owner for each durable responsibility

| Concern | Owner retained | Hermes contribution |
|---|---|---|
| Company intent, admission, lifecycle, accepted outcomes | Executive OS | Conversational intake and action requests within an admitted binding |
| Company knowledge, decisions, discoveries, organizational continuity | Agent OS, with its existing Macro source/publication workflow | Scoped retrieval and evidence-linked candidate lessons |
| Code, skills, source reviews, CI, implementation evidence | GitHub repositories and existing delivery workflow | Research, authored changes, skill use, result explanations |
| Model eligibility and compute placement | Existing ModelRouter and Capacity/Subagent Fabric | Consume the selected route and assigned worker capabilities |
| Exact conversation/session and return continuity | Existing native SessionAuthority, RuntimeBinding, Dialogue/Wake paths | Conversation, resumable interaction, original result consumption |
| Host processes and interactive applications | Existing supervisors and admitted host adapters | Execute qualified tools inside the assigned boundary |
| Credentials | Existing credential authority and qualified vault backend | Opaque credential selection and request metadata |
| User experience | Mastermind OS | One coherent teammate experience backed by owner records |
| Notifications and discussion | Slack and other approved transports | Scoped updates with source links |

This is a responsibility map, not a proposal for nine new services. New adapter methods should live inside the current owner's implementation. A derived retrieval index is permissible if it is rebuildable and cannot become a competing source of truth.

### 5.2 Data and control flow

~~~mermaid
flowchart TD
    U["Chairman and Mastermind OS"] --> H["Hermes native conversation"]
    H --> E["Executive OS admission"]
    E --> F["Capacity and Subagent Fabric"]
    F --> W["Qualified fleet workers"]
    W --> R["Canonical results and original return"]
    R --> H
    H <--> A["Agent OS knowledge"]
    H --> G["GitHub source and skills"]
    W --> V["Scoped credentials and computer sessions"]
~~~

Slack, Office, API, and local UI entry points should converge on existing identity and intake records. Changing the entry point must not create a second job, actor identity, or memory namespace.

### 5.3 Cross-engine contract

Extend the current adapter envelope only where required. Every admitted turn or worker continuation must carry:

- The owner-issued actor, root/job, attempt, plan digest, step, and original return reference.
- The selected engine/model identity and qualified capability manifest.
- Source and memory references with scope and revision.
- Workspace/repository bindings and relevant preimages.
- Budget, cancellation, lease, and expiry data issued by existing owners.
- Any unresolved effect references and the last trustworthy checkpoint.
- The expected result/evidence contract.

The model may propose work; it may not rewrite these bindings. Validate the response engine identity and capability support, rather than assuming every engine implements tools, vision, structured results, cancellation, and compaction identically.

Portability should mean a new qualified engine can reconstruct the remaining task from sources and receipts. It does not mean replaying an entire private transcript or assuming every provider shares identical hidden state.

## 6. Memory that remains useful over months

### 6.1 Separate memory classes

| Class | Contents | Durable owner and access rule |
|---|---|---|
| Personal preferences | Communication preferences, approved personal context | Existing private profile/session memory; never published to a shared repo by default |
| Role knowledge | Secretary or Meta-CEO operating context | Role-scoped records; common facts referenced through Agent OS |
| Company/project knowledge | Current decisions, constraints, discoveries, architecture | Agent OS and linked authoritative sources |
| Episodic work evidence | What ran, what changed, what was accepted | Executive/runtime/GitHub receipts; memory stores pointers and useful summaries |
| Procedural knowledge | How to perform and verify recurring work | Versioned skills in the existing skillpack/source workflow |
| Prospective commitments | Work owed, due dates, waiting conditions | Existing task, timer, Wake, and lifecycle owners; notes are not a queue |
| Secrets | Passwords, tokens, certificates, sensitive session material | Vault/credential owner only |

A small session-start note can orient Hermes, while retrieval brings in relevant detail. Avoid making one giant MEMORY.md the company's database. Do not share one mutable HERMES_HOME across different role principals.

### 6.2 Retrieval path

Implement the first useful slice as a read-only external MemoryProvider adapter:

1. Receive the already authenticated role and task scope from the host.
2. Retrieve a small amount of relevant context through the sanctioned Agent OS/read compiler and existing Steward surfaces.
3. Filter scope before ranking, and verify scope again when serving a result.
4. Return concise context with source reference, revision, date, and evidence class.
5. For facts that determine a consequential action, re-read the current owner record.
6. Record whether retrieval actually helped the accepted outcome.

Retrieved pages, tool output, and recalled notes are evidence, not executable authority. Preserve their trust labels and treat embedded instructions as untrusted content. Accepted source law and task grants enter through the existing authenticated source/admission path.

The initial index can be simple full-text and structured lookup. Add vector retrieval or graph relationships only when a measured failure set justifies them. If added, they are derived projections with deletion and reindexing support, not new owners.

The external provider and built-in Hermes memory need an explicit division. Native private notes can remain private. Shared facts must resolve to Agent OS. Cached excerpts must be labelled as derived and invalidated on source changes. Do not write the same organizational fact independently into two authoritative stores.

### 6.3 Proposed memory view contract

The following is a proposed view, not a deployed schema or a new storage system:

~~~yaml
memory_view:
  owner_ref: existing-owner-record
  subject_ref: stable-person-project-or-system-id
  scope: role-project-and-audience
  kind: preference-or-fact-or-decision-or-lesson
  source_ref: immutable-or-versioned-source
  source_revision: owner-version
  observed_at: timestamp
  valid_until: optional-refresh-boundary
  supersedes: optional-prior-owner-ref
  evidence_class: direct-observation-or-accepted-result-or-inference
  sensitivity: existing-classification
  retention_rule: existing-owner-policy
~~~

Avoid invented precision in confidence scores. A direct source, accepted proof, working hypothesis, and model inference are more useful distinctions than an unexplained “0.93 confidence.”

### 6.4 Writes and corrections

At material boundaries, produce a candidate lesson or fact with its supporting sources and intended audience. Route it through the existing owner-specific publication mechanism. Steward remains read-only.

Within a previously granted private-note scope, routine useful note updates can be automatic. Organizational decisions, authority changes, and executable skill changes follow their existing acceptance and publication rules. The implementation must not ask the Chairman to approve every harmless memory update.

Corrections should supersede the old claim and invalidate affected retrieval/cache entries. Deletion must distinguish stopping future use, removing derived content, and retaining source or audit history under existing rules. Track known derivatives and prevent re-ingestion of explicitly excluded material; do not promise erasure from every arbitrary copy.

### 6.5 Compaction and recovery

Use the selected Hermes v2 pre-compression contract on modes where Hermes owns the lossy rewrite. A successful callback must mean its durable checkpoint has actually committed. Enabling a flag without such a provider would be false assurance. [H1][H2]

For native engines with independent compaction, use their existing SessionAuthority and durable continuation mechanism. In particular, selected Hermes documentation refuses codex_app_server when a required checkpoint cannot be guaranteed. Do not mislabel every native Hermes backend as that mode; qualify the actual route. [H1]

Keep three records distinct:

- Conversational prose useful for personal or project continuity.
- Canonical tool/effect receipts and unresolved actions.
- Accepted facts, decisions, and procedures.

A prose checkpoint cannot replace the latter two. If checkpoint persistence fails, preserve the original transcript and unresolved effect references. Resume only from a truthful continuation boundary.

## 7. Learning that earns its complexity

### 7.1 The improvement cycle

Use the existing learning agenda and evaluation work as the foundation, while recognizing that the inspected Mastermind learning design is substantially market-domain oriented. Reuse its evidence and held-out evaluation principles; do not claim a generic teammate-learning runtime is already implemented. [I12]

The proposed loop is:

1. Capture an accepted result, a user correction, or a verified failure.
2. Identify the smallest generalizable lesson and its source.
3. Decide whether it belongs in a factual note, retrieval rule, skill, tool adapter, or product fix.
4. Create a bounded candidate change with explicit intended improvement.
5. Evaluate it against held-out examples and relevant failure cases.
6. Canary it on a limited existing role or workflow.
7. Publish through the current owner and monitor for regressions.
8. Roll back when the improvement does not survive real use.

Examples include a skill that consistently checks freshness before generating a brief, a browser routine that verifies a server-side save after a click, or a repo-specific debugging procedure that reduces time to accepted repair.

### 7.2 Bounded consolidation

Add consolidation as ordinary admitted work inside the current learning/Agent OS workflow. It can be triggered by meaningful new evidence, an accumulating correction backlog, or an already authorized scheduled maintenance window.

Take a versioned input snapshot, resolve the original sources, and propose a new view of the relevant knowledge. Identify duplicates, contradictions, expired facts, missing context, and possible procedural improvements. Keep exact user corrections deterministic; an LLM synthesis pass is not the mechanism for ensuring a specified sentence or record is changed.

Validate the proposal against sources and scope. Promote it through the existing owner, preserve rollback, and measure subsequent retrieval and task outcomes. Retain failed and cancelled output as unaccepted diagnostic material only when useful and permitted. An unfinished consolidation run must never become the current memory version.

This is a bounded job with existing budget and lifecycle controls. It creates no additional always-running learning daemon.

### 7.3 Prevent false learning

Repeatedly recalling a claim is not new evidence. A worker's confident prose is not an accepted result. A successful-looking screenshot is not proof that a backend mutation committed.

The learned change must not modify its own evaluation criteria, authority, budgets, or approval requirements. Preserve a held-out set and separate expected outcomes from the candidate implementation. Automated checks can evaluate many routine improvements without creating a new human-approval ceremony.

Learn from verified worker receipts, including across engines. Capture environment and version conditions so a procedure learned on one machine does not become an unconditional fleet-wide rule.

Financial research, forecasts, and workflow learning remain separate from trade origination, sizing, and execution authority. General teammate improvement does not silently expand those powers.

### 7.4 Measure useful improvement

Use metrics tied to the original consumer journeys:

- Accepted task completion at a defined quality threshold.
- Accurate scoped recall and correction propagation.
- Percentage of critical remembered facts with valid source references.
- Recovery after interruption without duplicate effects.
- Chairman interventions per accepted task.
- Cost and elapsed time per accepted outcome, including retries and review.
- Repeated-error rate before and after a learned change.
- Regressions introduced and time to rollback.

Run comparisons with the same model and task set when evaluating memory or skill changes, then compare engines separately. Otherwise a better model can masquerade as a better memory design.

## 8. Always-on operation and engine continuity

“Always on” should mean the system can receive responsibility, preserve it, resume work when eligible, and return results. It should not mean a model thinks continuously.

Use existing supervisors to keep admitted processes available. Feed supported source events into the existing intake and Wake/Dialogue paths. Persist the intake receipt before displaying an accepted or queued state.

A deterministic prefilter should coalesce duplicates and suppress no-change events. Model work begins when an event changes an admitted responsibility, a due commitment becomes eligible, a worker returns, or the Chairman supplies new intent.

Keep current Hermes timer ownership until the canonical supported binding exists. If timers are migrated later, retain one occurrence identity, reconcile pending and uncertain deliveries, and activate only one owner. A timer must never fire through two parallel carriers.

### 8.1 Recovery rules

| Situation | Correct behavior |
|---|---|
| Capacity rejects a task before execution | Existing Capacity can admit an eligible alternate route within the configured budget. |
| A running tool times out after a possible write | Mark and reconcile the original effect; do not repeat through another engine or account. |
| A process dies after a committed result | Recover the original receipt and return it to the same parent. |
| Effects are reconciled and a durable checkpoint exists | An authorized engine may continue the remaining work through existing admission. |
| All eligible inference routes are exhausted | Preserve the responsibility in its existing owner, show degraded/queued status only if persisted, and resume when eligibility changes. |
| A browser session loses connection | Reinspect the same session and target state before resubmitting a mutation. |
| A cancellation arrives | Stop new side effects, reconcile in-flight effects, and publish the truthful terminal state. |

Failover is useful after a safe boundary. The prohibited behavior is blind replay while effects remain uncertain, not every engine change after any historical side effect.

### 8.2 No extra control planes

Do not add another heartbeat agent, polling daemon, generic durable queue, or “self-improvement supervisor.” Implement missing behavior inside the owner already responsible for it.

A local model can be a qualified additional route for appropriate work. Its suitability depends on measured quality, hardware, latency, privacy, and available resources. It is not an assumed substitute for every frontier workload or a reason to bypass Capacity.

## 9. Deep tools, vault, browser, and computer use

### 9.1 Capability integration

The goal is broad practical capability with explicit task admission. A capability catalog should make available tools discoverable without placing every schema in every prompt. Select the qualified manifest at the task boundary and keep its serialization stable where practical; discovering a tool does not grant permission to execute it.

| Tool family | Integration destination | Proof needed |
|---|---|---|
| Executive/Steward | Existing grounded reads and admitted commands | Correct binding, current source, useful returned result |
| Agent OS | Sanctioned read compiler and owner-specific publication | Scoped recall, source freshness, correction propagation |
| GitHub/repos | Existing source workspace and delivery path | Branch/preimage correctness, focused checks, required CI, linked result |
| Subagent Fabric | Existing selected-child and placement contracts | Start receipt, exact identity, original parent consumption |
| VPS/services | Existing admitted host/service tools | Target identity, access scope, observed effect and service health |
| Browser | Qualified session adapter | Origin/account binding, one writer, effect readback |
| Desktop/design | Existing computer/Paper/platform adapters | Correct host/app/file, recoverable handoff, visible result |
| Credentials | Existing authority with qualified vault backend | Model-blind fill, scope enforcement, revocation |
| Learning/skills | Existing source publication and evaluation path | Held-out improvement, canary, rollback |

The current exact tool census must be extended deliberately. Built-in Hermes delegation cannot replace Fabric, and automatic upstream skill writing cannot bypass GitHub or the skillpack's publication rules.

### 9.2 Credential architecture

Use opaque secret handles in model-visible tool calls. Resolve values only at the execution boundary authorized for the exact target.

Bind access to role, project/task, credential purpose, service/account, and expiry. Browser fills also require exact origin, selected session, and safe frame/redirect handling. Logs should record which handle was used and the outcome, never the secret value.

Prefer the existing managed credential authority and a qualified keychain or equivalent host-protected backend. Verify the backend on each target platform; source presence is not evidence of working enrollment.

Separate credential resolution from arbitrary model-controlled shell access. If one process can read both the encrypted payload and its decryption key, a model-blind tool API alone does not prevent exposure through that process. Use the existing process, identity, filesystem, and network boundaries to enforce the separation.

Expose per-role permissions, last use, revoke, and secure entry in Mastermind OS. Request human participation only for a real credential, MFA, passkey, or physical-presence step that the current tools cannot perform. Do not invent a confirmation step for already authorized routine work.

Browser cookies and authenticated profiles also confer authority. They need scope, lifecycle, and revocation; they are not harmless files to clone across the fleet.

### 9.3 Newer Hermes source to reuse and qualify

At the inspected comparison revision 6b21d0564de0492e2ebd0d8f63fca86c03b5c892, Hermes already includes a browser vault tool, a login-backend registry, native keychain support, and 1Password/Bitwarden adapters. Its browser fill path checks origin and rechecks desktop control before a write. Reuse that implementation where compatible, after comparing it with the exact installed revision. [H7][H8]

Two concrete donor behaviors need attention before broad enrollment:

- The external-backend discovery code includes installed password managers unless disabled. Mastermind should instead bind an explicit backend/account allowlist from the existing credential owner. Availability is not an access grant. [H8]
- The computer permission helper's _child_env falls back to dict(os.environ) when sanitization raises. Qualify a fail-closed or minimal-environment path before running that donor helper with a secret-bearing parent environment. This is a finding in the inspected upstream source, not a claim that a deployed Mastermind host leaked credentials. [H9]

Keychain mode improves key custody for backups or copied home directories, but its source expressly notes that same-user or in-process code can still access the key. Treat plugins as trusted executable code and use the existing isolated credential boundary where stronger separation is needed. A website receiving an autofilled password can read it; “model-blind” refers to the model's visibility, not secrecy from the destination. [H8]

The newer computer backend distinguishes confirmed, unverifiable, and suspected-noop effects and supports a selected computer provider. Those semantics fit Mastermind's existing result discipline. Per-host OS permissions and native application access still require live proof. [H9]

### 9.4 Browser and desktop execution

Use the strongest available structured interface:

1. A purpose-built connector or API where it covers the requested operation.
2. DOM/accessibility automation for browser tasks.
3. Visual computer use when the application or workflow requires it.

All three must use the same task identity and effect rules. Switching interfaces does not reset uncertainty.

A computer-session lease should be enforced by the existing session/host owner. Bind it to principal, host, app or browser profile, task, and expiry. Permit only one mutating controller on a shared interactive surface at a time.

For a consequential interaction, capture the relevant precondition, perform the action, and verify the application's actual result. Avoid relying only on screenshots or a tool's “clicked” response. Where a website lacks idempotency, reconcile its current state after interruptions before retrying.

Human takeover pauses automation. Returning control requires a fresh observation and renewed task continuity, not replay of the last queued click.

### 9.5 A bounded canary

Begin with an internal browser workflow that has reversible state and an authoritative readback. Prove:

- Correct account and origin.
- Vault fill without secret exposure to prompts or logs.
- Successful structured action and domain-level confirmation.
- Interrupted action reconciliation.
- Human takeover and continuation.
- Revocation and cross-role denial.

Expand to more demanding external and native desktop work only after these behaviors are established through the existing qualification lane.

## 10. Fleet integration and repository access

### 10.1 Place work by capability

The live inventory, access, and health of every host were not verified in this research. The table below is a placement proposal for host classes, not a claim about current availability or a change to existing topology.

| Host class | Suitable responsibility, subject to qualification | Placement condition |
|---|---|---|
| Existing VPS/services | Existing durable ingress, control services, approved application/data workloads | Follow the current service topology and operational owner |
| Linux worker nodes | Isolated headless jobs, research, builds, tests, browser sessions | Capacity, workspace isolation, resource and disk limits |
| Mac fleet | Native macOS applications, design tools, macOS builds, appropriate general work | Exact application/file access and interactive-session isolation |
| Windows hosts | Windows-specific applications and tests | Qualified Windows automation and credential boundaries |
| Attended laptop/workstation | Tasks requiring local context or human participation | Explicit session availability and takeover behavior |

Use Capacity to select the host. The model should request capabilities such as a qualified browser, a particular app, or a repository workspace; it should not invent SSH paths or choose whichever machine happens to expose a credential.

Represent each admitted host with current health, supported tools, OS/app versions, capacity, credential scopes, workspace constraints, and lease state. Extend the existing inventory rather than creating an independent fleet registry.

A missing host blocks the jobs requiring it. Source research, coding, memory work, and other available lanes should continue independently.

### 10.2 Repositories as working environments

Each modifying task needs the intended repository, exact source baseline, existing writer/effect disposition, a task workspace or branch, and a clear result contract. Reuse current workspace and delivery mechanisms.

Skills and notes should tell Hermes where to look, how to verify, and what a useful result looks like. They should not silently grant access to all repositories or turn historical instructions into current law.

Protect current writers and uncertain effects. Reconcile the original target before recreating a job, branch, deployment, or review through a different carrier.

### 10.3 Cross-host continuity

Moving computation should carry source and result references, not a copy of a role's entire home directory. A qualified new host reconstructs the workspace from source and approved artifacts, receives scoped credentials through its existing authority, and resumes from the canonical checkpoint.

Private memory and authenticated browser profiles remain inside their authorized boundaries. A transfer must not broaden the audience merely because the destination is part of the same fleet.

## 11. The Mastermind OS product

The system should feel like a persistent colleague, with operations visible when needed. Extend existing Office surfaces rather than creating a dashboard for every new mechanism.

| Existing product area or proposed panel | User should be able to answer |
|---|---|
| Main conversation | What changed, what should happen next, and what needs my judgment? |
| Work | What is admitted, running, waiting, blocked, returned, or accepted, and which evidence proves that state? |
| Memory | What does the teammate remember, why, for whom, from which source, and how can I correct it? |
| Skills | What routines can it perform, what changed recently, and which evaluation supports the change? |
| Machines/computer | Where is work happening, can I inspect it, and can I take control? |
| Vault | Which role can use which credential, where was it used, and how do I revoke it? |

Use plain labels and progressive detail. Internal job IDs and adapter names belong in drill-down diagnostics, not every conversational reply.

Memory editing should include revision conflicts, source links, supersession, scope changes, and undo where the owner supports it. A memory budget indicator should help diagnose overgrown session context without suggesting that a larger context is always better.

Notifications should be grouped by responsibility and importance. The system should tell the Chairman about a completed outcome, a material change, or an exact decision needed. Routine successful background steps should not produce a stream of unnecessary messages.

Meta-CEO and Secretary remain distinct principals. Sharing a product shell does not merge their identity, authority, private memory, credentials, or runtime bindings.

## 12. Dependency-ordered implementation roadmap

The labels below are proposed work packets within the existing P0–P8 program. They are not new canonical job IDs, admissions, or approved commitments. Before execution, reconcile the active source carrier and extend the existing plan where appropriate.

The original P1 compared other harnesses. This dated research recommends the already integrated Hermes path for the present request. Preserve useful prior comparison evidence and original acceptance; repeat a comparison only when a material change or unresolved question warrants it.

| Packet / existing lane | Concrete deliverable | Dependencies | Done when |
|---|---|---|---|
| A: source/capability qualification, P0/P1 | Exact integration and per-host Hermes versions, donor manifest, current tool/mode matrix, active-carrier reconciliation | Current source law and writer/effect checks | One reproducible source baseline and truthful installed/unproven matrix; no overlapping implementation |
| B: scoped recall, P4 | MemoryProvider adapter to existing authorized read surfaces; bounded context and source attribution | A; role and task binding | Fresh sessions retrieve relevant scoped context, reject cross-role access, and expose citations |
| C: correction and checkpoints, P4 | Owner-specific candidate publication; corrections/deletion; route-specific durable checkpoints | B; existing native continuation owner | Corrected facts supersede old recall; interruption preserves original evidence and pending effects |
| D: execution and return, P3 | Existing selected-child path and separately scoped native worker path qualified through their carriers | Existing #2134 and #2147 or legitimate successors, exact source and runtime bindings | Each required admitted path starts a real task, returns evidence, and reaches its original parent |
| E: events and continuity, P4/P2 | Event-triggered eligible work, deterministic deduplication, timer ownership and recovery | D; existing event and timer owners | Relevant events resume the right task, quiet state costs no unnecessary model turns, restart preserves work |
| F: credential/browser/desktop canary, P5 | Scoped vault adapter, session lease, takeover and effect reconciliation | A and D; qualified target host/backend | A real internal task succeeds and the failure/denial cases behave correctly |
| G: coherent Office, P6 | Memory, work, skill, credential and computer views backed by real owner records | B/C/D; F for interactive controls | Chairman completes the actual journeys through the product |
| H: evaluated learning, P7 | Lesson-to-skill pipeline, held-out comparisons, rollback and reliability campaign | C/D/G; selected workflow | Measured improvement survives the held-out set and real use without breaking original acceptance |
| I: optional additional engines/local inference, P2/P8 | A qualified specialist or local route with explicit advantage | A; benchmark evidence and Capacity admission | Better cost, availability, or quality for a named workload without a new owner |

B and source preparation for F can proceed while D's live path is being reconciled. The live-runtime lane must not become a reason to stop all source work. Conversely, completing those independent adapters does not establish D's acceptance.

### 12.1 The first complete consumer journey

Use a real existing consumer, such as an AI Brief freshness incident, with permission and environment selected through the existing program:

1. Detect a material stale-data signal through the existing event owner.
2. Recall the relevant accepted source policy and last incident evidence.
3. Re-read the actual source and identify the current cause.
4. Admit one bounded repair or research task through Executive/Fabric.
5. Produce the required source change, checks, and original result.
6. Consume that result in the original parent conversation and update the Office state.
7. Preserve a supported lesson and propose a skill improvement if appropriate.
8. Demonstrate that a recurrence is diagnosed more effectively.

Start with read-only diagnosis if the modifying path is not yet qualified. The journey's completion state must say which slice was proved. An accepted diagnosis is useful, but does not close the full repair-and-learning journey.

### 12.2 First implementation packet, ready to commission

**Outcome:** A new admitted Hermes session can retrieve accurate, scoped Mastermind knowledge with sources, and a fresh session sees a corrected fact.

**Source ownership:** Existing Hermes integration and Agent OS read/publication owners.

**Proposed changes:**

- Add an adapter such as integrations/hermes_harness/agentos_memory_provider.py within the existing package.
- Add focused tests for scope, freshness, provenance, empty/error responses, stale-source rejection, and correction invalidation.
- Extend the existing native registration/configuration manifest only as required by the selected profile.
- Keep Steward as a read service; use the existing owner publication workflow for the correction fixture.
- Expose the memory source/scope result in the existing Office view contract.
- Keep native private notes and shared company knowledge explicitly separate.

These filenames are proposals, not claims that the files already exist. The assigned worker should confirm local package conventions before creating them.

**Acceptance fixture:** Two roles and two projects, one permitted common fact, one private fact, one stale shared fact, and a source-linked correction. Both the original and a fresh session must return the right scoped fact and current source. The private fact must never appear in the other role's result.

**Evidence:** Exact source revision, focused check results, recorded authenticated read path, returned source references, and fresh-session readback.

**Rollback:** Disable the external provider in the selected role profile and rebuild any derived index. Preserve canonical owner records and private native memory; do not erase company facts to undo an adapter rollout.

This packet establishes the foundation while keeping the next consumer, runtime integration, and acceptance denominator visible.

### 12.3 Delivery roles

Use native leadership for architectural judgment, source reconciliation, assignment, and acceptance. Use the existing paid Fabric path for eligible bounded implementation or evaluation labor when its admission and return path is actually available. Do not claim worker start from a capability report or a delivered message.

Separate bounded source packets by ownership: Hermes adapter, native runtime continuation, Office UI, credential/computer adapter, and evaluation fixtures. Give each packet a precise consumer, source baseline, effect boundary, expected evidence, and return path. Do not multiply workers when the dependency is an unresolved canonical effect.

## 13. Acceptance and falsification

The existing R2 obligations, original failure/rollback cases, ecosystem H1–H8, and Web/native journeys remain the acceptance denominator. The following cases add specificity; they do not replace the original contract. [I13][I14]

| Test journey | What must be observed |
|---|---|
| Cross-session memory | A fresh session retrieves the right scoped fact and source without a full history replay. |
| Correction and forgetting | A corrected claim supersedes old retrieval; excluded material is not silently re-ingested; retained audit history is described truthfully. |
| Cross-role isolation | Attempts to retrieve another role's private notes or use its credentials fail at the owner boundary. |
| Compaction | Durable checkpoint succeeds before lossy compression on supported routes; failed persistence does not discard the original context. |
| Native-engine continuity | A separately compacting engine uses its qualified native continuation path; no unsupported v2 claim is made. |
| Delegate and return | Exact admitted child starts, produces evidence, and the original parent consumes the original result. |
| Effect interruption | A timeout or process death after a possible write produces reconciliation, without duplicate mutation through another carrier. |
| Provider exhaustion | Eligibility changes are handled through Capacity; work remains durably represented and user-visible. |
| Browser and vault | Exact account/origin, model-blind fill, controlled takeover, revocation, and post-action readback all work. |
| Cross-host recovery | An eligible host reconstructs authorized state without copying secrets or expanding scope. |
| Evaluated learning | A candidate skill improves held-out outcomes and can be rolled back without corrupting source truth. |
| Endurance | A real multi-day campaign exercises the installed product, real events, restarts, actual quotas, and user-visible results. |

### 13.1 Benchmark structure

Retain the original 30–50 authentic-task comparative evaluation and seven-day reliability intent. Include relevant memory, browser, incident, coding, research, coordination, and correction cases inside that program. [I1][I13]

Use these comparison arms:

- Same model, harness and tasks: memory disabled versus enabled.
- Same model and context: original skill versus candidate skill.
- Same task and authority: qualified engines under the same accepted-outcome ruler.
- Whole-system tasks against commercial teammates only where access and terms permit, clearly distinguishing their different available tools.

A vendor feature list is not a benchmark. Do not report “better than Dot” or another system until the relevant comparison has been performed.

### 13.2 Proposed release targets

These are suggested targets to ratify against the baseline, not measured current results:

- 100% of critical remembered claims used for action resolve to an accessible current owner source.
- At least 90% correct recall on the deliberately scoped, held-out memory fixture.
- Zero observed cross-scope disclosures, unauthorized credential use, or duplicate effects in the defined adversarial campaign.
- A significant, repeatable reduction in repeated-error rate for each promoted learned skill.
- No model invocation caused solely by an unchanged polling result.
- Cost and intervention counts reported per accepted task, including unsuccessful attempts.
- Successful 24-hour canary before the original seven-day campaign; neither elapsed time alone nor synthetic clock advancement is acceptance.

Zero observed failures in a finite test set does not prove universal immunity. Keep the tested corpus, environments, and limitations in the receipt.

### 13.3 Evidence bundle

Every accepted increment should retain:

- The exact source/configuration revisions and tool/model/host qualifications.
- The consumer journey and its original acceptance references.
- Inputs, task scope, and expected result.
- Focused checks and required CI at the actual head.
- Real-path proof, with sensitive material excluded.
- Canonical outcome/effect/return references.
- Remaining limitations and rollback instructions.

## 14. Decisions, risks, and reversal criteria

| Decision | Why it is preferred | What would justify revisiting it |
|---|---|---|
| Keep existing Hermes initially | Source integration is substantial and required memory/vault seams already exist. | A named defect or unsupported consumer journey requires an upstream change. |
| One Agent OS knowledge owner | Avoids conflicting facts and duplicated organizational memory. | A proven new data class needs a formally assigned owner; an index alone does not. |
| Simple retrieval first | Makes scope, correction, and source quality easy to evaluate. | A measured failure set is resolved by vector or graph retrieval. |
| Selective donor reuse | Captures useful mechanisms without inheriting overlapping runtimes. | A bounded specialist wins a task and can fit the existing adapter contract. |
| Owner-enforced credential/session scope | Full tools require strong separation of authority and secret access. | A qualified existing backend offers a simpler equivalent boundary. |
| Evidence-driven skill improvement | Makes progress measurable and reversible. | A different evaluated learning mechanism produces better held-out outcomes. |
| Event-triggered cognition | Reduces idle work and preserves clear causality. | A particular consumer requires bounded sampling, with ownership and budget defined. |

The most important implementation risk is claiming more than the receipts establish: source availability as installation, CI as product acceptance, memory as authority, or a sent message as a running worker. The plan explicitly separates those states.

The most important product risk is building rich infrastructure while the first actual consumer remains unfinished. Every packet therefore ends in a named journey and a user-visible result.

The most important learning risk is amplifying unverified beliefs. Source provenance, correction, held-out evaluation, and rollback are part of the core design.

## 15. Research closeout and next action

This deliverable completes the bounded research and masterplan commission. It records commercial mechanisms, pinned reusable source, actual Mastermind integration boundaries, a target architecture, implementation packets, and acceptance criteria.

It does not claim a live vault enrollment, fleet qualification, working always-on worker, completed browser journey, successful learning experiment, or deployment. No secret was requested and no host installation was performed for this research.

**Next implementation action:** Reconcile the current Hermes carrier and exact head, preserve active writers and uncertain effects, then commission the scoped-recall packet in section 12.2 through the existing program. In parallel, advance the existing native execution-and-return qualification where its current evidence permits. The first full acceptance should join memory, admitted work, original result consumption, and a useful source-backed outcome.

## 16. Source register

Public product documentation was checked on 6 November 2026. It can change; product availability and pricing were not used as design assumptions. GitHub implementation references below are pinned to the inspected revisions. Assertions about proposed design and future targets are recommendations, not vendor claims.

### Internal source and program continuity

- **[I1]** [Existing open-harness convergence masterplan, P0–P8](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b0a280be474ae67e7681f68dc0dfe3af2aea1626/docs/superpowers/plans/2026-10-24-meta-ceo-open-harness-convergence-masterplan.md).
- **[I2]** [Meta-CEO autonomy open masterplan](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b0a280be474ae67e7681f68dc0dfe3af2aea1626/research/meta_ceo_autonomy_fable_2026-10-30/02_OPEN_MASTERPLAN.md).
- **[I3]** [Native Hermes session backend](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b0a280be474ae67e7681f68dc0dfe3af2aea1626/docs/hermes/NATIVE_SESSION_BACKEND.md).
- **[I4]** [Executive delegation binding](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b0a280be474ae67e7681f68dc0dfe3af2aea1626/docs/hermes/EXECUTIVE_DELEGATION_BINDING.md).
- **[I5]** [Hermes extensions](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b0a280be474ae67e7681f68dc0dfe3af2aea1626/integrations/hermes_harness/extensions.py) and [native tool registration](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b0a280be474ae67e7681f68dc0dfe3af2aea1626/integrations/hermes_harness/native_tool_registration.py).
- **[I6]** [Runtime registry](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b0a280be474ae67e7681f68dc0dfe3af2aea1626/integrations/hermes_runtime/registry.py).
- **[I7]** [Steward integration](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b0a280be474ae67e7681f68dc0dfe3af2aea1626/integrations/hermes_steward/README.md).
- **[I8]** [Model integration](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b0a280be474ae67e7681f68dc0dfe3af2aea1626/integrations/hermes_models/README.md).
- **[I9]** [Secretary unported/qualification inventory](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b0a280be474ae67e7681f68dc0dfe3af2aea1626/integrations/hermes_secretary/UNPORTED.md).
- **[I10]** [PR #2120](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120); merged state observed with merge commit 28a894186eb56654ab4e833eb11a183d2eed46ae.
- **[I11]** [PR #2134](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2134); open state observed at head ae40096acf4f911babb2a9b51e5c7e48c3d29a2e.
- **[I12]** [Existing Mastermind learning design](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b0a280be474ae67e7681f68dc0dfe3af2aea1626/research/MASTERMIND_LEARNING_DESIGN.md).
- **[I13]** [Existing acceptance and evaluation design](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b0a280be474ae67e7681f68dc0dfe3af2aea1626/research/meta_ceo_autonomy_fable_2026-10-30/04_ACCEPTANCE_AND_EVALUATION.md).
- **[I14]** [Chairman Control Room source](https://github.com/mastermindx-market-intelligence/macro/blob/a54d4d3db1484be3d0e07480f64c2a1a31775da8/agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md).
- **[I15]** [PR #2147](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2147) and [native attended Fabric adapter README at inspected head de68fadba4a3579b9d487a397d056f34a95657e6](https://github.com/mastermindx-market-intelligence/Mastermind/blob/de68fadba4a3579b9d487a397d056f34a95657e6/integrations/hermes_attended_fabric/README.md).

### Commercial product documentation

- **[P1]** [OpenAI: Getting started with your Dot](https://help.openai.com/en/articles/20001530-getting-started-with-your-dot).
- **[P2]** [Grok Bot: Create and manage Bots](https://docs.x.ai/grok-bot/bots).
- **[P3]** [Grok Bot: Skills, routines, and automations](https://docs.x.ai/grok-bot/skills-routines-and-automations).
- **[P4]** [Grok Bot: Vault and secure sign-in](https://docs.x.ai/grok-bot/vault).
- **[P5]** [Anthropic: Get started with Claude Duet](https://support.claude.com/en/articles/17631495-get-started-with-claude-duet).
- **[P6]** [Anthropic: Chat search and memory](https://support.claude.com/en/articles/11817273-use-claude-s-chat-search-and-memory-to-build-on-previous-context).
- **[P7]** [Manus: Context Engineering for AI Agents](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus), 18 July 2025.
- **[P8]** [Anthropic: The components of agent memory](https://www.anthropic.com/research/components-of-agent-memory), 6 November 2026.
- **[P9]** [OpenAI: Dreaming, better memory for a more helpful ChatGPT](https://openai.com/index/chatgpt-memory-dreaming/), 4 June 2026.
- **[P10]** [Claude Managed Agents: Dreams](https://platform.claude.com/docs/en/managed-agents/dreams), research-preview documentation.

### Hermes source

- **[H1]** [MemoryProvider developer contract at selected pin](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/website/docs/developer-guide/memory-provider-plugin.md).
- **[H2]** [Memory manager implementation](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/agent/memory_manager.py) and [conversation compression](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/agent/conversation_compression.py).
- **[H3]** [Selected Hermes vault store](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/agent/vault_store.py).
- **[H4]** [Selected Hermes skill guards](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/tools/skill_manager_guards.py).
- **[H5]** [Selected Hermes MIT license](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/LICENSE); [newer comparison snapshot](https://github.com/NousResearch/hermes-agent/tree/6b21d0564de0492e2ebd0d8f63fca86c03b5c892).
- **[H6]** [Checkpoint contract tests](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/tests/agent/test_pre_compress_checkpoint_contract.py). Tests were inspected as source, not executed in this research.
- **[H7]** [Newer Hermes browser vault tool](https://github.com/NousResearch/hermes-agent/blob/6b21d0564de0492e2ebd0d8f63fca86c03b5c892/tools/browser_vault_tool.py).
- **[H8]** [Newer keychain implementation](https://github.com/NousResearch/hermes-agent/blob/6b21d0564de0492e2ebd0d8f63fca86c03b5c892/agent/vault_keychain.py), [login backend selection](https://github.com/NousResearch/hermes-agent/blob/6b21d0564de0492e2ebd0d8f63fca86c03b5c892/agent/vault_backends/base.py), [1Password adapter](https://github.com/NousResearch/hermes-agent/blob/6b21d0564de0492e2ebd0d8f63fca86c03b5c892/agent/vault_backends/onepassword.py), and [Bitwarden adapter](https://github.com/NousResearch/hermes-agent/blob/6b21d0564de0492e2ebd0d8f63fca86c03b5c892/agent/vault_backends/bitwarden.py).
- **[H9]** [Newer computer backend](https://github.com/NousResearch/hermes-agent/blob/6b21d0564de0492e2ebd0d8f63fca86c03b5c892/tools/computer_use/backend.py) and [permission helper](https://github.com/NousResearch/hermes-agent/blob/6b21d0564de0492e2ebd0d8f63fca86c03b5c892/tools/computer_use/permissions.py).

### Other reusable source

- **[O1]** [OpenClaw memory architecture](https://github.com/openclaw/openclaw/blob/39d85007e9ba04ca502bf06da2ed51d35cbad491/docs/concepts/memory-architecture.md).
- **[O2]** [OpenClaw promotion rehydration](https://github.com/openclaw/openclaw/blob/39d85007e9ba04ca502bf06da2ed51d35cbad491/extensions/memory-core/src/short-term-promotion-rehydrate.ts), [consolidation eligibility](https://github.com/openclaw/openclaw/blob/39d85007e9ba04ca502bf06da2ed51d35cbad491/extensions/memory-core/src/dreaming-consolidation-candidates.ts), and [entry origins](https://github.com/openclaw/openclaw/blob/39d85007e9ba04ca502bf06da2ed51d35cbad491/extensions/memory-core/src/memory-entry-origins.ts).
- **[O3]** [OpenClaw memory provenance](https://github.com/openclaw/openclaw/blob/39d85007e9ba04ca502bf06da2ed51d35cbad491/docs/concepts/memory-provenance.md) and [MIT license](https://github.com/openclaw/openclaw/blob/39d85007e9ba04ca502bf06da2ed51d35cbad491/LICENSE).
- **[O4]** [OpenMausBot memory design](https://github.com/milind-soni/OpenMausBot/blob/164002b72b54127c4b8fa6d7bb017463b6b02ab2/docs/memory.md).
- **[O5]** [OpenMausBot provider contracts](https://github.com/milind-soni/OpenMausBot/blob/164002b72b54127c4b8fa6d7bb017463b6b02ab2/server/contracts.ts), [limit failover](https://github.com/milind-soni/OpenMausBot/blob/164002b72b54127c4b8fa6d7bb017463b6b02ab2/server/limit-failover.ts), and [core license](https://github.com/milind-soni/OpenMausBot/blob/164002b72b54127c4b8fa6d7bb017463b6b02ab2/LICENSE).
- **[O6]** [OpenMausBot enterprise license](https://github.com/milind-soni/OpenMausBot/blob/164002b72b54127c4b8fa6d7bb017463b6b02ab2/enterprise/LICENSE) and [licensing overview](https://github.com/milind-soni/OpenMausBot/blob/164002b72b54127c4b8fa6d7bb017463b6b02ab2/LICENSING.md).
- **[O7]** [NanoClaw snapshot](https://github.com/nanocoai/nanoclaw/tree/b6266ec9667ec3c1478a651987089b28714a729a) and [MIT license](https://github.com/nanocoai/nanoclaw/blob/b6266ec9667ec3c1478a651987089b28714a729a/LICENSE).
- **[O8]** [OpenHands SDK repository boundaries](https://github.com/OpenHands/software-agent-sdk/blob/039e5926d9655fd9b69b8c85604ec28ef17699bb/README.md) and [MIT license](https://github.com/OpenHands/software-agent-sdk/blob/039e5926d9655fd9b69b8c85604ec28ef17699bb/LICENSE).
- **[O9]** [OpenManus snapshot](https://github.com/FoundationAgents/OpenManus/tree/3309bf4e416fb1c74b008f3e86494439a31bad53) and [MIT license](https://github.com/FoundationAgents/OpenManus/blob/3309bf4e416fb1c74b008f3e86494439a31bad53/LICENSE).

- **[O10]** [Letta current source direction](https://github.com/letta-ai/letta/blob/8816d3a8516893bfdc0fa14bfb1235226012e295/README.md), [Letta Code reflection snapshot helper](https://github.com/letta-ai/letta-code/blob/5473a6639bd3b76fef74e293f6eed9ed6c2e9ad3/src/cli/helpers/reflection-memory-v2.ts), and [Apache-2.0 license](https://github.com/letta-ai/letta-code/blob/5473a6639bd3b76fef74e293f6eed9ed6c2e9ad3/LICENSE).
- **[O11]** [Graphiti implementation](https://github.com/getzep/graphiti/blob/747b480ec6b12ecb718f1e2bc588b20ee36ea9c2/graphiti_core/graphiti.py) and [Apache-2.0 license at inspected pin](https://github.com/getzep/graphiti/blob/747b480ec6b12ecb718f1e2bc588b20ee36ea9c2/LICENSE).
- **[O12]** [Mem0 README and OSS/managed distinction](https://github.com/mem0ai/mem0/blob/f1791daa86d469249c9b002f62644d58a1eb96a0/README.md) and [Apache-2.0 license](https://github.com/mem0ai/mem0/blob/f1791daa86d469249c9b002f62644d58a1eb96a0/LICENSE).
- **[O13]** [Playwright Apache-2.0 license](https://github.com/microsoft/playwright/blob/530161aae0ba59643dbbfa3c1b8c929874cc18ec/LICENSE).
- **[O14]** [browser-use MIT license](https://github.com/browser-use/browser-use/blob/b49a68e4060acb226da8f784194fef301c53a6d7/LICENSE) and [Stagehand MIT license](https://github.com/browserbase/stagehand/blob/c91e16776c3fb9964bbb9df6b9fe65a8f077ae7d/LICENSE).

## 17. Implementation continuation — Chairman-directed leadership

**Current directive:** “Take leadership to get this completely implemented.”
**Operation key / attended root:** hermes-teammate-evolution-20261106-c3.
**Immediate parent:** hermes-teammate-evolution-20261106-c3; this names the current attended program owner, not a fabricated native session ID.
**Existing workstream:** WS:CHAIRMAN-CONTROL-ROOM, Meta-CEO/open-harness program.
**Procedure/source pin:** ad6275a9c4d237bce75e52d0d6a8f41264b4ded5, protected master, Skillpack 1.0.1 / bootstrap major 1.
**Scope:** Implement and qualify the original memory, learning, tools, execution, fleet and Office journeys in sections 5–13. Source, installation, live use and acceptance remain distinct.

The assigned session owns recovery and implementation sequencing. The parent plan and source carrier remain this document and PR #2159. Existing #2134 selected-child and H24 native-context writers retain their paths and original effects. #2147 is now merged and must be reused; source merge is not worker enrollment proof.

### Current delivery organization

The principal owns architecture, integration choices, active-writer/effect reconciliation and original-scope acceptance. Eligible bounded implementation goes through the enrolled attended Fabric adapter with the original root, a stable child run ID and exact-source evidence. Native architectural judgment may resolve an ambiguous seam; it is not a substitute implementation worker or a mandatory review gate. WHY NOT FABLE: the first read-only adapter has a bounded existing compiler and a testable frozen contract.

The first ready work is scoped recall using ops/fabric_launch/agentos.py and its existing context_bundle.v1 compiler/validator. That existing owner already provides bounded exact-workstream reads and source observations. No new memory store, index, auth service, scheduler or compiler is authorized by this packet.

### First bounded packet and proof

- Consumer: a newly bound Hermes session receives current company context for its host-authorized workstream, with original source/accounting preserved.
- Scope: a new provider/registration adapter and focused tests under integrations/hermes_harness, plus its documentation. Do not edit the active selected-child/session/Control paths, shared profiles or live host configuration without separate collision reconciliation.
- Host authority: session/role/workstream scope comes from an injected current native host binding. Model text, constructor strings and retrieved notes are not authentication.
- Freshness: new retrieval invokes the existing owner; no persistent alternate facts cache. Currentness is checked before and after the read. Revoked/changed scope discards all returned context.
- Correction: the canonical source is changed through its existing owner; the next fresh session observes that version and source digest. The adapter does not independently rewrite company facts.
- Failure: bounded explicit unavailable result, no secret-bearing raw exception or partial unauthorized bundle, no manufactured durable-checkpoint success.
- Verification: actual provider-interface compatibility; two-role/two-workstream isolation; source correction across provider instances; revoke-during-read; malformed/oversized/compiler-error paths; no writes, schedules or delegation effects.
- Return: exact branch/head, owned paths, check commands/results, evidence digest and remaining integration/installation gap. Terminal worker output must be fully consumed and verified through the same Fabric run.

A local isolated source checkout has been acquired at the exact pin. The exposed Fabric adapter is available; worker START remains unproven until a real admission receipt. The Studio fleet-status surface returned FLEET_STATUS_UNAVAILABLE, an interface-specific capability gap rather than evidence that all hosts are unavailable. No runtime effect has been attempted in that lane.

### Continuing order

After the first verified source result, compose the actual Hermes provider registration and an owner-compiler integration proof, then advance corrections/continuity, credential/computer qualification and the Office consumer where dependencies permit. Reconcile existing active carriers before touching shared integration paths. Retain the original R2/H1–H8 and live/endurance acceptance; a source packet does not close the program.


### Independent computer-use hardening packet

Live read-only M2 inspection found native Hermes at 2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19 with the existing OMH memory provider selected. Its native vault/browser/computer modules exist; that is source presence, not credential or desktop enrollment. The existing provider and profile are preserved.

The installed permissions helper and its inner sanitizer can both return a parent-derived environment when sanitization fails. Independent source work will repair this exact donor behavior before broader computer qualification. Assigned new namespace: integrations/hermes_qualification/computer_env_guard/. Deliver a pinned, reproducible two-file source patch, offline qualification and source manifest/license attribution; no live installation, process restart, new credential broker or permission grant. The sanctioned installer remains the only installation owner.

Proof must show sanitizer import and execution failures, malformed sanitizer output, and the nested helper cannot launch a subprocess or expose synthetic secret values; valid sanitization preserves required desktop/telemetry fields. Test the actual selected donor bytes, not a restated reimplementation. Denial and readiness must remain truthful across the existing callers.

Memory original run hermes-teammate-memory-read-20261107-c3-01 has controller PID67433 and retained launch evidence on M1, but its last canonical projection has root/worker start unverified and no result. No retry, failover or replacement writer is allowed while that effect is unresolved. The computer packet is a separate disjoint source task under the same program root.


### Source review and implementation receipts (00:30 UTC)

Computer helper source is published in Ready PR #2165 at 08a1f2fbd10b815230bd6e68cef93224020f383d (tree88523462540c5a383c805e79d22491b6df467751). All ten committed files were read back exactly. Eighteen standard-library tests passed; pytest was absent. Both donor fallbacks are repaired with fixed OSError failures, invalid-output refusal and compatible _run_driver swallow handling. This is a patch qualification bundle, not an installed fix.

The original computer Fabric controller90657 terminated, and its retained same-root refusal records launch_attempted=false with reason prelaunch_FabricTaskError. The cause is not sufficiently typed to assert a capacity or permission denial. No worker ran and no dispatch was replayed. The assigned principal completed the permitted source work on the original assigned branch.

Memory child hermes-teammate-memory-read-20261107-c3-01 returned TERMINAL rc0, signalok, root verified, controller recorded. Full original response SHA256cbf8e83a8859c93db5249c20fc1e6c8147974e4f15cadbbbdfd13b85c9a0d8d1 was consumed. It published Draft PR #2163 at7b6173fa394040653977e1464bc6855c5d6a51fb (three assigned paths). This return is NOT_ACCEPTED: the principal reproduced a native default-path blocker against the exact upstream MemoryProvider source. build_provider_class stores the native module in _upstream_module, shadowing the method that _spawn_read calls. A real bound provider without an injected spawn raises TypeError before any reader call. Existing tests injected spawn and missed this product path.

The next bounded repair remains on #2163's same branch and three-path source scope. Separate module storage from helper lookup, prove default registration/preparation against the real native class/thread, enforce a finite positive freshness ceiling, prevent READY from claiming a revoked snapshot, and document restoration of the actual prior provider (M2 currently OMH) instead of blindly reverting to built-in memory. The original first leaf is terminal and has no background wake; no live source/host changes are inferred. A successful repaired source result will still owe native host wiring and the live owner read.

Original native integration #2134 head ae40096acf4f911babb2a9b51e5c7e48c3d29a2e has successful current-head checks but current GitHub reports a conflict; its original Studio publisher reads APPLIED with matching local/remote head. Managed workspace reports ignored/untracked material and remains preserved. The original root/admin Ubuntu1 C26-result denial and installed serving holds remain intact; no replay or cross-carrier privileged read was attempted.


### Real compiler probe and evaluated-learning consumer

The actual M2 Agent OS compiler completed a read-only WS:CHAIRMAN-CONTROL-ROOM request with budget4000: rc0, no stderr, 13.505seconds, 108257bytes, context_bundle.v1, exact target, no_answer_reason=null, six sections, three degraded entries and fifty budget omissions. Observed Macro revision3dd5556be110c0d94c3b83988d8bb06002d82570; compiler SHA25621b1857ab7c30b9b41cf37903ceb74fd369d9ed5cf2450e870e92c92024a32a0; bundleSHA256e9be707b7b5a043b3aef60f0f9f0a0a1a764282ea0586ddc0dd178b3eb3428e8. This exposes a real integration gap: the adapter's 32KiB envelope would refuse the current company bundle. Resolve at the existing owner/qualified delivery policy; never trim required accounting in a second compiler.

The existing Harness2 refinement engine and Agent Evaluation contracts are reused for learning. There is no production Hermes Harness2Port yet, and native_turn_evidence intentionally does not prove served-model identity. Outcome Learning #398 remains held. No heuristic assessment, synthetic receipt or public development fixture may be presented as held-out efficacy or automatic promotion.

Independent bounded source packet: add scripts/agent_eval/hermes_memory_grounding.py, tests/test_agent_eval_hermes_memory_grounding.py and docs/hermes/MEMORY_LEARNING_QUALIFICATION.md only. Named consumer is an AI Brief stale-source diagnosis after a canonical correction. A pure deterministic scorer checks the current fact/source, authorized scope and original-effect-preserving next action; the existing build_scorer_pass_document owns score-pass construction and exact run identity. No provider calls, stores, global corpus edits, skills publication, promotion or runtime gates. Existing native role and memory-provider paths remain fenced.


## 18. Implementation receipts and remaining integrations — 2026-11-07

This is a cumulative implementation milestone under the same parent operation `hermes-teammate-evolution-20261106-c3`. **MISSION_COMPLETE: false; BUILT_NOT_PROVEN overall.** The current assigned principal owns continuation. Published source and protected release requests do not prove installation, authenticated role execution, durable operation or learning improvement.

### P2 / scoped organizational recall

Mastermind PR **#2163**, original branch `sol/hermes-agentos-memory-20261107-c3`, now has head `62c0d6397b671a201d151600bfa0083bdcbec3e2`, tree `f99bafc6396e32f07bb057fcaa76678b22492d25`. Original feature head `7b6173fa394040653977e1464bc6855c5d6a51fb` was not accepted unchanged: principal reproduced a real native-default `TypeError` before any owner read because class module storage shadowed a method. The original repair worker published `4696e17970f39249f3a8c06e3462353f62ec05ea` on the same PR/worktree. That worker then ended rc1 with a provider session-title error (`MiniMax-M3` unrecognized); its Fabric return remains unaccepted, not rewritten as success. Root separately qualified the published source and continued through the original M1 worktree and ordinary same-branch git publication.

The adapter now uses the real upstream default context thread, preserves contextvars, checks finite positive freshness at most 300 seconds (120 default), and consults currentness before cached readiness. The host's immutable session binding defaults to a 32 KiB rendered-context limit and can explicitly select a positive integer up to 128 KiB. Model text and environment variables cannot choose this capacity. Every original owner byte and accounting field is retained; the wrapper counts toward the limit and oversize refuses whole. Huge integer freshness values also produce the closed refusal.

**Reproduced proof:** `/opt/homebrew/bin/python3.12 -m unittest -q integrations.hermes_harness.tests.test_agentos_memory_provider` on the original M1 worktree ran **69 tests, zero failures/skips**, original process44579 terminal rc0. All nine native interface cases executed against actual selected Hermes `1c0cd667746d3395fe9e1b6c74f8f85952486f18`; MemoryProvider source SHA256 `ac81dcf489c698891f0edebfe26845a75c50d2bde77ec3be8d7938a85c79f1fc`. Scratch separately ran69 with9 explicit skips because it lacks the full upstream checkout. These counts are not added together. Parent first reproduced64 passing tests on repair head4696 before the five new envelope cases.

**Actual owner-path qualification:** original M1 process45125 used the real native default thread and real `ops.fabric_launch.agentos.read_context`, with an explicitly synthetic qualification resolver/guard and no Runtime grant, selected provider or model request. Its local Macro root `/Users/chriswong/Documents/GitHub/macro`, head `c3d7f1d4149176e35abf6077c18c96513abe6600`, returned59,933 raw bytes in12.214seconds and61,065 rendered bytes. Verbatim suffix verified; six sections, three degraded,24 excluded,46 omitted records preserved. Bundle SHA256 `8f51503e4cfa25ff7a8f9a8199b29a48cedd2be7b46a9e3487355ca3004fb610`; compiler SHA256 `759bafaa825187eee22e76cee4df637763605a9c8878d8e101405375e3a19ee9`. This proves that local compiler revision, not fleet-wide freshness or production enrollment. The prior M2 read at Macro3dd5556 returned108,257bytes and motivated the larger explicit limit.

The source leaf is Ready for normal protected release. Runtime work remains: supply real authenticated session/role/generation bindings, select the intended native-role provider, preserve attended M2 OMH, enforce the first-turn preparation barrier, prove full native request fit including instructions/tools/response reserve, and run cross-role isolation/revocation using canonical publications. There is no installed `install_host_ports()` composition yet. Rollback restores the exact prior provider/configuration, never blindly `builtin`.

### P4 / computer environment boundary

PR **#2165**, branch `sol/hermes-computer-env-guard-20261107-c3`, head `1c8a4391cad243f860c25431e8adf849ecf5f6f7`, qualifies the two-file upstream fail-open repair and its actual caller behavior. Fixed `OSError` failures preserve unknown/not-ready probe contracts; `None` cannot request ambient environment inheritance. The existing sanitizer is reused. All **18 focused tests** passed; the final collector bridge includes those same cases in existing Python3.12/3.13 qualification CI. Original release request at08a1f2 was disabled/read back absent before that substantive collector fix; one new exact-head request was read back at2026-11-07T00:48:02Z. Do not rearm an already armed/queued effect.

Patch SHA256 `d17af87e60a1f92a52ef446ad393ce2841c876a28e2ae0580bc7e6db09d6721f`. Expected postimages: permissions `c1b1f7b1de10fc14ff2892ec8b0dd7ca2c1976ef76a0d6884e93577caeea8d0d`; backend `b106ce6b1086a932648c141a517821fd503a54b75d52e7cf5b127c94df1de78f`. Both selected1c0cd and observed M2 source2bd378 have the exact qualified preimages. MIT attribution is retained. No vendor tree, driver, permission or running service was changed.

**Receiving integration discovered:** existing `scripts/enroll_linux_secondary_worker.py` already ships `integrations/hermes_qualification`, but native install currently requires both pristine selected vendor HEAD1c0cd and an empty tracked/untracked diff. Dirty patched source fails `NATIVE_VENDOR_CHECKOUT_DIRTY`; a committed derivative fails `CHECKOUT_SHA_MISMATCH`. Existing `release_manifest.py`, `native_gateway_sources.py` and `hermes_runtime/install.py` need an explicit frozen vendor derivation inside their current source-preparation/install owner: base+exact patch identity+two postimages+complete dependency inventory, prepared into a new unselected artifact. Do not weaken clean-checkout rules or edit a serving vendor. These paths overlap original PR#2134 and must be composed in that carrier. M2's observed2bd378 home also has no demonstrated managed macOS immutable activation binding in this investigation. Computer capability enrollment and real desktop proof remain separate; current managed profiles refuse computer_use.

### P5 / measurement before learning claims

PR **#2167**, branch `sol/hermes-memory-grounding-20261107-c3`, head `79133a7f6a17a26f77a580bdb2621dd22bdf9bf5`, adds one pure scorer in existing Agent Evaluation,22 public synthetic tests and a prospective consumer recipe. `python -m unittest -v tests.test_agent_eval_hermes_memory_grounding` passed **22/22**. Exact three committed file bytes were read back. The source uses `verification.verify_run_graph` and `scoring.build_scorer_pass_document`, not another evaluator or receipt store.

The evidence entry point joins exact raw input/hidden-expectation/output bytes to existing scenario/run digests, rejects duplicate-key/malformed output, and measures exact source revision, corrected fact/version, scope, advisory-only recall and original-effect-preserving action. Unknown effects require reconciliation of the same operation. A rehashed forged VALID record is rejected; a genuinely invalid model/effect run remains invalid despite correct answer content. Bound fixture truth and actual source access are still owner assertions, not authenticated by equality checks. All six behavior dimensions and existing technical-integrity dimensions must be required by a deliberately enrolled real scenario.

A prospective same-model/procedure/task/source comparison, actual native model/capability/cleanup observations, a production Harness2Port, suspected Agent OS discovery, and fresh-session skill adoption/rollback are still owed. Existing Harness2 owns refinement; existing EVAL owns evidence; held Outcome Learning PR#398 remains held. Public development cases and unrecoverable holdout seals cannot prove generalization. This source PR was observed queued at position5, not merged, at the last boundary. Consume its original release effect.

### P4 / vault and browser ownership ruling

Existing Workbench/Executive owners already authenticate callers, admit work, enforce browser leases and retain action effects. `CredentialReadinessObservation` is readiness only. Current production browser composers explicitly return no persistent-profile grant. The inspected bindings do not grant website backend/account/item/origin use. Hermes native vault discovery/unlock/listing does not consume those Mastermind grants; a false page-backend match can fall back to native CDP, and HMAC action references contain base64 plaintext, not encryption.

The next useful vault slice must include **the existing owner's account/item permission producer plus one actual secret-safe fill receiver**. Bind one backend, account/item, exact origin, owned page, host/boot, original operation and current generation; revalidate before backend discovery/secret resolution and immediately before page write; reuse existing Runtime admission and ActionArtifactStore. Never put a resolved password in a model-visible action token or ordinary generated trace. No generic vault enablement, account enumeration or fallback browser. A mere grant dataclass/readiness wrapper is not integration. Prove a disposable synthetic account login, wrong-account/origin refusal before resolution, takeover/navigation revocation, no fallback, uncertain-effect preservation and secret-free artifacts. The current Workbench relay still lacks that qualified secret-fill transport.

### Original runtime dependency and exact gate

PR **#2134** remains the sole original runtime integration carrier: operation `meta-ceo-byok-followon-parent-20261106-c35-01`, M2 Studio managed workspace `/Volumes/Mastermind 2/agent-workspaces/web/meta-ceo-byok-followon-parent-20261106-c35-01`, branch `sol/web-meta-ceo-byok-followon-parent-20261106-c35-01`, head `ae40096acf4f911babb2a9b51e5c7e48c3d29a2e`. Original publisher status was APPLIED with local=remote head and clean tracked source. Fresh native GitHub read showed CONFLICTING/DIRTY and the existing auto-merge request from2026-11-06T23:23:08Z, with no queue entry. Do not create a replacement branch/PR or overwrite ignored/untracked material. Reconcile actual writer/custody and this release effect before original-carrier source composition.

The original Ubuntu1 root-owned C26 journal had an explicit PermissionError under the present user connection. Restore the **original authorized root/admin connection**, then reconcile that original journal. Do not replay the denied read through RDC, another account or carrier. This is an actual authorization boundary; it is not an old-author approval requirement. Secretary/Meta installed serving, original-child START/parent consumption and actual M2 Fabric execution enrollment remain unproven. Source qualification cannot clear these runtime facts.

### Continuation order and preserved effects

1. Consume the original protected release effects for2163,2165,2167. Repair only new concrete failures; no empty rebase or duplicate request. Read actual merge commits before installation claims.
2. Reconcile and recover original2134 source/release custody; compose explicit vendor derivation and actual native role/context/tool binding through its existing owners. Preserve any active writer or unknown effect.
3. At restored original C26 authorization, consume its result and continue the existing installed qualification/role activation. Do not restart or redispatch from a guessed result.
4. Prove one complete native journey and the account-scoped vault/browser path through current owners. Enroll additional hosts/capabilities only with their actual binding and post-action proof.
5. Run the prospective memory/skill experiment, publish supported suspected discoveries and source skills through current owners, then execute the original endurance/restart/revocation acceptance.

Original computer and grounding Fabric requests were reconciled as REQUEST_REFUSED_BEFORE_LAUNCH with retained launch_attempted=false and terminated controllers; neither was redispatched. Original memory feature and repair processes are terminal. No temporary watcher, post-turn wake, new scheduler or daemon was created. Native principal children supplied read-only architecture judgment. Current source procedure pin is `650b81344a7cf5790cdf617dff6e1e2175742037`; INDEX/laws were retrieved at that pin. Its sole delta fromad6275 is the delivery workflow's exact accepted-PR deployment identity example and its test; no source-law authority was silently changed.

## 19. Protected source merges and native carrier recovery — 2026-11-07

**Mission state remains BUILT_NOT_PROVEN; MISSION_COMPLETE=false.** This milestone records actual source merges and source recovery, not installed activation.

### Canonical release receipts

- Recall PR #2163 is MERGED at `5ca25e561ffaeacb4ef94bb08f507617f80d0607`.
- Grounded scorer PR #2167 is MERGED at `78d8cb693888579808f02de0934c18f4915fd042`.
- Both merges were read back through native GitHub state with timestamp `2026-11-07T01:17:19Z` and successful head checks. Do not re-arm their concluded effects.
- Computer guard PR #2165 remains on its original request at head `1c8a4391cad243f860c25431e8adf849ecf5f6f7`; one canonical test shard was still running at the observed boundary. No duplicate release request.
- Agent OS continuation is [macro PR #10813](https://github.com/mastermindx-market-intelligence/macro/pull/10813), head `3a1b705b945e514c7fd003cbd6d032ca30615e8e`, one new `agentos/handoffs/CHAIRMAN-CONTROL-ROOM-2026-11-07-hermes-teammate.md`. Exact protected `check_handoff` returned zero errors and the committed file was read back byte-for-byte. Full graph CI and Macro's own merge-on-green controller remain distinct; no native auto-merge fallback and no adopted-continuity claim before merge.

### Original PR #2134 recovered without replacing its carrier

The original auto request was disarmed with canonical absence of both auto request and queue entry. Its original registered M2 source workspace contained stale merge metadata for already-ancestor `e1869de4`, with a clean index/worktree. After that metadata was reconciled, a real merge against protected `1b469573f57c6016a46757dd98b95fa43af2a8eb` produced exactly one conflict: the `auth.rs` entry in `tests/executive_fabric_release_identity_review.py`.

The composed auth SHA-256 is `3b2699dffc841f1b5f1cd7381e8902b94eded1fd21b934b57bed89c1a876c85c`, with the unchanged HTTP 503 operands at lines 3514, 3519 and 3523. Both protected Control Room changes and native session behavior were retained. No broad scanner exemption or functional rewrite was introduced.

Final original branch head is **`7a3160fa76ceae58726eacd27d741872273d3828`**, tree **`3ddb5de3275c798c1d5eebc2210f1c86d7349163`**. The exposed typed commit schema lacks its implementation's nested merge fence. The known single-parent local commit `562d1990` was reconciled; the already prepared merge was concluded locally in the same registered workspace, preserving parents `562d1990` and `1b469573` and exactly the qualified tree. The original typed push returned APPLIED, clean local=remote at `7a3160fa`; remote PR readback is MERGEABLE. No undeclared tool input, new publisher, account switch, force push or service/configuration change was used. An unrelated automatic repack warning concerned another worktree's denied index; that read was not repeated or repaired.

Separate focused receipts: 316 Python identity/topology/shared-auth tests; TypeScript typecheck; 67 UI tests across six files; native-mode frontend build; 16 targeted native Rust passes. One existing signed-HTTP fixture was explicitly ignored, not counted as installed proof. The initial native build lacked mandatory source/build metadata and failed before tests; the corrected invocation used the actual committed source revision and passed. The final merge has the exact tested source tree. Fresh final-head canonical CI remains required.

### Next bounded implementation seams

1. **Vendor derivation:** extend the existing frozen native_gateway recipe, prepare-hermes-dependencies, NativeSourceClosure and installer. Reuse guard #2165's exact `prepare_sources()`, prepare a new unselected artifact, retain the selected upstream base, admit only the two declared postimages plus the complete frozen inventory, and preserve the pristine path. Never add allow_dirty or patch a selected runtime in place.
2. **Native recall enrollment:** use actual authenticated role/session/enrollment and per-admission authority. The provider needs a real local nonblocking generation fence; the existing network-capable session_guard cannot simply be substituted. Macro compiler root and rendered capacity must come from trusted installation input, not a job root or model text. Hermes' generic PluginContext.register_memory_provider is inert at the selected pin: actual MemoryManager/provider-loader or agent-construction receiving code must be exercised.
3. **Learning producer evidence:** use exact original terminal result and actual provider-call evidence. Retained answer bytes are redacted user-visible output, not raw provider bytes. Configured catalog model or served_model fallback hints cannot set model_identity_verified. Observer/middleware coverage and exact tool/model/runtime joins must be proven before existing EVAL can become technically VALID.
4. **Website vault:** retain the existing-owner permission-producer plus secret-safe owned-page fill requirement from section 18. Credential readiness alone remains insufficient; do not expose generic backend discovery/unlock.

The original Ubuntu1 C26 permission denial is unchanged. Restore its original authorized root/admin connection to reconcile the original result. It is not resolved by source merges or local tests. No post-turn wake, daemon or background Web execution is asserted.

## 20. Bounded implementation ownership — 2026-11-07

- Vendor derivation child `hermes-teammate-vendor-derive-20261107-c3-01`, original controller `17269`, is the sole writer assigned to the recipe/source-preparation/installer slice. Retained original trace records M1 LAUNCH at 01:35Z; canonical status still reported ACTIVE_OR_WAITING with root/worker START unverified. This is not durable execution proof. Do not replace its writer or retry; consume the original result. [Full brief](hermes/HERMES_VENDOR_DERIVATION_BRIEF_2026-11-07.md).
- Pure EVAL adapter child `hermes-teammate-native-eval-20261107-c3-01`, controller `40549`, was reconciled as REQUEST_REFUSED_BEFORE_LAUNCH, retained request, no worker execution, original adapter exit75 and terminated controller. It was not retried. Source adjudication then established that a three-new-path adapter cannot form a truthful existing EVAL run from today's native read result: mandatory observed model/process/workspace/environment/policy/tool-event/timing fields are absent, and invalid validity does not authorize invented required fields. Prefer real producer projection/instrumentation; no facade or fake run was written. [Full brief and disposition](hermes/HERMES_NATIVE_EVAL_BRIEF_2026-11-07.md).
- Original native PR #2134 exact-head auto request is enabled at `2026-11-07T01:34:08Z` on `7a3160fa76ceae58726eacd27d741872273d3828`, with no queue entry at readback. The protected test check is required, strict and enforced for admins; required approval count is zero and CODEOWNERS review is not required. All actual review/effect holds remain binding.
- Macro continuation #10813 was updated to `5a226a935b21839f9c9b999ba9f242ff47c2ed6b` with the completed original source recovery and vendor-child custody; exact file readback and canonical focused validator passed. It is still unmerged and unarmed while full current-head CI qualifies.

## 21. Real terminal metadata producer and qualified continuity release — 2026-11-07

Source adjudication replaced the speculative EVAL leaf with a concrete improvement to the existing authenticated native result owner. [PR #2170](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2170), branch `sol/hermes-native-eval-20261107-c3`, head `f2a8ae6b5c2a517a882f8001d35e823676bc6ac2`, tree `eeba7559a19104fd15a2c920b8ae3cf42f38b2a9`, changes only native_session_control.py, its existing tests, the exact reviewed source digest and the producer-contract document.

The original principal/profile/session/submission/input/admission checks still precede the stored read. A bounded terminal_metadata projection now preserves actual present flags versus missing data, per-turn API call count, configured/reported labels and the exact delivered UTF-8 output digest. Malformed selected fields are named without forwarding their values or losing a valid answer. Raw errors, reasoning, history, tools, arbitrary account/usage objects, pre-transform response and ambiguous served_model are omitted. Model identity remains explicitly unverified. Existing answer semantics, original-effect reconciliation, private socket and result store remain unchanged. This is original terminal metadata delivery, **not complete native EVAL**.

All four published files were read back exactly. Current-head canonical CI passed: protected test, PR fast checks, full Hermes runtime acceptance on Python3.12/3.13 and harness offline stacks on both versions. Runtime receipt: https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42326357509 . Protected test: https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/42326357523 . The local Python has no pytest, so no local pytest pass is claimed. The one native qualification-workspace acquire refused before construction with REPOSITORY_SOURCE_UNAVAILABLE; repository enrollment was READY and a bounded same-owner diagnostic verified the exact candidate object. No acquisition retry or alternate writer was used; hosted CI supplied executable proof.

PR2170 is Ready and stacked on original2134. **Do not merge into the active parent branch.** After2134's actual protected merge, retarget2170 to master, qualify the resulting current-head checks/holds and issue one ordinary head-leased release request.

The computer guard2165 now has successful head checks and an original native queue entry (position3, AWAITING_CHECKS at readback). Native2134 remains on its original pending-CI auto request. Recall2163 and grounding2167 remain canonically merged; do not re-arm them.

Macro10813 at5a226a935b21839f9c9b999ba9f242ff47c2ed6b passed its full selected CI packs, ci-gate, fences and active main authority. Exact current controller source81a255142085c42ffc942b19160d95b32730f161 returned can_arm_merge_on_green=true for the17 observed check runs; its complementary inactive pilot-authority failure is nonbinding on main by that existing controller. No comments/reviews/holds or mandatory formal approval were present. The single existing-controller opt-in label was added at2026-11-07T02:00:58Z. Consume a full original sweep and the actual merged receipt; label success is not merge or continuity adoption.

A bounded read of the original vendor worker's M1 source found its registered branch `sol/hermes-vendor-derive-20261107-c3` in `/Volumes/STORAGE/agent-workspaces/claude/36170df991f45592/pr-2134-b2a49ae6d982ec8f`. Head65cb4dd0697ff892016384bf31799b56206c062b is the explicit dependency merge with parents7a3160fa and1c8a4391; native_gateway_sources.py is being edited. This supports original source-writer custody, not a fabricated canonical START/root receipt. Keep original controller17269 and await/consume its return; no replacement writer.

Remaining core integration is unchanged: actual held memory enrollment/first-turn delivery, full native EVAL instrumentation, account-custodian enrollment plus atomic secret-safe browser fill, original installed/runtime/fleet/endurance proof. The real Ubuntu1 C26 denial still requires restoration of its original authorized root/admin connection before that exact journal can be reconciled. No alternate-account replay, new authority/store/controller or post-turn wake has been introduced.


## 22. Recovered vendor implementation and release boundary — 2026-11-07 02:41 UTC

MISSION_COMPLETE=false; BUILT_NOT_PROVEN. This milestone records source progress, not installed-role acceptance.

### Canonical release receipts

- Agent OS continuity PR10813 merged at 2026-11-07T02:06:29Z as `a29e6b1354f1f6255582c135eec12306853a5ed0` through the incumbent Macro merge-on-green controller. No native auto-merge was used.
- Computer-environment guard PR2165 merged at 2026-11-07T02:10:51Z as `cd4600eec2c0420358af1d9b75adbf27feeb613c`. Do not re-arm it.
- Native integration PR2134 remains original head `7a3160fa76ceae58726eacd27d741872273d3828`. Its current-head status rollup is SUCCESS; its original release effect is now a merge-queue entry, observed position3 AWAITING_CHECKS. Auto request is null because the queue owns the next step. Do not re-arm or duplicate.
- Terminal metadata PR2170 remains Ready, stacked on PR2134 at `f2a8ae6b5c2a517a882f8001d35e823676bc6ac2`; no auto request. Retarget the original PR to master only after2134's canonical merge.

### Vendor child reconciliation and actual source

The original vendor Fabric run `hermes-teammate-vendor-derive-20261107-c3-01` reached verified-terminal rc1, accepted=false, with a provider connection/session-title error. Exact failure response:292bytes, SHA-256 `e7e0ba556470bd39a62c45ad7efc0bb1b57fc8c979ceb75736a37538becc8d78`. No retry or failover.

Parent inspected the original M1 worktree `/Volumes/STORAGE/agent-workspaces/claude/36170df991f45592/pr-2134-b2a49ae6d982ec8f`. It retained branch `sol/hermes-vendor-derive-20261107-c3`, merge parent `65cb4dd0697ff892016384bf31799b56206c062b` (7a3160 + exact2165 dependency), and one incomplete source file. Parent recovered this same writer/worktree, replaced the incomplete helpers with connected implementation and tested it. Source is now committed and pushed cleanly at `7413842fb903d6a0d62d3d29d5af0fe9e73038f7`, exact remote readback.

Draft PR2171: https://github.com/mastermindx-market-intelligence/Mastermind/pull/2171
It connects the one closed computer_env_guard derivation to the existing root preparation, complete frozen inventory, native installer, installed receipt, launch and rollback. It has no new permission or runtime owner and activates nothing. Tests:385passed,1skipped under CPython3.12 on M1; the skip requires the actual fixed Linux3.12 recipe. Focused portable subset48passed under3.14. Required hosted Linux CI remains outstanding. Earlier two Linux-oriented lifecycle assertions failed on Mac /tmp and /etc aliases; these were not reported as passing. Actual tracked upstream census:20,971 regular blobs, no tracked symlink/gitlink at selected1c0cd; not host custody proof.

The six-file implementation delta, limitations and rollback tuple are documented in `docs/hermes/NATIVE_VENDOR_DERIVATION.md` at7413842. Preserve the original PR; do not merge the dependent branch into active2134. Parent retargets after canonical2134 merge.

### Next source lanes and bounded refusal

Request-content observation full brief is persisted at:
https://github.com/mastermindx-market-intelligence/Mastermind/blob/f8787f362eeee9da9b92a011082ab706e76b5039/research/hermes/HERMES_NATIVE_REQUEST_OBSERVATION_BRIEF_2026-11-07.md

Its original Fabric run `hermes-native-request-observation-20261107-c3-01`, controller69401, was REQUEST_REFUSED_BEFORE_LAUNCH with retained request and MMX_FABRIC_EXIT=75. No worker, source branch or result was created by that request; same-run replay is false. Parent proceeds with permitted direct source work, not a duplicate dispatch.

Memory enrollment design is pinned to the original held native recipe/loader/current-claim owner. An additional concrete issue must be resolved before implementing its compiler runner: Macro's compiler imports YAML and local helper code, so an entry-script hash alone does not qualify its executable closure. The reader's actual `sys.executable -B` subprocess must use a qualified source/dependency recipe and a closed environment. Do not guess a Macro host path, widen native import_roots, or treat a duck-typed callback as custody. Also7a3160 does not contain the merged recall provider; compose the actual2163 merge `5ca25e561ffaeacb4ef94bb08f507617f80d0607` when implementing this lane.

No admitted turn, provider dispatch, valid EVAL, browser account enrollment, fleet activation or endurance proof is claimed. Original Ubuntu1 C26 root/admin connection restoration remains the exact installed-runtime gate; no alternate carrier or account was used to replay its denied journal read. Outcome Learning398 stays held.


## 23. Protected native merge, scoped conflict repair, and request-observation producer — 2026-11-07 03:17 UTC

MISSION_COMPLETE=false. BUILT_NOT_PROVEN remains the overall classification. Source integration, installed capability, actual inference, EVAL validity, and user acceptance remain different facts.

### Current protected law and concrete company purpose
Protected master advanced through PR2134 merge4d1561bcba1bfad583c75e419ced9a6ff0f3fa40 to e37dc82f070fd391e29f0dbd0bf46b022166beea. Material AGENTS/CLAUDE changes distinguish Strategic State company portfolio from the domain-limited Improvement Agenda and require an active-P0 capability mapping. INDEX and applicable laws were refreshed together at e37dc82f; schema/master skillpack1.0.1/minimumbootstrap1 verified. All previously loaded procedural-law bytes remain identical; the strategic delta was read. The actual strategic_state.load_strategic_state loader verified active AUTONOMY_FORCE_MULTIPLIER.

This mission advances the concrete Chairman/machine journey: one authorized objective -> native teammate recalls canonical WS/DEC/DSC context -> Executive/Fabric executes scoped work -> original-operation evidence and continuity survive handoffs/restarts -> Chairman receives proved results without routine message shuttling or resupplying lost context. New source does not create another company-priority owner or claim AUTONOMY_BASELINE passed.

### Native integration and dependent branches
- Original PR2134 is MERGED as4d1561bcba1bfad583c75e419ced9a6ff0f3fa40. No re-arm or new original operation.
- GitHub automatically retargeted original2170 and2171 to master. Both showed conflicts caused by the older pre-squash common ancestor. Each conflicted file's immediate-parent bytes were independently verified identical to current protected-master bytes. Only the original scoped additions were retained; all other newer protected source/CI/law/memory/OMH/intake changes were preserved.
- PR2170 current head113134217efdb40a1a737a091ad5bf353e25c18c, parents f2a8ae6b5c2a517a882f8001d35e823676bc6ac2 +e37dc82f. Qualified treef0006fd1868ffc528fdddf9bd9758d86adcc1f0e; exact GitHub tree/ref readback. Four-file delta unchanged from qualified feature postimages. Local integration:107 native tests +184 source-identity tests passed. Hosted exact-head CI is rerunning; no new release effect yet.
- PR2171 current head332d20b5bf03e3427a8c16a0fa0ecedf479e9e87, parents7413842fb903d6a0d62d3d29d5af0fe9e73038f7 +e37dc82f. Qualified tree8e2bd3288cad054eda45a35ec3d374b22159bebb; exact tree/ref readback. Six-file own delta unchanged; guard2165 already comes from protected master. Local Linux integration:192 tests +2 subtests passed, including install lifecycle and D8 protected defaults. Original M1 385pass/1platformskip evidence remains historical. Readiness transition is being reconciled; do not invent merge/installation.
- Default branch enforcement freshly read: strict required test, zero mandatory approving reviews, CODEOWNERS reviewfalse, admins enforced; native SQUASH merge queue active, no bypass. No self-approval or direct self-merge occurred.

### Request-observation producer
Original paid Fabric run hermes-native-request-observation-20261107-c3-01 was refused before launch. It was not replayed. Parent implemented the original bounded source task directly.

Draft PR2176:
https://github.com/mastermindx-market-intelligence/Mastermind/pull/2176
branch sol/hermes-request-observation-20261107-c3
head726120186328e9ab8653c35f1de2936242636297
base e37dc82f070fd391e29f0dbd0bf46b022166beea
tree63c09e424ed40b0064d090e8d5a3e0490bd99001, independently matched to local complete Git tree.
13files: two production modules, one test module, one contract document, six unmodified MIT donor source files, one exact executor-method excerpt, provenance and license.

Actual receiving path: original SessionAuthority claim -> actual _execute_claimed -> actual finite/ingress -> original native executor context-copy -> actual request builder and pre-request helper -> original outer pending result -> native compaction/redaction/storage codec. Wrappers call originals once, preserve original failures/cancellation, never synthesize a result or register SessionEvents delivery observers. Final claim/adopted-agent identity checks and attachment use the original stream RLock then the scope lock. Native stored-generation checks remain outside that lock.

Digest stage is assembled_content_after_pre_request_hooks. Presence-sensitive messages/input/system/instructions are detached as bounded strict JSON, UTF8/sortedkeys/no spaces/custom canonicalization. At most8 events/16KiB metadata; content work cap4MiB/65,536nodes/depth64. Raw prompts, outputs, headers, credentials and model labels are not retained. Empty coverage is explicit, late executor contexts are sealed, overflow/errors remain visible. provider_dispatch_proven=false and model_identity_verified=false always.

38 focused source/composition tests passed on the integrated e37dc82f base, including actual native executor, actual claim-owner ordering, cancellation with a surviving thread, successor-claim isolation, interleaved admissions, deterministic adoption race, exactbytes, bounds, original outcome semantics and source qualification. Full local existing runtime suite had327pass/1skip/211subtestpass and6 failures in unchanged loopback/procfs/socket fixtures (two role subcases included). These failures are not waived; hosted Linux CI is required. Original child processes were bounded; a process reconciliation found no remaining test Python process. Restore-only tracked test fixture chmod was verified against exact unchanged bytes.

PR2170 does not yet expose this new outer document. A separate closed authenticated projection is owed before EVAL can consume it. Actual provider dispatch, full request/window inclusion of AgentOS memory, served model identity, real held-out judgments, and EVAL validity remain unproven.

### Adopted Agent OS receiver selected; original worker refusal
Source-linked concrete brief:
https://github.com/mastermindx-market-intelligence/Mastermind/blob/9eb293ca99e01b34b8527c82eac9c1f1bbd65633/research/hermes/HERMES_AGENTOS_ADOPTED_RECEIVER_BRIEF_2026-11-07.md
Exact readback blobdf6fcdfb051f26fcfc6712f2cb3341aa9782a11a.

Use existing InstalledBootPacketCollector + nominal installed-reader issuance + verified Macro private materialization + incumbent CF2 runtime. First leaf reads fixed WS context budget4000 from actual adopted snapshot, preserves rawbytes and complete source/runtime provenance. CODE/DATA/repo revision coincide. No latest-DATA permission is inferred from fresh bundle generation.
Actual fixture already exists at tests/fixtures/agentos-project-plan-owner-contract.json; verified Macro138a2c5cdc391b6319c797d9206bc66faa635cdc, full compiler/helper hashes in brief. Do not substitute a fake emitter or partial compiler entry hash.

Paid Fabric run hermes-agentos-adopted-receiver-20261107-c3-01, controller87331:
REQUEST_REFUSED_BEFORE_LAUNCH, retainedrequesttrue, innerexecutionabsenceproventrue; outer root verificationfalse/request-correlationonly; controllerMMX_FABRIC_EXIT=75/nativewrapperrc0. No result/START/worker/accepted implementation; same-run replayfalse. One original-controller read completed. No replay, no alternate worker or false durable execution. Parent may continue permitted direct source work.

Compatibility decision: same Executive server/process/endpoint will eventually select one fixed v1 or context catalogue from the existing authenticated principal's enrolled mission/profile/grants. Preserve v1 digest/profile material. New explicit grant/profile required; mixed/unknown catalogue association refuses. No second identity/catalogue owner, no union, no silent refresh of native publications. The present receiver leaf adds no public tool, grants, native provider activation or installation.

### Current frontier and preserved blocks
Next: consume exact-head CI/normal releases for2170/2171, qualify2176 hosted runtime checks, implement the bounded adopted receiver directly, then same-owner catalogue/transport/native provider composition and authenticated request-observation projection. Follow with real context inclusion/window/revocation/restart proof and honest EVAL acceptance.

C26 original Ubuntu1 root/admin journal access remains explicitly denied; do not retry by another carrier/account. Original service identity/installation and original Runtime Job must be reconciled on restored authorized access, not replaced. No Secretary/Meta START, model inference, credential-vault enrollment, browser account grant, fleet/endurance or overall teammate completion is claimed. Outcome Learning#398 remains held. M2 OMH and independent ControlRoom/R2 obligations are preserved.


## 24. Adopted Agent OS receiver and original-observation release checkpoint — 2026-11-07 03:55 UTC

Mission remains **BUILT_NOT_PROVEN / MISSION_COMPLETE=false**. Chairman implementation authority continues. Applicable source law remains verified at `e37dc82f070fd391e29f0dbd0bf46b022166beea`; subsequent protected master through `615146aac6a1b0c0933bc9b815517a2fd285ed4a` has no delta in the applicable bootstrap/law paths. AUTONOMY_FORCE_MULTIPLIER mapping remains the concrete canonical-context → scoped Executive/Fabric action → original evidence/continuity journey; no AUTONOMY_BASELINE claim.

### Accepted source carriers reconciled

- PR2170 merged as `9d1558e99615e30a0b4e47404e4b2b2e7c440083`, from repaired head `113134217efdb40a1a737a091ad5bf353e25c18c`. Original terminal metadata is now on protected source. No second release request.
- PR2176 merged as `e63d8acaebe0d3cee1ce7cfb8d85294bf0c57f46`, from `726120186328e9ab8653c35f1de2936242636297`. The earlier preflight AssertionError occurred before any mutation. A later exact-head preflight verified required test success, zero mandatory approvals, no holds, no existing auto/queue entry and the active native queue rule. One request `hermes-observer2176-726120-20261107` returned QUEUED position 1 and matching readback; canonical PR read now proves merge.
- PR2171 retains its original auto-merge request at `332d20b5bf03e3427a8c16a0fa0ecedf479e9e87`; no re-arm, cancellation, replacement or merge claim. Its observed auto-merge metadata says MERGE while the active queue rule says SQUASH; that difference has not been disguised or modified.

### Internal receiver source delivered

PR2178: https://github.com/mastermindx-market-intelligence/Mastermind/pull/2178

Head `fcc92293d6f18246f2b02acf7bf01de0b15d08c2`; local and GitHub tree both `a76f99bde01da447ffcccc0f6fddd1528c4a9e7e`; six scoped files, based on e37. Draft pending hosted checks/integration with evolving protected source.

The receiver uses the incumbent InstalledBootPacketCollector, opaque installed-reader binding, actual private Macro materialization, original Git/source-generation observations, real fixed isolated CLI and existing CF2 runtime attestor. CODE=DATA=adopted Macro snapshot. Active latest-DATA/project-compilation scopes are refused. It preserves all original UTF-8 bundle bytes, including mandatory over-budget content and accounting.

Receipts separately identify the two permitted Macro executable files, complete materialized-input inventory, existing source-generation seals and exact CF2 commitment fields. The closure digest joins those facts; consumers must also validate the separate release and import-policy fields. Generation time does not prove source freshness.

Two concrete provenance defects were closed before publication:

1. Macro's sys.path insertion could expose materialized artifacts to ordinary imports. The fixed child replaces PathFinder with qualified runtime/dependency paths and latches discovery of a prohibited outside-path candidate even if the compiler catches ImportError. Truly absent optional probes remain ordinary misses.
2. -B prevents bytecode writes but permits reads. The child refuses any lstat entry at the actual plan-helper cache_from_source candidate, with sys.pycache_prefix unset and optimization zero. It does not delete or hide selected artifacts. A valid matching-header hostile helper cache is a tested falsifier.

The existing synchronous runtime verifier is checked before/after against the original deadline; late results are refused. Receipt semantics are explicitly `cooperative_result_deadline_v1`, not a hard wall-clock cancellation claim.

### Validation and original labor state

- **282 passed, 7 skipped** in 20.49 seconds on local Linux/Python 3.12.14 across receiver, installed readers/bindings, source materialization and boot-runtime regressions.
- **44 new receiver tests** use actual immutable Macro compiler/helper source at `138a2c5cdc391b6319c797d9206bc66faa635cdc`, real Git, materialization, isolated child and bounded runner. Business records and CF2 host attestation are explicit fixtures, not production custody proof.
- Covers byte preservation, actual helper execution via typed DEC, required-source absence, source/private mutate-and-restore, copied/retargeted readers, output/receipt schemas, qualified dependency shadows, caught artifact imports, valid hostile helper bytecode, first/second attestor overrun, changed runtime commitment, mandatory over-budget context and cleanup uncertainty with no retry.
- Seven unchanged adjacent tests require an actual Macro owner checkout or CF1 interpreter absent here. They remain unproved installed paths.
- Principal read-only judgment found no remaining blocking ownership/import defect in this source slice. No mandatory independent approval was invented.
- Original Fabric receiver run `hermes-agentos-adopted-receiver-20261107-c3-01`, controller87331, remains REQUEST_REFUSED_BEFORE_LAUNCH / EXECUTION_NOT_ELIGIBLE. Inner execution absence is recorded; outer root verification remains false and correlation-only. No START, result, accepted labor or authorized replay. Parent completed the source work directly; unchanged refusal will not be retried as a new carrier.

### Next material work and unchanged gates

1. Integrate/qualify PR2178 against current protected source and move its single carrier through normal delivery.
2. Add a closed authenticated projection of the original outer request observation in native_session_control._read_original. Match original receipt scope; preserve historical instance identity rather than compare to today's runtime. Invalid observation withholds evidence only, preserving native answer/outcome. Current implementation SHA must not be relabeled original producer provenance.
3. Add the same-server authenticated COO/App/Control context read, explicit mission/profile permission, principal-selected compatible catalogue and strict raw-bundle/receipt cross-validation.
4. Enroll the actual Hermes memory loader with per-admission preparation before context compaction; then prove real model-window inclusion/revocation/restart and genuine held-out EVAL through the original admitted operation.

No public context tool, new profile/grant, native memory enrollment, latest-DATA capability, vault/browser credential enrollment, service install, provider dispatch, serving-model identity, valid EVAL or fleet/endurance acceptance is claimed. Original C26 Ubuntu1/root permission denial remains unretried and requires its authorized connection to be restored. Outcome Learning #398 remains held; C69/C70 and prior accepted source remain DO_NOT_REDO. No Slack transport or separate queue/daemon was created.
