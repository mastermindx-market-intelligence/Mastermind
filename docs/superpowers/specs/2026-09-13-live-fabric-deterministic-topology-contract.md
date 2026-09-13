# Live Fabric — relationships recorded at birth, rendered deterministically

**Parent:** WS:CHAIRMAN-CONTROL-ROOM / project-active-build-control  
**Carrier:** Mastermind PR #595, branch `sol/live-fabric-architecture-20260913`  
**Operation:** `mastermind-live-fabric-deterministic-topology-20260913-sol-001`  
**Source/procedure:** Mastermind `f087f9cf90a8fc7a81273c2576eefa6d06b54d9e`; Skillpack 1.0.1 / bootstrap 1  
**State:** architecture and qualification candidate; RECORDS_ONLY / SPEC_ONLY / PRODUCTION_INERT.

## 1. The answer to the Chairman's question

No background labeling AI is required. A model decides useful decomposition and supplies a bounded plan or request. The existing runtime validates and records that request with exact ownership and lineage. Qualified readers then derive the sidebar, inline child cards and Connections view from those same records. Creating a visual node is not another work operation.

The principle is **record relationships when the work is created, not infer them from chat afterward**. Execution, messages, review and continuity must enter through their existing instrumented boundaries. A graph renderer cannot repair a missing birth record by guessing a parent from a title, browser tab or similar-looking transcript.

The graph is a view, not a manually maintained company model. It has no separate lifecycle, scheduler, agent registry, identity map, transcript archive or graph database. A per-view node map, stable layout and an existing compositor cache are disposable presentation mechanics. They do not become sources of authority.

This contract narrows earlier designs wherever they implied that an arbitrary drawn hierarchy, generic dependency edge or source-level adapter automatically exists in the installed product. The conversation-first experience, complete authorized available history, safe messages, remote access and full longer-term multi-level ambition remain. No new runtime policy or source-owner permission is granted here.

## 2. What needs intelligence and what does not

| Decision or operation | Method |
|---|---|
| Interpret an objective, compare strategies, choose a useful decomposition | Bounded CEO/planner reasoning with current evidence and authority |
| Assign canonical IDs, bind a child to its admitted parent, validate grants and budgets | Existing deterministic runtime/admission code |
| Choose among eligible logical routes and make a concrete worker claim | Existing reviewed Model Router and Capacity owners; logical route and claim remain distinct |
| Bind an actual provider session/turn/process to its Attempt | Existing provider adapter and RuntimeBinding owners |
| Record who actually sent, received or consumed a company message | Existing authenticated Dialogue/Wake/return owners |
| Draw links, update statuses from their owner, group conversations, preserve layout | Deterministic projection and frontend rendering |
| Evaluate quality, resolve ambiguity, accept an independently reviewed outcome | The current accountable reasoning role under its actual grant |
| Keep work obligations alive while no model or GUI is running | Existing deterministic supervisory/continuation services, once operationally qualified |

A planner may name a step 'API implementation'. That title can help people navigate. Changing it must not change the step's Job, parent, worker, recipient, permissions or accepted result. Semantic discovery remains reasoning; structural bookkeeping does not require reasoning.

## 3. The existing source already contains concrete building blocks

All protected-source observations below are at the SHA in the header. They prove source behavior, not installed execution.

**COO cycle:** `control_plane/executive_coo_cycle.py`, blob `51c95d00c7d5541e58bc29b104f38f3c6b17d2ab`, exposes `CooCycle.run_once(parent_job_id)`. It is explicitly deterministic and production-inert, owns no durable state, does not invoke a model or provider, and delegates writes to existing Runtime commands. It creates the planner, admits a completed plan into child Jobs, creates reviews/repairs, and produces the immutable aggregation handoff. It reconciles an active exact dispatch before considering another queued child. This function is not, by itself, proof of a running daemon or parallel fleet.

**Dialogue identity:** `control_plane/executive_delegation_identity.py`, blob `d290b90af29058532aad3eb1c71af448158b8057`, exposes `derive_delegation_identity(job)`. It verifies immutable lineage/provenance and derives `exec-<lowercase Job ID>` and `asd-session-exec-<lowercase Job ID>`. There is no labeling model or lookup table. This dialogue `session_ref` is not a provider session and must never be used as one.

**Exact caller binding:** `integrations/slack_agent_dialogue/company_dialogue_runtime_binding.py`, blob `ca9a406c9c05e3fe361d25fbaa4e2873cc46c652`, compares the trusted current Job, Attempt, Worker, profile, dialogue parent fingerprint and RuntimeBinding against the caller. It derives a bounded DialogueBinding or refuses. A worker cannot declare itself another session by writing a persuasive message or copying an identifier.

**Recorded-lane observer:** #508 contains `control_plane/executive_lane_observation.py` at `3b0e97e7133153ecf4cc2539936f2dc9d7ca929f`, blob `45463ddbe161bf0a1e0f1b4884851c1fff65bc69`. `observe_root_lanes(...)` reads one exact root and descendants in a schema-qualified read transaction and validates the parent/depth graph. Its current Attempt/Worker join follows the recorded assignment. The source is reviewed but remains Draft/Hold and production-inert. Its own release/integration owner is retained; Live Fabric does not rebuild it.

The observer explicitly does not supply live provider activity, provider session, RuntimeBinding, host, account enrollment or current permission. The rich conversation consumer needs those additional qualified owner projections; a successful recorded-lane read cannot substitute for them.

## 4. Every displayed relationship has an origin

| Visible relationship | Recorded at | Exact basis / rule | What must not establish it |
|---|---|---|---|
| Mission contains child work | Existing child admission | `job_id`, `parent_job_id`, `root_job_id`, `depth` and verified creation provenance | Figma position, project name, chat title or a message saying 'I spawned' |
| Job has a current execution | Existing atomic claim and current-attempt owner | Job's `current_attempt_id`, matching Attempt/assigned Worker/quota and generation | Most recent process or most recently updated conversation |
| Conversation belongs to this execution | Existing session materialization/binding | Qualified provider session, epoch, process generation, turn and admitted scope | Provider brand, window order, shared account or reused display name |
| Role supervises work | Accepted organizational responsibility/commission owner | Exact accepted responsibility and applicable commission/binding | Assuming every visual vertical line is a runtime parent-child edge |
| Session sent a message to another | Existing admitted message/Dialogue operation | Authenticated sender, resolved recipient, message/operation identity, carrier and reply correlation | Natural-language mention, shared Slack channel or a transport timestamp alone |
| Child returned to its parent | Existing canonical result/return projector | Original Job/Attempt/artifact, intended parent obligation and target | Provider completion, model prose or sidebar unread state |
| Parent consumed a return | Existing obligation/consumption owner | Accepted current-target receipt tied to the original obligation | Browser viewed it, client received an SSE frame, or user marked a chat read |
| Work waits on something | Existing declared dependency/obligation owner | Exact source condition, target and resolution rule | Inferring 'waiting on' from silence or arbitrary summary text |
| Review applies to candidate | Existing review admission/result owner | `reviews_job_id`, reviewed Attempt and result/artifact digest | Same branch title, latest green check or an unrelated review |
| Repair supersedes a candidate | Existing repair admission | `supersedes_job_id`, rejected review, plan revision and repair round | Renaming an old task or replacing historical evidence in place |
| Native helper belongs inside parent | Qualified provider-native helper observation | Exact parent thread/Attempt and native subordinate identity under the admitted grant | Minting an independent Job after the helper has already acted |
| Execution runs on a host | Existing executor/host/binding owner | Qualified executor/host generation and placement receipt | Connector online status or a machine label in text |

The core graph can be derived from small field-based rules. Rich links require more producer information, not more clever inference. A missing authorized relationship remains unavailable or unjoined, with its source limitation disclosed. Do not add arbitrary new wire fields or a generic event vocabulary to a frozen owner schema just to fill a visual gap.

## 5. A concrete automatic journey

A planner returns a validated plan for one admitted root. The existing Runtime admits an API child and records its parent/root/provenance in the same owner operation. The existing reader subsequently returns that child. One pure display rule adds a Job entry and a parent-child edge; the conversation sidebar and inline child card reuse that same entry.

Later, Capacity claims a worker and Runtime records the current Attempt. The projection adds the exact execution association. The provider owner starts the permitted session and seals its observed binding; only then can a supported conversation link appear. Until that point the UI says queued or unbound, not 'Claude is thinking'.

As messages and tool-visible items arrive, the existing content owner supplies their exact scope. The selected conversation updates; the execution topology need not relayout per token. A canonical result creates the existing return obligation. The graph may highlight the return, while the parent remains awaiting consumption. The accepted parent response then changes the obligation and, where permitted, admits the next useful child.

No model is asked to keep the diagram synchronized. No periodic agent rereads all conversations to decide who belongs where. The engineering integration is written once for each supported owner/provider contract and maintained when those contracts change.

Reading must not create work. Rendering a missing node, reopening a tab, restoring a view, fetching history or subscribing to content cannot launch a process, emit a Wake acknowledgement, choose a successor or resubmit a message.

## 6. Important current ceilings: the drawing is ahead of one execution path

The inspected closed COO policy is `control_plane/executive_coo_policy.py`, blob `c2e53097a9e5ba377368338941316830dc1a6257`. It fixes:

- `max_depth = 1`: a root with direct children in this path.
- `max_fan_out_per_parent = 8` and `max_children_total = 16`.
- Two repair rounds and two review Jobs per revision; a reviewed step reserves nine possible child slots.
- The planner reserves one additional slot.

Consequently one reviewed step plus two unreviewed steps reserves twelve slots; two reviewed steps reserve nineteen and are refused. The fanout ceiling is not proof that eight fully reviewed steps fit the total budget. Do not remove required reviews to satisfy a reservation limit.

`derive_delegation_identity` also requires a direct root child. The current `mastermind.execution_plan/v1` schema in `control_plane/executive_orchestration_result.py` (blob `a1386a56ee588a223ca982069c87e741909f768d`) has ordered bounded steps, not an arbitrary per-step `depends_on` field. Its objects are closed. Agent OS dependencies exist separately and may be displayed with their own source; they do not silently become runnable scheduler conditions.

This does not prove every provider or Mastermind lane is limited identically. It establishes that this particular inspected integration cannot be advertised as arbitrary-depth, arbitrary-dependency, concurrently executing orchestration. A plural reader capable of displaying deeper recorded structures cannot authorize their creation.

The full target may include nested principal orchestrators and independently effectful descendants. Deliver that through one reviewed extension of the existing admission, schema, capacity, identity, result, recovery and consumer boundaries, with subtree budget and cancellation/fencing proof. Do not create another tree engine, bypass the closed policy, or draw a supervision chain and call it installed execution.

The first real path should use the currently lawful smallest complete task. Native read-only helpers remain distinguishable from independent child Jobs. The later expansion proves the desired depth/concurrency; it does not retroactively upgrade the earlier canary.

## 7. What remains configured or reasoned about

Trusted roles, grants, capability profiles, provider accounts and hosts need initial enrollment/configuration through their current owners. Those settings can evolve through accepted changes. That is not per-session manual graph upkeep.

The accountable planner decides which useful work packages and review obligations belong in a mission. It may use established patterns or produce a new bounded plan. The runtime supplies and validates the identity/authority context rather than trusting arbitrary claimed parents in model text. Unsupported requests return a structured refusal to the same accountable role for a lawful revision; they do not silently fall back to a more permissive route.

Legacy tabs or ad-hoc processes outside the managed birth path are not automatically governable. Show their observed presence separately. Use an explicitly supported existing-owner association/adoption workflow if available; the inspected rich contract does not support live App Server adoption. A human may need to authorize enrollment, but no one should label every future managed child.

“Who waits for whom?” is deterministic only when the relevant condition is structured. The future owner extension must record a blocker/dependency against exact work or artifact references at the point it is raised and accepted. A model may explain or propose that condition; the prose alone cannot block the scheduler or confer authority. The current closed tool schemas are not widened by this document.

## 8. Reconstruction and event delivery

The UI obtains a scoped snapshot from the existing owners, then consumes their qualified invalidations or observations. Owner mutation and owner evidence stay within their accepted persistence/effect contract. There is no independent graph write that can succeed while the work write fails.

Dropped display updates are repaired by re-reading the appropriate owner snapshot/history. The client can replace its derived graph without replaying a business command. Process restart, out-of-order responses and scope/auth changes require epoch-qualified reconciliation; a client timestamp cannot make old data current. A retired session remains historical to its actual retention ceiling.

The recorded-lane observer preserves inventory, attempt-join and source-coverage limitations. A complete scoped inventory may have an exact count while one current Attempt is unavailable. Truncation or unavailable inventory has no exact total. An inaccessible parent's existence/identifier must not be leaked through a graph denominator; the authorized projection decides which boundary information is safe.

Display coalescing is allowed; authoritative result handling is not dropped for a slow viewer. The application does not build a second durable event queue to keep the canvas animated. Spectator content remains separate from provider control consumption.

The existing deterministic host/supervisor must actually invoke the admitted cycle when eligible work or a return exists. A `run_once` function in source is not an always-on service. Prove restart/re-entry, original-operation reconciliation and return consumption with all viewers closed. A model is awakened only for a judgment that the accepted plan/policy cannot mechanically resolve. No new topology-monitoring model or daemon is introduced by Live Fabric.

## 9. The implementation is a finite set of connections

The later Fable principal commission should own integration and the authentic journey, not ask several workers to invent their own runtimes. Sol owns the accepted contract and final outcome review. No Fable receiver, worker or watcher is assigned by this record.

| Work package | Existing integration boundary | Independently useful proof |
|---|---|---|
| Born-linked work inventory | Existing Runtime, #508 reader and Steward/app projection | One real admitted root and children appear correctly; changing titles cannot change their topology |
| Exact provider conversation | Existing provider parser, binding and content/history owner | Actual visible text appears before terminal completion; history is readable without starting or draining a second session |
| Dialogue, return and next action | Existing Company Dialogue, result projector, RuntimeBinding and Wake | A result reaches and is consumed by the current parent while the viewer is closed |
| Conversation UI and scoped command ingress | Existing application authentication and finite read/action owners | Exact conversation opens, related work is navigable, an admitted message has truthful receipt and no duplicate effect |
| Richer hierarchy and dependency capability | Existing closed orchestration/capacity/result/recovery owners | Separately admitted deeper/concurrent work and typed waits function through the real path without widening child grants |

Logical packages are not a request to create five new services. Disjoint implementation and tests can be delegated to bounded specialists; the principal owns compatible interfaces, source custody, integration, browser proof and return to Sol. Provider adapters are added one at a time, not by assuming feature parity.

Ordinary model conversations use the shared chat UI, with context and the connection graph revealed on demand. A diagram is never a prerequisite for speaking to the CEO. The same recipient binding underlies the sidebar, selected thread, draft and actual message request.

## 10. Verification actually performed in this pass

A sandbox-only reference experiment ran **33 tests with zero failures/errors**, including all **24 input orderings** of four synthetic source rows. It exercised the exact copied COO policy, the unchanged `_valid_graph` helper excerpt from #508, and a disposable pure display projection. The full policy's Git blob matched the inspected source. The SQL reader, authentication, actual Runtime store, providers and production paths were not executed.

The checks discriminate title/prose changes, repeated snapshots, extra committed children, duplicate Job IDs, wrong roots, missing parents, depth errors, cycles, current-attempt replacement, incomplete coverage, unknown totals and parent-not-completed-by-child status. They also exercise the actual policy depth and child-slot reservation limits. Zero model or provider calls are needed to produce the reference graph.

This is **OFFLINE_SOURCE_AND_DESIGN_CHECKS_NOT_RUNTIME_PROOF**. It does not satisfy the existing 72-case live acceptance campaign or the first provider-to-UI release. It is evidence that the proposed projection is structurally deterministic, not proof that every installed producer emits the required facts.

The current Figma Connections example was generated from the same kind of synthetic parent fields, not from AI-assigned links. It deliberately separates queued Jobs from an observed provider session and exposes why the selected link exists. The full conversation-first prototype is still illustrative.

## 11. Acceptance and exact next action

The first source/build handoff must specify the actual managed provider/version, current authority service, existing authenticated resource contract and exact source-owned content/topology fields. Its real canary must show nonterminal content, available history, correct child lineage, a truthful message receipt and canonical parent return, while all missing capabilities remain explicit.

The graph-only acceptance bar is simpler: erase every disposable layout/node cache, rebuild from the same authorized source records, and recover the same identities/relationships with zero model calls and zero business mutations. Renaming a task or editing a chat summary must not change that answer. A node may move visually without changing its parent or authority.

The current source ceiling is not hidden. Before independently effectful nested orchestration is advertised, extend and prove the existing owners that presently enforce direct-child limits. In parallel, continue the lawful small conversation/return vertical. Do not turn a future capability into a reason to hold every useful current slice, and do not call a speculative topology live.

Superseded dashboard-first mockups are retired. `research/live_fabric/README.md` is the active design and implementation reading index; older records remain historical evidence, not ten competing build instructions. The next bounded implementation-design action is to freeze the exact continuous-content/history producer and authenticated consumer seam, then issue the scoped principal build commission through current placement and source gates. No repeat conceptual approval or per-session human labeling is required.
