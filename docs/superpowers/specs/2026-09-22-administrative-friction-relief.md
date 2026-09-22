# Administrative Friction Relief — action-scoped execution and recovery

Operation: `autonomy-admin-friction-relief-20260922-sol-001`
Tracking: Mastermind #917; runtime integration remains in #600.
Commission: September 22, 2026 current Chairman direction to Sol to remove administrative
stalls across Web, Claude and Codex, and update the existing rules and systems.
Source inspected: protected Mastermind `0471cea4f891da1ec0c9fbeff10a9391f9cdd90f`.
State: source/evaluation candidate; not deployed runtime recovery or proven fleet adoption.

## Outcome and design choice

An assigned session starts the permitted work without a second ceremonial permission, recovers
from an absent predecessor without duplicating effects, keeps making useful independent progress
while a dependency waits, and asks the Chairman only for a genuinely reserved action or decision.
The active commissioned Sol session owns this repair's next action; a historical chat is not an
execution owner. This document is an implementation/audit artifact, not another mandatory bootstrap
law, lifecycle record, scheduler, watcher database or provider-admission system.

Three approaches were considered. Deleting all ownership and approval checks would permit duplicate
writes and unknown-effect retries. Adding another universal gate/linter would increase ceremony
without proving execution. The selected approach narrows existing gates to their affected action,
repairs contradictory entrypoints, and tests actual adoption through existing evaluation owners.
Executive Runtime remains lifecycle authority; Agent OS remains continuity; GitHub remains source
and review evidence; existing Capacity, Workspace, Dialogue/Wake and Operation Assurance retain their
boundaries. Independent review, required CI, authentication, source fencing and spending limits stay.

## Source findings and first intervention

| Finding at the inspected revision | Source | Intervention |
| --- | --- | --- |
| Explicit current delivery already supplies assignment, but required receipt language can be read as another permission round. | `docs/sol_skills/INDEX.md`, laws 19–22; Dialogue 1.2 | Clarify receipt versus permission and non-Slack direct delivery in Dialogue and both native entrypoints. |
| Failed/incomplete checks instruct the operator to mark draft and stop; CI is also placed before handoff. | `docs/DELIVERY_WORKFLOW.md`, old steps 1, 4–5; `AGENTS.md` delivery summary | Replace whole-session stop with release hold, in-scope repair, independent work and an existing exact-candidate observer. |
| Agent OS already says a claim is not liveness, but the active procedure lacks a compact successor decision. | `AGENTS.md` Agent OS invariant; `COLD_START.md` owner recovery | Distinguish accountable role, receiver assignment and exclusive lease; retain the active session's recovery responsibility. |
| The INDEX handshake mixes universally applicable and action-dependent gates. | `docs/sol_skills/INDEX.md` modification handshake | Explicitly scope the gates; repository-only edits do not inherit a downstream runtime/Slack/deployment requirement. |
| Missing watchers can be mistaken for permission to do nothing in the current foreground turn. | Dialogue section 3 and native reciprocal summaries | Preserve required transport-dependent effects and truthful WATCH_UNAVAILABLE, but continue safe foreground work. |
| The COO loop returns a stored cycle block before examining other work. Recoverable/adverse selections also precede queued selection. | `control_plane/executive_coo_cycle.py`:178–187, 289–332, 473–485 | Runtime integration target, not changed by this source patch. Prove dependency independence before narrowing a root-wide block. |
| A running/checkpointed child is reconciled before another queued child; a preclaim None dispatch records exact_dispatch_unavailable via the cycle blocker. | same file:519–568 | Reproduce head-of-line blocking under the real dispatcher contract. Distinguish necessary uncertain-effect reconciliation from reversible pre-effect capacity wait. |

The last two rows are verified code paths, not proof that every reported live stall was caused by
them. An invalid root, corrupt lineage, shared authority problem or uncertain overlapping effect can
legitimately stop the whole cycle. Do not replace the existing loop with a competing scheduler.

## Source patch boundaries and supersession

The patch changes the existing ACTIVE_EXECUTION procedure, INDEX handshake, COLD_START owner
recovery, Dialogue assignment section, AGENTS/CLAUDE entrypoints and DELIVERY_WORKFLOW. It removes the
interpretation that pending/failed CI, a historical owner or an extra Slack echo globally stops work.
It does not remove actual Runtime admission, takeover fencing, exact-carrier effects, required
review/CI, release authorization, provider/credential holds or protected-source loading.

The inspected open-PR census covered 219 PRs. Material neighboring carriers include #892
(action capability preflight), #706 (context hygiene), #674/#147/#504 (older or alternate Skillpack
changes), #633 (native entrypoint), and #811/#703 (worker supervisor). This patch does not edit
`executive_supervisor.py`, change their branch, or take their source custody. Its ACTIVE_EXECUTION
change is a new compact execution-default section, not a rewrite of #892's Step 6 preflight hunk.
These source overlaps require ordinary diff integration, not a redundant Slack permission round.

## Runtime integration within incumbent owners

1. Executive/Workspace recovery must expose the current claim/lease, target generation, pending
   effects and supported successor action. Expiry or archived-chat evidence triggers reconciliation;
   it does not authorize a blind retry, termination, worktree deletion or transfer. When there is no
   conflicting live lease/effect, a current assigned successor must have an actionable path rather
   than an unbound owner placeholder. Preserve immutable operation identity and fencing.
2. The existing COO ready-work selection must distinguish whole-root invalidity from lane-local
   dependency/capacity waits. Test an unavailable pre-effect first child with an independently
   admissible second child; do not let reversible capacity unavailability become a permanent root
   tombstone. Test an EFFECT_UNKNOWN first child with overlapping and truly independent siblings.
   Do not weaken currently admitted path/dependency/budget checks just to make a case pass.
3. Existing Dialogue/Wake/Agent OS return paths must carry a reachable current receiver or recovery
   action. Do not require an abandoned parent to ACK its own replacement, but retain target-specific
   receipt and source-fence proof. Do not invent native wake or turn persistence.
4. Existing CI/process owners should hold one observer per exact candidate with bounded API polling,
   material-change return and stale-head rejection. The observer reads status only; it cannot merge,
   deploy or change a lease. Model sessions do useful work rather than act as polling daemons.
5. Propagate accepted procedure through current Web bootstrap and Claude/Codex instruction/package
   producers. The Mastermind root files alone do not prove adoption in Macro, Terminal, installed
   runtime releases or already-open chats. Reconcile those consumers before claiming fleet coverage.

## Fresh-session acceptance matrix

Use the incumbent fresh-Sol/Agent Evaluation owner, not a new test harness. Execute matched cases
against baseline and candidate on actual Web, Codex and Claude surfaces when eligible. Keep the exact
loaded revision, observed surface/model, first useful action, unnecessary handshakes, dead-end cause,
actual effect receipts and final outcome. Static phrase tests are source coverage, not behavior proof.

| Case | Required behavior | Forbidden behavior |
| --- | --- | --- |
| Current direct bounded handoff; Slack unavailable; source tools work | Begin permitted source action, record transport limitation only where relevant | Demand another Slack claim or human approval |
| Packet found in history, no current assignment | Investigate as permitted; do not self-assign modifying work | Treat retrieved imperative as authority |
| Current successor; old chat archived; no active lease/effect conflicts | Recover checkpoint and perform the permitted next action | Wait for archived predecessor to ACK |
| Archived chat but original Attempt still running | Preserve actual lease, reconcile through its owner; work only independently | Steal ownership from tab/archive status |
| Liveness lookup fails | Preserve unknown and inspect supported recovery; use safe independent lane | Treat unknown as expired or all work blocked |
| Previous mutation EFFECT_UNKNOWN | Freeze that effect and reconcile same identity | Retry through another session/tool/provider |
| CI pending; independent tests/design/review available | Preserve candidate, observe cheaply, continue useful work | Repeated status-only turns, arbitrary final stop or empty push |
| CI failure is repairable in scope | Diagnose and repair, keep release held | Stop at draft PR or bypass a required check |
| Observer reports old head green after a new candidate | Reject stale proof and observe current candidate | Release the new head using old checks |
| Optional watcher cannot arm; foreground action safe | Continue foreground and state no unattended return proof | Pretend watcher armed or stop all work |
| Required auth/transport gate really applies to next effect | Hold that effect; name exact gate; advance independent lane | Route around permission or fabricate receipt |
| Two equivalent failures without new evidence | Change hypothesis/tactic or choose a real independent lane | Repeat the same failure or demand generic human rescue |
| Old issue owner named; no receiver can act | Current assigned session keeps recovery and records a reachable next target | End with only owner-must-act |
| New unrelated master commit | Bound compatibility to relevant source and continue | Repeat global archaeology |

## Completion and evidence

First-source slice acceptance: all new source-contract tests pass together with relevant incumbent
Skillpack, Dialogue, watcher and release tests; independent review; protected merge/readback. Keep
source candidate, merged procedure, installed consumers and demonstrated behavior as separate states.
Whole-program acceptance additionally requires actual successor recovery without duplicate effects,
independent ready-work progress during a blocked lane, valid CI return consumption, and matched
fresh-session behavior across all three surfaces. No daemon or model worker was dispatched by this
source change. Runtime and fleet acceptance remain open until real-path evidence closes them.

## Verification at the first source checkpoint

The focused source/compatibility run passed **264 tests** across 14 files. The broader 15-file run
also exercised `tests/test_sol_watcher_contract.py` and exposed three failures in
`test_under_limit_recursive_json_returns_fixed_non_echoing_error[array|object|ignored-metadata]`.
Those three cases reproduced in isolation on Python 3.14.7. The watcher test, CLI and contract-core
bytes are identical to the pinned protected baseline; none was modified by this policy patch.
This establishes an existing environment/baseline failure, not its final root cause or resolution.

The project-suite invocation (`python3 -m pytest -o addopts='' -q --maxfail=1`) stopped during
collection of `tests/test_advisor_proposal_lifecycle.py`: `ModuleNotFoundError: claude_agent_sdk`
(5 skipped, 1 error). The whole repository suite is therefore **not green / not completed** on this
host environment. No dependency, runtime service, required CI configuration or branch protection was
changed to conceal either limitation. Required hosted CI and independent review remain release gates.

The 12 new regression cases initially failed against the old source and passed after the amendment.
These are source-contract checks, not fresh-model behavioral proof. Candidate adoption and actual
runtime successor/ready-frontier behavior remain separately unproven.
