# Terminal PR #1127 - exact original Fabric review-03 reconciliation candidate

**Scope:** source-only, fixed one original run. Does not start a worker, retry a provider, release a lease, approve a PR, or change installed/native Fabric state. Current source base is protected Mastermind `076c3a917965c3334264433205f445946208c135`. The original review target remains Terminal `b036cf2fb1a8011314fa21e67fca2bdd3d8fd06f`.

## Why this exists

The M2 original `terminal-colw-pr1127-independent-review-03` controller logged `DONE rc=124 signal=effect_unknown reason=transport_deadline_without_rc` and preserved lease `037d4f680550`. A later original-host Ubuntu1 process receipt proves that the exact provider child exited `rc=1` after a Qwen HTTP 429, with one validated receipt, exact 690-byte output, zero residual processes and normal capture/cleanup. Broker state for the original lease is **expired**, not held. No independent Fabric review resulted. Original `fabric_status` currently reports `EFFECT_UNKNOWN`, `root_verified=false`, `retry_allowed=false`.

The installed native adapter's existing reconcile verbs are scoped to other fixed runs and refuse this one. **Do not** use lease expiration or a fabricated DONE log to bypass the original-effect fence.

## Qualified source

The reviewed source was subsequently hardened after an independent MiniMax Fabric source review reported two concrete issues: descriptor-open directory-chain validation now guards both M2 original artifacts/receipt publication and the Ubuntu1 remote read, and one-time receipt publication converges by validating a concurrently published O_EXCL winner. The expanded fixture-backed suite covers source_snapshot(), observe_original_host(), CLI, ancestry symlinks and concurrent publication. This source review is not a Terminal code-review verdict.

The fixed-run module `source/native_watchlist_review03_reconcile.py` checks all of the following through incumbent owners, using source-pinned SHA-256 facts:

- M2 controller log, request, request-return, launch, transport, continuation, controller/routing processes, and one exact original outcome ledger row.
- Original run/root/parent, fixed Ubuntu1 / Qwen routing identity, original support and packet digests, one failed controller and the retained `EFFECT_UNKNOWN` log.
- Existing broker's SQLite **read-only** row; original lease ID, root, provider, account, host and **expired** state.
- Original Ubuntu1 worker process receipt, exact PID/PGID, captured 690-byte Qwen 429 output, `rc=1`, SHA-256-pinned packet, and cleanup census `residual_count=0`. Remote inspection uses fixed `ssh ubuntu1` command and does not invoke a provider.
- Pre/post local evidence recheck; duplicate-key/nonfinite rejection; no-follow, current-user owned, bounded regular file requirements.

`qualification()` is **read-only** and returns proof SHA-256. `reconcile_original()` is a **candidate** one-time exclusive receipt writer: exact run/root/digest required, 0600 no-follow O_EXCL file, fsync and readback, no erase/retry on uncertain publication. The candidate's status projection describes **TERMINAL_FAILURE / review not performed / no result or acceptance**, never PASS.

## Actual qualification and tests

- Live read-only qualification against the original **M2 + Ubuntu1 + broker**: **PASS**; proof SHA-256 `6e22cfa3c2f1c147bbd2f79d3d0c08fc0d9aeac0446709df490cc6b33f22e47e` (source-preview only; not a durable production terminal receipt).
- Hermetic `pytest -q ops/native_fabric/quota_continuity/tests/test_original_review03_reconciliation.py`: **24 passed**. Covers wrong identity, stale digest, pre/post drift, tampered/symlink receipt, file custody, idempotent publication, host-report falsification and no acceptance.
- No provider request, native lease write, original run write, installed source change, checkin, PR approval or merge has occurred.

## Integration / release fences

**Not installed, not integrated into `fabric_task.py` and not an authorized original-status change.** This candidate was deliberately built in two **new, path-disjoint** files and this guide: active Mastermind PR #1648 already owns a proposed `source/fabric_task.py` edit. An original Fabric source owner must integrate a fixed `RUN`-guarded `status_from_receipt` and bounded `check/reconcile` CLI branch into the existing native adapter *after reconciling that source writer*, with tests against the actual facade and typed root, and release via the existing sealed native publication/installation owner. Never directly patch a running installed adapter.

Only after the installed facade returns a **root-verified terminal failure** for the exact original -03 run and lease evidence is read back may an independently admitted **new** PR #1127 reviewer commission proceed. The currently connected Fabric MCP has no explicit provider/model override: preserve the requested **non-Qwen** requirement using a lawfully qualified placement route, not `subject_pool` spoofing or task-class inflation. The separate direct semantic PASS is already accepted by the PR owner; this candidate cannot generate a reviewer verdict.

**DO_NOT_REDO:** decoder source implementation, accepted direct PASS, original review-03 request, original lease, or historical Qwen call. Terminal PR stays Draft/HOLD and normal approval/merge gates remain reserved.

## Independent Fabric source review and bounded repairs

A separate MiniMax Fabric integration worker completed a root-verified terminal return under run `terminal-colw-pr1127-nativehook-integration-20261022-01`. It found that the earlier 15 tests omitted original-owner source/remote CLI paths, intermediate symlinks were not guarded, and O_EXCL winner races were misclassified. The module now delegates local ancestry custody to the **existing** `artifact_delivery.DirectoryChain`, holds remote ancestry descriptors in a source-fixed read-only ssh probe, and safely re-reads a concurrently published immutable receipt. **24 local focused tests now pass**, including owner fixtures for the eight original inputs, broker/ledger negative controls, the CLI and SSH response, symlink attacks and publication race. The read-only original M2/Ubuntu1/broker proof remains `6e22cfa3c2f1c147bbd2f79d3d0c08fc0d9aeac0446709df490cc6b33f22e47e`. No live receipt has been written.

## Native facade integration artifact — deferred, not installed

The original MiniMax Fabric source integration worker returned a source patch and integration-contract tests on its original root-qualified terminal result. These are now retained **in this same PR** as:

- `review03_integration/review03-into-fabric_task.patch`: changes **only** the future incumbent `source/fabric_task.py`, with the fixed-run `EFFECT_UNKNOWN` guard, default read-only check, explicit one-time reconcile with proof-digest witness, and strict run/root identity for **both** actions. It is **not applied** in this PR because Draft #1648 still owns that file.
- `review03_integration/deferred_tests/review03_integration_contract.py.txt`: source-only contract for the future integration. It uses the non-executable `.txt` suffix until the source owner integrates the hook, preventing the current green source-only PR from accidentally treating uninstalled integration as working.
- `review03_integration/HANDOFF_REVIEW03_HOOK_INTEGRATION.md`: the original independent review return, with a contextual warning for already-repaired #1796 issues.

**Actual validation:** a scratch, non-repository copy of current protected `fabric_task.py` was patched; Python compilation succeeded; **15/15 integration tests passed**, alongside the **24/24** current fixed-run source tests. This is **not** native installation, production readback, a provider review, or authority to alter #1648.

After the native source owner reconciles #1648's writer and accepts the exact patch, apply it through the incumbent source branch, copy/rename the contract to `ops/native_fabric/quota_continuity/tests/test_review03_integration_contract.py`, then rerun the full Native Fabric and protected source composition suites. Merge only with required protected CI, independent review, and complete-generation manifest publication. The original failed review's immutable artifacts and expired broker lease must remain unchanged; installed `fabric_status` must read back terminal/root-qualified before any new reviewer is commissioned.

## Source-security F1/F2/F3 corrections after the earlier 24-test checkpoint

**This section supersedes earlier test counts and original-preimage integration instructions above.** The independent Fabric source-security review returned a code-only PASS with six nonblocking findings against the earlier source. Source code on this same #1796 carrier has subsequently changed and needs fresh independent semantic review before release.

- F1 broker file custody: the read-only original SQLite lease query now holds the incumbent `artifact_delivery.DirectoryChain` for `broker/`, opens `leases.sqlite` with `O_NOFOLLOW`, and verifies held and visible inode/owner/mode/size/timestamps before and after SQLite read. New negative tests reject a symlinked SQLite leaf and a symlinked broker-directory ancestor. The broker is never mutated.
- F2 exclusive-receipt race: a rival original O_EXCL receipt still being populated is classified as `original_receipt_incomplete`. Its bytes are never erased or overwritten, and no automatic retry is authorized. Completed same-proof rivals still converge by readback.
- F3 deferred-contract relocation: the contract locates the original module by walking repository ancestors, both in its current deferred location and when installed under the standard `tests/` directory.

**Verified after the repairs:** 27/27 focused source/negative tests and 15/15 scratch integration contract tests pass. A fresh *read-only* original M2/Ubuntu1/broker qualification still returns the previously verified digest `6e22cfa3c2f1c147bbd2f79d3d0c08fc0d9aeac0446709df490cc6b33f22e47e`, proves original Qwen rc1 with no residual process, and confirms broker lease expired. This proves neither a new Terminal reviewer nor native installation.

**Important corrected integration ownership:** the retained `review03_integration/review03-into-fabric_task.patch` targets the frozen installed source preimage and MUST NOT BE APPLIED. The correct deferred patch is `review03_integration/review03-into-candidate-fabric_task.patch`; the newly introduced module also requires `review03_integration/review03-include-native-generation.patch` in the same reviewed/closed generation. See `review03_integration/COMPOSED_NATIVE_OVERLAY_RELEASE_EVIDENCE.md` for scratch 86-file composition. Any actual integration must reconcile candidate/publisher source writers and requalify tests/CI/independent review before sealed release.

**Release posture HOLD:** no change has been made to installed native adapter, original Fabric status/lease, Terminal PR head, Ready state, or auto-merge. Canonical `fabric_status` remains `EFFECT_UNKNOWN` until an actual installed owner performs the exact fixed-run one-time reconciliation and readback.

## Current candidate integration — protected-master composition (2026-10-22 late Pacific)

**This section supersedes the earlier source-only/deferred integration descriptions.** The same original #1796 source worktree has been updated conflict-free against protected Mastermind `08805aeb7f79712cc9964af1ea5fab959d2984fd`. The previously deferred fixed-run adapter hook was applied **to `candidate/fabric_task.py` only**, and the new `native_watchlist_review03_reconcile.py` was explicitly registered in `rollout/build_review_stage.py`. The existing immutable `source/fabric_task.py` preimage remains exactly SHA256 `8f28799dc4f2d0b815fa467dab1dee5c5a9781d220199a5358be49773a74b686`.

The contract test was promoted from the retained `.py.txt` archival copy to `tests/test_review03_integration_contract.py` with its assertions pointing to the actual candidate overlay rather than the frozen preimage. The native builder produced **96** explicit code files, up from **95**, with *exactly one* newly added native module and *exactly one* modified existing native code path (`ext/fabric_task.py`). Both tracked rollout inventory artifacts and the native security composition test's explicit expected-count/manifest-SHA constants were updated to the following reproducible stage digests:

- Native manifest SHA256: `d16b05629040c4fb2c7f887afb22327eb5e6f2c37d89dac45912234b2caae4ab`.
- Source inventory SHA256: `2152ba234afc2bad474919ffd85648974f3f33545e518b5b801c1cb1f7ac2731`.
- Staged candidate adapter SHA256: `50bf0afa5172ca0481a513aa3c8d851c3a7e0f2e002258eece965c68125fdb5c`.
- Staged original-run reconciler SHA256: `edb6478e4032b71f1746748100e2b0db78bca5e4f2ec9ac572d79d59de44c1a5`.

**Validation scope:** fixed-run 27/27 unit and negative tests PASS; integrated adapter contract 15/15 PASS; selected native generation/runtime-binding tests PASS (one known skip); full native stage assembled with all manifest digests correct and frozen preimage untouched. The comprehensive M2 macOS sparse-Git fixture tests still fail closed because Apple Git 2.50.1 emits the `advice.sparseIndexExpanded` hint (440 bytes stderr) for a sparse-index observation; the retained production reader intentionally refuses any stderr. The relevant executor `candidate/remote_sub_exec.py` is byte-identical to protected Mastermind. Do not suppress this warning, weaken the fail-closed check, or claim full cross-platform suite green; required hosted CI must adjudicate it on the runner environment.

**Review and effect posture:** the immediately preceding paid source-security attempt `terminal-colw-pr1127-nativehook-postfix-security-review-20261022-01` ended root-verified `TERMINAL rc=1` after Qwen 429 without an independent review response. It must not be called PASS. The newer integrated candidate semantics must receive their own independent review and protected current-head checks before merge or publication. **Nothing has been merged, published, installed, selected or enabled on the original M2 adapter. The original Terminal review-03 effect remains canonical `EFFECT_UNKNOWN`**, and this source candidate does not itself dispatch a new non-Qwen Terminal reviewer.

Open overlapping native-proposal PRs (#1315, #1648, #1731, #1784, #1788) must be reconciled through their true active source owners and ordinary GitHub merge/rebase rules before production release. Branch-local authoring of this candidate is not a grant to overwrite another branch, claim installed bytes, or bypass runtime source custody.
