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

## Fixed-preview installation preparation — source only

`preview_install.py` provides the missing narrow installation/preflight operation
inside this existing owner. It has **no network or automatic entrypoint**. Its
only file targets are `linux_cache_preview.py` on Linux and the existing
`fleet_remote_sweep.py` on M2. It cannot install a service, change enrollment or
admission, clear a lease, reclaim cache bytes, or run the preview/sweeper.

The receiver must first qualify the actual maintenance authorization, protected
source bytes and current target custody. Public Fabric enrollment is addressing
evidence, not that authorization. `enrolled_binding` resolves the semantic Ubuntu
ID through the existing `ext/hosts.json` `ssh_alias`/`hostnames` and the same
account's public SSH configuration. Dynamic Include/Match or unknown mappings
are held rather than evaluated by another process. No credentials are read.
For example, an enrolled `ubuntu0` can resolve to `mmx-ubuntu0`; the literal
`--hosts ubuntu0` spelling alone is never a qualified maintenance operation.

`transport_plan` prepares one argv for the existing driver's `SSH`/`run` carrier,
without calling it. The operation is only fixed-target `inspect`, `install`, or
source-bound `preview`; each remote command first requires the exact expected
account and enrolled machine hostname. There is no reachability probe, rsync,
alternate alias/host, retry, sweep or fallback. A separately authorized operator
must re-read/reconcile the public binding at action time before using that argv.
Inspect/install planning also requires `expected_installer_sha` from the already
qualified immutable source packet. A fresh file read cannot supply its own trust
pin: its no-follow/stable bytes must match that independent pin before a command
is prepared, and the same pin is verified before remote compile/exec.

Remote installed preimages remain UNKNOWN until an authorized fixed `inspect`
actually reports their SHA or ABSENT. Unknown is never converted to ABSENT.
Installing requires that exact observed preimage and the accepted payload SHA.
M2 driver installation additionally requires its exact current installed SHA.
The original fleet-driver lock (M2) or admission lock and empty active namespace
(Linux) must be available. No stale marker is removed. Target directories,
ownership, modes, symlinks, hardlinks, namespace and lock identity are checked.

Before replacement, the installer verifies an import of the accepted module
under a non-main name, durably retains the original bytes when present and
writes a PREPARED receipt in the existing storage-cleanup state directory.
It rechecks the exact target preimage, then atomically replaces that fixed file;
an ABSENT target uses atomic no-replace. A matching postimage import produces a
separate VERIFIED receipt. Neither import invokes preview, sweep or network.
The named receipt-state directory is rejoined with its held descriptor alongside
the toolkit/lock namespace, including after the postimage import and terminal
receipt write. Observed drift withholds successful acceptance.
An UNKNOWN companion dominates any already-written terminal receipt; failure to
retain it does not clear the caller's same-operation unknown-effect hold.
An unresolved PREPARED record holds later installs, including new IDs. After an
uncertain effect there is no automatic rollback or replay: the same owner must
reconcile the target and retained backup/receipt. Installing does not itself
authorize a preview or cleanup, and does not prove physical capacity recovery.
This narrow installer is one-shot: even a prior VERIFIED record requires fresh
existing-owner reconciliation before a new install ID/version. A written terminal
artifact is not proof that its last fence/fsync returned; it never grants another
effect. Fixed read-only inspection remains available and does not clear history.
No history-removal or automatic reconciliation command is supplied here.

Hermetic installer checks: `python3 -m unittest tests.test_storage_preview_install`.
The source candidate and prepared operation packet have not installed anything
or invoked a remote host. Root retains the actual installation/preview decision.
