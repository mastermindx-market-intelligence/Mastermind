# Run-bound canonical stdout for new Macro Fabric workers

**Status:** source-only draft, NOT INSTALLED, NO LIVE CANARY, NO AUTO-ACCEPTANCE.

## Observed defect
The installed controller supports a caller-selected `remote_sub.sh --out`, but its
`fabric_task.py` status/result/acceptance reader observes only the exact
`<ext>/lanes/<run-id>.remote.stdout` path. A bounded recent census found 64
of 69 terminal rc0 sparse-Macro runs used custom output paths without that
canonical file. This is *visibility* evidence, not evidence of accepted work.
No historical result was rewritten, no run was replayed or accepted.

## Tested correction
This candidate patches exactly two incumbent files, preserving the controller,
provider and original parent contracts. For **only** a new explicitly minted
Macro worktree with observed worker rc0:

1. Refuse pre-existing custom/canonical destinations *before* leasing a worker.
2. Transfer stdout into a unique private same-directory capture, not a fixed
   output filename; reject capture setup or transfer failures.
3. Reopen the captured regular file through a verified directory descriptor,
   check owner/inode/size/stability, chmod private, then publish it at the
   per-run canonical filename with an exclusive atomic link. Never overwrite.
   A capture rejected after transfer remains for original-run reconciliation.
4. If caller supplied custom `--out`, copy from that **already verified
   canonical result** into the requested destination, under its own directory
   descriptor with exclusive creation. Never overwrite another run's output.
   Preserve the canonical bytes if custom publication fails; mark the controller
   result unavailable instead of silently claiming successful delivery.
5. A default canonical output, a nonzero worker, and non-Macro workers retain
   their existing delivery semantics. A worker result becoming visible is
   **not** acceptance, lease settlement, deletion, or publication authority.

The two-step canonical-first approach closes the cross-run collision where
two worker IDs select the same custom filename. It additionally removes the
fixed-canonical rsync symlink/overwrite race after the initial preflight check.
Both file publications use no-replace directory-relative linking.

No scheduler, retry, credential, model, host, approval, or GC component added.

## Verification
Original on-M2 sources had the exact GitHub blobs and SHA256 checks recorded
in `SOURCE_MANIFEST.json`; the source revision was protected Mastermind
`2b3429d9aca0d539e7ac2b097a199fb86de2d329`. The combined patch passes
`git apply --check` and produces exact candidate bytes from those preimages.

Inside the isolated M2 candidate `~/lanes/fabric_stdout_canonical_fix_20261020/ext`:

```sh
bash -n remote_sub.sh
python3 -m py_compile remote_sub_helpers.py
python3 -m pytest -q tests/test_macro_result_canonical.py \
  tests/test_fabric_task.py tests/test_remote_sub.py
```

**74 passed**; includes canonical promotion, same-run collision, symlink
refusal, cross-worker custom collision, private-file custody, no autoaccept,
default/non-Macro preservation, prelaunch refusal and incumbent regressions.
This is isolated offline proof, not CI, merge, install, provider-call, or
production acceptance.

## Review and release boundary
Original Fabric source publisher must verify current source pin, writer/lease
and no effect-unknown collision, independently review the patch, publish through
the existing guarded path, run hosted CI, and carry out a **fresh, admitted
new-Macro worker canary** with custom output. Canary must prove exact-run
canonical result visibility, unchanged custom output, no acceptance before
original-parent review, and successful guarded reclaim only after explicit
acceptance. Do not backfill the 64 historical runs by inference.

Existing Mastermind #1651 draft PR is the single source carrier. Earlier
version in the same branch is superseded by this canonical-first candidate.
The Macro repository push guard is separate and remains untouched. Sparse
creation PR #9194 was already merged; do not redo it or add another GC plane.
