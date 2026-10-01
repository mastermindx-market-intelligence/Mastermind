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

The JSON receipt supplies the exact `workspace_path`, derived branch, base SHA, and shared Git common directory. Repeating `acquire` for the same operation reuses that workspace. Never point two independent operations at one workspace or mint proof/review worktrees outside this owner. Before editing, `cd` to the receipt path and confirm:

```bash
git status --short --branch
git rev-parse HEAD
```

Verify the receipt's operation, source repository, branch and acquired base against the
custody owner before editing. A reused workspace need not contain the latest
`origin/master`. Protected-base movement is assessed through
`docs/sol_skills/RECONCILE_STATE.md` Step 3A and
`docs/superpowers/specs/2026-09-02-autonomy-release-compatibility-review-reuse.md`:
keep semantic review separate from latest-base integration proof. Do not move a
reviewed source branch merely to refresh ancestry. This does not waive current-source
reconciliation, collision checks, required integration checks or release authority.

If a session opens in the legacy shared checkout and it is dirty, do not clean,
stash, reset, or overwrite it. Treat those changes as user-owned. Create a fresh
worktree and move only the task's deliberate edits there.

## Complete a change

1. Run the smallest relevant local test set while iterating. Publish a truthful candidate
   and request review with those results while hosted checks are pending; full required CI
   remains a merge/release gate, not a prerequisite to handing off a reviewable candidate.
2. Review `git diff --check`, `git status`, and the staged diff. Never stage
   `.env*`, credentials, logs, caches, runtime `data/`, or backup archives.
3. Commit a scoped change, push the branch, and open a PR:

   ```bash
   git push -u origin HEAD
   gh pr create --fill
   ```

4. CI blocks merge/release, not independent useful work. If checks fail or work is
   incomplete, keep the PR draft and release held; diagnose the failure and repair it within
   the assigned scope. While checks are queued/running, continue the highest-leverage safe
   independent implementation, tests, review or integration preparation. Do not duplicate an
   incumbent worker or mutate its frozen review candidate merely to appear busy.
5. Offload the wait to one existing Class-E or Class-T observer through the current
   process/CI owner. Bind repository, PR, exact head SHA and workflow run IDs; retain the
   process/run handle and return location in the existing checkpoint. Reuse an observer rather
   than creating one per check or chat. No merge/deploy action belongs in the observer.
   Consume only the matching candidate's results; a changed head invalidates stale observations.
   Queued CI is not a failing build, and do not push empty/rebase-only commits to restart CI.
   Without a usable observer, continue useful foreground work and check once at the next real
   integration boundary. Never claim a background Web turn or automatic wake that does not exist.
6. After required exact-candidate checks and review pass, and merge is authorized, merge
   through GitHub. A status query is not permission to merge; preserve current head/concurrency
   checks and never use an admin bypass. Bind `pr_number` and `reviewed_head_sha` to
   the accepted release record, not a newly observed unreviewed head. Preserve the
   action-time protected-base comparison required by the integration proof. A failed
   check must stop the command chain, and a changed PR head requires reconciliation:

   ```bash
   gh pr checks "${pr_number:?set the accepted PR number}" --required &&
     gh pr merge "$pr_number" --squash --delete-branch \
       --match-head-commit "${reviewed_head_sha:?set the accepted semantic head}"
   ```

7. Resolve the merge commit from GitHub and deploy that exact commit:

   ```bash
   merge_sha="$(gh pr view "${pr_number:?set the accepted PR number}" \
     --json mergeCommit --jq '.mergeCommit.oid')" &&
     [[ "$merge_sha" =~ ^[0-9a-f]{40}$ ]] &&
     ./scripts/deploy_from_git.sh "$merge_sha"
   ```

   Missing, malformed or unreadable merge evidence blocks deployment. Never substitute
   the moving `origin/master` tip for the accepted PR's merge commit. The existing
   wrapper fetches and refuses a commit that is no longer current `origin/master`;
   reconcile the new release identity and its authorization rather than silently
   changing `merge_sha`. Merge acceptance does not itself authorize deployment.

The deploy wrapper archives `origin/master` into a temporary clean release
directory. Local uncommitted files cannot enter the release. The VPS deploy
creates a rolling snapshot, restarts `mastermind.service`, checks
`http://127.0.0.1:8001/health`, and rolls back on failure.

## Recovery and concurrency rules

- Never resolve concurrent work by copying one shared directory over another.
  For proven path/dependency-disjoint protected movement, keep the source branch
  unchanged and refresh latest-base integration proof under the reconciliation and
  review-reuse law above. Unknown materiality blocks release; it is not permission
  for a blind branch join. Update source only when a real conflict, material dependency
  change or candidate repair requires it, through the existing source-custody owner.
  Re-review changed semantics; never rebase/reset/force-update a reviewed shared branch
  for ancestry cosmetics.
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
