#!/usr/bin/env python3
"""Periodic storage sweeper (launchd: com.mastermind.storage-sweeper, every 30 min).

Two bounded, receipted actions, both fail-closed and both already proven by hand
on 2026-09-14 (wave 3):
  1. temp_worktree_gc.py --apply  — removes orphaned detached temp worktrees
     (check_contract_delta.py leftovers etc.). Age gate adapts to disk pressure.
  2. sparse_idle_worktrees.py --apply — when the internal disk is under pressure,
     converts idle+clean full macro session worktrees to the repo's sparse profile
     (reversible: `python3 scripts/worktree_sparse.py full`).
A third, passive step writes a free-space sample so the trend is visible.
Pass 0 (every run, any mode): hung_process_reaper.py kills git/gh transports
stuck on the network for >= 3 h with no CPU (needs no TCC grant).

WHO RUNS THIS: on the Studio, the local launchd agent (every 30 min). On m1 and
mb the useful runs come from the Studio over ssh (fleet_remote_sweep.py, every
30 min) because a remote-login session there holds the file grants their launchd
Python.app does not; their own hourly agent is only the Studio-is-off fallback
and its GC passes fail closed with EPERM (visible as `clone_errors`).

Thresholds (fraction of the root volume, floored for small disks):
  < max(14 %,  60 GiB) : pressure -> temp GC min-age 30 min; sparse conversion for trees idle >= 6 h
  < max(22 %, 120 GiB) : caution  -> temp GC min-age 90 min; sparse conversion for trees idle >= 24 h
  otherwise            : calm     -> temp GC min-age 180 min; no sparse conversion
  (Studio 1.8 TiB -> ~250 / 400 GiB; M1 + MacBook 460 GB -> ~64 / 101 GiB)
Also: a one-shot `--push` notification file is written when free space < 80 GiB so a
human can see it in ~/.local/state/mastermind/storage-cleanup/ALERT.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = Path.home() / '.local/state/mastermind/storage-cleanup'
GIB = 1024 ** 3
LOCK = STATE / 'sweep.lock'


def _pool_archive_mount() -> Path | None:
    """Pick a UUID-verified SSD when this host has the two-volume pool policy.

    Single-volume remote hosts keep their own local storage setup. A corrupt or
    missing pool never falls back to the internal disk or unrelated WD archive.
    """
    try:
        config_path = Path.home() / '.config/mastermind/worktree-storage.json'
        policy = json.loads(config_path.read_text())
        if not policy.get('overflow_volumes'):
            return Path('/Volumes/WD 5TB')
        sys.path.insert(0, str(Path.home() / '.local/lib/mastermind/worktree-storage'))
        from worktree_storage import check_storage
        from pool_storage import select
        member = select(policy, lambda item, check_space=False:
                        check_storage(item, check_space=check_space))
        return Path(member['mount_point'])
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'pool_archive_refused': str(exc)[:180]}), file=sys.stderr)
        return None


def ssd_receipts(sub: str) -> list[str]:
    """`--receipts DIR` on the SSD when this process can actually create it.

    Under launchd the agent may lack the TCC "Removable Volumes" grant that the
    interactive shell has (observed 2026-09-14: mkdir -> EPERM on /Volumes/Mastermind),
    so the SSD copy of the receipts is best-effort; the state dir always keeps one.
    """
    try:
        pol = json.loads((Path.home() / '.config/mastermind/worktree-storage.json').read_text())
        if pol.get('overflow_volumes'):
            mount = _pool_archive_mount()
            if mount is None:
                return []
        else:
            mount = Path(pol['mount_point'])
    except (OSError, ValueError, KeyError):
        # No policy means no trustworthy removable destination for a receipt.
        return []
    d = Path(mount) / 'Offloaded' / sub
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / '.write-probe'
        probe.write_text(str(time.time()))
        probe.unlink()
        return ['--receipts', str(d)]
    except OSError as e:
        print(json.dumps({'receipts_ssd_unavailable': sub, 'error': str(e)}), file=sys.stderr)
        return []


# Probe the surface the passes actually read, not the folder above it.
#
# 2026-09-23: the old probe was `chdir(~/Documents); getcwd(); listdir(~/Documents)`.
# macOS lets a context with no Documents grant list that top folder while denying the
# items beneath it, so this returned 'ok' in the very launchd run where 760 of 1667
# worktrees failed with PermissionError(1) on `<clone>/.git/worktrees/<name>` -- and
# fleet_sparsify, whose du then measured 0 KiB everywhere, reported {"sparsified": 0}
# as a clean sweep over a 406 GiB pool. Same defect class as the fleet_archive probe
# that tested ~/Documents while the pass wrote to an external volume: a probe that does
# not touch the surface the pass uses proves nothing about that surface.
#
# Walks the worktree registry of every clone under ~/Documents and opens one entry --
# exactly what sparse_idle_worktrees.py does at the line that raised. Prints the first
# failing path so the receipt names the blocked surface instead of a bare 'denied'.
GRANT_PROBE = r"""
import os, pathlib, sys
home = pathlib.Path.home()
docs = home / 'Documents'
os.chdir(docs); os.getcwd(); os.listdir(docs)
checked = 0
for reg in docs.glob('*/*/.git/worktrees'):
    for entry in list(reg.iterdir())[:3]:
        list(entry.iterdir())          # the call that raises EPERM without the grant
        checked += 1
    if checked >= 3:
        break
if not checked:
    for gd in docs.glob('*/*/.git'):
        list(gd.iterdir()); checked += 1
        break
print(checked)
"""


def grants(timeout: int = 20) -> str:
    """Can THIS context open ~/Documents? -> 'ok' | 'denied' | 'hung'.

    Same operations git does first (chdir + getcwd + readdir), bounded. 'hung' is
    a real outcome, not a hypothetical: under launchd on m1 a git call on a clone
    the job has no grant for blocked for 6 minutes at 0.01 s of CPU instead of
    returning EPERM the way mb's does.
    """
    try:
        p = subprocess.run([sys.executable, '-c', GRANT_PROBE], capture_output=True, text=True, timeout=timeout)
        if p.returncode == 0:
            return 'ok'
        # Name the surface that refused. 'denied' alone sent three sessions looking at
        # the wrong folder; the traceback's last line identifies the exact path.
        tail = [l for l in (p.stderr or '').strip().splitlines() if l.strip()]
        return 'denied: ' + (tail[-1][:160] if tail else 'no stderr')
    except subprocess.TimeoutExpired:
        return 'hung'
    except OSError:
        return 'denied'


FLOOR_CONF = Path.home() / '.config/mastermind/storage-floor.json'


# Mirrors storage_floor_guard.py's DEFAULTS["internal_floor_gib"]. It is duplicated
# rather than imported because that module ends in a bare module-level `sys.exit(main())`
# -- importing it RUNS the guard. Keep the two in step; if the guard's default moves,
# move this. The fallback is load-bearing, not cosmetic: m1 carries NO storage-floor.json,
# so it alarms off the guard's default, and a reader that returned None on a missing file
# would leave the dead band open on the one host where it was actually measured.
GUARD_DEFAULT_FLOOR_GIB = 200.0


def floor_for_host() -> float | None:
    """The absolute internal floor the storage-floor guard enforces on THIS host.

    Read from the guard's own config file and key so the two instruments cannot
    disagree about whether the host is in trouble; falls back to the guard's own
    default when the host has no config file, because that is what the guard does.
    """
    try:
        v = float(json.loads(FLOOR_CONF.read_text())['internal_floor_gib'])
        return v if v > 0 else None
    except FileNotFoundError:
        return GUARD_DEFAULT_FLOOR_GIB
    except Exception:
        return GUARD_DEFAULT_FLOOR_GIB


def guarded(out: dict, key: str, argv: list, timeout: int, env=None, limit: int = 600):
    """Run one pass; a blown budget degrades THAT pass, never the whole sweep.

    2026-09-19: scratch_reap.py ran past its 90-minute budget on the Studio (29,672
    entries under /private/tmp) and the raw TimeoutExpired propagated out of main(),
    so repack, the fleet archive and the receipt itself never ran. A pass that cannot
    finish in budget is a slow pass, not a reason to lose the sweep.
    """
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        out[key] = f'TIMEOUT after {timeout}s'
        out[key + '_rc'] = 124
        return None
    except Exception as exc:                      # noqa: BLE001 - a pass must never kill the sweep
        out[key] = f'ERROR {type(exc).__name__}: {str(exc)[:200]}'
        out[key + '_rc'] = 125
        return None
    out[key] = (r.stdout.strip().splitlines() or [''])[-1][:limit]
    out[key + '_rc'] = r.returncode
    if r.returncode:
        out[key + '_err'] = r.stderr[-400:]
    return r



def _external_volume_snapshots() -> list[dict]:
    """Read-only observations of explicitly configured storage volumes and the lanes mount.

    The returned objects are telemetry only: this never adjusts sweep cleanup admission.
    Never let an unmounted /Volumes path be counted as free space on the root drive.
    """
    candidates: set[str] = set()
    policy_file = Path.home() / '.config/mastermind/worktree-storage.json'
    notes: list[dict] = []
    try:
        policy = json.loads(policy_file.read_text())
    except FileNotFoundError:
        policy = {}
    except (OSError, ValueError, TypeError) as exc:
        policy = {}
        notes.append({'mount': str(policy_file), 'state': 'POLICY_UNREADABLE',
                      'reason': type(exc).__name__})
    if isinstance(policy, dict):
        items = [policy.get('mount_point')]
        overflow = policy.get('overflow_volumes', [])
        if isinstance(overflow, list):
            items.extend(item.get('mount_point') for item in overflow
                         if isinstance(item, dict))
        for value in items:
            if isinstance(value, str) and value.startswith('/Volumes/'):
                parts = Path(value).parts
                if len(parts) >= 3 and parts[2] not in ('.', '..'):
                    candidates.add('/Volumes/' + parts[2])
    lanes = Path.home() / 'lanes'
    try:
        if lanes.is_symlink():
            resolved = Path(os.path.realpath(lanes))
            parts = resolved.parts
            if len(parts) >= 3 and parts[1] == 'Volumes':
                candidates.add('/Volumes/' + parts[2])
    except OSError as exc:
        notes.append({'mount': str(lanes), 'state': 'LANES_UNRESOLVED',
                      'reason': type(exc).__name__})
    try:
        root_dev = os.stat('/').st_dev
    except OSError:
        root_dev = None
    for mount in sorted(candidates)[:12]:
        path = Path(mount)
        record: dict = {'mount': mount}
        try:
            if not path.is_dir() or not os.path.ismount(mount):
                record['state'] = 'MOUNT_UNAVAILABLE'
            elif root_dev is not None and os.stat(mount).st_dev == root_dev:
                record['state'] = 'MOUNT_ON_ROOT'
            else:
                usage = shutil.disk_usage(mount)
                total = usage.total / GIB
                free = usage.free / GIB
                record.update(state='OK', total_gib=round(total, 1),
                              free_gib=round(free, 1),
                              used_pct=round(100 * (usage.total - usage.free) / usage.total, 1),
                              floor_gib=round(min(total, max(60, 0.14 * total)), 1),
                              warn_gib=round(min(total, max(120, 0.22 * total)), 1))
        except (OSError, ZeroDivisionError) as exc:
            record.update(state='MOUNT_UNAVAILABLE', reason=type(exc).__name__)
        notes.append(record)
    return notes


def finish(out: dict) -> int:
    out['free_gib_after'] = round(shutil.disk_usage('/').free / GIB, 1)
    out['external_volumes'] = _external_volume_snapshots()
    with (STATE / 'sweep-log.jsonl').open('a') as f:
        f.write(json.dumps(out) + '\n')
    alert = STATE / 'ALERT'
    if out['free_gib_after'] < 80:
        alert.write_text(f"{time.ctime()}: internal disk free {out['free_gib_after']} GiB after sweep\n")
    elif alert.exists():
        alert.unlink()
    print(json.dumps(out))
    return 0


LOOPBACK_KEY = Path.home() / '.ssh/id_mm_loopback'


def via_loopback(timeout: int = 2400) -> dict | str | None:
    """Re-enter this same sweep through ssh to 127.0.0.1, which HAS the grants.

    A launchd job holds no Documents/removable-volume grant; a Remote-Login
    session on the very same Mac does. Normally the Studio supplies that session
    (fleet_remote_sweep.py), but the MacBook travels -- when it is away from the
    LAN nothing would run the grant-requiring passes at all. So the host logs
    into itself with a key that exists only for this purpose:
      * generated on the host, never leaves it, no passphrase
      * authorized_keys entry is `from="127.0.0.1,::1"` + `restrict` (no pty, no
        forwarding) + a FORCED command -- presenting this key can run the sweeper
        and nothing else, whatever command the client asks for
      * the forced command sets MM_SWEEP_LOOPBACK=1 (so the child never re-enters
        again -- no recursion) and MM_SWEEP_NOLOCK=1 (the parent already holds the
        single-instance lock; the child must not deadlock against it)
    Returns the child's report, or None when this path is unavailable/not wanted.
    """
    if os.environ.get('MM_SWEEP_LOOPBACK') == '1' or not LOOPBACK_KEY.exists():
        return None
    try:
        p = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                            '-o', 'StrictHostKeyChecking=accept-new', '-i', str(LOOPBACK_KEY),
                            'localhost', 'sweep'],  # the command is ignored: authorized_keys forces it
                           capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f'loopback failed: {exc!r}'[:300]
    last = (p.stdout.strip().splitlines() or [''])[-1]
    try:
        return json.loads(last)
    except ValueError:
        return f'rc={p.returncode} {(p.stderr.strip() or last)[:300]}'


def main() -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    # The loopback child runs INSIDE the parent's lock (see via_loopback), so it must
    # not block on it -- but two children must still never overlap, hence its own file.
    nolock = os.environ.get('MM_SWEEP_NOLOCK') == '1'
    lock_path = (STATE / 'sweep-loopback.lock') if nolock else LOCK
    # single-instance guard (a previous sweep may still be converting). The lock
    # names its owner pid: a lock whose pid is gone is stale (a `launchctl bootout`
    # mid-sweep left one behind on 2026-09-14 and would have idled the agent for 6 h).
    if lock_path.exists() and time.time() - lock_path.stat().st_mtime < 6 * 3600:
        owner = None
        try:
            owner = int(json.loads(lock_path.read_text()).get('pid'))
        except (ValueError, TypeError, AttributeError, OSError):
            owner = None
        alive = False
        if owner:
            try:
                os.kill(owner, 0)
                alive = True
            except ProcessLookupError:
                alive = False
            except PermissionError:
                alive = True
        if alive:
            print(json.dumps({'skipped': 'previous sweep still running', 'pid': owner, 'lock_age_s': int(time.time() - lock_path.stat().st_mtime)}))
            return 0
        print(json.dumps({'stale_lock_removed': True, 'pid': owner}), file=sys.stderr)
    lock_path.write_text(json.dumps({'pid': os.getpid(), 'time': time.time()}))
    try:
        usage = shutil.disk_usage('/')
        free, total = usage.free, usage.total
        receipts = ssd_receipts('temp-worktree-gc')
        # thresholds scale with the disk: the Studio's 1.8 TiB gets ~250/400 GiB, the
        # 460 GB M1/MacBook get ~64/101 GiB (a fixed 250 GiB would pin them in pressure mode)
        if free < max(0.14 * total, 60 * GIB):
            mode, gc_age, sparse_idle = 'pressure', 30, 6.0
        elif free < max(0.22 * total, 120 * GIB):
            mode, gc_age, sparse_idle = 'caution', 90, 24.0
        else:
            mode, gc_age, sparse_idle = 'calm', 180, None
        # The percentage ladder above is disk-RELATIVE; the floor the guard enforces is
        # ABSOLUTE, and on a small disk with a big floor the two disagree -- a dead band
        # where the guard screams BREACH every 30 min and the sweeper it kicks answers
        # 'calm', takes gc_age=180d, and SKIPS repack entirely (`if mode != 'calm'`).
        # Measured on m1 2026-09-24: 460.4 GiB disk, 143.1 GiB free, caution starts at
        # 120.0, floor is 200 -> a 77 GiB band in which every cycle reclaimed exactly
        # 0.0 GiB and re-escalated. Granted sweeps did it too (148.3->148.3, 144.5->144.5),
        # which is why this was misread all session as a Full Disk Access problem.
        # A remediator must never grade a host calm while the alarm it serves is firing.
        floor_gib = floor_for_host()
        if floor_gib and free / GIB < floor_gib and mode == 'calm':
            mode, gc_age, sparse_idle = 'caution', 90, 24.0
        out = {'time': time.time(), 'free_gib_before': round(free / GIB, 1), 'mode': mode}
        if floor_gib:
            out['floor_gib'] = floor_gib
        # pass 0: git/gh transports stuck on the network for hours (ps + kill only, so
        # it works even where launchd python has no file grants yet — m1/mb)
        guarded(out, 'hung', [sys.executable, str(HERE / 'hung_process_reaper.py'), '--apply', '--json'], 300)
        # Gate: every pass below opens files this job may not be allowed to open.
        # A denied context wastes a sweep; a HUNG one (m1 under launchd) burns the
        # whole per-pass timeout budget and the host then never logs a completed
        # run at all. Stop here instead -- the Studio sweeps this host over ssh,
        # where the grants exist (fleet_remote_sweep.py).
        out['grants'] = grants()
        if out['grants'] != 'ok':
            # Last resort before giving up: log into this same machine, where the
            # grants do exist. The child does the real work and writes its own
            # sweep-log line; this one records that it delegated.
            lb = via_loopback()
            if lb is not None:
                out['loopback'] = lb
                return finish(out)
            out['skipped'] = 'grant-requiring passes; the Studio drives this host over ssh'
            return finish(out)
        # pass 0.5: abandoned git fetch temporaries. Runs in EVERY mode, not just under
        # pressure: a dead fetch's tmp_pack_* is pure waste at any free-space level, and
        # it accrues fast -- runner-4 held 86.65 GiB of them in one day (2026-09-19).
        # Cheap (stat + lsof, no repack, no repo lock) and refuses any file a process
        # still holds open, so a live transfer is never interrupted.
        # 1800 s, not 900: this pass now DISCOVERS clones across the host rather than
        # reading a five-path list, and the Studio's /private/tmp alone holds ~30k entries.
        guarded(out, 'stale_packs', [sys.executable, str(HERE / 'stale_pack_reaper.py'),
                                     '--apply', '--json', '--min-age-minutes', '120'], 1800,
                limit=2000)

        # pass 0.6 (Studio only): prune age-gated, ignored Terminal dependency/build
        # caches while keeping the worktrees, branch refs, dirty source and user
        # artifacts intact. Part of THIS sweeper lock; never a second daemon.
        # The helper fails closed on locks, active cwd/processes, unexpected Git
        # ownership, unknown cache contents, source-status drift or journal gaps.
        if os.uname().nodename.split('.')[0] == 'm2studio':
            guarded(out, 'generated_cache_trim',
                    [sys.executable, str(HERE / 'generated_cache_trim.py'),
                     '--apply', '--min-age-days', '10', '--cache-idle-days', '3',
                     '--max-worktrees', '3'], 240, limit=1800)

        # pass 1: the known producer (check_contract_delta.py) with the pressure-adaptive age gate
        guarded(out, 'temp_gc', [sys.executable, str(HERE / 'temp_worktree_gc.py'), '--apply', '--json',
                                 '--min-age-minutes', str(gc_age),
                                 '--name-prefix', 'contract-delta-base-', *receipts], 3600, limit=2000)
        # pass 2: any other detached, clean, unreferenced temp worktree, but only after 3 h idle
        guarded(out, 'temp_gc_generic', [sys.executable, str(HERE / 'temp_worktree_gc.py'), '--apply',
                                         '--json', '--min-age-minutes', '180', *receipts], 3600, limit=2000)
        # pass 3: dead `worktree add` creations (orphans / interrupted checkouts) of the known producer
        guarded(out, 'reap', [sys.executable, str(HERE / 'reap_incomplete_temp_worktrees.py'), '--apply',
                              '--json', '--min-age-minutes', str(max(gc_age, 45)), *receipts], 3600, limit=2000)
        if sparse_idle is not None:
            sr = ssd_receipts('sparse-conversions')
            guarded(out, 'sparse', [sys.executable, str(HERE / 'sparse_idle_worktrees.py'), '--apply',
                                    '--json', '--min-idle-hours', str(sparse_idle),
                                    '--max-convert', '25', *sr], 5400, limit=2000)
        # pass 4b: the clone list pass 4 walks is a FIXED list, so it is blind to any
        # checkout minted outside it. The 2026-09-19 census found FULL trees under
        # ~/lanes, ~/*-ops-wt and /private/tmp on every host — 41 GiB on the MacBook
        # alone, none of it visible to pass 4. This pass walks the host instead, keying
        # on a checkout carrying its own scripts/worktree_sparse.py.
        if sparse_idle is not None:
            # Age is the WEAK gate here; the strong ones are live-cwd and uncommitted
            # work in the heavy dirs, and sparsifying is reversible. Deriving MIN_AGE
            # from sparse_idle meant 6 h even under pressure — and these hosts mint
            # full 7 GiB lane trees faster than that, so a sweep on a MacBook at
            # 19.8 GiB free reclaimed exactly 0 while 52.8 GiB sat eligible but "too
            # young" (2026-09-20). Under pressure, trust the strong gates: ~30 min.
            fsp_age = {'pressure': 0.02, 'caution': 0.25}.get(mode, round(sparse_idle / 24.0, 3))
            fenv = dict(os.environ, MIN_AGE=str(fsp_age), MAX='60')
            guarded(out, 'fleet_sparse', [sys.executable, str(HERE / 'fleet_sparsify.py'),
                                          str(Path.home()), '/private/tmp', '--apply'],
                    5400, fenv)

        # pass 4b2: bound /private/tmp. Nothing ever reaped it, and it is the single
        # biggest generator on the compute hosts — 77 GiB on m1 and 73 GiB on the
        # MacBook on 2026-09-19, ~30 GiB/day of turnover, every tree under two days old.
        # Age-gated deletion alone therefore reclaims almost nothing, which is why the
        # sparse pass above runs first; this pass only takes what has genuinely gone
        # quiet, and writes a THIN bundle of any ref the remote lacks before removing.
        sc_age = {'pressure': '1', 'caution': '2'}.get(mode, '3')
        senv = dict(os.environ, MIN_AGE=sc_age, MIN_MB='200')
        guarded(out, 'scratch_reap', [sys.executable, str(HERE / 'scratch_reap.py'),
                                      '/private/tmp', str(Path.home() / 'lanes/tmp'), '--apply'],
                3600, senv)

        # pass 4c: consolidate ONE bloated object store per sweep. Nothing on this fleet
        # ever ran a repack before 2026-09-19, so fetch packs accrued without bound —
        # 18 packs / 35 GiB on m1's main macro clone, 492 packs in a single ops worktree,
        # 9 packs / 35.6 GiB on the MacBook's. Deliberately bounded to ONE store so a
        # long repack costs at most one sweep cycle, and it never prunes: --keep-unreachable
        # protects objects belonging to a sibling worktree's in-flight work.
        # Only when the host is actually short of room, and capped at one hour: this pass
        # runs INSIDE the sweep lock, so a long repack blocks the next scheduled sweep.
        # Measured 2026-09-19: one Studio store held the lock 26 min, so the original 2 h
        # ceiling could have idled the sweeper for four cycles. A timeout kill is safe --
        # the driver's failure path cleans the partial pack it leaves behind.
        if mode != 'calm':
            renv = dict(os.environ, MAX='1', MIN_PACKS='6', MIN_GIB='4',
                        DEADLINE_S='3300',
                        MIN_FREE_GIB=str(int(max(20, 0.05 * total / GIB))))
            guarded(out, 'repack', [sys.executable, str(HERE / 'fleet_repack.py'),
                                    str(Path.home()), '/private/tmp', '--apply'],
                    3600, renv)

        # pass 4d (Studio only): pull the OTHER hosts' unarchivable trees onto an
        # external volume here. The MacBook has no external drive of its own and no key
        # to push to this host, so the Studio pulls rather than anyone loosening auth
        # (operator 2026-09-19: "macbook u can archive to the external drive on the m2").
        # Gated on the volume actually being mounted, so it is a no-op on m1/mb.
        arch_vol = _pool_archive_mount()
        arch_stamp = STATE / 'fleet-archive.last'
        if arch_vol is not None and arch_vol.is_dir() and (not arch_stamp.exists()
                                  or time.time() - arch_stamp.stat().st_mtime > 21600):
            # The pool archiver only accepts paths beneath Offloaded/ on a
            # UUID-verified SSD. Keep the pre-pool WD layout unchanged.
            archive_dest = (arch_vol / 'fleet-archive' if arch_vol == Path('/Volumes/WD 5TB')
                            else arch_vol / 'Offloaded' / 'fleet-archive')
            pulled = {}
            for peer in ('mb', 'm1'):
                # Report candidate source-less trees without deleting remote data.
                # The legacy archive verifier checks tar readability/entry count,
                # not source-content equality or all remote process references.
                guarded(pulled, peer, [sys.executable, str(HERE / 'pull_remote_archive.py'),
                                       peer, str(archive_dest)], 3600)
            out['fleet_archive'] = pulled
            out['fleet_archive_mode'] = 'REPORT_ONLY_SOURCE_PRESERVED'
            out['fleet_archive_hold'] = 'remote deletion disabled until archive content proof is verified'
            candidates = {}
            for peer in ('mb', 'm1'):
                try:
                    item = json.loads(pulled.get(peer, '{}'))
                    if pulled.get(peer + '_rc') == 0 and item.get('status') == 'REPORT_ONLY_SOURCE_PRESERVED':
                        candidates[peer] = {
                            'eligible_source_less_trees': item['eligible_source_less_trees'],
                            'eligible_gib': item['eligible_gib'],
                            'remote_deletions': item['remote_deletions'],
                            'dest': item['dest'],
                        }
                except (TypeError, ValueError, KeyError):
                    continue
            out['fleet_archive_candidates'] = candidates
            # Only burn the 6-hour cooldown when a pass can actually run.
            # rc 2 indicates a storage identity, floor, or write-permission
            # refusal. Stamping such a refusal would delay recovery; preserve
            # the actual per-host reasons and retry on the next normal sweep.
            if not all(pulled.get(peer + '_rc') == 2 for peer in ('mb', 'm1')):
                arch_stamp.write_text(str(time.time()))
            else:
                # rc=2 covers mount identity, floor and permission refusals,
                # not only TCC. Report the actual preflight result instead of
                # incorrectly saying every refusal is a write-grant problem.
                reasons = []
                for peer in ('mb', 'm1'):
                    try:
                        receipt = json.loads(pulled.get(peer, '{}'))
                        reasons.append(f"{peer}: {str(receipt.get('reason', 'preflight refused'))[:140]}")
                    except (TypeError, ValueError):
                        reasons.append(f'{peer}: preflight refused')
                out['fleet_archive_blocked'] = '; '.join(reasons)[:360]
        elif arch_vol is None:
            out['fleet_archive_blocked'] = 'no verified external pool member'

        # pass 5 (M1 only — the host that owns the U-CHAIN producer): archive day frames
        # older than 7 days to the policy volume, at most once a day. Refuses on its own
        # while the producer is live or when this context cannot write the volume (TCC).
        chain = Path.home() / 'flow-ops-wt/data/chain_snapshots'
        stamp = STATE / 'chain-archive.last'
        if chain.is_dir() and not chain.is_symlink() and (not stamp.exists() or time.time() - stamp.stat().st_mtime > 86400):
            r5 = guarded(out, 'chain_archive', [sys.executable, str(HERE / 'chain_snapshot_archive.py'),
                                               '--apply', '--keep-days', '7'], 3600)
            # stamp on any successful assessment, including "nothing aged out yet":
            # frames cross the cutoff at a date boundary, so one look a day is the
            # design. rc != 0 (RTH window, writer lock held, volume unwritable) does
            # NOT stamp, so a refusal is retried on the next sweep.
            if r5 is not None and r5.returncode == 0:
                stamp.write_text(str(time.time()))
        return finish(out)
    finally:
        try:
            lock_path.unlink()
        except OSError:
            pass


if __name__ == '__main__':
    raise SystemExit(main())
