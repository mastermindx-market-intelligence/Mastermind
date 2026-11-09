# Fleet host readiness — typed read-only summary (Director C, C5) — 2026-11-09

**Every live readiness fact below is typed; no host fact is invented as
healthy.** This is a summary record, not a placement decision: nothing here
allocates a slot, admits a host, or ranks a host for launch. Sources were read
only; no service was started, probed, or restarted.

Three joined sources:

1. **Host join contract** — `control_plane/t3_environment_projection.py`
   (read at this branch): joins one `mastermind.host_readiness_snapshot/v1`
   host snapshot with one `mastermind.t3_environment_observation/v1` fact set.
   Typed capability states `ready|degraded|unknown`; missing/`None`/unobserved
   facts are `unknown`, and `unknown` is never `ready` (WO-04 thermal rule,
   module docstring l.9-12). `launch_eligible` requires host reachable AND both
   sides fresh within `DEFAULT_FRESHNESS_WINDOW_S = 45.0` AND every capability
   `ready` (`project`, l.675-680). PROVEN: `tests/test_t3_environment_projection.py`
   + `tests/test_session_bridge_t3.py` → **45 passed, 0 failed** at this SHA
   (`env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest`).
2. **WO-04 host census** — `~/.hermes/profiles/engineering/mmos/WO-04_HOST_CENSUS.md`
   (read-only program doc), collected **2026-11-08**, one-shot read-only probes.
3. **Heartbeat contract** — `control_plane/executive_host_executor.py` (WO-15):
   executor pulls claims only when a local slot is free, heartbeats the same
   `HostReadinessSnapshot.v1` on every pull; **stale host gets zero new
   claims** (`DEFAULT_HEARTBEAT_S = 15`, `DEFAULT_NO_NEW_CLAIMS_AFTER_S = 45`,
   module l.58-59, l.15-16); local pressure recheck before start refuses via
   the WO-14 pre-start release; lease expiry is never proof of stop. PROVEN:
   `tests/test_executive_worker_broker.py -k "executor or heartbeat"` →
   **7 passed, 0 failed** at this SHA. The MCP-side consumer of the same
   snapshot schema (`integrations/executive_mcp/route_preview.py`,
   `host_snapshot_paths` default empty) degrades, never upgrades, when
   snapshots are absent or malformed.

## Live state — typed

| Fact | Value | Evidence |
|---|---|---|
| Hosts with a **fresh** (≤45 s) readiness snapshot | **0** | no live `hosts/*.json` snapshot registry exists under the coordinator home (`~/.hermes/fleet/` has no `hosts/` dir); `project_registry(hosts_dir, …)` over that path returns `()` + `hosts_dir unavailable` note |
| Hosts with a live heartbeat ledger row | **0** | `HostHeartbeatIntake` writes a caller-supplied JSONL ledger only when wired; no ledger file exists under `~/.hermes`; no intake was started (and none may be from this lane) |
| Hosts `launch_eligible` now | **0** | follows from the two rows above by the contract (freshness + all-ready); not asserted by running a projection — there is nothing to project |
| Fleet roster size (census ground truth) | 7 | WO-04 roster 2026-11-08 |
| Reachable at census time (2026-11-08) | 6 of 7 | WO-04 roster; recorded as a **dated observation, not current reachability** |
| Thermal observed | **0 — unknown on all 7** | WO-04: no thermal sensor read on any host; never reported healthy without a sensor |
| Eligible slots fleet-wide | **0 (every host)** | WO-04 zero-until-enrolled rule (Rev 4 l.131); unchanged — no enrollment step has run |
| Proposed worker slots (formula output, NOT eligibility) | 25 across 6 workers + 12 on the coordinator (OQ-5 open) | WO-04 derivation `min(floor(cores/2), floor((ram−reserve)/6))` |

## Per-host typed rows (census observation 2026-11-08; live state UNKNOWN)

| host_id | role | census reachable | live readiness (2026-11-09) | thermal | eligible_slots | notes |
|---|---|---|---|---|---|---|
| m2-studio | coordinator | yes | UNKNOWN | unknown | 0 | `~/.hermes` on 86%-used Data volume; census load 58.6/24 cores would fail any pressure gate |
| m1-studio | worker | yes | UNKNOWN | unknown | 0 | no `~/.hermes` runtime dir; no hermes/opencode binaries |
| ubuntu0 | worker | yes | UNKNOWN | unknown | 0 | no `~/.hermes`; no runtimes |
| ubuntu1 (mastermind-pc) | worker | yes | UNKNOWN | unknown | 0 | only worker with opencode; `~/.hermes` present |
| ubuntu2 | worker | yes | UNKNOWN | unknown | 0 | no `~/.hermes`; opencode present |
| ubuntu3 | worker | yes | UNKNOWN | unknown | 0 | no `~/.hermes`; opencode present |
| ubuntu4 | worker | **no** | UNKNOWN (unobserved) | unknown | 0 | mid-setup: TCP/22 accepts but SSH handshake never completes (LAN 192.168.8.220, exit 255 ~10 s); tailnet alias unresolvable |

**Fresh vs unknown, stated once:** "fresh" in this contract means an observed
snapshot within the 45 s window feeding a live heartbeat stream. **Zero hosts
are fresh. All seven are live-UNKNOWN.** The census reachability column is a
2026-11-08 observation that is now older than the freshness window by ~5
orders of magnitude; it must not be read as current reachability or health,
and the projection contract itself would refuse to make it `launch_eligible`.

## Enrollment blockers (unchanged from WO-04; nothing in this lane resolves them)

1. ubuntu4 unreachable (sshd not completing handshake mid-setup).
2. Tailscale TCP/22 times out from M2 for the whole fleet (ping OK) — the
   primary control path must work before any host can heartbeat; LAN fallback
   exists but is not a control plane.
3. No thermal sensor evidence on any host — thermal stays `unknown`.
4. No `~/.hermes` runtime dir on m1-studio, ubuntu0, ubuntu2, ubuntu3; the
   20 GiB runtime floor cannot be evaluated there yet.
5. No `hermes` binary on any fabric worker; `deepseek` binary nowhere in the
   fleet.
6. M2's own load (census: 58.6 on 24 cores) — reinforces coordinator 0-slot
   posture (OQ-5).

## Non-claims

- NOT CLAIMED: current reachability/load/disk of any host (nothing was
  probed today); any placement, admission, or slot allocation decision; that
  the census's "reachable" hosts are still reachable; that any host is
  healthy, degraded, or launch-eligible. Unknown stays unknown.
- Method note: module line numbers cite this branch's working tree; census
  rows cite the read-only program doc verbatim. No file under `~/.hermes` was
  modified.
