# Mastermind OS — Daily Experience Builder Flow Specification

**Stage:** `DESIGN_CONTRACT` — reviewable design and builder contract; not live product qualification.
**Target repository path:** `docs/design/MASTERMIND_OS_DAILY_FLOW_SPEC.md`.
**Protected implementation baseline:** `mastermindx-market-intelligence/Mastermind@a2646f458f9ff41ddcedd89b338be4a4349e6cd6`.
**Design source:** approved Atelier visual direction, the current five-destination OS shell, and the daily-flow design decisions made in this Chairman-requested commission on 4 October 2026.
**Paper:** file `01M3NRCX55B452A12819WNE1RH`, page `p-E-0`, “13 · Daily Experience · Flow + Builder Notes”.
**Illustration rule:** every person, count, message, decision, outcome, project, status, and timestamp in a mockup is illustrative unless separately qualified by its current canonical owner.

## 1. Purpose and completion boundary

This specification makes the approved OS designs usable as a daily operating experience and gives builders an exact first slice.
The daily questions are: what needs my attention, what outcome is moving, who owns it, where do I continue the right conversation, and what evidence supports the state?
The shell remains **Today, Projects, Inbox, Conversations, Knowledge**.
Sessions, Resources, and Tools are contextual operational detail under More/Advanced.
The September 7 local Control Room proposal contributes decision-first hierarchy and bounded attention principles.
It does not replace the later five-destination Atelier shell or establish another lifecycle, priority queue, owner plane, command queue, or session registry.
Opening a destination, reading evidence, or continuing a conversation is navigation; it does not execute work.
The first build slice is source-qualified orientation → exact project/Mission → current permitted conversation/evidence → return, including authenticated negative cases.
Action composition and execution remain a separate future slice with their own current source-custody and capability qualification.

### 1.1 Product intent behind these decisions

Mastermind OS is the federated operating experience for an AI-led company. Its durable object is responsibility for an outcome; a provider tab or transcript is a replaceable carrier [S17, S20]. The company North Star combines durable out-of-sample forecasting, a trustworthy product, repeatable revenue acquisition and a continuously improving organization [S21]. The daily interface must help the Chairman direct those outcomes without reconstructing dispatch history, forwarding worker returns or managing provider sessions.

The Chairman supplies terminal intent, values, constraints and major corrections. The one Meta-CEO office reconstructs current truth, proposes useful transformations, delegates within the current envelope, integrates evidence and handles routine follow-through. Constitutional objectives, major budget expansion, irreversible changes, production-deployment policy, live-capital authority and other explicitly reserved boundaries remain Chairman decisions [S19]. A worker return waiting for Sol is therefore a team obligation, not automatically a Chairman Inbox item.

Decision-first Today applies the protected experience ruling: establish what the evidence can say, show the known decision, explain accountability and material exceptions, and keep source limits legible [S18]. The local Control Room's older three-entry proposal is not silently transplanted over the current OS shell; its hierarchy is implemented within the five human-facing destinations, with machinery in project context and Advanced. These are design decisions for this commission, not newly granted operational authority.

### 1.2 Source fact versus design requirement

Use `IMPLEMENTED` only for behavior observed in the protected source below.
Use `DESIGN_REQUIRED` for the intended experience builders must implement within existing owner contracts.
Use `CAPABILITY_ABSENT` when the protected app lacks the necessary read or command capability.
Use `FUTURE_ACTION_GATE` for interaction that cannot become enabled from this document alone.
A design fixture or successful decoder test is not a live installation, permission, dispatch, effect, or acceptance receipt.
No screen may borrow an action capability from a candidate branch and present it as protected implementation.

### 1.3 Exact baseline facts

The protected app is a read-only React/TypeScript consumer with a fixed web or native host installed before mounting [S1, S2].
Its actual views are Today, Work, Programs, Fleet & Capacity, Mission Workspace, Conversation, Activity, Connections, and Evidence [S3].
Today reads bounded Programs; Chairman attention, global Work queues, and Fleet & Capacity are explicitly not projected [S4, S5].
Programs resolve exactly one work reference to one unambiguous Runtime root; unresolved roots are not guessed [S6].
Conversation reads one current permitted managed-turn window; send, provider control, and history are all false in the closed DTO [S7].
Mission v3 adds bounded result navigation and exact-tuple result reads; execution, review, transport, acceptance, and freshness remain separate [S8, S9].
Live v2/v3 acceptance is pinned to `NOT_PROJECTED`; historical v1 acceptance support is a regression input, not a current acceptance capability [S10].
The protected source does not implement project creation, Inbox decision commands, durable conversation history, session replay, or execution resume [S3, S7, S11].

## 2. Paper directory and screen lineage

New UX artboards are explanatory flow/state contracts; existing AT/CH screens remain the visual component lineage.
All six IDs below were read back from the exact Paper file. The page is an editable storyboard and builder note set; the accepted Paper catalog exposes no prototype-link operation, so working click-through behavior is not claimed.
Desktop and mobile variants share the same source-state and effect semantics.

| Label | Content | Paper ID | Existing screen lineage |
| --- | --- | --- | --- |
| UX00 | Daily directory, shell, route and owner map | `PBO-0` | AT00 `KSB-0`, CH91 `KDN-0` |
| UX01 | Today attention/decision state matrix | `PBP-0` | AT01 `LNV-0`; mobile `N27-0` |
| UX02 | Direction, office/project conversation, named project flow | `PBQ-0` | AT03 `MHD-0` / `N29-0`; AT14 `N8N-0` / `NBB-0` |
| UX03 | Decision packet and closure | `PAY-0` | AT20 `OU0-0` / `P0I-0`; AT08 `L9V-0` / `MNS-0` |
| UX04 | Recovery, scope switch, evidence detour, return | `PAZ-0` | CH0 `JB4-0`, CH1 `IZB-0`, CH2 `JLU-0`, CH7 `KBA-0` |
| UX05 | Builder slice, capability gates, acceptance scenarios | `PBR-0` | all applicable lineage |

Avoid rendering the full provenance explanation as the daily headline.
Use a short understandable status near the content, with owner, clock, scope, reason, and limits available in details.
Keep enough qualified context visible that a user can distinguish a stale observation from a current decision packet.
The connection maps name actual frames and clearly labeled unavailable states. Builders must implement and test the corresponding navigation; static arrows, selected options and hidden layers do not establish working interaction.

### 2.1 Screen-to-flow lookup

Use [Page 13 — Daily Experience](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-E-0) for flow contracts, [Page 12 — Canonical Atelier](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-D-0) for route composition, and [Page 11 — Chat Atelier](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-C-0) for conversation details. A screen below is a design reference, never evidence of implemented route capability.

| Screen | Desktop / mobile | Entry and connected purpose |
| --- | --- | --- |
| AT01 Today | `LNV-0` / `N27-0` | default orientation; selected decision to AT20; office continuation to AT08 |
| AT02 Projects | `M4J-0` / `N28-0` | All projects or primary navigation; exact selection to AT03; new draft to AT14 |
| AT03 Project overview | `MHD-0` / `N29-0` | project outcome and owner; conversation to CH1; work to AT10; plan/evidence/journal through scoped tabs |
| AT04 Inbox | `KY5-0` / `MNL-0` | only qualified personal decisions/attention; selected item to AT20, preserving filter and origin |
| AT05 Knowledge | `L0Z-0` / `MNM-0` | reusable permitted knowledge; exact source detail; explicit Add to draft is not Send |
| AT06 Global search | `L3N-0` / `MNN-0` | Search/keyboard shortcut; visible scope; result opens exact permitted object; Close returns prior view |
| AT07 Settings & Sources | `L6N-0` / `MNO-0` | account/source detail and recovery; contextual entry retains originating view; no automatic reconnect authority |
| AT08 Meta-CEO office | `L9V-0` / `MNS-0` | one company conversation; To/Company scope; response identifies next owner and result |
| AT09 Resources & Systems | `LCJ-0` / `MO4-0` | project More; capacity/system facts from their owners; optional inspection |
| AT10 Work detail | `LF7-0` / `MOG-0` | exact project work/result; review, acceptance and release remain separate |
| AT11 Tools | `LHV-0` / `MP6-0` | contextual available capabilities; tool presence is not permission to execute |
| AT14 New project draft | `N8N-0` / `NBB-0` | name/outcome/scope; Review project opens UX02's review contract; one qualified record action |
| AT15 Session Estate | `NKM-0` / `NPO-0` | project More; Inspect next turn is an operator read, not a Chairman approval or execution request |
| AT16 Project master plan | `NV9-0` / `O1V-0` | Plan; owner maintains in-mandate sequencing; reserved change to Inbox |
| AT17 Session action preview | `O5Q-0` / `O5R-0` | advanced exact-target inspection; current preview limitation does not establish repeated-preview UX forever |
| AT18 Project evidence | `OE8-0` / `OKF-0` | Evidence or current result; source-bound evidence detail returns to the original selection |
| AT19 Project journal | `OMG-0` / `ORL-0` | More/Journal; material changes, next owner and source; no second memory plane |
| AT20 Chairman decision | `OU0-0` / `P0I-0` | exact complete packet; UX03 defines one final action and all closure branches |
| AT21 Receipt study | `P2V-0` / no counterpart verified in this pass | concurrent reference retained; use UX03 for this commission's completed receipt/recovery contract |
| CH0 / CH4 Welcome | `JB4-0` / `K3D-0` | new composition draft defaults to Meta-CEO/company; starter prompt appends, never auto-sends |
| CH1 / CH6 Project conversation | `IZB-0` / `K5X-0` | Sol with exact project context; evidence detour to CH2; unknown outcome to CH7 |
| CH2 Evidence / CH3 Context | `JLU-0` / `JV7-0` | companion to same conversation; preserve draft, selection, reading anchor and focus |
| CH7 Delivery recovery | `KBA-0` mobile | original-message status and no duplicate send; UX04 expands the recovery contract |

AT12/AT12M and AT13 remain retained earlier Session Estate/orchestration studies. AT15 is the current composition reference for that route. AT16–AT21 were observed as concurrent studies and were not modified by this commission; their current owner/source gates remain in force.

### 2.2 Concrete action anchors for wiring

The full action name and actual node ID identify a control. Short F-prefixes group journeys in the mockup and are not unique runtime command names or API enums.

| User action | Desktop node / mobile node | Builder connection |
| --- | --- | --- |
| Today: Review decision | `LUS-0` / `N4Y-0` | exact illustrative `DEC-R20-001` to AT20/AT20M; retain Today as return origin |
| Today: Continue with Meta-CEO | `LVF-0` / `PNJ-0` | AT08/AT08M with current qualified briefing context; no message or execution effect |
| Today: Mastermind OS outcome | `LWF-0` / `N5C-0` | AT03/AT03M exact project; organizational ownership is not execution proof |
| Today: All projects | `LW0-0` / `PR0-0` | AT02/AT02M, preserving the return path |
| Today: Sources and coverage | `LXA-0` / `PM6-0` | AT07 source context; return to the originating briefing |
| Office: Send message | `PK1-0` / `PN2-0` | qualified message owner, exact Meta-CEO/Company target, non-empty ready draft, once |
| Office: View project | `PSO-0` / `PMU-0` | AT03 project reference; preserve office draft and reading position |
| Project local navigation | `PN5-0` / `PT8-0` | scoped Plan, Work, Evidence and More; mobile Evidence remains in More plus the visible shortcut |
| New project: Review project | `PZO-0` / `NFI-0` | UX02 creation-review contract; no creation on this navigation action |
| Session Estate: Inspect next turn | text `NT6-0` / text `NU9-0` | AT17 advanced inspection; no routine Chairman approval requirement |
| Evidence and context return | CH2 `JLU-0` / CH7 `KBA-0` recovery | restore permitted exact origin; do not rebind or resend |

The Office mobile View project control is verified by its semantic layer name `F03M.OpenProject`; if an implementation extraction rebuilds its node IDs, resolve the live named node within AT08M rather than guessing. IDs identify this review snapshot and do not establish source identity.

## 3. Destination and design route map

These are **DESIGN ROUTE KEYS**, not proposed HTTP endpoints, authorization audiences, native commands, or API URLs.
Implement the keys using the existing router/view model as appropriate; do not infer transport capabilities from a route name.
An exact project may carry a canonical project reference and an admitted exact Mission pair when the owner provides both.
Do not treat a project reference, conversation ID, Job ID, and work reference as interchangeable identities.

| Design route key | User purpose | Required context | First-slice disposition |
| --- | --- | --- | --- |
| `today` | Understand strongest qualified attention and owned outcomes | independent attention and decision coverage | bounded Programs orientation plus explicit missing feeds |
| `projects` | Find and open an outcome | canonical project/work reference; root resolution state | existing Programs projection can back a labeled constrained view |
| `project.overview` | Outcome, milestone, owner, latest evidence | exact project and admitted Mission pair | existing Mission fields; missing milestone stays missing |
| `project.plan` | Understand current owner-approved plan | canonical plan revision | capability absent unless an existing owner supplies it |
| `project.work` | See scoped work posture | admitted Mission children and coverage | existing Activity projection |
| `project.evidence` | Inspect evidence for this project | owner/ref/revision and observation clocks | existing Evidence projection |
| `project.more` | Reach Sessions, Journal, Resources | scoped references and supported reads | links only when owner capability exists |
| `inbox` | Find current decisions and attention | exact owner item, coverage, filters | feed capability absent in baseline |
| `decision.packet` | Review and choose for one exact item | complete current owner packet and revision | fixture/preview until qualified decision capability |
| `conversations` | Find durable office/project conversations | canonical conversation ownership | current-window-only constrained baseline |
| `conversation.office` | Ask durable Meta-CEO office | current office binding; company/decision context | design requirement; no guessed session binding |
| `conversation.project` | Ask current project Sol | current project binding; To + About | current permitted window only where admitted |
| `knowledge` | Find reusable knowledge and evidence | canonical search/read scope | Evidence entry first; general search separately qualified |
| `search` | Find an exact permitted object | query, explicit scope and source-backed result pointer | general search capability separately qualified |
| `settings.sources` | Understand access and missing source coverage | independent account, acquisition/content permission and owner read state | existing auth/read facts; no invented connection authority |
| `project.create` | Draft named outcome and record project | AT14 fields; canonical creation capability | capability absent; retain draft in preview |
| `operation.status` | Reconcile an exact pending/unknown action | existing command owner operation identity | future action gate; not a new UI queue |

The five shell destinations remain visible across daily screens.
Project Overview/Plan/Work/Evidence/More are local navigation within the selected project.
Conversation scope is visible through **To** and **About**, not inferred from a highlighted sidebar row.
More/Advanced may expose Sessions/Resources/Tools only with contextual scope and meaningful unavailable states.
Selecting a model or recipient is not recovery of an unknown operation.

## 4. Source-owner and identity matrix

Every visible fact keeps the owner that already defines it.
Where a required owner feed is absent, show unavailable/not connected; do not manufacture another canonical source in UI state.
“Fresh,” “complete,” and “empty” must be explicit owner facts with bounded scope, not conclusions from a successful fetch alone.

| Concept | Existing source boundary / owner | Allowed UI interpretation | Forbidden inference |
| --- | --- | --- | --- |
| Program orientation | bounded Control Room envelope with Agent OS orientation | title, state, next action as projected | company-wide queue completeness |
| Exact Mission selection | resolved responsibility row and Runtime root | work-ref/root pair | newest root, last-opened root, or nearest matching root |
| Mission execution | admitted Runtime/Mission DTO | observed execution and child states | acceptance or later liveness |
| Accountable owner / owed turn | principal/transport projection | exact projected seat and reason | automatic dispatch authority |
| Current visible window | independently authorized content owner | permitted observed text and limited association | full transcript or proof of effect |
| Review | canonical review result / revision evidence | verdict with scope and currentness limits | acceptance or release |
| Acceptance | canonical acceptance owner | explicit qualified ruling only | runtime completed, PR green, or review approved |
| Release | canonical release owner and exact artifact | released revision if separately projected | accepted means deployed |
| Attention / decisions | existing attention and decision owners | exact items and independent coverage | missing feed means no decisions |
| Plan adoption | current project/plan owner | explicitly adopted revision | answer prose or ordinary Send adopts a plan |
| Project creation | canonical project-record owner | matched creation receipt and exact project | Send starts a project or assigns providers |
| Command effect | existing canonical command owner | exact operation stages and receipt/status | navigation state becomes command queue |
| Sessions / succession | existing RuntimeBinding and accepted succession path | current bound session when supported | Chairman hunts tabs or chooses newest session |
| Resources / capacity | canonical Capacity source | qualified fleet/placement observation | browser connected means host ready |
| Knowledge / evidence | existing evidence/knowledge owners | allowed scoped read and provenance | copied text becomes a new owner plane |

## 5. Today — decision-first daily orientation

Today leads with the strongest qualified attention/decision headline that the sources can support.
Show at most one expanded decision; show other owned outcomes compactly with owner, next result, and latest qualified evidence.
The main action on an actionable decision is **Review decision**.
**Continue with Meta-CEO** is optional; it must not compete visually with the required decision.
Team reviews remain owned by the team unless the current owner packet identifies a Chairman decision.
Do not promote every review, waiting worker, or incomplete outcome into Chairman attention.

| Attention coverage | Decision coverage | Known content | Today presentation |
| --- | --- | --- | --- |
| fresh, complete, empty | fresh, complete, empty | no qualified items | qualified all-clear with scope and observation time |
| fresh, complete | fresh, complete | one actionable current decision | decision headline + one expanded decision + compact owned outcomes |
| partial | fresh or partial | known attention/decisions | keep known items; explain limited coverage; withhold global totals |
| fresh or partial | unavailable | known attention | attention headline; decision feed unavailable; no zero-decision inference |
| unavailable | fresh, complete | known current decision | decision headline; attention coverage unavailable |
| historical | any | dated known items | dated history presentation; no current all-clear or enabled approval |
| unavailable | unavailable | none | unable to establish current attention; explain recovery path |
| complete but stale | complete but stale | none | last observed empty; current all-clear withheld |

Both independent feeds must be fresh, complete, and empty before an all-clear.
A known item may be displayed under partial coverage without claiming the list is exhaustive.
Withhold “0 decisions,” “all caught up,” and company totals when coverage does not support them.
Where only the protected Programs source exists, the honest headline is bounded Program orientation and the attention/decision feeds remain not connected.
Opening Today does not create a session, execute a command, refresh an owner workflow, or transfer review ownership.

## 6. Direction and durable conversations

### 6.1 Ask Meta-CEO

There is one durable Meta-CEO office, not a new office per project or question.
**Ask Meta-CEO** navigates to its current canonical office conversation with qualified company/decision context.
The header names **To: Meta-CEO** and **About: Company / exact decision / selected context**.
Do not mint a chat, guess a recent Runtime root, or use a stale tab as the office identity.
If the current office binding cannot be established, retain permitted draft context and explain that the conversation is unavailable.
Ordinary questions and messages use one Send when current capability permits; no blanket preview or confirmation ritual.
In the first protected slice, Send remains absent/disabled or clearly preview-only because the window DTO has no send capability [S7].

### 6.2 Project conversation

Project conversation targets the current project Sol through its existing canonical binding.
The header names **To: Project Sol** and **About: exact project** with enough identity to distinguish it from the office.
Switching projects loads that project's scoped draft; it does not silently retarget the current draft.
A user may explicitly move/copy a draft only through a supported design with visible new scope and no protected-content leakage.
Do not turn project selection into conversation creation or root guessing.
An unbound global current window remains labeled unbound; selecting a project does not prove correspondence [S7, S12].

### 6.3 Direction loop

The user states a desired outcome and may add constraints or context.
Meta-CEO responds with its understanding, the accountable owner, and the next expected result.
Ask for clarification only when a missing answer materially affects outcome, scope, owner, authority, or reversibility.
Routine follow-through inside the mandate proceeds automatically by the existing owner.
A consequential command or reserved change receives one contextual deterministic preflight only when that owner's law requires it.
Answer prose does not execute, adopt a plan, dispatch a worker, create a project, or record a decision.
Ordinary Send acknowledgment means the message was accepted by the message owner; it proves none of those separate downstream facts.

## 7. AT14 — named project creation

AT14 collects **Name** and **Outcome**; Scope is visible; Context and constraints are optional unless the existing owner requires them.
Use ordinary language that explains the result the user wants, without provider or session setup in the daily path.
One review states what creation **does**: records a canonical named project.
The same review states what creation **does not do**: start work, assign providers, dispatch workers, or silently adopt a plan.
The final action is **Create project** only when the current canonical creation capability is qualified.
After a matched canonical creation receipt, open the exact returned project reference.
Do not start a new chat automatically; show the existing project conversation entry when its binding is known.
Do not construct or guess a Mission root from the new project's name or latest Runtime job.
If unavailable, preserve the authorized draft and explain which recording capability is unavailable.
If outcome is unknown, reconcile the existing creation operation; do not blindly create a replacement.
The protected implementation has no project creation API or command [S3, S11].
The first slice may show AT14 as an illustrative draft/review with a clearly unavailable final action.

## 8. Exact project overview

The overview foregrounds Outcome, Next milestone, Accountable owner, and Latest evidence.
Only show a milestone when the owner projects one; a next-action string is not automatically a milestone.
Use local tabs **Overview / Plan / Work / Evidence / More**.
At 390px use **Overview / Plan / Work / More**; Evidence remains in More and the overview's visible evidence shortcut.
More contains Sessions, Journal, and Resources when their current scoped source exists.
Plan changes inside the mandate are handled by the project owner.
Reserved changes enter Inbox as an exact owner decision packet; they are not disguised as an ordinary plan edit.
Keep **Returned**, **Review**, **Accepted**, and **Released** visually and semantically separate.
Returned means a result exists; review names the verdict and revision; accepted names the ruling; released names the exact released artifact.
No “Done” aggregate may erase a missing acceptance owner or release receipt.
Protected Mission/Activity fields can support the first overview/work/evidence slice, but missing outcome/milestone/plan fields remain explicit gaps [S8, S9, S10].

## 9. AT20 — exact decision packet and closure

Today or Inbox opens one exact item with its canonical identity, packet revision, and originating filter.
AT20 is the complete **current** packet, not an approval card built from partial attention text.
Show why this needs the user, why now, two to four choices, consequences of waiting, reversibility, recommendation provenance, and evidence.
Recommendation provenance names the recommender and the qualified basis; illustrative recommendations remain labeled illustrative.
An incomplete packet is attention only; approval/decision controls remain unavailable.
One final action chooses the exact current packet option through the existing owner capability.
Do not add a second confirmation after a complete owner-required preflight unless the owner contract explicitly requires it.

### 9.1 Decision closure states

| State | Required evidence | User presentation | Allowed next step |
| --- | --- | --- | --- |
| `preview` | illustrative or incomplete packet | review only; action unavailable | read evidence / return |
| `ready` | complete current packet + permitted decision capability | exact option and consequences | one final action |
| `pending` | original request/operation identity retained; owner outcome not yet established | recording decision; preserve exact item | check existing operation status when supported |
| `recorded` | matched receipt for item, revision, option, and operation | decision recorded with receipt | refresh exact item and projections |
| `unknown` | request may have had effect; no matched terminal evidence | outcome not yet established | reconcile exact operation; no blind resend |
| `known_no_effect` | owner proves exact operation caused no effect | decision not recorded; reason visible | explicit retry only when current packet/capability permits |
| `changed_before_submit` | packet/revision changed before dispatch; effect NONE | item changed; previous choice remains a draft | reload current exact packet and review |
| `refused` | exact owner permission/validation refusal | action unavailable with reason | resolve allowed permission or packet issue |

Recorded means a matched canonical receipt, not a button click, success toast, HTTP delivery, journal entry, or generated answer.
After recorded, reread the exact owner item and refresh projections; do not locally erase it as proof of owner closure.
Journal failure after a recorded decision does not retry the decision; report journal failure separately.
`status: not_found` is not known no effect and must not unlock blind resend.
If a packet changes after dispatch, retain the original pending/unknown operation until its outcome is reconciled. A later revision never proves that an earlier submission had no effect. The changed-before-submit specimen applies only before dispatch.
Back returns to the originating Today/Inbox route and filter with preserved scroll/focus where available.
Keep all prototype packet details, options, and receipts clearly illustrative until an actual owner supplies them.

## 10. Transition contract

The following table is the minimum interaction contract; preserved state is conditional on authorized persistence and current permission.
Operation recovery always remains with the existing canonical command owner.

| Trigger | Guard | Destination / result | Preserved state |
| --- | --- | --- | --- |
| Open Today | acquisition/read context available or explicit unavailable | `today` with qualified source state | shell; last permitted local view context |
| Review decision | exact item exists | `decision.packet` | origin route/filter/scroll/focus |
| Open evidence from packet | scoped evidence read allowed | evidence detail | exact item/revision; choice draft; return target |
| Return from evidence | origin still permitted | same packet or changed-state packet | authorized choice draft, scroll, actual focus |
| Ask Meta-CEO | current office binding available | `conversation.office` | permitted office draft; qualified About context |
| Ask Meta-CEO unavailable | binding/capability absent | office unavailable state | authorized draft and context; no new conversation |
| Open project | exact canonical reference; root resolved if Mission read needed | `project.overview` | previous scope draft; origin filter |
| Project root unresolved | no unique admitted root | project identity plus unresolved-source state | project context; no guessed Mission |
| Continue conversation | current conversation binding/read permitted | `conversation.project` | scoped draft and About context |
| Switch project | new exact project selected | new scoped project/conversation | each authorized scoped draft; no automatic retarget |
| Send question | current send capability; ready draft; permitted scope | existing message owner operation | draft until matched acknowledgment policy permits clearing |
| Send unavailable | read-only/permission absent | same composer preview/unavailable | permitted draft; clear reason |
| Consequential command | owner requires deterministic preflight | one contextual review | exact command target and permitted draft |
| Create named project | complete AT14 draft and qualified creation capability | one creation review | draft fields/context |
| Confirm creation | current review and permitted exact operation | pending → exact returned project on receipt | operation identity; draft until outcome known |
| Final decision action | complete current packet and capability | pending / recorded / unknown / refused | exact item, revision, option, operation identity |
| Navigate during unknown operation | existing owner persists operation | chosen read destination; status remains recoverable | canonical operation reference; authorized return context |
| Change model/recipient | explicit supported selection | new composition context | scoped draft; unknown operation remains at original owner |
| Auth/permission boundary | current owner invalidation event | protected content cleared immediately | only draft state allowed by existing persistence and new permission |
| Browser Back/Forward | valid exact pair | restored Mission context | baseline pair only; richer state only where implemented |
| Continue work | separately supported command and owner guard | owner preflight/action | exact bound work identity; never guessed session |

## 11. Drafts, detours, succession, and return

Evidence/search/drilldown detours return the user to draft, scroll position, and actual focus when that origin remains permitted.
Save a return descriptor in the existing view-state facility; do not create a new command or session registry.
Project scope and recipient are part of the draft identity, not incidental labels.
Auth and permission changes immediately invalidate protected content, including in-flight reads and apparently identical native public auth state [S13].
Draft retention is allowed only by an existing approved persistence path and current permission.
Do not invent plaintext localStorage, offline storage, fake autosave, or “saved” claims to meet a mockup expectation.
If no approved persistence is available, state that the draft is held in this open view and avoid a durability promise.
On succession, use the existing accepted RuntimeBinding and canonical succession path.
The Chairman must not hunt sessions, compare newest tabs, or decide which worker is still alive.
**Continue conversation** means navigation to the current permitted binding.
**Continue work** is an execution command and appears only when supported by the current owner law and capability.
Unknown effect remains tied to its original operation even if the user navigates, switches project, changes model, or signs in again.

## 12. Command stage truth and action inventory

The labels below describe distinct facts; builders may not compress them into a generic success state.

| Stage / fact | Meaning | Does not prove |
| --- | --- | --- |
| draft | user composition only | server recording or command preparation |
| preview / preflight | owner-required deterministic review of exact proposed effect | execution |
| submitted | exact request left the client | owner received, accepted, or effected it |
| acknowledged | owner accepted an exact operation for tracking | final effect or acceptance |
| recorded / known effect | matched owner receipt establishes named effect | downstream dispatch, review, acceptance, or release |
| unknown | effect cannot yet be established | no effect or permission to repeat |
| known no effect | owner proves no effect for exact operation | replacement packet is safe without requalification |
| returned | bounded result emitted | reviewed, accepted, or released |
| reviewed | owner verdict on scoped revision | current revision accepted or released |
| accepted | qualified acceptance-owner ruling | deployment or release |
| released | exact release-owner artifact receipt | all work or decisions complete |

| Action | Type | First-slice status | Guard / effect boundary |
| --- | --- | --- | --- |
| Open destination/project | navigation/read | enabled where exact source qualifies | no execution |
| Review decision | navigation/read | preview when feed absent | exact owner item; incomplete packet cannot approve |
| Open evidence | read | existing permitted evidence | current scope and permission |
| Refresh current window | read | implemented | content permission; no history/send |
| Ask Meta-CEO | navigation | binding-dependent design | one durable office; no chat minting |
| Continue conversation | navigation/read | permitted current window only | exact current binding; no work resume |
| Send question/message | message effect | unavailable in protected source | separately qualified send capability; once |
| Propose consequential change | command composition | future action gate | owner-required contextual deterministic preflight |
| Create project | project-record effect | absent | canonical creation receipt; does not start work |
| Record decision | reserved owner effect | absent | complete packet + one final action + matched receipt |
| Continue work / STOP | execution effect | unavailable | current source custody, binding, owner capability |
| Sign in/out | auth boundary | implemented | separate acquisition/content; clear protected state |
| Change model/recipient | composition configuration | only when supported | never resolves prior unknown effect |
| Sessions/Resources/Tools | contextual reads/actions | owner-capability dependent | More/Advanced; no new plane |

## 13. Failure and microcopy matrix

Copy below is intended product copy; technical owner reason codes belong in expandable details.
Do not collapse a permission refusal, missing setup, incomplete coverage, or unknown operation into “Something went wrong.”

| Condition | Primary copy | Recovery affordance | Truth constraint |
| --- | --- | --- | --- |
| client registration absent | “Sign-in setup pending.” | explain setup availability | disabled sign-in; no invented registration |
| popup blocked | “Allow the sign-in popup and try again.” | Sign in | same auth flow, not content retry |
| popup closed | “Sign-in window closed. Try again when ready.” | Sign in | no implied signed-in state |
| acquisition allowed, content refused | “Workspace connected. Conversation access is unavailable.” | read project/evidence; permitted auth recovery | keep permission resources separate |
| Programs source unavailable | “Projects could not be established from the current source.” | supported source reread/sign-in | no zero-project claim |
| root unknown/conflict | “This project has no single resolved Mission.” | inspect owner-projected detail | no guessed root |
| partial attention | “Known attention is shown. Coverage is incomplete.” | inspect source details | no global count or all-clear |
| dated history | “Last observed [qualified time]. Current state is not established.” | supported current read | no enabled stale approval |
| incomplete decision | “This item needs more information before you can decide.” | view evidence / return | attention only |
| changed decision packet | “This decision changed. Review the current choices.” | reload exact item | old choice not applied automatically |
| decision pending | “Recording your decision…” | check exact operation | no recorded toast yet |
| unknown effect | “The outcome is not yet established. We are checking this operation.” | reconcile exact status | no resend/create replacement |
| status not found | “This status response does not establish the outcome.” | owner reconciliation | not known no effect |
| known no effect | “This operation did not record the change.” | current guarded retry where supported | exact no-effect evidence required |
| journal failed after decision | “Decision recorded. Its journal update is unavailable.” | journal recovery only | do not retry decision |
| project creation unavailable | “Project recording is unavailable. Your draft remains here.” | return/edit within permitted view | no durable save guarantee |
| unbound current window | “Current permitted window. Its link to this project is not established.” | evidence/read details | do not claim project transcript |
| empty observed window | “No visible response was returned in this observed window.” | Refresh window | not full history empty |
| owner withheld content | “Content withheld by its owner.” | available owner details | no reconstructed hidden text |
| read-only composer | “Sending is not available in this build.” | read current conversation/evidence | no simulated success |

## 14. Keyboard, mobile, and accessibility contract

Desktop Enter sends only when the draft is ready and the current send capability is available.
Shift+Enter inserts a newline; IME composition Enter does not send.
The protected read-only slice has no keyboard path that manufactures Send or executes from answer prose.
Mobile uses an explicit Send button; return/newline behavior cannot accidentally submit.
All mobile tap targets are at least 44 px; honor safe areas and keep composer/action controls reachable above the keyboard.
Test 320 px and 390 px widths, expanded text, long project names, owner labels, evidence references, and multiline drafts in the later actual build.
Preserve draft visibility when the software keyboard opens; do not hide To/About or change recipient silently.
Return from a detour restores actual focus to the originating control or a meaningful surviving heading.
Route changes must not steal focus during background data refresh; protected source already distinguishes navigation focus from refresh [S14].
Disabled controls have an adjacent explanation; do not require hover to understand a root or permission problem.
Status updates use appropriate accessible announcements without repeatedly reading unchanged source observations.
Do not claim accessibility verification from Paper frames alone; actual keyboard, focus, screen-reader, responsive, and auth-boundary tests are build acceptance.

## 15. Vertical slices and unrelated gates

### Slice A — first build

Implement five-destination shell presentation without claiming missing sources are connected.
Deliver qualified daily orientation, exact project/Mission entry, admitted overview/work/evidence, current permitted conversation, and return.
Include configuration absent, acquisition denied, content denied, root conflict, partial/historical source, unbound window, and identical-display auth-generation cases.
Use existing fixed transports, owner decoders, exact selection, generation fences, and abort handling.
Do not add a command queue, session registry, owner store, generic URL bridge, provider control, or plaintext draft persistence.
This is product read/navigation verification, not action acceptance or installation qualification.

### Slice B — separately qualified future actions

Send, command preflight, project creation, decision recording, operation reconciliation, execution continuation, and STOP need current owner capability and source custody.
This commission directly re-read both candidate PRs on 4 October 2026: #1046 remains open/draft at `089a745b9aa4a4f2ec615827912f547f3884d744`; #1150 remains open/draft at `37d02586eeb97d92e6fb9ed6dbc7cd142dd6449c` and is a launch-only candidate. These are custody observations, not protected implementation or installed proof.
SEND/STOP remain unavailable; candidate behavior must not be presented as protected behavior.
Before action implementation, reread the exact current #1046/#1150 sources through the existing custody procedure and bind the full revision and lawful capability.
BG3/BG5 retain the first Meta-CEO slice and source-ownership fences. In particular, no existing App/Work/command path is released for modification by this design document. Reconcile the current incumbent before the proposed broader shell integration; use only separately owned new Meta-CEO projection/fixture work while those paths remain held.
This design does not change protected send/stop gates, source-release gates, runtime leases, acceptance laws, provider enrollment, native installation, or deployment status.
Do not use unrelated CI/release waiting as a reason to block useful read-only design/build work.
Do not treat completion of this documentation as release authorization or a live qualification.

## 16. Illustrative scenario fixtures

Fixtures are test/design inputs only; names below are not claims about actual company state.

| Fixture | Inputs | Expected visible result |
| --- | --- | --- |
| F01 — complete empty | both attention and decision owners fresh, complete, empty | scoped dated all-clear; no expanded decision |
| F02 — known under partial | one known decision, partial attention coverage | one decision + coverage caveat; no total/all-clear |
| F03 — team review | review assigned to team, no Chairman packet | compact owned outcome; no Chairman approval CTA |
| F04 — office unavailable | office binding absent; authorized open-view draft | unavailable conversation; draft retained only within approved policy |
| F05 — exact project detour | resolved exact pair, evidence link, scoped draft | evidence then return to same scope/draft/scroll/focus |
| F06 — project switch | draft for project A; switch to B | B draft/context; A draft never silently retargeted |
| F07 — changed packet | user selects option; owner revision changes before dispatch | changed-before-submit state; re-review current choices; no old approval |
| F08 — unknown decision | request may have effected; no matched receipt; not_found status | unknown retained; owner reconciliation; no blind resend |
| F09 — recorded/journal failed | matched decision receipt; journal update fails | recorded decision plus separate journal failure |
| F10 — auth boundary | old content visible; identical native public auth event with new generation | immediate clear before replacement reads complete |
| F11 — result completed | execution completed, review present, acceptance not projected | separate completed/review/not-projected labels; no Done/accepted |
| F12 — create unavailable | named project draft; capability absent | one preview; unavailable final action; no project/chat/root fabricated |

## 17. Implementation acceptance scenarios — fifteen required

1. **Shell and contextual operations:** Today/Projects/Inbox/Conversations/Knowledge are the primary shell; Sessions/Resources/Tools stay contextual; missing feeds render honest unavailable states.
2. **All-clear boundary:** all-clear appears only when both independent attention and decision coverage are fresh, complete, empty; partial/stale/unavailable permutations withhold it.
3. **Decision-first hierarchy:** at most one qualified decision expands; Review decision is primary when actionable; optional office continuation remains secondary; team-owned review is not reassigned to Chairman.
4. **Exact identity:** valid work-ref/root selection opens the admitted Mission; duplicate/extra/malformed selectors and unknown/conflicting roots cause no guessed source read.
5. **Source-state fidelity:** known partial rows remain visible with coverage; historical rows show date; empty observation never means zero work; totals require owner completeness.
6. **Office/project distinction:** To/About visibly identify office versus project; unavailable binding creates no conversation; project switch never silently retargets a draft.
7. **Read-only send boundary:** protected slice has no effective send/stop/create/decision command; illustrative controls cannot generate synthetic acknowledgments or success receipts.
8. **Ordinary message behavior in future qualified slice:** ready Enter sends once; Shift+Enter newline; IME Enter does not send; mobile explicit Send; no blanket confirmation for a question.
9. **Consequential command review:** only owner-required deterministic preflight appears; exact effect and target are reviewable; answer prose cannot execute or adopt a plan.
10. **Project creation distinction:** AT14 review explains record-only effect; matched receipt opens exact project; unavailable retains permitted draft; unknown never blindly recreates or guesses root/chat.
11. **Decision packet completeness:** incomplete/stale packet has no approval; current packet shows why you/now, 2–4 choices, waiting consequences, reversibility, recommendation provenance, evidence.
12. **Decision receipt and recovery:** recorded requires matched identity/revision/option/operation receipt; pending/unknown/known-no-effect/changed remain distinct; not_found does not unlock resend; journal failure never retries decision.
13. **Auth generation protection:** sign-out, permission loss, and identical-display native generation changes clear protected rendered and in-flight content before replacements; retention follows existing authorized policy.
14. **Detour/return usability:** evidence/search detour returns authorized draft, origin filter, scroll, and actual focus; navigation during unknown retains exact canonical operation; recipient/model changes do not reconcile it.
15. **Responsive and semantic verification:** actual 320/390 px, expanded text, keyboard/safe-area, 44 px targets, focus restoration, and separated returned/review/accepted/released states pass; Paper/fixtures do not stand in for build/live qualification.

Future-action scenarios are required before that slice becomes enabled, not evidence that those capabilities exist today.
Record test results with exact source revision and actual observation; do not convert this list into a checklist of fabricated passes.

## 18. Protected-source references

Each reference is a primary repository source pinned to `a2646f458f9ff41ddcedd89b338be4a4349e6cd6`.
The census did not execute these sources or qualify installation, registration, permissions, callbacks, or live effects.

| Ref | Exact source | Relevant fact |
| --- | --- | --- |
| S1 | [README.md L3–21](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/README.md#L3-L21) | read-only scope, exact pairs, bounded observation, no send/history acceptance |
| S2 | [main.tsx L10–25](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/src/main.tsx#L10-L25) | fixed host before mount; callback cleanup boundary |
| S3 | [App.tsx L29–52, L894–905](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/src/App.tsx#L29-L52) | implemented navigation; local view state starts Today |
| S4 | [App.tsx L1450–1534](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/src/App.tsx#L1450-L1534) | bounded Today Programs and missing Chairman feed |
| S5 | [App.tsx L1590–1640](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/src/App.tsx#L1590-L1640) | missing global work and capacity sources |
| S6 | [mission.ts L1352–1405, L1587–1648](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/src/mission.ts#L1352-L1405) | exact selectors and unambiguous responsibility/root join |
| S7 | [workspace-contract.ts L178–218, L300–319](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/src/workspace-contract.ts#L178-L218) | one managed window; send/provider/history false |
| S8 | [App.tsx L371–611, L696–777](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/src/App.tsx#L371-L611) | Mission/Activity/Evidence presentation and separate facts |
| S9 | [App.tsx L100–290, L1674–1765](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/src/App.tsx#L100-L290) | exact result navigation, typed detail, review currentness limits |
| S10 | [mission.ts L1148–1173, L1929–1967](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/src/mission.ts#L1148-L1173) | live acceptance not projected; v3 reuses v2 validation |
| S11 | [host.ts L23–83, L270–276](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/src/host.ts#L23-L83) | fixed read/auth interface and native command surface |
| S12 | [workspace-contract.ts L429–485](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/src/workspace-contract.ts#L429-L485) | narrow observed Mission/window association |
| S13 | [App.tsx L987–1106](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/src/App.tsx#L987-L1106), [auth-generation test L75–124](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/src/App.auth-generation.test.tsx#L75-L124) | immediate clear, epochs/abort, identical-display native boundary fixtures |
| S14 | [App.tsx L977–986, L1210–1229, L1426–1446](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/src/App.tsx#L977-L986) | navigation focus, pair restoration, selection switching |
| S15 | [web-auth.ts L112–162, L392–439, L441–585](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/src/web-auth.ts#L112-L162) | private resource tokens, fixed GETs, failure and typed result 503 handling |
| S16 | [README.md L25–65, L89–94](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/app/mastermind_os/README.md#L25-L65) | operator configuration, independent permissions, BUILT_NOT_PROVEN |
| S17 | [Executive Chat-Native Sol Hierarchy Law §§3–6,9–10](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/docs/EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW.md) | one durable Meta-CEO, replaceable conversations, responsibilities rather than tabs |
| S18 | [Decision-First Chairman Experience §§1–2,9–14](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/docs/superpowers/specs/2026-09-07-chairman-control-room-decision-first-experience-design.md) | qualified attention, complete decision packets, bounded default surface and optional Advanced |
| S19 | [Executive Chairman Cognition Law §§1–4,6](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/docs/EXECUTIVE_CHAIRMAN_COGNITION_LAW.md) | Chairman intent, Meta-CEO cognition/execution, reserved authority, value/authority/serviceability separation |
| S20 | [Operating-Surface Convergence §§1–4](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/docs/superpowers/specs/2026-08-27-mastermind-operating-surface-convergence-design.md) | federated OS, source owner matrix, no manual dispatch reconstruction |
| S21 | [Strategic state, North Star and P0 objectives](https://github.com/mastermindx-market-intelligence/Mastermind/blob/a2646f458f9ff41ddcedd89b338be4a4349e6cd6/config/strategic_state.yml) | forecasting, product trust, revenue, organization and recurring Chairman-load reduction |

### 18.1 Source/documentation contradiction to preserve

README enumerates Mission v2, three GET routes, and older native read commands [S1, S16].
Actual code prefers Mission v3, includes `/workspace/mission/v3/current` and `/workspace/result/current`, and native `read_mission_v3`/`read_result` [S9, S11, S15].
Use code for current source behavior; update documentation through its authorized review path rather than treating README omissions as absent result capability.
The approved five-destination shell differs from implemented nine-view navigation; this document is the design contract for that presentation change, not a claim it is already built.
Today decision/attention completeness, durable office bindings, project recording, Inbox packet commands, and broader knowledge search still require existing-owner capability feeds.
Resolve those gaps through the existing owners; do not create substitute planes to make a design look complete.

## 19. Review outcome and remaining proof

All six workflow artboards exist on the exact Paper page, with their IDs recorded above. Actual screenshots and editable JSX were inspected. Today, Meta-CEO, project navigation, welcome context and new-project intake were refined in the canonical screen family. The directory, AT00, MC90 and CH91 point builders to this flow contract. The UX04 project-conversation example was reconciled to Project Sol rather than the company Meta-CEO. The AT15 example now keeps review recorded/correction next distinct from acceptance; Inspect next turn is an optional read.

Independent visual/semantic review accepted Today desktop/mobile, Meta-CEO desktop/mobile and UX00–UX04 at their reviewed states; the principal inspected UX05 and the final refinements. This proves editable design, fit and contract clarity, not functioning navigation or action. Enabled message/create/decision specimens describe a qualified target state; the present read-only slice must retain unavailable/preview behavior until its owner capability is actually accepted. There is no synthetic send, save, success receipt, deployment, background worker or production acceptance in this commission.

Builders must map every implemented field to the current DTO, preserve the exact source/permission/operation fences and run the fifteen slice-appropriate scenarios. The first missing capability is a real integrated journey in the application, followed by separately qualified action composition. No protected merge, source-custody transfer, runtime actuation or installed qualification follows from design completion.
