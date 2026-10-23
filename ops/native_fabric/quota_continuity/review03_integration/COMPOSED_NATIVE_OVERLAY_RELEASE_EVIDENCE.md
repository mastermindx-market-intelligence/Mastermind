# Deferred review-03 native overlay and explicit closed-generation proof

**Authority:** source-only evidence for the existing native Fabric owner. No install, publication, owner change, merge, lease mutation or Fabric terminal readback is proved here. All operations described below used a disposable copy.

## Correct target

The native rollout has two distinct code surfaces:
- `source/fabric_task.py` is an **immutable installed preimage**, SHA256 `8f28799dc4f2d0b815fa467dab1dee5c5a9781d220199a5358be49773a74b686`. It must continue to match `rollout/native-preimages.json`.
- `candidate/fabric_task.py` is the **reviewable proposed code overlay** chosen first by `rollout/build_review_stage.py`, which verifies the original source preimage separately. A native source hook must integrate into the **candidate**, not the source preimage.

Mastermind Draft PR #1648 (original writer `chriswong6031-creator`) accidentally edits `source/fabric_task.py` for the remote cwd default instead of `candidate/fabric_task.py`, producing its hosted `installed preimage mismatch: fabric_task.py` error. The exact owner correction was posted to #1648's existing comment: https://github.com/mastermindx-market-intelligence/Mastermind/pull/1648#issuecomment-6355823350 . The original #1648 writer must reconcile and own that correction; this PR does **not** edit either shared `fabric_task.py` path.

## Deferred exact-target patches

- `review03-into-candidate-fabric_task.patch`: reviewed original run/root `EFFECT_UNKNOWN` status hook, read-only guarded check, proof-SHA-gated same-run reconciliation CLI, against protected `candidate/fabric_task.py`; unlike the older historical source-preimage patch, this targets the actual **candidate**.
- `review03-include-native-generation.patch`: adds the **new** `native_watchlist_review03_reconcile.py` to the existing explicit `rollout/build_review_stage.py` `ADDITIONS` closed set. Never bypass its exact `BASE_FILES` preimage checks or silently insert unlisted files.
- `deferred_tests/review03_integration_contract.py.txt`: 15 source-only adapter integration tests; remains non-collected until the original owner lawfully lands the candidate patch.

Both patches are **deferred source artifacts**. They do not modify the installed native owner and must not be applied to a production service or owner branch without correct source custody.

## Actual isolated validation

At protected Mastermind pin `d2c25ea2653e23782b675f3606ca969196b3f476` the following were run entirely in a disposable owner-only directory:

1. Copy the reviewed native source subtree with immutable source preimage unchanged.
2. Apply both `git apply` patches to the copy (each returned rc 0).
3. Simulate #1648's **intended** remote cwd overlay change in the disposable **candidate only** (`--cwd` default `"~"`), retaining the immutable source SHA256 unchanged.
4. Run `python3 rollout/build_review_stage.py --output <scratch-artifacts>`, which verified every fixed preimage and emitted **86 native code files**, up from the original 85.
5. Inspect the produced exact native manifest: includes `ext/native_watchlist_review03_reconcile.py` and an overlay `ext/fabric_task.py` importing it and using receiver-home cwd.

Observed detached-stage receipt:
- native files: **86**
- manifest SHA256: `f73a11459b288b35982165404dbbea485cee162e09498fd249c2f57aa71c4815`
- source inventory SHA256: `210400f2fc2196dc36e0fb5f9ccb6d8719b5cefe91063552e08dba5c0cf8e058`
- staged reconciler SHA256: `714bba2db6a89c28be31efd439978185779f11f8279488a332777a5e19d893e1`
- staged combined fabric_task SHA256: `a3f6fe037aeabb0f840cdf12f481fae7bf98a6cec0a66b149c6815fce6c5edcb`

These bytes are **scratch outputs only**, not a protected release digest/installed-byte receipt. Any change to #1648 or #1796 or native source generation invalidates the scratch manifest; regenerate through the original owner before any actual source release.

## Remaining gates

1. Original #1648 writer repairs/clears its incorrect `source` edit, qualifies the correct **candidate** overlay, passes required current-base CI and releases writer custody.
2. Source owner integrates the reviewed fixed-run module/patch and the explicitly listed new generation member in one proper source carrier with independent security review, full native composition tests, protected GitHub CI, and merge.
3. Existing sealed native publisher/installer selects and readbacks the **actual** merged immutable generation through its ordinary CAS/owner contracts. This source-only PR does not grant that installation or bypass root/effect authentication.
4. On original M2 carrier, requalify fresh original `review-03` proof, write the exact one-time original receipt only if correctly admitted, and verify canonical Fabric MCP reports rooted **terminal failure**, never PASS. Only then admit one distinct non-Qwen Terminal #1127 reviewer through qualified capacity.
5. Terminal #1127 must have all strict current-base checks green, review findings adjudicated, and then normal Ready/auto-merge. No human Chris-specific approval is required by its observed branch-protection reviews field, but runtime and review gates remain.

**DO_NOT_REDO:** accepted Terminal watchlist source/test blobs, previously accepted separate-session direct semantic PASS, original failed Fabric worker, original broker lease, #1648's source author control, or any existing Fabric job.
