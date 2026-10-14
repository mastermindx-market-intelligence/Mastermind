# Ubuntu3 9950X thermal excursion and temporary lane admission — 2026-10-14 UTC

**State:** Existing M2 Fabric admission modification **INSTALLED AND LIVE-READBACK VERIFIED**. Sustained thermal relief, physical board control and throughput acceptance remain **UNPROVEN**. No running worker was stopped or reniced. The previous denied Ubuntu2 power-profile operation was not retried on any host.

## Measured excursion

At 2026-10-14 ~05:19–05:22 UTC Ubuntu3 (MSI MAG B850M MORTAR WIFI / Ryzen 9 9950X / UEFI 1.A40) reached **95.375–96.375°C Tctl** with **two** concurrent Fabric lanes, a one-minute load average around 6.2–7.8, and many user Python/Git processes individually using nearly 100% of one logical CPU. A direct host `/sys/class/hwmon` read gave **95.75°C** and CCD1 93.75°C. The OS governor was already `powersave` with `balance_performance` EPP; therefore Ubuntu2's Performance-profile explanation does **not** cover Ubuntu3. Host admission telemetry classified **HOT/CRITICAL** and was refusing new workers at the existing 85°C cutoff. Admission does not cool existing boost/PBO loads.

Original M2 collector history over the most recent eleven hours contained **576 valid Ubuntu3 per-minute observations**:

| Observed Fabric lanes | Samples | Peak Tctl | ≥80°C | ≥90°C |
|---:|---:|---:|---:|---:|
| 0 | 391 | 66.0°C | 0 | 0 |
| 1 | 82 | 70.75°C | 0 | 0 |
| 2 | 36 | **96.375°C** | 10 | 2 |
| 3 | 33 | 80.125°C | 1 | 0 |
| 4 | 16 | 74.875°C | 0 | 0 |
| 5 | 5 | 68.25°C | 0 | 0 |
| 6 | 2 | 64.625°C | 0 | 0 |
| 7 | 11 | 89.75°C | 1 | 0 |

This is *not* a controlled concurrency/temperature causal curve: workload shape, non-Fabric processes, time in boost and ambient/cooling conditions differ. The data supports a **temporary conservative admission hold** until an attended thermal limit can be qualified; it does not establish that one lane is physically guaranteed safe.

## Live controller change, original owner only

Controller `hosts.json` Ubuntu3 fields:
- `max_active`: **12 → 1**
- `load_gate`: **8 → 4**
- `cpu_tctl_limit_c`: **85.0°C → 80.0°C**

All other existing host configurations unchanged. Ubuntu3 retains `min_free_gb=300`, `checkout_reserve_gb=15`, `require_thermal=true`, its original `lane_ceiling=32`, and the original `LaneLease`/collector ownership.

Exact original file CAS SHA-256: `52593077d4d10087dbb80d47ae31f952610d2e1351cbe2f7b6741c9151ed3120` → **`ccda5a87d4e627486a0017a6fe7be79ab2b8d0e400c3ff1212d8860d30d6090f`**. Recoverable local exact backup: `hosts.json.bak-ubuntu3-concurrency-20261014`, in same incumbent M2 Fabric `ext` folder. Backup saved before same-inode/same-hash verified atomic replacement, with post-update readback. Never roll back without checking current source/writer/ownership and actual effect.

Live original launcher registry parser returned Ubuntu3 `max_active=1, load_gate=4, Tctl_limit=80.0, minimum_disk=315.000 GiB`. The live `host_pick.py --mode grok --json` returned **ineligible** with independent fail reasons `load 6.53<4`, `lane-ceiling 2<1`, `cpu_tctl 90.25>=80°C` and a 470-second recovery hold. This is `PROVEN_LIVE` at source/selected/admission level; no new worker was dispatched merely to demonstrate refusal.

## Next physical action and performance law

At the authenticated host console, schedule a maintenance window after existing workers are reconciled by their original owner. Record BIOS PBO/TDP/thermal/fan settings and cooler/pump status; trial the **85°C PBO Thermal Point** documented for this exact MSI board, then compare before/after Tctl, CPU clocks, throughput, run errors and worker results over a matched 10–15 minute workload. Do not combine 85°C firmware profile and power limit changes in one untraceable effect. Board-level controls still require attended access; no BIOS restart or remote privileged workaround occurred here.

Maintain the one-lane limit only while no accepted physical cooling proof exists; revise using real workload/performance evidence and exact file CAS, not an arbitrary timer or desire for more frontier sessions.
