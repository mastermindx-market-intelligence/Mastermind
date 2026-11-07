# Workspace release integrity — 2026-11-07

## Problem and change

The canonical release of this mission’s completed Macro source-consumption workspace failed before mutation: its read-only fleet-wide `git worktree list --porcelain` exceeded the60-second limit. The existing CLI also classified a lost native unlock/remove reply as NOT_APPLIED, which could falsely authorize a duplicate operation.

This repair remains in the existing Executive workspace owner and CLI. Release binds the original workspace directory, common Git directory, administrative registration, HEAD, branch and managed lock. A bounded census reads only existing administrative gitdir records to verify Git’s unique raw-suffix target selection, including the main worktree. It checks stable membership/record identity and revalidates before mutation. It does not read peers’ HEAD/index or create another registry. Ordinary inspection and acquisition retain their existing behavior.

Existing all-file cleanliness checks (including ignored files), source publication/commit recoverability and non-force native Git unlock/remove remain mandatory. Changes to the target or lock refuse before mutation. After unlock, late files or a replaced directory/registration prevent removal. Lock restoration is attempted only for the uniquely selected original target with proven absence of a current lock; a replacement, foreign lock or dangling symlink is never overwritten.

Uncertainty starts before the first native mutation invocation. The CLI returns EFFECT_UNKNOWN with original operation/path/head/branch, phase, restoration status and retry_authorized=false if that call or later verification fails. Restoring the original lock does not erase an uncertain partial removal. A preflight refusal remains NOT_APPLIED. Successful release still retains source branch/ref history.

## Actual qualification

The initial five regression cases produced four failures and one pass against the old source. They demonstrated the fleet-enumeration dependency, misclassified lost replies after real unlock and real removal, and duplicate native registration reaching mutation. All five passed after the repair.

The complete focused run executed328 cases:306 passed and22 failed. The20 new release fault cases, all104 CLI cases and all59 repository-binding cases passed. New cases cover before/after-unlock file writes, HEAD/branch/lock/registration/directory replacement, partial removal, raw suffix/case aliases and an unrelated new registration between observations.

The22 failures were in existing assignment sealing and MCP mount composition. A bounded environment probe found process umask0077 and MCP2.3.0 (whose low-level Server lacks list_tools), while this source explicitly pins MCP1.28.1. A separate disposable venv installed that exact declared SDK, and only its test child used umask0022. All22 affected cases then passed, zero failures/errors/skips, with no production source, installed environment or test assertion change. This is retained as a failed328-case run plus a successful22-case environmental follow-up, not a retroactively green run.

Exact commands, source hashes, module totals, log/JUnit digests and before/after receipts are in `review_evidence/workspace_release_integrity/qualification-20261107.json`. Git diff checking and Python syntax validation pass. Required hosted Linux CI and protected delivery remain required.

## Runtime boundary

No live helper was hotpatched, no installed workspace was removed by this repair, and the original failed Macro release has not been retried. The selected M2 launcher contains the existing multi-volume pool router and immutable payload8bd8daae5cec4bf0bfc08481fb31583473475e19. Its next upgrade must use the existing immutable launcher publisher while preserving that router and its repository/storage bindings. A fixed single-root wrapper must not replace the enrolled router.

Git2.50.1’s native unlock/remove can still enumerate registrations. This repair removes redundant Python-side full-fleet observations and hardens effects; it does not promise constant-time release, atomic exclusion against concurrent writers, or measured availability. Existing terminal-operation/live-writer checks remain required. After protected source delivery and a qualified installed upgrade, reconcile and release the same completed Macro operation once through canonical mmx-workspace, then record the actual result.

The unrelated #1199 branch-adoption scope and its thermal-refused/uncertain effect remain untouched. No retained-ref, promisor, offline-adoption or failed-adoption recovery behavior is changed.

## Authority and provenance

Operation: workspace-release-integrity-20261107-sol-001. Source base5199647e89166d163392905574097b2cfa16ca5b; compatible governing pin e63d8acaebe0d3cee1ce7cfb8d85294bf0c57f46. Protected547a880894b0f3d28a6d5118ee2534287b3fc1c0 has no governing-law delta.

Native selection was checked against Git2.50.1 primary source: [worktree.c](https://github.com/git/git/blob/v2.50.1/worktree.c), blobc34b9eb74e595af949d2c5ea8abf9687e90bbf0c, and [builtin/worktree.c](https://github.com/git/git/blob/v2.50.1/builtin/worktree.c), blob88a36ea9f8674e4f3708e359835765cb799011fc. Self-review and focused tests satisfy the attended Web review waiver; actual protected rules remain binding.
