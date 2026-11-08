#!/usr/bin/env python3
"""Periodic storage sweeper (launchd: com.mastermind.storage-sweeper, every 30 min).

Two bounded, receipted actions, both fail-closed and both already proven by hand
on 2026-09-14 (wave 3). In THIS source candidate both of them are HELD
pre-effect: their --apply modes are never invoked, because their installed
source/preimage is not qualified at this coordinator boundary. The holds are
recorded in the receipt (rc 78, NOT_APPLIED) and the sweep stays degraded:
  1. temp_worktree_gc.py --apply  — removes orphaned detached temp worktrees
     (check_contract_delta.py leftovers etc.). Age gate adapts to disk pressure.
     [HELD]
  2. sparse_idle_worktrees.py --apply — when the internal disk is under pressure,
     converts idle+clean full macro session worktrees to the repo's sparse profile
     (reversible: `python3 scripts/worktree_sparse.py full`). [HELD]
A third, passive step writes a free-space sample so the trend is visible.
Pass 0 (every run, any mode): hung_process_reaper.py kills git/gh transports
stuck on the network for >= 3 h with no CPU (needs no TCC grant). [HELD]
The stale-pack pass is HELD before any helper subprocess: the installed
stale-pack reaper is not source-enrolled here, so this coordinator never
dispatches it at all. The sweep's own INDEPENDENT telemetry survives the
hold -- the free-space sample, the external-volume snapshots and the
recurring sweep-log row all still happen on every sweep. What does not
survive is the helper's own discovery receipt: this source no longer asks
for it. Receipts retained by EARLIER dispatches stay in the append-only
sweep log and are classified retrospectively; they are never rewritten and
never resolved.

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



# The CLOSED set of apply-capable helpers this coordinator may name. Every
# entry names an installed or external helper whose --apply mode is not
# source/preimage-qualified at this coordinator boundary. A key outside this
# tuple is a programming error and is refused, never silently admitted.
UNQUALIFIED_APPLY_KEYS = (
    # B10/B12: already held before this change.
    'fleet_sparse', 'repack', 'generated_cache_trim',
    # The seven remaining apply-capable call sites, held before their effect.
    'hung', 'temp_gc', 'temp_gc_generic', 'reap', 'sparse',
    'scratch_reap', 'chain_archive',
)


def hold_unqualified_apply(out: dict, key: str) -> None:
    """Refuse an unqualified external producer BEFORE its --apply side effect.

    The external fleet_sparsify.py, fleet_repack.py, the installed
    generated_cache_trim.py, and the seven apply-capable passes this
    coordinator still names (hung_process_reaper.py, the two
    temp_worktree_gc.py passes, reap_incomplete_temp_worktrees.py,
    sparse_idle_worktrees.py, scratch_reap.py and chain_snapshot_archive.py)
    are not source/preimage-qualified for apply.

    A post-effect ledger cannot undo an uncertain effect. Until immutable
    producer source, effect safety, receipt semantics, and installed preimage
    are independently qualified, there is no apply admission for these
    helpers.

    A hold is a statement about ENROLLMENT, not a claim of a proven internal
    defect in the held helper. What is missing here is the qualification
    itself: exact installed/source identity, operation-specific complete
    discovery, the original owner/device/inode plus current lease and active
    worktree, the reserve, and interruption reconciliation (plus PID/start
    identity, ownership and carrier protection for the process reaper). One
    census of one helper does not qualify another.
    """
    if key not in UNQUALIFIED_APPLY_KEYS:
        raise ValueError('unexpected producer admission key')
    out[key] = 'PRE_EFFECT_HOLD: producer source and completion schema unqualified'
    out[key + '_rc'] = 78
    out[key + '_effect_state'] = 'NOT_APPLIED'



# B11: the installed stale-pack reaper is NOT source-enrolled in protected
# Mastermind (ops/fleet_storage_cleanup/stale_pack_reaper.py does not exist in
# the protected source) and its --apply path is not owner/inode-bound: it
# stats a candidate, runs `lsof` against the PATH, and then unlinks the PATH
# without re-binding the unlink to the identity it checked, so a writer that
# replaces that pathname in between can make the unlink hit a different live
# file. It also enters the candidate loop before its own incomplete scratch
# find/scan is known, so an incomplete discovery is a late rc2 rather than a
# pre-effect abstention.
#
# The candidate source therefore never asks this helper to apply, and it
# never asks it for an inventory either: a request-side guard does not bind
# the source that answers the request, so the coordinator holds the pass
# BEFORE any helper subprocess and dispatches no child at all. What the
# helper's own discovery receipt would have contributed is therefore not
# collected; the sweep's own INDEPENDENT telemetry -- the free-space
# sample, the external-volume snapshots and the recurring sweep-log row --
# still happens on every sweep. The receipt names the hold explicitly
# (NOT_APPLIED) and the sweep is degraded while the hold is in force. There
# is no bypass: no flag, environment variable or receipt path re-arms the
# apply mode of this helper.
STALE_PACK_HELPER = 'stale_pack_reaper.py'
STALE_PACK_HOLD = 'HELD_UNQUALIFIED_STALE_PACK_HELPER'
STALE_PACK_MIN_AGE_MINUTES = 120
# The exact refusal text the pre-dispatch hold writes for the stale-pack
# pass. The receipt reconciler recognises THIS string and nothing else, so
# every other retained text -- including one injected after the fact -- is
# classified strictly. The comparison is exact: a receipt that merely
# contains or resembles the refusal is not the refusal.
STALE_PACK_HOLD_REFUSAL = ('PRE_EFFECT_HOLD: the stale-pack helper is not '
                            'source-enrolled or preimage-bound at this '
                            'coordinator boundary')
# The stale-pack pass captures at most this many characters of the helper's
# stdout. What a receipt retains is therefore a CAPTURED EXCERPT -- the last
# stdout line, truncated here -- and NOT the helper's full original stdout. A
# retained text that does not parse is lost evidence, not a receipt that
# reports no effect.
STALE_PACK_CAPTURE_LIMIT = 2000
# The stale-pack pass may emit exactly ONE argv shape. A denylist of
# apply-capable spellings cannot express that: the installed helper parses
# its arguments with a default argparse.ArgumentParser(), so allow_abbrev is
# True and every unambiguous PREFIX of a long option is accepted as that
# option. '--a', '--ap', '--app' and '--appl' therefore all arm the helper's
# --apply branch, and not one of them appears in a denylist of whole tokens.
# The allowlist below is the only sound rule, so it is the rule.
_APPLY_CAPABLE_TOKENS = frozenset({
    '--apply', '-a', '--force-apply', '--apply-now',
    '--cleanup', '--prune', '--delete',
})
# Long options whose argparse abbreviation would still arm the destructive
# branch of the unenrolled helper.
_ABBREVIABLE_DESTRUCTIVE_FLAGS = ('--apply', '--mode', '--action')
_DESTRUCTIVE_VALUES = frozenset({'apply', 'cleanup', 'prune', 'delete'})
# The only two options the stale-pack inventory may carry.
_STALE_PACK_ALLOWED_OPTIONS = ('--json', '--min-age-minutes')


def _is_abbreviation_of(name: str, flags: tuple) -> bool:
    """True when `name` is, abbreviates, or extends one of `flags`.

    argparse accepts an unambiguous prefix of a long option, so '--ap' is
    '--apply'. A spelling that extends the flag ('--apply-now') is the flag
    plus a suffix and is equally destructive. Both directions are refused.
    """
    for flag in flags:
        if name == flag or flag.startswith(name) or name.startswith(flag):
            return True
    return False


def _is_apply_capable(token) -> bool:
    """True when an argv token could arm a helper's destructive mode.

    The incumbent spelling is '--apply'. The wider set is deliberate: this
    guard must keep an apply-capable invocation out of the candidate source
    even if a later edit renames the flag.

    The prefix rule is not optional. The installed helper parses with a
    default argparse.ArgumentParser(), so allow_abbrev is True: '--a',
    '--ap', '--app' and '--appl' are each accepted as '--apply'. A denylist
    of whole tokens misses every one of them, so the abbreviation relation
    is part of the rule here.
    """
    if not isinstance(token, str):
        # A token that is not a string cannot be cleared by any spelling rule.
        return True
    text = token.strip().lower()
    if not text:
        return False
    if text in _APPLY_CAPABLE_TOKENS:
        return True
    name, separator, value = text.partition('=')
    if separator:
        # '--mode=apply' and every argparse abbreviation of it.
        return (value.strip() in _DESTRUCTIVE_VALUES
                and _is_abbreviation_of(name, _ABBREVIABLE_DESTRUCTIVE_FLAGS))
    if name.startswith('--'):
        return _is_abbreviation_of(name, _ABBREVIABLE_DESTRUCTIVE_FLAGS)
    if name.startswith('-') and len(name) > 1:
        # A single-dash group: '-app' parses as '-a -p -p', and '-a' arms it.
        return 'a' in name[1:2]
    return False


def _assert_not_apply_capable(argv: list) -> None:
    """Fail closed on any apply-capable token in an argv."""
    apply_capable = [token for token in argv if _is_apply_capable(token)]
    if apply_capable:
        raise ValueError(
            'stale-pack invocation must not be apply-capable: '
            + repr(apply_capable))


def _assert_stale_pack_argv_allowed(argv) -> None:
    """Strict ALLOWLIST over the stale-pack argv. Fail closed on anything else.

    This is a pure function of the argv, so it can be enforced both where the
    argv is built and again at the boundary where it is about to be executed.
    It admits exactly one argv shape:

        [<interpreter>, <helper path>, '--json', '--min-age-minutes', <minutes>]

    Every other shape is refused, so an apply-capable token cannot enter
    through an abbreviation ('--app'), through a second option, through a
    non-integer or non-positive age, or through an option-like helper path.
    """
    if not isinstance(argv, (list, tuple)):
        raise ValueError('stale-pack argv must be a sequence: ' + repr(argv))
    tokens = list(argv)
    if len(tokens) != 5:
        raise ValueError(
            'stale-pack argv must be exactly [interpreter, helper, --json, '
            '--min-age-minutes, minutes]: ' + repr(tokens))
    if tokens[0] != sys.executable:
        raise ValueError('stale-pack argv must run under sys.executable: '
                         + repr(tokens[0]))
    helper_text = tokens[1]
    if not isinstance(helper_text, str) or not helper_text:
        raise ValueError('stale-pack helper path must be a non-empty string: '
                         + repr(helper_text))
    if helper_text.startswith('-'):
        raise ValueError('stale-pack helper path must not be option-like: '
                         + repr(helper_text))
    if any(character in helper_text for character in ('\n', '\r', '\x00')):
        raise ValueError(
            'stale-pack helper path must not contain control characters: '
            + repr(helper_text))
    if tokens[2] != _STALE_PACK_ALLOWED_OPTIONS[0]:
        raise ValueError('stale-pack argv must carry only --json: '
                         + repr(tokens[2]))
    if tokens[3] != _STALE_PACK_ALLOWED_OPTIONS[1]:
        raise ValueError('stale-pack argv must carry only --min-age-minutes: '
                         + repr(tokens[3]))
    minutes_text = tokens[4]
    if (not isinstance(minutes_text, str) or not minutes_text.isascii()
            or not minutes_text.isdigit()):
        raise ValueError(
            'stale-pack --min-age-minutes must be a decimal integer: '
            + repr(minutes_text))
    if int(minutes_text) <= 0 or minutes_text != str(int(minutes_text)):
        raise ValueError(
            'stale-pack --min-age-minutes must be a positive integer: '
            + repr(minutes_text))
    for token in tokens:
        if _is_apply_capable(token):
            raise ValueError(
                'stale-pack invocation must not be apply-capable: '
                + repr(token))
    # Only the two allowed options may look like options at all.
    for index, token in enumerate(tokens):
        if token.startswith('-') and index not in (2, 3):
            raise ValueError(
                'stale-pack argv may carry no other option token: '
                + repr(token))


def stale_pack_argv(helper: Path,
                    min_age_minutes: int = STALE_PACK_MIN_AGE_MINUTES) -> list:
    """The stale-pack pass argv: exactly one allowed never-apply shape.

    This is the single place the stale-pack invocation is formed. The
    allowlist below is what makes the guard fail closed: a later edit that
    re-adds an apply-capable token, an abbreviation of one, or any other
    argv shape raises here instead of shipping an apply-capable invocation
    of an unqualified, unenrolled helper.
    """
    if type(min_age_minutes) is not int:
        raise ValueError('min_age_minutes must be an int, not '
                         + type(min_age_minutes).__name__)
    if min_age_minutes <= 0:
        raise ValueError('min_age_minutes must be positive: '
                         + repr(min_age_minutes))
    if not isinstance(helper, (str, os.PathLike)):
        raise ValueError('helper must be a path-like, not '
                         + type(helper).__name__)
    helper_text = str(helper)
    if helper_text.startswith('-'):
        raise ValueError('helper path must not be option-like: '
                         + repr(helper_text))
    argv = [sys.executable, helper_text, '--json',
            '--min-age-minutes', str(min_age_minutes)]
    _assert_stale_pack_argv_allowed(argv)
    return argv


def stale_pack_discovery_pass(out: dict, key: str = 'stale_packs') -> None:
    """Hold the stale-pack pass BEFORE any helper subprocess runs.

    The installed stale-pack reaper is not source-enrolled in protected
    Mastermind (ops/fleet_storage_cleanup/stale_pack_reaper.py does not exist
    in the protected source), so this coordinator cannot bind the installed
    source or its preimage. A request-side guard does not bind the source that
    answers the request: that is the same gap that keeps the forced-command
    loopback child held. The pass therefore refuses BEFORE any child is
    started, and the helper is never dispatched at all.

    The refusal is the incumbent hold contract: the existing STALE_PACK_HOLD
    marker, rc 78, and NOT_APPLIED for THIS invocation. The verified
    reclaimed-byte count is 0, because nothing an unenrolled helper could
    report can be verified as reclaimed by this coordinator.

    The no-dispatch is scoped to THIS invocation. It reconciles nothing and
    claims nothing about any prior unknown effect, and there is no runtime
    bypass: no flag, environment variable or receipt path re-arms the helper.

    The argv builder and its strict allowlist stay here, and they stay PURE:
    building and checking an argv starts no child and touches no file. They
    are what makes the request shape provably never-apply, so a later edit
    that re-enables a dispatch cannot also smuggle an apply-capable argv past
    the allowlist. The same builder, and the zero-effect inventory predicate,
    are what the PURE retained-receipt classifier reads when it judges one
    receipt retained by an EARLIER dispatch.

    The sweep's INDEPENDENT telemetry is untouched by this hold: the
    free-space sample, the external-volume snapshots and the recurring
    sweep-log row all still happen on every sweep.
    """
    out[key + '_hold'] = STALE_PACK_HOLD
    out[key + '_effect_state'] = 'NOT_APPLIED'
    out[key + '_verified_reclaimed_bytes'] = 0
    out[key] = STALE_PACK_HOLD_REFUSAL
    out[key + '_rc'] = 78
    out[key + '_effect_report'] = {
        'state': 'NOT_APPLIED',
        'kind': 'runtime_pre_dispatch_hold',
        'reason': ('the stale-pack helper is not source-enrolled or '
                   'preimage-bound at this coordinator boundary, so this '
                   'invocation dispatched no child at all'),
        'signals': [],
        'inventory_claim': False,
        'raw_receipt': '',
        'verified_reclaimed_bytes': 0,
        'receipt_scope': 'none: no helper was dispatched',
        'scope': ('this invocation only: this hold reconciles nothing of, and '
                  'claims nothing about, any prior unknown effect'),
        'action': 'no dispatch, no retry, no new effect protocol',
    }
    argv = stale_pack_argv(HERE / STALE_PACK_HELPER, STALE_PACK_MIN_AGE_MINUTES)
    _assert_stale_pack_argv_allowed(argv)



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
    """A COMPLETE stale-pack INVENTORY: complete discovery and zero effect.

    The stale-pack pass runs as a never-apply inventory, so the only receipt
    that can qualify as its inventory is one that says exactly that: complete,
    error-free discovery, `applied` is False, and no removal and no freed
    bytes. A receipt that claims applied=true contradicts the never-apply
    request; it is not an inventory of this pass, and it is reported as an
    unexpected effect instead of as a completed inventory.

    The zero counters must be EXACT ints. 0.0, False and '0' are not proof of
    a zero count, so they do not qualify the inventory.

    A zero-exit reaper may also still fail to enumerate a protected scratch
    subtree, which is why complete, error-free discovery is part of the
    contract rather than the exit code.
    """
    try:
        report = json.loads(raw)
    except (ValueError, TypeError):
        return False
    if not isinstance(report, dict):
        return False
    census = report.get('scratch_discovery')
    return (isinstance(census, dict)
            and census.get('complete') is True
            and isinstance(census.get('errors'), list)
            and not census['errors']
            and report.get('applied') is False
            and type(report.get('removed')) is int
            and report['removed'] == 0
            and type(report.get('freed_bytes')) is int
            and report['freed_bytes'] == 0)


# The receipt fields that carry the helper's own account of what it did.
_STALE_PACK_EFFECT_COUNTERS = ('removed', 'freed_bytes')
# Every field a stale-pack receipt must state for its effect to be readable
# as "no effect". An OMITTED field is missing evidence, not a clearance.
_STALE_PACK_EFFECT_FIELDS = ('applied',) + _STALE_PACK_EFFECT_COUNTERS


def _stale_pack_effect_signals(report) -> list:
    """Adverse effect signals carried by a stale-pack helper receipt.

    An empty list means the receipt reports no effect at all. A receipt that
    reports applied=true, a positive removed/freed_bytes counter, or an effect
    field whose value cannot be read as "no effect" (a bool, a float, a
    string, null, a negative count) is a signal.

    The allowlisted argv proves the REQUEST was never-apply. It never proves
    the installed helper honoured that request, so an effect the request
    cannot explain is reported as an unexpected effect rather than asserted
    as NOT_APPLIED.

    An OMITTED effect field is neither a signal nor a clearance: it is
    missing evidence, and _stale_pack_retained_verdict handles it there.
    """
    if not isinstance(report, dict):
        return []
    signals = []
    if 'applied' in report:
        applied = report['applied']
        if applied is True:
            signals.append('applied_true')
        elif applied is not False:
            # 0, 1, 'true', null: none of these is a readable "not applied".
            signals.append('applied_ambiguous')
    for name in _STALE_PACK_EFFECT_COUNTERS:
        if name not in report:
            continue
        value = report[name]
        if type(value) is int and value == 0:
            continue
        if type(value) is int and value > 0:
            signals.append(name + '_positive')
        else:
            # bool, float, string, negative: not a readable zero.
            signals.append(name + '_ambiguous')
    return signals


def _strict_json_loads(text: str):
    """json.loads with the non-JSON constants refused.

    Python's json module accepts NaN, Infinity and -Infinity even though
    they are not JSON. A receipt carrying one of them is not a receipt this
    coordinator can read, so it is refused here instead of being accepted as
    a number it is not.
    """
    def refuse(constant):
        raise ValueError('non-JSON constant in receipt: ' + str(constant))
    return json.loads(text, parse_constant=refuse)


def _stale_pack_inventory_verdict(out: dict, key: str = 'stale_packs') -> bool:
    """The EXPLICIT inventory verdict for a retained stale-pack receipt.

    True only for an exact-int rc 0 with a present, non-blank stdout that
    satisfies the complete zero-effect inventory contract.

    It is a PRODUCER CLAIM of a complete zero-effect inventory. It is never
    proof that the installed helper is enrolled, source-identified or
    qualified, and it never shortens the hold.
    """
    raw = out.get(key)
    rc = out.get(key + '_rc')
    return bool(type(rc) is int and rc == 0
                and isinstance(raw, str) and raw.strip()
                and _stale_pack_inventory_complete(raw))


def _stale_pack_retained_verdict(raw, rc=None) -> dict:
    """Classify ONE retained stale-pack receipt.

    This is the retrospective / fixture classifier. It is PURE: it reads one
    retained string and writes nothing, so it can be applied to a receipt
    captured by an earlier dispatch, to a row of the existing append-only
    sweep log, or to a test fixture.

    It is deliberately strict, because the evidence it reads was produced by
    an UNQUALIFIED helper and the coordinator may never have seen the full
    stdout:

      * the retained text is a CAPTURED EXCERPT -- the last line of the
        helper's stdout, truncated at the capture limit -- not the helper's
        full original stdout. A text that does not parse is therefore lost
        evidence, not a receipt that reports no effect;
      * a receipt that cannot be parsed, or that is not a JSON object, is
        EFFECT_UNKNOWN. A parsing failure can never prove NOT_APPLIED;
      * a receipt that OMITS an effect field is EFFECT_UNKNOWN. An omitted
        field is missing evidence, not evidence of no effect;
      * a receipt whose rc is not exactly the int 0 -- a timeout, a nonzero
        exit, an interrupted pass, a bool, a float, a string, or a MISSING
        or null rc -- is EFFECT_UNKNOWN. Only an exact int rc of 0 can carry
        a completed producer claim at all;
      * a receipt that reports an effect the never-apply request cannot
        explain is EFFECT_UNKNOWN, and its raw text is retained verbatim;
      * only a receipt that states applied=false with removed and freed_bytes
        as exact int 0 is read as "no effect". That is a zero-effect PRODUCER
        CLAIM, not proof that the installed helper is enrolled, that it
        honoured the request, or that nothing physically happened. It is a
        COMPLETE inventory only when the retained discovery census is also
        complete and error-free; otherwise the inventory claim stays
        incomplete.

    The verified reclaimed-byte count is always 0: nothing an unenrolled
    helper reports can be verified as reclaimed by this coordinator.
    """
    text = raw if isinstance(raw, str) else ''
    verdict = {
        'state': 'EFFECT_UNKNOWN',
        'kind': 'evidence_missing',
        'signals': [],
        'reason': '',
        'inventory_claim': False,
        'verified_reclaimed_bytes': 0,
        'raw_receipt': text,
        'receipt_scope': 'captured_excerpt',
        'capture_limit': STALE_PACK_CAPTURE_LIMIT,
    }
    if not text.strip():
        verdict['reason'] = (
            'no receipt text was captured for this dispatch: the retained '
            'evidence is empty, and empty evidence cannot prove NOT_APPLIED')
        return verdict
    if rc is None:
        # A MISSING or null rc is missing evidence, not a completed dispatch.
        # It used to pass through this gate untouched, so a receipt with no
        # exit code at all could still carry a completed zero-effect claim.
        verdict['kind'] = 'evidence_missing'
        verdict['reason'] = (
            'no exit code was retained for this dispatch: a missing or null '
            'rc is missing evidence, and missing evidence cannot prove that '
            'no effect happened')
        return verdict
    if type(rc) is not int or rc != 0:
        # `type(rc) is int` is exact: a bool, a float or a string is not an
        # exit code, and a nonzero exit is not a completed dispatch.
        verdict['kind'] = 'interrupted'
        verdict['reason'] = (
            'the dispatch did not complete with exit code 0 (rc=%r): the '
            'retained text cannot prove that no effect happened' % (rc,))
        return verdict
    try:
        report = _strict_json_loads(text)
    except (ValueError, TypeError):
        verdict['kind'] = 'unparsable'
        verdict['reason'] = (
            'the retained receipt is not parseable JSON. What is retained is a '
            'captured excerpt -- the last stdout line, truncated at %d '
            'characters -- and not the helper\'s full original stdout, so a '
            'parsing failure is lost evidence and can never prove NOT_APPLIED'
            % STALE_PACK_CAPTURE_LIMIT)
        return verdict
    if not isinstance(report, dict):
        verdict['kind'] = 'unparsable'
        verdict['reason'] = ('the retained receipt is not a JSON object: it '
                             'cannot be read as a receipt of anything')
        return verdict
    missing = [name for name in _STALE_PACK_EFFECT_FIELDS if name not in report]
    if missing:
        verdict['kind'] = 'evidence_missing'
        verdict['signals'] = ['omitted:' + name for name in missing]
        verdict['reason'] = (
            'the retained receipt omits effect field(s) %s: an omitted field '
            'is missing evidence, not evidence of no effect' % ', '.join(missing))
        return verdict
    signals = _stale_pack_effect_signals(report)
    if signals:
        verdict['kind'] = 'contradiction'
        verdict['signals'] = signals
        verdict['reason'] = ('the retained receipt contradicts the never-apply '
                             'request')
        return verdict
    verdict['state'] = 'NOT_APPLIED'
    verdict['kind'] = 'zero_effect_producer_claim'
    # The inventory claim is the COMPLETE-discovery claim, and it is derived
    # from the existing predicate rather than asserted. Exact applied=false
    # with exact int zero counters is a zero-effect PRODUCER CLAIM; it is a
    # complete inventory only when the retained discovery census is complete
    # and error-free. A missing, incomplete or errored census -- or a
    # receipt that never bound a lease, path or file -- stays incomplete.
    complete_inventory = _stale_pack_inventory_complete(text)
    verdict['inventory_claim'] = complete_inventory
    verdict['reason'] = (
        'the retained receipt states applied=false with exact integer zero '
        'effect counters: that is a zero-effect producer claim, not proof '
        'that no effect physically happened or that the installed helper is '
        'enrolled. ' + (
            'The retained discovery census is complete and error-free, so '
            'the producer also claims a complete inventory.'
            if complete_inventory else
            'The retained discovery census is missing, incomplete or errored, '
            'so no complete inventory is claimed.'))
    return verdict


def _stale_pack_coordinator_hold(out: dict, key: str, raw, rc) -> bool:
    """True only for THIS coordinator's own pre-dispatch refusal.

    The refusal TEXT alone proves nothing: it is a plain string, so a
    retained receipt, a copied log row or an injected value can carry it
    verbatim. The provenance of a no-dispatch is the STRUCTURED metadata the
    current stale_pack_discovery_pass emits -- the incumbent hold marker and
    the runtime pre-dispatch report -- together with the incumbent refusal
    exit code 78.

    That report must be PRESENT and must be a dictionary whose kind is
    exactly 'runtime_pre_dispatch_hold'. The current producer emits the
    complete report before any argv work, so there is no legitimate
    intermediate reportless format: a missing, null or non-dictionary report
    is MISSING PROVENANCE, never provenance, and none of it is synthesized.

    A lookalike text with any other rc, or without that structured hold
    metadata, is not a proven coordinator refusal, so it is classified
    strictly like any other retained text and stays EFFECT_UNKNOWN. There is
    no boolean qualification flag and no authority registry: the evidence is
    the coordinator's own recorded hold, and nothing else.
    """
    if raw != STALE_PACK_HOLD_REFUSAL:
        return False
    if type(rc) is not int or rc != 78:
        return False
    if out.get(key + '_hold') != STALE_PACK_HOLD:
        return False
    report = out.get(key + '_effect_report')
    if not isinstance(report, dict):
        return False
    if report.get('kind') != 'runtime_pre_dispatch_hold':
        return False
    return True


def _record_stale_pack_receipt_truth(out: dict, key: str = 'stale_packs') -> None:
    """Reconcile the stale-pack receipt with the never-apply request.

    Records the explicit inventory verdict, the effect verdict, and the
    verified reclaimed-byte count (always zero: nothing an unenrolled helper
    reports can be verified as reclaimed by this coordinator).

    The verdict is STRICT. A receipt that cannot prove "no effect" is
    EFFECT_UNKNOWN: a parsing failure, a truncated capture, an interrupted
    or absent exit code, an omitted effect field and an effect the never-apply
    request cannot explain are all unknown, and none of them is softened into
    NOT_APPLIED. The coordinator's own pre-dispatch refusal is recognised
    only when the structured hold metadata it emits and the incumbent refusal
    rc prove the provenance, and it is then left alone: a known non-dispatch
    is not an unknown effect. The refusal TEXT alone is not that proof.

    The UNKNOWN classification is MONOTONIC within one observation: once
    this receipt has been classified EFFECT_UNKNOWN, a later zero or blank
    value for the same key does not downgrade it. An effect that could not
    be explained is not made explained by a later, weaker reading.

    A contradictory receipt is RETAINED verbatim -- the raw text stays in the
    receipt -- and the sweep records EFFECT_UNKNOWN. There is no retry, no
    compensation and no new effect protocol: an effect that cannot be
    explained is carried forward as unknown, not undone.

    This function never writes the sweep log and never claims that a prior
    unknown effect is resolved.
    """
    raw = out.get(key)
    rc = out.get(key + '_rc')
    out[key + '_inventory_complete'] = _stale_pack_inventory_verdict(out, key)
    existing = out.get(key + '_effect_state')
    if _stale_pack_coordinator_hold(out, key, raw, rc):
        # The coordinator's own pre-dispatch refusal, proven by the structured
        # hold metadata it emits together with the incumbent refusal rc, not
        # by the refusal text alone. This invocation dispatched no child, so
        # there is no effect evidence to reconcile and the runtime verdict
        # stands.
        out.setdefault(key + '_effect_state', 'NOT_APPLIED')
        out.setdefault(key + '_verified_reclaimed_bytes', 0)
        out.setdefault(key + '_effect_report', {
            'state': out[key + '_effect_state'],
            'kind': 'runtime_pre_dispatch_hold',
            'reason': ('the stale-pack pass refused before any helper '
                       'subprocess: this invocation dispatched no child'),
            'signals': [],
            'inventory_claim': False,
            'raw_receipt': '',
            'verified_reclaimed_bytes': 0,
            'receipt_scope': 'none: no helper was dispatched',
            'scope': ('this invocation only: this hold reconciles nothing of, '
                      'and claims nothing about, any prior unknown effect'),
            'action': 'no dispatch, no retry, no new effect protocol',
        })
        return
    verdict = _stale_pack_retained_verdict(raw, rc)
    if existing == 'EFFECT_UNKNOWN' and verdict['state'] == 'NOT_APPLIED':
        verdict = dict(verdict)
        verdict['state'] = 'EFFECT_UNKNOWN'
        verdict['kind'] = 'unknown_monotonic'
        verdict['inventory_claim'] = False
        verdict['reason'] = (
            'the unknown classification is monotonic within this observation: '
            'a later zero or blank value does not downgrade an effect that '
            'could not be explained')
    out[key + '_effect_state'] = verdict['state']
    out[key + '_effect_report'] = verdict
    out[key + '_verified_reclaimed_bytes'] = 0


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
    #
    # The retained stale-pack receipt is reconciled with the never-apply
    # request here, so a receipt that arrives by any path is judged the same
    # way the retrospective classifier judges it: an effect the request cannot
    # explain, or effect evidence that is missing, malformed, truncated,
    # interrupted or omitted, is EFFECT_UNKNOWN and never a completed
    # inventory. The coordinator's own pre-dispatch refusal is recognised
    # exactly and is left alone: a known non-dispatch is not an unknown
    # effect.
    if 'stale_packs' in out or 'stale_packs_rc' in out:
        _record_stale_pack_receipt_truth(out, 'stale_packs')
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
    # An exit-zero receipt that is not a complete zero-effect inventory is
    # not a completed inventory either: applied=true, a positive counter, an
    # inexact zero, or an incomplete census all fail the contract.
    if (out.get('stale_packs_rc') == 0
            and isinstance(out.get('stale_packs'), str)
            and out['stale_packs'].strip()
            and not _stale_pack_inventory_complete(out['stale_packs'])):
        incomplete.append('stale_packs.inventory_unverified')
    # B11: the stale-pack pass is held while the installed reaper is not
    # source-enrolled and its apply path is not owner/inode-bound. A never-apply
    # inventory is not a cleanup: while the hold is in force the sweep reports
    # degraded, never green, and the hold is named in the receipt. The receipt
    # of a discovery run reports applied=false, which is exactly the inventory
    # contract; it is a PRODUCER CLAIM of a complete zero-effect inventory,
    # not proof that the installed helper is enrolled or qualified.
    if out.get('stale_packs_hold') == STALE_PACK_HOLD:
        incomplete.append('stale_packs.held_unqualified_helper')
    # An effect the never-apply request cannot explain is not a completed
    # inventory and not a NOT_APPLIED pass. The contradictory raw receipt is
    # retained in the receipt; the sweep reports the unexpected effect and
    # verifies no reclaimed bytes. Nothing is retried or compensated here.
    if out.get('stale_packs_effect_state') == 'EFFECT_UNKNOWN':
        incomplete.append('stale_packs.unexpected_effect')
    # The loopback delegation is HELD before any forced-child invocation: the
    # parent nonce and the kernel flock bind the REQUEST and the exclusion of a
    # concurrent sweeper, not the installed source the forced child would run.
    # A held delegation is not a delegated sweep, so it degrades the receipt
    # by itself, the way a held apply pass does.
    if out.get('loopback_hold') == LOOPBACK_HOLD:
        incomplete.append('loopback.held_unqualified_child_source')
    # An unreviewed generated-cache helper cannot be retrospectively
    # qualified by a success-shaped stdout or a zero exit code.
    if out.get('generated_cache_trim_hold') == 'HELD_UNQUALIFIED_GENERATED_CACHE_HELPER':
        incomplete.append('generated_cache_trim.held_unqualified_helper')
    # A held apply pass is degraded by the HOLD itself, not only by the
    # refusal code it recorded. A zero exit code or a success-shaped receipt
    # injected later must not rearm a pass that never launched: the hold
    # marker is what the sweep remembers.
    for key in ('hung', 'temp_gc', 'temp_gc_generic', 'reap', 'sparse',
                'scratch_reap', 'chain_archive'):
        if out.get(key + '_effect_state') == 'NOT_APPLIED':
            incomplete.append(key + '.held_unqualified_helper')
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
# The forced-command loopback delegation is HELD: the child the
# authorized_keys forced command starts runs the HOST's installed sweeper,
# and neither the parent nonce nor the kernel flock binds that installed
# source or its preimage. Holding the delegation is a source safety hold. It
# is not a new permission workflow, and there is no qualification flag that
# could stand in for the missing qualification.
LOOPBACK_HOLD = 'HELD_UNBOUND_LOOPBACK_CHILD_SOURCE'


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
        # The temp-GC/reap receipt directory is NOT prepared here. Preparing it
        # is a mkdir plus a write probe on the removable volume, and every
        # apply-capable consumer of that directory is held pre-effect below,
        # so no consumer will launch. A receipt directory is prepared only
        # for a live consumer.
        # thresholds scale with the disk: the Studio's 1.8 TiB gets ~250/400 GiB, the
        # 460 GB M1/MacBook get ~64/101 GiB (a fixed 250 GiB would pin them in pressure mode)
        # The incumbent temp-GC age gate (pressure 30 min, caution 90 min, calm
        # 180 min) is not computed here: both temp-GC passes are held pre-effect,
        # so no age gate reaches a child. Restore it with the pass if that
        # helper is ever qualified.
        if free < max(0.14 * total, 60 * GIB):
            mode, sparse_idle = 'pressure', 6.0
        elif free < max(0.22 * total, 120 * GIB):
            mode, sparse_idle = 'caution', 24.0
        else:
            mode, sparse_idle = 'calm', None
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
            mode, sparse_idle = 'caution', 24.0
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
        # Pre-effect hold: the process reaper's installed source/preimage and its
        # PID/start-identity, ownership and carrier protection are not qualified
        # at this coordinator boundary, so its --apply mode is never invoked.
        # The hold is recorded BEFORE the grant gate, so a denied-grant host
        # still names the hold instead of an applied pass.
        hold_unqualified_apply(out, 'hung')
        # Gate: every pass below opens files this job may not be allowed to open.
        # A denied context wastes a sweep; a HUNG one (m1 under launchd) burns the
        # whole per-pass timeout budget and the host then never logs a completed
        # run at all. Stop here instead -- the Studio sweeps this host over ssh,
        # where the grants exist (fleet_remote_sweep.py).
        out['grants'] = grants()
        if out['grants'] != 'ok':
            # Last resort before giving up, in the incumbent design, is to log
            # into this same machine, where the grants do exist. The child does
            # the real work and writes its own sweep-log line; this one records
            # that it delegated.
            #
            # That delegation is HELD here, BEFORE any ssh or forced-child
            # invocation. The authorized_keys forced command starts the HOST's
            # installed sweeper, and neither the parent nonce nor the kernel
            # flock binds that installed source or its preimage: they bind the
            # REQUEST and the exclusion of a concurrent sweeper, not the code
            # that answers. The same gap keeps the unenrolled stale-pack helper
            # undispatched, and it applies here for the same reason.
            #
            # The transport, auth and lock code in via_loopback() is preserved
            # unchanged; only the admission of the delegation is held. There
            # is no qualification flag: restoring the delegation requires the
            # original owner to bind the installed child source/preimage, and
            # that is not a source-level decision.
            #
            # The helper-exclusion lock is NOT relinquished either: there is no
            # child to hand it to.
            out['loopback_hold'] = LOOPBACK_HOLD
            out['loopback_effect_state'] = 'NOT_APPLIED'
            out['loopback_rc'] = 78
            out['loopback_effect_report'] = {
                'state': 'NOT_APPLIED',
                'kind': 'runtime_pre_dispatch_hold',
                'reason': ('the forced-command child would run the host\'s '
                           'installed sweeper, which the parent nonce and the '
                           'kernel flock do not bind; the delegation is held '
                           'before any ssh or forced-child invocation'),
                'signals': [],
                'verified_reclaimed_bytes': 0,
                'receipt_scope': 'none: no child was dispatched',
                'scope': ('this invocation only: this hold reconciles nothing '
                          'of, and claims nothing about, any prior unknown '
                          'effect'),
                'action': 'no ssh, no forced child, no retry',
            }
            out['skipped'] = ('grant-requiring passes; the Studio drives this '
                              'host over ssh; the loopback delegation is held '
                              'before any forced-child invocation')
            return finish(out)
        # pass 0.5: abandoned git fetch temporaries. Runs in EVERY mode, not just under
        # pressure: a dead fetch's tmp_pack_* is pure waste at any free-space level, and
        # it accrues fast -- runner-4 held 86.65 GiB of them in one day (2026-09-19).
        # Cheap (stat + lsof, no repack, no repo lock). It refuses a file a
        # process still holds open, but that check is NOT a proof that a live
        # transfer is never interrupted: stat+lsof is a PATH check, not an
        # owner/inode binding, so a writer that replaces the pathname in
        # between can still be hit. That is exactly why this helper is held
        # below and is never dispatched by this source.
        # 1800 s, not 900: this pass now DISCOVERS clones across the host rather than
        # reading a five-path list, and the Studio's /private/tmp alone holds ~30k entries.
        # B11: the installed reaper is not source-enrolled and its --apply path is not
        # owner/inode-bound. This source therefore does not dispatch it at all: the
        # pass holds BEFORE any helper subprocess, so the coordinator never runs
        # installed source it cannot bind. The receipt records
        # HELD_UNQUALIFIED_STALE_PACK_HELPER / NOT_APPLIED for this invocation,
        # the verified reclaimed-byte count is 0, and the sweep stays degraded
        # while that hold is in force. The sweep's own independent telemetry --
        # the free-space sample, the external-volume snapshots and this
        # sweep-log row -- is unaffected by the hold.
        try:
            stale_pack_discovery_pass(out, 'stale_packs')
        except ValueError as exc:
            # The argv allowlist refused the invocation. That fails closed for
            # effects, and it must also keep the receipt: a refused pass is a
            # degraded pass (rc 78, the incumbent refusal code), never a lost
            # sweep and never a green heartbeat. A refused invocation is still a
            # non-dispatch, so it is not an unknown effect: the refusal text
            # stays the coordinator's own pre-dispatch refusal.
            out['stale_packs'] = STALE_PACK_HOLD_REFUSAL
            out['stale_packs_rc'] = 78
            out['stale_packs_refusal'] = ('REFUSED ' + type(exc).__name__ + ': '
                                          + str(exc)[:200])

        # pass 0.6 (Studio only): the installed generated_cache_trim.py has not
        # been source-enrolled, preimage-verified, or reviewed for an apply-capable
        # execution. Its receipt can arrive AFTER a deletion, so even a degraded
        # final ledger cannot prove safety. Keep the original sweep lock/timer,
        # but refuse THIS helper before spawning any child or deleting any cache.
        # No new cleaner, inventory command, permission, or scheduler is added.
        if os.uname().nodename.split('.')[0] == 'm2studio':
            out['generated_cache_trim_hold'] = 'HELD_UNQUALIFIED_GENERATED_CACHE_HELPER'
            hold_unqualified_apply(out, 'generated_cache_trim')

        # pass 1: the known producer (check_contract_delta.py) with the pressure-adaptive age gate [HELD]
        # pass 2: any other detached, clean, unreferenced temp worktree, but only after 3 h idle [HELD]
        # pass 3: dead `worktree add` creations (orphans / interrupted checkouts) of the known producer [HELD]
        #
        # Pre-effect hold for all three: the temp-GC and reap producers'
        # source/preimage identity and their operation-specific complete
        # discovery, owner/device/inode, current lease, active worktree,
        # reserve and interruption-reconciliation safeguards are not qualified
        # at this coordinator boundary. Their --apply modes are never invoked,
        # so the shared --receipts directory is not prepared either: no
        # consumer launches, so no removable volume is touched.
        hold_unqualified_apply(out, 'temp_gc')
        hold_unqualified_apply(out, 'temp_gc_generic')
        hold_unqualified_apply(out, 'reap')
        if sparse_idle is not None:
            # Pre-effect hold: the installed sparse producer is not
            # source/preimage-qualified for apply at this coordinator
            # boundary. Its --apply mode is never launched, and its
            # completion ledger is never accepted as a substitute for that
            # missing qualification. What is missing HERE is the
            # qualification itself, not a proven internal defect of the
            # helper. Its --receipts directory is not prepared either: the
            # only consumer is held.
            hold_unqualified_apply(out, 'sparse')
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
        # sparse pass above exists; this pass only takes what has genuinely gone
        # quiet, and writes a THIN bundle of any ref the remote lacks before removing.
        # Pre-effect hold: the scratch reaper's installed source/preimage and
        # its operation-specific safeguards are not qualified at this
        # coordinator boundary. Its --apply mode is never invoked, so its
        # incumbent age/environment gate (MIN_AGE 1/2/3 days by mode, MIN_MB
        # 200) never reaches a child.
        hold_unqualified_apply(out, 'scratch_reap')

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
            # Pre-effect hold: the chain snapshot archiver's installed
            # source/preimage and its operation-specific safeguards are not
            # qualified at this coordinator boundary, so its --apply mode is
            # never invoked.
            #
            # stamp on any successful assessment, including "nothing aged out yet":
            # frames cross the cutoff at a date boundary, so one look a day is the
            # design. rc != 0 (RTH window, writer lock held, volume unwritable) does
            # NOT stamp, so a refusal is retried on the next sweep. A HOLD is an
            # abstention, not an assessment: it does not stamp either, so the
            # condition is re-evaluated on the next sweep.
            hold_unqualified_apply(out, 'chain_archive')
            if (out.get('chain_archive_effect_state') != 'NOT_APPLIED'
                    and type(out.get('chain_archive_rc')) is int
                    and out['chain_archive_rc'] == 0
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
