# One original Fabric launch: sparse mint + CPU-budget scope

**Verified October 15, 2026 UTC. State: SOURCE_READY / TESTED_IN_ISOLATION / NOT_INSTALLED / NOT_RELEASED.** This is an integration of the **existing** original Fabric run, host/provider/physical admission, immutable support and result/settlement owners. It creates no second broker, worker queue, native RuntimeBinding, cleanup daemon, retry plane or power-management authority.

## Why these two changes must be one source update

Two draft source changes share the same original M2 controller files:
- [Existing strict sparse prelaunch candidate](FABRIC_SPARSE_PRELAUNCH_CANDIDATE_20261014.patch): create a new, source-pinned **Macro** sparse checkout only after original physical admission and before original provider START; avoid 10-GiB post-START full worktree materialization.
- [Original-run CPU scope and detached-child cleanup candidate](FABRIC_COMBINED_SPARSE_AND_CPU_SCOPE_20261015.patch): bound **all descendants** of qualified Ubuntu2/3 new workers with a user-owned cgroup CPU quota, then refuse original lease settlement until the scope is verified empty.

The stand-alone patches are **not directly composable**: seven shared insertion anchors in `fabric_task.py` and five in `remote_sub.sh` conflict. We reconciled these via three-way diff against exact original files, retaining both opt-in validations, one Linux route selection, both original launcher arguments and both original remote child environment fields. The merged `remote_sub_exec.py` and `support_bundle.py` were conflict-free. Use the **single authoritative** [combined patch](FABRIC_COMBINED_SPARSE_AND_CPU_SCOPE_20261015.patch), not sequentially applying the stand-alone patches.

Combined patch SHA-256: `f17fbf15d6544bccfebe02111c8503e663a918822f8ad3aa2342587b208b723d` (36,404 bytes). It includes the original `fabric_cpu_scope.py` helper [as a readable source](source/fabric_cpu_scope.py).

### Exact production M2 source preimages — no installed source changed

| Original source | Original SHA-256 | Combined candidate SHA-256 |
|---|---|---|
| `fabric_task.py` | `bfa5fcdc3df04d76d6c3b0b2dda2dac17ab4539253ec3ffb86fca4e2c4c13207` | `fd6b3c316089324d4b51478861a89a11702c5264d924f6dd29244d9ffe8a6349` |
| `remote_sub.sh` | `e2ec7dfe2efa0680b4bf961ac73ce916adf5f1dc90e510f6c8ff6ed50e069deb` | `85e4502a0040089cd4e0d59e99bd2af4ab7b1db8881393ffe305057348e8f999` |
| `remote_sub_exec.py` | `c6b4292cdb7d106d5b376587f29276da1550e5eee02268f479abd7ad2ea61189` | `fa5ed00fff3c6c367cc92d9452490b9098c5d9159f454537c9a5c5676261d4bd` |
| `support_bundle.py` | `2790f29690bac70f111b118ddb3defd8da49ecc2653a8a2cd3caa2be69121f51` | `e054b05fece124c6918f12dc1ce3962e6f20b5d74dea5e26630524be9b20295a` |
| **new** `fabric_cpu_scope.py` | absent | `15891591aba64e7d5658b7c92fd5ff90a89f6c57df952f8e5673c2a638fc0c63` |

All original SHA preimages were checked at the M2 source before patch generation and no concurrent writer had changed them. The combined source exists under `/tmp/mmx-fabric-cpu-scope-20261015-candidate/cpu_sparse_combo/`, *not* in M2 installed Fabric ext or any Ubuntu support release. Its exact GitHub bytes were read back after publication.

## New temporary CPU scope: discovery and true risk

Original installed `lane_runtime.run_owned_process` (immutable runtime SHA-256 `966869a4137545203faa2269faeed15cd0a096b5611161d242e2fb13b7c27937`) owns a process group. On **Ubuntu3**, a harmless temporary child deliberately called `start_new_session=True`. When the parent timed out (~1.29 seconds), Fabric returned `cleanup_proven=true` for the group, yet the detached child still appeared in its **user-owned systemd cgroup** and was independently alive. In the exact own-fixture scope `mmx-thermal-cleanup-proof-2804989.scope`, stopping *only that known test scope* returned 0, removed its remaining child, left the unit inactive and the cgroup empty. This is a real process-ownership gap, but it **does not prove** a particular historical zero-lane heat event was an orphan of Fabric.

Both Ubuntu2/3 support `cgroup v2` `cpu` and an authenticated **unprivileged** user systemd bus at `/run/user/1000/bus`. Actual user-owned `systemd-run --user --scope -p CPUQuota=100%` under the original owned-process runner returned a child `cpu.max=100000 100000` on **both hosts**, normal RC0 and cleanup-proven. No administrator, power-profile or BIOS change was made. The Ubuntu2 `powerprofilesctl set balanced` denial remains respected and has **not** been retried under a different carrier.

### CPU scope design inside existing Fabric ownership

Explicit controller `--cpu-scope-percent {100,200,400}` applies only to authorized **new** `glm/glm-codex/minimax/qwen` workers routed to `ubuntu2/ubuntu3`, with original root, parent, lease and support digest. It remains **unset by default**; no current worker is changed. The verified scope name is a bounded hash of those original identity fields. On the selected host **after** incumbent `LaneLease.acquire`, the original host executor invokes the user-owned systemd scope for exactly one worker and strips the systemd session bus and quota flag from the provider process environment. The cgroup enforces aggregate CPU time, including a worker's Python/Node detached descendants.

Before the original lease is released, the existing executor invokes `fabric_cpu_scope.settle_scope`: validates unit/cgroup identity and reads exact `cgroup.procs`; if descendants remain, stops only this original-run scope; then requires unit inactive and no PIDs. If identity, stop, cgroup state or process cleanup cannot be verified, it returns RC76/effect-unknown and retains the **original** Fabric reconciliation lease, not an invented retry or terminal receipt. The existing group cleanup remains in place. The helper has **no background watcher, polling daemon or independent lease/worker owner**.

## Tests and effect evidence

All tests below completed with direct readback, no actual provider dispatched:

- `tests/test_cpu_scope_controller.py`: 100/200/400 schema/mode/host/root/parent validation, existing router forwarding and disabled-default unmodified.
- `tests/test_cpu_scope_launch_contract.py`: fake actual host executor orders **physical lease → scoped worker START → scope verification → lease release**, verifies RC78 refusal before START and RC76 unknown cleanup with original lease held.
- `tests/test_cpu_scope_host_live.py`: the pinned runtime plus **actual Ubuntu3 user cgroup** qualified one CPU quota and reaped an intentionally detached child after the original process-group timeout. The remaining child was visible **before** scope settlement and absent **after**. No production Fabric run or worker was touched.
- [Combined source sparse tests](tests/test_combined_optin_contract.py): one original run with **both** flags orders `physical lease → exact sparse mint → cgroup scope preparation → worker START once → cgroup settlement → lease release`, while retaining its original request identity and stripping new-workspace flags from model environment.
- `tests/test_combined_shell_dryrun.py`: the staged original launcher accepted both explicit flags using `/usr/bin/false` for SSH/SCP/rsync; malformed quota and invalid pinned Git commit were refused before reservation with RC78; **no network worker dispatch**.
- Existing prior Mastermind tests `test_workspace_integration.py`, `test_controller_request.py`, `test_prelaunch_order.py`, `test_actual_macro_mint.py`, `test_launcher_dryrun.py` plus the new CPU tests all passed when invoked against the **same merged staged source**.
- Immutable support publication test: the **merged** code emitted exact 31-source digest `ca16d4bc96dff355eb20ecb6e41d6ddad222473a3b141616c3224898f99408e5` into **isolated** `/tmp` support-releases. The sealed host `remote_sub_exec.py` and `fabric_cpu_scope.py` bytes were verified. The older 30-file source generation was also accepted with digest `049d8de77a366c7f12d2d99f634dbe918349978fe4ae52d7c7d7160eb9d99dc4`. Neither original host release nor M2 live source was modified, and publication was idempotent in sandbox.

## Exact release and acceptance boundaries

This candidate is **NOT installed**. It does **not** impose a global CPU quota, alter active workers, change machine-wide CPU frequency, bypass PowerProfiles authority, or supersede BIOS thermal safety. Existing new-job limits on Ubuntu2/3 are each `max_active=1`, `load_gate=4`, `cpu_tctl_limit_c=80°C`.

Before production admission:
1. Have the original owner reconcile this one combined patch against the exact current M2 ext source and the active writer state; use CAS and keep one rollout carrier. The two earlier independent patches are **superseded for deployment** and must not be layered separately.
2. Resolve Macro draft [#9194](https://github.com/mastermindx-market-intelligence/macro/pull/9194) source/CI/release review and the overlapping Mac SSD draft #6939, then qualify the reviewed `fabric-mint` helper on a new selected Ubuntu donor repo. Do not reset the primary Macro source branch or re-sparsify old SNI worker checkouts.
3. Publish the **same source** as one newly verified immutable support generation. Confirm legacy generations stay valid, publisher hashes/source scope are checked, and original runtime admission/identity is preserved.
4. First accept a **bounded new task** through the original Fabric adapter with real original root and parent; explicitly request sparse mint and/or CPU quota. Verify source SHA, original leased host/worker process, sparse cwd, cgroup `cpu.max`, no descendants after stop, worker throughput and intact original return. Compare against a matched control. A dry-run, mock, or test cgroup does not prove production selection.
5. For sustained physical thermal headroom, Chris must attend MSI BIOS maintenance to qualify PBO 85°C thermal point and/or documented Eco Mode with a matched workload benchmark; the previous Ubuntu2 OS power-profile AccessDenied still blocks that operation.

**No host reboot, live service restart, forced worker termination, broad Git garbage collector or unreviewed privileged change occurred during this source-only CPU-scope engineering.**
