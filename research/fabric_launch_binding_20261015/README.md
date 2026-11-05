# Retain original lease identity before an artifact worker launch

The ordinary controller previously retained `LEASE_OK pool=...` but deleted the temporary acquire response during cleanup. An interrupted result could preserve source, process, parent and file evidence while losing the exact lease/account join. The recovered factory-test result demonstrates this gap; its missing historical join remains unknown.

This proposal appends one `LAUNCH_BINDING` record to the existing per-run log before a new ordinary GLM or Qwen artifact worker starts. The controller passes its original acquire response directly. The record includes run/root/parent/host/model/pool, lease/account, packet and support digests. The file and parent directory are flushed and the bytes read back before launch. Existing cleanup remains the sole lease owner.

Only new artifact contracts opt in. Plain packets retain their existing behavior. Unsafe files, mismatched contracts, duplicate bindings, an already launched or uncertain run, concurrent log mutation, or unconfirmed durability prevent launch. This records correlation; it creates no authentication, admission, acceptance, retry or lease-settlement authority. It cannot repair either historical missing lease record.

## Source and validation

`SOURCE_INTAKE.json` pins the installed two-file baseline; `launch-binding.patch` is a zero-context delta for exact-preimage installation (`git apply --unidiff-zero` only after matching both pinned preimages). `candidate/` retains exact candidate files, and `SOURCE_VERIFICATION.json` binds the tested hashes and counts. Tests use installed public dependencies and private disposable test data; they perform no provider, host, lease or ledger operation.

- 30 final focused helper, negative and Bash/CLI checks passed after actual-launch lease/account equality repair.
- Two actual Bash binding-block/CLI tests prove successful recording reaches the launch boundary and invalid acquisition exits78 before it.
- All40 existing remote-controller compatibility checks passed on both baseline and candidate with identical corrected fixture layout.
- The earlier directory-fixture and unsealed-policy fixture failures are retained locally and are not represented as valid regression proof.

The candidate preserves the concurrent installed sparse-worktree/CPU-scope changes. It does not modify adapterfd6b3c31, the user-trusted Stop hook, routing policy, capacities, provider credentials or native service bindings.

The paid Qwen review was consumed once and adjudicated. Its output exceeded the contract bound, so the worker remains NOT_ACCEPTED; the valid actual-launch binding finding was corrected and tested. See `review-adjudication.json`. Installed 2026-10-15T07:42:23Z against the exact intake preimages, helper first and controller second; both installed hashes matched the candidate and 30 installed checks passed. The original useful artifact test build `fabric-1462-reader-contract-tests-01a11e90-v1` is dispatched once; its result and actual launch-binding evidence remain pending. Installation receipt: `/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering/launch-binding-install-20261015/INSTALL.json`. Authenticated native same-parent production acceptance separately depends on the existing #1468/host readiness chain; this patch cannot satisfy it.
