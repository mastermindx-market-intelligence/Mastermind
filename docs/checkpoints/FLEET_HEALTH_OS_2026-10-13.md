# Fleet Health / Mastermind OS — implementation frontier (2026-10-13)

## Mission and ownership

Chairman commission: show Ubuntu/Linux and macOS physical machines in Mastermind OS, observed running subagents, CPU/RAM/thermal history, and evidence-backed long-use warnings/recommendations. Canonical protected Mastermind pin `d837e04bf60a9fb60b7c530d287115a298fc1af0`, compatible `mastermind.sol_skillpack.v1` v1.0.1. Assigned source operation `fleet-health-os-20261013-sol-001`, managed worktree branch `sol/web-fleet-health-os-20261013-sol-001`. Main code resides in this repository. Existing Fabric observer, Executive Runtime, Agent OS, Capacity, web authorization and GitHub release owners retain their original authorities.

## Source result

The existing Fleet & Capacity placeholder has been replaced in source by a read-only React diagnostic dashboard. The new `mastermind.fleet_health.v1` projection uses the existing installed Fabric registry, per-host snapshots and `state/host_pull.log`; no second collector, polling daemon, telemetry database, agent registry, placement gate, new credential or Worker control. The fixed authenticated `GET /workspace/fleet/current?window=...` is permission-fenced and decoded through the existing web and Tauri native clients. A trusted installer can provide the optional `workspace_fleet_observer_root` inside its sealed Workspace composition; absent this binding, the endpoint truthfully reports unavailable.

Safety semantics: unsupported measurements return `null`, not zero; occupancy is **observed Fabric active lanes**, not a complete count of nested/unmanaged agents. CPU load1 is distinct from CPU busy percent. Operator temperature limits are not manufacturer failure/damage thresholds; sustained conditions require contiguous actual observations and are advisory. Missing/stale records are explicit; history ranges describe a selected query interval, never guaranteed retained coverage. Temperature peaks, gaps and sample limits survive bounded downsampling.

## Reproduced source evidence

- Existing M2 Fabric observer source was **read**, not modified. Live source-to-WorkspaceReadService in-process test returned `schema=mastermind.fleet_health.v1`, availability `PARTIAL`, 12 registered machine records including six with current observations at that moment. This is **not** installed public-service end-to-end authentication proof.
- Focused Python suites `tests/test_fleet_health.py`, `tests/test_workspace_fleet.py`, `tests/test_workspace_read_app.py`, `tests/test_executive_workspace_mount.py`, `tests/test_executive_fabric_phase1c.py`, `tests/test_workspace_read_socket.py`: all tests passed using `.venv/bin/python`.
- Full Mastermind OS Vitest suite: **1,396 passed, one skipped, zero failures**; the historical App Fleet placeholder expectation was updated to the new no-source-safe view.
- Mastermind OS TypeScript typecheck and Vite web build passed. Build reports existing chunk-size/dynamic-import warnings, not failures.
- Tauri Rust locked test run: **29 primary tests plus 14 update-utility tests passed**. Rust `target/` is ignored and must never be published.
- Source has not yet been reviewed, merged, deployed or activated in the production workspace service. No live system configuration, worker admission, Mac thermal sensor, separate #1363 held activation or #1404 incumbent collector was modified.

## Known limitations / product honesty

- Physical Mac snapshots lack native CPU-busy and temperature coverage from this observer; installed Mac probe currently provides load average and estimated free+inactive memory. Do not invent precise RAM-used percentages or imply high load1 alone means hot hardware.
- Ubuntu CPU temperature, utilization and occupied Fabric lanes are observable where the existing sensor bridge reports them. Future Mac sensors require a separate qualified existing-observer upgrade and real sensor entitlements.
- Historical depth is limited by the **existing** observer log's actual rotation and 8 MiB bounded reader; 7d/30d selections are not guaranteed to have retained data. Improve retention via the existing observer/log policy, not a parallel history service.
- Current Fabric lane occupancy is not an authoritative global census of all subprocesses, Codex native children, unmanaged or nested provider sessions. A later semantic join to the existing Executive/Agent OS owners is needed for that guarantee; do not sum `process_active_lanes` and Fabric occupancy.
- Both the config binding and the frontend/web/native source are proposal code until qualified installation. Existing public Workspace/A1 client registration and scope permissions must be separately verified; do not assume authenticated production access from fixture tests.

## Conflicts/holds

PR #1363 separately owns held Ubuntu 0/3 collector activation; original transport refusal has **not** been bypassed. PR #1404 owns real installed M2 thermal mitigation and incumbent collector cadence, with sustained thermal relief unproven. PR #1346 owns separate canonical Capacity v2 observation composition. Do not merge or reinstall one to supersede the other. The new source is diagnostics-only, never host placement or physical-worker reservation authority.

## Next execution frontier

1. Publish this exact managed branch through Studio Direct's typed CAS commit/push. Obtain independent review/required CI for the scoped app, service, contract, telemetry reader, closed route, native bridge and tests. Preserve one head/effect carrier.
2. On accepted protected release, configure `workspace_fleet_observer_root` in the existing sealed service configuration to the actual host-readable incumbent Fabric observer root; verify read permissions from the installed service UID. No implicit HOME fallback and no request-supplied path. Qualify web and native authenticated reads, live Ubuntu/Mac observations, sign-out behavior and failing/no-sensor cases against actual installed service. Release only through existing protected workflow.
3. Advance existing Mac sensor and 30-day retention qualifications through their actual incumbent owners; then join canonical agent/run identities without inventing a new agent lifecycle store. Finish only when the Chairman can use the live app and observed fields are grounded on real hosts.

**State at this checkpoint:** `BUILT_NOT_PROVEN` for the end-to-end product source, `PARTIAL` real host telemetry coverage, `NOT_PROVEN` for installed public app and full-machine historical/agent-census coverage. Source tests and local live-source composition cannot be promoted to production completion.
