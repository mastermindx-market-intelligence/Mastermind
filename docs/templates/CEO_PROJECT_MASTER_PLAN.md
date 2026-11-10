# CEO Project Master Plan — TEMPLATE ONLY (not an active project)

> Copy into the **existing owning project's repository/source carrier** only after checking
> for an incumbent plan. Never write live status into this example or interpret placeholder
> IDs as issued Executive/Agent OS identities. Follow
> [CEO Project Plan and Crash-Continuity Contract](../CEO_PROJECT_PLAN_CONTINUITY.md).

## Identity and authority

| Field | Replace with project-specific value |
|---|---|
| Chairman objective | [one-sentence outcome] |
| Pinned plan | [existing `WS:<KEY>` and wave IDs; not this file] |
| Accountable CEO function | [real assigned responsibility, not an assumed lease] |
| Task tree and revision | [owning repo, exact path of this file, branch/PR, commit SHA] |
| Protected procedure pin | [repo / protected branch / compatible commit] |
| Latest handoff | [one `agentos/handoffs/<WS-KEY>-<YYYY-MM-DD>.md` path, or PENDING] |
| Cross-system Agent OS reference | [that workstream plus the handoff path; a missing plan SHA is normal] |
| Current approved scope | [precise in/out] |
| Required real-path acceptance | [what a real user and system must demonstrably achieve] |
| Created / last materially revised | [UTC timestamps from actual records] |

## North star, constraints and verification

**User's job:** [who must be able to do what]

**Machine's job:** [what intelligence/operation reliably produces]

**DONE_WHEN:** [observable capability and proof; not "PR merged" unless this is explicitly source-only]

**Product excellence:** [coherent workflow, accessibility, mobile/desktop, reliability, quality, performance and independent critique applicable to the deliverable]

**Reserved decisions / non-goals / security constraints:** [actual scope, authority and effect fences]

**Success metric and falsifier:** [quantitative/qualitative check and how to reject a deceptive green result]

## Work breakdown and dependency graph

Phases and tasks are the **task tree**, not Agent OS waves and not Executive Job/Attempt IDs.
Use the incumbent project's existing identifiers when available; these examples
are not globally reserved. Add as many hierarchical levels as needed.
The Editorial state column uses only the labels defined in the continuity contract.
It does not copy workstream status, wave status, or Job state.

| ID | Parent | Depends on | Outcome | Evidence / DONE_WHEN | Editorial state |
|---|---|---|---|---|---|
| P1 | — | — | Validate existing owners, user journey and mission | Canonical references and clear scope | proposed |
| P1.T1 | P1 | — | Recover original design, accepted plan and work | Verified source and incumbent-effect identities | proposed |
| P1.T2 | P1 | P1.T1 | Establish executable next phase and proof | Reviewed inputs, dependencies, acceptance tests | proposed |
| P1.T2.S1 | P1.T2 | P1.T1 | Implement one bounded independently testable slice | Exact source/test/evidence ref | proposed |
| P2 | — | P1 | Integrate and verify a real consumer | End-to-end user-path result and reviewer acceptance | proposed |

For each ready nontrivial task maintain a short detailed record:

### P1.T2.S1 — [title]

- **Objective / why now:** [deliverable and critical-path dependency]
- **Input/authority:** [exact pinned refs, current branch, allowed paths, decision owner]
- **Scope / exclusions:** [implementation surface and forbidden collateral]
- **Dependencies:** [IDs; blocked versus satisfied with proof]
- **Suggested lane:** [economical eligible operator/worker or principal judgment; not an actual runtime assignment]
- **Work:** [steps/substeps appropriate to the actual complexity]
- **DONE_WHEN / independent review:** [tests, product proof, failure case]
- **Risk, rollback and effects:** [reversibility, any pending effect and original carrier]
- **Evidence:** [PRs, commits, results, real-path URLs or exact proof absence]
- **State:** `proposed` / `ready` / `blocked` / `in_progress` / `implementation_complete` / `reviewed` / `accepted` / `superseded` (task-tree editorial label only; see the contract table)
- **Decision/notes:** [dated source-backed result, hypothesis or falsifier, not hidden reasoning]

## Accepted progress and outstanding gates

Record exact plan node, last committed source, evidence and proof level.
Never promote a GitHub PR, checked box, or Slack return into Runtime START
or user acceptance.

| Task ID | Last material result | Exact artifact/revision | Reviewer/consumer and actual disposition |
|---|---|---|---|
| [ID] | [observed change] | [immutable ref] | [actual owner / unknown] |

## Changes and supersession

| Plan revision | Changed task IDs | Decision/reason | Impact / dependencies | Unchanged task IDs |
|---|---|---|---|---|
| [commit SHA] | [stable IDs] | [source-backed rationale] | [impacted exact next tasks] | [IDs left as they were] |

`do_not_redo` stays on the workstream and the latest handoff. This column only lists task-tree IDs this revision did not change.

Current version changes do not silently revise a STARTed worker's admitted contract.

## Where the frontier lives (do not copy it into this file)

The pinned plan is the Agent OS workstream waves. The cumulative checkpoint is the
latest dated handoff, amended in place on the same day. Live Jobs and Attempts
live in Executive OS `control_plane`. This section is a read list, not a second
frontier and not a `latest` store.

- **Workstream and wave statuses:** [read `WS:<KEY>`; do not restate them as task labels]
- **Latest handoff path:** [the `<WS-KEY>-<YYYY-MM-DD>.md` file `compile-context` would select]
- **Task-tree revision:** [this file's path and commit SHA]
- **Next action:** [read workstream `next_action` and handoff `next_actions`; the workstream value is often newer]
- **DO_NOT_REDO, children, unresolved effects:** [read the handoff and `control_plane`; do not duplicate them here]

Do not put tokens, passwords, transcripts, full logs or personal secrets here.
