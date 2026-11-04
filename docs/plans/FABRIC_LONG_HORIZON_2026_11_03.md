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

## GLM signed-capability compatibility amendment (2026-11-03)

A follow-on owner census found the signed GLM gateway/issuer (`ops/native_fabric/paid_canonical_glm/candidate/glm_lease_capability.py`, `glm_lease_gateway.py`) still enforces a 7,500-second maximum. The native 15,000-second token-request change was therefore **withdrawn** as unqualified; the GLM client uses the unchanged 7,500-second token constraint. Newly classified C3 work on `glm-codex` and canonical-paid GLM is visibly narrowed to 7,200 seconds *before* provider/worker effects and the existing signed capability TTL remains <=7,500 seconds. Normal qualified routes may use the new 14,400-second window. Operator-root grant authorization is extended to 14,400 seconds for explicit admissible longer windows, but default 7,200-second root grants are not silently expanded. A separately reviewed and installed GLM capability-service update plus end-to-end host proof is required for four-hour GLM-codex support.

The amended 102-member native source manifest is `0df8514fe753aa5d0f912a259cffd3dae285be44d5d0c8455833673a1bcaba4d`. New 9-case no-provider bounds/GLM compatibility suite PASSED; 6 poll-margin cases, 23 historical native-upgrade and 19 historical Grok/Qwen composition cases PASSED. Reviewer request on PR #2019 is only an invitation, not independent approval; exact-head re-review is required after amendments.

## 2026-11-03 inherited broker-wait cleanup reserve — qualification update

The frozen original full-CLI deadline regression was still red on the previous
candidate: `elapsed_seconds=31.65011379099451` against the unchanged strict
`31.5`-second upper bound. Its captured real broker fixture consumed
`30.004829` seconds after being asked to wait 30, then foreground Bash,
owned-process cleanup and result handling required additional time. No lease
was granted, and no task or transport was launched. This is a reproduced
source-bounded timing defect, **not** a justification for extending the
original 31-second commission clock or relaxing the test's 0.5s allowance.

Repair: keep the existing `deadline-seconds` helper and original monotonic
clock, but accept one fixed internal `broker` selector only from the existing
`remote_sub.sh` lease-acquire seam. That selector reserves two seconds from
the *actual remaining* commission deadline before computing the broker
`--wait` argument; it uses a zero-second queue wait for short, still-positive deadlines;
short-path immediate acquisition and inherited deadline enforcement remain intact.
Other worker/poll/deadline consumers keep the old whole-second behavior.
The reserve is not a caller-supplied duration or a renewed deadline.

After the source repair the **same frozen original CLI fixture passed**:
`elapsed_seconds=29.33193345798645` (strict 31.5s limit unchanged),
`broker_requested_wait=27`, `broker_actual_wait=27.005s`,
`lease_granted=false`, `task_count=0`, terminal `rc=75`.
The new deterministic unit test also covers 4h unbounded-broker allowance
(ordinary 3600-second cap unchanged), short inherited budgets, an explicit
smaller requested wait, invalid reserve selectors, and expired deadlines.

Release qualification: 102-file native manifest now
`1d3ecc6627b0e106e9fb9400729e0bd81f27aa2f1c98fb2d57189e802e41ced4`;
review-stage manifest and inventory are regenerated from the exact selected
candidate. The historical 95-file fixture is restored using byte-pinned
predecessor inversion rather than silently changing old source. The combined
focused native, launch-upgrade, historical Grok/Qwen, and source staging suites
passed. The older hosted CI shard-2 failure applied to pre-repair head
`3505ab7785610df347fd6c0ceba6a97f92ad1e15`; it does not establish
CI green for this repaired head. Current-head hosted CI and independent review
are still required before production rollout. Sparse-Git observation remains
separate from the broker timing defect and is not waived.
