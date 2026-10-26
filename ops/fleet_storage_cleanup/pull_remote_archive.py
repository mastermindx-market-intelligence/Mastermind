#!/usr/bin/env python3
"""Pull a remote fleet host's archivable trees onto THIS host's external volume.

  pull_remote_archive.py HOST DEST [--apply]
  env: MIN_MB=500

Runs from the Studio because the MacBook has no external drive of its own and no
key to push here -- so the Studio pulls rather than anyone changing auth config
(operator 2026-09-19: "macbook u can archive to the external drive on the m2").

Archives, in order: (1) source trees carrying NO git identity -- nothing can
regenerate those, so they are streamed here as tar.gz, verified readable, and only
then removed on the remote; (2) the remote's preserved-ref bundle/manifest store,
which is copied (never removed -- it is tiny and it is the index of what was reaped).
"""
import json, os, subprocess, sys, time, shutil, hashlib, shlex
from pathlib import Path

APPLY = "--apply" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]
HOST, DEST = args[0], args[1]
MIN_MB = int(os.environ.get("MIN_MB", "500"))
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]


def _verified_archive_member(path):
    """Fail closed for the two-SSD pool; standalone WD archives stay compatible."""
    policy_path = Path.home() / '.config/mastermind/worktree-storage.json'
    try:
        policy = json.loads(policy_path.read_text())
        if not policy.get('overflow_volumes'):
            return None
        import sys
        sys.path.insert(0, str(Path.home() / '.local/lib/mastermind/worktree-storage'))
        from worktree_storage import check_storage
        from pool_storage import members
        dst = Path(path)
        if not dst.is_absolute() or '..' in dst.parts or dst.resolve() != dst:
            raise RuntimeError('archive destination is indirect or unsafe')
        matches = [m for m in members(policy)
                   if dst.is_relative_to(Path(m['mount_point']) / 'Offloaded')]
        if len(matches) != 1:
            raise RuntimeError('archive destination is outside the verified SSD pool')
        member = matches[0]
        check_storage(member, check_space=True)
        return member
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError('pool archive refusal: ' + str(exc)) from exc


# Validate the destination before initiating ANY remote probe.
try:
    POOL_MEMBER = _verified_archive_member(DEST)
except RuntimeError as exc:
    print(json.dumps({"status": "REFUSED", "reason": str(exc)[:240]}))
    raise SystemExit(2)

FIND = r'''
import json, os, subprocess
MARK=("CLAUDE.md","engine","scripts","templates"); out=[]
lsof_result=subprocess.run(["lsof","-a","-d","cwd","-Fn"],capture_output=True,text=True,timeout=300)
if lsof_result.returncode != 0: raise RuntimeError("lsof inventory incomplete")
cw=lsof_result.stdout
cwds={l[1:].rstrip("/") for l in cw.splitlines() if l.startswith("n/")}
cands=set()
for root in (os.path.expanduser("~"), "/private/tmp"):
    if not os.path.isdir(root): continue
    r=subprocess.run(["find",root,"-xdev","-maxdepth","6","-path","*/scripts/worktree_sparse.py",
                      "-not","-path","*/node_modules/*"],capture_output=True,text=True,timeout=1800)
    if r.returncode != 0: raise RuntimeError("find inventory incomplete")
    for l in r.stdout.splitlines():
        l=l.strip()
        if l.endswith("/scripts/worktree_sparse.py"): cands.add(l[:-len("/scripts/worktree_sparse.py")])
for p in sorted(cands):
    if sum(os.path.exists(os.path.join(p,m)) for m in MARK) < 3: continue
    if os.path.exists(os.path.join(p,".git")): continue
    if subprocess.run(["git","--no-optional-locks","-C",p,"rev-parse"],capture_output=True,timeout=120).returncode==0: continue
    if any(c==p or c.startswith(p+"/") for c in cwds): continue
    d=subprocess.run(["du","-sk",p],capture_output=True,text=True,timeout=1800)
    if d.returncode != 0: raise RuntimeError("du inventory incomplete")
    try:
        kb=int(d.stdout.split()[0])
        if kb < 0: raise ValueError("negative du inventory size")
    except (IndexError, ValueError) as exc:
        raise RuntimeError("invalid du inventory size") from exc
    out.append({"path":p,"kb":kb})
print(json.dumps(out))
'''

def run(a, t=600, **kw):
    try: return subprocess.run(a, capture_output=True, text=True, timeout=t, **kw)
    except Exception as e:
        class R: returncode, stdout, stderr = 125, "", str(e)
        return R()

def remote_archive_command(source_path):
    """Shell-quote inventory paths and terminate tar options before the basename."""
    return ("tar -czf - -C " + shlex.quote(os.path.dirname(source_path))
            + " -- " + shlex.quote(os.path.basename(source_path)))


def remote_remove_command(source_path):
    """Prevent shell and option interpretation of any remote inventory name."""
    return "rm -rf -- " + shlex.quote(source_path)


def archive_predelete_proof(source_path, archive_path):
    """Require a fresh byte-level archive match and two idle-process probes.

    Missing helper, changing source or non-deterministic archive => preserve source.
    """
    src = Path(source_path)
    if not src.is_absolute() or '..' in src.parts or len(src.parts) < 4:
        return False
    if not os.path.isfile(archive_path) or os.path.islink(archive_path):
        return False
    try:
        from remote_offload import remote_active_paths
        if remote_active_paths(HOST, source_path):
            return False
        local_hash = hashlib.sha256()
        with open(archive_path, 'rb') as archive:
            for block in iter(lambda: archive.read(8 * 1024 * 1024), b''):
                local_hash.update(block)
        directory = shlex.quote(os.path.dirname(source_path))
        basename = shlex.quote(os.path.basename(source_path))
        command = (
            f'set -o pipefail; /usr/bin/tar -czf - -C {directory} -- {basename} '
            '| /usr/bin/shasum -a 256'
        )
        result = run(SSH + [HOST, command], 6 * 3600)
        fields = result.stdout.strip().split()
        if result.returncode or not fields or fields[0] != local_hash.hexdigest():
            return False
        if remote_active_paths(HOST, source_path):
            return False
        return True
    except (ImportError, OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f'SKIP archive source-integrity unavailable: {str(exc)[:140]}', flush=True)
        return False


r = run(SSH + [HOST, "/usr/bin/python3 -"], 2400, input=FIND)
if r.returncode:
    print(json.dumps({"status": "REFUSED", "reason": "remote probe failed", "err": r.stderr[-200:]})); raise SystemExit(1)
def verified_probe_rows(stdout, min_mb):
    """Accept only a complete successful remote inventory, never a fabricated empty list."""
    lines = (stdout or "").strip().splitlines()
    if not lines:
        raise ValueError("remote inventory produced no stdout")
    payload = json.loads(lines[-1])
    if type(payload) is not list:
        raise ValueError("remote inventory is not an array")
    rows = []
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("remote inventory member is not an object")
        path, kb = row.get("path"), row.get("kb")
        if (not isinstance(path, str) or not path.startswith("/")
                or ".." in Path(path).parts or any(ord(c) < 32 for c in path)):
            raise ValueError("invalid remote inventory path")
        if type(kb) is not int or kb < 0:
            raise ValueError("invalid remote inventory size")
        if kb >= min_mb * 1024:
            rows.append({"path": path, "kb": kb})
    return rows


try: rows = verified_probe_rows(r.stdout, MIN_MB)
except (ValueError, TypeError, KeyError) as e:
    print(json.dumps({"status": "REFUSED", "reason": f"unparsable probe: {e}"})); raise SystemExit(1)

print(f"{HOST}: {len(rows)} orphan tree(s), {sum(x['kb'] for x in rows)/1048576:.2f} GiB")
for x in rows: print(f"  {x['kb']/1048576:6.2f} GiB  {x['path']}")
if not APPLY:
    print(json.dumps({
        "status": "REPORT_ONLY_SOURCE_PRESERVED",
        "host": HOST, "dest": DEST,
        "eligible_source_less_trees": len(rows),
        "eligible_gib": round(sum(x['kb'] for x in rows) / 1048576, 2),
        "remote_deletions": 0,
    }))
    raise SystemExit(0)

if POOL_MEMBER:
    try:
        _verified_archive_member(DEST)
    except RuntimeError as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)[:240]}))
        raise SystemExit(2)
os.makedirs(DEST, exist_ok=True)

# The destination is an EXTERNAL volume, and macOS grants removable-volume access
# as its own TCC category -- separate from the ~/Documents access sweep.py's
# grants() probe tests. So a launchd sweep reports `grants: ok`, walks every pass,
# and then dies here with an uncaught PermissionError (errno 1) on the first
# open(): measured 2026-09-21, this had failed on BOTH peers every cycle since the
# pass was written, while the receipt above it said the grants were fine. A probe
# that does not touch the surface the pass actually writes to proves nothing about
# that surface. Fail here, named and structured, instead of as a traceback.
probe = os.path.join(DEST, ".write-probe-%d" % os.getpid())
try:
    with open(probe, "wb") as _fh:
        _fh.write(b"x")
    os.unlink(probe)
except OSError as e:
    print(json.dumps({"status": "REFUSED", "reason": "dest-not-writable",
                      "dest": DEST, "errno": e.errno, "error": str(e),
                      "hint": "launchd context lacks the removable-volume grant; "
                              "run this pass from a session that has it"}))
    raise SystemExit(2)

ok = 0; freed = 0
for x in rows:
    p = x["path"]
    if POOL_MEMBER:
        # Leave the configured reserve even for a poorly compressible archive.
        needed = (POOL_MEMBER['min_free_bytes'] + int(x['kb'] * 1024 * 1.05)
                  + (256 << 20))
        try:
            _verified_archive_member(DEST)
            free = shutil.disk_usage(POOL_MEMBER['mount_point']).free
        except (OSError, RuntimeError) as exc:
            print(f"SKIP pool-unavailable {p}: {str(exc)[:110]}"); continue
        if free < needed:
            print(f"SKIP pool-free-floor {p}: available={free} required={needed}"); continue
    tarp = os.path.join(DEST, HOST + "_" + p.strip("/").replace("/", "_") + ".tar.gz")
    t0 = time.time()
    try:
        with open(tarp, "wb") as fh:
            c = subprocess.run(SSH + [HOST, remote_archive_command(p)],
                               stdout=fh, stderr=subprocess.PIPE, timeout=6 * 3600)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"SKIP stream-error {p}: {type(e).__name__}: {str(e)[:160]}", flush=True)
        continue
    if c.returncode or os.path.getsize(tarp) < 1024:
        print(f"SKIP stream-failed {p}: {(c.stderr or b'')[-160:]}"); continue
    v = run(["tar", "-tzf", tarp], 3 * 3600)
    n = len([l for l in v.stdout.splitlines() if l.strip()])
    if v.returncode or n < 100:
        print(f"SKIP archive-unverified {p} entries={n}"); continue
    if not archive_predelete_proof(p, tarp):
        print(f"SKIP remote-delete source or checksum not proven {p}"); continue
    if POOL_MEMBER:
        try:
            _verified_archive_member(DEST)
            if shutil.disk_usage(POOL_MEMBER['mount_point']).free < POOL_MEMBER['min_free_bytes']:
                print(f"SKIP remote-delete pool below reserve {p}"); continue
        except (OSError, RuntimeError) as exc:
            print(f"SKIP remote-delete pool unavailable {p}: {str(exc)[:110]}"); continue
    rm = run(SSH + [HOST, remote_remove_command(p)], 3600)
    if rm.returncode:
        print(f"ARCHIVED but remote rm failed {p}: {rm.stderr[-160:]}"); continue
    ok += 1; freed += x["kb"]
    print(f"ARCHIVED {x['kb']/1048576:6.2f} GiB -> {os.path.getsize(tarp)/1073741824:.2f} GiB "
          f"({n} entries, {round(time.time()-t0)}s) {p}", flush=True)

# the preserved-ref store is the index of everything the reaper removed: copy, never move
bdir = os.path.join(DEST, HOST + "-scratch-reap")
os.makedirs(bdir, exist_ok=True)
run(["rsync", "-a", "-e", " ".join(SSH),
     f"{HOST}:.local/state/mastermind/scratch-reap/", bdir + "/"], 3600)
print(json.dumps({"archived": ok, "freed_gib": round(freed/1048576, 2), "dest": DEST}))
