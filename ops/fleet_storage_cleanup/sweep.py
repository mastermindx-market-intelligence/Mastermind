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

import errno
import fcntl
import json
import os
import re
import secrets
import shutil
import stat
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
        configured = json.loads(FLOOR_CONF.read_text())['internal_floor_gib']
        if isinstance(configured, bool):
            return GUARD_DEFAULT_FLOOR_GIB
        v = float(configured)
        return v if 0.0 < v < float('inf') else GUARD_DEFAULT_FLOOR_GIB
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



def hold_unqualified_apply(out: dict, key: str) -> None:
    """Refuse an unqualified external producer BEFORE its --apply side effect.

    The existing fleet_sparsify.py and fleet_repack.py are not source-enrolled
    with the complete B10 receipt contract. A post-effect ledger cannot undo
    an uncertain effect. Until immutable producer source, complete receipt
    semantics and installed preimage are independently qualified, there is
    deliberately no executable admission path for either helper.
    """
    if key not in ('fleet_sparse', 'repack'):
        raise ValueError('unexpected producer admission key')
    out[key] = 'PRE_EFFECT_HOLD: producer source and completion schema unqualified'
    out[key + '_rc'] = 78
    out[key + '_effect_state'] = 'NOT_APPLIED'



def sparse_scan_allowed(free_gib: float, floor_gib: float | None) -> bool:
    """Preserve incumbent above-floor headroom before costly sparse censuses.

    This does NOT weaken the sparse-conversion gate near or below the
    absolute storage floor. Only skips scans when reserve >= 60 GiB.
    """
    return not (floor_gib and free_gib >= floor_gib + 60.0)



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


def _qualified_archive_peer(raw: str | None, peer: str,
                            expected_dest: str | None) -> dict | None:
    """One fail-closed receipt contract for archive inventory, cooldown and finish."""
    try:
        report = json.loads(raw) if isinstance(raw, str) else None
    except (ValueError, TypeError):
        return None
    if not (isinstance(report, dict)
            and report.get('status') == 'REPORT_ONLY_SOURCE_PRESERVED'
            and type(report.get('eligible_source_less_trees')) is int
            and report['eligible_source_less_trees'] >= 0
            and type(report.get('eligible_gib')) in (int, float)
            and 0 <= report['eligible_gib'] < float('inf')
            and type(report.get('remote_deletions')) is int
            and report['remote_deletions'] == 0
            and isinstance(expected_dest, str)
            and expected_dest.startswith('/')
            and '..' not in Path(expected_dest).parts
            and report.get('host') == peer
            and report.get('dest') == expected_dest):
        return None
    return report


def _archive_cooldown_ready(pulled: dict, dest: str) -> bool:
    """Only two independently verified successful peer inventories earn a cooldown."""
    return all(
        type(pulled.get(peer + '_rc')) is int
        and pulled[peer + '_rc'] == 0
        and _qualified_archive_peer(pulled.get(peer), peer, dest) is not None
        for peer in ('mb', 'm1')
    )


def _stale_pack_inventory_complete(raw: str) -> bool:
    """A zero-exit reaper may still fail to enumerate a protected scratch subtree."""
    try:
        report = json.loads(raw)
    except (ValueError, TypeError):
        return False
    census = report.get('scratch_discovery') if isinstance(report, dict) else None
    return (isinstance(census, dict)
            and census.get('complete') is True
            and isinstance(census.get('errors'), list)
            and not census['errors']
            and report.get('applied') is True
            and type(report.get('removed')) is int
            and report['removed'] >= 0
            and type(report.get('freed_bytes')) is int
            and report['freed_bytes'] >= 0)


def _finite_nonnegative(value) -> bool:
    return type(value) in (int, float) and 0 <= value < float('inf')


def _helper_receipt_qualified(key: str, raw: str) -> bool:
    """Validate helper completion, not just an exit-zero or text-shaped success.

    Existing fleet_sparse/repack producers omit complete-attempt evidence.
    Their zero-exit legacy receipts must remain HELD until the incumbent
    producer contract is independently source-qualified and installed.
    """
    try:
        report = json.loads(raw) if isinstance(raw, str) else None
    except (ValueError, TypeError):
        return False
    if not isinstance(report, dict):
        return False

    def count(name):
        return type(report.get(name)) is int and report[name] >= 0

    if key == 'generated_cache_trim':
        selected, verified, held = (report.get(name) for name in ('selected', 'verified', 'held'))
        return (report.get('mode') == 'APPLY'
                and isinstance(selected, list) and isinstance(verified, list)
                and isinstance(held, dict)
                and count('scanned') and count('held_count') and count('recovered_bytes')
                and report['held_count'] >= len(held)
                and 'refused' not in report and 'bounded' not in report
                and all(isinstance(item, dict)
                        and isinstance(item.get('name'), str) and item['name']
                        and isinstance(item.get('head'), str) and item['head']
                        and isinstance(item.get('caches'), list)
                        for item in selected)
                and all(isinstance(name, str) and name for name in verified)
                and set(verified).issubset({item['name'] for item in selected})
                and all(item['name'] in verified or item['name'] in held
                        for item in selected))
    if key == 'fleet_sparse':
        return (count('sparsified') and count('skipped')
                and count('conversion_failures') and report['conversion_failures'] == 0
                and _finite_nonnegative(report.get('freed_gib'))
                and report.get('discovery_complete') is True
                and report.get('scan_failures') == []
                and report.get('applied') is True)
    if key == 'repack':
        scope = report.get('discovery_scope')
        return (count('repacked') and count('attempts_failed')
                and report['attempts_failed'] == 0
                and _finite_nonnegative(report.get('total_freed_gib'))
                and _finite_nonnegative(report.get('free_after'))
                and report.get('discovery_complete') is True
                and report.get('scan_failures') == []
                and isinstance(scope, dict)
                and all(type(scope.get(name)) is int and scope[name] >= 0
                        for name in ('durable_clones_checked', 'object_stores_identified')))
    if key == 'chain_archive':
        dst, manifest = report.get('dst'), report.get('manifest')
        return (report.get('applied') is True and count('candidates')
                and count('archived') and report['archived'] == report['candidates']
                and count('errors') and report['errors'] == 0
                and count('bytes') and _finite_nonnegative(report.get('archived_gib'))
                and _finite_nonnegative(report.get('time'))
                and isinstance(report.get('src'), str)
                and report['src'].startswith('/')
                and isinstance(dst, str) and dst.startswith('/')
                and '..' not in Path(dst).parts
                and isinstance(manifest, str)
                and manifest.startswith(dst.rstrip('/') + '/_manifests/archive-')
                and manifest.endswith('.json'))
    return False


def finish(out: dict) -> int:
    # A completed top-level pass is not a clean sweep when a bounded helper
    # refused or only partially scanned. Preserve its original return code
    # and make the same launchd heartbeat report an explicit degraded result.
    # StartInterval continues recurring even when this invocation exits 1.
    # Every recorded helper return code must be an actual integer. String,
    # boolean, float and missing rc values cannot establish a clean pass.
    # The real subprocess guard always emits int; this prevents corrupted or
    # future alternate producer receipts from restoring false-green behavior.
    incomplete = sorted(key[:-3] for key, rc in out.items()
                        if key.endswith('_rc') and (type(rc) is not int or rc != 0))
    if out.get('grants') == 'ok':
        # A grant-qualified full sweep always calls these six helpers. Their
        # complete absence is not evidence of success, even on a calm host.
        mandatory = ('hung', 'stale_packs', 'temp_gc',
                     'temp_gc_generic', 'reap', 'scratch_reap')
        for key in mandatory:
            if key + '_rc' not in out:
                incomplete.append(f'{key}.rc_missing')
    # A helper's exit 0 without its expected --json receipt is not proof of a
    # completed inventory. Never translate absent stdout into a clean sweep.
    receipt_required = {'hung', 'stale_packs', 'temp_gc',
                        'temp_gc_generic', 'reap', 'sparse'}
    for key in sorted(receipt_required):
        if out.get(key + '_rc') == 0 and (
                not isinstance(out.get(key), str) or not out[key].strip()):
            incomplete.append(f'{key}.receipt_unverified')
    # Optional cleanup passes also require exact, interpretable completion ledgers.
    # Legacy success-shaped stdout or missing discovery proof is NOT green.
    for key in ('generated_cache_trim', 'fleet_sparse', 'repack', 'chain_archive'):
        if out.get(key + '_rc') == 0 and not _helper_receipt_qualified(key, out.get(key)):
            incomplete.append(f'{key}.receipt_unverified')
    # Incumbent stale_pack_reaper.py may exit zero after a failed find(1) in
    # /private/tmp. That JSON's scratch_discovery.complete=false is binding.
    if (out.get('stale_packs_rc') == 0
            and isinstance(out.get('stale_packs'), str)
            and out['stale_packs'].strip()
            and not _stale_pack_inventory_complete(out['stale_packs'])):
        incomplete.append('stale_packs.inventory_unverified')
    # The incumbent scratch_reap.py prints a final JSON ledger even when it
    # has zero eligible trees. Exit 0 with empty/truncated output, an unrelated
    # diagnostic line, or a partial scan cannot prove a completed sweep.
    if out.get('scratch_reap_rc') == 0:
        raw = out.get('scratch_reap')
        try:
            scratch = json.loads(raw) if isinstance(raw, str) else None
        except (TypeError, ValueError):
            scratch = None
        counters = ('removed', 'bundled', 'skipped', 'swept_overcap_bundles')
        valid = (
            isinstance(scratch, dict)
            and type(scratch.get('partial')) is bool
            and all(type(scratch.get(key)) is int and scratch[key] >= 0
                    for key in counters)
            and type(scratch.get('freed_gib')) in (int, float)
            and 0 <= scratch['freed_gib'] < float('inf')
            and type(scratch.get('elapsed_s')) in (int, float)
            and 0 <= scratch['elapsed_s'] < float('inf')
            and type(scratch.get('deadline_s')) in (int, float)
            and 0 < scratch['deadline_s'] < float('inf')
        )
        if not valid:
            incomplete.append('scratch_reap.receipt_unverified')
        elif scratch['partial']:
            incomplete.append('scratch_reap.partial')
    # The archive pass invokes two remote substeps under a nested receipt.
    # A failed or refused peer must not disappear beneath a green top-level
    # heartbeat merely because its *_rc is not a direct member of out.
    # Each archive peer's success exit must carry an interpretable receipt.
    # This is report-only, never authority to remove remote worktrees.
    if 'fleet_archive' in out:
        archive = out['fleet_archive']
        if not isinstance(archive, dict):
            incomplete.append('fleet_archive.receipt_unverified')
        else:
            expected_dest = out.get('fleet_archive_expected_dest')
            for peer in ('mb', 'm1'):
                rc = archive.get(peer + '_rc')
                if type(rc) is not int:
                    incomplete.append(f'fleet_archive.{peer}_receipt_unverified')
                elif rc != 0:
                    incomplete.append(f'fleet_archive.{peer}')
                elif _qualified_archive_peer(archive.get(peer), peer, expected_dest) is None:
                    incomplete.append(f'fleet_archive.{peer}_receipt_unverified')
    # The launchd parent can lack filesystem grants and delegate to its
    # existing forced-command loopback child. A string/partial/old child
    # response, or no child at all, is NOT a completed sweep: do not print a
    # green top-level receipt merely because hung-process triage succeeded.
    if 'grants' in out and out['grants'] != 'ok':
        child = out.get('loopback')
        # The localhost forced command must attest to a complete *current*
        # sweep, not merely supply a convenient success-shaped summary.
        mandatory = ('hung', 'stale_packs', 'temp_gc',
                     'temp_gc_generic', 'reap', 'scratch_reap')
        child_qualified = (
            isinstance(child, dict)
            and child.get('grants') == 'ok'
            and child.get('degraded') is False
            and type(child.get('free_gib_after')) in (int, float)
            and 0 <= child['free_gib_after'] < float('inf')
            and child.get('mode') in ('calm', 'caution', 'pressure')
            and child.get('incomplete_substeps') == []
            and not child.get('skipped')
            and type(out.get('time')) in (int, float)
            and type(child.get('time')) in (int, float)
            and out['time'] <= child['time'] <= time.time() + 5
            and all(type(child.get(key + '_rc')) is int
                    and child[key + '_rc'] == 0 for key in mandatory)
        )
        if not child_qualified:
            incomplete.append('grant_requiring_passes')
    incomplete.sort()
    out['incomplete_substeps'] = incomplete
    out['degraded'] = bool(incomplete)
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
    return 1 if incomplete else 0


LOOPBACK_KEY = Path.home() / '.ssh/id_mm_loopback'


def via_loopback(timeout: int = 2400, parent_nonce: str | None = None) -> dict | str | None:
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
    if not isinstance(parent_nonce, str) or not re.fullmatch(r'[0-9a-f]{64}', parent_nonce):
        return 'loopback refused: missing canonical parent nonce'
    try:
        p = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                            '-o', 'StrictHostKeyChecking=accept-new', '-i', str(LOOPBACK_KEY),
                            'localhost', f'sweep {parent_nonce}'],  # authorized_keys forces it
                           capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f'loopback failed: {exc!r}'[:300]
    # The forced-command transport's process exit is independently binding.
    # A success-shaped final JSON line cannot absolve a nonzero ssh/child exit.
    if p.returncode != 0:
        return f'loopback transport rc={p.returncode}'
    last = (p.stdout.strip().splitlines() or [''])[-1]
    try:
        return json.loads(last)
    except ValueError:
        return f'rc={p.returncode} {(p.stderr.strip() or last)[:300]}'


def _claim_sweep_lock(path: Path) -> int | None:
    """Atomically claim the existing lock inode; None means a live contender.

    Kernel flock, not PID liveness, is the unique sweeper authority. The marker
    stays on disk after process exit: unlinking it could create a second inode
    while an earlier owner still holds its kernel lock.
    """
    nofollow = getattr(os, 'O_NOFOLLOW', None)
    if nofollow is None:
        raise OSError(errno.ENOTSUP, 'no-follow lock unavailable')
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | nofollow, 0o600)
    claimed = False
    try:
        def qualified() -> bool:
            held = os.fstat(fd)
            named = os.lstat(path)
            return (stat.S_ISREG(held.st_mode)
                    and held.st_uid == os.getuid()
                    and held.st_nlink == 1
                    and not (held.st_mode & 0o022)
                    and (held.st_dev, held.st_ino) == (named.st_dev, named.st_ino))

        if not qualified():
            raise OSError(errno.EPERM, 'unqualified incumbent lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
        if not qualified():
            raise OSError(errno.EPERM, 'lock path changed')
        # An installed legacy sweeper writes a bare PID without taking flock.
        # Acquiring this inode cannot exclude that still-active old process.
        # Preserve the old marker: only the publisher can qualify a quiescent
        # old epoch before permitting a new persistent-flock epoch.
        prior_size = os.fstat(fd).st_size
        if prior_size > 512:
            raise OSError(errno.EPERM, 'unqualified legacy lock marker')
        if prior_size:
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                prior = json.loads(os.read(fd, prior_size))
            except (ValueError, UnicodeDecodeError) as exc:
                raise OSError(errno.EPERM, 'unqualified legacy lock marker') from exc
            if (type(prior) is not dict or type(prior.get('pid')) is not int
                    or prior['pid'] <= 0 or type(prior.get('time')) not in (int, float)
                    or not 0 < prior['time'] < float('inf')
                    or type(prior.get('nonce')) is not str
                    or re.fullmatch(r'[0-9a-f]{64}', prior['nonce']) is None):
                raise OSError(errno.EPERM, 'unqualified legacy lock marker')
        marker = json.dumps({'pid': os.getpid(), 'time': time.time(),
                             'nonce': secrets.token_hex(32)}).encode('ascii')
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        if os.write(fd, marker) != len(marker):
            raise OSError(errno.EIO, 'incomplete lock marker')
        os.fsync(fd)
        if not qualified():
            raise OSError(errno.EPERM, 'lock path changed after mark')
        claimed = True
        return fd
    finally:
        if not claimed:
            os.close(fd)


def _read_lock_nonce(fd: int) -> str:
    """Read the one-time source-owned marker from our claimed canonical flock."""
    os.lseek(fd, 0, os.SEEK_SET)
    marker = json.loads(os.read(fd, 1024))
    nonce = marker.get('nonce') if isinstance(marker, dict) else None
    if not isinstance(nonce, str) or not re.fullmatch(r'[0-9a-f]{64}', nonce):
        raise OSError(errno.EINVAL, 'canonical lock nonce unavailable')
    return nonce


def _bound_loopback_parent() -> bool:
    """A forced-SSH child needs the live original parent lock and nonce.

    The secondary lock serializes actual helpers: the parent owns it during
    normal passes and releases it solely for an attested forced-command child.
    If the parent dies, the child's held secondary lock fences new parents.
    """
    if os.environ.get('MM_SWEEP_LOOPBACK') != '1':
        return False
    match = re.fullmatch(r'sweep ([0-9a-f]{64})',
                         os.environ.get('SSH_ORIGINAL_COMMAND', ''))
    nofollow = getattr(os, 'O_NOFOLLOW', None)
    if match is None or nofollow is None:
        return False
    try:
        fd = os.open(LOCK, os.O_RDWR | os.O_CLOEXEC | nofollow)
    except OSError:
        return False
    try:
        held, named = os.fstat(fd), os.lstat(LOCK)
        if (not stat.S_ISREG(held.st_mode) or held.st_uid != os.getuid()
                or held.st_nlink != 1 or (held.st_mode & 0o022)
                or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)):
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass  # another live process MUST hold the canonical lock
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        os.lseek(fd, 0, os.SEEK_SET)
        marker = json.loads(os.read(fd, 1024))
        if not isinstance(marker, dict) or marker.get('nonce') != match.group(1):
            return False
        pid, started = marker.get('pid'), marker.get('time')
        if (type(pid) is not int or pid <= 0 or pid == os.getpid()
                or type(started) not in (int, float)
                or not (0 <= time.time() - started <= 600)):
            return False
        os.kill(pid, 0)  # supplemental to flock; PID alone never authorizes
        return True
    except (OSError, ValueError, TypeError):
        return False
    finally:
        os.close(fd)


def main() -> int:
    # Refuse an unbound NOLOCK child BEFORE any executable cleanup helper.
    nolock = os.environ.get('MM_SWEEP_NOLOCK') == '1'
    if nolock and not _bound_loopback_parent():
        print(json.dumps({'degraded': True, 'lock': 'UNBOUND_CHILD'}))
        return 78
    STATE.mkdir(parents=True, exist_ok=True)
    # Normal sweeps own BOTH inodes; the authenticated child owns the shared
    # helper exclusion inode while its parent retains the canonical inode.
    lock_path = (STATE / 'sweep-loopback.lock') if nolock else LOCK
    try:
        lock_fd = _claim_sweep_lock(lock_path)
    except OSError:
        print(json.dumps({'degraded': True, 'lock': 'UNVERIFIED'}))
        return 78
    if lock_fd is None:
        print(json.dumps({'degraded': True, 'lock': 'BUSY'}))
        return 75
    exclusion_fd = None
    try:
        if nolock:
            if not _bound_loopback_parent():
                print(json.dumps({'degraded': True, 'lock': 'UNBOUND_CHILD'}))
                return 78
        else:
            try:
                exclusion_fd = _claim_sweep_lock(STATE / 'sweep-loopback.lock')
            except OSError:
                print(json.dumps({'degraded': True, 'lock': 'UNVERIFIED'}))
                return 78
            if exclusion_fd is None:
                print(json.dumps({'degraded': True, 'lock': 'BUSY'}))
                return 75
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
        # Installed M1/M2 source defers the 5,400 s full-worktree census when
        # 60 GiB headroom remains above the immutable storage floor. Preserve
        # this incumbent behavior while adding source-level receipt hardening.
        if sparse_idle is not None and not sparse_scan_allowed(free / GIB, floor_gib):
            sparse_idle = None
            sparse_deferred = True
        else:
            sparse_deferred = False
        out = {'time': time.time(), 'free_gib_before': round(free / GIB, 1), 'mode': mode}
        if sparse_deferred:
            out['sparse_deferred'] = {'reason': 'above_floor_plus_60_gib',
                                      'target_gib': floor_gib + 60.0,
                                      'free_gib': round(free / GIB, 3)}
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
            # Relinquish only the helper-exclusion lock to the forced child.
            # Retain the canonical parent lock until the delegated pass returns.
            if exclusion_fd is not None:
                os.close(exclusion_fd)
                exclusion_fd = None
            lb = via_loopback(parent_nonce=_read_lock_nonce(lock_fd)) if not nolock else None
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
            # B10: the installed sparse producer lacks complete discovery and
            # conversion-attempt receipts. Never launch its --apply mode and
            # only THEN discover that its completion ledger was unqualified.
            hold_unqualified_apply(out, 'fleet_sparse')

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
            # B10: the incumbent repack producer has no reviewed complete
            # attempts_failed contract. Preserve all existing Git/worktree
            # ownership and objects rather than executing an unqualified apply.
            hold_unqualified_apply(out, 'repack')

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
            out['fleet_archive_expected_dest'] = str(archive_dest)
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
                item = _qualified_archive_peer(pulled.get(peer), peer, str(archive_dest))
                if pulled.get(peer + '_rc') == 0 and item is not None:
                    candidates[peer] = {
                        'eligible_source_less_trees': item['eligible_source_less_trees'],
                        'eligible_gib': item['eligible_gib'],
                        'remote_deletions': item['remote_deletions'],
                        'dest': item['dest'],
                    }
            out['fleet_archive_candidates'] = candidates
            # A timeout, nonzero exit, invalid receipt or partial peer does not
            # consume six hours of recovery eligibility. Never stamp one good peer.
            if _archive_cooldown_ready(pulled, str(archive_dest)):
                arch_stamp.write_text(str(time.time()))
            else:
                reasons = []
                for peer in ('mb', 'm1'):
                    if peer in candidates:
                        continue
                    try:
                        receipt = json.loads(pulled.get(peer, '{}'))
                        reason = (str(receipt.get('reason', 'unverified receipt'))[:140]
                                  if isinstance(receipt, dict) else 'unverified receipt')
                    except (TypeError, ValueError):
                        reason = 'unverified receipt'
                    reasons.append(f"{peer}: rc={pulled.get(peer + '_rc', 'missing')} {reason}")
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
            if (r5 is not None and r5.returncode == 0
                    and _helper_receipt_qualified('chain_archive', out.get('chain_archive'))):
                stamp.write_text(str(time.time()))
        return finish(out)
    finally:
        # Crash-release both kernel locks; never unlink a stable inode.
        if exclusion_fd is not None:
            os.close(exclusion_fd)
        os.close(lock_fd)


if __name__ == '__main__':
    raise SystemExit(main())
