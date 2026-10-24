# Mastermind fleet — Linux hourly hygiene peer

This is an adjunct to the EXISTING Mastermind fleet storage-maintenance toolkit
and existing M2/M1/MacBook 30-minute sweepers, not an alternative coordinator,
watcher lifecycle, worker queue, or Git authority. See `README.md` and issue #1632.

* `linux_hygiene.py` samples root and `~/lanes` free space, inodes,
  MemAvailable/swap, optional **operator-supplied** configured Fabric floor,
  and shallow `~/lanes/wt` directory ages. It writes one JSONL heartbeat each run
  to `~/.local/state/mastermind/storage-cleanup/linux-hygiene.jsonl`.
* When under pressure, `--apply-safe-caches` may use **package-manager cache
  commands** (pip and uv; npm additionally in critical mode) only when their
  usual local cache directory exists, no matching install process is observed,
  and no previous cleanup effect is held unverified. These actions cannot be
  claimed as exact reclaimed bytes from free-space deltas alone.
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

Calm: health/inode/memory/volume receipt; no destructive cleanup. Caution:
safe package caches, protected stale-worktree candidate report. Critical:
additional npm cache eviction after process check, alert incumbent Fleet owner
for exact Git/PR/lease adjudication and for blocked Fabric admission. Never
lower the host picker's storage reserve to make a warning disappear.

Rollback for an authorized operator is to disable the Linux timer, not to
touch the existing M2 Mac sweepers. Routine runs must never self-disable.
