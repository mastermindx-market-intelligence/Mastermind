# CF2-H0 Final-Review Safety Closure Continuation

> **Execution method:** Continue only on the existing
> `codex/cf2-h0-source-closure-20260827` carrier. Use RED-first TDD for every finding, commission
> one sequential implementer per task, and commission a fresh independent reviewer after the final
> task. No root/native operation, publication, merge, P0, OAuth, service, provider, worker, routing,
> Slack Agent Relay, WP-1/WP-2/WP-TW1, C1, Wake, K3-D, or B1 action belongs to these tasks.

**Goal:** Close the six independently reproduced Critical/Important residuals from the one allowed
final-review continuation wave without changing the accepted CF2-H0 product or lifecycle
architecture.

**Carrier identity at continuation:**

- Worktree: `/Users/chriswong/Documents/Cluade/Mastermind-h0-source-closure-20260827`
- Branch: `codex/cf2-h0-source-closure-20260827`
- Reconciled head: `bb40b24838b0633e154d96db5074d517d644072f`
- Protected master/Skillpack pin: `af43f356f4f7f34cb3514d1d1099b50444af8487`
- Preserved H0 topology/release commit: `e4e44867ace335ac9208a3990a10c163e199492d`
- Preserved H0 release tree: `ee1b95af3341a49151890cec1a6a31997f632aec`

**Architecture boundary:** Keep one existing H0 lock, intent, receipt, archive, installed source,
generation authority, repair entry point, and exact-commit carrier. The continuation may strengthen
read/authentication capabilities and the disposable bootstrap, but it may not introduce another
daemon, database, lifecycle, queue, state store, receipt type, retry/failover plane, or release
authority.

## Task 1: Restore v1 recovery compatibility and complete descriptor security-state checks

**Files:**

- Modify: `ops/executive_os/capacity_host_artifacts.py`
- Modify: `tests/test_capacity_host_artifacts.py`

**Observable mission:** A regular file cannot change any accepted security field during a
descriptor read, every retained traversal ancestor obeys the frozen security law, and an exact
pre-change recovery-v1 intent/receipt replays without identity migration.

- [ ] **Step 1: Add discriminating RED regressions**

Add tests that fail on the current head for:

1. post-read drift in regular-file type/mode, UID, GID, link count, and BSD flags;
2. nonzero flags, wrong UID/GID/mode/device/link state, ACLs, and xattrs on a true traversal-only
   ancestor both at open and revalidation;
3. exact pre-`1f1c290...` recovery-v1 digest replay after a partial move;
4. idempotent replay of an already completed pre-change recovery-v1 receipt; and
5. unchanged legacy-v1 canonical digest rows with a separate fail-closed nonzero-flags check.

The RED must demonstrate the prohibited acceptance or replay refusal, not merely inspect source
strings.

- [ ] **Step 2: Make one complete descriptor state authoritative**

Use one complete regular-file before/after tuple containing device, inode, file type/mode, UID,
GID, link count, flags, size, mtime, and ctime. Re-run the approved ACL/xattr/flags descriptor law
after content reads. Apply the complete immutable-ancestor law from retained `/` through the fixed
system root. Traversal-only macOS ancestors may carry platform-managed flags and xattr names such
as `com.apple.rootless`; freeze their exact identity/security state and exact xattr-name set,
forbid extended ACLs, and refuse drift. Their numeric link counts are shared OS state and may change
under unrelated temp-directory churn, so require `nlink >= 1` rather than freezing that number.
The fixed H0 system root retains a complete frozen directory state including link count and times,
plus the literal zero-flags and approved-only-xattrs law. H0-owned secured/transition objects keep
their existing zero-flags and phase-derived link-count law so authorized directory renames do not
create false drift.

- [ ] **Step 3: Preserve the frozen recovery-v1 byte identity**

Keep zero-flags refusal as a non-identity security validation, but remove `flags` from only the
legacy pathname `_closed_tree_digest()` canonical rows. Keep `flags: 0` in the new descriptor-based
source-repair v2 digest. Do not bump, dual-write, reinterpret, rewrite, or auto-migrate the existing
recovery-v1 intent or receipt.

- [ ] **Step 4: Prove GREEN and commit the task**

Run the new exact tests, the existing recovery/crash matrix, the complete
`tests/test_capacity_host_artifacts.py`, Apple Python compilation, and `git diff --check`. Commit
only after the RED failure and GREEN output are both recorded in the continuation workspace.

## Task 2: Authenticate the inert e4 release and make retained descriptors the semantic read plane

**Files:**

- Modify: `ops/executive_os/capacity_host_artifacts.py`
- Modify: `tests/test_capacity_host_artifacts.py`
- Modify only if the frozen law needs precision: `docs/superpowers/specs/2026-08-27-executive-capacity-cf2-h0-source-closure-repair-design.md`

**Observable mission:** Coordinated payload-plus-manifest substitution, basename swaps, and
restored namespace swaps cannot influence an accepted preserved-H0 observation; installed target
code remains inert.

- [ ] **Step 1: Add discriminating RED regressions**

Add behavior tests that fail on the current head for:

1. an arbitrary release plus a self-authored internally matching manifest under the exact e4
   basename;
2. a valid manifest shape carrying the wrong trusted e4 tree;
3. an exact release-basename swap after the root descriptor is retained;
4. a restored pathname swap surrounding a semantic read;
5. a preserved generation/runtime/topology/rollback/legacy semantic read attempting to reopen a
   retained pathname; and
6. an absolute topology path that skips component-by-component opening from a retained root.

Retain the existing sentinel proof that no installed `release_manifest.py` payload executes.

- [ ] **Step 2: Add one reviewed release trust root**

Pin the exact protected e4 tree `ee1b95af3341a49151890cec1a6a31997f632aec` and one independently
derived SHA-256 of the exact canonical e4 manifest bytes in the reviewed repair carrier. Require
canonical manifest framing, exact commit, exact tree, and exact trusted manifest digest before
using any target-owned entries. The authenticated manifest remains the single inventory root; do
not add a parallel installed-release database or second manifest.

- [ ] **Step 3: Rebind the release basename to its retained parent**

Freeze the parent-relative name relation when opening the release root, compare it immediately to
the retained root descriptor, and require the same complete relation/state at final acceptance.
Do not final-reopen release content by pathname.

- [ ] **Step 4: Use the existing retained graph as the only semantic capability**

Pass retained runtime, generation, archive, topology, rollback, release, telemetry, and legacy
views into the preserved-invariant verifier. Replace scoped `Path.read_bytes`, `Path.rglob`,
`Path.lstat`, and pathname `sha256_file` calls with descriptor-relative inventory/read/hash helpers
on those views. Open absolute evidence component-by-component from a retained `/` descriptor.
Revalidate full object state and parent relation after each semantic read and at final acceptance.
Do not build a filesystem event/audit plane: a transient swap is irrelevant once it cannot affect
accepted bytes and the final basename relation is exact.

- [ ] **Step 5: Prove GREEN and commit the task**

Run the new selectors, all preserved-invariant and source-repair tests, the complete
`tests/test_capacity_host_artifacts.py`, Apple Python compilation, and `git diff --check`. Record
the RED and GREEN receipts before committing.

## Task 3: Replace the privileged heredoc with an authenticated disposable carrier bootstrap

**Files:**

- Modify: `ops/executive_os/HOST_PREREQUISITES.md`
- Modify: `ops/executive_os/capacity_host_artifacts.py`
- Modify: `tests/test_capacity_host_artifacts.py`
- Modify: `tests/test_executive_capacity_source_closure_repair.py`
- Add only if required for a testable fixed command carrier: `ops/executive_os/bootstrap-capacity-source-closure.sh`
- Modify: `docs/superpowers/specs/2026-08-27-executive-capacity-cf2-h0-source-closure-repair-design.md`

**Observable mission:** Before a reviewed root-created exact-blob carrier is authenticated, root
executes only fixed macOS system binaries with explicit argv; operator program text, checkout
inodes, and carrier bytes are never interpreted. The disposable root namespace is removed on every
success/refusal/signal path.

- [ ] **Step 1: Add discriminating RED regressions**

Add behavior tests that fail on the current head for:

1. invalid bundle plus operator stdin/program text cannot create a sentinel before authentication;
2. a symlink bundle refuses without changing target bytes, inode, UID/GID, mode, flags, ACLs, or
   xattrs;
3. metadata-valid carrier files with one wrong byte refuse against a real fixture Git commit;
4. exact fixture Git blobs and modes pass;
5. the root namespace is absent after a pre-auth refusal and after three-pass success; and
6. cleanup failure cannot emit or return a clean success.

Tests must exercise the command/carrier behavior. A substring assertion alone is insufficient.

- [ ] **Step 2: Remove the privileged interpreter bootstrap**

Remove root `/bin/bash -s`, `sh -c`, interpreter `-c`, and any root execution of operator-supplied
stdin. If a checked-in bootstrap is needed, it runs only as the unprivileged operator and invokes
an explicit allowlist of absolute system-tool argv; root never interprets that file. Authentication
uses a root-created fixed literal namespace, a root-owned copied bundle, closed Git configuration,
the exact expected commit, exact path/mode/blob mapping, and new root-owned carrier inodes before
executing the carrier shell or Python.

The operator bundle is inert input. Reject an initially observed symlink, never preserve a symlink
into the root namespace, never mutate source-path metadata, copy into an exclusive root-owned
regular inode, bind the recorded bundle SHA-256, and revalidate the root-owned destination before
Git consumption. A source race may only cause deterministic refusal; it may not cause mutation or
unreviewed execution.

- [ ] **Step 3: Make exact blob identity part of `verify_repair_carrier()`**

Derive `path -> expected Git mode/blob OID` from the authenticated bare repository at the exact
commit. Before any carrier file is interpreted, hash each retained root-owned file with Git blob
framing and compare it to that mapping. The commit stamp is evidence, not authority. The verifier
must receive a retained authenticated repository view or equivalent trusted blob map and must
reject caller-authored placeholder bytes.

- [ ] **Step 4: Add one exact cleanup lifecycle**

Create the fixed root namespace no-replace; arm cleanup only after successful creation; target only
that literal namespace; run cleanup on success, refusal, HUP, INT, and TERM; preserve the primary
failure status; and convert cleanup failure after otherwise successful repair/two-verifies into a
typed non-success. Refuse an old/preexisting namespace rather than deleting unknown residue.

- [ ] **Step 5: Prove GREEN and commit the task**

Run the new bootstrap/carrier tests, Bash 3.2 syntax coverage, root-script syntax checks, the full
Task 5 test matrix, Apple Python compilation, `scripts/ci_pytest.py --plan-only`, and
`git diff --check`. Record RED and GREEN receipts before committing.

## Task 4: Exact-head adversarial acceptance and release gate

**Files:** no planned implementation edits; any blocker returns to its owning task.

- [ ] **Step 1: Re-pin and prove the exact local head**

Require a clean worktree, current protected master/Skillpack, zero task-path collision, zero
excluded CI tests, the complete frozen pytest matrix, Apple Python compilation, every Bash syntax
check, and `git diff --check origin/master...HEAD`.

- [ ] **Step 2: Commission a fresh independent whole-branch reviewer**

The reviewer must independently attempt coordinated release substitution, retained-path restored
swap, carrier-byte substitution, bundle-symlink mutation, cleanup failure, post-read metadata
drift, ancestor drift, and pre-change recovery-v1 replay. A clean result is required before any
publication.

- [ ] **Step 3: Publish and prove one PR**

Only after local and independent PASS, push this same branch, create one PR, and require hosted
exact-head CI and CodeQL. Re-pin head/base immediately before merge. A green PR is not native H0,
P0, service, provider, or routing proof.

- [ ] **Step 4: Resume the original Task 5 native gate**

Only the protected merge may build the final transport/carrier. Run the one native administrator
ceremony, require its repair sentinel, run two independent verify-only passes, and require the
disposable root namespace absent afterward. Never type, capture, log, or relay the Chairman's
password, OTP, passkey, OAuth code, or credential material. Any exit/mismatch returns to same-
carrier reconciliation; never blind-retry.

- [ ] **Step 5: Stop at H0**

Record exact PR/merge/transport/carrier/repair/two-verify/cleanup identities. Keep CF2-P0 and every
downstream/OAuth/service/provider/worker/routing lane held for its separately gated carrier.
