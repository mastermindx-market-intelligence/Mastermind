# Run-bound canonical stdout for new Macro Fabric workers

**Status: SOURCE_ONLY_NOT_INSTALLED.** This is an inert patch package for the
existing Fabric controller. Source merge does not install it, run a worker,
accept a result, settle a lease, or release a workspace.

## Defect and bounded correction

The original incident record counted 64 of 69 terminal-rc0 sparse-Macro runs
with custom output but no per-run canonical result. That historical visibility
census is not evidence of accepted work. No historical run is backfilled,
replayed, or accepted by this package.

Only an explicitly minted new Macro worktree with observed worker rc0 uses
the existing canonical-first path:

1. Refuse pre-existing custom and canonical destinations before worker leasing.
2. Transfer stdout into a private, unpredictable, same-directory capture.
3. Verify and privatize the capture, then publish the per-run canonical path
   through an exclusive directory-relative link.
4. Derive a caller-selected custom output from the verified canonical result
   using the existing exclusive scratch-and-link path.
5. Keep non-Macro and nonzero-worker delivery behavior and explicit parent
   acceptance unchanged.

The publication-identity correction keeps the verified capture or scratch
descriptor open throughout publication. Immediately after linking, it opens
the retained destination without following symlinks and checks the actual
device/inode, owner, private mode, link count, size, stable metadata and bounded
SHA256 content against that held descriptor and the verified digest. It checks
the temporary name before removing it, fsyncs the directory, then verifies
the retained destination again with its final single-link identity.

Custom-copy failure preserves the original canonical bytes. Cleanup skips a
known replacement of its temporary pathname. No failed verification prints a
success receipt; a destination created before a later verification failure is
unavailable evidence for original-run reconciliation, not permission to retry,
overwrite it, or accept the worker.

These are point-in-time checks. Portable pathname operations do not provide
immunity to an arbitrary same-UID writer after the final observation or between
a pathname check and unlink. Exclusive controller writer/lease custody remains
a runtime gate. Directory anchoring and no-replace linking retain their original
scope; this correction does not create another publisher, reader, queue,
retry, acceptance authority, or cleanup owner.

## Exact source and qualification

The frozen preimages in SOURCE_MANIFEST.json come from protected revision
2b3429d9aca0d539e7ac2b097a199fb86de2d329. Both are still byte-identical at
protected 88d16c0f587b129cf8b8c019cf6ab693eb21226c. The launcher candidate is
unchanged; only the two helper publication functions and two internal checks
change. Every other helper function remains unchanged.

Fresh principal qualification executes the exact helper and test function
bodies in memory against real test-owned temporary files:

- All 13 added cases pass: two ordinary successful publications and eleven
  negative cases covering same-length temporary-name substitution before and
  after link, same-inode content mutation, destination replacement after link
  and during temporary unlink, and custom private-mode enforcement.
- Running the same discriminators against the prior helper exposes ten
  unqualified success receipts and one deletion of a replaced temporary name.
  Both prior ordinary-success controls pass.
- Exact preimage and prior-candidate hashes, helper/test syntax, unchanged
  unrelated helper functions, strict patch reconstruction, and launcher
  bash syntax are checked.

All 22 existing candidate cases are retained, giving 35 total. The existing
hosted gate tests/test_fabric_canonical_result_candidate.py recreates the
reviewed public source closure, verifies preimage hashes, runs git apply
--check, applies the patch, verifies candidate hashes, and executes the full
35-case module. That full package run is pending at source publication; the
exact-head GitHub qualification receipt records its subsequent result.
The earlier 74-test receipt belongs to the previous candidate and is not
carried forward as fresh proof for this correction.

## Source disposition and runtime release boundary

The repaired five-file source package is SELF_REVIEWED for protected GitHub
source publication under the current Chairman assignment and attended-Web
review policy. The source finding in PR1651 comment6649856602 is addressed by
the actual identity/content discriminators and successful controls. No
independent security review is claimed.

Before installation or runtime use, the existing Fabric publisher must still
qualify the installed generation and current preimages, security behavior,
writer/lease custody and absence of uncertain effects; use its existing
guarded rollout; and complete a fresh admitted custom-output worker canary.
That canary must prove the exact run's canonical result availability, intact
custom output and accepted=false until explicit parent review. Guarded
workspace reclaim remains conditional on that acceptance.

The historical 64 runs remain unaccepted and unreplayed. Macro's deliberately
disabled push URL and the existing fleet holds remain untouched. Sparse
minting PR9194 is already merged and must not be duplicated. PR1651 remains
the single source carrier; no installed controller or original worker artifact
is touched by this package or its inert tests.
