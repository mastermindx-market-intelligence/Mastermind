# Fabric original-worker creation seam — strict sparse checkout adoption

> **Historical source/fixture record, superseded 2026-10-18.** The current
> security repair and exact preimage contract are in
> [CLEAN_LINKED_DONOR_SOURCE_REVIEW_20261017.md](CLEAN_LINKED_DONOR_SOURCE_REVIEW_20261017.md).
> The October 14 standalone/combined patches and helper pins below must not be
> replayed over the incumbent M2 stack. Current configured ceilings remain
> **12/18/12/12**, with Ubuntu2/3 **80°C** new-job admission. Older thermal and
> capacity numbers below are dated history, not restoration targets.
> The linked actual-mint script exists in this integration directory but needs
> private staged executor/helper files and M2 dependencies; its old observations
> do not establish a self-contained CI test or execution proof for the repair.

**Prepared:** 2026-10-14 UTC. **Status:** SOURCE_READY / TESTED_IN_FIXTURES; **NOT** production-installed, provider-qualified, automatically selected, or accepted. This is the next bounded in-scope consumer step after [Macro draft #9194](https://github.com/mastermindx-market-intelligence/macro/pull/9194). It does not create another queue, retry/auth plane, worker-run registry, cleanup daemon, or source lifecycle.

## Why the existing helper matters

The original M2 `remote_sub.sh` transports a task packet, obtains its broker/provider lease, publishes an immutable support capsule, and launches host `remote_sub_exec.py`. That host-side executor verifies CWD, acquires **the same physical `LaneLease`**, then runs `sub.sh`/the provider native CLI in the supplied CWD. The launcher **does not currently create a sparse Macro worktree** when the supplied CWD is `~/lanes/repos/macro`.

Exact original run evidence:
- `dataos-p05-1` / Ubuntu0 / GLM frontier / 2026-10-13 21:04–21:33 UTC: original `cwd=~/lanes/repos/macro`, terminal `rc=0`, afterward separate `~/lanes/wt/dataos-p05-1` full checkout ~10.32 GiB on `lane/dataos-p05-1` HEAD `c770f5007aad69f5f8c811229794fd3c8d6de160`.
- `dataos-p06-1` / same host and original CWD / 22:16–22:42 UTC: terminal `rc=0`, afterward separate full checkout ~10.33 GiB, branch `lane/dataos-p06-1`, HEAD `1470668dcc71e2f285302d6cecf6f598da14b8b5`.
- Both branch heads lacked local remote-tracking containment at later inspection, so their source/checkouts were preserved. This is a **post-START creation** failure mode. Simply adding `auto_profile()` root recognition to an old workspace does not prevent the initial 10 GiB materialization.

## The Macro-owned strict primitive now built and tested

Draft Macro #9194 adds to the original `scripts/worktree_sparse.py`:
- `MASTERMIND_FABRIC_SPARSE_NEW=1` recognizes **only exact immediate linked worktrees** under `$HOME/lanes/wt/<run>` in the existing `is_session_worktree` predicate. Default is OFF; no old full checkout is touched by the candidate.
- An explicit `fabric-mint <run-id> <40-lowercase-hex-commit>` CLI derives `$HOME/lanes/wt/<run-id>` and branch `lane/<run-id>`; validates strict ID and pinned existing commit; then calls the **existing owner** `mint_session_worktree(..., fetch=False, reuse_existing=False, strict=True)`.
- This uses `git worktree add --no-checkout` and applies the existing `config/sparse_worktree.json` *before* materializing tracked files; omitted directories remain recoverable via the existing `add/full` source tooling. No default Git configuration/hook is changed globally, no background cleanup, no credential or lease issuance, and no remote fetch/repack storms.
- Exact tested source blob `620927823770362b5c1d1e0dec6584612624d848`, test blob `69eabbd947458d357c51816913ed6250f9c9da45`, **102 isolated real-Git tests passed** plus existing upstream sparse safety suites. Creation refuses reused worktree/branch, malformed ID, unknown pinned commit, and missing explicit qualifier.

## Required **original Fabric** integration boundary

The natural consumer is the existing M2 `remote_sub.sh` / original host `remote_sub_exec.py` launch transaction, **not** a new service or default host-wide shell hook.

1. A currently authorized orchestrator explicitly requests a **new Macro sparse workspace**, with its **original stable Fabric run ID**, parent/root, task intent, and exact existing donor-commit SHA. It must distinguish NEW from resuming an incumbent or reconciling an unknown-effect run. Neither an arbitrary prompt nor a bare environment flag grants new-workspace authority.
2. The launcher must obtain the real broker/provider reservation and physical host LaneLease **before the first worktree modification**. Validate host identity, resolved original donor, existing `min_free_gb + checkout_reserve_gb`, thermal/load/memory gates, and original transport. Only a newly minted, qualified run may pass the one-shot opt-in signal. If admission fails, there must be **no new checkout effect**.
3. After this admission, execute the same Macro source owner's `fabric-mint` within the selected host's donor Macro repository, **not** from a globally mutable or cloned alternative helper. The caller supplies the exact SHA resolved from original source authority. Example only (not an action or general instruction to run before a lease):

   ```sh
   MASTERMIND_FABRIC_SPARSE_NEW=1 \
     python3 scripts/worktree_sparse.py fabric-mint "${ORIGINAL_RUN_ID}" "${PINNED_COMMIT_SHA40}"
   ```

4. Require readback: destination is a real, new registered Git worktree at the selected host's `~/lanes/wt/<run-id>` (no symlink/foreign metadata); `HEAD == PINNED_COMMIT_SHA40`; `branch == lane/<run-id>`; `core.sparseCheckout == true`; `git status --porcelain` clean; excluded tracked heavy directories did not materialize. The original Fabric carrier records this as **a child of the original launch**, not as a new run/controller/lease identity. Only then pass **that exact destination as the worker CWD**. The task packet must not instruct the worker to mint another full checkout.
5. If minting/ref checks fail or their effect is uncertain, **freeze the affected original carrier** and preserve its lease/source/worktree for inspection. An SSH timeout or stream detach is not proof the worktree was not created. Never blind-retry, force-prune, or silently resume/rename an existing branch. Release only under the original contract's proven cleanup result.
6. Check original paid/native worker identity and return separately from source checkout creation. Test a **new** bounded authorized GLM job using the actual original M2 route and verify no heavy initial checkout, no duplicate worktree, no disk reserve regression, and exactly the original run's result/return. Do not use a synthetic no-provider test as a claim of production adoption.
7. Do **not** set `MASTERMIND_FABRIC_SPARSE_NEW=1` globally or retrofit old `sni-*` worktrees. Those incumbents have unknown source custody; an attempted modification on Ubuntu0 SNI worktrees was already blocked by OpenAI safety checks and not retried.

### Current source prerequisites

A prior host audit found Ubuntu0 and Ubuntu2 donor source clones **lacked** `scripts/worktree_sparse.py`, `config/sparse_worktree.json`, and the Macro `WorktreeCreate` hook in their then-checked-out revisions; Ubuntu1 had some source, Ubuntu3 had the profile/hook but still showed full directly minted SNI checkouts. **Do not install an unmerged draft helper into those shared clones**, force-checkout the primary repository, or equate source creation with all-host deployment. Source rollout must first be accepted by original Macro owner, including overlap with Mac SSD draft #6939, and then proven on the exact selected hosts/immutable support generations.

## Completion boundary

Production source candidate exists and is tested; **original Fabric pre-launch opt-in, immutable support admission, host installation, paid-worker selection and sparse CWD acceptance remain NOT_PROVEN**. The user-directed thermal fleet still has its existing M2 60s sensor, 85°C new-job cutoff/cooldown, and a separate conservative 6-lane/6-load ceiling on overheated Ubuntu2. Physical 9950X BIOS thermal profile and matched-load throughput remain dependent on attended admin maintenance. Do not mark the root mission complete from this spec or either draft PR.

## October 14 integrated prelaunch-source proof

**Reviewed original Fabric candidate now staged, tested and published as a source patch:** [`FABRIC_SPARSE_PRELAUNCH_CANDIDATE_20261014.patch`](FABRIC_SPARSE_PRELAUNCH_CANDIDATE_20261014.patch), with [actual Macro helper fixture](tests/test_actual_macro_mint.py), [ordering fixture](tests/test_prelaunch_order.py), [controller routing fixture](tests/test_controller_request.py), and [six-case helper/unknown-effect fixture](tests/test_workspace_integration.py). These are source artifacts under draft Mastermind #1404, **not a live edit to installed M2 Fabric or Ubuntu releases**.

Source delta binds exactly three current original entrypoints: `fabric_task.py`, `remote_sub.sh`, `remote_sub_exec.py`. New requests must explicitly supply `--new-macro-worktree <existing-40-hex-Git-commit>` and `--cwd ~/lanes/repos/macro`, with original root and parent. Current scope is Ubuntu0–3 and existing economical GLM/MiniMax/Qwen routes; other hosts/modes fail closed. The controller checks original selection and lease as normal; **inside the incumbent physical `LaneLease` and before worker START**, the host calls the **exact reviewed Macro helper Git blob `620927823770362b5c1d1e0dec6584612624d848`**, requiring an unoccupied new run checkout. It verifies helper bytes/inode before and after subprocess invocation, original-branch/HEAD, clean sparse Git tree and original worktree registry before rebinding only this worker's CWD. It strips the mint flag from the worker's environment. All old requests retain their original command construction; **no global Git hook, new worker scheduler, extra lease authority or automatic retry** is installed. Inconsistent or uncertain creation preserves the original lease for reconciliation rather than quietly continuing or duplicating the checkout.

**New direct proof (isolated M2, no provider):** The actual `scripts/worktree_sparse.py` source from Macro #9194 with exact Git blob `620927823770362b5c1d1e0dec6584612624d848` was copied into a temporary test donor Git repository. Staged host `_new_macro_workspace` invoked that real helper using **the installed `run_owned_process` implementation**, which successfully minted `lanes/wt/actual-proven` at a pinned commit, preserved `lane/actual-proven`, omitted tracked generated directories, left a clean checkout, and emitted a `mastermind.local_owned_process_receipt.v1` with cleanup proven. A subsequent same-run attempt was refused before modification. Separate staged `_execute` unit mocks proved `physical lease → sparse mint → worker START` order, and that an uncertain mint returns RC76 and calls the original lease's `hold_for_reconciliation` before any provider START. Controller mocked requests proved explicit opt-in forwarding, mode/host/root/parent refusals and untouched legacy argument route. `python3` source compile and `bash -n` passed. Tests ran in temporary directories; no live helper or actual paid worker was installed/dispatched.

**Production blocker beyond source coding:** Macro #9194 remains DRAFT and its reviewed helper is absent from the older installed Ubuntu0/2 donor clones. The true versioned M2 launcher must be source-owner reviewed, the Macro helper installed by its original source workflow, and then one authorized **new** worker must prove exact leased host source/CWD/checkout/result. A test with fake lease or temporary Git repo never substitutes for a real provider and publication/release acceptance. Physical MSI 9950X BIOS TDP/PBO maintenance remains an attended host action.

## Second validation pass: original helper bytes and original launch dry-run

**No live dispatch/install.** In the existing M2 original Fabric staging directory `/tmp/mmx-fabric-new-macro-workspace-20261014-candidate/`, the reviewed source patch has SHA-256 `81965eb9a3b88872664b727b4b86d6e62d92f2ff5c743211e7d4d5c6e957733f`. Exact input M2 source SHA-256 for `fabric_task.py`, `remote_sub.sh`, `remote_sub_exec.py` are `bfa5fcdc3df04d76d6c3b0b2dda2dac17ab4539253ec3ffb86fca4e2c4c13207`, `e2ec7dfe2efa0680b4bf961ac73ce916adf5f1dc90e510f6c8ff6ed50e069deb`, and `c6b4292cdb7d106d5b376587f29276da1550e5eee02268f479abd7ad2ea61189` respectively. All originals were re-hashed to those unchanged preimages before the candidate patch was re-created. No installed files changed.

Additional deterministic fixtures, all with **no provider or real worker**:

- [`test_workspace_integration.py`](tests/test_workspace_integration.py): seven tests now include a helper-modified-during-mint case; both a failed Git create and a helper drift after invocation return **effect_unknown**, reserving the original lease for reconciliation. Duplicate workspace/receipt and code-blob pin rules are enforced.
- [`test_prelaunch_order.py`](tests/test_prelaunch_order.py): actual staged `remote_sub_exec._execute` is invoked under fake physical `LaneLease`; six cases cover legacy GLM, newly pinned GLM, GLM-Codex, MiniMax and Qwen command construction, and mint-uncertain refusal before provider START. `LEASE_ENTERED` precedes `MACRO_SPARSE_MINT_CALLED`, which precedes `PROVIDER_CHILD_START`, and an uncertain mint calls `LEASE_EFFECT_UNKNOWN_HELD` without START. Legacy command construction remains unchanged.
- [`test_controller_request.py`](tests/test_controller_request.py): original request router and `remote_sub.sh` CLI argument routing are intercepted before provider invocation. Invalid SHA, CWD, original root/parent, host/model and artifact mode fail closed.
- [`test_actual_macro_mint.py`](tests/test_actual_macro_mint.py): actual reviewed Macro helper blob `620927823770362b5c1d1e0dec6584612624d848` was placed under an isolated original-path Git fixture on M2 and launched through the **real installed `run_owned_process`**, generating a genuine proof-bearing `mastermind.local_owned_process_receipt.v1`, a clean sparse `lane/<id>` checkout at pinned HEAD, no checked-out generated heavy files, and same-run duplicate refusal. The fixture's SHA/checkout are ephemeral test artifacts, not production host source.
- [`test_launcher_dryrun.py`](tests/test_launcher_dryrun.py): the exact staged Bash launcher completed an opt-in positive `--dry-run` using **`/usr/bin/false` for SSH/SCP/rsync**, and a malformed-commit negative test returned RC78 before lease. The positive path emitted only described launch, provider and artifact operations; no network worker dispatch occurred.

The Macro provider helper's own source PR #9194 still has **102 passing real-Git safety tests** and remains Draft. Its latest hosted CI is independent of these M2 tests and must be read at its exact head; source drift (including a newer Macro helper blob after original owner updates), any original launch owner collision, and review/draft release protection are real gates. Do not treat the tested M2 source candidate as installed in the real immutable `support-releases` generation or permit direct Git mint by a worker as an authenticated workspace grant.
