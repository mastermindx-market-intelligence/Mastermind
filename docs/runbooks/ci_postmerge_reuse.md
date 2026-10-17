# Exact same-SHA post-merge CI reuse

## Purpose

GitHub's native merge queue already executes the complete required `CI / test`
workflow against the integrated commit. When that exact commit is later pushed
to protected `master`, the second full pytest run is redundant. This
workflow-level optimization does **not** change the merge queue, source
admission, branch protection, required `test` context, product deployment or
the canonical pytest module-selection policy.

## Fail-closed rule

The CI workflow still starts all three real runner **jobs** on every event,
always runs shard-zero Paper, Fabric, compile and shell gates, and always
runs the required aggregate `test` job. Immediately before each pytest
step, one bounded read-only proof check returns `reuse=true` only for a
`push` to `refs/heads/master` with the current exact `GITHUB_SHA`.

The proof requires the sole matching native `merge_group` CI workflow run
for that SHA to have finished successfully, and verifies the exact current
attempt's four successful jobs **and** their executed required steps:
`pytest shard 0/1/2`, the required `test` gate and the original four
shard-zero non-pytest qualification steps. The workflow run is re-read
after the job check to reject attempt/generation movement.

If any field, producer, step, attempt, permission, request, response,
repository identity or completion proof is absent/ambiguous, the proof writes
`reuse=false` and the existing complete pytest shards run. Pull requests,
merge queue candidates, manual workflows and direct protected pushes without
an actual matching green merge-group run always run full pytest. Failed or
cancelled merge-group results are never reused.

An actual skip occurs only at the **pytest step**, never at the matrix job
or protected final `test` job. The static source policy pins the proof
step ID, command, GH token surface, ordering and runner condition. A simple
`if: skip` on a required job would be unsafe and is not used.

## Credentials and effect boundary

A single read-only addition of `actions: read` is scoped to the existing
`pytest_shards` job only; root CI and the protected final `test` remain
`contents: read`. The token is passed to the short proof step only,
not to pytest. No new PAT, key, credential store, scheduler, agent,
watcher, lifecycle or queue is introduced. The proof uses three bounded
same-repository GitHub GET requests with no retries and no persistent data.

## Verification and rollout

Source tests include malicious/missing job and step results, skipped test
steps, stale rerun attempts, wrong SHA/repository, denied API reads, missing
proof and workflow-policy bypass attempts. A read-only live GitHub CLI canary
against integrated #1476 SHA `2d7284af863e4435e83e176498feb62041716753`
resolved the exact historical merge-group CI run `38967208427`; a made-up
SHA returned no proof, and PR context made no request. This is a **read
canary**, not an installed rollout receipt.

Before protected merge: require new-head full hosted CI, independent
source/security review and native `merge_group` checks. The final
production-path acceptance after merge should show the same-SHA `push`
workflow with each `Run repository test shard` step omitted **only after**
a logged verified merge-group run, original Paper/Fabric/compile/shell steps
still successful on shard zero, and final `test` successful. Also retain
an ordinary PR-head full-run and a negative/no-proof test. If any unexpected
skip or false-green is found, restore the unconditional shard runner step
through the normal protected source workflow; never change branch protection
or force the proof to succeed.

This is a distinct bounded release optimization. PR #1486's independently
owned GitHub PR-head reader/native waiter is not modified or replaced.
