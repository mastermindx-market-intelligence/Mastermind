#!/usr/bin/env python3
"""Drive the storage sweeper on the other Macs FROM the Studio, over ssh.

    fleet_remote_sweep.py [--hosts m1,mb] [--no-sync] [--timeout 1800] [--json]

Why this exists (2026-09-14): a launchd agent on `m1` / `mb` runs as its own TCC
subject (/usr/bin/python3 -> Command Line Tools Python.app), which holds NO
Documents grant and no removable-volume access there, so the local sweeper's GC
and chain-archive passes fail closed with EPERM. Granting Full Disk Access to
that Python.app needs a human in System Settings on each machine.

An ssh session does not: macOS attributes a remote-login session to the Remote
Login service, and on both hosts that service already has full disk access
(probed 2026-09-14 -- TCC.db readable, ~/Documents listable, /Volumes/STORAGE
and the SMB /Volumes/Mastermind writable from ssh). So the Studio -- which is
always on -- runs the sweep over ssh and the remote work inherits the grants
that the remote launchd job lacks. No FDA prompt, no per-host clicking.

Each host's own launchd sweeper stays installed as a fallback for when the
Studio is off: it still does the passes that need no grant (hung git/gh
transports). The sweeper's pid-aware lock keeps the two from overlapping; if a
host reports `skipped` because its local agent held the lock, this driver waits
once and retries.

Also rsyncs the toolkit to each host first (--no-sync to skip), so a fix made on
the Studio reaches the fleet on the next tick instead of drifting.
Ledger: ~/.local/state/mastermind/storage-cleanup/fleet-remote-sweep.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = Path.home() / '.local/state/mastermind/storage-cleanup'
LOCK = STATE / 'fleet-remote-sweep.lock'
SEEN = STATE / 'fleet-host-state.json'   # host -> last successful sweep (epoch)
STALE_HOURS = 72.0                       # a host unseen this long is worth surfacing
REMOTE_DIR = '$HOME/.local/lib/mastermind/storage-cleanup'
# keepalives so a dead TCP path ends in ~1 min instead of parking a transport for
# days -- the exact failure this toolkit reaps elsewhere (hung_process_reaper.py)
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=20',
       '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=4']


def run(cmd: list[str], timeout: int) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, '', f'timeout after {timeout}s'


def reachable(host: str) -> bool:
    """Cheap liveness check before spending the per-host budget.

    The MacBook is only on the LAN when the user is home -- it travels. An absent
    host is a normal state, not a failure: probe in seconds rather than letting a
    1800 s sweep timeout expire, and never fail the run because of it.
    """
    rc, _, _ = run(SSH + ['-o', 'ConnectTimeout=10', host, 'true'], 25)
    return rc == 0


def sync(host: str, timeout: int) -> str:
    rc, _, err = run(['rsync', '-a', '--exclude', '__pycache__', '-e', ' '.join(SSH),
                      str(HERE) + '/', f'{host}:.local/lib/mastermind/storage-cleanup/'], timeout)
    return 'ok' if rc == 0 else f'rc={rc} {err.strip()[:200]}'


def sweep(host: str, timeout: int, attempts: int = 3, retry_wait: int = 150) -> dict:
    """Run the remote sweeper; retry while the host's OWN agent is holding the lock.

    Observed 2026-09-14: m1's local sweep ran 16 min (sparse conversions), so one
    90 s retry wasn't enough. The hosts' agents are hourly and this driver is
    half-hourly, so a host that stays busy is simply picked up on the next tick.
    """
    out: dict = {'host': host}
    for attempt in range(1, attempts + 1):
        rc, so, se = run(SSH + [host, f'/usr/bin/python3 {REMOTE_DIR}/sweep.py'], timeout)
        last = (so.strip().splitlines() or [''])[-1]
        # keep the sweeper's report as an OBJECT: a sweep line runs past 2 KB, and
        # truncating it to a string made the whole ledger entry unparseable
        try:
            parsed = json.loads(last)
        except ValueError:
            parsed = None
        out.update(rc=rc, attempt=attempt, sweep=parsed if parsed is not None else last[:1200])
        if rc != 0:
            out['stderr'] = se.strip()[-400:]
        if rc == 0 and isinstance(parsed, dict) and 'skipped' in parsed and 'grants' not in parsed:
            out['deferred'] = True  # the host's own agent held the lock, not a real result
            if attempt < attempts:
                time.sleep(retry_wait)
                continue
        break
    if isinstance(out.get('sweep'), dict):
        out['free_gib'] = out['sweep'].get('free_gib_after')
    return out



# Fixed pre-execution source fence. The old/missing remote module is never run
# merely to discover its version. Execute only the same bounded bytes hashed.
LINUX_PREVIEW_BOOTSTRAP = """import hashlib,os,stat,sys
p=os.path.expanduser('~/.local/lib/mastermind/storage-cleanup/linux_cache_preview.py')
try:
 f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  s=os.fstat(f)
  if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or s.st_mode&0o022 or s.st_nlink!=1 or s.st_size>32768:
   raise ValueError()
  raw=os.read(f,32769)
  end=os.fstat(f)
  if len(raw)!=s.st_size or (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)!=(end.st_dev,end.st_ino,end.st_size,end.st_mtime_ns,end.st_ctime_ns):
   raise ValueError()
 finally:
  os.close(f)
 if hashlib.sha256(raw).hexdigest()!=sys.argv[1]:
  raise ValueError()
except (OSError,ValueError,IndexError):
 raise SystemExit(78)
sys.argv=[p,'--expected-source-sha',sys.argv[1]]
exec(compile(raw,p,'exec'),{'__name__':'__main__','__file__':p})
"""


def linux_cache_preview_command(source: Path | None = None) -> str:
    """Fixed installed-owner command, no arbitrary path/argv or install fallback."""
    import hashlib
    import stat
    source = HERE / "linux_cache_preview.py" if source is None else source
    info = source.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o022 or info.st_size > 32768):
        raise ValueError("preview source identity refused")
    with source.open("rb") as stream:
        raw = stream.read(32769)
        current = os.fstat(stream.fileno())
        if (len(raw) != info.st_size or
                (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns) !=
                (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)):
            raise ValueError("preview source changed")
    sha = hashlib.sha256(raw).hexdigest()
    import shlex
    return "/usr/bin/python3 -c " + shlex.quote(LINUX_PREVIEW_BOOTSTRAP) + " " + sha


def _qualified_linux_preview(body):
    import hashlib
    import math
    import re
    keys = {"schema", "preview_only", "cleanup_authorized", "observed_at",
            "status", "reasons", "caches", "receipt", "sha256", "bytes"}
    if (type(body) is not dict or set(body) != keys
            or body["schema"] != "mastermind.linux_cache_preview.v1"
            or body["preview_only"] is not True or body["cleanup_authorized"] is not False
            or body["status"] not in {"PREVIEWED", "HELD"}
            or type(body["observed_at"]) not in (float, int)
            or not math.isfinite(body["observed_at"]) or body["observed_at"] <= 0
            or type(body["reasons"]) is not list or len(body["reasons"]) > 2
            or type(body["caches"]) is not list or len(body["caches"]) > 2
            or type(body["receipt"]) is not str
            or re.fullmatch(r"linux-cache-preview-[0-9a-f]{32}\.json", body["receipt"]) is None
            or type(body["bytes"]) is not int or not 0 < body["bytes"] <= 32768
            or type(body["sha256"]) is not str):
        raise ValueError("preview body refused")
    reasons = {"linux_nonroot_owner_required", "ownership_or_write_mode", "directory_identity",
               "path_identity", "maintenance_journal_unknown", "live_use_unknown", "admission_busy",
               "admission_lock_identity", "active_lane_or_reconciliation_hold", "owner_or_lock_unavailable"}
    if any(type(r) is not str or r not in reasons for r in body["reasons"]):
        raise ValueError("preview reason refused")
    seen = set()
    for row in body["caches"]:
        roots = {"pip": ".cache/pip", "npm": ".npm/_cacache"}
        if (type(row) is not dict or row.get("cache") not in roots or row["cache"] in seen
                or row.get("relative_root") != roots[row["cache"]]):
            raise ValueError("preview cache refused")
        seen.add(row["cache"])
        common = {"cache", "relative_root", "status"}
        if row["status"] == "PREVIEWED":
            if (set(row) != common | {"entries", "logical_bytes", "allocated_bytes", "inventory_sha256", "filesystem_available_bytes"}
                    or any(type(row[k]) is not int or row[k] < 0 for k in
                           ("entries", "logical_bytes", "allocated_bytes", "filesystem_available_bytes"))
                    or row["entries"] > 20000 or max(row["logical_bytes"], row["allocated_bytes"]) > 256 * 1024 ** 3
                    or type(row["inventory_sha256"]) is not str
                    or re.fullmatch("[a-f0-9]{64}", row["inventory_sha256"]) is None):
                raise ValueError("preview count refused")
        elif row["status"] == "ABSENT":
            if set(row) != common:
                raise ValueError("preview missingness refused")
        elif row["status"] == "HELD":
            known = {"maintenance_effect_unknown", "live_use", "inventory_changed", "filesystem_unavailable",
                     "unrecognized_cache_layout", "inventory_bound", "cache_lock_or_unknown_entry",
                     "filesystem_changed", "different_worker_filesystem", "symlink_hardlink_or_special", "hardlink_or_duplicate"} | reasons
            if set(row) != common | {"reason"} or type(row["reason"]) is not str or row["reason"] not in known:
                raise ValueError("preview hold refused")
        else:
            raise ValueError("preview state refused")
    if (body["status"] == "PREVIEWED") != any(r["status"] == "PREVIEWED" for r in body["caches"]):
        raise ValueError("preview summary refused")
    bare = {k: v for k, v in body.items() if k not in {"receipt", "sha256", "bytes"}}
    raw = (json.dumps(bare, sort_keys=True, allow_nan=False) + "\n").encode()
    if len(raw) != body["bytes"] or hashlib.sha256(raw).hexdigest() != body["sha256"]:
        raise ValueError("preview receipt binding refused")
    return body


def preview_linux_caches(host: str, timeout: int = 20) -> dict:
    """One explicit read/receipt-only call through the EXISTING fleet transport.

    This source extension does not enroll/install a host. Missing/old installed
    preview source fails closed; never sync, probe, retry or run sweep as fallback.
    The caller still needs the existing target-host maintenance authorization.
    """
    if host not in {"ubuntu0", "ubuntu1", "ubuntu2", "ubuntu3", "ubuntu4"}:
        raise ValueError("Linux maintenance target refused")
    if type(timeout) is not int or not 1 <= timeout <= 20:
        raise ValueError("preview timeout refused")
    rc, out, _ = run(SSH + [host, linux_cache_preview_command()], timeout)
    if rc not in (0, 3) or len(out.encode()) > 32768:
        return {"host": host, "state": "UNAVAILABLE", "reason": "preview_transport_or_source_unavailable"}
    try:
        body = _qualified_linux_preview(json.loads(out))
        if (rc == 0) != (body["status"] == "PREVIEWED"):
            raise ValueError()
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return {"host": host, "state": "UNAVAILABLE", "reason": "preview_body_unqualified"}
    return {"host": host, "state": body["status"], "preview": body}

def _cleanup_blocker(row: dict) -> dict | None:
    """A successful remote command is not proof that storage cleanup ran.

    macOS TCC can refuse ~/Documents and the per-host sweep returns rc=0
    with grant-requiring passes skipped. Detect from the existing report.
    """
    result = row.get('sweep')
    if row.get('rc') != 0 or row.get('deferred') or not isinstance(result, dict):
        return None
    grant = str(result.get('grants', 'unknown'))
    skip = str(result.get('skipped', ''))
    nested = result.get('loopback')
    if isinstance(nested, dict):
        grant = str(nested.get('grants', grant))
        skip = str(nested.get('skipped', skip))
    if grant.startswith('denied:') or 'grant-requiring passes' in skip:
        return {'host': row['host'], 'state': 'CLEANUP_BLOCKED',
                'reason': 'macOS Documents/removable-volume access denied',
                'grants': grant[:170], 'skipped': skip[:130],
                'remote_rc': row['rc']}
    return None


def _space_pressure(row: dict) -> dict | None:
    """Read existing fresh peer sweep evidence; never query or modify the peer."""
    snapshot = row.get('sweep')
    if row.get('rc') != 0 or row.get('deferred') or not isinstance(snapshot, dict):
        return None
    free, floor = snapshot.get('free_gib_after'), snapshot.get('floor_gib')
    if type(free) not in (int, float) or type(floor) not in (int, float):
        return None
    if not 0 <= free < 1e9 or not 0 < floor < 1e9:
        return None
    headroom = round(free - floor, 1)
    warn_margin = max(15.0, round(floor * 0.1, 1))
    if headroom >= warn_margin:
        return None
    return dict(host=row['host'], free_gib=free, floor_gib=floor,
                headroom_gib=headroom, warn_margin_gib=warn_margin,
                severity='BREACH' if headroom < 0 else 'WARNING')



def _external_volume_pressure(row: dict) -> list[dict]:
    """Classify peer-reported external mount samples without contacting or modifying it."""
    if row.get('rc') != 0 or row.get('deferred'):
        return []
    sweep_result = row.get('sweep')
    if not isinstance(sweep_result, dict):
        return []
    records = sweep_result.get('external_volumes')
    if not isinstance(records, list):
        return [{'host': row['host'], 'mount': 'external-volume-telemetry',
                 'severity': 'UNVERIFIED', 'state': 'TELEMETRY_MISSING'}]
    observed: list[dict] = []
    for record in records[:12]:
        if not isinstance(record, dict):
            continue
        mount = record.get('mount')
        if (not isinstance(mount, str) or
                (not mount.startswith('/Volumes/') and
                 record.get('state') not in ('POLICY_UNREADABLE', 'LANES_UNRESOLVED'))):
            continue
        state = record.get('state')
        if state != 'OK':
            observed.append({'host': row['host'], 'mount': mount,
                             'severity': 'UNVERIFIED', 'state': str(state)[:64]})
            continue
        free = record.get('free_gib')
        floor = record.get('floor_gib')
        warn = record.get('warn_gib')
        total = record.get('total_gib')
        if not all(type(x) in (int, float) for x in (free, floor, warn, total)):
            observed.append({'host': row['host'], 'mount': mount,
                             'severity': 'UNVERIFIED', 'state': 'INVALID_METRIC'})
            continue
        if not (0 <= free <= total and 0 < floor <= warn <= total < 1e9):
            observed.append({'host': row['host'], 'mount': mount,
                             'severity': 'UNVERIFIED', 'state': 'INVALID_RANGE'})
            continue
        if free < warn:
            observed.append({'host': row['host'], 'mount': mount,
                             'free_gib': free, 'floor_gib': floor, 'warn_gib': warn,
                             'total_gib': total, 'used_pct': record.get('used_pct'),
                             'headroom_gib': round(free-floor, 1),
                             'severity': 'BREACH' if free < floor else 'WARNING'})
    return observed


def _external_prior_unverified(row: dict, previous: dict) -> list[dict]:
    """Retain last-known external breaches until same mount is observed healthy."""
    prior = previous.get('external_volume_pressure_hosts')
    prior = prior if isinstance(prior, list) else []
    carried = previous.get('unverified_prior_external_breaches')
    if isinstance(carried, list):
        prior = prior + carried
    fresh_sweep = row.get('sweep') if row.get('rc') == 0 and not row.get('deferred') else {}
    records = fresh_sweep.get('external_volumes') if isinstance(fresh_sweep, dict) else None
    observed = {r.get('mount'): r for r in records if isinstance(r, dict)
                and isinstance(r.get('mount'), str)} if isinstance(records, list) else {}
    held = []
    for item in prior[:24]:
        if (not isinstance(item, dict) or item.get('host') != row.get('host')
                or (item.get('severity') != 'BREACH'
                    and item.get('state') != 'UNVERIFIED')):
            continue
        mount = item.get('mount')
        now = observed.get(mount)
        if (isinstance(now, dict) and now.get('state') == 'OK'
                and type(now.get('free_gib')) in (int, float)
                and type(now.get('floor_gib')) in (int, float)):
            continue
        held.append({'host': row['host'], 'mount': mount,
                     'state': 'UNVERIFIED',
                     'last_free_gib': item.get('free_gib', item.get('last_free_gib')),
                     'floor_gib': item.get('floor_gib'),
                     'last_observed_epoch': item.get('last_observed_epoch',
                                                      previous.get('time'))})
    return held


def _previous_fleet_report(path: Path) -> dict:
    """Read the existing ledger's last complete report, never query a peer."""
    try:
        lines = path.read_text(errors='replace').splitlines()
        for line in reversed(lines[-4:]):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get('hosts'), list):
                return row
    except OSError:
        pass
    return {}


def _rapid_consumption(row: dict, previous: dict, now: float) -> dict | None:
    """Flag sampled rapid loss near a configured floor, without extrapolation."""
    if row.get('rc') != 0 or row.get('deferred'):
        return None
    snapshot = row.get('sweep')
    if not isinstance(snapshot, dict):
        return None
    free, floor = snapshot.get('free_gib_after'), snapshot.get('floor_gib')
    if type(free) not in (int, float) or type(floor) not in (int, float):
        return None
    if free < 0 or floor <= 0 or free > floor + 30:
        return None
    prior_time = previous.get('time')
    if type(prior_time) not in (int, float):
        return None
    hours = (now - prior_time) / 3600
    if not 0.08 <= hours <= 4:
        return None
    earlier = next((p for p in previous.get('hosts', [])
                    if isinstance(p, dict) and p.get('host') == row['host']), None)
    if not isinstance(earlier, dict) or earlier.get('rc') != 0 or earlier.get('deferred'):
        return None
    previous_free = earlier.get('free_gib')
    if type(previous_free) not in (int, float):
        return None
    lost = round(previous_free - free, 1)
    if lost < 10:
        return None
    return dict(host=row['host'], lost_gib=lost,
                elapsed_hours=round(hours, 2),
                sampled_gib_per_hour=round(lost / hours, 1),
                free_gib_after=free, floor_gib=floor,
                source='two successive existing fleet receipts')


def _unverified_prior_breach(row: dict, previous: dict) -> dict | None:
    """Do not clear a confirmed floor breach merely because the host goes dark."""
    current = row.get('sweep')
    if row.get('rc') == 0 and not row.get('deferred') and isinstance(current, dict):
        free, floor = current.get('free_gib_after'), current.get('floor_gib')
        if type(free) in (int, float) and type(floor) in (int, float):
            return None  # fresh measurement owns the answer, including recovery
    prior = next((p for p in previous.get('hosts', [])
                  if isinstance(p, dict) and p.get('host') == row['host']), None)
    if not isinstance(prior, dict):
        return None
    carried = prior.get('last_known_breach')
    if isinstance(carried, dict) and carried.get('state') == 'UNVERIFIED':
        return carried
    seen = prior.get('storage_pressure')
    if not isinstance(seen, dict):
        seen = prior.get('sweep') if isinstance(prior.get('sweep'), dict) else {}
        seen = dict(free_gib=seen.get('free_gib_after'), floor_gib=seen.get('floor_gib'))
    free, floor = seen.get('free_gib'), seen.get('floor_gib')
    if type(free) not in (int, float) or type(floor) not in (int, float):
        return None
    if not (0 <= free < floor):
        return None
    return dict(host=row['host'], state='UNVERIFIED',
                last_free_gib=free, floor_gib=floor,
                last_observed_epoch=previous.get('time'))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--hosts', default='m1,mb', help='comma-separated ssh host aliases')
    ap.add_argument('--no-sync', action='store_true', help='do not rsync the toolkit first')
    ap.add_argument('--timeout', type=int, default=1800, help='per-host seconds')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--linux-cache-preview', action='store_true',
                    help='explicit preview only; no sync, sweep, cleanup or retry')
    args = ap.parse_args()
    if args.linux_cache_preview:
        hosts = args.hosts.split(',')
        if not args.no_sync or len(hosts) != 1:
            ap.error('Linux preview requires --no-sync and exactly one existing authorized host')
        try:
            result = preview_linux_caches(hosts[0], timeout=min(args.timeout, 20))
        except (OSError, ValueError):
            result = {'state': 'UNAVAILABLE', 'reason': 'preview_configuration_unqualified'}
        print(json.dumps(result, sort_keys=True))
        return 0 if result['state'] == 'PREVIEWED' else 3

    STATE.mkdir(parents=True, exist_ok=True)
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 2 * 3600:
        try:
            os.kill(int(json.loads(LOCK.read_text())['pid']), 0)
            print(json.dumps({'skipped': 'previous fleet sweep still running'}))
            return 0
        except (ProcessLookupError, ValueError, TypeError, KeyError, OSError):
            pass
    LOCK.write_text(json.dumps({'pid': os.getpid(), 'time': time.time()}))
    try:
        try:
            seen = json.loads(SEEN.read_text())
        except (OSError, ValueError):
            seen = {}
        report = {'time': time.time(), 'hosts': []}
        previous = _previous_fleet_report(STATE / 'fleet-remote-sweep.jsonl')
        for host in [h.strip() for h in args.hosts.split(',') if h.strip()]:
            row = {'host': host}
            if not reachable(host):
                row['status'] = 'unreachable'          # laptop away / machine off: expected
            else:
                if not args.no_sync:
                    row['sync'] = sync(host, 300)
                row.update(sweep(host, args.timeout))
                if row.get('rc') == 0 and not row.get('deferred'):
                    seen[host] = time.time()
            last = seen.get(host)
            row['hours_since_sweep'] = round((time.time() - last) / 3600, 1) if last else None
            report['hosts'].append(row)
        # A host that has been gone for days is the one case worth a human's eye:
        # nothing is reclaiming its disk while it is away.
        stale = [h['host'] for h in report['hosts']
                 if h.get('status') == 'unreachable' and (h['hours_since_sweep'] or 1e9) > STALE_HOURS]
        report['stale_hosts'] = stale
        pressure = []
        for row in report['hosts']:
            warning = _space_pressure(row)
            if warning is not None:
                row['storage_pressure'] = warning
                pressure.append(warning)
        report['storage_pressure_hosts'] = pressure
        external_pressure = []
        for row in report['hosts']:
            ext = _external_volume_pressure(row)
            row['external_volume_pressure'] = ext
            external_pressure.extend(ext)
        report['external_volume_pressure_hosts'] = external_pressure
        carried_external = []
        for row in report['hosts']:
            carried_external.extend(_external_prior_unverified(row, previous))
        report['unverified_prior_external_breaches'] = carried_external
        rapid = []
        for row in report['hosts']:
            trend = _rapid_consumption(row, previous, report['time'])
            if trend is not None:
                row['rapid_consumption'] = trend
                rapid.append(trend)
        report['rapid_consumption_hosts'] = rapid
        blocked = []
        for row in report['hosts']:
            reason = _cleanup_blocker(row)
            if reason is not None:
                row['cleanup_capability'] = 'BLOCKED'
                row['cleanup_blocker'] = reason
                blocked.append(reason)
            elif row.get('rc') == 0 and not row.get('deferred'):
                row['cleanup_capability'] = 'NOT_BLOCKED_BY_OBSERVED_GRANTS'
        report['cleanup_blocked_hosts'] = blocked
        unverified = []
        for row in report['hosts']:
            prior_breach = _unverified_prior_breach(row, previous)
            if prior_breach is not None:
                row['last_known_breach'] = prior_breach
                unverified.append(prior_breach)
        report['unverified_prior_breaches'] = unverified
        alert = STATE / 'FLEET-ALERT'
        messages = []
        if stale:
            messages.append(f"no successful sweep for {STALE_HOURS} h on {', '.join(stale)}")
        for item in external_pressure:
            if item['severity'] == 'UNVERIFIED':
                messages.append(
                    f"EXTERNAL VOLUME UNVERIFIED {item['host']} {item['mount']}: "
                    f"{item['state']}")
            else:
                messages.append(
                    f"{'URGENT' if item['severity'] == 'BREACH' else 'WARNING'} "
                    f"{item['host']} EXTERNAL {item['mount']}: "
                    f"{item['free_gib']} GiB free; "
                    f"{item['floor_gib']} GiB critical floor; "
                    f"{item['warn_gib']} GiB warning floor")
        for item in carried_external:
            messages.append(
                f"UNVERIFIED LAST EXTERNAL BREACH {item['host']} {item['mount']}: "
                f"{item['last_free_gib']} GiB last observed")
        for item in blocked:
            messages.append(f"{item['host']} cleanup BLOCKED: {item['reason']}")
        for item in rapid:
            messages.append(
                f"RAPID SPACE LOSS {item['host']}: {item['lost_gib']} GiB "
                f"in {item['elapsed_hours']} sampled hours near disk floor"
            )
        for item in unverified:
            messages.append(
                f"UNVERIFIED LAST-KNOWN FLOOR BREACH {item['host']}: "
                f"{item['last_free_gib']} GiB last measured vs "
                f"{item['floor_gib']} GiB floor; host needs a fresh healthy receipt"
            )
        for row in pressure:
            if row['severity'] == 'BREACH':
                messages.append(
                    f"URGENT {row['host']} STORAGE FLOOR BREACHED: "
                    f"{abs(row['headroom_gib'])} GiB BELOW {row['floor_gib']} GiB floor; "
                    f"only {row['free_gib']} GiB remains"
                )
            else:
                messages.append(
                    f"{row['host']} low-space WARNING: {row['headroom_gib']} GiB "
                    f"above {row['floor_gib']} GiB floor"
                )
        if messages:
            alert.write_text(f"{time.ctime()}: {'; '.join(messages)}\n")
        elif alert.exists():
            alert.unlink()
        SEEN.write_text(json.dumps(seen, indent=1))
        with (STATE / 'fleet-remote-sweep.jsonl').open('a') as f:
            f.write(json.dumps(report) + '\n')
        print(json.dumps(report) if args.json else json.dumps(report, indent=1))
        # unreachable is not a failure -- only a host that answered and then failed is
        return 0 if all(h.get('rc') == 0 for h in report['hosts'] if 'rc' in h) else 1
    finally:
        try:
            LOCK.unlink()
        except OSError:
            pass


if __name__ == '__main__':
    raise SystemExit(main())


def read_original_orch_result(registry_bytes, ssh_config_bytes, *, expected_module_sha,
                              expected_storage_sha, expected_reader_sha, expected_driver_sha):
    """Opt-in fixed original read only; no caller argv/operation/deadline/route.

    Source pins and observed frames are comparisons, never dispatch authority.
    The assigned Root still owns permission for each actual call. No retry here.
    """
    import selectors
    import types
    from ops.native_fabric.quota_continuity.rollout import ubuntu4_policy as policy
    from ops.native_fabric.quota_continuity.rollout import orch_repair_read as reader
    plan = policy.transport_plan(types.SimpleNamespace(SSH=SSH), registry_bytes, ssh_config_bytes,
             kind='read-orch-repair-framed', operation_id=policy.ORCH_REPAIR_ORIGINAL_OPERATION,
             expected_module_sha=expected_module_sha, expected_storage_sha=expected_storage_sha,
             expected_reader_sha=expected_reader_sha, expected_driver_sha=expected_driver_sha)
    raw, expired, overflow, process = b'', False, False, None
    started = time.monotonic()
    try:
        process = subprocess.Popen(plan['argv'], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = plan['timeout'] - (time.monotonic() - started)
                if remaining <= 0 or not selector.select(remaining):
                    expired = True
                    break
                chunk = os.read(process.stdout.fileno(), reader.FRAME_LIMIT + 1 - len(raw))
                if not chunk:
                    selector.unregister(process.stdout)
                    break
                raw += chunk
                if len(raw) > reader.FRAME_LIMIT:
                    overflow = True
                    break
            if not expired and not overflow:
                try:
                    process.wait(timeout=max(0, plan['timeout'] - (time.monotonic() - started)))
                except subprocess.TimeoutExpired:
                    expired = True
    except OSError:
        return reader.transport_observation(b'', plan['context'], returncode=None,
                                             local_unavailable=True)
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
                process.wait()  # Reap OUR local read transport; never a remote cancellation.
            process.stdout.close()
    return reader.transport_observation(raw, plan['context'], returncode=process.returncode,
                                        timed_out=expired, overflow=overflow)
