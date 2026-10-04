# Mastermind OS — Daily Experience Builder Flow Specification

**Stage:** `DESIGN_CONTRACT` — reviewable design and builder contract; not live product qualification.
**Target repository path:** `docs/design/MASTERMIND_OS_DAILY_FLOW_SPEC.md`.
**Original protected implementation census:** `mastermindx-market-intelligence/Mastermind@a2646f458f9ff41ddcedd89b338be4a4349e6cd6`.
**Current continuation compatibility pin:** `5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f`; the bounded comparison from `3ac05a00dacde2c06893f5f15082b703d2c04463` is one commit with 104 changed files and no `app/` or Paper bridge changes (§18.4). The targeted Sources/access audit reads six relevant files at this exact pin; it is not a full audit of that delta. Prior compatibility pins and their evidence remain recorded in §§18.2–18.3.
**Design source:** approved Atelier visual direction, the current five-destination OS shell, and the daily-flow design decisions made in this Chairman-requested commission on 4 October 2026.
**Paper:** file `01M3NRCX55B452A12819WNE1RH`, page `p-E-0`, “13 · Daily Experience · Flow + Builder Notes”.
**Illustration rule:** every person, count, message, decision, outcome, project, status, and timestamp in a mockup is illustrative unless separately qualified by its current canonical owner.

### Builder reading order

1. Read UX00 and §1 for the daily loop, durable responsibilities, and current implementation boundary.
2. Use §2 and the actual action maps in §§6.4 and 11.1–11.2, plus the Sources/access maps in §11.7, to connect the exact screen family. Start with the read-only slice in §15.
3. Apply UX01–UX04 and UX06–UX11 with §§10–14 for source states, draft continuity, message outcomes, recovery, keyboard and return behavior. UX08/UX09 specify Search/Knowledge → exact source → explicit unsent append → original return (§§11.2–11.6). UX10/UX11 specify Sources/read availability/recheck and access/cancel/actual return (§11.7). The intended default composer is Options + Send; hidden historical controls are not instructions to restore their former behavior.
4. Build the slice-appropriate fixtures and run §§16–17 against the real application. Record the tested source revision and actual results; the Paper review is design evidence only.

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
General Search, Knowledge collections, general evidence-source opening, a composer, and Add to draft remain absent at the continuation pin. The implemented exact-result reader is a bounded five-key read, not a general source or search capability [S28–S30].
The exact current-pin audit confirms that Connections is a Mission relationship graph/list, not a source integration inventory. There is no source-status, enrollment, reconnect, service-start, send, or arbitrary-URL command in the app host. Sources/access overview and SA01 detail are target designs using separately qualified owner reads, not newly implemented APIs [S35–S39].

## 2. Paper directory and screen lineage

New UX artboards are explanatory flow/state contracts; existing AT/CH screens remain the visual component lineage.
The earlier directory identifies ten workflow notes UX00–UX09, all read back from the exact Paper page. UX08/UX09 extend the earlier eight notes. Their static review and remaining product amendments are recorded in §§11.6 and 19. The current Sources/access continuation adds UX10/UX11 on that same page, bringing the guide family to twelve; the exact new roots are recorded below. The supplied index-update response and reviewed UX00/directory/AT00-entry screenshots now name UX00–UX11, SA01 and the current compatibility pin (§19.1). The page is an editable storyboard and builder note set; the accepted Paper catalog exposes no prototype-link operation, so working click-through behavior is not claimed.
Desktop and mobile variants share the same source-state and effect semantics.

| Label | Content | Paper ID | Existing screen lineage |
| --- | --- | --- | --- |
| UX00 | Daily directory, shell, route and owner map | `PBO-0` | AT00 `KSB-0`, CH91 `KDN-0` |
| UX01 | Today attention/decision state matrix | `PBP-0` | AT01 `LNV-0`; mobile `N27-0` |
| UX02 | Direction, office/project conversation, named project flow | `PBQ-0` | AT03 `MHD-0` / `N29-0`; AT14 `N8N-0` / `NBB-0` |
| UX03 | Decision packet and closure | `PAY-0` | AT20 `OU0-0` / `P0I-0`; AT08 `L9V-0` / `MNS-0` |
| UX04 | Recovery, scope switch, evidence detour, return | `PAZ-0` | CH0 `JB4-0`, CH1 `IZB-0`, CH2 `JLU-0`, CH7 `KBA-0` |
| UX05 | Builder slice, capability gates, acceptance scenarios | `PBR-0` | all applicable lineage |
| UX06 | Conversation selection, source and empty-state contract | `SMO-0` | CV01 `SD8-0` / CV01M `SI5-0` |
| UX07 | Composer stages, detour continuity and original-message recovery | `SMP-0` | CH1/CH2/CH3/CH6/CH7 |
| UX08 | Search/Knowledge, exact source reading and return | `SXT-0` | AT05 `L0Z-0` / `MNM-0`; AT06 `L3N-0` / `MNN-0`; KD01 `SPU-0` / `STU-0` |
| UX09 | Unsent source append, added-state, mobile payload/details and conditional Undo | `SXU-0` | KD01 and original CH1/CH6 scoped draft; KD02 product variant unverified |
| UX10 | Sources, read availability and bounded recheck | `T7J-0` | AT07 `L6N-0` / `MNO-0`; SA01 `T0U-0` / `T0V-0` |
| UX11 | Access, cancel and actual-origin return | `T7K-0` | AT07/SA01 and original permitted Search/reading origin |

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
| AT04 Inbox | `KY5-0` / `MNL-0` | qualified reserved Chairman decisions; selected item to AT20, preserving filter and origin; team reviews through Projects |
| CV01 Conversations | `SD8-0` / `SI5-0` | primary Conversations destination; durable office or exact permitted project selection; bounded metadata filter |
| AT05 Knowledge | `L0Z-0` / `MNM-0` | reusable permitted knowledge; exact source detail; explicit Add to draft is not Send |
| AT06 Global search | `L3N-0` / `MNN-0` | Search/keyboard shortcut; visible scope; result opens exact permitted object; Close returns prior view |
| KD01 Source reader | `SPU-0` / `STU-0` | exact permitted source from Search or Knowledge; explicit Add to draft; Back/Close restore the actual origin; open mobile label/details amendment in §11.6 |
| AT07 Sources and access | `L6N-0` / `MNO-0` | source/access overview; Sources/Preferences tabs; exact source detail to SA01; contextual entry retains actual origin; §11.7 |
| SA01 Source read recovery | `T0U-0` / `T0V-0` | exact GitHub evidence metadata with full-content read unavailable; bounded owner recheck and actual reading/Search return; §11.7 |
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
| AT21 Receipt study | `P2V-0` / `P8L-0` | concurrent reference retained; use UX03 for this commission's completed receipt/recovery contract; mobile directory identity observed at close-out |
| CH0 / CH4 Welcome | `JB4-0` / `K3D-0` | new composition draft defaults to Meta-CEO/company; starter prompt appends, never auto-sends |
| CH1 / CH6 Project conversation | `IZB-0` / `K5X-0` | Sol with exact project context; evidence detour to CH2; unknown outcome to CH7 |
| CH2 Evidence / CH3 Context | `JLU-0` / `JV7-0` | companion to same conversation; preserve draft, selection, reading anchor and focus |
| CH7 Delivery recovery | `KBA-0` mobile | original-message status and no duplicate send; UX04 expands the recovery contract |

AT12/AT12M and AT13 remain retained earlier Session Estate/orchestration studies. AT15 is the current composition reference for that route. AT16–AT21 were observed as concurrent studies and were not modified by this commission; their current owner/source gates remain in force.

A bounded directory read at close-out on 2026-10-04 also observed another session's ongoing extension: AT22 Local Delegation Preview (`PK4-0` / `PXW-0`), AT23 New Web Session Preview (`PR3-0` / `Q1O-0`), and AT24 Activation Receipts (`Q50-0`; only desktop observed in that read). These are preserved concurrent references, not newly reviewed or implemented capabilities in this commission. Open their current owner notes before wiring those advanced actions. Their preview/release limits do not impose an extra Chairman approval on ordinary supported messages or routine in-policy follow-through. The directory snapshot is bounded; do not infer that an unlisted counterpart or later board is absent.

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
| Inbox: Review decision | `LSS-0` / `MW0-0` | navigation once to exact AT20/AT20M; preserve Inbox item and filter |
| Inbox: Evidence | `LSN-0` / `MVV-0` | permitted evidence with exact decision context and origin retained |
| Inbox: Projects footer | `LSZ-0` / mobile equivalent where exposed | AT02; team obligations stay with project owners |

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
| `inbox` | Find current reserved Chairman decisions | exact owner item, independent coverage, filters | feed capability absent in baseline |
| `decision.packet` | Review and choose for one exact item | complete current owner packet and revision | fixture/preview until qualified decision capability |
| `conversations` | Select office or exact project in CV01 | qualified office binding and permitted known project/topic metadata | directory feed absent; current-window-only baseline stays constrained |
| `conversation.office` | Ask durable Meta-CEO office | current office binding; company/decision context | design requirement; no guessed session binding |
| `conversation.project` | Ask current project Sol | current project binding; To + About | current permitted window only where admitted |
| `knowledge` | Find reusable knowledge and evidence | canonical search/read scope | Evidence entry first; general search separately qualified |
| `search` | Find an exact permitted object | query, explicit scope and source-backed result pointer | general search capability separately qualified |
| `settings.sources` | Understand access and missing source coverage | independent account, acquisition/content permission and owner read state | existing auth/read facts; no invented connection authority |
| `settings.sources.detail` | Diagnose one exact admitted source-read limitation | existing owner/ref/revision, permitted metadata, read outcome, complete nested return context | SA01 target; exact owner read separately qualified; no generic source-status API |
| `settings.preferences` | Inspect supported user preferences in AT07 | existing approved preference controls and current view context | collapsed contextual target; no account enrollment or source-control capability inferred |
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

### 6.4 CV01 — conversation selection and coverage

Primary **Conversations** opens CV01/CV01M. The office entry opens the one durable Meta-CEO office; a project entry opens that exact project's current permitted binding. A topic title, recent sidebar row, provider tab, or newest session is never sufficient identity. Directory metadata and conversation content have separate permission checks. Known metadata may remain visible while conversation content is unavailable only when its owner independently permits that metadata. The protected app currently exposes a permitted window, not a conversation list; CV01 is a qualified target design, not an implemented feed [S7, S22].

**Find by project or topic** filters only metadata supplied in the admitted directory scope. It does not search full history, hidden message bodies, other accounts, or missing sources. Keep the scope/coverage caveat when filtering. A cleared filter restores the admitted rows; it must not trigger a guessed session lookup. Office availability is independent of the project filter.

| Directory state | Required presentation |
| --- | --- |
| permitted known rows, partial coverage | show those rows and incomplete-coverage note; no exhaustive count |
| filter has no matches | “No matches in the available projects and topics”; Clear filter; retain coverage |
| bounded source returns no rows | “No conversations were returned in this available scope”; no company-wide empty claim |
| fresh complete permitted scope is empty | scope-qualified empty state; office remains independent |
| unavailable source or binding | explain unavailable scope; permitted known metadata only; no inferred empty history |
| stale/historical rows | show qualified observation time; revalidate the exact binding before opening current content |

Terminal's metadata-visible/content-unavailable example offers **Open project** only when the separate exact Terminal project read is permitted. AT03/AT03M supplies the visual template, whose illustrative Mastermind OS content must be replaced with Terminal's canonical project reference and its own admitted selection. Never route Terminal to the fixed Mastermind OS example or borrow its Mission root. Without separately permitted project access, expose source/access details instead of an enabled fallback.

Return restores the original permitted filter, selected row, reading position and actual originating focus; an existing scoped draft remains with its recipient/project. Revalidate permission and binding before restoring protected text. If the origin vanished, offer an honest permitted directory state without guessing a replacement. **New conversation** opens CH0/CH4 composition only: no new office, project record, transcript, Runtime job, or provider session. Draft retention means this authorized open view unless an existing approved persistence path proves more.

| CV01 action | Desktop / mobile control | Exact connection |
| --- | --- | --- |
| Open office | `SKC-0` / `SLZ-0` | AT08 / AT08M, canonical office |
| Open Work visibility | `SKZ-0` / `SM3-0` | CH1 / CH6, exact Mastermind OS project context |
| Open accessible Terminal project | `SLC-0` / `SMG-0`; named `CV01.OpenTerminalProject.withExactProjectRef` / `CV01M.OpenTerminalProject.withExactProjectRef` | AT03 / AT03M template with exact Terminal identity |
| Sources and access | `SLI-0` / `SMK-0` | AT07 / AT07M; retain directory return context |
| Local metadata filter | `SKI-0` / `SLP-0` | admitted project/topic metadata only |
| New composition draft | `SHT-0` / `SJG-0` | CH0 / CH4; no creation effect |
| Open primary navigation | existing desktop shell / `SJM-0` | five destinations; no binding mutation |

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

AT04 **Needs you** contains actual reserved Chairman decisions supplied by their current owners. A non-actionable team review is removed from this list, including hidden source layers that could accidentally become a rendered row. Team review remains discoverable through Projects and its accountable owner; it is not an approval request. The footer opens Projects. **Review decision** navigates directly to the one exact AT20 packet; it is not a preliminary review preview followed by another navigation ritual. Packet evidence preserves its decision identity, choice draft, revision and Inbox origin. These are illustrative target behaviors; the protected app still lacks the decision feed and recording command.

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

### 11.1 CH conversation, evidence and context continuity

CH1, CH2, CH3 and CH6 depict the same sent message, **“Keep this moving. What’s still missing before release?”**, and the same separate unsent draft, **“What evidence is still missing?”**. The examples are illustrative; actual protected content remains the owner's current permitted window. Opening Evidence or Context cannot send, replace that draft, attach a context pack, change To/About, or rebind the conversation. Reading a pack does not select it for a later message. **Add to draft** is an explicit permitted append to the existing scoped draft, visibly preserving prior text; it never sends or records a separate effect.

| CH screen | Verified controls | Connection / continuity |
| --- | --- | --- |
| CH1 `IZB-0` | Options `JAR-0`; Send `JB0-0`; Evidence `JA2-0`; Context `J84-0` | current project composition; Evidence→CH2; Context→CH3 |
| CH2 `JLU-0` | Options `JQ2-0`; Send `JQ6-0`; Back `JLW-0`; draft `JQ0-0`; reading scope `JPZ-0` | same draft and recipient; Back restores CH1 origin |
| CH3 `JV7-0` | Options `JVL-0`; Send `JVD-0`; Add to draft `K2Y-0`; Close `K0E-0` | explicit append only; Close preserves CH1 composition |
| CH6 `K5X-0` | Options `K96-0`; Send `K9F-0`; Evidence `K8T-0`; Context `K6G-0` | mobile same exact project/draft; detour uses corresponding permitted context |
| CH7 `KBA-0` | Options `KBO-0`; paused Send `KBG-0`; Check original `KDH-0`; next draft `KBE-0` | original uncertain operation remains bound; next draft is not a retry |

These IDs identify design controls, not effective command ports. Supplemental unavailable/read-only variants preserve unsupported Send as disabled with explanation. Options opens only supported composition/context choices and has no effect by itself; it cannot adopt a plan, switch an uncertain operation's owner, create a runtime, or manufacture retry authority. Return restores actual previous focus; mobile return from an evidence/context read must not focus the textarea and open the keyboard unless that was the user's actual prior focus.

### 11.2 Search/Knowledge → exact source — UX08

This is a **DESIGN_REQUIRED** connected journey. The protected app supplies bounded Mission Evidence and an exact-result reader; it has no general Search/Knowledge feed, general source reader, composer or Add-to-draft capability [S28–S30]. A static result row, source excerpt or button is not evidence that its owner feed or command is implemented. Qualify each read and composition capability through the existing owner before enabling it.

Search opens AT06/AT06M (`L3N-0` / `MNN-0`) with the actual query and visible scope. Its filters are **All, Projects, Conversations, Knowledge**; there is no People category in this commission. Knowledge opens AT05/AT05M (`L0Z-0` / `MNM-0`) with **All, Decisions, Artifacts, Discoveries** and independently reported coverage. Search may find permitted metadata; selecting a result does not prove its source content was read or that the result is current. Result kinds open their exact existing project, conversation, decision or source destination. Knowledge decision rows navigate to the exact decision packet, retaining their Knowledge origin; they do not record a choice.

| User action | Desktop control / mobile control | Connected design destination and retained context |
| --- | --- | --- |
| Search: open source | `M3A-0` / `MYR-0` | KD01 `SPU-0` / `STU-0`; exact source pointer, query/filter/result and actual origin retained |
| Knowledge: review source | `LZX-0` / corresponding mobile source control `MWX-0` | KD01; exact Knowledge selection and filter retained; no content or reuse inferred from row selection |
| Knowledge: search | `LT8-0` / `MW9-0` | AT06/AT06M with explicit scope and Knowledge as return origin |
| Knowledge: review decision | `LZN-0` / `MWP-0` | AT20 `OU0-0` / AT20M `P0I-0`; current exact packet and decision owner guards |
| Knowledge: Sources | `M0O-0` / `SVU-0` | AT07 `L6N-0` / AT07M `MNO-0`; preserve Knowledge origin |
| Search: Sources | `MD0-0` / `MZC-0` | AT07/AT07M with Search origin retained; no automatic reconnect |
| Search: Close | `L3R-0` / `MS9-0` | actual originating permitted view; no fixed return to Today |
| KD01: Add to draft | `SWW-0` / `SXN-0` | one explicit permitted insertion into the eligible original scoped draft; never Send |
| KD01: source details | source provenance panel / `SXF-0` | reviewable source identity, exact excerpt, label, revision, clocks, coverage and permission state; no new read authority |
| KD01: Back / Close | `SVH-0` / `SRA-0`; mobile `SUZ-0` / `SUT-0` | actual permitted Search, Knowledge or conversation origin; nested return keeps the full origin chain |

Wire each control to its exact containing row and owner-supplied source pointer. IDs identify this design snapshot and do not serve as canonical source identities. Back from a reader reached through Knowledge returns to Knowledge; Back from a reader reached through Search returns to that Search state; closing Search then returns to its own origin. A reader reached from a conversation detour preserves that same conversation. Sources is a scoped diagnostic detour, not a new account, reconnect, content-access or execution grant.

### 11.3 Source identity, clocks, permissions and states

An exact source pointer retains the existing owner's canonical ref and revision/digest where supplied, the permitted project scope, and the source kind. Do not treat a display title, search query, selected row, project reference, work reference, Job, Attempt and conversation identity as interchangeable. For the implemented result reader, preserve the exact five-key tuple including `result_envelope_digest`; the bounded navigation index is unvalidated until the independently permitted detail read passes the closed decoder [S29]. A generic source reader needs its own existing-owner contract; do not fabricate an endpoint from a Paper route.

Display source-currentness/freshness and observation recency independently. Source time describes the source event or publication; revision identifies the admitted version; observed-at describes the bounded read. A successful fetch or recent observation is not proof of latest revision, complete coverage, ongoing permission, acceptance or release [S28, S30]. Missing clocks stay unavailable. Stale or freshness-unverified material may be read/reused only when the owner permits it and its limitation remains visible; no append silently upgrades its freshness. The illustrative source label below is a human-readable label, not the complete canonical pointer.

| State | Required visible behavior and capability boundary |
| --- | --- |
| query empty | show permitted orientation or an honest prompt; no invented recent history or global completeness |
| searching / source loading | preserve query, origin and eligible draft; result selection is not yet admitted content |
| partial coverage | show known permitted rows and a concise coverage limit; no company-wide total or zero-result conclusion |
| bounded query-empty / local-filter-empty | distinguish no results in the admitted scope from a filter hiding known results; Clear filter does not broaden permission |
| unavailable / disconnected | show which Search, Knowledge or source read is unavailable; no manufactured empty collection |
| metadata allowed, content refused | show only independently permitted metadata; clear protected excerpt and disable Add; metadata access does not authorize reading |
| freshness unverified / historical | label the supplied revision and clocks; do not show Fresh solely from a recent read |
| exact source available | show admitted identity, excerpt, label and source limits; reading alone does not select it for composition |
| source changed before Add | visibly identify the changed revision/content, require a new review of the exact payload, and keep the original draft; no silent substitution |
| Add unavailable / no eligible draft | explain the missing composition or target capability; choose an existing permitted conversation through CV01/CV01M where supported; no automatic conversation/project creation |
| source added, still unsent | review the inserted payload and source label alongside the preserved draft and To/About; repeated Add cannot duplicate that same insertion |
| permission or auth generation changed | immediately clear rendered/in-flight protected content and prevent append; retained draft follows the current approved policy only |

Acquisition/search metadata, source-content access and draft-composition permission are separate owner checks. Before opening, adding or restoring protected source text, validate the applicable current permission and binding. An auth-generation boundary invalidates old and in-flight source detail before reacquisition, even when the public auth display is unchanged [S30]. A source revocation does not erase arbitrary newer user text by guesswork; follow the existing approved retention/redaction policy and never restore revoked text from another cache.

### 11.4 Explicit source append, unsent payload and conditional Undo — UX09

The illustrative eligible draft remains **To Project Sol · About Mastermind OS · Topic Work visibility**, with original unsent text **“What evidence is still missing?”**. The exact excerpt is **“Source freshness still needs verification against the current source.”** The full source label is **“Work visibility review pack · v2 · Mastermind OS · Freshness unverified”**. These are design fixtures, not current source observations.

Opening the reader, reviewing details, highlighting an excerpt, choosing a row, or returning cannot attach or send it. Explicit **Add to draft** validates the current exact source payload and the original eligible scoped draft, then appends the following plaintext quote and source label while visibly preserving the original text:

```text
What evidence is still missing?

“Source freshness still needs verification against the current source.”
Source: Work visibility review pack · v2 · Mastermind OS · Freshness unverified
```

The insertion contains the reviewed source representation; it does not establish current freshness, adopt a plan, record a decision or dispatch a message. Preserve its exact owner/ref/revision association using the existing draft facility when that facility supports it. Do not add a transcript, search/memory cache, attachment registry, command queue, background operation or new persistence plane to manufacture that association. If the build has no approved composition capability, Add remains unavailable and this payload is a review specimen only. Draft retention means the authorized open view unless an existing approved persistence path independently qualifies more.

Use one bounded insertion with the original draft identity/revision and reviewed source identity. Repeated activation for that same retained insertion must not duplicate it. A changed source revision or intervening user edit is visible and requalified before another explicit insertion; do not deduplicate unrelated user text merely because its words match. A late source response cannot append to a different recipient/project or overwrite text typed after the reader opened. If no eligible draft exists, an explicit supported choice through CV01/CV01M may select an existing permitted conversation; it is navigation only and never mints a conversation, project, session or Runtime root.

The added-state review, mobile payload/details and **Undo** behavior are specified on UX09 (`SXU-0`); there is no verified KD02 product variant. Show “Added to draft · Not sent” only after the existing draft facility confirms the insertion. Show Undo only when the existing draft owner can reverse the exact unchanged insertion under its supported revision policy. It removes only that insertion and preserves prior text. If that capability is absent, or newer typing, source change, target change or revision mismatch makes removal ambiguous, offer **Edit draft** instead; never erase newer text, a submitted snapshot or an original pending operation. Do not invent Undo history, a registry or a durable mutation ledger to implement this conditional affordance.

UX09's note specimens are after-append text `SZO-0`, Return `SZQ-0`, conditional Undo `SZS-0`, mobile exact-payload amendment `T0E-0` and expanded-source details `T0K-0`. They explain required states and connections; they are not effective product controls or proof that the KD01 amendment or a KD02 added-state variant exists.

An unresolved prior Send remains tied to its immutable submitted snapshot and existing owner operation. Adding to the separate next unsent draft does not retry, replace, resolve or retarget that original. The new backend receipt `work_ref` preserves original launch provenance; it is not evidence of the current selected Program/Mission association or message delivery [S27, S31].

### 11.5 Dynamic origin, focus, IME and mobile payload review

Use the existing view-state facility to retain the actual origin route, exact project/conversation binding, To/About, draft identity/revision, query/filter, selected result, reading anchor, scroll and focused control. Nested reader→Sources→reader→Search/Knowledge returns follow the actual chain. A fixed “Back to conversation” target is valid only when that conversation was the real permitted origin. Revalidate permission and binding before restoring protected content; if the origin vanished, present an honest permitted directory/unavailable state without guessing a replacement. Original operation recovery remains reachable independently.

Opening the source reader moves focus to its accessible heading or appropriate dialog entry; Back/Close restores the actual prior control where it still exists, or a sensible permitted fallback. Add announces one concise unsent insertion status and keeps the payload reviewable without silently sending or changing To/About. Background rereads do not steal focus. Search Escape/Close restores the prior origin rather than always focusing a composer. Mobile reader return opens the keyboard only when the composer actually had prior focus and its current permission permits restoration. Preserve the reading anchor and safe-area access to Back/Close/Add; details must be reachable without depending on truncated text.

IME composition Enter never selects a Search result, triggers Add, closes the reader, or sends. Outside composition, Enter in the query searches and Enter on the focused result opens it; result arrows stay within the list, while Tab follows normal controls. Shift+Enter in a draft adds a newline. Reader quote text is readable source content, not an editable substitute for the original draft. Verify actual 320/390 px wrapping, expanded text, keyboard, focus order, status announcements and 44 px targets in the implementation. Desktop/mobile mockups do not establish executed accessibility acceptance.

### 11.6 Paper effect custody and open mobile amendment

The KD01 desktop/mobile roots are `SPU-0` / `STU-0`. Read-only review requires the mobile reader to visibly label both the exact excerpt and the full source label from §11.4, and expose reviewable source/payload details through `SXF-0`. Final parent review also found that the status time/icons (`SVB-0` / `SV4-0`) and Close label (`SX6-0`, in `SUT-0`) are present as nodes but not visibly legible in the screenshot; restore their explicit light-on-ink rendering and recheck the header. These are **open product-screen amendments**: modifications to those roots are deferred under the unresolved duplication fence. Do not claim that the current mobile product screen already satisfies these requirements. UX09 supplies the added-state/mobile-payload/details/Undo specification while the product amendments remain outstanding.

The direct Mastermind Paper `duplicate_nodes` operation `mm-knowledge-flow-added-state-shells-20261004-001`, attempted against `SPU-0` / `STU-0`, returned non-JSON error text beginning `McpServerE…`; the old response wrapper failed to retain the full raw reply. Its effect remains **EFFECT_UNKNOWN**. Two same-carrier `get_basic_info`/`get_children` observations found no duplicates and 68 total boards; unchanged counts are bounded observation, not authoritative known-no-effect evidence. No KD02 product variant was observed or verified. No retry, replacement operation ID or carrier change is authorized by those observations.

The protected bridge has no operation-receipt/status store: its operation ID is correlation only, and edit-dispatch exceptions or upstream tool errors may have partial effects [S32]. Reconcile on the original direct carrier if definitive original evidence becomes available. Until then freeze that logical duplication and overlapping product targets; the fence is not a file/page-wide lease, and disjoint admitted guide artboards can continue [S33]. The static review and source diagnostic do not close this effect uncertainty or certify the requested mobile amendment.

A separate final note-text operation, `mm-knowledge-guide-mobile-chrome-amendment-20261004-001`, also returned `McpServerError: Connection timed out.` with `isError: true`, `error_code: UNAVAILABLE` and `type: mcp_network_error`. It attempted to change only UX09 leaf `T0J-0` to “Show full payload above Add; keep the draft visible. Make status and Close legible.” The improved wrapper preserved this full error response. Original-carrier `get_node_info` still observed “Show this full payload above Add; keep the original draft visible.” This operation also remains **EFFECT_UNKNOWN**; the unchanged text is not definitive no effect. No retry or carrier switch occurred. Fence that logical text change and leaf; retain the already reviewed UX09 layout and previously confirmed conditional-Undo/payload edits. The mobile header finding is recorded in this document even though its final Paper note amendment is unconfirmed. Owned working indicators were subsequently released through the original carrier; releasing an indicator does not settle either content effect.

### 11.7 Sources and access → exact read recovery → actual return — UX10/UX11

This is a **DESIGN_REQUIRED** daily diagnostic detour. The current protected app exposes authentication and fixed bounded reads; it has no source inventory/status endpoint, enrollment/reconnect command, service control, general GitHub reader or arbitrary-URL bridge [S35, S37]. Existing **Connections** presents source-derived Mission relationships in Graph/List modes, preserving missing joins. It is not AT07's source-management implementation [S35]. Map each design field to an independently admitted owner fact before wiring a real read; route keys and Paper control IDs grant no transport or effect capability.

The daily question is **what can I read here, what could not be established, and where can I continue without losing my place?** Sources/access should keep that answer close to the user's actual task. It is a contextual destination reached from Today, Conversations, Search, Knowledge or an evidence reader; it does not become a sixth primary shell destination. Preferences is secondary and collapsed. Its controls expose only supported preferences, never registration, enrollment, service administration, provider selection or action authority merely because a setting is visible.

#### 11.7.1 Product frames and exact control map

AT07/AT07M remain `L6N-0` / `MNO-0`, refined as the overview. New SA01 `T0U-0` is the 1600 × 1040 desktop detail at x=0,y=8120; SA01M `T0V-0` is the 390 × 844 mobile detail at x=1680,y=8120. UX10 `T7J-0` / UX11 `T7K-0` are 1600 × 1120 guide roots on Page 13 `p-E-0`, at x=0/1680,y=6250. These IDs and placement record the current continuation's supplied Paper snapshot. They are editable design references, not executed navigation.

| User action | Desktop / mobile control | Exact target and permitted behavior |
| --- | --- | --- |
| AT07 Sources tab | `MD9-0` / `T0X-0` | Sources/access overview; show independent facts for admitted sources; no automatic recheck or reconnect |
| AT07 Preferences tab | `MDB-0` / `T0Z-0` | supported preference presentation in the same context; retain actual originating view and source selection |
| AT07 collapsed preferences | `MDJ-0` / `N04-0` | expand/collapse supported preferences only; no source/access mutation inferred |
| AT07 exact source detail | `MEU-0` / `T19-0` | SA01 `T0U-0` / SA01M `T0V-0`; preserve exact selected source metadata and nested origin chain |
| AT07 Back to reading origin | `MH4-0` / `N1A-0` | restore the actual originating Search/reading view, including query, filters, selection, scroll, focus and eligible scoped draft; Search is this specimen's origin, not a universal fixed target |
| SA01 Back to overview | `T4L-0` / `T4D-0` | AT07/AT07M with the same exact source selection and return chain; navigation only |
| SA01 Close | `T3Z-0` / `T4H-0` | actual permitted reading origin; do not force Today, overview or a composer |
| SA01 Recheck source read | `T62-0` / `T76-0` | one fresh bounded read through that exact source's existing owner contract, only when available and permitted; no send, source-control action or unknown-write replay |
| SA01 Back to Search | `T6O-0` / `T7D-0` | explicit Search branch using the preserved query/filter/selected-result/scroll/focus; preserve the original draft and its To/About/Topic |

The two back/close purposes stay distinct: **Back to overview** returns one level within Sources; **Close** exits to the actual reading origin. **Back to Search** is an explicit alternative to continue the recorded search. The overview's back action follows the origin saved when that overview was entered. A real entry from Knowledge or Conversations restores that origin instead of silently redirecting it to Search. The optional desktop Open project control is removed from the active layout and excluded from this route map, keeping the same focused Recheck/Return choices on desktop and mobile. The principal confirmed computed `display: none` and inspected a fresh full SA01 screenshot without it; the node remains in the document and is not claimed deleted. Exact permitted project context remains available through normal Search/Projects navigation.

#### 11.7.2 Exact illustrative recovery specimen

The supplied example keeps query **source freshness**, **To Project Sol · About Mastermind OS · Topic Work visibility**, and separate unsent draft **“What evidence is still missing?”**. The exact displayed source reference is **“Work visibility review pack · v2”**, associated with GitHub evidence in the Mastermind OS project. The display title is not the complete canonical owner/ref/revision pointer; the implementation must carry that pointer only when its owner supplies it.

The state is **metadata available; full content read unavailable; cause unknown; freshness unverified; source time not supplied; observation time not supplied**. Showing v2 does not prove latest revision. The example neither supplies a read timestamp nor authorizes the product to synthesize one from the browser clock. Source metadata may remain visible only under its independent permission. Full source text, a reconstructed excerpt, Add to draft and hidden cached content remain unavailable while the source-content read is not admitted. The eligible original user draft is retained only under the existing approved draft policy; no new autosave or durability claim is introduced.

The verified desktop copy is **“Some content couldn’t be read.”** followed by **“Project metadata is still available. The cause of the incomplete read hasn’t been established.”** The verified mobile copy is **“Project metadata is available. Some content couldn’t be read; the cause is unknown.”** Details show the exact reference and project, independent metadata/content state, source-reported freshness, missing clocks and any admitted reason. Do not transform unknown cause into “Permission denied,” “Token expired,” “GitHub disconnected,” “Service stopped” or “Reconnect required.” On a generic failure retain the same limited truth; on a later specifically admitted refusal display its actual qualified cause. The protected web client collapses ordinary non-OK reads—including 401, 403 and 503—to `READ_FAILED`; App then also collapses many failures to `SOURCE_UNAVAILABLE`. Only the exact Result route can surface its validated typed 503 unavailable envelope [S37].

#### 11.7.3 Independent status and permission facts

| Fact axis | Honest states / required display | Evidence boundary |
| --- | --- | --- |
| Sign-in setup and authentication | setup pending; signed out; signing in; signed in/error as actually supplied | configuration/auth state, not source health or enrollment proof |
| Workspace acquisition access | resource token available/unavailable, plus actual admitted workspace read outcome | Programs/Mission/Result acquisition is separate from Conversation content |
| Conversation content access | resource token available/unavailable, plus admitted permitted-window outcome | content refusal may leave acquisition usable; no general source-content grant |
| Exact evidence metadata/content | independently permitted metadata versus full source read admitted/unavailable | metadata or selected result title never grants content access |
| Read availability | not checked; checking; admitted response; read unavailable | successful read is bounded to its actual owner/selection; no universal integration health |
| Freshness and clocks | source-reported freshness; source time; observed-at; revision; projection time when provided | each is separate; missing stays not supplied; recent fetch/render never establishes latest/fresh/current |
| Coverage | admitted complete/partial/gap/history limit or not established | missing feed/references cannot become zero work, empty history or all-clear |
| Action capability | viewer/read-only; capability absent or separately qualified owner capability | source reachability grants no send, restart, reconnect, enrollment, execution or acceptance authority |

Web `acquisition`/`content` booleans mean private unexpired resource tokens exist, not that an enrolled service accepted a read. Public auth status can be `error` with acquisition still true after a failed content transaction [S36]. Keep useful workspace access visible in that state. A badge based solely on `signed_in` must not say all sources are connected. The two protected token resources do not automatically map to general Search metadata or full GitHub content permission; those future reads need their own existing-owner contracts.

The current sign-in flow opens one popup in the direct click gesture, then performs acquisition followed by content authorization using separate one-use PKCE transactions. A new sign-in clears both tokens and reruns the whole flow; there is no isolated content-only retry port. The existing header offers Sign out when either resource remains available, Cancel sign in while signing, and disabled Sign-in setup pending when unconfigured [S36]. Do not wire a seemingly harmless “Retry content sign-in” to a silent replacement of useful access. If a future controlled sign-in action reruns both resources, explain its scope and invoke the existing user-gesture flow. Sign-out is local token disposal, not Auth0 SSO logout, source disconnection or service shutdown. Registration/enrollment is separate operator-owned work [S38].

#### 11.7.4 Recheck, lifecycle and return contract

**Recheck source read** is a known read, performed once against the same exact owner and selector under current permission. If the corresponding fixed read/contract is absent, render it unavailable with a nearby explanation. SA01 does not manufacture a generic endpoint by concatenating its source title or Paper route. The protected example of an explicit read retry is Refresh window, disabled while pending or without content access. Its bounded Conversation path may pair an independently authorized Mission v3 read to assess observation association; it never starts work [S39]. Use that read discipline without treating its content token as a general GitHub grant.

While rechecking, retain permitted metadata, current query and user draft; show checking without advancing freshness or clocks. Cancel or ignore obsolete completions after selection, auth/generation or route changes. A response is shown only after the full applicable decoder and exact-selection validation pass. Invalid/failed content clears protected full text; it cannot be retained as a hidden fallback or appended to a different draft. On success show only the returned qualified facts and their actual clocks. A changed revision is visible, never silently substituted into prior reading or inserted into the retained draft. Success does not auto-open a project, append text, send, adopt a plan or resume an original operation. Repeated activations while pending do not issue duplicate concurrent reads or queue future writes.

UX11's concrete pending-read note specimen uses disabled **Checking evidence…** `TAQ-0` and **Cancel** `TAS-0`, both 44 px high. They are explanatory guide controls, not an additional implemented product route or proof of a running read. A supported Cancel aborts the exact local bounded read or rejects its late completion; it preserves permitted query/draft/return context and supplies no new freshness, permission, outage diagnosis or write-outcome evidence. It does not cancel execution, settle an unknown original write or establish that a submitted action had no effect.

Store the return descriptor through the existing approved view-state facility: originating route and nested reading chain; exact permitted project/conversation/draft identity and revision; To/About/Topic; query and filter; selected result/source; reading anchor, scroll and actual focused control. The current app's browser history restores only an exact Mission pair; richer Search/draft/reading restoration is a builder requirement, not implemented baseline behavior [S39]. Revalidate binding and permission before reopening protected content. If the origin/source disappeared or permission changed, return to a clearly explained permitted state rather than guessing a nearby project, recent session or replacement source. Background rechecks never steal focus; mobile return opens the keyboard only if a composer actually had prior focus and current permission allows restoration.

No Sources action reconciles an unknown write. An original pending/unknown message or command retains its immutable submitted snapshot and existing owner reference while this read detour remains useful. Recheck, sign-in, overview return, Back to Search and Close must never replay, replace, acknowledge, consume or settle it. The two separate Paper operations and their overlapping target fences in §11.6 remain **EFFECT_UNKNOWN** and unchanged; these new disjoint Sources frames and this document do not establish no effect or release the frozen KD01 roots/UX09 leaf.

#### 11.7.5 Separate Company edge capability boundary

Current `COMPANY_CONSULTATION_EDGE.md` describes a separate runtime and service composition, with its Company execution profile disabled and installed native admission/live answer-consumption qualification outstanding [S40]. Root provisioning, explicit incomplete-runtime recovery and an installed Web CEO Sessions send/read_ref flow are not this app's Sources recovery capabilities. The internal delivery/consumption seam is outside the public MCP tool set and does not add a React send/read/status bridge. Native read evidence, confirmed delivery, Wake acknowledgement, Runtime consumption and original-parent RETURN remain separate facts. A `read_ref` read requires the same currently authorized caller/generation/original CONTINUE/physical thread and returns `parent_consumed: false`; it is not authority to read from an arbitrary current UI selection [S40].

Service restart reconciliation operates on persisted exact obligations with required route/retry arming; a stored delivered native read is reduced from its original command, not resubmitted to the provider. Sources cannot infer “ready,” “parent consumed,” “replied” or action permission from a reachable listener, built edge, recorded delivery, or component tests. The protected observed-window DTO still rejects send/provider-control/history capabilities other than false [S38]. No extra approval ritual is added to an ordinary supported read; unsupported execution remains absent.

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
| Search/Knowledge source opening | read/navigation | general capability absent | exact source owner/pointer; metadata selection is not content reading |
| Add source to draft / conditional Undo | local composition | absent in protected source | existing permitted draft owner only; preserve exact insertion/revision and prior text; no Send |
| Refresh current window | read | implemented | content permission; no history/send |
| Sources exact read recheck | read | target capability; only existing fixed reads are implemented | exact admitted owner/selector and current permission; no generic status API, reconnect, service start or write replay |
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

### 12.1 Message composition and delivery stages — UX07

The composer and original message have separate state. UX07 describes their qualified target behavior; the current protected slice remains read-only. Rendering a realistic Send specimen is not proof of an authenticated message owner or transport. Show unsupported capability independently of whether the permitted draft contains text. Permission/generation changes follow the existing auth fence; they never certify receipt, delivery or no effect.

| State | Required fact and visible behavior |
| --- | --- |
| available, empty | permitted supported composer; no ready message; Send disabled; no new operation |
| available, nonempty | current exact recipient/project and supported send capability; one ready Send |
| unsupported/read-only | “Sending is not available in this build”; permitted draft remains; keyboard cannot submit |
| sending | original submitted snapshot and operation retained; prevent duplicate submission of that operation |
| accepted, awaiting delivery | matched owner acceptance/recording; explicitly still awaiting delivery |
| delivered, awaiting reply | delivery owner proves delivery for the exact message; no inferred reply or responding state |
| uncertain original | request may have effected; outcome unresolved; Check original only where status read is supported |
| authoritative known-no-effect rejection | owner establishes exact operation had no effect; show reason and permitted correction/retry choices |
| response received | permitted response belongs to the exact conversation/message context; response text is readable within owner scope |

Use **Sent**, **Delivered**, or **Responding** only when the owner actually evidences the named stage. Client submission does not mean Sent; acceptance does not mean Delivered; delivery does not mean Responding. A spinner, elapsed time, adjacent transcript message, server transport success, or generic generated answer cannot fill the missing stage. Owner-projected generation may support a responding indication only with its exact message association; generation is not business acceptance, project creation or release.

At submission capture the immutable message snapshot, draft revision, exact recipient/project and existing owner operation identity. A delayed acceptance/receipt may clear only that submitted snapshot under the owner's acknowledgment policy. It must never erase text the user typed afterward, including a newer draft with coincidentally identical words. Keep the submitted original and next unsent draft visibly distinct; typing the next draft does not submit it or replace the original tracking identity. Do not add a second transcript store, directory registry or client command queue to provide this presentation.

Transport aborts, timeouts, permission changes and a `not_found` status do not establish no effect. Uncertainty remains with the original operation, principal context and owner. Do not resend it, switch its scope, fail it over to another provider, or start a new operation to evade uncertainty. Read the exact original status when supported. If status is unsupported, explain the limit and retain the original reference for existing-owner reconciliation. Authoritative known-no-effect evidence permits a new explicit attempt only after current scope, content, capability and owner guards are requalified; never auto-replay a rejected message.

Navigation and evidence reads can remain useful while an original message is unresolved, subject to current permission. They must preserve recovery identity without implying continued execution or a terminal result. A later response or newer message resolves only the operation its owner actually associates with it. An answer received is not a command effect, review verdict, accepted outcome or released artifact.

Desktop Enter sends once only for a ready supported draft. Shift+Enter inserts a newline and IME composition Enter never sends. Mobile uses the explicit supported Send control; newline/return is composition. Options and detour closure restore actual focus without stealing it during source refresh. Show stage changes through concise accessible status, keeping the draft readable and recovery reachable rather than repeatedly announcing unchanged observations. Actual keyboard and assistive-technology behavior remains unexecuted build acceptance.

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
The original census directly re-read both candidate PRs on 4 October 2026: #1046 was open/draft at `089a745b9aa4a4f2ec615827912f547f3884d744`; #1150 was open/draft at `37d02586eeb97d92e6fb9ed6dbc7cd142dd6449c` and was a launch-only candidate. Preserve these as dated custody observations; the continuation's later heads are recorded in §18.2. Neither observation is protected implementation or installed proof.
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
| F13 — source recovery specimen | query source freshness; exact Work visibility review pack · v2 metadata allowed, content read unavailable; unknown cause; freshness unverified; missing clocks; original scoped draft | SA01 limited-state truth; bounded read only if qualified; Recheck/Return; no inferred outage/permission cause, insertion or Send |
| F14 — partial authentication | public auth error; acquisition true; content false after separate content authorization failure | usable workspace access retained; conversation content unavailable; no all-sources disconnected claim or isolated content-retry API invented |
| F15 — source recheck invalidation | exact source recheck pending; auth generation or selected source changes before completion | old protected text immediately cleared and late response rejected; permitted current query/draft only; no obsolete success/freshness promotion |

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

### 17.1 Continuation extensions to the same fifteen scenarios

These are **unexecuted design acceptance requirements**, supplementing the existing scenarios rather than claiming new test passes.

| Existing scenarios | Required continuation checks |
| --- | --- |
| 1, 4, 6 | Conversations→CV01; office→AT08; exact project→CH1/CH6. Terminal fallback uses Terminal identity through the overview template, never Mastermind's sample. New conversation opens only CH0/CH4 draft. |
| 2, 3, 5, 11 | Needs you excludes team review; packet opens once. Directory unavailable, partial, bounded-empty, complete-empty and local-filter-empty remain distinct. Clearing filter restores admitted metadata without session discovery. |
| 7, 8, 9 | Read-only variant cannot send through pointer/Enter; supported empty/nonempty, sending, accepted-awaiting-delivery, delivered-awaiting-reply and received-response states keep separate evidence. Options adds no effect. |
| 12, 13 | Uncertain message/status-not-found retains original identity; no resend/failover. Known-no-effect requires exact owner proof. Auth generation clears stale Work and other protected content before reacquisition; draft follows current approved retention. |
| 8, 14 | Delayed receipt after further typing clears only submitted draft revision. Evidence/Context detour preserves shared sent message, unsent draft and To/About. Add to draft appends explicitly and never sends. |
| 14, 15 | Directory/Inbox return restores permitted filter, selected row, scroll and actual focus. Mobile evidence return does not summon keyboard unless composer was prior focus. Verify 320/390 px, expanded text, IME and Shift+Enter in the actual build. |

Run action-stage checks only after that owner capability is qualified; until then verify the honest unavailable/read-only presentation. Paper visual acceptance establishes no transport, receipt or accessibility execution.

### 17.2 Search/Knowledge extensions to the same fifteen scenarios

These checks are **required and unexecuted in the application**. They extend the same fifteen scenarios; static Paper/source review does not mark them passed.

| Existing scenarios | Required Search/Knowledge → source → append → return checks |
| --- | --- |
| 1, 4, 5 | Search filters are All/Projects/Conversations/Knowledge with no People; Knowledge filters are All/Decisions/Artifacts/Discoveries. Partial coverage, query-empty, filter-empty, unavailable and complete scope remain distinct. Exact result/source identity is admitted by its owner, never inferred from a selected title. |
| 4, 5, 11 | Search source controls and Knowledge review open the exact permitted KD01 reader; Knowledge decision opens the exact AT20/AT20M packet; Sources preserves origin. Source owner/ref/revision, source time, observed-at, coverage and freshness stay separate; recent fetch is not currentness or acceptance. |
| 6, 7, 8, 9 | Reading/selection never attaches or sends. Explicit Add appends exactly §11.4's plaintext quote and full source label to the preserved “What evidence is still missing?” draft, retaining To Project Sol/About Mastermind OS/Topic Work visibility. Read-only builds have no effective Add/Send and cannot synthesize acknowledgments. |
| 6, 10, 14 | No eligible draft offers a supported explicit choice of an existing permitted conversation through CV01/CV01M; it never auto-creates a conversation, project, provider session or Runtime root. A late source read does not append into a newly selected recipient/project. |
| 8, 12, 14 | Repeated Add cannot duplicate the same insertion; changed source before Add is visible and re-reviewed; intervening draft edits are preserved. Show Undo only when the existing draft owner can reverse that exact unchanged insertion/revision; otherwise offer Edit draft and preserve newer text. An unknown prior Send remains bound separately and is never resent/resolved by Add, Undo or navigation. |
| 5, 12, 13 | Metadata permission does not imply content permission; content loss clears protected excerpt and prevents Add before replacement reads. Draft retention uses current approved policy only. Original receipt work_ref is provenance, not current Mission association; timeout/not_found/error/unchanged count does not establish no effect. |
| 13, 14, 15 | Return follows actual nested origin, query/filter/selection, permitted draft/reading anchor/scroll and actual focus. Origin removal or permission loss yields an honest permitted fallback. Search Close never assumes Today; mobile Back/Close never opens keyboard unless composer actually had prior focus. |
| 8, 14, 15 | IME Enter cannot select/Add/close/send; Shift+Enter retains draft newline behavior. At 320/390 px show exact excerpt and full label, reachable details, reviewable inserted payload, safe-area controls and 44 px targets. Verify semantic focus/status behavior in the build; KD01 mobile amendment and UX09-only added-state/Undo are not fabricated product passes. |

### 17.3 Sources/access recovery extensions to the same fifteen scenarios

These checks are **required and unexecuted in the application**. They supplement the original fifteen scenarios and earlier extensions; source inspection, screenshots, observed applied Paper responses and independent design review do not mark any implementation scenario passed.

| Existing scenarios | Required Sources/access checks |
| --- | --- |
| 1, 4, 14 | Today/Conversations/Search/Knowledge/reader entries open contextual AT07 with the actual origin. MEU/T19 open exact SA01/SA01M metadata and preserve the nested chain. Sources stays contextual; Connections remains the admitted Mission relationship view rather than being mistaken for an integration inventory. |
| 4, 5, 7 | The illustrative Work visibility review pack · v2 state shows permitted metadata, unreadable full content, unknown cause, unverified freshness and no supplied clocks. No hidden excerpt, Add, Send, latest-revision claim or fabricated timestamp appears. No direct GitHub source API is inferred from a displayed reference. |
| 5, 13 | Independently vary acquisition/content tokens, admitted metadata/full-content permission, read availability, freshness and coverage. Auth error with acquisition true retains usable workspace reads. Signed-in or successful read never establishes service enrollment/health, source completeness, all-clear or send authority. |
| 5, 12 | Ordinary READ_FAILED/SOURCE_UNAVAILABLE stays causally unknown; precise auth/outage/permission copy appears only with an independent admitted reason. Exact Result typed 503 remains the sole allowed validated special response; arbitrary error bodies cannot become source facts. |
| 4, 7, 12 | T62/T76 invoke only the currently qualified exact bounded owner read. Missing contract/host/permission renders unavailable with explanation. While pending, repeated activation does not duplicate concurrent reads; Checking evidence is disabled, and a supported Cancel aborts/rejects only that bounded read's late completion while retaining permitted return context. UX11's TAQ/TAS specimen is not an executed product control. No reconnect/enroll/start/resume, generic URL request, unknown-write retry, receipt consumption or synthetic success occurs. |
| 4, 5, 13 | Recheck success passes full closed decoding/exact selection and displays only returned owner facts. Changed source/revision is visible. Auth/generation/selection/route changes abort or reject obsolete completion; protected content clears before replacement. Failed reads cannot expose cached content or auto-append into a newer/different draft. |
| 7, 8, 13 | User-gesture auth supports the existing setup-pending/sign-in/cancel/sign-out semantics, full acquisition→content flow and independent access. No silent content-only retry or refresh-token behavior is invented. Sign-out clears private tokens/content without claiming SSO logout, source disconnection or service shutdown. |
| 6, 12, 14 | Back to overview retains the selected source; Close exits to the actual reading origin; Back to Search restores source freshness query, filter, result, scroll and prior focus. To Project Sol/About Mastermind OS/Topic Work visibility and authorized What evidence is still missing? draft stay unchanged. An original unknown operation remains separate and unresolved through every route. |
| 13, 14 | Origin removal or permission loss returns an honest permitted fallback, never a guessed project/session/source. Rich draft/Search return is tested as target behavior rather than assumed from the baseline's pair-only history. Sources/Preferences and collapsed preferences retain context without an enrollment/effect action. Hidden optional project fallback is not an active control or keyboard stop. |
| 14, 15 | Test actual 320/390 px, expanded labels, 44 px targets, visible safe-area controls/home indicator, Tab/Escape/focus and IME. Recheck status announces once without stealing focus; mobile return opens keyboard only for actual prior permitted composer focus. Paper fit/dimensions are static evidence only. |

## 18. Protected-source references

Original references S1–S21 are primary repository sources pinned to `a2646f458f9ff41ddcedd89b338be4a4349e6cd6`; preserve this original census rather than silently repinning it. S22–S25 below record the earlier continuation separately. S26–S33 preserve the prior bounded continuation at protected `3ac05a00dacde2c06893f5f15082b703d2c04463`. S34–S40 record the current targeted Sources/access audit at exact protected `5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f`.
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

### 18.2 Continuation source compatibility and candidate observations

The bounded protected comparison `a264…28be` is ahead by three commits with 22 changed files and no `app/` changes [S22]. Its research preregistration, managed multi-repository workspace/Studio composition and fixed host Agent Relay lifecycle do not alter the daily app's window, evidence, project, decision or auth contract. Source capability does not prove installation or live return. Existing S1–S21 therefore remain the original exact evidence for this unchanged app surface.

Dated reads on 2026-10-04 observe #1046 open/draft/unmerged at `274a8a80c4f9e14b3d00b92fda3a9ac03a20e15f`, and #1150 open/draft/unmerged at `8aca50467f774f52b31cd9147a305936034f46bc`, stacked on the former [S23, S24]. #1046's current composition clears old Work rows in the auth-notification render, alongside Programs/Mission/window/Result invalidation, including identical-display native generation changes. Work becomes pending only when acquisition remains admitted; otherwise authentication-unavailable [S25]. Carry this fence into UX04/F10 and scenario 13; it is candidate composition evidence, not released source custody.

#1150's exact LAUNCH port source is unchanged from the original `37d…` read. It still returns null for message and STOP intents, retains unknown original status and requires matched receipt identity [S24]. Neither candidate establishes installed authenticated composition, canonical write arming, actual launch, deployment, or real return/reopen acceptance. No app implementation is commissioned in this design continuation.

| Ref | Exact primary evidence | Scope |
| --- | --- | --- |
| S22 | [Protected comparison](https://github.com/mastermindx-market-intelligence/Mastermind/compare/a2646f458f9ff41ddcedd89b338be4a4349e6cd6...28be2ce2d481fd542ec869344e178e5cec4d7d75) | bounded no-app-change compatibility check |
| S23 | [PR1046](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1046), [host at274a L94–145](https://github.com/mastermindx-market-intelligence/Mastermind/blob/274a8a80c4f9e14b3d00b92fda3a9ac03a20e15f/app/mastermind_os/src/host.ts#L94-L145) | dated candidate head/status and typed Work/auth read |
| S24 | [PR1150](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1150), [LAUNCH port at8aca L298–455](https://github.com/mastermindx-market-intelligence/Mastermind/blob/8aca50467f774f52b31cd9147a305936034f46bc/app/mastermind_os/src/orchestration/executive-launch-command-port.ts#L298-L455) | dated launch-only candidate; unchanged port; no Send/STOP |
| S25 | [App at274a L1225–1270](https://github.com/mastermindx-market-intelligence/Mastermind/blob/274a8a80c4f9e14b3d00b92fda3a9ac03a20e15f/app/mastermind_os/src/App.tsx#L1225-L1270), [auth fixture L114–129](https://github.com/mastermindx-market-intelligence/Mastermind/blob/274a8a80c4f9e14b3d00b92fda3a9ac03a20e15f/app/mastermind_os/src/App.auth-generation.test.tsx#L114-L129) | current candidate Work immediate-clear implementation and fixture |

### 18.3 Prior protected delta and launch-recovery evidence — 4 October 2026

The next bounded protected comparison `28be…3ac` is ahead by exactly one commit with 12 backend/evidence/test files and **no app changes** [S26]. Together with the preserved §18.2 comparison, this leaves the original daily app capability census unchanged. The current source adds optional original `work_ref` to strict receipt-v2, reconstructed on duplicate/status reads from original durable provenance. A legacy omission stays omitted; a present malformed field fails validation. Current UI configuration cannot relabel it, and conflict under the same intent creates no additional Job. This is original workstream provenance, not a current Program/Mission association, new registry, query plane, grant, dispatch path or proof of execution [S27].

The committed component evidence freezes #1150 at historical `37d02586eeb97d92e6fb9ed6dbc7cd142dd6449c`; do not confuse that probe snapshot with the later candidate observation in §18.2. Its eight disposable authenticated journeys exercise V2/V3 profiles, generic-v1/strict-v2 receipts and accepted/lost replies. Lost-reply recovery reads the original intent status without resubmission or fresh source admission. Each creates one queued root with zero attempts/workers; these fixtures prove neither installed OAuth/storage/producer composition nor worker execution or actual Mission presentation [S31].

Unmodified frozen #1150 accepts V2/server 1.2.0 recovery but retains unknown for V3/server 1.4.0 recovery because of its closed E1 version guard. The exact pending pointer remains, blocking duplicate submit. The proposed consumer patch permits only 1.2.0 and 1.4.0 and passes eight journeys/52 negatives on disposable copies; it is **unadopted**, not protected app implementation. Installed 1.3.1 remains unqualified and unsupported by that patch. Source merge of the backend contribution does not establish installed adoption. The evidence README's contributor-time “needs merge” prose is preserved history, not the current state of the backend files now at protected `3ac…` [S27, S31].

The current app still lacks general Search, Knowledge collections, source-to-draft reuse and a composer [S28]. Scoped Evidence renders qualified tuple metadata and artifact text; general source-reader links are absent. The implemented Mission v3 result reader validates the exact five-key selector and a fixed typed envelope; it is not a generic source route [S29]. Its source currentness, independent access resources, limited window coverage, auth-generation invalidation and limited Mission-pair return remain the applicable first-slice constraints [S30].

| Ref | Exact current primary evidence | Qualified fact |
| --- | --- | --- |
| S26 | [Protected 28be…3ac comparison](https://github.com/mastermindx-market-intelligence/Mastermind/compare/28be2ce2d481fd542ec869344e178e5cec4d7d75...3ac05a00dacde2c06893f5f15082b703d2c04463) | one commit, 12 backend/evidence/test files, no app changes |
| S27 | [Receipt evidence L9–24](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/research/evidence/mastermind_os_backend_app_contract_20261004/README.md#L9-L24), [receipt construction L891–947](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/control_plane/ceo_intent.py#L891-L947), [durable reconstruction L1156–1177](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/control_plane/ceo_intent.py#L1156-L1177) | optional original strict-v2 work_ref; original provenance not current Mission association |
| S28 | [Current navigation L29–52](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/app/mastermind_os/src/App.tsx#L29-L52), [closed host surface L23–83](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/app/mastermind_os/src/host.ts#L23-L83), [Conversation L802–890](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/app/mastermind_os/src/App.tsx#L802-L890) | no general Search/Knowledge/composer/reuse capability; current permitted window display |
| S29 | [Evidence L696–778](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/app/mastermind_os/src/App.tsx#L696-L778), [result index L100–185](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/app/mastermind_os/src/App.tsx#L100-L185), [exact result read L1674–1765](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/app/mastermind_os/src/App.tsx#L1674-L1765), [fixed GET surface L527–585](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/app/mastermind_os/src/web-auth.ts#L527-L585) | tuple metadata versus exact bounded detail; no general source-opening endpoint |
| S30 | [Currentness/access L8–43](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/app/mastermind_os/README.md#L8-L43), [window DTO L178–218](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/app/mastermind_os/src/workspace-contract.ts#L178-L218), [auth invalidation L987–1106](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/app/mastermind_os/src/App.tsx#L987-L1106), [pair-only return L1210–1229](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/app/mastermind_os/src/App.tsx#L1210-L1229) | bounded owner currentness; independent acquisition/content; no send/history; permission clear and limited return |
| S31 | [Recovery/patch evidence L28–75](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/research/evidence/mastermind_os_backend_app_contract_20261004/README.md#L28-L75), [journey refusal/admission/recovery L200–270](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/tests/test_executive_mcp_launch_journey.py#L200-L270), [remaining obligations L116–121](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/research/evidence/mastermind_os_backend_app_contract_20261004/README.md#L116-L121) | disposable actual-backend evidence; V3 unknown preserved; patch unadopted; installed/message/STOP/no-effect settlement remain separate |
| S32 | [Bridge read allowlist L32–43](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/integrations/paper_desktop/bridge.py#L32-L43), [no ledger/actions L426–437](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/integrations/paper_desktop/bridge.py#L426-L437), [dispatch/partial-effect semantics L489–521](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/integrations/paper_desktop/bridge.py#L489-L521), [MCP typed serialization L39–102](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/integrations/paper_desktop/mcp_server.py#L39-L102), [snapshot/effect limits L300–315](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/docs/PAPER_DESIGN_INTEGRATION.md#L300-L315) | operation ID correlation only; no receipt-read store; generic lost/error reply does not establish no effect |
| S33 | [Paper workflow scoped fence L89–95](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/skills/paper-design-workflow/SKILL.md#L89-L95), [same-carrier reconciliation L128–129](https://github.com/mastermindx-market-intelligence/Mastermind/blob/3ac05a00dacde2c06893f5f15082b703d2c04463/skills/paper-design-workflow/SKILL.md#L128-L129) | unknown operation freezes overlapping targets; no replay/carrier swap; disjoint targets remain eligible |

### 18.4 Current protected compatibility and Sources/access audit — 4 October 2026

The bounded protected `3ac…5b` comparison is ahead by one commit with 104 changed files and no `app/` or `integrations/paper_desktop/` changes [S34]. This compatibility statement records the principal's bounded delta evidence, not a 104-file audit. The Sources worker directly read the six requested files at exact protected `5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f`: App.tsx, host.ts, workspace-contract.ts, web-auth.ts, the app README and docs/COMPANY_CONSULTATION_EDGE.md. No source edits, runtime/Executive actuation, Browser, message sends or Paper operations were performed by that source audit. It confirms the unchanged read-only app boundary; source capability remains separate from actual installed acceptance.

Connections remains a Mission relationship graph/list; Evidence renders source-projected provenance tuples and artifact text; the host exposes only authentication and fixed read methods. There is no direct GitHub connector, generic source health/read API, service start/reconnect/enrollment, composer, Send or Add port [S35–S39]. The README still omits later Mission v3/Result routes and native commands; §18.1's code-over-documentation distinction continues to apply. Private resource-token presence is not proof of service enrollment or read success, and a content authorization failure can coexist with useful acquisition. Generic read failures do not supply a diagnostic cause. Only the exact Result read admits its validated unavailable 503 envelope [S36–S37].

CURRENT and SAME certify bounded owner observation/consistency rather than render-time liveness or independent freshness. Source time, observation time, projection generation, revision, completeness and acceptance remain separate. Protected text and in-flight reads invalidate on auth/generation changes; current browser history restores an exact Mission pair, not the richer Search/draft return target [S38–S39]. The new Company edge document describes separately held service/native composition; its disabled profile, outstanding installed acceptance and internal caller/delivery/consumption fences do not enlarge this app's public host or settle either prior Paper effect [S40].

| Ref | Exact current primary evidence | Qualified fact |
| --- | --- | --- |
| S34 | [Protected 3ac…5b comparison](https://github.com/mastermindx-market-intelligence/Mastermind/compare/3ac05a00dacde2c06893f5f15082b703d2c04463...5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f) | principal bounded comparison: one commit, 104 files; no app/Paper bridge changes; not a full delta audit |
| S35 | [Connections L617–694](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/src/App.tsx#L617-L694), [host L23–84](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/src/host.ts#L23-L84) | Mission relationship presentation; independent AuthState resources; auth/fixed-read-only host; no generic source/control/send API |
| S36 | [web auth state L141–162](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/src/web-auth.ts#L141-L162), [full sign-in/sign-out L392–439](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/src/web-auth.ts#L392-L439), [actual auth controls L1852–1912](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/src/App.tsx#L1852-L1912) | token availability versus read; error can coexist with acquisition; user-gesture two-resource auth, cancellation and local token disposal; no content-only retry |
| S37 | [fixed GET failure policy L441–511](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/src/web-auth.ts#L441-L511), [exact route map L527–585](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/src/web-auth.ts#L527-L585), [host Result decoder L157–204](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/src/host.ts#L157-L204) | ordinary non-OK reads collapse cause; sole exact Result typed 503; complete decode and epoch checks; no arbitrary URL/source read |
| S38 | [Evidence L696–779](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/src/App.tsx#L696-L779), [bounded currentness/access L8–49](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/README.md#L8-L49), [owner observation L23–176](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/src/workspace-contract.ts#L23-L176), [window capabilities L300–315](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/src/workspace-contract.ts#L300-L315) | provenance text and separate clocks/freshness; independent resources/operator permissions; observed currentness; send/provider-control/history false |
| S39 | [Conversation refresh L797–889](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/src/App.tsx#L797-L889), [auth invalidation and bounded pair/window read L987–1106](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/src/App.tsx#L987-L1106), [pair return L1210–1229](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/src/App.tsx#L1210-L1229), [window recheck trigger L1643–1655](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/app/mastermind_os/src/App.tsx#L1643-L1655) | implemented bounded read retry; immediate protected clear/late-response fence; current exact-pair-only history versus richer target origin |
| S40 | [Company edge disabled/provisioning L3–19](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/docs/COMPANY_CONSULTATION_EDGE.md#L3-L19), [original caller read L23–25](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/docs/COMPANY_CONSULTATION_EDGE.md#L23-L25), [evidence/consumption/recovery L29–45](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/docs/COMPANY_CONSULTATION_EDGE.md#L29-L45) | separate disabled runtime profile; caller/generation/thread-bound read_ref; delivery/read/consumption/RETURN separation; internal reconciliation without provider resubmit; installed acceptance outstanding |

## 19. Review outcome and remaining proof

The original six workflow artboards exist on the exact Paper page, with their IDs recorded above. Actual screenshots and editable JSX were inspected. Today, Meta-CEO, project navigation, welcome context and new-project intake were refined in the canonical screen family. The directory, AT00, MC90 and CH91 point builders to this flow contract. The UX04 project-conversation example was reconciled to Project Sol rather than the company Meta-CEO. The AT15 example now keeps review recorded/correction next distinct from acceptance; Inspect next turn is an optional read.

Continuation adds CV01/CV01M and UX06/UX07, and refines the Inbox pair and CH1/CH2/CH3/CH6/CH7: nine product screens and two new note boards in this continuation. Screenshots and editable extraction received scoped visual/semantic review at tokens `fd2ed32e`. Desktop product roots remain 1600 × 1040; mobile roots remain 390 × 844. The new note boards are 1600 × 1120. Options and Send controls retain 44px heights; reviewed mobile navigation/recovery actions retain at least 44px targets and their bottom safe area. These are static layout observations, not executed accessibility tests.

Independent reviews accepted CV01/CV01M, the Inbox pair and the connected semantic contract. The CH editor inspected all five affected chat frames; the principal additionally inspected final CH2 and CH7. Independent note review identified two wording corrections, now applied and visually rechecked: current complete-empty scope does not imply empty conversation history, and return may reopen the keyboard only when the composer had actual prior focus. Final extraction confirms the separate sent message and unsent draft, exact To/About scope, supported Options, distinct delivery stages and original-operation recovery.

At the earlier continuation, AT00, UX00, the main directory, MC90 and CH91 pointed to all eight then-existing workflow notes. The UX00 directory was expanded to 1600 × 1200 and its spacing adjusted so its complete guide list fit; the next row began at y=1250. Existing advanced-operation references were retained. This preserves that reviewed snapshot and does not claim that every directory anchor has already been updated for UX08/UX09.

Independent visual/semantic review accepted Today desktop/mobile, Meta-CEO desktop/mobile and UX00–UX04 at their reviewed states; the principal inspected UX05 and the final refinements. This proves editable design, fit and contract clarity, not functioning navigation or action. Enabled message/create/decision specimens describe a qualified target state; the present read-only slice must retain unavailable/preview behavior until its owner capability is actually accepted. There is no synthetic send, save, success receipt, deployment, background worker or production acceptance in this commission.

Builders must map every implemented field to the current DTO, preserve the exact source/permission/operation fences and run the fifteen slice-appropriate scenarios. The first missing capability is a real integrated journey in the application, followed by separately qualified action composition. No protected merge, source-custody transfer, runtime actuation or installed qualification follows from design completion.

The current continuation refines Search and Knowledge on desktop/mobile and adds KD01 `SPU-0` / `STU-0`: six product artboards created or refined. It adds UX08 `SXT-0` and UX09 `SXU-0`, bringing Page 13 to ten notes. Screenshots, edited text and the source audit establish static findings and named connections, not implemented reads, append, Undo, focus/IME behavior or transport. Both new guides render fully at 1600 × 1120. The conditional-Undo clarification was applied to `T00-0`, visually rechecked and read back exactly; the augmented draft `SZO-0` matches §11.4. AT00, UX00, the main directory, MC90 and CH91 now name UX00–UX09 and the source-reader family. Their updated entries were read and visually reviewed; UX00's complete guide list fits, and the other guide roots retain fit-content sizing.

The exact excerpt/full-label/mobile-details amendment remains open on the KD01 product roots under §11.6's original-carrier unknown-effect fence. KD02 was neither observed nor verified; added-state, mobile payload/details and conditional Undo remain UX09 requirements and note specimens only.

Required implementation proof includes the same fifteen scenarios with §17.2's Search/Knowledge checks and §17.3's Sources/access checks, exact permitted source reading and unsent append, source-change and permission negatives, conditional insertion/Undo behavior, dynamic origin and real keyboard/focus/IME/mobile review. The application remains read-only at current protected `5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f`; the prior `3ac…` census and all earlier pins remain historical evidence above. All fifteen application scenarios and their extensions are unexecuted. The two unresolved Paper operations are separate design-effect custody issues; neither can be closed by document edits, unchanged observations, green component evidence or completed work on disjoint guides.

### 19.1 Sources/access continuation checkpoint

The current continuation creates SA01 `T0U-0` / SA01M `T0V-0`, refines AT07 `L6N-0` / AT07M `MNO-0` as the Sources/access overview, and adds UX10 `T7J-0` / UX11 `T7K-0` on Page 13. The principal supplied screenshots/readback and reported independent UX acceptance for the SA01 pair. The principal also independently screenshot-reviewed and accepted the AT07 pair with four source rows, no clipping and visible safe area. Desktop/mobile retain the metadata-available/full-content-unavailable specimen, unknown cause, freshness unverified and missing source/observation clocks. The mobile home indicator was initially obscured; the principal adjusted content spacing and inspected a new screenshot with the safe area visible. UX10/UX11 were fully written and screenshot-reviewed without clipping, with 20 px root gaps; UX11 includes the concrete disabled Checking evidence…/Cancel pending-read note specimen. These are static design observations, not responsive/keyboard/accessibility execution.

The reviewed source-detail targets are desktop/mobile Recheck at 46/44 px height; Close at 52 × 44 / 44 × 44 px; Back to overview at 44 px height / 44 × 44 px; Back to Search at 46/44 px height. The principal confirmed the optional desktop project detour's computed `display: none` and fresh full screenshot without Open project. It is removed from the active layout, not deleted; `get_node_info` still reports `isVisible: true` because the layer exists. No mobile counterpart or new project route is invented. The normal source recovery choices remain bounded Recheck and actual Return, and the scoped user draft is separate from read/effect status.

Index operation `mm-source-access-guide-indexes-20261004-001` returned `APPLIED_RESPONSE_OBSERVED`. Updated leafs `Q9K-0` / `Q9L-0`, `NI0-0` / `NI1-0`, `Q4L-0` / `Q4N-0` / `Q4O-0`, `Q1R-0` / `Q1S-0`, `Q4H-0` / `Q4I-0` and `PZ3-0` now name UX00–UX11/SA01 and the current `5b…` compatibility pin. The principal reviewed screenshots of UX00 `PBO-0`, directory `Q1P-0` and AT00 entry `Q9I-0` as legible. This records the current index evidence while preserving the earlier eight-note and ten-note directory snapshots above.

The principal reports new Sources-continuation Paper edits as `APPLIED_RESPONSE_OBSERVED`, with no new unknown effect reported in this checkpoint. The principal subsequently released only its own Sources/new-guide/index working groups through `mm-source-access-release-owned-20261004-001`, with an applied response observed. Releasing those indicators does not settle either prior `EFFECT_UNKNOWN` operation in §11.6 or release its product/leaf targets. Earlier directory history, candidate action gates, source-owner laws and unexecuted implementation obligations remain intact. A separate Projects-finding phase is outside this Sources checkpoint and is not represented as completed here.
