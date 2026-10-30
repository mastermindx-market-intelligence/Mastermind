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
    -p 'test_fabric_tunnel_*.py'            # focused hermetic suite
python3 -m unittest discover -s tests \
    -p 'test_subagent_fabric_tunnels_source.py'   # CI gate, 4 tests
python3 -m compileall -q integrations/subagent_fabric_tunnels
```

## Host procedure (requires separately authorized host gates — FTR-6/7)

### 1. Qualify (the single sanctioned qualification entrypoint)

`verify` is NOT qualification: it reads back a manifest that does not exist
on a fresh host. The real entrypoint is the `qualify` subcommand, which
derives all five installed identities from the ACTUAL plists, enforces
distinct argv AND distinct executable identity, validates a CLOSED
operator-facts schema, and writes the private 0600 manifest:

```bash
# 1a. First-install dry run from an EMPTY manifest — reads only, writes nothing,
#     proves the install path is feasible before anything is authorized:
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_install.py --home ~ \
    qualify --dry-run --facts-file ~/ftr-facts.json

# 1b. Actual qualification (explicit operator confirmation):
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_install.py --home ~ \
    qualify --confirm --facts-file ~/ftr-facts.json

# 1c. Readback after install (requires the manifest; never a substitute for 1b):
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_install.py --home ~ verify
```

The facts file is an operator-written JSON document (0600, never committed,
group/world-WRITABLE modes are refused); qualification validates it against a
closed schema and refuses unknown fields — nothing is invented, hardcoded, or
guessed:

```json
{
  "seats": {
    "com.mastermind.subagent-fabric-tunnel.c1": {
      "heartbeat_path": "/absolute/path/to/that-seats-heartbeat",
      "heartbeat_kind": "tunnel-client-control-plane-last-seen",
      "heartbeat_proof_note": "how the operator proved this file is the first-party last-seen signal"
    }
  },
  "host": {
    "native_store_path": "/absolute/native-code-releases/path",
    "host_pull_telemetry_dir": "/absolute/telemetry/root",
    "host_pull_telemetry_files": ["lane-a.json", "lane-b.json"],
    "pinned_generation": "<64 lowercase hex>",
    "stale_telemetry_seconds": 900,
    "repair": {"files": {"ext/remote_sub_exec.py": "<64 lowercase hex>"}}
  }
}
```

Every fact is optional; every ABSENT fact becomes an explicit
`*_unqualified` health alert instead of a guessed default. Facts that ARE
provided are validated hard: absolute paths, existing regular non-symlink
files (including each heartbeat at qualification time — a client that has
never written its heartbeat cannot be qualified yet), ≤32 telemetry files
with relative POSIX paths and a `.json` suffix, 64-hex pinned generation and
repair digests. `heartbeat_kind` requires `heartbeat_proof_note`: without an
operator first-party attestation, a heartbeat file's mtime is never treated
as the tunnel-client/control-plane last-seen signal (B6).

Refusals that must be resolved by a human before anything else:
`foreign identity 'chatgpt1'`, `argv_tuple_duplicated`,
`executable_identity_duplicated`, `rogue_family_labels_present`,
`*_drift_since_qualification`, `label_mismatch`, `*_plist_owner_unsafe`,
`facts_*`. Qualification fails closed: any refusal means nothing is written.

### 2. Install (the only plist mutation this integration performs)

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

The batch is TRANSACTIONAL (B5): every mutation is fully derived before the
first write, and a failure on any seat rolls every previously installed seat
back through its validated preimage CAS (status `batch_rolled_back`), leaving
unattempted seats reported `not_attempted`. Only a fully installed or fully
already-compliant batch exits 0; partial states are never silent and never
survive a failed run.

Mutation custody ( tightened): the batch preflight hash-check is re-asserted
IMMEDIATELY before each seat's mutation — the on-disk bytes AND mode must
still be the EXACT qualified predecessor pinned in the manifest. A concurrent
external writer that lands after preflight makes that seat refuse
(`install_pre_mutation_drift_refused`); the intervening bytes are preserved
untouched, no launchd action is taken, and the rest of the batch aborts.
This CAS on the qualified bytes is the single mutation-owner enforcement; no
second lifecycle or lock plane exists. The LEXICAL ancestor chain of every
plist is also re-bound symlink-free at install time
(`*_install_parent_unsafe`), so a `~/Library` swap between qualification and
install refuses instead of resolving through the symlink.

Readback after install:

```bash
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_install.py --home ~ verify
```

### 3. Health loop (one bounded pass per invocation)

```bash
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_health.py pass --home ~
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_health.py last-pass --home ~
```

Installed form: the watchdog is installed and verified through the explicit
operator CLI (not only an importable function):

```bash
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_health.py \
    --home ~ watchdog-install --confirm
python3 integrations/subagent_fabric_tunnels/fabric_tunnel_health.py \
    --home ~ watchdog-verify
```

`watchdog-install --confirm` copies the four modules privately and installs
the watchdog LaunchAgent — `StartInterval=60`, `RunAtLoad=true`,
`ThrottleInterval=10`, **no KeepAlive** (a periodic job must not be
resurrected into a tight loop), python3 resolved from the host at install
time. Each fire is ONE pass; there is no daemon and no retry plane. It
refuses without `--confirm`, without a fresh manifest, or on any unsafe
target; `watchdog-verify` is read-only, performs no launchd call, and fails
closed (exit 4) on any absence, mismatch, or tamper
(`watchdog_plist_unavailable`, `watchdog_plist_not_ours`,
`watchdog_module_mode_unsafe`).

Watchdog install safety (B3, tightened): every target about to CHANGE (the
four copied modules and the watchdog plist) is captured as an exact private
preimage backup BEFORE any edit, and that backup is recorded as THIS
attempt's rollback source; already byte-identical targets are left untouched
(idempotent re-runs write nothing, create no backup churn, and rollback never
resurrects a stale earlier generation into them); symlinked or unsafe
targets REFUSE instead of being overwritten; the LEXICAL ancestor chains of
both write roots are re-bound symlink-free at install time; every write is
verified by read-back digest; and ANY fault — post-write mismatch, write or
chmod exception, or launchd failure — rolls ALL targets changed by this
attempt back to their exact preimage (or restores ABSENCE) under CAS against
this attempt's post digests. External drift after our write is preserved,
never clobbered (`watchdog_rollback_cas_refused_external_drift`). launchd is
reloaded only when the plist itself was actually mutated by the attempt, so
a fault during an earlier module write never starts or stops any job.
Watchdog install remains an install-time mutation and keeps the strict
fresh-manifest requirement.

### Manifest age vs. durable recovery (B1)

The manifest carries a one-day (86400 s) operator attestation bound. It
bounds TRUST of the attestation, not the life of the recovery:

- All MUTATION paths (install, rollback, verify, watchdog install) still
  refuse a manifest past the bound: `manifest_stale_requalify_required`.
  Install-time authorization and the preimage CAS are unchanged.
- The read-only health pass continues past the boundary: each pass re-proves
  every seat's installed identity, program digest/argv, and qualified
  heartbeat path from LIVE host state (`revalidate_stale_identity`) and
  raises a persistent `manifest_stale_revalidated` alert so the operator
  requalifies. A seat whose live identity no longer matches the pinned
  manifest is ALERT ONLY (`seat_identity_tampered_alert_only`; stable reason
  codes `argv_changed` / `executable_path_changed` / `executable_digest_changed`
  / `heartbeat_path_not_regular`) until a human requalifies — tampering never
  earns a kickstart and never disables the other seats' recovery. Nothing in
  this integration touches login, security, reboot, or launchd domain
  configuration.

### Heartbeat first-party proof (B6)

A heartbeat FILE's mtime is only a recovery signal when the operator
qualified that seat with `heartbeat_kind` + `heartbeat_proof_note`. Without
that attestation, a stale heartbeat is
`stale_heartbeat_unproven_alert_only` (ALERT ONLY, no forced restart) and
states the exact required host proof: an operator-correlated
tunnel-client/control-plane last-seen attestation recorded at qualification.
Missing-PID recovery is unaffected — that state is proven by launchd itself.
The user-visible error this replaces ("Tunnel-client has not been seen for
300 seconds") is never inferred from an arbitrary file's age.

Classification (distinguished exactly as the plan requires):

| Signal | Outcome |
| --- | --- |
| No PID on a qualified job | `missing_pid` → plain `launchctl kickstart gui/<uid>/<label>` |
| No PID, 3 persisted consecutive kicks without a witnessed fresh heartbeat | `kickstart_escalated_alert`, NO fourth kick even after cooldown, until a healthy pass witnesses a fresh heartbeat |
| PID present, heartbeat older than 300 s, first-party attested | `stale_heartbeat` → `launchctl kickstart -k` |
| PID present, heartbeat older than 300 s, NOT attested | `stale_heartbeat_unproven_alert_only`, NO action, exact required proof in the alert |
| PID present, heartbeat fresh | `healthy`, no action |
| Heartbeat file missing/unreadable | `heartbeat_missing` alert, NO action |
| Heartbeat path never qualified | `heartbeat_path_unqualified`, NO action |
| Heartbeat recorded but never attested first-party | `heartbeat_first_party_unproven` alert (per pass, until qualified) |
| `launchctl print` nonzero WITHOUT the specific `Could not find service` diagnostic | `launchd_state_uncertain_alert_only`, NO action, zero effect calls (never mistaken for a missing PID) |
| Kick ledger corrupt / unreadable / symlinked / unsafe-permissioned / malformed | `kick_ledger_refused_alert_only` (+ `kick_ledger_refused_recovery_alert_only`): NO recovery for the whole pass; on-disk history preserved, never auto-reset |
| Live seat identity ≠ pinned manifest (only past the day boundary) | `seat_identity_tampered_alert_only`, NO action for that seat; other seats recover |
| Manifest past 86400 s on a health pass | `manifest_stale_revalidated` alert; live revalidation, recovery continues |
| `CURRENT.json` selection ≠ qualified pinned generation | `selected_generation_drift` alert; repin REFUSED, CURRENT.json never rewritten |
| Selected generation missing | `selected_generation_missing` alert |
| Installed generation repair digest ≠ qualified stdin/ARG_MAX repair digest | `stdin_argmax_repair_missing` alert, never an auto selection/publish |
| Qualified telemetry set: oldest required file older than the threshold | `host_pull_telemetry_stale` alert |
| Any qualified telemetry file missing/symlinked/invalid, or file set unqualified | `host_pull_telemetry_unqualified` alert (never a partial freshness proof) |
| Kickstart already performed within cooldown (1800 s) | `kickstart_suppressed_cooldown` |

Host-pull telemetry is read from a bounded CLOSED set of operator-qualified
explicit files (`host_pull_telemetry_files` under `host_pull_telemetry_dir`,
≤32 entries, `.json` suffix, relative POSIX paths, regular non-symlink
files). The OLDEST required file drives freshness: an unrelated freshly
written file under the same root can never mask stale telemetry, and there
is no recursive scan to make the minute watchdog unbounded (B2).

The kick ledger is private (0600), persists across passes, and is what makes
recovery bounded. It also fails CLOSED: a GENUINELY ABSENT ledger initializes
as first use, but an existing ledger that is corrupt, unreadable, symlinked,
non-regular, group/world-writable, or shape-invalid REFUSES the whole pass's
recovery (`kick_ledger_refused_recovery_alert_only`) and is never rewritten —
cooldown/escalation history can never be silently erased to re-enable
unbounded restarts. Host-pull generation alerts never block a qualified seat's
own crash recovery: a dead tunnel client is recoverable even while the host
carrier needs human attention.

### Login/session semantics (documented, never changed)

These jobs are USER LaunchAgents: launchd loads them only when the user's
GUI/console session is established (login, or a re-login after reboot). They
do NOT run at power-on before login, and neither do the watchdog's passes.
After reboot WITHOUT a logged-in console session, no tunnel client, no
watchdog pass, and therefore no automatic recovery exists until someone logs
in; any "recovers after reboot" claim additionally requires a proven
logged-in session owner. This integration documents that fact and does not
and may not change login items, launchd domain configuration, security, or
session behavior to pre-login startup.

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
- Not a pre-login service: recovery exists only inside a live logged-in GUI
  session (see "Login/session semantics").
- Not a heartbeat truth-source by itself: an unattested file mtime is never
  claimed as first-party tunnel-client/control-plane last-seen.
- Not merged/approved: one Draft PR from the branch may exist, but review is
  a separate independent non-authoring Fabric pass (FTR-5) and merge/approve
  stays out of this mission.
