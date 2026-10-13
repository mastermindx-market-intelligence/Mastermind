# Ubuntu 2 and 3 — physical thermal-headroom maintenance runbook

**Prepared October 13, 2026. State: READY_FOR_ATTENDED_HARDWARE_ACTION / NOT_APPLIED / NOT_ACCEPTED.**

## Exact host grounding

| Host | Hostname | CPU | Motherboard | BIOS | OS power profile last verified |
|---|---|---|---|---|---|
| Ubuntu 2 | `ubuntu2` | AMD Ryzen 9 9950X, 16 cores/32 threads | MSI MAG B850M MORTAR WIFI (MS-7E61) | `1.A40` | `performance`, `amd-pstate-epp` governor `performance`, EPP `performance` |
| Ubuntu 3 | `ubuntu3-MS-7E61` | AMD Ryzen 9 9950X, 16 cores/32 threads | MSI MAG B850M MORTAR WIFI (MS-7E61) | `1.A40` | `balanced`, `amd-pstate-epp` governor `powersave`, EPP `balance_performance` |

These identities were read from `/sys/class/dmi/id/{board_vendor,board_name,bios_version}` and `/proc/cpuinfo`, not inferred from host names.

AMD specifies the desktop Ryzen 9 9950X at 170 W default TDP, 95°C Tjmax and liquid cooling recommended for optimal performance: https://www.amd.com/en/products/processors/desktops/ryzen/9000-series/amd-ryzen-9-9950x.html

The **exact MSI MAG B850M MORTAR WIFI** product page documents **PBO Thermal Point** profiles at 85/75/65°C and **Config TDP** with Eco Mode: https://us.msi.com/Motherboard/MAG-B850M-MORTAR-WIFI/Overview . This is a motherboard-specific feature description, not proof of the current UEFI option's exact location or of a completed setting.

### Why board-level headroom matters

The installed Mastermind Fabric controller collects Tctl every 60s, refuses new automatic placement at 85°C on Ubuntu2/3, and applies a cooldown after a rise/peak. **It does not control power already being consumed by an existing Python/Chrome worker or non-Fabric process**. Observed one-minute peaks earlier on October 13 included Ubuntu2 97.0°C and Ubuntu3 96.625°C; a later four-hour window had no >=85°C readings but did not include controlled matched-load proof.

Ubuntu2's ordinary `powerprofilesctl set balanced` call returned the specific OS authorization denial `org.freedesktop.UPower.PowerProfiles.switch-profile`. No sudo/PolicyKit bypass is authorized by this artifact. Treat a denial as terminal for that action; use an attended authorized host console rather than replaying the refused operation by a different carrier.

## Attended maintenance procedure, one host at a time

1. **Preserve custody:** Query Executive/Fabric for active, unknown-effect or unreleased workers and their original parent; schedule a real maintenance window. Never equate the count of visible processes with leases. If any worker is active or effect-unknown, do not reboot or kill it; settle through its original owner first.
2. **Baseline evidence:** Before changing firmware, capture `powerprofilesctl get`, read-only `/sys/class/hwmon` CPU Tctl, per-core frequency, board and BIOS identification, 60s collector Tctl/log samples, and a representative normal workload throughput/latency reference. Record case/cooler model and visually inspect fan/pump speed, mounting, radiator flow, and dust. On these boards, the CPU fan reading was **not** exposed in the observed hwmon telemetry, so do not invent fan RPM or AIO pump health.
3. **Record firmware state:** From the authorized local display/keyboard, reboot into MSI UEFI and photograph/export the **existing** PBO Thermal Point, Config TDP, Precision Boost Overdrive, CPU fan/pump/curve and any OC/Performance Switch options. Do not update BIOS or reset unrelated settings as part of this thermal slice.
4. **First reversible trial:** Find the MSI **PBO Thermal Point** control and choose **85°C** only if the actual `1.A40` BIOS exposes that documented option for the installed 9950X. Keep voltage/Curve Optimizer/PBO tuning otherwise unchanged; make **one** change and record it. The exact BIOS menu location is firmware-version-specific; never invent a menu path if the UI differs.
5. **Do not combine with Eco Mode initially.** If the 85°C profile is absent or inadequate, separately consider the BIOS Config TDP/Eco Mode option, with its exact shown wattage/current ceilings recorded. Do not assume a 105W entry exists. `65W` Eco Mode could meaningfully reduce multithreaded performance and requires an explicit benchmark tradeoff decision.
6. **OS-side balanced option:** For Ubuntu2 only, a locally authorized interactive user may select the desktop's Balanced power profile separately. Verify `powerprofilesctl get`, the governor and EPP afterward. Do **not** reattempt the earlier denied remote profile change through sudo or alternate credentials.
7. **Single-host acceptance:** Boot and prove normal SSH/Tailscale, original mounts and worker tools remain healthy; validate collectors show board temps and support-releases are intact. Compare matched 10–15 minute representative CPU-active workloads before/after, capturing every available Tctl sample, max and high percentile, worker throughput, wall time, IO PSI, CPU throttling flags, errors and CPU governor. Monitor normal peak workloads as well as unloaded idle.
8. **Release criterion:** Thermals should remain within the chosen BIOS target subject to sensor/BIOS semantics, with documented throughput and stability impact. A lower peak during idle alone is not acceptance. If results fail or critical services regress, revert the single firmware change from the photographed baseline in an attended maintenance window.
9. **Then repeat on the other 9950X host** only if the first host has clean source, stability, and throughput proof. Ubuntu0 is a mobile Ryzen 9 9955HX on a different vendor board; do not apply desktop 9950X BIOS instructions there. Ubuntu1 is Intel Core Ultra 9 285K/Alienware, also separate.

## Fabric dependencies and non-goals

No new monitoring daemon, USB firmware tool, privileged control agent, CPU throttler, host load balancer, or worker lifecycle is authorized by this document. Existing Fabric host admission and immutable support-releases remain the authoritative runtime owners; GitHub PR #1404 records the current controller source and evidence. The separate draft collector PR #1363 retains its earlier hold.

**Status distinction:** Board identity **verified**; feature availability **documented by MSI**; OS Remote power-profile action **access denied**; UEFI settings **not read or changed**; matched heavy-load thermal headroom **not proven**; no physical-worker restart authorized.
