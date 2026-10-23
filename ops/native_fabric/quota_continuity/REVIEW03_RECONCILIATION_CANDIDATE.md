# Terminal PR #1127 - exact original Fabric review-03 reconciliation candidate

**Scope:** source-only, fixed one original run. Does not start a worker, retry a provider, release a lease, approve a PR, or change installed/native Fabric state. Current source base is protected Mastermind `076c3a917965c3334264433205f445946208c135`. The original review target remains Terminal `b036cf2fb1a8011314fa21e67fca2bdd3d8fd06f`.

## Why this exists

The M2 original `terminal-colw-pr1127-independent-review-03` controller logged `DONE rc=124 signal=effect_unknown reason=transport_deadline_without_rc` and preserved lease `037d4f680550`. A later original-host Ubuntu1 process receipt proves that the exact provider child exited `rc=1` after a Qwen HTTP 429, with one validated receipt, exact 690-byte output, zero residual processes and normal capture/cleanup. Broker state for the original lease is **expired**, not held. No independent Fabric review resulted. Original `fabric_status` currently reports `EFFECT_UNKNOWN`, `root_verified=false`, `retry_allowed=false`.

The installed native adapter's existing reconcile verbs are scoped to other fixed runs and refuse this one. **Do not** use lease expiration or a fabricated DONE log to bypass the original-effect fence.

## Qualified source

The fixed-run module `source/native_watchlist_review03_reconcile.py` checks all of the following through incumbent owners, using source-pinned SHA-256 facts:

- M2 controller log, request, request-return, launch, transport, continuation, controller/routing processes, and one exact original outcome ledger row.
- Original run/root/parent, fixed Ubuntu1 / Qwen routing identity, original support and packet digests, one failed controller and the retained `EFFECT_UNKNOWN` log.
- Existing broker's SQLite **read-only** row; original lease ID, root, provider, account, host and **expired** state.
- Original Ubuntu1 worker process receipt, exact PID/PGID, captured 690-byte Qwen 429 output, `rc=1`, SHA-256-pinned packet, and cleanup census `residual_count=0`. Remote inspection uses fixed `ssh ubuntu1` command and does not invoke a provider.
- Pre/post local evidence recheck; duplicate-key/nonfinite rejection; no-follow, current-user owned, bounded regular file requirements.

`qualification()` is **read-only** and returns proof SHA-256. `reconcile_original()` is a **candidate** one-time exclusive receipt writer: exact run/root/digest required, 0600 no-follow O_EXCL file, fsync and readback, no erase/retry on uncertain publication. The candidate's status projection describes **TERMINAL_FAILURE / review not performed / no result or acceptance**, never PASS.

## Actual qualification and tests

- Live read-only qualification against the original **M2 + Ubuntu1 + broker**: **PASS**; proof SHA-256 `6e22cfa3c2f1c147bbd2f79d3d0c08fc0d9aeac0446709df490cc6b33f22e47e` (source-preview only; not a durable production terminal receipt).
- Hermetic `pytest -q ops/native_fabric/quota_continuity/tests/test_original_review03_reconciliation.py`: **15 passed**. Covers wrong identity, stale digest, pre/post drift, tampered/symlink receipt, file custody, idempotent publication, host-report falsification and no acceptance.
- No provider request, native lease write, original run write, installed source change, checkin, PR approval or merge has occurred.

## Integration / release fences

**Not installed, not integrated into `fabric_task.py` and not an authorized original-status change.** This candidate was deliberately built in two **new, path-disjoint** files and this guide: active Mastermind PR #1648 already owns a proposed `source/fabric_task.py` edit. An original Fabric source owner must integrate a fixed `RUN`-guarded `status_from_receipt` and bounded `check/reconcile` CLI branch into the existing native adapter *after reconciling that source writer*, with tests against the actual facade and typed root, and release via the existing sealed native publication/installation owner. Never directly patch a running installed adapter.

Only after the installed facade returns a **root-verified terminal failure** for the exact original -03 run and lease evidence is read back may an independently admitted **new** PR #1127 reviewer commission proceed. The currently connected Fabric MCP has no explicit provider/model override: preserve the requested **non-Qwen** requirement using a lawfully qualified placement route, not `subject_pool` spoofing or task-class inflation. The separate direct semantic PASS is already accepted by the PR owner; this candidate cannot generate a reviewer verdict.

**DO_NOT_REDO:** decoder source implementation, accepted direct PASS, original review-03 request, original lease, or historical Qwen call. Terminal PR stays Draft/HOLD and normal approval/merge gates remain reserved.
