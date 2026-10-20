# Canonical result binding for new Macro Fabric worktrees

Status: SOURCE-ONLY CANDIDATE / NOT INSTALLED / NO LIVE ACCEPTANCE PROOF

## Problem and evidence

The installed `remote_sub.sh` accepts an explicit `--out` destination.
The installed `fabric_task.py` reads a *different*, exact retained-result
path: `<ext>/lanes/<run-id>.remote.stdout`. Both current M2 source files are
byte-identical to their inspected source copies in the protected Mastermind
repository at commit `2b3429d9aca0d539e7ac2b097a199fb86de2d329`.

In a bounded recent Macro sparse-worker log audit, 69 runs were terminal
`rc=0`; 64 used custom output basenames and lacked the canonical result,
four had canonical outputs and accepted status, and one canonical result was
not accepted. These are *status/visibility* findings, not worker-result
quality or acceptance determinations. No original run was replayed or accepted.

## Change

`canonical-result-binding.patch` applies to the **existing** M2 controller
files `remote_sub.sh` and `remote_sub_helpers.py` only after exact source
preimage validation. It does not install a new worker runtime or collector.

For an explicitly minted Macro sparse checkout:

1. Refuse a previously existing custom output file or canonical result before
   provider leasing, including symlink collisions.
2. On an observed successful remote worker exit and successful rsync to a
   *custom* `--out` path, retain unchanged original output and mirror its
   exact bytes into the canonical result path with a private, atomic,
   exclusive create. No overwrite or inferred acceptance.
3. Require source owner/type, single link, non-group/world-writable mode,
   stable identity, bounded length <= 8,388,608 bytes, and an owned,
   non-group/world-writable canonical `lanes` directory. A failed check
   produces `RESULT_UNAVAILABLE` / controller rc=76, never a silent rc=0.
4. Preserve the existing behavior for default canonical stdout, non-Macro
   work, nonzero worker exits, and effect-unknown operations.

This is **artifact visibility only**. It cannot approve a worker result,
release a lease, infer an original parent, or authorize workspace deletion.
Existing accepted-run release, Git source publication, human-session custody,
and stash protections remain controlling.

## Reproduction and verification

The original two GitHub source blobs and exact SHA256 hashes are recorded in
`SOURCE_MANIFEST.json`. The combined patch was verified in a disposable
source directory using `git apply --check`, applied, then both resulting
files were compared byte-for-byte against the independently tested candidate.

The isolated M2 candidate at:
`~/lanes/fabric_stdout_canonical_fix_20261020/ext`
ran:

```sh
bash -n remote_sub.sh
python3 -m py_compile remote_sub_helpers.py
python3 -m pytest -q --basetemp='../isolated-test-tmp-final-20261020' \
  tests/test_macro_result_canonical.py \
  tests/test_fabric_task.py tests/test_remote_sub.py
```

Result: **70 passed**. Tests cover successful custom-output binding, no
automatic acceptance, original-byte preservation, collisions, symlinks,
hardlinks, writable files and directories, size limits, unavailable source,
invalid IDs, actual controller branch semantics, fail-closed mirror errors,
prelaunch refusal before transport, and incumbent controller regressions.
This is local hermetic evidence only, not hosted CI or a live worker canary.

## Held publication and recovery gates

This package does not change the live M2 `ext/` directory, Git branch heads
used by workers, or original Fabric run records. The separate Macro repository
has a deliberate `remote.origin.pushurl=/nonexistent/fabric-lane-push-disabled`;
do not alter or bypass that restriction as part of this change.

The existing authorized Mastermind source publisher must verify no concurrent
source lease/collision, compare exact source hashes to the manifest, review the
patch and tests, publish through its normal signed/guarded path and exercise a
**fresh admitted real new-Macro worker canary** using a custom output destination.
Proof requires the same run to be terminal rc0, custom output unchanged, canonical
`fabric_task status` result_available true, acceptance still false before an
authorized parent review, and successful guarded release only **after** that
review. No backfill of the 64 historical runs without their original parent's
retained exact output and separate provenance review.

DO_NOT_REDO: PR #9194 sparse creation was already merged; do not add another
sweeper, queue, provider fallback, or permission bypass.
