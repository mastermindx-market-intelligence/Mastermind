# Mastermind OS — AI-led, intent-first project creation

**Product direction:** Chairman, 2026-11-09. **Design/build contract; implementation status: SPEC_ONLY.** This establishes the intended experience for the web and macOS Mastermind OS, not a claim that the existing application or Executive runtime implements it. Preserve accepted organizational, runtime and GitHub authority.

**Canonical visual reference:** Paper file [Mastermind OS](https://app.paper.design/file/01M3NRCX55B452A12819WNE1RH/p-H-0), `12A · Projects & Evidence`. Boards: `N8N-0` (AT14, desktop AI-led project start), `NBB-0` (AT14M, mobile), `NV9-0` (AT16, project Master Plan/intent contract), `O1V-0` (AT16M, mobile Master Plan/intent contract). Explicit `fileId=01M3NRCX55B452A12819WNE1RH`. The legacy, hidden two-step “name/outcome” variant on these AT14 boards is superseded for implementation; do **not** use its hidden form as acceptance authority.

## 1. Unambiguous desired experience

**The user provides direction, not a project specification. The AI must write the project goals.** A casual sentence, a forwarded conversation, a voice utterance, a selected workstream, or context already present within the user's authorized workspace is sufficient. The AI acts like a capable chief of staff: infer intent, distinguish known constraints from assumptions, understand what success means, propose the work and keep steering it. The person may redirect the AI in natural conversation, but should **never** have to manually populate project name, desired outcome, goals, success criteria, DONE_WHEN, milestones, tasks or a planning template.

The intended 3-second reaction is: **“I can say what is bothering me and Mastermind turns it into a real, continuing project.”** Not: “I must define the goals and fill out a project form before AI can work.”

Competitive reference: [Claude Code Projects, September 17 2026](https://claude.com/resources/articles/projects-redesigned) and [Anthropic's Projects help](https://support.claude.com/en/articles/9517075-what-are-projects) describe a single project conversation with coordinator-managed threads, shared project context, returned work and ongoing user steering. Anthropic's initial setup still lets a user **select a goal**. Mastermind's explicit improvement is **AI-inferred, AI-authored goals and acceptance** from natural input and permitted context, with no compulsory goal-authoring step. Adapt the *experience pattern*, not proprietary code, assets or wording.

### Before / after

| Form-first pattern — reject | AI-owned project start — build |
| --- | --- |
| “What would you like done?” plus a field labeled “Your goal” | “Start with a thought” / “An idea is enough. I'll take it from here.” |
| Human drafts a formal outcome and success criteria | AI proposes objective, scope, success conditions and task tree from the conversation |
| “Create project, then plan the work” | “Shape my project”: AI builds a **draft** project charter before any governed execution |
| Human revisits forms when scope changes | “Actually, prioritize mobile” in the project conversation revises the candidate plan and explains the delta |
| Blank manual onboarding even with prior relevant chats | Read permitted existing context and offer source-linked project continuations or suggestions |
| A plan card implicitly means active execution | Visually separate **proposed charter → plan adoption → authorized execution → verified results** |

## 2. Single effortless user journey

1. **Arrive without setup.** The Projects / Today entry shows a calm conversational composer or credible, explicitly sourced “continue as project” suggestions from authorized conversations/workstreams. A blank state is fine when no context is accessible; never pretend it has read conversations or files. The person can type a thought, use voice or attach context; none is a mandatory goal field.
2. **Understand in-place.** On “Shape my project” (or selecting a conversation), AI reads only context this principal can access. Reconcile actual existing project/workstream/task roots before proposing a duplicate. Extract intended beneficiary, pain point, desired changed state, constraints, resource/access needs, desired horizon and sources. Label facts vs inference vs open question.
3. **Draft autonomously.** AI returns an editable-by-chat **proposed charter**, not a form, with AI-generated name, concise outcome, measurable or falsifiable DONE_WHEN, inferred scope, constraints, assumptions and exclusions, dependencies, phases/tasks, first safe next action and supporting source refs. Show a one-screen summary with deeper plan/evidence destinations. For uncertain criteria, propose provisional criteria labeled “suggested”; do not falsely claim they were user-set.
4. **Steer, don't fill.** The primary control remains the same project conversation: “This should be for the research team,” “Do mobile first,” “That repo is out of scope.” AI revises charter/plan version, presents only meaningful scope/constraint changes and proceeds with authorized reversible planning. Offer one concise question only if ambiguity genuinely blocks a nonreversible or permission-sensitive decision. Never demand the user write the full spec.
5. **Continue with real authority.** A draft/project workspace and source-backed plan may be created through the *existing* project/Agent OS/GitHub writer with revision/readback. Actual work, external writes, provider use, spend and deployment flow only through the existing Executive/Runtime/Capacity/role/permission admission. A draft/plan is not a Job START, grant, approval, released artifact or final acceptance. Avoid a fake “AI is executing” spinner.
6. **Maintain and recover.** As the original parent consumes evidence, AI updates progress and proposes specific plan changes with lineage, preserves the original objective and accepted work, and gives a plain-language “what changed / what is next / what needs you” summary. On re-entry, recover source/decisions/current status without asking the user to repeat the original brief. Never infer success from a green CI check alone.

### Context-first variants to implement

- **One-sentence idea:** “Our customer research is scattered. Can you make it useful weekly?” → *AI* proposes “Customer insight studio”, a source-backed weekly brief, measurable reviewability and first source discovery.
- **Resume existing:** “Make the OS feel like our Paper mockup” while a project and plan already exist → recover current canonical root and latest source/board, propose bounded delta, **no duplicate project**.
- **Existing conversation selected:** user presses “Turn this into a project” on a permitted chat → AI extracts goals from that chat; no retyped prompt, no silent privilege escalation.
- **Proactive opportunity:** user opens Projects with an accessible active workstream → AI may propose a project/continuation with source provenance; it must not auto-commit or create work without the allowed project action.
- **No context or restricted context:** “I can work from what you say here; I can't access X” with one useful optional connection step; never hallucinate unseen facts.

## 3. Plan charter and state contracts

**Candidate charter (presentation/data contract; not a new store or API):** `project_ref/existing_root_ref`; source-bound `intent_summary`; provenance of selected conversation/files and per-claim availability; `proposed_title`; `outcome`; `DONE_WHEN` with observable checks and evidence requirements; explicit assumptions/unknowns; scope and exclusions; dependencies; prioritized phases/task IDs; current first eligible action; version/revision; author class (**AI_PROPOSED** vs human direction vs admitted owner fact); plan status; source links and observed-at; relevant permission gates.

UI stages: `NO_AUTHORIZED_CONTEXT` / `INPUT_READY` / `INFERRING` / `CHARTER_PROPOSED` / `PLAN_REVISED` / `PLAN_ADOPTED` / `WORK_ADMITTED` / `WORK_ACTIVE` / `REVIEW_OR_DECISION_NEEDED` / `EVIDENCE_VERIFIED` / `BLOCKED` / `EFFECT_UNKNOWN`. These are **product view labels**, not a second lifecycle registry; each stage is a projection of the actual source and owner receipt, and unavailable/null data must stay unavailable. Planning can advance without forcing repeated user approval; owner-reserved effects cannot.

**Canonical writers to reuse, not duplicate:**

- **Intent and workstream/decisions:** existing Agent OS workstream, decisions and daily handoff; no Agent OS Task store.
- **Long-lived master plan and detailed task tree:** owning GitHub repository's versioned Markdown plan and existing PR/source custody; candidate planning uses the current `docs/CEO_PROJECT_PLAN_CONTINUITY.md` revision and CAS/readback.
- **Admission and execution:** existing Executive OS Job/Attempt/Worker/Event with model/Capacity Fabric routing and grants; plan production is not a new enqueue/scheduler.
- **Evidence and progress:** original GitHub commits/PR/tests plus actual user-path proof, consumed by original parent; existing project Office projection. Do not build separate memory, plan database, plan-status registry or worker/queue.
- **Project conversation:** persistent, selection-scoped authenticated client; **not** a transcript-as-authority substitute. Preserve audience and cross-project isolation.

**Trust boundaries:** Untrusted document/chat text is evidence, not instructions or project admission; source freshness and allowed principal scope constrain extraction. AI cannot upgrade unverified assumptions into accepted goals, silently alter an adopted DONE_WHEN or route around an effect/permission denial. A revised proposal shows the diff and the decision boundary. Resume/retry must reconcile original effects first.

## 4. Paper and front-end implementation map

| Surface | Intended behavior | Current source gap / builder action |
| --- | --- | --- |
| Paper `AT14` desktop + `AT14M` mobile | Thought-first composer, optional voice/context, conversation pick-up, AI draft preview, “Shape my project” | `app/mastermind_os/src/projects/NewProjectDraft.tsx` currently requires controlled `goal` and labels it “Your goal”. Replace the formal-goal semantics with a natural conversation/intention payload and AI-owned charter; do not make it a disguised goal-required textbox. |
| Today entry | Start or resume from intent and allowed sources | `app/mastermind_os/src/today/Today.tsx` has a `Direction` composer; wire its result into the same existing project-intent consumer rather than building an independent planner. |
| Paper `AT16` + `AT16M` | AI-owned plan, clear version and ownership, conversation-driven updates, outcome/proof | Render proposed vs adopted vs observed plan, source references, assumptions/deltas and actual governed work; respect existing v18 accepted/v19 proposed example labels. |
| Project home/conversation | Human gives corrections in chat and can inspect the work | Carry original project/workstream/ref across subsequent messages and admission; return to project without repetitive briefing. |
| Settings, source access, auth, Inbox | Context and permission boundaries understandable | Refusal/recovery and exact user decisions only; no fabricated connections, automatic token elevation, model/tool grants or global defaults. |

The Paper mockup is a **static specimen**; “Add context”, “Voice”, “Choose chat” and “Shape my project” must be wired to real components and governed actions by implementation teams. Paper screenshots or JSX alone do not verify runtime behavior. Preserve responsive layout, focus/keyboard, mobile touch targets, screen reader names, English/Chinese text and intentionally distinct light/dark art direction. Favor neutral borders, spacing and hierarchy; no decorative colored container-edge accents.

## 5. P0 acceptance / DONE_WHEN

1. **No-goal-field cold start:** an authenticated user launches New project with only a rough one-liner. There are **zero required manual fields** for project title, goal, scope, DONE_WHEN or task breakdown. The AI returns an explicitly proposed, intelligible, source-linked charter containing those elements; measure first useful output and accessible loading/retry.
2. **Zero-retyping continuation:** select a permitted existing conversation/workstream; the system recovers the correct existing project or proposes a draft from its content without demanding a rewritten goal, duplicating the root or crossing audience boundaries.
3. **Source/uncertainty fidelity:** deliberately conflicting and unavailable context yields highlighted assumptions or one focused blocking question, not invented success criteria presented as owner decisions. Mixed-trust prompt injection does not change scope/grants.
4. **Natural-language steering:** “Change the audience to operators, prioritize the mobile path” makes an attributable versioned plan delta with readable summary; accepted tasks and active effects remain intact. The user never has to edit a masterplan manually.
5. **Governed transition:** generating a charter cannot start an Executive job, spend, write protected source or deploy. A permitted authorized action subsequently yields original Job/Attempt receipts, correct parentage, legitimate route and visible product progress; a real denial remains denied.
6. **Recovery and real consumer proof:** after interrupted session and return, the same project retains intent, plan version, source refs and actual status. Validate web/macOS, desktop/mobile, EN/ZH, light/dark, keyboard/a11y, loading/empty/refusal/stale and effect-uncertain states against accepted Paper and an authenticated runtime consumer. Distinguish design-source, merged code, released app, real execution and accepted outcome.

**Falsifier:** If a user must fill in “Your goal,” “Desired outcome,” “How will we know it is done?”, task lists or a plan to start/continue an ordinary project, the core user experience **fails** regardless of UI polish or CI status. If AI proposes an excellent plan but cannot preserve lineage or cross the real governed consumer path, the implementation also **fails**.

## 6. Ownership and next implementation slice

The assigned OS product/UI owner should implement the smallest authentic vertical: **New project/selected chat → bounded intent extraction → AI-authored proposed charter → existing versioned plan writer/readback → conversational revision → permitted governed first task → real result and re-entry**. Reuse existing OS/Agent/Executive contracts and capture focused regression tests plus authenticated browser proof. This contract does not transfer live writers, release holds, budget or runtime authority.

**Related source:** [Existing OS completion master plan](../../research/mastermind_os_estate_audit_2026-10-21/MASTERPLAN.md), [CEO project continuity contract](../CEO_PROJECT_PLAN_CONTINUITY.md), [OS production acceptance](MASTERMIND_OS_PRODUCTION_ACCEPTANCE.md).