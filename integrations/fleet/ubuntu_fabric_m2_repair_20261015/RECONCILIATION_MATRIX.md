# Installed M2 audit vs Fleet PR #1404 — patch reconciliation

**Source snapshot:** `mastermindx-market-intelligence/Mastermind` fleet PR [#1404](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1404) head `672805ca932960c7fb8d15a7f09bb9240e6304f1`, original installed M2 13-file patch from [#1552](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1552) SHA-256 `7f80ddfd5a9bb6961e02c2a86bcc1866bd3e92ff4f4222c88fd2b7c5cd976e17`.

**Method:** Compared exact filenames parsed from all **12 GitHub patch artifacts** changed in #1404 against the 13 installed files in `SOURCE_MANIFEST.json`. This is a path-overlap census—not a claim that hunks conflict, commute, or have been accepted by the original writer. The M2 patch was reconstructed against archived **installed kit baselines**, not against GitHub master.

## Paths requiring hunk-level source reconciliation

| M2 patched file | Existing #1404 staged source patch artifacts | Guard/intent to preserve |
| --- | --- | --- |
| `host_pick.py` | `host_pick_collector.patch`, `precheckout_disk_admission.patch`, `thermal_recovery.patch` | Existing thermal cooldown, disk staging reserve, fresh probe and host-qualification checks; add only underscore metadata filtering |
| `host_pull_backend.py` | `collector_trend_logging.patch`, `hot_process_diagnostics.patch`, `thermal_recovery.patch` | Keep bounded trend + process diagnostics and risk/cooldown envelope; add only metadata filtering and optional-validator import isolation |
| `pool_status.py` | `status_thermal_dashboard.patch`, `thermal_trend_status.patch` | Keep existing thermal dashboard/status and 4-hour trend reader; add only metadata filtering |

The installed patch also includes **disjoint** runtime files `lease_broker.py` (metadata must not multiply host-admitted Grok/Cursor physical capacity) and `remote_lane_v8.sh` (same 32 parser syntax ceiling as `host_queue.sh`, without raising host admission caps). Its remaining eight paths are tests and fixtures:

- `tests/test_hosts_registry.py`, `tests/test_host_pull_selected.py`, `tests/test_host_aware_pick.py`, `tests/test_auto_host_pick.py`
- `tests/test_registry_metadata_filter.py` (new), `tests/test_five_host_enrollment.py`, `tests/test_sub_host_policy.py`, `tests/test_host_admitted_grok_cursor_20261012.py`

No path overlap was found against the other #1404 staged `FABRIC_COMBINED_SPARSE_AND_CPU_SCOPE_20261015.patch`, `FABRIC_SPARSE_PRELAUNCH_CANDIDATE_20261014.patch`, `FABRIC_ACCEPTED_WORKTREE_RECLAIM_PLAN_20261015.patch`, `go_thermal_disk_admission.patch`, `intel_package_thermal_admission.patch`, or `hot_process_diagnostics.patch` beyond the specific collector file described above.

## Source-owner integration order (no new authority)

1. Start from the **actual current reviewed release-source files**, not old archived versions. Confirm exact source identities and all preimage SHA-256 values from `SOURCE_MANIFEST.json`. Never reset/overwrite changed M2 runtime files merely to make a stale patch apply.
2. Check whether each staged #1404 thermal, disk, cooling, sparse and collector hunk is **already included** in the installed M2 baseline (likely for earlier live patches). Adopt only the incremental fix that is not already present. For the three overlapping files, manually rebase onto the accepted current file before generating an immutable source release patch.
3. Preserve `require_thermal`, per-host `max_active`, `lane_ceiling`, `load_gate`, thermal threshold, memory/disk checkout reserve, profile qualification, broker account limits, and original worker/lease custody. Do not interpret the legacy parser's upper bound of 32 as permission for 32 new workers on a host.
4. Run focused installed-source regressions (the saved M2 suite passed **259 tests**) plus release-specific exact-tree hosted CI; no test run in this source record is a replacement for live worker START/result/acceptance or physical cooling proof.
5. **Macro sparse helper #9194 is merged** (2026-10-15, `40abd9bd2291997cc066f30b408a1e670124cec4`), but exact helper installation on Ubuntu donor hosts is not established by merge alone. The separate accepted-worker GC PR [#9430](https://github.com/mastermindx-market-intelligence/macro/pull/9430) remains OPEN. Preserve both release boundaries.

## Current capacity observation

Four Ubuntu host configuration ceilings remain **12 / 18 / 12 / 12** (54 configured aggregate slots) with thermal gates. The incumbent 24-hour collector sample contained about **1,324 minute observations per host**; Ubuntu1 peaked **86°C** with only nine observed lanes against its **80°C** admission cutoff. No sustained 54-worker or even host-max representative test was performed; do not turn this figure into a claimed safe sustained throughput.

**Additional scope distinction:** Some Ubuntu user-local Codex configs explicitly have `max_concurrent_threads_per_session = 1`. This is **not** the Fabric physical `max_active` limit. The installed Fabric Go/GLM-Codex/MiniMax-Codex executors construct independent lane-private `CODEX_HOME` from their own `ext/codex_*/config.toml`. Do not change native subagent nesting to “repair” Fabric capacity without an explicit root/grant/provider concurrency analysis.

**Status:** source-only reviewer aid; #1404 remains the incumbent modifying source/release carrier; #1552 is not a production integration authority.
