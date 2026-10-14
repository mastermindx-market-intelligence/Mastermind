# Fleet Health: operator-to-Executive sanitized read-only handoff

**Status:** source-only candidate in Mastermind OS Fleet Health PR #1425. Not installed, configured, scheduled, enabled, or adopted by production. The existing M2 Fabric collector remains the sole host telemetry producer. This guide is a release/acceptance procedure for its authorized existing owner, **not an instruction to weaken private user filesystem permissions or create a second watcher/daemon**.

## Why an explicit handoff is necessary

The installed Fabric collector currently reads remote Mac/Linux machines under the `chriswong` macOS user. The independently installed Executive control service runs under `_mastermind_exec`. On M2 the collector's `~/.claude` ancestor was observed at mode `0700` and its registry `hosts.json` at `0600`. A new Executive `workspace_fleet_observer_root` pointing directly into that private tree would be unreadable by the production service; source-level same-user success is not a cross-UID installation test.

Do **not** change the permissions on the user's `~/.claude`, `hosts.json`, secrets, SSH configuration, provider homes or Fabric runtime. Do **not** change Executive's existing UID, broaden its service powers, or proxy through a new unsigned API/credential. The exposed Fleet observation remains `admission_authoritative=false` and cannot create, count globally, reserve, cancel, move or place Workers.

## Existing producer → sanitized one-file projection

`control_plane.fleet_health` already composes read-only, bounded diagnostics over the incumbent `hosts.json`, `state/hosts/<registered-id>.json`, and `state/host_pull.log` with genuine per-host freshness and missingness. New `control_plane.fleet_health_handoff` optionally lets the **same observer owner** materialize a single latest *derived* presentation into an installer-prepared destination directory. It contains four closed Fleet views (1h, 24h, 7d, 30d), sample time, source marker, no private roots, SSH aliases, credentials, worker packet bodies, raw logs or provider account data. The legacy source remains authoritative; this projection is not a second historical database, event log or worker lifecycle.

The file is atomically replaced (write separate exclusively created temporary file, fsync, replace, fsync directory). Failure leaves the previous report to age out; no empty/healthy output is manufactured. Reader requires the exact schema, window keys, closed DTO validation for *all four* windows, stable regular-file metadata, a protected directory, and a sample no more than 180 seconds old. An unsafe, stale, changed or unreadable file yields typed `UNAVAILABLE`. The file is advisory only.

### Operator/installation gates

An authorized existing installer must select and own an **exclusive directory reserved for this one Fleet handoff**. It must be a real non-symlink directory, mode `0700`, owned by the publishing observer user. A narrowly scoped macOS ACL may grant **only** the installed `_mastermind_exec` identity the minimum directory search/read permission needed to reach the one sanitized fixed report. The report has mode `0644` but is shielded by the restrictive parent directory; this directory must not be made world-searchable. Actual ACL behavior and the publisher's atomic-replace inheritance must be verified against the real UID. Avoid assuming a Unix group both principals share; the observed service account does not belong to the user's `_mastermind_ops` group.

No directory, ACL, launch agent, collector script or service configuration was changed by source development. Do not put the handoff in the protected `/var/run/mastermind-executive` tree merely because it exists; the Fabric owner does not own that service runtime tree. A destination is not enrolled by making up a name in a chat or replacing a private installer.

The existing Fabric observer may invoke this bounded **one-shot** producer **as part of its established post-collection pass**, after the accepted release has installed it and the shared destination. Example shape, placeholders intentionally non-operational until the actual approved paths are resolved:

```sh
python3 -m control_plane.fleet_health_handoff --once \
  --observer-root "$EXISTING_FABRIC_OBSERVER_ROOT" \
  --handoff-root "$INSTALLER_ENROLLED_SHARED_FLEET_ROOT"
```

There is deliberately no `--daemon`, scheduling switch, arbitrary timestamp override, publisher credential or shell/API server. Do not create a separate polling LaunchAgent or cron. Do not edit/activate the incumbent `host_pull.sh` outside its original installed owner, especially with PR #1404's live telemetry cadence and thermal controls. PR #1363's held host-collector activation must remain held; this is not an alternate carrier or replay for that effect.

### Read consumer integration — currently held

`read_fleet_health_handoff(shared_root, window="24h")` can consume the one-file projection without traversing `~/.claude`. It was tested with temporary directories as the same user, **not** with `_mastermind_exec` on production. The existing installed Workspace service currently has optional `workspace_fleet_observer_root`, whose provider binds **direct raw observer reads**. That existing source still fails safely where the actual service lacks private-directory access.

The intended next source change is to use an installer-enrolled **shared handoff directory**, rather than pointing the service at private raw observer state. A 2026-10-13 Studio source edit for the exact `_workspace_fleet_reader_from_config` binding was explicitly blocked by the platform safety check before dispatch; readback confirmed no change. That specific modification is **not authorized to be retried, reframed or moved to another tool/provider/carrier** by this source-only packet. Preserve the denial and resolve it through the appropriate permission/safety authority before attempting the same effect. The optional configuration spelling, service factory binding, tests and documentation must be updated together under that actual permitted path. Do not silently install a handoff source that the authenticated service cannot consume.

## Acceptance and proof

1. The original Fabric owner installs the reviewed one-shot reporter and invokes it in the **existing** collector pass only, without changing worker admission, collector cadence, or source identity. The publisher user owns the exclusive sanitized destination; the Executive user has only verified read access to that one directory/report.
2. Validate one actual host observation across both UID boundaries. Confirm shell/service/file ACLs, fixed sample freshness under timer drift and atomic replacement, no private source path/alias leak, 1h/24h/7d/30d history representation, expired/nonregular/symlink/future/unreadable refusal, and no new collector process.
3. Only after the binding integration has been lawfully accepted, route this fixed projection through the existing authenticated `GET /workspace/fleet/current?window=<closed-enum>` and web/Tauri consumer. Verify user authentication and mid-read revocation, sign-out abort, real Ubuntu current data, Mac missing-sensor status, old host staleness, per-agent occupancy scope, no unintended new-job placement or host settings.
4. Exact-head independent review and required CI, protected merge, installed service/gateway/native-account selection and genuine browser acceptance all remain separate proofs. A GitHub PR or a same-user report reader does not establish production acceptance.

**Operational rollback:** Stop the optional one-shot publication hook only through the original Fabric collector installation owner, remove/unbind the shared handoff under the approved installer, and confirm authenticated Fleet returns typed UNAVAILABLE; do not remove the collector or roll back its unrelated accepted thermal mitigation.

## Observability limitations to retain

The current Mac observer does not provide consistently qualified temperature, CPU-busy percentage or precise total-memory measurement. The new app shows `Unavailable` rather than inferred zero. Normalized one-minute load above 1.5× logical CPU count for 30 contiguous minutes can justify a **performance** recommendation only, never a hardware-damage or temperature diagnosis. Fabric active lanes exclude some native/nested/unmanaged agents; process candidates are not summed into a total. 7-day and 30-day query choices do not create retained samples if the existing log rotated. A long-term maintenance or hardware-damage conclusion requires actual manufacturer sensor limits, thermal/throttling evidence, cooling/fan/power signals and sufficient sampled time, not CPU load or uptime alone.
