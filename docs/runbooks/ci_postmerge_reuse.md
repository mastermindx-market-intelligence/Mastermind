# Exact same-SHA post-merge CI reuse

## Purpose

GitHub's native merge queue already executes the complete required `CI / test`
workflow against the integrated commit. When that exact commit is later pushed
to protected `master`, the second full pytest run is redundant. This
workflow-level optimization does **not** change the merge queue, source
admission, branch protection, required `test` context, product deployment or
the canonical pytest module-selection policy.

## Fail-closed rule

The CI workflow still starts all six real runner **jobs** on every event,
always runs the source-bound release preflight on each shard, shard-zero
Paper/Fabric/compile/shell gates, both shard-two H1 Linux gates, and the
required aggregate `test` job. The real H1 no-ACL fixture and its exact
initializer/provider assertions are unchanged. Immediately before each pytest
step, one bounded read-only proof check returns `reuse=true` only for a
`push` to `refs/heads/master` with the current exact `GITHUB_SHA`.

The proof requires the sole matching native `merge_group` CI workflow run
for that SHA to have finished successfully, and verifies the exact current
attempt's seven unique successful jobs **and** their executed required
steps: `pytest shard 0..5`, the required `test` gate, every shard's full
pytest and release-preflight steps, the four shard-zero qualifications,
and both shard-two H1 Linux qualification steps. Missing, skipped or
duplicate mandatory steps fail closed; legacy three-shard proof is not
accepted. The workflow run is re-read
after the job check to reject attempt/generation movement.

If any field, producer, step, attempt, permission, request, response,
repository identity or completion proof is absent/ambiguous, the proof writes
`reuse=false` and the existing complete pytest shards run. Pull requests,
merge queue candidates and manual workflows always run full pytest. A
protected push must have BOTH its API-authenticated actor and triggering
actor equal to the native `github-merge-queue[bot]` Bot. Human/API direct
pushes still run full pytest, even when they reuse an otherwise proven SHA.
The current HEAD, working tree and index must also match that exact SHA. Failed or
cancelled merge-group results are never reused.

An actual skip occurs only at the **pytest step**, never at the matrix job
or protected final `test` job. The static source policy pins the proof
step ID, command, GH token surface, ordering and runner condition. A simple
`if: skip` on a required job would be unsafe and is not used.

## Credentials and effect boundary

A single read-only addition of `actions: read` is scoped to the existing
`pytest_shards` job only; root CI and the protected final `test` remain
`contents: read`. The primary checkout explicitly sets
`persist-credentials: false` while retaining `fetch-depth: 0`; the secondary
Macro checkout already disables persistence. This prevents the checkout action
from leaving its authentication token in local Git configuration for subsequent
install/repository/test steps. The proof step receives its explicit `GH_TOKEN`
environment binding; pytest is not explicitly given that binding. These job
permissions and step environment choices are not a process sandbox or proof that
arbitrary trusted job code cannot access any runner credential. No new PAT, key, credential store, scheduler, agent,
watcher, lifecycle or queue is introduced. The proof uses at most five bounded
same-repository GitHub GET requests, each capped at 256,000 response bytes,
with no retries and no persistent state. The current push and prior group
are reread to reject actor, identity, attempt or generation movement.
An authenticated GitHub API response may not redirect, including to the same
host: Python's default urllib redirect handler forwards the original Bearer
authorization to the new URL even when the host changes. The fixed read helper
uses an explicit no-redirect opener; an HTTP 3xx is unqualified proof and the
normal full pytest path executes. Two no-network redirect regressions and a
normal same-origin JSON control protect this credential boundary.

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
still successful on shard zero, source-bound preflights successful on all
six shards, both real H1 gates successful on shard two, and final `test`
successful. The existing finite job/pytest-step timeouts and best-effort
fixed-diagnostics upload are retained; a reused pytest step does not invent
a new test execution or a diagnostics artifact. Also retain
an ordinary PR-head full-run and a negative/no-proof test. If any unexpected
skip or false-green is found, restore the unconditional shard runner step
through the normal protected source workflow; never change branch protection
or force the proof to succeed.

This is a distinct bounded release optimization. PR #1486's independently
owned GitHub PR-head reader/native waiter is not modified or replaced.


## Released six-shard contract and real API acceptance case

The original #1570 carrier now integrates protected source
`ab93f3ede66486e82e995c88a86e662677973732`, including released #1616 and #1930.
All seven native jobs are required; no module exclusions, replacement status,
new controller or timeout extension is introduced. The historical local
whole-repository test refusal remains in force; this repair uses focused
proof, workflow-policy and H1 source-contract tests, followed by normal hosted CI.

The read-only positive fixture is actual merge-group CI `41518522230` and
same-SHA push `41522114032` at `22c08067ed0f480d1d5324a815fa248661c4ab46`.
Its five owner responses fit the existing cap (largest 31,086 bytes). A
separate parent acceptance harness covers the genuine positive and 80
negative mutations. This is a candidate-function test against real API
observations, not evidence that the candidate was installed in that run.
That push actually repeated 6,176 pytest-step seconds across six runners;
this is a measured reuse opportunity, not achieved savings.

The failed implementation commission is retained under its original run;
no model, provider or account fallback was attempted. Direct integration on
the same reconciled source carrier does not satisfy independent review.
The current source head still requires an independent security verdict,
its own hosted CI and normal protected release before installed reuse can
be accepted.


Integration exposed one adjacent H1 source-contract assertion that required
an unconditional full-pytest step. That single assertion now requires the
exact pinned proof condition, while retaining all original checks that both
H1 steps execute first on shard two with unchanged isolation and positive
validators. No initializer implementation or Linux fixture was modified.
This is the sole eighth changed path beyond the original seven-path repair.

## Released Paper prepare guard composition (2026-11-03)

The six-shard adaptation also retains protected source's exact
`Verify Paper Studio prepare guard` step on shard zero. It runs
`node --test paper-design.test.mjs` in `integrations/studio_direct_mcp`
before reuse proof, regardless of whether full pytest can be omitted.
The workflow validator rejects omission, duplication, reuse-based suppression,
wrong command/directory, continued failure, or moving this gate after the proof.
The prior-run proof requires exactly one completed/successful copy of this step;
a successful job with its Paper guard missing, skipped, failed, pending or
duplicated cannot qualify. Existing redirect refusal, six-shard/H1 safeguards,
five-read budget and full-pytest fallback remain unchanged. These are source/test
contracts, not measured protected-push savings or installed acceptance.
