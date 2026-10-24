# CEO Project Plan and Crash-Continuity Contract

**Status:** Source contract. A branch or draft PR containing this file is `SPEC_ONLY`, not a deployed Executive editor, live ChatGPT Project setting, Agent OS write grant, or proof of automatic recovery. Adoption requires reviewed protected-source release and a real consumer canary.

## Purpose and scope

Any assigned CEO, Meta-CEO, project orchestrator or equivalent (ChatGPT Web Pro, Codex/Astra, Claude/Fable/Opus, Grok, or a future admitted harness) must be able to lose its conversation without losing the accepted project's direction and progress. The goal is **recoverable work, not immortal chat sessions**.

Apply to a project with multiple coherent phases, dependent deliverables, external children, consequential plan revisions, or continuation expected beyond the present chat. A trivial bounded answer needs no new project artifact. A genuine exploratory project may first perform the minimum safe investigation required to scope a useful plan, then persist the plan *before substantial execution or delegation*. Do not let an elaborate planning ritual postpone useful authorized action.

This contract does **not** create a new lifecycle, project registry, task queue, memory store, lease, authorization plane, runtime admission, GitHub publication right or Slack/Linear writer. Follow the protected `docs/sol_skills/INDEX.md`, active source law, actual resource grants, and existing current responsibility and effect fencing first.

## Canonical homes: one planning experience, existing owners

This is the Executive Ecosystem programme ownership split. Do not collapse these three records into one status graph or one "latest" file.

| Information | Canonical owner | Permitted representation |
|---|---|---|
| **Pinned plan:** workstream objective, inline waves, accepted decisions, discoveries, and the recovery frontier | Macro **Agent OS** | Existing `agentos/workstreams` (waves are the plan), `decisions`, `discoveries`, and dated `agentos/handoffs/<WS-KEY>-<YYYY-MM-DD>.md`. `compile-context` keeps the latest dated handoff only |
| **Task tree:** hierarchy, dependencies, node evidence, specifications | The owning repo's **master plan** | Versioned Markdown in that repo. Editorial labels below only. Not a second plan, wave status, or task registry |
| **Live work:** admitted Job, Attempt, Worker, admission, claim, lease, lifecycle and effects | **Executive OS** `control_plane` and the current RuntimeBinding/continuity owner | Existing typed admitted plans, Jobs, Attempts, Events, and runtime read APIs |
| Portfolio/issue list and human-selected progress view | **Linear** | Existing projection, no competing planning authority |
| Messages, exact dialogue turns, delivery and presence | **Slack / approved transport** | Existing carrier/thread, never a lifecycle substitute |
| Convenient conversation context | **ChatGPT Project history** | Advisory only, never required to recover a plan |

`DEC:AGENTOS-NO-TASK-STORE` still holds: Agent OS has no Task entity. Waves plus PRs are the pinned plan; a pre-PR Job store, when it exists, is the Executive dispatcher. The repo master plan may hold a deep task tree. It must not become a second task registry, priority queue, or copy of wave status and Job state. Merged orchestrator continuity W0/W1/W2 (`WS:ORCHESTRATOR-PROJECT-CONTINUITY`, Mastermind #1664, #1666, macro #9967) already published that workstream's waves, cumulative handoff, and research plan. Reuse those records. Do not re-encode their waves as a new `P1.T*` status registry.

Ownership is a role, not a session: if the named owner is absent, orphaned or not you, assume leadership, record the takeover, proceed; independent review still required; never self-merge or approve.

Executive OS may present one coherent **project cockpit**, but each mutation goes to the owner of that fact: task-tree edits to the repo plan writer, wave/handoff/decision edits to the Agent OS writer, runtime effects through existing Executive admission. No second plan database and no independent `latest` checkpoint directory. One project may have a deep task tree while each bounded Executive execution plan remains subject to its own existing validator and step limit. Never expand the admitted-plan schema to hundreds of nested steps just to mimic the task tree.

## A. Before substantial project execution: acquire or create the plan

1. Pin current protected source and existing workstream/operation identity. Read the workstream **waves** (the pinned plan) and the latest dated handoff the compiler would select. Open the task tree at the workstream `artifacts` path. `agentos.handoff.v1` has no master-plan SHA field, so a missing SHA is not a failed identity. Search the owning repository for a current task tree before creating one. Reuse accepted wave IDs and task-tree IDs; do not mint a duplicate plan because a ChatGPT conversation changed.
2. Recover actual live worker/dialogue/source-writer custody and uncertain effects where relevant. A plan or named owner is not proof of current authorization. A successor cannot take a live source writer, STARTed Job or `EFFECT_UNKNOWN` operation from a missing chat.
3. Frame the end-state: Chairman intent, persona and machine job, outcome, unique value/quality bar, constraints, dependencies, `DONE_WHEN`, required real-path proof and held non-goals. For product/design work include user journey, engineering rigor, performance, responsive/mobile, accessibility, independent review and quality falsifiers appropriate to scope. Prefer concrete testable outcomes over adjectives.
4. Decompose into enough ordered **phases, tasks and substeps** to direct independent bounded work. Record dependencies and exact handoff/input/output contracts. Unknown work can remain explicitly provisional; don't fabricate certainty. Avoid overplanning predictable mechanical details that a qualified worker should decide.
5. Persist the task tree in the project's **already owning GitHub repo** through an eligible authorized writer (branch/PR or existing incumbent carrier). The record must have a stable exact file path and revision/SHA; read back committed bytes. Where an organizational `WS:<KEY>` exists, add that repo-relative path to the workstream `artifacts` list through its lawful writer, and name the path in the latest dated handoff. Do not put a commit SHA in `artifacts`. Do not invent a workstream just to satisfy this step.
6. If GitHub or Agent OS write is genuinely unavailable, distinguish the scope of what is saved. A GitHub draft is durable source evidence but not accepted organizational state. Record `PLAN_NOT_ORG_LINKED` or `NOT_CANONICALLY_PERSISTED` as appropriate with the exact missing writer/receipt. Proceed only with independent safe work the gap does not gate; never describe a chat-only plan as saved.

## B. Master-plan record: compact header, arbitrarily deep tasks

Keep a human-readable Markdown master plan with stable identifiers and versioned changes. Use this minimum *content contract*, not a new runtime API schema:

- **Header:** exact workstream/operation refs when present; owning repo/path of this task tree; protected-procedure pin; Chairman objective and `DONE_WHEN`; the task tree's own git revision; recorded-at time. Plan acceptance is a workstream or decision fact, not a header flag named `accepted`.
- **Task hierarchy:** stable `P1`, `P1.T2`, `P1.T2.S3`-style IDs (or the incumbent equivalent), parent IDs, dependencies, objective, acceptance, source-bound inputs and outputs, risk/reversibility, intended execution lane, review gate and priority. A project may have many nodes; Executive runtime still admits only qualifying bounded slices. These IDs are not wave IDs and not Job IDs.
- **Task-tree status and evidence:** use only the editorial labels in the table below. Record exact PR/SHA/test/user-path proof where applicable. A ticked box is not acceptance.
- **Notes:** assumptions, constraints, hypotheses/falsifiers, and scoped change rationale that belong to this tree. Durable organizational decisions and discoveries go to Agent OS. Do not copy the conversation, wave status, `do_not_redo`, live children, or unresolved effects into this file.
- **Pointer, not a frontier:** cite the workstream key and the latest handoff path. The exact next action is workstream `next_action` and handoff `next_actions`. Live children and effects stay in `control_plane`.

Editorial labels are not a state machine and do not auto-advance. `blocked` may apply from any non-terminal label. Only the repo-plan writer sets them. Changing a label does not change a wave, a handoff, or a Job.

| Editorial label | Means on this task-tree node | Does not mean |
|---|---|---|
| `proposed` | Scoped in the tree; not yet eligible to offer as work | Workstream status `proposed`. Not admitted |
| `ready` | Dependencies and cited evidence for this node are satisfied, so a bounded slice may be *offered* to existing admission | Wave `todo` or `in_progress`. Not a Job. Not an Executive ready flag |
| `blocked` | This node waits on a named dependency or a named missing proof | Workstream `blocked` (that status requires `blocked_by`). Not a lease hold |
| `in_progress` | An owner is editing this node's source or evidence | Wave `in_progress`. Not Job `RUNNING`. Not a START receipt |
| `implementation_complete` | The node's implementation artifact exists and is cited | Not reviewed, not merged, not accepted, not Job `COMPLETED` |
| `reviewed` | A named reviewer recorded a verdict on the cited artifact | Not production acceptance and not a merge |
| `accepted` | The source or decision owner accepted this node's evidence into the plan | Not a protected merge, not user-path acceptance, not parent consumption of a Job |
| `superseded` | A named successor node replaces this one; do not execute it | Wave `dropped`. Do not copy this label onto the wave |

Wave status stays the Agent OS enum `todo`, `in_progress`, `awaiting_ci`, `done`, `dropped`. Workstream status stays `proposed`, `active`, `blocked`, `awaiting_ci`, `awaiting_review`, `done`, `parked`, `killed`. Handoff `ended_because` stays `complete`, `ci_handoff`, `blocked`, `context_budget`, `crashed`. Job and Attempt states stay in `control_plane`. The same English word in two columns is two facts.

Use linked GitHub Issues/Linear projection only when a selected human/project navigation object is useful under existing selection rules. Never generate one Issue per tiny substep or treat GitHub Issue status as Executive Job truth.

## C. Granular updates and plan revisions

**At meaningful milestones**, not per tool or clock tick: after accepted decisions, actual verified progress, important new evidence, delegated child boundaries, dependency changes, result/repair adjudication, and before risky/effectful operations or foreseeable session retirement:

1. Observe canonical owners first: evidence, current PR/source, runtime Job/Attempt, child dialogue, effect and source custody. Persist the relevant plan-node delta in the original authorized source carrier, preserving task IDs and accepted evidence.
2. Make revisions explicit: previous plan ref/SHA, new ref/SHA, changed task IDs, reason, downstream dependency impact, tasks preserved unchanged, any stopped/deferred future work, and tests/review that must be re-run. Use normal GitHub optimistic concurrency/source custody; do not overwrite other writers' or newer reviewed revisions.
3. Reconcile the pinned plan through the existing Agent OS writer. The cumulative checkpoint is the latest dated handoff `agentos/handoffs/<WS-KEY>-<YYYY-MM-DD>.md` that `compile-context` would select (date, then full stem). On the same calendar day, amend that file in place. A suffixed sibling is invisible to the compiler (`DSC:SUFFIXED-HANDOFF-IS-INVISIBLE`); do not mint one, and do not add a `latest` pointer file. Read back the committed handoff. A pending GitHub PR is not an Agent OS write receipt. The handoff must validate as `agentos.handoff.v1`: `model` is only `fable`, `opus`, `sonnet`, `haiku`, `codex`, `local`, or `sol` (Codex/Astra uses `codex` or `sol`; do not invent `grok`, `astra`, or `chatgpt`). If no admitted model value fits the seat, do not write an invalid handoff; report the gap and leave the prior checkpoint in place. `ended_because` is only the enum above; `unverified` is present (an empty list is valid); every `verified` item has a `command`; every `changed` item has `what`; the body does not say "see above" or "as discussed". Put the task-tree path in workstream `artifacts` as a repo-relative path (`mastermind:<path>` is allowed). A commit SHA is not an artifact path; put it in the handoff body or a verified claim. Update wave status and `next_action` only when the wave actually changed. Preserve the exact active child, current carrier, and release gate.
4. Reassess the original outcome and continue the next safe in-scope phase in the *same* healthy session. A save is not a stop. Do not duplicate or retarget STARTed children when a master plan changes; make any later change through the actual admission/continuation owners.

A runtime executable subset must be derived from the current wave and the task-tree node it cites, checked for dependencies, actual capacity/eligibility and budget, then admitted by Executive's existing validators. A task-tree label of `reviewed` or `ready` is not that admission. A GitHub edit cannot inherit new scope or modify already-running work.

## D. Failed ChatGPT session: deterministic recovery, not transcript reconstruction

A newly assigned eligible CEO receives at most a compact **continuation ref**, not a giant prior chat summary. It must:

1. Load one compatible protected procedure commit. Then recover in the handoff protocol's order, as separate records. A crashed session does not leave an orderly `ended_because: crashed` write; do not wait for one. A successor may use `crashed` only when it writes a real handoff after recovery.
   - The latest valid dated handoff is the durable checkpoint.
   - The workstream `next_action` and wave statuses are often newer, because they move at wave boundaries. If they disagree with the handoff, keep the disagreement visible. The bundle is testimony; the primary artifact wins.
   - Open the task tree at the workstream `artifacts` path. Resolve the commit that contains that path. Refuse a fuzzy identity (wrong workstream key, wrong repo, wrong path). Do not refuse a schema-valid handoff just because it has no master-plan SHA field.
2. Then read git status and log for the named worktree, and `active_builds` for PR state. Read the Executive Job/Attempt/worker/effect rows required for the next action. Refresh only material invalidators: new accepted decisions, source revisions, active returns, and ownership changes.
3. Verify which source and runtime effects are settled. Preserve current children, original dialogue carriers, live source writers, and `EFFECT_UNKNOWN` fences. An inaccessible predecessor chat and stale owner label alone never release an actual lease.
4. Report the verified current phase, accepted `DO_NOT_REDO` set, outstanding gates, one exact authorized next action and its `DONE_WHEN`. If the persisted plan is stale/contradictory, repair through its owner before trusting it.
5. Execute the next safe bounded action after current assignment/custody/admission checks. Do not reproduce closed investigation or replay the prior chat's private reasoning.
6. If the checkpoint writer is unavailable, emit the bounded `NOT_CANONICALLY_PERSISTED` frontier and hold only the dependent lane. Do not call an unverified GitHub draft or an assistant message a canonical save.

**Session succession is separate.** Automatic creation of a ChatGPT successor, semantic pickup and RuntimeBinding transfer require the production-proven existing Web-Sol context-rotation chain and exact effect fencing. This document does not implement that chain or authorize arbitrary browser control.

## E. Executive cockpit: smallest integration, no second control plane

Deliver this in phases through the existing Executive OS / Mastermind OS product owners:

1. **Read-first:** authenticated, exact-project view composing source-qualified Agent OS workstream/checkpoint + the referenced GitHub master-plan revision + Executive runtime Job/Attempt/child/admitted-plan views. Show freshness, partial coverage, contradictory sources and missing writers. No invented progress.
2. **Edit through owners:** `create_plan`, `add_task`, `add_substep`, `revise_task`, `attach_evidence`, `record_decision`, `checkpoint` and `resume_context` are **user-facing intents**, not new unguarded public Executive write verbs. Route them by fact, using expected revision, actor, source-bound target, effect reconciliation and exact readback:
   - Task-tree intents (`add_task`, `add_substep`, `revise_task`, and evidence that cites a task node) go only to the owning repo's master-plan writer.
   - `record_decision`, wave status, `next_action`, and `checkpoint` go only to existing Agent OS writers and must validate against `agentos.workstream.v1` / `agentos.handoff.v1`. `add_task` must not create an Agent OS task record.
   - Runtime actions use Executive's current Job/Attempt interfaces only. A task-tree edit does not admit, retarget, or complete a Job.
3. **Source-bound handoff:** from a task-tree node labeled `ready`, prepare one bounded execution packet with source revision, task IDs/dependencies, the outcome to accept, and real-path proof. Use existing admission/capacity/resource owners and original-root accounting; no new dispatch engine. The packet does not admit itself.
4. **Consumer proof:** a completely fresh Pro Project conversation with only the project kernel plus workstream, handoff, and task-tree refs reconstructs the same objective, marks five task-tree nodes with the editorial labels (for example `accepted`, `blocked`, and `in_progress`) without copying those labels onto waves or Jobs, refuses one injected stale or unknown effect, and advances one real eligible task without Chairman re-explaining the plan. Repeat with an admitted local Codex/Claude CEO surface before calling cross-harness parity proven.

## F. Acceptance and failure tests

- **Plan exists:** a new multi-phase project has one source-bound plan and verified initial readback before major delegation. Same initiation twice reuses the same project/plan identity, not a competing plan.
- **Deep hierarchy:** tasks and substeps retain stable IDs, dependency graph integrity and node-level evidence across revisions; no 8-step Runtime cap is falsely imposed on editorial master plans.
- **Concurrent editors:** stale expected revision refuses; active unrelated source writers and overlapping plans are not overwritten.
- **Lost chat:** fresh session recovers plan and precise next action from canonical owners without any predecessor transcript or Chairman transcription.
- **Interrupted write:** ambiguous save or branch operation is reconciled at its original target before retry; zero duplicate child Jobs or project-plan copies.
- **Plan shift:** accepted work survives a material revision; STARTed child remains bound to its original admitted contract until the existing owner lawfully changes it.
- **Missing owner:** unavailable Agent OS, GitHub, Runtime, source or Project UI is shown honestly as partial/degraded; no fallback memory or shadow job database appears.
- **Actual outcome:** substantive product/delivery acceptance comes from correct original consumers and real-path evidence, not a green CI badge or checked plan node.

**Implementation ownership:** use the existing `WS:EXECUTIVE-ECOSYSTEM-COMPLETION` waves for ecosystem delivery, and `WS:ORCHESTRATOR-PROJECT-CONTINUITY` waves for the already merged W0/W1/W2 harness records. This contract complements those pinned plans. It does not supersede the OS estate masterplan, source holds, or incumbent Fable/Astra integration or Project Workroom planning roles. This file alone proves only that the proposed instructions are versioned in GitHub.
