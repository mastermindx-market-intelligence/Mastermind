# Fabric Long-Horizon Execution — 2026-11-03

- Parent: existing `WS:EXECUTIVE-CAPACITY-FABRIC` (no new lifecycle owner).
- Chairman mandate: remove accidental short runtime ceilings and support reliable long tasks while conserving original-root, lease, host/cost, provider and settlement controls.
- Owning repository: `mastermindx-market-intelligence/Mastermind`; base protected master `9f65957e29eba92245d78609f032aaea523b7cb4`.
- Isolated workspace: `sol/web-fabric-long-horizon-timeout-20261103-sol-001`.
- Status: implementation in progress; no release or production proof.
- Collision: open PR #1902 edits candidate native remote_sub.sh, rollout source inventory and manifest. Our modifications to this launcher and manifest require rebasing/reconciliation, not overwrite or force push.

## Observed baseline

- Installed M2 native: routine max ~3600s, C2 3600s, C3 7200s, 400-turn ceiling. Outer non-native 7200s, native 3600s, go-codex ~210s special profile.
- Installed remote, slot, helper, commission-deadline and native-lease validation have independent 7200/7500 caps.
- Live Web Fabric capabilities do not expose runtime override or guarantee worker START. `fabric_wait` 10s is an observation wait, not a worker deadline.
- A worker may also end due to quota, turn cap, context, heartbeat/lease loss, deadline, or host; no unbounded work or automatic cross-provider replay may be invented.

## Outcome / DONE_WHEN

1. A new admitted C3 long-horizon worker can run beyond 7200s without a premature timeout, on compatible qualified original-carrier native routes, while bounded by a documented finite maximum.
2. End-to-end controller, child, remote, deadline, lease, native-window and turn-limit settings are consistent; special go-codex and nonqualified routes remain bounded/unchanged.
3. All finite-cap/overflow, cancellation/lease loss, inherited short deadlines, startup/settlement and effect-unknown tests pass in isolated execution; no provider calls or live-worker interruption in tests.
4. Source is independently reviewed, merged, staged and a safe real-path canary proves original run START/result and parent consumption before declaring production acceptance.

## Phases

- P0: Finish cap-chain census; validate collision/custody and actual deployed generation.
- P1: Implement finite, opt-in long-horizon runtime contract through existing source and native owner; preserve shorter explicit deadline and legal capacity/budget controls. Tests and exact source/manifest binding.
- P2: Independent nonauthor review and CI; integrate around active #1902 and other adjacent source changes, no bypass or self merge.
- P3: Install through existing native rollout owner without interrupting running generations; verify selected generation on M2 and relevant Ubuntu hosts and run an admitted nonmodifying proof canary.
- P4: Consume real result, verify restart/timeout/lease-loss failure modes, and project accepted results to existing Agent OS.

## Non-goals

No new scheduler, watcher, Job/Attempt table, retry engine, provider identity, global context override or unsafe infinite worker; no relaxation of permissions, billing, model admission, reviewer independence or platform safety denials. Existing started runs and their original source generation must not be mutated or replayed.

## Verified source milestone (2026-11-03; unmerged)

- Worktree head initially `9f65957e29eba92245d78609f032aaea523b7cb4`, branch `sol/web-fabric-long-horizon-timeout-20261103-sol-001`. Current developer edits remain local until exact-head publication.
- C2 floor increased to 7,200 seconds; C3 to 14,400 seconds; maximum 14,400 in remote launcher/child supervisor/commission, TTL 15,000 in broker-visible bounds. Five-digit seconds accepted only within finite cap. OCFree C3 inner timeout aligned; native window, operator grant and slot validation aligned. Historical go-codex and canonical paid sealed-model limits remain separate and unchanged.
- New `test_long_horizon_runtime.py`: seven deterministic no-provider tests PASS (original-shorter deadline, class floors, overflow, lease sufficiency and special route).
- Core regression group: PASS. Release/manifest group: PASS with some expected skips (exact per-case total not asserted). Native historical upgrade: 23 PASSED; original Grok/Qwen forward: 19 PASSED.
- Full historical `test_commission_deadline.py` run before expected-limit correction: one stale `7201` negative (corrected to `14401`), and separate original timing assertion `31.601s > 31.5s` remains a red timing proof; do not waive/retry merely for green. Specific `DeadlineValues` now passes.
- Broad sparse-Git security composition suite failed on `FABRIC_SPARSE_GIT_OBSERVATION_UNQUALIFIED` in unchanged workspace observation logic; exact source-pin/security manifest test passes. Scope remains unqualified for full release until independent reviewer decides.
- Material collision: open Mastermind PR #1902 edits the same native `remote_sub.sh` and release manifest, requiring exact-head reconciliation before integration. Do not self-merge or install an unreviewed candidate.
- Production status: `BUILT_NOT_PROVEN`. Actual installed M2 workers remain on earlier 2-hour generation; no Ubuntu rollout, live START, canary or parent acceptance claimed.
