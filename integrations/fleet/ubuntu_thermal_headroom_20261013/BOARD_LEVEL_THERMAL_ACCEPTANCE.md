# Ubuntu 2 and 3 — physical thermal-headroom maintenance runbook

**Prepared October 13, 2026. State: READY_FOR_ATTENDED_HARDWARE_ACTION / NOT_APPLIED / NOT_ACCEPTED.**

## Exact host grounding

| Host | Hostname | CPU | Motherboard | BIOS | OS power profile last verified |
|---|---|---|---|---|---|
| Ubuntu 2 | `ubuntu2` | AMD Ryzen 9 9950X, 16 cores/32 threads | MSI MAG B850M MORTAR WIFI (MS-7E61) | `1.A40` | `balanced`, governor `powersave`, EPP `balance_performance` (direct read 2026-10-16 00:07 UTC) |\n| Ubuntu 3 | `ubuntu3-MS-7E61` | AMD Ryzen 9 9950X, 16 cores/32 threads | MSI MAG B850M MORTAR WIFI (MS-7E61) | `1.A40` | `balanced`, `amd-pstate-epp` governor `powersave`, EPP `balance_performance` |

These identities were read from `/sys/class/dmi/id/{board_vendor,board_name,bios_version}` and `/proc/cpuinfo`, not inferred from host names.

AMD specifies the desktop Ryzen 9 9950X at 170 W default TDP, 95°C Tjmax and liquid cooling recommended for optimal performance: https://www.amd.com/en/products/processors/desktops/ryzen/9000-series/amd-ryzen-9-9950x.html

The **exact MSI MAG B850M MORTAR WIFI** product page documents **PBO Thermal Point** profiles at 85/75/65°C and **Config TDP** with Eco Mode: https://us.msi.com/Motherboard/MAG-B850M-MORTAR-WIFI/Overview . This is a motherboard-specific feature description, not proof of the current UEFI option's exact location or of a completed setting.
 MSI also documents Precision Boost Overdrive selection under EZ Config for selected AMD platforms, then F10 to save; verify the actual BIOS1.A40 on-device path rather than assuming it: https://www.msi.com/Landing/msi-click-bios-intel-amd-motherboard .\n
### Why board-level headroom matters

At the latest direct 2026-10-16 00:07 UTC evidence, the installed Mastermind Fabric controller collects Tctl every 60s and refuses **new** Ubuntu2/3 placement at **80°C**, with the incumbent cooldown after a rise/peak. The 85°C value elsewhere in this document is the **proposed BIOS firmware PBO Thermal Point**, not the current Fabric admission threshold. This is a timestamped observation, not permission to overwrite a newer emergency derate.\n
Historically, an Ubuntu2 `powerprofilesctl set balanced` attempt returned `org.freedesktop.UPower.PowerProfiles.switch-profile` AccessDenied. The source of the subsequent profile change is unknown, but at the direct 2026-10-16 00:07 UTC check Ubuntu2 **already reports Balanced**, as does Ubuntu3. Do not retry the denied operation through alternate credentials or make another unneeded OS profile change.\n

**Verified original-policy pin:** The M2 canonical `hosts.json` SHA256 `726ce27f38ecc8ce407cc0496e61ea66db3e731eb4ce3a60f9ae291a0321e048` has Ubuntu0/1/2/3 configured max_active **12/18/12/12**, and Ubuntu2/3 new-job admission **80°C** / load gate4. Earlier `1/1` emergency derates have already been restored: **DO_NOT_REDO_STATIC_RESTORE**. This is an observed snapshot, **not** an automatic restoration target; preserve any later authorized hot-host derate. Neither restored configured ceilings nor cool idle readings prove sustainable twelve-heavy-worker throughput.

## Attended maintenance procedure, one host at a time

1. **Preserve custody:** Query Executive/Fabric for active, unknown-effect or unreleased workers and their original parent; schedule a real maintenance window. Never equate the count of visible processes with leases. If any worker is active or effect-unknown, do not reboot or kill it; settle through its original owner first.
2. **Baseline evidence:** Before changing firmware, capture `powerprofilesctl get`, read-only `/sys/class/hwmon` CPU Tctl, per-core frequency, board and BIOS identification, 60s collector Tctl/log samples, and a representative normal workload throughput/latency reference. Record case/cooler model and visually inspect fan/pump speed, mounting, radiator flow, and dust. On these boards, the CPU fan reading was **not** exposed in the observed hwmon telemetry, so do not invent fan RPM or AIO pump health.
3. **Record firmware state:** From the authorized local display/keyboard, reboot into MSI UEFI and photograph/export the **existing** PBO Thermal Point, Config TDP, Precision Boost Overdrive, CPU fan/pump/curve and any OC/Performance Switch options. Do not update BIOS or reset unrelated settings as part of this thermal slice.
4. **First reversible trial:** Find the MSI **PBO Thermal Point** control and choose **85°C** only if the actual `1.A40` BIOS exposes that documented option for the installed 9950X. Keep voltage/Curve Optimizer/PBO tuning otherwise unchanged; make **one** change and record it. The exact BIOS menu location is firmware-version-specific; never invent a menu path if the UI differs.
5. **Do not combine with Eco Mode initially.** If the 85°C profile is absent or inadequate, separately consider the BIOS Config TDP/Eco Mode option, with its exact shown wattage/current ceilings recorded. Do not assume a 105W entry exists. `65W` Eco Mode could meaningfully reduce multithreaded performance and requires an explicit benchmark tradeoff decision.
6. **OS profile verification:** Both hosts already report Balanced with `powersave` governor and `balance_performance` EPP. Record these after BIOS, but make **no OS-side profile change** as part of this trial. Never retry the earlier denied remote profile change through sudo or alternate credentials.\n7. **Single-host acceptance:** Boot and prove normal SSH/Tailscale, original mounts and worker tools remain healthy; validate collectors show board temps and support-releases are intact. Compare matched 10–15 minute representative CPU-active workloads before/after, capturing every available Tctl sample, max and high percentile, worker throughput, wall time, IO PSI, CPU throttling flags, errors and CPU governor. Monitor normal peak workloads as well as unloaded idle.
8. **Release criterion:** Thermals should remain within the chosen BIOS target subject to sensor/BIOS semantics, with documented throughput and stability impact. A lower peak during idle alone is not acceptance. If results fail or critical services regress, revert the single firmware change from the photographed baseline in an attended maintenance window.
9. **Then repeat on the other 9950X host** only if the first host has clean source, stability, and throughput proof. Ubuntu0 is a mobile Ryzen 9 9955HX on a different vendor board; do not apply desktop 9950X BIOS instructions there. Ubuntu1 is Intel Core Ultra 9 285K/Alienware, also separate.

## Fabric dependencies and non-goals

No new monitoring daemon, USB firmware tool, privileged control agent, CPU throttler, host load balancer, or worker lifecycle is authorized by this document. Existing Fabric host admission and immutable support-releases remain the authoritative runtime owners; GitHub PR #1404 records the current controller source and evidence. The separate draft collector PR #1363 retains its earlier hold.

**Status distinction:** Board identity **verified**; feature availability **documented by MSI**; OS Remote power-profile action **access denied**; UEFI settings **not read or changed**; matched heavy-load thermal headroom **not proven**; no physical-worker restart authorized.
