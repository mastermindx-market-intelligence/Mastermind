# Mastermind OS Fleet Health

## Commission and authority

Chairman request: integrate Ubuntu PCs and Macs into Mastermind OS with hardware readings, working subagent visibility, CPU/RAM/temperature history, and evidence-based sustained-use recommendations. Source operation: `fleet-health-os-20261013-sol-001`; protected procedural/source pin: `d837e04bf60a9fb60b7c530d287115a298fc1af0` (compatible Skillpack 1.0.1). The assigned principal owns ordinary design/build/test work. Existing release, source custody, permissions and effect fences remain unchanged.

## Outcome

The existing Fleet & Capacity route shows registered computers, last observation, live/stale/offline/unknown state, available CPU/thermal/memory/storage metrics, observed Fabric occupancy, historical charts and explainable findings. Missing readings never become zero or healthy. The current source does not enumerate every unmanaged or nested subagent; the UI must explicitly distinguish observed Fabric lanes from a complete subagent count.

## Architecture

Reuse `hosts.json`, `state/hosts/<registered-id>.json`, and `state/host_pull.log` owned by the already-installed Fabric observer. No new collector daemon, registry, scheduler, queue, credentials, lifecycle, placement decision, telemetry database or monitoring service. A bounded read-only projection belongs behind the existing workspace service and its enrolled-viewer permission checks. The public HTTP and native bridge expose one fixed Fleet read, not a path, command or arbitrary URL. The React consumer uses the existing Noir design language.

Add an optional trusted-host Fleet reader to WorkspaceReadService and its existing factory. Its absence produces typed UNAVAILABLE; no guessed filesystem root is used. Installation must bind the actual existing Fabric source through the service's installation owner. The reader itself starts no collection or refresh.

## Data contract: mastermind.fleet_health.v1

Top-level exact keys: schema, availability (AVAILABLE/PARTIAL/UNAVAILABLE), generated_at (epoch seconds), window (1h/24h/7d/30d), history_truncated (boolean), admission_authoritative (false), source (fabric_host_observer), hosts (array), reason_codes (array). At most 32 hosts. A response is capped at 1,500,000 UTF-8 bytes. AVAILABLE means the projection is readable with current host snapshots, not complete sensors, all subagents, hardware safety or placement eligibility.

Each host has exact keys: id, label, platform (macos/linux/unknown), state (CURRENT/STALE/OFFLINE/UNKNOWN), observed_at (epoch seconds or null), metrics (object below), history (array below), findings (array below), coverage (array of closed reason strings).

Metrics keys, each finite nonnegative number or null: cpu_busy_pct (0..100), load1, load5, logical_cpus (positive integer), memory_available_bytes, memory_total_bytes, memory_used_pct (0..100), swap_used_bytes, cpu_temp_c (0..150), nvme_temp_c (0..150), fan_rpm, disk_free_bytes, fabric_active_lanes (nonnegative integer), process_lane_candidates (nonnegative integer), thermal_advisory_c (0..150). The advisory temperature is the existing Fabric operator limit, NOT a manufacturer damage limit. Nested temperature/CPU readings must match the outer observation timestamp; malformed, future or mismatched inputs stay unavailable. Booleans are not numeric measurements.

A history point has exact keys: timestamp, cpu_temp_c, cpu_busy_pct, load1, memory_used_pct, fabric_active_lanes, gaps. `gaps` is a unique list of those five metric keys whose interval from the previous retained point contains a missing reading or a raw observation gap over 180 seconds. This preserves gap truth after downsampling rather than treating downsample spacing as a raw observation gap. Numeric fields use the same constraints. Retain per-window extrema and explicit gaps in chart data; never connect over missing readings or long gaps. A maximum of 360 points per host per response bounds payload. Downsampling preserves temperature/CPU peaks and indicates truncation. History comes from the existing collector log, including additive richer fields when that owner publishes them. The oldest returned observation, not the selected window label, establishes actual coverage. RAM history is unavailable until the existing collector records it.

A finding has exact keys: code, severity (info/warning/critical), category (coverage/performance/hardware), summary, detail, duration_seconds (finite nonnegative number or null). Messages are deterministic, evidence-backed advisory templates, not model-generated hardware diagnoses. No remaining-life prediction or probability of hardware damage.

## Health semantics

High utilization and long uptime alone do not prove damage. Separate performance pressure, limited thermal headroom, observed hardware/OS warnings and missing coverage. Operator dispatch limits must not be presented as manufacturer specifications. Sustained conditions require real ordered observations with bounded gaps (180 seconds maximum); missing/future/duplicate/out-of-order evidence cannot accumulate duration. Evaluate sustained exposure on validated raw observations before chart downsampling. Current stale/offline hosts cannot receive a current healthy verdict. Historic findings are not silently presented as current alarms.

Initially detect sustained CPU saturation (>=90% for >=30 minutes) as a performance finding, sustained temperature at/above the configured Fabric advisory cutoff (>=10 minutes) as thermal-headroom advice, and observed NVMe critical margin exhaustion as a hardware warning. Explain source and thresholds, including that monitoring does not cool a computer. Recommendations may suggest reducing future concurrency through existing placement, inspecting cooling/airflow, or investigating sustained swap/pressure; they never stop workers, change firmware/voltage/governors, alter fan control, or reboot equipment.

## Security and boundedness

Read only registry-selected safe host IDs. Do not glob unrelated JSON manifests as computers. Reject symlinks/nonregular files, oversized inputs, unsafe IDs, duplicate registry IDs and mismatched host identity. Use bounded same-descriptor reads; malformed source content never escapes in an error. Do not publish paths, accounts, SSH aliases, credentials, process commands or provider configuration. No client-selected file/root/host-command inputs. Fixed window enum only. Authentication, permission-revocation recheck, no-store headers, exact path/query/body fences and abort/generation checks remain active.

## Known integration boundaries at entry

Fleet & Capacity is currently a placeholder. PR #1404 records an independently live existing Fabric observer at 60-second cadence and numeric trends; its source-record draft and incumbent files must not be overwritten. PR #1363's separate Ubuntu collector activation and test upload retain their explicit holds; this mission does not retry them through another carrier. #1346 and merged #1015 retain canonical Capacity observation/placement semantics. Some Mac snapshots are stale and lack temperature/CPU-percent/total-RAM readings. Do not claim those metrics live from fixture tests.

## Acceptance

Prove pure projection/missingness/duration/gap/size behavior; test the authenticated fixed route and revoked permission; test frontend decoding, sign-out cancellation, unknown/zero distinction, history and findings. Run TypeScript checks, frontend tests/build and focused Python regression suites. Record exact candidate, independent review and CI. Production completion additionally requires accepted protected-source installation, live observer-to-service-to-web/native proof on actual Ubuntu and Mac devices, and explicit sensor/history/subagent coverage. A PR or chart fixture does not complete that end-to-end outcome.
