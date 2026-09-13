# Live Fabric — dynamic prototype storyboard and implementation rubric

**Parent:** WS:CHAIRMAN-CONTROL-ROOM; Mastermind PR #595.  
**Existing Figma file:** `GfH3jNfel8F2cv7ZdTtiXt`.  
**Basis:** dynamic-orchestration addendum and dynamic implementation masterplan, September 13, 2026.  
**Status:** visual implementation specification; new frames and interactions are not claimed created by this document.

## 1. Design thesis

The new prototype demonstrates **how the company moves**, not merely the fact that agents have names. Keep the original ink/brass visual language and component library, but give actual dialogue, causality, route decisions and obligations enough screen space to be useful.

Do not add five unrelated dashboard screenshots and call them a dynamic system. Build one consistent sample mission across successive states. The same session, request, child, artifact and obligation identities persist from screen to screen. Numbers, statuses and content classes come from the shared scenario below. Every frame displays `ILLUSTRATIVE PLAYBACK — NO AGENTS CONNECTED`.

Preserve the existing file and original product frames. Add a separately named dynamic-workspace page after confirming the current file structure; a prior inventory is not evidence all pages remain present. No canonical design-library replacement, public sharing change, provider call or production activation is part of the mockup.

## 2. One scenario, one set of identities

Scenario name: **Policy Watch — research to production review**. All following identifiers are explicitly synthetic display identifiers, not real Executive IDs or PR numbers.

| Object | Sample identity | Meaning |
|---|---|---|
| Mission | `sample:policy-watch` | The single end-to-end outcome shown |
| CEO office | `sample:ceo-office` | Durable Meta-CEO role; production provider/model remains unselected |
| Research session | `sample:research-01` | Demonstration of a separately qualified research surface |
| Principal | `sample:fable-01` | Principal orchestration justified by this sample's cross-system scope |
| API worker | `sample:api-01` | Independently admitted source ingestion work |
| UI worker | `sample:ui-01` | Independently admitted interface work on disjoint source |
| Source analyst | `sample:analyst-01` | Bounded source-validation child |
| Native helper | `sample:api-helper-01` | Parent-bounded helper, not an independent Job |
| Reviewer | `sample:review-01` | Independent review after the candidate is materialized |
| Research artifact | `sample:research-v1` | Sources, alternatives, risks and proposed acceptance |
| Accepted build brief | `sample:brief-v2` | CEO/integrator's adjudicated build outcome |
| Integrated candidate | `sample:candidate-v1` | Exact sample artifact reviewed, not a live PR |
| Return obligation | `sample:consume-result-01` | Principal/CEO consumption remains separate from result return |

The CEO role is not renamed to a permanent model. In the design, its provider chip says `Implementation not selected`. Demonstration conversations illustrate its intended behavior; they do not assert an active production CEO. Research labeled as ChatGPT Web Pro is an intended qualified surface in the sample, not an API run or current mode attestation.

## 3. Main mission-room composition

Use a 1728 × 1117 reference frame, with a responsive 1440-width validation composition later. Keep a compact 72-pixel navigation rail and a 224-pixel mission context area. The content area starts at x=320 and reserves a generous 528-pixel actual-conversation pane at the right. This is intentionally wider than the first prototype's inspector, because real dialogue must be readable rather than buried in tiny cards.

The upper-left work area contains an approximately 832 × 504 topology canvas. Beneath it, an 832 × 244 panel shows the selected wait/route/return relationship. The right pane contains the actual sample messages, source-class chips, receipt strip and scoped composer. A short footer shows coverage, playback state and connection qualification; technical digests are available in detail rather than filling the primary UI.

One click selects an object and its corresponding dialogue. A second explicit action expands the operator workspace. Graph/list, conversation and source inspector retain the same selection. The vertical panels can be resized in the eventual product; the prototype shows their intended priorities without pretending resize code exists.

## 4. The twelve-state choreography

| State | Visible change | What the prototype must teach |
|---|---|---|
| S0 — CEO intake | Chairman's request and the CEO's communicated plan appear next to an empty mission graph | A conversation is not yet admitted work; no fake active workers |
| S1 — Research route proposed | An outlined research node and route preview appear | Proposal, eligibility and actual pickup are different |
| S2 — Research observed | Exact sample binding/start receipts appear; researcher response begins in the conversation pane | Motion starts on an observed event, not on button intent |
| S3 — Research returned | Versioned research artifact and a return edge appear | Returned research is not yet accepted architecture |
| S4 — Build brief accepted | CEO/integrator consumes the artifact and publishes `sample:brief-v2`; Fable delegation appears | The reviewed brief is the handoff, not the entire chat transcript |
| S5 — Child wave admitted | API, UI and source-analysis children appear with separate pickup/observation states | Proposed child, admitted child and observed session are distinct |
| S6 — Concurrent activity | Two actual content lanes update; a dotted helper appears under API | Native helper is parent-bounded; do not count it as another admitted Job |
| S7 — Dependency wait | UI waits on a particular API contract; the exact wait edge and source appear | “Waiting” names an object, accountable role and next receipt |
| S8 — Result returned | API result edge and artifact appear; parent consumption remains pending | A returned result does not automatically make its parent advance |
| S9 — Integration and review | The principal consumes results and sends the integrated candidate to an independent reviewer | Integration and independent review are explicit operations |
| S10 — Proof returned | Review and browser-proof artifacts appear; the CEO acceptance obligation remains | Green implementation checks are not final program acceptance |
| S11 — CEO ruling | CEO consumes the exact proof and records the sample outcome; work remains recoverable | Completion is an accepted useful outcome, not token activity |

Do not promise all twelve states are wired in the first visual revision. The first build of the revised prototype should complete S4–S8, because it demonstrates the most important missing behavior: child nodes appearing, real-text dialogue, a concrete wait and a returned result. Add the CEO intake/research chain and review/proof conclusion next without replacing those identities.

### Example conversation content

The following text is synthetic. Display its class explicitly, not as a screenshot of a real session.

**CEO → Principal / commission:** “Use the accepted brief. Keep source ingestion, interface work and source validation separate. Return one integrated candidate with browser proof; do not call implementation checks production acceptance.”

**Principal → API worker / commission:** “Implement the ingestion contract from brief v2 in your assigned worktree. Preserve source corrections. Return the exact candidate and integration evidence.”

**API worker / response:** “I have the assigned scope. I am checking the existing collector contract before editing.”

**System / receipt:** “The sample API child is admitted. Pickup recorded; provider activity observed. These are separate receipts.”

**UI worker → Principal / question:** “The selected source contains an optional correction timestamp. Should the list show the original publication time or the correction time?”

**Principal → UI worker / ruling:** “Show publication time as the primary date and correction time as a separate qualifier, consistent with the accepted brief. Keep the missing value explicit.”

**API worker → Principal / result:** “The sample candidate and integration evidence are ready. Production acceptance has not been established.”

**System / obligation:** “Result returned. Awaiting consumption by the exact current principal target.”

Content presented as a plan is a communicated plan. Content presented as a response is visible output. There is no invented hidden-thinking lane. Provider summaries, when shown, have their own label and source, not a deceptive `raw thoughts` heading.

## 5. Motion and playback contract

Use matched layer names across cloned state frames so transitions preserve the user's mental map. Existing nodes do not rearrange on every new message. Newly admitted children expand into reserved space. A return highlights its actual edge and artifact; it does not make the whole canvas pulse.

Provide **Play**, **Pause**, **Next event** and **Reset sample** controls. A step advances one defined sample event. Timed playback may animate the prepared sequence but remains labeled illustrative. Pause stops visual playback only; in the real product it would not stop agents. A reduced-motion version uses instant state changes and the same information.

Use a restrained legend: hierarchy/supervision, delegation, response/result, waiting and observed helper. State and edge meaning must not rely only on color. In the first dynamic revision, focus on two or three edge types at once; toggles reveal the rest. An unread-message counter appears only when the user is not following the selected conversation.

On a real stream, content can be coalesced for readability; the prototype must not imply each token triggers graph layout. Partial text and completed text are separate states. A corrected completion replaces the partial message rather than appending a second contradictory answer.

## 6. Router console: actual versus hypothetical

Create a connected route inspector, reached from a real sample delegation edge. Show these levels separately: request class; capability profile; logical provider/model route; physical capacity claim; exact bound session. Do not mix executive roles, provider brands, accounts and machines as interchangeable candidate tiles.

Show the sample request and accepted profile, source-authored reason codes, suitability tiers, exclusions and the separate pickup/binding receipt. Historical missing detail says `Not recorded`. No percentage confidence or estimated cost is fabricated.

A second state demonstrates **Simulate policy change**. Use the same request under an explicit proposed policy. A visible `HYPOTHETICAL — NO RESERVATION OR SESSION` banner stays present. The action button is `Review policy diff`, not `Move running agent`. Its next pane shows the exact affected future-work scope and expected preimage. Applying a policy is a later qualified command, not dragging a node to a different model.

Uncertain effects, exact-session requirements, unavailable quota and an unqualified host are distinct exclusion reasons. A blocked route returns to the original owner for reconciliation rather than switching providers in the prototype as though it were harmless.

## 7. CEO workspace: conversation with an office

The Chairman-facing screen gives primary space to the CEO conversation and secondary space to current delegated outcomes. The office header identifies the logical responsibility, selected capability profile and actual implementation status. The eventual model picker proposes a qualified binding/policy change; it does not retroactively turn one model's history into another's.

Adjacent delegation cards show the research request, returned artifact, adjudicated build brief, Fable principal mission, child outcomes and review/acceptance. Selecting a card opens the same mission room rather than another parallel dashboard. `Needs CEO action` displays exact obligations; `Needs Chairman` displays only genuine higher-authority decisions.

Use material metrics, such as returned results not yet consumed and obligations with unavailable targets, with scope/coverage. Do not invent a global green company-health score. A powerful-looking executive screen that conceals abandoned obligations fails the design.

## 8. Adverse states are part of the main flow

**Parent unavailable:** retain the role and obligation, show the previous target separately, and display the current reconciliation/fencing receipt. Do not replace the node with whichever session appears online. The successor is shown only after the sample's accepted transfer event.

**Action outcome unknown:** freeze the original operation reference, disable retry, keep the source receipt reachable and expose reconciliation. A successful transport reconnect does not erase uncertainty.

**Source unavailable:** stop live motion for affected observations, retain last-qualified timestamps and mark the current snapshot degraded. Do not show zero active work. The source-origin detail explains which reader failed without publishing private local paths into a remotely shared surface.

**Traveling client disconnected:** the connection indicator changes to dated evidence. The sample's remote workers do not stop merely because the viewer disconnected. Pending writes are not queued for automatic replay. Reconnection refreshes state and reads original receipts.

## 9. Hosted web and Mac architecture view

The visual topology shows **traveling browser / Mac client / responsive web → authenticated VPS gateway → private connection → one existing canonical authority → enrolled workers**. It must not draw a new authoritative database on the VPS and another on the home Mac.

Mark the difference between the universal hosted HTTPS product and a tailnet-only access option. The Mac client's optional local bridge is drawn as a narrow side capability, not the main company runtime. The authority's eventual migration to an always-on VPS is an explicit separately proven cutover, not an assumed effect of publishing the website.

Show the failure fact that matters: a reachable web gateway does not make a sleeping native worker capable. A qualified always-on worker can run portable tasks; browser/account-bound tasks remain tied to their enrolled hosts. The MacBook can view and interact while traveling through the same backend after authentication.

## 10. Visual acceptance and continuation

Before claiming the revised mockup is complete, read back its actual page/frame IDs, component usage, prototype destinations and sample-state contents. Inspect rendered screenshots for the main mission room, dialogue, router distinction and failure state. Check text bounds, contrast, focus intent, stable graph layout and consistent counts. Figma geometry is not browser accessibility or production proof.

Test the story with concrete questions: Can the reviewer identify who is speaking? Which child is still only proposed? Which result has returned but not been consumed? Which role is accountable when a session is unavailable? Which policy result is hypothetical? What stops when the traveling viewer disconnects? If the answers require reading an engineering essay beside the screen, the UI has not solved the task.

The next visual action is to implement the S4–S8 mission-room choreography in the existing file, with source-classed dialogue and one complete linked return journey. The next extension is the CEO/research chain and router control states, followed by remote/native topology and the adverse scenarios. Record actual completed frames and missing interactions rather than labeling all planned surfaces built.
