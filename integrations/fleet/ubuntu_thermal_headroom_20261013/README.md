# Ubuntu Fabric thermal headroom — 2026-10-13

**Status:** Installed and observed on the existing M2 Fabric controller; independent source-record draft. NOT proof of sustained physical cooling. This is **not** the separate, held Ubuntu 0/3 host telemetry deployment in PR #1363. No denied host-side activation was retried, and no existing worker, lease, or provider was migrated.

## Why and owner

The Chairman observed bursts around 95–97°C on the Ryzen 9 9950X Ubuntu 2/3 machines and roughly 90–94°C on Ubuntu 0. The installed Fabric already had one host telemetry puller, a 90°C temperature admission check for Ubuntu 0/2/3, cache-aware host selection, and an atomic live last-mile check inside `lane_runtime.LaneLease.acquire`. Existing CPU-heavy jobs can still boost while in flight. This change conservatively reduces **new** worker pressure and routes toward cooler eligible hosts without inventing another scheduler or worker-process controller.

The original M2 Fabric deployment is under:
`~/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext`

Existing owners:
- `hosts.json`: host roles/limits/qualification; both `host_pick.py` and `remote_sub.sh` use this, and new launches pass limits to `LaneLease`.
- `host_pull.sh` + existing LaunchAgent `com.mastermind.host-pull`: exclusive telemetry loop and per-host snapshot files `state/hosts/*.json`.
- `host_pick.py`: provider-neutral placement evaluation and eligible-host ranking.
- `lane_runtime.py`: last-mile physical admission; **not modified**.

## Installed operational changes (Oct 13 UTC)

| Target | Before | After |
|---|---|---|
| Ubuntu 0/2/3 `max_active` | 32 | 12 |
| Ubuntu 0/2/3 `load_gate` (1m load) | 16 | 8 |
| Ubuntu 0/2/3 `cpu_tctl_limit_c` | 90°C | 85°C |
| `host_pull.sh` interval | 150 seconds | 60 seconds |
| `host_pick.py` default max age | 600 seconds | 180 seconds |
| Eligible hot-host ranking | load and free lane fraction only | existing rank minus up to 0.20 as CPU approaches thermal cutoff |

Temperature penalty begins 25°C below the configured cutoff and increases linearly toward the cutoff; it applies only to hosts explicitly enrolled in the existing thermal gate and only **after** eligibility has passed. It does not authorize dispatch, expand capacity, or override native source/worker reservation checks. No existing worker is stopped or paused. Ubuntu 1's original policy is preserved: its package telemetry is observed but **not** last-mile temperature-gated by the current AMD-only `lane_runtime._linux_cpu_tctl_c` reader.

The script delta is in [host_pick_collector.patch](host_pick_collector.patch). The host-registry change is a data-only policy adjustment to the three keys on each of the three hosts, **not** a wholesale registry replacement.

### Installation/rollback identities

| Installed object | Before SHA-256 | After SHA-256 | Exact local backup |
|---|---|---|---|
| `hosts.json` | `1fb365f982c19f94e4241e5e8cbc1c449f3fce5051d70f235205868cdd9b8393` | `8ac7c8ff4fe20cbc006767384c071732538bbde5dfecc084648edd23cdce7014` | `hosts.json.bak-thermal-headroom-20261013` |
| `host_pull.sh` | `22c68f40ef4bb2e7157c29979141aa867d53a97e9ab0572a8280c27a51a47f1c` | `65b294a5ea2d17a9d7832307372bdb07262da62b5106a1ecad9ffa6c2b5cd9ad` | `host_pull.sh.bak-thermal-headroom-20261013` |
| `host_pick.py` | `c0cf204cf9edddaddee60973a83ab180275a5416e333e89c206ca3e5d67e462c` | `4342ad60605208ccce2b6fb558811fcd0f72391b09dd7abcb3b0a2ea8445be04` | `host_pick.py.bak-thermal-headroom-20261013` (base) and `host_pick.py.bak-thermal-score-20261013` (cadence-only variant) |

**Rollback fence:** Before any rollback, compare actual current file hashes and current source/owner work. Restore only known target files with CAS/atomic replacement while preserving all intervening accepted updates. For the collector, reload the **same** `com.mastermind.host-pull` LaunchAgent, not a new daemon. A late source writer or active dependent transition invalidates automatic rollback.

## Verification performed

1. A candidate `host_pick.py` was compiled prior to publication; collector replacement passed `bash -n`.
2. Deterministic in-memory fixtures verified that for equally loaded eligible hosts 60°C ranks above 80°C (penalty 0.16), temperatures above 85°C remain ineligible, and stale thermal evidence remains ineligible.
3. Compared old/new picker on the **same** live snapshot across all 15 registry hosts: all existing admission gates and eligibility outcomes were identical. Only advisory rank of eligible thermal-enrolled hosts differed.
4. Current picker readback showed `max_active=12` and `load_gate=8` on the target hosts and refused Ubuntu 0 at Tctl 90.625°C against 85°C. No worker dispatch was performed.
5. The existing LaunchAgent was restarted in place and read back with the log entry `2026-10-13T08:42Z [pull] daemon start pid=87840 interval=60s`. All four Ubuntu cache files refreshed afterward with `reachable=true`. The picker parser returned default max age 180 seconds.
6. Observed Ubuntu CPU readings following this restart included ~75.6°C (Ubuntu 0), 62°C (Ubuntu 1), 62.9°C (Ubuntu 2), and 60.9°C (Ubuntu 3). These are point readings, **not** controlled comparative proof that the new policy reduced peak CPU temperature.

**Capability state:** `PROVEN_LIVE` for installed collector cadence and new-job admission/ranking at M2, `NOT_PROVEN` for sustained temperature reduction / throughput performance under representative load. This branch is a source/evidence record; creating this PR does **not** install anything across all accounts or hosts.

## Continuous thermal trend in the original Fabric log

The existing `host_pull_backend.py` now prints **only validated numeric fields** (`tctl_c`, `load1`, `cpu_busy_pct`, `active_lanes`) alongside its existing per-host `reachable` response. These lines are captured by the same supervised `state/host_pull.log`, at the 60-second collector cadence. The canonical host snapshot `state/hosts/<host>.json` remains the sole host picker input; this log adds no scheduler, history authority, remote agent, listening socket or admission condition. Its text diff is in [collector_trend_logging.patch](collector_trend_logging.patch).

The backend's installed SHA-256 changed from `6c10385be89c32627bbb87a5f088e36e849de84b0635f02d460138d8e6884ad5` to `fb68aa42f8b06c7a8929f68b066953e12dc42efa219ae30d1c674b0e346bf87b`; original backup `host_pull_backend.py.bak-thermal-trend-20261013` is retained on M2. Validated candidate code in an isolated temporary telemetry state, then ran the original host collector against Ubuntu 2/3 using a second **isolated temporary state directory** (without touching their Fabric state or workers). Result: `reachable=true`, observed Tctl/load/CPU busy/active lanes with matching generated JSON. Later, the **already-running original LaunchAgent** wrote real lines for all four Ubuntu nodes at 08:57Z on October 13, 2026. LaunchAgent PID 87840 stayed unchanged; no restart or extra collector was needed.

This retains periodic snapshots sufficient to inspect future under-load trends, not high-resolution millisecond thermal telemetry, a persistent remote streaming connection or proof of active CPU heat control. The existing log's long-term rotation/retention should be checked by its owner before interpreting it as unlimited historical storage.

## Remaining in-scope work and honest boundary

The 9950X is a 170W TDP desktop CPU with a 95°C Tjmax. Boosting toward 95°C under sustained CPU workloads can be normal, but offers little reserved headroom. New-job gating does not reduce the power consumed by incumbents. To improve **physical thermal headroom** on Ubuntu 2/3, inspect each host's real BIOS/PBO/Eco Mode, cooler and case airflow, and actual available Linux `amd-pstate` governor/EPP support through an authorized host administrator. Favor a reversible BIOS **105W Eco Mode** (if supported) with baseline settings recorded before any change; avoid unverified undervolting, custom firmware writes, or untested OS-side power caps. Ubuntu 0 has a different CPU/thermal envelope: do not apply desktop 9950X settings to it.

After hardware tuning, run a bounded representative CPU-heavy worker workload at known concurrency (and idle baseline), capture at least 10 minutes of Tctl, frequency, fan RPM where exposed, load, PSI, worker throughput, errors, and cooldown recovery, then adjust the 12/8/85 policy conservatively only with evidence. Check Ubuntu 1 independently before enabling Intel last-mile thermal admission because the installed `lane_runtime` reader currently targets AMD k10temp. PR #1363's separate collector activation remains held under its original source/carrier rules.

There is no guarantee that monitoring itself cools the CPUs: monitoring steers **future** placements; OS/BIOS power and physical cooling govern sustained heat.

## Follow-up — continuous heat recovery and host power authorization

**Live M2 additions in this same original collector/picker (October 13 UTC):** `host_pull_backend.py` SHA-256 `fb68aa42f8b06c7a8929f68b066953e12dc42efa219ae30d1c674b0e346bf87b` → `3438939de34fc9279d7c84f1d064285467f27c4dee1ebb874fb598141bb9c798`; `host_pick.py` SHA-256 `4342ad60605208ccce2b6fb558811fcd0f72391b09dd7abcb3b0a2ea8445be04` → `7ee0ef91ede57053ce3e2af45b966e43c227413f3accc0e08a0af6914a486042`. Existing-file backups: `host_pull_backend.py.bak-thermal-recovery-20261013`, `host_pick.py.bak-thermal-recovery-20261013`. Exact follow-up diff: [thermal_recovery.patch](thermal_recovery.patch).

A *single existing per-host telemetry snapshot* now carries bounded, validated `thermal.risk`, `thermal.cooldown_until`, and `thermal.rise_c_per_min`. The incumbent host picker treats cooldown as an **additional** admission hold for enrolled thermal hosts only: Tctl ≥92°C holds automatic placement 600s; ≥85°C holds 240s; Tctl ≥75°C with an observed rise ≥10°C/min holds 180s. A hot spike extends but never cancels an existing longer hold. Missing legacy cooldown is backward-compatible; malformed present cooldown fails closed. Last-mile `LaneLease` and worker custody remain unchanged. Existing workers are neither stopped nor moved.

**Deterministic acceptance exercised on M2:** critical, recovering, hold expired, baseline, rapid rise, malformed present field, optional missing field, and unchanged eligibility on 15 live host snapshots before candidate installation. A live-path CLI smoke verified a 94°C sample sets a 600s hold; subsequent existing collector snapshots were read back with the new risk and cooldown fields. There is no claim of longitudinal temperature improvement yet.

**Measured heat despite first mitigation:** 403 one-minute Ubuntu host observations over 08:57–10:47 UTC. Ubuntu 0 mean 64.4°C, peak 95.25°C (16 readings ≥90°C); Ubuntu 1 mean 66.5°C, peak 87°C (none ≥90°C); Ubuntu 2 mean 69.1°C, peak 97°C (22 readings ≥90°C); Ubuntu 3 mean 64.9°C, peak 96.625°C (24 readings ≥90°C). Multiple ≥90°C samples on Ubuntu 2/3 had **zero Fabric active lanes**, so active heat must not be attributed solely to Fabric workers. Simulating the cooldown against ~108 historical observations per AMD host found 17 additional safe admission pauses on Ubuntu 0, 24 on Ubuntu 2, and 14 on Ubuntu 3; this is a hypothetical placement count, not a live cooling benchmark.

**Physical host power finding and permission boundary:** Ubuntu 2 Ryzen 9 9950X was configured with `amd-pstate-epp` `performance` governor, EPP `performance`, and `powerprofilesctl get=performance`, while otherwise similar Ubuntu 3 used `powersave`/`balance_performance` and system `balanced`. The ordinary Ubuntu 2 `powerprofilesctl set balanced` change was **denied** by `org.freedesktop.DBus.Error.AccessDenied: Not Authorized: org.freedesktop.UPower.PowerProfiles.switch-profile`. **No power-profile modification occurred. Do not bypass that denial through sudo, a different carrier or untrusted D-Bus impersonation.** The required administration action is an authorized local profile change (interactive login/approved host-administration pathway); then verify readback and benchmark thermals/throughput. A BIOS AMD 105W Eco Mode/PBO limit also requires hardware-specific admin access and baseline/reversion, and Ubuntu 0 is a mobile 9955HX, not a desktop 9950X. AMD's published 9950X Tjmax is 95°C and it recommends liquid cooling for optimal performance: https://www.amd.com/en/products/processors/desktops/ryzen/9000-series/amd-ryzen-9-9950x.html.

**Independent capacity gate discovered after installation:** both previous and current host picker returned no automatically eligible Grok host because of untouched **disk** floors, not a new thermal regression: Ubuntu 0 297.6GiB available vs 300GiB minimum; Ubuntu 1 143.4 vs 150; Ubuntu 2 140.7 vs 150; Ubuntu 3 202 vs 300. Do not reduce safety floors merely to show placement. Any cleanup must preserve active worktrees, other writers and source/storage leases. The disk dependency is a distinct issue from CPU thermal headroom.

**Next physical proof:** when the authorized host-power channel is available, capture idle and 15-minute equivalent CPU-heavy representative loads on Ubuntu 2/3 with profile, governor, Tctl, frequency, utilization, power where exposed, thermal warnings and worker throughput. Determine board cooling/fan telemetry; do not invent fan RPM where hwmon does not expose it. Only then qualify relaxed/new Fabric host concurrency limits. This PR remains draft and does not close the parent physical-headroom outcome.

## Live process attribution without extra agents (11:09 UTC)

The existing `host_pull_probe.template` now performs a bounded ~150 ms, process-start-identity-fenced `/proc/<pid>/stat` CPU delta sample during a warm host probe (Tctl ≥75°C), returning only up to five `pid/start_ticks/cpu_pct/comm` records; no argv, environment, open files or credential material. The existing `host_pull_backend.py` validates the field and stores nonauthoritative `thermal.top_cpu_processes` inside the same current snapshot. The collector's normal log includes a bounded top-CPU summary only when the CPU is already HOT or CRITICAL. Source diff: [hot_process_diagnostics.patch](hot_process_diagnostics.patch). This is not another host daemon or admission authority.

**Installed M2 identities:** `host_pull_probe.template` SHA-256 `2db9af35d7ae0262c94e49b21d318e11e0d58fd4a62e5601453c3403874ced8a` → `10ff206fb7050210e502d03c6916c092b2d82a2b8929d4b54b9cfe5b97bbea72`; `host_pull_backend.py` `3438939de34fc9279d7c84f1d064285467f27c4dee1ebb874fb598141bb9c798` → `a67d02455984992c64ac1a380abe01509ddcdbd12a800897fa1831601bca0f1e`. Backups are `host_pull_probe.template.bak-hot-process-20261013` and `host_pull_backend.py.bak-hot-process-20261013`. Original LaunchAgent `com.mastermind.host-pull` was restarted in place, PID 42014, with `2026-10-13T11:09Z [pull] daemon start pid=42014 interval=60s`. All Ubuntu snapshots refreshed with the new field.

**Proof:** new embedded sampler Python compiled, whole shell parsed, read-only probe executed on actual Ubuntu 2, synthetic hotter branch returned bounded process data, and parser accepted a valid record while rejecting malformed input. The first live sample at 11:09 UTC recorded Ubuntu 2 rising at +54.26°C/min to 76.5°C and triggered a three-minute rising-heat cooldown. Sample process CPU percentages: `bluetoothd` 97.9%, `python3` 91.8%, two `chrome-headless` processes 49% and 36.7%. A second 0.8-second targeted sample found `bluetoothd` at **0%** and `python3` at **100%**; thus the first short Bluetooth sample does **not** prove a sustained runaway daemon. The sustained Python PID traced through `bash → claude → slot.py → sub.sh`, working within `/home/ubuntu2/lanes/wt/fif-a0-se-r2-20261013`. M2 `fabric_task.py status fif-a0-se-r2-20261013` was `NOT_FOUND`; the worktree name alone is not a canonical controller run identity. No processes or workers were stopped.

**Interpretation and held effects:** A minority of heavy processes can boost specific CPU cores even with modest machine-average utilization. For true physical heat reduction, preserve the authenticated OS/BIOS host-admin gate, check BIOS Eco Mode/cooler/fan and power profiles, and benchmark worker throughput versus Tctl under matched load. The evidence is sufficient to improve awareness and decline new hot/rising placements, not to claim resolved cooling, host profile changes, or server-wide worker-run attribution.
