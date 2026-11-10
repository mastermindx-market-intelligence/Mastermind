# Mastermind OS — T3 conversations and persistent teammates
## Revision 7 source brief and implementation change order for Fable

**Date:** 10 November 2026 (America/Vancouver).  
**Scope:** Reconcile the current Mastermind OS build, latest masterplan and Paper designs; update the existing Fable programme. This is an architecture and implementation brief, not an installation, runtime admission, migration or product-acceptance receipt.  
**Current user intent:** Make the everyday company harness as simple and responsive as the user's successful T3 Code / DeepSeek Harness experience. Provide persistent teammates, real live conversation, project continuity and company work without exposing the complexity or defects of the Paperclip and Hermes apps.  
**Protected procedure pin:** Mastermind d8240eb033a3025aaa119a61c2adec8fb943b27c; sol skillpack 1.0.1, bootstrap major 1. INDEX and applicable laws were read at this pin.  
**Programme:** Continue the current Fable-led integration and its existing writers. No new programme, executive root, worker assignment or parallel app is created by reading this document.

## 1. Decision

Build **one Mastermind product with a shared T3 conversation experience for Team and Code**. Keep Paperclip's existing company/work records and useful work-management service behind the Mastermind interface. Make Hermes an optional runtime and a compatibility path for existing conversations, instead of a compulsory dependency for every new teammate.

This changes the previous architecture in three material ways:

1. **T3 supplies the actual conversation machinery.** Reuse its connection supervisor, authenticated typed RPC, projections, stream subscriptions, draft and queue behavior, pending requests, tool activity and recovery. Team is a simpler presentation of this shared machinery; Code reveals the full workspace. Copying the composer and drawing chat bubbles over another transport does not meet the decision.
2. **A teammate is stable company identity and continuity with a replaceable runtime/conversation binding.** It is not synonymous with a Hermes profile, one forever-growing T3 thread or a continuously running model loop. Preserve the existing identity owners; bind their references to the selected runtime and native thread.
3. **Paperclip remains useful without becoming the product experience.** The existing installation and newer company/work integration change the premise of Revision 6. Preserve native Paperclip company, project, issue and work-product references; adapt them into Mastermind. Do not introduce a second company task database, or discard the installed records because an older brief called Paperclip a presentation-only donor.

DeepSeek Harness is a preferred runtime candidate because of the user's experience and the existing integration. It is **not yet an unconditional default for this new conversation path**. Stock DSH ACP intentionally excludes raw provider deltas and rich native presentation. The exact installed T3/provider transport must satisfy the required interaction contract, persona isolation, grants and resume semantics. If raw streaming is required, repeating a stock-ACP test cannot remove its documented limitation: use a supported richer DSH integration in the existing provider seam, or an already-qualified provider selected through Capacity. [U1–U5]

This is a targeted correction to the current build. Retain the useful Executive, Capacity, Agent OS, T3 durability, work-management and design work. Redirect composition and default runtime dependence; do not restart the programme.

## 2. What this supersedes and what it preserves

The latest identified saved masterplan is **FABLE_HERMES_MASTER_IMPLEMENTATION_PLAN.md, Revision 6**, file version 5, modified 2026-11-09 05:11:23 UTC. Its 77,792-byte input has SHA-256 ea887b4f6d36606ef494d561dd66dd4baecd975fd511ddf9489db7d7bdcf3bd5. The filename is retained for continuity even though Hermes is no longer the required default. [B1]

A newer local handoff was also found on the authorized M2: **FABLE_Mastermind_T3_Hermes_Handoff_V2.md**, 46,024 bytes, modified 2026-11-09 07:48:23 UTC, SHA-256 e300499768554b0a170dbcd96b00d3f9a1ae8b41757ef00895a32989782a750f. It commissions the existing Fable principal with bounded T3/DSH, Hermes, Executive/Capacity and UI directors. This is a newer implementation brief, not proof of current worker pickup. A local masterplan download named “(6)” contains Revision 5; the suffix is a download copy number. No evidence established that Fable had consumed the saved Revision 6. [B2]

Revision 7 takes precedence over these specific older directions:

| Older direction or finding | Revision 7 disposition |
| --- | --- |
| Hermes must own every persistent teammate and conversation | Superseded for new/default Team conversations. Existing Hermes conversations retain their original owner; Hermes remains a selectable specialist/compatibility runtime. |
| Do not introduce a Paperclip company service | Superseded by the newer explicit company/work integration and installed native records. Keep those records and adapt their API through existing app boundaries. |
| T3 deep-linking is the final Code experience | Superseded by the already-merged full embedded T3 design contract. Deep links remain a transitional or explicit native escape hatch. |
| Repair process-local T3 launch/result maps | Preserve the completed SQLite change and scoped durable canary. Qualify the new composed path; do not repeat the old repair assignment. |
| More HQ screens or a company graph should lead the everyday Team experience | Make exact conversations primary; retain Company, Runtime and observability as secondary/advanced surfaces. |
| DSH's good native UX establishes good T3-over-ACP streaming | Unsupported. Qualify the actual transport; stock ACP's documented limitations are explicit. |

Preserve current source custody, live runs, source-specific holds, original-operation recovery, the existing Fable principal and authorized director scopes. Retain the current model/routing policy; a DSH runtime choice is not a direction to force every worker onto a DeepSeek model. Do not arm timers, move credentials, retry an uncertain effect, mass-import agents or switch existing conversation owners as part of this documentation update.

## 3. Census: source, installed state, design and proof are different

### 3.1 Current source frontier

These are observed immutable references, not permanent assignments. Refresh the affected head at implementation pickup and before changing shared files.

| Surface | Inspected reference | What exists | What remains unproven or missing |
| --- | --- | --- | --- |
| Protected source | d8240eb0; includes merged #2284 HQ build contract and #2345 Team/Code guide | Product contracts, source boundaries and accepted design scope | Merged design and five prepared HQ handoffs are not a running product or five started workers. |
| Main integration #2338, Draft | 957b27602d5a7d07ebf250a4c5c4cd3fadaab4ac | T3/DSH candidates composed into integration; many surfaces present or honestly gated | They are not all merged into master, installed or usable merely because the surface inventory is complete. |
| Current Team/estate work #2424 | 95762fc3700598a7be1a12b8c6c1995753071eed | Company/runtime/conversation shell, graph and return/context integration | TeamShell defaults to Company. Fresh governed T3 launch/acceptance still needs owner-enforced scope and descendant settlement. |
| Paperclip company/work #2395 | 59d8642892663ad863df5bff4dbc6e7cde18e27a | Existing Workspace-auth to request-scoped Paperclip service; native company/work records | Full wake → Executive/Capacity → runtime → same-issue return is not claimed complete. |
| Paperclip–T3 TeamLink #2419 | bf7574e6b2860f84855f031da52cc681cb4522b2 | Exact existing issue/thread binding, queue submission, result/comment and explicit consumption tools | Read-only/native qualification is not real bot consumption; minute-based final-result observation is not live chat streaming. |
| Hermes credential repair #2403 | b2b74c2cde0e68fa6af14e0e6bf28d77dc255bda | Finite invocation credential-custody repair and scoped qualification | No installed activation or original MAS-2 retry was claimed. Remote/background/delegated cases remain refused where unsupported. |
| Capacity #2351 | ecbbbc0563c74db0945972ac4cd4481f0853a55f | Source/UI candidate and explicit source qualification | Installed source selection is still a material boundary; SOURCE_UNAVAILABLE must remain honest. |

The current App.tsx mounts HermesNativePanel as Team's conversationPanel. CodeWorkspace describes a thread list/deep-link and per-attempt view; it explicitly lacks an embedded editor/terminal and says no host yet implements t3ThreadProjection. The Team roster and shell work do not by themselves bind the selected teammate to an exact conversation recipient. These are the principal product composition gaps. [M1–M5]

### 3.2 An important completed repair

The current T3 native composition uses SQLiteT3AdapterStateStore by default. The recorded durable canary at 2026-11-09T14:37:09Z, executed against adapter 128e5e8be5cb4a6ef4c33921c79c82401324e298, records five passing scenarios: crash after persisted receipt, crash after native launch but before receipt persistence with same-principal recovery, different OAuth principal, exact interrupt and lost reply after commit.

That is valuable accepted evidence. It used a fresh scratch SQLite database and the selected M2 T3/Capacity route; it was not a test of the actual Executive database or the new whole-app conversation path. Retain the fix and receipt, then add only the missing composed consumer proof. Do not sum overlapping test counts or turn a historical canary into a blanket production claim. [M6]

### 3.3 Read-only installed census

Observed on authorized M2 during 2026-11-10 approximately 12:09–12:25 UTC:

- Normal T3 Code Beta and a separate queue-stall staged T3 bundle were both running; both report version 0.1.7. A version string is therefore insufficient to identify the selected environment or tested bundle.
- DeepSeek Harness reports 0.2.2-rc.1.
- Hermes health responded HTTP 200, version 0.23.0, installed commit 2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19.
- Paperclip health responded HTTP 200, version 2026.1106.0, installed commit d69631b01b9c658f80bf8bed389863dce82643e1.
- Read-only Paperclip API census returned one accessible active company, MastermindX, with 13 agents. All 13 use hermes_local; 11 report idle, and Secretary plus Meta-CEO report error.
- Seven devices reported online through the remote-device connector: m2studio, m1studio, mini1, ubuntu0-MS-A2, ubuntu1, ubuntu2 and ubuntu3-MS-7E61. Offline/stale connector registrations do not establish host failure or Fabric ineligibility.
- The Executive-state read timed out. This is a transport/read gap, not a fresh denial or evidence that no runtime exists.

No service was restarted, no agent was woken, and no secret value or full adapter configuration was collected. Health and idle status establish reachability/record state, not working chat, streaming, company execution or acceptance. The two error records do not identify a root cause. Preserve live writer and original operation custody. [L1]

### 3.4 Paper design census

Read-only inspection of the existing Mastermind OS Paper file 01M3NRCX55B452A12819WNE1RH found:

- **Team conversations, page p-R-0: 24 boards.**
- **Code workspace, page p-U-0: 17 boards.**

The merged guide's earlier count of 14 Code boards is a historical count; the live page contains newer Long-horizon and task-context/original-room-return boards. The guide also specifies unified settings, state and build handoff pages. Keep that scope; no redesign from zero is necessary. [D1, D2]

Two frames were visually inspected:

- HC04, node 13RP-0: teammate list, exact conversation, working tool activity, queued direction, one composer, files/routines and project context.
- CW02, node 19VK-0: full T3 workbench with the same work/conversation context, terminal and browser surface, queued next turn and return to the originating Team room.

Additional live boards cover independent conversation drafts, exact-message search, Needs you, task dialogue, mobile tabs and attention, session adoption, files/diffs, PR review, linked PRs, context/history and long-horizon plan/acceptance.

These designs already express the desired product. The change is to make their conversation runtime shared and provider-qualified, and remove wording that makes “Team gateway” or “Hermes profile” the required user-facing foundation. Mockup counts and depicted tool/test text are fixtures, not live fleet or acceptance evidence.

## 4. The product the Chairman should experience

### 4.1 Team is the ordinary entry point

The default Team route opens a conversation list and the exact selected conversation. A person chooses Engineering, Secretary or another teammate, sends a message and sees real progress. “Needs you” is a compact filter over real actionable requests. Project, work, files and routines appear in context.

Use the existing TeamShell and navigation. Move Company hierarchy, runtime profiles, credentials, provider settings and detailed observability behind secondary views. Preserve those capabilities; do not ask the user to understand their configuration before having a useful conversation.

A task or result card in chat must open the actual work item or retained output. The task context panel must identify the company project and original conversation. Conversation switching preserves each draft, attachment selection, queue state and scroll position. Multi-conversation UI must not create multiple connections or duplicate prompt submission.

A room needs an explicit recipient or accountable lead for each message. A T3 thread does not automatically implement multi-agent room arbitration. Preserve existing room ownership and add delegated-work visibility before claiming concurrent group-bot behavior.

### 4.2 Code is the full workspace over the same conversation system

Switching Team → Code reveals the native T3 workspace capabilities: conversation/composer, files, terminal, diff, PR and linked-PR review, browser/device surface and side chat where supported by the selected environment.

For an existing coding thread, Team and Code resolve the same environment/thread/run tuple, shared projections and queue. Opening Code must not launch another model or copy the transcript into a second session. If a task deliberately creates a child work thread, make that a linked delegation with the original parent and return target, not an invisible conversation switch.

The existing full embedded design contract remains the target. External/native deep links remain useful while a surface is being integrated, but do not close the embedded-workspace acceptance requirement. [D1, U1]

### 4.3 Work management is available without taking over chat

| User-facing capability | Recommended Mastermind presentation | Authoritative underlying records |
| --- | --- | --- |
| Projects | Goal, team, work, context and retained results | Existing Paperclip project/work records plus links to existing Mastermind project-plan/continuity owners |
| Tasks | Assignment, status, blockers, comments, execution and outputs | Paperclip issue for business work; Executive Job/Attempt/Worker/Event for governed execution |
| Inbox / Needs you | Exact approval, question, failed work, review or decision with a concrete action | The original request/action owner; read and resolved are separate |
| Routines | Simple schedule, target teammate/project, next occurrence and result history | One incumbent trigger owner per routine; company execution admitted through current owners |
| Artifacts / Results | Useful output with preview, version/source, originating work and return context | Native work-product references and original source/storage; no new publication store |
| Dashboard / Today | Work that matters, blocked attention and recent useful results | A projection of qualified existing owners, not another status ledger |
| Workspaces | Clear link between business project and actual selected coding environment | Paperclip project/workspace context mapped to T3 native workspace/thread; no forced one-project/one-repository assumption |

The Paperclip donor value is strongest in these work relationships and recovery semantics. It does not need to supply Mastermind's everyday chrome, live conversation protocol, native Runner, placement broker, secrets system or second admission ledger. Existing Paperclip limits can remain local constraints, but do not become a competing allocator for company-wide Capacity reservations.

## 5. Ownership and integration contract

### 5.1 One owner for each kind of truth

| Concern | Owner / rule |
| --- | --- |
| Existing company/agent identity, business relationships and project/issue records | Existing Paperclip service and its native IDs, through the current Workspace/company integration |
| Charter, organizational continuity, retained project plans/context and cross-system references | Existing Agent OS and source-backed owners; preserve their identifiers and bindings |
| Company execution, admission and acceptance lineage | Executive OS; do not infer authority from a roster entry, prompt, skill or provider UI |
| Placement, runtime identity, quotas and reservations | Existing Capacity Fabric / RuntimeBinding; no T3 client-side load balancing that silently overrides selected placement |
| Live T3 conversation, messages, queues, pending native requests and thread projection | Selected T3 environment and its shared client runtime |
| Existing Hermes conversation, memory/profile and session persistence | Original Hermes gateway/profile owner until an explicit settled cutover |
| Routine firing | Exactly one recorded incumbent scheduler for that routine |
| Source/PR/CI/release evidence | GitHub and actual repository controls |
| Retained artifact bytes and publication | Existing canonical storage/source owner; Paperclip/Mastermind index references |
| Final business completion | Designated result/acceptance owner, after actual result return and consumption where required |

This resolves the newer Paperclip company/work candidate against the older presentation-only HQ wording. The installed records are preserved; Revision 7 does not claim that every candidate service or wake path is already deployed. The governing source and current Chairman intent still constrain execution. [M3, M7]

### 5.2 Persistent teammate binding

Extend the existing actor/runtime binding and company adapter; do not create an independent agent registry. Resolve these existing references as one qualified binding:

- Stable company actor/teammate reference, corresponding Paperclip agent reference where applicable, and current charter/persona revision.
- Existing Agent OS continuity/project references and authorized context scope.
- Selected runtime/provider profile, exact environment and admitted tools/grants.
- A **replaceable primary conversation pointer**, plus explicit task/work-thread bindings.
- Native conversation identity, original parent/result target and applicable execution references.
- Capability and qualification state for the selected version/transport.

Thread archive, context rotation, provider migration or environment replacement must not delete the teammate, its routines, project ownership or continuity. Replacement of a primary pointer is an explicit versioned binding change after live effects settle or are reconciled. A conversation transcript is not automatically a teammate's entire memory.

Use exact existing actor IDs or separately authorized new IDs for qualification; a new thread/runtime does not create a duplicate company teammate. Retain OMH or native memory custody wherever it is currently assigned. After a settled thread rotation, prove that the same actor retrieves an authorized retained memory/context item and that another actor cannot retrieve private material outside its scope. A T3 transcript or Agent OS project pointer is not a complete memory migration.

A persona must be applied in the actual runtime configuration, not merely displayed in a title or inserted into the first user message. Verify effective instructions, admitted tools and resume behavior for two deliberately distinguishable teammates. Configuration changes affecting a live run are versioned and applied at a defined boundary.

### 5.3 The missing company-actor dispatch and authentication join

All 13 installed company agents still dispatch through hermes_local. Current TeamLink attention invokes the original Paperclip agent; consumption acknowledgment requires that recipient's authenticated run. A T3 conversation pointer alone neither changes this wake owner nor grants authority to check out/update the issue or acknowledge its result.

Implement and qualify this join in the existing Paperclip adapter/RuntimeBinding seam, reusing a supported native adapter or supported externally owned runtime binding if available. Preserve the same company/agent ID. Route unattended work through existing Executive admission and Capacity placement before the selected runtime acts. Prove authenticated issue checkout/task operations, original-recipient acknowledgment and same-parent return through the selected runtime. Use the existing credential issuer/custody owner; neither browser credentials nor the finite Hermes credentials from #2403 become T3 authority by association.

Cut over one actor at a time under the actual configuration writer's custody, with old dispatch/wake ownership fenced and outstanding effects settled or reconciled. The pinned general Paperclip agent PATCH has no expected-revision/CAS field: do not invent If-Match support or treat a preflight digest as concurrency enforcement. Keep the actor paused with its old heartbeat disabled during an authorized adoption, use actual owner-enforced conditional mutation where supported, and enable the successor only after binding/auth/return proof. This is future implementation work, not a cutover authorized or performed by this assessment.

Until that path qualifies, the shared T3 Team surface is a human conversation with linked company work; it is not yet a fully Hermes-independent always-on company agent. No additional scheduler, credential relay, dispatcher or agent registry is introduced. [M3, M4]

### 5.4 Shared T3 integration, not a new chat engine

The upstream client-runtime is a private workspace package, not a standalone public “drop-in chat widget.” ChatView depends on routing, settings, drafts, projections, provider capabilities and native workspace services. Start by bringing a coherent T3 conversation/client feature area into the existing Mastermind composition and supplying the existing host/auth/navigation adapters. Preserve one connection supervisor per environment and the existing shared thread state. [U1, U2]

The implementation choice is falsifiable: if extracting a small component requires rebuilding T3's transport, queue, request, replay or projection logic, import a larger coherent feature area or use a thin maintained T3 client fork integrated with Mastermind navigation. Do not quietly substitute a homegrown chat engine. This fallback does not change backend authority or authorize deploying a second customer-facing application.

MCP automation credentials are not human Workspace HTTP/WebSocket authentication. Use the current authenticated app boundary and exact environment credentials/capabilities. T3's outgoing company tools and external-agent MCP can support task operations, while native typed RPC/subscriptions supply human interaction. Do not poll MCP for the user's token stream.

Shared client connection recovery does not automatically retry mutations. Preserve operation identity and the incumbent operation-specific reconciliation rules.

### 5.5 Live conversation and work return are separate channels

The current TeamLink plugin binds an existing Paperclip issue to an existing T3 root, sends queue-mode work using stable operation IDs, observes native completion, publishes an issue result and requires explicit consumer acknowledgment. Its scheduler scans each minute. That is a useful durable work-return path.

It is not a live chat transport. Use T3's native stream/projection for ongoing conversation and tool progress. Keep the existing TeamLink observer as the owner of its return/cursor semantics; do not start a second watcher to race it. Link the eventual task result and artifact into the original conversation and company work item. Native completion, delivered comment, parent consumption and business acceptance remain separate states. [M4]

### 5.6 “Always on” means durable availability and owned wakeups

A teammate remains discoverable and retains its identity, context references and work obligations when no model process is active. Human input, an admitted work assignment, a result needing attention or a routine occurrence can wake its selected runtime through the existing owners.

The browser must not be the daemon. Do not run a permanent reasoning loop for every idle teammate. Use the existing installed runtime/service lifecycle and one incumbent scheduler/trigger owner. Closing the browser must not lose committed work or require it to keep a timer alive.

T3 already has native schedules. Their dispatch status can report success after launch/send; that is not completion of the model's work. Paperclip routines and any existing Hermes cron retain their owner until explicit per-routine cutover. A new company routine can use the existing Paperclip scheduler only after its admission, occurrence and return path is qualified; do not also create a T3/Hermes timer for the same occurrence. [U6, M3]

## 6. Runtime choices and specific traps

### 6.1 Keep Hermes selectively; stop making its app the foundation

Current upstream documentation makes the profile gateway the canonical session writer for CLI, TUI, Desktop, API, ACP, cron and other clients. Normal CLI dispatch also uses the gateway. Replacing the Hermes app with ACP/CLI therefore does not automatically avoid the gateway problems the user experienced. [U3]

Hermes can remain valuable for existing conversations, specialist tools, memory integrations and channel-specific capabilities that actually qualify. Keep those native sessions on their owner. Directly embedding the lower-level agent loop is possible in source, but it is a separate lifecycle/persistence/approval/recovery integration, not an already-supported shortcut around the gateway. Do not put a new Hermes-core wrapper on the critical path for the new Team experience.

The candidate finite credential repair and its original operation have their own custody. A new UI is not authorization to rerun the original operation through another provider, copy temporary credentials into a new channel, or extend a finite-only fix into remote/background cases.

### 6.2 Make DSH a qualified runtime, not a brand assumption

Upstream DSH ACP describes itself as automation-only. It sends committed assistant messages/thoughts and generic tool lifecycle updates, deliberately excluding raw provider deltas, native presentation cards, plans, terminal views and elicitation. This is not the same interface as the smooth DSH native app. [U4]

For a candidate using ACP, profile composition and grants need special attention:

- A qualified named deployment profile can include ACP and the intended persona prefix/suffix while preserving harness/runtime guidance.
- ACP session creation does not automatically apply the native persona preset composition. A persona preset name alone is insufficient.
- Use the existing admitted-tool integration; persona text is not enforcement.
- Isolate teammate state/profile configuration where the chosen server shares globals. Prove that two teammates cannot inherit each other's private state, credentials or grants.
- Do not use a complete-prompt replacement merely to set a persona; that can discard the harness context/tool guidance.
- Separate harness selection from model/provider selection and retain centralized Capacity policy.

Qualification must name the exact installed source, transport, profile and grant combination. If the hard requirement is live raw text deltas, stock ACP is already known not to satisfy it; choose the richer supported seam or a qualified alternate provider. Do not simulate streaming by slowly revealing a completed buffered response. [U4, U5]

### 6.3 Do not confuse a usable T3 interface with governed execution

T3's UI quality and durable native threads are strong reasons to adopt its conversation experience. They do not by themselves establish Mastermind admission, scope attenuation, child settlement, provider account custody or fleet eligibility.

The current estate integration explicitly keeps fresh governed T3 launch/acceptance unavailable until owner-enforced scope and descendant settlement exist. Retain the existing selected-child/Control/workspace/WorkerBroker path for admitted coding leaves while that boundary remains. Native observation, exact existing-thread inspection and original-operation recovery are separate capabilities. Do not enable a launch button merely because the UI can call it. [M5]

## 7. Fable change order: preserve work and redirect the critical path

### 7.1 Keep / change / sequence

**Keep:** #2338 integration custody; SQLite T3 durability and its evidence; DSH source integration; Capacity and fleet selection; Agent OS continuity; current company/work APIs; TeamLink binding/return semantics; accepted Paper navigation, settings and full embedded Code scope; exact auth, source and release holds.

**Change now in the implementation plan:** Team defaults to conversation; replace compulsory HermesNativePanel composition with a runtime-qualified shared T3 conversation path for new/default teammates; bind the selected actor to the exact conversation; treat the existing Hermes panel as compatibility; qualify DSH transport before defaulting it; make work cards contextual; remove obsolete “repair dict persistence” work.

**Sequence after the first usable conversation:** broader company graph, observatory polish, mass teammate migration, autonomous multi-agent room arbitration and additional dashboards. Existing authorized independent work may continue without collision. These features are retained in scope, but do not block the first useful integrated teammate.

### 7.2 Reuse existing director scopes

| Existing scope | Revision 7 assignment | First concrete proof |
| --- | --- | --- |
| Fable principal / shared app integration | Reconcile exact active heads, release holds and shared-file writer; compose the single user journey | One source/installation map and a real Team → Code → same result journey |
| T3 + DSH director | Shared conversation/client area, exact environment/thread binding, provider/persona/grant qualification | Two distinguishable teammates; true event behavior; resume without duplicate execution |
| Hermes director | Preserve legacy sessions, finite custody repair and specialist runtime compatibility; support explicit handoff | Existing Hermes work remains on its owner; a new default teammate does not duplicate its wake/response |
| Executive / Capacity / fleet director | Existing auth/admission/runtime-binding and descendant-settlement contracts; company-actor runtime dispatch/authentication and original-operation recovery | No UI, automation or provider-switch bypass; exact selected actor/runtime, authenticated checkout/ack and result lineage |
| App/UI director | Conversation-first TeamShell, full embedded Code, contextual Work/Needs you/Results/Routines | Exact recipient, independent drafts, working streams, actionable requests and return navigation |

These are updates to the existing commission, not new worker starts or a claim that every director is currently active. Before touching shared App.tsx, host/auth contracts, root package/lockfiles, app routing/theme or integration selection, reconcile the current writer. No separate director creates a second shared composition branch.

### 7.3 Implementation sequence

**R7-A — Reconcile and freeze the binding contract.** Preserve live effects and accepted proof. Record current installed environment versus candidate source, the exact existing company/actor/project references, primary/work thread bindings, routine owner and unsupported capabilities. Include the current runtime selection, fresh-governed-T3 boundary and the company-actor dispatch/authentication join in §5.3. Finish this as part of the current programme, not a new census platform.

**R7-B — One real shared conversation.** Integrate the coherent T3 client area under the existing app auth/shell. Establish one actual teammate with a qualified provider. Show real text/tool events, queue and pending requests. Switch Team/Code and reconnect without changing the operation or creating another provider session. Do not wait for HQ graph polish.

**R7-C — Two teammates, actor dispatch and continuity.** Use exact existing or separately authorized actor IDs. Apply distinct real persona/tool profiles, qualify the company actor's dispatch/authenticated checkout/ack/return path and fence any former wake owner. Prove fresh session, resume and controlled profile revision; preserve independent drafts. Rotate one settled primary conversation pointer without deleting teammate identity or project obligations, and retrieve scoped durable memory through its existing owner. Keep a legacy Hermes conversation independently usable. A UI-only conversation does not close the always-on teammate requirement.

**R7-D — One project/work/result loop.** Select a real existing project and issue, perform one admitted bounded task, open the associated Code workspace where applicable, retain an actual useful output, publish it to the same work record and originating conversation, and observe the designated parent consume it. Use the existing authorized execution lane until any new native launch lane is qualified.

**R7-E — One routine and actionable attention.** Qualify one trigger owner, occurrence and return. Close the browser, recover at a known interruption boundary and prove one result. Exercise a real approval/question/review action through its owner. Dispatch acknowledgment must not prematurely complete the company task.

**R7-F — Finish breadth and qualify release.** Complete the already-accepted full Code/settings/device/mobile surfaces and relevant work-management views. Measure interaction behavior, run affected checks and actual repository gates, and perform installed browser/product proof on the exact selected source. Broaden migration only after the integrated slice passes.

Do not invent a full-build duration. The first integrated slice is the scheduling unit; scope expansion follows observed dependencies and performance, not another promise that all donor integration fits one day.

## 8. Acceptance: the product has to work, not only exist in source

The decisive package is **two teammates, one project, one real task, one retained artifact, one routine and one actual attention action**, exercised through the real app and selected runtime.

| Scenario | Required evidence |
| --- | --- |
| Shared Team/Code conversation | Same environment/thread/run identity, one queue/request owner, no extra model run on navigation |
| True streaming | Actual event type/timestamps through the selected provider path; no fake typing over a buffered final response; tool activity remains responsive |
| Two personas and grants | Effective runtime configuration, isolated authorized context/tools, correct fresh and resumed behavior |
| Reconnect/restart | Original operation and projection cursor recovered; no duplicate submission; unknown effects stay unknown until reconciled |
| Approval and stop | Exact pending request survives navigation; disconnect does not approve; stop requested differs from confirmed settlement |
| Company actor wake and authentication | Same native actor ID, one dispatch owner, admitted selected runtime, authentic issue checkout/comment/ack and same-parent return; no borrowed finite Hermes credentials |
| Company work and artifact | Same project/issue, real admitted attempt, usable output, correct return target and explicit parent consumption/acceptance where required |
| Routine | One trigger/occurrence owner, browser-independent wake, no duplicate firing after recovery, result-based completion |
| Legacy coexistence | Existing Hermes conversation retains native owner; no event wakes both old and new bindings |
| Thread replacement and memory | Teammate identity, continuity, work and routine obligations survive primary-thread rotation; authorized retained memory is retrievable through its existing owner and private context remains isolated |
| Full Code experience | Files, terminal, diffs/PRs, browser/device and side-chat capabilities work where qualified; unsupported capabilities are labeled accurately |
| Practical UX | Teammate selection always addresses the displayed recipient; independent drafts remain; Needs you actions resolve via the owner; returning from Code preserves context |

Keep the existing proposed interaction targets—typing responsiveness and warm surface reveal—as engineering targets to measure, not already-achieved benchmarks. Separate UI responsiveness, acknowledgment latency, first meaningful model output and total task duration. A fast composer does not establish fast model execution.

Reuse accepted exact-head tests and the scoped durable canary. Add focused integration/fault checks only for the new binding, shared connection, persona, stream and return boundaries. Green CI, healthy ports, rendered mockups, read-only MCP or successful queue dispatch do not close consumer acceptance.

## 9. Migration and maintenance

Use **new work first**. Existing Hermes sessions, Paperclip issues, T3 roots and routines stay bound to their original owners. The user can continue original conversations while new qualified Team conversations use the new default. Do not mirror live prompts into two runtimes.

A migration requires a settled/reconciled old operation, explicit target binding, authorized portable context references, one trigger/channel owner and an observable return path. Do not copy internal session databases into another runtime or imply exact native resume from an imported transcript. Preserve the old conversation as history when a new primary pointer is created.

Pin donor source and record copied versus adapted code, owning files, license/notice obligations and focused proof in the existing repository. The inspected [T3 license](https://github.com/pingdotgg/t3code/blob/d1aeed249288585390dbac4fde5b54c35bd5fc06/LICENSE) and [Paperclip license](https://github.com/paperclipai/paperclip/blob/d69631b01b9c658f80bf8bed389863dce82643e1/LICENSE) are MIT; preserve their required notices and review third-party assets separately. The prior upstream Paperclip assessment remains useful for behavior cataloging, but the installed/current integration pin governs exact adapter claims. Do not auto-ingest latest upstream or create an independent compatibility platform.

The lower-risk extraction boundary is original API adapters plus a coherent T3 client area. If maintaining a deeply split client costs more than a thin T3 client fork, choose the latter deliberately under the same product and authority contracts.

## 10. Delivery and remaining boundaries

This brief supports an updated Revision 7 masterplan and a short Fable change order. It does not assert that Fable has received, started or accepted them. The active commission and current source writers retain execution custody.

The assessment performed read-only installed/design/source inspection and documentation work. It did not deploy, enable a profile/plugin, wake a bot, change a timer, import agents, migrate credentials or retry a live operation. The Executive read timeout leaves current runtime state incompletely observed; it does not block this source/plan correction.

At implementation pickup, Fable should apply R7-A and start the shared conversation slice in its existing programme. The next report should show the exact source and selected installed environment, what one user can now do, actual event behavior, and the remaining consumer-proof boundary. More screen inventory is not the primary success measure.

## Evidence and reproducibility

### Baselines

- **[B1]** [Existing masterplan identity](https://chatgpt.com/library?file_id=libfile_2f67c0d2889c819180139e14f6ec92ee&account_id=personal), input Revision 6/version 5 with hash recorded above; previous [Revision 6 source](https://github.com/mastermindx-market-intelligence/Mastermind/blob/8dbf89bdbd33968e59b2c88714d5468881bcb5e6/docs/plans/2026-11-08-paperclip-donor-reconciliation.md), [PR #2359](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2359). Its head had changed to 80112000e1393039bdddb0b562e43f7bdd6691ba; this change order does not overwrite that branch.
- **[B2]** Authorized M2 read of /Users/chriswong/Downloads/FABLE_Mastermind_T3_Hermes_Handoff_V2.md, immutable input hash above. Companion CURRENT_STATE_AUDIT_T3_HERMES_MASTERMIND_2026-11-08.md: 31,977 bytes, SHA-256 299672c47bc58cd39d9ff57f6dc4410b6a406dbf6ebea478a1b822649354d3e1. Old audit findings were refreshed where they affected the decision.

### Mastermind source

- **[M1]** [App composition at #2338](https://github.com/mastermindx-market-intelligence/Mastermind/blob/957b27602d5a7d07ebf250a4c5c4cd3fadaab4ac/app/mastermind_os/src/App.tsx); [CodeWorkspace](https://github.com/mastermindx-market-intelligence/Mastermind/blob/957b27602d5a7d07ebf250a4c5c4cd3fadaab4ac/app/mastermind_os/src/code/CodeWorkspace.tsx).
- **[M2]** [TeamShell at #2424](https://github.com/mastermindx-market-intelligence/Mastermind/blob/95762fc3700598a7be1a12b8c6c1995753071eed/app/mastermind_os/src/team/TeamShell.tsx); [integration PR #2338](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2338).
- **[M3]** [Paperclip continuous-team architecture, #2395](https://github.com/mastermindx-market-intelligence/Mastermind/blob/59d8642892663ad863df5bff4dbc6e7cde18e27a/docs/architecture/PAPERCLIP_CONTINUOUS_TEAM.md); [fleet-readiness record](https://github.com/mastermindx-market-intelligence/Mastermind/blob/d8240eb033a3025aaa119a61c2adec8fb943b27c/docs/superpowers/plans/2026-11-09-paperclip-fleet-readiness.md).
- **[M4]** [TeamLink implementation contract, #2419](https://github.com/mastermindx-market-intelligence/Mastermind/blob/bf7574e6b2860f84855f031da52cc681cb4522b2/integrations/paperclip_teamlink/README.md).
- **[M5]** [Estate integration and governed-T3 boundary](https://github.com/mastermindx-market-intelligence/Mastermind/blob/95762fc3700598a7be1a12b8c6c1995753071eed/docs/ESTATE_GRAPH_INTEGRATION_PLAN.md); [Hermes finite custody repair #2403](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2403); [Capacity #2351](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2351).
- **[M6]** [T3 native composition](https://github.com/mastermindx-market-intelligence/Mastermind/blob/957b27602d5a7d07ebf250a4c5c4cd3fadaab4ac/control_plane/t3_native_composition.py); [durable canary receipt](https://github.com/mastermindx-market-intelligence/Mastermind/blob/957b27602d5a7d07ebf250a4c5c4cd3fadaab4ac/integrations/t3/live_proof/t3_durable_canary_receipt_r2.json).
- **[M7]** [Protected HQ build package](https://github.com/mastermindx-market-intelligence/Mastermind/blob/d8240eb033a3025aaa119a61c2adec8fb943b27c/docs/superpowers/plans/2026-11-08-unified-hq-build/README.md), including its explicit NOT COMPLETE/prepared-assignment boundary.

### Design and installed observation

- **[D1]** [Merged Team/full-T3 implementation guide, especially §18](https://github.com/mastermindx-market-intelligence/Mastermind/blob/d8240eb033a3025aaa119a61c2adec8fb943b27c/docs/plans/2026-11-08-mmos-team-delivery-integration.md).
- **[D2]** Authorized read-only Paper inspection on 2026-11-10: file 01M3NRCX55B452A12819WNE1RH, p-R-0/24 boards and p-U-0/17 boards; visual inspection HC04/13RP-0 and CW02/19VK-0. No design edits or production claims.
- **[L1]** Authorized M2 read-only process/version, health and company/agent API observations described in §3.3. API shapes verified against [Paperclip agents API at installed pin](https://github.com/paperclipai/paperclip/blob/d69631b01b9c658f80bf8bed389863dce82643e1/ui/src/api/agents.ts) and [companies API](https://github.com/paperclipai/paperclip/blob/d69631b01b9c658f80bf8bed389863dce82643e1/ui/src/api/companies.ts). Only safe identity/status/count fields were retained.

### Upstream primary sources

- **[U1]** T3 d1aeed249288585390dbac4fde5b54c35bd5fc06: [connection runtime](https://github.com/pingdotgg/t3code/blob/d1aeed249288585390dbac4fde5b54c35bd5fc06/docs/internals/connection-runtime.md), [composer](https://github.com/pingdotgg/t3code/blob/d1aeed249288585390dbac4fde5b54c35bd5fc06/docs/user/composer.md), [provider capabilities](https://github.com/pingdotgg/t3code/blob/d1aeed249288585390dbac4fde5b54c35bd5fc06/docs/orchestration-v2/provider-capability-system.md).
- **[U2]** Same T3 pin: [private client-runtime package](https://github.com/pingdotgg/t3code/blob/d1aeed249288585390dbac4fde5b54c35bd5fc06/packages/client-runtime/package.json), [ChatView](https://github.com/pingdotgg/t3code/blob/d1aeed249288585390dbac4fde5b54c35bd5fc06/apps/web/src/components/ChatView.tsx), [outside-agent interface](https://github.com/pingdotgg/t3code/blob/d1aeed249288585390dbac4fde5b54c35bd5fc06/docs/user/outside-agents.md). License and third-party notices remain part of any source adoption.
- **[U3]** Hermes da0b8208fa7fc61ad1f40c1398a14fbf649442b6: [gateway-backed CLI](https://github.com/NousResearch/hermes-agent/blob/da0b8208fa7fc61ad1f40c1398a14fbf649442b6/website/docs/developer-guide/gateway-classic-cli.md), [session storage](https://github.com/NousResearch/hermes-agent/blob/da0b8208fa7fc61ad1f40c1398a14fbf649442b6/website/docs/developer-guide/session-storage.md), [ACP gateway ownership](https://github.com/NousResearch/hermes-agent/blob/da0b8208fa7fc61ad1f40c1398a14fbf649442b6/acp_adapter/server.py). This upstream pin differs from the installed health-reported pin.
- **[U4]** DSH fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159: [ACP contract and limitations](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/acp/acp/README.md), [ACP session creation](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/acp/acp/src/index.ts).
- **[U5]** Same DSH pin: [system-prompt/persona composition](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/packages/core/system-prompt/README.md), [CLI profiles](https://github.com/deepseek-ai/deepseek-harness/blob/fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159/apps/cli/README.md); Mastermind [admitted DSH tool profile](https://github.com/mastermindx-market-intelligence/Mastermind/blob/957b27602d5a7d07ebf250a4c5c4cd3fadaab4ac/integrations/acp_worker/dsh_tool_profile.mjs).
- **[U6]** T3 [ScheduledTaskService](https://github.com/pingdotgg/t3code/blob/d1aeed249288585390dbac4fde5b54c35bd5fc06/apps/server/src/scheduledTasks/ScheduledTaskService.ts), [schedule contract](https://github.com/pingdotgg/t3code/blob/d1aeed249288585390dbac4fde5b54c35bd5fc06/packages/contracts/src/scheduledTask.ts).
