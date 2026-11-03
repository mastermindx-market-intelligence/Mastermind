# GitHub and VPS delivery workflow

`origin/master` is the only release source. The VPS remains the canonical writer
for live paper-portfolio state; GitHub owns code, configuration, tests, and
reviewable documentation.

## Start every session in isolation

From any clean administrative checkout, harness-provisioned sessions use the exact workspace already assigned by their harness. Attended ChatGPT Web/host sessions use the installed canonical source-custody launcher instead of raw clone/worktree commands or the repository Python payload:

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

1. Run the smallest relevant local test set while iterating. Publish a truthful
   candidate once its scoped source is stable and the relevant local qualification passes.
   For an ordinary non-author GitHub review, mark a qualified Draft PR **Ready for Review
   before asking the reviewer**. Hosted CI may still be queued or running: full required
   CI is a merge/release gate, not a prerequisite for review readiness. Keep unfinished
   or locally failing work in Draft; do not imply a reviewer is working just because
   a request exists.
2. Review `git diff --check`, `git status`, and the staged diff. Never stage
   `.env*`, credentials, logs, caches, runtime `data/`, or backup archives.
3. Commit a scoped change, push the branch, and open a PR:

   ```bash
   git push -u origin HEAD
   gh pr create --fill
   ```

4. CI blocks merge/release, not independent useful work. Incomplete scope, failed
   local qualification, or a known failing hosted check keeps release held; diagnose the failure and repair it within the assigned scope. A **pending** hosted check alone is not a reason
   to keep an otherwise qualified, reviewable PR in Draft. The incumbent
   `control_plane/github_review_intent.py` explicitly refuses `review_requested`
   events while Draft (`PULL_REQUEST_DRAFT`); leaving a PR Draft while waiting for
   that same review creates a liveness deadlock. Mark the stable candidate Ready
   before initiating the eligible GitHub review-request path. Do not infer that
   a prior draft-time request will automatically be re-admitted when the PR
   becomes Ready. Continue path-disjoint tests, integration and repair while CI
   and the real non-author reviewer advance; never duplicate a refused Fabric
   review or move an unreconciled worker effect to another carrier.
5. Offload the wait to one existing Class-E or Class-T observer through the current
   process/CI owner. Bind repository, PR, exact head SHA and workflow run IDs; retain the
   process/run handle and return location in the existing checkpoint. Reuse an observer rather
   than creating one per check or chat. No merge/deploy action belongs in the observer.
   Consume only the matching candidate's results; a changed head invalidates stale observations.
   Queued CI is not a failing build, and do not push empty/rebase-only commits to restart CI.
   Without a usable observer, continue useful foreground work and check once at the next real
   integration boundary. Never claim a background Web turn or automatic wake that does not exist.
6. After required PR-head checks and review pass and queue entry is authorized, use the
   repository's native GitHub merge queue when enabled. The active queue's `merge_group`
   workflow qualifies the exact integrated candidate after queue entry and **before merge**;
   do not add a manual synthetic PR merge-ref check requirement or ancestry-only rebase as
   a precondition to queue entry. If final integrated checks fail, the queue must not merge.
   Preserve current head/concurrency checks and never use an admin bypass:

   ```bash
   gh pr checks --required
   gh pr merge --squash --delete-branch
   ```

7. Deploy only when the assigned change requires runtime rollout and release is authorized.
   A source-only, research, documentation or instruction task must not restart an unrelated
   application. For a required deployment, resolve this operation's actual merge commit from
   GitHub; the newest default-branch commit may belong to another operation:

   ```bash
   git fetch origin master
   merge_sha="$(gh pr view --json mergeCommit --jq '.mergeCommit.oid')"
   test -n "$merge_sha" && test "$merge_sha" != null
   ./scripts/deploy_from_git.sh "$merge_sha"
   ```

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
3. Verify **one genuinely independent formal GitHub APPROVED review** on the
   exact current PR head and current source qualification. A Fabric technical
   `SOURCE_PASS`, reviewer request, or green hosted CI is **not** approval.
   A newer `CHANGES_REQUESTED`, dismissal, materially changed head or
   indeterminate reviewer identity invalidates the release evidence. Check
   actual review author against PR/commit authors; changing account inside
   the same reasoning session does not establish independent scrutiny.
   **Current interim gate:** Macro's sweeper does not yet read native PR
   reviews, so the eligible independent release/arming actor must verify
   this evidence before applying the opt-in label. Do not claim that
   `merge-on-green` alone enforces review, or use a shared author account
   to circumvent the no-self-approval/no-self-merge rule.
   **Cross-repository command boundary:** every CLI command below must bind
   `--repo mastermindx-market-intelligence/macro`; never rely on the current
   shell checkout or a previously selected repository to identify the PR.
4. Only when release is **actually authorized**, the head checks are
   concluded clean, and no hold/merge gate remains, the eligible release
   operator may opt in by adding the **single existing label** under the
   **current interim non-author release fence**:
   `gh pr edit <number> --repo mastermindx-market-intelligence/macro --add-label merge-on-green`
   (or the additive GitHub issue-label action). Record exact
   repo/PR/head, reviewer identity/decision and check/run evidence on the
   existing source-linked release record. Do not substitute
   `main-red-repair` (a separately justified exception) or touch
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

### Review once, release automatically — only after machine enforcement

The Chairman's target is **one independent source review, then an automatic
protected release**, not a second standing human release ceremony. The target is
**not yet live authority**: Macro's existing sweeper does not check formal
GitHub review state, and Mastermind's active native queue ruleset must not be
assumed to require review merely because a merge queue is configured.

Before dropping the interim non-author arming/release fence, the *incumbent*
controller or protected repository policy must enforce an exact-head formal
approval from a reviewer genuinely independent of source authors, review
revocation/CHANGES_REQUESTED, binding CI and current integrated proof, explicit
HOLD/STOP release order, branch conflicts and unavailable API data. Prove
negative tests for absent, stale, revoked, self-authored and unreadable reviews,
plus hold, red CI, stale-base and race conditions. Only after the existing
machine gate is **installed, independently qualified and read back** may the
existing release automation admit a reviewed, CI-green, unheld candidate
without an additional non-author release operator. The author must still not
self-merge through REST or an admin bypass, and the `merge-on-green` label
remains an opt-in, never proof of approval. A source change or successful
controller run does not establish production adoption.

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
   candidate. A `review_requested` event observed while Draft is refused by
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
   non-author approval, relevant source-law compatibility and native merge
   queue. After merge, verify any owed installed instructions, provider skills
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

After the operation is terminal, release the same workspace through the custody owner:

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
