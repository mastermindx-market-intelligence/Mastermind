# Fabric fast completion observation and admission — 2026-11-03

Repository: `mastermindx-market-intelligence/Mastermind` (existing `WS:EXECUTIVE-CAPACITY-FABRIC`).
Original root implementation: PR [#2019](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2019), exact base `da989061704182a25d93bc561400e3e99cbba6f7`.
This is a **separate source-only stacked performance change**, operation `fabric-fast-observation-20261103-sol-003`, branch `sol/web-fabric-fast-observation-20261103-sol-003`. It does not replace the existing worker/runtime/release author.

## Problem and honest baseline

- Controller's remote result checks use a fixed default 30-second interval on nonnative paths, 10 seconds on native and go-codex paths. The worker may finish at any time between checks, adding an expected delay of up to half the interval to user-visible terminal evidence.
- The incumbent broker uses one-second default polling while waiting for newly freed capacity, adding an expected ~0.5s detection delay after release with no event notification.
- Repeated SSH poll failures can create unhelpfully frequent retries when the fast first-minute cadence is enabled. An observation transport failure is not worker death, never approval to restart, move, or replay a launched task.

## Target/source contract

1. **Early fast observation:** the *same original remote run*, SSH alias and result file are observed with 2s checks for the first 30s, 5s until 2m, 10s until 10m, then the **same configured maximum poll period** (default 30s nonnative/10s native) thereafter. A lower caller-configured interval remains the maximum. Never add an independent watch/queue/heartbeat/retry engine.
2. **Transport-safe backoff:** successive failed/malformed remote reads use 5, 10, and then up to the existing configured ceiling instead of the fast cadence. A verified pending response resets backoff. All control/proof/timeout semantics remain with the incumbent launcher and original root.
3. **Held broker subpath:** acceleration of the independently protected Qwen lease-broker bytes requires a separate reviewed source contract. This performance PR preserves the exact protected broker SHA and does not alter its queue, fairness or lock.
4. **Consistency and proof:** tests assert strict cap/clock behavior, SSH failure backoff, 4-hour bounded poll count, response detection improvement with a simulated terminal time and broker wait improvement under deterministic time, no provider or live host. Preserve immutable historical 95-file and current 102-file native stage, exact digests and approved shared release composer. No production claims from simulated benchmarks.

## Acceptance and gates

- Deterministic simulation should show worst-case early completion readback of 2–5s rather than up to 30s, plus bounded extra polls per 4-hour job (no unbounded SSH storm). The separately held broker change must independently qualify fair admission and the immutable Qwen source before integration.
- Full focused test pack and source/fixture integrity checks, then real current-head CI and independent non-author review. Stacked branch cannot be installed or merged independently of PR #2019; conflicts with #1902 heredoc changes must be reconciled on protected source.
- Installed-generation proof on authorized M2/Ubuntu, first-seconds completion readback and original-parent result acceptance are required. Do not start paid worker for a benchmark or interrupt a running generation without the release owner.
- No new lifecycle, lease, scheduler, queue, provider reset, transport failover, repeat remote launch, or unattended program. Preserve exact source/restorable release and fail-closed unresolved effects.

Status: source development; production capability unchanged.

## Qwen-protected broker boundary (2026-11-03)

Initial source prototype included a three-probe admission pickup optimization in `candidate/lease_broker.py`. A deterministic no-provider test picked up simulated capacity released at 150ms within 350ms (vs the original 1s scan); **however** the integrated `test_protected_qwen_files_and_exact_context_reader_forward` refused this change because the Qwen branch pins the broker SHA `a2847a29abe590cb168c2cd8ae34e0b1c3222b6e92ab4c00f252a342d56e6406`. The owner has deliberately closed the existing Qwen forward exception set.

Decision: **do not waive or repin the protected-Qwen digest** as part of the remote-observation PR. Restore `lease_broker.py` byte-for-byte to its parent, remove broker-specific test changes, and reserve the fast three-probe optimization for separately authorized, independently qualified Qwen/provider source composition. It is not installed, benchmarked live, or claimed as delivered. The remote fast-result observation path is disjoint and remains the active source deliverable. No duplicate broker, queue, or retry carrier is created.

## Deterministic performance measurements (no live workers)

Source-extracted shell scheduling probe (same candidate code; virtual clock):

| Execution route/configured maximum | First 120s median completion-observation delay | First 120s maximum | Observations in a 4-hour run |
| --- | --- | --- | --- |
| Previous 30s result polling | 15s | 29s | 480 |
| Adaptive 30s ceiling | **1s** | **4s** | 541 (+61, 12.7%) |
| Previous 10s result polling | 5s | 9s | 1,440 |
| Adaptive 10s ceiling | **1s** | **4s** | 1,461 (+21, 1.5%) |

The late stage (after ten minutes) returns to the configured interval, so there is **no unbounded growth** in SSH reads for four-hour tasks. Repeated SSH/protocol failure only slows observation (5/10/max interval), not retries worker launch or transfers custody. The validated lease-broker heartbeat guard keeps the existing heartbeat frequency despite the faster early result checks; the original provider lease, heartbeat and process supervisors remain unchanged. Tests executed the actual extracted Bash helper in virtual time, with no SSH call, worker, billing, account or live broker.

Broker admission acceleration's simulated 0.35s pickup vs old ~1s polling was a *source prototype only*; it was removed from this branch to respect the protected-Qwen digest and requires separate qualified forwarding. No production speedup has yet been measured. The user-visible benefit requires the **same** immutable generation to be reviewed/merged/installed and a real original-root result-observation canary.

## Current source stage

- 102-member selected native source manifest SHA-256: `d47ea1dceaaf8818e442f65cd4e51a1796197e170f1d91723c0216c2e0778384`.
- Selected remote controller SHA-256: `c0cd0f437d3c88c09586c9a13eb03eca86442fbb8bfcce3ed338a8040c3e30f1`.
- Protected Qwen broker SHA remains `a2847a29abe590cb168c2cd8ae34e0b1c3222b6e92ab4c00f252a342d56e6406`.
- Parent exact base remains `da989061704182a25d93bc561400e3e99cbba6f7` (PR #2019), not protected master. No review or deploy/prod proof of this performance head is claimed yet.

## Explicit long-horizon limitations preserved

The native `fabric_task.wait_for()` observation helper still validates `timeout <= 7200` seconds and the Web `fabric_wait` tool has a much shorter observation window. **Those wait calls do not terminate the worker** and must not be advertised as the four-hour execution fuse. Their relevant source is inside the protected Qwen composition, so this source branch does not silently repin them. Observers may requery the existing run ID through the incumbent owner; a separate source-qualified change is needed for one uninterrupted four-hour CLI wait. Terminal absence after a short observation is not a failed worker or permission to replay.

Result latency is **one** performance dimension. This patch does not shorten model inference time, provider rate limiting, host startup, cost/usage, remote transfer or independent-review gates; quantify those using the installed owner’s existing process/CI/host receipts before proposing a second optimization. The gain documented above is simulated same-run terminal visibility only, not worker task throughput or total PR delivery time.

## Source qualification receipts — 2026-11-03

- New deterministic source-extracted fast-observation and heartbeat/backoff tests: **7/7 PASS**.
- Combined native-release, historical95, Grok/Qwen composition, initializer, host-pull, support-policy and slot-custody suites: **PASS** with unchanged expected skips.
- Existing full `test_commission_deadline.py` suite: **19/19 PASS** with its original strict 31.5s frozen deadline proof unrelaxed; no worker or provider launched.
- 102-file source staging manifest SHA-256 `d47ea1dceaaf8818e442f65cd4e51a1796197e170f1d91723c0216c2e0778384`, selected remote controller `c0cd0f437d3c88c09586c9a13eb03eca86442fbb8bfcce3ed338a8040c3e30f1`, Qwen protected broker unchanged.
- Temporary test-run outputs were archived outside the worktree and are **not** part of published source or an installed runtime.
- No live SSH/provider/lease, formal independent review, hosted CI or production canary exists for this performance branch at this checkpoint. This source is `BUILT_NOT_PROVEN`.

## Numeric safety amendment after source review request

The original launcher accepted zero values with leading zeroes (e.g. `REMOTE_SUB_POLL_SECS=00`) and oversized decimal strings before numeric comparisons. That could create a rapid SSH polling loop or overflow a shell integer. Exact pre-launch validation now refuses zero or >5-digit values for the poll/runtime, bounds each poll to 14,400s, preserves the original 14,400s maximum runtime and all valid 1..14,400 second inputs. Nine valid/negative combinations execute the real source fragment in a provider-free test; all pass. This is a source hardening delta on the same PR and requires an updated exact-head review and hosted CI.

## Real-path acceptance matrix and known operational gates

Source tests are not fleet performance measurements. The live adapter readback during this change reported `adapter_available=true` but `worker_admission=UNPROBED`, `worker_start=UNPROBED`, and no native background/parent Wake. Studio gateway status reported four of eight account tunnels READY, others DEGRADED, a configured 5-hour transport TTL and `physicalFleet=null`. That is **not** proof physical Ubuntu workers are unavailable or that a particular tunnel has five hours of remaining life. Any 4h commission must check its exact original admission/transport lifetime, host generation and effects rather than assuming a configured TTL is remaining headroom.

After lawful release, the incumbent owner must verify all of the following on the installed immutable generation before calling this upgrade production-accepted:

1. **Source/identity:** exact reviewed PR head, merger, 102-file selected manifest digest, installed M2 and each eligible Ubuntu host generation, original-root ancestry, provider lease and model attestation. No mutation of pre-existing started generations.
2. **Healthy quick-task proof:** an authorized low-cost no-mutation worker starts once; original run ID, remote terminal receipt and parent consumption are all observed, including elapsed time between worker-written RC and controller detection. Repeated healthy samples should quantify p50/p95 instead of extrapolating synthetic numbers.
3. **Healthy long-task proof:** a bounded, authorized existing-carrier long-running canary spans each polling phase and confirms the source's <=30s final observation window, unchanged 4h execution fuse, and successful lease heartbeat without redundant broker calls or duplicate launch.
4. **Failure/custody proof:** simulate remote status read failures on a safe non-provider fixture, check 5/10/max interval slowdown, recovery on verified pending, no hot-loop for leading-zero poll input, lease unknown retained on unreconciled launch, and zero foreign worker termination/forced replay.
5. **Fleet budget:** evidence from the actual authorized fleet/transport owner that its session/tunnel remains valid through the admitted worker + setup + settlement window. `physicalFleet=null` is a read-gap to resolve, not permission to invent an unavailable host, new tunnel, or background daemon.

Before/after deploy comparisons must separate actual model inference time, waiting for capacity, staging/SSH transfer, worker completion visibility, original parent acceptance and PR review/merge delay. No fabricated aggregate speedup or throughput figure is authorized.

## Bounded test-fixture stability amendment

The expanded offline deadline suite hit an intermittent assertion for `test_mutated_remote_packet_refuses_launch_and_binding`: the controller refused the corrupted packet with RC78, but setup had consumed its original eight-second fixture budget before the expected verification marker. One bounded no-provider diagnostic reproduced the **intended** transport refusal at 6.264 seconds with a real `TRANSPORT_VERIFICATION_REFUSED rc=78 before_launch=1` marker and no worker launch. The negative test's original purpose is packet tamper refusal, not an eight-second performance deadline. It now supplies **14 seconds** of finite startup headroom, while retaining *all* exact substantive assertions: RC78, transport read, zero launch, no trusted transport-verification record and no launch binding. The focused negative test PASSED on the new fixture. The 31-second/31.5-second strict deadline test and all production timeout defaults remain unchanged; test-fixture headroom is not provider authority or a performance claim.


## Canonical decimal and 30-second heartbeat observation (2026-11-03)

Adversarial prelaunch validation identified a second numeric corner: Bash interprets
leading-zero positive integer strings as octal during `$((...))`; the existing
prelaunch guard rejected `00` but let `00010`, `00008` and `07200` through.
Those are now **rejected**, rather than normalized by introducing new arithmetic
or preserving ambiguous spellings. The valid input contract remains canonical
1..14,400 decimal seconds. A large configured poll interval can no longer leave
an active worker unobserved for hours; the existing same-run result-check sleep
is capped at **30 seconds**, matching the incumbent heartbeat duty. Caller
poll settings below 30s are still honored. No extra lease/heartbeat owner,
new child, replay or transport is introduced.

Seven source-extracted no-provider tests PASS, including large configured poll
(`120` seconds) never producing a >30s gap over an entire virtual 4h run.
Source and historical native-manifest SHA pins were rebuilt from the selected
candidate with 102 exact members. A new exact-head review and hosted CI remain
required; the old published PR commit does not include this amendment.

## Stacked head source integration with current runtime (2026-11-03)

After the production runtime PR #2019 was integrated with protected master at
source SHA `93c8c3c01f9226d1ea267e21c548f047458654dc`, it advanced to a true
two-parent head `d0891a8ad99640b223cafb55c717f169e4a20819`.
This fast-observation source has been composed with that exact parent, preserving
protected same-selection diagnostics and the finite 4-hour runtime contract; six
source/pin conflicts were reconciled in the original operation-bound worktree.
The real 102-member selected stage now hashes to SHA-256
`d47ea1dceaaf8818e442f65cd4e51a1796197e170f1d91723c0216c2e0778384`,
with remote controller SHA unchanged at
`c0cd0f437d3c88c09586c9a13eb03eca86442fbb8bfcce3ed338a8040c3e30f1`.
Historical test fixtures remain sealed; the parent source plan retains its
own earlier-stage manifest for PR #2019, not this future performance release.
New head, CI, formal review and fleet acceptance still require canonical proof.

## Read-only fleet installation baseline (2026-11-03)

The live account gateway reported a previously degraded aggregate fleet view, but a separate authorized remote-device census observed **ubuntu0, ubuntu1, ubuntu2, ubuntu3 and ubuntu4 all reachable**. M2's own installed Fabric `hosts.json` lists all five as `lanes` roles with `max_active` 12, 18, 12, 12 and 2 respectively. Ubuntu1 has 24 logical cores; the other four expose 32. Snapshot load averages were 0.33, 2.70, 0.04, 1.05 and 0.00 for the five hosts (one observation only; not a throughput or capacity entitlement claim).

Current M2 immutable native selection is `8cefc4b27b2036f86bcec1d626e864f45f792e2c290ab8de56fbde89f78ac94a`, and the selected code still hashes to legacy remote controller `7da97d3b99a0b9bc7f8aa15f7b405a099f22d8954feb9fb9ec24acf2c3092e92`, legacy slot `4edfed01136259dd45bd5a8d049961161af0953e9f97e30fcddab1ba1164c34f`, and legacy fabric task `ca091b1e21f5b9d3349e7ce31ae46dff6173d27b5f36d432179418415f03eb88`. These are **not** this 4-hour/fast-poll candidate. The unchanged `ext/` flat helper hashes differed among Ubuntu hosts; that alone does not prove active-run code mismatch because per-run immutable `support-releases/` is the source of remote support, not an arbitrary flat file. No provider call, worker dispatch, installation or host mutation occurred in this census.

Production acceptance must confirm exact new native `CURRENT.json` generation and source identity on M2, each host's immutable support-release digest for *new* work, unchanged code of already-running controllers, broker original-root custody, real single worker START/result/parent-consumption, and p50/p95 terminal receipt delay from original log timestamps. Ubuntu4's configured two active lanes should not be raised solely because its one-time load was zero; qualify provider/model entitlement and resource pressure through the incumbent Capacity admission owner before any capacity adjustment.

## Long-horizon poll-margin and test-harness correction

The adaptive observer caps actual SSH result-check sleeps at 30 seconds even if a caller requests a larger interval. The original child-timeout calculation erroneously reserved two *configured* poll periods, needlessly truncating a four-hour child for a 120-second poll setting. The current source reserves exactly two *actual* periods (maximum 30 seconds); synthetic source-extracted tests assert a 14,400-second fuse yields a 14,340-second child with configured polls of both 30 and 120 seconds, with the inherited shorter commission always controlling. No production fuse or lease upper bound was extended.

The immutable offline launch/deadline fixture now gives its separate *test harness* finite headroom to observe actual commission expiry on overloaded hosts. Its harness timeout never enters the worker environment. Stage-specific fake delays were increased correspondingly where necessary to prove slow upload, setup and admission-refusal paths. Original security assertions, child cancellation, broker lease retention and zero duplicate launches remain binding; negative source tests and hosted current-head CI must still be verified.

## Integrated source release qualification at d089 parent

Current source is composed against true two-parent #2019 runtime source `d0891a8ad99640b223cafb55c717f169e4a20819`, rather than the superseded earlier parent. The exact canonical native-source builder produced 102 selected members (manifest SHA-256 `d47ea1dceaaf8818e442f65cd4e51a1796197e170f1d91723c0216c2e0778384`, controller SHA-256 `c0cd0f437d3c88c09586c9a13eb03eca86442fbb8bfcce3ed338a8040c3e30f1`). Local paired native/historical-source/closed-Qwen/Grok source-qualification tests PASS on the composed candidate. The entire original `test_commission_deadline.py` suite PASSED: **19/19 cases**, including strict immutable 31s admission fuse and prelaunch packet/transport integrity, with the separate offline harness giving finite load-sensitive headroom but not altering the commission clock. Fast source-extracted polling and margin tests PASS.

The original production host remains on older immutable generation `8cefc4b27b2036f86bcec1d626e864f45f792e2c290ab8de56fbde89f78ac94a`; this is source qualification, not new live worker proof. Do not install until genuine head CI, independent nonauthor GitHub review, protected merge, and owner-native generation admission.

A bounded read-only census of the latest 40 stored M2 controller logs found 30 terminal runs with minute-resolution median worker launch-to-result of roughly **6 minutes**, p90 roughly **7 minutes**, and generally immediate lease and support setup. Faster result observation addresses post-completion latency, not model inference; follow-on throughput optimization requires measured model routing and task subdivision through the existing owner. No new monitoring store was created.


## Current stack reconciled with reviewed slot-fuse repair

The original runtime source has advanced from the prior \`d0891a8\` head
to \`aca5a01582aa6cf0cc6e9ad918c5962c4112307c\`, repairing a major
independent-review defect in which an inner slot supervisor could terminate
an outer four-hour C3 worker at its original two-hour default. This
performance branch now **includes** that exact repair and the existing
source-selected 102-member generation, retaining its independent adaptive
polling changes without globally increasing slot defaults. The selected
stacked manifest SHA-256 is
\`dccb8bffd9bd78594863cc333630000793fcfb9a15ec5acd5f78c58e2d84ff43\`.
The separate \`tests/test_fabric_native_feature_suite_coverage.py\` CI guard
now recognizes the two distinct valid cleanup-margin source policies:
the current adaptive controller uses a <=30s **actual** poll interval,
while unchanged Grok overlay uses its original caller configuration.
Both still enforce the two-observation settlement margin, and the
real native margin test suite is executed rather than skipped. CI on
superseded \`d02075e\` was red ONLY on the obsolete source-marker
assertion; current-head CI and formal review are pending.


## Final launch-reserve integration

After the original long-horizon runtime carrier #2019 advanced to
`91b164c8b585eabd59cd76e7d66b06ae0209b7bb`, this stacked source
integrated its exact prelaunch observation-reserve repair. The same
original commission refuses a **new** remote launch with fewer than five
seconds left; already-running terminal observation, leased custody and
noncommissioned short runs are unchanged. This prevents avoidable
`EFFECT_UNKNOWN` caused by launching with a one-second residual
commission. The combined adaptive 2/5/10/30-second result observation,
inner slot-four-hour handoff, and strict original fuse are all retained.
The merged controller source SHA-256 is
`c0cd0f437d3c88c09586c9a13eb03eca86442fbb8bfcce3ed338a8040c3e30f1`
and selected immutable 102-file manifest SHA-256
`dccb8bffd9bd78594863cc333630000793fcfb9a15ec5acd5f78c58e2d84ff43`.
Tests and source safety gates remain binding until requalified at this exact
source head; no live worker has been launched or deployed.

## Latest exact runtime-parent composition and verification

The original operation-bound fast-observation branch at \`4e6c671da7bd979df3fc2299e83634d8c422520e\`
has now integrated the independently approved runtime #2019 source at exact
\`91b164c8b585eabd59cd76e7d66b06ae0209b7bb\`.
Nine content conflicts were resolved in this one worktree, including the
native source manifest/inventory, source-composition digests, and historical
source-qualification tests. The actual canonical immutable publisher selected
102 native files, with manifest SHA-256
\`dccb8bffd9bd78594863cc333630000793fcfb9a15ec5acd5f78c58e2d84ff43\`
and composed controller SHA-256
\`c0cd0f437d3c88c09586c9a13eb03eca86442fbb8bfcce3ed338a8040c3e30f1\`.
It contains the nested slot 4-hour effective timeout handoff and 5-second
new-launch original-commission reserve; the adaptive observer still has
the 30-second maximum receipt interval and preserves broker/lease identity.

Current integrated local **strict commission and launch-reserve suite PASS**
(24 actual tests, RC0; prelaunch/transport ambiguity negative paths intact).
Current integrated local **native source/historical95/B11/paid initializer/
provider custody/fast observer/slot handoff suite PASS** (RC0,
six explicitly expected source-fixture skips). No live worker/provider ran.

The signed GLM capability PR #2020 and CI Fastlane PR #2016 were **already
added to the incumbent protected merge queue** on GitHub (native timeline
events 2026-11-04T04:10:51Z and 2026-11-04T03:50:37Z respectively).
Existing QUEUED effects must be reconciled rather than duplicated despite a
stale Secretary note reporting them as not enqueued. Their merge and live
installation are not proven by those events. Parent runtime PR #2019 has
independent exact-head approval at \`91b164c8\` and its current-head CI/
protected integration remain separate gates.

The planned next source operation is a correctly parented merge commit on
this existing branch, one non-forced push and fresh current-head CI/review.
No M2 or Ubuntu \`CURRENT.json\`, supported generation, running worker,
provider lease, queue runner or original return was modified in local testing.
