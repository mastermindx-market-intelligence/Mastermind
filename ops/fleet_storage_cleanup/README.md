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
- The **recurring sweep telemetry is retained**: the sweep still runs on every
  scheduled sweep, and its own free-space sample, external-volume snapshots
  and sweep-log row are unaffected. What this source no longer does is ask
  the installed helper for a discovery receipt at all: the helper is not
  source-enrolled here, so the coordinator holds the pass BEFORE any helper
  subprocess instead of running installed source it cannot bind. No duplicate
  reaper and no second scheduler are introduced.
- The receipt names the hold explicitly — `stale_packs_hold:
  HELD_UNQUALIFIED_STALE_PACK_HELPER` and `stale_packs_effect_state:
  NOT_APPLIED` — and `finish()` records `stale_packs.held_unqualified_helper`
  in `incomplete_substeps`, so the sweep is **degraded, never green**, while
  the hold is in force. There is no bypass: no flag, environment variable or
  receipt path re-arms the apply mode.
- All other helper flow, receipt and last-exit contracts are unchanged. A
  receipt retained by an earlier dispatch reports `applied=false` with exact
  integer zero counters, which is a zero-effect **producer claim**; it is a
  complete inventory only when its discovery census is complete and
  error-free, and it is never proof that the installed helper is enrolled.

This is source-only. It does not install, arm, schedule or authorize anything,
does not prove an installed preimage, and does not qualify the helper for
native release. Host installation still separately requires exact preimage
hashes, a known backup, atomic replacement, source import verification and an
M2-to-M1 peer observation. Hermetic regression:
`python3 -m unittest discover -s tests -p test_fleet_storage_volume_monitor.py`.

## B12 source-only pre-effect hold: generated cache helper

The M2-only `generated_cache_trim.py` is **not enrolled in the protected
Mastermind source tree**. Its installed `--apply` behavior has not been
independently qualified against the installed preimage, active worktree
ownership, or an effect-safe completion contract. A nonzero or degraded
receipt written **after** a subprocess exits cannot undo deletions performed
earlier by that subprocess.

The existing sweeper therefore records
`generated_cache_trim_hold=HELD_UNQUALIFIED_GENERATED_CACHE_HELPER`,
`generated_cache_trim_effect_state=NOT_APPLIED`, and
`generated_cache_trim_rc=78` on the M2 path without invoking this helper.
`finish()` also records `generated_cache_trim.held_unqualified_helper`
in `incomplete_substeps`, even if a success-shaped helper receipt is
later injected. Other existing sweeper passes, the original timer,
kernel flock, and host configuration remain unchanged. No replacement
cleaner or inventory script is introduced.

This is an **inert source candidate**, stacked on the independently
reviewed Draft stale-pack guard #1900 and its #1877 base. Neither Draft
source approval nor green CI authorizes install, reconfigure, restart,
cache removal, ref publication, or merge. Before any eventual native
release, the existing installed-sweeper owner must reconcile exact
preimages, preserve backups, qualify source/effects of the unenrolled
helper, obtain independent review and protected integrated CI, and
prove one natural existing-service execution/JSONL result. Hermetic
coordinator regression: `python3 -m unittest discover -s tests -p
test_fleet_storage_volume_monitor.py`.

## S5 source-only: pre-dispatch holds, delegation hold, and truthful effect evidence

Source-only candidate on top of the B11/B12 holds. It installs nothing, arms
nothing, and grants no apply capability. The strict argv allowlist, the
zero-effect inventory predicate, the grant gate, the kernel flock, the #1951
generated-cache hold, the fleet sparse/repack/archive holds and the
external-volume telemetry are unchanged.

### The stale-pack pass holds BEFORE any helper subprocess

The installed `stale_pack_reaper.py` is not source-enrolled in protected
Mastermind, so this coordinator cannot bind the installed source or its
preimage. A request-side guard does not bind the source that answers the
request. The pass therefore refuses **before any child is started**: it builds
and validates the never-apply argv (purely — building an argv starts no
child), records the existing `HELD_UNQUALIFIED_STALE_PACK_HELPER` hold with
`stale_packs_rc` 78, `stale_packs_effect_state=NOT_APPLIED` and
`stale_packs_verified_reclaimed_bytes=0`, and dispatches nothing.

- There is **no runtime bypass**: no flag, environment variable or receipt
  path re-arms the helper.
- The no-dispatch is scoped to **this invocation**. It reconciles nothing of,
  and claims nothing about, any prior unknown effect.
- The sweep's **independent** telemetry is unaffected: the free-space sample,
  the external-volume snapshots and the recurring sweep-log row still happen
  on every sweep. What does not survive is the helper's own discovery receipt,
  because this source no longer asks for it.
- The argv builder and the zero-effect inventory predicate are kept as **pure**
  functions: they are what the pure retained-receipt classifier reads when it
  judges one receipt retained by an earlier dispatch.

### The denied-grant loopback delegation is held before any forced child

When the grant context is denied or unverified, the incumbent design's last
resort is to re-enter the same sweep over ssh to `127.0.0.1`, where a
Remote-Login session holds the grants. That delegation is now **held before
any ssh or forced-child invocation**.

The forced `authorized_keys` command starts the **host's installed sweeper**.
The parent nonce and the kernel flock bind the *request* and the exclusion of
a concurrent sweeper; they do **not** bind the installed source or preimage
the child would run. The same gap that keeps the unenrolled stale-pack helper
undispatched applies here for the same reason.

The transport, auth and lock code in `via_loopback()` is preserved unchanged;
only the admission of the delegation is held. The helper-exclusion lock is not
relinquished either, because there is no child to hand it to. The receipt
names `loopback_hold=HELD_UNBOUND_LOOPBACK_CHILD_SOURCE`,
`loopback_effect_state=NOT_APPLIED` and `loopback_rc=78`, and `finish()`
records `loopback.held_unqualified_child_source` in `incomplete_substeps`.
There is **no qualification flag**: restoring the delegation requires the
original owner to bind the installed child source/preimage, which is not a
source-level decision.

### Retained receipts are classified truthfully

A retained receipt is a **producer claim**: what an unqualified helper says
about itself. It is never proof that the installed helper is enrolled,
source-identified or safe to run apply-capable.

One retained receipt is classified by a **pure** classifier: it reads that
single captured text and the exit code retained with it, and it writes
nothing. The **existing** append-only `sweep-log.jsonl` remains the owner of
history — this source adds no history reader, no journal, no history
authority and no controller, and it reconciles nothing. An unknown row stays
unknown; no missing history is claimed to be cleared.

The classification is strict, because what a receipt retains is a **captured
excerpt** — the last stdout line, truncated at the capture limit — and not the
helper's full original stdout:

| retained evidence | verdict |
| --- | --- |
| `applied` is exactly `false`, `removed` and `freed_bytes` are exact int `0`, **and** the discovery census is complete and error-free | `NOT_APPLIED` — a zero-effect **producer claim** that also claims a complete inventory |
| `applied` is exactly `false`, `removed` and `freed_bytes` are exact int `0`, but the discovery census is missing, incomplete or errored | `NOT_APPLIED` — a zero-effect **producer claim**; the inventory claim stays **incomplete** |
| `applied: true`, a positive counter, or a value that cannot be read as "no effect" | `EFFECT_UNKNOWN` — the raw text is retained verbatim |
| an **omitted** effect field | `EFFECT_UNKNOWN` — an omitted field is missing evidence, not evidence of no effect |
| text that does not parse (malformed, truncated, capture loss) | `EFFECT_UNKNOWN` — a parsing failure can never prove `NOT_APPLIED` |
| a nonzero rc (timeout, interrupted pass) | `EFFECT_UNKNOWN` |
| a **missing or null rc**, or an rc that is not exactly the int `0` (bool, float, string) | `EFFECT_UNKNOWN` — only an exact int rc of `0` can carry a completed producer claim at all |

The verified reclaimed-byte count is always `0`: nothing an unenrolled helper
reports can be verified as reclaimed by this coordinator.

The **unknown classification is monotonic within one observation**: once a
receipt has been classified `EFFECT_UNKNOWN`, a later zero or blank value for
the same key does not downgrade it. The coordinator's own pre-dispatch refusal
is left alone — a known non-dispatch is not an unknown effect — but it is
recognised by the **structured hold metadata** the current stale-pack pass
emits together with the incumbent refusal rc `78`, **not** by the refusal text
alone. The exact refusal text with any other rc, or without that structured
hold metadata, is not a proven coordinator refusal and stays
`EFFECT_UNKNOWN`.

No runtime helper is retried automatically, because runtime dispatch is
unconditionally held.

### Seven pre-effect holds

`hold_unqualified_apply` keeps a **closed** tuple of unqualified apply call
sites, and each of the seven remaining apply invocations is replaced by that
existing pre-effect hold (`rc` 78, `NOT_APPLIED`, `PRE_EFFECT_HOLD: ...`):

| pass | helper | applicability |
| --- | --- | --- |
| `hung` | `hung_process_reaper.py` | every run, recorded **before** the grant gate |
| `temp_gc` | `temp_worktree_gc.py` | every granted run |
| `temp_gc_generic` | `temp_worktree_gc.py` | every granted run |
| `reap` | `reap_incomplete_temp_worktrees.py` | every granted run |
| `sparse` | `sparse_idle_worktrees.py` | only when the sparse census is eligible |
| `scratch_reap` | `scratch_reap.py` | every granted run |
| `chain_archive` | `chain_snapshot_archive.py` | only when the chain snapshot dir is eligible |

A hold is a statement about **enrollment**, not a claim of a proven internal
defect in the held helper. What is missing at this coordinator boundary is the
qualification itself: exact installed/source identity; operation-specific
complete discovery; the original owner/device/inode with the current lease
and the active worktree; the reserve; and interruption reconciliation — plus
PID/start identity, ownership and carrier protection for the process reaper.
One census of one helper does not qualify another, and a flag never fakes
qualification. The original `generated_cache`, `fleet_sparse`, `repack` and
archive holds are unchanged.

Consequences that are part of the contract:

- The held helpers never appear in the coordinator's child-process argv, so
  nothing apply-capable is spawned on any applicable path. The stale-pack
  helper is held the same way, so **no child at all** is spawned for it.
- The `--receipts` directory is prepared **only for a consumer that will
  actually launch**. Every consumer of the temp-GC/reap and sparse receipt
  directories is held, so the removable-volume mkdir/write probe never runs
  for a helper that will never run.
- A hold is an abstention, not a successful assessment: the chain-archive
  success stamp is **not** advanced, so the condition is re-evaluated on the
  next sweep.
- A hold degrades the receipt by itself (`<pass>.held_unqualified_helper`), so
  a success-shaped receipt or a zero exit code injected later cannot rearm a
  pass that never launched.
- The incumbent applicability conditions are unchanged: on a calm host with
  headroom the sparse census and the repack are still deferred, and those two
  passes are neither launched nor held there.

### A corrected comment about live transfers

The stale-pack pass comment previously claimed that the helper "refuses any
file a process still holds open, so a live transfer is never interrupted".
That claim was false: `stat` + `lsof` is a **path** check, not an
owner/inode binding, so a writer that replaces the pathname in between can
still be hit. The comment now says so, and points at the hold.

Hermetic regression (no live sweep, no helper, no host, no native file):
`python3 -m unittest discover -s tests -p test_fleet_storage_volume_monitor.py`.
