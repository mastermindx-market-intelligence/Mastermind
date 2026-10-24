"""Private root-transaction host observation producer, never admission authority.

Only ``qualify_paid_host`` owns the fresh incumbent host-pull child.  Transport
JSON and telemetry are untrusted DATA, not this process-local qualification.
The existing locked installer must separately authorize and bracket publication.
No function here creates remote paths, credentials, leases or service state.
"""
from __future__ import annotations

import base64
import errno
import hashlib
import grp
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import selectors
import shlex
import stat
import subprocess
import sys
import time

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_RELEASE = re.compile(r"[0-9a-f]{40}\Z")
SOURCE_NAMES = frozenset({"host_pull.sh", "host_pull_backend.py",
    "host_pull_probe.template", "paid_host_qualification.py", "remote_sub.sh"})
_SCHEMA = "mastermind.paid_host_observation/v1"
_CONTEXT = "canonical-paid-physical-owner.v1"
_TRANSPORT_UID = 501  # Same fixed owner as canonical_paid_definition.PAID_BRIDGE_UID.
_LIMIT = 65536
_SEAL = object()
_POPEN_TYPE = subprocess.Popen


class QualificationRefused(ValueError):
    pass


def _refuse():
    raise QualificationRefused("paid_host_qualification_refused")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _closed(value, keys):
    if (type(value) is not dict or any(type(k) is not str for k in value)
            or set(value) != keys):
        _refuse()
    return value


def _text(value, pattern):
    if type(value) is not str or not pattern.fullmatch(value):
        _refuse()
    return value


def _path(value):
    if (type(value) is not str or not value.startswith("/") or len(value) > 4096
            or any(c in value for c in "\0\r\n") or value != str(Path(value))
            or ".." in Path(value).parts):
        _refuse()
    return value


def _integer(value, low=0):
    if type(value) is not int or not low <= value < 2**63:
        _refuse()
    return value


def _json(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= _LIMIT:
        _refuse()
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                _refuse()
            result[k] = v
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: _refuse())
    except (ValueError, UnicodeError, RecursionError):
        _refuse()


def _identity(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid,
            st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _read_owned(path, *, owners, maximum=2*1024*1024):
    """Walk physical directories and read the same stable owned regular inode."""
    path = _path(str(path))
    parts = Path(path).parts
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            info = os.fstat(child)
            if info.st_uid not in owners or info.st_mode & 0o022:
                os.close(child)
                _refuse()
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid not in owners
                    or before.st_mode & 0o022 or before.st_nlink != 1
                    or not 0 < before.st_size <= maximum):
                _refuse()
            chunks = []
            size = 0
            while True:
                chunk = os.read(fd, min(65536, maximum + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > maximum:
                    _refuse()
            raw = b"".join(chunks)
            if (_identity(before) != _identity(os.fstat(fd))
                    or _identity(before) != _identity(os.stat(parts[-1], dir_fd=directory,
                                                              follow_symlinks=False))
                    or len(raw) != before.st_size):
                _refuse()
            return raw, _identity(before)
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def _snapshot(hosts_path, host_ref, expected_sources):
    _closed(expected_sources, SOURCE_NAMES)
    source = Path(__file__).absolute().parent
    snapshots = {}
    for name in sorted(SOURCE_NAMES):
        expected = _text(expected_sources[name], _SHA)
        raw, identity = _read_owned(source/name, owners={0})
        observed = hashlib.sha256(raw).hexdigest()
        if observed != expected:
            _refuse()
        snapshots[name] = {"sha256": observed, "identity": identity}
    # Registry can be the incumbent user's file; its exact held bytes/identity
    # are joined into the request. The child never reselects another route.
    raw, identity = _read_owned(hosts_path, owners={0, _TRANSPORT_UID})
    try:
        registry = _json(raw)
        if type(registry) is not dict or type(registry.get(host_ref)) is not dict:
            _refuse()
        entry = registry[host_ref]
        alias = _text(entry.get("ssh_alias"), _ID)
        modes, held = entry.get("allowed_modes"), entry.get("qualification_only_modes", [])
        def names(items):
            return (type(items) is list and all(type(x) is str and _ID.fullmatch(x) for x in items)
                    and len(items) == len(set(items)))
        if (entry.get("local") is not None and type(entry["local"]) is not bool):
            _refuse()
        if (not names(entry.get("roles")) or not names(held)
                or modes is not None and not names(modes)):
            _refuse()
        if (entry.get("local") is True or entry.get("platform") != "linux"
                or type(entry.get("roles")) is not list or "lanes" not in entry["roles"]
                or (modes is not None and (type(modes) is not list or "glm" not in modes))
                or type(held) is not list or "glm" in held):
            _refuse()
        return {"sources": snapshots, "registry_sha256": hashlib.sha256(raw).hexdigest(),
                "registry_identity": identity, "alias": alias}
    except (KeyError, TypeError):
        _refuse()


def _physical_directory(path, owners):
    path = _path(path)
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in Path(path).parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            info = os.fstat(child)
            if info.st_uid not in owners or info.st_mode & 0o022:
                os.close(child)
                _refuse()
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _transport_principal():
    try:
        record = pwd.getpwuid(_TRANSPORT_UID)
        reverse = pwd.getpwnam(record.pw_name)
        if (record.pw_uid != _TRANSPORT_UID or reverse != record
                or type(record.pw_gid) is not int or record.pw_gid <= 0):
            _refuse()
        _text(record.pw_name, _ID)
        _path(record.pw_dir)
        home_fd = _physical_directory(record.pw_dir, {0, _TRANSPORT_UID})
        try:
            home = os.fstat(home_fd)
        finally:
            os.close(home_fd)
        group = grp.getgrgid(record.pw_gid)
        if (not stat.S_ISDIR(home.st_mode) or home.st_uid != _TRANSPORT_UID
                or home.st_mode & 0o022 or grp.getgrnam(group.gr_name) != group):
            _refuse()
        return {"uid": record.pw_uid, "gid": record.pw_gid,
                "user": record.pw_name, "home": record.pw_dir}
    except (KeyError, OSError):
        _refuse()


def _owned_transport(request, principal):
    """One real child, bounded capture, no caller runner/callback injection."""
    script = Path(__file__).absolute().with_name("host_pull.sh")
    env = {"HOME": principal["home"], "USER": principal["user"],
           "LOGNAME": principal["user"], "LC_ALL": "C", "LANG": "C",
           "PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin:/usr/sbin:/sbin",
           "PYTHONDONTWRITEBYTECODE": "1"}
    child = subprocess.Popen(["/bin/bash", str(script), "--paid-qualification", request["host_ref"]],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, cwd="/", user=principal["uid"], group=principal["gid"],
        extra_groups=[], start_new_session=True, close_fds=True)
    started = time.monotonic()
    with selectors.DefaultSelector() as selected:
        assert child.stdin is not None and child.stdout is not None and child.stderr is not None
        try:
            outgoing = _canonical(request)
            offset = 0
            os.set_blocking(child.stdin.fileno(), False)
            selected.register(child.stdin, selectors.EVENT_WRITE, "in")
            selected.register(child.stdout, selectors.EVENT_READ, "out")
            selected.register(child.stderr, selectors.EVENT_READ, "err")
            captured = {"out": bytearray(), "err": bytearray()}
            while selected.get_map():
                remaining = 35 - (time.monotonic() - started)
                if remaining <= 0:
                    _refuse()
                for key, _ in selected.select(min(remaining, 0.25)):
                    if key.data == "in":
                        try:
                            offset += os.write(key.fileobj.fileno(), outgoing[offset:offset+4096])
                        except BlockingIOError:
                            continue
                        if offset == len(outgoing):
                            selected.unregister(key.fileobj)
                            child.stdin.close()
                        continue
                    part = os.read(key.fileobj.fileno(), 8192)
                    if not part:
                        selected.unregister(key.fileobj)
                    else:
                        captured[key.data].extend(part)
                        if len(captured[key.data]) > _LIMIT:
                            _refuse()
            child.wait(timeout=max(0.01, 35 - (time.monotonic() - started)))
            if child.returncode != 0 or captured["err"]:
                _refuse()
            # Retain the actual consumed process object, not a supplied PID or
            # a dict receipt that another caller could pass as an observation.
            return bytes(captured["out"]), child
        finally:
            if child.poll() is None:
                # Only our own short read-only transport process group; no
                # worker/controller/lease exists in this transaction.
                import signal
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
            child.stdin.close()
            child.stdout.close()
            child.stderr.close()


_REQUEST_FIELDS = frozenset({"schema", "host_ref", "transport_alias", "nonce",
    "python_path", "capture_root", "release_sha", "source_manifest_sha256",
    "preimage_sha256", "registry_sha256", "sources_sha256", "probe_sha256", "context"})


def _request(value):
    _closed(value, _REQUEST_FIELDS)
    if (type(value["schema"]) is not str or type(value["context"]) is not str
            or value["schema"] != "mastermind.paid_host_probe_request/v1" or value["context"] != _CONTEXT):
        _refuse()
    for name in ("host_ref", "transport_alias", "nonce"):
        _text(value[name], _ID)
    for name in ("source_manifest_sha256", "preimage_sha256", "registry_sha256", "probe_sha256"):
        _text(value[name], _SHA)
    _text(value["release_sha"], _RELEASE)
    for name in ("python_path", "capture_root"):
        _path(value[name])
    root = Path(value["capture_root"])
    if root.name != "lanes" or root.parent.name != "ext" or str(root.parent.parent) == "/":
        _refuse()
    _closed(value["sources_sha256"], SOURCE_NAMES)
    for h in value["sources_sha256"].values():
        _text(h, _SHA)
    if value["probe_sha256"] != hashlib.sha256(_REMOTE_PROBE.encode()).hexdigest():
        _refuse()
    if len(_canonical(value)) > 16384:
        _refuse()
    return json.loads(_canonical(value))


def build_paid_probe(value):
    """Pure command compilation for the existing shell transport, no grant."""
    request = _request(value)
    lane = str(Path(request["capture_root"]).parent.parent)
    encoded = base64.b64encode(_canonical(request)).decode("ascii")
    # Same reviewed physical-owner precedence as remote_sub. No -l shell,
    # remote PATH substitute, interpreter fallback or provider invocation.
    inner = ("export PATH=" + shlex.quote(lane + "/venv/bin") + ':"$HOME/.local/bin":/opt/homebrew/bin:"$PATH"; '
        + "source " + shlex.quote(lane + "/ext/HOST_ENV.sh") + " >/dev/null 2>&1 || exit 78; "
        + "export PATH=" + shlex.quote(lane + "/venv/bin") + ':"$PATH"; '
        + "exec python3 -I -S -c " + shlex.quote(_REMOTE_PROBE) + " " + shlex.quote(encoded))
    return request["transport_alias"], "/bin/bash -c " + shlex.quote(inner)


def prepare_paid_transport(host_ref, raw):
    request = _request(_json(raw))
    if request["host_ref"] != _text(host_ref, _ID):
        _refuse()
    return build_paid_probe(request)


_RESPONSE_FIELDS = frozenset({"schema", "request", "binary", "worker_uid", "worker_gid",
    "worker_user", "boot_id", "capture_root", "capture_identity", "context_identity"})
_BINARY_FIELDS = frozenset({"path", "real_path", "version", "sha256", "team_identifier",
    "size", "device", "inode", "mode", "uid", "gid", "mtime_ns"})
_DIR_FIELDS = frozenset({"device", "inode", "mode", "uid", "gid", "mtime_ns"})


def _observation(raw, request):
    value = _closed(_json(raw), _RESPONSE_FIELDS)
    if (type(value["schema"]) is not str or value["schema"] != _SCHEMA
            or _canonical(value["request"]) != _canonical(request)):
        _refuse()
    uid, gid = _integer(value["worker_uid"], 1), _integer(value["worker_gid"], 1)
    _text(value["worker_user"], _ID)
    boot = value["boot_id"]
    if type(boot) is not str or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", boot):
        _refuse()
    binary = _closed(value["binary"], _BINARY_FIELDS)
    if binary["path"] != request["python_path"] or binary["team_identifier"] is not None:
        _refuse()
    for name in ("path", "real_path"):
        _path(binary[name])
    for name in ("size", "device", "inode", "mode", "uid", "gid", "mtime_ns"):
        _integer(binary[name], 1 if name in ("size", "inode") else 0)
    _text(binary["sha256"], _SHA)
    if (not stat.S_ISREG(binary["mode"]) or not binary["mode"] & 0o111
            or binary["mode"] & 0o022 or binary["uid"] not in (0, uid)
            or type(binary["version"]) is not str or not 0 < len(binary["version"]) <= 512
            or "\0" in binary["version"] or binary["version"] != binary["version"].strip()):
        _refuse()
    if value["capture_root"] != request["capture_root"]:
        _refuse()
    capture = _closed(value["capture_identity"], _DIR_FIELDS)
    for v in capture.values():
        _integer(v)
    if (capture["uid"] != uid or capture["gid"] != gid or not capture["inode"]
            or not stat.S_ISDIR(capture["mode"]) or stat.S_IMODE(capture["mode"]) != 0o700):
        _refuse()
    context = _closed(value["context_identity"], frozenset({"profile", "host_env_path",
        "host_env_sha256", "kernel_executable", "lane_root"}))
    if (context["profile"] != _CONTEXT or context["kernel_executable"] != binary["real_path"]
            or context["lane_root"] != str(Path(request["capture_root"]).parent.parent)
            or context["host_env_path"] != context["lane_root"] + "/ext/HOST_ENV.sh"):
        _refuse()
    _text(context["host_env_sha256"], _SHA)
    return json.loads(_canonical(value))


class PaidHostQualification:
    """Nonserializable, single-use same-process observation; never a grant."""
    __slots__ = ("_seal", "_pid", "_at", "_binding", "_snapshot", "_principal", "_observation", "_child", "_consumed")

    def __new__(cls, seal=None):
        if cls is not PaidHostQualification or seal is not _SEAL:
            _refuse()
        return super().__new__(cls)

    def __setattr__(self, name, value):
        if name != "_consumed" and hasattr(self, name):
            _refuse()
        object.__setattr__(self, name, value)

    def __reduce_ex__(self, protocol):
        _refuse()


def _binding(host_ref, hosts_path, release_sha, source_manifest_sha256, preimage_sha256, expected_sources):
    _text(host_ref, _ID)
    _path(hosts_path)
    _text(release_sha, _RELEASE)
    _text(source_manifest_sha256, _SHA)
    _text(preimage_sha256, _SHA)
    _closed(expected_sources, SOURCE_NAMES)
    for v in expected_sources.values():
        _text(v, _SHA)
    return json.loads(_canonical(dict(host_ref=host_ref, hosts_path=hosts_path, release_sha=release_sha,
        source_manifest_sha256=source_manifest_sha256, preimage_sha256=preimage_sha256,
        expected_sources=expected_sources)))


def qualify_paid_host(*, host_ref, hosts_path, python_path, capture_root, release_sha,
                      source_manifest_sha256, preimage_sha256, expected_sources):
    """Own one fresh host-pull read inside the caller's real locked transaction."""
    try:
        if os.geteuid() != 0 or os.getuid() != 0:
            _refuse()
        binding = _binding(host_ref, hosts_path, release_sha, source_manifest_sha256,
                           preimage_sha256, expected_sources)
        principal = _transport_principal()
        snapshot = _snapshot(hosts_path, host_ref, expected_sources)
        request = _request(dict(schema="mastermind.paid_host_probe_request/v1", host_ref=host_ref,
            transport_alias=snapshot["alias"], nonce=secrets.token_hex(32),
            python_path=python_path, capture_root=capture_root, release_sha=release_sha,
            source_manifest_sha256=source_manifest_sha256, preimage_sha256=preimage_sha256,
            registry_sha256=snapshot["registry_sha256"], sources_sha256=dict(expected_sources),
            probe_sha256=hashlib.sha256(_REMOTE_PROBE.encode()).hexdigest(), context=_CONTEXT))
        raw, child = _owned_transport(request, principal)
        observed = _observation(raw, request)
        if type(child) is not _POPEN_TYPE or child.returncode != 0 or type(child.pid) is not int or child.pid <= 0:
            _refuse()
        if _snapshot(hosts_path, host_ref, expected_sources) != snapshot or _transport_principal() != principal:
            _refuse()
        result = PaidHostQualification(_SEAL)
        result._seal, result._pid, result._at = _SEAL, os.getpid(), time.monotonic()
        result._binding, result._snapshot, result._principal = binding, snapshot, principal
        result._observation, result._child, result._consumed = observed, child, False
        return result
    except (OSError, ValueError, TypeError, KeyError, OverflowError, subprocess.SubprocessError):
        _refuse()


def consume_paid_host_qualification(value, *, host_ref, hosts_path, release_sha,
                                    source_manifest_sha256, preimage_sha256, expected_sources):
    """Consume only a fresh producer-owned result in the same root transaction."""
    try:
        if (os.geteuid() != 0 or os.getuid() != 0 or type(value) is not PaidHostQualification
                or value._seal is not _SEAL or value._pid != os.getpid() or value._consumed
                or not 0 <= time.monotonic() - value._at <= 60):
            _refuse()
        binding = _binding(host_ref, hosts_path, release_sha, source_manifest_sha256,
                           preimage_sha256, expected_sources)
        if (binding != value._binding
                or _snapshot(hosts_path, host_ref, expected_sources) != value._snapshot
                or _transport_principal() != value._principal
                or type(value._child) is not _POPEN_TYPE or value._child.returncode != 0
                or type(value._child.pid) is not int or value._child.pid <= 0):
            _refuse()
        value._consumed = True
        return json.loads(_canonical(value._observation))
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        _refuse()


_REMOTE_PROBE = r'''import base64,errno,hashlib,json,os,pwd,stat,sys

def fail():
    raise ValueError('paid_host_probe_refused')

def identity(s):
    return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_size,s.st_mtime_ns,s.st_ctime_ns)

def acl(fd):
    for key in ('system.posix_acl_access','system.posix_acl_default'):
        try:
            os.getxattr(fd,key)
        except OSError as e:
            if e.errno not in (errno.ENODATA,getattr(errno,'ENOATTR',errno.ENODATA)):
                fail()
        else:
            fail()

def walk(path,uid):
    if not path.startswith('/') or '..' in path.split('/') or '\x00' in path:
        fail()
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in path.split('/')[1:]:
            if not part: fail()
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            s=os.fstat(child)
            if s.st_uid not in (0,uid) or s.st_mode&0o022:
                os.close(child);fail()
            acl(child)
            os.close(fd);fd=child
        return fd
    except BaseException:
        os.close(fd);raise

def read_file(path,uid,limit):
    parent,name=os.path.split(path)
    directory=walk(parent,uid)
    try:
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        try:
            before=os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_uid not in (0,uid) or before.st_mode&0o022 or before.st_size>limit or before.st_size<=0:
                fail()
            acl(fd)
            data=b''
            while len(data)<=limit:
                part=os.read(fd,min(65536,limit+1-len(data)))
                if not part: break
                data+=part
            if len(data)!=before.st_size or identity(before)!=identity(os.fstat(fd)) or identity(before)!=identity(os.stat(name,dir_fd=directory,follow_symlinks=False)):
                fail()
            return data,before
        finally: os.close(fd)
    finally: os.close(directory)

def observe(p):
    if sys.platform!='linux': fail()
    uid,gid=os.getuid(),os.getgid()
    if uid<=0 or gid<=0 or os.geteuid()!=uid or os.getegid()!=gid: fail()
    user=pwd.getpwuid(uid).pw_name
    if pwd.getpwnam(user).pw_uid!=uid: fail()
    requested=p['python_path']
    if os.path.abspath(sys.executable)!=requested: fail()
    links=[];target=requested
    for _ in range(9):
        parent,name=os.path.split(target)
        directory=walk(parent,uid)
        try: before=os.stat(name,dir_fd=directory,follow_symlinks=False)
        finally: os.close(directory)
        if not stat.S_ISLNK(before.st_mode): break
        if before.st_uid not in (0,uid): fail()
        link=os.readlink(target)
        links.append((target,identity(before),link))
        target=os.path.normpath(link if link.startswith('/') else os.path.join(parent,link))
    else: fail()
    real=os.path.realpath(target)
    if real!=target or os.path.realpath('/proc/self/exe')!=real: fail()
    binary,bs=read_file(real,uid,128*1024*1024)
    if not bs.st_mode&0o111: fail()
    for path,before,link in links:
        if identity(os.lstat(path))!=before or os.readlink(path)!=link: fail()
    root=p['capture_root'];fd=walk(root,uid)
    try:
        cs=os.fstat(fd);acl(fd)
        if cs.st_uid!=uid or cs.st_gid!=gid or stat.S_IMODE(cs.st_mode)!=0o700: fail()
        if identity(cs)!=identity(os.stat(root,follow_symlinks=False)): fail()
    finally: os.close(fd)
    lane=os.path.dirname(os.path.dirname(root));host_env=lane+'/ext/HOST_ENV.sh'
    context,_=read_file(host_env,uid,65536)
    boot=open('/proc/sys/kernel/random/boot_id',encoding='ascii').read(64).strip()
    return dict(schema='mastermind.paid_host_observation/v1',request=p,
        binary=dict(path=requested,real_path=real,version=sys.version,sha256=hashlib.sha256(binary).hexdigest(),team_identifier=None,
            size=bs.st_size,device=bs.st_dev,inode=bs.st_ino,mode=bs.st_mode,uid=bs.st_uid,gid=bs.st_gid,mtime_ns=bs.st_mtime_ns),
        worker_uid=uid,worker_gid=gid,worker_user=user,boot_id=boot,capture_root=root,
        capture_identity=dict(device=cs.st_dev,inode=cs.st_ino,mode=cs.st_mode,uid=cs.st_uid,gid=cs.st_gid,mtime_ns=cs.st_mtime_ns),
        context_identity=dict(profile=p['context'],host_env_path=host_env,host_env_sha256=hashlib.sha256(context).hexdigest(),kernel_executable=real,lane_root=lane))

if __name__=='__main__':
    try:
        p=json.loads(base64.b64decode(sys.argv[1],validate=True))
        result=observe(p)
        print(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False))
    except Exception:
        sys.exit(78)
'''
