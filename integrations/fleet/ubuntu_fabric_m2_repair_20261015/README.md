# M2 Ubuntu Fabric audit — source record (15 October 2026)

## Purpose and ownership

Reviewable, **non-release** source record for already-installed M2 Subagent Fabric repairs, published separately from the original fleet release writer to prevent an overlapping source mutation. The governing release remains [Mastermind PR #1404](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1404); [Macro PR #9194](https://github.com/mastermindx-market-intelligence/macro/pull/9194) is **SOURCE-MERGED** (2026-10-15, merge commit `40abd9bd2291997cc066f30b408a1e670124cec4`), but its reviewed helper has not been proven installed on the donor hosts. The separate [accepted-worker cleanup PR #9430](https://github.com/mastermindx-market-intelligence/macro/pull/9430) remains OPEN. This record does not authorize a merge, a host rollout, a forced restart, or a high-concurrency benchmark.

## Actual installed delta

`installed-source.patch` contains 13 original M2 kit files (12 changes plus one new test), SHA-256 `7f80ddfd5a9bb6961e02c2a86bcc1866bd3e92ff4f4222c88fd2b7c5cd976e17`. The local source-audit replay passed `git apply --check`, `git apply`, then **byte-exact reconstruction** of all 13 current installed files from their preserved original M2 backup baselines. Baseline and result hashes are in `SOURCE_MANIFEST.json`. The patch is relative to the **M2 kit's `ext/` directory**, not a drop-in patch for the protected Mastermind repository.

Changes include:

1. Excluding underscore-prefixed registry metadata from `host_pick.py`, `pool_status.py`, `host_pull_backend.py`, and `lease_broker.py` physical-capacity enumeration, with adversarial metadata regression coverage.
2. Synchronizing `remote_lane_v8.sh` with `host_queue.sh` for the 32-slot parser upper bound, **without** changing per-host limits or admission behavior.
3. Retaining ordinary host telemetry if an optional account-readiness module is absent, while **never** treating absent readiness evidence as authenticated or admitted.
4. Repairing obsolete host, parser, collector, real wrapper, account-readiness, and economic-policy fixtures. Explicit denial checks remain in place.

## Verified tests and live constraints

The combined installed-source Fabric test suite passed **259 tests**, with two non-fatal pytest cleanup warnings for preexisting Chromium temporary directories. `regression_integrated.txt` is the exact recorded summary; this is not all-repository CI or production release acceptance.

The incumbent collector reported 1,324 host samples each in the previous 24 hours (one-minute periodic snapshots, about 92% coverage):

| Host | Configured slots | Most lanes observed | CPU peak | Configured thermal admission cutoff |
| --- | ---: | ---: | ---: | ---: |
| Ubuntu0 | 12 | 5 | 72.375°C | 85°C |
| Ubuntu1 | 18 | 9 | 86.0°C | 80°C |
| Ubuntu2 | 12 | 3 | 73.75°C | 80°C |
| Ubuntu3 | 12 | 4 | 72.125°C | 80°C |

Ubuntu1 exceeded its configured 80°C admission cutoff in **four** recorded samples. The live mechanism must continue refusing new starts when its thermal and cooldown guards require it. No host approached all its configured worker slots during this sample window, and historical Ubuntu2 workload previously exceeded 95°C at nine lanes. **Neither 54 physical configured slots nor the source patch prove safe sustained 54-worker throughput.** The CSV-free observation summary and its limitations are in `thermal_capacity_observation_24h_20261015.json`.

The September 19 `HOST_ROUTING_SEAL.sha256` was inspected, not re-signed: **7 hashes match, 19 differ** after intervening production changes. No mass re-sealing or operator release attestation is claimed.

## Additional installed fix — M2 broker operator liveness (October 16)

The **historical 13-file** manifest above captures the original M2 installation at its verified snapshot. A subsequent read-only operator-status improvement changed M2 `lease_broker.py` from SHA-256 `9766f7c445ab430ea5a516e56602baec00a998129395ab85aa04853716d0853f` to `d2eb24f6a87c006f6b65098cb1336ae749481745e8bc8ff3e31f7c964d88aa3a`. The original replay manifest remains historical; the current installed source supersession is recorded in `ADVISORY_INSTALL_ADDENDUM.json`.

- `broker_controller_pid_advisory.patch` and `test_broker_controller_pid_advisory.py` are staged independently in this source-record PR. On M2 they are **installed and tested**: isolated 23 PASS and installed-integrated **79 PASS**, with two unrelated old temporary Chromium pytest cleanup warnings.
- Only the existing broker's **read-only operator display** changed: when a remote worker's acquiring *broker-host controller* PID is absent in the same PID namespace, print `CONTROLLER_PID_ABSENT`, not worker failure. Remote worker state stays unknown, and the broker still does **not** auto-release that lease.
- Five remote provider leases were observed held despite missing controller PIDs. Three had remote RC0 markers but no verified M2 controller return; two still had running remote workers. **No lease was released**, no worker cancelled, and no timed-out run repeated. See `LEASE_RECONCILIATION_AND_DIAGNOSTIC.md` for original run/root/host evidence and the lawful recovery frontier.

## Integration and release gates

1. The #1404 incumbent source writer compares exact before/after source hashes and reconciles patch overlap with thermal, disk, sparse-worktree and launcher changes. A new owner may not silently overwrite it.
2. Approved source must pass exact-tree hosted CI, maintain denial and resource guards, and satisfy the existing protected review/release controls. The merged #9194 helper must be independently read back and installed on the intended donor hosts before opt-in sparse mint is enabled; source merge alone is insufficient.
3. Use an *attended, bounded* real-host workload qualification and physical cooling proof with the original admission authority. Respect prior power-profile `AccessDenied`; no sudo, BIOS, worker-kill, or thermal override is justified by this record.
4. Keep this source record distinct from `INSTALLED`, `RELEASED`, `PRODUCTION_ACCEPTED` and `ALL_ACCOUNTS_SELECTED`. Original 13-file M2 installation is evidenced in the M2 evidence directory, not retroactively delivered to other hosts.

Original local evidence: `/Volumes/Mastermind/evidence/ubuntu-fabric-audit-20261015-sol-web-01` on M2 Studio. No secrets, credentials, vendor account bindings or mutable broker databases are included here.
