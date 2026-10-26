# H1 Linux test-platform qualification — exact #1847 source-only repair

**Status:** CI fixture correction, not host/provider/initializer approval. Current protected
source prerequisite `master@bb85b429f2ffffd38408080ce4df7d6378c34100`;
original #1847 repair base `bdcad338796111b7c0c6d670b4d7a4fd217d52d0`.

## Observed falsifier

Hosted `ubuntu-latest` job 121181466977, CI 40197393494, failed the real
`test_actual_nested_initializer_private_package_context_and_wire` at the
compiled child. The allowlisted v2 diagnostic says `InitializerCommitmentRefused`,
`BOOTSTRAP`, `HOME_ANCESTOR`, `DEFAULT`, at `run_bootstrap->pin->no_acl->refuse`.
This is an intended strict refusal: a POSIX default ACL on an ancestor of the
hosted account HOME is not an eligible execution environment. No private path,
token or ACL value needs to be displayed to establish the failure.

Read-only physical Linux metadata checks on ubuntu0, ubuntu1 and ubuntu2 found
ABSENT access/default ACLs at account HOME, its ancestor and `/`; a qualified
Linux account can exist. No existing account, ACL, credential or lane was changed.

## Source-only correction

1. The hosted test's **read-only real HOME ancestry** classifier determines
   fixture eligibility *before* the first observer, because an ACL-bearing
   fixture can be refused by that earlier observer (not necessarily the final
   compiled child). Any present ACL means the hosted fixture is an explicit
   `SKIP`, **not a positive runtime receipt**. Unsupported metadata errors
   remain hard failures. If the host is ACL-free, the entire original real
   observer/compiled-child journey remains mandatory, and any nonzero return
   is a hard failure. The required isolated step below cannot be skipped.
2. A **new required job step in the same pytest shard 2**, not optional,
   runs the original positive Linux real process/observer path in a disposable
   container with a fresh non-root account and no HOME-ancestor default ACL.
   The container has read-only source, no network, all caps dropped, no new
   privileges, read-only root filesystem, and only isolated HOME and `/tmp`
   tmpfs write targets. Its Python distribution remains an actual, root-owned
   CPython 3.12 image, not a monkeypatched observer or ACL check.
3. Ubuntu's Python package adds two administrative startup *symlinks* that
   the strict normal-profile initializer independently rejects. The disposable
   test image materializes their exact targets as root-owned **regular files**,
   checks SHA equality, then runs under its non-root account. This modifies
   test-image bytes only, never host `/usr`, private data or production guard.
   No `setfacl`, source runtime patch, fake `pwd`, fake Python status or stubbed
   credential/observer is used.
4. The existing workflow contract test now requires this step before the
   full shard, forbids `continue-on-error`, and checks source/profile isolation.

## Bounded real OS experiment (not CI acceptance)

On authorized Ubuntu0, a disposable `ubuntu:24.04` Python3.12/pytest image
with the two root-owned startup files materialized and a `uid=1555` non-root
fixture was exercised with all capabilities dropped, no network and read-only
source. The **unmodified pre-repair #1847 test source** completed its real
Linux private-package/initializer/getpath/observer process and output
`1 passed in 0.86s` with an `ASSERTIONS_COMPLETED` notice; no provider worker,
real credential, production launch or remote worker effect. The initial
unqualified image correctly refused two Python startup symlinks at
`_require_startup_entry` and was repaired inside the disposable image.

An adversarial negative-only disposable image with an actual POSIX DEFAULT
ACL on its private `/home` tmpfs demonstrated an earlier
`FINAL_OBSERVER_REFUSAL` before the final compiled child; an exit78-only
classifier at the final child would miss this legitimate path. The source
branch now rejects that ineligible test substrate *before* the observer,
without altering production ACL checks. Only the isolated real positive
step is accepted as a CI positive.

The actual GitHub Actions result on this PR's *new exact head* and separate
nonauthor source review are still owed. A compliant disposable positive is
**not** an actual paid-Fabric H1 remote-host acceptance/worker START.

## Do-not-merge boundaries

`candidate/paid_initializer.py` `no_acl` and its Root/file/FD/identity
requirements are unchanged. #1847 stays Draft and unreleased until hosted
current-head checks, independent review, and accepted H1 release gates.
The #1836 97-member host-pull source and already-selected M2 native seq23
are separate owners; this change does not publish, select, restart, merge,
qualify providers, retry a refused run or change an ACL on any live host.
