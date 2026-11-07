# S5 host capability and acceptance map — 2026-11-07

This is a return from evidence already collected in the original S5 workstreams. It introduces no host registry and performs no new host inspection. Labels are the incumbent producer's labels; no new alias or physical-identity reconciliation is implied.

**Operating outcome:** no S5 collector, cleaner or recovery service was installed or activated; no live cleanup, manual maintenance run or service restart was performed. Attributable reclaimed bytes are **0**. Installed S5 acceptance remains open.

## Observation classes

| Class | Evidence and scope |
| --- | --- |
| Read-only installed/retained observations | Entry Studio observer fingerprint; existing retained host snapshots; same-UID Ubuntu unit/file/reserve metadata. These are observations at the recorded times. |
| Source canary | Corrected source observer through the already-configured launcher as the same user. It is not a cross-UID installed-service receipt. |
| Synthetic execution | Compiled desktop/mobile Fleet browser fixtures, storage and recovery fixtures, native/application admission fixtures and paired translation fixture. Their simulated installation/restart records are not host effects. |
| Naturally observed execution | Existing Ubuntu1–4 timer triggers advanced during a 252.587–264.679-second observation interval. Their cleanup effects and reclaimed bytes were not measured or attributed. |
| Actual admission refusal | Existing Ubuntu0 remote admission returned rc75 and `allowed=false` for temperature at/above its limit at controller time 08:45Z. No replacement worker dispatch was issued. |
| Applied S5 cleanup/recovery | **None.** No reclaimed-byte or installed recovery claim follows from the other rows. |

Sources: [entry observer](installed-observer-entry.json), [source canary](source-observer.json), [retained sensors](retained-sensor-coverage.json), [Ubuntu metadata](ubuntu-readonly-observations.json), [browser receipt](browser-receipt.json), [thermal refusal](thermal-admission-refusal.json).

## All 13 registered hosts: source canary at 06:23:57.643 UTC

The producer marks every row `advisoryOnly=true`, `physicalIdentityProven=false`, `placementAuthority=false` and `executionAuthority=false`. The observed mode-specific owner facts do not grant new capacity. S3 remains the placement consumer.

| Host label | Online flag | Fresh | Age seconds | Observed active lanes / effective limit | Installed version evidence in this session |
| --- | --- | --- | ---: | --- | --- |
| m1 | true | yes | 59 | 0 / 1 | Host collector/maintenance version UNKNOWN |
| m2 | true | yes | 59 | UNKNOWN / UNKNOWN | Entry Studio observer fingerprint below; host collector generation UNKNOWN |
| mb | true | no | 1370944 | retained 0 / 3, not usable | UNKNOWN |
| mini1 | true | no | 2350064 | retained 0 / 1, not usable | UNKNOWN |
| mini2 | true | no | 2350064 | retained 0 / 1, not usable | UNKNOWN |
| mini3 | false | no | 2350059 | UNKNOWN / UNKNOWN | UNKNOWN |
| mini4 | true | no | 2350058 | UNKNOWN / UNKNOWN | UNKNOWN |
| pc | false | no | 2350050 | UNKNOWN / UNKNOWN | UNKNOWN |
| ubuntu0 | true | yes | 56 | 2 / 12 | Current maintenance version UNKNOWN; current metadata read returned no stdout |
| ubuntu1 | true | yes | 55 | 0 / 18 | Existing Linux hygiene executable and units verified at 07:05 |
| ubuntu2 | true | yes | 53 | 2 / 12 | Existing Linux hygiene executable and units verified at 07:05 |
| ubuntu3 | true | yes | 52 | UNKNOWN / UNKNOWN; held | Existing Linux hygiene executable and units verified at 07:05 |
| ubuntu4 | true | yes | 51 | 0 / 2; original exclusions remain | Existing Linux hygiene executable and units verified at 07:05 |

Freshness is independent of the online flag: mb/mini1/mini2/mini4 retained `online=true` but were stale and excluded. Missing readings remain unknown. There were eight ready public accounts at entry while the physical fleet was degraded; this is not evidence that every model is entitled or every host admitted.

## Existing sensor coverage from retained snapshots

Capture time: 06:43:38.283415 UTC. Individual snapshot times are shown below. These measurements were already available through the incumbent procfs/hwmon/OS path. The Linux disk/lane projection gap was a parser mismatch; it did not justify installing another exporter.

| Host | Snapshot UTC | CPU/load | RAM and swap | Filesystem | Thermal | Occupancy |
| --- | --- | --- | --- | --- | --- | --- |
| m1 | 06:43:31 | Logical CPU count and load observed; precise busy% missing | Free/inactive estimate observed; available bytes, total RAM and swap missing | Free space observed | CPU/NVMe/fan missing | Known 0 |
| m2 | 06:43:32 | Logical CPU count and load observed; precise busy% missing | Free/inactive estimate observed; available bytes, total RAM and swap missing | Free space observed | CPU/NVMe/fan missing | UNKNOWN |
| ubuntu0 | 06:43:35 | procfs busy% observed | MemAvailable and swap observed; MemTotal missing | Free space observed | hwmon CPU/NVMe observed; fan missing | Known 3 |
| ubuntu1 | 06:43:37 | procfs busy% observed | MemAvailable and swap observed; MemTotal missing | Free space observed | hwmon CPU/NVMe and fan observed | Known 0 |
| ubuntu2 | 06:42:23 | procfs busy% observed | MemAvailable and swap observed; MemTotal missing | Free space observed | hwmon CPU/NVMe observed; fan missing | Known 1 |
| ubuntu3 | 06:42:24 | procfs busy% measured 0 | MemAvailable and swap observed; MemTotal missing | Free space observed | hwmon CPU/NVMe observed; fan missing | Held/UNKNOWN |
| ubuntu4 | 06:42:25 | procfs busy% measured 0 | MemAvailable and measured-zero swap observed; MemTotal missing | Free space observed | hwmon CPU/NVMe observed; fan missing | Known 0 |
| mb, mini1–4, pc | no current snapshot qualified in this inventory | Current coverage UNKNOWN | Current coverage UNKNOWN | Retained/UNKNOWN only | Current coverage UNKNOWN | Excluded |

The differing lane/disk samples at 06:23,06:43 and07:05 must not be combined as one atomic observation. Their changes are not attributable cleanup.

The forward candidate probe/adapter now supports measured Linux MemTotal from the standard OS field. It has not been installed. Original `source/` files and installation preimages remain unchanged. The retained snapshot path's generation `ef94479b8c768088e7c6b611d498879b9b6896ba24faa2558135ad8465f8be46` is provenance for that retained path, not proof of current native selection.

## Exact installed fingerprints observed

| Component | Observed scope | SHA256 |
| --- | --- | --- |
| Studio observer module | Entry M2 observation, before source edits; no overall capture timestamp was returned | `b1ca93566b50246a271dc1720b9e0328d9887d4c3b32b50a7b9ed7107a1fae5a` |
| Configured existing placement launcher | Verified before its permitted source-canary read; not a new native selection | `bc0b3559392a07f3d4f7109455765c14dbc4dc946f6cb5a788e547ae179dbf0f` |
| linux_hygiene.py | Ubuntu1–4 existing same-UID installed files | `3f676c0075478029e5857f0a95cd4ba9ae0dba9221eab312b034f88bca2502e3` |
| fabric-storage-reserve.json | Ubuntu1–4 existing reserve binding, 75 GiB | `9e4dc81b57d804ddd717829a09c1b1fd398de47dcfc908dc23029df486e65f59` |
| mastermind-linux-hygiene.service | Ubuntu1–4 effective original service unit | `6045337141d4b57911584ee39e0ffb972395bf546304419d26fe1a2e04f05bde` |
| mastermind-linux-hygiene.timer | Ubuntu1–4 effective original enabled timer | `60c382d2152fb96096655bd607f57b243e3afed1c31554d815427676b5770867` |

Owner UID 1000, file modes, inodes, effective ExecStart and empty drop-in lists were retained in the metadata receipt. They do not prove hostile-path confinement or first-party tunnel heartbeat health.

| Host | Second observation UTC | Available GiB | Existing reserve GiB | Last observed service exit | Actual observation interval |
| --- | --- | ---: | ---: | ---: | ---: |
| ubuntu1 | 07:05:34.482795 | 63.050690 | 75 | 0 | 252.587s |
| ubuntu2 | 07:05:29.144183 | 137.979107 | 75 | 0 | 259.624s |
| ubuntu3 | 07:05:30.862596 | 139.591492 | 75 | 1 | 253.568s |
| ubuntu4 | 07:05:32.650984 | 864.052849 | 75 | 0 | 264.679s |
| ubuntu0 | no current observation returned | UNKNOWN | historical 75; current unverified | UNKNOWN | no interval established |

All four timers were enabled/active/waiting and their trigger advanced. Ubuntu1 still violated its reserve; zero exit did not establish recovery. Ubuntu0's two metadata probes returned no stdout; the bounded diagnostic was exhausted. No general outage or new permission denial was inferred from missing output.

At08:45Z, the separate original Fabric attempt targeting ubuntu0 was refused by its existing temperature gate despite active count 2 below max 12. The response did not contain the current temperature or its threshold; both remain null in the retained evidence. This refusal does not repair the earlier metadata gap and does not qualify the host for another mode.

## Requested fault cases mapped to executed evidence

Counts are kept in the [main evidence record](README.md). The names below identify actual fixture paths within those executed suites; they do not imply installed proof.

| Requested case | Executed source/fixture evidence | Limit |
| --- | --- | --- |
| Missing/stale telemetry | `tests/test_fleet_health.py::test_old_snapshot_remains_stale_even_when_reachable_was_true`, `test_missing_host_and_offline_do_not_become_zero` | Source/fixture projection; no cross-UID installation |
| History gaps/downsampling | Same module: `test_gaps_future_rows_and_duplicates_cannot_manufacture_sustained_heat`, `test_ram_history_is_missing_when_the_source_never_recorded_it`, `test_downsampling_preserves_peaks_and_raw_gaps_not_fake_continuity` | Does not invent complete 30-day retention |
| Fixed routes and revocation | `tests/test_workspace_fleet.py::test_fleet_frame_accepts_only_fixed_window_without_host_or_path`, `test_permission_denial_prevents_fleet_source_read`, `test_revocation_during_fleet_read_discards_the_result`; read-app revocation/malformed-owner cases | The separately refused handoff test was not replayed |
| Concurrent admission | Hosted d30 native gate: `test_application_turn_selection_admission.SelectedIngressTests.test_concurrent_first_requests_reconcile_to_one_turn_and_one_post`, `test_last_slot_selection_refusal_recovers_concurrent_original_pending`; HTTP admission `test_concurrent_same_request_grants_exactly_one_dispatch` | Existing application-owner fixtures, not a new physical placement admission |
| Disk pressure and floors | `reproduce_linux_pressure_false_green.py`: ten controls, including unknown floor and held target; separate `test_desired_degraded_true_and_nonzero_exit_for_critical_below_floor_without_qualifying_cleanup` intentionally fails on the current installed source | Negative evidence retained on #2007; executable not repaired or installed |
| Interrupted/unknown cleanup | #1900 volume-monitor suite: `test_stale_pack_adverse_receipt_is_effect_unknown_not_not_applied`, `test_missing_and_invalid_stale_pack_receipts_stay_degraded`, `test_two_natural_passes_sharing_one_state_never_dispatch_a_helper`, `test_injected_earlier_unknown_row_is_preserved_and_never_reconciled` | No unenrolled helper or actual deletion executed |
| Service death and identity drift | #1887 health suite: `test_missing_pid_triggers_cooldown_recorded_kickstart`, `test_missing_pid_kick_suppressed_when_identity_drifts` | Synthetic exact-job/launchd facts; no real service killed |
| Interrupted recovery and concurrency | #1887 recovery suite: `test_reservation_is_on_disk_before_the_action_is_invoked`, `test_interruption_before_the_effect_keeps_the_reservation`, `test_interruption_after_the_effect_keeps_the_reservation`, `test_post_rename_directory_failure_never_leaves_a_free_seat_on_disk`, `test_concurrent_passes_never_invoke_the_action_twice` | Disposable filesystem/process fixtures |
| Bounded recovery loops | Same suite: `test_a_repeated_advancing_stale_observation_never_renews_the_attempt`, `test_a_held_seat_is_never_retried_after_the_cooldown`, `test_a_direct_release_mutation_with_stale_evidence_is_refused` | One unconfirmed acknowledgement per episode; no elapsed installed recovery proof |
| Actual pressure admission | Original 08:45Z Ubuntu0 Fabric receipt: `allowed=false`, `host_temperature_at_or_above_limit` | No temperature value, no blanket fleet admission/reliability claim |

## Original carriers and exact remaining boundaries

- **#1425 / #1363:** cross-UID binding edit and collector activation refusals remain. The denied function's original bytes are preserved. A same-user canary and synthetic browser do not supply installed authenticated-service proof. The paired translation correction is one exact fixture identity, with 23 passing paired tests and a one-byte drift negative; production realm source is unchanged.
- **#1887 at cc62ef75:** parent source gate 4/nested 333 passed and required source-proximate CI succeeded. Draft remains. Pathname-spawn HOLD_SECURITY, Cellar rename window/ambient interpreter, historical selected/pinned-native mismatch, host-route refusal and absence-before-initial-lstat limitation remain. Studio Direct's carrier is forbidden.
- **#1900 at 79f05c0:** parent 61 storage/12 archive passed. The source-unenrolled helper is held before dispatch. No complete discovery, original object/current lease binding, active-worktree exclusion or measured cleanup is asserted for an apply candidate.
- **#1877 at 00411f15:** denied source-write action and parent branch remain unchanged. The child's strict guard does not close that parent publication lane.
- **#2007:** PR projects 0e20d9b2 while its branch was observed at e339c3b7. Original publisher/raw-log/provider/account holds remain; no retry or replacement carrier.
- **#1632 / #2008 / #2156:** preserve original storage and runner ownership, Ubuntu4 RAM-integrity quarantine, Ubuntu3 uncertain effects, Ubuntu0 historical SNI refusal, active/dirty/unique worktrees and current leases. Merged #2008/#2156 and #2154's incorporated preview are DO_NOT_REDO. Earlier 110.82 GiB and 117.05 GiB recoveries belong to the original #1632 receipts, not this session.

The remaining operating acceptance is an original-owner-qualified installed path and a specifically authorized real cleanup/recovery cycle with resource floors, before/after measurements, original-work survival and bounded elapsed recovery. There is no source-derived uptime percentage or 24x7 claim. Old author/chat ownership and old blanket review wording are not new approvals; genuine host/security/source gates remain.
