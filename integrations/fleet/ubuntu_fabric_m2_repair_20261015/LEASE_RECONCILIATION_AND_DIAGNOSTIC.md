# Interrupted M2 Fabric controllers: capacity evidence and safe recovery frontier

Observed **2026-10-16 00:19–00:21 UTC** through the incumbent M2 SQLite broker (opened in read-only mode), `fabric_task.py status` (read-only), retained original M2 `remote_sub` logs, and **direct read-only original Ubuntu host** process/terminal-marker reads. No new worker, lease edit, signal, process reprioritization, receipt replacement, or provider call.

## Why configured host capacity can look capped

The four Linux `max_active` values **12 / 18 / 12 / 12** are not the effective provider availability. At 00:19 UTC the canonical broker still counted **five `held` remote provider leases whose original M2 `remote_sub.sh` controller PIDs were no longer present**. `remote_sub.sh` acquires with `--pid "$$"` on the *M2 broker host* while its lease `host` field is the selected *remote worker host*. The current `Broker._gc_locked` only checks PID liveness if `row["host"] == self.this_host`; therefore for these remote leases **PID loss alone does not reclaim capacity**. They retain the recorded **7,470-second lease TTL** with liveness/renewal semantics. That conservatism protects remote workers whose controller disappeared; do not change it into an unconditional reaper.

## Exact observed original runs

| Lease ID | Original run ID | Root/parent owner | Host | Observed remote evidence | M2 controller |
| --- | --- | --- | --- | --- | --- |
| `acb037984977` | `mm-r1-experience-atomic-review-20261015-01a1333c-v1` | `01a1333c-a475-7052-95a8-72c623fb12e1` | ubuntu0 | remote RC absent, remote process running | PID `27893` missing |
| `3199b371c1f7` | `fable-p3-har-numerical-kernel-20261015` | `01a10340-ddc1-7e41-9b42-9c8543c28c3d` | ubuntu2 | remote `.rc` contains `0`; controller completion not proven | PID `32793` missing |
| `74fc1cce07d5` | `mm-u6-auth-demand-20261015-01a1333c-v1` | `01a1333c-a475-7052-95a8-72c623fb12e1` | ubuntu1 | remote RC absent, remote process running | PID `49485` missing |
| `e7cd591f7010` | `fable-s-incumbent-covariates-20261016` | `01a10340-ddc1-7e41-9b42-9c8543c28c3d` | ubuntu1 | remote `.rc` contains `0`; controller completion not proven | PID `67454` missing |
| `96351a8fe697` | `defense-publisher-history-review-01a13300-a` | `01a13300-c75b-79c3-83f9-79b3b4c01dc7` | ubuntu0 | remote `.rc` contains `0`; controller completion not proven | PID `76980` missing |

The original controller logs stop at approximately 00:09–00:11 UTC and do **not** establish M2-side `REMOTE_DONE`, delivered stdout, cleanup receipt or terminal ledger acceptance for these runs. `fabric_task status` reported `UNVERIFIED`, `result_available=false`, `worker_state=UNKNOWN` and `retry_authorized=false`. Remote RC `0` is not by itself a verified lifecycle result. In particular **do not release all five leases**: two workers remained visibly active and the other three have incomplete original controller return evidence.

## Additional direct-host process receipt evidence (read-only)

The same three RC0 runs were then inspected through exact original-host process receipt paths (not the old controller's missing local result). Each preserved `mastermind.local_owned_process_receipt.v1` has exactly **one** JSONL row, matching `label == original run_id`, integer `returncode == 0`, `timed_out == false`, `cleanup.status == not_needed`, `cleanup.reason == normal_completion`, `cleanup.residual_count == 0`, `census_proven == true`, `identity_verified == true`, and all three capture/delivery-complete flags true:

| Host | Original run | Original host process receipt SHA-256 |
| --- | --- | --- |
| ubuntu2 | `fable-p3-har-numerical-kernel-20261015` | `14870b36e955adcd86f02d5b0e34bfe4d7eba25cffc2ef12fd8d884c44681b37` |
| ubuntu1 | `fable-s-incumbent-covariates-20261016` | `c2470ee541602ae8b97359d2b5dd5c265bc83681ae6cf3f49cb52393356be741` |
| ubuntu0 | `defense-publisher-history-review-01a13300-a` | `919d9126e359593cc678fd1f4d4f26b1c79e9b0cac903a9c5227d90898c11a0e` |

**Important distinction:** These direct-host process receipts strongly support physical worker completion/cleanup and are ready for exact original-owner verification; they do **not** create a new M2 controller transport receipt, an accepted result, or original-parent permission to settle a broker lease. Source generation, immutable log, exact account binding and original delivery still require original-owner reconciliation before any capacity is reclaimed. The two other exact runs still lacked remote terminal markers at the earlier observation and must not be touched merely because their M2 controller vanished.

## Installed narrow repair, without new lifecycle authority

The incumbent M2 `lease_broker.py` operator `print_status` now emits `CONTROLLER_PID_ABSENT` for a remote-class lease when a **live same-broker-host snapshot** shows its controller PID absent, and prints `remote_worker=UNKNOWN no_release_or_retry=1`. It never changes the lease table, broker GC/TTL behavior, worker PID, credentials, host admission, or provider capacity. The warning is suppressed for a cross-host snapshot, uncertain permissions, and non-remote leases.

- Prior installed broker SHA-256: `9766f7c445ab430ea5a516e56602baec00a998129395ab85aa04853716d0853f`.
- New installed broker SHA-256: `d2eb24f6a87c006f6b65098cb1336ae749481745e8bc8ff3e31f7c964d88aa3a`.
- Candidate patch SHA-256: `293ab3aae9e401eef4278aaf065d74c7c981daa862e5e41bb87f9f8d315c831c`.
- New test SHA-256: `345f8beb1ed664f2e437a5496ecc25d16fb42a81d3f24a2e24e31e027ea10fa0`.
- Isolated 23/23 tests and **installed integrated 79/79 tests PASS** (two preexisting unrelated pytest temporary Chromium permission warnings).
- Reversible M2 backup: `lease_broker.py.bak-controller-pid-advisory-20261016`. The source patch is relative to the M2 kit `ext/` baseline and must be semantically integrated by the original source-release owner.

## Next safe recovery

The **original parent** for each run must reconcile the original run/root/parent, support generation, remote result/process cleanup and broker lease identity. Only after the original effect and worker termination are evidenced should the incumbent exact-run owner settle the existing lease under its own verified authority. Do not use `fabric_task.py request` to re-launch an uncertain run, substitute another worker, or turn a PID warning into a release certificate. Auto-expiring remote leases merely because the M2 controller is absent could double-spend provider slots while their detached remote workers continue.

The three original run parents are separate from Fleet #1404; this finding is fleet-capacity evidence, not a transfer of those sessions' worker custody. Fleet #1404 remains the original source/release owner; source record #1552 remains DRAFT and is not a published runtime rollout.
