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

- 102-member selected native source manifest SHA-256: `aae32107790f98eb652b3780a7c61d8340310a61576a5eccb58afd9b08bd0291`.
- Selected remote controller SHA-256: `e12c764d8978c2aeb536945e12f5e14cb89c3a98cdbab5802905dc014acdb73d`.
- Protected Qwen broker SHA remains `a2847a29abe590cb168c2cd8ae34e0b1c3222b6e92ab4c00f252a342d56e6406`.
- Parent exact base remains `da989061704182a25d93bc561400e3e99cbba6f7` (PR #2019), not protected master. No review or deploy/prod proof of this performance head is claimed yet.

## Explicit long-horizon limitations preserved

The native `fabric_task.wait_for()` observation helper still validates `timeout <= 7200` seconds and the Web `fabric_wait` tool has a much shorter observation window. **Those wait calls do not terminate the worker** and must not be advertised as the four-hour execution fuse. Their relevant source is inside the protected Qwen composition, so this source branch does not silently repin them. Observers may requery the existing run ID through the incumbent owner; a separate source-qualified change is needed for one uninterrupted four-hour CLI wait. Terminal absence after a short observation is not a failed worker or permission to replay.

Result latency is **one** performance dimension. This patch does not shorten model inference time, provider rate limiting, host startup, cost/usage, remote transfer or independent-review gates; quantify those using the installed owner’s existing process/CI/host receipts before proposing a second optimization. The gain documented above is simulated same-run terminal visibility only, not worker task throughput or total PR delivery time.

## Source qualification receipts — 2026-11-03

- New deterministic source-extracted fast-observation and heartbeat/backoff tests: **5/5 PASS**.
- Combined native-release, historical95, Grok/Qwen composition, initializer, host-pull, support-policy and slot-custody suites: **PASS** with unchanged expected skips.
- Existing full `test_commission_deadline.py` suite: **19/19 PASS** with its original strict 31.5s frozen deadline proof unrelaxed; no worker or provider launched.
- 102-file source staging manifest SHA-256 `aae32107790f98eb652b3780a7c61d8340310a61576a5eccb58afd9b08bd0291`, selected remote controller `e12c764d8978c2aeb536945e12f5e14cb89c3a98cdbab5802905dc014acdb73d`, Qwen protected broker unchanged.
- Temporary test-run outputs were archived outside the worktree and are **not** part of published source or an installed runtime.
- No live SSH/provider/lease, formal independent review, hosted CI or production canary exists for this performance branch at this checkpoint. This source is `BUILT_NOT_PROVEN`.
