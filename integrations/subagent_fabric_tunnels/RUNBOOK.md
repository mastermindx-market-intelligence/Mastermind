# Subagent Fabric tunnel-client recovery — source runbook (FTR-2/3/4)

Status: **SOURCE ONLY — NOT INSTALLED, NOT PRODUCTION-PROVEN.**
Plan: `RECOVERY_PLAN.md` (same directory), commit
`6dd11e7015235eff3c0242ef90dea554f4f4c58d` on
`sol/fabric-tunnels-autoheal-20261030-01`; source-law pin
`bb85b429f2ffffd38408080ce4df7d6378c34100` (Skillpack 1.0.1).

Scope is exactly five EXISTING user LaunchAgents on m2studio —
`com.mastermind.subagent-fabric-tunnel.{c1,c2-business,c2-personal,c3,c4}` —
plus one NEW repo-owned watchdog label,
`com.mastermind.subagent-fabric-tunnel.health`. Nothing else in the family is
adoptable; a family plist outside these six labels makes install and health
recovery refuse until a human resolves it. The Desktop Commander carrier
(`com.mastermind.desktop-commander.remote`) is a permanently forbidden action
target in every code path and is never parsed or rewritten. No sudo, no
security/SIP change, no CURRENT.json selection, no host-pull repin, no
additional queue or process watcher exists in this integration.

## Files

| File | Role |
| --- | --- |
| `fabric_tunnel_common.py` | Scope/allowlist fences, launchd argv builders (forbidden-label asserted), redaction, atomic writes, runner seam |
| `fabric_tunnel_identity.py` | FTR-2 identity verification, policy delta, private qualification manifest |
| `fabric_tunnel_install.py` | FTR-2 install/verify/rollback: backup → CAS policy-trio mutation → bootout/bootstrap reload |
| `fabric_tunnel_health.py` | FTR-3 one bounded pass: classify, cooldown-bounded kickstart, alerts; watchdog agent install |
| `test_fabric_tunnel_identity.py` | Hermetic suite: allowlist/argv/symlink/ownership/manifest rejects |
| `test_fabric_tunnel_install.py` | Hermetic suite: idempotence, backup privacy, rollback, drift/rogue refusals, exit-0 restart policy |
| `test_fabric_tunnel_health.py` | Hermetic suite: PID/heartbeat/generation/telemetry/repair discrimination, cooldown, escalation |
| `tests/test_subagent_fabric_tunnels_source.py` | Hosted-CI gate that runs the colocated suites + compile/fence checks |

## Source run commands (already executed; see "Test evidence")

```bash
# from a repo checkout at the branch commit
python3 -m unittest discover -s integrations/subagent_fabric_tunnels \
    -p 'test_fabric_tunnel_*.py'            # 83 tests
python3 -m unittest discover -s tests \
    -p 'test_subagent_fabric_tunnels_source.py'   # CI gate, 4 tests
python3 -m compileall -q integrations/subagent_fabric_tunnels
```

## Host procedure (requires separately authorized host gates — FTR-6/7)

### 1. Qualify (read-only; explicit operator step)

```bash
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_install.py --home ~ verify --now $(date +%s)
```

Qualification is built in-source (`fabric_tunnel_identity.build_manifest`) and
must be run by an operator AFTER first-party host readback: it records the
five installed plist identities (byte digests, argv tuples, resolved
executable digests) plus OPTIONAL host facts — each seat's first-party
tunnel-client heartbeat path, the `native-code-releases` store path, the
host-pull pinned generation, and the approved stdin/ARG_MAX repair file
digests from the merged upstream source. Nothing here invents any of those
values; every absent fact becomes an explicit `*_unqualified` alert and
health recovery stays blocked for what was never qualified. The manifest is
written PRIVATE (0600) under
`~/Library/Application Support/mastermind-subagent-fabric-tunnels/state/`
and is never committed, printed whole, or logged.

Refusals that must be resolved by a human before anything else:
`foreign identity 'chatgpt1'`, `argv_tuple_duplicated`, `rogue_family_labels_present`,
`*_drift_since_qualification`, `label_mismatch`, `*_plist_owner_unsafe`.

### 2. Install (the only mutation this integration performs)

```bash
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_install.py \
    --home ~ install --confirm
```

Per seat: preimage backup (private, 0600, digest sidecar) → apply exactly
`RunAtLoad=true`, unconditional `KeepAlive=true` (boolean; any dict form is
replaced because the tunnel client may exit 0 after SIGTERM),
`ThrottleInterval>=10` (a larger incumbent is preserved) → atomic rename with
parse-back → `launchctl bootout gui/<uid>/<label>` when loaded, then
`launchctl bootstrap gui/<uid> <plist>`. On bootstrap failure the preimage is
restored and the original plist re-bootstrapped (`install_failed_rolled_back`);
if even that fails the seat hard-alerts (`install_failed_rollback_also_failed`).
Idempotent: an already-compliant seat is reported `already_compliant` with no
write and no reload. Every action target is asserted against the immutable
allowlist before any argv is built.

Readback after install:

```bash
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_install.py --home ~ verify
```

### 3. Health loop (one bounded pass per invocation)

```bash
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_health.py pass --home ~
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_health.py last-pass --home ~
```

Installed form: `install_watchdog_agent` copies the four modules privately and
installs the watchdog LaunchAgent — `StartInterval=60`, `RunAtLoad=true`,
`ThrottleInterval=10`, **no KeepAlive** (a periodic job must not be
resurrected into a tight loop), python3 resolved from the host at install
time. Each fire is ONE pass; there is no daemon and no retry plane.

Classification (distinguished exactly as the plan requires):

| Signal | Outcome |
| --- | --- |
| No PID on a qualified job | `missing_pid` → plain `launchctl kickstart gui/<uid>/<label>` |
| PID present, heartbeat older than 300 s | `stale_heartbeat` → `launchctl kickstart -k` |
| PID present, heartbeat fresh | `healthy`, no action |
| Heartbeat file missing/unreadable | `heartbeat_missing` alert, NO action |
| Heartbeat path never qualified | `heartbeat_path_unqualified`, NO action |
| `CURRENT.json` selection ≠ qualified pinned generation | `selected_generation_drift` alert; repin REFUSED, CURRENT.json never rewritten |
| Selected generation missing | `selected_generation_missing` alert |
| Installed generation repair digest ≠ qualified stdin/ARG_MAX repair digest | `stdin_argmax_repair_missing` alert, never an auto selection/publish |
| Host-pull telemetry older than the qualified threshold | `host_pull_telemetry_stale` alert |
| Kickstart already performed within cooldown (1800 s) | `kickstart_suppressed_cooldown` |
| 3 consecutive kickstarts without a witnessed fresh heartbeat | `kickstart_escalated_alert`, alert-only until one fresh heartbeat is seen |

The kick ledger is private (0600), persists across passes, and is what makes
recovery bounded. Host-pull generation alerts never block a qualified seat's
own crash recovery: a dead tunnel client is recoverable even while the host
carrier needs human attention.

### Deliberate stop semantics

With unconditional `KeepAlive=true`, any exit — SIGTERM, crash, or clean
exit 0 — is followed by a launchd restart. A `kill` of the client PID is
therefore NOT a stop; it is a restart request. The only sanctioned deliberate
stop is the launchd owner action:

```bash
launchctl bootout gui/$(id -u)/com.mastermind.subagent-fabric-tunnel.<seat>
# restore:
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mastermind.subagent-fabric-tunnel.<seat>.plist
```

### Rollback

```bash
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_install.py \
    --home ~ rollback --confirm --label com.mastermind.subagent-fabric-tunnel.<seat>
```

Restores the newest preimage (CAS: refuses if current bytes drifted past the
recorded post digest), re-bootstraps the restored plist, and reports the
result as an alert code, never silently. Backups live under
`~/Library/Application Support/mastermind-subagent-fabric-tunnels/backups/`
(0700 dir, 0600 files) and must never be committed or pasted anywhere.

## Secret-safety contract

- Job `EnvironmentVariables` are stored ONLY inside the private manifest and
  private backups; every stdout/evidence surface passes through `redact_value`.
- Identity tables print label, digest prefixes, mode, argv LENGTH — never an
  argv body, never an env value, never a token.
- Pass reports contain no argv bodies; the report file is 0600.
- No credential, tunnel identity, or path is hardcoded in source; nothing in
  this repo's static text qualifies production (stale snapshots are not
  authority — the plan's own fence).

## What this is NOT

- Not installed anywhere, and no proof of host health.
- Not a CURRENT.json selector, publisher, or generation chooser.
- Not a Desktop Commander carrier observer or modifier.
- Not merged/approved: one Draft PR from the branch may exist, but review is
  a separate independent non-authoring Fabric pass (FTR-5) and merge/approve
  stays out of this mission.
