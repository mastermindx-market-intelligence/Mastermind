# Sparse workspace preflight and Git advisory repair

**Source candidate; not installed or selected.** Final focused validation:
**79 tests passed, 0 failed, 0 skipped**. Exact hashes and test scope are in
[source-validation.json](source-validation.json).

## Two concrete failure paths

The current caller verifies the helper and donor, then starts the effectful
Macro `fabric-mint` helper. That helper checks whether the requested object is
a commit before allocating a worktree. The caller treats any nonzero helper
return as an unknown workspace effect, because it cannot infer the stage of
failure from the exit code. Thus a clean missing-commit refusal inside the
helper can unnecessarily retain the lane as an unresolved workspace operation.

The added preflight uses the existing closed `_sparse_git` observer against the
same qualified donor, common Git directory and exact requested SHA. It accepts
only `b"commit\n"`. A completed, qualified observation that cannot establish
a local commit refuses with `FABRIC_SPARSE_PINNED_COMMIT_UNQUALIFIED` before
the workspace helper starts. The existing lease path handles that pre-helper
refusal; this patch creates no new lease or cleanup owner.

The first test run also reproduced a separate compatibility failure. A valid
`git ls-files` read returned exit 0 and correct output, but wrote Git's
`advice.sparseIndexExpanded` advisory to stderr. The strict observer rejected
it before workspace creation. The scoped Git settings now disable only that
documented advice. Other stderr, nonzero exits, configuration drift, index
flags, uncommitted changes and untrusted inputs retain their existing checks.
The setting does not modify a user's persisted Git configuration.
See [Git's configuration reference](https://git-scm.com/docs/git-config/2.46.2.html).

## Preserved effect boundaries

An observer's `SparseWorkspaceRefused(effect_unknown=True)` is re-raised
unchanged. The new preflight does not downgrade incomplete observation or
unproven process cleanup to a known-no-effect refusal. Unexpected exception
types are not converted into the new clean-refusal class.

The helper identity check still runs after the new observation. The helper
also retains its own commit check. If the commit or donor changes after
preflight, or the helper fails after starting, the existing conservative
unknown-effect handling remains in force. Local commit presence does not prove
that every later tree/blob can be materialized or that allocation will succeed.

The closed Git path already disables transport and lazy-fetch behavior. The
preflight does not acquire missing source objects. Source acquisition remains
with the existing source owner; an uncertain or timed-out object observation
still retains its existing conservative disposition.

## Verification

The new cases use disposable real Git repositories to verify missing pins and
blob, tree and annotated-tag objects. They inject observer cleanup uncertainty,
unexpected observation failures and helper drift, and prove that the helper is
not called on a preflight refusal. A helper that fails after a successful
preflight still produces an unknown-effect result.

The advisory cases verify that modified tracked files and untracked files in
excluded directories are still rejected. Clean, byte-identical tracked files
that Git has materialized are preserved, consistent with the existing donor
contract. The fix does not delete or re-sparsify these files.

The existing composition suite also passed. It verifies the historic source
transformation chain, unchanged negative donor cases, rebuilt native manifest,
immutable support publication and the inert end-to-end execution seam.
Historical source preimages remain unchanged; the new delta has its own
forward-patch fixture and digest.

The rebuilt inventory has 102 members. Only `ext/remote_sub_exec.py` changes
inside that closure. Its SHA256 changes from
`5880bad86fc4bc65a8460baf6156b46333a0ce33c24ef6742c905aa7db55ce2d` to
`7c7b94a974b85804598c49fc21ea1eb0d5ea55888dc3a6394dde8ab0b4d113e2`.
The original `source/remote_sub_exec.py` preimage and predecessor catalog
fixture are preserved.

## Historical Ubuntu2 incident

The four original runs are now bound through the retained ledger to root
`e3d62d36-ba30-4fed-a723-f6ce79ba4f99`, parent
`orch-v91-seat-direct-20261102`. They used support generation
`858b767be20a09d32f38995296fec25a514f4442a847b8ed7e24e678ee6139de`,
whose executor differs materially from the currently selected implementation.

Each original mint helper returned 1 after about 60 seconds. Its retained
process receipt proves termination of its observed descendants with residual
count zero, but records only the stderr byte count (55), not the stderr text.
The outer launcher returned 76 with `FABRIC_SPARSE_MINT_UNVERIFIED`.
No normal worker-process receipt was found for those attempts.

A missing-pin failure is consistent with one early helper diagnostic of that
length; it is **not established as the original cause**. Current reads found
no destination, branch, reflog or worktree registration for the first two
attempts, and their packet SHA candidates now exist as commits. The third
object read timed out with transport disabled, so the fourth was not queried.
The later exact-SHA process census found no matching residual process.
These current reads cannot retroactively settle the historical effects.

The four provider lease rows currently report released; that is an observation,
not a release performed by this operation. The four local workspace
reconciliation holds remain unchanged. This patch does not extend the closed
historical reconciliation contracts or authorize retry. Complete original
effect reconciliation and a fresh admissible worker remain separate work.

## Release and fleet acceptance

The live generation remains unchanged. The source-release owner must review
the exact published change, satisfy protected merge checks, and rebuild from
the protected merged source before considering generation selection. There is
no permission to install an unmerged stage as a shortcut.

Live fleet evidence is separately retained in
[runtime-validation.json](runtime-validation.json). Ubuntu0 completed one
bounded GLM task, returned verified arithmetic, received parent acceptance and
cleaned up normally. The larger GLM audit and the Qwen review did not deliver
accepted work. Ubuntu4 remains qualification-only, and Ubuntu2 remains held.
No whole-fleet-ready claim follows from the 79 source tests.


## Independent review and supplemental checks

The bounded Grok-pool technical review at source head
`bb0266fc54124255e5373ec20607ba410674cecd` returned
`NO_BLOCKING_FINDING_WITHIN_SCOPE`. The assigning parent verified the exact
response digest and accepted it. This is an excerpt review, not whole-repository
approval or a formal GitHub review; see [review-result.json](review-result.json).

The reviewer identified two low nonblocking limits: collapsing known-effect
diagnostic reasons under the pin-refusal code, and the need to establish that
suppressing advice does not conceal persistent index changes. The original
observer cause remains chained. The setting is process-scoped and does not
persist Git configuration. The pre/post metadata fingerprint does not cover
index bytes; no broader concurrent-index guarantee is claimed.

Two additional focused tests now establish that the previously failing real
sparse-index read preserves index/config/sparse-checkout bytes and that valid
stdout with exit 0 still refuses unrelated stderr. Both passed, with no skips,
errors or failures. They supplement the earlier 79 passing cases. Source
inspection also confirms the unchanged executor consumer holds uncertain
effects and returns 76, while known pre-launch refusals return 78 and exit the
lease context normally. The lease's sticky preserve flag retains unknown-effect
markers.

Only tests and evidence changed after the reviewed source head. The executable,
forward patch, manifest and inventory hashes recorded above remain exact.
No installed runtime, historical hold or provider qualification changed.
