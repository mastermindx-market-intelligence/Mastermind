# Existing fleet storage-sweeper source snapshot

This is auditable source for three EXISTING installed fleet-toolkit scripts,
not a new daemon, scheduler, storage authority, or alternative cleanup queue.
The archive-helper source here is a proposed fail-closed B7 repair only: the
incumbent installed helper remains unchanged until separately qualified release.

- Production install path on M2: ~/.local/lib/mastermind/storage-cleanup/
- Existing launch agents: com.mastermind.storage-sweeper and
  com.mastermind.fleet-remote-sweeper.
- M2 remote driver already synchronizes its toolkit to M1 and MacBook over SSH.
- Other helper scripts remain in the installed toolkit; these source files are
  not a standalone deployment bundle. Never run sweep.main() or the archive helper
  at top level in CI or tests: those entry points can invoke cleanup passes.
- pull_remote_archive.py is the existing report-only/archive helper's source-bound
  B7 candidate. It refuses success-shaped empty SSH output and failures of lsof,
  find, du or invalid inventory rows; it does NOT install, arm, schedule or authorize
  the helper's existing --apply mode. This candidate now explicitly refuses
  --apply with exit 78 before SSH or destination effects: destructive remote
  deletion needs an exclusive incumbent owner/identity lease spanning proof
  through removal plus independent release review; the legacy double idle
  probe alone is insufficient. Original production helper provenance and
  installer composition remain a separate protected-release gate.
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

B7 source-only hermetic regression: `python3 -m unittest discover -s tests -p test_fleet_storage_archive_probe_contract.py`.
This AST-extracts only pure functions and the embedded probe, intercepts every
subprocess call, and never connects to hosts or executes a production cleanup.

The original hourly Mac sweeper's top-level success classification is also
source-gated: successful receipt-bearing helpers must not have empty stdout;
a forced localhost loopback must report the current pass epoch and zero statuses
for all mandatory cleanup scans; both nested report-only archive peers must
identify their own host and the parent's policy-selected destination. A failed
proof is written in `incomplete_substeps` and causes a nonzero top-level exit;
it does not trigger a cleanup retry or grant a new deletion authority. This
narrow check does **not** certify the content semantics of every installed
helper's nonempty stdout, nor prove an installed B7 source. It is source-only
until nonauthor review, protected merge, original source/preimage qualification
and real existing-service receipt readback. Hermetic regression:
`python3 -m unittest discover -s tests -p test_fleet_storage_volume_monitor.py`.

## B11 source-only hold: the stale-pack reaper is never invoked apply-capable

The installed `stale_pack_reaper.py` is **not source-enrolled** in protected
Mastermind (there is no `ops/fleet_storage_cleanup/stale_pack_reaper.py` in the
protected source tree), and its `--apply` path is not owner/inode-bound: it
stats a candidate, runs `lsof` against the *path*, and then unlinks that path
without re-binding the unlink to the identity it checked, so a writer that
replaces the pathname in between can make the unlink hit a different live file.
It also enters the candidate loop before its own incomplete scratch find/scan is
known, so an incomplete discovery is a late rc2 rather than a pre-effect
abstention.

This source change therefore removes apply capability from the candidate
sweep:

- The stale-pack pass runs as a **never-apply inventory** only. Its argv is
  built in exactly one place (`stale_pack_argv`) and is checked against a
  strict **allowlist** — exactly
  `[<interpreter>, <helper path>, '--json', '--min-age-minutes', <positive
  integer minutes>]` — both where it is built and again at the boundary where
  the argv is about to be executed. A denylist of apply-capable spellings is
  not sufficient: the installed helper parses its arguments with a default
  `argparse.ArgumentParser()`, so `allow_abbrev` is true and `--a`, `--ap`,
  `--app` and `--appl` are each accepted as `--apply`. Any other argv shape,
  any abbreviation of an apply-capable flag, any non-integer or non-positive
  `--min-age-minutes`, and any option-like helper path are refused, so a later
  edit that re-adds apply capability fails closed instead of shipping. A
  refused invocation is recorded as a degraded pass (`stale_packs_rc` 78) and
  never loses the receipt.
- The **recurring telemetry is retained**: the pass still runs on every
  scheduled sweep and still reports its discovery receipt. No duplicate reaper
  and no second scheduler are introduced.
- The receipt names the hold explicitly — `stale_packs_hold:
  HELD_UNQUALIFIED_STALE_PACK_HELPER` and `stale_packs_effect_state:
  NOT_APPLIED` — and `finish()` records `stale_packs.held_unqualified_helper`
  in `incomplete_substeps`, so the sweep is **degraded, never green**, while
  the hold is in force. There is no bypass: no flag, environment variable or
  receipt path re-arms the apply mode.
- All other helper flow, receipt and last-exit contracts are unchanged. The
  helper's own exit code is still reported verbatim in `stale_packs_rc`; a
  discovery receipt reports `applied=false` and therefore can never satisfy the
  applied-receipt contract of the existing inventory check.

This is source-only. It does not install, arm, schedule or authorize anything,
does not prove an installed preimage, and does not qualify the helper for
native release. Host installation still separately requires exact preimage
hashes, a known backup, atomic replacement, source import verification and an
M2-to-M1 peer observation. Hermetic regression:
`python3 -m unittest discover -s tests -p test_fleet_storage_volume_monitor.py`.
