# GitHub and VPS delivery workflow

`origin/master` is the only release source. The VPS remains the canonical writer
for live paper-portfolio state; GitHub owns code, configuration, tests, and
reviewable documentation.

## Start every session with an isolated source owner

The protected `master` commit pins **governing procedure and release identity**, not
the machine or directory in which a proposed change must be authored. Authorized
sessions may use either of the following pre-effect authoring paths. Choose one
supported path for the original operation; a refused or uncertain effect is never
permission to replay it using the other path.

### GitHub-native authoring (no host worktree required)

An attended Web session with an actually authorized GitHub connector/API can create
and update an isolated GitHub branch and open a PR **without** `mmx-workspace`,
Studio Direct, a local checkout, an external SSD, an Executive Job, or a second
publisher chat. These host-local requirements do not apply to a GitHub-native
mutation. This is a source-authoring route, **not** a protected-merge bypass.

1. Verify the exact repository, current protected `master` commit and compatible
   procedure. Recover the original branch/PR and any active writer, denial or
   uncertain effect. Continue an existing operation on its **same branch/carrier**;
   for a genuinely new, unstarted operation create a unique branch from an exact
   protected commit. Do not duplicate an active or held PR to escape its gates.
2. Verify actual GitHub write permission. Make narrowly scoped changes on that
   branch through the authorized native file/tree/commit/ref APIs. Bind updates to
   the current file blob SHA and/or an expected branch-head SHA (compare-and-swap);
   inspect changed head/preimages on a conflict. Never force-update a shared ref,
   write directly to `master`, select arbitrary credentials, or overwrite a
   concurrent writer. An ambiguous mutation response requires original-branch
   readback before another effect; an explicit safety/permission denial is final
   for that effect, not a reason to switch to Studio/local publishing.
3. Inspect the resulting exact-head diff and path set, run available affected
   validation, and truthfully distinguish local tests from GitHub-hosted checks.
   Without a local runner, use hosted PR CI and do not claim unexecuted local
   tests. Keep incomplete/failing work Draft; make qualified, reviewable work
   Ready and use the same protected review/CI/merge-queue procedure below. GitHub
   native authoring does not waive any actual release hold or formal approval.

### Host-local worktree authoring

From any clean administrative checkout, harness-provisioned sessions use the exact workspace already assigned by their harness. When actually editing or publishing through a host-local checkout, attended ChatGPT Web/host sessions use the installed canonical source-custody launcher instead of raw clone/worktree commands or the repository Python payload:

```bash
git fetch origin --prune
base_sha="$(git rev-parse origin/master)"
mmx-workspace acquire \
  --operation-id <stable-operation-id> \
  --base-sha "$base_sha" \
  --lane web
```

The accepted release installs `mmx-workspace` with `scripts/install_mastermind_workspace_cli.sh`. The launcher, not the model/session, pins the canonical source checkout and host workspace root. On the Studio it also refuses execution when `/Volumes/Mastermind` is not the actual mounted workspace volume. `scripts/mastermind_workspace.py` is the versioned implementation payload and test/admin seam; it is not the production Web invocation.

The JSON receipt supplies the exact `workspace_path`, derived branch, base SHA, and shared Git common directory. Repeating `acquire` for the same operation reuses that workspace. Never point two independent operations at one workspace or mint proof/review worktrees outside this owner. Before editing, `cd` to the receipt path and confirm the intended branch, source revision and common ancestor:

```bash
git status --short --branch
git rev-parse HEAD
git merge-base HEAD origin/master
```

If protected `master` moved since acquisition, **do not block ordinary edits solely because the worktree is behind**. Compare current governing instructions, owned paths and imported dependencies. Only a material overlap or changed source law requires a bounded integration/review decision; no ancestry-only join, rebase or duplicate worker is required for path-disjoint movement. The native merge queue provides exact integrated checks before a protected merge.

If a session opens in the legacy shared checkout and it is dirty, do not clean,
stash, reset, or overwrite it. Treat those changes as user-owned. Create a fresh
worktree and move only the task's deliberate edits there.

## Complete a change

**Default is one-pass delivery, not a ceremony.** The assigned session implements,
self-checks the diff, runs available affected tests, opens one Ready PR, requests
native protected auto-merge once and consumes the resulting merge receipt. Do not
serialize extra review/approval/handoff rounds, repeated status sweeps, checkpoint
comments per command or an external publisher just to finish ordinary work.
Pending CI is an automated release dependency, not a new human assignment.

**Fast queue policy:** verified inert changes get source checks, ordinary code gets
focused executable tests, and privileged/financial/security/CI or unqualified
changes get full canonical CI. The protected `test` check stays mandatory, and
protected-main pushes still run the full suite. Real-world browser/installed proof
is required when a change affects that surface, not for inert docs. Preserve
actual protected rules, explicit HOLDs, live writers, denied or uncertain effects;
these are exceptional barriers, not default workflow steps.

### One qualification, normal protected release

Ordinary reversible FAST/STANDARD changes use the same session: implement, self-check
the coherent diff, run affected checks, publish and use the existing protected release
automation. No independent technical review, formal approval, separate release operator,
new task form or handoff is required by internal habit. Small changes should finish in
one healthy turn when checks and tools permit. Required hosted checks still gate merge.

Consequential native/automated changes mean the CRITICAL row in REVIEW_RISK_POLICY.md:
auth/security/permissions, source authority, review/release automation, privileged CI, financial execution, irreversible data and exactly-once. They receive **one** distinct native/Fabric technical review of the relevant risk. Repair findings and review only the affected delta. The existing attended
CEO-Web all-tier self-review waiver remains: a CRITICAL label alone adds no reviewer
handoff there. Stronger consequences still need stronger tests and real-path evidence.
An explicit current assignment or actually enforced repository/security requirement can
require review; identify that requirement rather than inventing a universal gate.

A technical review is not a formal GitHub approval. Obtain an authenticated non-author
`APPROVED` only when an actual repository rule or specific binding hold requires it.
Never impersonate a reviewer, self-approve, bypass enforced checks or clear a recorded
hold by inference. The assigned session may request ordinary automated release of its
own qualified PR; using the normal protected controller/queue is not an independent
review claim. No additional non-author arming ceremony follows a completed qualification.
The optional automatic review host remains OFF until separately enabled; its absence
adds no manual review. See [session review policy](SESSION_LOCAL_REVIEW_POLICY.md).

1. Run the smallest relevant **available** local tests when a runner exists.
   Publish an honest candidate when scoped source and available qualification
   are stable. GitHub-native authors without a local test runner may publish a
   reviewable PR for hosted CI: no local worktree or unexecutable local test is
   itself a source-publishing hold. Never claim tests that did not run.
   When an enforced GitHub rule or explicit authorized request requires review,
   mark a qualified Draft PR **Ready for Review before asking the reviewer**.
   No risk tier dispatches a reviewer solely for an obsolete universal-review
   rule. Pending hosted CI is a merge/release gate, not a prerequisite for PR
   publication or review readiness. Keep incomplete or actually failing work in
   Draft; do not imply review merely because a request exists.
2. On a local checkout, review `git diff --check`, `git status` and the
   staged diff. On a GitHub-native branch, inspect exact-head changed-file
   enumeration, complete diff and file preimages using available GitHub reads.
   Never publish `.env*`, credentials, logs, caches, runtime `data/`, or
   backup archives.
3. Publish the scoped change on the operation's isolated branch and open a PR.
   For a host-local worktree:

   ```bash
   git push -u origin HEAD
   gh pr create --fill
   ```

   For GitHub-native authoring, use the authorized branch/file/commit and PR
   tools with their expected preimages/head leases, then read back the branch
   SHA, exact PR head and diff. No local `git push` or launcher receipt is
   required for that path. Neither authoring path may directly merge a
   protected branch.

4. CI blocks merge/release, not independent useful work. Incomplete scope, failed
   local qualification, or a known failing hosted check keeps release held; diagnose the failure and repair it within the assigned scope. A **pending** hosted check alone is not a reason
   to keep an otherwise qualified, reviewable PR in Draft. The incumbent
   `control_plane/github_review_intent.py` explicitly refuses `review_requested`
   events while Draft (`PULL_REQUEST_DRAFT`); leaving a PR Draft while waiting for
   that same review creates a liveness deadlock. Mark the stable candidate Ready
   before initiating the eligible GitHub review-request path. Do not infer that
   a prior draft-time request will automatically be re-admitted when the PR
   becomes Ready. Continue path-disjoint tests, integration and repair while CI
   and any actually required non-author reviewer advance; never duplicate a refused Fabric
   review or move an unreconciled worker effect to another carrier.
5. Reuse one existing observer when it reduces a genuinely long wait; a short check
   may be consumed in this same healthy foreground session. Do not create an observer
   or a second operator just to complete a routine change. Bind repository, PR, exact head SHA and workflow run IDs; retain the
   process/run handle and return location in the existing checkpoint. Reuse an observer rather
   than creating one per check or chat. No merge/deploy action belongs in the observer.
   Consume only the matching candidate's results; a changed head invalidates stale observations.
   Queued CI is not a failing build; do not push empty/rebase-only commits to restart CI.
   A substantive qualified update may use normal configured CI supersession; retain
   the old run disposition and qualify the new exact head. Never manually cancel
   another writer’s checks or replay an uncertain side effect.
   Without a usable observer, continue useful foreground work and check once at the next real
   integration boundary. Never claim a background Web turn or automatic wake that does not exist.
6. **Enroll a qualified Ready PR in native Merge when ready without waiting for pending CI.**
   The assigned session owns this routine release request; do not introduce a second
   non-author arming ceremony. Immediately before acting, re-read the exact GitHub
   repository (`mastermindx-market-intelligence/Mastermind`), PR number, protected
   `master` base, full current 40-hex head SHA, Draft/Ready state, source-writer
   and effect custody, actual native/CODEOWNERS reviews, conflicts, explicit
   HOLD/STOP/security restrictions, and current trusted required-check conclusions.
   A source-complete, review-qualified candidate may be **armed while required
   hosted CI is pending**; a Draft, incomplete source, known failing check,
   conflict, missing/ambiguous enforcement evidence or binding hold must not be
   armed. Do not use `--admin`, REST direct merge, an ancestry-only rebase or an
   invented approval. Required CI remains a condition for the **merge**, not for
   a qualified pending-CI auto-merge request.

   Before the single request, inspect GitHub's native `autoMergeRequest` **and**
   `mergeQueueEntry` (or a verified exact queue ref). REST `auto_merge=null`
   alone does not prove a PR is unqueued. If it is already armed or queued,
   preserve that existing effect rather than submitting another. Otherwise run
   this head-leased request against the exact qualified candidate:

   ```bash
   gh pr merge <PR> --repo mastermindx-market-intelligence/Mastermind \
     --auto --squash \
     --match-head-commit <CURRENT_40_HEX_HEAD>
   ```

   Branch cleanup remains queue/repository-owned after merge; the native CLI
   does not support `--delete-branch` during queue enrollment.

   GitHub CLI refuses `--delete-branch` when merge queue is enabled. Do not add
   that flag to the auto-merge request: branch cleanup is an optional separate
   post-merge step, never a prerequisite for merge-queue admission. Read the
   actual merged PR/SHA first; preserve occupied or still-live source branches.

   Reconcile the actual returned request: pending conditions may create an
   auto-merge request; satisfied conditions may enter the existing protected
   merge queue immediately. An ambiguous reply requires reading the **same**
   PR/queue before any new effect. A changed head requires fresh source, hold,
   review and CI qualification; never blindly re-arm it. Only GitHub's enforced
   PR-head checks and native `merge_group` integrated candidate checks can
   permit the eventual protected SQUASH merge. Do not treat QUEUED, armed,
   green PR checks or a successful CLI return as a merged SHA. Read the actual
   merged PR and commit before claiming release or deploying.

   For integration proof, do not add a manual synthetic PR merge-ref check
   requirement; GitHub's native merge queue runs integrated checks after entry
   and before the actual merge. If final integrated checks fail, the queue must
   not merge. Protected integration requires that required PR-head checks and
   all **actually required** reviews pass and queue entry is authorized.

   When the queue removes a PR for failed checks, read that failed
   `merge_group` job before any new queue entry (its run is on branch
   `gh-readonly-queue/master/pr-<number>-*`; `gh run view <run> --log-failed`).
   A deterministic test failure on an unchanged head fails again, and every
   group built behind it is rebuilt and rerun: #506 re-entered unchanged and
   was removed twice, after 65 and 41 minutes in the queue. Re-enter only after
   a head change that addresses the failure, or once when the failed job shows
   an infrastructure cause (runner, dependency install, network, or a timeout
   not caused by the change) rather than a test assertion.

7. Deploy only when the assigned change requires runtime rollout and release is authorized.
   A source-only, research, documentation or instruction task must not restart an unrelated
   application. For a required deployment, resolve this operation's actual merge commit from
   GitHub using the accepted `pr_number`; the newest default-branch commit may belong
   to another operation:

   ```bash
   merge_sha="$(gh pr view "${pr_number:?set the accepted PR number}" \
     --repo mastermindx-market-intelligence/Mastermind \
     --json mergeCommit --jq '.mergeCommit.oid')" &&
     [[ "$merge_sha" =~ ^[0-9a-f]{40}$ ]] &&
     ./scripts/deploy_from_git.sh "$merge_sha"
   ```

   Missing, malformed or unreadable merge evidence blocks deployment. The unchanged
   wrapper fetches and refuses a receipt that is no longer current `origin/master`.
   Reconcile the new release identity and its authorization; never substitute the
   moving branch tip for this PR's receipt. Merge acceptance does not itself
   authorize deployment.

The deploy wrapper archives `origin/master` into a temporary clean release
directory. Local uncommitted files cannot enter the release. The VPS deploy
creates a rolling snapshot, restarts `mastermind.service`, checks
`http://127.0.0.1:8001/health`, and rolls back on failure.

## Macro release: `merge-on-green` is opt-in, not native auto-merge

This is a **cross-repository exception** for
`mastermindx-market-intelligence/macro` targeting `main`; it does not change
Mastermind's protected `master` merge-queue procedure above or install a new
merge service. Macro's incumbent controller is
`macro/.github/workflows/merge-on-green.yml` +
`macro/scripts/merge_on_green.py`. Its `merge-on-green` PR label is an
**explicit release opt-in** consumed by that controller, not a general-purpose
status, review approval, merge command, or license to override a hold.

**Never use GitHub's native `gh pr merge --auto` or `enable_auto_merge` as the
Macro fallback.** Macro's current source documents that without required status
checks this may merge before CI concludes. Repository-wide
`allow_auto_merge=true` does **not** mean that native auto-merge supplies
Macro's source/check freshness contract.

Before a session adds the label to any PR — particularly a PR it did not
create — perform the following **on the exact current PR/head**, using live
GitHub state, not a pasted handoff:

1. Check the **repository and base** (`macro/main` only), PR state (OPEN,
   not Draft), exact head SHA, source custody, latest main, merge compatibility,
   all binding PR-head checks (`ci-gate`, scheduled `ci-pack-*`, fences and
   other actual owner-specific checks), and any pending/red evidence. Macro's
   `can_arm_merge_on_green` is the source-level clean-check predicate; an
   absent or incomplete check is not green.
2. Read **title, body and issue comments** for explicit `HOLD`,
   `HOLD-FOR-SOL`, `STOP`, `do not merge` or release restrictions. Follow
   `macro/agentos/decisions/DEC-SOL-HOLD-IS-A-MERGE-BARRIER.md` and
   `DEC-MERGE-AUTOMATION-MUST-ENFORCE-RECORDED-HOLDS.md`.
   A held PR must stay Draft, disarmed and without native auto-merge; its
   particular holding authority must release it. Where the controller's
   `HOLD-RELEASED` protocol applies, the qualifying release must be newer
   than all binding hold comments. **A label or CI-green state never releases
   a recorded hold.** Do not blanket-label, re-home or silently un-draft.
3. Apply only the review actually required for this candidate under the shared policy
   above and current enforced rules. Ordinary reversible changes need no internal
   independent reviewer or formal approval. Consequential native/automated changes need
   one genuine independent technical review; Fabric or a distinct native child qualifies.
   A technical `SOURCE_PASS` is not GitHub `APPROVED`, and an approval is needed only
   where enforced or specifically held. Preserve blocking findings, review revocation
   and original review effects. Do not switch logins to manufacture independence.
   **Cross-repository command boundary:** every CLI command below must bind
   `--repo mastermindx-market-intelligence/macro`; never infer the target repository.
4. Once the required checks, applicable review and holds are satisfied, the assigned
   session may opt its own qualified PR into the existing automation:
   `gh pr edit <number> --repo mastermindx-market-intelligence/macro --add-label merge-on-green`
   (or the additive GitHub issue-label action). No second non-author release/arming
   actor is an internal prerequisite. Preserve exact repo/PR/head and useful existing
   evidence; no new release receipt stage. Do not substitute `main-red-repair` or touch
   `merge-refresh-in-flight` (controller-owned lease state).
5. Reconcile the **existing controller** and PR after arming:
   `gh run list --repo mastermindx-market-intelligence/macro --workflow merge-on-green.yml --limit 10`,
   `gh run view <run-id> --repo mastermindx-market-intelligence/macro --log`, and
   `gh pr view <number> --repo mastermindx-market-intelligence/macro --json state,isDraft,labels,headRefOid,mergeStateStatus,reviewDecision,autoMergeRequest`.
   Read a **full sweep**, not only a successful *failure-marker pass*.
   The controller can end SUCCESS without merging anything. A green head may
   be **stale** after `main` changes CI definitions; branch refresh can be
   deferred when its global CI workload cap is exhausted; conflicts, hold
   guards, missing semantic proof and inherited reds are separate blockers.
   Keep the original label/carrier and diagnose the actual verdict. Never
   spam workflows, push empty commits, cancel another lane's CI, or raise the
   workload cap merely to force progress.

### Qualify once, release automatically

The existing controller is responsible for machine enforcement. Do not treat source
policy as proof that a changed controller is installed. Until a prospective controller
change is installed and read back, preserve its actual enforced behavior and diagnose
its concrete verdict; do not bypass it or add an imaginary human gate around it.

For ordinary reversible changes the target is zero independent reviews; for consequential
native/automated changes it is one independent technical review, then normal automation.
Enforce real CI, current source/integration compatibility, explicit HOLD/STOP, conflicts,
and any actually required review. Missing or unreadable enforcement data must fail closed
for its dependent effect. Formal approval and a separate non-author arming decision are
not blanket prerequisites. Negative tests should cover the actual required review's absent,
stale, revoked and conflicting findings, plus hold, red CI and head races. Reuse valid
qualification until relevant source or requirements change. Never use REST/admin bypass.

`merge-blocked` is a refusal/diagnostic to investigate, **not** approval to
clear a hold. Record `ARMED`, `REFRESH_DEFERRED`, `CHECKS_PENDING`,
`CONFLICT`, `HELD`, `MERGED`, and `PROVEN_LIVE` as distinct evidence
claims, never as one "auto-merge enabled" status. Post-merge production
verification is still required when owed. For other repositories, inspect
their own current protected rules and release path; a Macro label is not a
universal auto-merge switch.

## Review-readiness liveness (no implicit reviewer execution)

This is sequencing guidance for the existing GitHub/Executive owners, **not** a
fourth review-intent channel, an approval bypass, an automatic review dispatcher,
a new watcher, or permission to retry an explicitly refused effect.

1. Re-read the exact repository, PR/head, Draft state, changed-path custody,
   local qualification, hosted checks and existing non-author review requests
   before the next metadata mutation. If the candidate is locally qualified
   and stable, transition it to **Ready for Review** even when hosted checks
   are still running; preserve any failed required CI as a merge blocker.
2. Request the genuine non-author GitHub reviewer only on an eligible reviewable
   candidate **only when a binding native branch rule or a separately authorized explicit manual request requires one**; risk tier alone creates no reviewer operation. A `review_requested` event observed while Draft is refused by
   the existing review-intent admission and a later `ready_for_review` event
   does **not** replay it. If a reviewer is already requested, inspect and
   consume that **same formal request**; do not send a duplicate technical
   Fabric/Dot job or manufacture a new review-intent event to evade a refusal.
   Any genuinely distinct authorized review needs its own admission and
   independent identity.
3. Distinguish `REVIEW_REQUESTED`, reviewer acknowledgement, actual independent
   review submission and `APPROVED`; none follows automatically from the
   preceding state. Reviewers may be unavailable. Record the **specific**
   missing external action and its existing exact carrier; do not call a
   notification, Slack mention or reviewer request an active worker.
4. At the next useful integration boundary, consume exact-head hosted CI and
   actual non-author review readback once. If either is still pending, continue
   source/test work on a path-disjoint dependency. After two support-only cycles
   with no new evidence, classify a no-delta loop and change tactic instead of
   polling or filing another handoff. This follows the protected
   `docs/sol_skills/ACTIVE_EXECUTION.md`, not a new lifecycle policy.
5. Keep the branch-protected release gate: required exact-head CI, genuine
   non-author approval **only where required by binding native rules or a specific release hold**,
   relevant source-law compatibility and native merge queue. After merge, verify any owed installed instructions, provider skills
   and real user-path behavior separately. `Ready` never means `merged`,
   `installed`, or `PROVEN_LIVE`.

## Recovery and concurrency rules

- Never resolve concurrent work by copying one shared directory over another.
  When actual path/semantic/dependency collisions require composition, coordinate with the
  incumbent source writer and update that same branch/worktree with bounded conflict resolution,
  affected tests, and appropriate review. Do not join/rebase merely to reset GitHub's `behind`
  count; rely on the native immutable merge-ref/merge-queue proof for a compatible unchanged head.
- Never bypass a failed check merely to get a deployment out.
- Never deploy a draft PR, a branch head, or a commit that is not the current
  `origin/master`.
- If a deployment fails, keep the PR/merge history intact, inspect the deploy
  log, and fix forward in a new PR. The deploy script attempts an automatic
  rollback before returning failure.
- GitHub credentials belong in macOS Keychain through `gh auth login`. VPS SSH
  credentials remain machine-local with mode `0600`; neither belongs in git or
  agent memory.

## Bootstrap note

The repository was initialized from the committed local history on 2026-07-30.
Pre-existing uncommitted application work was preserved separately in a draft PR
and must pass its failing acceptance tests before it is eligible to merge.

## Release attended Web workspaces

**Only if this operation acquired a host-local `mmx-workspace` checkout**, release
that same workspace through the custody owner. A GitHub-native operation has no
local worktree to release or register:

```bash
mmx-workspace release \
  --operation-id <stable-operation-id> \
  --lane web
```

`REMOVED` means the clean checkout was recoverable from the acquired base, current
`origin/master`, or the observed origin branch. `PRESERVED_DIRTY` and
`PRESERVED_UNPUBLISHED` are intentional fail-closed states: reconcile and publish
or deliberately preserve that work before trying to release it again. Workspace
release never deletes the Git branch. Missing old registrations may be pruned only
as a separate maintenance action after the backing path is proven absent.

The linked mode is for trusted attended sessions running as the repository owner.
Executive workers with a distinct OS principal continue to use the private,
credentialless clone prepared by `control_plane.executive_workspace`.
