# Mastermind fleet — Linux hourly hygiene peer

This is an adjunct to the EXISTING Mastermind fleet storage-maintenance toolkit
and existing M2/M1/MacBook 30-minute sweepers, not an alternative coordinator,
watcher lifecycle, worker queue, or Git authority. See `README.md` and issue #1632.

* `linux_hygiene.py` samples root and `~/lanes` free space, inodes,
  MemAvailable/swap, optional **operator-supplied** configured Fabric floor,
  and shallow `~/lanes/wt` directory ages. It writes one JSONL heartbeat each run
  to `~/.local/state/mastermind/storage-cleanup/linux-hygiene.jsonl`.
* **Current source-release HOLD: no package-manager purge is admitted.** A
  checked pathname can be replaced between preflight and a third-party
  manager's destructive open. No independently qualified inode-bound/namespace
  handoff exists; the source `manager_effect_target_bound()` is intentionally
  fail-closed and cannot be enabled by environment variables. Even when
  `--apply-safe-caches` is selected under pressure, the original timer only
  reports `HELD_UNBOUND_CACHE_TARGET`, `effect_state=NOT_APPLIED`, with a
  degraded/nonzero completion; it never invokes pip, uv or npm to delete cache
  data. Safe *telemetry* remains useful and the hourly timer stays enabled.
  The historical manager-effect tests inject simulated future confinement
  into hermetic mocks; they are **not** production effect authorization.
  A real manager purge requires a new reviewed, end-to-end kernel-bound target
  implementation and independent negative tests before this hold is lifted.
* The previously designed package-manager cleanup workflow, **currently
  unreachable from the production source**, uses pip and uv (npm additionally
  in critical mode) only when local cache paths exist, no active package writer
  (including `uvx`) is observed, and no previous effect is held unverified. Each manager invocation
  requires exact same-device root/cache before-and-after bytes and available
  inodes, and the durable PRE_EFFECT marker carries its exact preimage. Loss of
  device identity or postimage retains the EFFECT_UNVERIFIED hold. Before
  releasing the marker after a verified exit, a separate per-effect settlement
  is fsynced to the SAME canonical JSONL ledger, including its directory entry;
  settlement write failure retains the hold and forbids unattended replay. An observed
  free-space delta is NOT attributed to package-manager reclamation; until
  distinct manager-specific byte proof exists the attributable counter stays
  zero with an explicit NOT_ESTABLISHED attribution field.
* Package-manager nonzero exits retain only the exit code and a fixed error class;
  captured stderr is never copied into JSONL because it can contain credentials
  or private URLs. An `stderr_redacted` flag records its suppression.
* NO deletion of a Git worktree, registered Git metadata, external archive,
  root clone, `/tmp`, models, build artifacts, or user files is automated.
  An old directory is a TRIAGE CANDIDATE only. Human ChatGPT worktrees may be
  attached without a process; Fabric leases and last-effect/PR proof must be
  reconciled by the incumbent owner before removal.
* `classify` is the cleaner's intensity signal, not a replacement for Fabric's
  admission floor. A missing local floor is UNVERIFIED, never assumed cleared.

## Installation through original host owner (per host, after review)

Install source files with exact SHA/readback into
`~/.local/lib/mastermind/storage-cleanup/linux_hygiene.py` and
`~/.config/systemd/user/mastermind-linux-hygiene.{service,timer}`. Preserve
any pre-existing files and stop if their identities differ. Check
`loginctl show-user "$USER" -p Linger` reports `Linger=yes` (if not, request
authorized host administrator assistance; no sudo bypass).

**Remote user-bus preflight (observed on Ubuntu3, 2026-10-24):** SSH and
Desktop Commander noninteractive shells sometimes omit the user D-Bus
environment even when `Linger=yes` and the real user timer manager is active.
A bare `systemctl --user` then reports `Failed to connect to bus: No medium
found`; this is **not** proof that a timer is stopped. Use only this same
logged-in user's existing bus, after verifying that its runtime directory and
socket exist and are owned by that UID:

```sh
uid="$(id -u)"
test -d "/run/user/$uid" && test -S "/run/user/$uid/bus" || exit 1
test "$(stat -c %u "/run/user/$uid" "/run/user/$uid/bus" | sort -u)" = "$uid" || exit 1
export XDG_RUNTIME_DIR="/run/user/$uid"
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus"
systemctl --user list-timers --all
```

Do not manufacture another bus, alter access grants, use a different user's
manager, or infer an install from this read-only preflight. If this original
manager is unreachable, keep the installation pending with its exact failure.

Validate with `/usr/bin/python3 .../linux_hygiene.py` first (report-only),
then run `systemctl --user daemon-reload` and
`systemctl --user enable --now mastermind-linux-hygiene.timer`.
Verify `systemctl --user is-enabled`, `is-active`,
`list-timers --all`, `systemctl --user start ...service`, and the
fresh JSONL receipt. Periodic service runs stay ON indefinitely; a calm hour
writes a heartbeat rather than disabling or removing the timer. Another
independent hourly observer should alert if the timer stops, an expected
heartbeat is missing, or a host is unreachable. Never promise uninterrupted
execution during power loss or disconnected hosts.

To test: `python3 -m unittest discover -s tests -p test_fleet_linux_hygiene.py`.
Safe bounded production commands use only built-in Python/systemd and the
original host's logged-in user. The timer's lock prevents self-overlap;
other actual Fabric/source leases remain independent and authoritative.

## Pressure-specific action

Calm: health/inode/memory/volume receipt; no destructive cleanup.
Caution/critical: pressure and protected stale-worktree candidate report;
**package-manager eviction is HELD_UNBOUND_CACHE_TARGET and NOT_APPLIED** until
the atomic target-confinement release gate is independently satisfied. Critical
pressure alerts the existing Fleet owner for exact Git/PR/lease adjudication
and blocked Fabric admission. Never lower the host picker's reserve.

Rollback for an authorized operator is to disable the Linux timer, not to
touch the existing M2 Mac sweepers. Routine runs must never self-disable.
