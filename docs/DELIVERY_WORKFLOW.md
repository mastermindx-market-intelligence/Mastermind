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
git merge-base --is-ancestor origin/master HEAD
```

If a session opens in the legacy shared checkout and it is dirty, do not clean,
stash, reset, or overwrite it. Treat those changes as user-owned. Create a fresh
worktree and move only the task's deliberate edits there.

## Complete a change

1. Run the smallest relevant test set while iterating, then the repository CI
   gate before handoff.
2. Review `git diff --check`, `git status`, and the staged diff. Never stage
   `.env*`, credentials, logs, caches, runtime `data/`, or backup archives.
3. Commit a scoped change, push the branch, and open a PR:

   ```bash
   git push -u origin HEAD
   gh pr create --fill
   ```

4. Wait for required checks. If checks fail or the work is incomplete, mark the
   PR draft and stop; do not merge or deploy.
5. Merge through GitHub:

   ```bash
   gh pr checks --watch
   gh pr merge --squash --delete-branch
   ```

6. Resolve the merge commit from GitHub and deploy that exact commit:

   ```bash
   git fetch origin master
   merge_sha="$(git rev-parse origin/master)"
   ./scripts/deploy_from_git.sh "$merge_sha"
   ```

The deploy wrapper archives `origin/master` into a temporary clean release
directory. Local uncommitted files cannot enter the release. The VPS deploy
creates a rolling snapshot, restarts `mastermind.service`, checks
`http://127.0.0.1:8001/health`, and rolls back on failure.

## Recovery and concurrency rules

- Never resolve concurrent work by copying one shared directory over another.
  Rebase or merge the latest `origin/master` into the task branch and resolve
  conflicts in the branch worktree.
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
