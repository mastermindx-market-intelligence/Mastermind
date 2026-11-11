# Managed multi-repository workspaces implementation plan

> Execute inline through the existing #685 workspace; use test-first changes and independent whole-candidate review. Current Chairman approval covers this routine plan/build/test cycle; no additional planning approval round is requested.

**Goal:** A Web CEO can perform managed Macro/Terminal source work and publish exact candidates without arbitrary paths or another machine.
**Architecture:** Extend the existing host-pinned mmx-workspace route, then compose its receipts into existing Studio Git and Workbench boundaries. No second allocator, publisher, lifecycle or store.
**Tech stack:** Python standard library, POSIX shell, Git, Node ESM, existing MCP gateways.
**Spec:** `docs/superpowers/specs/2026-10-03-managed-multirepo-workspaces.md`.

## Global constraints

Preserve implicit Mastermind CLI v1 behavior and paths. Explicit aliases are exactly mastermind/macro/terminal. Canonical defaults are master/main/master. Existing storage UUID/root/reserve policy remains unchanged. Native harness workspaces and private workers are untouched. #1014 release-evidence changes and other active source writers require separate reconciliation, not copying their whole files. No production install before its applicable source/review/release gates.

## Review focus

Cross-repository same-operation collision; a disappearing/rebound source path; hostile inherited environment; storage root versus repository subroot; lost acquisition response after a possible effect. Each has an explicit test/verification below.

### 1. Reconcile the original carrier

- [x] Read protected source, installed launcher, #685/#929/#1099 and relevant open-path collisions.
- [x] Reuse the original installed-owner workspace and fast-forward to published #685 head63f3c980.
- [x] Resolve the three genuine integration conflicts to current protected source, after proving all #685 semantics are retained. Index tree equals protected775dbbf5; preserve MERGE_HEAD until the substantive new source commit.
- [x] Run current workspace/storage/sparse baseline, keeping historical umask-only fixture behavior explicit.

### 2. Closed multi-repo CLI and installer

Files: `scripts/mastermind_workspace.py`, `scripts/install_mastermind_workspace_cli.sh`; new `tests/test_mastermind_workspace_repositories.py`; minimal fixture updates in existing CLI tests only when the real installer now validates origin.

Interfaces: `installation_repository_bindings(source: Path, registrations: list[str]) -> dict`; closed host-pinned `MASTERMIND_WORKSPACE_REPOSITORIES` wrapper literal; CLI `repositories` and additive per-action `--repository {mastermind,macro,terminal}`. Existing constructor/lock/release owner is reused.

- [x] Write real-Git tests for three aliases, same-operation separation, reuse and dirty preservation; first run must fail for missing CLI behavior.
- [x] Test unenrolled/malformed binding, wrong origin, replaced common Git directory, unknown alias and invalid base with zero created branch/workspace.
- [x] Implement host-side validation before allocation; derive repository subroots but check storage against the unchanged host root.
- [x] Extend the existing installer with repeatable admin-only `--repository-source alias=/absolute/source`; validate before copying and emit shell-quoted immutable mappings. Test hostile environment and paths.
- [ ] Run new tests plus existing CLI/workspace/sparse/secondary-host tests; inspect exact diff, then commit/publish the substantive integrated candidate on #685.

### 3. Studio Direct consumer

Reuse `git-publish.mjs`; add only bounded repository-selection/acquisition composition and truthful tool schemas. Inspect current #795 source equivalence and gateway-hunk collisions before effects.

- [ ] Write Node tests for describe/acquire/status, correct publisher selection, exact HEAD/remote fences, unknown targets and ambiguous acquisition recovery.
- [ ] Delegate workspace creation to the installed launcher; public inputs contain no paths, remotes, credentials or shell.
- [ ] Preserve old Mastermind calls; test actual local MCP discovery and calls as well as helper behavior.
- [ ] Publish source and run the complete Studio package tests; independently review the exact combined candidate.

### 4. Installed consumer qualification

- [ ] Reconcile source/review/CI/release gates; install only the accepted release using the existing installer, preserving prior launcher for rollback.
- [ ] Bind real known Macro/Terminal sources only after observing their current Git identity and sparse enrollment.
- [ ] Prove acquire/status/reuse and isolated edit/test/commit/push readback for both, preserving foreign worktrees and production files.
- [ ] Update affected repository guides to distinguish attended-owner allocation from native harness workspaces through normal repo PRs.
- [ ] Restore the exact Workbench C3 transport through its existing operator only after lease/action/artifact reconciliation; do not retarget a live shared root. Prove native manifest/tool behavior and document any separately gated per-operation binding.
- [ ] Persist exact installation/release/consumer evidence and remaining obligations to #685 and existing #539/#911 owners; safely release only this operation's finished workspace.
