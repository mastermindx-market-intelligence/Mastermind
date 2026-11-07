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
