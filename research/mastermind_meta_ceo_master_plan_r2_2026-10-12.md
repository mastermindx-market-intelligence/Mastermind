# Mastermind OS — One Meta-CEO, Six Dots, Closed-Loop Delivery
## R2: Independent architecture assessment and revised implementation master plan

**Date:** October 12, 2026  
**Status:** Proposed for adoption; research/design deliverable, not an installed-system or production-acceptance claim.  
**Reviewed baseline:** `mastermind_meta_ceo_master_plan_2026-10-12.md` (R1), together with the Chairman’s original prompt.  
**Protected research pin:** `mastermindx-market-intelligence/Mastermind@66c3a1e179db208202e6b7879563293aa87f850a`.  
**Observed installed Executive grounding:** `a858ac249296ffaa7bf523863dea5917bbbc1f24`, from a successful read at `2026-10-12T07:44:02Z`. Source and installation are deliberately distinguished.

The assignment is to assess and strengthen the architecture. This review did not enroll accounts, create credentials, launch workers, arm watchers, purchase capacity, modify repository source, merge, deploy, or adopt this document into Agent OS. Proposed tests below have not been executed against the six-account system.

## Assessment in one page

**Keep the direction. Change the implementation priorities and strengthen the enforcement boundaries.**

R1 correctly identifies the central product: a single accountable conversational office, supported by replaceable reasoning surfaces and durable existing company systems. It correctly rejects six competing CEOs, an always-generating model, a second company task queue, and completion claims based only on source publication or green CI. Its treatment of interrupted submissions, original-intent review, role fencing, and direct decision returns is particularly valuable. [R1 §§1–3, 5–9, 13–15]

R1 is not yet sufficient as an implementation contract. The central risks are not another missing dashboard or another agent hierarchy. They are whether the chosen Dot interface satisfies the conversational experience, whether native Project Chat can participate through an eligible route, whether permissions survive cross-channel concurrency, and whether the company actually closes the decision-and-acceptance loop without Chairman intervention.

| Priority | R2 change | Why it changes the outcome |
|---|---|---|
| Critical | Qualify native-Chat feasibility at the beginning, in parallel with the core office | A requirement central to the Chairman’s vision must not first be investigated after most of the system is built. |
| Critical | Treat Dot2API as an asynchronous task transport and test conversational fit | A compatible API shape is not evidence of responsive chat or continuous conversation context. |
| Critical | Enforce principal and worker permissions at actual receiving services | Prompt instructions and final-response validation cannot stop side effects that already occurred during a turn. |
| Critical | Cover simultaneous app, Slack, native Dot, and event-triggered company turns | One provider queue does not establish company-wide exclusion across every ingress. |
| High | Give each programme one accountable delivery owner | One public voice must not mean every minor ruling waits for the primary Dot. |
| High | Check intent translation before implementation, then check delivery against that intent | A perfectly implemented misinterpretation is still a failed project. |
| High | Reuse the existing MCP Events work in PR #1362 | Avoid rebuilding an event-signing and reply path already under development. |
| High | Define a durable obligations loop, not just notifications | A delivered event is not proof someone decided, the worker resumed, or the parent consumed the result. |
| High | Measure weekly quota and peak responsiveness separately | More accounts can address one constraint without fixing the other. |
| High | Turn proactivity into goal-directed portfolio stewardship | A permanently busy backlog is not an autonomous company. |

These are refinements of R1, not a replacement of its ownership model. In particular, R1 already contains the two-transaction recovery insight and an intent contract; R2 makes those requirements earlier, more testable, and less dependent on model obedience.

## 1. Executive decision and product outcome

Build an **asynchronous conversational company office with bounded, event-driven autonomy**.

The Chairman can express an idea once, correct its interpretation in the same office, and see the existing company research, decide, implement, verify, and report back. Routine placement, message transport, ordinary design rulings, review follow-through, and continuation should not become Chairman labor.

The office is a durable responsibility and user experience, not an immortal transcript. The primary Dot is the preferred candidate occupant, subject to qualification. The other Dots supply programme ownership, independent quality, and operational continuity. Native Project Chat remains a distinct research avenue. Executive OS and its existing partners retain execution and authority.

Two release claims remain separate:

**Core autonomous office:** a real app conversation, grounded Dot reasoning, scoped Executive actions, existing Fabric work, direct decision returns, original-intent review, and truthful progress in the app.

**Full Chairman vision:** the core office plus an eligible, demonstrated way to commission and continue ordinary native Project Chat with the requested observable mode, relevant Project context, and an exact result/decision return path.

The native-Chat component is optional to the first release, but **not optional to claiming the full requested outcome**. Work, Codex, or API inference may not silently stand in for it. A supported alternative can be assessed separately with explicit differences and applicable budget authority.

The protected prior architecture favors included-plan native Chat cognition. Selecting Dot as the office occupant therefore needs an explicit qualified architecture amendment; it is not already established merely because both surfaces are provided by OpenAI. [E02]

## 2. What is known, changed, and still unproven

| Surface | Evidence inspected in this review | Interpretation |
|---|---|---|
| Protected architecture | Existing chat-native Meta-CEO specification at the R2 pin | Reuse one office, bounded responsibilities, existing authority, dependency, and dialogue owners. It remains a specification, not runtime proof. |
| Office UI | `app/mastermind_os/src/meta-ceo/README.md` | Direction preview is inert; no submission callback. Existing host/provenance seams and legacy routes should be preserved. [E03] |
| Dot worker | PR #1360, draft/open, head `343c08b8ddd66c37297d813e11031bb43969d804` | READ/RESEARCH worker candidate, disarmed; not the principal adapter and not live Dot acceptance. Local-test claims were not rerun here. [E04] |
| Dot worker isolation | Candidate runbook and stated capability profile | Local isolation and standing instructions do not themselves prove the Dot’s cloud-connected apps cannot write. This is an assurance gap, not a demonstrated exploit. [E05] |
| MCP Events source | PR #1362, draft/open, head `4e574cc24ac7a56c52e87ed5ab9a02802b8ce359` | Relevant existing reply-signing/callback source to integrate, not proof of installed delivery or parent consumption. [E06] |
| Wake descriptors | `control_plane/wake_transport.py` | `grok-computer` and `chatgpt-gui` are not marked implemented in this module. This is not a complete fleet inventory. [E07] |
| Executive read | `executive_state`, `2026-10-12T07:44:02Z`: successful, no degraded inputs | Supersedes R1’s failed-read observation. It does not prove Dot writes or native Chat control. [E08] |
| Addressable sessions | `session_targets`: successful, empty result | No target exposed to this caller in that read; not proof that no external conversations exist. [E08] |
| Principal tools | V3 actions exposed in this conversation were read/status/recovery readers | Exact Dot admission, steering, ruling, and acceptance must be separately qualified. No conclusion about every other app or account is implied. [E08] |
| Six-account inventory | Chairman-supplied four personal Pro and two Business Premium accounts and host installations | Planning input, not verified enrollment, common memory, independent quota, or six simultaneous control sessions. |

The live runtime projection contained 25 Jobs and 33 Attempts. Those counts are an observation of that Runtime, not a census of every active provider or desktop process. No business inference depends on treating the whole estate as idle.

## 3. Target architecture and canonical ownership

```text
Chairman
  ↕ one Mastermind OS office and conversation
Existing authenticated Conversation / application owner
  ↕ durable request and honest asynchronous response
Existing office responsibility → qualified primary Dot via Dot2API
  ↕ scoped company tools and current responsibility binding
Executive OS / Runtime / Model Router / Capacity
  ├─ programme responsibilities → programme Dots where useful
  ├─ existing orchestrators → existing Subagent Fabric workers
  ├─ independent quality responsibilities
  └─ eligible native Project Chat research
        ↕ conditional Grok Secretary desktop transport

Worker question / result
  → existing Dialogue / Wake obligation
  → exact responsible principal, normally by MCP Events
  → committed ruling or review
  → originating worker / parent consumes it
  → Agent OS decisions + GitHub evidence
  → Mastermind OS / Linear projections

Slack: notification and exact-reference transport, not runtime truth
```

These are integration boundaries, not instructions to create new services.

| Concern | Existing owner | Required addition |
|---|---|---|
| Office messages and pending answers | Conversation/application boundary | Durable request identity, target-specific drafts, recoverable asynchronous answer association |
| Intent and accepted decisions | Agent OS / declared project artifacts | Versioned interpretation, acceptance requirements, compact continuity |
| Admission, effects, cancellation and result lifecycle | Executive OS / Runtime | Scoped principal-originated decisions and exact reconciliation |
| Current occupant and session binding | RuntimeBinding / SessionTarget | Dot and eligible Chat bindings with enforced generations |
| Eligibility and resource placement | Model Router / Capacity | Actual account, role, data, mode, quota and host qualifications |
| Questions, results and recovery attention | Dialogue / Wake / Agent Relay | Event consumption, subscription health and missing-return repair |
| Source and proof | GitHub | Candidate-specific tests, independent review, actual product evidence |
| Portfolio presentation | Linear and Mastermind OS | Project current owner, dependency, next obligation and accepted outcome |

No new Meta-CEO database, agent election mechanism, company queue, session registry, memory authority, retry ledger, or provider router is needed. Where an incumbent owner lacks a field or contract, extend that owner instead of inventing an adjacent authority.

## 4. The office experience: one person, several concurrent missions

A single conversational identity should not force all projects into one undifferentiated prompt or serial approval chain.

Each user message retains its application request, audience, intended mission or company-level context, and current identity. The office can discuss several projects while each project keeps its own accountable owner and recoverable state. A late response about project A must not silently alter the selected project B or overwrite a newer Chairman correction.

The normal answer has three layers: the direct answer or ruling, verified actions and meaningful movement, and remaining limitations or a genuinely reserved decision. Activity logs, provider accounts, mode evidence and detailed receipts belong in drill-downs.

**Foreground behavior.** Record the message durably, then show a factual receipt. A proposed local product target is a persisted acknowledgment within two seconds at the 95th percentile under the defined acceptance load; this is a target for Mastermind’s application, not a promised Dot response time. Measure the first useful Dot response separately under idle and background-load conditions.

Reserve the primary’s work for interpretation, high-value decisions and concise synthesis. A primary turn should return after useful reasoning or committed delegation, not stay open while a child performs hours of work. Give foreground requests priority at safe admission boundaries without assuming a provider task can be preempted.

Do not render fake token streaming, label a queued task “working,” or fabricate progress to conceal latency. The app can independently show authenticated Runtime progress while a Dot explanation is pending. Pause-new-work and exact cancellation remain available through their actual owners without waiting for the conversational queue.

**Interruption behavior.** A Chairman correction creates a new intent revision. Pending actions that depend on the changed requirement are reconsidered; unrelated accepted evidence remains valid. An already-started effect is reconciled rather than retargeted by rewriting a prompt.

If the primary interface fails the conversational-fit test, retain the office architecture but do not declare that interface selected. Report the failed latency or continuity property and assess an eligible alternative explicitly. Do not hide another model behind the same identity as an unannounced “fast brain.”

## 5. Dot2API: useful transport, distinct security and transaction boundaries

The inspected upstream describes queued agent tasks, serial handling, delayed whole-answer delivery, and text-only compatibility. It explicitly does not position the gateway as a real-time chat backend. [P01]

Use its asynchronous task interface through the existing application/request owner, with one original request identity and recoverable task reference. Do not build the office around a long-held compatibility request whose generic SDK retries are allowed to create new work.

### 5.1 Principal and worker are different roles

PR #1360 is a research worker candidate. Preserve it. Reuse suitable transport, strict parsing and recovery code, but implement principal eligibility through Executive’s actual authority mechanisms. Do not widen the worker to “full access,” and do not make the office depend on every worker-specific broker qualification when a distinct principal integration can safely proceed independently.

Two patterns are acceptable:

**Proposal-only reasoning:** the Dot has actual read-only access to the relevant systems and produces a recommendation. A separately authorized command path commits effects.

**Scoped principal reasoning:** the Dot may call company actions during its turn, but each receiving service checks the authenticated connection, current role assignment, permitted action and resources, original operation, relevant revisions and effect identity before committing anything.

Do not combine the second pattern’s broad app access with the first pattern’s claimed safety merely by changing the prompt.

### 5.2 Enforce at the effect, not after the answer

Dot2API’s security documentation says it is not a sandbox and cannot constrain the Dot’s actions; task payloads and results also need storage protection. [P02]

Consequently, validating the final JSON cannot be the primary write control. The Dot might have called another connected app before producing that JSON. A local worker UID does not constrain a cloud account’s plugins.

For each participating Dot, qualify its real connected-app permissions, including tools that could bypass Executive. A company principal should not possess unrestricted deployment, trading, shell, or publication authority simply because it needs broad company visibility. Restrict unrelated write surfaces or retain their real human-confirmation boundary. If the provider cannot enforce a required isolation property, do not describe the account as a sealed read-only worker.

Treat the gateway as a trusted internal office boundary, not a public arbitrary-prompt endpoint. Keep credentials off the client, out of model-visible text and Slack, and outside transcripts and logs. Intersect task scope with actual account/data permissions at every service.

### 5.3 Reconcile the two transactions

Preserve R1’s important distinction: provider task execution and Executive command admission are not one transaction.

A Dot can admit a child and lose its response. The application must then reconcile both the original provider task and Executive command. A missing answer is not evidence that no child exists. Cancellation of a provider task is likewise not proof all external effects were cancelled.

Use existing idempotency and effect reconciliation. Design for duplicate transport delivery with one committed logical command, not an unsupported claim of exactly-once execution across provider and desktop boundaries. Where the original effect cannot be determined, hold that effect on its original carrier rather than replay it.

### 5.4 Close cross-channel concurrency

The application, direct Dot chat, Slack and event-triggered tasks can all present company work. Do not assume the gateway’s queue serializes every one of those surfaces.

All modifying company entries must join the same existing responsibility/turn eligibility rules. An account token authenticates a connection; a caller-supplied role name or task ID does not prove a current authorized turn. Receiving services must resolve the role and permitted operation from trusted current assignments, reject stale generations, and expose only the scoped action.

Qualification must establish what provenance the provider actually supplies. If exact concurrent-turn discrimination is unavailable, serialize modifying company eligibility more narrowly through the existing owner rather than invent task attestation. Read-only advice may continue, but stale or unrelated proposals cannot acquire write authority.

Failover changes the current occupant; it does not erase a predecessor’s pending effects or instantly cancel its provider activity. Fence late commands, reconcile the original effects, and keep recovery controls independent of the failed Dot.

## 6. Six Dots: role capacity, not six new departments

Keep R1’s useful functional skills, but avoid making every project pass sequentially through research, engineering, operations and quality Dots. The unit of accountability should be the programme or bounded project.

A recommended target allocation is:

| Capacity | Normal responsibility | Boundary |
|---|---|---|
| One primary office Dot | Chairman relationship, interpretation, portfolio choices and consequential cross-programme decisions | No bulk polling or approval of every ordinary edit |
| Up to three programme Dots | Each owns a coherent assigned programme, including research integration, ordinary rulings and delivery follow-through | No conflicting ownership; use specialists as bounded consultations |
| One quality Dot | Independent intent, evidence and user-journey review | Does not accept its own consequential work or quietly lower requirements |
| One operations/portfolio-relief Dot | Missing returns, capacity evidence, bounded operational recovery, backlog preparation and qualified standby | Not a simultaneous second Meta-CEO |

This is a capacity layout, not a permanent account-to-role mapping or a demand that all six remain busy. Existing accountable orchestrators and COO responsibilities are not displaced by creating these profiles.

Start with the primary and one programme responsibility; add an independent reviewer when testing consequential acceptance. Expand only when there is useful disjoint work and enough review capacity. Several projects can share a programme owner without each occupying a live provider turn.

Place accounts by eligible permissions, data audience, relevant context, actual task fit and capacity. Do not assume the Business accounts should automatically become CEOs or that a personal account may receive all Business information. Keep one normal public voice while making specialist contributions inspectable.

Routine rulings stay with the programme owner. The primary receives decisions that materially affect original intent, programme priorities, cross-programme dependencies or reserved acceptance. This is how the central experience remains unified without becoming a central bottleneck.

## 7. Memory and context: continuity without uncontrolled replication

Native memory remains useful, but it is not a complete operational record. OpenAI states that Dot tasks have their own conversations rather than automatically receiving every Dot conversation. Shared ChatGPT Projects also have bounded, project-only context rather than a union of participants’ outside memories. [P03, P04]

Preserve R1’s four context classes: personal/native memory, native Project context, accepted organizational continuity, and actual runtime/source evidence.

A company reasoning request should receive a compact context package assembled by existing owners:

| Context component | Purpose |
|---|---|
| Original intent reference and current revision | Prevent interpretation drift |
| Current role, grant and permitted audience | Bound decisions and disclosure |
| Relevant accepted decisions and non-goals | Preserve what is settled |
| Source/evidence references with freshness | Support grounded reasoning |
| Current carrier, effects and pending obligations | Prevent duplicate or conflicting continuation |
| Accepted work not to repeat | Avoid expensive rediscovery |
| Exact requested decision/output and proof | Give the turn a useful finish |

These are contract requirements, not a second context database. Extend the existing context/brief producers; do not create another organizational memory authority.

Keep recent office conversation in its legitimate application owner, accepted meaning in Agent OS, implementation evidence in GitHub, and lifecycle in Executive. Do not scrape and mirror every native transcript. A source reference can be retrieved progressively when needed.

Privacy follows the authorized audience. A business dossier, private email, personal memory or screenshot must not be copied to another account, Slack channel or external vision service merely because doing so improves convenience. An account’s rich context does not override the receiving audience’s access. Distinguish denied, missing and not-yet-retrieved context.

The continuity test should use meaningful prior constraints and a later correction, not only a synthetic password-recall exercise. The new turn must recover the right requirement, cite its source and avoid reverting to the superseded decision.

## 8. Close the decision-response loop and repair missing returns

Preserve one exact return obligation through the existing owners:

```text
Question recorded
 → responsible principal identified
 → authenticated event delivered
 → principal reads current request and evidence
 → scoped ruling committed
 → exact worker consumes the ruling
 → work resumes or stops explicitly
 → result reviewed against intent
 → originating parent consumes the disposition
 → office projects the verified outcome
```

OpenAI’s MCP Events documentation supports Dots and specified Work surfaces, not proof of ordinary Project Chat provisioning. It requires persistent subscription/callback handling. PR #1362 is relevant existing source for the reply-event boundary. [P05, E06]

A transport receipt closes only transport delivery. It does not close the decision, receiver-consumption, review, or parent-consumption obligation. These must remain independently observable.

The programme owner handles ordinary design and repair decisions. Cross-programme conflicts go to the primary. A real new expenditure outside the envelope, access consent, human-only ceremony, or material strategic change goes to the Chairman. Missing-tool claims require the bounded harmless evidence check before escalation; an explicit refusal is not a reason to probe another account.

Existing Wake should reconcile durable unconsumed obligations after restarts, subscription expiration or missed events. A deterministic reconciliation pass can recover missing notifications without waking six reasoners to inspect unchanged lists. Use revision/cause keys and current recipient resolution; suppress self-generated Slack loops and stale responses.

Backpressure belongs at admission. If decisions or reviews accumulate faster than owners can consume them, reduce new starts and prioritize blocked critical-path work. A growing queue of unreviewed results is not success.

For long research sessions, prefer a scoped result or decision returned directly by the participating session through an eligible company tool. A Secretary need not read and paraphrase every answer. Whether native Chat can receive a continuation and whether it can send a result are separate qualification questions.

## 9. Executive plugin integration contracts

Do not implement a universal “CEO super-tool.” Extend or reuse exact action families with bounded projections and server-side validation. Names below are semantic requirements, not claims of existing API endpoints.

| Contract | Required semantic input or association | Observable result |
|---|---|---|
| Qualified estate read | Authorized scope, current principal, pagination and freshness | Relevant programmes, dependencies, work and attention without inferred totals |
| Office turn admission | Application request, current office binding, intent/context revision | One accepted or rejected reasoning responsibility, without duplicate dispatch |
| Mission admission | Original direction, programme, grant, proof requirement and budget | Canonical command/Job reference or an exact gate |
| Decision response | Original question, current responder, expected revision, ruling and bounded continuation | Committed response with receiver-consumption status |
| Existing-session steering | Current root/target, intended semantic turn, source revision and authority | Exact delivery/consumption evidence, not an unstructured message-as-command |
| Review and repair | Immutable candidate/result, intent revision, reviewer and required proof | Accepted result or specific repair obligation |
| Pause/cancel/reconcile | Original effect/operation and current authority | Actual state, preserving completion/cancellation races |

Use existing schemas where they satisfy the contract. The first implementation package must map any missing semantic field to its actual owner and reject invalid requests there. Do not add a parallel record merely to fit this table.

Subscription signing, callback verification, access revalidation, delivery and consumption have different owners even when composed into one service. Reuse #1362’s appropriate source after review, without treating the draft as already installed or discarding its original-request boundary.

## 10. Grok Secretary and the native-Chat requirement

### 10.1 Qualify eligibility before automation

The reviewed OpenAI agreements contain restrictions relevant to automated output extraction and circumvention, with separate personal and business governing terms. The exact proposed workflow’s eligibility is not established by a different bot performing it. [P06, P07]

Distinguish technical absence from permission refusal. Keep the unresolved native lane attended unless an eligible integration is established. Do not build account switching or desktop relay as a workaround to an explicit refusal. This is a bounded feasibility determination, not a reason to stop unrelated core-office work.

The stage-zero native capability record must separately establish: eligible route, intended account/workspace, exact Project, conversation binding, observable selected mode, access to relevant Project context, permissible result return, continuation targeting, and failure reconciliation. A successful answer alone does not prove this complete chain.

### 10.2 Secretary responsibilities

For an eligible desktop route, the Secretary should perform interaction logistics, detect wrong targets or human-login boundaries, and return exact observations. It should not invent research objectives, decide product tradeoffs, lower acceptance standards, or issue unlimited generic “continue” prompts.

A continuation should come from the responsible programme’s committed ruling or bounded standing continuation policy. Semantic completion, a genuine question, unexpected effects or a changed scope returns to the principal. The child owns its own permitted investigate/build/test/repair loop; the Secretary should not micromanage every step.

Favor precise existing accessibility/interaction mechanisms for eligible tasks. Use external visual reasoning only where necessary and permitted by data policy. Measure any MiniMax perception offload rather than presuming it replaces Grok’s engine: Grok Bot currently manages model selection. [P08]

### 10.3 Transport and multiple secretaries

Cursor documents webhook-triggered Grok routines. This offers an additional candidate adapter: Executive/Wake can notify an eligible Secretary directly with an exact obligation reference, rather than requiring every request to transit Slack. Provider acknowledgment still does not prove the interaction or company result. [P09]

Keep one logical Secretary capability and an eligible execution pool. Use existing Capacity to assign unstarted work with host/account affinity. A second account can improve capacity or resilience when justified; it does not require a second secretary queue or a separate company hierarchy.

Separate three resources: provider reasoning capacity, a conversation’s current semantic turn, and the desktop’s active keyboard/mouse context. Hold the desktop interaction lease only while the interaction needs it; do not unnecessarily lock a computer for the entire research wait. Retain conversation/effect ownership throughout. A new interaction rechecks target identity and current eligibility.

A three-host/three-host split is a possible default affinity, not a permanent partition. Rebalance only eligible unstarted work. Started or ambiguous submissions remain with their reconciled original operation, even if another secretary has spare quota.

### 10.4 Reliability improvement, not “training to perfection”

Maintain a versioned interaction playbook and privacy-safe regression fixtures for wrong account/Project, modal dialogs, login expiry, changed mode labels, stream detachment, incomplete returns and ambiguous submit. Separate observation failures from action failures.

A finite test campaign cannot prove perfection. The mechanism must detect uncertainty, avoid duplicate effects, preserve the obligation and choose a safe recovery path. Provider or UI drift should invalidate the affected qualification, not silently relabel the adapter healthy.

## 11. Capacity, economics and weekly sustainability

**There is not enough measured evidence to conclude that one Grok account will support the proposed week.** Six computers do not answer that question.

Cursor’s documentation says linked grants do not add to a Cursor plan; the higher applicable grant is used. On-demand spending also requires care because an in-progress task is not necessarily interrupted at the configured limit. [P10]

Start with the current eligible Secretary account and software that can admit additional independent capacity later. Do not purchase two or three subscriptions before measuring actual demand, and do not assume a linked grant buys all the other products mentioned in the original prompt.

Measure intervention classes rather than message counts: session setup, targeted continuation, exceptional UI recovery, result routing and human-boundary detection. Separate reasoning time, desktop occupancy, queue delay and account consumption. Measure primary-Dot wait and programme review backlog as well as secretary quota.

Use the following planning equations with observed values, not invented provider limits:

```text
weekly demand = Σ(expected interventions in class i × observed cost of class i)
                + measured recovery allowance

secretary pool adequacy = weekly allowance adequacy
                         AND peak-response adequacy
                         AND required resilience
                         AND route/data eligibility
```

For uncertain meters, estimate ranges and preserve a recovery reserve. R1’s illustrative 70–80% planning envelope is a possible target, not a published limit. Use representative busy periods as well as ordinary days.

Do not keep a reasoning bot checking every computer every few minutes. Event-triggered interaction and deterministic obligation reconciliation should remove most empty checks. A cloud routine being scheduled does not prove a local desktop is reachable.

Adding a second paid account addresses only independently permitted capacity. It does not clear a refused action, revive an unknown submission, or eliminate provider-wide outages. Extra personas on the same account must not be counted as independent allowances.

Track total cost per accepted outcome, including principal review, failed starts, retries allowed by the original owner, visual perception and repair. A cheaper model that creates extensive rework may be the expensive route.

## 12. Autonomy: a strategic loop and an operational loop

R1’s standing charter is essential. Make it executable enough to let Dots proceed without repeated permission while retaining genuinely reserved decisions.

The charter identifies approved programme objectives, permitted surfaces and data, bounded spending, release limits, concurrent work, review responsibilities, and escalation criteria. An ordinary continuation inside that envelope is already authorized. A new issue is evidence to assess, not automatically executable authority.

**Operational loop:** consume decisions and useful returns, repair bounded failures, advance cleared dependencies and verify the next product increment.

**Strategic loop:** assess material observations against approved company goals, recover relevant existing work, compare the value of finishing, extending, researching or stopping an effort, then admit a bounded outcome through existing owners. This loop can decide that a proposed feature should not be built.

The primary should not routinely ingest every log or open every repository. Programme owners maintain compact evidence; the primary synthesizes the few decisions that affect the company’s direction. Existing priority and admission mechanisms retain authority; a new “AI priority score” must not quietly become another scheduler.

When idle, first resolve pending decisions and reviews, then advance admitted critical-path work, then perform bounded relevant discovery allowed by the charter. When no useful authorized work remains, sleep. Constant activity is not the objective.

The central product measure should be **accepted user-visible outcomes relative to avoidable Chairman interventions**, supported by decision-resolution time, overdue obligations, rework and effective spend. Do not optimize for number of agents, open chats, generated tokens, or issues touched.

## 13. Preserve original intent and evaluate the actual principal

### 13.1 Two acceptance questions

First: **Did the plan correctly translate the Chairman’s intended outcome?**

Second: **Does the delivered product actually satisfy that accepted interpretation?**

R1 already defines an intent contract. R2 adds an explicit test of that interpretation rather than assuming the contract captured the original idea correctly. Both questions must be tested from the first vertical slice.

The versioned intent contract should preserve original wording or reference, user problem, concrete user journey, must-haves, non-goals, design/evidence examples, relevant constraints and proof. Record consequential interpretation choices with rationale. Do not require a large formal specification for a trivial reversible repair.

For this very programme, a required trace is:

| Original intent | Required proof |
|---|---|
| “I speak to one central chat” | User never has to select among six Dots to finish the normal journey |
| Main CEO knows existing projects | Census identifies relevant accepted work and avoids a duplicate programme |
| Native Chat research, not silent Work replacement | Actual eligible Project Chat path or explicit incomplete/attended status |
| Workers do not strand on questions | Correct principal rules and the originating worker demonstrably consumes it |
| Autonomous progress | An approved event advances useful work without another Chairman kickoff |
| Delivery matches the original idea | A deliberately plausible but wrong/incomplete product is rejected |
| App can show the company | Displayed status matches qualified owners, with missingness and freshness |

An author may propose a changed requirement, but must not weaken it to make its own work pass. Reviewers need the original intent and actual artifacts, not only the author’s narrative.

### 13.2 Quality without an approval bureaucracy

Use risk-proportionate independent review. A consequential architecture or customer-facing release needs independent evidence. A minor in-scope reversible correction does not need a six-Dot council.

Separate research adequacy, product interpretation, implementation correctness, user experience and release acceptance. Preserve any independent review required by the existing source/release rules. Do not mistake “independent” for simply asking another identical prompt with the author’s answer attached.

### 13.3 Evaluate surfaces, not model branding

Do not assume that the Dot will outperform native Pro or Extra High merely because of its advertised model. Evaluate actual Mastermind work: ambiguous requirements, source contradictions, ordinary blockers, genuine permission boundaries, intentional false-completion examples and Chairman corrections.

Run two comparisons: one with the relevant context normalized to isolate reasoning differences, and one with each proposed surface’s realistic context/tools to assess the delivered system. Preserve visible mode and configuration; served identity remains unknown when not observable.

Judge requirement coverage, supported conclusions, useful rulings, refusal accuracy, false acceptance, recovery, review effort and total cost. Blind model labels where feasible. Include held-out cases not used to tune the playbook. Prefer fewer high-quality independent reviews over several correlated rubber stamps.

## 14. Implementation sequence and bounded work packages

Stages are dependency gates, not calendar promises. Logical owners below are proposed assignments, not dispatched workers.

### Stage 0 — Resolve the decision-changing unknowns in parallel

**0A: Dot office qualification.** Establish an eligible principal connection, actual company-tool permissions, one source-grounded turn, continuity into a subsequent corrected turn, foreground/background behavior and recoverability. Preserve the earlier refused credential action; any enrollment proceeds only through an independently established permitted action, not a carrier workaround.

**0B: Native-Chat feasibility.** Establish the exact eligible route and demonstrate or explicitly fail the account/Project/mode/context/result/continuation chain. Do not defer this existential question to the fifth build stage. A held native lane does not stop independent 0A/0C work.

**0C: Principal decision and event seam.** Map exposed account-specific actions to the actual Executive owners, inspect #1362’s relevant source, and identify the smallest installed callback/ruling/consumption proof. An estate read is not enough.

**Exit:** every critical assumption is observed or explicitly unresolved with an affected capability and reachable next action. Do not describe an untested route as either proven or impossible.

### Stage 1 — One complete vertical office loop

Use a small genuine existing programme need with bounded effects. The app records a direction; the Dot performs relevant census and records intent; Executive admits the work; the worker raises a real ordinary ruling; the correct principal answers; the worker consumes it and continues; independent evidence rejects an intentionally incomplete alternative; the original parent consumes the final disposition; the app shows the truthful outcome.

Include response-loss recovery, duplicate delivery and stale-intent rejection now, rather than after six-account rollout. Do not manufacture a production mutation merely to test a tool.

**Exit:** one trace proves useful user capability, not just task transport. No Chairman message shuttling, duplicate admission or unsupported completion claim.

### Stage 2 — Programme delegation and independent quality

Add a second programme only when work is disjoint and current ownership permits it. Prove that the primary remains available while programme owners handle routine decisions. Add independent quality and test a reviewer-authored-work rejection or reassignment.

**Exit:** concurrent programmes preserve scope, data audiences, current owners and review capacity; one user voice does not impose one serial decision chain.

### Stage 3 — Integrate the qualified native research path

Only after Stage 0B establishes eligibility, join native Project Chat research to the same intent, decision and return obligations. Prove relevant Project context, selected mode evidence, exact continuation and parent-consumed result. Prefer a participating session’s scoped tool return where supported rather than full-output relay.

**Exit:** the required native experience works through the installed path, or this release remains explicitly core-office-only/attended-native. No substitution is concealed.

### Stage 4 — Scale eligible Dots and Secretary capacity

Expand to all useful eligible accounts, test role relief with stale-writer rejection, measure representative ordinary/busy demand, and conduct a genuine seven-day observation campaign once installed.

**Exit:** no lost decision obligations, wrong-target writes or unaccounted spending in the accepted campaign; measured responsiveness and quota are adequate; original-intent review still works under load. A finite campaign is evidence, not a mathematical guarantee.

### Source-bounded implementation packages

| Package | Existing seam | Deliverable and proof |
|---|---|---|
| Office integration | `app/mastermind_os/src/meta-ceo/`, existing Conversation/MissionHost boundary | Durable submission and exact async answer, target/auth invalidation, delayed-response recovery |
| Principal integration | Existing Executive authority, RuntimeBinding and action owners | Scoped admission, ruling, steering, review and pause; stale or forged role rejected |
| Transport reuse | #1360 and `integrations/dot2api/` | Shared transport where appropriate; separate principal/worker permissions; original task recovery |
| Return integration | #1362, existing Dialogue/Wake | Callback qualification, exact obligation read, committed response and receiver/parent consumption |
| Context and quality | Agent OS brief/continuity owners, GitHub evidence | Original-intent trace, correction propagation, planted-drift rejection |
| Secretary adapter | Existing eligible host/Capacity/Wake owners | Qualified target interaction, uncertain-effect hold, direct exact-reference trigger and measured usage |
| Portfolio projection | Existing Mastermind OS/Linear projection owners | Actual responsibility, next obligation, freshness and verified outcome without a second queue |

Parallelize disjoint seams after agreeing the minimal contracts. Do not commission multiple writers against the same boundary or silently displace the current source carrier. Source ownership and live-operation custody are distinct.

## 15. Acceptance, failure and rollback campaign

All rows below are proposed tests. Provider and product claims require installed-path evidence; unit fixtures alone do not satisfy them.

| Test | Required outcome |
|---|---|
| Ordinary question while a child is working | Primary answers without waiting for child completion; no invented progress |
| Consecutive office tasks with a correction | Relevant continuity is recovered; the latest intent wins |
| Timeout after provider acceptance | Original task is inspected; no automatic second submission |
| Child admitted but Dot answer lost | Original Executive command and provider task are reconciled |
| Direct Slack and app turns overlap | Only currently eligible scoped company effects commit |
| Old Dot responds after relief | Late command rejected; predecessor effects remain recoverable |
| Caller supplies a CEO role string | No authority is granted from prompt content |
| Claimed read-only Dot attempts a connected-app write | Receiving permissions block it, or the claimed isolation fails qualification |
| Callback repeated or out of order | No duplicate ruling/effect; newer accepted revision preserved |
| Subscription expires or event is missed | Existing obligation reconciliation restores attention without losing work |
| Worker asks an ordinary design question | Programme owner decides and exact worker consumes the ruling |
| Worker claims a missing tool without evidence | A bounded harmless check is requested, not blind escalation |
| Explicit provider permission refusal | Affected action held; no alternate-account workaround |
| Real login or new consent is required | Exact human-only step surfaced; independent useful work continues |
| Native Project or selected mode cannot be verified | Requested native capability remains unproven |
| Secretary submits into a wrong target | No effect; mismatch detected before submission |
| UI stream detaches after submission | Original interaction reconciled; no blind continuation |
| Two secretaries seek one desktop | One active interaction writer; conversation ownership remains separate |
| Different data audiences share a programme | Retrieval and return respect permissions; no cross-account context leak |
| External vision would receive private information | Data permission checked before disclosure |
| Secretary quota is exhausted | Work remains truthfully pending; no hidden on-demand activation |
| Reviews accumulate | New admissions reduce; review/decision backlog gets priority |
| Green CI with missing must-have | Result rejected with precise repair, not accepted on test count |
| Spec is internally consistent but misreads original ask | Intent-translation review rejects it |
| Reviewer authored consequential work | Independent review assigned without losing existing effects |
| User logs out during a read | Private data cannot appear in a successor identity’s view |
| Cancellation races with completion | Actual terminal effect preserved; no false cancellation claim |
| Runtime restarts | Same request, obligations and pending effects recover |
| Programme reaches its accepted finish | Watches close; no invented successor project |
| No useful admitted work exists | Dots remain idle rather than creating a task treadmill |

For wrong-target writes, duplicate effects, unauthorized disclosure and stale-principal commands, require zero observed violations plus credible enforcement at the relevant boundary. If the enforcement mechanism is missing, a clean small test sample is insufficient.

Rollback disables new admissions for the affected role/route while preserving in-flight task IDs, effects, results and pending consumption. Uninstalling a UI or stopping a provider does not prove a child stopped. Test administrative pause and exact reconciliation without depending on a responsive Dot.

## 16. Alternatives and rejected shortcuts

**All relay through Grok:** simpler to imagine, but couples ordinary company decisions to desktop availability and Secretary quota. Reject as the default. Retain Grok for eligible interaction work that genuinely needs it.

**Six co-equal Dots in Slack:** distributes activity but leaves conflicting decisions, duplicate work and fragmented accountability. Reject. Use one public office and scoped programme responsibilities.

**API/Work replacement of native Projects:** may be a useful separate capability, but does not satisfy the stated native-Chat requirement. Do not adopt silently. Any paid alternative retains current budget and routing rules.

**One Dot does everything:** preserves a single voice but overloads context, response capacity and review. Reject as the scale model; retain direct handling for bounded work that does not benefit from delegation.

**Build all control infrastructure before a user journey:** produces many specifications without proving the office. Reject. Extend only the seams needed by the first complete loop, then expand against observed bottlenecks.

**Train the Secretary until errors disappear:** inadequate reliability strategy. Improve the playbook, but require detectable uncertainty, current target proof, scoped permissions and durable recovery.

## 17. Architecture decisions to adopt and exact next boundary

Adopt one logical office; a qualified primary Dot; programme-owned ordinary decisions; native Project Chat as a distinct required full-vision capability; existing Executive/Agent OS/Fabric ownership; direct exact-reference returns; server-enforced permissions; original-intent and delivered-product acceptance; and measured, event-driven capacity.

The next implementation boundary is the **three-part Stage 0 qualification**, not another six-account enrollment wave: establish conversational Dot fit and permissions, settle native-Chat eligibility and actual capability, and prove the smallest principal-decision/return seam. In parallel, prepare the Stage 1 intent and user-journey acceptance fixture so qualification immediately feeds a useful vertical slice.

The design is decision-ready. The selected provider bindings, principal writes, native-Chat lane, six-account permissions and weekly economics are not production-proven by this document. The core office can progress while one capability remains held, but the final release description must preserve that distinction.

---

## Evidence register

References identify what was inspected, not an assertion that all referenced proposals are accepted or installed. Repository file facts were read at immutable refs; live observations have separate timestamps.

**R1. Supplied baseline.** `mastermind_meta_ceo_master_plan_2026-10-12.md`, 17 sections plus source register; read with the Chairman’s original prompt. R2 preserves its terminology and ownership and identifies its own additions explicitly.

**E01. Protected procedure.** `mastermindx-market-intelligence/Mastermind@66c3a1e179db208202e6b7879563293aa87f850a`: `docs/sol_skills/INDEX.md`, `COLD_START.md`, `ACTIVE_EXECUTION.md`, `SESSION_RELIABILITY.md`, `WEB_CEO_DELEGATION.md`. Schema/version checked compatible with bootstrap major 1.

**E02. Existing architecture.** Same protected ref: `docs/superpowers/specs/2026-08-29-chat-native-meta-ceo-core-model-design.md`, especially included-plan cognition, one logical office, authority/dependency/dialogue separation, context and role replacement.

**E03. Existing office.** Same protected ref: `app/mastermind_os/src/meta-ceo/README.md`; preview/effect boundary, host provenance and live-acceptance gaps.

**E04. Dot worker candidate.** `https://github.com/mastermindx-market-intelligence/Mastermind/pull/1360`; retrieved open/draft metadata and head `343c08b8ddd66c37297d813e11031bb43969d804`. Body test claims are carrier-reported, not rerun here.

**E05. Worker runbook.** `docs/runbooks/dot2api-worker.md` at E04’s candidate head; principal separation, local service and enrollment/qualification instructions.

**E06. Reply events candidate.** `https://github.com/mastermindx-market-intelligence/Mastermind/pull/1362`; retrieved open/draft metadata and head `4e574cc24ac7a56c52e87ed5ab9a02802b8ce359`. Body describes signing/callback source, not installed proof.

**E07. Wake implementation descriptor.** E01 protected ref: `control_plane/wake_transport.py`.

**E08. Direct connector observations.** `Mastermind_Executive_V3.executive_state`, successful at `2026-10-12T07:44:02Z`, server `1.5.0`, installed grounding `a858ac249296ffaa7bf523863dea5917bbbc1f24`, 25 Jobs/33 Attempts; `session_targets` successful with an empty list. Neither read performs or proves a principal write.

**P01. Dot2API contract.** `https://raw.githubusercontent.com/Pluviobyte/dot2api/66a761505ff73c5dca730260efcaeb5697db81ad/README.md` — inspected exact upstream revision.

**P02. Dot2API security.** Same upstream revision, `SECURITY.md`: `https://raw.githubusercontent.com/Pluviobyte/dot2api/66a761505ff73c5dca730260efcaeb5697db81ad/SECURITY.md`.

**P03. Official Dot behavior.** `https://help.openai.com/en/articles/20001530-getting-started-with-your-dot` — task conversation/context distinction and product capability description.

**P04. Native Project context.** `https://help.openai.com/en/articles/10169521-projects-in-chatgpt` — shared/project-only memory boundaries.

**P05. Official event interface.** `https://developers.openai.com/plugins/build/mcp-events` — supported recipient surfaces and subscription/callback requirements.

**P06. Personal agreement.** `https://openai.com/policies/terms-of-use/` — restrictions relevant to extraction and circumvention. This review does not resolve permission for an unspecified automation deployment.

**P07. Business agreement.** `https://openai.com/policies/services-agreement/` — separately relevant agreement; personal-account terms are not assumed to govern every business seat.

**P08. Grok settings.** `https://cursor.com/docs/grok-bot/settings` — managed model selection.

**P09. Grok routines.** `https://cursor.com/help/grok-bot/routines` — webhook-triggered routines and usage considerations.

**P10. Grok billing.** `https://cursor.com/help/grok-bot/plans` — applicable grant, metering and on-demand behavior. Exact six-host weekly adequacy remains unmeasured.

**Evidence limitation:** This is an independent document/source review with bounded live reads, not a code audit of every integration, a provider-approved automation certification, a six-account capability campaign, or an executed system benchmark. No source, installation, selection, enrollment, scheduling or release effect is implied by the local deliverable.
