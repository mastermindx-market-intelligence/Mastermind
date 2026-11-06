# Existing fleet storage-sweeper source snapshot

This is checked-in source for two EXISTING installed scripts, not a new daemon,
scheduler, storage authority, or alternative cleanup queue.

- Production install path on M2: ~/.local/lib/mastermind/storage-cleanup/
- Existing launch agents: com.mastermind.storage-sweeper and
  com.mastermind.fleet-remote-sweeper.
- M2 remote driver already synchronizes its toolkit to M1 and MacBook over SSH.
- Other helper scripts remain in the installed toolkit; these source files are
  not a standalone deployment bundle. Never run sweep.main() in CI or tests:
  that entry point invokes active cleanup passes.
- This source snapshot is reviewable and tested to prevent unexplained host-local
  fixes. Source acceptance is separate from installed/armed/real-path proof.

## External volume observation added October 19, 2026

The existing sweep.py records read-only snapshots of configured external mounts
and the external mount backing ~/lanes. It refuses to count an absent mount as
available root volume space.

The existing fleet_remote_sweep.py consumes those observations and adds
external-volume warnings and breach evidence. A prior confirmed breach stays
unverified during repeated host outages and clears on a fresh healthy reading.
Root volume telemetry, cleanup mode, age gates, authority and locking remain
unchanged. No new deletion commands or workers are introduced.

Observation sources are only ~/.config/mastermind/worktree-storage.json and
the mount behind a symlinked ~/lanes, not recursive directory searches.

Thresholds:
- Critical floor: max(60 GiB, 14 percent of volume size).
- Warning floor: max(120 GiB, 22 percent of volume size).
- Unmounted volumes: UNVERIFIED, not healthy.

Acceptance test:
  python3 -m unittest discover -s tests -p test_fleet_storage_volume_monitor.py

Testing is hermetic. Host installation separately requires exact preimage hashes,
a known backup, atomic replacement, source import verification and an M2-to-M1
peer observation. Do not interpret green CI as production deployment.

Current program receipt: Mastermind GitHub issue #1632.

A peer lacking the new telemetry field produces TELEMETRY_MISSING (unverified),
and an unreadable volume policy is an unverified alert, not a healthy reading.

## Linux disposable-cache preview — source candidate, not enrolled

`linux_cache_preview.py` is an extension of this same storage-sweeper owner.
It has **no apply/delete mode** and starts no worker, network request, process
control, service or scheduler. Source acceptance does not enroll a Linux host,
install the module, grant host access, clear admission holds or recover space.

The first narrow subset is the current non-root user's fixed `.cache/pip` and
`.npm/_cacache` namespaces. Only recognized cache top-level layouts are inventoried.
No arbitrary root, pathname, credential file, source tree or worktree is accepted.
Preview counts are observations of candidate bytes, **not deletion authority**.
Unknown entries, symlinks/hardlinks/special files, foreign ownership, group/world
write modes, or another filesystem are held. Cached file content is never read.

The helper takes the existing physical `lanes/ext/active/.admission.lock`
non-blockingly without creating or replacing it. Any lane, reconciliation or
unknown marker holds the preview. The same-user Linux procfs cwd/executable/open-FD
census is required before and after inventory; incomplete or changing evidence
holds. Unresolved PREPARE records in the existing `generated-cache-trim.jsonl`
also hold. No new effect registry is created. Each cache is bounded by 20,000
entries, 12 levels, 256 GiB of counted bytes and the five-second inventory budget.
Only caches on the worker-admission filesystem are counted as preview candidates.

A new mode in the **existing** fleet driver compiles exactly one command using
its existing transport and a SHA-256-bound installed module. It does not probe,
sync/install, run the old sweep, retry or fall back. The source integration shape
for a separately authorized/enrolled operator is:

```
fleet_remote_sweep.py --linux-cache-preview --hosts ubuntu0 --no-sync --timeout 20
```

The closed host spelling is addressing validation, not permission to select a
worker or a new host grant. Current assignment, actual maintenance access, exact
installed source and host custody must still qualify. A missing or old installed
helper returns UNAVAILABLE. This command has **not been invoked on a fleet host**
for source qualification, and no current generation/host profile is changed here.

The helper writes one owner-only, write-once preview receipt beneath the existing
storage-cleanup state directory. The response contains fixed cache IDs, counts,
filesystem-available bytes, inventory digest, bounded hold reasons and the receipt
hash; it excludes file contents and arbitrary file names. The receiver checks the
closed body and receipt digest. `cleanup_authorized` is always false. Receipts are
transient evidence and cannot be replayed as apply tokens; a future cleanup effect
would need its own reviewed custody/source/currentness checks and authorization.

Hermetic checks (temporary directories, simulated procfs and mocked fleet transport):

```
python3 -m unittest tests.test_linux_cache_preview tests.test_fleet_storage_volume_monitor
```

Do not run `sweep.main()` or any remote invocation in tests. Existing scheduled
sweep behavior is unchanged unless the new explicit preview flag is supplied.
