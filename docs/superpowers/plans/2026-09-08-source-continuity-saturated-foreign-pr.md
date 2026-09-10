# Saturated Foreign-PR Source Continuity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Let the one official Source Continuity adapter complete a bounded, exact owned-path collision proof when a foreign open PR saturates GitHub's 3,000-file PR-files response ceiling.

**Architecture:** Keep the existing full changed-file/rename census for ordinary foreign PRs. Detect endpoint saturation with page 1 plus the documented terminal page 30, then compare only the target's frozen owned paths at the foreign PR merge-base and head using immutable non-recursive Git tree objects. Execute independent foreign-PR observations through a fixed read-only worker pool while retaining one locked invocation budget and the existing second full observation.

**Tech Stack:** Python 3.12 standard library, urllib, concurrent.futures, GitHub REST GET endpoints, pytest.

**Spec:** Mastermind issue #346 comments 5591831933 and 5592292126; protected source `ca833b63c3ac5b2c0c1dc0d670d11e3f1f24a5b4`.

## Global Constraints

- Preserve the pure verifier and all receipt/refusal schemas byte-for-byte.
- Preserve one cumulative 640-call, 32-MiB normalized-JSON, 180-second cooperative budget across both observations.
- Preserve authenticated GET-only transport, no retry, no failover, no persistent cache, and no authority grant.
- Preserve target-PR complete changed-path enforcement; the fallback applies only to foreign collision evidence.
- Conditional rereads prove the admitted HTTP validator interpretation only: a 304 with the same opaque entity tag, including the existing weak-to-strong same-opaque acceptance, preserves HTTP cache equivalence. Exact byte equality is not proven by this proposal and must not be claimed as live proof.
- A full page 30 is endpoint saturation, never completeness.
- Tree traversal must reject malformed, duplicate, unsafe, truncated, oversized, or identity-mismatched objects.
- Collision means any presence, mode, type, or object-SHA difference at an owned path between merge-base and head.
- Results remain deterministic and sorted regardless of worker completion order.
- No Macro source, product, CI budget, ranking, serving, lifecycle, credential, release, or trading behavior changes.

---
### Task 1: Reproduce the saturated foreign-PR failure

**Files:**
- Create: `tests/test_source_continuity_saturated_foreign_pr.py`
- Read: `scripts/source_continuity.py`

**Interfaces:**
- Consumes: `_collision_census(http_get, token, repository, target_pr, owned_paths)`.
- Produces: a fake GitHub transport that models page 1 and page 30 full, immutable merge-base/head trees, and exact call tracking.

- [x] **Step 1: Write a disjoint live-shape regression**

Create a fake open-PR list containing the target and foreign PR 6657. Return 100 valid file rows for foreign pages 1 through 10, full page 30, and identical `engine/entry_signal.py` entries at merge-base and head. Assert `DISJOINT`, `complete=True`, no colliding PRs, and no requests for pages 2 through 29 after page 30 proves saturation.

- [x] **Step 2: Run the regression against protected source**

Run: `python3.12 -B -m pytest -q -p no:cacheprovider -o addopts= tests/test_source_continuity_saturated_foreign_pr.py::test_saturated_foreign_pr_uses_owned_tree_entries_for_disjoint_proof`

Expected: FAIL because protected source stops after ten full pages with `INCOMPLETE` and never reads Git trees.

- [x] **Step 3: Add collision and rename-equivalent regressions**

Cover changed blob SHA, deletion from the owned path, addition to the owned path, and mode/type changes. Each must classify the foreign PR as `OVERLAP` without requiring a rename label.

- [x] **Step 4: Add fail-closed regressions**

Cover truncated tree payload, duplicate tree entry, unsafe tree name, missing merge-base identity, changed foreign head/base identity on the second observation, and a full page 30 that is never treated as complete files evidence.
### Task 2: Implement cap-aware foreign path evidence

**Files:**
- Modify: `scripts/source_continuity.py`
- Test: `tests/test_source_continuity_saturated_foreign_pr.py`

**Interfaces:**
- Produces: `_ForeignPullIdentity`, `_CollisionObservation`, `_RemoteTreeReader`, `_foreign_collision_observation(...)`.
- Preserves: `_changed_paths(...)` for complete target-PR scope verification.

- [x] **Step 1: Parse immutable foreign PR identity**

Require positive PR number, full 40-hex head/base SHAs, a safe head repository, and the expected base repository. Include number, head repository, head SHA, base SHA, proof method, observed paths, merge-base SHA, and owned-path entry pairs in the internal observation.

- [x] **Step 2: Add cap-aware foreign file enumeration**

Fetch page 1. If it is short, parse it as complete. If full, probe page 30. A full page 30 returns `SATURATED`; otherwise enumerate pages 2 through the first short page while reusing the page-30 payload and preserving every filename/previous_filename validation and duplicate refusal.

- [x] **Step 3: Add immutable tree traversal**

Fetch commit-to-root-tree and non-recursive tree objects through the existing bounded GET. Cache only immutable commit/tree objects inside one observation. Require exact returned SHA, `truncated is False`, valid direct child names, valid mode/type/SHA combinations, and no duplicate children. Resolve each owned path component-by-component.

- [x] **Step 4: Compare merge-base and head entries**

For a saturated foreign PR, read the merge-base SHA from the compare endpoint, resolve each sorted owned path on the base repository and head repository, and classify any absent/present or mode/type/SHA difference as a collision. Store all entry pairs in the observation so the second observation must match exactly.

- [x] **Step 5: Run focused GREEN tests**

Run the entire new module. Expected: all saturation, collision, rename-equivalent, malformed-object, and identity-drift tests pass.
### Task 3: Preserve the full two-observation proof within the existing deadline

**Files:**
- Modify: `scripts/source_continuity.py`
- Test: `tests/test_source_continuity_saturated_foreign_pr.py`

**Interfaces:**
- Produces: one fixed `_FOREIGN_PR_WORKERS` value and a thread-safe `_BoundedHTTPGet`.
- Consumes: `_foreign_collision_observation(...)` for independent foreign PRs.

- [x] **Step 1: Add a concurrency RED test**

Use a blocking fake transport with two foreign PRs. Assert both observations overlap in flight only when the production worker count is explicitly enabled, while the returned observation tuple remains sorted by PR number.

- [x] **Step 2: Lock the shared budget**

Protect monotonic clock state, call admission, and normalized-byte accounting with one `threading.Lock`. Keep network I/O and JSON encoding outside the lock. Every attempted GET still consumes exactly one call before transport; late, over-call, over-byte, backward-clock, and non-finite states still refuse.

- [x] **Step 3: Parallelize only independent foreign observations**

Use `ThreadPoolExecutor` with a fixed maximum of four workers for the real stdlib transport and one worker for injected transports unless a test opts in. Cancel pending futures after a failure, wait for already-running reads to settle, and emit no partial snapshot.

- [x] **Step 4: Verify deterministic failure and success**

Add tests proving sorted output across reversed completion order, shared exact call/byte ceilings, one propagated auth/remote failure, and unchanged serial behavior for existing fake transports.

- [x] **Step 5: Run all Source Continuity tests**

Run: `python3.12 -B -m pytest -q -p no:cacheprovider -o addopts= tests/test_source_continuity.py tests/test_source_continuity_r3_hardening.py tests/test_source_continuity_census_budget.py tests/test_source_continuity_saturated_foreign_pr.py tests/test_ci_pytest_policy.py`

Expected: all tests pass with zero skips and no source dirt beyond the three planned paths.
### Task 4: Prove, publish, review, and protect the capability

**Files:**
- Modify only the three planned paths.
- Evidence outside source: `exec-prestage-receipts/source-continuity-saturated-foreign-pr-20260908-sol-001/`.

- [ ] **Step 1: Run a candidate live-shape canary**

Invoke the candidate adapter once against existing clean Macro PR #6996 with its exact operation identity, branch, pickup base, two owned paths, and `NONE/NONE` effect evidence. Record terminal JSON, exit code, elapsed time, call/byte counts, exact target head before/after, and worktree cleanliness. This is candidate evidence, not an accepted receipt.

- [ ] **Step 2: Run static and mutation checks**

Compile the modified Python files, run `git diff --check`, confirm the pure verifier blob is unchanged, confirm no public CLI/schema/limit changed, and kill mutations that skip page-30 saturation, trust metadata zero, omit one owned-path side, drop mode/type comparison, reset the second-observation budget, or remove budget locking.

- [ ] **Step 3: Commit and publish one Draft/HOLD PR**

Create one normal commit, push the exact branch once, open one Draft/HOLD PR under issue #346, and read back exact head/tree/three-file diff. Do not enable auto-merge or merge-on-green.

- [ ] **Step 4: Obtain independent immutable-head review and natural CI**

Review the exact head against issue #346 and the protected Skillpack. Require no blocker/major, complete required repository/security checks, and a current-base integration result for the same semantic tree.

- [ ] **Step 5: Settle and release source**

Run the protected adapter against the source PR, consume `REMOTE_COMPLETE_VERIFIED`, issue explicit source-builder STOP, establish branch-writer release, then perform a fresh maintenance-only expected-head release operation. Merge only if action-time head, review, checks, collision, base, and effect predicates remain exact.

- [ ] **Step 6: Run the protected real Macro consumer proof**

After protection, invoke the protected adapter once against #6996. `CHECKPOINT_VERIFIED` or `REMOTE_COMPLETE_VERIFIED` must show complete two-observation pagination and exact local/remote facts within unchanged limits. Only then may Source Continuity become `PROVEN_LIVE`; #6996 remains independently held for its own review, CI, release, and production proof.

- [ ] **Step 7: Close out durable truth**

Update issue #346 and the existing stock-picks recovery record with exact protected commit, consumer receipt, capability state, remaining #6996/#6992 gates, and the next product action. Do not create another lifecycle, memory, or projection plane.

## Chairman-authorized continuation, 2026-09-10

The live Chairman explicitly transferred the stalled source continuation to Sol
under `source-continuity-saturated-foreign-pr-takeover-20260910-sol-001`.
The original three-file preimages were preserved and matched before adoption;
no prior remote branch/PR, active source process, Git mutation lock, competing
open-PR path or other dirty worktree on these paths was found. The existing
source branch and worktree are retained; no replacement adapter or carrier exists.
Current-source reconciliation and the separate ACK/START are recorded on #346.

The prepared correction was adopted byte-for-byte onto protected base
`f3f2d9155796876009f2d427bfdecc7ee7b63e74`. All four Source Continuity suites
plus the existing CI pytest-policy suite pass in the actual repository:
**276 passed**, zero failures, in 21.09 seconds. The pure verifier and three
existing Source Continuity test files remain unchanged.

This closes the local adoption gap, not source publication or live capability.
Publish one Draft/HOLD source PR before the separately recorded candidate live
consumer observation so review, full natural repository/security CI and live-scale
qualification can proceed against one immutable source identity. This ordering
change grants no accepted receipt, consumer release or production claim.
