# Routing continuation: priority isolation and integration readiness

Parent: Mastermind PR #1443; original audit operation `fabric-routing-deep-audit-20261013-c2-001`.
Independent source follow-on: `fabric-routing-queue-review-20261014-c2-001`.
Protected procedural pin remains `76576d8680bb70cdb9e1cfe7016aefec0fb3286f`.

**SOURCE FOLLOW-ON PUBLISHED; NOT INSTALLED; FULL ROUTING MISSION INCOMPLETE.**

## New defect fixed in the source candidate

The original broker queue decision returns true immediately on encountering any waiter belonging to the requesting root. A root's urgent waiter can therefore lend its priority/FIFO position to a different, lower-priority sibling request, letting that request jump ahead of higher-priority work from another root.

Example: root A has a queued heal (priority 0); root B has a queued build (priority 1). Root A now requests mechanical work (priority 3). The original decision grants A the next queue turn because it sees A's heal row first. It never compares B's build against the actual mechanical request. Propagating logical `job_class` into the broker, as the first #1443 patch does, does not repair this early-return flaw.

The follow-on changes only the same-root branch of `_front_of_queue`: reuse an existing waiter position only when its priority matches the current request. Otherwise continue comparing the real requested priority with other roots. This preserves same-priority FIFO and genuine new urgent work while preventing borrowed urgency. It does not add capacity, change a root, modify account selection, reinterpret transport identity, or create a queue.

## Discriminating verification

The final independent suite executes the actual follow-on patch against a source-backed decision-method excerpt:

- Before the queue decision repair: **9 failed / 22 passed**.
- Patched decision and artifact: **31 passed / 0 failed**.
- The suite includes **3,750 exhaustive combinations** of three roots' priorities, arrival ordering and current-request priority, compared against a separate priority/FIFO reference calculation. These combinations are inside the 31-test suite, not 3,750 additional pytest tests.
- Positive cases preserve no-waiter availability, original same-priority FIFO, genuine higher-priority preemption, another root's higher-priority protection, logical remote work classification and no same-root-only deadlock.
- An additional source-shape test reproduced and corrected a packaging defect: the initial hunk matched a dedented excerpt but not a real nested Broker method. The final patch retains method indentation and applies with 740 unrelated preceding source lines. The superseded initial patch was never installed.

Runnable repository test: `tests/test_native_fabric_queue_priority_isolation.py`.
Source package: `ops/native_fabric/routing_audit_20261013/queue_priority/`.

This is **function-level source verification**, not an end-to-end native broker test. The fixture is explicitly an excerpt, not a complete installed-file snapshot. Its method body comes from immutable archived source at `c2168fb0656688c11c386e83b26d0dc778bb4be4`, blob `3a8122c283dd4d37a7d80387dad7f2533c97c64b`; the signature and priority call include the already-published #1443 logical-class change. The test adds a synthetic class wrapper to retain native indentation. It imports no installed Fabric module, contacts no host/provider and opens no live lease database. It is separate from, and does not rerun or replace, the previously blocked original GLM-fixture/legacy regression actions.

The follow-on must apply after `logical_job_priority.patch`; its required complete broker candidate preimage is SHA256 `d3a8dfbcf01e86f0551435ab3c37caf1090376290b9eb99ea5bd3ee9f0f73b5a`. Its complete postimage must still be established by the incumbent source integrator. Final follow-on patch SHA256: `c0e33c5fbf69e9a83c951ee337629b891acd70e8b1bdbed293521a645cf8a351`. Published patch Git blob: `5eee68054ec5ab2feb8e25243d4cfec86febd255`; test Git blob: `ab5f66cec4aea556b0724871630f40b98cb8f7b4`. Those blobs match the locally verified bytes.

## Original verification remains separate and held

The original two #1443 patches still have their recorded **49 passed / 1 failed** result. The failing GLM fixture, incomplete original legacy regression and original action refusals have not been erased or relabeled by these new tests. Do not add the counts together and claim an 80-test native green suite. Independent review, full native regression, installed-version reconciliation and production original-parent proof remain unfulfilled.

The initial #1443 hosted CI run `38497924286`, for original head `1f3deb3687aed271e4c0c9f021a15e7758679460`, completed successfully. That result does not cover later commits and did not execute the original inert native reproducer. The new runnable repository test requires its own exact-head hosted observation.

## Current integration evidence, not three independent installations

Fresh GitHub source inspection found a useful common preimage:

| Candidate | Exact inspected head | Source contribution |
|---|---|---|
| #1441 V4 | `d9454abcbb5784751adff7dcf0268b43ebe3c9b8` | Cache-only advisory quota reads and protection against false pool-wide GLM exhaustion from incomplete account observations |
| #1365 | `4c27a8d3a4dab635b5301e3f8fda84576b711b9f` | Exact model/host interface, paired quota windows and claim-time GLM account expiry preference |
| Original #1443 | `1f3deb3687aed271e4c0c9f021a15e7758679460` | Logical work priority propagation and cross-provider explicit-complexity invariants |

All three candidate records name the same `pick.py` preimage, `c2d5420bbaf5b06b47788fecd999b7f920f60fe5f25154f2ab8a22afa2d58b29`. The #1365 and #1443 broker preimages both equal `a72bc031ddb81e559e0cf48fcbf824a959edfcf445c1d3d2d89348c3c66c6f0c`. #1441's usage-ledger preimage matches the audit's `d5785307d39d79eaa6dbdba2bdbfc527c9beb06cfeb55d395797b3954ccff0a6`.

The inspected #1441 picker hunks affect quota observation calls around lines 235, 285, 1469 and 1480; original #1443 complexity hunks affect the economic guard around lines 2229 and 2350. This is textual separation, not integrated test proof. The #1365 expiry helper is adjacent to queue code and must be retained when applying the queue follow-on. Its newest manifest describes seven patches and 366 integrated tests; its older PR-body six-patch/360-test paragraph is not the latest artifact record. None is a live adoption receipt.

**Integration implication:** produce one reviewed compatible support generation, not three blind sequential applications of complete-file manifests that all expect the original hashes. Preserve the newest host/account helper, the expiry allocator, the cache-only call contracts, original root/account/model admission and effect fences. Record combined output hashes and verify broker/launcher flag compatibility. Current source-owner, review and release gates still apply; this report neither takes the installed writer nor asks another actor to perform a refused action.

## Remaining queue and model-selection work

This patch does not solve the broader `(root,pool)` waiter-row conflation, model/account head-of-line blocking, first-fit concentration, unused scoring controls, normalized account utilization or cold-start quality confidence. Those findings remain explicit. Request-level demand needs conserved root accounting and compatibility work in the existing broker; it must not be improvised by minting roots or introducing another queue. The existing #1365/#1441/#1248/#1254 ownership and separate refusals remain intact.

## Effect and recovery boundary

The first host command in this continuation was rejected before dispatch by the platform safety checks. It requested host/workspace/source inspection; it did not run. The same action was not repackaged, retried, or moved to another host/tool. No running Fabric file was read through an alternative path or changed by this continuation.

Independent permitted work instead reviewed immutable GitHub source, implemented the additional queue-decision repair against a local source excerpt, and added new source artifacts through GitHub on the existing PR branch. The previous original host fixture/test/ledger and legacy-preparation denials remain attached to their original actions. Nothing here clears those restrictions or production installation gates.

**Source carrier note:** these new additions were committed through GitHub, not pushed from the managed M2 worktree. The last verified M2 source head remains `1f3deb3687aed271e4c0c9f021a15e7758679460`; it must not be assumed synchronized or used to overwrite this branch. The new source addition has known successful GitHub commit receipts, with no uncertain effect. Keep the same PR and branch; no replacement worker, installation, service restart, credentials, live quota/lease change or autonomous watcher was created.

Next useful actions are exact-source independent review and, only when its real action/custody gates permit, incumbent integration and native verification. Preserve the separately blocked original operations. A current GitHub source read and a source test do not prove restored host permission, current installed hashes, a started worker, or actual original-parent acceptance.
