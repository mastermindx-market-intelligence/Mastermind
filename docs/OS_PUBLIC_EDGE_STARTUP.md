# Public edge startup for an API-managed Caddy service

An API-published route can work while the service's saved startup and reload
commands still select an older Caddyfile that omits it. Reloading that file can
discard the route. Re-adapting a Caddyfile fragment is not necessarily an exact
native-configuration reconstruction: route ordering, groups and TLS automation
subjects can change.

`ops/executive_os/caddy-api-autosave.service.conf` is an **inactive, explicit opt-in
drop-in**. It makes both commands select the existing native JSON autosave. It
does not copy, adapt, regenerate or edit configuration, enable itself, or change
the service user. The executable and existing `--environ` startup and `--force`
reload flags are preserved. No automatic installer selects this file.

This candidate is specific to the stated executable and autosave paths. It must
not be applied to another service or environment by substitution. The inspected
Caddy v2.11.4 [configuration loader](https://github.com/caddyserver/caddy/blob/v2.11.4/cmd/main.go)
treats an explicit `.json` path as native JSON when no adapter is specified; it
does not use the Caddyfile adapter or the `--resume` alternate-path behavior.

## Existing-owner qualification before activation

The existing edge owner must establish all of the following at the actual
activation boundary, using its supported operation and custody controls:

- The effective service, executable/version, user, environment and original
  Start/Reload commands match the intended service. Environment-derived autosave
  output must equal the exact input path in this candidate.
- The autosave is a present, nonempty, valid native configuration under the
  required file and directory custody. API persistence is enabled. No symlink,
  path, ownership or unexplained content drift is accepted.
- The then-qualified complete live API configuration equals the actual autosave
  JSON, including TLS policies and every non-OS field. A historical digest or
  matching OS route alone is insufficient.
- No publication or other conflicting writer is in flight, and no earlier effect
  remains uncertain. Validate the actual file through the supported Caddy
  interface as the actual service user with its unchanged environment.

Independent review of the changed service/configuration authority is required.
Source review does not supply any missing live evidence or activation authority.
The applicable release and host gates remain in force.

## Bounded activation and acceptance

Retain the original unit/drop-ins and configuration references before any write.
After the controlled drop-in installation and daemon-reload, verify the effective
Start and Reload commands. Daemon-reload is not application reload or restart
proof. Any subsequent reload and eventual approved restart need their own actual
PID, complete configuration, TLS and HTTP observations.

The drop-in itself supplies neither an atomic file-read/publication fence nor an
autosave crash-consistency guarantee. Those properties must not be inferred from
an in-flight check, successful validation or an unchanged historical digest.

On an uncertain effect, preserve the operation and reconcile through the same
owner. Do not blindly retry, restart or restore a command selecting the known
incomplete Caddyfile. Recovery follows the existing effect rules.

Future accepted API changes continue to persist to the same existing autosave.
Changing persistence, autosave path/custody or the service's input invalidates the
durability join. This source artifact does not alter publisher intent handling,
allow extra publication attempts, change certificate authority, or prove product
behavior after a restart.
