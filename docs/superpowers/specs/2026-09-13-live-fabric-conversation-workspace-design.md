# Live Fabric — conversation-first autonomous workspace

**Parent:** WS:CHAIRMAN-CONTROL-ROOM / project-active-build-control  
**Carrier:** Mastermind PR #595  
**Operation:** `mastermind-live-fabric-conversation-design-20260913-sol-001`  
**Source/procedure:** Mastermind `f087f9cf90a8fc7a81273c2576eefa6d06b54d9e`, Skillpack 1.0.1 / bootstrap 1  
**State:** written design candidate / SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT.

## 1. Correct the center of the product

The Chairman's latest correction is not a request for more dashboard widgets. The product must be a usable conversation workspace for an autonomous company. Chris can speak to the CEO, read an orchestrator's complete available conversation, follow a child into its own conversation, inspect tools and artifacts, and compare connected sessions without becoming the person who keeps work moving.

The previous dynamic mission room demonstrated useful state transitions, but still gave the topology and technical status too much space. This specification changes the default working layout from **graph plus small transcript panel** to **full conversation plus optional context**. The graph remains important; it is no longer the compulsory center of every screen.

This document narrowly supersedes the default layout, conversation contract and first-slice proof in the September 13 dynamic addendum/masterplan/storyboard. Existing identity, authority, privacy, source ownership, effect reconciliation, remote topology and production-proof boundaries remain. It does not authorize a new runtime, provider, deployment, budget or final CEO model. The companion connected-suite contract map identifies actual source owners and incomplete interfaces instead of using the phrase 'existing system' as a substitute for integration design.

### Three primary jobs

**Understand:** Open the company, know what needs attention, find a mission and read the actual conversation doing the work. Reading an older message must not lose the current result or move the viewport.

**Communicate:** Ask the CEO a question or message an exact orchestrator/worker. The composer makes the recipient and delivery behavior clear without requiring a technical modal for every ordinary in-envelope sentence.

**Investigate or intervene:** Follow an inline delegation, reveal the waiting chain, compare two conversations, inspect the exact file/artifact, examine routing or perform a separately supported stop/interrupt/reconciliation action. These are contextual operations, not an always-visible wall of controls.

The machine job is unchanged: existing deterministic owners retain responsibilities, admit work, handle returns, wake the appropriate reasoning target and preserve useful continuation while every viewer is closed. Conversation visibility neither implements nor substitutes for that closed loop.

## 2. The information architecture

One product contains **Today**, **Conversations**, and **Work & outcomes**. Today remains the decision-first brief. Conversations is a first-class working surface, not an Advanced debug tab. The product may restore the last selected workspace as a presentation preference; this does not change the accepted priority or runtime.

### Conversation sidebar

Use one sidebar, not a navigation rail followed by another wide mission rail. It contains a pinned CEO office, mission-grouped conversations and optional participants. Sessions are titled primarily by the job they perform: 'API implementation', 'Interface implementation', 'Research & sources'. Provider/model information is subordinate and never the organizational identity.

Show unread user-facing content separately from work state. A new message does not necessarily require Chris. A waiting worker does not necessarily need Chris. 'Needs you' is derived from the appropriate attention owner, not from an arbitrary unread counter. Search operates over authorized inventory and retained content; incomplete indexing is disclosed. Names and titles help navigation but never establish the target binding.

An optional Workspace adviser appears as a distinct conversation/run surface under its relevant scope, not as an obligatory manager inserted above all workers. Archived or unavailable sessions remain discoverable to their authorized retention ceiling; they do not disappear merely because their process ended.

### Full conversation

The default view contains a compact identity header, a readable message column, inline delegated-work/artifact cards and a persistent composer. It does not surround every assistant response with a large metric tile. Use ordinary language in primary copy; put exact Job/Attempt/binding/source details behind Context.

The reference desktop is 1600 by 1040 with a 264-pixel sidebar. Main message text is 16 pixels with approximately 25-pixel line height; the reading column is centered within the remaining workspace and bounded rather than stretched across an ultrawide screen. These are initial design tokens, not substitutes for browser text-scaling and actual usability qualification.

Long conversations scroll within a reading area while the header and composer remain accessible. Selecting text, opening code, expanding a tool result or reading earlier history must not trigger auto-scroll. 'Follow latest' resumes tailing explicitly. Tool-call groups start collapsed when they would otherwise overwhelm the conversation, but exact available content is one expansion away. Compaction boundaries, missing ranges and filtered content remain visible without replacing the history with an unexplained summary.

### Three distinct ways to see several sessions

1. **Source conversation:** one actual conversation, preserving speaker, turn, item and content-block identity. This is the normal chat view.
2. **Mission activity:** a federated feed of messages, returns, artifacts and receipts from several sources. It explicitly names origin and recipient and does not pretend that the participants shared one provider conversation.
3. **Paired conversations:** two independently bound reading panes. Each retains its own scroll position, capabilities and composer recipient. Selection in one pane does not forward text or change the other's target.

Provider-native regeneration branches and organizational child Jobs are different structures. A chat branch picker must not be reused as the company's delegation hierarchy, and a child worker must not be treated as an alternative answer in the parent's model conversation.

### Context, not permanent clutter

Context explains the selected conversation's mission, accountability, exact current target, current result, evidence, granted tools, data access and route. Connections reveals the relevant authority/delegation/wait/result graph. Routing opens from the selected assignment and distinguishes a recorded route from a hypothetical policy change. Files and diffs appear only through their qualified project/artifact owners.

An initial view should answer 'Who am I reading?', 'What are they working on?', 'What changed?', and 'Who receives my message?' without showing raw hashes. A deep investigation must be able to recover the exact evidence, not stop at a friendly summary.

## 3. A concrete backend gap, not just a missing component

The earlier claim that the existing rich adapter was a nearly ready live-content producer was too optimistic. Inspection at the exact source above establishes three narrower facts in `control_plane/codex_operator_adapter.py`, blob `1351ef00da5ae97b0b87b34e6c5883f2dfbfc4ea`:

- `read_events` in the inspected lines 2788-2843 waits for `turn/completed` before draining and ingesting notifications when the selected turn has not completed. A method named `read_events` is therefore not, by itself, the continuous spectator feed the UI requires.
- `_ingest_turn_notifications`, inspected in lines 2105-2272, begins with `safe_payload = {"method": method}` and adds selected helper metadata. Its normalized event payload does not project ordinary response text as a complete live conversation.
- `collect_candidate_result`, inspected in lines 2855-2910, reduces a final text to a redacted summary bounded to 4000 characters. This is a candidate-result summary, not complete session history.

These statements concern this inspected path, not every possible installed provider lane. They establish that D1 cannot be delivered by connecting a React chat widget directly to that current metadata projection. They do not justify removing redaction, exposing the private raw-role-result seam, or starting a second provider process to obtain text.

The required owner extension has two separately useful read capabilities: **safe content while a managed turn is still running**, and **paged available conversation history with explicit completeness**. Both must preserve the primary controller's stream ownership and effect behavior.

## 4. The connected domain model

The application displays references among existing objects, rather than inventing an all-purpose 'agent' row:

- strategic objective and accepted delegation envelope;
- durable responsibility/role and workstream;
- admitted Job and Attempt;
- current session epoch, process generation and exact provider session;
- turn, provider item and content block;
- canonical company message/return/obligation;
- artifact version, source file or review;
- logical route decision, capacity claim and host qualification;
- authenticated viewer and permitted resource scope.

A UI selection binds a finite source-qualified tuple of these references. It is a derived read context, not a new identity registry. Missing joins remain absent. Provider titles, model names, timestamps, window order and observed activity cannot fill them.

Source presentation and command targeting use different predicates. Several qualified conversations may be readable while only one target is currently action-authoritative for a given obligation. A viewer can inspect a historical session without making it current. A role can be durable while its current implementation is absent.

The source cursor belongs to its source and epoch. A client publication sequence only orders UI delivery inside that subscription. It cannot replace the Executive event identity, provider item ID or dialogue obligation identity. Completed source blocks are deduplicated within the exact conversation/generation/item/block scope; adjacent assistant messages from different speakers are never merged merely because their role string is 'assistant'.

## 5. Continuous content without a second transcript system

### Primary ingestion and observer fan-out

The existing provider/adapter owner retains the one authoritative parser and controller connection. It processes provider events needed for safety, results and lifecycle first. A separately qualified observer projection receives permissible visible content from that owner before the entire turn terminates. Spectators do not drain the primary notification queue or independently advance its controller cursor.

Per-view bounded buffers, cached pages and layout state are replaceable presentation mechanisms. They are not another durable event bus, session manager or retry system. A slow or disconnected browser cannot block terminal-result handling or owner continuation. Backpressure coalesces display updates or requires resynchronization; it cannot discard a canonical return or acknowledge an obligation.

A content stream must be tested with actual text arriving while the source turn is demonstrably nonterminal. Merely streaming a collected response after completion does not pass the live-content requirement. Provider timestamps, actual observation time, gateway publication time and rendered time are separate measurements.

### History and retention

'Full conversation' means all authorized retained content available from the qualified source for that conversation, not unbounded access to every account or a promise that a provider exposes private internal reasoning. The view states whether it is live plus history, completed-items only, partial history, summary only, linked-native only, status only or unavailable.

The preferred source is the provider's existing qualified history interface and the existing company's message/artifact owners. If a required retired-session history cannot survive in those owners, the implementation must propose an explicit retention extension at the owning provider/content boundary, with encryption/access controls, retention, deletion, corrections and exact content references. It must not silently create a universal Live Fabric transcript database or misuse a domain-specific store.

`brain/advisor.py` already has a private Portfolio Research Advisor chat history and session mapping. Its inspected docstring and file paths bind that store to the portfolio-research surface; it is not evidence of an existing general executive-chat store. Reusing its UI ideas does not permit widening its data access or turning it into the company's new session registry.

Historical permission changes affect subsequent reads and active subscriptions. A revoked project grant closes its views and clears protected buffered content. A source correction invalidates the related current item; it is not hidden by keeping a previously cached copy as fresh. A history gap cannot be repaired by synthesizing messages or silently resuming a model.

### Content safety and fidelity

Visible responses, communicated plans, provider-approved reasoning summaries, tool activity and canonical receipts have distinct display classes. Private hidden reasoning is not exposed, reconstructed or falsely labeled. A tool-output string is not trustworthy because its field name contains 'redacted'.

The source/content owner decides which text and artifacts may cross the boundary. Test secrets split across stream chunks, untrusted links/Markdown, escaped terminal operations, malformed payloads, unrelated project content and role-imitation text. Content requiring complete-item filtering is withheld until it is safe to publish, with an honest availability label. This is a scoped safety limitation, not permission to substitute a vague summary for all ordinary text.

## 6. Instant-feeling chat with truthful delivery

The user interface should acknowledge a click immediately with a local **sending** state, then reflect the real owner's admission and delivery receipts. A local bubble is not a provider acknowledgement. Distinguish prepared, accepted for delivery, delivered/consumed when actually established, response started and terminal result. Existing owner state names remain authoritative; friendly labels are a closed projection.

There are two recipient intents:

**Message the office.** 'To Master CEO' addresses the durable logical responsibility. Under the accepted office-delivery contract, the owner resolves the current qualified implementation at dispatch. The receipt records which exact binding consumed it. It must not elect a new CEO or widen a grant merely to deliver the message.

**Message this session.** 'To API implementation / this Attempt' is exact-session targeting. Changing the selected graph node or receiving a new generation cannot silently retarget the draft. If the binding changes, revalidate and make the new recipient explicit. A message meant for an old worker must not be silently delivered to its successor.

The live owner must support the stated delivery behavior. The inspected Codex attention path refuses while the current writer has an active turn and sends a closed Wake instruction; it is not an arbitrary concurrent-user-chat API. The product must qualify a supported next-turn or steering action through the existing action/provider owner, not call attention delivery with unconstrained text.

When the existing owner accepts a message for later delivery, it retains the obligation and content reference. The browser owns no offline auto-send queue. If that accepted later-delivery capability is absent, show the limitation rather than claim a message is queued. Lost replies reconcile the original operation; they do not cause a second message, new account or replacement provider.

Ordinary authorized in-envelope messages should not require a repetitive modal. Run the applicable preflight and server validation behind the normal Send interaction. Ask for explicit confirmation when the action materially changes authority, recipient intent, spend, scope, interruption or irreversibility. Interrupting a turn, gracefully stopping a provider, canceling an Attempt and pausing new admissions remain distinct controls.

Edit, regenerate, fork and resend are disabled unless their exact semantics are admitted. A chat library's default regenerate button must not become an uncontrolled repeat of an effectful task. Two tabs with different request keys cannot consume the same single-consumption obligation twice. Offline drafts may remain local and clearly unsent; they never become executable authority on reconnect.

## 7. How the existing suite comes together

The companion `research/live_fabric/2026-09-13-connected-suite-contract-map.md` is the source-specific producer/consumer map. The major integrations are:

**Strategic cognition and the CEO:** `SOL:META-CEO:MASTERMIND` is one durable office. Its Chairman Cognition and CEO Execution modes connect the accepted direction to execution; no new Master Chairman or strategic task queue is created. Model selection remains configurable and qualified rather than hard-coded to a vendor.

**Executive app #599:** the five-tool app/binding program is the existing human/agent ingress. It is not a full chat-history, arbitrary-message or file-browsing API. Its installed/client proof remains a separate dependency, and the Live program does not add hidden sixth tools to that reviewed contract.

**Workspace supervision #603 / Macro #7130:** Workspace Agents may supply continuity advice or independent candidate review through qualified trigger/context/result/current-target interfaces. They are optional replaceable participants. The native path must continue without them. Trigger acceptance, provider status, returned candidate, parent consumption and final acceptance remain distinct.

**Workbench:** project files require the selected project's actual principal-bound lease, audience, expiry and allowed paths. A working transcript view is not file access. Read qualification does not authorize editing or a general terminal.

**Provider harness, router, capacity and hosts:** the logical route is separate from atomic placement and exact session materialization. Independent children are admitted work; ephemeral native helpers remain inside their parent's grant. Available quotas, enabled tools and awake hosts are distinct source facts.

**Dialogue, Wake and continuity:** actual results feed the existing return/obligation/current-target path. The UI sees it; it does not own the continuation. Reading a result, receiving a WebSocket frame or marking a message read in the sidebar does not consume the parent's company obligation.

**GitHub and Agent OS:** code, review and production artifacts are linked to their exact versions. Accepted decisions and discoveries update the existing durable records. A conversational statement alone neither merges code nor becomes organization-wide memory.

**Remote web and Mac:** the authenticated hosted application exposes finite approved resource/action projections over one current authority. It does not move or duplicate the Executive database. The Mac client is another viewer/controller client, not the always-on scheduler. Traveling-device disconnection does not stop workers elsewhere, and does not authorize offline command replay.

## 8. Workspace Agent visibility must remain honest

The current official trigger documentation describes API triggering, idempotency and beta run status, but says the agent's response cannot currently be retrieved through that API. That cannot power a promised full live chat view by itself. The application can show qualified run observations, a provider conversation link when available, and an authenticated candidate returned through an accepted result path. It cannot synthesize the missing conversation.

This does not shrink the full-chat product goal for supported managed lanes. It defines the adapter capability contract so the same UI can host different ceilings. A provider with status-only support has an explicit limited view and disabled unsupported composer, not a fake chat. A new full-content provider interface can upgrade the lane only after actual qualification.

The Workspace Agent callback/return design stays with #603's existing owners. An agent-authored result must bind to its operation, input revision, exact target/generation, artifact and authority; a model cannot use its callback to impersonate the Chairman or directly mark work accepted. A successful trigger is not a reason to insert an additional reasoning layer into every task.

## 9. Frontend foundation and reusable code

Retain React/TypeScript, the isolated Vite build, existing product tokens and the existing Python integration owners. React Flow powers Connections and mission topology; it does not have to occupy the default conversation screen. TanStack Query/Virtual and a small presentation store remain sufficient. Avoid adding several competing state frameworks.

Evaluate **assistant-ui's external-store runtime and primitives** as a specific chat-rendering donor. Its MIT license was read at blob `1be0da052dc2f3add7a56609d310d47c29e2f1bf`. Exact release/package integrity, dependency closure, accessibility, content rendering and behavior must be pinned and tested before adoption. No assistant-ui cloud history, new inference backend or implicit session manager is part of this choice.

Its documentation exposes important integration hazards: default adjacent-assistant content joining can erase distinct message boundaries, and handlers enable edit/regenerate/cancel/queue behavior. Use no automatic joining across source items, speakers or sessions. Bind only supported actions. Read-only/status-only lanes must remain read-only even if a convenient component expects a send callback. If its runtime assumptions conflict with Mastermind identity or authority, use its safe primitives or the custom renderer rather than alter company semantics to fit a library.

The native Mac package retains independent WKWebView/origin/IPC proof. A pleasant chat UI cannot justify arbitrary native filesystem, shell or credential access. Terminal output and browser previews remain separately qualified tools with their own input permissions.

## 10. First implementation slice: observable content, readable conversation, real interaction

D1 of the dynamic masterplan is tightened into a **conversation vertical**, not a graph vertical:

1. Qualify the existing managed provider owner and expose safe visible content before turn completion, while preserving the controller's ingestion and terminal-result path.
2. Read all available authorized retained content through bounded pagination, including a history longer than the existing 4000-character candidate summary. Report gaps or unsupported history honestly.
3. Render one exact source conversation with readable text, tool expansion, stable scrolling and a persistent clearly scoped composer. Inline child/artifact cards connect to qualified related views.
4. Inspect an orchestrator and child side by side without cross-target draft leakage, duplicate subscriptions that disturb execution, or merged identities.
5. Through a separately qualified existing command seam, send one exact ordinary message and display real owner receipts. If that action gate is not yet accepted, the read-only product may ship only to its clearly stated narrower ceiling; it does not close the full interaction milestone.
6. Demonstrate closed-viewer continuation: providers and the native return/parent-consumption path do not depend on the browser subscription.

The current source's terminal-gated metadata projection and result summary are the concrete producer work to finish. Figma/fixture work can proceed independently, but cannot satisfy this first real producer-to-reader capability. Workbench and optional Workspace integrations are separately qualified surfaces, not reasons to hold every supported conversation hostage.

### Additional acceptance discriminators

These augment the original 72-case matrix; none is claimed executed by this records wave.

- A response fragment is visible while the actual source turn is still nonterminal; terminal collection alone must fail this test.
- The same sample history viewed through source and UI preserves all authorized blocks beyond 4000 characters, with no accidental duplicate or dropped block.
- A slow spectator cannot stall provider execution, helper auditing, result persistence or parent attention.
- Opening the conversation, expanding a tool result and reading older history invoke zero provider starts, resumes, prompts or mutation calls.
- Two assistant-role messages from different sources remain separate and correctly attributed.
- A late event from a replaced generation cannot repaint the current session as active or retarget an unsent draft.
- An office-addressed message and an exact-session message obey their different recipient intentions and produce an exact dispatch receipt.
- A per-project file permission failure does not invent a missing file or grant broader access; independently authorized conversation content can remain readable.
- A status-only Workspace lane cannot display invented response text or enable instant chat from a trigger-status API.
- A user who scrolls upward or selects text is not pulled to the bottom by new messages; unread/follow state is presentation only.
- Closing every viewer during a worker return still produces the existing parent obligation, exact consumption and appropriate next edge.
- The primary usability tasks can be completed by keyboard and at 200-percent text scaling, with equivalent list navigation on narrow screens.

## 11. Figma scope and build-readiness gate

The new page `05 · Conversation-first workspace` in the existing Figma file is a design candidate. It preserves earlier iterations rather than pretending the older graph-first layout already satisfied the requirement. The key layouts are CEO chat, orchestrator chat, worker chat with expandable activity, paired conversations, on-demand Connections, recorded versus hypothetical routing, a limited provider lane and truthful message delivery.

All visible content is synthetic and labeled. A prototype transition never sends a provider message. Planned source contracts and frame inventories are not production proof. User review of readability and primary journeys remains distinct from source/security review.

When implementation is ready, Fable can lead the genuinely cross-system build under the Chairman's current direction. That handoff must include the accepted visual journey, the explicit producer gaps above, the suite contract map, exact source custody, bounded worker scopes, review independence and real-path acceptance. It is not issued now: assigning a principal before the conversation/content contract is settled would transfer unresolved product ambiguity rather than solve it.

The next design action is to verify the actual chat-first prototype's primary reading/navigation/split/context/message journey, then close the source-qualified spectator/history contract and acceptance tests needed by D1. Do not spend another wave merely adding dashboards or relabeling existing incomplete source as shipped.

## 12. Evidence references

Internal code reads use the source SHA in the header. Adjacent draft sources retain their own exact heads in the companion contract map. Documentation establishes available semantics; installed behavior remains unverified in this design pass.

- `control_plane/codex_operator_adapter.py`: inspected ingestion, read_events, attention and result paths; source facts in Section 3.
- `control_plane/operator_harness_contract.py`: canonical rich-interface and source identity/cursor boundary.
- `docs/EXECUTIVE_CHAIRMAN_COGNITION_LAW.md`: one executive office, cognition/execution modes and current reserved authority.
- `brain/advisor.py`: private portfolio-research conversation store, not a universal company chat owner.
- OpenAI Workspace trigger reference: https://developers.openai.com/workspace-agents/trigger-runs
- assistant-ui external-store contract: https://www.assistant-ui.com/docs/runtimes/custom/external-store
- assistant-ui license: https://github.com/assistant-ui/assistant-ui/blob/main/LICENSE
- Claude streaming reference: https://code.claude.com/docs/en/agent-sdk/streaming-output — main-session deltas and block-completion semantics are provider possibilities, not Mastermind's installed integration.
