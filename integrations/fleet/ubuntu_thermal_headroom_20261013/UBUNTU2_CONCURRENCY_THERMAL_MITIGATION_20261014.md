# Ubuntu2 thermal load-shed admission — 2026-10-14 UTC

**Operational status:** `PROVEN_LIVE` for existing M2 Fabric host-registry admission, **NOT_PROVEN** for sustained hardware cooling. Preserves original running worker custody. This is a narrowly scoped direct Ubuntu2 admission adjustment; no new scheduler, process controller, restart, Linux privilege action or telemetry daemon.

## Direct observed incident and 10-hour evidence

On **2026-10-14 04:03–04:04 UTC** on `ubuntu2`, with 9 active Fabric lanes, M2's 60-second collector reported Tctl **95.625°C** (critical) and one-minute system load ~9.29; a separate immediate host hwmon read gave **94.625°C**, while the CPU governor and EPP were both `performance`. The existing thermal gate automatically refused new placements at 85°C and retained a 600-second recovery window. A bounded host process census showed multiple Python and Git processes each consuming nearly one logical CPU; they were executing user work and were **not** terminated, signaled or reniced.

From the original M2 `state/host_pull.log`, 524 matched Ubuntu2 samples were available over the preceding ten hours. Counts/peaks by concurrently observed Fabric lane count:

| Fabric active lanes | 60-second samples | Highest Tctl | Samples ≥90°C |
|---:|---:|---:|---:|
| 0 | 177 | 62.5°C | 0 |
| 1 | 97 | 68.5°C | 0 |
| 2 | 69 | 77.375°C | 0 |
| 3 | 75 | 79.625°C | 0 |
| 4 | 24 | 72.75°C | 0 |
| 5 | 17 | 77°C | 0 |
| 6 | 13 | 77.875°C | 0 |
| 7 | 12 | 81°C | 0 |
| 8 | 6 | 76°C | 0 |
| 9 | 18 | 95.625°C | 4 |
| 10 | 13 | 95.875°C | 2 |
| 11 | 3 | 62.375°C | 0 |

All six observed ≥90°C samples belonged to lanes 9–10; however, other CPU-intensive non-Fabric work, workloads, thermal inertia, room conditions and sparse sampling confound any causal inference. **Do not interpret this as a proven safe 6-lane temperature ceiling.** The machine retains an AMD Ryzen 9 9950X with a 95°C published operating temperature maximum, and its unauthorized remote `powerprofilesctl set balanced` operation remains denied.

## Verified installed admission-only change

Physical M2 controller path: `~/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/hosts.json`.

For **ubuntu2 only**:
- `max_active`: 12 → **6**
- `load_gate` (1-minute load): 8 → **6**

All other hosts and keys are unchanged; `cpu_tctl_limit_c=85`, `require_thermal=true`, existing `min_free_gb=150`, `checkout_reserve_gb=15`, and the lane lease/storage/thermal predicates are unchanged. Incumbent 9-worker count can remain above 6 until existing worker owners settle naturally; the new cap is a **new-job admission hold**, not an active shutdown or forced lease transition.

**CAS provenance:** `hosts.json` SHA-256 before `7688ae6c7a713f48e1eaf78c7111bc176e0df718f3d52c897b4249674c5ed92b` → installed `52593077d4d10087dbb80d47ae31f952610d2e1351cbe2f7b6741c9151ed3120`. Local exact rollback backup `hosts.json.bak-ubuntu2-concurrency-20261014`, created before a same-inode/same-hash check and atomic replacement. Readback verified only two target fields changed. **Do not automatically restore** if the source hash has since drifted or a competing writer has changed the register.

An actual M2 `host_pick.py --mode grok --explain --json` run after publication returned `ubuntu2 eligible=false`, including `lane-ceiling FAIL 9<6 (lane_ceiling=32, max_active=6)` and `load FAIL 9.83<6`, while its disk and instantaneous Tctl (84.625°C) gates were PASS. The original `remote_sub.sh` embedded registry parser was separately executed with this exact installed file and read back `max_active=6, load_gate=6`, `minimum disk = 165 GiB`. Thus the change is **installed and selected by the existing picker/launcher**, but no new provider job has been dispatched merely to test it.

## Finish requirements

1. Track naturally declining workers at the original Fabric controller; compare equivalent busy workloads with 0–6 lanes versus previous 9–10 lane heating, including 60-second peaks and real throughput/error metrics. Do not repeatedly poll an unchanged worker to extend the session or mistake one quiet reading for proof.
2. Finish the **attended UEFI MSI MAG B850M MORTAR WIFI 85°C PBO Thermal Point** or documented Eco Mode qualified maintenance from the board-specific runbook. The firmware remains **NOT_CHANGED**.
3. Reassess this conservative max-6/load-6 policy only with enough repeatable workload/cooling evidence, under source CAS and original owner constraints. Do not trade away thermal reserve to increase token-throughput claims.
4. Preserve the existing source/owner boundaries of Macro draft #9194 (not yet production activated), Mastermind draft #1404, and the earlier separate Ubuntu0/3 collector hold.

## First 19 live samples following the admission change

The first bounded follow-up at **2026-10-14T04:31Z** examined the original M2 `state/host_pull.log`, beginning at least one minute after the installed file's verified 04:06:39Z mtime (so as not to misattribute a pre-policy reading). **19 matched 60-second observations per host** were available:

| Host | Mean Tctl | Peak Tctl | ≥85°C / ≥90°C readings | Observed lane range |
|---|---:|---:|---:|---:|
| Ubuntu0 | 51.0°C | 66.75°C | 0 / 0 | 0–4 |
| Ubuntu1 | 68.7°C | 80.0°C | 0 / 0 | 1–4 |
| **Ubuntu2** | **64.1°C** | **84.0°C** | **0 / 0** | **1–9** |
| Ubuntu3 | 40.2°C | 59.625°C | 0 / 0 | 0–1 |

Ubuntu2's earlier incumbents declined naturally below the newly configured `max_active=6` without an operator signal, worker termination or lease migration. Thus the live mitigation did not interrupt existing workers and temperatures were below the 85°C hardware-reading cutoff in this initial sampled interval.

**Inference boundary:** 19 discrete per-minute samples in a confounded, declining-workload interval are neither matched before/after throughput evidence nor proof that a six-lane limit keeps 9950X below the desired thermal point in every regime. The BIOS 85°C PBO Thermal Point/Config TDP and physical cooler remain untouched; no elevated remote profile switch was attempted. Retain the original physical-headroom acceptance obligation and the exact rollback/source-CAS fence above.
