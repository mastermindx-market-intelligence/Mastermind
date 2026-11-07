# Project launch and autonomous-team integration

This is an implementation contract for the existing Mastermind OS programme,
not a replacement project plan, runtime controller, queue or release approval.

- Programme: WS:EXECUTIVE-ECOSYSTEM-COMPLETION.
- Original Codex root: `01a15741-5e68-7803-8eb4-ccac74a6c04b`.
- Owning direction/return: [PR #1621 comment](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1621#issuecomment-6670337891).
- Source inspected: #2102 publication `63b0523546a0adbde4c82464d09873c2fe642bef`.
- Procedure pin: `49c2e1d93e5e080b1671c98087a845e5beb09dd5`.
- Contribution operation: `mmos-project-execution-offer-20261105-sol-001`.
- Status: supporting source contribution. The new helpers are not mounted by
  this change. Tests of them are not proof of an installed project journey.

## Product outcome

A person starts a project by describing an outcome and optionally attaching a
handoff. The accountable CEO uses that material, asks only consequential
questions, records a durable plan, and works within the admitted project scope.
It can assign bounded work to COO coordinators, which can use the existing
Fabric for eligible descendants. Results return to the original parent, are
consumed and advance the plan. The person can correct direction, ask about
progress and reopen the project without creating duplicate work.

A launch authorizes the admitted scope and policy. Ordinary in-scope steps do
not require repeated human approval. Credentials, new authority, destructive
effects and actual release/security holds retain their existing controls.
A model becoming unavailable must produce the existing truthful routing or
capacity outcome, not a claim of unlimited capacity or an unverified retry.

The project's primary view should answer:

1. What outcome are we pursuing, and which baseline is adopted?
2. Which CEO owns it, and what has actually started?
3. What result is due next, from whom, and when was this state observed?
4. What decision or blocker requires the person?
5. Where can the person continue the same conversation or inspect the team?

Keep team depth, evidence, source details and advanced controls available
through progressive disclosure. An authored plan state is not a runtime state.

## Verified source gap

At the inspected publication, `project_planning_admission.py` chooses
`native_research_only` with `direct_native_readonly`. Planning proposals are
retained read-only outputs. The Fresh conversation prompt excludes child work,
and conversation-turn code does not establish parent consumption of child
execution. These are useful entry and planning pieces; they do not complete
the autonomous project loop. The current Fresh path is also restricted to its
qualified Codex/TX5 native profile; that specific entry path must not be
presented as a provider-neutral execution interface. Broader role/model support
belongs in the existing admission, Router and Fabric capability owners.

`executive-launch-command-port.ts` already creates an admitted launch request
from the existing workstream/profile/path/validation configuration.
`App.tsx` already has an Office-to-launch handoff with live owner checks.
The project plan/adoption view has no equivalent mounted handoff at this base.

The existing orchestration result owner already supports a bounded plan with
coordinators, delegation and dependencies. Extend that path; do not introduce
another team scheduler, provider router or task-state database.

Two deliveries must remain distinguishable:

| Delivery | Meaning |
| --- | --- |
| Open an ordinary launch for this project | The existing launcher receives the exact selected workstream and the person's goal. Existing admission still decides whether execution may start. |
| Execute an adopted plan/task selection | The admitted operation is privately bound to qualified plan/adoption bytes and explicit requested task references. The current public launch payload does not establish this binding. |

Adopting a baseline must not silently launch it. Conversely, an ordinary
project launch must not be labelled as execution of that adopted baseline.

## Source contribution

### `project-execution-context.ts`

`projectExecutionContext(value, selection)` reuses the existing strict
`decodeProjectPlan` boundary and returns an available context or unavailable.
Malformed/mismatched input retains the decoder's fail-closed error.

The detached context retains the exact work reference, title, objective,
record-source identity, adoption summary and adoption-decision source.
Legacy v1 has no continuity claim. Equality compares every retained semantic
field and source component, independent of object key ordering.

The projection deliberately contains no inferred task readiness, launch
permission, runtime job, auth generation or new cache. A matching context
does not prove that its source remains readable or current.

### `project-launch-handoff.ts`

`createProjectLaunchDraft` detaches and freezes the context and preserves the
person's exact goal. It does not substitute the objective, truncate content or
create an operation identifier.

`decideProjectLaunchHandoff` returns a pure opening decision using current
context and the existing launch owner's live state. It refuses a stale or
unavailable context, unavailable launch owner, workstream mismatch, held
original command or another unsent goal. Reopening the exact existing handoff
returns `reuseExisting: true`; the caller must preserve any edits already made
in the launch form.

`projectLaunchContextIsCurrent` is the shared source comparison for handoff
and submit-time rechecks. The caller supplies the existing acquisition fence;
a boolean here is not an authentication or permission boundary.

These functions prepare, submit and dispatch nothing. They cannot make the
project feature operational until the incumbent application owner mounts them.

## Mount into the existing application owner

The active #2102 app composer retains its source custody. Integrate this
contribution on that exact current head and reconcile its newer changes.

1. Extend `ProjectPlanPanel.renderWorkspace` with the same captured plan read
   and an acquisition-currentness function. Reuse the panel's reader identity,
   request selection, source generation, canRead and window/document binding
   checks. Its current adoption inspection depends on selecting a proposal;
   do not make project launch depend on a proposal being selected.
2. Show a normal project action such as **Start work** beside the current plan
   and conversation. Let the person describe the work. Capture the qualified
   context with the exact goal into a `ProjectLaunchDraft`.
3. Reuse the existing launch-handoff state with a discriminant for Office or
   project. Do not add another retained draft store, command owner or queue.
   Pass only that owner's existing project draft as `openedDraft`.
4. At handoff, re-read the actual host command binding, signed-in principal,
   owner generation and launch manifest. Resolve the exact selected workstream;
   no fallback to a default project, title match or department mapping.
5. Call the pure decision. On OPENED with `reuseExisting: false`, populate the
   existing launch goal/workstream and open its existing view. On reuse, focus
   that view without overwriting text. On refusal, preserve text and show the
   actionable existing state.
6. Immediately before existing command preparation, repeat the source fence
   and context comparison plus host/binding/principal/generation checks. Require
   form workstream, enrollment workstream and captured context to agree. The
   existing `launchIntentFromBinding` remains the payload owner.
7. After preparation/submission, preserve the original operation and recovery
   pointer. A later plan change must not cause replay or replacement of an
   operation with an unknown effect. Reconcile that original operation first.

The existing launcher owns input limits. Objectives can exceed its goal limit;
do not silently truncate them or announce that unsubmitted text is accepted.
Normal validation should keep the full draft visible for the person to edit.

## Bind execution to an adopted plan through existing backend owners

The stronger north star needs the following work in the incumbent admission
lane. It is not implemented by these frontend helpers.

- Add a private, host-issued semantic source for project execution, comparable
  to existing nominal-source wrappers. Qualify the selected workstream, exact
  plan record, adoption decision and adopted-source bytes under the real
  principal and source reader. References supplied by UI text are candidates,
  not authority.
- Carry that source through existing `executive_ceo_ingress` submission and
  `ceo_intent.submit_intent` into the admitted orchestration root. Keep the
  closed public `CEO_REQUEST_V1` contract unchanged unless its owning protocol
  is intentionally versioned in a separately reviewed change.
- Retain the exact material through `TerminalOriginalInputArtifacts` and the
  existing prepared-command fingerprint. Bind explicit task references and
  policy scope there. Do not create a second artifact store, expose private
  handoff material in public receipts or encode provenance into the goal.
- Reject mismatched source before effect. Once an original operation exists,
  unknown-effect recovery uses its retained original input, rather than
  re-reading a newer plan and issuing a replacement job.
- Runtime admission validates requested task references, dependencies, permitted
  effects and descendant budgets. Markdown statuses and this UI's context
  projection cannot establish readiness.
- Extend the existing orchestration plan/result owners for CEO-to-COO-to-worker
  execution. Preserve original root/parent lineage, writer targets, budgets,
  admission and return/consumption links at every level. The existing bounded
  step limit requires durable continuation across chunks, not larger unbounded
  prompts or a second scheduler.
- Advance durable project progress only after the accountable parent consumes
  a qualifying result. A worker finishing, a message arriving or a PR merging
  alone must not mark the project accepted.
- Route clarification and corrections back to the same responsible CEO.
  Distinguish a new conversation from a new execution root. Preserve in-flight
  instructions and original effects when the person changes direction.

## Acceptance in the existing programme tree

Keep the programme's current AC1–AC10 and H1–H8 obligations. Add these concrete
checks to their relevant existing nodes, not to a parallel completion ledger.

| Check | Required proof |
| --- | --- |
| Real entry | Installed app starts a project and fresh conversation with actual authenticated source reads; drafts survive unavailable execution. |
| Ordinary launch handoff | Exact project/goal reach the existing launcher; occupied drafts and held commands are preserved. |
| Plan-bound launch | Exact adopted baseline and requested tasks are retained in the admitted original input; stale/tampered inputs fail before effect. |
| Autonomous hierarchy | One CEO, at least one COO and eligible Fabric descendants actually start under conserved root and budgets. Provider/capacity evidence is observable. |
| Result loop | A useful child result returns, the original parent consumes it, and the app shows truthful next work. |
| Correction and repair | Change intent in flight; handle a failed child; continue or escalate without replaying the original effect. |
| Recovery | Lose a submit response, close/reopen the app and recover exactly one original job and its retained context. |
| Product depth | Keyboard/focus/touch, light/dark, EN/ZH, narrow/wide layouts and loading/empty/stale/error/permission/success states work with the advanced team view. |

For this source contribution, focused fixture tests establish projection and
handoff behavior only. Mounted App tests must additionally observe that stale
context causes zero prepare/submit calls. Native/browser evidence must then
prove the actual journey and accessibility. Neither unit tests nor source merge
substitutes for that proof.

## Paper direction and present constraints

Use the established project overview, Meta-CEO, conversation and Work designs:
AT03 `MHD-0/N29-0`, AT08 `L9V-0/MNS-0`, CH1/CH6
`IZB-0/K5X-0`, AT10 `LF7-0/MOG-0` and UX13 `TDM-0` in
file `01M3NRCX55B452A12819WNE1RH`, subject to a fresh authorized inspection.
These IDs come from the source crosswalk; this contribution does not claim a
fresh visual read or acceptance of those boards.

The same-session live Paper inspect/catalog refused bridge identity with
retry disabled. No alternate Paper carrier was used. Exported design
specifications informed this contract; live editable-canvas and screenshot
verification remain with the authorized design lane.

The native route failure and original 09b protected-result hold remain owned by
the incumbent Runtime/root. This contribution does not retry either effect,
change credentials, restart services, arm a runtime or publish a release.

## Parent verification — 5 November 2026

The parent applied the two returned projection files unchanged and reviewed
all five contribution files. Integration guard review is SELF_REVIEWED; no
independent-review or mounted-product acceptance is asserted.

| Command / receipt | Observed result |
| --- | --- |
| `npm test -- --reporter=dot src/planning/project-execution-context.test.ts src/planning/project-launch-handoff.test.ts` | 2 files, 39 tests passed; exit 0. Studio process 84481. |
| `npm run typecheck` (`tsc -b --pretty false`) | Exit 0, no diagnostics. Studio process 84329. |
| Fabric run `mmos-project-execution-offer-20261105-c1-01` | Terminal return, rc 0, original root verified. |
| Exact complete Fabric adapter response | SHA-256 `3533398fba47d470082c1df2136a4024b69e1d8b933f14f261e959e072280f14`. |
| Original Fabric acceptance | `accepted: true`, `accepted_by: deterministic`, basis `deterministic_test_evidence`. This records bounded source acceptance only. |

The 39 tests comprise 21 projection tests and 18 handoff-guard tests. They cover
legacy/v2/unavailable reads, malformed or mismatched input, detached provenance,
source/adoption changes, key-order independence, exact user text, stale
acquisition fences, exact workstream selection, occupied drafts, held commands
and idempotent reopening. The parent did not repeat or rely on the worker's
broader-suite claims. App mounting, native command routing, actual autonomous
execution and browser/accessibility proof remain open in the existing programme.
