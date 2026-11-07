# Original Fabric: retain the host process receipt for new sparse worktrees

**Source date:** October 16, 2026. **State:** source-only repair. **Not installed, merged, or authorized to delete a worker checkout.**

## Observed live gap

The existing M2 `remote_sub.sh` fetches `~/lanes/ext/lanes/<run>.process.jsonl` into its original `LOG_DIR` following worker completion, sets `RECEIPT_SAVED=1`, and deliberately deletes the **host** copy in the same post-delivery cleanup as remote stdout. This is correct for legacy workers but conflicts with the **separate, not-yet-installed original Fabric accepted-worktree reclaim helper**, whose `_receipt()` function requires the exact host worker and mint process receipts to prove the physical owned process has settled before it will invoke GC.

This is not a synthetic assumption: the original accepted worker `opus-sparse-w3-20261015` on Ubuntu 2 has terminal `rc=0`, deterministic `ACCEPTED`, verified original root/parent, and a clean sparse `lane/opus-sparse-w3-20261015` worktree. Its mint receipt remains under `~/lanes/ext/lanes`, but the worker process receipt is absent on that host. The existing read-only `reclaim-plan` succeeds, yet host reclaim would correctly refuse. Its source commit `5fcd83449b8e8ca00714d5fd5d6bdc85e0cb1bfa` is not yet an ancestor of host `origin/main`; this checkout is **not** safe to remove independently of the missing receipt.

## Minimal original-owner change

The additive `FABRIC_SPARSE_PROCESS_RECEIPT_RETENTION_20261016.patch` changes **only** the original transport `remote_sub.sh`:

- For an explicitly **new sparse Macro worktree** (`NEW_MACRO_COMMIT` nonempty) **and only after** the process receipt was copied successfully to M2 (`RECEIPT_SAVED=1`), keep the existing original 0600 host `.process.jsonl`. Emit `HOST_PROCESS_RECEIPT_RETAINED` and an explicit `host_receipt_retained=1` on the existing `REMOTE_CLEANED` line.
- Every legacy worker with `NEW_MACRO_COMMIT` empty still deletes its host process receipt after successful M2 copy, as before. Unsaved/uncertain receipts are not treated as valid or cleaned by this change.
- Remote stdout, RC file, usage receipt, original lease, terminal/result ownership, support generation and all physical thermal/disk admission are unchanged. No new lifecycle, cleanup daemon, watcher, ledger, background task or GC invocation.

**Exact current-installed source preimage:** M2 `remote_sub.sh` SHA-256 `fdb50974e37852c8024135ddf4bf021e6c6a67d1a0418cd5675cc24dc4ad5a17`. **Staged postimage:** `c30482d6c4421f49511f4f276a30f9439c2150912076adf32e106d76a82493e2`. **Patch:** `cee62cdaf6abdd460545486a6a33aa33e43027d5eff97c14ac119ff801edcb41` (SHA-256). It was applied **with `patch --fuzz=0`** to a private byte-exact preimage and verified byte-for-byte against the staged postimage; `bash -n` passed.

**Tests:** Five scoped Bash regression cases under `tests/test_fabric_sparse_receipt_retention_20261016.py`: saved/unsaved new sparse, saved/unsaved legacy, and hunk/source scope checks. No SSH/provider calls or host worktree deletions are made. The current exact [Macro GC PR #9430](https://github.com/mastermindx-market-intelligence/macro/pull/9430) head `02b54676c0e6e55f64716eae4d595e94e0bb8b2b` separately passed **66/66** GC + liveness tests on M2 and Ubuntu 3 with Git source blob `edaee3dec0fb4041d69edae24f39836699971c67`; this does not install or approve that PR.

## Release and custody

Original Fabric source owner must revalidate the **exact installed preimage** and current code-review/CI gates before applying. Do not replay superseded combined patches or overwrite concurrently running `remote_sub.sh` sessions. Existing Ubuntu GC timers stay report-only. The newer source GC helper hash `edaee3dec0fb4041d69edae24f39836699971c67` supersedes the older `0665ea...` staging pin and will require a separately reviewed support generation. The earlier platform refusal concerning editing the original GC packaging script remains held—this patch is a distinct, separately tested receipt-preservation fix, not a retry or bypass of that refused operation.

A complete end-to-end release still requires current Git source review, original M2 host-support generation admission, original accepted result, physical worker/mint settlement, publication of the exact HEAD into trusted upstream `main`, fresh host/source/lease/cwd/FD checks, and **one canary** verifying only its exact accepted worktree is reclaimed, sibling intact. **No existing or unpublished worker checkout is in scope for deletion.**
