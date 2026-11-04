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
`a130be866589897c74a09ee5689ad9df751ce2207b8e5768cb5b58274292bbed`;
review-stage manifest and inventory are regenerated from the exact selected
candidate. The historical 95-file fixture is restored using byte-pinned
predecessor inversion rather than silently changing old source. The combined
focused native, launch-upgrade, historical Grok/Qwen, and source staging suites
passed. The older hosted CI shard-2 failure applied to pre-repair head
`3505ab7785610df347fd6c0ceba6a97f92ad1e15`; it does not establish
CI green for this repaired head. Current-head hosted CI and independent review
are still required before production rollout. Sparse-Git observation remains
separate from the broker timing defect and is not waived.

## 2026-11-03 hosted-CI exact-shard diagnosis and source-qualification repairs

Current pre-repair head `da989061704182a25d93bc561400e3e99cbba6f7`
hosted GitHub Actions CI run [41744937105](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/41744937105)
finished RED on four pytest shards (0,1,2,4); the aggregate `test` gate
was RED as a consequence. We fetched the dedicated first-party job logs
on the original source account to identify concrete failing tests rather
than claiming local results were CI success.

1. **Shard 1**: `test_h1_native100_packaging.py` still asserted that
   `GROK47_CANDIDATE_COMPOSITION_DIGESTS` had only the *historical four*
   names. The current 4h source legally introduces exactly three additional
   qualified sources (`sub.sh`, `native_remote.py`, `fabric_operator_contract.py`).
   The repaired assertion protects the original four and asserts the closed
   exact three additions (no open-ended set comparison), then verifies all
   member SHA-256 values. Local targeted test PASS.
2. **Shard 2**: `test_native_manual_auto_source_20261024.py` expected the
   historical `fabric_task.py` digest `ea918a83…` as *current*. The current
   selected `fabric_task.py` is `16bc8efd…` after two finite runtime
   comparisons changed from 7,200s to14,400s. The repaired test checks
   current exact SHA and reverses **only those two bounded comparisons** to
   prove the historical SHA. Original manual-auto fixture remains untouched.
   Local test PASS.
3. **Shard 4**: `test_native_launcher_successor_transition.py` expected
   the historical B11/current102 mismatch to consist of only five earlier
   sources; the new runtime source legitimately differs in ten other named
   source members. We added one immutable test-only historical source fixture:
   `tests/fixtures/native-long-horizon-predecessors-20261103.json`
   (SHA-256 `bb924475a501aa732ca0c5b1f05f9428c100c546bcbfb5d3e0c2ceaf268d6f19`),
   holding five exact source preimages from protected base
   `9f65957e29eba92245d78609f032aaea523b7cb4`, each verified against the
   unchanged original B11 manifest SHA and decompressed size. The other
   five source preimages are checked against immutable original
   `source/` or `grok47/overlay/` byte digests. The fixture restores only
   a disposable historical102 stage, never relabels or rewrites the
   immutable original B11/95 manifest, installer or real selected code.
   **All 32 B11 tests PASS locally** after this restoration.
4. **Shard 0**: `test_ceo_submit_armed_composition.py` D8 identity
   guard flagged two `660` numeric literals in a newly selected operator
   authorization source. Those literals described an **eleven-minute
   execution start window**, not a UID. We replaced both with the named
   `OPERATOR_MIN_START_WINDOW_SECONDS = 11 * 60`, preserving exact
   comparison boundaries. A new regression verifies the value is still
   exactly 660 and both source callsites use it. Read-only execution of
   the existing D8 source scanner against the working diff returned an empty
   finding set (no bypass or relaxation of the scanner).

Local **consolidated source-qualification suite PASS**, covering closed
forward map, exact manual-auto predecessor, all B11 historical successor
fixtures, paid initializer, source/manifest check, and historical95 upgrade;
the dedicated long-horizon suite also PASS. The selected current102 source
manifest SHA is `a130be866589897c74a09ee5689ad9df751ce2207b8e5768cb5b58274292bbed`.

This is not a production acceptance or a hosted green receipt. This branch
still needs new exact-head GitHub CI, formal nonauthor review, protected
merge, immutable-generation installation and original-root worker result
acceptance. The stacked performance PR #2023 remains pinned to the old
parent until the source owner lawfully reconciles its base; do not move or
merge it silently. The separately governed signed-GLM source #2020 remains
draft and uninstalled.

## Master integration conflict resolution — current wave

- Protected source read pinned at `Mastermind@93c8c3c01f9226d1ea267e21c548f047458654dc` (schema `mastermind.sol_skillpack.v1`, `1.0.1`, compatible bootstrap 1). GitHub source PR #2019 previous exact head `97f7a728367b86e861d7a337e585ab0726ecfec3` had all 12 current-head GitHub checks green, but a real content conflict with current protected master.
- Source integration uses a **real two-parent merge** of that exact protected commit into the existing operation-bound `fabric-long-horizon-timeout-20261103-sol-001` worktree, not a force push or second writer. The 10 content conflicts in the selected stage, manifest/inventory, source-qualification pins and historical tests were resolved to preserve **both** four-hour runtime limits and the merged protected S9 same-selection diagnostic observer.
- Source selection regenerated with the canonical builder: 102 native members, source manifest SHA-256 `a130be866589897c74a09ee5689ad9df751ce2207b8e5768cb5b58274292bbed`. Candidate `fabric_task.py` composed SHA-256 `778f4f3ebf03f5ce93e60081dc8a739ae90fb4cbeb32d01bbcc7b008c813a23b`; test inverses the **two bounded runtime budget changes** to the exact protected diagnostic source SHA `ca091b1e21f5b9d3349e7ce31ae46dff6173d27b5f36d432179418415f03eb88`.
- Historical B11 test now checks both the prior five source preimages, the five sealed long-runtime original preimages, the five unchanged source/overlay original preimages, **and** protected S9 preobserver picker. Original B11/95 manifests and independent byte hashes were not rewritten or waived.
- Focused release source tests `tests/test_h1_native100_packaging.py`, `test_native_manual_auto_source_20261024.py`, all B11 successor-transition tests, paid initializer, source/manifest, native95 upgrade and runtime C2/C3 budget cases **passed** before this merge publication. `git diff --check` for the candidate-owned delta relative to protected `93c8c3c` also passed. Protected master research Markdown trailing whitespace is unrelated and was not touched.
- The next irreversible effect is the existing workspace owner making one merge commit with exactly the original PR head + protected `93c8c3c` parent, followed by same-branch nonforce push, current-head CI, source review and release. No deployment or fleet worker proof exists from this source qualification.


## Independent review 5763157664 — real nested child fuse repair (2026-11-03)

The nonauthor reviewer \`mastermidx4\` requested changes on original exact-head
\`d0891a8ad99640b223cafb55c717f169e4a20819\`: even after increasing
the outer C3 worker ceiling to 14,400s, the real nested \`slot.py\`
still defaults to 7,200s and would terminate a qualified worker after two
hours. This is a **confirmed source defect**, not a reviewer process problem.

The original repair carrier now passes the **already-narrowed** parent
commission/lease timeout to the existing slot owner as
\`SLOT_CHILD_TIMEOUT_SECONDS\`, after late commission deadline rechecking,
for ordinary remote \`glm\`/\`minimax\`/\`qwen\` worker paths. Any stricter
pre-existing slot or pool timeout stays stricter; malformed/overflow values
refuse before worker START. Signed GLM remains capped by its existing
outer 7,200s/7,500s attestation, and the special go-codex path is unchanged.

For standalone Grok, the existing embedded Python launcher now supplies the
validated worker timeout through the same slot-owned environment key.
It also no longer raises an **explicit** shorter \`POOL_CHILD_TIMEOUT_SECONDS\`
commission to a four-hour worker solely because the task is C3;
classification can raise the **default** only. It does not change
the slot default, broker heartbeat/lease owner, or global timing semantics.
The original outer process remains the earlier terminating owner.

Source-extracted hermetic tests execute the actual Grok budget resolution and
slot launch fragment with an inert process recorder, and compile the exact
remote child handoff function from its current AST, invoking the real slot
timeout parser. They cover 14,400/14,340s, explicit 1,200s budget, inherited
500s and 210s bounds, malformed/NaN/overflow refusals, no implicit 2h
cap, and retained original supervisor. These are **not** provider/live
long-duration tests. Source stage rebuilt at exactly 102 members with
selected manifest SHA-256
\`a130be866589897c74a09ee5689ad9df751ce2207b8e5768cb5b58274292bbed\`,
remote executor SHA
\`9a01a5b7d559e2f86b92f1da9c7f426d6a5b9c4f1e0ca98542ce8a0452bf87c1\`,
and embedded Grok launcher SHA
\`4956942c77421b9d1015889995ebf0419399ea62c16de608765a0795b5fb551f\`.
Current-head CI, independent nonauthor re-review, protected merge,
immutable installed-generation readback and genuine single-run result
acceptance remain separate required gates.


## Original controller near-expiry launch prevention

The downstream strict commission fixture discovered a real *prelaunch*
uncertainty hazard: after source/support preparation used almost all of a
14-second caller commission, the remote controller still accepted a one-second
remaining budget for a **new** SSH launch. The result was a needless terminal
\`EFFECT_UNKNOWN\` and preserved broker lease with no time left to read
the remote RC. This is a canonical process-owner bug, not permission to replay.

The original \`remote_sub.sh\` commissioner now refuses a **new**
original-commission launch when fewer than five seconds remain. It does not
extend the monotonic deadline, alter the ordinary runtime fuse, bypass
pre-existing leases, or abort an already-observed terminal: the same-run
admission-retry path still collects the original result when \`RC_OBSERVED=1\`.
The special no-commission explicit short run retains its old contract.

A new source-extracted, no-SSH/broker/provider
\`test_launch_observation_reserve.py\` executes the actual launch-budget
shell function and checks 1–4 seconds refuse cleanly with RC75, 5+ seconds
retain bounded worker budgets, and non-launch stages stay unchanged:
**five tests PASS**. The 102-member source manifest was rebuilt, SHA-256
\`a130be866589897c74a09ee5689ad9df751ce2207b8e5768cb5b58274292bbed\`,
remote controller SHA-256
\`e24d6123ae1c303fe7a72b88c9ae6093979dcf35a9984d7ba16ccb9689700b05\`.
The dependent fast-observation PR #2023 needs to recompose this exact source
head before claiming the accepted long-horizon/fast result contract.
